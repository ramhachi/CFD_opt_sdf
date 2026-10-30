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
    """Write a new T1 contract whose ``rho`` is overwritten on active cells only.

    Fail-closed on generation (P7/C2): the injection owns a validated transfer of
    ``rho`` only — it does not own any filter or projection profile, so it can
    refresh the derived siblings (``rho_filtered``, ``rho_projected``, ``alpha``)
    at the same generation ONLY when the source contract provably satisfies the
    C3 identity contract (``rho_filtered == rho_projected == rho`` and
    ``alpha == beta_max * rho`` with one constant ``beta_max`` decoded from the
    recorded array). Any other derived state is refused rather than silently
    carried over in its previous generation.
    """

    npz_path = Path(openfoam_source_state_npz).resolve()
    provenance_path = Path(source_state_provenance_json).resolve()
    source_provenance = _load_json(provenance_path)
    if source_provenance.get("kind") != "openfoam_canonical_state_transfer":
        raise ValueError(f"Unsupported source-state provenance kind: {provenance_path}")

    with np.load(npz_path, allow_pickle=False) as payload:
        raw_arrays = {name: np.array(payload[name]) for name in payload.files}
    candidate_binding = _validate_candidate_provenance(
        source_provenance, npz_path, raw_arrays
    )
    if "source_rho_xfastest" not in raw_arrays:
        raise ValueError(f"{npz_path} is missing source_rho_xfastest")
    source_rho_xfastest = raw_arrays["source_rho_xfastest"].astype(np.float64)

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

    beta_max = _validate_identity_derived_generation(density_state, original_rho)
    new_rho = new_rho.astype(original_rho.dtype, copy=False)
    new_rho_projected = new_rho.copy()
    new_rho_filtered = new_rho.copy()
    alpha_dtype = np.asarray(density_state.arrays["alpha"]).dtype
    new_alpha = (beta_max * new_rho.astype(np.float64)).astype(alpha_dtype, copy=False)

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
        "candidate_binding": candidate_binding,
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
        "candidate_transfer": {
            "rho_variant": (source_provenance.get("target") or {}).get("rho_variant"),
            "target_rho_value_sha256": (source_provenance.get("target") or {}).get(
                "rho_value_sha256"
            ),
            "source_rho_xfastest_sha256": (
                (source_provenance.get("exported_arrays") or {}).get(
                    "source_rho_xfastest"
                )
                or {}
            ).get("sha256"),
        },
        "rho_to_alpha_convention": alpha_metadata,
        "derived_generation": {
            "contract": "C3 identity projection (rho_projected = rho_filtered = rho; alpha = beta_max * rho)",
            "validation": {
                "pre_state_rho_projected_equals_rho": True,
                "pre_state_rho_filtered_equals_rho": True,
                "alpha_equals_beta_max_times_rho": True,
                "beta_max": beta_max,
                "beta_max_source": "decoded from the recorded alpha/rho ratio on cells with rho > 0.5",
            },
            "arrays_refreshed_same_generation": ["rho", "rho_filtered", "rho_projected", "alpha"],
            "new_rho_sha256": _array_sha256(new_rho),
            "new_alpha_sha256": _array_sha256(new_alpha),
            "new_rho_filtered_sha256": _array_sha256(new_rho_filtered),
            "new_rho_projected_sha256": _array_sha256(new_rho_projected),
        },
        "source_files": {
            "openfoam_source_state_npz": {"path": str(npz_path), "sha256": _sha256_file(npz_path)},
            "source_state_provenance_json": {"path": str(provenance_path), "sha256": _sha256_file(provenance_path)},
        },
    }
    return _write_atomically(output_directory, density_state, new_rho, new_rho_filtered, new_rho_projected, new_alpha, provenance)


def _validate_candidate_provenance(
    source_provenance: dict[str, Any],
    npz_path: Path,
    raw_arrays: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Refuse an NPZ/provenance pair unless they were written together.

    ``transfer_and_write_openfoam_source_state`` binds a candidate's exported
    arrays to this exact ``provenance.json`` via ``artifact_file.sha256`` (the
    NPZ file's own hash) and per-array ``exported_arrays.<name>.sha256``
    hashes.  Re-deriving and comparing both here closes the hole where a
    stale ``provenance.json`` (e.g. the initial candidate's) is reused for a
    different candidate's NPZ: any byte difference in the file, or any
    dtype/shape/order/value difference in an exported array, changes its
    hash and is refused.
    """

    artifact_file = source_provenance.get("artifact_file")
    if not isinstance(artifact_file, dict) or not isinstance(artifact_file.get("sha256"), str):
        raise ValueError("source-state provenance is missing its own artifact_file hash")
    actual_npz_sha256 = _sha256_file(npz_path)
    if actual_npz_sha256 != artifact_file["sha256"]:
        raise ValueError(
            f"{npz_path} does not match the provenance that describes it (file hash "
            "mismatch); provenance.json must be this exact candidate's own sidecar, "
            "not a reused or swapped one"
        )
    exported = source_provenance.get("exported_arrays")
    if not isinstance(exported, dict) or not exported:
        raise ValueError("source-state provenance is missing exported_arrays hashes")
    for name, record in exported.items():
        if not isinstance(record, dict) or not isinstance(record.get("sha256"), str):
            raise ValueError(f"source-state provenance is missing exported_arrays.{name}.sha256")
        if name not in raw_arrays:
            raise ValueError(f"{npz_path} is missing array {name!r} recorded in its provenance")
        actual = _array_sha256(raw_arrays[name])
        if actual != record["sha256"]:
            raise ValueError(
                f"{npz_path} array {name!r} does not match its provenance hash "
                f"(dtype/shape/order/value changed); the NPZ and provenance must "
                "come from the same candidate transfer"
            )

    candidate = source_provenance.get("candidate_binding")
    if not isinstance(candidate, dict):
        raise ValueError("source-state provenance is missing candidate_binding")
    required_text = (
        "path",
        "sha256",
        "problem_id",
        "problem_spec_sha256",
        "candidate_id",
    )
    for key in required_text:
        if not isinstance(candidate.get(key), str) or not candidate[key]:
            raise ValueError(
                f"source-state provenance candidate_binding.{key} must be a non-empty string"
            )
    for key in ("sha256", "problem_spec_sha256"):
        value = candidate[key]
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(
                f"source-state provenance candidate_binding.{key} must be a lowercase SHA-256"
            )
    if candidate.get("execution_ready") is not True:
        raise ValueError("source-state provenance candidate binding is not execution-ready")
    iteration = candidate.get("iteration")
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 0:
        raise ValueError(
            "source-state provenance candidate_binding.iteration must be a non-negative integer"
        )
    parent = candidate.get("parent_candidate_id")
    if parent is not None and (not isinstance(parent, str) or not parent):
        raise ValueError(
            "source-state provenance candidate_binding.parent_candidate_id must be null or a non-empty string"
        )
    if (iteration == 0) != (parent is None):
        raise ValueError(
            "source-state provenance candidate lineage requires no parent at iteration 0 "
            "and a parent after iteration 0"
        )
    binding_path = Path(candidate["path"]).resolve()
    if not binding_path.is_file():
        raise ValueError(
            f"source-state provenance candidate binding does not exist: {binding_path}"
        )
    if _sha256_file(binding_path) != candidate["sha256"]:
        raise ValueError(
            "source-state provenance candidate binding file hash mismatch; the binding "
            "changed after the source-state transfer was written"
        )
    return dict(candidate)


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)}, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


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


def _validate_identity_derived_generation(
    density_state: FixedGridDensityState,
    original_rho: np.ndarray,
) -> float:
    """Fail closed unless the contract's derived siblings satisfy the C3 identity contract.

    The injector cannot own a filter/projector; it may only refresh
    ``rho_filtered``/``rho_projected``/``alpha`` at the new ``rho`` generation when
    the contract it is derived from actually encodes the identity contract. This
    both decodes ``beta_max`` from the recorded ``alpha`` and refuses any
    non-identity filter/projection/Brinkman state instead of carrying it forward
    (reading a formerly stale array would be exactly the P7 defect).
    """

    def array(name: str) -> np.ndarray:
        try:
            return np.asarray(density_state.arrays[name], dtype=np.float64)
        except KeyError as exc:
            raise ValueError(
                f"density.vti is missing array {name!r}; the injection requires all "
                "four design arrays of the C3 identity contract"
            ) from exc

    projected = array("rho_projected")
    filtered = array("rho_filtered")
    alpha = array("alpha")
    if not np.allclose(projected, original_rho, rtol=0.0, atol=1.0e-9):
        raise ValueError(
            "injection owns no projection profile: the contract's rho_projected is "
            "not the C3 identity (rho_projected != rho). Refusing to leave a stale "
            "projected array in place; re-inject through the profile that owns it"
        )
    if not np.allclose(filtered, original_rho, rtol=0.0, atol=1.0e-9):
        raise ValueError(
            "injection owns no filter profile: the contract's rho_filtered is not "
            "the C3 identity (rho_filtered != rho). Refusing to leave a stale "
            "filtered array in place; re-inject through the profile that owns it"
        )
    selectable = original_rho > 1.0e-6
    if not selectable.any():
        raise ValueError(
            "alpha convention cannot be decoded without a cell carrying finite "
            "density; refusing to reinfer the Brinkman coefficient"
        )
    ratios = alpha[selectable] / original_rho[selectable]
    beta_max = float(np.median(ratios))
    if not np.allclose(ratios, beta_max, rtol=1.0e-6, atol=0.0):
        raise ValueError(
            "alpha is not a singleBetaMax multiple of rho (alpha != beta_max * rho); "
            "refusing to recompute the derived alpha generation"
        )
    return beta_max


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
    new_rho_filtered: np.ndarray,
    new_rho_projected: np.ndarray,
    new_alpha: np.ndarray,
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
        new_arrays["rho_filtered"] = new_rho_filtered
        new_arrays["rho_projected"] = new_rho_projected
        new_arrays["alpha"] = new_alpha
        density_target = temporary / density_relative
        _write_cell_vti(density_state.grid, new_arrays, density_target, kind="fixed_grid_density")
        provenance["written_density_vti_sha256"] = _sha256_file(density_target)
        topology_relative = density_state.topology_state_json.relative_to(source_dir)
        topology_target = temporary / topology_relative
        candidate = provenance["candidate_binding"]
        state = dict(density_state.state)
        state.update(
            problem_id=candidate["problem_id"],
            problem_spec_sha256=candidate["problem_spec_sha256"],
            candidate_id=candidate["candidate_id"],
            parent_candidate_id=candidate["parent_candidate_id"],
            iteration=candidate["iteration"],
            density_vti_sha256=provenance["written_density_vti_sha256"],
            density_sha256=provenance["written_density_vti_sha256"],
        )
        artifacts = dict(state.get("artifacts") or {})
        artifacts["density_vti"] = {
            "path": str(density_relative),
            "sha256": provenance["written_density_vti_sha256"],
        }
        state["artifacts"] = artifacts
        state["canonical_candidate_binding"] = {
            **candidate,
            "rho_variant": (
                provenance.get("candidate_transfer") or {}
            ).get("rho_variant"),
            "source_state_npz_sha256": provenance["source_files"][
                "openfoam_source_state_npz"
            ]["sha256"],
            "source_state_provenance_sha256": provenance["source_files"][
                "source_state_provenance_json"
            ]["sha256"],
        }
        topology_target.write_text(
            json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        provenance["written_topology_state_sha256"] = _sha256_file(topology_target)
        provenance_json = temporary / "canonical_state_injection.json"
        provenance_json.write_text(
            json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
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
