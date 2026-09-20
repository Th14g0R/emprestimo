# Controle de Empréstimos — versão 2

Versão **2.0.0+build.1**, mantida na branch **release/v2**.
Sistema de uso real para empréstimos pessoais, recebimentos e cartão de crédito,
com interface administrativa e portal do cliente. Não inclui dados demonstrativos
nem usuário ou senha padrão.

## Funcionalidades

- Clientes, contratos independentes, contas bancárias e snapshots históricos.
- Juros mensais, abatimentos e quitação com valores em centavos inteiros.
- Atraso proporcional: juro mensal original × dias de atraso ÷ 30.
- Reagendamento e recebimentos agrupados com prévia detalhada, sem capitalizar
  atraso nos títulos futuros.
- Cartões, dashboard, relatórios, comprovantes privados e auditoria.
- CSRF, senhas com hash, limites de tentativas e transações financeiras atômicas.

## Instalação no Windows

Baixe a branch `release/v2` e execute **Gerenciar-Emprestimo.bat**. O gerenciador
instala o serviço **Emprestimo**, com Waitress e SQLite, e acompanha somente essa
branch. Para atualizar uma instalação anterior, use o gerenciador desta versão.

Veja [instalação e atualização](docs/DEPLOYMENT_WINDOWS.md), incluindo backup,
restauração e configuração de rede. O fluxo de serviço requer Windows; os testes
Python também podem ser executados em outros sistemas.

Para executar manualmente, em uma pasta de instalação:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 --threads=4 wsgi:application
```

Abra `http://127.0.0.1:5000` para criar o primeiro administrador. Faça essa
configuração localmente antes de disponibilizar o acesso a outros usuários.

## Dados e atualização

O padrão é `data/emprestimos.db`; comprovantes ficam em `data/comprovantes` e a
chave da sessão em `data/.secret_key`. Migrações são incrementais. Banco, chave,
comprovantes, backups e ambientes Python não fazem parte da publicação.

Antes de restaurar um banco antigo, valide uma cópia:

```bat
.venv\Scripts\python.exe scripts\verificar_banco.py C:\backup\emprestimos.db
```

Veja [compatibilidade e juros de atraso](docs/JUROS_ATRASO_E_RESTAURACAO.md).
O arquivo `.env.example` documenta variáveis de ambiente; a aplicação não carrega
arquivos `.env` automaticamente.

## Desenvolvimento e validação

Stack: Python 3.10+, Flask, SQLite, Jinja2, HTML/CSS, Pillow e Waitress.
`requirements.txt` define intervalos compatíveis; `requirements.lock` fixa as
versões validadas neste build.

```sh
python -m pip install -r requirements.lock
python -m unittest discover -s tests -v
python teste_local.py
```

O servidor isolado usa `data/local-test` e porta 5001, sem inserir exemplos.
Para desenvolvimento no banco configurado normalmente, use `python app.py`.

- [Changelog](CHANGELOG.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Regras financeiras](docs/BUSINESS_RULES.md)
- [Espaço e manutenção](docs/RECURSOS_E_MANUTENCAO.md)
- [Testes locais](docs/TESTE_LOCAL.md)
