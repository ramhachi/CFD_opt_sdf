#!/usr/bin/env python3
"""UNC-01 (#61) per-kernel verification (registration §2, §8; freeze 1 amendment 1).

`harness.py verify` accepts a formal verification only for ALL kernels of a campaign at once, so one failing kernel voids every table, and the U2 campaign,
which declares both flow_24 alternatives (f24, f24r) of which exactly one is pushed, could never verify.  This wrapper runs the harness's own checks
(`campaign_verify.validate_freeze` and `campaign_verify.check_kernel`, unchanged) on ONE kernel directory and writes a state-force table of that kernel
in the harness table format, marked `per_kernel: true`.  It adds no check and removes none except "exactly the campaign's kernel directories".

    python scripts/unc01_verify.py KERNEL_DIR --campaign C --freeze F --out TABLE.json     # exit 3 and no file on any failure
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_schema as SC  # noqa: E402
from cfd_harness import campaign_verify as V  # noqa: E402


def verify_one(campaign_path, kernel_dir, freeze_path):
    c, campaign_sha, rel = V.load_campaign(campaign_path)
    SC.req(not c["legacy_replay"], "per-kernel verification is for harness campaigns only")
    freeze = SC.jload(freeze_path)
    V.validate_freeze(freeze, freeze_path, c, campaign_sha, rel)
    k, states = V.check_kernel(kernel_dir, c, campaign_sha, rel, freeze)
    return {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_id": c["campaign_id"], "campaign_sha256": campaign_sha, "smoke": False,
            "legacy_replay": False, "source_commit": freeze["source_commit"], "freeze_sha256": SC.sha256_path(freeze_path), "harness_tool_sha256": SC.tool_hashes(),
            "per_kernel": True, "verifier": {"script": "scripts/unc01_verify.py", "sha256": SC.sha256_path(__file__)},
            "integrity": {"pass": True, "failures": []}, "kernel_manifest_sha256": {k: SC.sha256_path(Path(kernel_dir) / SC.MANIFEST_NAME)}, "state_forces_n": {k: states}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kernel_dir", type=Path)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--freeze", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    try:
        SC.req(not a.out.exists(), f"refusing to overwrite {a.out}")
        table = verify_one(a.campaign, a.kernel_dir, a.freeze)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        print(f"verify FAILED (fail closed): {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(3)
    a.out.write_text(json.dumps(table, sort_keys=True, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
