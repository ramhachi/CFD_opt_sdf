"""G2-DIAG1 recorded result: the kernel output kept in git is intact, the analysis is the one registered, and nothing outside the diagnostic changed."""
import gzip
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag1 as A

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
K = E / "kernel_output"
G2E = ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08"
ANALYSIS = json.loads((E / "diag1_analysis.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_kept_kernel_files_match_the_kernel_manifest():
    files = json.loads((K / "output_manifest.json").read_text())["files"]
    kept = 0
    for rel, digest in files.items():
        if rel == "stage_ledger.csv":
            assert hashlib.sha256(gzip.decompress((K / "stage_ledger.csv.gz").read_bytes())).hexdigest() == digest
        elif (K / rel).is_file():
            assert sha(K / rel) == digest, rel; kept += 1
        else:
            assert rel.startswith("snapshots/") and rel.endswith(".raw"), rel   # raw snapshots are kept outside git; SHAs in snapshot_index.json
    assert kept >= 15
    index = json.loads((K / "snapshot_index.json").read_text())
    assert len(index) == 57 and all(f"snapshots/{name}" in files and files[f"snapshots/{name}"] == meta["sha256"] for name, meta in index.items())


def test_terminal_state_and_registered_identity():
    index = json.loads((K / "diag_index.json").read_text())
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists()
    assert index["verdict"] == "DIAG_LOCALIZED" and index["status"] == "COMPLETE" and index["dryrun"] is False and index["backend"] == "cuda"
    assert set(index["qualification_flags"].values()) == {False}
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    identity = json.loads((K / "run_identity.json").read_text())
    assert identity["source_commit"] == freeze["source_commit"] and identity["failure_stage"] is None and identity["spike_exit_code"] == 0
    assert all(identity["verified"][rel] == digest for rel, digest in freeze["pins"].items())
    assert index["waterlily_flow_jl_sha256"] == freeze["runtime_source_hashes"]["waterlily_flow_jl_sha256"]


def test_analysis_is_the_registered_one_and_contains_no_bridge_value():
    assert ANALYSIS["integrity"]["pass"] is True and ANALYSIS["verdict"] == "DIAG_LOCALIZED" and ANALYSIS["verdict_matches_kernel"] is True
    assert ANALYSIS["first_bad_consistent_with_kernel"] is True and ANALYSIS["self_check"]["pass_rederived"] is True and ANALYSIS["self_check"]["mismatch_steps"] == []
    fi = ANALYSIS["failure_identity"]
    assert (fi["first_bad_step"], fi["first_bad_stage"], fi["first_bad_field"], fi["first_bad_component"]) == (1196, "correct_conv_diff", "f", "tangent")
    assert fi["first_nonfinite_value"]["tangent_repr"] == "Inf" and ANALYSIS["primal_health"]["first_primal_nonfinite"] is None
    assert ANALYSIS["case"] == "A" and ANALYSIS["growth"]["pattern"]["pattern"] == "roughly_exponential"
    assert {k: v for k, v in ANALYSIS["hypotheses"].items() if k.startswith("H")} == {"H1": "supports", "H2": "supports", "H3": "refutes", "H4": "refutes", "H5": "refutes", "H6": "refutes"}
    assert ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_bridge_value"] is True
    assert set(ANALYSIS["qualification_flags"].values()) == {False}


def test_analyzer_reproduces_the_recorded_first_bad_from_the_kept_ledger(tmp_path):
    (tmp_path / "stage_ledger.csv").write_bytes(gzip.decompress((K / "stage_ledger.csv.gz").read_bytes()))
    rows = A.load_ledger(tmp_path)
    bad = A.rederive_first_bad(rows)
    assert (bad["step"], bad["stage"], bad["field"], bad["np"], bad["nt"]) == (1196, "correct_conv_diff", "f", 0, 1)
    last, first = A.last_finite_and_first_bad_stage(rows, bad)
    assert last == (1196, 11, "project1_bc") and first == (1196, 12, "correct_conv_diff")


def test_g2_attempt1_namespace_is_untouched():
    sums = {line.split()[1]: line.split()[0] for line in (G2E / "SHA256SUMS").read_text().splitlines() if line.strip()}
    assert sums and all(sha(G2E / rel) == d for rel, d in sums.items() if (G2E / rel).is_file())
