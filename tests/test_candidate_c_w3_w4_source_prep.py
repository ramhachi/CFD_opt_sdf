import json
import ast
import hashlib
from pathlib import Path
import importlib.util
import pytest


ROOT = Path(__file__).resolve().parents[1]
def test_candidate_c_kaggle_identities_are_separate_and_cpu_gpu_profile_unchanged():
    for track, kernel_suffix, dataset_id in (
        ("w3", "w3-v17-candidate-c", "ramhachi888/cfd-opt-sdf-v17-candidate-c"),
        ("w4", "w4-v17-candidate-c", "ramhachi888/cfd-opt-sdf-v17-w4-candidate-c"),
    ):
        metadata = json.loads((ROOT / f"infra/kaggle/kernel_{track}_v17_candidate_c/kernel-metadata.json").read_text())
        assert metadata["id"].endswith(kernel_suffix)
        assert metadata["dataset_sources"] == [dataset_id]
        assert metadata["enable_gpu"] is True
        assert metadata["machine_shape"] == "NvidiaTeslaT4"
        assert metadata["enable_internet"] is True


def test_w3_job_wraps_candidate_and_union_with_composite_candidate_c():
    source = (ROOT / "scripts/waterlily_w3_v17_candidate_c_job.jl").read_text()
    assert '"src", "CandidateCWaterLilyBody.jl"' in source
    assert "NormalFloorWaterLilyBody(device_grid" in source
    assert "candidate=CandidateCWaterLilyBody(floor_candidate;" in source
    assert "combined=CandidateCWaterLilyBody(floor_candidate, base_bodies.ground;" in source
    assert "C_TRANSITION_WIDTH = Float32(1.1444091796875e-4)" in source
    assert "normal_floor=0.25f0, transition_width=C_TRANSITION_WIDTH" in source
    assert "isbitstype(typeof(bodies.combined))" in source
    assert "OwnedV16Run(device_owner, bodies, sim)" in source


def test_w4_keeps_v17_four_case_matrix_and_uses_outer_composite_wrapper():
    source = (ROOT / "scripts/waterlily_w4_v17_candidate_c_job.jl").read_text()
    assert 'EXPECTED_CASE_IDS = ("flow_16", "flow_24", "flow_32", "domain_xplus1m_16")' in source
    assert "T_END = 120.0" in source and "BURN_IN = 80.0" in source and "SAMPLE_EVERY = 8" in source
    assert "candidate = CandidateCWaterLilyBody(floor_candidate;" in source
    assert "combined=CandidateCWaterLilyBody(floor_candidate, ground;" in source
    assert "C_TRANSITION_WIDTH = Float32(1.1444091796875e-4)" in source
    assert "body=bodies.combined" in source
    assert "OwnedV16Run(owner, bodies, sim)" in source
    assert "GC.@preserve owned begin" in source


def test_both_c_runners_require_the_composite_operator_identity():
    for path in (
        ROOT / "infra/kaggle/kernel_w3_v17_candidate_c/runner.py",
        ROOT / "infra/kaggle/kernel_w4_v17_candidate_c/runner.py",
        ROOT / "scripts/prepare_kaggle_w3_v17_candidate_c_dataset.py",
        ROOT / "scripts/prepare_kaggle_w4_v17_candidate_c_dataset.py",
    ):
        source = path.read_text()
        assert "load_candidate_c_identity" in source
        assert "operator_identity_record" in source
        assert "qualification_flags" in source
    for path in (
        ROOT / "scripts/verify_kaggle_w3_v17_candidate_c.py",
        ROOT / "scripts/verify_kaggle_w4_v17_candidate_c.py",
    ):
        assert path.is_file()
        source = path.read_text()
        assert "load_candidate_c_identity" in source
        assert '"topology"' in source and '"fd_oracle"' in source
    w4 = (ROOT / "infra/kaggle/kernel_w4_v17_candidate_c/runner.py").read_text()
    assert '"v17_candidate_c"' in w4
    assert '"w4_v17_candidate_c"' in w4


def _function_source(path, name):
    source = path.read_text()
    tree = ast.parse(source)
    node = next(item for item in tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    return ast.unparse(node)


def test_existing_gate_evaluators_and_w4_matrix_are_unchanged():
    pairs = (
        (ROOT / "infra/kaggle/kernel_w3/runner.py",
         ROOT / "infra/kaggle/kernel_w3_v17_candidate_c/runner.py"),
        (ROOT / "infra/kaggle/kernel_w4_v17/runner.py",
         ROOT / "infra/kaggle/kernel_w4_v17_candidate_c/runner.py"),
    )
    for original, candidate_c in pairs:
        assert _function_source(original, "evaluate_gates") == _function_source(candidate_c, "evaluate_gates")
    from importlib.util import module_from_spec, spec_from_file_location

    modules = []
    for name, path in (
        ("w4_v17", ROOT / "infra/kaggle/kernel_w4_v17/runner.py"),
        ("w4_v17_c", ROOT / "infra/kaggle/kernel_w4_v17_candidate_c/runner.py"),
    ):
        spec = spec_from_file_location(name, path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    assert modules[0].EXPECTED_CASES == modules[1].EXPECTED_CASES


def _load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_w3_c_remote_inventory_is_payload_only_and_rejects_extras(tmp_path):
    verifier = _load_script(
        "verify_w3_candidate_c_inventory",
        ROOT / "scripts/verify_kaggle_w3_v17_candidate_c.py")
    label = "v17_candidate_c"
    criteria_bytes = b'{"criteria":"registered"}\n'
    criteria_sha = hashlib.sha256(criteria_bytes).hexdigest()
    raw_name = "canonical_phi.f32"
    payload = {
        "sdf_design_state.npz": b"npz",
        raw_name: b"raw-phi",
        f"w3_{label}_criteria.json": criteria_bytes,
        f"w3_{label}_criteria.json.sha256": (criteria_sha + "\n").encode(),
    }
    for name, content in payload.items():
        (tmp_path / name).write_bytes(content)
    files = {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()}
    manifest = {
        "dataset_id": "ramhachi888/cfd-opt-sdf-v17-candidate-c",
        "criteria_sha256": criteria_sha,
        "files": files,
    }
    manifest_path = tmp_path / f"w3_{label}_dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    (tmp_path / "dataset-metadata.json").write_text('{"id":"config-only"}\n')
    criteria = {
        "geometry": {"state_label": label},
        "input_dataset_id": manifest["dataset_id"],
        "inputs": {
            "canonical_state_npz": {"sha256": files["sdf_design_state.npz"]},
            "canonical_phi_fortran_raw": {"path": raw_name, "sha256": files[raw_name]},
        },
    }
    remote = verifier.expected_remote_inventory(criteria, tmp_path, criteria_sha)
    assert remote == {
        **files,
        manifest_path.name: hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    assert "dataset-metadata.json" not in remote
    (tmp_path / "unexpected-legacy-helper.py").write_text("unexpected")
    with pytest.raises(ValueError, match="missing or extra files"):
        verifier.expected_remote_inventory(criteria, tmp_path, criteria_sha)


def test_w3_c_criteria_draft_preserves_v17_numeric_contract_and_false_flags():
    registrar = _load_script(
        "prepare_w3_candidate_c_criteria",
        ROOT / "scripts/prepare_kaggle_w3_v17_candidate_c_criteria.py")
    baseline = json.loads((ROOT / "docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json").read_text())
    draft = registrar.build_draft()
    assert draft["status"] == "draft_unregistered"
    assert draft["immutable"] is False
    assert draft["input_dataset_id"] == "ramhachi888/cfd-opt-sdf-v17-candidate-c"
    assert draft["operator"]["identity"] == "candidate_c_moment_blend+normal_floor_0.25"
    assert draft["qualification_flags"] == {name: False for name in (
        "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
    measurement = dict(draft["measurement"])
    measurement["force_integration_body"] = baseline["measurement"]["force_integration_body"]
    assert measurement == baseline["measurement"]
    backend = dict(draft["backend"])
    assert backend.pop("driver_version_policy") == "recorded_not_gated"
    backend["driver_version"] = backend.pop("driver_version_round1_reference")
    assert backend == baseline["backend"]
    assert draft["criteria_round"] == 2
    assert draft["profile_adapter"] == baseline["profile_adapter"]
    assert draft["acceptance"] == baseline["acceptance"]
    for name, path in (
        ("legacy_host_evaluator", "scripts/verify_kaggle_w3_v16.py"),
        ("operator_identity_dependency", "src/cfd_sdf/criteria_supersession.py"),
    ):
        assert draft["inputs"][name]["path"] == path
        assert draft["inputs"][name]["sha256"] == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_w4_c_draft_fails_closed_without_actual_w3_c_pass(tmp_path):
    registrar = _load_script(
        "prepare_w4_candidate_c_criteria",
        ROOT / "scripts/prepare_kaggle_w4_v17_candidate_c_criteria.py")
    with pytest.raises(ValueError, match="requires registered W3-C criteria"):
        registrar.build_draft(tmp_path / "missing-w3-criteria.json",
                              tmp_path / "missing-w3-result.json")
    source = (ROOT / "scripts/prepare_kaggle_w4_v17_candidate_c_criteria.py").read_text()
    assert '"legacy_host_evaluator": "scripts/verify_kaggle_w4_v16.py"' in source
    assert '"operator_identity_dependency": "src/cfd_sdf/criteria_supersession.py"' in source


def test_candidate_c_flags_reject_integer_zero_as_not_literal_false():
    expected = {name: False for name in (
        "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
    invalid = dict(expected, fd_oracle=0)
    for name, path in (
        ("verify_w3_candidate_c_flags", ROOT / "scripts/verify_kaggle_w3_v17_candidate_c.py"),
        ("verify_w4_candidate_c_flags", ROOT / "scripts/verify_kaggle_w4_v17_candidate_c.py"),
        ("prepare_w3_candidate_c_flags", ROOT / "scripts/prepare_kaggle_w3_v17_candidate_c_dataset.py"),
        ("prepare_w4_candidate_c_flags", ROOT / "scripts/prepare_kaggle_w4_v17_candidate_c_dataset.py"),
        ("kernel_w3_candidate_c_flags", ROOT / "infra/kaggle/kernel_w3_v17_candidate_c/runner.py"),
        ("kernel_w4_candidate_c_flags", ROOT / "infra/kaggle/kernel_w4_v17_candidate_c/runner.py"),
    ):
        module = _load_script(name, path)
        assert module.literal_false_flags(expected)
        assert not module.literal_false_flags(invalid)


def test_w3_c_runner_records_driver_without_gating_only_for_round2_policy():
    runner = _load_script("w3_c_runner_driver", ROOT / "infra/kaggle/kernel_w3_v17_candidate_c/runner.py")
    row = "0, Tesla T4, GPU-x, 15360 MiB, 580.178.04"
    assert runner.driver_matches({"driver_version_policy": "recorded_not_gated"}, row)
    assert not runner.driver_matches({"driver_version": "580.159.04"}, row)
    assert runner.driver_matches({"driver_version": "580.178.04"}, row)
