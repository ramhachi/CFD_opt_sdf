"""Write provenance-bound v2 artifacts from completed OpenFOAM topology runs.

This module deliberately consumes the files OpenFOAM wrote during a run.  It
does not reconstruct a response from a log, invent a cell ordering, or accept
a merely compiled case as solver output.  The resulting ``.npz`` field file
uses the undecomposed OpenFOAM cell labels as its ordering; the labels are
recovered from each processor's ``cellProcAddressing`` file.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import io
import json
from math import isfinite, sqrt
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

import numpy as np

from .fixed_grid_artifacts import (
    read_fixed_grid_primal_summary,
    read_fixed_grid_sensitivity_summary,
    validate_primal_summary_against_problem_spec,
    validate_sensitivity_summary_against_problem_spec,
)
from .problem_spec import ProblemSpec, load_problem_spec, problem_spec_sha256, topology_constraint_ids


NATIVE_OPENFOAM_V2_ARTIFACT_SCHEMA_VERSION = 1
NATIVE_OPENFOAM_V2_ARTIFACT_PROVENANCE_KIND = "native_openfoam_v2_artifact_provenance"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROCESSOR_RE = re.compile(r"^processor([0-9]+)$")
_DIMENSIONS_RE = re.compile(r"\bdimensions\s+\[([^\]]+)\]\s*;", re.MULTILINE)
_OBJECT_RE = re.compile(r"\bobject\s+([^;\s]+)\s*;")
_CLASS_RE = re.compile(r"\bclass\s+([^;\s]+)\s*;")
_INTERNAL_FIELD_RE = re.compile(
    r"\binternalField\s+nonuniform\s+List<scalar>\s+([0-9]+)\s*\(\s*(.*?)\s*\)\s*;",
    re.DOTALL,
)
_LABEL_LIST_RE = re.compile(r"\n\s*([0-9]+)\s*\(\s*(.*?)\s*\)\s*;", re.DOTALL)


@dataclass(frozen=True)
class NativeOpenFoamV2Artifacts:
    """Paths written by :func:`write_native_openfoam_v2_artifacts`."""

    output_dir: Path
    primal_summary_json: Path
    sensitivity_summary_json: Path
    sensitivity_fields_npz: Path
    provenance_json: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "output_dir": str(self.output_dir),
            "primal_summary_json": str(self.primal_summary_json),
            "sensitivity_summary_json": str(self.sensitivity_summary_json),
            "sensitivity_fields_npz": str(self.sensitivity_fields_npz),
            "provenance_json": str(self.provenance_json),
        }


class NativeOpenFoamArtifactRefused(ValueError):
    """Raised when real OpenFOAM output lacks the bindings required by v2."""

    def __init__(self, assessment: Mapping[str, object]) -> None:
        self.assessment = dict(assessment)
        reasons = self.assessment.get("reasons") or []
        super().__init__("Native v2 OpenFOAM artifacts refused: " + ", ".join(map(str, reasons)))


def assess_native_openfoam_v2_artifact_readiness(
    *,
    project_yaml: str | Path,
    bundle_dir: str | Path,
) -> dict[str, object]:
    """Return an explicit non-mutating v2 export decision for a completed bundle.

    A compiled/qualified OpenFOAM run is insufficient by itself.  The v2
    contract needs independently declared unit, density-gradient, mesh-grid,
    and topology-constraint bindings.  Until a solver adapter emits that
    binding, this function deliberately returns ``ready: false`` instead of
    presenting a coefficient, filtered sensitivity, or unrelated mesh field
    as a native v2 artifact.
    """

    spec = load_problem_spec(project_yaml)
    root = Path(bundle_dir).resolve()
    reasons: list[str] = []
    binding_path = root / "native_openfoam_v2_artifact_binding.json"
    if not binding_path.is_file():
        return {
            "kind": "native_openfoam_v2_artifact_readiness",
            "schema_version": NATIVE_OPENFOAM_V2_ARTIFACT_SCHEMA_VERSION,
            **_problem_binding_dict(spec),
            "ready": False,
            "reasons": [
                "missing_native_artifact_binding",
                "response_value_unit_provenance_not_bound",
                "rho_gradient_convention_not_bound",
                "mesh_grid_mapping_not_bound",
                "topology_constraint_values_not_available",
            ],
        }
    try:
        binding = _read_json_mapping(binding_path)
        _validate_native_binding_header(binding, spec, root)
        _binding_response_values(binding, spec)
    except ValueError:
        reasons.append("response_value_unit_provenance_not_bound")
    try:
        binding = _read_json_mapping(binding_path)
        _validate_native_binding_header(binding, spec, root)
        _binding_gradients(binding, spec)
        _validate_bound_sensitivity_sources(binding, spec, root)
    except ValueError:
        reasons.append("rho_gradient_convention_not_bound")
    try:
        binding = _read_json_mapping(binding_path)
        _validate_native_binding_header(binding, spec, root)
        _binding_mesh(binding, spec)
    except ValueError:
        reasons.append("mesh_grid_mapping_not_bound")
    try:
        binding = _read_json_mapping(binding_path)
        _validate_native_binding_header(binding, spec, root)
        _binding_topology_values(binding, spec)
    except ValueError:
        reasons.append("topology_constraint_values_not_available")
    return {
        "kind": "native_openfoam_v2_artifact_readiness",
        "schema_version": NATIVE_OPENFOAM_V2_ARTIFACT_SCHEMA_VERSION,
        **_problem_binding_dict(spec),
        "ready": not reasons,
        "reasons": reasons,
        "binding_path": str(binding_path),
    }


def write_native_openfoam_v2_artifacts(
    *,
    project_yaml: str | Path,
    bundle_dir: str | Path,
    output_dir: str | Path,
) -> NativeOpenFoamV2Artifacts:
    """Extract native v2 summaries and cell fields from qualified OpenFOAM runs.

    The writer is intentionally fail-closed.  It requires the qualified
    convergence artifact and its provenance-bound evidence, checks the case
    bundle against the requested problem, verifies every evidence source that
    established numerical completion, and requires one final objective result
    plus an unambiguous decomposed final ``topOSens`` field per response.

    No files are published to ``output_dir`` unless every preflight and source
    extraction succeeds.
    """

    spec = load_problem_spec(project_yaml)
    resolved_bundle_dir = Path(bundle_dir).resolve()
    resolved_output_dir = Path(output_dir).resolve()
    if resolved_output_dir.exists():
        raise ValueError(f"Output directory already exists: {resolved_output_dir}")
    if not resolved_bundle_dir.is_dir():
        raise ValueError(f"OpenFOAM case bundle directory does not exist: {resolved_bundle_dir}")
    readiness = assess_native_openfoam_v2_artifact_readiness(
        project_yaml=project_yaml,
        bundle_dir=resolved_bundle_dir,
    )
    if readiness["ready"] is not True:
        raise NativeOpenFoamArtifactRefused(readiness)
    binding = _read_json_mapping(resolved_bundle_dir / "native_openfoam_v2_artifact_binding.json")

    source_hashes: dict[str, str] = {}
    bundle_path = _required_file(resolved_bundle_dir / "openfoam_case_bundle.json")
    bundle_bytes = bundle_path.read_bytes()
    bundle_sha256 = _sha256_bytes(bundle_bytes)
    source_hashes["bundle/openfoam_case_bundle.json"] = bundle_sha256
    bundle = _read_json_mapping(bundle_path)
    _validate_bundle(bundle, spec)

    evidence_path = _required_file(resolved_bundle_dir / "convergence_evidence.json")
    evidence_bytes = evidence_path.read_bytes()
    source_hashes["bundle/convergence_evidence.json"] = _sha256_bytes(evidence_bytes)
    evidence = _read_json_mapping(evidence_path)
    evidence_provenance_path = _required_file(
        resolved_bundle_dir / "convergence_evidence.json.provenance.json"
    )
    evidence_provenance_bytes = evidence_provenance_path.read_bytes()
    source_hashes["bundle/convergence_evidence.json.provenance.json"] = _sha256_bytes(
        evidence_provenance_bytes
    )
    evidence_provenance = _read_json_mapping(evidence_provenance_path)
    _validate_evidence_provenance(
        evidence_provenance,
        evidence_bytes=evidence_bytes,
        bundle_sha256=bundle_sha256,
        spec=spec,
    )

    qualification_path = _required_file(resolved_bundle_dir / "convergence_qualification.json")
    qualification_bytes = qualification_path.read_bytes()
    source_hashes["bundle/convergence_qualification.json"] = _sha256_bytes(qualification_bytes)
    qualification = _read_json_mapping(qualification_path)
    _validate_qualification(qualification, spec)

    flow_entries = _bundle_flow_entries(bundle, spec)
    _validate_complete_evidence(evidence, spec, resolved_bundle_dir, source_hashes)

    response_values: list[dict[str, object]] = []
    response_gradients: dict[str, np.ndarray] = {}
    response_gradient_details: dict[str, dict[str, object]] = {}
    response_conversions: dict[str, dict[str, object]] = {}
    response_value_bindings = _binding_response_values(binding, spec)
    expected_global_cell_ids: np.ndarray | None = None
    for response in spec.responses:
        flow_entry = flow_entries[response.flow_case_id]
        case_dir = _contained_case_dir(resolved_bundle_dir, flow_entry["case_dir"])
        compilation_path = _contained_case_file(
            resolved_bundle_dir, flow_entry["compilation_metadata"]
        )
        compilation_bytes = compilation_path.read_bytes()
        _require_sha256_match(
            compilation_bytes,
            flow_entry["compilation_sha256"],
            f"bundle compilation metadata for {response.flow_case_id!r}",
        )
        source_hashes[f"{response.flow_case_id}/{compilation_path.name}"] = _sha256_bytes(
            compilation_bytes
        )
        compilation = _read_json_mapping(compilation_path)
        _validate_compilation(compilation, spec, response.flow_case_id)

        response_metadata_path = _required_file(case_dir / "generated_openfoam_responses.json")
        response_metadata_bytes = response_metadata_path.read_bytes()
        _require_sha256_match(
            response_metadata_bytes,
            _nested_required_text(compilation, "responses", "metadata_sha256"),
            f"response metadata for {response.flow_case_id!r}",
        )
        source_hashes[f"{response.flow_case_id}/generated_openfoam_responses.json"] = _sha256_bytes(
            response_metadata_bytes
        )
        response_metadata = _read_json_mapping(response_metadata_path)
        mapping = _response_mapping(response_metadata, response.flow_case_id, response.id)

        objective_file = _objective_result_file(case_dir, mapping)
        objective_bytes = objective_file.read_bytes()
        source_hashes[
            f"{response.flow_case_id}/{objective_file.relative_to(case_dir).as_posix()}"
        ] = _sha256_bytes(objective_bytes)
        raw_value = _read_final_objective_value(objective_file)
        value_binding = response_value_bindings[(response.flow_case_id, response.id)]
        conversion = _force_conversion(spec, response, value_binding)
        value = _finite_scaled_value(
            raw_value,
            conversion["factor_N_per_coefficient"],
            f"response {response.flow_case_id}/{response.id}",
        )
        response_conversions[f"{response.flow_case_id}/{response.id}"] = conversion
        response_values.append(
            {
                "flow_case_id": response.flow_case_id,
                "response_id": response.id,
                "value": value,
                "units": value_binding["units"],
                "status": "converged",
                "source": value_binding["source"],
                "raw_value": raw_value,
                "raw_units": "1",
                "conversion": conversion,
            }
        )

        array_name = f"d_{response.id}_d_rho"
        if array_name in response_gradients:
            raise ValueError(f"Duplicate native response gradient array name: {array_name!r}")
        _validate_topo_sensitivity_case_source(
            case_dir,
            adjoint_solver_id=_required_text(mapping, "adjoint_solver_id", "response mapping"),
        )
        global_cell_ids, values, details, field_hashes = _read_decomposed_topo_sensitivity(
            case_dir,
            adjoint_solver_id=_required_text(mapping, "adjoint_solver_id", "response mapping"),
        )
        source_hashes.update(
            {
                f"{response.flow_case_id}/{relative_path}": digest
                for relative_path, digest in field_hashes.items()
            }
        )
        if expected_global_cell_ids is None:
            expected_global_cell_ids = global_cell_ids
        elif not np.array_equal(expected_global_cell_ids, global_cell_ids):
            raise ValueError(
                "Response sensitivity fields do not share the same undecomposed OpenFOAM "
                "cell-label ordering"
            )
        converted_values = values * float(conversion["factor_N_per_coefficient"])
        if not np.isfinite(converted_values).all():
            raise ValueError(f"Converted OpenFOAM sensitivity is non-finite for {response.id!r}")
        response_gradients[array_name] = converted_values
        response_gradient_details[array_name] = {**details, "conversion": conversion}

    if expected_global_cell_ids is None:
        raise ValueError("No response sensitivity fields were extracted")
    mesh_binding = _binding_mesh(binding, spec)
    if mesh_binding["cell_count"] != int(expected_global_cell_ids.size):
        raise ValueError("Native artifact mesh binding cell_count does not match OpenFOAM output")

    objective_values = _aggregate_objectives(spec, response_values)
    constraint_values = _aggregate_constraints(spec, response_values) + _binding_topology_values(binding, spec)
    gradient_bindings = _response_gradient_bindings(
        spec, response_gradient_details, _binding_gradients(binding, spec)
    )

    primal_summary = {
        "schema_version": 2,
        "kind": "fixed_grid_primal_summary",
        **_problem_binding_dict(spec),
        "flow_case_ids": [flow.id for flow in spec.flow_cases],
        "status": "converged",
        "response_values": response_values,
        "objective_values": objective_values,
        "constraint_values": constraint_values,
        "response_conversions": response_conversions,
        "producer": "openfoam_native_v2_artifacts",
    }
    sensitivity_summary = {
        "schema_version": 2,
        "kind": "fixed_grid_sensitivity_summary",
        **_problem_binding_dict(spec),
        "flow_case_ids": [flow.id for flow in spec.flow_cases],
        "status": "extracted",
        "gradient_bindings": gradient_bindings,
        "response_conversions": response_conversions,
        "producer": "openfoam_native_v2_artifacts",
    }

    # Validate the exact native summaries before publishing them.
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{resolved_output_dir.name}.native-v2-", dir=resolved_output_dir.parent)
    )
    try:
        primal_path = staging_root / "fixed_grid_primal_summary.json"
        sensitivity_path = staging_root / "fixed_grid_sensitivity_summary.json"
        fields_path = staging_root / "native_openfoam_sensitivity_fields.npz"
        provenance_path = staging_root / "native_openfoam_artifact_provenance.json"

        _write_json(primal_path, primal_summary)
        _write_json(sensitivity_path, sensitivity_summary)
        _write_npz(
            fields_path,
            {
                "global_cell_ids": expected_global_cell_ids.astype(np.int64, copy=False),
                **response_gradients,
            },
        )
        field_artifact = {
            "path": fields_path.name,
            "sha256": _sha256_file(fields_path),
            "format": "npz",
            "global_cell_ids_array": "global_cell_ids",
            "ordering": "undecomposed_openfoam_cell_label_ascending",
            "array_count": len(response_gradients),
            "cell_count": int(expected_global_cell_ids.size),
            "response_arrays": response_gradient_details,
        }
        primal_summary["field_artifact"] = field_artifact
        sensitivity_summary["field_artifact"] = field_artifact
        _write_json(primal_path, primal_summary)
        _write_json(sensitivity_path, sensitivity_summary)

        provenance = {
            "schema_version": NATIVE_OPENFOAM_V2_ARTIFACT_SCHEMA_VERSION,
            "kind": NATIVE_OPENFOAM_V2_ARTIFACT_PROVENANCE_KIND,
            **_problem_binding_dict(spec),
            "bundle_metadata_sha256": bundle_sha256,
            "response_conversions": response_conversions,
            "source_files_sha256": dict(sorted(source_hashes.items())),
            "output_files_sha256": {
                primal_path.name: _sha256_file(primal_path),
                sensitivity_path.name: _sha256_file(sensitivity_path),
                fields_path.name: _sha256_file(fields_path),
            },
        }
        _write_json(provenance_path, provenance)

        # Re-check the persisted summaries and complete provenance before publication.
        validate_primal_summary_against_problem_spec(read_fixed_grid_primal_summary(primal_path), spec)
        validate_sensitivity_summary_against_problem_spec(
            read_fixed_grid_sensitivity_summary(sensitivity_path), spec
        )
        verify_native_openfoam_v2_artifacts(
            output_dir=staging_root,
            bundle_dir=resolved_bundle_dir,
            project_yaml=project_yaml,
        )
        staging_root.replace(resolved_output_dir)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    return NativeOpenFoamV2Artifacts(
        output_dir=resolved_output_dir,
        primal_summary_json=resolved_output_dir / "fixed_grid_primal_summary.json",
        sensitivity_summary_json=resolved_output_dir / "fixed_grid_sensitivity_summary.json",
        sensitivity_fields_npz=resolved_output_dir / "native_openfoam_sensitivity_fields.npz",
        provenance_json=resolved_output_dir / "native_openfoam_artifact_provenance.json",
    )


def verify_native_openfoam_v2_artifacts(
    *,
    output_dir: str | Path,
    bundle_dir: str | Path,
    project_yaml: str | Path,
) -> None:
    """Verify published artifact hashes and the current run files they bind to."""

    spec = load_problem_spec(project_yaml)
    root = Path(output_dir).resolve()
    bundle_root = Path(bundle_dir).resolve()
    provenance_path = _required_file(root / "native_openfoam_artifact_provenance.json")
    provenance = _read_json_mapping(provenance_path)
    if provenance.get("schema_version") != NATIVE_OPENFOAM_V2_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("Native OpenFOAM artifact provenance has unsupported schema_version")
    if provenance.get("kind") != NATIVE_OPENFOAM_V2_ARTIFACT_PROVENANCE_KIND:
        raise ValueError("Native OpenFOAM artifact provenance has invalid kind")
    _validate_problem_binding(provenance, spec, "native artifact provenance")
    _require_sha256_match(
        (bundle_root / "openfoam_case_bundle.json").read_bytes(),
        _required_text(provenance, "bundle_metadata_sha256", "native artifact provenance"),
        "native artifact provenance bundle binding",
    )
    output_hashes = _required_mapping(provenance, "output_files_sha256", "native artifact provenance")
    for filename, digest in output_hashes.items():
        if not isinstance(filename, str) or not _is_sha256(digest):
            raise ValueError("Native artifact provenance has an invalid output file hash")
        _require_sha256_match((_required_file(root / filename)).read_bytes(), digest, filename)
    source_hashes = _required_mapping(provenance, "source_files_sha256", "native artifact provenance")
    for relative_path, digest in source_hashes.items():
        if not isinstance(relative_path, str) or not _is_sha256(digest):
            raise ValueError("Native artifact provenance has an invalid source file hash")
        source_path = _resolve_provenance_source(bundle_root, relative_path)
        _require_sha256_match(source_path.read_bytes(), digest, relative_path)

    validate_primal_summary_against_problem_spec(
        read_fixed_grid_primal_summary(root / "fixed_grid_primal_summary.json"), spec
    )
    validate_sensitivity_summary_against_problem_spec(
        read_fixed_grid_sensitivity_summary(root / "fixed_grid_sensitivity_summary.json"), spec
    )


def _validate_bundle(bundle: Mapping[str, Any], spec: ProblemSpec) -> None:
    if bundle.get("schema_version") != 1 or bundle.get("kind") != "openfoam_case_bundle":
        raise ValueError("OpenFOAM bundle is not a supported compiled case bundle")
    if bundle.get("status") != "compiled" or bundle.get("compile_ready") is not True:
        raise ValueError("OpenFOAM bundle is not compile-ready")
    _validate_problem_binding(bundle, spec, "OpenFOAM bundle")


def _validate_qualification(qualification: Mapping[str, Any], spec: ProblemSpec) -> None:
    if qualification.get("schema_version") != 1 or qualification.get("kind") != "openfoam_convergence_qualification":
        raise ValueError("Convergence qualification has an unsupported schema")
    _validate_problem_binding(qualification, spec, "convergence qualification")
    if qualification.get("status") != "pass" or qualification.get("qualified") is not True:
        raise ValueError("Convergence qualification is not a passing qualified result")
    flows = _required_mapping(qualification, "flow_cases", "convergence qualification")
    expected = {flow.id for flow in spec.flow_cases}
    if set(flows) != expected:
        raise ValueError("Convergence qualification flow cases do not exactly match the problem")
    for flow_id, value in flows.items():
        if not isinstance(value, Mapping) or value.get("qualified") is not True or value.get("status") != "pass":
            raise ValueError(f"Convergence qualification flow case {flow_id!r} did not pass")


def _validate_evidence_provenance(
    provenance: Mapping[str, Any],
    *,
    evidence_bytes: bytes,
    bundle_sha256: str,
    spec: ProblemSpec,
) -> None:
    if provenance.get("schema_version") != 1 or provenance.get("kind") != "openfoam_convergence_evidence_provenance":
        raise ValueError("Convergence evidence provenance has an unsupported schema")
    _validate_problem_binding(provenance, spec, "convergence evidence provenance")
    _require_sha256_match(
        evidence_bytes,
        _required_text(provenance, "evidence_sha256", "convergence evidence provenance"),
        "convergence evidence provenance",
    )
    if provenance.get("bundle_metadata_sha256") != bundle_sha256:
        raise ValueError("Convergence evidence provenance does not bind the current case bundle")
    flow_case_ids = provenance.get("flow_case_ids")
    expected = [flow.id for flow in spec.flow_cases]
    if flow_case_ids != sorted(expected):
        raise ValueError("Convergence evidence provenance flow cases do not match the problem")


def _validate_complete_evidence(
    evidence: Mapping[str, Any],
    spec: ProblemSpec,
    bundle_dir: Path,
    source_hashes: dict[str, str],
) -> None:
    flows = _required_mapping(evidence, "flow_cases", "convergence evidence")
    expected = {flow.id for flow in spec.flow_cases}
    if set(flows) != expected:
        raise ValueError("Convergence evidence flow cases do not exactly match the problem")
    for flow_id in sorted(expected):
        item = _required_mapping(flows, flow_id, "convergence evidence flow cases")
        if item.get("complete") is not True or item.get("status") != "complete":
            raise ValueError(f"Convergence evidence for {flow_id!r} is incomplete")
        case_dir_name = _required_text(item, "case_directory_name", f"evidence flow {flow_id}")
        case_dir = _contained_case_dir(bundle_dir, case_dir_name)
        sources = _required_mapping(item, "sources", f"evidence flow {flow_id}")
        for source_name, source in sources.items():
            if not isinstance(source, Mapping) or source.get("status") != "found":
                raise ValueError(f"Evidence source {source_name!r} for {flow_id!r} was not found")
            relative_path = _required_text(source, "path", f"evidence source {source_name}")
            path = _contained_case_file(case_dir, relative_path)
            digest = _required_text(source, "sha256", f"evidence source {source_name}")
            _require_sha256_match(path.read_bytes(), digest, f"evidence source {flow_id}/{relative_path}")
            source_hashes[f"{flow_id}/{relative_path}"] = digest


def _bundle_flow_entries(bundle: Mapping[str, Any], spec: ProblemSpec) -> dict[str, Mapping[str, Any]]:
    raw = _required_mapping(bundle, "flow_cases", "OpenFOAM bundle")
    expected = {flow.id for flow in spec.flow_cases}
    if set(raw) != expected:
        raise ValueError("OpenFOAM bundle flow cases do not exactly match the problem")
    entries: dict[str, Mapping[str, Any]] = {}
    for flow_id, entry in raw.items():
        if not isinstance(entry, Mapping) or entry.get("status") != "compiled":
            raise ValueError(f"OpenFOAM bundle flow case {flow_id!r} is not compiled")
        for key in ("case_dir", "compilation_metadata", "compilation_sha256"):
            _required_text(entry, key, f"OpenFOAM bundle flow case {flow_id}")
        entries[flow_id] = entry
    return entries


def _validate_compilation(compilation: Mapping[str, Any], spec: ProblemSpec, flow_case_id: str) -> None:
    if compilation.get("schema_version") != 1 or compilation.get("kind") != "openfoam_case_compilation":
        raise ValueError(f"Invalid OpenFOAM compilation metadata for {flow_case_id!r}")
    _validate_problem_binding(compilation, spec, f"OpenFOAM compilation {flow_case_id}")
    if compilation.get("flow_case_id") != flow_case_id:
        raise ValueError(f"OpenFOAM compilation metadata flow case mismatch for {flow_case_id!r}")


def _response_mapping(metadata: Mapping[str, Any], flow_case_id: str, response_id: str) -> Mapping[str, Any]:
    if metadata.get("schema_version") != 1 or metadata.get("kind") != "generated_openfoam_responses":
        raise ValueError(f"Invalid generated response metadata for {flow_case_id!r}")
    mappings = metadata.get("response_mappings")
    if not isinstance(mappings, list):
        raise ValueError(f"Generated response metadata for {flow_case_id!r} has no mappings")
    matches = [
        item
        for item in mappings
        if isinstance(item, Mapping)
        and item.get("flow_case_id") == flow_case_id
        and item.get("response_id") == response_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Generated response metadata must contain exactly one mapping for "
            f"{flow_case_id!r}/{response_id!r}"
        )
    for key in ("objective_name", "adjoint_solver_id"):
        _required_text(matches[0], key, "generated response mapping")
    return matches[0]


def _objective_result_file(case_dir: Path, mapping: Mapping[str, Any]) -> Path:
    objective_name = _required_text(mapping, "objective_name", "response mapping")
    adjoint_solver_id = _required_text(mapping, "adjoint_solver_id", "response mapping")
    path = case_dir / "optimisation" / "objective" / "0" / f"{objective_name}{adjoint_solver_id}"
    return _required_file(path)


def _read_final_objective_value(path: Path) -> float:
    final: float | None = None
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        tokens = line.split()
        if len(tokens) < 2:
            continue
        try:
            float(tokens[0])
            value = float(tokens[1])
        except ValueError:
            continue
        if not isfinite(value):
            raise ValueError(f"Objective result has a non-finite final value: {path}")
        final = value
    if final is None:
        raise ValueError(f"Objective result has no numeric J value: {path}")
    return final


def _read_decomposed_topo_sensitivity(
    case_dir: Path,
    *,
    adjoint_solver_id: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, object], dict[str, str]]:
    processor_dirs = _processor_dirs(case_dir)
    entries: list[tuple[int, np.ndarray, np.ndarray]] = []
    hashes: dict[str, str] = {}
    dimensions: str | None = None
    field_object = f"topOSens{adjoint_solver_id}"
    for processor_index, processor_dir in processor_dirs:
        field_path = _required_file(processor_dir / "1" / f"{field_object}.gz")
        labels_path = _required_file(
            processor_dir / "constant" / "polyMesh" / "cellProcAddressing.gz"
        )
        values, field_dimensions = _read_openfoam_scalar_field(field_path, expected_object=field_object)
        labels = _read_openfoam_label_list(labels_path)
        if values.size != labels.size:
            raise ValueError(
                f"Processor {processor_index} sensitivity field has {values.size} values but "
                f"{labels.size} cell addresses"
            )
        if dimensions is None:
            dimensions = field_dimensions
        elif dimensions != field_dimensions:
            raise ValueError("OpenFOAM final topO sensitivity fields have inconsistent dimensions")
        entries.append((processor_index, labels, values))
        hashes[str(field_path.relative_to(case_dir).as_posix())] = _sha256_file(field_path)
        hashes[str(labels_path.relative_to(case_dir).as_posix())] = _sha256_file(labels_path)

    global_ids = np.concatenate([item[1] for item in entries]).astype(np.int64, copy=False)
    values = np.concatenate([item[2] for item in entries]).astype(np.float64, copy=False)
    if np.any(global_ids < 0) or len(np.unique(global_ids)) != global_ids.size:
        raise ValueError("OpenFOAM cellProcAddressing does not provide unique non-negative cell labels")
    order = np.argsort(global_ids, kind="stable")
    global_ids = global_ids[order]
    values = values[order]
    expected = np.arange(global_ids.size, dtype=np.int64)
    if not np.array_equal(global_ids, expected):
        raise ValueError(
            "OpenFOAM cellProcAddressing must cover contiguous undecomposed cell labels starting at zero"
        )
    if not np.isfinite(values).all():
        raise ValueError("OpenFOAM final topO sensitivity contains non-finite values")
    return global_ids, values, {
        "source": "openfoam.topOSens",
        "openfoam_object": field_object,
        "openfoam_dimensions": dimensions,
        "processor_count": len(entries),
        "cell_count": int(values.size),
    }, hashes


def _read_openfoam_scalar_field(path: Path, *, expected_object: str) -> tuple[np.ndarray, str]:
    text = _read_gzip_text(path)
    field_class = _CLASS_RE.search(text)
    if field_class is None or field_class.group(1) != "volScalarField":
        raise ValueError(f"OpenFOAM sensitivity is not a volScalarField: {path}")
    object_match = _OBJECT_RE.search(text)
    if object_match is None or object_match.group(1) != expected_object:
        raise ValueError(f"OpenFOAM sensitivity object name does not match {expected_object!r}: {path}")
    dimensions_match = _DIMENSIONS_RE.search(text)
    if dimensions_match is None:
        raise ValueError(f"OpenFOAM sensitivity has no dimensions declaration: {path}")
    match = _INTERNAL_FIELD_RE.search(text)
    if match is None:
        raise ValueError(f"OpenFOAM sensitivity must have a nonuniform scalar internalField: {path}")
    count = int(match.group(1))
    try:
        values = np.fromstring(match.group(2), sep=" ", dtype=np.float64)
    except ValueError as exc:  # pragma: no cover - NumPy error text varies
        raise ValueError(f"OpenFOAM sensitivity has invalid scalar values: {path}") from exc
    if values.size != count:
        raise ValueError(f"OpenFOAM sensitivity expected {count} values, found {values.size}: {path}")
    if not np.isfinite(values).all():
        raise ValueError(f"OpenFOAM sensitivity contains non-finite values: {path}")
    return values, " ".join(dimensions_match.group(1).split())


def _read_openfoam_label_list(path: Path) -> np.ndarray:
    text = _read_gzip_text(path)
    if _CLASS_RE.search(text) is None or _CLASS_RE.search(text).group(1) != "labelList":
        raise ValueError(f"OpenFOAM cellProcAddressing is not a labelList: {path}")
    match = _LABEL_LIST_RE.search(text)
    if match is None:
        raise ValueError(f"OpenFOAM cellProcAddressing has no label list: {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", dtype=np.int64)
    if values.size != count:
        raise ValueError(f"OpenFOAM cellProcAddressing expected {count} labels, found {values.size}: {path}")
    return values


def _processor_dirs(case_dir: Path) -> list[tuple[int, Path]]:
    processors: list[tuple[int, Path]] = []
    for item in case_dir.iterdir():
        match = _PROCESSOR_RE.match(item.name)
        if item.is_dir() and match:
            processors.append((int(match.group(1)), item))
    processors.sort(key=lambda item: item[0])
    if not processors or [index for index, _ in processors] != list(range(len(processors))):
        raise ValueError(f"OpenFOAM case has no contiguous processor0..N directories: {case_dir}")
    return processors


def _aggregate_objectives(spec: ProblemSpec, response_values: list[dict[str, object]]) -> list[dict[str, object]]:
    values = {(str(item["flow_case_id"]), str(item["response_id"])): item for item in response_values}
    output: list[dict[str, object]] = []
    for objective in spec.objectives:
        selected = [values[(term.flow_case_id, term.response_id)] for term in objective.terms]
        units = _common_units(selected, f"objective {objective.id!r}")
        value = sum(float(term.coefficient) * float(item["value"]) for term, item in zip(objective.terms, selected))
        output.append(
            {
                "objective_id": objective.id,
                "value": value,
                "units": units,
                "status": "evaluated",
                "source": "weighted_openfoam_response_values",
            }
        )
    return output


def _aggregate_constraints(spec: ProblemSpec, response_values: list[dict[str, object]]) -> list[dict[str, object]]:
    values = {(str(item["flow_case_id"]), str(item["response_id"])): item for item in response_values}
    output: list[dict[str, object]] = []
    for constraint in spec.constraints:
        selected = [values[(term.flow_case_id, term.response_id)] for term in constraint.terms]
        units = _common_units(selected, f"constraint {constraint.id!r}")
        value = sum(float(term.coefficient) * float(item["value"]) for term, item in zip(constraint.terms, selected))
        output.append(
            {
                "scope": "aggregate",
                "constraint_id": constraint.id,
                "value": value,
                "units": units,
                "status": "evaluated",
                "source": "weighted_openfoam_response_values",
            }
        )
    return output


def _response_gradient_bindings(
    spec: ProblemSpec,
    details: Mapping[str, Mapping[str, object]],
    declared_bindings: Mapping[tuple[str, str], Mapping[str, object]],
) -> list[dict[str, object]]:
    bindings: list[dict[str, object]] = []
    for response in spec.responses:
        array_name = f"d_{response.id}_d_rho"
        item_details = details[array_name]
        declared = declared_bindings[(response.flow_case_id, response.id)]
        if declared["openfoam_dimensions"] != item_details["openfoam_dimensions"]:
            raise ValueError(
                f"Native gradient binding OpenFOAM dimensions do not match field for {response.id!r}"
            )
        bindings.append(
            {
                "target_kind": "response",
                "flow_case_id": response.flow_case_id,
                "response_id": response.id,
                "scope": "flow",
                "design_variable_id": "rho",
                "array_name": array_name,
                "units": declared["units"],
                "status": "extracted",
                "source": declared["source"],
                "conversion": item_details["conversion"],
            }
        )
    return bindings


def _response_units(kind: str) -> str:
    if kind == "force":
        return "N"
    raise ValueError(f"Native OpenFOAM artifact writer does not support response kind: {kind!r}")


def _force_conversion(
    spec: ProblemSpec,
    response: Any,
    binding: Mapping[str, object],
) -> dict[str, object]:
    """Derive the only supported porous coefficient-to-force conversion."""

    if response.kind != "force":
        raise ValueError("Coefficient-to-force conversion is only supported for force responses")
    if binding.get("source_quantity") != "porous_directional_force_coefficient":
        raise ValueError("Native force binding source_quantity must be porous_directional_force_coefficient")
    if binding.get("conversion_kind") != "dynamic_pressure_area":
        raise ValueError("Native force binding conversion_kind must be dynamic_pressure_area")
    if binding.get("units") != "N":
        raise ValueError("Native force binding output units must be N")
    forbidden = {"conversion_factor", "factor", "factor_N_per_coefficient"}.intersection(binding)
    if forbidden:
        raise ValueError(
            "Native force binding must not provide a custom conversion factor: "
            + ", ".join(sorted(forbidden))
        )
    if spec.reference_values is None or spec.reference_values.area_m2 is None:
        raise ValueError("Coefficient-to-force conversion requires reference_values.area_m2")
    area = float(spec.reference_values.area_m2)
    flow = next((item for item in spec.flow_cases if item.id == response.flow_case_id), None)
    if flow is None:  # Defensive: ProblemSpec validation normally makes this unreachable.
        raise ValueError(f"Response {response.id!r} references an unknown flow case")
    density = float(flow.fluid.density_kg_m3)
    velocity = tuple(float(component) for component in flow.freestream_velocity_mps)
    speed = sqrt(sum(component * component for component in velocity))
    factor = 0.5 * density * area * speed * speed
    if not all(isfinite(value) and value > 0.0 for value in (density, area, speed, factor)):
        raise ValueError("Coefficient-to-force conversion inputs must be finite and positive")
    return {
        "source_quantity": "porous_directional_force_coefficient",
        "conversion_kind": "dynamic_pressure_area",
        "factor_N_per_coefficient": factor,
        "density_kg_m3": density,
        "reference_area_m2": area,
        "freestream_speed_mps": speed,
        "freestream_velocity_mps": list(velocity),
    }


def _finite_scaled_value(value: float, factor: object, context: str) -> float:
    if not isinstance(factor, (int, float)) or isinstance(factor, bool) or not isfinite(float(factor)):
        raise ValueError(f"Coefficient-to-force factor is invalid for {context}")
    result = float(value) * float(factor)
    if not isfinite(result):
        raise ValueError(f"Coefficient-to-force result is non-finite for {context}")
    return result


def _validate_native_binding_header(
    binding: Mapping[str, Any], spec: ProblemSpec, bundle_dir: Path
) -> None:
    if (
        binding.get("schema_version") != NATIVE_OPENFOAM_V2_ARTIFACT_SCHEMA_VERSION
        or binding.get("kind") != "native_openfoam_v2_artifact_binding"
    ):
        raise ValueError("Native artifact binding has an unsupported schema")
    _validate_problem_binding(binding, spec, "native artifact binding")
    bundle_path = _required_file(bundle_dir / "openfoam_case_bundle.json")
    if binding.get("bundle_metadata_sha256") != _sha256_file(bundle_path):
        raise ValueError("Native artifact binding does not bind the current case bundle")
    for filename in ("convergence_evidence.json", "convergence_qualification.json"):
        expected = binding.get(f"{filename.removesuffix('.json')}_sha256")
        if not _is_sha256(expected) or expected != _sha256_file(_required_file(bundle_dir / filename)):
            raise ValueError(f"Native artifact binding does not bind current {filename}")


def _binding_response_values(
    binding: Mapping[str, Any], spec: ProblemSpec
) -> Mapping[tuple[str, str], Mapping[str, object]]:
    raw = binding.get("response_value_bindings")
    if not isinstance(raw, list):
        raise ValueError("Native artifact binding has no response_value_bindings")
    expected = {(response.flow_case_id, response.id): response for response in spec.responses}
    values: dict[tuple[str, str], Mapping[str, object]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Native response value binding must be an object")
        key = (item.get("flow_case_id"), item.get("response_id"))
        if key not in expected or key in values:
            raise ValueError("Native response value binding keys are invalid or duplicate")
        units = _required_text(item, "units", "native response value binding")
        if units != _response_units(expected[key].kind):
            raise ValueError("Native response value units are not bound to the declared response kind")
        _force_conversion(spec, expected[key], item)
        _required_text(item, "source", "native response value binding")
        values[key] = item
    if set(values) != set(expected):
        raise ValueError("Native response value bindings do not cover all declared responses")
    return values


def _binding_gradients(
    binding: Mapping[str, Any], spec: ProblemSpec
) -> Mapping[tuple[str, str], Mapping[str, object]]:
    raw = binding.get("gradient_bindings")
    if not isinstance(raw, list):
        raise ValueError("Native artifact binding has no gradient_bindings")
    expected = {(response.flow_case_id, response.id) for response in spec.responses}
    values: dict[tuple[str, str], Mapping[str, object]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Native gradient binding must be an object")
        key = (item.get("flow_case_id"), item.get("response_id"))
        if key not in expected or key in values:
            raise ValueError("Native gradient binding keys are invalid or duplicate")
        if item.get("design_variable_id") != "rho":
            raise ValueError("Native gradient binding design variable must be rho")
        if item.get("gradient_convention") != "d_response_d_rho_cell_integrated":
            raise ValueError("Native gradient binding does not define the rho derivative convention")
        if item.get("source_design_variable") != "alpha":
            raise ValueError("Native gradient binding source design variable must be alpha")
        if item.get("filtered_field") != "alphaTilda":
            raise ValueError("Native gradient binding filtered field must be alphaTilda")
        if item.get("projected_field") != "beta":
            raise ValueError("Native gradient binding projected field must be beta")
        if item.get("gradient_field_kind") != "topOSens":
            raise ValueError("Native gradient binding must use the final topOSens field")
        if item.get("filter_projection_chain_rule") != "alpha_to_alphaTilda_to_beta_complete":
            raise ValueError(
                "Native gradient binding must declare the complete alpha-to-alphaTilda-to-beta chain rule"
            )
        _required_text(item, "units", "native gradient binding")
        _required_text(item, "source", "native gradient binding")
        _required_text(item, "openfoam_dimensions", "native gradient binding")
        values[key] = item
    if set(values) != expected:
        raise ValueError("Native gradient bindings do not cover all declared responses")
    return values


def _validate_bound_sensitivity_sources(
    binding: Mapping[str, Any], spec: ProblemSpec, bundle_dir: Path
) -> None:
    """Ensure a binding refers to real final topO fields, not raw sensitivities."""

    bundle = _read_json_mapping(_required_file(bundle_dir / "openfoam_case_bundle.json"))
    flow_entries = _bundle_flow_entries(bundle, spec)
    _binding_gradients(binding, spec)
    for response in spec.responses:
        case_dir = _contained_case_dir(bundle_dir, flow_entries[response.flow_case_id]["case_dir"])
        metadata = _read_json_mapping(_required_file(case_dir / "generated_openfoam_responses.json"))
        mapping = _response_mapping(metadata, response.flow_case_id, response.id)
        _validate_topo_sensitivity_case_source(
            case_dir,
            adjoint_solver_id=_required_text(mapping, "adjoint_solver_id", "response mapping"),
        )


def _validate_topo_sensitivity_case_source(case_dir: Path, *, adjoint_solver_id: str) -> None:
    """Validate the OpenFOAM topO chain and final-field object identity."""

    optimisation_dict = _required_file(case_dir / "system" / "optimisationDict")
    text = optimisation_dict.read_text(encoding="utf-8", errors="strict")
    required_entries = {
        "designVariables type": r"\btype\s+topO\s*;",
        "designVariables sensitivityType": r"\bsensitivityType\s+topO\s*;",
        "designVariables writeFieldSens": r"\bwriteFieldSens\s+true\s*;",
    }
    for description, pattern in required_entries.items():
        if re.search(pattern, text) is None:
            raise ValueError(f"OpenFOAM optimisationDict is missing {description}")

    if not (case_dir / "0" / "alpha").is_file():
        raise ValueError("OpenFOAM topO source alpha field is missing")
    field_object = f"topOSens{adjoint_solver_id}"
    for _, processor_dir in _processor_dirs(case_dir):
        for field_name in ("alphaTilda", "beta", field_object):
            field_path = _required_file(processor_dir / "1" / f"{field_name}.gz")
            _read_openfoam_scalar_field(field_path, expected_object=field_name)


def _binding_mesh(binding: Mapping[str, Any], spec: ProblemSpec) -> Mapping[str, object]:
    mesh = _required_mapping(binding, "mesh_binding", "native artifact binding")
    if mesh.get("grid_kind") != spec.grid.kind:
        raise ValueError("Native artifact mesh binding grid kind does not match the problem")
    if mesh.get("voxel_size_m") != spec.grid.voxel_size_m:
        raise ValueError("Native artifact mesh binding voxel size does not match the problem")
    if mesh.get("ordering") != "undecomposed_openfoam_cell_label_ascending":
        raise ValueError("Native artifact mesh binding ordering is not supported")
    cell_count = mesh.get("cell_count")
    if not isinstance(cell_count, int) or isinstance(cell_count, bool) or cell_count <= 0:
        raise ValueError("Native artifact mesh binding needs a positive cell_count")
    return mesh


def _binding_topology_values(binding: Mapping[str, Any], spec: ProblemSpec) -> list[dict[str, object]]:
    expected = set(topology_constraint_ids(spec))
    if not expected:
        return []
    raw = binding.get("topology_constraint_values")
    if not isinstance(raw, list):
        raise ValueError("Native artifact binding has no topology_constraint_values")
    values: list[dict[str, object]] = []
    found: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Native topology constraint value must be an object")
        constraint_id = item.get("constraint_id")
        value = item.get("value")
        if not isinstance(constraint_id, str) or constraint_id not in expected or constraint_id in found:
            raise ValueError("Native topology constraint value IDs are invalid or duplicate")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(float(value)):
            raise ValueError("Native topology constraint values must be finite")
        values.append(
            {
                "scope": "topology",
                "constraint_id": constraint_id,
                "value": float(value),
                "units": _required_text(item, "units", "native topology constraint value"),
                "status": _required_text(item, "status", "native topology constraint value"),
                "source": _required_text(item, "source", "native topology constraint value"),
            }
        )
        found.add(constraint_id)
    if found != expected:
        raise ValueError("Native topology constraint values do not cover the problem topology policy")
    return values


def _common_units(values: list[dict[str, object]], context: str) -> str:
    units = {str(item["units"]) for item in values}
    if len(units) != 1:
        raise ValueError(f"Cannot aggregate response values with different units for {context}")
    return next(iter(units))


def _problem_binding_dict(spec: ProblemSpec) -> dict[str, object]:
    return {
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
    }


def _validate_problem_binding(data: Mapping[str, Any], spec: ProblemSpec, context: str) -> None:
    binding = _problem_binding_dict(spec)
    for key, value in binding.items():
        if data.get(key) != value:
            raise ValueError(f"{context} {key} does not match the project specification")


def _resolve_provenance_source(bundle_dir: Path, relative_path: str) -> Path:
    if relative_path.startswith("bundle/"):
        return _contained_case_file(bundle_dir, relative_path[len("bundle/") :])
    parts = relative_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid native artifact source path: {relative_path!r}")
    # Provenance keys intentionally use a semantic flow ID.  Resolve it through
    # the bundle rather than assuming that the case-directory name is identical.
    bundle = _read_json_mapping(_required_file(bundle_dir / "openfoam_case_bundle.json"))
    flow_entries = _required_mapping(bundle, "flow_cases", "OpenFOAM bundle")
    entry = flow_entries.get(parts[0])
    if not isinstance(entry, Mapping):
        raise ValueError(f"Native artifact source names an unknown flow case: {parts[0]!r}")
    return _contained_case_file(_contained_case_dir(bundle_dir, entry.get("case_dir")), parts[1])


def _contained_case_dir(root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("OpenFOAM case directory path must be a non-empty string")
    candidate = (root / relative_path).resolve()
    if candidate.parent != root.resolve() or not candidate.is_dir():
        raise ValueError(f"OpenFOAM case directory escapes the case bundle: {relative_path!r}")
    return candidate


def _contained_case_file(root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("OpenFOAM source path must be a non-empty string")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"OpenFOAM source path escapes its case directory: {relative_path!r}") from exc
    return _required_file(candidate)


def _required_file(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f"Required OpenFOAM artifact file does not exist: {path}")
    return path


def _read_json_mapping(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON artifact: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def _required_mapping(data: Mapping[str, Any], key: str, context: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}.{key} must be an object")
    return value


def _required_text(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be non-empty text")
    return value


def _nested_required_text(data: Mapping[str, Any], parent: str, key: str) -> str:
    return _required_text(_required_mapping(data, parent, "OpenFOAM compilation"), key, parent)


def _require_sha256_match(payload: bytes, expected: object, context: str) -> None:
    if not _is_sha256(expected):
        raise ValueError(f"{context} has an invalid SHA-256 digest")
    if _sha256_bytes(payload) != expected:
        raise ValueError(f"SHA-256 mismatch for {context}")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_gzip_text(path: Path) -> str:
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="strict") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Cannot read gzip OpenFOAM artifact: {path}") from exc


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    path.write_bytes(buffer.getvalue())
