#!/usr/bin/env python3
"""Bridge measurement: full-window forward-AD point derivative vs the frozen FD-08 Model-A regression slope.

Runs once, only after PASS_G2_TERMINAL_INTEGRITY. No threshold, no verdict, no delta: it tabulates the measured
discrepancy per (direction, response) and the aggregates. FD-08 values are read from the immutable scope record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE_RECORD = ROOT / "docs/evidence/fd08_v2_oracle_scope_record_2026_10_08/record.json"
SCOPE_RECORD_SHA256 = "3f8b7d3e43f32633aa67106ba57f36e5be16f3e74e655bc54f862e463cc608d0"
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
RESPONSES = {"drag": "fx", "downforce": "fz"}  # kernel series names; downforce tangent is the negated Fz tangent
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")


def analyze(verification: dict, record: dict) -> dict:
    if not str(verification.get("status", "")).startswith("PASS_G2_TERMINAL_INTEGRITY"):
        raise ValueError("terminal verification did not pass; the bridge analyzer must not run")
    scale = verification["force_scale_n_per_solver_force"]
    index = {(r["direction_id"], r["response_id"]): r for r in record["rows"]}
    rows = []
    for direction in DIRECTIONS:
        run = verification["runs"][direction]
        for response in RESPONSES:
            ref = index[(direction, response)]
            key = "fx" if response == "drag" else "fz"
            g_dual = run[f"{key}_dual_time"]["tangent"] * scale   # the host stored downforce as the -Fz series already
            g_frozen = run[f"{key}_frozen_time"]["tangent"] * scale
            g_hat, se = ref["g_hat_n_per_m"], ref["se_g_n_per_m"]
            diff = g_dual - g_hat
            rows.append({
                "direction_id": direction, "response_id": response,
                "direction_sha256_f32_c_order": ref["direction_sha256_f32_c_order"],
                "response_semantics_sha256": ref["response_semantics_sha256"],
                "g_forward_n_per_m": g_dual, "g_forward_frozen_time_n_per_m": g_frozen,
                "g_hat_fd08_modelA_n_per_m": g_hat, "se_g_fd08_n_per_m": se,
                "sign_forward": (g_dual > 0) - (g_dual < 0), "sign_fd08": (g_hat > 0) - (g_hat < 0),
                "sign_match": (g_dual > 0) == (g_hat > 0) and g_dual != 0,
                "absolute_difference": diff, "relative_difference_to_g_hat": abs(diff) / abs(g_hat),
                "difference_over_fd08_se": abs(diff) / se, "ratio_forward_over_g_hat": g_dual / g_hat,
                "time_tangent_effect_relative": abs(g_dual - g_frozen) / abs(g_dual) if g_dual else None,
            })
    rel = [r["relative_difference_to_g_hat"] for r in rows]
    return {
        "kind": "grad_g2_full_window_forward_bridge", "rows": rows, "row_count": len(rows),
        "aggregate": {"max_relative_difference": max(rel), "median_relative_difference": statistics.median(rel),
                      "max_difference_over_se": max(r["difference_over_fd08_se"] for r in rows),
                      "sign_mismatch_count": sum(not r["sign_match"] for r in rows)},
        "fd08_scope_record_sha256": SCOPE_RECORD_SHA256, "terminal_verification_status": verification["status"],
        "source_commit": verification["source_commit"],
        "units": "N/m (derivative with respect to the phi-perturbation amplitude in metres)",
        "selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "refit": False,
        "meaning": "point derivative of the exact discrete full-window objective vs FD-08's finite-amplitude Model-A regression slope over 0.5-5 mm; "
                   "not an epsilon-to-zero continuum derivative claim, not grid independence, not physical truth, not a gradient qualification",
        "qualification_flags": {k: False for k in FLAGS},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verification", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        sys.exit("refusing to overwrite evidence")
    if hashlib.sha256(SCOPE_RECORD.read_bytes()).hexdigest() != SCOPE_RECORD_SHA256:
        sys.exit("FD-08 scope record SHA mismatch")
    sidecar = args.verification.with_name(args.verification.name + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != hashlib.sha256(args.verification.read_bytes()).hexdigest():
        sys.exit("terminal verification file does not match its SHA sidecar")
    result = analyze(json.loads(args.verification.read_text()), json.loads(SCOPE_RECORD.read_text()))
    data = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    args.output.write_bytes(data)
    args.output.with_name(args.output.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(json.dumps(result["aggregate"], indent=2))


if __name__ == "__main__":
    main()
