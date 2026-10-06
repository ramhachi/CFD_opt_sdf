#!/usr/bin/env python3
"""Evaluate all 24 frozen predict-then-run formal comparisons without refitting."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from cfd_sdf.fd08_v2_campaign import (
    campaign_verdict,
    classify_formal_comparison,
    formal_prediction,
)
from fd08_v2_campaign_io import response_pair


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite formal one-shot result: {args.output}")
    criteria_sha = sha(args.criteria)
    if args.criteria.with_suffix(args.criteria.suffix + ".sha256").read_text().strip() != criteria_sha:
        raise ValueError("formal criteria sidecar mismatch")
    criteria = json.loads(args.criteria.read_text())
    verification = json.loads(args.host_verification.read_text())
    if args.host_verification.with_suffix(args.host_verification.suffix + ".sha256").read_text().strip() != sha(args.host_verification):
        raise ValueError("formal terminal verification SHA sidecar mismatch")
    binding = criteria["calibration_binding"]
    r6_analysis_sha = sha(args.r6_analysis)
    if (criteria.get("kind") != "fd08_v2_formal_validation"
            or binding.get("verdict") != "PASS"
            or verification.get("kind") != "fd08_v2_formal_host_terminal_verification"
            or verification.get("status") != "PASS_TERMINAL_INTEGRITY"
            or verification.get("state_count") != 25
            or verification.get("unexpected_state_count") != 0
            or binding.get("result_sha256") != r6_analysis_sha):
        raise ValueError("formal preregistration or exact 25/25 terminal chain failed")
    r6_analysis = json.loads(args.r6_analysis.read_text())
    if r6_analysis.get("verdict") != "PASS" or r6_analysis.get("series_count") != 8:
        raise ValueError("calibration is not a complete R6 PASS")
    markers = list(args.download.rglob("DONE"))
    if len(markers) != 1:
        raise ValueError("expected one verified formal output directory")
    output = markers[0].parent
    params = binding["T2_parameters"]
    state_map = {}
    for row in criteria["state_inventory"]:
        if row["kind"] == "formal":
            state_map.setdefault((row["direction_id"], row["epsilon_mm"]), {})[row["sign"]] = row
    comparisons = []
    for direction in criteria["direction_inventory"]["directions"]:
        for response in ("drag", "downforce"):
            fit = binding["fits"][f"{direction}|{response}"]
            for epsilon in criteria["formal_epsilon"]["epsilon_mm"]:
                signs = state_map[(direction, epsilon)]
                pair = response_pair(
                    output / "states" / signs[1]["name"] / "flow_24.forces.csv",
                    output / "states" / signs[-1]["name"] / "flow_24.forces.csv",
                    criteria,
                )[response]
                predicted = formal_prediction(
                    epsilon, fit["beta_mm"], fit["covariance_mm"], params,
                )
                decision = classify_formal_comparison(
                    predicted["s_pred_n"], pair["response_n"], predicted["sigma_pred_n"], params,
                )
                comparisons.append({
                    "direction_id": direction,
                    "response": response,
                    "epsilon_mm": epsilon,
                    "epsilon_m": epsilon / 1000.0,
                    "predicted": predicted,
                    "observed": pair,
                    "absolute_error_n": decision.get("absolute_error_n"),
                    "relative_error": decision.get("relative_error"),
                    "standardized_error": decision.get("standardized_error"),
                    "sign_same": decision.get("same_sign"),
                    "magnitude_passed": decision.get("magnitude_passed"),
                    "threshold_n": decision.get("threshold_n"),
                    "verdict": decision["verdict"],
                    "prediction_source": {
                        "model": "frozen calibration full six-point Model A",
                        "calibration_fit_verdict": fit["calibration_series_verdict"],
                        "formal_refit": False,
                    },
                })
    overall = campaign_verdict([row["verdict"] for row in comparisons])
    result = {
        "kind": "fd08_v2_formal_analysis",
        "evidence_class": "deterministic_solver_interior_interpolation_validation",
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "R6_criteria_sha256": binding["criteria_sha256"],
        "R6_result_sha256": r6_analysis_sha,
        "formal_terminal_verification_sha256": sha(args.host_verification),
        "analyzer_source_sha256": sha(Path(__file__)),
        "comparisons": comparisons,
        "comparison_count": len(comparisons),
        "verdict": overall,
        "analysis_runs": 1,
        "formal_refit": False,
        "qualification_flags": criteria["qualification_flags"],
        "interpretation": "interior interpolation validation only; not noise validation, extrapolation, direction generalization, grid independence, physical truth, exact epsilon-to-zero derivative, or joint 95% confidence",
    }
    if len(comparisons) != 24:
        raise ValueError("formal evaluation must contain exactly 24 comparisons")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(sha(args.output) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/formal_criteria.json")
    parser.add_argument("--host-verification", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/terminal_verification.json")
    parser.add_argument("--r6-analysis", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_analysis.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/formal_analysis.json")
    args = parser.parse_args()
    result = analyze(args)
    print(json.dumps({"verdict": result["verdict"], "comparison_count": result["comparison_count"],
                      "formal_refit": result["formal_refit"], "output": str(args.output)},
                     sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
