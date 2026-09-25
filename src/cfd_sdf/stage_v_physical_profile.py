"""Numerical qualification gates for one Stage V physical-profile run.

The profile contract is registered before OpenFOAM is started.  This module
only parses solver output and applies the already registered numerical rules;
it does not infer tolerances from the observed run.  Missing or ambiguous
fields fail closed.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


# The mesh, residual, and force rules are copied into the immutable manifest by
# the registration script.  Keep the values here in one place so the runner
# and its unit tests use exactly the same contract.
STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1: dict[str, Any] = {
    "profile_id": "stage_v_physical_profile_qualification_v1",
    "solver": {
        "requires_residual_control_message": True,
        "final_residual_max": {"p": 1.0e-5, "Ux": 1.0e-6, "Uy": 1.0e-6, "Uz": 1.0e-6},
    },
    "mass_conservation": {
        "normalized_mass_imbalance_max": 1.0e-4,
        "denominator": "0.5*sum(abs(phi) over every boundary face)",
    },
    "moving_ground": {
        "target_velocity_mps": [1.0, 0.0, 0.0],
        "max_velocity_component_error_mps": 1.0e-8,
        "max_normal_flux_abs": 1.0e-8,
        "patch": "bottom",
    },
    "candidate_wall": {
        "max_normal_flux_abs": 1.0e-8,
        "patch": "design_candidate",
    },
    "upstream_velocity": {
        "location": "inlet boundary-face mean (upstream outer boundary proxy)",
        "target_velocity_mps": [1.0, 0.0, 0.0],
        "relative_l2_error_max": 5.0e-2,
        "minimum_faces": 1,
    },
    "outer_boundary": {
        "patches": ["inlet", "outlet", "sideMin", "sideMax", "top"],
        "backflow_ratio_max": 5.0e-2,
        "pressure_face_max_abs_normalized": 5.0e-2,
        "pressure_normalization": "U_inf^2 (kinematic p; rho=1 in the registered case)",
        "minimum_faces": 1,
    },
}


_NUMBER = r"[-+0-9.eE]+"


def _numeric_time(case_dir: Path) -> Path | None:
    times = [path for path in case_dir.iterdir() if path.is_dir() and path.name.isdigit()]
    return max(times, key=lambda path: int(path.name)) if times else None


def _boundary_blocks(text: str) -> dict[str, str]:
    """Extract top-level boundaryField patch blocks without parsing OpenFOAM dictionaries."""

    anchor = text.find("boundaryField")
    if anchor < 0:
        raise ValueError("boundaryField is missing")
    lines = text[anchor:].splitlines()
    opened = False
    depth = 0
    current: str | None = None
    block: list[str] = []
    pending_name: str | None = None
    result: dict[str, str] = {}
    for line in lines:
        if not opened:
            if "{" in line:
                opened = True
                depth = line.count("{") - line.count("}")
            continue
        if current is None and depth == 1:
            match = re.match(r"^\s*(\"[^\"]+\"|[A-Za-z0-9_.+-]+)\s*\{", line)
            if match:
                current = match.group(1).strip('"')
                block = [line]
            elif pending_name is None:
                name_match = re.match(r"^\s*(\"[^\"]+\"|[A-Za-z0-9_.+-]+)\s*$", line)
                if name_match:
                    pending_name = name_match.group(1).strip('"')
            elif line.strip() == "{":
                current = pending_name
                pending_name = None
                block = [current + " {", line]
            else:
                pending_name = None
        elif current is not None:
            block.append(line)
        delta = line.count("{") - line.count("}")
        if current is not None and depth + delta == 1:
            result[current] = "\n".join(block)
            current = None
            block = []
        depth += delta
        if opened and depth <= 0:
            break
    if not result:
        raise ValueError("boundaryField contains no patch blocks")
    return result


def _field_values(body: str, kind: str) -> list[float] | list[tuple[float, float, float]]:
    if kind == "scalar":
        list_match = re.search(
            rf"nonuniform\s+List<scalar>\s+(\d+)\s*\(\s*(.*?)\s*\)\s*;",
            body,
            re.DOTALL,
        )
        if list_match:
            count = int(list_match.group(1))
            values = [float(value) for value in re.findall(_NUMBER, list_match.group(2))]
            if len(values) != count:
                raise ValueError(f"scalar list count mismatch: {len(values)} != {count}")
            return values
        uniform_match = re.search(rf"\bvalue\s+uniform\s+({_NUMBER})\s*;", body)
        if uniform_match is None:
            uniform_match = re.search(rf"\buniform\s+({_NUMBER})\s*;", body)
        if uniform_match is None:
            raise ValueError("scalar patch value is missing")
        return [float(uniform_match.group(1))]

    if kind == "vector":
        list_match = re.search(
            r"nonuniform\s+List<vector>\s+(\d+)\s*\(\s*(.*?)\s*\)\s*;",
            body,
            re.DOTALL,
        )
        if list_match:
            count = int(list_match.group(1))
            values = [
                tuple(float(component) for component in match)
                for match in re.findall(
                    rf"\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)",
                    list_match.group(2),
                )
            ]
            if len(values) != count:
                raise ValueError(f"vector list count mismatch: {len(values)} != {count}")
            return values
        uniform_match = re.search(
            rf"\bvalue\s+uniform\s*\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)\s*;",
            body,
        )
        if uniform_match is None:
            uniform_match = re.search(
                rf"\buniform\s*\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)\s*;",
                body,
            )
        if uniform_match is None:
            raise ValueError("vector patch value is missing")
        return [tuple(float(component) for component in uniform_match.groups())]
    raise ValueError(f"unsupported field kind: {kind}")


def read_boundary_field(path: Path, *, kind: str) -> dict[str, dict[str, Any]]:
    """Read final-time patch values and retain all faces for fail-closed metrics."""

    blocks = _boundary_blocks(path.read_text(encoding="utf-8", errors="ignore"))
    result: dict[str, dict[str, Any]] = {}
    for name, body in blocks.items():
        type_match = re.search(r"(?m)^\s*type\s+(\S+)\s*;", body)
        if type_match is None:
            raise ValueError(f"field type is missing for patch {name}")
        try:
            values = _field_values(body, kind)
            count = len(values)
            value_error = None
        except ValueError as exc:
            # zeroGradient/noSlip/symmetry patches may legitimately omit a
            # stored boundary value.  The caller decides which patches are
            # required for a particular metric and fails closed there.
            values = None
            count = 0
            value_error = str(exc)
        result[name] = {
            "type": type_match.group(1),
            "values": values,
            "count": count,
            "value_error": value_error,
        }
    return result


def _finite(values: Sequence[float]) -> bool:
    return all(math.isfinite(value) for value in values)


def _vector_mean(values: Sequence[tuple[float, float, float]]) -> tuple[float, float, float]:
    if not values:
        raise ValueError("empty vector patch")
    return tuple(sum(value[index] for value in values) / len(values) for index in range(3))


def _vector_max_error(values: Sequence[tuple[float, float, float]], target: Sequence[float]) -> float:
    if not values:
        raise ValueError("empty vector patch")
    return max(abs(value[index] - target[index]) for value in values for index in range(3))


def _scalar_stats(values: Sequence[float]) -> dict[str, float]:
    if not values or not _finite(values):
        raise ValueError("empty or non-finite scalar patch")
    return {
        "mean": float(sum(values) / len(values)),
        "mean_abs": float(sum(abs(value) for value in values) / len(values)),
        "max_abs": float(max(abs(value) for value in values)),
        "sum": float(sum(values)),
        "negative_sum_abs": float(sum(-value for value in values if value < 0.0)),
        "positive_sum": float(sum(value for value in values if value > 0.0)),
        "count": float(len(values)),
    }


def evaluate_boundary_metrics(
    case_dir: Path,
    *,
    freestream_velocity_mps: Sequence[float] = (1.0, 0.0, 0.0),
    profile: Mapping[str, Any] = STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1,
) -> dict[str, Any]:
    """Evaluate mass, wall, upstream, backflow, and pressure gates from final fields."""

    reasons: list[str] = []
    latest = _numeric_time(case_dir)
    if latest is None:
        return {"status": "fail", "qualified": False, "reasons": ["no_numeric_solver_time"]}
    try:
        phi = read_boundary_field(latest / "phi", kind="scalar")
        velocity = read_boundary_field(latest / "U", kind="vector")
        pressure = read_boundary_field(latest / "p", kind="scalar")
        required = {"inlet", "outlet", "sideMin", "sideMax", "top", "bottom", "design_candidate"}
        for name in required:
            if name not in phi:
                raise ValueError(f"required patch missing from final fields: {name}")
        for name in ("inlet", "bottom"):
            if name not in velocity or velocity[name]["values"] is None:
                raise ValueError(f"required velocity values missing from final fields: {name}")
        for name in profile["outer_boundary"]["patches"]:
            if name not in pressure or pressure[name]["values"] is None:
                raise ValueError(f"required pressure values missing from final fields: {name}")

        phi_stats = {name: _scalar_stats(item["values"]) for name, item in phi.items()}
        total_signed = sum(stats["sum"] for stats in phi_stats.values())
        total_abs = sum(sum(abs(value) for value in item["values"]) for item in phi.values())
        denominator = max(0.5 * total_abs, 1.0e-30)
        normalized_imbalance = abs(total_signed) / denominator

        target = tuple(float(value) for value in freestream_velocity_mps)
        ground_error = _vector_max_error(velocity["bottom"]["values"], profile["moving_ground"]["target_velocity_mps"])
        ground_phi_max = phi_stats["bottom"]["max_abs"]
        candidate_phi_max = phi_stats["design_candidate"]["max_abs"]

        inlet_mean = _vector_mean(velocity["inlet"]["values"])
        speed_scale = max(math.sqrt(sum(value * value for value in target)), 1.0e-30)
        upstream_error = math.sqrt(sum((inlet_mean[i] - target[i]) ** 2 for i in range(3))) / speed_scale
        throughput = max(abs(phi_stats["inlet"]["sum"]), 1.0e-30)
        backflow_ratio = {
            name: phi_stats[name]["negative_sum_abs"] / throughput
            for name in profile["outer_boundary"]["patches"]
            if name != "inlet"
        }
        inlet_outflow_ratio = phi_stats["inlet"]["positive_sum"] / throughput
        p_scale = speed_scale * speed_scale
        pressure_disturbance = {
            name: {
                "mean_abs_normalized": _scalar_stats(pressure[name]["values"])["mean_abs"] / p_scale,
                "max_abs_normalized": _scalar_stats(pressure[name]["values"])["max_abs"] / p_scale,
            }
            for name in profile["outer_boundary"]["patches"]
        }

        gates = {
            "global_mass_conservation": {
                "status": "pass" if normalized_imbalance <= profile["mass_conservation"]["normalized_mass_imbalance_max"] else "fail",
                "normalized_mass_imbalance": normalized_imbalance,
                "threshold": profile["mass_conservation"]["normalized_mass_imbalance_max"],
                "total_signed_flux": total_signed,
                "total_absolute_flux": total_abs,
                "latest_time": latest.name,
            },
            "moving_ground_velocity_and_zero_normal_flux": {
                "status": "pass"
                if ground_error <= profile["moving_ground"]["max_velocity_component_error_mps"]
                and ground_phi_max <= profile["moving_ground"]["max_normal_flux_abs"]
                else "fail",
                "ground_velocity_max_component_error_mps": ground_error,
                "ground_velocity_threshold_mps": profile["moving_ground"]["max_velocity_component_error_mps"],
                "ground_normal_flux_max_abs": ground_phi_max,
                "ground_normal_flux_threshold": profile["moving_ground"]["max_normal_flux_abs"],
            },
            "candidate_zero_normal_flux": {
                "status": "pass" if candidate_phi_max <= profile["candidate_wall"]["max_normal_flux_abs"] else "fail",
                "candidate_normal_flux_max_abs": candidate_phi_max,
                "candidate_normal_flux_threshold": profile["candidate_wall"]["max_normal_flux_abs"],
            },
            "near_candidate_upstream_velocity": {
                "status": "pass"
                if upstream_error <= profile["upstream_velocity"]["relative_l2_error_max"]
                else "fail",
                "location": profile["upstream_velocity"]["location"],
                "face_mean_velocity_mps": list(inlet_mean),
                "relative_l2_error": upstream_error,
                "threshold": profile["upstream_velocity"]["relative_l2_error_max"],
                "face_count": velocity["inlet"]["count"],
            },
            "outer_patch_backflow_and_pressure_disturbance": {
                "status": "pass"
                if inlet_outflow_ratio <= profile["outer_boundary"]["backflow_ratio_max"]
                and all(value <= profile["outer_boundary"]["backflow_ratio_max"] for value in backflow_ratio.values())
                and all(
                    value["max_abs_normalized"] <= profile["outer_boundary"]["pressure_face_max_abs_normalized"]
                    for value in pressure_disturbance.values()
                )
                else "fail",
                "throughput_reference_abs_inlet_flux": throughput,
                "inlet_outflow_ratio": inlet_outflow_ratio,
                "backflow_ratio_by_patch": backflow_ratio,
                "backflow_ratio_threshold": profile["outer_boundary"]["backflow_ratio_max"],
                "pressure_disturbance_by_patch": pressure_disturbance,
                "pressure_disturbance_threshold": profile["outer_boundary"]["pressure_face_max_abs_normalized"],
                "pressure_normalization": profile["outer_boundary"]["pressure_normalization"],
            },
        }
        reasons.extend(name for name, result in gates.items() if result["status"] != "pass")
        return {
            "status": "pass" if not reasons else "fail",
            "qualified": not reasons,
            "reasons": reasons,
            "latest_time": latest.name,
            "patch_counts": {name: int(item["count"]) for name, item in phi.items()},
            "phi_by_patch": phi_stats,
            "gates": gates,
        }
    except (OSError, ValueError, KeyError) as exc:
        return {
            "status": "fail",
            "qualified": False,
            "reasons": ["boundary_measurement_error"],
            "measurement_error": str(exc),
            "latest_time": latest.name,
        }


def evaluate_solver_residual_gate(
    solver_qualification: Mapping[str, Any],
    profile: Mapping[str, Any] = STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1,
) -> dict[str, Any]:
    """Apply explicit final residual thresholds in addition to residualControl termination."""

    parsed = solver_qualification.get("solver", solver_qualification)
    residuals = parsed.get("final_residuals") or {}
    required_message = bool(profile["solver"]["requires_residual_control_message"])
    message_ok = parsed.get("residual_control_converged_at_iteration") is not None
    values: dict[str, Any] = {}
    reasons: list[str] = []
    for field, threshold in profile["solver"]["final_residual_max"].items():
        observed = residuals.get(field)
        ok = isinstance(observed, (int, float)) and math.isfinite(float(observed)) and float(observed) <= threshold
        values[field] = {"observed": observed, "threshold": threshold, "status": "pass" if ok else "fail"}
        if not ok:
            reasons.append(f"residual_{field}")
    if required_message and not message_ok:
        reasons.append("residual_control_message_missing")
    if not parsed.get("end_marker"):
        reasons.append("solver_end_marker_missing")
    return {
        "status": "pass" if not reasons else "fail",
        "qualified": not reasons,
        "reasons": reasons,
        "residual_control_message": message_ok,
        "final_residuals": values,
    }


__all__ = [
    "STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1",
    "evaluate_boundary_metrics",
    "evaluate_solver_residual_gate",
    "read_boundary_field",
]
