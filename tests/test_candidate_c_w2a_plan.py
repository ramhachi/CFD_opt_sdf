import hashlib
import json
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs/evidence/candidate_c_w2a_sphere_cpu_criteria_2026_10_round2.json"
INHERITED = ROOT / "docs/evidence/sdf_native_w2a_sphere_cpu_criteria_2026_09.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_candidate_c_w2a_inherits_fixture_and_numeric_gates_exactly():
    current = _load(CRITERIA)
    prior = _load(INHERITED)

    assert current["fixture"] == prior["fixture"]
    gates = current["gates_registered_before_measurement"]
    assert "<= 0.02" in gates["G5_stationarity"]
    assert "<= 0.10" in gates["G6_candidate_c_vs_native"]
    assert "<=0.10" in gates["G7_lift_bound"]
    assert "<=1e-6" in gates["G8_reproducibility"]
    assert current["operator"]["normal_floor"] == 0.25
    assert current["operator"]["candidate_c_transition_width_solver_cells"] == 1.1444091796875e-4


def test_candidate_c_w2a_registration_is_pre_measurement_and_fail_closed():
    current = _load(CRITERIA)
    assert current["immutable"] is True
    assert current["registered_before_measurement"] is True
    assert current["measurement_started"] is False
    assert current["execution"]["parent_source_review_required_before_measurement"] is True
    assert all(value is False for value in current["flags"].values())
    assert current["round"] == 2
    assert current["execution"]["parent_source_review_required_before_measurement"] is True


def test_candidate_c_w2a_round2_discloses_evaluator_semantics_and_retention():
    current = _load(CRITERIA)
    recording = current["recording"]
    assert "trapezoid" in recording["window_statistics"]
    assert "bracketing" in recording["exact_window_brackets"]
    assert "differs from the legacy W2a arithmetic sample mean" in recording["window_statistics"]
    assert "terminal-FAIL.json" in current["execution"]["failure_retention"]
    assert current["supersedes_preexecution_draft"]["round"] == 1


def test_atomic_output_claim_uses_exclusive_mkdir_primitive(tmp_path: Path):
    claim = tmp_path / "run-001.claim"
    claim.mkdir()
    with pytest.raises(FileExistsError):
        claim.mkdir()


def test_candidate_c_w2a_source_manifest_and_criteria_hashes_resolve():
    current = _load(CRITERIA)
    criteria_bytes = CRITERIA.read_bytes()
    assert hashlib.sha256(criteria_bytes).hexdigest() == CRITERIA.with_suffix(".json.sha256").read_text().strip()
    manifest_path = ROOT / current["inputs"]["source_manifest_path"]
    manifest_bytes = manifest_path.read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == current["inputs"]["source_manifest_sha256"]
    for line in manifest_bytes.decode("utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
