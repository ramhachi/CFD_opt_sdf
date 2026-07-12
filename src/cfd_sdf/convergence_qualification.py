"""Fail-closed numerical convergence qualification for compiled flow cases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any

from .solver_case_manifest import SolverCaseManifest, SolverFlowCasePlan


CONVERGENCE_QUALIFICATION_SCHEMA_VERSION = 1
_FATAL_LOG_PATTERNS = (
    "FOAM FATAL",
    "Segmentation fault",
    "inconsistent patch and patchField types",
    "MPI_ABORT",
)
_FPE_FAILURE_PATTERN = re.compile(
    r"\b(?:floating point exception|foam_sigfpe|sigfpe)\b", flags=re.IGNORECASE
)
_TRAP_FPE_STARTUP_PATTERN = re.compile(
    r"^\s*trapFpe:\s+floating point exception trapping enabled\s+"
    r"\(foam_sigfpe\)\.\s*$",
    flags=re.IGNORECASE,
)


def evaluate_openfoam_convergence_bundle(
    manifest: SolverCaseManifest,
    evidence_by_flow_case: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate every manifest flow independently; only numerical evidence can pass."""

    unknown = sorted(set(evidence_by_flow_case) - {p.flow_case_id for p in manifest.flow_cases})
    if unknown:
        raise ValueError(f"Unknown convergence evidence flow_case IDs: {unknown!r}")
    flow_results: dict[str, Any] = {}
    for plan in manifest.flow_cases:
        evidence = evidence_by_flow_case.get(plan.flow_case_id)
        flow_results[plan.flow_case_id] = _evaluate_flow_case(plan, evidence)
    statuses = [result["status"] for result in flow_results.values()]
    if not manifest.compile_ready:
        status = "fail"
    elif statuses and all(status == "pass" for status in statuses):
        status = "pass"
    elif any(status == "fail" for status in statuses):
        status = "fail"
    else:
        status = "not_evaluated"
    return {
        "schema_version": CONVERGENCE_QUALIFICATION_SCHEMA_VERSION,
        "kind": "openfoam_convergence_qualification",
        "problem_id": manifest.problem_id,
        "problem_spec_sha256": manifest.problem_spec_sha256,
        "solver_profile": manifest.solver_profile,
        "manifest_compile_ready": manifest.compile_ready,
        "manifest_unsupported": [
            *manifest.unsupported,
            *(reason for plan in manifest.flow_cases for reason in plan.unsupported),
        ],
        "status": status,
        "qualified": status == "pass",
        "flow_cases": flow_results,
    }


def write_openfoam_convergence_qualification(
    result: Mapping[str, Any], path: str | Path
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            _json_copy(result),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return target


def _evaluate_flow_case(
    plan: SolverFlowCasePlan, evidence: Any
) -> dict[str, Any]:
    criteria = dict(plan.requested["convergence_criteria"])
    if evidence is None:
        return {
            "status": "not_evaluated",
            "qualified": False,
            "criteria": criteria,
            "gates": {},
            "reasons": ["missing_flow_case_evidence"],
        }
    if not isinstance(evidence, Mapping):
        return _failed_flow(criteria, "flow_case_evidence_must_be_mapping")

    gates = {
        "solver_completion": _completion_gate(evidence.get("solver_log")),
        "primal_final_residual": _residual_gate(
            evidence.get("primal_residual_history"),
            float(criteria["primal_final_residual_max"]),
        ),
        "normalized_mass_imbalance": _mass_gate(
            evidence.get("normalized_mass_imbalance_history"),
            float(criteria["normalized_mass_imbalance_max"]),
        ),
        "response_stationarity": _stationarity_gate(
            evidence.get("response_history"),
            plan.supported_response_ids,
            int(criteria["response_stationarity_window"]),
            float(criteria["response_relative_range_max"]),
        ),
        "adjoint_final_residual": _adjoint_gate(
            evidence.get("adjoint_residual_history"),
            plan.supported_response_ids,
            float(criteria["adjoint_final_residual_max"]),
        ),
    }
    extractor_completeness = _extractor_completeness_gate(evidence)
    if extractor_completeness is not None:
        gates["evidence_extraction"] = extractor_completeness
    failed = [name for name, gate in gates.items() if gate["status"] != "pass"]
    return {
        "status": "fail" if failed else "pass",
        "qualified": not failed,
        "criteria": criteria,
        "gates": gates,
        "reasons": [f"gate_failed:{name}" for name in failed],
    }


def _failed_flow(criteria: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "qualified": False,
        "criteria": dict(criteria),
        "gates": {},
        "reasons": [reason],
    }


def _completion_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return _gate_fail("missing_solver_log")
    fatal = _fatal_log_patterns(value)
    end_marker = any(line.strip() == "End" for line in value.splitlines())
    if fatal:
        return _gate_fail("fatal_solver_log_pattern", fatal_patterns=fatal)
    if not end_marker:
        return _gate_fail("missing_solver_end_marker")
    return {"status": "pass", "end_marker": True, "fatal_patterns": []}


def _fatal_log_patterns(value: str) -> list[str]:
    lower = value.lower()
    fatal = [pattern for pattern in _FATAL_LOG_PATTERNS if pattern.lower() in lower]
    for line in value.splitlines():
        if _TRAP_FPE_STARTUP_PATTERN.fullmatch(line):
            continue
        if _FPE_FAILURE_PATTERN.search(line):
            fatal.append("Floating point exception")
            break
    return fatal


def _extractor_completeness_gate(
    evidence: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Honor explicit incompleteness from the OpenFOAM evidence extractor.

    Historical evidence fixtures contain only the five numerical categories and
    therefore omit both markers.  They remain valid inputs.  Once an extractor
    explicitly reports an incomplete result, however, its parsed histories
    cannot be used to qualify a flow case selectively.
    """

    complete = evidence.get("complete")
    status = evidence.get("status")
    if complete is not False and status != "incomplete":
        return None

    return _gate_fail(
        "extractor_evidence_incomplete",
        extractor_complete=complete,
        extractor_status=status,
    )


def _residual_gate(value: Any, maximum: float) -> dict[str, Any]:
    latest, reason = _latest_residuals(value)
    if reason is not None:
        return _gate_fail(reason, threshold=maximum)
    observed = max(latest.values())
    return {
        "status": "pass" if observed <= maximum else "fail",
        "threshold": maximum,
        "observed_max": observed,
        "latest_by_field": latest,
    }


def _mass_gate(value: Any, maximum: float) -> dict[str, Any]:
    values, reason = _finite_series(value)
    if reason is not None:
        return _gate_fail(reason, threshold=maximum)
    observed = abs(values[-1])
    return {
        "status": "pass" if observed <= maximum else "fail",
        "threshold": maximum,
        "observed_final_abs": observed,
    }


def _stationarity_gate(
    value: Any,
    response_ids: Sequence[str],
    window: int,
    maximum: float,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _gate_fail("missing_response_history", window=window, threshold=maximum)
    results: dict[str, Any] = {}
    for response_id in response_ids:
        values, reason = _finite_series(value.get(response_id))
        if reason is not None or len(values) < window:
            results[response_id] = {
                "status": "fail",
                "reason": reason or "insufficient_stationarity_window",
                "available_values": len(values),
            }
            continue
        tail = values[-window:]
        scale = max(abs(number) for number in tail)
        relative_range = 0.0 if scale == 0.0 else (max(tail) - min(tail)) / scale
        results[response_id] = {
            "status": "pass" if relative_range <= maximum else "fail",
            "relative_range": relative_range,
            "available_values": len(values),
        }
    passed = bool(response_ids) and all(
        result["status"] == "pass" for result in results.values()
    )
    return {
        "status": "pass" if passed else "fail",
        "window": window,
        "threshold": maximum,
        "responses": results,
    }


def _adjoint_gate(
    value: Any, response_ids: Sequence[str], maximum: float
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _gate_fail("missing_adjoint_residual_history", threshold=maximum)
    results: dict[str, Any] = {}
    for response_id in response_ids:
        latest, reason = _latest_residuals(value.get(response_id))
        if reason is not None:
            results[response_id] = {"status": "fail", "reason": reason}
            continue
        observed = max(latest.values())
        results[response_id] = {
            "status": "pass" if observed <= maximum else "fail",
            "observed_max": observed,
            "latest_by_field": latest,
        }
    passed = bool(response_ids) and all(
        result["status"] == "pass" for result in results.values()
    )
    return {
        "status": "pass" if passed else "fail",
        "threshold": maximum,
        "responses": results,
    }


def _latest_residuals(value: Any) -> tuple[dict[str, float], str | None]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return {}, "missing_residual_history"
    latest: dict[str, float] = {}
    for row in value:
        if not isinstance(row, Mapping) or not isinstance(row.get("field"), str):
            return {}, "invalid_residual_history_row"
        residual = row.get("final_residual")
        if isinstance(residual, bool) or not isinstance(residual, (int, float)):
            return {}, "invalid_residual_history_row"
        number = float(residual)
        if not isfinite(number) or number < 0.0:
            return {}, "invalid_residual_history_row"
        latest[str(row["field"])] = number
    return latest, None


def _finite_series(value: Any) -> tuple[list[float], str | None]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return [], "missing_numeric_history"
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return [], "invalid_numeric_history"
        number = float(item)
        if not isfinite(number):
            return [], "invalid_numeric_history"
        result.append(number)
    return result, None


def _gate_fail(reason: str, **details: Any) -> dict[str, Any]:
    return {"status": "fail", "reason": reason, **details}


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value


__all__ = [
    "CONVERGENCE_QUALIFICATION_SCHEMA_VERSION",
    "evaluate_openfoam_convergence_bundle",
    "write_openfoam_convergence_qualification",
]
