<#
.SYNOPSIS
  Check the optional Gemini API key (GEMINI_API_KEY in .env) and model (GEMINI_MODEL)
  with one model-lookup request. No content is generated and the key is never printed.
  Restart the backend after changing .env; this check reads .env directly.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\check-gemini.ps1
#>
. "$PSScriptRoot\_common.ps1"
Assert-Venv
Assert-EnvFile

Write-Step "Checking the Gemini configuration in .env"
Push-Location $BackendDir
try { & $VenvPython (Join-Path $PSScriptRoot "check_gemini.py"); $code = $LASTEXITCODE } finally { Pop-Location }
switch ($code) {
    0 { Write-Ok "Gemini is configured" }
    2 { Write-Host "    Gemini is optional and currently disabled. To enable it, set GEMINI_API_KEY in .env (docs\SETUP_AND_RUN.md)." -ForegroundColor Yellow; exit 0 }
    default {
        Write-Host ""
        Write-Host "The check failed. Common causes:" -ForegroundColor Yellow
        Write-Host "  - API key not valid: create a new key at https://aistudio.google.com/apikey and update GEMINI_API_KEY"
        Write-Host "  - model not found: set GEMINI_MODEL to a current model (https://aistudio.google.com/docs/models)"
        Write-Host "  - HTTP 429: quota or rate limit reached; wait, or check your plan in Google AI Studio"
        Write-Host "  - network errors: this computer cannot reach generativelanguage.googleapis.com"
        exit 1
    }
}
