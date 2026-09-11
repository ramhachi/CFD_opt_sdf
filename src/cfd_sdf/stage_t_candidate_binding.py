"""Fail-closed lineage binding for a canonical Stage T density candidate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from .canonical_geometry_masks import (
    CanonicalGeometryMaskArtifacts,
    verify_canonical_geometry_mask_manifest,
)
from .canonical_grid_snapshot import (
    CANONICAL_MASK_IDS,
    VerifiedCanonicalGridSnapshot,
    load_and_verify_canonical_grid_snapshot,
)
from .fixed_grid_contract import CartesianCellGrid
from .fixed_grid_primal import load_fixed_grid_density_state
from .openfoam_grid_transfer import UniformCartesianCellGrid
from .problem_spec import (
    PROBLEM_SPEC_SCHEMA_VERSION,
    ProblemSpec,
    load_problem_spec,
    problem_spec_sha256,
    problem_spec_to_dict,
)


STAGE_T_CANDIDATE_BINDING_SCHEMA_VERSION = 1
STAGE_T_CANDIDATE_BINDING_KIND = "stage_t_candidate_binding"
STAGE_T_CANDIDATE_BINDING_PROFILE = "candidate_fixture_v1"
STAGE_T_CANDIDATE_BINDING_STATUS = "diagnostic_only"
CANONICAL_CELL_ORDER = "x-fastest"
FIXED_GRID_CELL_ORDER = "vtk-x-fastest"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_RHO_VARIANTS = frozenset({"rho", "rho_filtered", "rho_projected"})
_IDENTITY_MATRIX = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


@dataclass(frozen=True)
class StageTCandidateBindingArtifacts:
    path: Path
    binding: Mapping[str, object]


@dataclass(frozen=True)
class VerifiedStageTCandidateBinding:
    path: Path
    binding: Mapping[str, object]
    problem_spec: ProblemSpec
    canonical_grid: VerifiedCanonicalGridSnapshot
    geometry_manifest: CanonicalGeometryMaskArtifacts
    topology_state_path: Path
    density_vti_path: Path
    density_grid: CartesianCellGrid
    density_arrays: Mapping[str, np.ndarray]

    @property
    def candidate_id(self) -> str:
        return str(_required_mapping(self.binding, "candidate", "binding")["candidate_id"])


def write_stage_t_candidate_binding(
    path: str | Path,
    *,
    problem: ProblemSpec | str | Path,
    problem_snapshot: str | Path,
    canonical_grid_snapshot: str | Path,
    canonical_geometry_manifest: str | Path,
    topology_state: str | Path,
    density_vti: str | Path,
    candidate_id: str,
    parent_candidate_id: str | None = None,
    iteration: int = 0,
    rho_variant: str = "rho",
    require_execution_ready: bool = True,
) -> StageTCandidateBindingArtifacts:
    target = Path(path).resolve()
    if target.exists():
        raise FileExistsError(f"Stage T candidate binding already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    artifact_paths = {
        "problem_snapshot": problem_snapshot,
        "canonical_grid_snapshot": canonical_grid_snapshot,
        "canonical_geometry_manifest": canonical_geometry_manifest,
        "topology_state": topology_state,
        "density_vti": density_vti,
    }
    references = {
        key: _artifact_reference(value, target.parent, key)
        for key, value in artifact_paths.items()
    }
    _validate_candidate_id(candidate_id, "candidate_id")
    if parent_candidate_id is not None:
        _validate_candidate_id(parent_candidate_id, "parent_candidate_id")
    _validate_iteration(iteration)
    _validate_lineage(candidate_id, parent_candidate_id, iteration)
    if rho_variant not in _RHO_VARIANTS:
        raise ValueError(f"rho_variant must be one of {sorted(_RHO_VARIANTS)!r}")

    grid = load_and_verify_canonical_grid_snapshot(
        target.parent / references["canonical_grid_snapshot"]["path"], spec
    )
    binding: dict[str, object] = {
        "schema_version": STAGE_T_CANDIDATE_BINDING_SCHEMA_VERSION,
        "kind": STAGE_T_CANDIDATE_BINDING_KIND,
        "binding_profile": STAGE_T_CANDIDATE_BINDING_PROFILE,
        "qualification_status": STAGE_T_CANDIDATE_BINDING_STATUS,
        "ready_for_stage_s": False,
        "problem": {
            "snapshot_path": references["problem_snapshot"]["path"],
            "snapshot_sha256": references["problem_snapshot"]["sha256"],
            "problem_id": spec.problem_id,
            "problem_spec_sha256": problem_spec_sha256(spec),
            "execution_ready": spec.migration.execution_ready,
        },
        "candidate": {
            "candidate_id": candidate_id,
            "parent_candidate_id": parent_candidate_id,
            "iteration": iteration,
            "design_variable": "rho",
            "rho_variant": rho_variant,
        },
        "canonical_grid": {
            "snapshot_path": references["canonical_grid_snapshot"]["path"],
            "snapshot_sha256": references["canonical_grid_snapshot"]["sha256"],
            "grid_sha256": grid.snapshot.grid_sha256,
            "cell_order": CANONICAL_CELL_ORDER,
            "location": "cell",
        },
        "geometry_masks": {
            "manifest_path": references["canonical_geometry_manifest"]["path"],
            "manifest_sha256": references["canonical_geometry_manifest"]["sha256"],
            "grid_sha256": grid.snapshot.grid_sha256,
        },
        "topology_state": {
            "path": references["topology_state"]["path"],
            "sha256": references["topology_state"]["sha256"],
            "schema_version": 1,
            "kind": "fixed_grid_topology_state",
        },
        "density": {
            "path": references["density_vti"]["path"],
            "sha256": references["density_vti"]["sha256"],
            "kind": "fixed_grid_density",
            "array": rho_variant,
            "location": "cell",
            "source_cell_order": FIXED_GRID_CELL_ORDER,
            "grid_sha256": grid.snapshot.grid_sha256,
        },
        "source": {
            "grid_transform": {
                "kind": "identity",
                "matrix": [list(row) for row in _IDENTITY_MATRIX],
                "translation_m": [0.0, 0.0, 0.0],
            },
            "source_cell_order": FIXED_GRID_CELL_ORDER,
        },
    }
    # Validate the complete payload before making it visible.
    _verify_binding_payload(
        binding,
        target,
        spec,
        require_execution_ready=require_execution_ready,
    )
    target.write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    return StageTCandidateBindingArtifacts(path=target, binding=binding)


def verify_stage_t_candidate_binding(
    path: str | Path,
    problem: ProblemSpec | str | Path,
    *,
    require_execution_ready: bool = True,
) -> VerifiedStageTCandidateBinding:
    target = Path(path).resolve()
    try:
        binding = _mapping(
            json.loads(target.read_text(encoding="utf-8")),
            "Stage T candidate binding",
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read Stage T candidate binding: {target}") from exc
    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    return _verify_binding_payload(
        binding,
        target,
        spec,
        require_execution_ready=require_execution_ready,
    )


def _verify_binding_payload(
    binding: Mapping[str, object],
    binding_path: Path,
    spec: ProblemSpec,
    *,
    require_execution_ready: bool,
) -> VerifiedStageTCandidateBinding:
    _validate_binding_identity(binding)
    if require_execution_ready and not spec.migration.execution_ready:
        raise ValueError("Stage T candidate binding requires execution_ready ProblemSpec")
    if spec.migration.migrated:
        raise ValueError("Stage T candidate binding requires a native v2 ProblemSpec")
    root = binding_path.parent

    problem = _required_mapping(binding, "problem", "Stage T candidate binding")
    snapshot_path = _resolve_reference(root, problem, "snapshot_path", "problem")
    _match_hash(problem.get("snapshot_sha256"), snapshot_path, "problem snapshot")
    _validate_problem_snapshot(snapshot_path, spec)
    if problem.get("problem_id") != spec.problem_id:
        raise ValueError("problem.problem_id does not match ProblemSpec")
    if problem.get("problem_spec_sha256") != problem_spec_sha256(spec):
        raise ValueError("problem.problem_spec_sha256 does not match ProblemSpec")
    if problem.get("execution_ready") != spec.migration.execution_ready:
        raise ValueError("Stage T candidate binding execution_ready does not match ProblemSpec")

    canonical_grid = _required_mapping(binding, "canonical_grid", "Stage T candidate binding")
    grid_path = _resolve_reference(root, canonical_grid, "snapshot_path", "canonical_grid")
    _match_hash(canonical_grid.get("snapshot_sha256"), grid_path, "canonical grid snapshot")
    verified_grid = load_and_verify_canonical_grid_snapshot(grid_path, spec)
    _match_hash_value(
        canonical_grid.get("grid_sha256"),
        verified_grid.snapshot.grid_sha256,
        "canonical_grid.grid_sha256",
    )
    if canonical_grid.get("cell_order") != CANONICAL_CELL_ORDER:
        raise ValueError("canonical_grid.cell_order must be 'x-fastest'")
    if canonical_grid.get("location") != "cell":
        raise ValueError("canonical_grid.location must be 'cell'")

    geometry_binding = _required_mapping(
        binding, "geometry_masks", "Stage T candidate binding"
    )
    geometry_path = _resolve_reference(
        root, geometry_binding, "manifest_path", "geometry_masks"
    )
    _match_hash(
        geometry_binding.get("manifest_sha256"), geometry_path, "geometry mask manifest"
    )
    verified_geometry = verify_canonical_geometry_mask_manifest(geometry_path, spec)
    if verified_geometry.snapshot_path.resolve() != grid_path:
        raise ValueError(
            "geometry mask manifest does not reference the sidecar canonical grid snapshot"
        )
    _match_hash_value(
        geometry_binding.get("grid_sha256"),
        verified_grid.snapshot.grid_sha256,
        "geometry_masks.grid_sha256",
    )

    candidate = _required_mapping(binding, "candidate", "Stage T candidate binding")
    candidate_id = _validate_candidate_id(candidate.get("candidate_id"), "candidate_id")
    parent_id = candidate.get("parent_candidate_id")
    if parent_id is not None:
        parent_id = _validate_candidate_id(parent_id, "parent_candidate_id")
    iteration = _validate_iteration(candidate.get("iteration"))
    _validate_lineage(candidate_id, parent_id, iteration)
    if candidate.get("design_variable") != "rho":
        raise ValueError("candidate.design_variable must be 'rho'")
    rho_variant = candidate.get("rho_variant")
    if rho_variant not in _RHO_VARIANTS:
        raise ValueError(f"candidate.rho_variant must be one of {sorted(_RHO_VARIANTS)!r}")

    topology_binding = _required_mapping(
        binding, "topology_state", "Stage T candidate binding"
    )
    topology_path = _resolve_reference(root, topology_binding, "path", "topology_state")
    _match_hash(topology_binding.get("sha256"), topology_path, "topology state")
    if topology_binding.get("schema_version") != 1:
        raise ValueError("topology_state.schema_version must be 1")
    if topology_binding.get("kind") != "fixed_grid_topology_state":
        raise ValueError("topology_state.kind must be 'fixed_grid_topology_state'")
    density_state = load_fixed_grid_density_state(topology_path)
    state = density_state.state
    if state.get("design_variable") != "rho":
        raise ValueError("topology_state design_variable must be rho")

    density_binding = _required_mapping(binding, "density", "Stage T candidate binding")
    density_path = _resolve_reference(root, density_binding, "path", "density")
    density_hash = _match_hash(density_binding.get("sha256"), density_path, "density VTI")
    if density_binding.get("kind") != "fixed_grid_density":
        raise ValueError("density.kind must be 'fixed_grid_density'")
    if density_binding.get("location") != "cell":
        raise ValueError("density.location must be 'cell'")
    if density_binding.get("source_cell_order") != FIXED_GRID_CELL_ORDER:
        raise ValueError("density.source_cell_order must be 'vtk-x-fastest'")
    density_array_name = density_binding.get("array")
    if density_array_name != rho_variant:
        raise ValueError("density.array must match candidate.rho_variant")
    _match_hash_value(
        density_binding.get("grid_sha256"),
        verified_grid.snapshot.grid_sha256,
        "density.grid_sha256",
    )

    if density_state.density_vti.resolve() != density_path:
        raise ValueError("topology_state density_vti does not match sidecar density path")
    density_grid, arrays = density_state.grid, density_state.arrays
    canonical_uniform = UniformCartesianCellGrid(
        origin=density_grid.origin,
        spacing=density_grid.spacing,
        cell_shape=density_grid.cell_shape,
        cell_order=CANONICAL_CELL_ORDER,
    )
    if canonical_uniform.sha256 != verified_grid.snapshot.grid_sha256:
        raise ValueError(
            "density VTI grid does not match canonical grid; resampling is refused"
        )
    selected_rho = np.asarray(arrays[rho_variant], dtype=np.float64)
    if not np.isfinite(selected_rho).all():
        raise ValueError(f"density.vti:{rho_variant} contains non-finite values")
    if np.any(selected_rho < 0.0) or np.any(selected_rho > 1.0):
        raise ValueError(f"density.vti:{rho_variant} must satisfy 0 <= rho <= 1")
    _validate_masks_and_relationships(arrays, verified_grid, spec)

    declared_density_paths = [
        state.get("density_vti_sha256"),
        state.get("density_sha256"),
    ]
    artifacts = state.get("artifacts")
    if isinstance(artifacts, Mapping):
        density_artifact = artifacts.get("density_vti")
        if isinstance(density_artifact, Mapping):
            declared_density_paths.append(density_artifact.get("sha256"))
    for declared in declared_density_paths:
        if declared is not None:
            _match_hash_value(declared, density_hash, "topology state density hash")

    if state.get("density_array") != density_array_name:
        raise ValueError("topology_state density_array does not match sidecar density.array")
    _validate_state_lineage(state, spec, candidate_id, parent_id, iteration)

    _validate_source_mapping(
        _required_mapping(binding, "source", "Stage T candidate binding")
    )

    read_only_arrays = {}
    for name, values in arrays.items():
        array = np.asarray(values)
        array.setflags(write=False)
        read_only_arrays[name] = array
    return VerifiedStageTCandidateBinding(
        path=binding_path,
        binding=binding,
        problem_spec=spec,
        canonical_grid=verified_grid,
        geometry_manifest=verified_geometry,
        topology_state_path=topology_path,
        density_vti_path=density_path,
        density_grid=density_grid,
        density_arrays=read_only_arrays,
    )


def _validate_binding_identity(binding: Mapping[str, object]) -> None:
    expected = {
        "schema_version": STAGE_T_CANDIDATE_BINDING_SCHEMA_VERSION,
        "kind": STAGE_T_CANDIDATE_BINDING_KIND,
        "binding_profile": STAGE_T_CANDIDATE_BINDING_PROFILE,
        "qualification_status": STAGE_T_CANDIDATE_BINDING_STATUS,
        "ready_for_stage_s": False,
    }
    if any(binding.get(key) != value for key, value in expected.items()):
        raise ValueError("invalid Stage T candidate binding identity")


def _validate_problem_snapshot(path: Path, spec: ProblemSpec) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read ProblemSpec snapshot: {path}") from exc
    data = _mapping(raw, "ProblemSpec snapshot")
    if data.get("kind") != "cfd_optimization_problem_spec":
        raise ValueError("ProblemSpec snapshot has an invalid kind")
    if data.get("schema_version") != PROBLEM_SPEC_SCHEMA_VERSION:
        raise ValueError("ProblemSpec snapshot has an unsupported schema_version")
    if data.get("problem") != problem_spec_to_dict(spec):
        raise ValueError("ProblemSpec snapshot content does not match loaded ProblemSpec")
    _match_hash_value(
        data.get("problem_spec_sha256"),
        problem_spec_sha256(spec),
        "ProblemSpec snapshot problem_spec_sha256",
    )
    migration = _required_mapping(data, "migration", "ProblemSpec snapshot")
    if migration.get("execution_ready") != spec.migration.execution_ready:
        raise ValueError("ProblemSpec snapshot execution_ready does not match ProblemSpec")
    if migration.get("migrated") != spec.migration.migrated:
        raise ValueError("ProblemSpec snapshot migrated flag does not match ProblemSpec")


def _validate_masks_and_relationships(
    arrays: Mapping[str, np.ndarray],
    verified_grid: VerifiedCanonicalGridSnapshot,
    spec: ProblemSpec,
) -> None:
    for mask_id in CANONICAL_MASK_IDS:
        values = arrays.get(mask_id)
        if values is None:
            raise ValueError(f"density.vti is missing canonical mask: {mask_id}")
        expected = verified_grid.masks[mask_id]
        if not np.array_equal(values, expected):
            raise ValueError(f"density.vti:{mask_id} does not match canonical grid snapshot")
    active = np.asarray(arrays["active_design_mask"], dtype=bool)
    root = np.asarray(arrays["root_mask"], dtype=bool)
    if not np.any(active):
        raise ValueError("active_design_mask must not be empty")
    root_required = any(
        policy.mode in {"root_connected", "required_root_groups"}
        for policy in (
            spec.topology_policy.solid_connectivity,
            spec.topology_policy.void_connectivity,
        )
    )
    if root_required and not np.any(root):
        raise ValueError("root_mask is empty although topology_policy requires roots")


def _validate_source_mapping(value: object) -> None:
    source = _mapping(value, "Stage T candidate binding.source")
    transform = _required_mapping(source, "grid_transform", "source")
    if (
        source.get("source_cell_order") != FIXED_GRID_CELL_ORDER
        or transform.get("kind") != "identity"
        or transform.get("matrix") != [list(row) for row in _IDENTITY_MATRIX]
        or transform.get("translation_m") != [0.0, 0.0, 0.0]
    ):
        raise ValueError("source must declare vtk-x-fastest with identity transform")


def _validate_state_lineage(
    state: Mapping[str, object], spec: ProblemSpec, candidate_id: str,
    parent_id: str | None, iteration: int,
) -> None:
    expected = {"problem_id": spec.problem_id, "problem_spec_sha256": problem_spec_sha256(spec),
                "candidate_id": candidate_id, "parent_candidate_id": parent_id,
                "iteration": iteration}
    missing = sorted(key for key in expected if key not in state)
    if missing:
        raise ValueError(
            "topology state is missing candidate lineage: " + ", ".join(missing)
        )
    if any(state[key] != value for key, value in expected.items()):
        raise ValueError("topology state lineage does not match candidate binding")


def _artifact_reference(value: str | Path, root: Path, context: str) -> dict[str, str]:
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"{context} artifact is missing: {path}")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{context} must be inside the binding directory") from exc
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{context} path must be safely relative")
    return {
        "path": relative.as_posix(),
        "sha256": _sha256_file(path),
    }


def _resolve_reference(
    root: Path,
    mapping: Mapping[str, object],
    key: str,
    context: str,
) -> Path:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be a relative artifact path")
    raw = Path(value)
    if raw.is_absolute() or raw.drive or ".." in raw.parts:
        raise ValueError(f"{context}.{key} must be a safe relative path")
    path = (root / raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{context}.{key} escapes the binding directory") from exc
    if not path.is_file():
        raise ValueError(f"{context}.{key} artifact is missing: {path}")
    return path


def _match_hash(value: object, path: Path, context: str) -> str:
    actual = _sha256_file(path)
    _match_hash_value(value, actual, f"{context} sha256")
    return actual


def _match_hash_value(value: object, expected: str, context: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    if value != expected:
        raise ValueError(f"{context} does not match expected hash")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_mapping(value: Mapping[str, object], key: str, context: str) -> Mapping[str, object]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{context}.{key} must be an object")
    return item


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return value


def _validate_candidate_id(value: object, context: str) -> str:
    if not isinstance(value, str) or _CANDIDATE_ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{context} must be 1-128 characters using letters, digits, '_', '-', or '.'"
        )
    return value


def _validate_iteration(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("iteration must be a non-negative integer")
    return value


def _validate_lineage(
    candidate_id: str,
    parent_candidate_id: str | None,
    iteration: int,
) -> None:
    if parent_candidate_id == candidate_id:
        raise ValueError("parent_candidate_id must differ from candidate_id")
    if iteration == 0 and parent_candidate_id is not None:
        raise ValueError("iteration zero cannot have a parent_candidate_id")
    if iteration > 0 and parent_candidate_id is None:
        raise ValueError("iterations after zero require parent_candidate_id")
