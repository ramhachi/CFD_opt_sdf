param(
    [Parameter(Mandatory=$true)][string]$Out,
    [Parameter(Mandatory=$true)][string]$Lock,
    [string]$Julia = "julia"
)
# Native comparison arm only. It does not port or invoke the POSIX harness.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Project = Join-Path $Repo "julia/CFDSDFWaterLilyT4"
$Entry = Join-Path $PSScriptRoot "local_gpu_bench.jl"
if (Test-Path -LiteralPath $Out) { throw "Refusing to overwrite $Out" }
if (!(Test-Path -LiteralPath $Lock -PathType Leaf)) { throw "Reference WSL2 lock missing: $Lock" }
$LockSha = (Get-FileHash -LiteralPath $Lock -Algorithm SHA256).Hash.ToLowerInvariant()
if ((Get-Content -LiteralPath "$Lock.sha256" -Raw).Trim() -cne $LockSha) { throw "Reference WSL2 lock SHA sidecar mismatch" }
# This SHA binds the WSL2 reference. Native Julia/Manifest identity is recorded
# separately; it does not assert that native Windows equals the WSL2 lock.
$OutParent = Split-Path -Parent ([IO.Path]::GetFullPath($Out))
[IO.Directory]::CreateDirectory($OutParent) | Out-Null
$env:CUDA_VISIBLE_DEVICES = "0"
$env:CUDA_DEVICE_ORDER = "PCI_BUS_ID"
$env:JULIA_NUM_THREADS = "1"
& $Julia "--project=$Project" --startup-file=no $Entry --out $Out --host-label native_windows --lock-sha256 $LockSha
if ($LASTEXITCODE -ne 0) { throw "R0 native benchmark exited with $LASTEXITCODE" }
