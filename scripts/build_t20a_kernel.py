#!/usr/bin/env python3
"""Render the T2-0a kernel (infra/kaggle/kernel_t20a_cpu) for a pinned source commit: fills PIN_SOURCE_COMMIT and PIN_PINS and refuses unless every
pinned file is byte-identical in the commit (as build_grid02_kernel.py does). Writes runner.py + kernel-metadata.json to --out; refuses to overwrite."""
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
LOCK_SHA256 = "b5e59f8a7da34820fc3c6bda93b3524204dcaf4fa6e4f7f11d6c46ddddb66746"            # lock that passed the XFID Round 5 environment reproduction


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pins(template: str) -> dict:
    lock = re.search(r'^LOCK = "([^"]+)"', template, re.M).group(1)
    if sha(ROOT / lock) != LOCK_SHA256:
        raise ValueError("the OpenFOAM package lock differs from the registered one")
    return {p: sha(ROOT / p) for p in sorted((*FILES, lock))}


def verify_source(commit: str, paths) -> None:
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("source commit must be a full lowercase SHA")
    for rel in sorted(paths):
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{rel}"], capture_output=True, check=True).stdout
        if hashlib.sha256(blob).hexdigest() != sha(ROOT / rel):
            raise ValueError(f"committed source differs: {rel}")


def render(commit: str) -> str:
    text = (TEMPLATE_DIR / "runner.py").read_text()
    p = pins(text)
    verify_source(commit, p)
    for old, new in (('SOURCE_COMMIT = "PIN_SOURCE_COMMIT"', f"SOURCE_COMMIT = {commit!r}"), ("PINS = PIN_PINS", f"PINS = {p!r}")):
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
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite: {a.out}")
    text = render(a.source_commit)
    a.out.mkdir(parents=True)
    (a.out / "runner.py").write_text(text)
    shutil.copy2(TEMPLATE_DIR / "kernel-metadata.json", a.out / "kernel-metadata.json")
    meta = json.loads((a.out / "kernel-metadata.json").read_text())
    assert meta["title"] == meta["id"].split("/")[1] and not meta["enable_gpu"] and meta["is_private"]


if __name__ == "__main__":
    main()
