$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\cfd-sdf.exe")) {
    & "$PSScriptRoot\bootstrap.ps1"
}

& ".\.venv\Scripts\cfd-sdf.exe" init examples\front_wing
& ".\.venv\Scripts\cfd-sdf.exe" explore-topology examples\front_wing\project.yaml --iterations 3 --voxel-size-m 0.08 --evaluator openfoam-dry-run

Write-Host ""
Write-Host "Topology exploration demo complete."
Write-Host "Summary:"
Write-Host "  examples\front_wing\runs\front_wing_demo\topology_exploration\topology_summary.json"
