"""Independently verify the exact-version W3 CUDA memory-type probe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_runtime_type(result: dict, criteria: dict) -> dict:
    expected = criteria["backend"]
    for key in ("julia_version", "cuda_jl_version", "waterlily_version"):
        require(result[key] == expected[key], f"runtime {key} mismatch")
    require(result["selected_gpu_name"] == expected["gpu_name"], "selected GPU name mismatch")
    require(result["cuda_visible_devices"] == "0", "probe CUDA_VISIBLE_DEVICES mismatch")
    owner = result["owner"]
    module = owner["memory_module"]
    require(owner["eltype"] == "Float32" and owner["ndims"] == 3,
            "owner array element type or rank mismatch")
    require(owner["size"] == criteria["w3_input"]["point_shape"], "owner array shape mismatch")
    require(owner["memory_parameter"] in owner["type"], "memory parameter is absent from owner type")
    require(module["module"] == "CUDACore", "observed owner memory type parent module differs from CUDACore")
    require(module["package_version"], "CUDACore package version missing")
    require(isinstance(owner["module_device_memory_defined"], bool), "module binding observation missing")
    require(owner["module_device_memory_defined"] == isinstance(owner["module_device_memory_is_parameter"], bool),
            "module binding identity observation inconsistent")
    require(isinstance(owner["cuda_device_memory_defined"], bool), "CUDA binding observation missing")
    require(owner["cuda_device_memory_defined"] == isinstance(owner["cuda_device_memory_is_parameter"], bool),
            "CUDA type identity observation inconsistent")
    if owner["cuda_device_memory_defined"]:
        require(isinstance(owner["cuda_device_memory_is_module_binding"], bool),
                "CUDA/CUDACore identity comparison missing")
    else:
        require(owner["cuda_device_memory_is_module_binding"] is None,
                "undefined CUDA binding must not be compared")
    return owner


def verify(output_dir: Path, criteria_path: Path, criteria_dataset_dir: Path,
           w3_dataset_dir: Path, kernel_version: int,
           status_path: Path, log_path: Path) -> dict:
    criteria_path = Path(criteria_path)
    criteria_sha = sha256(criteria_path)
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    require(sidecar.read_text().strip() == criteria_sha, "criteria sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    require(criteria.get("immutable") is True and criteria.get("registered_before_computation") is True,
            "criteria are not preregistered")
    require(criteria.get("evidence_type") == "diagnostic_only", "criteria evidence class mismatch")

    criteria_manifest = Path(criteria_dataset_dir) / "w3_owner_type_probe_dataset_manifest.json"
    dataset_manifest = json.loads(criteria_manifest.read_text())
    require(dataset_manifest.get("dataset_id") == criteria["criteria_dataset_id"],
            "criteria dataset id mismatch")
    for filename, digest in dataset_manifest["files"].items():
        require(sha256(Path(criteria_dataset_dir) / filename) == digest,
                f"criteria dataset file hash mismatch: {filename}")

    w3_manifest = Path(w3_dataset_dir) / "w3_v16_dataset_manifest.json"
    require(sha256(w3_manifest) == criteria["w3_input"]["dataset_manifest_sha256"],
            "W3 dataset manifest mismatch")
    w3_manifest_json = json.loads(w3_manifest.read_text())
    require(w3_manifest_json.get("dataset_id") == criteria["w3_input"]["dataset_id"],
            "W3 dataset id mismatch")
    for filename, digest in w3_manifest_json["files"].items():
        require(sha256(Path(w3_dataset_dir) / filename) == digest,
                f"W3 input hash mismatch: {filename}")

    output_dir = Path(output_dir)
    require(not (output_dir / "ERROR.txt").exists(), "kernel output contains ERROR.txt")
    require((output_dir / "DONE").is_file(), "kernel output lacks DONE marker")
    output_manifest_path = output_dir / "sha256.json"
    output_manifest = json.loads(output_manifest_path.read_text())
    actual = {p.name for p in output_dir.iterdir() if p.is_file() and p.name not in {"sha256.json", "DONE"}}
    require(actual == set(output_manifest), "output artifact inventory differs from sha256.json")
    for name, digest in output_manifest.items():
        require(sha256(output_dir / name) == digest, f"output artifact hash mismatch: {name}")

    fingerprint = json.loads((output_dir / "fingerprint.json").read_text())
    result = json.loads((output_dir / "type_identity.json").read_text())
    execution = json.loads((output_dir / "execution.json").read_text())
    require(fingerprint["kernel_id"] == criteria["kernel_id"], "kernel id mismatch")
    require(fingerprint["source_commit"] == criteria["source_commit"], "source commit mismatch")
    require(fingerprint["source_files"] == criteria["source_files"], "source file identity mismatch")
    require(fingerprint["runner_sha256"] == criteria["source_files"]["runner"]["sha256"],
            "runner SHA mismatch")
    require(fingerprint["criteria"]["criteria_sha256"] == criteria_sha,
            "runtime criteria SHA mismatch")
    require(fingerprint["criteria_dataset_id"] == criteria["criteria_dataset_id"],
            "runtime criteria dataset id mismatch")
    require(fingerprint["w3_dataset_id"] == criteria["w3_input"]["dataset_id"],
            "runtime W3 dataset id mismatch")
    require(fingerprint["criteria"]["w3_dataset_manifest_sha256"] == criteria["w3_input"]["dataset_manifest_sha256"],
            "runtime W3 manifest identity mismatch")
    require(fingerprint["selected_gpu_uuid"], "selected GPU UUID missing")
    require(fingerprint["cuda_visible_devices"] == "0", "CUDA_VISIBLE_DEVICES mismatch")
    require(len(fingerprint["gpu_inventory"]) == criteria["backend"]["gpu_count"],
            "GPU inventory count mismatch")
    require(all(criteria["backend"]["gpu_name"] in row and criteria["backend"]["driver_version"] in row
                for row in fingerprint["gpu_inventory"]), "GPU model/driver mismatch")

    owner = verify_runtime_type(result, criteria)
    require(result["selected_gpu_uuid"] == fingerprint["selected_gpu_uuid"], "selected GPU UUID mismatch")
    require(result["gpu_roundtrip_sha256"] == criteria["w3_input"]["phi_fortran_sha256"],
            "GPU phi round-trip hash mismatch")
    require(result["canonical_phi_fortran_sha256"] == criteria["w3_input"]["phi_fortran_sha256"],
            "canonical Fortran hash mismatch")
    require(result["canonical_phi_c_order_sha256"] == criteria["w3_input"]["phi_c_order_sha256"],
            "canonical C-order hash mismatch")
    require(result["solver_steps"] == 0 and execution["solver_steps"] == 0,
            "type probe unexpectedly ran solver steps")
    require(execution["qualification"] is False and result["qualification"] is False,
            "type probe must not qualify any solver")

    status = Path(status_path).read_text()
    require("COMPLETE" in status.upper(), "exact Kaggle kernel status is not COMPLETE")
    log_sha = sha256(Path(log_path))
    return {
        "evidence_type": "diagnostic_only",
        "criteria_path": str(criteria_path),
        "criteria_sha256": criteria_sha,
        "criteria_dataset_manifest_sha256": sha256(criteria_manifest),
        "w3_dataset_manifest_sha256": sha256(w3_manifest),
        "source_commit": criteria["source_commit"],
        "kernel_id": criteria["kernel_id"],
        "kernel_version": kernel_version,
        "exact_kernel_ref": f"{criteria['kernel_id']}/{kernel_version}",
        "host_verification_passed": True,
        "host_verifier_sha256": sha256(Path(__file__)),
        "runtime_type_identity": owner,
        "julia_version": result["julia_version"],
        "cuda_jl_version": result["cuda_jl_version"],
        "waterlily_version": result["waterlily_version"],
        "gpu_inventory": fingerprint["gpu_inventory"],
        "selected_gpu_uuid": fingerprint["selected_gpu_uuid"],
        "cuda_visible_devices": fingerprint["cuda_visible_devices"],
        "canonical_phi_fortran_sha256": result["canonical_phi_fortran_sha256"],
        "canonical_phi_c_order_sha256": result["canonical_phi_c_order_sha256"],
        "gpu_roundtrip_sha256": result["gpu_roundtrip_sha256"],
        "solver_steps": 0,
        "output_manifest_sha256": sha256(output_manifest_path),
        "kaggle_status_sha256": sha256(Path(status_path)),
        "kaggle_log_sha256": log_sha,
        "qualification_flags": criteria["qualification_flags"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--criteria", required=True, type=Path)
    parser.add_argument("--criteria-dataset-dir", required=True, type=Path)
    parser.add_argument("--w3-dataset-dir", required=True, type=Path)
    parser.add_argument("--kernel-version", required=True, type=int)
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--record-evidence", action="store_true")
    args = parser.parse_args()
    evidence = verify(args.output, args.criteria, args.criteria_dataset_dir,
                      args.w3_dataset_dir, args.kernel_version, args.status, args.log)
    if args.record_evidence:
        output = args.criteria.parent / "kaggle_w3_owner_type_probe_result_2026_09.json"
        sidecar = output.with_suffix(output.suffix + ".sha256")
        require(not output.exists() and not sidecar.exists(), "refusing to overwrite type-probe evidence")
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        output.write_text(payload)
        sidecar.write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
