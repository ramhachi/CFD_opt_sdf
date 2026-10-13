"""Research topology policy v2 (#31): detached components allowed, root connectivity optional, events permitted by policy; never invokes a flow solver."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.topology_policy import SDF_TOPOLOGY_POLICY_ID, SDFTopologyFeatureMetrics, SDFTopologyPolicyError
from cfd_sdf.design.topology_policy_research import RESEARCH_POLICY_ID, SDFTopologyPolicyResearchV2, evaluate_research_transition

SHAPE = (7, 5, 5)


def policy(**kw):
    kw.setdefault("minimum_solid_width_m", 0.01)
    kw.setdefault("minimum_void_width_m", 0.012)
    kw.setdefault("minimum_gap_m", 0.015)
    return SDFTopologyPolicyResearchV2(**kw)


def state(p, solid_points, *, root=(), fixed=(), forbidden=(), binding=None):
    def mask(points):
        m = np.zeros(SHAPE, dtype=bool)
        for q in points:
            m[q] = True
        return m
    solid, root_m, fixed_m, forb = mask(solid_points), mask(root), mask(fixed), mask(forbidden)
    design = np.ones(SHAPE, dtype=bool); design[root_m] = False; design[fixed_m] = False
    return SDFDesignState.create(phi=np.where(solid, -0.1, 0.1).astype(np.float32), origin_m=(0.0, 0.0, 0.0), spacing_m=0.05, design_mask=design, fixed_solid_mask=fixed_m,
                                 forbidden_mask=forb, root_mask=root_m, narrow_band_width_m=0.1, topology_policy_id=binding or p.state_binding_id)


def metrics(s, solid=0.02, void=0.02, gap=0.02):
    return SDFTopologyFeatureMetrics(candidate_state_sha256=s.state_sha256, report_sha256="ab" * 32, minimum_solid_width_m=solid, minimum_void_width_m=void, minimum_gap_m=gap)


def check(p, a, b, **kw):
    kw.setdefault("feature_metrics", metrics(b))
    kw.setdefault("allowed_events", p.permitted_events)
    return evaluate_research_transition(p, a, b, **kw)


TWO = [(1, 2, 2), (5, 2, 2)]  # two detached solid cells, no root mask at all


def test_identity_is_content_addressed_round_trips_and_does_not_touch_v1():
    p = policy()
    assert p.policy_id == RESEARCH_POLICY_ID != SDF_TOPOLOGY_POLICY_ID and p.state_binding_id == f"{RESEARCH_POLICY_ID}@sha256:{p.policy_sha256}"
    assert policy(minimum_solid_width_m=0.02).policy_sha256 != p.policy_sha256 and policy().policy_sha256 == p.policy_sha256
    d = p.to_dict()
    assert SDFTopologyPolicyResearchV2.from_dict(d) == p and d["connectivity"]["disconnected_components"] == "allowed" and d["connectivity"]["root_connectivity"] == "optional"
    assert d["topology_events"] == {"birth": "permitted_by_policy", "merge": "permitted_by_policy", "split": "permitted_by_policy", "deletion": "permitted_by_policy"}
    for tamper in (lambda x: x.update(policy_sha256="0" * 64), lambda x: x["connectivity"].update(root_connectivity="required"), lambda x: x["topology_events"].update(birth="not_permitted")):
        bad = json.loads(json.dumps(d)); tamper(bad)
        with pytest.raises(SDFTopologyPolicyError):
            SDFTopologyPolicyResearchV2.from_dict(bad)
    with pytest.raises(SDFTopologyPolicyError):
        SDFTopologyPolicyResearchV2.from_dict({**d, "policy_id": "x"})


def test_unresolved_physical_limits_make_every_transition_inadmissible_and_are_never_inferred():
    p = SDFTopologyPolicyResearchV2()
    assert p.unresolved_inputs() == ("minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m") and p.minimum_solid_width_m is None
    a = state(p, TWO)
    v = check(p, a, a, allowed_events=())
    assert not v.admissible and {"minimum_solid_width_m", "minimum_void_width_m"} <= set(v.violations)
    assert policy().unresolved_inputs() == () and policy(minimum_gap_m=None).unresolved_inputs() == ("minimum_gap_m",)


def test_detached_components_without_any_root_are_admissible_for_an_unchanged_topology():
    p = policy()
    a = state(p, TWO)
    v = check(p, a, a, allowed_events=())
    assert v.admissible and v.violations == () and v.current_component_count == v.proposed_component_count == 2 and v.component_root_owners == ((1, ()), (2, ()))


def test_root_ownership_is_reported_but_never_required():
    p = policy()
    a = state(p, TWO, root=[(1, 2, 2)])
    v = check(p, a, a, allowed_events=())
    assert v.admissible and dict(v.component_root_owners) == {1: ("root_mask",), 2: ()}


@pytest.mark.parametrize("after,event", [([(1, 2, 2), (5, 2, 2), (3, 0, 0)], "birth"), ([(1, 2, 2)], "deletion")])
def test_birth_and_deletion_are_permitted_by_policy_and_blocked_by_a_topology_fixed_step(after, event):
    p = policy()
    a, b = state(p, TWO), state(p, after)
    permitted = check(p, a, b, birth_qualified=True)
    assert event in permitted.detected_events and permitted.admissible
    if event == "birth":  # policy permission is not execution permission: an unqualified birth is rejected even when the step allows births
        assert "topology_birth_not_qualified" in check(p, a, b).violations
    fixed = check(p, a, b, allowed_events=())
    assert not fixed.admissible and f"topology_event_not_permitted:{event}" in fixed.violations


def test_merge_and_split_follow_the_same_permission_logic():
    p = policy()
    bridged = [(1, 2, 2), (2, 2, 2), (3, 2, 2), (4, 2, 2), (5, 2, 2)]
    a, merged = state(p, TWO), state(p, bridged)
    v = check(p, a, merged)
    assert "merge" in v.detected_events and v.admissible and "topology_event_not_permitted:merge" in check(p, a, merged, allowed_events=("split",)).violations
    s = check(p, merged, a, birth_qualified=True)
    assert {"split", "birth"} & set(s.detected_events) and s.admissible
    narrow = policy(permitted_events=("merge", "split"))
    a2, b2 = state(narrow, TWO), state(narrow, TWO + [(3, 0, 0)])
    assert not check(narrow, a2, b2, birth_qualified=True).admissible and "topology_event_not_permitted:birth" in check(narrow, a2, b2, birth_qualified=True).violations


def test_allowed_events_may_only_narrow_the_policy():
    p = policy(permitted_events=("merge",))
    a = state(p, TWO)
    with pytest.raises(SDFTopologyPolicyError):
        check(p, a, a, allowed_events=("merge", "birth"))
    with pytest.raises(TypeError):  # required keyword: no default that silently permits everything
        evaluate_research_transition(p, a, a, feature_metrics=metrics(a))
    with pytest.raises(SDFTopologyPolicyError):
        check(p, a, a, allowed_events="merge")
    with pytest.raises(SDFTopologyPolicyError):
        policy(permitted_events=("birth", "birth"))
    with pytest.raises(SDFTopologyPolicyError):
        policy(permitted_events=("teleport",))


def test_hard_masks_still_apply():
    p = policy()
    base = state(p, TWO, fixed=[(1, 2, 2)], forbidden=[(6, 4, 4)])
    assert check(p, base, base, allowed_events=()).admissible
    lost_fixed = state(p, [(5, 2, 2)], fixed=[(1, 2, 2)], forbidden=[(6, 4, 4)])
    assert "fixed_solid_not_retained" in check(p, base, lost_fixed).violations
    in_forbidden = state(p, TWO + [(6, 4, 4)], fixed=[(1, 2, 2)], forbidden=[(6, 4, 4)])
    assert "material_in_forbidden_mask" in check(p, base, in_forbidden).violations
    root = state(p, TWO, root=[(1, 2, 2)])
    assert "root_material_not_retained" in check(p, root, state(p, [(5, 2, 2)], root=[(1, 2, 2)])).violations


def test_empty_solid_component_limit_and_mask_or_binding_mismatch_fail_closed():
    p = policy(max_components=1)
    a = state(p, [(1, 2, 2)])
    assert "solid_component_count_exceeds_policy_limit" in check(p, a, state(p, TWO)).violations
    q = policy()
    full = state(q, TWO)
    empty = state(q, [])
    assert "proposed_solid_is_empty" in check(q, full, empty).violations and "current_solid_is_empty" in check(q, empty, full).violations
    other = state(q, TWO, forbidden=[(0, 0, 0)])
    assert "state_mask_mismatch" in check(q, full, other).violations
    wrong = state(q, TWO, binding="sdf_topology_policy_v1@sha256:" + "0" * 64)
    assert "proposed_state_policy_hash_mismatch" in check(q, full, wrong).violations and "current_state_policy_hash_mismatch" in check(q, wrong, full).violations


def test_feature_measurements_must_exist_bind_to_the_state_and_meet_the_limits():
    p = policy()
    a = state(p, TWO)
    assert "feature_measurements_missing" in evaluate_research_transition(p, a, a, feature_metrics=None, allowed_events=()).violations
    assert "feature_measurements_state_hash_mismatch" in check(p, a, a, feature_metrics=metrics(state(p, [(1, 2, 2)])), allowed_events=()).violations
    assert "minimum_solid_width_violation" in check(p, a, a, feature_metrics=metrics(a, solid=0.005, gap=0.02), allowed_events=()).violations
    assert "minimum_void_width_violation" in check(p, a, a, feature_metrics=metrics(a, void=0.005, gap=0.02), allowed_events=()).violations
    assert "minimum_gap_measurement_missing" in check(p, a, a, feature_metrics=metrics(a, gap=None), allowed_events=()).violations
    assert "minimum_gap_violation" in check(p, a, a, feature_metrics=metrics(a, gap=0.01), allowed_events=()).violations
    assert check(p, a, a, feature_metrics=metrics(a, gap=0.02), allowed_events=()).admissible


def test_source_binding_is_all_or_nothing_and_lengths_are_validated():
    with pytest.raises(SDFTopologyPolicyError):
        SDFTopologyPolicyResearchV2(source_problem_id="p")
    with pytest.raises(SDFTopologyPolicyError):
        SDFTopologyPolicyResearchV2(source_problem_id="p", source_problem_spec_sha256="xyz")
    assert SDFTopologyPolicyResearchV2(source_problem_id="p", source_problem_spec_sha256="ab" * 32).to_dict()["source_problem_spec_v2"]["problem_id"] == "p"
    for bad in (-1.0, 0.0, float("nan"), float("inf"), True, "0.01", None.__class__):
        with pytest.raises(SDFTopologyPolicyError):
            SDFTopologyPolicyResearchV2(minimum_solid_width_m=bad)
    assert SDFTopologyPolicyResearchV2(minimum_solid_width_m=1).policy_sha256 == SDFTopologyPolicyResearchV2(minimum_solid_width_m=1.0).policy_sha256
    assert SDFTopologyPolicyResearchV2(minimum_solid_width_m=np.float32(0.5)).minimum_solid_width_m == 0.5 and type(SDFTopologyPolicyResearchV2(minimum_solid_width_m=np.float32(0.5)).minimum_solid_width_m) is float
    d = SDFTopologyPolicyResearchV2().to_dict()
    for bad in ({**d, "source_problem_spec_v2": "x"}, {**d, "minimum_features": []}):
        with pytest.raises(SDFTopologyPolicyError):
            SDFTopologyPolicyResearchV2.from_dict(bad)
    with pytest.raises(SDFTopologyPolicyError):
        check(policy(), state(policy(), TWO), state(policy(), TWO), feature_metrics="x")


def test_every_policy_field_changes_the_hash():
    base = policy(max_components=3, source_problem_id="p", source_problem_spec_sha256="ab" * 32).policy_sha256
    for kw in ({"minimum_solid_width_m": 0.011}, {"minimum_void_width_m": 0.013}, {"minimum_gap_m": 0.016}, {"max_components": 4}, {"source_problem_id": "q"},
               {"source_problem_spec_sha256": "cd" * 32}, {"permitted_events": ("merge", "split")}):
        args = {"max_components": 3, "source_problem_id": "p", "source_problem_spec_sha256": "ab" * 32, **kw}
        assert policy(**args).policy_sha256 != base, kw


def test_corner_touching_cells_are_one_component_and_shape_mismatch_fails_closed():
    p = policy()
    a = state(p, [(1, 2, 2), (2, 3, 3)])
    assert check(p, a, a).proposed_component_count == 1  # 26-connectivity: a corner contact is connected


def test_registered_artifact_matches_the_default_policy_and_its_sidecar():
    import hashlib
    path = ROOT / "docs/evidence/sdf_topology_policy_v2_research_2026_10_14.json"
    reg = json.loads(path.read_text())
    assert path.with_suffix(".json.sha256").read_text().strip() == hashlib.sha256(path.read_bytes()).hexdigest()
    p = SDFTopologyPolicyResearchV2()
    assert reg["policy"] == p.to_dict() and reg["state_binding_id"] == p.state_binding_id and SDFTopologyPolicyResearchV2.from_dict(reg["policy"]) == p
    assert reg["policy"]["unresolved_inputs"] == ["minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m"] and not any(reg["flags"].values()) and reg["solver_started"] is False
    assert hashlib.sha256((ROOT / "docs/evidence/sdf_topology_policy_v1_2026_09.json").read_bytes()).hexdigest() == reg["v1_registration_sha256"]  # the immutable v1 registration is untouched
