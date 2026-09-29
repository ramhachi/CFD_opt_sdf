"""Canonical sharp and differentiable SDF volume semantics.

Plan correction v2.1 (2026-09-26, registered) separates two volume
quantities that the legacy Stage T/Stage S path kept implicitly mixed:

- **Stage T density volume** ``V_rho``: the projected-volume integral over
  the design cells that Stage T constrained (v16: `V_rho = 0.0719735015`
  at limit `Vmax = 0.0763256681`).  It remains a Stage T diagnostic and a
  Stage S entry fidelity observable.  It is **not** the SDF-native
  constraint volume, and the legacy `Vmax` must not be carried into SDF
  Stage S evaluation.
- **SDF sharp volume** ``V_phi``: the voxel-equivalent sharp volume of the
  canonical SDF state, evaluated by the registered center-sampling rule
                                             3
      V_phi = N_center(phi) * h   ,
                                          3
  where ``N_center(phi) = | {c : phi~(c) < 0} |`` counts the h-cubes whose
  representative value is the trilinear mean of the eight surrounding
  state nodes and ``h`` is the state spacing.  At fixed grid spacing this
  is the ``epsilon -> 0`` limit of the differentiable volume
          V_eps = integral H_eps(-phi, eps) dOmega
  under the center sampling, i.e. the sharp midpoint occupancy rule on
  the discrete grid.  The separate continuum limit ``h -> 0`` of that
  discrete rule is what would converge toward the geometric solid volume
  of the sharp set; the two limits are distinct and only the discrete
  rule is registered.  The optimizer-side primitive below is a separate,
  versioned one-sided cosine regularization of the same cell-center samples.
  It does not change the sharp report or qualify a constrained shape update.

The first SDF volume constraint is `V_phi <= V_phi_0` with `V_phi_0`
re-measured on the registered baseline state (v16 genesis: 1009 sampled
solids, `V_phi_0 = 0.12612500000000004 m^3`), recorded in
`docs/evidence/sdf_native_volume_semantics_v1_2026_09.json` together with
the cross-checking physical measures:

- the handoff's revoxelized/mesh cell material (`1034` cells,
  `0.12925000000000003 m^3`, mesh volume error ~1e-8): a boundary-cell
  discretization difference between the mesh-exact sampling and the
  state-trilinear sampling, recorded but not the contract measure;
- the node-occupancy count (`1420` nodes, `0.1775 m^3`), a
  non-contracted diagnostic that each `phi < 0` node claims one voxel.

All three measures are recorded so no later reader can confuse them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from .sdf_state import SDFDesignState

VOLUME_SEMANTICS_KIND = "sdf_native_volume_semantics"
VOLUME_SEMANTICS_SCHEMA_VERSION = 1

SMOOTHED_VOLUME_CONTRACT_ID = "sdf_native_smoothed_volume_v1"
SMOOTHED_VOLUME_SCHEMA_VERSION = 1
SMOOTHED_VOLUME_LIMIT_M3 = 0.12612500000000004
SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID = "sdf_native_volume_semantics_v1_2026_09"
SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256 = (
    "0142ace4de9419dd73cc27e90135ed1fe1f847b074ca2faa37fdb0962505bbce"
)

_SMOOTHED_VOLUME_CONTRACT_PAYLOAD: dict[str, Any] = {
    "schema_version": SMOOTHED_VOLUME_SCHEMA_VERSION,
    "kind": SMOOTHED_VOLUME_CONTRACT_ID,
    "volume_limit_m3": SMOOTHED_VOLUME_LIMIT_M3,
    "volume_limit_source": {
        "registration_id": SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID,
        "sha256": SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256,
        "sampled_solid_centers": 1009,
    },
    "grid_sampling": (
        "one sample for every h-cube; the sample is the existing float32 "
        "arithmetic mean of the eight canonical SDF state nodes at the cube center"
    ),
    "cell_volume": "state.spacing_m ** 3, in m^3",
    "sign_convention": "phi < 0 is solid; phi = 0 is fluid",
    "heaviside": {
        "id": "one_sided_cosine_negative_inside_v1",
        "argument": "s = -center_phi, in m",
        "transition_width_cells": 1.0,
        "definition": (
            "H(s)=0 for s<=0; H(s)=(1-cos(pi*s/epsilon))/2 for 0<s<epsilon; "
            "H(s)=1 for s>=epsilon; epsilon=state.spacing_m"
        ),
        "sharp_limit": "pointwise H_eps(-center_phi) -> 1[center_phi < 0] as epsilon -> 0",
    },
    "smoothed_volume": "V_eps = sum_h-cubes H_eps(-center_phi) * h^3",
    "constraint": "g_V = V_eps / volume_limit_m3 - 1",
    "gradient": (
        "dV/dphi_node is the sum of -h^3 * H_prime(-center_phi) / 8 "
        "over adjacent h-cubes"
    ),
    "gradient_ownership": (
        "retain derivatives only where design_mask is true and fixed_solid_mask, "
        "forbidden_mask, and root_mask are all false; root ownership is independent "
        "of fixed_solid_mask and masks do not filter volume samples"
    ),
    "gradient_units": "dV/dphi in m^2; dg_V/dphi in m^-1",
    "result_identity": (
        "static contract SHA-256 over canonical sorted compact JSON; grid SHA-256 "
        "binds contract, shape, origin, spacing, and transition width; state_sha256 "
        "binds the field, masks, and policies"
    ),
    "result_serialization": (
        "JSON-compatible scalar metadata; gradient arrays are represented by "
        "little-endian float64 SHA-256 hashes"
    ),
    "acceptance_rule": (
        "the one-sided finite-epsilon value is not a conservative sharp-volume bound; "
        "sharp_volume_m3 <= volume_limit_m3 must be checked separately before acceptance"
    ),
    "legacy_stage_t_vmax_carried": False,
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


SMOOTHED_VOLUME_CONTRACT_SHA256 = hashlib.sha256(
    _canonical_json_bytes(_SMOOTHED_VOLUME_CONTRACT_PAYLOAD)
).hexdigest()


class VolumeSemanticsError(ValueError):
    """Fail-closed SDF volume-semantics contract violation."""


@dataclass(frozen=True, eq=False)
class SmoothedVolumeResult:
    """Smoothed constraint values, masked derivative, and deterministic identity.

    ``gradient_m2`` is ``dV_eps/dphi`` after design-mask ownership is applied.
    ``constraint_gradient_per_m`` is its derivative after dividing by the
    registered sharp-reference volume. ``sharp_volume_m3`` is reported as a
    separate diagnostic and is not substituted into the smooth residual.
    """

    smoothed_volume_m3: float
    sharp_volume_m3: float
    volume_limit_m3: float
    constraint_residual: float
    gradient_m2: np.ndarray
    transition_width_m: float
    state_sha256: str
    grid_sha256: str
    contract_id: str = SMOOTHED_VOLUME_CONTRACT_ID
    contract_sha256: str = SMOOTHED_VOLUME_CONTRACT_SHA256

    @property
    def sharp_volume_residual_m3(self) -> float:
        """Signed exact-measure margin ``V_phi - V_phi_0`` in cubic metres."""

        return self.sharp_volume_m3 - self.volume_limit_m3

    @property
    def sharp_volume_violation_m3(self) -> float:
        return max(0.0, self.sharp_volume_residual_m3)

    @property
    def sharp_volume_feasible(self) -> bool:
        return self.sharp_volume_m3 <= self.volume_limit_m3

    @property
    def constraint_gradient_per_m(self) -> np.ndarray:
        gradient = np.ascontiguousarray(
            self.gradient_m2 / self.volume_limit_m3,
            dtype="<f8",
        )
        gradient.setflags(write=False)
        return gradient

    def to_dict(self) -> dict[str, Any]:
        """Return stable JSON-compatible reporting metadata, not array payloads."""

        return {
            "schema_version": SMOOTHED_VOLUME_SCHEMA_VERSION,
            "kind": self.contract_id,
            "contract_sha256": self.contract_sha256,
            "grid_sha256": self.grid_sha256,
            "state_sha256": self.state_sha256,
            "transition_width_m": self.transition_width_m,
            "smoothed_volume_m3": self.smoothed_volume_m3,
            "sharp_reference_volume_m3": self.sharp_volume_m3,
            "sharp_reference_volume_residual_m3": self.sharp_volume_residual_m3,
            "sharp_reference_volume_violation_m3": self.sharp_volume_violation_m3,
            "sharp_reference_feasible": self.sharp_volume_feasible,
            "volume_limit_m3": self.volume_limit_m3,
            "constraint_residual": self.constraint_residual,
            "gradient_units": "m^2",
            "gradient_sha256": _float64_array_sha256(self.gradient_m2),
            "constraint_gradient_units": "m^-1",
            "constraint_gradient_sha256": _float64_array_sha256(
                self.constraint_gradient_per_m
            ),
            "legacy_stage_t_vmax_carried": False,
        }


def _float64_array_sha256(array: np.ndarray) -> str:
    canonical = np.ascontiguousarray(np.asarray(array, dtype="<f8"))
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def _validate_state(state: SDFDesignState) -> None:
    if not isinstance(state, SDFDesignState):
        raise VolumeSemanticsError("state must be an SDFDesignState")
    if not (np.isfinite(state.spacing_m) and state.spacing_m > 0.0):
        raise VolumeSemanticsError("state spacing must be finite and positive")


def _corner_mean(phi: np.ndarray) -> np.ndarray:
    """Trilinear value of ``phi`` at the centre of every h-cube."""

    return (
        phi[:-1, :-1, :-1]
        + phi[1:, :-1, :-1]
        + phi[:-1, 1:, :-1]
        + phi[:-1, :-1, 1:]
        + phi[1:, 1:, :-1]
        + phi[1:, :-1, 1:]
        + phi[:-1, 1:, 1:]
        + phi[1:, 1:, 1:]
    ) * np.float32(0.125)


def sampled_solid_centers_count(state: SDFDesignState) -> int:
    """Number of h-cubes whose trilinear centre sample is inside (phi<0)."""

    _validate_state(state)
    return int((_corner_mean(state.phi) < 0.0).sum())


def sharp_volume_m3(state: SDFDesignState) -> float:
    """Contract volume ``V_phi`` under the registered center-sampling rule.

    At fixed spacing this equals the ``epsilon -> 0`` occupancy limit of
    ``V_eps = integral H_eps(-phi)`` under center sampling (the discrete
    midpoint rule); continuum ``h -> 0`` convergence is a separate,
    unclaimed limit.
    """

    _validate_state(state)
    return float(sampled_solid_centers_count(state) * float(state.spacing_m) ** 3)


def node_occupancy_volume_m3(state: SDFDesignState) -> float:
    """Diagnostic volume: every ``phi < 0`` node claims one ``h^3`` voxel.

    Not the contract measure; recorded so the two samplings are never
    confused.
    """

    _validate_state(state)
    return float(int(state.solid_mask.sum()) * float(state.spacing_m) ** 3)


def volume_limit_violation_m3(state: SDFDesignState, volume_limit_m3: float) -> float:
    """Signed over-volume of `V_phi` above the registered limit (0 when feasible)."""

    _validate_state(state)
    if volume_limit_m3 is None or not np.isfinite(volume_limit_m3) or volume_limit_m3 <= 0.0:
        raise VolumeSemanticsError("volume_limit_m3 must be finite and positive")
    return float(max(0.0, sharp_volume_m3(state) - float(volume_limit_m3)))


def volume_semantics_report(state: SDFDesignState, *, volume_limit_m3: float) -> dict[str, Any]:
    """Build the fail-closed volume contract record for one state."""

    _validate_state(state)
    if volume_limit_m3 is None or not np.isfinite(volume_limit_m3) or volume_limit_m3 <= 0.0:
        raise VolumeSemanticsError("volume_limit_m3 must be finite and positive")
    volume = sharp_volume_m3(state)
    centers = sampled_solid_centers_count(state)
    violation = volume_limit_violation_m3(state, float(volume_limit_m3))
    return {
        "schema_version": VOLUME_SEMANTICS_SCHEMA_VERSION,
        "kind": VOLUME_SEMANTICS_KIND,
        "state_sha256": state.state_sha256,
        "state_phi_sha256": state.phi_sha256(),
        "volume_definition": (
            "V_phi = |{h-cubes with trilinear centre sample < 0}| * h^3 "
            "(the epsilon->0 occupancy limit of integral H_eps(-phi) under center sampling)"
        ),
        "state_spacing_m": float(state.spacing_m),
        "sampled_solid_centers": centers,
        "volume_m3": volume,
        "node_occupancy_diagnostic": {
            "solid_nodes": int(state.solid_mask.sum()),
            "volume_m3": node_occupancy_volume_m3(state),
            "role": "non-contracted diagnostic; never compare against V_phi limits",
        },
        "volume_limit_m3": float(volume_limit_m3),
        "volume_violation_m3": violation,
        "feasible": volume <= float(volume_limit_m3),
        "claims_not_supported": [
            "sharp center-count V_phi is not differentiable; optimizer constraints use a separate H_eps contract",
            "no sub-voxel geometry sensitivity; any sub-voxel volume change between states with equal sampled-center counts is invisible",
        ],
    }


def smoothed_volume_and_gradient(
    state: SDFDesignState,
    *,
    transition_width_m: float | None = None,
) -> SmoothedVolumeResult:
    """Evaluate the frozen v1 smooth volume and its analytic node derivative.

    Samples are the same eight-node center means used by :func:`sharp_volume_m3`.
    The one-sided cosine step transitions from fluid at ``center_phi >= 0`` to
    solid at ``center_phi <= -h``; this preserves the registered strict
    ``center_phi < 0`` sharp limit, including exact-zero centers. All cell
    samples contribute to volume. Derivatives are retained only on designable
    nodes, with fixed, forbidden, and root-owned nodes held constant.

    The optional width is accepted only when it exactly equals the state grid
    spacing. It allows callers to assert the registered width explicitly
    without allowing an alternate smoothing profile to enter v1.
    """

    _validate_state(state)
    if any(size < 2 for size in state.shape):
        raise VolumeSemanticsError(
            "volume grid must have at least two nodes along every axis"
        )
    spacing_m = float(state.spacing_m)
    if transition_width_m is None:
        epsilon_m = spacing_m
    else:
        if isinstance(transition_width_m, (bool, np.bool_)):
            raise VolumeSemanticsError(
                "transition_width_m must equal the registered grid spacing"
            )
        try:
            epsilon_m = float(transition_width_m)
        except (TypeError, ValueError) as error:
            raise VolumeSemanticsError(
                "transition_width_m must be finite and equal the registered grid spacing"
            ) from error
        if not np.isfinite(epsilon_m) or epsilon_m <= 0.0:
            raise VolumeSemanticsError(
                "transition_width_m must be finite and positive"
            )
        if epsilon_m != spacing_m:
            raise VolumeSemanticsError(
                "transition_width_m is frozen at exactly one state grid spacing"
            )

    cell_volume_m3 = spacing_m * spacing_m * spacing_m
    if not np.isfinite(cell_volume_m3) or cell_volume_m3 <= 0.0:
        raise VolumeSemanticsError(
            "state grid spacing does not define a finite positive cell volume"
        )

    center_phi = _corner_mean(state.phi).astype(np.float64)
    inside_distance_m = -center_phi
    transition = (inside_distance_m > 0.0) & (inside_distance_m < epsilon_m)
    solid = inside_distance_m >= epsilon_m

    heaviside = np.zeros(center_phi.shape, dtype=np.float64)
    heaviside[solid] = 1.0
    phase = np.pi * inside_distance_m[transition] / epsilon_m
    heaviside[transition] = 0.5 * (1.0 - np.cos(phase))

    heaviside_derivative_per_m = np.zeros(center_phi.shape, dtype=np.float64)
    heaviside_derivative_per_m[transition] = (
        0.5 * np.pi / epsilon_m * np.sin(phase)
    )

    smoothed_volume_m3 = float(np.sum(heaviside, dtype=np.float64) * cell_volume_m3)
    # d/dphi_node = d/dcenter_phi * 1/8; dH/dcenter_phi = -dH/ds.
    center_node_derivative_m2 = -cell_volume_m3 * heaviside_derivative_per_m / 8.0
    gradient_m2 = np.zeros(state.shape, dtype=np.float64)
    gradient_m2[:-1, :-1, :-1] += center_node_derivative_m2
    gradient_m2[1:, :-1, :-1] += center_node_derivative_m2
    gradient_m2[:-1, 1:, :-1] += center_node_derivative_m2
    gradient_m2[:-1, :-1, 1:] += center_node_derivative_m2
    gradient_m2[1:, 1:, :-1] += center_node_derivative_m2
    gradient_m2[1:, :-1, 1:] += center_node_derivative_m2
    gradient_m2[:-1, 1:, 1:] += center_node_derivative_m2
    gradient_m2[1:, 1:, 1:] += center_node_derivative_m2

    designable = (
        state.design_mask
        & ~state.fixed_solid_mask
        & ~state.forbidden_mask
        & ~state.root_mask
    )
    gradient_m2[~designable] = 0.0
    gradient_m2 = np.ascontiguousarray(gradient_m2, dtype="<f8")
    gradient_m2.setflags(write=False)

    volume_limit_m3 = SMOOTHED_VOLUME_LIMIT_M3
    constraint_residual = smoothed_volume_m3 / volume_limit_m3 - 1.0
    sharp_volume = sharp_volume_m3(state)
    grid_payload = {
        "contract_id": SMOOTHED_VOLUME_CONTRACT_ID,
        "contract_sha256": SMOOTHED_VOLUME_CONTRACT_SHA256,
        "shape": [int(value) for value in state.shape],
        "origin_m": [float(value) for value in state.origin_m],
        "spacing_m": spacing_m,
        "transition_width_m": epsilon_m,
    }
    grid_sha256 = hashlib.sha256(_canonical_json_bytes(grid_payload)).hexdigest()
    return SmoothedVolumeResult(
        smoothed_volume_m3=smoothed_volume_m3,
        sharp_volume_m3=sharp_volume,
        volume_limit_m3=volume_limit_m3,
        constraint_residual=float(constraint_residual),
        gradient_m2=gradient_m2,
        transition_width_m=epsilon_m,
        state_sha256=state.state_sha256,
        grid_sha256=grid_sha256,
    )


__all__ = [
    "VOLUME_SEMANTICS_KIND",
    "VOLUME_SEMANTICS_SCHEMA_VERSION",
    "SMOOTHED_VOLUME_CONTRACT_ID",
    "SMOOTHED_VOLUME_SCHEMA_VERSION",
    "SMOOTHED_VOLUME_LIMIT_M3",
    "SMOOTHED_VOLUME_LIMIT_SOURCE_REGISTRATION_ID",
    "SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256",
    "SMOOTHED_VOLUME_CONTRACT_SHA256",
    "VolumeSemanticsError",
    "SmoothedVolumeResult",
    "node_occupancy_volume_m3",
    "sampled_solid_centers_count",
    "sharp_volume_m3",
    "volume_limit_violation_m3",
    "volume_semantics_report",
    "smoothed_volume_and_gradient",
]
