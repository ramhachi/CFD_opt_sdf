#!/usr/bin/env python3
"""Render the T2-0a kernel (infra/kaggle/kernel_t20a_cpu) for a pinned source commit: fills PIN_SOURCE_COMMIT and PIN_PINS and refuses unless every
pinned file is byte-identical in the commit (as build_grid02_kernel.py does). Writes runner.py + kernel-metadata.json to --out; refuses to overwrite.
--mode mesh_only renders the checkMesh-only kernel (all registered meshes, no solver) under its own slug."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "infra/kaggle/kernel_t20a_cpu"
FILES = ("scripts/t20_case.py", "scripts/t20_foam.py", "data/t20/tyrrell026s_genua2009.dat")   # read on the kernel; the OpenFOAM lock is added below
MODES = {"full": "cfd-opt-sdf-t20a-cpu", "mesh_only": "cfd-opt-sdf-t20a-meshcheck"}   # kernel slug (= metadata title) per mode: generate + gmshToFoam + checkMesh for every registered mesh, no solver
LOCK_SHA256 = {"jammy": "b5e59f8a7da34820fc3c6bda93b3524204dcaf4fa6e4f7f11d6c46ddddb66746",   # XFID Round 5 environment reproduction
               "noble": "8bcf141db29d18800a55a70bca93175a37465ac18494e473efd32985317c7340"}   # XFID X2/X3 (Noble image)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pins(template: str) -> dict:
    locks = lock_paths(template)
    if set(locks) != set(LOCK_SHA256) or any(sha(ROOT / rel) != LOCK_SHA256[name] for name, rel in locks.items()):
        raise ValueError("the OpenFOAM package locks differ from the registered ones")
    return {p: sha(ROOT / p) for p in sorted((*FILES, *locks.values()))}


def lock_paths(template: str) -> dict:
    return dict(re.findall(r'"(\w+)": "(infra/kaggle/[^"]+openfoam_package_lock\.json)"', re.search(r'^LOCKS = \{.*\}', template, re.M).group(0)))


def verify_source(commit: str, paths) -> None:
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("source commit must be a full lowercase SHA")
    for rel in sorted(paths):
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{rel}"], capture_output=True, check=True).stdout
        if hashlib.sha256(blob).hexdigest() != sha(ROOT / rel):
            raise ValueError(f"committed source differs: {rel}")


def render(commit: str, mode: str = "full") -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    text = (TEMPLATE_DIR / "runner.py").read_text()
    p = pins(text)
    verify_source(commit, p)
    for old, new in (('SOURCE_COMMIT = "PIN_SOURCE_COMMIT"', f"SOURCE_COMMIT = {commit!r}"), ('MODE = "PIN_MODE"', f"MODE = {mode!r}"), ("PINS = PIN_PINS", f"PINS = {p!r}")):
        if text.count(old) != 1:
            raise ValueError(f"runner placeholder count differs: {old}")
        text = text.replace(old, new)
    if re.search(r'^\w+ = "?PIN_', text, re.M):
        raise ValueError("unresolved runner placeholder")
    compile(text, "runner.py", "exec")
    return text


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-commit", required=True)
    ap.add_argument("--mode", choices=sorted(MODES), default="full", help="mesh_only renders the checkMesh-only kernel (separate slug); use a separate --out")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite: {a.out}")
    text = render(a.source_commit, a.mode)
    a.out.mkdir(parents=True)
    (a.out / "runner.py").write_text(text)
    shutil.copy2(TEMPLATE_DIR / "kernel-metadata.json", a.out / "kernel-metadata.json")
    meta = json.loads((a.out / "kernel-metadata.json").read_text())
    meta["id"], meta["title"] = f"{meta['id'].split('/')[0]}/{MODES[a.mode]}", MODES[a.mode]
    (a.out / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    assert meta["title"] == meta["id"].split("/")[1] and not meta["enable_gpu"] and meta["is_private"]


if __name__ == "__main__":
    main()
