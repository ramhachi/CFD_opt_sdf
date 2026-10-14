#!/usr/bin/env python3
"""GRAD-TA1 analysis amendment 1 (post hoc, disclosed): the frozen analyzer (scripts/analyze_grad_ta1.py, unchanged) with ONE changed identity check.

The frozen check `index["tau"] != float(1e-5)` compares the kernel's Float32 tau recorded as its Float64 value (9.999999747378752e-06 = Float64(Float32(1f-5)))
with the Float64 literal 1e-5, so it can never hold for a Float32 tau.  Here that one check compares in Float32.  Every other check, gate, verdict rule and the BLOCKED
path are the frozen analyzer's own functions; the only addition is an `amendment` label key in the report so it cannot be mistaken for the official result.

    python scripts/analyze_grad_ta1_amendment1.py <kernel_output_dir> --check
    python scripts/analyze_grad_ta1_amendment1.py <kernel_output_dir> --write OUT.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_grad_ta1 as A  # noqa: E402

TAU_PROBLEM = "run is not QuickTie(1f-5) with Dual width 1"   # the frozen message, verbatim
LABEL = "amendment1: tau compared in Float32; the official registered result is the frozen analyzer's (GRAD_TA1_INCOMPLETE)"
_frozen_problems, _frozen_analyze = A.artifact_problems, A.analyze_output


def tau_ok(index: dict) -> bool:
    return bool(np.float32(index.get("tau")) == np.float32(A.TAU) and index.get("dual_width") == 1)


def artifact_problems(out_dir: Path, freeze: dict) -> list[str]:
    problems = _frozen_problems(out_dir, freeze)
    if TAU_PROBLEM in problems and tau_ok(json.loads((Path(out_dir) / "g2_run_index.json").read_text())):
        problems.remove(TAU_PROBLEM)
    return problems


def analyze_output(*args, **kwargs) -> dict:
    return {**_frozen_analyze(*args, **kwargs), "amendment": LABEL}


def load_freeze(path: Path) -> dict:
    """The frozen load_freeze, except that the analyzer bytes it pins are the frozen analyzer's (this file is not in the freeze)."""
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != A.sha256(path):
        sys.exit("the freeze does not match its SHA sidecar")
    freeze = json.loads(path.read_text())
    if freeze["file_hashes"].get(A.ANALYZER_FREEZE_KEY) != A.sha256(A.__file__):
        sys.exit("the frozen analyzer differs from the frozen bytes")
    return freeze


A.artifact_problems, A.analyze_output, A.load_freeze = artifact_problems, analyze_output, load_freeze

if __name__ == "__main__":
    A.main()
