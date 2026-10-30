"""Shared test helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# scripts/freeze_grad_ta1.py imports tomllib (Python >= 3.11) and is hash-pinned by the GRAD-TA1 freeze, so it cannot be edited;
# its test module (also pinned) is not collected on the 3.10 CI job instead.
collect_ignore = ["test_grad_ta1_kernel.py"] if sys.version_info < (3, 11) else []


def requires_work(*relpaths: str):
    """Skip unless every repo-root-relative path exists (``work/`` is gitignored, so a fresh clone or worktree lacks it)."""
    missing = [p for p in relpaths if not (REPO / p).exists()]
    return pytest.mark.skipif(bool(missing), reason=f"gitignored fixture not present: {', '.join(missing)}")


# The registration pins the *source file* of these tests by sha256, so they cannot carry a decorator; skip them by node id instead.
_PINNED_SOURCE_REQUIRES = {
    "tests/test_kaggle_sdf_directional_fd_v16.py::test_v17_flow24_prerequisites_use_registered_w3_w4_backend_identity": "work/sdf_native_genesis_v17/sdf_design_state.npz",
}


def pytest_collection_modifyitems(items):
    for item in items:
        if path := _PINNED_SOURCE_REQUIRES.get(item.nodeid):
            item.add_marker(requires_work(path))
