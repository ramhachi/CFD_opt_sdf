"""GRAD-00 epsilon/spread reference from the registered FD-08 v2 formal evidence (amend3).

Per direction: epsilon_m = the largest of the three FD-08 formal interior epsilons (formal_analysis.json comparisons, 24/24 PASS;
3.9716 mm, the same for the four directions), spread_n_per_m = the FD-08 Model A calibration standard error of the gradient
`se_g_n_per_m` (formal_criteria.json calibration_binding.fits): fx from the drag fit, fz from the downforce fit.
Definition fixed before any GRAD-00 run (docs/grad00_lambda_swap_spec_2026_11_01.md, Amendment 1). Writes once; `--check` recomputes and compares.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = "docs/evidence/fd08_v2_formal_2026_10_07_amend3"
SOURCES = (f"{EVIDENCE}/formal_analysis.json", f"{EVIDENCE}/formal_criteria.json")
OUT = ROOT / "docs/evidence/grad00_lambda_2026_11/reference.json"
DEFINITION = ("epsilon_m = the largest of the three FD-08 v2 formal interior epsilons of the direction (formal_analysis.json comparisons, all PASS); "
              "spread_n_per_m = the FD-08 Model A calibration standard error of the gradient se_g_n_per_m (formal_criteria.json calibration_binding.fits), "
              "fx from the drag fit, fz from the downforce fit. Fixed before any GRAD-00 run (GRAD-00 spec amendment 1, 2026-11-06).")


def build():
    analysis, criteria = (json.loads((ROOT / p).read_text()) for p in SOURCES)
    fits = criteria["calibration_binding"]["fits"]
    directions = {}
    for row in analysis["comparisons"]:
        d = directions.setdefault(row["direction_id"], {"epsilon_m": 0.0})
        d["epsilon_m"] = max(d["epsilon_m"], row["epsilon_m"])
    for name, d in directions.items():
        d["spread_n_per_m"] = {"fx": fits[f"{name}|drag"]["se_g_n_per_m"], "fz": fits[f"{name}|downforce"]["se_g_n_per_m"]}
    sources = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    return {"schema_version": 1, "kind": "grad00_fd08_reference", "definition": DEFINITION, "sources": sources, "directions": dict(sorted(directions.items()))}


def main(argv):
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    if argv == ["--check"]:
        sys.exit(0 if OUT.read_text() == text else f"{OUT} differs from the recomputed reference")
    if argv or OUT.exists():
        sys.exit(f"usage: {Path(__file__).name} [--check]; refusing to overwrite {OUT}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1:])
