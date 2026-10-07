#!/usr/bin/env python3
"""Solver-free trust radius of the frozen FD-08 v2 R6 micro-response models.

Reads saved R6 fits only; does not refit, re-register or change any verdict.
epsilon is the max-nominal phi-direction coefficient in mm, not a physical displacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.fd08_v2_gate import evaluate_series, load_params  # noqa: E402

R6_ANALYSIS = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_analysis.json"
R6_ANALYSIS_SHA256 = "b5d55b77f750f447fd486a600f9e52a66a3f6c2610c5dba5ce6792018cc647be"
FORMAL_ANALYSIS = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_analysis.json"
FORMAL_ANALYSIS_SHA256 = "3da59ac9b1086ed286cb0109cd669dac804f4fb99785986515ce35db1acf0466"
OUTPUT = ROOT / "docs/evidence/fd08_v2_trust_radius_2026_10_08/result.json"
RATIOS = (0.05, 0.10, 0.20)
H_SDF_MM = 25.0
H_FLOW_MM = 100.0 / 3.0
STEP01_RANGE_MM = (2.5, 12.5)  # 0.1-0.5 h_SDF, issue #47
SEED = 20261008
DRAWS = 20000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def radius_a(g, c, ratio):
    """eps where |c| eps^2 = ratio |g| (cubic/linear ratio); inf when c == 0."""
    g, c = np.abs(g), np.abs(c)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(c > 0, np.sqrt(ratio * g / np.where(c > 0, c, 1.0)), np.inf)


def radius_b(g, k, ratio):
    """eps where |k| eps = ratio |g| (quadratic/linear ratio); inf when k == 0."""
    g, k = np.abs(g), np.abs(k)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(k > 0, ratio * g / np.where(k > 0, k, 1.0), np.inf)


def _pct(values, q):
    finite = np.isfinite(values)
    if not finite.any():
        return None
    # inf counts as arbitrarily large; the percentile of the full sample is what is reported
    v = np.sort(values)
    x = v[min(len(v) - 1, int(np.floor(q / 100 * len(v))))]
    return float(x) if np.isfinite(x) else None  # None = unbounded at this percentile


def _model_block(beta, cov, rng, radius_fn):
    mean = np.asarray(beta, dtype=float)
    draws = rng.multivariate_normal(mean, np.asarray(cov, dtype=float), size=DRAWS)
    out = {"beta": mean.tolist(), "se_second_coefficient": float(np.sqrt(cov[1][1])),
           "z_second_coefficient": float(abs(mean[1]) / np.sqrt(cov[1][1])), "ratios": {}}
    for ratio in RATIOS:
        point = float(radius_fn(mean[0], mean[1], ratio))
        samples = radius_fn(draws[:, 0], draws[:, 1], ratio)
        out["ratios"][f"{ratio:.2f}"] = {
            "point_mm": None if not np.isfinite(point) else point,
            "p05_mm": _pct(samples, 5), "p50_mm": _pct(samples, 50), "p95_mm": _pct(samples, 95),
            "p05_in_h_sdf": None if _pct(samples, 5) is None else _pct(samples, 5) / H_SDF_MM,
            "p05_in_h_flow": None if _pct(samples, 5) is None else _pct(samples, 5) / H_FLOW_MM,
            "fraction_unbounded": float(np.mean(~np.isfinite(samples))),
        }
    return out


def analyze() -> dict:
    assert sha256(R6_ANALYSIS) == R6_ANALYSIS_SHA256, "R6 analysis SHA mismatch"
    assert sha256(FORMAL_ANALYSIS) == FORMAL_ANALYSIS_SHA256, "formal analysis SHA mismatch"
    r6 = json.loads(R6_ANALYSIS.read_text())
    formal = json.loads(FORMAL_ANALYSIS.read_text())
    params = load_params()
    rng = np.random.Generator(np.random.PCG64(SEED))
    rows, models = [], {}
    for series in r6["series"]:
        key = f"{series['direction_id']}|{series['response']}"
        refit = evaluate_series(series["epsilon_mm"], series["response_s_n"], params)
        match = (np.allclose(refit["model_a"]["beta"], series["model_a"]["beta"], rtol=1e-9, atol=0)
                 and np.allclose(refit["model_b"]["beta"], series["model_b"]["beta"], rtol=1e-9, atol=0))
        a = _model_block(series["model_a"]["beta"], series["model_a"]["covariance"], rng, radius_a)
        b = _model_block(series["model_b"]["beta"], series["model_b"]["covariance"], rng, radius_b)
        models[key] = {"A": series["model_a"], "B": series["model_b"]}
        rows.append({"series": key, "stored_fit_reproduced_by_evaluate_series": bool(match),
                     "epsilon_ladder_mm": series["epsilon_mm"], "model_A_cubic": a, "model_B_quadratic": b})
    # counterfactual: frozen R6 Model B prediction of the 24 formal observations (Model A is the registered one)
    comparisons = []
    for c in formal["comparisons"]:
        key = f"{c['direction_id']}|{c['response']}"
        beta = np.asarray(models[key]["B"]["beta"], dtype=float)
        eps = c["epsilon_mm"]
        pred_b = float(beta[0] * eps + beta[1] * eps * abs(eps))
        obs = c["observed"]["response_n"]
        comparisons.append({"series": key, "epsilon_mm": eps, "abs_error_model_A_n": c["absolute_error_n"],
                            "abs_error_model_B_n": abs(obs - pred_b)})
    closer_a = sum(x["abs_error_model_A_n"] < x["abs_error_model_B_n"] for x in comparisons)
    top = max(max(s["epsilon_mm"]) for s in r6["series"])
    return {
        "kind": "fd08_v2_trust_radius_solver_free",
        "evidence_class": "solver_free_post_hoc_extrapolation_of_frozen_micro_response_models_unregistered",
        "inputs": {"r6_analysis_sha256": R6_ANALYSIS_SHA256, "formal_analysis_sha256": FORMAL_ANALYSIS_SHA256},
        "method": {"model_A": "S = g eps + c eps^3 ; radius where |c| eps^2 = ratio |g|",
                   "model_B": "S = g eps + k eps|eps| ; radius where |k| eps = ratio |g|",
                   "uncertainty": f"{DRAWS} parametric draws from N(beta, nominal covariance), PCG64 seed {SEED}; "
                                  "covariance is the nominal T2 noise-model covariance (not measured noise)",
                   "ratios": list(RATIOS), "units": "epsilon mm = max-nominal phi-direction coefficient, not physical displacement",
                   "h_sdf_mm": H_SDF_MM, "h_flow_mm": H_FLOW_MM, "step01_range_mm": list(STEP01_RANGE_MM),
                   "calibrated_range_mm": [min(s["epsilon_mm"][0] for s in r6["series"]), top]},
        "series": rows,
        "formal_model_A_vs_B": {"closer_A": int(closer_a), "closer_B": len(comparisons) - int(closer_a),
                                "note": "B uses frozen R6 Model B fits as a counterfactual; the registered model is A",
                                "comparisons": comparisons},
        "claim_limit": "radii beyond the calibrated range are extrapolations of two assumed functional forms; they are not a validity "
                       "guarantee, a step-size recommendation, or a physical displacement. No flag or verdict changes.",
        "qualification_flags": {k: False for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=OUTPUT)
    args = p.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    data = (json.dumps(analyze(), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    args.output.with_name(args.output.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
