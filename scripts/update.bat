@echo off
REM ============================================================================
REM  ATUALIZADOR - Sistema de Controle de Empréstimos e Cartão de Crédito
REM  ============================================================================
REM  Este script realiza a atualização do sistema
REM  ============================================================================

setlocal enabledelayedexpansion

REM Cores para output
for /F %%A in ('copy /Z "%~f0" nul') do set "BS=%%A"
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "RESET=[0m"

title Atualizador - Sistema de Empréstimos

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
set "SERVICE_NAME=SistemaEmprestimosBackend"
set "FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend"

echo %BLUE%=====================================================================%RESET%
echo %BLUE%  ATUALIZADOR - Sistema de Controle de Empréstimos%RESET%
echo %BLUE%=====================================================================%RESET%
echo.

REM ============================================================================
REM Verificar se o sistema está instalado
REM ============================================================================
if not exist "%INSTALL_DIR%" (
    echo %RED%[!] Sistema não encontrado em: %INSTALL_DIR%%RESET%
    echo.
    echo Execute o instalador primeiro.
    echo.
    pause >nul
    exit /b 1
)

echo %GREEN%[✓] Sistema encontrado em: %INSTALL_DIR%%RESET%
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
REM Atualizar código via Git
REM ============================================================================
echo %BLUE%[2/4] Atualizando código...%RESET%

cd /d "%INSTALL_DIR%"

if exist .git (
    echo Executando: git pull
    git pull >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Código atualizado%RESET%
    ) else (
        echo %YELLOW%[!] Falha ao atualizar via Git. Usando atualização manual.%RESET%
    )
) else (
    echo %YELLOW%[!] Repositório Git não encontrado%RESET%
)

echo.

REM ============================================================================
REM Atualizar dependências
REM ============================================================================
echo %BLUE%[3/4] Atualizando dependências...%RESET%

if exist package.json (
    echo Executando: npm install
    call npm install >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Dependências atualizadas%RESET%
    ) else (
        echo %RED%[!] Erro ao atualizar dependências%RESET%
        goto error_exit
    )
) else (
    echo %RED%[!] arquivo package.json não encontrado%RESET%
    goto error_exit
)

echo.

REM ============================================================================
REM Executar migrations (se necessário)
REM ============================================================================
echo %BLUE%[4/4] Aplicando migrations...%RESET%

if exist apps\backend\prisma\schema.prisma (
    echo Iniciando banco de dados...
    docker-compose up -d >nul 2>&1
    
    timeout /t 5 >nul
    
    cd apps\backend
    echo Aplicando migrations...
    call npx prisma migrate deploy >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo %GREEN%[✓] Migrations aplicadas com sucesso%RESET%
    ) else (
        echo %YELLOW%[!] Aviso: Não houve migrations para aplicar%RESET%
    )
    
    cd /d "%INSTALL_DIR%"
) else (
    echo %YELLOW%[!] Schema Prisma não encontrado%RESET%
)

echo.

REM ============================================================================
REM Reiniciar serviços
REM ============================================================================
echo %BLUE%Reiniciando serviços...%RESET%

echo Iniciando Backend...
net start "%SERVICE_NAME%" >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Backend iniciado%RESET%
) else (
    echo %RED%[!] Erro ao iniciar Backend%RESET%
)

timeout /t 3 >nul

echo Iniciando Frontend...
net start "%FRONTEND_SERVICE_NAME%" >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%[✓] Frontend iniciado%RESET%
) else (
    echo %RED%[!] Erro ao iniciar Frontend%RESET%
)

echo.

REM ============================================================================
REM Exibir status dos serviços
REM ============================================================================
echo %BLUE%=====================================================================%RESET%
echo %BLUE% STATUS DOS SERVICOS%RESET%
echo %BLUE%=====================================================================%RESET%
echo.

for /f "tokens=3" %%i in ('sc query "%SERVICE_NAME%" ^| find "STATE"') do (
    if "%%i"=="RUNNING" (
        echo %GREEN%[✓] Backend: RODANDO%RESET%
    ) else (
        echo %YELLOW%[!] Backend: %%i%RESET%
    )
)

for /f "tokens=3" %%i in ('sc query "%FRONTEND_SERVICE_NAME%" ^| find "STATE"') do (
    if "%%i"=="RUNNING" (
        echo %GREEN%[✓] Frontend: RODANDO%RESET%
    ) else (
        echo %YELLOW%[!] Frontend: %%i%RESET%
    )
)

echo.
echo %GREEN%=====================================================================%RESET%
echo %GREEN% ATUALIZACAO CONCLUIDA COM SUCESSO!%RESET%
echo %GREEN%=====================================================================%RESET%
echo.
echo Acesse http://localhost:3000 para verificar as alterações.
echo.
pause >nul

goto end

REM ============================================================================
REM Tratamento de erros
REM ============================================================================
:error_exit
echo.
echo %RED%=====================================================================%RESET%
echo %RED% ERRO NA ATUALIZACAO%RESET%
echo %RED%=====================================================================%RESET%
echo.
echo Verifique se o sistema está instalado corretamente.
echo.
pause >nul
exit /b 1

:end
endlocal
exit /b 0
