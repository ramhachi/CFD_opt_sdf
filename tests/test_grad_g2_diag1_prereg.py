"""G2-DIAG1 pre-registration: the freeze matches the files that will run, binds the immutable G2 attempt-1 evidence, and the dry-run evidence behaves as registered."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag1 as A
from scripts import build_grad_g2_diag1_freeze as B

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
G2E = ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08"
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
    runner = (ROOT / "infra/kaggle/kernel_grad_g2_diag1/runner.py").read_text()
    assert f'SOURCE_COMMIT = "{freeze["source_commit"]}"' in runner
    assert set(freeze["pins"]) == {B.FILES[k] for k in ("t4_project", "t4_manifest", "script", "stages")}
    for rel, digest in freeze["pins"].items():
        assert digest in runner and sha(rel) == digest


def test_parent_g2_attempt1_identity_is_bound_and_untouched(freeze):
    assert len(freeze["parent_integration_commit"]) == 40
    for rel, digest in freeze["g2_attempt1_evidence_sha256"].items():
        assert hashlib.sha256((G2E / rel).read_bytes()).hexdigest() == digest, rel
    g2 = json.loads((G2E / "prerun_freeze.json").read_text())
    assert freeze["g2_attempt1"]["source_commit"] == g2["source_commit"] == "e44d0f08c07bde902017cc49854ef85b6ac6be64"
    assert freeze["g2_attempt1"]["script_sha256"] == sha("scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl") == g2["file_hashes"]["script"]
    assert freeze["g2_attempt1"]["failure"] == {"step": 1200, "t_u_l_repr": "16.409412384033203"} and freeze["g2_attempt1"]["verdict"] == "G2-BLOCKED"
    sums = {line.split()[1]: line.split()[0] for line in (G2E / "SHA256SUMS").read_text().splitlines() if line.strip()}
    assert sums and all(hashlib.sha256((G2E / rel).read_bytes()).hexdigest() == d for rel, d in sums.items() if (G2E / rel).is_file())


def test_scientific_state_is_that_of_g2_d0_only(freeze):
    g2 = json.loads((G2E / "prerun_freeze.json").read_text())
    assert freeze["candidate_c_identity"] == g2["candidate_c_identity"] and freeze["canonical_state"] == g2["canonical_state"]
    assert freeze["directions"]["fortran_raw_sha256_d0_only"] == {"D0_interface_offset": "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"}
    assert hashlib.sha256((ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw").read_bytes()).hexdigest() == \
        freeze["directions"]["fortran_raw_sha256_d0_only"]["D0_interface_offset"]
    sci = freeze["scientific_state"]
    assert (sci["float"], sci["dual_width"], sci["remeasure"], sci["poisson_tol"], sci["poisson_itmx"], sci["case_id"]) == ("Float32", 1, True, 1e-4, 32, "flow_24")
    assert freeze["runtime_pins"] == g2["runtime_pins"]


def test_declarations_prohibitions_horizon_and_flags(freeze):
    assert freeze["declarations"] == {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False}
    assert all(freeze["prohibitions"].values()) and set(freeze["qualification_flags"].values()) == {False}
    run = freeze["run"]
    assert run["directions"] == ["D0_interface_offset"] and run["horizon"]["min_steps"] == 1400 and run["horizon"]["min_t_u_l"] == 20.0
    assert run["snapshot_steps"] == [0, 2, 100, 500, 900, 1000, 1050, 1100, 1150, 1175, 1190, 1195, 1198, 1199]
    assert set(freeze["hypotheses"]) == {f"H{i}" for i in range(1, 7)} and set(freeze["decision_table"]) == {"A", "B", "C", "D", "E", "F", "unclassified"}
    assert freeze["case_priority"] == ["E", "D", "F", "A", "C", "B", "unclassified"]
    for k, v in freeze["analysis_constants"].items():
        assert getattr(A, k) == v, k


def test_kernel_identity_is_new_and_free(freeze):
    meta = freeze["kernel_identity"]
    assert meta["id"] == "ramhachi888/cfd-opt-sdf-grad-g2-d0-nonfinite-diag1" and meta["machine_shape"] == "NvidiaTeslaT4"
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag1"}
    assert meta["id"] not in used
    check = json.loads((E / "identity_free_check.json").read_text())
    assert check["all_free"] is True and check["intended_slugs"] == ["cfd-opt-sdf-grad-g2-d0-nonfinite-diag1"]


def test_runtime_source_hashes_match_the_installed_waterlily_when_available(freeze):
    try:
        local = B.runtime_source_hashes()
    except AssertionError:
        pytest.skip("WaterLily source not installed")
    assert local == freeze["runtime_source_hashes"]


# ---- CPU dry-run evidence (code-path only; not scientific data) -----------------------------------------------------------
DRY = E / "cpu_dryrun_diagnostic"


def stage_order(path):
    return [x["stage"] for x in json.loads((path / "stage_order.json").read_text())]


def test_dryrun_normal_run_is_bitwise_non_interfering_and_has_the_registered_stage_order(freeze):
    n = DRY / "normal"
    assert stage_order(n) == freeze["run"]["stage_order"]
    sc = json.loads((n / "selfcheck.json").read_text())
    assert sc["pass"] is True and sc["checksum_mismatch_steps"] == [] and sc["sha256_mismatch_steps"] == [] and sc["compared_steps"] >= 5
    index = json.loads((n / "diag_index.json").read_text())
    assert index["dryrun"] is True and index["status"] == "COMPLETE" and set(index["qualification_flags"].values()) == {False}
    rows = list(csv.DictReader((n / "stage_ledger.csv").open()))
    assert {r["stage"] for r in rows} >= set(freeze["run"]["stage_order"][:22])
    assert all(r["nonfinite_primal"] == "0" and r["nonfinite_tangent"] == "0" for r in rows)


def test_dryrun_injected_tangent_inf_is_localized_as_primal_finite_tangent_nonfinite(freeze):
    d = DRY / "inject_tangent_inf"
    fb = json.loads((d / "first_bad.json").read_text())
    assert (fb["step"], fb["stage"], fb["field"], fb["component"]) == (4, "project1_solve", "x", "tangent")
    assert fb["first_bad_element_class"].startswith("B_primal_finite_tangent_nonfinite") and fb["first_bad_index"]
    rows = A.load_ledger(d)
    bad = A.rederive_first_bad(rows)
    assert (bad["step"], bad["stage"], bad["field"]) == (4, "project1_solve", "x") and bad["np"] == 0 and bad["nt"] == 1
    last, first = A.last_finite_and_first_bad_stage(rows, bad)
    assert last[2] == "project1_rhs" and first[2] == "project1_solve"
    assert json.loads((d / "diag_index.json").read_text())["verdict"] == "DRYRUN_LOCALIZED"


def test_dryrun_deliberate_exception_keeps_partial_history_and_is_incomplete():
    d = DRY / "raise_exception"
    index = json.loads((d / "diag_index.json").read_text())
    assert index["verdict"] == "DIAG_INCOMPLETE" and index["status"] == "INCOMPLETE" and "deliberate dry-run exception at step 4" in index["instrumented"]["exception"]
    assert sorted({int(r["step"]) for r in csv.DictReader((d / "stage_ledger.csv").open())}) == [1, 2, 3]
    assert len(list(csv.DictReader((d / "force_ledger.csv").open()))) == 3 and len(list(csv.DictReader((d / "instrumented_checksums.csv").open()))) == 4
    assert not (d / "DONE").exists()
