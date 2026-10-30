"""REINIT-04 (#28): the preregistered verdict rule on synthetic gate dicts, plus a fixture smoke of the measurement pipeline (not the canonical states)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
pytest.importorskip("skimage")
import reinit04_v17 as r  # noqa: E402

from cfd_sdf.design.geometry_gates_v2 import evaluate_geometry_gates_v2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402

OP_OK = {"eikonal_fluid_p50": {"passed": True}, "zero_level_displacement_edges_max": {"passed": True}}
IN_OK = {"sdf_distance_property": "pass", "min_feature_width": "pass", "volume_semantics": "pass", "near_zero_gradient_band": "fail"}


def verdict(op=OP_OK, inp=IN_OK, out=None, n_phi=8272):
    return r.state_verdict(op, inp, out or {**IN_OK, "near_zero_gradient_band": "fail"}, n_phi)


def test_all_pass_is_bounded_and_near_zero_gradient_band_is_excluded():
    assert verdict()["pass"] is True
    assert verdict(inp={**IN_OK, "near_zero_gradient_band": "pass"}, out={**IN_OK, "near_zero_gradient_band": "fail"})["pass"] is True


def test_gate_failing_on_the_input_is_not_required_on_the_output():
    assert verdict(inp={**IN_OK, "min_feature_width": "fail"}, out={**IN_OK, "min_feature_width": "fail"})["pass"] is True


def test_geom02_gate_passing_on_input_must_pass_on_output_and_unmeasured_blocks():
    for bad in ("fail", "unmeasured", None):
        out = {**IN_OK, "sdf_distance_property": bad}
        if bad is None:
            del out["sdf_distance_property"]
        assert verdict(out=out)["failed"] == ["geom02:sdf_distance_property"]


def test_operator_gate_and_count_failures_are_named_and_count_only_is_labelled():
    v = verdict(op={**OP_OK, "zero_level_displacement_edges_max": {"passed": False}})
    assert v["failed"] == ["operator:zero_level_displacement_edges_max"] and v["note"] is None
    v = verdict(n_phi=8273, out={**IN_OK, "volume_semantics": "fail"})
    assert v["pass"] is False and v["failed"] == ["geom02:volume_semantics", "n_phi"] and v["note"] == r.COUNT_BUDGET_NOTE
    assert verdict(op={**OP_OK, "eikonal_fluid_p50": {"passed": False}}, n_phi=8273)["note"] is None


def _state(parent_pass=True, baseline_pass=False):
    ok = {"verdict": {"pass": True, "failed": [], "note": None}}
    bad = {"verdict": {"pass": False, "failed": ["n_phi"], "note": None}}
    return {"baseline": ok if baseline_pass else bad, "lowdim03_parent": ok if parent_pass else bad}


def test_parent_alone_decides_and_baseline_is_reported_separately():
    d = r.decide(_state(parent_pass=True, baseline_pass=False))
    assert d["verdict"] == r.BOUNDED and d["baseline_separate"]["pass"] is False
    d = r.decide(_state(parent_pass=False, baseline_pass=True))
    assert d["verdict"] == r.NOT_BOUNDED and d["baseline_separate"]["pass"] is True


def test_incomplete_parent_is_incomplete_and_incomplete_baseline_does_not_decide():
    s = _state()
    assert r.decide({**s, "lowdim03_parent": {"incomplete": "ValueError: non-finite"}})["verdict"] == r.INCOMPLETE
    d = r.decide({**s, "baseline": {"incomplete": "RuntimeError: pin mismatch"}})
    assert d["verdict"] == r.BOUNDED and d["baseline_separate"] == {"incomplete": "RuntimeError: pin mismatch"}


def test_pipeline_smoke_on_a_fixture_box_is_serialisable_and_reports_every_field():
    h, shape = 0.05, (36, 28, 28)
    grid = np.stack(np.meshgrid(*[np.arange(n) for n in shape], indexing="ij"), axis=-1)
    q = np.abs(grid - np.array([16.0, 13.0, 13.0])) - np.array([8.2, 5.2, 5.2])
    phi = (np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(q.max(axis=-1), 0.0)) * h
    state = SDFDesignState.create(phi=phi.astype(np.float32), origin_m=(0.0, 0.0, 0.0), spacing_m=h, narrow_band_width_m=0.1)
    profile = {"profile_id": "test", "eikonal_median_tolerance": 0.10, "zero_level_gradient_floor": 0.5, "boundary_margin_cells": 1,
               "domain_bounds_m": [[-0.3, -0.3, -0.3], [2.05, 1.65, 1.65]], "min_clearance_m": 0.25, "max_solid_centers": 10**9,
               "lattice": {"origin_m": [0.0, 0.0, 0.0], "spacing_m": h, "node_shape": list(shape)}, "allowed_events": [], "birth_qualified": False,
               "export": {"refinement": 1, "small_component_min_bbox_diagonal_m": h, "self_intersection_tolerance_rel": 1e-12}}
    policy = SDFTopologyPolicyResearchV2(minimum_solid_width_m=1.5 * h, minimum_void_width_m=1.5 * h, minimum_gap_m=2.5 * h)
    bundle = evaluate_geometry_gates_v2(state, parent_state=state, profile=profile, policy=policy, export_mesh=r.canon.export_from_state(state, profile))
    doc, out = r.evaluate_state(state, bundle, profile, policy)
    json.dumps(doc, allow_nan=False)
    assert doc["output"]["state_sha256"] == out.state_sha256 != doc["input"]["state_sha256"]
    for key in ("operator_report", "zero_level_displacement", "n_phi", "geom02", "solid_side_eikonal", "export_mesh_signed_volume_m3", "gradient_floor_failing_nodes", "verdict"):
        assert key in doc
    assert set(doc["zero_level_displacement"]) >= {"degenerate", "non_degenerate"} and doc["n_phi"]["flipped_total"] == doc["n_phi"]["centres_lost"] + doc["n_phi"]["centres_gained"]
    assert doc["n_phi"]["signed_change"] == doc["n_phi"]["centres_gained"] - doc["n_phi"]["centres_lost"]
    assert set(doc["geom02"]["output_status"]) == set(doc["geom02"]["input_status"])
