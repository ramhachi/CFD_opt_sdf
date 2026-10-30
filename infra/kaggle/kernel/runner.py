"""Kaggle background runner for the registered SDF-native GPU gate."""

import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path


STAGE = "w2t4b"
OUT = Path("/kaggle/working") / STAGE
SOURCE_COMMIT = "2da94a92ffb9af55dfc159068ace8f25c55c0e6c"
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT_SHA256 = "e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194"
MANIFEST_SHA256 = "c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707"
CRITERIA_SHA256 = "154fec9111737f8cb76579f0a02fd2d6b4c043c30250d1d24b8a5d05b3ea15ad"
COLAB_RESULT_SHA256 = "70f747e264bacc9c3360ab9d6445c7bb77e6b11a6a6d521271297780301af754"
W1G_CRITERIA_SHA256 = "717053a2e4cb32d16cbbc2e3de2007371c1046f365f76a404cb166322adaadcb"
K0_RESULT_SHA256 = "0f9176083c2cb2503101b7f69fd48ef9bc24f15f63d7d187e32bc8eef4cda719"
W1G_RESULT_SHA256 = "bb233f72068b5c6681b9f3f9b4dba180b538f945f8283312fb521c24ac802eb8"
W2A_CPU_RESULT_SHA256 = "26b6a65f6a2f89dde7e9976b2209b776eeb90d895432707214a582e9192f920b"
W2A_CPU_CRITERIA_SHA256 = "aea91e6cc8de65ef072b3fbb19a3ca50a01b5e75198e62c128fda3fe8849602f"
W2T4A_RESULT_SHA256 = "70f747e264bacc9c3360ab9d6445c7bb77e6b11a6a6d521271297780301af754"
W2T4A_CRITERIA_SHA256 = "154fec9111737f8cb76579f0a02fd2d6b4c043c30250d1d24b8a5d05b3ea15ad"
W2T4B_CRITERIA_SHA256 = "85bd5ba4f6ff0a13c7f0509b1ba86b74cfeb7bc346fc590b27a819ce3f228e66"
CANONICAL_PHI_SHA256 = "393d5d7897885d71cda0902129a4aa3db561c59b1a85e8e221d55ce19fca4161"
W2T4_JOB_SHA256 = "b968f853343611b6ababe4951bc4f470a8f5d596ddead3131cdfecccbde1027b"
DEVICE_GRID_SDF_SHA256 = "2f02c840f4fad5ba5d26d42f4c24bc83f413502b15487427a7dc52f06a80a874"
W2A_CPU_SAMPLED_DRAG = 88.2335378441562
W2T4A_ANALYTIC_CD = 0.8795874366347541
SAMPLED_ANALYTIC_CD_TOL = 0.10
CPU_KAGGLE_SAMPLED_DRAG_TOL = 0.01
W2T4B_STATIONARITY_TOL = 0.02
W2T4B_LIFT_RATIO_TOL = 0.10
W2T4B_PHI_MARGIN_MIN_M = 0.15
W2T4B_PHI_MARGIN_GATE_M = 0.15
W2T4B_PHI_MARGIN_EXPECTED_M = 0.19999998807907104
W2T4B_PHI_MARGIN_TOL_M = 1e-6
W2T4B_T_END = 60.0


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
    csv = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
         "--format=csv,noheader"], text=True)
    (OUT / "nvidia_smi.csv").write_text(csv)
    rows = [row.strip() for row in csv.splitlines() if row.strip()]
    if len(rows) != 2 or [row.split(",", 1)[0] for row in rows] != ["0", "1"]:
        raise RuntimeError("K0 requires exactly GPU indexes 0 and 1")
    if any("Tesla T4" not in row for row in rows):
        raise RuntimeError("K0 requires two Tesla T4 GPUs")
    return rows


def fetch_source(base):
    source = base / "source"
    command(["git", "init", "-q", str(source)], OUT / "git_init.log")
    command(["git", "-C", str(source), "fetch", "--depth", "1", SOURCE_URL,
             SOURCE_COMMIT], OUT / "git_fetch.log", timeout=600)
    command(["git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"],
            OUT / "git_checkout.log")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError("source commit drift")
    check_hash(source / "docs/evidence/sdf_native_w2t4a_analytic_sphere_criteria_2026_09.json",
               CRITERIA_SHA256)
    check_hash(source / "docs/evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json",
               COLAB_RESULT_SHA256)
    for path, expected in (
        ("docs/evidence/kaggle_k0_result_2026_09.json", K0_RESULT_SHA256),
        ("docs/evidence/kaggle_w1g_round2_result_2026_09.json", W1G_RESULT_SHA256),
        ("docs/evidence/sdf_native_w2a_sphere_cpu_2026_09.json", W2A_CPU_RESULT_SHA256),
    ):
        check_hash(source / path, expected)
    project = source / "julia/CFDSDFWaterLilyT4"
    check_hash(project / "Project.toml", PROJECT_SHA256)
    check_hash(project / "Manifest.toml", MANIFEST_SHA256)
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


def write_params(source):
    criteria = json.loads((source / "docs/evidence/sdf_native_w2t4a_analytic_sphere_criteria_2026_09.json").read_text())
    fixture = criteria["fixture"]
    flow, affine, period = fixture["flow"], fixture["affine_map"], fixture["time"]
    sample = int(re.search(r"every (\d+) solver steps", period["force_sampling"]).group(1))
    def tup(values):
        return "(" + ", ".join(repr(value) for value in values) + ")"
    fields = {
        "flow_dims": tup(flow["dims"]),
        "solver_center": tup(flow["solver_center"]),
        "solver_radius": repr(float(flow["solver_radius"])),
        "u_inf": repr(float(flow["u_inf"])),
        "reynolds": repr(float(flow["reynolds_diameter"])),
        "viscosity": repr(float(flow["kinematic_viscosity_solver"])),
        "world_origin": tup(affine["world_origin_m"]),
        "world_per_solver": repr(float(affine["world_per_solver"])),
        "t_end": repr(float(period["t_end_tu_d"])),
        "burn_in": repr(float(period["burn_in_tu_d"])),
        "sample_every": repr(sample),
    }
    path = OUT / "params.jl"
    path.write_text("const W2T4_PARAMS = (\n" + "".join(
        f"    {key} = {value},\n" for key, value in fields.items()) + ")\n")
    return path


def relative(a, b):
    if not math.isfinite(a) or not math.isfinite(b) or a == 0 or b == 0:
        raise ValueError("response is zero or non-finite")
    return abs(a - b) / max(abs(a), abs(b))


def assess_analytic(summary, reference_drag, single_drag=None):
    drag = float(summary["window_mean_drag"])
    gates = {
        "completion": summary["mode"] == "analytic" and summary["steps"] == 2246
                      and summary["t_end_reached"] >= 60,
        "finite": all(summary[key] is True for key in ("finite_u", "finite_p", "finite_forces")),
        "drag_positive": drag > 0,
        "stationarity": relative(summary["first_half_mean_drag"],
                                 summary["second_half_mean_drag"]) <= 0.02,
        "runtime_vram": summary["wall_seconds"] > 0 and summary["ms_per_step"] > 0
                        and 0 < summary["peak_vram_bytes"] < summary["vram_total_bytes"],
        "colab_agreement": relative(drag, reference_drag) <= 0.0001,
    }
    if single_drag is not None:
        gates["single_gpu_agreement"] = relative(drag, single_drag) <= 0.000001
    return gates


def read_result(prefix):
    summary = json.loads((OUT / f"{prefix}.summary.json").read_text())
    check_hash(OUT / f"{prefix}.forces.csv", summary["csv_sha256"])
    if (summary["gpu_name"], summary["julia_version"], summary["cuda_jl_version"],
        summary["waterlily_version"]) != ("Tesla T4", "1.12.6", "6.3.1", "1.8.0"):
        raise RuntimeError(f"Julia/CUDA/WaterLily/GPU version drift: {prefix}")
    return summary


def job_args(julia, project, source, params, prefix, mode="analytic"):
    return [str(julia), "--startup-file=no", f"--project={project}",
            str(source / "scripts/waterlily_w2t4_job.jl"), str(params), mode,
            str(OUT / prefix)]


def w2t4b_gates(summary, rows, smoke, prerequisites_ok=True):
    drag = float(summary["window_mean_drag"])
    analytic_ref_cd = W2T4A_ANALYTIC_CD
    selected_uuid = rows[0].split(", ")[2] if rows else ""
    gates = {
        "T0_prerequisites": prerequisites_ok,
        "T1_completion": summary["mode"] == "gridsdf" and summary["steps"] > 0
                         and summary["t_end_reached"] >= W2T4B_T_END,
        "T2_finiteness": summary["finite_u"] is True and summary["finite_p"] is True,
        "T3_force_finite": summary["finite_forces"] is True and summary["force_samples"] > 0,
        "T4_drag_sign": drag > 0,
        "T5_stationarity": drag != 0 and math.isfinite(drag)
                            and abs(summary["first_half_mean_drag"]
                                    - summary["second_half_mean_drag"]) / abs(drag)
                            <= W2T4B_STATIONARITY_TOL,
        "T6_cpu_kaggle_agreement": abs(drag - W2A_CPU_SAMPLED_DRAG)
                                   / abs(W2A_CPU_SAMPLED_DRAG) <= CPU_KAGGLE_SAMPLED_DRAG_TOL,
        "T7_sampled_analytic_agreement": abs(summary["cd"] - analytic_ref_cd)
                                         / abs(analytic_ref_cd) <= SAMPLED_ANALYTIC_CD_TOL,
        "T8_lift_bound": drag > 0 and math.isfinite(drag)
                         and abs(summary["window_mean_lift"]) / drag <= W2T4B_LIFT_RATIO_TOL,
        "T9_canonical_grid": summary["phi_sha256"] == CANONICAL_PHI_SHA256
                             and summary["device_roundtrip_sha256"] == CANONICAL_PHI_SHA256
                             and summary.get("phi_margin_gate_m") == W2T4B_PHI_MARGIN_GATE_M
                             and summary["phi_margin_m"] >= W2T4B_PHI_MARGIN_MIN_M
                             and abs(summary["phi_margin_m"] - W2T4B_PHI_MARGIN_EXPECTED_M)
                             <= W2T4B_PHI_MARGIN_TOL_M,
        "T10_runtime_vram": summary["wall_seconds"] > 0 and summary["ms_per_step"] > 0
                            and 0 < summary["peak_vram_bytes"] < summary["vram_total_bytes"],
        "T11_backend_identity": len(rows) == 2 and len(set(row.split(", ")[2] for row in rows)) == 2
                                and all("Tesla T4" in row and row.split(", ")[-1] == "580.159.04"
                                        for row in rows)
                                and summary["gpu_name"] == "Tesla T4"
                                and summary["julia_version"] == "1.12.6"
                                and summary["cuda_jl_version"] == "6.3.1"
                                and summary["waterlily_version"] == "1.8.0"
                                and "GPU_COMPUTE_CAPABILITY 7.5.0" in smoke
                                and "CUDA_RUNTIME_VERSION 13.3.0" in smoke
                                and selected_uuid.startswith("GPU-"),
    }
    return gates


def verify_w2t4b_prerequisites(source, project):
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                               text=True).strip() != SOURCE_COMMIT:
        raise RuntimeError("W2-T4b source commit drift")
    check_hash(project / "Project.toml", PROJECT_SHA256)
    check_hash(project / "Manifest.toml", MANIFEST_SHA256)
    for path, expected in (
        ("docs/evidence/kaggle_k0_result_2026_09.json", K0_RESULT_SHA256),
        ("docs/evidence/kaggle_w1g_round2_result_2026_09.json", W1G_RESULT_SHA256),
        ("docs/evidence/sdf_native_w2a_sphere_cpu_2026_09.json", W2A_CPU_RESULT_SHA256),
        ("docs/evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json", W2T4A_RESULT_SHA256),
        ("docs/evidence/sdf_native_w2a_sphere_cpu_criteria_2026_09.json",
         W2A_CPU_CRITERIA_SHA256),
        ("docs/evidence/sdf_native_w2t4a_analytic_sphere_criteria_2026_09.json",
         W2T4A_CRITERIA_SHA256),
        ("scripts/waterlily_w2t4_job.jl", W2T4_JOB_SHA256),
        ("julia/CFDSDFWaterLily/src/DeviceGridSDF.jl", DEVICE_GRID_SDF_SHA256),
    ):
        check_hash(source / path, expected)


def run_w2t4b(julia, project, source, params, env, rows, smoke):
    if any(row.split(", ")[-1] != "580.159.04" for row in rows):
        raise RuntimeError("Kaggle W2-T4b NVIDIA driver cohort drift")
    verify_w2t4b_prerequisites(source, project)
    prefix = "gridsdf"
    command(job_args(julia, project, source, params, prefix, mode="gridsdf"),
            OUT / "gridsdf.log", env=env, timeout=1800)
    summary = read_result(prefix)
    gates = w2t4b_gates(summary, rows, smoke)
    write_json(OUT / "outcome.json", {
        "criteria_sha256": W2T4B_CRITERIA_SHA256,
        "source_commit": SOURCE_COMMIT,
        "project_sha256": PROJECT_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "gpu_inventory": rows,
        "selected_gpu_uuid": rows[0].split(", ")[2],
        "fixture_summary": summary,
        "gates": gates,
    })
    if not all(gates.values()):
        raise RuntimeError(f"W2-T4b failed: {gates}")
    print("KAGGLE_W2T4B_DONE", json.dumps(gates, sort_keys=True), flush=True)


def write_hash_manifest():
    write_json(OUT / "sha256.json", {path.name: sha256(path) for path in sorted(OUT.iterdir())
            if path.is_file() and path.name not in {"sha256.json", "DONE"}})


def w1g_gates(summary, rows, fixture_text):
    identity = summary["backend_identity"]
    selected_uuid = rows[0].split(", ")[2]
    return {
        "G1_device_copy": summary["source_phi_sha256"] == CANONICAL_PHI_SHA256
                          and summary["device_roundtrip_sha256"] == CANONICAL_PHI_SHA256,
        "G2_kernel": summary["mode"] == "gpu" and summary["probe_count"] == 200012
                     and summary["bulk_box"] == 100000 and summary["bulk_band"] == 100000
                     and summary["representative_count"] == 12,
        "G3_finite": summary["all_finite"] is True,
        "G4_sign": summary["sign_violations"] == 0 and summary["sign_gated_probes"] > 0,
        "G5_value": summary["max_value_error_world_m"] <= 1e-5,
        "G6_normal": summary["max_normal_error"] <= 1e-3 and summary["normal_gated_probes"] > 0,
        "G7_outside": summary["outside_exact"] is True and summary["outside_probes"] == 6,
        "G8_no_scalar_fallback": summary["scalar_index_blocked"] is True
                                 and "CUDA.allowscalar(true)" not in fixture_text,
        "G9_backend": identity == {
            "gpu_name": "Tesla T4", "gpu_uuid": selected_uuid,
            "compute_capability": "7.5.0", "cuda_jl_version": "6.3.1",
            "waterlily_version": "1.8.0", "julia_version": "1.12.6",
            "cuda_runtime_version": "13.3.0",
        },
    }


def run_w1g(julia, project, source, env, rows, smoke):
    if "GPU_COMPUTE_CAPABILITY 7.5.0" not in smoke or "CUDA_RUNTIME_VERSION 13.3.0" not in smoke:
        raise RuntimeError("Kaggle W1g hardware/runtime cohort drift")
    if any(row.split(", ")[-1] != "580.159.04" for row in rows):
        raise RuntimeError("Kaggle W1g NVIDIA driver cohort drift")
    log = OUT / "w1g.log"
    command([str(julia), "--startup-file=no", f"--project={project}",
             str(source / "scripts/w1g_gpu_geometry_fixture.jl"), "gpu", str(OUT / "fixture")],
            log, env=env, timeout=1800)
    summary = json.loads((OUT / "fixture.summary.json").read_text())
    gates = w1g_gates(summary, rows,
                      (source / "scripts/w1g_gpu_geometry_fixture.jl").read_text())
    write_json(OUT / "outcome.json", {
        "criteria_sha256": W1G_CRITERIA_SHA256, "source_commit": SOURCE_COMMIT,
        "project_sha256": PROJECT_SHA256, "manifest_sha256": MANIFEST_SHA256,
        "gpu_inventory": rows, "fixture_summary": summary, "gates": gates,
    })
    if not all(gates.values()):
        raise RuntimeError(f"W1g failed: {gates}")
    print("KAGGLE_W1G_DONE", json.dumps(gates, sort_keys=True), flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = gpu_inventory()
    write_json(OUT / "fingerprint.json", {
        "gpu_csv": rows, "python": sys.version, "platform": platform.platform(),
        "runner_sha256": sha256(Path(__file__)), "source_commit": SOURCE_COMMIT,
        "julia_archive_sha256": JULIA_SHA256,
    })
    with tempfile.TemporaryDirectory(prefix="cfd_k0_") as folder:
        base = Path(folder)
        source, project = fetch_source(base)
        julia = install_julia(base)
        env = os.environ.copy()
        env.update(JULIA_DEPOT_PATH=str(base / "julia_depot"), JULIA_NUM_THREADS="1",
                   CUDA_VISIBLE_DEVICES="0")
        command([str(julia), "--startup-file=no", f"--project={project}",
                 "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log",
                env=env, timeout=3600)
        check_hash(project / "Project.toml", PROJECT_SHA256)
        check_hash(project / "Manifest.toml", MANIFEST_SHA256)
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / "scripts/w0b_t4_smoke.jl")],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        for marker in ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "CUARRAY_SMOKE true",
                       "KA_SMOKE true", "WATERLILY_CUDA_EXT true", "JULIA_VERSION 1.12.6",
                       "CUDA_JL_VERSION 6.3.1", "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4"):
            if marker not in smoke:
                raise RuntimeError(f"Julia CUDA smoke missing marker: {marker}")
        if STAGE == "w1g":
            run_w1g(julia, project, source, env, rows, smoke)
            write_hash_manifest()
            (OUT / "DONE").write_text("Kaggle W1g G1-G9 completed; verify retrieved SHA-256 files\n")
            return
        if STAGE == "w2t4b":
            params = write_params(source)
            run_w2t4b(julia, project, source, params, env, rows, smoke)
            write_hash_manifest()
            (OUT / "DONE").write_text("Kaggle W2-T4b sampled-sphere gates completed; verify retrieved SHA-256 files\n")
            return
        params = write_params(source)
        colab = json.loads((source / "docs/evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json").read_text())
        reference_drag = colab["runs"]["run"]["window_mean_drag"]
        if reference_drag != 88.42577373189188:
            raise RuntimeError("Colab reference drift")
        command(job_args(julia, project, source, params, "single"),
                OUT / "single.log", env=env, timeout=1200)
        single = read_result("single")
        single_gates = assess_analytic(single, reference_drag)
        if not all(single_gates.values()):
            raise RuntimeError(f"K0-C/D failed: {single_gates}")

        workers = []
        for index in (0, 1):
            worker_env = env.copy()
            worker_env["CUDA_VISIBLE_DEVICES"] = str(index)
            log = (OUT / f"gpu{index}.log").open("w")
            started = time.monotonic()
            proc = subprocess.Popen(job_args(julia, project, source, params, f"gpu{index}"),
                                    env=worker_env, stdout=log, stderr=subprocess.STDOUT)
            workers.append((index, proc, log, started))
        intervals = {}
        for index, proc, log, started in workers:
            try:
                code = proc.wait(timeout=1200)
            finally:
                log.close()
            intervals[f"gpu{index}"] = {"start_monotonic": started,
                                      "end_monotonic": time.monotonic(), "exit_code": code}
        dual = {f"gpu{index}": read_result(f"gpu{index}") for index in (0, 1)}
        overlap = max(item["start_monotonic"] for item in intervals.values()) < min(
            item["end_monotonic"] for item in intervals.values())
        dual_gates = {key: assess_analytic(value, reference_drag,
                                           single_drag=single["window_mean_drag"])
                      for key, value in dual.items()}
        if any(item["exit_code"] for item in intervals.values()) or not overlap or not all(
                all(gates.values()) for gates in dual_gates.values()):
            raise RuntimeError(f"K0-E failed: overlap={overlap}, gates={dual_gates}")
        write_json(OUT / "outcome.json", {
            "gates": {"K0_A": True, "K0_B": True, "K0_C_D": single_gates,
                      "K0_E_overlap": overlap, "K0_E_workers": dual_gates},
            "single": single, "dual": dual, "intervals": intervals,
            "reference_drag": reference_drag, "project_sha256": PROJECT_SHA256,
            "manifest_sha256": MANIFEST_SHA256, "source_commit": SOURCE_COMMIT,
        })
    write_hash_manifest()
    (OUT / "DONE").write_text("K0-A through K0-E completed; verify K0-F after CLI retrieval\n")
    print("K0_ANALYTIC_DONE", single["window_mean_drag"], flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        write_hash_manifest()
        raise
