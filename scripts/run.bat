@echo off
REM ============================================================================
REM  EXECUTOR COM PRIVILEGIOS - Facilita execução de scripts com admin
REM  ============================================================================

setlocal enabledelayedexpansion

REM Se já é administrador, prossegue direto
net session >nul 2>&1
if %errorlevel% equ 0 (
    goto :execute
)

REM Solicita privilégios de administrador
echo Solicitando privilégios de administrador...
powershell -Command "Start-Process cmd -ArgumentList '/c %~s0 %*' -Verb RunAs"
exit /b

:execute
REM Executa o script apropriado baseado no argumento
if "%1"=="" goto :show_menu
if /i "%1"=="install" goto :run_install
if /i "%1"=="update" goto :run_update
if /i "%1"=="uninstall" goto :run_uninstall
if /i "%1"=="manage" goto :run_manage
if /i "%1"=="help" goto :show_help

echo Comando desconhecido: %1
goto :show_menu

:show_menu
cls
echo.
echo ====================================================================
echo  SISTEMA DE EMPRESTIMOS - Menu de Execução Rápida
echo ====================================================================
echo.
echo Use: %~nx0 [comando]
echo.
echo Comandos disponíveis:
echo   install   - Instalar o sistema
echo   update    - Atualizar o sistema
echo   uninstall - Desinstalar o sistema
echo   manage    - Gerenciar serviços
echo   help      - Mostrar esta ajuda
echo.
echo Exemplo: %~nx0 install
echo.
pause >nul
goto :end

:show_help
echo.
echo ====================================================================
echo  AJUDA - Scripts de Instalação e Gerenciamento
echo ====================================================================
echo.
echo Este arquivo facilita a execução dos scripts com privilégios admin.
echo.
echo USO:
echo   %~nx0 install    - Primeira instalação do sistema
echo   %~nx0 update     - Atualizar para nova versão
echo   %~nx0 uninstall  - Remover o sistema
echo   %~nx0 manage     - Abrir painel de gerenciamento
echo.
echo PRIMEIRA VEZ:
echo 1. Execute: %~nx0 install
echo 2. Aguarde a conclusão (15-30 minutos)
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
pause >nul
goto :end

:run_install
call install.bat
goto :end

:run_update
call update.bat
goto :end

:run_uninstall
call uninstall.bat
goto :end

:run_manage
call manage.bat
goto :end

:end
endlocal
