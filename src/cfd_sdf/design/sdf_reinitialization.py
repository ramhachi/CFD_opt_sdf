"""Explicit Godunov SDF reinitialization after an accepted design update.

The operator is not part of the registered finite-difference map
``phi -> response``. See the versioned reinitialization contract for its
sub-cell interface seed, fixed narrow-band, and fail-closed effect gates.
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

REINIT_CONTRACT_ID = "sdf_native_reinitialization_godunov2_v2"
REINIT_SCHEMA_VERSION = 2
BAND_HALF_WIDTH_CELLS = 3.0
SIGN_FLOOR_FRACTION_OF_H = 1e-9
DEGENERATE_EDGE_SUM_M = 1e-7
MAX_SWEEP_ITERATIONS_PER_AXIS_SUM = 4
TOLERANCES = {
    "fixture_eikonal_p50_max": 0.05,
    "fixture_eikonal_p95_max": 0.25,
    "fixture_eikonal_max": 0.50,
    "canonical_eikonal_p50_max": 0.10,
    "canonical_eikonal_p95_max": 0.50,
    "zero_level_displacement_max_edges": 0.25,
    "volume_relative_drift_max": 0.05,
    "idempotence_max_h": 0.10,
}
REINIT_CONTRACT_PAYLOAD: dict[str, Any] = {
    "schema_version": REINIT_SCHEMA_VERSION,
    "kind": REINIT_CONTRACT_ID,
    "method": (
        "sub-cell edge-crossing initialization followed by deterministic Jacobi "
        "second-order Godunov Eikonal relaxation per sign side; float64 internal "
        "distances, float32 output; exact-zero nodes remain zero"
    ),
    "sign_rule": "solid iff input phi < 0; exact zero is non-solid and remains zero",
    "interface": "linear zero crossing on every strict solid/non-solid grid edge",
    "degenerate_edge_rule": "if endpoint absolute-value sum < 1e-7 m, use midpoint t=0.5",
    "interface_node_seed": "dmin_axis is the nearest crossing distance on that axis; d=1/sqrt(sum_axis(1/dmin_axis^2)); missing axes contribute zero",
    "near_band": "replace only nodes with abs(input phi) <= 3*h; preserve all farther input values exactly",
    "masks": "copy design, fixed-solid, forbidden, and root masks byte-identically",
    "state_binding": "generation + 1; reinitialization_policy_id is this contract kind",
    "stopping": "zero-tolerance exact floating-point fixed point; max iterations = 4*sum(grid shape)",
    "tolerances": TOLERANCES,
    "volume": "registered trilinear cell-center sharp volume and sdf_native_smoothed_volume_v1",
    "fd_boundary": "post-acceptance only; excluded from the phi-to-response finite-difference map",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


REINIT_CONTRACT_SHA256 = hashlib.sha256(_canonical_json_bytes(REINIT_CONTRACT_PAYLOAD)).hexdigest()
_MASKS = ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")


class SDFReinitializationError(ValueError):
    """Fail-closed reinitialization or effect-gate failure."""


@dataclass(frozen=True)
class ReinitResult:
    state: SDFDesignState
    report: dict[str, Any]


def _axis_slices(axis: int) -> tuple[tuple[slice, ...], tuple[slice, ...]]:
    lo = [slice(None)] * 3
    hi = [slice(None)] * 3
    lo[axis], hi[axis] = slice(None, -1), slice(1, None)
    return tuple(lo), tuple(hi)


def edge_crossings(phi: np.ndarray, solid: np.ndarray):
    """Return crossing masks, fractions from lower-index nodes, and degenerate counts."""
    absolute = np.abs(phi.astype(np.float64))
    result = []
    for axis in range(3):
        lo, hi = _axis_slices(axis)
        crossing = solid[lo] != solid[hi]
        total = absolute[lo] + absolute[hi]
        degenerate = crossing & (total < DEGENERATE_EDGE_SUM_M)
        t_from_solid = np.where(
            degenerate, 0.5,
            np.divide(np.where(solid[lo], absolute[lo], absolute[hi]), total,
                      out=np.zeros_like(total), where=total != 0),
        )
        t_from_lo = np.where(solid[lo], t_from_solid, 1.0 - t_from_solid)
        result.append((crossing, np.where(crossing, t_from_lo, 0.0), int(degenerate.sum())))
    return result


def _reinit_phi(phi: np.ndarray, spacing_m: float) -> tuple[np.ndarray, int]:
    """Build sub-cell-seeded signed distances and retain the input far field."""
    solid = phi < 0.0
    crossings = edge_crossings(phi, solid)
    if not solid.any() or solid.all() or not any(mask.any() for mask, _, _ in crossings):
        raise SDFReinitializationError("input has no solid/non-solid interface")

    inverse_square = np.zeros(phi.shape, dtype=np.float64)
    for axis, (crossing, t_from_lo, _) in enumerate(crossings):
        lo, hi = _axis_slices(axis)
        nearest = np.full(phi.shape, np.inf)
        np.minimum(nearest[lo], np.where(crossing, spacing_m * t_from_lo, np.inf), out=nearest[lo])
        np.minimum(nearest[hi], np.where(crossing, spacing_m * (1.0 - t_from_lo), np.inf), out=nearest[hi])
        with np.errstate(divide="ignore"):
            inverse_square += np.where(np.isfinite(nearest), 1.0 / nearest**2, 0.0)

    # Existing exact-zero nodes are interface points and remain exact zeros.
    frozen = (inverse_square > 0.0) | (phi == 0.0)
    with np.errstate(divide="ignore"):
        seed = np.where(inverse_square > 0.0, 1.0 / np.sqrt(inverse_square), np.inf)
    seed[phi == 0.0] = 0.0
    distance = seed.copy()
    padded_solid = np.pad(solid, 2, constant_values=False)
    iteration_limit = MAX_SWEEP_ITERATIONS_PER_AXIS_SUM * sum(phi.shape)

    for iteration in range(1, iteration_limit + 1):
        padded_distance = np.pad(distance, 2, constant_values=np.inf)

        def neighbour(axis: int, offset: int) -> np.ndarray:
            slices = [slice(2, -2)] * 3
            slices[axis] = slice(2 + offset, padded_distance.shape[axis] - 2 + offset)
            slices = tuple(slices)
            return np.where(padded_solid[slices] == solid, padded_distance[slices], np.inf)

        targets, weights = [], []
        for axis in range(3):
            best, second_upwind = np.full(phi.shape, np.inf), np.full(phi.shape, np.inf)
            for offset in (-1, 1):
                adjacent, beyond = neighbour(axis, offset), neighbour(axis, 2 * offset)
                chosen = adjacent < best
                best, second_upwind = np.where(chosen, adjacent, best), np.where(chosen, beyond, second_upwind)
            use_second = np.isfinite(second_upwind) & (second_upwind <= best)
            with np.errstate(invalid="ignore"):
                targets.append(np.where(use_second, (4.0 * best - second_upwind) / 3.0, best))
            weights.append(np.where(use_second, 2.25, 1.0))

        order = np.argsort(np.stack(targets), axis=0, kind="stable")
        ordered_t = np.take_along_axis(np.stack(targets), order, axis=0)
        ordered_w = np.take_along_axis(np.stack(weights), order, axis=0)
        finite_t = np.where(np.isfinite(ordered_t), ordered_t, 0.0)
        candidates = []
        for count in (1, 2, 3):
            weight_sum = ordered_w[:count].sum(axis=0)
            weighted_sum = (ordered_w[:count] * finite_t[:count]).sum(axis=0)
            discriminant = weighted_sum**2 - weight_sum * (
                (ordered_w[:count] * finite_t[:count]**2).sum(axis=0) - spacing_m**2
            )
            candidate = (weighted_sum + np.sqrt(np.maximum(discriminant, 0.0))) / weight_sum
            candidates.append(np.where(np.isfinite(ordered_t[count - 1]), candidate, np.inf))
        update = np.where(
            candidates[0] <= ordered_t[1], candidates[0],
            np.where(candidates[1] <= ordered_t[2], candidates[1], candidates[2]),
        )
        updated = np.where(frozen, seed, np.minimum(distance, update))
        if np.array_equal(updated, distance):
            break
        distance = updated
    else:
        raise SDFReinitializationError(f"Godunov iteration limit reached ({iteration_limit})")

    if not np.isfinite(distance).all():
        raise SDFReinitializationError("interface does not reach every same-sign component")
    signed = np.where(solid, -1.0, 1.0) * np.maximum(distance, SIGN_FLOOR_FRACTION_OF_H * spacing_m)
    signed[phi == 0.0] = 0.0
    near_band = np.abs(phi) <= BAND_HALF_WIDTH_CELLS * spacing_m
    output = phi.astype(np.float64).copy()
    output[near_band] = signed[near_band]
    return output.astype(np.float32), iteration


def _with_phi(state: SDFDesignState, phi: np.ndarray) -> SDFDesignState:
    return SDFDesignState.create(
        phi=phi, origin_m=state.origin_m, spacing_m=state.spacing_m,
        design_mask=state.design_mask, fixed_solid_mask=state.fixed_solid_mask,
        forbidden_mask=state.forbidden_mask, root_mask=state.root_mask,
        narrow_band_width_m=state.narrow_band_width_m, generation=state.generation + 1,
        source_sha256=state.source_sha256, topology_policy_id=state.topology_policy_id,
        reinitialization_policy_id=REINIT_CONTRACT_ID,
    )


def _eikonal_stats(phi: np.ndarray, spacing_m: float) -> dict[str, Any]:
    gradient = np.sqrt(sum(value**2 for value in np.gradient(phi.astype(np.float64), spacing_m)))
    interior = np.zeros(phi.shape, dtype=bool)
    interior[1:-1, 1:-1, 1:-1] = True
    band = (np.abs(phi) <= BAND_HALF_WIDTH_CELLS * spacing_m) & interior
    report = {}
    for side, side_mask in (("fluid", phi > 0), ("solid", phi < 0)):
        errors = np.abs(gradient[band & side_mask] - 1.0)
        report[side] = {"count": int(errors.size), "p50": float(np.percentile(errors, 50)) if errors.size else None,
            "p95": float(np.percentile(errors, 95)) if errors.size else None,
            "max": float(errors.max()) if errors.size else None}
    return report


def _component_count(mask: np.ndarray) -> int:
    return int(ndimage.label(mask, structure=_FULL_26_CONNECTED_3D)[1])


def reinitialization_report(before: SDFDesignState, after: SDFDesignState, *, profile: str,
                            iterations: int) -> dict[str, Any]:
    if profile not in ("fixture", "canonical"):
        raise SDFReinitializationError("profile must be 'fixture' or 'canonical'")
    spacing = float(before.spacing_m)
    before_solid, after_solid = before.solid_mask, after.solid_mask
    crossings_before = edge_crossings(before.phi, before_solid)
    crossings_after = edge_crossings(after.phi, after_solid)
    changes = []
    for (mask0, t0, _), (mask1, t1, _) in zip(crossings_before, crossings_after):
        common = mask0 & mask1
        changes.append(np.abs(t0[common] - t1[common]))
    displacement = np.concatenate(changes) if changes else np.array([], dtype=np.float64)
    unmatched = sum(int(np.count_nonzero(a[0] != b[0])) for a, b in zip(crossings_before, crossings_after))
    crossing_count = sum(int(mask.sum()) for mask, _, _ in crossings_before)
    degenerate_count = sum(count for _, _, count in crossings_before)
    center_before, center_after = _corner_mean(before.phi) < 0, _corner_mean(after.phi) < 0
    before_node, after_node = classify_topology_events(before_solid, after_solid), classify_topology_events(after_solid, before_solid)
    before_center, after_center = classify_topology_events(center_before, center_after), classify_topology_events(center_after, center_before)
    second, second_iterations = _reinit_phi(after.phi, spacing)
    band_after = np.abs(after.phi) <= BAND_HALF_WIDTH_CELLS * spacing
    idempotence = float(np.max(np.abs(second[band_after] - after.phi[band_after])) / spacing)
    v_sharp_before, v_sharp_after = sharp_volume_m3(before), sharp_volume_m3(after)
    v_smooth_before = smoothed_volume_and_gradient(before).smoothed_volume_m3
    v_smooth_after = smoothed_volume_and_gradient(after).smoothed_volume_m3
    eikonal_before, eikonal_after = _eikonal_stats(before.phi, spacing), _eikonal_stats(after.phi, spacing)
    measured = {
        "input_state_sha256": before.state_sha256,
        "output_state_sha256": after.state_sha256,
        "input_phi_sha256": before.phi_sha256(),
        "output_phi_sha256": after.phi_sha256(),
        "crossing_edge_count": crossing_count,
        "degenerate_crossing_edge_count": degenerate_count,
        "godunov_iterations": iterations,
        "godunov_fixed_point": True,
        "idempotence_iterations": second_iterations,
        "input_far_band_preserved": bool(np.array_equal(
            before.phi[np.abs(before.phi) > BAND_HALF_WIDTH_CELLS * spacing],
            after.phi[np.abs(before.phi) > BAND_HALF_WIDTH_CELLS * spacing])),
        "eikonal_input": eikonal_before,
        "eikonal_output": eikonal_after,
        "zero_level_displacement_edges_max": float(displacement.max()) if displacement.size else None,
        "unmatched_crossings": unmatched,
        "sign_changes": int(np.count_nonzero(before_solid != after_solid)),
        "exact_zero_nodes_preserved": bool(np.array_equal(before.phi == 0, after.phi == 0)),
        "mask_bytes_identical": {
            name: bool(np.array_equal(getattr(before, name), getattr(after, name))) for name in _MASKS
        },
        "sharp_volume_m3": {"input": v_sharp_before, "output": v_sharp_after,
            "relative_drift": (v_sharp_after - v_sharp_before) / v_sharp_before if v_sharp_before else None},
        "smoothed_volume_m3": {"input": v_smooth_before, "output": v_smooth_after,
            "relative_drift": (v_smooth_after - v_smooth_before) / v_smooth_before if v_smooth_before else None},
        "node_topology_events": {"before_to_after": list(before_node), "after_to_before": list(after_node)},
        "node_components": [_component_count(before_solid), _component_count(after_solid)],
        "center_topology_events": {"before_to_after": list(before_center), "after_to_before": list(after_center)},
        "center_components": [_component_count(center_before), _component_count(center_after)],
        "band_idempotence_max_h": idempotence,
    }
    t = TOLERANCES
    gates = {}

    def gate(name, value, limit, passed):
        gates[name] = {"value": value, "limit": limit, "passed": bool(passed)}

    def le(name, value, limit):
        gate(name, value, limit, value is not None and np.isfinite(value) and value <= limit)

    if profile == "fixture":
        for side in ("fluid", "solid"):
            for quantile in ("p50", "p95", "max"):
                limit_key = f"fixture_eikonal_{quantile}_max" if quantile != "max" else "fixture_eikonal_max"
                le(f"eikonal_{side}_{quantile}", eikonal_after[side][quantile], t[limit_key])
    else:
        le("eikonal_fluid_p50", eikonal_after["fluid"]["p50"], t["canonical_eikonal_p50_max"])
        le("eikonal_fluid_p95", eikonal_after["fluid"]["p95"], t["canonical_eikonal_p95_max"])
    le("zero_level_displacement_edges_max", measured["zero_level_displacement_edges_max"], t["zero_level_displacement_max_edges"])
    gate("unmatched_crossings", unmatched, 0, unmatched == 0)
    le("sharp_volume_relative_drift", abs(measured["sharp_volume_m3"]["relative_drift"]) if measured["sharp_volume_m3"]["relative_drift"] is not None else None, t["volume_relative_drift_max"])
    le("smoothed_volume_relative_drift", abs(measured["smoothed_volume_m3"]["relative_drift"]) if measured["smoothed_volume_m3"]["relative_drift"] is not None else None, t["volume_relative_drift_max"])
    gate("mask_bytes_identical", measured["mask_bytes_identical"], True, all(measured["mask_bytes_identical"].values()))
    gate("sign_changes", measured["sign_changes"], 0, measured["sign_changes"] == 0)
    gate("exact_zero_nodes_preserved", measured["exact_zero_nodes_preserved"], True, measured["exact_zero_nodes_preserved"])
    gate("far_band_preserved", measured["input_far_band_preserved"], True, measured["input_far_band_preserved"])
    gate("node_topology_events", measured["node_topology_events"], [], not before_node and not after_node)
    gate("node_component_count", measured["node_components"], "equal", measured["node_components"][0] == measured["node_components"][1])
    gate("center_topology_events", measured["center_topology_events"], [], not before_center and not after_center)
    gate("center_component_count", measured["center_components"], "equal", measured["center_components"][0] == measured["center_components"][1])
    le("band_idempotence_max_h", idempotence, t["idempotence_max_h"])
    return {"kind": REINIT_CONTRACT_ID, "schema_version": REINIT_SCHEMA_VERSION,
        "contract_sha256": REINIT_CONTRACT_SHA256,
        "smoothed_volume_contract_sha256": SMOOTHED_VOLUME_CONTRACT_SHA256,
        "profile": profile, "measured": measured, "gates": gates,
        "admissible": all(item["passed"] for item in gates.values())}


def reinitialize_sdf(state: SDFDesignState, *, profile: str, fail_closed: bool = True) -> ReinitResult:
    if not isinstance(state, SDFDesignState):
        raise SDFReinitializationError("state must be an SDFDesignState")
    field, iterations = _reinit_phi(state.phi, float(state.spacing_m))
    output = _with_phi(state, field)
    report = reinitialization_report(state, output, profile=profile, iterations=iterations)
    if fail_closed and not report["admissible"]:
        failed = sorted(name for name, value in report["gates"].items() if not value["passed"])
        raise SDFReinitializationError(f"reinitialization gates failed: {failed}", report)
    return ReinitResult(output, report)


__all__ = ["REINIT_CONTRACT_ID", "REINIT_CONTRACT_PAYLOAD", "REINIT_CONTRACT_SHA256",
    "TOLERANCES", "ReinitResult", "SDFReinitializationError", "edge_crossings",
    "reinitialization_report", "reinitialize_sdf"]
