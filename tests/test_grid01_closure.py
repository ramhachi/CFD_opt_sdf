"""GRID-01 closure synthesis: the pinned inputs, the frozen decision rule, and the retained disagreement it rests on."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import synthesize_grid01_closure as G  # noqa: E402


def test_synthesis_is_rederived_from_the_pinned_inputs():
    data = (json.dumps(G.build(), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    assert data == G.OUT.read_bytes()


def test_the_decision_and_the_retained_disagreement():
    s = json.loads(G.OUT.read_text())
    assert s["decision"]["verdict"] == "DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE" and s["decision"]["flow32_declared_converged_or_true"] is False
    assert s["evidence"]["states_compared"] == 9 and s["evidence"]["acceptance_disagreements"] == 5
    assert s["single_grid_selection_on_the_04b_ladder"] == {"flow_24_alone_would_select": "s0.3125mm", "flow_32_alone_would_select": "s1.25mm"}
    assert 0.0 < s["decision"]["min_downforce_cosine_margin_to_proposal_threshold"] < 0.1  # the proposal role is not robust to a 0.9 threshold, and the record says so
    two_sided = {k for k, v in s["actual_primal_acceptance_by_grid"].items() if v["grids_disagree"]}
    flow24_fails = {k for k in two_sided if not s["actual_primal_acceptance_by_grid"][k]["flow_24"]["passes_rule"]}
    assert len(two_sided) == 5 and len(flow24_fails) == 4 and (two_sided - flow24_fails) == {"lowdim02a|+1.25mm"}


def evidence(down, drag, disagreements):
    return {"downforce_cosines": {"a": down[0], "b": down[1]}, "drag_cosines": {"a": drag[0], "b": drag[1]}, "acceptance_disagreements": disagreements, "states_compared": 9}


@pytest.mark.parametrize("down,drag,dis,verdict", [
    ((0.99, 0.97), (0.9, 0.85), 0, "FLOW24_SUFFICIENT_FOR_FIRST_UPDATE"),
    ((0.99, 0.97), (0.9, 0.85), 2, "DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE"),
    ((0.99, 0.97), (0.2, 0.1), 0, "UNDECIDED"),          # drag disagrees but acceptance never did: not sufficient, and nothing shows both are needed
    ((0.99, 0.7), (0.9, 0.85), 3, "UNDECIDED"),          # flow_24 may not even propose
    ((0.99, 0.864), (0.28, 0.1), 5, "DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE"),
])
def test_decision_rule_branches(down, drag, dis, verdict):
    assert G.decide(evidence(down, drag, dis))["verdict"] == verdict


def test_the_rule_is_strict_at_the_floor_and_requires_a_nonpositive_drag_change():
    assert not G.passes(3e-5, -1e-5) and G.passes(3.0001e-5, 0.0) and not G.passes(1e-4, 1e-9)


def test_a_tampered_input_is_refused(monkeypatch):
    monkeypatch.setitem(G.PINS, "grid01", (G.PINS["grid01"][0], "0" * 64))
    with pytest.raises(ValueError):
        G.build()


def test_floor_sensitivity_and_the_secant_norm_ratios_and_wall_time_ratios_are_pinned():
    s = json.loads(G.OUT.read_text())
    assert s["disagreements_by_floor"] == {"5e-06": 4, "1e-05": 4, "2e-05": 4, "3e-05": 5}  # only the 0.625 mm flow_24 case (3.4e-7 N under the floor) flips
    nr = s["secant_norm_ratios_flow32_over_flow24"]
    assert nr["downforce"]["parent_lowdim04a"] > 2.0 and nr["drag"]["parent_lowdim04a"] < 0.5
    assert all(2.2 < v["flow32_over_flow24_process_wall"] < 2.5 and 3.0 < v["flow32_over_flow24_julia_wall"] < 3.4 for v in s["wall_time_ratios_flow32_over_flow24"].values())


def test_decision_thresholds_are_inclusive_at_the_boundary():
    assert G.decide(evidence((0.8, 0.8), (0.1, 0.1), 1))["flow24_may_propose_directions"] is True
    assert G.decide(evidence((0.7999, 0.9), (0.1, 0.1), 1))["flow24_may_propose_directions"] is False
    assert G.decide(evidence((0.95, 0.95), (0.8, 0.8), 0))["verdict"] == "FLOW24_SUFFICIENT_FOR_FIRST_UPDATE"
    assert G.decide(evidence((0.9499, 0.99), (0.9, 0.9), 0))["verdict"] != "FLOW24_SUFFICIENT_FOR_FIRST_UPDATE"


def test_the_record_quotes_the_synthesis_numbers():
    s, rec = json.loads(G.OUT.read_text()), (G.OUT.parent / "decision_record.md").read_text()
    c = s["secant_vector_cosines"]
    for v in (c["downforce"]["baseline_grid01"], c["downforce"]["parent_lowdim04a"], c["drag"]["baseline_grid01"], c["drag"]["parent_lowdim04a"]):
        assert f"{v:.3f}" in rec
    w4 = s["w4_v17_resolution_sensitivity_percent"]
    assert f"{w4['flow24_to_flow32_drag_percent']:.2f}%" in rec and f"{w4['flow24_to_flow32_downforce_percent']:.2f}%" in rec and "5 of 9" in rec and "4 / 4 / 4 / 5" in rec
