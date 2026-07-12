$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\cfd-sdf.exe")) {
    & "$PSScriptRoot\bootstrap.ps1"
}

& ".\.venv\Scripts\cfd-sdf.exe" init examples\front_wing
& ".\.venv\Scripts\cfd-sdf.exe" optimize-parametric examples\front_wing\project.yaml --iterations 3 --voxel-size-m 0.08 --evaluator mock

Write-Host ""
Write-Host "Parametric optimization demo complete."
Write-Host "Summary:"
Write-Host "  examples\front_wing\runs\front_wing_demo\parametric_optimization\optimization_summary.json"
