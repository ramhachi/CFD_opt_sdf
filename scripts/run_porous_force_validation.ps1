param(
    [string]$DockerImage = "opencfd/openfoam-default:2512",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OpenFoamRoot = "/usr/lib/openfoam/openfoam2512"
$LibraryDir = "/work/openfoam_extensions/porousDirectionalForce/lib"
$CaseRoot = Join-Path $Root "examples\fixed_grid_backend_spike\openfoam"
$ReportDir = Join-Path $Root "examples\fixed_grid_backend_spike\report\3d"
$Cli = Join-Path $Root ".venv\Scripts\cfd-sdf.exe"

if (-not (Test-Path $Cli)) {
    throw "Python environment is missing. Run scripts\bootstrap.ps1 first."
}

function Invoke-OpenFoam {
    param(
        [string]$WorkingDirectory,
        [string]$Command
    )

    $ShellCommand = @"
source $OpenFoamRoot/etc/bashrc
export FOAM_USER_LIBBIN=$LibraryDir
export LD_LIBRARY_PATH=${LibraryDir}:`$LD_LIBRARY_PATH
$Command
"@
    & docker run --rm --entrypoint bash `
        -v "${Root}:/work" `
        -w $WorkingDirectory `
        $DockerImage `
        -lc $ShellCommand
    if ($LASTEXITCODE -ne 0) {
        throw "OpenFOAM command failed in $WorkingDirectory with exit code $LASTEXITCODE."
    }
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build_porous_force_objective.ps1") -DockerImage $DockerImage
}

$Cases = @(
    "porous_force_3d_fd_base",
    "porous_force_3d_fd_plus",
    "porous_force_3d_fd_minus"
)

foreach ($CaseName in $Cases) {
    $ContainerCase = "/work/examples/fixed_grid_backend_spike/openfoam/$CaseName"
    Invoke-OpenFoam -WorkingDirectory $ContainerCase -Command "bash ./Allclean"
    Invoke-OpenFoam -WorkingDirectory $ContainerCase -Command "bash ./Allrun"
}

$BaseContainerCase = "/work/examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base"
Invoke-OpenFoam -WorkingDirectory $BaseContainerCase -Command "reconstructPar -latestTime -no-libs"
Invoke-OpenFoam `
    -WorkingDirectory $BaseContainerCase `
    -Command 'foamToVTK -no-libs -time "0,1" -fields "(alpha alphaTilda topOSensas1 topOSensdownforce topologySensas1 topologySensdownforce beta U p)"'

$Base = Join-Path $CaseRoot "porous_force_3d_fd_base"
$Plus = Join-Path $CaseRoot "porous_force_3d_fd_plus"
$Minus = Join-Path $CaseRoot "porous_force_3d_fd_minus"

& $Cli validate-porous-force-gradient `
    $Base $Plus $Minus `
    --output-dir $ReportDir `
    --epsilon 0.005 `
    --objective-name drag `
    --sensitivity-array topOSensas1 `
    --relative-error-tolerance 0.1
if ($LASTEXITCODE -ne 0) {
    throw "Drag gradient validation failed."
}

$DownforceReportDir = Join-Path $ReportDir "downforce"
& $Cli validate-porous-force-gradient `
    $Base $Plus $Minus `
    --output-dir $DownforceReportDir `
    --epsilon 0.005 `
    --objective-name downforce `
    --sensitivity-array topOSensdownforce `
    --relative-error-tolerance 0.1
if ($LASTEXITCODE -ne 0) {
    throw "Strict three-dimensional downforce gradient validation failed."
}

$EfficiencyReportDir = Join-Path $ReportDir "efficiency"
& $Cli validate-efficiency-gradient `
    $Base $Plus $Minus `
    --output-dir $EfficiencyReportDir `
    --efficiency-min 3.0 `
    --epsilon 0.005 `
    --downforce-objective-name downforce `
    --downforce-sensitivity-array topOSensdownforce `
    --relative-error-tolerance 0.1
if ($LASTEXITCODE -ne 0) {
    throw "Efficiency-constraint gradient validation failed."
}

& $Cli probe-fixed-grid-backend `
    (Join-Path $CaseRoot "porosity_based_R10x_init") `
    --output-dir $ReportDir `
    --porous-force-validation-json (Join-Path $ReportDir "porous_force_gradient_validation.json") `
    --downforce-validation-json (Join-Path $DownforceReportDir "porous_force_gradient_validation.json") `
    --efficiency-validation-json (Join-Path $EfficiencyReportDir "efficiency_constraint_gradient_validation.json")
if ($LASTEXITCODE -ne 0) {
    throw "Fixed-grid backend probe failed."
}

$SummaryPath = Join-Path $ReportDir "fixed_grid_backend_probe_summary.json"
$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
if ($Summary.overall_status -notin @("pass", "pass_t0")) {
    throw "T0 backend gate did not pass. Status: $($Summary.overall_status)"
}

$ContractDir = Join-Path $ReportDir "t1_contract"
& $Cli build-fixed-grid-contract `
    $Base `
    --output-dir $ContractDir `
    --efficiency-min 3.0 `
    --docker-image $DockerImage `
    --solver-version 2512 `
    --drag-validation-json (Join-Path $ReportDir "porous_force_gradient_validation.json") `
    --downforce-validation-json (Join-Path $DownforceReportDir "porous_force_gradient_validation.json") `
    --efficiency-validation-json (Join-Path $EfficiencyReportDir "efficiency_constraint_gradient_validation.json")
if ($LASTEXITCODE -ne 0) {
    throw "T1 fixed-grid contract build failed."
}

& $Cli validate-fixed-grid-contract `
    (Join-Path $ContractDir "topology_state.json")
if ($LASTEXITCODE -ne 0) {
    throw "T1 fixed-grid contract validation failed."
}

Write-Host "Validation reports: $ReportDir"
