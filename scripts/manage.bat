@echo off
REM ============================================================================
REM  GERENCIADOR - Sistema de Controle de Emprestimos e Cartao de Credito
REM  ============================================================================
REM  Este script permite gerenciar o servico (iniciar, parar, reiniciar)
REM  ============================================================================

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Gerenciador - Sistema de Emprestimos

REM ============================================================================
REM Verificar privilegios de administrador
REM ============================================================================
echo.
echo [*] Verificando privilegios de administrador...

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Este script requer privilegios de administrador!
    powershell -Command "Start-Process cmd -ArgumentList '/c %~s0 %*' -Verb RunAs" >nul 2>&1
    exit /b
)

REM ============================================================================
REM Definir variaveis
REM ============================================================================
set "INSTALL_DIR=%ProgramFiles%\SistemaEmprestimos"
set "SERVICE_NAME=SistemaEmprestimosBackend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"

REM ============================================================================
REM Menu de opcoes
REM ============================================================================
:menu
cls
echo.
echo =====================================================================
echo  GERENCIADOR - Sistema de Controle de Emprestimos
echo =====================================================================
echo.
echo Selecione uma operacao:
echo.
echo  1 - Iniciar servicos
echo  2 - Parar servicos
echo  3 - Reiniciar servicos
echo  4 - Ver status dos servicos
echo  5 - Abrir Frontend (http://localhost:3000^)
echo  6 - Abrir Backend API (http://localhost:3001/api^)
echo  7 - Abrir Database Admin (http://localhost:8080^)
echo  8 - Ver logs Backend
echo  9 - Ver logs Frontend
echo  0 - Sair
echo.
set /p choice="Digite a opcao desejada: "

if "%choice%"=="1" goto start_services
if "%choice%"=="2" goto stop_services
if "%choice%"=="3" goto restart_services
if "%choice%"=="4" goto service_status
if "%choice%"=="5" goto open_frontend
if "%choice%"=="6" goto open_backend
if "%choice%"=="7" goto open_database
if "%choice%"=="8" goto view_backend_logs
if "%choice%"=="9" goto view_frontend_logs
if "%choice%"=="0" goto end
goto menu

REM ============================================================================
REM Iniciar servicos
REM ============================================================================
:start_services
echo.
echo [!] Iniciando Backend...
net start "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend iniciado
) else (
    echo [!] Backend nao pode ser iniciado (talvez ja esteja rodando^)
)

echo [!] Iniciando Frontend...
net start "%FRONTEND_SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend iniciado
) else (
    echo [!] Frontend nao pode ser iniciado (talvez ja esteja rodando^)
)

echo [!] Iniciando Docker...
docker-compose -f "%INSTALL_DIR%\docker-compose.yml" up -d >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Docker Compose iniciado
) else (
    echo [!] Docker nao pode ser iniciado
)

echo.
echo [OK] Servicos iniciados
echo Acesse: http://localhost:3000
echo.
timeout /t 3 /nobreak >nul
goto menu

REM ============================================================================
REM Parar servicos
REM ============================================================================
:stop_services
echo.
echo [!] Parando Backend...
net stop "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend parado
) else (
    echo [!] Backend nao pode ser parado
)

echo [!] Parando Frontend...
net stop "%FRONTEND_SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend parado
) else (
    echo [!] Frontend nao pode ser parado
)

echo [!] Parando Docker...
docker-compose -f "%INSTALL_DIR%\docker-compose.yml" down >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Docker Compose parado
) else (
    echo [!] Docker nao pode ser parado
)

echo.
echo [OK] Servicos parados
echo.
timeout /t 3 /nobreak >nul
goto menu

REM ============================================================================
REM Reiniciar servicos
REM ============================================================================
:restart_services
echo.
echo [!] Reiniciando servicos...
call :stop_services
timeout /t 2 /nobreak >nul
call :start_services
echo.
timeout /t 3 /nobreak >nul
goto menu

REM ============================================================================
REM Ver status dos servicos
REM ============================================================================
:service_status
echo.
echo =====================================================================
echo  STATUS DOS SERVICOS
echo =====================================================================
echo.

echo Backend (%SERVICE_NAME%^):
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%i in ('sc query "%SERVICE_NAME%" ^| find "STATE"') do (
        if "%%i"=="RUNNING" (
            echo   Status: OK [RUNNING]
        ) else if "%%i"=="STOPPED" (
            echo   Status: PARADO [STOPPED]
        ) else (
            echo   Status: %%i
        )
    )
) else (
    echo   Status: SERVICO NAO ENCONTRADO
)

echo.
echo Frontend (%FRONTEND_SERVICE_NAME%^):
sc query "%FRONTEND_SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%i in ('sc query "%FRONTEND_SERVICE_NAME%" ^| find "STATE"') do (
        if "%%i"=="RUNNING" (
            echo   Status: OK [RUNNING]
        ) else if "%%i"=="STOPPED" (
            echo   Status: PARADO [STOPPED]
        ) else (
            echo   Status: %%i
        )
    )
) else (
    echo   Status: SERVICO NAO ENCONTRADO
)

echo.
echo Docker Compose:
docker ps --format "table {{.Names}}\t{{.Status}}" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Status: OK [RUNNING]
    echo.
    docker ps --format "table {{.Names}}\t{{.Status}}"
) else (
    echo   Status: PARADO ou NAO ENCONTRADO
)

echo.
timeout /t 5 /nobreak >nul
goto menu

REM ============================================================================
REM Abrir Frontend
REM ============================================================================
:open_frontend
echo.
echo [!] Abrindo navegador em http://localhost:3000...
start http://localhost:3000
timeout /t 2 /nobreak >nul
goto menu

REM ============================================================================
REM Abrir Backend API
REM ============================================================================
:open_backend
echo.
echo [!] Abrindo navegador em http://localhost:3001/api...
start http://localhost:3001/api
timeout /t 2 /nobreak >nul
goto menu

REM ============================================================================
REM Abrir Database Admin
REM ============================================================================
:open_database
echo.
echo [!] Abrindo navegador em http://localhost:8080...
start http://localhost:8080
timeout /t 2 /nobreak >nul
goto menu

REM ============================================================================
REM Ver logs Backend
REM ============================================================================
:view_backend_logs
echo.
echo [!] Exibindo logs do Backend...
echo.

if exist "%INSTALL_DIR%\backend.log" (
    type "%INSTALL_DIR%\backend.log"
) else (
    echo Arquivo de log nao encontrado: %INSTALL_DIR%\backend.log
    echo.
    echo Tentando obter logs do servico...
    wevtutil qe System /q:"Event[System[Provider[@Name='Service Control Manager'] and EventID=7036 and TimeCreated[timediff(@SystemTime) &lt; 3600000]]]" /f:text /c:10 2>nul
)

echo.
timeout /t 5 /nobreak >nul
goto menu

REM ============================================================================
REM Ver logs Frontend
REM ============================================================================
:view_frontend_logs
echo.
echo [!] Exibindo logs do Frontend...
echo.

if exist "%INSTALL_DIR%\frontend.log" (
    type "%INSTALL_DIR%\frontend.log"
) else (
    echo Arquivo de log nao encontrado: %INSTALL_DIR%\frontend.log
    echo.
    echo Tentando obter logs do servico...
    wevtutil qe System /q:"Event[System[Provider[@Name='Service Control Manager'] and EventID=7036 and TimeCreated[timediff(@SystemTime) &lt; 3600000]]]" /f:text /c:10 2>nul
)

echo.
timeout /t 5 /nobreak >nul
goto menu

REM ============================================================================
REM Sair
REM ============================================================================
:end
echo.
echo [OK] Ate logo!
echo.
timeout /t 2 /nobreak >nul
endlocal
