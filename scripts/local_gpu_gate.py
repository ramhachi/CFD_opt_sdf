#!/usr/bin/env python3
"""LOCAL-GPU-01 comparator; reads evidence only and creates one exclusive result.

    local_gpu_gate.py --runs docs/evidence/local_gpu_gate_2026_11 --out .../gate.json

R1a/R1b/R2a/R2b/R3/R4/R5 contain local_run.json and one parent kernel output.
R6 contains watchdog.csv, watchdog_status.json and completed repeat_*/local_run.json.
Missing evidence is INCOMPLETE; malformed or contradictory evidence fails closed.
C3/C4 numerical differences are descriptive, never cross-GPU qualification gates.
No Julia, solver, GPU measurement, cloud command, freeze or registration is run here.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from fd08_v2_campaign_io import (FORCE_COLUMNS, clipped_window, read_force_history,
                                 recompute_force_n, time_weighted_mean)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_harness import backend_profiles as BP  # noqa: E402

RUNS = ROOT / "docs/evidence/local_gpu_gate_2026_11"
LOCK = ROOT / "infra/local_gpu/lock.json"
PROFILE = "local_rtx4070ti"
GPU_NAME = "NVIDIA GeForce RTX 4070 Ti"
RELATIVE_TOLERANCE = 1e-6  # LOCAL-GPU-01 §5 C1 (Amendment 1: same local backend).
WATCHDOG_COLUMNS = ("elapsed_s", "clocks_sm_mhz", "temperature_gpu_c", "power_draw_w",
                    "memory_used_mib", "driver_reset", "error", "reset_monitor_error",
                    "utilization_gpu_pct", "gpu_uuid", "missing_reason", "memory_total_mib")
# LOCAL-GPU-01 §11.3(d): development defaults, not measured platform limits.
DEVELOPMENT_DEFAULTS = {"sample_gap_allowance_seconds": 90, "first_sample_allowance_seconds": 60,
                        "workload_gap_allowance_seconds": 90}
SUMMARY_IDENTITY_KEYS = (
    "case_id", "flow_dims", "flow_spacing_m", "flow_origin_m", "canonical_sdf_origin_m",
    "canonical_design_spacing_m", "canonical_state_label", "solver_length", "solver_time_unit_s",
    "solver_velocity", "solver_viscosity", "reynolds", "density_kg_m3", "dynamic_viscosity_pa_s",
    "freestream_mps", "reference_length_m", "reference_area_m2", "state_sha256", "state_npz_sha256",
    "source_surface_sha256", "phi_c_order_sha256", "phi_fortran_sha256", "device_roundtrip_sha256",
    "canonical_design_point_shape", "canonical_design_cell_shape", "burn_in_t_u_l", "t_end_target", "sample_every_solver_steps",
    "force_projection_semantics", "gpu_name", "gpu_uuid",
)
REFERENCE_IDENTITY_KEYS = tuple(key for key in SUMMARY_IDENTITY_KEYS if key not in ("gpu_name", "gpu_uuid"))
RUN_IDENTITY_KEYS = ("campaign_path", "source_commit", "runner_sha256", "backend_profile", "used_gpu_count",
                     "gpu_identity", "lock_sha256", "cuda_visible_devices", "cuda_device_order", "julia", "project", "runtime_project_pins",
                     "julia_depot", "filtered_environment")
UNC_SMOKE_TABLE = "docs/evidence/unc01_2026_10_20/u01/smoke/smoke_verify_table.json"
UNC_SMOKE_GATE = "docs/evidence/unc01_2026_10_20/u01/smoke/u0_smoke_gate.json"
UNC_ANALYSIS = "docs/evidence/unc01_2026_10_20/analysis.json"
# Paths locate immutable reference records. Their SHA values are read, never copied here.
REFERENCES = {
    "R1": {"output": "docs/evidence/harness01_smoke_2026_10_16/v1_1_1edbdcb/harness01_replay_a",
           "csv": "states/opt01b__parent/flow_16.forces.csv", "case_id": "flow_16"},
    "R2": {"output": "docs/evidence/unc01_2026_10_20/u01/smoke/unc01_u01_f24",
           "csv": "states/v18__parent__k0/flow_24.forces.csv", "case_id": "flow_24"},
    "R3": {"output": "docs/evidence/screen01_2026_10_30/wl/kernel_output/screen01_f_f32a",
           "csv": "states/v18__parent__k13/flow_32.forces.csv", "case_id": "flow_32"},
    "R4": {"output": "docs/evidence/screen01_2026_10_30/wl/kernel_output/screen01_f48_f48k13",
           "csv": "states/v18__parent__k13/flow_48.forces.csv", "case_id": "flow_48"},
}


class Missing(Exception):
    """Required evidence has not been acquired; never substitute a passing value."""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path):
    path = Path(path)
    if not path.is_file():
        raise Missing(f"missing {path}")
    return json.loads(path.read_text(), object_pairs_hook=_pairs, parse_float=_json_float, parse_constant=_json_constant)


def _json_float(token):
    value = float(token)
    require(math.isfinite(value), f"nonfinite JSON number: {token}")
    return value


def _json_constant(token):
    raise ValueError(f"nonfinite JSON: {token}")


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(path):
    path = Path(path)
    if not path.is_file():
        raise Missing(f"missing {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(root, value):
    require(isinstance(value, str) and value and not Path(value).is_absolute()
            and ".." not in Path(value).parts, f"unsafe relative path: {value!r}")
    path = Path(root) / value
    require(path.resolve().is_relative_to(Path(root).resolve()), f"path escapes evidence root: {value}")
    return path


def checked_sha(path, expected):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), f"invalid SHA for {path}")
    actual = sha(path)
    require(actual == expected, f"SHA-256 mismatch: {path}")
    return actual


def finite(value, what, positive=False):
    require(not isinstance(value, bool), f"invalid numeric {what}")
    number = float(value)
    require(math.isfinite(number) and (not positive or number > 0), f"nonfinite/nonpositive {what}")
    return number


def relative_difference(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def utc(value):
    require(isinstance(value, str), "missing/invalid UTC timestamp")
    result = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timestamp has no timezone")
    return result.astimezone(datetime.timezone.utc)


def part(function, *args):
    try:
        result = function(*args)
        canonical(result)  # Also rejects overflow in derived readouts before a PASS can escape.
        return result
    except Missing as exc:
        return {"status": "INCOMPLETE", "reason": str(exc)}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, csv.Error, OverflowError) as exc:
        return {"status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"}


def read_lock(path):
    lock = load(path)
    require(isinstance(lock, dict) and type(lock.get("schema_version")) is int and lock["schema_version"] == 1, "unknown lock schema")
    require(Path(path).read_bytes() == canonical(lock), "lock JSON is not canonical")
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file():
        raise Missing(f"missing {sidecar}")
    lock_sha = checked_sha(path, sidecar.read_text().strip())
    environment = lock["environment"]
    require(environment["backend_profile"] == PROFILE and environment["cuda_visible_devices"] == "0", "lock backend/CUDA pin differs")
    require(environment["gpu"]["name"] == GPU_NAME, "lock is not the RTX 4070 Ti profile")
    require(isinstance(environment["gpu"]["driver_version"], str) and environment["gpu"]["driver_version"].strip(), "lock driver version is unavailable")
    for identity in (environment["julia"]["sha256"], environment["julia"]["root_sha256"],
                     environment["julia_depot"]["manifest_packages_sha256"], environment["project"]["manifest_sha256"],
                     environment["project"]["project_sha256"]):
        require(isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{64}", identity), "lock Julia/Manifest SHA is unavailable")
    require(isinstance(environment["julia"]["root"], str) and Path(environment["julia"]["root"]).is_absolute(), "lock Julia root is unavailable")
    require(isinstance(environment["julia_depot"]["path"], str) and Path(environment["julia_depot"]["path"]).is_absolute(), "lock Julia depot is unavailable")
    require(isinstance(environment["julia"]["version"], str)
            and re.fullmatch(r"(?:julia version )?1\.12\.6", environment["julia"]["version"])
            and environment["project"]["path"] == "julia/CFDSDFWaterLilyT4", "lock Julia/GPU project differs")
    return lock_sha, environment


def read_run(directory, lock_sha, environment, repo):
    """A completed run with absent identity/output evidence is contradictory, not pending."""
    directory = Path(directory)
    try:
        return _read_run(directory, lock_sha, environment, repo)
    except Missing as exc:
        record = load(directory / "local_run.json") if (directory / "local_run.json").is_file() else {}
        if record.get("done") is True or any(directory.rglob("DONE")):
            raise ValueError(f"DONE run lacks required evidence: {exc}") from exc
        raise


def _read_run(directory, lock_sha, environment, repo):
    """Bind wrapper, environment, campaign, runner identity, manifest and parent artifacts."""
    directory = Path(directory)
    gpu = environment["gpu"]
    rec = load(directory / "local_run.json")
    require(isinstance(rec, dict) and type(rec.get("schema_version")) is int and rec["schema_version"] == 1, "unknown local_run schema")
    require(rec["lock_sha256"] == lock_sha and rec["backend_profile"] == PROFILE, "run lock/profile differs")
    require(rec["gpu_identity"] == gpu and rec["cuda_visible_devices"] == "0" and rec["cuda_device_order"] == "PCI_BUS_ID", "run GPU/CUDA identity differs from lock")
    require(type(rec["used_gpu_count"]) is int and rec["used_gpu_count"] == 1, "run did not pin exactly one GPU")
    require(rec["julia"] == environment["julia"] and rec["project"] == environment["project"], "run Julia/project differs from lock")
    require(rec["julia_depot"] == environment["julia_depot"], "run Julia depot differs from lock")
    require(isinstance(rec["filtered_environment"], dict)
            and all(isinstance(key, str) and isinstance(value, str) for key, value in rec["filtered_environment"].items()), "invalid filtered environment")
    require(rec["filtered_environment"].get("JULIA_DEPOT_PATH") == environment["julia_depot"]["path"], "runner did not use the locked Julia depot")
    require(type(rec["returncode"]) is int and rec["returncode"] == 0, "run exited unsuccessfully")
    if rec["done"] is not True:
        raise Missing(f"{directory}: run has no DONE")
    output = relative_path(directory, rec["kernel_output"])
    if not (output / "DONE").is_file():
        raise Missing(f"{directory}: missing runner DONE")
    require(not list(output.rglob("ERROR.txt")), f"{directory}: runner ERROR exists")
    hashes = rec["output_sha256"]
    require(isinstance(hashes, dict) and hashes, "wrapper has no output hashes")
    for rel, expected in hashes.items():
        checked_sha(relative_path(directory, rel), expected)
    for path in output.rglob("*"):
        if path.is_file():
            require(str(path.relative_to(directory)) in hashes, f"unrecorded kernel output: {path}")
    campaign_path = relative_path(repo, rec["campaign_path"])
    campaign = load(campaign_path)
    require(campaign.get("backend_profile") == PROFILE, "campaign backend profile differs")
    require(isinstance(rec["source_commit"], str) and re.fullmatch(r"[0-9a-f]{40}", rec["source_commit"]), "invalid source commit")
    identity = load(output / "run_identity.json")
    require(identity["filtered_environment"] == rec["filtered_environment"], "wrapper/runner filtered environment differs")
    require(identity["source_commit"] == rec["source_commit"] and identity["campaign_sha256"] == sha(campaign_path), "run source/campaign identity differs")
    require(isinstance(rec["runner_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", rec["runner_sha256"])
            and identity["runner_sha256"] == rec["runner_sha256"], "wrapper/runner SHA identity differs")
    runtime_pins = {"julia/CFDSDFWaterLilyT4/Manifest.toml": environment["project"]["manifest_sha256"],
                    "julia/CFDSDFWaterLilyT4/Project.toml": environment["project"]["project_sha256"]}
    require(rec["runtime_project_pins"] == runtime_pins
            and all(identity["pins"][key] == value for key, value in runtime_pins.items()), "actual runner Project/Manifest pins differ from lock")
    require(identity["cuda_visible_devices"] == "0" and identity["cuda_device_order"] == "PCI_BUS_ID", "runner CUDA pin differs")
    require(identity["backend_profile"] == PROFILE and type(identity["used_gpu_count"]) is int
            and identity["used_gpu_count"] == 1, "runner local profile/singleton identity differs")
    smi_path, probe_path = output / "nvidia_smi.csv", output / "gpu_device_probe.json"
    if not smi_path.is_file():
        raise Missing(f"missing {smi_path}")
    inventory = smi_path.read_text()
    selected = BP.select_worker_gpu(inventory, PROFILE)
    require(canonical(identity["selected_gpu"]) == canonical(selected), "runner selected GPU differs from observed inventory")
    probe = load(probe_path)
    observed_uuid = BP.check_probe(PROFILE, selected, probe)
    # The shared selector has validated one five-column row; read only its driver field here.
    driver = next(row[-1].strip() for row in csv.reader(inventory.splitlines()) if row and any(value.strip() for value in row))
    require(driver == gpu["driver_version"], "observed nvidia-smi driver differs from lock")
    require(selected["name"] == gpu["name"], "runner GPU name differs")
    if isinstance(gpu.get("uuid"), str):
        require(observed_uuid == gpu["uuid"], "runner GPU UUID differs")
    index = load(output / campaign.get("index_name", "harness_index.json"))
    require(index["status"] == "COMPLETE" and len(index["states"]) == 1, "gate expects exactly one completed parent state")
    state = index["states"][0]
    require(state["complete"] is True and type(state["exit_code"]) is int and state["exit_code"] == 0, "parent state is incomplete")
    state_dir = relative_path(output / "states", state["name"])
    case = index["case_id"]
    require(isinstance(case, str) and re.fullmatch(r"flow_(16|24|32|48)", case), "unknown gate flow case")
    csv_path, summary_path = state_dir / f"{case}.forces.csv", state_dir / f"{case}.summary.json"
    checked_sha(csv_path, state["forces_csv_sha256"])
    manifest_path = output / "output_manifest.json"
    manifest = load(manifest_path)["files"]
    require(isinstance(manifest, dict), "manifest files must be an object")
    for rel, expected in manifest.items():
        checked_sha(relative_path(output, rel), expected)
    for path in (output / "DONE", output / "run_identity.json", output / campaign.get("index_name", "harness_index.json"),
                 csv_path, summary_path, smi_path, probe_path):
        require(str(path.relative_to(output)) in manifest, f"required output absent from manifest: {path}")
    summary = load(summary_path)
    require(summary["case_id"] == case and summary["gpu_name"] == gpu["name"], "summary case/GPU differs")
    require(summary["gpu_uuid"] == observed_uuid, "summary GPU UUID differs from observed CUDA device")
    require(all(summary[key] is True for key in ("finite_u", "finite_p", "finite_forces")), "nonfinite solver state/forces")
    rows = read_force_history(csv_path)
    window = campaign["measurement"]["time_window_t_u_l"]
    require(window == [80.0, 120.0], "LOCAL-GPU-01 requires the registered [80,120] window")
    return {"directory": directory, "record": rec, "output": output, "campaign_path": campaign_path,
            "campaign": campaign, "summary": summary, "csv": csv_path, "rows": rows,
            "cuda_uuid": observed_uuid, "logical_device_count": probe["logical_device_count"],
            "input_sha256": {"local_run.json": sha(directory / "local_run.json"),
                             "output_manifest.json": sha(manifest_path), "forces.csv": sha(csv_path),
                             "summary.json": sha(summary_path)}}


def run_identity(record):
    identity = {key: record[key] for key in RUN_IDENTITY_KEYS}
    identity["filtered_environment"] = {key: value for key, value in identity["filtered_environment"].items()
                                        if key not in BP.VOLATILE_ENVIRONMENT_KEYS}
    return identity


def compare_samples(a, b):
    left, right = a["rows"], b["rows"]
    require(a["campaign"] == b["campaign"] and run_identity(a["record"]) == run_identity(b["record"]),
            "paired run campaign/source/runner/environment differs")
    require(all(a["summary"][key] == b["summary"][key] for key in SUMMARY_IDENTITY_KEYS), "paired run case/geometry/placement/scaling differs")
    require(len(left) == len(right), "force sample counts differ")
    require(all(x["step"] == y["step"] for x, y in zip(left, right)), "force sample step alignment differs")
    maximum = max(relative_difference(x[key], y[key]) for x, y in zip(left, right) for key in FORCE_COLUMNS)
    bitwise = a["csv"].read_bytes() == b["csv"].read_bytes()
    return {"bitwise": bitwise, "max_relative_difference": maximum,
            "class": "BITWISE" if bitwise else "TOLERANCE" if maximum <= RELATIVE_TOLERANCE else "FAIL",
            "samples": len(left), "sha256": [sha(a["csv"]), sha(b["csv"])]}


def c1(read):
    pairs = {label: compare_samples(read(label + "a"), read(label + "b")) for label in ("R1", "R2")}
    require(read("R1a")["summary"]["case_id"] == "flow_16" and read("R2a")["summary"]["case_id"] == "flow_24", "C1 smoke grids differ from R1/R2")
    classification = "FAIL" if any(pair["class"] == "FAIL" for pair in pairs.values()) else (
        "BITWISE" if all(pair["bitwise"] for pair in pairs.values()) else "TOLERANCE")
    return {"status": "FAIL" if classification == "FAIL" else "PASS", "class": classification,
            "relative_tolerance": RELATIVE_TOLERANCE, "pairs": pairs}


def c2(read, repo):
    records = {}
    for name in ("R2a", "R2b"):
        run = read(name)
        command = [sys.executable, str(ROOT / "scripts/local_gpu.py"), "verify", "--kernel-output", str(run["output"]),
                   "--campaign", str(run["campaign_path"]), "--smoke", "--source-commit", run["record"]["source_commit"]]
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
        records[name] = {"command": command, "returncode": completed.returncode,
                         "stdout": completed.stdout, "stderr": completed.stderr}
        require(completed.returncode == 0, f"{name}: harness verify --smoke failed: {completed.stderr.strip()}")
        table = json.loads(completed.stdout, object_pairs_hook=_pairs, parse_float=_json_float, parse_constant=_json_constant)
        require(table.get("integrity", {}).get("pass") is True and table.get("smoke") is True, f"{name}: invalid smoke verifier table")
    return {"status": "PASS", "runs": records}


def window_statistics(run):
    measurement = {"case": run["summary"], "time_window_t_u_l": [80.0, 120.0]}
    result = recompute_force_n(run["csv"], {"measurement": measurement})
    finite(result["force_scale_n_per_solver_force"], "physical force scale", positive=True)
    values = {key: result[key] for key in ("drag_n", "downforce_n")}
    for start, end in ((80.0, 100.0), (100.0, 120.0), (80.0, 120.0)):
        window = clipped_window(run["rows"], start, end)
        for column in FORCE_COLUMNS[2:]:
            values[f"{start:g}:{end:g}/{column}"] = time_weighted_mean(window, column)
    require(all(math.isfinite(value) for value in values.values()), "nonfinite derived window statistics")
    return values


def reference(repo, name):
    ref = REFERENCES[name]
    output = relative_path(repo, ref["output"])
    csv_path = relative_path(output, ref["csv"])
    summary_path = csv_path.with_name(csv_path.name.replace(".forces.csv", ".summary.json"))
    manifest_path = output / "output_manifest.json"
    manifest = load(manifest_path)["files"]
    checked_sha(csv_path, manifest[ref["csv"]])
    checked_sha(summary_path, manifest[str(summary_path.relative_to(output))])
    provenance = {"output_manifest": str(manifest_path.relative_to(repo)), "output_manifest_sha256": sha(manifest_path),
                  "forces_csv": str(csv_path.relative_to(repo)), "forces_csv_sha256": sha(csv_path), "summary_sha256": sha(summary_path)}
    if name == "R2":
        table_path, gate_path = relative_path(repo, UNC_SMOKE_TABLE), relative_path(repo, UNC_SMOKE_GATE)
        checked_sha(table_path, load(gate_path)["table_sha256"]["smoke_verify_table.json"])
        table = load(table_path)
        require(table["integrity"]["pass"] is True, "T4 smoke reference table is not verified")
        table_row = table["state_forces_n"]["f24"]["v18__parent__k0"]
        checked_sha(csv_path, table_row["forces_csv_sha256"])
        checked_sha(summary_path, table_row["summary_sha256"])
        provenance.update({"smoke_table": UNC_SMOKE_TABLE, "smoke_table_sha256": sha(table_path),
                           "smoke_gate": UNC_SMOKE_GATE, "smoke_gate_sha256": sha(gate_path)})
    summary = load(summary_path)
    require(summary["case_id"] == ref["case_id"] and summary["gpu_name"] == "Tesla T4", "retained reference case/GPU differs")
    return {"csv": csv_path, "rows": read_force_history(csv_path), "summary": summary, "provenance": provenance}


def unc_phase_scales(repo):
    path = relative_path(repo, UNC_ANALYSIS)
    sums_path = path.parent / "SHA256SUMS"
    if not sums_path.is_file():
        raise Missing(f"missing {sums_path}")
    matches = [line.split(maxsplit=1)[0] for line in sums_path.read_text().splitlines()
               if len(line.split(maxsplit=1)) == 2 and line.split(maxsplit=1)[1].lstrip("*") == UNC_ANALYSIS]
    require(len(matches) == 1, "UNC analysis must have exactly one registered SHA256SUMS entry")
    checked_sha(path, matches[0])
    values = {}

    def visit(value, key=""):
        if isinstance(value, dict):
            for name, child in value.items():
                subkey = f"{key}/{name}"
                if name == "sigma_d_n":
                    values[subkey] = finite(child, subkey)
                else:
                    visit(child, subkey)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{key}/{index}")

    visit(load(path))
    require(values, "UNC analysis has no phase sigma_d_n")
    return {"source": UNC_ANALYSIS, "sha256": sha(path), "values": values,
            "note": "UNC-01 paired-response phase SD, descriptive scale; not a cross-GPU acceptance bound"}


def c3(read, repo):
    comparisons = {}
    for label, run_name in (("R1", "R1a"), ("R2", "R2a"), ("R3", "R3"), ("R4", "R4")):
        local, retained = read(run_name), reference(repo, label)
        require(local["summary"]["case_id"] == REFERENCES[label]["case_id"], f"{label}: wrong reference grid")
        require(all(local["summary"][key] == retained["summary"][key] for key in REFERENCE_IDENTITY_KEYS),
                f"{label}: local/T4 physical identity differs (geometry, phase, grid, scaling or measurement contract)")
        a, b = window_statistics(local), window_statistics(retained)
        differences = {key: {"local": a[key], "t4": b[key], "difference": a[key] - b[key],
                             "relative_difference": abs(a[key] - b[key]) / max(abs(b[key]), 1e-300)} for key in ("drag_n", "downforce_n")}
        left, right = local["rows"], retained["rows"]
        aligned = len(left) == len(right) and all(a["step"] == b["step"] for a, b in zip(left, right))
        samples = {"status": "DESCRIPTIVE" if aligned else "INCOMPLETE", "local_samples": len(left), "t4_samples": len(right),
                   "alignment": "same registered solver-step indices; no time interpolation"}
        if aligned:
            samples.update(max_relative_difference=max(abs(a[key] - b[key]) / max(abs(b[key]), 1e-300)
                                                        for a, b in zip(left, right) for key in FORCE_COLUMNS[2:]),
                           max_time_offset_t_u_l=max(abs(a["t_u_l"] - b["t_u_l"]) for a, b in zip(left, right)))
        else:
            samples["reason"] = "sample counts or solver-step indices differ; no matched per-sample comparison is available"
        comparisons[label] = {"window_t_u_l": [80.0, 120.0], "forces": differences,
                              "max_relative_difference": max(row["relative_difference"] for row in differences.values()),
                              "samples": samples,
                              "reference": retained["provenance"]}
        if label in ("R3", "R4"):
            comparisons[label]["reference_throughput"] = throughput(retained["summary"])
    return {"status": "DESCRIPTIVE", "comparisons": comparisons, "unc_phase_scales": unc_phase_scales(repo),
            "relative_difference_definition": "abs(local-T4)/max(abs(T4),1e-300); no acceptance threshold"}


def throughput(summary):
    dims, steps = summary["flow_dims"], summary["steps"]
    require(isinstance(dims, list) and len(dims) == 3 and all(type(v) is int and v > 0 for v in dims), "invalid flow dimensions")
    require(type(steps) is int and steps > 0, "invalid solver step count")
    wall = finite(summary["wall_seconds"], "solver wall", positive=True)
    return {"steps": steps, "flow_dims": dims, "solver_wall_seconds": wall,
            "cell_steps_per_second": finite(math.prod(dims) * steps / wall, "cell-step throughput", positive=True),
            "throughput_definition": "registered steps*cells/wall; steps includes the initial warm-up step, wall excludes it"}


def c4(read, repo):
    runs = {}
    for name in ("R3", "R4"):
        run, retained = read(name), reference(repo, name)
        summary = run["summary"]
        require(summary["case_id"] == ("flow_32" if name == "R3" else "flow_48"), f"{name}: wrong throughput grid")
        local_rate, t4_rate = throughput(summary), throughput(retained["summary"])
        dims, steps, wall = local_rate["flow_dims"], local_rate["steps"], local_rate["solver_wall_seconds"]
        anchor = t4_rate["cell_steps_per_second"]
        runs[name] = {**local_rate,
                      "timed_cell_steps_per_second": (steps - 1) * math.prod(dims) / wall,
                      "timed_throughput_definition": "descriptive (steps-1)*cells/wall for a cold uninterrupted job",
                      "t4_anchor_cell_steps_per_second": anchor, "ratio_to_t4": local_rate["cell_steps_per_second"] / anchor,
                      "t4_anchor": t4_rate, "reference": retained["provenance"],
                      "wrapper_wall_seconds": run["record"].get("wall_seconds"), "peak_vram_mib": run["record"].get("peak_vram_mib")}
    return {"status": "DESCRIPTIVE", "runs": runs}


def c5(read, classification):
    if classification not in ("BITWISE", "TOLERANCE"):
        raise Missing("C1 has not established a reproducibility class")
    original, resumed = read("R3"), read("R5")
    require(run_identity(original["record"]) == run_identity(resumed["record"]), "R3/R5 campaign/source/runner/environment differs")
    require(all(original["summary"][key] == resumed["summary"][key] for key in SUMMARY_IDENTITY_KEYS), "R3/R5 geometry/placement/scaling differs")
    resume = resumed["record"].get("resume")
    if not resume:
        raise Missing("R5 has no interruption/resume provenance")
    require(resume["resumed"] is True, "R5 did not resume")
    root = resumed["directory"]
    checkpoint = relative_path(root, resume["checkpoint_path"])
    prior_path = relative_path(root, resume["interrupted_run"])
    checked_sha(checkpoint, resume["checkpoint_sha256"])
    checked_sha(prior_path, resume["interrupted_run_sha256"])
    prior = load(prior_path)
    require(run_identity(prior) == run_identity(resumed["record"]), "interrupted run campaign/source/runner/environment differs from R5")
    require(type(prior["returncode"]) is int and prior["returncode"] in (-9, -15, 137, 143)
            and prior["done"] is False and prior["lock_sha256"] == resumed["record"]["lock_sha256"], "R5 interruption is not a recorded killed run on this lock")
    original_checkpoint = resume["interrupted_checkpoint_path"]
    relative_path(root, original_checkpoint)  # validate the original map key without reading an external run
    require(prior["output_sha256"][original_checkpoint] == resume["checkpoint_sha256"], "loaded checkpoint SHA differs from interrupted run output map")
    require(original["summary"]["case_id"] == resumed["summary"]["case_id"] == "flow_32", "R3/R5 grid differs")
    events = sorted(resumed["output"].rglob("local_gpu_resume.json"))
    if not events:
        raise ValueError("DONE R5 has no job-produced resume identity event")
    require(len(events) == 1, "R5 has multiple job resume events")
    event = load(events[0])
    require(event["schema_version"] == 1 and event["resumed"] is True
            and event["checkpoint_sha256"] == resume["checkpoint_sha256"], "job resume event differs from wrapper checkpoint")
    require(type(event["checkpoint_step"]) is int and 0 < event["checkpoint_step"] < original["summary"]["steps"], "invalid resume checkpoint step")
    require(0 < finite(event["checkpoint_time_t_u_l"], "checkpoint time") < 120.0
            and isinstance(event["identity"], str) and re.fullmatch(r"[0-9a-f]{64}", event["identity"]), "invalid resume checkpoint time/identity")
    a, b = window_statistics(original), window_statistics(resumed)
    maximum = max(relative_difference(a[key], b[key]) for key in a)
    bitwise = all(a[key].hex() == b[key].hex() for key in a)
    passed = bitwise if classification == "BITWISE" else maximum <= RELATIVE_TOLERANCE
    return {"status": "PASS" if passed else "FAIL", "required_class": classification,
            "window_statistics_bitwise": bitwise, "max_relative_difference": maximum,
            "window_statistics": {key: {"R3": a[key], "R5": b[key]} for key in a}, "resume": resume,
            "job_resume_event": event, "job_resume_event_sha256": sha(events[0])}


def c6(read, runs):
    root = Path(runs) / "R6"
    watch, status_path = root / "watchdog.csv", root / "watchdog_status.json"
    status = load(status_path)
    checked_sha(watch, status["watchdog_sha256"])
    require(status["schema_version"] == 1 and status["interval_s"] == 60, "unknown watchdog schema/cadence")
    with watch.open(newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        require(len(columns) == len(set(columns)) and set(columns) == set(WATCHDOG_COLUMNS), "watchdog CSV schema differs")
        rows = list(reader)
    if not rows:
        raise Missing("R6 watchdog has no samples")
    available = status.get("driver_reset_monitor", {}).get("available")
    require(type(available) is bool, "unknown driver-reset monitor availability")
    require(isinstance(status["driver_reset_monitor"].get("source"), str)
            and status["driver_reset_monitor"]["source"], "driver-reset monitor source is absent")
    missing = [] if available else ["driver reset monitor is unavailable"]

    def blocking_messages(message, unavailable=False):
        # The collector joins field-labelled NVML diagnostics with semicolons.
        # §11.7 makes power/temperature record-only; absent UUID/capacity can
        # be supplied by the same run's CUDA probe / locked device identity.
        require(isinstance(message, str) and message.strip(), "invalid telemetry diagnostic")
        ignored = ("power.draw", "temperature.gpu") + (("uuid", "memory.total") if unavailable else ())
        return [item.strip() for item in message.split(";") if item.strip()
                and re.split(r"[:\s]", item.strip(), maxsplit=1)[0] not in ignored]

    for error in status.get("telemetry_errors", []):
        if isinstance(error, dict) and error.get("incomplete"):
            missing.extend(f"telemetry acquisition incomplete: {message}"
                           for message in blocking_messages(error["incomplete"], unavailable=True))
        else:
            require(isinstance(error, dict) and not blocking_messages(error.get("error")), f"R6 telemetry acquisition error: {error}")
    elapsed, samples = [], []

    def telemetry(row, key, required=True):
        value = row.get(key, "")
        if value in (None, "", "N/A", "[N/A]", "[Not Supported]"):
            if required:
                missing.append(f"sample {len(samples)}: missing {key}")
            return None
        return finite(value, key)

    for row in rows:
        require(not row.get("error") or not blocking_messages(row["error"]), f"R6 telemetry failed: {row.get('error')}")
        reset = row.get("driver_reset", "")
        require(reset in ("true", "false", ""), "unknown driver-reset observation")
        require(reset != "true", "R6 driver reset observed")
        if row.get("reset_monitor_error") or reset == "":
            missing.append(f"sample {len(samples)}: driver reset monitor is unavailable")
        elapsed.append(finite(row["elapsed_s"], "watchdog elapsed"))
        sample = {key: telemetry(row, key) for key in ("clocks_sm_mhz", "memory_used_mib", "utilization_gpu_pct")}
        sample["memory_total_mib"] = telemetry(row, "memory_total_mib", required=False)
        uuid = row.get("gpu_uuid", "")
        if uuid in (None, "", "N/A", "[N/A]", "[Not Supported]"):
            uuid = ""
        else:
            require(isinstance(uuid, str) and uuid.startswith("GPU-") and len(uuid) > 4, "invalid telemetry GPU UUID")
        sample["gpu_uuid"] = uuid
        for key in ("clocks_sm_mhz", "memory_used_mib"):
            require(sample[key] is None or sample[key] >= 0, f"invalid negative {key}")
        require(sample["memory_total_mib"] is None or sample["memory_total_mib"] > 0, "invalid device VRAM total")
        require(sample["utilization_gpu_pct"] is None or 0 <= sample["utilization_gpu_pct"] <= 100, "invalid GPU utilization")
        if sample["memory_used_mib"] is not None and sample["memory_total_mib"] is not None:
            require(sample["memory_used_mib"] <= sample["memory_total_mib"], "observed VRAM exceeds device total")
        samples.append(sample)
    require(all(right > left for left, right in zip(elapsed, elapsed[1:])), "watchdog elapsed time does not increase")
    records = sorted(path for path in root.glob("repeat_*/local_run.json"))
    if (root / "local_run.json").is_file():
        records.append(root / "local_run.json")
    if not records:
        raise Missing("R6 has no completed R3-sized run records")
    intervals, workloads, workload_wall, solver_wall = [], [], 0.0, 0.0
    original = read("R3")
    expected_dims, expected_uuid = original["summary"]["flow_dims"], original["cuda_uuid"]
    for sample in samples:
        require(not sample["gpu_uuid"] or sample["gpu_uuid"] == expected_uuid, "watchdog GPU UUID differs from CUDA probe")
    totals = [sample["memory_total_mib"] for sample in samples if sample["memory_total_mib"] is not None]
    require(not totals or all(total == totals[0] for total in totals), "device total VRAM changes during R6")
    total_source = "watchdog.csv:memory_total_mib"
    if not totals:
        capacity = original["record"]["gpu_identity"].get("memory_total")
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s+MiB", capacity) if isinstance(capacity, str) else None
        if match:
            totals = [finite(match[1], "locked device VRAM total", positive=True)]
            total_source = "locked_gpu_identity"
        else:
            missing.append("device total VRAM capacity is unavailable for the stability rule")
    for sample in samples:
        require(sample["memory_used_mib"] is None or not totals or sample["memory_used_mib"] <= totals[0], "observed VRAM exceeds device total")
    for path in records:
        run = read(str(path.parent.relative_to(Path(runs))))
        require(run["summary"]["case_id"] == "flow_32" and run["summary"]["flow_dims"] == expected_dims, "R6 repeat is not R3-sized")
        require(run["cuda_uuid"] == expected_uuid, "R6 repeat CUDA UUID differs from R3")
        rec = run["record"]
        started, finished = utc(rec["started_utc"]), utc(rec["finished_utc"])
        wall = finite(rec["wall_seconds"], "R6 repeat wall", positive=True)
        require(finished > started and wall <= (finished - started).total_seconds() + 1.0, "R6 repeat wall/timestamps disagree")
        workload_wall += wall
        solver_wall += finite(run["summary"]["wall_seconds"], "R6 solver wall", positive=True)
        intervals.append((started, finished))
        active_intervals = []
        for interval in rec.get("solver_intervals", []):
            active_start, active_end = utc(interval["started_utc"]), utc(interval["finished_utc"])
            require(started <= active_start < active_end <= finished, "solver-active interval exceeds wrapper interval")
            active_intervals.append((active_start, active_end))
        active_intervals.sort()
        require(all(right[0] >= left[1] for left, right in zip(active_intervals, active_intervals[1:])), "solver-active intervals overlap")
        workloads.append({"run": str(path.parent.relative_to(Path(runs))), "start": started, "finish": finished,
                          "active_intervals": active_intervals, "peak_vram_mib": rec.get("peak_vram_mib"),
                          "cuda_uuid": run["cuda_uuid"], "cuda_probe_sha256": sha(run["output"] / "gpu_device_probe.json")})
    intervals.sort()
    require(all(right[0] >= left[1] for left, right in zip(intervals, intervals[1:])), "R6 workload runs overlap")
    if any((right[0] - left[1]).total_seconds() > DEVELOPMENT_DEFAULTS["workload_gap_allowance_seconds"] for left, right in zip(intervals, intervals[1:])):
        missing.append("R6 workload has a gap above the development continuous-loop allowance")
    monitor_start, monitor_end = utc(status["started_utc"]), utc(status["finished_utc"])
    require(monitor_end > monitor_start, "R6 monitor timestamps disagree")
    wall = finite(status["wall_seconds"], "watchdog wall", positive=True)
    if status.get("completed") is not True or wall < 21600 or workload_wall < 21600:
        missing.append("R6 has not recorded a complete six-hour interval")
    if monitor_start > intervals[0][0] or monitor_end < intervals[-1][1]:
        missing.append("R6 monitor does not cover the workload interval")
    require(elapsed[0] >= 0 and elapsed[-1] <= wall + 1.0, "R6 sample elapsed times exceed monitor duration")
    if (len(elapsed) < 2 or elapsed[0] > DEVELOPMENT_DEFAULTS["first_sample_allowance_seconds"]
            or wall - elapsed[-1] > DEVELOPMENT_DEFAULTS["sample_gap_allowance_seconds"]
            or any(right - left > DEVELOPMENT_DEFAULTS["sample_gap_allowance_seconds"] for left, right in zip(elapsed, elapsed[1:]))):
        missing.append("R6 60-second watchdog coverage exceeds development sample allowances")
    workloads.sort(key=lambda item: item["start"])
    active_indices, stability_intervals, repeat_peaks, mature_peaks = [], [], {}, {}
    skipped_intervals, telemetry_identity, assigned_identity_samples = [], {}, set()
    for workload in workloads:
        peak_vram = workload["peak_vram_mib"]
        if peak_vram is None or isinstance(peak_vram, dict):
            missing.append(f"{workload['run']}: 10-second per-repeat VRAM peak is unavailable")
        else:
            peak_vram = finite(peak_vram, "recorded repeat VRAM peak")
            require(peak_vram >= 0 and (not totals or peak_vram <= totals[0]), "invalid recorded repeat VRAM peak")
            repeat_peaks[workload["run"]] = peak_vram
        groups, current, fallback_samples, nvml_samples = [], [], [], 0
        for index, (second, sample) in enumerate(zip(elapsed, samples)):
            timestamp = monitor_start + datetime.timedelta(seconds=second)
            in_workload = workload["start"] <= timestamp < workload["finish"] or timestamp == workload["finish"] == workloads[-1]["finish"]
            if in_workload:
                assigned_identity_samples.add(index)
                if sample["gpu_uuid"]:
                    nvml_samples += 1
                else:
                    fallback_samples.append(index)
            from_interval = any(start <= timestamp <= end for start, end in workload["active_intervals"])
            active = in_workload and (from_interval or (sample["utilization_gpu_pct"] is not None and sample["utilization_gpu_pct"] >= 50))
            if active:
                if current and second - elapsed[current[-1]] > DEVELOPMENT_DEFAULTS["sample_gap_allowance_seconds"]:
                    groups.append(current)
                    current = []
                current.append(index)
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)
        if not groups:
            missing.append(f"{workload['run']}: no solver-active samples")
        telemetry_identity[workload["run"]] = {"cuda_uuid": workload["cuda_uuid"],
            "cuda_probe_sha256": workload["cuda_probe_sha256"], "nvml_samples": nvml_samples,
            "cuda_probe_fallback_samples": fallback_samples, "fallback_source": "gpu_device_probe.json:default_device_uuid"}
        peak_values = []
        qualifying_intervals = 0
        for group in groups:
            active_indices.extend(group)
            # The start is measured from telemetry unless a recorded solver interval starts earlier.
            first_time = monitor_start + datetime.timedelta(seconds=elapsed[group[0]])
            starts = [start for start, end in workload["active_intervals"] if start <= first_time <= end]
            active_start = min([first_time, *starts])
            mature = [index for index in group if (monitor_start + datetime.timedelta(seconds=elapsed[index]) - active_start).total_seconds() >= 60]
            if len(mature) < 2:
                skipped_intervals.append({"run": workload["run"], "started_utc": active_start.isoformat(),
                    "last_sample_elapsed_s": elapsed[group[-1]], "samples": len(group), "mature_samples": len(mature),
                    "reason": "fewer than two samples after the first 60 seconds; VRAM interval skipped"})
                continue
            qualifying_intervals += 1
            values = [samples[index]["memory_used_mib"] for index in mature if samples[index]["memory_used_mib"] is not None]
            if len(values) < 2 or not totals:
                missing.append(f"{workload['run']}: insufficient VRAM samples after the first 60 seconds of an active interval")
                continue
            variation = (max(values) - min(values)) / totals[0]
            require(variation <= 0.05, f"R6 within-interval VRAM variation {variation:g} exceeds 5 percent of device total")
            stability_intervals.append({"run": workload["run"], "started_utc": active_start.isoformat(),
                                        "mature_samples": len(values), "vram_min_mib": min(values), "vram_max_mib": max(values),
                                        "range_fraction_of_device_total": variation})
            peak_values.extend(values)
        if not qualifying_intervals:
            missing.append(f"{workload['run']}: needs at least one solver-active interval with two samples after the first 60 seconds")
        if peak_values:
            mature_peaks[workload["run"]] = max(peak_values)
    active_clocks = [samples[index]["clocks_sm_mhz"] for index in active_indices if samples[index]["clocks_sm_mhz"] is not None]
    clock_drop = 0.0
    if active_clocks:
        require(all(clock > 0 for clock in active_clocks), "nonpositive solver-active GPU clock")
        peak = active_clocks[0]
        for clock in active_clocks:
            peak = max(peak, clock)
            clock_drop = max(clock_drop, (peak - clock) / peak)
        require(clock_drop < 0.15, f"R6 solver-active clock drop {clock_drop:g} is not below 15 percent")
    else:
        missing.append("R6 has no observed solver-active clocks")
    peaks = list(repeat_peaks.values())
    repeat_variation = (max(peaks) - min(peaks)) / max(peaks) if peaks and max(peaks) > 0 else 0.0
    require(repeat_variation <= 0.02, f"R6 repeat VRAM peak variation {repeat_variation:g} exceeds 2 percent of the maximum repeat peak")
    if len(peaks) < 2:
        missing.append("R6 needs at least two repeats with observed stable VRAM peaks")
    vram = [sample["memory_used_mib"] for sample in samples if sample["memory_used_mib"] is not None]
    return {"status": "INCOMPLETE" if missing else "PASS", "missing_evidence": sorted(set(missing)),
            "samples": len(rows), "solver_active_samples": len(active_indices), "duration_seconds": wall, "workload_wall_seconds": workload_wall,
            "solver_wall_seconds_total": solver_wall, "solver_fraction_of_wrapper": solver_wall / workload_wall,
            "workload_scope": "six hours of a cold-process wrapper loop, not six GPU-active hours; solver wall excludes the initial warm-up step",
            "clock_observations_mhz": {"first": active_clocks[:1], "peak": max(active_clocks, default=None), "minimum": min(active_clocks, default=None)},
            "clock_drop_fraction": clock_drop, "clock_rule": "maximum historical-peak drawdown over solver-active samples only; utilization>=50% OR recorded solver interval",
            "vram_min_mib": min(vram, default=None), "vram_max_mib": max(vram, default=None),
            "vram_device_total_mib": totals[0] if totals else None, "vram_device_total_source": total_source if totals else None,
            "vram_rule": "intervals with at least two samples after first 60 seconds: range/device total<=0.05; at least one interval per repeat; across repeats (max peak-min peak)/max peak<=0.02",
            "vram_peak_scope": "per-repeat local_run.json peak_vram_mib uses all 10-second wrapper samples, including startup; mature watchdog peaks are separate descriptive readouts",
            "vram_intervals": stability_intervals, "vram_repeat_peaks_mib": repeat_peaks, "vram_mature_watchdog_peaks_mib": mature_peaks,
            "vram_skipped_intervals": skipped_intervals,
            "vram_repeat_peak_variation": repeat_variation,
            "required_telemetry_fields": ["memory.used", "utilization.gpu", "clocks.sm"],
            "record_only_telemetry_fields": ["power.draw", "temperature.gpu"],
            "telemetry_acquisition_notes": status.get("telemetry_errors", []),
            "telemetry_identity": telemetry_identity,
            "missing_nvml_uuid_samples_outside_workloads": [index for index, sample in enumerate(samples)
                if not sample["gpu_uuid"] and index not in assigned_identity_samples],
            "development_defaults": DEVELOPMENT_DEFAULTS,
            "driver_reset_monitor": status["driver_reset_monitor"],
            "reset_scope": "no reset observed by this monitor; other reset/event classes are not physically excluded",
            "completed_runs": len(records), "watchdog_sha256": sha(watch), "watchdog_status_sha256": sha(status_path)}


def common_cuda_identity(runs, environment):
    """Check available probes independently of descriptive R4 completion/artifacts."""
    directories = [(name, Path(runs) / name, name != "R4") for name in ("R1a", "R1b", "R2a", "R2b", "R3", "R4", "R5")]
    r6 = sorted(path for path in (Path(runs) / "R6").glob("repeat_*") if path.is_dir())
    if (Path(runs) / "R6/local_run.json").is_file():
        r6.append(Path(runs) / "R6")
    directories.extend((str(path.relative_to(runs)), path, True) for path in r6)
    observed, unavailable = {}, []
    if not r6:
        unavailable.append("R6: no repeat probes recorded")
    for name, directory, mandatory in directories:
        probes = sorted(directory.rglob("gpu_device_probe.json"))
        if not probes:
            require(not any(directory.rglob("DONE")), f"{name}: DONE run lacks CUDA identity probe")
            if mandatory:
                unavailable.append(f"{name}: CUDA identity probe is missing")
            continue
        require(len(probes) == 1, f"{name}: ambiguous CUDA identity probes")
        probe = load(probes[0])
        uuid = BP.check_probe(PROFILE, {"uuid": ""}, probe)
        require(isinstance(uuid, str) and uuid.startswith("GPU-") and len(uuid) > 4, f"{name}: missing CUDA UUID")
        observed[name] = {"cuda_uuid": uuid, "logical_device_count": probe["logical_device_count"],
                          "probe_sha256": sha(probes[0])}
    uuids = {item["cuda_uuid"] for item in observed.values()}
    require(len(uuids) <= 1, "R1–R6 CUDA UUIDs differ; the environment gate requires one physical GPU")
    uuid = next(iter(uuids), None)
    if isinstance(environment["gpu"].get("uuid"), str):
        require(uuid is None or uuid == environment["gpu"]["uuid"], "CUDA UUID differs from lock")
    return {"status": "INCOMPLETE" if unavailable else "PASS", "cuda_uuid": uuid, "runs": observed,
            "missing_evidence": unavailable, "r4_probe_recorded": "R4" in observed,
            "used_gpu_count_evidence": "gpu_device_probe.json:logical_device_count",
            "used_gpu_count_note": "runner used_gpu_count is bookkeeping; the observed probe is the singleton evidence"}


def evaluate(runs=RUNS, *, lock=LOCK, repo=ROOT):
    runs, repo = Path(runs), Path(repo)
    lock_result = part(read_lock, lock)
    if isinstance(lock_result, dict):
        return {"status": lock_result["status"], "failed_criteria": ["lock"] if lock_result["status"] == "FAIL" else [],
                "incomplete_criteria": ["lock"] if lock_result["status"] == "INCOMPLETE" else [], "criteria": {"lock": lock_result},
                "excluded_identity_environment_variables": list(BP.VOLATILE_ENVIRONMENT_KEYS)}
    lock_sha, environment = lock_result
    cache = {}

    def read(name):
        if name not in cache:
            cache[name] = read_run(relative_path(runs, name), lock_sha, environment, repo)
        return cache[name]

    criteria = {"C1": part(c1, read), "C2": part(c2, read, repo), "C3": part(c3, read, repo), "C4": part(c4, read, repo)}
    criteria["C5"] = part(c5, read, criteria["C1"].get("class"))
    criteria["C6"] = part(c6, read, runs)
    criteria["C_identity"] = part(common_cuda_identity, runs, environment)
    required = ("C1", "C2", "C5", "C6", "C_identity")
    failed = [name for name in required if criteria[name]["status"] == "FAIL"]
    missing = [name for name in required if criteria[name]["status"] == "INCOMPLETE"]
    result = {"schema_version": 1, "status": "FAIL" if failed else "INCOMPLETE" if missing else "PASS",
              "failed_criteria": failed, "incomplete_criteria": missing, "criteria": criteria,
              "descriptive_issues": {name: criteria[name]["status"] for name in ("C3", "C4") if criteria[name]["status"] in ("FAIL", "INCOMPLETE")},
              "evidence_class": "engineering environment capability gate; no physics qualification",
              "lock_sha256": lock_sha, "gpu_identity": environment["gpu"],
              "common_cuda_uuid": criteria["C_identity"].get("cuda_uuid"),
              "excluded_identity_environment_variables": list(BP.VOLATILE_ENVIRONMENT_KEYS),
              "used_gpu_count_evidence": "gpu_device_probe.json:logical_device_count",
              "development_defaults": DEVELOPMENT_DEFAULTS,
              "comparator_sha256": sha(Path(__file__)),
              "evaluated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "run_inputs_sha256": {name: run["input_sha256"] for name, run in cache.items()}}
    if criteria["C1"]["status"] == "PASS":
        result["local_first_state_reference"] = {label: {"lock_sha256": lock_sha,
            "class": criteria["C1"]["class"], "forces_csv_sha256": criteria["C1"]["pairs"][label]["sha256"][0]}
            for label in ("R1", "R2")}
    return result


def write_gate(runs, out, *, lock=LOCK, repo=ROOT):
    """Publish a complete temporary record atomically, without replacing an existing gate."""
    out = Path(out)
    if os.path.lexists(out):
        raise FileExistsError(f"refusing to overwrite existing gate: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = evaluate(runs, lock=lock, repo=repo)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=out.parent, prefix=f".{out.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(canonical(result))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, out)  # Same-directory hard link is atomic and refuses any existing destination.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--lock", type=Path, default=LOCK)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = write_gate(args.runs, args.out or args.runs / "gate.json", lock=args.lock)
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps({"status": result["status"], "failed_criteria": result["failed_criteria"],
                      "incomplete_criteria": result["incomplete_criteria"]}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
