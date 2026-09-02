@echo off
REM ============================================================================
REM  EXECUTOR COM PRIVILEGIOS - Facilita execucao de scripts com admin
REM  ============================================================================

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM Se nao tem argumento, mostra menu
if "%1"=="" goto :no_args

REM Se ja e administrador, prossegue com comando
net session >nul 2>&1
if %errorlevel% equ 0 (
    goto :check_args
)

REM Pede privilegios e passa argumentos
echo [*] Solicitando privilegios de administrador...
powershell -Command "Start-Process cmd -ArgumentList '/c cd /d %CD% ^& %~s0 %~1 %~2 %~3' -Verb RunAs"
exit /b

:no_args
REM Pede privilegios para menu
net session >nul 2>&1
if %errorlevel% equ 0 (
    goto :show_menu
)

echo [*] Solicitando privilegios de administrador...
powershell -Command "Start-Process cmd -ArgumentList '/c cd /d %CD% ^& %~s0' -Verb RunAs"
exit /b

:check_args
REM Executa o script apropriado baseado no argumento
if /i "%1"=="install" goto :run_install
if /i "%1"=="update" goto :run_update
if /i "%1"=="uninstall" goto :run_uninstall
if /i "%1"=="manage" goto :run_manage
if /i "%1"=="help" goto :show_help

echo Comando desconhecido: %1
echo.
timeout /t 2 /nobreak >nul
goto :show_menu

:show_menu
cls
echo.
echo ====================================================================
echo  SISTEMA DE EMPRESTIMOS - Menu de Execucao Rapida
echo ====================================================================
echo.
echo Use: %~nx0 [comando]
echo.
echo Comandos disponiveis:
echo   install   - Instalar o sistema
echo   update    - Atualizar o sistema
echo   uninstall - Desinstalar o sistema
echo   manage    - Gerenciar servicos
echo   help      - Mostrar esta ajuda
echo.
echo Exemplo: %~nx0 install
echo.
set /p COMANDO="Digite o comando: "
if "!COMANDO!"=="" goto :show_menu
if /i "!COMANDO!"=="install" goto :run_install
if /i "!COMANDO!"=="update" goto :run_update
if /i "!COMANDO!"=="uninstall" goto :run_uninstall
if /i "!COMANDO!"=="manage" goto :run_manage
if /i "!COMANDO!"=="help" goto :show_help
echo.
echo Comando desconhecido: !COMANDO!
echo.
timeout /t 2 /nobreak >nul
goto :show_menu

:show_help
echo.
echo ====================================================================
echo  AJUDA - Scripts de Instalacao e Gerenciamento
echo ====================================================================
echo.
echo Este arquivo facilita a execucao dos scripts com privilegios admin.
echo.
echo USO:
echo   %~nx0 install    - Primeira instalacao do sistema
echo   %~nx0 update     - Atualizar para nova versao
echo   %~nx0 uninstall  - Remover o sistema
echo   %~nx0 manage     - Abrir painel de gerenciamento
echo.
echo PRIMEIRA VEZ:
echo 1. Execute: %~nx0 install
echo 2. Aguarde a conclusao (15-30 minutos)
echo 3. Acesse: http://localhost:3000
echo.
echo ATUALIZAR:
echo Execute: %~nx0 update
echo.
echo DESINSTALAR:
echo Execute: %~nx0 uninstall
echo.
echo GERENCIAR:
echo Execute: %~nx0 manage
echo.
timeout /t 5 /nobreak >nul
goto :end

:run_install
call install.bat
goto :show_menu

:run_update
call update.bat
goto :show_menu

:run_uninstall
call uninstall.bat
goto :show_menu

:run_manage
call manage.bat
goto :show_menu

:end
endlocal
