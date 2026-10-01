from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design.sdf_reinitialization import (
    SDFReinitializationError,
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


@pytest.mark.parametrize("value", [-1.0, 0.0, 1.0])
def test_reinit_rejects_empty_or_uniform_sign_domains(value):
    phi = np.full((7, 7, 7), value, dtype=np.float32)
    with pytest.raises(SDFReinitializationError, match="no solid/non-solid interface"):
        _reinit_phi(phi, 0.1)
