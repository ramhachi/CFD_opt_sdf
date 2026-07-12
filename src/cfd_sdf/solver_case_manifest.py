"""Pure ProblemSpec-to-OpenFOAM compile planning and manifest serialization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from math import isfinite, sqrt
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from .problem_spec import ProblemSpec, problem_spec_sha256


SOLVER_CASE_MANIFEST_SCHEMA_VERSION = 1
SOLVER_PROFILE = "openfoam_fixed_grid_incompressible_v1"
_SUPPORTED_BOUNDARY_KINDS = {
    "freestream",
    "pressure_outlet",
    "symmetry",
    "stationary_wall",
    "moving_wall",
}
_PATCH_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class SolverFlowCasePlan:
    flow_case_id: str
    case_directory_name: str
    requested: Mapping[str, Any]
    generated: Mapping[str, Any]
    supported_response_ids: tuple[str, ...]
    unsupported: tuple[str, ...]


@dataclass(frozen=True)
class SolverCaseManifest:
    problem_id: str
    problem_spec_sha256: str
    solver_profile: str
    flow_cases: tuple[SolverFlowCasePlan, ...]
    compile_ready: bool
    unsupported: tuple[str, ...]
    schema_version: int = SOLVER_CASE_MANIFEST_SCHEMA_VERSION
    kind: str = "openfoam_solver_case_manifest"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "problem_id": self.problem_id,
            "problem_spec_sha256": self.problem_spec_sha256,
            "solver_profile": self.solver_profile,
            "compile_ready": self.compile_ready,
            "unsupported": list(self.unsupported),
            "flow_cases": [
                {
                    "flow_case_id": plan.flow_case_id,
                    "case_directory_name": plan.case_directory_name,
                    "requested": _json_copy(plan.requested),
                    "generated": _json_copy(plan.generated),
                    "supported_response_ids": list(plan.supported_response_ids),
                    "unsupported": list(plan.unsupported),
                }
                for plan in self.flow_cases
            ],
        }


def build_openfoam_solver_case_manifest(
    spec: ProblemSpec,
    *,
    available_patch_ids: Sequence[str] | None = None,
) -> SolverCaseManifest:
    """Build a deterministic, non-writing OpenFOAM compile plan."""

    global_unsupported: list[str] = []
    if not spec.migration.execution_ready:
        global_unsupported.append("problem_spec_not_execution_ready")
    if spec.grid.kind != "uniform_cartesian":
        global_unsupported.append(f"unsupported_grid_kind:{spec.grid.kind}")

    available_patches: tuple[str, ...] | None = None
    if available_patch_ids is not None:
        available_patches = tuple(str(value) for value in available_patch_ids)
        if len(set(available_patches)) != len(available_patches):
            global_unsupported.append("duplicate_available_patch_id")
        for patch_id in available_patches:
            if _PATCH_ID_PATTERN.fullmatch(patch_id) is None:
                global_unsupported.append(f"unsafe_available_patch_id:{patch_id}")

    plans = tuple(
        _build_flow_case_plan(spec, case, available_patches)
        for case in spec.flow_cases
    )
    compile_ready = not global_unsupported and all(not plan.unsupported for plan in plans)
    return SolverCaseManifest(
        problem_id=spec.problem_id,
        problem_spec_sha256=problem_spec_sha256(spec),
        solver_profile=SOLVER_PROFILE,
        flow_cases=plans,
        compile_ready=compile_ready,
        unsupported=tuple(global_unsupported),
    )


def write_openfoam_solver_case_manifest(
    manifest: SolverCaseManifest, path: str | Path
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            manifest.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return target


def _build_flow_case_plan(
    spec: ProblemSpec,
    case: Any,
    available_patch_ids: tuple[str, ...] | None,
) -> SolverFlowCasePlan:
    unsupported: list[str] = []
    velocity = tuple(float(value) for value in case.freestream_velocity_mps)
    speed = sqrt(sum(value * value for value in velocity))
    nu = case.fluid.dynamic_viscosity_pa_s / case.fluid.density_kg_m3

    if case.fluid.model != "incompressible_newtonian":
        unsupported.append(f"unsupported_fluid_model:{case.fluid.model}")

    turbulence_generated = _compile_turbulence(case, speed, unsupported)
    boundary_generated = _compile_boundaries(case, available_patch_ids, unsupported)
    responses = tuple(response for response in spec.responses if response.flow_case_id == case.id)
    if not responses:
        unsupported.append("no_responses_for_flow_case")
    generated_responses: list[dict[str, Any]] = []
    supported_response_ids: list[str] = []
    for response in responses:
        if response.kind != "force":
            unsupported.append(f"unsupported_response_kind:{response.id}:{response.kind}")
            continue
        if response.direction is None:
            unsupported.append(f"force_response_missing_direction:{response.id}")
            continue
        if spec.reference_values is None or spec.reference_values.area_m2 is None:
            unsupported.append(f"force_response_missing_reference_area:{response.id}")
            continue
        generated_responses.append(
            {
                "response_id": response.id,
                "openfoam_objective_type": "porousDirectionalForce",
                "direction": response.direction,
                "Aref": spec.reference_values.area_m2,
                "UInf": speed,
            }
        )
        supported_response_ids.append(response.id)

    references = {
        "area_m2": None if spec.reference_values is None else spec.reference_values.area_m2,
        "length_m": None if spec.reference_values is None else spec.reference_values.length_m,
        "moment_center_m": None
        if spec.reference_values is None
        else spec.reference_values.moment_center_m,
    }
    requested = {
        "freestream_velocity_mps": velocity,
        "fluid": {
            "model": case.fluid.model,
            "density_kg_m3": case.fluid.density_kg_m3,
            "dynamic_viscosity_pa_s": case.fluid.dynamic_viscosity_pa_s,
        },
        "turbulence": None
        if case.turbulence is None
        else {"model": case.turbulence.model, **case.turbulence.options},
        "boundary_conditions": case.boundary_conditions,
        "motion_profiles": case.motion_profiles,
        "convergence_criteria": {
            "primal_final_residual_max": (
                case.convergence_criteria.primal_final_residual_max
            ),
            "normalized_mass_imbalance_max": (
                case.convergence_criteria.normalized_mass_imbalance_max
            ),
            "response_stationarity_window": (
                case.convergence_criteria.response_stationarity_window
            ),
            "response_relative_range_max": (
                case.convergence_criteria.response_relative_range_max
            ),
            "adjoint_final_residual_max": (
                case.convergence_criteria.adjoint_final_residual_max
            ),
        },
        "reference_values": references,
        "response_ids": tuple(response.id for response in responses),
    }
    generated = {
        "freestream_velocity_mps": velocity,
        "speed_mps": speed,
        "fluid": {
            "kinematic_viscosity_m2_s": nu,
        },
        "turbulence": turbulence_generated,
        "boundary_conditions": boundary_generated,
        "reference_values": references,
        "responses": tuple(generated_responses),
    }
    return SolverFlowCasePlan(
        flow_case_id=case.id,
        case_directory_name=f"flow_{case.id}",
        requested=_freeze(requested),
        generated=_freeze(generated),
        supported_response_ids=tuple(supported_response_ids),
        unsupported=tuple(unsupported),
    )


def _compile_turbulence(case: Any, speed: float, unsupported: list[str]) -> dict[str, Any]:
    if case.turbulence is None:
        unsupported.append("missing_turbulence_model")
        return {"model": None, "k_m2_s2": None, "omega_s_inv": None}
    model = case.turbulence.model
    if model == "laminar":
        return {"model": "laminar", "k_m2_s2": None, "omega_s_inv": None}
    if model != "k_omega_sst":
        unsupported.append(f"unsupported_turbulence_model:{model}")
        return {"model": model, "k_m2_s2": None, "omega_s_inv": None}

    intensity = _finite_number(case.turbulence.options.get("turbulence_intensity"))
    length_scale = _finite_number(case.turbulence.options.get("turbulence_length_scale_m"))
    if intensity is None or not (0.0 < intensity < 1.0):
        unsupported.append("invalid_turbulence_intensity")
    if length_scale is None or length_scale <= 0.0:
        unsupported.append("invalid_turbulence_length_scale_m")
    if intensity is None or not (0.0 < intensity < 1.0) or length_scale is None or length_scale <= 0.0:
        return {"model": model, "k_m2_s2": None, "omega_s_inv": None}
    k = 1.5 * (speed * intensity) ** 2
    omega = sqrt(k) / ((0.09 ** 0.25) * length_scale)
    return {
        "model": model,
        "turbulence_intensity": intensity,
        "turbulence_length_scale_m": length_scale,
        "k_m2_s2": k,
        "omega_s_inv": omega,
        "Cmu": 0.09,
    }


def _compile_boundaries(
    case: Any,
    available_patch_ids: tuple[str, ...] | None,
    unsupported: list[str],
) -> dict[str, Any]:
    raw_boundaries = case.boundary_conditions or {}
    generated: dict[str, Any] = {}
    declared_ids = {str(key) for key in raw_boundaries}
    for patch_id in sorted(declared_ids):
        if _PATCH_ID_PATTERN.fullmatch(patch_id) is None:
            unsupported.append(f"unsafe_boundary_patch_id:{patch_id}")
    if available_patch_ids is not None:
        available = set(available_patch_ids)
        for patch_id in sorted(declared_ids - available):
            unsupported.append(f"unknown_boundary_patch:{patch_id}")
        for patch_id in sorted(available - declared_ids):
            unsupported.append(f"undeclared_available_patch:{patch_id}")

    motion_coverages = _motion_coverages(case, raw_boundaries, unsupported)
    for patch_id, raw_kind in raw_boundaries.items():
        patch_id = str(patch_id)
        if not isinstance(raw_kind, str) or raw_kind not in _SUPPORTED_BOUNDARY_KINDS:
            unsupported.append(f"unsupported_boundary_condition:{patch_id}:{raw_kind}")
            continue
        if raw_kind == "freestream":
            generated[patch_id] = {
                "patch_type": "patch",
                "U": {"type": "fixedValue", "value": case.freestream_velocity_mps},
                "p": {"type": "zeroGradient"},
            }
        elif raw_kind == "pressure_outlet":
            generated[patch_id] = {
                "patch_type": "patch",
                "U": {"type": "zeroGradient"},
                "p": {"type": "fixedValue", "value": 0.0},
            }
        elif raw_kind == "symmetry":
            generated[patch_id] = {
                "patch_type": "symmetryPlane",
                "U": {"type": "symmetryPlane"},
                "p": {"type": "symmetryPlane"},
            }
        elif raw_kind == "stationary_wall":
            generated[patch_id] = {
                "patch_type": "wall",
                "U": {"type": "fixedValue", "value": (0.0, 0.0, 0.0)},
                "p": {"type": "zeroGradient"},
            }
        else:
            profiles = motion_coverages.get(patch_id, ())
            if len(profiles) != 1:
                unsupported.append(f"moving_wall_requires_exactly_one_motion_profile:{patch_id}")
                continue
            profile_id, velocity = profiles[0]
            generated[patch_id] = {
                "patch_type": "wall",
                "U": {"type": "fixedValue", "value": velocity},
                "p": {"type": "zeroGradient"},
                "motion_profile_id": profile_id,
            }
    return generated


def _motion_coverages(
    case: Any,
    boundaries: Mapping[str, Any],
    unsupported: list[str],
) -> dict[str, tuple[tuple[str, tuple[float, float, float]], ...]]:
    coverages: dict[str, list[tuple[str, tuple[float, float, float]]]] = {}
    for profile_id, raw_profile in case.motion_profiles.items():
        profile = dict(raw_profile)
        kind = profile.get("kind")
        if kind != "translation":
            unsupported.append(f"unsupported_motion_profile_kind:{profile_id}:{kind}")
            continue
        raw_boundary_ids = profile.get("boundary_ids")
        if (
            not isinstance(raw_boundary_ids, Sequence)
            or isinstance(raw_boundary_ids, (str, bytes, bytearray))
            or not raw_boundary_ids
        ):
            unsupported.append(f"invalid_motion_profile_boundary_ids:{profile_id}")
            continue
        boundary_ids = tuple(str(value) for value in raw_boundary_ids)
        if len(set(boundary_ids)) != len(boundary_ids):
            unsupported.append(f"duplicate_motion_profile_boundary_id:{profile_id}")
            continue
        velocity = _vector3(profile.get("velocity_mps"))
        if velocity is None:
            unsupported.append(f"invalid_motion_profile_velocity_mps:{profile_id}")
            continue
        for boundary_id in boundary_ids:
            if boundary_id not in boundaries:
                unsupported.append(f"unknown_motion_profile_boundary:{profile_id}:{boundary_id}")
                continue
            if boundaries[boundary_id] != "moving_wall":
                unsupported.append(f"motion_profile_boundary_not_moving_wall:{profile_id}:{boundary_id}")
                continue
            coverages.setdefault(boundary_id, []).append((str(profile_id), velocity))
    return {key: tuple(values) for key, values in coverages.items()}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _vector3(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 3:
        return None
    converted = tuple(_finite_number(component) for component in value)
    if any(component is None for component in converted):
        return None
    return (float(converted[0]), float(converted[1]), float(converted[2]))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value


__all__ = [
    "SOLVER_CASE_MANIFEST_SCHEMA_VERSION",
    "SolverCaseManifest",
    "SolverFlowCasePlan",
    "build_openfoam_solver_case_manifest",
    "write_openfoam_solver_case_manifest",
]
