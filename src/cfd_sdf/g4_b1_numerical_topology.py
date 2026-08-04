"""Deterministic, STL-independent G4 B1 numerical topology benchmark.

This module deliberately has a much narrower scope than the localized G2
reference-state workflow.  It materialises small canonical voxel fixtures and
uses the existing localized filter/projection and discrete topology checker
semantics to test their numerical contract.  No OpenFOAM case, STL, flow
solution, or physical objective is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

import numpy as np

from . import localized_reference_topology as topology
from .localized_design_state_manifest import CANONICAL_CELL_ORDER, LocalizedDesignGrid
from .localized_filter_projection import (
    LocalizedConeFilterConfig,
    LocalizedHeavisideProjectionConfig,
    apply_localized_cone_filter,
    apply_localized_cone_filter_adjoint,
    apply_localized_heaviside_projection,
    localized_heaviside_projection_derivative,
)
from .problem_spec import ConnectivityPolicySpec, TopologyPolicySpec


G4_B1_NUMERICAL_TOPOLOGY_SCHEMA_VERSION = 1
G4_B1_NUMERICAL_TOPOLOGY_KIND = "g4_b1_numerical_topology_benchmark"
G4_B1_NUMERICAL_TOPOLOGY_FILENAME = "g4_b1_numerical_topology_index.json"
_SPACING_M = 0.002
_MIN_SOLID_WIDTH_M = 0.010
_EROSION_RADIUS_M = 0.004
_H_LADDER = (1.0e-4, 1.0e-5, 1.0e-6)
_DIRECTION_SEED = 20_260_730


@dataclass(frozen=True)
class G4B1NumericalTopologyBenchmark:
    """Published immutable B1 result index."""

    path: Path
    status: str
    index_sha256: str


def run_g4_b1_numerical_topology_benchmark(
    *, output_dir: str | Path,
) -> G4B1NumericalTopologyBenchmark:
    """Build the canonical B1 pack and atomically publish its result index.

    The output path is intentionally the only parameter.  Fixture geometry,
    2 mm/10 mm policy, filter/projection settings, finite-difference ladder,
    and random seed are all fixed by the B1 decision record.
    """

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite G4 B1 benchmark output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        payload = _build_pack(staging)
        _write_json(staging / G4_B1_NUMERICAL_TOPOLOGY_FILENAME, payload)
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    index_path = destination / G4_B1_NUMERICAL_TOPOLOGY_FILENAME
    return G4B1NumericalTopologyBenchmark(
        path=index_path,
        status=str(payload["status"]),
        index_sha256=_sha256_file(index_path),
    )


def _build_pack(staging: Path) -> dict[str, Any]:
    arrays = staging / "arrays"
    arrays.mkdir()
    policy = _policy()
    policy_json = _policy_dict(policy)
    fixtures: list[dict[str, Any]] = []
    artifact_hashes: dict[str, str] = {}

    for fixture_id, expected_status, expected_reason, grid, active, root, rho in _fixtures():
        paths = {
            "active_mask": arrays / f"{fixture_id}_active_mask.npy",
            "root_mask": arrays / f"{fixture_id}_root_mask.npy",
            "rho_projected": arrays / f"{fixture_id}_rho_projected.npy",
        }
        _save_array(paths["active_mask"], active)
        _save_array(paths["root_mask"], root)
        _save_array(paths["rho_projected"], rho)
        report = _topology_report(grid, active, root, rho, policy, staging / f".{fixture_id}-checker")
        checker = {
            "kind": "localized_discrete_voxel_topology_checker",
            "grid_sha256": grid.sha256,
            "grid": _grid_dict(grid),
            "policy": policy_json,
            "policy_sha256": _sha256_json(policy_json),
            "threshold": {"operator": ">=", "value": 0.5},
            "neighborhood": "6_face",
            "status": report["status"],
            "reasons": report["reasons"],
            "checks": report["checks"],
        }
        checker_hash = _sha256_json(checker)
        passed = report["status"] == expected_status and (
            expected_reason is None or expected_reason in report["reasons"]
        )
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "expected_status": expected_status,
                "expected_reason": expected_reason,
                "status": report["status"],
                "reasons": report["reasons"],
                "acceptance_passed": passed,
                "checker": checker,
                "checker_sha256": checker_hash,
                "array_files": {key: path.relative_to(staging).as_posix() for key, path in paths.items()},
            }
        )
        artifact_hashes.update({path.relative_to(staging).as_posix(): _sha256_file(path) for path in paths.values()})

    numerical, numerical_hashes = _numerical_derivative_pack(arrays)
    artifact_hashes.update(numerical_hashes)
    fixture_passed = all(bool(item["acceptance_passed"]) for item in fixtures)
    numerical_passed = bool(numerical["acceptance_passed"])
    reasons: list[str] = []
    if not fixture_passed:
        reasons.append("topology_fixture_acceptance_failed")
    if not numerical_passed:
        reasons.append("transform_derivative_acceptance_failed")
    return {
        "schema_version": G4_B1_NUMERICAL_TOPOLOGY_SCHEMA_VERSION,
        "kind": G4_B1_NUMERICAL_TOPOLOGY_KIND,
        "scope": "stl_independent_discrete_voxel_topology_and_filter_projection_derivative_only",
        "status": "success" if not reasons else "rejected",
        "reasons": reasons,
        "cell_order": CANONICAL_CELL_ORDER,
        "policy": policy_json,
        "policy_sha256": _sha256_json(policy_json),
        "filter": LocalizedConeFilterConfig().to_dict(),
        "filter_sha256": LocalizedConeFilterConfig().sha256,
        "projection": LocalizedHeavisideProjectionConfig().to_dict(),
        "projection_sha256": LocalizedHeavisideProjectionConfig().sha256,
        "fixtures": fixtures,
        "transform_derivative": numerical,
        "artifact_sha256": dict(sorted(artifact_hashes.items())),
        "limitations": [
            "small_canonical_voxel_fixture_only",
            "does_not_use_stl_or_reference_state_bundle",
            "does_not_execute_or_qualify_openfoam_or_cfd",
            "does_not_prove_continuous_manufacturability",
        ],
    }


def _fixtures() -> tuple[tuple[str, str, str | None, LocalizedDesignGrid, np.ndarray, np.ndarray, np.ndarray], ...]:
    """Return root-connected bar fixtures and one disconnected island."""

    grid = LocalizedDesignGrid((0.0, 0.0, 0.0), (_SPACING_M,) * 3, (30, 20, 20))
    result: list[tuple[str, str, str | None, LocalizedDesignGrid, np.ndarray, np.ndarray, np.ndarray]] = []
    for width in range(1, 7):
        active, root, rho = _root_attached_bar(grid, width)
        result.append((
            f"root_attached_bridge_{width}_cells",
            "success" if width >= 5 else "rejected",
            None if width >= 5 else "minimum_solid_width",
            grid, active, root, rho,
        ))
    active, root, rho = _root_attached_bar(grid, 6)
    volume = rho.reshape((20, 20, 30), order="C")
    # The island is deliberately clear of the rooted bar.  Its mandatory
    # acceptance reason is nominal root connectivity; any additional local
    # width finding remains preserved rather than tuned away.
    volume[0:6, 0:6, 12:18] = 1.0
    result.append(("unrooted_island", "rejected", "solid_component_without_root_nominal", grid, active, root, rho))
    return tuple(result)


def _root_attached_bar(grid: LocalizedDesignGrid, width: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not 1 <= width <= 6:
        raise ValueError("canonical B1 bridge width must be in [1, 6]")
    shape = (grid.cell_shape[2], grid.cell_shape[1], grid.cell_shape[0])
    active = np.ones(grid.cell_count, dtype=np.bool_)
    root = np.zeros(grid.cell_count, dtype=np.bool_)
    rho = np.zeros(grid.cell_count, dtype=np.float64)
    root3 = root.reshape(shape, order="C")
    rho3 = rho.reshape(shape, order="C")
    # Two 6-cell root slabs remove terminal features from the width predicate:
    # the fixture isolates bridge cross-section width rather than a small
    # unsupported root attachment.
    root3[:, :, :6] = True
    root3[:, :, -6:] = True
    # Localized design roles are disjoint: declared root material is immutable
    # attachment geometry, never a mutable active design cell.
    active.reshape(shape, order="C")[root3] = False
    start = (shape[1] - width) // 2
    # The bridge has one controlled thickness dimension (y) and spans z.
    # This keeps the rolling-ball criterion focused on the stated width rather
    # than introducing unrequested corner-radius failures in a square bar.
    rho3[:, start:start + width, 6:-6] = 1.0
    return active, root, rho


def _policy() -> TopologyPolicySpec:
    return TopologyPolicySpec(
        root_groups=(),
        solid_connectivity=ConnectivityPolicySpec(
            mode="root_connected", required_root_group_ids=(), max_components=None, evaluate_eroded=True,
        ),
        void_connectivity=ConnectivityPolicySpec(
            mode="disabled", required_root_group_ids=(), max_components=None, evaluate_eroded=False,
        ),
        minimum_solid_width_m=_MIN_SOLID_WIDTH_M,
        minimum_void_width_m=None,
        minimum_gap_m=None,
        erosion_radius_m=_EROSION_RADIUS_M,
    )


def _policy_dict(policy: TopologyPolicySpec) -> dict[str, Any]:
    return {
        "solid_connectivity": {
            "mode": policy.solid_connectivity.mode,
            "required_root_group_ids": list(policy.solid_connectivity.required_root_group_ids),
            "max_components": policy.solid_connectivity.max_components,
            "evaluate_eroded": policy.solid_connectivity.evaluate_eroded,
        },
        "void_connectivity": {
            "mode": policy.void_connectivity.mode,
            "required_root_group_ids": list(policy.void_connectivity.required_root_group_ids),
            "max_components": policy.void_connectivity.max_components,
            "evaluate_eroded": policy.void_connectivity.evaluate_eroded,
        },
        "minimum_solid_width_m": policy.minimum_solid_width_m,
        "minimum_void_width_m": policy.minimum_void_width_m,
        "minimum_gap_m": policy.minimum_gap_m,
        "erosion_radius_m": policy.erosion_radius_m,
    }


def _topology_report(
    grid: LocalizedDesignGrid, active: np.ndarray, root: np.ndarray, rho: np.ndarray,
    policy: TopologyPolicySpec, work: Path,
) -> dict[str, Any]:
    """Call the localized evaluator's exact six-face/EDT primitives on a fixture."""

    spatial_shape = (grid.cell_shape[2], grid.cell_shape[1], grid.cell_shape[0])
    work.mkdir(parents=True)
    active3 = active.reshape(spatial_shape, order="C")
    root3 = root.reshape(spatial_shape, order="C")
    rho3 = rho.reshape(spatial_shape, order="C")
    domain = topology._new_bool(work / "design_domain.npy", spatial_shape)
    solid = topology._new_bool(work / "solid.npy", spatial_shape)
    void = topology._new_bool(work / "void.npy", spatial_shape)
    try:
        domain[:] = active3 | root3
        solid[:] = (active3 & (rho3 >= 0.5)) | root3
        void[:] = domain & ~solid
        domain.flush(); solid.flush(); void.flush()
        reasons: list[str] = []
        checks: dict[str, Any] = {
            "digital_state": {
                "design_domain_count": int(np.count_nonzero(domain)),
                "solid_count": int(np.count_nonzero(solid)),
                "void_count": int(np.count_nonzero(void)),
                "first_solid_index": topology._first_index(solid, grid),
                "first_void_index": topology._first_index(void, grid),
            }
        }
        topology._connectivity_checks(solid, root3, policy.solid_connectivity, grid, work, "solid", reasons, checks)
        topology._void_component_checks(void, domain, policy.void_connectivity, grid, work, reasons, checks)
        topology._erosion_checks(solid, active3, root3, policy.solid_connectivity, policy.erosion_radius_m, grid, work, reasons, checks)
        topology._width_checks(solid, void, domain, policy, grid, work, reasons, checks)
        return {"status": "success" if not reasons else "rejected", "reasons": list(dict.fromkeys(reasons)), "checks": checks}
    finally:
        del void, solid, domain
        shutil.rmtree(work, ignore_errors=True)


def _numerical_derivative_pack(arrays: Path) -> tuple[dict[str, Any], dict[str, str]]:
    grid = LocalizedDesignGrid((0.0, 0.0, 0.0), (_SPACING_M,) * 3, (7, 5, 4))
    count = grid.cell_count
    active = np.ones(count, dtype=np.bool_)
    active[[3, 19, 55, 91, 122]] = False
    indices = np.arange(count, dtype=np.float64)
    raw = np.zeros(count, dtype=np.float64)
    raw[active] = 0.5 + 0.2 * np.sin(indices[active] * 0.37)
    weights = np.zeros(count, dtype=np.float64)
    weights[active] = np.cos(indices[active] * 0.23) + 0.125 * np.sin(indices[active] * 0.11)
    generator = np.random.default_rng(_DIRECTION_SEED)
    directions = np.zeros((3, count), dtype=np.float64)
    directions[:, active] = generator.standard_normal((3, int(np.count_nonzero(active))))
    directions /= np.linalg.norm(directions, axis=1)[:, None]

    filtered = apply_localized_cone_filter(raw, active, grid)
    derivative_projected = localized_heaviside_projection_derivative(filtered, active)
    analytic = apply_localized_cone_filter_adjoint(derivative_projected * weights, active, grid)
    cellwise_fd = np.zeros((len(_H_LADDER), count), dtype=np.float64)
    direction_fd = np.zeros((len(_H_LADDER), directions.shape[0]), dtype=np.float64)
    direction_analytic = directions @ analytic
    for h_index, h in enumerate(_H_LADDER):
        for cell in np.flatnonzero(active):
            direction = np.zeros(count, dtype=np.float64)
            direction[cell] = 1.0
            cellwise_fd[h_index, cell] = _central_difference(raw, active, grid, weights, direction, h)
        for direction_index, direction in enumerate(directions):
            direction_fd[h_index, direction_index] = _central_difference(raw, active, grid, weights, direction, h)

    cell_errors = np.abs(cellwise_fd - analytic[None, :])
    direction_errors = np.abs(direction_fd - direction_analytic[None, :])
    max_errors = [float(max(np.max(cell_errors[row]), np.max(direction_errors[row]))) for row in range(len(_H_LADDER))]
    # Keep the cellwise and directional tolerances explicit: their dimensions
    # differ, even though both use the same accepted formula.
    direction_tolerance = 2.0e-9 + 1.0e-7 * np.maximum(np.abs(direction_fd[1]), np.abs(direction_analytic))
    h_1e5_ok = bool(np.all(cell_errors[1] <= (2.0e-9 + 1.0e-7 * np.maximum(np.abs(cellwise_fd[1]), np.abs(analytic)))) and np.all(direction_errors[1] <= direction_tolerance))
    improved = bool(max_errors[1] < max_errors[0])
    inactive_exact_zero = bool(
        np.all(raw[~active] == 0.0)
        and np.all(weights[~active] == 0.0)
        and np.all(directions[:, ~active] == 0.0)
        and np.all(analytic[~active] == 0.0)
        and np.all(cellwise_fd[:, ~active] == 0.0)
    )
    paths = {
        "derivative_active_mask.npy": active,
        "derivative_rho_raw.npy": raw,
        "derivative_weights.npy": weights,
        "derivative_directions.npy": directions,
        "derivative_analytic.npy": analytic,
        "derivative_cellwise_fd.npy": cellwise_fd,
        "derivative_direction_analytic.npy": direction_analytic,
        "derivative_direction_fd.npy": direction_fd,
    }
    hashes: dict[str, str] = {}
    for name, value in paths.items():
        path = arrays / name
        _save_array(path, value)
        hashes[path.relative_to(arrays.parent).as_posix()] = _sha256_file(path)
    return {
        "scalar_probe": "J(rho_raw)=w^T P(F(rho_raw))",
        "grid_sha256": grid.sha256,
        "grid": _grid_dict(grid),
        "cell_order": CANONICAL_CELL_ORDER,
        "active_cell_count": int(np.count_nonzero(active)),
        "direction_seed": _DIRECTION_SEED,
        "direction_indices": [0, 1, 2],
        "direction_normalisation": "active_only_l2_unit",
        "epsilon_ladder": list(_H_LADDER),
        "finite_difference": "central",
        "analytic_gradient": "F.T(P_prime(F(rho_raw))*w)",
        "array_files": {name: f"arrays/{name}" for name in paths},
        "maximum_absolute_error": max_errors,
        "h_1e-5_tolerance": "abs(FD-analytic)<=2e-9+1e-7*max(abs(FD),abs(analytic))",
        "h_1e-5_acceptance_passed": h_1e5_ok,
        "error_improves_1e-4_to_1e-5": improved,
        "h_1e-6_recorded_only": True,
        "inactive_entries_exact_zero": inactive_exact_zero,
        "acceptance_passed": bool(h_1e5_ok and improved and inactive_exact_zero),
    }, hashes


def _central_difference(raw: np.ndarray, active: np.ndarray, grid: LocalizedDesignGrid, weights: np.ndarray, direction: np.ndarray, h: float) -> float:
    return (_probe(raw + h * direction, active, grid, weights) - _probe(raw - h * direction, active, grid, weights)) / (2.0 * h)


def _probe(raw: np.ndarray, active: np.ndarray, grid: LocalizedDesignGrid, weights: np.ndarray) -> float:
    projected = apply_localized_heaviside_projection(apply_localized_cone_filter(raw, active, grid), active)
    return float(np.dot(weights, projected))


def _grid_dict(grid: LocalizedDesignGrid) -> dict[str, Any]:
    return {"origin": list(grid.origin), "spacing": list(grid.spacing), "cell_shape": list(grid.cell_shape), "cell_order": grid.cell_order}


def _save_array(path: Path, values: np.ndarray) -> None:
    np.save(path, values, allow_pickle=False)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")


__all__ = [
    "G4_B1_NUMERICAL_TOPOLOGY_FILENAME",
    "G4_B1_NUMERICAL_TOPOLOGY_KIND",
    "G4_B1_NUMERICAL_TOPOLOGY_SCHEMA_VERSION",
    "G4B1NumericalTopologyBenchmark",
    "run_g4_b1_numerical_topology_benchmark",
]
