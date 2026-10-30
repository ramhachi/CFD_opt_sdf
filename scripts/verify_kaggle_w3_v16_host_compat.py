#!/usr/bin/env python3
"""Run the immutable W3 verifier with its missing self-path global supplied."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/verify_kaggle_w3_v16.py"


def main() -> int:
    namespace = runpy.run_path(str(VERIFIER))
    namespace["main"].__globals__["HOST_VERIFIER"] = VERIFIER
    return int(namespace["main"]())


if __name__ == "__main__":
    raise SystemExit(main())
