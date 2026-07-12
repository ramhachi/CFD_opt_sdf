$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.10+ first."
}

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"

Write-Host ""
Write-Host "Environment ready."
Write-Host "Try:"
Write-Host "  .\.venv\Scripts\cfd-sdf.exe init examples\front_wing"
Write-Host "  .\.venv\Scripts\cfd-sdf.exe build-sdf examples\front_wing\project.yaml"
Write-Host "  .\.venv\Scripts\cfd-sdf.exe check-constraints examples\front_wing\project.yaml"
