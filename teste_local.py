"""Servidor local isolado: python teste_local.py [--port 5001]."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Teste local com banco separado dos dados reais.')
    parser.add_argument('--port', type=int, default=5001)
    args = parser.parse_args()
    local_data = Path(__file__).resolve().parent / 'data' / 'local-test'
    # Não reutiliza caminhos de produção herdados do terminal.
    os.environ['EMPRESTIMO_DATA_DIR'] = str(local_data)
    os.environ['EMPRESTIMO_DATABASE'] = str(local_data / 'emprestimos.db')
    os.environ['EMPRESTIMO_SECRET_KEY_FILE'] = str(local_data / '.secret_key')
    os.environ['EMPRESTIMO_HTTPS'] = '0'
    os.environ['EMPRESTIMO_BEHIND_PROXY'] = '0'
    os.environ['EMPRESTIMO_TRUSTED_HOSTS'] = 'localhost,127.0.0.1'
    from app import app, get_db, sync_receivable_titles
    with app.app_context():
        sync_receivable_titles(get_db())
    print(f'Teste local: http://127.0.0.1:{args.port}')
    print(f'Dados isolados: {local_data}')
    print('No primeiro acesso, crie seu administrador. Não há senha padrão.')
    app.run(host='127.0.0.1', port=args.port, debug=False)


if __name__ == '__main__':
    main()
