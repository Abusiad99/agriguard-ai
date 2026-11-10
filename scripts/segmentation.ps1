<#
.SYNOPSIS
  Disease-localization (segmentation) dataset and model pipeline.

.PARAMETER Action
  validate    check datasets\segmentation (writes reports\validation_summary.md)
  preprocess  validate, then build processed\ + splits\ + manifests\dataset_manifest.json
  train       train a model (long-running; never started automatically). Extra args are passed on,
              e.g. -Extra "--epochs 30 --device cuda"
  evaluate    evaluate the served model on the test split
  status      show the model registry entry

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action validate
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "preprocess", "train", "evaluate", "status")]
    [string]$Action,
    [string]$Extra = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv

$module = @{ validate = "ai.segmentation.validate"; preprocess = "ai.segmentation.preprocess";
             train = "ai.segmentation.train"; evaluate = "ai.segmentation.evaluate" }[$Action]
$extraArgs = Split-ExtraArgs $Extra

Push-Location $RepoRoot
try {
    if ($Action -eq "status") {
        & $VenvPython -c "import json; from ai import registry; print(json.dumps(registry.describe('segmentation').public_dict(), indent=2))"
    } else {
        Write-Step "python -m $module $Extra"
        & $VenvPython -m $module @extraArgs
    }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
