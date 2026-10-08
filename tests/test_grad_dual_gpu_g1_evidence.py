"""G1 T4 evidence: frozen inputs match what ran, the registered rule gives PASS, flags stay false."""
import hashlib
import json
from pathlib import Path

from scripts import evaluate_grad_dual_gpu_g1 as g1

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_frozen_files_and_run_identity_match():
    freeze = json.loads((E / "prerun_freeze.json").read_text())
    identity = json.loads((E / "kernel_output/run_identity.json").read_text())
    assert sha(ROOT / "scripts/waterlily_grad_dual_gpu_spike_2026_10_08.jl") == freeze["script_sha256"]
    assert identity["pins"]["scripts/waterlily_grad_dual_gpu_spike_2026_10_08.jl"] == freeze["script_sha256"]
    assert identity["source_commit"] == freeze["source_commit"] and identity["failure_stage"] is None
    assert sha(E / "prerun_note.md") == freeze["prerun_note_sha256"] and sha(ROOT / "scripts/evaluate_grad_dual_gpu_g1.py") == freeze["evaluator_sha256"]
    assert sha(ROOT / "infra/kaggle/kernel_grad_dual_gpu_spike/runner.py") == freeze["runner_sha256"]


def test_kernel_output_matches_its_manifest_except_the_trimmed_log():
    manifest = json.loads((E / "kernel_output/output_manifest.json").read_text())["files"]
    for name, digest in manifest.items():
        if name != "instantiate.log":  # stored with trailing whitespace removed
            assert sha(E / "kernel_output" / name) == digest, name


def test_registered_rule_gives_pass_and_flags_are_false():
    result = json.loads((E / "kernel_output/result_g1.json").read_text())
    assert g1.decide(result)["verdict"] == "G1-PASS"
    assert result["backend"] == "cuda" and "Tesla T4" in result["gpu_name"]
    assert set(result["qualification_flags"].values()) == {False}
    assert json.loads((E / "g1_evaluation.json").read_text())["verdict"] == "G1-PASS"
