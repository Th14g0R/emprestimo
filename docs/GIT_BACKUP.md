# Backup do código no GitHub

Repositório oficial:

```text
https://github.com/Th14g0R/emprestimo
```

## O que deve ir para o Git

- `app.py`;
- templates;
- CSS/JS estáticos;
- scripts de instalação/manutenção;
- documentação `.md`;
- `requirements.txt`;
- `.gitignore`;
- `.env.example`.

## O que NÃO deve ir para o Git

- `data/emprestimos.db`;
- `data/.secret_key`;
- arquivos `-wal` e `-shm`;
- `.venv`;
- logs;
- backups do banco;
- credenciais ou tokens.

O repositório é de código-fonte. O backup dos dados financeiros deve ser feito separadamente e protegido.

## Substituindo a versão antiga do `main`

A forma mais segura é clonar o repositório atual para uma pasta temporária, remover os arquivos da árvore de trabalho e copiar a versão nova por cima. Isso cria um commit normal que remove o Node/Docker da versão atual sem precisar de `push --force`.

Consulte também `scripts/Publicar-GitHub.ps1`.

## Histórico Git

Remover os arquivos em um novo commit faz com que eles deixem de existir na versão atual da branch `main`, mas commits antigos continuam fazendo parte do histórico Git. Isso é normal.
