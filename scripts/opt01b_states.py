"""OPT-01 v1.1 Stage B state plan: numpy-only, shared with the Kaggle runner; every parameter comes from the pinned OPT-01 v1.1 contract JSON.

Per grid: the OPT-01 v1 parent (the Stage A parent, generation 1) first, then the positive ladder along the Stage A robust solution (proposal states)
and its reverse diagnostics (probe states).  Copy-adapted from the frozen lowdim04b_states (never edited).
"""
import hashlib
import json
from pathlib import Path

import step01_states as S

CONTRACT_REL = "docs/evidence/opt01_v1_2026_10_15/opt01_v1_1_contract.json"
CONTRACT_SHA256 = "0f164a4e555d6a2169fc5e30b6e2cf12957da76d1d1560f05121d3e3efbf0ba1"
_raw = (Path(__file__).resolve().parents[1] / CONTRACT_REL).read_bytes()
if hashlib.sha256(_raw).hexdigest() != CONTRACT_SHA256:
    raise RuntimeError("the OPT-01 v1 contract differs from its pinned hash")
CONTRACT = json.loads(_raw)
BASIS = tuple(CONTRACT["pins"]["basis_order"])
if BASIS != tuple(S.SINGLE_DIRECTIONS):
    raise RuntimeError("the contract basis order differs from the frozen STEP-01 basis")
_LADDER = CONTRACT["D3_update"]["ladder"]
STEPS_MM = tuple(float(s) for s in _LADDER["steps_mm"])
CONTROL_STEPS_MM = tuple(float(s) for s in _LADDER["reverse_diagnostics_mm"])   # reverse diagnostics: never accepted, never selected
if (_LADDER["sign"], STEPS_MM, CONTROL_STEPS_MM) != (1, (0.3125, 0.625, 0.9375, 1.25), (0.625, 1.25)):
    raise RuntimeError("the contract ladder differs from the registered Stage B ladder")
PARENT_NAME = "opt01b__parent"
DIRECTION = "robust_opt01a"
_SCOPE = CONTRACT["D3_update"]["gate_scope"]


def hard_failures(kind, table):
    """Gates of `table` (name -> 'pass'|...) that block under the contract's gate scope.

    kind "control" (reverse diagnostic = probe): the report-only gates are exempt; "parent" and "candidate" (proposal states): nothing is exempt.
    Pre-CFD a failing parent or control blocks the stage; a failing candidate is gate-REJECTED for that step (it is neither dropped nor shrunk).
    """
    exempt = _SCOPE["probe"]["report_only"] if kind == "control" else []
    return sorted(g for g, v in table.items() if v != "pass" and g not in exempt)


def candidate_name(step_mm):
    return f"opt01b__prop__s{step_mm:g}mm"


def control_name(step_mm):
    return f"opt01b__ctrl_reverse__s{step_mm:g}mm"


def plan():
    return ([{"name": PARENT_NAME, "kind": "parent", "direction": None, "step_mm": 0.0, "sign": 0}]
            + [{"name": candidate_name(s), "kind": "candidate", "direction": DIRECTION, "step_mm": s, "sign": 1} for s in STEPS_MM]
            + [{"name": control_name(s), "kind": "control", "direction": DIRECTION, "step_mm": s, "sign": -1} for s in CONTROL_STEPS_MM])
