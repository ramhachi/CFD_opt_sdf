from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cfd_sdf.localized_design_state_manifest import LocalizedDesignGrid
from cfd_sdf.localized_design_state_manifest import create_localized_design_state_manifest, write_localized_design_state_manifest
from cfd_sdf.localized_feasible_initializer import (
    LOCALIZED_FEASIBLE_DERIVED_STATE_FILENAME,
    build_localized_feasible_derived_state,
    repair_raw_density_forward_only,
)
from cfd_sdf.localized_filter_projection import (
    LocalizedConeFilterConfig,
    LocalizedHeavisideProjectionConfig,
    apply_localized_cone_filter,
    apply_localized_heaviside_projection,
    write_canonical_filter_config,
    write_canonical_projection_config,
)
from cfd_sdf.localized_reference_state_bundle import LocalizedReferenceStateBundle
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
import cfd_sdf.localized_feasible_initializer as initializer_module


def _problem():
    return load_problem_spec(Path(__file__).parents[1] / "examples" / "g2_openfoam_compile" / "project.yaml")


def _grid() -> LocalizedDesignGrid:
    return LocalizedDesignGrid((0.0, 0.0, 0.0), (0.002, 0.002, 0.002), (11, 9, 9))


def test_forward_repair_removes_thin_active_solid_and_preserves_root_boundary() -> None:
    grid = _grid()
    shape = (9, 9, 11)
    active = np.ones(grid.cell_count, dtype=bool).reshape(shape)
    root = np.zeros(grid.cell_count, dtype=bool).reshape(shape)
    active[:, :, 0] = False
    root[:, :, 0] = True
    raw = np.zeros(grid.cell_count, dtype=np.float64).reshape(shape)
    # One-cell-thick plate is below the unchanged 10 mm solid-width policy.
    raw[:, 4, 1:10] = 1.0

    repaired = repair_raw_density_forward_only(raw.ravel(), active.ravel(), root.ravel(), grid, _problem())

    repaired3 = repaired.reshape(shape)
    assert not np.any(repaired3[:, 4, 1:10])
    assert np.all(repaired3[:, :, 0] == 0.0)  # roots are topology material, never raw density.
    assert np.all(repaired[~active.ravel()] == 0.0)


def test_forward_repair_fills_narrow_external_gap_without_writing_outside_active() -> None:
    grid = _grid()
    shape = (9, 9, 11)
    active = np.ones(grid.cell_count, dtype=bool).reshape(shape)
    root = np.zeros(grid.cell_count, dtype=bool).reshape(shape)
    active[:, :, 0] = False
    root[:, :, 0] = True
    raw = active.astype(np.float64)
    # This single exterior-facing void cell is below the unchanged 8 mm gap policy.
    raw[4, 4, 10] = 0.0

    repaired = repair_raw_density_forward_only(raw.ravel(), active.ravel(), root.ravel(), grid, _problem())

    assert repaired.reshape(shape)[4, 4, 10] == 1.0
    assert np.all(repaired[~active.ravel()] == 0.0)


def test_forward_repair_is_deterministic_float64_x_fastest_vector() -> None:
    grid = _grid()
    active = np.ones(grid.cell_count, dtype=bool)
    root = np.zeros(grid.cell_count, dtype=bool)
    active.reshape((9, 9, 11))[:, :, 0] = False
    root.reshape((9, 9, 11))[:, :, 0] = True
    raw = np.zeros(grid.cell_count, dtype=np.float64)
    raw.reshape((9, 9, 11))[2:7, 2:7, 1:10] = 1.0

    first = repair_raw_density_forward_only(raw, active, root, grid, _problem())
    second = repair_raw_density_forward_only(raw, active, root, grid, _problem())

    assert first.dtype == np.float64
    assert first.shape == (grid.cell_count,)
    assert np.array_equal(first, second)


def test_successful_scaffold_keeps_parent_direct_evidence_and_prohibits_alpha_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent, state = _small_parent_state(tmp_path)
    bundle = LocalizedReferenceStateBundle(
        parent, SimpleNamespace(sha256="g" * 64), state.sha256, "r" * 64, "i" * 64,
    )
    monkeypatch.setattr(initializer_module, "verify_localized_reference_state_bundle", lambda *_args, **_kwargs: bundle)
    rejected = tmp_path / "direct-rejected.json"
    rejected.write_text(
        __import__("json").dumps({
            "kind": "localized_reference_topology_report", "status": "rejected",
            "reference_bundle_path": str(parent), "reference_state_manifest_sha256": state.sha256,
            "rho_projected_sha256": state.states["rho_projected"].byte_sha256,
        }), encoding="utf-8",
    )

    result = build_localized_feasible_derived_state(
        _problem(), direct_reference_bundle_path=parent, rejected_topology_report_path=rejected,
        output_dir=tmp_path / "derived",
    )

    ledger = __import__("json").loads((result.path / LOCALIZED_FEASIBLE_DERIVED_STATE_FILENAME).read_text())
    assert result.topology_report_path.is_file()
    assert ledger["initialization_kind"] == "constraint_aware_feasibility_projection"
    assert ledger["parent_rejected_topology_report_sha256"]
    assert ledger["alpha_reference"]["direct_stl_binding_reused"] is False
    assert ledger["repair"]["stop_reason"] == "topology_success"


def _small_parent_state(tmp_path: Path):
    parent = tmp_path / "parent"; geometry = parent / "geometry_snapshot"; geometry.mkdir(parents=True)
    grid = _grid(); shape = (9, 9, 11); n = grid.cell_count
    active = np.ones(n, dtype=bool).reshape(shape); root = np.zeros(n, dtype=bool).reshape(shape)
    active[:, :, 0] = False; root[:, :, 0] = True
    fixed = root.copy(); forbidden = np.zeros_like(active)
    masks = {"active_design_mask": active.ravel(), "forbidden_mask": forbidden.ravel(), "fixed_solid_mask": fixed.ravel(), "root_mask": root.ravel()}
    for name, values in masks.items(): np.save(geometry / f"{name}.npy", values)
    raw = active.ravel().astype(np.float64)
    filtered = apply_localized_cone_filter(raw, masks["active_design_mask"], grid, config=LocalizedConeFilterConfig())
    projected = apply_localized_heaviside_projection(filtered, masks["active_design_mask"], config=LocalizedHeavisideProjectionConfig())
    states = parent / "states"; states.mkdir()
    for name, values in (("rho", raw), ("rho_filtered", filtered), ("rho_projected", projected)):
        np.save(states / f"{name}.npy", values)
    configs = parent / "configs"; configs.mkdir()
    filter_hash = write_canonical_filter_config(configs / "filter_config.json", LocalizedConeFilterConfig())
    projection_hash = write_canonical_projection_config(configs / "projection_config.json", LocalizedHeavisideProjectionConfig())
    state = create_localized_design_state_manifest(
        path=parent / "localized_design_state_manifest.json", problem_spec_sha256=problem_spec_sha256(_problem()), grid=grid,
        masks={name: geometry / f"{name}.npy" for name in masks},
        states={name: states / f"{name}.npy" for name in ("rho", "rho_filtered", "rho_projected")},
        filter_config_sha256=filter_hash, projection_config_sha256=projection_hash,
        filter_config_path=configs / "filter_config.json", projection_config_path=configs / "projection_config.json",
    )
    write_localized_design_state_manifest(state)
    return parent, state
