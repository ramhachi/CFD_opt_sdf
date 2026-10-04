#!/usr/bin/env python3
"""Run a two-state, one-step CPU rehearsal before FD-08 T4 execution.

The rehearsal confirms the exact registered baseline/perturbation inputs can be
loaded by the CPU WaterLily Candidate C path. Its forces and runtime are setup
diagnostics only and never enter calibration or formal analysis.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.candidate_c_identity import load_candidate_c_identity
from cfd_sdf.fd08_calibration import (
    recompute_force_history,
    verify_output_manifest,
    verify_source_inputs,
)

CPU_FORCE_COLUMNS = (
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver",
    "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
    "viscous_fy_solver", "viscous_fz_solver",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_preview(path: Path) -> tuple[dict, str]:
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("builder-generated CPU rehearsal preview and SHA-256 sidecar are required")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise ValueError("CPU rehearsal preview SHA-256 sidecar mismatch")
    return json.loads(path.read_text()), digest


def verify_preview_dataset(preview: dict, preview_sha: str, dataset_dir: Path) -> dict:
    """Verify builder-staged preview inputs while keeping them outside registration."""
    if (preview.get("kind") != "fd08_candidate_c_cpu_rehearsal_preview"
            or preview.get("evidence_class") != "unregistered_cpu_setup_preview_only"
            or preview.get("immutable") is not False
            or preview.get("registered_before_computation") is not False
            or preview.get("criteria_registered") is not False
            or preview.get("formal_measurement_started") is not False):
        raise ValueError("CPU rehearsal requires a non-registered setup preview, not immutable criteria")
    flags = preview.get("qualification_flags")
    expected_flags = {key: False for key in (
        "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
    if flags != expected_flags:
        raise ValueError("CPU preview must preserve all six literal-false qualification flags")
    states = preview.get("state_order")
    baselines = [row for row in states if row.get("role") == "baseline"] if isinstance(states, list) else []
    perturbations = [row for row in states if row.get("role") == "perturbation"] if isinstance(states, list) else []
    epsilons = preview.get("calibration_epsilon_ladder_m")
    expected_directions = {
        "D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026",
    }
    cells = {
        (row.get("direction_id"), float(row.get("epsilon_m", float("nan"))), row.get("sign"))
        for row in perturbations
    }
    expected_cells = {
        (direction, float(epsilon), sign)
        for direction in expected_directions for epsilon in (epsilons or []) for sign in (-1, 1)
    }
    valid_epsilon_ladder = (
        isinstance(epsilons, list) and len(epsilons) == 7
        and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)) and float(value) > 0.0 for value in epsilons)
        and all(float(left) < float(right) for left, right in zip(epsilons, epsilons[1:]))
        and float(epsilons[-1]) / float(epsilons[0]) >= 1000.0
    )
    valid_signed_cells = all(
        isinstance(row, dict)
        and isinstance(row.get("sign"), int) and not isinstance(row.get("sign"), bool)
        and row["sign"] in (-1, 1)
        and row.get("direction_id") in expected_directions
        for row in perturbations
    )
    if (not isinstance(states, list) or len(states) != 47 or len(baselines) != 5
            or len(perturbations) != 42 or len({row.get("name") for row in states}) != 47
            or not valid_epsilon_ladder or not valid_signed_cells
            or cells != expected_cells):
        raise ValueError("CPU preview must preserve the builder's complete five-plus-forty-two state inventory")
    files = preview.get("dataset_files")
    if not isinstance(files, dict) or not files:
        raise ValueError("CPU preview dataset inventory is missing")
    root = Path(dataset_dir).resolve()
    contract_name = "cpu_rehearsal_preview.json"
    sidecar_name = f"{contract_name}.sha256"
    sidecar_path = root / sidecar_name
    if not sidecar_path.is_file() or sidecar_path.is_symlink():
        raise ValueError("CPU rehearsal preview SHA-256 sidecar is missing or unsafe")
    expected = {**files, contract_name: preview_sha}
    expected[sidecar_name] = hashlib.sha256((root / sidecar_name).read_bytes()).hexdigest()
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"CPU preview contains a symbolic link: {path.relative_to(root)}")
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = path
    if set(actual) != set(expected):
        raise ValueError("CPU preview dataset inventory differs from its generated preview contract")
    if (actual[contract_name].resolve() != (root / contract_name).resolve()
            or sha256(actual[contract_name]) != preview_sha
            or actual[sidecar_name].read_text().strip() != preview_sha):
        raise ValueError("CPU preview contract or its sidecar changed after staging")
    for name, digest in files.items():
        if (not isinstance(name, str) or name != Path(name).as_posix()
                or Path(name).is_absolute() or ".." in Path(name).parts
                or name in {contract_name, sidecar_name}
                or not isinstance(digest, str) or len(digest) != 64):
            raise ValueError("CPU preview contains an unsafe or invalid staged file entry")
        path = actual[name].resolve()
        if root not in path.parents or sha256(path) != digest:
            raise ValueError(f"CPU preview staged file SHA-256 mismatch: {name}")
    return {
        "dataset_root": root.as_posix(), "verified_file_count": len(files),
        "preview_sha256": preview_sha,
        "inventory_sha256": hashlib.sha256(
            "\n".join(f"{name}  {files[name]}" for name in sorted(files)).encode()
        ).hexdigest(),
    }


def choose_states(criteria: dict) -> list[dict]:
    states = criteria.get("state_order", [])
    baselines = [row for row in states if row.get("role") == "baseline"]
    perturbations = [row for row in states if row.get("role") == "perturbation"]
    if not baselines or not perturbations:
        raise ValueError("CPU rehearsal requires registered baseline and perturbation inputs")
    first_epsilon = min(float(row["epsilon_m"]) for row in perturbations)
    direction = "D0_interface_offset"
    candidates = [row for row in perturbations if row.get("direction_id") == direction
                  and float(row["epsilon_m"]) == first_epsilon and row.get("sign") == 1]
    if len(candidates) != 1:
        raise ValueError("CPU rehearsal requires the registered D0 smallest-epsilon plus state")
    return [baselines[0], candidates[0]]


def audit_cpu_force_history(path: Path, *, force_scale: float,
                            component_tolerances: tuple[float, float]) -> dict:
    """Parse the two-row CPU trace through the production raw-history parser."""
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CPU_FORCE_COLUMNS:
            raise ValueError("CPU rehearsal force-history CSV schema mismatch")
        rows = list(reader)
    if len(rows) != 2:
        raise ValueError("CPU rehearsal must emit initial and post-step force rows")
    try:
        step_time = [(float(row["step"]), float(row["t_u_l"])) for row in rows]
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("CPU rehearsal force-history step/time columns are invalid") from exc
    if (step_time[0][0] != 0 or step_time[1][0] != 1
            or step_time[0][1] != 0.0 or not step_time[1][1] > step_time[0][1]):
        raise ValueError("CPU rehearsal force history does not contain initial and one-step endpoints")
    audit = recompute_force_history(
        path, force_scale_n_per_solver_force=force_scale,
        window_t_u_l=(step_time[0][1], step_time[1][1]),
        force_component_tolerances=component_tolerances,
    )
    if (audit["row_count"] != 2 or audit["force_component_audit"]["verified"] is not True
            or audit["window_t_u_l"] != [step_time[0][1], step_time[1][1]]):
        raise ValueError("CPU raw-history host parse did not verify the complete one-step window")
    return audit


def write_cpu_output_manifest(output_root: Path, terminal_path: Path, completed_count: int) -> dict:
    """Seal raw CPU runner outputs, terminal state and hashes before host parsing."""
    output_root = Path(output_root)
    reserved = {"sha256.json", "DONE"}
    inventory = {}
    for path in output_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"CPU runner output contains a symbolic link: {path.relative_to(output_root)}")
        if path.is_file():
            name = path.relative_to(output_root).as_posix()
            if name not in reserved:
                inventory[name] = sha256(path)
    manifest_path = output_root / "sha256.json"
    done_path = output_root / "DONE"
    if manifest_path.exists() or done_path.exists():
        raise FileExistsError("refusing to overwrite CPU rehearsal manifest or terminal marker")
    manifest_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    done_path.write_text(json.dumps({
        "status": "FINISHED_STATE_LOOP",
        "status_counts": {"COMPLETED": completed_count},
    }, indent=2, sort_keys=True) + "\n")
    return verify_output_manifest(output_root, terminal_path)


def parse_cpu_completion_marker(text: str, *, run_id: str, phi_sha256: str,
                                force_csv_sha256: str, margin_gate_m: float,
                                margin_tolerance_m: float) -> dict:
    """Bind the one-step solver terminal to its inputs, runtime and raw history."""
    prefix = f"FD08_CPU_REHEARSAL_DONE run_id={run_id} "
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    invoked = f"FD08_CPU_REHEARSAL_STEP_INVOKED run_id={run_id}"
    if len(lines) != 1 or text.splitlines().count(invoked) != 1:
        raise ValueError("CPU rehearsal log must contain one invoked and one completion marker for its state")
    fields = {}
    for token in lines[0].split()[1:]:
        key, separator, value = token.partition("=")
        if not separator or not value or key in fields:
            raise ValueError("CPU rehearsal completion marker has an invalid field")
        fields[key] = value
    expected = {
        "run_id": run_id,
        "phi_fortran_sha256": phi_sha256,
        "backend": "Array",
        "steps": "1",
        "force_rows": "2",
        "csv_sha256": force_csv_sha256,
        "qualification": "false",
    }
    if any(fields.get(key) != value for key, value in expected.items()):
        raise ValueError("CPU rehearsal completion marker does not match its input or force-history identity")
    try:
        margin = float(fields["margin_m"])
    except (KeyError, ValueError) as exc:
        raise ValueError("CPU rehearsal completion marker margin is invalid") from exc
    if (not math.isfinite(margin) or not math.isfinite(margin_gate_m)
            or not math.isfinite(margin_tolerance_m) or margin_tolerance_m < 0
            or margin < margin_gate_m - margin_tolerance_m
            or not fields.get("julia") or not fields.get("waterlily")):
        raise ValueError("CPU rehearsal completion marker runtime or SDF margin is invalid")
    return {
        "julia_version": fields["julia"],
        "waterlily_version": fields["waterlily"],
        "backend": fields["backend"],
        "phi_margin_m": margin,
        "solver_steps": int(fields["steps"]),
        "force_row_count": int(fields["force_rows"]),
        "force_csv_sha256": fields["csv_sha256"],
    }


def _write_failure(output_dir: Path, source_commit: str, preview_sha: str,
                   failed_run_id: str, error: Exception) -> None:
    """Keep a failed bounded rehearsal append-only and outside solver evidence namespaces."""
    path = Path(output_dir) / "rehearsal_failure.json"
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"refusing to overwrite CPU rehearsal failure evidence: {path}")
    payload = (json.dumps({
        "kind": "fd08_cpu_rehearsal_failure",
        "source_commit": source_commit,
        "preview_sha256": preview_sha,
        "failed_run_id": failed_run_id,
        "error_type": type(error).__name__,
        "error": str(error),
        "evidence_class": "cpu_setup_harness_or_environment_failure_not_scientific_verdict",
        "formal_qualification": False,
    }, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.write_bytes(payload)
    sidecar.write_text(hashlib.sha256(payload).hexdigest() + "\n")


def resolve_output_directory(output_dir: Path) -> Path:
    """Resolve a commit-ready rehearsal directory and reject paths outside this checkout."""
    root = ROOT.resolve()
    resolved = Path(output_dir).resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("CPU rehearsal output must resolve inside the repository")
    return resolved


def rehearse(preview_path: Path, dataset_dir: Path, output_dir: Path, julia: str | None = None) -> dict:
    preview, preview_sha = load_preview(preview_path)
    dataset_audit = verify_preview_dataset(preview, preview_sha, dataset_dir)
    source_hashes = verify_source_inputs(preview.get("source_inputs", {}), root=ROOT)
    if not {"calibration_registrar", "cpu_rehearsal_cli", "cpu_rehearsal_job",
            "cpu_julia_project", "cpu_julia_manifest"}.issubset(source_hashes):
        raise ValueError("CPU preview does not bind the calibration builder and rehearsal sources")
    source_commit = preview.get("source_commit")
    current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if (branch != "codex/kaggle-batch-migration"
            or not isinstance(source_commit, str) or current_head != source_commit):
        raise ValueError("CPU rehearsal must run on the exact integration source commit frozen in the preview")
    if preview.get("candidate_c_identity") != load_candidate_c_identity(ROOT):
        raise ValueError("CPU rehearsal preview differs from the frozen Candidate C source identity")
    selected = choose_states(preview)
    exe = julia or shutil.which("julia")
    if not exe:
        raise ValueError("Julia executable was not found; pass --julia")
    output_dir = resolve_output_directory(output_dir)
    reserved_roots = (
        ROOT / "docs/evidence/fd08_candidate_c_calibration_2026_10_04/result",
        ROOT / "docs/evidence/fd08_candidate_c_formal_2026_10_04/result",
    )
    resolved_output = output_dir.resolve()
    if any(resolved_output == reserved or reserved in resolved_output.parents or resolved_output in reserved.parents
           for reserved in (path.resolve() for path in reserved_roots)):
        raise ValueError("CPU rehearsal output must stay outside calibration and formal result namespaces")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty CPU rehearsal directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_preview = output_dir / "cpu_rehearsal_preview.json"
    evidence_preview_sidecar = evidence_preview.with_suffix(evidence_preview.suffix + ".sha256")
    if evidence_preview.exists() or evidence_preview_sidecar.exists():
        raise FileExistsError("refusing to overwrite committed CPU rehearsal preview evidence")
    shutil.copyfile(preview_path, evidence_preview)
    shutil.copyfile(Path(preview_path).with_suffix(Path(preview_path).suffix + ".sha256"),
                    evidence_preview_sidecar)
    if sha256(evidence_preview) != preview_sha or evidence_preview_sidecar.read_text().strip() != preview_sha:
        raise ValueError("copied CPU rehearsal preview differs from the builder-generated contract")
    input_evidence_dir = output_dir / "inputs"
    input_evidence_dir.mkdir()
    runner_output = output_dir / "runner_output"
    runner_output.mkdir()
    job = ROOT / "scripts/waterlily_fd08_cpu_rehearsal.jl"
    project = ROOT / "julia/CFDSDFWaterLily"
    completed = []
    case = preview["case"]
    force_scale = (float(case["density_kg_m3"]) * float(case["freestream_mps"][0]) ** 2
                   * float(case["flow_spacing_m"]) ** 2)
    measurement = preview["measurement"]
    component_tolerances = (
        float(measurement["force_component_relative_tolerance"]),
        float(measurement["force_component_absolute_tolerance"]),
    )
    for state in selected:
        run_id = state["name"]
        raw_relative = Path(state["raw_file"])
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id)
                or raw_relative.is_absolute() or ".." in raw_relative.parts
                or state["raw_file"] not in preview["dataset_files"]):
            raise ValueError("CPU rehearsal state contains an unsafe or unverified preview path")
        raw_path = (Path(dataset_dir).resolve() / raw_relative).resolve()
        if Path(dataset_dir).resolve() not in raw_path.parents:
            raise ValueError("CPU rehearsal state raw phi escaped the registered dataset directory")
        if sha256(raw_path) != state["phi_fortran_sha256"]:
            raise ValueError(f"registered raw phi hash mismatch: {run_id}")
        input_evidence = input_evidence_dir / f"{run_id}.phi_f4_fortran.raw"
        if input_evidence.exists():
            raise FileExistsError(f"refusing to overwrite CPU rehearsal input evidence: {input_evidence}")
        shutil.copyfile(raw_path, input_evidence)
        if sha256(input_evidence) != state["phi_fortran_sha256"]:
            raise ValueError(f"copied CPU rehearsal input differs from its registered phi hash: {run_id}")
        force_csv = runner_output / f"{run_id}.forces.csv"
        geometry = preview["geometry"]
        margin_gate = float(geometry["phi_margin_gate_m"])
        margin_tolerance = float(geometry["phi_margin_tolerance_m"])
        command = [str(exe), "--startup-file=no", f"--project={project}", str(job),
                   str(input_evidence), state["phi_fortran_sha256"], run_id, str(force_csv),
                   str(margin_gate), str(margin_tolerance)]
        log_path = runner_output / f"{run_id}.log"
        try:
            process = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, check=False)
            if log_path.exists():
                raise FileExistsError(f"refusing to overwrite CPU rehearsal log: {log_path}")
            log_path.write_text(process.stdout)
            marker = f"FD08_CPU_REHEARSAL_DONE run_id={run_id}"
            if process.returncode != 0 or marker not in process.stdout or not force_csv.is_file():
                raise RuntimeError(f"CPU rehearsal failed for {state['name']}; see {log_path}")
            history_audit = audit_cpu_force_history(
                force_csv, force_scale=force_scale, component_tolerances=component_tolerances,
            )
            runtime = parse_cpu_completion_marker(
                process.stdout, run_id=run_id,
                phi_sha256=state["phi_fortran_sha256"],
                force_csv_sha256=history_audit["sha256"],
                margin_gate_m=margin_gate, margin_tolerance_m=margin_tolerance,
            )
            summary = {
                "run_id": run_id, "role": state["role"],
                "phi_fortran_sha256": state["phi_fortran_sha256"],
                "cpu_runtime": runtime,
                "force_csv_sha256": history_audit["sha256"],
                "host_recomputed_force_n": history_audit["force_n"],
                "row_count": history_audit["row_count"],
                "force_component_audit": history_audit["force_component_audit"],
                "window_t_u_l": history_audit["window_t_u_l"],
                "evidence_class": "cpu_one_step_diagnostic_only",
            }
            summary_path = runner_output / f"{run_id}.summary.json"
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
            completed.append({
                "run_id": run_id, "role": state["role"],
                "phi_fortran_sha256": state["phi_fortran_sha256"],
                "log_path": (Path("runner_output") / log_path.name).as_posix(),
                "log_sha256": sha256(log_path),
                "force_csv_path": (Path("runner_output") / force_csv.name).as_posix(),
                "force_csv_sha256": history_audit["sha256"],
                "summary_path": (Path("runner_output") / summary_path.name).as_posix(),
                "summary_sha256": sha256(summary_path),
                "force_history_host_audit": history_audit,
                "cpu_runtime": runtime,
                "solver_steps": 1, "status": "CPU_REHEARSAL_PASS",
            })
        except Exception as exc:
            _write_failure(output_dir, source_commit, preview_sha, run_id, exc)
            raise

    runner_terminal = runner_output / "cpu_runner_result.json"
    runner_terminal.write_text(json.dumps({
        "kind": "fd08_cpu_rehearsal_kernel_terminal",
        "all_states_completed": True,
        "states": {row["run_id"]: {"status": "COMPLETED"} for row in completed},
        "status_counts": {"COMPLETED": len(completed)},
    }, indent=2, sort_keys=True, allow_nan=False) + "\n")
    runner_manifest_audit = write_cpu_output_manifest(
        runner_output, runner_terminal, len(completed),
    )
    runner_files = []
    for path in sorted(runner_output.rglob("*")):
        if path.is_file():
            runner_files.append({
                "path": (Path("runner_output") / path.relative_to(runner_output)).as_posix(),
                "sha256": sha256(path),
            })
    result = {
        "kind": "fd08_cpu_rehearsal",
        "evidence_class": "cpu_setup_operator_rehearsal_only",
        "preview_path": evidence_preview.relative_to(ROOT).as_posix(), "preview_sha256": preview_sha,
        "source_commit": source_commit,
        "verified_source_inputs": source_hashes,
        "preview_dataset_audit": dataset_audit,
        "input_state_bindings": [
            {"run_id": row["name"], "role": row["role"],
             "phi_fortran_sha256": row["phi_fortran_sha256"],
             "raw_phi_evidence_path": (Path("inputs") / f"{row['name']}.phi_f4_fortran.raw").as_posix(),
             "raw_phi_evidence_sha256": row["phi_fortran_sha256"]}
            for row in selected
        ],
        "states": completed,
        "runner_output_path": "runner_output",
        "runner_terminal_path": "runner_output/cpu_runner_result.json",
        "runner_output_manifest_audit": runner_manifest_audit,
        "runner_output_file_inventory": runner_files,
        "criteria_registered": False,
        "registered_force_measurement_started": False,
        "gpu_qualification_started": False,
        "calibration_evidence": False,
        "formal_qualification": False,
        "qualification_flags": preview["qualification_flags"],
    }
    result_path = output_dir / "rehearsal_result.json"
    sidecar = output_dir / "rehearsal_result.json.sha256"
    if result_path.exists() or sidecar.exists():
        raise FileExistsError("refusing to overwrite append-only CPU rehearsal result")
    payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    result_path.write_bytes(payload)
    sidecar.write_text(hashlib.sha256(payload).hexdigest() + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-contract", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--julia", default=None)
    args = parser.parse_args()
    result = rehearse(args.preview_contract, args.dataset, args.output, args.julia)
    print(json.dumps({"kind": result["kind"], "states": len(result["states"]),
                      "evidence_class": result["evidence_class"], "formal_qualification": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
