"""OPT-01 v1 Stage A state plan: numpy-only, shared with the Kaggle runner; every parameter comes from the pinned OPT-01 v1 contract JSON.

Per grid: the new OPT-01 v1 parent (the LOWDIM-04B selected state, generation + 1) first, then the eight centered perturbations D0/D1/D2/P1 x -/+ the contract's secant step.
"""
import hashlib
import json
from pathlib import Path

import step01_states as S

CONTRACT_REL = "docs/evidence/opt01_v1_2026_10_15/opt01_v1_contract.json"
CONTRACT_SHA256 = "f76a09c79cea70ffd07d94994d5b075dc346ddf32c678a18b4fab49ab90643e2"
_raw = (Path(__file__).resolve().parents[1] / CONTRACT_REL).read_bytes()
if hashlib.sha256(_raw).hexdigest() != CONTRACT_SHA256:
    raise RuntimeError("the OPT-01 v1 contract differs from its pinned hash")
CONTRACT = json.loads(_raw)
BASIS = tuple(CONTRACT["pins"]["basis_order"])
STEP_MM = float(CONTRACT["D3_update"]["secant_step_mm"])
if BASIS != tuple(S.SINGLE_DIRECTIONS):
    raise RuntimeError("the contract basis order differs from the frozen STEP-01 basis")
PARENT_NAME = "opt01a__parent"


def state_name(direction, sign):
    return f"opt01a__{direction}__{'plus' if sign > 0 else 'minus'}{STEP_MM:g}mm"


def plan():
    rows = [{"name": PARENT_NAME, "kind": "parent", "direction": None, "step_mm": 0.0, "sign": 0}]
    for d in BASIS:
        for sign in (-1, 1):
            rows.append({"name": state_name(d, sign), "kind": "perturbation", "direction": d, "step_mm": STEP_MM, "sign": sign})
    return rows
