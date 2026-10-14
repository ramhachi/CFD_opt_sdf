"""OPT-01 v1 Stage A rendered worker: state generation and plan checks without a GPU (the pre-freeze dry run)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_opt01a_kernel as K  # noqa: E402
import step01_states as S  # noqa: E402

REAL_INV = json.loads((ROOT / "docs/evidence/opt01a_stage_a_2026_10_15/inventory.json").read_text())
INV = json.loads(json.dumps(REAL_INV))  # READY under contract v1.1: probes carry a report-only near_zero_gradient_band failure
DUMMY = "0" * 40


def worker(kernel):
    ns = {"__name__": "rendered_worker"}
    exec(compile(K.render(DUMMY, kernel), f"runner_{kernel}.py", "exec"), ns)
    return ns


@pytest.mark.parametrize("kernel", ["a", "b"])
def test_rendered_worker_accepts_the_exact_plan_and_regenerates_every_state_in_both_byte_orders(kernel):
    ns = worker(kernel)
    assert ns["KERNEL"] == kernel and ns["CASE_ID"] == INV["grids"][kernel]["case_id"] and ns["JOB"] == INV["grids"][kernel]["job"]
    ns["PINS"].update({ns["BASELINE_RAW"]: "x", ns["BASELINE_FORCE_CSV"]: "x"})  # pins are bound at render time from real files; the dry run checks the plan logic
    rows = ns["expected_plan"](INV)
    assert [r["name"] for r in rows] == ns["EXPECTED_NAMES"] and len(rows) == 9 and rows[0]["kind"] == "parent"
    parent = S.read_f4(ROOT / INV["parent"]["raw_path"])
    dirs = {n: S.read_f4(ROOT / INV["directions"][n]["path"]) for n in INV["basis_order"]}
    for row in rows:
        raw = ns["generate_phi"](S, ROOT, row, parent, dirs)  # raises if the Fortran/C hashes, changed-node count or max change differ from the inventory
        phi = np.frombuffer(raw, dtype="<f4").reshape(parent.shape, order="F")
        assert S.sha256_bytes(raw) == row["phi_fortran_order_sha256"] and np.array_equal(phi, parent) == (row["kind"] == "parent")


def test_rendered_worker_rejects_a_wrong_plan_a_swapped_parent_and_an_unpinned_input():
    ns = worker("a")
    ns["PINS"].update({ns["BASELINE_RAW"]: "x", ns["BASELINE_FORCE_CSV"]: "x"})
    bad = json.loads(json.dumps(INV)); bad["states"][3], bad["states"][4] = bad["states"][4], bad["states"][3]
    with pytest.raises(ValueError):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["states"][2]["pre_cfd_gates"].update(all_pass=False, failed=["x"])
    with pytest.raises(ValueError):
        ns["expected_plan"](bad)


@pytest.mark.parametrize("kernel", ["a", "b"])
def test_pins_bind_the_parent_raw_the_reference_csv_and_all_four_directions_to_the_real_bytes(kernel):
    pins = worker(kernel)["PINS"]
    ref = INV["grids"][kernel]["baseline_reference"]
    assert pins[INV["parent"]["raw_path"]] == INV["parent"]["phi_fortran_order_sha256"] == K.sha(ROOT / INV["parent"]["raw_path"])
    assert pins[ref["forces_csv_path"]] == ref["forces_csv_sha256"]
    assert all(pins[d["path"]] == d["sha256_fortran_raw"] for d in INV["directions"].values()) and len(INV["directions"]) == 4
    assert pins["scripts/opt01a_states.py"] and pins[INV["contract"]["path"]] == INV["contract"]["sha256"] and not any("lowdim03_states" in k or "proposal" in k for k in pins)


def test_rendered_worker_gate_scope_probe_near_zero_is_report_only_everything_else_blocks():
    ns = worker("a")
    ns["PINS"].update({ns["BASELINE_RAW"]: "x", ns["BASELINE_FORCE_CSV"]: "x"})
    assert REAL_INV["stage_status"] == "READY" and any(r["pre_cfd_gates"]["table"]["near_zero_gradient_band"] == "fail" for r in INV["states"] if r["kind"] == "perturbation")
    ns["expected_plan"](INV)  # the registered inventory is accepted although six probes fail the report-only gate
    bad = json.loads(json.dumps(INV)); bad["states"][2]["pre_cfd_gates"]["table"]["p22_v2"] = "fail"  # a probe failing another gate still blocks
    with pytest.raises(ValueError, match="pre-CFD gate"):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["states"][0]["pre_cfd_gates"]["table"]["near_zero_gradient_band"] = "fail"  # the proposal (parent) keeps the crossing-slope rule hard
    with pytest.raises(ValueError, match="pre-CFD gate"):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["stage_status"], bad["blockers"] = "BLOCKED_PRE_CFD", [{"state": "x", "failed": ["y"]}]
    with pytest.raises(ValueError, match="blocked before CFD"):
        ns["expected_plan"](bad)
    bad = json.loads(json.dumps(INV)); bad["contract"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contract"):
        ns["expected_plan"](bad)
