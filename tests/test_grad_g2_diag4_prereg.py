"""G2-DIAG4 pre-registration: the freeze matches the files that will run, binds DIAG1-3, and the CPU dry-run evidence behaves as registered."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag4 as A
from scripts import build_grad_g2_diag4_freeze as B

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09"
FREEZE_PATH = E / "prerun_freeze.json"
DRY = E / "cpu_dryrun_diagnostic"


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


# ---- the DIAG3 authority the regression gates compare with (independent of the freeze) ---------------------------------------------------------
def test_diag2_v1c_and_diag3_f32_are_bit_identical_over_the_200_overlap_steps():
    cols = A.CS_COLUMNS
    d2 = {int(r["step"]): tuple(r[c] for c in cols) for r in A.read_csv(ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08/kernel_output/variant_V1c_poisson_n32.steps.csv")}
    d3 = {int(r["step"]): tuple(r[c] for c in cols) for r in A.read_csv(A.REF_F32)}
    assert set(d2) == set(d3) == set(range(781, 981)) and all(d2[s] == d3[s] for s in d2)
    assert set(range(0, 981)) <= {int(r["step"]) for r in A.read_csv(A.REF_STRAIGHT)}


@pytest.mark.skipif(not FREEZE_PATH.is_file(), reason="freeze not written yet")
class TestFreeze:
    @pytest.fixture(scope="class")
    def freeze(self):
        return json.loads(FREEZE_PATH.read_text())

    def test_sidecar_and_every_frozen_file_hash(self, freeze):
        assert hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest() == (E / "prerun_freeze.json.sha256").read_text().strip()
        for name, path in B.FILES.items():
            assert freeze["file_hashes"][name] == sha(path), name

    def test_runner_pins_agree_with_the_freeze(self, freeze):
        runner = (ROOT / "infra/kaggle/kernel_grad_g2_diag4/runner.py").read_text()
        assert f'SOURCE_COMMIT = "{freeze["source_commit"]}"' in runner
        assert set(freeze["pins"]) == {B.FILES[k] for k in ("t4_project", "t4_manifest", "script", "stages_diag1", "stages_diag3", "ref_straight", "ref_f32")}
        for rel, digest in freeze["pins"].items():
            assert digest in runner and sha(rel) == digest

    def test_earlier_records_are_bound_and_unchanged(self, freeze):
        for key, base in (("diag1_evidence_sha256", B.D1E), ("diag2_evidence_sha256", B.D2E), ("diag3_evidence_sha256", B.D3E)):
            for rel, digest in freeze[key].items():
                assert hashlib.sha256((base / rel).read_bytes()).hexdigest() == digest, (key, rel)
        d1 = json.loads((B.D1E / "prerun_freeze.json").read_text())
        assert freeze["canonical_state"] == d1["canonical_state"] and freeze["candidate_c_identity"] == d1["candidate_c_identity"] and freeze["scientific_state"] == d1["scientific_state"]
        assert freeze["directions"]["fortran_raw_sha256_d0_only"] == {"D0_interface_offset": "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"}

    def test_registered_design_constants_and_declarations(self, freeze):
        run = freeze["run"]
        assert (run["fork_step"], run["end_step"], run["reference_last_step"]) == (780, 1500, 980) and run["intervals"] == [list(i) for i in A.INTERVALS]
        assert run["rolling_windows"][0] == [800, 900] and run["rolling_windows"][-1] == [1400, 1500] and len(run["rolling_windows"]) == 25
        for k, v in freeze["analysis_constants"].items():
            assert getattr(A, k) == v, k
        assert freeze["classification"] == ["FORCED32_NO_ONSET_OBSERVED_TO_1500", "FORCED32_DELAYED_ONSET", "FORCED32_DIFFERENT_MODE", "FORCED32_GROWTH_UNLOCALIZED", "DIAG4_INCOMPLETE"]
        assert freeze["declarations"] == {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False,
                                          "forced32_is_a_different_solver_candidate": True}
        assert all(freeze["prohibitions"].values()) and set(freeze["qualification_flags"].values()) == {False} and "SECONDARY" in run["arms"]["B32fresh"]

    def test_kernel_identity_is_new_and_free(self, freeze):
        meta = freeze["kernel_identity"]
        assert meta["id"] == "ramhachi888/cfd-opt-sdf-grad-g2-d0-forced32-horizon-diag4" and meta["machine_shape"] == "NvidiaTeslaT4"
        used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag4"}
        assert meta["id"] not in used
        assert json.loads((E / "identity_free_check.json").read_text())["all_free"] is True

    def test_runtime_source_hashes_match_the_installed_waterlily_when_available(self, freeze):
        try:
            local = B.runtime_source_hashes()
        except AssertionError:
            pytest.skip("WaterLily source not installed")
        assert local == freeze["runtime_source_hashes"]


# ---- CPU dry-run evidence (code path only; not scientific data) ------------------------------------------------------------------------------------
def test_dryrun_gates_pass_clone_is_exact_and_simulations_are_independent():
    d = DRY / "gates_pass"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["verdict"] == "DIAG4_RECORDED" and index["dryrun"] is True and index["independence_checked"] is True and index["clone_bit_identical_at_fork"] is True
    assert index["result"]["gate"] == {"b0_vs_diag3_straight_checked_steps": 14, "fork_vs_diag3_f32_checked_steps": 8, "failure": None}
    assert len(list(csv.DictReader((d / "arm_B0.steps.csv").open()))) == 14 and len(list(csv.DictReader((d / "arm_B32fork.steps.csv").open()))) == 8
    assert len(list(csv.DictReader((d / "arm_B32fresh.steps.csv").open()))) == 14 and len(list(csv.DictReader((d / "cmp_B32fork_vs_B0.csv").open()))) == 8


def test_dryrun_a_regression_mismatch_stops_the_run_and_keeps_the_history():
    d = DRY / "gate_failure"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["verdict"] == "DIAG4_INCOMPLETE" and index["status"] == "ERROR" and "B32fork differs from the DIAG3 F32 arm" in index["error"] and "at step 9" in index["error"]
    assert not (d / "DONE").exists() and len(list(csv.DictReader((d / "arm_B32fork.steps.csv").open()))) == 3


def test_dryrun_an_exception_is_incomplete_and_keeps_the_history():
    d = DRY / "exception"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["verdict"] == "DIAG4_INCOMPLETE" and "deliberate dry-run exception at step 9" in index["error"] and not (d / "DONE").exists()
    assert len(list(csv.DictReader((d / "arm_B0.steps.csv").open()))) == 8
