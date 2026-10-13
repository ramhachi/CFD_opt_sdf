"""LOWDIM-04 Stage B rendered worker: state generation and plan checks without a GPU (the pre-freeze dry run)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_lowdim04b_kernel as K  # noqa: E402
import step01_states as S  # noqa: E402

INV = json.loads((ROOT / "docs/evidence/lowdim04b_stage_b_2026_10_13/inventory.json").read_text())
DUMMY = "0" * 40


def worker(kernel):
    ns = {"__name__": "rendered_worker"}
    exec(compile(K.render(DUMMY, kernel), f"runner_{kernel}.py", "exec"), ns)
    return ns


@pytest.mark.parametrize("kernel", ["a", "b"])
def test_rendered_worker_accepts_the_exact_plan_and_regenerates_every_state_in_both_byte_orders(kernel):
    ns = worker(kernel)
    assert ns["KERNEL"] == kernel and ns["CASE_ID"] == INV["grids"][kernel]["case_id"] and ns["JOB"] == INV["grids"][kernel]["job"] and ns["SOLVER_WALL_TIME_CAP_S"] == 6300
    rows = ns["expected_plan"](INV)
    assert [r["name"] for r in rows] == ns["EXPECTED_NAMES"] and len(rows) == 7 and rows[0]["kind"] == "parent"
    parent = S.read_f4(ROOT / INV["parent"]["raw_path"])
    dirs = {"robust_stage_a": S.read_f4(ROOT / INV["proposal"]["file"])}
    for row in rows:
        raw = ns["generate_phi"](S, ROOT, row, parent, dirs)  # raises if the Fortran/C hashes, changed-node count or max change differ from the inventory
        phi = np.frombuffer(raw, dtype="<f4").reshape(parent.shape, order="F")
        assert S.sha256_bytes(raw) == row["phi_fortran_order_sha256"] and np.array_equal(phi, parent) == (row["kind"] == "parent")


def test_rendered_worker_rejects_a_wrong_plan_and_a_failed_gate():
    ns = worker("a")
    bad = json.loads(json.dumps(INV)); bad["states"][3], bad["states"][4] = bad["states"][4], bad["states"][3]
    with pytest.raises(ValueError):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["states"][2]["geometry_gates"]["all_hard_gates_pass"] = False
    with pytest.raises(ValueError):
        ns["expected_plan"](bad)


@pytest.mark.parametrize("kernel", ["a", "b"])
def test_pins_bind_the_parent_raw_the_reference_csv_and_the_proposal_to_the_real_bytes(kernel):
    pins = worker(kernel)["PINS"]
    ref = INV["grids"][kernel]["baseline_reference"]
    assert pins[INV["parent"]["raw_path"]] == INV["parent"]["phi_fortran_order_sha256"] == K.sha(ROOT / INV["parent"]["raw_path"])
    assert pins[ref["forces_csv_path"]] == ref["forces_csv_sha256"] and pins[INV["proposal"]["file"]] == INV["proposal"]["sha256_fortran_raw"]
    assert pins["scripts/lowdim04b_states.py"] and not any("lowdim04a" in k or "lowdim03_states" in k for k in pins)
