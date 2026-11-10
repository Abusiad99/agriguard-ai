<#
.SYNOPSIS
  Outbreak-risk dataset and model pipeline.

.PARAMETER Action
  validate    check datasets\outbreak\raw (writes reports\validation_summary.md)
  preprocess  build processed\training_table.csv + manifests\dataset_manifest.json
  train       train the risk model (refuses below the data minimums in configs\outbreak\default.json)
  evaluate    evaluate the served model on the latest (held-out) period
  import      load raw\observations.csv into the app database (for the risk map)
  backfill    add map observations for existing scans that have an opted-in location
  status      show the model registry entry

.PARAMETER Extra
  Extra arguments for the Python module, e.g. -Extra '--config "C:\path\outbreak.json"'.
  The dataset folder follows $env:AGRIGUARD_DATASETS_DIR (default: datasets\ in the repo).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action validate
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "preprocess", "train", "evaluate", "import", "backfill", "status")]
    [string]$Action,
    [string]$Extra = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv
$extraArgs = Split-ExtraArgs $Extra

if ($Action -in @("import", "backfill")) {
    Assert-EnvFile
    Push-Location $BackendDir
    try {
        Write-Step "python -m app.tools.outbreak_data $Action $Extra"
        & $VenvPython -m app.tools.outbreak_data $Action @extraArgs
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    exit $code
}

Push-Location $RepoRoot
try {
    if ($Action -eq "status") {
        & $VenvPython -c "import json; from ai import registry; print(json.dumps(registry.describe('outbreak').public_dict(), indent=2))"
    } else {
        Write-Step "python -m ai.outbreak.$Action $Extra"
        & $VenvPython -m "ai.outbreak.$Action" @extraArgs
    }
    $code = $LASTEXITCODE
} finally { Pop-Location }
exit $code
