"""GRIDRES-01 rendered worker: state generation and plan checks without a GPU (the pre-freeze dry run), both grids."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_gridres01_kernel as K  # noqa: E402
import gridres01_states as G  # noqa: E402
import step01_states as S  # noqa: E402

INV = json.loads((ROOT / "docs/evidence/gridres01_2026_10_20/inventory.json").read_text())
DUMMY = "0" * 40


def worker(case):
    ns = {"__name__": "rendered_worker"}
    exec(compile(K.render(DUMMY, case), f"runner_{case}.py", "exec"), ns)
    return ns


@pytest.mark.parametrize("case", ["flow_40", "flow_48"])
def test_rendered_worker_accepts_the_exact_plan_and_regenerates_every_state_in_both_byte_orders(case):
    ns = worker(case)
    spec = G.GRIDS[case]
    assert (ns["CASE_ID"], ns["CELLS"], ns["JOB"]) == (case, spec["cells"], INV["grids"][case]["job"])
    assert (ns["PER_STATE_TIMEOUT_S"], ns["SOLVER_WALL_TIME_CAP_S"], ns["KERNEL_TIMEOUT_S"]) == (spec["per_state_timeout_s"], spec["solver_wall_time_cap_s"], spec["kernel_timeout_s"])
    assert ns["SOLVER_WALL_TIME_CAP_S"] == 5 * ns["PER_STATE_TIMEOUT_S"] and ns["EXPECTED_NAMES"] == list(G.NAMES)
    rows = ns["expected_plan"](INV)
    assert [r["name"] for r in rows] == ns["EXPECTED_NAMES"] and len(rows) == 5 and rows[0]["kind"] == "parent"
    parent = S.read_f4(ROOT / INV["parent"]["raw_path"])
    dirs = {"robust_opt01a": S.read_f4(ROOT / INV["proposal"]["file"])}
    for row in rows:
        raw = ns["generate_phi"](S, ROOT, row, parent, dirs)  # raises if the Fortran/C hashes, changed-node count or max change differ from the inventory
        phi = np.frombuffer(raw, dtype="<f4").reshape(parent.shape, order="F")
        assert S.sha256_bytes(raw) == row["phi_fortran_order_sha256"] and np.array_equal(phi, parent) == (row["kind"] == "parent")


def test_rendered_worker_rejects_a_wrong_plan_wrong_caps_a_blocked_inventory_or_the_other_grid():
    ns = worker("flow_40")
    bad = json.loads(json.dumps(INV)); bad["states"][3], bad["states"][4] = bad["states"][4], bad["states"][3]
    with pytest.raises(ValueError):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["grids"]["flow_40"]["limits"]["per_state_timeout_s"] = 3600
    with pytest.raises(ValueError, match="caps"):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["stage_status"], bad["blockers"] = "BLOCKED", [{"state": "x"}]
    with pytest.raises(ValueError, match="blocked"):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["parent"]["raw_path"] = "elsewhere.raw"
    with pytest.raises(ValueError):
        ns["expected_plan"](bad)
    other = worker("flow_48")
    assert other["expected_plan"](INV) and other["CASE_ID"] != ns["CASE_ID"]


@pytest.mark.parametrize("case", ["flow_40", "flow_48"])
def test_pins_bind_the_parent_raw_the_direction_the_job_and_the_inventory_to_the_real_bytes(case):
    pins = worker(case)["PINS"]
    assert pins[INV["parent"]["raw_path"]] == INV["parent"]["phi_fortran_order_sha256"] == K.sha(ROOT / INV["parent"]["raw_path"])
    assert pins[INV["proposal"]["file"]] == INV["proposal"]["sha256_fortran_raw"] and pins["scripts/waterlily_gridres01_job.jl"] == K.sha(ROOT / "scripts/waterlily_gridres01_job.jl")
    assert pins["docs/evidence/gridres01_2026_10_20/inventory.json"] == K.sha(ROOT / "docs/evidence/gridres01_2026_10_20/inventory.json") and "scripts/gridres01_states.py" in pins
    assert K.KERNEL_IDS[case].startswith("ramhachi888/cfd-opt-sdf-gridres01-") and K.metadata(case)["id"] == K.KERNEL_IDS[case] and K.metadata(case)["machine_shape"] == "NvidiaTeslaT4"
