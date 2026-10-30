#!/usr/bin/env python3
"""GEOM-02 (#29) post-run descriptive diagnostic of the nodes that fail ``near_zero_gradient_band``.  Changes no verdict.

Takes the failing nodes of the registered rule (module function ``_zero_level_gradient``, floor from the registered profile) on the two
canonical states and classifies each, precedence ``tie_plateau`` > ``kink`` > ``other``:
  tie_plateau  node is exact zero or has an exact-zero 6-neighbour;
  kink         along some axis the forward and backward one-sided slopes have opposite signs and both magnitudes > KINK_SLOPE (a ridge of the
               distance field: locally one node thick in that axis, distance accurate but the normal undefined);
  other.
Writes docs/evidence/geom02_v17_gates_2026_10_14/gradient_floor_diagnostic.json (+ .sha256) once and refuses to overwrite; ``--check`` re-derives.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import geom02_canonical as canon  # noqa: E402
import register_geom02_profile as reg  # noqa: E402
from cfd_sdf.design.geometry_gates_v2 import _zero_level_gradient  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402

OUTPUT = reg.OUT / "gradient_floor_diagnostic.json"
KINK_SLOPE = 0.3
QUANTILES = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)


def classify(state: SDFDesignState, floor: float) -> dict:
    z = _zero_level_gradient(state)
    if z is None or "norm" not in z:
        return {"failing_nodes": 0}
    bad = z["nodes"] & (z["norm"] < floor)
    phi, h = z["phi"], float(state.spacing_m)
    zero = phi == 0.0
    tie = bad & (zero | ndimage.binary_dilation(zero))
    fwd, bwd = [], []
    for axis in range(3):
        d = np.zeros_like(phi)
        d[tuple(slice(None, -1) if a == axis else slice(None) for a in range(3))] = np.diff(phi, axis=axis) / h
        fwd.append(d)  # slope towards +axis (last layer unused: failing nodes are interior)
        bwd.append(np.roll(d, 1, axis=axis))  # slope from -axis
    kink_axis = [(f * b < 0) & (np.abs(f) > KINK_SLOPE) & (np.abs(b) > KINK_SLOPE) for f, b in zip(fwd, bwd)]
    kink_any = np.any(kink_axis, axis=0)
    kink = bad & ~tie & kink_any
    slope = np.max([np.maximum(np.abs(f), np.abs(b)) for f, b in zip(fwd, bwd)], axis=0)[bad]
    return {
        "failing_nodes": int(bad.sum()), "interior_sign_change_nodes": z["sign_change_nodes_interior"],
        "class_counts": {"tie_plateau": int(tie.sum()), "kink": int(kink.sum()), "other": int((bad & ~tie & ~kink_any).sum())},
        "solid_fluid": {"solid": int((bad & (phi < 0)).sum()), "fluid_or_zero": int((bad & (phi >= 0)).sum())},
        "kink_nodes_by_axis": {"xyz"[a]: int((bad & ~tie & kink_axis[a]).sum()) for a in range(3)},
        "max_one_sided_slope_quantiles": {str(q): float(np.quantile(slope, q)) for q in QUANTILES} if slope.size else {},
        "kink_nodes_including_tie_plateau": int((bad & kink_any).sum()),
    }


def derive() -> dict:
    profile = json.loads(reg.PROFILE.read_text())
    require = canon.require
    require(reg.sha_file(reg.PROFILE) == canon.PROFILE_SHA256, "registered profile hash")
    require(reg.sha_file(canon.INPUTS / "v17_baseline.npz") == canon.BASELINE_NPZ_SHA, "v17 baseline npz hash")
    require(reg.sha_file(canon.INPUTS / "lowdim03_parent.npz") == canon.PARENT_NPZ_SHA, "LOWDIM-03 parent npz hash")
    floor = profile["zero_level_gradient_floor"]
    return {
        "kind": "geom02_gradient_floor_diagnostic", "evidence_class": "contract_and_capability", "verdict_effect": "none (descriptive, post-run)",
        "inputs": {"v17_baseline_npz_sha256": canon.BASELINE_NPZ_SHA, "lowdim03_parent_npz_sha256": canon.PARENT_NPZ_SHA, "profile_sha256": canon.PROFILE_SHA256},
        "rule": {"zero_level_gradient_floor": floor, "kink_one_sided_slope_min": KINK_SLOPE, "class_precedence": ["tie_plateau", "kink", "other"]},
        "states": {name: classify(SDFDesignState.load(canon.INPUTS / f"{npz}.npz"), floor) for name, npz in (("baseline", "v17_baseline"), ("lowdim03_parent", "lowdim03_parent"))},
        "claims_not_supported": reg.NOT_SUPPORTED,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    if ap.parse_args().check:
        sidecar = OUTPUT.with_name(OUTPUT.name + ".sha256").read_text().split()[0]
        canon.require(sidecar == reg.sha_file(OUTPUT), "diagnostic sidecar")
        canon.require(json.loads(reg.dump(derive())) == json.loads(OUTPUT.read_text()), "diagnostic does not re-derive")
        print("check ok", sidecar)
        return
    diagnostic = derive()
    print(reg.write_once(OUTPUT, diagnostic))
    for name, s in diagnostic["states"].items():
        print(name, s["failing_nodes"], s.get("class_counts"))


if __name__ == "__main__":
    main()
