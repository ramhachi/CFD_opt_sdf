"""OPT-01 v1 Stage A: the state plan and the analysis rules are the pinned contract's (parameterized, not hard-coded)."""
import copy
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_opt01a as A  # noqa: E402
import lowdim04a_contract as C  # noqa: E402
import lowdim04a_states as L4  # noqa: E402
import opt01a_states as L  # noqa: E402


def test_plan_is_parent_first_then_eight_centered_perturbations_mirroring_lowdim04a():
    plan = L.plan()
    assert [r["name"] for r in plan][0] == "opt01a__parent" and len(plan) == 9
    assert [r["name"].replace("opt01a__", "") for r in plan] == [r["name"].replace("lowdim04a__", "") for r in L4.plan()]
    assert [{k: v for k, v in r.items() if k != "name"} for r in plan] == [{k: v for k, v in r.items() if k != "name"} for r in L4.plan()]
    assert list(C.BASIS) == list(L.BASIS)


def test_the_contract_hash_is_pinned_and_the_parameters_come_from_it():
    assert hashlib.sha256((ROOT / L.CONTRACT_REL).read_bytes()).hexdigest() == L.CONTRACT_SHA256
    assert L.STEP_MM == L.CONTRACT["D3_update"]["secant_step_mm"] == 1.25 and L.BASIS == tuple(L.CONTRACT["pins"]["basis_order"])
    A.check_contract_parameters()
    assert A.FROZEN_PARAMETERS == {"step_m": 0.00125, "min_resolved_n": 3e-5, "epsilon_n_per_m": 0.012, "min_predicted_downforce_n": 3e-5}


def test_changed_floors_or_cone_code_are_rejected(monkeypatch):
    bad = copy.deepcopy(L.CONTRACT); bad["floors"]["l1_epsilon_n_per_m"] = 0.006
    monkeypatch.setattr(L, "CONTRACT", bad)
    with pytest.raises(ValueError, match="differ from the OPT-01 v1 contract"):
        A.check_contract_parameters()
    monkeypatch.undo()
    monkeypatch.setitem(A.CONE_CODE, "scripts/lowdim04a_contract.py", "0" * 64)
    with pytest.raises(ValueError, match="differ from the OPT-01 v1 contract"):
        A.check_contract_parameters()


def test_the_imported_rules_are_the_frozen_lowdim04a_ones_at_the_registered_1p25_mm():
    a = C.secant_sample(1.0, 1.0 + 1e-3, 1.0 - 1e-3)
    assert a["g_sec_n_per_m"] == pytest.approx(2e-3 / (2 * 0.00125)) and C.EPSILON_N_PER_M == pytest.approx(0.012)
