#!/usr/bin/env python3
"""OPT-01 v1 phase 1 (#30): the GEOM-02 profile v2 bundle, P22-v2 and the retained LOWDIM gates on the v17 baseline, the LOWDIM-03 parent and the
LOWDIM-04B selected trial state (reconstructed with construct_state, hash-checked against the 04B inventory).  Solver-free.

Writes docs/evidence/opt01_v1_2026_10_15/opt01_v1_phase1_evaluation.json (+ .sha256) once and refuses to overwrite; ``--check`` re-derives it
(runtime fields excluded).  Includes the E4 precondition verdict for the trial as the next parent, the count-equal margin recomputed at the trial,
and a RETROACTIVE (non-prospective, cannot close #30, E8) D3 conformance statement for the 04B trial from the retained 04B responses.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_lowdim01_inputs as lowdim  # noqa: E402
import build_lowdim04a_inputs as b4a  # noqa: E402
import geom02_canonical as canon  # noqa: E402
import geom02_gradient_floor_diagnostic as diag  # noqa: E402
import register_geom02_profile as reg  # noqa: E402
import register_opt01_v1 as reg1  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.geometry_gates_v2 import evaluate_geometry_gates_v2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402
from cfd_sdf.design.volume_semantics import sampled_solid_centers_count  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity  # noqa: E402
from cfd_sdf.lowdim03_contract import GRIDS, evaluate_candidate  # noqa: E402

ARTIFACT = reg1.OUT / "opt01_v1_phase1_evaluation.json"
TRIAL, STEP_MM = "lowdim04b__prop__s0.3125mm", 0.3125
PARENT_ROW = "lowdim04b__parent"
IDENTITY_KEYS = ("state_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256")
require = canon.require


def retained_gates(state: SDFDesignState, base_geometry: dict) -> dict:
    """LOWDIM gates kept next to GEOM-02 (E6): smoothed volume band vs the v17 baseline and the zero-level clearance margin."""
    g, margin = lowdim.geometry(state), state_identity(state)["margin_m"]
    rel = g["smoothed_volume_m3"] / base_geometry["smoothed_volume_m3"] - 1.0
    gates = {"smoothed_volume_band": abs(rel) <= lowdim.VOLUME_BAND, "clearance": margin >= lowdim.MARGIN_GATE_M}
    return {"relative_smoothed_volume_change": rel, "volume_band": lowdim.VOLUME_BAND, "zero_level_margin_m": margin, "margin_gate_m": lowdim.MARGIN_GATE_M,
            "gates": gates, "all_pass": all(gates.values())}


def state_record(state, parent, profile, policy, export, base_geometry) -> dict:
    bundle = evaluate_geometry_gates_v2(state, parent_state=parent, profile=profile, policy=policy, export_mesh=export)
    count = sampled_solid_centers_count(state)
    p22 = {"sampled_solid_centers": count, "n_max": V2.MAX_SOLID_CENTERS, "pass": count <= V2.MAX_SOLID_CENTERS}
    retained = retained_gates(state, base_geometry)
    return {"geom02_v2": bundle, "p22_v2": p22, "retained_lowdim": retained, "central_gradient_classification": diag.classify(state, profile["zero_level_gradient_floor"]),
            "all_pass": bool(bundle["verdict"]["pass"] and p22["pass"] and retained["all_pass"])}


def retroactive_d3(contract: dict, trial_record: dict, margin_positive: bool) -> dict:
    """D3 conformance of the 04B selected trial using the retained 04B responses.  Descriptive; the 04B acceptance preceded D2/D3."""
    path = reg.EV / "lowdim04b_stage_b_2026_10_13/lowdim04b_analysis.json"
    a = json.loads(path.read_text())
    forces = a["state_forces_n"]
    ev = evaluate_candidate({g: forces[g][PARENT_ROW] for g in GRIDS}, {g: forces[g][TRIAL] for g in GRIDS}, trial_record["all_pass"])
    ladder = contract["D3_update"]["ladder"]
    checks = {
        "04b_integrity_pass_and_verdict_accept": bool(a["integrity"]["pass"] is True and a["verdict"] == "LOWDIM04B_ACCEPT"),
        "ladder_and_reverse_steps_equal_contract": [a["frozen_parameters"]["steps_mm"], a["frozen_parameters"]["control_steps_mm"]] == [ladder["steps_mm"], ladder["reverse_diagnostics_mm"]],
        "trial_passes_geom02_v2_p22_and_retained_gates": trial_record["all_pass"],
        "dual_grid_accept_rule_recomputed": ev["accepted"],
        "recomputed_equals_retained_04b_evaluation": all(ev["per_grid"][g][k] == a["candidates"][TRIAL]["per_grid"][g][k] for g in GRIDS for k in ev["per_grid"][g]),
        "selected_equals_trial": a["selected"] == TRIAL,
        "only_04b_accepted_step_is_the_trial": [n for n, c in a["candidates"].items() if c["accepted"]] == [TRIAL],
        "count_equal_margin_positive_at_trial": margin_positive,
    }
    return {
        "label": "RETROACTIVE (non-prospective): the 04B acceptance was decided before D2/D3 existed",
        "analysis": reg1.pin(path.relative_to(ROOT)), "per_grid": ev["per_grid"], "worst_grid_downforce_gain_n": ev["worst_grid_downforce_gain_n"],
        "flow_32_drag_small_flag": ev["per_grid"]["flow_32"]["small_computed_drag_margin"], "checks": checks, "conforms": all(checks.values()),
        "scope": "gates were recomputed only at the selected trial; the other ladder steps were accepted by no one in 04B, so adding gates cannot add an acceptance and D3 selection equals the 04B selection iff the trial passes",
        "statement": "RETROACTIVE conformance of the LOWDIM-04B selected trial (0.3125 mm) to the OPT-01 v1 D3 contract, from retained 04B responses: "
                     + ("it conforms. " if all(checks.values()) else "it does NOT conform on: " + ", ".join(k for k, v in checks.items() if not v) + ". ")
                     + "This only shows the contract is satisfiable; it is non-prospective (acceptance preceded the contract, the gain is at the noise floor and biased upward) "
                       "and cannot close #30 (plan E5/E8).",
    }


def derive() -> dict:
    profile_v2, contract = reg1.build()
    for path, obj in ((reg1.PROFILE, profile_v2), (reg1.CONTRACT, contract)):
        require(path.read_text() == reg.dump(obj) and path.with_name(path.name + ".sha256").read_text().split()[0] == reg.sha_file(path), f"{path.name} not registered or does not re-derive")
    pins = contract["pins"]
    require(reg.sha_file(reg1.PROFILE) == pins["gate_profile_v2"]["sha256"], "profile v2 pin")
    require(reg.sha_file(ROOT / pins["gate_code"]["path"]) == pins["gate_code"]["sha256"], "gate code differs from the contract pin")
    require(reg.sha_file(reg.POLICY) == pins["resolved_research_policy"]["sha256"] == canon.POLICY_SHA256, "policy pin")
    profile = json.loads(reg1.PROFILE.read_text())
    policy = SDFTopologyPolicyResearchV2.from_dict(json.loads(reg.POLICY.read_text())["policy"])
    baseline, parent = (SDFDesignState.load(canon.INPUTS / n) for n in ("v17_baseline.npz", "lowdim03_parent.npz"))
    require(reg.sha_file(canon.INPUTS / "v17_baseline.npz") == canon.BASELINE_NPZ_SHA and reg.sha_file(canon.INPUTS / "lowdim03_parent.npz") == canon.PARENT_NPZ_SHA, "input npz hashes")
    inv = json.loads((reg1.B04 / "inventory.json").read_text())
    require(reg.sha_file(reg1.B04 / "inventory.json") == pins["lowdim04b_inventory"]["sha256"], "04B inventory pin")
    direction_path = ROOT / inv["proposal"]["file"]
    require(reg.sha_file(direction_path) == inv["proposal"]["sha256_fortran_raw"], "robust Stage A direction hash")
    trial, audit = construct_state(parent, S.read_f4(direction_path), STEP_MM, 1)
    row = next(r for r in inv["states"] if r["name"] == TRIAL)
    ident, parent_ident = state_identity(trial), state_identity(parent)
    require(all(ident[k] == row[k] for k in IDENTITY_KEYS), "trial identity differs from the 04B inventory")
    prow = next(r for r in inv["states"] if r["name"] == PARENT_ROW)
    require(all(parent_ident[k] == prow[k] for k in IDENTITY_KEYS), "parent identity differs from the 04B inventory")
    with tempfile.TemporaryDirectory() as tmp:
        trial.save(Path(tmp) / "t.npz")
        npz_match = reg.sha_file(Path(tmp) / "t.npz") == row["npz_sha256"]

    states = {"baseline": (baseline, baseline), "lowdim03_parent": (parent, baseline), "lowdim04b_trial": (trial, parent)}
    base_geometry = lowdim.geometry(baseline)
    records = {n: state_record(s, p, profile, policy, canon.export_from_state(s, profile), base_geometry) for n, (s, p) in states.items()}

    prior = json.loads((reg.OUT / "geom02_gate_artifact.json").read_text())["states"]
    def comparable(gates):  # the #29 baseline export was oriented twice (orientation_flips 0, same mesh); here once (1): not compared
        out = {k: v for k, v in canon.strip_runtime(gates).items() if k != "near_zero_gradient_band"}
        out["export_surface_integrity"] = {**out["export_surface_integrity"], "measured": {k: v for k, v in out["export_surface_integrity"]["measured"].items() if k != "orientation_flips"}}
        return out

    for n in ("baseline", "lowdim03_parent"):  # only the near-zero gate may differ from the registered #29 artifact
        require(comparable(records[n]["geom02_v2"]["gates"]) == comparable(prior[n]["gates"]), f"{n}: gates other than near_zero_gradient_band differ from the #29 artifact")

    trial_margin, step_margin = b4a.invariance(trial.phi, trial.phi), b4a.invariance(parent.phi, trial.phi)
    margin = trial_margin["count_equal_margin_m"]
    ladder_mm = contract["D3_update"]["ladder"]["steps_mm"]
    precondition = records["lowdim04b_trial"]["all_pass"]
    table = {n: {**{g: v["status"] for g, v in r["geom02_v2"]["gates"].items()}, "p22_v2": "pass" if r["p22_v2"]["pass"] else "fail",
                 **{f"retained_{g}": "pass" if ok else "fail" for g, ok in r["retained_lowdim"]["gates"].items()}} for n, r in records.items()}
    return {
        "kind": "opt01_v1_phase1_evaluation", "evidence_class": "contract_and_capability", "contract_id": contract["contract_id"],
        "inputs": {"gate_profile_v2_sha256": reg.sha_file(reg1.PROFILE), "contract_sha256": reg.sha_file(reg1.CONTRACT), "policy_sha256": canon.POLICY_SHA256,
                   "v17_baseline_npz_sha256": canon.BASELINE_NPZ_SHA, "lowdim03_parent_npz_sha256": canon.PARENT_NPZ_SHA, "robust_stage_a_direction_sha256": inv["proposal"]["sha256_fortran_raw"]},
        "trial_reconstruction": {"parent": PARENT_ROW, "step_mm": STEP_MM, "sign": 1, "identity": {k: ident[k] for k in IDENTITY_KEYS}, "identity_matches_04b_inventory": True,
                                 "npz_sha256_matches_04b_inventory": npz_match, "construct_state_audit": audit, "generation": trial.generation,
                                 "note": "construct_state keeps the parent generation; the E4 generation = parent + 1 is applied when step 3 builds its own parent"},
        "table": table, "states": records,
        "e4_precondition": {"trial_as_next_parent_passes": precondition, "rule": "all GEOM-02 v2 gates + P22-v2 + retained LOWDIM gates; transition from the LOWDIM-03 parent",
                            "failed_geom02": records["lowdim04b_trial"]["geom02_v2"]["verdict"]["failed"], "unmeasured_geom02": records["lowdim04b_trial"]["geom02_v2"]["verdict"]["unmeasured"],
                            "step3_may_start": precondition and margin > 0},
        "count_equal_margin": {"at_trial_state_m": margin, "at_trial_detail": trial_margin, "trial_vs_lowdim03_parent_m": step_margin["count_equal_margin_m"],
                               "reference": "build_lowdim04a_inputs.invariance (max-norm: a step of sup |dphi| below the margin keeps the sign pattern, hence N_phi)",
                               "ladder_steps_below_margin": {f"{s:g}": s / 1000.0 < margin for s in ladder_mm}},
        "retroactive_d3_conformance": retroactive_d3(contract, records["lowdim04b_trial"], margin > 0),
        "flags": reg.FLAGS, "claims_not_supported": contract["claims_not_supported"], "solver_started": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    if ap.parse_args().check:
        require(ARTIFACT.with_name(ARTIFACT.name + ".sha256").read_text().split()[0] == reg.sha_file(ARTIFACT), "artifact sidecar")
        require(canon.strip_runtime(json.loads(reg.dump(derive()))) == canon.strip_runtime(json.loads(ARTIFACT.read_text())), "artifact does not re-derive")
        print("check ok", reg.sha_file(ARTIFACT))
        return
    artifact = derive()
    print(reg.write_once(ARTIFACT, artifact))
    print(json.dumps(artifact["table"], indent=1))
    for k in ("e4_precondition", "count_equal_margin"):
        print(k, json.dumps({a: b for a, b in artifact[k].items() if a != "at_trial_detail"}))
    print(artifact["retroactive_d3_conformance"]["statement"])


if __name__ == "__main__":
    main()
