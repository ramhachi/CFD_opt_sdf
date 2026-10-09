"""Synthetic two-kernel corruption tests; no CFD or prior production analysis."""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import analyze_lowdim03 as A
import build_lowdim03_kernel as K
import freeze_lowdim03 as F
from cfd_sdf import lowdim03_contract as C
from fd08_v2_campaign_io import FORCE_COLUMNS, recompute_force_n


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def identity_proof():
    proof = {"owner": "ramhachi888", "all_free": True, "kernel_ids": list(K.KERNEL_IDS.values()),
             "captured_utc": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
             "listings": {}, "positive_controls": {}}
    for kind in ("kernels", "datasets"):
        rows = [{"ref": "ramhachi888/existing-synthetic-resource", "title": "existing synthetic resource"}]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=("ref", "title"))
        writer.writeheader(); writer.writerows(rows)
        proof["listings"][kind] = {"complete": True, "rows": rows, "pages": [{
            "command": ["kaggle", kind, "list", "--mine", "--page-size", "100", "--page", "1", "--csv"],
            "exit_code": 0, "stdout": buffer.getvalue(), "stderr": "", "rows": rows}]}
        command = ["kaggle", kind, "status", rows[0]["ref"]] if kind == "kernels" else ["kaggle", kind, "files", rows[0]["ref"], "--csv"]
        proof["positive_controls"][kind] = {"command": command, "exit_code": 0, "stdout": "existing resource accessible", "stderr": ""}
    return proof


@pytest.fixture(scope="module")
def registered(tmp_path_factory, request):
    """A separate Git repository binds real reviewed inputs and synthetic outputs."""
    root = tmp_path_factory.mktemp("lowdim03-source")
    inventory = json.loads((ROOT / A.EVIDENCE_REL / "inventory.json").read_text())
    paths = A.required_file_paths(inventory)
    for relative in paths:
        source, target = ROOT / relative, root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            shutil.copyfile(source, target)
        else:
            target.write_text("synthetic pinned registration input\n")
    proof_path = root / A.EVIDENCE_REL / "identity_free_check.json"
    proof = identity_proof()
    dump(proof_path, proof)
    proof_path.with_name(proof_path.name + ".sha256").write_text(A.sha256(proof_path) + "\n")
    git(root, "init", "-q")
    git(root, "config", "user.name", "LOWDIM-03 synthetic test")
    git(root, "config", "user.email", "lowdim03-test@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "synthetic registration source")
    source_commit = git(root, "rev-parse", "HEAD")
    patch = pytest.MonkeyPatch()
    request.addfinalizer(patch.undo)
    patch.setattr(A, "ROOT", root)
    patch.setattr(A, "PARENT_COMMIT", source_commit)
    patch.setattr(K, "ROOT", root)
    patch.setattr(K, "EVIDENCE", root / A.EVIDENCE_REL)
    patch.setattr(K, "TEMPLATE", root / "scripts/lowdim03_runner_template.py")
    patch.setattr(F, "ROOT", root)
    patch.setattr(F, "E", root / A.EVIDENCE_REL)
    patch.setattr(F, "IDENTITY", proof_path)
    freeze = {"kind": "lowdim03_dual_grid_primal_prerun_freeze", "parent_integration_commit": source_commit,
              "source_commit": source_commit, "frozen_utc": datetime.now(timezone.utc).isoformat(),
              "inventory_sha256": A.sha256(root / A.EVIDENCE_REL / "inventory.json"),
              "file_hashes": {p: A.sha256(root / p) for p in paths}, "identity_free_check": proof,
              "qualification_flags": {key: False for key in C.QUALIFICATION_FLAGS}, "rules": deepcopy(C.RULES),
              "selected_delta": None, "reinitialization": "none", "pins": {}, "runtime": {}}
    for kernel, grid in A.KERNELS.items():
        directory = root / f"infra/kaggle/kernel_lowdim03_{kernel}"
        directory.mkdir(parents=True)
        runner = directory / "runner.py"
        runner.write_text(K.render(source_commit, kernel))
        meta = directory / "kernel-metadata.json"
        dump(meta, K.metadata(kernel))
        freeze["pins"][kernel] = K.pins(kernel)
        freeze["runtime"][kernel] = {**A.RUNTIME_NUMBERS, "kernel_id": K.KERNEL_IDS[kernel], "case_id": grid,
                                    "runner_sha256": A.sha256(runner), "metadata_sha256": A.sha256(meta),
                                    "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0", "timeout_s": 10800,
                                    "selected_gpu_physical_index": 0, "used_gpu_count": 1,
                                    "machine_shape": "NvidiaTeslaT4", "dataset_sources": []}
    yield root, inventory, freeze
    patch.undo()


def force_csv(path, lift, drag, scale):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FORCE_COLUMNS)
        writer.writeheader()
        for step, time in enumerate((0, 80, 100, 120, 121), 1):
            row = dict.fromkeys(FORCE_COLUMNS, 0.0)
            row.update(step=step, t_u_l=time, fx_solver=drag / scale, drag_solver=drag / scale,
                       fz_solver=-lift / scale, downforce_solver=lift / scale,
                       pressure_fx_solver=drag / scale, pressure_fz_solver=-lift / scale)
            writer.writerow(row)


def manifest(out):
    dump(out / "output_manifest.json", {"files": {str(p.relative_to(out)): A.sha256(p)
         for p in out.rglob("*") if p.is_file() and p != out / "output_manifest.json"}})


def output(out, kernel, root, inventory, freeze):
    out.mkdir()
    grid = A.KERNELS[kernel]
    config, runtime = inventory["grids"][kernel], freeze["runtime"][kernel]
    uuid = "GPU-synthetic-physical-index-zero"
    (out / "nvidia_smi.csv").write_text(f"0, Tesla T4, {uuid}, 15360 MiB, 535.1\n")
    (out / "gpu_device_probe.log").write_text("synthetic observed CUDA identity\n")
    dump(out / "gpu_device_probe.json", {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"],
         "visible_gpu_uuids": [uuid], "default_device_uuid": uuid, "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"})
    dump(out / "run_identity.json", {"source_commit": freeze["source_commit"], "kernel": kernel,
         "kernel_id": runtime["kernel_id"], "case_id": grid, "runner_sha256": runtime["runner_sha256"],
         "pins": freeze["pins"][kernel], "verified": freeze["pins"][kernel], "failure_stage": None,
         "baseline_csv_sha256": config["baseline_reference"]["forces_csv_sha256"],
         "selected_gpu": {"index": 0, "name": "Tesla T4", "uuid": uuid}, "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"})
    index = {"kernel": kernel, "kernel_id": runtime["kernel_id"], "case_id": grid,
             "status": "COMPLETE", "states": [], "solver_process_wall_seconds_total": 7.0}
    case = config["measurement"]["case"]
    base = config["baseline_reference"]["host_recomputed_n"]
    scale = case["density_kg_m3"] * case["freestream_mps"][0] ** 2 * case["flow_spacing_m"] ** 2
    for row in inventory["states"]:
        directory = out / "states" / row["name"]
        directory.mkdir(parents=True)
        csv_path = directory / f"{grid}.forces.csv"
        if row["kind"] == "baseline":
            shutil.copyfile(root / config["baseline_reference"]["forces_csv_path"], csv_path)
        else:
            gain = row["sign"] * .0001 * row["step_mm"] / .625
            drag = 1e-5 if kernel == "b" and row["step_mm"] == 2.5 and row["sign"] == 1 else -1e-5
            force_csv(csv_path, base["downforce_n"] + gain, base["drag_n"] + drag, scale)
        host = recompute_force_n(csv_path, {"measurement": config["measurement"]})
        job_env = inventory["job_env_common"]
        summary = {**case, "gpu_name": "Tesla T4", "gpu_uuid": uuid, "phi_fortran_sha256": row["phi_fortran_order_sha256"],
                   "phi_c_order_sha256": row["phi_c_order_sha256"], "state_sha256": row["state_sha256"], "state_npz_sha256": row["npz_sha256"],
                   "canonical_sdf_origin_m": [float(v) for v in job_env["W4_CANONICAL_ORIGIN_M"].split(",")],
                   "canonical_design_spacing_m": float(job_env["W4_CANONICAL_DESIGN_SPACING_M"]),
                   "canonical_state_label": job_env["W4_CANONICAL_STATE_LABEL"],
                   "canonical_design_point_shape": [int(v) for v in job_env["W4_POINT_SHAPE"].split(",")],
                   "canonical_design_cell_shape": [int(v) for v in job_env["W4_CELL_SHAPE"].split(",")],
                   "source_surface_sha256": job_env["W4_SOURCE_SURFACE_SHA256"],
                   "device_roundtrip_sha256": row["phi_c_order_sha256"],
                   "force_integration_body": config["measurement"]["candidate_operator"], "force_projection_semantics": "drag=+Fx; downforce=-Fz",
                   "finite_u": True, "finite_p": True, "finite_forces": True, "julia_threads": 1,
                   "t_end_reached": 120.01, "burn_in_t_u_l": 80, "phi_margin_m": row["zero_level_margin_m"], "phi_margin_gate_m": .15,
                   "wall_seconds": .8, "downforce_time_weighted_n": host["downforce_n"], "drag_time_weighted_n": host["drag_n"]}
        dump(directory / f"{grid}.summary.json", summary)
        (directory / "W4_JOB_DONE").write_text("synthetic job done\n")
        index["states"].append({key: row[key] for key in ("name", "kind", "step_mm", "sign")})
        index["states"][-1].update(complete=True, exit_code=0, seconds=1.0, forces_csv_sha256=A.sha256(csv_path))
    dump(out / "lowdim03_index.json", index)
    (out / "DONE").write_text("synthetic all seven completed\n")
    manifest(out)


@pytest.fixture
def valid(registered, tmp_path):
    root, inventory, freeze = registered
    a, b = tmp_path / "lowdim03_a", tmp_path / "lowdim03_b"
    output(a, "a", root, inventory, freeze)
    output(b, "b", root, inventory, freeze)
    return a, b, deepcopy(freeze), deepcopy(inventory)


def run(case):
    return A.analyze(case[0], case[1], case[2], case[3])


def test_complete_two_grid_trial_selects_common_step_and_keeps_controls_diagnostic(valid):
    report = run(valid)
    assert report["integrity"] == {"pass": True, "failures": []}
    assert report["verdict"] == "LOWDIM03_ACCEPT" and report["selected_step_mm"] == 1.25
    assert report["candidates"][C.state_name(2.5, 1)]["accepted"] is False
    assert set(report["paired_model_diagnostics"]) == {"0.625", "1.25", "2.5"}
    assert set(report["qualification_flags"].values()) == {False} and report["selected_delta"] is None
    assert report["rules"]["reverse_controls_eligible"] is False and report["rules"]["rho_is_acceptance_gate"] is False


@pytest.mark.parametrize("mutation", ["missing_kernel", "missing_control", "extra_state", "extra_file", "ERROR", "empty_manifest",
                                    "wrong_gpu", "wrong_probe", "wrong_grid", "bool_threads", "bool_complete", "nan_force", "bad_summary_force",
                                    "wrong_state", "bad_runtime_sum", "over_budget", "force_component", "manifest_escape"])
def test_output_corruption_never_produces_accept_or_no_accept(valid, mutation):
    a, b, _, inv = valid
    name = C.state_name(.625, -1)
    summary_path = b / "states" / name / "flow_32.summary.json"
    if mutation == "missing_kernel":
        shutil.rmtree(b)
    elif mutation == "missing_control":
        shutil.rmtree(b / "states" / name); manifest(b)
    elif mutation == "extra_state":
        (b / "states/unregistered").mkdir(); manifest(b)
    elif mutation == "extra_file":
        (b / "unmanifested.txt").write_text("extra")
    elif mutation == "ERROR":
        (b / "ERROR.txt").write_text("runner failed"); manifest(b)
    elif mutation == "empty_manifest":
        dump(b / "output_manifest.json", {"files": {}})
    elif mutation == "wrong_gpu":
        (b / "nvidia_smi.csv").write_text("0, A100, GPU-wrong, 40000 MiB, 535.1\n"); manifest(b)
    elif mutation == "wrong_probe":
        p = b / "gpu_device_probe.json"; obj = A.jload(p); obj["default_device_uuid"] = "GPU-other"; dump(p, obj); manifest(b)
    elif mutation in ("wrong_grid", "bool_threads", "bad_summary_force", "wrong_state"):
        obj = A.jload(summary_path)
        key, value = {"wrong_grid": ("flow_spacing_m", 1 / 30), "bool_threads": ("julia_threads", True),
                      "bad_summary_force": ("downforce_time_weighted_n", .123), "wrong_state": ("state_sha256", "a" * 64)}[mutation]
        obj[key] = value; dump(summary_path, obj); manifest(b)
    elif mutation in ("bool_complete", "bad_runtime_sum", "over_budget"):
        p = b / "lowdim03_index.json"; obj = A.jload(p)
        if mutation == "bool_complete": obj["states"][1]["complete"] = 1
        if mutation == "bad_runtime_sum": obj["solver_process_wall_seconds_total"] = 8.0
        if mutation == "over_budget": obj["states"][1]["seconds"] = 901
        dump(p, obj); manifest(b)
    elif mutation in ("nan_force", "force_component"):
        p = b / "states" / name / "flow_32.forces.csv"
        text = p.read_text(); rows = list(csv.DictReader(io.StringIO(text)))
        rows[1]["downforce_solver"] = "nan" if mutation == "nan_force" else "100000"
        with p.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FORCE_COLUMNS); writer.writeheader(); writer.writerows(rows)
        index = A.jload(b / "lowdim03_index.json")
        next(x for x in index["states"] if x["name"] == name)["forces_csv_sha256"] = A.sha256(p)
        dump(b / "lowdim03_index.json", index); manifest(b)
    elif mutation == "manifest_escape":
        p = b / "output_manifest.json"; obj = A.jload(p); obj["files"]["../escaped"] = "b" * 64; dump(p, obj)
    report = run(valid)
    assert report["verdict"] == "LOWDIM03_INCOMPLETE" and report["integrity"]["pass"] is False
    assert "selected" not in report


@pytest.mark.parametrize("mutation", ["closure", "source", "kind", "parent", "rules", "flags", "identity", "runtime_boolean", "pins", "proposal", "inventory_boolean"])
def test_malformed_or_changed_freeze_is_fail_closed(valid, mutation):
    freeze, inv = valid[2], valid[3]
    if mutation == "closure": freeze["file_hashes"].pop("scripts/analyze_lowdim03.py")
    if mutation == "source": freeze["source_commit"] = "a" * 40
    if mutation == "kind": freeze["kind"] = "another_campaign"
    if mutation == "parent": freeze["parent_integration_commit"] = "a" * 40
    if mutation == "rules": freeze["rules"]["drag_change_at_most_n"] = 3e-5
    if mutation == "flags": freeze["qualification_flags"]["optimizer"] = True
    if mutation == "identity": freeze.pop("identity_free_check")
    if mutation == "runtime_boolean": freeze["runtime"]["a"]["julia_threads"] = True
    if mutation == "pins": freeze["pins"]["b"].pop("scripts/lowdim01_states.py")
    if mutation == "proposal": inv["proposal"]["coefficient_vector"][0] += .001
    if mutation == "inventory_boolean": inv["states"][0]["sign"] = False
    report = run(valid)
    assert report["verdict"] == "LOWDIM03_INCOMPLETE" and report["integrity"]["pass"] is False


@pytest.mark.parametrize("field", ["geometry_gates", "job_env_common"])
def test_registered_geometry_and_canonical_semantics_reject_internally_consistent_changes(valid, monkeypatch, field):
    # Isolate the semantic guard after the independently tested byte/source checks.
    inventory = valid[3]
    if field == "geometry_gates":
        gates = inventory["states"][1][field]
        gates["gates"]["clearance"] = False
        gates["all_hard_gates_pass"] = False
        reason = "must pass every hard geometry gate"
    else:
        inventory[field]["W4_CANONICAL_STATE_LABEL"] = "another_state"
        reason = "immutable job_env_common"
    load = A.jload
    inv_path = A.ROOT / A.EVIDENCE_REL / "inventory.json"
    monkeypatch.setattr(A, "jload", lambda p: inventory if p == inv_path else load(p))
    with pytest.raises(ValueError, match=reason):
        A.validate_registration(valid[2], inventory)


@pytest.mark.parametrize("field", ["canonical_sdf_origin_m", "canonical_design_spacing_m", "canonical_state_label",
                                  "canonical_design_point_shape", "canonical_design_cell_shape",
                                  "source_surface_sha256", "device_roundtrip_sha256"])
def test_summary_canonical_metadata_must_match_registered_bytes(valid, field):
    output_dir = valid[1]
    summary_path = output_dir / "states" / C.state_name(.625, 1) / "flow_32.summary.json"
    summary = A.jload(summary_path)
    summary[field] = None
    dump(summary_path, summary)
    manifest(output_dir)
    with pytest.raises(ValueError, match=field):
        A.check_kernel(output_dir, "b", valid[2], valid[3])


def cli_args(valid, tmp_path, extra):
    freeze_path = tmp_path / "freeze.json"
    dump(freeze_path, valid[2])
    freeze_path.with_name(freeze_path.name + ".sha256").write_text(A.sha256(freeze_path) + "\n")
    return ["analyze_lowdim03.py", "--kernel-a-dir", str(valid[0]), "--kernel-b-dir", str(valid[1]),
            "--freeze", str(freeze_path), *extra]


def test_cli_check_is_read_only_and_modes_are_exclusive(valid, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", cli_args(valid, tmp_path, ["--check"]))
    A.main()
    target = tmp_path / "analysis.json"
    monkeypatch.setattr(sys, "argv", cli_args(valid, tmp_path, ["--check", "--write", str(target)]))
    with pytest.raises(SystemExit) as err:
        A.main()
    assert err.value.code == 2 and not target.exists()


def test_cli_refuses_invalid_integrity_or_missing_sidecar_before_any_write(valid, tmp_path, monkeypatch):
    target = tmp_path / "analysis.json"
    valid[2]["rules"]["drag_change_at_most_n"] = .001
    monkeypatch.setattr(sys, "argv", cli_args(valid, tmp_path, ["--write", str(target)]))
    with pytest.raises(SystemExit) as err:
        A.main()
    assert err.value.code == 3 and not target.exists()
    (tmp_path / "freeze.json.sha256").unlink()
    with pytest.raises(SystemExit) as err:
        A.main()
    assert err.value.code == 3 and not target.exists()


def test_integrity_valid_no_accept_writes_once_and_refuses_overwrite(valid, tmp_path, monkeypatch):
    # Every positive candidate violates computed drag on b; controls remain unchanged.
    out = valid[1]; inv = valid[3]
    case = inv["grids"]["b"]["measurement"]["case"]
    base = inv["grids"]["b"]["baseline_reference"]["host_recomputed_n"]
    index = A.jload(out / "lowdim03_index.json")
    for step in C.STEPS_MM:
        name = C.state_name(step, 1); directory = out / "states" / name; p = directory / "flow_32.forces.csv"
        force_csv(p, base["downforce_n"] + .0001, base["drag_n"] + .0001, case["flow_spacing_m"] ** 2)
        host = recompute_force_n(p, {"measurement": inv["grids"]["b"]["measurement"]})
        summary_path = directory / "flow_32.summary.json"; summary = A.jload(summary_path)
        summary.update(downforce_time_weighted_n=host["downforce_n"], drag_time_weighted_n=host["drag_n"])
        dump(summary_path, summary)
        next(e for e in index["states"] if e["name"] == name)["forces_csv_sha256"] = A.sha256(p)
    dump(out / "lowdim03_index.json", index); manifest(out)
    target = tmp_path / "analysis.json"
    monkeypatch.setattr(sys, "argv", cli_args(valid, tmp_path, ["--write", str(target)]))
    A.main()
    assert A.jload(target)["verdict"] == "LOWDIM03_NO_ACCEPT" and A.jload(target)["integrity"]["pass"] is True
    original = target.read_bytes()
    with pytest.raises(SystemExit): A.main()
    assert target.read_bytes() == original
