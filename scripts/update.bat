@echo off
REM ============================================================================
REM  ATUALIZADOR - Sistema de Controle de Emprestimos e Cartao de Credito
REM  ============================================================================
REM  Este script realiza a atualizacao do sistema
REM  ============================================================================

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Atualizador - Sistema de Emprestimos

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
echo  ATUALIZADOR - Sistema de Controle de Emprestimos
echo =====================================================================
echo.

REM ============================================================================
REM Verificar dependencias
REM ============================================================================
echo [0/4] Verificando dependencias...

git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Git nao esta instalado
    echo [!] Execute primeiro: run.bat install
    pause >nul
    exit /b 1
)
echo [OK] Git encontrado

docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [AVISO] Docker nao esta instalado
    echo [!] Continue assim mesmo, Docker pode ser instalado depois
) else (
    echo [OK] Docker encontrado
)

echo.

REM ============================================================================
REM Verificar se o sistema esta instalado
REM ============================================================================
if not exist "%INSTALL_DIR%" (
    echo [!] Sistema nao encontrado em: %INSTALL_DIR%
    echo.
    echo Execute o instalador primeiro: run.bat install
    echo.
    pause >nul
    exit /b 1
)

echo [OK] Sistema encontrado em: %INSTALL_DIR%
echo.

REM ============================================================================
REM Parar servicos
REM ============================================================================
echo [1/4] Parando servicos...

echo Parando Backend...
net stop "%SERVICE_NAME%" /y >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Backend parado
) else (
    echo [!] Aviso: Backend pode nao estar rodando
)

timeout /t 2 >nul

echo Parando Frontend...
net stop "%FRONTEND_SERVICE_NAME%" /y >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Frontend parado
) else (
    echo [!] Aviso: Frontend pode nao estar rodando
)

timeout /t 2 >nul

echo Parando banco de dados...
cd /d "%INSTALL_DIR%"
docker-compose down >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Banco de dados parado
) else (
    echo [!] Aviso: Banco pode nao estar rodando
)

echo.

REM ============================================================================
REM Atualizar codigo via Git
REM ============================================================================
echo [2/4] Atualizando codigo...

cd /d "%INSTALL_DIR%"

if exist .git (
    echo Executando: git pull
    git pull >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo [OK] Codigo atualizado
    ) else (
        echo [!] Falha ao atualizar via Git. Usando atualizacao manual.
    )
) else (
    echo [!] Repositorio Git nao encontrado
)

echo.

REM ============================================================================
REM Atualizar dependencias
REM ============================================================================
echo [3/4] Atualizando dependencias...

if exist package.json (
    echo Executando: npm install
    call npm install >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo [OK] Dependencias atualizadas
    ) else (
        echo [ERRO] Erro ao atualizar dependencias
        goto error_exit
    )
) else (
    echo [ERRO] arquivo package.json nao encontrado
    goto error_exit
)

echo.

REM ============================================================================
REM Executar migrations (se necessario)
REM ============================================================================
echo [4/4] Aplicando migrations...

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
