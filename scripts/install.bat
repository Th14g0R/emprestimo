@echo off
REM ============================================================================
REM  INSTALADOR - Sistema de Controle de Emprestimos e Cartao de Credito
REM  ============================================================================
REM  Este script realiza a instalacao completa do sistema
REM  Verifica dependencias, instala o necessario e configura como servico
REM  ============================================================================

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Instalador - Sistema de Emprestimos

REM ============================================================================
REM Verificar privilegios de administrador
REM ============================================================================
echo.
echo [*] Verificando privilegios de administrador...

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Este script requer privilegios de administrador!
    echo.
    echo Solicitando privilegios...
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d %CD% ^& %~s0' -Verb RunAs"
    pause
    exit /b
)

echo [OK] Privilegios de administrador confirmados
echo.

REM ============================================================================
REM Definir variaveis
REM ============================================================================
set "INSTALL_DIR=%ProgramFiles%\SistemaEmprestimos"
set "APP_NAME=Sistema-Emprestimos"
set "SERVICE_NAME=SistemaEmprestimosBackend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"
set "REPO_URL=https://github.com/Th14g0R/emprestimo.git"

echo =====================================================================
echo  INSTALADOR - Sistema de Controle de Emprestimos
echo =====================================================================
echo.
echo Diretorio de instalacao: %INSTALL_DIR%
echo.

REM ============================================================================
REM Verificar e instalar Node.js
REM ============================================================================
echo [1/6] Verificando Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Node.js nao encontrado. Instalando...
    echo [!] Baixando de: https://nodejs.org/dist/v18.18.0/node-v18.18.0-x64.msi
    
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://nodejs.org/dist/v18.18.0/node-v18.18.0-x64.msi' -OutFile '%temp%\nodejs.msi'" 2>nul
    
    if exist "%temp%\nodejs.msi" (
        echo [!] Instalando Node.js...
        msiexec /i "%temp%\nodejs.msi" /quiet /norestart
        timeout /t 5 /nobreak >nul
        del "%temp%\nodejs.msi" 2>nul
        
        REM Recarrega PATH
        for /f "delims=" %%i in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('Path', 'Machine')"') do set "PATH=%%i"
        
        echo [OK] Node.js instalado com sucesso
    ) else (
        echo [ERRO] Falha ao baixar Node.js
        echo [!] Tente novamente ou instale manualmente de:
        echo [!] https://nodejs.org/
        goto error_exit
    )
) else (
    echo [OK] Node.js ja esta instalado
    for /f "tokens=*" %%i in ('node --version') do echo    Versao: %%i
)
echo.

REM ============================================================================
REM Verificar e instalar Git
REM ============================================================================
echo [2/6] Verificando Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Git nao encontrado. Instalando...
    echo [!] Baixando de: https://github.com/git-for-windows/git/releases/download/v2.42.0.windows.1/Git-2.42.0-64-bit.exe
    
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.42.0.windows.1/Git-2.42.0-64-bit.exe' -OutFile '%temp%\GitInstaller.exe'" 2>nul
    
    if exist "%temp%\GitInstaller.exe" (
        echo [!] Instalando Git...
        "%temp%\GitInstaller.exe" /VERYSILENT /NORESTART
        timeout /t 5 /nobreak >nul
        del "%temp%\GitInstaller.exe" 2>nul
        
        REM Recarrega PATH
        for /f "delims=" %%i in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('Path', 'Machine')"') do set "PATH=%%i"
        
        echo [OK] Git instalado com sucesso
        timeout /t 2 /nobreak >nul
    ) else (
        echo [ERRO] Falha ao baixar Git
        echo [!] Tente novamente ou instale manualmente de:
        echo [!] https://git-scm.com/download/win
        goto error_exit
    )
) else (
    echo [OK] Git ja esta instalado
    for /f "tokens=*" %%i in ('git --version') do echo    Versao: %%i
)
echo.

REM ============================================================================
REM Verificar e instalar Docker
REM ============================================================================
echo [3/6] Verificando Docker...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Docker nao encontrado. Instalando Docker Desktop...
    echo [!] Baixando de: https://desktop.docker.com/win/main/amd64/
    
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker%%20Desktop%%20Installer.exe' -OutFile '%temp%\DockerInstaller.exe'" 2>nul
    
    if exist "%temp%\DockerInstaller.exe" (
        echo [!] Instalando Docker Desktop (pode levar alguns minutos)...
        "%temp%\DockerInstaller.exe" install --quiet
        timeout /t 10 /nobreak >nul
        del "%temp%\DockerInstaller.exe" 2>nul
        echo [OK] Docker Desktop instalado
    ) else (
        echo [AVISO] Falha ao baixar Docker
        echo [!] Continuando sem Docker por enquanto...
    )
) else (
    echo [OK] Docker ja esta instalado
    for /f "tokens=*" %%i in ('docker --version') do echo    Versao: %%i
)
echo.

REM ============================================================================
REM Criar diretorio de instalacao
REM ============================================================================
echo [4/6] Preparando diretorio de instalacao...
if exist "%INSTALL_DIR%" (
    echo [!] Diretorio ja existe
) else (
    mkdir "%INSTALL_DIR%"
    echo [OK] Diretorio criado: %INSTALL_DIR%
)
echo.

REM ============================================================================
REM Clonar repositorio do Git
REM ============================================================================
echo [5/6] Clonando repositorio...

REM Verifica novamente se Git foi instalado com sucesso
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Git nao esta disponivel
    echo [!] Tente reiniciar o computador e executar novamente
    goto error_exit
)

cd /d "%INSTALL_DIR%"

if exist "%INSTALL_DIR%\.git" (
    echo [!] Repositorio ja clonado. Atualizando...
    git pull origin main 2>nul
) else (
    echo [!] Clonando repositorio de %REPO_URL%
    git clone "%REPO_URL%" . 2>nul
    
    if !errorlevel! neq 0 (
        echo [ERRO] Falha ao clonar repositorio
        echo [!] Verifique sua conexao com a internet
        echo [!] URL: %REPO_URL%
        goto error_exit
    )
)

echo [OK] Repositorio pronto
echo.

REM ============================================================================
REM Instalar dependencias
REM ============================================================================
echo [6/6] Instalando dependencias npm...
cd /d "%INSTALL_DIR%"

if not exist "package.json" (
    echo [ERRO] package.json nao encontrado
    goto error_exit
)

echo [!] Executando npm install...
call npm install --legacy-peer-deps 2>nul

if %errorlevel% equ 0 (
    echo [OK] Dependencias instaladas com sucesso
) else (
    echo [AVISO] Houve erros ao instalar dependencias
)
echo.

REM ============================================================================
REM Criar arquivo .env
REM ============================================================================
echo Criando arquivo .env...
if not exist "%INSTALL_DIR%\.env" (
    (
        echo DATABASE_URL=postgresql://emprestimos:senha123@localhost:5432/emprestimos_db
        echo BACKEND_PORT=3001
        echo FRONTEND_PORT=3000
        echo JWT_SECRET=sua_chave_secreta_aqui_mudar_em_producao
        echo NEXT_PUBLIC_API_URL=http://localhost:3001
    ) > "%INSTALL_DIR%\.env"
    echo [OK] Arquivo .env criado
) else (
    echo [!] Arquivo .env ja existe
)
echo.

REM ============================================================================
REM Sucesso
REM ============================================================================
echo =====================================================================
echo [OK] INSTALACAO CONCLUIDA COM SUCESSO!
echo =====================================================================
echo.
echo Proximo passos:
echo  1. Acesse: http://localhost:3000
echo  2. Backend API: http://localhost:3001/api
echo  3. Admin BD: http://localhost:8080
echo.
timeout /t 5 /nobreak >nul
goto end

:error_exit
echo.
echo =====================================================================
echo [ERRO] FALHA NA INSTALACAO
echo =====================================================================
echo.
echo Verifique o log de erros e tente novamente.
echo Se o problema persistir, visite:
echo  https://github.com/Th14g0R/emprestimo/issues
echo.
timeout /t 10 /nobreak >nul
goto end

:end
echo.
pause
endlocal
