"""GRIDRES-01 inventory: byte-identical to the frozen OPT-01 Stage B states, the grid table, and the plan."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_gridres01_inputs as B  # noqa: E402
import gridres01_states as G  # noqa: E402

INV = json.loads((ROOT / B.EVIDENCE / "inventory.json").read_text())
OLD = json.loads((ROOT / G.OPT01B_REL / "inventory.json").read_text())


def test_inventory_is_the_committed_derivation_and_its_sidecar_matches():
    from build_grid01_inputs import canonical_json
    data = (ROOT / B.EVIDENCE / "inventory.json").read_bytes()
    assert data == canonical_json(B.build()) and (ROOT / B.EVIDENCE / "inventory.json.sha256").read_text().strip() == hashlib.sha256(data).hexdigest()


def test_the_five_states_are_byte_identical_to_the_stage_b_states():
    old = {r["name"]: r for r in OLD["states"]}
    assert [r["name"] for r in INV["states"]] == list(G.NAMES) and len(INV["states"]) == 5
    for row in INV["states"]:
        assert all(row[k] == old[row["name"]][k] for k in B.ROW_KEYS)   # every phi hash, the state identity and the change metrics
    assert [{k: r[k] for k in ("name", "kind", "direction", "step_mm", "sign")} for r in INV["states"]] == G.plan()
    assert INV["parent"]["phi_fortran_order_sha256"] == OLD["parent"]["phi_fortran_order_sha256"] and INV["proposal"]["sha256_fortran_raw"] == OLD["proposal"]["sha256_fortran_raw"]


def test_grid_table_flow_40_and_flow_48():
    for case, cells, dims, per_state, cap, kernel in (("flow_40", 40, [250, 120, 90], 1800, 10800, 21600), ("flow_48", 48, [300, 144, 108], 3600, 18000, 43000)):
        g = INV["grids"][case]
        c = g["measurement"]["case"]
        assert (g["cells"], c["flow_dims"], c["solver_length"], c["solver_viscosity"], c["flow_spacing_m"]) == (cells, dims, float(cells), cells / 80, 0.8 / cells)
        assert g["limits"] == {"per_state_timeout_s": per_state, "solver_wall_time_cap_s": cap, "kernel_timeout_s": kernel} and g["job"] == "scripts/waterlily_gridres01_job.jl"
        spans = (5.0, 2.4, 1.8)   # the W4 base box
        assert all(abs(d * 0.8 / cells - s) < 1e-12 for d, s in zip(dims, spans))
    assert INV["grids"]["flow_40"]["measurement"]["time_window_t_u_l"] == [80.0, 120.0] == INV["grids"]["flow_48"]["measurement"]["time_window_t_u_l"]
    assert INV["stage_status"] == "READY" and INV["kernels"] == {"flow_40": list(G.NAMES), "flow_48": list(G.NAMES)}


def test_flow_40_reruns_the_retained_parents_with_their_stage_b_csv_hashes_and_flow_48_does_not():
    """Amendment 2 H2: order flow_24, flow_32; each carries the Stage B parent CSV hash (also the file's own hash); the aggregate cap is 10800 s."""
    reruns = INV["grids"]["flow_40"]["parent_reruns"]
    assert [r["case_id"] for r in reruns] == ["flow_24", "flow_32"] and INV["grids"]["flow_48"]["parent_reruns"] == []
    assert INV["grids"]["flow_40"]["limits"]["solver_wall_time_cap_s"] == 10800
    for r in reruns:
        assert hashlib.sha256((ROOT / r["retained_forces_csv"]).read_bytes()).hexdigest() == r["retained_forces_csv_sha256"]
        assert (r["cells"], r["flow_dims"]) == (G.RERUN_CELLS[r["case_id"]], list(G.RERUN_DIMS[r["case_id"]]))
