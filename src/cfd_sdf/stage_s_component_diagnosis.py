"""Work F D4.1 derivative-component audit (solver-free, explanatory only).

Parses the full ``volumetricBSplines`` design-variable derivative tables
(all component columns, not only ``total``), contracts every column with the
registered direction vectors over the active variable space, and records the
per-row component closure, cancellation index and FD residual. The
single-component-drop and single-scalar hypotheses are explanatory diagnostics
only: they never modify the registered verdict, thresholds or directions.

The OpenFOAM v2512 ``shapeDesignVariables`` writer defines
``total = dxdbVol + dxdbSurf + dSdb + dndb + dxdbDirect + dVdb``; the remaining
columns (``distance``, ``options``, ``dvdb``) are independent solver outputs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

DERIVATIVE_HEADER_COLUMNS: tuple[str, ...] = (
    "#varID",
    "total",
    "dxdbVol",
    "dxdbSurf",
    "dSdb",
    "dndb",
    "dxdbDirect",
    "dVdb",
    "distance",
    "options",
    "dvdb",
)
TOTAL_COLUMN = "total"
COMPONENT_COLUMNS: tuple[str, ...] = (
    "dxdbVol",
    "dxdbSurf",
    "dSdb",
    "dndb",
    "dxdbDirect",
    "dVdb",
)
AUXILIARY_COLUMNS: tuple[str, ...] = ("distance", "options", "dvdb")
DERIVATIVE_SUM_FORMULA = "total = " + " + ".join(COMPONENT_COLUMNS)
CLOSURE_ABSOLUTE_TOLERANCE = 1.0e-7
RELATIVE_GATE = 0.05
SCALE_FLOOR = 1.0e-30


class ComponentDiagnosisError(ValueError):
    """Fail-closed component-audit contract violation."""


@dataclass(frozen=True)
class DerivativeTable:
    """One fully parsed solver-specific design-variable derivative table."""

    path: str
    sha256: str
    solver: str
    final_iteration: int
    var_ids: tuple[int, ...]
    columns: dict[str, tuple[float, ...]]

    def column(self, name: str) -> np.ndarray:
        return np.asarray(self.columns[name], dtype=np.float64)


def _final_iteration(name: str, solver: str) -> int:
    if solver not in name:
        raise ComponentDiagnosisError(
            f"derivative file {name!r} does not name the expected solver {solver!r}"
        )
    digits = "".join(character for character in name.split("ESI")[-1] if character.isdigit())
    if not digits:
        raise ComponentDiagnosisError(f"derivative file {name!r} does not encode its final iteration")
    return int(digits)


def parse_derivative_table(path: str | Path, *, expected_solver: str) -> DerivativeTable:
    """Parse every column of a derivative table fail-closed."""

    source = Path(path)
    lines = [
        line
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    if not lines or tuple(lines[0].split()) != DERIVATIVE_HEADER_COLUMNS:
        raise ComponentDiagnosisError(f"derivative file {source.name!r} has an unexpected header")
    values = np.asarray([[float(part) for part in line.split()] for line in lines[1:]], dtype=np.float64)
    if values.size == 0 or not np.isfinite(values).all():
        raise ComponentDiagnosisError(f"derivative file {source.name!r} is empty or non-finite")
    var_ids = tuple(int(value) for value in values[:, 0])
    columns = {
        name: tuple(float(value) for value in values[:, index])
        for index, name in enumerate(DERIVATIVE_HEADER_COLUMNS)
        if index > 0
    }
    return DerivativeTable(
        path=str(source),
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        solver=expected_solver,
        final_iteration=_final_iteration(source.name, expected_solver),
        var_ids=var_ids,
        columns=columns,
    )


def order_columns(table: DerivativeTable, active_ids: tuple[int, ...]) -> dict[str, np.ndarray]:
    """Reorder every column onto the registered active-variable order."""

    if len(set(table.var_ids)) != len(table.var_ids):
        raise ComponentDiagnosisError(f"{table.path}: duplicate varIDs")
    if set(table.var_ids) != set(active_ids):
        missing = sorted(set(active_ids) - set(table.var_ids))[:5]
        extra = sorted(set(table.var_ids) - set(active_ids))[:5]
        raise ComponentDiagnosisError(
            f"{table.path}: varID set does not match the active set; "
            f"missing={missing}, extra={extra}"
        )
    position = {var_id: index for index, var_id in enumerate(table.var_ids)}
    order = np.asarray([position[var_id] for var_id in active_ids], dtype=np.int64)
    return {name: table.column(name)[order] for name in table.columns}


def contract_columns(
    ordered: dict[str, np.ndarray], direction: np.ndarray
) -> dict[str, float]:
    """Contract every ordered column with one direction vector."""

    values = np.asarray(direction, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ComponentDiagnosisError("direction contains non-finite values")
    size = next(iter(ordered.values())).size
    if values.size != size:
        raise ComponentDiagnosisError(
            f"direction size {values.size} does not match the column size {size}"
        )
    return {name: float(column @ values) for name, column in ordered.items()}


def component_closure(record: dict[str, float]) -> float:
    return float(record[TOTAL_COLUMN]) - float(sum(record[name] for name in COMPONENT_COLUMNS))


def cancellation_index(record: dict[str, float], *, floor: float) -> float:
    numerator = float(sum(abs(record[name]) for name in COMPONENT_COLUMNS))
    denominator = max(abs(float(record[TOTAL_COLUMN])), float(floor), SCALE_FLOOR)
    return numerator / denominator


def relative_gate(analytic: float, fd: float) -> tuple[float | None, bool, bool]:
    """The registered relative rule: ratio, within-gate and sign agreement."""

    if abs(float(analytic)) <= SCALE_FLOOR:
        return None, False, False
    ratio = float(fd) / float(analytic)
    within = abs(ratio - 1.0) <= RELATIVE_GATE
    sign_agreement = (float(fd) > 0.0) == (float(analytic) > 0.0)
    return ratio, bool(within and sign_agreement), bool(sign_agreement)


def drop_component_hypothesis(
    rows: Iterable[dict[str, Any]], dropped: str
) -> dict[str, Any]:
    """Re-evaluate every row with one component removed (explanation only)."""

    total_rows = 0
    passing = 0
    improved = 0
    worsened_controls = 0
    unresolved = 0
    relative_errors: list[float] = []
    failing_rows: list[dict[str, Any]] = []
    worsened_rows: list[dict[str, Any]] = []
    for row in rows:
        total_rows += 1
        reduced = float(row["d_total"]) - float(row[f"d_{dropped}"])
        if abs(reduced) <= float(row["noise_floor"]):
            unresolved += 1
            failing_rows.append({"row": row["row_id"], "reason": "near_zero_reduced_derivative"})
            continue
        ratio = float(row["fd"]) / reduced
        within = bool(abs(ratio - 1.0) <= RELATIVE_GATE)
        error = abs(ratio - 1.0)
        relative_errors.append(error)
        baseline_within = bool(row["within_gate"])
        if within:
            passing += 1
            if not baseline_within:
                improved += 1
        else:
            failing_rows.append(
                {
                    "row": row["row_id"],
                    "ratio": ratio,
                    "relative_error": error,
                    "baseline_within_gate": baseline_within,
                }
            )
            if baseline_within:
                worsened_controls += 1
                worsened_rows.append(row["row_id"])
    explains = bool(
        total_rows > 0
        and passing == total_rows
        and worsened_controls == 0
        and unresolved == 0
    )
    return {
        "dropped_component": dropped,
        "n_rows": total_rows,
        "n_passing_after_drop": passing,
        "n_improved_from_baseline": improved,
        "n_worsened_controls": worsened_controls,
        "n_unresolved_near_zero": unresolved,
        "max_relative_error_after_drop": max(relative_errors) if relative_errors else None,
        "explains_all_directions": explains,
        "failing_rows": failing_rows,
        "worsened_rows": worsened_rows,
        "note": "post-hoc explanation only; not a production correction or qualification",
    }


def fitted_scale(analytics: np.ndarray, fds: np.ndarray) -> float:
    """Least-squares common scalar fd ~ s * analytic (explanation only)."""

    a = np.asarray(analytics, dtype=np.float64)
    f = np.asarray(fds, dtype=np.float64)
    denominator = float(a @ a)
    if denominator <= SCALE_FLOOR:
        raise ComponentDiagnosisError("cannot fit a scale on a zero analytic vector")
    return float(a @ f / denominator)


def single_scalar_hypothesis(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One common scale for every row of one scheme (explanation only)."""

    records = list(rows)
    analytics = np.asarray([row["d_total"] for row in records], dtype=np.float64)
    fds = np.asarray([row["fd"] for row in records], dtype=np.float64)
    if analytics.size == 0:
        raise ComponentDiagnosisError("no rows for the single-scalar hypothesis")
    scale = fitted_scale(analytics, fds)
    scaled = scale * analytics
    errors = [abs(float(fd) / float(value) - 1.0) for fd, value in zip(fds, scaled, strict=True)]
    within = [
        bool(error <= RELATIVE_GATE and (fd > 0.0) == (value > 0.0))
        for error, fd, value in zip(errors, fds, scaled, strict=True)
    ]
    return {
        "fitted_scale": scale,
        "n_rows": len(records),
        "n_passing_with_scale": int(sum(within)),
        "max_relative_error_with_scale": max(errors) if errors else None,
        "explains_all_directions": bool(all(within)),
        "note": "post-hoc fit is explanatory only and is never a production correction",
    }


def holdout_seed(manifest_sha256: str, index: int) -> int:
    """Deterministic holdout seed derived from the registered manifest hash."""

    if index < 1:
        raise ComponentDiagnosisError("holdout seed indices start at 1")
    digest = hashlib.sha256(f"{manifest_sha256}:holdout:seed:{index}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "AUXILIARY_COLUMNS",
    "CLOSURE_ABSOLUTE_TOLERANCE",
    "COMPONENT_COLUMNS",
    "ComponentDiagnosisError",
    "DERIVATIVE_HEADER_COLUMNS",
    "DERIVATIVE_SUM_FORMULA",
    "DerivativeTable",
    "RELATIVE_GATE",
    "cancellation_index",
    "component_closure",
    "contract_columns",
    "drop_component_hypothesis",
    "fitted_scale",
    "holdout_seed",
    "load_json",
    "order_columns",
    "parse_derivative_table",
    "relative_gate",
    "single_scalar_hypothesis",
]
