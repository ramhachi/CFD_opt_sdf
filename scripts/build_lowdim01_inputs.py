#!/usr/bin/env python3
"""Host registrar of the LOWDIM-01 (#48) inputs (solver-free): the coefficient gradient bound from STEP-01, the proposal direction, the candidate states with their geometry gates.

The coefficient gradient is the centered finite difference at +-2.5 mm of the STEP-01 run (same baseline, same job, deterministic): g_i = [R(+2.5 mm) - R(-2.5 mm)] / (2 * 2.5 mm).
It is used ONLY to propose a direction; accept/reject uses actual responses.  Writes inventory.json and the proposal direction raw.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import lowdim01_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf.design.geometry_gates import _gradient_diagnostics, cell_occupancy  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import sharp_volume_m3, smoothed_volume_and_gradient  # noqa: E402
from cfd_sdf.fd08_v2_campaign import MARGIN_GATE_M, construct_state, state_identity  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
STEP01 = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
CANONICAL_NPZ = Path("/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v17/sdf_design_state.npz")
CANONICAL_NPZ_SHA = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
# registered geometry gate thresholds (chosen from the solver-free STEP-01 exploration, geometry_exploration_step01_states.json, BEFORE the candidates were evaluated)
VOLUME_BAND = 0.10               # |V_eps(candidate)/V_eps(baseline) - 1| <= 10%  (smoothed volume, contract sdf_native_smoothed_volume_v1)
EIKONAL_MEDIAN_MAX = 0.10        # median | |grad phi| - 1 | over the narrow band <= 0.10  (reinitialization is NOT used; the baseline value is 2.5e-7)
CELL_COMPONENTS = 1              # solid cell components (face connectivity) must equal the baseline's
MARGIN_TOLERANCE_M = 1e-6


def geometry(state: SDFDesignState) -> dict:
    cells, n_cells = ndimage.label(cell_occupancy(state))
    nodes, n_nodes = ndimage.label(state.phi < 0)
    eik = _gradient_diagnostics(state)
    return {"sharp_volume_m3": float(sharp_volume_m3(state)), "smoothed_volume_m3": float(smoothed_volume_and_gradient(state).smoothed_volume_m3), "cell_components": int(n_cells),
            "node_components": int(n_nodes), "eikonal_median_abs_deviation": eik["median_abs_gradient_deviation"], "eikonal_p95_abs_deviation": eik["p95_abs_gradient_deviation"],
            "eikonal_max_abs_deviation": eik["max_abs_gradient_deviation"], "eikonal_band_node_count": eik["eikonal_band_node_count"]}


def gates(base: dict, cand: dict, audit: dict) -> dict:
    rel = cand["smoothed_volume_m3"] / base["smoothed_volume_m3"] - 1.0
    g = {"clearance": audit["zero_level_margin_m"] >= MARGIN_GATE_M, "masks_and_support_preserved": bool(audit["masks_equal"] and audit["support_outside_active_exactly_unchanged"]),
         "cell_components_equal_baseline": cand["cell_components"] == base["cell_components"] == CELL_COMPONENTS, "smoothed_volume_band": abs(rel) <= VOLUME_BAND,
         "eikonal_median_within_limit": cand["eikonal_median_abs_deviation"] <= EIKONAL_MEDIAN_MAX}
    return {"relative_smoothed_volume_change": rel, "relative_sharp_volume_change": cand["sharp_volume_m3"] / base["sharp_volume_m3"] - 1.0, "gates": g, "all_hard_gates_pass": all(g.values())}


def build(canonical: Path, write_raw: bool) -> dict:
    analysis_path = STEP01 / "step01_analysis.json"
    a = json.loads(analysis_path.read_text())
    assert a["verdict"] == "STEP01_RECORDED" and a["integrity"]["pass"] is True
    g = {}
    fd = {}
    for d in L.BASIS:
        row = a["series"][f"{d}|downforce"]["rows"][0]
        assert row["step_mm"] == L.FD_STEP_MM
        g[d] = row["g_sec_n_per_m"]
        fd[d] = {"r_plus_n": row["r_plus_n"], "r_minus_n": row["r_minus_n"], "g_sec_n_per_m": row["g_sec_n_per_m"], "ghat_fd08_n_per_m": a["series"][f"{d}|downforce"]["g_hat_n_per_m"]}
    inv1 = json.loads((STEP01 / "inventory.json").read_text())
    base_raw = ROOT / inv1["baseline"]["path"]
    phi = S.read_f4(base_raw)
    dirs = {n: S.read_f4(ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs" / e["file"]) for n, e in inv1["directions"].items()}
    prop, info = L.coefficient_direction(g, dirs)
    raw = S.to_raw(prop)
    path = E / "inputs" / L.PROPOSAL_FILE
    if write_raw:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    else:
        assert path.read_bytes() == raw, "the committed proposal direction differs from the re-derivation"
    parent = SDFDesignState.load(canonical)
    assert S.sha256_bytes(canonical.read_bytes()) == CANONICAL_NPZ_SHA and S.to_raw(parent.phi) == S.to_raw(phi)
    base_geo = geometry(parent)
    base_id = state_identity(parent)
    rows = []
    seen: set[bytes] = set()
    for item in L.plan():
        if item["kind"] == "baseline":
            child, audit, raw_c = parent, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": base_id["margin_m"], "masks_equal": True,
                                           "support_outside_active_exactly_unchanged": True}, S.to_raw(phi)
            geo = base_geo
            gate = None
        else:
            child, audit = construct_state(parent, prop, item["step_mm"], item["sign"])
            raw_c = S.to_raw(child.phi)
            assert raw_c == S.to_raw(S.perturb(phi, prop, item["step_mm"], item["sign"])), f"runner-style numpy generation differs from construct_state: {item['name']}"
            assert raw_c not in seen and raw_c != S.to_raw(phi), f"a candidate repeats another state or the baseline: {item['name']}"
            seen.add(raw_c)
            geo = geometry(child)
            gate = gates(base_geo, geo, audit)
        ident = state_identity(child)
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp) / "a.npz", Path(tmp) / "b.npz"
            child.save(p1); child.save(p2)
            npz1, npz2 = S.sha256_bytes(p1.read_bytes()), S.sha256_bytes(p2.read_bytes())
        assert npz1 == npz2
        rows.append({**item, "kernel": "a", "phi_fortran_order_sha256": ident["phi_fortran_order_sha256"], "phi_c_order_sha256": ident["phi_c_order_sha256"], "state_sha256": ident["state_sha256"],
                     "npz_sha256": npz1, "changed_node_count": int(audit["changed_node_count"]), "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]),
                     "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": MARGIN_TOLERANCE_M, "geometry": geo, "geometry_gates": gate})
    criteria_bytes = (ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json").read_bytes()
    canonical_state = json.loads(criteria_bytes)["canonical_state"]
    job_env_common = inv1["job_env_common"]
    pred = {}
    for item in rows[1:]:
        s = item["step_mm"] * item["sign"]
        pred[item["name"]] = {"linear_predicted_downforce_change_n": sum(g[n] * (info["per_unit_step_basis_coefficients"][n] * s / 1000.0) for n in L.BASIS)}
    return {"kind": "lowdim01_state_inventory", "job_env_common": job_env_common, "formal_criteria_sha256": hashlib.sha256(criteria_bytes).hexdigest(), "baseline": inv1["baseline"],
            "fd08_baseline_reference": inv1["fd08_baseline_reference"], "basis": list(L.BASIS), "directions": inv1["directions"],
            "coefficient_gradient": {"source": "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json (centered +-2.5 mm, downforce)", "step_mm": L.FD_STEP_MM,
                                     "step01_analysis_sha256": S.sha256_bytes(analysis_path.read_bytes()), "units": "N/m per unit-max-norm basis direction (= 1e3 x N/mm)", "values": fd},
            "proposal": {"objective": "maximise downforce", "file": str(path.relative_to(ROOT)), "sha256_fortran_raw": S.sha256_bytes(raw), **info,
                         "metric": "Euclidean in coefficient space (no curvature weighting)"},
            "candidate_step_mm": list(L.CANDIDATE_STEP_MM), "control_step_mm": list(L.CONTROL_STEP_MM), "margin_gate_m": MARGIN_GATE_M,
            "geometry_gate_thresholds": {"smoothed_volume_band": VOLUME_BAND, "eikonal_median_abs_deviation_max": EIKONAL_MEDIAN_MAX, "cell_components": CELL_COMPONENTS, "clearance_m": MARGIN_GATE_M,
                                         "reinitialization": "none (SDF-02 / #28 is not qualified)", "recorded_only": ["sharp volume change", "eikonal p95 / max", "node components", "min feature width", "gaps"]},
            "linear_prediction_reference_only": pred, "canonical_npz_sha256": CANONICAL_NPZ_SHA, "kernels": {"a": [r["name"] for r in rows]}, "states": rows,
            "perturbation": "float32(float64(phi) + (sign*eps_m)*float64(direction)), eps_m = step_mm/1000 (cfd_sdf.fd08_v2_campaign.construct_state)"}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--canonical", type=Path, default=CANONICAL_NPZ)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    inv = build(args.canonical, write_raw=not args.check)
    data = (json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()
    out = E / "inventory.json"
    if args.check:
        assert out.read_bytes() == data, "the committed inventory differs from the re-derivation"
        print("inventory reproduced", hashlib.sha256(data).hexdigest())
        return
    if out.exists():
        sys.exit("refusing to overwrite the inventory")
    E.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data); out.with_name("inventory.json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
