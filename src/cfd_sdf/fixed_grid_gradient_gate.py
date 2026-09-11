"""Thin, fail-closed aggregation for fixed-grid gradient evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_REQUIRED_DIRECTIONS = ("sensitivity", "filtered-random")
DEFAULT_REQUIRED_EPSILONS = (3.0e-5, 1.0e-4, 3.0e-4, 1.0e-3)
DEFAULT_RATIO_MIN = 0.8
DEFAULT_RATIO_MAX = 1.2
DEFAULT_RELATIVE_ERROR_TOLERANCE = 0.10

Json = dict[str, Any]
Input = str | Path | Mapping[str, Any]


def aggregate_fixed_grid_gradient_gate(
    suite_summaries: Iterable[Input] | Input,
    *,
    required_directions: Sequence[str] = DEFAULT_REQUIRED_DIRECTIONS,
    required_epsilons: Sequence[float] = DEFAULT_REQUIRED_EPSILONS,
    problem_binding: Mapping[str, Any] | None = None,
    ratio_min: float = DEFAULT_RATIO_MIN,
    ratio_max: float = DEFAULT_RATIO_MAX,
    relative_error_tolerance: float = DEFAULT_RELATIVE_ERROR_TOLERANCE,
    noise_floor: float | None = None,
) -> Json:
    """Aggregate suite summaries into one deterministic gate report.

    A path or loaded dictionary is accepted for each suite summary.  A report
    is ``pass`` only if the requested direction x epsilon matrix is complete
    and unique, every row passes the configured numerical thresholds, primal
    convergence and referenced artifacts are present, and the problem
    binding, clipping evidence, and noise floor are bound.  Missing problem
    binding is reported as ``diagnostic_only`` when no harder failure exists.
    """
    directions = _normalise_directions(required_directions)
    epsilons = _normalise_epsilons(required_epsilons)
    config_failures = _config_failures(
        directions,
        epsilons,
        ratio_min=ratio_min,
        ratio_max=ratio_max,
        relative_error_tolerance=relative_error_tolerance,
    )

    rows: list[Json] = []
    input_failures: list[str] = []
    for index, item in enumerate(_as_sequence(suite_summaries)):
        try:
            summary, source_path = _load_input(item)
            rows.append(
                _row(
                    summary,
                    index=index,
                    source_path=source_path,
                    ratio_min=ratio_min,
                    ratio_max=ratio_max,
                    relative_error_tolerance=relative_error_tolerance,
                    noise_floor=noise_floor,
                )
            )
        except Exception as exc:  # malformed evidence must be visible
            input_failures.append(f"input[{index}]: {type(exc).__name__}: {exc}")

    coverage = _coverage(rows, directions, epsilons)
    binding = _binding(rows, problem_binding)
    failures = list(config_failures) + list(input_failures)
    objectives = sorted({str(row["objective"]) for row in rows})
    if len(objectives) > 1:
        failures.append("mixed_objectives")
    evidence_gaps: list[str] = []
    for row in rows:
        failures.extend(f"row[{row['index']}]: {item}" for item in row["failures"])
        evidence_gaps.extend(f"row[{row['index']}]: {item}" for item in row["evidence_gaps"])
    failures.extend(f"coverage: {item}" for item in coverage["failures"])
    failures.extend(binding["failures"])
    evidence_gaps.extend(binding["evidence_gaps"])

    if not rows or failures:
        status = "fail"
    elif binding["status"] != "bound":
        status = "diagnostic_only"
    elif evidence_gaps:
        status = "incomplete"
    else:
        status = "pass"

    return {
        "schema_version": 1,
        "kind": "fixed_grid_gradient_gate",
        "status": status,
        "ok": status == "pass",
        "evidence_class": "numerical",
        "objective": objectives[0] if len(objectives) == 1 else None,
        "observed_objectives": objectives,
        "problem_binding": binding["value"],
        "problem_binding_status": binding["status"],
        "requirements": {
            "required_directions": directions,
            "required_epsilons": epsilons,
            "ratio_min": float(ratio_min),
            "ratio_max": float(ratio_max),
            "relative_error_tolerance": float(relative_error_tolerance),
            "noise_floor": noise_floor,
        },
        "coverage": coverage,
        "rows": rows,
        "artifact_hashes": _all_artifact_hashes(rows),
        "failures": _unique(failures),
        "evidence_gaps": _unique(evidence_gaps),
    }


def write_fixed_grid_gradient_gate(report: Mapping[str, Any], output_path: str | Path) -> Path:
    """Write a gate report as JSON and return its absolute path."""
    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(report), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _row(
    suite: Mapping[str, Any],
    *,
    index: int,
    source_path: Path | None,
    ratio_min: float,
    ratio_max: float,
    relative_error_tolerance: float,
    noise_floor: float | None,
) -> Json:
    direction = _load_reference(
        suite.get("direction_summary_json"),
        source_path=source_path,
        inline=suite.get("direction_summary"),
    )
    validation = _validation(suite, source_path=source_path)
    objective = _text(suite.get("objective"), validation.get("objective")) or "unknown"
    mode = _text(suite.get("direction_mode"), direction.get("direction_mode")) or "unknown"
    seed = _seed(
        suite.get("perturbation_seed"),
        suite.get("seed"),
        direction.get("perturbation_seed"),
        direction.get("seed"),
        (direction.get("direction_info") or {}).get("perturbation_seed")
        if isinstance(direction.get("direction_info"), Mapping)
        else None,
    )
    direction_id = _text(suite.get("direction_id"), direction.get("direction_id"))
    direction_id = direction_id or (f"{mode}:seed={seed}" if seed is not None else mode)
    epsilon = _number(suite.get("epsilon"), direction.get("epsilon"), validation.get("epsilon"))
    failures: list[str] = []
    gaps: list[str] = []
    if mode == "unknown":
        failures.append("direction_mode_missing")
    if objective == "unknown":
        failures.append("objective_missing")
    if epsilon is None or epsilon <= 0.0:
        failures.append("epsilon_missing_or_invalid")

    numeric = _numeric(validation, ratio_min, ratio_max, relative_error_tolerance)
    failures.extend(numeric["failures"])

    convergence = _convergence(suite, source_path=source_path)
    failures.extend(convergence["failures"])

    clipping = _clipping(suite, direction)
    if not clipping["bound"]:
        gaps.append("clipping_evidence_unbound")

    threshold = _noise_threshold(noise_floor, suite, validation)
    noise = _noise(numeric, threshold)
    failures.extend(noise["failures"])
    if not noise["bound"]:
        gaps.append("noise_floor_unbound")

    artifacts = _artifacts(suite, source_path=source_path)
    for item in artifacts:
        if item["status"] != "present":
            failures.append(f"artifact_{item['status']}:{item['role']}")

    return {
        "index": index,
        "source_summary": str(source_path) if source_path else None,
        "objective": objective,
        "direction_id": direction_id,
        "direction_mode": mode,
        "direction_seed": seed,
        "epsilon": epsilon,
        "row_key": _row_key(direction_id, epsilon),
        "problem_binding": _problem_binding(suite),
        "status": "fail" if failures else ("incomplete" if gaps else "pass"),
        "numeric": numeric,
        "convergence": convergence["value"],
        "clipping": clipping,
        "noise_floor": noise,
        "artifacts": artifacts,
        "failures": _unique(failures),
        "evidence_gaps": _unique(gaps),
    }


def _numeric(validation: Mapping[str, Any], lo: float, hi: float, tolerance: float) -> Json:
    failures: list[str] = []
    fd = _number(validation.get("finite_difference_derivative"), validation.get("finite_difference"))
    adj = _number(validation.get("adjoint_directional_derivative"), validation.get("adjoint_derivative"))
    ratio = _number(validation.get("finite_difference_to_adjoint_ratio"), validation.get("ratio"))
    if ratio is None and fd is not None and adj not in (None, 0.0):
        ratio = fd / adj
    error = _number(validation.get("relative_error"), validation.get("relative_error_fraction"))
    if error is None and fd is not None and adj is not None:
        error = abs(fd - adj) / max(abs(fd), abs(adj), 1.0e-30)
    if validation.get("status") != "pass":
        failures.append("validation_status_not_pass")
    if validation.get("sign_match") is not True:
        failures.append("sign_match_missing_or_false")
    if ratio is None or not math.isfinite(ratio):
        failures.append("ratio_missing_or_non_finite")
    elif not lo <= ratio <= hi:
        failures.append("ratio_out_of_bounds")
    if error is None or not math.isfinite(error):
        failures.append("relative_error_missing_or_non_finite")
    elif error > tolerance:
        failures.append("relative_error_out_of_bounds")
    return {
        "status": "fail" if failures else "pass",
        "finite_difference_derivative": fd,
        "adjoint_directional_derivative": adj,
        "ratio": ratio,
        "relative_error": error,
        "sign_match": validation.get("sign_match") if isinstance(validation.get("sign_match"), bool) else None,
        "validation_status": validation.get("status"),
        "failures": failures,
    }


def _convergence(suite: Mapping[str, Any], *, source_path: Path | None) -> Json:
    cases: dict[str, Json] = {}
    failures: list[str] = []
    for label in ("baseline", "plus", "minus"):
        if label == "baseline":
            case = suite.get("baseline_case") or suite.get("baseline")
            path = _resolve(suite.get("baseline_primal_summary_json"), source_path)
            if case is None:
                base = _resolve(suite.get("baseline_case_dir"), source_path)
                path = (base / "fixed_grid_primal_summary.json") if base else path
        else:
            case = suite.get(f"{label}_case")
            path = None
        summary, summary_path = _case_summary(case, path, source_path)
        convergence = summary.get("convergence")
        convergence = convergence if isinstance(convergence, Mapping) else {}
        primal = convergence.get("primal_converged")
        passed = primal is True or summary.get("status") == "converged"
        cases[label] = {
            "status": summary.get("status"),
            "primal_converged": primal if isinstance(primal, bool) else None,
            "passed": passed,
            "summary_json": str(summary_path) if summary_path else None,
        }
        if not passed:
            failures.append(f"{label}_primal_not_converged")
    return {"value": cases, "failures": failures}


def _case_summary(case: Any, path: Path | None, source_path: Path | None) -> tuple[Json, Path | None]:
    if isinstance(case, Mapping):
        nested = case.get("summary")
        if isinstance(nested, Mapping):
            return dict(nested), _resolve(case.get("primal_summary_json"), source_path)
        case_path = _resolve(case.get("primal_summary_json"), source_path)
        if case_path and case_path.exists():
            return _read_json(case_path), case_path
        return dict(case), case_path
    resolved = _resolve(case, source_path) if case is not None else path
    if resolved and resolved.exists():
        return _read_json(resolved), resolved
    return {}, resolved


def _clipping(suite: Mapping[str, Any], direction: Mapping[str, Any]) -> Json:
    value = next(
        (
            item
            for item in (suite.get("clipping"), suite.get("clipping_stats"), direction.get("clipping"))
            if isinstance(item, Mapping)
        ),
        None,
    )
    if value is not None:
        count = _number(value.get("clipped_count"), value.get("clipped_cell_count"))
        fraction = _number(value.get("clipped_fraction"), value.get("fraction"))
        return {
            "bound": count is not None or fraction is not None,
            "status": _text(value.get("status")) or "bound",
            "clipped_count": int(count) if count is not None else None,
            "clipped_fraction": fraction,
            "source": "explicit",
        }
    stats = direction.get("statistics")
    requested = stats.get("requested_direction_active") if isinstance(stats, Mapping) else None
    actual = stats.get("actual_direction_active") if isinstance(stats, Mapping) else None
    before = _number(requested.get("l2")) if isinstance(requested, Mapping) else None
    after = _number(actual.get("l2")) if isinstance(actual, Mapping) else None
    if before is not None and after is not None and before > 0.0:
        return {
            "bound": False,
            "status": "inferred_from_direction_stats",
            "clipped_count": None,
            "clipped_fraction": None,
            "actual_to_requested_l2_ratio": after / before,
            "source": "direction_statistics",
        }
    return {"bound": False, "status": "unavailable", "clipped_count": None, "clipped_fraction": None, "source": None}


def _noise_threshold(
    configured: float | None,
    suite: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> float | None:
    direct = _number(suite.get("noise_floor"), validation.get("noise_floor"))
    if direct is not None and direct >= 0.0:
        return direct
    if isinstance(configured, (int, float)) and not isinstance(configured, bool):
        value = float(configured)
        return value if math.isfinite(value) and value >= 0.0 else None
    return None


def _noise(numeric: Mapping[str, Any], threshold: float | None) -> Json:
    values = [
        abs(float(numeric[key]))
        for key in ("finite_difference_derivative", "adjoint_directional_derivative")
        if isinstance(numeric.get(key), (int, float))
    ]
    signal = max(values) if values else None
    if threshold is None:
        return {"bound": False, "status": "unbound", "threshold": None, "signal": signal, "passed": None, "failures": []}
    passed = signal is not None and math.isfinite(signal) and signal > threshold
    return {
        "bound": True,
        "status": "pass" if passed else "fail",
        "threshold": threshold,
        "signal": signal,
        "passed": passed,
        "failures": [] if passed else ["below_noise_floor"],
    }


def _artifacts(suite: Mapping[str, Any], *, source_path: Path | None) -> list[Json]:
    refs: list[tuple[str, Any]] = [
        ("direction_summary_json", suite.get("direction_summary_json")),
        ("sensitivity_vti", suite.get("sensitivity_vti")),
        ("direction_vti", suite.get("direction_vti")),
    ]
    validation = suite.get("validation")
    if isinstance(validation, Mapping):
        refs.append(("validation_report_json", validation.get("report_json")))
    elif isinstance(validation, (str, Path)):
        refs.append(("validation_report_json", validation))
    for label in ("baseline", "plus", "minus"):
        case = suite.get("baseline_case" if label == "baseline" else f"{label}_case")
        if isinstance(case, Mapping):
            for key in ("primal_summary_json", "case_metadata_json", "input_density_vti", "density_vti"):
                if case.get(key) is not None:
                    refs.append((f"{label}_{key}", case[key]))
        elif label == "baseline":
            base = _resolve(suite.get("baseline_case_dir"), source_path)
            if base:
                refs.append(("baseline_primal_summary_json", base / "fixed_grid_primal_summary.json"))
    result: list[Json] = []
    seen: set[tuple[str, str | None]] = set()
    for role, value in refs:
        path = _resolve(value, source_path)
        key = role, str(path) if path else None
        if key in seen:
            continue
        seen.add(key)
        if path is None:
            status, digest = "unbound", None
        elif not path.is_file():
            status, digest = "missing", None
        else:
            status, digest = "present", _sha256(path)
        result.append({"role": role, "path": str(path) if path else None, "sha256": digest, "status": status})
    required = {"sensitivity_vti", "direction_vti", "plus_primal_summary_json", "minus_primal_summary_json"}
    present_roles = {item["role"] for item in result}
    for role in sorted(required - present_roles):
        result.append({"role": role, "path": None, "sha256": None, "status": "unbound"})
    return result


def _coverage(rows: Sequence[Mapping[str, Any]], directions: Sequence[Json], epsilons: Sequence[float]) -> Json:
    failures: list[str] = []
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["row_key"]] = counts.get(row["row_key"], 0) + 1
    duplicates = sorted(key for key, count in counts.items() if key != "None@None" and count > 1)
    if duplicates:
        failures.append("duplicate_direction_epsilon_rows")
    missing: list[Json] = []
    matched: set[int] = set()
    for direction in directions:
        for epsilon in epsilons:
            candidates = [
                (index, row)
                for index, row in enumerate(rows)
                if _matches(direction, row) and _close(epsilon, row.get("epsilon"))
            ]
            if not candidates:
                missing.append({"direction": direction["label"], "epsilon": epsilon})
            elif len(candidates) > 1:
                failures.append(f"duplicate_required_pair:{direction['label']}@{_ekey(epsilon)}")
            else:
                matched.add(candidates[0][0])
    if missing:
        failures.append("missing_required_direction_epsilon_pairs")
    unexpected = [
        {"index": index, "direction_id": row["direction_id"], "epsilon": row["epsilon"]}
        for index, row in enumerate(rows)
        if index not in matched
        and not any(_matches(direction, row) and _close(epsilon, row.get("epsilon")) for direction in directions for epsilon in epsilons)
    ]
    if unexpected:
        failures.append("unexpected_direction_epsilon_rows")
    return {
        "complete": not failures,
        "required_pair_count": len(directions) * len(epsilons),
        "observed_row_count": len(rows),
        "observed_pair_count": len(matched),
        "missing": missing,
        "duplicates": duplicates,
        "unexpected": unexpected,
        "failures": _unique(failures),
    }


def _binding(rows: Sequence[Mapping[str, Any]], provided: Mapping[str, Any] | None) -> Json:
    values = [provided] if isinstance(provided, Mapping) else []
    values.extend(row["problem_binding"] for row in rows if isinstance(row.get("problem_binding"), Mapping))
    if not values:
        return {"status": "missing", "value": None, "failures": [], "evidence_gaps": ["problem_binding_missing"]}
    value = dict(values[0])
    missing = [key for key in ("problem_id", "problem_spec_sha256", "execution_ready") if key not in value]
    if missing:
        return {"status": "incomplete", "value": value, "failures": [], "evidence_gaps": [f"problem_binding_missing:{key}" for key in missing]}
    digest = str(value["problem_spec_sha256"])
    if len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
        return {"status": "invalid", "value": value, "failures": ["problem_spec_sha256_invalid"], "evidence_gaps": []}
    if value["execution_ready"] is not True:
        return {"status": "not_execution_ready", "value": value, "failures": [], "evidence_gaps": ["problem_binding_not_execution_ready"]}
    if any(dict(other) != value for other in values[1:]):
        return {"status": "mismatch", "value": value, "failures": ["problem_binding_mismatch"], "evidence_gaps": []}
    return {"status": "bound", "value": value, "failures": [], "evidence_gaps": []}


def _normalise_directions(values: Sequence[str]) -> list[Json]:
    result: list[Json] = []
    for value in values:
        if isinstance(value, str):
            mode, seed = _direction_label(value)
            result.append({"label": value, "id": value, "mode": mode, "seed": seed})
        else:
            raise TypeError("direction requirement must be a string")
    return result


def _normalise_epsilons(values: Sequence[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        number = float(value)
        if not math.isfinite(number) or number <= 0.0:
            raise ValueError("required epsilon must be finite and positive")
        if not any(_close(number, old) for old in result):
            result.append(number)
    return result


def _config_failures(directions: Sequence[Json], epsilons: Sequence[float], *, ratio_min: float, ratio_max: float, relative_error_tolerance: float) -> list[str]:
    failures: list[str] = []
    if len({item["label"] for item in directions}) != len(directions):
        failures.append("duplicate_required_directions")
    if len(epsilons) == 0:
        failures.append("no_required_epsilons")
    if ratio_min > ratio_max or not all(math.isfinite(float(item)) for item in (ratio_min, ratio_max)):
        failures.append("ratio_bounds_invalid")
    if not math.isfinite(float(relative_error_tolerance)) or relative_error_tolerance < 0.0:
        failures.append("relative_error_tolerance_invalid")
    return failures


def _matches(requirement: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    if requirement.get("seed") is not None:
        return requirement.get("mode") == row.get("direction_mode") and requirement.get("seed") == row.get("direction_seed")
    if requirement.get("mode") == requirement.get("id"):
        return requirement.get("mode") == row.get("direction_mode")
    return requirement.get("id") == row.get("direction_id")


def _direction_label(value: str) -> tuple[str, int | None]:
    if ":seed=" in value:
        mode, raw = value.rsplit(":seed=", 1)
        return mode, _seed(raw)
    return value, None


def _load_input(value: Input) -> tuple[Json, Path | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    path = Path(value).resolve()
    return _read_json(path), path


def _load_reference(value: Any, *, source_path: Path | None, inline: Any = None) -> Json:
    if isinstance(inline, Mapping):
        return dict(inline)
    path = _resolve(value, source_path)
    return _read_json(path) if path and path.exists() else {}


def _validation(suite: Mapping[str, Any], *, source_path: Path | None) -> Json:
    value = suite.get("validation")
    if isinstance(value, Mapping):
        direct = dict(value)
        path = _resolve(value.get("report_json"), source_path)
    else:
        direct = {}
        path = _resolve(value, source_path)
    if path and path.exists():
        return {**_read_json(path), **direct}
    return direct


def _read_json(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return dict(value)


def _resolve(value: Any, source_path: Path | None) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        return None
    path = Path(value)
    if not path.is_absolute() and source_path:
        path = source_path.parent / path
    return path.resolve()


def _as_sequence(value: Iterable[Input] | Input) -> list[Input]:
    return [value] if isinstance(value, (str, Path, Mapping)) else list(value)


def _row_key(direction_id: str, epsilon: float | None) -> str:
    return f"{direction_id}@{_ekey(epsilon)}" if epsilon is not None else "None@None"


def _ekey(value: float | None) -> str:
    return "None" if value is None else format(float(value), ".17g")


def _close(left: Any, right: Any) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=1.0e-9, abs_tol=1.0e-15)
    except (TypeError, ValueError):
        return False


def _number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


def _text(*values: Any) -> str | None:
    return next((value for value in values if isinstance(value, str) and value), None)


def _seed(*values: Any) -> int | None:
    for value in values:
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def _problem_binding(summary: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = summary.get("problem_binding")
    return dict(value) if isinstance(value, Mapping) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _all_artifact_hashes(rows: Sequence[Mapping[str, Any]]) -> list[Json]:
    result: list[Json] = []
    seen: set[tuple[Any, Any]] = set()
    for row in rows:
        for item in row.get("artifacts", []):
            key = item.get("role"), item.get("path")
            if key in seen:
                continue
            seen.add(key)
            result.append(dict(item))
    return result


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))
