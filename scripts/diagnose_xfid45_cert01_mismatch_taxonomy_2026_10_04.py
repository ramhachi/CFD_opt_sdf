"""Solver-free post-hoc taxonomy of the CERT-01 attempt02 root-set mismatches.

Reads only the retained 49,152-row trace; imports no certifier. Descriptive
diagnostic: it sets no threshold, changes no gate and qualifies nothing.
"""

import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE = (
    ROOT
    / "docs/evidence/xfid45_root_certifier_2026_10_03/target/attempt02/r1_2_4_8"
    / "correspondence_roots.jsonl.gz"
)
OUT = ROOT / "docs/evidence/xfid45_cert01_mismatch_taxonomy_2026_10_04"
MATCH_M = 1e-6  # only pairs roots to find extras; not an agreement tolerance
ZERO_M = 1e-12  # |t| below this = root at the sample point itself


def classify(side):
    """Return None if primary/Sturm agree, else (exclusive class, nearest-affected)."""
    p, i = side["primary"], side["independent"]
    pt = [x["t_m"] for x in p["roots"]]
    extras = [x for x in i["roots"] if not any(abs(x["t_m"] - t) <= MATCH_M for t in pt)]
    same_status = p["status"] == i["status"]
    same_count = len(p["roots"]) == len(i["roots"])
    paired = [(a["t_m"], b["t_m"]) for a, b in zip(p["roots"], i["roots"])]
    pos_bad = same_count and any(abs(a - b) > 3.7e-13 for a, b in paired)
    if same_status and same_count and not pos_bad:
        return None
    reasons = set(p["reasons"]) | set(i["reasons"])
    if extras and all(abs(x["t_m"]) < ZERO_M for x in extras):
        cls = "A_root_at_sample_point_dropped_by_primary_endpoint_envelope"
    elif extras:
        cls = "B_nonzero_cell_endpoint_root_dropped_by_primary_endpoint_envelope"
    elif p["status"] == "COMPLETE" and i["status"] == "UNRESOLVED":
        cls = "C_sturm_splits_one_root_into_ulp_apart_pair"
    elif "root_position_exceeds_roundoff_enclosure" in reasons:
        cls = "D_primary_position_bracket_exceeds_roundoff_enclosure"
    elif pos_bad:
        cls = "E_paired_root_position_delta_only"
    else:
        cls = "F_other"
    return cls


def main():
    n = collections.Counter()
    tab = collections.Counter()
    for line in gzip.open(TRACE, "rt"):
        r = json.loads(line)
        for side_name in ("baseline", "target"):
            n["comparisons"] += 1
            cls = classify(r[side_name])
            if cls:
                n["mismatching"] += 1
                tab[(side_name, r["r"], cls)] += 1
    by_class = collections.Counter()
    by_side = collections.Counter()
    for (side, _, cls), v in tab.items():
        by_class[cls] += v
        by_side[side] += v
    rows = [
        {"side": s, "r": r, "class": c, "count": v} for (s, r, c), v in sorted(tab.items())
    ]
    res = {
        "evidence_class": "solver_free_post_hoc_trace_taxonomy_unregistered",
        "trace_sha256": hashlib.sha256(TRACE.read_bytes()).hexdigest(),
        "totals": dict(n),
        "by_class": dict(sorted(by_class.items())),
        "by_side": dict(by_side),
        "by_side_r_class": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "taxonomy.json").write_text(json.dumps(res, indent=1) + "\n")
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
