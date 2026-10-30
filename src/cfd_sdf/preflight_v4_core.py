"""Shared rules for the PQ3.3b preflight v4 / campaign lineage."""

from __future__ import annotations

import numpy as np


def inherit_level_start_rho(previous_level_accepted_rho: np.ndarray) -> np.ndarray:
    """Exact rho carryover between continuation levels.

    Level switches change only the transform (b/q schedule); the design array,
    masks and rho values are bitwise identical. No clip, no decay, no
    re-seeding.
    """
    rho = np.asarray(previous_level_accepted_rho, dtype=np.float64)
    carryover = rho.copy()
    if not np.array_equal(rho, carryover):
        raise ValueError("rho inheritance lost values; fail-closed")
    return carryover


def exact_rho_carryover(previous_level_accepted_rho_sha256: str, next_level_input_rho_sha256: str) -> bool:
    """Lineage verdict recorded between continuation levels."""
    return previous_level_accepted_rho_sha256 == next_level_input_rho_sha256


__all__ = ["exact_rho_carryover", "inherit_level_start_rho"]
