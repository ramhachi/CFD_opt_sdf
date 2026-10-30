#!/usr/bin/env python3
"""Render the T2-0b kernel (#57, REGISTERED; template infra/kaggle/kernel_t20b_cpu) for a pinned source commit. Fork of build_t20a_kernel.py:
fills PIN_SOURCE_COMMIT / PIN_MODE / PIN_PINS and refuses unless every pinned file (generator, adjoint module, coordinates, OpenFOAM locks) is
byte-identical in the commit. Modes and slugs: smoke (development smoke before the code freeze), wf (kernel W), lm (kernel L). Refuses to overwrite --out."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_t20a_kernel as A  # noqa: E402  (lock checks and commit verification reused unchanged)

ROOT = A.ROOT
TEMPLATE_DIR = ROOT / "infra/kaggle/kernel_t20b_cpu"
FILES = ("scripts/t20_case.py", "scripts/t20_foam.py", "scripts/t20b_adjoint.py", "data/t20/tyrrell026s_genua2009.dat")
MODES = {"smoke": "cfd-opt-sdf-t20b-smoke", "wf": "cfd-opt-sdf-t20b-wf", "lm": "cfd-opt-sdf-t20b-lm"}


def pins(template: str) -> dict:
    locks = A.lock_paths(template)
    if set(locks) != set(A.LOCK_SHA256) or any(A.sha(ROOT / rel) != A.LOCK_SHA256[name] for name, rel in locks.items()):
        raise ValueError("the OpenFOAM package locks differ from the registered ones")
    return {p: A.sha(ROOT / p) for p in sorted((*FILES, *locks.values()))}


def render(commit: str, mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    text = (TEMPLATE_DIR / "runner.py").read_text()
    p = pins(text)
    A.verify_source(commit, [*p, "infra/kaggle/kernel_t20b_cpu/runner.py"])
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
    ap.add_argument("--mode", choices=sorted(MODES), required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite: {a.out}")
    text = render(a.source_commit, a.mode)
    a.out.mkdir(parents=True)
    (a.out / "runner.py").write_text(text)
    meta = json.loads((TEMPLATE_DIR / "kernel-metadata.json").read_text())
    meta["id"], meta["title"] = f"{meta['id'].split('/')[0]}/{MODES[a.mode]}", MODES[a.mode]
    assert not meta["enable_gpu"] and meta["is_private"] and meta["enable_internet"]
    (a.out / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
