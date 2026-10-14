"""Solver-free GEOM-02 contract checks for the v2 gate bundle; fixture thresholds are not the canonical profile."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cfd_sdf.design.geometry_gates import GATE_IDS
from cfd_sdf.design.geometry_gates_v2 import (
    REBOUND_ONLY_REASONS,
    _gradient_floor_gate,
    evaluate_geometry_gates_v2,
    mesh_self_intersection,
)
from cfd_sdf.design.sdf_state import DEFAULT_TOPOLOGY_POLICY_ID, SDFDesignState
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2, evaluate_research_transition
from cfd_sdf.extraction_qualification import _triangles_self_intersect

H = 0.05
SHAPE = (36, 28, 28)
POLICY = SDFTopologyPolicyResearchV2(minimum_solid_width_m=1.5 * H, minimum_void_width_m=1.5 * H, minimum_gap_m=2.5 * H)


def _profile(state: SDFDesignState) -> dict:
    return {
        "profile_id": "test",
        "eikonal_median_tolerance": 0.10,
        "zero_level_gradient_floor": 0.5,
        "boundary_margin_cells": 1,
        "domain_bounds_m": [[-0.3, -0.3, -0.3], [2.05, 1.65, 1.65]],
        "min_clearance_m": 0.25,
        "max_solid_centers": 10**9,
        "lattice": {"origin_m": [0.0, 0.0, 0.0], "spacing_m": H, "node_shape": list(SHAPE)},
        "allowed_events": [],
        "birth_qualified": False,
        "export": {"refinement": 1, "small_component_min_bbox_diagonal_m": H, "self_intersection_tolerance_rel": 1e-12},
    }


def _faces(lo, hi) -> np.ndarray:
    """Exact SDF of the axis-aligned box with faces at index coordinates lo..hi."""
    grid = np.stack(np.meshgrid(*[np.arange(n) for n in SHAPE], indexing="ij"), axis=-1)
    q = np.abs(grid - (np.asarray(lo) + np.asarray(hi)) / 2.0) - (np.asarray(hi) - np.asarray(lo)) / 2.0
    return (np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(q.max(axis=-1), 0.0)) * H


def _box(lo, hi) -> np.ndarray:
    """Box whose solid nodes are lo..hi (faces 0.2 cells beyond)."""
    return _faces(np.asarray(lo) - 0.2, np.asarray(hi) + 0.2)


def _patch(lo, hi) -> np.ndarray:
    mask = np.zeros(SHAPE, dtype=bool)
    mask[lo[0] : hi[0] + 1, lo[1] : hi[1] + 1, lo[2] : hi[2] + 1] = True
    return mask


def _state(phi, **masks) -> SDFDesignState:
    return SDFDesignState.create(phi=np.asarray(phi, dtype=np.float32), origin_m=(0.0, 0.0, 0.0), spacing_m=H, narrow_band_width_m=0.1, **masks)


def _export(vertices, faces) -> dict:
    """Export dict as the scripts layer builds it, for a mesh supplied directly (orientation taken as established)."""
    import xfid45_round3_export as ex

    return {"vertices": np.asarray(vertices, float), "faces": np.asarray(faces), "topology": ex.topology(vertices, faces), "orientation_status": "PASS",
            "orientation_flips": 0, "removed_components": [], "extracted_triangles": len(faces), "refinement": 1}


def _evaluate(state, parent=None, *, profile=None, policy=POLICY, export="state"):
    profile = _profile(state) if profile is None else profile
    if isinstance(export, str):
        pytest.importorskip("skimage")
        import geom02_canonical as canon

        export = canon.export_from_state(state, profile)
    return evaluate_geometry_gates_v2(state, parent_state=parent or state, profile=profile, policy=policy, export_mesh=export)


def _clean_phi():
    return _box((8, 8, 8), (24, 18, 18))


@pytest.fixture(scope="module")
def clean():
    state = _state(_clean_phi())
    return state, _evaluate(state)


def _only(report, *gate_ids):
    """Exactly ``gate_ids`` fail; every other gate passes."""
    assert report["verdict"]["failed"] == sorted(gate_ids, key=GATE_IDS.index), report["verdict"]
    assert report["verdict"]["unmeasured"] == []


def test_clean_fixture_passes_all_thirteen_gates_and_labels_vacuous_masks(clean):
    state, report = clean
    assert tuple(report["gates"]) == GATE_IDS and report["verdict"]["pass"] is True
    assert report["gates"]["mask_preservation"]["measured"]["vacuous_empty_masks"] is True
    assert report["gates"]["inter_component_gap"]["measured"]["label"] == "not_applicable_single_component"
    assert report["gates"]["min_feature_width"]["measured"]["void_width_label"] == "not_applicable_no_enclosed_or_slot_void"
    assert report["stored_topology_policy_id"]["state"] == DEFAULT_TOPOLOGY_POLICY_ID
    assert report["gates"]["surface_self_intersection"]["measured"]["triangles"] > 0
    import json

    json.dumps(report, allow_nan=False)


def test_stored_state_and_its_legacy_binding_are_not_modified(clean):
    state, report = clean
    before = (state.state_sha256, state.recompute_sha256(), state.phi.tobytes(), state.topology_policy_id)
    _evaluate(state)
    assert (state.state_sha256, state.recompute_sha256(), state.phi.tobytes(), state.topology_policy_id) == before
    assert report["state_sha256"] == state.state_sha256 and report["phi_sha256"] == state.phi_sha256()


def test_non_finite_phi_fails_the_structure_gate_and_blocks_the_rest():
    state = _state(_clean_phi())
    broken = state.phi.copy()
    broken[3, 3, 3] = np.nan
    object.__setattr__(state, "phi", broken)
    report = _evaluate(state, export=None)
    assert "phi_not_finite" in report["gates"]["sdf_finite_structure"]["fail_reasons"]
    assert all(report["gates"][g]["status"] == "unmeasured" for g in GATE_IDS[1:])


def test_scaled_phi_breaks_only_the_distance_property():
    report = _evaluate(_state(3.0 * _clean_phi()))
    _only(report, "sdf_distance_property")


def test_zero_level_plateau_fails_only_the_gradient_gate():
    phi = _clean_phi()
    patch = _patch((6, 10, 10), (7, 16, 16))  # two exact-zero node layers just outside the x-lower face
    phi[patch] = 0.0
    report = _evaluate(_state(phi))
    _only(report, "near_zero_gradient_band")
    failing = report["gates"]["near_zero_gradient_band"]["measured"]["failing_nodes"]
    assert failing["exact_zero_phi"] > 0 and failing["abs_phi_min_max_m"][0] == 0.0


def test_two_cell_sheet_passes_and_one_cell_sheet_fails_the_gradient_floor():
    def sheet(zhi):
        return _state(_faces((6.8, 6.8, 9.8), (28.2, 20.2, zhi)))

    assert _gradient_floor_gate(sheet(12.2), 0.5)["status"] == "pass"
    one = _gradient_floor_gate(sheet(11.4), 0.5)
    assert one["status"] == "fail" and one["measured"]["nodes_below_floor"] > 0


def test_solid_on_the_array_edge_fails_the_margin_and_leaves_the_gradient_unmeasured():
    report = _evaluate(_state(_box((0, 8, 8), (16, 18, 18))))
    assert report["verdict"]["failed"] == ["sdf_boundary_margin", "export_surface_integrity"]  # the extracted surface is open at the array edge
    assert report["gates"]["near_zero_gradient_band"]["unmeasured_reasons"] == ["sign_change_nodes_on_array_boundary"]
    assert report["verdict"]["unmeasured"] == ["near_zero_gradient_band"]


def test_material_in_the_forbidden_mask_fails_the_mask_gate():
    state = _state(_clean_phi(), forbidden_mask=_patch((14, 10, 10), (16, 12, 12)))
    _only(_evaluate(state), "mask_preservation")


def test_lost_fixed_region_fails_the_mask_gate_and_keeps_the_other_violations_visible():
    fixed = _patch((14, 12, 12), (16, 14, 14))
    parent = _state(_clean_phi(), fixed_solid_mask=fixed)
    cavity = _state(np.maximum(_clean_phi(), -_box((13, 11, 11), (17, 15, 15))), fixed_solid_mask=fixed)
    report = _evaluate(cavity, parent)
    _only(report, "mask_preservation")
    assert report["gates"]["mask_preservation"]["fail_reasons"] == ["fixed_solid_not_retained"]
    assert report["parent_state_sha256"] == parent.state_sha256 != report["state_sha256"]


def test_rebinding_filter_removes_only_the_three_named_reasons():
    fixed = _patch((14, 12, 12), (16, 14, 14))
    parent = _state(_clean_phi(), fixed_solid_mask=fixed, forbidden_mask=_patch((30, 3, 3), (31, 4, 4)))
    bad = _state(np.maximum(_clean_phi(), -_box((13, 11, 11), (17, 15, 15))), fixed_solid_mask=fixed, forbidden_mask=_patch((20, 12, 12), (21, 13, 13)))
    raw = set(evaluate_research_transition(POLICY, parent, bad, feature_metrics=None, allowed_events=(), birth_qualified=False).violations)
    assert REBOUND_ONLY_REASONS <= raw and raw - REBOUND_ONLY_REASONS  # legacy binding is the only thing filtered
    report = _evaluate(bad, parent, export=None)
    seen = {r for g in report["gates"].values() for r in g["fail_reasons"] + g["unmeasured_reasons"]}
    assert not seen & REBOUND_ONLY_REASONS
    assert {"fixed_solid_not_retained", "material_in_forbidden_mask", "state_mask_mismatch"} <= seen


def test_two_components_one_cell_apart_fail_the_gap_gate_and_four_cells_pass():
    near = _state(np.minimum(_faces((7.8, 7.8, 7.8), (14.9, 18.2, 18.2)), _faces((15.95, 7.8, 7.8), (24.2, 18.2, 18.2))))
    report = _evaluate(near, export=None)  # a one-cell gap is also an unresolvable zero level for the gradient floor (A4 coupling)
    assert report["gates"]["inter_component_gap"]["status"] == "fail" and report["gates"]["inter_component_gap"]["measured"]["min_gap_m"] == pytest.approx(H)
    assert report["verdict"]["failed"] == ["near_zero_gradient_band", "min_feature_width", "inter_component_gap"]  # the gap is also a one-cell void
    far = _state(np.minimum(_box((8, 8, 8), (13, 18, 18)), _box((17, 8, 8), (24, 18, 18))))
    report = _evaluate(far, export=None)
    assert report["gates"]["inter_component_gap"]["status"] == "pass" and report["gates"]["inter_component_gap"]["measured"]["min_gap_m"] == pytest.approx(4 * H)
    mid = _state(np.minimum(_box((8, 8, 8), (14, 18, 18)), _box((17, 8, 8), (24, 18, 18))))
    assert _evaluate(mid, export=None)["gates"]["inter_component_gap"]["status"] == "unmeasured"


def test_one_cell_plate_fails_solid_width_and_a_two_cell_sheet_passes():
    plate = _evaluate(_state(_faces((6.8, 6.8, 9.8), (28.2, 20.2, 11.4))), export=None)
    assert plate["gates"]["min_feature_width"]["fail_reasons"] == ["minimum_solid_width_violation"]
    sheet = _evaluate(_state(_faces((6.8, 6.8, 9.8), (28.2, 20.2, 12.2))), export=None)
    assert sheet["gates"]["min_feature_width"]["status"] == "pass"


def test_one_cell_slot_fails_void_width():
    slot = np.maximum(_box((8, 8, 8), (26, 18, 18)), -_faces((6.0, 12.05, 6.0), (20.0, 13.1, 30.0)))  # a one-cell blind slot
    report = _evaluate(_state(slot), export=None)
    gate = report["gates"]["min_feature_width"]
    assert gate["fail_reasons"] == ["minimum_void_width_violation"] and gate["measured"]["void_width_label"] == "measured"
    assert report["verdict"]["failed"] == ["near_zero_gradient_band", "min_feature_width"]  # the same A4 coupling


def test_split_and_birth_are_rejected_when_the_step_allows_no_events():
    parent = _state(_clean_phi())
    split = _state(np.maximum(_clean_phi(), -_faces((14.0, 0.0, 0.0), (19.0, 30.0, 30.0))))
    report = _evaluate(split, parent, export=None)
    assert report["gates"]["topology_change_classification"]["fail_reasons"] == ["topology_event_not_permitted:split"]
    assert report["gates"]["component_connectivity"]["status"] == "pass" and report["gates"]["inter_component_gap"]["status"] == "pass"
    born = _state(np.minimum(_clean_phi(), _box((28, 8, 8), (33, 18, 18))))
    reasons = _evaluate(born, parent, export=None)["gates"]["topology_change_classification"]["fail_reasons"]
    assert "topology_event_not_permitted:birth" in reasons and "topology_birth_not_qualified" in reasons
    permitted = dict(_profile(split), allowed_events=["split"])
    assert _evaluate(split, parent, profile=permitted, export=None)["gates"]["topology_change_classification"]["status"] == "pass"


def test_open_mesh_fails_only_the_integrity_gate():
    sphere = trimesh.creation.icosphere(subdivisions=2)
    state = _state(_clean_phi())
    report = _evaluate(state, export=_export(sphere.vertices, sphere.faces[3:]))
    _only(report, "export_surface_integrity")
    assert "mesh_not_watertight" in report["gates"]["export_surface_integrity"]["fail_reasons"]


def test_self_intersecting_closed_meshes_fail_only_the_intersection_gate():
    a, b = trimesh.creation.box(extents=(1, 1, 1)), trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation((0.4, 0.3, 0.2))
    both = trimesh.util.concatenate([a, b])
    state = _state(_clean_phi())
    report = _evaluate(state, export=_export(both.vertices, both.faces))
    _only(report, "surface_self_intersection")
    assert report["gates"]["surface_self_intersection"]["fail_reasons"] == ["mesh_self_intersects"]


def test_too_little_domain_clearance_fails_only_that_gate():
    state = _state(_clean_phi())
    tight = dict(_profile(state), domain_bounds_m=[[0.2, -0.3, -0.3], [2.05, 1.65, 1.65]])  # x lower face of the solid is 0.2 m from the domain
    _only(_evaluate(state, profile=tight), "domain_clearance")


def test_solid_count_over_the_limit_fails_only_the_volume_gate(clean):
    state, report = clean
    n = report["gates"]["volume_semantics"]["measured"]["sampled_solid_centers"]
    _only(_evaluate(state, profile=dict(_profile(state), max_solid_centers=n - 1)), "volume_semantics")
    assert _evaluate(state, profile=dict(_profile(state), max_solid_centers=n))["gates"]["volume_semantics"]["status"] == "pass"
    other = dict(_profile(state), lattice={"origin_m": [0.0, 0.0, 0.0], "spacing_m": 0.025, "node_shape": [121, 65, 49]})
    assert _evaluate(state, profile=other)["gates"]["volume_semantics"]["status"] == "unmeasured"


@pytest.mark.parametrize(
    "key,gates",
    [
        ("eikonal_median_tolerance", ["sdf_distance_property"]),
        ("zero_level_gradient_floor", ["near_zero_gradient_band"]),
        ("boundary_margin_cells", ["sdf_boundary_margin"]),
        ("domain_bounds_m", ["domain_clearance"]),
        ("min_clearance_m", ["domain_clearance"]),
        ("max_solid_centers", ["volume_semantics"]),
        ("allowed_events", ["mask_preservation", "component_connectivity", "topology_change_classification"]),
    ],
)
def test_unregistered_threshold_is_unmeasured_never_defaulted(clean, key, gates):
    state, _ = clean
    report = _evaluate(state, profile=dict(_profile(state), **{key: None}), export=None)
    assert [g for g in GATE_IDS if report["gates"][g]["status"] == "unmeasured" and g not in ("export_surface_integrity", "surface_self_intersection")] == gates


def test_unresolved_policy_limits_and_missing_mesh_are_unmeasured(clean):
    state, _ = clean
    report = _evaluate(state, policy=SDFTopologyPolicyResearchV2(), export=None)
    assert report["gates"]["min_feature_width"]["status"] == "unmeasured" and report["gates"]["inter_component_gap"]["status"] == "unmeasured"
    assert report["gates"]["export_surface_integrity"]["unmeasured_reasons"] == ["export_mesh_not_supplied"]
    assert report["verdict"]["pass"] is False


def test_self_intersection_search_matches_the_p20_detector_on_small_meshes():
    sphere = trimesh.creation.icosphere(subdivisions=3)  # 1280 triangles
    shifted = sphere.copy()
    shifted.apply_translation((0.5, 0.0, 0.0))
    far = sphere.copy()
    far.apply_translation((3.0, 0.0, 0.0))
    planted = trimesh.Trimesh(  # one extra triangle piercing the sphere
        np.vstack((sphere.vertices, [[0.0, 0.0, 0.5], [0.2, 0.0, 1.5], [-0.2, 0.0, 1.5]])),
        np.vstack((sphere.faces, [[len(sphere.vertices), len(sphere.vertices) + 1, len(sphere.vertices) + 2]])),
        process=False,
    )
    coplanar = trimesh.Trimesh(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.1, 0.1, 0], [1.1, 0.1, 0], [0.1, 1.1, 0]], float), np.array([[0, 1, 2], [3, 4, 5]]), process=False)
    cases = {"single": (sphere, "none"), "overlapping": (trimesh.util.concatenate([sphere, shifted]), "fail"), "disjoint": (trimesh.util.concatenate([sphere, far]), "none"),
             "planted": (planted, "fail"), "coplanar": (coplanar, "fail")}
    for name, (mesh, expected) in cases.items():
        assert len(mesh.faces) <= 12_000
        verdict, stats = mesh_self_intersection(mesh.vertices, mesh.faces)
        assert verdict == _triangles_self_intersect(mesh) == expected, name
    assert stats["candidate_pairs"] >= 1
    assert mesh_self_intersection(np.zeros((3, 3)), np.array([[0, 1, 2]]))[0] == "not_evaluated_degenerate_triangle"


def test_subcell_components_are_removed_and_counted_by_the_export_pipeline():
    import geom02_canonical as canon

    sphere = trimesh.creation.icosphere(subdivisions=3, radius=0.6)
    sphere.apply_translation((1.0, 1.0, 1.0))
    speck = trimesh.creation.icosphere(subdivisions=1, radius=0.004)
    speck.apply_translation((1.8, 1.8, 1.8))
    mesh = trimesh.util.concatenate([sphere, speck])
    grid = np.stack(np.meshgrid(*[np.arange(21)] * 3, indexing="ij"), axis=-1) * 0.1
    phi = np.linalg.norm(grid - 1.0, axis=-1) - 0.6
    export = canon.export_from_arrays(mesh.vertices, mesh.faces, phi.astype(np.float32), (0.0, 0.0, 0.0), 0.1, min_diagonal_m=0.1)
    assert len(export["removed_components"]) == 1 and export["topology"]["watertight"] and export["topology"]["signed_volume_m3"] > 0
    assert export["orientation_status"] == "PASS" and export["extracted_triangles"] == len(mesh.faces)


def test_needle_triangles_touching_at_one_vertex_are_not_a_contact_at_the_registered_tolerance():
    """Two coplanar Lewiner needles of the v17 baseline touch only at a shared vertex; P20's absolute 1e-10 tolerance reports a phantom contact."""
    vertices = np.array(
        [[-0.25, 0.2437499999999999, -0.09687499999999993], [-0.25, 0.24687499999999996, -0.09687499999999993], [-0.25, 0.24687499999999996, -0.096875524520874],
         [-0.25, 0.24687499999999996, -0.09375], [-0.25, 0.2468755722045899, -0.09687499999999993],
         [-0.6, 0.0, 0.0], [0.55, 0.0, 0.0], [0.55, 0.1, 0.0]]  # far triangle: sets the extent (and so P20's tolerance) to the v17 mesh's
    )
    mesh = trimesh.Trimesh(vertices, np.array([[0, 1, 2], [3, 4, 1], [5, 6, 7]]), process=False)
    assert _triangles_self_intersect(mesh) == mesh_self_intersection(mesh.vertices, mesh.faces)[0] == "fail"
    assert mesh_self_intersection(mesh.vertices, mesh.faces, tolerance_rel=1e-12)[0] == "none"
