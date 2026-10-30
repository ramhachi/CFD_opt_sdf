"""SDF topology policy contracts; these tests never invoke a flow solver."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import DEFAULT_TOPOLOGY_POLICY_ID, SDFDesignState
from cfd_sdf.design.topology_policy import (
    SDFTopologyFeatureMetrics,
    SDFTopologyPolicy,
    SDFTopologyPolicyError,
    classify_topology_events,
    evaluate_sdf_topology_transition,
)
from cfd_sdf.problem_spec import load_problem_spec


GENERIC_SPEC = ROOT / "examples/generic_problem_v2/project.yaml"
REGISTRATION = ROOT / "docs/evidence/sdf_topology_policy_v1_2026_09.json"


def _source_spec(*, minimum_solid_width_m: float | None = 0.01,
                 minimum_void_width_m: float | None = 0.012):
    source = load_problem_spec(GENERIC_SPEC)
    topology = replace(
        source.topology_policy,
        solid_connectivity=replace(
            source.topology_policy.solid_connectivity,
            evaluate_eroded=False,
        ),
        minimum_solid_width_m=minimum_solid_width_m,
        minimum_void_width_m=minimum_void_width_m,
        erosion_radius_m=None,
    )
    return replace(source, topology_policy=topology)


def _registered_policy() -> SDFTopologyPolicy:
    return SDFTopologyPolicy.from_problem_spec(_source_spec())


def _state(
    policy: SDFTopologyPolicy,
    solid: np.ndarray,
    root_mask: np.ndarray,
    *,
    forbidden_mask: np.ndarray | None = None,
    topology_policy_id: str | None = None,
) -> SDFDesignState:
    solid = np.asarray(solid, dtype=bool)
    root_mask = np.asarray(root_mask, dtype=bool)
    shape = solid.shape
    phi = np.where(solid, -0.1, 0.1).astype(np.float32)
    design_mask = np.ones(shape, dtype=bool)
    design_mask[root_mask] = False
    forbidden = np.zeros(shape, dtype=bool) if forbidden_mask is None else forbidden_mask
    return SDFDesignState.create(
        phi=phi,
        origin_m=(0.0, 0.0, 0.0),
        spacing_m=0.05,
        design_mask=design_mask,
        fixed_solid_mask=np.zeros(shape, dtype=bool),
        forbidden_mask=forbidden,
        root_mask=root_mask,
        narrow_band_width_m=0.1,
        topology_policy_id=topology_policy_id or policy.state_binding_id,
    )


def _root_fixture():
    policy = _registered_policy()
    root_mask = np.zeros((7, 5, 5), dtype=bool)
    root_mask[1, 2, 2] = True
    root_mask[5, 2, 2] = True
    solid = root_mask.copy()
    state = _state(policy, solid, root_mask)
    root_group_masks = {"mounts": root_mask.copy()}
    return policy, state, root_mask, root_group_masks


def _metrics(
    state: SDFDesignState,
    *,
    solid: float = 0.02,
    void: float = 0.02,
    gap: float | None = 0.02,
):
    return SDFTopologyFeatureMetrics(
        candidate_state_sha256=state.state_sha256,
        report_sha256="ab" * 32,
        minimum_solid_width_m=solid,
        minimum_void_width_m=void,
        minimum_gap_m=gap,
    )


def test_policy_hash_is_stable_and_binds_problem_spec_v2_topology_source():
    source = _source_spec()
    first = SDFTopologyPolicy.from_problem_spec(source)
    second = _registered_policy()
    assert first.policy_sha256 == second.policy_sha256
    assert first.to_dict() == second.to_dict()
    assert first.source_problem_spec_sha256 == second.source_problem_spec_sha256
    assert first.source_topology_policy_sha256 == second.source_topology_policy_sha256
    assert first.birth_enabled is False
    assert first.state_binding_id.endswith(first.policy_sha256)
    assert SDFTopologyPolicy.from_dict(first.to_dict(), source_problem=source) == first
    with pytest.raises(SDFTopologyPolicyError, match="source_problem is required"):
        SDFTopologyPolicy.from_dict(first.to_dict())

    changed = SDFTopologyPolicy.from_problem_spec(
        _source_spec(minimum_solid_width_m=0.015)
    )
    assert changed.policy_sha256 != first.policy_sha256
    assert changed.source_topology_policy_sha256 != first.source_topology_policy_sha256


def test_registered_policy_artifact_and_file_sidecar_are_hash_frozen():
    document = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    policy = document["policy"]
    assert SDFTopologyPolicy.unresolved_registration().to_dict() == policy
    assert SDFTopologyPolicy.from_dict(policy).to_dict() == policy
    expected_policy_hash = policy["policy_sha256"]
    hash_payload = {key: value for key, value in policy.items() if key != "policy_sha256"}
    actual_policy_hash = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   allow_nan=False).encode("utf-8")
    ).hexdigest()
    assert actual_policy_hash == expected_policy_hash
    sidecar = REGISTRATION.with_suffix(REGISTRATION.suffix + ".sha256")
    assert sidecar.read_text(encoding="utf-8").strip() == hashlib.sha256(
        REGISTRATION.read_bytes()
    ).hexdigest()
    assert document["v16_binding"]["qualification"] == "not_qualified"
    assert document["v16_binding"]["root_connectivity"] == "not_applicable"
    assert document["policy"]["birth_enabled"] is False


def test_policy_rejects_birth_enablement_and_missing_v2_root_or_feature_sources():
    with pytest.raises(SDFTopologyPolicyError, match="permanently disables"):
        SDFTopologyPolicy(
            source_problem_id=None,
            source_problem_spec_sha256=None,
            source_topology_policy_sha256=None,
            source_topology_policy=None,
            birth_enabled=True,
        )

    policy = SDFTopologyPolicy.from_problem_spec(
        _source_spec(minimum_solid_width_m=None, minimum_void_width_m=None)
    )
    assert not policy.birth_ready
    assert "minimum_solid_width_m" in policy.unresolved_birth_inputs()
    assert "minimum_void_width_m" in policy.unresolved_birth_inputs()

    unresolved = SDFTopologyPolicy.unresolved_registration()
    assert unresolved.unresolved_birth_inputs() == (
        "problem_spec_v2_source",
        "required_root_groups",
        "minimum_solid_width_m",
        "minimum_void_width_m",
    )


def test_separate_solid_components_are_allowed_only_when_each_has_a_root_owner():
    policy, current, root_mask, root_group_masks = _root_fixture()
    verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        current,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(current),
    )
    assert verdict.admissible
    assert verdict.proposed_component_count == 2
    assert verdict.component_root_owners == ((1, ("mounts",)), (2, ("mounts",)))

    unrooted = current.solid_mask.copy()
    unrooted[3, 0, 0] = True
    proposed = _state(policy, unrooted, root_mask)
    rejected = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(proposed),
    )
    assert "proposed_solid_component_unrooted" in rejected.violations
    assert "solid_component_count_exceeds_problem_spec_limit" in rejected.violations


def test_root_group_mask_ids_and_union_must_match_the_registered_binding():
    policy, current, root_mask, _ = _root_fixture()
    wrong_id = evaluate_sdf_topology_transition(
        policy,
        current,
        current,
        root_group_masks={"unregistered": root_mask.copy()},
        feature_metrics=_metrics(current),
    )
    assert "root_group_mask_ids_mismatch" in wrong_id.violations

    wrong_union = root_mask.copy()
    wrong_union[5, 2, 2] = False
    mismatched = evaluate_sdf_topology_transition(
        policy,
        current,
        current,
        root_group_masks={"mounts": wrong_union},
        feature_metrics=_metrics(current),
    )
    assert "root_group_masks_do_not_match_state_root_mask" in mismatched.violations


def test_mismatched_state_shapes_fail_closed_without_cross_grid_root_ownership():
    policy, current, _, _ = _root_fixture()
    proposed_root = np.zeros((6, 5, 5), dtype=bool)
    proposed_root[1, 2, 2] = True
    proposed_root[4, 2, 2] = True
    proposed = _state(policy, proposed_root.copy(), proposed_root)

    verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks={"mounts": proposed_root.copy()},
        feature_metrics=_metrics(proposed),
    )

    assert not verdict.admissible
    assert "state_grid_mismatch" in verdict.violations


def test_corner_contact_uses_the_registered_26_neighbour_convention():
    policy = _registered_policy()
    root_mask = np.zeros((5, 5, 5), dtype=bool)
    root_mask[1, 1, 1] = True
    current = _state(policy, root_mask.copy(), root_mask)
    proposed_solid = root_mask.copy()
    proposed_solid[2, 2, 2] = True
    proposed = _state(policy, proposed_solid, root_mask)
    assert classify_topology_events(current.solid_mask, proposed.solid_mask) == ()

    verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks={"mounts": root_mask.copy()},
        feature_metrics=_metrics(proposed),
    )
    assert verdict.admissible
    assert verdict.proposed_component_count == 1
    assert verdict.component_root_owners == ((1, ("mounts",)),)


@pytest.mark.parametrize(
    ("current_points", "proposed_points", "expected"),
    [
        (((1, 2, 2),), ((1, 2, 2), (5, 2, 2)), ("birth",)),
        (((1, 2, 2), (5, 2, 2)), tuple((x, 2, 2) for x in range(1, 6)), ("merge",)),
        (tuple((x, 2, 2) for x in range(1, 6)), ((1, 2, 2), (5, 2, 2)), ("split",)),
        (((1, 2, 2), (5, 2, 2)), ((1, 2, 2),), ("deletion",)),
    ],
)
def test_topology_event_classification_is_stable(current_points, proposed_points, expected):
    current = np.zeros((7, 5, 5), dtype=bool)
    proposed = np.zeros_like(current)
    for point in current_points:
        current[point] = True
    for point in proposed_points:
        proposed[point] = True
    assert classify_topology_events(current, proposed) == expected


def test_birth_and_component_deletion_are_fail_closed_events():
    policy, current, root_mask, root_group_masks = _root_fixture()
    birth_solid = current.solid_mask.copy()
    birth_solid[3, 0, 0] = True
    birth = _state(policy, birth_solid, root_mask)
    birth_verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        birth,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(birth),
    )
    assert "birth" in birth_verdict.detected_events
    assert "topology_birth_disabled" in birth_verdict.violations

    deletion_solid = current.solid_mask.copy()
    deletion_solid[5, 2, 2] = False
    deletion = _state(policy, deletion_solid, root_mask)
    deletion_verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        deletion,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(deletion),
    )
    assert "deletion" in deletion_verdict.detected_events
    assert "component_deletion_disabled" in deletion_verdict.violations
    assert "root_material_not_retained" in deletion_verdict.violations


def test_root_owned_merge_and_split_are_allowed_when_all_other_rules_pass():
    policy, current, root_mask, root_group_masks = _root_fixture()
    merged_solid = current.solid_mask.copy()
    merged_solid[2:5, 2, 2] = True
    merged = _state(policy, merged_solid, root_mask)
    merge_verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        merged,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(merged),
    )
    assert merge_verdict.admissible
    assert "merge" in merge_verdict.detected_events

    split_current = _state(policy, merged_solid, root_mask)
    split = _state(policy, current.solid_mask, root_mask)
    split_verdict = evaluate_sdf_topology_transition(
        policy,
        split_current,
        split,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(split),
    )
    assert split_verdict.admissible
    assert "split" in split_verdict.detected_events


def test_forbidden_material_and_minimum_feature_rules_reject_candidate():
    policy, current, root_mask, root_group_masks = _root_fixture()
    forbidden = np.zeros_like(root_mask)
    forbidden[3, 0, 0] = True
    current = _state(policy, current.solid_mask, root_mask, forbidden_mask=forbidden)
    forbidden_solid = current.solid_mask.copy()
    forbidden_solid[3, 0, 0] = True
    proposed = _state(policy, forbidden_solid, root_mask, forbidden_mask=forbidden)
    verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(proposed, solid=0.005, void=0.005),
    )
    assert "material_in_forbidden_mask" in verdict.violations
    assert "minimum_solid_width_violation" in verdict.violations
    assert "minimum_void_width_violation" in verdict.violations


def test_declared_minimum_gap_requires_candidate_measurement_and_enforces_limit():
    policy, current, root_mask, root_group_masks = _root_fixture()
    proposed = current

    missing = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(proposed, gap=None),
    )
    assert not missing.admissible
    assert "minimum_gap_measurement_missing" in missing.violations

    too_narrow = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(proposed, gap=0.005),
    )
    assert not too_narrow.admissible
    assert "minimum_gap_violation" in too_narrow.violations

    passing = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(proposed, gap=0.008),
    )
    assert passing.admissible


def test_feature_measurements_must_bind_to_the_exact_proposed_state_hash():
    policy, current, root_mask, root_group_masks = _root_fixture()
    proposed_solid = current.solid_mask.copy()
    proposed_solid[2:5, 2, 2] = True
    proposed = _state(policy, proposed_solid, root_mask)

    verdict = evaluate_sdf_topology_transition(
        policy,
        current,
        proposed,
        root_group_masks=root_group_masks,
        feature_metrics=_metrics(current),
    )

    assert not verdict.admissible
    assert "feature_measurements_state_hash_mismatch" in verdict.violations


def test_v16_empty_root_policy_is_unresolved_and_never_qualifies_birth():
    document = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    v16 = document["v16_binding"]
    assert v16["mask_cell_counts"] == {
        "fixed_solid": 0,
        "forbidden": 0,
        "root": 0,
    }
    assert v16["root_connectivity"] == "not_applicable"
    assert v16["qualification"] == "not_qualified"
    assert v16["topology_birth_qualified"] is False

    policy = SDFTopologyPolicy.unresolved_registration()
    empty = np.zeros((3, 3, 3), dtype=bool)
    state = SDFDesignState.create(
        phi=np.ones((3, 3, 3), dtype=np.float32),
        origin_m=(0.0, 0.0, 0.0),
        spacing_m=0.05,
        design_mask=np.ones((3, 3, 3), dtype=bool),
        fixed_solid_mask=empty.copy(),
        forbidden_mask=empty.copy(),
        root_mask=empty.copy(),
        narrow_band_width_m=0.1,
        topology_policy_id=DEFAULT_TOPOLOGY_POLICY_ID,
    )
    verdict = evaluate_sdf_topology_transition(
        policy,
        state,
        state,
        root_group_masks=None,
        feature_metrics=None,
    )
    assert not verdict.admissible
    assert "required_root_groups" in verdict.violations
    assert "minimum_solid_width_m" in verdict.violations
    assert "minimum_void_width_m" in verdict.violations
    assert "proposed_state_policy_hash_mismatch" in verdict.violations
