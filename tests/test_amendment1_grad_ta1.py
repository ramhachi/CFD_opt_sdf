"""GRAD-TA1 amendment 1: the only behavioural difference from the frozen analyzer is the Float32 tau comparison."""
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import analyze_grad_ta1 as A
from scripts import analyze_grad_ta1_amendment1 as M
from tests.test_grad_ta1_analyzer import RECORD, build_ta1, make_blocked, patch_index

ROOT = Path(__file__).resolve().parents[1]
TAU32 = float(np.float32(1e-5))   # what the kernel records: 9.999999747378752e-06


def test_the_real_recorded_tau_is_the_float64_value_of_the_float32_one():
    index = json.loads((ROOT / "docs/evidence/grad_ta1_2026_10_15/kernel_output/grad_ta1/g2_run_index.json").read_text())
    assert index["tau"] == TAU32 != 1e-5 and M.tau_ok(index)


@pytest.mark.parametrize("blocked", [False, True])
def test_float32_tau_is_incomplete_when_frozen_and_equals_the_float64_tau_result_when_amended(tmp_path, blocked):
    out, freeze, formal = build_ta1(tmp_path)                                         # tau = 1e-5 as a Float64: the frozen check passes
    if blocked:
        make_blocked(out)
    reference = A.analyze_output(out, freeze, RECORD, formal)
    assert "problems" not in reference or M.TAU_PROBLEM not in reference["problems"]
    patch_index(out, tau=TAU32)
    frozen = A.analyze_output(out, freeze, RECORD, formal)
    assert frozen["verdict"] == "GRAD_TA1_INCOMPLETE" and frozen["problems"] == [M.TAU_PROBLEM]
    amended = M.analyze_output(out, freeze, RECORD, formal)
    assert amended.pop("amendment") == M.LABEL and amended == reference               # the only behavioural difference is the tau check
    assert reference["verdict"] == ("GRAD_TA1_BLOCKED" if blocked else reference["verdict"])


@pytest.mark.parametrize("tau, width", [(1e-4, 1), (2e-5, 1), (None, 1), (TAU32, 2)])
def test_a_genuinely_wrong_tau_or_width_is_still_incomplete(tmp_path, tau, width):
    out, freeze, formal = build_ta1(tmp_path)
    patch_index(out, tau=tau, dual_width=width)
    result = M.analyze_output(out, freeze, RECORD, formal)
    assert result["verdict"] == "GRAD_TA1_INCOMPLETE" and M.TAU_PROBLEM in result["problems"]
