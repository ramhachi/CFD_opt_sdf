$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\cfd-sdf.exe")) {
    & "$PSScriptRoot\bootstrap.ps1"
}

& ".\.venv\Scripts\cfd-sdf.exe" init examples\front_wing
& ".\.venv\Scripts\cfd-sdf.exe" run-optimization examples\front_wing\project.yaml --mode topology --iterations 3 --voxel-size-m 0.08 --evaluator openfoam-dry-run

Write-Host ""
Write-Host "Practical optimization demo complete."
Write-Host "Summary:"
Write-Host "  examples\front_wing\runs\front_wing_demo\practical_optimization\runner_summary.json"
Write-Host "Progress:"
Write-Host "  examples\front_wing\runs\front_wing_demo\practical_optimization\progress.json"
Write-Host "Best design:"
Write-Host "  examples\front_wing\runs\front_wing_demo\practical_optimization\best_design"
