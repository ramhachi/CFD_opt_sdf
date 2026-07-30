"""Stage one fresh G3 OpenFOAM case with a provenance-bound ``alpha`` field.

This is deliberately only a case-preparation boundary.  It consumes a
cellwise CFD ``alpha`` vector that has already been calculated by the
localized design transfer, writes it through the strict alpha codec, and
ensures the compiled case's ``setFields`` step cannot overwrite it.  It does
not run OpenFOAM, reconstruct a state, or establish native-v2 qualification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import numpy as np

from .openfoam_alpha_codec import (
    OpenFOAMAlphaField,
    openfoam_alpha_values_sha256,
    read_openfoam_alpha_field,
    write_and_verify_openfoam_alpha_field,
)
from .localized_alpha_reference_binding import (
    LocalizedAlphaSource,
    VerifiedLocalizedAlphaReferenceBinding,
    validate_localized_alpha_reference_binding,
)
from .openfoam_blockmesh_grid import OpenFoamBlockMeshGrid, read_openfoam_blockmesh_uniform_cartesian_grid
from .openfoam_grid_transfer import CANONICAL_CELL_ORDER


LOCALIZED_OPENFOAM_ALPHA_CASE_SCHEMA_VERSION = 1
LOCALIZED_OPENFOAM_ALPHA_CASE_KIND = "localized_openfoam_alpha_case"
_MANIFEST_NAME = "localized_openfoam_alpha_case.json"
_SET_FIELDS_MARKER = "runApplication setFields"
_ALPHA_RESTORE_COMMAND = "cp 0.orig/alpha 0/alpha"
_PROCESSOR_DIRECTORY = re.compile(r"^processor[0-9]+$")
_NUMERIC_TIME_DIRECTORY = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LocalizedOpenFOAMAlphaCaseArtifacts:
    """Verified result of staging, never a solver-result claim."""

    case_dir: Path
    alpha_path: Path
    manifest_json: Path
    alpha_cell_count: int
    alpha_values_sha256: str
    allrun_sha256: str
    removed_runtime_artifacts: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("case_dir", "alpha_path", "manifest_json"):
            data[key] = str(data[key])
        data["removed_runtime_artifacts"] = list(self.removed_runtime_artifacts)
        return data


def stage_localized_openfoam_alpha_case(
    *,
    compiled_case_dir: str | Path,
    output_case_dir: str | Path,
    alpha_source: LocalizedAlphaSource,
    verified_alpha_binding: VerifiedLocalizedAlphaReferenceBinding,
) -> LocalizedOpenFOAMAlphaCaseArtifacts:
    """Copy a compiled case into a new fresh case and bind ``source_alpha``.

    ``output_case_dir`` must not exist.  A raw array is deliberately not
    accepted: the source and verified reference binding must agree with the
    strictly parsed compiled-case mesh.  The compiled case is read-only; all
    mutations occur in an adjacent temporary directory and are atomically
    published only after grid, codec readback, and Allrun checks succeed.
    """

    template = _verify_compiled_case(compiled_case_dir)
    template_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(template / "system" / "blockMeshDict")
    binding = _require_alpha_source_contract(
        alpha_source=alpha_source,
        verified_alpha_binding=verified_alpha_binding,
        block_mesh=template_mesh,
    )
    output = Path(output_case_dir).resolve()
    if output.exists():
        raise FileExistsError(f"localized OpenFOAM output case already exists: {output}")
    if output == template or _is_relative_to(template, output) or _is_relative_to(output, template):
        raise ValueError("output_case_dir must be disjoint from the compiled case")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging_", dir=output.parent))
    staged_case = staging / "case"
    try:
        shutil.copytree(template, staged_case)
        removed = _reset_copied_case_for_fresh_execution(staged_case, staging_root=staging)
        staged_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(staged_case / "system" / "blockMeshDict")
        _validate_staged_mesh_identity(template_mesh, staged_mesh)
        observed = write_and_verify_openfoam_alpha_field(staged_case / "0.orig" / "alpha", alpha_source.alpha)
        _patch_allrun_to_restore_alpha(staged_case / "Allrun")
        _validate_staged_case_contract(staged_case, observed)
        # Parse the final staged dictionary too, so no mutation made while
        # preparing the field/script can silently substitute mesh semantics.
        staged_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(staged_case / "system" / "blockMeshDict")
        _validate_staged_mesh_identity(template_mesh, staged_mesh)
        manifest_path = staged_case / _MANIFEST_NAME
        _write_manifest(
            manifest_path,
            template=template,
            staged_case=staged_case,
            alpha=observed,
            removed=removed,
            template_mesh=template_mesh,
            staged_mesh=staged_mesh,
            alpha_source=alpha_source,
            binding=binding,
        )
        staged_case.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return LocalizedOpenFOAMAlphaCaseArtifacts(
        case_dir=output,
        alpha_path=output / "0.orig" / "alpha",
        manifest_json=output / _MANIFEST_NAME,
        alpha_cell_count=observed.cell_count,
        alpha_values_sha256=observed.value_sha256,
        allrun_sha256=_sha256_file(output / "Allrun"),
        removed_runtime_artifacts=tuple(removed),
    )


def validate_localized_openfoam_alpha_case(case_dir: str | Path) -> LocalizedOpenFOAMAlphaCaseArtifacts:
    """Recheck the staged alpha and Allrun contract without executing it."""

    case = Path(case_dir).resolve()
    manifest_path = case / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"localized OpenFOAM alpha-case manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"localized OpenFOAM alpha-case manifest is invalid JSON: {manifest_path}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != LOCALIZED_OPENFOAM_ALPHA_CASE_SCHEMA_VERSION or manifest.get("kind") != LOCALIZED_OPENFOAM_ALPHA_CASE_KIND:
        raise ValueError(f"localized OpenFOAM alpha-case manifest has an unsupported contract: {manifest_path}")
    if manifest.get("status") != "prepared" or manifest.get("execution_qualification") != "not_run":
        raise ValueError("localized OpenFOAM alpha-case manifest must only claim prepared/not_run")
    alpha = read_openfoam_alpha_field(case / "0.orig" / "alpha")
    _validate_staged_case_contract(case, alpha)
    source = manifest.get("alpha_source")
    if not isinstance(source, dict) or source.get("cell_count") != alpha.cell_count or source.get("values_sha256") != alpha.value_sha256:
        raise ValueError("localized OpenFOAM alpha-case alpha readback does not match its manifest")
    current_state_sha256 = source.get("current_state_manifest_sha256")
    if not isinstance(current_state_sha256, str) or _SHA256_RE.fullmatch(current_state_sha256) is None:
        raise ValueError("localized OpenFOAM alpha-case current state manifest provenance is invalid")
    mesh = read_openfoam_blockmesh_uniform_cartesian_grid(case / "system" / "blockMeshDict")
    block_mesh = manifest.get("block_mesh")
    binding = manifest.get("alpha_binding")
    if not isinstance(block_mesh, dict) or not isinstance(binding, dict):
        raise ValueError("localized OpenFOAM alpha-case mesh/binding manifest is invalid")
    if (
        block_mesh.get("staged_block_mesh_sha256") != mesh.block_mesh_sha256
        or block_mesh.get("grid_sha256") != mesh.grid_sha256
        or source.get("cfd_grid_sha256") != mesh.grid_sha256
        or source.get("cfd_cell_count") != mesh.grid.cell_count
        or source.get("cell_order") != CANONICAL_CELL_ORDER
        or binding.get("cfd_grid_sha256") != mesh.grid_sha256
        or binding.get("cfd_cell_count") != mesh.grid.cell_count
        or binding.get("binding_sha256") != source.get("binding_sha256")
    ):
        raise ValueError("localized OpenFOAM alpha-case mesh, source, and binding contract mismatch")
    allrun = manifest.get("allrun")
    allrun_sha256 = _sha256_file(case / "Allrun")
    if not isinstance(allrun, dict) or allrun.get("sha256") != allrun_sha256:
        raise ValueError("localized OpenFOAM alpha-case Allrun hash does not match its manifest")
    removed = manifest.get("fresh_execution_reset", {}).get("removed_runtime_artifacts", [])
    if not isinstance(removed, list) or not all(isinstance(item, str) for item in removed):
        raise ValueError("localized OpenFOAM alpha-case reset manifest is invalid")
    return LocalizedOpenFOAMAlphaCaseArtifacts(
        case_dir=case,
        alpha_path=alpha.path,
        manifest_json=manifest_path,
        alpha_cell_count=alpha.cell_count,
        alpha_values_sha256=alpha.value_sha256,
        allrun_sha256=allrun_sha256,
        removed_runtime_artifacts=tuple(removed),
    )


def _verify_compiled_case(path: str | Path) -> Path:
    case = Path(path).resolve()
    if not case.is_dir():
        raise FileNotFoundError(f"compiled OpenFOAM case is missing: {case}")
    metadata_path = case / "openfoam_case_compilation.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"compiled OpenFOAM case metadata is missing: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"compiled OpenFOAM case metadata is invalid JSON: {metadata_path}") from error
    if not isinstance(metadata, dict) or metadata.get("status") != "compiled":
        raise ValueError(f"case metadata does not identify a compiled OpenFOAM case: {metadata_path}")
    for relative in ("0.orig/alpha", "constant", "system", "Allrun", "Allclean"):
        target = case / relative
        if not target.exists():
            raise FileNotFoundError(f"compiled OpenFOAM case lacks required input: {target}")
    return case


def _require_alpha_source_contract(
    *,
    alpha_source: LocalizedAlphaSource,
    verified_alpha_binding: VerifiedLocalizedAlphaReferenceBinding,
    block_mesh: OpenFoamBlockMeshGrid,
) -> VerifiedLocalizedAlphaReferenceBinding:
    """Require all three independently-derived descriptions of the CFD grid."""

    if not isinstance(alpha_source, LocalizedAlphaSource):
        raise ValueError("alpha_source must be a calculated LocalizedAlphaSource, not a bare array")
    if not isinstance(verified_alpha_binding, VerifiedLocalizedAlphaReferenceBinding):
        raise ValueError("verified_alpha_binding must be VerifiedLocalizedAlphaReferenceBinding")
    # Revalidate rather than trusting an object supplied by a different
    # process.  This checks its state/alpha artifacts as well as metadata.
    binding = validate_localized_alpha_reference_binding(verified_alpha_binding.binding)
    if alpha_source.binding_sha256 != binding.binding.sha256:
        raise ValueError("localized alpha source binding hash does not match verified alpha binding")
    if alpha_source.cell_order != CANONICAL_CELL_ORDER:
        raise ValueError("localized alpha source cell_order must be x-fastest")
    if not isinstance(alpha_source.alpha, np.ndarray) or alpha_source.alpha.dtype != np.dtype(np.float64) or alpha_source.alpha.ndim != 1:
        raise ValueError("localized alpha source vector must be a one-dimensional native float64 array")
    if not np.all(np.isfinite(alpha_source.alpha)):
        raise ValueError("localized alpha source vector contains a non-finite value")
    if np.any(alpha_source.alpha < 0.0) or np.any(alpha_source.alpha > 1.0):
        raise ValueError("localized alpha source vector must remain within [0, 1] without clipping")
    value_sha = openfoam_alpha_values_sha256(alpha_source.alpha)
    if alpha_source.alpha_sha256 != value_sha:
        raise ValueError("localized alpha source vector hash does not match its declared alpha_sha256")
    if alpha_source.cfd_cell_count != alpha_source.alpha.size:
        raise ValueError("localized alpha source cfd_cell_count does not match vector count")
    if not isinstance(alpha_source.current_state_manifest_sha256, str) or _SHA256_RE.fullmatch(alpha_source.current_state_manifest_sha256) is None:
        raise ValueError("localized alpha source current state manifest hash is invalid")
    if (
        alpha_source.cfd_grid_sha256 != binding.binding.cfd_grid_sha256
        or alpha_source.cfd_cell_count != binding.binding.cfd_grid.cell_count
        or binding.binding.cfd_grid_sha256 != block_mesh.grid_sha256
        or alpha_source.cfd_grid_sha256 != block_mesh.grid_sha256
        or alpha_source.cfd_cell_count != block_mesh.grid.cell_count
    ):
        raise ValueError("localized alpha source, verified alpha binding, and blockMesh CFD grid must match")
    return binding


def _validate_staged_mesh_identity(template: OpenFoamBlockMeshGrid, staged: OpenFoamBlockMeshGrid) -> None:
    if template.block_mesh_sha256 != staged.block_mesh_sha256 or template.grid_sha256 != staged.grid_sha256:
        raise ValueError("staged blockMeshDict must remain byte-identical and grid-identical to compiled template")


def _reset_copied_case_for_fresh_execution(case: Path, *, staging_root: Path) -> list[str]:
    """Remove known solver output only from the newly copied case."""

    if not _is_relative_to(case.resolve(), staging_root.resolve()):
        raise ValueError("fresh-case reset may only target an unpublished staging copy")
    removed: list[str] = []
    for child in sorted(case.iterdir(), key=lambda item: item.name):
        name = child.name
        is_generated_directory = (
            _PROCESSOR_DIRECTORY.fullmatch(name) is not None
            or _NUMERIC_TIME_DIRECTORY.fullmatch(name) is not None
            or name in {"optimisation", "postProcessing", "VTK"}
        )
        is_generated_file = name.startswith("log.") or name in {"openfoam_run_summary.json", "case.foam"}
        if is_generated_directory:
            if not child.is_dir():
                raise ValueError(f"expected runtime artifact directory is not a directory: {child}")
            shutil.rmtree(child)
            removed.append(name + "/")
        elif is_generated_file:
            if not child.is_file():
                raise ValueError(f"expected runtime artifact is not a file: {child}")
            child.unlink()
            removed.append(name)
    return removed


def _patch_allrun_to_restore_alpha(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"compiled case Allrun is missing: {path}")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("#!"):
        raise ValueError(f"Allrun must start with a POSIX shell shebang: {path}")
    if text.count(_SET_FIELDS_MARKER) != 1:
        raise ValueError(f"Allrun must contain exactly one {_SET_FIELDS_MARKER!r}: {path}")
    patched = text.replace(_SET_FIELDS_MARKER, _SET_FIELDS_MARKER + "\n" + _ALPHA_RESTORE_COMMAND)
    path.write_bytes(patched.encode("utf-8"))
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _validate_allrun_alpha_restore(path)


def _validate_staged_case_contract(case: Path, alpha: OpenFOAMAlphaField) -> None:
    if alpha.path.resolve() != (case / "0.orig" / "alpha").resolve():
        raise ValueError("staged alpha readback is not exactly 0.orig/alpha")
    if alpha.cell_count <= 0 or len(alpha.value_sha256) != 64:
        raise ValueError("staged alpha codec result is invalid")
    _validate_allrun_alpha_restore(case / "Allrun")


def _validate_allrun_alpha_restore(path: Path) -> None:
    raw = path.read_bytes()
    if b"\r" in raw:
        raise ValueError(f"Allrun must use POSIX LF line endings: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Allrun must be UTF-8 text: {path}") from error
    expected = _SET_FIELDS_MARKER + "\n" + _ALPHA_RESTORE_COMMAND
    if not text.startswith("#!") or text.count(_SET_FIELDS_MARKER) != 1 or text.count(expected) != 1:
        raise ValueError(f"Allrun does not preserve the exact post-setFields alpha restore contract: {path}")
    # Windows does not expose POSIX execute bits reliably even after chmod;
    # Docker/WSL runners apply chmod before invoking Allrun.  On POSIX we can
    # and do prove that the staged script remains directly executable.
    if os.name != "nt" and not (path.stat().st_mode & stat.S_IXUSR):
        raise ValueError(f"Allrun must retain an executable owner bit: {path}")


def _write_manifest(
    path: Path,
    *,
    template: Path,
    staged_case: Path,
    alpha: OpenFOAMAlphaField,
    removed: list[str],
    template_mesh: OpenFoamBlockMeshGrid,
    staged_mesh: OpenFoamBlockMeshGrid,
    alpha_source: LocalizedAlphaSource,
    binding: VerifiedLocalizedAlphaReferenceBinding,
) -> None:
    data = {
        "schema_version": LOCALIZED_OPENFOAM_ALPHA_CASE_SCHEMA_VERSION,
        "kind": LOCALIZED_OPENFOAM_ALPHA_CASE_KIND,
        "status": "prepared",
        "execution_qualification": "not_run",
        "template": {
            "compiled_case_dir": str(template),
            "compilation_metadata_sha256": _sha256_file(template / "openfoam_case_compilation.json"),
            "alpha_template_sha256": _sha256_file(template / "0.orig" / "alpha"),
            "allrun_template_sha256": _sha256_file(template / "Allrun"),
        },
        "block_mesh": {
            "template_block_mesh_sha256": template_mesh.block_mesh_sha256,
            "staged_block_mesh_sha256": staged_mesh.block_mesh_sha256,
            "grid_sha256": template_mesh.grid_sha256,
            "origin": list(template_mesh.grid.origin),
            "spacing": list(template_mesh.grid.spacing),
            "cell_shape": list(template_mesh.grid.cell_shape),
            "cell_order": template_mesh.grid.cell_order,
        },
        "alpha_source": {
            "path": "0.orig/alpha",
            "cell_count": alpha.cell_count,
            "values_sha256": alpha.value_sha256,
            "cfd_cell_count": alpha_source.cfd_cell_count,
            "cfd_grid_sha256": alpha_source.cfd_grid_sha256,
            "cell_order": alpha_source.cell_order,
            "binding_sha256": alpha_source.binding_sha256,
            "current_state_manifest_sha256": alpha_source.current_state_manifest_sha256,
            "codec": "strict_openfoam_alpha_codec",
            "readback_verified": True,
        },
        "alpha_binding": {
            "binding_sha256": binding.binding.sha256,
            "cfd_grid_sha256": binding.binding.cfd_grid_sha256,
            "cfd_cell_count": binding.binding.cfd_grid.cell_count,
        },
        "allrun": {
            "path": "Allrun",
            "sha256": _sha256_file(staged_case / "Allrun"),
            "set_fields_marker": _SET_FIELDS_MARKER,
            "immediate_next_command": _ALPHA_RESTORE_COMMAND,
            "line_endings": "LF",
            "executable_owner_bit": bool(staged_case.joinpath("Allrun").stat().st_mode & stat.S_IXUSR),
        },
        "fresh_execution_reset": {"removed_runtime_artifacts": removed},
    }
    path.write_bytes((json.dumps(data, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


__all__ = [
    "LOCALIZED_OPENFOAM_ALPHA_CASE_KIND",
    "LOCALIZED_OPENFOAM_ALPHA_CASE_SCHEMA_VERSION",
    "LocalizedOpenFOAMAlphaCaseArtifacts",
    "stage_localized_openfoam_alpha_case",
    "validate_localized_openfoam_alpha_case",
]
