#!/usr/bin/env python3
"""Collect extracted WP5 RANS cases, preserving missing and nonsettling runs.

No qualification verdict is computed here. Cl is downforce, all element and
total coefficients use the SAME main-chord reference area. Raw force files are
required for completed cases; a summary alone cannot establish convergence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_t20c as TC  # noqa: E402 -- registered SIMPLE classification, unchanged
import t20_case as T  # noqa: E402 -- reference scales, no gmsh import side effect

SCHEMA = ROOT / "docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_measurement_schema.json"
SHARED_SCHEMA = SCHEMA.with_name("topo2d00_rans_result_schema.json")
VERSION = "topo2d00-rans-v1"
CONFIGS = ("E1_sharp", "E2_sharp", "E1", "E2", "E3")
STUDY_GEOMETRIES = (*CONFIGS, "E3_sharp")  # BL plan includes the unsolved E3 original.
MODELS, FAMILIES = ("sa-wf", "sst-wf"), ("fine30", "med30")
KEY_FIELDS = ("config", "model", "family", "realisation")
NORMALIZATION = {
    "reference_chord_m": T.CHORD, "extrusion_span_m": T.Z,
    # t20_foam.system_and_constant serializes Aref with .10g; preserve that
    # actual dictionary value rather than the binary multiply's extra digits.
    "reference_area_m2": float(format(T.CHORD * T.Z, ".10g")), "U_inf_m_s": T.U_INF, "rho_kg_m3": 1.0,
}
FORCE_CONVENTION = {
    "Cl": "downforce", "Cd": "drag",
    "lift_direction": [0, -1, 0], "drag_direction": [1, 0, 0],
}
INFRA_STATUSES = TC.INFRA | {"SOLVER_TIMEOUT_PARTIAL", "NOT_RUN"}
MECHANICAL_STATUSES = (TC.MECH - {"PARSE_FAILED"}) | {"MESH_FAILED"}
SOLVER_STATUSES = {"COMPLETED", "SOLVER_DIVERGED", "SOLVER_FAIL", "simpleFoam_FAILED", "simpleFoam_cont_FAILED",
                   "simpleFoam_TIMEOUT", "simpleFoam_cont_TIMEOUT", "PARSE_FAILED"}
STATUSES = INFRA_STATUSES | MECHANICAL_STATUSES | SOLVER_STATUSES
# Immutable T2-0b runner.py:371-372 (blown_up), inherited by T2-0c.
BLOWUP_ABS = 100.0
# TOPO-2D-00 registration §§2-3: common h=100 mm, c1=223.4 mm,
# combined experimental chord c=380 mm, Re_c1=4.6e5.
HEIGHT_M, COMBINED_CHORD_M, REYNOLDS_C1 = .1, .380, 460000


@lru_cache(maxsize=None)
def inherited_runner(source: Path = ROOT):
    """Load immutable T2-0b helpers without rendering or invoking its main."""
    p = source / "infra/kaggle/kernel_t20b_cpu/runner.py"
    spec = importlib.util.spec_from_file_location("wp5_t20b_helpers", p)
    module = importlib.util.module_from_spec(spec)
    module.PIN_PINS = {}
    spec.loader.exec_module(module)
    return module


_HELPER = inherited_runner()
# One policy object re-exported by t2d_foam_case and used by the driver.
# T2-0c registration §5 / analyzer.classify inherits this force_summary.
CONVERGENCE = {
    "initial_iterations": 5000, "continuation_iterations": _HELPER.CONT_ITERS,
    "max_continuations": 1, "tail_fraction": _HELPER.TAIL_FRACTION,
    "tail_min_rows": 50,  # force_summary's registered minimum tail length
    "block_iterations": _HELPER.BLOCK,
    "plateau_relative_std_limit": _HELPER.PLATEAU_REL,
    "plateau_relative_drift_limit": _HELPER.PLATEAU_REL,
    "unsteady_raw_tail_relative_std": TC.TH["unsteady"],
    "rule_source": "T2-0c: infra/kaggle/kernel_t20b_cpu/runner.py:force_summary; docs/t20c_registration_2026_10_20.md §5; analyze_t20c.classify",
}


def cl_summary(history: np.ndarray) -> dict:
    """Exact inherited Cl statistics, without unused raw Cd diagnostics.

    The registered validity rule uses Cl only. Supply Cl in the helper's
    unused Cd slot to keep zero drag from making that unrelated ratio undefined.
    """
    rows = [{"Time": float(t), "Cl": float(cl), "Cd": float(cl)} for t, cl in history[:, :2]]
    summary = inherited_runner().force_summary(rows)
    summary.pop("Cd")
    summary.pop("force_plateau")
    return summary


class HistoryUnavailable(ValueError):
    """An interrupted solver has no usable history; not an integrity failure."""


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key_of(record: dict) -> dict:
    try:
        k = {name: record[name] for name in KEY_FIELDS}
    except (KeyError, TypeError) as exc:
        raise ValueError("missing run identity") from exc
    if (k["config"] not in CONFIGS or k["model"] not in MODELS or k["family"] not in FAMILIES
            or type(k["realisation"]) is not int or k["realisation"] not in range(8)):
        raise ValueError(f"unknown run identity: {k}")
    return k


def run_id(record: dict) -> str:
    k = key_of(record)
    return f"{k['config']}__{k['model']}__{k['family']}__r{k['realisation']:02d}"


def expected_runs(stage: str = "tr00", qualified_cells=None) -> list[dict]:
    if stage not in ("tr00", "main"):
        raise ValueError(f"unknown stage: {stage}")
    cells = [(m, f) for m in MODELS for f in FAMILIES] if qualified_cells is None else list(qualified_cells)
    if not cells or len(set(cells)) != len(cells) or any(m not in MODELS or f not in FAMILIES for m, f in cells):
        raise ValueError("qualified cells must be unique known (model, family) pairs")
    configs = CONFIGS[:2] if stage == "tr00" else CONFIGS[2:]
    return [dict(config=c, model=m, family=f, realisation=i) for c in configs for m, f in cells for i in range(8)]


def _read_json(path: Path) -> dict:
    def reject(value):
        raise ValueError(f"nonfinite JSON constant in {path}: {value}")
    obj = json.loads(path.read_text(), parse_constant=reject)
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object: {path}")
    return obj


def _digest(value, label: str, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError(f"invalid {label} SHA-256")
    return value


def _input_path(folder: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"unsafe artifact path: {relative!r}")
    p = (folder / relative).resolve(strict=True)
    if not p.is_relative_to(folder.resolve()) or not p.is_file():
        raise ValueError(f"artifact escapes case directory: {relative}")
    return p


def read_history(folder: Path, files: list[dict], columns=("Time", "Cl", "Cd"), *, minimum_rows=2) -> np.ndarray:
    """Strict named-column reader of restart segments in their declared order."""
    if not isinstance(files, list) or not files:
        raise HistoryUnavailable("missing coefficient history")
    pieces, used = [], set()
    for entry in files:
        if set(entry) != {"path", "sha256"} or entry["path"] in used:
            raise ValueError("invalid or duplicate coefficient artifact")
        used.add(entry["path"])
        p = _input_path(folder, entry["path"])
        if sha256(p) != _digest(entry["sha256"], "coefficient"):
            raise ValueError(f"coefficient SHA mismatch: {p}")
        opener = gzip.open if p.suffix == ".gz" else open
        with opener(p, "rt") as fh:
            text = fh.read()
        if not any(line.strip() and not line.startswith("#") for line in text.splitlines()):
            raise HistoryUnavailable("coefficient history has no rows")
        headers = [line.lstrip("#").split() for line in text.splitlines() if line.startswith("#")]
        if not headers or not all(k in headers[-1] for k in columns):
            raise ValueError(f"coefficient header missing: {p}")
        h = headers[-1]
        a = np.loadtxt(text.splitlines(), comments="#", ndmin=2)
        if not a.size or a.shape[1] != len(h):
            raise ValueError(f"coefficient column count differs: {p}")
        pieces.append(a[:, [h.index(name) for name in columns]])
    out = np.concatenate(pieces)
    if len(out) < minimum_rows:
        raise HistoryUnavailable(f"coefficient history has fewer than {minimum_rows} rows")
    if not np.isfinite(out[:, 0]).all() or not np.all(np.diff(out[:, 0]) == 1):
        raise ValueError("coefficient SIMPLE iteration history must be contiguous, increasing, with >=2 rows")
    return out


def divergent_coefficients(folder: Path, files: dict) -> bool:
    """Even one nonfinite solver row is a result, including interrupted runs."""
    if not isinstance(files, dict):
        raise ValueError("coefficient_files must be an object")
    diverged = False
    for entries in files.values():
        try:
            history = read_history(folder, entries, minimum_rows=1)
        except HistoryUnavailable:
            continue
        # Inspect all declared artifacts even after a bad row, preserving SHA
        # and path validation instead of hiding corruption behind divergence.
        diverged |= not np.isfinite(history[:, 1:]).all() or bool(np.abs(history[:, 1:]).max() > BLOWUP_ABS)
    return diverged


def read_force_parts(folder: Path, files: list[dict]) -> dict[str, np.ndarray]:
    """v2512 forces' dimensional split (not forceCoeffs' front/rear split)."""
    names = ("Time", *(f"{kind}_{axis}" for kind in ("total", "pressure", "viscous") for axis in "xyz"))
    raw = read_history(folder, files, names)
    if np.isfinite(raw).all() and not np.allclose(raw[:, 1:4], raw[:, 4:7] + raw[:, 7:10], rtol=1e-5, atol=1e-8):
        raise ValueError("dimensional force total != pressure + viscous")
    q_area = .5 * NORMALIZATION["rho_kg_m3"] * NORMALIZATION["U_inf_m_s"]**2 * NORMALIZATION["reference_area_m2"]
    return {kind: np.column_stack((raw[:, 0], -raw[:, start+1]/q_area, raw[:, start]/q_area))
            for kind, start in (("total", 1), ("pressure", 4), ("viscous", 7))}


def convergence(history: np.ndarray, record: dict) -> dict:
    """T2-0c block plateau, then raw-tail Cl variability; no cycle label."""
    base = {"coordinate": "SIMPLE iteration (not physical time)", "raw_class": "SOLVER_FAIL", "statistics": {}}
    solver = record.get("solver", {})
    bad_log = any(solver.get(k) for k in ("nan_in_log", "sigfpe", "foam_fatal"))
    if (record["status"] == "SOLVER_DIVERGED" or bad_log or not np.isfinite(history[:, 1:]).all()
            or np.max(np.abs(history[:, 1:])) > BLOWUP_ABS):
        return {**base, "state": "diverged", "reason": "solver failure, nonfinite coefficient, or |coefficient|>100"}
    if record["status"] != "COMPLETED":
        return {**base, "state": "not_settled", "reason": record["status"]}
    cl = history[:, 1]
    # The registered relative tests are undefined at exactly zero mean.
    n = min(len(cl), max(CONVERGENCE["tail_min_rows"], math.ceil(len(cl) * CONVERGENCE["tail_fraction"])))
    if abs(float(cl[-n:].mean())) < np.finfo(float).tiny:
        return {**base, "state": "not_settled", "reason": "zero Cl mean: relative convergence rule undefined"}
    st = cl_summary(history)
    raw = TC.classify({"status": "COMPLETED", "check_mesh": {"mesh_ok": True}, "forces": st})
    return {**base, "state": "settled" if raw == "VALID" else "not_settled", "raw_class": raw,
            "statistics": st, "reason": "T2-0c block plateau and raw-tail relative Cl std <=0.005" if raw == "VALID"
            else "T2-0c raw-tail relative Cl std >0.005" if raw == "UNSTEADY" else "T2-0c Cl block plateau failed"}


def _finite_json(value):
    """Undefined diagnostic ratios stay null; force values never use this repair."""
    if isinstance(value, dict):
        return {k: _finite_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_finite_json(v) for v in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def collect_case(path: Path) -> dict:
    r = _read_json(path)
    key = key_of(r)
    if r.get("schema_version") != "topo2d00-case-v1" or r.get("id") != run_id(key):
        raise ValueError(f"case identity/schema mismatch: {path}")
    if r.get("mode") != "production":
        raise ValueError("smoke or mesh-only cases cannot be production analysis inputs")
    status = r.get("status")
    if status not in STATUSES:
        raise ValueError(f"unknown case status: {status}")
    if r.get("normalization") != NORMALIZATION or r.get("force_convention") != FORCE_CONVENTION:
        raise ValueError("force normalization/convention differs from the common c1 reference")
    if status == "COMPLETED" and r.get("convergence_policy") != CONVERGENCE:
        raise ValueError("completed run convergence policy differs from the T2-0c contract")
    geometry = _digest(r.get("geometry_sha256"), "geometry")
    mesh = _digest(r.get("mesh_msh_sha256"), "mesh", nullable=status != "COMPLETED")
    n_layers = r.get("n_layers")
    if ((n_layers is not None and (type(n_layers) is not int or n_layers < 1))
            or mesh is not None and status not in MECHANICAL_STATUSES and n_layers is None):
        raise ValueError("meshed run requires a positive integer n_layers")
    if r.get("mesh_file"):
        if sha256(_input_path(path.parent, r["mesh_file"])) != mesh:
            raise ValueError("mesh SHA mismatch")
    elif status == "COMPLETED":
        raise ValueError("completed run has no archived mesh artifact")
    expected_count = int(key["config"][1])
    elements = r.get("elements", [])
    patches = ["airfoil" if i == 0 else f"airfoil_{i+1}" for i in range(expected_count)]
    if (len(elements) != expected_count or [e.get("patch") for e in elements] != patches
            or len({e.get("name") for e in elements}) != expected_count
            or any(not isinstance(e.get("name"), str) or not e["name"] for e in elements)):
        raise ValueError("element count/names/patches differ from configuration")
    base = {**key, "status": "MESH_FAILED" if status in MECHANICAL_STATUSES else status,
            "mesh_msh_sha256": mesh, "geometry_sha256": geometry, "n_layers": n_layers,
            "observable": "pressure_cl" if key["config"].endswith("_sharp") else "total_cl",
            "coefficients": {"total": None, "elements": [{"name": e["name"], "patch": e["patch"], "Cl": None, "Cd": None} for e in elements]},
            "pressure_coefficients": {"total": None, "elements": [{"name": e["name"], "patch": e["patch"], "Cl": None, "Cd": None} for e in elements]},
            "viscous_coefficients": {"total": None, "elements": [{"name": e["name"], "patch": e["patch"], "Cl": None, "Cd": None} for e in elements]},
            "convergence": {"state": "unavailable", "raw_class": "INFRA_LOSS" if status in INFRA_STATUSES else "MESH_FAILED",
                            "coordinate": "SIMPLE iteration (not physical time)", "statistics": {}, "reason": status},
            "usable": False, "provenance": {"case_result": str(path), "case_result_sha256": sha256(path),
                                            "coefficient_files": r.get("coefficient_files", {}), "force_files": r.get("force_files", {})}}
    base["pressure_convergence"] = dict(base["convergence"])
    cm = r.get("check_mesh", {})
    if status == "COMPLETED" and (not cm.get("mesh_ok") or cm.get("failed_check_counts")):
        base["status"] = "MESH_FAILED"
        base["convergence"]["reason"] = "checkMesh rejected the mesh"
        base["pressure_convergence"] = dict(base["convergence"])
        return base
    coefficient_failure = status not in MECHANICAL_STATUSES and divergent_coefficients(path.parent, r.get("coefficient_files", {}))
    bad_solver_log = any(r.get("solver", {}).get(k) for k in ("nan_in_log", "sigfpe", "foam_fatal"))
    if status not in MECHANICAL_STATUSES and (coefficient_failure or bad_solver_log):
        base["status"] = "SOLVER_DIVERGED"
        base["convergence"] = {**base["convergence"], "state": "diverged", "raw_class": "SOLVER_FAIL",
                               "reason": "nonfinite/blown-up coefficient row or genuine solver failure log, including a partial or timed-out history"}
        base["pressure_convergence"] = dict(base["convergence"])
        return base
    timed_out = status.endswith("_TIMEOUT") and status not in MECHANICAL_STATUSES
    if status in INFRA_STATUSES | MECHANICAL_STATUSES or timed_out and not r.get("solver", {}).get("nan_in_log"):
        if timed_out:
            base["convergence"]["raw_class"] = "INFRA_LOSS"
            base["pressure_convergence"]["raw_class"] = "INFRA_LOSS"
        return base
    files = r.get("coefficient_files", {})
    if status != "COMPLETED":
        bad_log = status == "SOLVER_DIVERGED" or any(r.get("solver", {}).get(k) for k in ("nan_in_log", "sigfpe", "foam_fatal"))
        base["convergence"] = {**base["convergence"], "state": "diverged" if bad_log else "not_settled", "raw_class": "SOLVER_FAIL", "reason": status}
        base["pressure_convergence"] = dict(base["convergence"])
        if set(files) != {"total", *patches} or any(not parts for parts in files.values()):
            base["convergence"]["reason"] += ": interrupted solver has no complete coefficient history"
            return base
    if set(files) != {"total", *patches}:
        raise ValueError("coefficient histories must include total and every element exactly once")
    try:
        histories = {name: read_history(path.parent, parts) for name, parts in files.items()}
    except HistoryUnavailable as exc:
        if status == "COMPLETED":
            raise
        base["convergence"]["reason"] += f": {exc}"
        return base
    total = histories["total"]
    force_files = r.get("force_files", {})
    if set(force_files) != set(files):
        if status != "COMPLETED":
            base["convergence"]["reason"] += ": interrupted solver has no complete dimensional force history"
            return base
        raise ValueError("dimensional force histories must include total and every element")
    try:
        split = {name: read_force_parts(path.parent, parts) for name, parts in force_files.items()}
    except HistoryUnavailable as exc:
        if status == "COMPLETED":
            raise
        base["convergence"]["reason"] += f": {exc}"
        return base
    if any(not np.array_equal(h[:, 0], total[:, 0]) for h in histories.values()):
        raise ValueError("total and element history sampling differs")
    if any(not np.array_equal(parts["total"][:, 0], total[:, 0]) for parts in split.values()):
        raise ValueError("dimensional force and forceCoeffs history sampling differs")
    segment_counts = {len(parts) for parts in files.values()} | {len(parts) for parts in force_files.values()}
    if len(segment_counts) != 1 or max(segment_counts) > 2:
        raise ValueError("force objects must have the same one initial + at most one continuation segment")
    if max(segment_counts) > 1 and r.get("continued_to") != 15000:
        raise ValueError("multiple coefficient segments require the registered continuation to 15000")
    analysis_histories, analysis_split = histories, split
    if max(segment_counts) > 1:
        # T2-0c judges a continued case on the continuation, while keeping the
        # initial history for provenance and cross-object force closure.
        analysis_histories = {name: read_history(path.parent, parts[-1:]) for name, parts in files.items()}
        analysis_split = {name: read_force_parts(path.parent, parts[-1:]) for name, parts in force_files.items()}
    cv = convergence(analysis_histories["total"], r)
    cv["statistics"]["history_rows"] = len(total)
    cv["statistics"]["analysis_segment"] = "last continuation" if max(segment_counts) > 1 else "initial solve"
    all_histories = [*histories.values(), *(h for parts in split.values() for h in parts.values())]
    if any(not np.isfinite(h[:, 1:]).all() or np.abs(h[:, 1:]).max() > BLOWUP_ABS for h in all_histories):
        cv = {**cv, "state": "diverged", "raw_class": "SOLVER_FAIL", "reason": "nonfinite/blown-up element history"}
    base["convergence"] = _finite_json(cv)
    pressure_cv = convergence(analysis_split["total"]["pressure"], r)
    pressure_cv["statistics"]["history_rows"] = len(total)
    pressure_cv["statistics"]["analysis_segment"] = cv["statistics"]["analysis_segment"]
    base["pressure_convergence"] = _finite_json(pressure_cv)
    if cv["state"] == "diverged":
        return base
    if not np.allclose(sum(histories[p][:, 1:] for p in patches), total[:, 1:], rtol=1e-5, atol=1e-6):
        raise ValueError("per-element force sum fails total closure")
    for name, h in histories.items():
        if not np.allclose(split[name]["total"][:, 1:], h[:, 1:], rtol=1e-5, atol=1e-6):
            raise ValueError("dimensional total force does not match forceCoeffs")
    for component in ("pressure", "viscous"):
        if not np.allclose(sum(split[p][component][:, 1:] for p in patches), split["total"][component][:, 1:], rtol=1e-5, atol=1e-6):
            raise ValueError(f"per-element {component} force sum fails total closure")
    count = len(analysis_histories["total"])
    n = min(count, max(CONVERGENCE["tail_min_rows"], math.ceil(count * CONVERGENCE["tail_fraction"])))
    mean = lambda a: {"Cl": float(a[-n:, 1].mean()), "Cd": float(a[-n:, 2].mean())}
    base["coefficients"] = {"total": mean(analysis_histories["total"]), "elements": [{"name": e["name"], "patch": e["patch"], **mean(analysis_histories[e["patch"]])} for e in elements]}
    for component in ("pressure", "viscous"):
        base[f"{component}_coefficients"] = {"total": mean(analysis_split["total"][component]), "elements": [
            {"name": e["name"], "patch": e["patch"], **mean(analysis_split[e["patch"]][component])} for e in elements]}
    cm = r.get("check_mesh", {})
    selected_cv = pressure_cv if base["observable"] == "pressure_cl" else cv
    base["usable"] = bool(selected_cv["state"] == "settled" and status == "COMPLETED"
                          and cm.get("mesh_ok") and not cm.get("failed_check_counts"))
    return base


def _family_layers(rows: list[dict]) -> dict[str, int]:
    """A3: the same stack is required across configurations and models."""
    families = {}
    for row in rows:
        count = row.get("n_layers")
        if count is None:
            if row.get("mesh_msh_sha256") is not None and row.get("status") != "MESH_FAILED":
                raise ValueError(f"meshed run requires n_layers for {row['family']}")
            continue  # Generator failure before a mesh was available.
        if type(count) is not int or count < 1:
            raise ValueError(f"invalid n_layers for {row['family']}")
        if row["family"] in families and families[row["family"]] != count:
            raise ValueError(f"inconsistent n_layers within family {row['family']}")
        families[row["family"]] = count
    return families


def collect(inputs, *, expected=None, stage="tr00") -> dict:
    supplied = expected_runs(stage) if expected is None else list(expected)
    expected = [key_of(k) for k in supplied]
    if not expected or len({run_id(k) for k in expected}) != len(expected):
        raise ValueError("expected run list is empty or duplicate")
    allowed = {run_id(k) for k in expected}
    bound = {run_id(k): k for k in supplied}
    paths = set()
    for item in inputs:
        p = Path(item)
        if not p.exists():
            raise FileNotFoundError(p)
        paths.update(p.rglob("case_result.json") if p.is_dir() else [p])
    found, rows = set(), []
    for p in sorted(paths):
        record = _read_json(p)
        rid = run_id(record)
        if rid in found:
            raise ValueError(f"duplicate run key: {rid}")
        if rid not in allowed:
            raise ValueError(f"unexpected run key: {rid}")
        for field in ("geometry_sha256", "n_layers"):
            if field in bound[rid] and record.get(field) != bound[rid][field]:
                raise ValueError(f"run {field} differs from the expected plan: {rid}")
        found.add(rid)
        rows.append(collect_case(p))
    _family_layers(rows)
    missing = [k for k in expected if run_id(k) not in found]
    out = {"schema_version": VERSION, "evidence_class": "RANS_MEASUREMENT_UNQUALIFIED", "normalization": NORMALIZATION,
           "force_convention": FORCE_CONVENTION, "complete": not missing, "expected_runs": len(expected),
           "missing_runs": missing, "results": rows}
    json.dumps(out, allow_nan=False)
    return out


def _number(value, label, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return float(value)


def _pressure_reference(reference: dict) -> dict:
    """Map only the canonical digitize_cp output, retaining its uncertainty ceiling."""
    if reference.get("kind") != "topo2d00_pressure_reference_v1" or reference.get("observable") != "pressure_cl":
        raise ValueError("reference must come from digitize_cp.build_reference")
    norm = reference.get("normalization", {})
    if (not math.isclose(_number(norm.get("reference_chord_m"), "reference chord"), T.CHORD, rel_tol=0, abs_tol=1e-12)
            or norm.get("sign") != "downforce=-Fz" or norm.get("observable") != "pressure_only_centre_section_Cl"
            or norm.get("abscissa_direction") != "global_streamwise" or norm.get("surfaces") != "physical_upper_lower"):
        raise ValueError("reference normalization, sign or observable is not the common-c1 pressure contract")
    refs = reference.get("references", [])
    if not isinstance(refs, list) or any(not isinstance(r, dict) for r in refs):
        raise ValueError("reference estimates missing")
    named = {r.get("config"): r for r in refs}
    if len(named) != len(refs) or not {"E1_sharp", "E2_sharp"} <= set(named):
        raise ValueError("reference requires unique E1_sharp and E2_sharp estimates")
    chosen = [named[c] for c in ("E1_sharp", "E2_sharp")]
    urls = []
    for ref in chosen:
        if (_number(ref.get("height_m"), "reference height") != HEIGHT_M
                or ref.get("observable") != "pressure_cl"
                or not math.isclose(_number(ref.get("h_over_c1"), "reference h/c1"), HEIGHT_M/T.CHORD, rel_tol=1e-12)
                or not math.isclose(_number(ref.get("h_over_c"), "reference h/c"), HEIGHT_M/COMBINED_CHORD_M, rel_tol=1e-12)):
            raise ValueError("TR-00 reference must declare the same physical h=100 mm")
        if ref.get("source", {}).get("observable") != "centre_section_pressure_integrated":
            raise ValueError("reference source must be centre-section pressure, not balance CL")
        _number(ref.get("Cl"), "reference Cl")
        _number(ref.get("digitization_sensitivity_abs"), "reference sensitivity", nonnegative=True)
        url = ref["source"].get("url")
        if not isinstance(url, str) or urlsplit(url).scheme not in ("https", "http") or not urlsplit(url).netloc:
            raise ValueError("shared reference output requires an explicit HTTP(S) source.url for each reference; no URL is inferred")
        if url not in urls:
            urls.append(url)
    double = chosen[1]
    readers = double.get("digitizers", [])
    ids = [r.get("id") for r in readers]
    if double.get("method") != "cp" or len(readers) != 2 or len(set(ids)) != 2 or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("E2_sharp needs two independent Cp digitization records")
    if len(double.get("elements", [])) != 2:
        raise ValueError("E2_sharp pressure reference must integrate two elements")
    for element in double["elements"]:
        digitizations = element.get("digitizations", [])
        if len(digitizations) != 2 or {d.get("id") for d in digitizations} != set(ids):
            raise ValueError("Cp element lacks both digitizations")
        if _number(element.get("Cl"), "Cp element Cl") <= 0:
            raise ValueError("Cp element Cl must be downforce-positive")
        for digitization in digitizations:
            if _number(digitization.get("Cl"), "Cp reading Cl") <= 0:
                raise ValueError("each Cp element reading must be downforce-positive")
            for surface in ("upper", "lower"):
                artifact = digitization.get(surface, {})
                if not isinstance(artifact.get("path"), str) or not artifact["path"]:
                    raise ValueError("Cp digitization source path missing")
                _digest(artifact.get("sha256"), "Cp digitization")
                if type(artifact.get("points")) is not int or artifact["points"] < 10:
                    raise ValueError("each Cp surface requires at least 10 points")
        if any(digitizations[0][surface]["sha256"] == digitizations[1][surface]["sha256"] for surface in ("upper", "lower")):
            raise ValueError("independent Cp digitizations require SHA-distinct corresponding CSVs")
    increments = [i for i in reference.get("increments", []) if i.get("from") == "E1_sharp" and i.get("to") == "E2_sharp"]
    if len(increments) != 1:
        raise ValueError("reference requires the unique E1_sharp -> E2_sharp increment")
    inc = increments[0]
    delta = _number(inc.get("delta_Cl"), "reference increment")
    sensitivity = _number(inc.get("digitization_sensitivity_abs"), "increment digitizing sensitivity", nonnegative=True)
    if (delta == 0 or not math.isclose(delta, chosen[1]["Cl"] - chosen[0]["Cl"], rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(sensitivity, chosen[1]["digitization_sensitivity_abs"], rel_tol=1e-12, abs_tol=1e-12)
            or inc.get("threshold_fraction") != .05
            or inc.get("threshold_uncertainty_basis") != "to_reference_digitization_sensitivity_abs"
            or inc.get("from_digitization_sensitivity_abs") != chosen[0]["digitization_sensitivity_abs"]
            or inc.get("to_digitization_sensitivity_abs") != chosen[1]["digitization_sensitivity_abs"]
            or not math.isclose(_number(inc.get("reference_difference_reading_sensitivity_abs"), "full difference reading sensitivity"),
                                sum(r["digitization_sensitivity_abs"] for r in chosen), rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError("reference increment/sensitivity/unchanged 5% threshold is inconsistent")
    manifest = reference.get("manifest", {})
    manifest_digest = _digest(manifest.get("sha256"), "Cp manifest")
    manifest_path = Path(manifest.get("path", ""))
    if not manifest_path.is_absolute():
        raise ValueError("Cp manifest.path must be canonical absolute; rebuild the reference with digitize_cp.py")
    manifest_path = manifest_path.resolve(strict=True)
    if sha256(manifest_path) != manifest_digest:
        raise ValueError("Cp manifest SHA mismatch")
    artifacts, seen = [], set()

    def add_artifact(artifact, method):
        value = artifact.get("path")
        if not isinstance(value, str) or not value or "#" in value:
            raise ValueError("reference digitization must name an actual artifact, not a fragment")
        p = Path(value)
        p = (p if p.is_absolute() else manifest_path.parent / p).resolve(strict=True)
        digest = _digest(artifact.get("sha256"), "reference artifact")
        if not p.is_file() or sha256(p) != digest:
            raise ValueError(f"reference artifact SHA mismatch: {p}")
        if p in seen:
            raise ValueError("reference digitization artifact paths must be distinct")
        seen.add(p)
        artifacts.append({"path": str(p), "sha256": digest, "method": method})

    add_artifact({"path": str(manifest_path), "sha256": manifest_digest},
                 "digitize_cp configuration manifest; scalar table extraction and pressure/curve normalization provenance; not an independent figure digitization")
    for ref in chosen:
        method = ref.get("method")
        readers_by_id = {r["id"]: r for r in ref.get("digitizers", [])}
        if method == "cp":
            for element in ref["elements"]:
                for digitization in element["digitizations"]:
                    reader = readers_by_id[digitization["id"]]
                    for surface in ("upper", "lower"):
                        add_artifact(digitization[surface], f"{ref['config']} cp {element['id']} {surface}; operator={reader['operator']}; tool={reader['tool']}; digitizer={reader['id']}; global-streamwise pressure integration")
        elif method == "cl_curve":
            if len(ref.get("digitizations", [])) != 2 or len({d["input"]["sha256"] for d in ref["digitizations"]}) != 2:
                raise ValueError("Cl(h) readings require SHA-distinct CSVs")
            for digitization in ref["digitizations"]:
                reader = readers_by_id[digitization["id"]]
                add_artifact(digitization["input"], f"{ref['config']} cl_curve; operator={reader['operator']}; tool={reader['tool']}; digitizer={reader['id']}; interpolation at declared physical height")
        elif method == "tabulated_cl":
            pass  # Exact scalar extraction is bound by the manifest, not a fabricated CSV.
        else:
            raise ValueError("unknown reference extraction method")
    return {"delta_cl": delta, "digitizing_uncertainty": sensitivity, "observable": "pressure_cl",
            "source": {"title": "; ".join(r["source"]["citation"] for r in chosen),
                       "url": "; ".join(urls),
                       "pages": "; ".join(r["source"]["location"] for r in chosen),
                       "observable": "centre-section pressure-integrated Cl",
                       "digitization_records": artifacts,
                       "method": "digitize_cp: " + "; ".join(f"{r['config']}={r['method']} ({r['source']['location']})" for r in chosen)
                                 + "; registered 5% test uses E2 elementwise absolute reading sensitivity; E1 reading sensitivity remains separately in reference_estimate; total experimental/integration uncertainty remains unknown"}}


def _export_identity(measurements, plans, supplied_geometry):
    """Actual input identities, including unrun geometry plans; no inferred freeze."""
    geometry, identities, runtimes = {}, [], []

    def bind(config, digest):
        if config not in STUDY_GEOMETRIES:
            raise ValueError(f"unknown geometry config: {config}")
        _digest(digest, "geometry")
        if config in geometry and geometry[config] != digest:
            raise ValueError(f"conflicting geometry SHA for {config}")
        geometry[config] = digest

    def source_identity(value, origin):
        keys = ("source_commit", "source_dirty", "bundle_sha256", "source_archive_sha256", "input_sha256", "pins")
        known = {k: value[k] for k in keys if k in value}
        if not known:
            return
        if "source_commit" in known and (not isinstance(known["source_commit"], str) or re.fullmatch(r"[0-9a-f]{40}", known["source_commit"]) is None):
            raise ValueError("invalid supplied source commit")
        if "source_dirty" in known and type(known["source_dirty"]) is not bool:
            raise ValueError("invalid supplied source dirty flag")
        for k in ("bundle_sha256", "source_archive_sha256"):
            if k in known:
                _digest(known[k], "source archive")
        for k in ("input_sha256", "pins"):
            if k in known:
                if not isinstance(known[k], dict):
                    raise ValueError("source input identity must be an object")
                for digest in known[k].values():
                    _digest(digest, "source input")
        identities.append({"origin": origin, **known})

    for row in measurements.get("results", []):
        bind(row["config"], row["geometry_sha256"])
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            raise ValueError("geometry/source plan must be an object")
        for config, digest in plan.get("geometry_input_sha256", {}).items():
            bind(config, digest)
        for row in plan.get("runs", []):
            if "geometry_sha256" in row:
                bind(row["config"], row["geometry_sha256"])
        source_identity(plan, f"supplied plan {index}")
    if supplied_geometry is not None:
        if not isinstance(supplied_geometry, dict) or not set(CONFIGS) <= set(supplied_geometry) <= set(STUDY_GEOMETRIES):
            raise ValueError("supplied geometry SHA inventory must contain all five run configurations, optionally E3_sharp for the BL plan")
        for config, digest in supplied_geometry.items():
            bind(config, digest)
    if not set(CONFIGS) <= set(geometry):
        raise ValueError("shared output needs all five geometry identities; supply --geometry-plan without requiring main solves, or use --measurements-only")
    roots = set()
    for row in measurements.get("results", []):
        case = Path(row.get("provenance", {}).get("case_result", ""))
        if case.parent.parent.name == "cases":
            roots.add(case.parent.parent.parent.resolve())
    for root in sorted(roots):
        for name in ("environment.json", "install.json"):
            p = root / name
            if p.is_file():
                payload = _read_json(p)
                runtimes.append({"path": str(p), "sha256": sha256(p), "record": payload})
                source_identity(payload, str(p))
    result = {"geometry_sha256": {c: geometry[c] for c in CONFIGS}}
    if "E3_sharp" in geometry:
        result["study_geometry_sha256"] = geometry
    if identities:
        result["source_identity"] = identities
        commits = {x["source_commit"] for x in identities if "source_commit" in x}
        if len(commits) == 1:
            result["source_commit"] = commits.pop()
    if runtimes:
        result["runtime_records"] = runtimes
    return result


def to_wp4(measurements: dict, reference_json: dict, *, plans=(), geometry_sha256=None) -> dict:
    """The actual WP4 nested interchange; raw rows stay in diagnostics/provenance.

    TR-00 sharp arms compare pressure-only coefficients to Cp. Thickened main
    arms use pressure+viscous totals for the WaterLily transfer comparison.
    Missing, numerical and infrastructure outcomes are never assigned zero.
    """
    if measurements.get("schema_version") != VERSION or measurements.get("normalization") != NORMALIZATION or measurements.get("force_convention") != FORCE_CONVENTION:
        raise ValueError("unknown RANS measurement normalization/schema")
    _family_layers(measurements.get("results", []))
    reference = _pressure_reference(reference_json)
    identity = _export_identity(measurements, plans, geometry_sha256)
    rows, cells = {}, set()
    for row in measurements.get("results", []):
        key = key_of(row)
        rid = run_id(key)
        if rid in rows:
            raise ValueError("duplicate measurement run identity")
        observable = "pressure_cl" if key["config"].endswith("_sharp") else "total_cl"
        selected_cv = row.get("pressure_convergence" if observable == "pressure_cl" else "convergence", {})
        if type(row.get("usable")) is not bool or row["usable"] and (row.get("status") != "COMPLETED" or selected_cv.get("state") != "settled"):
            raise ValueError("usable measurement contradicts its declared convergence/status")
        if row.get("observable") != observable:
            raise ValueError(f"measurement observable differs for {key['config']}")
        rows[rid] = row
        cells.add((key["model"], key["family"]))
    for missing in measurements.get("missing_runs", []):
        key = key_of(missing)
        if run_id(key) in rows:
            raise ValueError("run is both present and missing")
        cells.add((key["model"], key["family"]))
    if not cells:
        raise ValueError("measurement matrix is empty")
    component = {c: "pressure_cl" if c.endswith("_sharp") else "total_cl" for c in CONFIGS}
    mapped = []
    for model, family in sorted(cells):
        replicates = []
        for i in range(8):
            rep = {"id": f"r{i:02d}", "mesh_sha256": {}, "status": {}, "forces": {}, "diagnostics": {}}
            for config in ("E1", "E2", "E3", "E1_sharp", "E2_sharp"):
                key = dict(config=config, model=model, family=family, realisation=i)
                row = rows.get(run_id(key))
                rep["mesh_sha256"][config] = row["mesh_msh_sha256"] if row else None
                rep["forces"][config] = None
                if row is None:
                    rep["status"][config] = "INCOMPLETE"
                    rep["diagnostics"][config] = {"missing": True, **key}
                    continue
                rep["diagnostics"][config] = row
                if row["usable"]:
                    field = "pressure_coefficients" if config.endswith("_sharp") else "coefficients"
                    values = row[field]["total"]
                    rep["forces"][config] = {"downforce": _number(values["Cl"], "exported Cl"), "drag": _number(values["Cd"], "exported Cd"),
                                              "observable": component[config]}
                    _digest(row["mesh_msh_sha256"], "settled mesh")
                    rep["status"][config] = "SETTLED"
                else:
                    infrastructure = row["convergence"].get("raw_class") == "INFRA_LOSS"
                    rep["status"][config] = "INCOMPLETE" if infrastructure else "MESH_FAILED" if row["status"] == "MESH_FAILED" else "NUMERICAL"
            replicates.append(rep)
        summaries = {}
        for config in CONFIGS:
            hashes = [r["mesh_sha256"][config] for r in replicates if r["mesh_sha256"][config] is not None]
            forces = [r["forces"][config] for r in replicates if r["forces"][config] is not None]
            statuses = {r["status"][config] for r in replicates}
            degenerate = len(set(hashes)) < len(hashes)
            state = ("DEGENERATE_REALISATIONS" if degenerate else "MESH_FAILED" if "MESH_FAILED" in statuses else
                     "NUMERICAL" if "NUMERICAL" in statuses else "COMPLETE" if statuses == {"SETTLED"} else "INCOMPLETE")
            summaries[config] = {"status": state, "observable": component[config], "distinct_meshes": len(set(hashes)),
                                 "measured_realisations": len(forces),
                                 "point_estimate": {name: float(np.mean([f[name] for f in forces])) for name in ("downforce", "drag")} if forces else None,
                                 # WP4 owns confidence intervals. Degenerate cells can
                                 # never yield one, even from identical finite forces.
                                 "ci90": None, "ratio_test_status": "READY" if state == "COMPLETE" else "INCOMPLETE"}
            if degenerate:
                for rep in replicates:
                    # Compatibility bridge: the old WP4 reader cannot certify a
                    # duplicate-mesh cell while retaining finite diagnostic forces.
                    rep["status"][config] = "INCOMPLETE"
        thickening = []
        for config in ("E1", "E2"):
            for observable, field in (("pressure_cl", "pressure_coefficients"), ("total_cl", "coefficients")):
                differences = []
                for i in range(8):
                    left = rows.get(run_id(dict(config=config+"_sharp", model=model, family=family, realisation=i)))
                    right = rows.get(run_id(dict(config=config, model=model, family=family, realisation=i)))
                    if left and right and left["usable"] and right["usable"]:
                        a, b = left[field]["total"], right[field]["total"]
                        differences.append({"downforce": _number(b["Cl"], "thickened Cl")-_number(a["Cl"], "original Cl"),
                                            "drag": _number(b["Cd"], "thickened Cd")-_number(a["Cd"], "original Cd")})
                thickening.append({"from": config+"_sharp", "to": config, "observable": observable,
                                   "paired_realisations": len(differences), "ci90": None,
                                   "point_estimate": {name: float(np.mean([d[name] for d in differences])) for name in ("downforce", "drag")} if differences else None})
        mapped.append({"model": model, "family": family, "realisations": replicates,
                       "cell_summary": summaries, "thickening_alone": thickening})
    out = {"schema": "topo2d00-rans-results-v1", "coefficient_reference": {"chord_mm": float(format(T.CHORD*1000, ".10g")), "units": "dimensionless", "downforce": "-Cz", "drag": "+Cx",
                                                                                  "reynolds_c1": REYNOLDS_C1, "height_mm": HEIGHT_M*1000,
                                                                                  "h_over_c1": HEIGHT_M/T.CHORD, "h_over_c": HEIGHT_M/COMBINED_CHORD_M},
           "reference": reference, "cells": mapped,
           "provenance": {"component_by_config": component, "measurements": measurements, "reference_estimate": reference_json,
                          **identity,
                          "uncertainty_ceiling": "digitizing sensitivity is not total reference uncertainty or a confidence interval"}}
    json.dumps(out, allow_nan=False)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--plan", type=Path, action="append", help="builder run_plan.json; repeat for TR and main coverage")
    ap.add_argument("--geometry-plan", type=Path, action="append", default=[], help="additional rendered plan for geometry/source identity only, without expecting its unsolved runs")
    ap.add_argument("--reference", type=Path, help="canonical digitize_cp.py output; required for the WP4 interchange")
    ap.add_argument("--measurements-only", action="store_true", help="write detailed diagnostics without claiming WP4 interchange readiness")
    ap.add_argument("--stage", choices=("tr00", "main"), default="tr00")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--allow-incomplete", action="store_true", help="explicitly accept diagnostic coverage only")
    args = ap.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite: {args.out}")
    if args.measurements_only and args.reference:
        raise ValueError("--reference and --measurements-only are mutually exclusive")
    if not args.measurements_only and not args.reference:
        raise ValueError("--reference is required; use --measurements-only for diagnostics")
    plans = [_read_json(p) for p in args.plan or []]
    identity_plans = plans + [_read_json(p) for p in args.geometry_plan]
    expected = [run for plan in plans for run in plan["runs"]] if plans else None
    measurements = collect(args.inputs, expected=expected, stage=args.stage)
    out = measurements if args.measurements_only else to_wp4(measurements, _read_json(args.reference), plans=identity_plans)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return 0 if measurements["complete"] or args.allow_incomplete else 2


if __name__ == "__main__":
    sys.exit(main())
