"""Registered evidence must re-verify byte for byte using the current tree.

This guard intentionally avoids git archives or historical imports: a change to
BASE_PINS, runtime rendering, or TOOL_FILES must be visible here.
"""
import json
from pathlib import Path

import pytest

from cfd_harness import campaign_verify as V

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/unc01_2026_10_20/u01"
CAMPAIGN = ROOT / "docs/harness/unc01_u01_campaign.json"


@pytest.mark.parametrize("smoke", [True, False], ids=["unc01_u01_smoke", "unc01_u01_formal"])
def test_registered_unc01_u01_current_tree_reverify_is_byte_equal(smoke):
    saved = EVIDENCE / ("smoke/smoke_verify_table.json" if smoke else "state_force_table.json")
    reference = json.loads(saved.read_text())
    if smoke:
        table = V.verify(CAMPAIGN, [EVIDENCE / "smoke/unc01_u01_f24"], smoke=True,
                         source_commit=reference["source_commit"])
    else:
        directories = [EVIDENCE / "kernel_output" / f"unc01_u01_{kernel}" for kernel in ("f24", "f32", "f48")]
        table = V.verify(CAMPAIGN, directories,
                         ROOT / "docs/harness/unc01_u01_campaign.prerun_freeze.json")
    actual = (json.dumps(table, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    assert actual == saved.read_bytes()
