#!/usr/bin/env python3
"""Write the four registered FD-08 directions as <f4 Fortran-order raw files for the GPU Dual spike.

Each direction is regenerated from the canonical v17 state and checked against the registered C-order <f4 hash in the
formal criteria before anything is written. The baseline phi raw is already tracked in git (its SHA is pinned here).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.fd08_v2_campaign import generate_p1  # noqa: E402
from cfd_sdf.gradients.directional_fd import direction_sha256, generate_directions  # noqa: E402

CRITERIA = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
CRITERIA_SHA256 = "31b29cccc9d3fd6912a910b09694a8230f9ee0aa84e6a418161881ffbcf907be"
NPZ_SHA256 = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
BASELINE_PHI = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
BASELINE_PHI_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
OUT = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, default=DEFAULT_STATE)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    assert sha(CRITERIA.read_bytes()) == CRITERIA_SHA256, "formal criteria changed"
    assert sha(args.state.read_bytes()) == NPZ_SHA256, "canonical NPZ mismatch"
    assert sha((ROOT / BASELINE_PHI).read_bytes()) == BASELINE_PHI_SHA256, "baseline phi raw mismatch"
    registered = json.loads(CRITERIA.read_text())["direction_inventory"]["hashes"]
    state = SDFDesignState.load(args.state)
    directions = dict(generate_directions(state))
    directions["P1_upstream_lobe"], _ = generate_p1(state)
    if args.out.exists() and any(args.out.iterdir()):
        sys.exit(f"refusing to overwrite {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "grad_dual_gpu_spike_inputs", "baseline_phi": {"path": BASELINE_PHI, "sha256": BASELINE_PHI_SHA256},
                "formal_criteria_sha256": CRITERIA_SHA256, "directions": {}}
    for name, direction in directions.items():
        assert direction_sha256(direction) == registered[name], f"direction hash drift: {name}"
        assert float(np.abs(direction).max()) == 1.0
        raw = np.asarray(direction, "<f4").tobytes(order="F")
        path = args.out / f"{name}.dir_f4_fortran.raw"
        path.write_bytes(raw)
        manifest["directions"][name] = {"file": path.name, "sha256_fortran_raw": sha(raw), "registered_sha256_c_order": registered[name]}
    data = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (args.out / "inputs_manifest.json").write_bytes(data)
    (args.out / "inputs_manifest.json.sha256").write_text(sha(data) + "\n")
    print(json.dumps({k: v["sha256_fortran_raw"] for k, v in manifest["directions"].items()}, indent=1))


if __name__ == "__main__":
    main()
