"""GRIDRES-01 flow_40 prerun freeze: the committed freeze validates against the committed bytes, and tampering is refused."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_gridres01 as A  # noqa: E402

E = ROOT / A.EVIDENCE_REL
FREEZE = json.loads((E / "prerun_freeze_flow_40.json").read_text())
INV = json.loads((E / "inventory.json").read_text())


def test_the_committed_freeze_validates_and_binds_the_caps_the_kernel_and_the_ancestry():
    A.validate_registration(FREEZE, INV, "flow_40")
    r = FREEZE["runtime"]
    assert (r["per_state_timeout_s"], r["solver_wall_time_cap_s"], r["kernel_timeout_s"], r["kernel_id"]) == (1800, 10800, 21600, "ramhachi888/cfd-opt-sdf-gridres01-f40")
    assert FREEZE["case_id"] == "flow_40" and not any(FREEZE["qualification_flags"].values()) and FREEZE["parent_integration_commit"] == A.PARENT_INTEGRATION_COMMIT
    assert (E / "prerun_freeze_flow_40.json.sha256").read_text().strip() == A.sha256(E / "prerun_freeze_flow_40.json")
    assert "scripts/waterlily_gridres01_job.jl" in FREEZE["pins"] and not any("flow_48" in k for k in FREEZE["file_hashes"])   # nothing about flow_48 is frozen


def test_tampered_freezes_are_refused():
    for mutate in (lambda f: f["runtime"].update(per_state_timeout_s=3600), lambda f: f["file_hashes"].update({"scripts/gridres01_states.py": "0" * 64}),
                   lambda f: f.update(case_id="flow_48"), lambda f: f["pins"].update({"scripts/gridres01_states.py": "0" * 64}), lambda f: f["qualification_flags"].update(optimizer=True),
                   lambda f: f.update(inventory_sha256="0" * 64)):
        bad = copy.deepcopy(FREEZE)
        mutate(bad)
        with pytest.raises(ValueError):
            A.validate_registration(bad, INV, "flow_40")
