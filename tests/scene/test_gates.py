"""Solver-free scene admission; no claim of registered physics qualification."""

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
import trimesh

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_gen.scene.gates import SceneGatePolicy, evaluate_scene_gates, opening_defect_gate
from cfd_gen.scene.primitives import BoxBody, EndplatePlate, MeshBody, PlateElement
from cfd_gen.scene.scene import Scene


def policy(**kwargs):
    values = dict(
        required_components=1,
        envelope={"lower": [-20, -20, -20], "upper": [20, 20, 20],
                  "rule_source": "synthetic test envelope; no FSAE qualification"},
        clearance_m=0.1,
    )
    values.update(kwargs)
    return SceneGatePolicy(**values)


def plate(id="p", **kwargs):
    values = dict(x=0.0, z=1.0, chord=1.2, thickness=0.5, span=1.0)
    values.update(kwargs)
    return PlateElement(id=id, **values)


def run(scene=None, **kwargs):
    return evaluate_scene_gates(
        scene or Scene((plate(),), ground=-2), h=0.1, dimension=2,
        policy=kwargs.pop("policy", policy()), **kwargs,
    )


def test_valid_control_and_zero_solver_budget():
    report = run()
    assert report["passed"], report
    assert report["rejection_reasons"] == []
    assert report["cfd_evaluations"] == report["budget_charged"] == 0
    assert report["gates"]["thickness"]["thresholds"]["source"] == "development_default_4h_not_RES00_registered"


def test_fixed_tyre_touching_ground_is_outside_design_constraint_scope():
    wing = plate()
    tyre = BoxBody("tyre", (4, 0, 0.6), (0.6, 0.6, 0.6))
    scene = Scene((wing,), fixed=(tyre,), ground=0)
    state = scene.sample(.1, dimension=2)
    points = Scene.grid_points(state)[..., [0, 2]]
    movable, fixed = wing.phi(points) < 0, tyre.phi(points) < 0
    p = policy(required_components=2,
        envelope={"lower": [-1, -1, .6], "upper": [1, 1, 1.4], "rule_source": "synthetic wing-only rules box"},
        domain={"lower": [-1, -1, .5], "upper": [1, 1, 1.5]},
        forbidden_mask=fixed, require_forbidden_mask=True, root_masks={"wing_mount": movable})
    report = run(scene, state=state, policy=p)
    assert report["passed"], report["rejection_reasons"]
    assert report["gates"]["connectivity"]["measured"]["solid_components"] == 2
    assert report["gates"]["clearance"]["measured"]["ground_m"] == pytest.approx(.75)


def test_fixed_context_still_participates_in_pair_gap_check():
    wing = plate()
    tyre = BoxBody("tyre", (0, 0, .1), (.3, .3, .3))
    report = run(Scene((wing,), fixed=(tyre,), ground=-2), policy=policy(required_components=2))
    assert report["gates"]["gap"]["status"] == "fail"
    assert "minimum_gap_violation|p|tyre" in report["gates"]["gap"]["fail_reasons"]


def test_fixed_stl_tyre_and_thin_endplate_do_not_own_design_width_or_joints(tmp_path):
    h = .1
    # Small closed octagonal tyre stand-in, tangent to ground, hash-bound STL.
    tyre_mesh = trimesh.creation.cylinder(radius=.4, height=.6, sections=8)
    tyre_mesh.apply_translation([2., 0., .3])
    payload = tyre_mesh.export(file_type="stl")
    path = tmp_path / "tyre.stl"
    path.write_bytes(payload)
    tyre = MeshBody("tyre", str(path), hashlib.sha256(payload).hexdigest())
    panel = EndplatePlate("fixed_panel", -2., 0., .8, .8, .6, 2*h)
    wing = plate(chord=.8, thickness=4*h, span=.6)
    scene = Scene((wing,), fixed=(tyre, panel), ground=0)
    result = evaluate_scene_gates(scene, h=h, dimension=3, policy=policy(required_components=3,
        envelope={"lower": [-.7, -.5, .6], "upper": [.7, .5, 1.4],
                  "rule_source": "synthetic movable-wing-only envelope"}))
    assert result["passed"], result["rejection_reasons"]
    assert set(result["gates"]["thickness"]["measured"]["components"]) == {wing.id}
    assert result["gates"]["endplate_joints"]["thresholds"]["required_pairs"] == []
    assert set(result["gates"]["gap"]["measured"]["pairs"]) == {"p|tyre", "p|fixed_panel"}
    context = result["context_resolution"]
    assert context["scope"] == "fixed_context_informational_only"
    assert context["h_m"] == h
    assert context["components"]["tyre"]["lower_bound_m"] is None
    assert context["components"]["tyre"]["sampled_solid_nodes"] > 0
    assert context["components"]["fixed_panel"]["lower_bound_cells"] == pytest.approx(2)
    assert result["cfd_evaluations"] == result["budget_charged"] == 0


def test_fixed_endplate_cannot_receive_a_design_joint_gap_exemption():
    wing = plate(span=1, z=1)
    tip = EndplatePlate("fixed_tip", 0, .5, 1, 1, 1.5, .2)
    scene = Scene((wing,), fixed=(tip,), ground=-2)
    result = evaluate_scene_gates(scene, h=.1, dimension=3,
        policy=policy(joints=((wing.id, tip.id),)))
    assert "joint_ids_or_types_invalid|p|fixed_tip" in result["gates"]["endplate_joints"]["fail_reasons"]
    assert "component_overlap|p|fixed_tip" in result["gates"]["gap"]["fail_reasons"]


def test_missing_policy_inputs_refuse_admission():
    report = run(policy=SceneGatePolicy())
    assert not report["passed"]
    assert report["gates"]["envelope"]["status"] == "unmeasured"
    assert report["gates"]["clearance"]["status"] == "unmeasured"
    assert report["gates"]["connectivity"]["status"] == "unmeasured"


def test_thickness_and_deformed_normal_width_are_separate_from_parameter():
    report = run(Scene((plate(thickness=0.3),), ground=-2))
    assert report["gates"]["thickness"]["status"] == "fail"
    deformed = run(Scene((plate(thickness=0.4, camber=0.06, reflex=0.04),), ground=-2))
    gate = deformed["gates"]["thickness"]
    assert gate["measured"]["components"]["p"]["lower_bound_m"] < 0.4
    assert gate["status"] != "pass"


@pytest.mark.parametrize("distance,expected", [(0.1, "fail"), (0.8, "fail"), (1.3, "pass")])
def test_gap_overlap_and_separation(distance, expected):
    scene = Scene((plate("a"), plate("b", z=1 + distance)), ground=-2)
    report = run(scene, policy=policy(required_components=2))
    assert report["gates"]["gap"]["status"] == expected
    if distance == 0.1:
        assert any("overlap" in item["reason"] for item in report["rejection_reasons"])


def test_containment_is_overlap_even_without_boundary_crossing():
    outer, inner = plate("outer", thickness=0.8), plate("inner", chord=0.4, thickness=0.2)
    report = run(Scene((outer, inner), ground=-2))
    assert report["gates"]["gap"]["status"] == "fail"
    assert "component_overlap|outer|inner" in report["gates"]["gap"]["fail_reasons"]


def test_rejection_separator_is_unambiguous_for_colon_containing_ids():
    a = plate("main:split2:0")
    b = replace(a, id="main:split2:1", x=.1)
    report = run(Scene((a, b), ground=-2))
    reason = f"component_overlap|{a.id}|{b.id}"
    assert reason in report["gates"]["gap"]["fail_reasons"]
    assert reason.split("|") == ["component_overlap", a.id, b.id]
    with pytest.raises(ValueError, match="identifier"):
        policy(root_masks={"bad|root": None})


def test_gap_near_limit_without_certifying_aabb_lower_bound_is_unmeasured():
    angle = np.pi / 4
    normal_offset = .5 + .4
    a = plate("a", angle=angle)
    b = plate("b", angle=angle, x=-normal_offset*np.sin(angle), z=1+normal_offset*np.cos(angle))
    report = run(Scene((a, b), ground=-2), policy=policy(required_components=2))
    assert report["gates"]["gap"]["status"] == "unmeasured"


def test_sampled_gap_below_limit_is_definite_failure_without_symmetric_guard():
    angle = np.pi / 4
    normal_offset = .5 + .39
    a = plate("a", angle=angle)
    b = plate("b", angle=angle, x=-normal_offset*np.sin(angle), z=1+normal_offset*np.cos(angle))
    report = run(Scene((a, b), ground=-2), policy=policy(required_components=2))
    gate = report["gates"]["gap"]
    assert gate["measured"]["pairs"]["a|b"]["minimum_sampled_field_m"] < .4
    assert "minimum_gap_violation|a|b" in gate["fail_reasons"]
    assert gate["status"] == "fail"


def test_connectivity_and_individual_disappearance():
    separated = Scene((plate("a"), plate("b", x=4)), ground=-2)
    report = run(separated)
    assert report["gates"]["connectivity"]["status"] == "fail"
    coarse = Scene((plate(thickness=0.01, z=0.05),), ground=-2)
    report = run(coarse)
    assert any("absent" in reason for reason in report["gates"]["connectivity"]["fail_reasons"])


def test_closed_void_is_detected_by_face_connected_boundary_floodfill():
    # Rectangular ring, all four bars meet with positive overlap.
    bars = (
        EndplatePlate("left", -1, 0, 1, 3, 0.5, 0.5),
        EndplatePlate("right", 1, 0, 1, 3, 0.5, 0.5),
        EndplatePlate("bottom", 0, 0, -0.25, 0.5, 2.5, 0.5),
        EndplatePlate("top", 0, 0, 2.25, 0.5, 2.5, 0.5),
    )
    report = run(Scene(bars, ground=-2))
    assert report["gates"]["closed_cavities"]["status"] == "fail"
    assert report["gates"]["closed_cavities"]["measured"]["enclosed_void_nodes"] > 0


def test_envelope_and_ground_clearance_and_explicit_domain():
    scene = Scene((plate(z=0.2),), ground=0)
    report = run(scene, policy=policy(envelope={"lower": [-0.2, -5, -5], "upper": [0.2, 5, 5], "rule_source": "test"}))
    assert report["gates"]["envelope"]["status"] == "fail"
    assert report["gates"]["clearance"]["status"] == "fail"
    no_ground = Scene((plate(),))
    assert run(no_ground)["gates"]["clearance"]["status"] == "unmeasured"
    domain = {"lower": [-3, -3, -3], "upper": [3, 3, 3]}
    assert run(no_ground, policy=policy(domain=domain))["gates"]["clearance"]["status"] == "pass"


def test_explicit_endplate_joint_is_required_and_contact_is_verified():
    # Horizontal plate's span terminates at y=.5; the endplate overlaps that tip.
    wing = plate(span=1, z=1)
    tip = EndplatePlate("tip", 0, 0.5, 1, 1, 1.5, 0.4)
    scene = Scene((wing, tip), ground=-2)
    report = evaluate_scene_gates(scene, h=0.1, dimension=3, policy=policy())
    assert report["gates"]["endplate_joints"]["status"] == "fail"
    declared = policy(joints=(("p", "tip"),))
    report = evaluate_scene_gates(scene, h=0.1, dimension=3, policy=declared)
    assert report["gates"]["endplate_joints"]["status"] == "pass"
    assert report["gates"]["gap"]["status"] == "pass"
    distant = Scene((wing, replace(tip, y=3)), ground=-2)
    report = evaluate_scene_gates(distant, h=0.1, dimension=3, policy=declared)
    assert report["gates"]["endplate_joints"]["status"] == "fail"


def test_box_component_does_not_require_a_wing_endplate_joint():
    pod = BoxBody("pod", (0, 0, 1), (.5, .5, .5))
    ep = EndplatePlate("ep", 4, 0, 1, 1, 1, .5)
    report = run(Scene((pod,), fixed=(ep,), ground=-2), policy=policy(required_components=2))
    assert report["gates"]["endplate_joints"]["status"] == "pass"
    assert report["gates"]["endplate_joints"]["thresholds"]["required_pairs"] == []


def test_root_and_forbidden_masks_and_declared_missing_masks():
    scene = Scene((plate(),), ground=-2)
    state = scene.sample(0.1, dimension=2)
    solid = state.phi < 0
    root = np.zeros(state.shape, bool)
    root[tuple(np.argwhere(solid)[0])] = True
    p = policy(root_masks={"mount": root}, forbidden_mask=~solid)
    report = run(scene, state=state, policy=p)
    assert report["gates"]["masks_roots"]["status"] == "pass"
    p = policy(root_masks={"mount": ~solid}, forbidden_mask=solid)
    report = run(scene, state=state, policy=p)
    assert report["gates"]["masks_roots"]["status"] == "fail"
    missing = policy(root_masks={"mount": None}, require_forbidden_mask=True)
    report = run(scene, state=state, policy=missing)
    assert report["gates"]["masks_roots"]["status"] == "unmeasured"


@pytest.mark.parametrize("phase", [(0, 0, 0), (0.25, 0, 0.5), (0.75, 0, 0.25)])
def test_topology_has_no_r0_subcell_component_alias(phase):
    report = run(phase=phase)
    assert report["gates"]["connectivity"]["measured"]["solid_components"] == 1
    assert report["gates"]["opening_defect"]["status"] == "pass"


@pytest.mark.parametrize("dimension", [2, 3])
@pytest.mark.parametrize("index", range(16))
def test_exact_4h_thickness_and_gap_admit_all_sixteen_subcell_phases(dimension, index):
    a = plate("main", thickness=.4, span=.6)
    b = replace(a, id="flap", z=a.z+.8)
    scene = Scene((a, b), ground=-2)
    phase = (index/16, 0 if dimension == 2 else ((3*index) % 16)/16, ((5*index) % 16)/16)
    report = evaluate_scene_gates(scene, h=.1, dimension=dimension,
        policy=policy(required_components=2), phase=phase)
    assert report["passed"], report["rejection_reasons"]
    assert report["gates"]["connectivity"]["measured"]["solid_components"] == 2


@pytest.mark.parametrize("case", ["valid", "thin", "resource_limit"])
def test_sixteen_phase_admission_requires_every_phase_pass_and_retains_reasons(case):
    from cfd_gen.scene.gates import evaluate_scene_gates_phases

    scene = Scene((plate(thickness=.3 if case == "thin" else .5),), ground=-2)
    phases = [(i/16, 0, ((5*i) % 16)/16) for i in range(16)]
    report = evaluate_scene_gates_phases(scene, h=.0001 if case == "resource_limit" else .1,
        dimension=2, policy=policy(), phases=phases)
    assert report["passed"] is (case == "valid")
    assert report["phase_count"] == len(report["phase_reports"]) == 16
    assert report["scene_sha256"] == scene.scene_sha256
    assert [row["phase"] for row in report["phase_reports"]] == [list(p) for p in phases]
    for row in report["phase_reports"]:
        assert row["result"]["scene_sha256"] == scene.scene_sha256
        if case != "valid":
            assert row["result"]["rejection_reasons"]
    assert {tuple(item["phase"]) for item in report["rejection_reasons"]} == (set() if case == "valid" else set(phases))
    if case == "resource_limit":
        assert all(row["result"]["gates"]["sampling"]["status"] == "unmeasured" for row in report["phase_reports"])
    assert report["cfd_evaluations"] == report["budget_charged"] == 0


def test_sixteen_phase_admission_cannot_hide_one_rejected_phase(monkeypatch):
    import cfd_gen.scene.gates as gates

    phases = [(i/16, 0, ((5*i) % 16)/16) for i in range(16)]
    original = gates.evaluate_scene_gates
    visited = []
    def reject_one(*args, phase, **kwargs):
        visited.append(tuple(phase))
        result = original(*args, phase=phase, **kwargs)
        if tuple(phase) == phases[5]:
            result["passed"] = False
            result["rejection_reasons"] = [{"gate": "closed_cavities", "reason": "synthetic_phase_rejection", "status": "fail"}]
        return result
    monkeypatch.setattr(gates, "evaluate_scene_gates", reject_one)
    scene = Scene((plate(),), ground=-2)
    report = gates.evaluate_scene_gates_phases(scene, h=.1, dimension=2, policy=policy(), phases=phases)
    assert not report["passed"]
    assert visited == phases  # The failure cannot short-circuit the remaining record.
    assert report["rejection_reasons"] == [{"phase": list(phases[5]), "gate": "closed_cavities",
                                            "reason": "synthetic_phase_rejection", "status": "fail"}]


@pytest.mark.parametrize("phases,dimension", [
    ([], 2), ([(0, 0, 0)] * 16, 2),
    ([(i/16, 0, 0) for i in range(15)], 2),
    ([(i/16, 0, 0) for i in range(17)], 2),
    ([(i/16, .5, 0) for i in range(16)], 2),
    ([(i/16, 0, float("nan")) for i in range(16)], 3),
    ([(i/16, 0j, 0) for i in range(16)], 3),
    ([(i/16, 0) for i in range(16)], 3),
    (None, 2),
])
def test_invalid_common_phase_sets_fail_before_evaluation(monkeypatch, phases, dimension):
    import cfd_gen.scene.gates as gates

    def unexpected_evaluation(*args, **kwargs):
        pytest.fail("invalid phase set reached geometry evaluation")
    monkeypatch.setattr(gates, "evaluate_scene_gates", unexpected_evaluation)
    with pytest.raises(ValueError, match="phase"):
        gates.evaluate_scene_gates_phases(Scene((plate(),)), h=.1, dimension=dimension,
            policy=policy(), phases=phases)


def test_explicit_merged_element_distance_contract_exemption_is_recorded():
    from cfd_gen.scene.scene import MergedElement

    a = plate("a")
    merged = MergedElement("merge:a:b", (a, replace(a, id="b", x=.4)))
    report = run(Scene((merged,), ground=-2))
    assert report["passed"], report["rejection_reasons"]
    assert report["distance_contract_exemptions"] == [merged.id]


@pytest.mark.parametrize("scene", [Scene(()), Scene((), ground=0), Scene((), fixed=(plate(),))])
def test_no_design_scene_keeps_report_hash_schema(scene):
    report = run(scene)
    assert not report["passed"]
    assert report["scene_sha256"] == scene.scene_sha256
    assert report["state_sha256"] is None
    assert report["distance_contract_exemptions"] == []


def test_design_lattice_resource_limit_is_unmeasured_without_allocating():
    scene = Scene((plate(chord=3, span=3),), ground=-2)
    report = evaluate_scene_gates(scene, h=.001, dimension=3, policy=policy())
    assert not report["passed"]
    assert report["gates"]["sampling"]["status"] == "unmeasured"
    assert report["gates"]["sampling"]["unmeasured_reasons"] == ["scene_sampling_resource_limit"]
    measured = report["gates"]["sampling"]["measured"]
    assert measured["node_count"] > measured["max_nodes"] == 2_000_000
    assert report["scene_sha256"] == scene.scene_sha256
    assert report["state_sha256"] is None
    assert report["cfd_evaluations"] == report["budget_charged"] == 0


def test_mw01_sized_r3_crop_is_explicitly_unmeasured():
    wing = plate(chord=.3, thickness=.02, span=1.4)
    report = evaluate_scene_gates(Scene((wing,), ground=0), h=.005, dimension=3, policy=policy())
    gate = report["gates"]["opening_defect"]
    assert gate["status"] == "unmeasured"
    assert gate["unmeasured_reasons"] == ["R3_refinement_resource_limit"]
    assert gate["measured"]["node_count"] > gate["measured"]["max_nodes"] == 8_000_000


def test_gate_and_knockout_share_element_parameter_floors():
    from cfd_gen.scene.gates import thickness_parameter_floors
    from cfd_gen.scene.events import thickness_knockout_ids

    h = .025
    flat = plate("flat", chord=1, thickness=4*h, z=0)
    curved = replace(flat, id="curved", camber=.06, reflex=-.04, x=2)
    scene = Scene((flat, curved), ground=-2)
    floors = thickness_parameter_floors(scene, h=h, dimension=2, policy=policy())
    assert floors[flat.id] == pytest.approx(4*h)
    assert floors[curved.id] > 4*h
    scene = replace(scene, components=tuple(replace(p, thickness=floors[p.id]) for p in scene.components))
    gate = evaluate_scene_gates(scene, h=h, dimension=2, policy=policy(required_components=2))["gates"]["thickness"]
    assert gate["status"] == "pass"
    for p in scene.components:
        assert gate["measured"]["components"][p.id]["parameter_floor_m"] == pytest.approx(floors[p.id])
    history = [{"checkpoint": k, "thickness": floors} for k in (1, 2)]
    assert thickness_knockout_ids(history, floors) == ("curved", "flat")


def test_checkpoint_floor_provenance_tracks_changed_camber_and_removed_ids():
    from cfd_gen.scene.gates import thickness_parameter_floors
    from cfd_gen.scene.events import thickness_knockout_ids

    h = .025
    flat = plate("wing", chord=1, thickness=4*h)
    curved = replace(flat, camber=.06, reflex=-.04)
    snapshots = [thickness_parameter_floors(Scene((p,)), h=h, dimension=2, policy=policy())
                 for p in (flat, curved)]
    assert snapshots[1]["wing"] > snapshots[0]["wing"]
    history = [{"checkpoint": i, "thickness": dict(floors), "parameter_floors": floors}
               for i, floors in enumerate(snapshots, 1)]
    assert thickness_knockout_ids(history) == ("wing",)
    # A removed parameter is valid history, and cannot become a candidate at
    # the next checkpoint. Its old per-checkpoint floor stays available.
    history.append({"checkpoint": 3, "thickness": {}, "parameter_floors": {}})
    assert thickness_knockout_ids(history) == ()


def test_opening_solid_void_counterexamples_and_empty_convention():
    x, z = np.meshgrid(np.arange(-12, 13), np.arange(-12, 13), indexing="ij")
    thin = np.maximum(np.abs(x) - 8, np.abs(z) - 0.3).astype(float)
    assert opening_defect_gate(thin, 1.0)["measured"]["solid_status"] == "fail"
    # A long thin slit in a thick solid; void defect cannot be hidden by solid width.
    box = np.maximum(np.abs(x) - 9, np.abs(z) - 9)
    slit = np.maximum(np.abs(x) - 7, np.abs(z) - 0.3)
    cavity = np.maximum(box, -slit).astype(float)
    assert opening_defect_gate(cavity, 1.0)["measured"]["void_status"] == "fail"
    assert opening_defect_gate(np.ones((9, 9)), 1.0)["status"] == "unmeasured"
    assert opening_defect_gate(-np.ones((9, 9)), 1.0)["measured"]["void_status"] == "pass"


@pytest.mark.parametrize("length,status", [(0.5, "pass"), (1.25, "unmeasured"), (1.5, "fail")])
def test_r3_fin_defect_thresholds_include_unmeasured_band(length, status):
    x, z = np.meshgrid(np.arange(-7, 8, dtype=float), np.arange(-7, 8, dtype=float), indexing="ij")
    base = np.maximum(np.abs(x)-4, np.abs(z+2)-2)
    fin = np.maximum(np.abs(x)-0.3, np.abs(z-length/2)-length/2)
    gate = opening_defect_gate(np.minimum(base, fin), 1.)
    assert gate["status"] == status
    if length == 1.25:
        assert gate["measured"]["solid_defect_m"] == 1.25


def test_clipped_finite_solid_and_underspecified_width_provenance_block_acceptance():
    scene = Scene((plate(),), ground=-2)
    state = scene.sample(.1, dimension=2, padding_cells=0, bounds=((-0.2, 0.9), (0.2, 1.1)))
    report = run(scene, state=state)
    assert report["gates"]["connectivity"]["status"] == "unmeasured"
    assert report["gates"]["closed_cavities"]["status"] == "unmeasured"
    assert "finite_solid_touches_array_boundary" in report["gates"]["opening_defect"]["unmeasured_reasons"]
    with pytest.raises(ValueError, match="provenance"):
        policy(minimum_widths_m={"mesh": .5})


def test_every_solid_component_requires_root_owner_when_roots_declared():
    scene = Scene((plate("a"), plate("b", x=4)), ground=-2)
    state = scene.sample(.1, dimension=2)
    root = np.zeros(state.shape, dtype=bool)
    points = scene.grid_points(state)[..., [0, 2]]
    root[scene.components[0].phi(points) < 0] = True
    report = run(scene, state=state, policy=policy(required_components=2, root_masks={"one_mount": root}))
    assert "solid_component_unrooted|2" in report["gates"]["masks_roots"]["fail_reasons"]


def test_ground_is_excluded_from_finite_component_count():
    scene = Scene((plate(z=.4),), ground=0.)
    report = run(scene, policy=policy(clearance_m=0))
    assert report["gates"]["connectivity"]["measured"]["solid_components"] == 1


def test_all_independent_rejections_are_reported():
    scene = Scene((plate(thickness=.2, z=0.),), ground=0.)
    p = policy(envelope={"lower": [-.1, -.1, -.1], "upper": [.1, .1, .1], "rule_source": "synthetic"})
    report = run(scene, policy=p)
    names = {r["gate"] for r in report["rejection_reasons"]}
    assert {"thickness", "clearance", "envelope"} <= names


def test_movable_stl_width_requires_an_external_lower_bound_with_provenance(tmp_path):
    path = tmp_path / "fixed_box.stl"
    payload = trimesh.creation.box(extents=(2, 2, 2)).export(file_type="stl")
    path.write_bytes(payload)
    mesh = MeshBody("fixed_mesh", str(path), hashlib.sha256(payload).hexdigest())
    scene = Scene((plate(x=6, thickness=2, span=2, chord=2), mesh), ground=-5)
    kwargs = dict(h=.5, dimension=3)
    unknown = evaluate_scene_gates(scene, policy=policy(required_components=2), **kwargs)
    assert unknown["gates"]["thickness"]["status"] == "unmeasured"
    known = evaluate_scene_gates(scene, policy=policy(required_components=2,
        minimum_widths_m={"fixed_mesh": 2}, width_source="synthetic exact 2m cube"), **kwargs)
    assert known["gates"]["thickness"]["status"] == "pass"


def test_uncertified_superellipsoid_gap_does_not_pass_from_field_samples():
    a = BoxBody("a", (0, 0, 1), (2, .8, .4))
    b = BoxBody("b", (3, 0, 2), (2, .8, .4))
    report = run(Scene((a, b), ground=-2), policy=policy(required_components=2))
    assert report["gates"]["gap"]["status"] == "unmeasured"
    assert "gap_field_or_surface_coverage_unqualified|a|b" in report["gates"]["gap"]["unmeasured_reasons"]


def test_unqualified_box_field_below_gap_limit_is_not_a_definite_distance_proof():
    a = BoxBody("a", (0, 0, 1), (2, .8, .4))
    b = BoxBody("b", (3, 0, 2), (2, .8, .4))
    report = run(Scene((a, b), ground=-2), policy=policy(required_components=2, minimum_gap_m=1))
    gate = report["gates"]["gap"]
    assert 0 < gate["measured"]["pairs"]["a|b"]["minimum_sampled_field_m"] < 1
    assert gate["status"] == "unmeasured"
    assert gate["fail_reasons"] == []


def test_r3_matches_existing_study_exactly_in_3d():
    script = Path(__file__).resolve().parents[2] / "scripts/width_rule_study.py"
    spec = importlib.util.spec_from_file_location("width_rule_study_scene_test", script)
    module = importlib.util.module_from_spec(spec)
    original_path = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    x, y, z = np.meshgrid(*(np.arange(-6, 7, dtype=float),) * 3, indexing="ij")
    fields = (np.sqrt(x*x+y*y+z*z)-4, np.maximum.reduce((np.abs(x)-4, np.abs(y)-4, np.abs(z)-0.3)))
    for phi in fields:
        existing = module.r3(phi, 1.0)
        gate = opening_defect_gate(phi, 1.0)
        assert gate["status"] == existing["status"]
        assert gate["measured"]["solid_defect_m"] == existing["solid"]
        assert gate["measured"]["void_defect_m"] == existing["void"]


def test_invalid_h_policy_and_mismatched_state_fail_closed():
    with pytest.raises(ValueError):
        evaluate_scene_gates(Scene((plate(),)), h=0, dimension=2, policy=policy())
    with pytest.raises(ValueError):
        run(policy=policy(minimum_gap_m=float("nan")))
    wrong = Scene((plate(x=3),), ground=-2).sample(0.1, dimension=2)
    with pytest.raises(ValueError, match="state"):
        run(state=wrong)
    scene = Scene((plate(),), ground=-2)
    correct = scene.sample(.1, dimension=2)
    forged = SDFDesignState.create(phi=np.ones(correct.shape), origin_m=correct.origin_m,
        spacing_m=.1, narrow_band_width_m=.2, source_sha256=scene.scene_sha256)
    with pytest.raises(ValueError, match="state field"):
        run(scene, state=forged)


def test_state_hash_tampering_and_complex_or_unknown_policy_inputs_fail_closed():
    scene = Scene((plate(),), ground=-2)
    state = scene.sample(.1, dimension=2)
    state.forbidden_mask[0, 0, 0] = True
    with pytest.raises(ValueError, match="state"):
        run(scene, state=state)
    with pytest.raises(ValueError, match="complex"):
        run(phase=(0j, 0, 0))
    with pytest.raises(ValueError, match="complex"):
        run(policy=policy(envelope={"lower": [-20+0j, -20, -20], "upper": [20, 20, 20], "rule_source": "synthetic"}))
    with pytest.raises(ValueError, match="unknown"):
        run(policy=policy(envelope={"lower": [-20, -20, -20], "upper": [20, 20, 20], "rule_source": "synthetic", "lower_typo": 0}))
