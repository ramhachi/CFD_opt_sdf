"""OPT-01 v1.1 Stage A state plan: numpy-only, shared with the Kaggle runner; every parameter comes from the pinned OPT-01 v1 contract JSON.

Per grid: the new OPT-01 v1 parent (the LOWDIM-04B selected state, generation + 1) first, then the eight centered perturbations D0/D1/D2/P1 x -/+ the contract's secant step.
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
STEP_MM = float(CONTRACT["D3_update"]["secant_step_mm"])
if BASIS != tuple(S.SINGLE_DIRECTIONS):
    raise RuntimeError("the contract basis order differs from the frozen STEP-01 basis")
PARENT_NAME = "opt01a__parent"
_SCOPE = CONTRACT["D3_update"]["gate_scope"]


def hard_failures(kind, table):
    """Gates of `table` (name -> 'pass'|...) that block before CFD under the contract's gate scope: probes ("perturbation") exempt the report-only gates, proposals ("parent") exempt nothing."""
    exempt = _SCOPE["probe"]["report_only"] if kind == "perturbation" else []
    return sorted(g for g, v in table.items() if v != "pass" and g not in exempt)


def state_name(direction, sign):
    return f"opt01a__{direction}__{'plus' if sign > 0 else 'minus'}{STEP_MM:g}mm"


def plan():
    rows = [{"name": PARENT_NAME, "kind": "parent", "direction": None, "step_mm": 0.0, "sign": 0}]
    for d in BASIS:
        for sign in (-1, 1):
            rows.append({"name": state_name(d, sign), "kind": "perturbation", "direction": d, "step_mm": STEP_MM, "sign": sign})
    return rows
