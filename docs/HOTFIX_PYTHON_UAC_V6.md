# HOTFIX V6 — Contexto do Python e UAC

## Causa

O Python funciona no CMD do usuário, mas pode não ser encontrado depois que o
PowerShell é elevado pelo UAC.

O código WinGet `-1978335189` equivale a `0x8A15002B`
(`APPINSTALLER_CLI_ERROR_UPDATE_NOT_APPLICABLE`), isto é, não há atualização
aplicável.

## Correção

O `.bat` agora:

1. detecta Python antes da elevação;
2. executa `python -c "import sys; print(sys.executable)"`;
3. usa `py` como segunda opção;
4. passa o caminho físico via `-PythonExeHint`;
5. o PS1 preserva esse caminho ao elevar para Administrador.

Se Python ainda não estiver instalado, o BAT usa WinGet e reinicia a si próprio
para carregar o novo ambiente.

O PS1 também:
- não trata 0x8A15002B como falha fatal;
- verifica se o pacote já existe antes de reinstalar;
- procura Python em todos os perfis locais como fallback.
