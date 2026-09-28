"""Freeze the causal W3 owner-lifetime horizon diagnostic before T4 execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W3_CRITERIA_PATH = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json"
W3_DATASET_DIR = ROOT / "work/kaggle_w3_v16_dataset_round3"
TYPE_RESULT_PATH = ROOT / "docs/evidence/kaggle_w3_owner_type_probe_result_2026_09.json"
TYPE_CRITERIA_PATH = ROOT / "docs/evidence/kaggle_w3_owner_type_probe_criteria_2026_09_round2.json"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic"
JULIA_ARCHIVE_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
OUTPUT = ROOT / "docs/evidence/kaggle_w3_owner_full_horizon_criteria_2026_09.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_file_map() -> dict[str, str]:
    paths = {
        "job": "scripts/waterlily_w3_v16_owner_full_horizon_job.jl",
        "runner": "infra/kaggle/kernel_w3_owner_full_horizon/runner.py",
        "kernel_metadata": "infra/kaggle/kernel_w3_owner_full_horizon/kernel-metadata.json",
        "host_verifier": "scripts/verify_kaggle_w3_owner_full_horizon.py",
        "criteria_registrar": "scripts/register_kaggle_w3_owner_full_horizon_2026_09.py",
        "dataset_preparer": "scripts/prepare_kaggle_w3_owner_full_horizon_dataset_2026_09.py",
        "python_tests": "tests/test_kaggle_w3_owner_full_horizon.py",
        "production_w3_job": "scripts/waterlily_w3_v16_primal_job.jl",
        "cfd_sdf_module": "julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl",
        "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
        "waterlily_body": "julia/CFDSDFWaterLily/src/WaterLilyBody.jl",
        "forces": "julia/CFDSDFWaterLily/src/Forces.jl",
        "runtime": "julia/CFDSDFWaterLily/src/Runtime.jl",
        "simulation": "julia/CFDSDFWaterLily/src/Simulation.jl",
        "device_grid_sdf": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
        "v16_profile": "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl",
        "t4_smoke": "scripts/w0b_t4_smoke.jl",
        "project": "julia/CFDSDFWaterLilyT4/Project.toml",
        "manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    }
    return {key: {"path": path, "sha256": sha256(ROOT / path)} for key, path in paths.items()}


def evidence_ref(path: str) -> dict[str, str]:
    full_path = ROOT / path
    sidecar = full_path.with_suffix(full_path.suffix + ".sha256")
    if not full_path.is_file():
        raise ValueError(f"required evidence is missing: {path}")
    result = {"path": path, "sha256": sha256(full_path)}
    if sidecar.is_file():
        if sidecar.read_text().strip() != result["sha256"]:
            raise ValueError(f"evidence sidecar mismatch: {path}")
        result["sidecar_sha256"] = sha256(sidecar)
    return result


def output_for_round(round_number: int) -> Path:
    return OUTPUT if round_number == 1 else OUTPUT.with_name(
        f"kaggle_w3_owner_full_horizon_criteria_2026_09_round{round_number}.json")


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def candidate_probe_definition(phi_path: Path, geometry: dict,
                               flow_origin: list[float]) -> list[dict]:
    shape = geometry["point_shape"]
    count = shape[0] * shape[1] * shape[2]
    values = [item[0] for item in struct.iter_unpack("<f", Path(phi_path).read_bytes())]
    if len(values) != count:
        raise ValueError("canonical phi size does not match registered point shape")
    solid_linear = min(range(count), key=values.__getitem__)
    surface_linear = min(range(count), key=lambda i: abs(values[i]))
    positive_linear = min((i for i, value in enumerate(values) if value > 0), key=values.__getitem__)
    names = ("candidate_min_phi", "candidate_surface_min_abs_phi",
             "candidate_nearest_positive", "world_origin")
    linears = (solid_linear, surface_linear, positive_linear, None)
    result = []
    for name, linear in zip(names, linears):
        if linear is None:
            one_based = [0, 0, 0]
            world = [0.0, 0.0, 0.0]
        else:
            zero_based = [linear % shape[0], (linear // shape[0]) % shape[1],
                          linear // (shape[0] * shape[1])]
            one_based = [index + 1 for index in zero_based]
            world = [f32(geometry["canonical_sdf_origin_m"][axis] +
                         zero_based[axis] * geometry["spacing_m"]) for axis in range(3)]
        flow = [f32(f32(world[axis] - f32(flow_origin[axis])) /
                    f32(geometry["spacing_m"])) for axis in range(3)]
        result.append({"name": name, "canonical_index_1based": one_based,
                       "world_m": world, "flow_solver": flow})
    return result


def build(source_commit: str, round_number: int) -> dict:
    if run_git("rev-parse", "HEAD") != source_commit:
        raise ValueError("source commit must equal the checked-out HEAD")
    if run_git("branch", "--show-current") != "codex/kaggle-batch-migration":
        raise ValueError("criteria must be registered from codex/kaggle-batch-migration")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT, check=False).returncode:
        raise ValueError("tracked source tree must be clean before criteria registration")

    w3_criteria_sha = sha256(W3_CRITERIA_PATH)
    w3_sidecar = W3_CRITERIA_PATH.with_suffix(W3_CRITERIA_PATH.suffix + ".sha256")
    w3_criteria = json.loads(W3_CRITERIA_PATH.read_text())
    w3_manifest_path = W3_DATASET_DIR / "w3_v16_dataset_manifest.json"
    w3_manifest = json.loads(w3_manifest_path.read_text())
    if w3_sidecar.read_text().strip() != w3_criteria_sha:
        raise ValueError("W3 criteria sidecar mismatch")
    if w3_manifest.get("dataset_id") != w3_criteria["input_dataset_id"]:
        raise ValueError("W3 dataset id mismatch")
    if w3_manifest.get("criteria_sha256") != w3_criteria_sha:
        raise ValueError("W3 dataset is not bound to round-3 criteria")
    w3_phi_path = W3_DATASET_DIR / w3_criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    if sha256(w3_phi_path) != w3_criteria["geometry"]["phi_fortran_sha256"]:
        raise ValueError("canonical W3 phi differs from registered bytes")
    production_job_sha = sha256(ROOT / "scripts/waterlily_w3_v16_primal_job.jl")
    if production_job_sha != w3_criteria["inputs"]["job"]["sha256"]:
        raise ValueError("production W3 job differs from immutable round-3 identity")
    w3_v4_path = ROOT / "docs/evidence/kaggle_w3_v16_primal_version4_diagnostic_2026_09.json"
    w3_v4 = json.loads(w3_v4_path.read_text())
    if (w3_v4.get("source_identity", {}).get("commit") != w3_criteria["source_commit"]
            or w3_v4.get("source_identity", {}).get("registered_inputs", {}).get("job", {}).get("sha256")
            != production_job_sha):
        raise ValueError("W3 v4 comparison evidence does not bind the immutable production source")

    type_result_sha = sha256(TYPE_RESULT_PATH)
    type_result_sidecar = TYPE_RESULT_PATH.with_suffix(TYPE_RESULT_PATH.suffix + ".sha256")
    type_criteria_sha = sha256(TYPE_CRITERIA_PATH)
    type_criteria_sidecar = TYPE_CRITERIA_PATH.with_suffix(TYPE_CRITERIA_PATH.suffix + ".sha256")
    if type_result_sidecar.read_text().strip() != type_result_sha:
        raise ValueError("type-probe result sidecar mismatch")
    if type_criteria_sidecar.read_text().strip() != type_criteria_sha:
        raise ValueError("type-probe criteria sidecar mismatch")
    type_result = json.loads(TYPE_RESULT_PATH.read_text())
    type_criteria = json.loads(TYPE_CRITERIA_PATH.read_text())
    type_identity = type_result["runtime_type_identity"]
    if type_result.get("host_verification_passed") is not True:
        raise ValueError("type-probe evidence is not host-verified")
    if type_result.get("exact_kernel_ref") != "ramhachi888/cfd-opt-sdf-w3-owner-type-probe/2":
        raise ValueError("type-probe exact kernel version mismatch")
    if not all(type_identity.get(key) is True for key in (
            "cuda_device_memory_defined", "cuda_device_memory_is_parameter",
            "cuda_device_memory_is_module_binding")):
        raise ValueError("CUDA.DeviceMemory/CUDACore.DeviceMemory identity is unresolved")

    previous = {
        "w3_v4_zero_force_diagnostic": evidence_ref(w3_v4_path.relative_to(ROOT).as_posix()),
        "w3_v4_fixture_mapping_followup": evidence_ref("docs/evidence/kaggle_w3_v16_primal_version4_followup_diagnostic_2026_09.json"),
        "owner_lifetime_round4_criteria": evidence_ref("docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round4.json"),
        "owner_lifetime_v7_result": evidence_ref("docs/evidence/kaggle_w3_v16_cuda_diagnostic_version7_2026_09.json"),
        "owner_lifetime_v7_host_correction": evidence_ref("docs/evidence/kaggle_w3_v16_cuda_diagnostic_version7_host_correction_2026_09.json"),
        "type_probe_round1_diagnostic": evidence_ref("docs/evidence/kaggle_w3_owner_type_probe_version1_diagnostic_2026_09.json"),
        "type_probe_round2_criteria": evidence_ref(TYPE_CRITERIA_PATH.relative_to(ROOT).as_posix()),
        "type_probe_round2_result": evidence_ref(TYPE_RESULT_PATH.relative_to(ROOT).as_posix()),
    }
    if round_number > 1:
        previous["owner_full_horizon_round1_criteria"] = evidence_ref(
            "docs/evidence/kaggle_w3_owner_full_horizon_criteria_2026_09.json")
    dataset_id = "ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-criteria"
    if round_number > 1:
        dataset_id += f"-round{round_number}"
    files = source_file_map()
    return {
        "schema_version": 1,
        "criteria_id": f"kaggle_w3_owner_full_horizon_2026_09_round{round_number}",
        "round": round_number,
        "evidence_type": "diagnostic_only",
        "immutable": True,
        "registered_before_computation": True,
        "source_commit": source_commit,
        "source_branch": "codex/kaggle-batch-migration",
        "source_files": files,
        "kernel_id": KERNEL_ID,
        "kernel_version": 1 if round_number == 1 else round_number,
        "criteria_dataset_id": dataset_id,
        "claim_scope": "test whether backing CuArray owner collection reproduces the W3 v4 all-zero force history on the exact registered full-horizon WaterLily path; no primal qualification",
        "round_reason": None if round_number == 1 else (
            "round 1 was submitted under the title-derived Kaggle slug, which differed from the registered kernel-metadata id; "
            "round 2 binds the exact observed slug and changes no solver semantics, thresholds, arms, inputs, or measurement rules"),
        "type_probe_prerequisite": {
            "criteria_id": type_criteria["criteria_id"],
            "criteria_path": TYPE_CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "criteria_sha256": type_criteria_sha,
            "criteria_sidecar_sha256": sha256(type_criteria_sidecar),
            "exact_kernel_ref": type_result["exact_kernel_ref"],
            "result_path": TYPE_RESULT_PATH.relative_to(ROOT).as_posix(),
            "result_sha256": type_result_sha,
            "result_sidecar_sha256": sha256(type_result_sidecar),
            "output_manifest_sha256": type_result["output_manifest_sha256"],
            "kaggle_log_sha256": type_result["kaggle_log_sha256"],
            "host_verifier_sha256": type_result["host_verifier_sha256"],
            "runtime_type_identity": type_identity,
            "exact_identity_claim": "CUDA.DeviceMemory is defined and identical by === to the owner array's third type parameter, CUDACore.DeviceMemory, on the registered Julia 1.12.6 / CUDA.jl 6.3.1 / CUDACore 6.3.1 T4 runtime",
        },
        "w3_input": {
            "criteria_path": W3_CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "criteria_sha256": w3_criteria_sha,
            "criteria_sidecar_sha256": sha256(w3_sidecar),
            "dataset_id": w3_manifest["dataset_id"],
            "dataset_manifest_sha256": sha256(w3_manifest_path),
            "canonical_npz_sha256": w3_criteria["inputs"]["canonical_state_npz"]["sha256"],
            "phi_fortran_sha256": w3_criteria["geometry"]["phi_fortran_sha256"],
            "phi_c_order_sha256": w3_criteria["geometry"]["phi_c_order_sha256"],
            "state_sha256": w3_criteria["geometry"]["state_sha256"],
            "source_surface_sha256": w3_criteria["geometry"]["source_surface_sha256"],
            "design_domain_sha256": w3_criteria["geometry"]["design_domain_sha256"],
        },
        "prior_evidence": previous,
        "comparison_production_source": {
            "w3_v4_source_commit": w3_v4["source_identity"]["commit"],
            "production_job_path": "scripts/waterlily_w3_v16_primal_job.jl",
            "production_job_sha256": production_job_sha,
            "same_as_immutable_w3_round3_job": True,
            "w3_v4_observed_solver_steps": 3841,
            "w3_v4_observed_t_u_l": 120.015625,
            "w3_v4_force_rows": 481,
            "w3_v4_all_total_pressure_viscous_force_components_exact_zero": True,
            "w3_v4_velocity_pressure_finite": True,
        },
        "fixture": {
            "canonical_sdf_origin_m": w3_criteria["geometry"]["canonical_sdf_origin_m"],
            "canonical_phi_margin_m": w3_criteria["geometry"]["expected_margin_m"],
            "point_shape": w3_criteria["geometry"]["point_shape"],
            "spacing_m": w3_criteria["geometry"]["spacing_m"],
            "flow_dims": w3_criteria["profile_adapter"]["cell_dims"],
            "flow_origin_m": w3_criteria["profile_adapter"]["flow_origin_m"],
            "flow_upper_m": [pair[1] for pair in w3_criteria["profile_adapter"]["physical_box_m"]],
            "reynolds": w3_criteria["profile_adapter"]["reynolds"],
            "solver_length": w3_criteria["profile_adapter"]["solver_length"],
            "solver_viscosity": w3_criteria["profile_adapter"]["solver_viscosity"],
            "reference_area_m2": w3_criteria["measurement"]["reference_area_m2"],
            "density_kg_m3": w3_criteria["measurement"]["density_kg_m3"],
            "freestream_mps": w3_criteria["measurement"]["freestream_mps"],
            "force_scale_n_per_solver_unit": w3_criteria["measurement"]["density_kg_m3"] *
                w3_criteria["measurement"]["freestream_mps"][0] ** 2 * w3_criteria["geometry"]["spacing_m"] ** 2,
            "candidate_force_body": "canonical candidate GridSDF only; do not integrate auxiliary moving ground",
            "drag_projection": "+Fx_body",
            "downforce_projection": "-Fz_body",
            "body_composition": "canonical v16 candidate plus registered moving-ground half-space",
            "boundary_semantics": "unchanged native WaterLily 1.8.0 finite-box adapter; not equivalent to OpenFOAM per-patch freestream pressure/velocity",
            "candidate_probe_points": candidate_probe_definition(
                w3_phi_path, w3_criteria["geometry"], w3_criteria["profile_adapter"]["flow_origin_m"]),
        },
        "backend": {
            "machine_shape": w3_criteria["backend"]["machine_shape"],
            "gpu_count": w3_criteria["backend"]["gpu_count"],
            "gpu_name": w3_criteria["backend"]["gpu_name"],
            "driver_version": w3_criteria["backend"]["driver_version"],
            "compute_capability": w3_criteria["backend"]["compute_capability"],
            "cuda_driver_api_version": w3_criteria["backend"]["cuda_driver_api_version"],
            "cuda_runtime_version": w3_criteria["backend"]["cuda_runtime_version"],
            "cuda_visible_devices": "0",
            "julia_version": w3_criteria["backend"]["julia_version"],
            "julia_threads": w3_criteria["backend"]["julia_threads"],
            "cuda_jl_version": w3_criteria["backend"]["cuda_jl_version"],
            "cudacore_version": "6.3.1",
            "waterlily_version": w3_criteria["backend"]["waterlily_version"],
            "waterlily_backend": w3_v4["backend_identity"]["waterlily_backend"],
            "julia_archive_sha256": JULIA_ARCHIVE_SHA256,
            "selected_gpu_policy": "visible GPU index 0; record runtime UUID",
        },
        "arm_order": ["A-natural", "A-forced", "B-natural-1", "B-natural-2", "B-forced-1", "B-forced-2"],
        "arm_semantics": {
            "A-natural": "structurally retain backing DeviceGridSDF owner for full horizon; automatic GC enabled; no explicit GC",
            "A-forced": "same retained owner and exact forced-GC bracket as B-forced arms; owner retention isolates the GC intervention",
            "B-natural-1/B-natural-2": "production-equivalent helper boundary returns only bodies/simulation/WeakRef; no strong owner reference; ordinary automatic GC; independent Julia process per replicate; no explicit GC",
            "B-forced-1/B-forced-2": "same unrooted helper boundary, automatic GC suppressed during setup/warmup, then registered two-call forced-GC bracket after warmup step 1; diagnostic causal control only",
            "production_equivalence": "same canonical input, DeviceGridSDF->CuDeviceArray mapping, v16 bodies, WaterLily simulation and sim_step! sequence, warm-up, tU/L=120 loop, force body/signs, stride and time window as the pinned W3 production job; no production source edits",
        },
        "measurement": {
            "target_t_u_l": 120.0,
            "minimum_t_u_l": 120.0,
            "warmup": "one sim_step! before timed horizon, same as W3 production job",
            "force_sample_stride_steps": w3_criteria["measurement"]["sample_every_solver_steps"],
            "minimum_window_samples": w3_criteria["measurement"]["minimum_window_samples"],
            "force_window_t_u_l": w3_criteria["measurement"]["force_window_t_u_l"],
            "endpoint_policy": w3_criteria["measurement"]["endpoint_policy"],
            "integration": w3_criteria["measurement"]["integration"],
            "host_recompute_relative_tolerance": w3_criteria["measurement"]["host_recompute_relative_tolerance"],
            "host_recompute_absolute_tolerance": 1e-10,
            "host_recompute_absolute_tolerance_precedent": "inherited unchanged from scripts/verify_kaggle_w3_v16.py",
            "pressure_viscous_projection": "pressure=-WaterLily.pressure_force; viscous=-WaterLily.viscous_force; total=pressure+viscous",
            "finite_field_snapshots": "at first observed collection and full-horizon endpoint; summarize finite flags and min/max/mean for velocity and pressure",
            "candidate_sdf_normal_probes": "at first observed collection and full-horizon endpoint; four preregistered world points from unchanged canonical phi plus registered flow-origin mapping",
            "owner_weakref": "observe backing owner.grid.phi after each sim_step!, after the production force and CUDA memory sampling operations; never promote the WeakRef target to a retained local",
            "cuda_memory_sampling": "after warm-up, every 50 steps, and at full-horizon endpoint",
            "per_arm_runtime_limit_s": 1800,
            "kernel_runtime_limit_s": 7200,
        },
        "causal_decision_rules": {
            "force_component_absolute_tolerance": w3_criteria["measurement"]["force_component_absolute_tolerance"],
            "force_component_relative_tolerance": w3_criteria["measurement"]["force_component_relative_tolerance"],
            "force_divergence_absolute_tolerance": w3_criteria["measurement"]["force_component_absolute_tolerance"],
            "force_divergence_relative_tolerance": w3_criteria["measurement"]["force_component_relative_tolerance"],
            "minimum_post_collection_force_samples": w3_criteria["measurement"]["minimum_window_samples"],
            "exact_zero_definition": "all sampled total, pressure, viscous, drag and downforce components are finite and exactly numerically zero",
            "full_horizon_v4_correspondence": "full horizon reaches tU/L>=120, all raw force components exactly zero across the history, finite endpoint velocity and pressure, and at least the registered minimum count of post-collection force samples",
            "owner_lifetime_bug_confirmed": "A-natural and A-forced both retain the backing owner and complete the full horizon with finite fields and nonzero forces; both independent B-natural replicates complete the full horizon, observe owner collection, and show at least the registered number of post-collection samples with reproducible corruption beginning after collection; pre-collection force samples, when present, match A-natural within the registered W3 component tolerances; both B-natural replicates have the same post-collection failure class",
            "strong_w3_v4_root_cause_support": "owner-lifetime implementation-bug rule passes and both B-natural replicates reproduce the exact full-horizon zero-force/finite-field W3 v4 failure class while A controls remain nonzero and finite",
            "forced_gc_role": "B-forced can corroborate the mechanism but cannot by itself satisfy the production-fix gate or prove ordinary-GC causation",
            "if_natural_owner_not_collected": "do not apply a production fix based on forced-only results; classify ordinary-GC hypothesis as weakened and preserve the exact W3 v4 cause as open",
            "threshold_policy": "all force component and divergence tolerances are inherited unchanged from immutable W3 round-3 criteria; no post-measurement threshold adjustment",
        },
        "evidence_output": {
            "artifact_schema": ["fingerprint.json", "execution.json", "input_mount_inventory.json", "per-arm summary/force/progress/field/probe/memory/log files", "sha256.json", "DONE or ERROR.txt"],
            "qualification": False,
            "qualification_flags": {key: False for key in (
                "waterlily_v16_primal_qualified", "physical_profile_qualified", "grid_response_qualified",
                "sdf_gradient_qualified", "waterlily_reverse_cpu_qualified", "waterlily_reverse_cuda_qualified",
                "topology_birth_qualified", "shape_update_allowed")},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--round", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    output = output_for_round(args.round)
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or sidecar.exists():
        raise SystemExit("refusing to overwrite owner full-horizon criteria")
    criteria = build(args.source_commit, args.round)
    payload = json.dumps(criteria, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    output.write_text(payload)
    sidecar.write_text(digest + "\n")
    print(json.dumps({"criteria_path": output.relative_to(ROOT).as_posix(), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
