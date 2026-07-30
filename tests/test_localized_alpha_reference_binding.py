from __future__ import annotations

import json

import numpy as np
import pytest

from cfd_sdf.localized_alpha_reference_binding import (
    calculate_localized_alpha_source,
    create_localized_alpha_reference_binding,
    load_and_verify_localized_alpha_reference_binding,
    read_localized_alpha_reference_binding,
    write_localized_alpha_reference_binding,
)
from cfd_sdf.localized_design_state_manifest import (
    LocalizedDesignGrid,
    create_localized_design_state_manifest,
    write_localized_design_state_manifest,
)
from cfd_sdf.localized_design_transfer import LocalizedDesignToCfdTransfer
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid


_PROBLEM_HASH = "a" * 64
_FILTER_HASH = "b" * 64
_PROJECTION_HASH = "c" * 64


def _state(root, *, rho_projected: np.ndarray, active_design_mask: np.ndarray | None = None):
    (root / "arrays").mkdir(parents=True)
    active = (
        np.array([True, True, False, False], dtype=np.bool_)
        if active_design_mask is None
        else np.asarray(active_design_mask, dtype=np.bool_)
    )
    masks = {
        "active_design_mask": active,
        "forbidden_mask": np.array([False, False, True, False], dtype=np.bool_),
        "fixed_solid_mask": np.array([False, False, False, True], dtype=np.bool_),
        "root_mask": np.array([False, False, False, True], dtype=np.bool_),
    }
    states = {
        "rho": rho_projected,
        "rho_filtered": rho_projected,
        "rho_projected": rho_projected,
    }
    mask_paths = {}
    state_paths = {}
    for identifier, values in masks.items():
        path = root / "arrays" / f"{identifier}.npy"
        np.save(path, values)
        mask_paths[identifier] = path.relative_to(root).as_posix()
    for identifier, values in states.items():
        path = root / "arrays" / f"{identifier}.npy"
        np.save(path, values)
        state_paths[identifier] = path.relative_to(root).as_posix()
    manifest = create_localized_design_state_manifest(
        path=root / "state.json",
        problem_spec_sha256=_PROBLEM_HASH,
        grid=LocalizedDesignGrid(
            origin=(0.0, 0.0, 0.0), spacing=(0.5, 0.5, 1.0), cell_shape=(2, 2, 1)
        ),
        masks=mask_paths,
        states=state_paths,
        filter_config_sha256=_FILTER_HASH,
        projection_config_sha256=_PROJECTION_HASH,
    )
    return write_localized_design_state_manifest(manifest)


def _fixture(tmp_path):
    reference_path = _state(
        tmp_path / "reference", rho_projected=np.array([0.2, 0.8, 0.0, 0.0], dtype=np.float64)
    )
    current_path = _state(
        tmp_path / "current", rho_projected=np.array([0.3, 0.7, 0.0, 0.0], dtype=np.float64)
    )
    cfd_grid = UniformCartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(0.5, 0.5, 1.0), cell_shape=(2, 2, 1)
    )
    alpha_path = tmp_path / "alpha_reference.npy"
    np.save(alpha_path, np.array([0.4, 0.6, 0.0, 0.0], dtype=np.float64))
    binding = create_localized_alpha_reference_binding(
        path=tmp_path / "alpha_reference_binding.json",
        reference_state_manifest_path=reference_path,
        cfd_grid=cfd_grid,
        alpha_reference_path=alpha_path,
        provenance={"source": "small-mock-reference", "raw_alpha_file_sha256": "d" * 64},
    )
    binding_path = write_localized_alpha_reference_binding(binding)
    # The transfer intentionally consumes the manifest's exact grid object.
    reference = load_and_verify_localized_alpha_reference_binding(binding_path)
    transfer = LocalizedDesignToCfdTransfer.build(
        cfd_grid=cfd_grid, design_grid=reference.reference_state.manifest.grid
    )
    return binding_path, reference_path, current_path, transfer


def test_reference_binding_round_trip_and_one_way_alpha_source(tmp_path) -> None:
    binding_path, reference_path, current_path, transfer = _fixture(tmp_path)

    binding = load_and_verify_localized_alpha_reference_binding(
        binding_path, expected_problem_spec_sha256=_PROBLEM_HASH
    )
    current = calculate_localized_alpha_source(
        binding=binding,
        current_state=read_localized_state(current_path),
        transfer=transfer,
    )
    reference = calculate_localized_alpha_source(
        binding=binding,
        current_state=read_localized_state(reference_path),
        transfer=transfer,
    )

    assert current.alpha.dtype == np.float64
    assert current.alpha == pytest.approx([0.5, 0.5, 0.0, 0.0])
    assert np.array_equal(reference.alpha, np.array([0.4, 0.6, 0.0, 0.0], dtype=np.float64))
    assert current.binding_sha256 == binding.binding.sha256
    assert len(current.alpha_sha256) == 64
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    assert raw["reference_rho_projected_sha256"] == binding.reference_state.manifest.states["rho_projected"].byte_sha256
    assert raw["provenance_sha256"] == binding.binding.provenance_sha256


def test_calculation_refuses_out_of_range_result_without_clipping(tmp_path) -> None:
    binding_path, _reference_path, _current_path, transfer = _fixture(tmp_path)
    out_of_range_path = _state(
        tmp_path / "out_of_range", rho_projected=np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float64)
    )
    with pytest.raises(ValueError, match="clipping is forbidden"):
        calculate_localized_alpha_source(
            binding=read_localized_alpha_reference_binding(binding_path),
            current_state=read_localized_state(out_of_range_path),
            transfer=transfer,
        )


def test_binding_refuses_tampered_alpha_provenance_and_path_escape(tmp_path) -> None:
    binding_path, _reference_path, _current_path, _transfer = _fixture(tmp_path)
    alpha_path = tmp_path / "alpha_reference.npy"
    np.save(alpha_path, np.array([0.4, 0.61, 0.0, 0.0], dtype=np.float64))
    with pytest.raises(ValueError, match="alpha reference hash mismatch"):
        load_and_verify_localized_alpha_reference_binding(binding_path)

    # Restore the original byte-bound alpha, then test untrusted sidecar text.
    np.save(alpha_path, np.array([0.4, 0.6, 0.0, 0.0], dtype=np.float64))
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    raw["provenance"]["source"] = "substituted"
    binding_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance hash mismatch"):
        load_and_verify_localized_alpha_reference_binding(binding_path)

    raw["provenance"]["source"] = "small-mock-reference"
    raw["reference_state_manifest_relative_path"] = "../escape.json"
    binding_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="safe relative path"):
        read_localized_alpha_reference_binding(binding_path)


def test_calculation_refuses_mismatched_transfer_or_current_mask_contract(tmp_path) -> None:
    binding_path, _reference_path, current_path, transfer = _fixture(tmp_path)
    binding = read_localized_alpha_reference_binding(binding_path)
    mismatched_grid = UniformCartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 0.5, 1.0), cell_shape=(1, 2, 1)
    )
    bad_transfer = LocalizedDesignToCfdTransfer.build(
        cfd_grid=mismatched_grid, design_grid=load_and_verify_localized_alpha_reference_binding(binding_path).reference_state.manifest.grid
    )
    with pytest.raises(ValueError, match="CFD grid"):
        calculate_localized_alpha_source(
            binding=binding, current_state=read_localized_state(current_path), transfer=bad_transfer
        )

    # A separately valid current manifest with different active topology is still not an allowed reference descendant.
    altered = _state(
        tmp_path / "changed-mask",
        rho_projected=np.array([0.3, 0.0, 0.0, 0.0], dtype=np.float64),
        active_design_mask=np.array([True, False, False, False], dtype=np.bool_),
    )
    with pytest.raises(ValueError, match="active_design_mask hash"):
        calculate_localized_alpha_source(
            binding=binding, current_state=read_localized_state(altered), transfer=transfer
        )


def read_localized_state(path):
    from cfd_sdf.localized_design_state_manifest import read_localized_design_state_manifest

    return read_localized_design_state_manifest(path)
