"""Versioned, solver-independent CFD optimization problem specifications."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from math import isfinite, sqrt
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

import yaml


PROBLEM_SPEC_SCHEMA_VERSION = 2
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
Vector3 = tuple[float, float, float]
_GEOMETRY_ROLES = {
    "fixed_solid",
    "initial_design",
    "design_domain",
    "forbidden_region",
    "root",
}
_CONNECTIVITY_MODES = {
    "disabled",
    "single_component",
    "root_connected",
    "required_root_groups",
    "bounded_component_count",
}
DEFAULT_PRIMAL_FINAL_RESIDUAL_MAX = 1.0e-6
DEFAULT_NORMALIZED_MASS_IMBALANCE_MAX = 1.0e-4
DEFAULT_RESPONSE_STATIONARITY_WINDOW = 20
DEFAULT_RESPONSE_RELATIVE_RANGE_MAX = 1.0e-3
DEFAULT_ADJOINT_FINAL_RESIDUAL_MAX = 1.0e-6


@dataclass(frozen=True)
class UnitsSpec:
    length: str
    time: str
    mass: str


@dataclass(frozen=True)
class BasisSpec:
    x: Vector3
    y: Vector3
    z: Vector3


@dataclass(frozen=True)
class CoordinateFrameSpec:
    id: str
    origin_m: Vector3
    basis: BasisSpec


@dataclass(frozen=True)
class GridSpec:
    kind: str
    voxel_size_m: float
    padding_m: float
    options: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class ReferenceValuesSpec:
    area_m2: float | None = None
    length_m: float | None = None
    moment_center_m: Vector3 | None = None


@dataclass(frozen=True)
class GeometryRegionSpec:
    id: str
    role: str
    file: Path


@dataclass(frozen=True)
class RootGroupSpec:
    id: str
    region_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConnectivityPolicySpec:
    mode: str
    required_root_group_ids: tuple[str, ...]
    max_components: int | None
    evaluate_eroded: bool


@dataclass(frozen=True)
class TopologyPolicySpec:
    root_groups: tuple[RootGroupSpec, ...]
    solid_connectivity: ConnectivityPolicySpec
    void_connectivity: ConnectivityPolicySpec
    minimum_solid_width_m: float | None
    minimum_void_width_m: float | None
    minimum_gap_m: float | None
    erosion_radius_m: float | None


@dataclass(frozen=True)
class FluidSpec:
    model: str
    density_kg_m3: float
    dynamic_viscosity_pa_s: float


@dataclass(frozen=True)
class TurbulenceSpec:
    model: str
    options: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class ConvergenceCriteriaSpec:
    primal_final_residual_max: float
    normalized_mass_imbalance_max: float
    response_stationarity_window: int
    response_relative_range_max: float
    adjoint_final_residual_max: float


@dataclass(frozen=True)
class FlowCaseSpec:
    id: str
    freestream_velocity_mps: Vector3
    fluid: FluidSpec
    turbulence: TurbulenceSpec | None
    boundary_conditions: Mapping[str, Any] | None
    motion_profiles: Mapping[str, Any]
    convergence_criteria: ConvergenceCriteriaSpec


@dataclass(frozen=True)
class ResponseSpec:
    id: str
    kind: str
    flow_case_id: str
    direction: Vector3 | None
    options: Mapping[str, Any]


@dataclass(frozen=True)
class WeightedTermSpec:
    coefficient: float
    flow_case_id: str
    response_id: str


@dataclass(frozen=True)
class ObjectiveSpec:
    id: str
    sense: str
    terms: tuple[WeightedTermSpec, ...]


@dataclass(frozen=True)
class ConstraintSpec:
    id: str
    relation: str
    limit: float
    terms: tuple[WeightedTermSpec, ...]


@dataclass(frozen=True)
class MigrationSpec:
    source_schema_version: int | None
    migrated: bool
    execution_ready: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProblemSpec:
    path: Path
    schema_version: int
    problem_id: str
    units: UnitsSpec
    coordinate_frame: CoordinateFrameSpec
    grid: GridSpec
    reference_values: ReferenceValuesSpec | None
    geometry_regions: tuple[GeometryRegionSpec, ...]
    flow_cases: tuple[FlowCaseSpec, ...]
    responses: tuple[ResponseSpec, ...]
    objectives: tuple[ObjectiveSpec, ...]
    constraints: tuple[ConstraintSpec, ...]
    topology_policy: TopologyPolicySpec
    migration: MigrationSpec

    @property
    def base_dir(self) -> Path:
        return self.path.parent

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.base_dir / candidate


def load_problem_spec(path: str | Path) -> ProblemSpec:
    """Load schema v2 YAML, migrating the legacy project schema when needed."""

    spec_path = Path(path).resolve()
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ValueError("Problem specification root must be a mapping")

    schema_version = raw.get("schema_version")
    if schema_version in (None, 1, "1"):
        spec = _migrate_legacy(spec_path, raw, schema_version)
    else:
        try:
            version = int(schema_version)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid schema_version: {schema_version!r}") from exc
        if version != PROBLEM_SPEC_SCHEMA_VERSION:
            raise ValueError(f"Unsupported problem schema_version: {schema_version!r}")
        spec = _load_v2(spec_path, raw)

    _validate_references(spec)
    return spec


def topology_constraint_ids(spec: ProblemSpec) -> tuple[str, ...]:
    """Return deterministic IDs for constraints implied by the topology policy."""

    policy = spec.topology_policy
    result: list[str] = []
    if policy.solid_connectivity.mode != "disabled":
        result.append("solid_connectivity_nominal")
        if policy.solid_connectivity.evaluate_eroded:
            result.append("solid_connectivity_eroded")
    if policy.void_connectivity.mode != "disabled":
        result.append("void_connectivity_nominal")
        if policy.void_connectivity.evaluate_eroded:
            result.append("void_connectivity_eroded")
    if policy.minimum_solid_width_m is not None:
        result.append("minimum_solid_width")
    if policy.minimum_void_width_m is not None:
        result.append("minimum_void_width")
    if policy.minimum_gap_m is not None:
        result.append("minimum_gap")
    return tuple(result)


def problem_spec_to_dict(spec: ProblemSpec) -> dict[str, Any]:
    """Return canonical problem content without source path or migration record."""

    references: dict[str, Any] | None = None
    if spec.reference_values is not None:
        references = {
            "area_m2": spec.reference_values.area_m2,
            "length_m": spec.reference_values.length_m,
            "moment_center_m": spec.reference_values.moment_center_m,
        }
    content = {
        "schema_version": spec.schema_version,
        "problem_id": spec.problem_id,
        "units": {
            "length": spec.units.length,
            "time": spec.units.time,
            "mass": spec.units.mass,
        },
        "coordinate_frame": {
            "id": spec.coordinate_frame.id,
            "origin_m": spec.coordinate_frame.origin_m,
            "basis": {
                "x": spec.coordinate_frame.basis.x,
                "y": spec.coordinate_frame.basis.y,
                "z": spec.coordinate_frame.basis.z,
            },
        },
        "grid": {
            "kind": spec.grid.kind,
            "voxel_size_m": spec.grid.voxel_size_m,
            "padding_m": spec.grid.padding_m,
            **spec.grid.options,
        },
        "reference_values": references,
        "geometry_regions": [
            {
                "id": region.id,
                "role": region.role,
                "file": region.file.as_posix(),
            }
            for region in spec.geometry_regions
        ],
        "flow_cases": [
            {
                "id": case.id,
                "freestream_velocity_mps": case.freestream_velocity_mps,
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
                "convergence_criteria": _convergence_criteria_to_dict(
                    case.convergence_criteria
                ),
            }
            for case in spec.flow_cases
        ],
        "responses": [
            {
                "id": response.id,
                "kind": response.kind,
                "flow_case_id": response.flow_case_id,
                "direction": response.direction,
                "options": response.options,
            }
            for response in spec.responses
        ],
        "objectives": [
            {
                "id": objective.id,
                "sense": objective.sense,
                "terms": [
                    {
                        "coefficient": term.coefficient,
                        "flow_case_id": term.flow_case_id,
                        "response_id": term.response_id,
                    }
                    for term in objective.terms
                ],
            }
            for objective in spec.objectives
        ],
        "constraints": [
            {
                "id": constraint.id,
                "relation": constraint.relation,
                "limit": constraint.limit,
                "terms": [
                    {
                        "coefficient": term.coefficient,
                        "flow_case_id": term.flow_case_id,
                        "response_id": term.response_id,
                    }
                    for term in constraint.terms
                ],
            }
            for constraint in spec.constraints
        ],
        "topology_policy": {
            "root_groups": [
                {"id": group.id, "region_ids": group.region_ids}
                for group in spec.topology_policy.root_groups
            ],
            "solid_connectivity": _connectivity_policy_to_dict(
                spec.topology_policy.solid_connectivity
            ),
            "void_connectivity": _connectivity_policy_to_dict(
                spec.topology_policy.void_connectivity
            ),
            "minimum_solid_width_m": spec.topology_policy.minimum_solid_width_m,
            "minimum_void_width_m": spec.topology_policy.minimum_void_width_m,
            "minimum_gap_m": spec.topology_policy.minimum_gap_m,
            "erosion_radius_m": spec.topology_policy.erosion_radius_m,
        },
    }
    return _json_safe(content)


def canonical_problem_spec_json(spec: ProblemSpec) -> str:
    """Serialize canonical problem content deterministically."""

    return json.dumps(
        problem_spec_to_dict(spec),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def problem_spec_sha256(spec: ProblemSpec) -> str:
    """Return the SHA-256 digest of canonical problem content."""

    return hashlib.sha256(canonical_problem_spec_json(spec).encode("utf-8")).hexdigest()


def write_problem_spec_snapshot(spec: ProblemSpec, path: str | Path) -> Path:
    """Write portable canonical content and migration provenance."""

    snapshot_path = Path(path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "kind": "cfd_optimization_problem_spec",
        "schema_version": PROBLEM_SPEC_SCHEMA_VERSION,
        "problem": problem_spec_to_dict(spec),
        "problem_spec_sha256": problem_spec_sha256(spec),
        "migration": {
            "source_schema_version": spec.migration.source_schema_version,
            "migrated": spec.migration.migrated,
            "execution_ready": spec.migration.execution_ready,
            "notes": list(spec.migration.notes),
        },
    }
    snapshot_path.write_text(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return snapshot_path


def _load_v2(path: Path, raw: Mapping[str, Any]) -> ProblemSpec:
    _reject_unknown_keys(
        raw,
        {
            "schema_version",
            "problem_id",
            "units",
            "coordinate_frame",
            "grid",
            "reference_values",
            "geometry_regions",
            "flow_cases",
            "responses",
            "objectives",
            "constraints",
            "topology_policy",
        },
        "problem specification",
    )
    units_raw = _mapping(raw, "units")
    _reject_unknown_keys(units_raw, {"length", "time", "mass"}, "units")
    units = UnitsSpec(
        length=_required_text(units_raw, "length", "units"),
        time=_required_text(units_raw, "time", "units"),
        mass=_required_text(units_raw, "mass", "units"),
    )
    if units != UnitsSpec(length="m", time="s", mass="kg"):
        raise ValueError("schema_version 2 requires SI base units: length=m, time=s, mass=kg")

    frame_raw = _mapping(raw, "coordinate_frame")
    _reject_unknown_keys(frame_raw, {"id", "origin_m", "basis"}, "coordinate_frame")
    basis_raw = _mapping(frame_raw, "basis", "coordinate_frame")
    _reject_unknown_keys(basis_raw, {"x", "y", "z"}, "coordinate_frame.basis")
    frame = CoordinateFrameSpec(
        id=_required_id(frame_raw, "id", "coordinate_frame"),
        origin_m=_vector3(frame_raw.get("origin_m"), "coordinate_frame.origin_m"),
        basis=BasisSpec(
            x=_nonzero_vector(basis_raw.get("x"), "coordinate_frame.basis.x"),
            y=_nonzero_vector(basis_raw.get("y"), "coordinate_frame.basis.y"),
            z=_nonzero_vector(basis_raw.get("z"), "coordinate_frame.basis.z"),
        ),
    )
    _validate_basis(frame.basis)

    grid_raw = _mapping(raw, "grid")
    grid_kind = _required_text(grid_raw, "kind", "grid")
    if grid_kind not in {"uniform_cartesian", "octree_amr"}:
        raise ValueError("grid.kind must be 'uniform_cartesian' or 'octree_amr'")
    grid = GridSpec(
        kind=grid_kind,
        voxel_size_m=_positive_float(grid_raw.get("voxel_size_m"), "grid.voxel_size_m"),
        padding_m=_nonnegative_float(grid_raw.get("padding_m"), "grid.padding_m"),
        options=_freeze_mapping(
            {key: value for key, value in grid_raw.items() if key not in {"kind", "voxel_size_m", "padding_m"}}
        ),
    )

    reference_values = _load_reference_values(raw.get("reference_values"))
    geometry_regions = tuple(
        _load_geometry_region(item, index)
        for index, item in enumerate(_sequence(raw, "geometry_regions"))
    )
    flow_cases = tuple(_load_flow_case(item, index) for index, item in enumerate(_sequence(raw, "flow_cases")))
    responses = tuple(_load_response(item, index) for index, item in enumerate(_sequence(raw, "responses")))
    objectives = tuple(_load_objective(item, index) for index, item in enumerate(_sequence(raw, "objectives")))
    constraints = tuple(_load_constraint(item, index) for index, item in enumerate(_sequence(raw, "constraints")))
    _require_nonempty("flow_cases", flow_cases)
    _require_nonempty("responses", responses)
    _require_nonempty("objectives", objectives)

    topology_policy = _load_topology_policy(
        _mapping(raw, "topology_policy"), geometry_regions
    )

    return ProblemSpec(
        path=path,
        schema_version=PROBLEM_SPEC_SCHEMA_VERSION,
        problem_id=_required_id(raw, "problem_id", "problem specification"),
        units=units,
        coordinate_frame=frame,
        grid=grid,
        reference_values=reference_values,
        geometry_regions=geometry_regions,
        flow_cases=flow_cases,
        responses=responses,
        objectives=objectives,
        constraints=constraints,
        topology_policy=topology_policy,
        migration=MigrationSpec(
            source_schema_version=PROBLEM_SPEC_SCHEMA_VERSION,
            migrated=False,
            execution_ready=_is_v2_execution_ready(
                grid, reference_values, geometry_regions, flow_cases
            ),
        ),
    )


def _load_reference_values(value: Any) -> ReferenceValuesSpec | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("reference_values must be a mapping")
    _reject_unknown_keys(
        value,
        {"area_m2", "length_m", "moment_center_m"},
        "reference_values",
    )
    area = _optional_positive_float(value.get("area_m2"), "reference_values.area_m2")
    length = _optional_positive_float(value.get("length_m"), "reference_values.length_m")
    center = value.get("moment_center_m")
    return ReferenceValuesSpec(
        area_m2=area,
        length_m=length,
        moment_center_m=None if center is None else _vector3(center, "reference_values.moment_center_m"),
    )


def _load_geometry_region(value: Any, index: int) -> GeometryRegionSpec:
    context = f"geometry_regions[{index}]"
    item = _as_mapping(value, context)
    _reject_unknown_keys(item, {"id", "role", "file"}, context)
    role = _required_text(item, "role", context)
    if role not in _GEOMETRY_ROLES:
        raise ValueError(
            f"{context}.role must be one of {sorted(_GEOMETRY_ROLES)!r}"
        )
    file_value = item.get("file")
    if not isinstance(file_value, (str, Path)) or not str(file_value).strip():
        raise ValueError(f"{context}.file must be a non-empty path")
    file = Path(str(file_value).strip())
    if file.is_absolute():
        raise ValueError(f"{context}.file must be a relative path for a portable contract")
    if file.suffix.lower() != ".stl":
        raise ValueError(f"{context}.file must use the .stl extension")
    return GeometryRegionSpec(
        id=_required_id(item, "id", context),
        role=role,
        file=file,
    )


def _load_topology_policy(
    value: Mapping[str, Any],
    geometry_regions: tuple[GeometryRegionSpec, ...],
) -> TopologyPolicySpec:
    _reject_unknown_keys(
        value,
        {
            "root_groups",
            "solid_connectivity",
            "void_connectivity",
            "minimum_solid_width_m",
            "minimum_void_width_m",
            "minimum_gap_m",
            "erosion_radius_m",
        },
        "topology_policy",
    )
    raw_groups = _sequence(value, "root_groups", "topology_policy")
    groups: list[RootGroupSpec] = []
    group_ids: set[str] = set()
    root_region_ids = {region.id for region in geometry_regions if region.role == "root"}
    all_region_ids = {region.id for region in geometry_regions}
    for index, raw_group in enumerate(raw_groups):
        context = f"topology_policy.root_groups[{index}]"
        item = _as_mapping(raw_group, context)
        _reject_unknown_keys(item, {"id", "region_ids"}, context)
        group_id = _required_id(item, "id", context)
        if group_id in group_ids:
            raise ValueError(f"Duplicate root group id: {group_id!r}")
        group_ids.add(group_id)
        region_ids = _required_unique_id_sequence(item, "region_ids", context)
        if not region_ids:
            raise ValueError(f"{context}.region_ids must not be empty")
        for region_id in region_ids:
            if region_id not in all_region_ids:
                raise ValueError(f"{context} references unknown geometry region {region_id!r}")
            if region_id not in root_region_ids:
                raise ValueError(f"{context} region {region_id!r} must have role='root'")
        groups.append(RootGroupSpec(group_id, region_ids))

    solid = _load_connectivity_policy(
        _mapping(value, "solid_connectivity", "topology_policy"),
        "topology_policy.solid_connectivity",
        group_ids,
    )
    void = _load_connectivity_policy(
        _mapping(value, "void_connectivity", "topology_policy"),
        "topology_policy.void_connectivity",
        group_ids,
    )
    minimum_solid_width_m = _optional_positive_float(
        value.get("minimum_solid_width_m"), "topology_policy.minimum_solid_width_m"
    )
    minimum_void_width_m = _optional_positive_float(
        value.get("minimum_void_width_m"), "topology_policy.minimum_void_width_m"
    )
    minimum_gap_m = _optional_positive_float(
        value.get("minimum_gap_m"), "topology_policy.minimum_gap_m"
    )
    erosion_radius_m = _optional_positive_float(
        value.get("erosion_radius_m"), "topology_policy.erosion_radius_m"
    )
    if (solid.evaluate_eroded or void.evaluate_eroded) and erosion_radius_m is None:
        raise ValueError(
            "topology_policy.erosion_radius_m is required when evaluate_eroded is true"
        )
    return TopologyPolicySpec(
        root_groups=tuple(groups),
        solid_connectivity=solid,
        void_connectivity=void,
        minimum_solid_width_m=minimum_solid_width_m,
        minimum_void_width_m=minimum_void_width_m,
        minimum_gap_m=minimum_gap_m,
        erosion_radius_m=erosion_radius_m,
    )


def _load_connectivity_policy(
    value: Mapping[str, Any], context: str, defined_group_ids: set[str]
) -> ConnectivityPolicySpec:
    _reject_unknown_keys(
        value,
        {"mode", "required_root_group_ids", "max_components", "evaluate_eroded"},
        context,
    )
    mode = _required_text(value, "mode", context)
    if mode not in _CONNECTIVITY_MODES:
        raise ValueError(f"{context}.mode must be one of {sorted(_CONNECTIVITY_MODES)!r}")
    required_ids = _required_unique_id_sequence(
        value, "required_root_group_ids", context
    )
    for group_id in required_ids:
        if group_id not in defined_group_ids:
            raise ValueError(f"{context} references unknown root group {group_id!r}")
    max_components = value.get("max_components")
    if max_components is not None:
        if isinstance(max_components, bool) or not isinstance(max_components, int) or max_components <= 0:
            raise ValueError(f"{context}.max_components must be a positive integer or null")
    evaluate_eroded = value.get("evaluate_eroded")
    if not isinstance(evaluate_eroded, bool):
        raise ValueError(f"{context}.evaluate_eroded must be a boolean")

    if mode == "disabled" and (required_ids or max_components is not None):
        raise ValueError(f"{context} disabled mode forbids root groups and max_components")
    if mode == "disabled" and evaluate_eroded:
        raise ValueError(f"{context} disabled mode requires evaluate_eroded=false")
    if mode == "single_component" and (required_ids or max_components not in {None, 1}):
        raise ValueError(
            f"{context} single_component mode forbids root groups and only allows max_components=1"
        )
    if mode in {"root_connected", "required_root_groups"} and not required_ids:
        raise ValueError(f"{context} {mode} mode requires required_root_group_ids")
    if mode == "bounded_component_count" and max_components is None:
        raise ValueError(f"{context} bounded_component_count mode requires max_components")
    return ConnectivityPolicySpec(mode, required_ids, max_components, evaluate_eroded)


def _connectivity_policy_to_dict(policy: ConnectivityPolicySpec) -> dict[str, Any]:
    return {
        "mode": policy.mode,
        "required_root_group_ids": policy.required_root_group_ids,
        "max_components": policy.max_components,
        "evaluate_eroded": policy.evaluate_eroded,
    }


def _empty_topology_policy() -> TopologyPolicySpec:
    disabled = ConnectivityPolicySpec("disabled", (), None, False)
    return TopologyPolicySpec((), disabled, disabled, None, None, None, None)


def _default_convergence_criteria() -> ConvergenceCriteriaSpec:
    return ConvergenceCriteriaSpec(
        primal_final_residual_max=DEFAULT_PRIMAL_FINAL_RESIDUAL_MAX,
        normalized_mass_imbalance_max=DEFAULT_NORMALIZED_MASS_IMBALANCE_MAX,
        response_stationarity_window=DEFAULT_RESPONSE_STATIONARITY_WINDOW,
        response_relative_range_max=DEFAULT_RESPONSE_RELATIVE_RANGE_MAX,
        adjoint_final_residual_max=DEFAULT_ADJOINT_FINAL_RESIDUAL_MAX,
    )


def _convergence_criteria_to_dict(
    criteria: ConvergenceCriteriaSpec,
) -> dict[str, float | int]:
    return {
        "primal_final_residual_max": criteria.primal_final_residual_max,
        "normalized_mass_imbalance_max": criteria.normalized_mass_imbalance_max,
        "response_stationarity_window": criteria.response_stationarity_window,
        "response_relative_range_max": criteria.response_relative_range_max,
        "adjoint_final_residual_max": criteria.adjoint_final_residual_max,
    }


def _load_convergence_criteria(
    value: Any, context: str
) -> ConvergenceCriteriaSpec:
    raw = _as_mapping(value, context)
    allowed = {
        "primal_final_residual_max",
        "normalized_mass_imbalance_max",
        "response_stationarity_window",
        "response_relative_range_max",
        "adjoint_final_residual_max",
    }
    _reject_unknown_keys(raw, allowed, context)
    defaults = _default_convergence_criteria()
    window = raw.get(
        "response_stationarity_window", defaults.response_stationarity_window
    )
    if isinstance(window, bool) or not isinstance(window, int):
        raise ValueError(f"{context}.response_stationarity_window must be an integer")
    if not 2 <= window <= 100_000:
        raise ValueError(
            f"{context}.response_stationarity_window must be between 2 and 100000"
        )

    def residual(name: str, default: float) -> float:
        value = raw.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{context}.{name} must be a number")
        result = _positive_float(value, f"{context}.{name}")
        if result > 1.0:
            raise ValueError(f"{context}.{name} must be at most 1")
        return result

    def ratio(name: str, default: float) -> float:
        value = raw.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{context}.{name} must be a number")
        result = _nonnegative_float(value, f"{context}.{name}")
        if result > 1.0:
            raise ValueError(f"{context}.{name} must be at most 1")
        return result

    return ConvergenceCriteriaSpec(
        primal_final_residual_max=residual(
            "primal_final_residual_max", defaults.primal_final_residual_max
        ),
        normalized_mass_imbalance_max=ratio(
            "normalized_mass_imbalance_max",
            defaults.normalized_mass_imbalance_max,
        ),
        response_stationarity_window=window,
        response_relative_range_max=ratio(
            "response_relative_range_max",
            defaults.response_relative_range_max,
        ),
        adjoint_final_residual_max=residual(
            "adjoint_final_residual_max", defaults.adjoint_final_residual_max
        ),
    )


def _load_flow_case(value: Any, index: int) -> FlowCaseSpec:
    context = f"flow_cases[{index}]"
    item = _as_mapping(value, context)
    _reject_unknown_keys(
        item,
        {
            "id",
            "freestream_velocity_mps",
            "fluid",
            "turbulence",
            "boundary_conditions",
            "motion_profiles",
            "convergence_criteria",
        },
        context,
    )
    fluid_raw = _mapping(item, "fluid", context)
    _reject_unknown_keys(
        fluid_raw,
        {"model", "density_kg_m3", "dynamic_viscosity_pa_s"},
        f"{context}.fluid",
    )
    turbulence_value = item.get("turbulence")
    turbulence: TurbulenceSpec | None = None
    if turbulence_value is not None:
        turbulence_raw = _as_mapping(turbulence_value, f"{context}.turbulence")
        turbulence = TurbulenceSpec(
            model=_required_text(turbulence_raw, "model", f"{context}.turbulence"),
            options=_freeze_mapping({key: val for key, val in turbulence_raw.items() if key != "model"}),
        )
    boundary_conditions = item.get("boundary_conditions")
    if boundary_conditions is not None and not isinstance(boundary_conditions, Mapping):
        raise ValueError(f"{context}.boundary_conditions must be a mapping or null")
    motion_profiles = _load_motion_profiles(item, context)
    return FlowCaseSpec(
        id=_required_id(item, "id", context),
        freestream_velocity_mps=_nonzero_vector(
            item.get("freestream_velocity_mps"), f"{context}.freestream_velocity_mps"
        ),
        fluid=FluidSpec(
            model=_required_text(fluid_raw, "model", f"{context}.fluid"),
            density_kg_m3=_positive_float(fluid_raw.get("density_kg_m3"), f"{context}.fluid.density_kg_m3"),
            dynamic_viscosity_pa_s=_positive_float(
                fluid_raw.get("dynamic_viscosity_pa_s"), f"{context}.fluid.dynamic_viscosity_pa_s"
            ),
        ),
        turbulence=turbulence,
        boundary_conditions=None if boundary_conditions is None else _freeze_mapping(boundary_conditions),
        motion_profiles=motion_profiles,
        convergence_criteria=(
            _load_convergence_criteria(
                item["convergence_criteria"], f"{context}.convergence_criteria"
            )
            if "convergence_criteria" in item
            else _default_convergence_criteria()
        ),
    )


def _load_motion_profiles(
    item: Mapping[str, Any], context: str
) -> Mapping[str, Any]:
    value = item["motion_profiles"] if "motion_profiles" in item else {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}.motion_profiles must be a mapping")
    profiles: dict[str, Any] = {}
    for key, raw_profile in value.items():
        if not isinstance(key, str) or _ID_PATTERN.fullmatch(key) is None:
            raise ValueError(
                f"{context}.motion_profiles key {key!r} must match ^[a-z][a-z0-9_]{{0,63}}$"
            )
        if not isinstance(raw_profile, Mapping):
            raise ValueError(f"{context}.motion_profiles.{key} must be a mapping")
        profiles[key] = raw_profile
    return _freeze_mapping(profiles)


def _load_response(value: Any, index: int) -> ResponseSpec:
    context = f"responses[{index}]"
    item = _as_mapping(value, context)
    _reject_unknown_keys(item, {"id", "kind", "flow_case_id", "direction", "options"}, context)
    kind = _required_text(item, "kind", context).lower()
    if kind not in {"force", "moment", "pressure_loss", "flow_rate", "plugin"}:
        raise ValueError(
            f"{context}.kind must be force, moment, pressure_loss, flow_rate, or plugin"
        )
    options_value = item["options"] if "options" in item else {}
    if not isinstance(options_value, Mapping):
        raise ValueError(f"{context}.options must be a mapping")
    options = _freeze_mapping(options_value)
    if kind in {"force", "moment"}:
        direction: Vector3 | None = _nonzero_vector(
            item.get("direction"), f"{context}.direction"
        )
    else:
        if item.get("direction") is not None:
            raise ValueError(f"{context}.direction is only allowed for force and moment responses")
        direction = None
    if kind == "pressure_loss":
        from_boundary_id = _required_id(options_value, "from_boundary_id", f"{context}.options")
        to_boundary_id = _required_id(options_value, "to_boundary_id", f"{context}.options")
        if from_boundary_id == to_boundary_id:
            raise ValueError(f"{context} pressure_loss boundary endpoints must be different")
    elif kind == "flow_rate":
        _required_id(options_value, "boundary_id", f"{context}.options")
    elif kind == "plugin":
        _required_id(options_value, "plugin_id", f"{context}.options")
    return ResponseSpec(
        id=_required_id(item, "id", context),
        kind=kind,
        flow_case_id=_required_id(item, "flow_case_id", context),
        direction=direction,
        options=options,
    )


def _load_objective(value: Any, index: int) -> ObjectiveSpec:
    context = f"objectives[{index}]"
    item = _as_mapping(value, context)
    _reject_unknown_keys(item, {"id", "sense", "terms"}, context)
    sense = _required_text(item, "sense", context).lower()
    if sense not in {"minimize", "maximize"}:
        raise ValueError(f"{context}.sense must be 'minimize' or 'maximize'")
    return ObjectiveSpec(
        id=_required_id(item, "id", context),
        sense=sense,
        terms=_load_terms(item, context),
    )


def _load_constraint(value: Any, index: int) -> ConstraintSpec:
    context = f"constraints[{index}]"
    item = _as_mapping(value, context)
    _reject_unknown_keys(item, {"id", "relation", "limit", "terms"}, context)
    relation = _required_text(item, "relation", context)
    if relation not in {"<=", ">=", "=="}:
        raise ValueError(f"{context}.relation must be '<=', '>=', or '=='")
    return ConstraintSpec(
        id=_required_id(item, "id", context),
        relation=relation,
        limit=_finite_float(item.get("limit"), f"{context}.limit"),
        terms=_load_terms(item, context),
    )


def _load_terms(item: Mapping[str, Any], context: str) -> tuple[WeightedTermSpec, ...]:
    values = _sequence(item, "terms", context)
    if not values:
        raise ValueError(f"{context}.terms must not be empty")
    terms: list[WeightedTermSpec] = []
    for index, value in enumerate(values):
        term_context = f"{context}.terms[{index}]"
        term = _as_mapping(value, term_context)
        _reject_unknown_keys(
            term, {"coefficient", "flow_case_id", "response_id"}, term_context
        )
        terms.append(
            WeightedTermSpec(
                coefficient=_finite_float(term.get("coefficient"), f"{term_context}.coefficient"),
                flow_case_id=_required_id(term, "flow_case_id", term_context),
                response_id=_required_id(term, "response_id", term_context),
            )
        )
    if not any(term.coefficient != 0.0 for term in terms):
        raise ValueError(f"{context}.terms must contain at least one nonzero coefficient")
    return tuple(terms)


def _migrate_legacy(path: Path, raw: Mapping[str, Any], source_version: Any) -> ProblemSpec:
    operating = raw.get("operating_point", {}) or {}
    if not isinstance(operating, Mapping):
        raise ValueError("operating_point must be a mapping")
    velocity = _positive_float(operating.get("velocity_mps", 11.0), "operating_point.velocity_mps")
    density = _positive_float(operating.get("density", 1.229), "operating_point.density")
    viscosity = _positive_float(operating.get("viscosity", 1.73e-5), "operating_point.viscosity")

    objective_raw = raw.get("objective", {}) or {}
    if not isinstance(objective_raw, Mapping):
        raise ValueError("objective must be a mapping")
    objective_type = str(objective_raw.get("type", "maximize_downforce_with_efficiency_constraint"))
    if objective_type != "maximize_downforce_with_efficiency_constraint":
        raise ValueError(f"Unsupported legacy objective.type: {objective_type!r}")
    efficiency_min = _finite_float(objective_raw.get("efficiency_min", 3.0), "objective.efficiency_min")

    flow_case_id = "legacy_default"
    responses = (
        ResponseSpec("drag", "force", flow_case_id, (1.0, 0.0, 0.0), _freeze_mapping({})),
        ResponseSpec(
            "downforce", "force", flow_case_id, (0.0, 0.0, -1.0), _freeze_mapping({})
        ),
    )
    try:
        source = None if source_version is None else int(source_version)
    except (TypeError, ValueError):
        source = None

    grid_raw = raw.get("grid", {}) or {}
    if not isinstance(grid_raw, Mapping):
        raise ValueError("grid must be a mapping")
    voxel_size = _positive_float(grid_raw.get("voxel_size_m", 0.025), "grid.voxel_size_m")
    padding = _nonnegative_float(grid_raw.get("padding_m", 0.15), "grid.padding_m")
    geometry_regions, geometry_notes = _migrate_legacy_geometry(raw)

    return ProblemSpec(
        path=path,
        schema_version=PROBLEM_SPEC_SCHEMA_VERSION,
        problem_id="legacy_front_wing",
        units=UnitsSpec("m", "s", "kg"),
        coordinate_frame=CoordinateFrameSpec(
            "legacy_global",
            (0.0, 0.0, 0.0),
            BasisSpec((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ),
        grid=GridSpec(
            "uniform_cartesian",
            voxel_size,
            padding,
            _freeze_mapping(
                {key: value for key, value in grid_raw.items() if key not in {"voxel_size_m", "padding_m"}}
            ),
        ),
        reference_values=None,
        geometry_regions=geometry_regions,
        flow_cases=(
            FlowCaseSpec(
                flow_case_id,
                (velocity, 0.0, 0.0),
                FluidSpec("incompressible_newtonian", density, viscosity),
                None,
                None,
                _freeze_mapping({}),
                _default_convergence_criteria(),
            ),
        ),
        responses=responses,
        objectives=(
            ObjectiveSpec("downforce", "maximize", (WeightedTermSpec(1.0, flow_case_id, "downforce"),)),
        ),
        constraints=(
            ConstraintSpec(
                "efficiency",
                ">=",
                0.0,
                (
                    WeightedTermSpec(1.0, flow_case_id, "downforce"),
                    WeightedTermSpec(-efficiency_min, flow_case_id, "drag"),
                ),
            ),
        ),
        topology_policy=_empty_topology_policy(),
        migration=MigrationSpec(
            source_schema_version=source,
            migrated=True,
            execution_ready=False,
            notes=(
                "Legacy objective and operating point were migrated to canonical weighted responses.",
                "Reference values and boundary conditions remain unspecified and must be supplied before execution.",
                *geometry_notes,
            ),
        ),
    )


def _migrate_legacy_geometry(
    raw: Mapping[str, Any],
) -> tuple[tuple[GeometryRegionSpec, ...], tuple[str, ...]]:
    regions: list[GeometryRegionSpec] = []
    notes: list[str] = []
    seen: set[str] = set()

    def append_region(item: Any, role: str, context: str) -> None:
        if not isinstance(item, Mapping):
            notes.append(f"Ignored malformed legacy geometry entry at {context}.")
            return
        region_id = item.get("id")
        file_value = item.get("file")
        if (
            not isinstance(region_id, str)
            or _ID_PATTERN.fullmatch(region_id) is None
            or not isinstance(file_value, (str, Path))
            or Path(str(file_value)).suffix.lower() != ".stl"
        ):
            notes.append(f"Ignored malformed or non-STL legacy geometry entry at {context}.")
            return
        if region_id in seen:
            notes.append(f"Ignored duplicate legacy geometry region id {region_id!r} at {context}.")
            return
        seen.add(region_id)
        regions.append(GeometryRegionSpec(region_id, role, Path(str(file_value))))

    geometry = raw.get("geometry", {}) or {}
    if isinstance(geometry, Mapping):
        for key, role in (
            ("fixed_solids", "fixed_solid"),
            ("design_geometry", "initial_design"),
            ("design_domains", "design_domain"),
            ("forbidden_regions", "forbidden_region"),
        ):
            entries = geometry.get(key, []) or []
            if isinstance(entries, list):
                for index, item in enumerate(entries):
                    append_region(item, role, f"geometry.{key}[{index}]")
            else:
                notes.append(f"Ignored malformed legacy geometry collection geometry.{key}.")
    else:
        notes.append("Ignored malformed legacy geometry mapping.")

    roots = raw.get("roots", []) or []
    if isinstance(roots, list):
        for index, item in enumerate(roots):
            if not isinstance(item, Mapping) or str(item.get("type", "stl")).lower() != "stl":
                notes.append(f"Ignored analytic or malformed legacy root at roots[{index}].")
                continue
            append_region(item, "root", f"roots[{index}]")
    else:
        notes.append("Ignored malformed legacy roots collection.")
    return tuple(regions), tuple(notes)


def _validate_references(spec: ProblemSpec) -> None:
    _ensure_unique_ids("geometry region", (item.id for item in spec.geometry_regions))
    _ensure_unique_ids("flow case", (item.id for item in spec.flow_cases))
    _ensure_unique_ids("response", (item.id for item in spec.responses))
    _ensure_unique_ids("objective", (item.id for item in spec.objectives))
    _ensure_unique_ids("constraint", (item.id for item in spec.constraints))

    flow_case_ids = {item.id for item in spec.flow_cases}
    responses_by_id = {item.id: item for item in spec.responses}
    for response in spec.responses:
        if response.flow_case_id not in flow_case_ids:
            raise ValueError(
                f"Response {response.id!r} references unknown flow_case_id {response.flow_case_id!r}"
            )
    for owner in (*spec.objectives, *spec.constraints):
        for term in owner.terms:
            if term.flow_case_id not in flow_case_ids:
                raise ValueError(f"{owner.id!r} term references unknown flow_case_id {term.flow_case_id!r}")
            response = responses_by_id.get(term.response_id)
            if response is None:
                raise ValueError(f"{owner.id!r} term references unknown response_id {term.response_id!r}")
            if response.flow_case_id != term.flow_case_id:
                raise ValueError(
                    f"{owner.id!r} term binds response {term.response_id!r} to flow case "
                    f"{term.flow_case_id!r}, but the response belongs to {response.flow_case_id!r}"
                )


def _is_v2_execution_ready(
    grid: GridSpec,
    reference_values: ReferenceValuesSpec | None,
    geometry_regions: tuple[GeometryRegionSpec, ...],
    flow_cases: tuple[FlowCaseSpec, ...],
) -> bool:
    references_complete = (
        reference_values is not None
        and reference_values.area_m2 is not None
        and reference_values.length_m is not None
        and reference_values.moment_center_m is not None
    )
    cases_complete = all(
        case.boundary_conditions is not None
        and bool(case.boundary_conditions)
        and case.turbulence is not None
        for case in flow_cases
    )
    geometry_complete = any(region.role == "design_domain" for region in geometry_regions)
    return (
        grid.kind == "uniform_cartesian"
        and references_complete
        and geometry_complete
        and cases_complete
    )


def _validate_basis(basis: BasisSpec) -> None:
    tolerance = 1.0e-6
    for name, vector in (("x", basis.x), ("y", basis.y), ("z", basis.z)):
        norm = sqrt(_dot(vector, vector))
        if abs(norm - 1.0) > tolerance:
            raise ValueError(f"coordinate_frame.basis.{name} must be a unit vector")
    if any(
        abs(value) > tolerance
        for value in (_dot(basis.x, basis.y), _dot(basis.x, basis.z), _dot(basis.y, basis.z))
    ):
        raise ValueError("coordinate_frame basis vectors must be mutually orthogonal")
    if _dot(_cross(basis.x, basis.y), basis.z) < 1.0 - tolerance:
        raise ValueError("coordinate_frame basis must be right-handed")


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _require_nonempty(name: str, values: Sequence[Any]) -> None:
    if not values:
        raise ValueError(f"{name} must not be empty")


def _ensure_unique_ids(kind: str, values: Any) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate {kind} id: {value!r}")
        seen.add(value)


def _mapping(data: Mapping[str, Any], key: str, context: str = "problem specification") -> Mapping[str, Any]:
    return _as_mapping(data.get(key), f"{context}.{key}")


def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _sequence(data: Mapping[str, Any], key: str, context: str = "problem specification") -> Sequence[Any]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{context}.{key} must be a sequence")
    return value


def _required_text(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _required_id(data: Mapping[str, Any], key: str, context: str) -> str:
    value = _required_text(data, key, context)
    if _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{context}.{key} must match ^[a-z][a-z0-9_]{{0,63}}$")
    return value


def _required_unique_id_sequence(
    data: Mapping[str, Any], key: str, context: str
) -> tuple[str, ...]:
    values = _sequence(data, key, context)
    result: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(values):
        item_context = f"{context}.{key}[{index}]"
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{item_context} must be an ID")
        item_id = raw.strip()
        if _ID_PATTERN.fullmatch(item_id) is None:
            raise ValueError(f"{item_context} must match ^[a-z][a-z0-9_]{{0,63}}$")
        if item_id in seen:
            raise ValueError(f"Duplicate ID {item_id!r} in {context}.{key}")
        seen.add(item_id)
        result.append(item_id)
    return tuple(result)


def _reject_unknown_keys(
    value: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise ValueError(f"{context} has unknown keys: {unknown!r}")


def _vector3(value: Any, context: str) -> Vector3:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 3:
        raise ValueError(f"{context} must contain exactly three finite numbers")
    return (
        _finite_float(value[0], f"{context}[0]"),
        _finite_float(value[1], f"{context}[1]"),
        _finite_float(value[2], f"{context}[2]"),
    )


def _nonzero_vector(value: Any, context: str) -> Vector3:
    result = _vector3(value, context)
    if _dot(result, result) <= 0.0:
        raise ValueError(f"{context} must be nonzero")
    return result


def _finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{context} must be a finite number")
    return result


def _positive_float(value: Any, context: str) -> float:
    result = _finite_float(value, context)
    if result <= 0.0:
        raise ValueError(f"{context} must be positive")
    return result


def _nonnegative_float(value: Any, context: str) -> float:
    result = _finite_float(value, context)
    if result < 0.0:
        raise ValueError(f"{context} must be nonnegative")
    return result


def _optional_positive_float(value: Any, context: str) -> float | None:
    return None if value is None else _positive_float(value, context)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


__all__ = [
    "BasisSpec",
    "ConstraintSpec",
    "ConvergenceCriteriaSpec",
    "ConnectivityPolicySpec",
    "CoordinateFrameSpec",
    "FlowCaseSpec",
    "FluidSpec",
    "GeometryRegionSpec",
    "GridSpec",
    "MigrationSpec",
    "ObjectiveSpec",
    "PROBLEM_SPEC_SCHEMA_VERSION",
    "ProblemSpec",
    "ReferenceValuesSpec",
    "ResponseSpec",
    "RootGroupSpec",
    "TopologyPolicySpec",
    "TurbulenceSpec",
    "UnitsSpec",
    "WeightedTermSpec",
    "canonical_problem_spec_json",
    "load_problem_spec",
    "problem_spec_sha256",
    "problem_spec_to_dict",
    "topology_constraint_ids",
    "write_problem_spec_snapshot",
]
