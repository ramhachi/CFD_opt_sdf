#!/usr/bin/env python3
"""Write the immutable G2 pre-registration freeze (hashes of everything the T4 run and its analysis depend on)."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08"
SCOPE_RECORD = ROOT / "docs/evidence/fd08_v2_oracle_scope_record_2026_10_08/record.json"
FORMAL = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
INPUTS = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json"
FILES = {
    "script": "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl",
    "runner": "infra/kaggle/kernel_grad_g2_bridge/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_grad_g2_bridge/kernel-metadata.json",
    "host_window": "scripts/grad_g2_window.py",
    "terminal_verifier": "scripts/verify_grad_g2_terminal.py",
    "bridge_analyzer": "scripts/analyze_grad_g2_bridge.py",
    "prerun_note": "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08/prerun_note.md",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "device_grid_sdf": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
}


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def build(source_commit: str) -> dict:
    scope = json.loads(SCOPE_RECORD.read_text())
    criteria = json.loads(FORMAL.read_text())
    inputs = json.loads(INPUTS.read_text())
    meta = json.loads((ROOT / FILES["kernel_metadata"]).read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    return {
        "kind": "grad03_g2_full_window_forward_bridge_prerun_freeze",
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": {FILES["t4_project"]: hashes["t4_project"], FILES["t4_manifest"]: hashes["t4_manifest"], FILES["script"]: hashes["script"]},
        "runtime_pins": {"julia": "1.12.6", "waterlily": "1.8.0", "forwarddiff": "1.4.5", "cuda_jl": "6.3.1"},
        "candidate_c_identity": criteria["candidate_c_identity"]["body_source_sha256"] | {"contract_sha256": criteria["candidate_c_identity"]["contract_sha256"],
                                                                                       "operator_identity": criteria["candidate_c_identity"]["operator_identity"]},
        "canonical_state": criteria["canonical_state"],
        "directions": {"order": list(inputs["directions"]), "fortran_raw_sha256": {k: v["sha256_fortran_raw"] for k, v in inputs["directions"].items()},
                       "registered_c_order_f32_sha256": {k: v["registered_sha256_c_order"] for k, v in inputs["directions"].items()},
                       "baseline_phi": inputs["baseline_phi"], "inputs_manifest_sha256": sha("docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json")},
        "fd08": {"scope_record_sha256": hashlib.sha256(SCOPE_RECORD.read_bytes()).hexdigest(), "formal_criteria_sha256": hashlib.sha256(FORMAL.read_bytes()).hexdigest(),
                 "evidence_pins": scope["evidence"], "response_semantics_sha256": scope["grad01_bridge"]["response_semantics_sha256"],
                 "fd_backend_fingerprint_sha256": scope["grad01_bridge"]["fd_backend_fingerprint_sha256"],
                 "measurement_block": criteria["measurement"], "g_hat_rows": [(r["direction_id"], r["response_id"], r["g_hat_n_per_m"], r["se_g_n_per_m"]) for r in scope["rows"]]},
        "run_inventory": ["plain_float32", "D0_interface_offset_dual1", "D1_filtered_seed11_dual1", "D2_filtered_seed2026_dual1", "P1_upstream_lobe_dual1"],
        "dual_width": 1, "alpha_unit": "metre", "remeasure": "default (as the registered FD-08 job)", "sample_every_steps": 8,
        "gates": {"dual_vs_plain_window_mean_primal_rel": 1e-3, "plain_vs_formal_baseline_v17_rel": 1e-6, "host_vs_kernel_summary_rel": 1e-9},
        "kernel_identity": {"id": meta["id"], "title": meta["title"], "type": meta["kernel_type"], "machine_shape": meta["machine_shape"]},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "fd08_refit": False, "dual4": False},
        "qualification_flags": {k: False for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")},
        "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-commit", required=True)
    args = p.parse_args()
    out = E / "prerun_freeze.json"
    if out.exists():
        sys.exit("refusing to overwrite the freeze")
    data = (json.dumps(build(args.source_commit), sort_keys=True, indent=2) + "\n").encode()
    out.write_bytes(data)
    out.with_name(out.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
