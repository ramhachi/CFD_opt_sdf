#!/usr/bin/env python3
"""LOWDIM-04 Stage B (#51) host registrar: the parent plus the actual-primal ladder along the Stage A robust solution.  Solver-free.

Derives the proposal direction from the hash-pinned Stage A analysis, builds the seven states per grid (parent, four positive steps, two reverse diagnostics),
checks the pre-CFD gates, the exact hard count and the max-norm invariance per state, and writes inventory.json plus the parent and direction raw inputs.
Refuses to overwrite; --check re-derives.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_lowdim01_inputs as geometry_helpers  # noqa: E402
import lowdim01_states  # noqa: E402
import lowdim04b_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402
from build_lowdim04a_inputs import BASELINE_NPZ, PARENT_FORTRAN_SHA, PARENT_NPZ, PARENT_NPZ_SHA, continuum_zero_set_volume_m3, invariance, sha  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/lowdim04b_stage_b_2026_10_13"
STAGE_A = ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13"
STAGE_A_ANALYSIS_SHA = "414d08677fb263db09e33f9a253d004c505fd4910d1859261ec6ffc5c4fd119d"
PARENT_RAW = EVIDENCE / "inputs/parent.phi_f4_fortran.raw"
PROPOSAL_RAW = EVIDENCE / "inputs/robust_stage_a.dir_f4_fortran.raw"
SOLVER_WALL_TIME_CAP_S = 7 * 900


def build():
    if sha(STAGE_A / "lowdim04a_analysis.json") != STAGE_A_ANALYSIS_SHA:
        raise ValueError("the Stage A analysis differs from the recorded immutable result")
    analysis = json.loads((STAGE_A / "lowdim04a_analysis.json").read_text())
    if analysis["integrity"]["pass"] is not True or analysis["verdict"] != "LOCAL_FEASIBLE_CONE_FOUND":
        raise ValueError("the Stage A result is not intact and FOUND")
    inv_a = json.loads((STAGE_A / "inventory.json").read_text())
    if sha(PARENT_NPZ) != PARENT_NPZ_SHA:
        raise ValueError("retained parent NPZ differs from the registered LOWDIM-03 parent")
    arrays = {n: S.read_f4(ROOT / inv_a["directions"][n]["path"]) for n in L.BASIS}
    for n in L.BASIS:
        if sha(ROOT / inv_a["directions"][n]["path"]) != inv_a["directions"][n]["sha256_fortran_raw"]:
            raise ValueError(f"basis hash mismatch: {n}")
    robust = analysis["solutions"]["robust_cross_grid"]
    prop, info = lowdim01_states.coefficient_direction(dict(zip(L.BASIS, robust["coefficient_vector"])), arrays)
    stage_a_m = analysis["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["m_max_abs_sum"]
    if abs(info["m_max_abs_sum"] - stage_a_m) > 1e-12 or float(np.max(np.abs(prop))) != 1.0:
        raise ValueError("the regenerated direction differs from the Stage A normalization")
    raw_prop = S.to_raw(prop)
    parent, baseline = SDFDesignState.load(PARENT_NPZ), SDFDesignState.load(BASELINE_NPZ)
    ident_parent = state_identity(parent)
    if ident_parent["phi_fortran_order_sha256"] != PARENT_FORTRAN_SHA:
        raise ValueError("parent identity differs from the registered parent")
    base_geo, parent_geo = geometry_helpers.geometry(baseline), geometry_helpers.geometry(parent)
    parent_row_a = inv_a["states"][0]
    parent_v = {"v_cont_m3": continuum_zero_set_volume_m3(parent.phi, parent.spacing_m), "v_eps_m3": parent_geo["smoothed_volume_m3"]}
    rows, seen = [], set()
    for item in L.plan():
        if item["kind"] == "parent":
            child, audit, geo, gate = parent, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": ident_parent["margin_m"]}, parent_geo, parent_row_a["geometry_gates"]
        else:
            child, audit = construct_state(parent, prop, item["step_mm"], item["sign"])
            if S.to_raw(child.phi) != S.to_raw(S.perturb(parent.phi, prop, item["step_mm"], item["sign"])):
                raise ValueError("host and runner perturbation bytes differ")
            geo = geometry_helpers.geometry(child)
            gate = geometry_helpers.gates(base_geo, geo, audit)
            if not gate["all_hard_gates_pass"]:
                raise ValueError(f"geometry preflight failed (blocker, no step is dropped or shrunk): {item['name']}")
        ident = state_identity(child)
        if ident["phi_fortran_order_sha256"] in seen:
            raise ValueError("duplicate registered geometry")
        seen.add(ident["phi_fortran_order_sha256"])
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp) / "1.npz", Path(tmp) / "2.npz"
            child.save(p1); child.save(p2)
            npz_sha = sha(p1)
            if npz_sha != sha(p2):
                raise ValueError("non-deterministic NPZ serialization")
        residual, inv = V2.hard_count_residual(child), invariance(parent.phi, child.phi)
        if residual != 0 or (item["kind"] != "parent" and not inv["count_equal_margin_m"] > 0):
            raise ValueError(f"hard count is not exactly N_max or the invariance margin is not positive: {item['name']}")
        v_cont = continuum_zero_set_volume_m3(child.phi, child.spacing_m)
        rows.append({**item, **{k: ident[k] for k in ("phi_fortran_order_sha256", "phi_c_order_sha256", "state_sha256")}, "npz_sha256": npz_sha,
                     "changed_node_count": int(audit["changed_node_count"]), "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]),
                     "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": 1e-6, "geometry": geo, "geometry_gates": gate,
                     "hard_count": {"sampled_solid_centers": V2.MAX_SOLID_CENTERS + residual, "residual_vs_n_max": residual, **inv},
                     "volume": {"v_eps_m3": geo["smoothed_volume_m3"], "v_cont_m3": v_cont, "v_eps_vs_parent": geo["smoothed_volume_m3"] / parent_v["v_eps_m3"] - 1.0,
                                "v_cont_vs_parent": v_cont / parent_v["v_cont_m3"] - 1.0, "sharp_volume_m3": geo["sharp_volume_m3"]}})
    grids = {}
    for kernel, grid in inv_a["grids"].items():
        measurement = copy.deepcopy(grid["measurement"])
        measurement.update({"solver_wall_time_cap_s": SOLVER_WALL_TIME_CAP_S, "qualification_claim": "bounded LOWDIM-04 Stage B two-grid actual-primal ladder; no qualification"})
        grids[kernel] = {**copy.deepcopy(grid), "measurement": measurement}
    inventory = {"kind": "lowdim04b_stage_b_inventory", "basis_order": list(L.BASIS), "steps_mm": list(L.STEPS_MM), "control_steps_mm": list(L.CONTROL_STEPS_MM),
                 "parent": {**inv_a["parent"], "raw_path": str(PARENT_RAW.relative_to(ROOT))}, "baseline": inv_a["baseline"], "canonical_npz": inv_a["canonical_npz"],
                 "directions": inv_a["directions"], "job_env_common": inv_a["job_env_common"], "margin_gate_m": 0.15, "geometry_gate_base": inv_a["geometry_gate_base"],
                 "grids": grids, "kernels": {k: [r["name"] for r in rows] for k in grids}, "states": rows, "geometry_gate_thresholds": inv_a["geometry_gate_thresholds"],
                 "perturbation": inv_a["perturbation"], "formal_criteria_path": inv_a["formal_criteria_path"], "formal_criteria_sha256": inv_a["formal_criteria_sha256"],
                 "parent_volume": parent_v, "p22_v2": inv_a["p22_v2"],
                 "proposal": {"file": str(PROPOSAL_RAW.relative_to(ROOT)), "sha256_fortran_raw": hashlib.sha256(raw_prop).hexdigest(), "coefficient_vector": robust["coefficient_vector"],
                              "m_max_abs_sum": info["m_max_abs_sum"], "per_unit_step_basis_coefficients": info["per_unit_step_basis_coefficients"], "source": "Stage A robust cross-grid solution"},
                 "stage_a": {"analysis_path": str((STAGE_A / "lowdim04a_analysis.json").relative_to(ROOT)), "analysis_sha256": STAGE_A_ANALYSIS_SHA,
                             "inventory_sha256": sha(STAGE_A / "inventory.json")}}
    return inventory, S.to_raw(parent.phi), raw_prop


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    inv, raw_parent, raw_prop = build()
    data, target = canonical_json(inv), EVIDENCE / "inventory.json"
    if hashlib.sha256(raw_parent).hexdigest() != PARENT_FORTRAN_SHA:
        raise ValueError("parent raw is not the registered Fortran-order bytes")
    if args.check:
        if target.read_bytes() != data or PARENT_RAW.read_bytes() != raw_parent or PROPOSAL_RAW.read_bytes() != raw_prop:
            raise SystemExit("frozen inventory/raw inputs differ from their derivation")
    else:
        if target.exists() or PARENT_RAW.exists() or PROPOSAL_RAW.exists():
            raise SystemExit("refusing to overwrite LOWDIM-04 Stage B inputs")
        PARENT_RAW.parent.mkdir(parents=True, exist_ok=True)
        PARENT_RAW.write_bytes(raw_parent); PROPOSAL_RAW.write_bytes(raw_prop)
        target.write_bytes(data)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print("inventory reproduced", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
