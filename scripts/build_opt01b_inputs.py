#!/usr/bin/env python3
"""OPT-01 v1.1 Stage B host registrar: the parent plus the actual-primal ladder along the Stage A robust solution, with the contract's pre-CFD gates.  Solver-free.

Derives the proposal direction from the hash-pinned OPT-01 Stage A analysis (robust coefficient vector through the production `coefficient_direction`, max-norm 1, m equal to the
Stage A normalization to 1e-12), reconstructs the OPT-01 v1 parent (generation 1) from the retained Stage A parent NPZ, and builds the seven states per grid (parent, four positive
steps, two reverse diagnostics).  Pre-CFD gates run here once on the exact bytes under contract v1.1 gate_scope: PROPOSAL states (parent, positive steps) keep the full GEOM-02 profile v2
bundle (13 gates incl. crossing-slope), P22-v2 N_phi <= 8272 with a positive count-equal margin and the retained LOWDIM gates; the reverse diagnostics are probes (crossing-slope report-only).
A positive step failing a gate is NOT dropped and NOT shrunk: it is recorded gate-REJECTED (ineligible) and still runs in CFD for the record.  A failing parent or reverse diagnostic
blocks the stage (BLOCKED_PRE_CFD).  Plateau attribution (baseline |phi| < 1e-6 tie nodes; a node-set coincidence, not a mechanism) is recorded for every crossing-slope failure.
Copy-adapted from build_lowdim04b_inputs / build_opt01a_inputs (never edited).  Refuses to overwrite; --check re-derives.
"""
from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import json
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_lowdim01_inputs as lowdim  # noqa: E402
import build_lowdim04a_inputs as b4a  # noqa: E402
import build_opt01a_inputs as A1  # noqa: E402
import evaluate_opt01_v1_states as E1  # noqa: E402
import geom02_canonical as canon  # noqa: E402
import lowdim01_states  # noqa: E402
import opt01b_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/opt01b_stage_b_2026_10_15"
STAGE_A = ROOT / "docs/evidence/opt01a_stage_a_2026_10_15"
STAGE_A_ANALYSIS_SHA = "229efc7e58c9b99069de7edf7434768329352080a61b1e522c52d243c2001d43"
STAGE_A_INVENTORY_SHA = "7046bf2c98df1acbc8cd66a8c91420c37ab2de79d351655d92aaaf22b5044f92"
PARENT_STATE_SHA_PREFIX = "c9e12f62"
PARENT_RAW, PROPOSAL_RAW = EVIDENCE / "inputs/parent.phi_f4_fortran.raw", EVIDENCE / "inputs/robust_opt01a.dir_f4_fortran.raw"
SOLVER_WALL_TIME_CAP_S = 7 * 900  # as LOWDIM-04B: seven states x the 900 s per-state timeout
IDENTITY_KEYS = A1.IDENTITY_KEYS
sha = b4a.sha


def derive_direction(analysis: dict, arrays: dict):
    robust = analysis["solutions"]["robust_cross_grid"]
    prop, info = lowdim01_states.coefficient_direction(dict(zip(L.BASIS, robust["coefficient_vector"])), arrays)
    stage_a_m = analysis["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["m_max_abs_sum"]
    if abs(info["m_max_abs_sum"] - stage_a_m) > 1e-12 or float(np.max(np.abs(prop))) != 1.0:
        raise ValueError("the regenerated direction differs from the Stage A normalization")
    return prop, info, robust


@functools.cache
def context() -> SimpleNamespace:
    contract = L.CONTRACT
    A1.verify_pins(contract)
    pins = contract["pins"]
    if sha(STAGE_A / "opt01a_analysis.json") != STAGE_A_ANALYSIS_SHA or sha(STAGE_A / "inventory.json") != STAGE_A_INVENTORY_SHA:
        raise ValueError("the OPT-01 Stage A analysis or inventory differs from the recorded immutable result")
    analysis, inv_a = json.loads((STAGE_A / "opt01a_analysis.json").read_text()), json.loads((STAGE_A / "inventory.json").read_text())
    if analysis["integrity"]["pass"] is not True or analysis["verdict"] != "LOCAL_FEASIBLE_CONE_FOUND":
        raise ValueError("the Stage A result is not intact and FOUND")
    profile = json.loads((ROOT / pins["gate_profile_v2"]["path"]).read_text())
    policy = SDFTopologyPolicyResearchV2.from_dict(json.loads((ROOT / pins["resolved_research_policy"]["path"]).read_text())["policy"])
    baseline = SDFDesignState.load(b4a.BASELINE_NPZ)
    if sha(b4a.BASELINE_NPZ) != canon.BASELINE_NPZ_SHA:
        raise ValueError("retained baseline NPZ differs from the registered one")
    parent_npz = ROOT / inv_a["parent"]["npz_path"]
    row_a = inv_a["states"][0]
    if sha(parent_npz) != row_a["npz_sha256"]:
        raise ValueError("retained OPT-01 parent NPZ differs from the Stage A inventory")
    parent = SDFDesignState.load(parent_npz)
    ident = state_identity(parent)
    if any(ident[k] != row_a[k] for k in IDENTITY_KEYS) or not ident["state_sha256"].startswith(PARENT_STATE_SHA_PREFIX) or parent.generation != 1:
        raise ValueError("the OPT-01 v1 parent differs from the Stage A inventory parent (generation 1)")
    arrays = {n: S.read_f4(ROOT / d["path"]) for n, d in pins["basis_raw_files"].items()}
    prop, info, robust = derive_direction(analysis, arrays)
    states = {}
    for item in L.plan():
        if item["kind"] == "parent":
            states[item["name"]] = (parent, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": ident["margin_m"]})
        else:
            child, audit = construct_state(parent, prop, item["step_mm"], item["sign"])
            if S.to_raw(child.phi) != S.to_raw(S.perturb(parent.phi, prop, item["step_mm"], item["sign"])):
                raise ValueError("host and runner perturbation bytes differ")
            states[item["name"]] = (child, audit)
    return SimpleNamespace(contract=contract, profile=profile, policy=policy, baseline=baseline, parent=parent, inv_a=inv_a, analysis=analysis, prop=prop, info=info, robust=robust,
                           states=states, base_geometry=lowdim.geometry(baseline))


def gate_job(name: str) -> dict:
    """The heavy part (r=8 export, self-intersection): one state, run once here and never in the kernel."""
    ctx = context()
    child, _ = ctx.states[name]
    export = canon.export_from_state(child, ctx.profile)
    out = {"record": canon.strip_runtime(E1.state_record(child, ctx.parent, ctx.profile, ctx.policy, export, ctx.base_geometry))}
    out["plateau"] = A1.plateau_attribution(child.phi, ctx.baseline.phi, float(child.spacing_m), float(ctx.profile["near_zero_gradient_band"]["threshold"]))
    if out["plateau"]["failing_nodes"] != out["record"]["geom02_v2"]["gates"]["near_zero_gradient_band"]["measured"].get("nodes_below_threshold", 0):
        raise ValueError(f"{name}: the plateau attribution does not re-derive the gate's failing node count")
    return out


def selected_lineage(ctx, child) -> dict:
    """Identity the step would have as the next parent: construct_state keeps the parent generation, a selected step becomes the new parent with generation + 1 (phi hashes unchanged)."""
    nxt = SDFDesignState.create(
        phi=child.phi, origin_m=child.origin_m, spacing_m=child.spacing_m, design_mask=child.design_mask, fixed_solid_mask=child.fixed_solid_mask, forbidden_mask=child.forbidden_mask,
        root_mask=child.root_mask, narrow_band_width_m=child.narrow_band_width_m, generation=child.generation + 1, source_sha256=child.source_sha256,
        topology_policy_id=child.topology_policy_id, reinitialization_policy_id=child.reinitialization_policy_id)
    ident = state_identity(nxt)
    return {"generation": nxt.generation, "state_sha256": ident["state_sha256"], "parent_state_sha256": state_identity(ctx.parent)["state_sha256"], "rollback": "keep the parent"}


def build(jobs: int = 3, gate_results: dict | None = None):
    ctx = context()
    if gate_results is None:
        names = [r["name"] for r in L.plan()]
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            gate_results = dict(zip(names, pool.map(gate_job, names)))
    parent_ident = state_identity(ctx.parent)
    parent_v = {"v_cont_m3": b4a.continuum_zero_set_volume_m3(ctx.parent.phi, ctx.parent.spacing_m), "v_eps_m3": lowdim.geometry(ctx.parent)["smoothed_volume_m3"]}
    rows, seen, blockers, rejected = [], set(), [], []
    for item in L.plan():
        child, audit = ctx.states[item["name"]]
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
        residual, inv = V2.hard_count_residual(child), b4a.invariance(ctx.parent.phi, child.phi)
        margin = inv["count_equal_margin_m"]
        rec = gate_results[item["name"]]["record"]
        table = A1.gate_table(rec, margin)
        failed = L.hard_failures(item["kind"], table)
        reported = sorted(g for g, v in table.items() if v != "pass" and g not in failed)
        if failed and item["kind"] != "candidate":
            blockers.append({"state": item["name"], "failed": failed})
        if failed and item["kind"] == "candidate":
            rejected.append({"state": item["name"], "step_mm": item["step_mm"], "failed": failed})
        geo, v_cont = lowdim.geometry(child), b4a.continuum_zero_set_volume_m3(child.phi, child.spacing_m)
        pre_cfd = {"all_pass": not failed, "failed": failed, "report_only_failed": reported, "near_zero_gradient_band": gate_results[item["name"]]["plateau"], "table": table,
                   "geom02_v2_pass_count": sum(v["status"] == "pass" for v in rec["geom02_v2"]["gates"].values()), "geom02_v2_gate_count": len(rec["geom02_v2"]["gates"]), "record": rec}
        if item["kind"] == "candidate":
            pre_cfd["eligible_for_acceptance"] = not failed
            pre_cfd["gate_rejected"] = bool(failed)
        rows.append({**item, **{k: ident[k] for k in IDENTITY_KEYS}, "npz_sha256": npz_sha, "changed_node_count": int(audit["changed_node_count"]),
                     "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]), "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": 1e-6,
                     "geometry": geo, "pre_cfd_gates": pre_cfd,
                     **({"if_selected_lineage": selected_lineage(ctx, child)} if item["kind"] == "candidate" else {}),
                     "hard_count": {"sampled_solid_centers": V2.MAX_SOLID_CENTERS + residual, "residual_vs_n_max": residual, **inv},
                     "volume": {"v_eps_m3": geo["smoothed_volume_m3"], "v_cont_m3": v_cont, "v_eps_vs_parent": geo["smoothed_volume_m3"] / parent_v["v_eps_m3"] - 1.0,
                                "v_cont_vs_parent": v_cont / parent_v["v_cont_m3"] - 1.0, "sharp_volume_m3": geo["sharp_volume_m3"]}})
    pins = ctx.contract["pins"]
    grids = {}
    for kernel, case in (("a", "flow_24"), ("b", "flow_32")):
        grid = pins["dual_grid_kernels"][case]
        measurement = copy.deepcopy(grid["measurement"])
        measurement.update({"solver_wall_time_cap_s": SOLVER_WALL_TIME_CAP_S, "qualification_claim": "bounded OPT-01 v1 Stage B two-grid actual-primal ladder; no qualification"})
        csv_rel = f"docs/evidence/opt01a_stage_a_2026_10_15/kernel_output/opt01a_{kernel}/states/opt01a__parent/{case}.forces.csv"
        retained = ctx.analysis["state_forces_n"][case]["opt01a__parent"]
        host = recompute_force_n(ROOT / csv_rel, {"measurement": measurement})
        if grid["kernel"] != kernel or retained["forces_csv_sha256"] != sha(ROOT / csv_rel) or any(abs(host[f"{q}_n"] - retained[f"{q}_n"]) > 1e-12 * abs(retained[f"{q}_n"]) for q in ("drag", "downforce")):
            raise ValueError(f"{case} parent reference CSV differs from the retained OPT-01 Stage A analysis")
        grids[kernel] = {"case_id": case, "job": grid["job"]["path"], "measurement": measurement,
                         "baseline_reference": {"forces_csv_path": csv_rel, "forces_csv_sha256": sha(ROOT / csv_rel), "role": "retained OPT-01 Stage A parent run of the identical phi bytes (the OPT-01 v1 parent)",
                                                "host_recomputed_n": {q: host[f"{q}_n"] for q in ("drag", "downforce")}, "force_scale_n_per_solver_force": host["force_scale_n_per_solver_force"]}}
    raw_prop = S.to_raw(ctx.prop)
    inventory = {"kind": "opt01b_stage_b_inventory", "contract": {"path": L.CONTRACT_REL, "sha256": L.CONTRACT_SHA256, "contract_id": ctx.contract["contract_id"], "pins_verified": A1.verify_pins(ctx.contract)},
                 "stage_status": "BLOCKED_PRE_CFD" if blockers else "READY", "blockers": blockers, "gate_rejected_candidates": rejected, "gate_scope": ctx.contract["D3_update"]["gate_scope"],
                 "basis_order": list(L.BASIS), "steps_mm": list(L.STEPS_MM), "control_steps_mm": list(L.CONTROL_STEPS_MM),
                 "parent": {"state_sha256": parent_ident["state_sha256"], "phi_fortran_order_sha256": parent_ident["phi_fortran_order_sha256"], "phi_c_order_sha256": parent_ident["phi_c_order_sha256"],
                            "generation": ctx.parent.generation, "raw_path": str(PARENT_RAW.relative_to(ROOT)), "npz_sha256": ctx.inv_a["states"][0]["npz_sha256"],
                            "lineage": {"opt01a_stage_a_inventory_sha256": STAGE_A_INVENTORY_SHA, "opt01a_parent_npz_path": ctx.inv_a["parent"]["npz_path"], "opt01a_parent_lineage": ctx.inv_a["parent"]["lineage"]}},
                 "geometry_gate_base": "canonical v17 baseline (smoothed_volume_band) and the OPT-01 v1 parent (GEOM-02 transition, allowed_events = ())", "margin_gate_m": 0.15, "grids": grids,
                 "kernels": {k: [r["name"] for r in rows] for k in grids}, "states": rows, "directions": pins["basis_raw_files"], "job_env_common": pins["job_env_common"], "parent_volume": parent_v,
                 "p22_v2": {"registration_path": pins["p22_v2"]["path"], "registration_sha256": pins["p22_v2"]["sha256"], "n_max": V2.MAX_SOLID_CENTERS,
                            "meaning": "lattice count only; constrains no physical or sub-voxel volume"},
                 "proposal": {"file": str(PROPOSAL_RAW.relative_to(ROOT)), "sha256_fortran_raw": hashlib.sha256(raw_prop).hexdigest(), "coefficient_vector": ctx.robust["coefficient_vector"],
                              "m_max_abs_sum": ctx.info["m_max_abs_sum"], "per_unit_step_basis_coefficients": ctx.info["per_unit_step_basis_coefficients"],
                              "source": "OPT-01 Stage A robust cross-grid solution (contract v1.1 E6: derived by the registrar through the production coefficient_direction)"},
                 "stage_a": {"analysis_path": str((STAGE_A / "opt01a_analysis.json").relative_to(ROOT)), "analysis_sha256": STAGE_A_ANALYSIS_SHA, "inventory_path": str((STAGE_A / "inventory.json").relative_to(ROOT)),
                             "inventory_sha256": STAGE_A_INVENTORY_SHA},
                 "lineage": {"parent_state_sha256": parent_ident["state_sha256"], "parent_generation": ctx.parent.generation, "direction_sha256_fortran_raw": hashlib.sha256(raw_prop).hexdigest(),
                             "contract_sha256": L.CONTRACT_SHA256, "stage_a_analysis_sha256": STAGE_A_ANALYSIS_SHA, "child_generation_if_selected": ctx.parent.generation + 1, "rollback": "keep the parent"}}
    return inventory, S.to_raw(ctx.parent.phi), raw_prop


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--jobs", type=int, default=3)
    args = p.parse_args()
    inv, raw_parent, raw_prop = build(args.jobs)
    data, target = canonical_json(inv), EVIDENCE / "inventory.json"
    if args.check:
        if target.read_bytes() != data or PARENT_RAW.read_bytes() != raw_parent or PROPOSAL_RAW.read_bytes() != raw_prop:
            raise SystemExit("frozen inventory/raw inputs differ from their derivation")
    else:
        if target.exists() or PARENT_RAW.exists() or PROPOSAL_RAW.exists():
            raise SystemExit("refusing to overwrite OPT-01 v1 Stage B inputs")
        PARENT_RAW.parent.mkdir(parents=True, exist_ok=True)
        PARENT_RAW.write_bytes(raw_parent); PROPOSAL_RAW.write_bytes(raw_prop)
        target.write_bytes(data)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print("inventory", inv["stage_status"], hashlib.sha256(data).hexdigest())
    for b in inv["blockers"]:
        print("BLOCKER", json.dumps(b))
    for b in inv["gate_rejected_candidates"]:
        print("GATE-REJECTED", json.dumps(b))
    for r in inv["states"]:
        g = r["pre_cfd_gates"]
        print(r["name"], g["geom02_v2_pass_count"], "/", g["geom02_v2_gate_count"], "hard_failed", g["failed"], "report_only", g["report_only_failed"], "plateau", g["near_zero_gradient_band"],
              "margin", r["hard_count"]["count_equal_margin_m"], "v_eps_vs_parent", r["volume"]["v_eps_vs_parent"])
    if inv["blockers"]:
        raise SystemExit(3)  # registered blocker before CFD: no freeze, no kernel


if __name__ == "__main__":
    main()
