"""Compile a ProblemSpec into the algebra the optimizer actually solves (DF1).

The Stage T optimizer used to hard-code ``objective = -d(downforce)/d(rho)`` and
to read pre-combined constraint arrays without checking them against the
declared problem. This module owns the mapping from ``ProblemSpec``
objectives/constraints/term aggregation to:

- a standardized minimization objective ``J = sense_sign * sum(coeff * response)``
  with its gradient assembled from primitive response gradients;
- constraints normalized to ``g <= 0`` with values and gradients assembled from
  the same primitives;
- the projected occupied-volume constraint ``V_occ(rho_projected) - V_max <= 0``,
  where ``V_occ`` is defined on the projected field (never the raw design
  variable);
- topology-policy geometry requirements, which are not linear constraint terms
  and are surfaced separately;
- fail-closed rejection of unsupported responses, unknown units, missing
  primitives, and undeclared design-variable bindings.

Nothing here starts a solver; a missing primitive is a compile-time error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .design_transform import DesignTransform

SUPPORTED_RESPONSE_KINDS = ("force",)


class ProblemCompileError(ValueError):
    """Fail-closed ProblemSpec-to-algebra compilation failure."""


@dataclass(frozen=True)
class CompiledTerm:
    coefficient: float
    flow_case_id: str
    response_id: str


@dataclass(frozen=True)
class CompiledObjective:
    objective_id: str
    sense: str
    terms: tuple[CompiledTerm, ...]

    @property
    def sign(self) -> float:
        return 1.0 if self.sense == "minimize" else -1.0

    def required_primitives(self) -> set[tuple[str, str]]:
        return {(term.flow_case_id, term.response_id) for term in self.terms}


@dataclass(frozen=True)
class CompiledConstraint:
    constraint_id: str
    relation: str
    limit: float
    terms: tuple[CompiledTerm, ...]

    def required_primitives(self) -> set[tuple[str, str]]:
        return {(term.flow_case_id, term.response_id) for term in self.terms}

    def scalar(self, primitive_values: Mapping[tuple[str, str], float]) -> float:
        total = 0.0
        for term in self.terms:
            total += term.coefficient * float(primitive_values[(term.flow_case_id, term.response_id)])
        if self.relation == "<=":
            return total - self.limit
        if self.relation == ">=":
            return self.limit - total
        raise ProblemCompileError(
            f"constraint {self.constraint_id!r} uses unsupported relation {self.relation!r}"
        )

    def gradient(
        self, primitive_gradients: Mapping[tuple[str, str], np.ndarray]
    ) -> np.ndarray:
        gradient = None
        for term in self.terms:
            contribution = term.coefficient * np.asarray(
                primitive_gradients[(term.flow_case_id, term.response_id)], dtype=np.float64
            )
            gradient = contribution if gradient is None else gradient + contribution
        if gradient is None:
            raise ProblemCompileError(f"constraint {self.constraint_id!r} has no terms")
        if self.relation == ">=":
            gradient = -gradient
        return gradient


@dataclass(frozen=True)
class VolumeBudget:
    """Explicit compile-time volume declaration; ProblemSpec v2 has no field for it.

    The contract amendment that would make this a ProblemSpec field is a
    separate decision (architecture plan PQ0 stop condition). Until then the
    budget must be declared at compile time or the production runner fails
    closed; no default is guessed.
    """

    constraint_id: str
    limit: float

    def __post_init__(self) -> None:
        if not self.constraint_id:
            raise ProblemCompileError("volume budget constraint_id must not be empty")
        if not 0.0 <= float(self.limit) <= 1.0:
            raise ProblemCompileError("volume budget limit must be within [0, 1]")


@dataclass(frozen=True)
class VolumeOccupationConstraint:
    """``g_V = V_occ(rho_projected) - V_max <= 0``.

    ``V_occ`` and its gradient live in the **projection output** space
    (``DesignTransformState.rho_projected``); the RAMP derivative is not part
    of this constraint. The artifact array named ``rho_projected`` is the RAMP
    output (OpenFOAM beta) under the fixed-grid contract, so the production
    runner recomputes the projection output from the stored ``rho_filtered``
    and the declared projection instead of reading that array.
    """

    constraint_id: str
    limit: float
    field: str = "rho_projected"

    def value(self, transform: DesignTransform, rho: np.ndarray) -> float:
        state = transform.forward(rho)
        return transform.projected_volume_fraction(state) - self.limit

    def gradient(self, transform: DesignTransform, rho: np.ndarray) -> np.ndarray:
        state = transform.forward(rho)
        occupancy = np.asarray(state.rho_projected)
        active = transform.active
        count = max(int(active.sum()), 1)
        g_projected = np.zeros_like(occupancy)
        g_projected[active] = 1.0 / float(count)
        return transform.pullback_from_projected(rho, g_projected)


@dataclass(frozen=True)
class GeometryRequirement:
    requirement_id: str
    kind: str
    declared: dict[str, Any]


@dataclass(frozen=True)
class CompiledProblem:
    problem_spec_sha256: str
    objectives: tuple[CompiledObjective, ...]
    constraints: tuple[CompiledConstraint, ...]
    volume_constraint: VolumeOccupationConstraint | None
    geometry_requirements: tuple[GeometryRequirement, ...]
    response_bindings: dict[str, str]

    def solved_set(self) -> dict[str, Any]:
        """Machine-readable declared-versus-solved audit for the production runner."""

        return {
            "objectives": [
                {
                    "id": objective.objective_id,
                    "sense": objective.sense,
                    "source": "problem_spec.objectives",
                    "terms": [
                        {
                            "coefficient": term.coefficient,
                            "flow_case_id": term.flow_case_id,
                            "response_id": term.response_id,
                        }
                        for term in objective.terms
                    ],
                }
                for objective in self.objectives
            ],
            "constraints": [
                {
                    "id": constraint.constraint_id,
                    "relation": constraint.relation,
                    "limit": constraint.limit,
                    "source": "problem_spec.constraints",
                    "terms": [
                        {
                            "coefficient": term.coefficient,
                            "flow_case_id": term.flow_case_id,
                            "response_id": term.response_id,
                        }
                        for term in constraint.terms
                    ],
                }
                for constraint in self.constraints
            ],
            "volume": (
                {
                    "id": self.volume_constraint.constraint_id,
                    "limit": self.volume_constraint.limit,
                    "field": self.volume_constraint.field,
                    "source": "compile_time_declaration",
                }
                if self.volume_constraint is not None
                else None
            ),
            "geometry_requirements": [
                {
                    "id": requirement.requirement_id,
                    "kind": requirement.kind,
                    "source": "topology_policy",
                    "declared": requirement.declared,
                }
                for requirement in self.geometry_requirements
            ],
        }

    def compiled_problem_hash(self) -> str:
        import hashlib
        import json as _json

        payload = _json.dumps(
            {
                "problem_spec_sha256": self.problem_spec_sha256,
                "solved_set": self.solved_set(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def required_primitives(self) -> set[tuple[str, str]]:
        required: set[tuple[str, str]] = set()
        for objective in self.objectives:
            required |= objective.required_primitives()
        for constraint in self.constraints:
            required |= constraint.required_primitives()
        return required

    def objective_value(self, primitive_values: Mapping[tuple[str, str], float]) -> float:
        total = 0.0
        for objective in self.objectives:
            contribution = 0.0
            for term in objective.terms:
                contribution += term.coefficient * float(
                    primitive_values[(term.flow_case_id, term.response_id)]
                )
            total += objective.sign * contribution
        return total

    def objective_gradient(
        self, primitive_gradients: Mapping[tuple[str, str], np.ndarray]
    ) -> np.ndarray:
        gradient = None
        for objective in self.objectives:
            for term in objective.terms:
                contribution = objective.sign * term.coefficient * np.asarray(
                    primitive_gradients[(term.flow_case_id, term.response_id)],
                    dtype=np.float64,
                )
                gradient = contribution if gradient is None else gradient + contribution
        if gradient is None:
            raise ProblemCompileError("no objective terms are declared")
        if not np.isfinite(gradient).all():
            raise ProblemCompileError("assembled objective gradient contains non-finite values")
        return gradient

    def constraint_values(
        self, primitive_values: Mapping[tuple[str, str], float]
    ) -> dict[str, float]:
        return {
            constraint.constraint_id: constraint.scalar(primitive_values)
            for constraint in self.constraints
        }

    def constraint_gradients(
        self, primitive_gradients: Mapping[tuple[str, str], np.ndarray]
    ) -> dict[str, np.ndarray]:
        return {
            constraint.constraint_id: constraint.gradient(primitive_gradients)
            for constraint in self.constraints
        }

    def enforce_primitives(self, available: set[tuple[str, str]]) -> None:
        missing = sorted(self.required_primitives() - available)
        if missing:
            formatted = ", ".join(f"{case}/{response}" for case, response in missing)
            raise ProblemCompileError(
                f"declared problem requires primitives that were not provided: {formatted}"
            )


def _response_index(spec: Any) -> dict[str, Any]:
    return {response.id: response for response in spec.responses}


def compile_problem(
    spec: Any,
    *,
    sha256: str | None = None,
    volume_budget: VolumeBudget | None = None,
) -> CompiledProblem:
    """Compile a loaded ``ProblemSpec`` (fail-closed on unsupported declarations).

    ``volume_budget`` is the explicit compile-time volume declaration. When it
    is absent, no volume constraint is solved, and the production runner must
    refuse to add one from legacy control defaults.
    """

    from .problem_spec import problem_spec_sha256  # local import avoids cycles

    responses = _response_index(spec)
    units = getattr(spec, "units", None)
    if units is None:
        raise ProblemCompileError("ProblemSpec must declare units before compilation")

    if not spec.objectives:
        raise ProblemCompileError("ProblemSpec declares no objectives")

    objectives: list[CompiledObjective] = []
    for objective in spec.objectives:
        terms = _compile_terms(objective.terms, objective.id, responses, spec)
        objectives.append(
            CompiledObjective(
                objective_id=objective.id,
                sense=objective.sense,
                terms=terms,
            )
        )

    constraints: list[CompiledConstraint] = []
    for constraint in spec.constraints:
        if constraint.relation == "==":
            raise ProblemCompileError(
                f"constraint {constraint.id!r} is an equality; the optimizer solves "
                "inequalities only and the declaration must be re-registered as a bound"
            )
        terms = _compile_terms(constraint.terms, constraint.id, responses, spec)
        constraints.append(
            CompiledConstraint(
                constraint_id=constraint.id,
                relation=constraint.relation,
                limit=float(constraint.limit),
                terms=terms,
            )
        )

    requirements = _compile_topology_policy(spec)
    response_bindings = {}
    for response in spec.responses:
        options = getattr(response, "options", {}) or {}
        solver = options.get("openfoam_adjoint_solver_id")
        response_bindings[response.id] = str(solver) if solver else response.id

    volume_constraint = (
        VolumeOccupationConstraint(volume_budget.constraint_id, volume_budget.limit)
        if volume_budget is not None
        else None
    )
    return CompiledProblem(
        problem_spec_sha256=sha256 or problem_spec_sha256(spec),
        objectives=tuple(objectives),
        constraints=tuple(constraints),
        volume_constraint=volume_constraint,
        geometry_requirements=tuple(requirements),
        response_bindings=response_bindings,
    )


def _compile_terms(
    terms: Any,
    owner_id: str,
    responses: dict[str, Any],
    spec: Any,
) -> tuple[CompiledTerm, ...]:
    compiled: list[CompiledTerm] = []
    for term in terms:
        if term.coefficient == 0.0:
            continue
        response = responses.get(term.response_id)
        if response is None:
            raise ProblemCompileError(
                f"{owner_id!r} references undeclared response {term.response_id!r}"
            )
        if response.kind not in SUPPORTED_RESPONSE_KINDS:
            raise ProblemCompileError(
                f"response {response.id!r} has kind {response.kind!r}; the current "
                f"compiler supports {SUPPORTED_RESPONSE_KINDS} only"
            )
        if response.flow_case_id != term.flow_case_id:
            raise ProblemCompileError(
                f"{owner_id!r} binds response {response.id!r} to flow case "
                f"{term.flow_case_id!r} but the response is declared for "
                f"{response.flow_case_id!r}"
            )
        compiled.append(
            CompiledTerm(
                coefficient=float(term.coefficient),
                flow_case_id=term.flow_case_id,
                response_id=term.response_id,
            )
        )
    if not compiled:
        raise ProblemCompileError(f"{owner_id!r} has no non-zero terms")
    return tuple(compiled)


def _compile_topology_policy(spec: Any) -> list[GeometryRequirement]:
    policy = getattr(spec, "topology_policy", None)
    if policy is None:
        return []
    requirements: list[GeometryRequirement] = []
    for field_name in ("minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m"):
        value = getattr(policy, field_name, None)
        if value is not None:
            requirements.append(
                GeometryRequirement(
                    requirement_id=field_name,
                    kind="minimum_length_scale",
                    declared={"value_m": float(value)},
                )
            )
    for name in ("solid_connectivity", "void_connectivity"):
        connectivity = getattr(policy, name, None)
        if connectivity is None or connectivity.mode == "disabled":
            continue
        requirements.append(
            GeometryRequirement(
                requirement_id=f"{name}_connectivity",
                kind="connectivity",
                declared={
                    "mode": connectivity.mode,
                    "max_components": connectivity.max_components,
                    "evaluate_eroded": bool(connectivity.evaluate_eroded),
                    "required_root_group_ids": list(connectivity.required_root_group_ids),
                },
            )
        )
    return requirements


__all__ = [
    "CompiledConstraint",
    "CompiledObjective",
    "CompiledProblem",
    "CompiledTerm",
    "GeometryRequirement",
    "ProblemCompileError",
    "SUPPORTED_RESPONSE_KINDS",
    "VolumeBudget",
    "VolumeOccupationConstraint",
    "compile_problem",
]
