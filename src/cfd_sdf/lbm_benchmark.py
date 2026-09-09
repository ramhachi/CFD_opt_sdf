"""Measured periodic-flow benchmark, with optional CPU/Metal comparison."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import time

import numpy as np

from .lbm_reference import (
    LBMConfig, macroscopic, one_step,
    run_taylor_green, taylor_green_initial_state,
)


def run_lbm_benchmark(config: LBMConfig, backend: str = "cpu") -> dict:
    if backend not in {"cpu", "metal"}:
        raise ValueError("backend must be cpu or metal")
    # Bounds protect an interactive research command from accidental large runs.
    if config.nx * config.ny > 1_048_576 or config.steps > 20_000:
        raise ValueError("research benchmark is limited to 1M cells and 20000 steps")
    if config.steps == 0 or config.velocity == 0:
        raise ValueError("benchmark requires positive steps and nonzero velocity")
    decay = np.exp(-config.viscosity * ((2 * np.pi / config.nx) ** 2
                                      + (2 * np.pi / config.ny) ** 2) * config.steps)
    if config.velocity * decay < np.finfo(np.float64).eps:
        raise ValueError("analytical final velocity is below FP64 resolution; shorten the run")
    started = time.perf_counter()
    report = run_taylor_green(config)
    cpu_seconds = time.perf_counter() - started
    report["kind"] = "lbm_periodic_benchmark"
    report["requested_backend"] = backend
    report["config_sha256"] = hashlib.sha256(
        json.dumps(asdict(config), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report["timing"] = {
        "cpu_reference_seconds": cpu_seconds,
        "cpu_reference_mlups": config.nx * config.ny * config.steps / cpu_seconds / 1e6,
        "scope": "CPU reference including validation and metrics; not optimized solver throughput",
    }
    report["capabilities"] = {
        "periodic_primal": True, "wall_force": False,
        "sdf_geometry": False, "adjoint": False, "target_aerodynamics": False,
    }
    if backend == "cpu":
        return report

    from .lbm_metal import MetalStepper, require_metal
    mx = require_metal()
    _, u0, f0 = taylor_green_initial_state(config)
    step = MetalStepper(config.viscosity)
    f = mx.array(f0, dtype=mx.float32)
    mx.eval(f)
    # Compile/warm up without advancing the measured initial state.
    warm_started = time.perf_counter()
    warm = step(f)
    warm_seconds = time.perf_counter() - warm_started
    del warm
    mx.reset_peak_memory()
    started = time.perf_counter()
    for _ in range(config.steps):
        f = step(f)
    seconds = time.perf_counter() - started
    peak = mx.get_peak_memory()
    gpu_f = np.asarray(f)
    rho, u = macroscopic(gpu_f)
    # Same lattice and complete field comparison, not just a scalar force/RMS.
    ref_f = f0
    for _ in range(config.steps):
        ref_f = one_step(ref_f, config)
    _, ref_u = macroscopic(ref_f)
    relative_u = float(np.linalg.norm(u - ref_u) / np.linalg.norm(ref_u))
    relative_mass = float(abs(rho.sum() - f0.sum()) / f0.sum())
    analytic_u = u0 * report["analytic_decay"]["factor"]
    analytic_error = float(np.linalg.norm(u - analytic_u) / np.linalg.norm(analytic_u))
    checks = {
        "velocity_relative_l2": relative_u,
        "velocity_relative_tolerance": 0.005,
        "mass_relative_error": relative_mass,
        "mass_relative_tolerance": 0.0001,
        "analytic_relative_l2": analytic_error,
        "analytic_relative_tolerance": 0.05,
    }
    passed = bool(
        np.isfinite([relative_u, relative_mass, analytic_error]).all()
        and relative_u <= 0.005 and relative_mass <= 0.0001 and analytic_error <= 0.05
    )
    report["metal"] = {
        "precision": "float32", "checks": checks,
        "status": "pass" if passed else "fail",
        "step_loop_seconds": seconds,
        "step_loop_mlups": config.nx * config.ny * config.steps / seconds / 1e6,
        "compile_warmup_seconds": warm_seconds,
        "mlx_peak_bytes": peak,
        "memory_scope": "MLX allocator peak during this run, not process RSS",
        "timing_scope": "materialized GPU steps, excluding initialization, CPU comparison and metrics",
    }
    report["status"] = report["overall_status"] = (
        "pass" if passed and report["status"] == "pass" else "fail"
    )
    return report
