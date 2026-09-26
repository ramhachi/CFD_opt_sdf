"""Canonical sharp-SDF volume semantics for the SDF-native line.

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
      V_phi = N_center(phi) h ,
                                          3
  where ``N_center(phi) = | {c : phi~(c) < 0} |`` counts the h-cubes whose
  representative value is the trilinear mean of the eight surrounding
  state nodes and ``h`` is the state spacing.  This is the h->0 limit of
  the user-registered differentiable volume
  ``V_eps = integral H_eps(-phi) dOmega`` under the center sampling; the
  smoothed implementation itself is deferred until the one-step gate.

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

from typing import Any

import numpy as np

from .sdf_state import SDFDesignState

VOLUME_SEMANTICS_KIND = "sdf_native_volume_semantics"
VOLUME_SEMANTICS_SCHEMA_VERSION = 1


class VolumeSemanticsError(ValueError):
    """Fail-closed SDF volume-semantics contract violation."""


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
    """Contract volume ``V_phi`` under the registered center-sampling rule."""

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
            "(the sharp limit of integral H_eps(-phi) under center sampling)"
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
            "voxel-equivalent volume is not a differentiable constraint until its H_eps gradient contract is registered",
            "no sub-voxel geometry sensitivity; any sub-voxel volume change between states with equal sampled-center counts is invisible",
        ],
    }


__all__ = [
    "VOLUME_SEMANTICS_KIND",
    "VOLUME_SEMANTICS_SCHEMA_VERSION",
    "VolumeSemanticsError",
    "node_occupancy_volume_m3",
    "sampled_solid_centers_count",
    "sharp_volume_m3",
    "volume_limit_violation_m3",
    "volume_semantics_report",
]
