"""LOWDIM-04A Stage A inventory: re-derivation, identity table, parent gate, hard count; freeze validation negatives."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_lowdim04a as A  # noqa: E402
import build_lowdim04a_inputs as B  # noqa: E402
import lowdim04a_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402

EV = ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13"
INV = json.loads((EV / "inventory.json").read_text())


@pytest.fixture(scope="module")
def rederived():
    return B.build()


def test_inventory_and_parent_raw_are_reproduced_from_retained_inputs(rederived):
    inv, raw = rederived
    assert canonical_json(inv) == (EV / "inventory.json").read_bytes() and raw == B.PARENT_RAW.read_bytes()
    assert (EV / "inventory.json.sha256").read_text().strip() == B.sha(EV / "inventory.json")


def test_identity_table_has_four_named_hashes_and_consumers_use_the_right_order(rederived):
    inv, _ = rederived
    parent = S.read_f4(B.PARENT_RAW)
    dirs = {n: S.read_f4(ROOT / inv["directions"][n]["path"]) for n in L.BASIS}
    for row in inv["states"]:
        assert len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) == 2 and all(len(row[k]) == 64 for k in ("state_sha256", "npz_sha256"))
        phi = parent if row["kind"] == "parent" else S.perturb(parent, dirs[row["direction"]], row["step_mm"], row["sign"])
        assert S.sha256_bytes(S.to_raw(phi)) == row["phi_fortran_order_sha256"]  # the runner and device round trip pin the Fortran order
    assert inv["states"][0]["phi_fortran_order_sha256"] == B.PARENT_FORTRAN_SHA == INV["parent"]["phi_fortran_order_sha256"]


def test_nine_states_parent_first_same_plan_on_both_grids_all_at_n_max():
    assert [r["name"] for r in INV["states"]] == [r["name"] for r in L.plan()]
    assert INV["kernels"]["a"] == INV["kernels"]["b"] == [r["name"] for r in INV["states"]] and INV["states"][0]["kind"] == "parent"
    for r in INV["states"]:
        assert r["hard_count"]["residual_vs_n_max"] == 0 and r["hard_count"]["sampled_solid_centers"] == 8272
        assert r["hard_count"]["count_equal_margin_m"] > 0 or r["kind"] == "parent"
        assert r["geometry_gates"]["all_hard_gates_pass"] is True


def test_parent_reference_is_the_retained_lowdim03_run_of_the_identical_bytes():
    for k, g in INV["grids"].items():
        ref = g["baseline_reference"]
        assert "lowdim03__prop__s1.25mm" in ref["forces_csv_path"] and B.sha(ROOT / ref["forces_csv_path"]) == ref["forces_csv_sha256"]


def _freeze(**over):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    f = {"kind": A.FREEZE_KIND, "frozen_parameters": A.FROZEN_PARAMETERS, "inventory_sha256": B.sha(EV / "inventory.json"), "file_hashes": {},
         "source_commit": head, "source_tree_id": A.git_tree_sha(head), "qualification_flags": {"optimizer": False, "shape_update_allowed": False}, "selected_delta": None}
    f.update(over)
    return f


def test_registration_validation_accepts_the_frozen_inventory_and_rejects_tampering():
    A.validate_registration(_freeze(), INV)
    bad = copy.deepcopy(INV); bad["states"][1]["hard_count"]["residual_vs_n_max"] = 1
    for freeze, inv in ((_freeze(qualification_flags={"optimizer": True}), INV), (_freeze(frozen_parameters={**A.FROZEN_PARAMETERS, "epsilon_n_per_m": 0.006}), INV),
                        (_freeze(), bad), (_freeze(selected_delta=1.0), INV), (_freeze(source_tree_id="0" * 40), INV), (_freeze(file_hashes={"scripts/lowdim04a_states.py": "0" * 64}), INV)):
        with pytest.raises(ValueError):
            A.validate_registration(freeze, inv)
