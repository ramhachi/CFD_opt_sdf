param(
    [Parameter(Mandatory=$true)][string]$Out,
    [string]$Julia = "julia"
)
# Native comparison arm only. It does not port or invoke the POSIX harness.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Project = Join-Path $Repo "julia/CFDSDFWaterLilyT4"
$Entry = Join-Path $PSScriptRoot "local_gpu_bench.jl"
if (Test-Path -LiteralPath $Out) { throw "Refusing to overwrite $Out" }
$env:CUDA_VISIBLE_DEVICES = "0"
& $Julia "--project=$Project" --startup-file=no $Entry --out $Out --host-label native_windows
if ($LASTEXITCODE -ne 0) { throw "R0 native benchmark exited with $LASTEXITCODE" }
