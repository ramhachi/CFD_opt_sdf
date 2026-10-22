#!/usr/bin/env python3
"""FID-01 (#62) wrapper around the unchanged harness v1.1 freeze and per-kernel verify (registration §10, freeze 1 amendment 2).

On 2026-10-21 the owner's authenticated Kaggle kernel listing contained a row with an empty ref and the title "[Private Notebook]" (an
unaddressable never-run draft; `kaggle kernels status` cannot reach it).  The harness identity-free check requires every listed ref to start with
the owner, so `harness.py freeze` fails closed on that row for every campaign.  This wrapper exempts exactly such rows (ref == "" and title ==
"[Private Notebook]") from the listing parser, for both the freeze-time check and its re-validation at verify time, and changes nothing else:
the harness files are not edited, the recorded stdout keeps the row, and a named slug can never be exempted (it has a ref).

    python scripts/fid01/fid01_harness.py freeze CAMPAIGN --source-commit X --smoke-table T
    python scripts/fid01/fid01_harness.py verify KERNEL_DIR --campaign C --freeze F --out TABLE.json    # as scripts/unc01_verify.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_build as B  # noqa: E402
from cfd_harness import campaign_schema as SC  # noqa: E402

PLACEHOLDER_TITLE = "[Private Notebook]"
_parse = SC.parse_listing


def parse_listing(stdout):
    return [r for r in _parse(stdout) if not (r.get("ref", "") == "" and r.get("title") == PLACEHOLDER_TITLE)]


SC.parse_listing = parse_listing   # module global: used by campaign_build.identity_free_check and campaign_schema.validate_identity_free


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze", "verify"])
    ap.add_argument("path", type=Path)
    ap.add_argument("--source-commit")
    ap.add_argument("--smoke-table", type=Path)
    ap.add_argument("--campaign", type=Path)
    ap.add_argument("--freeze", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        if a.cmd == "freeze":
            print("freeze", B.freeze(a.path, a.source_commit, smoke_table=a.smoke_table))
        else:
            import unc01_verify as UV
            SC.req(a.out is not None and not a.out.exists(), "--out must be a new file")
            table = UV.verify_one(a.campaign, a.path, a.freeze)
            table["verifier"] = {"script": "scripts/fid01/fid01_harness.py verify (scripts/unc01_verify.verify_one with the placeholder-tolerant listing parser)",
                                 "sha256": SC.sha256_path(__file__)}
            a.out.write_text(json.dumps(table, sort_keys=True, indent=2, allow_nan=False) + "\n")
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        print(f"{a.cmd} FAILED (fail closed): {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
