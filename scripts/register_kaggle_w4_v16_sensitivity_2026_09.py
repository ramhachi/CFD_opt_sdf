#!/usr/bin/env python3
"""Freeze a W4 matrix only after binding its exact host-verified W3 PASS."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs/evidence/w4_v16_sensitivity_criteria_draft_2026_09.json"
OUTPUT = ROOT / "docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v16-w4-sensitivity"
KERNEL_IDS = {
    "v16": "ramhachi888/cfd-opt-sdf-w4-v16-sensitivity",
    "v17": "ramhachi888/cfd-opt-sdf-w4-v17-sensitivity",
}
W3_ROUND4_CRITERIA = "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json"
W3_ROUND4_RESULT = "docs/evidence/kaggle_w3_v16_primal_result_round4_2026_09.json"
W3_V17_CRITERIA = "docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json"
W3_V17_RESULT = "docs/evidence/kaggle_w3_v17_primal_result_2026_09.json"
GENESIS_V17 = "docs/evidence/sdf_native_genesis_v17_2026_09.json"
W4_V16_ROUND4_CRITERIA = "docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json"
W4_V16_ROUND4_CRITERIA_SHA = W4_V16_ROUND4_CRITERIA + ".sha256"
W4_V16_ROUND4_RESULT = "docs/evidence/kaggle_w4_v16_sensitivity_result_round4_2026_09.json"
W4_V16_ROUND4_RESULT_SHA = W4_V16_ROUND4_RESULT + ".sha256"
DATASET_IDS = {
    "v16": DATASET_ID,
    "v17": "ramhachi888/cfd-opt-sdf-v17-w4-sensitivity",
}
SOURCE_INPUTS = {
    "kernel_runner": ROOT / "infra/kaggle/kernel_w4/runner.py",
    "kernel_package_runner": ROOT / "infra/kaggle/kernel_w4_v17/runner.py",
    "kernel_metadata": ROOT / "infra/kaggle/kernel_w4_v17/kernel-metadata.json",
    "host_verifier": ROOT / "scripts/verify_kaggle_w4_v16.py",
    "job": ROOT / "scripts/waterlily_w4_v16_sensitivity_job.jl",
    "owner_run_type": ROOT / "julia/CFDSDFWaterLily/src/OwnedV16Run.jl",
    "case_module": ROOT / "julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl",
    "profile_adapter": ROOT / "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl",
    "device_grid": ROOT / "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
    "project": ROOT / "julia/CFDSDFWaterLilyT4/Project.toml",
    "manifest": ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "kaggle_smoke": ROOT / "scripts/w0b_t4_smoke.jl",
    "dataset_preparer": ROOT / "scripts/prepare_kaggle_w4_v16_dataset_2026_09.py",
    "criteria_registrar": Path(__file__).resolve(),
    "contract_tests": ROOT / "tests/test_kaggle_w4.py",
    "criteria_draft": DRAFT,
    "historical_v16_w4_criteria": ROOT / W4_V16_ROUND4_CRITERIA,
    "historical_v16_w4_criteria_sidecar": ROOT / W4_V16_ROUND4_CRITERIA_SHA,
    "historical_v16_w4_result": ROOT / W4_V16_ROUND4_RESULT,
    "historical_v16_w4_result_sidecar": ROOT / W4_V16_ROUND4_RESULT_SHA,
}
BACKEND_KEYS = (
    "accelerator", "machine_shape", "gpu_count", "gpu_name", "driver_version",
    "cuda_visible_devices", "julia_archive_sha256", "compute_capability",
    "cuda_driver_api_version", "cuda_runtime_version", "cuda_jl_version",
    "julia_version", "julia_threads", "waterlily_version", "waterlily_backend",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def criteria_output_path(criteria_round: int, state_label: str = "v16") -> Path:
    if criteria_round < 1:
        raise ValueError("W4 criteria round must be positive")
    if state_label == "v16" and criteria_round == 1:
        return OUTPUT
    suffix = "" if criteria_round == 1 else f"_round{criteria_round}"
    return OUTPUT.with_name(f"kaggle_w4_{state_label}_sensitivity_criteria_2026_09{suffix}.json")


def input_entry(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path), "location": "source_repo"}


def load_w3_pass(criteria_path: Path, result_path: Path) -> tuple[dict, dict, str, str]:
    criteria_path = Path(criteria_path)
    result_path = Path(result_path)
    criteria_sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not criteria_sidecar.is_file():
        raise ValueError("immutable W3 criteria and SHA sidecar are required")
    criteria_sha = sha256(criteria_path)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise ValueError("W3 criteria sidecar SHA mismatch")
    w3_criteria = json.loads(criteria_path.read_text())
    if (w3_criteria.get("immutable") is not True
            or w3_criteria.get("registered_before_computation") is not True
            or w3_criteria.get("source_commit") != w3_criteria.get("registered_source_commit")):
        raise ValueError("W3 criteria are not immutable preregistration")
    result_sha = sha256(result_path)
    result = json.loads(result_path.read_text())
    if (result.get("verdict") != "PASS"
            or result.get("host_verification_passed") is not True
            or not result.get("gates")
            or not all(result["gates"].values())):
        raise ValueError("W3 result is not an exact host-verified PASS")
    criteria_rel = criteria_path.resolve().relative_to(ROOT).as_posix()
    result_rel = result_path.resolve().relative_to(ROOT).as_posix()
    w3_label = w3_criteria.get("geometry", {}).get("state_label", "v16")
    expected_w3_paths = {
        "v16": (W3_ROUND4_CRITERIA, W3_ROUND4_RESULT),
        "v17": (W3_V17_CRITERIA, W3_V17_RESULT),
    }
    if expected_w3_paths.get(w3_label) != (criteria_rel, result_rel):
        raise ValueError("W4 registration requires the exact registered W3 PASS for the same canonical state")
    if (result.get("verdict") != "PASS"
            or result.get("host_verification_passed") is not True
            or result.get("criteria_path") != criteria_rel
            or result.get("criteria_sha256") != criteria_sha
            or not isinstance(result.get("kernel_version"), int)
            or result["kernel_version"] < 1
            or result.get("source_commit") != w3_criteria["source_commit"]
            or result.get("host_verifier_sha256")
            != w3_criteria["inputs"]["host_verifier"]["sha256"]
            or not result.get("gates")
            or not all(result["gates"].values())):
        raise ValueError("W3 result is not an exact host-verified PASS")
    backend = result.get("backend_identity")
    if not isinstance(backend, dict) or set(backend) != set(BACKEND_KEYS):
        raise ValueError("W3 PASS evidence lacks the complete observed backend identity")
    if (backend["accelerator"] != "NvidiaTeslaT4"
            or backend["machine_shape"] != "NvidiaTeslaT4"
            or backend["gpu_count"] != 2
            or backend["gpu_name"] != "Tesla T4"
            or backend["cuda_visible_devices"] != "0"
            or backend["julia_version"] != "1.12.6"
            or backend["julia_threads"] != 1
            or backend["waterlily_version"] != "1.8.0"
            or not backend["waterlily_backend"]
            or any(not backend[key] for key in BACKEND_KEYS)):
        raise ValueError("observed W3 backend is outside the registered W4 T4 cohort")
    if (result.get("selected_gpu_uuid") is None
            or not str(result["selected_gpu_uuid"]).startswith("GPU-")):
        raise ValueError("W3 PASS evidence lacks its selected GPU UUID")
    return w3_criteria, result, criteria_sha, result_sha


def build_criteria(source_commit: str, criteria_round: int,
                   w3_criteria_path: Path, w3_result_path: Path) -> dict:
    w3_criteria, w3_result, w3_criteria_sha, w3_result_sha = load_w3_pass(
        w3_criteria_path, w3_result_path)
    draft = json.loads(DRAFT.read_text())
    if draft.get("immutable") is not False or draft.get("registered_before_computation") is not False:
        raise ValueError("W4 source draft is no longer a mutable, unregistered draft")
    w3_geometry = w3_criteria["geometry"]
    state_label = w3_geometry.get("state_label", "v16")
    if state_label not in DATASET_IDS:
        raise ValueError(f"unsupported canonical W4 state label: {state_label}")
    expected_geometry = {
        "canonical_state_sha256": w3_geometry["state_sha256"],
        "canonical_state_npz_sha256": w3_criteria["inputs"]["canonical_state_npz"]["sha256"],
        "canonical_phi_c_order_sha256": w3_geometry["phi_c_order_sha256"],
        "canonical_phi_fortran_sha256": w3_geometry["phi_fortran_sha256"],
        "point_shape": w3_geometry["point_shape"],
        "cell_shape": w3_geometry["cell_shape"],
        "source_surface_sha256": w3_geometry["source_surface_sha256"],
        "canonical_sdf_origin_m": w3_geometry["canonical_sdf_origin_m"],
        "baseline_flow_origin_m": w3_criteria["profile_adapter"]["flow_origin_m"],
        "baseline_physical_box_m": w3_criteria["profile_adapter"]["physical_box_m"],
        "design_lattice_spacing_m": w3_geometry.get("spacing_m", draft["geometry"]["design_lattice_spacing_m"]),
        "phi_expected_margin_m": w3_geometry["expected_margin_m"],
        "phi_margin_gate_m": w3_geometry["margin_gate_m"],
        "phi_margin_tolerance_m": w3_geometry["margin_tolerance_m"],
    }
    for key in ("baseline_flow_origin_m", "baseline_physical_box_m", "reynolds",
                "density_kg_m3", "dynamic_viscosity_pa_s", "freestream_mps",
                "reference_length_m", "reference_area_m2"):
        if draft["geometry"].get(key) != expected_geometry.get(key, draft["geometry"].get(key)):
            raise ValueError(f"W4 invariant profile geometry differs from W3: {key}")
    draft["geometry"].update(expected_geometry)
    draft["geometry"]["state_label"] = state_label
    draft["geometry"]["design_lattice_is_resampled"] = False
    draft["geometry"]["flow_grid_is_separate_from_design_lattice"] = True

    source_inputs = dict(SOURCE_INPUTS)
    if state_label != "v17":
        for name in ("kernel_package_runner", "kernel_metadata", "historical_v16_w4_criteria",
                     "historical_v16_w4_criteria_sidecar", "historical_v16_w4_result",
                     "historical_v16_w4_result_sidecar"):
            source_inputs.pop(name)
    inputs = {name: input_entry(path) for name, path in source_inputs.items()}
    w3_criteria_path = Path(w3_criteria_path).resolve()
    w3_result_path = Path(w3_result_path).resolve()
    w3_host_verifier = ROOT / w3_criteria["inputs"]["host_verifier"]["path"]
    inputs["w3_host_verifier"] = input_entry(w3_host_verifier)
    inputs["w3_criteria"] = input_entry(w3_criteria_path)
    inputs["w3_result_evidence"] = input_entry(w3_result_path)
    if state_label == "v17":
        genesis_path = ROOT / GENESIS_V17
        inputs["genesis_evidence"] = input_entry(genesis_path)
        if sha256(genesis_path) != w3_criteria["inputs"]["genesis_evidence"]["sha256"]:
            raise ValueError("W3 v17 criteria do not bind the checked-in v17 genesis evidence")
    inputs["canonical_state_npz"] = {
        "path": "sdf_design_state.npz",
        "sha256": w3_criteria["inputs"]["canonical_state_npz"]["sha256"],
        "location": "kaggle_dataset",
    }
    inputs["canonical_phi_fortran_raw"] = {
        "path": f"canonical_{state_label}_phi_f4_fortran.raw",
        "sha256": w3_criteria["geometry"]["phi_fortran_sha256"],
        "location": "kaggle_dataset",
        "dtype": "float32_little_endian",
        "order": "Fortran",
        "shape": w3_geometry["point_shape"],
    }

    profile = draft["profile_semantics"]
    profile["force_integration_body"] = (
        f"canonical {state_label} candidate GridSDF only; exclude auxiliary moving-ground half-space")
    response_rule = draft["w3_flow16_comparison"]["interpretation_rule"]
    draft["w3_flow16_comparison"]["interpretation_rule"] = response_rule.replace(
        "W3 round-4", f"W3 {state_label}")
    stationarity = draft["measurement"]["stationarity"]
    stationarity["precedent_criteria_path"] = w3_criteria_path.relative_to(ROOT).as_posix()
    stationarity["precedent_criteria_sha256"] = w3_criteria_sha

    final = {key: value for key, value in draft.items()
             if key not in {"registration_todo", "criteria_id", "prerequisites"}}
    final.update({
        "schema_version": 1,
        "kind": ("waterlily_w4_v16_grid_domain_sensitivity_criteria" if state_label == "v16"
                 else "waterlily_w4_canonical_grid_domain_sensitivity_criteria"),
        "criteria_id": (f"waterlily_w4_{state_label}_grid_domain_sensitivity_2026_09"
                        if criteria_round == 1 else
                        f"waterlily_w4_{state_label}_grid_domain_sensitivity_2026_09_round{criteria_round}"),
        "criteria_round": criteria_round,
        "status": "registered_not_run",
        "immutable": True,
        "registered_before_computation": True,
        "registered_source_commit": source_commit,
        "source_commit": source_commit,
        "input_dataset_id": DATASET_IDS[state_label],
        "kernel_id": KERNEL_IDS[state_label],
        "inputs": inputs,
        "backend": w3_result["backend_identity"],
        "prerequisites": {
            "w3_result_must_pass_host_verification": True,
            "w3_baseline_reused": False,
            "all_four_cases_reexecuted": True,
            "w3_flow16_comparison_required": True,
            "w3_flow16_numerical_repeatability_gate_registered": False,
            "canonical_state_identity": {
                "state_label": state_label,
                "state_sha256": expected_geometry["canonical_state_sha256"],
                "state_npz_sha256": expected_geometry["canonical_state_npz_sha256"],
                "phi_c_order_sha256": expected_geometry["canonical_phi_c_order_sha256"],
                "phi_fortran_sha256": expected_geometry["canonical_phi_fortran_sha256"],
                "point_shape": expected_geometry["point_shape"],
                "cell_shape": expected_geometry["cell_shape"],
                "design_lattice_spacing_m": expected_geometry["design_lattice_spacing_m"],
                "canonical_sdf_origin_m": expected_geometry["canonical_sdf_origin_m"],
                "source_surface_sha256": expected_geometry["source_surface_sha256"],
            },
            "w3_result_evidence": {
                "path": w3_result_path.relative_to(ROOT).as_posix(),
                "sha256": w3_result_sha,
                "criteria_path": w3_criteria_path.relative_to(ROOT).as_posix(),
                "criteria_sha256": w3_criteria_sha,
                "kernel_version": w3_result["kernel_version"],
                "host_verified": True,
                "host_verifier_sha256": w3_result["host_verifier_sha256"],
                "backend_identity": w3_result["backend_identity"],
            },
        },
    })
    final["evidence_scope"]["claim_scope"] = (
        f"the registered canonical {state_label} SDF finite-box resolution/domain sensitivity matrix "
        "completed and satisfied the registered integrity and stationarity contract")
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--w3-criteria", type=Path, required=True)
    parser.add_argument("--w3-result", type=Path, required=True)
    parser.add_argument("--state-label", choices=tuple(DATASET_IDS), default="v16")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = criteria_output_path(args.round, args.state_label)
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if args.check:
        if not output.is_file() or not sidecar.is_file():
            raise SystemExit("immutable W4 criteria or sidecar is missing")
        digest = sha256(output)
        if sidecar.read_text().strip() != digest:
            raise SystemExit("W4 criteria SHA sidecar mismatch")
        criteria = json.loads(output.read_text())
        if (criteria.get("immutable") is not True
                or criteria.get("registered_before_computation") is not True
                or criteria.get("criteria_round") != args.round
                or criteria.get("geometry", {}).get("state_label", "v16") != args.state_label):
            raise SystemExit("W4 criteria are not the requested immutable round")
        print(digest)
        return 0
    if output.exists() or sidecar.exists():
        raise SystemExit("W4 criteria already exists; immutable registration will not be overwritten")
    branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
    if branch != "codex/kaggle-batch-migration":
        raise SystemExit(f"unexpected W4 registration branch: {branch}")
    status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip()
    if status:
        raise SystemExit("commit and push all W4 source files before immutable registration")
    source_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    criteria = build_criteria(source_commit, args.round, args.w3_criteria, args.w3_result)
    if criteria["geometry"].get("state_label", "v16") != args.state_label:
        raise SystemExit("requested W4 state label differs from the exact W3 PASS")
    output.write_text(json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = sha256(output)
    sidecar.write_text(digest + "\n")
    print(json.dumps({"criteria_path": output.relative_to(ROOT).as_posix(),
                      "criteria_sha256": digest,
                      "source_commit": source_commit}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
