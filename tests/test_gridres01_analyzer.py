"""GRIDRES-01 analyzer: every verdict branch on synthetic tables, the guard-band edges, the residual INCOMPLETE rule, and the retained flow_24/flow_32 reproduction from the real CSVs."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_gridres01 as A  # noqa: E402
import gridres01_states as G  # noqa: E402


def table(a, b, bump=0.0, drag=(0.0, 0.0), base=0.33):
    """One grid's five-state table with downforce change a*s + b*s^2 (a bump added at +1.25 mm) and drag change drag[0]*s + drag[1]*s^2."""
    out = {G.PARENT_NAME: {"downforce_n": base, "drag_n": 0.32}}
    for s in G.STEPS_MM:
        out[G.state_name(s)] = {"downforce_n": base + a * s + b * s * s + (bump if s == 1.25 else 0.0), "drag_n": 0.32 + drag[0] * s + drag[1] * s * s}
    return out


T24, T32 = table(9.9e-5, -2.28e-4), table(4.75e-4, -7.6e-5)


def verdict(a, b, **kw):
    return A.report({"flow_24": T24, "flow_32": T32, "flow_40": table(a, b, **kw)}, "flow_40")


def test_fit_recovers_synthetic_coefficients_and_g_max_endpoint_and_vertex():
    fit = A.lsq({s: 3e-4 * s - 5e-5 * s * s for s in G.STEPS_MM})
    assert fit["a"] == pytest.approx(3e-4) and fit["b"] == pytest.approx(-5e-5) and fit["max_residual_n"] < 1e-15
    assert A.g_max(4e-5, 0.0) == pytest.approx(5e-5)                       # endpoint
    assert A.g_max(1e-4, -2.28e-4) == pytest.approx(1e-4 ** 2 / (4 * 2.28e-4))  # interior vertex at 0.22 mm
    assert A.g_max(-1e-4, -1e-4) == 0.0 and A.g_max(-1e-4, 5e-5) == 0.0   # never positive: the s -> 0 limit


@pytest.mark.parametrize("a,b,expected", [(4.75e-4, -7.6e-5, "FLOW40_SIDES_WITH_FLOW32"), (9.9e-5, -2.28e-4, "FLOW40_SIDES_WITH_FLOW24"), (3e-5, 0.0, "FLOW40_AMBIGUOUS"),
                                          (0.0, 0.0, "FLOW40_SIDES_WITH_FLOW24"), (-1e-4, 5e-5, "FLOW40_SIDES_WITH_FLOW24")])
def test_each_verdict_branch(a, b, expected):
    assert verdict(a, b)["verdict"] == expected  # a=3e-5, b=0: G_max = 3.75e-5, inside the guard band


def test_guard_band_edges_are_strict():
    up, dn = float(np.nextafter(A.HI_N, 1)), float(np.nextafter(A.LO_N, 0))
    assert [A.classify(x) for x in (up, A.HI_N, A.LO_N, dn)] == ["SIDES_WITH_FLOW32", "AMBIGUOUS", "AMBIGUOUS", "SIDES_WITH_FLOW24"]
    assert verdict(4e-5 / 1.25 * 1.001, 0.0)["verdict"] == "FLOW40_SIDES_WITH_FLOW32" and verdict(2e-5 / 1.25 * 0.999, 0.0)["verdict"] == "FLOW40_SIDES_WITH_FLOW24"


def test_a_fit_residual_above_2e_5_makes_the_run_incomplete_on_any_grid():
    assert verdict(4.75e-4, -7.6e-5, bump=1.5e-5)["verdict"] == "FLOW40_SIDES_WITH_FLOW32"   # residual below the limit stays decidable
    bad = verdict(4.75e-4, -7.6e-5, bump=1e-4)
    assert bad["verdict"] == "INCOMPLETE" and bad["max_downforce_fit_residual_n"] > A.RESIDUAL_MAX_N
    rep = A.report({"flow_24": table(9.9e-5, -2.28e-4, bump=1e-4), "flow_32": T32, "flow_40": table(4.75e-4, -7.6e-5)}, "flow_40")
    assert rep["verdict"] == "INCOMPLETE"


def test_flow_48_uses_the_same_code():
    rep = A.report({"flow_24": T24, "flow_32": T32, "flow_48": table(4.75e-4, -7.6e-5)}, "flow_48")
    assert rep["verdict"] == "FLOW48_SIDES_WITH_FLOW32" and rep["fine_grid"] == "flow_48"


def test_report_only_labels_and_acceptance_emulation_and_drag_fit():
    spread = 4.75e-4 - 9.9e-5
    beyond = verdict(4.75e-4 + 0.8 * spread, -7.6e-5)["report_only_labels"]   # past flow_32 by 0.8 of the 24-32 spread: not contracting, a third value
    assert beyond["contracting"] is False and beyond["third_value"] is True and beyond["ratios"]["a"] == pytest.approx(0.8, rel=1e-6)
    between = verdict(9.9e-5 + 0.45 * spread, -7.6e-5)["report_only_labels"]   # 0.55 of the spread from flow_32: contracting, within half of one of the two
    assert between["contracting"] is True and between["third_value"] is False
    near32 = verdict(4.8e-4, -7.7e-5)["report_only_labels"]
    assert near32["contracting"] is True and near32["third_value"] is False
    rep = verdict(4.75e-4, -7.6e-5, drag=(-1e-4, 2e-5))
    emu = rep["grids"]["flow_40"]["acceptance_emulation"]
    assert set(emu) == {"0.3125", "0.625", "1.25"} and all(v["accepted"] for v in emu.values())   # gain > 3e-5, drag change <= 0
    assert rep["grids"]["flow_40"]["fit"]["drag"]["a"] == pytest.approx(-1e-4) and rep["grids"]["flow_40"]["fit"]["drag"]["b"] == pytest.approx(2e-5)
    flat = verdict(1e-5, 0.0, drag=(1e-4, 0.0))["grids"]["flow_40"]["acceptance_emulation"]
    assert not any(v["accepted"] for v in flat.values())   # gain below 3e-5 N and a computed drag increase
    assert verdict(4.75e-4, -7.6e-5)["grids"]["flow_40"]["forward_fit"]["downforce"]["a"] == pytest.approx(4.75e-4)  # forward-only uses the three positive steps


def test_retained_flow_24_and_flow_32_fits_reproduce_the_plan_figures_from_the_real_csvs():
    t = A.retained_tables()
    r24, r32 = A.grid_report(t["flow_24"]), A.grid_report(t["flow_32"])
    f24, f32 = r24["fit"]["downforce"], r32["fit"]["downforce"]
    # the plan's figures come from the six retained states of each grid; the matched five-state subset is within a few percent
    assert f24["a"] == pytest.approx(9.9e-5, rel=0.03) and f24["b"] == pytest.approx(-2.28e-4, rel=0.03) and f24["max_residual_n"] < 6e-6
    assert f32["a"] == pytest.approx(4.75e-4, rel=0.03) and f32["b"] == pytest.approx(-7.6e-5, rel=0.03) and f32["max_residual_n"] < 1.1e-5
    assert r24["g_max_n"] == pytest.approx(1.1e-5, rel=0.06) and r32["g_max_n"] == pytest.approx(4.75e-4, rel=0.02)
    assert A.classify(r24["g_max_n"]) == "SIDES_WITH_FLOW24" and A.classify(r32["g_max_n"]) == "SIDES_WITH_FLOW32"
    assert not any(v["accepted"] for v in r24["acceptance_emulation"].values()) and all(v["accepted"] for v in r32["acceptance_emulation"].values())


def test_a_tampered_retained_csv_is_refused(tmp_path):
    import shutil
    root = tmp_path
    shutil.copytree(ROOT / G.OPT01B_REL, root / G.OPT01B_REL, ignore=shutil.ignore_patterns("*.raw", "*.log"))
    A.retained_tables(root)   # untampered copy passes the pinned-hash gates
    csv = root / G.OPT01B_REL / "kernel_output/opt01b_a/states/opt01b__parent/flow_24.forces.csv"
    csv.write_text(csv.read_text().replace("\n", "\n", 1) + "\n")
    with pytest.raises(ValueError, match="retained force CSV differs"):
        A.retained_tables(root)


def test_analyze_fails_closed_without_a_valid_freeze(tmp_path):
    rep = A.analyze("flow_40", tmp_path, {"kind": "nope"})
    assert rep["verdict"] == "INCOMPLETE" and rep["integrity"]["pass"] is False and rep["integrity"]["failures"]
