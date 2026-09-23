"""Regression tests: campaign runner fail-closed assertions and manifest v3."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, "src")

REPO = Path(__file__).resolve().parents[1]
from cfd_sdf import campaign_assertions as ca  # noqa: E402


def _manifest() -> dict:
    return {
        "schema_version": 4,
        "status": ca.STATUS_AWAITING_GO,
        "input_checkpoint": {"path": "work/pq3_3_volume_target/checkpoint_chunk02.json"},
        "problem_spec": {"path": "work/pq0_2_smoke/project_downforce_volume.yaml"},
        "compiled_problem_hash": "x" * 64,
        "canonical_grid": {"grid_sha256": "y" * 64},
        "openfoam_image": "opencfd/openfoam-default:2512",
        "template_tree_hash": "z" * 64,
        "solver_controls_hash": "a" * 64,
        "filter_radius_m": 0.15,
        "registered_target": 0.018,
        "v_max_projected": 0.07632566813424899,
        "b_q_schedule": [{"b": 4.0, "q": 15.0, "move_limit": 0.05}],
        "move_limit": 0.05,
        "objective_alpha_ladder": [1.0, 0.5, 0.25, 0.125, 0.0625],
        "volume_tolerance": 1e-4,
        "path_b_epsilon": 1e-4,
        "noise_calibration": {"path": "docs/evidence/pq3_3b_noise_calibration_2026_09.json"},
        "iteration_bounds": {"min": 1, "max": 40},
        "convergence_thresholds": {"objective": 1e-6, "volume_residual": 1e-4},
        "reject_stop_count": 8,
        "checkpoint_resume_rule": "sha256 chain accepted states only",
        "fresh_output_rule": "refuse when the output directory exists",
        "preflight_v4": {"path": "docs/evidence/pq3_3b_preflight_v4_2026_09.json"},
        "state_lineage": "previous_level.accepted_rho_sha256 == next_level.input_rho_sha256",
        "objective": {"sense": "maximize", "canonical": "J = -downforce"},
        "phase_1_backend": {"id": "projected-volume-restoration-oc"},
        "phase_2_backend": {"id": "volume-corrected-objective-oc"},
    }


def test_manifest_completeness_passes_when_all_hashes_present():
    ca.assert_manifest_complete(_manifest())


def test_manifest_missing_a_required_hash_fails():
    manifest = _manifest()
    manifest["solver_controls_hash"] = ""
    with pytest.raises(ValueError, match="solver_controls_hash"):
        ca.assert_manifest_complete(manifest)


def test_manifest_absolute_missing_field_fails():
    manifest = _manifest()
    del manifest["preflight_v4"]
    with pytest.raises(ValueError, match="preflight_v4"):
        ca.assert_manifest_complete(manifest)


def test_legacy_backend_is_refused():
    manifest = _manifest()
    manifest["phase_2_backend"] = {"id": "projected-volume-target-oc"}
    with pytest.raises(ValueError, match="legacy multiplicative"):
        ca.assert_no_legacy_backend(manifest)


def test_unregistered_phase1_backend_is_refused():
    manifest = _manifest()
    manifest["phase_1_backend"] = {"id": "someone-elses-backend"}
    with pytest.raises(ValueError, match="not the registered"):
        ca.assert_backend_ids(manifest)


def test_wrong_objective_sense_is_refused():
    manifest = _manifest()
    manifest["objective"] = {"sense": "minimize", "canonical": "J = +downforce"}
    with pytest.raises(ValueError, match="objective sense"):
        ca.assert_compiled_objective_sense(manifest)


def test_output_directory_already_exists_is_refused(tmp_path):
    ca.assert_fresh_output_directory(tmp_path / "fresh")
    with pytest.raises(ValueError, match="already exists"):
        ca.assert_fresh_output_directory(tmp_path)


def test_level_lineage_mismatch_is_refused():
    ca.assert_level_exact_rho_lineage("abc", "abc")
    with pytest.raises(ValueError, match="lineage broken"):
        ca.assert_level_exact_rho_lineage("abc", "def")


def test_path_b_bracket_sign_mismatch_fails():
    ok_bracket = {"ok": True, "reason": "descent_sign_match", "d_adj": -1.0, "d_fd": -1.0}
    assert ca.assert_path_b_bracket(ok_bracket) is True
    bad_bracket = {"ok": False, "reason": "not_a_descent_direction", "d_adj": 1.0, "d_fd": -1.0}
    with pytest.raises(ValueError, match="Path B"):
        ca.assert_path_b_bracket(bad_bracket)


def test_downforce_and_objective_improvement_gates():
    with pytest.raises(ValueError, match="raw downforce"):
        ca.assert_raw_downforce_improvement(0.5, 0.499, 1e-6)
    assert ca.assert_raw_downforce_improvement(0.5, 0.51, 1e-6)
    with pytest.raises(ValueError, match="canonical objective"):
        ca.assert_canonical_objective_improvement(-0.5, -0.499, 1e-6)
    assert ca.assert_canonical_objective_improvement(-0.5, -0.51, 1e-6)


def test_v_max_guard():
    with pytest.raises(ValueError, match="exceeded"):
        ca.assert_projected_volume_upper_bound(0.08, 0.0763)
    assert ca.assert_projected_volume_upper_bound(0.0763, 0.07632566813424899)


def _runner_module():
    spec = importlib.util.spec_from_file_location(
        "pq3_3b_campaign_runner", REPO / "scripts" / "pq3_3b_campaign_2026_09.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_refuses_to_start_when_manifest_is_blocked(tmp_path):
    module = _runner_module()
    output = tmp_path / "fresh-output"
    with pytest.raises(SystemExit, match="not awaiting the campaign go"):
        module.run_campaign(output)
    assert not output.exists()


def _accepted_fixture(tmp_path, monkeypatch):
    module = _runner_module()

    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    checkpoint = write_json(tmp_path / "checkpoint.json", {"rho": [0.2, 0.4]})
    spec = write_json(tmp_path / "spec.json", {"objective": "maximize_downforce"})
    grid = write_json(tmp_path / "grid.json", {"shape": [2, 1, 1]})
    preflight = write_json(tmp_path / "preflight.json", {"summary": {"preflight_pass": True}})
    noise = write_json(tmp_path / "noise.json", {"objective_noise_threshold": 1e-6})
    template = tmp_path / "template"
    template.mkdir()
    (template / "controlDict").write_text("endTime 100;", encoding="utf-8")
    manifest = _manifest()
    manifest.update({
        "compiled_problem_hash": "a" * 64,
        "input_checkpoint": {"path": str(checkpoint), "sha256": ca.sha256_file(checkpoint)},
        "input_rho_sha256": hashlib.sha256(np.asarray([0.2, 0.4], dtype=np.float64).tobytes()).hexdigest(),
        "problem_spec": {"path": str(spec), "sha256": ca.sha256_file(spec)},
        "canonical_grid": {"path": str(grid), "sha256": ca.sha256_file(grid)},
        "template_parent": {"path": str(template)},
        "template_tree_hash": ca.tree_sha256(template),
        "solver_controls": {"path": str(template)},
        "solver_controls_hash": ca.tree_sha256(template),
        "noise_calibration": {"path": str(noise), "sha256": ca.sha256_file(noise)},
        "preflight_v4": {"path": str(preflight), "sha256": ca.sha256_file(preflight)},
    })
    manifest_path = write_json(tmp_path / "manifest.json", manifest)
    manifest_sha = ca.sha256_file(manifest_path)
    sidecar = tmp_path / "manifest.json.sha256"
    sidecar.write_text(manifest_sha + "\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "MANIFEST", manifest_path)
    monkeypatch.setattr(module, "MANIFEST_SIDE_CAR", sidecar)
    monkeypatch.setattr(module, "PREFLIGHT_V4", preflight)
    monkeypatch.setattr(module, "NOISE", noise)
    return module, manifest_sha, manifest_path, spec, preflight


def test_accepted_fixture_checks_referenced_hashes_without_creating_output(tmp_path, monkeypatch):
    module, manifest_sha, _, spec, preflight = _accepted_fixture(tmp_path, monkeypatch)
    output = tmp_path / "campaign-output"
    assert module.verify_preconditions(output, expected_manifest_sha=manifest_sha)["status"] == ca.STATUS_AWAITING_GO
    with pytest.raises(NotImplementedError, match="not implemented"):
        module.run_campaign(output, expected_manifest_sha=manifest_sha)
    assert not output.exists()

    spec.write_text("modified", encoding="utf-8")
    with pytest.raises(ValueError, match="problem_spec.*SHA-256"):
        module.verify_preconditions(output, expected_manifest_sha=manifest_sha)
    spec.write_text(json.dumps({"objective": "maximize_downforce"}), encoding="utf-8")
    preflight.write_text("modified", encoding="utf-8")
    with pytest.raises(ValueError, match="preflight_v4.*SHA-256"):
        module.verify_preconditions(output, expected_manifest_sha=manifest_sha)
    assert not output.exists()


def test_runner_uses_pinned_manifest_sha_and_cli_run_output(tmp_path, monkeypatch):
    module, manifest_sha, _, _, _ = _accepted_fixture(tmp_path, monkeypatch)
    output = tmp_path / "campaign-output"
    with pytest.raises(SystemExit, match="pinned --manifest-sha"):
        module.verify_preconditions(output, expected_manifest_sha="0" * 64)
    monkeypatch.setattr(sys, "argv", [
        "pq3_3b_campaign_2026_09.py", "--run", "--manifest-sha", manifest_sha,
        "--output", str(output),
    ])
    with pytest.raises(NotImplementedError, match="not implemented"):
        module.main()
    assert not output.exists()
