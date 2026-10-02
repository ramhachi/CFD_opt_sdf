import json
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = {
    "identity": "candidate_c_moment_blend+normal_floor_0.25",
    "normal_floor": "0.25",
    "transition_width_solver": "1.1444091796875e-4",
    "simulation_body": "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid)+moving_ground)",
    "force_integration_body": "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))",
}


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
        for value in OPERATOR.values():
            assert value in source
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
