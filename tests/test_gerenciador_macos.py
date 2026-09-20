"""Proteções do instalador, sem alterar launchd ou dados do computador."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.gerenciar_macos import Manager, copy_data, copy_database, has_financial_data, sha256


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = Manager(self.root / 'Aplicativos com espaço', self.root / 'Estado com espaço')
        self.manager.state.mkdir()
        self.source = self.root / 'v1'
        self.source.mkdir()
        self.db = self.source / 'emprestimos.db'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT)')
            db.execute("INSERT INTO clientes VALUES (1, 'Cliente sintético')")
            db.commit()
        (self.source / '.secret_key').write_text('chave-sintetica-apenas-para-teste')
        (self.source / 'comprovantes').mkdir()
        (self.source / 'comprovantes/prova.pdf').write_bytes(b'comprovante sintetico')

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_includes_wal_without_changing_source(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA wal_autocheckpoint=0')
            db.execute("INSERT INTO clientes VALUES (2, 'Ainda no WAL')")
            db.commit()
            before = sha256(self.db)
            destination = self.root / 'copia.db'
            copy_database(self.db, destination)
            self.assertEqual(sha256(self.db), before)
            with closing(sqlite3.connect(destination)) as clone:
                self.assertEqual(clone.execute('SELECT COUNT(*) FROM clientes').fetchone()[0], 2)

    def test_copy_preserves_proofs_key_and_values(self):
        before = sha256(self.db)
        target = self.root / 'importacao'
        copy_data(self.db, target)
        self.assertTrue(has_financial_data(target / 'emprestimos.db'))
        self.assertEqual(sha256(self.db), before)
        self.assertEqual((target / '.secret_key').read_bytes(), (self.source / '.secret_key').read_bytes())
        self.assertEqual((target / 'comprovantes/prova.pdf').read_bytes(), b'comprovante sintetico')
        with self.assertRaises(ValueError):
            copy_data(self.db, target)

    def test_import_never_overwrites_a_used_destination(self):
        copy_data(self.db, self.manager.data)
        before = sha256(self.manager.data / 'emprestimos.db')
        with patch.object(self.manager, 'installed', return_value=self.root), patch.object(self.manager, 'stop') as stop:
            with self.assertRaisesRegex(ValueError, 'já contém'):
                self.manager.import_v1(self.db)
            stop.assert_not_called()
        self.assertEqual(sha256(self.manager.data / 'emprestimos.db'), before)

    def test_failed_validation_does_not_stop_or_import(self):
        before = sha256(self.db)
        with patch.object(self.manager, 'installed', return_value=self.root), \
             patch.object(self.manager, 'confirm', return_value=True), \
             patch.object(self.manager, 'stop') as stop, \
             patch('scripts.gerenciar_macos.run', side_effect=subprocess.CalledProcessError(1, 'validar')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.manager.import_v1(self.db)
            stop.assert_not_called()
        self.assertFalse(self.manager.data.exists())
        self.assertEqual(sha256(self.db), before)

    def test_backup_has_integrity_manifest(self):
        copy_data(self.db, self.manager.data)
        backup = self.manager.backup('teste')
        manifest = json.loads((backup / 'manifesto.json').read_text())
        self.assertEqual(manifest['banco_sha256'], sha256(backup / 'data/emprestimos.db'))
        self.assertTrue((backup / 'data/comprovantes/prova.pdf').is_file())

    def test_cancelled_update_does_not_touch_service_or_data(self):
        with patch.object(self.manager, 'guard_plist'), patch.object(self.manager, 'remote_commit', return_value='a' * 40), \
             patch.object(self.manager, 'prepare', return_value=self.root), \
             patch.object(self.manager, 'confirm', return_value=False), \
             patch.object(self.manager, 'stop') as stop, patch.object(self.manager, 'backup') as backup:
            self.manager.update()
            stop.assert_not_called()
            backup.assert_not_called()
        self.assertFalse(self.manager.current.exists())

    def test_environment_does_not_inherit_development_database_or_secret(self):
        with patch.dict('os.environ', {'EMPRESTIMO_DATABASE': 'banco-real-externo.db', 'SECRET_KEY': 'nao-herdar',
                                     'PYTHONPATH': 'modulos-externos', 'EMPRESTIMO_HTTPS': '1'}):
            env = self.manager.environment()
        self.assertEqual(env['EMPRESTIMO_DATABASE'], str(self.manager.data / 'emprestimos.db'))
        self.assertNotIn('SECRET_KEY', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertEqual(env['EMPRESTIMO_HTTPS'], '0')

    def test_refuses_overlapping_directories(self):
        with self.assertRaises(ValueError):
            Manager(self.root, self.root / 'data')

    def test_never_replaces_existing_current_directory(self):
        self.manager.current.mkdir(parents=True)
        with self.assertRaises(ValueError):
            self.manager.point_to(self.root)
        self.assertTrue(self.manager.current.is_dir())

    def test_occupied_port_does_not_kill_other_process(self):
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            self.manager.port = sock.getsockname()[1]
            with self.assertRaisesRegex(ValueError, 'ocupada'):
                self.manager.port_free()
            self.assertGreater(sock.fileno(), 0)
