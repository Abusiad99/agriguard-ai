<#
.SYNOPSIS
  Install the backend (FastAPI) and AI pipeline Python dependencies into a virtual
  environment, and create .env from .env.example if it does not exist yet.

.PARAMETER SkipAi
  Skip the AI pipeline packages (PyTorch, timm, ...). The API still runs, but
  POST /api/v1/scans answers 503 until they are installed and a model is trained.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install-backend.ps1
#>
param([switch]$SkipAi)

. "$PSScriptRoot\_common.ps1"

Write-Step "Locating Python 3.10+"
$python = $null
foreach ($candidate in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python"))) {
    $exe = $candidate[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $launcherArgs = @($candidate | Select-Object -Skip 1)
    # A missing version makes the py launcher write to stderr; don't let that abort.
    $ErrorActionPreference = "Continue"
    $version = & $exe @launcherArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -eq 0 -and $version -and ([version]$version -ge [version]"3.10")) {
        $python = $candidate
        Write-Ok "Python $version ($($candidate -join ' '))"
        break
    }
}
if ($null -eq $python) { Fail "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/windows/ and re-run." }

if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating virtual environment at $VenvDir"
    $exe = $python[0]
    $launcherArgs = @($python | Select-Object -Skip 1)
    & $exe @launcherArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
} else {
    Write-Ok "Virtual environment exists at $VenvDir"
}

Write-Step "Upgrading pip"
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }

Write-Step "Installing backend requirements (backend\requirements.txt)"
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $BackendDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Backend requirements failed to install." }

if ($SkipAi) {
    Write-Host "    Skipping AI pipeline requirements (-SkipAi). Scans will return 503." -ForegroundColor Yellow
} else {
    Write-Step "Installing AI pipeline requirements (ai\requirements.txt; PyTorch is a large download)"
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $RepoRoot "ai\requirements.txt")
    if ($LASTEXITCODE -ne 0) { Fail "AI requirements failed to install." }
}

$envFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Step "Creating .env from .env.example with a random JWT secret"
    $secret = & $VenvPython -c "import secrets; print(secrets.token_urlsafe(48))"
    # Read as UTF-8 explicitly: Windows PowerShell 5.1's Get-Content would use the ANSI code page.
    $content = [System.IO.File]::ReadAllText((Join-Path $RepoRoot ".env.example"), [System.Text.Encoding]::UTF8)
    $content = $content -replace "(?m)^JWT_SECRET_KEY=.*$", "JWT_SECRET_KEY=$secret"
    [System.IO.File]::WriteAllText($envFile, $content, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok "Created .env - now replace YOUR_DB_PASSWORD in DATABASE_URL with your PostgreSQL password"
} else {
    Write-Ok ".env already exists (left unchanged)"
}

Write-Host ""
Write-Host "Backend dependencies installed. Next:" -ForegroundColor Green
Write-Host "  scripts\check-db.ps1      # verify PostgreSQL is reachable"
Write-Host "  scripts\migrate.ps1       # create/upgrade the database schema"
Write-Host "  scripts\start-backend.ps1 # http://127.0.0.1:8000/api/docs"
