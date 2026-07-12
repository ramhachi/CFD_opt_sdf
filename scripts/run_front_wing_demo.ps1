$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\cfd-sdf.exe")) {
    & "$PSScriptRoot\bootstrap.ps1"
}

& ".\.venv\Scripts\cfd-sdf.exe" init examples\front_wing
& ".\.venv\Scripts\cfd-sdf.exe" clean examples\front_wing\project.yaml
& ".\.venv\Scripts\cfd-sdf.exe" build-sdf examples\front_wing\project.yaml
& ".\.venv\Scripts\cfd-sdf.exe" evaluate examples\front_wing\project.yaml
& ".\.venv\Scripts\cfd-sdf.exe" validate-outputs examples\front_wing\project.yaml

Write-Host ""
Write-Host "Demo complete."
Write-Host "Open in ParaView:"
Write-Host "  examples\front_wing\runs\front_wing_demo\sdf_fields.vti"
Write-Host "  examples\front_wing\runs\front_wing_demo\zero_surface.ply"
Write-Host "OpenFOAM case:"
Write-Host "  examples\front_wing\runs\front_wing_demo\openfoam_front_wing"
