@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Sistema Emprestimo - Gerenciador

set "REPO_RAW=https://raw.githubusercontent.com/Th14g0R/emprestimo/main/scripts/Gerenciar-Emprestimo.ps1"
set "LOCAL_SCRIPT=%~dp0scripts\Gerenciar-Emprestimo.ps1"
set "BOOT_DIR=%TEMP%\EmprestimoBootstrap"
set "BOOT_SCRIPT=%BOOT_DIR%\Gerenciar-Emprestimo.ps1"
set "PYTHON_EXE="

if not exist "%BOOT_DIR%" mkdir "%BOOT_DIR%" >nul 2>&1

echo ============================================================
echo GERENCIADOR - SISTEMA EMPRESTIMO - V17
echo ============================================================
echo.

rem Detect Python BEFORE UAC elevation.
for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
    for /f "usebackq delims=" %%P in (`py -c "import sys; print(sys.executable)" 2^>nul`) do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
    )
)

if defined PYTHON_EXE (
    echo [OK] Python detectado antes da elevacao:
    echo      %PYTHON_EXE%
    echo.
) else (
    echo [!] Python nao foi encontrado.
    echo.

    where winget.exe >nul 2>&1
    if errorlevel 1 (
        echo ERRO: WinGet nao esta disponivel.
        echo Instale o App Installer da Microsoft Store e tente novamente.
        echo.
        pause
        exit /b 1
    )

    if defined EMPRESTIMO_PYTHON_RETRY (
        echo ERRO: Python continua indisponivel apos a tentativa de instalacao.
        echo.
        echo Abra um CMD novo e teste:
        echo   python --version
        echo.
        pause
        exit /b 1
    )

    set /p "RESP=Python e necessario. Deseja instala-lo agora? [S/n]: "
    if /I "%RESP%"=="N" exit /b 1
    if /I "%RESP%"=="NAO" exit /b 1

    echo.
    echo [+] Instalando Python 3.14 via WinGet...
    winget install --id Python.Python.3.14 -e --source winget --accept-package-agreements --accept-source-agreements

    echo.
    echo [+] Reiniciando o gerenciador para atualizar PATH e aliases...
    set "EMPRESTIMO_PYTHON_RETRY=1"
    start "" "%~f0"
    exit /b 0
)

rem Get the PowerShell manager.
if exist "%LOCAL_SCRIPT%" (
    echo [OK] Usando gerenciador local:
    echo      %LOCAL_SCRIPT%
    copy /Y "%LOCAL_SCRIPT%" "%BOOT_SCRIPT%" >nul
) else (
    echo [+] Baixando gerenciador atual do GitHub...
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
        echo.
        pause
        exit /b 1
    )
)

if not exist "%BOOT_SCRIPT%" (
    echo.
    echo ERRO: Gerenciador PowerShell nao encontrado.
    echo.
    pause
    exit /b 1
)

rem Pass the REAL interpreter path into the elevated PowerShell.
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%BOOT_SCRIPT%" -PythonExeHint "%PYTHON_EXE%"
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
