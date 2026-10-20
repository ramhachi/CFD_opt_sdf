"""WIDTH-RULE candidate rules on small fixtures: a round bar (smooth, 4.6h thick) whose cell occupancy grows one-cell nubs at some placements,
a 0.75h sheet (genuinely thin), a 3h slab, and the opening defect on voxel boxes.  Plan: docs/width_rule_plan_2026_10_20.md."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import width_rule_study as W  # noqa: E402

N, K, I3 = 17, 4, np.eye(3)
C0 = (N - 1) / 2


def _phi(inside, c):
    return W.synthetic_phi(inside, I3, np.asarray(c, float), n=N, k=K)


def _bar(x, y, z):  # round bar, radius 2.3h (v18's edge radius), axis along y
    return (x * x + z * z <= 2.3 ** 2) & (np.abs(y) <= 4)


def test_round_bar_r0_fails_at_some_placements_r1_r3_never():
    rows = [W.measure(_phi(_bar, [C0 + dx, C0, C0 + dz])) for dx in (0, 0.25, 0.5, 0.75) for dz in (0, 0.25, 0.5, 0.75)]
    assert any(abs(r["r0"]["solid"] - W.H) < 1e-12 for r in rows)  # a one-cell nub: exactly one cell wide
    assert all(r["r1"]["status"] == "pass" and r["r3"]["status"] == "pass" for r in rows)


def test_thin_sheet_fails_every_rule_thick_box_passes_r1_r3():
    thin, thick = (W.measure(_phi(W.SHAPES[n]["inside"], [C0 + 0.3] * 3)) for n in ("slab_w0.75", "slab_w3"))
    assert all(thin[r]["status"] != "pass" for r in W.RULES)
    assert thick["r1"]["status"] == thick["r3"]["status"] == "pass"
    assert thick["r0"]["solid"] == W.H  # the occupancy drops the box's corner cells: a one-cell fin along each edge


def test_sign_rules_ignore_phi_scale_r1_does_not():
    phi = _phi(W.SHAPES["slab_w0.75"]["inside"], [C0 + 0.3] * 3)
    assert W.r3(2 * phi, W.H) == W.r3(phi, W.H)
    assert W.r1(10 * phi, W.H)["status"] == "pass"  # the ridge reads phi units: a thin sheet with |grad phi| = 10 passes R1


def test_opening_defect_basics():
    b = np.zeros((40, 40, 40), bool)
    b[5:35, 5:35, 5:35] = True
    assert W.opening_defect(b, 1.0, 3.0) <= 3 * (3 ** 0.5 - 1) + 3 ** 0.5  # right-angle vertices only: r (sqrt3 - 1) plus one voxel diagonal
    b[18:21, 18:21, 35:39] = True  # 3x3 spike, 4 long: no radius-3 ball fits in it
    assert W.opening_defect(b, 1.0, 3.0) >= 3
    assert W.opening_defect(np.zeros((4, 4, 4), bool), 1.0, 1.0) is None
