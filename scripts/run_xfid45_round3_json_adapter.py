#!/usr/bin/env python3
"""Lossless JSON integer adapter for an immutable Round3 evaluator.

No extraction, measurement, verifier, gate, or threshold code is modified.
Only NumPy integer scalars in diagnostic records gain JSON encoding.
"""

import hashlib
import json
from pathlib import Path
import numpy as np
import audit_xfid45_surface_round3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"
original_dumps = json.dumps


def integer_scalar(value):
    if isinstance(value, np.integer):
        return int(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def lossless_dumps(*args, **kwargs):
    kwargs.setdefault("default", integer_scalar)
    return original_dumps(*args, **kwargs)


def main():
    addendum = json.loads((OUT / "execution_adapter_registration.json").read_text())
    assert (
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        == addendum["adapter_sha256"]
    )
    # Includes json.dumps used by frozen diagnostic serialization and strict ledgers.
    json.dumps = lossless_dumps
    audit_xfid45_surface_round3.main()


if __name__ == "__main__":
    main()
