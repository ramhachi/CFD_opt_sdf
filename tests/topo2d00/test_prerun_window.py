"""Parent-only engineering windows are calculated from authenticated histories."""
import csv
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import lfilter

from cfd_harness import campaign_schema as SC

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("topo2d_prerun_window", ROOT / "scripts/topo2d00/prerun_window.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def series(values, times=None):
    times = np.arange(len(values)) if times is None else times
    return [{"t_u_l": float(t), "downforce_n_per_m": float(v)} for t, v in zip(times, values)]


def independent_mean(rows, start, end):
    times = np.array([row["t_u_l"] for row in rows])
    values = np.array([row["downforce_n_per_m"] for row in rows])
    clipped = np.r_[start, times[(times > start) & (times < end)], end]
    return np.trapezoid(np.interp(clipped, times, values), clipped) / (end - start)


def test_constant_parent_has_zero_s0_and_shortest_registered_window():
    got = P.estimate(series(np.full(521, 2.0)))
    assert got["burn_in"] == 80
    assert got["mean_downforce"] == 2
    assert got["s0_point"] == 0
    assert got["window"] == [80, 130]
    assert got["window_width"] == 50
    assert got["units"] == {"downforce": "N/m", "time": "c1/U", "s0": "(N/m)^2*c1/U"}
    assert [row["start"] for row in got["burn_candidates"]] == list(range(0, 421, 50))
    assert got["flags"] == {"BURN_IN_FALLBACK": False, "WINDOW_CAPPED": False}
    assert got["formula"]["burn_candidate_origin"] == "first sample time"
    assert all(row["s0_point"] == 0 for row in got["spectral_estimates"])
    assert "s0_upper" not in got and "s0_upper_confidence" not in got["formula"]


def test_burn_in_excludes_transient_candidate_and_uses_subsequent_blocks():
    values = np.full(521, 2.0)
    values[:100] = 20.0
    got = P.estimate(series(values))
    assert got["burn_in"] == 100
    assert got["burn_candidates"][0]["accepted"] is False
    assert got["burn_candidates"][1]["accepted"] is False
    assert got["burn_candidates"][2]["accepted"] is True
    assert got["flags"]["BURN_IN_FALLBACK"] is False


def test_first_sample_after_step_one_is_the_candidate_origin_without_extrapolation():
    got = P.estimate(series(np.full(521, 2.0), 0.125 + np.arange(521)))
    assert got["burn_in"] == 80
    assert [row["start"] for row in got["burn_candidates"]] == pytest.approx(0.125 + np.arange(9) * 50)
    assert got["burn_candidates"][0]["accepted"] is True
    # The final complete 100 block has less than two complete 20 blocks left.
    assert got["burn_candidates"][-1]["accepted"] is False
    assert got["burn_candidates"][-1]["reason"] == "fewer than two remainder batches"
    assert got["flags"]["BURN_IN_FALLBACK"] is False


def test_known_batch_series_reproduces_point_s0_without_a_chi_squared_bound():
    values = 2 + 0.001 * np.sin(np.arange(521) * 1.234)
    got = P.estimate(series(values))
    estimates = []
    assert [row["block_length"] for row in got["spectral_estimates"]] == [10, 20, 40]
    for length in (10, 20, 40):
        boundaries = np.arange(got["burn_in"], 521, length)
        means = np.array([independent_mean(series(values), a, b) for a, b in zip(boundaries, boundaries[1:])])
        want = length * np.var(means, ddof=1)
        estimates.append(want)
        row = next(row for row in got["spectral_estimates"] if row["block_length"] == length)
        assert row["s0_point"] == pytest.approx(want, rel=1e-10, abs=1e-20)
        assert row["batch_count"] == len(means)
        assert "s0_upper" not in row
    assert got["s0_point"] == pytest.approx(max(estimates), rel=1e-10)


def test_burn_band_uses_twice_remainder_twenty_block_batch_means_se():
    values = np.where((np.arange(521) - 100) // 20 % 2 == 0, 1.0, 3.0)
    values[:100] = 2.2
    rows = series(values)
    got = P.estimate(rows)
    row = got["burn_candidates"][0]
    means = np.array([independent_mean(rows, start, start + 20) for start in range(100, 501, 20)])
    center = independent_mean(rows, 100, 520)
    se = np.std(means, ddof=1) / math.sqrt(len(means))
    delta = abs(independent_mean(rows, 0, 100) - center)
    assert se < delta < 2 * se  # Fails the superseded +/-1 SE criterion.
    assert row["remainder_mean"] == pytest.approx(center)
    assert row["remainder_se"] == pytest.approx(se)
    assert row["remainder_batch_count"] == len(means)
    assert row["accepted"] is True
    assert got["burn_in"] == 80


def test_no_qualifying_candidate_falls_back_and_large_window_is_clipped():
    got = P.estimate(series(2 + 0.01 * np.arange(521)))
    assert got["burn_in"] == 130
    assert not any(row["accepted"] for row in got["burn_candidates"])
    assert got["flags"] == {"BURN_IN_FALLBACK": True, "WINDOW_CAPPED": True}
    assert got["window_width"] == 400
    assert got["window"] == [130, 530]
    assert got["uncapped_window_width"] > 400


def test_piecewise_linear_endpoint_integration_at_non_sample_boundaries():
    times = np.r_[0.17 + np.arange(744) * 0.7, 520.44]
    rows = series(2 + 0.001 * np.sin(times), times)
    got = P.estimate(rows)
    assert got["mean_downforce"] == pytest.approx(independent_mean(rows, got["burn_in"], 520), rel=1e-13)
    for row in got["burn_candidates"]:
        if "mean" in row:
            assert row["mean"] == pytest.approx(independent_mean(rows, row["start"], row["start"] + 100), rel=1e-13)


@pytest.mark.parametrize("mutation", ["nonfinite", "reordered", "short", "zero_mean"])
def test_prerun_refuses_nonfinite_missing_or_zero_mean_inputs(mutation):
    rows = series(np.full(521, 2.0))
    if mutation == "nonfinite":
        rows[40]["downforce_n_per_m"] = float("nan")
    elif mutation == "reordered":
        rows[40], rows[41] = rows[41], rows[40]
    elif mutation == "short":
        rows.pop()
    elif mutation == "zero_mean":
        rows = series(np.zeros(521))
    with pytest.raises(ValueError):
        P.estimate(rows)


def ar1_experiment(true_window, *, seeds=200, tau=1.0, transient_fraction=0.0):
    """Review N2's stationary AR(1), using its exact discrete spectral density."""
    mean, dt, horizon = 0.17, 0.05, 520
    phi = math.exp(-dt / tau)
    s0 = true_window * (0.015 * mean) ** 2
    variance = s0 / (dt * (1 + phi) / (1 - phi))
    times = np.arange(round(horizon / dt) + 1) * dt
    windows, burns, rejections, fallbacks, caps = [], [], [], 0, 0
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        initial = rng.normal(scale=math.sqrt(variance))
        tail, _ = lfilter([1], [1, -phi], rng.normal(scale=math.sqrt(variance * (1 - phi ** 2)), size=len(times) - 1), zi=[phi * initial])
        values = mean + np.r_[initial, tail] + transient_fraction * mean * np.exp(-times / 20)
        try:
            got = P.estimate(series(values, times))
        except ValueError as exc:
            rejections.append({"seed": seed, "reason": str(exc)})
            continue
        windows.append(got["window_width"])
        burns.append(got["burn_in"])
        fallbacks += int(got["flags"]["BURN_IN_FALLBACK"])
        caps += int(got["flags"]["WINDOW_CAPPED"])
    return {"true_window": true_window, "true_s0": s0, "mean": mean, "tau": tau, "dt": dt,
            "horizon": horizon, "stationary_initial_sample": True, "transient_fraction": transient_fraction,
            "seeds": seeds, "rejections": rejections, "rejection_rate": len(rejections) / seeds,
            "median_window": float(np.median(windows)) if windows else None,
            "median_burn_in": float(np.median(burns)) if burns else None,
            "burn_in_fallback_count": fallbacks, "window_capped_count": caps, "windows": windows}


@pytest.mark.parametrize("true_window", [50, 100, 150])
def test_stationary_ar1_two_hundred_seeds_have_no_refusal_and_calibrated_median(true_window, record_property):
    result = ar1_experiment(true_window)
    record_property("ar1", json.dumps(result, sort_keys=True))
    assert result["rejection_rate"] == 0, result
    # registration amendment 7: W is rounded up to a multiple of 50 c1/U, so the calibration tolerance is one granularity step (prompt amendment 6, corrected 2026-11-07)
    assert true_window <= result["median_window"] <= true_window + 50, result


def write_parent_files(tmp_path):
    relative = "work/parent/forces.csv"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    dx = 0.2234 / 120
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SC.FORCE_COLUMNS)
        for i in range(521):
            drag, downforce = 1 / dx, 2 / dx
            writer.writerow([i, i, drag, 0, -downforce, drag, downforce, drag, 0, -downforce, 0, 0, 0])
    summary_path = tmp_path / "work/parent/summary.json"
    summary = {"topo2d": {"configuration": "E1", "height_mm": 100, "reynolds": 1000, "grid": "main", "phase": "0", "role": "prerun"},
               "observable": "total_cl", "force_unit": "N/m", "reference_chord_mm": 223.4,
               "h_over_c1": 100 / 223.4, "h_over_c": 100 / 380,
               "flow_dims": [840, 824], "solver_length": 120, "reynolds": 1000,
               "force_csv_sha256": SC.sha256_path(path), "scene_sha256": "a" * 64,
               "finite_u": True, "finite_p": True, "finite_forces": True,
               "phase_shift_m": [0, 0, 0], "top_factor": 1.0,
               "window_t_u_l": [80, 520], "t_end_reached": 520, "smoke": False,
               "runtime": {"memory": "CuArray"}, "source_sha256": {"example": "b" * 64}}
    summary_path.write_text(json.dumps(summary))
    return path, summary_path


def test_parent_record_is_written_once_and_recomputed_from_its_raw_series(tmp_path):
    path, summary = write_parent_files(tmp_path)
    target = tmp_path / "docs/harness/topo2d00_window_re1000.json"
    target.parent.mkdir(parents=True)
    record = P.write_record(path, summary, target, repo=tmp_path)
    assert record["schema"] == "topo2d-parent-window-v1"
    assert record["series_sha256"] == SC.sha256_path(path)
    assert record["burn_in"] == 80 and record["window"] == [80, 130]
    assert P.validate_record(target, repo=tmp_path) == record
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        P.write_record(path, summary, target, repo=tmp_path)
    assert target.read_bytes() == before
    forged = json.loads(before)
    forged["s0_point"] = 1
    target.write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="recomputed|differs"):
        P.validate_record(target, repo=tmp_path)


def test_record_rejects_manual_statistics_and_changed_source_series(tmp_path):
    path, summary = write_parent_files(tmp_path)
    target = tmp_path / "parent_window.json"
    P.write_record(path, summary, target, repo=tmp_path)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash"):
        P.validate_record(target, repo=tmp_path)
    target.write_text(json.dumps({"configuration": "E1", "mean_downforce": 2, "s0_point": 0, "burn_in": 80}))
    with pytest.raises(ValueError, match="schema|hand"):
        P.validate_record(target, repo=tmp_path)


@pytest.mark.parametrize("field,value", [("smoke", True), ("force_unit", "Cl"), ("observable", "pressure_cl"), ("window_t_u_l", [80, 400])])
def test_record_rejects_wrong_parent_measurement_contract(tmp_path, field, value):
    path, summary_path = write_parent_files(tmp_path)
    summary = SC.jload(summary_path)
    summary[field] = value
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        P.write_record(path, summary_path, tmp_path / "bad.json", repo=tmp_path)


def test_formal_context_reads_recomputed_parent_record_and_refuses_forged_statistics(tmp_path, monkeypatch):
    from cfd_harness import scene_campaign as S
    campaign = S.make_campaign()
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text(json.dumps(campaign))
    path, summary_path = write_parent_files(tmp_path)
    runtime = {"memory": "CuArray", "device_uuid": "GPU-synthetic"}
    parent_state = next(row for row in campaign["states"].values() if row["topo2d"]["role"] == "prerun" and row["topo2d"]["reynolds"] == 1000)
    pins = {relative: "b" * 64 for relative in S.source_paths("cuda", repo=tmp_path)}
    summary = SC.jload(summary_path)
    summary.update(runtime=runtime, source_sha256=pins, scene_sha256=parent_state["scene_sha256"])
    summary_path.write_text(json.dumps(summary))
    target = tmp_path / "parent_window.json"
    P.write_record(path, summary_path, target, repo=tmp_path)
    gate_path = tmp_path / "backend_gate.json"
    gate_path.write_text(json.dumps({"schema_version": 1, "status": "PASS", "failed_criteria": [], "incomplete_criteria": [],
                                     "gpu_identity": {"uuid": "GPU-synthetic"}, "criteria": {key: {"status": "PASS"} for key in ("C1", "C2", "C5", "C6")}}))
    freeze = {"kind": SC.FREEZE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_sha256": SC.sha256_path(campaign_path), "source_commit": "a" * 40,
              "scene_runner_approved": True, "runtime": {"re1000": {"backend": "WaterLily CUDA", "identity": runtime}}, "pins": {"re1000": pins},
              "backend_qualification": {"passed": True, "backend": "cuda", "device_uuid": "GPU-synthetic", "path": "backend_gate.json", "sha256": SC.sha256_path(gate_path)},
              "parent_window_records": {"re1000": {"path": "parent_window.json", "sha256": SC.sha256_path(target)}}}
    # Only external reviewed source/geometry/backend admission is synthetic;
    # raw CSV, summary, derived record, SHA and estimator checks run unchanged.
    monkeypatch.setattr(S, "scene_pins", lambda *args: pins)
    monkeypatch.setattr(S, "_scene_records", lambda *args: {"synthetic": {"sources": [{"verification": "VERIFIED_PDF"}]}})
    monkeypatch.setattr(S, "_window_estimator", lambda *args: {"validate_record": P.validate_record})
    assert S.formal_context(campaign, campaign_path, "re1000", freeze, repo=tmp_path) == [80, 130]
    # A parent can be measured before the derived record exists: this path
    # admits only its registered fixed horizon, never a manually selected W.
    assert S.formal_context(campaign, campaign_path, "re1000", {key: value for key, value in freeze.items() if key != "parent_window_records"}, repo=tmp_path, prerun=True) == [80, 520]
    forged = SC.jload(target)
    forged["mean_downforce"] = 3
    target.write_text(json.dumps(forged))
    freeze["parent_window_records"]["re1000"]["sha256"] = SC.sha256_path(target)
    with pytest.raises(ValueError, match="recomputed"):
        S.formal_context(campaign, campaign_path, "re1000", freeze, repo=tmp_path)
