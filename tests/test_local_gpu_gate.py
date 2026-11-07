"""LOCAL-GPU-01: deterministic synthetic evidence; never starts Julia or a GPU."""
import csv
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import local_gpu_gate as G  # noqa: E402
from fd08_v2_campaign_io import FORCE_COLUMNS  # noqa: E402


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def force_csv(path, factor=1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FORCE_COLUMNS)
        for step, time in enumerate((0.0, 79.0, 90.0, 100.0, 121.0)):
            writer.writerow((step * 8, time, 2 * factor, 0.0, -3 * factor,
                             2 * factor, 3 * factor, factor, 0.0, -2 * factor,
                             factor, 0.0, -factor))


def summary(case_id):
    return {"case_id": case_id, "flow_dims": [10, 8, 6], "steps": 100,
            "wall_seconds": 2.0, "density_kg_m3": 1.0, "freestream_mps": [1.0, 0.0, 0.0],
            "flow_spacing_m": 0.5, "burn_in_t_u_l": 80.0, "t_end_target": 120.0,
            "flow_origin_m": [-1.0, -1.0, -1.0], "canonical_sdf_origin_m": [-0.5, -0.5, -0.5],
            "canonical_design_spacing_m": 0.5, "canonical_state_label": "synthetic", "solver_length": 1.0,
            "canonical_design_point_shape": [11, 9, 7], "canonical_design_cell_shape": [10, 8, 6],
            "sample_every_solver_steps": 8,
            "solver_time_unit_s": 0.5, "solver_velocity": 1.0, "solver_viscosity": 0.01, "reynolds": 100.0,
            "dynamic_viscosity_pa_s": 0.01, "reference_length_m": 1.0, "reference_area_m2": 1.0,
            "state_sha256": "1" * 64, "state_npz_sha256": "2" * 64, "source_surface_sha256": "3" * 64,
            "phi_c_order_sha256": "4" * 64, "phi_fortran_sha256": "5" * 64, "device_roundtrip_sha256": "5" * 64,
            "force_projection_semantics": "drag=+Fx; downforce=-Fz",
            "finite_u": True, "finite_p": True, "finite_forces": True,
            "drag_time_weighted_n": 0.5, "downforce_time_weighted_n": 0.75,
            "gpu_name": "NVIDIA GeForce RTX 4070 Ti", "gpu_uuid": "GPU-test"}


def make_run(root, name, lock_sha, case_id="flow_32"):
    run = root / name
    out = run / "kernel"
    campaign_path = next(parent / "campaign.json" for parent in root.parents if (parent / "campaign.json").is_file())
    environment = json.loads((campaign_path.parent / "lock.json").read_text())["environment"]
    csv_path = out / "states/parent" / f"{case_id}.forces.csv"
    force_csv(csv_path)
    write_json(csv_path.with_name(f"{case_id}.summary.json"), summary(case_id))
    write_json(out / "harness_index.json", {"kernel": "k", "case_id": case_id,
               "status": "COMPLETE", "states": [{"name": "parent", "complete": True,
               "exit_code": 0, "forces_csv_sha256": digest(csv_path)}]})
    write_json(out / "run_identity.json", {"selected_gpu": {"index": 0, "name": "NVIDIA GeForce RTX 4070 Ti", "uuid": "GPU-test"},
               "cuda_visible_devices": "0", "cuda_device_order": "PCI_BUS_ID", "source_commit": "a" * 40, "used_gpu_count": 1,
               "campaign_sha256": digest(campaign_path), "backend_profile": "local_rtx4070ti", "runner_sha256": "c" * 64,
               "filtered_environment": {"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_DEPOT_PATH": environment["julia_depot"]["path"]},
               "pins": {"julia/CFDSDFWaterLilyT4/Manifest.toml": environment["project"]["manifest_sha256"],
                        "julia/CFDSDFWaterLilyT4/Project.toml": environment["project"]["project_sha256"]}})
    (out / "nvidia_smi.csv").write_text("0, NVIDIA GeForce RTX 4070 Ti, GPU-test, 12282 MiB, 555.0\n")
    write_json(out / "gpu_device_probe.json", {"logical_device_count": 1,
               "visible_gpu_names": ["NVIDIA GeForce RTX 4070 Ti"], "cuda_device_order": "PCI_BUS_ID",
               "cuda_visible_devices": "0", "visible_gpu_uuids": ["GPU-test"], "default_device_uuid": "GPU-test"})
    if name == "R5":
        write_json(csv_path.parent / "local_gpu_resume.json", {"schema_version": 1, "resumed": True,
                   "checkpoint_sha256": hashlib.sha256(b"checkpoint").hexdigest(),
                   "checkpoint_step": 48, "checkpoint_time_t_u_l": 60.0, "identity": "d" * 64})
    (out / "DONE").write_text("done\n")
    write_json(out / "output_manifest.json", {"files": {
        str(path.relative_to(out)): digest(path) for path in out.rglob("*")
        if path.is_file() and path.name != "output_manifest.json"}})
    rec = {"schema_version": 1, "backend_profile": "local_rtx4070ti", "lock_sha256": lock_sha,
           "gpu_identity": environment["gpu"], "julia": environment["julia"], "project": environment["project"], "used_gpu_count": 1,
           "julia_depot": environment["julia_depot"],
           "filtered_environment": {"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_DEPOT_PATH": environment["julia_depot"]["path"]},
           "cuda_visible_devices": "0", "cuda_device_order": "PCI_BUS_ID", "returncode": 0, "done": True,
           "source_commit": "a" * 40, "runner_sha256": "c" * 64, "campaign_path": "campaign.json", "kernel_output": "kernel",
           "runtime_project_pins": {"julia/CFDSDFWaterLilyT4/Manifest.toml": environment["project"]["manifest_sha256"],
                                    "julia/CFDSDFWaterLilyT4/Project.toml": environment["project"]["project_sha256"]},
           "started_utc": "2026-11-06T00:00:00+00:00", "finished_utc": "2026-11-06T00:00:02+00:00",
           "wall_seconds": 2.0, "stage_wall_seconds": {"runner": 2.0}, "peak_vram_mib": 50.0,
           "output_sha256": {str(path.relative_to(run)): digest(path) for path in out.rglob("*") if path.is_file()}}
    write_json(run / "local_run.json", rec)
    return run


def rehash_run(run):
    rec = json.loads((run / "local_run.json").read_text())
    out = run / rec["kernel_output"]
    index = json.loads((out / "harness_index.json").read_text())
    for state in index["states"]:
        state["forces_csv_sha256"] = digest(next((out / "states" / state["name"]).glob("*.forces.csv")))
    write_json(out / "harness_index.json", index)
    write_json(out / "output_manifest.json", {"files": {
        str(path.relative_to(out)): digest(path) for path in out.rglob("*")
        if path.is_file() and path.name != "output_manifest.json"}})
    rec["output_sha256"] = {str(path.relative_to(run)): digest(path) for path in out.rglob("*") if path.is_file()}
    write_json(run / "local_run.json", rec)


def make_references(repo):
    for label, ref in G.REFERENCES.items():
        out = repo / ref["output"]
        csv_path = out / ref["csv"]
        force_csv(csv_path)
        summary_path = csv_path.with_name(csv_path.name.replace(".forces.csv", ".summary.json"))
        write_json(summary_path, {**summary(ref["case_id"]), "gpu_name": "Tesla T4"})
        write_json(out / "output_manifest.json", {"files": {ref["csv"]: digest(csv_path),
                   str(summary_path.relative_to(out)): digest(summary_path)}})
    u01 = repo / G.UNC_SMOKE_TABLE
    r2 = G.REFERENCES["R2"]
    csv_path = repo / r2["output"] / r2["csv"]
    write_json(u01, {"integrity": {"pass": True}, "state_forces_n": {"f24": {"v18__parent__k0": {
        "drag_n": 0.5, "downforce_n": 0.75, "forces_csv_sha256": digest(csv_path),
        "summary_sha256": digest(csv_path.with_name("flow_24.summary.json"))}}}})
    write_json(repo / G.UNC_SMOKE_GATE, {"table_sha256": {"smoke_verify_table.json": digest(u01)}})
    analysis = repo / G.UNC_ANALYSIS
    write_json(analysis, {"M3a_tables": {"downforce": {"per_state": {"flow_32": {
        "direction": {"sigma_d_n": 0.002}}}}}})
    (analysis.parent / "SHA256SUMS").write_text(f"{digest(analysis)}  {G.UNC_ANALYSIS}\n")


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    runs = repo / "runs"
    write_json(repo / "campaign.json", {"backend_profile": "local_rtx4070ti",
               "measurement": {"time_window_t_u_l": [80.0, 120.0]}})
    lock = repo / "lock.json"
    write_json(lock, {"schema_version": 1, "environment": {"backend_profile": "local_rtx4070ti",
               "gpu": {"name": "NVIDIA GeForce RTX 4070 Ti", "uuid": "GPU-test", "driver_version": "555.0", "memory_total": "12282 MiB"},
               "julia": {"version": "1.12.6", "sha256": "e" * 64, "root": "/opt/julia-1.12.6", "root_sha256": "d" * 64},
               "julia_depot": {"path": "/opt/local-gpu-depot", "manifest_packages_sha256": "c" * 64},
               "project": {"path": "julia/CFDSDFWaterLilyT4", "manifest_sha256": "f" * 64, "project_sha256": "a" * 64},
               "cuda_visible_devices": "0", "cuda_device_order": "PCI_BUS_ID"}})
    lock.with_name("lock.json.sha256").write_text(digest(lock) + "\n")
    for name, case in (("R1a", "flow_16"), ("R1b", "flow_16"), ("R2a", "flow_24"),
                       ("R2b", "flow_24"), ("R3", "flow_32"), ("R4", "flow_48"), ("R5", "flow_32")):
        make_run(runs, name, digest(lock), case)
    prior = runs / "R5/resume_input/prior_local_run.json"
    prior_record = json.loads((runs / "R5/local_run.json").read_text())
    prior_record.update(returncode=-15, done=False, output_sha256={"checkpoint.bin": hashlib.sha256(b"checkpoint").hexdigest()})
    write_json(prior, prior_record)
    checkpoint = runs / "R5/checkpoint.bin"
    checkpoint.write_bytes(b"checkpoint")
    rec = json.loads((runs / "R5/local_run.json").read_text())
    rec["resume"] = {"resumed": True, "checkpoint_path": "checkpoint.bin", "checkpoint_sha256": digest(checkpoint),
                     "interrupted_run": "resume_input/prior_local_run.json", "interrupted_run_sha256": digest(prior),
                     "interrupted_checkpoint_path": "checkpoint.bin"}
    write_json(runs / "R5/local_run.json", rec)
    for index in range(2):
        repeat = make_run(runs / "R6", f"repeat_{index + 1:03}", digest(lock))
        r6_path = repeat / "local_run.json"
        r6_rec = json.loads(r6_path.read_text())
        start = datetime.datetime(2026, 11, 6, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=3 * index)
        r6_rec.update(wall_seconds=10800.0, started_utc=start.isoformat(),
                      finished_utc=(start + datetime.timedelta(hours=3)).isoformat())
        write_json(r6_path, r6_rec)
        summary_path = repeat / "kernel/states/parent/flow_32.summary.json"
        write_json(summary_path, {**summary("flow_32"), "wall_seconds": 10680.0})
        rehash_run(repeat)
    watch = runs / "R6/watchdog.csv"
    with watch.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, G.WATCHDOG_COLUMNS)
        writer.writeheader()
        writer.writerows({"elapsed_s": second, "clocks_sm_mhz": 2000, "temperature_gpu_c": 60,
                         "power_draw_w": 100, "memory_used_mib": 50, "memory_total_mib": 12282,
                         "utilization_gpu_pct": 80, "gpu_uuid": "GPU-test", "driver_reset": "false",
                         "error": "", "reset_monitor_error": "", "missing_reason": ""}
                        for second in range(0, 21601, 60))
    write_json(watch.with_name("watchdog_status.json"), {
        "schema_version": 1, "wall_seconds": 21600.0, "interval_s": 60,
        "started_utc": "2026-11-06T00:00:00+00:00", "finished_utc": "2026-11-06T06:00:00+00:00",
        "completed": True, "driver_reset_monitor": {"available": True, "source": "synthetic"},
        "watchdog_sha256": digest(watch)})
    make_references(repo)
    calls = []

    def fake_verify(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps({"integrity": {"pass": True}, "smoke": True}), "")

    monkeypatch.setattr(G.subprocess, "run", fake_verify)
    return repo, runs, lock, calls


def evaluate(evidence):
    repo, runs, lock, _ = evidence
    return G.evaluate(runs, lock=lock, repo=repo)


def update_watch(evidence, change):
    _, runs, _, _ = evidence
    watch = runs / "R6/watchdog.csv"
    with watch.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    change(rows)
    with watch.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, G.WATCHDOG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    status_path = watch.with_name("watchdog_status.json")
    status = json.loads(status_path.read_text())
    status["watchdog_sha256"] = digest(watch)
    write_json(status_path, status)


def test_all_criteria_synthetic_pass_and_reference_provenance(evidence):
    result = evaluate(evidence)
    assert result["status"] == "PASS"
    assert result["criteria"]["C1"]["class"] == "BITWISE"
    assert result["criteria"]["C3"]["status"] == "DESCRIPTIVE"
    assert result["criteria"]["C3"]["comparisons"]["R1"]["max_relative_difference"] == 0
    assert result["criteria"]["C3"]["unc_phase_scales"]["values"]
    assert result["criteria"]["C4"]["runs"]["R3"]["cell_steps_per_second"] == 24000
    assert result["criteria"]["C4"]["runs"]["R3"]["timed_cell_steps_per_second"] == 23760
    assert result["criteria"]["C4"]["runs"]["R4"]["t4_anchor_cell_steps_per_second"] == 24000
    assert result["criteria"]["C4"]["runs"]["R4"]["ratio_to_t4"] == 1
    assert result["criteria"]["C4"]["runs"]["R4"]["reference"]["summary_sha256"]
    assert result["common_cuda_uuid"] == "GPU-test"
    assert result["used_gpu_count_evidence"] == "gpu_device_probe.json:logical_device_count"
    assert result["development_defaults"]["sample_gap_allowance_seconds"] == 90
    assert result["development_defaults"]["first_sample_allowance_seconds"] == 60
    assert result["criteria"]["C5"]["status"] == "PASS"
    assert result["criteria"]["C6"]["clock_drop_fraction"] == 0
    assert result["criteria"]["C6"]["solver_wall_seconds_total"] == 21360.0
    assert result["criteria"]["C6"]["solver_fraction_of_wrapper"] == 21360.0 / 21600.0
    assert set(result["local_first_state_reference"]) == {"R1", "R2"}
    calls = evidence[3]
    assert len(calls) == 2 and all("--smoke" in command and "verify" in command for command in calls)


@pytest.mark.parametrize("run_name", ["R1b", "R2b"])
def test_c1_requires_the_same_runner_for_each_repeat(evidence, run_name):
    _, runs, _, _ = evidence
    run = runs / run_name
    record_path = run / "local_run.json"
    record = json.loads(record_path.read_text())
    record["runner_sha256"] = "b" * 64
    write_json(record_path, record)
    identity_path = run / "kernel/run_identity.json"
    identity = json.loads(identity_path.read_text())
    identity["runner_sha256"] = record["runner_sha256"]
    write_json(identity_path, identity)
    rehash_run(run)
    result = evaluate(evidence)
    assert result["status"] == "FAIL" and result["criteria"]["C1"]["status"] == "FAIL"
    assert "runner" in result["criteria"]["C1"]["reason"]


def test_c1_tolerance_and_fail(evidence):
    _, runs, _, _ = evidence
    force_csv(runs / "R1b/kernel/states/parent/flow_16.forces.csv", factor=1 + 5e-7)
    rehash_run(runs / "R1b")
    result = evaluate(evidence)
    assert result["criteria"]["C1"]["class"] == "TOLERANCE"
    force_csv(runs / "R1b/kernel/states/parent/flow_16.forces.csv", factor=1 + 2e-6)
    rehash_run(runs / "R1b")
    result = evaluate(evidence)
    assert result["status"] == "FAIL" and "C1" in result["failed_criteria"]
    assert "local_first_state_reference" not in result


def test_missing_run_incomplete_and_failure_dominates(evidence):
    _, runs, _, _ = evidence
    shutil.rmtree(runs / "R4")
    assert evaluate(evidence)["status"] == "PASS"
    assert evaluate(evidence)["descriptive_issues"]["C4"] == "INCOMPLETE"
    force_csv(runs / "R1b/kernel/states/parent/flow_16.forces.csv", factor=1.1)
    rehash_run(runs / "R1b")
    result = evaluate(evidence)
    assert result["status"] == "FAIL" and "C4" not in result["incomplete_criteria"]
    assert result["descriptive_issues"]["C4"] == "INCOMPLETE"


@pytest.mark.parametrize("field,value", [("lock_sha256", "b" * 64), ("backend_profile", "unknown"),
                                            ("cuda_visible_devices", "1"), ("returncode", 3), ("used_gpu_count", 2)])
def test_run_identity_fail_closed(evidence, field, value):
    _, runs, _, _ = evidence
    path = runs / "R1a/local_run.json"
    rec = json.loads(path.read_text())
    rec[field] = value
    write_json(path, rec)
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"


@pytest.mark.parametrize("where", ["wrapper", "identity"])
def test_actual_runtime_project_pins_must_match_environment_lock(evidence, where):
    _, runs, _, _ = evidence
    path = runs / "R3/local_run.json" if where == "wrapper" else runs / "R3/kernel/run_identity.json"
    doc = json.loads(path.read_text())
    key = "runtime_project_pins" if where == "wrapper" else "pins"
    doc[key]["julia/CFDSDFWaterLilyT4/Manifest.toml"] = "b" * 64
    write_json(path, doc)
    if where == "identity":
        rehash_run(runs / "R3")
    assert evaluate(evidence)["criteria"]["C4"]["status"] == "FAIL"


@pytest.mark.parametrize("target,key,value", [
    ("probe", "logical_device_count", 2),
    ("probe", "visible_gpu_names", ["Tesla T4"]),
    ("probe", "default_device_uuid", "GPU-other"),
    ("identity", "used_gpu_count", 2),
    ("identity", "selected_gpu", {"index": False, "name": "NVIDIA GeForce RTX 4070 Ti", "uuid": "GPU-test"}),
    ("identity", "backend_profile", None),
    ("identity", "cuda_device_order", None),
    ("smi", "driver", "556.0"),
])
def test_every_run_checks_observed_gpu_identity(evidence, target, key, value):
    _, runs, _, _ = evidence
    out = runs / "R3/kernel"
    if target == "smi":
        path = out / "nvidia_smi.csv"
        path.write_text(path.read_text().replace("555.0", value))
    else:
        path = out / ("gpu_device_probe.json" if target == "probe" else "run_identity.json")
        doc = json.loads(path.read_text())
        if value is None:
            del doc[key]
        else:
            doc[key] = value
        write_json(path, doc)
    rehash_run(runs / "R3")
    assert evaluate(evidence)["criteria"]["C4"]["status"] == "FAIL"


def test_cuda_uuid_stays_bound_when_nvml_uuid_is_unavailable(evidence):
    repo, runs, lock, _ = evidence
    doc = json.loads(lock.read_text())
    doc["environment"]["gpu"]["uuid"] = {"error": "NVML UUID unavailable"}
    write_json(lock, doc)
    lock.with_name("lock.json.sha256").write_text(digest(lock) + "\n")
    for path in runs.rglob("local_run.json"):
        rec = json.loads(path.read_text())
        rec.update(lock_sha256=digest(lock), gpu_identity=doc["environment"]["gpu"])
        write_json(path, rec)
    out = runs / "R3/kernel"
    inventory = out / "nvidia_smi.csv"
    inventory.write_text(inventory.read_text().replace("GPU-test", "[N/A]"))
    identity_path = out / "run_identity.json"
    identity = json.loads(identity_path.read_text())
    identity["selected_gpu"]["uuid"] = ""
    write_json(identity_path, identity)
    rehash_run(runs / "R3")
    assert G.evaluate(runs, lock=lock, repo=repo)["criteria"]["C4"]["status"] == "DESCRIPTIVE"
    path = out / "states/parent/flow_32.summary.json"
    summary_doc = json.loads(path.read_text())
    summary_doc["gpu_uuid"] = "GPU-other"
    write_json(path, summary_doc)
    rehash_run(runs / "R3")
    assert G.evaluate(runs, lock=lock, repo=repo)["criteria"]["C4"]["status"] == "FAIL"


def test_cuda_uuid_is_common_across_runs_without_nvml_identity(evidence):
    repo, runs, lock, _ = evidence
    doc = json.loads(lock.read_text())
    doc["environment"]["gpu"]["uuid"] = {"error": "NVML UUID unavailable"}
    write_json(lock, doc)
    lock.with_name("lock.json.sha256").write_text(digest(lock) + "\n")
    for path in list(runs.rglob("local_run.json")) + [runs / "R5/resume_input/prior_local_run.json"]:
        rec = json.loads(path.read_text())
        rec.update(lock_sha256=digest(lock), gpu_identity=doc["environment"]["gpu"])
        write_json(path, rec)
    rec_path = runs / "R5/local_run.json"
    rec = json.loads(rec_path.read_text())
    rec["resume"]["interrupted_run_sha256"] = digest(runs / "R5/resume_input/prior_local_run.json")
    write_json(rec_path, rec)
    assert G.evaluate(runs, lock=lock, repo=repo)["common_cuda_uuid"] == "GPU-test"
    # R4 is descriptive, but a real probe from another GPU contradicts the common environment identity.
    probe_path = runs / "R4/kernel/gpu_device_probe.json"
    probe = json.loads(probe_path.read_text())
    probe.update(visible_gpu_uuids=["GPU-other"], default_device_uuid="GPU-other")
    write_json(probe_path, probe)
    # Even another missing descriptive artifact must not hide the already-recorded GPU contradiction.
    (runs / "R4/kernel/states/parent/flow_48.summary.json").unlink()
    result = G.evaluate(runs, lock=lock, repo=repo)
    assert result["status"] == "FAIL" and "C_identity" in result["failed_criteria"]
    assert "UUID" in result["criteria"]["C_identity"]["reason"]


def test_csv_hash_schema_nonfinite_and_steps_fail_closed(evidence):
    _, runs, _, _ = evidence
    path = runs / "R1a/kernel/states/parent/flow_16.forces.csv"
    path.write_text(path.read_text().replace("2.0", "nan", 1))
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"  # wrapper hash mismatch
    rehash_run(runs / "R1a")
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"  # valid hash, nonfinite CSV
    force_csv(path)
    path.write_text(path.read_text().replace("8,79.0", "9,79.0"))
    rehash_run(runs / "R1a")
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"


def test_c1_rejects_schema_and_different_case_even_with_equal_bytes(evidence):
    _, runs, _, _ = evidence
    path = runs / "R1b/kernel/states/parent/flow_16.forces.csv"
    path.write_text(path.read_text().replace("fx_solver", "fx_wrong", 1))
    rehash_run(runs / "R1b")
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"
    make_run(runs, "R1b", digest(evidence[2]), "flow_24")
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"


def test_c2_failure_and_invalid_json_fail_closed(evidence, monkeypatch):
    monkeypatch.setattr(G.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 3, "", "invalid"))
    assert evaluate(evidence)["criteria"]["C2"]["status"] == "FAIL"
    monkeypatch.setattr(G.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "garbage", ""))
    assert evaluate(evidence)["criteria"]["C2"]["status"] == "FAIL"
    monkeypatch.setattr(G.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "[]", ""))
    assert evaluate(evidence)["criteria"]["C2"]["status"] == "FAIL"
    monkeypatch.setattr(G.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(
        command, 0, '{"integrity":{"pass":true},"smoke":true,"invalid":NaN}', ""))
    assert evaluate(evidence)["criteria"]["C2"]["status"] == "FAIL"


def test_c3_difference_descriptive_but_reference_hash_mismatch_fails(evidence):
    repo, runs, _, _ = evidence
    force_csv(runs / "R3/kernel/states/parent/flow_32.forces.csv", factor=1.2)
    rehash_run(runs / "R3")
    result = evaluate(evidence)
    assert result["criteria"]["C3"]["status"] == "DESCRIPTIVE"
    assert result["criteria"]["C3"]["comparisons"]["R3"]["max_relative_difference"] > 0.1
    assert result["criteria"]["C3"]["comparisons"]["R3"]["forces"]["drag_n"]["relative_difference"] == pytest.approx(0.2)
    assert result["criteria"]["C3"]["comparisons"]["R3"]["samples"]["max_relative_difference"] == pytest.approx(0.2)
    ref = G.REFERENCES["R1"]
    (repo / ref["output"] / ref["csv"]).write_text("corrupt")
    assert evaluate(evidence)["criteria"]["C3"]["status"] == "FAIL"


@pytest.mark.parametrize("criterion,status", [("C3", "FAIL"), ("C3", "INCOMPLETE"),
                                               ("C4", "FAIL"), ("C4", "INCOMPLETE")])
def test_descriptive_criteria_never_block_pass(evidence, monkeypatch, criterion, status):
    monkeypatch.setattr(G, criterion.lower(), lambda *args: {"status": status, "reason": "synthetic unavailable description"})
    result = evaluate(evidence)
    assert result["status"] == "PASS"
    assert result["descriptive_issues"][criterion] == status
    assert criterion not in result["failed_criteria"] + result["incomplete_criteria"]


@pytest.mark.parametrize("key,value", [("canonical_sdf_origin_m", [-0.4, -0.5, -0.5]),
                                       ("phi_fortran_sha256", "b" * 64),
                                       ("density_kg_m3", 1.2), ("burn_in_t_u_l", 70.0)])
def test_c3_rejects_a_different_geometry_or_physical_contract(evidence, key, value):
    _, runs, _, _ = evidence
    # Alter both R3/R5 so C5 still has a consistent pair; C3 must reject the wrong T4 comparator.
    for name in ("R3", "R5"):
        path = runs / name / "kernel/states/parent/flow_32.summary.json"
        doc = json.loads(path.read_text())
        doc[key] = value
        write_json(path, doc)
        rehash_run(runs / name)
    result = evaluate(evidence)
    assert result["criteria"]["C5"]["status"] == "PASS"
    assert result["criteria"]["C3"]["status"] == "FAIL"
    assert result["status"] == "PASS"


def test_c5_requires_resume_provenance_and_statistics(evidence):
    _, runs, _, _ = evidence
    path = runs / "R5/local_run.json"
    rec = json.loads(path.read_text())
    rec["resume"]["checkpoint_sha256"] = "b" * 64
    write_json(path, rec)
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "FAIL"
    rec["resume"]["checkpoint_sha256"] = digest(runs / "R5/checkpoint.bin")
    write_json(path, rec)
    force_csv(runs / "R5/kernel/states/parent/flow_32.forces.csv", factor=1 + 5e-7)
    rehash_run(runs / "R5")
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "FAIL"  # C1 BITWISE
    force_csv(runs / "R1b/kernel/states/parent/flow_16.forces.csv", factor=1 + 5e-7)
    rehash_run(runs / "R1b")
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "PASS"  # C1 TOLERANCE


def test_c5_rejects_missing_or_contradictory_job_resume_event(evidence):
    _, runs, _, _ = evidence
    event = runs / "R5/kernel/states/parent/local_gpu_resume.json"
    doc = json.loads(event.read_text())
    doc["checkpoint_sha256"] = "b" * 64
    write_json(event, doc)
    rehash_run(runs / "R5")
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "FAIL"
    event.unlink()
    rehash_run(runs / "R5")
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "FAIL"


@pytest.mark.parametrize("where,key,value", [("prior", "source_commit", "b" * 40),
                                             ("prior", "runner_sha256", "b" * 64),
                                             ("summary", "canonical_sdf_origin_m", [-0.4, -0.5, -0.5])])
def test_c5_rejects_unrelated_interruption_or_geometry(evidence, where, key, value):
    _, runs, _, _ = evidence
    path = runs / "R5/resume_input/prior_local_run.json" if where == "prior" else runs / "R5/kernel/states/parent/flow_32.summary.json"
    doc = json.loads(path.read_text())
    doc[key] = value
    write_json(path, doc)
    if where == "prior":
        record_path = runs / "R5/local_run.json"
        rec = json.loads(record_path.read_text())
        rec["resume"]["interrupted_run_sha256"] = digest(path)
        write_json(record_path, rec)
    rehash_run(runs / "R5")
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "FAIL"


def test_c5_prior_checkpoint_must_be_the_checkpoint_actually_loaded(evidence):
    _, runs, _, _ = evidence
    prior = runs / "R5/resume_input/prior_local_run.json"
    doc = json.loads(prior.read_text())
    doc["output_sha256"]["checkpoint.bin"] = "b" * 64
    write_json(prior, doc)
    rec_path = runs / "R5/local_run.json"
    rec = json.loads(rec_path.read_text())
    rec["resume"]["interrupted_run_sha256"] = digest(prior)
    write_json(rec_path, rec)
    assert evaluate(evidence)["criteria"]["C5"]["status"] == "FAIL"


@pytest.mark.parametrize("column,value", [("clocks_sm_mhz", "1700"), ("power_draw_w", "nan"),
                                             ("driver_reset", "true"), ("error", "nvidia-smi failed")])
def test_c6_stability_failures(evidence, column, value):
    update_watch(evidence, lambda rows: rows[-1].update({column: value}))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "FAIL"


def test_c6_clock_drawdown_ignores_only_initial_ramp_up(evidence):
    def ramp_then_drop(rows):
        rows[0]["clocks_sm_mhz"] = "500"
        rows[-1]["clocks_sm_mhz"] = "1600"  # 20% below the subsequent 2000 MHz peak

    update_watch(evidence, ramp_then_drop)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "FAIL"
    update_watch(evidence, lambda rows: rows[-1].update(clocks_sm_mhz="1701"))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "PASS"


def test_c6_idle_drawdown_is_excluded_only_with_active_evidence(evidence):
    update_watch(evidence, lambda rows: rows[10].update(clocks_sm_mhz="500", utilization_gpu_pct="0"))
    result = evaluate(evidence)["criteria"]["C6"]
    assert result["status"] == "PASS"
    assert result["samples"] == result["solver_active_samples"] + 1
    update_watch(evidence, lambda rows: rows[10].update(utilization_gpu_pct="80"))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "FAIL"


def test_c6_runner_solver_intervals_can_mark_active_samples(evidence):
    _, runs, _, _ = evidence
    for path in (runs / "R6").glob("repeat_*/local_run.json"):
        rec = json.loads(path.read_text())
        rec["solver_intervals"] = [{"started_utc": rec["started_utc"], "finished_utc": rec["finished_utc"]}]
        write_json(path, rec)
    update_watch(evidence, lambda rows: [row.update(utilization_gpu_pct="0") for row in rows])
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "PASS"


def test_c6_vram_leak_and_repeat_peak_change(evidence):
    update_watch(evidence, lambda rows: rows[100].update(memory_used_mib="1050"))
    result = evaluate(evidence)["criteria"]["C6"]
    assert result["status"] == "FAIL" and "within" in result["reason"]
    update_watch(evidence, lambda rows: rows[100].update(memory_used_mib="50"))
    path = evidence[1] / "R6/repeat_002/local_run.json"
    rec = json.loads(path.read_text())
    rec["peak_vram_mib"] = 52.0  # The 10-second peak can differ while all minute/mature samples remain the same.
    write_json(path, rec)
    result = evaluate(evidence)["criteria"]["C6"]
    assert result["status"] == "FAIL" and "repeat" in result["reason"]


def test_c6_missing_ten_second_peak_is_incomplete(evidence):
    path = evidence[1] / "R6/repeat_002/local_run.json"
    rec = json.loads(path.read_text())
    rec["peak_vram_mib"] = {"error": "memory query unavailable"}
    write_json(path, rec)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"


@pytest.mark.parametrize("column", ["clocks_sm_mhz", "temperature_gpu_c", "power_draw_w", "memory_used_mib",
                                    "memory_total_mib", "utilization_gpu_pct", "gpu_uuid"])
def test_c6_missing_telemetry_is_incomplete(evidence, column):
    update_watch(evidence, lambda rows: rows[10].update({column: "", "missing_reason": f"{column}: NVML unavailable"}))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"


def test_c6_missing_telemetry_does_not_hide_nonfinite_or_reset(evidence):
    update_watch(evidence, lambda rows: (rows[10].update(power_draw_w=""), rows[-1].update(driver_reset="true")))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "FAIL"


def test_c6_real_collector_missing_markers_are_incomplete(evidence):
    _, runs, _, _ = evidence
    update_watch(evidence, lambda rows: rows[10].update(power_draw_w="", missing_reason="power.draw unavailable"))
    path = runs / "R6/watchdog_status.json"
    status = json.loads(path.read_text())
    status["telemetry_errors"] = [{"incomplete": "power.draw unavailable"}]
    write_json(path, status)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"


@pytest.mark.parametrize("missing_column", ["power_draw_w", "memory_used_mib"])
def test_actual_telemetry_collector_missing_reaches_gate_as_incomplete(evidence, tmp_path, monkeypatch, missing_column):
    import local_gpu as L

    # Execute the real parser, collector and status writer against a deterministic NVML response.
    # Only wall coverage comes from the synthetic six-hour evidence; no hardware is queried.
    def raw_probe(argv, **kwargs):
        if "--query-gpu=memory.used" in argv:
            return "[N/A]" if missing_column == "memory_used_mib" else "50"
        values = ["2000", "60", "100", "50", "80", "GPU-test", "12282"]
        values[2 if missing_column == "power_draw_w" else 3] = "[N/A]"
        return ", ".join(values)

    monkeypatch.setattr(L.C, "probe", raw_probe)
    monkeypatch.setattr(L, "query_resets", lambda started: False)
    collected = tmp_path / "collected.csv"
    telemetry = L.Telemetry(collected)
    monkeypatch.setattr(telemetry.stop, "wait", lambda timeout: telemetry.stop.set())
    telemetry.start()
    telemetry.thread.join(timeout=2)
    assert not telemetry.thread.is_alive()
    actual_status = telemetry.finish()
    with collected.open(newline="") as handle:
        actual_row = next(csv.DictReader(handle))
    assert actual_row[missing_column] == "" and actual_row["missing_reason"]
    assert actual_status["telemetry_errors"][0]["incomplete"]
    actual_row["elapsed_s"] = "600"
    update_watch(evidence, lambda rows: rows.__setitem__(10, actual_row))
    status_path = evidence[1] / "R6/watchdog_status.json"
    status = json.loads(status_path.read_text())
    status["telemetry_errors"] = actual_status["telemetry_errors"]
    write_json(status_path, status)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"


def test_c6_unobservable_reset_and_short_duration_incomplete(evidence):
    update_watch(evidence, lambda rows: rows[-1].update({"reset_monitor_error": "permission denied", "driver_reset": ""}))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"
    update_watch(evidence, lambda rows: rows.pop())
    path = evidence[1] / "R6/watchdog_status.json"
    status = json.loads(path.read_text())
    status["wall_seconds"] = 21540.0
    write_json(path, status)
    result = evaluate(evidence)
    assert result["criteria"]["C6"]["status"] == "INCOMPLETE"


def test_c6_monitor_unknown_type_and_cadence_gap(evidence):
    _, runs, _, _ = evidence
    path = runs / "R6/watchdog_status.json"
    status = json.loads(path.read_text())
    status["driver_reset_monitor"]["available"] = "false"
    write_json(path, status)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "FAIL"
    status["driver_reset_monitor"]["available"] = True
    write_json(path, status)
    update_watch(evidence, lambda rows: rows.pop(10))
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"


def test_c6_watch_alone_cannot_qualify_a_short_workload(evidence):
    _, runs, _, _ = evidence
    path = runs / "R6/repeat_001/local_run.json"
    rec = json.loads(path.read_text())
    rec.update(wall_seconds=2.0, finished_utc="2026-11-06T00:00:02+00:00")
    write_json(path, rec)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"


def test_c6_requires_monitor_overlap_and_nonoverlapping_workloads(evidence):
    _, runs, _, _ = evidence
    path = runs / "R6/watchdog_status.json"
    status = json.loads(path.read_text())
    status["started_utc"] = "2026-11-06T00:00:01+00:00"
    write_json(path, status)
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "INCOMPLETE"
    status["started_utc"] = "2026-11-06T00:00:00+00:00"
    write_json(path, status)
    make_run(runs / "R6", "repeat_003", digest(evidence[2]))  # overlaps repeat_001
    assert evaluate(evidence)["criteria"]["C6"]["status"] == "FAIL"


def test_malformed_objects_return_structured_failure(evidence):
    _, runs, _, _ = evidence
    path = runs / "R2a/local_run.json"
    write_json(path, [])
    assert evaluate(evidence)["status"] == "FAIL"
    write_json(path, {"schema_version": 1})
    assert evaluate(evidence)["status"] == "FAIL"


def test_c4_rejects_invalid_steps_and_wall(evidence):
    _, runs, _, _ = evidence
    path = runs / "R3/kernel/states/parent/flow_32.summary.json"
    doc = json.loads(path.read_text())
    doc["steps"] = True
    write_json(path, doc)
    rehash_run(runs / "R3")
    assert evaluate(evidence)["criteria"]["C4"]["status"] == "FAIL"
    doc["steps"], doc["wall_seconds"] = 100, 0.0
    write_json(path, doc)
    rehash_run(runs / "R3")
    assert evaluate(evidence)["criteria"]["C4"]["status"] == "FAIL"


def test_duplicate_json_and_unsafe_output_paths_fail_closed(evidence):
    _, runs, _, _ = evidence
    path = runs / "R1a/local_run.json"
    original = path.read_text()
    path.write_text(original.replace('"returncode": 0', '"returncode": 0, "returncode": 0'))
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"
    rec = json.loads(original)
    rec["output_sha256"]["../outside"] = "b" * 64
    write_json(path, rec)
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"


def test_write_once_output_and_lock_sidecar(evidence, tmp_path):
    repo, runs, lock, calls = evidence
    out = tmp_path / "gate.json"
    G.write_gate(runs, out, lock=lock, repo=repo)
    assert json.loads(out.read_text())["status"] == "PASS"
    calls.clear()
    with pytest.raises(FileExistsError):
        G.write_gate(runs, out, lock=lock, repo=repo)
    assert calls == []
    lock.with_name("lock.json.sha256").write_text("b" * 64 + "\n")
    assert G.evaluate(runs, lock=lock, repo=repo)["status"] == "FAIL"


def test_unexpected_gate_exception_does_not_reserve_output(evidence, tmp_path, monkeypatch):
    out = tmp_path / "gate.json"
    monkeypatch.setattr(G, "evaluate", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unexpected")))
    with pytest.raises(RuntimeError, match="unexpected"):
        G.write_gate(evidence[1], out, lock=evidence[2], repo=evidence[0])
    assert not out.exists()
    assert not list(tmp_path.glob(".gate.json.*"))


def test_exclusive_gate_publish_preserves_a_racing_writer(tmp_path, monkeypatch):
    out = tmp_path / "gate.json"

    def racing_result(*args, **kwargs):
        out.write_text("winner\n")
        return {"status": "PASS"}

    monkeypatch.setattr(G, "evaluate", racing_result)
    with pytest.raises(FileExistsError):
        G.write_gate(tmp_path, out)
    assert out.read_text() == "winner\n"
    assert not list(tmp_path.glob(".gate.json.*"))


@pytest.mark.parametrize("name", ["run_identity.json", "gpu_device_probe.json", "nvidia_smi.csv", "output_manifest.json"])
def test_done_missing_identity_artifacts_fails(evidence, name):
    _, runs, _, _ = evidence
    (runs / "R1a/kernel" / name).unlink()
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"


@pytest.mark.parametrize("key", ["filtered_environment", "julia_depot"])
def test_c1_binds_runtime_environment_and_depot(evidence, key):
    _, runs, _, _ = evidence
    path = runs / "R1b/local_run.json"
    rec = json.loads(path.read_text())
    rec[key] = {**rec[key], "unexpected": "changed"}
    write_json(path, rec)
    assert evaluate(evidence)["criteria"]["C1"]["status"] == "FAIL"


def test_lock_matches_utf8_capture_and_requires_binary_manifest_identity(evidence):
    repo, runs, lock, _ = evidence
    doc = json.loads(lock.read_text())
    doc["observations"] = {"windows_ver": "Microsoft Windows バージョン"}
    lock.write_bytes((json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    lock.with_name("lock.json.sha256").write_text(digest(lock) + "\n")
    assert G.read_lock(lock)[0] == digest(lock)
    del doc["environment"]["julia"]["sha256"]
    lock.write_bytes(G.canonical(doc))
    lock.with_name("lock.json.sha256").write_text(digest(lock) + "\n")
    assert G.evaluate(runs, lock=lock, repo=repo)["status"] == "FAIL"


def test_json_float_overflow_is_a_structured_failure(evidence):
    _, runs, _, _ = evidence
    for name in ("R3", "R5"):
        path = runs / name / "kernel/states/parent/flow_32.summary.json"
        path.write_text(path.read_text().replace('"density_kg_m3": 1.0', '"density_kg_m3": 1e309'))
        rehash_run(runs / name)
    result = evaluate(evidence)
    assert result["criteria"]["C5"]["status"] == "FAIL"
    assert result["status"] == "FAIL"
    assert G.canonical(result)


def test_finite_inputs_with_nonfinite_derived_statistics_cannot_pass(evidence):
    repo, runs, _, _ = evidence
    ref = G.REFERENCES["R3"]
    retained = repo / ref["output"] / ref["csv"]
    retained_summary = retained.with_name("flow_32.summary.json")
    paths = [runs / name / "kernel/states/parent/flow_32.summary.json" for name in ("R3", "R5")]
    for path in [*paths, retained_summary]:
        doc = json.loads(path.read_text())
        doc.update(density_kg_m3=1e308, freestream_mps=[1e154, 0.0, 0.0])
        write_json(path, doc)
    for name in ("R3", "R5"):
        rehash_run(runs / name)
    manifest_path = repo / ref["output"] / "output_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][str(retained_summary.relative_to(manifest_path.parent))] = digest(retained_summary)
    write_json(manifest_path, manifest)
    result = evaluate(evidence)
    assert result["status"] == "FAIL"
    assert result["criteria"]["C5"]["status"] == "FAIL"
    assert G.canonical(result)


@pytest.mark.skipif(not (G.ROOT / G.UNC_SMOKE_TABLE).is_file(), reason="retained reference archive unavailable")
def test_retained_t4_references_recompute_read_only():
    for label in G.REFERENCES:
        retained = G.reference(G.ROOT, label)
        assert set(G.REFERENCE_IDENTITY_KEYS) <= set(retained["summary"])
        stats = G.window_statistics(retained)
        assert stats["drag_n"] == retained["summary"]["drag_time_weighted_n"]
        assert stats["downforce_n"] == retained["summary"]["downforce_time_weighted_n"]
    assert G.unc_phase_scales(G.ROOT)["values"]
