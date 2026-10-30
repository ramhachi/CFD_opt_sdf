#!/usr/bin/env python3
"""Render the GRAD-TA1 Kaggle worker from the committed, byte-verified inputs (pattern of scripts/build_lowdim04a_kernel.py, whose sha / verify_source are reused)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_lowdim04a_kernel import sha, verify_source  # noqa: E402,F401  (directory-aware SHA-256; committed-bytes check)

TEMPLATE = ROOT / "scripts/grad_ta1_runner_template.py"
KERNEL_DIR = ROOT / "infra/kaggle/kernel_grad_ta1"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-grad-ta1"
PROJECT = "julia/CFDSDFWaterLilyT4"
SCRIPT = "scripts/waterlily_grad_ta1_2026_10_15.jl"
PHI_RAW = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
INPUT_DIR = "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
# every file the kernel imports or reads: the T4 Julia project (package pins), the bridge, QuickTie, the CFDSDFWaterLily source tree (included by the bridge), the inputs
PIN_PATHS = (f"{PROJECT}/Project.toml", f"{PROJECT}/Manifest.toml", SCRIPT, "scripts/quick_tie.jl", "julia/CFDSDFWaterLily/src", PHI_RAW,
             *(f"{INPUT_DIR}/{d}.dir_f4_fortran.raw" for d in DIRECTIONS))


def pins() -> dict:
    return {p: sha(ROOT / p) for p in sorted(PIN_PATHS)}


def tree_id(source_commit: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", f"{source_commit}^{{tree}}"], text=True).strip()


def render(source_commit: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", source_commit):
        raise ValueError("source commit must be a full lowercase SHA")
    text = TEMPLATE.read_text()
    for key, value in {"PIN_SOURCE_COMMIT": source_commit, "PIN_SOURCE_TREE_ID": tree_id(source_commit), "PIN_KERNEL_ID": KERNEL_ID}.items():
        old = json.dumps(key)
        if text.count(old) != 1:
            raise ValueError(f"runner placeholder count differs: {key}")
        text = text.replace(old, json.dumps(value))
    if text.count("PINS = PIN_PINS") != 1:
        raise ValueError("runner pin placeholder count differs")
    text = text.replace("PINS = PIN_PINS", "PINS = " + repr(pins()))
    if "PIN_" in text:
        raise ValueError("unresolved runner placeholder")
    compile(text, "runner.py", "exec")
    namespace: dict = {}
    exec(compile(text.split("def sha256")[0], "runner.py", "exec"), namespace)  # constants only: the template's inputs must agree with the pins
    for name, digest in namespace["DIRECTION_INPUTS"]:
        if namespace["PINS"][f"{INPUT_DIR}/{name}.dir_f4_fortran.raw"] != digest:
            raise ValueError(f"template direction hash differs from the pinned file: {name}")
    if namespace["PINS"][PHI_RAW] != namespace["PHI_SHA256"] or namespace["SCRIPT"] != SCRIPT or namespace["PROJECT"] != PROJECT:
        raise ValueError("template constants differ from the builder")
    return text


def metadata() -> dict:
    return {"id": KERNEL_ID, "title": KERNEL_ID.split("/")[1], "code_file": "runner.py", "language": "python", "kernel_type": "script", "is_private": True,
            "enable_gpu": True, "enable_internet": True, "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-commit", required=True)
    args = p.parse_args()
    verify_source(args.source_commit, set(PIN_PATHS) | {str(TEMPLATE.relative_to(ROOT))})
    if KERNEL_DIR.exists():
        raise SystemExit(f"refusing to overwrite the rendered worker: {KERNEL_DIR}")
    KERNEL_DIR.mkdir(parents=True)
    (KERNEL_DIR / "runner.py").write_text(render(args.source_commit))
    (KERNEL_DIR / "kernel-metadata.json").write_text(json.dumps(metadata(), sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
