@echo off
REM ============================================================================
REM  INSTALADOR - Sistema de Controle de Empréstimos e Cartão de Crédito
REM  ============================================================================
REM  Este script realiza a instalação completa do sistema
REM  Verifica dependências, instala o necessário e configura como serviço
REM  ============================================================================

setlocal enabledelayedexpansion

REM Cores para output
for /F %%A in ('copy /Z "%~f0" nul') do set "BS=%%A"
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "RESET=[0m"

title Instalador - Sistema de Empréstimos

REM ============================================================================
REM Verificar privilégios de administrador
REM ============================================================================
echo.
echo %BLUE%[*] Verificando privilégios de administrador...%RESET%

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[!] Este script requer privilégios de administrador!%RESET%
    echo.
    echo Solicitando privilégios...
    powershell -Command "Start-Process cmd -ArgumentList '/c %~s0' -Verb RunAs" >nul 2>&1
    exit /b
)

echo %GREEN%[✓] Privilégios de administrador confirmados%RESET%
echo.

REM ============================================================================
REM Definir variáveis
REM ============================================================================
setlocal enabledelayedexpansion
set "INSTALL_DIR=%ProgramFiles%\SistemaEmprestimos"
set "APP_NAME=Sistema-Emprestimos"
set "SERVICE_NAME=SistemaEmprestimosBackend"
set "SERVICE_DISPLAY_NAME=Sistema de Empréstimos - Backend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"
set "FRONTEND_DISPLAY_NAME=Sistema de Empréstimos - Frontend"

echo %BLUE%=====================================================================%RESET%
echo %BLUE%  INSTALADOR - Sistema de Controle de Empréstimos%RESET%
echo %BLUE%=====================================================================%RESET%
echo.
echo Diretório de instalação: %INSTALL_DIR%
echo.

REM ============================================================================
REM Verificar e instalar Node.js
REM ============================================================================
echo %BLUE%[1/5] Verificando Node.js...%RESET%
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%[!] Node.js não encontrado. Instalando...%RESET%
    REM Baixar Node.js LTS
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue'; ^
        Invoke-WebRequest -Uri 'https://nodejs.org/dist/v18.18.0/node-v18.18.0-x64.msi' -OutFile '%temp%\nodejs.msi'; ^
        Start-Process msiexec -ArgumentList '/i %temp%\nodejs.msi /quiet' -Wait; ^
        Remove-Item '%temp%\nodejs.msi'" >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Node.js instalado com sucesso%RESET%
        REM Atualizar PATH
        set "PATH=%PATH%;C:\Program Files\nodejs"
    ) else (
        echo %RED%[!] Erro ao instalar Node.js%RESET%
        goto error_exit
    )
) else (
    echo %GREEN%[✓] Node.js já está instalado%RESET%
    for /f "tokens=*" %%i in ('node --version') do echo    Versão: %%i
)
echo.

REM ============================================================================
REM Verificar e instalar Docker
REM ============================================================================
echo %BLUE%[2/5] Verificando Docker...%RESET%
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%[!] Docker não encontrado. Instalando Docker Desktop...%RESET%
    echo.
    echo Para instalar Docker Desktop, visite:
    echo %BLUE%https://www.docker.com/products/docker-desktop%RESET%
    echo.
    echo Depois de instalar, execute este script novamente.
    timeout /t 3 >nul
    goto error_exit
) else (
    echo %GREEN%[✓] Docker já está instalado%RESET%
    for /f "tokens=*" %%i in ('docker --version') do echo    %%i
)
echo.

REM ============================================================================
REM Verificar e instalar Git
REM ============================================================================
echo %BLUE%[3/5] Verificando Git...%RESET%
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%[!] Git não encontrado. Instalando...%RESET%
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue'; ^
        Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.42.0.windows.1/Git-2.42.0-64-bit.exe' -OutFile '%temp%\git-installer.exe'; ^
        Start-Process '%temp%\git-installer.exe' -ArgumentList '/VERYSILENT /NORESTART' -Wait; ^
        Remove-Item '%temp%\git-installer.exe'" >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Git instalado com sucesso%RESET%
        set "PATH=%PATH%;C:\Program Files\Git\cmd"
    ) else (
        echo %RED%[!] Erro ao instalar Git%RESET%
        goto error_exit
    )
) else (
    echo %GREEN%[✓] Git já está instalado%RESET%
    for /f "tokens=*" %%i in ('git --version') do echo    %%i
)
echo.

REM ============================================================================
REM Criar diretório de instalação
REM ============================================================================
echo %BLUE%[4/5] Criando diretórios...%RESET%

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo %GREEN%[✓] Diretório criado: %INSTALL_DIR%%RESET%
) else (
    echo %YELLOW%[!] Diretório já existe%RESET%
)

REM Copiar arquivos do projeto
if exist "%~dp0.." (
    echo Copiando arquivos do projeto...
    xcopy "%~dp0..\*" "%INSTALL_DIR%\" /E /I /Y >nul 2>&1
    echo %GREEN%[✓] Arquivos copiados%RESET%
) else (
    echo %YELLOW%[!] Não foi possível localizar arquivos do projeto%RESET%
    echo Verifique se o script está no diretório correto
)
echo.

REM ============================================================================
REM Instalar dependências npm
REM ============================================================================
echo %BLUE%[5/5] Instalando dependências...%RESET%
cd /d "%INSTALL_DIR%"

if exist package.json (
    echo Executando: npm install
    call npm install >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Dependências instaladas%RESET%
    ) else (
        echo %RED%[!] Erro ao instalar dependências%RESET%
        goto error_exit
    )
) else (
    echo %YELLOW%[!] arquivo package.json não encontrado%RESET%
)
echo.

REM ============================================================================
REM Criar serviços do Windows
REM ============================================================================
echo %BLUE%Criando serviços do Windows...%RESET%

REM Verificar se NSSM está instalado
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%[!] Instalando NSSM (Non-Sucking Service Manager)...%RESET%
    
    powershell -Command ^
        "$ProgressPreference = 'SilentlyContinue'; ^
        Invoke-WebRequest -Uri 'https://nssm.cc/download/nssm-2.24-101-g897c7f7.zip' -OutFile '%temp%\nssm.zip'; ^
        Expand-Archive -Path '%temp%\nssm.zip' -DestinationPath '%temp%' -Force; ^
        Copy-Item '%temp%\nssm-*\win64\nssm.exe' 'C:\Windows\System32\' -Force; ^
        Remove-Item '%temp%\nssm.zip'; ^
        Remove-Item '%temp%\nssm-*' -Recurse -Force" >nul 2>&1
)

REM Criar serviço Backend
echo Criando serviço Backend...
nssm install "%SERVICE_NAME%" "cmd.exe" "/c cd /d %INSTALL_DIR%\apps\backend && npm start" >nul 2>&1
nssm set "%SERVICE_NAME%" AppDirectory "%INSTALL_DIR%\apps\backend" >nul 2>&1
nssm set "%SERVICE_NAME%" AppExit Default Restart >nul 2>&1
nssm set "%SERVICE_NAME%" AppRestartDelay 5000 >nul 2>&1

REM Definir que o serviço inicia automaticamente
sc config "%SERVICE_NAME%" start= auto >nul 2>&1

if !errorlevel! equ 0 (
    echo %GREEN%[✓] Serviço Backend criado e configurado%RESET%
) else (
    echo %YELLOW%[!] Falha ao criar serviço Backend. Tente manualmente mais tarde.%RESET%
)

REM Criar serviço Frontend
echo Criando serviço Frontend...
nssm install "%FRONTEND_SERVICE_NAME%" "cmd.exe" "/c cd /d %INSTALL_DIR%\apps\frontend && npm start" >nul 2>&1
nssm set "%FRONTEND_SERVICE_NAME%" AppDirectory "%INSTALL_DIR%\apps\frontend" >nul 2>&1
nssm set "%FRONTEND_SERVICE_NAME%" AppExit Default Restart >nul 2>&1
nssm set "%FRONTEND_SERVICE_NAME%" AppRestartDelay 5000 >nul 2>&1

sc config "%FRONTEND_SERVICE_NAME%" start= auto >nul 2>&1

if !errorlevel! equ 0 (
    echo %GREEN%[✓] Serviço Frontend criado e configurado%RESET%
) else (
    echo %YELLOW%[!] Falha ao criar serviço Frontend. Tente manualmente mais tarde.%RESET%
)
echo.

REM ============================================================================
REM Iniciar serviços
REM ============================================================================
echo %BLUE%Iniciando serviços...%RESET%

echo Iniciando Docker...
start "Docker" "C:\Program Files\Docker\Docker\Docker.exe" >nul 2>&1
timeout /t 5 >nul

echo Iniciando banco de dados (PostgreSQL)...
cd /d "%INSTALL_DIR%"
docker-compose up -d >nul 2>&1

if !errorlevel! equ 0 (
    echo %GREEN%[✓] Banco de dados iniciado%RESET%
) else (
    echo %YELLOW%[!] Erro ao iniciar Docker Compose. Verifique manualmente.%RESET%
)
echo.

echo Iniciando serviço Backend...
net start "%SERVICE_NAME%" >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Serviço Backend iniciado%RESET%
) else (
    echo %YELLOW%[!] Erro ao iniciar Backend. Verifique os logs.%RESET%
)

timeout /t 3 >nul

echo Iniciando serviço Frontend...
net start "%FRONTEND_SERVICE_NAME%" >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Serviço Frontend iniciado%RESET%
) else (
    echo %YELLOW%[!] Erro ao iniciar Frontend. Verifique os logs.%RESET%
)
echo.

REM ============================================================================
REM Criar atalhos de acesso rápido
REM ============================================================================
echo %BLUE%Criando atalhos de acesso rápido...%RESET%

REM Atalho na área de trabalho
powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; ^
    $Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Sistema Emprestimos.lnk'); ^
    $Shortcut.TargetPath = 'http://localhost:3000'; ^
    $Shortcut.Save()" >nul 2>&1

echo %GREEN%[✓] Atalho criado na área de trabalho%RESET%
echo.

REM ============================================================================
REM Criar arquivo de resumo
REM ============================================================================
(
    echo.
    echo ====================================================================
    echo INSTALACAO CONCLUIDA - Sistema de Empréstimos
    echo ====================================================================
    echo.
    echo INFORMACOES IMPORTANTES:
    echo.
    echo Diretório de Instalação: %INSTALL_DIR%
    echo.
    echo SERVICOS CRIADOS:
    echo - %SERVICE_DISPLAY_NAME%
    echo - %FRONTEND_DISPLAY_NAME%
    echo.
    echo ACESSOS:
    echo - Frontend: http://localhost:3000
    echo - Backend API: http://localhost:3001/api
    echo - Database Admin: http://localhost:8080
    echo.
    echo PROXIMOS PASSOS:
    echo 1. Abra http://localhost:3000 no seu navegador
    echo 2. Autentique-se com suas credenciais
    echo 3. Configure o banco de dados conforme necessário
    echo.
    echo COMANDO PARA GERENCIAR SERVICOS:
    echo - Para parar:  net stop "%SERVICE_NAME%"
    echo - Para iniciar: net start "%SERVICE_NAME%"
    echo - Para reiniciar: net stop "%SERVICE_NAME%" ^&^& net start "%SERVICE_NAME%"
    echo.
    echo ====================================================================
) > "%INSTALL_DIR%\INSTALACAO_INFO.txt"

echo %BLUE%Abrindo informações de instalação...%RESET%
start "" "%INSTALL_DIR%\INSTALACAO_INFO.txt"

echo.
echo %GREEN%=====================================================================%RESET%
echo %GREEN% INSTALACAO CONCLUIDA COM SUCESSO!%RESET%
echo %GREEN%=====================================================================%RESET%
echo.
echo O sistema está rodando nos seguintes endereços:
echo.
echo   %BLUE%Frontend:%RESET%  http://localhost:3000
echo   %BLUE%Backend:%RESET%   http://localhost:3001/api
echo   %BLUE%Database:%RESET%  http://localhost:8080
echo.
echo Os serviços foram configurados para iniciar automaticamente com o Windows.
echo.
echo Pressione qualquer tecla para fechar...
pause >nul

goto end

REM ============================================================================
REM Tratamento de erros
REM ============================================================================
:error_exit
echo.
echo %RED%=====================================================================%RESET%
echo %RED% ERRO NA INSTALACAO%RESET%
echo %RED%=====================================================================%RESET%
echo.
echo Verifique o log de erros e tente novamente.
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
exit /b 1

:end
endlocal
exit /b 0
