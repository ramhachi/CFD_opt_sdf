#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Docker Desktop does not always put its credential helper on the shell PATH.
if [[ -d /Applications/Docker.app/Contents/Resources/bin ]]; then
    export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
fi

docker run --rm --entrypoint bash \
    --mount "type=bind,source=$PWD,target=/work" \
    -w /work/openfoam_extensions/porousDirectionalForce \
    "${CFD_SDF_OPENFOAM_IMAGE:-opencfd/openfoam-default:2512}" \
    -lc 'source /usr/lib/openfoam/openfoam2512/etc/bashrc || exit; set -e; export FOAM_USER_LIBBIN=/work/openfoam_extensions/porousDirectionalForce/lib; wmake libso'
