from __future__ import annotations

import json

import numpy as np
import pytest

from cfd_sdf.localized_design_state_manifest import (
    LOCALIZED_DESIGN_STATE_MANIFEST_KIND,
    LocalizedDesignGrid,
    create_localized_design_state_manifest,
    load_and_verify_localized_design_state_manifest,
    localized_design_state_manifest_sha256,
    read_localized_design_state_manifest,
    require_localized_design_state_manifest_v2,
    write_localized_design_state_manifest,
)
from cfd_sdf.localized_filter_projection import (
    LocalizedConeFilterConfig,
    LocalizedHeavisideProjectionConfig,
    write_canonical_filter_config,
    write_canonical_projection_config,
)


_HASH = "a" * 64
_FILTER_HASH = "b" * 64
_PROJECTION_HASH = "c" * 64


def _write_artifacts(root, *, masks=None, states=None) -> tuple[dict[str, str], dict[str, str]]:
    root.mkdir(exist_ok=True)
    (root / "arrays").mkdir(exist_ok=True)
    count = 4
    mask_values = {
        "active_design_mask": np.array([True, True, False, False], dtype=np.bool_),
        "forbidden_mask": np.array([False, False, True, False], dtype=np.bool_),
        "fixed_solid_mask": np.array([False, False, False, True], dtype=np.bool_),
        "root_mask": np.array([False, False, False, True], dtype=np.bool_),
    }
    state_values = {
        "rho": np.array([0.25, 0.75, 0.0, 0.0], dtype=np.float64),
        "rho_filtered": np.array([0.3, 0.7, 0.0, 0.0], dtype=np.float64),
        "rho_projected": np.array([0.2, 0.8, 0.0, 0.0], dtype=np.float64),
    }
    if masks:
        mask_values.update(masks)
    if states:
        state_values.update(states)
    mask_paths: dict[str, str] = {}
    state_paths: dict[str, str] = {}
    for identifier, values in mask_values.items():
        relative = f"arrays/{identifier}.npy"
        np.save(root / relative, values)
        mask_paths[identifier] = relative
    for identifier, values in state_values.items():
        relative = f"arrays/{identifier}.npy"
        np.save(root / relative, values)
        state_paths[identifier] = relative
    return mask_paths, state_paths


def _create(root, *, masks=None, states=None):
    mask_paths, state_paths = _write_artifacts(root, masks=masks, states=states)
    return create_localized_design_state_manifest(
        path=root / "localized_state.json",
        problem_spec_sha256=_HASH,
        grid=LocalizedDesignGrid(
            origin=(0.0, 0.0, 0.0), spacing=(0.002, 0.002, 0.002), cell_shape=(2, 2, 1)
        ),
        masks=mask_paths,
        states=state_paths,
        filter_config_sha256=_FILTER_HASH,
        projection_config_sha256=_PROJECTION_HASH,
    )


def test_round_trip_is_portable_deterministic_and_binds_all_artifacts(tmp_path) -> None:
    manifest = _create(tmp_path)
    assert manifest.kind == LOCALIZED_DESIGN_STATE_MANIFEST_KIND
    assert manifest.grid.cell_count == 4
    assert manifest.masks["active_design_mask"].dtype == "bool"
    assert manifest.states["rho"].dtype == "float64"
    assert manifest.masks["root_mask"].relative_path == "arrays/root_mask.npy"

    written = write_localized_design_state_manifest(manifest)
    parsed = read_localized_design_state_manifest(written)
    verified = load_and_verify_localized_design_state_manifest(written, expected_problem_spec_sha256=_HASH)
    assert verified.manifest.sha256 == localized_design_state_manifest_sha256(parsed)
    assert written.read_text(encoding="utf-8") == (
        json.dumps(json.loads(written.read_text(encoding="utf-8")), sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def test_verifier_rejects_file_tampering_even_if_npy_is_still_valid(tmp_path) -> None:
    manifest = _create(tmp_path)
    written = write_localized_design_state_manifest(manifest)
    np.save(tmp_path / "arrays/rho.npy", np.array([0.4, 0.6, 0.0, 0.0], dtype=np.float64))

    with pytest.raises(ValueError, match="hash mismatch: rho"):
        load_and_verify_localized_design_state_manifest(written)


@pytest.mark.parametrize(
    ("masks", "states", "message"),
    [
        (
            None,
            {"rho": np.array([0.2, 0.8, 0.2, 0.0], dtype=np.float64)},
            "exactly zero outside active_design_mask",
        ),
        (
            None,
            {"rho_filtered": np.array([0.2, 1.01, 0.0, 0.0], dtype=np.float64)},
            "finite values in",
        ),
        (
            {"active_design_mask": np.array([True, False, True, False], dtype=np.bool_)},
            None,
            "must not overlap forbidden_mask",
        ),
        (
            {"root_mask": np.array([True, False, False, False], dtype=np.bool_)},
            None,
            "must be a subset of fixed_solid_mask",
        ),
    ],
)
def test_create_fails_closed_for_state_and_mask_invariants(tmp_path, masks, states, message) -> None:
    with pytest.raises(ValueError, match=message):
        _create(tmp_path, masks=masks, states=states)


def test_create_refuses_wrong_dtype_and_artifacts_outside_portable_root(tmp_path) -> None:
    with pytest.raises(ValueError, match="dtype float64"):
        _create(tmp_path, states={"rho": np.ones(4, dtype=np.float32)})

    mask_paths, state_paths = _write_artifacts(tmp_path)
    outside = tmp_path.parent / "outside.npy"
    np.save(outside, np.zeros(4, dtype=np.float64))
    state_paths["rho"] = str(outside)
    with pytest.raises(ValueError, match="below manifest directory"):
        create_localized_design_state_manifest(
            path=tmp_path / "localized_state.json",
            problem_spec_sha256=_HASH,
            grid=LocalizedDesignGrid(
                origin=(0.0, 0.0, 0.0), spacing=(0.002, 0.002, 0.002), cell_shape=(2, 2, 1)
            ),
            masks=mask_paths,
            states=state_paths,
            filter_config_sha256=_FILTER_HASH,
            projection_config_sha256=_PROJECTION_HASH,
        )


def test_reader_refuses_path_escape_and_geometry_hash_mismatch(tmp_path) -> None:
    manifest = _create(tmp_path)
    written = write_localized_design_state_manifest(manifest)
    raw = json.loads(written.read_text(encoding="utf-8"))
    raw["masks"]["root_mask"]["relative_path"] = "../root.npy"
    written.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="safe relative path"):
        read_localized_design_state_manifest(written)

    raw["masks"]["root_mask"]["relative_path"] = "arrays/root_mask.npy"
    raw["grid_sha256"] = "0" * 64
    written.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="grid_sha256"):
        read_localized_design_state_manifest(written)


def test_schema_v2_binds_canonical_config_artifacts_and_v1_remains_readable(tmp_path) -> None:
    mask_paths, state_paths = _write_artifacts(tmp_path)
    filter_path = tmp_path / "filter_config.json"
    projection_path = tmp_path / "projection_config.json"
    filter_hash = write_canonical_filter_config(filter_path, LocalizedConeFilterConfig())
    projection_hash = write_canonical_projection_config(projection_path, LocalizedHeavisideProjectionConfig())
    manifest = create_localized_design_state_manifest(
        path=tmp_path / "v2.json",
        problem_spec_sha256=_HASH,
        grid=LocalizedDesignGrid(origin=(0.0, 0.0, 0.0), spacing=(.002, .002, .002), cell_shape=(2, 2, 1)),
        masks=mask_paths,
        states=state_paths,
        filter_config_sha256=filter_hash,
        projection_config_sha256=projection_hash,
        filter_config_path="filter_config.json",
        projection_config_path="projection_config.json",
    )
    path = write_localized_design_state_manifest(manifest)
    verified = load_and_verify_localized_design_state_manifest(path)
    assert verified.manifest.schema_version == 2
    assert require_localized_design_state_manifest_v2(verified).manifest.filter_config is not None
    # Old explicit hash-only artifacts still parse and validate; they simply
    # cannot become a full-resolution reference.
    v1 = _create(tmp_path / "v1")
    v1_path = write_localized_design_state_manifest(v1)
    with pytest.raises(ValueError, match="requires schema-v2"):
        require_localized_design_state_manifest_v2(load_and_verify_localized_design_state_manifest(v1_path))
    filter_path.write_text(filter_path.read_text(encoding="utf-8").replace("0.004", "0.005"), encoding="utf-8")
    with pytest.raises(ValueError, match="filter_config hash mismatch"):
        load_and_verify_localized_design_state_manifest(path)
