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
- the triangle self-intersection detector is the P20-repaired algorithm of
  ``extraction_qualification`` copied here so this module has no dependency
  on Stage S/PQ4 code; it is re-verified on analytic fixtures;
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
SELF_INTERSECTION_MAX_TRIANGLES = 12_000

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


def cell_occupancy(state: SDFDesignState) -> np.ndarray:
    """Registered V_phi occupancy: h-cubes whose trilinear centre sample is < 0."""

    return _corner_mean(state.phi) < 0.0


def min_feature_width_m(mask: np.ndarray, spacing_m: float) -> float | None:
    """Minimum local thickness (2 x EDT on the medial-axis ridge) of a cell mask.

    Same measure as the DF0 ridge statistic, on a 4x supersampled grid so a
    k-cell slab measures exactly ``k * h``.  Edge padding keeps the domain
    boundary from creating artificial ridge cells.  Voxel-quantized: features
    not aligned with the grid carry up to one supersample of error.
    """

    if not mask.any() or mask.all():
        return None
    up = np.pad(mask, 1, mode="edge")
    for axis in range(3):
        up = np.repeat(up, FEATURE_SUPERSAMPLE, axis=axis)
    distance = ndimage.distance_transform_edt(up, sampling=spacing_m / FEATURE_SUPERSAMPLE)
    ridge = up & (distance >= ndimage.maximum_filter(distance, size=3) - 1e-12)
    pad = FEATURE_SUPERSAMPLE
    ridge = ridge[pad:-pad, pad:-pad, pad:-pad]
    return float(2.0 * distance[pad:-pad, pad:-pad, pad:-pad][ridge].min())


def min_component_gap_m(labels: np.ndarray, count: int, spacing_m: float) -> float | None:
    """Exact minimum face-to-face gap between labelled cell components.

    Cube-to-cube distance is ``sqrt(sum(max(|d_i| - 1, 0)^2)) * h`` in cell
    offsets ``d``; that equals the centre-to-centre Euclidean distance to the
    one-cell (26-neighbour) dilation of the other component.
    """

    best = None
    for label in range(1, count):
        dilated = ndimage.binary_dilation(labels == label, structure=_S26)
        distance = ndimage.distance_transform_edt(~dilated, sampling=spacing_m)
        later = distance[labels > label]
        if later.size:
            best = float(later.min()) if best is None else min(best, float(later.min()))
    return best


def _eikonal(state: SDFDesignState) -> dict[str, Any] | None:
    if min(state.shape) < 3:
        return None
    gradient = np.gradient(state.phi.astype(np.float64), float(state.spacing_m))
    norm = np.sqrt(sum(np.square(axis) for axis in gradient))
    band = np.zeros(state.shape, dtype=bool)
    band[1:-1, 1:-1, 1:-1] = True
    band &= np.abs(state.phi) <= state.narrow_band_width_m
    if not band.any():
        return None
    deviation = np.abs(norm[band] - 1.0)
    return {
        "band_node_count": int(band.sum()),
        "median_abs_gradient_deviation": float(np.median(deviation)),
        "p95_abs_gradient_deviation": float(np.percentile(deviation, 95)),
        "max_abs_gradient_deviation": float(deviation.max()),
    }


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
    """Registered export surface: VTK surface nets on the cell occupancy, no smoothing.

    The extractor PQ4.1 v2 adopted after marching cubes produced sliver
    triangles; the surface is the exact voxel boundary of the occupancy.
    Returns ``None`` for an empty occupancy.
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
    boundary_margin_cells: int = BOUNDARY_MARGIN_CELLS,
    domain_bounds_m: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None,
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
        return _bundle(state, parent_state, policy, gates)

    occupancy = cell_occupancy(state)
    h = float(state.spacing_m)
    if not occupancy.any():
        gates["sdf_finite_structure"] = _gate(
            fail=gates["sdf_finite_structure"]["fail_reasons"] + ["solid_cell_occupancy_empty"],
            measured=measured,
        )

    # --- distance (eikonal) property --------------------------------------
    eikonal = _eikonal(state)
    unmeasured = []
    fail = []
    if eikonal is None:
        unmeasured.append("no_narrow_band_interior_nodes")
    elif eikonal_median_tolerance is None:
        unmeasured.append("eikonal_median_tolerance_unregistered")
    elif eikonal["median_abs_gradient_deviation"] > eikonal_median_tolerance:
        fail.append("phi_not_a_distance_field")
    gates["sdf_distance_property"] = _gate(
        fail, unmeasured, eikonal, {"eikonal_median_tolerance": eikonal_median_tolerance}
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
        fail = ["domain_clearance_violation"] if (
            min_clearance_m is not None and lowest < min_clearance_m - LENGTH_TOLERANCE_M
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
        gates["mask_preservation"] = _gate(fail=parts["masks"], measured=counts)

        unresolved = set(policy.unresolved_birth_inputs()) | _ALWAYS_UNMEASURED
        conn = parts["connectivity"]
        gates["component_connectivity"] = _gate(
            fail=[r for r in conn if r not in unresolved],
            unmeasured=[r for r in conn if r in unresolved],
            measured={
                "node_occupancy_components": transition.proposed_component_count,
                "component_root_owners": [[i, list(o)] for i, o in transition.component_root_owners],
                "connectivity": "26-neighbour, node occupancy phi<0",
            },
            thresholds={"source": "SDFTopologyPolicy/ProblemSpec v2", "policy": policy.state_binding_id},
        )
        gates["topology_change_classification"] = _gate(
            fail=parts["events"],
            unmeasured=["parent_state_missing"] if parent_state is None else [],
            measured={
                "detected_events": list(transition.detected_events),
                "parent_component_count": transition.current_component_count,
                "component_count": transition.proposed_component_count,
                "parent_kind": _parent_kind(state, parent_state),
            },
            thresholds={"birth": "disabled", "deletion": "disabled",
                        "merge": "allowed_if_all_other_gates_pass", "split": "allowed_if_rooted"},
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
    for name, value in (("solid", solid_width), ("void", void_width)):
        limit = limits[f"minimum_{name}_width_m"]
        if limit is None:
            unmeasured.append(f"minimum_{name}_width_m_unregistered")
        if value is None:
            unmeasured.append(f"{name}_width_not_measurable")
        elif limit is not None and value < limit - LENGTH_TOLERANCE_M:
            fail.append(f"minimum_{name}_width_violation")
    gates["min_feature_width"] = _gate(
        fail, unmeasured,
        {"min_solid_width_m": _f(solid_width), "min_void_width_m": _f(void_width),
         "method": f"2*EDT ridge minimum, {FEATURE_SUPERSAMPLE}x supersampled cell occupancy"},
        {**{k: limits[k] for k in ("minimum_solid_width_m", "minimum_void_width_m")},
         "source": "SDFTopologyPolicy/ProblemSpec v2"},
    )
    unmeasured = ["minimum_gap_m_unregistered"] if limits["minimum_gap_m"] is None else []
    fail = ["minimum_gap_violation"] if (
        gap is not None and limits["minimum_gap_m"] is not None
        and gap < limits["minimum_gap_m"] - LENGTH_TOLERANCE_M
    ) else []
    gates["inter_component_gap"] = _gate(
        fail, unmeasured,
        {"cell_occupancy_components": int(count), "min_gap_m": _f(gap),
         "method": "exact axis-aligned cube face distance, 26-neighbour components"},
        {"minimum_gap_m": limits["minimum_gap_m"], "source": "SDFTopologyPolicy/ProblemSpec v2"},
    )

    # --- export surface and self-intersection -----------------------------
    _, node_count = ndimage.label(state.solid_mask, structure=_S26)
    gates["export_surface_integrity"], gates["surface_self_intersection"] = surface_gates(
        export_surface(state), sharp_volume_m3(state), node_count, count
    )

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
    return _bundle(state, parent_state, policy, gates)


def _parent_kind(state, parent) -> str:
    if parent is None:
        return "none"
    return "identity" if parent.state_sha256 == state.state_sha256 else "distinct"


def _bundle(state, parent, policy, gates) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Triangle self-intersection detector: P20-repaired algorithm copied from
# extraction_qualification (coplanar overlap and shared-vertex crossings are
# detected; contact is allowed only on the shared simplex).  Re-verified on
# analytic fixtures in tests/test_sdf_native_geometry_gates.py.
# ---------------------------------------------------------------------------


def triangles_self_intersect(mesh) -> str:
    """``"none"`` / ``"fail"`` / ``"not_evaluated_*"`` (unmeasured, fail-closed)."""

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    n = faces.shape[0]
    if n > SELF_INTERSECTION_MAX_TRIANGLES:
        return "not_evaluated_too_many_triangles"
    tri = vertices[faces]
    extent = float(np.max(np.ptp(vertices, axis=0))) if vertices.size else 0.0
    magnitude = float(np.max(np.abs(vertices))) if vertices.size else 0.0
    tolerance = max(
        extent * 1e-10,
        np.finfo(np.float64).eps * max(extent, magnitude) * 64.0,
        np.finfo(np.float64).tiny,
    )
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    if np.any(np.linalg.norm(normals, axis=1) <= tolerance * max(extent, tolerance)):
        return "not_evaluated_degenerate_triangle"
    tri_min, tri_max = tri.min(axis=1), tri.max(axis=1)
    overlap = np.ones((n, n), dtype=bool)
    for axis in range(3):
        overlap &= tri_min[:, None, axis] <= tri_max[None, :, axis] + tolerance
        overlap &= tri_max[:, None, axis] + tolerance >= tri_min[None, :, axis]
    pair_i, pair_j = np.nonzero(np.triu(overlap, k=1))
    for a, b in zip(pair_i, pair_j, strict=True):
        shared = np.intersect1d(faces[a], faces[b])
        if shared.size == 3:
            return "fail"
        contacts = _contacts(tri[a], tri[b], tolerance)
        if contacts and not _confined(contacts, vertices[shared], tolerance):
            return "fail"
    return "none"


def _confined(contacts, allowed, tolerance) -> bool:
    if allowed.shape[0] == 1:
        return all(np.linalg.norm(p - allowed[0]) <= tolerance for p in contacts)
    if allowed.shape[0] == 2:
        edge = allowed[1] - allowed[0]
        for p in contacts:
            t = float(np.dot(p - allowed[0], edge) / np.dot(edge, edge))
            if np.linalg.norm(p - (allowed[0] + np.clip(t, 0.0, 1.0) * edge)) > tolerance:
                return False
        return True
    return False


def _contacts(a, b, tolerance):
    unit_a = np.cross(a[1] - a[0], a[2] - a[0])
    unit_b = np.cross(b[1] - b[0], b[2] - b[0])
    unit_a, unit_b = unit_a / np.linalg.norm(unit_a), unit_b / np.linalg.norm(unit_b)
    parallel = np.linalg.norm(np.cross(unit_a, unit_b)) <= 1e-10
    if parallel and max(
        float(np.max(np.abs((b - a[0]) @ unit_a))), float(np.max(np.abs((a - b[0]) @ unit_b)))
    ) <= tolerance:
        keep = [axis for axis in range(3) if axis != int(np.argmax(np.abs(unit_a)))]
        return _coplanar_contacts(a, b, a[:, keep], b[:, keep], tolerance)
    contacts: list[np.ndarray] = []
    for source, target, normal in ((a, b, unit_b), (b, a, unit_a)):
        signed = (source - target[0]) @ normal
        for i in range(3):
            p0, p1 = source[i], source[(i + 1) % 3]
            d0, d1 = float(signed[i]), float(signed[(i + 1) % 3])
            for p, d in ((p0, d0), (p1, d1)):
                if abs(d) <= tolerance and _in_triangle_3d(p, target, tolerance):
                    _add(contacts, p, tolerance)
            if (d0 < -tolerance and d1 > tolerance) or (d0 > tolerance and d1 < -tolerance):
                point = p0 + (d0 / (d0 - d1)) * (p1 - p0)
                if _in_triangle_3d(point, target, tolerance):
                    _add(contacts, point, tolerance)
    return contacts


def _in_triangle_3d(point, triangle, tolerance) -> bool:
    v0, v1, v2 = triangle[1] - triangle[0], triangle[2] - triangle[0], point - triangle[0]
    d00, d01, d11 = float(v0 @ v0), float(v0 @ v1), float(v1 @ v1)
    denominator = d00 * d11 - d01 * d01
    v = (d11 * float(v2 @ v0) - d01 * float(v2 @ v1)) / denominator
    w = (d00 * float(v2 @ v1) - d01 * float(v2 @ v0)) / denominator
    slack = tolerance / max(np.linalg.norm(v0), np.linalg.norm(v1), tolerance)
    return v >= -slack and w >= -slack and v + w <= 1.0 + slack


def _coplanar_contacts(a3, b3, a2, b2, tolerance):
    contacts: list[np.ndarray] = []
    scale = max(float(np.max(np.ptp(a2, axis=0))), float(np.max(np.ptp(b2, axis=0))))
    area_tolerance = tolerance * max(scale, tolerance)
    for p3, p2 in zip(a3, a2, strict=True):
        if _in_triangle_2d(p2, b2, area_tolerance):
            _add(contacts, p3, tolerance)
    for p3, p2 in zip(b3, b2, strict=True):
        if _in_triangle_2d(p2, a2, area_tolerance):
            _add(contacts, p3, tolerance)
    for ea in range(3):
        for eb in range(3):
            for t in _segment_parameters_2d(
                a2[ea], a2[(ea + 1) % 3], b2[eb], b2[(eb + 1) % 3], area_tolerance
            ):
                _add(contacts, a3[ea] + t * (a3[(ea + 1) % 3] - a3[ea]), tolerance)
    return contacts


def _cross_2d(a, b) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _in_triangle_2d(point, triangle, area_tolerance) -> bool:
    signs = [_cross_2d(triangle[(i + 1) % 3] - triangle[i], point - triangle[i]) for i in range(3)]
    return min(signs) >= -area_tolerance or max(signs) <= area_tolerance


def _segment_parameters_2d(p0, p1, q0, q1, area_tolerance) -> list[float]:
    r, s, offset = p1 - p0, q1 - q0, q0 - p0
    denominator = _cross_2d(r, s)
    if abs(denominator) > area_tolerance:
        t, u = _cross_2d(offset, s) / denominator, _cross_2d(offset, r) / denominator
        slack = area_tolerance / max(float(r @ r), float(s @ s), area_tolerance)
        if -slack <= t <= 1.0 + slack and -slack <= u <= 1.0 + slack:
            return [float(np.clip(t, 0.0, 1.0))]
        return []
    if abs(_cross_2d(offset, r)) > area_tolerance:
        return []
    length_squared = float(r @ r)
    t0, t1 = float((q0 - p0) @ r) / length_squared, float((q1 - p0) @ r) / length_squared
    lower, upper = max(0.0, min(t0, t1)), min(1.0, max(t0, t1))
    if lower > upper + area_tolerance / length_squared:
        return []
    return [float(np.clip(lower, 0.0, 1.0)), float(np.clip(upper, 0.0, 1.0))]


def _add(contacts, point, tolerance) -> None:
    if not any(np.linalg.norm(point - existing) <= tolerance for existing in contacts):
        contacts.append(np.asarray(point, dtype=np.float64))


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
