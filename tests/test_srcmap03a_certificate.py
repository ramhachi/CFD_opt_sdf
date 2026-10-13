"""SRCMAP-03a certificate logic on tiny synthetic fields; no retained-evidence run."""
import importlib.util
from pathlib import Path

import numpy as np
import trimesh

spec = importlib.util.spec_from_file_location("srcmap03a", Path(__file__).parents[1] / "scripts/certify_p22_v17_sign_invariance.py")
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)


def one_cell(other_seven, band_value):
    """3x3x3 field; the corner (0,0,0) of cell (0,0,0) is the only band node, the other seven corners are given."""
    phi = np.ones((3, 3, 3), np.float32)
    for (i, j, k), v in zip(C.OFFSETS[1:], other_seven):
        phi[i, j, k] = v
    phi[0, 0, 0] = band_value
    band = np.zeros(phi.shape, bool); band[0, 0, 0] = True
    return phi, band


def test_interval_certificate_flags_an_ambiguous_cell():
    phi, band = one_cell([0.01, 0.01, 0.01, -0.01, -0.01, -0.01, 0.0], 1e-9)  # other corners cancel: the centre sign is the band sign
    r = C.occupancy_certificate(phi, band, np.full(phi.shape, 1e-6, np.float32), C.cell_occupancy_of(phi))
    assert r["ambiguous_cells"] == 1 and not r["pass"]


def test_interval_certificate_passes_when_centre_is_far_from_zero():
    phi, band = one_cell([0.01] * 7, 1e-9)
    r = C.occupancy_certificate(phi, band, np.full(phi.shape, 1e-6, np.float32), C.cell_occupancy_of(phi))
    assert r["ambiguous_cells"] == 0 and r["pass"] and r["endpoints_equal_enumeration_extrema"]


def test_winding_number_of_a_cube():
    m = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    w = C.winding_numbers(np.array([[0, 0, 0], [0.4, 0.4, 0.4], [2, 0, 0], [0, 3, 1]], float), m.vertices.astype(float), m.faces)
    assert np.allclose(w, [1, 1, 0, 0], atol=1e-12)


def test_band_plateau_reports_gap_and_membership():
    phi = np.array([[[1e-9, -2e-8, 0.0], [0.5, -0.5, 0.3], [1.0, 2.0, 3.0]]], np.float32)
    p = C.band_plateau(phi, 1e-6)
    assert p["band_nodes"] == 3 and p["identical_at_lo_rep_hi"] and p["ratio"] > 1e6
    assert (p["negative"], p["positive"], p["exact_zero"]) == (1, 1, 1)


def test_classification_precedence():
    preds = {"a": True, "b": True}
    assert C.classify({"predicates": preds}) == "P22_V17_SIGN_INVARIANCE_CERTIFIED"
    assert C.classify({"predicates": {"a": True, "b": False}}) == "P22_V17_SIGN_INVARIANCE_NOT_CERTIFIED"
    assert C.classify({"predicates": {"a": True, "b": None}}) == "INCOMPLETE"
