"""Contract tests for the canonical SDF design state."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design.sdf_state import SDFDesignState, SDFStateError

SOURCE_SHA = "ab" * 32


def _phi() -> np.ndarray:
    field = np.full((4, 5, 6), 0.1, dtype=np.float32)
    field[:, :, :2] = -0.5
    return field


def _state(**overrides) -> SDFDesignState:
    kwargs = {
        "phi": _phi(),
        "origin_m": (-0.5, -0.25, -0.15),
        "spacing_m": 0.05,
        "narrow_band_width_m": 0.15,
        "source_sha256": SOURCE_SHA,
    }
    kwargs.update(overrides)
    return SDFDesignState.create(**kwargs)


def test_state_hash_is_deterministic_and_binds_the_sign_convention():
    first = _state()
    second = _state()
    assert first.state_sha256 == second.state_sha256 == first.recompute_sha256()
    assert first == second and hash(first) == hash(second)
    assert first.solid_mask.sum() > 0 and first.fluid_mask.sum() > 0
    assert np.array_equal(first.solid_mask, first.phi < 0.0)
    assert first.to_dict()["sign_convention"] == "negative_inside"


@pytest.mark.parametrize(
    "change",
    [
        {"phi": _phi() * np.float32(1.0000001)},
        {"spacing_m": 0.0500001},
        {"generation": 1},
        {"topology_policy_id": "other_topology_policy"},
        {"reinitialization_policy_id": "other_reinit_policy"},
    ],
)
def test_state_hash_changes_with_any_registered_design_content(change):
    assert _state(**change).state_sha256 != _state().state_sha256


def test_create_converts_float64_and_defaults_masks():
    state = SDFDesignState.create(
        phi=_phi().astype(np.float64),
        origin_m=(0.0, 0.0, 0.0),
        spacing_m=0.05,
        narrow_band_width_m=0.1,
    )
    assert state.phi.dtype == np.float32
    assert state.design_mask.all() and not state.fixed_solid_mask.any()
    assert not state.forbidden_mask.any() and not state.root_mask.any()


def test_state_roundtrip_preserves_hash_and_content(tmp_path):
    state = _state(
        design_mask=np.ones((4, 5, 6), dtype=np.bool_),
        fixed_solid_mask=np.zeros((4, 5, 6), dtype=np.bool_),
    )
    path = state.save(tmp_path / "state.npz")
    loaded = SDFDesignState.load(path)
    assert loaded.state_sha256 == state.state_sha256
    assert loaded == state
    assert np.array_equal(loaded.phi, state.phi)


def test_invalid_states_fail_closed():
    state = _state()
    with pytest.raises(SDFStateError, match="spacing_m"):
        _state(spacing_m=0.0)
    with pytest.raises(SDFStateError, match="source_sha256"):
        _state(source_sha256="not-a-hash")
    with pytest.raises(SDFStateError, match="boolean ndarray"):
        SDFDesignState(**{**state.__dict__, "design_mask": np.ones((4, 5, 6), dtype=np.int8)})
    with pytest.raises(SDFStateError, match="shape"):
        SDFDesignState(**{**state.__dict__, "design_mask": np.ones((4, 5, 5), dtype=np.bool_)})
    with pytest.raises(SDFStateError, match="float32"):
        SDFDesignState(
            phi=_phi().astype(np.float64),
            origin_m=(0.0, 0.0, 0.0),
            spacing_m=0.05,
            shape=(4, 5, 6),
            design_mask=np.ones((4, 5, 6), dtype=np.bool_),
            fixed_solid_mask=np.zeros((4, 5, 6), dtype=np.bool_),
            forbidden_mask=np.zeros((4, 5, 6), dtype=np.bool_),
            root_mask=np.zeros((4, 5, 6), dtype=np.bool_),
            sign_convention="negative_inside",
            narrow_band_width_m=0.1,
            generation=0,
            source_sha256=None,
            state_sha256="0" * 64,
        )
    state = _state()
    with pytest.raises(SDFStateError, match="state_sha256"):
        SDFDesignState(**{**state.__dict__, "state_sha256": "0" * 64})
