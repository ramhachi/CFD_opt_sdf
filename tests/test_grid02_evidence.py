"""Verify the retained GRID-02 evidence: kernel outputs intact and bound to the freeze, the analysis the registered one and reproducible, the quoted observations hold."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_grid02 as A  # noqa: E402

E = ROOT / "docs/evidence/grid02_trend_2026_10_16"
K = E / "kernel_output"
FREEZE = json.loads((E / "prerun_freeze.json").read_text())
ANALYSIS = json.loads((E / "grid02_analysis.json").read_text())
KERNELS = ("f16", "f48a", "f48b", "s24", "s32")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_all_five_kernels_complete_and_the_manifests_hold():
    for k in KERNELS:
        d = K / f"grid02_{k}"
        index = json.loads((d / "grid02_index.json").read_text())
        assert (d / "DONE").is_file() and not (d / "ERROR.txt").exists() and index["status"] == "COMPLETE" and all(s["complete"] for s in index["states"])
        ident = json.loads((d / "run_identity.json").read_text())
        assert ident["source_commit"] == FREEZE["source_commit"] and ident["failure_stage"] is None
        assert all(sha(d / rel) == digest for rel, digest in json.loads((d / "output_manifest.json").read_text())["files"].items())
    assert sum(len(json.loads((K / f"grid02_{k}" / "grid02_index.json").read_text())["states"]) for k in KERNELS) == 29


def test_the_analysis_is_the_registered_one_and_reproduces_from_the_kept_output():
    assert ANALYSIS["verdict"] == "GRID02_RECORDED" and ANALYSIS["integrity"]["pass"] is True
    assert ANALYSIS["provenance"]["freeze_sha256"] == sha(E / "prerun_freeze.json") and ANALYSIS["provenance"]["analyzer_sha256"] == sha(ROOT / "scripts/analyze_grid02.py")
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["shape_update_allowed"] is False and set(ANALYSIS["qualification_flags"].values()) == {False}
    again = A.analyze({k: K / f"grid02_{k}" for k in KERNELS}, FREEZE)
    assert again["verdict"] == "GRID02_RECORDED"
    for key in ("cells", "alignment", "fine", "stable_32_to_48", "placement_effect", "four_point_table"):
        assert json.loads(json.dumps(again[key], allow_nan=False)) == ANALYSIS[key], key


def test_the_quoted_observations_hold():
    al, fi, c = ANALYSIS["alignment"], ANALYSIS["fine"], ANALYSIS["cells"]
    assert al["classification"] == "GRID02_ALIGNMENT_PARTIAL_OR_MIXED" and fi["classification"] == "FINE_CONTINUES_TO_FLOW32" and ANALYSIS["stable_32_to_48"] is True
    assert al["m24"] == pytest.approx(0.561, abs=2e-3) and al["m32"] == pytest.approx(-1.105, abs=2e-3) and fi["r"] == pytest.approx(1.007, abs=2e-3) and al["G"] == pytest.approx(3.96e-4, abs=2e-6)
    b = {k: v["fit"]["b_n_per_mm"] for k, v in c.items()}
    assert b["24n"] < 1e-4 < 4e-4 < min(b["16n"], b["32n"], b["48n"]) and abs(b["48n"] - b["32n"]) < 5e-6
    assert c["48n"]["fit"]["max_residual_n"] > 3e-5 and c["48n"]["b_central_n_per_mm"] > 6e-4
    pe = ANALYSIS["placement_effect"]
    assert pe["32"]["parent_downforce_shifted_minus_native_n"] == pytest.approx(-0.0346, abs=5e-4) and pe["24"]["parent_downforce_shifted_minus_native_n"] == pytest.approx(0.0055, abs=2e-4)
    assert ANALYSIS["slope_robustness"]["would_change_if_slopes_were"]["b_central"]["stable_32_to_48"] is False
    rule = ANALYSIS["both_grid_rule_descriptive"]
    assert rule["24n_32n"]["passing_steps_mm"] == [] and rule["24s_32s"]["passing_steps_mm"] == [0.9375, 1.25] and rule["32n_48n"]["passing_steps_mm"] == [0.3125, 0.625, 0.9375, 1.25]


def test_earlier_records_are_untouched():
    assert FREEZE["file_hashes"]["opt01b_analysis"] == sha(ROOT / "docs/evidence/opt01b_stage_b_2026_10_15/opt01b_analysis.json") if "opt01b_analysis" in FREEZE["file_hashes"] else True
