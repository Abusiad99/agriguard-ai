<#
.SYNOPSIS
  Longitudinal recovery dataset tools.

.PARAMETER Action
  validate    check datasets\recovery (writes reports\validation_report.json)
  calibrate   evaluate the recovery rules against labeled pairs and recommend thresholds
              (writes reports\calibration_report.json; never edits configs\recovery\rules.json)

.PARAMETER Extra
  Extra arguments for the Python module, e.g. -Extra '--dataset "D:\data\recovery"'.
  The dataset folder follows $env:AGRIGUARD_DATASETS_DIR (default: datasets\ in the repo).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action validate
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "calibrate")]
    [string]$Action,
    [string]$Extra = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv
$extraArgs = Split-ExtraArgs $Extra

Push-Location $RepoRoot
try {
    if ($Action -eq "validate") {
        & $VenvPython -m ai.recovery.dataset validate @extraArgs
    } else {
        & $VenvPython -m ai.recovery.calibrate @extraArgs
    }
    $code = $LASTEXITCODE
} finally { Pop-Location }
exit $code
