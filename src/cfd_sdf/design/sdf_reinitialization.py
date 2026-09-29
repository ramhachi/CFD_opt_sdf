"""Explicit SDF reinitialization operator (SDF-02, contract v1).

Contract constants were registered before any numerical evidence existed; see
``docs/sdf_native_reinitialization_contract_v1_2026_09.md``.  The operator is
applied only to an accepted update and is never differentiated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from .sdf_state import SDFDesignState
from .topology_policy import _FULL_26_CONNECTED_3D, classify_topology_events
from .volume_semantics import (
    SMOOTHED_VOLUME_CONTRACT_SHA256,
    _corner_mean,
    sharp_volume_m3,
    smoothed_volume_and_gradient,
)

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
        "deterministic Jacobi Godunov Eikonal relaxation per sign side, second-order "
        "backward differences where the second upwind neighbour is no larger (Sethian); float64 "
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

_MASKS = ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")


class SDFReinitializationError(ValueError):
    """Fail-closed reinitialization violation; ``report`` holds the evidence when available."""

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class ReinitResult:
    state: SDFDesignState
    report: dict[str, Any]


def _axis_slices(axis: int) -> tuple[tuple[slice, ...], tuple[slice, ...]]:
    lo = [slice(None)] * 3
    hi = [slice(None)] * 3
    lo[axis], hi[axis] = slice(None, -1), slice(1, None)
    return tuple(lo), tuple(hi)


def edge_crossings(phi: np.ndarray, solid: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, int]]:
    """Per axis: (crossing-edge mask, fraction t measured from the lower node, degenerate count)."""

    p = np.abs(phi.astype(np.float64))
    out = []
    for axis in range(3):
        lo, hi = _axis_slices(axis)
        cross = solid[lo] != solid[hi]
        total = p[lo] + p[hi]
        degenerate = cross & (total < DEGENERATE_EDGE_SUM_M)
        with np.errstate(invalid="ignore", divide="ignore"):
            t_solid = np.where(degenerate, 0.5, np.where(solid[lo], p[lo], p[hi]) / total)
        t_lo = np.where(solid[lo], t_solid, 1.0 - t_solid)
        out.append((cross, np.where(cross, t_lo, 0.0), int(degenerate.sum())))
    return out


def _reinit_phi(phi: np.ndarray, h: float) -> np.ndarray:
    """Signed float64 field with the contract's sign classes preserved."""

    solid = phi < 0.0
    crossings = edge_crossings(phi, solid)
    if not any(cross.any() for cross, _, _ in crossings):
        raise SDFReinitializationError("input has no solid/non-solid edge; nothing to reinitialize")
    inv2 = np.zeros(phi.shape)
    for axis, (cross, t_lo, _) in enumerate(crossings):
        lo, hi = _axis_slices(axis)
        dmin = np.full(phi.shape, np.inf)
        np.minimum(dmin[lo], np.where(cross, h * t_lo, np.inf), out=dmin[lo])
        np.minimum(dmin[hi], np.where(cross, h * (1.0 - t_lo), np.inf), out=dmin[hi])
        with np.errstate(divide="ignore"):
            inv2 += np.where(np.isfinite(dmin), 1.0 / dmin**2, 0.0)
    frozen = inv2 > 0.0
    with np.errstate(divide="ignore"):
        u = np.where(frozen, 1.0 / np.sqrt(inv2), np.inf)
    seed = u
    padded_solid = np.pad(solid, 2, constant_values=False)
    for _ in range(4 * sum(phi.shape)):
        padded_u = np.pad(u, 2, constant_values=np.inf)

        def neighbour(axis: int, k: int) -> np.ndarray:
            sl = [slice(2, -2)] * 3
            sl[axis] = slice(2 + k, padded_u.shape[axis] - 2 + k)
            sl = tuple(sl)
            # same-side neighbours only; out-of-grid padding is inf
            return np.where(padded_solid[sl] == solid, padded_u[sl], np.inf)

        targets, weights = [], []
        for axis in range(3):
            best, beyond = np.full(u.shape, np.inf), np.full(u.shape, np.inf)
            for shift in (-1, 1):
                a, b = neighbour(axis, shift), neighbour(axis, 2 * shift)
                better = a < best
                best, beyond = np.where(better, a, best), np.where(better, b, beyond)
            second = np.isfinite(beyond) & (beyond <= best)  # second-order backward difference
            with np.errstate(invalid="ignore"):
                targets.append(np.where(second, (4.0 * best - beyond) / 3.0, best))
            weights.append(np.where(second, 2.25, 1.0))
        order = np.argsort(np.stack(targets), axis=0, kind="stable")
        T = np.take_along_axis(np.stack(targets), order, 0)
        W = np.take_along_axis(np.stack(weights), order, 0)
        Tf = np.where(np.isfinite(T), T, 0.0)
        cands = []
        for k in (1, 2, 3):  # solve sum_i W_i (u - T_i)^2 = h^2 over the k smallest targets
            A, B = W[:k].sum(0), (W[:k] * Tf[:k]).sum(0)
            disc = B * B - A * ((W[:k] * Tf[:k] ** 2).sum(0) - h * h)
            cands.append(np.where(np.isfinite(T[k - 1]), (B + np.sqrt(np.maximum(disc, 0.0))) / A, np.inf))
        candidate = np.where(cands[0] <= T[1], cands[0], np.where(cands[1] <= T[2], cands[1], cands[2]))
        new = np.where(frozen, seed, np.minimum(u, candidate))
        if np.array_equal(new, u):
            break
        u = new
    else:
        raise SDFReinitializationError("Godunov relaxation did not reach a fixed point")
    if not np.isfinite(u).all():
        raise SDFReinitializationError("unreachable node after relaxation")
    return np.where(solid, -1.0, 1.0) * np.maximum(u, SIGN_FLOOR_FRACTION_OF_H * h)


def _with_phi(state: SDFDesignState, phi: np.ndarray) -> SDFDesignState:
    return SDFDesignState.create(
        phi=phi.astype(np.float32),
        origin_m=state.origin_m,
        spacing_m=state.spacing_m,
        design_mask=state.design_mask,
        fixed_solid_mask=state.fixed_solid_mask,
        forbidden_mask=state.forbidden_mask,
        root_mask=state.root_mask,
        narrow_band_width_m=state.narrow_band_width_m,
        generation=state.generation + 1,
        source_sha256=state.source_sha256,
        topology_policy_id=state.topology_policy_id,
        reinitialization_policy_id=REINIT_CONTRACT_ID,
    )


def _eikonal_stats(phi: np.ndarray, h: float) -> dict[str, Any]:
    p = phi.astype(np.float64)
    grad = np.sqrt(sum(g**2 for g in np.gradient(p, h)))
    interior = np.zeros(p.shape, dtype=bool)
    interior[1:-1, 1:-1, 1:-1] = True
    band = (np.abs(p) <= BAND_HALF_WIDTH_CELLS * h) & interior
    stats: dict[str, Any] = {}
    for side, side_mask in (("fluid", p > 0), ("solid", p < 0)):
        sel = band & side_mask
        err = np.abs(grad[sel] - 1.0)
        stats[side] = (
            {"count": 0, "p50": None, "p95": None, "max": None, "grad_min": None}
            if err.size == 0
            else {
                "count": int(err.size),
                "p50": float(np.percentile(err, 50)),
                "p95": float(np.percentile(err, 95)),
                "max": float(err.max()),
                "grad_min": float(grad[sel].min()),
            }
        )
    return stats


def _components(mask: np.ndarray) -> int:
    return int(ndimage.label(mask, structure=_FULL_26_CONNECTED_3D)[1])


def reinitialization_report(
    before: SDFDesignState, after: SDFDesignState, *, profile: str = "fixture"
) -> dict[str, Any]:
    """Measure the operator effect and evaluate every contract gate."""

    if profile not in ("fixture", "canonical"):
        raise SDFReinitializationError("profile must be 'fixture' or 'canonical'")
    h = float(before.spacing_m)
    solid_b, solid_a = before.solid_mask, after.solid_mask
    cross_b, cross_a = edge_crossings(before.phi, solid_b), edge_crossings(after.phi, solid_a)
    dt = np.concatenate([np.abs(tb[cb] - ta[cb]) for (cb, tb, _), (_, ta, _) in zip(cross_b, cross_a)])
    unmatched = sum(int(np.sum(cb != ca)) for (cb, _, _), (ca, _, _) in zip(cross_b, cross_a))
    eik_b, eik_a = _eikonal_stats(before.phi, h), _eikonal_stats(after.phi, h)
    phi_a64 = after.phi.astype(np.float64)
    band_a = np.abs(phi_a64) <= BAND_HALF_WIDTH_CELLS * h
    idem = np.abs(_reinit_phi(after.phi, h) - phi_a64)[band_a].max() / h
    change = np.abs(phi_a64 - before.phi)
    vs_b, vs_a = sharp_volume_m3(before), sharp_volume_m3(after)
    ve_b = smoothed_volume_and_gradient(before).smoothed_volume_m3
    ve_a = smoothed_volume_and_gradient(after).smoothed_volume_m3
    center_b, center_a = _corner_mean(before.phi) < 0.0, _corner_mean(after.phi) < 0.0
    node_events = classify_topology_events(solid_b, solid_a)
    center_events = classify_topology_events(center_b, center_a)
    top = {
        "node_events": list(node_events),
        "node_components": [_components(solid_b), _components(solid_a)],
        "center_events": list(center_events),
        "center_components": [_components(center_b), _components(center_a)],
    }
    measured: dict[str, Any] = {
        "input_state_sha256": before.state_sha256,
        "output_state_sha256": after.state_sha256,
        "input_phi_sha256": before.phi_sha256(),
        "output_phi_sha256": after.phi_sha256(),
        "crossing_edge_count": int(sum(c.sum() for c, _, _ in cross_b)),
        "degenerate_crossing_edge_count": int(sum(d for _, _, d in cross_b)),
        "eikonal_input": eik_b,
        "eikonal_output": eik_a,
        "zero_level_displacement_edges": {
            "max": float(dt.max()),
            "p95": float(np.percentile(dt, 95)),
            "mean": float(dt.mean()),
            "max_m": float(dt.max() * h),
        },
        "unmatched_crossings": unmatched,
        "phi_change_m": {"max_abs": float(change.max()), "max_abs_band": float(change[band_a].max())},
        "sharp_volume_m3": {"input": vs_b, "output": vs_a, "relative_drift": (vs_a - vs_b) / vs_b},
        "smoothed_volume_m3": {"input": ve_b, "output": ve_a, "relative_drift": (ve_a - ve_b) / ve_b},
        "solid_node_count": {"input": int(solid_b.sum()), "output": int(solid_a.sum())},
        "sign_changes": int(np.sum(solid_b != solid_a)),
        "masks_identical": all(np.array_equal(getattr(before, m), getattr(after, m)) for m in _MASKS),
        "topology": top,
        "idempotence_max_h": float(idem),
    }
    t = TOLERANCES
    gates: dict[str, dict[str, Any]] = {}

    def gate(name: str, value: Any, limit: Any, passed: bool) -> None:
        gates[name] = {"value": value, "limit": limit, "passed": bool(passed)}

    def le(name: str, value: float | None, limit: float) -> None:
        gate(name, value, limit, value is not None and bool(np.isfinite(value)) and value <= limit)

    if profile == "fixture":
        for side in ("fluid", "solid"):
            for q in ("p50", "p95", "max"):
                le(f"eikonal_{side}_{q}", eik_a[side][q], t[f"fixture_eikonal_{q}_max" if q != "max" else "fixture_eikonal_max"])
    else:
        le("eikonal_fluid_p50", eik_a["fluid"]["p50"], t["canonical_eikonal_p50_max"])
        le("eikonal_fluid_p95", eik_a["fluid"]["p95"], t["canonical_eikonal_p95_max"])
    le("zero_level_displacement_max_edges", measured["zero_level_displacement_edges"]["max"], t["zero_level_displacement_max_edges"])
    gate("unmatched_crossings", unmatched, 0, unmatched == 0)
    le("sharp_volume_relative_drift", abs(measured["sharp_volume_m3"]["relative_drift"]), t["volume_relative_drift_max"])
    le("smoothed_volume_relative_drift", abs(measured["smoothed_volume_m3"]["relative_drift"]), t["volume_relative_drift_max"])
    gate("masks_identical", measured["masks_identical"], True, measured["masks_identical"])
    gate("sign_changes", measured["sign_changes"], 0, measured["sign_changes"] == 0)
    gate("node_topology_events", top["node_events"], [], not node_events)
    gate("node_component_count", top["node_components"], "equal", top["node_components"][0] == top["node_components"][1])
    gate("center_topology_events", top["center_events"], [], not center_events)
    gate("center_component_count", top["center_components"], "equal", top["center_components"][0] == top["center_components"][1])
    le("idempotence_max_h", measured["idempotence_max_h"], t["idempotence_max_h"])
    return {
        "kind": REINIT_CONTRACT_ID,
        "schema_version": REINIT_SCHEMA_VERSION,
        "contract_sha256": REINIT_CONTRACT_SHA256,
        "smoothed_volume_contract_sha256": SMOOTHED_VOLUME_CONTRACT_SHA256,
        "profile": profile,
        "measured": measured,
        "gates": gates,
        "admissible": all(g["passed"] for g in gates.values()),
    }


def reinitialize_sdf(
    state: SDFDesignState, *, profile: str = "fixture", fail_closed: bool = True
) -> ReinitResult:
    """Apply the registered operator; raise on any gate failure unless ``fail_closed=False``."""

    if not isinstance(state, SDFDesignState):
        raise SDFReinitializationError("state must be an SDFDesignState")
    out = _with_phi(state, _reinit_phi(state.phi, float(state.spacing_m)))
    report = reinitialization_report(state, out, profile=profile)
    if fail_closed and not report["admissible"]:
        failed = sorted(k for k, g in report["gates"].items() if not g["passed"])
        raise SDFReinitializationError(f"reinitialization gates failed: {failed}", report)
    return ReinitResult(out, report)


__all__ = [
    "REINIT_CONTRACT_ID",
    "REINIT_CONTRACT_PAYLOAD",
    "REINIT_CONTRACT_SHA256",
    "TOLERANCES",
    "ReinitResult",
    "SDFReinitializationError",
    "edge_crossings",
    "reinitialization_report",
    "reinitialize_sdf",
]
