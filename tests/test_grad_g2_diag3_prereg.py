"""G2-DIAG3 pre-registration: the freeze matches the files that will run, binds the DIAG1/DIAG2 records and the dry-run evidence behaves as registered."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag3 as A
from scripts import build_grad_g2_diag3_freeze as B

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
D2E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
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
    runner = (ROOT / "infra/kaggle/kernel_grad_g2_diag3/runner.py").read_text()
    assert f'SOURCE_COMMIT = "{freeze["source_commit"]}"' in runner
    assert set(freeze["pins"]) == {B.FILES[k] for k in ("t4_project", "t4_manifest", "script", "stages_diag1", "stages_diag3", "fixture")}
    for rel, digest in freeze["pins"].items():
        assert digest in runner and sha(rel) == digest


def test_earlier_records_are_bound_and_unchanged(freeze):
    for rel, digest in freeze["diag1_evidence_sha256"].items():
        assert hashlib.sha256((D1E / rel).read_bytes()).hexdigest() == digest, rel
    for rel, digest in freeze["diag2_evidence_sha256"].items():
        assert hashlib.sha256((D2E / rel).read_bytes()).hexdigest() == digest, rel
    assert freeze["g2_plain_history_sha256"] == hashlib.sha256(A.G2_PLAIN_HISTORY.read_bytes()).hexdigest()
    d2 = json.loads((D2E / "diag2_analysis.json").read_text())
    assert d2["verdict"] == "DIAG2_LOCALIZED" and freeze["diag2"]["verdict"] == "DIAG2_LOCALIZED"
    d1 = json.loads((D1E / "prerun_freeze.json").read_text())
    assert freeze["canonical_state"] == d1["canonical_state"] and freeze["candidate_c_identity"] == d1["candidate_c_identity"] and freeze["scientific_state"] == d1["scientific_state"]
    assert freeze["directions"]["fortran_raw_sha256_d0_only"] == {"D0_interface_offset": "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"}


def test_registered_design_constants_and_declarations(freeze):
    run = freeze["run"]
    assert (run["fork_step"], run["end_step"], run["slope_window"]) == (780, 980, [880, 980]) and run["arms"] == A.ARM_NAMES and len(A.ARM_NAMES) == 24
    for k, v in freeze["analysis_constants"].items():
        assert getattr(A, k) == v, k
    assert (A.SUPPRESS_SLOPE, A.FLOOR_FACTOR, A.BASELINE_MIN_SLOPE, A.PLATEAU_RUN, A.MAX_TANGENT_CYCLES) == (0.005, 2.0, 0.05, 3, 64)
    assert freeze["declarations"] == {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False}
    assert all(freeze["prohibitions"].values()) and set(freeze["qualification_flags"].values()) == {False} and set(freeze["hypotheses"]) == {"H11", "H14"}
    assert freeze["poisson_semantics"]["system"].startswith("A(L) x = z")


def test_kernel_identity_is_new_and_free(freeze):
    meta = freeze["kernel_identity"]
    assert meta["id"] == "ramhachi888/cfd-opt-sdf-grad-g2-d0-tangent-poisson-diag3" and meta["machine_shape"] == "NvidiaTeslaT4"
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag3"}
    assert meta["id"] not in used
    check = json.loads((E / "identity_free_check.json").read_text())
    assert check["all_free"] is True and check["intended_slugs"] == ["cfd-opt-sdf-grad-g2-d0-tangent-poisson-diag3"]


def test_runtime_source_hashes_match_the_installed_waterlily_when_available(freeze):
    try:
        local = B.runtime_source_hashes()
    except AssertionError:
        pytest.skip("WaterLily source not installed")
    assert local == freeze["runtime_source_hashes"]


# ---- CPU dry-run evidence (code path only; not scientific data) ------------------------------------------------------------------------
DRY = E / "cpu_dryrun_diagnostic"


def test_dryrun_all_arms_ran_identity_holds_for_tangent_only_arms_only():
    d = DRY / "all_arms"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["dryrun"] is True and index["baseline"]["identity_and_complete"] is True and sorted(index["arm_results"]) == sorted(A.ARM_NAMES) and index["arms"] == A.ARM_NAMES
    assert not any("exception" in r for r in index["arm_results"].values()) and all(v["steps_run"] == 8 for v in index["arm_results"].values())
    ident = index["identity_primal_values"]
    assert all(ident[a] for a in A.ARM_NAMES if a.startswith(("A0", "A1")))                       # the primal never moves under tangent-only continuation
    assert not any(ident[a] for a in ("F32_forced_dual_32",)) and not all(ident[a] for a in A.ARM_NAMES if a.startswith("D_"))   # the secondary arms do change the primal
    smoke = index["smoke"]
    assert smoke["s_refine"]["primal_equal_to_baseline"] and smoke["s_threshold"]["primal_equal_to_baseline"] and not smoke["s_forced"]["primal_equal_to_baseline"]
    rows = list(csv.DictReader((d / "arm_A1_n04.steps.csv").open()))
    assert {float(r["cyc1"]) for r in rows} == {4.0} and {float(r["cyc2"]) for r in rows} == {4.0}
    assert len(list(csv.DictReader((d / "drift.csv").open()))) >= 20


def test_dryrun_stage_b_runs_for_a_forced_candidate_and_an_arm_exception_is_incomplete():
    d = DRY / "stage_b"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["selected_candidate"] == "A1_tau_1e-5" and index["stage_b_verdict"] == "DRYRUN_STAGE_B" and index["stage_b"]["steps_run"] == 12
    assert len(list(csv.DictReader((d / "longrun.steps.csv").open()))) == 12
    r = DRY / "raise_arm"
    ri = json.loads((r / "diag_index.json").read_text())
    assert ri["verdict"] == "DIAG3_INCONCLUSIVE" and ri["status"] == "INCOMPLETE" and "deliberate dry-run exception" in ri["arm_results"]["A1_n02"]["exception"]
    assert not (r / "DONE").exists()
