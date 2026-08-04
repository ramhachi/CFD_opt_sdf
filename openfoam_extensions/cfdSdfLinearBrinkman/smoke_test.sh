#!/usr/bin/env bash
# Minimal OpenCFD OpenFOAM v2512 runtime smoke for this project extension.
# OpenFOAM's environment script expects a few unset variables, so source it
# before enabling nounset.
source /usr/lib/openfoam/openfoam2512/etc/bashrc
set -euo pipefail

extension_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FOAM_USER_LIBBIN="${extension_dir}/lib"
export LD_LIBRARY_PATH="${FOAM_USER_LIBBIN}:${LD_LIBRARY_PATH:-}"

wmake libso

case_dir="$(mktemp -d)"
cleanup() { rm -rf "${case_dir}"; }
trap cleanup EXIT

cp -a "${FOAM_TUTORIALS}/incompressible/simpleFoam/pitzDaily/." "${case_dir}/"
cd "${case_dir}"

foamDictionary -entry endTime -set 1 system/controlDict
foamDictionary -entry writeInterval -set 1 system/controlDict
foamDictionary -entry functions -remove system/controlDict
foamDictionary -entry libs -set '("libcfdSdfLinearBrinkman.so")' system/controlDict

cat > 0/beta <<'EOF'
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      beta;
}
dimensions      [0 0 0 0 0 0 0];
internalField   uniform 0.1;
boundaryField
{
    inlet       { type zeroGradient; }
    outlet      { type zeroGradient; }
    upperWall   { type zeroGradient; }
    lowerWall   { type zeroGradient; }
    frontAndBack { type empty; }
}
EOF

cp "${extension_dir}/example_fvOptions" system/fvOptions

blockMesh > log.blockMesh 2>&1 || { cat log.blockMesh; exit 1; }
simpleFoam > log.simpleFoam 2>&1 || { cat log.simpleFoam; exit 1; }

grep -q "Creating finite-volume options" log.simpleFoam || { cat log.simpleFoam; exit 1; }
grep -q "porousCylinderResistance" log.simpleFoam || { cat log.simpleFoam; exit 1; }
test -f 1/brinkmanResistance
grep -q "internalField" 1/brinkmanResistance

echo "cfdSdfLinearBrinkman v2512 runtime smoke passed"
