"""Host-side artifact and physical-force reconstruction for FD-08 v2 rounds."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


FORCE_COLUMNS = (
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver",
    "downforce_solver", "pressure_fx_solver", "pressure_fy_solver",
    "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver",
    "viscous_fz_solver",
)


def read_force_history(path: Path) -> list[dict[str, float]]:
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FORCE_COLUMNS:
            raise ValueError(f"force CSV schema mismatch: {path}")
        rows = [{key: float(row[key]) for key in FORCE_COLUMNS} for row in reader]
    if len(rows) < 4 or any(not math.isfinite(value) for row in rows for value in row.values()):
        raise ValueError(f"force CSV empty or nonfinite: {path}")
    if any(right["step"] <= left["step"] or right["t_u_l"] <= left["t_u_l"]
           for left, right in zip(rows, rows[1:])):
        raise ValueError(f"force CSV step/time is not strictly increasing: {path}")
    return rows


def _at(rows: list[dict[str, float]], time: float) -> dict[str, float]:
    for row in rows:
        if row["t_u_l"] == time:
            return dict(row)
    for left, right in zip(rows, rows[1:]):
        if left["t_u_l"] < time < right["t_u_l"]:
            alpha = (time - left["t_u_l"]) / (right["t_u_l"] - left["t_u_l"])
            return {key: time if key == "t_u_l" else left[key] + alpha * (right[key] - left[key])
                    for key in FORCE_COLUMNS}
    raise ValueError(f"raw force history does not bracket time {time}")


def clipped_window(rows: list[dict[str, float]], start: float, end: float) -> list[dict[str, float]]:
    if rows[0]["t_u_l"] > start or rows[-1]["t_u_l"] < end:
        raise ValueError(f"raw force history does not bracket [{start},{end}]")
    return [_at(rows, start), *[row for row in rows if start < row["t_u_l"] < end], _at(rows, end)]


def time_weighted_mean(rows: list[dict[str, float]], column: str) -> float:
    duration = 0.0
    total = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        duration += dt
        total += 0.5 * (left[column] + right[column]) * dt
    if duration <= 0:
        raise ValueError("force measurement window has no positive duration")
    return total / duration


def recompute_force_n(path: Path, criteria: dict[str, Any]) -> dict[str, Any]:
    rows = read_force_history(path)
    measurement = criteria["measurement"]
    case = measurement["case"]
    start, end = measurement["time_window_t_u_l"]
    window = clipped_window(rows, float(start), float(end))
    scale = (case["density_kg_m3"] * case["freestream_mps"][0] ** 2
             * case["flow_spacing_m"] ** 2)
    means = {quantity: time_weighted_mean(window, column)
             for quantity, column in (("drag", "drag_solver"), ("downforce", "downforce_solver"))}
    force_n = {f"{quantity}_n": float(mean * scale) for quantity, mean in means.items()}
    components_ok = all(
        math.isclose(row["drag_solver"], row["fx_solver"], rel_tol=1e-6, abs_tol=1e-8)
        and math.isclose(row["downforce_solver"], -row["fz_solver"], rel_tol=1e-6, abs_tol=1e-8)
        and all(math.isclose(row[f"{axis}_solver"],
                             row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"],
                             rel_tol=1e-6, abs_tol=1e-8)
                for axis in ("fx", "fy", "fz"))
        for row in rows
    )
    if not components_ok:
        raise ValueError("force component and projection identities failed")
    return {
        **force_n,
        "solver_force_means": means,
        "force_scale_n_per_solver_force": scale,
        "window_t_u_l": [float(start), float(end)],
        "raw_sample_count": len(rows),
        "host_component_identities_passed": components_ok,
    }


def response_pair(
    plus_path: Path,
    minus_path: Path,
    criteria: dict[str, Any],
) -> dict[str, dict[str, float]]:
    plus, minus = recompute_force_n(plus_path, criteria), recompute_force_n(minus_path, criteria)
    result = {}
    for quantity in ("drag", "downforce"):
        r_plus = plus[f"{quantity}_n"]
        r_minus = minus[f"{quantity}_n"]
        result[quantity] = {
            "response_n": (r_plus - r_minus) / 2.0,
            "response_from_plus_n": r_plus,
            "response_from_minus_n": r_minus,
        }
    return result
