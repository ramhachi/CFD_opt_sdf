#!/usr/bin/env python3
"""Build GRID-01's hash-bound nine-state inventory from frozen STEP-01 inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import build_lowdim01_inputs as lowdim01  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf import grid01_contract as C  # noqa: E402
from cfd_sdf.lowdim02a_contract import FLOW32_CASE  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402
from analyze_lowdim02a import flow32_criteria  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"
STEP01_EVIDENCE = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
LOWDIM01_EVIDENCE = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
GEOMETRY_EXPLORATION = LOWDIM01_EVIDENCE / "geometry_exploration_step01_states.json"
CANONICAL_NPZ = ROOT / "docs/evidence/xfid01_geometry_preflight_2026_10_03/canonical_state.npz"
FORMAL = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
W4_BASELINE_DIR = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained"
W4_RESULT = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_result_2026_10.json"
SIGNS = (("plus", 1), ("minus", -1))
MARGIN_TOLERANCE_M = 1.0e-6


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _finite_record(row: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    for key in fields:
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(float(value)):
            raise ValueError(f"{label}.{key} must be finite")


def _step01_reference(step01_analysis: dict[str, Any]) -> dict[str, Any]:
    if step01_analysis.get("verdict") != "STEP01_RECORDED" or step01_analysis.get("integrity", {}).get("pass") is not True:
        raise ValueError("the frozen STEP-01 analysis is not an intact recorded result")
    result: dict[str, Any] = {}
    for direction in C.BASIS:
        result[direction] = {}
        for quantity in C.RESPONSES:
            rows = step01_analysis.get("series", {}).get(f"{direction}|{quantity}", {}).get("rows")
            if not isinstance(rows, list) or not rows or rows[0].get("step_mm") != 2.5:
                raise ValueError(f"STEP-01 lacks the registered 2.5 mm row for {direction}|{quantity}")
            row = rows[0]
            _finite_record(row, ("r0_n", "r_plus_n", "r_minus_n", "g_sec_n_per_m", "eta_even"), f"{direction}|{quantity}")
            if not isinstance(row.get("resolved"), bool):
                raise ValueError(f"STEP-01 resolved flag is missing for {direction}|{quantity}")
            contrast = row["r_plus_n"] - row["r_minus_n"]
            result[direction][quantity] = {
                **{
                    key: row[key]
                    for key in ("step_mm", "r0_n", "r_plus_n", "r_minus_n", "g_sec_n_per_m", "eta_even")
                },
                "source_step01_resolved": row["resolved"],
                "even_part_n": (row["r_plus_n"] + row["r_minus_n"] - 2.0 * row["r0_n"]) / 2.0,
                "resolved": abs(contrast) > C.MIN_RESOLVED_N,
            }
    return result


def _save_npz_twice(state: SDFDesignState) -> str:
    with tempfile.TemporaryDirectory(prefix="grid01-npz-") as temp:
        first, second = Path(temp) / "first.npz", Path(temp) / "second.npz"
        state.save(first); state.save(second)
        one, two = sha(first), sha(second)
    if one != two:
        raise ValueError("canonical state NPZ serialization is not deterministic")
    return one


def _make_state_rows(
    canonical: Path,
    step01_inventory: dict[str, Any],
    lowdim01_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    by_step = {row["name"]: row for row in step01_inventory["states"]}
    by_direction = lowdim01_inventory["directions"]
    source_states = {row["name"]: row for row in lowdim01_inventory["states"]}
    parent = SDFDesignState.load(canonical)
    base_phi = S.read_f4(ROOT / step01_inventory["baseline"]["path"])
    if S.to_raw(parent.phi) != S.to_raw(base_phi):
        raise ValueError("canonical NPZ and STEP-01 baseline phi differ")
    base_geometry = lowdim01.geometry(parent)
    rows: list[dict[str, Any]] = []
    plan: list[tuple[str, str, float, int]] = [("step01__baseline", "baseline", 0.0, 0)]
    for direction in C.BASIS:
        for suffix, sign in SIGNS:
            plan.append((S.single_name(direction, 2.5, sign), direction, 2.5, sign))
    for name, direction, step_mm, sign in plan:
        source_row = by_step.get(name)
        if source_row is None:
            raise ValueError(f"STEP-01 state is missing: {name}")
        if step_mm == 0.0:
            child, audit = parent, {
                "changed_node_count": 0,
                "maximum_pointwise_change_m": 0.0,
                "zero_level_margin_m": state_identity(parent)["margin_m"],
                "masks_equal": True,
                "support_outside_active_exactly_unchanged": True,
            }
            geometry = base_geometry
            gate = None
        else:
            raw_direction = by_direction[direction]
            direction_path = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs" / raw_direction["file"]
            direction_array = S.read_f4(direction_path)
            child, audit = construct_state(parent, direction_array, step_mm, sign)
            geometry = lowdim01.geometry(child)
            gate = lowdim01.gates(base_geometry, geometry, audit)
            gate_rows = source_states.get(name)
            if gate_rows is not None:
                raise ValueError(f"unexpected LOWDIM-01 proposal state name collision: {name}")
            exploration = json.loads(GEOMETRY_EXPLORATION.read_text())["states"].get(name)
            if not isinstance(exploration, dict):
                raise ValueError(f"STEP-01 geometry exploration is missing: {name}")
            if exploration.get("directions") != [direction] or exploration.get("step_mm") != step_mm or exploration.get("sign") != sign:
                raise ValueError(f"geometry exploration identity differs for {name}")
        identity = state_identity(child)
        npz_sha = _save_npz_twice(child)
        for key, actual in (
            ("phi_fortran_order_sha256", identity["phi_fortran_order_sha256"]),
            ("phi_c_order_sha256", identity["phi_c_order_sha256"]),
            ("state_sha256", identity["state_sha256"]),
            ("npz_sha256", npz_sha),
        ):
            if source_row.get(key) != actual:
                raise ValueError(f"regenerated STEP-01 {key} differs for {name}")
        if abs(float(source_row["zero_level_margin_m"]) - float(audit["zero_level_margin_m"])) > 1.0e-12:
            raise ValueError(f"regenerated STEP-01 zero-level margin differs for {name}")
        if source_row["changed_node_count"] != int(audit["changed_node_count"]):
            raise ValueError(f"regenerated STEP-01 changed-node count differs for {name}")
        if abs(float(source_row["maximum_pointwise_change_m"]) - float(audit["maximum_pointwise_change_m"])) > 1.0e-12:
            raise ValueError(f"regenerated STEP-01 maximum pointwise change differs for {name}")
        row = {
            "name": name,
            "kind": "baseline" if step_mm == 0.0 else "single",
            "direction": None if step_mm == 0.0 else direction,
            "step_mm": step_mm,
            "sign": sign,
            "kernel": "a",
            "step01_kernel": source_row["kernel"],
            "step01_source_name": source_row["name"],
            **{key: source_row[key] for key in (
                "phi_fortran_order_sha256", "phi_c_order_sha256", "state_sha256", "npz_sha256",
                "changed_node_count", "maximum_pointwise_change_m", "zero_level_margin_m", "margin_tolerance_m",
            )},
            "geometry": geometry,
            "geometry_gates": gate,
        }
        if step_mm != 0.0 and (not isinstance(gate, dict) or set(gate["gates"]) != C.GEOMETRY_GATE_KEYS):
            raise ValueError(f"wrong geometry gate set for {name}")
        rows.append(row)
    if len(rows) != 9 or sum(r["kind"] == "baseline" for r in rows) != 1 or rows[0]["kind"] != "baseline":
        raise ValueError("GRID-01 must contain exactly one first baseline and eight paired perturbations")
    return rows


def measurement_contract(formal: dict[str, Any]) -> dict[str, Any]:
    criteria = flow32_criteria(formal)
    if criteria["measurement"]["case"].get("case_id") != FLOW32_CASE["case_id"]:
        raise ValueError("flow32_criteria did not resolve its nested case to FLOW32_CASE")
    criteria["measurement"]["case_id"] = FLOW32_CASE["case_id"]
    criteria["measurement"]["qualification_claim"] = "bounded GRID-01 flow_32 finite-step diagnostic; no qualification claim"
    criteria["measurement"]["kernel_execution_allowance_s"] = C.KERNEL_TIMEOUT_S
    criteria["measurement"]["per_state_timeout_s"] = C.PER_STATE_TIMEOUT_S
    criteria["measurement"]["solver_wall_time_cap_s"] = C.SOLVER_WALL_TIME_CAP_S
    return {
        "flow32_case": FLOW32_CASE,
        "flow32_measurement": criteria["measurement"],
        "time_window_t_u_l": [80.0, 120.0],
        "force_conversion": "host recomputation with flow_32 spacing 0.025 m; do not pass flow_24 criteria unchanged",
        "step_mm": 2.5,
        "signed_perturbations": ["plus", "minus"],
        "resolution_difference_n_strictly_greater_than": C.MIN_RESOLVED_N,
        "unresolved_numeric_secants_preserved": True,
    }


def build(canonical: Path = CANONICAL_NPZ) -> dict[str, Any]:
    step01_inventory_path = STEP01_EVIDENCE / "inventory.json"
    step01_analysis_path = STEP01_EVIDENCE / "step01_analysis.json"
    lowdim01_inventory_path = LOWDIM01_EVIDENCE / "inventory.json"
    step01_inventory = json.loads(step01_inventory_path.read_text())
    step01_analysis = json.loads(step01_analysis_path.read_text())
    lowdim01_inventory = json.loads(lowdim01_inventory_path.read_text())
    formal = json.loads(FORMAL.read_text())
    if sha(canonical) != step01_inventory["baseline"]["canonical_npz_sha256"]:
        raise ValueError("canonical NPZ hash differs from the STEP-01 inventory")
    if sha(step01_analysis_path) != lowdim01_inventory["coefficient_gradient"]["step01_analysis_sha256"]:
        raise ValueError("LOWDIM-01 does not bind the current immutable STEP-01 analysis")
    if lowdim01_inventory.get("basis") != list(C.BASIS):
        raise ValueError("LOWDIM-01 basis order differs from GRID-01")
    if step01_inventory.get("directions") != lowdim01_inventory.get("directions"):
        raise ValueError("STEP-01 and LOWDIM-01 direction identities differ")
    for direction, ref in step01_inventory["directions"].items():
        path = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs" / ref["file"]
        if sha(path) != ref["sha256_fortran_raw"]:
            raise ValueError(f"direction hash mismatch: {direction}")
        if not np.all(np.isfinite(S.read_f4(path))):
            raise ValueError(f"direction contains non-finite values: {direction}")
    step01_ref = _step01_reference(step01_analysis)
    rows = _make_state_rows(canonical, step01_inventory, lowdim01_inventory)
    baseline_raw = ROOT / step01_inventory["baseline"]["path"]
    formal_bytes = FORMAL.read_bytes()
    contract = measurement_contract(formal)
    measurement = {"measurement": contract["flow32_measurement"]}
    w4_csv = W4_BASELINE_DIR / "flow_32.forces.csv"
    w4_results = json.loads(W4_RESULT.read_text())["case_measurements"]["flow_32"]
    w4_host = recompute_force_n(w4_csv, measurement)
    for q in ("drag_n", "downforce_n"):
        if abs(w4_host[q] - w4_results[f"total_{q}"]) > 1.0e-12 * abs(w4_results[f"total_{q}"]):
            raise ValueError(f"flow_32 host force scale does not reproduce W4 {q}")
    directions = {
        name: {
            "path": f"docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/{ref['file']}",
            "sha256_fortran_raw": ref["sha256_fortran_raw"],
        }
        for name, ref in step01_inventory["directions"].items()
    }
    flow24_ref = {
        "source": "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json; numeric fields copied from series rows[0] at step_mm=2.5, source resolved retained separately, GRID-01 resolved/even part rederived",
        "step01_analysis_sha256": sha(step01_analysis_path),
        "secants": step01_ref,
        "recomputed": False,
    }
    return {
        "kind": "grid01_flow24_flow32_cross_grid_secant_inventory",
        "canonical_npz": {
            "path": str(canonical.resolve().relative_to(ROOT.resolve())),
            "sha256": sha(canonical),
        },
        "measurement_contract": contract,
        "source_hashes": {
            "step01_inventory_sha256": sha(step01_inventory_path),
            "step01_analysis_sha256": sha(step01_analysis_path),
            "lowdim01_inventory_sha256": sha(lowdim01_inventory_path),
            "geometry_exploration_sha256": sha(GEOMETRY_EXPLORATION),
            "formal_criteria_sha256": sha(FORMAL),
            "canonical_npz_sha256": sha(canonical),
            "baseline_phi_raw_sha256": sha(baseline_raw),
        },
        "baseline": {
            "path": step01_inventory["baseline"]["path"],
            "phi_fortran_sha256": step01_inventory["baseline"]["phi_fortran_sha256"],
            "canonical_npz_sha256": step01_inventory["baseline"]["canonical_npz_sha256"],
            "state_sha256": step01_inventory["baseline"]["state_sha256"],
            "zero_level_margin_m": step01_inventory["baseline"]["margin_m"],
        },
        "directions": directions,
        "basis_order": list(C.BASIS),
        "job_env_common": step01_inventory["job_env_common"],
        "margin_gate_m": step01_inventory["margin_gate_m"],
        "flow32_baseline_reference": {
            "forces_csv_path": "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv",
            "forces_csv_sha256": sha(w4_csv),
            "source": "retained W4 v17 round-2 flow_32 baseline; byte-identity gate only, not a reused measurement record",
            "w4_result_total_downforce_n": w4_results["total_downforce_n"],
            "w4_result_total_drag_n": w4_results["total_drag_n"],
            "host_recomputed_n": {"downforce_n": w4_host["downforce_n"], "drag_n": w4_host["drag_n"]},
            "force_scale_n_per_solver_force": w4_host["force_scale_n_per_solver_force"],
        },
        "flow24_reference_step01": flow24_ref,
        "geometry_gate_contract": {
            "gate_keys": sorted(C.GEOMETRY_GATE_KEYS),
            "thresholds": lowdim01_inventory["geometry_gate_thresholds"],
            "evidence": "solver-free geometry gates recomputed with the existing LOWDIM-01 geometry and state-construction helpers; descriptive per-state metadata, not a geometry qualification",
        },
        "kernels": {"a": [row["name"] for row in rows]},
        "states": rows,
        "perturbation": step01_inventory["perturbation"],
        "formal_criteria_sha256": hashlib.sha256(formal_bytes).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=CANONICAL_NPZ)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory = build(args.canonical)
    data = canonical_json(inventory)
    out = EVIDENCE / "inventory.json"
    digest = hashlib.sha256(data).hexdigest()
    if args.check:
        if not out.is_file() or out.read_bytes() != data:
            raise SystemExit("the committed GRID-01 inventory differs from its frozen-input re-derivation")
        print("inventory reproduced", digest)
        return
    if out.exists():
        raise SystemExit("refusing to overwrite the existing GRID-01 inventory")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    out.with_name("inventory.json.sha256").write_text(digest + "\n")
    print(digest)


if __name__ == "__main__":
    main()
