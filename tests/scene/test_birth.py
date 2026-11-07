"""#32 Birth-0, and Birth-1 **software preparation**, without primal runs.

Component counts use 8/26-neighbour node occupancy phi<0, consistent with the
repository topology convention. Area/volume is a separate sampling diagnostic.
"""
from dataclasses import replace

import numpy as np
import pytest
from scipy import ndimage

from cfd_gen.scene.events import seed_candidates, knockout_candidates, merge_candidates, classify_change
from cfd_gen.scene.gates import SceneGatePolicy, evaluate_scene_gates
from cfd_gen.scene.primitives import PlateElement
from cfd_gen.scene.scene import Scene


def count(scene,dimension=2):
    state = scene.sample(.025,dimension=dimension,bounds=((-1.,-1.),(3.,1.)) if dimension==2 else ((-1.,-.6,-1.),(3.,.6,1.)))
    return ndimage.label(state.solid_mask,np.ones((3,3,3)))[1]


@pytest.mark.parametrize("dimension",[2,3])
def test_birth0_exactly_intended_primitive_position_measure_and_component(dimension):
    main = PlateElement("main",0.,0.,1.,.2,span=.6)
    parent = Scene((main,))
    proposed = seed_candidates(parent,{"chord":[.4],"thickness":[.15],"camber":[0.]},[(1.55,-.25)])[0]
    bounds = ((-1.,-1.),(3.,1.)) if dimension==2 else ((-.7,-.35,-.45),(2.,.35,.2))
    h = .0125
    a = parent.sample(h,dimension=dimension,bounds=bounds,phase=(.5,0. if dimension==2 else .5,.5))
    b = proposed.sample(h,dimension=dimension,bounds=bounds,phase=(.5,0. if dimension==2 else .5,.5))
    points = Scene.grid_points(b)
    q = points[..., [0,2]] if dimension==2 else points
    new_solid = b.solid_mask & ~a.solid_mask
    seed = proposed.components[-1]
    np.testing.assert_array_equal(new_solid,seed.phi(q)<0)
    assert ndimage.label(new_solid,np.ones((3,3,3)))[1]==1
    assert ndimage.label(b.solid_mask,np.ones((3,3,3)))[1]-ndimage.label(a.solid_mask,np.ones((3,3,3)))[1]==1
    center = q[new_solid].mean(axis=0)
    np.testing.assert_allclose(center,(1.55,-.25) if dimension==2 else (1.55,0.,-.25),atol=h)
    exact = (.4*.15+np.pi*.15**2/4)*(.6 if dimension==3 else 1.)
    assert new_solid.sum()*h**dimension == pytest.approx(exact,rel=.025)
    assert proposed.components[0] is main
    assert classify_change(parent,proposed)["cfd_evaluations"]==0


def test_birth0_invalid_thin_and_forbidden_seed_are_rejected_before_cfd():
    parent = Scene((PlateElement("main",0.,0.,1.,.2),),ground=-1.)
    proposed = seed_candidates(parent,{"chord":[.4],"thickness":[.05],"camber":[0.]},[(1.5,-.25)])[0]
    p = SceneGatePolicy(required_components=2,clearance_m=.1,
        envelope={"lower":[-1.,-1.],"upper":[3.,1.],"rule_source":"synthetic Birth-0 envelope (not FSAE dimensions)"})
    result = evaluate_scene_gates(proposed,h=.025,dimension=2,policy=p)
    assert not result["passed"]
    assert result["gates"]["thickness"]["status"]=="fail"
    state = proposed.sample(.025,dimension=2)
    points = Scene.grid_points(state)[..., [0,2]]
    forbidden = proposed.components[-1].phi(points)<0
    result = evaluate_scene_gates(proposed,h=.025,dimension=2,state=state,
        policy=replace(p,forbidden_mask=forbidden,require_forbidden_mask=True))
    assert not result["passed"]
    assert result["cfd_evaluations"]==0 and result["budget_charged"]==0


@pytest.mark.parametrize("dimension", [2, 3])
def test_birth0_valid_seed_obeys_policy_before_any_cfd(dimension):
    parent = Scene((PlateElement("main", 0, 0, 1, .2, span=.6),), ground=-1)
    proposed = seed_candidates(parent, {"chord": [.4], "thickness": [.15], "camber": [0.]}, [(1.55, -.25)])[0]
    h = .0375
    state = proposed.sample(h, dimension=dimension)
    points = Scene.grid_points(state)
    if dimension == 2:
        points = points[..., [0, 2]]
    roots = {p.id: p.phi(points) < 0 for p in proposed.components}
    # Deliberately require the same policy classes as the invalid Birth-0
    # controls: roots, forbidden material, clearance and minimum features.
    p = SceneGatePolicy(required_components=2, clearance_m=.1, root_masks=roots,
        forbidden_mask=np.zeros(state.shape, dtype=bool), require_forbidden_mask=True,
        envelope={"lower": [-1, -1, -.8], "upper": [3, 1, 1],
                  "rule_source": "synthetic Birth-0 rules box; not physical FSAE qualification"})
    report = evaluate_scene_gates(proposed, h=h, dimension=dimension, policy=p, state=state)
    assert report["passed"], report["rejection_reasons"]
    assert report["gates"]["connectivity"]["measured"]["solid_components"] == 2
    assert report["cfd_evaluations"] == report["budget_charged"] == 0


def test_birth1_software_preparation_classifies_counts_and_deleted_identity():
    a = PlateElement("main",0.,0.,1.,.2,span=.6)
    parent = Scene((a,))
    seeded = seed_candidates(parent,{"chord":[.4],"thickness":[.2],"camber":[0.]},[(1.55,-.25)])[0]
    assert classify_change(parent,seeded)["kind"]=="seed"
    assert count(seeded)-count(parent)==1
    knocked = knockout_candidates(seeded)[1]
    report = classify_change(seeded,knocked)
    assert report["kind"]=="knockout"
    assert report["removed_ids"]==[seeded.components[1].id]
    assert count(knocked)-count(seeded)==-1
    assert knocked.components[0] is a
    close = Scene((a,replace(a,id="flap",x=1.4)))
    merged = merge_candidates(close,max_gap=.25)[0]
    report = classify_change(close,merged)
    assert report["kind"]=="merge" and report["removed_ids"]==["flap","main"]
    assert count(merged)-count(close)==-1
    assert report["evidence_class"]=="Birth-1 software preparation"
