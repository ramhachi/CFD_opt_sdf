"""Compile a ProblemSpec into a safe, deterministic per-flow OpenFOAM bundle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from types import MappingProxyType
from typing import Any

from .openfoam_case_renderer import render_openfoam_physics_files
from .openfoam_response_renderer import render_openfoam_force_response_files
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


def compile_openfoam_solver_case_bundle(
    spec: ProblemSpec,
    *,
    template_case_dir: str | Path,
    output_dir: str | Path,
    available_patch_ids: Sequence[str] | None,
    adjoint_iterations: int = 1,
    overwrite: bool = False,
    require_compile_ready: bool = True,
) -> OpenFOAMCaseBundleArtifacts:
    """Compile a per-flow bundle without copying runtime result directories."""

    if (
        isinstance(adjoint_iterations, bool)
        or not isinstance(adjoint_iterations, int)
        or adjoint_iterations <= 0
    ):
        raise ValueError("adjoint_iterations must be a positive integer")
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
    mesh_boundary_contract, mesh_unsupported = _audit_mesh_boundary_contract(
        template, manifest
    )
    execution_unsupported = (*execution_unsupported, *mesh_unsupported)
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
        bundle["mesh_boundary_contract"] = mesh_boundary_contract
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
                case_mesh_boundary_contract = _stage_mesh_boundary_contract(
                    plan, case_staging
                )

                physics_staging = Path(
                    tempfile.mkdtemp(
                        prefix=f".physics_{plan.flow_case_id}_", dir=output
                    )
                )
                try:
                    physics = render_openfoam_physics_files(plan, physics_staging)
                    physics_owned = (
                        physics.transport_properties,
                        physics.turbulence_properties,
                        physics.adjoint_turbulence_properties,
                        physics.fv_schemes,
                        physics.fv_solution,
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
                    },
                    "responses": {
                        "metadata_sha256": _file_sha256(response_marker),
                        "files_sha256": dict(responses.file_sha256),
                    },
                    "execution_contract": case_execution_contract,
                    "mesh_boundary_contract": case_mesh_boundary_contract,
                    "status": "compiled",
                    "execution_qualification": "not_run",
                }
                _write_json(compilation_path, compilation)
                compilation_sha = _file_sha256(compilation_path)
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
        failed_bundle["mesh_boundary_contract"] = mesh_boundary_contract
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
    bundle["mesh_boundary_contract"] = mesh_boundary_contract
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
