"""STEP-01 recorded result: the kept kernel output is intact and bound to the freeze, the analysis is the registered one and reproducible, the quoted observations hold."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_step01 as A  # noqa: E402
import step01_states as S  # noqa: E402

E = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
K = {k: E / "kernel_output" / k for k in "abc"}
FREEZE = json.loads((E / "prerun_freeze.json").read_text())
ANALYSIS = json.loads((E / "step01_analysis.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_terminal_state_every_kernel_complete_and_baselines_byte_identical_to_fd08():
    for k, d in K.items():
        index = json.loads((d / "step01_index.json").read_text())
        assert (d / "DONE").is_file() and not (d / "ERROR.txt").exists() and index["status"] == "COMPLETE" and index["states"][0]["matches_fd08_baseline_v17"] is True
        assert index["states"][0]["forces_csv_sha256"] == FREEZE["fd08_baseline"]["forces_csv_sha256"] and [e["name"] for e in index["states"]] == [p["name"] for p in S.state_plan(k)]
        ident = json.loads((d / "run_identity.json").read_text())
        assert ident["source_commit"] == FREEZE["source_commit"] and ident["failure_stage"] is None and all(ident["verified"][r] == v for r, v in {**FREEZE["pins"], **FREEZE["direction_files"]}.items())
        assert all(sha(d / rel) == digest for rel, digest in json.loads((d / "output_manifest.json").read_text())["files"].items())


def test_the_analysis_is_the_registered_one_and_reproduced_from_the_kept_output():
    assert ANALYSIS["verdict"] == "STEP01_RECORDED" and ANALYSIS["integrity"]["pass"] is True and ANALYSIS["provenance"]["freeze_sha256"] == sha(E / "prerun_freeze.json")
    assert ANALYSIS["provenance"]["analyzer_sha256"] == FREEZE["file_hashes"]["analyzer"] == sha(ROOT / "scripts/analyze_step01.py")
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_gradient_claim"] is True and ANALYSIS["fd08_verdict_unchanged"] is True
    assert set(ANALYSIS["qualification_flags"].values()) == {False}
    again = A.analyze(K, FREEZE)
    assert A.clean(again["series"]) == json.loads(json.dumps(A.clean(ANALYSIS["series"]))) and again["verdict"] == "STEP01_RECORDED"


def test_the_quoted_observations_hold():
    s = ANALYSIS["series"]
    assert len(s) == 8 and all(v["sign_stability"]["constant_over_resolved_steps"] is True and v["sign_stability"]["same_sign_as_g_hat_over_resolved_steps"] is True for v in s.values())
    assert all(v["agreement_radius_mm"]["50pct"] is not None for v in s.values()) and s["D0_interface_offset|drag"]["agreement_radius_mm"]["30pct"] == 10.0
    assert sum(1 for v in s.values() if v["agreement_radius_mm"]["30pct"] == 12.5) == 7
    d0 = s["D0_interface_offset|downforce"]["rows"]
    assert d0[0]["eta_even"] > 1.3 and d0[-1]["eta_even"] > 8 and d0[0]["delta_plus_n"] < 0 < s["D0_interface_offset|downforce"]["g_hat_n_per_m"]       # the +s response has the opposite sign of g-hat already at 2.5 mm
    for v in s.values():
        assert all(r["delta_plus_n"] + r["delta_minus_n"] < 0 for r in v["rows"])                      # the even part is negative for every series and step
    c = ANALYSIS["combined_directions"]
    assert all(cell["additivity"]["relative_to_combo"] > 1.0 for cell in c["D0_interface_offset+P1_upstream_lobe"].values())
    assert max(cell["additivity"]["relative_to_combo"] for cell in c["D1_filtered_seed11+D2_filtered_seed2026"].values()) < 0.3
    assert ANALYSIS["responses_n"]["a"]["step01__baseline"] == ANALYSIS["responses_n"]["b"]["step01__baseline"] == ANALYSIS["responses_n"]["c"]["step01__baseline"]


def test_earlier_records_are_untouched():
    for rel, digest in FREEZE["diag5_evidence_sha256"].items():
        assert sha(ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09" / rel) == digest
    assert FREEZE["file_hashes"]["formal_criteria"] == sha(ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json")
