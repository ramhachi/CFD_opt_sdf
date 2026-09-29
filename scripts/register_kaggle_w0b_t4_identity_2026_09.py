"""Freeze the W0b-Kaggle T4 CUDA/WaterLily identity criteria before any Kaggle run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/evidence/kaggle_w0b_t4_identity_criteria_2026_09.json"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-w0b-kaggle-t4-identity"
JULIA_ARCHIVE_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
SOURCE_PATHS = {
    "smoke": "scripts/w0b_t4_smoke.jl",
    "project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "identity_module": "scripts/t4_backend_identity.py",
    "criteria_registrar": "scripts/register_kaggle_w0b_t4_identity_2026_09.py",
    "host_verifier": "scripts/verify_kaggle_w0b.py",
    "python_tests": "tests/test_w0b_kaggle_registration.py",
    "kernel_metadata": "infra/kaggle/kernel_w0b/kernel-metadata.json",
}
# Historical/basis evidence; read-only.  The Kaggle expected values below come from these.
BASIS_EVIDENCE = {
    "colab_w0b_result": "docs/evidence/sdf_native_w0b_t4_cuda_env_2026_09.json",
    "kaggle_k0_result": "docs/evidence/kaggle_k0_result_2026_09.json",
    "kaggle_w2b_round5_criteria": "docs/evidence/kaggle_w2b_criteria_2026_09_round5.json",
}
FLAGS = ("sdf_gradient_qualified", "shape_update_allowed", "topology_birth_qualified",
         "waterlily_reverse_cpu_qualified", "waterlily_reverse_cuda_qualified")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(source_commit: str) -> dict:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if source_commit != head:
        raise ValueError("source commit must equal the checked-out HEAD")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT, check=False).returncode != 0:
        raise ValueError("tracked source tree must be clean before criteria registration")
    files = {key: {"path": rel, "sha256": sha256(ROOT / rel)} for key, rel in SOURCE_PATHS.items()}
    return {
        "schema_version": 1,
        "criteria_id": "kaggle_w0b_t4_identity_2026_09_round1",
        "kind": "kaggle_w0b_t4_cuda_waterlily_identity_criteria",
        "round": 1,
        "evidence_class": "capability_and_contract",
        "immutable": True,
        "registered_before_computation": True,
        "solver_started": False,
        "source_commit": source_commit,
        "kernel": {
            "id": KERNEL_ID,
            "private": True,
            "accelerator": "NvidiaTeslaT4",
            "timeout_seconds": 1800,
            "dataset_sources": [],
            "source_ref": "refs/heads/feat/issue-42-w0b-kaggle",
            "runner_binding": "The runner embeds the commit holding this criteria file, so it cannot be hashed here; "
                              "the runner SHA-256 is recorded in the run fingerprint and re-checked by the host verifier against the committed file.",
            "max_submissions": 3,
        },
        "source_files": files,
        "basis_evidence": {key: {"path": rel, "sha256": sha256(ROOT / rel)} for key, rel in BASIS_EVIDENCE.items()},
        "identity_policy": {
            "uuid": "Kaggle rotates the physical GPU (and exposes two T4s) per run, so a UUID cannot be a registered "
                    "binding as in the Colab W0b. The selected GPU UUID (nvidia-smi index 0 == CUDA_VISIBLE_DEVICES=0) "
                    "is recorded from the observation and only checked for form, uniqueness, inventory membership and "
                    "agreement with the UUID Julia CUDA.jl reports for its device.",
            "bound": "GPU model, compute capability, VRAM, driver-major pattern, CUDA driver API and runtime versions, "
                     "Julia/CUDA.jl/WaterLily versions, T4 Project/Manifest SHA-256, pinned Julia archive SHA-256. "
                     "These are what determine whether the same CUDA/WaterLily binary path runs; any drift is a fail-closed "
                     "stop and requires a new registration round.",
            "reason_driver_pattern": "Every earlier Kaggle T4 run (K0, W1g, W2b, W3, W4, FD) observed driver 580.159.04; the "
                                     "branch (major) is bound and the exact value is recorded.",
        },
        "backend": {
            "gpu_name": "Tesla T4",
            "compute_capability": "7.5.0",
            "memory_total_mib": 15360,
            "gpu_count_min": 1,
            "all_gpus_must_be_model": "Tesla T4",
            "driver_version_pattern": r"580\.\d+\.\d+",
            "cuda_driver_api_version": "13.3.0",
            "cuda_runtime_version": "12.8.0",
            "julia_version": "1.12.6",
            "cuda_jl_version": "6.3.1",
            "waterlily_version": "1.8.0",
            "project_sha256": files["project"]["sha256"],
            "manifest_sha256": files["manifest"]["sha256"],
            "julia_archive_sha256": JULIA_ARCHIVE_SHA256,
        },
        "gates": {
            "G0_targeted_runtime": "every nvidia-smi device is Tesla T4 with the registered VRAM and driver pattern, at least gpu_count_min devices",
            "G1_cuda_functional": "CUDA_FUNCTIONAL true in the registered smoke output",
            "G2_cuarray_smoke": "CUARRAY_SMOKE true (registered exact Float32 CuArray round trip, broadcast, reduction)",
            "G3_ka_smoke": "KA_SMOKE true (registered exact KernelAbstractions kernel over a CuArray)",
            "G4_waterlily_cuda_ext": "WATERLILY_CUDA_EXT true (Base.get_extension(WaterLily, :WaterLilyCUDAExt) is not nothing)",
            "G5_no_solver_step": "NO_SOLVER_STEP present and W0B_SMOKE_DONE; the smoke script (bound by SHA-256) constructs no Simulation and calls no sim_step!",
            "G6_identity": "the observed identity equals the backend block (exact fields, driver pattern, VRAM, Project/Manifest SHA-256)",
            "G7_uuid_recorded_consistent": "selected UUID is well-formed, unique in the nvidia-smi inventory, and equals the CUDA.jl device UUID",
            "G8_source_binding": "the kernel checked out the criteria commit, matched the criteria SHA-256, and every source_files SHA-256 (rechecked on host)",
            "G9_artifact_integrity": "DONE marker present, no ERROR.txt, every output file matches sha256.json, runner SHA-256 equals the committed runner",
            "threshold_modification_rule": "no gate or backend value changes after a measurement; a failure is a fail-closed diagnostic and a source-only fix needs a new round",
        },
        "retry_policy": "At most two retries after the first submission (max_submissions 3). A wrong-GPU allocation is recorded as a diagnostic and may be retried unchanged. A source change needs a new round with new criteria.",
        "claims_supported_on_pass": [
            "the committed julia/CFDSDFWaterLilyT4 Project/Manifest pair instantiates on the private Kaggle NvidiaTeslaT4 runtime",
            "CUDA.jl is functional on the T4 and the WaterLily CUDA extension activates",
            "CuArray and KernelAbstractions CUDA smoke operations pass",
            "the Kaggle T4 identity (driver, CUDA runtime, package versions) equals the registered values",
        ],
        "claims_not_supported": [
            "no WaterLily time step, force value or GridSDF geometry fixture (W1g is not run here)",
            "no CUDA/Enzyme reverse capability",
            "no FD, gradient, topology or optimizer claim",
            "no absolute, grid-independent, high-Re or full-vehicle downforce claim",
        ],
        "flags": {name: False for name in FLAGS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    sidecar = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
    if OUTPUT.exists() or sidecar.exists():
        raise SystemExit("refusing to overwrite W0b-Kaggle criteria")
    payload = json.dumps(build(args.source_commit), indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    OUTPUT.write_text(payload)
    sidecar.write_text(digest + "\n")
    print(json.dumps({"criteria_path": str(OUTPUT.relative_to(ROOT)), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
