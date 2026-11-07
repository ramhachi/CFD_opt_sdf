"""FORCE-00's single parent-derived measuring box per grid."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("force00_boxes", ROOT / "scripts/force00_boxes.py")
boxes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(boxes)


def support():
    return {"schema": "force00_box_support_v1", "phase_shift_m": [0.0] * 3,
            "field_type": "Float32", "waterlily_version": "1.8.0",
            "ground_plane_solver": 0.0, "source_sha256": {},
            "grids": {name: {"flow_dims": dims,
                "mu0_support_lower": [20, 15, 12],
                "mu0_support_upper": [40, 30, 25], "mu0_support_count": 100}
                for name, dims in (("flow_24", [150, 72, 54]), ("flow_32", [200, 96, 72]))}}


def parent():
    return {"state": {"state_sha256": "a" * 64, "phi_fortran_order_sha256": "b" * 64}}


def test_largest_box_and_exact_margin():
    record = boxes.boxes_from_support(support(), parent())
    assert record["parent_state_sha256"] == "a" * 64
    assert record["parent_phi_fortran_sha256"] == "b" * 64
    for grid, value in record["grids"].items():
        assert value["lower"] == [4, 4, 6]
        assert value["upper"] == [n - 1 for n in support()["grids"][grid]["flow_dims"]]
        assert value["body_clearance_cells"] == 5
        assert value["domain_inset_cells"] == 2
    data = support()
    data["grids"]["flow_24"]["mu0_support_lower"][2] = 11
    assert boxes.boxes_from_support(data, parent())["grids"]["flow_24"]["lower"][2] == 6
    data["grids"]["flow_24"]["mu0_support_lower"][2] = 10
    with pytest.raises(ValueError, match="five-cell"):
        boxes.boxes_from_support(data, parent())


@pytest.mark.parametrize("defect", ["grid", "phase", "type", "nonfinite", "empty", "backend", "version"])
def test_bad_support_rejected(defect):
    data = support()
    if defect == "grid": del data["grids"]["flow_24"]
    if defect == "phase": data["phase_shift_m"][0] = 0.1
    if defect == "type": data["grids"]["flow_24"]["flow_dims"][0] = True
    if defect == "nonfinite": data["ground_plane_solver"] = float("nan")
    if defect == "empty": data["grids"]["flow_24"]["mu0_support_count"] = 0
    if defect == "backend": data["field_type"] = "Float64"
    if defect == "version": data["waterlily_version"] = "1.10.0"
    with pytest.raises(ValueError):
        boxes.boxes_from_support(data, parent())


def test_write_once_refuses_before_measurement(tmp_path):
    target = tmp_path / "boxes.json"
    target.write_bytes(b"already registered\n")
    with pytest.raises(FileExistsError):
        boxes.register(target, measure=lambda: pytest.fail("measurement must not run"))
    assert target.read_bytes() == b"already registered\n"


def test_registered_boxes_match_parent_and_support():
    value = json.loads((ROOT / "docs/harness/force00_boxes.json").read_text())
    genesis = json.loads((ROOT / "docs/evidence/v18_genesis_2026_10_19/genesis.json").read_text())
    assert value["schema"] == "force00_boxes_v1"
    assert value["parent_state_sha256"] == genesis["state"]["state_sha256"]
    assert value["parent_phi_fortran_sha256"] == genesis["state"]["phi_fortran_order_sha256"]
    for item in value["grids"].values():
        for lo, hi, n, support_lo, support_hi in zip(item["lower"], item["upper"],
                item["flow_dims"], item["mu0_support_lower"], item["mu0_support_upper"]):
            assert lo >= 4 and hi <= n - 1
            assert support_lo - lo >= 5 and hi + 1 - support_hi >= 5
