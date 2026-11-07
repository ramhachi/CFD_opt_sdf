#!/usr/bin/env python3
"""TOPO-2D-00 draft arithmetic and fail-closed, written-once analysis.

``analyze_input`` accepts the design memo's normalized tables for synthetic tests.
The CLI additionally re-verifies raw harness outputs and all frozen input/source
hashes. No registration, solver execution, or qualification flag is produced here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from scipy.stats import t

REPO = Path(__file__).resolve().parents[2]
CONFIGS = ("E1", "E2", "E3")
RCONFIGS = CONFIGS + ("E1_sharp", "E2_sharp")
READOUTS = ("cur", "nds", "cv")
RESPONSES = ("downforce", "drag")
REYNOLDS = (1000, 3000)
# Registration Amendment 3 section 3 orders cell states, independently of
# the study's ordered scientific labels (which have no MESH_FAILED label).
CELL_SEVERITY = {"SETTLED": 0, "NUMERICAL": 1, "MESH_FAILED": 2, "INCOMPLETE": 3}
SHA = re.compile(r"[0-9a-f]{64}\Z")
LIMITATIONS = [
    "No physical, grid-independent, FSAE or 3D qualification is implied.",
    "Concordance is judged per Re under registration Amendment 7: downforce 12/23 are required on both sides, and 13 is also required if W or any qualified R cell is non-monotone; only jointly resolved pairs determine ordering. Re states combine under Amendment 5.",
    "RETENTION_12 uses delta-method relative-increment variances followed by Fieller; it is not an exact nested-ratio interval.",
    "The uncertainty model treats placement phases and equal-duration batches as sampling units; iid adequacy requires registration review.",
    "The confirmation grid re-thickens at its own 4dx; its contrast includes geometry and grid changes.",
    "Thickening-alone differences need the same observable on sharp and thick arms; the primary pressure/total arms cannot be subtracted.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value, name="number"):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"{name} must be finite")
    return float(value)


def is_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def validate_input(data):
    require(isinstance(data, dict) and data.get("schema") == "topo2d00-input-v1", "unknown normalized input schema")
    for key in ("identity_valid", "cap_hit"):
        require(type(data.get(key)) is bool, f"{key} must be a declared boolean")
    require(isinstance(data.get("controls"), dict), "controls must be an object")
    require(data["controls"].get("primary_readout", "cur") in READOUTS, "unknown primary readout")
    require(isinstance(data.get("waterlily"), list), "waterlily must be an array")
    seen = set()
    for row in data["waterlily"]:
        require(isinstance(row, dict), "WaterLily row must be an object")
        require(row.get("configuration") in CONFIGS, "unknown WaterLily configuration")
        require(row.get("reynolds") in REYNOLDS, "unknown WaterLily Reynolds number")
        require(row.get("grid") in ("main", "confirmation"), "unknown WaterLily grid")
        require(row.get("role") in ("primary", "confirmation", "secondary", "domain", "determinism"), "unknown WaterLily role")
        require(finite(row.get("height_mm"), "height_mm") > 0, "positive height required")
        require(row.get("observable") == "total_cl", "WaterLily observable must be total_cl")
        for name, chord in (("h_over_c1", 223.4), ("h_over_c", 380.0)):
            if name in row:
                require(math.isclose(finite(row[name], name), row["height_mm"] / chord, rel_tol=1e-12), f"inconsistent {name}")
        require(isinstance(row.get("phase"), (str, int)) and not isinstance(row.get("phase"), bool) and str(row["phase"]), "phase identity missing")
        require(is_sha(row.get("scene_sha256")), "scene SHA missing or invalid")
        for key in ("ok", "finite", "complete"):
            require(type(row.get(key)) is bool, f"WaterLily {key} status missing")
        identity = tuple(str(row[k]) for k in ("configuration", "height_mm", "reynolds", "grid", "phase", "role"))
        require(identity not in seen, "duplicate WaterLily phase identity")
        seen.add(identity)
        require(isinstance(row.get("readouts"), dict) and set(row["readouts"]) == set(READOUTS), "readout availability must be explicit")
        for name, value in row["readouts"].items():
            if value is None:
                continue
            require(isinstance(value, dict), f"{name} readout must be an object or null")
            require(value.get("observable") == row["observable"], "WaterLily readout observable differs from row; cannot difference across observables")
            for response in RESPONSES:
                finite(value.get(response), f"{name} {response}")
            batches = value.get("batches")
            require(isinstance(batches, list) and len(batches) >= 4, "at least 4 equal-duration batch means required")
            for batch in batches:
                require(isinstance(batch, dict), "batch must be an object")
                for response in RESPONSES:
                    finite(batch.get(response), f"{name} batch {response}")
            for response in RESPONSES:
                whole = value[response]
                batch_mean = math.fsum(batch[response] for batch in batches) / len(batches)
                require(abs(whole - batch_mean) <= 1e-9 * max(1, abs(whole), abs(batch_mean)),
                        f"{name} {response} whole mean differs from equal-duration batch mean")
        if "force_csv_sha256" in row:
            require(is_sha(row["force_csv_sha256"]), "invalid raw force CSV SHA")
    rans = data.get("rans")
    require(isinstance(rans, dict) and rans.get("schema") == "topo2d00-rans-results-v1", "unknown RANS schema")
    reference = rans.get("coefficient_reference", {})
    require(reference.get("chord_mm") == 223.4, "RANS coefficients must use common c1 = 223.4 mm")
    require(reference.get("height_mm") == 100, "RANS primary height must be 100 mm")
    for name, chord in (("h_over_c1", 223.4), ("h_over_c", 380.0)):
        require(math.isclose(finite(reference.get(name), name), 100 / chord, rel_tol=1e-12), f"inconsistent RANS {name}")
    if "units" in reference:
        require(reference["units"] == "dimensionless", "RANS force coefficients must be dimensionless")
    ref = rans.get("reference", {})
    require(ref.get("observable") == "pressure_cl", "TR-00 reference observable must be pressure_cl")
    require(finite(ref.get("delta_cl"), "reference delta_cl") != 0, "reference increment must be nonzero")
    require(finite(ref.get("digitizing_uncertainty"), "digitizing uncertainty") >= 0, "negative digitizing uncertainty")
    require(isinstance(rans.get("cells"), list) and bool(rans["cells"]), "RANS model/family matrix missing")
    cells = set()
    for cell in rans["cells"]:
        for key in ("model", "family"):
            require(isinstance(cell.get(key), str) and cell[key] and "/" not in cell[key], f"invalid RANS {key}")
        name = cell_id(cell)
        require(name not in cells, "duplicate RANS model/family cell")
        cells.add(name)
        rows = cell.get("realisations")
        require(isinstance(rows, list) and len(rows) == 8, "each RANS cell needs exactly 8 realisations")
        ids = set()
        for row in rows:
            require(isinstance(row.get("id"), str) and row["id"] and row["id"] not in ids, "duplicate or missing RANS realisation id")
            ids.add(row["id"])
            for field in ("status", "mesh_sha256", "forces"):
                require(isinstance(row.get(field), dict) and set(row[field]) == set(RCONFIGS), f"RANS {field} must cover exactly E1/E2/E3 and E1_sharp/E2_sharp")
            for config in RCONFIGS:
                status = row["status"][config]
                require(status in ("SETTLED", "NUMERICAL", "INCOMPLETE", "MESH_FAILED"), "unknown RANS status")
                mesh = row["mesh_sha256"][config]
                require(is_sha(mesh) or (status != "SETTLED" and mesh is None), "RANS mesh SHA missing")
                force = row["forces"][config]
                if force is not None:
                    observable = "pressure_cl" if config.endswith("_sharp") else "total_cl"
                    require(isinstance(force, dict) and force.get("observable") == observable, f"RANS {config} observable must be {observable}; cannot difference across observables")
                if status == "SETTLED":
                    require(isinstance(force, dict), "settled RANS force missing")
                    for response in RESPONSES:
                        finite(force.get(response), f"RANS {response}")
                else:
                    require(force is None or (isinstance(force, dict) and all(math.isfinite(finite(force.get(q))) for q in RESPONSES)), "failed RANS force must be null or finite diagnostics")


def cell_id(cell):
    return cell["model"] + "/" + cell["family"]


def worst_cell_state(states):
    return max(states, key=CELL_SEVERITY.__getitem__, default="SETTLED")


def rstat(values):
    x = np.asarray(values, dtype=float)
    require(x.ndim == 1 and len(x) >= 2 and np.isfinite(x).all(), "at least two finite samples required")
    n = len(x)
    mean, sd = float(x.mean()), float(x.std(ddof=1))
    se = sd / math.sqrt(n)
    margin = float(t.ppf(0.95, n - 1)) * se
    return {"n": n, "mean": mean, "sd": sd, "se": se, "df": n - 1, "ci90": [mean - margin, mean + margin]}


def batch_variance(row, readout, response):
    values = np.asarray([b[response] for b in row["readouts"][readout]["batches"]], dtype=float)
    var = float(values.var(ddof=1)) / len(values)
    return var


def wstat(base, candidate, readout="cur", response="downforce"):
    require(len(base) == len(candidate) and len(base) >= 2, "paired phases required")
    require(all(r.get("observable") == "total_cl" and r["readouts"][readout].get("observable") == "total_cl" for r in [*base, *candidate]),
            "cannot difference across observables")
    p = len(base)
    b = np.asarray([r["readouts"][readout][response] for r in base])
    c = np.asarray([r["readouts"][readout][response] for r in candidate])
    d = c - b
    a = float(d.std(ddof=1))
    vb = [batch_variance(r, readout, response) for r in base]
    vc = [batch_variance(r, readout, response) for r in candidate]
    sigma_b = math.sqrt(float(np.mean(np.asarray(vb) + vc)))
    # Amendment 5: point sigma only, with B in paired-phase SD units.
    se = max(a, sigma_b) / math.sqrt(p)
    mean = float(d.mean())
    margin = float(t.ppf(0.95, p - 1)) * se
    return {"n": p, "mean": mean, "sigma_a": a, "sigma_b": sigma_b, "sigma": max(a, sigma_b),
            "se": se, "df": p - 1, "ci90": [mean - margin, mean + margin]}


def fieller(numerator, denominator, variance_num, variance_den, covariance=0.0, df=7):
    """Confidence set for a ratio of approximately normal estimates (90%).

    Infinity is serialized as null. The relative increments supplied by this
    study already use a delta approximation; this is not an exact nested ratio.
    """
    values = [finite(v) for v in (numerator, denominator, variance_num, variance_den, covariance)]
    n, d, vn, vd, cov = values
    require(vn >= 0 and vd >= 0, "invalid Fieller variance/covariance")
    if vn == 0 or vd == 0:
        require(cov == 0, "invalid Fieller variance/covariance")
    else:
        # Dimensionless PSD check avoids squared-product under/overflow. This
        # is the 64-epsilon relative squared-PSD bound without an absolute floor.
        correlation = (abs(cov) / math.sqrt(vn)) / math.sqrt(vd)
        limit = 1 / math.sqrt(1 - 64 * np.finfo(float).eps)
        require(correlation <= limit, "invalid Fieller variance/covariance")
    require(isinstance(df, (int, float)) and df > 0, "positive Fieller degrees of freedom required")
    q = float(t.ppf(0.95, df)) ** 2
    a, b, c = d * d - q * vd, -2 * (n * d - q * cov), n * n - q * vn
    scale = 64 * np.finfo(float).eps
    atol = scale * max(abs(d * d), abs(q * vd), 1e-300)
    btol = scale * max(2 * abs(n * d), 2 * abs(q * cov), 1e-300)
    ctol = scale * max(abs(n * n), abs(q * vn), 1e-300)
    if abs(a) <= atol:
        if abs(b) <= btol:
            return {"kind": "all_real" if c <= ctol else "empty", "intervals": [[None, None]] if c <= ctol else []}
        root = -c / b
        return {"kind": "half_line", "intervals": [[None, root]] if b > 0 else [[root, None]]}
    discriminant = b * b - 4 * a * c
    dtol = scale * max(b * b, abs(4 * a * c), 1e-300)
    if discriminant < -dtol:
        return {"kind": "all_real" if a < 0 else "empty", "intervals": [[None, None]] if a < 0 else []}
    root = math.sqrt(max(discriminant, 0.0))
    # Cancellation-safe quadratic roots (important for a narrow ratio interval).
    qr = -0.5 * (b + math.copysign(root, b))
    roots = sorted([qr / a, c / qr] if qr else [-b / (2 * a)] * 2)
    if a > 0:
        return {"kind": "bounded", "intervals": [[roots[0], roots[-1]]]}
    if discriminant <= dtol:
        return {"kind": "all_real", "intervals": [[None, None]]}
    return {"kind": "disjoint", "intervals": [[None, roots[0]], [roots[-1], None]]}


def sign(interval):
    return 1 if interval[0] > 0 else -1 if interval[1] < 0 else 0


def zvalue(mean, se):
    return abs(mean) / se if se else (0.0 if mean == 0 else None)


def rarrays(cell, config, response):
    return np.asarray([r["forces"][config][response] for r in cell["realisations"]], dtype=float)


def rans_diagnostics(rans):
    """Mesh repeats remain point diagnostics, never independent realizations."""
    result = {}
    for cell in rans["cells"]:
        result[cell_id(cell)] = {}
        for config in RCONFIGS:
            rows = cell["realisations"]
            hashes = [r["mesh_sha256"][config] for r in rows if r["mesh_sha256"][config] is not None]
            values = [r["forces"][config] for r in rows if r["forces"][config] is not None]
            duplicate = len(hashes) == 8 and len(set(hashes)) < 8
            states = {r["status"][config] for r in rows}
            state = worst_cell_state(states)
            status = ("INCOMPLETE" if state == "INCOMPLETE" else "DEGENERATE_REALISATIONS" if duplicate else
                      state if state != "SETTLED" else
                      "COMPLETE" if len(hashes) == 8 else "INCOMPLETE")
            result[cell_id(cell)][config] = {
                "status": status,
                "distinct_meshes": len(set(hashes)), "measured_realisations": len(values),
                "point_estimate": {q: float(np.mean([v[q] for v in values])) for q in RESPONSES} if values else None,
                "ci90": None,
            }
    return result


def thickening_diagnostics(cell):
    """Descriptive, same-observable contrasts from WP5's raw diagnostics.

    Collector summaries are deliberately not arithmetic inputs. ``usable`` is
    the native arm's flag, so the auxiliary observable must additionally pass
    its own convergence state. Duplicate meshes can retain points, never CIs.
    """
    result = {}
    for config in CONFIGS:
        sharp = config + "_sharp"
        if sharp not in RCONFIGS:
            result[config] = {"status": "UNAVAILABLE_SHARP_ARM", "observables": {}}
            continue
        result[config] = {"from": sharp, "to": config, "observables": {}}
        for observable, field, convergence in (("pressure_cl", "pressure_coefficients", "pressure_convergence"),
                                                ("total_cl", "coefficients", "convergence")):
            differences = []
            for row in cell["realisations"]:
                pair = []
                for arm in (sharp, config):
                    raw = row.get("diagnostics", {}).get(arm, {})
                    values = raw.get(field, {}).get("total")
                    ready = (raw.get("usable") is True and raw.get("status") == "COMPLETED"
                             and raw.get(convergence, {}).get("state") == "settled"
                             and row["status"][arm] in ("SETTLED", "INCOMPLETE"))
                    if not ready or not isinstance(values, dict) or not all(isinstance(values.get(q), (int, float)) and not isinstance(values[q], bool) and math.isfinite(values[q]) for q in ("Cl", "Cd")):
                        break
                    require(raw.get("config") == arm and raw.get("model") == cell["model"] and raw.get("family") == cell["family"]
                            and raw.get("mesh_msh_sha256") == row["mesh_sha256"][arm], "auxiliary RANS config/model/family/mesh identity differs")
                    pair.append(values)
                if len(pair) == 2:
                    differences.append({q: pair[1][key] - pair[0][key] for q, key in (("downforce", "Cl"), ("drag", "Cd"))})
            rows = cell["realisations"]
            distinct = all(len({r["mesh_sha256"][arm] for r in rows}) == 8 and all(r["mesh_sha256"][arm] is not None for r in rows) for arm in (sharp, config))
            settled = all(r["status"][arm] == "SETTLED" for r in rows for arm in (sharp, config))
            complete = len(differences) == 8 and distinct and settled
            result[config]["observables"][observable] = {
                "observable": observable, "status": "DESCRIPTIVE" if complete else "POINT_ONLY" if differences else "UNAVAILABLE",
                "paired_realisations": len(differences),
                "point_estimate": {q: float(np.mean([d[q] for d in differences])) for q in RESPONSES} if differences else None,
                "ci90": {q: rstat([d[q] for d in differences])["ci90"] for q in RESPONSES} if complete else None,
            }
    return result


def reference_from_records(rans, bundle):
    """Recompute WP5's canonical digitize_cp manifest from frozen raw CSVs.

    The upstream format is ``topo2d00_cp_manifest_v1`` and the manifest pointer
    is WP5's existing ``provenance.reference_estimate.manifest``. No derived
    ``Cl`` in reference_estimate is trusted. The independent checker parses the
    same raw records without importing this implementation or the WP5 reader.
    """
    require(isinstance(bundle, dict) and isinstance(bundle.get("sha256"), dict), "frozen reference inputs missing")
    hashes = bundle["sha256"]
    require(hashes and all(Path(path).is_absolute() and is_sha(digest) for path, digest in hashes.items()), "reference paths/SHA invalid")
    for path, digest in hashes.items():
        require(Path(path).is_file() and sha256(path) == digest, "reference input SHA mismatch: " + path)
    estimate = rans.get("provenance", {}).get("reference_estimate", {})
    require(estimate.get("kind") == "topo2d00_pressure_reference_v1" and estimate.get("observable") == "pressure_cl", "canonical WP5 reference estimate missing")
    descriptor = estimate.get("manifest", {})
    manifest_path = Path(bundle.get("manifest", "")).resolve()
    require(descriptor.get("path") == str(manifest_path) and hashes.get(str(manifest_path)) == descriptor.get("sha256"), "reference manifest missing or not frozen")
    manifest = load_json(manifest_path)
    require(manifest.get("kind") == "topo2d00_cp_manifest_v1" and finite(manifest.get("reference_chord_m")) == .2234, "unknown reference manifest or chord")
    configs = manifest.get("configs")
    require(isinstance(configs, list) and all(isinstance(c, dict) for c in configs), "reference configs missing")
    named = {c.get("config"): c for c in configs}
    require(len(named) == len(configs) and {"E1_sharp", "E2_sharp"} <= set(named), "reference configs must uniquely cover sharp E1/E2")
    requests = manifest.get("increments")
    require(isinstance(requests, list) and sum(r == {"from": "E1_sharp", "to": "E2_sharp"} for r in requests) == 1, "reference increment request missing or duplicated")

    def points(relative, columns):
        require(isinstance(relative, str) and relative, "reference CSV path missing")
        path = (manifest_path.parent / relative).resolve()
        require(str(path) in hashes, "reference CSV missing from freeze inputs")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            require(next(reader, None) == list(columns), "reference CSV header mismatch")
            rows = []
            for row in reader:
                require(len(row) == 2, "reference CSV requires two columns")
                rows.append(tuple(finite(float(v), "reference CSV value") for v in row))
        require(len(rows) >= (10 if columns[0] == "x/c" else 2), "reference surface needs at least 10 points; curve needs two")
        if all(b[0] < a[0] for a, b in zip(rows, rows[1:])):
            rows.reverse()
        require(all(b[0] > a[0] for a, b in zip(rows, rows[1:])), "reference abscissa must be strictly monotone")
        return rows

    def readers(config):
        who = config.get("digitizers")
        require(isinstance(who, list) and len(who) == 2 and all(isinstance(w, dict) for w in who), "reference needs two independent digitizers")
        require(all(isinstance(w.get(k), str) and w[k].strip() for w in who for k in ("id", "operator", "tool")), "reference digitizer identity incomplete")
        require(who[0]["id"] != who[1]["id"] and (who[0]["operator"], who[0]["tool"]) != (who[1]["operator"], who[1]["tool"]), "reference digitizers are not independent")
        require(isinstance(config.get("independence_note"), str) and config["independence_note"].strip(), "reference independence note missing")
        return [w["id"] for w in who]

    def estimate_config(config, name):
        require(finite(config.get("height_m")) == .1 and config.get("source", {}).get("observable") == "centre_section_pressure_integrated", "reference height/observable differs")
        method = config.get("method")
        if name == "E2_sharp":
            require(method == "cp", "E2 reference requires raw Cp integration")
        if method in ("tabulated_cl", "cl_curve"):
            require(config.get("coefficient_sign") == "downforce=-Fz", "reference sign differs")
            scale = finite(config.get("coefficient_chord_m")) / .2234
            require(scale > 0, "reference coefficient chord must be positive")
            if method == "tabulated_cl":
                require(finite(config.get("reading_sensitivity_abs")) >= 0, "reference table reading sensitivity must be nonnegative")
                return finite(config.get("Cl")) * scale, 0.
            ids = readers(config)
            require(isinstance(config.get("curves"), dict) and set(config["curves"]) == set(ids), "reference curve readers differ")
            height_chord = finite(config.get("height_chord_m"))
            require(height_chord > 0, "reference height chord must be positive")
            target = .1 / height_chord
            curves = [points(config["curves"][who], ("h/c", "Cl")) for who in ids]
            require(curves[0] != curves[1], "reference curves have identical normalized numeric contents")
            values = []
            for curve in curves:
                require(curve[0][0] <= target <= curve[-1][0], "reference curve extrapolation refused")
                values.append(float(np.interp(target, [p[0] for p in curve], [p[1] for p in curve])) * scale)
            return math.fsum(values) / 2, abs(values[0] - values[1])
        require(method == "cp" and config.get("abscissa_direction") == "global_streamwise", "unknown reference method or non-global Cp abscissa")
        ids = readers(config)
        elements = config.get("elements")
        require(isinstance(elements, list) and len(elements) == (2 if name == "E2_sharp" else 1), "reference pressure element count differs")
        require(len({e.get("id") for e in elements}) == len(elements), "duplicate reference pressure element")
        means, uncertainties = [], []
        for element in elements:
            scale = finite(element.get("abscissa_chord_m")) / .2234
            require(scale > 0, "reference abscissa chord must be positive")
            extent = element.get("x_extent")
            require(isinstance(extent, list) and len(extent) == 2 and finite(extent[0]) < finite(extent[1]), "reference contour extent invalid")
            surfaces = element.get("surfaces")
            require(isinstance(surfaces, dict) and set(surfaces) == set(ids), "reference surface readers differ")
            parsed = []
            for who in ids:
                require(isinstance(surfaces[who], dict) and set(surfaces[who]) == {"upper", "lower"}, "reference needs physical upper/lower surfaces")
                parsed.append({side: points(surfaces[who][side], ("x/c", "Cp")) for side in ("upper", "lower")})
            for side in ("upper", "lower"):
                require(parsed[0][side] != parsed[1][side], "reference surfaces have identical normalized numeric contents")
            values = []
            for reading in parsed:
                integrals = {}
                for side, curve in reading.items():
                    require(all(math.isclose(curve[i][0], extent[j], rel_tol=0, abs_tol=1e-10) for i, j in ((0, 0), (-1, 1))), "reference contour coverage incomplete")
                    integrals[side] = math.fsum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(curve, curve[1:]))
                value = (integrals["upper"] - integrals["lower"]) * scale
                require(value > 0, "each reference element must be downforce-positive; surface swap refused")
                values.append(value)
            means.append(math.fsum(values) / 2)
            uncertainties.append(abs(values[0] - values[1]))
        return math.fsum(means), math.fsum(uncertainties)

    single, _ = estimate_config(named["E1_sharp"], "E1_sharp")
    double, uncertainty = estimate_config(named["E2_sharp"], "E2_sharp")
    reference = {"delta_cl": finite(double - single), "digitizing_uncertainty": finite(uncertainty)}
    require(reference["delta_cl"] != 0, "recomputed reference increment is zero")
    for key, value in reference.items():
        require(math.isclose(finite(rans["reference"].get(key)), value, rel_tol=1e-12, abs_tol=1e-12), "claimed summary differs from recomputed reference " + key)
    return reference


def tr00(rans, reference=None):
    reference = reference or {key: rans["reference"][key] for key in ("delta_cl", "digitizing_uncertainty")}
    ref = reference["delta_cl"]
    sign_only = reference["digitizing_uncertainty"] > 0.05 * abs(ref)
    result = {"cells": {}, "qualified_cells": [], "reference": reference}
    for cell in rans["cells"]:
        name = cell_id(cell)
        statuses = [r["status"][c] for r in cell["realisations"] for c in ("E1_sharp", "E2_sharp")]
        degenerate = any(len({r["mesh_sha256"][c] for r in cell["realisations"]}) < 8
                         and all(r["mesh_sha256"][c] is not None for r in cell["realisations"])
                         for c in ("E1_sharp", "E2_sharp"))
        point = (float(np.mean(rarrays(cell, "E2_sharp", "downforce") - rarrays(cell, "E1_sharp", "downforce")))
                 if all(r["forces"][c] is not None for r in cell["realisations"] for c in ("E1_sharp", "E2_sharp")) else None)
        state = worst_cell_state(statuses + (["INCOMPLETE"] if degenerate else []))
        record = {"label": state if state != "SETTLED" else "INCOMPLETE",
                  "delta": None, "ratio_ci90": None, "point_estimate": point,
                  "reason": "DEGENERATE_REALISATIONS" if degenerate else None, "observable": "pressure_cl"}
        if set(statuses) == {"SETTLED"} and not degenerate:
            stat = rstat(rarrays(cell, "E2_sharp", "downforce") - rarrays(cell, "E1_sharp", "downforce"))
            ratio = sorted(x / ref for x in stat["ci90"])
            agrees = sign(stat["ci90"]) == (1 if ref > 0 else -1)
            passed = agrees and (sign_only or (ratio[0] >= 0.5 and ratio[1] <= 2))
            label = ("TR00_PASS_SIGN" if sign_only else "TR00_PASS_RATIO") if passed else "TR00_FAIL"
            record.update(label=label, delta=stat, ratio_ci90=ratio)
            if passed:
                result["qualified_cells"].append(name)
        result["cells"][name] = record
    result["qualified_cells"].sort()
    return result


def select_runs(data, re, grid="main", role="primary", count=None, readout="cur"):
    groups = {}
    for config in CONFIGS if role == "primary" else CONFIGS[:2]:
        rows = [r for r in data["waterlily"] if r["reynolds"] == re and r["configuration"] == config
                and r["grid"] == grid and r["role"] == role and r["height_mm"] == 100]
        groups[config] = {str(r["phase"]): r for r in rows}
        if count is not None:
            require(len(rows) == count, f"{re}/{grid}/{config} requires exactly {count} phases")
        for row in rows:
            require(row["readouts"][readout] is not None, "selected force readout unavailable")
    active = CONFIGS if role == "primary" else CONFIGS[:2]
    require(all(set(groups[c]) == set(groups[active[0]]) for c in active), "paired phase sets differ")
    phases = sorted(groups[active[0]])
    return {c: [groups[c][p] for p in phases] for c in active}, phases


def relative_w(base, candidate, readout):
    p = len(base)
    b = np.asarray([r["readouts"][readout]["downforce"] for r in base])
    c = np.asarray([r["readouts"][readout]["downforce"] for r in candidate])
    if float(b.mean()) == 0:
        return None, None
    ratio = float((c - b).mean() / b.mean())
    influence = ((c - b) - ratio * b) / b.mean()
    a = float(influence.var(ddof=1)) / p
    v = sum(batch_variance(cr, readout, "downforce") + (1 + ratio) ** 2 * batch_variance(br, readout, "downforce")
            for br, cr in zip(base, candidate)) / (p * p * float(b.mean()) ** 2)
    return ratio, max(a, v)


def relative_r(cell):
    b, c = rarrays(cell, "E1", "downforce"), rarrays(cell, "E2", "downforce")
    if float(b.mean()) == 0:
        return None, None
    ratio = float((c - b).mean() / b.mean())
    return ratio, float((((c - b) - ratio * b) / b.mean()).var(ddof=1)) / len(b)


def empty_result():
    return {"schema": "topo2d00-analysis-v1", "label": None, "tr00": {"cells": {}, "qualified_cells": []},
            "waterlily": {}, "rans": {}, "agreement": {}, "resolution": {"status": "NOT_JUDGED", "downforce": None},
            "height": {"height_mm": 100.0, "h_over_c1": 100 / 223.4, "h_over_c": 100 / 380.0},
            "observables": {"waterlily": "total_cl", "rans_main": "total_cl", "tr00": "pressure_cl"},
            "rans_diagnostics": {}, "thickening_alone": {},
            "controls": {"determinism": {"judged": False, "pass": None}, "domain": {"status": "DOMAIN_NOT_JUDGED", "z": None},
                         "readout": {}, "manipulation": {}}, "limitations": list(LIMITATIONS)}


def analyze_input(data):
    validate_input(data)
    result = empty_result()
    if not data["identity_valid"]:
        result["label"] = "INVALID"
        return result
    require("reference_inputs" in data or "reference_estimate" not in data["rans"].get("provenance", {}),
            "WP5 reference provenance requires frozen reference inputs; scalar-only API is synthetic only")
    result["rans_diagnostics"] = rans_diagnostics(data["rans"])
    result["thickening_alone"] = {cell_id(c): thickening_diagnostics(c) for c in data["rans"]["cells"]}
    reference = reference_from_records(data["rans"], data["reference_inputs"]) if "reference_inputs" in data else None
    result["tr00"] = tr00(data["rans"], reference)
    qualified = [c for c in data["rans"]["cells"] if cell_id(c) in result["tr00"]["qualified_cells"]]
    if not qualified:
        result["label"] = "TR_UNQUALIFIED"
        return result
    required_w = [r for r in data["waterlily"] if r["height_mm"] == 100 and r["role"] in ("primary", "confirmation")]
    # Aggregate each RANS arm's cell state before mapping to study labels.
    # Within-cell INCOMPLETE has precedence, while an independent numerical
    # cell/run outranks a cap at study level (registration Amendment 5).
    states = [result["rans_diagnostics"][cell_id(c)][config]["status"] for c in qualified for config in CONFIGS]
    numerical = (any(state in ("MESH_FAILED", "NUMERICAL") for state in states)
                 or any(not row["finite"] for row in data["waterlily"])
                 or any(row["complete"] and not row["ok"] for row in required_w))
    incomplete = (data["cap_hit"] or any(state in ("INCOMPLETE", "DEGENERATE_REALISATIONS") for state in states)
                  or any(not row["complete"] and row["finite"] for row in required_w))
    if numerical or incomplete:
        result["label"] = "NUMERICAL" if numerical else "INCOMPLETE"
        return result
    readout = data["controls"].get("primary_readout", "cur")
    groups = {re: select_runs(data, re, count=16, readout=readout)[0] for re in REYNOLDS}
    for cell in qualified:
        name = cell_id(cell)
        result["rans"][name] = {f"{a}{b}": {q: rstat(rarrays(cell, f"E{b}", q) - rarrays(cell, f"E{a}", q)) for q in RESPONSES}
                                for a, b in ((1, 2), (2, 3), (1, 3))}
        stat = result["rans"][name]["12"]["downforce"]
        result["controls"]["manipulation"]["R/" + name] = {"z": zvalue(stat["mean"], stat["se"]), "pass": abs(stat["mean"]) > 3 * stat["se"]}
    for re in REYNOLDS:
        w = groups[re]
        estimates = {f"{a}{b}": {q: wstat(w[f"E{a}"], w[f"E{b}"], readout, q) for q in RESPONSES} for a, b in ((1, 2), (2, 3), (1, 3))}
        result["waterlily"][str(re)] = estimates
        point_deltas = [(stats["12"]["downforce"]["mean"], stats["23"]["downforce"]["mean"])
                        for stats in [estimates, *result["rans"].values()]]
        nonmonotone = any(min(a, b) < 0 < max(a, b) for a, b in point_deltas)
        required_pairs = ["12", "23", "13"] if nonmonotone else ["12", "23"]
        wr, wv = relative_w(w["E1"], w["E2"], readout)
        agreement = {"SIGN_AGREE_12": True, "RANK_AGREE": True, "DRAG_SIGN_AGREE_12": True,
                     "required_pairs": required_pairs, "cells": {}}
        for cell in qualified:
            name = cell_id(cell)
            rr, rv = relative_r(cell)
            pair_signs = {p: (sign(estimates[p]["downforce"]["ci90"]), sign(result["rans"][name][p]["downforce"]["ci90"]))
                          for p in ("12", "23", "13")}
            rank_resolved = all(all(pair_signs[p]) for p in required_pairs)
            rank_opposite = any(ws * rs == -1 for ws, rs in pair_signs.values())
            record = {"SIGN_AGREE_12": sign(estimates["12"]["downforce"]["ci90"]) != 0 and sign(estimates["12"]["downforce"]["ci90"]) == sign(result["rans"][name]["12"]["downforce"]["ci90"]),
                      "RANK_AGREE": rank_resolved and not rank_opposite,
                      "DRAG_SIGN_AGREE_12": sign(estimates["12"]["drag"]["ci90"]) != 0 and sign(estimates["12"]["drag"]["ci90"]) == sign(result["rans"][name]["12"]["drag"]["ci90"]),
                      "RETENTION_12": {"relative_w": wr, "variance_w": wv, "relative_r": rr, "variance_r": rv,
                                       "fieller": {"kind": "undefined_zero_baseline", "intervals": []} if wr is None or rr is None else fieller(wr, rr, wv, rv)}}
            agreement["cells"][name] = record
            for key in ("SIGN_AGREE_12", "RANK_AGREE", "DRAG_SIGN_AGREE_12"):
                agreement[key] = agreement[key] and record[key]
        result["agreement"][str(re)] = agreement
        required = [estimates[c]["downforce"]["ci90"] for c in required_pairs]
        required += [result["rans"][name][c]["downforce"]["ci90"] for name in result["rans"] for c in required_pairs]
        if any(sign(interval) == 0 for interval in required):
            agreement["state"] = "UNRESOLVED"
        elif not agreement["SIGN_AGREE_12"] or not agreement["RANK_AGREE"]:
            agreement["state"] = "DISCORDANT"
        else:
            agreement["state"] = "CONCORDANT"
        stat = estimates["12"]["downforce"]
        result["controls"]["manipulation"][f"W/{re}"] = {"z": zvalue(stat["mean"], stat["se"]), "pass": abs(stat["mean"]) > 3 * stat["se"]}
        result["controls"]["readout"][str(re)] = {}
        for alternative in READOUTS:
            available = all(r["readouts"][alternative] is not None for c in ("E1", "E2") for r in w[c])
            result["controls"]["readout"][str(re)][alternative] = ({q: float(np.mean([c["readouts"][alternative][q] - b["readouts"][alternative][q] for b, c in zip(w["E1"], w["E2"])])) for q in RESPONSES} if available else None)
    fine, phases = select_runs(data, 3000, "confirmation", "confirmation", 4, readout)
    main = {c: {str(r["phase"]): r for r in groups[3000][c]} for c in ("E1", "E2")}
    require(set(phases) <= set(main["E1"]), "confirmation phases must match primary phases")
    matched = {c: [main[c][p] for p in phases] for c in ("E1", "E2")}
    coarse_stat, fine_stat = wstat(matched["E1"], matched["E2"], readout), wstat(fine["E1"], fine["E2"], readout)
    differences = lambda g: np.asarray([b["readouts"][readout]["downforce"] - a["readouts"][readout]["downforce"] for a, b in zip(g["E1"], g["E2"])])
    covariance = float(np.cov(differences(fine), differences(matched), ddof=1)[0, 1]) / 4
    ratio = fieller(fine_stat["mean"], coarse_stat["mean"], fine_stat["se"] ** 2, coarse_stat["se"] ** 2, covariance, 3)
    retained = ratio["kind"] == "bounded" and ratio["intervals"][0][0] >= 0.5 and ratio["intervals"][0][1] <= 2
    resolution_limited = np.sign(fine_stat["mean"]) != np.sign(coarse_stat["mean"]) or not retained
    result["resolution"] = {"status": "RESOLUTION_LIMITED" if resolution_limited else "PASS", "downforce": {"main": coarse_stat, "confirmation": fine_stat, "ratio": ratio}}
    repeats = [r for r in data["waterlily"] if r["role"] == "determinism"]
    if repeats:
        passes = []
        for row in repeats:
            matches = [r for r in data["waterlily"] if r["role"] == "primary" and all(str(r[k]) == str(row[k]) for k in ("configuration", "height_mm", "reynolds", "grid", "phase"))]
            require(len(matches) == 1, "determinism repeat has no unique primary")
            base = matches[0]
            require(("force_csv_sha256" in row) == ("force_csv_sha256" in base), "determinism raw SHA availability differs")
            passes.append(all(r[k] for r in (row, base) for k in ("complete", "finite", "ok"))
                          and row["readouts"] == base["readouts"] and row["scene_sha256"] == base["scene_sha256"]
                          and row.get("force_csv_sha256") == base.get("force_csv_sha256"))
        result["controls"]["determinism"] = {"judged": True, "pass": all(passes)}
    domain_rows = [r for r in data["waterlily"] if r["role"] == "domain" and r["reynolds"] == 3000
                   and r["height_mm"] == 100 and r["grid"] == "main"]
    domain = {c: {str(r["phase"]): r for r in domain_rows if r["configuration"] == c} for c in ("E1", "E2")}
    dp = sorted(domain["E1"])
    # Amendment 7 makes unavailable DOMAIN measurements descriptive only.
    domain_ready = ({r["configuration"] for r in domain_rows} == {"E1", "E2"}
                    and len(dp) >= 2 and set(dp) == set(domain["E2"]) and set(dp) <= set(main["E1"])
                    and all(r["ok"] and r["finite"] and r["complete"] and r["readouts"][readout] is not None for r in domain_rows))
    if domain_ready:
        domain = {c: [domain[c][p] for p in dp] for c in ("E1", "E2")}
        native = {c: [main[c][p] for p in dp] for c in ("E1", "E2")}
        ds, ns = wstat(domain["E1"], domain["E2"], readout), wstat(native["E1"], native["E2"], readout)
        difference = abs(ds["mean"] - ns["mean"])
        pooled = math.hypot(ds["se"], ns["se"])
        result["controls"]["domain"] = {"status": "DOMAIN_SENSITIVE" if difference > 3 * pooled else "CONSISTENT", "z": zvalue(difference, pooled)}
    states = [result["agreement"][str(re)]["state"] for re in REYNOLDS]
    if resolution_limited:
        label = "RESOLUTION_LIMITED"
    elif "UNRESOLVED" in states or not all(r["pass"] for r in result["controls"]["manipulation"].values()):
        label = "UNRESOLVED"
    elif states == ["DISCORDANT", "DISCORDANT"]:
        label = "DISCORDANT"
    elif "DISCORDANT" in states:
        label = "CONCORDANT_PARTIAL"
    else:
        label = "CONCORDANT"
    result["label"] = label
    return result


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    def pairs(items):
        keys = [key for key, _ in items]
        require(len(keys) == len(set(keys)), f"duplicate JSON key in {path}")
        return dict(items)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda text: (_ for _ in ()).throw(ValueError(f"non-finite JSON constant {text}")))


def write_analysis(out, record):
    out = Path(out)
    targets = tuple(out / name for name in ("analysis.json", "analysis.md", "tr00.json", "SHA256SUMS"))
    for path in targets:
        if path.exists():
            raise FileExistsError(f"written-once analysis exists: {path}")
    payload = json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
    result = record.get("result", {})
    markdown = summary_markdown(record)
    tr_payload = json.dumps(result["tr00"], indent=2, sort_keys=True, allow_nan=False) + "\n"
    contents = [payload, markdown, tr_payload]
    contents.append("".join(hashlib.sha256(content.encode("utf-8")).hexdigest() + "  " + path.name + "\n"
                            for path, content in zip(targets, contents)))
    out.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        # Reserve every path before writing any: no silent overwrite even
        # under concurrent invocations. Roll back our own incomplete reservations.
        handles = []
        try:
            for path in targets:
                handles.append(path.open("x", encoding="utf-8"))
                created.append(path)
            for handle, content in zip(handles, contents):
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            for handle in handles:
                handle.close()
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return record


def summary_markdown(record):
    result = record.get("result", {})
    text = "# TOPO-2D-00 analysis\n\nStatus: **" + str(result.get("label", "INVALID")) + "**.\n\n"
    text += "\n".join("- " + item for item in result.get("limitations", [])) + "\n\n"
    text += "All forces below are dimensionless coefficients on c1 = 223.4 mm. Differences are candidate minus baseline; positive downforce is -Cz and positive drag is +Cx.\n\n"
    text += "## TR-00 qualification\n\n| model/family | result | sharp increment | 90% interval | ratio 90% interval |\n| --- | --- | ---: | --- | --- |\n"
    for name, cell in result.get("tr00", {}).get("cells", {}).items():
        stat = cell["delta"]
        text += f"| {name} | {cell['label']} | {stat['mean'] if stat else 'N/A'} | {stat['ci90'] if stat else 'N/A'} | {cell['ratio_ci90']} |\n"
    text += "\n## WaterLily paired estimates\n\n| Re | contrast | response | mean | sigma A | sigma B | sigma | 90% interval |\n| --- | --- | --- | ---: | ---: | ---: | ---: | --- |\n"
    for reynolds, contrasts in result.get("waterlily", {}).items():
        for contrast, responses in contrasts.items():
            for response, stat in responses.items():
                text += f"| {reynolds} | {contrast} | {response} | {stat['mean']:.10g} | {stat['sigma_a']:.8g} | {stat['sigma_b']:.8g} | {stat['sigma']:.8g} | {stat['ci90']} |\n"
    text += "\n## Qualified RANS cells and worst-case interval envelope\n\n| model/family | contrast | response | mean | 90% interval |\n| --- | --- | --- | ---: | --- |\n"
    for name, contrasts in result.get("rans", {}).items():
        for contrast, responses in contrasts.items():
            for response, stat in responses.items():
                text += f"| {name} | {contrast} | {response} | {stat['mean']:.10g} | {stat['ci90']} |\n"
    if result.get("rans"):
        text += "\nWorst-case envelopes retain every qualified model/family; they are descriptive envelopes, not pooled confidence intervals. Agreement requires every qualified cell to agree.\n\n"
        for contrast in ("12", "23", "13"):
            for response in RESPONSES:
                intervals = [cell[contrast][response]["ci90"] for cell in result["rans"].values()]
                text += f"- {contrast} {response}: [{min(i[0] for i in intervals):.10g}, {max(i[1] for i in intervals):.10g}].\n"
    text += "\n## Agreement, resolution, controls and observable diagnostics\n\n```json\n" + json.dumps({k: result.get(k) for k in ("height", "observables", "agreement", "resolution", "controls", "rans_diagnostics", "thickening_alone")}, indent=2, sort_keys=True, allow_nan=False) + "\n```\n"
    text += "\n## Provenance\n\n```json\n" + json.dumps(record.get("provenance", {}), indent=2, sort_keys=True, allow_nan=False) + "\n```\n"
    return text


def load_formal_inputs(table_paths, rans_path, freeze_path):
    """Re-run the source-bound harness verifier; a success flag is insufficient."""
    sys.path.insert(0, str(REPO / "src"))
    from cfd_harness import campaign_schema as schema
    freeze = load_json(freeze_path)
    require(freeze.get("schema") == "topo2d00-analysis-freeze-v1", "unknown analysis freeze schema")
    require(re.fullmatch(r"[0-9a-f]{40}", freeze.get("source_commit", "")) is not None, "freeze source commit missing")
    require(type(freeze.get("cap_hit")) is bool and freeze.get("primary_readout") in READOUTS and freeze.get("height_mm") == 100, "freeze analysis settings missing")
    require(isinstance(freeze.get("sources"), dict) and bool(freeze["sources"]) and isinstance(freeze.get("inputs"), dict), "freeze source/input hashes missing")
    sidecar = Path(str(freeze_path) + ".sha256")
    require(sidecar.is_file(), "analysis freeze SHA sidecar missing")
    paths = [Path(p).resolve() for p in table_paths]
    require(len(paths) == len(set(paths)), "duplicate force table")
    supplied = {str(p): schema.require_formal_table(load_json(p)) for p in paths}
    require(all(table.get("force_unit") == "N/m" for table in supplied.values()), "TOPO force tables must explicitly carry 2D physical N/m units")
    identities_valid = sidecar.read_text().strip() == sha256(freeze_path)
    errors = [] if identities_valid else ["analysis freeze SHA sidecar mismatch"]
    required_sources = {"scripts/topo2d00/analyze.py", "scripts/topo2d00/check.py", "scripts/waterlily_topo2d_job.jl", "src/cfd_gen/topo2d/geometry.py"}
    require(required_sources <= set(freeze["sources"]), "freeze omits required analyzer/checker/job/geometry source")
    for rel, expected in freeze["sources"].items():
        require(is_sha(expected) and not Path(rel).is_absolute() and ".." not in Path(rel).parts, "invalid frozen source path/hash")
        try:
            committed = subprocess.check_output(["git", "show", freeze["source_commit"] + ":" + rel], cwd=REPO, stderr=subprocess.DEVNULL)
            valid = hashlib.sha256(committed).hexdigest() == expected and (REPO / rel).is_file() and sha256(REPO / rel) == expected
        except subprocess.CalledProcessError:
            valid = False
        if not valid:
            identities_valid = False
            errors.append("source mismatch: " + rel)
    def frozen_path(path):
        require(isinstance(path, str) and bool(path), "frozen input path must be a nonempty string")
        return str((REPO / path).resolve())
    required_paths = {str(p) for p in paths} | {str(Path(rans_path).resolve())}
    bound = {frozen_path(p): digest for p, digest in freeze["inputs"].items()}
    require(len(bound) == len(freeze["inputs"]), "duplicate resolved input identity in freeze")
    require(required_paths <= set(bound), "table/RANS input missing from freeze")
    for path, expected in bound.items():
        require(is_sha(expected), "invalid frozen input SHA")
        require(Path(path).is_file(), "missing frozen input: " + path)
        if sha256(path) != expected:
            identities_valid = False
            errors.append("input mismatch: " + path)
    geometry = freeze.get("geometry_sha256")
    require(isinstance(geometry, dict) and set(geometry) == set(RCONFIGS) and all(is_sha(h) for h in geometry.values()), "study freeze must bind all five main/sharp geometry JSON hashes")
    require(set(geometry.values()) <= set(bound.values()), "frozen geometry artifacts missing from input inventory")
    from cfd_harness.scene_campaign import require_verified_geometry
    for config, digest in geometry.items():
        files = sorted(path for path, actual in bound.items() if actual == digest and Path(path).suffix == ".json")
        require(files, "frozen geometry JSON missing for " + config)
        scene = load_json(files[0])
        require(isinstance(scene, dict) and scene.get("schema") == "topo2d-scene-v1", "frozen geometry must be a scene JSON")
        # Sharp RANS arms are absent from the W campaign, so the study freeze
        # must enforce source verification here as well as at W admission.
        require_verified_geometry(scene)
    rans = load_json(rans_path)
    reference_source = rans.get("reference", {}).get("source")
    require(isinstance(reference_source, dict) and reference_source.get("observable") == "centre-section pressure-integrated Cl", "formal TR-00 needs centre-section pressure-integrated reference provenance")
    require(all(isinstance(reference_source.get(k), str) and reference_source[k].strip() for k in ("title", "url", "pages", "method")), "formal TR-00 reference source metadata incomplete")
    digitizations = reference_source.get("digitization_records")
    require(isinstance(digitizations, list) and len(digitizations) >= 2, "formal TR-00 needs two independent digitization records")
    digitization_paths = []
    for digitization in digitizations:
        require(isinstance(digitization, dict) and is_sha(digitization.get("sha256")) and isinstance(digitization.get("method"), str) and digitization["method"].strip(), "invalid TR-00 digitization record")
        path = frozen_path(digitization.get("path"))
        require(path in bound, "TR-00 digitization record missing from freeze inputs")
        digitization_paths.append(path)
        if digitization["sha256"] != bound[path]:
            identities_valid = False
            errors.append("TR-00 digitization SHA differs from frozen input: " + path)
    require(len(set(digitization_paths)) == len(digitization_paths), "TR-00 digitization records must be distinct artifacts")
    estimate = rans.get("provenance", {}).get("reference_estimate", {})
    require(isinstance(estimate, dict) and isinstance(estimate.get("manifest"), dict), "formal TR-00 reference manifest missing")
    manifest = estimate["manifest"].get("path")
    require(isinstance(manifest, str) and Path(manifest).is_absolute() and manifest in digitization_paths, "formal reference manifest must be a frozen digitization record")
    reference_inputs = {"manifest": manifest, "sha256": {p: bound[p] for p in digitization_paths}}
    reference_from_records(rans, reference_inputs)
    require(isinstance(rans.get("provenance"), dict) and isinstance(rans["provenance"].get("geometry_sha256"), dict), "formal RANS results need geometry provenance")
    if "component_by_config" in rans["provenance"]:
        components = {config: "pressure_only" if config.endswith("_sharp") else "pressure_plus_viscous" for config in RCONFIGS}
        observables = {config: "pressure_cl" if config.endswith("_sharp") else "total_cl" for config in RCONFIGS}
        require(rans["provenance"]["component_by_config"] in (components, observables), "formal RANS component_by_config conflicts with force observables")
    if rans["provenance"]["geometry_sha256"] != geometry:
        identities_valid = False
        errors.append("RANS geometry identity differs from main/sharp study geometry")
    entries = freeze.get("harness")
    require(isinstance(entries, list) and all(isinstance(e, dict) and isinstance(e.get("outputs"), list) and e["outputs"] for e in entries), "freeze harness entries/outputs missing")
    require(len(entries) == len(supplied) and {frozen_path(e["table"]) for e in entries} == set(supplied), "freeze harness entries do not cover exactly the tables")
    normalized, numerical_failures, skipped_numerical = [], [], []
    cap_receipts, unmeasured_cap = [], []
    cap_hit = freeze["cap_hit"]
    for entry in entries:
        table_path = frozen_path(entry["table"])
        table = supplied[table_path]
        for key in ("campaign", "freeze"):
            require(frozen_path(entry[key]) in bound, f"harness {key} missing from freeze inputs")
        # Scene verifier is a separate harness boundary. It re-reads manifests,
        # histories and scene SHA, and rejects CPU smoke as formal evidence.
        from cfd_harness import scene_campaign
        verified = False
        try:
            actual = scene_campaign.verify(frozen_path(entry["campaign"]), [frozen_path(p) for p in entry["outputs"]],
                                           frozen_path(entry["freeze"]), smoke=False, repo=REPO,
                                           source_commit=freeze["source_commit"])
            verified = True
        except ValueError as exc:
            identities_valid = False
            errors.append("raw harness verification failed: " + str(exc))
            actual = table
        if actual != table:
            identities_valid = False
            errors.append("reverified force table differs: " + table_path)
        if table.get("source_commit") != freeze["source_commit"]:
            identities_valid = False
            errors.append("force-table source commit differs from study freeze")
        if not verified:
            # Claimed failure/skip flags are not normalized as scientific inputs
            # after raw admission failed. Identity-invalid data ends INVALID.
            continue
        require(type(actual.get("cap_hit", False)) is bool and isinstance(actual.get("cap_receipts", {}), dict), "verified cap transport malformed")
        receipts = actual.get("cap_receipts", {})
        require(actual.get("cap_hit", False) == bool(receipts), "verified cap flag and receipts disagree")
        for kernel, receipt in receipts.items():
            require(isinstance(receipt, dict) and is_sha(receipt.get("sha256")) and isinstance(receipt.get("record"), dict), "verified cap receipt malformed")
            cap_receipts.append({"table": table_path, "kernel": kernel, **receipt})
            affected = [row for run, row in actual["state_forces_n"][kernel].items()
                        if row.get("status") in ("INCOMPLETE_TIMEOUT", "UNRUN_CAP") or run == receipt["record"].get("state")]
            # Preserve study-wide/required caps. A DOMAIN-only timeout or
            # overrun is retained in provenance but cannot block the study.
            cap_hit = cap_hit or not (affected and all(row.get("topo2d", {}).get("role") == "domain" for row in affected))
        for kernel, runs in actual["state_forces_n"].items():
            for run, row in runs.items():
                topo = row.get("topo2d")
                require(isinstance(topo, dict), "force table has no TOPO identity")
                identity = {"kernel": kernel, "run": run, "topo2d": topo, "scene_sha256": row["scene_sha256"]}
                if topo.get("role") == "primary" and topo.get("height_mm") == 100 and row.get("scene_sha256") != geometry.get(topo.get("configuration")):
                    identities_valid = False
                    errors.append("WaterLily primary geometry differs from RANS main geometry")
                if row.get("status") in ("INCOMPLETE_TIMEOUT", "UNRUN_CAP"):
                    require(kernel in receipts and row.get("cap_receipt_sha256") == receipts[kernel]["sha256"], "unmeasured cap row lacks authenticated receipt")
                    unmeasured_cap.append({**identity, "status": row["status"], "cap_receipt_sha256": row["cap_receipt_sha256"]})
                    continue
                if row.get("status") == "SKIPPED_NUMERICAL":
                    require(is_sha(row.get("prior_failure_sha256")), "authenticated numerical skip lacks prior failure SHA")
                    skipped_numerical.append({**identity, "prior_failure_sha256": row["prior_failure_sha256"]})
                    continue
                if row.get("status") == "NUMERICAL":
                    require(is_sha(row.get("failure_sha256")) and row["finite"] is False and row["ok"] is False and row["complete"] is False
                            and row["readouts"] == {name: None for name in READOUTS}, "authenticated numerical failure row is inconsistent")
                    numerical_failures.append({**identity, "failure_sha256": row["failure_sha256"]})
                require(row.get("observable") == "total_cl", "verified WaterLily observable must be total_cl")
                normalized.append({**topo, "observable": "total_cl", "h_over_c1": topo["height_mm"] / 223.4, "h_over_c": topo["height_mm"] / 380.0,
                                   "ok": row["ok"], "finite": row["finite"], "complete": row["complete"],
                                   "scene_sha256": row["scene_sha256"], "readouts": row["readouts"],
                                   **({"force_csv_sha256": row["forces_csv_sha256"]} if "forces_csv_sha256" in row else {})})
    data = {"schema": "topo2d00-input-v1", "identity_valid": identities_valid, "cap_hit": cap_hit,
            "waterlily": normalized, "rans": rans, "controls": {"primary_readout": freeze["primary_readout"]},
            "reference_inputs": reference_inputs}
    provenance = {"source_commit": freeze["source_commit"], "freeze_sha256": sha256(freeze_path),
                  "input_sha256": {path: sha256(path) for path in sorted(bound)}, "identity_errors": errors,
                  "sources": freeze["sources"], "numerical_failures": numerical_failures, "skipped_numerical": skipped_numerical,
                  "cap_receipts": cap_receipts, "unmeasured_cap": unmeasured_cap,
                  "evidence_class": "software_contract_no_physical_qualification"}
    return data, provenance


def run_analysis(table_paths, rans_path, freeze_path, out):
    for name in ("analysis.json", "analysis.md", "tr00.json", "SHA256SUMS"):
        if (Path(out) / name).exists():
            raise FileExistsError(f"written-once analysis exists: {Path(out) / name}")
    data, provenance = load_formal_inputs(table_paths, rans_path, freeze_path)
    return write_analysis(out, {"input": data, "result": analyze_input(data), "provenance": provenance})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", action="append", required=True, type=Path)
    parser.add_argument("--rans", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    record = run_analysis(args.table, args.rans, args.freeze, args.out)
    print(record["result"]["label"])


if __name__ == "__main__":
    main()
