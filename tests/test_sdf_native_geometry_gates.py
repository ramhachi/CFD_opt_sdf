"""Solver-free GEOM-01 contract checks; fixture thresholds are not canonical policy."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from cfd_sdf.design.geometry_gates import (
    GATE_IDS,
    _minimum_measure_gate,
    evaluate_geometry_gates,
    min_component_gap_m,
)
from cfd_sdf.design.sdf_state import DEFAULT_TOPOLOGY_POLICY_ID, SDFDesignState
from cfd_sdf.design.topology_policy import SDFTopologyPolicy
from cfd_sdf.design.volume_semantics import SMOOTHED_VOLUME_LIMIT_M3, sharp_volume_m3
from cfd_sdf.problem_spec import load_problem_spec

ROOT = Path(__file__).resolve().parents[1]
GENERIC_SPEC = ROOT / "examples/generic_problem_v2/project.yaml"
H = 0.05
SHAPE = (40, 30, 30)
FACE_OFFSET = 0.2


def _fixture_policy(solid=0.10, void=0.10, gap=0.10) -> SDFTopologyPolicy:
    source = load_problem_spec(GENERIC_SPEC)
    solid_connectivity = replace(
        source.topology_policy.solid_connectivity,
        evaluate_eroded=False,
        max_components=2,
    )
    topology = replace(
        source.topology_policy,
        solid_connectivity=solid_connectivity,
        minimum_solid_width_m=solid,
        minimum_void_width_m=void,
        minimum_gap_m=gap,
        erosion_radius_m=None,
    )
    return SDFTopologyPolicy.from_problem_spec(replace(source, topology_policy=topology))


def _box(lo, hi) -> np.ndarray:
    grid = np.stack(np.meshgrid(*[np.arange(n) for n in SHAPE], indexing="ij"), axis=-1)
    low, high = np.asarray(lo) - FACE_OFFSET, np.asarray(hi) + FACE_OFFSET
    q = np.abs(grid - (low + high) / 2.0) - (high - low) / 2.0
    return (np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(q.max(axis=-1), 0.0)) * H


def _shell(outer_lo, outer_hi, inner_lo, inner_hi) -> np.ndarray:
    """Bounded analytic solid and void regions for fixture-only thresholds."""
    return np.maximum(_box(outer_lo, outer_hi), -_box(inner_lo, inner_hi))


def _patch(lo, hi) -> np.ndarray:
    mask = np.zeros(SHAPE, dtype=bool)
    mask[lo[0] : hi[0] + 1, lo[1] : hi[1] + 1, lo[2] : hi[2] + 1] = True
    return mask


def _state(phi, root, *, policy, forbidden=None):
    return SDFDesignState.create(
        phi=np.asarray(phi, dtype=np.float32),
        origin_m=(0.0, 0.0, 0.0),
        spacing_m=H,
        design_mask=~root,
        forbidden_mask=forbidden,
        root_mask=root,
        narrow_band_width_m=0.1,
        topology_policy_id=policy.state_binding_id,
    )


def _evaluate(state, policy):
    return evaluate_geometry_gates(
        state,
        policy=policy,
        parent_state=state,
        root_group_masks={"mounts": state.root_mask.copy()},
        volume_limit_m3=sharp_volume_m3(state) * 1.05,
        min_clearance_m=0.25,
        eikonal_median_tolerance=0.15,
        low_gradient_norm_floor=1e-6,
        policy_scope="fixture_only",
    )


def test_clean_analytic_box_passes_the_fixture_only_gate_bundle():
    policy = _fixture_policy()
    root = _patch((8, 12, 12), (9, 14, 14))
    state = _state(
        _shell((7, 6, 6), (29, 23, 23), (11, 10, 10), (25, 19, 19)),
        root,
        policy=policy,
    )

    report = _evaluate(state, policy)

    assert tuple(report["gates"]) == GATE_IDS
    assert report["verdict"]["pass"] is True
    assert report["policy_scope"] == "fixture_only"
    assert report["gates"]["near_zero_gradient_band"]["status"] == "pass"
    assert report["state_sha256"] == state.state_sha256
    json.dumps(report, allow_nan=False)


def test_deliberate_forbidden_overlap_fails_the_mask_gate():
    policy = _fixture_policy()
    root = _patch((10, 12, 12), (12, 14, 14))
    forbidden = _patch((18, 12, 12), (18, 14, 14))
    state = _state(_box((10, 8, 10), (25, 20, 18)), root, policy=policy, forbidden=forbidden)

    report = _evaluate(state, policy)

    assert report["gates"]["mask_preservation"]["status"] == "fail"
    assert "material_in_forbidden_mask" in report["gates"]["mask_preservation"]["fail_reasons"]
    assert report["verdict"]["pass"] is False


def test_disconnected_canonical_components_are_counted_without_inventing_root_failure():
    policy = SDFTopologyPolicy.unresolved_registration()
    phi = np.minimum(_box((7, 7, 7), (13, 13, 13)), _box((24, 17, 17), (30, 23, 23)))
    state = _state(phi, np.zeros(SHAPE, dtype=bool), policy=policy)

    report = evaluate_geometry_gates(
        state,
        policy=policy,
        parent_state=state,
        root_group_masks=None,
        volume_limit_m3=SMOOTHED_VOLUME_LIMIT_M3,
        policy_scope="canonical_unresolved",
    )

    gate = report["gates"]["component_connectivity"]
    assert gate["measured"]["node_occupancy_components"] == 2
    assert gate["status"] == "unmeasured"
    assert not any("unrooted" in reason for reason in gate["fail_reasons"])


def test_sampled_width_measure_near_limit_is_unresolved():
    gate = _minimum_measure_gate(value=0.10, limit=0.10, guard_m=H / 4, label="solid_width")
    assert gate["status"] == "unmeasured"
    assert gate["fail_reasons"] == []


def test_cell_union_gap_has_expected_axis_aligned_cube_distance():
    labels = np.zeros((7, 3, 3), dtype=np.int8)
    labels[1, 1, 1] = 1
    labels[4, 1, 1] = 2
    assert min_component_gap_m(labels, 3, 0.05) == 0.10


def test_unresolved_canonical_policy_is_complete_but_not_qualified():
    state = SDFDesignState.load(ROOT / "docs/evidence/reinitialization_parent_review_2026_10_02/raw_round3/canonical_v16_input.npz")
    report = evaluate_geometry_gates(
        state,
        policy=SDFTopologyPolicy.unresolved_registration(),
        parent_state=state,
        root_group_masks=None,
        volume_limit_m3=SMOOTHED_VOLUME_LIMIT_M3,
        policy_scope="canonical_unresolved",
    )

    assert tuple(report["gates"]) == GATE_IDS
    assert report["verdict"]["pass"] is False
    assert report["policy_scope"] == "canonical_unresolved"
    assert report["gates"]["mask_preservation"]["status"] == "unmeasured"
    assert report["gates"]["component_connectivity"]["status"] == "unmeasured"
    assert report["gates"]["topology_change_classification"]["status"] == "unmeasured"
    assert report["gates"]["min_feature_width"]["status"] == "unmeasured"
    assert report["gates"]["inter_component_gap"]["status"] == "unmeasured"
    assert report["gates"]["domain_clearance"]["status"] == "unmeasured"
    assert report["gates"]["sdf_distance_property"]["status"] == "unmeasured"
    assert report["gates"]["near_zero_gradient_band"]["status"] == "unmeasured"
    assert report["gates"]["export_surface_integrity"]["status"] == "unmeasured"
    assert "voxel_cell_union_proxy" in report["gates"]["export_surface_integrity"]["measured"]
    assert report["gates"]["volume_semantics"]["status"] in {"pass", "fail"}
    json.dumps(report, allow_nan=False)
