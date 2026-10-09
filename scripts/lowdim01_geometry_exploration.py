#!/usr/bin/env python3
"""LOWDIM-01 (#48) solver-free exploration of the 44 STEP-01 perturbed states: smoothed/sharp volume change, the |grad phi| - 1 narrow-band deviation, component counts.

Exploratory and unregistered: it informs the pre-registered volume and SDF-quality gates of LOWDIM-01 (no CFD, no response, no flag).  Run once; refuses to overwrite.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import step01_states as S  # noqa: E402
from cfd_sdf.design.geometry_gates import _gradient_diagnostics, cell_occupancy  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import sharp_volume_m3, smoothed_volume_and_gradient  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
STEP01 = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
CANONICAL = Path("/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v17/sdf_design_state.npz")


def measures(state: SDFDesignState, baseline: dict | None) -> dict:
    occ = cell_occupancy(state)
    cells, n_cells = ndimage.label(occ)                      # face connectivity of solid cells
    nodes, n_nodes = ndimage.label(state.phi < 0)
    result = smoothed_volume_and_gradient(state)
    v_eps = float(result.smoothed_volume_m3)
    out = {"sharp_volume_m3": float(sharp_volume_m3(state)), "smoothed_volume_m3": v_eps, "cell_components": int(n_cells), "node_components": int(n_nodes), "eikonal": _gradient_diagnostics(state)}
    if baseline:
        out["relative_sharp_volume_change"] = out["sharp_volume_m3"] / baseline["sharp_volume_m3"] - 1.0
        if v_eps is not None:
            out["relative_smoothed_volume_change"] = v_eps / baseline["smoothed_volume_m3"] - 1.0
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--canonical", type=Path, default=CANONICAL)
    args = p.parse_args()
    out = E / "geometry_exploration_step01_states.json"
    if out.exists():
        sys.exit("refusing to overwrite")
    inv = json.loads((STEP01 / "inventory.json").read_text())
    parent = SDFDesignState.load(args.canonical)
    phi = S.read_f4(ROOT / inv["baseline"]["path"])
    dirs = {n: S.read_f4(ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs" / e["file"]) for n, e in inv["directions"].items()}
    combos = {k: S.read_f4(ROOT / c["file"]) for k, c in inv["combined_directions"].items()}
    base = measures(parent, None)
    rows = {S.BASELINE_NAME: base}
    for row in inv["states"]:
        if row["kind"] == "baseline":
            continue
        d = dirs[row["directions"][0]] if row["kind"] == "single" else combos["+".join(row["directions"])]
        child, audit = construct_state(parent, d, row["step_mm"], row["sign"])
        rows[row["name"]] = {**measures(child, base), "zero_level_margin_m": audit["zero_level_margin_m"], "step_mm": row["step_mm"], "sign": row["sign"], "directions": row["directions"]}
    out.write_text(json.dumps({"kind": "lowdim01_step01_geometry_exploration", "evidence_class": "solver_free_exploratory_unregistered", "baseline": base, "states": rows}, indent=2, sort_keys=True) + "\n")
    print("written", len(rows))


if __name__ == "__main__":
    main()
