# Sistema de Controle de Empréstimos

Aplicação web monolítica para controle de empréstimos pessoais e cartão de crédito.

## Stack atual

- Python 3.9+
- Flask 3.1+
- SQLite local
- Jinja2 / HTML / CSS
- Waitress para execução como serviço no Windows
- openpyxl e ReportLab para relatórios

O projeto **não usa Node.js, Docker, PostgreSQL, Next.js ou NestJS**.

## Execução para desenvolvimento

```bat
cd C:\temp\site\emprestimo
python -m pip install -r requirements.txt
python app.py
```

Acesse `http://127.0.0.1:5000`.

## Produção no Windows

Use `Gerenciar-Emprestimo.bat`. O gerenciador pode:

1. instalar dependências necessárias;
2. clonar este repositório;
3. criar ambiente virtual;
4. instalar `requirements.txt`;
5. instalar o site como serviço Windows chamado **Emprestimo**;
6. atualizar a instalação comparando o commit local com `origin/main`;
7. desinstalar o serviço e os arquivos, com opção de preservar o banco.

Consulte [docs/DEPLOYMENT_WINDOWS.md](docs/DEPLOYMENT_WINDOWS.md).

## Dados locais

O SQLite fica em:

```text
data/emprestimos.db
```

Esse banco pode conter dados pessoais, financeiros, bancos e chaves PIX. **Ele não deve ser enviado ao GitHub.** O arquivo `.gitignore` bloqueia banco, WAL, SHM e `data/.secret_key`.

## Documentação para desenvolvedores e IAs

- [AGENTS.md](AGENTS.md) — contexto curto e regras obrigatórias para agentes de IA.
- [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) — escopo funcional.
- [docs/BUSINESS_RULES.md](docs/BUSINESS_RULES.md) — regras financeiras que não podem ser quebradas.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — arquitetura atual.
- [docs/DEPLOYMENT_WINDOWS.md](docs/DEPLOYMENT_WINDOWS.md) — instalação, atualização e desinstalação.
- [docs/GIT_BACKUP.md](docs/GIT_BACKUP.md) — publicação segura no GitHub.
- [docs/ROADMAP.md](docs/ROADMAP.md) — próximos passos.

## Regra de manutenção

Mudanças de schema SQLite devem ser retrocompatíveis e preservar dados existentes. Nunca recrie o banco automaticamente para fazer uma atualização.
