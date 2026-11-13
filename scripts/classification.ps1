<#
.SYNOPSIS
  Plant-disease classification dataset and model pipeline.

.PARAMETER Action
  validate    check the images under datasets\ (read-only). Add -Extra "--full" to decode
              every image and count duplicates.
  train       train the classifier (long-running; never started automatically). Settings are
              environment variables, e.g. $env:AGRIGUARD_DEVICE = "cuda" (see ai\config.py)
  evaluate    evaluate the latest trained model on the held-out test split
  status      show the model registry entry (is a trained model available?)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action validate
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "train", "evaluate", "status")]
    [string]$Action,
    [string]$Extra = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Venv

$extraArgs = Split-ExtraArgs $Extra

Push-Location $RepoRoot
try {
    if ($Action -eq "status") {
        & $VenvPython -c "import json; from ai import registry; print(json.dumps(registry.describe('classification').public_dict(), indent=2))"
    } elseif ($Action -eq "validate") {
        Write-Step "python -m ai.data.validate_dataset $Extra"
        & $VenvPython -m ai.data.validate_dataset @extraArgs
    } else {
        $script = @{ train = "train.py"; evaluate = "evaluate.py" }[$Action]
        Write-Step "python $script $Extra"
        & $VenvPython $script @extraArgs
    }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
