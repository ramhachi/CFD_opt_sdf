"""G2-DIAG2 pre-registration: the freeze matches the files that will run, binds the immutable DIAG1 evidence, and the CPU dry-run evidence behaves as registered."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag2 as A
from scripts import build_grad_g2_diag2_freeze as B

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
FREEZE_PATH = E / "prerun_freeze.json"
pytestmark = pytest.mark.skipif(not FREEZE_PATH.is_file(), reason="freeze not written yet")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def freeze():
    return json.loads(FREEZE_PATH.read_text())


def test_freeze_sidecar_and_every_frozen_file_hash(freeze):
    assert hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest() == (E / "prerun_freeze.json.sha256").read_text().strip()
    for name, path in B.FILES.items():
        assert freeze["file_hashes"][name] == sha(path), name


def test_runner_pins_agree_with_the_freeze(freeze):
    runner = (ROOT / "infra/kaggle/kernel_grad_g2_diag2/runner.py").read_text()
    assert f'SOURCE_COMMIT = "{freeze["source_commit"]}"' in runner
    assert set(freeze["pins"]) == {B.FILES[k] for k in ("t4_project", "t4_manifest", "script", "stages_diag1", "stages_diag2")}
    for rel, digest in freeze["pins"].items():
        assert digest in runner and sha(rel) == digest


def test_diag1_record_is_bound_and_unchanged(freeze):
    for rel, digest in freeze["diag1_evidence_sha256"].items():
        assert hashlib.sha256((D1E / rel).read_bytes()).hexdigest() == digest, rel
    d1 = json.loads((D1E / "prerun_freeze.json").read_text())
    assert freeze["diag1"]["source_commit"] == d1["source_commit"] and freeze["canonical_state"] == d1["canonical_state"] and freeze["candidate_c_identity"] == d1["candidate_c_identity"]
    assert freeze["directions"]["fortran_raw_sha256_d0_only"] == {"D0_interface_offset": "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"}
    sci = freeze["scientific_state"]
    assert (sci["float"], sci["dual_width"], sci["remeasure"], sci["poisson_tol"], sci["poisson_itmx"], sci["case_id"]) == ("Float32", 1, True, 1e-4, 32, "flow_24")


def test_registered_design_and_constants(freeze):
    run = freeze["run"]
    assert (run["fork_step"], run["end_step"], run["slope_window"]) == (780, 980, [880, 980]) and list(run["variants"]) == list(A.VARIANTS)
    for k, v in freeze["analysis_constants"].items():
        assert getattr(A, k) == v, k
    assert (A.BASELINE_MIN_SLOPE, A.SUPPRESS_SLOPE, A.REDUCE_FACTOR) == (0.05, 0.01, 0.5)
    assert set(freeze["hypotheses"]) == set(A.HYPOTHESES) and freeze["hypothesis_variants"] == {h: list(v) for h, v in A.HYPOTHESES.items()}
    assert run["intervention_stages"] == ["predict_bc", "predict_exitbc", "project1_bc", "correct_bc", "project2_bc"]


def test_declarations_prohibitions_and_flags(freeze):
    assert freeze["declarations"]["selected_delta"] is None and freeze["declarations"]["grad03_verdict"] is None and freeze["declarations"]["reverse"] == "untouched"
    assert freeze["declarations"]["bridge_value"] is None and freeze["declarations"]["float64_run"] is False and freeze["declarations"]["interventions_are_counterfactual_not_fixes"] is True
    assert all(freeze["prohibitions"].values()) and set(freeze["qualification_flags"].values()) == {False}


def test_kernel_identity_is_new_and_free(freeze):
    meta = freeze["kernel_identity"]
    assert meta["id"] == "ramhachi888/cfd-opt-sdf-grad-g2-d0-tangent-diag2" and meta["machine_shape"] == "NvidiaTeslaT4"
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag2"}
    assert meta["id"] not in used
    check = json.loads((E / "identity_free_check.json").read_text())
    assert check["all_free"] is True and check["intended_slugs"] == ["cfd-opt-sdf-grad-g2-d0-tangent-diag2"]


def test_runtime_source_hashes_match_the_installed_waterlily_when_available(freeze):
    try:
        local = B.runtime_source_hashes()
    except AssertionError:
        pytest.skip("WaterLily source not installed")
    assert local == freeze["runtime_source_hashes"]


# ---- CPU dry-run evidence (code path only; not scientific data) -------------------------------------------------------------
DRY = E / "cpu_dryrun_diagnostic"


def test_dryrun_all_variants_run_and_v0_is_bitwise_equal_to_the_straight_replay():
    d = DRY / "all_variants"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["dryrun"] is True and index["v0_bitwise_equal_to_straight"] is True and index["status"] in ("COMPLETE",)
    assert index["preflight"]["tangent_zero_in_box"] and index["preflight"]["value_kept"] and index["preflight"]["tangent_untouched_outside"]
    assert list(index["variant_results"]) == list(A.VARIANTS) and not any("exception" in r for r in index["variant_results"].values())
    straight = {int(r["step"]): tuple(r[c] for c in A.CS_COLUMNS) for r in csv.DictReader((d / "straight_checksums.csv").open())}
    v0 = list(csv.DictReader((d / "variant_V0_baseline.steps.csv").open()))
    assert len(v0) == 8 and all(straight[int(r["step"])] == tuple(r[c] for c in A.CS_COLUMNS) for r in v0)
    # interventions change the state, V0 does not: a killed-region variant differs from V0 in its checksums
    v3 = list(csv.DictReader((d / "variant_V3_kill_corner_box.steps.csv").open()))
    assert tuple(v3[-1][c] for c in A.CS_COLUMNS) != tuple(v0[-1][c] for c in A.CS_COLUMNS)
    v1 = {r["step"]: r for r in csv.DictReader((d / "variant_V1a_poisson_n4.steps.csv").open())}
    assert {float(r["iters1"]) for r in v1.values()} == {4.0}


def test_dryrun_variant_exception_is_recorded_and_the_run_is_incomplete():
    d = DRY / "raise_variant"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["verdict"] == "DIAG2_INCOMPLETE" and index["status"] == "INCOMPLETE" and "deliberate dry-run exception" in index["variant_results"]["V3_kill_corner_box"]["exception"]
    assert index["variant_results"]["V0_baseline"]["steps_run"] == 8 and not (d / "DONE").exists()
