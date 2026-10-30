"""Numerical contract tests for the differentiable SDF volume primitive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import (
    SMOOTHED_VOLUME_CONTRACT_ID,
    SMOOTHED_VOLUME_CONTRACT_SHA256,
    SMOOTHED_VOLUME_LIMIT_M3,
    SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID,
    SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256,
    VolumeSemanticsError,
    sampled_solid_centers_count,
    sharp_volume_m3,
    smoothed_volume_and_gradient,
)


def _state(
    phi: np.ndarray,
    *,
    spacing_m: float = 0.1,
    design_mask: np.ndarray | None = None,
    fixed_solid_mask: np.ndarray | None = None,
    forbidden_mask: np.ndarray | None = None,
    root_mask: np.ndarray | None = None,
) -> SDFDesignState:
    return SDFDesignState.create(
        phi=phi,
        origin_m=(-1.0, -0.8, -0.6),
        spacing_m=spacing_m,
        design_mask=design_mask,
        fixed_solid_mask=fixed_solid_mask,
        forbidden_mask=forbidden_mask,
        root_mask=root_mask,
        narrow_band_width_m=spacing_m,
    )


def test_registered_v16_sharp_reference_is_bound_without_stage_t_vmax() -> None:
    evidence_path = (
        Path(__file__).resolve().parents[1]
        / "docs/evidence/sdf_native_volume_semantics_v1_2026_09.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert SMOOTHED_VOLUME_CONTRACT_ID == "sdf_native_smoothed_volume_v1"
    assert SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID == "sdf_native_volume_semantics_v1_2026_09"
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == (
        SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256
    )
    assert evidence["contract"]["volume_limit_m3"] == SMOOTHED_VOLUME_LIMIT_M3
    assert evidence["contract"]["volume_limit_source"] == (
        "re-measured voxel-equivalent sharp volume of the registered v16 genesis state (1009 sampled solid centers)"
    )
    assert evidence["measured"]["sampled_solid_centers"] == 1009
    assert SMOOTHED_VOLUME_LIMIT_M3 == pytest.approx(1009 * 0.05**3, abs=1e-16)
    assert SMOOTHED_VOLUME_LIMIT_M3 != pytest.approx(0.0763256681, abs=1e-6)
    assert SMOOTHED_VOLUME_CONTRACT_SHA256 == (
        "56825cd50c0916c5659badd21c84bab517ddb370085a92056d40a9028e8a7969"
    )

    # The frozen sharp-center rule assigns zero-level samples to fluid.
    state = _state(np.zeros((2, 2, 2), dtype=np.float32))
    assert sampled_solid_centers_count(state) == 0
    assert sharp_volume_m3(state) == 0.0


def test_one_sided_cosine_transition_has_known_value_and_node_gradient() -> None:
    spacing_m = 0.1
    state = _state(np.full((2, 2, 2), -spacing_m / 2, dtype=np.float32), spacing_m=spacing_m)

    result = smoothed_volume_and_gradient(state)

    assert result.transition_width_m == spacing_m
    # The frozen center sample is a float32 eight-node mean; -0.05 is not
    # exactly representable, so the analytic value includes that rounding.
    assert result.smoothed_volume_m3 == pytest.approx(0.5 * spacing_m**3, abs=1e-10)
    assert result.sharp_volume_m3 == pytest.approx(spacing_m**3, abs=1e-15)
    assert result.volume_limit_m3 == SMOOTHED_VOLUME_LIMIT_M3
    assert result.constraint_residual == pytest.approx(
        result.smoothed_volume_m3 / SMOOTHED_VOLUME_LIMIT_M3 - 1.0,
        abs=1e-15,
    )
    expected_node_derivative_m2 = -np.pi * spacing_m**2 / 16.0
    assert result.gradient_m2 == pytest.approx(
        np.full((2, 2, 2), expected_node_derivative_m2),
        abs=1e-14,
    )
    assert result.constraint_gradient_per_m == pytest.approx(
        result.gradient_m2 / SMOOTHED_VOLUME_LIMIT_M3,
        abs=1e-14,
    )
    assert not result.gradient_m2.flags.writeable
    assert not result.constraint_gradient_per_m.flags.writeable


def test_solid_fluid_and_exact_interface_samples_have_frozen_limits() -> None:
    spacing_m = 0.1
    fluid = _state(np.full((2, 2, 2), 0.25, dtype=np.float32), spacing_m=spacing_m)
    interface = _state(np.zeros((2, 2, 2), dtype=np.float32), spacing_m=spacing_m)
    solid = _state(np.full((2, 2, 2), -2 * spacing_m, dtype=np.float32), spacing_m=spacing_m)

    fluid_result = smoothed_volume_and_gradient(fluid)
    interface_result = smoothed_volume_and_gradient(interface)
    solid_result = smoothed_volume_and_gradient(solid)

    assert fluid_result.smoothed_volume_m3 == 0.0
    assert interface_result.smoothed_volume_m3 == 0.0
    assert solid_result.smoothed_volume_m3 == pytest.approx(spacing_m**3, abs=1e-15)
    assert np.count_nonzero(fluid_result.gradient_m2) == 0
    assert np.count_nonzero(interface_result.gradient_m2) == 0
    assert np.count_nonzero(solid_result.gradient_m2) == 0


def test_fixed_forbidden_and_root_nodes_keep_phi_volume_but_own_no_gradient() -> None:
    spacing_m = 0.1
    phi = np.full((3, 3, 3), -spacing_m / 2, dtype=np.float32)
    fixed = np.zeros(phi.shape, dtype=np.bool_)
    forbidden = np.zeros(phi.shape, dtype=np.bool_)
    root = np.zeros(phi.shape, dtype=np.bool_)
    design = np.ones(phi.shape, dtype=np.bool_)
    fixed[0, 0, 0] = True
    forbidden[2, 2, 2] = True
    root[0, 2, 1] = True  # Root is independently protected, even outside fixed_solid.
    design[1, 1, 1] = False

    all_design_result = smoothed_volume_and_gradient(_state(phi, spacing_m=spacing_m))
    masked_state = _state(
        phi,
        spacing_m=spacing_m,
        design_mask=design,
        fixed_solid_mask=fixed,
        forbidden_mask=forbidden,
        root_mask=root,
    )
    result = smoothed_volume_and_gradient(masked_state)

    assert result.smoothed_volume_m3 == pytest.approx(
        all_design_result.smoothed_volume_m3,
        abs=0.0,
    )
    assert result.sharp_volume_m3 == pytest.approx(all_design_result.sharp_volume_m3, abs=0.0)
    for node in ((0, 0, 0), (2, 2, 2), (0, 2, 1), (1, 1, 1)):
        assert result.gradient_m2[node] == 0.0
    assert result.gradient_m2[1, 1, 2] < 0.0


def test_analytic_gradient_matches_centered_finite_difference() -> None:
    rng = np.random.default_rng(2701)
    phi = rng.uniform(-0.8, -0.2, size=(4, 4, 4)).astype(np.float32) * 0.1
    state = _state(phi, spacing_m=0.1)
    direction = rng.normal(size=phi.shape)
    direction /= np.linalg.norm(direction)
    step_m = 1.0e-3

    analytic = float(np.sum(smoothed_volume_and_gradient(state).gradient_m2 * direction))
    plus = _state(phi + step_m * direction, spacing_m=0.1)
    minus = _state(phi - step_m * direction, spacing_m=0.1)
    finite_difference = (
        smoothed_volume_and_gradient(plus).smoothed_volume_m3
        - smoothed_volume_and_gradient(minus).smoothed_volume_m3
    ) / (2.0 * step_m)

    assert finite_difference == pytest.approx(analytic, rel=3e-4, abs=2e-9)


def test_result_serialization_and_hashes_are_deterministic() -> None:
    state = _state(np.full((3, 3, 3), -0.04, dtype=np.float32))
    first = smoothed_volume_and_gradient(state)
    second = smoothed_volume_and_gradient(state)

    first_json = json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    second_json = json.dumps(second.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert first_json == second_json
    assert first.grid_sha256 == second.grid_sha256
    assert first.to_dict()["gradient_sha256"] == second.to_dict()["gradient_sha256"]
    assert first.to_dict()["sharp_reference_volume_m3"] == first.sharp_volume_m3
    assert first.to_dict()["smoothed_volume_m3"] == first.smoothed_volume_m3
    assert first.to_dict()["legacy_stage_t_vmax_carried"] is False


def test_smooth_feasibility_does_not_replace_registered_sharp_volume_gate() -> None:
    spacing_m = 0.05
    # Every center has phi=-h/2, so the one-sided cosine contributes exactly
    # one half per center, while the sharp contract counts every center as solid.
    state = _state(
        np.full((12, 12, 12), -spacing_m / 2, dtype=np.float32),
        spacing_m=spacing_m,
    )

    result = smoothed_volume_and_gradient(state)
    report = result.to_dict()

    assert result.constraint_residual < 0.0
    assert result.smoothed_volume_m3 == pytest.approx(0.5 * 11**3 * spacing_m**3)
    assert result.sharp_volume_m3 == pytest.approx(11**3 * spacing_m**3)
    assert result.sharp_volume_residual_m3 == pytest.approx(
        result.sharp_volume_m3 - SMOOTHED_VOLUME_LIMIT_M3
    )
    assert result.sharp_volume_violation_m3 == pytest.approx(
        result.sharp_volume_residual_m3
    )
    assert result.sharp_volume_violation_m3 > 0.0
    assert not result.sharp_volume_feasible
    assert report["sharp_reference_feasible"] is False
    assert report["sharp_reference_volume_violation_m3"] > 0.0


@pytest.mark.parametrize("bad_width", [0.0, -0.1, float("nan"), float("inf"), 0.2, True])
def test_transition_width_must_be_positive_and_frozen_to_one_cell(bad_width: float) -> None:
    state = _state(np.full((2, 2, 2), -0.05, dtype=np.float32))
    with pytest.raises(VolumeSemanticsError, match="transition_width_m"):
        smoothed_volume_and_gradient(state, transition_width_m=bad_width)


def test_grid_without_eight_node_cells_is_rejected() -> None:
    state = _state(np.zeros((1, 2, 2), dtype=np.float32))
    with pytest.raises(VolumeSemanticsError, match="at least two nodes"):
        smoothed_volume_and_gradient(state)
