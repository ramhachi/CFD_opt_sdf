#!/usr/bin/env python3
"""Pressure-only sectional downforce from user-supplied independent readings.

The CSV abscissa must be global streamwise X divided by a declared chord,
not a local inclined chord coordinate. See reports/cp_digitised_format.md.
This tool estimates digitization sensitivity; it never qualifies TR-00.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import math
from pathlib import Path


# TOPO-2D-00 draft §2: use the SAME reference length for E1/E2/E3 differences.
REFERENCE_CHORD_M = 0.2234
COMBINED_CHORD_M = 0.380  # Registration §2: second, published ride-height normalization.
SIGN = "downforce=-Fz"
_COVERAGE_TOL = 1e-10  # dimensionless x/c, tolerance for text representation only
_COMMON = {"config", "method", "height_m", "height_mapping_note", "source"}


def _fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    if set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f"missing or unknown fields: expected {sorted(required)}, got {sorted(value)}")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f"{name} has an invalid sign")
    return float(value)


def _csv_input(path, columns):
    payload = Path(path).read_bytes()
    reader = csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
    try:
        if next(reader, None) != list(columns):
            raise ValueError(f"{path}: required CSV header is {','.join(columns)}")
        points = []
        for line, row in enumerate(reader, 2):
            if len(row) != 2:
                raise ValueError(f"{path}:{line}: expected exactly two columns")
            pair = tuple(float(v) for v in row)
            if not all(math.isfinite(v) for v in pair):
                raise ValueError(f"{path}:{line}: nonfinite value")
            points.append(pair)
    except (csv.Error, UnicodeError) as exc:
        raise ValueError(f"{path}: invalid CSV") from exc
    # Registration Amendment 1 §6: >=10 points per physical Cp surface. A
    # Cl(h/c) curve is not a surface; linear interpolation still needs >=2.
    minimum = 10 if tuple(columns) == ("x/c", "Cp") else 2
    if len(points) < minimum:
        raise ValueError(f"{path}: at least {minimum} points are required")
    if all(b[0] < a[0] for a, b in zip(points, points[1:])):
        points.reverse()
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError(f"{path}: abscissa must be strictly monotone without duplicates")
    return points, {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(), "points": len(points)}


def read_csv(path, columns=("x/c", "Cp")):
    """Read finite monotone data: >=10 Cp points, >=2 curve points; reverse descending."""
    return _csv_input(path, columns)[0]


def _integrate_points(upper, lower, abscissa_chord_m, reference_chord_m, x_extent):
    scale = _number(abscissa_chord_m, "abscissa_chord_m", positive=True) / _number(
        reference_chord_m, "reference_chord_m", positive=True)
    if not isinstance(x_extent, list) or len(x_extent) != 2:
        raise ValueError("x_extent must contain two complete-contour endpoints")
    start, end = (_number(v, "x_extent") for v in x_extent)
    if end <= start:
        raise ValueError("x_extent must increase")
    for surface in (upper, lower):
        if not (math.isclose(surface[0][0], start, rel_tol=0, abs_tol=_COVERAGE_TOL)
                and math.isclose(surface[-1][0], end, rel_tol=0, abs_tol=_COVERAGE_TOL)):
            raise ValueError("surface coverage does not match declared complete-contour x_extent")
    # Global +z is upward. Pressure gives Fz/q = ∫lower Cp dX − ∫upper Cp dX.
    # Upper/lower may use DIFFERENT interior x samples; no interpolation needed.
    def trapezoid(points):
        return math.fsum((b[0] - a[0]) * (0.5 * a[1] + 0.5 * b[1])
                         for a, b in zip(points, points[1:]))
    return _number((trapezoid(upper) - trapezoid(lower)) * scale, "integrated Cl")


def integrate_cp(upper_csv, lower_csv, *, abscissa_chord_m, reference_chord_m, x_extent):
    """Return positive-downward pressure Cl on declared global-x contours."""
    return _integrate_points(read_csv(upper_csv), read_csv(lower_csv),
                             abscissa_chord_m, reference_chord_m, x_extent)


def _digitizers(config):
    pair = config["digitizers"]
    if not isinstance(pair, list) or len(pair) != 2:
        raise ValueError("exactly two independent digitizers are required")
    for who in pair:
        _fields(who, {"id", "operator", "tool"})
        for key in ("id", "operator", "tool"):
            _text(who[key], key)
    if pair[0]["id"] == pair[1]["id"] or (pair[0]["operator"], pair[0]["tool"]) == (pair[1]["operator"], pair[1]["tool"]):
        raise ValueError("two distinct digitizers (different person or tool) are required")
    _text(config["independence_note"], "independence_note")
    return [who["id"] for who in pair]


def _input(base, value, columns=("x/c", "Cp")):
    relative = _text(value, "CSV path")
    rows, record = _csv_input(base / relative, columns)
    record["path"] = relative
    return rows, record


def _pair_summary(values):
    return _number(math.fsum(v / 2 for v in values), "mean Cl"), _number(abs(values[1] - values[0]), "digitization sensitivity")


def _cp(config, base, chord):
    _fields(config, _COMMON | {"abscissa_direction", "independence_note", "digitizers", "elements"})
    if config["abscissa_direction"] != "global_streamwise":
        raise ValueError("Cp requires global_streamwise x, not an inclined local-chord abscissa")
    ids = _digitizers(config)
    if not isinstance(config["elements"], list) or not 1 <= len(config["elements"]) <= 3:
        raise ValueError("one to three pressure elements are required")
    elements, seen = [], set()
    for element in config["elements"]:
        _fields(element, {"id", "abscissa_chord_m", "x_extent", "coverage_note", "surfaces"})
        element_id = _text(element["id"], "element id")
        if element_id in seen:
            raise ValueError("duplicate pressure element id")
        seen.add(element_id)
        _text(element["coverage_note"], "coverage_note")
        _fields(element["surfaces"], set(ids))
        digitizations = []
        for who in ids:
            surfaces = element["surfaces"][who]
            _fields(surfaces, {"upper", "lower"})
            upper, up_input = _input(base, surfaces["upper"])
            lower, lo_input = _input(base, surfaces["lower"])
            value = _integrate_points(upper, lower, element["abscissa_chord_m"], chord, element["x_extent"])
            if value <= 0:
                raise ValueError(f"{element_id}/{who}: integrated Cl must be downforce-positive; check physical upper/lower surface labels")
            digitizations.append({"id": who, "Cl": value, "upper": up_input, "lower": lo_input})
        for surface in ("upper", "lower"):
            if digitizations[0][surface]["sha256"] == digitizations[1][surface]["sha256"]:
                raise ValueError(f"{element_id}: {surface} digitizations must have different CSV SHA-256 contents")
        value, sensitivity = _pair_summary([d["Cl"] for d in digitizations])
        elements.append({"id": element_id, "Cl": value, "digitization_sensitivity_abs": sensitivity,
                         "abscissa_chord_m": element["abscissa_chord_m"], "x_extent": element["x_extent"],
                         "coverage_note": element["coverage_note"], "digitizations": digitizations})
    totals = [_number(math.fsum(e["digitizations"][i]["Cl"] for e in elements), "total Cl") for i in range(2)]
    value, paired_difference = _pair_summary(totals)
    sensitivity = _number(math.fsum(e["digitization_sensitivity_abs"] for e in elements), "total sensitivity")
    return {"Cl": value, "digitization_sensitivity_abs": sensitivity, "paired_total_difference_abs": paired_difference,
            "elements": elements, "digitizers": config["digitizers"], "independence_note": config["independence_note"],
            "uncertainty_method": "sum_of_absolute_element_pair_differences"}


def _coefficient_scale(config, chord):
    if config["coefficient_sign"] != SIGN:
        raise ValueError(f"source coefficient_sign must be {SIGN}")
    return _number(config["coefficient_chord_m"], "coefficient_chord_m", positive=True) / chord


def _tabulated(config, chord):
    _fields(config, _COMMON | {"Cl", "coefficient_chord_m", "coefficient_sign", "reading_sensitivity_abs", "reading_sensitivity_note"})
    scale = _coefficient_scale(config, chord)
    _text(config["reading_sensitivity_note"], "reading_sensitivity_note")
    return {"Cl": _number(_number(config["Cl"], "Cl") * scale, "normalized Cl"),
            "digitization_sensitivity_abs": _number(_number(config["reading_sensitivity_abs"], "reading_sensitivity_abs", nonnegative=True) * scale, "normalized reading sensitivity"),
            "source_Cl": config["Cl"], "coefficient_chord_m": config["coefficient_chord_m"],
            "reading_sensitivity_note": config["reading_sensitivity_note"], "uncertainty_method": "explicit_table_reading_sensitivity"}


def _curve(config, base, chord):
    _fields(config, _COMMON | {"coefficient_chord_m", "coefficient_sign", "height_chord_m", "digitizers", "independence_note", "curves"})
    ids = _digitizers(config)
    _fields(config["curves"], set(ids))
    scale = _coefficient_scale(config, chord)
    target = config["height_m"] / _number(config["height_chord_m"], "height_chord_m", positive=True)
    digits = []
    for who in ids:
        points, inp = _input(base, config["curves"][who], ("h/c", "Cl"))
        if not points[0][0] <= target <= points[-1][0]:
            raise ValueError("Cl(h/c) reference would require extrapolation")
        i = min(max(bisect.bisect_left([p[0] for p in points], target), 1), len(points) - 1)
        (x0, y0), (x1, y1) = points[i - 1:i + 1]
        fraction = (target - x0) / (x1 - x0)
        digits.append({"id": who, "Cl": _number(((1 - fraction) * y0 + fraction * y1) * scale, "interpolated Cl"), "input": inp})
    if digits[0]["input"]["sha256"] == digits[1]["input"]["sha256"]:
        raise ValueError("Cl(h/c) digitizations must have different CSV SHA-256 contents")
    value, sensitivity = _pair_summary([d["Cl"] for d in digits])
    return {"Cl": value, "digitization_sensitivity_abs": sensitivity, "digitizations": digits,
            "digitizers": config["digitizers"], "independence_note": config["independence_note"],
            "coefficient_chord_m": config["coefficient_chord_m"], "height_chord_m": config["height_chord_m"],
            "target_h_over_c": target, "uncertainty_method": "absolute_curve_pair_difference"}


def build_reference(manifest_path):
    """Validate a user manifest and return common-c1 pressure reference estimates."""
    manifest_path = Path(manifest_path).resolve()
    payload = manifest_path.read_bytes()
    manifest = json.loads(payload)
    _fields(manifest, {"kind", "reference_chord_m", "configs", "increments"})
    if manifest["kind"] != "topo2d00_cp_manifest_v1":
        raise ValueError("unknown Cp manifest kind")
    chord = _number(manifest["reference_chord_m"], "reference_chord_m", positive=True)
    if not math.isclose(chord, REFERENCE_CHORD_M, rel_tol=0, abs_tol=1e-12):
        raise ValueError("TR-00 output requires the common c1=0.2234 m reference chord")
    if not isinstance(manifest["configs"], list) or not manifest["configs"]:
        raise ValueError("configs must be a nonempty list")
    references = []
    for config in manifest["configs"]:
        if not isinstance(config, dict) or _COMMON - set(config):
            raise ValueError("missing reference config fields")
        name = _text(config["config"], "config")
        _number(config["height_m"], "height_m", positive=True)
        _text(config["height_mapping_note"], "height_mapping_note")
        source = config["source"]
        if not isinstance(source, dict) or {"citation", "location", "observable", "transition"} - set(source):
            raise ValueError("source requires citation, location, observable and transition provenance")
        for field in ("citation", "location", "transition"):
            _text(source[field], field)
        if source["observable"] != "centre_section_pressure_integrated":
            raise ValueError("source must be centre_section_pressure_integrated, not balance CL")
        method = config["method"]
        if method == "cp":
            estimate = _cp(config, manifest_path.parent, chord)
        elif method == "tabulated_cl":
            estimate = _tabulated(config, chord)
        elif method == "cl_curve":
            estimate = _curve(config, manifest_path.parent, chord)
        else:
            raise ValueError("unknown reference method")
        references.append({"config": name, "method": method, "observable": "pressure_cl",
                           "height_m": config["height_m"], "h_over_c1": config["height_m"] / chord,
                           "h_over_c": config["height_m"] / COMBINED_CHORD_M,
                           "height_mapping_note": config["height_mapping_note"], "source": source, **estimate,
                           "uncertainty": {"digitization_sensitivity_abs": estimate["digitization_sensitivity_abs"],
                                           "total_reference_abs": None, "covers_total_reference": False,
                                           "interpretation": "Reading sensitivity only; not a confidence interval or total experimental/integration error"}})
    by_name = {r["config"]: r for r in references}
    if len(by_name) != len(references):
        raise ValueError("duplicate reference config")
    if not isinstance(manifest["increments"], list):
        raise ValueError("increments must be a list")
    increments, seen = [], set()
    for request in manifest["increments"]:
        _fields(request, {"from", "to"})
        names = (request["from"], request["to"])
        if any(not isinstance(n, str) or n not in by_name for n in names) or names[0] == names[1] or names in seen:
            raise ValueError("unknown, duplicate or self-referencing increment")
        seen.add(names)
        a, b = (by_name[n] for n in names)
        if a["height_m"] != b["height_m"]:
            raise ValueError("increment references must declare the same physical height")
        delta = _number(b["Cl"] - a["Cl"], "reference increment")
        # Registration §4 / Amendment 1 §6: compare the double-element reading
        # uncertainty against 5% of the increment, retaining E1 separately.
        sensitivity = b["digitization_sensitivity_abs"]
        difference_sensitivity = _number(a["digitization_sensitivity_abs"] + sensitivity, "difference reading sensitivity")
        increments.append({**request, "delta_Cl": delta, "digitization_sensitivity_abs": sensitivity,
                           "from_digitization_sensitivity_abs": a["digitization_sensitivity_abs"],
                           "to_digitization_sensitivity_abs": sensitivity,
                           "reference_difference_reading_sensitivity_abs": difference_sensitivity,
                           "threshold_uncertainty_basis": "to_reference_digitization_sensitivity_abs",
                           "digitization_fraction_of_increment": sensitivity / abs(delta) if delta else None,
                           "digitization_exceeds_5_percent": sensitivity > 0.05 * abs(delta) if delta else None,
                           "threshold_fraction": 0.05,  # TOPO-2D-00 draft §4, never tuned here
                           "zero_increment": delta == 0, "total_reference_uncertainty_known": False,
                           "qualification_decided": False})
    result = {"kind": "topo2d00_pressure_reference_v1", "evidence_class": "reference_estimate",
              "observable": "pressure_cl",
              "normalization": {"reference_chord_m": chord, "sign": SIGN,
                                "observable": "pressure_only_centre_section_Cl",
                                "abscissa_direction": "global_streamwise", "surfaces": "physical_upper_lower"},
              "manifest": {"path": str(manifest_path), "sha256": hashlib.sha256(payload).hexdigest()},
              "references": references, "increments": increments, "qualification_decided": False}
    # Reject nonfinite arithmetic and nonfinite values hidden in extra source metadata.
    json.dumps(result, allow_nan=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_reference(args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
