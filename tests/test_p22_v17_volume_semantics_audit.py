"""Portable reference identity and sampling tests for the solver-free bridge."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_p22_v17_volume_semantics as A
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design import volume_semantics as V


def test_original_reference_exact_replay_and_registered_identity():
    state = A.load_checked("v16_reference", A.E / "inputs/v16_reference.npz")
    assert V.sampled_solid_centers_count(state) == 1009
    assert V.sharp_volume_m3(state) == 0.12612500000000004
    assert state.phi_sha256() == "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"


def test_float32_center_arithmetic_is_not_float64_or_node_occupancy():
    # Exact real/Float64 mean is -1/8; registered left-to-right Float32
    # accumulation rounds 2**25 - 1 to 2**25, so its center is exact zero.
    phi = np.zeros((2, 2, 2), dtype=np.float32)
    phi[0, 0, 0], phi[1, 0, 0], phi[0, 1, 0] = 2**25, -1, -(2**25)
    state = SDFDesignState.create(phi=phi, spacing_m=0.05, origin_m=(0, 0, 0), narrow_band_width_m=0.1)
    assert phi.astype(np.float64).mean() == -0.125
    assert V._corner_mean(phi).dtype == np.float32
    assert V._corner_mean(phi).item() == 0
    assert V.sharp_volume_m3(state) == 0
    assert V.node_occupancy_volume_m3(state) > 0


def test_exact_zero_center_is_fluid_and_smooth_gradient_zero():
    phi = np.ones((2, 2, 2), dtype=np.float32)
    phi[0] = -1
    state = SDFDesignState.create(phi=phi, spacing_m=0.05, origin_m=(0, 0, 0), narrow_band_width_m=0.1)
    result = V.smoothed_volume_and_gradient(state)
    assert V.sampled_solid_centers_count(state) == 0
    assert result.sharp_volume_m3 == result.smoothed_volume_m3 == 0
    assert np.count_nonzero(result.gradient_m2) == 0


@pytest.mark.parametrize("label,other", [("v16_reference", "v17_baseline"), ("v17_baseline", "v16_reference"), ("lowdim03_parent", "v17_baseline")])
def test_distinct_registered_inputs_cannot_be_swapped(label, other):
    with pytest.raises(ValueError, match="NPZ identity mismatch"):
        A.load_checked(label, A.E / "inputs" / f"{other}.npz")


@pytest.mark.parametrize("label,grid_sha,shape,h", [
    ("v16_reference", "242d499b462eb76bb72bc0e5dc87f6731e95e417298f915ac33f19097a1de4c0", (61, 33, 25), 0.05),
    ("v17_baseline", "645bc1c756ce833fd4c741b82b3932e36adc1c2f4fa762bb3c59317ed809b9b5", (121, 65, 49), 0.025),
    ("lowdim03_parent", "645bc1c756ce833fd4c741b82b3932e36adc1c2f4fa762bb3c59317ed809b9b5", (121, 65, 49), 0.025),
])
def test_frozen_state_and_grid_hashes(label, grid_sha, shape, h):
    state = A.load_checked(label, A.E / "inputs" / f"{label}.npz")
    assert state.shape == shape and state.spacing_m == h
    assert state.origin_m == (-1.0, -0.8, -0.6)
    assert V.smoothed_volume_and_gradient(state).grid_sha256 == grid_sha


def test_reconstruction_and_frozen_comparison_replay():
    assert A.canonical(A.replay()) == (A.E / "volume_semantics_comparison.json").read_bytes()
