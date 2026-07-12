param(
    [string]$DockerImage = "opencfd/openfoam-default:2512"
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ContainerWorkDir = "/work/openfoam_extensions/porousDirectionalForce"
$BuildCommand = @'
source /usr/lib/openfoam/openfoam2512/etc/bashrc
export FOAM_USER_LIBBIN=/work/openfoam_extensions/porousDirectionalForce/lib
wmake libso
'@

& docker run --rm --entrypoint bash `
    -v "${Root}:/work" `
    -w $ContainerWorkDir `
    $DockerImage `
    -lc $BuildCommand

if ($LASTEXITCODE -ne 0) {
    throw "OpenFOAM porous-force objective build failed with exit code $LASTEXITCODE."
}

Write-Host "Built openfoam_extensions/porousDirectionalForce/lib/libcfdSdfPorousObjectives.so"
