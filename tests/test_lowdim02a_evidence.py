"""LOWDIM-02A recorded result: the kept kernel output is intact and bound to the freeze, the analysis is the registered one and reproducible, the quoted observations hold."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_lowdim02a as A  # noqa: E402

E = ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
K = E / "kernel_output/lowdim02a_a"
FREEZE = json.loads((E / "prerun_freeze.json").read_text())
ANALYSIS = json.loads((E / "lowdim02a_analysis.json").read_text())
INV = json.loads((E / "inventory.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_terminal_state_complete_and_the_baseline_is_byte_identical_to_the_w4_flow32_baseline():
    index = json.loads((K / "lowdim02a_index.json").read_text())
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists() and index["status"] == "COMPLETE" and [e["name"] for e in index["states"]] == INV["kernels"]["a"]
    assert index["states"][0]["matches_w4_v17_flow32_baseline"] is True and index["states"][0]["forces_csv_sha256"] == FREEZE["flow32_baseline"]["forces_csv_sha256"]
    assert index["states"][1]["forces_csv_sha256"] == index["states"][0]["forces_csv_sha256"]
    ident = json.loads((K / "run_identity.json").read_text())
    assert ident["source_commit"] == FREEZE["source_commit"] and ident["failure_stage"] is None and all(ident["verified"][r] == v for r, v in FREEZE["pins"].items())
    assert all(sha(K / rel) == digest for rel, digest in json.loads((K / "output_manifest.json").read_text())["files"].items())


def test_the_analysis_is_the_registered_one_and_reproduced_from_the_kept_output():
    assert ANALYSIS["verdict"] == "STAGE_A_CONSTRAINT_FAIL" and ANALYSIS["integrity"]["pass"] is True
    assert ANALYSIS["provenance"]["freeze_sha256"] == sha(E / "prerun_freeze.json") and ANALYSIS["provenance"]["analyzer_sha256"] == FREEZE["file_hashes"]["analyzer"] == sha(ROOT / "scripts/analyze_lowdim02a.py")
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_gradient_claim"] is True and ANALYSIS["not_grid01"] is True and ANALYSIS["not_opt01"] is True
    assert ANALYSIS["reinitialization"] == "none" and set(ANALYSIS["qualification_flags"].values()) == {False}
    again = A.analyze(K, FREEZE)
    assert again["verdict"] == "STAGE_A_CONSTRAINT_FAIL" and A.clean(again["stage_a"]) == json.loads(json.dumps(A.clean(ANALYSIS["stage_a"]))) and A.clean(again["flow_32"]) == json.loads(json.dumps(A.clean(ANALYSIS["flow_32"])))


def test_the_quoted_observations_hold():
    s = ANALYSIS["stage_a"]
    assert 7.3e-4 < s["downforce_gain_n"] < 7.4e-4 and s["control_downforce_change_n"] < -1.09e-3 and s["control_resolvably_loses_downforce"] is True and s["hard_geometry_gates_pass"] is True
    assert s["drag_constraint_ok"] is False and 5.4e-5 < s["drag_change_n"] < 5.5e-5 and s["drag_resolution_n"] == pytest.approx(3e-5) and s["resolution_source"] == "nominal_floor" and s["marginal"] is False
    d = ANALYSIS["descriptive_comparison_with_flow_24"]
    assert d["baseline_repeat_forces_csv_byte_identical"] is True and d["odd_part_n"]["flow32_over_flow24"] == pytest.approx(1.127, abs=2e-3) and d["even_part_n"]["flow32_over_flow24"] == pytest.approx(0.447, abs=2e-3)
    assert d["downforce_change_n"]["flow_32"]["+2.5"] > 1.2e-3 and d["downforce_change_n"]["flow_24_lowdim01"]["+2.5"] < 0 and d["baseline_downforce_n"]["relative_difference"] == pytest.approx(0.0894, abs=1e-3)
    assert d["resolved_sign_positive_on_flow32"] == {"+1.25": True, "-1.25": False}


def test_earlier_records_are_untouched():
    assert FREEZE["file_hashes"]["lowdim01_analysis"] == sha(ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09/lowdim01_analysis.json")
    assert FREEZE["file_hashes"]["formal_criteria"] == sha(ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json")
    assert FREEZE["file_hashes"]["w4_flow32_baseline_csv"] == sha(ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv")
