"""Transfer a verified canonical Stage T density into OpenFOAM cell order.

The only state operation qualified here is the conservative Cartesian map
``source_rho = P @ canonical_rho``.  The module does not infer an inverse map,
convert density to Brinkman coefficients, or write an OpenFOAM field whose
boundary conditions would require solver-specific semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

import numpy as np

from .openfoam_blockmesh_grid import (
    OpenFoamBlockMeshGrid,
    read_openfoam_blockmesh_uniform_cartesian_grid,
)
from .openfoam_grid_transfer import (
    ExactCartesianOverlapTransfer,
    load_openfoam_cell_order_mapping,
)
from .stage_t_candidate_binding import (
    VerifiedStageTCandidateBinding,
    verify_stage_t_candidate_binding,
)


_ARTIFACT_KIND = "openfoam_canonical_state_transfer"
_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CanonicalStateTransferArtifacts:
    """Paths to one atomically written source-state transfer."""

    directory: Path
    fields_npz: Path
    provenance_json: Path


def transfer_and_write_openfoam_source_state(
    *,
    candidate_binding_json: str | Path,
    problem: str | Path,
    block_mesh_dict: str | Path,
    source_global_cell_labels_by_xfastest: str | Path,
    output_directory: str | Path,
) -> CanonicalStateTransferArtifacts:
    """Verify all disk inputs and write OpenFOAM-ordered source density."""

    verified = verify_stage_t_candidate_binding(candidate_binding_json, problem)
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(block_mesh_dict)
    return write_openfoam_source_state_transfer(
        verified_candidate=verified,
        source_mesh=source_mesh,
        source_global_cell_labels_by_xfastest=source_global_cell_labels_by_xfastest,
        output_directory=output_directory,
    )


def write_openfoam_source_state_transfer(
    *,
    verified_candidate: VerifiedStageTCandidateBinding,
    source_mesh: OpenFoamBlockMeshGrid,
    source_global_cell_labels_by_xfastest: str | Path,
    output_directory: str | Path,
) -> CanonicalStateTransferArtifacts:
    """Write ``P @ rho`` for already verified candidate and mesh objects."""

    if not isinstance(verified_candidate, VerifiedStageTCandidateBinding):
        raise ValueError("verified_candidate must be VerifiedStageTCandidateBinding")
    if not isinstance(source_mesh, OpenFoamBlockMeshGrid):
        raise ValueError("source_mesh must be OpenFoamBlockMeshGrid")
    binding = verified_candidate.binding
    candidate = _mapping(binding.get("candidate"), "candidate")
    problem = _mapping(binding.get("problem"), "problem")
    density = _mapping(binding.get("density"), "density")
    if problem.get("execution_ready") is not True:
        raise ValueError("verified candidate must bind an execution-ready ProblemSpec")
    rho_variant = density.get("array")
    if rho_variant not in {"rho", "rho_filtered", "rho_projected"}:
        raise ValueError("candidate density.array is not a supported rho variant")
    if rho_variant not in verified_candidate.density_arrays:
        raise ValueError(f"verified candidate is missing density array {rho_variant!r}")

    target_grid = verified_candidate.canonical_grid.snapshot.grid
    if target_grid.sha256 != verified_candidate.canonical_grid.snapshot.grid_sha256:
        raise ValueError("verified candidate canonical grid hash is inconsistent")
    if source_mesh.grid.sha256 != source_mesh.grid_sha256:
        raise ValueError("OpenFOAM source grid hash is inconsistent")
    canonical_rho = _rho(
        verified_candidate.density_arrays[rho_variant],
        target_grid.cell_count,
        f"candidate {rho_variant}",
    )
    transfer = ExactCartesianOverlapTransfer.build(
        source_grid=source_mesh.grid,
        target_grid=target_grid,
        source_active_mask=np.ones(source_mesh.grid.cell_count, dtype=bool),
        target_active_mask=np.ones(target_grid.cell_count, dtype=bool),
        expected_source_grid_sha256=source_mesh.grid_sha256,
        expected_target_grid_sha256=target_grid.sha256,
    )
    order_mapping = load_openfoam_cell_order_mapping(
        source_global_cell_labels_by_xfastest,
        cell_count=source_mesh.grid.cell_count,
    )
    source_rho_xfastest = transfer.transfer_state_to_source(canonical_rho)
    _rho(
        source_rho_xfastest,
        source_mesh.grid.cell_count,
        "transferred source rho",
    )
    source_rho_global = np.empty_like(source_rho_xfastest)
    source_rho_global[order_mapping.global_cell_labels_by_xfastest] = (
        source_rho_xfastest
    )
    payload = {
        "source_rho_xfastest": source_rho_xfastest,
        "source_rho_global_label": source_rho_global,
        "source_global_cell_labels_by_xfastest": (
            order_mapping.global_cell_labels_by_xfastest
        ),
    }
    provenance = {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "kind": _ARTIFACT_KIND,
        "status": "capability_only",
        "qualified": False,
        "candidate_binding": {
            "path": str(verified_candidate.path.resolve()),
            "sha256": _sha256_file(verified_candidate.path),
            "problem_id": problem.get("problem_id"),
            "problem_spec_sha256": problem.get("problem_spec_sha256"),
            "execution_ready": problem.get("execution_ready"),
            "candidate_id": candidate.get("candidate_id"),
            "parent_candidate_id": candidate.get("parent_candidate_id"),
            "iteration": candidate.get("iteration"),
        },
        "target": {
            "density_path": str(verified_candidate.density_vti_path.resolve()),
            "density_file_sha256": density.get("sha256"),
            "rho_variant": rho_variant,
            "rho_value_sha256": _array_sha256(canonical_rho),
            "grid_sha256": target_grid.sha256,
            "cell_count": target_grid.cell_count,
            "cell_order": target_grid.cell_order,
            "origin": list(target_grid.origin),
            "spacing": list(target_grid.spacing),
            "cell_shape": list(target_grid.cell_shape),
        },
        "source": {
            "block_mesh": source_mesh.to_dict(),
            "cell_count": source_mesh.grid.cell_count,
            "cell_order": source_mesh.grid.cell_order,
            "origin": list(source_mesh.grid.origin),
            "spacing": list(source_mesh.grid.spacing),
            "cell_shape": list(source_mesh.grid.cell_shape),
            "cell_order_mapping": order_mapping.to_dict(),
        },
        "transfer": {
            "state_map": "source = P @ target",
            "inverse_state_map": "refused_not_defined",
            "implementation": "ExactCartesianOverlapTransfer.transfer_state_to_source",
            "source_grid_sha256": transfer.source_grid_sha256,
            "target_grid_sha256": transfer.target_grid_sha256,
            "source_active_mask_sha256": transfer.source_active_mask_sha256,
            "target_active_mask_sha256": transfer.target_active_mask_sha256,
            "matrix_shape": list(transfer.matrix.shape),
            "matrix_nnz": int(transfer.matrix.nnz),
            "coverage": "full source and target grid domains",
        },
        "exported_arrays": {
            "source_rho_xfastest": {
                "sha256": _array_sha256(source_rho_xfastest),
                "cell_count": int(source_rho_xfastest.size),
                "range": [
                    float(np.min(source_rho_xfastest)),
                    float(np.max(source_rho_xfastest)),
                ],
            },
            "source_rho_global_label": {
                "sha256": _array_sha256(source_rho_global),
                "cell_count": int(source_rho_global.size),
            },
            "source_global_cell_labels_by_xfastest": {
                "sha256": _array_sha256(
                    payload["source_global_cell_labels_by_xfastest"]
                ),
                "cell_count": int(source_rho_xfastest.size),
            },
        },
        "solver_field_conversion": {
            "status": "not_performed",
            "reason": "rho-to-alpha and OpenFOAM boundary semantics belong to the solver case compiler",
        },
    }
    return _write_atomically(output_directory, payload, provenance)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"verified candidate binding is missing {name}")
    return value


def _rho(values: object, count: int, name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.shape != (count,) or not np.issubdtype(raw.dtype, np.number):
        raise ValueError(f"{name} must be a numeric vector with shape ({count},)")
    array = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    if np.any(array < 0.0) or np.any(array > 1.0):
        raise ValueError(f"{name} must satisfy 0 <= rho <= 1")
    return array


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values))
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)},
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_atomically(
    output_directory: str | Path,
    payload: dict[str, np.ndarray],
    provenance: dict[str, Any],
) -> CanonicalStateTransferArtifacts:
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError(f"output_directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.tmp-{uuid4().hex}"
    fields_npz = temporary / "openfoam_source_state.npz"
    provenance_json = temporary / "provenance.json"
    try:
        temporary.mkdir()
        np.savez_compressed(fields_npz, **payload)
        provenance["artifact_file"] = {
            "path": fields_npz.name,
            "sha256": _sha256_file(fields_npz),
        }
        provenance_json.write_text(
            json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        with np.load(fields_npz, allow_pickle=False) as written:
            if set(written.files) != set(payload):
                raise ValueError("written source-state NPZ has an unexpected array set")
            for key, expected in payload.items():
                if not np.array_equal(written[key], expected):
                    raise ValueError(f"written source-state NPZ does not preserve {key}")
        json.loads(provenance_json.read_text(encoding="utf-8"))
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return CanonicalStateTransferArtifacts(
        directory=output,
        fields_npz=output / fields_npz.name,
        provenance_json=output / provenance_json.name,
    )


__all__ = [
    "CanonicalStateTransferArtifacts",
    "transfer_and_write_openfoam_source_state",
    "write_openfoam_source_state_transfer",
]
