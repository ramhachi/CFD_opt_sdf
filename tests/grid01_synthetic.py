"""Synthetic GRID-01 host-output fixture used only by solver-free tests."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_grid01 as A  # noqa: E402
import build_grid01_freeze as BF  # noqa: E402
import build_grid01_kernel as KB  # noqa: E402
from cfd_sdf import grid01_contract as C  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

INV_PATH = ROOT / A.FILE_PATHS["inventory"]
FORMAL_PATH = ROOT / A.FILE_PATHS["formal_criteria"]
STEP01_ANALYSIS_PATH = ROOT / A.FILE_PATHS["step01_analysis"]
STEP01_INVENTORY_PATH = ROOT / A.FILE_PATHS["step01_inventory"]
INV = json.loads(INV_PATH.read_text())
FORMAL = json.loads(FORMAL_PATH.read_text())
STEP01_ANALYSIS = json.loads(STEP01_ANALYSIS_PATH.read_text())
STEP01_INVENTORY = json.loads(STEP01_INVENTORY_PATH.read_text())
LOWDIM01_INVENTORY = json.loads((ROOT / A.FILE_PATHS["lowdim01_inventory"]).read_text())
BASELINE_FORCE_CSV = ROOT / A.FILE_PATHS["w4_flow32_baseline_csv"]
FORCE_COLUMNS = (
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver", "downforce_solver",
    "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver",
)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_force_csv(path: Path, drag_n: float, downforce_n: float, scale: float) -> None:
    drag, down = drag_n / scale, downforce_n / scale
    with Path(path).open("w") as handle:
        handle.write(",".join(FORCE_COLUMNS) + "\n")
        for step, time in enumerate((0.0, 80.0, 100.0, 120.0, 140.0), start=1):
            values = (step, time, drag, 0.0, -down, drag, down, drag, 0.0, -down, 0.0, 0.0, 0.0)
            handle.write(",".join(format(float(x), ".17g") for x in values) + "\n")


def install_synthetic_root(tmp_path: Path, monkeypatch) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    test_root = Path(tmp_path) / "repo"
    test_root.mkdir(parents=True)
    copied = []
    for relpath in sorted(set(A.FILE_PATHS.values()), key=lambda value: (len(Path(value).parts), value)):
        if any(Path(relpath).is_relative_to(Path(parent)) for parent in copied if (test_root / parent).is_dir()):
            continue
        source = ROOT / relpath
        target = test_root / relpath
        if source.is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            copied.append(relpath)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    runtime_dir = test_root / "infra/kaggle/kernel_grid01_a"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "runner.py").write_text(KB.render("a" * 40))
    metadata = KB.metadata()
    (runtime_dir / "kernel-metadata.json").write_text(json.dumps(metadata, sort_keys=True) + "\n")
    identity_free = {
        "kind": "fd08_v2_kaggle_identity_free_check",
        "all_free": True,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "cli_version": "Kaggle CLI test fixture",
        "intended_slugs": [A.KERNEL_ID.split("/", 1)[1]],
        "listed_slug_clashes": {},
        "owned_kernel_count": 1,
        "owned_dataset_count": 1,
        "owner": A.KERNEL_ID.split("/", 1)[0],
        "status_probes": {
            A.KERNEL_ID.split("/", 1)[1]: {
                kind: {"exit_code": 1, "stdout": "", "stderr": "404 Not Found"}
                for kind in ("kernels", "datasets")
            }
        },
    }
    identity_path = test_root / A.FILE_PATHS["identity_free_check"]
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(identity_free, sort_keys=True) + "\n")
    identity_path.with_name(identity_path.name + ".sha256").write_text(sha(identity_path) + "\n")

    monkeypatch.setattr(A, "ROOT", test_root)
    monkeypatch.setattr(A, "FORMAL", test_root / A.FILE_PATHS["formal_criteria"])
    monkeypatch.setattr(A, "STEP01_ANALYSIS", test_root / A.FILE_PATHS["step01_analysis"])
    monkeypatch.setattr(A, "STEP01_INVENTORY", test_root / A.FILE_PATHS["step01_inventory"])
    monkeypatch.setattr(A, "_source_commit_failures", lambda *_args, **_kwargs: [])
    # This synthetic root has no Git history; real committed-member hashing is tested separately.
    monkeypatch.setattr(A, "frozen_path_sha", lambda _name, path, _commit, **_kwargs: A.sha256(path))
    file_hashes = {name: A.sha256(test_root / relpath) for name, relpath in A.FILE_PATHS.items()}
    inventory = json.loads((test_root / A.FILE_PATHS["inventory"]).read_text())
    file_hashes["inventory_canonical_json"] = A._json_sha(inventory)
    freeze = {
        "kind": "grid01_cross_grid_secant_prerun_freeze",
        "parent_integration_commit": "32e64715dc20a9ac2dd78e3c011bcb48f311b98e",
        "source_commit": "a" * 40,
        "file_hashes": file_hashes,
        "pins": KB.pins(),
        "identity_free_check": identity_free,
        **BF.contract_sections(inventory),
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = make_kernel(test_root, inventory, freeze)
    return output, freeze, inventory


def make_kernel(test_root: Path, inventory: dict[str, Any], freeze: dict[str, Any]) -> Path:
    out = Path(test_root) / "synthetic_kernel_output/grid01_a"
    (out / "states").mkdir(parents=True)
    baseline_host = recompute_force_n(BASELINE_FORCE_CSV, A.flow32_criteria(FORMAL))
    gradients_lift = dict(zip(C.BASIS, (0.72, 0.001, 0.0, -0.35)))
    gradients_drag = dict(zip(C.BASIS, (-0.08, -0.03, -0.12, -0.10)))
    scale = 0.025**2
    index = {"kernel": "a", "kernel_id": A.KERNEL_ID, "states": [], "status": "COMPLETE"}
    for row in inventory["states"]:
        name = row["name"]
        state_dir = out / "states" / name
        state_dir.mkdir()
        if row["kind"] == "baseline":
            shutil.copy2(BASELINE_FORCE_CSV, state_dir / "flow_32.forces.csv")
            host = baseline_host
        else:
            step = row["step_mm"] / 1000.0
            sign = row["sign"]
            direction = row["direction"]
            even_lift = 1.0e-4 if direction == "D2_filtered_seed2026" else 2.0e-6
            even_drag = 1.0e-6
            down = baseline_host["downforce_n"] + sign * step * gradients_lift[direction] + even_lift
            drag = baseline_host["drag_n"] + sign * step * gradients_drag[direction] + even_drag
            write_force_csv(state_dir / "flow_32.forces.csv", drag, down, scale)
            host = recompute_force_n(state_dir / "flow_32.forces.csv", A.flow32_criteria(FORMAL))
        (state_dir / "W4_JOB_DONE").write_text("complete\n")
        (state_dir / "job.log").write_text("synthetic primal fixture; no CFD executed\n")
        summary = {
            "phi_fortran_sha256": row["phi_fortran_order_sha256"],
            "phi_c_order_sha256": row["phi_c_order_sha256"],
            "state_sha256": row["state_sha256"],
            "state_npz_sha256": row["npz_sha256"],
            "gpu_name": "Tesla T4",
            "gpu_uuid": "GPU-grid01-physical-index-zero",
            "case_id": "flow_32",
            "flow_dims": [200, 96, 72],
            "flow_spacing_m": 0.025,
            "phi_margin_m": row["zero_level_margin_m"],
            "phi_margin_gate_m": 0.15,
            "finite_u": True,
            "finite_p": True,
            "finite_forces": True,
            "t_end_reached": 120.0,
            "julia_threads": 1,
            "wall_seconds": 400.0,
            "drag_time_weighted_n": host["drag_n"],
            "downforce_time_weighted_n": host["downforce_n"],
        }
        (state_dir / "flow_32.summary.json").write_text(json.dumps(summary, allow_nan=True) + "\n")
        csv_sha = sha(state_dir / "flow_32.forces.csv")
        index["states"].append({
            "name": name,
            "kind": row["kind"],
            "direction": row["direction"],
            "step_mm": row["step_mm"],
            "sign": row["sign"],
            "exit_code": 0,
            "seconds": 450.0,
            "complete": True,
            "forces_csv_sha256": csv_sha,
            **({"matches_w4_v17_flow32_baseline": True} if row["kind"] == "baseline" else {}),
        })
    index["solver_process_wall_seconds_total"] = 4050.0
    (out / "grid01_index.json").write_text(json.dumps(index, sort_keys=True) + "\n")
    identity = {
        "runner_sha256": freeze["file_hashes"]["rendered_runner"],
        "kernel": "a",
        "kernel_id": A.KERNEL_ID,
        "source_commit": freeze["source_commit"],
        "failure_stage": None,
        "pins": freeze["pins"],
        "verified": freeze["pins"],
        "flow32_baseline_csv_sha256": inventory["flow32_baseline_reference"]["forces_csv_sha256"],
        "selected_gpu": {"index": 0, "name": "Tesla T4", "uuid": "GPU-grid01-physical-index-zero"},
        "cuda_device_order": "PCI_BUS_ID",
        "cuda_visible_devices": "0",
    }
    (out / "run_identity.json").write_text(json.dumps(identity, sort_keys=True) + "\n")
    (out / "nvidia_smi.csv").write_text(
        "1, Tesla T4, GPU-grid01-index-one, 15360 MiB, 535.1\n"
        "0, Tesla T4, GPU-grid01-physical-index-zero, 15360 MiB, 535.1\n"
    )
    probe = {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"],
             "visible_gpu_uuids": ["GPU-grid01-physical-index-zero"], "default_device_uuid": "GPU-grid01-physical-index-zero",
             "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}
    (out / "gpu_device_probe.json").write_text(json.dumps(probe) + "\n")
    (out / "gpu_device_probe.log").write_text("synthetic observed CUDA metadata; no GPU execution\n")
    (out / "DONE").write_text("synthetic complete marker\n")
    files = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob("*")) if path.is_file() and path.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}, sort_keys=True) + "\n")
    return out


def rebuild_manifest(out: Path) -> None:
    files = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob("*")) if path.is_file() and path.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}, sort_keys=True) + "\n")
