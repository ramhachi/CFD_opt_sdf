"""Extract fail-closed numerical evidence from a compiled OpenFOAM flow case.

The convergence qualifier intentionally accepts only a small, JSON-compatible
evidence shape.  This module is the boundary between OpenFOAM's text output and
that shape.  It does not infer a normalized mass imbalance from raw continuity
errors, and it does not guess response-to-adjoint-field mappings: both would
make an incomplete run look qualified.  Unscoped OpenFOAM adjoint fields are
accepted only while a compiler-recorded adjoint-solver marker is active.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any

from .openfoam_mass_imbalance import (
    NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME,
    validate_normalized_mass_imbalance_artifact,
)


OPENFOAM_FLOW_CASE_EVIDENCE_SCHEMA_VERSION = 1

_DEFAULT_SOLVER_APPLICATION = "adjointOptimisationFoam"
_RESPONSE_METADATA_NAME = "generated_openfoam_responses.json"
_PHYSICS_METADATA_NAME = "generated_openfoam_physics.json"
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_APPLICATION_PATTERN = re.compile(
    r"(?m)^\s*application\s+([A-Za-z_][A-Za-z0-9_.-]*)\s*;"
)
_RESIDUAL_PATTERN = re.compile(
    r"\bSolving\s+for\s+(?P<field>[A-Za-z_][A-Za-z0-9_]*)\s*,\s*"
    r"Initial\s+residual\s*=\s*(?P<initial>[^,\s]+)\s*,\s*"
    r"Final\s+residual\s*=\s*(?P<final>[^,\s]+)\s*,\s*"
    r"No\s+Iterations\s+(?P<iterations>[^\s]+)\s*$"
)
_RESIDUAL_FIELD_PATTERN = re.compile(
    r"\bSolving\s+for\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)
_CONTINUITY_PATTERN = re.compile(
    r"^\s*time\s+step\s+continuity\s+errors\s*:\s*"
    r"sum\s+local\s*=\s*(?P<sum_local>[^,\s]+)\s*,\s*"
    r"global\s*=\s*(?P<global>[^,\s]+)\s*,\s*"
    r"cumulative\s*=\s*(?P<cumulative>[^\s]+)\s*$",
    flags=re.IGNORECASE,
)
_CONTINUITY_PREFIX = re.compile(
    r"^\s*time\s+step\s+continuity\s+errors\s*:", flags=re.IGNORECASE
)
_ADJOINT_MARKER_PATTERN = re.compile(
    r"^\s*Adjoint\s+solver\s+(?P<solver>[A-Za-z_][A-Za-z0-9_]*)\s*$",
    flags=re.IGNORECASE,
)


def extract_openfoam_flow_case_evidence(case_dir: str | Path) -> dict[str, Any]:
    """Return convergence evidence for one compiled OpenFOAM flow-case directory.

    The returned object can be passed directly as one value in
    ``evaluate_openfoam_convergence_bundle(..., evidence_by_flow_case)``.  A
    ``status`` of ``complete`` only means that all required evidence categories
    were extracted; it does *not* claim numerical convergence.  Numerical
    convergence remains the responsibility of ``convergence_qualification``.

    Missing or malformed inputs return an ``incomplete`` object with empty/null
    required values, so existing qualification gates fail without trusting
    extractor-only status metadata.
    """

    target = Path(case_dir)
    if not target.is_dir():
        raise FileNotFoundError(f"OpenFOAM flow-case directory does not exist: {target}")

    mappings, response_source, response_reasons = _load_response_mappings(target)
    primal_fields, physics_source, physics_reasons = _load_primal_fields(target)
    mass_history, mass_source, mass_reasons = _load_normalized_mass_imbalance(target)
    solver_log, solver_source, log_reasons = _load_solver_log(target)

    response_history = {mapping["response_id"]: [] for mapping in mappings}
    adjoint_residual_history = {mapping["response_id"]: [] for mapping in mappings}
    primal_residual_history: list[dict[str, Any]] = []
    normalized_mass_imbalance_history = mass_history
    continuity_error_history: list[dict[str, Any]] = []
    adjoint_solver_markers = {mapping["response_id"]: 0 for mapping in mappings}
    parse_issues: list[str] = []
    invalid_primal = False
    invalid_responses: set[str] = set()
    invalid_adjoint_responses: set[str] = set()

    if solver_log is not None:
        parsed = _parse_solver_log(
            solver_log,
            mappings=mappings,
            primal_fields=primal_fields,
        )
        primal_residual_history = parsed["primal_residual_history"]
        response_history = parsed["response_history"]
        adjoint_residual_history = parsed["adjoint_residual_history"]
        continuity_error_history = parsed["continuity_error_history"]
        adjoint_solver_markers = parsed["adjoint_solver_markers"]
        parse_issues = parsed["parse_issues"]
        invalid_primal = parsed["invalid_primal"]
        invalid_responses = parsed["invalid_responses"]
        invalid_adjoint_responses = parsed["invalid_adjoint_responses"]

    # Do not leave a partially parsed series available to a downstream gate
    # after a semantic parsing error in that same evidence category.
    if invalid_primal:
        primal_residual_history = []
    for response_id in invalid_responses:
        response_history[response_id] = []
    for response_id in invalid_adjoint_responses:
        adjoint_residual_history[response_id] = []

    incomplete_reasons = [
        *response_reasons,
        *physics_reasons,
        *mass_reasons,
        *log_reasons,
        *parse_issues,
    ]
    if not primal_residual_history:
        incomplete_reasons.append("missing_primal_residual_history")
    if not normalized_mass_imbalance_history:
        incomplete_reasons.append("missing_normalized_mass_imbalance_history")
    for mapping in mappings:
        response_id = mapping["response_id"]
        if not response_history[response_id]:
            incomplete_reasons.append(f"missing_response_history:{response_id}")
        if not adjoint_residual_history[response_id]:
            incomplete_reasons.append(
                f"missing_adjoint_residual_history:{response_id}"
            )

    incomplete_reasons = sorted(set(incomplete_reasons))
    return {
        "schema_version": OPENFOAM_FLOW_CASE_EVIDENCE_SCHEMA_VERSION,
        "kind": "openfoam_flow_case_convergence_evidence",
        "case_directory_name": target.name,
        "status": "complete" if not incomplete_reasons else "incomplete",
        "complete": not incomplete_reasons,
        "incomplete_reasons": incomplete_reasons,
        # The following five members are intentionally the exact shape used by
        # convergence_qualification.  Keep them at the top level.
        "solver_log": solver_log,
        "primal_residual_history": primal_residual_history,
        "normalized_mass_imbalance_history": normalized_mass_imbalance_history,
        "response_history": response_history,
        "adjoint_residual_history": adjoint_residual_history,
        "sources": {
            "solver_log": solver_source,
            "response_metadata": response_source,
            "physics_metadata": physics_source,
            "normalized_mass_imbalance": mass_source,
        },
        "diagnostics": {
            "continuity_error_history": continuity_error_history,
            "adjoint_solver_markers": adjoint_solver_markers,
            "parse_issues": parse_issues,
        },
    }


def write_openfoam_flow_case_evidence(
    evidence: Mapping[str, Any], path: str | Path
) -> Path:
    """Write an extracted evidence object as deterministic JSON."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            dict(evidence),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return target


def _load_response_mappings(
    case_dir: Path,
) -> tuple[list[dict[str, str]], dict[str, Any], list[str]]:
    path = case_dir / _RESPONSE_METADATA_NAME
    if not path.is_file():
        return [], _missing_source(_RESPONSE_METADATA_NAME), ["missing_response_metadata"]
    raw, source = _read_json_source(path, _RESPONSE_METADATA_NAME)
    if raw is None:
        return [], source, ["invalid_response_metadata"]
    if not isinstance(raw, Mapping) or raw.get("kind") != "generated_openfoam_responses":
        return [], _invalid_source(source), ["invalid_response_metadata"]
    raw_mappings = raw.get("response_mappings")
    if not _is_sequence(raw_mappings) or not raw_mappings:
        return [], _invalid_source(source), ["invalid_response_metadata"]

    mappings: list[dict[str, str]] = []
    response_ids: set[str] = set()
    objective_names: set[str] = set()
    solver_ids: set[str] = set()
    velocity_fields: set[str] = set()
    for item in raw_mappings:
        if not isinstance(item, Mapping):
            return [], _invalid_source(source), ["invalid_response_metadata"]
        response_id = item.get("response_id")
        objective_name = item.get("objective_name")
        adjoint_solver_id = item.get("adjoint_solver_id")
        adjoint_velocity_field = item.get("adjoint_velocity_field")
        if (
            not _safe_id(response_id)
            or not _safe_id(objective_name)
            or not _safe_field(adjoint_solver_id)
            or not _safe_field(adjoint_velocity_field)
            or not str(adjoint_velocity_field).startswith("Ua")
        ):
            return [], _invalid_source(source), ["invalid_response_metadata"]
        if (
            response_id in response_ids
            or objective_name in objective_names
            or adjoint_solver_id in solver_ids
            or adjoint_velocity_field in velocity_fields
        ):
            return [], _invalid_source(source), ["invalid_response_metadata"]
        response_ids.add(response_id)
        objective_names.add(objective_name)
        solver_ids.add(adjoint_solver_id)
        velocity_fields.add(adjoint_velocity_field)
        mappings.append(
            {
                "response_id": response_id,
                "objective_name": objective_name,
                "adjoint_solver_id": adjoint_solver_id,
                "adjoint_velocity_field": adjoint_velocity_field,
            }
        )
    return mappings, source, []


def _load_primal_fields(
    case_dir: Path,
) -> tuple[set[str], dict[str, Any], list[str]]:
    path = case_dir / _PHYSICS_METADATA_NAME
    if not path.is_file():
        return set(), _missing_source(_PHYSICS_METADATA_NAME), ["missing_physics_metadata"]
    raw, source = _read_json_source(path, _PHYSICS_METADATA_NAME)
    if raw is None:
        return set(), source, ["invalid_physics_metadata"]
    if not isinstance(raw, Mapping) or raw.get("kind") != "generated_openfoam_physics":
        return set(), _invalid_source(source), ["invalid_physics_metadata"]
    generated = raw.get("generated")
    turbulence = generated.get("turbulence") if isinstance(generated, Mapping) else None
    model = turbulence.get("model") if isinstance(turbulence, Mapping) else None
    if model == "laminar":
        return {"U", "p"}, source, []
    if model == "k_omega_sst":
        return {"U", "p", "k", "omega", "nut"}, source, []
    return set(), _invalid_source(source), ["unsupported_or_invalid_turbulence_model"]


def _load_normalized_mass_imbalance(
    case_dir: Path,
) -> tuple[list[float], dict[str, Any], list[str]]:
    """Load only structured patch-flux evidence, never a solver-log estimate."""

    path = case_dir / NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME
    if not path.is_file():
        return [], _missing_source(NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME), [
            "missing_normalized_mass_imbalance_artifact"
        ]
    raw, source = _read_json_source(path, NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME)
    if raw is None:
        return [], source, ["invalid_normalized_mass_imbalance_artifact"]
    try:
        expected_flow_case_id, expected_open_patch_ids = _mass_imbalance_contract(
            case_dir
        )
        return validate_normalized_mass_imbalance_artifact(
            raw,
            expected_flow_case_id=expected_flow_case_id,
            expected_open_patch_ids=expected_open_patch_ids,
        ), source, []
    except ValueError:
        return [], _invalid_source(source), ["invalid_normalized_mass_imbalance_artifact"]


def _mass_imbalance_contract(case_dir: Path) -> tuple[str, Sequence[str]]:
    """Read the compiler-owned identity and patch set for an evidence file."""

    try:
        raw = json.loads((case_dir / _PHYSICS_METADATA_NAME).read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid physics metadata for mass-imbalance evidence") from exc
    if not isinstance(raw, Mapping) or raw.get("kind") != "generated_openfoam_physics":
        raise ValueError("invalid physics metadata for mass-imbalance evidence")
    flow_case_id = raw.get("flow_case_id")
    contract = raw.get("normalized_mass_imbalance")
    if not _safe_id(flow_case_id) or not isinstance(contract, Mapping):
        raise ValueError("missing compiler mass-imbalance contract")
    patches = contract.get("open_patch_ids")
    if not _is_sequence(patches) or not patches:
        raise ValueError("missing compiler mass-imbalance patch set")
    return str(flow_case_id), [str(patch) for patch in patches]


def _load_solver_log(
    case_dir: Path,
) -> tuple[str | None, dict[str, Any], list[str]]:
    application = _configured_application(case_dir / "system" / "controlDict")
    candidates = _unique(
        [
            *([f"log.{application}"] if application is not None else []),
            f"log.{_DEFAULT_SOLVER_APPLICATION}",
        ]
    )
    existing = [case_dir / candidate for candidate in candidates if (case_dir / candidate).is_file()]
    if not existing:
        return None, {
            "status": "missing",
            "candidates": candidates,
        }, ["missing_solver_log"]
    if len(existing) != 1:
        return None, {
            "status": "ambiguous",
            "candidates": [path.name for path in existing],
        }, ["ambiguous_solver_log"]
    path = existing[0]
    payload = path.read_bytes()
    return payload.decode("utf-8", errors="replace"), {
        "status": "found",
        "path": path.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }, []


def _configured_application(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _APPLICATION_PATTERN.search(text)
    return match.group(1) if match else None


def _parse_solver_log(
    log_text: str,
    *,
    mappings: Sequence[Mapping[str, str]],
    primal_fields: set[str],
) -> dict[str, Any]:
    response_history = {mapping["response_id"]: [] for mapping in mappings}
    adjoint_residual_history = {mapping["response_id"]: [] for mapping in mappings}
    markers = {mapping["response_id"]: 0 for mapping in mappings}
    solver_to_response = {
        mapping["adjoint_solver_id"]: mapping["response_id"] for mapping in mappings
    }
    objective_to_response = {
        mapping["objective_name"]: mapping["response_id"] for mapping in mappings
    }
    primal_rows: list[dict[str, Any]] = []
    continuity_rows: list[dict[str, Any]] = []
    parse_issues: list[str] = []
    invalid_primal = False
    invalid_responses: set[str] = set()
    invalid_adjoint_responses: set[str] = set()
    global_residual_failure = False
    residual_index = 0
    active_adjoint_response: str | None = None

    for line in log_text.splitlines():
        marker = _ADJOINT_MARKER_PATTERN.match(line)
        if marker is not None:
            response_id = solver_to_response.get(marker.group("solver"))
            active_adjoint_response = response_id
            if response_id is not None:
                markers[response_id] += 1

        continuity = _CONTINUITY_PATTERN.match(line)
        if continuity is not None:
            values = {
                key: _finite_float(continuity.group(key))
                for key in ("sum_local", "global", "cumulative")
            }
            if any(value is None for value in values.values()):
                parse_issues.append("invalid_continuity_error")
            else:
                continuity_rows.append(
                    {
                        "index": len(continuity_rows),
                        "sum_local": values["sum_local"],
                        "global": values["global"],
                        "cumulative": values["cumulative"],
                    }
                )
        elif _CONTINUITY_PREFIX.match(line) is not None:
            parse_issues.append("invalid_continuity_error")

        matched_objective = _matching_objective_line(line, objective_to_response)
        if matched_objective is not None:
            response_id, value_text = matched_objective
            value = _finite_float(value_text)
            if value is None:
                invalid_responses.add(response_id)
                parse_issues.append(f"invalid_response_value:{response_id}")
            else:
                response_history[response_id].append(value)

        if "Solving for" not in line:
            continue
        residual = _RESIDUAL_PATTERN.search(line)
        if residual is None:
            field_match = _RESIDUAL_FIELD_PATTERN.search(line)
            field = field_match.group(1) if field_match is not None else None
            if field is None:
                global_residual_failure = True
            else:
                response_id = _adjoint_response_for_field(
                    field,
                    mappings,
                    active_response_id=active_adjoint_response,
                )
                if response_id is not None:
                    invalid_adjoint_responses.add(response_id)
                elif _is_primal_field(field, primal_fields):
                    invalid_primal = True
            parse_issues.append("invalid_solver_residual_line")
            continue

        field = residual.group("field")
        initial = _finite_float(residual.group("initial"))
        final = _finite_float(residual.group("final"))
        iterations = _nonnegative_integer(residual.group("iterations"))
        if initial is None or final is None or iterations is None:
            response_id = _adjoint_response_for_field(
                field,
                mappings,
                active_response_id=active_adjoint_response,
            )
            if response_id is not None:
                invalid_adjoint_responses.add(response_id)
            elif _is_primal_field(field, primal_fields):
                invalid_primal = True
            parse_issues.append("invalid_solver_residual_line")
            continue

        row = {
            "index": residual_index,
            "field": field,
            "initial_residual": initial,
            "final_residual": final,
            "iterations": iterations,
        }
        residual_index += 1
        response_id = _adjoint_response_for_field(
            field,
            mappings,
            active_response_id=active_adjoint_response,
        )
        if response_id is not None:
            adjoint_residual_history[response_id].append(row)
        elif _is_primal_field(field, primal_fields):
            primal_rows.append(row)

    if global_residual_failure:
        invalid_primal = True
        invalid_adjoint_responses.update(adjoint_residual_history)
    return {
        "primal_residual_history": primal_rows,
        "response_history": response_history,
        "adjoint_residual_history": adjoint_residual_history,
        "continuity_error_history": continuity_rows,
        "adjoint_solver_markers": markers,
        "parse_issues": parse_issues,
        "invalid_primal": invalid_primal,
        "invalid_responses": invalid_responses,
        "invalid_adjoint_responses": invalid_adjoint_responses,
    }


def _matching_objective_line(
    line: str, objective_to_response: Mapping[str, str]
) -> tuple[str, str] | None:
    for objective_name, response_id in objective_to_response.items():
        match = re.match(
            rf"^\s*{re.escape(objective_name)}\s*:\s*(?P<value>\S+)\s*$", line
        )
        if match is not None:
            return response_id, match.group("value")
        if re.match(rf"^\s*{re.escape(objective_name)}\s*:", line):
            return response_id, ""
    return None


def _adjoint_response_for_field(
    field: str,
    mappings: Sequence[Mapping[str, str]],
    *,
    active_response_id: str | None = None,
) -> str | None:
    for mapping in mappings:
        velocity = mapping["adjoint_velocity_field"]
        suffix = velocity[2:]
        velocity_components = {velocity, f"{velocity}x", f"{velocity}y", f"{velocity}z"}
        scalar_fields = {
            f"pa{suffix}",
            f"ka{suffix}",
            f"wa{suffix}",
            f"phia{suffix}",
        }
        if field in velocity_components or field in scalar_fields:
            return mapping["response_id"]
    if active_response_id is not None and _is_unscoped_adjoint_field(field):
        return active_response_id
    return None


def _is_unscoped_adjoint_field(field: str) -> bool:
    return field in {
        "Ua",
        "Uax",
        "Uay",
        "Uaz",
        "pa",
        "ka",
        "wa",
        "phia",
    }


def _is_primal_field(field: str, primal_fields: set[str]) -> bool:
    if "U" in primal_fields and field in {"U", "Ux", "Uy", "Uz"}:
        return True
    return field in primal_fields - {"U"}


def _read_json_source(path: Path, relative_name: str) -> tuple[Any | None, dict[str, Any]]:
    payload = path.read_bytes()
    source = {
        "status": "found",
        "path": relative_name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    try:
        return json.loads(payload.decode("utf-8")), source
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _invalid_source(source)


def _missing_source(relative_name: str) -> dict[str, Any]:
    return {"status": "missing", "path": relative_name}


def _invalid_source(source: Mapping[str, Any]) -> dict[str, Any]:
    return {**source, "status": "invalid"}


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def _safe_field(value: Any) -> bool:
    return isinstance(value, str) and _FIELD_PATTERN.fullmatch(value) is not None


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _finite_float(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if isfinite(number) else None


def _nonnegative_integer(value: str) -> int | None:
    if not re.fullmatch(r"\d+", value):
        return None
    return int(value)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = [
    "OPENFOAM_FLOW_CASE_EVIDENCE_SCHEMA_VERSION",
    "extract_openfoam_flow_case_evidence",
    "write_openfoam_flow_case_evidence",
]
