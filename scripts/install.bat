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
    powershell -Command "Start-Process cmd -ArgumentList '/c %~s0' -Verb RunAs" >nul 2>&1
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
set "SERVICE_DISPLAY_NAME=Sistema de Emprestimos - Backend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"
set "FRONTEND_DISPLAY_NAME=Sistema de Emprestimos - Frontend"
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
    
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue'; ^
        echo 'Baixando Node.js...'; ^
        Invoke-WebRequest -Uri 'https://nodejs.org/dist/v18.18.0/node-v18.18.0-x64.msi' -OutFile '%temp%\nodejs.msi'; ^
        echo 'Instalando...'; ^
        Start-Process msiexec -ArgumentList '/i %temp%\nodejs.msi /quiet /norestart' -Wait; ^
        Remove-Item '%temp%\nodejs.msi' -Force" 2>nul
    
    if !errorlevel! equ 0 (
        echo [OK] Node.js instalado com sucesso
        set "PATH=%PATH%;C:\Program Files\nodejs"
    ) else (
        echo [ERRO] Falha ao instalar Node.js
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
    
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue'; ^
        echo 'Baixando Git...'; ^
        Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.42.0.windows.1/Git-2.42.0-64-bit.exe' -OutFile '%temp%\GitInstaller.exe'; ^
        echo 'Instalando...'; ^
        Start-Process '%temp%\GitInstaller.exe' -ArgumentList '/VERYSILENT /NORESTART' -Wait; ^
        Remove-Item '%temp%\GitInstaller.exe' -Force" 2>nul
    
    if !errorlevel! equ 0 (
        echo [OK] Git instalado com sucesso
        set "PATH=%PATH%;C:\Program Files\Git\cmd"
    ) else (
        echo [ERRO] Falha ao instalar Git
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
    
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue'; ^
        $url = 'https://desktop.docker.com/win/main/amd64/Docker%%20Desktop%%20Installer.exe'; ^
        $output = '%temp%\DockerInstaller.exe'; ^
        echo 'Baixando Docker Desktop (pode levar alguns minutos)...'; ^
        try { ^
            Invoke-WebRequest -Uri $url -OutFile $output; ^
            echo 'Instalando Docker Desktop (aguarde, pode tomar alguns minutos)...'; ^
            Start-Process $output -ArgumentList 'install --quiet' -Wait; ^
            Remove-Item $output -Force ^
        } catch { ^
            Write-Host 'Erro ao baixar: tentando URL alternativa'; ^
            $url2 = 'https://download.docker.com/win/stable/DockerDesktopInstaller.exe'; ^
            Invoke-WebRequest -Uri $url2 -OutFile $output; ^
            Start-Process $output -ArgumentList 'install --quiet' -Wait; ^
            Remove-Item $output -Force ^
        }" 2>nul
    
    if !errorlevel! equ 0 (
        echo [OK] Docker Desktop instalado com sucesso
        echo [!] Aguarde Docker iniciar (pode levar alguns minutos)...
        timeout /t 10 /nobreak >nul
    ) else (
        echo [AVISO] Falha ao instalar Docker Desktop
        echo [!] Continuando com instalacao do resto...
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
    echo [!] Diretorio ja existe. Realizando backup...
    if not exist "%INSTALL_DIR%_backup" mkdir "%INSTALL_DIR%_backup"
    xcopy "%INSTALL_DIR%" "%INSTALL_DIR%_backup" /E /I /Y >nul 2>&1
)

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo [OK] Diretorio criado: %INSTALL_DIR%
) else (
    echo [OK] Diretorio ja existe
)
echo.

REM ============================================================================
REM Clonar repositorio do Git
REM ============================================================================
echo [5/6] Clonando repositorio...
cd /d "%INSTALL_DIR%"

if exist "%INSTALL_DIR%\.git" (
    echo [!] Repositorio ja clonado. Atualizando...
    cd /d "%INSTALL_DIR%"
    git pull origin main >nul 2>&1
) else (
    echo [!] Clonando repositorio de %REPO_URL%
    git clone "%REPO_URL%" "%INSTALL_DIR%" >nul 2>&1
    
    if !errorlevel! neq 0 (
        echo [ERRO] Falha ao clonar repositorio
        echo [!] Verifique sua conexao com a internet
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
call npm install --legacy-peer-deps >nul 2>&1

if %errorlevel% equ 0 (
    echo [OK] Dependencias instaladas com sucesso
) else (
    echo [AVISO] Houve erros ao instalar dependencias
    echo [!] Tentando continuar...
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
REM Iniciar Docker Compose
REM ============================================================================
echo Iniciando Docker Compose...
cd /d "%INSTALL_DIR%"

if exist "docker-compose.yml" (
    docker-compose up -d >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Docker Compose iniciado
    ) else (
        echo [AVISO] Erro ao iniciar Docker Compose
    )
) else (
    echo [!] docker-compose.yml nao encontrado
)
echo.

REM ============================================================================
REM Criar atalho na area de trabalho
REM ============================================================================
echo Criando atalho na area de trabalho...
set "DESKTOP=%USERPROFILE%\Desktop"
if exist "%DESKTOP%" (
    (
        echo @echo off
        echo cd /d "%INSTALL_DIR%"
        echo call scripts\run.bat
    ) > "%DESKTOP%\Sistema Emprestimos.bat"
    echo [OK] Atalho criado: %DESKTOP%\Sistema Emprestimos.bat
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
echo Para gerenciar o sistema, execute:
echo  %DESKTOP%\Sistema Emprestimos.bat
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
endlocal
