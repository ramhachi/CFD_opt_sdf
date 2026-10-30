#!/usr/bin/env python3
"""Verify a complete 25-state formal terminal before prediction comparison."""

from __future__ import annotations

import argparse
from pathlib import Path

import verify_fd08_v2_r6

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/formal_criteria.json")
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "work/kaggle_fd08_v2_formal_dataset")
    parser.add_argument("--kernel-version", type=int, required=True)
    parser.add_argument("--evidence", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/terminal_verification.json")
    args = parser.parse_args()
    result = verify_fd08_v2_r6.verify(args)
    if result["kind"] != "fd08_v2_formal_host_terminal_verification" or result["state_count"] != 25:
        raise ValueError("formal verification did not return exact 25/25 terminal integrity")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
