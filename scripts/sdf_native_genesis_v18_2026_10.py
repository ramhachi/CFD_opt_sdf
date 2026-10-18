#!/usr/bin/env python3
"""SDF genesis v18 (#60, B1 = v18 analytic plate, 2026-10-19): the analytic rectangle ⊕ ball plate of scripts/v18_plate.py on the v17 lattice.
EXPLORATORY_COMMITTED (PROC-01).  Writes docs/evidence/v18_genesis_2026_10_19/{v18_parent.npz, v18_parent.phi_f4_fortran.raw, genesis.json} once
(refuses to overwrite different bytes); ``--check`` rebuilds and compares the bytes and the json (runtime fields excluded).

    python scripts/sdf_native_genesis_v18_2026_10.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import v18_plate as V  # noqa: E402

OUT = ROOT / "docs/evidence/v18_genesis_2026_10_19"
RUNTIME = ("environment",)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def min_zero_z(s, phi) -> float:
    """Lowest zero-level z over all columns (linear interpolation below the lowest solid node of each column): the ride height is this + 0.9 m."""
    neg = phi < 0
    k = np.argmax(neg, axis=2)
    i, j = np.nonzero(neg.any(axis=2) & (k > 0))
    k = k[i, j]
    lo, hi = phi[i, j, k - 1].astype(np.float64), phi[i, j, k].astype(np.float64)
    z = s.origin_m[2] + s.spacing_m * (k - 1 + lo / (lo - hi))
    return float(z.min())


def build() -> tuple[dict, dict[str, bytes]]:
    import build_lowdim01_inputs as lowdim
    import build_lowdim04a_inputs as b4a
    import mode01_prescreen as P
    from cfd_sdf.design.sdf_state import SDFDesignState
    from cfd_sdf.design.volume_semantics import _corner_mean
    from cfd_sdf.fd08_v2_campaign import state_identity

    if sha(V.V17_BASELINE) != V.V17_BASELINE_NPZ_SHA:
        raise SystemExit("v17 baseline npz differs from its pinned hash")
    s, p = V.build_parent()
    base = SDFDesignState.load(V.V17_BASELINE)
    with tempfile.TemporaryDirectory() as tmp:
        s.save(Path(tmp) / "v18_parent.npz")
        npz = (Path(tmp) / "v18_parent.npz").read_bytes()
    raw = np.asfortranarray(s.phi).tobytes(order="F")
    ident = state_identity(s)
    P._init("opt01")  # the registered gate stack: GEOM-02 v2 profile (cap 8272), policy, v17 baseline volume base
    P.G.update(parent=s, parent_geom=lowdim.geometry(s))
    gates = P.evaluate(s)
    g, gb = lowdim.geometry(s), lowdim.geometry(base)
    X, Y, Z = V.axes(s)
    solid = s.phi < 0
    tied = int((np.abs(s.phi) < 1e-3).sum())
    evidence = {
        "kind": "sdf_native_genesis_v18", "genesis_id": "sdf_native_genesis_v18_2026_10", "issue": "#60", "decision": "B1 = v18 analytic plate (user, 2026-10-19, #60 comment)",
        "evidence_tier": "EXPLORATORY_COMMITTED", "evidence_class": "contract_and_capability (geometry only)", "plan": "docs/v18_mode01_plan_2026_10_19.md", "solver_started": False,
        "shape": "stadium section (thickness t, round edges) extruded over |y| <= y_tip with flat tips; exact extrusion SDF (scripts/v18_plate.py)",
        "parameters": p, "alpha_deg": float(np.degrees(p["alpha"])), "chord_m": p["L"] + p["t"], "span_tip_to_tip_m": 2 * p["y_tip"],
        "rules": {"bounding_box_m": V.BBOX, "y_tip": "0.45 - h/2 (flat tips on the cell-centre plane)", "thickness": "bisection: smoothed volume = v17 baseline smoothed volume, rounded to 0.1 mm",
                  "masks_policies": "copied from the v17 baseline (identical to the OPT-01 v1 parent masks)", "generation": 0, "source_sha256": "SHA-256 of the sorted-key JSON of the parameters"},
        "lattice": {"origin_m": list(s.origin_m), "spacing_m": s.spacing_m, "shape": list(s.shape)},
        "lineage": {"v17_baseline_npz": {"path": str(V.V17_BASELINE.relative_to(ROOT)), "sha256": V.V17_BASELINE_NPZ_SHA}},
        "state": {"state_sha256": ident["state_sha256"], "npz_sha256": hashlib.sha256(npz).hexdigest(), "phi_fortran_order_sha256": ident["phi_fortran_order_sha256"],
                  "phi_c_order_sha256": ident["phi_c_order_sha256"], "zero_level_margin_m": ident["margin_m"], "source_sha256": s.source_sha256},
        "measurements": {
            "n_phi": P.count(s, s.phi), "n_max_p22_v2": P.N_MAX, "p22_slack": P.N_MAX - P.count(s, s.phi), "v17_baseline_n_phi": P.count(base, base.phi),
            "smoothed_volume_m3": g["smoothed_volume_m3"], "v17_smoothed_volume_m3": gb["smoothed_volume_m3"], "smoothed_volume_vs_v17": g["smoothed_volume_m3"] / gb["smoothed_volume_m3"] - 1,
            "sharp_volume_m3": g["sharp_volume_m3"], "continuum_volume_m3": V.volume(p["L"], p["t"]),
            "min_zero_level_z_m": min_zero_z(s, s.phi), "ride_height_above_ground_m": min_zero_z(s, s.phi) + 0.9,
            "solid_node_extent_m": {a: [float(A[solid].min()), float(A[solid].max())] for a, A in (("x", X), ("y", Y), ("z", Z))},
            "nodes_abs_phi_below_1e-3": tied, "crossing_slope_fail_nodes": P.crossing_slope_failures(s.phi),
            "hard_count_invariance": b4a.invariance(s.phi, s.phi),
            "planform_area_m2": (p["L"] + p["t"]) * 2 * p["y_tip"], "frontal_area_x_m2": 0.5 * 2 * p["y_tip"], "centroid_m": [p["xc"], 0.0, p["zc"]],
            "cell_centre_ties_exact_zero": int((_corner_mean(s.phi) == 0).sum()),
            "end_layers_outside_mask": {"j14_j50_min_phi_m": float(s.phi[:, [14, 50], :].min()), "solid_outside_design_mask": int((solid & ~s.design_mask).sum())},
        },
        "gates": gates,
        "changes_vs_v17": "docs/v18_mode01_plan_2026_10_19.md §3.4",
        "flags": {"shape_update_allowed": False, "sdf_gradient_qualified": False, "topology_birth_qualified": False},
        "claims_not_supported": ["no solver ran; no force, slope or sigma_d", "v17 results (GRID-02, XFID, FD-08, OPT-01) do not transfer to v18", "not a registered parent: M2 (#61) pins it"],
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(), "numpy": np.__version__},
    }
    return evidence, {"v18_parent.npz": npz, "v18_parent.phi_f4_fortran.raw": raw}


def dump(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, default=float) + "\n").encode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    evidence, files = build()
    files["genesis.json"] = dump(evidence)
    if args.check:
        old = json.loads((OUT / "genesis.json").read_text())
        same = {k: v for k, v in old.items() if k not in RUNTIME} == json.loads(dump({k: v for k, v in evidence.items() if k not in RUNTIME}))
        bad = [n for n, b in files.items() if n != "genesis.json" and (OUT / n).read_bytes() != b] + ([] if same else ["genesis.json"])
        print("CHECK", "PASS" if not bad else f"FAIL {bad}")
        sys.exit(1 if bad else 0)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        path = OUT / name
        if path.exists() and path.read_bytes() != payload:
            raise SystemExit(f"refusing to overwrite {path.relative_to(ROOT)}")
        path.write_bytes(payload)
    m = evidence["measurements"]
    print(json.dumps({"state": evidence["state"], "n_phi": m["n_phi"], "volume_vs_v17": m["smoothed_volume_vs_v17"], "all_pass": evidence["gates"]["all_pass"],
                      "failed": evidence["gates"]["failed_geom02"]}, indent=1))


if __name__ == "__main__":
    main()
