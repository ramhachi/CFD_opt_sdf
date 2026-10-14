#!/usr/bin/env python3
"""OPT-01 v1.1 Stage A host registrar: the nine states per grid at the new OPT-01 v1 parent.  Solver-free.

New parent = the LOWDIM-04B selected state (LOWDIM-03 parent + 0.3125 mm x the robust Stage A direction, rebuilt with construct_state and hash-checked against
the 04B inventory), re-created with generation = parent generation + 1 (phi hashes unchanged, state_sha256 changes; the mapping is recorded).  Every parameter
comes from the pinned OPT-01 v1 contract.  The pre-CFD gates of E4 run here, once, on the exact bytes: GEOM-02 profile v2 (13 gates, transition from the new
parent, allowed_events=()), P22-v2 N_phi <= 8272 with a positive count-equal margin, and the retained LOWDIM gates (smoothed volume band, clearance).  A failing
state is recorded and the stage is BLOCKED_PRE_CFD.  Contract v1.1 gate scope (plan Amendment 2 F1): for probe states near_zero_gradient_band is report-only (counts and
attribution to the baseline tie plateau are recorded), for the parent every gate is hard.  Refuses to overwrite; --supersede-blocked replaces only the registered
BLOCKED inventory of commit 576441c (hash-checked, recorded in `supersedes`); --check re-derives (runtime fields excluded).
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
import evaluate_opt01_v1_states as E1  # noqa: E402
import geom02_canonical as canon  # noqa: E402
import opt01a_states as L  # noqa: E402
import register_geom02_profile as reg  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.geometry_gates_v2 import _zero_level_gradient  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/opt01a_stage_a_2026_10_15"
B04 = ROOT / "docs/evidence/lowdim04b_stage_b_2026_10_13"
A04 = ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13"
PARENT_RAW, PARENT_NPZ = EVIDENCE / "inputs/parent.phi_f4_fortran.raw", EVIDENCE / "inputs/opt01_v1_parent.npz"
TRIAL_ROW, LOWDIM04B_PARENT_ROW = "lowdim04b__prop__s0.3125mm", "lowdim04b__parent"
TRIAL_STEP_MM = 0.3125
SOLVER_WALL_TIME_CAP_S = 9 * 900  # as LOWDIM-04A: nine states x the 900 s per-state timeout
IDENTITY_KEYS = ("state_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256")
sha = b4a.sha
BLOCKED_INVENTORY = {"commit": "576441ce95a8b209e1a9b16fadbceb55f819ea75", "sha256": "52f4b1d6b513c06e8a6ff29af418226043297b5093453c43267939126a2c53cd", "stage_status": "BLOCKED_PRE_CFD"}
PLATEAU_ABS_PHI_M = 1e-6  # the v17 genesis tie plateau: baseline |phi| below this (STL faces on lattice planes; SRCMAP-03a)


def verify_pins(contract: dict) -> int:
    """Every {path, sha256 | sha256_fortran_raw} pin of the contract (and its plan) must match the file now on disk."""
    n = 0

    def walk(x):
        nonlocal n
        if isinstance(x, dict):
            digest = x.get("sha256", x.get("sha256_fortran_raw"))
            if isinstance(x.get("path"), str) and isinstance(digest, str) and len(digest) == 64:
                if sha(ROOT / x["path"]) != digest:
                    raise ValueError(f"contract pin differs from the file: {x['path']}")
                n += 1
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(contract)
    return n


@functools.cache
def context() -> SimpleNamespace:
    contract = L.CONTRACT
    verify_pins(contract)
    pins = contract["pins"]
    profile = json.loads((ROOT / pins["gate_profile_v2"]["path"]).read_text())
    policy = SDFTopologyPolicyResearchV2.from_dict(json.loads((ROOT / pins["resolved_research_policy"]["path"]).read_text())["policy"])
    inv04b = json.loads((ROOT / pins["lowdim04b_inventory"]["path"]).read_text())
    baseline, lowdim03 = SDFDesignState.load(b4a.BASELINE_NPZ), SDFDesignState.load(b4a.PARENT_NPZ)
    if sha(b4a.PARENT_NPZ) != b4a.PARENT_NPZ_SHA or sha(b4a.BASELINE_NPZ) != canon.BASELINE_NPZ_SHA:
        raise ValueError("retained baseline/LOWDIM-03 parent NPZ differs from the registered one")
    direction_path = ROOT / inv04b["proposal"]["file"]
    if sha(direction_path) != inv04b["proposal"]["sha256_fortran_raw"]:
        raise ValueError("robust Stage A direction hash differs from the 04B inventory")
    trial, _ = construct_state(lowdim03, S.read_f4(direction_path), TRIAL_STEP_MM, 1)
    row = next(r for r in inv04b["states"] if r["name"] == TRIAL_ROW)
    if any(state_identity(trial)[k] != row[k] for k in IDENTITY_KEYS):
        raise ValueError("the reconstructed LOWDIM-04B selected state differs from the 04B inventory")
    parent = SDFDesignState.create(
        phi=trial.phi, origin_m=trial.origin_m, spacing_m=trial.spacing_m, design_mask=trial.design_mask, fixed_solid_mask=trial.fixed_solid_mask,
        forbidden_mask=trial.forbidden_mask, root_mask=trial.root_mask, narrow_band_width_m=trial.narrow_band_width_m, generation=trial.generation + 1,
        source_sha256=trial.source_sha256, topology_policy_id=trial.topology_policy_id, reinitialization_policy_id=trial.reinitialization_policy_id)
    directions = {n: S.read_f4(ROOT / d["path"]) for n, d in pins["basis_raw_files"].items()}
    states = {}
    for item in L.plan():
        if item["kind"] == "parent":
            states[item["name"]] = (parent, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": state_identity(parent)["margin_m"]})
        else:
            child, audit = construct_state(parent, directions[item["direction"]], item["step_mm"], item["sign"])
            if S.to_raw(child.phi) != S.to_raw(S.perturb(parent.phi, directions[item["direction"]], item["step_mm"], item["sign"])):
                raise ValueError("host and runner perturbation bytes differ")
            states[item["name"]] = (child, audit)
    return SimpleNamespace(contract=contract, profile=profile, policy=policy, inv04b=inv04b, baseline=baseline, lowdim03=lowdim03, trial=trial, parent=parent, trial_row=row,
                           directions=directions, states=states, base_geometry=lowdim.geometry(baseline))


def plateau_attribution(child_phi, base_phi, spacing_m: float, threshold: float) -> dict:
    """Which crossing-slope-failing nodes of a state are baseline tie-plateau nodes (|phi_baseline| < 1e-6).  Descriptive; re-derives the gate's failing set (cross-checked by the caller)."""
    z = _zero_level_gradient(SimpleNamespace(phi=child_phi, shape=child_phi.shape, spacing_m=spacing_m))
    base = np.abs(base_phi.astype(np.float64)) < PLATEAU_ABS_PHI_M
    out = {"failing_nodes": 0, "on_baseline_tie_plateau": 0, "off_plateau": 0, "baseline_plateau_nodes": int(base.sum()), "plateau_abs_phi_m": PLATEAU_ABS_PHI_M}
    if z is None or "norm" not in z:
        return out
    nodes, phi = z["nodes"], z["phi"]
    solid, slope = phi < 0.0, np.zeros(phi.shape)
    for axis in range(3):
        for shift in (1, -1):
            slope = np.maximum(slope, np.where(np.roll(solid, shift, axis=axis) != solid, np.abs(phi - np.roll(phi, shift, axis=axis)) / spacing_m, 0.0))
    bad = nodes & (slope < threshold)
    return {**out, "failing_nodes": int(bad.sum()), "on_baseline_tie_plateau": int((bad & base).sum()), "off_plateau": int((bad & ~base).sum())}


def gate_job(name: str) -> dict:
    """The heavy part (r=8 export, self-intersection): one state, run once here and never in the kernel."""
    ctx = context()
    child, _ = ctx.states[name]
    export = canon.export_from_state(child, ctx.profile)
    out = {"record": canon.strip_runtime(E1.state_record(child, ctx.parent, ctx.profile, ctx.policy, export, ctx.base_geometry))}
    out["plateau"] = plateau_attribution(child.phi, ctx.baseline.phi, float(child.spacing_m), float(ctx.profile["near_zero_gradient_band"]["threshold"]))
    if out["plateau"]["failing_nodes"] != out["record"]["geom02_v2"]["gates"]["near_zero_gradient_band"]["measured"].get("nodes_below_threshold", 0):
        raise ValueError(f"{name}: the plateau attribution does not re-derive the gate's failing node count")
    if name == L.PARENT_NAME:  # the E4 stop rule: the parent's transition from its own parent (the LOWDIM-03 parent)
        out["e4_vs_lowdim03_parent"] = canon.strip_runtime(E1.state_record(child, ctx.lowdim03, ctx.profile, ctx.policy, export, ctx.base_geometry))
    return out


def gate_table(rec: dict, margin: float) -> dict:
    return {**{g: v["status"] for g, v in rec["geom02_v2"]["gates"].items()}, "p22_v2": "pass" if rec["p22_v2"]["pass"] else "fail",
            **{f"retained_{g}": "pass" if ok else "fail" for g, ok in rec["retained_lowdim"]["gates"].items()}, "count_equal_margin_positive": "pass" if margin > 0 else "fail"}


def build(jobs: int = 3, gate_results: dict | None = None):
    ctx = context()
    if gate_results is None:
        names = [r["name"] for r in L.plan()]
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            gate_results = dict(zip(names, pool.map(gate_job, names)))
    parent_ident, trial_ident = state_identity(ctx.parent), state_identity(ctx.trial)
    if any(parent_ident[k] != trial_ident[k] for k in IDENTITY_KEYS[1:]) or parent_ident["state_sha256"] == trial_ident["state_sha256"]:
        raise ValueError("the generation bump must change only state_sha256")
    parent_v = {"v_cont_m3": b4a.continuum_zero_set_volume_m3(ctx.parent.phi, ctx.parent.spacing_m), "v_eps_m3": lowdim.geometry(ctx.parent)["smoothed_volume_m3"]}
    rows, seen, blockers = [], set(), []
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
        table = gate_table(rec, margin)
        failed = L.hard_failures(item["kind"], table)
        reported = sorted(g for g, v in table.items() if v != "pass" and g not in failed)
        if failed:
            blockers.append({"state": item["name"], "failed": failed})
        geo, v_cont = lowdim.geometry(child), b4a.continuum_zero_set_volume_m3(child.phi, child.spacing_m)
        pre_cfd = {"all_pass": not failed, "failed": failed, "report_only_failed": reported, "near_zero_gradient_band": gate_results[item["name"]]["plateau"], "table": table, "geom02_v2_pass_count": sum(v == "pass" for v in (s["status"] for s in rec["geom02_v2"]["gates"].values())),
                   "geom02_v2_gate_count": len(rec["geom02_v2"]["gates"]), "record": rec}
        if "e4_vs_lowdim03_parent" in gate_results[item["name"]]:
            e4 = gate_results[item["name"]]["e4_vs_lowdim03_parent"]
            pre_cfd["e4_vs_lowdim03_parent"] = {"all_pass": e4["all_pass"], "geom02_v2_verdict": e4["geom02_v2"]["verdict"]}
            if not e4["all_pass"]:
                blockers.append({"state": item["name"], "failed": ["e4_stop_rule_vs_lowdim03_parent"]})
        rows.append({**item, **{k: ident[k] for k in IDENTITY_KEYS}, "npz_sha256": npz_sha, "changed_node_count": int(audit["changed_node_count"]),
                     "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]), "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": 1e-6,
                     "geometry": geo, "pre_cfd_gates": pre_cfd,
                     "hard_count": {"sampled_solid_centers": V2.MAX_SOLID_CENTERS + residual, "residual_vs_n_max": residual, **inv},
                     "volume": {"v_eps_m3": geo["smoothed_volume_m3"], "v_cont_m3": v_cont, "v_eps_vs_parent": geo["smoothed_volume_m3"] / parent_v["v_eps_m3"] - 1.0,
                                "v_cont_vs_parent": v_cont / parent_v["v_cont_m3"] - 1.0, "sharp_volume_m3": geo["sharp_volume_m3"]}})
    pins = ctx.contract["pins"]
    analysis04b = json.loads((B04 / "lowdim04b_analysis.json").read_text())
    grids = {}
    for kernel, case in (("a", "flow_24"), ("b", "flow_32")):
        grid = pins["dual_grid_kernels"][case]
        measurement = copy.deepcopy(grid["measurement"])
        measurement.update({"solver_wall_time_cap_s": SOLVER_WALL_TIME_CAP_S, "qualification_claim": "bounded OPT-01 v1 Stage A local dual-grid model evidence; no qualification"})
        csv_rel = str((B04 / f"kernel_output/lowdim04b_{kernel}/states/{TRIAL_ROW}/{case}.forces.csv").relative_to(ROOT))
        retained = analysis04b["state_forces_n"][case][TRIAL_ROW]
        host = recompute_force_n(ROOT / csv_rel, {"measurement": measurement})
        if grid["kernel"] != kernel or retained["forces_csv_sha256"] != sha(ROOT / csv_rel) or any(abs(host[f"{q}_n"] - retained[f"{q}_n"]) > 1e-12 * abs(retained[f"{q}_n"]) for q in ("drag", "downforce")):
            raise ValueError(f"{case} parent reference CSV differs from the retained LOWDIM-04B analysis")
        grids[kernel] = {"case_id": case, "job": grid["job"]["path"], "measurement": measurement,
                         "baseline_reference": {"forces_csv_path": csv_rel, "forces_csv_sha256": sha(ROOT / csv_rel), "role": "retained LOWDIM-04B prop s0.3125 mm run of the identical phi bytes (the new parent)",
                                                "host_recomputed_n": {q: host[f"{q}_n"] for q in ("drag", "downforce")}, "force_scale_n_per_solver_force": host["force_scale_n_per_solver_force"]}}
    a04 = json.loads((A04 / "lowdim04a_analysis.json").read_text())
    inv04b = ctx.inv04b
    inventory = {"kind": "opt01a_stage_a_inventory", "contract": {"path": L.CONTRACT_REL, "sha256": L.CONTRACT_SHA256, "contract_id": ctx.contract["contract_id"], "pins_verified": verify_pins(ctx.contract)},
                 "stage_status": "BLOCKED_PRE_CFD" if blockers else "READY", "blockers": blockers,
                 "gate_scope": ctx.contract["D3_update"]["gate_scope"], "supersedes": BLOCKED_INVENTORY, "basis_order": list(L.BASIS), "step_mm": L.STEP_MM,
                 "parent": {"state_sha256": parent_ident["state_sha256"], "phi_fortran_order_sha256": parent_ident["phi_fortran_order_sha256"], "phi_c_order_sha256": parent_ident["phi_c_order_sha256"],
                            "generation": ctx.parent.generation, "npz_path": str(PARENT_NPZ.relative_to(ROOT)), "raw_path": str(PARENT_RAW.relative_to(ROOT)),
                            "lineage": {"lowdim04b_selected_state": {**{k: trial_ident[k] for k in IDENTITY_KEYS}, "generation": ctx.trial.generation, "inventory_row": TRIAL_ROW,
                                                                   "inventory_path": pins["lowdim04b_inventory"]["path"], "inventory_sha256": pins["lowdim04b_inventory"]["sha256"]},
                                        "lowdim03_parent_npz_sha256": b4a.PARENT_NPZ_SHA, "robust_stage_a_direction_sha256": inv04b["proposal"]["sha256_fortran_raw"],
                                        "step_mm": TRIAL_STEP_MM, "sign": 1,
                                        "generation_bump": "construct_state keeps the parent generation; OPT-01 v1 (E4) makes the 04B selected state the parent with generation + 1: "
                                                           "phi hashes unchanged, state_sha256 changes. Children keep the new parent's generation (construct_state semantics)."}},
                 "geometry_gate_base": "canonical v17 baseline (smoothed_volume_band) and the new parent (GEOM-02 transition)", "margin_gate_m": 0.15, "grids": grids,
                 "kernels": {k: [r["name"] for r in rows] for k in grids}, "states": rows, "directions": pins["basis_raw_files"], "job_env_common": pins["job_env_common"],
                 "parent_volume": parent_v, "p22_v2": {"registration_path": pins["p22_v2"]["path"], "registration_sha256": pins["p22_v2"]["sha256"], "n_max": V2.MAX_SOLID_CENTERS,
                                                       "meaning": "lattice count only; constrains no physical or sub-voxel volume"},
                 "prior_robust_proposal": {"coefficient_vector": inv04b["proposal"]["coefficient_vector"], "m_max_abs_sum": inv04b["proposal"]["m_max_abs_sum"],
                                           "sha256_fortran_raw": inv04b["proposal"]["sha256_fortran_raw"]},
                 "lowdim04a_reference": {"analysis_path": str((A04 / "lowdim04a_analysis.json").relative_to(ROOT)), "analysis_sha256": sha(A04 / "lowdim04a_analysis.json"),
                                         "coefficient_vectors_n_per_m": {q: {g: [a04["secants"][g][q][d]["g_sec_n_per_m"] for d in L.BASIS] for g in ("flow_24", "flow_32")} for q in ("downforce", "drag")},
                                         "step_m": 0.00125, "base": "LOWDIM-03 parent (the parent of the 04B selected state)"}}
    return inventory, S.to_raw(ctx.parent.phi), ctx.parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--supersede-blocked", action="store_true", help="replace the registered BLOCKED inventory of commit 576441c (hash-checked) by the v1.1 one")
    args = p.parse_args()
    inv, raw, parent = build(args.jobs)
    data, target = canonical_json(inv), EVIDENCE / "inventory.json"
    with tempfile.TemporaryDirectory() as tmp:
        parent.save(Path(tmp) / "p.npz")
        npz = (Path(tmp) / "p.npz").read_bytes()
    if args.check:
        if target.read_bytes() != data or PARENT_RAW.read_bytes() != raw or PARENT_NPZ.read_bytes() != npz:
            raise SystemExit("frozen inventory/parent inputs differ from their derivation")
    else:
        if target.exists() and (not args.supersede_blocked or sha(target) != BLOCKED_INVENTORY["sha256"]):
            raise SystemExit("refusing to overwrite OPT-01 v1 Stage A inputs (only the registered BLOCKED inventory may be superseded, with --supersede-blocked)")
        if (PARENT_RAW.exists() and PARENT_RAW.read_bytes() != raw) or (PARENT_NPZ.exists() and PARENT_NPZ.read_bytes() != npz):
            raise SystemExit("refusing to overwrite OPT-01 v1 Stage A parent inputs (they must equal the re-derivation)")
        PARENT_RAW.parent.mkdir(parents=True, exist_ok=True)
        PARENT_RAW.write_bytes(raw)
        PARENT_NPZ.write_bytes(npz)
        target.write_bytes(data)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print("inventory", inv["stage_status"], hashlib.sha256(data).hexdigest())
    for b in inv["blockers"]:
        print("BLOCKER", json.dumps(b))
    for r in inv["states"]:
        g = r["pre_cfd_gates"]
        print(r["name"], g["geom02_v2_pass_count"], "/", g["geom02_v2_gate_count"], "hard_failed", g["failed"], "report_only", g["report_only_failed"], "plateau", g["near_zero_gradient_band"], "margin", r["hard_count"]["count_equal_margin_m"])
    if inv["blockers"]:
        raise SystemExit(3)  # registered blocker before CFD: no freeze, no kernel


if __name__ == "__main__":
    main()
