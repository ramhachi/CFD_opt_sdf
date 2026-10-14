"""SDF-native geometry hard-gate bundle (GEOM-02, contract v2, #29).

Same 13 gate ids and fail-closed semantics as v1 (``geometry_gates``, immutable); the inputs v1 left open are supplied by a
registered ``profile`` dict (thresholds only; ``None``/missing/invalid means ``unmeasured``), a resolved
``SDFTopologyPolicyResearchV2`` (widths and gap) and the actual zero-level export mesh (built in the scripts layer).
v1 helpers are reused, not copied; v1 ``evaluate_geometry_gates`` is monolithic, so only its orchestration is redone here.

Evidence scope: solver-free research gates.  The width/gap limits are lattice representability limits, not physical ones,
and nothing here permits a shape update.  Topology is judged on the stored states by the research evaluator; the three
violations caused only by the stored legacy policy binding (``REBOUND_ONLY_REASONS``) are removed by name and recorded.
"""

from __future__ import annotations

import itertools
import math
import time
from typing import Any

import numpy as np
from scipy import ndimage

from ..extraction_qualification import _contacts_confined_to_shared_simplex, _triangle_intersection_contacts
from .geometry_gates import (
    _S26, CELL_GAP_RESOLUTION_GUARD, FEATURE_SUPERSAMPLE, GATE_IDS, _clearances_m, _f, _gate,
    _gradient_diagnostics, _minimum_measure_gate, cell_occupancy, min_component_gap_m, min_feature_width_m,
)
from .sdf_state import SIGN_CONVENTION, SDFDesignState
from .topology_policy import SDFTopologyPolicyError
from .topology_policy_research import SDFTopologyPolicyResearchV2, evaluate_research_transition
from .volume_semantics import sampled_solid_centers_count

GEOMETRY_GATES_V2_CONTRACT_ID = "sdf_native_geometry_gates_v2"
GEOMETRY_GATES_V2_SCHEMA_VERSION = 2
LENGTH_TOLERANCE_M = 1e-9
REBOUND_ONLY_REASONS = frozenset(
    {"current_state_policy_hash_mismatch", "proposed_state_policy_hash_mismatch", "feature_measurements_missing"}
)
_MASK_REASONS = frozenset(
    {"state_mask_mismatch", "material_in_forbidden_mask", "material_outside_design_fixed_root_masks",
     "fixed_solid_not_retained", "root_material_not_retained"}
)
_EVENT_PREFIXES = ("topology_event_not_permitted:", "topology_birth_not_qualified", "state_grid_mismatch", "state_shape_mismatch")
_SEPARATED_OFFSETS = [o for o in itertools.product((-1, 0, 1), repeat=3) if o >= (0, 0, 0)]  # self + 13 half-neighbours
_PAIR_CHUNK = 2_000_000


def _limit(value: Any) -> float | None:
    """A registered threshold, or None when missing/non-finite/negative (the gate is then unmeasured)."""

    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0.0:
        return None
    return float(value)


def _candidate_pairs(keys: np.ndarray, deltas: list[int]):
    """Yield (i, j) triangle-index chunks for every same-or-neighbouring bin pair, each unordered pair once."""

    order = np.argsort(keys, kind="stable")
    ukeys, starts, counts = np.unique(keys[order], return_index=True, return_counts=True)
    for delta in deltas:
        pos = np.searchsorted(ukeys, ukeys + delta)
        pos = np.minimum(pos, len(ukeys) - 1)
        hit = np.flatnonzero(ukeys[pos] == ukeys + delta)
        a, b = hit, pos[hit]
        sizes = counts[a] * counts[b]
        ends = np.cumsum(sizes)
        lo = 0
        while lo < len(a):
            hi = int(np.searchsorted(ends, (ends[lo - 1] if lo else 0) + _PAIR_CHUNK, side="right"))
            hi = max(hi, lo + 1)
            sa, sb, cb, sz = starts[a[lo:hi]], starts[b[lo:hi]], counts[b[lo:hi]], sizes[lo:hi]
            p = np.arange(sz.sum()) - np.repeat(np.cumsum(sz) - sz, sz)
            i = order[np.repeat(sa, sz) + p // np.repeat(cb, sz)]
            j = order[np.repeat(sb, sz) + p % np.repeat(cb, sz)]
            if delta == 0:
                keep = i < j
                i, j = i[keep], j[keep]
            yield i, j
            lo = hi


def _edge_separated(a: np.ndarray, b: np.ndarray, normal: np.ndarray, shared_b: np.ndarray, tol: float) -> np.ndarray:
    """Coplanar pairs: some edge line of ``a`` has every vertex of ``b`` strictly outside, or shared and on that line."""

    out = np.zeros(len(a), dtype=bool)
    for k in range(3):
        p, third = a[:, k], a[:, (k + 2) % 3]
        n = np.cross(normal, a[:, (k + 1) % 3] - p)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        n *= -np.sign(np.einsum("mc,mc->m", n, third - p))[:, None]  # outward from ``a``
        d = np.einsum("mkc,mc->mk", b - p[:, None, :], n)
        out |= ((d > tol) | (shared_b & (np.abs(d) <= tol))).all(axis=1)
    return out


def mesh_self_intersection(vertices: np.ndarray, faces: np.ndarray, *, tolerance_rel: float = 1e-10) -> tuple[str, dict[str, Any]]:
    """Self-intersection verdict (``none`` / ``fail`` / ``not_evaluated_*``) with the P20 narrow phase and a binned broad phase.

    Triangles are binned by centroid in cells of twice the largest triangle extent, so two touching triangles are in the
    same or a 26-neighbouring bin.  Candidate pairs get the P20 AABB test; a pair whose non-shared vertices lie strictly
    on one side of the other triangle's plane (beyond the P20 tolerance), or a coplanar pair separated by an edge line,
    can only touch on the shared simplex and is dropped; the rest go to the unchanged P20 contact tests.  Verdicts equal
    the P20 detector's on meshes it can evaluate.  One deliberate difference: P20 declares a triangle degenerate when its
    doubled area is <= 1e-10 * extent^2 (about 1.3e-10 m^2 here), which trips on the needle-thin Lewiner triangles that the
    zero-tie epsilon creates (86 on the v17 baseline, normals still accurate to ~1e-8); here only triangles collinear to
    rounding (doubled area <= 64 eps * longest edge^2) are unevaluable.
    """

    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    n = len(faces)
    stats: dict[str, Any] = {"triangles": int(n), "candidate_pairs": 0, "aabb_overlap_pairs": 0, "narrow_phase_pairs": 0, "complete": True}
    clock = time.perf_counter()
    tri = vertices[faces]
    extent = float(np.max(np.ptp(vertices, axis=0))) if vertices.size else 0.0
    magnitude = float(np.max(np.abs(vertices))) if vertices.size else 0.0
    tol = max(extent * tolerance_rel, np.finfo(np.float64).eps * max(extent, magnitude) * 64.0, np.finfo(np.float64).tiny)  # P20 formula (P20: 1e-10)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normals, axis=1)
    if n == 0:
        stats.update(complete=False, runtime_s=time.perf_counter() - clock)
        return "not_evaluated_empty_mesh", stats
    longest = np.linalg.norm(np.roll(tri, -1, axis=1) - tri, axis=2).max(axis=1)
    if np.any(length <= 64.0 * np.finfo(np.float64).eps * longest**2):  # collinear to rounding; see the docstring
        stats.update(complete=False, runtime_s=time.perf_counter() - clock)
        return "not_evaluated_degenerate_triangle", stats
    unit = normals / length[:, None]
    lo, hi = tri.min(axis=1), tri.max(axis=1)
    cell = 2.0 * float((hi - lo).max())
    ijk = np.floor((tri.mean(axis=1) - vertices.min(axis=0)) / cell).astype(np.int64) + 1
    dims = ijk.max(axis=0) + 2
    keys = (ijk[:, 0] * dims[1] + ijk[:, 1]) * dims[2] + ijk[:, 2]
    deltas = [(dx * dims[1] + dy) * dims[2] + dz for dx, dy, dz in _SEPARATED_OFFSETS]
    verdict = "none"
    for i, j in _candidate_pairs(keys, deltas):
        stats["candidate_pairs"] += len(i)
        ok = np.ones(len(i), dtype=bool)
        for axis in range(3):
            ok &= (lo[i, axis] <= hi[j, axis] + tol) & (hi[i, axis] + tol >= lo[j, axis])
        i, j = i[ok], j[ok]
        stats["aabb_overlap_pairs"] += len(i)
        eq = faces[i][:, :, None] == faces[j][:, None, :]
        shared_i, shared_j = eq.any(axis=2), eq.any(axis=1)
        if np.any(shared_i.all(axis=1)):
            verdict = "fail"
            break
        d_j = np.einsum("mkc,mc->mk", tri[j] - tri[i][:, :1, :], unit[i])
        d_i = np.einsum("mkc,mc->mk", tri[i] - tri[j][:, :1, :], unit[j])
        separated = np.zeros(len(i), dtype=bool)
        for d, shared in ((d_j, shared_j), (d_i, shared_i)):
            separated |= ((d > tol) | shared).all(axis=1) | ((d < -tol) | shared).all(axis=1)
        coplanar = ~separated & (np.abs(d_j) <= tol).all(axis=1) & (np.abs(d_i) <= tol).all(axis=1)
        c = np.flatnonzero(coplanar)
        if c.size:
            ci, cj = i[c], j[c]
            separated[c] = _edge_separated(tri[ci], tri[cj], unit[ci], shared_j[c], tol) | _edge_separated(tri[cj], tri[ci], unit[cj], shared_i[c], tol)
        i, j = i[~separated], j[~separated]
        stats["narrow_phase_pairs"] += len(i)
        for a, b in zip(i, j, strict=True):
            contacts = _triangle_intersection_contacts(tri[a], tri[b], tol)
            if contacts and not _contacts_confined_to_shared_simplex(contacts, vertices[np.intersect1d(faces[a], faces[b])], tol):
                verdict = "fail"
                break
        if verdict == "fail":
            break
    stats["complete"] = verdict != "fail"
    stats["runtime_s"] = time.perf_counter() - clock
    return verdict, stats


def _zero_level_gradient(state: SDFDesignState) -> dict[str, Any] | None:
    """Central-difference ``|grad phi|`` at the interior nodes that have a 6-neighbour of the other class (exact zero = fluid)."""

    if min(state.shape) < 3:
        return None
    phi = state.phi.astype(np.float64)
    solid = phi < 0.0
    change = np.zeros(state.shape, dtype=bool)
    for axis in range(3):
        flip = np.diff(solid, axis=axis)  # XOR of neighbouring classes
        low = [slice(None)] * 3
        high = [slice(None)] * 3
        low[axis], high[axis] = slice(None, -1), slice(1, None)
        change[tuple(low)] |= flip
        change[tuple(high)] |= flip
    interior = np.zeros(state.shape, dtype=bool)
    interior[1:-1, 1:-1, 1:-1] = True
    nodes = change & interior
    out: dict[str, Any] = {"sign_change_nodes_interior": int(nodes.sum()), "sign_change_nodes_on_array_boundary": int((change & ~interior).sum())}
    if not nodes.any():
        return out
    norm = np.sqrt(sum(np.square(g) for g in np.gradient(phi, float(state.spacing_m))))
    out["norm"], out["nodes"], out["phi"] = norm, nodes, phi
    return out


def _gradient_floor_gate(state: SDFDesignState, floor: float | None) -> dict[str, Any]:
    z = _zero_level_gradient(state)
    thresholds = {"zero_level_gradient_floor": floor, "nodes": "interior nodes with a 6-neighbour of the opposite class; exact zero is fluid"}
    if z is None or "norm" not in z:
        return _gate(unmeasured=["no_interior_sign_change_nodes"], measured={} if z is None else z, thresholds=thresholds)
    norm, nodes, phi = z.pop("norm"), z.pop("nodes"), z.pop("phi")
    values = norm[nodes]
    z.update(gradient_norm_min=float(values.min()), gradient_norm_median=float(np.median(values)))
    unmeasured = ["sign_change_nodes_on_array_boundary"] if z["sign_change_nodes_on_array_boundary"] else []
    bad = np.zeros_like(nodes)
    if floor is None:
        unmeasured.append("zero_level_gradient_floor_unregistered_or_invalid")
    else:
        bad = nodes & (norm < floor)
    z["nodes_below_floor"] = int(bad.sum())
    if bad.any():
        zero = phi == 0.0
        near_zero = ndimage.binary_dilation(zero) & ~zero  # 6-neighbour of an exact-zero node
        idx = np.argwhere(bad)
        worst = idx[np.argsort(norm[bad])[:5]]
        z["failing_nodes"] = {
            "abs_phi_min_max_m": [float(np.abs(phi[bad]).min()), float(np.abs(phi[bad]).max())],
            "exact_zero_phi": int((bad & zero).sum()),
            "adjacent_to_exact_zero_phi": int((bad & near_zero).sum()),
            "other_thin_or_cancelling": int((bad & ~zero & ~near_zero).sum()),
            "index_min": idx.min(axis=0).tolist(), "index_max": idx.max(axis=0).tolist(),
            "worst_five": [{"index": w.tolist(), "phi": float(phi[tuple(w)]), "gradient_norm": float(norm[tuple(w)])} for w in worst],
        }
    return _gate(fail=["near_zero_gradient_at_zero_level"] if z["nodes_below_floor"] else (), unmeasured=unmeasured, measured=z, thresholds=thresholds)


def _feature_gates(occupancy: np.ndarray, h: float, policy: SDFTopologyPolicyResearchV2) -> tuple[dict, dict]:
    idx = np.argwhere(occupancy)
    if not idx.size:
        return _gate(unmeasured=["no_solid_cells"]), _gate(unmeasured=["no_solid_cells"])
    crop = occupancy[tuple(slice(max(a - 1, 0), b + 2) for a, b in zip(idx.min(axis=0), idx.max(axis=0)))]  # solid AABB + 1 cell
    solid_w, void_w = min_feature_width_m(crop, h), min_feature_width_m(~crop, h)
    guard = h / FEATURE_SUPERSAMPLE
    fail, unmeasured = [], []
    solid = _minimum_measure_gate(solid_w, policy.minimum_solid_width_m, guard, "solid_width")
    if void_w is None and policy.minimum_void_width_m is not None:
        void, void_label = _gate(), "not_applicable_no_enclosed_or_slot_void"
    else:
        void, void_label = _minimum_measure_gate(void_w, policy.minimum_void_width_m, guard, "void_width"), "measured"
    for gate in (solid, void):
        fail += gate["fail_reasons"]
        unmeasured += gate["unmeasured_reasons"]
    width = _gate(
        fail, unmeasured,
        {"min_solid_width_m": _f(solid_w), "min_void_width_m": _f(void_w), "void_width_label": void_label,
         "method": f"2*EDT ridge minimum, {FEATURE_SUPERSAMPLE}x supersampled cell occupancy; void measured inside the solid AABB padded by one cell"},
        {"minimum_solid_width_m": policy.minimum_solid_width_m, "minimum_void_width_m": policy.minimum_void_width_m,
         "sampling_guard_m": guard, "label": "lattice representability limit (research), not physical"},
    )
    labels, count = ndimage.label(crop, structure=_S26)
    limit = policy.minimum_gap_m
    gap = None if count < 2 else min_component_gap_m(labels, count, h)
    if count < 2:
        gate = _gate(unmeasured=["minimum_gap_m_unregistered"]) if limit is None else _gate()
    else:
        gate = _minimum_measure_gate(gap, limit, CELL_GAP_RESOLUTION_GUARD * h, "gap")
    gap_gate = _gate(
        gate["fail_reasons"], gate["unmeasured_reasons"],
        {"cell_occupancy_components": int(count), "min_gap_m": _f(gap),
         "label": "not_applicable_single_component" if count < 2 else "measured"},
        {"minimum_gap_m": limit, "sampling_resolution_guard_m": CELL_GAP_RESOLUTION_GUARD * h,
         "label": "lattice representability limit (research), not physical"},
    )
    return width, gap_gate


def _topology_gates(state, parent_state, policy, allowed_events, birth_qualified) -> dict[str, dict]:
    ids = ("mask_preservation", "component_connectivity", "topology_change_classification")
    if allowed_events is None or birth_qualified is None:
        return {g: _gate(unmeasured=["allowed_events_or_birth_qualified_unregistered"]) for g in ids}
    try:
        transition = evaluate_research_transition(
            policy, parent_state or state, state, feature_metrics=None,
            allowed_events=tuple(allowed_events), birth_qualified=birth_qualified,
        )
    except SDFTopologyPolicyError as error:
        return {g: _gate(unmeasured=[f"topology_evaluator_rejected_input:{error}"]) for g in ids}
    masks, events, connectivity = [], [], []
    for reason in transition.violations:
        if reason in REBOUND_ONLY_REASONS or reason in policy.unresolved_inputs():  # widths/gap are gated below
            continue
        (masks if reason in _MASK_REASONS else events if reason.startswith(_EVENT_PREFIXES) else connectivity).append(reason)
    empty = [n for n in ("fixed_solid", "forbidden", "root") if not getattr(state, f"{n}_mask").any()]
    parent_kind = "none" if parent_state is None else "identity" if parent_state.state_sha256 == state.state_sha256 else "distinct"
    return {
        "mask_preservation": _gate(
            masks, measured={"design_cells": int(state.design_mask.sum()), "empty_masks": empty, "vacuous_empty_masks": len(empty) == 3,
                             "source_problem_spec_bound": policy.source_problem_spec_sha256 is not None},
            thresholds={"rule": "material only in design|fixed|root, none in forbidden, fixed/root retained"}),
        "component_connectivity": _gate(
            connectivity,
            measured={"node_occupancy_components": transition.proposed_component_count, "connectivity": "26-neighbour, node occupancy phi<0",
                      "disconnected_components": "allowed", "root_connectivity": "optional"},
            thresholds={"max_components": policy.max_components, "policy": policy.state_binding_id}),
        "topology_change_classification": _gate(
            events, ["parent_state_missing"] if parent_state is None else (),
            {"detected_events": list(transition.detected_events), "parent_component_count": transition.current_component_count,
             "component_count": transition.proposed_component_count, "parent_kind": parent_kind,
             "scope": "solid components only; cavities and tunnels are not judged"},
            {"allowed_events": list(allowed_events), "birth_qualified": birth_qualified}),
    }


def _export_gates(export: dict[str, Any] | None, state: SDFDesignState, tolerance_rel: float | None) -> tuple[dict, dict]:
    if export is None:
        gate = _gate(unmeasured=["export_mesh_not_supplied"])
        return gate, dict(gate)
    topo = export["topology"]
    h = float(state.spacing_m)
    fail = []
    if topo["triangle_count"] == 0:
        fail.append("mesh_empty")
    for ok, reason in (
        (topo["watertight"], "mesh_not_watertight"),
        (topo["winding_consistent"], "mesh_winding_inconsistent"),
        (topo["nonmanifold_edge_count"] == 0 and topo["boundary_edge_count"] == 0, "mesh_not_edge_manifold"),
        (topo["vertex_link_bad_count"] == 0, "mesh_not_vertex_link_manifold"),
        (topo["duplicate_face_count"] == 0 and topo["repeated_index_face_count"] == 0 and topo["zero_area_face_count"] == 0, "mesh_duplicate_or_degenerate_faces"),
        (topo["signed_volume_m3"] > 0.0, "mesh_volume_not_positive"),
        (export["orientation_status"] == "PASS", "mesh_orientation_not_established"),
    ):
        if not ok:
            fail.append(reason)
    sharp = sampled_solid_centers_count(state) * h**3
    measured = {
        "triangles": topo["triangle_count"], "extracted_triangles": export["extracted_triangles"], "refinement": export["refinement"],
        "removed_subcell_components": export["removed_components"], "mesh_signed_volume_m3": topo["signed_volume_m3"],
        "mesh_area_m2": topo["area_m2"], "edge_connected_components": topo["edge_connected_component_count"],
        "orientation_status": export["orientation_status"], "orientation_flips": export["orientation_flips"],
        "sharp_cell_count_volume_m3": sharp, "mesh_volume_relative_to_sharp": topo["signed_volume_m3"] / sharp if sharp else None,
        "volume_comparison": "informational; the sharp count volume is not the zero-level volume",
    }
    integrity = _gate(fail, measured=measured, thresholds={"rule": "watertight, edge- and vertex-link-manifold, no duplicate/degenerate faces, positive volume, orientation established"})
    if tolerance_rel is None:
        return integrity, _gate(unmeasured=["self_intersection_tolerance_unregistered_or_invalid"])
    verdict, stats = mesh_self_intersection(export["vertices"], export["faces"], tolerance_rel=tolerance_rel)
    stats["tolerance_rel_to_extent"] = tolerance_rel
    if verdict == "none":
        crossing = _gate(measured=stats)
    elif verdict == "fail":
        crossing = _gate(fail=["mesh_self_intersects"], measured=stats)
    else:
        crossing = _gate(unmeasured=[verdict], measured=stats)
    return integrity, crossing


def evaluate_geometry_gates_v2(
    state: SDFDesignState,
    *,
    parent_state: SDFDesignState | None,
    profile: dict[str, Any],
    policy: SDFTopologyPolicyResearchV2,
    export_mesh: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate every gate for ``state``; the verdict is the AND of all gates (unmeasured blocks like fail).

    ``export_mesh`` is the scripts-layer export dict (``vertices``, ``faces``, ``topology``, ``orientation_status``,
    ``orientation_flips``, ``removed_components``, ``extracted_triangles``, ``refinement``) or None.  The state is never modified.
    """

    if not isinstance(state, SDFDesignState) or not isinstance(policy, SDFTopologyPolicyResearchV2):
        raise TypeError("state must be an SDFDesignState and policy an SDFTopologyPolicyResearchV2")
    gates: dict[str, dict[str, Any]] = {}
    h = float(state.spacing_m)

    finite = bool(np.isfinite(state.phi).all())
    fail = [] if finite else ["phi_not_finite"]
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
        for gate_id in GATE_IDS[1:]:
            gates[gate_id] = _gate(unmeasured=["sdf_not_finite"])
        return _bundle(state, parent_state, profile, policy, gates)

    occupancy = cell_occupancy(state)
    if not occupancy.any():
        gates["sdf_finite_structure"] = _gate(fail=fail + ["solid_cell_occupancy_empty"], measured=measured)

    eikonal = _gradient_diagnostics(state)
    tolerance = _limit(profile.get("eikonal_median_tolerance"))
    thresholds = {"eikonal_median_tolerance": profile.get("eikonal_median_tolerance")}
    if eikonal is None or "median_abs_gradient_deviation" not in eikonal:
        gates["sdf_distance_property"] = _gate(unmeasured=["no_narrow_band_interior_nodes"], measured=eikonal, thresholds=thresholds)
    elif tolerance is None:
        gates["sdf_distance_property"] = _gate(unmeasured=["eikonal_median_tolerance_unregistered_or_invalid"], measured=eikonal, thresholds=thresholds)
    else:
        failed = eikonal["median_abs_gradient_deviation"] > tolerance
        gates["sdf_distance_property"] = _gate(["phi_not_a_distance_field"] if failed else (), measured=eikonal, thresholds=thresholds)
    gates["near_zero_gradient_band"] = _gradient_floor_gate(state, _limit(profile.get("zero_level_gradient_floor")))

    margin = _limit(profile.get("boundary_margin_cells"))
    own = _clearances_m(occupancy, state, None)
    if own is None:
        gates["sdf_boundary_margin"] = gates["domain_clearance"] = _gate(unmeasured=["no_solid_cells"])
    else:
        lowest = min(own.values())
        gates["sdf_boundary_margin"] = _gate(
            ["solid_within_boundary_margin"] if margin is not None and lowest < margin * h - LENGTH_TOLERANCE_M else (),
            [] if margin is not None else ["boundary_margin_cells_unregistered_or_invalid"],
            {"min_clearance_cells": lowest / h, "clearances_m": own}, {"boundary_margin_cells": profile.get("boundary_margin_cells")},
        )
        bounds, need = profile.get("domain_bounds_m"), _limit(profile.get("min_clearance_m"))
        flow = _clearances_m(occupancy, state, bounds) if bounds is not None else None
        gates["domain_clearance"] = _gate(
            ["domain_clearance_violation"] if flow is not None and need is not None and min(flow.values()) < need - LENGTH_TOLERANCE_M else (),
            (["domain_bounds_m_unregistered"] if flow is None else []) + (["min_clearance_m_unregistered_or_invalid"] if need is None else []),
            {"min_clearance_m": None if flow is None else min(flow.values()), "clearances_m": flow, "domain_bounds_m": bounds},
            {"min_clearance_m": profile.get("min_clearance_m")},
        )

    gates.update(_topology_gates(state, parent_state, policy, profile.get("allowed_events"), profile.get("birth_qualified")))
    gates["min_feature_width"], gates["inter_component_gap"] = _feature_gates(occupancy, h, policy)
    gates["export_surface_integrity"], gates["surface_self_intersection"] = _export_gates(export_mesh, state, _limit((profile.get("export") or {}).get("self_intersection_tolerance_rel")))

    count, limit, lattice = sampled_solid_centers_count(state), profile.get("max_solid_centers"), profile.get("lattice")
    here = {"origin_m": [float(v) for v in state.origin_m], "spacing_m": h, "node_shape": [int(v) for v in state.shape]}
    unmeasured = (["max_solid_centers_unregistered"] if _limit(limit) is None else []) + (["lattice_not_the_registered_one"] if lattice != here else [])
    gates["volume_semantics"] = _gate(
        ["solid_center_count_exceeds_limit"] if not unmeasured and count > limit else (), unmeasured,
        {"sampled_solid_centers": count, "lattice": here},
        {"max_solid_centers": limit, "lattice": lattice, "rule": "P22-v2 integer hard count; representation-specific, not a physical volume"},
    )
    return _bundle(state, parent_state, profile, policy, gates)


def _bundle(state, parent, profile, policy, gates) -> dict[str, Any]:
    ordered = {g: gates[g] for g in GATE_IDS}
    by_status = {s: [g for g, v in ordered.items() if v["status"] == s] for s in ("pass", "fail", "unmeasured")}
    return {
        "schema_version": GEOMETRY_GATES_V2_SCHEMA_VERSION,
        "kind": "sdf_native_geometry_gates",
        "contract_id": GEOMETRY_GATES_V2_CONTRACT_ID,
        "evidence_class": "contract_and_capability",
        "profile_id": profile.get("profile_id"),
        "policy_binding": policy.state_binding_id,
        "state_sha256": state.state_sha256,
        "parent_state_sha256": None if parent is None else parent.state_sha256,
        "stored_topology_policy_id": {"state": state.topology_policy_id, "parent": None if parent is None else parent.topology_policy_id},
        "phi_sha256": state.phi_sha256(),
        "grid": {"shape": [int(v) for v in state.shape], "origin_m": [float(v) for v in state.origin_m], "spacing_m": float(state.spacing_m)},
        "gates": ordered,
        "verdict": {
            "pass": len(by_status["pass"]) == len(GATE_IDS),
            "passed": by_status["pass"], "failed": by_status["fail"], "unmeasured": by_status["unmeasured"],
            "rule": "AND of all gates; unmeasured blocks like fail",
        },
    }


__all__ = ["GEOMETRY_GATES_V2_CONTRACT_ID", "REBOUND_ONLY_REASONS", "evaluate_geometry_gates_v2", "mesh_self_intersection"]
