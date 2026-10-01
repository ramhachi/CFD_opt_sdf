from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design.sdf_reinitialization import (
    SDFReinitializationError,
    _eikonal_stats,
    _reinit_phi,
)


def test_godunov_reinit_preserves_exact_zero_and_far_band():
    h = 0.1
    axis = (np.arange(15, dtype=np.float32) - 7) * h
    phi = np.broadcast_to(axis[:, None, None], (15, 15, 15)).copy()

    output, iterations = _reinit_phi(phi, h)

    assert iterations > 0
    assert np.array_equal(output[phi == 0.0], phi[phi == 0.0])
    far = np.abs(phi) > 3 * h
    assert np.array_equal(output[far], phi[far])
    assert np.array_equal(output < 0, phi < 0)
    assert np.isfinite(output).all()


def test_eikonal_report_uses_fixed_input_band_and_sign_labels():
    h = 0.1
    axis = (np.arange(15, dtype=np.float32) - 7) * h
    before = np.broadcast_to(axis[:, None, None], (15, 15, 15)).copy()
    input_solid = before < 0
    evaluation_band = np.zeros(before.shape, dtype=bool)
    evaluation_band[1:-1, 1:-1, 1:-1] = True
    evaluation_band &= np.abs(before) <= 3 * h

    after = before.copy()
    after[7, 7, 7] = 10 * h  # leaves the input band; must remain in fixed sample
    before_stats = _eikonal_stats(before, h, evaluation_band, input_solid)
    after_stats = _eikonal_stats(after, h, evaluation_band, input_solid)

    assert before_stats["fluid"]["count"] == after_stats["fluid"]["count"]
    assert before_stats["solid"]["count"] == after_stats["solid"]["count"]
    assert before_stats["fluid"]["count"] + before_stats["solid"]["count"] == int(evaluation_band.sum())


@pytest.mark.parametrize("value", [-1.0, 0.0, 1.0])
def test_reinit_rejects_empty_or_uniform_sign_domains(value):
    phi = np.full((7, 7, 7), value, dtype=np.float32)
    with pytest.raises(SDFReinitializationError, match="no solid/non-solid interface"):
        _reinit_phi(phi, 0.1)
