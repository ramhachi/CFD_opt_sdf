import math
import json

import numpy as np
import pytest

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.gradients.directional_fd import (
    BASELINE_REPEATS,
    DIRECTION_IDS,
    EPSILON_LADDER_M,
    PLATEAU_RELATIVE_TOLERANCE,
    RESOLUTION_FACTOR,
    DirectionalFDEvaluation,
    DirectionalFDRequest,
    baseline_noise_floor,
    classify_direction,
    direction_sha256,
    generate_directions,
    interface_taper,
    perturbation_case_ids,
    perturbed_state,
    phi_sha256,
    registered_run_order,
    stationarity_drift,
    validate_directions,
    zero_level_margin_m,
)


def make_state(shape=(21, 21, 21)):
    spacing = 0.05
    axes = [(np.arange(n) - (n - 1) / 2) * spacing for n in shape]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    phi = np.sqrt(x * x + y * y + z * z).astype(np.float32) - np.float32(0.2)
    design = np.ones(shape, dtype=bool)
    fixed = np.zeros(shape, dtype=bool)
    forbidden = np.zeros(shape, dtype=bool)
    root = np.zeros(shape, dtype=bool)
    fixed[shape[0] // 2, shape[1] // 2, shape[2] // 2] = True
    forbidden[1, 1, 1] = True
    root[-2, -2, -2] = True
    return SDFDesignState.create(
        phi=phi,
        origin_m=tuple(-0.5 * (n - 1) * spacing for n in shape),
        spacing_m=spacing,
        design_mask=design,
        fixed_solid_mask=fixed,
        forbidden_mask=forbidden,
        root_mask=root,
        narrow_band_width_m=0.1,
    )


def make_pairs(slopes, *, epsilons=EPSILON_LADDER_M, baseline=0.4):
    return [
        {
            "epsilon_m": epsilon,
            "plus_response": baseline + epsilon * slope,
            "minus_response": baseline - epsilon * slope,
        }
        for epsilon, slope in zip(epsilons, slopes)
    ]


def test_direction_generator_reproducibility_masks_hashes_and_cosines():
    state = make_state()
    first = generate_directions(state)
    second = generate_directions(state)
    audit = validate_directions(state, first)

    assert tuple(first) == DIRECTION_IDS
    assert audit["shape"] == list(state.shape)
    assert audit["dtype"] == "float32"
    assert audit["direction_sha256"] == {
        direction_id: direction_sha256(second[direction_id])
        for direction_id in DIRECTION_IDS
    }
    active = state.design_mask & ~state.fixed_solid_mask & ~state.forbidden_mask & ~state.root_mask
    for direction_id in DIRECTION_IDS:
        np.testing.assert_array_equal(first[direction_id], second[direction_id])
        assert first[direction_id].dtype == np.float32
        assert first[direction_id].shape == state.shape
        assert np.all(first[direction_id][~active] == 0.0)
        assert np.max(np.abs(first[direction_id])) == pytest.approx(1.0)
    assert all(abs(value) < 0.95 for value in audit["pairwise_cosine"].values())

    # The taper uses the SDF state's declared narrow-band width verbatim.
    modified = state.phi.copy()
    modified[3, 3, 3] = 0.0
    modified[3, 3, 4] = state.narrow_band_width_m / 2
    modified[3, 3, 5] = state.narrow_band_width_m
    taper_state = SDFDesignState.create(
        phi=modified,
        origin_m=state.origin_m,
        spacing_m=state.spacing_m,
        design_mask=state.design_mask,
        fixed_solid_mask=state.fixed_solid_mask,
        forbidden_mask=state.forbidden_mask,
        root_mask=state.root_mask,
        narrow_band_width_m=state.narrow_band_width_m,
    )
    taper = interface_taper(taper_state)
    assert taper[3, 3, 3] == pytest.approx(1.0)
    assert taper[3, 3, 4] == pytest.approx(0.5)
    assert taper[3, 3, 5] == pytest.approx(0.0, abs=1e-15)


def test_perturbations_are_direct_float32_edits_and_keep_masks_parent_and_margin():
    state = make_state()
    directions = generate_directions(state)
    before = state.phi.copy()
    plus, plus_identity = perturbed_state(
        state, directions[DIRECTION_IDS[1]], epsilon_m=0.0025, sign=1
    )
    minus, minus_identity = perturbed_state(
        state, directions[DIRECTION_IDS[1]], epsilon_m=0.0025, sign=-1
    )

    np.testing.assert_array_equal(state.phi, before)
    for child, identity, sign in ((plus, plus_identity, 1), (minus, minus_identity, -1)):
        for name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"):
            np.testing.assert_array_equal(getattr(child, name), getattr(state, name))
        np.testing.assert_array_equal(child.phi[~state.design_mask], state.phi[~state.design_mask])
        expected = np.asarray(
            state.phi.astype(np.float64)
            + (sign * 0.0025) * directions[DIRECTION_IDS[1]].astype(np.float64),
            dtype=np.float32,
        )
        expected[~(state.design_mask & ~state.fixed_solid_mask & ~state.forbidden_mask & ~state.root_mask)] = state.phi[
            ~(state.design_mask & ~state.fixed_solid_mask & ~state.forbidden_mask & ~state.root_mask)
        ]
        np.testing.assert_array_equal(child.phi, expected)
        assert identity["masks_unchanged"] is True
        assert identity["outside_design_phi_identical"] is True
        assert identity["reinitialization_applied"] is False
        assert identity["volume_correction_applied"] is False
        assert identity["clipping_applied"] is False
        assert identity["maximum_pointwise_change_m"] <= 0.0025 + 1.2e-8
        assert identity["zero_level_margin_m"] >= identity["margin_gate_m"] == 0.15
        assert identity["phi_c_order_sha256"] == phi_sha256(child.phi, order="C")
        assert identity["phi_fortran_order_sha256"] == phi_sha256(child.phi, order="F")
    assert plus.state_sha256 != minus.state_sha256
    with pytest.raises(ValueError, match="margin gate"):
        perturbed_state(state, directions[DIRECTION_IDS[0]], epsilon_m=0.01, sign=1,
                        margin_gate_m=2.0)
    with pytest.raises(ValueError, match="float32"):
        perturbed_state(state, directions[DIRECTION_IDS[0]].astype(np.float64),
                        epsilon_m=0.001, sign=1)


def test_zero_level_margin_does_not_qualify_an_empty_solid():
    assert math.isinf(zero_level_margin_m(np.ones((3, 3, 3), dtype=np.float32), 0.05))


def test_all_30_preregistered_perturbations_and_fixed_33_run_order():
    assert len(perturbation_case_ids()) == 30
    order = registered_run_order()
    assert len(order) == 33
    assert order[0] == "baseline_A"
    assert order[17] == "baseline_B"
    assert order[-1] == "baseline_C"
    assert len(order[1:17]) == 16
    for start, stop in ((1, 17), (18, 32)):
        chunk = order[start:stop]
        assert len(chunk) % 2 == 0
        for plus_id, minus_id in zip(chunk[::2], chunk[1::2]):
            assert plus_id.endswith("__plus")
            assert minus_id.endswith("__minus")
            assert plus_id.removesuffix("__plus") == minus_id.removesuffix("__minus")
    assert order[1].startswith("D0_interface_offset__eps_0p0005m__plus")
    assert order[16].startswith("D1_filtered_seed11__eps_0p0025m__minus")
    assert order[18].startswith("D1_filtered_seed11__eps_0p0050m__plus")
    assert order[31].startswith("D2_filtered_seed2026__eps_0p0100m__minus")


def test_baseline_noise_floor_and_stationarity_boundaries():
    baseline = baseline_noise_floor((0.3360, 0.3361, 0.3362))
    assert baseline["median"] == pytest.approx(0.3361)
    assert baseline["span"] == pytest.approx(0.0002)
    assert baseline["noise_floor"] == pytest.approx(0.0002)
    assert baseline_noise_floor((0.0, 0.0, 0.0))["noise_floor"] == 1e-8
    with pytest.raises(ValueError):
        baseline_noise_floor((1.0, 1.0))
    with pytest.raises(ValueError):
        baseline_noise_floor((1.0, math.inf, 1.0))
    assert stationarity_drift(1.0, 1.02, 1.0) == pytest.approx(0.02)
    assert stationarity_drift(1.0, 1.02001, 1.0) > 0.02


def test_centered_fd_exact_ladder_resolution_plateau_and_even_diagnostic():
    result = classify_direction(make_pairs([2.0, 2.02, 1.98, 2.0, 2.01]),
                                baseline_median=0.4, noise_floor=1e-8)
    assert result["resolved_count"] == 5
    assert result["plateau_epsilon_m"] == list(EPSILON_LADDER_M[:3])
    assert result["reference_directional_derivative"] == pytest.approx(2.0)
    assert result["plateau_max_relative_deviation"] <= PLATEAU_RELATIVE_TOLERANCE
    assert result["sign_stable"] is True
    assert result["plateau_pass"] is True
    assert all(row["even_nonlinearity"] == pytest.approx(0.0, abs=1e-15)
               for row in result["all_epsilons"])
    # Exact signal threshold: |R+ - R-| == 20 * baseline noise floor.
    threshold = classify_direction(make_pairs([0.0, 0.0, 4e-5, 2e-5, 1e-5]),
                                    baseline_median=0.0, noise_floor=1e-8)
    assert threshold["all_epsilons"][2]["pair_signal"] == pytest.approx(2e-7)
    assert threshold["all_epsilons"][3]["resolved"] is True
    assert threshold["plateau_epsilon_m"] == list(EPSILON_LADDER_M[2:])
    assert threshold["directional_noise_equivalent"] > 0.0


@pytest.mark.parametrize(
    "pairs, expected",
    [
        (make_pairs([1e-6] * 5), False),
        (make_pairs([2.0, 2.0, -2.0, -2.0, -2.0]), False),
        (make_pairs([2.0, 2.2, 1.8, 2.0, 2.0]), False),
    ],
)
def test_centered_fd_rejects_unresolved_sign_flip_and_nonplateau(pairs, expected):
    result = classify_direction(pairs, baseline_median=0.4, noise_floor=1e-8)
    assert result["plateau_pass"] is expected


def test_centered_fd_rejects_changed_ladder_thresholds_and_nonfinite_inputs():
    with pytest.raises(ValueError, match="epsilon ladder"):
        classify_direction(make_pairs([1.0] * 5, epsilons=(0.001,) * 5),
                           baseline_median=0.0, noise_floor=1e-8)
    with pytest.raises(ValueError, match="epsilon ladder"):
        classify_direction(make_pairs([1.0] * 5, epsilons=EPSILON_LADDER_M[:-1]),
                           baseline_median=0.0, noise_floor=1e-8)
    with pytest.raises(ValueError, match="thresholds"):
        classify_direction(make_pairs([1.0] * 5), baseline_median=0.0,
                           noise_floor=1e-8, plateau_tolerance=1.0)


def test_unresolved_fd_result_is_json_safe_and_remains_unqualified():
    result = classify_direction(
        make_pairs([0.0] * len(EPSILON_LADDER_M)),
        baseline_median=0.4,
        noise_floor=1e-8,
    )
    assert result["resolved_count"] == 0
    assert result["plateau_pass"] is False
    assert result["reference_directional_derivative"] is None
    assert result["directional_noise_equivalent"] is None
    assert result["plateau_max_relative_deviation"] is None
    json.dumps(result, allow_nan=False)


def test_request_and_qualified_evaluation_require_complete_33_run_evidence():
    request = DirectionalFDRequest(
        parent_state_sha256="a" * 64,
        response_ids=("drag", "downforce"),
        direction_ids=DIRECTION_IDS,
        epsilon_ladder_m=EPSILON_LADDER_M,
        backend_identity="registered flow_16 T4 cohort",
    )
    baseline = {
        response: {"median": 1.0, "min": 1.0, "max": 1.0, "span": 0.0, "noise_floor": 1e-8}
        for response in request.response_ids
    }
    passing = {"resolved_count": 5, "plateau_pass": True}
    results = {direction: {response: passing for response in request.response_ids}
               for direction in request.direction_ids}
    hashes = {run_id: "b" * 64 for run_id in registered_run_order()}
    kwargs = dict(
        request=request,
        direction_sha256={direction: "c" * 64 for direction in DIRECTION_IDS},
        raw_run_sha256=hashes,
        baseline_responses=baseline,
        direction_results=results,
        backend_fingerprint_sha256="d" * 64,
        evidence_sha256={"criteria": "e" * 64},
        qualified=True,
    )
    assert DirectionalFDEvaluation(**kwargs).qualified is True
    with pytest.raises(ValueError, match="exact 33-run"):
        DirectionalFDEvaluation(**{**kwargs, "raw_run_sha256": dict(list(hashes.items())[:-1])})
    with pytest.raises(ValueError, match="direction IDs"):
        DirectionalFDEvaluation(**{**kwargs, "direction_results": {}})
