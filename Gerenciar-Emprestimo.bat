@echo off
setlocal

set "SCRIPT=%~dp0scripts\Gerenciar-Emprestimo.ps1"

if not exist "%SCRIPT%" (
    echo ERRO: Nao foi encontrado:
    echo %SCRIPT%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo O gerenciador terminou com erro. Codigo: %RC%
    pause
)

exit /b %RC%
