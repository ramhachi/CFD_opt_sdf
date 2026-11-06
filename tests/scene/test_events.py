"""Finite event proposals; no response, selection or evaluation budget."""
from dataclasses import replace

import pytest
import numpy as np

from cfd_sdf.scene.events import (
    downstream_seed_positions, seed_candidates, knockout_candidates,
    merge_candidates, thickness_knockout_ids, element_count_designs, classify_change,
)
from cfd_sdf.scene.primitives import PlateElement
from cfd_sdf.scene.scene import Scene, MergedElement


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
    np.testing.assert_allclose(downstream_seed_positions(s,[.2,.3],[.2]),[(0.8,-.2),(.9,-.2)],atol=1e-15)
    with pytest.raises(ValueError):
        downstream_seed_positions(s,[-.1],[.2])


def test_knockout_changes_exact_identity_and_retains_fixed_ground():
    s = parent()
    a = s.components[0]
    s = Scene((a,replace(a,id="flap",x=1.4)),(replace(a,id="fixed",z=1.),),ground=-1.)
    cs = knockout_candidates(s)
    assert len(cs)==2
    assert [classify_change(s,c)["removed_ids"] for c in cs] == [["main"],["flap"]]
    assert all(c.fixed==s.fixed and c.ground==s.ground for c in cs)


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


def test_two_consecutive_checkpoints_at_lower_bound_by_stable_id():
    history = [
        {"checkpoint":1,"thickness":{"main":.2,"flap":.3}},
        {"checkpoint":2,"thickness":{"main":.2,"flap":.2}},
        {"checkpoint":3,"thickness":{"main":.2,"flap":.2}},
    ]
    assert thickness_knockout_ids(history[:2],.2)==("main",)
    assert thickness_knockout_ids(history,.2)==("flap","main")
    assert thickness_knockout_ids(history[:1],.2)==()
    assert thickness_knockout_ids([history[0],history[2]],.2)==()
    with pytest.raises(ValueError):
        thickness_knockout_ids([history[1],history[0]],.2)
    with pytest.raises(ValueError):
        thickness_knockout_ids([{"checkpoint":1,"thickness":{"main":float("nan")}}],.2)


def test_outer_loop_returns_split_warm_starts_with_explicit_count():
    cs = element_count_designs(parent(),4,gap=.2)
    assert [len(c.components) for c in cs]==[1,2,3,4]
    assert len({c.scene_sha256 for c in cs})==4
    assert all(p.thickness==.2 and p.span==.6 for c in cs for p in c.components)
    with pytest.raises(ValueError):
        element_count_designs(parent(),0,gap=.2)


def test_invalid_library_unknown_keys_and_nonfinite_positions_are_rejected():
    with pytest.raises(ValueError):
        seed_candidates(parent(),{"typo":[1]},[(1.,0.)])
    with pytest.raises(ValueError):
        seed_candidates(parent(),{"thickness":[.2],"chord":[.2],"camber":[0.]},[(float("nan"),0.)])


def test_reused_seed_library_after_merge_does_not_collide_with_child_ids():
    library = {"thickness":[.2],"chord":[.4],"camber":[0.]}
    seeded = seed_candidates(parent(),library,[(.8,-.1)])[0]
    assert seed_candidates(seeded,library,[(.8,-.1)]) == []
    merged = merge_candidates(seeded,max_gap=2.)[0]
    reseeded = seed_candidates(merged,library,[(.8,-.1)])
    assert len(reseeded)==1
    assert reseeded[0].components[-1].id != seeded.components[-1].id
    assert classify_change(merged,reseeded[0])["kind"] == "seed"
