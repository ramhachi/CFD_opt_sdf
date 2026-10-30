#!/usr/bin/env python3
"""Run the registered six-item v2 gate exactly once on host-verified R6 data."""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from cfd_sdf.fd08_v2_gate import evaluate_series, load_params
from fd08_v2_campaign_io import response_pair


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        # C5 diagnostic arithmetic is intentionally retained at Decimal precision.
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def flatten_map(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(flatten_map(child, f"{prefix}.{key}" if prefix else key))
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            result.update(flatten_map(child, f"{prefix}[{index}]"))
        return result
    return {prefix: value}


def _fit_groups(gate: dict, reference: dict, bounds: dict):
    yield "full_A", gate["model_a"], reference["model_a"], bounds["model_a"]
    yield "full_B", gate["model_b"], reference["model_b"], bounds["model_b"]
    ref_nested = {row["drop"]: row for row in reference["nested"]}
    bound_nested = {row["drop"]: row for row in bounds["nested"]}
    for row in gate["nested"]:
        for model in ("a", "b"):
            yield (f"nested{row['drop']}_{model}", row[f"model_{model}"],
                   ref_nested[row["drop"]][f"model_{model}"],
                   bound_nested[row["drop"]][f"model_{model}"])
    ref_holdout = {row["index"]: row for row in reference["holdout"]}
    bound_holdout = {row["index"]: row for row in bounds["holdout"]}
    for row in gate["holdout"]:
        yield (f"holdout{row['index']}", row["fit"], ref_holdout[row["index"]]["fit"],
               bound_holdout[row["index"]]["fit"])


def c4_c5_compare(epsilon_mm: list[float], response_n: list[float], params: dict,
                  gate: dict) -> dict[str, Any]:
    numeric = load_script("fd08_v2_numeric_r6", ROOT / "scripts/analyze_fd08_v2_numeric_contract.py")
    forward = load_script("fd08_v2_forward_error_r6", ROOT / "scripts/fd08_v2_forward_error.py")
    reference = numeric.reference_series(epsilon_mm, response_n, params, precision=80, decimal_output=True)
    bound_result = forward.bound_series(epsilon_mm, response_n, params, variant="N1", decimal_output=True)
    bound = bound_result["bounds"]
    primary_semantics = {
        "verdict": gate["verdict"],
        "item_passes": {key: value["passed"] for key, value in gate["items"].items()},
        "model_a_available": gate["model_a"]["available"],
        "model_b_available": gate["model_b"]["available"],
        "nested": [(row["drop"], row["used_for_sign"], row["used_for_stability"],
                    row["model_a"]["available"], row["model_b"]["available"])
                   for row in gate["nested"]],
        "holdouts": [(row["index"], row["passed"], row["fit"]["available"])
                     for row in gate["holdout"]],
    }
    reference_semantics = {
        "verdict": reference["verdict"],
        "item_passes": {key: value["passed"] for key, value in reference["items"].items()},
        "model_a_available": reference["model_a"]["available"],
        "model_b_available": reference["model_b"]["available"],
        "nested": [(row["drop"], row["used_for_sign"], row["used_for_stability"],
                    row["model_a"]["available"], row["model_b"]["available"])
                   for row in reference["nested"]],
        "holdouts": [(row["index"], row["passed"], row["fit"]["available"])
                     for row in reference["holdout"]],
    }
    c4_passed = primary_semantics == reference_semantics

    c5_checks = []
    for label, primary_fit, reference_fit, bound_fit in _fit_groups(gate, reference, bound):
        if not primary_fit.get("available"):
            c5_checks.append({"fit": label, "passed": False, "reason": "primary_fit_unavailable"})
            continue
        if not bound_fit.get("available"):
            c5_checks.append({"fit": label, "passed": False, "reason": "conditional_envelope_unavailable"})
            continue
        scalar_pairs = [
            ("beta_mm[0]", primary_fit["beta"][0], reference_fit["beta_mm"][0], bound_fit["beta_mm"][0]),
            ("beta_mm[1]", primary_fit["beta"][1], reference_fit["beta_mm"][1], bound_fit["beta_mm"][1]),
            ("se_g_n_per_mm", primary_fit["se_g_n_per_mm"], reference_fit["se_g_n_per_mm"],
             bound_fit["se_g_n_per_mm"]),
        ]
        for i in range(2):
            for j in range(2):
                scalar_pairs.append((f"cov_mm[{i}][{j}]", primary_fit["covariance"][i][j],
                                     reference_fit["cov_mm"][i][j], bound_fit["cov_mm"][i][j]))
        fit_ok = True
        max_ratio = Decimal(0)
        checks = []
        for metric, actual, expected, allowance in scalar_pairs:
            if expected is None or allowance is None:
                fit_ok = False
                checks.append({"metric": metric, "passed": False, "reason": "C5 value unavailable"})
                continue
            actual_d = Decimal.from_float(float(actual))
            error = abs(actual_d - expected)
            limit = allowance if isinstance(allowance, Decimal) else Decimal.from_float(float(allowance))
            passed = error <= limit
            fit_ok &= passed
            if limit > 0:
                max_ratio = max(max_ratio, error / limit)
            elif error == 0:
                max_ratio = max(max_ratio, Decimal(0))
            else:
                max_ratio = Decimal("Infinity")
            checks.append({"metric": metric, "absolute_error": str(error),
                           "conditional_C5_bound": str(limit), "passed": passed})
        c5_checks.append({"fit": label, "passed": fit_ok,
                          "maximum_error_over_bound": str(max_ratio), "checks": checks})
    c5_passed = (bound_result["diagnostics"]["valid"] is True
                 and bound_result["diagnostics"]["ratio_bounds_valid"] is True
                 and all(row["passed"] for row in c5_checks))
    return {
        "C4": {"passed": c4_passed, "primary_semantics": primary_semantics,
               "decimal_reference_semantics": reference_semantics,
               "reference_independence": False},
        "C5": {
            "passed": c5_passed,
            "kind": "conditional fit/operand backward-error engineering envelope",
            "universal_LAPACK_or_SVD_guarantee": False,
            "diagnostics": bound_result["diagnostics"],
            "fit_checks": c5_checks,
        },
        "C1_C2_C3": "diagnostic only",
    }


def load_terminal(args):
    verify_path = args.host_verification
    sidecar = verify_path.with_suffix(verify_path.suffix + ".sha256")
    if not verify_path.is_file() or not sidecar.is_file() or sidecar.read_text().strip() != sha(verify_path):
        raise ValueError("host terminal verification or its SHA sidecar is missing/mismatched")
    host = json.loads(verify_path.read_text())
    criteria_sha = sha(args.criteria)
    if (host.get("status") != "PASS_TERMINAL_INTEGRITY"
            or host.get("analysis_performed") is not False
            or host.get("criteria_sha256") != criteria_sha
            or host.get("state_count") != 49
            or host.get("unexpected_state_count") != 0):
        raise ValueError("R6 terminal verification is not a complete exact 49/49 pass")
    criteria = json.loads(args.criteria.read_text())
    if criteria.get("kind") != "fd08_v2_r6_calibration" or criteria.get("status") != "registered_not_run":
        raise ValueError("R6 immutable criteria identity/status mismatch")
    output = args.download
    markers = list(output.rglob("DONE"))
    if len(markers) != 1:
        raise ValueError("expected exactly one verified R6 output directory")
    return criteria, host, markers[0].parent


def analyze(args) -> dict:
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite the one-shot analyzer output: {args.output}")
    criteria, host, output = load_terminal(args)
    params = load_params(ROOT / "src/cfd_sdf/fd08_v2_gate_params.json")
    if params != criteria["numeric_contract"]["parameters"]:
        raise ValueError("T2 parameters differ from the immutable R6 contract")
    state_rows = {row["name"]: row for row in criteria["state_inventory"]}
    by_series = {}
    for row in criteria["state_inventory"]:
        if row["kind"] != "calibration":
            continue
        key = (row["direction_id"], row["epsilon_mm"])
        by_series.setdefault(key, {})[row["sign"]] = row
    dir_resp = {}
    for direction in criteria["direction_inventory"]["directions"]:
        for response_name in ("drag", "downforce"):
            epsilons, observations = [], []
            force_audits = []
            for epsilon in criteria["ladder"]["epsilon_mm"]:
                signed = by_series[(direction, epsilon)]
                plus_row, minus_row = signed[1], signed[-1]
                pair = response_pair(
                    output / "states" / plus_row["name"] / "flow_24.forces.csv",
                    output / "states" / minus_row["name"] / "flow_24.forces.csv",
                    criteria,
                )[response_name]
                epsilons.append(float(epsilon))
                observations.append(pair["response_n"])
                force_audits.append({"epsilon_mm": float(epsilon), **pair})
            gate = evaluate_series(epsilons, observations, params)
            comparison = c4_c5_compare(epsilons, observations, params, gate)
            raw_verdict = gate["verdict"]
            effective = raw_verdict if comparison["C4"]["passed"] and comparison["C5"]["passed"] else "UNRESOLVED"
            model_a = gate["model_a"]
            x = np.column_stack((epsilons, np.asarray(epsilons) ** 3))
            if model_a["available"] and model_a["weights"] is not None:
                weights = np.asarray(model_a["weights"], dtype=np.float64)
                weighted_x = x * np.sqrt(weights[:, None])
                condition_2 = float(np.linalg.cond(weighted_x))
                leverage = np.diag(weighted_x @ np.linalg.pinv(weighted_x))
                max_leverage = float(np.max(leverage))
            else:
                condition_2 = None
                max_leverage = None
            holdout_ratios = [
                row["error_n"] / row["limit_n"] if row["error_n"] is not None and row["limit_n"] > 0 else None
                for row in gate["holdout"]
            ]
            holdout_max = max((value for value in holdout_ratios if value is not None), default=None)
            series = {
                "direction_id": direction,
                "response": response_name,
                "epsilon_mm": epsilons,
                "response_s_n": observations,
                "q_n_per_m": gate["q_n_per_m"],
                "model_a": gate["model_a"],
                "model_b": gate["model_b"],
                "relative_se": gate["items"]["relative_se"]["value"],
                "nested_max_relative_shift": gate["items"]["nested_stability"]["maximum_relative_shift"],
                "model_difference": gate["items"]["model_difference"]["value"],
                "holdout_max_error_over_limit": holdout_max,
                "holdout_error_over_limit": holdout_ratios,
                "magnitude_count": gate["items"]["magnitude"]["point_count"],
                "sign": gate["items"]["sign"]["signs"],
                "condition_2_weighted_design": condition_2,
                "max_weighted_leverage": max_leverage,
                "items": gate["items"],
                "primary_gate_verdict": raw_verdict,
                "numeric_consistency": comparison,
                "verdict": effective,
                "force_history_recomputation": force_audits,
            }
            dir_resp[(direction, response_name)] = series
    ordered = [dir_resp[(direction, response)] for direction in criteria["direction_inventory"]["directions"]
               for response in ("drag", "downforce")]
    from cfd_sdf.fd08_v2_campaign import campaign_verdict
    overall = campaign_verdict([row["verdict"] for row in ordered])
    result = {
        "kind": "fd08_v2_r6_analysis",
        "evidence_class": "host_analyzed_only_after_exact_terminal_integrity_pass",
        "criteria_sha256": sha(args.criteria),
        "criteria_source_commit": criteria["source_commit"],
        "terminal_verification_sha256": sha(args.host_verification),
        "terminal_output_manifest_sha256": host["download_output_manifest_sha256"],
        "analyzer_source_sha256": sha(Path(__file__)),
        "parameter_sha256": sha(ROOT / "src/cfd_sdf/fd08_v2_gate_params.json"),
        "T2_classification": "arbitrary-provisional diagnostic operating contract only",
        "series": ordered,
        "series_count": len(ordered),
        "all_series_pass": sum(row["verdict"] == "PASS" for row in ordered) == 8,
        "verdict": overall,
        "qualification_flags": criteria["qualification_flags"],
        "interpretation": "frozen Candidate C/v17/flow_24/approved four-direction local diagnostic; not #23 delta, gradient accuracy, physical truth, grid independence, or epsilon-to-zero truth",
        "analysis_runs": 1,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False,
                                      default=_json_default) + "\n")
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(sha(args.output) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", type=Path, default=ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_criteria.json")
    parser.add_argument("--host-verification", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/terminal_verification.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_analysis.json")
    result = analyze(parser.parse_args())
    print(json.dumps({"verdict": result["verdict"], "series_count": result["series_count"],
                      "analysis_runs": result["analysis_runs"], "output": str(parser.parse_args().output)},
                     sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
