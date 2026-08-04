"""Atomic, reproducible initial state bundles for the localized G3 grid.

The bundle deliberately starts from the declared ``initial_design`` STL.  It
never tries to infer a fine state from a coarse OpenFOAM alpha field.  The
geometry snapshot is copied (rather than linked), so the resulting directory
is a self-contained, immutable input to the later alpha-reference binding.
"""

from __future__ import annotations

import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from dataclasses import dataclass
from typing import Callable, Any

import numpy as np

from .local_design_geometry_snapshot import (
    LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME,
    LocalDesignGeometryMaskSnapshot,
    load_and_verify_local_design_geometry_mask_snapshot,
)
from .local_initial_design_rho import (
    LOCAL_INITIAL_DESIGN_RHO_FILENAME,
    build_local_initial_design_rho_raw,
)
from .localized_design_state_manifest import (
    LocalizedDesignGrid,
    create_localized_design_state_manifest,
    load_and_verify_localized_design_state_manifest,
    localized_design_state_manifest_sha256,
    require_localized_design_state_manifest_v2,
    write_localized_design_state_manifest,
)
from .localized_filter_projection import (
    LocalizedConeFilterConfig,
    LocalizedHeavisideProjectionConfig,
    apply_localized_heaviside_projection,
    read_canonical_filter_config,
    read_canonical_projection_config,
    write_canonical_filter_config,
    write_canonical_projection_config,
    write_localized_cone_filtered_npy,
)
from .problem_spec import ProblemSpec, canonical_local_design_grid, load_problem_spec, problem_spec_sha256


LOCALIZED_REFERENCE_STATE_SCHEMA_VERSION = 1
LOCALIZED_REFERENCE_STATE_KIND = "localized_reference_state_bundle"
LOCALIZED_REFERENCE_STATE_FILENAME = "localized_reference_state.json"
LOCALIZED_REFERENCE_STATE_FAILURE_SCHEMA_VERSION = 1
LOCALIZED_REFERENCE_STATE_FAILURE_KIND = "localized_reference_state_build_failure"
_MIN_RESOURCE_BYTES = 8 * 1024**3
_CHUNK = 1_048_576


@dataclass(frozen=True)
class LocalizedReferenceStateBundle:
    path: Path
    geometry_snapshot: LocalDesignGeometryMaskSnapshot
    state_manifest_sha256: str
    raw_manifest_sha256: str
    initial_design_stl_sha256: str


def localized_reference_state_failure_report_path(output_dir: str | Path) -> Path:
    """Return the diagnostic sidecar path for one requested bundle output.

    This sidecar is deliberately a sibling of the requested output directory,
    never a member of a published bundle.  It records only a failed build; it
    is not a topology evaluation or a partially valid state artifact.
    """

    destination = Path(output_dir)
    return destination.parent / f".{destination.name}.build-failure.json"


def build_localized_reference_state_bundle(
    problem: ProblemSpec | str | Path,
    *,
    geometry_snapshot_path: str | Path,
    output_dir: str | Path,
    filter_config: LocalizedConeFilterConfig = LocalizedConeFilterConfig(),
    projection_config: LocalizedHeavisideProjectionConfig = LocalizedHeavisideProjectionConfig(),
    z_slab_size: int = 1,
    disk_free_bytes: Callable[[Path], int] | None = None,
    available_memory_bytes: Callable[[], int] | None = None,
    expected_component_count: int = 10,
) -> LocalizedReferenceStateBundle:
    """Build and atomically publish a local raw/filter/projected state bundle.

    The resource guard is intentionally conservative.  A real 87.5M-cell
    bundle has several large NPY artifacts and must never begin when less than
    8 GiB are free both on its output volume and in available system memory.
    Tests may inject probes; production uses OS probes.
    """
    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    if not isinstance(spec, ProblemSpec):
        raise ValueError("problem must be ProblemSpec or a project YAML path")
    if not isinstance(filter_config, LocalizedConeFilterConfig) or not isinstance(projection_config, LocalizedHeavisideProjectionConfig):
        raise ValueError("filter_config and projection_config must be canonical localized configs")
    if not isinstance(z_slab_size, int) or isinstance(z_slab_size, bool) or z_slab_size <= 0:
        raise ValueError("z_slab_size must be a positive integer")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing localized reference state: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_resources(destination.parent, disk_free_bytes, available_memory_bytes)

    expected_problem_hash = problem_spec_sha256(spec)
    geometry = load_and_verify_local_design_geometry_mask_snapshot(
        geometry_snapshot_path, expected_problem_spec_sha256=expected_problem_hash
    ).snapshot
    grid = _canonical_grid(spec)
    if geometry.grid != grid or geometry.grid_sha256 != grid.sha256:
        raise ValueError("geometry snapshot grid does not match project local design grid")
    initial_stl, initial_sha = _declared_initial_design(spec, geometry)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    stage = "copy_geometry_snapshot"
    active: np.memmap | None = None
    try:
        geometry_dir = staging / "geometry_snapshot"
        shutil.copytree(geometry.path.parent, geometry_dir, copy_function=shutil.copy2)
        stage = "verify_copied_geometry_snapshot"
        copied_geometry = load_and_verify_local_design_geometry_mask_snapshot(
            geometry_dir / LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME,
            expected_problem_spec_sha256=expected_problem_hash,
        ).snapshot
        active_path = geometry_dir / copied_geometry.masks["active_design_mask"].relative_path
        active = np.load(active_path, mmap_mode="r", allow_pickle=False)
        if not isinstance(active, np.memmap):
            raise ValueError("copied active_design_mask must be a memory-mappable NPY array")
        stage = "build_raw_initial_design_rho"
        raw = build_local_initial_design_rho_raw(
            grid=grid,
            active_design_mask=active,
            initial_design_stl=initial_stl,
            output_dir=staging / "raw",
            expected_component_count=expected_component_count,
            z_chunk_size=z_slab_size,
        )
        if raw.manifest.stl_sha256 != initial_sha:
            raise ValueError("raw initial-design provenance does not match declared STL")
        states = staging / "states"
        states.mkdir()
        stage = "filter_raw_initial_design_rho"
        raw_values = np.load(raw.rho_raw_path, mmap_mode="r", allow_pickle=False)
        try:
            filtered_path = write_localized_cone_filtered_npy(
                raw_values, active, grid,
                output_path=states / "rho_filtered.npy", config=filter_config, z_slab_size=z_slab_size,
            )
        finally:
            _close_memmap(raw_values)
        projected_path = states / "rho_projected.npy"
        projected = np.lib.format.open_memmap(projected_path, mode="w+", dtype=np.float64, shape=(grid.cell_count,))
        try:
            stage = "project_filtered_initial_design_rho"
            filtered_values = np.load(filtered_path, mmap_mode="r", allow_pickle=False)
            try:
                apply_localized_heaviside_projection(
                    filtered_values, active, config=projection_config, out=projected
                )
            finally:
                _close_memmap(filtered_values)
            projected.flush()
        finally:
            _close_memmap(projected)
        configs = staging / "configs"
        configs.mkdir()
        filter_path = configs / "filter_config.json"
        projection_path = configs / "projection_config.json"
        filter_hash = write_canonical_filter_config(filter_path, filter_config)
        projection_hash = write_canonical_projection_config(projection_path, projection_config)
        manifest_path = staging / "localized_design_state_manifest.json"
        state_manifest = create_localized_design_state_manifest(
            path=manifest_path, problem_spec_sha256=expected_problem_hash, grid=grid,
            masks={identifier: geometry_dir / artifact.relative_path for identifier, artifact in copied_geometry.masks.items()},
            states={"rho": raw.rho_raw_path, "rho_filtered": filtered_path, "rho_projected": projected_path},
            filter_config_sha256=filter_hash, projection_config_sha256=projection_hash,
            filter_config_path=filter_path, projection_config_path=projection_path,
        )
        write_localized_design_state_manifest(state_manifest)
        # ``active`` is a Windows NPY mapping.  Close it before the final
        # directory rename; a live mapping keeps the parent directory busy.
        _close_memmap(active)
        active = None
        state_hash = localized_design_state_manifest_sha256(state_manifest)
        raw_hash = _sha256_file(raw.manifest_path)
        _write_json(staging / LOCALIZED_REFERENCE_STATE_FILENAME, {
            "schema_version": LOCALIZED_REFERENCE_STATE_SCHEMA_VERSION,
            "kind": LOCALIZED_REFERENCE_STATE_KIND,
            "problem_spec_sha256": expected_problem_hash,
            "grid_sha256": grid.sha256,
            "geometry_snapshot_relative_path": f"geometry_snapshot/{LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME}",
            "geometry_snapshot_sha256": copied_geometry.sha256,
            "initial_design_stl_sha256": initial_sha,
            "raw_manifest_relative_path": f"raw/{LOCAL_INITIAL_DESIGN_RHO_FILENAME}",
            "raw_manifest_sha256": raw_hash,
            "state_manifest_relative_path": "localized_design_state_manifest.json",
            "state_manifest_sha256": state_hash,
            "filter_config_sha256": filter_hash,
            "projection_config_sha256": projection_hash,
        })
        stage = "verify_staged_bundle"
        verify_localized_reference_state_bundle(staging, problem=spec)
        gc.collect()
        stage = "publish_bundle"
        os.replace(staging, destination)
    except BaseException as exc:
        _close_memmap(active)
        active = None
        gc.collect()
        cleanup_error = _remove_staging_directory(staging)
        report = _write_failure_report(
            destination=destination,
            staging=staging,
            failed_stage=stage,
            error=exc,
            cleanup_error=cleanup_error,
        )
        if report is not None and hasattr(exc, "add_note"):
            exc.add_note(f"localized reference-state diagnostic report: {report}")
        raise
    return verify_localized_reference_state_bundle(destination, problem=spec)


def verify_localized_reference_state_bundle(
    path: str | Path, *, problem: ProblemSpec | str | Path
) -> LocalizedReferenceStateBundle:
    """Independently stream-verify all provenance, arrays and transformations."""
    root = Path(path)
    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    if not root.is_dir() or not isinstance(spec, ProblemSpec):
        raise ValueError("bundle directory and ProblemSpec are required")
    ledger = _read_ledger(root / LOCALIZED_REFERENCE_STATE_FILENAME)
    problem_hash = problem_spec_sha256(spec)
    if ledger["problem_spec_sha256"] != problem_hash:
        raise ValueError("reference bundle problem_spec_sha256 does not match project")
    grid = _canonical_grid(spec)
    if ledger["grid_sha256"] != grid.sha256:
        raise ValueError("reference bundle grid_sha256 does not match project")
    geometry_path = _safe_under(root, ledger["geometry_snapshot_relative_path"])
    geometry = load_and_verify_local_design_geometry_mask_snapshot(geometry_path, expected_problem_spec_sha256=problem_hash).snapshot
    if geometry.sha256 != ledger["geometry_snapshot_sha256"] or geometry.grid != grid:
        raise ValueError("reference bundle geometry snapshot binding is invalid")
    stl, stl_hash = _declared_initial_design(spec, geometry)
    del stl
    if stl_hash != ledger["initial_design_stl_sha256"]:
        raise ValueError("reference bundle initial_design STL hash mismatch")
    raw_manifest_path = _safe_under(root, ledger["raw_manifest_relative_path"])
    if _sha256_file(raw_manifest_path) != ledger["raw_manifest_sha256"]:
        raise ValueError("reference bundle raw manifest hash mismatch")
    raw_data = _read_json(raw_manifest_path)
    _verify_raw_manifest(raw_data, root, grid, geometry, stl_hash)
    state_path = _safe_under(root, ledger["state_manifest_relative_path"])
    verified_state = require_localized_design_state_manifest_v2(
        load_and_verify_localized_design_state_manifest(state_path, expected_problem_spec_sha256=problem_hash)
    )
    state = verified_state.manifest
    if localized_design_state_manifest_sha256(state) != ledger["state_manifest_sha256"] or state.grid != grid:
        raise ValueError("reference bundle state manifest binding is invalid")
    if state.filter_config_sha256 != ledger["filter_config_sha256"] or state.projection_config_sha256 != ledger["projection_config_sha256"]:
        raise ValueError("reference bundle configuration hash binding is invalid")
    _verify_state_uses_copied_geometry(state, root, geometry)
    _verify_transformations(root, state, grid, z_slab_size=1)
    return LocalizedReferenceStateBundle(root, geometry, ledger["state_manifest_sha256"], ledger["raw_manifest_sha256"], stl_hash)


def _canonical_grid(spec: ProblemSpec) -> LocalizedDesignGrid:
    source = canonical_local_design_grid(spec)
    return LocalizedDesignGrid(tuple(source.origin), tuple(source.spacing), tuple(source.cell_shape), source.cell_order)


def _declared_initial_design(spec: ProblemSpec, geometry: LocalDesignGeometryMaskSnapshot) -> tuple[Path, str]:
    regions = [item for item in spec.geometry_regions if item.role == "initial_design"]
    if len(regions) != 1:
        raise ValueError("project must declare exactly one initial_design STL")
    region = regions[0]
    snapshot_region = geometry.classifier_regions.get(region.id)
    if snapshot_region is None or snapshot_region.get("role") != "initial_design":
        raise ValueError("geometry snapshot does not bind the declared initial_design region")
    source_ref = snapshot_region.get("source_ref")
    if not isinstance(source_ref, dict) or source_ref.get("kind") != "problem_spec_relative_stl":
        raise ValueError("geometry snapshot initial_design source reference is invalid")
    if source_ref.get("declared_path") != _declared_path(spec, region.file):
        raise ValueError("geometry snapshot initial_design source path does not match project")
    source_path = spec.resolve(region.file)
    actual = _sha256_file(source_path)
    if snapshot_region.get("sha256") != actual:
        raise ValueError("geometry snapshot initial_design source hash does not match project")
    return source_path, actual


def _declared_path(spec: ProblemSpec, path: Path) -> str:
    # ``GeometryRegionSpec.file`` is normalized by the YAML reader.  Preserve
    # project-relative (including ``..``) spelling only for source comparison.
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(spec.path.parent).as_posix()
    except ValueError:
        return Path(os.path.relpath(path, spec.path.parent)).as_posix()


def _verify_raw_manifest(raw: dict[str, Any], root: Path, grid: LocalizedDesignGrid, geometry: LocalDesignGeometryMaskSnapshot, stl_hash: str) -> None:
    required = {"schema_version", "kind", "stl_sha256", "role", "component_count", "grid_sha256", "active_design_mask_sha256", "method", "subcell_offsets", "surface_rejection_tolerance_m", "rho_raw_relative_path", "rho_raw_sha256", "rho_raw_dtype", "rho_raw_shape", "occupancy_volume_m3"}
    schema_version = raw.get("schema_version")
    expected = required if schema_version == 1 else required | {"surface_resolution"}
    if set(raw) != expected or schema_version not in {1, 2} or raw["kind"] != "local_initial_design_rho_raw" or raw["role"] != "initial_design":
        raise ValueError("raw initial-design manifest schema is invalid")
    if raw["stl_sha256"] != stl_hash or raw["grid_sha256"] != grid.sha256 or raw["method"] != "direct_stl_union_occupancy_2x2x2":
        raise ValueError("raw initial-design manifest provenance is invalid")
    if schema_version == 2:
        _verify_surface_resolution(raw["surface_resolution"])
    rho_path = _safe_under(root / "raw", raw["rho_raw_relative_path"])
    if _sha256_file(rho_path) != raw["rho_raw_sha256"]:
        raise ValueError("raw rho hash mismatch")
    active = np.load(_safe_under(root / "geometry_snapshot", geometry.masks["active_design_mask"].relative_path), mmap_mode="r", allow_pickle=False)
    rho = np.load(rho_path, mmap_mode="r", allow_pickle=False)
    try:
        if _logical_bool_hash(active) != raw["active_design_mask_sha256"]:
            raise ValueError("raw active mask provenance hash mismatch")
        if rho.dtype != np.dtype(np.float64) or rho.shape != (grid.cell_count,):
            raise ValueError("raw rho layout is invalid")
        for start in range(0, grid.cell_count, _CHUNK):
            values, active_chunk = rho[start:start + _CHUNK], active[start:start + _CHUNK]
            if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1) or np.any(values[~active_chunk] != 0):
                raise ValueError("raw rho values violate active-mask contract")
            denominator = 16.0 if schema_version == 2 else 8.0
            if np.any(values[active_chunk] * denominator != np.rint(values[active_chunk] * denominator)):
                raise ValueError("raw rho values must be exact declared subcell fractions")
    finally:
        del rho
        del active


def _verify_surface_resolution(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("raw surface_resolution is invalid")
    required = {
        "kind", "surface_tolerance_m", "normal_offset_m", "tie_point_count",
        "contribution_counts", "sampler_implementation", "sampler_version",
    }
    if set(value) != required or value["kind"] != "symmetric_normal_offset_union":
        raise ValueError("raw surface_resolution schema is invalid")
    if value["surface_tolerance_m"] != 1.0e-9 or value["normal_offset_m"] != 1.0e-6:
        raise ValueError("raw surface_resolution parameters are invalid")
    if value["sampler_implementation"] != "cfd_sdf.local_initial_design_rho" or value["sampler_version"] != 2:
        raise ValueError("raw surface_resolution sampler is invalid")
    count = value["tie_point_count"]
    counts = value["contribution_counts"]
    if (
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        or not isinstance(counts, dict) or set(counts) != {"zero", "half", "one"}
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in counts.values())
        or count != sum(counts.values())
    ):
        raise ValueError("raw surface_resolution counts are invalid")


def _verify_state_uses_copied_geometry(state: Any, root: Path, geometry: LocalDesignGeometryMaskSnapshot) -> None:
    for identifier, artifact in state.masks.items():
        expected = _safe_under(root / "geometry_snapshot", geometry.masks[identifier].relative_path)
        actual = _safe_under(root, artifact.relative_path)
        if actual != expected:
            raise ValueError("state manifest must use copied geometry masks")
        if artifact.byte_sha256 != geometry.masks[identifier].byte_sha256:
            raise ValueError("state manifest mask hash does not match copied geometry")


def _verify_transformations(root: Path, state: Any, grid: LocalizedDesignGrid, *, z_slab_size: int) -> None:
    active = np.load(_safe_under(root, state.masks["active_design_mask"].relative_path), mmap_mode="r", allow_pickle=False)
    raw = np.load(_safe_under(root, state.states["rho"].relative_path), mmap_mode="r", allow_pickle=False)
    filtered = np.load(_safe_under(root, state.states["rho_filtered"].relative_path), mmap_mode="r", allow_pickle=False)
    projected = np.load(_safe_under(root, state.states["rho_projected"].relative_path), mmap_mode="r", allow_pickle=False)
    try:
        filter_config = read_canonical_filter_config(_safe_under(root, state.filter_config.relative_path))
        projection_config = read_canonical_projection_config(_safe_under(root, state.projection_config.relative_path))
        with tempfile.TemporaryDirectory(prefix=".verify-local-state-", dir=root.parent) as temporary:
            recomputed_filtered_path = Path(temporary) / "filtered.npy"
            recomputed_filtered = write_localized_cone_filtered_npy(raw, active, grid, output_path=recomputed_filtered_path, config=filter_config, z_slab_size=z_slab_size)
            candidate_filtered = np.load(recomputed_filtered, mmap_mode="r", allow_pickle=False)
            try:
                _require_equal_arrays(candidate_filtered, filtered, "filtered state")
            finally:
                del candidate_filtered
            recomputed_projected = np.lib.format.open_memmap(Path(temporary) / "projected.npy", mode="w+", dtype=np.float64, shape=(grid.cell_count,))
            try:
                recomputed_filtered_data = np.load(recomputed_filtered, mmap_mode="r", allow_pickle=False)
                try:
                    apply_localized_heaviside_projection(recomputed_filtered_data, active, config=projection_config, out=recomputed_projected)
                finally:
                    del recomputed_filtered_data
                recomputed_projected.flush()
            finally:
                del recomputed_projected
            candidate_projected = np.load(Path(temporary) / "projected.npy", mmap_mode="r", allow_pickle=False)
            try:
                _require_equal_arrays(candidate_projected, projected, "projected state")
            finally:
                del candidate_projected
    finally:
        del projected
        del filtered
        del raw
        del active


def _require_equal_arrays(left: np.ndarray, right: np.ndarray, label: str) -> None:
    for start in range(0, left.size, _CHUNK):
        if not np.array_equal(left[start:start + _CHUNK], right[start:start + _CHUNK]):
            raise ValueError(f"{label} does not exactly match its declared transformation")


def _require_resources(parent: Path, disk_probe: Callable[[Path], int] | None, memory_probe: Callable[[], int] | None) -> None:
    disk = int((disk_probe or (lambda path: shutil.disk_usage(path).free))(parent))
    memory = int((memory_probe or _available_memory_bytes)())
    if disk < _MIN_RESOURCE_BYTES:
        raise ValueError("localized reference state requires at least 8 GiB free on the output volume")
    if memory < _MIN_RESOURCE_BYTES:
        raise ValueError("localized reference state requires at least 8 GiB available RAM")


def _available_memory_bytes() -> int:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MEMORYSTATUSEX(); status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, ValueError, OSError):
        return 0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _close_memmap(value: Any) -> None:
    """Close an NPY mapping now rather than relying on CPython refcounts.

    Directory rename and recursive deletion have stricter sharing semantics
    on Windows.  ``np.memmap`` exposes its underlying mapping specifically so
    a private staging tree can be released before it is removed or published.
    """

    if isinstance(value, np.memmap):
        mapping = getattr(value, "_mmap", None)
        if mapping is not None:
            mapping.close()


def _remove_staging_directory(staging: Path) -> OSError | None:
    if not staging.exists():
        return None
    try:
        shutil.rmtree(staging)
    except OSError as exc:
        return exc
    return None


def _write_failure_report(
    *,
    destination: Path,
    staging: Path,
    failed_stage: str,
    error: BaseException,
    cleanup_error: OSError | None,
) -> Path | None:
    """Atomically record a build failure without publishing a bundle.

    Reporting must never hide the original build exception.  A forced process
    termination cannot run this handler; the report therefore documents only
    failures that reached ordinary Python exception handling.
    """

    report = localized_reference_state_failure_report_path(destination)
    payload = {
        "schema_version": LOCALIZED_REFERENCE_STATE_FAILURE_SCHEMA_VERSION,
        "kind": LOCALIZED_REFERENCE_STATE_FAILURE_KIND,
        "status": "build_failed",
        "requested_output_directory": str(destination),
        "staging_directory": str(staging),
        "failed_stage": failed_stage,
        "exception_type": type(error).__name__,
        "exception_message": str(error),
        "staging_cleanup": "removed" if cleanup_error is None and not staging.exists() else "failed",
        "staging_cleanup_error": None if cleanup_error is None else str(cleanup_error),
    }
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{report.name}.tmp-", dir=report.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            os.replace(temporary, report)
        finally:
            if temporary.exists():
                temporary.unlink()
    except OSError:
        return None
    return report


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read reference bundle JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("reference bundle JSON must be an object")
    return data


def _read_ledger(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    required = {"schema_version", "kind", "problem_spec_sha256", "grid_sha256", "geometry_snapshot_relative_path", "geometry_snapshot_sha256", "initial_design_stl_sha256", "raw_manifest_relative_path", "raw_manifest_sha256", "state_manifest_relative_path", "state_manifest_sha256", "filter_config_sha256", "projection_config_sha256"}
    if set(data) != required or data.get("schema_version") != 1 or data.get("kind") != LOCALIZED_REFERENCE_STATE_KIND:
        raise ValueError("reference bundle ledger schema is invalid")
    for key in (item for item in required if item.endswith("sha256")):
        if not isinstance(data[key], str) or len(data[key]) != 64 or any(char not in "0123456789abcdef" for char in data[key]):
            raise ValueError(f"reference bundle ledger {key} is invalid")
    for key in ("geometry_snapshot_relative_path", "raw_manifest_relative_path", "state_manifest_relative_path"):
        _safe_under(path.parent, data[key])
    return data


def _safe_under(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("reference bundle path must be a safe relative path")
    candidate = root / relative
    try:
        return candidate.resolve().relative_to(root.resolve()) and candidate.resolve()
    except ValueError as exc:
        raise ValueError("reference bundle path escapes its directory") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical_bool_hash(values: np.ndarray) -> str:
    digest = hashlib.sha256()
    for start in range(0, values.size, _CHUNK):
        digest.update(np.asarray(values[start:start + _CHUNK], dtype=np.bool_).tobytes(order="C"))
    return digest.hexdigest()


__all__ = [
    "LOCALIZED_REFERENCE_STATE_FILENAME", "LOCALIZED_REFERENCE_STATE_KIND", "LOCALIZED_REFERENCE_STATE_SCHEMA_VERSION",
    "LOCALIZED_REFERENCE_STATE_FAILURE_KIND", "LOCALIZED_REFERENCE_STATE_FAILURE_SCHEMA_VERSION",
    "LocalizedReferenceStateBundle", "build_localized_reference_state_bundle", "localized_reference_state_failure_report_path",
    "verify_localized_reference_state_bundle",
]
