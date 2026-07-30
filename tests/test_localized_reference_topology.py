from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cfd_sdf.localized_design_state_manifest import LocalizedDesignGrid
from cfd_sdf.localized_reference_topology import (
    LOCALIZED_REFERENCE_TOPOLOGY_FILENAME,
    _Inputs,
    _evaluate_to_dict,
    _external_void_labels,
    evaluate_localized_reference_topology,
)
import cfd_sdf.localized_reference_topology as topology_module
from cfd_sdf.problem_spec import load_problem_spec


def test_one_cell_bridge_is_rejected(tmp_path: Path) -> None:
    spec = _project()
    grid = _grid((9, 7, 7))
    active = np.ones(grid.cell_count, dtype=bool)
    fixed = np.zeros_like(active)
    root = np.zeros_like(active)
    # Two thick blocks attached through a one-cell y/z bridge.
    s = np.zeros((7, 7, 9), dtype=bool)
    s[:, 1:6, :3] = True
    s[:, 3:4, 3:6] = True
    s[:, 1:6, 6:] = True
    root.reshape(s.shape)[3, 3, 0] = True
    root.reshape(s.shape)[3, 3, 8] = True
    fixed[:] = root
    rho = (s.ravel().astype(float))
    report = _evaluate_to_dict(spec, _bundle(tmp_path), _inputs(grid, active, np.zeros_like(active), fixed, root, rho), tmp_path / "work")
    assert report["status"] == "rejected"
    assert "minimum_solid_width" in report["reasons"]


def test_thick_solid_bar_passes_discrete_rules(tmp_path: Path) -> None:
    spec = _project()
    grid = _grid((11, 9, 9))
    active = np.ones(grid.cell_count, dtype=bool)
    fixed = np.zeros_like(active)
    root = np.zeros_like(active)
    s = np.ones((9, 9, 11), dtype=bool)
    root.reshape(s.shape)[:, :, 0] = True
    root.reshape(s.shape)[:, :, -1] = True
    fixed[:] = root
    report = _evaluate_to_dict(spec, _bundle(tmp_path), _inputs(grid, active, np.zeros_like(active), fixed, root, s.ravel().astype(float)), tmp_path / "work")
    assert report["status"] == "success"


def test_erosion_no_effect_is_rejected(tmp_path: Path) -> None:
    spec = _project()
    grid = _grid((7, 7, 7))
    active = np.zeros(grid.cell_count, dtype=bool)
    active.reshape((7, 7, 7))[3, 3, 3] = True
    root = np.zeros_like(active)
    root.reshape((7, 7, 7))[3, 3, 0] = True
    fixed = ~active
    # The sole mutable voxel is embedded in fixed solid, so exact erosion must
    # retain it.  This exercises the no-op guard without changing a radius.
    report = _evaluate_to_dict(spec, _bundle(tmp_path), _inputs(grid, active, np.zeros_like(active), fixed, root, np.ones(grid.cell_count)), tmp_path / "work")
    assert "erosion_no_effect" in report["reasons"]


def test_external_gap_and_enclosed_void_are_distinguished(tmp_path: Path) -> None:
    # A shell with an enclosed centre plus a tunnel to the exterior is labelled
    # through the same six-face calculation used by the evaluator.
    domain = np.ones((5, 5, 5), dtype=bool)
    void = np.zeros_like(domain)
    void[2, 2, 2] = True  # enclosed
    void[0, 1, 1] = True  # array-boundary external gap
    from scipy import ndimage
    labels, count = ndimage.label(void, structure=topology_module._STRUCTURE_6)
    external = _external_void_labels(labels, domain, count)
    assert not external[labels[2, 2, 2]]
    assert external[labels[0, 1, 1]]


def test_public_api_refuses_tampered_input_without_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, bundle = _fake_bundle(tmp_path, tampered=True)
    _patch_bundle_loaders(monkeypatch, bundle, root)
    out = tmp_path / "report"
    with pytest.raises(ValueError, match="non-finite"):
        evaluate_localized_reference_topology(_project(), reference_bundle_path=root, output_dir=out, disk_free_bytes=lambda _: 99 * 1024**3, available_memory_bytes=lambda: 99 * 1024**3)
    assert not out.exists()


def test_public_api_publishes_rejected_report_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, bundle = _fake_bundle(tmp_path, tampered=False)
    _patch_bundle_loaders(monkeypatch, bundle, root)
    out = tmp_path / "report"
    result = evaluate_localized_reference_topology(_project(), reference_bundle_path=root, output_dir=out, disk_free_bytes=lambda _: 99 * 1024**3, available_memory_bytes=lambda: 99 * 1024**3)
    assert result.status == "rejected"
    assert result.path == out / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME
    assert not list(tmp_path.glob(".report.tmp-*"))
    assert json.loads(result.path.read_text())["status"] == "rejected"


def test_public_api_resource_refusal_does_not_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, bundle = _fake_bundle(tmp_path, tampered=False)
    _patch_bundle_loaders(monkeypatch, bundle, root)
    out = tmp_path / "report"
    with pytest.raises(ValueError, match="10 GiB"):
        evaluate_localized_reference_topology(_project(), reference_bundle_path=root, output_dir=out, disk_free_bytes=lambda _: 0, available_memory_bytes=lambda: 99 * 1024**3)
    assert not out.exists()


def _project():
    return load_problem_spec(Path(__file__).parents[1] / "examples" / "g2_openfoam_compile" / "project.yaml")


def _grid(shape: tuple[int, int, int]) -> LocalizedDesignGrid:
    return LocalizedDesignGrid((0.0, 0.0, 0.0), (0.002, 0.002, 0.002), shape)


def _bundle(path: Path):
    return SimpleNamespace(path=path, state_manifest_sha256="s" * 64, raw_manifest_sha256="r" * 64,
                           initial_design_stl_sha256="i" * 64, geometry_snapshot=SimpleNamespace(sha256="g" * 64))


def _inputs(grid, active, forbidden, fixed, root, rho):
    return _Inputs(grid, active, forbidden, fixed, root, rho, "s" * 64,
                   {key: "0" * 64 for key in ("active_design_mask", "forbidden_mask", "fixed_solid_mask", "root_mask")}, "1" * 64)


def _fake_bundle(tmp_path: Path, *, tampered: bool):
    root = tmp_path / "bundle"; root.mkdir()
    grid = _grid((7, 7, 7)); n = grid.cell_count
    masks = {
        "active_design_mask": np.ones(n, dtype=bool), "forbidden_mask": np.zeros(n, dtype=bool),
        "fixed_solid_mask": np.zeros(n, dtype=bool), "root_mask": np.zeros(n, dtype=bool),
    }
    masks["root_mask"].reshape((7, 7, 7))[3, 3, 0] = True
    masks["fixed_solid_mask"][:] = masks["root_mask"]
    for name, values in masks.items(): np.save(root / f"{name}.npy", values)
    rho = np.full(n, np.nan if tampered else 0.0)
    np.save(root / "rho_projected.npy", rho)
    def artifact(name, values):
        path = root / f"{name}.npy"
        return SimpleNamespace(relative_path=path.name, byte_sha256=_sha(path))
    state = SimpleNamespace(
        grid=grid, sha256="s" * 64,
        masks={name: artifact(name, values) for name, values in masks.items()},
        states={"rho_projected": artifact("rho_projected", rho)},
    )
    bundle = SimpleNamespace(path=root, state_manifest_sha256="s" * 64, raw_manifest_sha256="r" * 64,
                             initial_design_stl_sha256="i" * 64, geometry_snapshot=SimpleNamespace(sha256="g" * 64))
    return root, (bundle, state)


def _patch_bundle_loaders(monkeypatch, bundle_and_state, root):
    bundle, state = bundle_and_state
    monkeypatch.setattr(topology_module, "verify_localized_reference_state_bundle", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(topology_module, "load_and_verify_localized_design_state_manifest", lambda *_args, **_kwargs: SimpleNamespace(manifest=state))
    monkeypatch.setattr(topology_module, "require_localized_design_state_manifest_v2", lambda value: value)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
