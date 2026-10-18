"""v18 analytic plate (#60): shape, parameter rules, mode conventions and the harness state model.  Solver-free, ~10 s."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import mode01_modes as M  # noqa: E402
import mode01_prescreen as P  # noqa: E402
import v18_plate as V  # noqa: E402

S, PAR = V.build_parent()
X, Y, Z = V.axes(S)
MODES = ("heave", "pitch", "camber", "reflex", "thick_chord", "twist", "dihedral", "sweep", "surge", "twist_anti", "thickness_D0", "offset_s125", "corrugation")


def test_parent_fills_the_v17_box_and_keeps_ride_height():
    p = PAR
    assert math.isclose(p["L"] * math.cos(p["alpha"]) + p["t"], 1.15) and math.isclose(p["L"] * math.sin(p["alpha"]) + p["t"], 0.5)
    lowest = p["zc"] - p["L"] / 2 * math.sin(p["alpha"]) - p["t"] / 2
    assert math.isclose(lowest, -0.25, abs_tol=1e-12)
    assert S.phi.dtype == np.dtype("<f4") and np.isfinite(S.phi).all()
    assert (S.phi[:, [14, 50], :] >= np.float32(0.0125)).all()  # the end layers outside the design mask stay fluid (12.5 mm off the flat tips)
    assert not ((S.phi < 0) & ~S.design_mask).any()


def test_parent_is_an_exact_sdf_and_gate_friendly():
    g = np.stack(np.gradient(S.phi.astype(np.float64), S.spacing_m))
    band = (np.abs(S.phi) < 0.02) & M.active_mask(S)
    assert np.median(np.abs(np.sqrt((g ** 2).sum(0))[band] - 1)) < 1e-6
    assert P.crossing_slope_failures(S.phi) == 0 and P.count(S, S.phi) < P.N_MAX
    assert int((np.abs(S.phi) < 1e-7).sum()) == 0          # no tie plateau on nodes
    from cfd_sdf.design.volume_semantics import _corner_mean
    tie = _corner_mean(S.phi) == 0                          # the flat tips sit on the cell-centre plane: exact-zero centres, counted fluid, mode-invariant
    assert tie.any() and set(np.nonzero(tie)[1]) <= {14, 49}


@pytest.mark.parametrize("mode", MODES)
def test_zero_amplitude_is_parent_and_inactive_nodes_keep_parent_bytes(mode):
    assert V.mode_phi(S, PAR, mode, 0.0).tobytes() == S.phi.tobytes()
    a = {"pitch": 1.0, "twist": 2.0, "twist_anti": 2.0, "thick_chord": 0.05}.get(mode, 5.0)
    new = V.mode_phi(S, PAR, mode, a)
    assert np.array_equal(new[~M.active_mask(S)], S.phi[~M.active_mask(S)])
    h = V.harness_state(S, new)
    assert np.abs(h.phi.astype(np.float64) - new).max() < 1e-7 and np.array_equal(h.phi[~M.active_mask(S)], S.phi[~M.active_mask(S)])


def test_rigid_heave_by_one_spacing_is_a_lattice_shift():
    new = V.mode_phi(S, PAR, "heave", 25.0)
    act = M.active_mask(S)
    act[:, :, 0] = False
    assert np.abs(new[:, :, 1:][act[:, :, 1:]] - S.phi[:, :, :-1][act[:, :, 1:]]).max() < 1e-7


def test_sign_conventions():
    assert Z[V.mode_phi(S, PAR, "heave", 10.0) < 0].mean() > Z[S.phi < 0].mean()
    le = X < -0.4
    assert Z[(V.mode_phi(S, PAR, "pitch", 2.0) < 0) & le].mean() < Z[(S.phi < 0) & le].mean()  # + = nose down
    mid = np.abs(X - PAR["xc"]) < 0.1
    assert Z[(V.mode_phi(S, PAR, "camber", 30.0) < 0) & mid].mean() > Z[(S.phi < 0) & mid].mean()  # + = mid-chord up


def test_twist_anti_is_mirror_odd_and_volume_neutral_modes_keep_continuum_volume():
    plus, minus = V.mode_phi(S, PAR, "twist_anti", 2.0), V.mode_phi(S, PAR, "twist_anti", -2.0)
    assert np.abs(plus - minus[:, ::-1, :]).max() < 1e-6
    t2 = PAR["t"] * 1.05
    L2 = (PAR["L"] * PAR["t"] + math.pi * PAR["t"] ** 2 / 4 - math.pi * t2 ** 2 / 4) / t2
    assert math.isclose(V.volume(L2, t2), V.volume(PAR["L"], PAR["t"]), rel_tol=1e-12)
    for mode, a in (("heave", 20.0), ("pitch", 2.0), ("camber", 30.0), ("twist", 3.0), ("dihedral", 30.0), ("thick_chord", 0.05)):
        assert abs(P.count(S, V.mode_phi(S, PAR, mode, a)) / P.count(S, S.phi) - 1) < 0.03, mode
