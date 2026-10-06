"""Solver-free tests for the frozen R6/formal design contract."""

import numpy as np

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.fd08_v2_campaign import (
    FORMAL_EPSILON_MM,
    R6_EPSILON_MM,
    campaign_verdict,
    classify_formal_comparison,
    construct_state,
    formal_prediction,
    generate_p1,
    build_state_inventory,
    DIRECTION_IDS,
)
from cfd_sdf.gradients.directional_fd import generate_directions


def _state():
    x, y, z = np.mgrid[-4:5, -4:5, -4:5]
    phi = (np.sqrt(x * x + y * y + z * z) - 2.0).astype(np.float32) * 0.2
    shape = phi.shape
    design = np.ones(shape, dtype=bool)
    fixed = np.zeros(shape, dtype=bool)
    fixed[0] = True
    forbidden = np.zeros(shape, dtype=bool)
    forbidden[:, 0] = True
    root = np.zeros(shape, dtype=bool)
    root[:, :, 0] = True
    return SDFDesignState.create(
        phi=phi,
        origin_m=(-0.8, -0.8, -0.8),
        spacing_m=0.2,
        design_mask=design,
        fixed_solid_mask=fixed,
        forbidden_mask=forbidden,
        root_mask=root,
        narrow_band_width_m=0.4,
    )


def test_frozen_r6_and_formal_ladders_are_deterministic_and_interior():
    assert len(R6_EPSILON_MM) == 6
    assert all(a < b for a, b in zip(R6_EPSILON_MM, R6_EPSILON_MM[1:]))
    assert len(FORMAL_EPSILON_MM) == 3
    assert all(value not in R6_EPSILON_MM for value in FORMAL_EPSILON_MM)
    assert FORMAL_EPSILON_MM == tuple(
        float(np.sqrt(R6_EPSILON_MM[i] * R6_EPSILON_MM[i + 1]))
        for i in (0, 2, 4)
    )


def test_p1_is_finite_normalized_and_respects_all_protected_masks():
    state = _state()
    direction, audit = generate_p1(state)
    assert direction.dtype == np.dtype("<f4")
    assert direction.flags.c_contiguous
    assert np.isfinite(direction).all()
    assert np.max(np.abs(direction)) == 1.0
    assert np.all(direction[state.fixed_solid_mask] == 0)
    assert np.all(direction[state.forbidden_mask] == 0)
    assert np.all(direction[state.root_mask] == 0)
    assert audit["center_bbox_fraction"] == [0.25, 0.5, 0.5]


def test_state_construction_keeps_masks_and_constrained_phi_fixed():
    state = _state()
    direction, _ = generate_p1(state)
    child, audit = construct_state(state, direction, R6_EPSILON_MM[0], 1)
    fixed = state.fixed_solid_mask | state.forbidden_mask | state.root_mask | ~state.design_mask
    assert np.array_equal(child.phi[fixed].view("<u4"), state.phi[fixed].view("<u4"))
    for name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"):
        assert np.array_equal(getattr(child, name), getattr(state, name))
    assert audit["changed_node_count"] > 0


def test_formal_prediction_and_decision_have_expected_limits():
    params = {"sigma0_n": 3e-6, "rho": 0.05, "tol_hold": 0.15, "k_mag": 5}
    prediction = formal_prediction(FORMAL_EPSILON_MM[1], [-2e-4, 1e-7], [[1e-10, 0], [0, 1e-16]], params)
    passed = classify_formal_comparison(-1e-4, -1.05e-4, 1e-6, params)
    failed = classify_formal_comparison(-1e-4, 1e-4, 1e-6, params)
    unresolved = classify_formal_comparison(-1e-6, -1e-6, 1e-6, params)
    assert prediction["s_pred_n"] < 0 and prediction["sigma_pred_n"] > 0
    assert passed["verdict"] == "PASS"
    assert failed["verdict"] == "FAIL"
    assert unresolved["verdict"] == "UNRESOLVED"
    assert campaign_verdict(["PASS", "PASS"]) == "PASS"
    assert campaign_verdict(["PASS", "UNRESOLVED"]) == "UNRESOLVED"
    assert campaign_verdict(["PASS", "FAIL"]) == "FAIL"


def test_formal_inventory_has_25_states_and_stays_disjoint_from_r6_ladder():
    state = _state()
    directions = generate_directions(state)
    p1, _ = generate_p1(state)
    directions["P1_upstream_lobe"] = p1
    inventory, formal_bytes, audits = build_state_inventory(
        state, directions, FORMAL_EPSILON_MM, expected_state_count=25
    )
    _, r6_bytes, _ = build_state_inventory(state, directions)
    assert tuple(directions) == DIRECTION_IDS
    assert len(inventory) == 25 and len(formal_bytes) == 25 and len(audits) == 12
    assert len({formal_bytes[row["phi_raw_file"]] for row in inventory}) == 25
    formal_signed = {formal_bytes[row["phi_raw_file"]] for row in inventory if row["kind"] != "baseline"}
    assert not (formal_signed & set(r6_bytes.values()))
    assert {row["epsilon_mm"] for row in inventory if row["kind"] != "baseline"} == set(FORMAL_EPSILON_MM)
