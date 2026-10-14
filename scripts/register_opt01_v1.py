#!/usr/bin/env python3
"""Register OPT-01 v1 (#30, #25) phase 1: the GEOM-02 gate profile v2 (crossing-slope rule) and the update contract.  Solver-free.

Plan: docs/opt01_v1_plan_2026_10_15.md with Amendment 1 (E1-E8 override D1-D3).  Writes docs/evidence/opt01_v1_2026_10_15/
{geom02_gate_profile_v2,opt01_v1_contract}.json (+ .sha256) once and refuses to overwrite; ``--check`` re-derives both.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import register_geom02_profile as reg  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402

OUT = reg.EV / "opt01_v1_2026_10_15"
PROFILE, CONTRACT = OUT / "geom02_gate_profile_v2.json", OUT / "opt01_v1_contract.json"
V1_PROFILE_SHA256 = "af3d74c883e4071904483a8d365d1a9bb9206717c49c0bf429da5867cd0f9f9d"
POLICY_SHA256 = "b5bcc8c742cb9c09988a80b7e42374c7d7f9bdfccce5c5acb8713cc9204375c8"
PLAN = "docs/opt01_v1_plan_2026_10_15.md"
A04, B04 = reg.EV / "lowdim04a_stage_a_2026_10_13", reg.EV / "lowdim04b_stage_b_2026_10_13"
V2_REGISTRATION = reg.EV / "sdf_native_volume_semantics_v2_2026_10.json"
CONE_CODE = {  # path -> the LOWDIM freeze whose file_hashes must still agree (the code that produced the 04A/04B results)
    "src/cfd_sdf/grid01_contract.py": A04, "scripts/lowdim04a_contract.py": A04, "src/cfd_sdf/lowdim03_contract.py": B04, "scripts/lowdim04b_contract.py": B04,
}
AUTHORITY = ("user words of 2026-10-13 「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」, read as an interpretation, not a #30/#25-specific grant; "
             "a later explicit user decision supersedes it")
SUPERSEDED = ['#30 (OPT-01) still depends on #25 and #26 to #29: there is no separate "first accepted update" gate before them, and the LOWDIM-03/04 parent remains an experimental state under false flags.',
              "No further LOWDIM cycle is planned (exit rule recorded in the LOWDIM-04 Stage B entry)."]  # docs/phase_plan.md (2026-10-14/15), verbatim; the second is amended by E3


def pin(path) -> dict:
    p = ROOT / path
    return {"path": str(path), "sha256": reg.sha_file(p)}


def load(path) -> dict:
    return json.loads(Path(path).read_text())


def build_profile() -> dict:
    if reg.sha_file(reg.PROFILE) != V1_PROFILE_SHA256:
        raise SystemExit("GEOM-02 profile v1 hash changed")
    profile = load(reg.PROFILE)
    profile["profile_id"] = "geom02_v17_research_gates_v2_crossing_slope_2026_10_15"
    profile["near_zero_gradient_band"] = {
        "rule": "crossing_slope_v1", "threshold": 0.5,
        "text": "at every interior sign-change node (exact zero = fluid) the largest crossing slope |phi(n)-phi(m)|/h over 6-neighbours m of the opposite sign is >= threshold; "
                "array-boundary sign-change nodes are unmeasured; central-difference counts (zero_level_gradient_floor) are reported, not gated",
        "bound": "zero-set shift per unit dphi along the crossing edge is at most 2 dphi (0.625 mm for a 0.3125 mm step)",
    }
    profile["predecessor_profile"] = {"path": str(reg.PROFILE.relative_to(ROOT)), "sha256": V1_PROFILE_SHA256, "difference": "profile_id, near_zero_gradient_band, predecessor_profile, non_blind_v2; all other fields identical"}
    profile["non_blind_v2"] = ("crossing-slope failing/interior sign-change nodes measured before registration (plan Amendment 1, E1): baseline 567/9,390, LOWDIM-03 parent 7/8,062, "
                               "LOWDIM-04B 0.3125 mm trial 0/8,038; the rule was chosen after the #29 diagnostic (non-blind). A future normal-velocity backend must re-register the central rule as hard")
    return profile


def build_contract(profile_sha: str) -> dict:
    inv_a, inv_b = load(A04 / "inventory.json"), load(B04 / "inventory.json")
    if inv_a["directions"] != inv_b["directions"] or inv_a["basis_order"] != inv_b["basis_order"]:
        raise SystemExit("LOWDIM-04A and 04B basis inventories differ")
    for rel, freeze in CONE_CODE.items():
        if load(freeze / "prerun_freeze.json")["file_hashes"].get(rel) != reg.sha_file(ROOT / rel):
            raise SystemExit(f"{rel} differs from its LOWDIM prerun freeze")
    if load(B04 / "inventory.json")["p22_v2"]["registration_sha256"] != reg.sha_file(V2_REGISTRATION):
        raise SystemExit("P22-v2 registration hash differs from the 04B inventory")
    grids = {g["case_id"]: {"kernel": k, "job": pin(g["job"]), "measurement": g["measurement"]} for k, g in inv_b["grids"].items()}
    return {
        "kind": "opt01_v1_update_contract", "schema_version": 1, "contract_id": "opt01_v1_phi_space_dual_grid_update_2026_10_15",
        "evidence_class": "contract", "immutable": True,
        "plan": {**pin(PLAN), "amendment": "Amendment 1 (E1-E8) overrides D1-D3 and Steps"},
        "authority": AUTHORITY,
        "D1_backend": {
            "text": "The first OPT-01 step's update direction is the LOWDIM-04 L1-robust cone solution on dual-grid centered phi-space secants (+-1.25 mm) of the frozen 4-direction basis "
                    "(D0, D1, D2, P1; hand-picked, not rule-selected): a subspace step, cost 2k+1 runs per grid. The 8-direction cap is a budget, not a justification.",
            "supersedes": {"document": "docs/phase_plan.md", "sentences": SUPERSEDED, "scope": "OPT-01 v1 only; #25 stays open for any high-dimensional backend, FD stays verification-only beyond 8 directions"},
            "no_gradient_claim": "secants are finite-step responses, not derivatives; sdf_gradient_qualified stays false; #23, #24, #25 stay open",
            "open_questions": ["secants vs derivatives", "behaviour outside span(4)", "the negative even parts of unknown cause"],
        },
        "D3_update": {
            "objective": "downforce change on both grids (flow_24, flow_32)",
            "constraints": {
                "drag": "computed drag change <= 0 on both grids; flow_32 changes under 3e-5 N flagged 'small'",
                "p22_v2": f"N_phi <= {V2.MAX_SOLID_CENTERS}, held by sign-pattern invariance; the count-equal margin is recomputed at each parent and every step must stay inside it",
                "geom02_gate_profile_v2": "all 13 gates hard (allowed_events = (), no reinitialization)",
                "retained_lowdim_gates": {"smoothed_volume_band": "|V_eps/V_eps(v17 baseline) - 1| <= 0.10", "clearance": "zero_level_margin_m >= 0.15"},
            },
            "direction": "L1-robust cone solver (code hashes pinned) on dual-grid centered secants at +-1.25 mm over the pinned basis",
            "secant_step_mm": 1.25,
            "ladder": {"fractions_of_secant_step": [0.25, 0.5, 0.75, 1.0], "steps_mm": [0.3125, 0.625, 0.9375, 1.25], "sign": 1,
                       "reverse_diagnostics_mm": [0.625, 1.25], "reverse_role": "diagnostic only, never accepted or selected"},
            "accept": "strictly more than 3e-5 N downforce gain and drag change <= 0 on both grids, plus every gate above",
            "selection": "largest minimum-over-grids downforce gain among accepted steps; exact ties to the smaller step",
            "lineage": "parent state hash, direction hash and the contract hashes; rollback = keep the parent",
        },
        "preconditions_E4": {
            "new_parent": "the LOWDIM-04B selected state, reconstructed with construct_state from the pinned parent, direction, step 0.3125 mm, sign +1 and hash-checked against the 04B inventory; generation = parent + 1",
            "stop_rule": "step 3 starts only if this parent passes GEOM-02 profile v2 (all gates, transition from its own parent), P22-v2 and the retained LOWDIM gates",
            "gate_order": "gates on every Stage A/B candidate run before CFD; a candidate failing a gate is excluded with the reason recorded; a gate failure on a ladder step is a REJECT of that step, not a dropped step",
            "lowdim_scripts": "frozen: reuse by copy-adapt into new modules, never edits; every existing freeze --verify must keep holding",
        },
        "done_E5": {
            "closes_30": "ACCEPT or REJECT of an actual-primal trial run on both grids with complete integrity",
            "does_not_close_30": ["NO_DIRECTION (no cone solution)", "retroactive conformance of the 04B trial (E8)", "any incomplete or integrity-failed run"],
            "unambiguous": "integrity-complete and rule-computed, not noise-resolved (flow_24 floor 3e-5 N is about 1 sigma; flow_32 drag sign is jitter-prone)",
        },
        "pins": {
            "gate_profile_v2": {"path": str(PROFILE.relative_to(ROOT)), "sha256": profile_sha},
            "gate_profile_v1": {"path": str(reg.PROFILE.relative_to(ROOT)), "sha256": V1_PROFILE_SHA256},
            "resolved_research_policy": {"path": str(reg.POLICY.relative_to(ROOT)), "sha256": POLICY_SHA256},
            "p22_v2": {**pin(V2_REGISTRATION.relative_to(ROOT)), "n_max": V2.MAX_SOLID_CENTERS, "code": pin("src/cfd_sdf/design/volume_semantics_v2.py"),
                       "registration_record": pin("docs/evidence/p22_v2_registration_2026_10_13/decision_record.md")},
            "cone_solver_code": {rel: pin(rel) for rel in CONE_CODE},
            "gate_code": pin("src/cfd_sdf/design/geometry_gates_v2.py"),
            "basis_raw_files": inv_a["directions"], "basis_order": inv_a["basis_order"],
            "lowdim04a_inventory": pin((A04 / "inventory.json").relative_to(ROOT)), "lowdim04b_inventory": pin((B04 / "inventory.json").relative_to(ROOT)),
            "dual_grid_kernels": grids, "job_env_common": inv_b["job_env_common"],
        },
        "floors": {"min_downforce_gain_n": 3e-5, "small_drag_margin_n": 3e-5, "min_resolved_n": 3e-5, "l1_epsilon_n_per_m": 3e-5 / (2.0 * 0.00125),
                   "label": "nominal floor, about 1 sigma of the retained flow_32 jitter, not a noise measurement"},
        "diagnostics": {"ladder_and_reverse": "retained for every trial, descriptive", "reverse_controls": "diagnostic only"},
        "flags": reg.FLAGS, "flag_changes": "none; 'accepted' is a record-level status of the trial only (E7)",
        "claims_not_supported": reg.NOT_SUPPORTED + ["a qualified gradient", "physical or Stage V downforce gain", "optimizer convergence", "multi-step behaviour"],
        "solver_started": False,
    }


def build() -> tuple[dict, dict]:
    profile = build_profile()
    return profile, build_contract(hashlib.sha256(reg.dump(profile).encode()).hexdigest())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    profile, contract = build()
    if ap.parse_args().check:
        for path, obj in ((PROFILE, profile), (CONTRACT, contract)):
            side = path.with_name(path.name + ".sha256").read_text().split()[0]
            if path.read_text() != reg.dump(obj) or side != reg.sha_file(path):
                raise SystemExit(f"check failed: {path}")
        print("check ok", reg.sha_file(PROFILE), reg.sha_file(CONTRACT))
        return
    print("profile v2", reg.write_once(PROFILE, profile))
    print("contract", reg.write_once(CONTRACT, contract))


if __name__ == "__main__":
    main()
