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
