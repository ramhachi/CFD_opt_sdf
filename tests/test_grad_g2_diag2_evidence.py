"""G2-DIAG2 recorded result: the kernel output kept in git is intact, the analysis is the registered one, and the earlier records are untouched."""
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag2 as A

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
K = E / "kernel_output"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
ANALYSIS = json.loads((E / "diag2_analysis.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_kept_kernel_files_match_the_kernel_manifest():
    files = json.loads((K / "output_manifest.json").read_text())["files"]
    assert len(files) >= 17
    for rel, digest in files.items():
        assert sha(K / rel) == digest, rel


def test_terminal_state_and_registered_identity():
    index = json.loads((K / "diag_index.json").read_text())
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists()
    assert index["verdict"] == "DIAG2_LOCALIZED" and index["status"] == "COMPLETE" and index["dryrun"] is False and index["backend"] == "cuda"
    assert set(index["qualification_flags"].values()) == {False} and index["v0_bitwise_equal_to_straight"] is True
    assert (index["fork_step"], index["end_step"], index["slope_from_step"]) == (780, 980, 880)
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    identity = json.loads((K / "run_identity.json").read_text())
    assert identity["source_commit"] == freeze["source_commit"] and identity["failure_stage"] is None and identity["spike_exit_code"] == 0
    assert all(identity["verified"][rel] == digest for rel, digest in freeze["pins"].items())
    assert index["waterlily_flow_jl_sha256"] == freeze["runtime_source_hashes"]["waterlily_flow_jl_sha256"]


def test_analysis_is_the_registered_one_and_contains_no_bridge_value():
    assert ANALYSIS["integrity"]["pass"] is True and ANALYSIS["verdict"] == "DIAG2_LOCALIZED" and ANALYSIS["verdict_matches_kernel"] is True and ANALYSIS["classes_match_kernel"] is True
    assert ANALYSIS["v0"]["bitwise_equal_to_straight"] is True and ANALYSIS["v0"]["complete_run"] is True and 0.09 < ANALYSIS["v0"]["slope_decade_per_step"] < 0.11
    classes = {n: v["class"] for n, v in ANALYSIS["variants"].items()}
    assert classes == {"V0_baseline": "baseline", "V1a_poisson_n4": "no_effect", "V1b_poisson_n16": "reduces", "V1c_poisson_n32": "suppresses", "V2_dt_tangent_frozen": "no_effect",
                       "V3_kill_corner_box": "suppresses", "V4a_kill_slab_xmin": "suppresses", "V4b_kill_slab_ymin": "suppresses", "V4c_kill_slab_zmax": "suppresses",
                       "V4d_kill_slabs_all": "suppresses", "V5_kill_ghost_layers": "no_effect", "V6_kill_exit_slab": "no_effect"}
    assert {k: v for k, v in ANALYSIS["hypotheses"].items() if k.startswith("H")} == {"H11": "supports", "H12": "refutes", "H13": "refutes", "H7": "refutes", "H8": "supports"}
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_bridge_value"] is True and set(ANALYSIS["qualification_flags"].values()) == {False}


def test_analyzer_reproduces_the_recorded_classes_from_the_kept_csvs():
    rows = {n: A.read_csv(K / f"variant_{n}.steps.csv") for n in A.VARIANTS}
    s0, sb0 = A.slope_of(rows["V0_baseline"]), A.slope_of(rows["V0_baseline"], "box_project2_bc")
    for n in A.VARIANTS[1:]:
        got = A.classify(A.slope_of(rows[n]), A.slope_of(rows[n], "box_project2_bc"), s0, sb0, None)
        assert got == ANALYSIS["variants"][n]["class"], n


def test_earlier_records_are_untouched():
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    for rel, digest in freeze["diag1_evidence_sha256"].items():
        assert sha(D1E / rel) == digest, rel
