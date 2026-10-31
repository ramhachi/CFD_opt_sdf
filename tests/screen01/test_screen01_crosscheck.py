"""SCREEN-01 (#64): the analyzer and the independent second implementation (`scripts/screen01/screen01_check.py`) agree on every synthetic branch.

`screen01_check.check(T)` and `screen01_check.compare(mine, theirs, stage)` are the only entry points used (INTERFACE.md); the grid is the registered 81 per axis."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import synthetic as Y  # noqa: E402

S = Y.S
CHECK = S.ROOT / "scripts/screen01/screen01_check.py"
pytestmark = pytest.mark.skipif(not CHECK.exists(), reason="scripts/screen01/screen01_check.py is not present yet (run by the orchestrator once it is)")


@pytest.mark.parametrize("name", list(Y.BRANCHES))
def test_analyzer_and_checker_agree(name):
    assert S.GRID_N == 81
    T = Y.branch(name)
    mine = S.compute(T)
    record = S.cross_check(mine, T)             # raises with the discrepancy paths if they differ
    assert record["discrepancies"] == [] and record["stage"] == T["stage"]


def test_checker_does_not_mutate_its_input_and_is_deterministic():
    import screen01_check as C
    T = Y.branch("main_gain")
    before = copy.deepcopy(T)
    a = C.check(copy.deepcopy(T))
    assert T == before and C.check(copy.deepcopy(T)) == a
    assert set(S.CMP["main"]) <= set(a) and C.compare(S.canon({k: S.compute(T)[k] for k in S.CMP["main"]}), S.canon(a), "main") == []


def test_compare_detects_a_planted_difference():
    import screen01_check as C
    T = Y.branch("fin_base")
    mine = S.compute(T)
    theirs = C.check(copy.deepcopy(T))
    planted = {k: mine[k] for k in S.CMP["finalist"]}
    planted["K_opt"] += 1
    assert C.compare(S.canon(planted), S.canon(theirs), "finalist") != []
