"""Inject a transferred OpenFOAM-ordered canonical state into a T1 contract.

``transfer-stage-t-candidate-to-openfoam`` writes ``source_rho_xfastest``: the
canonical Stage T density averaged onto the OpenFOAM source grid, in that
grid's x-fastest order.  A fixed-grid (T1) contract's ``density.vti`` already
lives on that same OpenFOAM grid in ``vtk-x-fastest`` order.  This module
overwrites only the T1 contract's ``active_design_mask`` cells with that
transferred value, leaving every fixed-solid, forbidden, and outer-fluid cell
untouched, and never mutates the input contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

import numpy as np

from .fixed_grid_contract import _write_cell_vti
from .fixed_grid_primal import FixedGridDensityState, load_fixed_grid_density_state
from .openfoam_grid_transfer import UniformCartesianCellGrid


_ARTIFACT_KIND = "canonical_state_injection"
_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CanonicalStateInjectionArtifacts:
    """Paths to one atomically written T1 contract with injected canonical state."""

    directory: Path
    topology_state_json: Path
    density_vti: Path
    provenance_json: Path


def inject_canonical_state_into_fixed_grid_contract(
    *,
    openfoam_source_state_npz: str | Path,
    source_state_provenance_json: str | Path,
    topology_state_json: str | Path,
    output_directory: str | Path,
) -> CanonicalStateInjectionArtifacts:
    """Write a new T1 contract whose ``rho`` is overwritten on active cells only."""

    npz_path = Path(openfoam_source_state_npz).resolve()
    provenance_path = Path(source_state_provenance_json).resolve()
    source_provenance = _load_json(provenance_path)
    if source_provenance.get("kind") != "openfoam_canonical_state_transfer":
        raise ValueError(f"Unsupported source-state provenance kind: {provenance_path}")

    with np.load(npz_path, allow_pickle=False) as payload:
        if "source_rho_xfastest" not in payload.files:
            raise ValueError(f"{npz_path} is missing source_rho_xfastest")
        source_rho_xfastest = np.array(payload["source_rho_xfastest"], dtype=np.float64)

    density_state = load_fixed_grid_density_state(Path(topology_state_json))
    contract_grid = density_state.grid
    contract_uniform_grid = UniformCartesianCellGrid(
        origin=contract_grid.origin,
        spacing=contract_grid.spacing,
        cell_shape=contract_grid.cell_shape,
        cell_order="x-fastest",
    )
    _validate_source_grid_identity(source_provenance, contract_uniform_grid, contract_grid.cell_count)
    source_rho_xfastest = _validate_rho(source_rho_xfastest, contract_grid.cell_count)

    active_mask = np.asarray(density_state.arrays["active_design_mask"])
    if not np.isin(active_mask, (0, 1)).all():
        raise ValueError("density.vti:active_design_mask must be binary")
    active = active_mask > 0

    original_rho = np.asarray(density_state.arrays["rho"])
    new_rho = original_rho.astype(np.float64, copy=True)
    new_rho[active] = source_rho_xfastest[active]
    new_rho = new_rho.astype(original_rho.dtype, copy=False)

    alpha_metadata = dict(
        (density_state.state.get("array_metadata") or {}).get("alpha") or {}
    )
    if not alpha_metadata:
        raise ValueError(
            f"{topology_state_json} is missing array_metadata for alpha; "
            "the rho-to-alpha convention cannot be recorded without inventing one"
        )

    provenance = {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "kind": _ARTIFACT_KIND,
        "candidate_binding": source_provenance.get("candidate_binding"),
        "grids": {
            "npz_target_canonical_grid_sha256": (source_provenance.get("target") or {}).get("grid_sha256"),
            "npz_source_openfoam_grid_sha256": (
                (source_provenance.get("source") or {}).get("block_mesh") or {}
            ).get("grid_sha256"),
            "contract_grid_sha256": contract_uniform_grid.sha256,
        },
        "active_design_mask": {
            "sha256": _mask_sha256(active_mask),
            "true_count": int(np.count_nonzero(active)),
        },
        "overwritten_cell_count": int(np.count_nonzero(active)),
        "rho_variant_written": "rho",
        "rho_to_alpha_convention": alpha_metadata,
        "source_files": {
            "openfoam_source_state_npz": {"path": str(npz_path), "sha256": _sha256_file(npz_path)},
            "source_state_provenance_json": {"path": str(provenance_path), "sha256": _sha256_file(provenance_path)},
        },
    }
    return _write_atomically(output_directory, density_state, new_rho, provenance)


def _validate_source_grid_identity(
    source_provenance: dict[str, Any],
    contract_grid: UniformCartesianCellGrid,
    contract_cell_count: int,
) -> None:
    source = source_provenance.get("source")
    if not isinstance(source, dict):
        raise ValueError("source-state provenance is missing its source grid identity")
    block_mesh = source.get("block_mesh")
    if not isinstance(block_mesh, dict):
        raise ValueError("source-state provenance is missing its source blockMesh identity")
    if source.get("cell_count") != contract_cell_count:
        raise ValueError(
            "npz source grid cell_count does not match the T1 contract grid: "
            f"{source.get('cell_count')!r} != {contract_cell_count}"
        )
    if not np.allclose(source.get("origin") or [], contract_grid.origin, rtol=0.0, atol=1.0e-9):
        raise ValueError("npz source grid origin does not match the T1 contract grid")
    if not np.allclose(source.get("spacing") or [], contract_grid.spacing, rtol=0.0, atol=1.0e-9):
        raise ValueError("npz source grid spacing does not match the T1 contract grid")
    if tuple(source.get("cell_shape") or []) != tuple(contract_grid.cell_shape):
        raise ValueError("npz source grid cell_shape does not match the T1 contract grid")
    if block_mesh.get("grid_sha256") != contract_grid.sha256:
        raise ValueError("npz source grid_sha256 does not match the T1 contract grid")


def _validate_rho(values: np.ndarray, count: int) -> np.ndarray:
    if values.shape != (count,):
        raise ValueError(f"source_rho_xfastest must have shape ({count},), got {values.shape!r}")
    if not np.isfinite(values).all():
        raise ValueError("source_rho_xfastest must contain only finite values")
    if np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("source_rho_xfastest must satisfy 0 <= rho <= 1")
    return values


def _mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.uint8).tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read source-state provenance: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Source-state provenance must be a JSON object: {path}")
    return data


def _write_atomically(
    output_directory: str | Path,
    density_state: FixedGridDensityState,
    new_rho: np.ndarray,
    provenance: dict[str, Any],
) -> CanonicalStateInjectionArtifacts:
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError(f"output_directory already exists: {output}")
    source_dir = density_state.output_dir
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.tmp-{uuid4().hex}"
    try:
        shutil.copytree(source_dir, temporary)
        density_relative = density_state.density_vti.relative_to(source_dir)
        new_arrays = dict(density_state.arrays)
        new_arrays["rho"] = new_rho
        density_target = temporary / density_relative
        _write_cell_vti(density_state.grid, new_arrays, density_target, kind="fixed_grid_density")
        provenance["written_density_vti_sha256"] = _sha256_file(density_target)
        provenance_json = temporary / "canonical_state_injection.json"
        provenance_json.write_text(
            json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    topology_relative = density_state.topology_state_json.relative_to(source_dir)
    return CanonicalStateInjectionArtifacts(
        directory=output,
        topology_state_json=output / topology_relative,
        density_vti=output / density_relative,
        provenance_json=output / "canonical_state_injection.json",
    )


__all__ = [
    "CanonicalStateInjectionArtifacts",
    "inject_canonical_state_into_fixed_grid_contract",
]
