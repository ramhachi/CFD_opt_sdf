#!/usr/bin/env python3
"""G2-DIAG5 local driver: runs the registered matrix of CPU processes (one julia -t 1 process per state x group) and writes DONE only if every process completed.

The pins (SHA-256 of the job, the stage copies, the Julia project files, the stored-state indexes) are checked before anything runs.  Fail closed: any mismatch,
any non-zero exit or any missing result writes ERROR.txt and no DONE.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "e06e3364c3436db1b681e8934ec6a43ed498814f"
SRC_TREE = "julia/CFDSDFWaterLily/src"      # every file the job `include`s lives here; pinned as one tree hash
JOB = "scripts/waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl"
STAGES = "scripts/waterlily_grad_g2_diag5_stages.jl"
PINS = {
    JOB: "85a032c29d9008a8404ddba61f027144a9300408030a588aa9f2687d1e75eb87",
    STAGES: "b0aa40bfe3c33b75a639853eaf86d36a93b70f0a40b11f100a6020872cbee06a",
    "julia/CFDSDFWaterLily/Project.toml": "5abca50d507cd809e6950ec654703cd1887977aab14ba5b864bcf066b4865e27",
    "julia/CFDSDFWaterLily/Manifest.toml": "65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c",
    SRC_TREE: "9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85",
    "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/snapshot_index.json": "38ee230b0e3b139cb3f185358fed08e839b18c4d0d8707c60727d27879d8d2e2",
    "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/instrumented_checksums.csv": "776779dab31eb1c79d3c4599c9faafae30fb14dd56860f803450be49b0744f8c",
}
PHI = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
PHI_SHA = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
D0 = "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw"
D0_SHA = "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"
SNAP_INDEX = "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/snapshot_index.json"
CHECKSUMS = "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/instrumented_checksums.csv"
EPS_E5 = ("1e-5", "1e-4", "1e-3", "1e-2")
STATES = ("S900", "S1000")
GROUPS = ("E1", "E2", "E3", "E3C", "E5AD", *(f"E5FD:{e}" for e in EPS_E5), "E6")
MATRIX = [("R1188", "E0"), *((s, g) for s in STATES for g in GROUPS)]


def sha256(path: Path) -> str:
    path = Path(path)
    if path.is_dir():       # a tree hash: SHA-256 over the sorted "relative path  file hash" lines
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag(state: str, group: str) -> str:
    return f"{state}_{group.replace(':', '_')}"


def git_state() -> tuple[str, list[str]]:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    bad = []
    if subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip():
        bad.append("the working tree has uncommitted changes to tracked files")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"], capture_output=True).returncode != 0:
        bad.append("HEAD does not contain the pinned source commit")
    return head, bad


def run_one(julia: str, snapdir: Path, out: Path, state: str, group: str) -> dict:
    d = out / tag(state, group)
    cmd = [julia, "-t", "1", f"--project={ROOT / 'julia/CFDSDFWaterLily'}", str(ROOT / JOB), str(ROOT / PHI), PHI_SHA, str(ROOT / D0), D0_SHA,
           str(snapdir), str(ROOT / SNAP_INDEX), str(ROOT / CHECKSUMS), str(d), state, group]
    started = time.time()
    with (out / f"{tag(state, group)}.log").open("w") as log:
        env = {k: v for k, v in os.environ.items() if not k.startswith("DIAG5_")}      # the dry-run switches must never reach a registered run
        code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
    status = json.loads((d / "status.json").read_text()) if (d / "status.json").is_file() else {}
    ok = code == 0 and (d / "result.json").is_file() and status.get("status") == "COMPLETE" and status.get("dryrun") is False and status.get("k_steps") == 40
    return {"state": state, "group": group, "exit": code, "ok": ok, "seconds": time.time() - started}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapdir", required=True, type=Path, help="the DIAG1 snapshot directory (outside git)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--julia", default="julia")
    p.add_argument("--jobs", type=int, default=8)
    args = p.parse_args()
    if args.out.exists():
        sys.exit("refusing to overwrite an existing output directory")
    args.out.mkdir(parents=True)
    failures: list[str] = []
    for rel, digest in PINS.items():
        if sha256(ROOT / rel) != digest:
            failures.append(f"pin mismatch: {rel}")
    head, git_failures = git_state()
    failures += git_failures
    index = {"tier": "G2-DIAG5", "source_commit": SOURCE_COMMIT, "git_head_at_run": head, "pins": PINS, "matrix": [list(m) for m in MATRIX], "julia": args.julia, "jobs": args.jobs,
             "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "processes": []}
    if failures:
        (args.out / "ERROR.txt").write_text("\n".join(failures) + "\n")
        (args.out / "driver_index.json").write_text(json.dumps(index, indent=2) + "\n")
        sys.exit(1)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_one, args.julia, args.snapdir, args.out, s, g) for s, g in MATRIX]
            for f in futures:
                index["processes"].append(f.result())
    except BaseException as err:  # noqa: BLE001
        failures.append(f"driver error: {type(err).__name__}: {err}")
    failures += [f"process failed: {r['state']} {r['group']} (exit {r['exit']})" for r in index["processes"] if not r["ok"]]
    if len(index["processes"]) != len(MATRIX):
        failures.append("process inventory incomplete")
    index["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    index["status"] = "COMPLETE" if not failures else "ERROR"
    (args.out / "driver_index.json").write_text(json.dumps(index, indent=2) + "\n")
    if failures:
        (args.out / "ERROR.txt").write_text("\n".join(failures) + "\n")
        sys.exit(1)
    (args.out / "DONE").write_text("DIAG5 matrix completed; run the host analyzer once.\n")


if __name__ == "__main__":
    main()
