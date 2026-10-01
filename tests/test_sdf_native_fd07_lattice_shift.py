"""FD-07 diagnostic: move the sampling lattice while holding the source fixed."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "fd07_prepare", ROOT / "scripts/sdf_native_fd07_lattice_shift_prepare.py"
)
prepare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prepare
spec.loader.exec_module(prepare)
genesis = sys.modules["sdf_native_genesis_v17_2026_09"]
import sdf_native_fd07_lattice_shift_analysis as analysis


def test_resampling_keeps_source_in_world_coordinates(monkeypatch):
    # An affine signed distance distinguishes xyz order and physical translation.
    normal = np.array([1.0, 2.0, 3.0]) / np.sqrt(14.0)
    monkeypatch.setattr(
        genesis, "signed_distance", lambda mesh, points: points @ normal - 0.14
    )
    shape = (4, 5, 6)
    origin = np.array([-0.1, -0.2, -0.3])
    shifted = origin + prepare.SPACING * np.asarray(prepare.SHIFT_FRACTION)
    phi = prepare.resample(None, shifted, prepare.SPACING, shape)
    indices = np.indices(shape).transpose(1, 2, 3, 0)
    world = shifted + prepare.SPACING * indices
    expected = (world @ normal - 0.14).astype(np.float32)
    np.testing.assert_array_equal(phi, expected)
    assert phi.shape == shape and phi.dtype == np.float32
    assert not np.array_equal(phi, prepare.resample(None, origin, prepare.SPACING, shape))


def test_shifted_design_box_preserves_clearance_and_refuses_crop():
    bounds = np.array([[-0.8, -0.6, -0.4], [1.8, 0.6, 0.4]])
    shifted = np.asarray(prepare.ORIGIN) + prepare.SPACING * np.asarray(prepare.SHIFT_FRACTION)
    clearance = prepare.validate_source_bounds(bounds, shifted, prepare.SHAPE, prepare.SPACING)
    assert clearance == pytest.approx(0.2 - prepare.SPACING * max(prepare.SHIFT_FRACTION))
    assert clearance >= 0.15
    for bad_bounds in (
        np.array([[-1.001, -0.6, -0.4], [1.8, 0.6, 0.4]]),
        np.array([[-0.95, -0.6, -0.4], [1.8, 0.6, 0.4]]),
        np.array([[-0.8, -0.6, -0.4], [2.1, 0.6, 0.4]]),
    ):
        with pytest.raises(ValueError):
            prepare.validate_source_bounds(bad_bounds, shifted, prepare.SHAPE, prepare.SPACING)


def test_preparation_refuses_existing_output_and_wrong_source_hash(tmp_path, monkeypatch):
    source = tmp_path / "source.stl"
    source.write_bytes(b"changed source")
    raw = tmp_path / "control.raw"
    raw.write_bytes(b"changed control")
    output = tmp_path / "diagnostic"
    output.mkdir()
    marker = output / "preserved.txt"
    marker.write_text("prior measurement")
    with pytest.raises(FileExistsError):
        prepare.prepare(source, raw, output)
    assert marker.read_text() == "prior measurement"
    fresh = tmp_path / "fresh"
    with pytest.raises(ValueError, match="source STL"):
        prepare.prepare(source, raw, fresh)
    assert not fresh.exists()
    monkeypatch.setattr(prepare, "SOURCE_SHA256", prepare.sha(source))
    with pytest.raises(ValueError, match="control raw phi"):
        prepare.prepare(source, raw, fresh)
    assert not fresh.exists()


def test_exact_window_mean_is_independent_of_affine_history_sampling():
    for times in ([1.8, 2.1, 2.2, 2.95, 3.05], [1.5, 2.0, 2.7, 3.0, 3.4]):
        values = [4 * time - 3 for time in times]
        assert analysis.window_mean(times, values) == pytest.approx(7.0)
    for times, values in (
        ([2.1, 2.7, 3.1], [1, 2, 3]),
        ([1.9, 2.7, 2.9], [1, 2, 3]),
        ([1.9, 2.7, 2.7, 3.1], [1, 2, 3, 4]),
        ([1.9, 2.7, 3.1], [1, float("nan"), 3]),
    ):
        with pytest.raises(ValueError):
            analysis.window_mean(times, values)


def test_summary_binds_histories_and_separates_odd_even_response(tmp_path):
    run_order = ["baseline", "noise_seed1@+1e-8", "noise_seed1@-1e-8", "noise_seed1@+1e-7", "noise_seed1@-1e-7"]
    plan = {"solver": {"analysis_window_u_l": [2, 3]}, "lattice_order": ["control", "shifted"],
            "run_order": run_order, "lattices": {}, "limitations": ["synthetic test"]}
    for name in ("runtime.txt", "noise_f8_fortran.raw", "initial_fields_and_realized_noise.csv"):
        (tmp_path / name).write_bytes(b"test")
    for lattice in plan["lattice_order"]:
        directory = tmp_path / lattice
        directory.mkdir()
        (directory / "phi.raw").write_bytes(lattice.encode())
        plan["lattices"][lattice] = {"raw_sha256": analysis.sha(directory / "phi.raw")}
        for run_id in run_order:
            delta = 0 if run_id == "baseline" else (5 if "+" in run_id else 1) * (10 if "1e-7" in run_id else 1)
            lines = ["t_u_l,drag_solver,downforce_solver"]
            lines += [f"{t},{900 * (t + delta)},{900 * (-t + delta)}" for t in (1.9, 2.15, 2.9, 3.1)]
            (directory / f"{run_id}.csv").write_text("\n".join(lines) + "\n")
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    result = analysis.summarize(tmp_path)
    control = result["lattices"]["control"]
    assert control["runs"]["baseline"]["window_mean_n"]["drag"] == pytest.approx(2.5)
    assert control["runs"]["baseline"]["window_mean_n"]["downforce"] == pytest.approx(-2.5)
    assert control["noise_pairs"]["1e-8"]["drag"] == pytest.approx({"odd_n": 2, "even_n": 3})
    assert control["signed_ratio_1e_minus7_over_1e_minus8"]["drag"] == pytest.approx({"odd_n": 10, "even_n": 10})
    assert result["input_sha256"]["control/baseline.csv"] == analysis.sha(tmp_path / "control/baseline.csv")
    assert result["flags"]["sdf_gradient_qualified"] is False
    with pytest.raises(FileExistsError):
        analysis.summarize(tmp_path)
