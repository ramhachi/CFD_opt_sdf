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
import re
import subprocess
import sys
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
T4_THROUGHPUT = {"R3": 5.5e7, "R4": 5.6e7}  # LOCAL-GPU-01 §5 C4, cell-step/s.
WATCHDOG_COLUMNS = ("elapsed_s", "clocks_sm_mhz", "temperature_gpu_c", "power_draw_w",
                    "memory_used_mib", "driver_reset", "error", "reset_monitor_error")
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
                     "gpu_identity", "lock_sha256", "cuda_visible_devices", "cuda_device_order", "julia", "project", "runtime_project_pins")
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
    for identity in (environment["julia"]["sha256"], environment["project"]["manifest_sha256"], environment["project"]["project_sha256"]):
        require(isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{64}", identity), "lock Julia/Manifest SHA is unavailable")
    require(isinstance(environment["julia"]["version"], str)
            and re.fullmatch(r"(?:julia version )?1\.12\.6", environment["julia"]["version"])
            and environment["project"]["path"] == "julia/CFDSDFWaterLilyT4", "lock Julia/GPU project differs")
    return lock_sha, environment


def read_run(directory, lock_sha, environment, repo):
    """Bind wrapper, environment, campaign, runner identity, manifest and parent artifacts."""
    directory = Path(directory)
    gpu = environment["gpu"]
    rec = load(directory / "local_run.json")
    require(isinstance(rec, dict) and type(rec.get("schema_version")) is int and rec["schema_version"] == 1, "unknown local_run schema")
    require(rec["lock_sha256"] == lock_sha and rec["backend_profile"] == PROFILE, "run lock/profile differs")
    require(rec["gpu_identity"] == gpu and rec["cuda_visible_devices"] == "0" and rec["cuda_device_order"] == "PCI_BUS_ID", "run GPU/CUDA identity differs from lock")
    require(type(rec["used_gpu_count"]) is int and rec["used_gpu_count"] == 1, "run did not pin exactly one GPU")
    require(rec["julia"] == environment["julia"] and rec["project"] == environment["project"], "run Julia/project differs from lock")
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
    observed_uuid = BP.check_probe(PROFILE, selected, load(probe_path))
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
            "input_sha256": {"local_run.json": sha(directory / "local_run.json"),
                             "output_manifest.json": sha(manifest_path), "forces.csv": sha(csv_path),
                             "summary.json": sha(summary_path)}}


def compare_samples(a, b):
    left, right = a["rows"], b["rows"]
    require(a["campaign"] == b["campaign"] and all(a["record"][key] == b["record"][key] for key in RUN_IDENTITY_KEYS),
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
        command = [sys.executable, str(ROOT / "scripts/harness.py"), "verify", str(run["output"]),
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
        comparisons[label] = {"window_t_u_l": [80.0, 120.0], "forces": differences,
                              "max_relative_difference": max(row["relative_difference"] for row in differences.values()),
                              "reference": retained["provenance"]}
    return {"status": "DESCRIPTIVE", "comparisons": comparisons, "unc_phase_scales": unc_phase_scales(repo),
            "relative_difference_definition": "abs(local-T4)/max(abs(T4),1e-300); no acceptance threshold"}


def c4(read):
    runs = {}
    for name, anchor in T4_THROUGHPUT.items():
        run = read(name)
        summary = run["summary"]
        require(summary["case_id"] == ("flow_32" if name == "R3" else "flow_48"), f"{name}: wrong throughput grid")
        dims, steps = summary["flow_dims"], summary["steps"]
        require(isinstance(dims, list) and len(dims) == 3 and all(type(v) is int and v > 0 for v in dims), "invalid flow dimensions")
        require(type(steps) is int and steps > 0, "invalid solver step count")
        wall = finite(summary["wall_seconds"], "solver wall", positive=True)
        speed = math.prod(dims) * steps / wall
        runs[name] = {"steps": steps, "flow_dims": dims, "solver_wall_seconds": wall, "cell_steps_per_second": speed,
                      "throughput_definition": "registered steps*cells/wall; steps includes the initial warm-up step, wall excludes it",
                      "timed_cell_steps_per_second": (steps - 1) * math.prod(dims) / wall,
                      "timed_throughput_definition": "descriptive (steps-1)*cells/wall for a cold uninterrupted job",
                      "t4_anchor_cell_steps_per_second": anchor, "ratio_to_t4": speed / anchor,
                      "wrapper_wall_seconds": run["record"].get("wall_seconds"), "peak_vram_mib": run["record"].get("peak_vram_mib")}
    return {"status": "DESCRIPTIVE", "runs": runs}


def c5(read, classification):
    if classification not in ("BITWISE", "TOLERANCE"):
        raise Missing("C1 has not established a reproducibility class")
    original, resumed = read("R3"), read("R5")
    require(all(original["record"][key] == resumed["record"][key] for key in RUN_IDENTITY_KEYS), "R3/R5 campaign/source/runner/environment differs")
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
    require(all(prior[key] == resumed["record"][key] for key in RUN_IDENTITY_KEYS), "interrupted run campaign/source/runner/environment differs from R5")
    require(type(prior["returncode"]) is int and prior["returncode"] in (-9, -15, 137, 143)
            and prior["done"] is False and prior["lock_sha256"] == resumed["record"]["lock_sha256"], "R5 interruption is not a recorded killed run on this lock")
    original_checkpoint = resume["interrupted_checkpoint_path"]
    relative_path(root, original_checkpoint)  # validate the original map key without reading an external run
    require(prior["output_sha256"][original_checkpoint] == resume["checkpoint_sha256"], "loaded checkpoint SHA differs from interrupted run output map")
    require(original["summary"]["case_id"] == resumed["summary"]["case_id"] == "flow_32", "R3/R5 grid differs")
    events = sorted(resumed["output"].rglob("local_gpu_resume.json"))
    if not events:
        raise Missing("R5 has no job-produced resume event")
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
        require(tuple(reader.fieldnames or ()) == WATCHDOG_COLUMNS, "watchdog CSV schema differs")
        rows = list(reader)
    if not rows:
        raise Missing("R6 watchdog has no samples")
    available = status.get("driver_reset_monitor", {}).get("available")
    require(type(available) is bool, "unknown driver-reset monitor availability")
    require(isinstance(status["driver_reset_monitor"].get("source"), str)
            and status["driver_reset_monitor"]["source"], "driver-reset monitor source is absent")
    require(not status.get("telemetry_errors"), "R6 telemetry acquisition errors were recorded")
    missing_reset = not available
    clocks, vram, elapsed = [], [], []
    for row in rows:
        require(not row["error"], f"R6 telemetry failed: {row['error']}")
        require(row["driver_reset"] in ("true", "false", ""), "unknown driver-reset observation")
        require(row["driver_reset"] != "true", "R6 driver reset observed")
        missing_reset |= bool(row["reset_monitor_error"]) or row["driver_reset"] == ""
        elapsed.append(finite(row["elapsed_s"], "watchdog elapsed"))
        clocks.append(finite(row["clocks_sm_mhz"], "GPU clock", positive=True))
        vram.append(finite(row["memory_used_mib"], "VRAM"))
        finite(row["temperature_gpu_c"], "GPU temperature")
        finite(row["power_draw_w"], "GPU power")
    require(all(right > left for left, right in zip(elapsed, elapsed[1:])), "watchdog elapsed time does not increase")
    peak, clock_drop = clocks[0], 0.0
    for clock in clocks:
        peak = max(peak, clock)
        clock_drop = max(clock_drop, (peak - clock) / peak)
    require(clock_drop < 0.15, f"R6 clock drop {clock_drop:g} is not below 15 percent")
    records = sorted(path for path in root.glob("repeat_*/local_run.json"))
    if (root / "local_run.json").is_file():
        records.append(root / "local_run.json")
    if not records:
        raise Missing("R6 has no completed R3-sized run records")
    intervals, workload_wall, solver_wall = [], 0.0, 0.0
    expected_dims = read("R3")["summary"]["flow_dims"]
    for path in records:
        run = read(str(path.parent.relative_to(Path(runs))))
        require(run["summary"]["case_id"] == "flow_32" and run["summary"]["flow_dims"] == expected_dims, "R6 repeat is not R3-sized")
        rec = run["record"]
        started, finished = utc(rec["started_utc"]), utc(rec["finished_utc"])
        wall = finite(rec["wall_seconds"], "R6 repeat wall", positive=True)
        require(finished > started and wall <= (finished - started).total_seconds() + 1.0, "R6 repeat wall/timestamps disagree")
        workload_wall += wall
        solver_wall += finite(run["summary"]["wall_seconds"], "R6 solver wall", positive=True)
        intervals.append((started, finished))
    intervals.sort()
    require(all(right[0] >= left[1] for left, right in zip(intervals, intervals[1:])), "R6 workload runs overlap")
    if any((right[0] - left[1]).total_seconds() > 90 for left, right in zip(intervals, intervals[1:])):
        raise Missing("R6 workload has a gap above the fixed 90-second continuous-loop allowance")
    monitor_start, monitor_end = utc(status["started_utc"]), utc(status["finished_utc"])
    require(monitor_end > monitor_start, "R6 monitor timestamps disagree")
    if missing_reset:
        raise Missing("R6 driver reset monitor was unavailable for at least one sample")
    wall = finite(status["wall_seconds"], "watchdog wall", positive=True)
    if status.get("completed") is not True or wall < 21600 or workload_wall < 21600:
        raise Missing("R6 has not recorded a complete six-hour interval")
    if monitor_start > intervals[0][0] or monitor_end < intervals[-1][1]:
        raise Missing("R6 monitor does not cover the workload interval")
    require(elapsed[0] >= 0 and elapsed[-1] <= wall + 1.0, "R6 sample elapsed times exceed monitor duration")
    if len(elapsed) < 2 or elapsed[0] > 60 or wall - elapsed[-1] > 90 or max(right - left for left, right in zip(elapsed, elapsed[1:])) > 90:
        raise Missing("R6 60-second watchdog coverage has a gap above 90 seconds")
    return {"status": "PASS", "samples": len(rows), "duration_seconds": wall, "workload_wall_seconds": workload_wall,
            "solver_wall_seconds_total": solver_wall, "solver_fraction_of_wrapper": solver_wall / workload_wall,
            "workload_scope": "six hours of a cold-process wrapper loop, not six GPU-active hours; solver wall excludes the initial warm-up step",
            "clock_first_mhz": clocks[0], "clock_peak_mhz": max(clocks), "clock_min_mhz": min(clocks), "clock_drop_fraction": clock_drop,
            "clock_rule": "maximum drawdown from the historical clock peak; all samples, including idle, retained",
            "clock_scope_limitation": "cold startup and between-process idle can fail this fixed clock-stability rule; a failure does not prove thermal throttling",
            "vram_min_mib": min(vram), "vram_max_mib": max(vram), "vram_range_mib": max(vram) - min(vram),
            "vram_rule": "descriptive range; no numerical stability threshold is specified",
            "driver_reset_monitor": status["driver_reset_monitor"],
            "reset_scope": "no reset observed by this monitor; other reset/event classes are not physically excluded",
            "completed_runs": len(records), "watchdog_sha256": sha(watch), "watchdog_status_sha256": sha(status_path)}


def evaluate(runs=RUNS, *, lock=LOCK, repo=ROOT):
    runs, repo = Path(runs), Path(repo)
    lock_result = part(read_lock, lock)
    if isinstance(lock_result, dict):
        return {"status": lock_result["status"], "failed_criteria": ["lock"] if lock_result["status"] == "FAIL" else [],
                "incomplete_criteria": ["lock"] if lock_result["status"] == "INCOMPLETE" else [], "criteria": {"lock": lock_result}}
    lock_sha, environment = lock_result
    cache = {}

    def read(name):
        if name not in cache:
            cache[name] = read_run(relative_path(runs, name), lock_sha, environment, repo)
        return cache[name]

    criteria = {"C1": part(c1, read), "C2": part(c2, read, repo), "C3": part(c3, read, repo), "C4": part(c4, read)}
    criteria["C5"] = part(c5, read, criteria["C1"].get("class"))
    criteria["C6"] = part(c6, read, runs)
    failed = [name for name, value in criteria.items() if value["status"] == "FAIL"]
    missing = [name for name, value in criteria.items() if value["status"] == "INCOMPLETE"]
    result = {"schema_version": 1, "status": "FAIL" if failed else "INCOMPLETE" if missing else "PASS",
              "failed_criteria": failed, "incomplete_criteria": missing, "criteria": criteria,
              "evidence_class": "engineering environment capability gate; no physics qualification",
              "lock_sha256": lock_sha, "gpu_identity": environment["gpu"],
              "comparator_sha256": sha(Path(__file__)),
              "evaluated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "run_inputs_sha256": {name: run["input_sha256"] for name, run in cache.items()}}
    if criteria["C1"]["status"] == "PASS":
        result["local_first_state_reference"] = {label: {"lock_sha256": lock_sha,
            "class": criteria["C1"]["class"], "forces_csv_sha256": criteria["C1"]["pairs"][label]["sha256"][0]}
            for label in ("R1", "R2")}
    return result


def write_gate(runs, out, *, lock=LOCK, repo=ROOT):
    """Reserve output before invoking the verifier; even an interrupted attempt is not overwritten."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as handle:
        result = evaluate(runs, lock=lock, repo=repo)
        handle.write(canonical(result))
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
