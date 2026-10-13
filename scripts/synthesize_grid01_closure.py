#!/usr/bin/env python3
"""GRID-01 (#26) closure: a solver-free synthesis of the retained cross-grid evidence into one decision about which flow grid may decide a first update.

Reads only hash-pinned retained analyses (W4 v17 sensitivity, GRID-01, LOWDIM-02A/03/04A/04B); runs no CFD and measures nothing new.  The decision rule is fixed in
`decide` below and in docs/evidence/grid01_closure_2026_10_14/decision_record.md.  Writes synthesis.json once (never overwrites); --check re-derives it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/grid01_closure_2026_10_14/synthesis.json"
E = "docs/evidence/"
PINS = {
    "w4_v17": (E + "kaggle_w4_v17_sensitivity_result_2026_09.json", "25297c4646d048050974d6beccbb90ac672c910eeb558a99c1006226bdd59933"),
    "grid01": (E + "grid01_cross_grid_secant_2026_10_09/grid01_analysis.json", "ec00ed9afe4f44926dd40ff1e87f303dd9baf89195b19cb550103606beedb69c"),
    "lowdim02a": (E + "lowdim02a_flow32_cross_grid_2026_10_09/lowdim02a_analysis.json", "55c3185ebfab089e43419e04eb91f48e0a5c94dcbfc0c711b194882b542f4960"),
    "lowdim03": (E + "lowdim03_dual_grid_primal_2026_10_10/amendment1/lowdim03_analysis.json", "8615474dee771d37ad4c853c9efc276878423adbd02b154c7e3cb4604e24c54a"),
    "lowdim04a": (E + "lowdim04a_stage_a_2026_10_13/lowdim04a_analysis.json", "414d08677fb263db09e33f9a253d004c505fd4910d1859261ec6ffc5c4fd119d"),
    "lowdim04b": (E + "lowdim04b_stage_b_2026_10_13/lowdim04b_analysis.json", "ab248289df8c4c26df16ee09ed5807ec201de439e2ddd90ddb6e92978cda2ffc"),
}
# frozen decision constants (judgement values for this synthesis, not from a standard; the margins to them are reported)
PROPOSAL_COSINE_MIN = 0.8        # downforce secant vectors of the two grids must agree at least this well at every measured state for flow_24 to propose directions
SUFFICIENT_DOWNFORCE_COSINE = 0.95
SUFFICIENT_DRAG_COSINE = 0.8
FLOOR_N = 3e-5                   # the nominal downforce floor of the LOWDIM acceptance rule
GRIDS = ("flow_24", "flow_32")


def load(name):
    rel, digest = PINS[name]
    data = (ROOT / rel).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"pinned input differs: {rel}")
    return json.loads(data)


def passes(down, drag):
    """The LOWDIM acceptance rule per grid (downforce gain strictly above the floor and a computed drag change <= 0), geometry gates aside."""
    return bool(down > FLOOR_N and drag <= 0.0)


def decide(evidence: dict) -> dict:
    """Frozen rule.  FLOW24_SUFFICIENT only if the grids agree on direction and drag everywhere and never disagree on acceptance; FLOW32_SUFFICIENT is not decidable
    from this evidence (no convergence is shown, so flow_32 cannot be declared the truth); DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE if flow_24 still agrees on the
    downforce direction well enough to propose (cosine >= 0.8 at every measured state) but the grids disagree on acceptance somewhere; otherwise UNDECIDED."""
    cosd = evidence["downforce_cosines"].values()
    cosr = evidence["drag_cosines"].values()
    sufficient24 = min(cosd) >= SUFFICIENT_DOWNFORCE_COSINE and min(cosr) >= SUFFICIENT_DRAG_COSINE and evidence["acceptance_disagreements"] == 0
    proposal24 = min(cosd) >= PROPOSAL_COSINE_MIN
    if sufficient24:
        verdict = "FLOW24_SUFFICIENT_FOR_FIRST_UPDATE"
    elif proposal24 and evidence["acceptance_disagreements"] > 0:
        verdict = "DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE"
    else:
        verdict = "UNDECIDED"
    return {"verdict": verdict, "flow24_sufficient": sufficient24, "flow24_may_propose_directions": proposal24,
            "min_downforce_cosine": min(cosd), "min_downforce_cosine_margin_to_proposal_threshold": min(cosd) - PROPOSAL_COSINE_MIN,
            "min_drag_cosine": min(cosr), "flow32_declared_converged_or_true": False}


def build() -> dict:
    w4, g01, l02, l03, a04, b04 = (load(n) for n in ("w4_v17", "grid01", "lowdim02a", "lowdim03", "lowdim04a", "lowdim04b"))
    ra = w4["response_analysis"]
    w4_sens = {"flow24_to_flow32_drag_percent": ra["drag_time_weighted_n"]["resolution_delta_relative_percent"], "flow24_to_flow32_downforce_percent": ra["downforce_time_weighted_n"]["resolution_delta_relative_percent"],
               "flow16_to_flow24_drag_percent": ra["drag_time_weighted_n"]["flow16_to_flow24_delta_relative_percent"], "flow16_to_flow24_downforce_percent": ra["downforce_time_weighted_n"]["flow16_to_flow24_delta_relative_percent"]}
    cos = {"downforce": {"baseline_grid01": g01["coefficient_space_comparison_raw_finite_step_vectors"]["downforce"]["cosine"], "parent_lowdim04a": a04["response_vector_comparisons"]["downforce"]["flow_24_vs_flow_32_at_parent"]["cosine"]},
           "drag": {"baseline_grid01": g01["coefficient_space_comparison_raw_finite_step_vectors"]["drag"]["cosine"], "parent_lowdim04a": a04["response_vector_comparisons"]["drag"]["flow_24_vs_flow_32_at_parent"]["cosine"]}}
    g01_status = {f"{q}|{d}": g01["component_comparisons"][d][q]["sign_status"] for d in g01["component_comparisons"] for q in ("downforce", "drag")}
    a04_status = {k: v["sign_status"] for k, v in a04["component_comparisons"].items()}
    # actual-primal states measured on both grids: (source, state) -> per-grid (downforce change, drag change) in N relative to that source's own reference state
    states = {}
    d, r = l02["descriptive_comparison_with_flow_24"]["downforce_change_n"], l02["descriptive_comparison_with_flow_24"]["drag_change_n"]
    for s in ("+1.25", "+2.5"):
        states[f"lowdim02a|{s}mm"] = {"flow_24": (d["flow_24_lowdim01"][s], r["flow_24_lowdim01"][s]), "flow_32": (d["flow_32"][s], r["flow_32"][s])}
    for name, c in l03["candidates"].items():
        states[f"lowdim03|{name.split('__')[-1]}"] = {g: (c["per_grid"][g]["downforce_change_n"], c["per_grid"][g]["drag_change_n"]) for g in GRIDS}
    for name, c in b04["candidates"].items():
        states[f"lowdim04b|{name.split('__')[-1]}"] = {g: (c["per_grid"][g]["downforce_change_n"], c["per_grid"][g]["drag_change_n"]) for g in GRIDS}
    table = {k: {**{g: {"downforce_change_n": v[g][0], "drag_change_n": v[g][1], "passes_rule": passes(*v[g])} for g in GRIDS}} for k, v in states.items()}
    for k in table:
        table[k]["grids_disagree"] = table[k]["flow_24"]["passes_rule"] != table[k]["flow_32"]["passes_rule"]
    disagree = sum(v["grids_disagree"] for v in table.values())
    ladder = {k.split("|")[1]: v for k, v in table.items() if k.startswith("lowdim04b|")}
    single = {"flow_24_alone_would_select": max((k for k, v in ladder.items() if v["flow_24"]["passes_rule"]), key=lambda k: ladder[k]["flow_24"]["downforce_change_n"], default=None),
              "flow_32_alone_would_select": max((k for k, v in ladder.items() if v["flow_32"]["passes_rule"]), key=lambda k: ladder[k]["flow_32"]["downforce_change_n"], default=None)}
    evidence = {"downforce_cosines": cos["downforce"], "drag_cosines": cos["drag"], "acceptance_disagreements": disagree, "states_compared": len(table)}
    return {"kind": "grid01_closure_synthesis", "inputs": {k: {"path": p, "sha256": h} for k, (p, h) in PINS.items()}, "w4_v17_resolution_sensitivity_percent": w4_sens, "secant_vector_cosines": cos,
            "component_sign_status": {"grid01_baseline": g01_status, "lowdim04a_parent": a04_status}, "actual_primal_acceptance_by_grid": table, "single_grid_selection_on_the_04b_ladder": single,
            "evidence": evidence, "decision": decide(evidence), "floor_n": FLOOR_N,
            "constants": {"proposal_cosine_min": PROPOSAL_COSINE_MIN, "sufficient_downforce_cosine": SUFFICIENT_DOWNFORCE_COSINE, "sufficient_drag_cosine": SUFFICIENT_DRAG_COSINE},
            "claims_not_made": ["flow_32 (or any grid) is the converged or true response: W4 shows 6.8% and 8.4% drag/downforce change from flow_24 to flow_32 and no finer grid exists", "formal continuum or GCI gradient convergence",
                                "flow_32 noise: the 3e-5 N floor is nominal", "a physical downforce or drag gain", "that the dual-grid rule is optimal, only that single-grid acceptance is contradicted by retained states"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = (json.dumps(build(), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.check:
        if OUT.read_bytes() != data:
            raise SystemExit("synthesis differs from its derivation")
    elif OUT.exists():
        raise SystemExit("refusing to overwrite the synthesis")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(data)
    print("synthesis", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
