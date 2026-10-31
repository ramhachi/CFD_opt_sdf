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


def pytest_collection_modifyitems(items):
    for item in items:
        if path := _PINNED_SOURCE_REQUIRES.get(item.nodeid):
            item.add_marker(requires_work(path))
        if _NO_GMSH and item.nodeid in _PINNED_SOURCE_REQUIRES_GMSH:
            item.add_marker(pytest.mark.skip(reason="gmsh not installed (not a declared dependency)"))
        if sys.platform != "darwin" and item.nodeid in _PINNED_SOURCE_MACOS_BYTES:
            item.add_marker(pytest.mark.skip(reason="byte replay of a macOS-produced record"))
