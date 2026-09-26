"""Contract tests for the SDF-native sharp volume semantics."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import (
    VolumeSemanticsError,
    node_occupancy_volume_m3,
    sampled_solid_centers_count,
    sharp_volume_m3,
    volume_limit_violation_m3,
    volume_semantics_report,
)


def _state(phi: np.ndarray, spacing: float = 0.05) -> SDFDesignState:
    return SDFDesignState.create(
        phi=phi,
        origin_m=(-1.0, -0.8, -0.6),
        spacing_m=spacing,
        narrow_band_width_m=spacing,
    )


def _solid_slab(shape=(5, 5, 5), solid_layers=2) -> np.ndarray:
    phi = np.full(shape, 0.1, dtype=np.float32)
    phi[:, :, :solid_layers] = -0.4
    return phi


def test_sampled_sharp_volume_counts_center_samples():
    phi = _solid_slab(solid_layers=3)
    state = _state(phi, spacing=0.1)
    # corner mean of all-negative corner sets: cells whose 8 nodes are all
    # negative plus the magnitude-weighted boundary band produced by the
    # registered corner-mean rule
    expected_count = int(
        (
            phi[:-1, :-1, :-1]
            + phi[1:, :-1, :-1]
            + phi[:-1, 1:, :-1]
            + phi[:-1, :-1, 1:]
            + phi[1:, 1:, :-1]
            + phi[1:, :-1, 1:]
            + phi[:-1, 1:, 1:]
            + phi[1:, 1:, 1:]
        ).__truediv__(8.0)
        .__lt__(0)
        .sum()
    )
    assert sampled_solid_centers_count(state) == expected_count
    assert sharp_volume_m3(state) == pytest.approx(expected_count * 0.1**3, abs=1e-15)


def test_contract_measure_differs_from_node_occupancy_diagnostic():
    phi = _solid_slab(solid_layers=2, shape=(6, 6, 6))
    phi[:, :, 1] = 0.6  # a magnitude-weighted boundary layer flips its cubes
    state = _state(phi, spacing=0.1)
    assert node_occupancy_volume_m3(state) > sharp_volume_m3(state)
    assert node_occupancy_volume_m3(state) == pytest.approx(
        int((phi < 0).sum()) * 0.1**3, abs=1e-15
    )


def test_volume_limit_violation_boundary():
    phi = _solid_slab(solid_layers=3)
    state = _state(phi, spacing=0.05)
    volume = sharp_volume_m3(state)
    assert volume_limit_violation_m3(state, volume) == 0.0
    assert volume_limit_violation_m3(state, volume + 1e-9) == 0.0
    assert volume_limit_violation_m3(state, volume - 1e-9) == pytest.approx(1e-9)


def test_volume_limit_fails_closed_on_invalid_limit():
    state = _state(_solid_slab())
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(VolumeSemanticsError, match="volume_limit_m3"):
            volume_limit_violation_m3(state, bad)


def test_report_binds_state_identity_and_feasibility():
    phi = _solid_slab(solid_layers=3)
    state = _state(phi, spacing=0.1)
    volume = sharp_volume_m3(state)
    report = volume_semantics_report(state, volume_limit_m3=volume)
    assert report["feasible"] is True
    assert report["volume_violation_m3"] == 0.0
    assert report["sampled_solid_centers"] == sampled_solid_centers_count(state)
    assert report["node_occupancy_diagnostic"]["solid_nodes"] == int((phi < 0).sum())
    assert report["state_sha256"] == state.state_sha256
    assert report["state_phi_sha256"] == state.phi_sha256()
    assert "not a differentiable constraint" in report["claims_not_supported"][0]


def test_report_flags_infeasible_state():
    state = _state(_solid_slab(solid_layers=3), spacing=0.1)
    volume = sharp_volume_m3(state)
    report = volume_semantics_report(state, volume_limit_m3=volume * 0.5)
    assert report["feasible"] is False
    assert report["volume_violation_m3"] == pytest.approx(volume * 0.5)


def test_zero_solid_state_has_zero_volume():
    phi = np.full((3, 3, 3), 0.5, dtype=np.float32)
    state = _state(phi, spacing=0.1)
    assert sampled_solid_centers_count(state) == 0
    assert sharp_volume_m3(state) == 0.0
    assert node_occupancy_volume_m3(state) == 0.0
