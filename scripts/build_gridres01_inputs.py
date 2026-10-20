#!/usr/bin/env python3
"""GRIDRES-01 host registrar: derives the five-state inventory from the frozen OPT-01 Stage B inventory (hash-pinned), so the states are byte-identical by construction.

Every phi hash is re-derived here from the pinned parent and direction raw files (as the OPT-01 Stage B runner does).  The grid table (flow_40, flow_48) is derived from the
frozen W4 case construction (spacing = 0.8 m / cells, nu = cells / 80); nothing under julia/CFDSDFWaterLily/src is edited.  Solver-free.  Refuses to overwrite; --check re-derives.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import gridres01_states as G  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/gridres01_2026_10_20"
JOB = "scripts/waterlily_gridres01_job.jl"
ROW_KEYS = ("name", "kind", "direction", "step_mm", "sign", "state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "zero_level_margin_m", "margin_tolerance_m",
            "changed_node_count", "maximum_pointwise_change_m")


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def retained_parent_reruns(spec: dict, analysis: dict) -> list:
    """Amendment 2 H2: the retained grids whose OPT-01 parent the kernel reruns instrumented, with the Stage B parent force CSV hash it must reproduce byte for byte."""
    return [{"case_id": g, "cells": G.RERUN_CELLS[g], "flow_dims": list(G.RERUN_DIMS[g]), "retained_forces_csv": f"{G.OPT01B_REL}/kernel_output/opt01b_{G.RETAINED_KERNEL[g]}/states/{G.PARENT_NAME}/{g}.forces.csv",
             "retained_forces_csv_sha256": analysis["state_forces_n"][g][G.PARENT_NAME]["forces_csv_sha256"]} for g in spec["parent_reruns"]]


def grid_entry(case_id: str, spec: dict, template: dict, analysis: dict) -> dict:
    """Measurement block of one grid: the Stage B flow_32 block with the case fields rebuilt from the cell count."""
    n, h = spec["cells"], 0.8 / spec["cells"]
    m = copy.deepcopy(template)
    m["case"].update({"case_id": case_id, "flow_dims": list(spec["dims"]), "flow_spacing_m": h, "solver_length": float(n), "solver_time_unit_s": h, "solver_viscosity": n / 80})
    m.update({"case_id": case_id, "per_state_timeout_s": spec["per_state_timeout_s"], "solver_wall_time_cap_s": spec["solver_wall_time_cap_s"], "kernel_execution_allowance_s": spec["kernel_timeout_s"],
              "qualification_claim": "bounded GRIDRES-01 finer-grid actual-primal response check along the OPT-01 direction; no qualification"})
    return {"case_id": case_id, "cells": n, "job": JOB, "measurement": m, "limits": {k: spec[k] for k in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")},
            "parent_reruns": retained_parent_reruns(spec, analysis)}


def build() -> dict:
    src = ROOT / G.OPT01B_REL / "inventory.json"
    if sha(src) != G.OPT01B_INVENTORY_SHA:
        raise ValueError("the OPT-01 Stage B inventory differs from its pinned hash")
    inv = json.loads(src.read_text())
    ana_path = ROOT / G.OPT01B_REL / "opt01b_analysis.json"
    if sha(ana_path) != G.OPT01B_ANALYSIS_SHA:
        raise ValueError("the OPT-01 Stage B analysis differs from its pinned hash")
    analysis = json.loads(ana_path.read_text())
    if inv["stage_status"] != "READY" or inv["blockers"]:
        raise ValueError("the OPT-01 Stage B inventory is blocked")
    by_name = {r["name"]: r for r in inv["states"]}
    if [{k: by_name[r["name"]][k] for k in ("name", "kind", "direction", "step_mm", "sign")} for r in G.plan()] != G.plan():
        raise ValueError("the GRIDRES-01 state plan differs from the Stage B rows")
    parent = S.read_f4(ROOT / inv["parent"]["raw_path"])
    prop = S.read_f4(ROOT / inv["proposal"]["file"])
    if sha(ROOT / inv["parent"]["raw_path"]) != inv["parent"]["phi_fortran_order_sha256"] or sha(ROOT / inv["proposal"]["file"]) != inv["proposal"]["sha256_fortran_raw"]:
        raise ValueError("the parent or direction raw file differs from the Stage B inventory")
    rows = []
    for item in G.plan():
        row = by_name[item["name"]]
        phi = parent if item["kind"] == "parent" else S.perturb(parent, prop, item["step_mm"], item["sign"])
        if (S.sha256_bytes(S.to_raw(phi)) != row["phi_fortran_order_sha256"]
                or hashlib.sha256(np.asarray(phi, dtype="<f4").tobytes(order="C")).hexdigest() != row["phi_c_order_sha256"]):
            raise ValueError(f"regenerated phi differs from the Stage B inventory: {item['name']}")
        rows.append({k: row[k] for k in ROW_KEYS})
    template = inv["grids"]["b"]["measurement"]
    return {"kind": "gridres01_inventory", "stage_status": "READY", "blockers": [], "names": list(G.NAMES), "steps_mm": list(G.STEPS_MM),
            "opt01b_inventory": {"path": str(src.relative_to(ROOT)), "sha256": G.OPT01B_INVENTORY_SHA}, "opt01b_analysis": {"path": f"{G.OPT01B_REL}/opt01b_analysis.json", "sha256": G.OPT01B_ANALYSIS_SHA},
            "parent": {k: inv["parent"][k] for k in ("state_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "generation", "raw_path")},
            "proposal": {k: inv["proposal"][k] for k in ("file", "sha256_fortran_raw", "coefficient_vector", "m_max_abs_sum")},
            "job_env_common": inv["job_env_common"], "margin_gate_m": inv["margin_gate_m"], "states": rows,
            "grids": {case_id: grid_entry(case_id, spec, template, analysis) for case_id, spec in G.GRIDS.items()}, "kernels": {case_id: list(G.NAMES) for case_id in G.GRIDS},
            "disclosure": "flow_48 is parameterization only: no flow_48 run is registered by the flow_40 freeze (plan Amendment 1 G2); a flow_48 freeze needs its own review and two kernels (Amendment 2 H4)"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    data, target = canonical_json(build()), EVIDENCE / "inventory.json"
    if args.check:
        if target.read_bytes() != data:
            raise SystemExit("frozen inventory differs from its derivation")
    else:
        if target.exists():
            raise SystemExit("refusing to overwrite the GRIDRES-01 inventory")
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print("inventory", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
