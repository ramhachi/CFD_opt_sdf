"""SDF-native geometry hard-gate bundle (GEOM-01, contract v1).

One fail-closed bundle applied to every proposed or accepted
:class:`~cfd_sdf.design.sdf_state.SDFDesignState`.  Each gate returns
``pass`` / ``fail`` / ``unmeasured`` and the bundle passes only if every gate
passes: an unregistered threshold, a missing input or an unevaluable
measurement is ``unmeasured`` and blocks acceptance exactly like a failure.
Nothing here proposes, modifies or optimizes an SDF, and no solver runs.

Reuse decisions (see ``docs/sdf_native_geometry_gates_contract_v1_2026_09.md``):

- topology, mask, root and component rules come from the #31
  :func:`evaluate_sdf_topology_transition` checker; its violation strings are
  partitioned into gates, never re-derived;
- volumes come from the #27 ``volume_semantics`` module;
- the P20-repaired triangle self-intersection detector is reused from
  ``extraction_qualification`` rather than copied;
- the historical ``component_boundary_gap_m`` is NOT reused: it picks the
  Euclidean-nearest cell pair and can overestimate a gap (anti-conservative).
  The gap here is exact for axis-aligned cell faces.

Occupancy conventions: topology/mask/root rules use node occupancy
``phi < 0`` (the #31 registered rule); volume, feature widths, gaps,
clearance and the export surface use the registered cell-centre occupancy
(trilinear mean of the eight nodes ``< 0``), which is the ``V_phi`` rule.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage

from ..extraction_qualification import _triangles_self_intersect as triangles_self_intersect
from .sdf_state import SIGN_CONVENTION, SDFDesignState
from .topology_policy import (
    SDFTopologyPolicy,
    SDFTopologyPolicyError,
    evaluate_sdf_topology_transition,
)
from .volume_semantics import (
    _corner_mean,
    node_occupancy_volume_m3,
    sharp_volume_m3,
    smoothed_volume_and_gradient,
)

GEOMETRY_GATES_CONTRACT_ID = "sdf_native_geometry_gates_v1"
GEOMETRY_GATES_SCHEMA_VERSION = 1
GATE_IDS = (
    "sdf_finite_structure",
    "sdf_distance_property",
    "near_zero_gradient_band",
    "sdf_boundary_margin",
    "mask_preservation",
    "component_connectivity",
    "topology_change_classification",
    "min_feature_width",
    "inter_component_gap",
    "export_surface_integrity",
    "surface_self_intersection",
    "domain_clearance",
    "volume_semantics",
)

# Thresholds fixed by this contract before any measurement (structural, not physical).
BOUNDARY_MARGIN_CELLS = 1
SURFACE_VOLUME_RELATIVE_TOLERANCE = 1e-6
FEATURE_SUPERSAMPLE = 4
LENGTH_TOLERANCE_M = 1e-9
LOW_GRADIENT_BAND_M = 0.05
CELL_GAP_RESOLUTION_GUARD = 1.0

_S26 = np.ones((3, 3, 3), dtype=bool)
_MASK_REASONS = frozenset(
    {
        "state_mask_mismatch",
        "material_in_forbidden_mask",
        "material_outside_design_fixed_root_masks",
        "fixed_solid_not_retained",
        "root_material_not_retained",
        "required_root_region_not_material",
        "root_group_masks_do_not_match_state_root_mask",
    }
)
_EVENT_REASONS = frozenset(
    {
        "topology_birth_disabled",
        "component_deletion_disabled",
        "state_grid_mismatch",
        "state_shape_mismatch",
    }
)
_ALWAYS_UNMEASURED = frozenset({"root_group_masks_missing", "required_root_groups_unresolved"})
_UNBOUND_POLICY_REASONS = frozenset({
    "current_state_policy_hash_mismatch",
    "proposed_state_policy_hash_mismatch",
    "root_group_masks_missing",
    "required_root_groups_unresolved",
})
_UNDECIDED_EVENT_REASONS = frozenset({"topology_birth_disabled", "component_deletion_disabled"})


def _gate(fail=(), unmeasured=(), measured=None, thresholds=None) -> dict[str, Any]:
    fail, unmeasured = sorted(set(fail)), sorted(set(unmeasured))
    return {
        "status": "fail" if fail else ("unmeasured" if unmeasured else "pass"),
        "fail_reasons": fail,
        "unmeasured_reasons": unmeasured,
        "measured": measured or {},
        "thresholds": thresholds or {},
    }


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


def _minimum_measure_gate(value, limit, guard_m, label):
    if limit is None:
        return _gate(unmeasured=[f"minimum_{label}_unregistered"])
    if value is None:
        return _gate(unmeasured=[f"{label}_not_measurable"])
    if value < limit - guard_m - LENGTH_TOLERANCE_M:
        return _gate(fail=[f"minimum_{label}_violation"])
    if value <= limit + guard_m + LENGTH_TOLERANCE_M:
        return _gate(unmeasured=[f"{label}_within_sampling_guard_of_limit"])
    return _gate()


def cell_occupancy(state: SDFDesignState) -> np.ndarray:
    """Registered V_phi occupancy: h-cubes whose trilinear centre sample is < 0."""

    return _corner_mean(state.phi) < 0.0


def min_feature_width_m(mask: np.ndarray, spacing_m: float) -> float | None:
    """Sampled ``2*EDT`` ridge-width estimate on 4x cell occupancy.

    Edge padding avoids artificial boundary ridges. This is not a guaranteed
    continuous-geometry minimum; values near a registered limit are unresolved
    within one supersample spacing.
    """

    if not mask.any() or mask.all():
        return None
    up = np.pad(mask, 1, mode="edge")
    for axis in range(3):
        up = np.repeat(up, FEATURE_SUPERSAMPLE, axis=axis)
    distance = ndimage.distance_transform_edt(up, sampling=spacing_m / FEATURE_SUPERSAMPLE)
    ridge = up & (distance >= ndimage.maximum_filter(distance, size=3) - 1e-12)
    pad = FEATURE_SUPERSAMPLE
    interior_distance = distance[pad:-pad, pad:-pad, pad:-pad]
    interior_ridge = ridge[pad:-pad, pad:-pad, pad:-pad]
    if not interior_ridge.any():
        return None
    return float(2.0 * interior_distance[interior_ridge].min())


def min_component_gap_m(labels: np.ndarray, count: int, spacing_m: float) -> float | None:
    """Minimum face-to-face gap estimate between labelled cell-union components.

    Cube-to-cube distance is ``sqrt(sum(max(|d_i| - 1, 0)^2)) * h`` in cell
    offsets ``d``; the distance is exact for the sampled cell union, not the
    underlying continuous SDF geometry. The calling gate applies a one-cell
    resolution guard around a registered policy limit.
    """

    best = None
    for label in range(1, count):
        dilated = ndimage.binary_dilation(labels == label, structure=_S26)
        distance = ndimage.distance_transform_edt(~dilated, sampling=spacing_m)
        later = distance[labels > label]
        if later.size:
            best = float(later.min()) if best is None else min(best, float(later.min()))
    return best


def _gradient_diagnostics(state: SDFDesignState) -> dict[str, Any] | None:
    if min(state.shape) < 3:
        return None
    gradient = np.gradient(state.phi.astype(np.float64), float(state.spacing_m))
    norm = np.sqrt(sum(np.square(axis) for axis in gradient))
    interior = np.zeros(state.shape, dtype=bool)
    interior[1:-1, 1:-1, 1:-1] = True
    narrow = interior & (np.abs(state.phi) <= state.narrow_band_width_m)
    low_gradient_band = interior & (np.abs(state.phi) <= LOW_GRADIENT_BAND_M)
    if not narrow.any() and not low_gradient_band.any():
        return None
    if not np.isfinite(norm[narrow | low_gradient_band]).all():
        return None
    out: dict[str, Any] = {
        "eikonal_band_node_count": int(narrow.sum()),
        "low_gradient_band_m": LOW_GRADIENT_BAND_M,
        "low_gradient_band_node_count": int(low_gradient_band.sum()),
    }
    if low_gradient_band.any():
        low_norm = norm[low_gradient_band]
        out.update(
            gradient_norm_min=float(low_norm.min()),
            gradient_norm_p01=float(np.percentile(low_norm, 1)),
            gradient_norm_median=float(np.median(low_norm)),
            gradient_norm_p99=float(np.percentile(low_norm, 99)),
            prior_descriptive_bins={
                "below_1e-6_count": int(np.count_nonzero(low_norm < 1e-6)),
                "at_or_above_0_25_count": int(np.count_nonzero(low_norm >= 0.25)),
                "meaning": "descriptive only; not a registered acceptance threshold",
            },
        )
    if narrow.any():
        deviation = np.abs(norm[narrow] - 1.0)
        out.update(
            median_abs_gradient_deviation=float(np.median(deviation)),
            p95_abs_gradient_deviation=float(np.percentile(deviation, 95)),
            max_abs_gradient_deviation=float(deviation.max()),
        )
    return out


def _clearances_m(occupancy: np.ndarray, state: SDFDesignState, bounds) -> dict[str, float] | None:
    idx = np.argwhere(occupancy)
    if idx.size == 0:
        return None
    h = float(state.spacing_m)
    origin = np.asarray(state.origin_m, dtype=np.float64)
    if bounds is None:
        lo_dom = origin
        hi_dom = origin + (np.asarray(state.shape) - 1) * h
    else:
        lo_dom, hi_dom = (np.asarray(b, dtype=np.float64) for b in bounds)
    lo_body = origin + idx.min(axis=0) * h
    hi_body = origin + (idx.max(axis=0) + 1) * h
    out: dict[str, float] = {}
    for axis, name in enumerate("xyz"):
        out[f"lower_{name}"] = float(lo_body[axis] - lo_dom[axis])
        out[f"upper_{name}"] = float(hi_dom[axis] - hi_body[axis])
    return out


def export_surface(state: SDFDesignState):
    """Diagnostic voxel-cell-union surface nets, not the canonical SDF export.

    Returns ``None`` for an empty occupancy. Canonical SDF zero-level/STL
    qualification requires the actual exported mesh as a separate input.
    """

    import pyvista as pv
    import trimesh

    occupancy = cell_occupancy(state)
    if not occupancy.any():
        return None
    h = float(state.spacing_m)
    image = pv.ImageData(dimensions=tuple(state.shape), spacing=(h, h, h), origin=state.origin_m)
    image.cell_data["material"] = occupancy.astype(np.int32).ravel(order="F")
    surface = image.contour_labels(
        boundary_style="external",
        background_value=0,
        select_inputs=[1],
        output_mesh_type="triangles",
        scalars="material",
        pad_background=True,
        smoothing=False,
    )
    surface = surface.clean(tolerance=0.02 * h, absolute=True).triangulate()
    faces = np.asarray(surface.faces).reshape(-1, 4)[:, 1:4]
    return trimesh.Trimesh(np.asarray(surface.points, dtype=np.float64), faces, process=False)


def surface_gates(mesh, expected_volume_m3: float, node_components: int, cell_components: int):
    """(export_surface_integrity, surface_self_intersection) gates for one mesh."""

    thresholds = {"volume_relative_tolerance": SURFACE_VOLUME_RELATIVE_TOLERANCE}
    if mesh is None or len(mesh.faces) == 0:
        return (
            _gate(fail=["mesh_empty"], thresholds=thresholds),
            _gate(unmeasured=["no_mesh_to_evaluate"]),
        )
    faces = np.asarray(mesh.faces)
    _, edge_counts = np.unique(np.sort(mesh.edges_sorted, axis=1), axis=0, return_counts=True)
    volume = float(mesh.volume) if mesh.is_volume else 0.0
    measured = {
        "triangle_count": int(len(faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "non_manifold_edge_count": int(np.count_nonzero(edge_counts != 2)),
        "duplicate_face_count": int(len(faces) - np.unique(np.sort(faces, axis=1), axis=0).shape[0]),
        "mesh_volume_m3": volume,
        "expected_volume_m3": float(expected_volume_m3),
        "node_occupancy_components": int(node_components),
        "cell_occupancy_components": int(cell_components),
    }
    fail = []
    if not measured["watertight"]:
        fail.append("mesh_not_watertight")
    if not measured["winding_consistent"]:
        fail.append("mesh_winding_inconsistent")
    if measured["non_manifold_edge_count"]:
        fail.append("mesh_has_non_manifold_edges")
    if measured["duplicate_face_count"]:
        fail.append("mesh_has_duplicate_faces")
    if volume <= 0.0:
        fail.append("mesh_volume_not_positive")
    if abs(volume - expected_volume_m3) > SURFACE_VOLUME_RELATIVE_TOLERANCE * expected_volume_m3:
        fail.append("mesh_volume_mismatch")
    if node_components != cell_components:
        fail.append("node_cell_component_count_mismatch")
    integrity = _gate(fail=fail, measured=measured, thresholds=thresholds)

    verdict = triangles_self_intersect(mesh)
    if verdict == "none":
        intersection = _gate(measured={"detector_verdict": verdict})
    elif verdict == "fail":
        intersection = _gate(fail=["mesh_self_intersects"], measured={"detector_verdict": verdict})
    else:
        intersection = _gate(unmeasured=[verdict], measured={"detector_verdict": verdict})
    return integrity, intersection


def _partition(violations) -> tuple[dict[str, list[str]], list[str]]:
    """Split #31 violations into per-gate lists; the feature-width parts are ignored."""

    parts: dict[str, list[str]] = {"masks": [], "events": [], "connectivity": []}
    ignored = []
    for reason in violations:
        if reason.startswith("minimum_") or reason == "feature_measurements_missing":
            ignored.append(reason)  # measured by min_feature_width / inter_component_gap
        elif reason in _MASK_REASONS:
            parts["masks"].append(reason)
        elif reason in _EVENT_REASONS:
            parts["events"].append(reason)
        else:
            parts["connectivity"].append(reason)
    return parts, ignored


def evaluate_geometry_gates(
    state: SDFDesignState,
    *,
    policy: SDFTopologyPolicy,
    parent_state: SDFDesignState | None,
    root_group_masks: dict[str, np.ndarray] | None,
    volume_limit_m3: float | None,
    min_clearance_m: float | None = None,
    eikonal_median_tolerance: float | None = None,
    low_gradient_norm_floor: float | None = None,
    boundary_margin_cells: int = BOUNDARY_MARGIN_CELLS,
    domain_bounds_m: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None,
    policy_scope: str = "canonical_unresolved",
) -> dict[str, Any]:
    """Evaluate every gate for ``state``; the verdict is the AND of all gates.

    ``policy`` supplies all width/gap/root limits (ProblemSpec v2 source; an
    unresolved policy makes the dependent gates ``unmeasured``).  ``None`` for
    ``volume_limit_m3``, ``min_clearance_m`` or ``eikonal_median_tolerance``
    means the value is unregistered and the gate is ``unmeasured``.
    ``parent_state=None`` leaves the topology-change gate ``unmeasured``; pass
    the state itself as its own parent for an identity transition.
    """

    if not isinstance(state, SDFDesignState) or not isinstance(policy, SDFTopologyPolicy):
        raise TypeError("state must be an SDFDesignState and policy an SDFTopologyPolicy")
    if policy_scope not in {"canonical_unresolved", "fixture_only"}:
        raise ValueError("policy_scope must be 'canonical_unresolved' or 'fixture_only'")
    gates: dict[str, dict[str, Any]] = {}

    # --- finite / canonical structure -------------------------------------
    finite = bool(np.isfinite(state.phi).all())
    fail = []
    if not finite:
        fail.append("phi_not_finite")
    if state.phi.dtype != np.float32 or state.phi.ndim != 3:
        fail.append("phi_not_3d_float32")
    if state.sign_convention != SIGN_CONVENTION:
        fail.append("sign_convention_not_negative_inside")
    if state.recompute_sha256() != state.state_sha256:
        fail.append("state_sha256_mismatch")
    measured: dict[str, Any] = {"phi_finite": finite}
    if finite:
        measured.update(phi_min=float(state.phi.min()), phi_max=float(state.phi.max()))
        if not state.phi.min() < 0.0:
            fail.append("no_solid_phi")
        if not state.phi.max() > 0.0:
            fail.append("no_fluid_phi")
    gates["sdf_finite_structure"] = _gate(fail=fail, measured=measured)

    if not finite:
        blocked = _gate(unmeasured=["sdf_not_finite"])
        for gate_id in GATE_IDS[1:]:
            gates[gate_id] = dict(blocked)
        return _bundle(state, parent_state, policy, gates, policy_scope)

    occupancy = cell_occupancy(state)
    h = float(state.spacing_m)
    if not occupancy.any():
        gates["sdf_finite_structure"] = _gate(
            fail=gates["sdf_finite_structure"]["fail_reasons"] + ["solid_cell_occupancy_empty"],
            measured=measured,
        )

    # --- distance (eikonal) property --------------------------------------
    eikonal = _gradient_diagnostics(state)
    unmeasured = []
    fail = []
    if eikonal is None or "median_abs_gradient_deviation" not in eikonal:
        unmeasured.append("no_narrow_band_interior_nodes")
    elif eikonal_median_tolerance is None:
        unmeasured.append("eikonal_median_tolerance_unregistered")
    elif not math.isfinite(eikonal_median_tolerance) or eikonal_median_tolerance < 0.0:
        unmeasured.append("eikonal_median_tolerance_invalid")
    elif eikonal["median_abs_gradient_deviation"] > eikonal_median_tolerance:
        fail.append("phi_not_a_distance_field")
    gates["sdf_distance_property"] = _gate(
        fail, unmeasured, eikonal, {"eikonal_median_tolerance": eikonal_median_tolerance}
    )
    gradient_floor_measured = eikonal is not None and "gradient_norm_p01" in eikonal
    gradient_fail = []
    gradient_unmeasured = []
    if not gradient_floor_measured:
        gradient_unmeasured.append("no_gradient_samples_in_registered_0_05m_band")
    elif low_gradient_norm_floor is None:
        gradient_unmeasured.append("low_gradient_norm_floor_unregistered")
    elif not math.isfinite(low_gradient_norm_floor) or low_gradient_norm_floor < 0.0:
        gradient_unmeasured.append("low_gradient_norm_floor_invalid")
    elif eikonal["gradient_norm_min"] < low_gradient_norm_floor:
        gradient_fail.append("near_zero_gradient_cells_present")
    gates["near_zero_gradient_band"] = _gate(
        gradient_fail,
        gradient_unmeasured,
        eikonal,
        {
            "band_abs_phi_m": LOW_GRADIENT_BAND_M,
            "low_gradient_norm_floor": low_gradient_norm_floor,
        },
    )

    # --- structural boundary margin and physical domain clearance ---------
    clearances = _clearances_m(occupancy, state, domain_bounds_m)
    if clearances is None:
        gates["sdf_boundary_margin"] = _gate(unmeasured=["no_solid_cells"])
        gates["domain_clearance"] = _gate(unmeasured=["no_solid_cells"])
    else:
        lowest = min(clearances.values())
        gates["sdf_boundary_margin"] = _gate(
            fail=["solid_within_boundary_margin"] if lowest < boundary_margin_cells * h - LENGTH_TOLERANCE_M else (),
            measured={"min_clearance_cells": lowest / h, "clearances_m": clearances},
            thresholds={"boundary_margin_cells": boundary_margin_cells, "source": "contract_structural"},
        )
        unmeasured = ["min_clearance_m_unregistered"] if min_clearance_m is None else []
        if min_clearance_m is not None and (not math.isfinite(min_clearance_m) or min_clearance_m < 0.0):
            unmeasured.append("min_clearance_m_invalid")
        fail = ["domain_clearance_violation"] if (
            min_clearance_m is not None and math.isfinite(min_clearance_m)
            and min_clearance_m >= 0.0 and lowest < min_clearance_m - LENGTH_TOLERANCE_M
        ) else []
        gates["domain_clearance"] = _gate(
            fail, unmeasured,
            {"min_clearance_m": lowest, "clearances_m": clearances,
             "domain": "sdf_grid_extent" if domain_bounds_m is None else "caller_supplied"},
            {"min_clearance_m": min_clearance_m},
        )

    # --- masks / connectivity / topology events (#31 evaluator) -----------
    try:
        transition = evaluate_sdf_topology_transition(
            policy, parent_state or state, state,
            root_group_masks=root_group_masks, feature_metrics=None,
        )
    except SDFTopologyPolicyError as error:
        for gate_id in ("mask_preservation", "component_connectivity", "topology_change_classification"):
            gates[gate_id] = _gate(unmeasured=[f"topology_evaluator_rejected_input:{error}"])
        transition = None
    if transition is not None:
        parts, ignored = _partition(transition.violations)
        counts = {
            "cells": {name: int(getattr(state, f"{name}_mask").sum())
                      for name in ("design", "fixed_solid", "forbidden", "root")},
        }
        counts["vacuous_masks"] = [n for n in ("fixed_solid", "forbidden", "root") if counts["cells"][n] == 0]
        mask_unmeasured = []
        if policy_scope == "canonical_unresolved" and policy.source_problem_spec_sha256 is None:
            mask_unmeasured.append("source_problem_spec_and_root_mask_binding_unregistered")
        gates["mask_preservation"] = _gate(fail=parts["masks"], unmeasured=mask_unmeasured, measured=counts)

        unresolved = set(policy.unresolved_birth_inputs()) | _ALWAYS_UNMEASURED
        conn = parts["connectivity"]
        policy_unresolved = policy_scope == "canonical_unresolved"
        gates["component_connectivity"] = _gate(
            fail=[r for r in conn if r not in unresolved and not (policy_unresolved and r in _UNBOUND_POLICY_REASONS)],
            unmeasured=[r for r in conn if r in unresolved or (policy_unresolved and r in _UNBOUND_POLICY_REASONS)]
            + (["research_disconnected_component_and_optional_root_policy_not_content_bound"] if policy_unresolved else []),
            measured={
                "node_occupancy_components": transition.proposed_component_count,
                "component_root_owners": [[i, list(o)] for i, o in transition.component_root_owners],
                "connectivity": "26-neighbour, node occupancy phi<0",
            },
            thresholds={"source": "SDFTopologyPolicy/ProblemSpec v2", "policy": policy.state_binding_id},
        )
        event_unmeasured = ["parent_state_missing"] if parent_state is None else []
        event_fail = list(parts["events"])
        event_thresholds: dict[str, Any] = {
            "birth": "disabled",
            "deletion": "disabled",
            "merge": "allowed_if_all_other_gates_pass",
            "split": "allowed_if_rooted",
        }
        if policy_unresolved:
            event_fail = [reason for reason in event_fail if reason not in _UNDECIDED_EVENT_REASONS]
            event_unmeasured.extend(["birth_split_merge_deletion_permissions_unanswered"])
            event_unmeasured.extend(reason for reason in parts["events"] if reason in _UNDECIDED_EVENT_REASONS)
            event_thresholds = {"source": "successor SDFTopologyPolicy unregistered", "event_permissions": "unresolved"}
        gates["topology_change_classification"] = _gate(
            fail=event_fail,
            unmeasured=event_unmeasured,
            measured={
                "detected_events": list(transition.detected_events),
                "parent_component_count": transition.current_component_count,
                "component_count": transition.proposed_component_count,
                "parent_kind": _parent_kind(state, parent_state),
            },
            thresholds=event_thresholds,
        )

    # --- feature widths and inter-component gap ---------------------------
    solid_width = min_feature_width_m(occupancy, h)
    void_width = min_feature_width_m(~occupancy, h)
    labels, count = ndimage.label(occupancy, structure=_S26)
    gap = min_component_gap_m(labels, count, h)
    limits = {
        "minimum_solid_width_m": policy.minimum_solid_width_m,
        "minimum_void_width_m": policy.minimum_void_width_m,
        "minimum_gap_m": policy.minimum_gap_m,
    }
    fail, unmeasured = [], []
    width_guard_m = h / FEATURE_SUPERSAMPLE
    for name, value in (("solid", solid_width), ("void", void_width)):
        limit = limits[f"minimum_{name}_width_m"]
        gate = _minimum_measure_gate(value, limit, width_guard_m, f"{name}_width")
        fail.extend(gate["fail_reasons"])
        unmeasured.extend(gate["unmeasured_reasons"])
    gates["min_feature_width"] = _gate(
        fail, unmeasured,
        {"min_solid_width_m": _f(solid_width), "min_void_width_m": _f(void_width),
         "method": f"2*EDT ridge minimum, {FEATURE_SUPERSAMPLE}x supersampled cell occupancy"},
        {**{k: limits[k] for k in ("minimum_solid_width_m", "minimum_void_width_m")},
         "sampling_guard_m": width_guard_m,
         "source": "SDFTopologyPolicy/ProblemSpec v2"},
    )
    gap_guard_m = CELL_GAP_RESOLUTION_GUARD * h
    gap_gate = (
        (
            _gate(unmeasured=["minimum_gap_m_unregistered"],
                  measured={"applicable": False, "reason": "fewer_than_two_components"})
            if limits["minimum_gap_m"] is None
            else _gate(measured={"applicable": False, "reason": "fewer_than_two_components"})
        )
        if count < 2
        else _minimum_measure_gate(gap, limits["minimum_gap_m"], gap_guard_m, "gap")
    )
    unmeasured = list(gap_gate["unmeasured_reasons"])
    fail = list(gap_gate["fail_reasons"])
    gates["inter_component_gap"] = _gate(
        fail, unmeasured,
        {"cell_occupancy_components": int(count), "min_gap_m": _f(gap),
         "method": "cell-union cube face distance estimate, 26-neighbour components"},
        {"minimum_gap_m": limits["minimum_gap_m"], "sampling_resolution_guard_m": gap_guard_m,
         "source": "SDFTopologyPolicy/ProblemSpec v2"},
    )

    # --- export surface and self-intersection -----------------------------
    _, node_count = ndimage.label(state.solid_mask, structure=_S26)
    proxy_integrity, proxy_intersection = surface_gates(
        export_surface(state), sharp_volume_m3(state), node_count, count
    )
    if policy_scope == "canonical_unresolved":
        reason = "canonical_gridsdf_zero_level_export_mesh_not_supplied"
        gates["export_surface_integrity"] = _gate(
            unmeasured=[reason], measured={"voxel_cell_union_proxy": proxy_integrity}
        )
        gates["surface_self_intersection"] = _gate(
            unmeasured=[reason], measured={"voxel_cell_union_proxy": proxy_intersection}
        )
    else:
        gates["export_surface_integrity"] = proxy_integrity
        gates["surface_self_intersection"] = proxy_intersection

    # --- volume semantics -------------------------------------------------
    smoothed = smoothed_volume_and_gradient(state).smoothed_volume_m3
    sharp = sharp_volume_m3(state)
    measured = {
        "sharp_volume_m3": sharp,
        "sampled_solid_centers": int(occupancy.sum()),
        "smoothed_volume_m3": smoothed,
        "node_occupancy_diagnostic_m3": node_occupancy_volume_m3(state),
        "smoothed_volume_role": "diagnostic; not a conservative sharp bound, never gates acceptance",
    }
    if volume_limit_m3 is None or not math.isfinite(volume_limit_m3) or volume_limit_m3 <= 0.0:
        gates["volume_semantics"] = _gate(unmeasured=["volume_limit_m3_unregistered"], measured=measured)
    else:
        measured["sharp_volume_violation_m3"] = max(0.0, sharp - volume_limit_m3)
        measured["smoothed_constraint_residual"] = smoothed / volume_limit_m3 - 1.0
        gates["volume_semantics"] = _gate(
            fail=["sharp_volume_exceeds_limit"] if sharp > volume_limit_m3 else (),
            measured=measured,
            thresholds={"volume_limit_m3": float(volume_limit_m3), "rule": "V_phi <= limit (registered sharp rule)"},
        )
    return _bundle(state, parent_state, policy, gates, policy_scope)


def _parent_kind(state, parent) -> str:
    if parent is None:
        return "none"
    return "identity" if parent.state_sha256 == state.state_sha256 else "distinct"


def _bundle(state, parent, policy, gates, policy_scope: str) -> dict[str, Any]:
    ordered = {gate_id: gates[gate_id] for gate_id in GATE_IDS}
    by_status = {
        status: [g for g, v in ordered.items() if v["status"] == status]
        for status in ("pass", "fail", "unmeasured")
    }
    return {
        "schema_version": GEOMETRY_GATES_SCHEMA_VERSION,
        "kind": "sdf_native_geometry_gates",
        "contract_id": GEOMETRY_GATES_CONTRACT_ID,
        "evidence_class": "contract_and_capability",
        "state_sha256": state.state_sha256,
        "parent_state_sha256": None if parent is None else parent.state_sha256,
        "parent_kind": _parent_kind(state, parent),
        "policy_binding": policy.state_binding_id,
        "policy_scope": policy_scope,
        "policy_source_problem_spec_sha256": policy.source_problem_spec_sha256,
        "grid": {
            "shape": [int(v) for v in state.shape],
            "origin_m": [float(v) for v in state.origin_m],
            "spacing_m": float(state.spacing_m),
        },
        "gates": ordered,
        "verdict": {
            "pass": len(by_status["pass"]) == len(GATE_IDS),
            "passed": by_status["pass"],
            "failed": by_status["fail"],
            "unmeasured": by_status["unmeasured"],
            "rule": "AND of all gates; unmeasured blocks like fail",
        },
    }



__all__ = [
    "GATE_IDS",
    "GEOMETRY_GATES_CONTRACT_ID",
    "GEOMETRY_GATES_SCHEMA_VERSION",
    "cell_occupancy",
    "evaluate_geometry_gates",
    "export_surface",
    "min_component_gap_m",
    "min_feature_width_m",
    "surface_gates",
    "triangles_self_intersect",
]
