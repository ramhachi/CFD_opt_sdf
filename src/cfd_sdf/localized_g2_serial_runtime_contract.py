"""Compiler-owned serial runtime contract for localized G2 evidence.

The module deliberately does *not* interpret OpenFOAM output.  It emits the
immutable names, units, conversion factor, mesh/order proof, and fresh
adjoint script that a later runtime/extractor must satisfy.  The declared
native response/gradient files are not produced here; their exporter remains
an explicit OpenFOAM-extension deliverable.
"""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from pathlib import Path
import os
import re
import stat
from typing import Any, Mapping

import numpy as np

from .openfoam_blockmesh_grid import OpenFoamBlockMeshGrid
from .openfoam_grid_transfer import CANONICAL_CELL_ORDER


LOCALIZED_G2_SERIAL_RUNTIME_SCHEMA_VERSION = 1
LOCALIZED_G2_SERIAL_RUNTIME_KIND = "localized_g2_serial_runtime_contract"
LOCALIZED_G2_SERIAL_RUNTIME_FILENAME = "localized_g2_serial_runtime.json"
LOCALIZED_G2_CELL_CENTRE_PROOF_FILENAME = "localized_g2_cell_centre_ordering.json"
LOCALIZED_G2_RESPONSE_GRADIENT_CONTRACT_FILENAME = "localized_g2_response_gradient_contract.json"
_PROCESSOR = re.compile(r"^processor[0-9]+$")


def emit_localized_g2_serial_runtime_contract(
    *,
    case_dir: Path,
    flow_case_id: str,
    response: Mapping[str, object],
    density_kg_m3: float,
    compilation_metadata_sha256: str,
    mesh: OpenFoamBlockMeshGrid,
) -> dict[str, object]:
    """Emit the narrow serial-only contract for exactly one force response.

    ``case_dir`` is still compiler-owned staging.  The caller writes the base
    compilation metadata first so contracts can bind its immutable hash
    without a metadata/contract hash cycle.
    """

    _require_id(flow_case_id, "flow_case_id")
    response_id = _require_id(response.get("response_id"), "response_id")
    if not isinstance(compilation_metadata_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", compilation_metadata_sha256):
        raise ValueError("compilation_metadata_sha256 must be a SHA-256 digest")
    rho = _positive(density_kg_m3, "density_kg_m3")
    area = _positive(response.get("Aref"), "response Aref")
    speed = _positive(response.get("UInf"), "response UInf")
    _reject_parallel_template_state(case_dir)
    parsed_mesh = mesh
    if parsed_mesh.grid.cell_order != CANONICAL_CELL_ORDER:
        raise ValueError("localized G2 serial runtime requires canonical x-fastest blockMesh cells")

    q_ref = 0.5 * rho * speed * speed
    factor = q_ref * area
    if not isfinite(factor) or factor <= 0.0:
        raise ValueError("localized G2 coefficient-to-force factor must be finite and positive")

    ordering = _cell_centre_ordering_proof(parsed_mesh)
    ordering_path = case_dir / LOCALIZED_G2_CELL_CENTRE_PROOF_FILENAME
    _write_json(ordering_path, ordering)
    ordering_sha = _sha256_file(ordering_path)

    script_path = case_dir / "AllrunAdjoint"
    command = ["adjointOptimisationFoam", "-case", "."]
    _write_adjoint_script(script_path, command=command)
    script_sha = _sha256_file(script_path)

    runtime = {
        "schema_version": LOCALIZED_G2_SERIAL_RUNTIME_SCHEMA_VERSION,
        "kind": LOCALIZED_G2_SERIAL_RUNTIME_KIND,
        "status": "compiled",
        "flow_case_id": flow_case_id,
        "response_id": response_id,
        "named_adjoint_id": f"resp_{response_id}",
        "compiler": {"compilation_metadata_sha256": compilation_metadata_sha256},
        "serial_execution": {
            "required": True,
            "decomposition": "forbidden",
            "forbidden_runtime_directory_pattern": "processor[0-9]+",
            "forbidden_commands": ["decomposePar", "reconstructPar", "mpirun", "-parallel"],
            "template_audit": "pass",
        },
        "block_mesh": {
            "path": "system/blockMeshDict",
            "sha256": parsed_mesh.block_mesh_sha256,
            "grid_sha256": parsed_mesh.grid_sha256,
            "cell_count": parsed_mesh.grid.cell_count,
            "cell_shape": list(parsed_mesh.grid.cell_shape),
            "origin_m": list(parsed_mesh.grid.origin),
            "spacing_m": list(parsed_mesh.grid.spacing),
            "cell_order": CANONICAL_CELL_ORDER,
        },
        "cell_centre_ordering_proof": {
            "path": LOCALIZED_G2_CELL_CENTRE_PROOF_FILENAME,
            "sha256": ordering_sha,
            "status": "proved",
        },
        "adjoint_script": {
            "path": "AllrunAdjoint",
            "sha256": script_sha,
            "command": command,
            "line_endings": "LF",
            "executable_owner_bit": bool(script_path.stat().st_mode & stat.S_IXUSR),
            "alpha_guard": "strict_openfoam_alpha_codec_values_sha256",
        },
        "execution_qualification": "not_run",
        "limitations": [
            "declares_but_does_not_implement_native_raw_alpha_gradient_export",
            "does_not_qualify_openfoam_execution_or_fd_agreement",
        ],
    }
    runtime_path = case_dir / LOCALIZED_G2_SERIAL_RUNTIME_FILENAME
    _write_json(runtime_path, runtime)
    runtime_sha = _sha256_file(runtime_path)

    conversion = {
        "kind": "coefficient_to_force_N",
        "factor": factor,
        "conversion": "q_ref_times_area",
        "q_ref_pa": q_ref,
        "density_kg_m3": rho,
        "speed_mps": speed,
        "area_m2": area,
    }
    contract = {
        "schema_version": 2,
        "kind": "localized_g2_openfoam_response_gradient_contract",
        "status": "compiled",
        "flow_case_id": flow_case_id,
        "response_id": response_id,
        "named_adjoint_id": f"resp_{response_id}",
        "compiler": {
            "compilation_metadata_sha256": compilation_metadata_sha256,
            "serial_runtime_sha256": runtime_sha,
        },
        "cfd_grid_sha256": parsed_mesh.grid_sha256,
        "cfd_cell_count": parsed_mesh.grid.cell_count,
        "cell_order": CANONICAL_CELL_ORDER,
        "block_mesh_sha256": parsed_mesh.block_mesh_sha256,
        "primal_response": {
            "source": {
                "relative_path_template": "postProcessing/cfdSdfLocalizedG2/{final_time}/response_coefficient.json",
                "format": "json",
                "json_pointer": "/coefficient",
            },
            "units": "N",
            "scale": conversion,
            "final_time_selection": "recorded_attempt_final_time",
        },
        "adjoint_gradient": {
            "source": {
                "relative_path_template": "postProcessing/cfdSdfLocalizedG2/{final_time}/d_coefficient_d_raw_alpha.npy",
                "format": "npy",
            },
            "variable": "raw_alpha",
            "meaning": "dJ=sum_i g_alpha[i]*d(alpha_i)",
            "units": "N",
            "scale": conversion,
            "final_time_selection": "recorded_attempt_final_time",
            "decomposition": {"kind": "single_case_canonical_x_fastest", "global_cell_order": CANONICAL_CELL_ORDER},
        },
    }
    _write_json(case_dir / LOCALIZED_G2_RESPONSE_GRADIENT_CONTRACT_FILENAME, contract)
    return runtime


def _reject_parallel_template_state(case_dir: Path) -> None:
    forbidden_dirs = [item.name for item in case_dir.iterdir() if item.is_dir() and _PROCESSOR.fullmatch(item.name)]
    if forbidden_dirs:
        raise ValueError("localized G2 serial runtime rejects processor directories: " + ", ".join(sorted(forbidden_dirs)))
    for name in ("Allrun", "Allclean"):
        path = case_dir / name
        text = path.read_text(encoding="utf-8")
        forbidden = [token for token in ("decomposePar", "reconstructPar", "mpirun", "-parallel") if token in text]
        if forbidden:
            raise ValueError(f"localized G2 serial runtime rejects parallel command(s) in {name}: " + ", ".join(forbidden))


def _cell_centre_ordering_proof(mesh: OpenFoamBlockMeshGrid) -> dict[str, object]:
    grid = mesh.grid
    nx, ny, nz = grid.cell_shape
    count = grid.cell_count
    digest = hashlib.sha256()
    chunk = 262144
    for start in range(0, count, chunk):
        labels = np.arange(start, min(start + chunk, count), dtype=np.int64)
        i = labels % nx
        j = (labels // nx) % ny
        k = labels // (nx * ny)
        centres = np.empty((labels.size, 3), dtype="<f8")
        centres[:, 0] = grid.origin[0] + grid.spacing[0] * (i + 0.5)
        centres[:, 1] = grid.origin[1] + grid.spacing[1] * (j + 0.5)
        centres[:, 2] = grid.origin[2] + grid.spacing[2] * (k + 0.5)
        digest.update(centres.tobytes(order="C"))
    probes = sorted({0, 1 if count > 1 else 0, nx - 1, nx, nx * ny - 1, nx * ny, count - 1})
    records = []
    for label in probes:
        if not 0 <= label < count:
            continue
        i, j, k = label % nx, (label // nx) % ny, label // (nx * ny)
        records.append({"linear_index": label, "ijk": [int(i), int(j), int(k)], "centre_m": [grid.origin[0] + grid.spacing[0] * (i + 0.5), grid.origin[1] + grid.spacing[1] * (j + 0.5), grid.origin[2] + grid.spacing[2] * (k + 0.5)]})
    return {
        "schema_version": 1,
        "kind": "localized_g2_cell_centre_x_fastest_proof",
        "status": "proved",
        "block_mesh_sha256": mesh.block_mesh_sha256,
        "grid_sha256": grid.sha256,
        "cell_count": count,
        "cell_order": CANONICAL_CELL_ORDER,
        "linear_index_rule": "i=index%nx; j=(index//nx)%ny; k=index//(nx*ny)",
        "centre_rule": "origin_m + spacing_m*(ijk + 0.5)",
        "float64_le_c_order_sha256": digest.hexdigest(),
        "probes": records,
    }


def _write_adjoint_script(path: Path, *, command: list[str]) -> None:
    # This uses only Python's standard library inside the OpenFOAM image.  It
    # validates the same canonical little-endian float64 value hash that the
    # strict alpha codec records, then proves the copied runtime field is exact.
    text = """#!/bin/sh
set -eu
case_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$case_dir"
if find . -maxdepth 1 -type d -name 'processor[0-9]*' -print -quit | grep -q .; then
    echo 'localized G2 serial runtime refuses processor directories' >&2
    exit 64
fi
expected_alpha_sha256=$(python3 - <<'PY'
import json
with open('localized_openfoam_alpha_case.json', encoding='utf-8') as handle:
    data = json.load(handle)
value = data['alpha_source']['values_sha256']
if not isinstance(value, str) or len(value) != 64:
    raise SystemExit('invalid staged alpha hash')
print(value)
PY
)
actual_alpha_sha256=$(python3 - <<'PY'
import hashlib
import re
import struct
text = open('0.orig/alpha', encoding='utf-8').read()
match = re.search(r'internalField\\s+nonuniform\\s+List<scalar>\\s+([0-9]+)\\s*\\((.*?)\\)\\s*;', text, re.S)
if match is None:
    raise SystemExit('0.orig/alpha is not a strict nonuniform scalar field')
count = int(match.group(1))
numbers = re.findall(r'[-+]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][-+]?[0-9]+)?', match.group(2))
if len(numbers) != count:
    raise SystemExit('0.orig/alpha count mismatch')
digest = hashlib.sha256()
for item in numbers:
    digest.update(struct.pack('<d', float(item)))
print(digest.hexdigest())
PY
)
[ "$actual_alpha_sha256" = "$expected_alpha_sha256" ] || { echo 'localized G2 alpha hash mismatch' >&2; exit 65; }
mkdir -p 0
cp 0.orig/alpha 0/alpha
cmp -s 0.orig/alpha 0/alpha || { echo 'localized G2 alpha copy mismatch' >&2; exit 66; }
exec adjointOptimisationFoam -case .
"""
    if "\r" in text:
        raise AssertionError("generated AllrunAdjoint must use LF")
    path.write_bytes(text.encode("utf-8"))
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _positive(value: object, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a positive finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a positive finite number") from exc
    if not isfinite(result) or result <= 0.0:
        raise ValueError(f"{context} must be a positive finite number")
    return result


def _require_id(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) is None:
        raise ValueError(f"{context} must be a safe non-empty identifier")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


__all__ = [
    "LOCALIZED_G2_CELL_CENTRE_PROOF_FILENAME",
    "LOCALIZED_G2_RESPONSE_GRADIENT_CONTRACT_FILENAME",
    "LOCALIZED_G2_SERIAL_RUNTIME_FILENAME",
    "LOCALIZED_G2_SERIAL_RUNTIME_KIND",
    "emit_localized_g2_serial_runtime_contract",
]
