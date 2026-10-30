import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs/evidence/candidate_c_w2a_sphere_cpu_criteria_2026_10_round4.json"
INHERITED = ROOT / "docs/evidence/sdf_native_w2a_sphere_cpu_criteria_2026_09.json"
RUNNER_PATH = ROOT / "scripts/run_waterlily_w2a_candidate_c_cpu_2026_10.py"
SPEC = importlib.util.spec_from_file_location("candidate_c_w2a_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


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
    assert current["round"] == 4
    assert current["execution"]["parent_source_review_required_before_measurement"] is True


def test_candidate_c_w2a_round3_discloses_evaluator_semantics_and_retention():
    current = _load(CRITERIA)
    recording = current["recording"]
    assert "trapezoid" in recording["window_statistics"]
    assert "bracketing" in recording["exact_window_brackets"]
    assert "differs from the legacy W2a arithmetic sample mean" in recording["window_statistics"]
    assert "terminal-FAIL.json" in current["execution"]["failure_retention"]
    assert current["supersedes_preexecution_draft"]["round"] == 3


def test_stationarity_uses_both_half_windows_and_fails_closed_on_zero_mean():
    ratio = RUNNER._stationarity_ratio(98.5, 101.5, 100.0)
    assert ratio == 0.03
    assert ratio > RUNNER.STATIONARITY_BOUND
    assert RUNNER._stationarity_ratio(1.0, 2.0, 0.0) == float("inf")
    assert RUNNER._stationarity_ratio(float("nan"), 1.0, 1.0) == float("inf")


def test_raw_csv_window_means_recompute_reported_values_and_detect_mismatch():
    rows = [
        {"t_ud": t, "drag_solver": t, "lift_solver": 2.0 * t, "side_solver": -t}
        for t in (39.0, 41.0, 49.0, 51.0, 59.0, 61.0)
    ]
    stats = RUNNER._raw_window_statistics(rows)
    assert stats == {
        "window_mean_drag": 50.0,
        "window_mean_lift": 100.0,
        "window_mean_side": -50.0,
        "first_half_mean_drag": 45.0,
        "second_half_mean_drag": 55.0,
    }
    assert RUNNER._summary_matches_raw(stats, stats)
    altered = dict(stats, window_mean_drag=50.01)
    assert not RUNNER._summary_matches_raw(altered, stats)


def test_lift_ratio_zero_drag_fails_closed():
    assert RUNNER._lift_ratio(0.0, 0.0) == float("inf")
    assert RUNNER._lift_ratio(1.0, 0.0) == float("inf")


def test_success_artifact_claims_and_paths_match_registered_criteria_schema():
    current = _load(CRITERIA)
    claims = RUNNER._qualification_claims(current)
    assert claims == current["claims_supported_if_all_gates_pass"]
    assert current["execution"]["output"].find("round4") >= 0
    assert current["provenance"]["source_manifest"] == current["inputs"]["source_manifest_path"]
    assert current["inputs"]["source_manifest_sha256"] == hashlib.sha256(
        (ROOT / current["inputs"]["source_manifest_path"]).read_bytes()
    ).hexdigest()


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
