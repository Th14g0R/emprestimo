@echo off
REM ============================================================================
REM  GERENCIADOR - Sistema de Controle de Emprestimos e Cartao de Credito
REM  ============================================================================
REM  Este script permite gerenciar o servico (iniciar, parar, reiniciar)
REM  ============================================================================

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM Cores para output
for /F %%A in ('copy /Z "%~f0" nul') do set "BS=%%A"
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "RESET=[0m"

title Gerenciador - Sistema de Empréstimos

REM ============================================================================
REM Verificar privilégios de administrador
REM ============================================================================
echo.
echo %BLUE%[*] Verificando privilégios de administrador...%RESET%

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[!] Este script requer privilégios de administrador!%RESET%
    powershell -Command "Start-Process cmd -ArgumentList '/c %~s0 %*' -Verb RunAs" >nul 2>&1
    exit /b
)

REM ============================================================================
REM Definir variáveis
REM ============================================================================
set "INSTALL_DIR=%ProgramFiles%\SistemaEmprestimos"
set "SERVICE_NAME=SistemaEmprestimosBackend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"

REM ============================================================================
REM Menu de opções
REM ============================================================================
:menu
cls
echo.
echo %BLUE%=====================================================================%RESET%
echo %BLUE%  GERENCIADOR - Sistema de Controle de Empréstimos%RESET%
echo %BLUE%=====================================================================%RESET%
echo.
echo Selecione uma operação:
echo.
echo  1 - Iniciar serviços
echo  2 - Parar serviços
echo  3 - Reiniciar serviços
echo  4 - Ver status dos serviços
echo  5 - Abrir Frontend (http://localhost:3000^)
echo  6 - Abrir Backend API (http://localhost:3001/api^)
echo  7 - Abrir Database Admin (http://localhost:8080^)
echo  8 - Ver logs Backend
echo  9 - Ver logs Frontend
echo  0 - Sair
echo.
set /p choice="Digite a opção desejada: "

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
REM Iniciar serviços
REM ============================================================================
:start_services
echo.
echo %BLUE%Iniciando serviços...%RESET%
echo.

echo Iniciando Backend...
net start "%SERVICE_NAME%" >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Backend iniciado com sucesso%RESET%
) else (
    echo %YELLOW%[!] Backend já está rodando ou erro ao iniciar%RESET%
)

echo Iniciando Frontend...
net start "%FRONTEND_SERVICE_NAME%" >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Frontend iniciado com sucesso%RESET%
) else (
    echo %YELLOW%[!] Frontend já está rodando ou erro ao iniciar%RESET%
)

timeout /t 2 >nul
goto menu

REM ============================================================================
REM Parar serviços
REM ============================================================================
:stop_services
echo.
echo %BLUE%Parando serviços...%RESET%
echo.

echo Parando Backend...
net stop "%SERVICE_NAME%" /y >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Backend parado com sucesso%RESET%
) else (
    echo %YELLOW%[!] Backend pode não estar rodando%RESET%
)

echo Parando Frontend...
net stop "%FRONTEND_SERVICE_NAME%" /y >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Frontend parado com sucesso%RESET%
) else (
    echo %YELLOW%[!] Frontend pode não estar rodando%RESET%
)

timeout /t 2 >nul
goto menu

REM ============================================================================
REM Reiniciar serviços
REM ============================================================================
:restart_services
echo.
echo %BLUE%Reiniciando serviços...%RESET%
echo.

call :stop_services
timeout /t 3 >nul
call :start_services

goto menu

REM ============================================================================
REM Ver status dos serviços
REM ============================================================================
:service_status
echo.
echo %BLUE%Status dos serviços:%RESET%
echo.

for /f "tokens=3" %%i in ('sc query "%SERVICE_NAME%" ^| find "STATE"') do (
    if "%%i"=="RUNNING" (
        echo %GREEN%[✓] Backend: RODANDO%RESET%
    ) else if "%%i"=="STOPPED" (
        echo %RED%[✗] Backend: PARADO%RESET%
    ) else (
        echo %YELLOW%[!] Backend: %%i%RESET%
    )
)

for /f "tokens=3" %%i in ('sc query "%FRONTEND_SERVICE_NAME%" ^| find "STATE"') do (
    if "%%i"=="RUNNING" (
        echo %GREEN%[✓] Frontend: RODANDO%RESET%
    ) else if "%%i"=="STOPPED" (
        echo %RED%[✗] Frontend: PARADO%RESET%
    ) else (
        echo %YELLOW%[!] Frontend: %%i%RESET%
    )
)

echo.
echo Pressione uma tecla para continuar...
pause >nul
goto menu

REM ============================================================================
REM Abrir aplicações
REM ============================================================================
:open_frontend
start http://localhost:3000
echo Frontend abrindo em seu navegador...
timeout /t 2 >nul
goto menu

:open_backend
start http://localhost:3001/api
echo Backend API abrindo em seu navegador...
timeout /t 2 >nul
goto menu

:open_database
start http://localhost:8080
echo Adminer (Database Admin) abrindo em seu navegador...
timeout /t 2 >nul
goto menu

REM ============================================================================
REM Ver logs
REM ============================================================================
:view_backend_logs
echo.
echo %BLUE%Logs do Backend (últimas 50 linhas):%%RESET%
echo.

if exist "%INSTALL_DIR%\apps\backend\logs\*.log" (
    for %%F in ("%INSTALL_DIR%\apps\backend\logs\*.log") do (
        echo Arquivo: %%F
        echo ---
        for /f "skip=END tokens=*" %%A in ('find /v "" ^<"%%F" ^| find /c /v ""') do set lines=%%A
        if !lines! gtr 50 (
            more +!lines:-50=0! "%%F"
        ) else (
            type "%%F"
        )
    )
) else (
    echo %YELLOW%Nenhum arquivo de log encontrado%RESET%
)

echo.
echo Pressione uma tecla para continuar...
pause >nul
goto menu

:view_frontend_logs
echo.
echo %BLUE%Logs do Frontend (últimas 50 linhas):%%RESET%
echo.

if exist "%INSTALL_DIR%\apps\frontend\logs\*.log" (
    for %%F in ("%INSTALL_DIR%\apps\frontend\logs\*.log") do (
        echo Arquivo: %%F
        echo ---
        for /f "skip=END tokens=*" %%A in ('find /v "" ^<"%%F" ^| find /c /v ""') do set lines=%%A
        if !lines! gtr 50 (
            more +!lines:-50=0! "%%F"
        ) else (
            type "%%F"
        )
    )
) else (
    echo %YELLOW%Nenhum arquivo de log encontrado%RESET%
)

echo.
echo Pressione uma tecla para continuar...
pause >nul
goto menu

REM ============================================================================
REM Sair
REM ============================================================================
:end
echo.
echo Até logo!
echo.
endlocal
exit /b 0
