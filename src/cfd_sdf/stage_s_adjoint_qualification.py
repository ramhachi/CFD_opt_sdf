"""Qualify the Work F base-adjoint derivative artifacts (Slice A).

Parses the two ``volumetricBSplines`` design-variable derivative files and the
control-point catalog, materializes the registered direction vectors on the
active B-spline variable space, and emits the append-only qualification
artifact. ``perturbation_allowed`` stays false unless every base gate passes.

The active-variable mapping is authoritative, not inferred from row order:
OpenFOAM's ``NURBS3DVolume::getCPID(i, j, k)`` is ``k*nCPsU*nCPsV + j*nCPsU + i``
and ``confineBoundaryControlPoints true`` leaves exactly the interior control
points ``i, j, k in [1, nCPs-2]`` active, each with three components. The
qualifier verifies that the derivative files' ``varID`` set equals that active
set exactly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

N_CONTROL_POINTS: tuple[int, int, int] = (8, 8, 8)
DERIVATIVE_HEADER_COLUMNS: tuple[str, ...] = (
    "#varID",
    "total",
    "dxdbVol",
    "dxdbSurf",
    "dSdb",
    "dndb",
    "dxdbDirect",
    "dVdb",
    "distance",
    "options",
    "dvdb",
)
DERIVATIVE_SIGN_CONVENTION: dict[str, str] = {
    "drag": "total = d(Cd)/dvar; the registered drag adjoint objective is the +x coefficient",
    "downforce": "total = d(downforce)/dvar; the +x-free downforce objective uses direction (0,0,-1)",
}


class AdjointQualificationError(ValueError):
    """Fail-closed derivative-qualification contract violation."""


@dataclass(frozen=True)
class DerivativeFile:
    """One parsed solver-specific design-variable derivative table."""

    path: str
    sha256: str
    solver: str
    final_iteration: int
    var_ids: tuple[int, ...]
    totals: tuple[float, ...]

    def total_by_var(self) -> dict[int, float]:
        return dict(zip(self.var_ids, self.totals, strict=True))


def active_var_ids(n_cps: tuple[int, int, int] = N_CONTROL_POINTS) -> tuple[int, ...]:
    """The interior control-point component ids, ordered by varID."""

    nx, ny, nz = (int(value) for value in n_cps)
    if nx < 3 or ny < 3 or nz < 3:
        raise AdjointQualificationError("at least three control points per direction are required")
    ids: list[int] = []
    for k in range(1, nz - 1):
        for j in range(1, ny - 1):
            for i in range(1, nx - 1):
                cp_id = k * nx * ny + j * nx + i
                ids.extend(cp_id * 3 + component for component in range(3))
    return tuple(sorted(ids))


def var_id_to_ijk_component(
    var_id: int, n_cps: tuple[int, int, int] = N_CONTROL_POINTS
) -> tuple[int, int, int, int]:
    """The authoritative ``varID -> (i, j, k, component)`` mapping."""

    nx, ny, nz = (int(value) for value in n_cps)
    total_components = nx * ny * nz * 3
    if not 0 <= var_id < total_components:
        raise AdjointQualificationError(f"varID {var_id} outside the control-point space")
    cp_id, component = divmod(var_id, 3)
    k, remainder = divmod(cp_id, nx * ny)
    j, i = divmod(remainder, nx)
    return i, j, k, component


def parse_derivative_file(path: str | Path, *, expected_solver: str) -> DerivativeFile:
    """Parse one derivative file fail-closed, including its solver identity."""

    source = Path(path)
    name = source.name
    if expected_solver not in name:
        raise AdjointQualificationError(
            f"derivative file {name!r} does not name the expected solver {expected_solver!r}"
        )
    iteration_match = None
    for token in name.split("ESI")[-1:]:
        digits = "".join(character for character in token if character.isdigit())
        if digits:
            iteration_match = int(digits)
    if iteration_match is None:
        raise AdjointQualificationError(f"derivative file {name!r} does not encode its final iteration")
    lines = [
        line
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    if not lines or tuple(lines[0].split()) != DERIVATIVE_HEADER_COLUMNS:
        raise AdjointQualificationError(f"derivative file {name!r} has an unexpected header")
    var_ids: list[int] = []
    totals: list[float] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != len(DERIVATIVE_HEADER_COLUMNS):
            raise AdjointQualificationError(f"derivative file {name!r} has a malformed row: {line!r}")
        var_id = int(parts[0])
        total = float(parts[1])
        if not np.isfinite(total):
            raise AdjointQualificationError(f"derivative file {name!r} has a non-finite total at varID {var_id}")
        var_ids.append(var_id)
        totals.append(total)
    return DerivativeFile(
        path=str(source),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        solver=expected_solver,
        final_iteration=iteration_match,
        var_ids=tuple(var_ids),
        totals=tuple(totals),
    )


def response_derivative_vector(
    derivative: DerivativeFile,
    *,
    active_ids: tuple[int, ...],
    objective_sign: float,
) -> np.ndarray:
    """The response derivative over the active variables with the registered sign."""

    by_var = derivative.total_by_var()
    if set(by_var) != set(active_ids):
        missing = sorted(set(active_ids) - set(by_var))[:5]
        extra = sorted(set(by_var) - set(active_ids))[:5]
        raise AdjointQualificationError(
            f"{derivative.solver}: derivative varID set does not match the active set; "
            f"missing={missing}, extra={extra}"
        )
    return np.asarray([by_var[var_id] for var_id in active_ids], dtype=np.float64) * float(objective_sign)


def materialize_direction(
    vector: np.ndarray, *, kind: str, seed: int | None = None
) -> dict[str, Any]:
    """Normalize one direction to unit infinity norm and record its identity."""

    values = np.asarray(vector, dtype=np.float64)
    if values.size == 0 or not np.isfinite(values).all():
        raise AdjointQualificationError(f"direction {kind!r} is empty or non-finite")
    inf_norm = float(np.max(np.abs(values)))
    if inf_norm <= 0.0:
        raise AdjointQualificationError(f"direction {kind!r} is the zero vector")
    unit = values / inf_norm
    array_sha = hashlib.sha256(np.ascontiguousarray(unit, dtype=np.float64).tobytes()).hexdigest()
    return {
        "kind": kind,
        "seed": seed,
        "inf_norm_before_normalization": inf_norm,
        "l2_norm": float(np.linalg.norm(unit)),
        "unit_inf_norm": float(np.max(np.abs(unit))),
        "sha256": array_sha,
        "values": [float(value) for value in unit],
    }


def random_direction(active_ids: tuple[int, ...], *, seed: int) -> np.ndarray:
    """Deterministic seeded normal field on the active variables only."""

    rng = np.random.default_rng(seed)
    return rng.standard_normal(len(active_ids))


def qualification_checks(
    *,
    drag: DerivativeFile,
    downforce: DerivativeFile,
    active_ids: tuple[int, ...],
) -> dict[str, bool]:
    return {
        "drag_var_ids_unique": len(set(drag.var_ids)) == len(drag.var_ids),
        "downforce_var_ids_unique": len(set(downforce.var_ids)) == len(downforce.var_ids),
        "drag_matches_active_set": set(drag.var_ids) == set(active_ids),
        "downforce_matches_active_set": set(downforce.var_ids) == set(active_ids),
        "same_var_id_set": set(drag.var_ids) == set(downforce.var_ids),
        "expected_active_count": len(active_ids) == len(drag.var_ids) == len(downforce.var_ids),
        "all_totals_finite": all(np.isfinite(value) for value in (*drag.totals, *downforce.totals)),
        "drag_solver_identity": drag.solver == "adjDrag",
        "downforce_solver_identity": downforce.solver == "adjDownforce",
    }


def build_direction_artifact(
    *,
    drag: DerivativeFile,
    downforce: DerivativeFile,
    active_ids: tuple[int, ...],
    random_seeds: tuple[int, ...],
    objective_signs: dict[str, float],
) -> dict[str, Any]:
    """The four registered unit-inf-norm directions on the active variable space."""

    checks = qualification_checks(drag=drag, downforce=downforce, active_ids=active_ids)
    if not all(checks.values()):
        raise AdjointQualificationError(
            "derivative qualification failed: "
            + ", ".join(sorted(key for key, value in checks.items() if not value))
        )
    directions: dict[str, dict[str, Any]] = {}
    for response, derivative in (("drag", drag), ("downforce", downforce)):
        vector = response_derivative_vector(
            derivative,
            active_ids=active_ids,
            objective_sign=objective_signs[response],
        )
        directions[f"{response}_gradient_aligned"] = materialize_direction(
            vector, kind="gradient_aligned"
        )
    for seed in random_seeds:
        directions[f"random_seed_{seed}"] = materialize_direction(
            random_direction(active_ids, seed=seed), kind="random", seed=seed
        )
    direction_hashes = {name: record["sha256"] for name, record in directions.items()}
    return {
        "active_var_ids": [int(value) for value in active_ids],
        "n_active_variables": len(active_ids),
        "checks": checks,
        "directions": directions,
        "direction_hashes": direction_hashes,
        "sign_convention": DERIVATIVE_SIGN_CONVENTION,
    }


def load_direction_artifact(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "AdjointQualificationError",
    "DERIVATIVE_HEADER_COLUMNS",
    "DERIVATIVE_SIGN_CONVENTION",
    "DerivativeFile",
    "N_CONTROL_POINTS",
    "active_var_ids",
    "build_direction_artifact",
    "load_direction_artifact",
    "materialize_direction",
    "parse_derivative_file",
    "qualification_checks",
    "random_direction",
    "response_derivative_vector",
    "var_id_to_ijk_component",
]
