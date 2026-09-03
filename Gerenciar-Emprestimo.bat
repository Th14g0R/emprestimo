@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sistema Emprestimo - Gerenciador

set "REPO_RAW=https://raw.githubusercontent.com/Th14g0R/emprestimo/main/scripts/Gerenciar-Emprestimo.ps1"
set "LOCAL_SCRIPT=%~dp0scripts\Gerenciar-Emprestimo.ps1"
set "BOOT_DIR=%TEMP%\EmprestimoBootstrap"
set "BOOT_SCRIPT=%BOOT_DIR%\Gerenciar-Emprestimo.ps1"

if not exist "%BOOT_DIR%" mkdir "%BOOT_DIR%" >nul 2>&1

echo ============================================================
echo GERENCIADOR - SISTEMA EMPRESTIMO
echo ============================================================
echo.
echo Este arquivo pode ser executado sozinho.
echo.
echo Na instalacao ele ira:
echo   - permitir escolher a pasta graficamente;
echo   - verificar Git, Python e pip;
echo   - oferecer instalacao das dependencias ausentes;
echo   - baixar o projeto do GitHub;
echo   - criar o ambiente virtual;
echo   - instalar requirements.txt;
echo   - criar e iniciar o servico Windows Emprestimo;
echo   - criar o atalho de acesso.
echo.

rem Em uma pasta de desenvolvimento/clone, prefere o script local.
rem Assim uma alteracao ainda nao publicada pode ser testada antes do push.
if exist "%LOCAL_SCRIPT%" (
    echo [OK] Usando gerenciador local:
    echo      %LOCAL_SCRIPT%
    copy /Y "%LOCAL_SCRIPT%" "%BOOT_SCRIPT%" >nul
    goto :RUN
)

echo [+] Gerenciador local nao encontrado.
echo [+] Baixando o gerenciador atual do GitHub...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$ProgressPreference='SilentlyContinue';" ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
  "New-Item -ItemType Directory -Path '%BOOT_DIR%' -Force | Out-Null;" ^
  "Invoke-WebRequest -Uri '%REPO_RAW%' -OutFile '%BOOT_SCRIPT%' -UseBasicParsing"

if errorlevel 1 (
    echo.
    echo ERRO: Nao foi possivel baixar o gerenciador do GitHub.
    echo Verifique a conexao com a Internet.
    echo.
    pause
    exit /b 1
)

if not exist "%BOOT_SCRIPT%" (
    echo.
    echo ERRO: O arquivo do gerenciador nao foi baixado.
    echo.
    pause
    exit /b 1
)

echo [OK] Gerenciador baixado.
echo.

:RUN
rem -STA e usado para garantir compatibilidade com FolderBrowserDialog do Windows Forms.
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%BOOT_SCRIPT%"
set "RC=%ERRORLEVEL%"

echo.
echo ============================================================
if "%RC%"=="0" (
    echo GERENCIADOR FINALIZADO.
) else (
    echo GERENCIADOR FINALIZADO COM ERRO. CODIGO: %RC%
)
echo ============================================================
echo.
pause
exit /b %RC%
