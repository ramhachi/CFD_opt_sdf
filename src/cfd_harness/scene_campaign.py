"""Isolated harness v1.1 scene contract, CPU smoke runner, and 2D verifier.

The historical phi runner and its T4 identity contract are deliberately separate.
The rendered local GPU path requires an external approved freeze and qualified
backend before execution. This module never freezes, publishes, installs
packages, or imports CUDA. GPU code is supplied but is not GPU-qualified here.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cfd_harness import campaign_schema as SC

ROOT = Path(__file__).resolve().parents[2]
SCENE_KEYS = {"kind", "scene_path", "scene_sha256", "topo2d"}
IDENTITY_KEYS = {"configuration", "height_mm", "reynolds", "grid", "phase", "role"}
READOUTS = ("cur", "nds", "cv")


def is_scene_campaign(c):
    return isinstance(c, dict) and bool(c.get("states")) and all(isinstance(r, dict) and r.get("kind") == "scene" for r in c["states"].values())


def validate_campaign(c):
    SC.req(is_scene_campaign(c), "not a scene campaign")
    SC.req(set(c) == set(SC.CAMPAIGN_KEYS) and c["harness_version"] == SC.HARNESS_VERSION, "scene campaign keys or harness version")
    SC.req(c["baseline"] is None and c["directions"] == {} and c["legacy_replay"] is False, "a scene has no phi baseline/direction or legacy replay")
    SC.req(c["measurement"].get("time_window_t_u_l") is None and c["measurement"].get("requires_parent_window_freeze") is True,
           "draft scene campaign requires the parent-derived window freeze")
    SC.req(c["measurement"].get("force_unit") == "N/m" and c["measurement"].get("reference_chord_mm") == 223.4, "scene force/chord contract")
    SC.req(c["kernels"] and c["owner"] and c["campaign_id"], "scene campaign identity")
    SC.req(isinstance(c["job_env_common"], dict) and all(isinstance(key, str) and SC.NAME.fullmatch(key) and isinstance(value, str) for key, value in c["job_env_common"].items()), "scene common environment")
    SC.req(isinstance(c["job_env_keys"], list) and len(set(c["job_env_keys"])) == len(c["job_env_keys"]) and all(isinstance(key, str) and SC.NAME.fullmatch(key) for key in c["job_env_keys"]), "scene declared environment keys")
    SC.req(isinstance(c["scrub_env"], list) and all(isinstance(key, str) for key in c["scrub_env"]), "scene scrub environment")
    SC.req(not any(key.startswith("CUDA_") or key.startswith("W4_") or key == "JULIA_NUM_THREADS" for key in c["job_env_common"]), "scene common environment sets runner-owned identity/device")
    for name, row in c["states"].items():
        SC.req(SC.NAME.fullmatch(name) and set(row) == SCENE_KEYS, "scene state keys/name")
        SC.safe_rel(row["scene_path"])
        SC.req(SC.is_sha(row["scene_sha256"]), "scene state SHA")
        ident = row["topo2d"]
        SC.req(set(ident) == IDENTITY_KEYS and ident["configuration"] in ("E1", "E2", "E3"), "scene run identity")
        SC.req(ident["grid"] in ("main", "confirmation") and ident["role"] in ("primary", "confirmation", "determinism", "domain", "secondary", "prerun"), "scene grid/role")
        SC.req(SC.finite(ident["height_mm"]) > 0 and SC.finite(ident["reynolds"]) > 0 and isinstance(ident["phase"], (str, int)), "scene physical identity")
    used = set()
    for key, kernel in c["kernels"].items():
        SC.req(set(kernel) == set(SC.KERNEL_KEYS) and kernel["job"] == "scripts/waterlily_topo2d_job.jl", "scene kernel contract")
        SC.safe_rel(kernel["job"])
        SC.req(kernel["kernel_id"].startswith(c["owner"] + "/"), "scene kernel id")
        case = kernel["case"]
        SC.req(set(case) == set(SC.CASE_KEYS) and len(case["flow_dims"]) == 2 and all(type(v) is int and v > 0 for v in case["flow_dims"]), "scene 2D case")
        SC.req(case["reference_length_m"] == 0.2234 and case["freestream_mps"] == [1.0, 0.0, 0.0], "scene common reference chord or flow")
        SC.req(math.isclose(case["flow_spacing_m"] * case["solver_length"], 0.2234, rel_tol=1e-12), "scene cell/chord map")
        SC.req(math.isclose(case["solver_viscosity"], case["solver_length"] / case["reynolds"], rel_tol=1e-12), "scene common-chord Reynolds")
        cfg = kernel["config"]
        SC.req(set(SC.BUDGET_KEYS) <= set(cfg) and all(SC.finite(cfg[k]) > 0 for k in SC.BUDGET_KEYS), "scene budgets")
        SC.req(cfg["per_state_timeout_s"] <= cfg["solver_wall_time_cap_s"] and cfg["solver_wall_time_cap_s"] + cfg["reserve_s"] + cfg["instantiate_timeout_s"] + cfg["gpu_probe_timeout_s"] <= cfg["kernel_timeout_s"], "scene aggregate budget")
        SC.req(kernel["runs"] and len(set(SC.run_names(kernel))) == len(kernel["runs"]), "scene run names")
        for run in kernel["runs"]:
            SC.req(set(run) == {"state", "env"} and run["state"] in c["states"], "scene run")
            used.add(run["state"])
            SC.req({SC.ORIGIN_ENV} <= set(run["env"]) <= {SC.ORIGIN_ENV, "TOPO2D_TOP_FACTOR"}, "scene phase environment")
            shift = SC.floats(run["env"][SC.ORIGIN_ENV])
            SC.req(len(shift) == 3 and all(math.isfinite(v) for v in shift) and shift[1] == 0, "2D scene phase must be x,0,z in meters")
            ident = c["states"][run["state"]]["topo2d"]
            SC.req(ident["reynolds"] == case["reynolds"], "scene state/kernel Re mismatch")
            SC.req(float(run["env"].get("TOPO2D_TOP_FACTOR", "1")) == (1.5 if ident["role"] == "domain" else 1.0), "scene domain control factor")
            if ident["role"] == "prerun":
                SC.req(ident["configuration"] == "E1" and ident["grid"] == "main" and str(ident["phase"]) == "0" and shift == [0, 0, 0] and case["solver_length"] == 120, "scene E1 parent pre-run contract")
    SC.req(used == set(c["states"]), "unreferenced scene state")


def _scene_declaration(scene, declared):
    SC.req(scene["configuration"] == declared["configuration"], "declared scene configuration differs from JSON")
    SC.req(SC.finite(scene["height_mm"]) == SC.finite(declared["height_mm"]), "declared scene height differs from JSON")


def scene_record(path, expected_sha, declared=None):
    """Read one hash-bound geometry, optionally binding the study declaration."""
    path = Path(path)
    SC.req(SC.sha256_path(path) == expected_sha, "scene hash mismatch")
    s = SC.jload(path)
    SC.req(s.get("schema") == "topo2d-scene-v1" and s.get("gates", {}).get("accepted") is True, "scene geometry gate not accepted")
    from cfd_gen.topo2d.geometry import validate_scene
    SC.req(validate_scene(s) == s["gates"], "scene geometry gate record is stale")
    SC.req(s.get("configuration") in ("E1", "E2", "E3"), "unregistered scene configuration")
    dx, ground = SC.finite(s["dx_mm"]), SC.finite(s["ground_z_mm"])
    SC.req(dx > 0 and s["normalizations"]["c1_mm"] == 223.4 and s["normalizations"]["c_mm"] == 380, "scene scale contract")
    elements = s["elements"]
    SC.req(len(elements) == int(s["configuration"][1]) and len({e["name"] for e in elements}) == len(elements), "scene element count/names")
    for e in elements:
        poly = e["polygon_mm"]
        SC.req(SC.NAME.fullmatch(e["name"]) and len(poly) >= 4 and poly[0] != poly[-1], "scene polygon must use implicit closure without a duplicated endpoint")
        SC.req(all(len(p) == 2 and all(math.isfinite(SC.finite(v)) for v in p) for p in poly), "scene polygon coordinates")
        SC.req(all(a != b for a, b in zip(poly, poly[1:] + poly[:1])), "scene polygon zero-length edge")
    if declared is not None:
        _scene_declaration(s, declared)
    return s


def _scene_records(rows, repo):
    """Gate each geometry once while binding every declared run identity."""
    scenes = {}
    for row in rows:
        key = row["scene_path"], row["scene_sha256"]
        if key not in scenes:
            scenes[key] = scene_record(Path(repo) / key[0], key[1])
        _scene_declaration(scenes[key], row["topo2d"])
    return scenes


def require_verified_geometry(scene):
    """Formal freeze/admission never upgrades the deliberately marked OCR rows."""
    sources = scene.get("sources")
    SC.req(isinstance(sources, list) and sources, "formal geometry source provenance missing")
    SC.req(all(isinstance(source.get("verification"), str) and source["verification"].startswith("VERIFIED_") for source in sources), "formal freeze refuses UNVERIFIED_OCR or unknown geometry source verification")


def numerical_stop_key(identity):
    """Only the exact (configuration, Re, height, role) stops; phases share it."""
    return tuple(identity[key] for key in ("configuration", "reynolds", "height_mm", "role"))


def job_environment(campaign, run, inherited):
    """Scrub job/device prefixes, then apply the campaign's explicit environment."""
    allowed = {SC.ORIGIN_ENV, *campaign["job_env_keys"]}
    SC.req(set(run["env"]) <= allowed and all(isinstance(value, str) for value in run["env"].values()), "run environment contains an undeclared key or non-string value")
    env = {key: value for key, value in inherited.items() if not key.startswith(("TOPO2D_", "W4_", "CUDA_"))}
    for key in campaign["scrub_env"]:
        env.pop(key, None)
    env.update(campaign["job_env_common"])
    env.update(run["env"])
    return env


def scene_wire(path, expected_sha):
    """Validated text bridge to Julia; the vertex list closes cyclically."""
    s = scene_record(path, expected_sha)
    elements = s["elements"]
    lines = [s["schema"], s["configuration"], repr(SC.finite(s["dx_mm"])), repr(SC.finite(s["ground_z_mm"])), repr(SC.finite(s["height_mm"])), str(len(elements))]
    for e in elements:
        poly = e["polygon_mm"]
        lines += [e["name"], str(len(poly)), *(f"{p[0]!r} {p[1]!r}" for p in poly)]
        probes = e["bulk_core_probe_stations_mm"]
        lines += [str(len(probes)), *(f"{p[0]!r} {p[1]!r}" for p in probes)]
    return "\n".join(lines) + "\n"


def _mean(rows, column, start, end):
    SC.req(rows[0]["t_u_l"] <= start < end <= rows[-1]["t_u_l"], "force history does not bracket window")
    total = 0.0
    for a, b in zip(rows, rows[1:]):
        lo, hi = max(start, a["t_u_l"]), min(end, b["t_u_l"])
        if lo < hi:
            slope = (b[column] - a[column]) / (b["t_u_l"] - a["t_u_l"])
            total += (a[column] + slope * ((lo + hi) / 2 - a["t_u_l"])) * (hi - lo)
    return total / (end - start)


def validate_observable(record, height_mm):
    """Bind the WaterLily total-force observable and both ride-height scales."""
    SC.req(record.get("observable") == "total_cl", "WaterLily scene observable must be total_cl")
    for key, chord in (("h_over_c1", 223.4), ("h_over_c", 380.0)):
        SC.req(math.isclose(SC.finite(record.get(key), key), height_mm / chord, rel_tol=1e-12), f"scene {key} differs from height_mm")


def host_readouts(path, *, start, end, solver_length, force_scale, available, batches=8, element_names=None):
    """Recompute 2D physical means and common-c1 coefficients, including batches."""
    SC.req(type(batches) is int and batches >= 4 and solver_length > 0 and force_scale > 0, "2D force/batch contract")
    SC.req(set(available) == set(READOUTS) and available["cur"] is True and all(type(v) is bool for v in available.values()), "readout availability contract")
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        SC.req(tuple(header[:13]) == SC.FORCE_COLUMNS and len(set(header)) == len(header), "scene force CSV schema")
        if element_names is not None:
            axes = ("fx", "fy", "fz", "drag", "downforce")
            expected = [*SC.FORCE_COLUMNS, *(f"{r}_{axis}_solver" for r in READOUTS for axis in axes), *(f"element_{name}_{axis}_solver" for name in element_names for axis in axes)]
            SC.req(header == expected, "scene readout/element CSV columns differ from the declared elements")
        rows = [{k: float(v) for k, v in r.items()} for r in reader]
    SC.req(len(rows) >= 4 and all(all(math.isfinite(r[k]) for k in SC.FORCE_COLUMNS) for r in rows), "scene force history nonfinite or short")
    SC.req(all(b["step"] > a["step"] and b["t_u_l"] > a["t_u_l"] for a, b in zip(rows, rows[1:])), "scene force step/time order")
    for r in rows:
        SC.req(math.isclose(r["drag_solver"], r["fx_solver"], abs_tol=1e-9) and math.isclose(r["downforce_solver"], -r["fz_solver"], abs_tol=1e-9), "scene force projection")
        SC.req(all(r[k] == 0 for k in ("fy_solver", "pressure_fy_solver", "viscous_fy_solver")), "2D scene spanwise force must be zero")
        SC.req(all(math.isclose(r[f"{a}_solver"], r[f"pressure_{a}_solver"] + r[f"viscous_{a}_solver"], abs_tol=1e-9) for a in ("fx", "fy", "fz")), "scene force component closure")
        SC.req(all(math.isfinite(v) for k, v in r.items() if not any(k.startswith(prefix + "_") and not available[prefix] for prefix in READOUTS)), "nonfinite available scene/element force")
    elements = sorted({column[:-len("_drag_solver")] for column in header if column.startswith("element_") and column.endswith("_drag_solver")})
    for r in rows:
        for axis in ("fx", "fy", "fz", "drag", "downforce"):
            if elements:
                SC.req(all(f"{element}_{axis}_solver" in header for element in elements), "incomplete element force columns")
                SC.req(math.isclose(sum(r[f"{element}_{axis}_solver"] for element in elements), r[f"{axis}_solver"], rel_tol=1e-9, abs_tol=1e-9), "element forces do not sum to wing force")
    out = {}
    for readout in READOUTS:
        cols = [f"{readout}_{q}_solver" for q in ("downforce", "drag")]
        SC.req(all(c in header for c in cols), "missing scene readout columns")
        values = [r[k] for r in rows for k in header if k.startswith(readout + "_")]
        if not available[readout]:
            SC.req(all(math.isnan(v) for v in values), f"unavailable {readout} must be NaN, never invented zeros")
            out[readout] = None
            continue
        SC.req(all(math.isfinite(v) for v in values), f"available {readout} is nonfinite")
        for r in rows:
            if f"{readout}_fx_solver" in header:
                SC.req(math.isclose(r[f"{readout}_fx_solver"], r[f"{readout}_drag_solver"], abs_tol=1e-9) and math.isclose(r[f"{readout}_fz_solver"], -r[f"{readout}_downforce_solver"], abs_tol=1e-9), "scene readout projection identity")
                SC.req(r[f"{readout}_fy_solver"] == 0, "2D scene readout spanwise force must be zero")
        coefficient = lambda q, a, b: 2 * _mean(rows, f"{readout}_{q}_solver", a, b) / solver_length
        edges = [start + (end - start) * i / batches for i in range(batches + 1)]
        out[readout] = {"observable": "total_cl", **{q: coefficient(q, start, end) for q in ("downforce", "drag")}}
        out[readout]["batches"] = [{q: coefficient(q, a, b) for q in ("downforce", "drag")} for a, b in zip(edges, edges[1:])]
    SC.req(all(math.isclose(r[f"cur_{q}_solver"], r[f"{q}_solver"], rel_tol=1e-12, abs_tol=1e-12) for r in rows for q in ("downforce", "drag")), "cur differs from canonical force")
    return {"observable": "total_cl", "drag_n": force_scale * _mean(rows, "drag_solver", start, end), "downforce_n": force_scale * _mean(rows, "downforce_solver", start, end), "readouts": out}


def refuse_formal_runner():
    raise ValueError("the Kaggle formal scene runner is unavailable; use the frozen local scene runner after backend/window approval")


def source_paths(backend="cpu", repo=ROOT):
    project = "CFDSDFWaterLilyT4" if backend == "cuda" else "CFDSDFWaterLily"
    paths = ["scripts/waterlily_topo2d_job.jl", "julia/CFDSDFWaterLily/gen01/Topo2D.jl", "src/cfd_harness/scene_campaign.py", "src/cfd_harness/campaign_schema.py", "src/cfd_gen/topo2d/geometry.py",
            "src/cfd_gen/__init__.py", "src/cfd_gen/topo2d/__init__.py",
            "data/zz2003/main_element_table3.dat", "data/zz2003/flap_table4.dat", "data/zz2003/single_element_table2.dat",
            "julia/CFDSDFWaterLily/src/Forces.jl", f"julia/{project}/Project.toml", f"julia/{project}/Manifest.toml"]
    paths += [f"julia/CFDSDFWaterLily/src/{name}" for name in ("CFDSDFWaterLily.jl", "GridSDFBody.jl", "WaterLilyBody.jl", "Runtime.jl", "Simulation.jl")]
    for optional in ("Checkpoint.jl", "Force00.jl"):
        for folder in ("gen01", "src"):
            path = f"julia/CFDSDFWaterLily/{folder}/" + optional
            if (Path(repo) / path).is_file():
                paths.append(path)
                break
    return paths


def _window_estimator(repo):
    # The estimator is an explicitly pinned script, keeping registered harness
    # v1.1 tool files unchanged. run_name='__run_path__' does not invoke its CLI.
    return runpy.run_path(str(Path(repo) / "scripts/topo2d00/prerun_window.py"))


def scene_pins(c, campaign_rel, kernel, repo=ROOT, backend="cuda"):
    paths = {*source_paths(backend, repo), *SC.TOOL_FILES, campaign_rel, *c["pins"], c["kernels"][kernel]["job"], "scripts/topo2d00/prerun_window.py"}
    scenes = _scene_records((c["states"][run["state"]] for run in c["kernels"][kernel]["runs"]), repo)
    paths.update(path for path, _ in scenes)
    return {p: SC.sha256_path(Path(repo) / p) for p in sorted(paths)}


def render(campaign_path, source_commit, kernel, smoke=False, repo=ROOT):
    """Render a local existing-checkout runner; no network, install, or GPU use.

    The formal runner cannot launch until an external reviewed freeze binds its
    parent-derived window, backend qualification artifact, runtime and all pins.
    """
    repo, path = Path(repo).resolve(), Path(campaign_path).resolve()
    c = SC.jload(path)
    validate_campaign(c)
    SC.req(SC.COMMIT.fullmatch(source_commit or "") is not None and kernel in c["kernels"], "scene render commit/kernel")
    relative = str(path.relative_to(repo))
    pins = scene_pins(c, relative, kernel, repo, "cpu" if smoke else "cuda")
    from cfd_harness.campaign_build import verify_source
    verify_source(repo, source_commit, pins)
    text = "\n".join([
        "# TOPO-2D local runner. Existing pinned checkout only; never installs or publishes.",
        "import json, os, subprocess, sys", "from pathlib import Path", f"SOURCE_COMMIT = {source_commit!r}", f"CAMPAIGN = {relative!r}", f"KERNEL = {kernel!r}", f"PINS = {pins!r}",
        "root = Path(os.environ['TOPO2D_SOURCE_ROOT']).resolve()", "sys.path.insert(0, str(root / 'src'))", "from cfd_harness import scene_campaign as S", "from cfd_harness import campaign_schema as SC",
        "SC.req(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip() == SOURCE_COMMIT, 'runner checkout commit differs')",
        "SC.req(all(SC.sha256_path(root / p) == h for p,h in PINS.items()), 'runner source/scene pin mismatch')",
        ("S.run_cpu_smoke(root / CAMPAIGN, KERNEL, Path(os.environ['TOPO2D_OUTPUT_DIR']), window=(float(os.environ['TOPO2D_SMOKE_START']),float(os.environ['TOPO2D_SMOKE_END'])), repo=root)" if smoke else
         "S.run_frozen_kernel(root / CAMPAIGN, KERNEL, Path(os.environ['TOPO2D_OUTPUT_DIR']), Path(os.environ['TOPO2D_FREEZE']), expected_commit=SOURCE_COMMIT, expected_pins=PINS, repo=root)"), ""])
    compile(text, "topo2d_scene_runner.py", "exec")
    return text


def parent_window(mean_downforce, s0_point, burn_in):
    """Amendment 7: point S0, 50 c1/U rounding, 1.5% target, clip at 400."""
    mean, s0, burn = SC.finite(mean_downforce), SC.finite(s0_point), SC.finite(burn_in)
    SC.req(mean != 0 and s0 >= 0 and burn >= 80, "invalid parent window statistics")
    width = max(50, 50 * math.ceil(s0 / (0.015 * abs(mean))**2 / 50))
    return [burn, burn + min(400, width)]


def formal_context(c, campaign_path, kernel, freeze, repo=ROOT, *, prerun=False):
    """Same source/backend/window admission for execution AND verification."""
    repo = Path(repo).resolve()
    SC.req("formal_context" not in freeze and "windows" not in freeze, "hand-entered formal_context/windows are forbidden; use the hash-bound parent record")
    SC.req(freeze.get("kind") == SC.FREEZE_KIND and freeze.get("harness_version") == SC.HARNESS_VERSION and freeze.get("campaign_sha256") == SC.sha256_path(campaign_path), "scene freeze identity")
    SC.req(SC.COMMIT.fullmatch(freeze.get("source_commit", "")) is not None and freeze.get("scene_runner_approved") is True, "scene runner is not frozen/approved")
    runtime = freeze.get("runtime", {}).get(kernel)
    SC.req(isinstance(runtime, dict) and runtime.get("backend") == "WaterLily CUDA" and runtime.get("identity", {}).get("memory") == "CuArray", "formal scene evidence requires qualified CUDA, never CPU")
    pins = scene_pins(c, str(Path(campaign_path).resolve().relative_to(repo)), kernel, repo)
    SC.req(freeze.get("pins", {}).get(kernel) == pins, "scene freeze omits or changes source/scene pins")
    for scene in _scene_records((c["states"][run["state"]] for run in c["kernels"][kernel]["runs"]), repo).values():
        require_verified_geometry(scene)
    qualification = freeze.get("backend_qualification", {})
    SC.req(qualification.get("passed") is True and qualification.get("backend") == "cuda" and isinstance(qualification.get("device_uuid"), str) and qualification["device_uuid"].startswith("GPU-"), "backend qualification is absent or not passed")
    gate_path = repo / SC.safe_rel(qualification.get("path"))
    SC.req(SC.is_sha(qualification.get("sha256")) and SC.sha256_path(gate_path) == qualification["sha256"], "backend qualification artifact hash")
    gate = SC.jload(gate_path)
    SC.req(gate.get("schema_version") == 1 and gate.get("status") == "PASS" and gate.get("failed_criteria") == [] and gate.get("incomplete_criteria") == [], "LOCAL-GPU-01 backend gate is not PASS")
    SC.req(gate.get("gpu_identity", {}).get("uuid") == qualification["device_uuid"] == runtime["identity"].get("device_uuid"), "qualified gate/runtime device UUID mismatch")
    SC.req(all(gate.get("criteria", {}).get(k, {}).get("status") == "PASS" for k in ("C1", "C2", "C5", "C6")), "LOCAL-GPU-01 required backend criteria are absent")
    if prerun:
        SC.req(any(c["states"][run["state"]]["topo2d"]["role"] == "prerun" for run in c["kernels"][kernel]["runs"]), "kernel has no registered E1 pre-run")
        return [80, 520]
    parent = freeze.get("parent_window_records", {}).get(kernel)
    SC.req(isinstance(parent, dict) and SC.is_sha(parent.get("sha256")), "frozen E1 parent window record missing")
    parent_path = repo / SC.safe_rel(parent["path"])
    SC.req(SC.sha256_path(parent_path) == parent["sha256"], "parent pre-run record hash mismatch")
    record = _window_estimator(repo)["validate_record"](parent_path, repo=repo)
    SC.req(record.get("configuration") == "E1" and record.get("reynolds") == c["kernels"][kernel]["case"]["reynolds"], "parent pre-run identity")
    expected_parent = next(row for row in c["states"].values() if row["topo2d"]["role"] == "prerun" and row["topo2d"]["reynolds"] == record["reynolds"])
    SC.req(record["scene_sha256"] == expected_parent["scene_sha256"] and record["height_mm"] == expected_parent["topo2d"]["height_mm"] and record["runtime"] == runtime["identity"], "parent pre-run source scene/height/runtime identity")
    SC.req(all(pins.get(path) == digest for path, digest in record["source_sha256"].items()) and set(record["source_sha256"]) == set(source_paths("cuda", repo)), "parent pre-run source pins differ")
    window = record["window"]
    return window


def run_frozen_kernel(campaign_path, kernel, output_dir, freeze_path, *, expected_commit, expected_pins, repo=ROOT, julia="julia", prerun=False):
    """Future local qualified-GPU entry point. No call is made during WP4 tests."""
    repo, freeze_path = Path(repo).resolve(), Path(freeze_path).resolve()
    c, freeze = SC.jload(campaign_path), SC.jload(freeze_path)
    validate_campaign(c)
    SC.req(SC.COMMIT.fullmatch(expected_commit or "") is not None and subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip() == expected_commit, "scene execution checkout commit differs")
    SC.req(kernel in c["kernels"] and Path(str(freeze_path) + ".sha256").read_text().strip() == SC.sha256_path(freeze_path), "scene freeze sidecar/kernel")
    SC.req(freeze.get("kind") == SC.FREEZE_KIND and freeze.get("harness_version") == SC.HARNESS_VERSION and freeze.get("campaign_sha256") == SC.sha256_path(campaign_path), "scene freeze identity")
    SC.req(freeze.get("source_commit") == expected_commit and freeze.get("scene_runner_approved") is True and freeze.get("pins", {}).get(kernel) == expected_pins, "scene runner is not frozen/approved")
    SC.req(all(SC.sha256_path(repo / SC.safe_rel(p)) == h for p, h in expected_pins.items()), "scene frozen source changed")
    SC.req(expected_pins == scene_pins(c, str(Path(campaign_path).resolve().relative_to(repo)), kernel, repo), "scene freeze omits or changes source/scene pins")
    window = formal_context(c, campaign_path, kernel, freeze, repo, prerun=prerun)
    runs = [run for run in c["kernels"][kernel]["runs"] if (c["states"][run["state"]]["topo2d"]["role"] == "prerun") is prerun]
    return _run_kernel(campaign_path, kernel, output_dir, window=window, count=len(runs), repo=repo, julia=julia,
                       smoke=False, backend="cuda", freeze=freeze, pins=expected_pins, prerun=prerun)


def make_campaign(repo=ROOT):
    """Unfrozen three-kernel declaration; windows intentionally require pre-run data."""
    repo = Path(repo)
    states, kernels = {}, {}
    scene_inputs = {}

    def scene_input(relative):
        # One generation reuses a geometry across phases and Re. Gate each
        # distinct input once here; run/verify still recheck the actual files.
        if relative not in scene_inputs:
            digest = SC.sha256_path(repo / relative)
            scene_inputs[relative] = digest, scene_record(repo / relative, digest)
        return scene_inputs[relative]
    primary_height = scene_input("docs/harness/topo2d00_scenes/E1.json")[1]["height_mm"]
    secondary_height = scene_input("docs/harness/topo2d00_scenes/E1_h80.json")[1]["height_mm"]
    # JOB-02's R2 placement mechanism, centered and extended with exact mirrors
    # in (x,z). Every configuration uses the identical phase at a given grid.
    r2 = (0.7548776662, 0.5698402910)  # scripts/unc01_build.py:48, JOB-02 mechanism
    fractions = []
    for i in range(1, 9):
        vector = ((i * r2[0]) % 1 - 0.5, (i * r2[1]) % 1 - 0.5)
        fractions.extend([vector, tuple(-v for v in vector)])
    for key, re, resolution, configs, nphases in (("re1000", 1000, 120, ("E1", "E2", "E3"), 16), ("re3000", 3000, 120, ("E1", "E2", "E3"), 16), ("confirmation", 3000, 180, ("E1", "E2"), 4)):
        dx = 0.2234 / resolution
        grid, role = ("confirmation", "confirmation") if key == "confirmation" else ("main", "primary")
        runs = []
        for phase, vector in enumerate(fractions[:nphases], 1):
            for config in configs:
                relative = f"docs/harness/topo2d00_scenes/{config}{'_fine' if resolution == 180 else ''}.json"
                digest, scene = scene_input(relative)
                _scene_declaration(scene, {"configuration": config, "height_mm": primary_height})
                height = scene["height_mm"]
                name = f"{config}_h{height:g}_re{re}_{grid}_k{phase:02d}"
                states[name] = {"kind": "scene", "scene_path": relative, "scene_sha256": digest,
                                "topo2d": {"configuration": scene["configuration"], "height_mm": height, "reynolds": float(re), "grid": grid, "phase": str(phase), "role": role}}
                runs.append({"state": name, "env": {SC.ORIGIN_ENV: f"{vector[0] * dx:.17g},0,{vector[1] * dx:.17g}"}})
        extras = []
        if resolution == 120:
            extras += [(config, "_h80", secondary_height, phase, "secondary") for phase in range(1, 5) for config in ("E1", "E2")]
        if key == "re3000":
            extras += [("E1", "", primary_height, 1, "determinism")]
            extras += [(config, "", primary_height, phase, "domain") for phase in (1, 2) for config in ("E1", "E2")]
        for config, suffix, declared_height, phase, extra_role in extras:
            vector = fractions[phase - 1]
            relative = f"docs/harness/topo2d00_scenes/{config}{suffix}.json"
            digest, scene = scene_input(relative)
            _scene_declaration(scene, {"configuration": config, "height_mm": declared_height})
            height = scene["height_mm"]
            name = f"{config}_h{height:g}_re{re}_{grid}_k{phase:02d}_{extra_role}"
            states[name] = {"kind": "scene", "scene_path": relative, "scene_sha256": digest,
                            "topo2d": {"configuration": scene["configuration"], "height_mm": height, "reynolds": float(re), "grid": grid, "phase": str(phase), "role": extra_role}}
            env = {SC.ORIGIN_ENV: f"{vector[0] * dx:.17g},0,{vector[1] * dx:.17g}"}
            if extra_role == "domain":
                env["TOPO2D_TOP_FACTOR"] = "1.5"
            runs.append({"state": name, "env": env})
        if resolution == 120:
            relative = "docs/harness/topo2d00_scenes/E1.json"
            digest, scene = scene_input(relative)
            name = f"E1_h{scene['height_mm']:g}_re{re}_main_k00_prerun"
            states[name] = {"kind": "scene", "scene_path": relative, "scene_sha256": digest,
                            "topo2d": {"configuration": "E1", "height_mm": scene["height_mm"], "reynolds": float(re), "grid": "main", "phase": "0", "role": "prerun"}}
            runs.append({"state": name, "env": {SC.ORIGIN_ENV: "0,0,0"}})
        cap = 21600 if resolution == 180 else 50400
        kernels[key] = {"kernel_id": f"ramhachi888/cfd-opt-sdf-topo2d00-{key}", "job": "scripts/waterlily_topo2d_job.jl",
                        "case": {"case_id": key, "flow_dims": [7 * resolution, round(6.8 * resolution) + 8], "flow_spacing_m": dx, "solver_length": float(resolution),
                                 "solver_time_unit_s": dx, "solver_viscosity": resolution / re, "reynolds": float(re), "density_kg_m3": 1.0,
                                 "dynamic_viscosity_pa_s": 0.2234 / re, "reference_length_m": 0.2234, "reference_area_m2": 0.2234, "freestream_mps": [1.0, 0.0, 0.0]},
                        "config": {"per_state_timeout_s": 3600, "solver_wall_time_cap_s": cap, "kernel_timeout_s": cap + 3600,
                                   "instantiate_timeout_s": 2400, "gpu_probe_timeout_s": 300, "reserve_s": 900, "formal_runner": "FROZEN_LOCAL_GPU_REQUIRES_BACKEND_AND_WINDOW_APPROVAL"}, "runs": runs}
    campaign = {"harness_version": SC.HARNESS_VERSION, "campaign_id": "topo2d00", "owner": "ramhachi888", "repo_url": "https://github.com/ramhachi/CFD_opt_sdf.git",
                "index_name": SC.INDEX_NAME_DEFAULT, "out_prefix": "topo2d00_", "job_env_common": {"TOPO2D_BACKEND": "cpu", "TOPO2D_WINDOW_FROZEN": "0"},
                "job_env_keys": ["TOPO2D_REYNOLDS", "TOPO2D_WINDOW_START", "TOPO2D_WINDOW_END", "TOPO2D_PHASE", "TOPO2D_GRID", "TOPO2D_ROLE", "TOPO2D_CASE_ID", "TOPO2D_TOP_FACTOR"],
                "scrub_env": [], "measurement": {"candidate_operator": "SetBody(min, AutoBody polygon elements); wing-only force", "time_window_t_u_l": None,
                "requires_parent_window_freeze": True, "force_unit": "N/m", "reference_chord_mm": 223.4,
                "window_formula": {"source": "TOPO-2D-00 section 5; RE-01 Stage-0", "minimum_multiple_c1_over_u": 50, "target_se_fraction": 0.015, "cap_c1_over_u": 400},
                "parent_prerun": {"configuration": "E1", "grid": "main", "phase": "0", "horizon_c1_over_u": 520,
                                  "measurement_window_c1_over_u": [80, 520], "record_template": "docs/harness/topo2d00_window_re<Re>.json",
                                  "estimator": "scripts/topo2d00/prerun_window.py", "formal_window": "hash-bound parent record; hand-entered windows refused"},
                "phase_rule": "JOB-02 R2 (0.7548776662,0.5698402910) fractional shifts centered at 0, k=1..8 with exact mirrors in x,z",
                "remaining_controls": "E1 parent pre-run force histories must fix windows before freeze; unavailable readout controls remain NOT_JUDGED until WP2 integration"},
                "domain": {"fluid_box_min_m": [-0.4468, 0.0, 0.0], "fluid_box_max_m": [1.117, 0.0, 1.51912], "solid_ground_padding_cells": 8}, "baseline": None, "directions": {},
                "states": states, "kernels": kernels, "sparse": ["julia/CFDSDFWaterLily/gen01", "docs/harness/topo2d00_scenes"], "pins": ["julia/CFDSDFWaterLily/gen01/Topo2D.jl", "src/cfd_harness/scene_campaign.py"], "legacy_replay": False}
    validate_campaign(campaign)
    return campaign


def run_cpu_smoke(campaign_path, kernel, output_dir, *, window, count=1, repo=ROOT, julia="julia"):
    """Execute an explicit short CPU capability smoke, never a formal campaign."""
    return _run_kernel(campaign_path, kernel, output_dir, window=window, count=count, repo=repo, julia=julia, smoke=True, backend="cpu")


def _run_kernel(campaign_path, kernel, output_dir, *, window, count, repo, julia, smoke, backend, freeze=None, pins=None, prerun=False):
    repo, output_dir = Path(repo).resolve(), Path(output_dir).resolve()
    c = SC.jload(campaign_path)
    validate_campaign(c)
    SC.req(kernel in c["kernels"] and not output_dir.exists(), "unknown kernel or existing CPU smoke output")
    k = c["kernels"][kernel]
    if not smoke:
        k = {**k, "runs": [run for run in k["runs"] if (c["states"][run["state"]]["topo2d"]["role"] == "prerun") is prerun]}
    SC.req(1 <= count <= len(k["runs"]) and all(math.isfinite(v) for v in window) and 0 <= window[0] < window[1], "CPU smoke run/window")
    _scene_records((c["states"][run["state"]] for run in k["runs"][:count]), repo)
    output_dir.mkdir(parents=True)
    paths = [str(Path(campaign_path).resolve().relative_to(repo)), *source_paths(backend, repo), *SC.TOOL_FILES]
    paths += [c["states"][r["state"]]["scene_path"] for r in k["runs"][:count]]
    pins = pins or {p: SC.sha256_path(repo / p) for p in sorted(set(paths))}
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    identity = {"schema": "topo2d-scene-run-identity-v1", "kernel": kernel, "campaign_sha256": SC.sha256_path(campaign_path), "smoke": smoke, "backend": "WaterLily CPU" if smoke else "WaterLily CUDA",
                "source_commit": commit, "pins": pins, "expected_names": SC.run_names(k)[:count], "prerun": prerun}
    index = {"kernel": kernel, "status": "RUNNING", "states": [], "solver_process_wall_seconds_total": 0.0}
    (output_dir / SC.IDENTITY_NAME).write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    stopped = {}
    def checkpoint_index():
        (output_dir / SC.INDEX_NAME_DEFAULT).write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    def finish_cap(position, reason, elapsed, limit, recorded=False):
        current = k["runs"][position]
        current_dir = output_dir / "states" / SC.run_name(current)
        preflight_path = current_dir / "job_preflight.json"
        preflight = SC.jload(preflight_path) if preflight_path.is_file() else None
        receipt = {"schema": "topo2d-cap-receipt-v1", "kernel": kernel, "reason": reason, "state": SC.run_name(current), "smoke": smoke,
                   "campaign_sha256": identity["campaign_sha256"], "source_commit": commit, "source_sha256": {p: pins[p] for p in source_paths(backend, repo)},
                   "prior_solver_wall_seconds": sum(e["seconds"] for e in index["states"][:position]), "elapsed_seconds": elapsed, "limit_seconds": limit,
                   "per_state_timeout_s": k["config"]["per_state_timeout_s"], "solver_wall_time_cap_s": k["config"]["solver_wall_time_cap_s"],
                   "runtime_expected": None if smoke else freeze["runtime"][kernel]["identity"],
                   "runtime_observed": None if preflight is None else preflight.get("runtime"),
                   "preflight_sha256": None if preflight is None else SC.sha256_path(preflight_path)}
        receipt_path = output_dir / "cap_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        digest = SC.sha256_path(receipt_path)
        if not recorded:
            index["solver_process_wall_seconds_total"] += elapsed
        for offset, pending in enumerate(k["runs"][position + int(recorded):count]):
            name = SC.run_name(pending)
            dest = output_dir / "states" / name
            dest.mkdir(parents=True, exist_ok=True)
            status = "INCOMPLETE_TIMEOUT" if offset == 0 and reason == "STATE_TIMEOUT" else "UNRUN_CAP"
            (dest / SC.ERROR_NAME).write_text(status + ": " + reason + "\n")
            index["states"].append({"name": name, "status": status, "seconds": elapsed if offset == 0 and not recorded else 0.0, "cap_receipt_sha256": digest})
        index["status"] = "INCOMPLETE"
        checkpoint_index()
        (output_dir / SC.ERROR_NAME).write_text("INCOMPLETE: " + reason + " at " + receipt["state"] + ".\n")
        (output_dir / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output_dir), indent=2, sort_keys=True) + "\n")
        return output_dir
    checkpoint_index()
    for position, run in enumerate(k["runs"][:count]):
        name, state = SC.run_name(run), c["states"][run["state"]]
        dest = output_dir / "states" / name
        dest.mkdir(parents=True)
        stop_key = numerical_stop_key(state["topo2d"])
        if stop_key in stopped:
            (dest / SC.ERROR_NAME).write_text("SKIPPED_NUMERICAL: this configuration/Re/height/role already failed.\n")
            index["states"].append({"name": name, "complete": False, "status": "SKIPPED_NUMERICAL", "seconds": 0.0, "prior_failure_sha256": stopped[stop_key]})
            checkpoint_index()
            continue
        SC.req(all(SC.sha256_path(repo / p) == digest for p, digest in pins.items()), "scene source changed before job launch")
        env = dict(job_environment(c, run, os.environ), W4_JOB_SHA256=pins[k["job"]], W4_SCENE_SHA256=state["scene_sha256"], TOPO2D_BACKEND=backend, TOPO2D_SMOKE="1" if smoke else "0", TOPO2D_WINDOW_FROZEN="0" if smoke else "1",
                   TOPO2D_REYNOLDS=str(k["case"]["reynolds"]), TOPO2D_WINDOW_START=str(window[0]), TOPO2D_WINDOW_END=str(window[1]), TOPO2D_SAMPLE_EVERY="1" if smoke else "8", TOPO2D_BATCHES="4" if smoke else "8",
                   TOPO2D_PHASE=str(state["topo2d"]["phase"]), TOPO2D_GRID=state["topo2d"]["grid"], TOPO2D_ROLE=state["topo2d"]["role"], TOPO2D_CASE_ID=k["case"]["case_id"],
                   TOPO2D_PYTHON=sys.executable, JULIA_NUM_THREADS="1")
        if not smoke:
            env["W4_SELECTED_GPU_UUID"] = freeze["backend_qualification"]["device_uuid"]
        started = time.monotonic()
        remaining = k["config"]["solver_wall_time_cap_s"] - index["solver_process_wall_seconds_total"]
        if remaining <= 0:
            return finish_cap(position, "SOLVER_WALL_CAP", 0.0, 0.0)
        try:
            with (dest / "job.log").open("w") as log:
                project = "CFDSDFWaterLilyT4" if backend == "cuda" else "CFDSDFWaterLily"
                result = subprocess.run([julia, "--startup-file=no", "--project=" + str(repo / "julia" / project), str(repo / k["job"]), str(repo / state["scene_path"]), str(dest)], env=env, stdout=log, stderr=subprocess.STDOUT, timeout=min(k["config"]["per_state_timeout_s"], remaining))
        except subprocess.TimeoutExpired:
            seconds = time.monotonic() - started
            return finish_cap(position, "STATE_TIMEOUT", seconds, min(k["config"]["per_state_timeout_s"], remaining))
        seconds = time.monotonic() - started
        index["solver_process_wall_seconds_total"] += seconds
        if result.returncode == 42:
            failure_path = dest / "numerical_failure.json"
            failure = SC.jload(failure_path)
            SC.req(failure.get("schema") == "topo2d-job-failure-v1" and failure.get("status") == "NUMERICAL" and failure.get("scene_sha256") == state["scene_sha256"] and failure.get("topo2d") == state["topo2d"], "numerical failure identity")
            SC.req(failure.get("smoke") is smoke and failure.get("source_sha256") == {p: pins[p] for p in source_paths(backend, repo)}, "numerical failure source identity")
            if not smoke:
                SC.req(failure.get("runtime") == freeze["runtime"][kernel]["identity"], "numerical failure runtime identity")
            stopped[stop_key] = SC.sha256_path(failure_path)
            index["states"].append({"name": name, "complete": False, "status": "NUMERICAL", "exit_code": 42, "seconds": seconds, "failure_sha256": SC.sha256_path(failure_path)})
            checkpoint_index()
            if seconds > min(k["config"]["per_state_timeout_s"], remaining):
                return finish_cap(position, "WALL_TIME_OVERRUN", seconds, min(k["config"]["per_state_timeout_s"], remaining), recorded=True)
            continue
        SC.req(result.returncode == 0, f"scene job failed: {dest / 'job.log'}")
        summary = SC.jload(dest / SC.summary_name(k["case"]["case_id"]))
        if not smoke:
            SC.req(summary["runtime"] == freeze["runtime"][kernel]["identity"], "actual runtime differs from frozen qualified runtime")
        index["states"].append({"name": name, "complete": True, "exit_code": 0, "seconds": seconds, "forces_csv_sha256": SC.sha256_path(dest / SC.forces_name(k["case"]["case_id"]))})
        checkpoint_index()
        if seconds > min(k["config"]["per_state_timeout_s"], remaining):
            return finish_cap(position, "WALL_TIME_OVERRUN", seconds, min(k["config"]["per_state_timeout_s"], remaining), recorded=True)
    index["status"] = "NUMERICAL" if stopped else "COMPLETE"
    checkpoint_index()
    if stopped:
        (output_dir / SC.ERROR_NAME).write_text("NUMERICAL: stopped (configuration, Re, height, role): " + ", ".join(map(str, sorted(stopped))) + "; unaffected states continued.\n")
    else:
        (output_dir / SC.DONE_NAME).write_text("CPU capability smoke only; not formal evidence.\n" if smoke else "Frozen scene kernel completed; host verification required.\n")
    (output_dir / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output_dir), indent=2, sort_keys=True) + "\n")
    return output_dir


def verify(campaign_path, kernel_dirs, freeze_path=None, smoke=False, repo=ROOT, source_commit=None, prerun=False):
    """Verify scene kernel directories and return the usual harness force table.

    A formal record needs an externally supplied freeze with exact source pins,
    per-Re windows and runtime identity. This function never writes a freeze.
    """
    repo, campaign_path = Path(repo).resolve(), Path(campaign_path).resolve()
    c = SC.jload(campaign_path)
    validate_campaign(c)
    csha = SC.sha256_path(campaign_path)
    SC.req(smoke == (freeze_path is None), "formal scene verification requires freeze; smoke takes none")
    SC.req(not (smoke and prerun), "formal parent pre-run verification cannot be a CPU smoke")
    freeze = None if smoke else SC.jload(freeze_path)
    if freeze is not None:
        sidecar = Path(str(freeze_path) + ".sha256")
        SC.req(sidecar.is_file() and sidecar.read_text().strip() == SC.sha256_path(freeze_path), "scene freeze sidecar")
        SC.req(freeze.get("campaign_sha256") == csha and freeze.get("kind") == SC.FREEZE_KIND and freeze.get("harness_version") == SC.HARNESS_VERSION, "scene freeze identity")
        SC.req(SC.COMMIT.fullmatch(freeze.get("source_commit", "")) is not None and freeze.get("scene_runner_approved") is True, "scene formal runner has not been approved")
    tables, manifests, cap_receipts = {}, {}, {}
    for directory in kernel_dirs:
        d = Path(directory)
        index, identity = SC.jload(d / SC.INDEX_NAME_DEFAULT), SC.jload(d / SC.IDENTITY_NAME)
        k = index.get("kernel")
        SC.req(k in c["kernels"] and k not in tables and index.get("status") in ("COMPLETE", "NUMERICAL", "INCOMPLETE"), "scene kernel identity/status")
        kernel = c["kernels"][k]
        if not smoke:
            kernel = {**kernel, "runs": [run for run in kernel["runs"] if (c["states"][run["state"]]["topo2d"]["role"] == "prerun") is prerun]}
            SC.req(kernel["runs"] and identity.get("prerun", False) is prerun, "scene pre-run/formal identity or empty kernel")
        window = None
        if freeze is not None:
            window = formal_context(c, campaign_path, k, freeze, repo, prerun=True) if prerun else formal_context(c, campaign_path, k, freeze, repo)
        names = SC.run_names(kernel)
        if smoke:
            names = identity.get("expected_names")
            SC.req(isinstance(names, list) and names and names == SC.run_names(kernel)[:len(names)], "scene smoke run order")
        SC.req(identity.get("smoke") is smoke and identity.get("campaign_sha256") == csha, "scene campaign/smoke identity")
        SC.req([e.get("name") for e in index["states"]] == names, "scene exact run order")
        numerical, capped = index["status"] == "NUMERICAL", index["status"] == "INCOMPLETE"
        SC.req(((d / SC.ERROR_NAME).is_file() and not (d / SC.DONE_NAME).exists()) if numerical or capped else ((d / SC.DONE_NAME).is_file() and not any(d.rglob(SC.ERROR_NAME))), "scene DONE/error")
        needed = {SC.INDEX_NAME_DEFAULT, SC.IDENTITY_NAME, SC.ERROR_NAME if numerical or capped else SC.DONE_NAME}
        if capped:
            needed.add("cap_receipt.json")
        for entry in index["states"]:
            status = entry.get("status", "COMPLETE" if entry.get("complete") is True else None)
            allowed = ("COMPLETE", "NUMERICAL", "SKIPPED_NUMERICAL") if numerical or capped else ("COMPLETE",)
            SC.req(status in allowed + (("INCOMPLETE_TIMEOUT", "UNRUN_CAP") if capped else ()), "scene unregistered state status")
            suffixes = (SC.forces_name(kernel["case"]["case_id"]), SC.summary_name(kernel["case"]["case_id"]), SC.JOB_DONE_NAME) if status == "COMPLETE" else (("numerical_failure.json", SC.ERROR_NAME) if status == "NUMERICAL" else (SC.ERROR_NAME,))
            needed |= {f"states/{entry['name']}/{suffix}" for suffix in suffixes}
        SC.check_manifest(d, needed)
        SC.req({p.name for p in (d / "states").iterdir() if p.is_dir()} == set(names), "scene state directory set")
        SC.req(SC.COMMIT.fullmatch(identity.get("source_commit", "")) is not None and (source_commit is None or identity["source_commit"] == source_commit), "scene source commit")
        needed_pins = {str(campaign_path.relative_to(repo)), kernel["job"], *source_paths("cpu" if smoke else "cuda", repo)}
        needed_pins |= {c["states"][r["state"]]["scene_path"] for r in kernel["runs"][:len(names)]}
        SC.req(isinstance(identity.get("pins"), dict) and needed_pins <= set(identity["pins"]), "scene run pins omit required source/scene files")
        if not smoke:
            SC.req(identity["source_commit"] == freeze["source_commit"] and identity["pins"] == freeze["pins"][k], "scene source/freeze pins")
        for rel, digest in identity["pins"].items():
            SC.safe_rel(rel)
            SC.req(SC.is_sha(digest) and SC.sha256_path(repo / rel) == digest, f"scene source hash differs: {rel}")
        if capped:
            receipt_path = d / "cap_receipt.json"
            receipt, digest = SC.jload(receipt_path), SC.sha256_path(receipt_path)
            SC.req(receipt.get("schema") == "topo2d-cap-receipt-v1" and receipt.get("reason") in ("STATE_TIMEOUT", "SOLVER_WALL_CAP", "WALL_TIME_OVERRUN") and receipt.get("kernel") == k, "scene cap receipt kind/reason")
            SC.req(receipt.get("campaign_sha256") == csha and receipt.get("source_commit") == identity["source_commit"] and receipt.get("smoke") is smoke, "scene cap campaign/source identity")
            SC.req(receipt.get("source_sha256") == {p: identity["pins"][p] for p in source_paths("cpu" if smoke else "cuda", repo)}, "scene cap source hashes")
            positions = [i for i, e in enumerate(index["states"]) if e.get("status") in ("INCOMPLETE_TIMEOUT", "UNRUN_CAP")]
            SC.req(receipt.get("state") in names, "scene cap state")
            cap_position = names.index(receipt["state"])
            overrun = receipt["reason"] == "WALL_TIME_OVERRUN"
            SC.req(positions == list(range(cap_position + int(overrun), len(names))), "scene cap must describe the exact unmeasured run suffix")
            prior = sum(SC.finite(e["seconds"]) for e in index["states"][:cap_position])
            elapsed, limit = SC.finite(receipt["elapsed_seconds"]), SC.finite(receipt["limit_seconds"])
            SC.req(receipt.get("prior_solver_wall_seconds") == prior and receipt.get("per_state_timeout_s") == kernel["config"]["per_state_timeout_s"] and receipt.get("solver_wall_time_cap_s") == kernel["config"]["solver_wall_time_cap_s"], "scene cap budget identity")
            if receipt["reason"] in ("STATE_TIMEOUT", "WALL_TIME_OVERRUN"):
                expected_limit = min(kernel["config"]["per_state_timeout_s"], kernel["config"]["solver_wall_time_cap_s"] - prior)
                SC.req(0 < limit == expected_limit <= elapsed, "scene timeout/overrun does not meet its pinned budget")
                if overrun:
                    measured = index["states"][cap_position]
                    SC.req(limit < elapsed == measured.get("seconds") and (measured.get("complete") is True or measured.get("status") == "NUMERICAL"), "scene wall overrun lacks a measured result")
                else:
                    SC.req(index["states"][cap_position].get("status") == "INCOMPLETE_TIMEOUT", "scene timeout status")
            else:
                SC.req(prior >= kernel["config"]["solver_wall_time_cap_s"] and limit == elapsed == 0, "scene aggregate cap was not exhausted")
                SC.req(receipt.get("preflight_sha256") is None and receipt.get("runtime_observed") is None, "unrun aggregate-cap state cannot claim an observed runtime")
            for offset, position in enumerate(positions):
                entry = index["states"][position]
                want = "INCOMPLETE_TIMEOUT" if offset == 0 and receipt["reason"] == "STATE_TIMEOUT" else "UNRUN_CAP"
                SC.req(entry.get("status") == want and entry.get("seconds") == (elapsed if offset == 0 and not overrun else 0) and entry.get("cap_receipt_sha256") == digest, "scene cap suffix receipt/elapsed identity")
            SC.req(receipt.get("runtime_expected") == (None if smoke else freeze["runtime"][k]["identity"]), "scene cap expected runtime differs from qualified freeze")
            preflight_path = d / "states" / receipt["state"] / "job_preflight.json"
            if receipt.get("preflight_sha256") is None:
                SC.req(receipt.get("runtime_observed") is None and not preflight_path.exists(), "unobserved cap runtime must remain explicit")
            else:
                SC.req(SC.is_sha(receipt["preflight_sha256"]) and SC.sha256_path(preflight_path) == receipt["preflight_sha256"], "scene cap preflight hash")
                preflight = SC.jload(preflight_path)
                state = c["states"][receipt["state"]]
                run = kernel["runs"][cap_position]
                SC.req(preflight.get("schema") == "topo2d-job-preflight-v1" and preflight.get("topo2d") == state["topo2d"] and preflight.get("scene_sha256") == state["scene_sha256"] and preflight.get("source_sha256") == receipt["source_sha256"], "scene cap preflight source/scene identity")
                validate_observable(preflight, state["topo2d"]["height_mm"])
                SC.req(preflight.get("smoke") is smoke and preflight.get("phase_shift_m") == SC.floats(run["env"][SC.ORIGIN_ENV]) and SC.is_sha(preflight.get("contract_fingerprint")), "scene cap preflight phase/contract")
                expected_dims = list(kernel["case"]["flow_dims"])
                expected_dims[1] = round((expected_dims[1] - 8) * float(run["env"].get("TOPO2D_TOP_FACTOR", "1"))) + 8
                a, b = preflight["window_t_u_l"]
                SC.req(preflight.get("flow_dims") == expected_dims and 0 <= SC.finite(a) < SC.finite(b), "scene cap preflight grid/window")
                observed = preflight.get("runtime", {})
                SC.req(receipt.get("runtime_observed") == observed and observed.get("waterlily_version") == "1.8.0" and observed.get("memory") == ("Array" if smoke else "CuArray") and observed.get("threads") == 1 and observed.get("scalar_type") == "Float32" and observed.get("scheme") == "quick", "scene cap observed runtime")
                if not smoke:
                    SC.req(observed == freeze["runtime"][k]["identity"] and preflight.get("window_t_u_l") == window, "scene cap preflight qualified runtime/window")
            cap_receipts[k] = {"sha256": digest, "record": receipt}
        states, total, failures = {}, 0.0, {}
        for entry, run in zip(index["states"], kernel["runs"]):
            name = SC.run_name(run)
            row = c["states"][run["state"]]
            scene_path = repo / SC.safe_rel(row["scene_path"])
            scene_record(scene_path, row["scene_sha256"], row["topo2d"])
            case = kernel["case"]
            state_dir = d / "states" / name
            stop_key = numerical_stop_key(row["topo2d"])
            if entry.get("status") in ("INCOMPLETE_TIMEOUT", "UNRUN_CAP"):
                SC.req(not (state_dir / "numerical_failure.json").exists(), "budget marker cannot hide a recorded numerical failure")
                if entry["status"] == "UNRUN_CAP":
                    SC.req({p.name for p in state_dir.iterdir()} == {SC.ERROR_NAME}, "unrun cap state contains solver outputs")
                total += SC.finite(entry["seconds"])
                states[name] = {"topo2d": row["topo2d"], "scene_sha256": row["scene_sha256"], "status": entry["status"], "cap_receipt_sha256": cap_receipts[k]["sha256"]}
                continue
            if entry.get("status") == "SKIPPED_NUMERICAL":
                SC.req(entry.get("complete") is False and entry.get("seconds") == 0 and entry.get("prior_failure_sha256") == failures.get(stop_key) and stop_key in failures, "skipped scene lacks an earlier authenticated failure for this configuration/Re/height/role")
                SC.req({p.name for p in state_dir.iterdir()} == {SC.ERROR_NAME}, "skipped scene contains solver outputs")
                states[name] = {"observable": "total_cl", "topo2d": row["topo2d"], "scene_sha256": row["scene_sha256"], "ok": False, "finite": None, "complete": False,
                                "status": "SKIPPED_NUMERICAL", "prior_failure_sha256": failures[stop_key], "drag_n": None, "downforce_n": None, "readouts": dict.fromkeys(READOUTS)}
                continue
            SC.req(stop_key not in failures, "a configuration/Re/height/role continued after its registered numerical stop")
            if entry.get("status") == "NUMERICAL":
                failure_path = state_dir / "numerical_failure.json"
                failure = SC.jload(failure_path)
                digest = SC.sha256_path(failure_path)
                SC.req(entry.get("complete") is False and entry.get("exit_code") == 42 and entry.get("failure_sha256") == digest, "scene numerical failure index/hash")
                SC.req(failure.get("schema") == "topo2d-job-failure-v1" and failure.get("status") == "NUMERICAL" and failure.get("topo2d") == row["topo2d"] and failure.get("scene_sha256") == row["scene_sha256"], "scene numerical failure identity")
                validate_observable(failure, row["topo2d"]["height_mm"])
                SC.req(failure.get("source_sha256") == {p: identity["pins"][p] for p in source_paths("cpu" if smoke else "cuda", repo)}, "scene numerical failure source identity")
                SC.req(failure.get("smoke") is smoke and failure.get("phase_shift_m") == SC.floats(run["env"][SC.ORIGIN_ENV]) and SC.is_sha(failure.get("contract_fingerprint")), "scene numerical failure phase/contract")
                runtime = failure.get("runtime", {})
                SC.req(runtime.get("waterlily_version") == "1.8.0" and runtime.get("scalar_type") == "Float32" and runtime.get("scheme") == "quick" and runtime.get("threads") == 1 and runtime.get("memory") == ("Array" if smoke else "CuArray"), "scene numerical failure runtime")
                start, end = failure["window_t_u_l"]
                SC.req(0 <= SC.finite(start) < SC.finite(end) and isinstance(failure.get("reason"), str) and failure["reason"], "scene numerical failure window/reason")
                expected_dims = list(case["flow_dims"])
                expected_dims[1] = round((expected_dims[1] - 8) * float(run["env"].get("TOPO2D_TOP_FACTOR", "1"))) + 8
                SC.req(failure.get("flow_dims") == expected_dims, "scene numerical failure grid")
                if freeze is not None:
                    SC.req([start, end] == window and runtime == freeze["runtime"][k]["identity"], "scene numerical failure frozen window/runtime")
                wall = SC.finite(entry["seconds"])
                is_overrun = capped and cap_receipts[k]["record"]["reason"] == "WALL_TIME_OVERRUN" and cap_receipts[k]["record"]["state"] == name
                SC.req(0 < SC.finite(failure["wall_seconds"]) <= wall and (wall <= kernel["config"]["per_state_timeout_s"] or is_overrun), "scene numerical failure wall budget")
                total += wall
                failures[stop_key] = digest
                states[name] = {"observable": "total_cl", "topo2d": row["topo2d"], "scene_sha256": row["scene_sha256"], "ok": False, "finite": False, "complete": False,
                                "status": "NUMERICAL", "failure_sha256": digest, "drag_n": None, "downforce_n": None, "readouts": dict.fromkeys(READOUTS), "solver_process_wall_seconds": wall}
                continue
            csv_path, summary_path = state_dir / SC.forces_name(case["case_id"]), state_dir / SC.summary_name(case["case_id"])
            summary = SC.jload(summary_path)
            SC.req(summary.get("force_csv_sha256") == SC.sha256_path(csv_path), "scene summary CSV hash differs")
            source_shas = summary.get("source_sha256")
            SC.req(isinstance(source_shas, dict) and set(source_shas) == needed_pins - {str(campaign_path.relative_to(repo))} - {c["states"][r["state"]]["scene_path"] for r in kernel["runs"][:len(names)]}, "scene summary source set")
            SC.req(all(identity["pins"].get(p) == h for p, h in source_shas.items()), "scene job source hash differs from runner")
            SC.req(entry.get("complete") is True and entry.get("exit_code") == 0 and entry.get("forces_csv_sha256") == SC.sha256_path(csv_path), "scene incomplete/csv index")
            wall = SC.finite(entry["seconds"])
            is_overrun = capped and cap_receipts[k]["record"]["reason"] == "WALL_TIME_OVERRUN" and cap_receipts[k]["record"]["state"] == name
            SC.req(0 < wall and (wall <= kernel["config"]["per_state_timeout_s"] or is_overrun), "scene state wall budget")
            total += wall
            SC.req(summary.get("scene_sha256") == row["scene_sha256"] and summary.get("topo2d") == row["topo2d"], "scene job identity")
            validate_observable(summary, row["topo2d"]["height_mm"])
            SC.req(summary.get("phase_shift_m") == SC.floats(run["env"][SC.ORIGIN_ENV]), "scene job phase")
            SC.req(summary.get("force_unit") == "N/m" and summary.get("reference_chord_mm") == 223.4, "scene force units")
            SC.req(summary.get("smoke") is smoke and (summary.get("backend") == "WaterLily CPU" if smoke else summary.get("backend") == freeze["runtime"][k]["backend"]), "scene runtime backend/smoke")
            SC.req(summary.get("runtime", {}).get("waterlily_version") == "1.8.0" and summary["runtime"].get("scalar_type") == "Float32" and summary["runtime"].get("scheme") == "quick", "scene pinned solver runtime")
            SC.req(summary["runtime"].get("threads") == 1, "scene Julia thread identity")
            SC.req(all(summary.get(f) is True for f in ("finite_u", "finite_p", "finite_forces")), "scene nonfinite")
            expected_dims = list(case["flow_dims"])
            top_factor = float(run["env"].get("TOPO2D_TOP_FACTOR", "1"))
            expected_dims[1] = round((expected_dims[1] - 8) * top_factor) + 8
            SC.req(summary.get("flow_dims") == expected_dims and summary.get("top_factor") == top_factor and math.isclose(summary.get("solver_length", 0), case["solver_length"], rel_tol=1e-12), "scene grid identity")
            origin = summary.get("flow_origin_m", [])
            SC.req(len(origin) == 3 and all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15) for a, b in zip(origin, [-0.4468, 0.0, -8 * case["flow_spacing_m"]])), "scene physical flow origin/solid ground padding")
            SC.req(math.isclose(summary.get("reynolds", 0), case["reynolds"], rel_tol=1e-12), "scene Reynolds identity")
            start, end = summary["window_t_u_l"]
            SC.req(0 <= SC.finite(start) < SC.finite(end) <= SC.finite(summary["t_end_reached"]), "scene window/horizon")
            SC.req(0 < SC.finite(summary["wall_seconds"]) <= wall and (summary["wall_seconds"] <= kernel["config"]["per_state_timeout_s"] or is_overrun), "scene Julia wall budget")
            if freeze is not None:
                SC.req([start, end] == window and summary["runtime"] == freeze["runtime"][k]["identity"], "scene frozen window/runtime")
            scale = case["density_kg_m3"] * case["freestream_mps"][0] ** 2 * case["flow_spacing_m"]
            element_names = [element["name"] for element in SC.jload(scene_path)["elements"]]
            host = host_readouts(csv_path, start=start, end=end, solver_length=case["solver_length"], force_scale=scale, available=summary["readout_available"], batches=summary["batch_count"], element_names=element_names)
            for q in ("drag", "downforce"):
                SC.req(math.isclose(host[q + "_n"], summary[q + "_time_weighted_n_per_m"], rel_tol=1e-9, abs_tol=1e-12), "scene host/Julia force mismatch")
            states[name] = {**host, "topo2d": row["topo2d"], "scene_sha256": row["scene_sha256"], "ok": True, "finite": True, "complete": True,
                            "forces_csv_sha256": SC.sha256_path(csv_path), "summary_sha256": SC.sha256_path(summary_path), "solver_process_wall_seconds": wall, "julia_summary_wall_seconds": summary["wall_seconds"]}
        SC.req(capped or bool(failures) is numerical, "scene kernel numerical status lacks an actual failure")
        SC.req((capped or total <= kernel["config"]["solver_wall_time_cap_s"]) and math.isclose(total, index["solver_process_wall_seconds_total"], rel_tol=1e-12), "scene aggregate wall budget")
        tables[k], manifests[k] = states, SC.sha256_path(d / SC.MANIFEST_NAME)
    expected_kernels = {key for key, row in c["kernels"].items() if any((c["states"][run["state"]]["topo2d"]["role"] == "prerun") is prerun for run in row["runs"])}
    SC.req(len(tables) == 1 if smoke else set(tables) == expected_kernels, "scene required kernel set")
    return {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_id": c["campaign_id"], "campaign_sha256": csha, "source_commit": identity["source_commit"],
            "smoke": smoke, "prerun": prerun, "legacy_replay": False, "freeze_sha256": None if smoke else SC.sha256_path(freeze_path), "harness_tool_sha256": {**SC.tool_hashes(), "src/cfd_harness/scene_campaign.py": SC.sha256_path(__file__)},
            "integrity": {"pass": True, "failures": []}, "kernel_manifest_sha256": manifests, "force_unit": "N/m", "cap_hit": bool(cap_receipts), "cap_receipts": cap_receipts, "state_forces_n": tables}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    wire = sub.add_parser("wire")
    wire.add_argument("scene", type=Path)
    wire.add_argument("expected_sha")
    summary = sub.add_parser("summary-json")
    summary.add_argument("toml", type=Path)
    summary.add_argument("out", type=Path)
    cpu = sub.add_parser("cpu-smoke", help="short CPU capability only; does not freeze or publish")
    cpu.add_argument("campaign", type=Path)
    cpu.add_argument("kernel")
    cpu.add_argument("out", type=Path)
    cpu.add_argument("--start", type=float, required=True)
    cpu.add_argument("--end", type=float, required=True)
    cpu.add_argument("--count", type=int, default=1)
    validate = sub.add_parser("validate")
    validate.add_argument("campaign", type=Path)
    rendered = sub.add_parser("render", help="render a pinned existing-checkout local runner; no launch")
    rendered.add_argument("campaign", type=Path)
    rendered.add_argument("--source-commit", required=True)
    rendered.add_argument("--kernel", required=True)
    rendered.add_argument("--smoke", action="store_true")
    rendered.add_argument("--out", required=True, type=Path)
    frozen = sub.add_parser("run-frozen", help="future execution only after external backend/window/source approval")
    frozen.add_argument("campaign", type=Path)
    frozen.add_argument("kernel")
    frozen.add_argument("out", type=Path)
    frozen.add_argument("--freeze", required=True, type=Path)
    frozen.add_argument("--source-commit", required=True)
    frozen.add_argument("--prerun", action="store_true", help="run only the E1 phase-0 parent at horizon 520; no derived window needed yet")
    checked = sub.add_parser("verify")
    checked.add_argument("campaign", type=Path)
    checked.add_argument("outputs", nargs="+", type=Path)
    checked.add_argument("--freeze", type=Path)
    checked.add_argument("--smoke", action="store_true")
    checked.add_argument("--source-commit")
    checked.add_argument("--prerun", action="store_true", help="verify only the two parent pre-run kernels")
    checked.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "wire":
        print(scene_wire(args.scene, args.expected_sha), end="")
    elif args.command == "summary-json":
        record = tomllib.loads(args.toml.read_text())
        with args.out.open("x") as handle:
            handle.write(json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n")
    elif args.command == "cpu-smoke":
        print(run_cpu_smoke(args.campaign, args.kernel, args.out, window=(args.start, args.end), count=args.count))
    elif args.command == "validate":
        campaign = SC.jload(args.campaign)
        validate_campaign(campaign)
        _scene_records(campaign["states"].values(), ROOT)
        print("PASS: unfrozen harness v1.1 scene extension; formal execution requires external freeze and qualified backend")
    elif args.command == "render":
        text = render(args.campaign, args.source_commit, args.kernel, args.smoke)
        with args.out.open("x") as handle:
            handle.write(text)
    elif args.command == "run-frozen":
        campaign = SC.jload(args.campaign)
        pins = scene_pins(campaign, str(args.campaign.resolve().relative_to(ROOT)), args.kernel)
        print(run_frozen_kernel(args.campaign, args.kernel, args.out, args.freeze, expected_commit=args.source_commit, expected_pins=pins, prerun=args.prerun))
    else:
        table = verify(args.campaign, args.outputs, args.freeze, args.smoke, source_commit=args.source_commit, prerun=args.prerun)
        text = json.dumps(table, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.out is None:
            print(text, end="")
        else:
            with args.out.open("x") as handle:
                handle.write(text)


if __name__ == "__main__":
    main()
