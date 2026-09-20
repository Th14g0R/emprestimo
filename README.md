# Controle de Empréstimos — versão 2

Versão **2.1.0+build.2**, mantida na branch **release/v2**.
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

## Instalação: escolha seu sistema

| Sistema | Guia completo | Como executar |
| --- | --- | --- |
| Windows | [Instalar no Windows](docs/DEPLOYMENT_WINDOWS.md) | Gerenciador `.bat` ou Waitress manual; serviço Windows |
| macOS | [Produção no Mac e gerenciador](docs/PRODUCAO_MACOS.md) | Menu `.command`: instalar, importar v1, backup e atualizar |
| Linux | [Instalar no Linux](docs/DEPLOYMENT_LINUX.md) | Terminal; serviço systemd opcional |

O [guia geral](docs/INSTALACAO.md) explica dados, backup, atualização, restauração
e acesso pela rede. Todos os sistemas usam o mesmo código com Waitress e SQLite.
O gerenciador `.bat` é exclusivo do Windows.

### Instalação guiada no Mac

Baixe **Code → Download ZIP** da branch `release/v2`, extraia e execute
`bash Gerenciar-Emprestimo.command` no Terminal dessa pasta. O menu prepara a
instalação fora do VS Code, em diretório próprio, e pede confirmação antes de
ativar ou importar a base v1. O endereço padrão é **http://127.0.0.1:5002**.
Veja o [passo a passo completo](docs/PRODUCAO_MACOS.md).

### Alternativa manual no macOS/Linux

Com Git e Python 3.10+ instalados, em uma pasta onde deseja guardar o sistema:

```sh
git clone --branch release/v2 --single-branch https://github.com/Th14g0R/emprestimo.git emprestimo-v2
cd emprestimo-v2
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/waitress-serve --listen=127.0.0.1:5000 --threads=4 wsgi:application
```

No Mac, se o Python instalado responde por `python3.14`, use esse comando no
lugar de `python3`. Abra **http://127.0.0.1:5000** no mesmo computador e crie o
administrador. Mantenha o Terminal aberto; Control + C para parar. Para executar
sem Terminal, siga a configuração automática do guia do seu sistema.

### Início no Windows

Baixe a branch `release/v2` e execute **Gerenciar-Emprestimo.bat**. Ele instala o
serviço **Emprestimo** e acompanha essa branch. Para atualizar uma instalação
anterior, use o gerenciador desta versão. O [guia Windows](docs/DEPLOYMENT_WINDOWS.md)
também explica a instalação manual e os pré-requisitos.

## Dados e atualização

O padrão é `data/emprestimos.db`; comprovantes ficam em `data/comprovantes` e a
chave da sessão em `data/.secret_key`. Migrações são incrementais. Banco, chave,
comprovantes, backups e ambientes Python não fazem parte da publicação.

Antes de restaurar um banco antigo, valide uma cópia:

Windows:

```bat
.venv\Scripts\python.exe scripts\verificar_banco.py C:\backup\emprestimos.db
```

macOS/Linux:

```sh
.venv/bin/python scripts/verificar_banco.py /caminho/do/backup/emprestimos.db
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
