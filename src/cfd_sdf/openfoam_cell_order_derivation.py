"""Derive the OpenFOAM global-cell-label permutation by measurement.

``source_global_cell_labels_by_xfastest.npy`` binds every x-fastest design-grid
index to the OpenFOAM global cell label that ``adjointOptimisationFoam``
actually assigned it.  blockMesh numbering is never assumed: this module
writes ``writeCellCentres`` on the reconstructed (serial) mesh, reads back the
resulting ``Cx``/``Cy``/``Cz`` volScalarFields in global-label order, and
matches each measured centre to its exact uniform-grid cell.  Any centre that
does not land on a cell centre, or any duplicate mapping, is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import numpy as np

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE
from .fixed_grid_sensitivity import read_openfoam_vol_scalar_field
from .openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from .openfoam_grid_transfer import UniformCartesianCellGrid, load_openfoam_cell_order_mapping


_ARTIFACT_KIND = "openfoam_cell_order_derivation"
_ARTIFACT_SCHEMA_VERSION = 1
_MAPPING_FILE_NAME = "source_global_cell_labels_by_xfastest.npy"


@dataclass(frozen=True)
class OpenFoamCellOrderDerivationArtifacts:
    """Paths to one atomically written cell-order mapping artifact set."""

    directory: Path
    mapping_npy: Path
    provenance_json: Path


def derive_and_write_openfoam_cell_order_mapping(
    case_dir: str | Path,
    *,
    block_mesh_dict: str | Path,
    output_directory: str | Path,
    time_name: str = "0",
    execute: bool = True,
    backend: str = "auto",
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
    timeout_seconds: int | None = None,
    tolerance_cells: float = 1.0e-6,
) -> OpenFoamCellOrderDerivationArtifacts:
    """Measure OpenFOAM cell centres and write the x-fastest label mapping.

    ``execute=False`` is an escape hatch for tests and cases where
    ``writeCellCentres`` has already been run: ``time_name`` must already
    contain ``Cx``/``Cy``/``Cz`` and no OpenFOAM process is started.
    """

    if tolerance_cells <= 0.0:
        raise ValueError("tolerance_cells must be positive")
    case = Path(case_dir).resolve()
    if not case.is_dir():
        raise ValueError(f"OpenFOAM case directory does not exist: {case}")
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(block_mesh_dict)

    command: list[str] | None = None
    selected_backend: str | None = None
    if execute:
        selected_backend = _select_backend(backend)
        command = _writecellcentres_command(selected_backend, case, docker_image, time_name)
        _run(command, case, timeout_seconds)

    centre_dir = case / time_name
    cx_path, cy_path, cz_path = (
        _resolve_field_file(centre_dir / name) for name in ("Cx", "Cy", "Cz")
    )
    cx = read_openfoam_vol_scalar_field(cx_path)
    cy = read_openfoam_vol_scalar_field(cy_path)
    cz = read_openfoam_vol_scalar_field(cz_path)
    cell_count = source_mesh.grid.cell_count
    for name, values in (("Cx", cx), ("Cy", cy), ("Cz", cz)):
        if values.shape != (cell_count,):
            raise ValueError(
                f"{name} has {values.size} values but blockMesh declares {cell_count} cells"
            )

    values_by_xfastest, tolerance_used = _invert_cell_centres(
        cx, cy, cz, source_mesh.grid, tolerance_cells=tolerance_cells
    )

    provenance = {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "kind": _ARTIFACT_KIND,
        "case_dir": str(case),
        "block_mesh": source_mesh.to_dict(),
        "cell_count": cell_count,
        "time_name": time_name,
        "tolerance_cells": tolerance_cells,
        "tolerance_length_m": tolerance_used,
        "execution": {
            "executed": execute,
            "backend": selected_backend,
            "command": command,
        },
        "source_files": {
            "Cx": _file_reference(case, cx_path),
            "Cy": _file_reference(case, cy_path),
            "Cz": _file_reference(case, cz_path),
        },
        "mapping": "global_label = values[x_fastest_index]",
        "array_sha256": _array_sha256(values_by_xfastest),
    }
    return _write_atomically(output_directory, values_by_xfastest, provenance, cell_count)


def _resolve_field_file(base: Path) -> Path:
    """Resolve a writeCellCentres field written plain or with writeCompression."""

    candidates = [path for path in (base, base.with_name(base.name + ".gz")) if path.is_file()]
    if len(candidates) > 1:
        raise ValueError(f"writeCellCentres output is ambiguous (plain and gzip): {base}")
    if not candidates:
        raise ValueError(
            f"writeCellCentres output is missing: {base}; run with execute=True "
            "or provide a time directory that already has Cx/Cy/Cz"
        )
    return candidates[0]


def _invert_cell_centres(
    cx: np.ndarray,
    cy: np.ndarray,
    cz: np.ndarray,
    grid: UniformCartesianCellGrid,
    *,
    tolerance_cells: float,
) -> tuple[np.ndarray, float]:
    origin = np.asarray(grid.origin, dtype=np.float64)
    spacing = np.asarray(grid.spacing, dtype=np.float64)
    nx, ny, nz = grid.cell_shape
    cell_count = grid.cell_count
    tolerance = float(tolerance_cells * np.min(spacing))
    centres = np.stack([cx, cy, cz], axis=1)
    fractional = (centres - origin) / spacing - 0.5
    indices = np.round(fractional).astype(np.int64)
    predicted = origin + spacing * (indices.astype(np.float64) + 0.5)
    residual = np.max(np.abs(centres - predicted), axis=1)

    values_by_xfastest = np.full(cell_count, -1, dtype=np.int64)
    for label in range(cell_count):
        if residual[label] > tolerance:
            raise ValueError(
                f"cell centre for global label {label} is not within tolerance "
                f"({residual[label]:.3g} > {tolerance:.3g}) of an exact grid cell centre"
            )
        i, j, k = (int(value) for value in indices[label])
        if not (0 <= i < nx and 0 <= j < ny and 0 <= k < nz):
            raise ValueError(
                f"cell centre for global label {label} maps to out-of-range index {(i, j, k)!r}"
            )
        x_fastest = i + nx * (j + ny * k)
        if values_by_xfastest[x_fastest] != -1:
            raise ValueError(
                "cell-centre inversion is not a permutation: x-fastest index "
                f"{x_fastest} matches both global labels {values_by_xfastest[x_fastest]} and {label}"
            )
        values_by_xfastest[x_fastest] = label
    return values_by_xfastest, tolerance


def _select_backend(backend: str) -> str:
    normalized = backend.lower()
    if normalized not in {"auto", "local", "wsl", "docker"}:
        raise ValueError(f"Unsupported OpenFOAM backend: {backend}")
    if normalized != "auto":
        return normalized
    if shutil.which("postProcess"):
        return "local"
    if platform.system().lower().startswith("win") and shutil.which("wsl") and _wsl_has_postprocess():
        return "wsl"
    if shutil.which("docker") and _docker_is_ready():
        return "docker"
    return "local"


def _wsl_has_postprocess() -> bool:
    return _command_succeeds(["wsl", "bash", "-lc", "command -v postProcess >/dev/null"])


def _docker_is_ready() -> bool:
    return _command_succeeds(["docker", "info", "--format", "{{.ServerVersion}}"])


def _command_succeeds(command: list[str]) -> bool:
    try:
        completed = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _writecellcentres_command(backend: str, case_dir: Path, docker_image: str, time_name: str) -> list[str]:
    command = f"postProcess -func writeCellCentres -time {time_name}"
    if backend == "local":
        return ["bash", "-lc", command]
    if backend == "wsl":
        script = 'case_dir="$(wslpath -a "$1")" && cd "$case_dir" && ' + command
        return ["wsl", "bash", "-lc", script, "bash", str(case_dir)]
    if backend == "docker":
        return [
            "docker", "run", "--rm", "--entrypoint", "bash",
            "--mount", f"type=bind,source={case_dir},target=/case",
            "-w", "/case", docker_image, "-lc", command,
        ]
    raise ValueError(f"Unsupported OpenFOAM backend: {backend}")


def _run(command: list[str], case_dir: Path, timeout_seconds: int | None) -> None:
    stdout_path = case_dir / "log.writeCellCentres.stdout"
    stderr_path = case_dir / "log.writeCellCentres.stderr"
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(
                command, cwd=case_dir, stdout=stdout, stderr=stderr, text=True, timeout=timeout_seconds, check=False
            )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"writeCellCentres timed out after {exc.timeout} seconds") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start writeCellCentres: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"writeCellCentres failed with exit code {completed.returncode}; see {stderr_path.name}"
        )


def _file_reference(root: Path, path: Path) -> dict[str, object]:
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha256_file(path)}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.int64))
    header = json.dumps({"dtype": array.dtype.str, "shape": list(array.shape)}, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


def _write_atomically(
    output_directory: str | Path,
    values_by_xfastest: np.ndarray,
    provenance: dict[str, object],
    cell_count: int,
) -> OpenFoamCellOrderDerivationArtifacts:
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError(f"output_directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.tmp-{uuid4().hex}"
    mapping_npy = temporary / _MAPPING_FILE_NAME
    provenance_json = temporary / "provenance.json"
    try:
        temporary.mkdir()
        np.save(mapping_npy, values_by_xfastest, allow_pickle=False)
        provenance_json.write_text(
            json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        # Round-trip through the same reader every downstream consumer uses,
        # so a written mapping that fails the permutation contract is refused
        # before it ever becomes visible.
        load_openfoam_cell_order_mapping(mapping_npy, cell_count=cell_count)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return OpenFoamCellOrderDerivationArtifacts(
        directory=output,
        mapping_npy=output / mapping_npy.name,
        provenance_json=output / provenance_json.name,
    )


__all__ = [
    "OpenFoamCellOrderDerivationArtifacts",
    "derive_and_write_openfoam_cell_order_mapping",
]
