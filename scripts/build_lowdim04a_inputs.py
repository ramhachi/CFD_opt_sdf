#!/usr/bin/env python3
"""LOWDIM-04A Stage A (#51) host registrar: the nine states per grid at the accepted LOWDIM-03 parent.  Solver-free.

Builds inventory.json (identity table with four named hashes per state, pre-CFD geometry gates, exact hard count and the max-norm invariance
margin per state, descriptive volumes, the parent byte-identity reference) and inputs/parent.phi_f4_fortran.raw.  Refuses to overwrite; --check re-derives.
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
import lowdim04a_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import _corner_mean  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13"
L3 = ROOT / "docs/evidence/lowdim03_dual_grid_primal_2026_10_10"
P22 = ROOT / "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs"
GRID01 = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"
PARENT_NPZ, BASELINE_NPZ = P22 / "lowdim03_parent.npz", P22 / "v17_baseline.npz"
PARENT_NPZ_SHA = "0ce3256b0f3e5c919caeb2ac1b36f1a33838f34c767c091cb89bda0234ac750b"
PARENT_FORTRAN_SHA = "b02dc49c39c3e8895befd5a95ae007ccf04fb2582064e8d79bd0f4c57c55286e"
PARENT_RAW = EVIDENCE / "inputs/parent.phi_f4_fortran.raw"
REGISTRATION_V2 = ROOT / "docs/evidence/sdf_native_volume_semantics_v2_2026_10.json"
LOWDIM03_PARENT_ROW = "lowdim03__prop__s1.25mm"
SOLVER_WALL_TIME_CAP_S = 9 * 900
ROUNDING_U = 2.0**-24


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def continuum_zero_set_volume_m3(phi: np.ndarray, spacing_m: float, n: int = 48) -> float:
    """Descriptive volume of {trilinear phi < 0}: exact in z (the interpolant is linear along z), n x n samples in (x, y) in every mixed cell."""
    p = phi.astype(np.float64)
    nx, ny, nz = p.shape
    corners = np.stack([p[i:nx - 1 + i, j:ny - 1 + j, k:nz - 1 + k] for i in (0, 1) for j in (0, 1) for k in (0, 1)], -1)
    inside = int((corners.max(-1) < 0).sum())
    ci, cj, ck = np.argwhere((corners.min(-1) < 0) & (corners.max(-1) >= 0)).T
    t = (np.arange(n) + 0.5) / n
    X, Y = (a.ravel() for a in np.meshgrid(t, t, indexing="ij"))

    def face(k):
        c = lambda a, b: p[ci + a, cj + b, ck + k][:, None]
        return c(0, 0) * (1 - X) * (1 - Y) + c(1, 0) * X * (1 - Y) + c(0, 1) * (1 - X) * Y + c(1, 1) * X * Y

    a, b = face(0), face(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where((a < 0) & (b < 0), 1.0, np.where((a >= 0) & (b >= 0), 0.0, np.where(a < 0, a / (a - b), -b / (a - b))))
    return float((inside + fraction.mean(1).sum()) * spacing_m**3)


def invariance(parent_phi: np.ndarray, child_phi: np.ndarray) -> dict:
    """Hard-count invariance within a max-norm radius, with the Float32 rounding terms: a state within r_plus (no increase) or r_all (count equal) of the parent."""
    c = _corner_mean(parent_phi).astype(np.float64)
    r_all, r_plus = float(np.abs(c).min()), float(c[c >= 0].min())
    sup = float(np.max(np.abs(child_phi.astype(np.float64) - parent_phi.astype(np.float64))))
    gamma7 = 7 * ROUNDING_U / (1 - 7 * ROUNDING_U)
    rounding = 2 * gamma7 * float(np.max(np.abs(child_phi))) + float(np.max(np.spacing(np.abs(child_phi).astype(np.float32)))) / 2
    return {"min_abs_parent_centre_m": r_all, "min_fluid_parent_centre_m": r_plus, "sup_norm_dphi_m": sup, "rounding_allowance_m": rounding,
            "count_equal_margin_m": r_all - sup - rounding, "count_no_increase_margin_m": r_plus - sup - rounding}


def build():
    if sha(PARENT_NPZ) != PARENT_NPZ_SHA:
        raise ValueError("retained parent NPZ differs from the registered LOWDIM-03 parent")
    inv3 = json.loads((L3 / "inventory.json").read_text())
    analysis3 = json.loads((L3 / "amendment1/lowdim03_analysis.json").read_text())
    source = json.loads((GRID01 / "inventory.json").read_text())
    parent, baseline = SDFDesignState.load(PARENT_NPZ), SDFDesignState.load(BASELINE_NPZ)
    row3 = next(r for r in inv3["states"] if r["name"] == LOWDIM03_PARENT_ROW)
    ident_parent = state_identity(parent)
    if ident_parent["phi_fortran_order_sha256"] != PARENT_FORTRAN_SHA or any(ident_parent[k] != row3[k] for k in ("phi_fortran_order_sha256", "phi_c_order_sha256", "state_sha256")):
        raise ValueError("parent identity differs from the LOWDIM-03 s1.25 mm row")
    directions = {n: S.read_f4(ROOT / source["directions"][n]["path"]) for n in L.BASIS}
    for n in L.BASIS:
        if sha(ROOT / source["directions"][n]["path"]) != source["directions"][n]["sha256_fortran_raw"]:
            raise ValueError(f"basis hash mismatch: {n}")
    base_geo, parent_geo = geometry_helpers.geometry(baseline), geometry_helpers.geometry(parent)
    parent_v = {"v_cont_m3": continuum_zero_set_volume_m3(parent.phi, parent.spacing_m), "v_eps_m3": parent_geo["smoothed_volume_m3"]}
    rows, seen = [], set()
    for item in L.plan():
        if item["kind"] == "parent":
            child, audit, geo, gate = parent, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": ident_parent["margin_m"]}, parent_geo, row3["geometry_gates"]
        else:
            child, audit = construct_state(parent, directions[item["direction"]], item["step_mm"], item["sign"])
            if S.to_raw(child.phi) != S.to_raw(S.perturb(parent.phi, directions[item["direction"]], item["step_mm"], item["sign"])):
                raise ValueError("host and runner perturbation bytes differ")
            geo = geometry_helpers.geometry(child)
            gate = geometry_helpers.gates(base_geo, geo, audit)
            if not gate["all_hard_gates_pass"]:
                raise ValueError(f"geometry preflight failed (blocker, no state is dropped or shrunk): {item['name']}")
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
    for kernel, case in (("a", "flow_24"), ("b", "flow_32")):
        measurement = copy.deepcopy(inv3["grids"][kernel]["measurement"])
        measurement.update({"kernel_execution_allowance_s": 10800, "per_state_timeout_s": 900, "solver_wall_time_cap_s": SOLVER_WALL_TIME_CAP_S,
                            "qualification_claim": "bounded LOWDIM-04A Stage A local dual-grid model evidence; no qualification"})
        csv_rel = str((L3 / f"failed_attempt1/kernel_output/lowdim03_{kernel}/states/{LOWDIM03_PARENT_ROW}/{case}.forces.csv").relative_to(ROOT))
        csv_sha = sha(ROOT / csv_rel)
        retained = analysis3["state_forces_n"][case][LOWDIM03_PARENT_ROW]
        host = recompute_force_n(ROOT / csv_rel, {"measurement": measurement})
        if retained["forces_csv_sha256"] != csv_sha or any(abs(host[f"{q}_n"] - retained[f"{q}_n"]) > 1e-12 * abs(retained[f"{q}_n"]) for q in ("drag", "downforce")):
            raise ValueError(f"{case} parent reference CSV differs from the retained LOWDIM-03 analysis")
        grids[kernel] = {"case_id": case, "job": inv3["grids"][kernel]["job"], "measurement": measurement,
                         "baseline_reference": {"forces_csv_path": csv_rel, "forces_csv_sha256": csv_sha, "role": "retained LOWDIM-03 prop s1.25 mm run of the identical parent bytes",
                                                "host_recomputed_n": {q: host[f"{q}_n"] for q in ("drag", "downforce")}, "force_scale_n_per_solver_force": host["force_scale_n_per_solver_force"]}}
    grid01 = json.loads((GRID01 / "grid01_analysis.json").read_text())
    inventory = {"kind": "lowdim04a_stage_a_inventory", "basis_order": list(L.BASIS), "step_mm": L.STEP_MM,
                 "parent": {"npz_path": str(PARENT_NPZ.relative_to(ROOT)), "npz_sha256": PARENT_NPZ_SHA, "state_sha256": ident_parent["state_sha256"],
                            "phi_fortran_order_sha256": PARENT_FORTRAN_SHA, "raw_path": str(PARENT_RAW.relative_to(ROOT)), "lowdim03_row": LOWDIM03_PARENT_ROW},
                 "baseline": inv3["baseline"], "canonical_npz": inv3["canonical_npz"], "directions": source["directions"], "job_env_common": inv3["job_env_common"],
                 "margin_gate_m": 0.15, "geometry_gate_base": "canonical v17 baseline (as in every LOWDIM geometry gate)", "grids": grids,
                 "kernels": {k: [r["name"] for r in rows] for k in grids}, "states": rows,
                 "geometry_gate_thresholds": inv3["geometry_gate_thresholds"], "perturbation": source["perturbation"], "formal_criteria_path": inv3["formal_criteria_path"],
                 "formal_criteria_sha256": inv3["formal_criteria_sha256"], "parent_volume": parent_v,
                 "p22_v2": {"registration_path": str(REGISTRATION_V2.relative_to(ROOT)), "registration_sha256": sha(REGISTRATION_V2), "n_max": V2.MAX_SOLID_CENTERS,
                            "meaning": "lattice count only; constrains no physical or sub-voxel volume"},
                 "prior_robust_proposal": {"coefficient_vector": inv3["proposal"]["coefficient_vector"], "m_max_abs_sum": inv3["proposal"]["m_max_abs_sum"],
                                           "sha256_fortran_raw": inv3["proposal"]["sha256_fortran_raw"]},
                 "grid01_reference": {"analysis_path": str((GRID01 / "grid01_analysis.json").relative_to(ROOT)), "analysis_sha256": sha(GRID01 / "grid01_analysis.json"),
                                      "coefficient_vectors_n_per_m": grid01["coefficient_vectors_n_per_m"], "step_m": 0.0025, "base": "canonical v17 baseline"}}
    return inventory, S.to_raw(parent.phi)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    inv, raw = build()
    data, target = canonical_json(inv), EVIDENCE / "inventory.json"
    if hashlib.sha256(raw).hexdigest() != PARENT_FORTRAN_SHA:
        raise ValueError("parent raw is not the registered Fortran-order bytes")
    if args.check:
        if target.read_bytes() != data or PARENT_RAW.read_bytes() != raw:
            raise SystemExit("frozen inventory/parent raw differs from its derivation")
    else:
        if target.exists() or PARENT_RAW.exists():
            raise SystemExit("refusing to overwrite LOWDIM-04A Stage A inputs")
        PARENT_RAW.parent.mkdir(parents=True, exist_ok=True)
        PARENT_RAW.write_bytes(raw)
        target.write_bytes(data)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print("inventory reproduced", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
