#!/usr/bin/env python3
"""Fill the STEP-01 runner template (kernel key, source commit, SHA pins) and write infra/kaggle/kernel_step01_{a,b,c}/{runner.py,kernel-metadata.json}."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import step01_states as S  # noqa: E402

TEMPLATE = ROOT / "scripts/step01_runner_template.py"
EVIDENCE = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
OWNER = "ramhachi888"
TIMEOUT_S = {"a": 7200, "b": 7200, "c": 3600}
TITLES = {"a": "CFD Opt SDF Step01 A", "b": "CFD Opt SDF Step01 B", "c": "CFD Opt SDF Step01 C"}
FD08_BASELINE_CSV_SHA = S.FD08_BASELINE_CSV_SHA256


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def sha(path: Path) -> str:
    path = Path(path)
    if path.is_dir():
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins() -> tuple[dict, dict]:
    inv = json.loads((EVIDENCE / "inventory.json").read_text())
    files = {"julia/CFDSDFWaterLilyT4/Project.toml": sha(ROOT / "julia/CFDSDFWaterLilyT4/Project.toml"),
             "julia/CFDSDFWaterLilyT4/Manifest.toml": sha(ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml"),
             "scripts/waterlily_xfid_candidate_c_job.jl": sha(ROOT / "scripts/waterlily_xfid_candidate_c_job.jl"),
             "scripts/step01_states.py": sha(ROOT / "scripts/step01_states.py"),
             "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json": sha(EVIDENCE / "inventory.json"),
             "julia/CFDSDFWaterLily/src": sha(ROOT / "julia/CFDSDFWaterLily/src"),
             inv["baseline"]["path"]: inv["baseline"]["phi_fortran_sha256"]}
    assert sha(ROOT / inv["baseline"]["path"]) == inv["baseline"]["phi_fortran_sha256"]
    directions = {}
    for name, entry in inv["directions"].items():
        rel = f"docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/{entry['file']}"
        assert sha(ROOT / rel) == entry["sha256_fortran_raw"]
        directions[rel] = entry["sha256_fortran_raw"]
    for entry in inv["combined_directions"].values():
        assert sha(ROOT / entry["file"]) == entry["sha256_fortran_raw"]
        directions[entry["file"]] = entry["sha256_fortran_raw"]
    return files, directions


def verify_pins_against_commit(source_commit: str) -> None:
    """The pins are computed from the worktree; the kernel verifies them against the commit it fetches. Refuse to render unless both are the same bytes."""
    import subprocess
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
    if dirty:
        raise RuntimeError("tracked files have uncommitted changes")
    files, directions = pins()
    for rel, digest in {**files, **directions}.items():
        path = ROOT / rel
        names = sorted(str(p.relative_to(ROOT)) for p in path.rglob("*") if p.is_file()) if path.is_dir() else [rel]
        for name in names:
            blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{source_commit}:{name}"], capture_output=True)
            if blob.returncode != 0 or hashlib.sha256(blob.stdout).hexdigest() != sha(ROOT / name):
                raise RuntimeError(f"{name} in commit {source_commit} differs from the worktree (or is absent)")


def render(kernel: str, source_commit: str) -> str:
    files, directions = pins()
    text = TEMPLATE.read_text()
    subs = {'KERNEL = "PIN_KERNEL"': f'KERNEL = "{kernel}"', 'SOURCE_COMMIT = "PIN_SOURCE_COMMIT"': f'SOURCE_COMMIT = "{source_commit}"',
            '"PIN_T4_PROJECT_SHA"': f'"{files["julia/CFDSDFWaterLilyT4/Project.toml"]}"', '"PIN_T4_MANIFEST_SHA"': f'"{files["julia/CFDSDFWaterLilyT4/Manifest.toml"]}"',
            '"PIN_JOB_SHA"': f'"{files["scripts/waterlily_xfid_candidate_c_job.jl"]}"', '"PIN_STATES_SHA"': f'"{files["scripts/step01_states.py"]}"',
            '"PIN_INVENTORY_SHA"': f'"{files["docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json"]}"', '"PIN_SRC_TREE_SHA"': f'"{files["julia/CFDSDFWaterLily/src"]}"',
            '"PIN_BASELINE_RAW_SHA"': f'"{files[next(k for k in files if k.endswith("cal_baseline_01.phi_f4_fortran.raw"))]}"',
            'DIRECTION_FILES = "PIN_DIRECTION_FILES"': "DIRECTION_FILES = " + json.dumps(directions, indent=4, sort_keys=True),
            '"PIN_FD08_BASELINE_CSV_SHA"': f'"{FD08_BASELINE_CSV_SHA}"', 'int("PIN_KERNEL_TIMEOUT_S")': str(TIMEOUT_S[kernel])}
    for old, new in subs.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    assert "PIN_" not in text
    return text


def metadata(kernel: str) -> dict:
    slug = slugify(TITLES[kernel])
    return {"id": f"{OWNER}/{slug}", "title": TITLES[kernel], "code_file": "runner.py", "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
            "enable_internet": True, "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-commit", required=True)
    args = p.parse_args()
    verify_pins_against_commit(args.source_commit)
    for kernel in S.KERNELS:
        d = ROOT / f"infra/kaggle/kernel_step01_{kernel}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "runner.py").write_text(render(kernel, args.source_commit))
        (d / "kernel-metadata.json").write_text(json.dumps(metadata(kernel), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
