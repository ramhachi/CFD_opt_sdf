"""Parent-only engineering windows are calculated from authenticated histories."""
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import chi2

from cfd_harness import campaign_schema as SC

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("topo2d_prerun_window", ROOT / "scripts/topo2d00/prerun_window.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def series(values):
    return [{"t_u_l": float(i), "downforce_n_per_m": float(v)} for i, v in enumerate(values)]


def test_constant_parent_has_zero_s0_and_shortest_registered_window():
    got = P.estimate(series(np.full(521, 2.0)))
    assert got["burn_in"] == 80
    assert got["mean_downforce"] == 2
    assert got["s0_upper"] == 0
    assert got["window"] == [80, 130]
    assert got["window_width"] == 50
    assert got["units"] == {"downforce": "N/m", "time": "c1/U", "s0": "(N/m)^2*c1/U"}
    assert got["formula"]["burn_candidate_starts"] == [0, 100, 200, 300]
    assert all(row["s0_upper"] == 0 for row in got["spectral_estimates"])


def test_burn_in_excludes_transient_candidate_and_uses_subsequent_blocks():
    values = np.full(521, 2.0)
    values[:100] = 20.0
    got = P.estimate(series(values))
    assert got["burn_in"] == 100
    assert got["burn_candidates"][0]["accepted"] is False
    assert got["burn_candidates"][1]["accepted"] is True


def test_missing_time_zero_sample_skips_candidate_without_extrapolation():
    got = P.estimate(series(np.full(521, 2.0))[1:])
    assert got["burn_in"] == 100
    assert got["burn_candidates"][0] == {"start": 0, "subsequent_count": 4, "accepted": False, "reason": "unbracketed candidate"}


def test_known_batch_series_reproduces_variance_and_chi_squared_upper_bound():
    # These piecewise-linear samples provide a known deterministic batch-mean
    # calculation independently of the estimator. An upper confidence bound is
    # an engineering estimate here, separate from the paired formal sigma_d.
    values = 2 + 0.001 * np.sin(np.arange(521) * 1.234)
    got = P.estimate(series(values))
    estimates = []
    for length in (5, 10, 20, 40, 80):
        boundaries = np.arange(got["burn_in"], 521, length)
        means = np.array([np.trapezoid(values[a:b + 1], dx=1) / length for a, b in zip(boundaries, boundaries[1:])])
        want = length * np.var(means, ddof=1) * (len(means) - 1) / chi2.ppf(0.1, len(means) - 1)
        estimates.append(want)
        row = next(row for row in got["spectral_estimates"] if row["block_length"] == length)
        assert row["s0_upper"] == pytest.approx(want, rel=1e-10, abs=1e-20)
        assert row["batch_count"] == len(means)
    assert got["s0_upper"] == pytest.approx(max(estimates), rel=1e-10)


@pytest.mark.parametrize("mutation", ["nonfinite", "reordered", "short", "zero_mean", "no_plateau", "cap"])
def test_prerun_refuses_nonfinite_missing_nonstationary_or_uncapped_window(mutation):
    rows = series(np.full(521, 2.0))
    if mutation == "nonfinite":
        rows[40]["downforce_n_per_m"] = float("nan")
    elif mutation == "reordered":
        rows[40], rows[41] = rows[41], rows[40]
    elif mutation == "short":
        rows.pop()
    elif mutation == "zero_mean":
        rows = series(np.zeros(521))
    elif mutation == "no_plateau":
        rows = series(np.arange(521))
    elif mutation == "cap":
        rows = series(2 + 100 * np.sin(np.arange(521) * 1.234))
    with pytest.raises(ValueError):
        P.estimate(rows)


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
    forged["s0_upper"] = 1
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
    target.write_text(json.dumps({"configuration": "E1", "mean_downforce": 2, "s0_upper": 0, "burn_in": 80}))
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
