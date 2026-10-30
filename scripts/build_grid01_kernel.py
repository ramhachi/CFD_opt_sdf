#!/usr/bin/env python3
"""Render the pinned GRID-01 Kaggle kernel after review and source commit."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf import grid01_contract as C

TEMPLATE = ROOT / "scripts/grid01_runner_template.py"
EVIDENCE = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"
OWNER = "ramhachi888"
KERNEL = "a"
KERNEL_SLUG = "cfd-opt-sdf-grid01-a"
KERNEL_ID = f"{OWNER}/{KERNEL_SLUG}"
TIMEOUT_S = C.KERNEL_TIMEOUT_S
TITLE = KERNEL_SLUG
PROJECT = "julia/CFDSDFWaterLilyT4"
JOB = "scripts/waterlily_lowdim02_flow32_job.jl"
STATES_MODULE = "scripts/step01_states.py"
GPU_POLICY_MODULE = "scripts/grid01_gpu.py"
INVENTORY = "docs/evidence/grid01_cross_grid_secant_2026_10_09/inventory.json"
BASELINE_FORCE_CSV = "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv"
BASELINE_RAW = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
SOURCE_TREE = "julia/CFDSDFWaterLily/src"
DIRECTION_PIN_NAMES = {
    "D0_interface_offset": "PIN_D0_DIRECTION_SHA",
    "D1_filtered_seed11": "PIN_D1_DIRECTION_SHA",
    "D2_filtered_seed2026": "PIN_D2_DIRECTION_SHA",
    "P1_upstream_lobe": "PIN_P1_DIRECTION_SHA",
}


def sha(path: Path) -> str:
    path = Path(path)
    if path.is_dir():
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins() -> dict[str, str]:
    inventory = json.loads((EVIDENCE / "inventory.json").read_text())
    files = {
        f"{PROJECT}/Project.toml": sha(ROOT / f"{PROJECT}/Project.toml"),
        f"{PROJECT}/Manifest.toml": sha(ROOT / f"{PROJECT}/Manifest.toml"),
        JOB: sha(ROOT / JOB),
        STATES_MODULE: sha(ROOT / STATES_MODULE),
        GPU_POLICY_MODULE: sha(ROOT / GPU_POLICY_MODULE),
        INVENTORY: sha(ROOT / INVENTORY),
        BASELINE_RAW: sha(ROOT / BASELINE_RAW),
        BASELINE_FORCE_CSV: sha(ROOT / BASELINE_FORCE_CSV),
        SOURCE_TREE: sha(ROOT / SOURCE_TREE),
    }
    for name, token in DIRECTION_PIN_NAMES.items():
        ref = inventory["directions"][name]
        path = ref["path"]
        actual = sha(ROOT / path)
        if actual != ref["sha256_fortran_raw"]:
            raise ValueError(f"direction differs from GRID-01 inventory: {name}")
        files[path] = actual
    if files[BASELINE_RAW] != inventory["baseline"]["phi_fortran_sha256"]:
        raise ValueError("baseline phi differs from the GRID-01 inventory")
    if files[BASELINE_FORCE_CSV] != inventory["flow32_baseline_reference"]["forces_csv_sha256"]:
        raise ValueError("W4 flow_32 baseline differs from the GRID-01 inventory")
    return files


def _tracked_paths(source_commit: str, rel_dir: str) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", source_commit, "--", rel_dir],
        check=True, capture_output=True, text=True,
    )
    return {line for line in result.stdout.splitlines() if line}


def verify_pins_against_commit(source_commit: str) -> None:
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
    if dirty:
        raise RuntimeError("tracked files have uncommitted changes; render only from the committed reviewed source")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", source_commit, "HEAD"]).returncode:
        raise RuntimeError("the source commit is not an ancestor of HEAD")
    import analyze_grid01 as analyzer

    source_hashes = {
        name: analyzer.frozen_path_sha(name, ROOT / relpath, source_commit, root=ROOT)
        for name, relpath in analyzer.FILE_PATHS.items()
        if name not in analyzer.SOURCE_COMMIT_EXCEPTIONS
    }
    source_failures = analyzer._source_commit_failures(source_commit, source_hashes, root=ROOT)
    if source_failures:
        raise RuntimeError("source commit does not contain the reviewed source closure: " + "; ".join(source_failures))
    expected = pins()
    for rel, digest in expected.items():
        path = ROOT / rel
        if path.is_dir():
            names = _tracked_paths(source_commit, rel)
            present = {str(p.relative_to(ROOT)) for p in path.rglob("*") if p.is_file()}
            if names != present:
                raise RuntimeError(f"tracked contents under {rel} differ from the reviewed source tree")
        else:
            names = {rel}
        for name in sorted(names):
            blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{source_commit}:{name}"], capture_output=True)
            if blob.returncode != 0 or hashlib.sha256(blob.stdout).hexdigest() != sha(ROOT / name):
                raise RuntimeError(f"{name} in {source_commit} differs from the current worktree")
        if path.is_dir() and sha(path) != digest:
            raise RuntimeError(f"tree hash changed while validating {rel}")


def render(source_commit: str) -> str:
    p = pins()
    inv = json.loads((EVIDENCE / "inventory.json").read_text())
    substitutions = {
        'KERNEL = "PIN_KERNEL"': f'KERNEL = "{KERNEL}"',
        'KERNEL_ID = "PIN_KERNEL_ID"': f'KERNEL_ID = "{KERNEL_ID}"',
        'SOURCE_COMMIT = "PIN_SOURCE_COMMIT"': f'SOURCE_COMMIT = "{source_commit}"',
        '"PIN_T4_PROJECT_SHA"': f'"{p[f"{PROJECT}/Project.toml"]}"',
        '"PIN_T4_MANIFEST_SHA"': f'"{p[f"{PROJECT}/Manifest.toml"]}"',
        '"PIN_JOB_SHA"': f'"{p[JOB]}"',
        '"PIN_STATES_SHA"': f'"{p[STATES_MODULE]}"',
        '"PIN_GPU_POLICY_SHA"': f'"{p[GPU_POLICY_MODULE]}"',
        '"PIN_INVENTORY_SHA"': f'"{p[INVENTORY]}"',
        '"PIN_BASELINE_RAW_SHA"': f'"{p[BASELINE_RAW]}"',
        '"PIN_FLOW32_BASELINE_CSV_SHA"': f'"{p[BASELINE_FORCE_CSV]}"',
        '"PIN_SRC_TREE_SHA"': f'"{p[SOURCE_TREE]}"',
        '"PIN_D0_DIRECTION_SHA"': f'"{p[inv["directions"]["D0_interface_offset"]["path"]]}"',
        '"PIN_D1_DIRECTION_SHA"': f'"{p[inv["directions"]["D1_filtered_seed11"]["path"]]}"',
        '"PIN_D2_DIRECTION_SHA"': f'"{p[inv["directions"]["D2_filtered_seed2026"]["path"]]}"',
        '"PIN_P1_DIRECTION_SHA"': f'"{p[inv["directions"]["P1_upstream_lobe"]["path"]]}"',
        'int("PIN_KERNEL_TIMEOUT_S")': str(TIMEOUT_S),
        'int("PIN_PER_STATE_TIMEOUT_S")': str(C.PER_STATE_TIMEOUT_S),
        'int("PIN_SOLVER_WALL_TIME_CAP_S")': str(C.SOLVER_WALL_TIME_CAP_S),
        'int("PIN_GPU_PROBE_TIMEOUT_S")': str(C.GPU_PROBE_TIMEOUT_S),
    }
    text = TEMPLATE.read_text()
    for old, new in substitutions.items():
        if text.count(old) != 1:
            raise ValueError(f"expected exactly one runner placeholder {old}")
        text = text.replace(old, new)
    if "PIN_" in text:
        raise ValueError("an unresolved runner pin remains")
    pin_node = next(node.value for node in ast.parse(text).body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "PINS" for target in node.targets))
    constants = {"PROJECT": PROJECT, "JOB": JOB, "STATES_MODULE": STATES_MODULE,
                 "INVENTORY": INVENTORY, "BASELINE_RAW": BASELINE_RAW,
                 "BASELINE_FORCE_CSV": BASELINE_FORCE_CSV,
                 "DIRECTIONS": {name: inv["directions"][name]["path"] for name in DIRECTION_PIN_NAMES}}
    rendered_pins = eval(compile(ast.Expression(pin_node), str(TEMPLATE), "eval"), {"__builtins__": {}}, constants)
    if rendered_pins != p:
        raise ValueError("rendered runner PINS differ from the complete registered pin set")
    return text


def metadata() -> dict:
    return {
        "id": KERNEL_ID,
        "title": TITLE,
        "code_file": "runner.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise SystemExit("--source-commit must be a full lowercase Git SHA-1")
    verify_pins_against_commit(args.source_commit)
    target = ROOT / "infra/kaggle/kernel_grid01_a"
    if target.exists():
        raise SystemExit(f"refusing to overwrite rendered kernel files in {target}")
    target.mkdir(parents=True)
    (target / "runner.py").write_text(render(args.source_commit))
    (target / "kernel-metadata.json").write_text(json.dumps(metadata(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
