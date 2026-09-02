[CmdletBinding()]
param(
    [ValidateSet('Instalar', 'Atualizar', 'Desinstalar')]
    [string]$Acao,

    [string]$InstallPath,

    [ValidateRange(1024, 65535)]
    [int]$Porta = 5000,

    [ValidateSet('Local', 'Rede')]
    [string]$Acesso
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Script:RepoUrl = 'https://github.com/Th14g0R/emprestimo.git'
$Script:Branch = 'main'
$Script:ServiceName = 'Emprestimo'
$Script:RegistryPath = 'HKLM:\SOFTWARE\Emprestimo'
$Script:DefaultInstallPath = Join-Path $env:ProgramData 'Emprestimo'
$Script:BackupRoot = Join-Path $env:ProgramData 'EmprestimoBackup'
$Script:WinSWVersion = '2.12.0'
$Script:WinSWX64Sha256 = '05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da'
$Script:WinSWX86Sha256 = '0c21327463a43a61f2efb227ec4afd2467fde91618cc725148c1099001ca91ae'
$Script:FirewallRuleName = 'Emprestimo HTTP'
$Script:ShortcutPath = Join-Path $env:PUBLIC 'Desktop\Emprestimo.url'

function Write-Title {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
}

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
        [bool]$DefaultYes = $true
    )

    $suffix = if ($DefaultYes) { '[S/n]' } else { '[s/N]' }
    while ($true) {
        $answer = (Read-Host "$Question $suffix").Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($answer)) { return $DefaultYes }
        if ($answer -in @('s', 'sim', 'y', 'yes')) { return $true }
        if ($answer -in @('n', 'nao', 'não', 'no')) { return $false }
        Write-Warn 'Responda S ou N.'
    }
}

function Ensure-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if ($isAdmin) { return }

    Write-Warn 'Esta operação precisa de privilégios de Administrador.'

    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($Acao) { $arguments += @('-Acao', $Acao) }
    if ($InstallPath) { $arguments += @('-InstallPath', "`"$InstallPath`"") }
    if ($PSBoundParameters.ContainsKey('Porta')) { $arguments += @('-Porta', $Porta) }
    if ($Acesso) { $arguments += @('-Acesso', $Acesso) }

    Start-Process -FilePath 'powershell.exe' -ArgumentList ($arguments -join ' ') -Verb RunAs -Wait
    exit 0
}

function Refresh-PathEnvironment {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
}

function Get-Winget {
    $cmd = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Install-WithWinget {
    param(
        [Parameter(Mandatory)] [string]$PackageId,
        [Parameter(Mandatory)] [string]$DisplayName
    )

    $winget = Get-Winget
    if (-not $winget) {
        throw "WinGet não está disponível. Instale 'App Installer' da Microsoft Store e execute novamente para instalar $DisplayName automaticamente."
    }

    if (-not (Ask-YesNo "$DisplayName não foi encontrado. Deseja instalá-lo agora?" $true)) {
        throw "$DisplayName é necessário para continuar."
    }

    Write-Step "Instalando $DisplayName via WinGet..."
    & $winget install --id $PackageId -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Falha na instalação de $DisplayName pelo WinGet. Código: $LASTEXITCODE"
    }

    Refresh-PathEnvironment
}

function Resolve-Git {
    $git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }

    $known = 'C:\Program Files\Git\cmd\git.exe'
    if (Test-Path $known) { return $known }

    Install-WithWinget -PackageId 'Git.Git' -DisplayName 'Git for Windows'

    $git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }
    if (Test-Path $known) { return $known }

    throw 'Git foi instalado, mas o executável não pôde ser localizado. Abra um novo terminal e execute novamente.'
}

function Test-PythonCandidate {
    param([string]$Executable, [string[]]$PrefixArgs = @())

    try {
        $script = 'import sys; print(sys.executable); print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'
        $result = & $Executable @PrefixArgs -c $script 2>$null
        if ($LASTEXITCODE -ne 0 -or $result.Count -lt 2) { return $null }

        $version = [Version]$result[-1]
        if ($version -lt [Version]'3.9.0') { return $null }

        return [PSCustomObject]@{
            Exe = $result[0]
            Version = $version
        }
    }
    catch {
        return $null
    }
}

function Resolve-Python {
    $python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($python) {
        $candidate = Test-PythonCandidate -Executable $python.Source
        if ($candidate) { return $candidate }
    }

    $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($selector in @('-3.14', '-3.13', '-3.12', '-3.11', '-3.10', '-3.9')) {
            $candidate = Test-PythonCandidate -Executable $py.Source -PrefixArgs @($selector)
            if ($candidate) { return $candidate }
        }
    }

    Install-WithWinget -PackageId 'Python.Python.3.14' -DisplayName 'Python 3.14'

    Refresh-PathEnvironment
    $python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($python) {
        $candidate = Test-PythonCandidate -Executable $python.Source
        if ($candidate) { return $candidate }
    }

    $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($py) {
        $candidate = Test-PythonCandidate -Executable $py.Source -PrefixArgs @('-3.14')
        if ($candidate) { return $candidate }
    }

    throw 'Python foi instalado, mas não pôde ser localizado. Abra um novo terminal e execute novamente.'
}

function Ensure-Pip {
    param([Parameter(Mandatory)] [string]$PythonExe)

    Write-Step 'Verificando pip...'
    & $PythonExe -m pip --version *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok 'pip disponível.'
        return
    }

    Write-Warn 'pip não encontrado. Tentando recuperar com ensurepip...'
    & $PythonExe -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        throw 'Não foi possível instalar o pip com ensurepip.'
    }

    & $PythonExe -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'pip continua indisponível após ensurepip.'
    }

    Write-Ok 'pip instalado.'
}

function Get-InstallInfo {
    if (Test-Path $Script:RegistryPath) {
        $item = Get-ItemProperty -Path $Script:RegistryPath
        return [PSCustomObject]@{
            InstallPath = $item.InstallPath
            Port = [int]$item.Port
            Access = $item.Access
            RepositoryUrl = $item.RepositoryUrl
            Branch = $item.Branch
        }
    }

    $service = Get-CimInstance Win32_Service -Filter "Name='$($Script:ServiceName)'" -ErrorAction SilentlyContinue
    if ($service -and $service.PathName) {
        $pathText = $service.PathName.Trim('"')
        $serviceDir = Split-Path $pathText -Parent
        $candidate = Split-Path $serviceDir -Parent
        if (Test-Path (Join-Path $candidate 'app.py')) {
            return [PSCustomObject]@{
                InstallPath = $candidate
                Port = 5000
                Access = 'Local'
                RepositoryUrl = $Script:RepoUrl
                Branch = $Script:Branch
            }
        }
    }

    if (Test-Path (Join-Path $Script:DefaultInstallPath 'app.py')) {
        return [PSCustomObject]@{
            InstallPath = $Script:DefaultInstallPath
            Port = 5000
            Access = 'Local'
            RepositoryUrl = $Script:RepoUrl
            Branch = $Script:Branch
        }
    }

    return $null
}

function Save-InstallInfo {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [int]$Port,
        [Parameter(Mandatory)] [string]$Access
    )

    if (-not (Test-Path $Script:RegistryPath)) {
        New-Item -Path $Script:RegistryPath -Force | Out-Null
    }

    New-ItemProperty -Path $Script:RegistryPath -Name 'InstallPath' -Value $Path -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $Script:RegistryPath -Name 'Port' -Value $Port -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $Script:RegistryPath -Name 'Access' -Value $Access -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $Script:RegistryPath -Name 'RepositoryUrl' -Value $Script:RepoUrl -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $Script:RegistryPath -Name 'Branch' -Value $Script:Branch -PropertyType String -Force | Out-Null
}

function Stop-EmprestimoService {
    $service = Get-Service -Name $Script:ServiceName -ErrorAction SilentlyContinue
    if (-not $service) { return }

    if ($service.Status -ne 'Stopped') {
        Write-Step 'Parando serviço Emprestimo...'
        Stop-Service -Name $Script:ServiceName -Force
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
        Write-Ok 'Serviço parado.'
    }
}

function Start-EmprestimoService {
    $service = Get-Service -Name $Script:ServiceName -ErrorAction Stop
    if ($service.Status -ne 'Running') {
        Write-Step 'Iniciando serviço Emprestimo...'
        Start-Service -Name $Script:ServiceName
        $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    }
    Write-Ok 'Serviço Emprestimo em execução.'
}

function Invoke-SqliteCheckpoint {
    param([Parameter(Mandatory)] [string]$Path)

    $db = Join-Path $Path 'data\emprestimos.db'
    $venvPython = Join-Path $Path '.venv\Scripts\python.exe'
    if (-not (Test-Path $db) -or -not (Test-Path $venvPython)) { return }

    try {
        $py = 'import sqlite3, sys; c=sqlite3.connect(sys.argv[1]); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.close()'
        & $venvPython -c $py $db *> $null
    }
    catch {
        Write-Warn "Não foi possível executar checkpoint SQLite: $($_.Exception.Message)"
    }
}

function Backup-Data {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [string]$Reason = 'manual'
    )

    $dataPath = Join-Path $Path 'data'
    if (-not (Test-Path $dataPath)) { return $null }

    Invoke-SqliteCheckpoint -Path $Path

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $destination = Join-Path $Script:BackupRoot "${timestamp}_${Reason}\data"
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath $dataPath -Force -ErrorAction SilentlyContinue |
        Copy-Item -Destination $destination -Recurse -Force -ErrorAction SilentlyContinue
    Write-Ok "Backup dos dados criado em: $destination"
    return $destination
}

function Ensure-RuntimeDirectories {
    param([Parameter(Mandatory)] [string]$Path)

    foreach ($dir in @('data', 'logs', 'service')) {
        New-Item -ItemType Directory -Path (Join-Path $Path $dir) -Force | Out-Null
    }

    # LocalService SID S-1-5-19; usa SID para não depender do idioma do Windows.
    & icacls.exe $Path /grant '*S-1-5-19:(OI)(CI)RX' /T /C *> $null
    & icacls.exe (Join-Path $Path 'data') /grant '*S-1-5-19:(OI)(CI)M' /T /C *> $null
    & icacls.exe (Join-Path $Path 'logs') /grant '*S-1-5-19:(OI)(CI)M' /T /C *> $null
}

function Install-PythonRequirements {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$SystemPython
    )

    $venvPython = Join-Path $Path '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Write-Step 'Criando ambiente virtual Python (.venv)...'
        & $SystemPython -m venv (Join-Path $Path '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente virtual.' }
    }

    Write-Step 'Atualizando pip do ambiente virtual...'
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar pip no ambiente virtual.' }

    Write-Step 'Instalando/atualizando dependências do projeto...'
    & $venvPython -m pip install -r (Join-Path $Path 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar requirements.txt.' }

    Write-Ok 'Dependências Python instaladas.'
}

function Test-ApplicationImport {
    param([Parameter(Mandatory)] [string]$Path)

    $venvPython = Join-Path $Path '.venv\Scripts\python.exe'
    Write-Step 'Validando importação da aplicação...'
    Push-Location $Path
    try {
        & $venvPython -c 'import app; print("Aplicacao importada com sucesso")'
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao importar app.py.' }
    }
    finally {
        Pop-Location
    }
    Write-Ok 'Aplicação Python válida.'
}

function Ensure-WinSW {
    param([Parameter(Mandatory)] [string]$Path)

    $serviceDir = Join-Path $Path 'service'
    New-Item -ItemType Directory -Path $serviceDir -Force | Out-Null
    $exe = Join-Path $serviceDir 'EmprestimoService.exe'

    $is64 = [Environment]::Is64BitOperatingSystem
    $arch = if ($is64) { 'x64' } else { 'x86' }
    $expectedHash = if ($is64) { $Script:WinSWX64Sha256 } else { $Script:WinSWX86Sha256 }
    $url = "https://github.com/winsw/winsw/releases/download/v$($Script:WinSWVersion)/WinSW-$arch.exe"

    $needDownload = $true
    if (Test-Path $exe) {
        $hash = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -eq $expectedHash) { $needDownload = $false }
    }

    if ($needDownload) {
        Write-Step "Baixando WinSW $($Script:WinSWVersion) ($arch)..."
        Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
        $hash = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $expectedHash) {
            Remove-Item $exe -Force -ErrorAction SilentlyContinue
            throw "SHA-256 do WinSW inválido. Download descartado. Obtido=$hash"
        }
        Write-Ok 'WinSW baixado e SHA-256 validado.'
    }

    return $exe
}

function Write-ServiceConfig {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [int]$Port,
        [Parameter(Mandatory)] [string]$Access
    )

    $listenHost = if ($Access -eq 'Rede') { '0.0.0.0' } else { '127.0.0.1' }
    $xmlPath = Join-Path $Path 'service\EmprestimoService.xml'

    $xml = @"
<service>
  <id>Emprestimo</id>
  <name>Emprestimo</name>
  <description>Sistema de Controle de Emprestimos - Flask/SQLite</description>
  <executable>%BASE%\..\.venv\Scripts\waitress-serve.exe</executable>
  <arguments>--listen=$listenHost`:$Port app:app</arguments>
  <workingdirectory>%BASE%\..</workingdirectory>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
  <serviceaccount>
    <username>NT AUTHORITY\LocalService</username>
  </serviceaccount>
  <onfailure action="restart" delay="5 sec"/>
  <onfailure action="restart" delay="15 sec"/>
  <resetfailure>1 hour</resetfailure>
  <logpath>%BASE%\..\logs</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>10</keepFiles>
  </log>
</service>
"@

    [IO.File]::WriteAllText($xmlPath, $xml, (New-Object Text.UTF8Encoding($false)))
    return $xmlPath
}

function Configure-Firewall {
    param(
        [Parameter(Mandatory)] [int]$Port,
        [Parameter(Mandatory)] [string]$Access
    )

    Get-NetFirewallRule -DisplayName "$($Script:FirewallRuleName)*" -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue

    if ($Access -eq 'Rede') {
        Write-Step "Liberando TCP $Port no Firewall para perfil de rede Privada..."
        New-NetFirewallRule -DisplayName "$($Script:FirewallRuleName) $Port" `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
        Write-Ok 'Regra de firewall criada.'
    }
}

function Create-Shortcut {
    param([Parameter(Mandatory)] [int]$Port)

    $content = @"
[InternetShortcut]
URL=http://localhost:$Port/
"@
    [IO.File]::WriteAllText($Script:ShortcutPath, $content, (New-Object Text.UTF8Encoding($false)))
    Write-Ok "Atalho criado: $($Script:ShortcutPath)"
}

function Install-ServiceWrapper {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [int]$Port,
        [Parameter(Mandatory)] [string]$Access
    )

    Ensure-RuntimeDirectories -Path $Path
    $serviceExe = Ensure-WinSW -Path $Path
    $null = Write-ServiceConfig -Path $Path -Port $Port -Access $Access

    $existing = Get-Service -Name $Script:ServiceName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Step 'Instalando serviço Windows Emprestimo...'
        & $serviceExe install
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o serviço Emprestimo.' }
    }

    # Reforça conta de baixo privilégio, inclusive para versões do wrapper que
    # eventualmente não apliquem serviceaccount como esperado.
    & sc.exe config $Script:ServiceName obj= 'NT AUTHORITY\LocalService' *> $null
    & sc.exe config $Script:ServiceName start= delayed-auto *> $null

    Configure-Firewall -Port $Port -Access $Access
    Create-Shortcut -Port $Port
    Start-EmprestimoService
}

function Test-HttpHealth {
    param([Parameter(Mandatory)] [int]$Port)

    Write-Step 'Testando endpoint /health...'
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -eq 200) {
            Write-Ok 'Aplicação respondeu HTTP 200.'
            return
        }
    }
    catch {
        Write-Warn "O serviço iniciou, mas o teste HTTP falhou: $($_.Exception.Message)"
        Write-Warn 'Verifique os arquivos na pasta logs e o serviço Emprestimo.'
        return
    }
}

function Install-Emprestimo {
    Write-Title 'INSTALAÇÃO - Sistema Emprestimo'

    $existingInfo = Get-InstallInfo
    if ($existingInfo) {
        Write-Warn "Uma instalação já foi encontrada em: $($existingInfo.InstallPath)"
        if (Ask-YesNo 'Deseja executar a atualização em vez de uma nova instalação?' $true) {
            Update-Emprestimo -Info $existingInfo
            return
        }
        throw 'Instalação cancelada para evitar sobrescrever uma instalação existente.'
    }

    $git = Resolve-Git
    Write-Ok "Git: $git"

    $python = Resolve-Python
    Write-Ok "Python $($python.Version): $($python.Exe)"
    Ensure-Pip -PythonExe $python.Exe

    $target = $InstallPath
    if ([string]::IsNullOrWhiteSpace($target)) {
        $entered = Read-Host "Pasta de instalação [$($Script:DefaultInstallPath)]"
        $target = if ([string]::IsNullOrWhiteSpace($entered)) { $Script:DefaultInstallPath } else { $entered.Trim() }
    }
    $target = [IO.Path]::GetFullPath($target)

    if (Test-Path $target) {
        $contents = Get-ChildItem -LiteralPath $target -Force -ErrorAction SilentlyContinue
        if ($contents) {
            throw "A pasta '$target' já existe e não está vazia. Escolha outra pasta ou remova o conteúdo manualmente."
        }
    }

    if (-not $Acesso) {
        Write-Host ''
        Write-Host 'Modo de acesso:' -ForegroundColor Cyan
        Write-Host '  1 - Somente neste computador (mais seguro)'
        Write-Host '  2 - Rede local (outros computadores poderão acessar a porta escolhida)'
        $choice = Read-Host 'Escolha [1]'
        $resolvedAccess = if ($choice.Trim() -eq '2') { 'Rede' } else { 'Local' }
    }
    else {
        $resolvedAccess = $Acesso
    }

    Write-Step "Clonando repositório em $target..."
    & $git clone --branch $Script:Branch --single-branch $Script:RepoUrl $target
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao clonar o repositório.' }

    Ensure-RuntimeDirectories -Path $target
    Install-PythonRequirements -Path $target -SystemPython $python.Exe
    Test-ApplicationImport -Path $target
    Install-ServiceWrapper -Path $target -Port $Porta -Access $resolvedAccess
    Save-InstallInfo -Path $target -Port $Porta -Access $resolvedAccess
    Test-HttpHealth -Port $Porta

    Write-Title 'INSTALAÇÃO CONCLUÍDA'
    Write-Host "Pasta:   $target"
    Write-Host "Serviço: $($Script:ServiceName)"
    Write-Host "URL local: http://localhost:$Porta/" -ForegroundColor Green

    if ($resolvedAccess -eq 'Rede') {
        $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Select-Object -ExpandProperty IPAddress -Unique
        foreach ($ip in $ips) {
            Write-Host "URL rede:  http://$ip`:$Porta/" -ForegroundColor Green
        }
    }
}

function Update-Emprestimo {
    param([object]$Info)

    Write-Title 'ATUALIZAÇÃO - Sistema Emprestimo'

    if (-not $Info) { $Info = Get-InstallInfo }
    if (-not $Info) { throw 'Instalação do Emprestimo não encontrada.' }

    $path = $Info.InstallPath
    if (-not (Test-Path (Join-Path $path '.git'))) {
        throw "A instalação encontrada em '$path' não contém um repositório Git."
    }

    $git = Resolve-Git
    $python = Resolve-Python
    Ensure-Pip -PythonExe $python.Exe

    Write-Step 'Consultando repositório remoto...'
    & $git -C $path fetch origin $Script:Branch --prune
    if ($LASTEXITCODE -ne 0) { throw 'Falha no git fetch.' }

    $current = (& $git -C $path rev-parse HEAD).Trim()
    $remote = (& $git -C $path rev-parse "origin/$($Script:Branch)").Trim()

    Write-Host "Commit instalado: $current"
    Write-Host "Commit remoto:    $remote"

    if ($current -eq $remote) {
        Write-Ok 'A instalação já está na mesma versão do repositório.'
        return
    }

    Write-Warn 'Há atualização disponível.'
    if (-not (Ask-YesNo 'Deseja aplicar a atualização agora?' $true)) {
        Write-Warn 'Atualização cancelada.'
        return
    }

    Stop-EmprestimoService
    $null = Backup-Data -Path $path -Reason 'pre-update'

    try {
        Write-Step 'Atualizando arquivos versionados...'
        & $git -C $path reset --hard "origin/$($Script:Branch)"
        if ($LASTEXITCODE -ne 0) { throw 'Falha no git reset.' }

        # Sem -x: arquivos ignorados como data, .venv, logs e service são preservados.
        & $git -C $path clean -fd
        if ($LASTEXITCODE -ne 0) { throw 'Falha no git clean.' }

        Ensure-RuntimeDirectories -Path $path
        Install-PythonRequirements -Path $path -SystemPython $python.Exe
        Test-ApplicationImport -Path $path
        $null = Ensure-WinSW -Path $path
        $null = Write-ServiceConfig -Path $path -Port $Info.Port -Access $Info.Access
        Configure-Firewall -Port $Info.Port -Access $Info.Access
        Create-Shortcut -Port $Info.Port
        Save-InstallInfo -Path $path -Port $Info.Port -Access $Info.Access
        Start-EmprestimoService
        Test-HttpHealth -Port $Info.Port
    }
    catch {
        Write-Warn "Falha durante atualização: $($_.Exception.Message)"
        Write-Warn 'O backup pré-atualização foi preservado.'
        try { Start-EmprestimoService } catch { }
        throw
    }

    $newCommit = (& $git -C $path rev-parse HEAD).Trim()
    Write-Title 'ATUALIZAÇÃO CONCLUÍDA'
    Write-Host "Novo commit: $newCommit" -ForegroundColor Green
}

function Uninstall-Emprestimo {
    Write-Title 'DESINSTALAÇÃO - Sistema Emprestimo'

    $info = Get-InstallInfo
    if (-not $info) {
        Write-Warn 'Instalação não encontrada no Registry, serviço ou pasta padrão.'
        return
    }

    $path = $info.InstallPath
    Write-Host "Instalação encontrada em: $path"

    if (-not (Ask-YesNo 'Confirma a desinstalação do sistema Emprestimo?' $false)) {
        Write-Warn 'Desinstalação cancelada.'
        return
    }

    Stop-EmprestimoService

    $keepData = Ask-YesNo 'Deseja manter uma cópia do banco de dados e dados locais?' $true
    $backupPath = $null
    if ($keepData -and (Test-Path $path)) {
        $backupPath = Backup-Data -Path $path -Reason 'uninstall'
    }

    $serviceExe = Join-Path $path 'service\EmprestimoService.exe'
    if (Test-Path $serviceExe) {
        Write-Step 'Removendo serviço Windows...'
        & $serviceExe uninstall
        if ($LASTEXITCODE -ne 0) {
            Write-Warn 'WinSW retornou erro ao desinstalar; tentando sc.exe delete.'
            & sc.exe delete $Script:ServiceName *> $null
        }
    }
    elseif (Get-Service -Name $Script:ServiceName -ErrorAction SilentlyContinue) {
        & sc.exe delete $Script:ServiceName *> $null
    }

    Get-NetFirewallRule -DisplayName "$($Script:FirewallRuleName)*" -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue

    Remove-Item -Path $Script:ShortcutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $Script:RegistryPath -Recurse -Force -ErrorAction SilentlyContinue

    if (Test-Path $path) {
        Write-Step 'Removendo arquivos instalados...'
        Remove-Item -LiteralPath $path -Recurse -Force
    }

    Write-Title 'DESINSTALAÇÃO CONCLUÍDA'
    if ($backupPath) {
        Write-Host "Dados preservados em: $backupPath" -ForegroundColor Green
    }
    else {
        Write-Host 'Os dados locais não foram preservados.' -ForegroundColor Yellow
    }
    Write-Host 'Python e Git não foram removidos porque podem ser utilizados por outros programas.'
}

function Show-Menu {
    Write-Title 'GERENCIADOR - Sistema Emprestimo'
    Write-Host '1 - Instalar'
    Write-Host '2 - Atualizar'
    Write-Host '3 - Desinstalar'
    Write-Host '0 - Sair'

    while ($true) {
        $choice = (Read-Host 'Escolha uma opção').Trim()
        switch ($choice) {
            '1' { return 'Instalar' }
            '2' { return 'Atualizar' }
            '3' { return 'Desinstalar' }
            '0' { return 'Sair' }
            default { Write-Warn 'Opção inválida.' }
        }
    }
}

try {
    Ensure-Administrator

    # Não atribui o retorno do menu diretamente a $Acao.
    # $Acao possui ValidateSet e PowerShell valida cada nova atribuição.
    $SelectedAction = $Acao

    if ([string]::IsNullOrWhiteSpace($SelectedAction)) {
        $SelectedAction = Show-Menu
    }

    if ($SelectedAction -eq 'Sair') {
        exit 0
    }

    switch ($SelectedAction) {
        'Instalar' { Install-Emprestimo }
        'Atualizar' { Update-Emprestimo }
        'Desinstalar' { Uninstall-Emprestimo }
        default { throw "Ação inválida: $SelectedAction" }
    }
}
catch {
    Write-Host ''
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    Read-Host 'Pressione ENTER para sair' | Out-Null
    exit 1
}

Write-Host ''
Read-Host 'Pressione ENTER para fechar' | Out-Null
