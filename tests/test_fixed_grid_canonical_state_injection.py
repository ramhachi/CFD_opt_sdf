from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from cfd_sdf.fixed_grid_canonical_state_injection import (
    inject_canonical_state_into_fixed_grid_contract,
)
from cfd_sdf.fixed_grid_contract import FIXED_GRID_CONTRACT_SCHEMA_VERSION
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid


_GRID_SHA256 = UniformCartesianCellGrid(
    origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(2, 1, 1), cell_order="x-fastest"
).sha256


def _array_sha256(values: np.ndarray) -> str:
    """Mirror fixed_grid_canonical_state_injection._array_sha256 exactly."""

    array = np.ascontiguousarray(values)
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)}, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


def _write_contract(directory: Path) -> Path:
    directory.mkdir(parents=True)
    image = pv.ImageData(dimensions=(3, 2, 2), spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))
    count = image.n_cells
    rho = np.asarray([0.3, 0.3], dtype=np.float32)
    active = np.asarray([0, 1], dtype=np.uint8)
    image.cell_data["rho"] = rho
    image.cell_data["rho_filtered"] = rho
    image.cell_data["rho_projected"] = rho
    image.cell_data["alpha"] = 2500.0 * rho
    image.cell_data["allowed_mask"] = np.ones(count, dtype=np.uint8)
    image.cell_data["forbidden_mask"] = np.zeros(count, dtype=np.uint8)
    image.cell_data["fixed_solid_mask"] = np.zeros(count, dtype=np.uint8)
    image.cell_data["root_mask"] = np.zeros(count, dtype=np.uint8)
    image.cell_data["active_design_mask"] = active
    image.field_data["schema_version"] = np.array([FIXED_GRID_CONTRACT_SCHEMA_VERSION], dtype=np.int32)
    image.field_data["kind"] = np.array(["fixed_grid_density"])
    image.field_data["cell_order"] = np.array(["vtk-x-fastest"])
    image.save(directory / "density.vti")

    state = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": {
            "location": "cell",
            "cell_order": "vtk-x-fastest",
            "origin": [0.0, 0.0, 0.0],
            "spacing": [1.0, 1.0, 1.0],
            "cell_shape": [2, 1, 1],
            "point_dimensions": [3, 2, 2],
            "cell_count": count,
            "bounds": [[0.0, 0.0, 0.0], [2.0, 1.0, 1.0]],
        },
        "density_vti": "density.vti",
        "array_metadata": {
            "alpha": {
                "units": "1/s",
                "location": "cell",
                "source": "2500 * OpenFOAM beta",
                "sign_convention": "non-negative Brinkman momentum penalization",
            },
        },
    }
    path = directory / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def _write_source_state(
    directory: Path,
    *,
    rho_xfastest: list[float],
    grid_sha256: str = _GRID_SHA256,
    cell_shape: list[int] | None = None,
    candidate_id: str = "candidate_0000",
) -> tuple[Path, Path]:
    """Write a real, self-consistent NPZ + provenance pair, as the candidate
    state transfer (openfoam_canonical_state_transfer.py) would."""

    directory.mkdir(parents=True, exist_ok=True)
    npz_path = directory / "openfoam_source_state.npz"
    rho_array = np.asarray(rho_xfastest, dtype=np.float64)
    global_labels = np.arange(rho_array.size, dtype=np.int64)
    payload = {
        "source_rho_xfastest": rho_array,
        "source_rho_global_label": rho_array.copy(),
        "source_global_cell_labels_by_xfastest": global_labels,
    }
    np.savez_compressed(npz_path, **payload)
    provenance = {
        "kind": "openfoam_canonical_state_transfer",
        "candidate_binding": {"candidate_id": candidate_id, "problem_id": "demo"},
        "target": {"grid_sha256": "a" * 64},
        "source": {
            "block_mesh": {"grid_sha256": grid_sha256},
            "cell_count": len(rho_xfastest),
            "origin": [0.0, 0.0, 0.0],
            "spacing": [1.0, 1.0, 1.0],
            "cell_shape": cell_shape or [2, 1, 1],
        },
        "artifact_file": {
            "path": npz_path.name,
            "sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest(),
        },
        "exported_arrays": {
            name: {"sha256": _array_sha256(values)} for name, values in payload.items()
        },
    }
    provenance_path = directory / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    return npz_path, provenance_path


def test_injection_overwrites_only_active_cells(tmp_path: Path) -> None:
    topology_state = _write_contract(tmp_path / "contract")
    npz_path, provenance_path = _write_source_state(tmp_path / "source_state", rho_xfastest=[0.9, 0.9])

    artifacts = inject_canonical_state_into_fixed_grid_contract(
        openfoam_source_state_npz=npz_path,
        source_state_provenance_json=provenance_path,
        topology_state_json=topology_state,
        output_directory=tmp_path / "new_contract",
    )

    new_rho = pv.read(artifacts.density_vti).cell_data["rho"]
    assert new_rho == pytest.approx([0.3, 0.9], abs=1.0e-6)
    # The input contract must be untouched.
    assert pv.read(topology_state.parent / "density.vti").cell_data["rho"] == pytest.approx([0.3, 0.3])

    provenance = json.loads(artifacts.provenance_json.read_text(encoding="utf-8"))
    assert provenance["overwritten_cell_count"] == 1
    assert provenance["active_design_mask"]["true_count"] == 1
    assert provenance["candidate_binding"]["candidate_id"] == "candidate_0000"
    assert provenance["rho_to_alpha_convention"]["source"] == "2500 * OpenFOAM beta"


def test_injection_rejects_grid_identity_mismatch(tmp_path: Path) -> None:
    topology_state = _write_contract(tmp_path / "contract")
    npz_path, provenance_path = _write_source_state(
        tmp_path / "source_state", rho_xfastest=[0.9, 0.9], grid_sha256="b" * 64
    )

    with pytest.raises(ValueError, match="grid_sha256"):
        inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=npz_path,
            source_state_provenance_json=provenance_path,
            topology_state_json=topology_state,
            output_directory=tmp_path / "new_contract",
        )
    assert not (tmp_path / "new_contract").exists()


def test_injection_rejects_out_of_range_rho(tmp_path: Path) -> None:
    topology_state = _write_contract(tmp_path / "contract")
    npz_path, provenance_path = _write_source_state(tmp_path / "source_state", rho_xfastest=[0.9, 1.5])

    with pytest.raises(ValueError, match="0 <= rho <= 1"):
        inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=npz_path,
            source_state_provenance_json=provenance_path,
            topology_state_json=topology_state,
            output_directory=tmp_path / "new_contract",
        )
    assert not (tmp_path / "new_contract").exists()


def test_injection_rejects_missing_provenance_hashes(tmp_path: Path) -> None:
    """Provenance lacking its own artifact/array hashes cannot bind an NPZ at all."""

    topology_state = _write_contract(tmp_path / "contract")
    directory = tmp_path / "source_state"
    directory.mkdir()
    npz_path = directory / "openfoam_source_state.npz"
    np.savez_compressed(npz_path, source_rho_xfastest=np.asarray([0.9, 0.9], dtype=np.float64))
    provenance_path = directory / "provenance.json"
    provenance_path.write_text(
        json.dumps(
            {
                "kind": "openfoam_canonical_state_transfer",
                "candidate_binding": {"candidate_id": "candidate_0000"},
                "source": {"block_mesh": {"grid_sha256": _GRID_SHA256}, "cell_count": 2,
                           "origin": [0.0, 0.0, 0.0], "spacing": [1.0, 1.0, 1.0], "cell_shape": [2, 1, 1]},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artifact_file hash"):
        inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=npz_path,
            source_state_provenance_json=provenance_path,
            topology_state_json=topology_state,
            output_directory=tmp_path / "new_contract",
        )
    assert not (tmp_path / "new_contract").exists()


def test_injection_rejects_one_byte_npz_tamper(tmp_path: Path) -> None:
    """C2 mutation test: a single changed byte in the NPZ must be refused."""

    topology_state = _write_contract(tmp_path / "contract")
    npz_path, provenance_path = _write_source_state(tmp_path / "source_state", rho_xfastest=[0.9, 0.9])

    raw = bytearray(npz_path.read_bytes())
    raw[-1] ^= 0x01
    npz_path.write_bytes(bytes(raw))

    with pytest.raises(ValueError, match="does not match the provenance that describes it"):
        inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=npz_path,
            source_state_provenance_json=provenance_path,
            topology_state_json=topology_state,
            output_directory=tmp_path / "new_contract",
        )
    assert not (tmp_path / "new_contract").exists()


def test_injection_rejects_provenance_swapped_from_another_candidate(tmp_path: Path) -> None:
    """C2 mutation test: reusing a different candidate's provenance.json is refused.

    This reproduces the audit's headline C2 defect: the loop wrote a fresh
    ``source_state.npz`` per trial but handed the injector the *initial*
    candidate's ``provenance.json`` every time.
    """

    topology_state = _write_contract(tmp_path / "contract")
    _initial_npz, initial_provenance = _write_source_state(
        tmp_path / "initial_candidate", rho_xfastest=[0.9, 0.9], candidate_id="candidate_0000"
    )
    other_npz, _other_provenance = _write_source_state(
        tmp_path / "other_candidate", rho_xfastest=[0.4, 0.6], candidate_id="candidate_0007"
    )

    with pytest.raises(ValueError, match="does not match the provenance that describes it"):
        inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=other_npz,
            source_state_provenance_json=initial_provenance,
            topology_state_json=topology_state,
            output_directory=tmp_path / "new_contract",
        )
    assert not (tmp_path / "new_contract").exists()


def test_injection_rejects_array_shape_tamper(tmp_path: Path) -> None:
    """C2 mutation test: a shape/dtype/order change in an exported array is refused,
    even though the NPZ file itself was rewritten (so a naive file-hash-only
    check would miss it) and the provenance's own recorded file hash is kept
    consistent with the tampered file."""

    topology_state = _write_contract(tmp_path / "contract")
    npz_path, provenance_path = _write_source_state(tmp_path / "source_state", rho_xfastest=[0.9, 0.9])

    with np.load(npz_path, allow_pickle=False) as payload:
        arrays = {name: payload[name] for name in payload.files}
    arrays["source_rho_xfastest"] = arrays["source_rho_xfastest"].astype(np.float32)
    np.savez_compressed(npz_path, **arrays)
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["artifact_file"]["sha256"] = hashlib.sha256(npz_path.read_bytes()).hexdigest()
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its provenance hash"):
        inject_canonical_state_into_fixed_grid_contract(
            openfoam_source_state_npz=npz_path,
            source_state_provenance_json=provenance_path,
            topology_state_json=topology_state,
            output_directory=tmp_path / "new_contract",
        )
    assert not (tmp_path / "new_contract").exists()
