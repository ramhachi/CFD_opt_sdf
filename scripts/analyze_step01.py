#!/usr/bin/env python3
"""STEP-01 (#47) host analyzer: integrity and gates of the three T4 kernels, then the pre-registered finite-step secant quantities (run once).

Primary quantity: the centered secant  g_sec(s) = [R(+s) - R(-s)] / (2 s)  (N/m) per direction x response, with eta_even(s) = |R(+s)+R(-s)-2R(0)| / |R(+s)-R(-s)|.
Reported descriptively per series: sign stability, the secant drift radius (where g_sec bends by 30% / 50% relative to the smallest step), the 30% / 50% agreement radius
against FD-08's local slope g-hat (Model A; NOT the epsilon->0 derivative, so an agreement radius is not a statement that a step is correct), g_sec / g-hat and
(g_sec - g-hat) / SE (SE is the nominal T2 value, not a confidence interval), and the finite-step additivity of the two combined directions.
It is not a gradient qualification, does not change FD-08, any flag, delta or GRAD-03.  Verdicts: STEP01_RECORDED | STEP01_INCOMPLETE.
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
import step01_states as S  # noqa: E402
from cfd_sdf import step01_contract as C  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

E = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
FORMAL_CRITERIA = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
RESPONSES = ("drag", "downforce")
TOLERANCES = C.AGREEMENT_TOLERANCES            # (0.30, 0.50)
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


# ---- per-kernel integrity and the host recomputation of every state -------------------------------------------------------------------------------------------
def check_kernel(out: Path, kernel: str, freeze: dict, inventory: dict, criteria: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    states: dict = {}
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done == error:
        failures.append(f"kernel {kernel}: exactly one of DONE/ERROR.txt must exist (done={done}, error={error})")
    index = jload(out / "step01_index.json") if (out / "step01_index.json").is_file() else {}
    identity = jload(out / "run_identity.json") if (out / "run_identity.json").is_file() else {}
    if index.get("status") != "COMPLETE" or index.get("kernel") != kernel:
        failures.append(f"kernel {kernel}: step01_index status {index.get('status')!r}")
    if identity.get("source_commit") != freeze["source_commit"] or identity.get("failure_stage") is not None:
        failures.append(f"kernel {kernel}: run identity source commit / failure stage")
    if not freeze["pins"] or not freeze["direction_files"]:
        failures.append(f"kernel {kernel}: the freeze has no pins or direction files to verify")
    for rel_path, digest in freeze["pins"].items():
        if identity.get("verified", {}).get(rel_path) != digest:
            failures.append(f"kernel {kernel}: pin not verified on the kernel: {rel_path}")
    for rel_path, digest in freeze["direction_files"].items():
        if identity.get("verified", {}).get(rel_path) != digest:
            failures.append(f"kernel {kernel}: direction file not verified on the kernel: {rel_path}")
    if identity.get("fd08_baseline_csv_sha256") != freeze["fd08_baseline"]["forces_csv_sha256"]:
        failures.append(f"kernel {kernel}: the FD-08 baseline CSV pin differs from the freeze")
    manifest = jload(out / "output_manifest.json").get("files") if (out / "output_manifest.json").is_file() else None
    if not isinstance(manifest, dict):
        failures.append(f"kernel {kernel}: output_manifest.json missing or malformed")
    else:
        required = {"step01_index.json", "run_identity.json", "nvidia_smi.csv"} | {f"states/{n}/{f}" for n in inventory["kernels"][kernel] for f in ("flow_24.forces.csv", "flow_24.summary.json", "W4_JOB_DONE")}
        if not required <= set(manifest):
            failures.append(f"kernel {kernel}: the manifest does not list every required output file")
        for rel_path, digest in manifest.items():
            p = out / rel_path
            if not p.is_file() or sha256(p) != digest:
                failures.append(f"kernel {kernel}: manifest mismatch: {rel_path}")
    gpu = (out / "nvidia_smi.csv").read_text() if (out / "nvidia_smi.csv").is_file() else ""
    if not gpu.strip() or any("Tesla T4" not in r for r in gpu.strip().splitlines()):
        failures.append(f"kernel {kernel}: the recorded GPU is not a Tesla T4")
    plan = inventory["kernels"][kernel]
    listed = [e.get("name") for e in index.get("states", [])]
    if listed != plan or not all(e.get("complete") for e in index.get("states", [])):
        failures.append(f"kernel {kernel}: the completed states are not exactly the registered plan")
    present = sorted(p.name for p in (out / "states").iterdir() if p.is_dir()) if (out / "states").is_dir() else []
    if present != sorted(plan):
        failures.append(f"kernel {kernel}: the state directories differ from the plan")
    by_name = {r["name"]: r for r in inventory["states"] if r["kernel"] == kernel}
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
            states[name] = {"drag_n": host["drag_n"], "downforce_n": host["downforce_n"], "csv_sha256": entry["forces_csv_sha256"], "raw_samples": host["raw_sample_count"]}
        except Exception as err:  # noqa: BLE001  any malformed state output is an integrity failure, never a crash
            failures.append(f"kernel {kernel}: state {name}: {err}")
    return failures, states


# ---- the registered quantities -------------------------------------------------------------------------------------------------------------------------------
def series_table(res: dict, inventory: dict, fits: dict) -> dict:
    """Per direction x response: the signed responses, the centered secant, eta_even, resolved flags and the registered descriptive statistics."""
    out = {}
    for direction in S.SINGLE_DIRECTIONS:
        kernel = "a" if direction in S.KERNELS["a"] else "b"
        for resp in RESPONSES:
            r0 = res[kernel][S.BASELINE_NAME][f"{resp}_n"]
            steps, gs, etas, resolved, rows = [], [], [], [], []
            for step in S.STEP_MM:
                rp = res[kernel][S.single_name(direction, step, +1)][f"{resp}_n"]
                rm = res[kernel][S.single_name(direction, step, -1)][f"{resp}_n"]
                g = C.centered_secant(rp, rm, step / 1000.0)
                ok = C.is_resolved(rp - r0, rm - r0)
                steps.append(step); gs.append(g); resolved.append(ok); etas.append(C.even_ratio(rp, rm, r0))
                rows.append({"step_mm": step, "r_plus_n": rp, "r_minus_n": rm, "r0_n": r0, "delta_plus_n": rp - r0, "delta_minus_n": rm - r0, "g_sec_n_per_m": g,
                             "one_sided_secant_plus_n_per_m": (rp - r0) / (step / 1000.0), "one_sided_secant_minus_n_per_m": (rm - r0) / (-step / 1000.0),
                             "eta_even": etas[-1], "resolved": ok})
            fit = fits[f"{direction}|{resp}"]
            g_hat, se = float(fit["g_n_per_m"]), float(fit["se_g_n_per_m"])
            if not (math.isfinite(g_hat) and g_hat != 0 and math.isfinite(se) and se > 0):
                raise ValueError(f"unusable FD-08 fit for {direction}|{resp}")
            for row in rows:
                row["g_sec_over_g_hat"] = row["g_sec_n_per_m"] / g_hat
                row["diff_over_nominal_se"] = (row["g_sec_n_per_m"] - g_hat) / se
            stab = C.sign_stability(gs, g_hat, resolved)
            through = None                       # the last RESOLVED step before the first sign flip; None when no step is resolved
            for i, (step, ok) in enumerate(zip(steps, resolved)):
                if stab["first_flip_index"] is not None and i >= stab["first_flip_index"]:
                    break
                if ok:
                    through = step
            ref_ok = resolved[0] and gs[0] != 0
            out[f"{direction}|{resp}"] = {
                "rows": rows, "g_hat_n_per_m": g_hat, "se_g_hat_n_per_m_nominal": se, "sign_stability": stab, "sign_stable_through_mm": through,
                "secant_drift": {f"{int(t * 100)}pct": (C.secant_drift_radius(steps, gs, t) if ref_ok else None) for t in TOLERANCES},
                "agreement_radius_mm": {f"{int(t * 100)}pct": C.agreement_radius(steps, gs, g_hat, t) for t in TOLERANCES},
                "eta_even_by_step": etas, "g_hat_support": "FD-08 calibrated range 0.5-5 mm; steps above 5 mm are extrapolations of the local slope"}
    return out


def combo_table(res: dict, inventory: dict) -> dict:
    out = {}
    for pair in S.COMBOS:
        key = "+".join(pair)
        comp = inventory["combined_directions"][key]["component_step_mm"]
        for resp in RESPONSES:
            for sign in (-1, 1):
                combo = res["c"][S.combo_name(pair, sign)][f"{resp}_n"] - res["c"][S.BASELINE_NAME][f"{resp}_n"]
                parts, spread = 0.0, 0.0                      # spread = sum over the two components of |PCHIP - linear|
                for direction in pair:
                    kernel = "a" if direction in S.KERNELS["a"] else "b"
                    r0 = res[kernel][S.BASELINE_NAME][f"{resp}_n"]
                    xs = [s * sg for s in S.STEP_MM for sg in (-1, 1)]
                    ys = [res[kernel][S.single_name(direction, s, sg)][f"{resp}_n"] - r0 for s in S.STEP_MM for sg in (-1, 1)]
                    q = C.interpolate_signed_response(xs, ys, sign * comp)
                    parts += q["pchip_n"]; spread += q["interpolation_spread_n"]
                    out.setdefault(key, {}).setdefault(f"{resp}|{'plus' if sign > 0 else 'minus'}", {}).setdefault("components", {})[direction] = q
                cell = out[key][f"{resp}|{'plus' if sign > 0 else 'minus'}"]
                pred_linear = sum(cell["components"][d]["linear_n"] for d in pair)
                cell.update({"component_step_mm": comp, "delta_combo_n": combo, "predicted_pchip_n": parts, "predicted_linear_n": pred_linear, "prediction_spread_n": spread,
                             "additivity": C.additivity_defect(combo, parts, spread), "additivity_linear_prediction": C.additivity_defect(combo, pred_linear, spread),
                             "resolved": C.is_resolved(combo)})
    return out


def contract_summary(series: dict, combos: dict) -> dict:
    """What #48 can take over: per series the sign-stable range, the drift radii and the agreement radii; the worst combined-direction additivity defect."""
    per_series = {k: {"sign_stable_through_mm": v["sign_stable_through_mm"], "secant_drift": v["secant_drift"], "agreement_radius_mm": v["agreement_radius_mm"],
                      "first_flip_index": v["sign_stability"]["first_flip_index"], "unresolved_steps": v["sign_stability"]["unresolved_indices"]} for k, v in series.items()}
    defects = [(cell["additivity"]["relative_to_combo"], f"{key}|{name}") for key, cells in combos.items() for name, cell in cells.items()
               if cell["resolved"] and math.isfinite(cell["additivity"]["relative_to_combo"])]
    worst = max(defects) if defects else None
    return {"per_series": per_series, "worst_combined_additivity_relative_defect": None if worst is None else {"relative_defect": worst[0], "cell": worst[1]},
            "all_series_sign_constant_through_12.5mm": all(v["sign_stability"]["constant_over_resolved_steps"] for v in series.values())}


def analyze(dirs: dict[str, Path], freeze: dict | None, inventory: dict | None = None, formal: dict | None = None) -> dict:
    inventory = inventory if inventory is not None else jload(E / "inventory.json")
    formal = formal if formal is not None else jload(FORMAL_CRITERIA)
    criteria = {"measurement": formal["measurement"]}
    fits = formal["calibration_binding"]["fits"]
    report: dict = {"kind": "step01_finite_step_secant_analysis", "selected_delta": None, "grad03_verdict": None, "no_gradient_claim": True, "fd08_verdict_unchanged": True,
                    "qualification_flags": {k: False for k in FLAGS}}
    failures: list[str] = []
    res: dict = {}
    if freeze is None:
        raise ValueError("a freeze is required")
    # everything the analysis computes with is checked against the frozen hashes: the analyzer itself, its imports, the force reader, the formal criteria and the frozen g-hat fits
    for name, path in (("analyzer", Path(__file__)), ("contract", ROOT / "src/cfd_sdf/step01_contract.py"), ("states_module", ROOT / "scripts/step01_states.py"),
                       ("force_io", ROOT / "scripts/fd08_v2_campaign_io.py"), ("formal_criteria", FORMAL_CRITERIA)):
        if sha256(path) != freeze["file_hashes"].get(name):
            failures.append(f"{name} differs from (or is missing in) the freeze")
    if hashlib.sha256((json.dumps(inventory, sort_keys=True, indent=2) + "\n").encode()).hexdigest() != freeze["file_hashes"].get("inventory_canonical_json"):
        failures.append("the inventory differs from the frozen inventory")
    for key, frozen in freeze.get("fd08_g_hat_fits", {}).items():
        if (fits.get(key) or {}).get("g_n_per_m") != frozen["g_n_per_m"] or (fits.get(key) or {}).get("se_g_n_per_m") != frozen["se_g_n_per_m"]:
            failures.append(f"the g-hat / SE of {key} differs from the frozen value")
    if len(freeze.get("fd08_g_hat_fits", {})) != 8:
        failures.append("the freeze does not hold the 8 FD-08 fits")
    for k in S.KERNELS:
        f, res[k] = check_kernel(dirs[k], k, freeze, inventory, criteria)
        failures += f
    ref = inventory["fd08_baseline_reference"]
    for k in S.KERNELS:
        base = res[k].get(S.BASELINE_NAME)
        if not base:
            failures.append(f"kernel {k}: no baseline")
            continue
        if base["csv_sha256"] != ref["forces_csv_sha256"]:
            failures.append(f"kernel {k}: the baseline force CSV differs from FD-08's baseline_v17")
        for q in ("drag_n", "downforce_n"):
            if rel(base[q], ref["host_recomputed_n"][q]) > BASELINE_REL:
                failures.append(f"kernel {k}: baseline {q} differs from FD-08's baseline_v17")
    report["integrity"] = {"pass": not failures, "failures": failures}
    if failures:
        report["verdict"] = "STEP01_INCOMPLETE"
        return report
    try:
        series = series_table(res, inventory, fits)
        combos = combo_table(res, inventory)
    except Exception as err:  # noqa: BLE001  a computation failure is never a recorded result
        report["integrity"] = {"pass": False, "failures": [f"analysis error: {type(err).__name__}: {err}"]}
        report["verdict"] = "STEP01_INCOMPLETE"
        return report
    report.update({"verdict": "STEP01_RECORDED", "series": series, "combined_directions": combos, "contract_inputs_for_lowdim": contract_summary(series, combos),
                   "interpretation": INTERPRETATION, "responses_n": {k: {n: {q: v[q] for q in ("drag_n", "downforce_n")} for n, v in res[k].items()} for k in res}})
    return report


INTERPRETATION = ("Finite-step secant responses of the Candidate C operator at 2.5-12.5 mm (0.1-0.5 h) along the registered FD-08 directions and two combined directions. "
                  "These are measured response changes, not derivatives and not a gradient qualification; the agreement radii compare with FD-08's Model-A local slope, which is "
                  "itself an extrapolation above 5 mm, and say nothing about whether a step is correct. The standard error used for (g_sec - g-hat)/SE is the nominal T2 value. "
                  "No flag, FD-08 verdict, delta or GRAD-03 verdict is changed.")


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
    p.add_argument("--kernel-dir", action="append", required=True, metavar="KEY=PATH", help="a=..., b=..., c=... (the downloaded kernel output directories)")
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--write", type=Path)
    p.add_argument("--check", action="store_true", help="integrity and gates only; writes nothing")
    args = p.parse_args()
    dirs = {kv.split("=", 1)[0]: Path(kv.split("=", 1)[1]) for kv in args.kernel_dir}
    if set(dirs) != set(S.KERNELS):
        sys.exit("--kernel-dir must give a, b and c")
    freeze = jload(args.freeze)
    report = analyze(dirs, freeze)
    report["provenance"] = {"freeze_sha256": sha256(args.freeze), "analyzer_sha256": sha256(Path(__file__)), "source_commit": freeze["source_commit"],
                            "kernel_manifest_sha256": {k: (sha256(v / "output_manifest.json") if (v / "output_manifest.json").is_file() else None) for k, v in dirs.items()}}
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
    if report["verdict"] != "STEP01_RECORDED":
        sys.exit(3)


if __name__ == "__main__":
    main()
