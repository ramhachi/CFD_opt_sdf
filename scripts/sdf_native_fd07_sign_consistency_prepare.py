"""Prepare immutable inputs and preregister the FD-07 sign-correction probe."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE_HEAD = "b41c8fa8ff054f7f9aeee983850dadeefdf8a7d4"
BRANCH = "exp/issue-37-sign-consistency-causal-probe"
EVIDENCE = "docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10"
SHAPE = (121, 65, 49)
STL = "docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/source_surface.stl"
PHI = "docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/control/phi.raw"
STL_SHA256 = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
PHI_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
BODY_SHA256 = "aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee"
FIXED_FACE_CSV = "docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/world_map_precision/fixed_face_scalar_ablation.csv"
FIXED_FACE_SHA256 = "ddc3e5ed8470c7c247cc616b686f078a9ce2ab91414b91ba0eb73d7ac2ce7519"
SEEDS = (1, 11, 2026)
AMPLITUDES = (1e-8, 1e-7)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def realize_perturbation(base: np.ndarray, noise: np.ndarray, amplitude: float, sign: int):
    if sign not in (-1, 1):
        raise ValueError("perturbation sign must be -1 or +1")
    if base.shape != noise.shape or not np.isfinite(base).all() or not np.isfinite(noise).all():
        raise ValueError("base and noise must be finite arrays of equal shape")
    phi = (base.astype(np.float64) + sign * amplitude * noise).astype("<f4")
    delta = phi.astype(np.float64) - base.astype(np.float64)
    return phi, {
        "changed_node_count": int(np.count_nonzero(delta)),
        "realized_rms_m": float(np.sqrt(np.mean(delta * delta))),
        "realized_max_abs_m": float(np.max(np.abs(delta))),
    }


def _tracked_source_hashes() -> dict[str, str]:
    files = [
        Path("scripts/sdf_native_fd07_sign_consistency_prepare.py"),
        Path("scripts/sdf_native_fd07_sign_consistency_causal_cpu_probe.jl"),
        Path("scripts/sdf_native_fd07_sign_consistency_analysis.py"),
        Path("scripts/sdf_native_fd07_lattice_shift_cpu_probe.jl"),
        Path("scripts/sdf_native_fd07_lattice_shift_analysis.py"),
        Path("tests/test_sdf_native_fd07_sign_consistency.py"),
        Path("julia/CFDSDFWaterLily/Project.toml"),
        Path("julia/CFDSDFWaterLily/Manifest.toml"),
        Path("julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl"),
        Path("julia/CFDSDFWaterLily/src/GridSDFBody.jl"),
        Path("julia/CFDSDFWaterLily/src/WaterLilyBody.jl"),
        Path("julia/CFDSDFWaterLily/src/Forces.jl"),
        Path("julia/CFDSDFWaterLily/src/Runtime.jl"),
        Path("julia/CFDSDFWaterLily/src/Simulation.jl"),
        Path("julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl"),
        Path("julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl"),
        Path("julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl"),
        Path("docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/plan.json"),
        Path("docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/world_map_precision/summary.json"),
        Path(FIXED_FACE_CSV),
    ]
    return {p.as_posix(): sha(ROOT / p) for p in files}


def verify(outdir: Path) -> dict:
    plan_path = outdir / "plan.json"
    plan = json.loads(plan_path.read_text())
    recorded_plan_sha = (outdir / "plan.sha256").read_text().split()[0]
    if sha(plan_path) != recorded_plan_sha:
        raise ValueError("plan hash differs from its preregistration sidecar")
    if plan["source"]["waterlily_body_jl_sha256"] != sha(
        Path(plan["source"]["waterlily_body_jl"])
    ):
        raise ValueError("pinned WaterLily Body.jl changed")
    if plan["fixed_face_control"]["source_csv_sha256"] != sha(
        ROOT / plan["fixed_face_control"]["source_csv"]
    ):
        raise ValueError("registered FD-07 fixed-face control source changed")
    if plan["fixed_face_control"]["source_csv_sha256"] != sha(
        outdir / plan["fixed_face_control"]["copied_csv"]
    ):
        raise ValueError("copied FD-07 fixed-face control differs from source")
    source_manifest_path = outdir / "repository_sources.sha256"
    if plan["source"]["repository_sources_manifest_sha256"] != sha(source_manifest_path):
        raise ValueError("repository source manifest differs from preregistration")
    source_manifest = {
        relative: expected
        for expected, relative in (
            line.split("  ", 1) for line in source_manifest_path.read_text().splitlines()
        )
    }
    if source_manifest != plan["source"]["repository_source_sha256"]:
        raise ValueError("repository source manifest contents differ from preregistration")
    for relative, expected in plan["source"]["repository_source_sha256"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError(f"preregistered source file changed: {relative}")
    for relative, expected in plan["input_cases"]["baseline"].items():
        if relative.endswith("_sha256") and expected != sha(
            ROOT / plan["canonical_state"]["phi_source"]
        ):
            raise ValueError("registered baseline phi changed")
    checked = 0
    for line in (outdir / "input_files.sha256").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        if sha(outdir / relative) != expected:
            raise ValueError(f"input file hash mismatch: {relative}")
        checked += 1
    if plan["input_files_manifest_sha256"] != sha(outdir / "input_files.sha256"):
        raise ValueError("input file manifest hash differs from preregistration")
    if plan["realized_noise_csv_sha256"] != sha(outdir / "realized_noise.csv"):
        raise ValueError("realized-noise table differs from preregistration")
    return {"plan_sha256": recorded_plan_sha, "input_files_checked": checked}


def prepare(outdir: Path) -> dict:
    if outdir.exists():
        raise FileExistsError(f"refusing existing evidence directory: {outdir}")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if branch != BRANCH:
        raise ValueError(f"expected experiment branch {BRANCH}, got {branch}")
    if head != BASE_HEAD:
        raise ValueError(f"expected preregistration base {BASE_HEAD}, got {head}")

    stl_path, phi_path = ROOT / STL, ROOT / PHI
    if sha(stl_path) != STL_SHA256:
        raise ValueError("registered source STL hash mismatch")
    base_payload = phi_path.read_bytes()
    if sha_bytes(base_payload) != PHI_SHA256:
        raise ValueError("registered v17 phi hash mismatch")
    base = np.frombuffer(base_payload, dtype="<f4").reshape(SHAPE, order="F").copy(order="F")

    noise_dir = outdir / "inputs" / "noise"
    phi_dir = outdir / "inputs" / "phi"
    noise_hashes: dict[str, str] = {}
    baseline_name = "baseline.raw"
    write_new(phi_dir / baseline_name, base_payload)
    fixed_face_payload = (ROOT / FIXED_FACE_CSV).read_bytes()
    if sha_bytes(fixed_face_payload) != FIXED_FACE_SHA256:
        raise ValueError("registered FD-07 fixed-face control hash mismatch")
    write_new(outdir / "controls" / "fd07_fixed_face_scalar_ablation.csv", fixed_face_payload)
    cases: dict[str, dict] = {
        "baseline": {
            "phi_file": "inputs/phi/baseline.raw",
            "phi_sha256": PHI_SHA256,
            "changed_node_count": 0,
            "realized_rms_m": 0.0,
            "realized_max_abs_m": 0.0,
        }
    }
    realized_rows = []
    for seed in SEEDS:
        noise = np.random.RandomState(seed).standard_normal(SHAPE).astype("<f8")
        noise_payload = np.asfortranarray(noise).tobytes(order="F")
        noise_name = f"seed_{seed}_f8_fortran.raw"
        write_new(noise_dir / noise_name, noise_payload)
        noise_hashes[str(seed)] = sha_bytes(noise_payload)
        for amplitude in AMPLITUDES:
            tag = f"{amplitude:.0e}"
            for sign, sign_text in ((1, "plus"), (-1, "minus")):
                case_id = f"seed_{seed}_{sign_text}_{tag}"
                phi, realized = realize_perturbation(base, noise, amplitude, sign)
                payload = np.asfortranarray(phi).tobytes(order="F")
                phi_name = f"{case_id}.raw"
                write_new(phi_dir / phi_name, payload)
                cases[case_id] = {
                    "seed": seed,
                    "sign": sign,
                    "amplitude_m": amplitude,
                    "noise_file": f"inputs/noise/{noise_name}",
                    "noise_sha256": noise_hashes[str(seed)],
                    "phi_file": f"inputs/phi/{phi_name}",
                    "phi_sha256": sha_bytes(payload),
                    **realized,
                }
                realized_rows.append(
                    (seed, sign_text, tag, noise_hashes[str(seed)],
                     cases[case_id]["phi_sha256"], realized["changed_node_count"],
                     realized["realized_rms_m"], realized["realized_max_abs_m"])
                )

    source_hashes = _tracked_source_hashes()
    source_manifest_payload = "".join(
        f"{expected}  {relative}\n" for relative, expected in sorted(source_hashes.items())
    ).encode()
    write_new(outdir / "repository_sources.sha256", source_manifest_payload)
    body_file = Path("/Users/sota/.julia/packages/WaterLily/yOkji/src/Body.jl")
    body_sha = sha(body_file)
    if body_sha != BODY_SHA256:
        raise ValueError(f"pinned WaterLily Body.jl hash mismatch: {body_sha}")
    write_new(outdir / "realized_noise.csv", (
        "seed,sign,amplitude_m,noise_sha256,phi_sha256,changed_nodes,realized_rms_m,realized_max_abs_m\n"
        + "".join(",".join(map(str, row)) + "\n" for row in realized_rows)
    ).encode())
    input_files = sorted(
        path for path in outdir.rglob("*")
        if path.is_file() and path.name not in {"plan.json", "plan.sha256", "input_files.sha256"}
    )
    manifest_payload = "".join(
        f"{sha(path)}  {path.relative_to(outdir).as_posix()}\n" for path in input_files
    ).encode()
    write_new(outdir / "input_files.sha256", manifest_payload)
    plan = {
        "kind": "fd07_sign_consistency_causal_cpu_diagnostic_preregistration",
        "issue": "#37",
        "evidence_class": "bounded_causal_diagnostic_only",
        "created_before_initialization_or_force_inspection": True,
        "source": {
            "base_head": head,
            "branch": branch,
            "waterlily_version": "1.8.0",
            "waterlily_body_jl": str(body_file),
            "waterlily_body_jl_sha256": body_sha,
            "repository_source_sha256": source_hashes,
            "repository_sources_manifest_sha256": sha(outdir / "repository_sources.sha256"),
        },
        "preparation_runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "canonical_state": {
            "id": "v17",
            "design_origin_m": [-1.0, -0.8, -0.6],
            "design_spacing_m": 0.025,
            "shape": list(SHAPE),
            "phi_source": PHI,
            "phi_sha256": PHI_SHA256,
            "source_stl": STL,
            "source_stl_sha256": STL_SHA256,
        },
        "fixed_face_control": {
            "source_csv": FIXED_FACE_CSV,
            "source_csv_sha256": FIXED_FACE_SHA256,
            "copied_csv": "controls/fd07_fixed_face_scalar_ablation.csv",
            "maps": ["A", "B", "C"],
            "runs": ["baseline", "seed1_plus_1e-8", "seed1_minus_1e-8"],
            "fixed_face_count_per_run": 261,
            "recomputation": "parse every fixed center/face distance as Float32; reapply the pinned copysign expression and WaterLily 1.8.0 scalar mu0, then compare both arm results with the recorded CSV columns",
            "delta_threshold": 1e-3,
            "recorded_mu0_rowwise_abs_tolerance": 5e-7,
            "corrected_face_distance_bitwise_equal": True,
            "expected_baseline_relative": {
                "A": {
                    "seed1_plus_1e-8": {
                        "corrected_max_abs_delta": 0.81831123,
                        "corrected_count_abs_delta_gt_1e-3": 54,
                        "uncorrected_max_abs_delta": 2.6e-7,
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    },
                    "seed1_minus_1e-8": {
                        "corrected_max_abs_delta": 0.81831123,
                        "corrected_count_abs_delta_gt_1e-3": 64,
                        "uncorrected_max_abs_delta": 2.7e-7,
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    },
                },
                "B": {
                    "seed1_plus_1e-8": {
                        "corrected_max_abs_delta": 2.5e-7,
                        "corrected_count_abs_delta_gt_1e-3": 0,
                        "uncorrected_max_abs_delta": 2.5e-7,
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    },
                    "seed1_minus_1e-8": {
                        "corrected_max_abs_delta": 2.6e-7,
                        "corrected_count_abs_delta_gt_1e-3": 0,
                        "uncorrected_max_abs_delta": 2.6e-7,
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    },
                },
                "C": {
                    "seed1_plus_1e-8": {
                        "corrected_max_abs_delta": 0.818310245,
                        "corrected_count_abs_delta_gt_1e-3": 10,
                        "uncorrected_max_abs_delta": 2.5e-7,
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    },
                    "seed1_minus_1e-8": {
                        "corrected_max_abs_delta": 0.818310335,
                        "corrected_count_abs_delta_gt_1e-3": 23,
                        "uncorrected_max_abs_delta": 2.5e-7,
                        "uncorrected_count_abs_delta_gt_1e-3": 0,
                    },
                },
            },
            "max_delta_abs_tolerance": 5e-7,
            "counts_exact": True,
            "solver_steps": 0,
        },
        "interventions": {
            "UPSTREAM": "diagnostic copy of WaterLily 1.8.0 measure! with the pinned sign-consistency expression",
            "NO_SIGN_CORRECTION": "same diagnostic measure! and body maps, with only the copysign operation omitted",
            "scope": "the combined candidate plus moving-ground body; ground inputs and velocity remain identical",
            "normal_floor": 0.25,
            "production_package_modified": False,
            "shifted_lattice_used": False,
        },
        "solver": {
            "case_id": "flow_24",
            "flow_dims": [150, 72, 54],
            "flow_origin_m": [-2.5, -1.2, -0.9],
            "flow_spacing_m": 1.0 / 30.0,
            "solver_length": 24.0,
            "velocity": 1.0,
            "viscosity": 0.3,
            "reynolds": 80.0,
            "body": "registered v17 candidate plus V16MovingGroundBody(z_plane=0, velocity_x=1)",
            "exit_boundary": True,
            "backend": "CPU Array",
            "solver_float": "Float32",
            "phi_storage": "Float32",
            "normal_floor": 0.25,
            "pressure_solver": {"tolerance": 1e-4, "maximum_iterations": 32, "WaterLily_defaults": True},
            "stop_time_u_l": 3.0,
            "sample_every_steps": 8,
            "analysis_window_u_l": [2.0, 3.0],
            "force_conversion_n_per_solver_force": 1.0 / 900.0,
            "force_signs": {
                "pressure": "p = -WaterLily.pressure_force(flow, candidate)",
                "viscous": "v = -WaterLily.viscous_force(flow, candidate)",
                "drag": "p[1] + v[1]",
                "downforce": "-(p[3] + v[3])",
            },
        },
        "perturbations": {
            "seeds": list(SEEDS),
            "rng": "NumPy RandomState MT19937, standard-normal Float64 field; Fortran-order serialization",
            "noise_shared_between_interventions": True,
            "signs": ["plus", "minus"],
            "amplitudes_m": list(AMPLITUDES),
            "float32_realization": "phi = Float32(Float64(base_phi) + sign * amplitude * noise)",
            "noise_sha256": noise_hashes,
        },
        "input_cases": cases,
        "input_files_manifest_sha256": sha(outdir / "input_files.sha256"),
        "realized_noise_csv_sha256": sha(outdir / "realized_noise.csv"),
        "run_order": [
            f"{arm}/{case_id}"
            for case_id in ("baseline",) + tuple(
                f"seed_{seed}_{sign}_{amp:.0e}"
                for seed in SEEDS for amp in AMPLITUDES for sign in ("plus", "minus")
            )
            for arm in ("UPSTREAM", "NO_SIGN_CORRECTION")
        ],
        "solver_call_count": 26,
        "sample_fields": [
            "total drag/downforce",
            "pressure Fx/Fz",
            "viscous Fx/Fz",
            "solver time and step",
        ],
        "primary_comparisons_fixed_before_force_inspection": {
            "initial_coefficients": [
                "per-arm baseline-relative max_abs_delta_mu0",
                "per-arm baseline-relative count_abs_delta_mu0_gt_1e-3",
                "UPSTREAM versus NO_SIGN_CORRECTION baseline and perturbation coefficients",
            ],
            "solved_force": [
                "per seed/amplitude/arm: absolute plus and minus deviations from that arm baseline",
                "per seed/amplitude/arm: odd=(Rplus-Rminus)/2 and even=(Rplus+Rminus)/2-Rbaseline",
                "magnitude NO_SIGN_CORRECTION to UPSTREAM ratios for absolute deviations, odd and even; retain signed response values separately",
                "same-seed, same-amplitude geometry bytes across arms",
            ],
            "thresholds": "descriptive raw results only; no post-hoc pass/fail threshold",
        },
        "moving_ground_control": {
            "ground_geometry_and_velocity": "same V16MovingGroundBody(z_plane=0, velocity_x=1) in both arms",
            "check": "zero-step ground-only sigma, mu0, mu1 and V arrays match exactly; combined-body V and center/face map-input hashes match between arms",
        },
        "analysis": {
            "exact_window": "[2,3] tU/L, linearly interpolated endpoints and trapezoidal mean",
            "force_closure": "per-sample and exact-window pressure plus viscous closure in solver units and N",
            "response_parts": ["drag", "downforce", "pressure_fx", "pressure_fz", "viscous_fx", "viscous_fz"],
        },
        "limitations": [
            "one short CPU fixture and registered v17 state; not formal centered-FD qualification",
            "NO_SIGN_CORRECTION intentionally changes the immersed-boundary discrete model; it is not a production remedy",
            "no thin-body, conservation, long-horizon, grid-independence, or target-physics qualification",
            "single baseline per intervention; three independent noise seeds; no baseline-repeat estimate",
        ],
        "flags": {
            "fd_qualified": False,
            "sdf_gradient_qualified": False,
            "shape_update_allowed": False,
            "canonical_v18_registered": False,
            "optimizer_allowed": False,
        },
    }
    plan_path = outdir / "plan.json"
    write_new(plan_path, (json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    write_new(outdir / "plan.sha256", (sha(plan_path) + "  plan.json\n").encode())
    verify(outdir)
    return plan


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify":
        print(json.dumps(verify(Path(sys.argv[2]).resolve()), indent=2))
        raise SystemExit(0)
    evidence_dir = ROOT / EVIDENCE
    result = prepare(evidence_dir)
    print(json.dumps({
        "plan_sha256": sha(evidence_dir / "plan.json"),
        "solver_call_count": result["solver_call_count"],
        "input_cases": len(result["input_cases"]),
        "realized_noise_file": str(evidence_dir / "realized_noise.csv"),
    }, indent=2))
