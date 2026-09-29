#!/usr/bin/env python3
"""Independently host-verify one exact Kaggle directional-FD kernel version."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CRITERIA_DEFAULT = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round1.json"
DEFAULT_STATE = ROOT / "work/kaggle_w3_v16_dataset_registered_3c54f386/sdf_design_state.npz"
OUTPUT_NAME = "sdf_directional_fd_v16"
CRITERIA_NAME = "sdf_directional_fd_v16_criteria.json"
DATASET_MANIFEST_NAME = "sdf_directional_fd_v16_dataset_manifest.json"
EXPECTED_RUNS = []
BASELINE_RUNS = ("baseline_A", "baseline_B", "baseline_C")
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
EPSILONS = (0.0005, 0.001, 0.0025, 0.005, 0.01)
for _direction in DIRECTIONS:
    for _epsilon in EPSILONS:
        EXPECTED_RUNS.extend([
            f"{_direction}__eps_{_epsilon:.4f}".replace(".", "p") + "m__plus",
            f"{_direction}__eps_{_epsilon:.4f}".replace(".", "p") + "m__minus",
        ])
EXPECTED_RUNS = ["baseline_A", *EXPECTED_RUNS[:10], *EXPECTED_RUNS[10:16],
                 "baseline_B", *EXPECTED_RUNS[16:], "baseline_C"]
FORCE_COLUMNS = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver",
    "downforce_solver", "pressure_fx_solver", "pressure_fy_solver",
    "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver",
]
REQUIRED_WINDOW_COMPONENT_METRICS = tuple(
    f"window_time_weighted_{component}_solver"
    for component in (
        "pressure_fx", "pressure_fy", "pressure_fz",
        "viscous_fx", "viscous_fy", "viscous_fz",
    )
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha(value: dict) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                  allow_nan=False).encode())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def load_criteria(path: Path) -> tuple[dict, str]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    require(path.is_file() and sidecar.is_file(), "immutable FD criteria/sidecar missing")
    digest = sha256(path)
    require(sidecar.read_text().strip() == digest, "FD criteria sidecar SHA mismatch")
    criteria = read_json(path)
    require(criteria.get("immutable") is True
            and criteria.get("registered_before_computation") is True
            and criteria.get("status") == "registered_not_run"
            and criteria.get("formal_measurement_started") is False
            and criteria.get("source_commit") == criteria.get("registered_source_commit")
            and criteria.get("criteria_sha256") == canonical_json_sha(
                {key: value for key, value in criteria.items() if key != "criteria_sha256"}),
            "FD criteria are not the exact immutable premeasurement round")
    require(criteria.get("kind") == "sdf_directional_fd_flow16_criteria",
            "unexpected FD criteria schema")
    return criteria, digest


def git_blob_sha(commit: str, path: str) -> str:
    content = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{path}"])
    return sha256_bytes(content)


def verify_source(criteria: dict, criteria_sha: str, runner_sha: str) -> dict:
    commit = criteria["source_commit"]
    require(criteria.get("registered_source_commit") == commit, "FD source commit identity mismatch")
    source_hashes = {}
    for name, entry in criteria["inputs"].items():
        if entry.get("location") != "source_repo":
            continue
        digest = git_blob_sha(commit, entry["path"])
        require(digest == entry["sha256"], f"pinned source hash mismatch: {name}")
        current = ROOT / entry["path"]
        require(current.is_file() and sha256(current) == entry["sha256"],
                f"current checkout source hash mismatch: {name}")
        source_hashes[name] = digest
    runner_entry = criteria["inputs"]["kernel_runner"]
    require(runner_sha == runner_entry["sha256"], "Kaggle runner SHA mismatch")
    for prereq_key in ("w3", "w4"):
        prereq = criteria["prerequisites"][prereq_key]
        for field in ("criteria_path", "result_path"):
            path = prereq[field]
            expected = prereq["criteria_sha256"] if field == "criteria_path" else prereq["result_sha256"]
            require(source_hashes.get(prereq_key + ("_criteria" if field == "criteria_path" else "_result")) == expected,
                    f"{prereq_key} prerequisite is not source-bound: {path}")
            local = ROOT / path
            require(sha256(local) == expected, f"{prereq_key} evidence SHA mismatch")
        criteria_doc = read_json(ROOT / prereq["criteria_path"])
        result_doc = read_json(ROOT / prereq["result_path"])
        observed_identity = result_doc.get("backend_identity", {})
        registered_identity = observed_identity if prereq_key == "w3" else observed_identity.get("registered_backend")
        require(criteria_doc.get("immutable") is True
                and criteria_doc.get("registered_before_computation") is True
                and result_doc.get("verdict") == "PASS"
                and result_doc.get("host_verification_passed") is True
                and registered_identity == prereq["backend_identity"],
                f"{prereq_key} is not exact host-verified PASS evidence")
        if prereq_key == "w4":
            require(result_doc.get("w4_sensitivity_matrix_passed") is True
                    and result_doc.get("fd_entry_gate") == "OPEN"
                    and result_doc.get("formal_fd_measurement_started") is False
                    and result_doc.get("extended_domain_fine_grid_required") is False
                    and observed_identity.get("selected_gpu_uuid") == prereq["selected_gpu_uuid"]
                    and canonical_json_sha(observed_identity) == prereq["observed_backend_identity_sha256"],
                    "W4 formal FD entry gate is not open")
    require(criteria["prerequisites"]["w3"]["backend_identity"]
            == criteria["prerequisites"]["w4"]["backend_identity"],
            "W3/W4 observed backend identities differ")
    return source_hashes


def load_and_verify_inputs(criteria: dict, criteria_sha: str, dataset_dir: Path,
                           canonical_state_path: Path) -> dict:
    from cfd_sdf.design.sdf_state import SDFDesignState
    from cfd_sdf.gradients.directional_fd import (
        DIRECTION_IDS as CONTRACT_DIRECTIONS,
        generate_directions, perturbation_case_id, perturbed_state,
        phi_sha256, validate_directions, zero_level_margin_m,
    )

    generation_runtime = criteria.get("direction_generation_runtime", {})
    require(generation_runtime.get("python_version") == platform.python_version()
            and generation_runtime.get("numpy_version") == np.__version__,
            "host Python/NumPy differs from the frozen direction generator environment")

    expected_files = {entry["path"]: entry["sha256"] for entry in criteria["inputs"].values()
                      if entry.get("location") == "kaggle_dataset"}
    expected_files[CRITERIA_NAME] = criteria_sha
    expected_files[CRITERIA_NAME + ".sha256"] = sha256(dataset_dir / (CRITERIA_NAME + ".sha256"))
    manifest_path = dataset_dir / DATASET_MANIFEST_NAME
    require(manifest_path.is_file(), "FD dataset manifest is missing")
    manifest = read_json(manifest_path)
    require(manifest.get("dataset_id") == criteria["input_dataset_id"]
            and manifest.get("criteria_sha256") == criteria_sha
            and manifest.get("source_commit") == criteria["source_commit"]
            and manifest.get("files") == expected_files,
            "FD dataset manifest identity/file inventory mismatch")
    actual = {path.relative_to(dataset_dir).as_posix() for path in dataset_dir.rglob("*") if path.is_file()}
    require(actual == set(expected_files) | {DATASET_MANIFEST_NAME},
            f"remote dataset payload inventory mismatch: extra={actual-set(expected_files)-{DATASET_MANIFEST_NAME}}")
    for name, expected in expected_files.items():
        path = dataset_dir / name
        require(path.is_file() and sha256(path) == expected, f"FD dataset file SHA mismatch: {name}")

    state_entry = criteria["inputs"]["canonical_state_npz"]
    source_state = Path(canonical_state_path)
    dataset_state_path = dataset_dir / state_entry["path"]
    require(sha256(source_state) == state_entry["sha256"]
            and sha256(dataset_state_path) == state_entry["sha256"],
            "canonical SDF NPZ differs from W3/W4-bound state")
    state = SDFDesignState.load(dataset_state_path)
    geometry = criteria["geometry"]
    require(state.state_sha256 == geometry["canonical_state_sha256"]
            and state.shape == tuple(geometry["point_shape"])
            and list(state.origin_m) == geometry["canonical_sdf_origin_m"]
            and state.spacing_m == geometry["design_spacing_m"]
            and state.narrow_band_width_m == geometry["narrow_band_width_m"]
            and state.source_sha256 == geometry["source_surface_sha256"],
            "canonical SDF state metadata differs from criteria")
    require(phi_sha256(state.phi, order="C") == geometry["canonical_phi_c_order_sha256"],
            "canonical C-order phi hash mismatch")
    raw_fortran = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    require(sha256_bytes(raw_fortran) == geometry["canonical_phi_fortran_sha256"],
            "canonical Fortran-order phi hash mismatch")
    raw_path = dataset_dir / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    require(raw_path.read_bytes() == raw_fortran, "canonical raw phi bytes differ from NPZ")
    measured_margin = zero_level_margin_m(state.phi, state.spacing_m)
    require(math.isfinite(measured_margin)
            and measured_margin >= geometry["margin_gate_m"]
            and math.isclose(measured_margin, geometry["canonical_phi_margin_m"], rel_tol=0, abs_tol=1e-6),
            "canonical CPU SDF margin failed")
    mask_hashes = {}
    for key, name in (("design_mask_sha256", "design_mask"),
                      ("fixed_solid_mask_sha256", "fixed_solid_mask"),
                      ("forbidden_mask_sha256", "forbidden_mask"),
                      ("root_mask_sha256", "root_mask")):
        digest = sha256_bytes(np.ascontiguousarray(getattr(state, name), dtype="u1").tobytes())
        require(digest == geometry[key], f"canonical {name} SHA mismatch")
        mask_hashes[name] = digest

    directions = generate_directions(state)
    audit = validate_directions(state, directions)
    require(tuple(directions) == CONTRACT_DIRECTIONS == tuple(criteria["direction_inventory"]),
            "direction inventory/order mismatch")
    require(audit == criteria["direction_audit"], "direction generator/cosine audit mismatch")
    for direction_id in CONTRACT_DIRECTIONS:
        record = criteria["direction_inventory"][direction_id]
        raw = np.asarray(directions[direction_id], dtype="<f4", order="C").tobytes(order="C")
        require(sha256_bytes(raw) == record["sha256"]
                and (dataset_dir / record["dataset_path"]).read_bytes() == raw,
                f"direction raw array identity mismatch: {direction_id}")
    require(len(criteria["perturbation_inventory"]) == 30, "FD criteria do not bind all 30 perturbations")
    preflight = []
    for entry in criteria["perturbation_inventory"]:
        case_id = perturbation_case_id(entry["direction_id"], entry["epsilon_m"], entry["sign"])
        require(case_id == entry["case_id"], "perturbation case id mismatch")
        child, identity = perturbed_state(state, directions[entry["direction_id"]],
            epsilon_m=entry["epsilon_m"], sign=entry["sign"], margin_gate_m=entry["margin_gate_m"])
        raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
        require((dataset_dir / entry["dataset_path"]).read_bytes() == raw
                and sha256_bytes(raw) == entry["phi_file_sha256"]
                and child.state_sha256 == entry["state_sha256"]
                and identity["phi_c_order_sha256"] == entry["phi_c_order_sha256"]
                and identity["phi_fortran_order_sha256"] == entry["phi_fortran_sha256"]
                and identity["masks_unchanged"] is True
                and identity["outside_design_phi_identical"] is True
                and identity["zero_level_margin_m"] >= geometry["margin_gate_m"],
                f"perturbed state preflight identity/gate mismatch: {case_id}")
        preflight.append({"case_id": case_id,
            "state_sha256": child.state_sha256,
            "phi_c_order_sha256": identity["phi_c_order_sha256"],
            "phi_fortran_sha256": identity["phi_fortran_order_sha256"],
            "maximum_pointwise_change_m": identity["maximum_pointwise_change_m"],
            "changed_node_count": identity["changed_node_count"],
            "zero_level_margin_m": identity["zero_level_margin_m"],
            "sign_change_node_count": int(np.count_nonzero((child.phi < 0) != (state.phi < 0)))})
    return {"state": state, "directions": directions, "direction_audit": audit,
        "perturbation_preflight": preflight, "state_npz_sha256": sha256(dataset_state_path),
        "canonical_phi_c_order_sha256": phi_sha256(state.phi, order="C"),
        "canonical_phi_fortran_sha256": sha256_bytes(raw_fortran),
        "canonical_margin_m": measured_margin, "mask_sha256": mask_hashes,
        "dataset_manifest_sha256": sha256(manifest_path), "dataset_files": expected_files,
        "dataset_manifest": manifest}


def verify_runner_preflight_identity(output_dir: Path, input_result: dict,
                                    criteria: dict) -> dict:
    path = output_dir / "input_state_and_direction_identity.json"
    runner_state = read_json(path)
    canonical = input_result["state"].to_dict()
    for key, expected in canonical.items():
        require(runner_state.get(key) == expected, f"runner canonical state field mismatch: {key}")
    require(runner_state.get("state_npz_sha256") == input_result["state_npz_sha256"]
            and runner_state.get("canonical_phi_c_order_sha256") == input_result["canonical_phi_c_order_sha256"]
            and runner_state.get("canonical_phi_fortran_sha256") == input_result["canonical_phi_fortran_sha256"]
            and math.isclose(runner_state.get("canonical_margin_m", math.nan),
                             input_result["canonical_margin_m"], rel_tol=0, abs_tol=1e-12)
            and runner_state.get("mask_sha256") == input_result["mask_sha256"],
            "runner canonical NPZ/phi/mask/margin preflight identity differs from host")
    runner_audit = runner_state.get("direction_audit", {})
    host_audit = input_result["direction_audit"]
    require(runner_audit.get("shape") == host_audit["shape"]
            and runner_audit.get("dtype") == host_audit["dtype"]
            and runner_audit.get("direction_sha256") == host_audit["direction_sha256"]
            and set(runner_audit.get("pairwise_cosine", {})) == set(host_audit["pairwise_cosine"])
            and all(math.isfinite(float(value)) and abs(float(value)) < 0.95
                    for value in runner_audit.get("pairwise_cosine", {}).values()),
            "runner frozen-direction identity/nonduplication audit differs from host")
    runner_perturbations = runner_state.get("perturbation_preflight", [])
    host_perturbations = input_result["perturbation_preflight"]
    require(len(runner_perturbations) == len(host_perturbations) == 30,
            "runner/host preflight does not contain all 30 frozen perturbations")
    for runner_item, host_item in zip(runner_perturbations, host_perturbations):
        require(runner_item.get("case_id") == host_item["case_id"]
                and runner_item.get("sign_change_node_count") == host_item["sign_change_node_count"]
                and math.isclose(runner_item.get("zero_level_margin_m", math.nan),
                                 host_item["zero_level_margin_m"], rel_tol=0, abs_tol=1e-12),
                f"runner/host perturbation preflight mismatch: {host_item['case_id']}")
    return {"matched": True, "state_sha256": canonical["state_sha256"],
        "direction_sha256": runner_audit["direction_sha256"],
        "perturbation_count": len(runner_perturbations), "sha256": sha256(path)}


def verify_output_files(folder: Path) -> tuple[dict, str]:
    require((folder / "DONE").is_file(), "FD Kaggle output has no DONE marker")
    require(not (folder / "ERROR.txt").exists(), "FD Kaggle output contains ERROR.txt")
    manifest_path = folder / "sha256.json"
    manifest = read_json(manifest_path)
    names = {path.name for path in folder.iterdir() if path.is_file()}
    require(set(manifest) == names - {"sha256.json", "DONE"},
            "FD output inventory differs from output SHA manifest")
    for name, digest in manifest.items():
        require(Path(name).name == name and sha256(folder / name) == digest,
                f"FD output artifact SHA mismatch: {name}")
    return manifest, sha256(manifest_path)


def parse_force_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == FORCE_COLUMNS, f"raw force CSV columns mismatch: {path.name}")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    require(bool(rows) and all(math.isfinite(value) for row in rows for value in row.values()),
            f"raw force CSV empty/nonfinite: {path.name}")
    require(all(right["step"] > left["step"] and right["t_u_l"] > left["t_u_l"]
                for left, right in zip(rows, rows[1:])), f"raw force CSV order invalid: {path.name}")
    return rows


def validate_sample_stride(rows, criteria):
    measurement = criteria["measurement"]
    stride = measurement["force_sample_every_solver_steps"]
    terminal_extra = int(rows[-1]["step"]) % stride != 0
    regular = rows[:-1] if terminal_extra else rows
    require(all(int(row["step"]) % stride == 0 for row in regular)
            and all(int(right["step"] - left["step"]) == stride
                    for left, right in zip(regular, regular[1:])),
            "registered force sampling stride mismatch")
    if terminal_extra:
        require(rows[-1]["t_u_l"] >= measurement["target_t_u_l"]
                and 0 < rows[-1]["step"] - rows[-2]["step"] < stride,
                "terminal first-at-or-after-120 sample rule mismatch")
    start, end = measurement["force_window_t_u_l"]
    raw_window_samples = sum(start <= row["t_u_l"] <= end for row in rows)
    require(raw_window_samples >= measurement["minimum_window_samples"],
            "registered force window has too few raw samples")


def interpolate(rows, t):
    right = next((index for index, row in enumerate(rows) if row["t_u_l"] >= t), None)
    require(right is not None, f"force samples do not reach exact tU/L={t}")
    if rows[right]["t_u_l"] == t:
        return dict(rows[right])
    require(right > 0, "force samples do not bracket the exact window start")
    left, after = rows[right - 1], rows[right]
    alpha = (t - left["t_u_l"]) / (after["t_u_l"] - left["t_u_l"])
    return {key: t if key == "t_u_l" else left[key] + alpha * (after[key] - left[key])
            for key in left}


def exact_window(rows, start, end):
    require(rows[0]["t_u_l"] <= start and rows[-1]["t_u_l"] >= end,
            "raw samples do not bracket exact [80,120] window")
    return [interpolate(rows, start), *[row for row in rows if start < row["t_u_l"] < end], interpolate(rows, end)]


def time_mean(rows, column):
    integral = duration = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        integral += 0.5 * (left[column] + right[column]) * dt
        duration += dt
    require(duration > 0.0, "force window duration is nonpositive")
    return integral / duration


def recompute_run_metrics(rows, criteria):
    measurement = criteria["measurement"]
    whole = exact_window(rows, *measurement["force_window_t_u_l"])
    first = exact_window(rows, *measurement["stationarity_half_windows_t_u_l"][0])
    second = exact_window(rows, *measurement["stationarity_half_windows_t_u_l"][1])
    cols = ("fx_solver", "fy_solver", "fz_solver", "drag_solver", "downforce_solver",
        "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver",
        "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver")
    metrics = {f"window_time_weighted_{column}": time_mean(whole, column) for column in cols}
    flow = criteria["geometry"]["flow_case"]
    density, speed, dx = flow["density_kg_m3"], flow["freestream_mps"][0], flow["flow_spacing_m"]
    force_scale = density * speed**2 * dx**2
    reference_area_solver = flow["reference_area_m2"] / dx**2
    metrics.update({
        "drag_time_weighted_n": metrics["window_time_weighted_drag_solver"] * force_scale,
        "downforce_time_weighted_n": metrics["window_time_weighted_downforce_solver"] * force_scale,
        "cd_time_weighted": metrics["window_time_weighted_drag_solver"] / (
            0.5 * reference_area_solver * speed**2),
    })
    for quantity, col in (("drag", "drag_solver"), ("downforce", "downforce_solver")):
        f, s, w = time_mean(first, col), time_mean(second, col), metrics[f"window_time_weighted_{col}"]
        metrics[f"stationarity_first_half_time_weighted_{quantity}_solver"] = f
        metrics[f"stationarity_second_half_time_weighted_{quantity}_solver"] = s
        metrics[f"stationarity_relative_half_window_drift_{quantity}"] = abs(f-s) / max(abs(w), sys.float_info.epsilon)
    return metrics


def force_components_close(rows, criteria):
    measurement = criteria["measurement"]
    rel, absolute = measurement["force_component_relative_tolerance"], measurement["force_component_absolute_tolerance"]
    return all(math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=rel, abs_tol=absolute)
        and math.isclose(row["downforce_solver"], -row["fz_solver"], rel_tol=rel, abs_tol=absolute)
        and all(math.isclose(row[f"{axis}_solver"],
            row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"],
            rel_tol=rel, abs_tol=absolute) for axis in ("fx", "fy", "fz")) for row in rows)


def runner_metrics_match(summary, metrics, tolerance):
    if any(key not in summary or key not in metrics
           for key in REQUIRED_WINDOW_COMPONENT_METRICS):
        return False
    return all(math.isclose(float(summary.get(key, math.nan)), value,
                            rel_tol=tolerance, abs_tol=1e-10) for key, value in metrics.items())


def host_physics_identity(summary, criteria):
    geometry = criteria["geometry"]
    flow = geometry["flow_case"]
    run_id = summary.get("run_id")
    expected_margin = geometry["canonical_phi_margin_m"] if run_id in {
        "baseline_A", "baseline_B", "baseline_C"} else next(
            item["zero_level_margin_m"] for item in criteria["perturbation_inventory"]
            if item["case_id"] == run_id)
    close = lambda key, expected: math.isclose(
        float(summary.get(key, math.nan)), float(expected), rel_tol=0.0, abs_tol=1e-12)
    return (
        math.isclose(float(summary.get("phi_margin_m", math.nan)), expected_margin,
                     rel_tol=0.0, abs_tol=1e-6)
        and close("phi_margin_gate_m", geometry["margin_gate_m"])
        and summary.get("point_shape") == geometry["point_shape"]
        and summary.get("canonical_sdf_origin_m") == geometry["canonical_sdf_origin_m"]
        and summary.get("flow_origin_m") == flow["flow_origin_m"]
        and summary.get("flow_dims") == flow["flow_dims"]
        and close("flow_spacing_m", flow["flow_spacing_m"])
        and close("solver_length", flow["solver_length"])
        and close("solver_viscosity", flow["solver_viscosity"])
        and close("solver_velocity", flow["solver_velocity"])
        and close("solver_time_unit_s", flow["solver_time_unit_s"])
        and close("reynolds", flow["reynolds"])
        and close("density_kg_m3", flow["density_kg_m3"])
        and close("dynamic_viscosity_pa_s", flow["dynamic_viscosity_pa_s"])
        and list(summary.get("freestream_mps", ())) == flow["freestream_mps"]
        and close("reference_length_m", flow["reference_length_m"])
        and close("reference_area_m2", flow["reference_area_m2"])
        and close("canonical_design_spacing_m", geometry["design_spacing_m"])
        and summary.get("candidate_body_mapping") == flow["candidate_body_mapping"]
        and close("sdf_outside_value_m", geometry["outside_value_m"])
        and close("moving_ground_solver_plane", flow["moving_ground_solver_plane"])
        and close("moving_ground_world_plane_m", flow["moving_ground_world_plane_m"])
        and list(summary.get("moving_ground_velocity_mps", ())) == flow["moving_ground_velocity_mps"]
        and summary.get("force_window_t_u_l") == criteria["measurement"]["force_window_t_u_l"]
        and summary.get("stationarity_half_windows_t_u_l") == criteria["measurement"]["stationarity_half_windows_t_u_l"]
        and summary.get("sample_every_solver_steps") == criteria["measurement"]["force_sample_every_solver_steps"]
        and summary.get("physical_box_m") == flow["physical_box_m"]
        and summary.get("native_velocity_boundary") == flow["native_velocity_boundary"]
        and summary.get("side_top_tangential_boundary") == flow["side_top_tangential_boundary"]
        and summary.get("x_plus_boundary") == flow["x_plus_boundary"]
        and summary.get("pressure_boundary") == flow["pressure_boundary"]
        and summary.get("ground_model") == flow["ground_model"]
        and summary.get("force_integration_body") == flow["force_integration_body"]
        and summary.get("force_projection_semantics") == flow["force_projection_semantics"]
        and summary.get("source_profile_equivalent") is flow["source_profile_equivalent"]
        and summary.get("physical_profile_qualified") is flow["physical_profile_qualified"]
    )


def host_baseline_noise(values):
    values = np.asarray(values, dtype=np.float64)
    med, lo, hi = float(np.median(values)), float(values.min()), float(values.max())
    span = hi - lo
    return {"median": med, "min": lo, "max": hi, "span": span,
            "noise_floor": max(span, 1e-8 * max(1.0, abs(med)))}


def host_classify_pairs(pairs, baseline, noise):
    rows = []
    for pair in sorted(pairs, key=lambda item: item["epsilon_m"]):
        eps, plus, minus = pair["epsilon_m"], pair["plus_response_n"], pair["minus_response_n"]
        signal = abs(plus - minus)
        slope = (plus - minus) / (2 * eps)
        even = plus + minus - 2 * baseline
        rows.append({"epsilon_m": eps, "plus_response_n": plus, "minus_response_n": minus,
            "pair_signal_n": signal, "resolved": signal >= 20 * noise,
            "centered_derivative_n_per_m": slope, "even_nonlinearity_n": even,
            "even_to_odd_ratio": abs(even) / max(signal, noise)})
    resolved = [row for row in rows if row["resolved"]]
    selected = resolved[:3]
    enough = len(selected) == 3
    reference = float(np.median([row["centered_derivative_n_per_m"] for row in selected])) if enough else None
    noise_equivalent = max(noise / row["epsilon_m"] for row in selected) if enough else None
    deviations = []
    for row in selected:
        error = abs(row["centered_derivative_n_per_m"] - reference) / max(abs(reference), noise_equivalent)
        row["directional_noise_equivalent_n_per_m"] = noise_equivalent
        row["plateau_relative_deviation"] = error
        deviations.append(error)
    signs = [int(math.copysign(1, row["centered_derivative_n_per_m"]))
             if row["centered_derivative_n_per_m"] != 0 else 0 for row in selected]
    sign_stable = enough and bool(signs) and signs[0] != 0 and len(set(signs)) == 1
    passed = enough and sign_stable and all(value <= 0.05 for value in deviations)
    return {"all_epsilon_results": rows, "resolved_epsilon_m": [row["epsilon_m"] for row in resolved],
        "resolved_count": len(resolved), "plateau_epsilon_m": [row["epsilon_m"] for row in selected],
        "reference_derivative_n_per_m": reference,
        "directional_noise_equivalent_n_per_m": noise_equivalent,
        "plateau_relative_deviations": deviations,
        "plateau_max_relative_deviation": max(deviations) if deviations else None,
        "plateau_signs": signs, "sign_stable": sign_stable, "plateau_pass": passed}


def expected_input_for_run(criteria, run_id):
    if run_id in BASELINE_RUNS:
        return {"phi_sha": criteria["geometry"]["canonical_phi_fortran_sha256"],
            "state_sha": criteria["geometry"]["canonical_state_sha256"], "direction_id": "",
            "epsilon_m": 0.0, "sign": 0}
    row = next(item for item in criteria["perturbation_inventory"] if item["case_id"] == run_id)
    return {"phi_sha": row["phi_fortran_sha256"], "state_sha": row["state_sha256"],
        "direction_id": row["direction_id"], "epsilon_m": row["epsilon_m"], "sign": row["sign"]}


def verify_run_summaries(criteria, output_dir, output_hashes):
    run_order = criteria["run_order"]
    require(run_order == EXPECTED_RUNS and len(run_order) == 33,
            "registered FD exact 33-run order mismatch")
    summaries, rows_by_run, metrics = {}, {}, {}
    for run_id in run_order:
        summary_path, raw_path = output_dir / f"{run_id}.summary.json", output_dir / f"{run_id}.forces.csv"
        require(summary_path.name in output_hashes and raw_path.name in output_hashes,
                f"run artifacts missing from manifest: {run_id}")
        summary = read_json(summary_path)
        rows = parse_force_csv(raw_path)
        validate_sample_stride(rows, criteria)
        measured = recompute_run_metrics(rows, criteria)
        expected_input = expected_input_for_run(criteria, run_id)
        geom = criteria["geometry"]["flow_case"]
        require(summary.get("run_id") == run_id
                and summary.get("input_phi_sha256") == expected_input["phi_sha"]
                and summary.get("input_state_sha256") == expected_input["state_sha"]
                and summary.get("direction_id") == expected_input["direction_id"]
                and summary.get("epsilon_m") == expected_input["epsilon_m"]
                and summary.get("sign") == expected_input["sign"],
                f"run identity mismatch: {run_id}")
        require(summary.get("phi_c_order_sha256") == criteria["geometry"]["canonical_phi_c_order_sha256"]
                    if run_id in BASELINE_RUNS else summary.get("phi_c_order_sha256") == next(
                        x["phi_c_order_sha256"] for x in criteria["perturbation_inventory"] if x["case_id"] == run_id),
                f"run C-order phi hash mismatch: {run_id}")
        require(summary.get("phi_fortran_sha256") == expected_input["phi_sha"]
                and summary.get("device_roundtrip_sha256") == expected_input["phi_sha"],
                f"run Fortran/GPU round-trip hash mismatch: {run_id}")
        require(summary.get("point_shape") == criteria["geometry"]["point_shape"]
                and summary.get("canonical_sdf_origin_m") == criteria["geometry"]["canonical_sdf_origin_m"]
                and summary.get("flow_origin_m") == geom["flow_origin_m"]
                and summary.get("flow_dims") == geom["flow_dims"]
                and summary.get("flow_spacing_m") == geom["flow_spacing_m"]
                and summary.get("solver_length") == geom["solver_length"]
                and math.isclose(summary.get("solver_viscosity", math.nan), geom["solver_viscosity"], rel_tol=0, abs_tol=1e-12)
                and summary.get("reynolds") == geom["reynolds"]
                and summary.get("physical_box_m") == geom["physical_box_m"],
                f"flow_16 grid/world mapping or Re mismatch: {run_id}")
        require(host_physics_identity(summary, criteria),
                f"flow_16 constants, BC, ground, force-body, or projection identity mismatch: {run_id}")
        require(summary.get("t_end_target") == 120.0 and summary.get("t_end_reached", 0) >= 120.0
                and summary.get("finite_u") is True and summary.get("finite_p") is True
                and summary.get("finite_forces") is True,
                f"fresh primal did not complete with finite fields/forces: {run_id}")
        raw_window_count = sum(
            criteria["measurement"]["force_window_t_u_l"][0] <= row["t_u_l"]
            <= criteria["measurement"]["force_window_t_u_l"][1] for row in rows)
        require(summary.get("window_samples") == raw_window_count
                and raw_window_count >= criteria["measurement"]["minimum_window_samples"],
                f"force-window raw sample count mismatch: {run_id}")
        require(force_components_close(rows, criteria), f"force closure/projection failed: {run_id}")
        require(summary.get("force_csv_sha256") == sha256(raw_path), f"raw force CSV SHA mismatch: {run_id}")
        require(runner_metrics_match(summary, measured, criteria["measurement"]["host_recompute_relative_tolerance"]),
                f"host exact-window metric differs from runner summary: {run_id}")
        require(summary.get("force_projection_semantics") == "drag=+Fx; downforce=-Fz"
                and summary.get("source_profile_equivalent") is False
                and summary.get("physical_profile_qualified") is False,
                f"force or physical-profile scope drift: {run_id}")
        summaries[run_id], rows_by_run[run_id], metrics[run_id] = summary, rows, measured
    return summaries, rows_by_run, metrics


def verify_julia_progress(output_dir, criteria):
    log_path = output_dir / "fd_v16.log"
    log_text = log_path.read_text(errors="replace")
    invoked = [line.split()[-1] for line in log_text.splitlines() if line.startswith("FD_SOLVER_STEP_INVOKED ")]
    returned = [line.split()[-1] for line in log_text.splitlines() if line.startswith("FD_SOLVER_STEP_RETURNED ")]
    started = [line.split()[-1] for line in log_text.splitlines() if line.startswith("FD_RUN_STARTED ")]
    finished = [line.split()[1] for line in log_text.splitlines() if line.startswith("FD_RUN_DONE ")]
    require(invoked == criteria["run_order"] and returned == invoked
            and started == criteria["run_order"] and finished == criteria["run_order"],
            "Julia run/first-step marker sequences do not match the registered 33-run order")
    execution = read_json(output_dir / "execution_state.json")
    require(execution.get("solver_step_invoked") == criteria["run_order"]
            and execution.get("solver_step_returned") == criteria["run_order"]
            and execution.get("solver_started") is True,
            "runner execution-state completion markers mismatch")
    return {"solver_step_invoked": invoked, "solver_step_returned": returned,
            "run_started": started, "run_finished": finished,
            "execution_state": execution}


def verify_runtime(criteria, output_dir, summaries):
    backend = criteria["backend"]
    gpu_text = (output_dir / "nvidia_smi.csv").read_text()
    gpu_rows = [", ".join(cell.strip() for cell in row)
                for row in csv.reader(gpu_text.splitlines()) if row]
    require(len(gpu_rows) == backend["gpu_count"], "GPU inventory count is not two")
    selected_uuid = read_json(output_dir / "runtime_fingerprint.json")["selected_gpu_uuid"]
    rows_parsed = [[item.strip() for item in row.split(", ")] for row in gpu_rows]
    require([row[0] for row in rows_parsed] == ["0", "1"]
            and all(backend["gpu_name"] in row[1] and row[-1] == backend["driver_version"] for row in rows_parsed)
            and selected_uuid == rows_parsed[0][2], "observed GPU model/driver/selected UUID mismatch")
    fingerprint = read_json(output_dir / "runtime_fingerprint.json")
    require(fingerprint.get("criteria_sha256") == sha256(output_dir / "input_criteria.json")
            and fingerprint.get("source_commit") == criteria["source_commit"]
            and fingerprint.get("kernel_runner_sha256") == criteria["inputs"]["kernel_runner"]["sha256"]
            and fingerprint.get("dataset_id") == criteria["input_dataset_id"]
            and fingerprint.get("dataset_manifest_sha256") == sha256(output_dir / "input_dataset_manifest.json")
            and fingerprint.get("julia_archive_sha256") == backend["julia_archive_sha256"]
            and fingerprint.get("gpu_inventory") == gpu_rows
            and fingerprint.get("backend_expected") == backend
            and fingerprint.get("selected_gpu_uuid") == selected_uuid,
            "runtime fingerprint source/backend identity mismatch")
    smoke = (output_dir / "julia_smoke.log").read_text(errors="replace")
    markers = ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
        f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
        f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
        f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
        f"JULIA_VERSION {backend['julia_version']}",
        f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
        f"WATERLILY_VERSION {backend['waterlily_version']}", f"GPU_NAME {backend['gpu_name']}", "NO_SOLVER_STEP")
    require(all(marker in smoke for marker in markers), "T4 smoke runtime markers mismatch")
    for run_id, summary in summaries.items():
        require(summary.get("gpu_uuid") == selected_uuid
                and summary.get("cuda_visible_devices") == backend["cuda_visible_devices"]
                and summary.get("julia_version") == backend["julia_version"]
                and summary.get("julia_threads") == backend["julia_threads"]
                and summary.get("cuda_jl_version") == backend["cuda_jl_version"]
                and summary.get("cuda_runtime_version") == backend["cuda_runtime_version"]
                and summary.get("waterlily_version") == backend["waterlily_version"]
                and summary.get("waterlily_backend") == backend["waterlily_backend"],
                f"per-run observed T4/Julia/CUDA/WaterLily identity mismatch: {run_id}")
    return gpu_rows, selected_uuid, fingerprint


def evaluate(criteria, input_result, output_dir, output_hashes, summaries, rows, metrics,
             progress, runtime, kernel_version, status_text, status_sha, log_path, log_sha):
    measurement = criteria["measurement"]
    baseline = {response: host_baseline_noise([metrics[run][f"{response}_time_weighted_n"]
        for run in BASELINE_RUNS]) for response in ("drag", "downforce")}
    direction_results = {}
    response_pairs = {}
    for direction_id in DIRECTIONS:
        direction_results[direction_id], response_pairs[direction_id] = {}, {}
        for response in ("drag", "downforce"):
            pairs = []
            for epsilon in EPSILONS:
                stem = f"{direction_id}__eps_{epsilon:.4f}".replace(".", "p") + "m"
                plus_id, minus_id = stem + "__plus", stem + "__minus"
                pair = {"epsilon_m": epsilon,
                    "plus_response_n": metrics[plus_id][f"{response}_time_weighted_n"],
                    "minus_response_n": metrics[minus_id][f"{response}_time_weighted_n"]}
                pairs.append(pair)
            response_pairs[direction_id][response] = pairs
            direction_results[direction_id][response] = host_classify_pairs(
                pairs, baseline[response]["median"], baseline[response]["noise_floor"])
    drag_gate = all(direction_results[d]["drag"]["plateau_pass"] for d in DIRECTIONS)
    down_gate = all(direction_results[d]["downforce"]["plateau_pass"] for d in DIRECTIONS)
    w4 = read_json(ROOT / criteria["prerequisites"]["w4"]["result_path"])
    w4_flow16 = w4["case_measurements"]["flow_16"]["force_metrics_host_recomputed"]
    ref_drag = w4_flow16["drag_time_weighted_n"]
    ref_down = w4_flow16["downforce_time_weighted_n"]
    crosscheck = {"w4_flow16_drag_n": ref_drag,
        "fd_baseline_median_drag_n": baseline["drag"]["median"],
        "drag_delta_n": baseline["drag"]["median"]-ref_drag,
        "w4_flow16_downforce_n": ref_down,
        "fd_baseline_median_downforce_n": baseline["downforce"]["median"],
        "downforce_delta_n": baseline["downforce"]["median"]-ref_down,
        "numerical_tolerance_gate_registered": False,
        "drag_sign_consistent": math.copysign(1, baseline["drag"]["median"]) == math.copysign(1, ref_drag)}
    force_integrity = all(force_components_close(rows[run], criteria) for run in criteria["run_order"])
    stationarity = all(metrics[run][f"stationarity_relative_half_window_drift_{q}"]
        <= measurement["stationarity_relative_half_window_drift_max"]
        for run in criteria["run_order"] for q in ("drag", "downforce"))
    recompute_match = all(runner_metrics_match(summaries[run], metrics[run],
        measurement["host_recompute_relative_tolerance"]) for run in criteria["run_order"])
    runtime_limits = all(0 < summaries[run]["wall_seconds"] <= measurement["run_wall_time_limit_s"]
        and 0 < summaries[run]["first_step_seconds"] <= measurement["first_step_wall_time_limit_s"]
        for run in criteria["run_order"])
    total_solver_wall = sum(summaries[run]["wall_seconds"] for run in criteria["run_order"])
    vram_limits = all(0 < summaries[run]["peak_vram_bytes"] <= measurement["peak_vram_limit_bytes"]
        and summaries[run]["peak_vram_bytes"] < summaries[run]["vram_total_bytes"]
        for run in criteria["run_order"])
    exact_status = "KernelWorkerStatus.COMPLETE" in status_text or status_text.strip().upper() == "COMPLETE"
    gates = {
        "T0_exact_W3_W4_prerequisites_and_FD_entry_gate": (
            criteria["prerequisites"]["w3"]["host_verified"] is True
            and criteria["prerequisites"]["w4"]["host_verified"] is True
            and criteria["prerequisites"]["w4"]["fd_entry_gate"] == "OPEN"
            and criteria["prerequisites"]["w4"]["formal_fd_measurement_started"] is False
            and criteria["prerequisites"]["w4"]["extended_domain_fine_grid_required"] is False),
        "T1_canonical_state_phi_masks_and_margin_identity": (
            input_result["state"].state_sha256 == criteria["geometry"]["canonical_state_sha256"]
            and input_result["canonical_margin_m"] >= criteria["geometry"]["margin_gate_m"]
            and input_result["runner_preflight_identity"]["matched"] is True
            and set(input_result["mask_sha256"]) == {"design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"}),
        "T2_direction_generation_identity_and_nonduplication": (
            set(input_result["direction_audit"]["direction_sha256"]) == set(DIRECTIONS)
            and max(abs(value) for value in input_result["direction_audit"]["pairwise_cosine"].values()) < 0.95),
        "T3_all_30_perturbation_identities_and_preflight": (
            len(input_result["perturbation_preflight"]) == 30
            and min(row["zero_level_margin_m"] for row in input_result["perturbation_preflight"])
                >= criteria["geometry"]["margin_gate_m"]),
        "T4_exact_backend_and_runtime_identity": runtime["identity_passed"],
        "T5_all_33_fresh_primal_runs_complete_to_tU_L_120": (
            progress["solver_step_invoked"] == criteria["run_order"]
            and progress["solver_step_returned"] == criteria["run_order"]
            and progress["run_started"] == criteria["run_order"]
            and progress["run_finished"] == criteria["run_order"]
            and all(summaries[run]["t_end_reached"] >= 120 for run in criteria["run_order"])),
        "T6_finite_fields_forces_component_closure_and_projection": (
            force_integrity and all(summaries[run]["finite_u"] and summaries[run]["finite_p"]
                                    and summaries[run]["finite_forces"] for run in criteria["run_order"])),
        "T7_host_recomputed_exact_window_responses_match_runner": recompute_match,
        "T8_all_run_stationarity": stationarity,
        "T9_three_baseline_noise_measurement": all(
            baseline[r]["noise_floor"] > 0 and len(BASELINE_RUNS) == 3 for r in ("drag", "downforce"))
            and crosscheck["drag_sign_consistent"],
        "T10_drag_directional_resolution_sign_and_plateau": drag_gate,
        "T11_downforce_directional_resolution_sign_and_plateau": down_gate,
        "T12_source_dataset_kernel_runtime_VRAM_and_artifact_integrity": (
            kernel_version >= 1 and exact_status and len(status_sha) == 64 and len(log_sha) == 64
            and runtime_limits and total_solver_wall <= measurement["aggregate_solver_wall_time_limit_s"]
            and vram_limits and len(output_hashes) >= 70
            and input_result["dataset_manifest_sha256"] == sha256(output_dir / "input_dataset_manifest.json")),
    }
    runner_outcome = read_json(output_dir / "outcome.json") if (output_dir / "outcome.json").is_file() else {}
    runner_gates = runner_outcome.get("gates", {})
    compared_gate_names = set(gates) - {"T12_source_dataset_kernel_runtime_VRAM_and_artifact_integrity"}
    runner_metrics = runner_outcome.get("host_recomputed_metrics", {})
    runner_outcome_metrics_match = set(runner_metrics) == set(metrics) and all(
        set(runner_metrics[run]) == set(metrics[run])
        and all(math.isclose(float(runner_metrics[run][key]), metrics[run][key],
                             rel_tol=measurement["host_recompute_relative_tolerance"], abs_tol=1e-10)
                for key in metrics[run])
        for run in metrics
    )
    runner_gate_match = (
        set(runner_gates) == set(gates)
        and all(runner_gates.get(name) is gates[name] for name in compared_gate_names)
        and runner_gates.get("T12_source_dataset_kernel_runtime_VRAM_and_artifact_integrity") is True
        and runner_outcome.get("host_runner_gate_all_pass") is all(runner_gates.values())
        and runner_outcome.get("criteria_sha256") == criteria["criteria_sha256"]
        and runner_outcome.get("source_commit") == criteria["source_commit"]
        and runner_outcome.get("dataset_manifest_sha256") == input_result["dataset_manifest_sha256"]
        and runner_outcome_metrics_match
    )
    gates["T12_source_dataset_kernel_runtime_VRAM_and_artifact_integrity"] = (
        gates["T12_source_dataset_kernel_runtime_VRAM_and_artifact_integrity"] and runner_gate_match
    )
    return {"baseline_noise": baseline, "directional_fd_results": direction_results,
        "directional_pairs": response_pairs, "w4_flow16_crosscheck": crosscheck,
        "aggregate_solver_wall_seconds": total_solver_wall,
        "all_run_stationarity_pass": stationarity,
        "all_run_force_closure_pass": force_integrity,
        "host_runner_recomputation_match": recompute_match,
        "runner_outcome_gate_match": runner_gate_match,
        "runner_outcome_gates": runner_gates,
        "runner_outcome_sha256": sha256(output_dir / "outcome.json") if (output_dir / "outcome.json").is_file() else None,
        "gates": gates, "all_gates_pass": all(gates.values())}


def write_evidence(report: dict, criteria: dict, criteria_sha: str, output_dir: Path,
                   output_manifest_sha: str, kernel_version: int, status_sha: str, log_sha: str,
                   host_verifier_sha: str, verification_path: Path,
                   evidence_path: Path | None):
    if evidence_path is None:
        return None, None
    require(report.get("verdict") == "PASS" and report.get("host_verification_passed") is True,
            "result evidence is allowed only after complete host PASS")
    if evidence_path.exists() or evidence_path.with_suffix(evidence_path.suffix + ".sha256").exists():
        raise FileExistsError(f"append-only evidence target exists: {evidence_path}")
    result = {
        "schema_version": 1,
        "kind": "sdf_directional_fd_flow16_result",
        "criteria_path": criteria["criteria_path"],
        "criteria_sha256": criteria_sha,
        "criteria_round": criteria["criteria_round"],
        "source_commit": criteria["source_commit"],
        "kernel_id": criteria["kernel_id"],
        "kernel_version": kernel_version,
        "terminal_status": "COMPLETE",
        "kaggle_status_sha256": status_sha,
        "kaggle_log_sha256": log_sha,
        "output_manifest_sha256": output_manifest_sha,
        "dataset_id": criteria["input_dataset_id"],
        "dataset_version": report["dataset_version"],
        "dataset_manifest_sha256": report["dataset_manifest_sha256"],
        "host_verifier_path": "scripts/verify_kaggle_sdf_directional_fd_v16.py",
        "host_verifier_sha256": host_verifier_sha,
        "host_verification_path": str(verification_path),
        "host_verification_passed": report["host_verification_passed"],
        "verdict": report["verdict"],
        "canonical_state": report["canonical_state"],
        "runner_preflight_identity": report["runner_preflight_identity"],
        "backend_identity": report["backend_identity"],
        "selected_gpu_uuid": report["selected_gpu_uuid"],
        "runner_runtime_fingerprint": report["runner_runtime_fingerprint"],
        "run_order": report["run_order"],
        "run_count": report["run_count"],
        "direction_inventory": report["direction_inventory"],
        "perturbation_inventory": report["perturbation_inventory"],
        "baseline_noise": report["baseline_noise"],
        "run_metrics": report["run_metrics"],
        "directional_fd_results": report["directional_fd_results"],
        "directional_pairs": report["directional_pairs"],
        "w4_flow16_crosscheck": report["w4_flow16_crosscheck"],
        "runner_outcome_gate_match": report["runner_outcome_gate_match"],
        "runner_outcome_gates": report["runner_outcome_gates"],
        "runner_outcome_sha256": report["runner_outcome_sha256"],
        "gates": report["gates"],
        "sdf_directional_fd_oracle_qualified": report["sdf_directional_fd_oracle_qualified"],
        "sdf_directional_fd_flow16_qualified": report["sdf_directional_fd_flow16_qualified"],
        "sdf_gradient_field_qualified": False,
        "gradient_qualified": False,
        "reverse_mode_qualified": False,
        "physical_profile_equivalence_qualified": False,
        "grid_or_domain_convergence_qualified": False,
        "absolute_downforce_qualified": False,
        "optimizer_qualified": False,
        "topology_qualified": False,
        "shape_update_allowed": False,
        "claim_scope": "The registered centered directional-FD oracle is qualified for the canonical v16 SDF on the registered WaterLily flow_16 discrete finite-box primal.",
        "limitations": criteria["claims"]["unsupported"],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = sha256(evidence_path)
    sidecar = evidence_path.with_suffix(evidence_path.suffix + ".sha256")
    sidecar.write_text(digest + "\n")
    return result, digest


def verify(args) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    criteria_path = args.criteria.resolve()
    criteria, criteria_sha = load_criteria(criteria_path)
    if args.kernel_id != criteria["kernel_id"] or args.kernel_version < 1:
        raise ValueError("exact Kaggle kernel identity/version does not match the registered criteria")
    output_dir, dataset_dir = args.output.resolve(), args.dataset_dir.resolve()
    status_text, kaggle_log = Path(args.status_file).read_text(), Path(args.kaggle_log_file).read_bytes()
    status_sha, log_sha = sha256(Path(args.status_file)), sha256(Path(args.kaggle_log_file))
    output_hashes, output_manifest_sha = verify_output_files(output_dir)
    require((output_dir / "input_criteria.json").read_bytes() == criteria_path.read_bytes()
            and (output_dir / "input_criteria.json.sha256").read_text().strip() == criteria_sha,
            "Kaggle runner input criteria identity mismatch")
    source_hashes = verify_source(criteria, criteria_sha,
        sha256(ROOT / criteria["inputs"]["kernel_runner"]["path"]))
    input_result = load_and_verify_inputs(criteria, criteria_sha, dataset_dir, args.state.resolve())
    input_result["runner_preflight_identity"] = verify_runner_preflight_identity(
        output_dir, input_result, criteria)
    progress = verify_julia_progress(output_dir, criteria)
    summaries, rows_by_run, metrics = verify_run_summaries(criteria, output_dir, output_hashes)
    gpu_rows, selected_uuid, fingerprint = verify_runtime(criteria, output_dir, summaries)
    runtime_identity_passed = True
    runtime = {"identity_passed": runtime_identity_passed, "gpu_inventory": gpu_rows,
        "selected_gpu_uuid": selected_uuid, "fingerprint": fingerprint,
        "status_text": status_text, "kaggle_log_sha256": log_sha}
    measured = evaluate(criteria, input_result, output_dir, output_hashes, summaries, rows_by_run,
        metrics, progress, runtime, args.kernel_version, status_text, status_sha,
        Path(args.kaggle_log_file), log_sha)
    all_pass = measured["all_gates_pass"]
    host_report = {
        "schema_version": 1,
        "kind": "sdf_directional_fd_v16_host_verification",
        "verdict": "PASS" if all_pass else "FAIL",
        "host_verification_passed": all_pass,
        "criteria_path": criteria_path.relative_to(ROOT).as_posix(),
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "host_verifier_sha256": sha256(Path(__file__)),
        "kernel_id": args.kernel_id,
        "kernel_version": args.kernel_version,
        "kaggle_status_sha256": status_sha,
        "kaggle_log_sha256": log_sha,
        "output_manifest_sha256": output_manifest_sha,
        "output_file_count": len(output_hashes),
        "dataset_id": criteria["input_dataset_id"],
        "dataset_version": args.dataset_version,
        "dataset_manifest_sha256": input_result["dataset_manifest_sha256"],
        "canonical_state": {
            "state_sha256": input_result["state"].state_sha256,
            "state_npz_sha256": input_result["state_npz_sha256"],
            "phi_c_order_sha256": input_result["canonical_phi_c_order_sha256"],
            "phi_fortran_sha256": input_result["canonical_phi_fortran_sha256"],
            "point_shape": list(input_result["state"].shape),
            "origin_m": list(input_result["state"].origin_m),
            "spacing_m": input_result["state"].spacing_m,
            "narrow_band_width_m": input_result["state"].narrow_band_width_m,
            "mask_sha256": input_result["mask_sha256"],
            "cpu_margin_m": input_result["canonical_margin_m"],
        },
        "runner_preflight_identity": input_result["runner_preflight_identity"],
        "backend_identity": criteria["backend"],
        "selected_gpu_uuid": selected_uuid,
        "runner_runtime_fingerprint": fingerprint,
        "source_input_sha256": source_hashes,
        "run_order": progress["solver_step_invoked"],
        "run_count": len(progress["solver_step_invoked"]),
        "run_metrics": metrics,
        "run_summaries": summaries,
        "raw_force_csv_sha256": {run: sha256(output_dir / f"{run}.forces.csv") for run in criteria["run_order"]},
        "direction_inventory": criteria["direction_inventory"],
        "direction_audit": input_result["direction_audit"],
        "perturbation_inventory": criteria["perturbation_inventory"],
        "perturbation_preflight": input_result["perturbation_preflight"],
        "baseline_noise": measured["baseline_noise"],
        "directional_fd_results": measured["directional_fd_results"],
        "directional_pairs": measured["directional_pairs"],
        "w4_flow16_crosscheck": measured["w4_flow16_crosscheck"],
        "runner_outcome_gate_match": measured["runner_outcome_gate_match"],
        "runner_outcome_gates": measured["runner_outcome_gates"],
        "runner_outcome_sha256": measured["runner_outcome_sha256"],
        "aggregate_solver_wall_seconds": measured["aggregate_solver_wall_seconds"],
        "gates": measured["gates"],
        "sdf_directional_fd_oracle_qualified": all_pass,
        "sdf_directional_fd_flow16_qualified": all_pass,
        "sdf_gradient_field_qualified": False,
        "gradient_qualified": False,
        "reverse_mode_qualified": False,
        "physical_profile_equivalence_qualified": False,
        "grid_or_domain_convergence_qualified": False,
        "absolute_downforce_qualified": False,
        "optimizer_qualified": False,
        "topology_qualified": False,
        "shape_update_allowed": False,
        "limitations": criteria["claims"]["unsupported"],
    }
    verification_path = Path(args.verification_output).resolve()
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification_path.write_text(json.dumps(host_report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    if not all_pass:
        raise ValueError(f"host verification failed closed: {measured['gates']}")
    evidence_path = Path(args.evidence_path).resolve() if args.evidence_path else None
    evidence, evidence_sha = write_evidence(host_report, criteria, criteria_sha, output_dir,
        output_manifest_sha, args.kernel_version, status_sha, log_sha,
        sha256(Path(__file__)), verification_path, evidence_path)
    host_report["verification_report_path"] = str(verification_path)
    host_report["verification_report_sha256"] = sha256(verification_path)
    if evidence is not None:
        host_report["result_evidence_path"] = str(evidence_path)
        host_report["result_evidence_sha256"] = evidence_sha
    return host_report


def default_diagnostic_path(criteria: dict) -> Path:
    round_number = int(criteria.get("criteria_round", 1))
    return ROOT / f"docs/evidence/sdf_directional_fd_v16_diagnostic_2026_09_round{round_number}.json"


def write_diagnostic(args, error: Exception) -> tuple[Path, str] | None:
    """Append an exact-run diagnostic when strict verification cannot PASS."""
    criteria_path = Path(args.criteria).resolve()
    try:
        criteria, criteria_sha = load_criteria(criteria_path)
    except Exception:
        criteria = {}
        criteria_sha = sha256(criteria_path) if criteria_path.is_file() else None
    output_dir = Path(args.output).resolve()
    status_path = Path(args.status_file)
    log_path = Path(args.kaggle_log_file)
    verification_path = Path(args.verification_output)
    if getattr(args, "diagnostic_path", None):
        diagnostic_path = Path(args.diagnostic_path).resolve()
    else:
        diagnostic_path = default_diagnostic_path(criteria)
    sidecar = diagnostic_path.with_suffix(diagnostic_path.suffix + ".sha256")
    if diagnostic_path.exists() or sidecar.exists():
        raise FileExistsError(f"append-only FD diagnostic already exists: {diagnostic_path}")

    output_files = {}
    if output_dir.is_dir():
        output_files = {path.relative_to(output_dir).as_posix(): sha256(path)
                        for path in sorted(output_dir.rglob("*")) if path.is_file()}
    manifest_path = output_dir / "sha256.json"
    manifest_consistent = None
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
            actual = {name: digest for name, digest in output_files.items()
                      if name not in {"sha256.json", "DONE"}}
            manifest_consistent = manifest == actual
        except Exception:
            manifest_consistent = False
    execution = None
    execution_path = output_dir / "execution_state.json"
    if execution_path.is_file():
        try:
            execution = read_json(execution_path)
        except Exception as parse_error:
            execution = {"parse_error": str(parse_error), "sha256": sha256(execution_path)}
    julia_log_path = output_dir / "fd_v16.log"
    julia_log = julia_log_path.read_text(errors="replace") if julia_log_path.is_file() else ""
    markers = {
        "run_started": [line.split()[1] for line in julia_log.splitlines()
                        if line.startswith("FD_RUN_STARTED ")],
        "solver_step_invoked": [line.split()[1] for line in julia_log.splitlines()
                                 if line.startswith("FD_SOLVER_STEP_INVOKED ")],
        "solver_step_returned": [line.split()[1] for line in julia_log.splitlines()
                                 if line.startswith("FD_SOLVER_STEP_RETURNED ")],
        "run_finished": [line.split()[1] for line in julia_log.splitlines()
                         if line.startswith("FD_RUN_DONE ")],
    }
    runner_outcome = None
    outcome_path = output_dir / "outcome.json"
    if outcome_path.is_file():
        try:
            runner_outcome = read_json(outcome_path)
        except Exception as parse_error:
            runner_outcome = {"parse_error": str(parse_error), "sha256": sha256(outcome_path)}
    host_report = None
    if verification_path.is_file():
        try:
            host_report = read_json(verification_path)
        except Exception:
            host_report = {"sha256": sha256(verification_path), "parseable": False}
    status_bytes = status_path.read_bytes() if status_path.is_file() else b""
    log_bytes = log_path.read_bytes() if log_path.is_file() else b""
    result = {
        "schema_version": 1,
        "kind": "sdf_directional_fd_flow16_diagnostic",
        "criteria_path": criteria_path.relative_to(ROOT).as_posix() if criteria_path.is_relative_to(ROOT) else str(criteria_path),
        "criteria_sha256": criteria_sha,
        "source_commit": criteria.get("source_commit"),
        "kernel_id": getattr(args, "kernel_id", None),
        "kernel_version": getattr(args, "kernel_version", None),
        "dataset_id": criteria.get("input_dataset_id"),
        "dataset_version": getattr(args, "dataset_version", None),
        "terminal_status": status_bytes.decode(errors="replace").strip() or "unavailable",
        "kaggle_status_sha256": sha256(status_path) if status_path.is_file() else None,
        "kaggle_log_sha256": sha256(log_path) if log_path.is_file() else None,
        "output_directory": str(output_dir),
        "output_files_sha256": output_files,
        "output_manifest_sha256": sha256(manifest_path) if manifest_path.is_file() else None,
        "output_manifest_consistent": manifest_consistent,
        "runner_execution_state": execution,
        "julia_progress_markers": markers,
        "runner_outcome": runner_outcome,
        "host_verification_report": host_report,
        "host_verifier_error": f"{type(error).__name__}: {error}",
        "host_verification_passed": False,
        "sdf_directional_fd_oracle_qualified": False,
        "sdf_directional_fd_flow16_qualified": False,
        "sdf_gradient_field_qualified": False,
        "gradient_qualified": False,
        "reverse_mode_qualified": False,
        "physical_profile_equivalence_qualified": False,
        "grid_or_domain_convergence_qualified": False,
        "absolute_downforce_qualified": False,
        "optimizer_qualified": False,
        "topology_qualified": False,
        "shape_update_allowed": False,
    }
    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = sha256(diagnostic_path)
    sidecar.write_text(digest + "\n")
    return diagnostic_path, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--criteria", type=Path, default=CRITERIA_DEFAULT)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--kernel-id", required=True)
    parser.add_argument("--kernel-version", type=int, required=True)
    parser.add_argument("--dataset-version", type=int, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--kaggle-log-file", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--diagnostic-path", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args)
    except Exception as error:
        diagnostic = write_diagnostic(args, error)
        if diagnostic:
            print(json.dumps({"verdict": "FAIL", "diagnostic_path": str(diagnostic[0]),
                              "diagnostic_sha256": diagnostic[1], "error": str(error)}, sort_keys=True),
                  file=sys.stderr)
        raise
    print(json.dumps({"verdict": report["verdict"], "criteria_sha256": report["criteria_sha256"],
                      "gates": report["gates"], "result_evidence_path": report.get("result_evidence_path"),
                      "result_evidence_sha256": report.get("result_evidence_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
