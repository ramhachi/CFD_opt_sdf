"""Solver-independent SDF topology policy and fail-closed transition checks.

This module adapts the existing ProblemSpec v2 topology policy rather than
introducing another source for root groups or minimum feature lengths.  It
does not propose, modify, or optimize an SDF; it only checks an already
constructed pair of immutable design states.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np
from scipy import ndimage

from ..problem_spec import (
    PROBLEM_SPEC_SCHEMA_VERSION,
    ConnectivityPolicySpec,
    ProblemSpec,
    RootGroupSpec,
    TopologyPolicySpec,
    problem_spec_sha256,
)
from ..runtime.fingerprint import FingerprintError, validate_sha256_hex
from .sdf_state import SDFDesignState


SDF_TOPOLOGY_POLICY_SCHEMA_VERSION = 1
SDF_TOPOLOGY_POLICY_ID = "sdf_topology_policy_v1"
# Match the repository's current Stage S component convention: face, edge,
# and corner neighbours are connected.
_FULL_26_CONNECTED_3D = np.ones((3, 3, 3), dtype=bool)
_ROOT_CONNECTIVITY_MODES = {"root_connected", "required_root_groups"}
_EVENTS = ("birth", "merge", "split", "deletion")


class SDFTopologyPolicyError(ValueError):
    """Invalid SDF topology policy or measurement input."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _connectivity_to_dict(policy: ConnectivityPolicySpec) -> dict[str, Any]:
    return {
        "mode": policy.mode,
        "required_root_group_ids": list(policy.required_root_group_ids),
        "max_components": policy.max_components,
        "evaluate_eroded": policy.evaluate_eroded,
    }


def _topology_policy_to_dict(policy: TopologyPolicySpec) -> dict[str, Any]:
    """Use the same semantic fields and names as ProblemSpec v2."""

    return {
        "root_groups": [
            {"id": group.id, "region_ids": list(group.region_ids)}
            for group in policy.root_groups
        ],
        "solid_connectivity": _connectivity_to_dict(policy.solid_connectivity),
        "void_connectivity": _connectivity_to_dict(policy.void_connectivity),
        "minimum_solid_width_m": policy.minimum_solid_width_m,
        "minimum_void_width_m": policy.minimum_void_width_m,
        "minimum_gap_m": policy.minimum_gap_m,
        "erosion_radius_m": policy.erosion_radius_m,
    }


@dataclass(frozen=True)
class SDFTopologyPolicy:
    """Immutable v1 SDF policy, linked to the source ProblemSpec by hashes.

    Missing source definitions are represented as ``None`` and surfaced by
    :meth:`unresolved_birth_inputs`; they never receive inferred defaults.
    ``birth_enabled`` is fixed false in v1.  The policy ID placed in a state is
    the content-addressed :attr:`state_binding_id`, not the bare version name.
    """

    source_problem_id: str | None
    source_problem_spec_sha256: str | None
    source_topology_policy_sha256: str | None
    source_topology_policy: TopologyPolicySpec | None
    schema_version: int = SDF_TOPOLOGY_POLICY_SCHEMA_VERSION
    policy_id: str = SDF_TOPOLOGY_POLICY_ID
    birth_enabled: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != SDF_TOPOLOGY_POLICY_SCHEMA_VERSION:
            raise SDFTopologyPolicyError("unsupported SDF topology policy schema version")
        if self.policy_id != SDF_TOPOLOGY_POLICY_ID:
            raise SDFTopologyPolicyError(f"policy_id must be {SDF_TOPOLOGY_POLICY_ID!r}")
        if self.birth_enabled is not False:
            raise SDFTopologyPolicyError("SDFTopologyPolicy v1 permanently disables topology birth")
        if self.source_topology_policy is None:
            if any(
                value is not None
                for value in (
                    self.source_problem_id,
                    self.source_problem_spec_sha256,
                    self.source_topology_policy_sha256,
                )
            ):
                raise SDFTopologyPolicyError(
                    "source problem identifiers and hashes require a source ProblemSpec policy"
                )
        else:
            if not isinstance(self.source_problem_id, str) or not self.source_problem_id.strip():
                raise SDFTopologyPolicyError("source_problem_id must be non-empty")
            for name, value in (
                ("source_problem_spec_sha256", self.source_problem_spec_sha256),
                ("source_topology_policy_sha256", self.source_topology_policy_sha256),
            ):
                try:
                    validate_sha256_hex(value, field_name=name)
                except FingerprintError as error:
                    raise SDFTopologyPolicyError(str(error)) from error
            expected = _sha256_json(_topology_policy_to_dict(self.source_topology_policy))
            if expected != self.source_topology_policy_sha256:
                raise SDFTopologyPolicyError(
                    "source_topology_policy_sha256 does not match the embedded ProblemSpec v2 policy"
                )
        if self.source_problem_spec_sha256 is not None:
            try:
                validate_sha256_hex(
                    self.source_problem_spec_sha256,
                    field_name="source_problem_spec_sha256",
                )
            except FingerprintError as error:
                raise SDFTopologyPolicyError(str(error)) from error

    @classmethod
    def from_problem_spec(cls, spec: ProblemSpec) -> "SDFTopologyPolicy":
        """Bind the v1 policy to a native ProblemSpec v2 topology definition."""

        if not isinstance(spec, ProblemSpec):
            raise SDFTopologyPolicyError("spec must be a ProblemSpec")
        if spec.schema_version != PROBLEM_SPEC_SCHEMA_VERSION or spec.migration.migrated:
            raise SDFTopologyPolicyError("SDF topology policy requires a native ProblemSpec v2")
        source_policy = spec.topology_policy
        source_policy_sha256 = _sha256_json(_topology_policy_to_dict(source_policy))
        return cls(
            source_problem_id=spec.problem_id,
            source_problem_spec_sha256=problem_spec_sha256(spec),
            source_topology_policy_sha256=source_policy_sha256,
            source_topology_policy=source_policy,
        )

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        source_problem: ProblemSpec | None = None,
    ) -> "SDFTopologyPolicy":
        """Parse the exact serialized policy, rechecking any v2 source digest.

        A resolved policy cannot be loaded without its source ProblemSpec:
        the full source digest must be recomputed instead of trusting a JSON
        field copied into a detached policy document.
        """

        if not isinstance(value, Mapping):
            raise SDFTopologyPolicyError("serialized policy must be a mapping")
        source = value.get("source_problem_spec_v2")
        if source is None:
            if source_problem is not None:
                raise SDFTopologyPolicyError(
                    "unresolved policy document cannot be paired with a source ProblemSpec"
                )
            policy = cls.unresolved_registration()
        else:
            if source_problem is None:
                raise SDFTopologyPolicyError(
                    "source_problem is required to verify a resolved policy document"
                )
            policy = cls.from_problem_spec(source_problem)
        if _canonical_json(dict(value)) != _canonical_json(policy.to_dict()):
            raise SDFTopologyPolicyError(
                "serialized policy does not match its canonical v1 content and source ProblemSpec"
            )
        return policy

    @classmethod
    def unresolved_registration(cls) -> "SDFTopologyPolicy":
        """The registered v1 semantics before a v16 source policy is available."""

        return cls(
            source_problem_id=None,
            source_problem_spec_sha256=None,
            source_topology_policy_sha256=None,
            source_topology_policy=None,
        )

    @property
    def source_root_groups(self) -> tuple[RootGroupSpec, ...]:
        if self.source_topology_policy is None:
            return ()
        return self.source_topology_policy.root_groups

    @property
    def required_root_group_ids(self) -> tuple[str, ...]:
        if self.source_topology_policy is None:
            return ()
        return self.source_topology_policy.solid_connectivity.required_root_group_ids

    @property
    def allow_disconnected_solid_components(self) -> bool:
        """v1 permits separate components only when each has a root owner."""

        return True

    @property
    def state_binding_id(self) -> str:
        return f"{self.policy_id}@sha256:{self.policy_sha256}"

    @property
    def policy_sha256(self) -> str:
        return _sha256_json(self.to_dict(include_sha256=False))

    @property
    def minimum_solid_width_m(self) -> float | None:
        return (
            None
            if self.source_topology_policy is None
            else self.source_topology_policy.minimum_solid_width_m
        )

    @property
    def minimum_void_width_m(self) -> float | None:
        return (
            None
            if self.source_topology_policy is None
            else self.source_topology_policy.minimum_void_width_m
        )

    @property
    def minimum_gap_m(self) -> float | None:
        return (
            None
            if self.source_topology_policy is None
            else self.source_topology_policy.minimum_gap_m
        )

    def unresolved_birth_inputs(self) -> tuple[str, ...]:
        """Return every missing or unsupported prerequisite for a birth check."""

        missing: list[str] = []
        if self.source_topology_policy is None:
            return (
                "problem_spec_v2_source",
                "required_root_groups",
                "minimum_solid_width_m",
                "minimum_void_width_m",
            )
        source = self.source_topology_policy
        if source.solid_connectivity.mode not in _ROOT_CONNECTIVITY_MODES:
            missing.append("solid_connectivity_root_mode")
        defined_group_ids = {group.id for group in source.root_groups}
        if not self.required_root_group_ids or not set(self.required_root_group_ids) <= defined_group_ids:
            missing.append("required_root_groups")
        if source.minimum_solid_width_m is None:
            missing.append("minimum_solid_width_m")
        if source.minimum_void_width_m is None:
            missing.append("minimum_void_width_m")
        if source.void_connectivity.mode != "disabled":
            missing.append("void_connectivity_evaluator")
        if source.solid_connectivity.evaluate_eroded or source.void_connectivity.evaluate_eroded:
            missing.append("eroded_connectivity_evaluator")
        return tuple(missing)

    @property
    def birth_ready(self) -> bool:
        return not self.unresolved_birth_inputs()

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, Any]:
        source: dict[str, Any] | None = None
        if self.source_topology_policy is not None:
            source = {
                "problem_id": self.source_problem_id,
                "problem_spec_sha256": self.source_problem_spec_sha256,
                "topology_policy_sha256": self.source_topology_policy_sha256,
                "topology_policy": _topology_policy_to_dict(self.source_topology_policy),
            }
        content: dict[str, Any] = {
            "kind": "sdf_topology_policy",
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "source_problem_spec_v2": source,
            "connectivity": {
                "solid_neighborhood": 26,
                "component_ownership": "each_component_intersects_at_least_one_required_root_group",
                "disconnected_components": "allowed_only_when_each_component_has_a_root_owner",
            },
            "hard_masks": {
                "material_allowed_where": ["design_mask", "fixed_solid_mask", "root_mask"],
                "retain_all_solid_cells_in": ["fixed_solid_mask", "root_mask"],
                "forbid_material_in": "forbidden_mask",
                "root_group_masks_union_must_equal": "root_mask",
            },
            "minimum_features": {
                "source": "ProblemSpec_v2.topology_policy",
                "minimum_solid_width_m": self.minimum_solid_width_m,
                "minimum_void_width_m": self.minimum_void_width_m,
                "minimum_gap_m": self.minimum_gap_m,
                "require_both_registered_values_for_birth": True,
                "measurements_must_bind_to_candidate_state_sha256": True,
                "require_gap_measurement_if_declared": True,
            },
            "topology_events": {
                "birth": "disabled",
                "merge": "allowed_if_all_other_rules_pass",
                "split": "allowed_if_each_resulting_component_has_a_root_owner",
                "deletion": "disabled",
            },
            "birth_enabled": self.birth_enabled,
            "birth_unresolved_inputs": list(self.unresolved_birth_inputs()),
        }
        if include_sha256:
            content["policy_sha256"] = _sha256_json(content)
        return content


@dataclass(frozen=True)
class SDFTopologyFeatureMetrics:
    """Measured candidate feature widths with state and report provenance."""

    candidate_state_sha256: str
    report_sha256: str
    minimum_solid_width_m: float
    minimum_void_width_m: float
    minimum_gap_m: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("candidate_state_sha256", self.candidate_state_sha256),
            ("report_sha256", self.report_sha256),
        ):
            try:
                validate_sha256_hex(value, field_name=name)
            except FingerprintError as error:
                raise SDFTopologyPolicyError(str(error)) from error
        for name, value in (
            ("minimum_solid_width_m", self.minimum_solid_width_m),
            ("minimum_void_width_m", self.minimum_void_width_m),
        ):
            if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0.0:
                raise SDFTopologyPolicyError(f"{name} must be finite and non-negative")
        if self.minimum_gap_m is not None and (
            isinstance(self.minimum_gap_m, bool)
            or not math.isfinite(float(self.minimum_gap_m))
            or float(self.minimum_gap_m) < 0.0
        ):
            raise SDFTopologyPolicyError("minimum_gap_m must be finite and non-negative")


@dataclass(frozen=True)
class SDFTopologyAdmissibility:
    """Read-only verdict for one proposed state transition."""

    admissible: bool
    violations: tuple[str, ...]
    detected_events: tuple[str, ...]
    current_component_count: int
    proposed_component_count: int
    component_root_owners: tuple[tuple[int, tuple[str, ...]], ...]
    evidence_class: str = "contract_and_capability"


def _events_from_labels(
    old_labels: np.ndarray,
    old_count: int,
    new_labels: np.ndarray,
    new_count: int,
) -> tuple[str, ...]:
    old_to_new: dict[int, set[int]] = {label: set() for label in range(1, old_count + 1)}
    new_to_old: dict[int, set[int]] = {label: set() for label in range(1, new_count + 1)}
    overlap = (old_labels > 0) & (new_labels > 0)
    if overlap.any():
        pairs = np.unique(np.stack((old_labels[overlap], new_labels[overlap]), axis=1), axis=0)
        for old_label, new_label in pairs:
            old_to_new[int(old_label)].add(int(new_label))
            new_to_old[int(new_label)].add(int(old_label))
    events: list[str] = []
    if any(not owners for owners in new_to_old.values()):
        events.append("birth")
    if any(not descendants for descendants in old_to_new.values()):
        events.append("deletion")
    if any(len(descendants) > 1 for descendants in old_to_new.values()):
        events.append("split")
    if any(len(ancestors) > 1 for ancestors in new_to_old.values()):
        events.append("merge")
    return tuple(name for name in _EVENTS if name in events)


def classify_topology_events(current_solid: np.ndarray, proposed_solid: np.ndarray) -> tuple[str, ...]:
    """Classify 26-neighbour solid-component births, merges, splits and deletions."""

    current = np.asarray(current_solid, dtype=bool)
    proposed = np.asarray(proposed_solid, dtype=bool)
    if current.ndim != 3 or proposed.shape != current.shape:
        raise SDFTopologyPolicyError("solid masks must be same-shape 3D arrays")
    old_labels, old_count = ndimage.label(current, structure=_FULL_26_CONNECTED_3D)
    new_labels, new_count = ndimage.label(proposed, structure=_FULL_26_CONNECTED_3D)
    return _events_from_labels(old_labels, old_count, new_labels, new_count)


def evaluate_sdf_topology_transition(
    policy: SDFTopologyPolicy,
    current_state: SDFDesignState,
    proposed_state: SDFDesignState,
    *,
    root_group_masks: Mapping[str, np.ndarray] | None,
    feature_metrics: SDFTopologyFeatureMetrics | None,
) -> SDFTopologyAdmissibility:
    """Check an existing proposal without mutating or generating either state.

    Root-group masks must be the source ProblemSpec v2 role masks projected by
    the registered genesis policy.  Feature metrics must already have been
    measured and bind to the exact proposed state hash.  Missing evidence is
    a rejection, never a pass.
    """

    if not isinstance(policy, SDFTopologyPolicy):
        raise SDFTopologyPolicyError("policy must be SDFTopologyPolicy")
    if not isinstance(current_state, SDFDesignState) or not isinstance(proposed_state, SDFDesignState):
        raise SDFTopologyPolicyError("current_state and proposed_state must be SDFDesignState")
    violations: set[str] = set(policy.unresolved_birth_inputs())
    if current_state.topology_policy_id != policy.state_binding_id:
        violations.add("current_state_policy_hash_mismatch")
    if proposed_state.topology_policy_id != policy.state_binding_id:
        violations.add("proposed_state_policy_hash_mismatch")
    same_grid = (
        current_state.shape == proposed_state.shape
        and current_state.origin_m == proposed_state.origin_m
        and current_state.spacing_m == proposed_state.spacing_m
    )
    if not same_grid:
        violations.add("state_grid_mismatch")
    for mask_name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"):
        if not np.array_equal(getattr(current_state, mask_name), getattr(proposed_state, mask_name)):
            violations.add("state_mask_mismatch")
    current = current_state.solid_mask
    proposed = proposed_state.solid_mask
    current_labels, current_count = ndimage.label(
        current, structure=_FULL_26_CONNECTED_3D
    )
    proposed_labels, proposed_count = ndimage.label(
        proposed, structure=_FULL_26_CONNECTED_3D
    )
    if current.shape != proposed.shape:
        violations.add("state_shape_mismatch")
        events: tuple[str, ...] = ()
    else:
        events = _events_from_labels(
            current_labels, current_count, proposed_labels, proposed_count
        )
    if "birth" in events and not policy.birth_enabled:
        violations.add("topology_birth_disabled")
    if "deletion" in events:
        violations.add("component_deletion_disabled")

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

    owners: list[tuple[int, tuple[str, ...]]] = []
    required_ids = policy.required_root_group_ids
    if required_ids:
        if root_group_masks is None:
            violations.add("root_group_masks_missing")
        elif set(root_group_masks) != set(required_ids):
            violations.add("root_group_mask_ids_mismatch")
        else:
            normalized: dict[str, np.ndarray] = {}
            for group_id in required_ids:
                mask = root_group_masks[group_id]
                if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_:
                    violations.add("root_group_mask_invalid")
                    continue
                if mask.shape != proposed_state.shape:
                    violations.add("root_group_mask_shape_mismatch")
                    continue
                normalized[group_id] = mask
            if len(normalized) == len(required_ids):
                union = np.zeros(proposed_state.shape, dtype=bool)
                for mask in normalized.values():
                    union |= mask
                if not union.any():
                    violations.add("required_root_mask_empty")
                if not np.array_equal(union, proposed_state.root_mask):
                    violations.add("root_group_masks_do_not_match_state_root_mask")
                states_to_check = (
                    (("current", current_labels, current_count),
                     ("proposed", proposed_labels, proposed_count))
                    if current.shape == proposed.shape
                    else (("proposed", proposed_labels, proposed_count),)
                )
                for state_label, labels, count in states_to_check:
                    if count == 0:
                        violations.add(f"{state_label}_solid_is_empty")
                    for label in range(1, count + 1):
                        component = labels == label
                        component_owners = tuple(
                            group_id
                            for group_id, mask in normalized.items()
                            if np.any(component & mask)
                        )
                        if not component_owners:
                            violations.add(f"{state_label}_solid_component_unrooted")
                        if state_label == "proposed":
                            owners.append((label, component_owners))
                if np.any(union & ~proposed):
                    violations.add("required_root_region_not_material")
    else:
        violations.add("required_root_groups_unresolved")

    source_policy = policy.source_topology_policy
    if source_policy is not None:
        maximum = source_policy.solid_connectivity.max_components
        if maximum is not None and proposed_count > maximum:
            violations.add("solid_component_count_exceeds_problem_spec_limit")

    if feature_metrics is None:
        violations.add("feature_measurements_missing")
    else:
        if feature_metrics.candidate_state_sha256 != proposed_state.state_sha256:
            violations.add("feature_measurements_state_hash_mismatch")
        if policy.minimum_solid_width_m is None:
            violations.add("minimum_solid_width_m_unresolved")
        elif feature_metrics.minimum_solid_width_m < policy.minimum_solid_width_m:
            violations.add("minimum_solid_width_violation")
        if policy.minimum_void_width_m is None:
            violations.add("minimum_void_width_m_unresolved")
        elif feature_metrics.minimum_void_width_m < policy.minimum_void_width_m:
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
        component_root_owners=tuple(owners),
    )


__all__ = [
    "SDF_TOPOLOGY_POLICY_ID",
    "SDF_TOPOLOGY_POLICY_SCHEMA_VERSION",
    "SDFTopologyAdmissibility",
    "SDFTopologyFeatureMetrics",
    "SDFTopologyPolicy",
    "SDFTopologyPolicyError",
    "classify_topology_events",
    "evaluate_sdf_topology_transition",
]
