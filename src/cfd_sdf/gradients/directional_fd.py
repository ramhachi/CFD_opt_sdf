"""Solver-neutral centered finite differences along frozen SDF directions.

This contract represents scalar directional derivatives of primitive responses;
it is deliberately distinct from :class:`GradientEvaluation`, which represents
three-dimensional response gradients.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from ..design.sdf_state import SDFDesignState
from ..oracles.base import PRIMITIVE_RESPONSES
from ..runtime.fingerprint import canonical_json_sha256, validate_sha256_hex

DIRECTION_IDS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
EPSILON_LADDER_M = (0.0005, 0.0010, 0.0025, 0.0050, 0.0100)
FILTER_KERNEL = np.asarray((1, 4, 6, 4, 1), dtype=np.float64) / 16.0
BASELINE_REPEATS = 3
RESOLUTION_FACTOR = 20.0
PLATEAU_RELATIVE_TOLERANCE = 0.05
STATIONARITY_RELATIVE_DRIFT_MAX = 0.02
NOISE_RELATIVE_FLOOR = 1.0e-8
SDF_MARGIN_GATE_M = 0.15
FLOAT32_PHI_TOLERANCE_M = 2.0 * np.finfo(np.float32).eps * 0.05


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def phi_sha256(phi: np.ndarray, *, order: str) -> str:
    if order not in {"C", "F"}:
        raise ValueError("phi order must be 'C' or 'F'")
    return sha256_bytes(np.asarray(phi, dtype="<f4", order=order).tobytes(order=order))


def direction_sha256(direction: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(direction, dtype="<f4").tobytes())


def _active_mask(state: SDFDesignState) -> np.ndarray:
    return state.design_mask & ~state.fixed_solid_mask & ~state.forbidden_mask & ~state.root_mask


def interface_taper(state: SDFDesignState) -> np.ndarray:
    """Cosine taper on the metadata-declared SDF narrow band."""

    radius = np.abs(state.phi.astype(np.float64)) / float(state.narrow_band_width_m)
    taper = np.zeros(state.shape, dtype=np.float64)
    inside = radius < 1.0
    taper[inside] = 0.5 * (1.0 + np.cos(np.pi * radius[inside]))
    return taper


def _normalize_direction(values: np.ndarray, active: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64).copy()
    result[~active] = 0.0
    peak = float(np.max(np.abs(result), initial=0.0))
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValueError("direction has no finite nonzero support")
    result = np.asarray(result / peak, dtype=np.float32)
    result[~active] = 0.0
    return np.ascontiguousarray(result)


def _convolve_reflect(values: np.ndarray, axis: int) -> np.ndarray:
    pad = [(0, 0)] * values.ndim
    pad[axis] = (2, 2)
    padded = np.pad(values, pad, mode="reflect")
    result = np.zeros_like(values, dtype=np.float64)
    for offset, weight in enumerate(FILTER_KERNEL):
        start = offset
        stop = start + values.shape[axis]
        slices = [slice(None)] * values.ndim
        slices[axis] = slice(start, stop)
        result += weight * padded[tuple(slices)]
    return result


def _filtered_noise(seed: int, shape: tuple[int, int, int]) -> np.ndarray:
    # Explicit PCG64 and reflect padding make the registered generator stable
    # and independent of SciPy or other optional image-processing packages.
    values = np.random.Generator(np.random.PCG64(seed)).standard_normal(shape)
    for _ in range(2):
        for axis in range(3):
            values = _convolve_reflect(values, axis)
    return values


def generate_directions(state: SDFDesignState) -> dict[str, np.ndarray]:
    """Return D0 and the two fixed-seed, filtered random directions."""

    active = _active_mask(state)
    weights = interface_taper(state) * active
    if not np.any(weights > 0.0):
        raise ValueError("canonical design mask has no interface narrow-band support")

    d0 = _normalize_direction(weights, active)
    directions = {DIRECTION_IDS[0]: d0}
    for direction_id, seed in ((DIRECTION_IDS[1], 11), (DIRECTION_IDS[2], 2026)):
        noise = _filtered_noise(seed, state.shape)
        weight_sum = float(weights.sum())
        weighted_mean = float(np.sum(noise * weights) / weight_sum)
        directions[direction_id] = _normalize_direction((noise - weighted_mean) * weights, active)
    validate_directions(state, directions)
    return directions


def validate_directions(
    state: SDFDesignState,
    directions: Mapping[str, np.ndarray],
    *,
    duplicate_cosine_abs_max: float = 0.95,
) -> dict[str, Any]:
    if tuple(directions) != DIRECTION_IDS:
        raise ValueError("direction inventory/order does not match the registered three directions")
    active = _active_mask(state)
    hashes: dict[str, str] = {}
    peaks: dict[str, float] = {}
    for direction_id, raw in directions.items():
        direction = np.asarray(raw)
        if direction.dtype != np.float32 or direction.shape != state.shape:
            raise ValueError(f"{direction_id} must be float32 with canonical point-grid shape")
        if not np.isfinite(direction).all():
            raise ValueError(f"{direction_id} contains non-finite values")
        if np.any(direction[~active] != 0.0):
            raise ValueError(f"{direction_id} is nonzero outside the unconstrained design mask")
        peak = float(np.max(np.abs(direction), initial=0.0))
        if not math.isclose(peak, 1.0, rel_tol=0.0, abs_tol=2.0e-7):
            raise ValueError(f"{direction_id} max-absolute value is not one")
        hashes[direction_id] = direction_sha256(direction)
        peaks[direction_id] = peak

    similarities: dict[str, float] = {}
    ids = tuple(directions)
    for i, left_id in enumerate(ids):
        left = np.asarray(directions[left_id], dtype=np.float64).ravel()
        for right_id in ids[i + 1:]:
            right = np.asarray(directions[right_id], dtype=np.float64).ravel()
            cosine = float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right)))
            key = f"{left_id}|{right_id}"
            similarities[key] = cosine
            if not math.isfinite(cosine) or abs(cosine) >= duplicate_cosine_abs_max:
                raise ValueError(f"registered directions are duplicates: {key} cosine={cosine}")
    return {
        "shape": list(state.shape),
        "dtype": "float32",
        "direction_sha256": hashes,
        "max_abs": peaks,
        "pairwise_cosine": similarities,
    }


def perturbation_case_id(direction_id: str, epsilon_m: float, sign: int) -> str:
    if direction_id not in DIRECTION_IDS or epsilon_m not in EPSILON_LADDER_M or sign not in {-1, 1}:
        raise ValueError("unregistered direction, epsilon, or perturbation sign")
    epsilon_tag = f"{epsilon_m:.4f}".replace(".", "p")
    sign_tag = "plus" if sign == 1 else "minus"
    return f"{direction_id}__eps_{epsilon_tag}m__{sign_tag}"


def perturbation_case_ids() -> tuple[str, ...]:
    return tuple(
        perturbation_case_id(direction_id, epsilon_m, sign)
        for direction_id in DIRECTION_IDS
        for epsilon_m in EPSILON_LADDER_M
        for sign in (1, -1)
    )


def perturbed_state(
    parent: SDFDesignState,
    direction: np.ndarray,
    *,
    epsilon_m: float,
    sign: int,
    margin_gate_m: float = SDF_MARGIN_GATE_M,
) -> tuple[SDFDesignState, dict[str, Any]]:
    if (not math.isfinite(epsilon_m) or epsilon_m <= 0.0 or sign not in {-1, 1}
            or not math.isfinite(margin_gate_m) or margin_gate_m < 0.0):
        raise ValueError("epsilon and margin gate must be finite/valid and sign must be +/-1")
    validate_direction(parent, direction)
    delta = (float(sign) * float(epsilon_m)) * np.asarray(direction, dtype=np.float64)
    phi = np.asarray(parent.phi.astype(np.float64) + delta, dtype=np.float32)
    # Preserve every constrained node byte-for-byte, even if a future
    # direction generator accidentally leaves a subnormal outside its mask.
    constrained = ~_active_mask(parent)
    phi[constrained] = parent.phi[constrained]
    child = SDFDesignState.create(
        phi=phi,
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
    actual_delta = np.abs(child.phi.astype(np.float64) - parent.phi.astype(np.float64))
    if float(actual_delta.max(initial=0.0)) > epsilon_m + FLOAT32_PHI_TOLERANCE_M:
        raise ValueError("float32 perturbation exceeds the registered epsilon tolerance")
    if not np.array_equal(child.phi[~parent.design_mask], parent.phi[~parent.design_mask]):
        raise ValueError("perturbation changed phi outside the canonical design mask")
    margin = zero_level_margin_m(child.phi, child.spacing_m)
    if not math.isfinite(margin) or margin < margin_gate_m:
        raise ValueError("perturbed SDF fails the registered interface-to-box margin gate")
    identity = {
        "parent_state_sha256": parent.state_sha256,
        "state_sha256": child.state_sha256,
        "epsilon_m": float(epsilon_m),
        "sign": int(sign),
        "phi_c_order_sha256": phi_sha256(child.phi, order="C"),
        "phi_fortran_order_sha256": phi_sha256(child.phi, order="F"),
        "shape": list(child.shape),
        "origin_m": list(child.origin_m),
        "spacing_m": float(child.spacing_m),
        "maximum_pointwise_change_m": float(actual_delta.max(initial=0.0)),
        "changed_node_count": int(np.count_nonzero(actual_delta)),
        "zero_level_margin_m": margin,
        "margin_gate_m": float(margin_gate_m),
        "outside_design_phi_identical": True,
        "masks_unchanged": all(
            np.array_equal(getattr(child, name), getattr(parent, name))
            for name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")
        ),
        "reinitialization_applied": False,
        "volume_correction_applied": False,
        "clipping_applied": False,
    }
    return child, identity


def validate_direction(state: SDFDesignState, direction: np.ndarray) -> None:
    """Validate one frozen direction without fabricating a direction set."""
    candidate = np.asarray(direction)
    if candidate.dtype != np.float32 or candidate.shape != state.shape:
        raise ValueError("direction must be float32 with the canonical point-grid shape")
    if not np.isfinite(candidate).all() or np.any(candidate[~_active_mask(state)] != 0.0):
        raise ValueError("direction is non-finite or nonzero at a constrained node")
    peak = float(np.max(np.abs(candidate), initial=0.0))
    if not math.isclose(peak, 1.0, rel_tol=0.0, abs_tol=2.0e-7):
        raise ValueError("direction max-absolute value is not one")


def registered_run_order() -> tuple[str, ...]:
    """Return three baselines interleaved with adjacent centered-FD pairs."""
    pair_ids = perturbation_case_ids()
    return (
        ("baseline_A",)
        + pair_ids[: 2 * 8]
        + ("baseline_B",)
        + pair_ids[2 * 8 :]
        + ("baseline_C",)
    )


def zero_level_margin_m(phi: np.ndarray, spacing_m: float) -> float:
    solid = np.asarray(phi) < 0.0
    if not solid.any():
        return math.inf if np.all(np.asarray(phi) > 0.0) else math.nan
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing_m for n in phi.shape]
    face_gap = np.minimum(
        np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]), gaps[2][None, None, :]
    )
    return float(np.min(face_gap[solid] + np.asarray(phi)[solid]))


def baseline_noise_floor(values: list[float] | tuple[float, ...]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (BASELINE_REPEATS,) or not np.isfinite(array).all():
        raise ValueError("baseline noise requires exactly three finite fresh responses")
    median = float(np.median(array))
    minimum = float(array.min())
    maximum = float(array.max())
    span = maximum - minimum
    floor = max(span, NOISE_RELATIVE_FLOOR * max(1.0, abs(median)))
    return {"median": median, "min": minimum, "max": maximum, "span": span, "noise_floor": floor}


def stationarity_drift(first_mean: float, second_mean: float, whole_mean: float) -> float:
    values = (first_mean, second_mean, whole_mean)
    if not all(math.isfinite(value) for value in values):
        return math.inf
    return abs(first_mean - second_mean) / max(abs(whole_mean), np.finfo(np.float64).eps)


def classify_direction(
    pairs: list[Mapping[str, float]],
    *,
    baseline_median: float,
    noise_floor: float,
    resolution_factor: float = RESOLUTION_FACTOR,
    plateau_tolerance: float = PLATEAU_RELATIVE_TOLERANCE,
) -> dict[str, Any]:
    """Resolve epsilon pairs and judge the three smallest resolved slopes."""

    if not math.isfinite(baseline_median) or not math.isfinite(noise_floor) or noise_floor <= 0.0:
        raise ValueError("baseline response and noise floor must be finite; floor must be positive")
    if (resolution_factor != RESOLUTION_FACTOR
            or plateau_tolerance != PLATEAU_RELATIVE_TOLERANCE):
        raise ValueError("FD resolution and plateau thresholds are immutable registered values")
    supplied_eps = [float(pair.get("epsilon_m", math.nan)) for pair in pairs]
    if (len(supplied_eps) != len(EPSILON_LADDER_M)
            or any(not math.isfinite(value) for value in supplied_eps)
            or sorted(supplied_eps) != list(EPSILON_LADDER_M)):
        raise ValueError("direction classification requires the exact registered epsilon ladder")
    rows = []
    seen = set()
    for pair in sorted(pairs, key=lambda item: float(item["epsilon_m"])):
        epsilon = float(pair["epsilon_m"])
        plus, minus = float(pair["plus_response"]), float(pair["minus_response"])
        if epsilon <= 0.0 or epsilon in seen or not all(map(math.isfinite, (plus, minus))):
            raise ValueError("FD pair epsilon must be unique/positive and responses finite")
        seen.add(epsilon)
        signal = abs(plus - minus)
        derivative = (plus - minus) / (2.0 * epsilon)
        even = plus + minus - 2.0 * baseline_median
        rows.append({
            "epsilon_m": epsilon,
            "plus_response": plus,
            "minus_response": minus,
            "pair_signal": signal,
            "resolved": signal >= resolution_factor * noise_floor,
            "directional_derivative": derivative,
            "even_nonlinearity": even,
            "even_to_odd_ratio": abs(even) / max(signal, noise_floor),
        })
    resolved = [row for row in rows if row["resolved"]]
    plateau = resolved[:3]
    enough = len(plateau) == 3
    reference = float(np.median([row["directional_derivative"] for row in plateau])) if enough else None
    noise_equivalent = max(noise_floor / row["epsilon_m"] for row in plateau) if enough else None
    normalizer = max(abs(reference), noise_equivalent) if enough else None
    for row in plateau:
        row["plateau_relative_deviation"] = abs(row["directional_derivative"] - reference) / normalizer
        row["directional_noise_equivalent"] = noise_equivalent
    signs = [int(math.copysign(1, row["directional_derivative"]))
             if row["directional_derivative"] != 0.0 else 0 for row in plateau]
    sign_stable = enough and signs[0] != 0 and len(set(signs)) == 1
    deviations = [row["plateau_relative_deviation"] for row in plateau]
    plateau_pass = enough and sign_stable and all(value <= plateau_tolerance for value in deviations)
    return {
        "all_epsilons": rows,
        "resolved_epsilon_m": [row["epsilon_m"] for row in resolved],
        "resolved_count": len(resolved),
        "plateau_epsilon_m": [row["epsilon_m"] for row in plateau],
        "minimum_resolved_count": 3,
        "reference_directional_derivative": reference,
        "directional_noise_equivalent": noise_equivalent,
        "plateau_relative_tolerance": plateau_tolerance,
        "plateau_max_relative_deviation": max(deviations) if deviations else None,
        "plateau_signs": signs,
        "sign_stable": sign_stable,
        "plateau_pass": plateau_pass,
    }


@dataclass(frozen=True)
class DirectionalFDRequest:
    """A scalar directional-derivative request, not a field-gradient request."""

    parent_state_sha256: str
    response_ids: tuple[str, ...]
    direction_ids: tuple[str, ...]
    epsilon_ladder_m: tuple[float, ...]
    backend_identity: str
    flow_case_id: str = "flow_16"

    def __post_init__(self) -> None:
        validate_sha256_hex(self.parent_state_sha256, field_name="parent_state_sha256")
        if self.response_ids != PRIMITIVE_RESPONSES:
            raise ValueError("directional FD primary responses must be primitive drag and downforce")
        if self.direction_ids != DIRECTION_IDS:
            raise ValueError("direction ids do not match the registered three-direction contract")
        if self.epsilon_ladder_m != EPSILON_LADDER_M:
            raise ValueError("epsilon ladder differs from the registered flow_16 contract")
        if not self.backend_identity.strip() or self.flow_case_id != "flow_16":
            raise ValueError("backend identity and flow_16 case are required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "sdf_directional_fd_request",
            "parent_state_sha256": self.parent_state_sha256,
            "response_ids": list(self.response_ids),
            "direction_ids": list(self.direction_ids),
            "epsilon_ladder_m": list(self.epsilon_ladder_m),
            "backend_identity": self.backend_identity,
            "flow_case_id": self.flow_case_id,
        }

    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


@dataclass(frozen=True)
class DirectionalFDEvaluation:
    """Host-verified primitive directional derivatives and their evidence links."""

    request: DirectionalFDRequest
    direction_sha256: Mapping[str, str]
    raw_run_sha256: Mapping[str, str]
    baseline_responses: Mapping[str, Mapping[str, float]]
    direction_results: Mapping[str, Mapping[str, Any]]
    backend_fingerprint_sha256: str
    evidence_sha256: Mapping[str, str]
    qualified: bool = False

    def __post_init__(self) -> None:
        validate_sha256_hex(self.backend_fingerprint_sha256,
                            field_name="backend_fingerprint_sha256")
        if set(self.direction_sha256) != set(self.request.direction_ids):
            raise ValueError("direction hashes do not match the request")
        for name, digest in self.direction_sha256.items():
            validate_sha256_hex(digest, field_name=f"direction_sha256[{name}]")
        expected_runs = {"baseline_A", "baseline_B", "baseline_C"}
        expected_runs.update(perturbation_case_ids())
        if set(self.raw_run_sha256) != expected_runs:
            raise ValueError("raw run hashes must bind the exact 33-run contract")
        for name, digest in self.raw_run_sha256.items():
            validate_sha256_hex(digest, field_name=f"raw_run_sha256[{name}]")
        if set(self.baseline_responses) != set(self.request.response_ids):
            raise ValueError("baseline responses must contain exactly the primitive response IDs")
        for response, summary in self.baseline_responses.items():
            if (set(summary) != {"median", "min", "max", "span", "noise_floor"}
                    or not all(math.isfinite(float(value)) for value in summary.values())
                    or summary["noise_floor"] <= 0.0):
                raise ValueError(f"baseline noise summary is incomplete/invalid: {response}")
        expected_direction_results = set(self.request.direction_ids)
        if set(self.direction_results) != expected_direction_results:
            raise ValueError("direction results must contain exactly the registered direction IDs")
        for direction_id, result in self.direction_results.items():
            if set(result) != set(self.request.response_ids):
                raise ValueError(f"direction response results are incomplete: {direction_id}")
            if any(result[response].get("plateau_pass") is not True
                   for response in self.request.response_ids):
                if self.qualified:
                    raise ValueError("qualified evaluation has a failing directional plateau")
        for name, digest in self.evidence_sha256.items():
            validate_sha256_hex(digest, field_name=f"evidence_sha256[{name}]")
        if self.qualified and not self.evidence_sha256:
            raise ValueError("qualified evaluation requires linked immutable evidence hashes")
        if not isinstance(self.qualified, bool):
            raise ValueError("qualified must be a bool")
        canonical_json_sha256({"baseline_responses": dict(self.baseline_responses),
                               "direction_results": dict(self.direction_results)})

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "sdf_directional_fd_evaluation",
            "request": self.request.to_dict(),
            "request_sha256": self.request.sha256(),
            "parent_state_sha256": self.request.parent_state_sha256,
            "response_ids": list(self.request.response_ids),
            "direction_sha256": dict(self.direction_sha256),
            "epsilon_ladder_m": list(self.request.epsilon_ladder_m),
            "backend_identity": self.request.backend_identity,
            "backend_fingerprint_sha256": self.backend_fingerprint_sha256,
            "raw_run_sha256": dict(self.raw_run_sha256),
            "baseline_responses": dict(self.baseline_responses),
            "direction_results": dict(self.direction_results),
            "evidence_sha256": dict(self.evidence_sha256),
            "qualified": bool(self.qualified),
        }

    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


__all__ = [
    "BASELINE_REPEATS", "DIRECTION_IDS", "EPSILON_LADDER_M", "FILTER_KERNEL",
    "FLOAT32_PHI_TOLERANCE_M", "NOISE_RELATIVE_FLOOR", "PLATEAU_RELATIVE_TOLERANCE",
    "RESOLUTION_FACTOR", "SDF_MARGIN_GATE_M",
    "STATIONARITY_RELATIVE_DRIFT_MAX", "DirectionalFDEvaluation", "DirectionalFDRequest",
    "baseline_noise_floor", "classify_direction", "direction_sha256", "generate_directions",
    "interface_taper", "perturbed_state", "phi_sha256", "sha256_bytes",
    "perturbation_case_id", "perturbation_case_ids", "registered_run_order",
    "stationarity_drift", "validate_direction",
    "validate_directions", "zero_level_margin_m",
]
