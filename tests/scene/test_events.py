"""Finite event proposals; no response, selection or evaluation budget."""
from dataclasses import replace

import pytest
import numpy as np

from cfd_gen.scene.events import (
    downstream_seed_positions, seed_candidates, knockout_candidates,
    merge_candidates, thickness_knockout_ids, element_count_designs, classify_change,
)
from cfd_gen.scene import events
from cfd_gen.scene.gates import SceneGatePolicy, evaluate_scene_gates
from cfd_gen.scene.primitives import BoxBody, EndplatePlate, PlateElement
from cfd_gen.scene.scene import Scene, MergedElement


def parent():
    return Scene((PlateElement("main",0.,0.,1.,.2,span=.6),))


def test_seed_product_and_no_duplicate_or_parent_mutation():
    s = parent()
    positions = [(1.5,-.3),(1.5,-.3),(2.,-.4)]
    library = {"thickness":[.2,.2,.3],"chord":[.4,.5],"camber":[0.,.01]}
    candidates = seed_candidates(s,library,positions)
    assert len(candidates)==16
    assert len({c.scene_sha256 for c in candidates})==16
    assert all(len(c.components)==2 and c.components[0]==s.components[0] for c in candidates)
    assert all(c.components[-1].span==.6 for c in candidates)
    assert len(s.components)==1
    for c in candidates:
        report = classify_change(s,c)
        assert report["kind"]=="seed" and len(report["added_ids"])==1


def test_downstream_grid_uses_trailing_edge_not_center():
    s = parent()
    np.testing.assert_allclose(downstream_seed_positions(s,[.2,.3],[-.2,.2]),
        [(0.8,-.2),(.8,.2),(.9,-.2),(.9,.2)],atol=1e-15)
    np.testing.assert_allclose(downstream_seed_positions(s,[.2],[-.2,.2],allowed_quadrants=("above",)),[(.8,.2)])
    np.testing.assert_allclose(downstream_seed_positions(s,[.2],[-.2,.2],allowed_quadrants=("below",)),[(.8,-.2)])
    with pytest.raises(ValueError):
        downstream_seed_positions(s,[-.1],[.2])


@pytest.mark.parametrize("offset",[0.,float("nan"),float("inf"),True,1j])
def test_downstream_grid_rejects_invalid_signed_or_downstream_offsets(offset):
    with pytest.raises(ValueError):
        downstream_seed_positions(parent(),[.2],[offset])
    with pytest.raises(ValueError):
        downstream_seed_positions(parent(),[offset],[.2])


@pytest.mark.parametrize("quadrants",[(),("left",),("above","left"),"above",None])
def test_downstream_grid_rejects_invalid_quadrant_policy(quadrants):
    with pytest.raises(ValueError):
        downstream_seed_positions(parent(),[.2],[.2],allowed_quadrants=quadrants)


def test_knockout_changes_exact_identity_and_retains_fixed_ground():
    s = parent()
    a = s.components[0]
    s = Scene((a,replace(a,id="flap",x=1.4)),(replace(a,id="fixed",z=1.),),ground=-1.)
    cs = knockout_candidates(s)
    assert len(cs)==2
    assert [classify_change(s,c)["removed_ids"] for c in cs] == [["main"],["flap"]]
    assert all(c.fixed==s.fixed and c.ground==s.ground for c in cs)


def test_knockout_removes_only_wing_elements_and_retains_other_components():
    main = parent().components[0]
    endplate = EndplatePlate("endplate",0.,.3,0.,.5,1.2,.1)
    pod = BoxBody("pod",(4.,0.,0.),(.5,.5,.5))
    merged = MergedElement("merge:a:b",(replace(main,id="a",x=3.),replace(main,id="b",x=3.2)))
    s = Scene((main,endplate,pod,merged),ground=-1.)
    cs = knockout_candidates(s)
    assert [classify_change(s,c)["removed_ids"] for c in cs] == [["main"],["merge:a:b"]]
    assert all(endplate in c.components and pod in c.components and c.ground==s.ground for c in cs)


def test_merge_is_explicit_aggregate_and_only_near_pairs():
    a = parent().components[0]
    s = Scene((a,replace(a,id="flap",x=1.25),replace(a,id="far",x=5.)))
    cs = merge_candidates(s,max_gap=.1)
    assert len(cs)==1
    c = cs[0]
    assert len(c.components)==2
    merged = [p for p in c.components if isinstance(p,MergedElement)][0]
    assert {p.id for p in merged.parts}=={"main","flap"}
    assert classify_change(s,c)["kind"]=="merge"
    assert classify_change(s,c)["element_count_delta"]==-1


def test_merge_translates_by_gap_plus_declared_overlap_and_keeps_first_plate():
    a = parent().components[0]
    b = replace(a,id="flap",x=1.3,chord=.6)
    original_gap = b.x-a.x-(a.chord+b.chord+a.thickness+b.thickness)/2
    merged = merge_candidates(Scene((a,b)),max_gap=.5,overlap=.03)[0].components[0]
    assert merged.parts[0] is a
    assert merged.parts[1].id==b.id
    np.testing.assert_allclose([merged.parts[1].x,merged.parts[1].y,merged.parts[1].z],
        [b.x-original_gap-.03,b.y,b.z],atol=1e-8)
    # The flap stays at the trailing edge, with a small explicit overlap.
    assert merged.parts[1].x>a.x+.5*a.chord


def test_merge_default_overlap_is_half_the_smaller_plate_thickness():
    a = parent().components[0]
    b = replace(a,id="flap",x=1.3,chord=.6,thickness=.12)
    gap = b.x-a.x-(a.chord+b.chord+a.thickness+b.thickness)/2
    moved = merge_candidates(Scene((a,b)),max_gap=.5)[0].components[0].parts[1]
    np.testing.assert_allclose([moved.x,moved.y,moved.z],
        [b.x-gap-min(a.thickness,b.thickness)/2,b.y,b.z],atol=1e-8)


def test_merge_skips_only_nonconverged_pair_and_records_deterministic_reason(monkeypatch):
    a = parent().components[0]
    b,c = replace(a,id="flap",x=1.3),replace(a,id="other",x=-1.3)
    original = events._nearest_boundary_pair
    def nearest(first,second):
        if (first.id,second.id)==("main","flap"):
            raise events.NearestBoundaryConvergenceError("nearest-boundary refinement did not converge")
        return original(first,second)
    monkeypatch.setattr(events,"_nearest_boundary_pair",nearest)
    diagnostics = []
    source = Scene((a,b,c))
    proposals = merge_candidates(source,max_gap=.2,diagnostics=diagnostics)
    assert len(proposals)==1
    assert proposals[0].components[0].id=="merge:main:other"
    assert proposals[0].components[1] is b
    assert diagnostics==[{"pair_ids":["main","flap"],
        "reason":"nearest_boundary_refinement_did_not_converge"}]


def test_merge_logs_pair_reason_when_no_diagnostics_list_is_supplied(monkeypatch,caplog):
    def no_convergence(first,second):
        raise events.NearestBoundaryConvergenceError("nearest-boundary refinement did not converge")
    monkeypatch.setattr(events,"_nearest_boundary_pair",no_convergence)
    a = parent().components[0]
    with caplog.at_level("WARNING",logger=events.__name__):
        assert merge_candidates(Scene((a,replace(a,id="flap",x=1.3))),max_gap=.2)==[]
    assert len(caplog.records)==1
    assert "main" in caplog.text and "flap" in caplog.text
    assert "nearest_boundary_refinement_did_not_converge" in caplog.text


def test_nearest_boundary_failure_uses_specific_convergence_exception(monkeypatch):
    from types import SimpleNamespace
    def no_convergence(fun,initial,**kwargs):
        return SimpleNamespace(success=False,x=initial)
    monkeypatch.setattr(events,"minimize",no_convergence)
    a = parent().components[0]
    with pytest.raises(events.NearestBoundaryConvergenceError):
        events._nearest_boundary_pair(a,replace(a,id="flap",x=1.3))


def test_merge_does_not_swallow_unrelated_errors(monkeypatch):
    def invalid(first,second):
        raise ValueError("invalid boundary geometry")
    monkeypatch.setattr(events,"_nearest_boundary_pair",invalid)
    a = parent().components[0]
    diagnostics = []
    with pytest.raises(ValueError,match="invalid boundary geometry"):
        merge_candidates(Scene((a,replace(a,id="flap",x=1.3))),max_gap=.2,diagnostics=diagnostics)
    assert diagnostics==[]


@pytest.mark.parametrize("diagnostics",[{},(),False,"log"])
def test_merge_rejects_invalid_diagnostics_container(diagnostics):
    with pytest.raises(ValueError,match="diagnostics"):
        merge_candidates(parent(),diagnostics=diagnostics)


def test_merge_uses_exact_extrusion_gap_when_sections_overlap():
    a = replace(parent().components[0],y=-.5)
    b = replace(a,id="flap",y=.3,chord=.6)
    merged = merge_candidates(Scene((a,b)),max_gap=.3,overlap=.03)[0].components[0]
    # Span intervals [-.8,-.2] and [0,.6] are .2 m apart; x-z already overlap.
    moved = merged.parts[1]
    np.testing.assert_allclose([moved.x-b.x,moved.y-b.y,moved.z-b.z],[0.,-.23,0.],atol=1e-8)
    assert merged.parts[0] is a


def test_existing_plate_contact_or_overlap_is_not_a_new_merge_proposal():
    a = parent().components[0]
    for x in (.5,1.2):
        assert merge_candidates(Scene((a,replace(a,id="flap",x=x))),max_gap=.3)==[]


@pytest.mark.parametrize("dimension",[2,3])
def test_nonidentical_above_downstream_merge_passes_development_scene_gates(dimension):
    h = .025
    main = PlateElement("main",0.,0.,1.2,4*h,span=.6)
    flap = PlateElement("flap",.65,.26,.4,5*h,angle=.12,span=.6)
    source = Scene((main,flap),ground=-1.)
    proposal = merge_candidates(source,max_gap=.2,overlap=.04)[0]
    moved = proposal.components[0].parts[1]
    assert proposal.components[0].parts[0] is main
    assert moved.id==flap.id and moved.x>main.x+.3
    assert 0<np.linalg.norm([moved.x-flap.x,moved.z-flap.z])<.25
    policy = SceneGatePolicy(required_components=1,clearance_m=.1,
        envelope={"lower":[-2.,-1.,-.8],"upper":[2.,1.,.8],"rule_source":"synthetic merge regression; no FSAE qualification"})
    source_result = evaluate_scene_gates(source,h=h,dimension=dimension,policy=replace(policy,required_components=2))
    assert source_result["passed"],source_result["rejection_reasons"]
    assert source_result["gates"]["connectivity"]["measured"]["solid_components"]==2
    result = evaluate_scene_gates(proposal,h=h,dimension=dimension,policy=policy)
    assert result["passed"],result["rejection_reasons"]
    assert result["gates"]["connectivity"]["measured"]["solid_components"]==1
    assert result["distance_contract_exemptions"]==[proposal.components[0].id]
    assert result["cfd_evaluations"]==result["budget_charged"]==0
    change = classify_change(source,proposal)
    assert change["kind"]=="merge" and change["removed_ids"]==["flap","main"]
    assert change["evidence_class"]=="Birth-1 software preparation"


@pytest.mark.parametrize("dimension",[2,3])
def test_default_oblique_merge_passes_all_16_declared_phases(dimension):
    from cfd_gen.scene.gates import evaluate_scene_gates_phases
    h = .025
    main = PlateElement("main",0.,0.,1.2,6*h,span=.15)
    flap = PlateElement("flap",.65,.26,.4,7*h,angle=.35,span=.15)
    source = Scene((main,flap),ground=-1.)
    proposal = merge_candidates(source,max_gap=.25)[0]
    moved = proposal.components[0].parts[1]
    assert moved.id==flap.id and moved.x>main.x+.3
    policy = SceneGatePolicy(required_components=1,clearance_m=.1,
        envelope={"lower":[-2.,-1.,-.8],"upper":[2.,1.,.8],
            "rule_source":"synthetic 0.35-rad merge regression; no FSAE qualification"})
    phases = [(i/4,0. if dimension==2 else ((i+j)%4)/4,j/4)
        for i in range(4) for j in range(4)]
    result = evaluate_scene_gates_phases(proposal,h=h,dimension=dimension,policy=policy,phases=phases)
    assert result["passed"],result["rejection_reasons"]
    assert result["phase_count"]==16
    assert all(row["result"]["passed"] for row in result["phase_reports"])
    assert result["budget_charged"]==result["cfd_evaluations"]==0
    assert classify_change(source,proposal)["kind"]=="merge"


@pytest.mark.parametrize("kwargs",[{"max_gap":-1},{"max_gap":float("nan")},
    {"overlap":0},{"overlap":-1},{"overlap":float("inf")}])
def test_merge_rejects_invalid_gap_or_overlap(kwargs):
    with pytest.raises(ValueError):
        merge_candidates(parent(),**kwargs)


def test_two_consecutive_checkpoints_at_lower_bound_by_stable_id():
    history = [
        {"checkpoint":1,"thickness":{"main":.2,"flap":.3}},
        {"checkpoint":2,"thickness":{"main":.2,"flap":.2}},
        {"checkpoint":3,"thickness":{"main":.2,"flap":.2}},
    ]
    floors = {"main":.2,"flap":.2}
    assert thickness_knockout_ids(history[:2],floors)==("main",)
    assert thickness_knockout_ids(history,floors)==("flap","main")
    assert thickness_knockout_ids(history[:1],floors)==()
    assert thickness_knockout_ids([history[0],history[2]],floors)==()
    with pytest.raises(ValueError):
        thickness_knockout_ids([history[1],history[0]],floors)
    with pytest.raises(ValueError):
        thickness_knockout_ids([{"checkpoint":1,"thickness":{"main":float("nan")}}],floors)


def test_per_id_parameter_floor_history_retains_consecutive_id_semantics():
    floors = {"main:cambered":.22,"flap":.2}
    history = [
        {"checkpoint":1,"thickness":{"main:cambered":.22}},
        {"checkpoint":2,"thickness":{"main:cambered":.22,"flap":.2}},
        {"checkpoint":3,"thickness":{"main:cambered":.22,"flap":.2}},
    ]
    assert thickness_knockout_ids(history[:2],floors)==("main:cambered",)
    assert thickness_knockout_ids(history,floors)==("flap","main:cambered")
    with pytest.raises(ValueError,match="known"):
        thickness_knockout_ids([{"checkpoint":1,"thickness":{"unknown":.2}}],floors)
    with pytest.raises(ValueError,match="lower bound"):
        thickness_knockout_ids([{"checkpoint":1,"thickness":{"main:cambered":.2}}],floors)


def test_floor_snapshots_follow_same_id_when_its_shape_changes():
    history = [
        {"checkpoint":1,"thickness":{"main":.1},"parameter_floors":{"main":.1}},
        {"checkpoint":2,"thickness":{"main":.12},"parameter_floors":{"main":.12}},
    ]
    assert thickness_knockout_ids(history)==("main",)
    # Explicit row snapshots take precedence over a frozen per-ID fallback.
    assert thickness_knockout_ids(history,{"main":.2})==("main",)


def test_floor_snapshots_validate_old_parent_ids_after_a_split_or_removal():
    history = [
        {"checkpoint":1,"thickness":{"parent":.1},"parameter_floors":{"parent":.1}},
        {"checkpoint":2,"thickness":{"child:0":.11},"parameter_floors":{"child:0":.11}},
        {"checkpoint":3,"thickness":{"child:0":.11},"parameter_floors":{"child:0":.11}},
    ]
    assert thickness_knockout_ids(history[:2])==()
    assert thickness_knockout_ids(history)==("child:0",)
    assert thickness_knockout_ids(history,{"child:0":.11})==("child:0",)


@pytest.mark.parametrize("snapshot",[None,{}, {"other":.1}, {"main":.1,"extra":.2},
    {"main":0}, {"main":float("nan")}, {"bad|id":.1}, {"main":.2}])
def test_floor_snapshots_reject_missing_mismatched_or_invalid_limits(snapshot):
    history = [{"checkpoint":1,"thickness":{"main":.1},"parameter_floors":snapshot}]
    with pytest.raises(ValueError):
        thickness_knockout_ids(history)


def test_missing_snapshot_requires_explicit_frozen_floor_for_that_row():
    history = [
        {"checkpoint":1,"thickness":{"main":.1}},
        {"checkpoint":2,"thickness":{"main":.1},"parameter_floors":{"main":.1}},
    ]
    with pytest.raises(ValueError,match="floor"):
        thickness_knockout_ids(history)
    assert thickness_knockout_ids(history,{"main":.1})==("main",)


@pytest.mark.parametrize("scalar",[.1,0.,-1.,True,float("nan"),float("inf")])
@pytest.mark.parametrize("snapshots",[False,True])
def test_scalar_thickness_floor_is_rejected_even_with_complete_snapshots(scalar,snapshots):
    history = [{"checkpoint":n,"thickness":{"main":.1}} for n in (1,2)]
    if snapshots:
        for row in history:
            row["parameter_floors"] = {"main":.1}
    with pytest.raises(ValueError,match="per-ID|mapping"):
        thickness_knockout_ids(history,scalar)


@pytest.mark.parametrize("floors",[{}, {"bad|id":.2}, {"main":0}, {"main":float("nan")}])
def test_parameter_floors_reject_invalid_ids_or_limits(floors):
    with pytest.raises(ValueError):
        thickness_knockout_ids([],floors)


@pytest.mark.parametrize("id",["bad|id","bad id", "ü"])
def test_thickness_history_uses_shared_ascii_id_contract(id):
    with pytest.raises(ValueError):
        thickness_knockout_ids([{"checkpoint":1,"thickness":{id:.2}}],{"main":.2})


def test_outer_loop_returns_split_warm_starts_with_explicit_count():
    h = .025
    s = Scene((PlateElement("main",0.,0.,2.4,4*h,span=.6),),ground=-1.)
    cs = element_count_designs(s,5,gap=4*h)
    assert [len(c.components) for c in cs]==[1,2,3,4,5]
    assert len({c.scene_sha256 for c in cs})==5
    assert cs[0] is s
    for n,c in enumerate(cs,1):
        assert len({p.id for p in c.components})==n
        assert all(p.thickness==4*h and p.span==.6 for p in c.components)
        np.testing.assert_allclose(c.bbox(2),s.bbox(2),atol=1e-14)
        result = evaluate_scene_gates(c,h=h,dimension=2,policy=SceneGatePolicy(required_components=n,clearance_m=.1,
            envelope={"lower":[-2.,-.8],"upper":[2.,.8],"rule_source":"synthetic resolved split regression; no FSAE qualification"}))
        assert result["passed"],(n,result["rejection_reasons"])
        assert result["cfd_evaluations"]==result["budget_charged"]==0
    with pytest.raises(ValueError):
        element_count_designs(parent(),0,gap=.2)


def test_split_preserves_axial_footprint_and_relative_deformation_amplitudes():
    p = PlateElement("main",.2,.1,2.4,.1,angle=.3,camber=.04,reflex=-.02,span=.6,y=.2)
    designs = element_count_designs(Scene((p,)),5,gap=.1)
    axis = np.array([np.cos(p.angle),np.sin(p.angle)])
    for scene in designs:
        boundary = np.concatenate([child.boundary_points(.02,2) for child in scene.components])@axis
        center = np.array([p.x,p.z])@axis
        np.testing.assert_allclose([boundary.min(),boundary.max()],center+np.array([-1,1])*(p.chord+p.thickness)/2,atol=1e-14)
        for child in scene.components:
            assert child.camber/child.chord==pytest.approx(p.camber/p.chord)
            assert child.reflex/child.chord==pytest.approx(p.reflex/p.chord)
            assert (child.angle,child.y,child.span)==(p.angle,p.y,p.span)


@pytest.mark.parametrize("dimension",[2,3])
@pytest.mark.parametrize("angle_degrees",[0.,-10.,-20.])
def test_default_split_gap_admits_angled_cambered_n1_to_n5(dimension,angle_degrees):
    from cfd_gen.scene.gates import _gap_sampling_guard
    h = .025
    p = PlateElement("main",0.,0.,2.4,4.1*h,angle=np.deg2rad(angle_degrees),
        camber=.03,span=4*h)
    source = Scene((p,),ground=-1.)
    policy = SceneGatePolicy(clearance_m=.1,
        envelope={"lower":[-2.,-.3,-.8],"upper":[2.,.3,.8],
            "rule_source":"synthetic angled cambered split regression; no FSAE qualification"})
    designs = element_count_designs(source,5,h=h,dimension=dimension,policy=policy)
    assert [len(s.components) for s in designs]==[1,2,3,4,5]
    assert len({s.scene_sha256 for s in designs})==5
    child_a,child_b = designs[1].components
    expected_gap = 4*h+_gap_sampling_guard(h,dimension,child_a,child_b)
    assert p.chord-2*child_a.chord-p.thickness==pytest.approx(expected_gap)
    axis = np.array([np.cos(p.angle),np.sin(p.angle)])
    expected = np.array([-1,1])*(p.chord+p.thickness)/2
    for n,design in enumerate(designs,1):
        # This cap spacing includes theta=0, the exact axial extremum.
        boundary = np.concatenate([child.boundary_points(p.thickness/10,2) for child in design.components])@axis
        np.testing.assert_allclose([boundary.min(),boundary.max()],expected,atol=1e-13)
        assert all(child.camber/child.chord==pytest.approx(p.camber/p.chord) for child in design.components)
        result = evaluate_scene_gates(design,h=h,dimension=dimension,policy=replace(policy,required_components=n))
        assert result["passed"],(n,angle_degrees,dimension,result["rejection_reasons"])
        assert result["cfd_evaluations"]==result["budget_charged"]==0


def test_default_split_gap_uses_supplied_policy_minimum():
    from cfd_gen.scene.gates import _gap_sampling_guard
    h = .025
    policy = SceneGatePolicy(minimum_gap_m=.15)
    p = parent().components[0]
    children = element_count_designs(Scene((p,)),2,h=h,dimension=2,policy=policy)[1].components
    assert p.chord-2*children[0].chord-p.thickness==pytest.approx(.15+_gap_sampling_guard(h,2,*children))


@pytest.mark.parametrize("kwargs",[{}, {"h":0}, {"h":-1}, {"h":float("nan")},
    {"h":True}, {"h":.02,"dimension":4}, {"h":.02,"dimension":True},
    {"h":.02,"policy":{}}])
def test_default_split_gap_rejects_missing_or_invalid_grid_policy(kwargs):
    with pytest.raises(ValueError):
        element_count_designs(parent(),2,**kwargs)


@pytest.mark.parametrize("chord",[.3,.4])
def test_split_rejects_nonpositive_child_straight_chord(chord):
    s = Scene((replace(parent().components[0],chord=chord),))
    with pytest.raises(ValueError,match="positive.*chord"):
        element_count_designs(s,2,gap=.2)


def test_invalid_library_unknown_keys_and_nonfinite_positions_are_rejected():
    with pytest.raises(ValueError):
        seed_candidates(parent(),{"typo":[1]},[(1.,0.)])
    with pytest.raises(ValueError):
        seed_candidates(parent(),{"thickness":[.2],"chord":[.2],"camber":[0.]},[(float("nan"),0.)])


def test_reused_seed_library_after_merge_does_not_collide_with_child_ids():
    library = {"thickness":[.2],"chord":[.4],"camber":[0.]}
    seeded = seed_candidates(parent(),library,[(1.,-.1)])[0]
    assert seed_candidates(seeded,library,[(1.,-.1)]) == []
    merged = merge_candidates(seeded,max_gap=2.)[0]
    reseeded = seed_candidates(merged,library,[(1.,-.1)])
    assert len(reseeded)==1
    assert reseeded[0].components[-1].id != seeded.components[-1].id
    assert classify_change(merged,reseeded[0])["kind"] == "seed"
