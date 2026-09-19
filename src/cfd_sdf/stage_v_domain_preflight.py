"""Fixed far-field domain binding and pre-mesh physical clearance preflight.

Implements the WP1 slice of `docs/opencode_handoff_2026_09.md` (P17):
`blockMesh`/`snappyHexMesh` far-field planes must come from the ProblemSpec's
declared ``grid.domain_bounds_m`` rather than from the candidate's union bounds,
and a declared physical clearance between the candidate surface and every
axis-aligned far-field plane must be checked BEFORE any mesh command runs.

Everything here is fail-closed: a missing or invalid domain, a candidate point
outside the fixed box, or a clearance below the declared margin refuses the
Stage V case and never produces a solver-launch permission. The margin is a
declared physical length in a versioned profile; it is never inferred from a
run result or from cell counts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import trimesh

from .problem_spec import ProblemSpec, problem_spec_sha256

# ---------------------------------------------------------------------------
# Versioned clearance profile. The margin is a declared physical length, not a
# cell-derived quantity: the recorded V3 clearance failure
# (candidate `opt_q100_b0_stage5..._keep_round`, docs/problem_register_2026_09.md P17)
# left roughly one finest background cell (~0.0125 m) between the candidate and
# the far-field `top` patch and produced 220 under-determined cells. A margin
# far above any achievable background cell width is therefore required before
# meshing. Fixed now, before any new run is judged.
# ---------------------------------------------------------------------------

STAGE_V_CLEARANCE_PROFILE_V1: dict[str, Any] = {
    "profile_id": "stage_v_clearance_v1",
    "minimum_clearance_m": 0.25,
    # Patch naming matches the fixed-domain blockMeshDict in cfd_sdf.openfoam:
    # x-lower=inlet, x-upper=outlet, y-lower=sideMin, y-upper=sideMax,
    # z-lower=bottom, z-upper=top.
    "clearance_patches": {
        "lower_x": "inlet",
        "upper_x": "outlet",
        "lower_y": "sideMin",
        "upper_y": "sideMax",
        "lower_z": "bottom",
        "upper_z": "top",
    },
}

_SCHEMA_VERSION = 1

_DOMAIN_ALIGNMENT_TOLERANCE_M = 1.0e-9

# Inside-the-box tolerance: binary STL stores coordinates as float32, so a
# candidate exactly touching the declared plane can appear ~1e-7 m outside.
# The clearance gate below still fails exact contact (clearance ~0 < margin).
_INSIDE_BOX_TOLERANCE_M = 1.0e-6


@dataclass(frozen=True)
class StageVDomainPreflight:
    """Fail-closed verdict plus all measured values for one candidate/level."""

    qualified: bool
    reasons: tuple[str, ...]
    domain_bounds_m: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    voxel_size_m: float | None
    flow_case_id: str | None
    candidate_stl: Path | None
    candidate_stl_sha256: str | None
    problem_spec_sha256_value: str | None
    candidate_bounds_m: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    inside_fixed_box: bool | None
    clearances_m: dict[str, float] | None
    limiting_patch: str | None
    minimum_clearance_m_: float | None
    profile_id: str
    declared_minimum_clearance_m: float

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "pass" if self.qualified else "fail",
            "qualified": self.qualified,
            "reasons": list(self.reasons),
            "qualification_profile": {
                "profile_id": self.profile_id,
                "minimum_clearance_m": self.declared_minimum_clearance_m,
            },
            "fixed_domain_binding": {
                "from_problem_spec_grid_domain_bounds_m": True,
                "domain_bounds_m": (
                    None
                    if self.domain_bounds_m is None
                    else {"lower": list(self.domain_bounds_m[0]), "upper": list(self.domain_bounds_m[1])}
                ),
            },
            "voxel_size_m": self.voxel_size_m,
            "flow_case_id": self.flow_case_id,
            "candidate_stl": None if self.candidate_stl is None else str(self.candidate_stl),
            "candidate_stl_sha256": self.candidate_stl_sha256,
            "problem_spec_sha256": self.problem_spec_sha256_value,
            "candidate_bounds_m": (
                None
                if self.candidate_bounds_m is None
                else {"lower": list(self.candidate_bounds_m[0]), "upper": list(self.candidate_bounds_m[1])}
            ),
            "candidate_inside_fixed_box": self.inside_fixed_box,
            "clearances_m": None if self.clearances_m is None else dict(self.clearances_m),
            "limiting_patch": self.limiting_patch,
            "minimum_clearance_m": self.minimum_clearance_m_,
            "measured_before_any_mesh_command": True,
        }
        return data


def evaluate_stage_v_domain_preflight(
    spec: ProblemSpec,
    candidate_stl: str | Path,
    voxel_size_m: float,
    *,
    flow_case_id: str | None = None,
    profile: Mapping[str, Any] = STAGE_V_CLEARANCE_PROFILE_V1,
) -> StageVDomainPreflight:
    """Judge one candidate/domain/voxel combination before any meshing runs."""

    bounds = spec.grid.domain_bounds_m
    margin = float(profile["minimum_clearance_m"])
    patches = dict(profile["clearance_patches"])

    reasons: list[str] = []
    domain_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    candidate_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    clearance_values: dict[str, float] | None = None
    inside: bool | None = None
    limiting_patch: str | None = None
    minimum_clearance: float | None = None
    flow_case_id_ = flow_case_id

    if bounds is None:
        reasons.append("domain_bounds_missing")
    else:
        lower = np.asarray(bounds.lower, dtype=float)
        upper = np.asarray(bounds.upper, dtype=float)
        extents = upper - lower
        if (
            not np.all(np.isfinite(lower))
            or not np.all(np.isfinite(upper))
            or np.any(extents <= 0.0)
        ):
            reasons.append("domain_bounds_invalid")
        else:
            domain_bounds = (tuple(float(x) for x in bounds.lower), tuple(float(x) for x in bounds.upper))
            if spec.grid.padding_m:
                reasons.append("grid_padding_m_must_be_zero_with_declared_domain")
            if voxel_size_m is None or not isfinite(voxel_size_m) or voxel_size_m <= 0.0:
                reasons.append("voxel_size_m_invalid")
            else:
                cells = extents / float(voxel_size_m)
                if np.any(np.abs(cells - np.round(cells)) * float(voxel_size_m) > _DOMAIN_ALIGNMENT_TOLERANCE_M):
                    reasons.append("voxel_alignment_invalid")

    candidate_path: Path | None = None
    stl_sha: str | None = None
    try:
        candidate_path = Path(candidate_stl)
        candidate_path = candidate_path if candidate_path.is_absolute() else (spec.path.parent / candidate_path)
        stl_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        mesh = trimesh.load_mesh(candidate_path)
        if mesh.is_empty:
            reasons.append("candidate_stl_empty")
        else:
            lo = np.asarray(mesh.bounds[0], dtype=float)
            hi = np.asarray(mesh.bounds[1], dtype=float)
            candidate_bounds = (tuple(lo.tolist()), tuple(hi.tolist()))
            if (
                bounds is not None
                and candidates_finite(lo, hi)
                and "domain_bounds_invalid" not in reasons
            ):
                d_lo = np.asarray(bounds.lower, dtype=float)
                d_hi = np.asarray(bounds.upper, dtype=float)
                lower_gap = lo - d_lo
                upper_gap = d_hi - hi
                inside = bool(
                    np.all(lower_gap >= -_INSIDE_BOX_TOLERANCE_M)
                    and np.all(upper_gap >= -_INSIDE_BOX_TOLERANCE_M)
                )
                # Clearance measurements stay separate from the verdict so a
                # failing artifact still records every measured value.
                measured = {
                    f"{patches['lower_x']} (lower_x)": lower_gap[0],
                    f"{patches['upper_x']} (upper_x)": upper_gap[0],
                    f"{patches['lower_y']} (lower_y)": lower_gap[1],
                    f"{patches['upper_y']} (upper_y)": upper_gap[1],
                    f"{patches['lower_z']} (lower_z)": lower_gap[2],
                    f"{patches['upper_z']} (upper_z)": upper_gap[2],
                }
                if not np.all(np.isfinite(list(measured.values()))):
                    reasons.append("clearance_non_finite")
                else:
                    clearance_values = {key: float(value) for key, value in measured.items()}
                    limiting_patch, minimum_clearance = min(
                        measured.items(), key=lambda item: float(item[1])
                    )
                    limiting_patch = str(limiting_patch)
                    minimum_clearance = float(minimum_clearance)
                    if inside is False:
                        reasons.append("candidate_outside_fixed_domain")
                    if minimum_clearance < margin:
                        reasons.append("clearance_below_declared_margin")
    except FileNotFoundError:
        reasons.append("candidate_stl_missing")
    except (OSError, ValueError):
        reasons.append("candidate_stl_unreadable")

    return StageVDomainPreflight(
        qualified=not reasons,
        reasons=tuple(reasons),
        domain_bounds_m=domain_bounds,
        voxel_size_m=None if voxel_size_m is None else float(voxel_size_m),
        flow_case_id=flow_case_id_,
        candidate_stl=candidate_path,
        candidate_stl_sha256=stl_sha,
        problem_spec_sha256_value=problem_spec_sha256(spec),
        candidate_bounds_m=candidate_bounds,
        inside_fixed_box=inside,
        clearances_m=clearance_values,
        limiting_patch=limiting_patch,
        minimum_clearance_m_=minimum_clearance,
        profile_id=str(profile["profile_id"]),
        declared_minimum_clearance_m=margin,
    )


def candidates_finite(lo: np.ndarray, hi: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(lo)) and np.all(np.isfinite(hi)))


def write_stage_v_domain_preflight_report(
    case_dir: str | Path,
    preflight: StageVDomainPreflight,
    filename: str = "stage_v_domain_preflight.json",
) -> Path:
    """Write the preflight verdict before any mesh/solver command in ``case_dir``.

    A failed preflight may record this diagnostic artifact; it must never be
    confused with permission to launch ``blockMesh``/``snappyHexMesh``/``simpleFoam``.
    """

    path = Path(case_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preflight.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
