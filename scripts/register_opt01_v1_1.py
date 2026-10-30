#!/usr/bin/env python3
"""Register the OPT-01 v1.1 update contract (#30, #25): the v1 contract with the plan Amendment 2 (F1-F3) gate scope.  Solver-free.

Everything is v1 (`register_opt01_v1.build`, history kept) except: probe states run the crossing-slope gate report-only, proposal states keep it hard.
Writes docs/evidence/opt01_v1_2026_10_15/opt01_v1_1_contract.json (+ .sha256) once, refuses to overwrite; ``--check`` re-derives it (and v1 still re-derives).
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import register_opt01_v1 as v1  # noqa: E402

reg = v1.reg
CONTRACT = v1.OUT / "opt01_v1_1_contract.json"
V1_CONTRACT_SHA256 = "f76a09c79cea70ffd07d94994d5b075dc346ddf32c678a18b4fab49ab90643e2"
REPORT_ONLY_FOR_PROBES = ["near_zero_gradient_band"]
GATE_SCOPE = {
    "probe": {"states": "secant probe states (Stage A +-1.25 mm perturbations): measurement points, never proposed or accepted",
              "report_only": REPORT_ONLY_FOR_PROBES,
              "hard_before_cfd": "the other twelve GEOM-02 profile v2 gates, P22-v2 (N_phi <= 8272 with a positive count-equal margin), the retained LOWDIM gates, allowed_events = ()"},
    "proposal": {"states": "the parent and every Stage B ladder step (proposed or accepted states)",
                 "hard_before_cfd": "the full bundle: all thirteen GEOM-02 profile v2 gates including the crossing-slope near_zero_gradient_band, P22-v2, the retained LOWDIM gates",
                 "ladder_step_failure": "a ladder step failing any hard gate (including crossing-slope) is a REJECT of that step (E4/E5 unchanged)"},
    "reported_for_probes": "near_zero_gradient_band failing-node counts with their attribution to the baseline |phi| < 1e-6 tie plateau",
    "source": "plan Amendment 2 F1-F3",
}


def build() -> dict:
    profile, c1 = v1.build()
    contract = copy.deepcopy(c1)
    if v1.reg.sha_file(v1.CONTRACT) != V1_CONTRACT_SHA256 or v1.reg.dump(c1) != v1.CONTRACT.read_text():
        raise SystemExit("the registered v1 contract changed or does not re-derive")
    contract.update(contract_id="opt01_v1_1_phi_space_dual_grid_update_2026_10_15", version="1.1")
    contract["plan"] = {**v1.pin(v1.PLAN), "amendment": "Amendment 1 (E1-E8) overrides D1-D3 and Steps; Amendment 2 (F1-F3) sets the gate scope (this contract v1.1)"}
    contract["predecessor_contract"] = {"path": str(v1.CONTRACT.relative_to(ROOT)), "sha256": V1_CONTRACT_SHA256, "difference": "contract_id, version, plan pin, predecessor_contract, non_blind_v1_1, "
                                        "D3_update.gate_scope, D3_update.constraints.geom02_gate_profile_v2, preconditions_E4.gate_order; all else identical. v1 stays as history."}
    contract["non_blind_v1_1"] = ("registered after the Stage A pre-CFD result was seen (commit 576441c: six of the eight probe states fail near_zero_gradient_band, every failing node a baseline |phi| < 1e-6 tie-plateau node "
                                  "per the planner's check); the scope change F1 is therefore non-blind, disclosed in plan Amendment 2; the profile and every threshold are unchanged")
    d3 = contract["D3_update"]
    d3["gate_scope"] = GATE_SCOPE
    d3["constraints"]["geom02_gate_profile_v2"] = ("proposal states: all 13 gates hard; probe states: twelve hard, near_zero_gradient_band report-only (gate_scope); allowed_events = (), no reinitialization")
    contract["preconditions_E4"]["gate_order"] = ("gates on every Stage A/B state run before CFD under gate_scope (probe: crossing-slope report-only; proposal: all hard); a proposal failing a gate is excluded with the reason recorded, "
                                                  "a gate failure on a ladder step is a REJECT of that step, not a dropped step")
    return contract


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    contract = build()
    if ap.parse_args().check:
        side = CONTRACT.with_name(CONTRACT.name + ".sha256").read_text().split()[0]
        if CONTRACT.read_text() != reg.dump(contract) or side != reg.sha_file(CONTRACT):
            raise SystemExit(f"check failed: {CONTRACT}")
        print("check ok", reg.sha_file(CONTRACT))
        return
    print("contract v1.1", reg.write_once(CONTRACT, contract))


if __name__ == "__main__":
    main()
