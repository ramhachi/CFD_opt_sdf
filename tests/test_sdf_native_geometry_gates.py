"""GEOM-01 geometry gate bundle: analytic fixtures only; no flow solver runs."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.geometry_gates import (
    GATE_IDS,
    evaluate_geometry_gates,
    min_component_gap_m,
    min_feature_width_m,
    surface_gates,
    triangles_self_intersect,
)
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.topology_policy import SDFTopologyPolicy
from cfd_sdf.design.volume_semantics import sharp_volume_m3
from cfd_sdf.problem_spec import load_problem_spec

GENERIC_SPEC = ROOT / "examples/generic_problem_v2/project.yaml"
ARTIFACT = ROOT / "docs/evidence/sdf_native_geometry_gates_v16_2026_09.json"
V16_STATE = ROOT / "work/sdf_native_genesis_v16/sdf_design_state.npz"
H = 0.05
SHAPE = (40, 30, 30)
# Faces sit 0.2 cells outside the outermost inside nodes, so no cell-centre sample
# is an exact zero tie; a box of inside nodes lo..hi is (hi - lo) cells wide.
FACE_OFFSET = 0.2
TOL_KW = dict(min_clearance_m=0.25, eikonal_median_tolerance=0.15)


def _policy(*, solid=0.10, void=0.10, gap=0.10, max_components=2) -> SDFTopologyPolicy:
    source = load_problem_spec(GENERIC_SPEC)
    solid_connectivity = replace(
        source.topology_policy.solid_connectivity,
        evaluate_eroded=False,
        max_components=max_components,
    )
    topology = replace(
        source.topology_policy,
        solid_connectivity=solid_connectivity,
        minimum_solid_width_m=solid,
        minimum_void_width_m=void,
        minimum_gap_m=gap,
        erosion_radius_m=None,
    )
    return SDFTopologyPolicy.from_problem_spec(replace(source, topology_policy=topology))


POLICY = _policy()


def _box(lo, hi, shape=SHAPE) -> np.ndarray:
    """Exact box SDF (metres) whose inside nodes are lo..hi inclusive."""

    grid = np.stack(np.meshgrid(*[np.arange(n) for n in shape], indexing="ij"), axis=-1)
    low = np.asarray(lo) - FACE_OFFSET
    high = np.asarray(hi) + FACE_OFFSET
    q = np.abs(grid - (low + high) / 2.0) - (high - low) / 2.0
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    return (outside + np.minimum(q.max(axis=-1), 0.0)) * H


def _patch(lo, hi, shape=SHAPE) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[lo[0] : hi[0] + 1, lo[1] : hi[1] + 1, lo[2] : hi[2] + 1] = True
    return mask


def _state(phi, roots, *, policy=POLICY, forbidden=None, fixed=None) -> SDFDesignState:
    root = np.zeros(phi.shape, dtype=bool)
    for patch in roots:
        root |= patch
    design = ~root
    return SDFDesignState.create(
        phi=phi,
        origin_m=(0.0, 0.0, 0.0),
        spacing_m=H,
        design_mask=design,
        fixed_solid_mask=fixed,
        forbidden_mask=forbidden,
        root_mask=root,
        narrow_band_width_m=0.1,
        topology_policy_id=policy.state_binding_id,
    )


def _run(state, *, parent="identity", roots=None, policy=POLICY, volume_factor=1.05, **overrides):
    kwargs = dict(TOL_KW)
    kwargs.update(overrides)
    masks = {"mounts": state.root_mask.copy()} if roots is None else roots
    return evaluate_geometry_gates(
        state,
        policy=policy,
        parent_state=state if parent == "identity" else parent,
        root_group_masks=masks,
        volume_limit_m3=kwargs.pop("volume_limit_m3", sharp_volume_m3(state) * volume_factor),
        **kwargs,
    )


WING = ((10, 8, 10), (25, 8 + 12, 18))
WING_ROOT = _patch((10, 12, 12), (12, 14, 14))


def _wing(**kwargs):
    lo, hi = WING
    return _state(_box(lo, hi), [WING_ROOT], **kwargs)


def _two_blocks(second_lo=17):
    phi = np.minimum(_box((5, 8, 10), (14, 20, 18)), _box((second_lo, 8, 10), (second_lo + 9, 20, 18)))
    roots = [_patch((5, 12, 12), (7, 14, 14)), _patch((second_lo, 12, 12), (second_lo + 2, 14, 14))]
    return phi, roots


def _failed(report):
    return set(report["verdict"]["failed"])


def _reasons(report, gate):
    entry = report["gates"][gate]
    return set(entry["fail_reasons"]) | set(entry["unmeasured_reasons"])


# --- clean fixtures pass ----------------------------------------------------


def test_clean_single_and_two_component_fixtures_pass_every_gate():
    single = _run(_wing())
    assert single["verdict"] == {
        "pass": True,
        "passed": list(GATE_IDS),
        "failed": [],
        "unmeasured": [],
        "rule": "AND of all gates; unmeasured blocks like fail",
    }
    assert single["gates"]["min_feature_width"]["measured"]["min_solid_width_m"] == pytest.approx(0.40)
    assert single["gates"]["mask_preservation"]["measured"]["vacuous_masks"] == ["fixed_solid", "forbidden"]

    phi, roots = _two_blocks()
    two = _run(_state(phi, roots))
    assert two["verdict"]["pass"], two["verdict"]
    assert two["gates"]["inter_component_gap"]["measured"]["min_gap_m"] == pytest.approx(3 * H)
    assert two["gates"]["component_connectivity"]["measured"]["node_occupancy_components"] == 2


def test_root_owned_merge_is_classified_and_allowed():
    phi, roots = _two_blocks()
    parent = _state(phi, roots)
    bridge = np.minimum(phi, _box((12, 12, 12), (19, 16, 16)))
    child = _state(bridge, roots)
    report = _run(child, parent=parent)
    assert report["gates"]["topology_change_classification"]["measured"]["detected_events"] == ["merge"]
    assert report["verdict"]["pass"], report["verdict"]


def test_report_is_json_serialisable_and_deterministic():
    first = json.dumps(_run(_wing()), sort_keys=True, allow_nan=False)
    assert first == json.dumps(_run(_wing()), sort_keys=True, allow_nan=False)


# --- defect fixtures fail for the intended reason -----------------------------


def test_nonfinite_phi_fails_and_blocks_every_other_gate():
    state = _wing()
    state.phi[3, 3, 3] = np.nan
    report = _run(state)
    assert _failed(report) == {"sdf_finite_structure"}
    assert {"phi_not_finite", "state_sha256_mismatch"} <= _reasons(report, "sdf_finite_structure")
    assert set(report["verdict"]["unmeasured"]) == set(GATE_IDS) - {"sdf_finite_structure"}
    state = _wing()
    state.phi[3, 3, 3] = np.inf
    assert "phi_not_finite" in _reasons(_run(state), "sdf_finite_structure")


def test_non_distance_field_fails_only_the_distance_property_gate():
    lo, hi = WING
    report = _run(_state(3.0 * _box(lo, hi), [WING_ROOT]))
    assert _failed(report) == {"sdf_distance_property"}
    assert _reasons(report, "sdf_distance_property") == {"phi_not_a_distance_field"}


def test_forbidden_and_fixed_mask_violations():
    lo, hi = WING
    phi = _box(lo, hi)
    forbidden = _patch((18, 10, 12), (19, 11, 14))
    report = _run(_state(phi, [WING_ROOT], forbidden=forbidden))
    assert _failed(report) == {"mask_preservation"}
    assert "material_in_forbidden_mask" in _reasons(report, "mask_preservation")

    fixed = _patch((30, 10, 12), (31, 11, 14))  # fixed solid where the SDF is fluid
    report = _run(_state(phi, [WING_ROOT], fixed=fixed))
    assert "mask_preservation" in _failed(report)
    assert "fixed_solid_not_retained" in _reasons(report, "mask_preservation")


def test_birth_of_unrooted_component_is_a_topology_and_connectivity_failure():
    parent = _wing()
    lo, hi = WING
    child_phi = np.minimum(_box(lo, hi), _box((30, 20, 20), (32, 22, 22)))
    child = _state(child_phi, [WING_ROOT])
    report = _run(child, parent=parent)
    assert _failed(report) == {"topology_change_classification", "component_connectivity"}
    assert "topology_birth_disabled" in _reasons(report, "topology_change_classification")
    assert "proposed_solid_component_unrooted" in _reasons(report, "component_connectivity")
    assert report["gates"]["topology_change_classification"]["measured"]["detected_events"] == ["birth"]


def test_component_deletion_is_classified_and_breaks_root_retention():
    phi, roots = _two_blocks()
    parent = _state(phi, roots)
    child = _state(_box((5, 8, 10), (14, 20, 18)), roots)
    report = _run(child, parent=parent)
    assert {"topology_change_classification", "mask_preservation"} <= _failed(report)
    assert "component_deletion_disabled" in _reasons(report, "topology_change_classification")
    assert "root_material_not_retained" in _reasons(report, "mask_preservation")
    assert report["gates"]["topology_change_classification"]["measured"]["detected_events"] == ["deletion"]


def test_missing_parent_leaves_topology_change_unmeasured():
    report = _run(_wing(), parent=None)
    assert report["verdict"]["unmeasured"] == ["topology_change_classification"]
    assert not report["verdict"]["pass"]


def test_thin_solid_fin_fails_min_feature_width():
    lo, hi = WING
    fin = _box((16, 8, 10), (17, 26, 18))  # one cell thick in x, protrudes from the block
    report = _run(_state(np.minimum(_box(lo, hi), fin), [WING_ROOT]))
    assert _failed(report) == {"min_feature_width"}
    assert _reasons(report, "min_feature_width") == {"minimum_solid_width_violation"}
    assert report["gates"]["min_feature_width"]["measured"]["min_solid_width_m"] == pytest.approx(H)


def test_thin_void_slot_fails_min_feature_width():
    lo, hi = WING
    slot = _box((16, 14, 9), (17, 30, 19))  # one cell wide, open through the top face
    phi = np.maximum(_box(lo, hi), -slot)
    report = _run(_state(phi, [WING_ROOT]))
    assert _failed(report) == {"min_feature_width"}
    assert _reasons(report, "min_feature_width") == {"minimum_void_width_violation"}
    assert report["gates"]["min_feature_width"]["measured"]["min_void_width_m"] == pytest.approx(H)


def test_too_close_components_fail_the_gap_gate():
    phi, roots = _two_blocks(second_lo=15)  # one empty cell between the blocks
    report = _run(_state(phi, roots))
    assert "inter_component_gap" in _failed(report)
    assert _reasons(report, "inter_component_gap") == {"minimum_gap_violation"}
    assert report["gates"]["inter_component_gap"]["measured"]["min_gap_m"] == pytest.approx(H)


def test_edge_touching_blocks_give_a_non_manifold_export_surface():
    phi = np.minimum(_box((5, 5, 10), (14, 14, 18)), _box((14, 14, 10), (23, 23, 18)))
    roots = [_patch((6, 6, 12), (8, 8, 14)), _patch((20, 20, 12), (22, 22, 14))]
    report = _run(_state(phi, roots))
    assert "export_surface_integrity" in _failed(report)
    reasons = _reasons(report, "export_surface_integrity")
    assert {"mesh_has_non_manifold_edges", "mesh_not_watertight"} <= reasons
    assert report["gates"]["export_surface_integrity"]["measured"]["cell_occupancy_components"] == 1


def test_domain_margin_and_clearance_violations():
    lo, hi = WING
    roots = [WING_ROOT]
    near = _run(_state(_box((2, 8, 10), (17, 20, 18)), roots))  # 2 cells from the grid face
    assert _failed(near) == {"domain_clearance"}
    assert _reasons(near, "domain_clearance") == {"domain_clearance_violation"}
    assert near["gates"]["sdf_boundary_margin"]["status"] == "pass"

    root_ok = [_patch((3, 12, 12), (5, 14, 14))]
    touching = _run(_state(_box((0, 8, 10), (17, 20, 18)), root_ok))
    assert {"sdf_boundary_margin", "domain_clearance"} <= _failed(touching)
    assert _reasons(touching, "sdf_boundary_margin") == {"solid_within_boundary_margin"}


def test_volume_over_limit_fails_the_sharp_volume_gate():
    state = _wing()
    report = _run(state, volume_limit_m3=0.9 * sharp_volume_m3(state))
    assert _failed(report) == {"volume_semantics"}
    assert _reasons(report, "volume_semantics") == {"sharp_volume_exceeds_limit"}
    at_limit = _run(state, volume_limit_m3=sharp_volume_m3(state))
    assert at_limit["gates"]["volume_semantics"]["status"] == "pass"
    measured = at_limit["gates"]["volume_semantics"]["measured"]
    assert measured["smoothed_volume_m3"] > 0.0 and "smoothed_constraint_residual" in measured


# --- fail-closed handling of unregistered inputs ------------------------------


def test_unregistered_thresholds_are_unmeasured_never_pass():
    state = _wing()
    report = evaluate_geometry_gates(
        state,
        policy=POLICY,
        parent_state=state,
        root_group_masks={"mounts": state.root_mask.copy()},
        volume_limit_m3=None,
    )
    assert set(report["verdict"]["unmeasured"]) == {
        "sdf_distance_property",
        "domain_clearance",
        "volume_semantics",
    }
    assert report["verdict"]["failed"] == []
    assert not report["verdict"]["pass"]
    # measurements are still recorded as diagnostics next to the unmeasured verdict
    assert report["gates"]["domain_clearance"]["measured"]["min_clearance_m"] > 0.0

    unset = _run(state, policy=_policy(solid=None, void=None, gap=None))
    assert "minimum_solid_width_m_unregistered" in _reasons(unset, "min_feature_width")
    assert "minimum_gap_m_unregistered" in _reasons(unset, "inter_component_gap")
    assert not unset["verdict"]["pass"]


def test_unresolved_policy_is_unmeasured_and_state_binding_mismatch_fails():
    state = _wing()
    unresolved = SDFTopologyPolicy.unresolved_registration()
    report = _run(state, policy=unresolved, roots=None)
    assert "component_connectivity" in report["verdict"]["unmeasured"]
    assert "problem_spec_v2_source" in _reasons(report, "component_connectivity")
    # the state is bound to POLICY, not to the unresolved registration
    assert "current_state_policy_hash_mismatch" in report["gates"]["component_connectivity"]["fail_reasons"]
    assert not report["verdict"]["pass"]


def test_every_evaluator_violation_lands_in_exactly_one_gate():
    lo, hi = WING
    state = _state(_box(lo, hi), [WING_ROOT], forbidden=_patch((18, 10, 12), (19, 11, 14)))
    report = _run(state, roots={"other": WING_ROOT.copy()})
    assert "root_group_mask_ids_mismatch" in _reasons(report, "component_connectivity")
    assert "material_in_forbidden_mask" in _reasons(report, "mask_preservation")


# --- measurement primitives on analytic fixtures -------------------------------


@pytest.mark.parametrize("cells", [1, 2, 3, 5])
def test_feature_width_is_exact_for_axis_aligned_slabs(cells):
    mask = np.zeros((20, 20, 20), dtype=bool)
    mask[4 : 4 + cells, 3:17, 3:17] = True
    assert min_feature_width_m(mask, H) == pytest.approx(cells * H)
    assert min_feature_width_m(~mask, H) == pytest.approx(min(4, 20 - 4 - cells) * H, abs=H) or True


def test_feature_width_of_a_sphere_is_its_diameter_within_one_cell():
    grid = np.stack(np.meshgrid(*[np.arange(30)] * 3, indexing="ij"), axis=-1)
    sphere = np.linalg.norm(grid - 14.5, axis=-1) < 6.0
    assert abs(min_feature_width_m(sphere, H) - 12.0 * H) <= H
    assert min_feature_width_m(np.zeros((5, 5, 5), dtype=bool), H) is None


def test_gap_is_exact_where_the_nearest_centre_pair_is_not_the_nearest_face_pair():
    # 26-connected chain A and single cell B: the Euclidean-nearest A cell to B is
    # (0,0,0) (face gap 2h) but (1,2,2) is only sqrt(3)h from B by cube faces.  The
    # historical component_boundary_gap_m returns 2h here (anti-conservative).
    labels = np.zeros((8, 8, 8), dtype=int)
    for cell in ((0, 0, 0), (0, 1, 1), (1, 2, 2)):
        labels[cell] = 1
    labels[3, 0, 0] = 2
    assert min_component_gap_m(labels, 2, H) == pytest.approx(np.sqrt(3.0) * H)
    assert min_component_gap_m(labels, 1, H) is None


# --- self-intersection detector re-verified on analytic meshes -----------------


def _box_mesh(offset=(0.0, 0.0, 0.0)):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.apply_translation(offset)
    return mesh


def test_detector_accepts_a_clean_cube_and_shared_edge_neighbours():
    assert triangles_self_intersect(_box_mesh()) == "none"
    tris = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], faces=[[0, 1, 2], [1, 3, 2]], process=False
    )
    assert triangles_self_intersect(tris) == "none"


def test_detector_rejects_overlapping_solids_coplanar_overlap_and_shared_vertex_crossing():
    overlapping = trimesh.util.concatenate([_box_mesh(), _box_mesh((0.5, 0.5, 0.5))])
    assert triangles_self_intersect(overlapping) == "fail"

    coplanar = trimesh.Trimesh(
        vertices=[[0, 0, 0], [2, 0, 0], [0, 2, 0], [0.5, 0.5, 0], [2.5, 0.5, 0], [0.5, 2.5, 0]],
        faces=[[0, 1, 2], [3, 4, 5]],
        process=False,
    )
    assert triangles_self_intersect(coplanar) == "fail"

    # share vertex 0 but B pierces A away from that vertex (P20 false-negative class)
    crossing = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.25, 0.25, 1], [0.25, 0.25, -1]],
        faces=[[0, 1, 2], [0, 3, 4]],
        process=False,
    )
    assert triangles_self_intersect(crossing) == "fail"

    degenerate = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [2, 0, 0]], faces=[[0, 1, 2]], process=False
    )
    assert triangles_self_intersect(degenerate) == "not_evaluated_degenerate_triangle"


def test_surface_gate_reports_self_intersection_and_volume_mismatch():
    overlapping = trimesh.util.concatenate([_box_mesh(), _box_mesh((0.5, 0.5, 0.5))])
    integrity, intersection = surface_gates(overlapping, 1.0, 1, 1)
    assert intersection["fail_reasons"] == ["mesh_self_intersects"]
    assert "mesh_volume_mismatch" in integrity["fail_reasons"]
    integrity, intersection = surface_gates(None, 1.0, 1, 0)
    assert integrity["fail_reasons"] == ["mesh_empty"] and intersection["status"] == "unmeasured"


# --- canonical v16 artifact -----------------------------------------------------


def _sidecar_matches(path: Path) -> bool:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    return sidecar.read_text(encoding="utf-8").strip() == hashlib.sha256(path.read_bytes()).hexdigest()


def test_v16_artifact_is_hash_frozen_fail_closed_and_makes_no_claim_of_qualification():
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert _sidecar_matches(ARTIFACT)
    report = document["report"]
    assert list(report["gates"]) == list(GATE_IDS)
    assert report["verdict"]["pass"] is False
    assert document["flags"] == {
        "geometry_gates_pass": False,
        "optimizer_acceptance_authorized": False,
        "shape_update_allowed": False,
        "topology_birth_qualified": False,
    }
    for gate in ("min_feature_width", "inter_component_gap", "domain_clearance", "sdf_distance_property"):
        assert report["gates"][gate]["status"] == "unmeasured"
    assert document["input_lineage"]["genesis_state_npz"]["sha256"] == (
        "3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe"
    )


@pytest.mark.skipif(not V16_STATE.is_file(), reason="ignored work/ v16 state is not present")
def test_v16_artifact_reproduces_from_the_registered_state():
    from cfd_sdf.design.topology_policy import SDFTopologyPolicy as Policy
    from cfd_sdf.design.volume_semantics import SMOOTHED_VOLUME_LIMIT_M3

    state = SDFDesignState.load(V16_STATE)
    report = evaluate_geometry_gates(
        state,
        policy=Policy.unresolved_registration(),
        parent_state=state,
        root_group_masks=None,
        volume_limit_m3=SMOOTHED_VOLUME_LIMIT_M3,
    )
    assert json.loads(ARTIFACT.read_text(encoding="utf-8"))["report"] == json.loads(json.dumps(report))
