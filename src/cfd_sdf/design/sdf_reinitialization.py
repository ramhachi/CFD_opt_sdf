"""Explicit SDF reinitialization operator (SDF-02, contract v1).

Contract constants are registered before any numerical evidence exists; see
``docs/sdf_native_reinitialization_contract_v1_2026_09.md``.  The operator
itself is added below the contract block.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

REINIT_CONTRACT_ID = "sdf_native_reinitialization_v1"
REINIT_SCHEMA_VERSION = 1

# All tolerances are frozen here, before any evidence run, and are part of
# the contract hash.  They are never call arguments.
BAND_HALF_WIDTH_CELLS = 3.0
SIGN_FLOOR_FRACTION_OF_H = 1e-9
DEGENERATE_EDGE_SUM_M = 1e-7
TOLERANCES: dict[str, float] = {
    # | |grad phi| - 1 | on band nodes, central differences, full-stencil nodes only.
    "fixture_eikonal_p50_max": 0.05,
    "fixture_eikonal_p95_max": 0.25,
    "fixture_eikonal_max": 0.50,
    # canonical v16 is a voxel staircase with legitimate medial-axis ridges:
    # percentiles only, fluid side only.
    "canonical_eikonal_p50_max": 0.10,
    "canonical_eikonal_p95_max": 0.50,
    # max change of the edge zero-crossing fraction t (edge length = 1).
    "zero_level_displacement_max_edges": 0.25,
    # relative drift of sharp and smoothed volume vs the input state.
    "volume_relative_drift_max": 0.05,
    # max |reinit(reinit(x)) - reinit(x)| on band nodes, in units of h.
    "idempotence_max_h": 0.10,
}

REINIT_CONTRACT_PAYLOAD: dict[str, Any] = {
    "schema_version": REINIT_SCHEMA_VERSION,
    "kind": REINIT_CONTRACT_ID,
    "method": (
        "subcell edge-crossing initialization on interface-adjacent nodes, then "
        "deterministic Jacobi Godunov Eikonal relaxation per sign side; float64 "
        "internally, float32 output"
    ),
    "sign_rule": "solid iff phi_in < 0 (strict); every other node is non-solid; signs are never changed",
    "interface": (
        "edge zero crossing of the trilinear node field: t = |pa| / (|pa| + |pb|) from the "
        "solid node; t = 0.5 when |pa| + |pb| < degenerate_edge_sum_m"
    ),
    "frozen_node_distance": (
        "1 / sqrt(sum over axes of 1 / dmin_axis^2), dmin_axis = h * min t over that axis's "
        "crossing edges at the node; axes without a crossing contribute 0"
    ),
    "sign_floor": "output magnitude >= sign_floor_fraction_of_h * h so no node changes sign class",
    "band_half_width_cells": BAND_HALF_WIDTH_CELLS,
    "sign_floor_fraction_of_h": SIGN_FLOOR_FRACTION_OF_H,
    "degenerate_edge_sum_m": DEGENERATE_EDGE_SUM_M,
    "tolerances": TOLERANCES,
    "masks": "copied unchanged; magnitudes at masked nodes may change, signs never",
    "state_binding": "generation + 1; reinitialization_policy_id = kind; all other fields copied",
    "fail_closed": "any gate failure raises unless fail_closed=False is passed for evidence recording",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


REINIT_CONTRACT_SHA256 = hashlib.sha256(_canonical_json_bytes(REINIT_CONTRACT_PAYLOAD)).hexdigest()
