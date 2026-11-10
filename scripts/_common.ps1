# Shared helpers for the AgriGuard AI development scripts. Dot-source it:
#   . "$PSScriptRoot\_common.ps1"
# Compatible with Windows PowerShell 5.1 and PowerShell 7. Keep this file ASCII-only:
# PowerShell 5.1 reads BOM-less files in the system code page.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$RunDir = Join-Path $RepoRoot ".run"
$LogDir = Join-Path $RepoRoot "logs"

# Virtual environment location. Override with $env:AGRIGUARD_VENV, e.g. when the
# repository sits in a deep folder and Windows path-length limits break pip.
if ($env:AGRIGUARD_VENV) { $VenvDir = $env:AGRIGUARD_VENV } else { $VenvDir = Join-Path $RepoRoot ".venv" }
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# Make both the backend `app` package and the repo-root `ai` package importable.
$env:PYTHONPATH = "$RepoRoot;$BackendDir"
$env:PYTHONUTF8 = "1"

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "    OK  $Message" -ForegroundColor Green
}

function Fail([string]$Message) {
    Write-Host "    ERROR  $Message" -ForegroundColor Red
    exit 1
}

function Assert-Venv {
    if (-not (Test-Path $VenvPython)) {
        Fail "Python environment not found at $VenvDir. Run scripts\install-backend.ps1 first."
    }
}

function Assert-EnvFile {
    if (-not ((Test-Path (Join-Path $RepoRoot ".env")) -or (Test-Path (Join-Path $BackendDir ".env")))) {
        Fail "No .env found. Run scripts\install-backend.ps1 (it creates one from .env.example)."
    }
}

function Join-ProcessArguments([string[]]$Arguments) {
    # Windows PowerShell 5.1's Start-Process joins -ArgumentList with spaces and does
    # not quote, so a path like "C:\Users\Jane Doe\..." would split in two.
    $quoted = foreach ($a in $Arguments) { if ($a -match '\s') { '"' + $a + '"' } else { $a } }
    return ($quoted -join " ")
}

function Start-BackgroundCommand([string]$Exe, [string[]]$Arguments, [string]$WorkingDirectory,
                                 [string]$OutLog, [string]$ErrLog) {
    # Runs `Exe Arguments > OutLog 2> ErrLog` hidden, via cmd.exe. The redirection is
    # done by cmd rather than Start-Process -RedirectStandardOutput, which would make
    # the server inherit this script's handles and keep a calling pipeline (CI, a
    # parent script) from ever finishing. Returns the cmd.exe process; stop-dev.ps1
    # stops it together with its children.
    $command = '"' + $Exe + '" ' + (Join-ProcessArguments $Arguments) + ' > "' + $OutLog + '" 2> "' + $ErrLog + '"'
    return Start-Process -FilePath "cmd.exe" -ArgumentList "/d /s /c `"$command`"" `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
}

function Test-PortInUse([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return [bool]$listener
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            return $response.StatusCode
        } catch {
            if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
            Start-Sleep -Milliseconds 500
        }
    }
    return 0
}

# PID files record the process id AND its start time, so stop-dev.ps1 never kills an
# unrelated process that later reused the same id.
function Save-ProcessRecord([string]$Name, [System.Diagnostics.Process]$Process) {
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $record = @{ pid = $Process.Id; started = $Process.StartTime.ToString("o"); name = $Process.ProcessName }
    $record | ConvertTo-Json | Set-Content -Encoding ASCII -Path (Join-Path $RunDir "$Name.json")
}

function Get-ProcessRecord([string]$Name) {
    $path = Join-Path $RunDir "$Name.json"
    if (-not (Test-Path $path)) { return $null }
    return Get-Content $path -Raw | ConvertFrom-Json
}

function Get-RecordedProcess([string]$Name) {
    # The live process for a record, or $null if it has exited or the id was reused.
    $record = Get-ProcessRecord $Name
    if ($null -eq $record) { return $null }
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    if ($process.StartTime.ToString("o") -ne $record.started) { return $null }
    return $process
}

function Remove-ProcessRecord([string]$Name) {
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $RunDir "$Name.json")
}

# Stop a dev server started by start-backend.ps1 / start-frontend.ps1, with its child
# processes (Uvicorn's reloader, Vite under npm). Only the process recorded in .run\
# is stopped, and only while its id still belongs to it - never by name.
# Returns: not-started | already-stopped | stopped | failed
function Stop-DevProcess([string]$Name) {
    if ($null -eq (Get-ProcessRecord $Name)) { return "not-started" }
    $process = Get-RecordedProcess $Name
    if ($null -eq $process) {
        Remove-ProcessRecord $Name
        return "already-stopped"
    }
    & taskkill.exe /PID $process.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) { return "failed" }
    Remove-ProcessRecord $Name
    return "stopped"
}

# Split an -Extra "..." string into arguments. Double quotes group words, so paths with
# spaces work: -Extra '--config "C:\My Data\seg.json" --epochs 30'.
function Split-ExtraArgs([string]$Extra) {
    if (-not $Extra) { return @() }
    return @([regex]::Matches($Extra, '"([^"]*)"|(\S+)') | ForEach-Object {
        if ($_.Groups[1].Success) { $_.Groups[1].Value } else { $_.Groups[2].Value }
    })
}
