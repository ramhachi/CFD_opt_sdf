#!/usr/bin/env python3
"""Apply the pre-registered G1 decision rule (docs/evidence/grad03_gpu_dual_spike_2026_10_08/prerun_note.md) to a result JSON."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# CPU Float64 AD tangent, 2 steps, Poisson tol 1e-4 (docs/evidence/grad02_forward_ad_spike_2026_10_08/result_canonical.json)
CPU_FLOAT64_REFERENCE = {"combined_fx": 23053.4, "combined_fz": -4567.25}
PRIMAL_REL_LIMIT = 1e-3
CPU_AGREEMENT_LIMIT = 1e-1
FORCE_KEYS = ("combined_fx", "combined_fz", "cand_drag", "cand_downforce")


def decide(result: dict) -> dict:
    if result.get("status") not in ("COMPLETE", "FLOAT32_DONE") or "float32" not in result:  # FLOAT32_DONE: the info-only tier did not finish
        return {"verdict": "G1-FAIL", "reason": "run did not complete: " + str(result.get("error", result.get("status")))[:300]}
    f = result["float32"]
    tangents = [f[k]["ad_tangent"] for k in FORCE_KEYS]
    if not (f.get("fields_finite_incl_partials") and all(isinstance(t, (int, float)) and math.isfinite(t) for t in tangents)
            and all(t != 0 for t in tangents)):
        return {"verdict": "G1-FAIL", "reason": "tangent non-finite, zero, or fields non-finite"}
    agreement = {k: abs(f[k]["ad_tangent"] - ref) / abs(ref) for k, ref in CPU_FLOAT64_REFERENCE.items()}
    checks = {"primal_rel_diff_max_le_1e-3": f["primal_rel_diff_max"] <= PRIMAL_REL_LIMIT,
              "cpu_float64_tangent_agreement_le_1e-1": max(agreement.values()) <= CPU_AGREEMENT_LIMIT}
    verdict = "G1-PASS" if all(checks.values()) else "PARTIAL"
    return {"verdict": verdict, "checks": checks, "cpu_float64_tangent_rel_diff": agreement,
            "primal_rel_diff_max": f["primal_rel_diff_max"]}


if __name__ == "__main__":
    print(json.dumps(decide(json.loads(Path(sys.argv[1]).read_text())), indent=2, sort_keys=True))
