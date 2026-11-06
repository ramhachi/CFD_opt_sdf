#!/usr/bin/env python3
"""Run an explicitly configured GRAD-00 CPU side arm and retain analyzer-compatible artifacts.

This wrapper never installs packages or changes manifests. It requires committed
source bytes, an authenticated epsilon/spread reference, and an existing Julia
environment. A complete or intact BLOCKED Julia job returns wrapper exit 0;
failures retain identity/log/ERROR.txt but never DONE or an output manifest.
No full CPU measurement is authorized by creating or testing this wrapper.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_grad00_kernels as B  # noqa: E402
from analyze_grad00 import INPUT_SHA256  # noqa: E402

PROJECTS = ("julia/CFDSDFWaterLily", "julia/CFDSDFWaterLily110")
DRYRUN_SWITCHES = ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT", "GRAD00_PREFLIGHT_ONLY")
MAX_TIMEOUT_S = 60 * 3600  # GRAD-00 rev 0 arm F CPU budget; never extended here.
CPU_THREADS = 10  # GRAD-00 rev 0 arm F: Mac with ten Julia threads; match Float32 controls.


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def verify_terminal(out: Path, code: int, arm: str, real_type: str, project: str) -> None:
    """Check the CPU 7/13-run terminal before publishing transport artifacts."""
    expected_status = {0: "COMPLETE", 3: "BLOCKED"}[code]
    directions = B.DIRECTIONS[:2] if real_type == "Float64" else B.DIRECTIONS
    order = ["plain", *(d + suffix for d in directions for suffix in ("", "__plus", "__minus"))]
    for filename in ("g2_run_index.json", "grad00_index.json"):
        index = json.loads((out / filename).read_text())
        if (index["status"] != expected_status or index["arm"] != arm or index["real_type"] != real_type
                or index["backend"] != "cpu" or index["preflight"]["pass"] is not True
                or index["waterlily"] != ("1.10.0" if project == PROJECTS[1] else "1.8.0")):
            raise ValueError(f"{filename}: exit status, arm, precision, runtime or preflight mismatch")
        statuses = index["run_status"]
        if (index["directions"] != list(directions) or index["run_order"] != order
                or set(index["runs"]) != set(order) or set(statuses) != set(order)):
            raise ValueError(f"{filename}: incomplete CPU {len(order)}-run inventory")
        if any(status not in (("COMPLETE", "BLOCKED") if name in directions else ("COMPLETE",)) for name, status in statuses.items()):
            raise ValueError(f"{filename}: invalid run status")
        if ("BLOCKED" in statuses.values()) != (code == 3):
            raise ValueError(f"{filename}: BLOCKED status does not match Julia exit code")


def run_cpu(*, source_commit: str, reference_path: Path, output_dir: Path, arm: str, real_type: str,
            timeout_s: float, project: str = PROJECTS[0], julia: str = "julia") -> int:
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"refusing to overwrite CPU output: {output_dir}")
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= MAX_TIMEOUT_S:
        raise ValueError("timeout_s must be positive, finite and at most 60 CPU hours")
    if arm not in ("quick", "quick_nobound") or real_type not in ("Float32", "Float64") or project not in PROJECTS:
        raise ValueError("CPU precision comparison requires quick/quick_nobound, Float32/Float64 and a declared CPU project")
    if project == PROJECTS[1] and (arm != "quick" or real_type != "Float32"):
        raise ValueError("WaterLily 1.10.0 side E requires quick Float32")
    if not re.fullmatch(r"[a-f0-9]{40}", source_commit):
        raise ValueError("source commit must be a full lowercase SHA")
    reference = B.reference_config(reference_path)
    if reference is None:
        raise ValueError("an authenticated epsilon/spread reference is required")
    paths = B.pin_paths(reference) - {f"{B.PROJECT}/Project.toml", f"{B.PROJECT}/Manifest.toml"}
    paths.update((f"{project}/Project.toml", f"{project}/Manifest.toml", "scripts/run_grad00_cpu.py"))
    B.verify_source(source_commit, paths)
    pins = {name: B.sha(ROOT / name) for name in sorted(paths)}
    if (pins[reference["path"]] != reference["sha256"]
            or any(pins[name] != digest for name, digest in reference["sources"].items())):
        raise ValueError("reference bytes changed after authentication")
    inputs = [(B.PHI_RAW, INPUT_SHA256["phi"]),
              *((f"{B.INPUT_DIR}/{d}.dir_f4_fortran.raw", INPUT_SHA256["directions"][d]) for d in B.DIRECTIONS)]
    if any(pins[name] != digest for name, digest in inputs):
        raise ValueError("canonical input SHA mismatch")
    identity = {"source_commit": source_commit, "source_tree_id": B.tree_id(source_commit),
                "runner_sha256": B.sha(Path(__file__)), "runner": "run_grad00_cpu.py", "arm": arm,
                "project": project, "real_type": real_type, "backend": "cpu", "timeout_s": timeout_s,
                "julia_threads": CPU_THREADS,
                "pins": pins, "verified": dict(pins), "reference": reference,
                "phi_sha256": INPUT_SHA256["phi"], "direction_sha256": INPUT_SHA256["directions"],
                "failure_stage": None, "status": "RUNNING"}
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True)
    write_json(output_dir / "run_identity.json", identity)
    stage = "measurement"
    try:
        env = os.environ.copy()
        for name in DRYRUN_SWITCHES:
            env.pop(name, None)
        env.update(G2_BACKEND="cpu", GRAD00_ARM=arm, GRAD00_T=real_type, JULIA_NUM_THREADS=str(CPU_THREADS))
        args = [julia, f"--project={ROOT / project}", str(ROOT / B.SCRIPT), str(ROOT / B.PHI_RAW), INPUT_SHA256["phi"], str(output_dir)]
        for direction in B.DIRECTIONS:
            args += [str(ROOT / B.INPUT_DIR / f"{direction}.dir_f4_fortran.raw"), INPUT_SHA256["directions"][direction]]
        args += [str(reference["directions"][direction]["epsilon_m"]) for direction in B.DIRECTIONS]
        with (output_dir / "measurement.log").open("w") as log:
            result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout_s, cwd=ROOT, check=False)
        identity["spike_exit_code"] = result.returncode
        if result.returncode not in (0, 3):
            raise RuntimeError(f"CPU Julia job exited {result.returncode}")
        stage = "terminal_verification"
        for name in ("Project.toml", "Manifest.toml"):
            if B.sha(ROOT / project / name) != pins[f"{project}/{name}"]:
                raise ValueError(f"{name} changed during the CPU job")
        verify_terminal(output_dir, result.returncode, arm, real_type, project)
        identity["status"] = "COMPLETE" if result.returncode == 0 else "BLOCKED"
        write_json(output_dir / "run_identity.json", identity)
        (output_dir / "DONE").write_text("GRAD-00 CPU terminal verified; run the campaign analyzer once after all required arms exist.\n")
        write_json(output_dir / "output_manifest.json", {"files": {str(p.relative_to(output_dir)): B.sha(p)
                   for p in sorted(output_dir.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}})
        return 0
    except BaseException:
        (output_dir / "DONE").unlink(missing_ok=True)
        (output_dir / "output_manifest.json").unlink(missing_ok=True)
        identity.update(failure_stage=stage, status="ERROR")
        write_json(output_dir / "run_identity.json", identity)
        (output_dir / "ERROR.txt").write_text(traceback.format_exc())
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=("quick", "quick_nobound"), required=True)
    parser.add_argument("--real-type", choices=("Float32", "Float64"), required=True)
    parser.add_argument("--project", choices=PROJECTS, default=PROJECTS[0])
    parser.add_argument("--timeout-s", type=float, required=True)
    parser.add_argument("--julia", default="julia", help="existing Julia executable; no installation is performed")
    args = parser.parse_args()
    try:
        code = run_cpu(source_commit=args.source_commit, reference_path=args.reference, output_dir=args.output_dir,
                       arm=args.arm, real_type=args.real_type, project=args.project, timeout_s=args.timeout_s, julia=args.julia)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"GRAD-00 CPU prerequisite failure: {error}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
