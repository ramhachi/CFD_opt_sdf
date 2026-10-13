"""P22-v2 contract on the retained v17 states; no CFD, no registration artifact required."""
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.design import volume_semantics_v2 as V2
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import (
    SMOOTHED_VOLUME_CONTRACT_SHA256,
    VolumeSemanticsError,
    sharp_volume_m3,
    smoothed_volume_and_gradient,
)

INPUTS = Path(__file__).parents[1] / "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs"
BASELINE = SDFDesignState.load(INPUTS / "v17_baseline.npz")
PARENT = SDFDesignState.load(INPUTS / "lowdim03_parent.npz")


def test_constants_are_pinned_and_the_limit_is_derived_from_the_integer():
    assert V2.MAX_SOLID_CENTERS == 8272 and V2.VOLUME_LIMIT_M3 == 8272 * 0.025 ** 3 == 0.12925000000000003
    assert V2.CONTRACT_SHA256 == "d7ec7ba51a92acaa34a2f17f05c58d1ae4c163fd6f4ec323fb4483ed62821513"
    assert SMOOTHED_VOLUME_CONTRACT_SHA256 == "56825cd50c0916c5659badd21c84bab517ddb370085a92056d40a9028e8a7969"  # v1 is untouched


def test_baseline_and_parent_sit_exactly_at_the_integer_limit_and_fail_v1():
    for state in (BASELINE, PARENT):
        assert V2.hard_count_residual(state) == 0 and V2.hard_feasible(state)
        assert sharp_volume_m3(state) == V2.VOLUME_LIMIT_M3
        assert not smoothed_volume_and_gradient(state).sharp_volume_feasible  # v1 limit 0.126125 is exceeded: the reason for v2


def test_one_more_solid_centre_is_infeasible(monkeypatch):
    monkeypatch.setattr(V2, "MAX_SOLID_CENTERS", 8271)
    assert V2.hard_count_residual(BASELINE) == 1 and not V2.hard_feasible(BASELINE)


def test_v2_smooth_primitive_is_v1_with_the_v2_denominator():
    v1, v2 = smoothed_volume_and_gradient(PARENT), V2.smoothed_volume_and_gradient_v2(PARENT)
    assert v2.smoothed_volume_m3 == v1.smoothed_volume_m3 and np.array_equal(v2.gradient_m2, v1.gradient_m2)
    assert v2.volume_limit_m3 == V2.VOLUME_LIMIT_M3 and v2.constraint_residual == v1.smoothed_volume_m3 / V2.VOLUME_LIMIT_M3 - 1.0
    assert v2.contract_id == V2.CONTRACT_ID and v2.contract_sha256 == V2.CONTRACT_SHA256 and v2.grid_sha256 != v1.grid_sha256
    assert np.allclose(v2.constraint_gradient_per_m * V2.VOLUME_LIMIT_M3, v2.gradient_m2)
    assert v2.sharp_volume_feasible  # the same float expression as the integer limit


def test_every_other_lattice_is_refused():
    phi = np.ones((5, 5, 5), np.float32); phi[1:4, 1:4, 1:4] = -1.0
    other = SDFDesignState.create(phi=phi, origin_m=(0.0, 0.0, 0.0), spacing_m=0.1, narrow_band_width_m=0.3, design_mask=np.ones(phi.shape, bool))
    for call in (V2.hard_count_residual, V2.hard_feasible, V2.smoothed_volume_and_gradient_v2):
        with pytest.raises(VolumeSemanticsError):
            call(other)
