"""Focused tests for the immutable FD-07 causal diagnostic inputs and analysis."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prepare = load_script(
    "fd07_sign_consistency_prepare",
    "sdf_native_fd07_sign_consistency_prepare.py",
)
analysis = load_script(
    "fd07_sign_consistency_analysis",
    "sdf_native_fd07_sign_consistency_analysis.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_campaign(outdir: Path) -> Path:
    outdir.mkdir()
    raw_dir = outdir / "inputs/phi"
    raw_dir.mkdir(parents=True)
    raw_path = raw_dir / "baseline.raw"
    raw_path.write_bytes(b"canonical phi")
    control_path = outdir / "controls/fd07_fixed_face_scalar_ablation.csv"
    control_path.parent.mkdir(parents=True)
    control_path.write_text("synthetic fixed-face control\n")
    source_manifest = outdir / "repository_sources.sha256"
    source_manifest.write_text("")
    input_manifest = outdir / "input_files.sha256"
    input_manifest.write_text(
        f"{sha(control_path)}  controls/fd07_fixed_face_scalar_ablation.csv\n"
        f"{sha(raw_path)}  inputs/phi/baseline.raw\n"
        f"{sha(source_manifest)}  repository_sources.sha256\n"
    )
    noise = outdir / "realized_noise.csv"
    noise.write_text(
        "seed,sign,amplitude_m,noise_sha256,phi_sha256,changed_nodes,realized_rms_m,realized_max_abs_m\n"
    )
    body = outdir / "Body.jl"
    body.write_text("pinned fixture\n")
    phi_hashes = {"baseline": sha(raw_path)}
    cases = {"baseline": {"phi_file": "inputs/phi/baseline.raw", "phi_sha256": sha(raw_path)}}
    fixed_expected = {
        "A": {"seed1_plus_1e-8": (0.81831123, 54, 2.6e-7),
              "seed1_minus_1e-8": (0.81831123, 64, 2.7e-7)},
        "B": {"seed1_plus_1e-8": (2.5e-7, 0, 2.5e-7),
              "seed1_minus_1e-8": (2.6e-7, 0, 2.6e-7)},
        "C": {"seed1_plus_1e-8": (0.818310245, 10, 2.5e-7),
              "seed1_minus_1e-8": (0.818310335, 23, 2.5e-7)},
    }
    for seed in (1, 11, 2026):
        for amplitude in (1e-8, 1e-7):
            tag = f"{amplitude:.0e}"
            for sign in ("plus", "minus"):
                case_id = f"seed_{seed}_{sign}_{tag}"
                digest = hashlib.sha256(case_id.encode()).hexdigest()
                phi_hashes[case_id] = digest
                cases[case_id] = {"phi_sha256": digest}
    plan = {
        "solver": {"analysis_window_u_l": [2.0, 3.0], "force_conversion_n_per_solver_force": 1 / 900},
        "input_cases": cases,
        "input_files_manifest_sha256": sha(input_manifest),
        "realized_noise_csv_sha256": sha(noise),
        "source": {"repository_source_sha256": {},
                   "repository_sources_manifest_sha256": sha(source_manifest),
                   "waterlily_body_jl": str(body), "waterlily_body_jl_sha256": sha(body)},
        "perturbations": {"seeds": [1, 11, 2026], "amplitudes_m": [1e-8, 1e-7]},
        "fixed_face_control": {
            "source_csv": "synthetic prior table",
            "source_csv_sha256": sha(control_path),
            "copied_csv": "controls/fd07_fixed_face_scalar_ablation.csv",
            "maps": ["A", "B", "C"],
            "runs": ["baseline", "seed1_plus_1e-8", "seed1_minus_1e-8"],
            "fixed_face_count_per_run": 261,
            "recorded_mu0_rowwise_abs_tolerance": 5e-7,
            "corrected_face_distance_bitwise_equal": True,
            "max_delta_abs_tolerance": 5e-7,
            "expected_baseline_relative": {
                map_name: {
                    run_id: {
                        "corrected_max_abs_delta": vals[0],
                        "corrected_count_abs_delta_gt_1e-3": vals[1],
                        "uncorrected_max_abs_delta": vals[2],
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    }
                    for run_id, vals in runs.items()
                }
                for map_name, runs in fixed_expected.items()
            },
        },
        "primary_comparisons_fixed_before_force_inspection": {
            "thresholds": "descriptive only",
        },
        "limitations": ["synthetic unit test"],
        "flags": {"fd_qualified": False, "shape_update_allowed": False},
    }
    (outdir / "plan.json").write_text(json.dumps(plan, sort_keys=True))
    (outdir / "plan.sha256").write_text(sha(outdir / "plan.json") + "  plan.json\n")
    (outdir / "preflight.txt").write_text(
        "native_vs_diagnostic_upstream_exact=true\n"
        "moving_ground_native_vs_no_correction_exact=true\n"
        "fixed_face_scalar_control_pass=true\n"
    )
    with (outdir / "fixed_face_control.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "map", "run_id", "face_count", "corrected_max_abs_delta",
            "corrected_count_abs_delta_gt_1e-3", "uncorrected_max_abs_delta",
            "uncorrected_count_abs_delta_gt_1e-3", "recorded_mu0_max_abs_error",
            "corrected_face_bitwise_equal", "control_pass",
        ])
        for map_name in ("A", "B", "C"):
            writer.writerow([map_name, "baseline", 261, 0, 0, 0, 0, 0, "true", "true"])
            for run_id, (corrected_max, corrected_count, uncorrected_max) in fixed_expected[map_name].items():
                writer.writerow([map_name, run_id, 261, corrected_max, corrected_count,
                                 uncorrected_max, 0, 0, "true", "true"])
    (outdir / "runtime.txt").write_text("synthetic runtime\n")
    headers = [
        "arm", "case_id", "phi_sha256", "mu0_sha256", "mu1_sha256", "sigma_sha256",
        "flow_velocity_sha256", "branch_face_count", "sign_flip_face_count",
        "threshold_branch_changed_faces", "sign_flip_decision_changed_faces",
        "mu0_changed_vs_arm_baseline", "mu0_max_delta_vs_arm_baseline",
        "mu0_count_delta_gt_1e-3", "mu1_changed_vs_arm_baseline",
        "mu1_max_delta_vs_arm_baseline", "mu1_count_delta_gt_1e-3",
        "ab_mu0_max_delta", "ab_mu0_count_gt_1e-3", "ab_mu1_max_delta",
        "ab_mu1_count_gt_1e-3", "input_hashes",
    ]
    with (outdir / "initialization.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for case_id, phi_hash in phi_hashes.items():
            for arm in ("UPSTREAM", "NO_SIGN_CORRECTION"):
                writer.writerow({
                    "arm": arm, "case_id": case_id, "phi_sha256": phi_hash,
                    "mu0_sha256": f"{arm}-{case_id}-mu0",
                    "mu1_sha256": f"{arm}-{case_id}-mu1",
                    "sigma_sha256": f"{case_id}-sigma",
                    "flow_velocity_sha256": f"{case_id}-velocity",
                    "branch_face_count": 100, "sign_flip_face_count": 8,
                    "threshold_branch_changed_faces": 2,
                    "sign_flip_decision_changed_faces": 3,
                    "mu0_changed_vs_arm_baseline": 0,
                    "mu0_max_delta_vs_arm_baseline": 0,
                    "mu0_count_delta_gt_1e-3": 0,
                    "mu1_changed_vs_arm_baseline": 0,
                    "mu1_max_delta_vs_arm_baseline": 0,
                    "mu1_count_delta_gt_1e-3": 0,
                    "ab_mu0_max_delta": 0.8,
                    "ab_mu0_count_gt_1e-3": 5,
                    "ab_mu1_max_delta": 0.2,
                    "ab_mu1_count_gt_1e-3": 4,
                    "input_hashes": f"phi_sha256:{phi_hash};sigma_center_sha256:{case_id}-sigma;"
                                    f"raw_face_distance_sha256:{case_id}-distance;"
                                    f"raw_face_normal_sha256:{case_id}-normal;"
                                    f"raw_face_velocity_sha256:{case_id}-facevelocity;"
                                    f"initialized_velocity_sha256:{case_id}-velocity",
                })
    for arm in ("upstream", "no_sign_correction"):
        target = outdir / arm
        target.mkdir()
        for case_id in cases:
            seed = 1
            sign = 0
            amp_factor = 0.0
            if case_id != "baseline":
                _, seed_text, side, amp_tag = case_id.split("_")
                seed = int(seed_text)
                sign = 1 if side == "plus" else -1
                amp_factor = 1.0 if amp_tag == "1e-08" else 10.0
            delta = (seed / 3) * amp_factor * (sign + 0.25)
            arm_factor = 1.0 if arm == "upstream" else 0.5
            delta *= arm_factor
            pfx, vfx = 20 + delta / 2, 10 + delta / 2
            pfz, vfz = -8 + delta / 10, -4 + delta / 10
            lines = ["step,t_u_l,drag_solver,downforce_solver,pressure_fx_solver,pressure_fz_solver,viscous_fx_solver,viscous_fz_solver"]
            for idx, time in enumerate((1.8, 2.15, 2.55, 2.9, 3.2), start=1):
                lines.append(
                    f"{idx},{time},{pfx + vfx},{-(pfz + vfz)},{pfx},{pfz},{vfx},{vfz}"
                )
            (target / f"{case_id}.csv").write_text("\n".join(lines) + "\n")
    return outdir


def test_realized_perturbation_records_float32_effect():
    base = np.array([0.0, 0.125, -0.25], dtype=np.float32)
    noise = np.array([1.0, -2.0, 0.5], dtype=np.float64)
    plus, plus_stats = prepare.realize_perturbation(base, noise, 1e-8, 1)
    minus, minus_stats = prepare.realize_perturbation(base, noise, 1e-8, -1)
    assert plus.dtype == np.dtype("<f4")
    assert minus.dtype == np.dtype("<f4")
    assert plus_stats["changed_node_count"] == np.count_nonzero(plus != base)
    assert minus_stats["changed_node_count"] == np.count_nonzero(minus != base)
    assert plus_stats["realized_rms_m"] > 0
    assert minus_stats["realized_max_abs_m"] > 0
    with pytest.raises(ValueError, match="sign"):
        prepare.realize_perturbation(base, noise, 1e-8, 0)


def test_exact_window_trapezoid_interpolates_registered_endpoints():
    times = [1.8, 2.15, 2.55, 2.9, 3.2]
    values = [5 * t - 2 for t in times]
    assert analysis.exact_window_mean(times, values, 2, 3) == pytest.approx(10.5)
    with pytest.raises(ValueError, match="bracket"):
        analysis.exact_window_mean([2.1, 2.6, 3.2], [1, 2, 3], 2, 3)


def test_analysis_recomputes_force_splits_odd_even_and_arm_ratios(tmp_path):
    outdir = _synthetic_campaign(tmp_path / "campaign")
    result = analysis.analyze(outdir)
    assert len(result["runs"]["UPSTREAM"]) == 13
    assert len(result["paired_force_response"]["UPSTREAM"]) == 6
    assert result["runs"]["UPSTREAM"]["baseline"]["window_mean_n"]["drag"] == pytest.approx(30 / 900)
    assert result["runs"]["UPSTREAM"]["baseline"]["window_mean_n"]["downforce"] == pytest.approx(12 / 900)
    assert result["baseline_no_sign_minus_upstream_n"]["drag"] == pytest.approx(0)
    pair = result["no_sign_over_upstream_magnitude_ratios"]["seed_1@1e-08"]
    assert pair["drag"]["abs_delta_plus_b_over_a"] == pytest.approx(0.5)
    assert pair["pressure_fx"]["abs_odd_b_over_a"] == pytest.approx(0.5)
    assert pair["downforce"]["abs_even_b_over_a"] == pytest.approx(0.5)
    assert abs(result["runs"]["UPSTREAM"]["baseline"]["force_closure"]["window_drag_n"]) < 1e-14
    assert result["flags"]["fd_qualified"] is False
    with pytest.raises(FileExistsError):
        analysis.analyze(outdir)


def test_analysis_fails_closed_when_ab_body_map_inputs_differ(tmp_path):
    outdir = _synthetic_campaign(tmp_path / "campaign")
    path = outdir / "initialization.csv"
    content = path.read_text()
    content = content.replace("raw_face_distance_sha256:baseline-distance",
                              "raw_face_distance_sha256:changed-distance", 1)
    path.write_text(content)
    with pytest.raises(ValueError, match="raw body-map input hashes differ"):
        analysis.analyze(outdir)
