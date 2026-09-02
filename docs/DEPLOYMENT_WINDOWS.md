# Instalação, atualização e desinstalação no Windows

## Arquivo principal

Execute como administrador:

```text
Gerenciar-Emprestimo.bat
```

O BAT executa `scripts/Gerenciar-Emprestimo.ps1` a partir de uma cópia temporária para que o próprio gerenciador possa atualizar ou remover a pasta instalada com segurança.

## Instalação

O gerenciador:

1. verifica privilégios de administrador;
2. verifica Git;
3. verifica Python compatível;
4. verifica/recupera pip por `ensurepip` se necessário;
5. oferece instalar Git/Python via WinGet quando ausentes;
6. clona `https://github.com/Th14g0R/emprestimo.git`;
7. cria `.venv`;
8. instala `requirements.txt`;
9. valida a importação do Flask app;
10. baixa WinSW 2.12.0 e valida o SHA-256 do binário;
11. cria o serviço Windows `Emprestimo`;
12. inicia o serviço automaticamente;
13. cria atalho no Desktop Público;
14. quando escolhido acesso em rede, cria uma regra de firewall para a porta informada;
15. registra o caminho de instalação em `HKLM\SOFTWARE\Emprestimo`.

Pasta padrão:

```text
C:\ProgramData\Emprestimo
```

## Servidor WSGI

Produção usa Waitress, não o servidor `app.run()` do Flask.

O serviço executa:

```text
waitress-serve --listen=<host>:<porta> app:app
```

## Atualização

A opção `Atualizar` descobre o caminho pelo Registry, faz `git fetch`, compara `HEAD` com `origin/main` e somente aplica atualização quando há commit diferente.

Antes de alterar os arquivos:

- para o serviço;
- executa checkpoint SQLite quando possível;
- cria backup de `data`;
- aplica `git reset --hard origin/main`;
- remove arquivos antigos não versionados, preservando os itens ignorados pelo `.gitignore`;
- atualiza dependências do virtualenv;
- valida o app;
- inicia o serviço novamente.

Não edite código diretamente na pasta instalada. Faça alterações no repositório de desenvolvimento, faça commit/push e use `Atualizar` no computador servidor.

## Desinstalação

A opção `Desinstalar`:

- para e remove o serviço `Emprestimo`;
- remove regra de firewall criada pelo instalador;
- remove atalho;
- pergunta se o banco deve ser preservado;
- se sim, copia `data` para `C:\ProgramData\EmprestimoBackup\<data-hora>`;
- remove a pasta da aplicação;
- remove as informações de instalação do Registry.

Python e Git não são removidos, pois podem ser usados por outros programas.
