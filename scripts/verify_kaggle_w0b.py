#!/usr/bin/env python3
"""Strictly verify a version-specific Kaggle W0b download and (optionally) record the immutable result."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from t4_backend_identity import verify_kaggle_backend_identity  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs/evidence/kaggle_w0b_t4_identity_criteria_2026_09.json"
RESULT_STEM = "kaggle_w0b_t4_identity_result_2026_09"
RUNNER = ROOT / "infra/kaggle/kernel_w0b/runner.py"
FLAGS = ("sdf_gradient_qualified", "shape_update_allowed", "topology_birth_qualified",
         "waterlily_reverse_cpu_qualified", "waterlily_reverse_cuda_qualified")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def marker(text: str, key: str):
    match = re.search(rf"^{re.escape(key)} (.+)$", text, re.M)
    return match.group(1).strip() if match else None


def parse_rows(text: str) -> list[list[str]]:
    return [[part.strip() for part in line.split(",")] for line in text.splitlines() if line.strip()]


def evaluate(folder: Path, criteria: dict) -> tuple[dict, dict]:
    """Return (gates, observed).  Missing artifacts fail their gates; nothing raises."""
    backend = criteria["backend"]

    def read(name: str) -> str:
        path = folder / name
        return path.read_text(errors="replace") if path.is_file() else ""

    def load(name: str) -> dict:
        try:
            return json.loads(read(name))
        except ValueError:
            return {}

    smoke, rows = read("julia_smoke.log"), parse_rows(read("nvidia_smi.csv"))
    fingerprint, manifest = load("fingerprint.json"), load("sha256.json")
    julia_uuid = (marker(read("julia_uuid.log"), "GPU_UUID_JULIA") or "").strip()
    first = rows[0] if rows else [""] * 5
    memory = first[3].split()[0] if first[3].split() else ""
    observed = {
        "gpu_name": marker(smoke, "GPU_NAME"),
        "compute_capability": marker(smoke, "GPU_COMPUTE_CAPABILITY"),
        "cuda_jl_version": marker(smoke, "CUDA_JL_VERSION"),
        "waterlily_version": marker(smoke, "WATERLILY_VERSION"),
        "julia_version": marker(smoke, "JULIA_VERSION"),
        "cuda_runtime_version": marker(smoke, "CUDA_RUNTIME_VERSION"),
        "cuda_driver_api_version": marker(smoke, "CUDA_DRIVER_VERSION"),
        "driver_version": first[4],
        "memory_total_mib": int(memory) if memory.isdigit() else None,
        "gpu_total_memory_bytes": marker(smoke, "GPU_TOTAL_MEMORY_BYTES"),
        "gpu_uuid": first[2],
        "julia_gpu_uuid": julia_uuid,
        "inventory_uuids": [row[2] for row in rows],
        "inventory": rows,
        "project_sha256": fingerprint.get("project_sha256"),
        "manifest_sha256": fingerprint.get("manifest_sha256"),
    }
    identity = verify_kaggle_backend_identity(observed, backend)
    bad = {item["field"] for item in identity["mismatches"]}
    gates: dict[str, dict] = {}

    def gate(name: str, ok: bool, detail: str) -> None:
        gates[name] = {"pass": bool(ok), "detail": detail}

    pattern = re.compile(backend["driver_version_pattern"])
    gate("G0_targeted_runtime",
         bool(rows) and len(rows) == len(observed["inventory_uuids"]) >= backend["gpu_count_min"]
         and all(len(row) == 5 and row[1] == backend["all_gpus_must_be_model"]
                 and row[3] == f"{backend['memory_total_mib']} MiB" and pattern.fullmatch(row[4]) for row in rows),
         f"nvidia-smi inventory {rows}")
    for name, key in (("G1_cuda_functional", "CUDA_FUNCTIONAL"), ("G2_cuarray_smoke", "CUARRAY_SMOKE"),
                      ("G3_ka_smoke", "KA_SMOKE"), ("G4_waterlily_cuda_ext", "WATERLILY_CUDA_EXT")):
        gate(name, marker(smoke, key) == "true", f"{key}={marker(smoke, key)}")
    gate("G5_no_solver_step", "NO_SOLVER_STEP" in smoke and "W0B_SMOKE_DONE" in smoke,
         "NO_SOLVER_STEP and W0B_SMOKE_DONE markers")
    gate("G6_identity", not bad - {"gpu_uuid", "gpu_count"}, f"mismatches {identity['mismatches']}")
    gate("G7_uuid_recorded_consistent",
         "gpu_uuid" not in bad and julia_uuid == observed["gpu_uuid"],
         f"nvidia-smi {observed['gpu_uuid']} julia {julia_uuid}")

    def committed(path: str) -> str:
        try:
            blob = subprocess.check_output(["git", "show", f"{fingerprint.get('criteria_commit')}:{path}"],
                                           cwd=ROOT, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, OSError):
            return ""
        return hashlib.sha256(blob).hexdigest()

    criteria_sha = sha256(CRITERIA)
    gate("G8_source_binding",
         fingerprint.get("criteria_sha256") == criteria_sha == CRITERIA.with_suffix(".json.sha256").read_text().strip()
         and committed("docs/evidence/kaggle_w0b_t4_identity_criteria_2026_09.json") == criteria_sha
         and all(sha256(ROOT / e["path"]) == e["sha256"] == committed(e["path"])
                 for e in criteria["source_files"].values())
         and fingerprint.get("julia_archive_sha256") == backend["julia_archive_sha256"]
         and (folder / "git_checkout.log").is_file(),
         f"criteria commit {fingerprint.get('criteria_commit')}")
    names = {path.name for path in folder.iterdir() if path.is_file()} if folder.is_dir() else set()
    gate("G9_artifact_integrity",
         {"DONE", "fingerprint.json", "sha256.json"} <= names and "ERROR.txt" not in names
         and set(manifest) == names - {"sha256.json", "DONE"}
         and all(sha256(folder / n) == h for n, h in manifest.items() if (folder / n).is_file())
         and fingerprint.get("runner_sha256") == sha256(RUNNER),
         f"{len(manifest)} files in manifest")
    return gates, observed


def record(folder: Path, criteria: dict, gates: dict, observed: dict, args) -> dict:
    fingerprint = json.loads((folder / "fingerprint.json").read_text()) if (folder / "fingerprint.json").is_file() else {}
    passed = all(item["pass"] for item in gates.values())
    return {
        "schema_version": 1,
        "kind": "kaggle_w0b_t4_identity_result",
        "attempt": args.attempt,
        "evidence_class": "capability_and_contract",
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "criteria": {"path": CRITERIA.relative_to(ROOT).as_posix(), "sha256": sha256(CRITERIA),
                     "commit": fingerprint.get("criteria_commit")},
        "kernel": {"ref": criteria["kernel"]["id"], "version": args.kernel_version, "private": True,
                   "accelerator": criteria["kernel"]["accelerator"], "cli_version": args.cli_version,
                   "runner_sha256": fingerprint.get("runner_sha256"),
                   "runner_wall_seconds": (fingerprint.get("finished_unix", 0) - fingerprint.get("started_unix", 0)) or None,
                   "host_local_download": args.download.as_posix()},
        "observed": observed,
        "gates": gates,
        "download_integrity": {
            "verified_files": len(json.loads((folder / "sha256.json").read_text())) if (folder / "sha256.json").is_file() else 0,
            "manifest_sha256": sha256(folder / "sha256.json") if (folder / "sha256.json").is_file() else None,
            "fingerprint_sha256": sha256(folder / "fingerprint.json") if (folder / "fingerprint.json").is_file() else None,
        },
        "verdict": {"w0b_kaggle_qualified": passed, "fail_closed": not passed},
        "claims_supported": criteria["claims_supported_on_pass"] if passed else [],
        "claims_not_supported": criteria["claims_not_supported"],
        "flags": {name: False for name in FLAGS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific kaggle kernels output directory")
    parser.add_argument("--kernel-version", type=int)
    parser.add_argument("--cli-version", default="2.2.4")
    parser.add_argument("--attempt", type=int, default=1, help="submission attempt number (result file suffix for >1)")
    parser.add_argument("--record", action="store_true", help="write the immutable result JSON and sidecar")
    args = parser.parse_args()
    if sha256(CRITERIA) != CRITERIA.with_suffix(".json.sha256").read_text().strip():
        raise SystemExit("W0b-Kaggle criteria hash mismatch")
    criteria = json.loads(CRITERIA.read_text())
    folder = args.download / "w0b_kaggle"
    gates, observed = evaluate(folder, criteria)
    passed = all(item["pass"] for item in gates.values())
    print(json.dumps({"pass": passed, "gates": gates}, indent=2, sort_keys=True))
    if args.record:
        if args.kernel_version is None:
            raise SystemExit("--kernel-version is required with --record")
        result = ROOT / "docs/evidence" / (RESULT_STEM + ("" if args.attempt == 1 else f"_attempt{args.attempt}") + ".json")
        sidecar = result.with_suffix(".json.sha256")
        if result.exists() or sidecar.exists():
            raise SystemExit("refusing to overwrite W0b-Kaggle result")
        payload = json.dumps(record(folder, criteria, gates, observed, args), indent=2, sort_keys=True) + "\n"
        result.write_text(payload)
        sidecar.write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
