"""G2 attempt 1: the registered fail-closed path fired; no bridge was produced; plain baseline reproduced FD-08 exactly."""
import json
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_bridge as analyzer

E = Path(__file__).resolve().parents[1] / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08"


def load(name):
    return json.loads((E / name).read_text())


def test_attempt_failed_closed_and_was_not_mistaken_for_success():
    verification = load("terminal_verification_attempt1.json")
    assert verification["status"] == "FAIL_G2_TERMINAL_INTEGRITY"
    assert not (E / "kernel_attempt1/DONE").exists() and (E / "kernel_attempt1/ERROR.txt").is_file()
    index = load("kernel_attempt1/g2_run_index.json")
    assert index["status"] == "ERROR" and "non-finite" in index["error"] and list(index["runs"]) == ["plain"]
    assert load("kernel_attempt1/run_identity.json")["spike_exit_code"] == 2
    with pytest.raises(ValueError):
        analyzer.analyze(verification, json.loads(analyzer.SCOPE_RECORD.read_text()))


def test_no_bridge_artifact_exists_and_no_delta_or_flag_was_set():
    assert not list(E.glob("bridge_analysis*")) and not list(E.glob("*bridge_table*"))
    freeze = load("prerun_freeze.json")
    assert freeze["declarations"]["selected_delta"] is None and set(freeze["qualification_flags"].values()) == {False}


def test_plain_baseline_reproduced_the_registered_fd08_baseline_exactly():
    plain = load("terminal_verification_attempt1.json")["integrity"]["plain_vs_formal_baseline_v17"]
    assert plain["rel_drag"] == 0.0 and plain["rel_downforce"] == 0.0
    assert load("terminal_verification_attempt1.json")["runs"]["plain"]["samples"] == 1093
