# Arquitetura

## Objetivo arquitetural

Manter o sistema simples o suficiente para ser instalado em um computador Windows sem servidor de banco, Docker ou runtime JavaScript.

## Componentes

```text
Navegador
   |
   v
Waitress (produção Windows)
   |
   v
Flask / Jinja2
   |
   v
sqlite3
   |
   v
data/emprestimos.db
```

Durante desenvolvimento, `python app.py` usa o servidor de desenvolvimento do Flask apenas em `127.0.0.1`.

## Estrutura

```text
app.py
requirements.txt
templates/
static/
data/                  # runtime, não versionado
scripts/               # instalação/manutenção/publicação
service/               # runtime gerado no destino, não versionado
logs/                  # runtime, não versionado
docs/
AGENTS.md
README.md
```

## Persistência

SQLite é acessado pelo módulo `sqlite3` da biblioteca padrão.

Toda conexão deve habilitar:

```sql
PRAGMA foreign_keys = ON;
```

O projeto utiliza WAL quando configurado pela aplicação. O banco, `-wal` e `-shm` são runtime e não devem entrar no Git.

## Transações

Operações que alteram empréstimo e movimento correspondente devem ser atômicas. Em caso de falha, executar rollback e não deixar o saldo divergente do histórico.

## Evolução de schema

Como a aplicação é distribuída com SQLite local, atualizações precisam executar evolução incremental do schema.

Nunca substituir `emprestimos.db` por um banco vazio durante uma atualização.

## Produção Windows

O instalador cria um virtualenv local e usa Waitress, que suporta Windows nativamente.

O processo é encapsulado por WinSW no serviço:

```text
Emprestimo
```

O serviço executa com conta `LocalService` sempre que possível e possui permissão de escrita apenas nas áreas de runtime necessárias (`data` e `logs`).
