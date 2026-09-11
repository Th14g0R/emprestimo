import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StartupTest(unittest.TestCase):
    def test_entrypoints(self):
        for entrypoint in ("script", "wsgi"):
            with self.subTest(entrypoint=entrypoint), tempfile.TemporaryDirectory() as directory:
                env = dict(os.environ, EMPRESTIMO_DATA_DIR=directory,
                           EMPRESTIMO_DATABASE=str(Path(directory) / "test.db"),
                           EMPRESTIMO_SECRET_KEY_FILE=str(Path(directory) / ".secret_key"),
                           SECRET_KEY="startup-test-only", EMPRESTIMO_DEBUG="0",
                           EMPRESTIMO_TRUSTED_HOSTS="localhost")
                result = subprocess.run(
                    [sys.executable, "-c", f"""
import runpy
from unittest.mock import patch
from flask import Flask

created = []
original_init = Flask.__init__
def track_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    created.append(self)

with patch.object(Flask, '__init__', track_init), patch.object(Flask, 'run') as run:
    if {entrypoint!r} == 'script':
        namespace = runpy.run_path('app.py', run_name='__main__')
        run.assert_called_once()
        application = namespace['app']
    else:
        from wsgi import app as application
        run.assert_not_called()
assert len(created) == 1, len(created)
assert 'portal' in application.blueprints
client = application.test_client()
assert client.get('/').status_code == 302
assert client.get('/login', follow_redirects=True).status_code == 200
with application.app_context():
    from app import get_db
    assert get_db().execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert get_db().execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    from werkzeug.security import generate_password_hash
    get_db().execute('INSERT INTO usuarios(nome, login, senha_hash) VALUES (?, ?, ?)',
                     ('Teste', 'teste', generate_password_hash('test-only')))
    get_db().commit()
assert client.get('/login').status_code == 200
"""], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
