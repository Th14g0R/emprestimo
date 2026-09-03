# HOTFIX V5 — Detecção do Python após WinGet

## Problema

Em uma instalação nova, o WinGet instala o Python 3.14 corretamente, porém o
PowerShell que iniciou antes da instalação pode continuar sem localizar
`python.exe`.

A documentação atual do Python/Microsoft orienta normalmente fechar e reabrir o
terminal após a instalação. Para um instalador automático, isso interromperia o
fluxo.

## Solução

`Resolve-Python` não depende mais apenas do PATH.

A detecção agora tenta, nesta ordem:

1. `python.exe` disponível no PATH;
2. Python Launcher `py.exe`;
3. Registro oficial do CPython (`PythonCore`, conforme PEP 514);
4. `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`;
5. `%LOCALAPPDATA%\Python\pythoncore-*\python.exe`;
6. `%ProgramFiles%\Python*\python.exe`;
7. `%ProgramFiles(x86)%\Python*\python.exe`.

Depois de uma instalação pelo WinGet, o gerenciador repete a detecção por até
10 segundos, sem exigir reinício do terminal.

## Regra

O executável encontrado é validado executando Python e lendo
`sys.executable`/`sys.version_info`. Apenas Python >= 3.9 é aceito.
