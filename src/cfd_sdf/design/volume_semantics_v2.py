"""P22-v2 (#55): representation-specific discrete volume contract on the registered v17 design lattice.

The v1 primitive (one sample per h-cube centre, one-sided cosine step, epsilon = h, gradient ownership) is reused
unchanged; only the reference and the constraint denominator change, and every other lattice is refused. The
primary constraint is the integer ``N_phi <= MAX_SOLID_CENTERS``; ``VOLUME_LIMIT_M3`` is derived and never the
acceptance quantity. This is a lattice-specific discrete constraint, not a physical or continuum volume constraint.
v1 code and its registration are untouched.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

import numpy as np

from .sdf_state import SDFDesignState
from .volume_semantics import (
    SMOOTHED_VOLUME_CONTRACT_SHA256 as V1_CONTRACT_SHA256,
    SmoothedVolumeResult,
    VolumeSemanticsError,
    _canonical_json_bytes,
    _validate_state,
    sampled_solid_centers_count,
    smoothed_volume_and_gradient,
)

REGISTRATION_ID = "sdf_native_volume_semantics_v2_2026_10"
CONTRACT_ID = "sdf_native_smoothed_volume_v2"
SCHEMA_VERSION = 2
SPACING_M = 0.025
ORIGIN_M = (-1.0, -0.8, -0.6)
NODE_SHAPE = (121, 65, 49)
MAX_SOLID_CENTERS = 8272
VOLUME_LIMIT_M3 = MAX_SOLID_CENTERS * SPACING_M**3  # derived value only; same expression as sharp_volume_m3
REFERENCE_STATE_SHA256 = "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"
REFERENCE_NPZ_SHA256 = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"

_CONTRACT_PAYLOAD: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "kind": CONTRACT_ID,
    "registration_id": REGISTRATION_ID,
    "scope": (
        "representation-specific discrete constraint on the registered v17 design lattice; "
        "not a physical or continuum volume constraint; N <= N_max is not equivalent to V <= 0.12925 m^3 physical"
    ),
    "primitive": "identical to sdf_native_smoothed_volume_v1 (heaviside, epsilon = h, gradient and ownership)",
    "v1_contract_sha256": V1_CONTRACT_SHA256,
    "lattice": {"origin_m": list(ORIGIN_M), "spacing_m": SPACING_M, "node_shape": list(NODE_SHAPE)},
    "sampled_solid_centers_max": MAX_SOLID_CENTERS,
    "volume_limit_m3_derived": VOLUME_LIMIT_M3,
    "reference": {"state_sha256": REFERENCE_STATE_SHA256, "npz_sha256": REFERENCE_NPZ_SHA256},
    "constraint": (
        "g_V = V_eps / volume_limit_m3_derived - 1; at N_phi = N_max this is about -0.31 (V_eps/V_sharp is about 0.69), "
        "so g_V <= 0 is inactive at the hard boundary and cannot signal the active hard constraint"
    ),
    "sub_voxel_sensitivity": (
        "none for the hard count: states with equal N_phi may differ materially in smoothed or physical volume "
        "(the recorded +-1.25 mm D0 states keep N_phi and change V_eps by about +-2.8%)"
    ),
    "acceptance_rule": (
        "sampled_solid_centers_count(state) <= sampled_solid_centers_max, an integer comparison; "
        "the smooth value never substitutes for it"
    ),
}
CONTRACT_SHA256 = hashlib.sha256(_canonical_json_bytes(_CONTRACT_PAYLOAD)).hexdigest()


def _require_registered_lattice(state: SDFDesignState) -> None:
    _validate_state(state)
    if (
        tuple(int(v) for v in state.shape) != NODE_SHAPE
        or tuple(float(v) for v in state.origin_m) != ORIGIN_M
        or float(state.spacing_m) != SPACING_M
    ):
        raise VolumeSemanticsError("P22-v2 is defined only on the registered v17 design lattice")


def hard_count_residual(state: SDFDesignState) -> int:
    """Signed integer margin ``N_phi - N_max``; feasible when <= 0."""

    _require_registered_lattice(state)
    return sampled_solid_centers_count(state) - MAX_SOLID_CENTERS


def hard_feasible(state: SDFDesignState) -> bool:
    return hard_count_residual(state) <= 0


def smoothed_volume_and_gradient_v2(state: SDFDesignState) -> SmoothedVolumeResult:
    """The v1 smooth value and gradient with the constraint bound to the v2 derived limit."""

    _require_registered_lattice(state)
    base = smoothed_volume_and_gradient(state)
    grid_payload = {
        "contract_id": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "shape": [int(v) for v in state.shape],
        "origin_m": [float(v) for v in state.origin_m],
        "spacing_m": float(state.spacing_m),
        "transition_width_m": base.transition_width_m,
    }
    return dataclasses.replace(
        base,
        volume_limit_m3=VOLUME_LIMIT_M3,
        constraint_residual=float(base.smoothed_volume_m3 / VOLUME_LIMIT_M3 - 1.0),
        grid_sha256=hashlib.sha256(_canonical_json_bytes(grid_payload)).hexdigest(),
        contract_id=CONTRACT_ID,
        contract_sha256=CONTRACT_SHA256,
    )


def report_v2(state: SDFDesignState) -> dict[str, Any]:
    """Reporting dict that carries the contract scope; the v1 ``to_dict`` layout is not reused for v2."""

    result = smoothed_volume_and_gradient_v2(state)
    n = sampled_solid_centers_count(state)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_ID,
        "contract_sha256": CONTRACT_SHA256,
        "scope": _CONTRACT_PAYLOAD["scope"],
        "sampled_solid_centers": n,
        "sampled_solid_centers_max": MAX_SOLID_CENTERS,
        "hard_count_residual": n - MAX_SOLID_CENTERS,
        "hard_feasible": n <= MAX_SOLID_CENTERS,
        "volume_limit_m3_derived": VOLUME_LIMIT_M3,
        "limit_kind": "derived from the integer count; lattice-specific; not a physical volume",
        "smoothed_volume_m3": result.smoothed_volume_m3,
        "constraint_residual": result.constraint_residual,
        "constraint_residual_note": _CONTRACT_PAYLOAD["constraint"],
        "gradient_sha256": result.to_dict()["gradient_sha256"],
    }


__all__ = [
    "REGISTRATION_ID",
    "CONTRACT_ID",
    "CONTRACT_SHA256",
    "MAX_SOLID_CENTERS",
    "VOLUME_LIMIT_M3",
    "hard_count_residual",
    "hard_feasible",
    "report_v2",
    "smoothed_volume_and_gradient_v2",
]
