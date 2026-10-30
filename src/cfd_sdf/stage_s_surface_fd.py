"""Stage S Work F surface-FD contract (body-fitted matched-Re laminar).

The Work F gate qualifies the drag and downforce surface directional
derivatives of the registered V1 body-fitted baseline. This module owns the
response identity contract, the surface basis and fixed-region registration,
the dimensionless epsilon ladder, the two response-specific FD manifests that
share one perturbation catalog, a solver-free worst-case geometry preflight,
and the per-response evaluation wrapper. It never runs OpenFOAM.

Registered semantics:

- the qualified responses are the *coefficients* the Stage V case writes:
  ``Cd`` (relative bound) and ``downforce`` (absolute bound); the Stage T
  objective ``J = -downforce`` is a separate sign convention and is never
  silently substituted;
- the outward surface normal is the perturbation direction; a positive
  epsilon displaces the free surface outward along the local normal;
- the gradient-aligned directions are derived from the base adjoint at run
  time (they are registered by role and sign convention, never by a
  post-result vector);
- epsilons are registered as dimensionless ratios of the V1 voxel size, and
  the two response manifests share the same catalog;
- a gradient-aligned analytic derivative below the registered noise floor is
  unresolved and fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .extraction_qualification import _triangles_self_intersect
from .fd_preregistration import (
    FdCampaignManifest,
    FdDirection,
    build_fd_campaign_manifest,
    evaluate_fd_campaign_rows,
)
from .fixed_grid_contract import CartesianCellGrid
from .handoff import _build_revoxelized_density
from .shape_feature_metrics import occupancy_metrics
from .stage_v_domain_preflight import (
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
)

WORK_F_RESPONSES: dict[str, dict[str, Any]] = {
    "drag": {
        "response_id": "drag",
        "direction": (1.0, 0.0, 0.0),
        "coefficient": "Cd",
        "objective_sign": 1.0,
        "bound_kind": "relative",
        "sign_convention": (
            "d(Cd)/d(normal displacement); the drag-adjoint objective is the "
            "declared +x drag response, so the analytic derivative is the "
            "faceSensNormal<drag> value with the adjoint objective sign applied"
        ),
    },
    "downforce": {
        "response_id": "downforce",
        "direction": (0.0, 0.0, -1.0),
        "coefficient": "downforce",
        "objective_sign": -1.0,
        "bound_kind": "absolute",
        "sign_convention": (
            "d(downforce)/d(normal displacement); OpenFOAM forceCoeffs liftDir is "
            "the negated downforce direction (0,0,1), so downforce = -Cl and the "
            "downforce-adjoint objective sign must be applied explicitly"
        ),
    },
}

DEFAULT_EPSILON_RATIOS: tuple[float, ...] = (0.002, 0.005, 0.01, 0.02)
DEFAULT_RANDOM_SEEDS: tuple[int, ...] = (11, 2026)
NEAR_ZERO_RELATIVE = 1.0e-3
NEAR_ZERO_ABSOLUTE_RATIO = 1.0e-4


@dataclass(frozen=True)
class SurfaceBasisSpec:
    """Registered surface-perturbation basis and its normalization."""

    kind: str
    box_m: tuple[tuple[float, float, float], tuple[float, float, float]]
    control_points: tuple[int, int, int]
    normalization: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "box_m": {"min": list(self.box_m[0]), "max": list(self.box_m[1])},
            "control_points": list(self.control_points),
            "normalization": self.normalization,
        }


@dataclass(frozen=True)
class FixedRegionSpec:
    """Regions that the perturbation may not move, and the displacement cap."""

    fixed_patches: tuple[str, ...]
    free_patch: str
    max_normal_displacement_m: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixed_patches": list(self.fixed_patches),
            "free_patch": self.free_patch,
            "max_normal_displacement_m": self.max_normal_displacement_m,
        }


@dataclass(frozen=True)
class EpsilonLadder:
    """Dimensionless epsilon ratios resolved against the registered voxel size."""

    voxel_size_m: float
    ratios: tuple[float, ...]

    @property
    def epsilons_m(self) -> tuple[float, ...]:
        return tuple(float(ratio) * float(self.voxel_size_m) for ratio in self.ratios)

    def to_dict(self) -> dict[str, Any]:
        return {
            "voxel_size_m": self.voxel_size_m,
            "ratios": list(self.ratios),
            "epsilons_m": list(self.epsilons_m),
        }


def build_epsilon_ladder(
    voxel_size_m: float, ratios: tuple[float, ...] = DEFAULT_EPSILON_RATIOS
) -> EpsilonLadder:
    if len(ratios) < 4:
        raise ValueError("the registered FD profile requires at least four epsilons")
    if any(ratio <= 0.0 for ratio in ratios):
        raise ValueError("epsilon ratios must be positive")
    return EpsilonLadder(voxel_size_m=float(voxel_size_m), ratios=tuple(float(r) for r in ratios))


def default_surface_basis(surface_bounds: np.ndarray) -> SurfaceBasisSpec:
    """A B-spline box that contains the registered surface with a small margin."""

    lower = np.asarray(surface_bounds[0], dtype=np.float64)
    upper = np.asarray(surface_bounds[1], dtype=np.float64)
    margin = 0.1 * (upper - lower)
    box = (
        tuple(float(value) for value in lower - margin),
        tuple(float(value) for value in upper + margin),
    )
    return SurfaceBasisSpec(
        kind="volumetricBSplines",
        box_m=box,
        control_points=(8, 8, 8),
        normalization="unit_inf_norm_over_the_free_surface",
    )


def default_fixed_regions(max_normal_displacement_m: float) -> FixedRegionSpec:
    return FixedRegionSpec(
        fixed_patches=("inlet", "outlet", "sideMin", "sideMax", "bottom", "top"),
        free_patch="design_candidate",
        max_normal_displacement_m=float(max_normal_displacement_m),
    )


def _direction_specs() -> tuple[FdDirection, ...]:
    directions = [
        FdDirection(
            name=f"{response}_gradient_aligned",
            role="gradient_aligned",
            seed=None,
            sign_convention=WORK_F_RESPONSES[response]["sign_convention"],
            description=(
                f"direction = normalized {response} surface gradient from the base "
                "adjoint, projected on the free surface"
            ),
        )
        for response in ("downforce", "drag")
    ]
    directions.extend(
        FdDirection(
            name=f"random_seed_{seed}",
            role="random",
            seed=seed,
            sign_convention=(
                "d(response)/d(normal displacement); the direction is a seeded unit "
                "normal field on the free surface"
            ),
            description=f"seeded random normal field on the free surface (seed {seed})",
        )
        for seed in DEFAULT_RANDOM_SEEDS
    )
    return tuple(directions)


def build_work_f_fd_manifests(
    *,
    baseline: dict[str, Any],
    problem_spec_sha256: str,
    level_name: str,
    voxel_size_m: float,
    response_scales: dict[str, float],
    basis: SurfaceBasisSpec,
    fixed_regions: FixedRegionSpec,
    ladder: EpsilonLadder,
    code_commit: str | None = None,
) -> dict[str, FdCampaignManifest]:
    """Two response-specific manifests sharing one perturbation catalog."""

    directions = _direction_specs()
    manifests: dict[str, FdCampaignManifest] = {}
    for response, identity in WORK_F_RESPONSES.items():
        scale = float(response_scales[response])
        manifests[response] = build_fd_campaign_manifest(
            campaign_id=f"stage_s_work_f_{response}_surface_fd_2026_09",
            hypothesis=(
                f"the base {response} surface adjoint on the registered V1 body-fitted "
                "baseline agrees with centered FD of the same response within the "
                "registered profile"
            ),
            decision=(
                f"qualify the {response} surface directional derivative; a failure "
                "keeps the shape update unauthorized"
            ),
            fixture={
                "candidate_binding": baseline["handoff"]["pq4_1_artifact"]["path"],
                "candidate_rho_sha256": baseline["candidate"]["rho_sha256"],
                "surface_stl_sha256": baseline["handoff"]["artifacts"]["surface_stl"]["sha256"],
                "problem_spec_sha256": str(problem_spec_sha256),
                "grid_family": f"body_fitted_{level_name}_{voxel_size_m:g}m",
                "refinement_ratio": 1.0,
                "response_scale": scale,
                "near_zero_relative": NEAR_ZERO_RELATIVE,
                "near_zero_absolute_error": NEAR_ZERO_ABSOLUTE_RATIO * scale,
                "response_identity": identity,
                "surface_basis": basis.to_dict(),
                "fixed_regions": fixed_regions.to_dict(),
                "epsilon_ladder": ladder.to_dict(),
            },
            responses=[response],
            epsilons=ladder.epsilons_m,
            directions=directions,
            uncertainty_rule=(
                "centered-difference relative error against the analytic directional "
                "derivative; a gradient-aligned analytic below the registered noise "
                "floor is unresolved and fails closed; near-zero non-aligned "
                "directions use the pre-registered absolute error rule"
            ),
            gates={
                "convergence": (
                    "every perturbation primal meets the registered problem-spec "
                    "residual convergence; no unconverged run enters the FD table"
                ),
                "stationarity": "response stationarity window per the registered Stage V profile",
                "mesh": "the registered stage_v_qualification_v1 mesh profile on every perturbation case",
                "geometry": (
                    "baseline/spec/hash binding plus watertight, manifold, "
                    "non-self-intersecting, volume, width/gap and clearance gates on "
                    "both the +epsilon and -epsilon surfaces"
                ),
                "required_pairs": (
                    "both gradient-aligned directions and every registered random seed "
                    "at every registered epsilon; a pair fails if either side fails"
                ),
                "resolvability": (
                    "relative error <= 5% and sign agreement; otherwise the row is "
                    "resolved as fail, never dropped"
                ),
            },
            stop_conditions=(
                "stop and re-register if any perturbation pair misses a geometry, mesh, residual or stationarity gate",
                "never change epsilons, seeds, directions or tolerances after the first response value",
                "do not run a shape update from this campaign",
            ),
            fallback_conditions=(
                "if the analytic derivative is below the noise floor, record the response as unresolved",
                "diagnose sign, surface-area weighting, normal convention and morpher one factor at a time",
            ),
            code_commit=code_commit,
        )
    return manifests


def worst_case_offset_mesh(mesh, offset_m: float):
    """Offset every vertex along its outward normal (a conservative bound)."""

    import trimesh

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
    offset = trimesh.Trimesh(
        vertices=vertices + float(offset_m) * normals,
        faces=np.asarray(mesh.faces, dtype=np.int64),
        process=True,
    )
    return offset


def worst_case_geometry_checks(
    *,
    baseline_mesh,
    spec,
    grid: CartesianCellGrid,
    epsilons_m: tuple[float, ...],
    clearance_profile: dict[str, Any] = STAGE_V_CLEARANCE_PROFILE_V1,
) -> dict[str, Any]:
    """Watertight/manifold/self-intersection/volume/width/clearance gates per epsilon.

    The uniform outward/inward normal offset is the conservative bound for any
    unit-normal perturbation of magnitude epsilon: if the bound passes, every
    smoother registered direction at that epsilon passes the geometry gates.
    """

    import tempfile
    from pathlib import Path

    baseline_volume = float(baseline_mesh.volume)
    results: dict[str, Any] = {}
    for epsilon in epsilons_m:
        for sign, label in ((1.0, "plus"), (-1.0, "minus")):
            offset_mesh = worst_case_offset_mesh(baseline_mesh, sign * float(epsilon))
            entry: dict[str, Any] = {
                "epsilon_m": float(epsilon),
                "sign": label,
                "watertight": bool(offset_mesh.is_watertight),
                "winding_consistent": bool(offset_mesh.is_winding_consistent),
                "positive_volume": bool(offset_mesh.volume > 0.0),
                "self_intersection": _triangles_self_intersect(offset_mesh),
                "volume_m3": float(offset_mesh.volume),
                "volume_relative_difference": float(
                    abs(offset_mesh.volume - baseline_volume) / max(baseline_volume, 1e-30)
                ),
            }
            revoxelized = _build_revoxelized_density(offset_mesh, grid)
            material = np.asarray(revoxelized, dtype=bool)
            metrics = occupancy_metrics(material, float(grid.spacing[0]))
            entry["minimum_solid_width_m"] = metrics.get("thickness_ridge_m_min")
            with tempfile.TemporaryDirectory() as tmp:
                stl_path = Path(tmp) / "offset.stl"
                offset_mesh.export(stl_path)
                preflight = evaluate_stage_v_domain_preflight(
                    spec,
                    stl_path,
                    float(spec.grid.voxel_size_m),
                    profile=clearance_profile,
                )
            entry["clearance_qualified"] = bool(preflight.qualified)
            entry["clearance_reasons"] = list(preflight.reasons)
            entry["pass"] = bool(
                entry["watertight"]
                and entry["winding_consistent"]
                and entry["positive_volume"]
                and entry["self_intersection"] == "none"
                and entry["clearance_qualified"]
            )
            results[f"{float(epsilon):.6g}_{label}"] = entry
    return {
        "baseline_volume_m3": baseline_volume,
        "epsilons_m": list(epsilons_m),
        "rows": results,
        "all_pass": all(entry["pass"] for entry in results.values()),
    }


def evaluate_work_f_fd(
    manifests: dict[str, FdCampaignManifest],
    *,
    rows: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Per-response verdicts; the combined gate requires both responses to pass.

    In addition to the registered row evaluation, each response's own
    gradient-aligned direction must be resolvable above the registered noise
    floor; a below-noise primary derivative is unresolved and fails closed even
    when the absolute rule would tolerate it.
    """

    verdicts: dict[str, Any] = {}
    for response, manifest in manifests.items():
        near_zero_relative = float(manifest.fixture["near_zero_relative"])
        scale = abs(float(manifest.fixture["response_scale"]))
        threshold = near_zero_relative * scale
        verdict = evaluate_fd_campaign_rows(
            manifest,
            rows[response],
            near_zero_relative=near_zero_relative,
        )
        primary = f"{response}_gradient_aligned"
        primary_rows = [row for row in rows[response] if row.get("direction") == primary]
        resolved = bool(primary_rows) and all(
            abs(float(row["analytic"])) >= threshold for row in primary_rows
        )
        if not resolved:
            verdict["passed"] = False
            verdict.setdefault("failures", []).append(
                {"direction": primary, "reason": "near_zero_gradient_aligned_unresolved"}
            )
        verdict["primary_gradient_aligned_resolved"] = resolved
        verdicts[response] = verdict
    return {
        "responses": verdicts,
        "both_pass": all(verdict["passed"] for verdict in verdicts.values()),
        "shape_update_allowed": False,
    }


__all__ = [
    "DEFAULT_EPSILON_RATIOS",
    "DEFAULT_RANDOM_SEEDS",
    "EpsilonLadder",
    "FixedRegionSpec",
    "NEAR_ZERO_ABSOLUTE_RATIO",
    "NEAR_ZERO_RELATIVE",
    "SurfaceBasisSpec",
    "WORK_F_RESPONSES",
    "build_epsilon_ladder",
    "build_work_f_fd_manifests",
    "default_fixed_regions",
    "default_surface_basis",
    "evaluate_work_f_fd",
    "worst_case_geometry_checks",
    "worst_case_offset_mesh",
]
