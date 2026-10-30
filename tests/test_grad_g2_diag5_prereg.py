"""G2-DIAG5 pre-registration: the freeze matches the files that will run, binds DIAG1-4, and the registered constants are consistent."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag5 as A
from scripts import build_grad_g2_diag5_freeze as B
from scripts import run_grad_g2_diag5_local as D

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09"
FREEZE_PATH = E / "prerun_freeze.json"
pytestmark = pytest.mark.skipif(not FREEZE_PATH.is_file(), reason="freeze not written yet")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def freeze():
    return json.loads(FREEZE_PATH.read_text())


def test_sidecar_and_every_frozen_file_hash(freeze):
    assert hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest() == (E / "prerun_freeze.json.sha256").read_text().strip()
    for name, path in B.FILES.items():
        assert freeze["file_hashes"][name] == sha(path), name


def test_driver_pins_agree_with_the_freeze(freeze):
    assert D.SOURCE_COMMIT == freeze["source_commit"] and len(D.SOURCE_COMMIT) == 40
    assert D.PINS == freeze["pins"]
    for rel, digest in freeze["pins"].items():
        assert D.sha256(ROOT / rel) == digest, rel


def test_stored_states_are_bound_to_the_diag1_snapshot_index(freeze):
    assert freeze["stored_state_sha256"] == B.stored_state_hashes() and len(freeze["stored_state_sha256"]) == 8
    assert freeze["file_hashes"]["snapshot_index"] == sha(D.SNAP_INDEX) and freeze["file_hashes"]["checksums"] == sha(D.CHECKSUMS)


def test_earlier_records_are_bound_and_unchanged(freeze):
    for key, base in (("diag1_evidence_sha256", B.D1E), ("diag2_evidence_sha256", B.D2E), ("diag3_evidence_sha256", B.D3E), ("diag4_evidence_sha256", B.D4E)):
        for rel, digest in freeze[key].items():
            assert hashlib.sha256((base / rel).read_bytes()).hexdigest() == digest, (key, rel)
    d1 = json.loads((B.D1E / "prerun_freeze.json").read_text())
    assert freeze["canonical_state"] == d1["canonical_state"] and freeze["candidate_c_identity"] == d1["candidate_c_identity"]
    assert freeze["directions"]["fortran_raw_sha256_d0_only"] == {"D0_interface_offset": D.D0_SHA} and freeze["prior_results"]["diag4"] == "FORCED32_DELAYED_ONSET"
    assert D.PHI_SHA == d1["canonical_state"]["phi_fortran_sha256"]


def test_registered_thresholds_equal_the_analyzer(freeze):
    for k, v in freeze["thresholds"].items():
        got = getattr(A, k)
        assert (list(got) if isinstance(got, tuple) else got) == v, k
    assert freeze["classification"] == ["R1_SELECTOR_CONVENTION", "R2_LINEARISATION_DEFECT", "R3_FINITE_INSTABILITY", "R4_INCONCLUSIVE", "DIAG5_INCOMPLETE"] and freeze["classification_priority"] == ["R2", "R3", "R1", "R4"]


def test_declarations_prohibitions_flags_and_design(freeze):
    assert freeze["declarations"]["selected_delta"] is None and freeze["declarations"]["grad03_verdict"] is None and freeze["declarations"]["float64_run"] is False
    assert freeze["declarations"]["e4_variants_are_surrogate_derivatives_not_the_derivative_of_the_implemented_map"] is True
    assert freeze["declarations"]["r4_is_a_bounded_no_go_of_the_current_programme_not_of_full_field_ad"] is True
    assert all(freeze["prohibitions"].values()) and set(freeze["qualification_flags"].values()) == {False}
    run = freeze["run"]
    assert run["states"] == ["S900", "S1000"] and run["k_steps"] == 40 and run["ensemble_n"] == 16 and run["box_1based"] == {"i": [1, 12], "j": [1, 8], "k": [49, 56]}
    assert run["eps_e3"] == [1e-6, 1e-5, 1e-4, 1e-3, 1e-2] and run["eps_e5"] == ["1e-5", "1e-4", "1e-3", "1e-2"] and run["tie_taus"] == [1e-5, 1e-4]
    assert "frozen-branch" in run["e4"]["baseline"] and "surrogate" not in run["e4"]["baseline"] and len(freeze["pre_freeze_disclosures"]) >= 5
    assert len(D.MATRIX) == 21 and set(run["groups"]) == {"E0", "E1", "E2", "E3", "E3C", "E5AD", "E5FD", "E6"}


def test_runtime_source_hashes_match_the_installed_waterlily_when_available(freeze):
    try:
        local = B.runtime_source_hashes()
    except AssertionError:
        pytest.skip("WaterLily source not installed")
    assert local == freeze["runtime_source_hashes"]


def test_dry_run_evidence_is_diagnostic_and_unregistered():
    base = E / "cpu_dryrun_diagnostic"
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        st = json.loads((d / "status.json").read_text())
        assert st["status"] == "COMPLETE" and st["dryrun"] is True and st["k_steps"] == 3 and set(st["qualification_flags"].values()) == {False}, d.name
        assert (d.name.startswith("R1188") and st["state"] == "R1188") or st["state"] == "S100"
    assert {p.name for p in base.iterdir() if p.is_dir()} == {"R1188_E0", "S100_E1", "S100_E2", "S100_E3", "S100_E3C", "S100_E5AD", "S100_E5FD_1e-3", "S100_E6"}
