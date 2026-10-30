#!/usr/bin/env python3
"""Frozen synthetic-only FD-08 v2 measurement; no target-data path or solver."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.fd08_v2_gate import classify_result, evaluate_series, load_params

OUTPUT = ROOT / "docs/evidence/fd08_v2_stage1_2026_10_06"
PARAMS = ROOT / "src/cfd_sdf/fd08_v2_gate_params.json"
BASE_SEED = 461006
TRIALS = 2000
TOLERANCES = (0.05, 0.10, 0.15, 0.20)
LADDERS = {6: np.geomspace(0.5, 5, 6), 8: np.geomspace(0.3, 5, 8)}
EXTENDED_LADDER = np.geomspace(0.5, 15, 7)
BLIND_SCENARIOS = (1, 2, 3, 7, 9, 12, 15, 23, 18, 27)
FLAGS = {key: False for key in (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}


def rounded(value):
    if isinstance(value, dict):
        return {str(key): rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [rounded(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(format(value, ".12g"))
    if isinstance(value, np.integer):
        return int(value)
    return value


def save_json(path, value):
    path.write_text(json.dumps(rounded(value), sort_keys=True, allow_nan=False,
                               indent=2) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scenarios():
    rows = []
    def add(family, g, c_q=0., sigma=0., w=0., curvature=0.):
        number = len(rows) + 1
        rows.append(dict(number=number, id=f"{family}{number:02d}", family=family,
                         g_true_n_per_m=g, c_q_n_per_m_per_mm2=c_q,
                         absolute_sigma_n=sigma, relative_w=w,
                         curvature_ratio_at_5mm=curvature,
                         false_rejection_applicable=family in ("a", "b") and sigma <= 3e-6))
    truth = ((-0.17, 0.), (-0.104, -0.00104))
    for g, c in truth:
        add("a", g, c)
    for g, c in truth:
        for sigma in (1.5e-6, 3e-6, 4e-6):
            add("b", g, c, sigma)
    for g, c in truth:
        for w in (.04, .07):
            add("c", g, c, 3e-6, w)
    for g in (-.104, -.17):
        for ratio in (.10, .15, .25, .50, 1., 1.5, 2.):
            add("d", g, sigma=1.5e-6, curvature=ratio)
    add("e", -.02, sigma=3e-6)
    return rows


def observation(scenario, epsilon, rng):
    # Fixed draw order: each point's absolute noise, then relative deviation.
    draws = rng.standard_normal((len(epsilon), 2))
    g = scenario["g_true_n_per_m"]
    if scenario["family"] == "d":
        # k has g's sign; curvature definition always refers to 5 mm.
        q = g * (1 + scenario["curvature_ratio_at_5mm"] * np.abs(epsilon) / 5)
    else:
        q = g + scenario["c_q_n_per_m_per_mm2"] * epsilon**2
    response = q * epsilon / 1000
    return (response * (1 + scenario["relative_w"] * draws[:, 1])
            + scenario["absolute_sigma_n"] * draws[:, 0])


def parameter_sets(params):
    result = {"default": params}
    for tolerance in TOLERANCES:
        result[f"{tolerance:.0%}"] = dict(params, **{key: tolerance for key in (
            "tol_se", "tol_nested", "tol_model", "tol_hold")})
    return result


def freeze(output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "prerun_freeze.json").exists():
        raise ValueError("freeze exists: do not overwrite the pre-run record")
    note = output / "stage1_note.md"
    text = note.read_text(encoding="utf-8")
    if not all(token in text for token in ("A1", "A4", "95%", "5%", "Stage 1 FAILED")):
        raise ValueError("acceptance conditions must be recorded before freeze")
    snapshot = output / "prerun_note.md"
    snapshot.write_bytes(note.read_bytes())
    sources = [PARAMS, ROOT / "src/cfd_sdf/fd08_v2_gate.py", Path(__file__),
               ROOT / "docs/issues/46_fd08_v2_stage1_instruction_2026_10_06.md", snapshot]
    save_json(output / "prerun_freeze.json", {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "solver_free_design_and_simulation_unregistered",
        "params_status": "provisional_unapproved", "params": load_params(),
        "sha256": {str(path.relative_to(ROOT)): sha256(path) for path in sources},
        "numpy_version": np.__version__, "python_version": platform.python_version(),
        "base_seed": BASE_SEED, "trial_count": TRIALS, "scenarios": scenarios(),
        "ladders_mm": LADDERS, "extended_d_ladder_mm": EXTENDED_LADDER,
        "sensitivity_simultaneous_tolerances": TOLERANCES,
        "blind_scenario_numbers": BLIND_SCENARIOS,
        "blind_seed_offset": 900000,
        "draw_order": "per point: absolute standard normal, relative standard normal; always consume both",
        "qualification_flags": FLAGS})
    print(f"Frozen params sha256={sha256(PARAMS)}; no simulation run.", flush=True)


def validate_freeze(output):
    record = json.loads((output / "prerun_freeze.json").read_text(encoding="utf-8"))
    for relative, expected in record["sha256"].items():
        if sha256(ROOT / relative) != expected:
            raise ValueError(f"frozen input changed: {relative}; protocol violation, stop")
    if record["numpy_version"] != np.__version__:
        raise ValueError("numpy version differs from frozen environment")
    return record


def fixed_inputs(output):
    params = load_params()
    cases = []
    for number in BLIND_SCENARIOS:
        scenario = scenarios()[number - 1]
        for count, epsilon in LADDERS.items():
            seed = BASE_SEED + 900000 + 1000 * number + count
            rng = np.random.Generator(np.random.PCG64(seed))
            cases.append(dict(id=f"{scenario['id']}_n{count}", scenario=scenario, seed=seed,
                              epsilon_mm=epsilon, response_n=observation(scenario, epsilon, rng),
                              params=params))
    save_json(output / "synthetic_inputs.json", {"cases": cases, "numpy_version": np.__version__,
              "base_seed": BASE_SEED, "seed_offset": 900000,
              "mapping": [{"id": case["id"], "scenario_number": case["scenario"]["number"],
                           "ladder_points": len(case["epsilon_mm"]), "seed": case["seed"]}
                          for case in cases]})
    # Evaluate the exact rounded JSON delivered to the independent checker.
    saved = json.loads((output / "synthetic_inputs.json").read_text(encoding="utf-8"))
    results = [{"id": case["id"], "result": evaluate_series(case["epsilon_mm"],
               case["response_n"], case["params"])} for case in saved["cases"]]
    save_json(output / "primary_fixed20_results.json", {"cases": results})


def measure(scenario, epsilon, params):
    count = len(epsilon)
    seed = BASE_SEED + 1000 * scenario["number"] + count
    rng = np.random.Generator(np.random.PCG64(seed))
    variants = parameter_sets(params)
    counts = {key: {verdict: 0 for verdict in ("PASS", "FAIL", "UNRESOLVED")}
              for key in variants}
    errors, estimates = [], []
    false_pass = dict.fromkeys(variants, 0)
    false_reject = dict.fromkeys(variants, 0)
    for _ in range(TRIALS):
        response = observation(scenario, epsilon, rng)
        result = evaluate_series(epsilon, response, params)
        estimate = result["model_a"]["g_n_per_m"]
        if estimate is None:
            raise ValueError("synthetic fit unexpectedly unavailable")
        error = abs(estimate - scenario["g_true_n_per_m"]) / abs(scenario["g_true_n_per_m"])
        errors.append(error)
        estimates.append(estimate)
        for key, variant in variants.items():
            verdict = result["verdict"] if key == "default" else classify_result(result, variant)
            counts[key][verdict] += 1
            false_pass[key] += verdict == "PASS" and error > .20
            false_reject[key] += (scenario["false_rejection_applicable"]
                                  and verdict == "FAIL" and error <= .05)
    return [dict(scenario=scenario, ladder_points=count, epsilon_mm=epsilon, seed=seed,
                 tolerance_label=key, params=variant, trials=TRIALS,
                 verdict_counts=counts[key],
                 verdict_rates={verdict: value / TRIALS for verdict, value in counts[key].items()},
                 g_bias_median_n_per_m=float(np.median(np.array(estimates) - scenario["g_true_n_per_m"])),
                 relative_error_p50=float(np.quantile(errors, .5)),
                 relative_error_p90=float(np.quantile(errors, .9)),
                 false_pass_count=int(false_pass[key]), false_pass_rate=false_pass[key] / TRIALS,
                 false_rejection_count=int(false_reject[key]) if scenario["false_rejection_applicable"] else None,
                 false_rejection_rate=false_reject[key] / TRIALS if scenario["false_rejection_applicable"] else None)
            for key, variant in variants.items()]


def acceptance(rows):
    default = [row for row in rows if row["tolerance_label"] == "default"]
    a1 = [row for row in default if row["scenario"]["false_rejection_applicable"]]
    a4 = [row for row in default if not (row["scenario"]["family"] == "d"
                                        and row["scenario"]["curvature_ratio_at_5mm"] >= 1)]
    failures_a1 = [dict(scenario=row["scenario"]["id"], ladder_points=row["ladder_points"],
                       pass_rate=row["verdict_rates"]["PASS"]) for row in a1
                   if row["verdict_rates"]["PASS"] < .95]
    failures_a4 = [dict(scenario=row["scenario"]["id"], ladder_points=row["ladder_points"],
                       false_pass_rate=row["false_pass_rate"]) for row in a4 if row["false_pass_rate"] >= .05]
    return {"A1": {"passed": not failures_a1, "tested_rows": len(a1), "failures": failures_a1,
                   "minimum_pass_rate": min(row["verdict_rates"]["PASS"] for row in a1)},
            "A4": {"passed": not failures_a4, "tested_rows": len(a4), "failures": failures_a4,
                   "maximum_false_pass_rate": max(row["false_pass_rate"] for row in a4)},
            "stage1_status": "Stage 1 FAILED" if failures_a1 or failures_a4 else "Stage 1 PASSED"}


def run(output):
    record = validate_freeze(output)
    if (output / "simulation_result.json").exists():
        raise ValueError("result exists: preserve the first run; use --replay-output for exact reproduction")
    fixed_inputs(output)
    params = load_params()
    rows, extended = [], []
    for scenario in scenarios():
        for epsilon in LADDERS.values():
            rows.extend(measure(scenario, epsilon, params))
        print(f"measured {scenario['id']} ({scenario['number']}/27)", flush=True)
    for scenario in scenarios():
        if scenario["family"] == "d":
            extended.extend(measure(scenario, EXTENDED_LADDER, params))
            print(f"extended15mm {scenario['id']}", flush=True)
    result = {"evidence_class": "solver_free_design_and_simulation_unregistered",
              "numpy_version": np.__version__, "base_seed": BASE_SEED, "trials_per_row": TRIALS,
              "params_sha256": sha256(PARAMS), "prerun_freeze_sha256": sha256(output / "prerun_freeze.json"),
              "rows": rows, "extended15mm_rows_report_only": extended,
              "acceptance": acceptance(rows), "qualification_flags": FLAGS}
    save_json(output / "simulation_result.json", result)
    print(json.dumps(result["acceptance"], sort_keys=True, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="record hashes without running any simulation")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--replay-output", type=Path, help="reproduce unchanged frozen design in a fresh directory")
    args = parser.parse_args()
    if args.freeze:
        if args.replay_output:
            parser.error("--freeze and --replay-output cannot be combined")
        freeze(args.output)
    elif args.replay_output:
        validate_freeze(args.output)
        args.replay_output.mkdir(parents=True, exist_ok=False)
        (args.replay_output / "prerun_freeze.json").write_bytes((args.output / "prerun_freeze.json").read_bytes())
        run(args.replay_output)
    else:
        run(args.output)


if __name__ == "__main__":
    main()
