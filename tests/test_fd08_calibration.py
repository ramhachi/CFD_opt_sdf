from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cfd_sdf.fd08_calibration import (
    FORMAL_DIRECTION_IDS,
    aggregate_formal_verdict,
    audit_float32_centered_pair,
    classify_calibration_screen,
    clipped_time_mean_from_rows,
    derive_response_floor,
    evaluate_formal_direction_response,
    inspect_runner_state_gates,
    select_formal_epsilon_ladder,
    validate_calibration_ladder,
    validate_formal_epsilon_ladder,
    verify_force_component_semantics,
    verify_output_manifest,
    verify_registered_dataset,
    verify_runner_state_gates,
    verify_cross_kernel_runtime,
    verify_runtime_artifacts,
)
from verify_fd08_formal import verify_source_inputs
from preflight_fd08_cpu import (
    audit_cpu_force_history,
    parse_cpu_completion_marker,
    resolve_output_directory,
    verify_preview_dataset,
)
from register_fd08_calibration import write_cpu_preview


def _calibration_rows(epsilons: tuple[float, ...], slope: float) -> list[dict]:
    return [{"epsilon_m": eps, "centered_response_n": slope * eps,
             "centered_slope_n_per_m": slope, "sign": 1}
            for eps in epsilons]


def test_exact_endpoint_clipping_recomputes_linear_force_mean():
    rows = [{"t_u_l": t, "drag_solver": 2 * t, "downforce_solver": -3 * t,
             "step": t, "fx_solver": 2 * t, "fy_solver": 0, "fz_solver": 3 * t,
             "pressure_fx_solver": t, "pressure_fy_solver": 0, "pressure_fz_solver": 0,
             "viscous_fx_solver": t, "viscous_fy_solver": 0, "viscous_fz_solver": 3 * t}
            for t in (79.0, 91.0, 113.0, 121.0)]
    assert clipped_time_mean_from_rows(rows, "drag_solver") == pytest.approx(200.0)
    assert clipped_time_mean_from_rows(rows, "downforce_solver") == pytest.approx(-300.0)


def test_response_floor_uses_exactly_five_repeats_and_positive_guard():
    exact = derive_response_floor([0.3] * 5)
    assert exact["repeat_count"] == 5
    assert exact["span_n"] == 0.0
    assert exact["response_floor_n"] == pytest.approx(1e-8)
    varied = derive_response_floor([0.3, 0.3001, 0.3, 0.2999, 0.3])
    assert varied["response_floor_n"] == pytest.approx(0.0002)
    with pytest.raises(ValueError, match="exactly 5"):
        derive_response_floor([0.3] * 4)


def test_calibration_epsilon_ladder_requires_broad_unique_positive_range():
    ladder = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)
    assert validate_calibration_ladder(ladder) == ladder
    with pytest.raises(ValueError, match="span at least"):
        validate_calibration_ladder((1e-3, 2e-3, 3e-3, 4e-3, 5e-3, 6e-3, 1e-2))
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_calibration_ladder((1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 3e-2))


def test_formal_epsilon_ladder_is_exactly_five_selected_points():
    ladder = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2)
    assert validate_formal_epsilon_ladder(ladder) == ladder
    with pytest.raises(ValueError, match="exactly 5"):
        validate_formal_epsilon_ladder((*ladder, 3e-2))
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_formal_epsilon_ladder((1e-4, 1e-3, 3e-4, 3e-3, 1e-2))


def test_runner_output_manifest_checks_full_inventory_and_file_bytes(tmp_path: Path):
    root = tmp_path / "output"
    root.mkdir()
    terminal = root / "result.json"
    terminal.write_text('{"status":"complete"}\n')
    digest = hashlib.sha256(terminal.read_bytes()).hexdigest()
    (root / "sha256.json").write_text(json.dumps({"result.json": digest}))
    (root / "DONE").write_text(json.dumps({
        "status": "FINISHED_STATE_LOOP", "status_counts": {"COMPLETED": 1},
    }) + "\n")
    verified = verify_output_manifest(root, terminal)
    assert verified["verified_file_count"] == 1
    terminal.write_text("tampered\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_output_manifest(root, terminal)
    (root / "DONE").unlink()
    with pytest.raises(ValueError, match="DONE marker"):
        verify_output_manifest(root, terminal)


def test_registered_dataset_verifies_exact_staged_payload(tmp_path: Path):
    root = tmp_path / "dataset"
    root.mkdir()
    payload = root / "baseline.raw"
    payload.write_bytes(b"phi")
    criteria_bytes = b'{"immutable":true}\n'
    criteria_sha = hashlib.sha256(criteria_bytes).hexdigest()
    (root / "xfidc_criteria.json").write_bytes(criteria_bytes)
    (root / "xfidc_criteria.json.sha256").write_text(criteria_sha + "\n")
    (root / "dataset-metadata.json").write_text("{}\n")
    criteria = {"dataset_files": {"baseline.raw": hashlib.sha256(b"phi").hexdigest()}}
    assert verify_registered_dataset(criteria, criteria_sha, root)["verified_file_count"] == 1
    payload.write_bytes(b"changed")
    with pytest.raises(ValueError, match="file SHA-256 mismatch"):
        verify_registered_dataset(criteria, criteria_sha, root)


def test_unregistered_builder_preview_is_hash_bound_and_cannot_look_registered(tmp_path: Path):
    flags = {key: False for key in (
        "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
    epsilons = [5e-5, 1.5e-4, 5e-4, 1.5e-3, 5e-3, 1.5e-2, 5e-2]
    directions = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
    states = [
        {"name": f"cal_baseline_{index:02d}", "role": "baseline",
         "phi_fortran_sha256": f"base-{index}"}
        for index in range(1, 6)
    ]
    for direction in directions:
        for epsilon in epsilons:
            for sign in (-1, 1):
                states.append({
                    "name": f"{direction}__{epsilon:g}__{sign:+d}", "role": "perturbation",
                    "direction_id": direction, "epsilon_m": epsilon, "sign": sign,
                    "phi_fortran_sha256": f"{direction}-{epsilon}-{sign}",
                })
    criteria = {
        "source_commit": "a" * 40, "candidate_c_identity": {"identity": "frozen"},
        "qualification_flags": flags, "geometry": {}, "case": {}, "measurement": {},
        "backend": {}, "calibration_epsilon_ladder_m": epsilons,
        "state_order": states, "source_inputs": {},
    }
    preview_dir = tmp_path / "preview"
    staged_data = {f"states/{row['name']}.raw": row["name"].encode() for row in states}
    result = write_cpu_preview(criteria, staged_data, preview_dir)
    preview_path = Path(result["preview_path"])
    preview = json.loads(preview_path.read_text())
    audit = verify_preview_dataset(preview, result["preview_sha256"], preview_dir)
    assert preview["immutable"] is False
    assert preview["registered_before_computation"] is False
    assert preview["criteria_registered"] is False
    assert audit["verified_file_count"] == 47
    assert not (preview_dir / "xfidc_criteria.json").exists()
    (preview_dir / "xfidc_criteria.json").write_text("{}\n")
    with pytest.raises(ValueError, match="inventory differs"):
        verify_preview_dataset(preview, result["preview_sha256"], preview_dir)


def test_host_raw_force_audit_checks_body_sign_and_stationarity(tmp_path: Path):
    import csv

    path = tmp_path / "forces.csv"
    fields = ("step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver",
              "downforce_solver", "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver",
              "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver")
    rows = []
    for step, t in enumerate((79.0, 85.0, 95.0, 105.0, 115.0, 121.0)):
        fx, fy, fz = 2.0 + 0.01 * t, 0.0, -3.0 - 0.02 * t
        rows.append({
            "step": step, "t_u_l": t, "fx_solver": fx, "fy_solver": fy, "fz_solver": fz,
            "drag_solver": fx, "downforce_solver": -fz,
            "pressure_fx_solver": 0.4 * fx, "pressure_fy_solver": 0.0,
            "pressure_fz_solver": fz, "viscous_fx_solver": 0.6 * fx,
            "viscous_fy_solver": 0.0, "viscous_fz_solver": 0.0,
        })
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    from cfd_sdf.fd08_calibration import recompute_force_history

    audit = recompute_force_history(path, force_component_tolerances=(1e-6, 1e-8))
    assert audit["force_component_audit"]["verified"] is True
    assert audit["force_component_audit"]["row_count"] == len(rows)
    assert set(audit["stationarity_relative_half_window_drift"]) == {"drag", "downforce"}
    bad = [dict(row) for row in rows]
    bad[2]["downforce_solver"] *= -1
    with pytest.raises(ValueError, match="force-on-body"):
        verify_force_component_semantics(bad, relative_tolerance=1e-6, absolute_tolerance=1e-8)


def test_cpu_rehearsal_history_uses_production_host_parser(tmp_path: Path):
    import csv

    path = tmp_path / "cpu.forces.csv"
    rows = [
        {"step": 0, "t_u_l": 0.0, "fx_solver": 2.0, "fy_solver": 0.0,
         "fz_solver": -3.0, "drag_solver": 2.0, "downforce_solver": 3.0,
         "pressure_fx_solver": 0.5, "pressure_fy_solver": 0.0,
         "pressure_fz_solver": -1.0, "viscous_fx_solver": 1.5,
         "viscous_fy_solver": 0.0, "viscous_fz_solver": -2.0},
        {"step": 1, "t_u_l": 0.25, "fx_solver": 2.2, "fy_solver": 0.0,
         "fz_solver": -3.2, "drag_solver": 2.2, "downforce_solver": 3.2,
         "pressure_fx_solver": 0.55, "pressure_fy_solver": 0.0,
         "pressure_fz_solver": -1.1, "viscous_fx_solver": 1.65,
         "viscous_fy_solver": 0.0, "viscous_fz_solver": -2.1},
    ]
    fields = tuple(rows[0])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = audit_cpu_force_history(
        path, force_scale=1 / 900, component_tolerances=(1e-6, 1e-8),
    )
    assert result["row_count"] == 2
    assert result["window_t_u_l"] == [0.0, 0.25]
    assert result["force_component_audit"]["verified"] is True
    assert result["force_n"]["drag"] == pytest.approx(2.1 / 900)
    rows[1]["step"] = 2
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="initial and one-step endpoints"):
        audit_cpu_force_history(
            path, force_scale=1 / 900, component_tolerances=(1e-6, 1e-8),
        )


def test_cpu_rehearsal_resolves_repo_relative_output_before_running_solver(tmp_path: Path):
    from preflight_fd08_cpu import ROOT

    assert resolve_output_directory(Path("docs/evidence/cpu_rehearsal")) == (
        ROOT / "docs/evidence/cpu_rehearsal"
    ).resolve()
    with pytest.raises(ValueError, match="inside the repository"):
        resolve_output_directory(tmp_path / "outside")


def test_cpu_rehearsal_terminal_marker_binds_inputs_runtime_and_raw_history():
    invoked = "FD08_CPU_REHEARSAL_STEP_INVOKED run_id=baseline"
    line = (
        "FD08_CPU_REHEARSAL_DONE run_id=baseline phi_fortran_sha256=phi-sha "
        "margin_m=0.15 julia=1.12.6 waterlily=1.8.0 backend=Array "
        "steps=1 force_rows=2 csv_sha256=csv-sha qualification=false"
    )
    result = parse_cpu_completion_marker(
        f"{invoked}\n{line}", run_id="baseline", phi_sha256="phi-sha", force_csv_sha256="csv-sha",
        margin_gate_m=0.15, margin_tolerance_m=1e-6,
    )
    assert result["julia_version"] == "1.12.6"
    assert result["waterlily_version"] == "1.8.0"
    assert result["backend"] == "Array"
    assert result["solver_steps"] == 1 and result["force_row_count"] == 2
    with pytest.raises(ValueError, match="input or force-history identity"):
        parse_cpu_completion_marker(
            f"{invoked}\n{line}", run_id="baseline", phi_sha256="wrong", force_csv_sha256="csv-sha",
            margin_gate_m=0.15, margin_tolerance_m=1e-6,
        )


def test_runner_state_verification_rejects_missing_gate_or_truthy_non_boolean():
    from cfd_sdf.fd08_calibration import RUNNER_STATE_GATES

    complete = {key: True for key in RUNNER_STATE_GATES}
    assert verify_runner_state_gates({"status": "COMPLETED", "gates": complete}, "run-1") == complete
    with pytest.raises(ValueError, match="failed/missing gate"):
        verify_runner_state_gates({"status": "COMPLETED", "gates": {"vram": True}}, "run-2")
    complete["stationarity"] = 1
    with pytest.raises(ValueError, match="failed/missing gate"):
        verify_runner_state_gates({"status": "COMPLETED", "gates": complete}, "run-3")


def test_runner_gate_failure_is_preserved_as_a_gate_failure_not_an_exception():
    from cfd_sdf.fd08_calibration import RUNNER_STATE_GATES

    gates = {key: True for key in RUNNER_STATE_GATES}
    gates["finite"] = False
    assert inspect_runner_state_gates(
        {"status": "GATE_FAILED", "gates": gates}, "run-failed") == gates
    with pytest.raises(ValueError, match="failed registered gate"):
        verify_runner_state_gates({"status": "GATE_FAILED", "gates": gates}, "run-failed")
    with pytest.raises(ValueError, match="status does not match"):
        inspect_runner_state_gates({"status": "COMPLETED", "gates": gates}, "run-wrong")


def test_kaggle_runtime_audit_gates_pinned_stack_but_only_records_os_driver(tmp_path: Path):
    backend = {
        "gpu_count": 2, "gpu_name": "Tesla T4", "compute_capability": "7.5.0",
        "cuda_driver_api_version": "13.3.0", "cuda_runtime_version": "12.8.0",
        "julia_version": "1.12.6", "cuda_jl_version": "6.3.1", "waterlily_version": "1.8.0",
    }
    (tmp_path / "nvidia_smi.csv").write_text(
        "0, Tesla T4, GPU-one, 15360 MiB, 580.178.04\n"
        "1, Tesla T4, GPU-two, 15360 MiB, 580.178.04\n"
    )
    markers = (
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
        "CUDA_DRIVER_VERSION 13.3.0", "CUDA_RUNTIME_VERSION 12.8.0",
        "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1", "WATERLILY_VERSION 1.8.0",
        "GPU_NAME Tesla T4", "NO_SOLVER_STEP",
    )
    (tmp_path / "julia_smoke.log").write_text("\n".join(markers) + "\n")
    audit = verify_runtime_artifacts(tmp_path, backend)
    assert audit["selected_gpu_uuid"] == "GPU-one"
    assert audit["driver_version_recorded_not_gated"] == "580.178.04"
    assert "not a cross-kernel equality gate" in audit["gpu_uuid_policy"]
    (tmp_path / "julia_smoke.log").write_text("CUDA_FUNCTIONAL true\n")
    with pytest.raises(ValueError, match="runtime does not match"):
        verify_runtime_artifacts(tmp_path, backend)


def test_cross_kernel_runtime_records_but_does_not_gate_uuid_or_os_driver():
    calibration = {
        "julia_version": "1.12.6", "waterlily_version": "1.8.0",
        "cuda_jl_version": "6.3.1", "gpu_name": "Tesla T4",
        "gpu_uuid": "GPU-first", "driver_version": "580.178.04",
    }
    fresh_kernel = {**calibration, "gpu_uuid": "GPU-second", "driver_version": "590.1"}
    assert verify_cross_kernel_runtime(fresh_kernel, calibration) == (
        "julia_version", "waterlily_version", "cuda_jl_version", "gpu_name",
    )
    fresh_kernel["waterlily_version"] = "1.9.0"
    with pytest.raises(ValueError, match="waterlily_version"):
        verify_cross_kernel_runtime(fresh_kernel, calibration)


def test_float32_direction_audit_reports_realized_pair_and_rejects_rounding_error():
    base = np.array([0.25, -0.5, 1.0], dtype=np.float32)
    direction = np.array([1.0, 0.0, -1.0])
    eps = 1e-2
    plus = np.asarray(base.astype(np.float64) + eps * direction, dtype=np.float32)
    minus = np.asarray(base.astype(np.float64) - eps * direction, dtype=np.float32)
    result = audit_float32_centered_pair(base, direction, epsilon_m=eps,
                                         phi_plus=plus, phi_minus=minus)
    assert result["changed_node_count_plus"] == 2
    assert result["changed_node_count_minus"] == 2
    assert result["direction_gate_passed"] is True
    with pytest.raises(ValueError, match="Float32"):
        audit_float32_centered_pair(base, direction, epsilon_m=1e-8,
                                    phi_plus=base.copy(), phi_minus=base.copy())


def test_calibration_selection_is_common_smallest_contiguous_five_for_all_six():
    eps = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)
    pairs = {direction: {response: _calibration_rows(eps, 0.01)
                         for response in ("drag", "downforce")}
             for direction in ("D0", "D1", "D2")}
    result = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n={"drag": 1e-8, "downforce": 1e-8})
    assert result["status"] == "COMMON_PLATEAU_FOUND"
    assert result["selected_formal_epsilon_ladder_m"] == list(eps[:5])
    pairs["D2"]["drag"] = _calibration_rows(eps, 0.01)
    pairs["D2"]["drag"][0]["centered_slope_n_per_m"] = 0.012
    pairs["D2"]["drag"][0]["centered_response_n"] = 0.012 * eps[0]
    result = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n={"drag": 1e-8, "downforce": 1e-8})
    assert result["status"] == "COMMON_PLATEAU_FOUND"
    assert result["selected_formal_epsilon_ladder_m"] == list(eps[1:6])


def test_formal_verdict_gives_resolved_failure_precedence_over_subfloor_rows():
    rows = [{"epsilon_m": eps, "response_plus_n": 0.01 * eps, "response_minus_n": -0.01 * eps}
            for eps in (1e-4, 3e-4, 1e-3, 3e-3, 1e-2)]
    rows[0] = {"epsilon_m": 1e-4, "response_plus_n": 1e-12, "response_minus_n": -1e-12}
    rows[3] = {"epsilon_m": 3e-3, "response_plus_n": 0.014 * 3e-3,
               "response_minus_n": -0.014 * 3e-3}
    result = evaluate_formal_direction_response(rows, response_floor_n=1e-8)
    assert result["verdict"] == "FAIL"
    assert "resolved_plateau_failure" in result["failure_gates"]
    rows = [{"epsilon_m": eps, "response_plus_n": 0.01 * eps, "response_minus_n": -0.01 * eps}
            for eps in (1e-4, 3e-4, 1e-3, 3e-3, 1e-2)]
    rows[0] = {"epsilon_m": 1e-4, "response_plus_n": 1e-12, "response_minus_n": -1e-12}
    assert evaluate_formal_direction_response(rows, response_floor_n=1e-8)["verdict"] == "UNRESOLVED"


def test_calibration_screen_preserves_fail_precedence_and_unresolved_only():
    eps = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)
    floors = {"drag": 1e-8, "downforce": 1e-8}

    def series(slopes):
        return [{
            "epsilon_m": epsilon,
            "centered_response_n": slope * epsilon,
            "centered_slope_n_per_m": slope,
            "sign": 1 if slope > 0 else -1 if slope < 0 else 0,
            "response_plus_n": 1.0 + slope * epsilon,
            "response_minus_n": 1.0 - slope * epsilon,
        } for epsilon, slope in zip(eps, slopes)]

    pairs = {direction: {response: series([1.0] * len(eps))
                         for response in ("drag", "downforce")}
             for direction in ("D0", "D1", "D2")}
    selection = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n=floors)
    assert classify_calibration_screen(
        epsilons_m=eps, pairs=pairs, response_floors_n=floors,
        selection=selection)["verdict"] == "PASS"

    pairs["D0"]["drag"] = series([1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0])
    selection = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n=floors)
    failed = classify_calibration_screen(
        epsilons_m=eps, pairs=pairs, response_floors_n=floors,
        selection=selection)
    assert selection["registration_allowed"] is False
    assert failed["verdict"] == "FAIL"
    assert failed["resolved_failure_windows"]

    pairs["D0"]["drag"] = series([0.0] * len(eps))
    selection = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n=floors)
    unresolved = classify_calibration_screen(
        epsilons_m=eps, pairs=pairs, response_floors_n=floors,
        selection=selection)
    assert unresolved["verdict"] == "UNRESOLVED"
    assert unresolved["resolved_failure_windows"] == []


def test_formal_aggregate_requires_six_cells_and_fails_before_unresolved():
    values = {f"{d}/{r}": {"verdict": "PASS"}
              for d in FORMAL_DIRECTION_IDS for r in ("drag", "downforce")}
    values[f"{FORMAL_DIRECTION_IDS[1]}/drag"] = {"verdict": "UNRESOLVED"}
    values[f"{FORMAL_DIRECTION_IDS[2]}/downforce"] = {"verdict": "FAIL"}
    result = aggregate_formal_verdict(values)
    assert result["verdict"] == "FAIL"
    assert result["qualification_flags"]["fd_oracle"] is False
    with pytest.raises(ValueError, match="six registered"):
        aggregate_formal_verdict({f"{FORMAL_DIRECTION_IDS[0]}/drag": {"verdict": "PASS"}})


def test_formal_integrity_failure_fails_before_unresolved_response():
    values = {f"{direction}/{response}": {"verdict": "PASS"}
              for direction in FORMAL_DIRECTION_IDS for response in ("drag", "downforce")}
    values[f"{FORMAL_DIRECTION_IDS[1]}/drag"] = {"verdict": "UNRESOLVED"}
    result = aggregate_formal_verdict(
        values, integrity_failures=[{"run_id": "D1", "gate": "body_and_backend"}],
    )
    assert result["verdict"] == "FAIL"
    assert result["unresolved_count"] == 1
    assert result["integrity_failure_count"] == 1


def test_fd08_t4_runner_reuses_registered_xfid_runner_byte_for_byte():
    repo = Path(__file__).resolve().parents[1]
    calibration = (repo / "infra/kaggle/kernel_fd08_calibration/runner_base.py").read_text()
    formal = (repo / "infra/kaggle/kernel_fd08_formal/runner_base.py").read_text()
    xfid = (repo / "infra/kaggle/kernel_xfid_candidate_c/runner.py").read_text()
    assert calibration == formal
    assert calibration == xfid


def test_runner_stationarity_is_reported_without_becoming_a_completion_gate(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    path = repo / "infra/kaggle/kernel_fd08_calibration/runner_base.py"
    spec = importlib.util.spec_from_file_location("fd08_runner_gate_test", path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    outdir = tmp_path / "runner_output"
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "flow_24.forces.csv"
    csv_path.write_text("runner test input\n")
    summary = {
        "force_csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "finite_u": True, "finite_p": True, "finite_forces": True,
        "t_end_reached": 120.0, "state_sha256": "state", "phi_fortran_sha256": "phi",
        "device_roundtrip_sha256": "phi", "force_integration_body": "body",
        "waterlily_version": "1.8.0", "cuda_jl_version": "6.3.1", "julia_version": "1.12.6",
        "gpu_name": "Tesla T4", "peak_vram_bytes": 10, "vram_total_bytes": 20,
    }
    (outdir / "flow_24.summary.json").write_text(json.dumps(summary))
    metrics = {
        "stationarity_relative_half_window_drift_drag": 0.03,
        "stationarity_relative_half_window_drift_downforce": 0.01,
        "drag_time_weighted_n": 1.0, "downforce_time_weighted_n": 2.0,
        "pressure_drag_time_weighted_n": 0.5, "viscous_drag_time_weighted_n": 0.5,
        "pressure_downforce_time_weighted_n": 1.0, "viscous_downforce_time_weighted_n": 1.0,
        "cd_time_weighted": 0.1,
    }
    monkeypatch.setattr(runner, "parse_force_csv", lambda _: [])
    monkeypatch.setattr(runner, "recompute_case_metrics", lambda *_: metrics)
    monkeypatch.setattr(runner, "force_components_close", lambda *_: True)
    monkeypatch.setattr(runner, "close_summary", lambda *_: True)
    measurement = {
        "host_recompute_relative_tolerance": 1e-9,
        "stationarity": {"relative_half_window_drift_max": 0.02},
        "force_component_relative_tolerance": 1e-6,
        "force_component_absolute_tolerance": 1e-8,
        "target_t_u_l": 120.0,
        "force_integration_body": "body",
    }
    criteria = {
        "measurement": measurement, "case": {}, "backend": {
            "waterlily_version": "1.8.0", "cuda_jl_version": "6.3.1", "julia_version": "1.12.6",
            "gpu_name": "Tesla T4",
        },
    }
    state = {"state_sha256": "state", "phi_fortran_sha256": "phi"}
    diagnostic = runner.evaluate_state("unstable", state, criteria, outdir, "W4_SOLVER_STEP_INVOKED flow_24\nW4_SOLVER_STEP_RETURNED flow_24\n", 0.2)
    assert diagnostic["status"] == "COMPLETED"
    assert diagnostic["stationarity_drift_max"] == 0.03
    assert diagnostic["stationarity_within_registered_limit"] is False
    metrics["stationarity_relative_half_window_drift_drag"] = 0.019
    passed = runner.evaluate_state("stable", state, criteria, outdir, "W4_SOLVER_STEP_INVOKED flow_24\nW4_SOLVER_STEP_RETURNED flow_24\n", 0.2)
    assert passed["status"] == "COMPLETED"
    assert passed["stationarity_within_registered_limit"] is True


def test_formal_verifier_checks_criteria_bound_source_hashes(tmp_path: Path):
    source = tmp_path / "scripts" / "verifier.py"
    source.parent.mkdir()
    source.write_text("verified source\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    inputs = {
        "formal_verifier": {
            "path": "scripts/verifier.py", "sha256": digest, "location": "source_repo",
        },
    }
    assert verify_source_inputs(inputs, root=tmp_path) == {"formal_verifier": digest}
    source.write_text("changed source\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_source_inputs(inputs, root=tmp_path)
