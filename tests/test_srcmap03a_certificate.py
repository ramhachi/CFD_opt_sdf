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


def brute_force_extrema(phi, band, amp, cell):
    i, j, k = cell
    idx = [(i + a, j + b, k + c) for a, b, c in C.OFFSETS]
    amb = [t for t in idx if band[t]]
    lo, hi = np.inf, -np.inf
    for pattern in range(2 ** len(amb)):
        v = phi.copy()
        for n, t in enumerate(amb):
            v[t] = amp[t] if (pattern >> n) & 1 else -amp[t]
        c = float(C._corner_mean(v[i:i + 2, j:j + 2, k:k + 2])[0, 0, 0])
        lo, hi = min(lo, c), max(hi, c)
    return lo, hi


def test_enumeration_matches_per_cell_brute_force_with_shared_corners_zero_amplitude_and_full_cells():
    rng = np.random.default_rng(7)
    for trial in range(8):
        phi = rng.normal(0.0, 0.02, (5, 5, 5)).astype(np.float32)
        band = rng.random(phi.shape) < (0.15 if trial < 6 else 0.9)  # trials 6-7 make cells with all eight corners ambiguous
        amp = np.where(rng.random(phi.shape) < 0.3, 0.0, rng.uniform(0, 1e-2, phi.shape)).astype(np.float32)  # exact-zero amplitudes included
        e = C.enumerate_cells(phi, band, amp)
        touching = {tuple(c) for c in e["cells"]}
        assert touching == {tuple(c) for c in np.argwhere(C._corner_mean(band.astype(np.float32)) > 0)}
        for n, cell in enumerate(map(tuple, e["cells"])):
            lo, hi = brute_force_extrema(phi, band, amp, cell)
            assert np.float32(lo) == e["cmin"][n] and np.float32(hi) == e["cmax"][n]


def test_plateau_ratio_is_reported_when_the_gap_is_small():
    phi = np.array([[[1e-9, 3e-9, 2e-9], [5e-9, 1.0, 1.0]]], np.float32)
    assert C.band_plateau(phi, 4e-9)["ratio"] < C.PLATEAU_MIN_RATIO


def cube_lattice():
    m = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ax = np.arange(5) * 0.5 - 1.0
    x, y, z = np.meshgrid(ax, ax, ax, indexing="ij")
    phi = (np.maximum.reduce([abs(x), abs(y), abs(z)]) - 0.5).astype(np.float32)  # sign of the cube SDF; nodes with |x|=0.5 lie on the surface
    return m, phi, np.abs(phi) < 1e-6


def test_outside_sign_certification_detects_a_flipped_node_and_a_flipped_mesh():
    m, phi, band = cube_lattice()
    V, F = m.vertices.astype(float), m.faces
    assert C.outside_sign_certification(phi, band, (-1.0, -1.0, -1.0), 0.5, V, F)["pass"]
    bad = phi.copy(); bad[0, 0, 0] = -1.0
    r = C.outside_sign_certification(bad, band, (-1.0, -1.0, -1.0), 0.5, V, F)
    assert r["sign_mismatches_vs_registered"] == 1 and not r["pass"]
    assert not C.outside_sign_certification(phi, band, (-1.0, -1.0, -1.0), 0.5, V, F[:, ::-1])["pass"]


def test_gate_bounds_dominate_random_sign_assignments(monkeypatch):
    from cfd_sdf.design.geometry_gates import _gradient_diagnostics
    from cfd_sdf.design.sdf_state import SDFDesignState
    from cfd_sdf.design.volume_semantics import smoothed_volume_and_gradient
    from cfd_sdf.gradients.directional_fd import zero_level_margin_m
    rng = np.random.default_rng(1); h = 0.1; n = (21, 21, 21)
    X, Y, Z = np.meshgrid(*[np.arange(m) * h - 1.0 for m in n], indexing="ij")
    phi0 = np.minimum(np.maximum.reduce([abs(X) - 0.3, abs(Y) - 0.3, abs(Z) - 0.3]), np.sqrt((X - .45) ** 2 + Y ** 2 + Z ** 2) - 0.2).astype(np.float32)
    near = np.abs(phi0) < 1e-6; phi0[near] += rng.uniform(-5e-4, 5e-4, near.sum()).astype(np.float32)
    tau = np.float32(1e-3); monkeypatch.setattr(C, "TAU_REP", tau)
    mk = lambda p: SDFDesignState.create(phi=p, origin_m=(-1., -1., -1.), spacing_m=h, narrow_band_width_m=0.3, design_mask=np.ones(n, bool))
    s0 = mk(phi0); band = np.abs(phi0) < tau
    g = C.gate_bounds(s0, band, s0, float(np.abs(phi0[band]).max()))
    m0 = float(_gradient_diagnostics(s0)["median_abs_gradient_deviation"]); v0 = smoothed_volume_and_gradient(s0).smoothed_volume_m3
    for t in range(12):
        p = phi0.copy(); p[band] = (rng.choice([-1, 1], band.sum()) * tau if t % 2 else rng.uniform(-1, 1, band.sum()) * tau).astype(np.float32)
        s = mk(p)
        assert abs(float(_gradient_diagnostics(s)["median_abs_gradient_deviation"]) - m0) <= g["eikonal_median"]["bound_tau"]
        assert abs(smoothed_volume_and_gradient(s).smoothed_volume_m3 - v0) <= g["smoothed_volume"]["abs_bound_m3"]
        assert zero_level_margin_m(p, h) >= g["clearance"]["worst_case_margin_m"] - 1e-9


def test_failure_before_a_verdict_is_recorded_as_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "verify_freeze", lambda path: (_ for _ in ()).throw(C.IntegrityError("tampered")))
    assert C.main(tmp_path) == 1
    import json
    assert json.loads((tmp_path / "classification.json").read_text())["terminal_classification"] == "INCOMPLETE"


def test_freeze_verification_rejects_a_modified_manifest(tmp_path):
    import json, pytest
    f = tmp_path / "prerun_freeze.json"; f.write_text(json.dumps({"files": [], "frozen_parameters": {}, "freeze_sha256": "0" * 64}))
    with pytest.raises(C.IntegrityError):
        C.verify_freeze(f)


def test_manifest_check_is_exact_except_named_living_documents(monkeypatch, tmp_path):
    (tmp_path / "ev").mkdir(); (tmp_path / "ev/a.txt").write_text("a"); (tmp_path / "doc.md").write_text("living")
    import hashlib
    h = lambda s: hashlib.sha256(s.encode()).hexdigest()
    m = tmp_path / "SHA256SUMS"; m.write_text(f"{h('a')}  ev/a.txt\n{h('OLD')}  doc.md\n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    assert C.verify_manifest(m, ("doc.md",)) == {"entries_verified": 1, "excluded_living_documents": ["doc.md"], "mismatches": []}
    assert C.verify_manifest(m, ())["mismatches"] == ["doc.md"]  # an unnamed changed entry is a mismatch
    (tmp_path / "ev/a.txt").write_text("changed")
    assert C.verify_manifest(m, ("doc.md",))["mismatches"] == ["ev/a.txt"]
