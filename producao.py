"""Waitress com logs limitados; usado pelo gerenciador macOS."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5002)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Escolha uma porta entre 1024 e 65535.')
    log_dir = Path(os.environ.get('EMPRESTIMO_LOG_DIR', Path(__file__).resolve().parent / 'logs'))
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / 'aplicacao.log', maxBytes=5 * 1024 * 1024,
                                  backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    from app import app, APP_VERSION
    if args.check:
        with app.test_client() as client:
            if client.get('/health').status_code != 200:
                raise RuntimeError('Falha na validação do banco e da aplicação.')
        print(f'Produção validada: {APP_VERSION}')
        return
    from waitress import serve
    logging.info('Iniciando versão %s na porta %s', APP_VERSION, args.port)
    try:
        serve(app, host='127.0.0.1', port=args.port, threads=4)
    except Exception:
        logging.exception('Falha no servidor')
        raise


if __name__ == '__main__':
    main()
