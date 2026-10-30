"""Research successor SDF topology policy (``sdf_topology_policy_v2_research``) and its fail-closed transition check (#31).

v1 (``topology_policy.py``, immutable) requires every solid component to touch a required root group.  The user's research decision (2026-10-02) allows detached
components and makes root connectivity optional; the event decision (2026-10-14, ``docs/issues/31_event_policy_decision_2026_10_14.md``) permits birth, split, merge
and whole-component deletion **in the policy**.  Policy permission is not execution permission: a step that must keep the topology passes ``allowed_events=()``, and
executing a birth needs its own qualification (``birth_qualified=True``, False by default).  Physical minimum widths and the source ProblemSpec binding stay unresolved (``None``) unless supplied; they are never
inferred from the grid or the observed shape, and an unresolved input makes every transition inadmissible (a partial decision cannot produce an admissibility PASS).
A resolved limit must be positive; a policy instance with resolved limits is a new content-addressed policy and needs its own registration.  The check judges solid components only:
changes of genus or of void topology (cavities, through-tunnels) are not detected here, and v1's void-connectivity and eroded-connectivity flags are not carried over (#29 owns them).
Explicit design/fixed/forbidden/root masks remain hard constraints.  A required support connection would need a separately registered physical specification.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import numbers
from typing import Any, Mapping

import numpy as np
from scipy import ndimage

from ..runtime.fingerprint import FingerprintError, validate_sha256_hex
from .sdf_state import SDFDesignState
from .topology_policy import (
    _EVENTS,
    _FULL_26_CONNECTED_3D,
    SDFTopologyAdmissibility,
    SDFTopologyFeatureMetrics,
    SDFTopologyPolicyError,
    _events_from_labels,
)

RESEARCH_POLICY_SCHEMA_VERSION = 2
RESEARCH_POLICY_ID = "sdf_topology_policy_v2_research"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _optional_length(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise SDFTopologyPolicyError(f"{name} must be None (unresolved) or a finite positive number")
    return float(value)


@dataclass(frozen=True)
class SDFTopologyPolicyResearchV2:
    """Immutable research policy: detached components allowed, root connectivity optional, all four events permitted by policy."""

    minimum_solid_width_m: float | None = None
    minimum_void_width_m: float | None = None
    minimum_gap_m: float | None = None
    max_components: int | None = None
    source_problem_id: str | None = None
    source_problem_spec_sha256: str | None = None
    permitted_events: tuple[str, ...] = _EVENTS
    schema_version: int = RESEARCH_POLICY_SCHEMA_VERSION
    policy_id: str = RESEARCH_POLICY_ID

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_POLICY_SCHEMA_VERSION or self.policy_id != RESEARCH_POLICY_ID:
            raise SDFTopologyPolicyError("unsupported research policy identity or schema version")
        for name in ("minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m"):
            object.__setattr__(self, name, _optional_length(name, getattr(self, name)))
        if self.max_components is not None and (isinstance(self.max_components, bool) or not isinstance(self.max_components, int) or self.max_components < 1):
            raise SDFTopologyPolicyError("max_components must be None or a positive integer")
        if isinstance(self.permitted_events, str) or not isinstance(self.permitted_events, (tuple, list)) or not all(isinstance(e, str) for e in self.permitted_events):
            raise SDFTopologyPolicyError("permitted_events must be a tuple of event names")
        events = tuple(self.permitted_events)
        if len(set(events)) != len(events) or not set(events) <= set(_EVENTS):
            raise SDFTopologyPolicyError("permitted_events must be distinct members of birth, merge, split, deletion")
        object.__setattr__(self, "permitted_events", tuple(name for name in _EVENTS if name in events))
        if (self.source_problem_id is None) != (self.source_problem_spec_sha256 is None):
            raise SDFTopologyPolicyError("source_problem_id and source_problem_spec_sha256 are bound together or both absent")
        if self.source_problem_spec_sha256 is not None:
            if not isinstance(self.source_problem_id, str) or not self.source_problem_id.strip():
                raise SDFTopologyPolicyError("source_problem_id must be non-empty")
            try:
                validate_sha256_hex(self.source_problem_spec_sha256, field_name="source_problem_spec_sha256")
            except FingerprintError as error:
                raise SDFTopologyPolicyError(str(error)) from error

    def unresolved_inputs(self) -> tuple[str, ...]:
        """Missing prerequisites of any admissibility PASS; never filled by inference."""

        missing = []
        if self.minimum_solid_width_m is None:
            missing.append("minimum_solid_width_m")
        if self.minimum_void_width_m is None:
            missing.append("minimum_void_width_m")
        if self.minimum_gap_m is None:  # detached components are allowed, so the inter-component gap (#29) must be specified too
            missing.append("minimum_gap_m")
        return tuple(missing)

    @property
    def policy_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_dict(include_sha256=False)).encode("utf-8")).hexdigest()

    @property
    def state_binding_id(self) -> str:
        return f"{self.policy_id}@sha256:{self.policy_sha256}"

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, Any]:
        content: dict[str, Any] = {
            "kind": "sdf_topology_policy",
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "supersedes_for_research": "sdf_topology_policy_v1 (immutable, unchanged; required root ownership)",
            "source_problem_spec_v2": None if self.source_problem_id is None else {"problem_id": self.source_problem_id, "problem_spec_sha256": self.source_problem_spec_sha256},
            "connectivity": {"solid_neighborhood": 26, "disconnected_components": "allowed", "root_connectivity": "optional",
                             "required_support_connection": "not inferable from an empty mask; needs a separately registered physical specification"},
            "hard_masks": {"material_allowed_where": ["design_mask", "fixed_solid_mask", "root_mask"], "retain_all_solid_cells_in": ["fixed_solid_mask", "root_mask"], "forbid_material_in": "forbidden_mask"},
            "minimum_features": {"minimum_solid_width_m": self.minimum_solid_width_m, "minimum_void_width_m": self.minimum_void_width_m, "minimum_gap_m": self.minimum_gap_m,
                                 "unresolved_values_are_never_inferred": True, "measurements_must_bind_to_candidate_state_sha256": True, "require_gap_measurement_if_declared": True},
            "topology_events": {name: ("permitted_by_policy" if name in self.permitted_events else "not_permitted") for name in _EVENTS},
            "event_semantics": "policy permission is not execution permission; a topology-fixed step passes allowed_events=() and a birth still needs its own qualification",
            "max_components": self.max_components,
            "empty_solid": "inadmissible",
            "unresolved_inputs": list(self.unresolved_inputs()),
        }
        if include_sha256:
            content["policy_sha256"] = hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()
        return content

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SDFTopologyPolicyResearchV2":
        """Parse an exact serialized policy; the canonical content (including the digest) must round-trip."""

        if not isinstance(value, Mapping):
            raise SDFTopologyPolicyError("serialized policy must be a mapping")
        source = value.get("source_problem_spec_v2")
        features, events = value.get("minimum_features"), value.get("topology_events")
        if (source is not None and not isinstance(source, Mapping)) or not isinstance(features, Mapping) or not isinstance(events, Mapping):
            raise SDFTopologyPolicyError("serialized policy is missing its feature or event sections")
        policy = cls(minimum_solid_width_m=features.get("minimum_solid_width_m"), minimum_void_width_m=features.get("minimum_void_width_m"), minimum_gap_m=features.get("minimum_gap_m"),
                     max_components=value.get("max_components"), source_problem_id=None if source is None else source.get("problem_id"),
                     source_problem_spec_sha256=None if source is None else source.get("problem_spec_sha256"),
                     permitted_events=tuple(name for name in _EVENTS if events.get(name) == "permitted_by_policy"))
        if _canonical_json(dict(value)) != _canonical_json(policy.to_dict()):
            raise SDFTopologyPolicyError("serialized policy does not match its canonical v2 research content")
        return policy


def evaluate_research_transition(
    policy: SDFTopologyPolicyResearchV2,
    current_state: SDFDesignState,
    proposed_state: SDFDesignState,
    *,
    feature_metrics: SDFTopologyFeatureMetrics | None,
    allowed_events: tuple[str, ...],
    birth_qualified: bool = False,
) -> SDFTopologyAdmissibility:
    """Check an existing proposal without mutating or generating either state; missing evidence is a rejection, never a pass.

    ``allowed_events`` is required (no default) and may only narrow the policy's permissions: pass ``()`` for a topology-fixed step.  A detected birth is rejected
    unless ``birth_qualified`` is True (topology birth is a separately qualified mechanism).  Only solid-component events are judged; cavities and tunnels are not.
    """

    if not isinstance(policy, SDFTopologyPolicyResearchV2):
        raise SDFTopologyPolicyError("policy must be SDFTopologyPolicyResearchV2")
    if not isinstance(current_state, SDFDesignState) or not isinstance(proposed_state, SDFDesignState):
        raise SDFTopologyPolicyError("current_state and proposed_state must be SDFDesignState")
    if isinstance(allowed_events, str) or not isinstance(allowed_events, (tuple, list)) or not all(isinstance(e, str) for e in allowed_events):
        raise SDFTopologyPolicyError("allowed_events must be a tuple of event names")
    if feature_metrics is not None and not isinstance(feature_metrics, SDFTopologyFeatureMetrics):
        raise SDFTopologyPolicyError("feature_metrics must be SDFTopologyFeatureMetrics or None")
    step_events = tuple(allowed_events)
    if not set(step_events) <= set(policy.permitted_events):
        raise SDFTopologyPolicyError("allowed_events may only narrow the policy's permitted events")
    violations: set[str] = set(policy.unresolved_inputs())
    for label, state in (("current", current_state), ("proposed", proposed_state)):
        if state.topology_policy_id != policy.state_binding_id:
            violations.add(f"{label}_state_policy_hash_mismatch")
    same_grid = (current_state.shape == proposed_state.shape and current_state.origin_m == proposed_state.origin_m and current_state.spacing_m == proposed_state.spacing_m)
    if not same_grid:
        violations.add("state_grid_mismatch")
    for mask_name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"):
        if not np.array_equal(getattr(current_state, mask_name), getattr(proposed_state, mask_name)):
            violations.add("state_mask_mismatch")
    current, proposed = current_state.solid_mask, proposed_state.solid_mask
    current_labels, current_count = ndimage.label(current, structure=_FULL_26_CONNECTED_3D)
    proposed_labels, proposed_count = ndimage.label(proposed, structure=_FULL_26_CONNECTED_3D)
    if current_count == 0:
        violations.add("current_solid_is_empty")
    if proposed_count == 0:
        violations.add("proposed_solid_is_empty")
    if current.shape != proposed.shape:
        violations.add("state_shape_mismatch")
        events: tuple[str, ...] = ()
    else:
        events = _events_from_labels(current_labels, current_count, proposed_labels, proposed_count)
    for name in events:
        if name not in step_events:
            violations.add(f"topology_event_not_permitted:{name}")
    if "birth" in events and birth_qualified is not True:
        violations.add("topology_birth_not_qualified")
    if same_grid and current.shape == proposed.shape:
        allowed = proposed_state.design_mask | proposed_state.fixed_solid_mask | proposed_state.root_mask
        if np.any(proposed & proposed_state.forbidden_mask):
            violations.add("material_in_forbidden_mask")
        if np.any(proposed & ~allowed):
            violations.add("material_outside_design_fixed_root_masks")
        if np.any(proposed_state.fixed_solid_mask & ~proposed):
            violations.add("fixed_solid_not_retained")
        if np.any(proposed_state.root_mask & ~proposed):
            violations.add("root_material_not_retained")
    if policy.max_components is not None and proposed_count > policy.max_components:
        violations.add("solid_component_count_exceeds_policy_limit")
    rooted = {int(x) for x in np.unique(proposed_labels[proposed_state.root_mask]) if x > 0} if proposed.shape == proposed_state.root_mask.shape else set()
    owners = tuple((label, ("root_mask",) if label in rooted else ()) for label in range(1, proposed_count + 1))  # informational only: root ownership is optional in this policy
    if feature_metrics is None:
        violations.add("feature_measurements_missing")
    else:
        if feature_metrics.candidate_state_sha256 != proposed_state.state_sha256:
            violations.add("feature_measurements_state_hash_mismatch")
        if policy.minimum_solid_width_m is not None and feature_metrics.minimum_solid_width_m < policy.minimum_solid_width_m:
            violations.add("minimum_solid_width_violation")
        if policy.minimum_void_width_m is not None and feature_metrics.minimum_void_width_m < policy.minimum_void_width_m:
            violations.add("minimum_void_width_violation")
        if policy.minimum_gap_m is not None:
            if feature_metrics.minimum_gap_m is None:
                violations.add("minimum_gap_measurement_missing")
            elif feature_metrics.minimum_gap_m < policy.minimum_gap_m:
                violations.add("minimum_gap_violation")
    return SDFTopologyAdmissibility(
        admissible=not violations,
        violations=tuple(sorted(violations)),
        detected_events=events,
        current_component_count=current_count,
        proposed_component_count=proposed_count,
        component_root_owners=owners,
    )


__all__ = [
    "RESEARCH_POLICY_ID",
    "RESEARCH_POLICY_SCHEMA_VERSION",
    "SDFTopologyPolicyResearchV2",
    "evaluate_research_transition",
]
