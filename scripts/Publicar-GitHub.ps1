[CmdletBinding()]
param(
    [string]$SourcePath,
    [string]$RepositoryUrl = 'https://github.com/Th14g0R/emprestimo.git',
    [string]$Branch = 'main'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Step {
    param([string]$Text)
    Write-Host "`n[+] $Text" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Text)
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Text)
    Write-Host "[!] $Text" -ForegroundColor Yellow
}

function Ask-YesNo {
    param(
        [Parameter(Mandatory)] [string]$Question,
        [bool]$DefaultYes = $false
    )

    $suffix = if ($DefaultYes) { '[S/n]' } else { '[s/N]' }

    while ($true) {
        $answer = (Read-Host "$Question $suffix").Trim().ToLowerInvariant()

        if ([string]::IsNullOrWhiteSpace($answer)) {
            return $DefaultYes
        }

        if ($answer -in @('s', 'sim', 'y', 'yes')) { return $true }
        if ($answer -in @('n', 'nao', 'não', 'no')) { return $false }

        Write-Warn 'Responda S ou N.'
    }
}

function Refresh-PathEnvironment {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
}

function Resolve-Git {
    $git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }

    $knownPaths = @(
        'C:\Program Files\Git\cmd\git.exe',
        'C:\Program Files\Git\bin\git.exe',
        (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe')
    )

    foreach ($known in $knownPaths) {
        if (Test-Path $known) { return $known }
    }

    Write-Warn 'Git for Windows não foi encontrado.'

    if (-not (Ask-YesNo 'Deseja instalar o Git automaticamente para continuar?' $true)) {
        throw 'Git é necessário para publicar o projeto.'
    }

    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'WinGet não está disponível. Instale o Git for Windows e execute novamente.'
    }

    Write-Step 'Instalando Git for Windows...'
    & $winget.Source install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements

    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar Git. Código: $LASTEXITCODE"
    }

    Refresh-PathEnvironment

    $git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }

    foreach ($known in $knownPaths) {
        if (Test-Path $known) { return $known }
    }

    throw 'Git foi instalado, mas ainda não foi localizado. Feche o terminal, abra novamente e execute o publicador.'
}

function Resolve-SourcePath {
    param([string]$RequestedPath)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        return [IO.Path]::GetFullPath($RequestedPath)
    }

    $currentScript = $PSCommandPath
    if ([string]::IsNullOrWhiteSpace($currentScript)) {
        $currentScript = $MyInvocation.MyCommand.Path
    }

    if ([string]::IsNullOrWhiteSpace($currentScript)) {
        throw 'Não foi possível determinar o caminho deste script.'
    }

    $scriptDirectory = Split-Path -Parent $currentScript
    return (Resolve-Path -LiteralPath (Join-Path $scriptDirectory '..')).Path
}

function Ensure-GitIdentity {
    param(
        [Parameter(Mandatory)] [string]$GitExe,
        [Parameter(Mandatory)] [string]$RepositoryPath
    )

    $name = (& $GitExe -C $RepositoryPath config user.name 2>$null | Select-Object -First 1)
    $email = (& $GitExe -C $RepositoryPath config user.email 2>$null | Select-Object -First 1)

    if ([string]::IsNullOrWhiteSpace($name)) {
        $name = (Read-Host 'Nome para identificar o commit no GitHub').Trim()
        if ([string]::IsNullOrWhiteSpace($name)) {
            throw 'O nome do autor do commit é obrigatório.'
        }
        & $GitExe -C $RepositoryPath config user.name $name
    }

    if ([string]::IsNullOrWhiteSpace($email)) {
        $email = (Read-Host 'E-mail para identificar o commit no GitHub').Trim()
        if ([string]::IsNullOrWhiteSpace($email)) {
            throw 'O e-mail do autor do commit é obrigatório.'
        }
        & $GitExe -C $RepositoryPath config user.email $email
    }
}

function Invoke-GitHubBrowserLogin {
    param([Parameter(Mandatory)] [string]$GitExe)

    Write-Step 'Preparando autenticação segura no GitHub...'

    # Git for Windows atual normalmente inclui Git Credential Manager.
    & $GitExe credential-manager --version *> $null

    if ($LASTEXITCODE -ne 0) {
        throw @'
Git Credential Manager não foi localizado.
Atualize/reinstale o Git for Windows ou autentique com GitHub CLI/PAT.
'@
    }

    # GCM é o helper recomendado para HTTPS no Windows.
    & $GitExe config --global credential.helper manager
    & $GitExe config --global credential.gitHubAccountFiltering false

    Write-Host ''
    Write-Host 'Será aberta a autenticação do GitHub.' -ForegroundColor Yellow
    Write-Host 'Escolha "Sign in with your browser" e entre na conta Th14g0R.' -ForegroundColor Yellow
    Write-Host ''

    & $GitExe credential-manager github login

    if ($LASTEXITCODE -ne 0) {
        throw 'A autenticação pelo Git Credential Manager não foi concluída.'
    }

    Write-Ok 'Autenticação do GitHub concluída.'
}

function Push-WithAuthenticationRetry {
    param(
        [Parameter(Mandatory)] [string]$GitExe,
        [Parameter(Mandatory)] [string]$RepositoryPath,
        [Parameter(Mandatory)] [string]$BranchName
    )

    Write-Step 'Enviando para o GitHub...'
    & $GitExe -C $RepositoryPath push origin $BranchName

    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Warn 'O primeiro push falhou por autenticação ou credencial armazenada.'

    if (-not (Ask-YesNo 'Deseja autenticar pelo navegador e tentar novamente?' $true)) {
        throw 'Push não realizado.'
    }

    Invoke-GitHubBrowserLogin -GitExe $GitExe

    Write-Step 'Tentando o push novamente...'
    & $GitExe -C $RepositoryPath push origin $BranchName

    if ($LASTEXITCODE -ne 0) {
        throw @'
O push continuou falhando.

Se aparecer "Invalid username or token", remova a credencial antiga do GitHub em:
Painel de Controle > Contas de Usuário > Gerenciador de Credenciais >
Credenciais do Windows.

Remova as entradas relacionadas a github.com e execute o publicador novamente.
'@
    }
}

$SourcePath = Resolve-SourcePath -RequestedPath $SourcePath
$git = Resolve-Git

Write-Ok "Git encontrado: $git"

if (-not (Test-Path (Join-Path $SourcePath 'app.py'))) {
    throw "app.py não encontrado em '$SourcePath'."
}

if (-not (Test-Path (Join-Path $SourcePath '.gitignore'))) {
    throw '.gitignore não encontrado.'
}

$sensitive = @(
    (Join-Path $SourcePath 'data\emprestimos.db'),
    (Join-Path $SourcePath 'data\.secret_key')
) | Where-Object { Test-Path $_ }

if ($sensitive.Count -gt 0) {
    Write-Host ''
    Write-Warn 'Arquivos locais sensíveis encontrados. Eles NÃO serão enviados:'
    $sensitive | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
}

Write-Host ''
Write-Host "Origem:      $SourcePath"
Write-Host "Repositório: $RepositoryUrl"
Write-Host "Branch:      $Branch"
Write-Host ''
Write-Warn 'A branch atual será atualizada com o projeto Python.'
Write-Warn 'O histórico anterior do Git continuará preservado.'

if (-not (Ask-YesNo 'Deseja continuar?' $false)) {
    exit 0
}

$tempRoot = Join-Path $env:TEMP ("emprestimo-publish-" + [Guid]::NewGuid().ToString('N'))

try {
    Write-Step 'Clonando a versão atual do repositório...'
    & $git clone --branch $Branch --single-branch $RepositoryUrl $tempRoot

    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao clonar o repositório.'
    }

    Get-ChildItem -LiteralPath $tempRoot -Force |
        Where-Object { $_.Name -ne '.git' } |
        Remove-Item -Recurse -Force

    $excludeDirs = @(
        '.git', '.venv', 'venv', 'env', '__pycache__',
        'data', 'logs', 'service', 'backups', 'backup'
    )

    $excludeFiles = @(
        '*.pyc', '*.pyo', '*.db', '*.db-wal', '*.db-shm',
        '.secret_key', '.env'
    )

    $robocopyArgs = @(
        $SourcePath, $tempRoot,
        '/E', '/R:2', '/W:1',
        '/NFL', '/NDL', '/NJH', '/NJS', '/NP',
        '/XD'
    ) + $excludeDirs + @('/XF') + $excludeFiles

    Write-Step 'Copiando o projeto atual...'
    & robocopy.exe @robocopyArgs | Out-Null

    if ($LASTEXITCODE -ge 8) {
        throw "Robocopy falhou. Código: $LASTEXITCODE"
    }

    New-Item -ItemType Directory -Path (Join-Path $tempRoot 'data') -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $tempRoot 'data\.gitkeep') -Force | Out-Null

    & $git -C $tempRoot add -A
    if ($LASTEXITCODE -ne 0) {
        throw 'Falha no git add.'
    }

    Write-Host ''
    Write-Host 'Alterações que serão publicadas:' -ForegroundColor Cyan
    & $git -C $tempRoot status --short

    $status = (& $git -C $tempRoot status --porcelain)
    if (-not $status) {
        Write-Ok 'Não existem diferenças para publicar.'
        exit 0
    }

    if (-not (Ask-YesNo 'Confirma o commit e o push?' $false)) {
        exit 0
    }

    Ensure-GitIdentity -GitExe $git -RepositoryPath $tempRoot

    $message = "Atualiza projeto Python Flask SQLite - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

    Write-Step 'Criando commit...'
    & $git -C $tempRoot commit -m $message

    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao criar o commit.'
    }

    Push-WithAuthenticationRetry `
        -GitExe $git `
        -RepositoryPath $tempRoot `
        -BranchName $Branch

    Write-Host ''
    Write-Ok 'Publicação concluída com sucesso.'
    Write-Host "Repositório: $RepositoryUrl"
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
