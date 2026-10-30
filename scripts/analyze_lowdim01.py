#!/usr/bin/env python3
"""LOWDIM-01 (#48) host analyzer: integrity of the T4 kernel, then the pre-registered accept / reject by the ACTUAL primal responses and the hard geometry gates (run once).

One kernel: the baseline and the line-search candidates along the proposal direction (the coefficient gradient is the STEP-01 centered +-2.5 mm difference, used only to propose).
Verdicts: LOWDIM_ACCEPT (an accepted coefficient-space step: capability statement for the 4-direction basis) | LOWDIM_NO_GO (no candidate accepted: a bounded No-Go) | LOWDIM_INCOMPLETE.
Not a gradient qualification, not OPT-01 (#30); no flag, FD-08 verdict, delta or GRAD-03 change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import lowdim01_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf import lowdim01_contract as C  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
FORMAL_CRITERIA = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
SUMMARY_REL = 1e-9
BASELINE_REL = 1e-12
MIN_T_END = 120.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def jload(path: Path):
    return json.loads(Path(path).read_text())


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-300)


def check_kernel(out: Path, freeze: dict, inventory: dict, criteria: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    states: dict = {}
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done == error:
        failures.append(f"exactly one of DONE/ERROR.txt must exist (done={done}, error={error})")
    index = jload(out / "lowdim01_index.json") if (out / "lowdim01_index.json").is_file() else {}
    identity = jload(out / "run_identity.json") if (out / "run_identity.json").is_file() else {}
    if index.get("status") != "COMPLETE" or index.get("kernel") != "a":
        failures.append(f"lowdim01_index status {index.get('status')!r}")
    if identity.get("source_commit") != freeze["source_commit"] or identity.get("failure_stage") is not None:
        failures.append("run identity source commit / failure stage")
    if not freeze["pins"]:
        failures.append("the freeze has no pins to verify")
    for rel_path, digest in freeze["pins"].items():
        if identity.get("verified", {}).get(rel_path) != digest:
            failures.append(f"pin not verified on the kernel: {rel_path}")
    if identity.get("fd08_baseline_csv_sha256") != freeze["fd08_baseline"]["forces_csv_sha256"]:
        failures.append("the FD-08 baseline CSV pin differs from the freeze")
    manifest = jload(out / "output_manifest.json").get("files") if (out / "output_manifest.json").is_file() else None
    plan = inventory["kernels"]["a"]
    if not isinstance(manifest, dict):
        failures.append("output_manifest.json missing or malformed")
    else:
        required = {"lowdim01_index.json", "run_identity.json", "nvidia_smi.csv"} | {f"states/{n}/{f}" for n in plan for f in ("flow_24.forces.csv", "flow_24.summary.json", "W4_JOB_DONE")}
        if not required <= set(manifest):
            failures.append("the manifest does not list every required output file")
        for rel_path, digest in manifest.items():
            p = out / rel_path
            if not p.is_file() or sha256(p) != digest:
                failures.append(f"manifest mismatch: {rel_path}")
    gpu = (out / "nvidia_smi.csv").read_text() if (out / "nvidia_smi.csv").is_file() else ""
    if not gpu.strip() or any("Tesla T4" not in r for r in gpu.strip().splitlines()):
        failures.append("the recorded GPU is not a Tesla T4")
    listed = [e.get("name") for e in index.get("states", [])]
    if listed != plan or not all(e.get("complete") for e in index.get("states", [])):
        failures.append("the completed states are not exactly the registered plan")
    present = sorted(p.name for p in (out / "states").iterdir() if p.is_dir()) if (out / "states").is_dir() else []
    if present != sorted(plan):
        failures.append("the state directories differ from the plan")
    by_name = {r["name"]: r for r in inventory["states"]}
    for name in plan:
        row, d = by_name[name], out / "states" / name
        try:
            csv, summary_path = d / "flow_24.forces.csv", d / "flow_24.summary.json"
            if not (csv.is_file() and summary_path.is_file() and (d / "W4_JOB_DONE").is_file()):
                raise ValueError("a state output file is missing")
            entry = next(e for e in index["states"] if e["name"] == name)
            if entry.get("forces_csv_sha256") != sha256(csv):
                raise ValueError("the force CSV differs from the index")
            summary = jload(summary_path)
            for key, want in (("phi_fortran_sha256", row["phi_fortran_order_sha256"]), ("state_sha256", row["state_sha256"]), ("state_npz_sha256", row["npz_sha256"]),
                              ("phi_c_order_sha256", row["phi_c_order_sha256"]), ("gpu_name", "Tesla T4")):
                if summary.get(key) != want:
                    raise ValueError(f"summary {key} differs from the registered value")
            margin = summary.get("phi_margin_m")
            if not isinstance(margin, (int, float)) or not abs(margin - row["zero_level_margin_m"]) <= row["margin_tolerance_m"] or summary.get("phi_margin_gate_m") != 0.15:
                raise ValueError("summary margin differs from the registered value")
            t_end = summary.get("t_end_reached")
            if not (summary.get("finite_u") is True and summary.get("finite_p") is True and summary.get("finite_forces") is True and summary.get("case_id") == "flow_24"
                    and isinstance(t_end, (int, float)) and t_end >= MIN_T_END and summary.get("julia_threads") == 1):
                raise ValueError("summary finiteness / horizon / case / threads")
            host = recompute_force_n(csv, criteria)
            for host_q, summary_q in (("drag_n", "drag_time_weighted_n"), ("downforce_n", "downforce_time_weighted_n")):
                sv = summary.get(summary_q)
                if not isinstance(sv, (int, float)) or not math.isfinite(host[host_q]) or not rel(host[host_q], sv) <= SUMMARY_REL:
                    raise ValueError("the host recomputation differs from the Julia summary")
            states[name] = {"drag_n": host["drag_n"], "downforce_n": host["downforce_n"], "csv_sha256": entry["forces_csv_sha256"]}
        except Exception as err:  # noqa: BLE001
            failures.append(f"state {name}: {err}")
    return failures, states


def analyze(out: Path, freeze: dict, inventory: dict | None = None, formal: dict | None = None, step01_analysis: dict | None = None) -> dict:
    inventory = inventory if inventory is not None else jload(E / "inventory.json")
    formal = formal if formal is not None else jload(FORMAL_CRITERIA)
    criteria = {"measurement": formal["measurement"]}
    report: dict = {"kind": "lowdim01_four_direction_capability_analysis", "selected_delta": None, "grad03_verdict": None, "no_gradient_claim": True, "not_opt01": True,
                    "fd08_verdict_unchanged": True, "reinitialization": "none", "qualification_flags": {k: False for k in FLAGS}}
    failures: list[str] = []
    for name, path in (("analyzer", Path(__file__)), ("contract", ROOT / "src/cfd_sdf/lowdim01_contract.py"), ("states_module", ROOT / "scripts/lowdim01_states.py"),
                       ("step01_states_module", ROOT / "scripts/step01_states.py"), ("force_io", ROOT / "scripts/fd08_v2_campaign_io.py"), ("formal_criteria", FORMAL_CRITERIA)):
        if sha256(path) != freeze["file_hashes"].get(name):
            failures.append(f"{name} differs from (or is missing in) the freeze")
    if hashlib.sha256((json.dumps(inventory, sort_keys=True, indent=2) + "\n").encode()).hexdigest() != freeze["file_hashes"].get("inventory_canonical_json"):
        failures.append("the inventory differs from the frozen inventory")
    # the coefficient gradient is the bound STEP-01 data
    step01_path = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json"
    if step01_analysis is None:
        if sha256(step01_path) != freeze["step01_analysis_sha256"]:
            failures.append("the bound STEP-01 analysis differs from the frozen one")
        step01_analysis = jload(step01_path)
    for d in L.BASIS:
        row = step01_analysis["series"][f"{d}|downforce"]["rows"][0]
        if row["g_sec_n_per_m"] != inventory["coefficient_gradient"]["values"][d]["g_sec_n_per_m"] or row["step_mm"] != L.FD_STEP_MM:
            failures.append(f"the registered coefficient gradient differs from the STEP-01 data: {d}")
    f, res = check_kernel(out, freeze, inventory, criteria)
    failures += f
    ref = inventory["fd08_baseline_reference"]
    base = res.get(L.BASELINE_NAME)
    if not base:
        failures.append("no baseline")
    else:
        if base["csv_sha256"] != ref["forces_csv_sha256"]:
            failures.append("the baseline force CSV differs from FD-08's baseline_v17")
        for q in ("drag_n", "downforce_n"):
            if not rel(base[q], ref["host_recomputed_n"][q]) <= BASELINE_REL:
                failures.append(f"baseline {q} differs from FD-08's baseline_v17")
    report["integrity"] = {"pass": not failures, "failures": failures}
    if failures:
        report["verdict"] = "LOWDIM_INCOMPLETE"
        return report
    try:
        report.update(decide(res, base, inventory))
    except Exception as err:  # noqa: BLE001  a computation failure after the gates is never a recorded verdict
        report["integrity"] = {"pass": False, "failures": [f"analysis error: {type(err).__name__}: {err}"]}
        report["verdict"] = "LOWDIM_INCOMPLETE"
    return report


GATE_KEYS = {"clearance", "masks_and_support_preserved", "cell_components_equal_baseline", "smoothed_volume_band", "eikonal_median_within_limit"}


def decide(res: dict, base: dict, inventory: dict) -> dict:
    rows = {r["name"]: r for r in inventory["states"]}
    evals, steps, table, controls = {}, {}, {}, {}
    for item in L.plan()[1:]:
        name = item["name"]
        g = rows[name]["geometry_gates"]
        if set(g["gates"]) != GATE_KEYS or g["all_hard_gates_pass"] is not all(g["gates"].values()):
            raise ValueError(f"the registered geometry gates of {name} are inconsistent")
        pred = inventory["linear_prediction_reference_only"][name]["linear_predicted_downforce_change_n"]
        ev = C.evaluate_candidate(base["downforce_n"], base["drag_n"], res[name]["downforce_n"], res[name]["drag_n"], g["all_hard_gates_pass"])
        row = {**ev, "step_mm": item["step_mm"], "signed_step_mm": item["step_mm"] * item["sign"], "downforce_n": res[name]["downforce_n"], "drag_n": res[name]["drag_n"], "geometry_gates": g["gates"],
               "relative_smoothed_volume_change": g["relative_smoothed_volume_change"], "relative_sharp_volume_change": g["relative_sharp_volume_change"],
               "eikonal_median_abs_deviation": rows[name]["geometry"]["eikonal_median_abs_deviation"], "linear_predicted_downforce_change_n_reference_only": pred,
               "actual_over_predicted_reference_only": ev["downforce_change_n"] / pred if pred else None}
        if item["kind"] == "candidate":
            evals[name], steps[name], table[name] = ev, item["step_mm"], row
        else:
            controls[name] = {k: v for k, v in row.items() if k != "accepted"} | {"never_accepted_or_selected": True}
    choice = C.select_trial(evals, steps)
    odd = {}
    for s_mm in L.CONTROL_STEP_MM:                    # the odd part of the downforce response along the proposal: (R(+s) - R(-s)) / 2, descriptive
        plus, minus = table.get(L.candidate_name(s_mm)), controls.get(L.control_name(s_mm))
        if plus and minus:
            odd[f"{s_mm:g}"] = {"odd_part_n": (plus["downforce_change_n"] - minus["downforce_change_n"]) / 2.0, "even_part_n": (plus["downforce_change_n"] + minus["downforce_change_n"]) / 2.0,
                                "forward_minus_reverse_n": plus["downforce_change_n"] - minus["downforce_change_n"]}
    return {"verdict": choice["verdict"], "selected": choice["selected"], "baseline": {"downforce_n": base["downforce_n"], "drag_n": base["drag_n"]}, "candidates": table, "controls": controls,
            "proposal_sign_check_descriptive": odd,
            "rules": {"min_downforce_gain_n": C.MIN_DOWNFORCE_GAIN_N, "drag_allowance_n": C.DRAG_ALLOWANCE_N, "geometry_thresholds": inventory["geometry_gate_thresholds"],
                      "authority": "actual primal responses and hard geometry gates; predictions are reference only; controls are never accepted or selected"},
            "interpretation": INTERPRETATION[choice["verdict"]]}


INTERPRETATION = {
    "LOWDIM_ACCEPT": ("An accepted coefficient-space step exists on the fixed four-direction basis (D0, D1, D2, P1): the actual primal downforce improved by more than the nominal resolution "
                      "(10 x the nominal sigma0 of FD-08, not a measured noise) with the drag, volume and SDF-quality gates satisfied. Evidence scope: one trial on the single registered flow grid "
                      "(flow_24), the [80,120] tU/L time-weighted force, deterministic Float32 T4 runs, no reinitialization. This is a capability statement for a fixed low-dimensional basis, not "
                      "a full-field gradient, not OPT-01 (#30), not grid-independent or physical downforce, and not a statement that the proposal direction is a descent direction in general; "
                      "the improvement may be small and may be largely predictable from STEP-01's curvature."),
    "LOWDIM_NO_GO": ("No line-search candidate was accepted: with the registered rules the four-direction basis gave no resolved downforce improvement that satisfied the drag, volume and "
                     "SDF-quality gates. This is a bounded No-Go for this basis, proposal and candidate set, not a statement about low-dimensional optimisation in general."),
    "LOWDIM_INCOMPLETE": "the integrity gates failed: nothing is concluded"}


def clean(x):
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kernel-dir", required=True, type=Path)
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--write", type=Path)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    freeze = jload(args.freeze)
    report = analyze(args.kernel_dir, freeze)
    report["provenance"] = {"freeze_sha256": sha256(args.freeze), "analyzer_sha256": sha256(Path(__file__)), "source_commit": freeze["source_commit"],
                            "kernel_manifest_sha256": sha256(args.kernel_dir / "output_manifest.json") if (args.kernel_dir / "output_manifest.json").is_file() else None}
    if args.check:
        print(json.dumps(clean({"integrity": report["integrity"], "verdict": report["verdict"]}), indent=2, sort_keys=True))
        return
    if args.write is None:
        sys.exit("--write is required unless --check")
    if args.write.exists():
        sys.exit("refusing to overwrite an existing analysis (the analyzer runs once)")
    data = json.dumps(clean(report), indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(report["verdict"], hashlib.sha256(data.encode()).hexdigest())
    if report["verdict"] == "LOWDIM_INCOMPLETE":
        sys.exit(3)


if __name__ == "__main__":
    main()
