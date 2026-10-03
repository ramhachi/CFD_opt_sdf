#!/usr/bin/env python3
"""Schedule the frozen independent verifier on four disjoint r partitions.

This adds no scientific gate or numerical code; each saved case is evaluated by
verify_xfid45_surface_round3.main and verify_xfid45_round3 unchanged.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("r", type=int, choices=[1, 2, 4, 8])
    args = parser.parse_args()
    r = args.r
    ref = json.loads((OUT / "result.json").read_text())
    cases = [c for c in ref["cases"] if c["r"] == r]
    pairs = [c for c in ref["fidelity_pairs"] if c["r"] == r]
    assert len(cases) == 10 and len(pairs) == 6, "partition not complete"
    folder = ROOT / "work/xfid45_round3_independent_partitions" / f"r{r}"
    folder.mkdir(parents=True, exist_ok=True)
    reg = json.loads((OUT / "preregistration.json").read_text())
    assert all(
        hashlib.sha256((ROOT / s["path"]).read_bytes()).hexdigest() == s["sha256"]
        for s in reg["sources"].values()
    )
    (folder / "preregistration.json").write_bytes(
        (OUT / "preregistration.json").read_bytes()
    )
    if not (folder / "surfaces").exists():
        (folder / "surfaces").symlink_to(OUT / "surfaces", target_is_directory=True)
    snapshot = dict(
        ref,
        cases=cases,
        fidelity_pairs=pairs,
        candidate_pass_before_independent_verification={
            str(k): k == r
            and all(c["surface_gates_pass"] for c in cases)
            and all(p["status"] == "PASS" for p in pairs)
            for k in (1, 2, 4, 8)
        },
    )
    (folder / "result.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    )
    code = 'from pathlib import Path; import verify_xfid45_surface_round3 as v; v.OUT=Path(__import__("sys").argv[1]); v.main()'
    subprocess.run([sys.executable, "-c", code, str(folder)], cwd=ROOT, check=True)
    output = OUT / "independent_partitions" / f"r{r}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "input_result_subset.json").write_bytes(
        (folder / "result.json").read_bytes()
    )
    (output / "independent_result.json").write_bytes(
        (folder / "independent_result.json").read_bytes()
    )


if __name__ == "__main__":
    main()
