"""Prepare one fixed, diagnostic-only design-lattice phase experiment (#37).

Freshly sample the unchanged registered STL; do not translate its geometry.
The trilinear representation and fluid-only design-support faces can change.
No canonical state, masks, qualification, or acceptance threshold is registered.
"""
from __future__ import annotations

import hashlib
from functools import partial
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdf_native_genesis_v17_2026_09 import gradient_census, resample, write_immutable
import sdf_native_genesis_v17_2026_09 as genesis

# Same signed-distance helper, bounded nearest-triangle workspace (no 200k batches).
genesis.signed_distance = partial(genesis.signed_distance, chunk_size=8000)

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = (-1.0, -0.8, -0.6)
SHAPE = (121, 65, 49)
SPACING = 0.025
SHIFT_FRACTION = (0.27, 0.37, 0.43)
SOURCE_SHA256 = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source_bounds(bounds, origin, shape, spacing, margin=0.15) -> float:
    bounds = np.asarray(bounds, dtype=float)
    origin = np.asarray(origin, dtype=float)
    upper = origin + spacing * (np.asarray(shape) - 1)
    if bounds.shape != (2, 3) or not np.isfinite(bounds).all():
        raise ValueError("source bounds must be finite 2-by-3 coordinates")
    clearance = float(np.min(np.r_[bounds[0] - origin, upper - bounds[1]]))
    if clearance < margin:
        raise ValueError(f"source has only {clearance} m design-support clearance")
    return clearance


def prepare(stl_path: Path, v17_raw: Path, outdir: Path) -> dict:
    if outdir.exists():
        raise FileExistsError(f"diagnostic output already exists: {outdir}")
    if sha(stl_path) != SOURCE_SHA256:
        raise ValueError("source STL differs from registered genesis lineage")
    expected_raw = json.loads((ROOT / "docs/evidence/sdf_native_genesis_v17_2026_09.json").read_text())["state"]["phi_f4_fortran_sha256"]
    if sha(v17_raw) != expected_raw:
        raise ValueError("control raw phi differs from registered v17")
    mesh = trimesh.load(stl_path, force="mesh")
    if not mesh.is_watertight:
        raise ValueError("registered source must remain watertight")
    lattices = {}
    for name, fractions in (("control", (0.0, 0.0, 0.0)), ("shifted", SHIFT_FRACTION)):
        origin = tuple(o + SPACING * f for o, f in zip(ORIGIN, fractions))
        clearance = validate_source_bounds(mesh.bounds, origin, SHAPE, SPACING)
        phi = resample(mesh, origin, SPACING, SHAPE)
        payload = np.asfortranarray(phi).tobytes(order="F")
        if name == "control" and payload != v17_raw.read_bytes():
            old = np.frombuffer(v17_raw.read_bytes(), dtype=np.float32).reshape(SHAPE, order="F")
            audit = {"numeric_equal": bool(np.array_equal(phi, old)),
                     "unequal_nodes": int(np.count_nonzero(phi != old)),
                     "max_abs_difference_m": float(np.max(np.abs(phi.astype(float) - old))),
                     "signed_zero_differences": int(np.count_nonzero((phi == 0) & (old == 0) & (np.signbit(phi) != np.signbit(old))))}
            auditdir = ROOT / "work/fd07_validation/fresh_control_audit"
            write_immutable(auditdir / "phi.raw", payload)
            write_immutable(auditdir / "audit.json", (json.dumps(audit, indent=2) + "\n").encode())
            raise ValueError(f"fresh control fails registered raw byte identity: {audit}")
        write_immutable(outdir / name / "phi.raw", payload)
        lattices[name] = {"origin_m": origin, "spacing_m": SPACING, "point_shape": SHAPE,
                          "support_upper_m": (np.array(origin) + SPACING * (np.array(SHAPE) - 1)).tolist(),
                          "source_bounds_clearance_m": clearance,
                          "raw_sha256": sha(outdir / name / "phi.raw"),
                          "gradient_census": gradient_census(phi, SPACING)}
    identity_paths = [ROOT / "scripts/sdf_native_fd07_lattice_shift_prepare.py",
                      ROOT / "scripts/sdf_native_fd07_lattice_shift_cpu_probe.jl",
                      ROOT / "scripts/sdf_native_genesis_v17_2026_09.py",
                      ROOT / "src/cfd_sdf/sdf.py",
                      ROOT / "julia/CFDSDFWaterLily/Project.toml",
                      ROOT / "julia/CFDSDFWaterLily/Manifest.toml"]
    identity_paths += sorted((ROOT / "julia/CFDSDFWaterLily/src").glob("*.jl"))
    plan = {"kind": "fd07_lattice_phase_cpu_diagnostic_preregistration", "issue": "#37",
            "evidence_class": "diagnostic_only", "source_stl_sha256": SOURCE_SHA256,
            "source_stl_bounds_m": mesh.bounds.tolist(), "source_stl_unchanged": True,
            "baseline_reproduction_bitwise": True, "lattices": lattices,
            "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_file_hashes": {str(p.relative_to(ROOT)): sha(p) for p in identity_paths},
            "python_runtime": {"version": sys.version, "platform": platform.platform(),
                               "numpy": np.__version__, "trimesh": trimesh.__version__},
            "solver": {"backend": "CPU_Array", "float": "Float32", "phi_storage": "Float32",
                       "normal_floor": 0.25, "poisson_tolerance": 1e-4,
                       "poisson_max_iterations": 32, "case_id": "flow_24",
                       "flow_origin_m": [-2.5, -1.2, -0.9], "flow_dims": [150, 72, 54],
                       "flow_spacing_m": 0.8 / 24, "t_end_u_l": 3.0,
                       "analysis_window_u_l": [2.0, 3.0], "sample_every_steps": 8},
            "run_order": ["baseline", "noise_seed1@+1e-8", "noise_seed1@-1e-8", "noise_seed1@+1e-7", "noise_seed1@-1e-7"],
            "lattice_order": ["control", "shifted"], "solver_calls": 10,
            "noise": "identical MersenneTwister(1) Float64 standard-normal node array across amplitudes/signs/lattices; lattice-local noise, not the same world-space realization",
            "summary": "matched window mean forces; odd=(plus-minus)/2, even=(plus+minus)/2-baseline; ratios between fixed noise scales; initial mu0/mu1 changes",
            "limitations": ["one seed, no fresh repeated baseline, short horizon only", "same STL but changed discrete trilinear geometry and translated fluid-only SDF support",
                            "no isolated causal proof, no full-window FD qualification", "Float32 perturbation realization must be reported"],
            "flags": {"shape_update_allowed": False, "sdf_gradient_qualified": False, "canonical_registered": False}}
    write_immutable(outdir / "plan.json", (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode())
    return plan


if __name__ == "__main__":
    plan = prepare(*(Path(x).resolve() for x in sys.argv[1:4]))
    print(json.dumps({"plan_sha256": sha(Path(sys.argv[3]) / "plan.json"), "lattices": plan["lattices"]}, indent=2))
