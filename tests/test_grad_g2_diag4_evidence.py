"""G2-DIAG4 recorded result: the kernel output kept in git is intact, the analysis is the registered one, and the earlier records are untouched."""
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag4 as A

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09"
K = E / "kernel_output"
ANALYSIS = json.loads((E / "diag4_analysis.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_kept_kernel_files_match_the_kernel_manifest():
    files = json.loads((K / "output_manifest.json").read_text())["files"]
    kept = {rel: d for rel, d in files.items() if not rel.startswith("snapshots/")}
    assert len(kept) >= 12 and all((K / rel).is_file() and sha(K / rel) == d for rel, d in kept.items())      # raw snapshots (175 MB) stay outside git
    assert len(files) - len(kept) == 18


def test_terminal_state_and_registered_identity():
    index = json.loads((K / "diag_index.json").read_text())
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists()
    assert index["status"] == "COMPLETE" and index["verdict"] == "DIAG4_RECORDED" and index["dryrun"] is False and index["backend"] == "cuda" and set(index["qualification_flags"].values()) == {False}
    assert index["clone_bit_identical_at_fork"] is True and index["independence_checked"] is True and index["result"]["gate"] == {"b0_vs_diag3_straight_checked_steps": 980, "failure": None, "fork_vs_diag3_f32_checked_steps": 200}
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    identity = json.loads((K / "run_identity.json").read_text())
    assert identity["source_commit"] == freeze["source_commit"] and identity["failure_stage"] is None and identity["spike_exit_code"] == 0
    assert all(identity["verified"][rel] == digest for rel, digest in freeze["pins"].items())
    assert all(index[k] == freeze["runtime_source_hashes"][k] for k in ("waterlily_flow_jl_sha256", "waterlily_multilevelpoisson_jl_sha256", "waterlily_poisson_jl_sha256"))


def test_analysis_is_the_registered_one_and_contains_no_bridge_value():
    assert ANALYSIS["integrity"]["pass"] is True and ANALYSIS["verdict"] == "FORCED32_DELAYED_ONSET" and ANALYSIS["regression"]["pass"] is True and ANALYSIS["control_b0_reproduces_the_corner_mode"] is True
    arms = ANALYSIS["arms"]
    assert arms["B0"]["classification"] == "DELAYED_ONSET" and arms["B0"]["first_step_box_gt_1"] == 838 and arms["B0"]["first_nonfinite_step"] == 1196
    assert arms["B32fork"]["classification"] == "DELAYED_ONSET" and arms["B32fork"]["first_step_box_gt_1"] == 1216 and arms["B32fork"]["magnitude_breach_step"] == 1261 and arms["B32fork"]["first_nonfinite_step"] is None
    assert arms["B32fork"]["mode"]["corner_localised"] is True and arms["B32fork"]["last_step"] == 1500 and arms["B32fork"]["primal_nonfinite_step"] is None
    assert arms["B32fresh"]["classification"] == "DIFFERENT_MODE" and arms["B32fresh"]["mode"]["first_dominant_step"] == 445          # secondary only; see the note on the evaluation point
    assert ANALYSIS["history_dependence_reading_secondary_only"]["fork"] == "DELAYED_ONSET"
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_bridge_value"] is True and set(ANALYSIS["qualification_flags"].values()) == {False}


def test_analyzer_reproduces_the_recorded_classes_from_the_kept_csvs():
    rows = {a: A.read_csv(K / f"arm_{a}.steps.csv") for a in A.ARMS}
    floor = float(next(r for r in rows["B0"] if int(r["step"]) == A.FORK_STEP)["glob_max_tangent_u"])
    for a in A.ARMS:
        got = A.analyse_arm(rows[a], floor, A.FIRST_STEP[a])
        assert A.classify_arm(got) == ANALYSIS["arms"][a]["classification"] and got["growth_event_step"] == ANALYSIS["arms"][a]["growth_event_step"], a
    assert A.regression(K, rows)["pass"] is True


def test_earlier_records_are_untouched():
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    for key, base in (("diag1_evidence_sha256", "grad03_g2_diag1_d0_nonfinite_2026_10_08"), ("diag2_evidence_sha256", "grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"),
                      ("diag3_evidence_sha256", "grad03_g2_diag3_tangent_poisson_2026_10_08")):
        for rel, digest in freeze[key].items():
            assert sha(ROOT / "docs/evidence" / base / rel) == digest, (key, rel)
