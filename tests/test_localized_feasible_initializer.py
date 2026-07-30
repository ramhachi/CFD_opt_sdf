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
    repair_raw_density_threshold_opening_legacy,
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


def test_legacy_raw_threshold_repair_is_explicitly_separate_from_support_buffer() -> None:
    grid = _grid()
    shape = (9, 9, 11)
    active = np.ones(grid.cell_count, dtype=bool).reshape(shape)
    root = np.zeros(grid.cell_count, dtype=bool).reshape(shape)
    active[:, :, 0] = False
    root[:, :, 0] = True
    raw = np.zeros(grid.cell_count, dtype=np.float64).reshape(shape)
    # One-cell-thick plate is below the unchanged 10 mm solid-width policy.
    raw[:, 4, 1:10] = 1.0

    repaired = repair_raw_density_threshold_opening_legacy(raw.ravel(), active.ravel(), root.ravel(), grid, _problem())

    repaired3 = repaired.reshape(shape)
    assert not np.any(repaired3[:, 4, 1:10])
    assert np.all(repaired3[:, :, 0] == 0.0)  # roots are topology material, never raw density.
    assert np.all(repaired[~active.ravel()] == 0.0)


def test_legacy_raw_threshold_gap_fill_remains_replay_only() -> None:
    grid = _grid()
    shape = (9, 9, 11)
    active = np.ones(grid.cell_count, dtype=bool).reshape(shape)
    root = np.zeros(grid.cell_count, dtype=bool).reshape(shape)
    active[:, :, 0] = False
    root[:, :, 0] = True
    raw = active.astype(np.float64)
    # This single exterior-facing void cell is below the unchanged 8 mm gap policy.
    raw[4, 4, 10] = 0.0

    repaired = repair_raw_density_threshold_opening_legacy(raw.ravel(), active.ravel(), root.ravel(), grid, _problem())

    assert repaired.reshape(shape)[4, 4, 10] == 1.0
    assert np.all(repaired[~active.ravel()] == 0.0)


def test_legacy_raw_threshold_repair_is_deterministic_float64_x_fastest_vector() -> None:
    grid = _grid()
    active = np.ones(grid.cell_count, dtype=bool)
    root = np.zeros(grid.cell_count, dtype=bool)
    active.reshape((9, 9, 11))[:, :, 0] = False
    root.reshape((9, 9, 11))[:, :, 0] = True
    raw = np.zeros(grid.cell_count, dtype=np.float64)
    raw.reshape((9, 9, 11))[2:7, 2:7, 1:10] = 1.0

    first = repair_raw_density_threshold_opening_legacy(raw, active, root, grid, _problem())
    second = repair_raw_density_threshold_opening_legacy(raw, active, root, grid, _problem())

    assert first.dtype == np.float64
    assert first.shape == (grid.cell_count,)
    assert np.array_equal(first, second)


def test_exact_positive_cone_support_repairs_projected_target_that_raw_only_write_cannot() -> None:
    # Radius 1.1 on a 1 m grid includes the target and its six face-neighbours.
    # A raw-threshold classification misses a projected target; setting the
    # *whole* positive support to zero forces it to the exact endpoint without
    # inverse projection.
    grid = LocalizedDesignGrid((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (5, 5, 5))
    n = grid.cell_count
    active = np.ones(n, dtype=np.bool_)
    center = np.ravel_multi_index((2, 2, 2), (5, 5, 5), order="C")
    target = np.zeros(n, dtype=np.bool_); target[center] = True
    metadata = initializer_module._mask_metadata(target) | {"mask": target}
    support, support_metadata = initializer_module._exact_positive_cone_support(
        metadata, active, grid, LocalizedConeFilterConfig(radius_m=1.1),
    )
    # A raw threshold operator sees this target as void (0.49) and cannot
    # repair the projected solid made by its positive-support neighbours.
    raw_only = np.ones(n, dtype=np.float64); raw_only[center] = 0.49
    raw_buffered = raw_only.copy(); raw_buffered[support] = 0.0
    projected_raw_only = apply_localized_heaviside_projection(
        apply_localized_cone_filter(raw_only, active, grid, config=LocalizedConeFilterConfig(radius_m=1.1)), active,
    )
    projected_buffered = apply_localized_heaviside_projection(
        apply_localized_cone_filter(raw_buffered, active, grid, config=LocalizedConeFilterConfig(radius_m=1.1)), active,
    )
    assert projected_raw_only[center] > 0.5
    assert projected_buffered[center] == 0.0
    assert raw_only[center] < 0.5
    assert support_metadata["buffer"]["count"] == 7
    assert support_metadata["kernel_sha256"]


def test_overlapping_remove_and_fill_supports_are_detectable_as_conflict() -> None:
    grid = LocalizedDesignGrid((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (5, 5, 5))
    n = grid.cell_count; active = np.ones(n, dtype=np.bool_)
    left = np.zeros(n, dtype=np.bool_); right = np.zeros(n, dtype=np.bool_)
    left[np.ravel_multi_index((2, 2, 2), (5, 5, 5), order="C")] = True
    right[np.ravel_multi_index((2, 2, 3), (5, 5, 5), order="C")] = True
    left_buffer, _ = initializer_module._exact_positive_cone_support(
        initializer_module._mask_metadata(left) | {"mask": left}, active, grid, LocalizedConeFilterConfig(radius_m=1.1),
    )
    right_buffer, _ = initializer_module._exact_positive_cone_support(
        initializer_module._mask_metadata(right) | {"mask": right}, active, grid, LocalizedConeFilterConfig(radius_m=1.1),
    )
    conflict = left_buffer & right_buffer
    assert np.count_nonzero(conflict) > 0
    assert initializer_module._mask_metadata(conflict)["first_index"] is not None


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


def test_tampered_raw_state_writes_failure_sidecar_and_never_publishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent, state = _small_parent_state(tmp_path)
    bundle = LocalizedReferenceStateBundle(parent, SimpleNamespace(sha256="g" * 64), state.sha256, "r" * 64, "i" * 64)
    monkeypatch.setattr(initializer_module, "verify_localized_reference_state_bundle", lambda *_args, **_kwargs: bundle)
    original_load = initializer_module._load_parent_arrays
    def tampered_load(*args, **kwargs):
        values = original_load(*args, **kwargs)
        values["rho"][0] = 1.0  # root/non-active cell: hard invariant violation.
        return values
    monkeypatch.setattr(initializer_module, "_load_parent_arrays", tampered_load)
    rejected = tmp_path / "direct-rejected.json"
    rejected.write_text(__import__("json").dumps({
        "kind": "localized_reference_topology_report", "status": "rejected",
        "reference_bundle_path": str(parent), "reference_state_manifest_sha256": state.sha256,
        "rho_projected_sha256": state.states["rho_projected"].byte_sha256,
    }), encoding="utf-8")

    destination = tmp_path / "derived-tampered"
    with pytest.raises(ValueError, match="outside active_design_mask"):
        build_localized_feasible_derived_state(
            _problem(), direct_reference_bundle_path=parent, rejected_topology_report_path=rejected, output_dir=destination,
        )
    assert not destination.exists()
    failure = initializer_module.localized_feasible_initializer_failure_report_path(destination)
    payload = __import__("json").loads(failure.read_text())
    assert payload["status"] == "rejected_no_feasible_bundle_published"
    assert payload["repair"]["failure_details"]["error_type"] == "ValueError"


def test_conflicting_support_buffers_fail_closed_without_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent, state = _small_parent_state(tmp_path)
    bundle = LocalizedReferenceStateBundle(parent, SimpleNamespace(sha256="g" * 64), state.sha256, "r" * 64, "i" * 64)
    monkeypatch.setattr(initializer_module, "verify_localized_reference_state_bundle", lambda *_args, **_kwargs: bundle)
    rejected = tmp_path / "direct-rejected.json"
    rejected.write_text(__import__("json").dumps({
        "kind": "localized_reference_topology_report", "status": "rejected",
        "reference_bundle_path": str(parent), "reference_state_manifest_sha256": state.sha256,
        "rho_projected_sha256": state.states["rho_projected"].byte_sha256,
    }), encoding="utf-8")
    n = state.grid.cell_count
    first_target = np.zeros(n, dtype=np.bool_); first_target[100] = True
    second_target = np.zeros(n, dtype=np.bool_); second_target[101] = True
    calls = iter((
        {"minimum_solid_width": initializer_module._mask_metadata(first_target) | {"mask": first_target},
         "minimum_gap": initializer_module._mask_metadata(np.zeros(n, dtype=np.bool_)) | {"mask": np.zeros(n, dtype=np.bool_)}},
        {"minimum_solid_width": initializer_module._mask_metadata(np.zeros(n, dtype=np.bool_)) | {"mask": np.zeros(n, dtype=np.bool_)},
         "minimum_gap": initializer_module._mask_metadata(second_target) | {"mask": second_target}},
    ))
    monkeypatch.setattr(initializer_module, "_checker_targets", lambda *_args, **_kwargs: next(calls))
    def rejected_evaluation(*args, **kwargs):
        raw = args[7]
        active = args[3]
        return raw.copy(), raw.copy(), {
            "status": "rejected", "reasons": ["minimum_solid_width"], "checks": {
                "minimum_solid_width": {"violation_count": 1, "first_violation_index": 100},
                "minimum_gap": {"violation_count": 0, "first_violation_index": None},
            },
        }
    monkeypatch.setattr(initializer_module, "_evaluate_candidate", rejected_evaluation)

    destination = tmp_path / "derived-conflict"
    with pytest.raises(ValueError, match="add_remove_support_conflict_rejected"):
        build_localized_feasible_derived_state(
            _problem(), direct_reference_bundle_path=parent, rejected_topology_report_path=rejected, output_dir=destination,
        )
    assert not destination.exists()
    payload = __import__("json").loads(initializer_module.localized_feasible_initializer_failure_report_path(destination).read_text())
    assert payload["repair"]["stop_reason"] == "add_remove_support_conflict_rejected"
    assert payload["repair"]["failure_details"]["conflict"]["count"] > 0


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
