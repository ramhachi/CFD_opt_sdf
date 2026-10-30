#!/usr/bin/env python3
"""Render the T2-0d kernel (#57, registration docs/t20d_registration_2026_10_21.md; template infra/kaggle/kernel_t20d_cpu) for a pinned source commit.
Fork of build_t20c_kernel.py: fills PIN_SOURCE_COMMIT / PIN_MODE / PIN_PINS / PIN_ONLY and refuses unless every pinned file (generators, morph module, stage
module, coordinates, OpenFOAM locks) is byte-identical in the commit. `--only` (a resubmission, registration section 8) takes the geometry ids that have a lost
run and renders the closure over their sets (a geometry with all its stage-2 runs; a morph scan with its base). Refuses to overwrite --out."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_t20a_kernel as A  # noqa: E402  (lock checks and commit verification reused unchanged)

ROOT = A.ROOT
TEMPLATE_DIR = ROOT / "infra/kaggle/kernel_t20d_cpu"
FILES = ("scripts/t20_case.py", "scripts/t20_foam.py", "scripts/t20c_case.py", "scripts/t20d_case.py", "data/t20/tyrrell026s_genua2009.dat")
MODES = {m: f"cfd-opt-sdf-t20d-{m}" for m in ("smoke", "xp1", "xp2", "xo1", "xo2", "f1", "f2")}


def pins(template: str) -> dict:
    locks = A.lock_paths(template)
    if set(locks) != set(A.LOCK_SHA256) or any(A.sha(ROOT / rel) != A.LOCK_SHA256[name] for name, rel in locks.items()):
        raise ValueError("the OpenFOAM package locks differ from the registered ones")
    return {p: A.sha(ROOT / p) for p in sorted((*FILES, *locks.values()))}


def registered() -> dict:
    """{mode: [(geometry tuple, stage-2 kinds)]}: the runner template's registered lists (its constants block, executed without the rest of the runner)."""
    ns = {}
    exec(compile((TEMPLATE_DIR / "runner.py").read_text().replace("PIN_PINS", "{}").replace("PIN_ONLY", "None").split("\ndef require(")[0], "runner", "exec"), ns)
    return ns["GEOMETRIES"]


def set_key(c) -> object:
    """A set (registration section 8): a remeshed geometry alone; a base with the morphs of that base, keyed (mesh, h, variant)."""
    return (c[2], c[1], c[5]) if c[0] in ("morph", "base") else _case_id(*c)


def set_closure(mode: str, ids) -> list[str]:
    """The geometry ids of every set that contains one of `ids`."""
    geoms = [c for c, _ in registered()[mode]]
    key = set_key
    unknown = set(ids) - {_case_id(*c) for c in geoms}
    if unknown:
        raise ValueError(f"not geometries of {mode}: {sorted(unknown)}")
    keys = {key(c) for c in geoms if _case_id(*c) in set(ids)}
    return sorted(_case_id(*c) for c in geoms if key(c) in keys)


def _case_id(method, h, mesh, mode, amp, variant="") -> str:   # the runner's case_id (kept identical; a test compares them)
    a = "0" if amp == 0 else format(amp, "+g")
    tail = f"da{a}" if mode == "incidence" else f"{mode}{a}mm"
    if method in ("remesh", "base"):
        return f"sa-wf_h{h}_{mesh}_{tail}"
    return f"sa-wf_h{h}_{mesh}_morph{ {'': '', 'B2': 'B2'}[variant]}-{tail}"


def render(commit: str, mode: str, only=None) -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    text = (TEMPLATE_DIR / "runner.py").read_text()
    p = pins(text)
    A.verify_source(commit, [*p, "infra/kaggle/kernel_t20d_cpu/runner.py"])
    only = set_closure(mode, only) if only else None
    for old, new in (('SOURCE_COMMIT = "PIN_SOURCE_COMMIT"', f"SOURCE_COMMIT = {commit!r}"), ('MODE = "PIN_MODE"', f"MODE = {mode!r}"), ("PINS = PIN_PINS", f"PINS = {p!r}"),
                     ("ONLY = PIN_ONLY", f"ONLY = {only!r}")):
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
    ap.add_argument("--only", nargs="+", help="resubmission: geometry ids with a lost run (the closure over their sets is rendered)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite: {a.out}")
    text = render(a.source_commit, a.mode, a.only)
    a.out.mkdir(parents=True)
    (a.out / "runner.py").write_text(text)
    meta = json.loads((TEMPLATE_DIR / "kernel-metadata.json").read_text())
    meta["id"], meta["title"] = f"{meta['id'].split('/')[0]}/{MODES[a.mode]}", MODES[a.mode]
    assert not meta["enable_gpu"] and meta["is_private"] and meta["enable_internet"]
    (a.out / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
