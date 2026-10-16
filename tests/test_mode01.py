"""MODE-01 (#60): mode generators and prescreen helpers on the real OPT-01 v1 parent.  MODE01_SLOW=1 also runs the full 13-gate bundle (~2 min)."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import mode01_modes as M  # noqa: E402
import mode01_prescreen as P  # noqa: E402

S = M.load_parent()
ALL = [(m, a) for m in P.AMPS for a in (P.AMPS[m][0],)]


def test_parent_identity_matches_registered_inventory():
    inv = json.loads((ROOT / "docs/evidence/opt01b_stage_b_2026_10_15/inventory.json").read_text())
    row = next(r for r in inv["states"] if r["name"] == "opt01b__parent")
    assert M.phi_fortran_sha(S.phi) == M.PARENT_PHI_FORTRAN_SHA == row["phi_fortran_order_sha256"]


@pytest.mark.parametrize("mode", list(P.AMPS))
def test_zero_amplitude_returns_parent_bytes(mode):
    assert M.mode_phi(S, mode, 0.0).tobytes() == S.phi.tobytes()


def test_tiny_pitch_is_near_identity_and_surge_one_spacing_is_a_lattice_shift():
    assert np.abs(M.mode_phi(S, "pitch", 1e-7) - S.phi).max() < 1e-6
    new = M.mode_phi(S, "surge", 25.0)  # h = 25 mm: phi_new[i] = phi[i-1] where the source is in the lattice and the node is active
    act = M.active_mask(S)
    act[0] = False
    assert np.array_equal(new[1:][act[1:]], S.phi[:-1][act[1:]])


def test_sign_conventions_and_outside_active_untouched():
    X, _, Z = M._axes(S)
    mean_z = lambda phi, sel: Z[(phi < 0) & sel].mean()  # noqa: E731
    nose, tail = X < X[S.phi < 0].mean() - 0.3, X > X[S.phi < 0].mean() + 0.3
    p = M.mode_phi(S, "pitch", 2.0)
    assert mean_z(p, nose) < mean_z(S.phi, nose) and mean_z(p, tail) > mean_z(S.phi, tail)  # + = nose down
    assert mean_z(M.mode_phi(S, "heave", 10.0), X > -9) > mean_z(S.phi, X > -9)  # + = up
    for mode, a in ALL:
        assert np.array_equal(M.mode_phi(S, mode, a)[~M.active_mask(S)], S.phi[~M.active_mask(S)])
        st = M.make_state(S, mode, a)
        assert all(np.array_equal(getattr(st, k), getattr(S, k)) for k in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"))


def test_support_fractions_wide_gt_medium_gt_small():
    f = lambda m, a: M.support_fraction(S, M.mode_phi(S, m, a))["fraction"]  # noqa: E731
    wide = min(f("pitch", 2), f("camber", 20), f("aspect", 0.04), f("heave", 10), f("thickness", 3))
    assert wide > f("bump_lower", 5) > f("bump_small", 5)
    assert f("bump_upper", 5) > f("bump_small", 5)
    assert f("D1_filtered_seed11", 2) > f("bump_small", 5) and f("P1_upstream_lobe", 2) > f("bump_small", 5)  # finding: the grad03 refs are rough, not compact


def test_deterministic_bytes():
    for mode, a in (("pitch", 2.0), ("camber", -20.0), ("bump_upper", 5.0), ("aspect", 0.02)):
        x, y = M.mode_phi(S, mode, a), M.mode_phi(S, mode, a)
        assert x.tobytes() == y.tobytes() and M.phi_fortran_sha(x) == M.phi_fortran_sha(y)


def test_gates_and_projection_on_real_states():
    import evaluate_opt01_v1_states as ev
    base = ev.lowdim.geometry(ev.SDFDesignState.load(ev.canon.INPUTS / "v17_baseline.npz"))
    st = M.make_state(S, "pitch", 1.0)
    r = ev.retained_gates(st, base)
    assert r["gates"]["clearance"] and r["gates"]["smoothed_volume_band"]
    assert ev.sampled_solid_centers_count(S) == P.N_MAX
    assert P.project_p22(S, S.phi)[0] == 0.0  # parent already at the cap
    over = M.mode_phi(S, "aspect", 0.04)
    assert P.count(S, over) > P.N_MAX
    delta, proj = P.project_p22(S, over)
    assert delta < 0 and P.count(S, proj) <= P.N_MAX and P.count(S, np.where(M.active_mask(S), proj.astype(float) - 1e-6, proj).astype("<f4")) > P.N_MAX


def test_plateau_finding_subcell_modes_break_crossing_slope_on_parent_but_not_always_on_regen_parent():
    assert P.crossing_slope_failures(S.phi) == 0
    assert P.crossing_slope_failures(M.mode_phi(S, "surge", 25.0)) == 0  # a whole lattice spacing keeps the sign pattern and slopes
    assert P.crossing_slope_failures(M.mode_phi(S, "heave", 30.0)) > 100  # tie plateau of the parent (measured 746)
    R = P.regen_parent(S)
    assert P.count(R, R.phi) == 8328 and R.design_mask.sum() > S.design_mask.sum()
    assert P.crossing_slope_failures(M.mode_phi(R, "heave", 30.0)) == 0 and P.crossing_slope_failures(M.mode_phi(R, "bump_lower", -5.0)) == 0


@pytest.mark.skipif(not os.environ.get("MODE01_SLOW"), reason="full GEOM-02 bundle takes ~2 min")
def test_full_gate_bundle_on_parent_and_a_mode():
    P._init()
    r = P.work(("parent", 0.0))
    assert r["all_pass"] and r["p22"]["n_phi"] == P.N_MAX and len(r["gate_status"]) == 13
