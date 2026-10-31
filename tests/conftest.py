"""Shared test helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def requires_work(*relpaths: str):
    """Skip unless every repo-root-relative path exists (``work/`` is gitignored, so a fresh clone or worktree lacks it)."""
    missing = [p for p in relpaths if not (REPO / p).exists()]
    return pytest.mark.skipif(bool(missing), reason=f"gitignored fixture not present: {', '.join(missing)}")


# The registration pins the *source file* of these tests by sha256, so they cannot carry a decorator; skip them by node id instead.
_PINNED_SOURCE_REQUIRES = {
    "tests/test_kaggle_sdf_directional_fd_v16.py::test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity": "work/sdf_native_genesis_v17/sdf_design_state.npz",
}


# T2-0 tests whose fake-OpenFOAM pipeline still meshes with gmsh (scripts/t20_case.py), which is not a declared dependency; pinned like the above.
_PINNED_SOURCE_REQUIRES_GMSH = {
    "tests/test_t20a_kernel.py::test_run_case_orchestration_with_a_fake_openfoam",
    "tests/test_t20a_kernel.py::test_lm_runs_as_a_continuation_of_the_sst_stage",
    "tests/test_t20a_kernel.py::test_lm_divergence_is_a_result_with_diagnostics_not_a_kernel_failure",
    "tests/test_t20a_kernel.py::test_lm_limiter_rejected_at_startup_is_dropped_and_the_stage_rerun",
    "tests/test_t20a_kernel.py::test_mesh_only_registers_every_spec_at_every_height_and_runs_no_solver",
    "tests/test_t20c.py::test_zero_morph_is_byte_identical_and_initial_fields_are_the_generators",
    "tests/test_t20c.py::test_incidence_morph_reaches_the_generator_geometry",
    "tests/test_t20c.py::test_shape_modes_signs_ride_height_and_remeshed_contour",
    "tests/test_t20c.py::test_morph_assertion_failure_exits_nonzero",
}
_NO_GMSH = importlib.util.find_spec("gmsh") is None

# Pinned runners for Kaggle Linux / local Docker import POSIX-only modules (fcntl, resource); their tests cannot be imported on Windows.
collect_ignore = ["test_candidate_c_w2a_plan.py", "test_geom03.py", "test_xfid_gridphase_x2.py", "test_xfid_gridphase_x3.py"] if sys.platform == "win32" else []

# Exact replays of records produced on macOS arm64; Linux runners differ in the last float digit (as LOCAL-OF-01 found for the Python stack).
_PINNED_SOURCE_MACOS_BYTES = {
    "tests/test_p22_v17_volume_semantics_audit.py::test_reconstruction_and_frozen_comparison_replay",
    "tests/test_grid02_evidence.py::test_the_analysis_is_the_registered_one_and_reproduces_from_the_kept_output",
}

# Re-derives SCREEN-01 freeze 1 from the working tree and counts its 36 G1 raws; the 4 G2 raws registered after freeze 1 share
# inputs/, so it can only pass before G2. The written freeze1.json (36 raws) stays bound by freeze 2-3 and by `analyze_screen01.py main`.
_PINNED_SOURCE_PRE_SCREEN01_G2 = {"tests/screen01/test_screen01_build.py::test_freeze1_content"}
_SCREEN01_G2_DONE = (REPO / "docs/evidence/screen01_2026_10_30/states_g2.json").exists()

# SCREEN-01 tests that write or check a freeze record, whose environment pin reads the scikit-image version (the optional
# `geometry-gates` extra, which CI does not install; unpinned tests use importorskip("skimage") instead). Parametrizations included.
_PINNED_SOURCE_REQUIRES_SKIMAGE = {f"tests/screen01/test_screen01_{m}.py::test_{t}" for m, names in {
    "analyze": ("a_campaign_given_for_an_unneeded_group_and_the_loss_of_both_g1_kernels", "a_frozen_file_is_looked_up_by_its_repo_relative_key",
                "a_gate_row_with_an_error_makes_rs_refuse", "a_table_from_another_freeze_or_other_tools_is_refused",
                "budget_not_pushed_kernel_gives_incomplete_budget_whatever_the_other_data_show", "cli_main_with_not_pushed_and_lost_arguments",
                "handoff_content_and_its_file_checks", "handoff_of_an_axial_or_design_finalist_reads_the_p0_rows",
                "invalid_g1_stops_the_push_and_main_writes_the_invalid_outcome", "lost_declaration_must_cite_a_matching_record",
                "lost_kernel_cites_its_classification_record_through_the_pipeline", "main_refuses_freeze_3_that_disagrees_with_finalist_json",
                "main_without_a_finalist_binds_freeze_3_and_writes_once", "not_pushed_declarations_are_verified",
                "not_pushed_invalid_g1_with_a_clean_rs_json_is_refused_at_finalist", "pipeline_rs_finalist_main_gain_writes_once",
                "rederivation_accepts_a_1e10_float_perturbation_and_refuses_a_name_change", "the_freeze_chain_the_environment_and_the_fingerprint_are_checked"),
    "build": ("freeze1_record_is_accepted_by_the_analyzer", "freeze2_1_without_a_g2_campaign_needs_no_budget_or_smoke", "freeze2_2_1_and_3_records_in_order",
              "freeze3_is_written_without_f_for_a_null_finalist_and_for_invalid_at_step_2", "freeze_refuses_untracked_files_under_the_registered_directories"),
}.items() for t in names}
_NO_SKIMAGE = importlib.util.find_spec("skimage") is None


def pytest_collection_modifyitems(items):
    for item in items:
        if path := _PINNED_SOURCE_REQUIRES.get(item.nodeid):
            item.add_marker(requires_work(path))
        if _NO_GMSH and item.nodeid in _PINNED_SOURCE_REQUIRES_GMSH:
            item.add_marker(pytest.mark.skip(reason="gmsh not installed (not a declared dependency)"))
        if sys.platform != "darwin" and item.nodeid in _PINNED_SOURCE_MACOS_BYTES:
            item.add_marker(pytest.mark.skip(reason="byte replay of a macOS-produced record"))
        if _SCREEN01_G2_DONE and item.nodeid in _PINNED_SOURCE_PRE_SCREEN01_G2:
            item.add_marker(pytest.mark.skip(reason="re-derives SCREEN-01 freeze 1, which predates the registered G2 raws"))
        if _NO_SKIMAGE and item.nodeid.split("[")[0] in _PINNED_SOURCE_REQUIRES_SKIMAGE:
            item.add_marker(pytest.mark.skip(reason="scikit-image not installed (optional geometry-gates extra)"))
