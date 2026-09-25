"""Contract tests for the Stage S reduced-basis S0/S1 architecture."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_s_adjoint_qualification import active_var_ids  # noqa: E402
from cfd_sdf.stage_s_reduced_basis import (  # noqa: E402
    CANDIDATE_COUNT,
    EPSILON_LADDER_M,
    K_MODES,
    MIN_NORMAL_EFFICIENCY,
    canonical_sign,
    holdout_mode_directions,
    holdout_seed,
    mode_candidates,
    mode_sha256,
    mode_to_movement,
    normal_displacement,
    preserves_y_symmetry,
    sine_mode_vector,
)

MANIFEST = ROOT / "docs/evidence/stage_s_reduced_basis_fd_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_2026_09.json"
PRESERVED_FIRST = ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_scratch_reuse_error_2026_09.json"
PRESERVED_SECOND = ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_rate_gate_error_2026_09.json"
REDUCED_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar_reduced_basis_v1.yaml"


def test_mode_candidates_are_ordered_symmetric_and_distinct():
    candidates = mode_candidates(CANDIDATE_COUNT)
    assert len(candidates) == CANDIDATE_COUNT
    frequencies = [candidate.frequency for candidate in candidates]
    assert frequencies == sorted(frequencies)
    for candidate in candidates:
        assert preserves_y_symmetry(candidate.axis, candidate.b)
        assert 1 <= candidate.a <= 6 and 1 <= candidate.b <= 6 and 1 <= candidate.c <= 6
    ids = active_var_ids()
    vectors = [canonical_sign(sine_mode_vector(c, active_ids=ids))[0] for c in candidates[:8]]
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            assert not np.allclose(vectors[i], vectors[j])


def test_mode_vector_boundary_zero_and_movement_mapping():
    ids = active_var_ids()
    candidate = mode_candidates(1)[0]
    vector = sine_mode_vector(candidate, active_ids=ids)
    assert np.max(np.abs(vector)) == pytest.approx(1.0)
    movement = mode_to_movement(vector, active_ids=ids, coefficient=1.0e-3, sign=-1.0)
    assert movement.shape == (512, 3)
    assert np.max(np.abs(movement)) == pytest.approx(1.0e-3)
    for cp_id in range(512):
        k, remainder = divmod(cp_id, 64)
        j, i = divmod(remainder, 8)
        if i in (0, 7) or j in (0, 7) or k in (0, 7):
            assert np.max(np.abs(movement[cp_id])) == 0.0
    assert mode_sha256(vector) == mode_sha256(vector.copy())


def test_canonical_sign_and_holdout_determinism():
    values = np.asarray([0.0, -2.0, 1.0])
    flipped, was_flipped = canonical_sign(values)
    assert was_flipped is True
    assert flipped[np.argmax(np.abs(flipped))] > 0
    positive, was_flipped = canonical_sign(np.asarray([3.0, -1.0]))
    assert was_flipped is False
    first = holdout_seed("abc", 1)
    assert first == holdout_seed("abc", 1)
    assert first != holdout_seed("abc", 2)
    directions = holdout_mode_directions("abc", n_random=2)
    assert [entry["seed"] for entry in directions] == [holdout_seed("abc", 1), holdout_seed("abc", 2)]
    assert all(len(entry["values"]) == K_MODES for entry in directions)


def test_normal_displacement_on_a_translated_patch():
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64
    )
    faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    moved = vertices + np.asarray([0.0, 0.0, 2.5e-3])
    result = normal_displacement(base_vertices=vertices, faces=faces, moved_vertices=moved)
    assert result["point_count"] == 4
    assert result["max_abs_normal_displacement_m"] == pytest.approx(2.5e-3, rel=1e-6)


def test_registered_manifest_contract_and_reduced_spec():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["kind"] == "stage_s_reduced_basis_fd_manifest"
    assert manifest["architecture"]["id"] == "stage_s_reduced_basis_fd_v1"
    assert manifest["design_space"]["k_modes"] == K_MODES
    assert manifest["design_space"]["q_change_policy"].startswith("K is fixed")
    assert manifest["mode_generation"]["min_normal_efficiency"] == MIN_NORMAL_EFFICIENCY
    assert manifest["epsilon_ladder_m"] == list(EPSILON_LADDER_M)
    assert manifest["flags"] == {
        "original_adjoint_derivative_qualified": False,
        "reduced_basis_fd_qualified": "pending",
        "shape_update_allowed": False,
    }
    assert manifest["objective_contract"]["declared"] == "maximize downforce"
    assert manifest["objective_contract"]["canonical_J"] == "J = -downforce"
    assert manifest["objective_contract"]["drag"] == "report_only"
    assert manifest["budget"]["s1_flow_runs"] == 0
    for name, record in manifest["inputs"].items():
        if "sha256" in record:
            assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], name
    reduced = manifest["inputs"]["reduced_basis_problem_spec"]
    assert reduced["diff_keys"] == ["objectives", "problem_id"]
    assert ca.sha256_file(REDUCED_SPEC) == reduced["sha256"]
    spec = load_problem_spec(REDUCED_SPEC)
    objectives = {objective.id: objective for objective in spec.objectives}
    assert set(objectives) == {"maximize_downforce"}
    objective = objectives["maximize_downforce"]
    assert objective.sense == "maximize"
    assert [(term.response_id, float(term.coefficient)) for term in objective.terms] == [("downforce", 1.0)]
    assert spec.constraints == ()
    assert {response.id for response in spec.responses} == {"drag", "downforce"}


def test_registered_preflight_selects_sixteen_modes():
    manifest_sha = ca.sha256_file(MANIFEST)
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["manifest"]["sha256"] == manifest_sha
    summary = evidence["summary"]
    assert summary["n_modes_selected"] == K_MODES
    assert summary["all_preflight_pass"] is True
    assert summary["flow_campaign_allowed"] is True
    assert summary["reduced_basis_fd_qualified"] == "pending"
    assert summary["shape_update_allowed"] is False
    assert len(evidence["modes"]) == K_MODES
    orders = [record["order"] for record in evidence["modes"]]
    assert orders == list(range(1, K_MODES + 1))
    for record in evidence["modes"]:
        assert record["normal_efficiency"] >= MIN_NORMAL_EFFICIENCY
        assert record["realized_direction_cosine"] >= 0.999999
        assert record["preflight_plus_pass"] is True
        assert record["preflight_minus_pass"] is True
        for side in ("plus", "minus"):
            assert record["case_dirs"][side]
            assert record["max_abs_normal_displacement_%s_m" % side] == pytest.approx(
                1.0e-3, rel=1.0e-3
            )
    assert evidence["holdout_rule_preview"]["seeds"] == [
        entry["seed"] for entry in holdout_mode_directions(manifest_sha, n_random=2)
    ]
    correction = evidence["method_correction"]
    assert ca.sha256_file(PRESERVED_FIRST) == correction["preserved_attempts"][0]["sha256"]
    assert ca.sha256_file(PRESERVED_SECOND) == correction["preserved_attempts"][1]["sha256"]
    evaluated = [record["candidate"]["name"] for record in evidence["candidates"]]
    expected_order = [candidate.name for candidate in mode_candidates(CANDIDATE_COUNT)]
    assert evaluated == expected_order[: summary["n_candidates_evaluated"]]
