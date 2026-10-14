#!/usr/bin/env python3
"""Assemble the two per-state tau-sensitivity JSONs (scripts/waterlily_grad_ta1_tau_sensitivity.jl) into the disclosed, non-gating evidence file.

Adds the reproduction gate: the quick and tau=1e-5 rows must equal the recorded DIAG5 E3 rows (run_output/<state>_E3/e3_rows.csv) to 1e-6 relative.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E5 = ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09/run_output"
OUT = ROOT / "docs/evidence/grad_ta1_2026_10_15/tau_sensitivity.json"
FIELDS = ("rel", "cos", "ratio", "gain_jvp_box_max", "gain_fd_box_max")
GATE = 1e-6


def main(paths: list[str]) -> None:
    if OUT.exists():
        sys.exit("refusing to overwrite evidence")
    states, worst = {}, 0.0
    for path in map(Path, paths):
        r = json.loads(path.read_text())
        ref = {(float(x["eps"]), x["lambda"], x["region"]): x for x in csv.DictReader((E5 / f"{r['state']}_E3/e3_rows.csv").open())}
        for row in r["rows"]:
            name = {"quick": "quick", "tie_tau=1.0e-5": "tie1e-5"}.get(row["lambda"])
            if name:
                recorded = ref[(row["eps"], name, row["region"])]
                worst = max([worst] + [abs(row[f] - float(recorded[f])) / max(abs(float(recorded[f])), 1e-30) for f in FIELDS])
        assert r["primal_bits_equal_across_lambda"] is True, "a tau changed the primal"
        states[r["state"]] = r
    out = {"kind": "grad_ta1_tau_sensitivity", "non_gating": True, "verdict_uses": "QuickTie(1f-5) regardless of this table",
           "reproduction_gate": {"max_relative_difference_vs_diag5_recorded_quick_and_tie1e-5_rows": worst, "gate": GATE, "pass": worst <= GATE},
           "states": states,
           "reading": "one-step JVP of the stored D0 corner-box states against the central finite difference of the same map; far-field, not force-level; near-body/wake and D1/D2/P1 are not compared"}
    assert out["reproduction_gate"]["pass"], out["reproduction_gate"]
    data = (json.dumps(out, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    OUT.write_bytes(data)
    OUT.with_name(OUT.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest(), worst)


if __name__ == "__main__":
    main(sys.argv[1:])
