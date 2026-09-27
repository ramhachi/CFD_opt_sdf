#!/usr/bin/env python3
"""Run the registered W2b analytic/GridSDF flow-grid ladder on Kaggle T4."""

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path


STAGE = "w2b"
OUT = Path("/kaggle/working") / STAGE
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
SOURCE_FETCH_DEPTH = 8
SOURCE_COMMIT = "548231050fc6ca22bc1c0394272564f81571dbbc"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT_SHA256 = "e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194"
MANIFEST_SHA256 = "c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707"
CRITERIA_SHA256 = "3573b903c2ff025db62cb184ba328f81c48da70f72d4393e3623bd3bbb58bf1c"
CANONICAL_PHI_SHA256 = "393d5d7897885d71cda0902129a4aa3db561c59b1a85e8e221d55ce19fca4161"
CUDA_DRIVER_API_VERSION = "13.3.0"
CUDA_RUNTIME_VERSION = "12.8.0"
W2T4A_ANALYTIC_DRAG = 88.42577373189188
W2T4B_GRID_SDF_DRAG = 88.23605899425723
STATIONARITY_TOL = 0.02
LIFT_RATIO_TOL = 0.10
T4_BASELINE_DRAG_TOL = 0.01
GEOMETRY_CD_TOL = 0.01
FINEST_GRID_CD_TOL = 0.03
PHI_MARGIN_MIN_M = 0.15
PHI_MARGIN_EXPECTED_M = 0.19999998807907104
PHI_MARGIN_TOL_M = 1e-6
T_END = 60.0

REGISTERED_INPUTS = {
    "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl": "2f02c840f4fad5ba5d26d42f4c24bc83f413502b15487427a7dc52f06a80a874",
    "julia/CFDSDFWaterLily/src/Forces.jl": "0e5a6b9dae2a5a3044a9ed08162a42ceb9e5ea5fac41585e7a758184205adc8e",
    "julia/CFDSDFWaterLily/src/GridSDFBody.jl": "fa6aecccecbf140158396c9c8e5f3a6c16d3810f792ba45b9c8f4ee481709058",
    "scripts/waterlily_w2b_grid_ladder_job.jl": "e907cf1e038ce76556533a59c2f1ce1ebb7de51c7ad134e0b3f6756ad34b9a26",
    "docs/evidence/kaggle_k0_result_2026_09.json": "0f9176083c2cb2503101b7f69fd48ef9bc24f15f63d7d187e32bc8eef4cda719",
    "julia/CFDSDFWaterLilyT4/Manifest.toml": MANIFEST_SHA256,
    "julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl": "996224432490df72726e208ad36d1a68657b506ba4058d79a0f9eb72154d4e9e",
    "julia/CFDSDFWaterLilyT4/Project.toml": PROJECT_SHA256,
    "julia/CFDSDFWaterLily/src/Runtime.jl": "bd830f7f307f7bd5de67642b4e9243ae5586959fd475765b13ef14d19637d458",
    "julia/CFDSDFWaterLily/src/Simulation.jl": "99cfc7a30741c17b7e83f4451270e0536e336dd2c79cc1f904492910e8588cc2",
    "docs/evidence/kaggle_w1g_round2_result_2026_09.json": "bb233f72068b5c6681b9f3f9b4dba180b538f945f8283312fb521c24ac802eb8",
    "docs/evidence/sdf_native_w2a_sphere_cpu_criteria_2026_09.json": "aea91e6cc8de65ef072b3fbb19a3ca50a01b5e75198e62c128fda3fe8849602f",
    "docs/evidence/sdf_native_w2a_sphere_cpu_2026_09.json": "26b6a65f6a2f89dde7e9976b2209b776eeb90d895432707214a582e9192f920b",
    "docs/evidence/sdf_native_w2t4a_analytic_sphere_criteria_2026_09.json": "154fec9111737f8cb76579f0a02fd2d6b4c043c30250d1d24b8a5d05b3ea15ad",
    "docs/evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json": "70f747e264bacc9c3360ab9d6445c7bb77e6b11a6a6d521271297780301af754",
    "docs/evidence/kaggle_w2t4b_criteria_2026_09_round2.json": "85bd5ba4f6ff0a13c7f0509b1ba86b74cfeb7bc346fc590b27a819ce3f228e66",
    "docs/evidence/kaggle_w2t4b_round2_result_2026_09.json": "737ea3f6946b0eb3867902ea2b1db8bc6c92ccb8f45de30f664cd34dd2fb4b82",
    "julia/CFDSDFWaterLily/src/WaterLilyBody.jl": "e5b9329fbf29bc86fa1eb1a5481b255535e255e04418d0d2582f1d33e42df369",
}

W2B_CASES = [
    {"case_id": "analytic_16", "mode": "analytic", "cells_per_diameter": 16,
     "flow_dims": (96, 64, 64), "solver_center": (32, 32, 32), "solver_radius": 8.0,
     "u_inf": 1.0, "reynolds": 100.0, "viscosity": 0.16,
     "world_origin_m": (-1.75, -2.0, -2.0), "world_per_solver": 0.0625},
    {"case_id": "gridsdf_16", "mode": "gridsdf", "cells_per_diameter": 16,
     "flow_dims": (96, 64, 64), "solver_center": (32, 32, 32), "solver_radius": 8.0,
     "u_inf": 1.0, "reynolds": 100.0, "viscosity": 0.16,
     "world_origin_m": (-1.75, -2.0, -2.0), "world_per_solver": 0.0625},
    {"case_id": "analytic_24", "mode": "analytic", "cells_per_diameter": 24,
     "flow_dims": (144, 96, 96), "solver_center": (48, 48, 48), "solver_radius": 12.0,
     "u_inf": 1.0, "reynolds": 100.0, "viscosity": 0.24,
     "world_origin_m": (-1.75, -2.0, -2.0), "world_per_solver": 1.0 / 24.0},
    {"case_id": "gridsdf_24", "mode": "gridsdf", "cells_per_diameter": 24,
     "flow_dims": (144, 96, 96), "solver_center": (48, 48, 48), "solver_radius": 12.0,
     "u_inf": 1.0, "reynolds": 100.0, "viscosity": 0.24,
     "world_origin_m": (-1.75, -2.0, -2.0), "world_per_solver": 1.0 / 24.0},
    {"case_id": "analytic_32", "mode": "analytic", "cells_per_diameter": 32,
     "flow_dims": (192, 128, 128), "solver_center": (64, 64, 64), "solver_radius": 16.0,
     "u_inf": 1.0, "reynolds": 100.0, "viscosity": 0.32,
     "world_origin_m": (-1.75, -2.0, -2.0), "world_per_solver": 1.0 / 32.0},
    {"case_id": "gridsdf_32", "mode": "gridsdf", "cells_per_diameter": 32,
     "flow_dims": (192, 128, 128), "solver_center": (64, 64, 64), "solver_radius": 16.0,
     "u_inf": 1.0, "reynolds": 100.0, "viscosity": 0.32,
     "world_origin_m": (-1.75, -2.0, -2.0), "world_per_solver": 1.0 / 32.0},
]
CASE_IDS = [case["case_id"] for case in W2B_CASES]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_hash(path, expected):
    if sha256(path) != expected:
        raise RuntimeError(f"SHA-256 mismatch: {path}")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def command(args, log_path, *, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with log_path.open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {log_path.name}")
    return log_path.read_text(errors="replace")


def gpu_inventory():
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
         "--format=csv,noheader"], text=True)
    (OUT / "nvidia_smi.csv").write_text(text)
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if len(rows) != 2 or [row.split(",", 1)[0] for row in rows] != ["0", "1"]:
        raise RuntimeError("W2b requires exactly GPU indexes 0 and 1")
    if any("Tesla T4" not in row or row.split(", ")[-1] != "580.159.04" for row in rows):
        raise RuntimeError("W2b T4/driver cohort mismatch")
    uuids = [row.split(", ")[2] for row in rows]
    if len(set(uuids)) != 2 or any(not uuid.startswith("GPU-") for uuid in uuids):
        raise RuntimeError("W2b GPU UUID inventory invalid")
    return rows


def fetch_source(base):
    source = base / "source"
    command(["git", "init", "-q", str(source)], OUT / "git_init.log")
    command(["git", "-C", str(source), "fetch", "--depth", str(SOURCE_FETCH_DEPTH),
             SOURCE_URL, SOURCE_REF], OUT / "git_fetch.log", timeout=600)
    command(["git", "-C", str(source), "checkout", "--detach", SOURCE_COMMIT],
            OUT / "git_checkout.log")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError("W2b source commit drift")
    for path, expected in REGISTERED_INPUTS.items():
        check_hash(source / path, expected)
    project = source / "julia/CFDSDFWaterLilyT4"
    return source, project


def install_julia(base):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia binary SHA-256 mismatch")
    command(["tar", "-xzf", str(archive), "-C", str(base)], OUT / "julia_extract.log",
            timeout=600)
    julia = base / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("verified Julia binary was not extracted")
    return julia


def jl_tuple(values):
    return "(" + ", ".join(repr(value) for value in values) + ")"


def write_params():
    fields = []
    for case in W2B_CASES:
        values = {
            "case_id": json.dumps(case["case_id"]),
            "mode": json.dumps(case["mode"]),
            "cells_per_diameter": str(case["cells_per_diameter"]),
            "flow_dims": jl_tuple(case["flow_dims"]),
            "solver_center": jl_tuple(case["solver_center"]),
            "solver_radius": repr(case["solver_radius"]),
            "u_inf": repr(case["u_inf"]),
            "reynolds": repr(case["reynolds"]),
            "viscosity": repr(case["viscosity"]),
            "world_origin_m": jl_tuple(case["world_origin_m"]),
            "world_per_solver": repr(case["world_per_solver"]),
            "t_end": "60.0",
            "burn_in": "40.0",
            "sample_every": "4",
        }
        fields.append("    (" + ", ".join(f"{key}={value}" for key, value in values.items()) + ")")
    path = OUT / "params.jl"
    path.write_text("const W2B_CASES = (\n" + ",\n".join(fields) + ",\n)\n")
    return path


def relative(a, b):
    if not math.isfinite(a) or not math.isfinite(b) or a == 0 or b == 0:
        raise ValueError("response is zero or non-finite")
    return abs(a - b) / max(abs(a), abs(b))


def w2b_gates(summaries, finite_force_csv, rows, smoke, prerequisites_ok=True):
    cases = {case["case_id"]: case for case in W2B_CASES}
    complete = set(summaries) == set(CASE_IDS)
    if not complete:
        summaries = {}
    all_summaries = [summaries.get(case_id, {}) for case_id in CASE_IDS]
    def all_case(predicate):
        return complete and all(predicate(case_id, summary) for case_id, summary in zip(CASE_IDS, all_summaries))

    t1 = all_case(lambda case_id, s: s.get("case_id") == case_id
                  and s.get("mode") == cases[case_id]["mode"]
                  and s.get("cells_per_diameter") == cases[case_id]["cells_per_diameter"]
                  and s.get("flow_dims") == list(cases[case_id]["flow_dims"])
                  and s.get("solver_center") == list(cases[case_id]["solver_center"])
                  and s.get("solver_radius") == cases[case_id]["solver_radius"]
                  and s.get("reynolds") == cases[case_id]["reynolds"]
                  and s.get("viscosity") == cases[case_id]["viscosity"]
                  and s.get("world_origin_m") == list(cases[case_id]["world_origin_m"])
                  and math.isclose(s.get("world_per_solver", math.nan),
                                   cases[case_id]["world_per_solver"], rel_tol=0, abs_tol=1e-12)
                  and s.get("steps", 0) > 0 and s.get("t_end_target") == T_END
                  and s.get("t_end_reached", 0) >= T_END)
    t2 = all_case(lambda _, s: s.get("finite_u") is True and s.get("finite_p") is True)
    t3 = all_case(lambda case_id, s: s.get("finite_forces") is True
                  and s.get("force_samples", 0) > 0
                  and finite_force_csv.get(case_id, False))
    t4 = all_case(lambda _, s: math.isfinite(s.get("window_mean_drag", math.nan))
                  and s.get("window_mean_drag", 0) > 0)
    t5 = all_case(lambda _, s: s.get("window_mean_drag", 0) != 0
                  and abs(s.get("first_half_mean_drag", math.nan)
                          - s.get("second_half_mean_drag", math.nan))
                  / abs(s.get("window_mean_drag", 1)) <= STATIONARITY_TOL)
    t6 = all_case(lambda _, s: s.get("window_mean_drag", 0) > 0
                  and abs(s.get("window_mean_lift", math.inf))
                  / s.get("window_mean_drag", 1) <= LIFT_RATIO_TOL)
    t7 = all_case(lambda case_id, s: (
        (s.get("phi_sha256") == CANONICAL_PHI_SHA256
         and s.get("device_roundtrip_sha256") == CANONICAL_PHI_SHA256
         and s.get("phi_margin_gate_m") == PHI_MARGIN_MIN_M
         and s.get("phi_margin_m", 0) >= PHI_MARGIN_MIN_M
         and abs(s.get("phi_margin_m", 0) - PHI_MARGIN_EXPECTED_M) <= PHI_MARGIN_TOL_M)
        if cases[case_id]["mode"] == "gridsdf" else
        s.get("phi_sha256") == "" and s.get("device_roundtrip_sha256") == ""
        and s.get("phi_margin_m") is None and s.get("phi_margin_gate_m") is None
    ))
    t8 = complete and relative(summaries["analytic_16"]["window_mean_drag"], W2T4A_ANALYTIC_DRAG) <= T4_BASELINE_DRAG_TOL \
         and relative(summaries["gridsdf_16"]["window_mean_drag"], W2T4B_GRID_SDF_DRAG) <= T4_BASELINE_DRAG_TOL
    t9 = complete and all(relative(summaries[f"analytic_{n}"]["time_weighted_cd"],
                                  summaries[f"gridsdf_{n}"]["time_weighted_cd"]) <= GEOMETRY_CD_TOL
                          for n in (16, 24, 32))
    t10 = complete and all(relative(summaries[f"{mode}_24"]["time_weighted_cd"],
                                    summaries[f"{mode}_32"]["time_weighted_cd"])
                           <= FINEST_GRID_CD_TOL for mode in ("analytic", "gridsdf"))
    t11 = all_case(lambda _, s: 0 < s.get("wall_seconds", 0) <= 1800.0
                   and s.get("ms_per_step", 0) > 0
                   and 0 < s.get("peak_vram_bytes", 0) < s.get("vram_total_bytes", 0))
    selected_uuid = rows[0].split(", ")[2] if rows else ""
    t12 = (len(rows) == 2 and len(set(row.split(", ")[2] for row in rows)) == 2
           and all("Tesla T4" in row and row.split(", ")[-1] == "580.159.04" for row in rows)
           and all(s.get("gpu_name") == "Tesla T4" and s.get("julia_version") == "1.12.6"
                   and s.get("julia_threads") == 1
                   and s.get("cuda_jl_version") == "6.3.1" and s.get("waterlily_version") == "1.8.0"
                   for s in all_summaries)
           and selected_uuid.startswith("GPU-")
           and "GPU_COMPUTE_CAPABILITY 7.5.0" in smoke
           and f"CUDA_DRIVER_VERSION {CUDA_DRIVER_API_VERSION}" in smoke
           and f"CUDA_RUNTIME_VERSION {CUDA_RUNTIME_VERSION}" in smoke)
    return {
        "T0_prerequisites": prerequisites_ok,
        "T1_completion": t1,
        "T2_finiteness": t2,
        "T3_force_finite": t3,
        "T4_drag_sign": t4,
        "T5_stationarity": t5,
        "T6_lift_bound": t6,
        "T7_canonical_grid": t7,
        "T8_16_baseline_agreement": t8,
        "T9_geometry_interpolation_agreement": t9,
        "T10_finest_grid_response": t10,
        "T11_runtime_vram": t11,
        "T12_backend_identity": t12,
    }


def read_case_outputs():
    summaries = {}
    finite_csv = {}
    for case_id in CASE_IDS:
        summary_path = OUT / f"{case_id}.summary.json"
        csv_path = OUT / f"{case_id}.forces.csv"
        if not summary_path.is_file() or not csv_path.is_file():
            continue
        summary = json.loads(summary_path.read_text())
        if sha256(csv_path) != summary.get("csv_sha256"):
            finite_csv[case_id] = False
            summaries[case_id] = summary
            continue
        with csv_path.open(newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows or rows[0] != ["step", "t_ud", "drag", "lift", "side", "pressure_drag", "viscous_drag"]:
            finite_csv[case_id] = False
        else:
            try:
                numeric = [[float(value) for value in row] for row in rows[1:]]
                finite_csv[case_id] = (len(numeric) == summary["force_samples"]
                                       and all(len(row) == 7 and all(math.isfinite(value) for value in row)
                                               for row in numeric))
            except (TypeError, ValueError):
                finite_csv[case_id] = False
        summaries[case_id] = summary
    return summaries, finite_csv


def write_hash_manifest():
    files = {path.name: sha256(path) for path in sorted(OUT.iterdir())
             if path.is_file() and path.name not in {"sha256.json", "DONE"}}
    write_json(OUT / "sha256.json", files)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = gpu_inventory()
    with tempfile.TemporaryDirectory(prefix="cfd_w2b_") as temp:
        base = Path(temp)
        source, project = fetch_source(base)
        check_hash(project / "Project.toml", PROJECT_SHA256)
        check_hash(project / "Manifest.toml", MANIFEST_SHA256)
        julia = install_julia(base)
        env = os.environ.copy()
        env.update({"JULIA_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "0"})
        command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                 "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env, timeout=1800)
        check_hash(project / "Project.toml", PROJECT_SHA256)
        check_hash(project / "Manifest.toml", MANIFEST_SHA256)
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / "scripts/w0b_t4_smoke.jl")],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        for marker in ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
                       f"CUDA_DRIVER_VERSION {CUDA_DRIVER_API_VERSION}",
                       f"CUDA_RUNTIME_VERSION {CUDA_RUNTIME_VERSION}", "JULIA_VERSION 1.12.6",
                       "CUDA_JL_VERSION 6.3.1", "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4"):
            if marker not in smoke:
                raise RuntimeError(f"W2b CUDA smoke missing marker: {marker}")

        params = write_params()
        env["JULIA_NUM_THREADS"] = "1"
        command([str(julia), "--startup-file=no", f"--project={project}",
                 str(source / "scripts/waterlily_w2b_grid_ladder_job.jl"),
                 str(params), str(OUT)], OUT / "w2b.log", env=env, timeout=5400)
        summaries, finite_csv = read_case_outputs()
        gates = w2b_gates(summaries, finite_csv, rows, smoke)
        write_json(OUT / "fingerprint.json", {
            "gpu_csv": rows,
            "julia_archive_sha256": JULIA_SHA256,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "runner_sha256": sha256(Path(__file__)),
            "source_commit": SOURCE_COMMIT,
            "criteria_sha256": CRITERIA_SHA256,
        })
        write_json(OUT / "outcome.json", {
            "criteria_sha256": CRITERIA_SHA256,
            "source_commit": SOURCE_COMMIT,
            "project_sha256": PROJECT_SHA256,
            "manifest_sha256": MANIFEST_SHA256,
            "parameters_sha256": sha256(params),
            "gpu_inventory": rows,
            "selected_gpu_uuid": rows[0].split(", ")[2],
            "summaries": summaries,
            "force_csv_finite": finite_csv,
            "gates": gates,
        })
        if not all(gates.values()):
            raise RuntimeError(f"W2b gates failed: {gates}")
        write_hash_manifest()
        (OUT / "DONE").write_text("Kaggle W2b registered six-case ladder completed; verify retrieved SHA-256 files\n")
        print("KAGGLE_W2B_DONE", json.dumps(gates, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        write_hash_manifest()
        raise
