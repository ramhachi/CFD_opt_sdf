#!/usr/bin/env python3
"""Fill the LOWDIM-01 runner template (source commit, SHA pins) and write infra/kaggle/kernel_lowdim01_a/{runner.py,kernel-metadata.json}."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import step01_states as S  # noqa: E402

TEMPLATE = ROOT / "scripts/lowdim01_runner_template.py"
EVIDENCE = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
OWNER = "ramhachi888"
KERNEL = "a"
TIMEOUT_S = 3600
TITLE = "CFD Opt SDF Lowdim01 A"


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def sha(path: Path) -> str:
    path = Path(path)
    if path.is_dir():
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins() -> dict:
    inv = json.loads((EVIDENCE / "inventory.json").read_text())
    files = {"julia/CFDSDFWaterLilyT4/Project.toml": sha(ROOT / "julia/CFDSDFWaterLilyT4/Project.toml"), "julia/CFDSDFWaterLilyT4/Manifest.toml": sha(ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml"),
             "scripts/waterlily_xfid_candidate_c_job.jl": sha(ROOT / "scripts/waterlily_xfid_candidate_c_job.jl"), "scripts/step01_states.py": sha(ROOT / "scripts/step01_states.py"),
             "scripts/lowdim01_states.py": sha(ROOT / "scripts/lowdim01_states.py"), "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json": sha(EVIDENCE / "inventory.json"),
             inv["proposal"]["file"]: inv["proposal"]["sha256_fortran_raw"], "julia/CFDSDFWaterLily/src": sha(ROOT / "julia/CFDSDFWaterLily/src"),
             inv["baseline"]["path"]: inv["baseline"]["phi_fortran_sha256"]}
    assert sha(ROOT / inv["proposal"]["file"]) == inv["proposal"]["sha256_fortran_raw"] and sha(ROOT / inv["baseline"]["path"]) == inv["baseline"]["phi_fortran_sha256"]
    return files


def verify_pins_against_commit(source_commit: str) -> None:
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
    if dirty:
        raise RuntimeError("tracked files have uncommitted changes")
    for rel in pins():
        path = ROOT / rel
        names = sorted(str(p.relative_to(ROOT)) for p in path.rglob("*") if p.is_file()) if path.is_dir() else [rel]
        for name in names:
            blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{source_commit}:{name}"], capture_output=True)
            if blob.returncode != 0 or hashlib.sha256(blob.stdout).hexdigest() != sha(ROOT / name):
                raise RuntimeError(f"{name} in commit {source_commit} differs from the worktree (or is absent)")


def render(source_commit: str) -> str:
    p = pins()
    inv = json.loads((EVIDENCE / "inventory.json").read_text())
    text = TEMPLATE.read_text()
    subs = {'KERNEL = "PIN_KERNEL"': f'KERNEL = "{KERNEL}"', 'SOURCE_COMMIT = "PIN_SOURCE_COMMIT"': f'SOURCE_COMMIT = "{source_commit}"',
            '"PIN_T4_PROJECT_SHA"': f'"{p["julia/CFDSDFWaterLilyT4/Project.toml"]}"', '"PIN_T4_MANIFEST_SHA"': f'"{p["julia/CFDSDFWaterLilyT4/Manifest.toml"]}"',
            '"PIN_JOB_SHA"': f'"{p["scripts/waterlily_xfid_candidate_c_job.jl"]}"', '"PIN_STATES_SHA"': f'"{p["scripts/step01_states.py"]}"', '"PIN_LOWDIM_SHA"': f'"{p["scripts/lowdim01_states.py"]}"',
            '"PIN_PROPOSAL_SHA"': f'"{inv["proposal"]["sha256_fortran_raw"]}"',
            '"PIN_INVENTORY_SHA"': f'"{p["docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json"]}"', '"PIN_SRC_TREE_SHA"': f'"{p["julia/CFDSDFWaterLily/src"]}"',
            '"PIN_BASELINE_RAW_SHA"': f'"{inv["baseline"]["phi_fortran_sha256"]}"', '"PIN_FD08_BASELINE_CSV_SHA"': f'"{S.FD08_BASELINE_CSV_SHA256}"', 'int("PIN_KERNEL_TIMEOUT_S")': str(TIMEOUT_S)}
    for old, new in subs.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    assert "PIN_" not in text
    return text


def metadata() -> dict:
    return {"id": f"{OWNER}/{slugify(TITLE)}", "title": TITLE, "code_file": "runner.py", "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
            "enable_internet": True, "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    verify_pins_against_commit(args.source_commit)
    d = ROOT / "infra/kaggle/kernel_lowdim01_a"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runner.py").write_text(render(args.source_commit))
    (d / "kernel-metadata.json").write_text(json.dumps(metadata(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
