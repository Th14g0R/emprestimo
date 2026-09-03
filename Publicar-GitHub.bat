@echo off
setlocal EnableExtensions

set "BASE=%~dp0"
set "SCRIPT=%BASE%scripts\Publicar-GitHub.ps1"
set "LOGDIR=%BASE%logs"

if not exist "%SCRIPT%" (
    echo.
    echo ERRO: Nao foi encontrado:
    echo %SCRIPT%
    echo.
    pause
    exit /b 1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-4 delims=/ " %%a in ("%date%") do (
    set "DATA=%%d-%%c-%%b"
)
set "HORA=%time::=-%"
set "HORA=%HORA: =0%"
set "HORA=%HORA:.=-%"
set "LOG=%LOGDIR%\publicar-github_%DATA%_%HORA%.log"

echo ============================================================
echo PUBLICAR PROJETO EMPRESTIMO NO GITHUB
echo ============================================================
echo.
echo Script:
echo %SCRIPT%
echo.
echo Log:
echo %LOG%
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Continue';" ^
  "Start-Transcript -LiteralPath '%LOG%' -Force | Out-Null;" ^
  "$rc=0;" ^
  "try { & '%SCRIPT%'; if (-not $?) { $rc=1 } }" ^
  "catch { Write-Host ''; Write-Host ('ERRO: ' + $_.Exception.Message) -ForegroundColor Red; $rc=1 }" ^
  "finally { try { Stop-Transcript | Out-Null } catch {} };" ^
  "exit $rc"

set "RC=%ERRORLEVEL%"

echo.
echo ============================================================
if "%RC%"=="0" (
    echo PROCESSO FINALIZADO SEM ERRO.
) else (
    echo PROCESSO FINALIZADO COM ERRO. CODIGO: %RC%
)
echo.
echo O log completo foi salvo em:
echo %LOG%
echo ============================================================
echo.
pause

exit /b %RC%
