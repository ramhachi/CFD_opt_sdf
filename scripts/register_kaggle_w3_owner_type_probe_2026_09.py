"""Freeze the exact-source T4 type-identity diagnostic before submission."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/evidence/kaggle_w3_owner_type_probe_criteria_2026_09.json"
W3_CRITERIA = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json"
W3_DATASET = ROOT / "work/kaggle_w3_v16_dataset_round3"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-w3-owner-type-probe"
CRITERIA_DATASET_ID = "ramhachi888/cfd-opt-sdf-w3-owner-type-probe-criteria"
JULIA_ARCHIVE_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(source_commit: str) -> dict:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if source_commit != head:
        raise ValueError("source commit must equal the checked-out HEAD")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("source tree must be clean before criteria registration")
    w3_sha = sha256(W3_CRITERIA)
    w3_criteria = json.loads(W3_CRITERIA.read_text())
    w3_sidecar = W3_CRITERIA.with_suffix(W3_CRITERIA.suffix + ".sha256")
    manifest_path = W3_DATASET / "w3_v16_dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if w3_sidecar.read_text().strip() != w3_sha:
        raise ValueError("W3 round-3 criteria sidecar mismatch")
    if manifest.get("criteria_sha256") != w3_sha:
        raise ValueError("canonical dataset does not use W3 round-3 criteria")

    source_paths = {
        "probe_job": "scripts/waterlily_w3_v16_owner_type_probe_job.jl",
        "production_w3_job": "scripts/waterlily_w3_v16_primal_job.jl",
        "runner": "infra/kaggle/kernel_w3_owner_type_probe/runner.py",
        "kernel_metadata": "infra/kaggle/kernel_w3_owner_type_probe/kernel-metadata.json",
        "host_verifier": "scripts/verify_kaggle_w3_owner_type_probe.py",
        "criteria_registrar": "scripts/register_kaggle_w3_owner_type_probe_2026_09.py",
        "dataset_preparer": "scripts/prepare_kaggle_w3_owner_type_probe_dataset_2026_09.py",
        "python_tests": "tests/test_kaggle_w3_owner_type_probe.py",
        "project": "julia/CFDSDFWaterLilyT4/Project.toml",
        "manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
        "t4_smoke": "scripts/w0b_t4_smoke.jl",
    }
    files = {key: {"path": relative, "sha256": sha256(ROOT / relative)}
             for key, relative in source_paths.items()}
    return {
        "schema_version": 1,
        "criteria_id": "kaggle_w3_owner_type_probe_2026_09",
        "evidence_type": "diagnostic_only",
        "immutable": True,
        "registered_before_computation": True,
        "claim_scope": "exact registered Kaggle T4 Julia runtime identity for the backing SDF CuArray memory type; no solver or qualification claim",
        "kernel_id": KERNEL_ID,
        "criteria_dataset_id": CRITERIA_DATASET_ID,
        "source_commit": source_commit,
        "source_files": files,
        "w3_input": {
            "criteria_path": W3_CRITERIA.relative_to(ROOT).as_posix(),
            "criteria_sha256": w3_sha,
            "criteria_sidecar_sha256": sha256(w3_sidecar),
            "dataset_id": w3_criteria["input_dataset_id"],
            "dataset_manifest_path": "w3_v16_dataset_manifest.json",
            "dataset_manifest_sha256": sha256(manifest_path),
            "canonical_state_npz_sha256": w3_criteria["inputs"]["canonical_state_npz"]["sha256"],
            "phi_c_order_sha256": w3_criteria["geometry"]["phi_c_order_sha256"],
            "phi_fortran_sha256": w3_criteria["geometry"]["phi_fortran_sha256"],
            "canonical_sdf_origin_m": w3_criteria["geometry"]["canonical_sdf_origin_m"],
            "spacing_m": w3_criteria["geometry"]["spacing_m"],
            "point_shape": w3_criteria["geometry"]["point_shape"],
            "state_sha256": w3_criteria["geometry"]["state_sha256"],
            "design_domain_sha256": w3_criteria["geometry"]["design_domain_sha256"],
        },
        "backend": {
            **w3_criteria["backend"],
            "julia_archive_sha256": JULIA_ARCHIVE_SHA256,
            "cuda_core_version": "observe from exact T4 runtime; not assumed from a type display label",
        },
        "observations": {
            "owner_array": ["typeof", "eltype", "ndims", "size"],
            "memory_type": ["type_parameter_object", "string", "parentmodule", "package_uuid", "package_version"],
            "cuda_device_memory": ["isdefined(CUDA, :DeviceMemory)", "=== actual memory type parameter when defined"],
            "module_device_memory": ["isdefined(parentmodule(memory_type), :DeviceMemory)", "=== actual memory type parameter when defined"],
            "kernel_view_type": "record separately",
            "canonical_gpu_roundtrip_sha256": w3_criteria["geometry"]["phi_fortran_sha256"],
            "solver_steps": 0,
        },
        "prior_evidence": {
            "owner_lifetime_round4_criteria": {
                "path": "docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round4.json",
                "sha256": sha256(ROOT / "docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round4.json"),
            },
            "owner_lifetime_v7_result": {
                "path": "docs/evidence/kaggle_w3_v16_cuda_diagnostic_version7_2026_09.json",
                "sha256": sha256(ROOT / "docs/evidence/kaggle_w3_v16_cuda_diagnostic_version7_2026_09.json"),
            },
            "owner_lifetime_v7_host_correction": {
                "path": "docs/evidence/kaggle_w3_v16_cuda_diagnostic_version7_host_correction_2026_09.json",
                "sha256": sha256(ROOT / "docs/evidence/kaggle_w3_v16_cuda_diagnostic_version7_host_correction_2026_09.json"),
            },
        },
        "qualification_flags": {key: False for key in (
            "waterlily_v16_primal_qualified", "physical_profile_qualified",
            "sdf_gradient_qualified", "waterlily_reverse_cpu_qualified",
            "waterlily_reverse_cuda_qualified", "topology_birth_qualified",
            "shape_update_allowed")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if OUTPUT.exists() or OUTPUT.with_suffix(OUTPUT.suffix + ".sha256").exists():
        raise SystemExit("refusing to overwrite type-probe criteria")
    criteria = build(args.source_commit)
    payload = json.dumps(criteria, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    OUTPUT.write_text(payload)
    OUTPUT.with_suffix(OUTPUT.suffix + ".sha256").write_text(digest + "\n")
    print(json.dumps({"criteria_path": str(OUTPUT.relative_to(ROOT)), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
