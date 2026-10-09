#!/usr/bin/env python3
"""Host registrar of the LOWDIM-02A (#49) inputs (solver-free): the five flow_32 states (a subset of the LOWDIM-01 inventory plus a baseline repeat) and the bound references.

States: baseline, baseline repeat (determinism / noise floor), +1.25 mm along the LOWDIM-01 proposal (the accepted step), -1.25 mm (reverse control), +2.5 mm (descriptive only).
Every perturbed state is the LOWDIM-01 state with the same phi (identity copied from the hash-bound LOWDIM-01 inventory).  The flow_32 baseline reference is the W4 v17 round-2 retained
flow_32.forces.csv of the same canonical state (byte-identity gate only).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from cfd_sdf import lowdim02a_contract as C  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

E = ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
L1 = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
W4 = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained"
W4_RESULT = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_result_2026_10.json"
FORMAL = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
PLAN = (("lowdim02a__baseline", "baseline", "lowdim01__baseline", 0.0, 0), ("lowdim02a__baseline_repeat", "baseline_repeat", "lowdim01__baseline", 0.0, 0),
        ("lowdim02a__prop__s1.25mm", "candidate", "lowdim01__prop__s1.25mm", 1.25, 1), ("lowdim02a__ctrl_reverse__s1.25mm", "control", "lowdim01__ctrl_reverse__s1.25mm", 1.25, -1),
        ("lowdim02a__prop__s2.5mm", "descriptive", "lowdim01__prop__s2.5mm", 2.5, 1))


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measurement(formal: dict) -> dict:
    m = json.loads(json.dumps(formal["measurement"]))
    m["case"] = {**m["case"], **C.FLOW32_CASE}
    return {"measurement": m}


def build() -> dict:
    inv1 = json.loads((L1 / "inventory.json").read_text())
    by = {r["name"]: r for r in inv1["states"]}
    formal = json.loads(FORMAL.read_text())
    w4 = json.loads(W4_RESULT.read_text())["case_measurements"]["flow_32"]
    host = recompute_force_n(W4 / "flow_32.forces.csv", measurement(formal))
    assert abs(host["downforce_n"] - w4["total_downforce_n"]) <= 1e-12 * abs(w4["total_downforce_n"]) and abs(host["drag_n"] - w4["total_drag_n"]) <= 1e-12 * abs(w4["total_drag_n"])
    a1 = json.loads((L1 / "lowdim01_analysis.json").read_text())
    rows = []
    for name, kind, src, step, sign in PLAN:
        r = by[src]
        rows.append({"name": name, "kind": kind, "source_lowdim01_state": src, "step_mm": step, "sign": sign, "kernel": "a", **{k: r[k] for k in (
            "phi_fortran_order_sha256", "phi_c_order_sha256", "state_sha256", "npz_sha256", "changed_node_count", "maximum_pointwise_change_m", "zero_level_margin_m", "margin_tolerance_m",
            "geometry", "geometry_gates")}})
    ref24 = {"source": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/lowdim01_analysis.json", "lowdim01_analysis_sha256": sha(L1 / "lowdim01_analysis.json"), "baseline": a1["baseline"],
             "downforce_change_n": {"+1.25": a1["candidates"]["lowdim01__prop__s1.25mm"]["downforce_change_n"], "-1.25": a1["controls"]["lowdim01__ctrl_reverse__s1.25mm"]["downforce_change_n"],
                                    "+2.5": a1["candidates"]["lowdim01__prop__s2.5mm"]["downforce_change_n"]},
             "drag_change_n": {"+1.25": a1["candidates"]["lowdim01__prop__s1.25mm"]["drag_change_n"], "-1.25": a1["controls"]["lowdim01__ctrl_reverse__s1.25mm"]["drag_change_n"],
                               "+2.5": a1["candidates"]["lowdim01__prop__s2.5mm"]["drag_change_n"]}}
    return {"kind": "lowdim02a_state_inventory", "job_env_common": inv1["job_env_common"], "formal_criteria_sha256": sha(FORMAL), "baseline": inv1["baseline"],
            "lowdim01_inventory_sha256": sha(L1 / "inventory.json"), "proposal": inv1["proposal"], "basis": inv1["basis"], "directions": inv1["directions"], "margin_gate_m": inv1["margin_gate_m"],
            "flow32_baseline_reference": {"forces_csv_sha256": sha(W4 / "flow_32.forces.csv"), "source": "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv (same canonical state; a reference for the byte-identity gate only, not a reused record)",
                                          "w4_result_total_downforce_n": w4["total_downforce_n"], "w4_result_total_drag_n": w4["total_drag_n"],
                                          "host_recomputed_n": {"downforce_n": host["downforce_n"], "drag_n": host["drag_n"]}, "force_scale_n_per_solver_force": host["force_scale_n_per_solver_force"]},
            "flow32_case": C.FLOW32_CASE, "flow24_reference_lowdim01": ref24,
            "rules": {"min_resolved_n": C.MIN_RESOLVED_N, "noise_factor": C.NOISE_FACTOR, "nominal_sigma0_n": C.NOMINAL_SIGMA0_N, "verdicts": list(C.VERDICTS)},
            "kernels": {"a": [r["name"] for r in rows]}, "states": rows}


def main() -> None:
    inv = build()
    data = (json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()
    out = E / "inventory.json"
    if "--check" in sys.argv:
        assert out.read_bytes() == data, "the committed inventory differs from the re-derivation"
        print("inventory reproduced", hashlib.sha256(data).hexdigest())
        return
    if out.exists():
        sys.exit("refusing to overwrite the inventory")
    out.write_bytes(data); out.with_name("inventory.json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
