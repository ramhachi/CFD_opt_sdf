"""Frozen R6 and predict-then-run state construction contracts.

This module contains only host-side geometry/inventory rules.  It does not
read force histories, run a solver, or import the registered FD-08 evaluator.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping

import numpy as np

from .design.sdf_state import SDFDesignState
from .gradients.directional_fd import (
    direction_sha256,
    generate_directions,
    zero_level_margin_m,
)


R6_EPSILON_MM = tuple(float(value) for value in np.geomspace(0.5, 5.0, 6))
FORMAL_INTERVAL_INDICES = (0, 2, 4)
FORMAL_EPSILON_MM = tuple(
    math.sqrt(R6_EPSILON_MM[index] * R6_EPSILON_MM[index + 1])
    for index in FORMAL_INTERVAL_INDICES
)
DIRECTION_IDS = (
    "D0_interface_offset",
    "D1_filtered_seed11",
    "D2_filtered_seed2026",
    "P1_upstream_lobe",
)
FLAG_NAMES = (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse",
    "optimizer", "topology",
)
DUPLICATE_COSINE_ABS_LIMIT = 0.95
FLOAT32_DIRECTION_RELATIVE_L2_LIMIT = 0.05
MARGIN_GATE_M = 0.15
MARGIN_TOLERANCE_M = 1e-6


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    import json

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256_bytes(encoded)


def false_flags() -> dict[str, bool]:
    return {name: False for name in FLAG_NAMES}


def _active(state: SDFDesignState) -> np.ndarray:
    return state.design_mask & ~state.fixed_solid_mask & ~state.forbidden_mask & ~state.root_mask


def _active_gradient(state: SDFDesignState, indices: np.ndarray) -> np.ndarray:
    """Match the frozen Stage 1.5 central/one-sided finite-difference stencil."""
    components = []
    for axis in range(3):
        left, right = indices.copy(), indices.copy()
        left[:, axis] = np.maximum(indices[:, axis] - 1, 0)
        right[:, axis] = np.minimum(indices[:, axis] + 1, state.shape[axis] - 1)
        denominator = (right[:, axis] - left[:, axis]) * state.spacing_m
        if np.any(denominator <= 0):
            raise ValueError("P1 gradient stencil encountered a singleton grid axis")
        component = (
            state.phi[tuple(right.T)].astype(np.float64)
            - state.phi[tuple(left.T)].astype(np.float64)
        ) / denominator
        components.append(component)
    return np.stack(components, axis=1)


def generate_p1(state: SDFDesignState) -> tuple[np.ndarray, dict[str, Any]]:
    """Build the approved P1 mode, without response-dependent choices."""
    active = _active(state)
    indices = np.argwhere(active)
    if not len(indices):
        raise ValueError("P1 requires nonempty unconstrained active nodes")
    xyz = np.asarray(state.origin_m, dtype=np.float64) + indices * state.spacing_m
    low, high = xyz.min(axis=0), xyz.max(axis=0)
    span = high - low
    if np.any(span <= 0):
        raise ValueError("P1 active coordinate bounding box is degenerate")
    center = low + np.asarray((0.25, 0.5, 0.5)) * span
    width = np.asarray((0.6, 0.8, 0.8)) * span
    radius2 = np.sum(((xyz - center) / width) ** 2, axis=1)
    amplitude = np.maximum(1.0 - radius2, 0.0) ** 3
    gradient = _active_gradient(state, indices)
    magnitude = np.linalg.norm(gradient, axis=1)
    radius = np.abs(state.phi[active].astype(np.float64)) / state.narrow_band_width_m
    taper = np.where(radius < 1.0, 0.5 * (1.0 + np.cos(np.pi * radius)), 0.0)
    raw = -amplitude * magnitude * taper
    peak = float(np.max(np.abs(raw), initial=0.0))
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValueError("frozen P1 expression has no finite nonzero support")
    direction = np.zeros(state.shape, dtype="<f4")
    direction[active] = np.asarray(raw / peak, dtype="<f4")
    direction[~active] = 0.0
    if not np.isfinite(direction).all():
        raise ValueError("P1 contains nonfinite values")
    peak_f32 = float(np.max(np.abs(direction), initial=0.0))
    if not math.isclose(peak_f32, 1.0, rel_tol=0.0, abs_tol=2e-7):
        raise ValueError("P1 max normalization failed after Float32 conversion")
    audit = {
        "id": "P1_upstream_lobe",
        "center_bbox_fraction": [0.25, 0.5, 0.5],
        "width_bbox_fraction": [0.6, 0.8, 0.8],
        "center_m": center.tolist(),
        "width_m": width.tolist(),
        "amplitude": "max(1-r^2,0)^3",
        "normal_convention": "+gradient(phi)/|gradient(phi)|; phi<0 is solid",
        "raw_scalar_rule": "-amplitude*|gradient(phi)|*cosine_interface_taper",
        "normal_displacement_rule": "delta_phi approximately -a*|gradient(phi)|",
        "gradient_stencil": "central difference in interior; first-order one-sided at each box face",
        "taper": "0.5*(1+cos(pi*abs(phi)/narrow_band_width)) for radius<1, otherwise 0",
        "normalization": "divide by maximum absolute raw value, cast little-endian Float32, retain max=1",
        "raw_normalizer": peak,
        "max_abs_float32": peak_f32,
        "active_nonzero_nodes": int(np.count_nonzero(direction[active])),
        "support_outside_active_zero": bool(np.all(direction[~active] == 0)),
        "direction_sha256_c_order_le_f32": direction_sha256(direction),
    }
    return np.ascontiguousarray(direction), audit


def direction_diagnostics(
    state: SDFDesignState, directions: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    if tuple(directions) != DIRECTION_IDS:
        raise ValueError("R6 direction order must be D0, D1, D2, P1")
    active = _active(state)
    flattened = {key: np.asarray(value, dtype=np.float64).ravel() for key, value in directions.items()}
    rows = {}
    for name, direction in directions.items():
        values = np.asarray(direction)
        if values.shape != state.shape or values.dtype != np.dtype("<f4"):
            raise ValueError(f"{name} dtype or point-grid shape mismatch")
        if not np.isfinite(values).all() or np.any(values[~active] != 0.0):
            raise ValueError(f"{name} has invalid values or constrained support")
        peak = float(np.max(np.abs(values), initial=0.0))
        if not math.isclose(peak, 1.0, rel_tol=0.0, abs_tol=2e-7):
            raise ValueError(f"{name} is not max normalized")
        rms_active = float(np.sqrt(np.mean(values[active].astype(np.float64) ** 2)))
        rms_full = float(np.linalg.norm(values.astype(np.float64).ravel()) / math.sqrt(values.size))
        rows[name] = {
            "sha256": direction_sha256(values),
            "dtype": "little-endian-float32",
            "order": "C",
            "max_abs": peak,
            "support_nonzero_nodes": int(np.count_nonzero(values)),
            "rms_active": rms_active,
            "rms_full": rms_full,
        }
    pairwise = {}
    for index, left in enumerate(DIRECTION_IDS):
        for right in DIRECTION_IDS[index + 1:]:
            a, b = flattened[left], flattened[right]
            cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            intersection = int(np.count_nonzero((a != 0.0) & (b != 0.0)))
            union = int(np.count_nonzero((a != 0.0) | (b != 0.0)))
            pairwise[f"{left}|{right}"] = {
                "l2_inner_product": float(np.dot(a, b)),
                "cosine": cosine,
                "rms_difference": float(np.sqrt(np.mean((a - b) ** 2))),
                "max_abs_difference": float(np.max(np.abs(a - b), initial=0.0)),
                "support_intersection_nodes": intersection,
                "support_union_nodes": union,
                "support_jaccard": intersection / union if union else None,
                "duplicate_gate_abs_cosine_lt": DUPLICATE_COSINE_ABS_LIMIT,
                "duplicate_gate_passed": abs(cosine) < DUPLICATE_COSINE_ABS_LIMIT,
            }
            if not math.isfinite(cosine) or abs(cosine) >= DUPLICATE_COSINE_ABS_LIMIT:
                raise ValueError(f"direction duplicate gate failed: {left} and {right}")
    return {"directions": rows, "pairwise": pairwise}


def state_identity(state: SDFDesignState) -> dict[str, Any]:
    phi_c = np.asarray(state.phi, dtype="<f4", order="C").tobytes(order="C")
    phi_f = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    return {
        "state_sha256": state.state_sha256,
        "phi_c_order_sha256": sha256_bytes(phi_c),
        "phi_fortran_order_sha256": sha256_bytes(phi_f),
        "phi_bytes": phi_f,
        "shape": list(state.shape),
        "origin_m": list(state.origin_m),
        "spacing_m": state.spacing_m,
        "margin_m": zero_level_margin_m(state.phi, state.spacing_m),
    }


def construct_state(
    parent: SDFDesignState,
    direction: np.ndarray,
    epsilon_mm: float,
    sign: int,
) -> tuple[SDFDesignState, dict[str, Any]]:
    if not math.isfinite(epsilon_mm) or epsilon_mm <= 0 or sign not in (-1, 1):
        raise ValueError("epsilon must be positive finite mm and sign must be +/-1")
    active = _active(parent)
    eps_m = epsilon_mm / 1000.0
    raw = np.asarray(
        parent.phi.astype(np.float64) + sign * eps_m * direction.astype(np.float64),
        dtype="<f4",
    )
    raw[~active] = parent.phi[~active]
    child = SDFDesignState.create(
        phi=raw,
        origin_m=parent.origin_m,
        spacing_m=parent.spacing_m,
        design_mask=parent.design_mask,
        fixed_solid_mask=parent.fixed_solid_mask,
        forbidden_mask=parent.forbidden_mask,
        root_mask=parent.root_mask,
        narrow_band_width_m=parent.narrow_band_width_m,
        generation=parent.generation,
        source_sha256=parent.source_sha256,
        topology_policy_id=parent.topology_policy_id,
        reinitialization_policy_id=parent.reinitialization_policy_id,
    )
    delta = np.abs(child.phi.astype(np.float64) - parent.phi.astype(np.float64))
    changed = delta != 0.0
    if not changed.any() or not np.any(changed & active):
        raise ValueError("Float32 perturbation changes no active nodes")
    if np.any(changed & ~active) or np.any(child.phi[~active].view("<u4") != parent.phi[~active].view("<u4")):
        raise ValueError("perturbation changed fixed, forbidden, root, or out-of-design nodes")
    if not np.array_equal(child.design_mask, parent.design_mask):
        raise ValueError("design mask changed")
    if not np.array_equal(child.fixed_solid_mask, parent.fixed_solid_mask):
        raise ValueError("fixed-solid mask changed")
    if not np.array_equal(child.forbidden_mask, parent.forbidden_mask):
        raise ValueError("forbidden mask changed")
    if not np.array_equal(child.root_mask, parent.root_mask):
        raise ValueError("root mask changed")
    margin = zero_level_margin_m(child.phi, child.spacing_m)
    if not math.isfinite(margin) or margin < MARGIN_GATE_M:
        raise ValueError(f"perturbed state margin below {MARGIN_GATE_M}: {margin}")
    return child, {
        "changed_node_count": int(np.count_nonzero(changed)),
        "maximum_pointwise_change_m": float(delta.max(initial=0.0)),
        "support_outside_active_exactly_unchanged": True,
        "masks_equal": True,
        "zero_level_margin_m": margin,
        "margin_gate_m": MARGIN_GATE_M,
    }


def float32_centered_audit(
    state: SDFDesignState,
    direction: np.ndarray,
    epsilon_mm: float,
) -> dict[str, Any]:
    plus, plus_audit = construct_state(state, direction, epsilon_mm, +1)
    minus, minus_audit = construct_state(state, direction, epsilon_mm, -1)
    eps_m = epsilon_mm / 1000.0
    realized = (plus.phi.astype(np.float64) - minus.phi.astype(np.float64)) / (2 * eps_m)
    requested = direction.astype(np.float64)
    active = _active(state)
    support = active & (requested != 0.0)
    denom = float(np.linalg.norm(requested[support]))
    if not math.isfinite(denom) or denom <= 0:
        raise ValueError("requested direction has empty or invalid support")
    relative_l2 = float(np.linalg.norm(realized[support] - requested[support]) / denom)
    if not math.isfinite(relative_l2) or relative_l2 > FLOAT32_DIRECTION_RELATIVE_L2_LIMIT:
        raise ValueError(f"centered Float32 direction relative L2 error exceeds 5%: {relative_l2}")
    outside = ~active
    support_outside_byte_equal = (
        plus.phi[outside].tobytes() == state.phi[outside].tobytes()
        and minus.phi[outside].tobytes() == state.phi[outside].tobytes()
    )
    if not support_outside_byte_equal:
        raise ValueError("support-outside phi bytes changed")
    return {
        "epsilon_mm": epsilon_mm,
        "plus": plus_audit,
        "minus": minus_audit,
        "centered_realized_direction_relative_l2_error": relative_l2,
        "relative_l2_limit": FLOAT32_DIRECTION_RELATIVE_L2_LIMIT,
        "requested_direction_support_nodes": int(np.count_nonzero(support)),
        "centered_changed_nodes": int(np.count_nonzero(plus.phi != minus.phi)),
        "support_outside_byte_equal": support_outside_byte_equal,
        "plus_state_sha256": plus.state_sha256,
        "minus_state_sha256": minus.state_sha256,
        "plus_phi_fortran_sha256": state_identity(plus)["phi_fortran_order_sha256"],
        "minus_phi_fortran_sha256": state_identity(minus)["phi_fortran_order_sha256"],
    }


def build_state_inventory(
    state: SDFDesignState,
    directions: Mapping[str, np.ndarray],
    epsilon_mm: tuple[float, ...] = R6_EPSILON_MM,
    *,
    expected_state_count: int = 49,
) -> tuple[list[dict[str, Any]], dict[str, bytes], list[dict[str, Any]]]:
    inventory = []
    blobs: dict[str, bytes] = {}
    audits = []
    baseline = state_identity(state)
    inventory.append({
        "name": "baseline_v17",
        "kind": "baseline",
        "direction_id": None,
        "epsilon_mm": None,
        "sign": 0,
        **{key: baseline[key] for key in baseline if key != "phi_bytes"},
        "phi_raw_file": "baseline_v17.phi.f32f",
    })
    blobs["baseline_v17.phi.f32f"] = baseline["phi_bytes"]
    seen = {baseline["phi_bytes"]: "baseline_v17"}
    for direction_id in DIRECTION_IDS:
        direction = directions[direction_id]
        epsilons = epsilon_mm if len(epsilon_mm) == 6 else epsilon_mm
        for epsilon in epsilons:
            audit = float32_centered_audit(state, direction, epsilon)
            audits.append({"direction_id": direction_id, **audit})
            for sign, sign_name in ((1, "plus"), (-1, "minus")):
                child, perturbation = construct_state(state, direction, epsilon, sign)
                identity = state_identity(child)
                raw_name = f"{direction_id}__e{epsilon:.17g}mm__{sign_name}.phi.f32f"
                if identity["phi_bytes"] in seen:
                    raise ValueError(f"distinct R6 state bytes collide: {raw_name} == {seen[identity['phi_bytes']]}")
                seen[identity["phi_bytes"]] = raw_name
                blobs[raw_name] = identity["phi_bytes"]
                inventory.append({
                    "name": raw_name[:-9],
                    "kind": "calibration",
                    "direction_id": direction_id,
                    "epsilon_mm": epsilon,
                    "epsilon_m": epsilon / 1000.0,
                    "sign": sign,
                    "sign_label": sign_name,
                    **{key: identity[key] for key in identity if key != "phi_bytes"},
                    **perturbation,
                    "phi_raw_file": raw_name,
                })
    if len(inventory) != expected_state_count or len(blobs) != expected_state_count:
        raise ValueError(f"state inventory must have {expected_state_count} states, got {len(inventory)}")
    return inventory, blobs, audits


def formal_prediction(
    epsilon_mm: float,
    beta_mm: list[float] | tuple[float, float],
    covariance_mm: list[list[float]] | tuple[tuple[float, float], tuple[float, float]],
    params: Mapping[str, float],
) -> dict[str, float]:
    """Apply the preregistered full calibration Model A without refitting."""
    beta = np.asarray(beta_mm, dtype=np.float64)
    covariance = np.asarray(covariance_mm, dtype=np.float64)
    if beta.shape != (2,) or covariance.shape != (2, 2):
        raise ValueError("formal prediction requires the frozen two-parameter Model A fit")
    x = np.asarray((epsilon_mm, epsilon_mm**3), dtype=np.float64)
    prediction = float(x @ beta)
    variance = float(
        params["sigma0_n"] ** 2
        + (params["rho"] * prediction) ** 2
        + x @ covariance @ x
    )
    if variance < 0 or not math.isfinite(variance):
        raise ValueError("formal predictive variance is nonfinite or negative")
    return {"s_pred_n": prediction, "sigma_pred_n": math.sqrt(variance)}


def classify_formal_comparison(
    s_pred_n: float,
    s_obs_n: float,
    sigma_pred_n: float,
    params: Mapping[str, float],
) -> dict[str, Any]:
    vals = (s_pred_n, s_obs_n, sigma_pred_n)
    if not all(math.isfinite(value) for value in vals) or sigma_pred_n < 0:
        return {"verdict": "UNRESOLVED", "reason": "nonfinite_prediction_observation_or_sigma"}
    threshold = max(3.0 * sigma_pred_n, params["tol_hold"] * abs(s_pred_n))
    error = abs(s_obs_n - s_pred_n)
    relative_error = error / abs(s_pred_n) if s_pred_n != 0 else None
    standardized = error / sigma_pred_n if sigma_pred_n > 0 else None
    same_sign = s_pred_n != 0 and s_obs_n != 0 and math.copysign(1.0, s_pred_n) == math.copysign(1.0, s_obs_n)
    finite_integrity = all(math.isfinite(value) for value in vals)
    magnitude = abs(s_pred_n) >= params["k_mag"] * params["sigma0_n"] and abs(s_obs_n) >= params["k_mag"] * params["sigma0_n"]
    if not finite_integrity or not same_sign:
        verdict = "FAIL"
    elif error > threshold:
        verdict = "FAIL"
    elif not magnitude:
        verdict = "UNRESOLVED"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict,
        "same_sign": same_sign,
        "magnitude_passed": magnitude,
        "absolute_error_n": error,
        "relative_error": relative_error,
        "standardized_error": standardized,
        "threshold_n": threshold,
        "s_pred_n": s_pred_n,
        "s_obs_n": s_obs_n,
        "sigma_pred_n": sigma_pred_n,
    }


def campaign_verdict(verdicts: list[str]) -> str:
    if not verdicts:
        return "UNRESOLVED"
    if any(value == "FAIL" for value in verdicts):
        return "FAIL"
    if all(value == "PASS" for value in verdicts):
        return "PASS"
    return "UNRESOLVED"
