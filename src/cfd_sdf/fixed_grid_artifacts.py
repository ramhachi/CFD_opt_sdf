"""Versioned readers for fixed-grid primal and sensitivity summary artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from .problem_spec import ProblemSpec, problem_spec_sha256, topology_constraint_ids


_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProblemBinding:
    problem_id: str
    problem_spec_sha256: str | None
    execution_ready: bool


@dataclass(frozen=True)
class ResponseKey:
    flow_case_id: str
    response_id: str


@dataclass(frozen=True)
class ConstraintKey:
    scope: str
    constraint_id: str


@dataclass(frozen=True)
class QuantityValue:
    value: float | None
    units: str
    status: str
    source: str


ResponseValue = QuantityValue


@dataclass(frozen=True)
class GradientBinding:
    target_kind: str
    flow_case_id: str | None
    response_id: str | None
    objective_id: str | None
    constraint_id: str | None
    scope: str
    design_variable_id: str
    array_name: str
    units: str
    status: str
    source: str


@dataclass(frozen=True)
class CanonicalPrimalSummary:
    path: Path
    schema_version: int
    kind: str
    problem: ProblemBinding
    flow_case_ids: tuple[str, ...]
    response_values: Mapping[ResponseKey, QuantityValue]
    objective_values: Mapping[str, QuantityValue]
    constraint_values: Mapping[ConstraintKey, QuantityValue]
    status: str

    @property
    def problem_binding(self) -> ProblemBinding:
        return self.problem

    @property
    def flow_case_id(self) -> str | None:
        return self.flow_case_ids[0] if len(self.flow_case_ids) == 1 else None


@dataclass(frozen=True)
class CanonicalSensitivitySummary:
    path: Path
    schema_version: int
    kind: str
    problem: ProblemBinding
    flow_case_ids: tuple[str, ...]
    gradient_bindings: tuple[GradientBinding, ...]
    status: str

    @property
    def problem_binding(self) -> ProblemBinding:
        return self.problem

    @property
    def flow_case_id(self) -> str | None:
        return self.flow_case_ids[0] if len(self.flow_case_ids) == 1 else None


def read_fixed_grid_primal_summary(path: str | Path) -> CanonicalPrimalSummary:
    summary_path, data = _read_json_mapping(path)
    version = _schema_version(data)
    if version == 1:
        return _read_v1_primal(summary_path, data)
    if version == 2:
        return _read_v2_primal(summary_path, data)
    raise ValueError(f"Unsupported fixed-grid primal schema_version: {version!r}")


def read_fixed_grid_sensitivity_summary(path: str | Path) -> CanonicalSensitivitySummary:
    summary_path, data = _read_json_mapping(path)
    version = _schema_version(data)
    if version == 1:
        return _read_v1_sensitivity(summary_path, data)
    if version == 2:
        return _read_v2_sensitivity(summary_path, data)
    raise ValueError(f"Unsupported fixed-grid sensitivity schema_version: {version!r}")


def validate_primal_summary_against_problem_spec(
    summary: CanonicalPrimalSummary,
    spec: ProblemSpec,
) -> None:
    """Validate a canonical primal artifact against its declared problem semantics."""

    _validate_summary_binding(summary, spec)
    if summary.schema_version == 1:
        return

    response_keys = {(response.flow_case_id, response.id) for response in spec.responses}
    for key in summary.response_values:
        semantic_key = (key.flow_case_id, key.response_id)
        if semantic_key not in response_keys:
            raise ValueError(
                "Unknown primal response binding in problem specification: "
                f"flow_case_id={key.flow_case_id!r}, response_id={key.response_id!r}"
            )

    objective_ids = {objective.id for objective in spec.objectives}
    for objective_id in summary.objective_values:
        if objective_id not in objective_ids:
            raise ValueError(
                f"Unknown primal objective_id in problem specification: {objective_id!r}"
            )

    aggregate_constraint_ids = {constraint.id for constraint in spec.constraints}
    topology_ids = set(topology_constraint_ids(spec))
    for key in summary.constraint_values:
        allowed_ids = aggregate_constraint_ids if key.scope == "aggregate" else topology_ids
        if key.constraint_id not in allowed_ids:
            raise ValueError(
                "Unknown primal constraint binding in problem specification: "
                f"scope={key.scope!r}, constraint_id={key.constraint_id!r}"
            )


def validate_sensitivity_summary_against_problem_spec(
    summary: CanonicalSensitivitySummary,
    spec: ProblemSpec,
) -> None:
    """Validate a canonical sensitivity artifact against its declared problem semantics."""

    _validate_summary_binding(summary, spec)
    if summary.schema_version == 1:
        return

    response_keys = {(response.flow_case_id, response.id) for response in spec.responses}
    objective_ids = {objective.id for objective in spec.objectives}
    aggregate_constraint_ids = {constraint.id for constraint in spec.constraints}
    topology_ids = set(topology_constraint_ids(spec))
    for binding in summary.gradient_bindings:
        if binding.target_kind == "response":
            semantic_key = (binding.flow_case_id, binding.response_id)
            if semantic_key not in response_keys:
                raise ValueError(
                    "Unknown sensitivity response binding in problem specification: "
                    f"flow_case_id={binding.flow_case_id!r}, response_id={binding.response_id!r}"
                )
        elif binding.target_kind == "objective":
            if binding.objective_id not in objective_ids:
                raise ValueError(
                    "Unknown sensitivity objective_id in problem specification: "
                    f"{binding.objective_id!r}"
                )
        elif binding.scope == "aggregate":
            if binding.constraint_id not in aggregate_constraint_ids:
                raise ValueError(
                    "Unknown sensitivity aggregate constraint_id in problem specification: "
                    f"{binding.constraint_id!r}"
                )
        elif binding.constraint_id not in topology_ids:
            raise ValueError(
                "Unknown sensitivity topology constraint_id in problem specification: "
                f"{binding.constraint_id!r}"
            )


def _validate_summary_binding(
    summary: CanonicalPrimalSummary | CanonicalSensitivitySummary,
    spec: ProblemSpec,
) -> None:
    if summary.schema_version == 1 and not spec.migration.migrated:
        raise ValueError(
            "Legacy v1 fixed-grid summaries can only bind to a migrated legacy problem specification"
        )
    if summary.problem.problem_id != spec.problem_id:
        raise ValueError(
            "Problem ID mismatch: "
            f"summary={summary.problem.problem_id!r}, specification={spec.problem_id!r}"
        )
    if summary.schema_version != 1:
        expected_hash = problem_spec_sha256(spec)
        if summary.problem.problem_spec_sha256 != expected_hash:
            raise ValueError(
                "Problem specification hash mismatch: "
                f"summary={summary.problem.problem_spec_sha256!r}, expected={expected_hash!r}"
            )
    if summary.problem.execution_ready != spec.migration.execution_ready:
        raise ValueError(
            "execution_ready mismatch: "
            f"summary={summary.problem.execution_ready!r}, "
            f"specification={spec.migration.execution_ready!r}"
        )

    declared_flow_case_ids = {flow_case.id for flow_case in spec.flow_cases}
    unknown_flow_case_ids = [
        flow_case_id
        for flow_case_id in summary.flow_case_ids
        if flow_case_id not in declared_flow_case_ids
    ]
    if unknown_flow_case_ids:
        raise ValueError(
            "Summary references flow_case_ids not declared by the problem specification: "
            f"{unknown_flow_case_ids!r}"
        )


def _read_v2_primal(path: Path, data: Mapping[str, Any]) -> CanonicalPrimalSummary:
    _require_kind(data, "fixed_grid_primal_summary")
    problem = _v2_problem_binding(data)
    flow_case_ids = _required_id_list(data, "flow_case_ids", "fixed-grid primal summary")
    flow_case_id_set = set(flow_case_ids)
    raw_values = _required_list(data, "response_values", "fixed-grid primal summary")
    if not raw_values:
        raise ValueError("fixed-grid primal summary.response_values must not be empty")
    values: dict[ResponseKey, QuantityValue] = {}
    for index, raw in enumerate(raw_values):
        context = f"response_values[{index}]"
        item = _as_mapping(raw, context)
        item_flow_case_id = _required_id(item, "flow_case_id", context)
        if item_flow_case_id not in flow_case_id_set:
            raise ValueError(
                f"{context}.flow_case_id {item_flow_case_id!r} is not present in "
                f"top-level flow_case_ids"
            )
        key = ResponseKey(
            flow_case_id=item_flow_case_id,
            response_id=_required_id(item, "response_id", context),
        )
        if key in values:
            raise ValueError(f"Duplicate response key: {key!r}")
        values[key] = QuantityValue(
            value=_optional_finite_float(item.get("value"), f"{context}.value"),
            units=_required_text(item, "units", context),
            status=_required_text(item, "status", context),
            source=_required_text(item, "source", context),
        )
    objective_values = _read_v2_named_values(
        data,
        collection_name="objective_values",
        id_name="objective_id",
        require_nonempty=True,
    )
    constraint_values = _read_v2_constraint_values(data)
    return CanonicalPrimalSummary(
        path=path,
        schema_version=2,
        kind="fixed_grid_primal_summary",
        problem=problem,
        flow_case_ids=flow_case_ids,
        response_values=MappingProxyType(values),
        objective_values=objective_values,
        constraint_values=constraint_values,
        status=_required_text(data, "status", "fixed-grid primal summary"),
    )


def _read_v2_named_values(
    data: Mapping[str, Any],
    *,
    collection_name: str,
    id_name: str,
    require_nonempty: bool,
) -> Mapping[str, QuantityValue]:
    raw_values = _required_list(data, collection_name, "fixed-grid primal summary")
    if require_nonempty and not raw_values:
        raise ValueError(f"fixed-grid primal summary.{collection_name} must not be empty")
    values: dict[str, QuantityValue] = {}
    for index, raw in enumerate(raw_values):
        context = f"{collection_name}[{index}]"
        item = _as_mapping(raw, context)
        item_id = _required_id(item, id_name, context)
        if item_id in values:
            raise ValueError(f"Duplicate {id_name}: {item_id!r}")
        values[item_id] = QuantityValue(
            value=_optional_finite_float(item.get("value"), f"{context}.value"),
            units=_required_text(item, "units", context),
            status=_required_text(item, "status", context),
            source=_required_text(item, "source", context),
        )
    return MappingProxyType(values)


def _read_v2_constraint_values(
    data: Mapping[str, Any],
) -> Mapping[ConstraintKey, QuantityValue]:
    raw_values = _required_list(data, "constraint_values", "fixed-grid primal summary")
    values: dict[ConstraintKey, QuantityValue] = {}
    for index, raw in enumerate(raw_values):
        context = f"constraint_values[{index}]"
        item = _as_mapping(raw, context)
        scope = _required_text(item, "scope", context)
        if scope not in {"aggregate", "topology"}:
            raise ValueError(f"{context}.scope must be 'aggregate' or 'topology'")
        key = ConstraintKey(
            scope=scope,
            constraint_id=_required_id(item, "constraint_id", context),
        )
        if key in values:
            raise ValueError(f"Duplicate constraint key: {key!r}")
        values[key] = QuantityValue(
            value=_optional_finite_float(item.get("value"), f"{context}.value"),
            units=_required_text(item, "units", context),
            status=_required_text(item, "status", context),
            source=_required_text(item, "source", context),
        )
    return MappingProxyType(values)


def _read_v2_sensitivity(path: Path, data: Mapping[str, Any]) -> CanonicalSensitivitySummary:
    _require_kind(data, "fixed_grid_sensitivity_summary")
    problem = _v2_problem_binding(data)
    flow_case_ids = _required_id_list(data, "flow_case_ids", "fixed-grid sensitivity summary")
    flow_case_id_set = set(flow_case_ids)
    raw_bindings = _required_list(data, "gradient_bindings", "fixed-grid sensitivity summary")
    if not raw_bindings:
        raise ValueError("fixed-grid sensitivity summary.gradient_bindings must not be empty")
    bindings: list[GradientBinding] = []
    semantic_keys: set[
        tuple[str, str | None, str | None, str | None, str | None, str, str]
    ] = set()
    array_names: set[str] = set()
    for index, raw in enumerate(raw_bindings):
        context = f"gradient_bindings[{index}]"
        binding = _read_v2_gradient_binding(_as_mapping(raw, context), context, flow_case_id_set)
        semantic_key = (
            binding.target_kind,
            binding.flow_case_id,
            binding.response_id,
            binding.objective_id,
            binding.constraint_id,
            binding.scope,
            binding.design_variable_id,
        )
        if semantic_key in semantic_keys:
            raise ValueError(f"Duplicate gradient key: {semantic_key!r}")
        if binding.array_name in array_names:
            raise ValueError(f"Duplicate gradient array_name: {binding.array_name!r}")
        semantic_keys.add(semantic_key)
        array_names.add(binding.array_name)
        bindings.append(binding)
    return CanonicalSensitivitySummary(
        path=path,
        schema_version=2,
        kind="fixed_grid_sensitivity_summary",
        problem=problem,
        flow_case_ids=flow_case_ids,
        gradient_bindings=tuple(bindings),
        status=_required_text(data, "status", "fixed-grid sensitivity summary"),
    )


def _read_v2_gradient_binding(
    item: Mapping[str, Any], context: str, top_flow_case_ids: set[str]
) -> GradientBinding:
    target_kind = _required_text(item, "target_kind", context)
    if target_kind not in {"response", "objective", "constraint"}:
        raise ValueError(f"{context}.target_kind must be 'response', 'objective', or 'constraint'")
    scope = _required_text(item, "scope", context)
    if scope not in {"flow", "aggregate", "topology"}:
        raise ValueError(f"{context}.scope must be 'flow', 'aggregate', or 'topology'")

    flow_case_id = _optional_id(item.get("flow_case_id"), f"{context}.flow_case_id")
    response_id = _optional_id(item.get("response_id"), f"{context}.response_id")
    objective_id = _optional_id(item.get("objective_id"), f"{context}.objective_id")
    constraint_id = _optional_id(item.get("constraint_id"), f"{context}.constraint_id")
    if target_kind == "response":
        if (
            scope != "flow"
            or flow_case_id is None
            or response_id is None
            or objective_id is not None
            or constraint_id is not None
        ):
            raise ValueError(
                f"{context} response gradients require scope='flow', flow_case_id and response_id only"
            )
    elif target_kind == "objective":
        if (
            scope != "aggregate"
            or objective_id is None
            or flow_case_id is not None
            or response_id is not None
            or constraint_id is not None
        ):
            raise ValueError(
                f"{context} objective gradients require scope='aggregate' and objective_id only"
            )
    elif (
        scope not in {"aggregate", "topology"}
        or constraint_id is None
        or flow_case_id is not None
        or response_id is not None
        or objective_id is not None
    ):
        raise ValueError(
            f"{context} constraint gradients require aggregate/topology scope and constraint_id only"
        )
    if flow_case_id is not None and flow_case_id not in top_flow_case_ids:
        raise ValueError(
            f"{context}.flow_case_id {flow_case_id!r} is not present in top-level flow_case_ids"
        )

    return GradientBinding(
        target_kind=target_kind,
        flow_case_id=flow_case_id,
        response_id=response_id,
        objective_id=objective_id,
        constraint_id=constraint_id,
        scope=scope,
        design_variable_id=_required_id(item, "design_variable_id", context),
        array_name=_required_id(item, "array_name", context),
        units=_required_text(item, "units", context),
        status=_required_text(item, "status", context),
        source=_required_text(item, "source", context),
    )


def _read_v1_primal(path: Path, data: Mapping[str, Any]) -> CanonicalPrimalSummary:
    _require_kind(data, "fixed_grid_primal_summary")
    flow_case_id = "legacy_default"
    units = data.get("units", {}) or {}
    if not isinstance(units, Mapping):
        units = {}
    status = str(data.get("status") or "legacy_v1")
    values: dict[ResponseKey, QuantityValue] = {}
    for field, response_id in (
        ("drag_coefficient", "drag"),
        ("downforce_coefficient", "downforce"),
    ):
        key = ResponseKey(flow_case_id, response_id)
        values[key] = QuantityValue(
            value=_optional_finite_float(data.get(field), field),
            units=str(units.get(field, "1")),
            status=status,
            source=f"legacy_v1.{field}",
        )
    objective_values = MappingProxyType(
        {
            "legacy_objective": QuantityValue(
                value=_optional_finite_float(data.get("objective"), "objective"),
                units=str(units.get("objective", "1")),
                status=status,
                source="legacy_v1.objective",
            )
        }
    )
    constraint_values = MappingProxyType(
        {
            ConstraintKey("aggregate", "efficiency"): QuantityValue(
                value=_optional_finite_float(data.get("efficiency_constraint"), "efficiency_constraint"),
                units=str(units.get("efficiency_constraint", "1")),
                status=status,
                source="legacy_v1.efficiency_constraint",
            )
        }
    )
    return CanonicalPrimalSummary(
        path=path,
        schema_version=1,
        kind="fixed_grid_primal_summary",
        problem=_legacy_problem_binding(),
        flow_case_ids=(flow_case_id,),
        response_values=MappingProxyType(values),
        objective_values=objective_values,
        constraint_values=constraint_values,
        status=status,
    )


def _read_v1_sensitivity(path: Path, data: Mapping[str, Any]) -> CanonicalSensitivitySummary:
    _require_kind(data, "fixed_grid_sensitivity_summary")
    metadata = data.get("array_metadata", {}) or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("array_metadata must be a mapping")
    field_sources = data.get("field_sources", {}) or {}
    if not isinstance(field_sources, Mapping):
        field_sources = {}
    default_design_variable = str(data.get("design_variable") or "rho")
    default_status = str(data.get("status") or "legacy_v1")
    bindings: list[GradientBinding] = []
    for array_name, raw_metadata in metadata.items():
        if not isinstance(array_name, str) or not array_name.startswith("d_"):
            continue
        item = _as_mapping(raw_metadata, f"array_metadata.{array_name}")
        target_id, design_variable_id = _legacy_gradient_name(array_name, default_design_variable)
        target_kind, scope, flow_case_id, response_id, objective_id, constraint_id = (
            _legacy_gradient_target(target_id)
        )
        bindings.append(
            GradientBinding(
                target_kind=target_kind,
                flow_case_id=flow_case_id,
                response_id=response_id,
                objective_id=objective_id,
                constraint_id=constraint_id,
                scope=scope,
                design_variable_id=design_variable_id,
                array_name=array_name,
                units=str(item.get("units", "1")),
                status=str(item.get("status") or default_status),
                source=str(item.get("source") or field_sources.get(array_name) or f"legacy_v1.{array_name}"),
            )
        )
    if not bindings:
        raise ValueError("array_metadata must contain at least one d_* gradient array")
    return CanonicalSensitivitySummary(
        path=path,
        schema_version=1,
        kind="fixed_grid_sensitivity_summary",
        problem=_legacy_problem_binding(),
        flow_case_ids=("legacy_default",),
        gradient_bindings=tuple(bindings),
        status=default_status,
    )


def _legacy_gradient_name(array_name: str, default_design_variable: str) -> tuple[str, str]:
    match = re.fullmatch(r"d_(.+)_d_([a-z][a-z0-9_]*)", array_name)
    if match is None:
        return array_name[2:], default_design_variable
    return match.group(1), match.group(2)


def _legacy_gradient_target(
    target_id: str,
) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    if target_id.startswith("connectivity_"):
        return "constraint", "topology", None, None, None, target_id
    if target_id == "efficiency_constraint":
        return "constraint", "aggregate", None, None, None, "efficiency"
    if target_id == "objective":
        return "objective", "aggregate", None, None, "legacy_objective", None
    return "response", "flow", "legacy_default", target_id, None, None


def _v2_problem_binding(data: Mapping[str, Any]) -> ProblemBinding:
    problem_id = _required_id(data, "problem_id", "fixed-grid summary")
    digest = _required_text(data, "problem_spec_sha256", "fixed-grid summary")
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("problem_spec_sha256 must be 64 lowercase hexadecimal characters")
    execution_ready = data.get("execution_ready")
    if not isinstance(execution_ready, bool):
        raise ValueError("fixed-grid summary.execution_ready must be a boolean")
    return ProblemBinding(problem_id, digest, execution_ready)


def _legacy_problem_binding() -> ProblemBinding:
    return ProblemBinding("legacy_front_wing", None, False)


def _read_json_mapping(path: str | Path) -> tuple[Path, Mapping[str, Any]]:
    summary_path = Path(path).resolve()
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {summary_path}: {exc.msg}") from exc
    if not isinstance(data, Mapping):
        raise ValueError("Fixed-grid summary root must be a mapping")
    return summary_path, data


def _schema_version(data: Mapping[str, Any]) -> int:
    try:
        return int(data.get("schema_version"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid schema_version: {data.get('schema_version')!r}") from exc


def _require_kind(data: Mapping[str, Any], expected: str) -> None:
    if data.get("kind") != expected:
        raise ValueError(f"Expected kind {expected!r}, got {data.get('kind')!r}")


def _required_list(data: Mapping[str, Any], key: str, context: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{context}.{key} must be a list")
    return value


def _required_id_list(data: Mapping[str, Any], key: str, context: str) -> tuple[str, ...]:
    raw_values = _required_list(data, key, context)
    if not raw_values:
        raise ValueError(f"{context}.{key} must not be empty")
    values: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_values):
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{context}.{key}[{index}] must be an ID")
        value = _validate_id(raw.strip(), f"{context}.{key}[{index}]")
        if value in seen:
            raise ValueError(f"Duplicate flow_case_id in {context}.{key}: {value!r}")
        seen.add(value)
        values.append(value)
    return tuple(values)


def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _required_text(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _required_id(data: Mapping[str, Any], key: str, context: str) -> str:
    return _validate_id(_required_text(data, key, context), f"{context}.{key}")


def _optional_id(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be an ID or null")
    return _validate_id(value.strip(), context)


def _validate_id(value: str, context: str) -> str:
    if _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{context} must match ^[a-z][a-z0-9_]{{0,63}}$")
    return value


def _optional_finite_float(value: Any, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a finite number or null")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a finite number or null") from exc
    if not isfinite(result):
        raise ValueError(f"{context} must be a finite number or null")
    return result


__all__ = [
    "CanonicalPrimalSummary",
    "CanonicalSensitivitySummary",
    "ConstraintKey",
    "GradientBinding",
    "ProblemBinding",
    "QuantityValue",
    "ResponseKey",
    "ResponseValue",
    "read_fixed_grid_primal_summary",
    "read_fixed_grid_sensitivity_summary",
    "validate_primal_summary_against_problem_spec",
    "validate_sensitivity_summary_against_problem_spec",
]
