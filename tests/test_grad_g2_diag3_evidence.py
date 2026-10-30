"""G2-DIAG3 recorded result: the kernel output kept in git is intact, the analysis is the registered one, and the earlier records are untouched."""
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag3 as A

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08"
K = E / "kernel_output"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
D2E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
ANALYSIS = json.loads((E / "diag3_analysis.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_kept_kernel_files_match_the_kernel_manifest():
    files = json.loads((K / "output_manifest.json").read_text())["files"]
    assert len(files) >= 30
    for rel, digest in files.items():
        assert sha(K / rel) == digest, rel


def test_terminal_state_and_registered_identity():
    index = json.loads((K / "diag_index.json").read_text())
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists()
    assert index["status"] == "COMPLETE" and index["verdict"] == "TANGENT_ONLY_NO_SUPPORT" and index["stage_b_verdict"] == "SKIPPED_NO_CANDIDATE" and index["selected_candidate"] is None
    assert index["dryrun"] is False and index["backend"] == "cuda" and set(index["qualification_flags"].values()) == {False} and index["arms"] == A.ARM_NAMES
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    identity = json.loads((K / "run_identity.json").read_text())
    assert identity["source_commit"] == freeze["source_commit"] and identity["failure_stage"] is None and identity["spike_exit_code"] == 0
    assert all(identity["verified"][rel] == digest for rel, digest in freeze["pins"].items())
    assert all(index[k] == freeze["runtime_source_hashes"][k] for k in ("waterlily_flow_jl_sha256", "waterlily_multilevelpoisson_jl_sha256", "waterlily_poisson_jl_sha256"))
    assert not (K / "longrun.steps.csv").exists()          # Stage B was not run: no candidate


def test_analysis_is_the_registered_one_and_contains_no_bridge_value():
    assert ANALYSIS["integrity"]["pass"] is True and ANALYSIS["verdict"] == "TANGENT_ONLY_NO_SUPPORT" and ANALYSIS["verdict_matches_kernel"] is True
    assert ANALYSIS["classes_match_kernel"] is True and ANALYSIS["selection_matches_kernel"] is True and ANALYSIS["stage_b_verdict"] == "SKIPPED_NO_CANDIDATE"
    a = ANALYSIS["stage_a"]
    assert a["baseline"]["identity_and_complete"] is True and 0.09 < a["baseline"]["slope"] < 0.11 and a["plateau"] == {"threshold": [], "count": []} and a["exceptions"] == []
    arms = a["arms"]
    tangent_only = [n for n in A.ARM_NAMES if n.startswith("A1_")]
    assert len(tangent_only) == 18 and all(arms[n]["primal_value_identity"] is True and arms[n]["class"] == "no_effect" and arms[n]["slope"] > 0.1 for n in tangent_only)
    assert all(arms[n]["tangent_relative_residual_after_demeaned_mean"] < arms[n]["tangent_relative_residual_before_mean"] for n in tangent_only if n != "A1_n01")
    assert arms["A1_n64"]["tangent_relative_residual_after_demeaned_mean"] < 2e-7 and arms["F32_forced_dual_32"]["class"] == "suppresses"
    assert all(arms[n]["primal_value_identity"] is False and arms[n]["class"] == "no_effect" for n in A.ARM_NAMES if n.startswith("D_"))
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_bridge_value"] is True and set(ANALYSIS["qualification_flags"].values()) == {False}


def test_analyzer_reproduces_the_recorded_classes_from_the_kept_csvs():
    rows = {n: A.read_csv(K / f"arm_{n}.steps.csv") for n in A.ARM_NAMES}
    s0, sb0 = A.slope_of(rows["A0_baseline"]), A.slope_of(rows["A0_baseline"], "box_project2_bc")
    floor = float(next(r for r in A.read_csv(K / "straight_checksums.csv") if int(r["step"]) == A.FORK_STEP)["glob_max_tangent_u"])
    for n in A.ARM_NAMES[1:]:
        r = rows[n]
        got = A.classify(A.slope_of(r), A.slope_of(r, "box_project2_bc"), float(r[-1]["glob_max_tangent_u"]), s0, sb0, floor, None)
        assert got == ANALYSIS["stage_a"]["arms"][n]["class"], n


def test_earlier_records_are_untouched():
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    for rel, digest in freeze["diag1_evidence_sha256"].items():
        assert sha(D1E / rel) == digest, rel
    for rel, digest in freeze["diag2_evidence_sha256"].items():
        assert sha(D2E / rel) == digest, rel
