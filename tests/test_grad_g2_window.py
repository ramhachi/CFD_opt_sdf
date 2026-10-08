"""G2 host window reconstruction: registered semantics, tangent correctness and replay of an archived FD-08 history."""
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts import fd08_v2_campaign_io as io_ref
from scripts import grad_g2_window as W
from tests.grad_g2_synthetic import make_rows

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_kernel_output.tar.gz"
BASELINE_CSV = "fd08_v2_formal_2026_10_07_amend3__states__baseline_v17__flow_24.forces.csv"


def test_dual_arithmetic_matches_calculus():
    x, y = W.Dual(3.0, 1.0), W.Dual(2.0, 0.5)
    assert (x * y).d == 3.0 * 0.5 + 2.0 * 1.0
    assert (x / y).d == pytest.approx((1.0 * 2.0 - 3.0 * 0.5) / 4.0)


@pytest.mark.parametrize("series", ["fx", "-fz", "pfx"])
def test_window_tangent_equals_finite_difference_of_the_value(series):
    h = 1e-7
    value, tangent = W.window_mean(make_rows(0.0), series, 80.0, 120.0)
    plus = W.window_mean(make_rows(h), series, 80.0, 120.0, time_tangent=False)[0]
    minus = W.window_mean(make_rows(-h), series, 80.0, 120.0, time_tangent=False)[0]
    assert tangent == pytest.approx((plus - minus) / (2 * h), rel=1e-5)
    assert value == pytest.approx(W.window_mean(make_rows(0.0), series, 80.0, 120.0, time_tangent=False)[0], rel=0, abs=0)


def test_frozen_time_differs_from_dual_time_when_time_depends_on_alpha():
    dual = W.window_mean(make_rows(0.0), "fx", 80.0, 120.0)[1]
    frozen = W.window_mean(make_rows(0.0), "fx", 80.0, 120.0, time_tangent=False)[1]
    assert dual != frozen


def test_primal_matches_the_registered_fd08_window_helpers_on_the_archived_baseline():
    with tarfile.open(ARCHIVE) as tar:
        text = tar.extractfile(BASELINE_CSV).read().decode()
    path = Path(__file__).with_name("_baseline_tmp.csv")
    try:
        path.write_text(text)
        criteria = json.loads((ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json").read_text())
        reference = io_ref.recompute_force_n(path, criteria)
        rows = [{"step": r["step"], "t_u_l": r["t_u_l"], "t_u_l_tan": 0.0,
                 **{name: r[col] for name, col in zip(W.SERIES, ("fx_solver", "fy_solver", "fz_solver", "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver"))},
                 **{name + "_tan": 0.0 for name in W.SERIES}} for r in io_ref.read_force_history(path)]
    finally:
        path.unlink(missing_ok=True)
    assert W.window_mean(rows, "fx", 80.0, 120.0)[0] * W.FORCE_SCALE_N_PER_SOLVER == pytest.approx(reference["drag_n"], rel=1e-12)
    assert W.window_mean(rows, "-fz", 80.0, 120.0)[0] * W.FORCE_SCALE_N_PER_SOLVER == pytest.approx(reference["downforce_n"], rel=1e-12)
    case = criteria["measurement"]["case"]
    assert reference["force_scale_n_per_solver_force"] == pytest.approx(W.FORCE_SCALE_N_PER_SOLVER, rel=1e-15)
    assert case["flow_spacing_m"] == pytest.approx(1 / 30)


def test_history_that_does_not_bracket_the_window_is_rejected():
    with pytest.raises(ValueError):
        W.window_mean(make_rows(0.0, steps=range(8, 4000, 8)), "fx", 80.0, 120.0)
