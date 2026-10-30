#!/usr/bin/env python3
"""GRID-02 host registrar (solver-free): the inventory of the five kernels.  Nothing is regenerated or re-gated: the seven geometry rows, the direction, the parent and the job env are copied
unchanged from the hash-bound OPT-01 v1 Stage B inventory; one derived row `opt01b__parent_repeat` (identical identity to the parent) is added; the native flow_24/flow_32 forces come from
the hash-bound OPT-01 Stage B analysis.  Refuses to overwrite; `--check` re-derives and compares bytes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_grid01_inputs import canonical_json  # noqa: E402
from cfd_sdf import grid02_contract as C  # noqa: E402

OPT01B = ROOT / "docs/evidence/opt01b_stage_b_2026_10_15"
EVIDENCE = ROOT / "docs/evidence/grid02_trend_2026_10_16"
OPT01B_INVENTORY_SHA = "e571e729f3152d4f71ada1db6c815a66488f3f229e4f5d239349d367ca30bac7"
OPT01B_ANALYSIS_SHA = "63413dc228980e4cf29c31e6e820ed194aa08697f35a13445b4998dc0a1c01bd"
IDENTITY_KEYS = ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "zero_level_margin_m", "changed_node_count", "maximum_pointwise_change_m")
INSTANTIATE_TIMEOUT_S, GPU_PROBE_TIMEOUT_S, RESERVE_S = 2400, 300, 300
QUALIFICATION_CLAIM = "GRID-02 response slope/curvature study on four flow grids with a lattice-alignment control; no qualification"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kernel_config(kernel: str, spec: dict, opt01b: dict) -> dict:
    case = spec["case"]
    ref = opt01b["grids"]["a" if case == "flow_24" else "b"]  # the flow_24 / flow_32 measurement is the template for every grid (only the case dict is overridden)
    measurement = copy.deepcopy(ref["measurement"])
    override = C.case_dict(case)
    if case in ("flow_24", "flow_32") and {k: measurement["case"][k] for k in override} != override:
        raise ValueError(f"the derived {case} case differs from the registered OPT-01 measurement case")
    cap = C.aggregate_cap_s(kernel)
    measurement["case"] = {**measurement["case"], **override}
    measurement.update({"case_id": case, "per_state_timeout_s": spec["per_state_timeout_s"], "solver_wall_time_cap_s": cap, "kernel_execution_allowance_s": spec["kernel_timeout_s"],
                        "qualification_claim": QUALIFICATION_CLAIM})
    return {"kernel_id": f"ramhachi888/cfd-opt-sdf-grid02-{kernel}", "case_id": case, "job": spec["job"], "placement": spec["placement"], "canonical_origin_m": list(C.PLACEMENTS[spec["placement"]]),
            "W4_CANONICAL_ORIGIN_M": C.origin_env(spec["placement"]), "GRID02_CASE": spec["grid02_case"], "per_state_timeout_s": spec["per_state_timeout_s"], "solver_wall_time_cap_s": cap,
            "kernel_timeout_s": spec["kernel_timeout_s"], "instantiate_timeout_s": INSTANTIATE_TIMEOUT_S, "gpu_probe_timeout_s": GPU_PROBE_TIMEOUT_S, "reserve_s": RESERVE_S,
            "force_scale_n_per_solver_force": C.force_scale_n(case), "measurement": measurement}


def build() -> dict:
    if sha(OPT01B / "inventory.json") != OPT01B_INVENTORY_SHA or sha(OPT01B / "opt01b_analysis.json") != OPT01B_ANALYSIS_SHA:
        raise ValueError("the OPT-01 Stage B inventory or analysis differs from its pinned immutable result")
    opt01b, analysis = json.loads((OPT01B / "inventory.json").read_text()), json.loads((OPT01B / "opt01b_analysis.json").read_text())
    if opt01b["stage_status"] != "READY" or opt01b["blockers"] or opt01b["kernels"]["a"] != list(C.SEVEN) or opt01b["kernels"]["b"] != list(C.SEVEN):
        raise ValueError("the OPT-01 Stage B inventory is blocked or its state plan differs")
    rows = opt01b["states"]
    if [r["name"] for r in rows] != list(C.SEVEN) or any(k not in r for r in rows for k in IDENTITY_KEYS) or rows[0]["kind"] != "parent":
        raise ValueError("the seven OPT-01 Stage B rows are not the registered plan or lack identity fields")
    if len({r["phi_fortran_order_sha256"] for r in rows}) != 7:
        raise ValueError("duplicate registered geometry")
    repeat = {**copy.deepcopy(rows[0]), "name": C.REPEAT, "kind": "parent_repeat", "repeat_of": C.PARENT}
    if any(repeat[k] != rows[0][k] for k in IDENTITY_KEYS):
        raise ValueError("the parent repeat must have the parent's identity")
    native = {}
    for case in ("flow_24", "flow_32"):
        forces = analysis["state_forces_n"][case]
        if sorted(forces) != sorted(C.SEVEN):
            raise ValueError(f"the OPT-01 analysis lacks the seven {case} states")
        native[case] = copy.deepcopy(forces)
    return {"kind": "grid02_inventory", "stage_status": "READY", "blockers": [],
            "source": {"opt01b_inventory_path": str((OPT01B / "inventory.json").relative_to(ROOT)), "opt01b_inventory_sha256": OPT01B_INVENTORY_SHA,
                       "opt01b_analysis_path": str((OPT01B / "opt01b_analysis.json").relative_to(ROOT)), "opt01b_analysis_sha256": OPT01B_ANALYSIS_SHA},
            "parent": copy.deepcopy(opt01b["parent"]), "proposal": copy.deepcopy(opt01b["proposal"]), "directions": copy.deepcopy(opt01b["directions"]), "job_env_common": copy.deepcopy(opt01b["job_env_common"]),
            "states": copy.deepcopy(rows) + [repeat], "kernels": {k: list(v["states"]) for k, v in C.KERNELS.items()},
            "kernel_config": {k: kernel_config(k, v, opt01b) for k, v in C.KERNELS.items()},
            "native_reference": {"analysis_path": str((OPT01B / "opt01b_analysis.json").relative_to(ROOT)), "analysis_sha256": OPT01B_ANALYSIS_SHA, "state_forces_n": native}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    data, target = canonical_json(build()), EVIDENCE / "inventory.json"
    if args.check:
        if target.read_bytes() != data or (EVIDENCE / "inventory.json.sha256").read_text().strip() != hashlib.sha256(data).hexdigest():
            raise SystemExit("frozen inventory differs from its derivation")
    else:
        if target.exists():
            raise SystemExit("refusing to overwrite the GRID-02 inventory")
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print("inventory READY", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
