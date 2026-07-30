"""Compile a ProblemSpec into a safe, deterministic per-flow OpenFOAM bundle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re
import shutil
import tempfile
from types import MappingProxyType
from typing import Any

from .openfoam_case_renderer import (
    openfoam_retained_field_boundary_specs,
    render_openfoam_physics_files,
)
from .openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from .openfoam_response_renderer import render_openfoam_force_response_files
from .localized_g2_serial_runtime_contract import (
    LOCALIZED_G2_RESPONSE_GRADIENT_CONTRACT_FILENAME,
    LOCALIZED_G2_SERIAL_RUNTIME_FILENAME,
    emit_localized_g2_serial_runtime_contract,
)
from .problem_spec import ProblemSpec
from .solver_case_manifest import (
    SolverCaseManifest,
    build_openfoam_solver_case_manifest,
    write_openfoam_solver_case_manifest,
)


_MANIFEST_NAME = "openfoam_solver_case_manifest.json"
_BUNDLE_METADATA_NAME = "openfoam_case_bundle.json"
DEFAULT_FIXED_GRID_PATCH_IDS = (
    "inlet",
    "outlet",
    "spanMin",
    "spanMax",
    "lower",
    "upper",
)
_EXECUTION_SCRIPTS = ("Allrun", "Allclean")
_CONTROL_DICT_LIBS = re.compile(
    r"(?ms)^[ \t]*libs[ \t]*(?P<body>\([^;]*\))[ \t]*;"
)
_LIBRARY_TOKEN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"|([^\s()]+)')
_CUSTOM_LIBRARY_PREFIX = "libcfdSdf"
_REQUIRED_OBJECTIVE_LIBRARY = "libcfdSdfPorousObjectives.so"
_KNOWN_REPOSITORY_LIBRARIES = {
    _REQUIRED_OBJECTIVE_LIBRARY: (
        "openfoam_extensions/porousDirectionalForce/lib/"
        "libcfdSdfPorousObjectives.so"
    ),
}
_REQUIRED_RETAINED_INITIAL_FIELDS = ("alpha", "Ua", "pa")


@dataclass(frozen=True)
class OpenFOAMCaseBundleArtifacts:
    output_dir: Path
    manifest_json: Path
    bundle_metadata_json: Path
    case_dirs: Mapping[str, Path]
    manifest: SolverCaseManifest


@dataclass(frozen=True)
class _FoamToken:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class _FoamFieldBoundaryEntry:
    name: str
    body_open: _FoamToken
    body_close: _FoamToken
    type_token: _FoamToken
    type_value: _FoamToken
    value_component_spans: tuple[tuple[int, int], ...] | None


@dataclass(frozen=True)
class _FoamFieldBoundary:
    entries: Mapping[str, _FoamFieldBoundaryEntry]


def compile_openfoam_solver_case_bundle(
    spec: ProblemSpec,
    *,
    template_case_dir: str | Path,
    output_dir: str | Path,
    available_patch_ids: Sequence[str] | None,
    adjoint_iterations: int = 1,
    overwrite: bool = False,
    require_compile_ready: bool = True,
    localized_g2_serial_runtime_contract: bool = False,
) -> OpenFOAMCaseBundleArtifacts:
    """Compile a per-flow bundle without copying runtime result directories."""

    if (
        isinstance(adjoint_iterations, bool)
        or not isinstance(adjoint_iterations, int)
        or adjoint_iterations <= 0
    ):
        raise ValueError("adjoint_iterations must be a positive integer")
    if not isinstance(localized_g2_serial_runtime_contract, bool):
        raise ValueError("localized_g2_serial_runtime_contract must be a boolean")
    template = Path(template_case_dir).resolve()
    output = Path(output_dir).resolve()
    if template == output or _is_relative_to(template, output):
        raise ValueError("template_case_dir must not equal or be inside output_dir")

    manifest = build_openfoam_solver_case_manifest(
        spec, available_patch_ids=available_patch_ids
    )
    _prepare_output_directory(output, overwrite=overwrite)
    manifest_path = write_openfoam_solver_case_manifest(
        manifest, output / _MANIFEST_NAME
    )
    manifest_sha = _file_sha256(manifest_path)
    bundle_path = output / _BUNDLE_METADATA_NAME

    if not manifest.compile_ready:
        flow_metadata = {
            plan.flow_case_id: {
                "case_dir": plan.case_directory_name,
                "status": "unsupported",
                "unsupported": list(plan.unsupported),
            }
            for plan in manifest.flow_cases
        }
        bundle = _bundle_metadata(
            spec=spec,
            template=template,
            manifest_sha=manifest_sha,
            compile_ready=False,
            status="unsupported",
            unsupported=_all_unsupported(manifest),
            flow_cases=flow_metadata,
            template_files={},
        )
        _write_json(bundle_path, bundle)
        artifacts = OpenFOAMCaseBundleArtifacts(
            output_dir=output,
            manifest_json=manifest_path,
            bundle_metadata_json=bundle_path,
            case_dirs=MappingProxyType({}),
            manifest=manifest,
        )
        if require_compile_ready:
            raise ValueError(
                "OpenFOAM solver case manifest is not compile-ready: "
                + ", ".join(_all_unsupported(manifest))
            )
        return artifacts

    _validate_template(template)
    execution_contract, execution_unsupported = _audit_execution_contract(template)
    fv_solution_initialization_contract, fv_solution_unsupported = (
        _audit_fv_solution_initialization_contract(template)
    )
    mesh_boundary_contract, mesh_unsupported = _audit_mesh_boundary_contract(
        template, manifest
    )
    field_boundary_contract, field_unsupported = _audit_field_boundary_contract(
        template, manifest, mesh_boundary_contract
    )
    execution_unsupported = (
        *execution_unsupported,
        *fv_solution_unsupported,
        *mesh_unsupported,
        *field_unsupported,
    )
    if execution_unsupported:
        manifest = replace(
            manifest,
            compile_ready=False,
            unsupported=(*manifest.unsupported, *execution_unsupported),
        )
        manifest_path = write_openfoam_solver_case_manifest(
            manifest, output / _MANIFEST_NAME
        )
        manifest_sha = _file_sha256(manifest_path)
        flow_metadata = {
            plan.flow_case_id: {
                "case_dir": plan.case_directory_name,
                "status": "unsupported",
                "unsupported": list(execution_unsupported),
            }
            for plan in manifest.flow_cases
        }
        bundle = _bundle_metadata(
            spec=spec,
            template=template,
            manifest_sha=manifest_sha,
            compile_ready=False,
            status="unsupported",
            unsupported=_all_unsupported(manifest),
            flow_cases=flow_metadata,
            template_files=_template_provenance(template),
        )
        bundle["execution_contract"] = execution_contract
        bundle["fv_solution_initialization_contract"] = (
            fv_solution_initialization_contract
        )
        bundle["mesh_boundary_contract"] = mesh_boundary_contract
        bundle["field_boundary_contract"] = field_boundary_contract
        _write_json(bundle_path, bundle)
        artifacts = OpenFOAMCaseBundleArtifacts(
            output_dir=output,
            manifest_json=manifest_path,
            bundle_metadata_json=bundle_path,
            case_dirs=MappingProxyType({}),
            manifest=manifest,
        )
        if require_compile_ready:
            raise ValueError(
                "OpenFOAM solver case manifest is not compile-ready: "
                + ", ".join(_all_unsupported(manifest))
            )
        return artifacts

    template_files = _template_provenance(template)
    case_dirs: dict[str, Path] = {}
    flow_metadata: dict[str, Any] = {}
    committed_case_dirs: list[Path] = []
    try:
        for plan in manifest.flow_cases:
            case_dir = _contained_case_dir(output, plan.case_directory_name)
            if case_dir.exists():
                raise FileExistsError(f"Refusing to replace unowned case path: {case_dir}")
            case_staging = Path(
                tempfile.mkdtemp(prefix=f".case_{plan.flow_case_id}_", dir=output)
            )
            try:
                for relative in ("0.orig", "constant", "system"):
                    shutil.copytree(template / relative, case_staging / relative)
                for script in _EXECUTION_SCRIPTS:
                    shutil.copy2(template / script, case_staging / script)
                case_execution_contract = _stage_execution_contract(
                    execution_contract, case_staging
                )
                case_mesh_domain_contract = _stage_mesh_domain_bounds_contract(
                    spec, case_staging
                )
                case_mesh_boundary_contract = _stage_mesh_boundary_contract(
                    plan, case_staging
                )
                case_field_boundary_contract = _stage_retained_field_boundary_contract(
                    plan, case_staging
                )

                physics_staging = Path(
                    tempfile.mkdtemp(
                        prefix=f".physics_{plan.flow_case_id}_", dir=output
                    )
                )
                try:
                    physics = render_openfoam_physics_files(
                        plan,
                        physics_staging,
                        fv_solution_initialization_solver_fields=tuple(
                            fv_solution_initialization_contract[
                                "required_solver_fields"
                            ]
                        ),
                    )
                    physics_owned = (
                        physics.transport_properties,
                        physics.turbulence_properties,
                        physics.adjoint_turbulence_properties,
                        physics.fv_schemes,
                        physics.fv_solution,
                        physics.normalized_mass_imbalance_function_dict,
                        physics.velocity_field,
                        physics.pressure_field,
                        physics.metadata_json,
                        physics.turbulent_kinetic_energy_field,
                        physics.specific_dissipation_rate_field,
                        physics.turbulent_viscosity_field,
                        physics.adjoint_turbulent_kinetic_energy_field,
                        physics.adjoint_specific_dissipation_rate_field,
                    )
                    for source in physics_owned:
                        if source is None:
                            continue
                        relative = source.relative_to(physics_staging)
                        destination = case_staging / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
                finally:
                    if physics_staging.exists():
                        shutil.rmtree(physics_staging)

                case_field_boundary_contract = _validate_staged_field_boundary_contract(
                    case_staging, case_field_boundary_contract
                )

                responses = render_openfoam_force_response_files(
                    plan,
                    case_staging,
                    adjoint_iterations=adjoint_iterations,
                )
                physics_marker = case_staging / "generated_openfoam_physics.json"
                response_marker = case_staging / "generated_openfoam_responses.json"
                compilation_path = case_staging / "openfoam_case_compilation.json"
                compilation = {
                    "schema_version": 1,
                    "kind": "openfoam_case_compilation",
                    "problem_id": spec.problem_id,
                    "problem_spec_sha256": manifest.problem_spec_sha256,
                    "flow_case_id": plan.flow_case_id,
                    "case_dir": plan.case_directory_name,
                    "paths": {
                        "physics_metadata": physics_marker.name,
                        "response_metadata": response_marker.name,
                    },
                    "template_provenance": {
                        "template_case_dir": str(template),
                        "files_sha256": template_files,
                    },
                    "physics": {
                        "metadata_sha256": _file_sha256(physics_marker),
                        "files_sha256": dict(physics.file_sha256),
                        "fv_solution_initialization_solver_fields": list(
                            physics.fv_solution_initialization_solver_fields
                        ),
                    },
                    "responses": {
                        "metadata_sha256": _file_sha256(response_marker),
                        "files_sha256": dict(responses.file_sha256),
                    },
                    "execution_contract": case_execution_contract,
                    "mesh_domain_contract": case_mesh_domain_contract,
                    "mesh_boundary_contract": case_mesh_boundary_contract,
                    "field_boundary_contract": case_field_boundary_contract,
                    "status": "compiled",
                    "execution_qualification": "not_run",
                }
                _write_json(compilation_path, compilation)
                compilation_sha = _file_sha256(compilation_path)
                if localized_g2_serial_runtime_contract:
                    generated_responses = tuple(
                        _mapping(plan.generated, "generated responses").get("responses", ())
                    )
                    if len(generated_responses) != 1 or not isinstance(generated_responses[0], Mapping):
                        raise ValueError(
                            "localized G2 serial runtime requires exactly one supported force response per flow case"
                        )
                    requested_fluid = _mapping(plan.requested, "flow requested").get("fluid")
                    if not isinstance(requested_fluid, Mapping):
                        raise ValueError("localized G2 serial runtime flow fluid metadata is invalid")
                    density = requested_fluid.get("density_kg_m3")
                    staged_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(
                        case_staging / "system" / "blockMeshDict"
                    )
                    runtime = emit_localized_g2_serial_runtime_contract(
                        case_dir=case_staging,
                        flow_case_id=plan.flow_case_id,
                        response=generated_responses[0],
                        density_kg_m3=float(density),
                        compilation_metadata_sha256=compilation_sha,
                        mesh=staged_mesh,
                    )
                case_staging.replace(case_dir)
                committed_case_dirs.append(case_dir)
                case_dirs[plan.flow_case_id] = case_dir
                flow_metadata[plan.flow_case_id] = {
                    "case_dir": plan.case_directory_name,
                    "compilation_metadata": (
                        f"{plan.case_directory_name}/{compilation_path.name}"
                    ),
                    "compilation_sha256": compilation_sha,
                    "status": "compiled",
                }
                if localized_g2_serial_runtime_contract:
                    flow_metadata[plan.flow_case_id]["localized_g2_serial_runtime"] = {
                        "path": f"{plan.case_directory_name}/{LOCALIZED_G2_SERIAL_RUNTIME_FILENAME}",
                        "sha256": _file_sha256(case_dir / LOCALIZED_G2_SERIAL_RUNTIME_FILENAME),
                        "response_gradient_contract": (
                            f"{plan.case_directory_name}/{LOCALIZED_G2_RESPONSE_GRADIENT_CONTRACT_FILENAME}"
                        ),
                        "response_gradient_contract_sha256": _file_sha256(
                            case_dir / LOCALIZED_G2_RESPONSE_GRADIENT_CONTRACT_FILENAME
                        ),
                        "status": runtime["status"],
                    }
            finally:
                if case_staging.exists():
                    shutil.rmtree(case_staging)
    except Exception as exc:
        for committed in committed_case_dirs:
            if committed.exists():
                shutil.rmtree(committed)
        rolled_back = {
            flow_case_id: {**metadata, "status": "rolled_back", "rolled_back": True}
            for flow_case_id, metadata in flow_metadata.items()
        }
        failed_bundle = _bundle_metadata(
            spec=spec,
            template=template,
            manifest_sha=manifest_sha,
            compile_ready=True,
            status="failed",
            unsupported=(),
            flow_cases=rolled_back,
            template_files=template_files,
        )
        failed_bundle["error_type"] = type(exc).__name__
        failed_bundle["error_message"] = str(exc)
        failed_bundle["execution_contract"] = execution_contract
        failed_bundle["fv_solution_initialization_contract"] = (
            fv_solution_initialization_contract
        )
        failed_bundle["mesh_boundary_contract"] = mesh_boundary_contract
        failed_bundle["field_boundary_contract"] = field_boundary_contract
        _write_json(bundle_path, failed_bundle)
        raise

    bundle = _bundle_metadata(
        spec=spec,
        template=template,
        manifest_sha=manifest_sha,
        compile_ready=True,
        status="compiled",
        unsupported=(),
        flow_cases=flow_metadata,
        template_files=template_files,
    )
    bundle["execution_contract"] = execution_contract
    bundle["fv_solution_initialization_contract"] = (
        fv_solution_initialization_contract
    )
    bundle["mesh_boundary_contract"] = mesh_boundary_contract
    bundle["field_boundary_contract"] = field_boundary_contract
    _write_json(bundle_path, bundle)
    return OpenFOAMCaseBundleArtifacts(
        output_dir=output,
        manifest_json=manifest_path,
        bundle_metadata_json=bundle_path,
        case_dirs=MappingProxyType(dict(case_dirs)),
        manifest=manifest,
    )


def _prepare_output_directory(output: Path, *, overwrite: bool) -> None:
    marker = output / _BUNDLE_METADATA_NAME
    if not output.exists():
        output.mkdir(parents=True)
        return
    entries = list(output.iterdir())
    if not entries:
        return
    if not marker.is_file():
        raise FileExistsError(
            f"Refusing non-empty output without {_BUNDLE_METADATA_NAME}: {output}"
        )
    if not overwrite:
        raise FileExistsError(f"Compiled bundle exists; use overwrite=True: {output}")
    try:
        old = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Existing bundle metadata is unreadable") from exc
    if old.get("kind") != "openfoam_case_bundle":
        raise ValueError("Existing output marker has the wrong kind")
    flow_cases = old.get("flow_cases", {})
    if not isinstance(flow_cases, Mapping):
        raise ValueError("Existing bundle flow_cases must be a mapping")
    for value in flow_cases.values():
        if not isinstance(value, Mapping) or not isinstance(value.get("case_dir"), str):
            raise ValueError("Existing bundle has an invalid case_dir entry")
        case_dir = _contained_case_dir(output, str(value["case_dir"]))
        if case_dir.exists():
            if not case_dir.is_dir():
                raise ValueError(f"Owned case path is not a directory: {case_dir}")
            shutil.rmtree(case_dir)


def _validate_template(template: Path) -> None:
    required = (
        template / "0.orig",
        template / "constant",
        template / "system",
        template / "system/optimisationDict",
        template / "system/fvOptions",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"OpenFOAM template is missing required paths: {missing!r}")
    if not all(path.is_dir() for path in required[:3]):
        raise ValueError("OpenFOAM template 0.orig, constant, and system must be directories")
    if not all(path.is_file() for path in required[3:]):
        raise ValueError("OpenFOAM template optimisationDict and fvOptions must be files")


def _template_provenance(template: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for directory in ("0.orig", "constant", "system"):
        for path in sorted((template / directory).rglob("*")):
            if path.is_file():
                files[path.relative_to(template).as_posix()] = _file_sha256(path)
    for script in _EXECUTION_SCRIPTS:
        path = template / script
        if path.is_file():
            files[script] = _file_sha256(path)
    library_dir = template / "lib"
    if library_dir.is_dir():
        for path in sorted(library_dir.rglob("*")):
            if path.is_file():
                files[path.relative_to(template).as_posix()] = _file_sha256(path)
    return files


def _audit_execution_contract(template: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    unsupported: list[str] = []
    scripts: list[dict[str, Any]] = []
    for name in _EXECUTION_SCRIPTS:
        source = template / name
        resolved = source.is_file()
        if not resolved:
            unsupported.append(f"missing_execution_script:{name}")
        source_sha = _file_sha256(source) if resolved else None
        fail_fast = None
        if name == "Allrun" and resolved:
            try:
                source_text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                unsupported.append("allrun_not_utf8")
                fail_fast = False
            else:
                has_shebang = source_text.startswith("#!")
                fail_fast = has_shebang and _allrun_has_immediate_set_e(
                    source_text
                )
                if not has_shebang:
                    unsupported.append("allrun_missing_shebang")
        scripts.append(
            {
                "required": name,
                "resolved_source": str(source) if resolved else None,
                "staged_path": name if resolved else None,
                "sha256": source_sha,
                "pre_patch_sha256": source_sha,
                "post_patch_sha256": None,
                "fail_fast": fail_fast,
                "qualification": "resolved_for_staging" if resolved else "missing",
            }
        )

    control_dict = template / "system/controlDict"
    libraries: list[dict[str, Any]] = []
    if not control_dict.is_file():
        unsupported.append("missing_execution_control_dict:system/controlDict")
    else:
        try:
            tokens, _ = _parse_control_dict_libraries(
                control_dict.read_text(encoding="utf-8")
            )
        except ValueError:
            unsupported.append("malformed_control_dict_libs")
        else:
            required_library_names = {Path(token).name for token in tokens}
            if _REQUIRED_OBJECTIVE_LIBRARY not in required_library_names:
                unsupported.append(
                    "missing_required_control_dict_library:"
                    + _REQUIRED_OBJECTIVE_LIBRARY
                )
            for token in tokens:
                library, reason = _resolve_required_library(template, token)
                libraries.append(library)
                if reason is not None:
                    unsupported.append(reason)

    contract = {
        "control_dict": "system/controlDict",
        "scripts": scripts,
        "libraries": libraries,
        "qualification": "unsupported" if unsupported else "resolved_for_staging",
        "runtime_execution": "not_run",
    }
    return contract, tuple(unsupported)


def _audit_fv_solution_initialization_contract(
    template: Path,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Determine v2512 solver entries needed before the optimisation loop.

    ``topO`` design variables only solve the temporary Helmholtz field
    ``bTilda`` during startup when their regularisation is explicitly enabled.
    The template owns that choice, so the compiler inspects its
    ``optimisationDict`` instead of unconditionally adding a solver entry to
    every generated flow case.
    """

    path = template / "system/optimisationDict"
    contract: dict[str, Any] = {
        "path": "system/optimisationDict",
        "openfoam_version": "v2512",
        "design_variables_type": None,
        "regularisation": {
            "enabled": None,
            "source": "not_inspected",
        },
        "required_solver_fields": [],
        "validation": "resolved_for_staging",
    }
    unsupported: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
        tokens = _foam_tokens(text)
        optimisation = _find_unique_direct_dictionary(tokens, None, "optimisation")
        if optimisation is None:
            raise ValueError("missing_optimisation_dictionary")
        design_variables = _find_unique_direct_dictionary(
            tokens, optimisation, "designVariables"
        )
        if design_variables is None:
            raise ValueError("missing_design_variables_dictionary")
        design_type = _find_unique_direct_scalar(tokens, design_variables, "type")
        if design_type is None:
            raise ValueError("missing_design_variables_type")
        contract["design_variables_type"] = design_type
        if design_type != "topO":
            contract["regularisation"] = {
                "enabled": False,
                "source": "not_applicable_to_non_topology_design",
            }
            return contract, ()

        regularisation = _find_unique_direct_dictionary(
            tokens, design_variables, "regularisation"
        )
        if regularisation is None:
            regularise = False
            regularisation_source = "openfoam_v2512_default_false"
        else:
            configured = _find_unique_direct_scalar(
                tokens, regularisation, "regularise"
            )
            if configured is None:
                regularise = False
                regularisation_source = "openfoam_v2512_default_false"
            elif configured == "true":
                regularise = True
                regularisation_source = "template"
            elif configured == "false":
                regularise = False
                regularisation_source = "template"
            else:
                raise ValueError("unsupported_regularise_switch")
        contract["regularisation"] = {
            "enabled": regularise,
            "source": regularisation_source,
        }
        if regularise:
            # v2512's topO Helmholtz regularisation calls smoothEqn.solve() on
            # the temporary scalar field bTilda before the first primal solve.
            contract["required_solver_fields"] = ["bTilda"]
    except UnicodeDecodeError:
        unsupported.append("optimisation_dict_not_utf8")
    except ValueError as exc:
        unsupported.append(
            "malformed_optimisation_dict_for_fv_solution_initialization:"
            + str(exc)
        )

    if unsupported:
        contract["validation"] = "unsupported"
    return contract, tuple(unsupported)


def _find_unique_direct_dictionary(
    tokens: Sequence[_FoamToken],
    parent: tuple[int, int] | None,
    name: str,
) -> tuple[int, int] | None:
    """Find one direct dictionary child, rejecting ambiguous OpenFOAM input."""

    start = 0 if parent is None else parent[0] + 1
    end = len(tokens) if parent is None else parent[1]
    matches: list[tuple[int, int]] = []
    brace_depth = 0
    paren_depth = 0
    for index in range(start, end):
        token = tokens[index]
        if (
            token.value == name
            and brace_depth == 0
            and paren_depth == 0
            and index + 1 < end
            and tokens[index + 1].value == "{"
        ):
            closing = _matching_token(tokens, index + 1, "{", "}")
            if closing >= end:
                raise ValueError(f"dictionary_escapes_parent:{name}")
            matches.append((index + 1, closing))
        if token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
        if brace_depth < 0 or paren_depth < 0:
            raise ValueError("unbalanced_delimiter")
    if brace_depth != 0 or paren_depth != 0:
        raise ValueError("unbalanced_delimiter")
    if len(matches) > 1:
        raise ValueError(f"ambiguous_dictionary:{name}")
    return matches[0] if matches else None


def _find_unique_direct_scalar(
    tokens: Sequence[_FoamToken],
    parent: tuple[int, int],
    name: str,
) -> str | None:
    """Read one direct ``key value;`` statement from a dictionary body."""

    start = parent[0] + 1
    end = parent[1]
    values: list[str] = []
    brace_depth = 0
    paren_depth = 0
    for index in range(start, end):
        token = tokens[index]
        if token.value == name and brace_depth == 0 and paren_depth == 0:
            if (
                index + 2 >= end
                or tokens[index + 1].value in {"{", "}", "(", ")", ";"}
                or tokens[index + 2].value != ";"
            ):
                raise ValueError(f"invalid_scalar_entry:{name}")
            values.append(tokens[index + 1].value)
        if token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
        if brace_depth < 0 or paren_depth < 0:
            raise ValueError("unbalanced_delimiter")
    if brace_depth != 0 or paren_depth != 0:
        raise ValueError("unbalanced_delimiter")
    if len(values) > 1:
        raise ValueError(f"ambiguous_scalar_entry:{name}")
    return values[0] if values else None


def _audit_mesh_boundary_contract(
    template: Path, manifest: SolverCaseManifest
) -> tuple[dict[str, Any], tuple[str, ...]]:
    path = template / "system/blockMeshDict"
    unsupported: list[str] = []
    template_types: dict[str, str] = {}
    if not path.is_file():
        unsupported.append("missing_block_mesh_dict:system/blockMeshDict")
    else:
        try:
            parsed = _parse_block_mesh_boundary(
                path.read_bytes().decode("utf-8")
            )
        except (UnicodeDecodeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "block_mesh_not_utf8"
            unsupported.append(f"malformed_block_mesh_boundary:{reason}")
        else:
            template_types = {
                patch_id: str(value["type"]) for patch_id, value in parsed.items()
            }

    flow_cases: dict[str, Any] = {}
    for plan in manifest.flow_cases:
        requested = {
            str(key): str(value)
            for key, value in plan.requested["boundary_conditions"].items()
        }
        generated = {
            str(key): str(value["patch_type"])
            for key, value in plan.generated["boundary_conditions"].items()
        }
        missing = sorted(set(generated) - set(template_types))
        for patch_id in missing:
            unsupported.append(
                f"missing_block_mesh_patch:{plan.flow_case_id}:{patch_id}"
            )
        flow_cases[plan.flow_case_id] = {
            "requested_boundary_conditions": requested,
            "generated_patch_types": generated,
            "missing_patches": missing,
            "validation": "pass" if not missing and template_types else "unsupported",
        }
    return (
        {
            "path": "system/blockMeshDict",
            "template_patch_types": template_types,
            "flow_cases": flow_cases,
            "validation": "unsupported" if unsupported else "resolved_for_staging",
        },
        tuple(unsupported),
    )


def _stage_mesh_domain_bounds_contract(
    spec: ProblemSpec, case_staging: Path
) -> dict[str, Any]:
    """Bind a staged uniform ``blockMesh`` extent to the canonical domain.

    Native OpenFOAM cases may deliberately use a coarser source mesh than the
    canonical optimization grid.  Their physical extent must nevertheless be
    identical: otherwise field transfer would silently crop or extrapolate a
    different problem domain.  Keep the template block's cell counts and
    grading untouched; only its eight Cartesian vertex coordinates are bound.
    """

    requested = spec.grid.domain_bounds_m
    if requested is None:
        return {
            "path": "system/blockMeshDict",
            "binding": "not_requested",
        }

    path = case_staging / "system/blockMeshDict"
    original = path.read_bytes()
    try:
        source = read_openfoam_blockmesh_uniform_cartesian_grid(path)
    except ValueError as exc:
        raise ValueError(
            "Cannot bind blockMeshDict to grid.domain_bounds_m: " + str(exc)
        ) from exc

    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Cannot bind blockMeshDict to grid.domain_bounds_m: not UTF-8") from exc
    source_upper = tuple(
        source.lower[axis] + source.spacing[axis] * source.cell_shape[axis]
        for axis in range(3)
    )
    source_lower_raw = tuple(value / source.scale for value in source.lower)
    source_upper_raw = tuple(value / source.scale for value in source_upper)
    target_lower_raw = tuple(value / source.scale for value in requested.lower)
    target_upper_raw = tuple(value / source.scale for value in requested.upper)
    bound = _bind_uniform_block_mesh_vertices(
        text,
        source_lower=source_lower_raw,
        source_upper=source_upper_raw,
        target_lower=target_lower_raw,
        target_upper=target_upper_raw,
    )
    path.write_bytes(bound.encode("utf-8"))

    try:
        rendered = read_openfoam_blockmesh_uniform_cartesian_grid(path)
    except ValueError as exc:
        raise ValueError(
            "Rendered blockMeshDict is invalid after domain binding: " + str(exc)
        ) from exc
    rendered_upper = tuple(
        rendered.lower[axis]
        + rendered.spacing[axis] * rendered.cell_shape[axis]
        for axis in range(3)
    )
    if not _same_vector(rendered.lower, requested.lower) or not _same_vector(
        rendered_upper, requested.upper
    ):
        raise ValueError(
            "Rendered blockMeshDict bounds do not match grid.domain_bounds_m"
        )
    return {
        "path": "system/blockMeshDict",
        "binding": "bound",
        "requested_lower_m": list(requested.lower),
        "requested_upper_m": list(requested.upper),
        "source_lower_m": list(source.lower),
        "source_upper_m": list(source_upper),
        "source_cell_shape": list(source.cell_shape),
        "rendered_lower_m": list(rendered.lower),
        "rendered_upper_m": list(rendered_upper),
        "pre_bind_sha256": hashlib.sha256(original).hexdigest(),
        "post_bind_sha256": _file_sha256(path),
        "validation": "pass",
    }


def _bind_uniform_block_mesh_vertices(
    text: str,
    *,
    source_lower: Sequence[float],
    source_upper: Sequence[float],
    target_lower: Sequence[float],
    target_upper: Sequence[float],
) -> str:
    """Replace only the coordinate tokens of one uniform Cartesian block."""

    vertices = _block_mesh_vertex_coordinate_tokens(text)
    replacements: list[tuple[int, int, str]] = []
    for coordinate_tokens in vertices:
        for axis, token in enumerate(coordinate_tokens):
            try:
                value = float(token.value)
            except ValueError as exc:
                raise ValueError("blockMesh vertex coordinate is not numeric") from exc
            if _same_number(value, source_lower[axis]):
                target = target_lower[axis]
            elif _same_number(value, source_upper[axis]):
                target = target_upper[axis]
            else:
                raise ValueError(
                    "blockMesh vertex is not a corner of its uniform Cartesian extent"
                )
            replacements.append((token.start, token.end, format(float(target), ".12g")))
    return _replace_text_spans(text, replacements)


def _block_mesh_vertex_coordinate_tokens(text: str) -> tuple[tuple[_FoamToken, ...], ...]:
    tokens = _foam_tokens(text)
    candidates = [
        index
        for index, token in enumerate(tokens)
        if token.value == "vertices"
        and index + 1 < len(tokens)
        and tokens[index + 1].value == "("
    ]
    if len(candidates) != 1:
        raise ValueError("blockMeshDict must contain exactly one vertices list")
    opening = candidates[0] + 1
    closing = _matching_token(tokens, opening, "(", ")")
    vertices: list[tuple[_FoamToken, ...]] = []
    cursor = opening + 1
    while cursor < closing:
        if tokens[cursor].value != "(":
            raise ValueError("blockMesh vertices must contain only coordinate triples")
        coordinate_close = _matching_token(tokens, cursor, "(", ")")
        coordinates = tuple(tokens[cursor + 1 : coordinate_close])
        if len(coordinates) != 3 or any(
            token.value in {"(", ")", "{", "}", ";"} for token in coordinates
        ):
            raise ValueError("blockMesh vertex must contain exactly three coordinates")
        vertices.append(coordinates)
        cursor = coordinate_close + 1
    if len(vertices) != 8:
        raise ValueError("blockMesh domain binding requires exactly eight vertices")
    return tuple(vertices)


def _same_number(left: float, right: float) -> bool:
    return isclose(left, right, rel_tol=0.0, abs_tol=1e-12 * max(1.0, abs(left), abs(right)))


def _same_vector(left: Sequence[float], right: Sequence[float]) -> bool:
    return len(left) == len(right) and all(
        _same_number(float(a), float(b)) for a, b in zip(left, right)
    )


def _stage_mesh_boundary_contract(
    plan: Any, case_staging: Path
) -> dict[str, Any]:
    path = case_staging / "system/blockMeshDict"
    original = path.read_bytes()
    text = original.decode("utf-8")
    parsed = _parse_block_mesh_boundary(text)
    requested = {
        str(key): str(value)
        for key, value in plan.requested["boundary_conditions"].items()
    }
    generated = {
        str(key): str(value["patch_type"])
        for key, value in plan.generated["boundary_conditions"].items()
    }
    missing = sorted(set(generated) - set(parsed))
    if missing:
        raise ValueError(f"Missing staged blockMesh patches: {missing!r}")
    replacements = sorted(
        (
            int(parsed[patch_id]["type_span"][0]),
            int(parsed[patch_id]["type_span"][1]),
            patch_type,
        )
        for patch_id, patch_type in generated.items()
    )
    for start, end, patch_type in reversed(replacements):
        text = text[:start] + patch_type + text[end:]
    staged = text.encode("utf-8")
    path.write_bytes(staged)
    staged_parsed = _parse_block_mesh_boundary(text)
    staged_types = {
        patch_id: str(staged_parsed[patch_id]["type"])
        for patch_id in generated
    }
    if staged_types != generated:
        raise ValueError("Staged blockMesh patch type validation failed")
    return {
        "path": "system/blockMeshDict",
        "requested_boundary_conditions": requested,
        "generated_patch_types": generated,
        "template_patch_types_before": {
            patch_id: str(parsed[patch_id]["type"]) for patch_id in generated
        },
        "staged_patch_types_after": staged_types,
        "pre_patch_sha256": hashlib.sha256(original).hexdigest(),
        "post_patch_sha256": hashlib.sha256(staged).hexdigest(),
        "validation": "pass",
    }


def _audit_field_boundary_contract(
    template: Path,
    manifest: SolverCaseManifest,
    mesh_boundary_contract: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Validate retained initial fields against each flow's final mesh types."""

    initial_dir = template / "0.orig"
    fields, scan_unsupported = _scan_initial_field_boundaries(initial_dir)
    unsupported = list(scan_unsupported)
    unsupported.extend(_audit_required_root_initial_fields(initial_dir))

    raw_template_types = mesh_boundary_contract.get("template_patch_types", {})
    template_types = (
        {str(key): str(value) for key, value in raw_template_types.items()}
        if isinstance(raw_template_types, Mapping)
        else {}
    )
    flow_cases: dict[str, Any] = {}
    for plan in manifest.flow_cases:
        final_mesh_types = _final_mesh_patch_types(template_types, plan)
        try:
            policy = openfoam_retained_field_boundary_specs(plan)
        except ValueError as exc:
            reason = f"invalid_retained_field_boundary_policy:{plan.flow_case_id}:{exc}"
            unsupported.append(reason)
            flow_cases[plan.flow_case_id] = {
                "validation": "unsupported",
                "reason": reason,
            }
            continue

        renderer_owned = _renderer_owned_initial_fields(plan)
        retained = {
            field_name: boundary
            for field_name, boundary in fields.items()
            if field_name not in renderer_owned
        }
        flow_reasons: list[str] = []
        field_records: dict[str, Any] = {}
        for field_name, boundary in retained.items():
            overrides = policy.get(field_name, {})
            reasons = _field_boundary_compatibility_reasons(
                flow_case_id=plan.flow_case_id,
                field_name=field_name,
                boundary=boundary,
                mesh_patch_types=final_mesh_types,
                type_overrides=overrides,
            )
            flow_reasons.extend(reasons)
            field_records[field_name] = {
                "template_path": f"0.orig/{field_name}",
                "template_patch_types": {
                    patch_id: entry.type_value.value
                    for patch_id, entry in sorted(boundary.entries.items())
                },
                "manifest_patched_types": {
                    patch_id: str(spec["type"])
                    for patch_id, spec in sorted(overrides.items())
                },
                "validation": "pass" if not reasons else "unsupported",
            }
        unsupported.extend(flow_reasons)
        flow_cases[plan.flow_case_id] = {
            "final_mesh_patch_types": final_mesh_types,
            "renderer_owned_fields": sorted(renderer_owned),
            "retained_fields": field_records,
            "validation": "pass" if not flow_reasons else "unsupported",
        }

    return (
        {
            "path": "0.orig",
            "required_retained_fields": list(_REQUIRED_RETAINED_INITIAL_FIELDS),
            "template_fields": sorted(fields),
            "flow_cases": flow_cases,
            "validation": "unsupported" if unsupported else "resolved_for_staging",
        },
        tuple(dict.fromkeys(unsupported)),
    )


def _final_mesh_patch_types(
    template_types: Mapping[str, str], plan: Any
) -> dict[str, str]:
    result = dict(template_types)
    generated = _mapping(plan.generated, "plan.generated")
    boundaries = _mapping(
        generated.get("boundary_conditions"), "plan.generated.boundary_conditions"
    )
    for raw_patch_id, raw_spec in boundaries.items():
        patch_id = str(raw_patch_id)
        if patch_id not in result:
            continue
        spec = _mapping(raw_spec, f"boundary_conditions.{patch_id}")
        patch_type = spec.get("patch_type")
        if not isinstance(patch_type, str) or not patch_type:
            raise ValueError(f"Missing generated patch type for {patch_id}")
        result[patch_id] = patch_type
    return result


def _renderer_owned_initial_fields(plan: Any) -> set[str]:
    generated = _mapping(plan.generated, "plan.generated")
    turbulence = _mapping(generated.get("turbulence"), "plan.generated.turbulence")
    owned = {"U", "p"}
    if turbulence.get("model") == "k_omega_sst":
        owned.update({"k", "omega", "nut", "ka", "wa"})
    return owned


def _audit_required_root_initial_fields(initial_dir: Path) -> tuple[str, ...]:
    """Require compiler-patched fields to be valid, unique root-level files."""

    unsupported: list[str] = []
    for field_name in _REQUIRED_RETAINED_INITIAL_FIELDS:
        root_path = initial_dir / field_name
        if not root_path.is_file():
            unsupported.append(f"required_initial_field_not_root_level:{field_name}")
            continue
        nested_matches = sorted(
            path
            for path in initial_dir.rglob(field_name)
            if path != root_path and path.is_file()
        )
        for nested in nested_matches:
            relative = nested.relative_to(initial_dir).as_posix()
            unsupported.append(
                f"duplicate_required_initial_field_path:{field_name}:{relative}"
            )
        raw = root_path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            unsupported.append(f"non_utf8_required_initial_field:{field_name}")
            continue
        try:
            boundary = _parse_openfoam_field_boundary(text)
        except ValueError as exc:
            unsupported.append(
                f"malformed_required_initial_field_boundary:{field_name}:{exc}"
            )
            continue
        if boundary is None:
            unsupported.append(f"missing_required_initial_field_boundary:{field_name}")
    return tuple(unsupported)


def _scan_initial_field_boundaries(
    initial_dir: Path,
) -> tuple[dict[str, _FoamFieldBoundary], tuple[str, ...]]:
    fields: dict[str, _FoamFieldBoundary] = {}
    unsupported: list[str] = []
    if not initial_dir.is_dir():
        return fields, ("missing_initial_field_directory:0.orig",)
    for path in sorted(initial_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(initial_dir).as_posix()
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            if b"boundaryField" in raw:
                unsupported.append(f"non_utf8_initial_field:{relative}")
            continue
        try:
            boundary = _parse_openfoam_field_boundary(text)
        except ValueError as exc:
            unsupported.append(f"malformed_initial_field_boundary:{relative}:{exc}")
            continue
        if boundary is None:
            continue
        field_name = path.name
        if field_name in fields:
            unsupported.append(f"duplicate_initial_field_name:{field_name}")
            continue
        fields[field_name] = boundary
    return fields, tuple(unsupported)


def _field_boundary_compatibility_reasons(
    *,
    flow_case_id: str,
    field_name: str,
    boundary: _FoamFieldBoundary,
    mesh_patch_types: Mapping[str, str],
    type_overrides: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    field_patches = set(boundary.entries)
    mesh_patches = set(mesh_patch_types)
    for patch_id in sorted(mesh_patches - field_patches):
        reasons.append(
            f"field_boundary_missing_patch:{flow_case_id}:{field_name}:{patch_id}"
        )
    for patch_id in sorted(field_patches - mesh_patches):
        reasons.append(
            f"field_boundary_unknown_patch:{flow_case_id}:{field_name}:{patch_id}"
        )
    for patch_id in sorted(field_patches & mesh_patches):
        entry = boundary.entries[patch_id]
        override = type_overrides.get(patch_id)
        field_type = (
            str(override["type"])
            if override is not None and isinstance(override.get("type"), str)
            else entry.type_value.value
        )
        mesh_type = str(mesh_patch_types[patch_id])
        if not _field_patch_type_is_compatible(field_type, mesh_type):
            reasons.append(
                "field_patch_type_incompatible:"
                f"{flow_case_id}:{field_name}:{patch_id}:{field_type}:{mesh_type}"
            )
    return reasons


def _field_patch_type_is_compatible(field_type: str, mesh_type: str) -> bool:
    if field_type == "symmetryPlane":
        return mesh_type == "symmetryPlane"
    if field_type in {"empty", "wedge", "cyclic", "cyclicAMI"}:
        return mesh_type == field_type
    if field_type == "adjointWallVelocity" or field_type.endswith("WallFunction"):
        return mesh_type == "wall"
    if field_type in {
        "adjointInletVelocity",
        "adjointOutletVelocity",
        "adjointOutletPressure",
        "adjointZeroInlet",
        "adjointOutletKa",
        "adjointOutletWa",
    }:
        return mesh_type == "patch"
    if field_type in {"fixedValue", "zeroGradient", "calculated"}:
        return mesh_type in {"patch", "wall"}
    return False


def _parse_openfoam_field_boundary(text: str) -> _FoamFieldBoundary | None:
    tokens = _foam_tokens(text)
    candidates: list[int] = []
    brace_depth = 0
    paren_depth = 0
    for index, token in enumerate(tokens):
        if (
            token.value == "boundaryField"
            and brace_depth == 0
            and paren_depth == 0
            and index + 1 < len(tokens)
            and tokens[index + 1].value == "{"
        ):
            candidates.append(index + 1)
        if token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
        if brace_depth < 0 or paren_depth < 0:
            raise ValueError("unbalanced_delimiter")
    if brace_depth != 0 or paren_depth != 0:
        raise ValueError("unbalanced_delimiter")
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("ambiguous_boundary_field")

    opening = candidates[0]
    closing = _matching_token(tokens, opening, "{", "}")
    entries: dict[str, _FoamFieldBoundaryEntry] = {}
    index = opening + 1
    while index < closing:
        if tokens[index].value == ";":
            index += 1
            continue
        name = tokens[index].value
        if index + 1 >= closing or tokens[index + 1].value != "{":
            raise ValueError("invalid_boundary_field_patch_entry")
        if name in entries:
            raise ValueError(f"duplicate_field_patch:{name}")
        body_open = index + 1
        body_close = _matching_token(tokens, body_open, "{", "}")
        if body_close >= closing:
            raise ValueError("field_patch_dictionary_escapes_boundary_field")
        type_token, type_value = _field_patch_type_tokens(
            tokens, body_open, body_close, name
        )
        value_component_spans = _field_patch_value_component_spans(
            tokens, body_open, body_close, name
        )
        entries[name] = _FoamFieldBoundaryEntry(
            name=name,
            body_open=tokens[body_open],
            body_close=tokens[body_close],
            type_token=type_token,
            type_value=type_value,
            value_component_spans=value_component_spans,
        )
        index = body_close + 1
        if index < closing and tokens[index].value == ";":
            index += 1
    if not entries:
        raise ValueError("empty_boundary_field")
    return _FoamFieldBoundary(entries=MappingProxyType(entries))


def _field_patch_type_tokens(
    tokens: Sequence[_FoamToken], body_open: int, body_close: int, patch_name: str
) -> tuple[_FoamToken, _FoamToken]:
    matches: list[tuple[_FoamToken, _FoamToken]] = []
    brace_depth = 0
    paren_depth = 0
    for index in range(body_open + 1, body_close):
        token = tokens[index]
        if token.value == "type" and brace_depth == 0 and paren_depth == 0:
            if (
                index + 2 >= body_close
                or tokens[index + 2].value != ";"
                or tokens[index + 1].value in "{}();"
            ):
                raise ValueError(f"invalid_field_patch_type:{patch_name}")
            matches.append((token, tokens[index + 1]))
        if token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
    if len(matches) != 1:
        raise ValueError(f"ambiguous_field_patch_type:{patch_name}")
    return matches[0]


def _field_patch_value_component_spans(
    tokens: Sequence[_FoamToken], body_open: int, body_close: int, patch_name: str
) -> tuple[tuple[int, int], ...] | None:
    matches: list[tuple[tuple[int, int], ...]] = []
    brace_depth = 0
    paren_depth = 0
    for index in range(body_open + 1, body_close):
        token = tokens[index]
        if token.value == "value" and brace_depth == 0 and paren_depth == 0:
            terminator = _field_statement_terminator(tokens, index, body_close)
            matches.append(
                _uniform_value_component_spans(tokens, index, terminator, patch_name)
            )
        if token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
    if len(matches) > 1:
        raise ValueError(f"ambiguous_field_patch_value:{patch_name}")
    return matches[0] if matches else None


def _uniform_value_component_spans(
    tokens: Sequence[_FoamToken], value_index: int, terminator: int, patch_name: str
) -> tuple[tuple[int, int], ...]:
    uniform_index = value_index + 1
    if uniform_index >= terminator or tokens[uniform_index].value != "uniform":
        raise ValueError(f"unsupported_field_patch_value:{patch_name}")
    first_value = uniform_index + 1
    if first_value >= terminator:
        raise ValueError(f"unsupported_field_patch_value:{patch_name}")
    if tokens[first_value].value != "(":
        if first_value + 1 != terminator or tokens[first_value].value in "{}();":
            raise ValueError(f"unsupported_field_patch_value:{patch_name}")
        return ((tokens[first_value].start, tokens[first_value].end),)
    closing = _matching_token(tokens, first_value, "(", ")")
    if closing + 1 != terminator:
        raise ValueError(f"unsupported_field_patch_value:{patch_name}")
    component_tokens = [
        token
        for token in tokens[first_value + 1 : closing]
        if token.value not in {"(", ")", "{", "}", ";"}
    ]
    if not component_tokens:
        raise ValueError(f"unsupported_field_patch_value:{patch_name}")
    return tuple((token.start, token.end) for token in component_tokens)


def _field_statement_terminator(
    tokens: Sequence[_FoamToken], start: int, body_close: int
) -> int:
    paren_depth = 0
    brace_depth = 0
    for index in range(start + 1, body_close):
        token = tokens[index]
        if token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
        elif token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == ";" and brace_depth == 0 and paren_depth == 0:
            return index
    raise ValueError("unterminated_field_patch_value")


def _stage_retained_field_boundary_contract(
    plan: Any, case_staging: Path
) -> dict[str, Any]:
    mesh_path = case_staging / "system/blockMeshDict"
    mesh_types = {
        patch_id: str(record["type"])
        for patch_id, record in _parse_block_mesh_boundary(
            mesh_path.read_bytes().decode("utf-8")
        ).items()
    }
    initial_dir = case_staging / "0.orig"
    fields, scan_unsupported = _scan_initial_field_boundaries(initial_dir)
    if scan_unsupported:
        raise ValueError("Invalid staged initial field(s): " + ", ".join(scan_unsupported))
    missing = [name for name in _REQUIRED_RETAINED_INITIAL_FIELDS if name not in fields]
    if missing:
        raise ValueError(f"Missing required staged initial field(s): {missing!r}")
    policy = openfoam_retained_field_boundary_specs(plan)

    patched_fields: dict[str, Any] = {}
    for field_name in _REQUIRED_RETAINED_INITIAL_FIELDS:
        path = initial_dir / field_name
        source = path.read_bytes()
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Staged initial field is not UTF-8: {field_name}") from exc
        boundary = _parse_openfoam_field_boundary(text)
        if boundary is None:
            raise ValueError(f"Staged initial field is missing boundaryField: {field_name}")
        specs = policy[field_name]
        patched = _patch_openfoam_field_boundary(text, boundary, specs)
        if patched != text:
            path.write_bytes(patched.encode("utf-8"))
        patched_fields[field_name] = {
            "path": f"0.orig/{field_name}",
            "pre_patch_sha256": hashlib.sha256(source).hexdigest(),
            "post_patch_sha256": _file_sha256(path),
            "manifest_patch_types": {
                patch_id: str(spec["type"])
                for patch_id, spec in sorted(specs.items())
            },
            "validation": "staged_pending_final_validation",
        }
    return {
        "path": "0.orig",
        "flow_case_id": plan.flow_case_id,
        "final_mesh_patch_types": mesh_types,
        "manifest_patched_fields": patched_fields,
        "validation": "staged_pending_final_validation",
    }


def _patch_openfoam_field_boundary(
    text: str,
    boundary: _FoamFieldBoundary,
    specs: Mapping[str, Mapping[str, Any]],
) -> str:
    replacements: list[tuple[int, int, str]] = []
    newline = "\r\n" if "\r\n" in text else "\n"
    for patch_id, spec in sorted(specs.items()):
        entry = boundary.entries.get(patch_id)
        if entry is None:
            raise ValueError(f"Retained field is missing manifest patch: {patch_id}")
        field_type = spec.get("type")
        if not isinstance(field_type, str) or not field_type:
            raise ValueError(f"Retained-field policy is missing a type: {patch_id}")
        replacements.append((entry.type_value.start, entry.type_value.end, field_type))
        if "value" not in spec:
            continue
        value_statement = f"value           uniform {_format_uniform_field_value(spec['value'])};"
        components = _format_uniform_field_components(spec["value"])
        if entry.value_component_spans is not None:
            if len(entry.value_component_spans) != len(components):
                raise ValueError(
                    f"Retained-field value shape does not match policy: {patch_id}"
                )
            replacements.extend(
                (start, end, component)
                for (start, end), component in zip(entry.value_component_spans, components)
            )
            continue
        insertion_start, insertion = _missing_value_insertion(
            text, entry, value_statement, newline
        )
        replacements.append((insertion_start, insertion_start, insertion))
    return _replace_text_spans(text, replacements)


def _missing_value_insertion(
    text: str,
    entry: _FoamFieldBoundaryEntry,
    value_statement: str,
    newline: str,
) -> tuple[int, str]:
    close_line_start = text.rfind("\n", 0, entry.body_close.start) + 1
    close_line_prefix = text[close_line_start:entry.body_close.start]
    if close_line_prefix.strip():
        return entry.body_close.start, f" {value_statement} "
    type_line_start = text.rfind("\n", 0, entry.type_token.start) + 1
    indent = text[type_line_start:entry.type_token.start]
    return close_line_start, f"{indent}{value_statement}{newline}"


def _format_uniform_field_value(value: Any) -> str:
    components = _format_uniform_field_components(value)
    return "(" + " ".join(components) + ")" if len(components) == 3 else components[0]


def _format_uniform_field_components(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) != 3:
            raise ValueError("Retained-field vector value must contain three components")
        return tuple(_format_field_number(item) for item in value)
    return (_format_field_number(value),)


def _format_field_number(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("Retained-field values must be finite numbers")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Retained-field values must be finite numbers") from exc
    if not isfinite(numeric):
        raise ValueError("Retained-field values must be finite numbers")
    if numeric == 0.0:
        return "0"
    return format(numeric, ".12g")


def _replace_text_spans(text: str, replacements: Sequence[tuple[int, int, str]]) -> str:
    result = text
    previous_start = len(text) + 1
    for start, end, replacement in sorted(replacements, reverse=True):
        if start < 0 or end < start or end > len(text) or end > previous_start:
            raise ValueError("Overlapping retained-field patch spans")
        result = result[:start] + replacement + result[end:]
        previous_start = start
    return result


def _validate_staged_field_boundary_contract(
    case_staging: Path, staged_contract: Mapping[str, Any]
) -> dict[str, Any]:
    mesh_path = case_staging / "system/blockMeshDict"
    mesh_types = {
        patch_id: str(record["type"])
        for patch_id, record in _parse_block_mesh_boundary(
            mesh_path.read_bytes().decode("utf-8")
        ).items()
    }
    fields, scan_unsupported = _scan_initial_field_boundaries(case_staging / "0.orig")
    reasons = list(scan_unsupported)
    for field_name in _REQUIRED_RETAINED_INITIAL_FIELDS:
        if field_name not in fields:
            reasons.append(f"missing_required_initial_field:{field_name}")
    records: dict[str, Any] = {}
    for field_name, boundary in fields.items():
        field_reasons = _field_boundary_compatibility_reasons(
            flow_case_id=str(staged_contract["flow_case_id"]),
            field_name=field_name,
            boundary=boundary,
            mesh_patch_types=mesh_types,
            type_overrides={},
        )
        reasons.extend(field_reasons)
        records[field_name] = {
            "path": f"0.orig/{field_name}",
            "patch_types": {
                patch_id: entry.type_value.value
                for patch_id, entry in sorted(boundary.entries.items())
            },
            "validation": "pass" if not field_reasons else "unsupported",
        }
    if reasons:
        raise ValueError("Staged field boundary validation failed: " + ", ".join(reasons))
    return {
        **_json_copy(staged_contract),
        "final_mesh_patch_types": mesh_types,
        "all_initial_fields": records,
        "validation": "pass",
    }


def _parse_block_mesh_boundary(text: str) -> dict[str, dict[str, Any]]:
    tokens = _foam_tokens(text)
    candidates: list[int] = []
    brace_depth = 0
    paren_depth = 0
    for index, token in enumerate(tokens):
        if (
            token.value == "boundary"
            and brace_depth == 0
            and paren_depth == 0
            and index + 1 < len(tokens)
            and tokens[index + 1].value == "("
        ):
            candidates.append(index + 1)
        if token.value == "{":
            brace_depth += 1
        elif token.value == "}":
            brace_depth -= 1
        elif token.value == "(":
            paren_depth += 1
        elif token.value == ")":
            paren_depth -= 1
        if brace_depth < 0 or paren_depth < 0:
            raise ValueError("unbalanced_delimiter")
    if brace_depth != 0 or paren_depth != 0:
        raise ValueError("unbalanced_delimiter")
    if len(candidates) != 1:
        raise ValueError("ambiguous_boundary_dictionary")
    opening = candidates[0]
    closing = _matching_token(tokens, opening, "(", ")")
    result: dict[str, dict[str, Any]] = {}
    index = opening + 1
    while index < closing:
        if tokens[index].value == ";":
            index += 1
            continue
        name = tokens[index].value
        if index + 1 >= closing or tokens[index + 1].value != "{":
            raise ValueError("invalid_boundary_patch_entry")
        if name in result:
            raise ValueError(f"duplicate_patch:{name}")
        body_open = index + 1
        body_close = _matching_token(tokens, body_open, "{", "}")
        if body_close >= closing:
            raise ValueError("patch_dictionary_escapes_boundary")
        type_tokens: list[tuple[_FoamToken, _FoamToken]] = []
        nested_braces = 0
        nested_parens = 0
        cursor = body_open + 1
        while cursor < body_close:
            token = tokens[cursor]
            if (
                token.value == "type"
                and nested_braces == 0
                and nested_parens == 0
            ):
                if (
                    cursor + 2 >= body_close
                    or tokens[cursor + 2].value != ";"
                    or tokens[cursor + 1].value in "{}();"
                ):
                    raise ValueError(f"invalid_patch_type:{name}")
                type_tokens.append((token, tokens[cursor + 1]))
            if token.value == "{":
                nested_braces += 1
            elif token.value == "}":
                nested_braces -= 1
            elif token.value == "(":
                nested_parens += 1
            elif token.value == ")":
                nested_parens -= 1
            cursor += 1
        if len(type_tokens) != 1:
            raise ValueError(f"ambiguous_patch_type:{name}")
        _, type_value = type_tokens[0]
        result[name] = {
            "type": type_value.value,
            "type_span": (type_value.start, type_value.end),
        }
        index = body_close + 1
        if index < closing and tokens[index].value == ";":
            index += 1
    if not result:
        raise ValueError("empty_boundary_dictionary")
    return result


def _foam_tokens(text: str) -> list[_FoamToken]:
    tokens: list[_FoamToken] = []
    punctuation = "{}();"
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated_block_comment")
            index = end + 2
            continue
        start = index
        if text[index] == '"':
            index += 1
            value_start = index
            while index < len(text) and text[index] != '"':
                if text[index] == "\\":
                    index += 1
                index += 1
            if index >= len(text):
                raise ValueError("unterminated_quoted_token")
            tokens.append(_FoamToken(text[value_start:index], start, index + 1))
            index += 1
            continue
        if text[index] in punctuation:
            tokens.append(_FoamToken(text[index], index, index + 1))
            index += 1
            continue
        while (
            index < len(text)
            and not text[index].isspace()
            and text[index] not in punctuation
            and not text.startswith("//", index)
            and not text.startswith("/*", index)
        ):
            index += 1
        if start == index:
            raise ValueError("invalid_token")
        tokens.append(_FoamToken(text[start:index], start, index))
    return tokens


def _matching_token(
    tokens: Sequence[_FoamToken], opening: int, left: str, right: str
) -> int:
    depth = 0
    for index in range(opening, len(tokens)):
        if tokens[index].value == left:
            depth += 1
        elif tokens[index].value == right:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("unbalanced_delimiter")


def _parse_control_dict_libraries(text: str) -> tuple[tuple[str, ...], tuple[int, int]]:
    matches = list(_CONTROL_DICT_LIBS.finditer(text))
    if len(matches) != 1:
        raise ValueError("controlDict must contain exactly one unambiguous libs statement")
    match = matches[0]
    body = match.group("body")[1:-1]
    tokens: list[str] = []
    position = 0
    for token_match in _LIBRARY_TOKEN.finditer(body):
        if body[position : token_match.start()].strip():
            raise ValueError("controlDict libs contains unsupported syntax")
        token = token_match.group(1) or token_match.group(2)
        if token.startswith("//") or token.startswith("/*"):
            raise ValueError("comments inside controlDict libs are not supported")
        tokens.append(token)
        position = token_match.end()
    if body[position:].strip():
        raise ValueError("controlDict libs contains unsupported syntax")
    return tuple(tokens), match.span()


def _resolve_required_library(
    template: Path, token: str
) -> tuple[dict[str, Any], str | None]:
    requested = Path(token)
    name = requested.name
    is_path = requested.is_absolute() or len(requested.parts) > 1
    is_custom = is_path or name.startswith(_CUSTOM_LIBRARY_PREFIX)
    base = {
        "required": token,
        "classification": (
            "case_local_custom_library" if is_custom else "solver_runtime_library"
        ),
        "resolved_source": None,
        "staged_path": None,
        "sha256": None,
    }
    if not is_custom:
        return (
            {
                **base,
                "qualification": "solver_runtime_required_not_verified",
            },
            None,
        )
    if requested.is_absolute():
        return (
            {**base, "qualification": "unsupported_host_absolute_path"},
            f"host_absolute_library_path_not_supported:{token}",
        )

    candidates: list[tuple[str, Path]] = []
    if len(requested.parts) > 1:
        candidate = (template / requested).resolve()
        if not _is_relative_to(candidate, template):
            return (
                {**base, "qualification": "unsafe_relative_path"},
                f"library_path_escapes_template:{token}",
            )
        candidates.append(("template_relative", candidate))
    else:
        candidates.append(("template_lib", template / "lib" / name))
        repository_relative = _KNOWN_REPOSITORY_LIBRARIES.get(name)
        if repository_relative is not None:
            repository_root = Path(__file__).resolve().parents[2]
            candidates.append(
                ("repository_extension", repository_root / repository_relative)
            )

    for origin, candidate in candidates:
        if candidate.is_file():
            return (
                {
                    **base,
                    "resolved_source": str(candidate.resolve()),
                    "resolution_origin": origin,
                    "staged_path": f"lib/{name}",
                    "sha256": _file_sha256(candidate),
                    "qualification": "resolved_for_staging",
                },
                None,
            )
    return (
        {**base, "qualification": "missing"},
        f"missing_custom_library:{token}",
    )


def _stage_execution_contract(
    execution_contract: Mapping[str, Any], case_staging: Path
) -> dict[str, Any]:
    staged_scripts: list[dict[str, Any]] = []
    for raw in execution_contract["scripts"]:
        script = dict(raw)
        staged_path = script.get("staged_path")
        if not isinstance(staged_path, str):
            raise ValueError(f"Unresolved execution script: {script['required']}")
        destination = case_staging / staged_path
        if _file_sha256(destination) != script["sha256"]:
            raise OSError(
                f"Staged execution script hash mismatch: {script['required']}"
            )
        pre_patch_sha = _file_sha256(destination)
        if script["required"] == "Allrun":
            patched, patch_applied = _patch_allrun_fail_fast(destination.read_bytes())
            destination.write_bytes(patched)
            if not _allrun_has_immediate_set_e(patched.decode("utf-8")):
                raise ValueError("Staged Allrun does not guarantee fail-fast execution")
            script["fail_fast"] = True
            script["patch_applied"] = patch_applied
            script["qualification"] = "staged_fail_fast_not_runtime_qualified"
        else:
            script["patch_applied"] = False
            script["qualification"] = "staged_not_runtime_qualified"
        script["pre_patch_sha256"] = pre_patch_sha
        script["post_patch_sha256"] = _file_sha256(destination)
        staged_scripts.append(script)

    staged_libraries: list[dict[str, Any]] = []
    replacement_tokens: list[str] = []
    for raw in execution_contract["libraries"]:
        library = dict(raw)
        staged_path = library.get("staged_path")
        source = library.get("resolved_source")
        if library["classification"] == "case_local_custom_library":
            if not isinstance(staged_path, str) or not isinstance(source, str):
                raise ValueError(f"Unresolved custom library: {library['required']}")
            destination = case_staging / staged_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(source), destination)
            if _file_sha256(destination) != library["sha256"]:
                raise OSError(f"Staged library hash mismatch: {library['required']}")
            library["qualification"] = "staged_not_runtime_qualified"
            replacement_tokens.append(f"./{staged_path}")
        else:
            replacement_tokens.append(str(library["required"]))
        staged_libraries.append(library)

    control_dict = case_staging / "system/controlDict"
    text = control_dict.read_text(encoding="utf-8")
    _, span = _parse_control_dict_libraries(text)
    replacement = "libs\n(\n" + "".join(
        f'    "{token}"\n' for token in replacement_tokens
    ) + ");"
    control_dict.write_text(
        text[: span[0]] + replacement + text[span[1] :],
        encoding="utf-8",
        newline="\n",
    )
    return {
        **_json_copy(execution_contract),
        "scripts": staged_scripts,
        "libraries": staged_libraries,
        "qualification": "compiled_not_runtime_qualified",
        "runtime_execution": "not_run",
    }


def _patch_allrun_fail_fast(source: bytes) -> tuple[bytes, bool]:
    text = source.decode("utf-8")
    if not text.startswith("#!"):
        raise ValueError("Allrun must start with a shebang")
    if _allrun_has_immediate_set_e(text):
        return source, False
    newline_index = source.find(b"\n")
    if newline_index < 0:
        return source + b"\nset -e\n", True
    newline = b"\r\n" if source[: newline_index + 1].endswith(b"\r\n") else b"\n"
    insertion = b"set -e" + newline
    return source[: newline_index + 1] + insertion + source[newline_index + 1 :], True


def _allrun_has_immediate_set_e(text: str) -> bool:
    lines = text.splitlines()
    if len(lines) < 2 or not lines[0].startswith("#!"):
        return False
    return re.fullmatch(r"\s*set\s+-[A-Za-z]*e[A-Za-z]*\s*(?:#.*)?", lines[1]) is not None


def _bundle_metadata(
    *,
    spec: ProblemSpec,
    template: Path,
    manifest_sha: str,
    compile_ready: bool,
    status: str,
    unsupported: Sequence[str],
    flow_cases: Mapping[str, Any],
    template_files: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "openfoam_case_bundle",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_hash_from_manifest_file_value(spec),
        "manifest_path": _MANIFEST_NAME,
        "manifest_sha256": manifest_sha,
        "template": {
            "template_case_dir": str(template),
            "files_sha256": dict(template_files),
        },
        "compile_ready": compile_ready,
        "status": status,
        "unsupported": list(unsupported),
        "flow_cases": _json_copy(flow_cases),
    }


def problem_spec_hash_from_manifest_file_value(spec: ProblemSpec) -> str:
    # Kept local so the bundle and manifest use the same public canonical hash contract.
    from .problem_spec import problem_spec_sha256

    return problem_spec_sha256(spec)


def _all_unsupported(manifest: SolverCaseManifest) -> tuple[str, ...]:
    return (
        *manifest.unsupported,
        *(reason for plan in manifest.flow_cases for reason in plan.unsupported),
    )


def _contained_case_dir(output: Path, relative: str) -> Path:
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or len(candidate_relative.parts) != 1:
        raise ValueError(f"Unsafe case directory name: {relative!r}")
    candidate = (output / candidate_relative).resolve()
    if not _is_relative_to(candidate, output) or candidate == output:
        raise ValueError(f"Case directory escapes output_dir: {relative!r}")
    return candidate


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            _json_copy(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value


__all__ = [
    "DEFAULT_FIXED_GRID_PATCH_IDS",
    "OpenFOAMCaseBundleArtifacts",
    "compile_openfoam_solver_case_bundle",
]
