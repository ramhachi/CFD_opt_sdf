"""Patch OpenFOAM force-response dictionaries using brace-aware parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, NamedTuple

from .solver_case_manifest import SolverFlowCasePlan


_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MARKER_NAME = "generated_openfoam_responses.json"


@dataclass(frozen=True)
class OpenFOAMResponseArtifacts:
    case_dir: Path
    optimisation_dict: Path
    fv_options: Path
    metadata_json: Path
    response_ids: tuple[str, ...]
    file_sha256: Mapping[str, str]


class _Token(NamedTuple):
    value: str
    start: int
    end: int
    depth: int


def render_openfoam_force_response_files(
    plan: SolverFlowCasePlan,
    case_dir: str | Path,
    *,
    adjoint_iterations: int = 1,
    overwrite: bool = False,
) -> OpenFOAMResponseArtifacts:
    """Patch response blocks after fully rendering and validating both outputs."""

    if plan.unsupported:
        raise ValueError(f"Cannot render a flow plan with unsupported features: {plan.unsupported!r}")
    if isinstance(adjoint_iterations, bool) or not isinstance(adjoint_iterations, int) or adjoint_iterations <= 0:
        raise ValueError("adjoint_iterations must be a positive integer")
    _validate_id(plan.flow_case_id, "flow_case_id")
    responses = _validated_responses(plan)

    target = Path(case_dir)
    optimisation_path = target / "system/optimisationDict"
    fv_options_path = target / "system/fvOptions"
    marker_path = target / _MARKER_NAME
    if not optimisation_path.is_file() or not fv_options_path.is_file():
        raise FileNotFoundError(
            "case_dir must contain system/optimisationDict and system/fvOptions"
        )
    if marker_path.exists() and not overwrite:
        raise FileExistsError(f"Generated responses already exist; use overwrite=True: {target}")

    optimisation_before_bytes = optimisation_path.read_bytes()
    fv_options_before_bytes = fv_options_path.read_bytes()
    optimisation_before = optimisation_before_bytes.decode("utf-8")
    fv_options_before = fv_options_before_bytes.decode("utf-8")
    manager_block = _adjoint_managers_block(responses, adjoint_iterations)
    optimisation_after = _replace_unique_top_level_block(
        optimisation_before, "adjointManagers", manager_block
    )
    field_names = ("U", *(f"Uaresp_{response['response_id']}" for response in responses))
    fv_options_after = _replace_toposource_names(fv_options_before, field_names)

    pre_hashes = {
        "system/optimisationDict": hashlib.sha256(optimisation_before_bytes).hexdigest(),
        "system/fvOptions": hashlib.sha256(fv_options_before_bytes).hexdigest(),
    }
    post_hashes = {
        "system/optimisationDict": _sha256(optimisation_after),
        "system/fvOptions": _sha256(fv_options_after),
    }
    mappings = [
        {
            "flow_case_id": plan.flow_case_id,
            "response_id": response["response_id"],
            "adjoint_solver_id": f"resp_{response['response_id']}",
            "adjoint_velocity_field": f"Uaresp_{response['response_id']}",
            "objective_name": response["response_id"],
        }
        for response in responses
    ]
    metadata = {
        "schema_version": 1,
        "kind": "generated_openfoam_responses",
        "flow_case_id": plan.flow_case_id,
        "case_directory_name": plan.case_directory_name,
        "adjoint_iterations": adjoint_iterations,
        "response_mappings": mappings,
        "source_files": {
            name: {"pre_sha256": pre_hashes[name], "post_sha256": post_hashes[name]}
            for name in ("system/optimisationDict", "system/fvOptions")
        },
    }
    metadata_text = json.dumps(
        metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    optimisation_path.write_bytes(optimisation_after.encode("utf-8"))
    fv_options_path.write_bytes(fv_options_after.encode("utf-8"))
    marker_path.write_bytes(metadata_text.encode("utf-8"))
    return OpenFOAMResponseArtifacts(
        case_dir=target,
        optimisation_dict=optimisation_path,
        fv_options=fv_options_path,
        metadata_json=marker_path,
        response_ids=tuple(response["response_id"] for response in responses),
        file_sha256=MappingProxyType(dict(post_hashes)),
    )


def _validated_responses(plan: SolverFlowCasePlan) -> tuple[dict[str, Any], ...]:
    generated = plan.generated
    if not isinstance(generated, Mapping):
        raise ValueError("plan.generated must be a mapping")
    raw_responses = generated.get("responses")
    if (
        not isinstance(raw_responses, Sequence)
        or isinstance(raw_responses, (str, bytes, bytearray))
        or not raw_responses
    ):
        raise ValueError("generated.responses must be a non-empty sequence")
    responses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_responses):
        if not isinstance(raw, Mapping):
            raise ValueError(f"generated.responses[{index}] must be a mapping")
        response_id = raw.get("response_id")
        if not isinstance(response_id, str):
            raise ValueError(f"generated.responses[{index}].response_id must be a string")
        _validate_id(response_id, "response_id")
        if response_id in seen:
            raise ValueError(f"Duplicate generated response_id: {response_id!r}")
        seen.add(response_id)
        if raw.get("openfoam_objective_type") != "porousDirectionalForce":
            raise ValueError(
                f"generated response {response_id!r} must use porousDirectionalForce"
            )
        direction = _vector3(raw.get("direction"), f"response {response_id} direction")
        aref = _positive_number(raw.get("Aref"), f"response {response_id} Aref")
        uinf = _positive_number(raw.get("UInf"), f"response {response_id} UInf")
        responses.append(
            {
                "response_id": response_id,
                "direction": direction,
                "Aref": aref,
                "UInf": uinf,
            }
        )
    ids = tuple(response["response_id"] for response in responses)
    if ids != plan.supported_response_ids:
        raise ValueError("generated response IDs must match supported_response_ids in order")
    return tuple(responses)


def _adjoint_managers_block(
    responses: tuple[dict[str, Any], ...], adjoint_iterations: int
) -> str:
    solver_blocks = "\n".join(
        _adjoint_solver_block(response, adjoint_iterations) for response in responses
    )
    return (
        "adjointManagers\n"
        "{\n"
        "    adjManager1\n"
        "    {\n"
        "        primalSolver op1;\n"
        "        adjointSolvers\n"
        "        {\n"
        f"{solver_blocks}\n"
        "        }\n"
        "    }\n"
        "}"
    )


def _adjoint_solver_block(response: Mapping[str, Any], iterations: int) -> str:
    response_id = str(response["response_id"])
    direction = "(" + " ".join(_format_number(value) for value in response["direction"]) + ")"
    return (
        f"            resp_{response_id}\n"
        "            {\n"
        "                active true;\n"
        "                type incompressible;\n"
        "                solver adjointSimple;\n"
        "                isConstraint false;\n"
        "                objectives\n"
        "                {\n"
        "                    type incompressible;\n"
        "                    objectiveNames\n"
        "                    {\n"
        f"                        {response_id}\n"
        "                        {\n"
        "                            weight 1;\n"
        "                            type porousDirectionalForce;\n"
        f"                            direction {direction};\n"
        f"                            Aref {_format_number(response['Aref'])};\n"
        f"                            UInf {_format_number(response['UInf'])};\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "                ATCModel\n"
        "                {\n"
        "                    ATCModel standard;\n"
        "                    extraConvection 1;\n"
        "                }\n"
        "                solutionControls\n"
        "                {\n"
        f"                    nIters {iterations};\n"
        "                    residualControl\n"
        "                    {\n"
        "                        \"pa.*\" 5e-7;\n"
        "                        \"Ua.*\" 5e-7;\n"
        "                    }\n"
        "                }\n"
        "            }"
    )


def _replace_unique_top_level_block(text: str, name: str, replacement: str) -> str:
    tokens = _tokens(text)
    blocks = _named_top_level_blocks(tokens, name)
    if len(blocks) != 1:
        raise ValueError(f"Expected exactly one top-level {name} block, found {len(blocks)}")
    start, end = blocks[0]
    return text[:start] + replacement + text[end:]


def _replace_toposource_names(text: str, field_names: tuple[str, ...]) -> str:
    tokens = _tokens(text)
    blocks = _all_top_level_blocks(tokens)
    top_sources: list[tuple[int, int, int, int]] = []
    for start, end, open_index, close_index in blocks:
        type_values = []
        for index in range(open_index + 1, close_index - 1):
            token = tokens[index]
            if token.depth == 1 and token.value == "type":
                type_values.append(tokens[index + 1].value)
        if type_values == ["topOSource"]:
            top_sources.append((start, end, open_index, close_index))
    if len(top_sources) != 1:
        raise ValueError(f"Expected exactly one topOSource block, found {len(top_sources)}")
    _, _, open_index, close_index = top_sources[0]
    names_tokens: list[tuple[int, int]] = []
    for index in range(open_index + 1, close_index):
        token = tokens[index]
        if token.depth == 1 and token.value == "names":
            if index + 1 >= len(tokens) or tokens[index + 1].value != "(":
                raise ValueError("topOSource names must use parenthesized syntax")
            closing = _matching_token(tokens, index + 1, "(", ")")
            names_tokens.append((tokens[index + 1].start, tokens[closing].end))
    if len(names_tokens) != 1:
        raise ValueError(f"Expected exactly one names statement in topOSource, found {len(names_tokens)}")
    start, end = names_tokens[0]
    return text[:start] + "(" + " ".join(field_names) + ")" + text[end:]


def _tokens(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    depth = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated block comment")
            index = end + 2
            continue
        if char in {'"', "'"}:
            quote = char
            cursor = index + 1
            while cursor < len(text):
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == quote:
                    break
                cursor += 1
            if cursor >= len(text):
                raise ValueError("Unterminated quoted text")
            index = cursor + 1
            continue
        if char == "{":
            tokens.append(_Token(char, index, index + 1, depth))
            depth += 1
            index += 1
            continue
        if char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced closing brace")
            tokens.append(_Token(char, index, index + 1, depth))
            index += 1
            continue
        if char in "();":
            tokens.append(_Token(char, index, index + 1, depth))
            index += 1
            continue
        if char.isalpha() or char == "_":
            cursor = index + 1
            while cursor < len(text) and (text[cursor].isalnum() or text[cursor] in "_.-"):
                cursor += 1
            tokens.append(_Token(text[index:cursor], index, cursor, depth))
            index = cursor
            continue
        index += 1
    if depth != 0:
        raise ValueError("Unbalanced opening brace")
    return tokens


def _named_top_level_blocks(tokens: list[_Token], name: str) -> list[tuple[int, int]]:
    return [
        (start, end)
        for start, end, open_index, _ in _all_top_level_blocks(tokens)
        if tokens[open_index - 1].value == name
    ]


def _all_top_level_blocks(tokens: list[_Token]) -> list[tuple[int, int, int, int]]:
    blocks: list[tuple[int, int, int, int]] = []
    for index in range(len(tokens) - 1):
        name = tokens[index]
        opening = tokens[index + 1]
        if name.depth == 0 and opening.depth == 0 and opening.value == "{" and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_.-]*", name.value
        ):
            closing_index = _matching_token(tokens, index + 1, "{", "}")
            blocks.append((name.start, tokens[closing_index].end, index + 1, closing_index))
    return blocks


def _matching_token(
    tokens: list[_Token], opening_index: int, opening: str, closing: str
) -> int:
    level = 0
    for index in range(opening_index, len(tokens)):
        if tokens[index].value == opening:
            level += 1
        elif tokens[index].value == closing:
            level -= 1
            if level == 0:
                return index
    raise ValueError(f"Unbalanced {opening}{closing} delimiters")


def _positive_number(value: Any, context: str) -> float:
    result = _number(value, context)
    if result <= 0.0:
        raise ValueError(f"{context} must be positive")
    return result


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be finite") from exc
    if not isfinite(result):
        raise ValueError(f"{context} must be finite")
    return result


def _vector3(value: Any, context: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 3:
        raise ValueError(f"{context} must be a finite vector3")
    return tuple(_number(component, context) for component in value)  # type: ignore[return-value]


def _format_number(value: Any) -> str:
    result = _number(value, "OpenFOAM numeric value")
    if result == 0.0:
        return "0"
    return format(result, ".12g")


def _validate_id(value: str, context: str) -> None:
    if _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Unsafe {context}: {value!r}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["OpenFOAMResponseArtifacts", "render_openfoam_force_response_files"]
