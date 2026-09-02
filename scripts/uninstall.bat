@echo off
REM ============================================================================
REM  DESINSTALADOR - Sistema de Controle de Emprestimos e Cartao de Credito
REM  ============================================================================
REM  Este script realiza a desinstalacao completa do sistema
REM  ============================================================================

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Desinstalador - Sistema de Emprestimos

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
set "SERVICE_NAME=SistemaEmprestimosBackend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"

echo =====================================================================
echo  DESINSTALADOR - Sistema de Controle de Emprestimos
echo =====================================================================
echo.
echo AVISO: Esta operacao vai remover o sistema completamente!
echo.
echo Diretorio a ser removido: %INSTALL_DIR%
echo.

REM ============================================================================
REM Confirmacao
REM ============================================================================
set /p confirm="Deseja continuar? (S/N): "
if /i not "%confirm%"=="S" (
    echo.
    echo Desinstalacao cancelada
    echo.
    pause >nul
    exit /b 0
)

echo.

REM ============================================================================
REM Verificar se o sistema esta instalado
REM ============================================================================
if not exist "%INSTALL_DIR%" (
    echo [!] Sistema nao encontrado em: %INSTALL_DIR%
    echo.
    echo Nada a desinstalar.
    echo.
    pause >nul
    exit /b 1
)

echo %GREEN%[✓] Sistema encontrado%RESET%
echo.

REM ============================================================================
REM Parar serviços
REM ============================================================================
echo %BLUE%[1/4] Parando serviços...%RESET%

echo Parando Backend...
net stop "%SERVICE_NAME%" /y >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Backend parado%RESET%
) else (
    echo %YELLOW%[!] Aviso: Backend pode não estar rodando%RESET%
)

timeout /t 2 >nul

echo Parando Frontend...
net stop "%FRONTEND_SERVICE_NAME%" /y >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Frontend parado%RESET%
) else (
    echo %YELLOW%[!] Aviso: Frontend pode não estar rodando%RESET%
)

timeout /t 2 >nul

echo Parando banco de dados...
cd /d "%INSTALL_DIR%"
docker-compose down >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Banco de dados parado%RESET%
) else (
    echo %YELLOW%[!] Aviso: Banco pode não estar rodando%RESET%
)

echo.

REM ============================================================================
REM Remover serviços do Windows
REM ============================================================================
echo %BLUE%[2/4] Removendo serviços do Windows...%RESET%

REM Verificar se NSSM está disponível
where nssm >nul 2>&1
if %errorlevel% equ 0 (
    echo Removendo serviço Backend...
    nssm remove "%SERVICE_NAME%" confirm >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Serviço Backend removido%RESET%
    ) else (
        echo %YELLOW%[!] Aviso: Não foi possível remover o serviço Backend%RESET%
    )
    
    echo Removendo serviço Frontend...
    nssm remove "%FRONTEND_SERVICE_NAME%" confirm >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Serviço Frontend removido%RESET%
    ) else (
        echo %YELLOW%[!] Aviso: Não foi possível remover o serviço Frontend%RESET%
    )
) else (
    echo %YELLOW%[!] NSSM não encontrado. Tentando remover manualmente...%RESET%
    
    sc delete "%SERVICE_NAME%" >nul 2>&1
    sc delete "%FRONTEND_SERVICE_NAME%" >nul 2>&1
    
    echo %GREEN%[✓] Serviços removidos%RESET%
)

echo.

REM ============================================================================
REM Remover atalhos
REM ============================================================================
echo %BLUE%[3/4] Removendo atalhos...%RESET%

if exist "%USERPROFILE%\Desktop\Sistema Emprestimos.lnk" (
    del "%USERPROFILE%\Desktop\Sistema Emprestimos.lnk" >nul 2>&1
    echo %GREEN%[✓] Atalho removido%RESET%
) else (
    echo %YELLOW%[!] Atalho não encontrado%RESET%
)

echo.

REM ============================================================================
REM Remover diretório de instalação
REM ============================================================================
echo %BLUE%[4/4] Removendo diretórios...%RESET%

if exist "%INSTALL_DIR%" (
    echo Removendo: %INSTALL_DIR%
    REM Dar permissão total e remover
    icacls "%INSTALL_DIR%" /grant:r "%USERNAME%:F" /T /C >nul 2>&1
    rmdir /s /q "%INSTALL_DIR%" >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Diretório removido com sucesso%RESET%
    ) else (
        echo %YELLOW%[!] Aviso: Alguns arquivos podem ter permanecido%RESET%
        echo Remova manualmente: %INSTALL_DIR%
    )
) else (
    echo %YELLOW%[!] Diretório já foi removido%RESET%
)

echo.

REM ============================================================================
REM Limpeza final
REM ============================================================================
echo %BLUE%Limpando variáveis de ambiente...%RESET%

REM Remover do PATH se estava lá
setx PATH "!PATH:%INSTALL_DIR%\bin=!"  >nul 2>&1

echo %GREEN%[✓] Limpeza concluída%RESET%
echo.

REM ============================================================================
REM Resumo
REM ============================================================================
echo %GREEN%=====================================================================%RESET%
echo %GREEN% DESINSTALACAO CONCLUIDA COM SUCESSO!%RESET%
echo %GREEN%=====================================================================%RESET%
echo.
echo O Sistema de Empréstimos foi removido de sua máquina.
echo.
echo Se desejar reinstalar, execute o script install.bat
echo.
pause >nul

goto end

:end
endlocal
exit /b 0
