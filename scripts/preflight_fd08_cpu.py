#!/usr/bin/env python3
"""Run a two-state, one-step CPU rehearsal before FD-08 T4 execution.

The rehearsal confirms the exact registered baseline/perturbation inputs can be
loaded by the CPU WaterLily Candidate C path. Its forces and runtime are setup
diagnostics only and never enter calibration or formal analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.fd08_calibration import verify_registered_dataset


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_immutable(path: Path) -> tuple[dict, str]:
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("immutable FD-08 criteria and SHA-256 sidecar are required")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise ValueError("FD-08 criteria SHA-256 sidecar mismatch")
    return json.loads(path.read_text()), digest


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


def rehearse(criteria_path: Path, dataset_dir: Path, output_dir: Path, julia: str | None = None) -> dict:
    criteria, criteria_sha = load_immutable(criteria_path)
    if (criteria.get("kind") not in {"fd08_candidate_c_calibration", "fd08_candidate_c_formal"}
            or criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True):
        raise ValueError("CPU rehearsal accepts only immutable preregistered FD-08 criteria")
    dataset_audit = verify_registered_dataset(criteria, criteria_sha, dataset_dir)
    selected = choose_states(criteria)
    exe = julia or shutil.which("julia")
    if not exe:
        raise ValueError("Julia executable was not found; pass --julia")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty CPU rehearsal directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    job = ROOT / "scripts/waterlily_fd08_cpu_rehearsal.jl"
    project = ROOT / "julia/CFDSDFWaterLily"
    completed = []
    for state in selected:
        run_id = state["name"]
        raw_relative = Path(state["raw_file"])
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id)
                or raw_relative.is_absolute() or ".." in raw_relative.parts
                or state["raw_file"] not in criteria["dataset_files"]):
            raise ValueError("CPU rehearsal state contains an unsafe or unregistered path")
        raw_path = (Path(dataset_dir).resolve() / raw_relative).resolve()
        if Path(dataset_dir).resolve() not in raw_path.parents:
            raise ValueError("CPU rehearsal state raw phi escaped the registered dataset directory")
        if sha256(raw_path) != state["phi_fortran_sha256"]:
            raise ValueError(f"registered raw phi hash mismatch: {run_id}")
        command = [str(exe), "--startup-file=no", f"--project={project}", str(job),
                   str(raw_path), state["phi_fortran_sha256"], run_id]
        process = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, check=False)
        log_path = output_dir / f"{run_id}.log"
        if log_path.exists():
            raise FileExistsError(f"refusing to overwrite CPU rehearsal log: {log_path}")
        log_path.write_text(process.stdout)
        marker = f"FD08_CPU_REHEARSAL_DONE run_id={run_id}"
        if process.returncode != 0 or marker not in process.stdout:
            raise RuntimeError(f"CPU rehearsal failed for {state['name']}; see {log_path}")
        completed.append({
            "run_id": run_id, "role": state["role"],
            "phi_fortran_sha256": state["phi_fortran_sha256"],
            "log_path": log_path.name, "log_sha256": sha256(log_path),
            "solver_steps": 1, "status": "CPU_REHEARSAL_PASS",
        })
    result = {
        "kind": "fd08_cpu_rehearsal",
        "evidence_class": "cpu_setup_operator_rehearsal_only",
        "criteria_path": Path(criteria_path).as_posix(), "criteria_sha256": criteria_sha,
        "registered_dataset_audit": dataset_audit,
        "states": completed,
        "registered_force_measurement_started": False,
        "gpu_qualification_started": False,
        "calibration_evidence": False,
        "formal_qualification": False,
        "qualification_flags": criteria.get("qualification_flags"),
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
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--julia", default=None)
    args = parser.parse_args()
    result = rehearse(args.criteria, args.dataset, args.output, args.julia)
    print(json.dumps({"kind": result["kind"], "states": len(result["states"]),
                      "evidence_class": result["evidence_class"], "formal_qualification": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
