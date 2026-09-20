"""Operação local da v2: releases separadas, dados persistentes e confirmação."""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

REPOSITORY = 'https://github.com/Th14g0R/emprestimo.git'
BRANCH = 'release/v2'
LABEL = 'br.com.emprestimo.v2'


def run(*args, cwd=None, env=None, capture=False):
    return subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, timeout=600)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def copy_database(source, target):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src:
        src.execute('PRAGMA foreign_keys=ON')
        with closing(sqlite3.connect(target)) as dst:
            dst.execute('PRAGMA foreign_keys=ON')
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('A cópia do banco falhou na verificação de integridade.')


def copy_data(source_db, target):
    """A origem deve estar parada para manter comprovantes e banco no mesmo instante."""
    source_db, target = Path(source_db).resolve(), Path(target)
    if not source_db.is_file():
        raise ValueError('Banco de origem não encontrado.')
    if target.exists():
        raise ValueError('A pasta de destino da cópia deve ser nova.')
    proofs = source_db.parent / 'comprovantes'
    if proofs.is_symlink() or (proofs.exists() and any(p.is_symlink() for p in proofs.rglob('*'))):
        raise ValueError('Comprovantes contêm links simbólicos; confira os arquivos antes da cópia.')
    key = source_db.parent / '.secret_key'
    if key.is_symlink():
        raise ValueError('A chave de sessão é um link simbólico; confira a origem.')
    target.mkdir(parents=True, mode=0o700)
    copy_database(source_db, target / 'emprestimos.db')
    if proofs.is_dir():
        shutil.copytree(proofs, target / 'comprovantes')
    if key.is_file():
        shutil.copyfile(key, target / '.secret_key')
        (target / '.secret_key').chmod(0o600)


def has_financial_data(path):
    if not Path(path).is_file():
        return False
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('clientes', 'emprestimos', 'movimentacoes_emprestimo', 'cartoes_credito'):
            if table in tables and db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                return True
    return False


class Manager:
    def __init__(self, install_dir=None, state_dir=None, port=5002):
        self.install = Path(install_dir or Path.home() / 'Aplicativos/emprestimo-v2').expanduser().resolve()
        self.state = Path(state_dir or Path.home() / 'Library/Application Support/Emprestimo').expanduser().resolve()
        self.port = port
        if not 1024 <= port <= 65535:
            raise ValueError('Porta inválida.')
        if self.state == self.install or self.install in self.state.parents or self.state in self.install.parents:
            raise ValueError('Código e dados precisam ficar em diretórios separados.')
        self.data = self.state / 'data'
        self.current = self.install / 'current'
        self.plist = Path.home() / 'Library/LaunchAgents' / f'{LABEL}.plist'
        self.domain = f'gui/{os.getuid()}' if hasattr(os, 'getuid') else ''

    @contextmanager
    def locked(self):
        """Uma operação por instalação; o lock é liberado pelo SO se o processo cair."""
        if sys.platform != 'darwin':
            raise ValueError('Este gerenciador de serviços é exclusivo do macOS.')
        import fcntl
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state.chmod(0o700)
        settings = self.state / 'gerenciador.json'
        expected = {'install_dir': str(self.install), 'state_dir': str(self.state), 'port': self.port}
        if settings.exists() and json.loads(settings.read_text()) != expected:
            raise ValueError('Esta instalação usa outros caminhos/porta. Consulte gerenciador.json e informe os mesmos parâmetros.')
        with (self.state / 'operacao.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Já existe outro gerenciador realizando uma operação.') from None
            if not settings.exists():
                settings.write_text(json.dumps(expected, indent=2))
            yield

    def environment(self, data=None):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('EMPRESTIMO_') and k not in {'SECRET_KEY', 'PYTHONPATH', 'PYTHONHOME'}}
        root = Path(data or self.data)
        env.update(EMPRESTIMO_DATA_DIR=str(root), EMPRESTIMO_DATABASE=str(root / 'emprestimos.db'),
                   EMPRESTIMO_SECRET_KEY_FILE=str(root / '.secret_key'),
                   EMPRESTIMO_LOG_DIR=str(self.state / 'logs' if data is None else root / 'logs'),
                   EMPRESTIMO_TRUSTED_HOSTS='localhost,127.0.0.1', EMPRESTIMO_HTTPS='0',
                   EMPRESTIMO_BEHIND_PROXY='0')
        return env

    def installed(self):
        if not self.current.is_symlink():
            if self.current.exists():
                raise ValueError('current já existe e não é um link gerenciado. Não será substituído.')
            return None
        release = self.current.resolve()
        if release.parent != self.install / 'releases' or not (release / 'app.py').is_file():
            raise ValueError('O link current não aponta para uma versão gerenciada válida.')
        return release

    def remote_commit(self):
        result = run('git', 'ls-remote', REPOSITORY, f'refs/heads/{BRANCH}', capture=True).stdout.strip()
        parts = result.split()
        if len(parts) != 2 or not re.fullmatch('[0-9a-f]{40}', parts[0]):
            raise ValueError('Não foi possível identificar a versão publicada.')
        return parts[0]

    def commit(self, release):
        return run('git', 'rev-parse', 'HEAD', cwd=release, capture=True).stdout.strip()

    def status(self, check_remote=False):
        release = self.installed()
        print(f'Código: {self.install}\nDados: {self.data}\nBackups: {self.state / "backups"}')
        print(f'Acesso: http://127.0.0.1:{self.port}')
        local = self.commit(release) if release else None
        print(f'Commit instalado: {local or "ainda não instalado"}')
        if check_remote:
            remote = self.remote_commit()
            print(f'Commit disponível em {BRANCH}: {remote}')
            print('Já está atualizado.' if local == remote else 'Há uma versão disponível para instalação.')
        return local

    def service_loaded(self):
        result = subprocess.run(['launchctl', 'print', f'{self.domain}/{LABEL}'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return result.returncode == 0

    def guard_plist(self):
        if self.plist.exists():
            with self.plist.open('rb') as stream:
                config = plistlib.load(stream)
            if config.get('WorkingDirectory') != str(self.current):
                raise ValueError('Já existe um LaunchAgent de outra instalação. Pare e guarde o plist antigo antes de usar este gerenciador.')
        elif self.service_loaded():
            raise ValueError('Há um serviço com este nome sem o plist esperado. Confira a instalação anterior antes de continuar.')

    def stop(self):
        self.guard_plist()
        if self.service_loaded():
            details = run('launchctl', 'print', f'{self.domain}/{LABEL}', capture=True).stdout
            match = re.search(r'^\s*pid = (\d+)\s*$', details, re.MULTILINE)
            pid = int(match.group(1)) if match else None
            run('launchctl', 'bootout', f'{self.domain}/{LABEL}')
            if pid:
                for _ in range(100):
                    try:
                        os.kill(pid, 0)  # Apenas consulta; não encerra processos.
                    except ProcessLookupError:
                        break
                    time.sleep(0.1)
                else:
                    raise ValueError('O processo anterior ainda não encerrou. Aguarde antes de copiar dados ou reiniciar.')
        print('Serviço descarregado. Não mantenha outra instância manual usando os mesmos dados.')

    def port_free(self):
        with socket.socket() as sock:
            # Igual ao listener do Waitress: TIME_WAIT após uma parada normal
            # não deve ser confundido com outro servidor escutando nesta porta.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', self.port))
            except OSError:
                raise ValueError(f'A porta {self.port} está ocupada. Não será encerrado nenhum outro processo.') from None

    def write_plist(self):
        self.guard_plist()
        self.plist.parent.mkdir(parents=True, exist_ok=True)
        config = dict(Label=LABEL, ProgramArguments=[str(self.current / '.venv/bin/python'),
                      str(self.current / 'producao.py'), '--port', str(self.port)],
                      WorkingDirectory=str(self.current), RunAtLoad=True, KeepAlive=True,
                      ThrottleInterval=10, Umask=0o077,
                      EnvironmentVariables={k: v for k, v in self.environment().items() if k.startswith('EMPRESTIMO_')})
        with self.plist.open('wb') as stream:
            plistlib.dump(config, stream)

    def start(self):
        release = self.installed()
        if release is None:
            raise ValueError('Instale primeiro uma versão.')
        self.guard_plist()
        if self.service_loaded():
            print('O serviço já está carregado. Use Parar antes de reiniciar.')
            return
        self.port_free()
        check = run(release / '.venv/bin/python', release / 'producao.py', '--check',
                    cwd=release, env=self.environment(), capture=True).stdout.strip()
        if not check.startswith('Produção validada: '):
            raise ValueError('O runner não informou a versão validada.')
        expected_version = check.removeprefix('Produção validada: ')
        print(check)
        self.write_plist()
        run('launchctl', 'bootstrap', self.domain, self.plist)
        for _ in range(30):
            try:
                with urlopen(f'http://127.0.0.1:{self.port}/health', timeout=2) as response:
                    health = json.load(response)
                if health.get('status') == 'ok' and health.get('version') == expected_version:
                    print(f'Em execução: {health.get("version")} — http://127.0.0.1:{self.port}')
                    return
            except (OSError, URLError, ValueError):
                pass
            time.sleep(1)
        self.stop()
        raise ValueError(f'O serviço não respondeu. Consulte {self.state / "logs/aplicacao.log"}. O serviço foi parado.')

    def point_to(self, release):
        self.installed()  # Valida antes de substituir qualquer entrada.
        temporary = self.install / 'current.next'
        if temporary.exists() or temporary.is_symlink():
            raise ValueError('current.next já existe; confira uma possível operação interrompida.')
        temporary.symlink_to(release, target_is_directory=True)
        os.replace(temporary, self.current)

    def backup(self, reason):
        folder = self.state / 'backups' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + reason)
        folder.mkdir(parents=True, mode=0o700)
        db = self.data / 'emprestimos.db'
        if db.exists():
            copy_data(db, folder / 'data')
        release = self.installed()
        manifest = {'motivo': reason, 'release': str(release) if release else None,
                    'commit': self.commit(release) if release else None,
                    'banco_sha256': sha256(folder / 'data/emprestimos.db') if db.exists() else None}
        if release:
            run('git', 'archive', '--format=zip', f'--output={folder / "codigo.zip"}', 'HEAD', cwd=release)
        (folder / 'manifesto.json').write_text(json.dumps(manifest, indent=2))
        print(f'Backup preservado: {folder}')
        return folder

    def prepare(self, commit):
        destination = self.install / 'releases' / commit
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            run('git', 'clone', '--no-checkout', '--single-branch', '--branch', BRANCH, REPOSITORY, destination)
            run('git', 'checkout', '--detach', commit, cwd=destination)
        if self.commit(destination) != commit:
            raise ValueError('A pasta da versão preparada contém outro commit.')
        if run('git', 'status', '--porcelain', cwd=destination, capture=True).stdout.strip():
            raise ValueError('A versão preparada tem alterações locais; não será reutilizada.')
        if not (destination / 'producao.py').exists():
            raise ValueError('A versão publicada ainda não inclui este gerenciador de produção.')
        python = destination / '.venv/bin/python'
        if not python.exists():
            run(sys.executable, '-m', 'venv', destination / '.venv')
        run(python, '-m', 'pip', 'install', '-r', destination / 'requirements.lock')
        with tempfile.TemporaryDirectory(prefix='emprestimo-preflight-') as tmp:
            run(python, destination / 'producao.py', '--check', cwd=destination, env=self.environment(tmp))
        if (self.data / 'emprestimos.db').exists():
            run(python, destination / 'scripts/verificar_banco.py', self.data / 'emprestimos.db',
                cwd=destination, env=self.environment())
        print(f'Versão preparada e validada: {commit}. Ainda não foi ativada.')
        return destination

    def confirm(self, message, word):
        print(message)
        if input(f'Digite {word} para confirmar (Enter cancela): ').strip() != word:
            print('Cancelado. Nenhum dado de produção foi substituído.')
            return False
        return True

    def update(self):
        self.guard_plist()
        old = self.installed()
        remote = self.remote_commit()
        if old and self.commit(old) == remote:
            print('A instalação já está no commit publicado.')
            return
        if old and run('git', 'status', '--porcelain', cwd=old, capture=True).stdout.strip():
            raise ValueError('A versão instalada tem alterações locais. Guarde-as antes de atualizar.')
        candidate = self.prepare(remote)
        if not self.confirm(f'Ativar {remote[:12]}? O serviço será parado e haverá backup antes da troca.\n'
                            'Pare também eventuais instâncias manuais que usem estes dados.', 'ATUALIZAR' if old else 'INSTALAR'):
            return
        self.stop()
        backup = self.backup('antes-atualizacao' if old else 'antes-instalacao')
        self.point_to(candidate)
        try:
            self.start()
        except Exception:
            print(f'Ativação não concluída. O backup está em {backup}.\n'
                  'Não volte apenas o código: restaure código e dados juntos. Use o guia de recuperação.')
            raise

    def import_v1(self, source):
        release = self.installed()
        if release is None:
            raise ValueError('Instale a v2 antes de importar a base v1.')
        if has_financial_data(self.data / 'emprestimos.db'):
            raise ValueError('A v2 já contém clientes ou movimentos. A importação inicial não sobrescreve uma base em uso.')
        source = Path(source).expanduser().resolve()
        if source == (self.data / 'emprestimos.db').resolve():
            raise ValueError('A origem não pode ser o banco de destino.')
        print('Use uma cópia da pasta data da v1 obtida com o sistema de origem parado.\n'
              'Comprovantes e .secret_key devem estar ao lado do banco. A origem não será alterada.')
        if not self.confirm('Confirma que a origem é uma cópia estável, sem gravações em andamento?', 'ORIGEM PARADA'):
            return
        with tempfile.TemporaryDirectory(prefix='importacao-', dir=self.state) as tmp:
            stage = Path(tmp) / 'data'
            copy_data(source, stage)
            run(release / '.venv/bin/python', release / 'scripts/verificar_banco.py', stage / 'emprestimos.db',
                cwd=release, env=self.environment())
            if not self.confirm('Revise os alertas acima. Importar esta base e usar seus usuários/senhas?\n'
                                'O estado vazio da v2 será guardado em backup. Pare qualquer instância manual da v2.', 'IMPORTAR'):
                return
            self.stop()
            # Revalida após parar, impedindo substituir cadastros feitos durante a prévia.
            if has_financial_data(self.data / 'emprestimos.db'):
                raise ValueError('A v2 recebeu dados durante a prévia. Importação cancelada.')
            backup = self.backup('antes-importacao-v1')
            if self.data.exists():
                self.data.rename(backup / 'data-anterior-completa')
            stage.rename(self.data)
            try:
                self.start()
            except Exception:
                print(f'Não opere até corrigir a inicialização. Origem v1 preservada; backup v2 em {backup}.')
                raise
        print('Base importada. Confira clientes, saldos, últimos recebimentos e comprovantes antes de operar.')

    def make_backup(self):
        self.guard_plist()
        running = self.service_loaded()
        if not self.confirm('O serviço será parado para copiar banco, comprovantes e chave.\n'
                            'Pare também eventuais instâncias manuais.', 'BACKUP'):
            return
        self.stop()
        self.backup('manual')
        if running:
            self.start()

    def menu(self):
        actions = {'1': self.update, '2': lambda: self.status(True), '3': self.start,
                   '4': self.stop, '5': self.make_backup,
                   '6': lambda: self.import_v1(input('Caminho completo do banco v1 (.db): ').strip().strip('"\'')),
                   '7': self.status}
        while True:
            print('\nEMPRÉSTIMO V2 — PRODUÇÃO NO MAC\n'
                  '1 Instalar / atualizar (com confirmação)\n2 Consultar atualizações no GitHub\n'
                  '3 Iniciar\n4 Parar\n5 Fazer backup\n6 Importar base v1 em instalação vazia\n'
                  '7 Ver caminhos e versão\n0 Sair')
            choice = input('Opção: ').strip()
            if choice == '0':
                return
            if choice not in actions:
                print('Opção inválida.')
                continue
            try:
                with self.locked():
                    actions[choice]()
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                print(f'OPERAÇÃO NÃO CONCLUÍDA: {exc}')
                if getattr(exc, 'stderr', None):
                    print(exc.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=['menu', 'status', 'verificar', 'atualizar', 'iniciar', 'parar', 'backup', 'importar'], default='menu')
    parser.add_argument('--install-dir')
    parser.add_argument('--state-dir')
    parser.add_argument('--port', type=int, default=5002)
    parser.add_argument('--banco', type=Path)
    args = parser.parse_args()
    manager = Manager(args.install_dir, args.state_dir, args.port)
    if args.action == 'menu':
        manager.menu()
        return
    actions = {'status': manager.status, 'verificar': lambda: manager.status(True), 'atualizar': manager.update,
               'iniciar': manager.start, 'parar': manager.stop, 'backup': manager.make_backup}
    with manager.locked():
        if args.action == 'importar':
            if args.banco is None:
                parser.error('Informe --banco com o caminho do banco v1.')
            manager.import_v1(args.banco)
        else:
            actions[args.action]()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'OPERAÇÃO NÃO CONCLUÍDA: {exc}', file=sys.stderr)
        sys.exit(1)
