#!/usr/bin/env python3
"""Register the P22-v2 v17-lattice discrete volume contract (#55).  Solver-free; reads retained evidence only.

Writes docs/evidence/sdf_native_volume_semantics_v2_2026_10.json (+ .sha256 sidecar) once and refuses to overwrite.
It re-measures the retained v17 baseline and LOWDIM-03 parent with the unchanged v1 evaluator and records the
recorded LOWDIM-04A perturbation volumes; it requires the SRCMAP-03a certificate to be intact and CERTIFIED.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import (  # noqa: E402
    SMOOTHED_VOLUME_CONTRACT_SHA256 as V1_CONTRACT_SHA256,
    SMOOTHED_VOLUME_LIMIT_M3 as V1_LIMIT_M3,
    sampled_solid_centers_count,
    sharp_volume_m3,
    smoothed_volume_and_gradient,
)

EV = ROOT / "docs/evidence"
OUT = EV / "sdf_native_volume_semantics_v2_2026_10.json"
INPUTS = EV / "p22_v17_volume_semantics_bridge_2026_10_11/inputs"
S3A = EV / "srcmap03a_sign_invariance_2026_10_13"
PINNED = {  # sha256 of every artifact the registration binds, fixed before the run
    "srcmap03a/classification.json": "97a6ff83d7af82dd6490b3e042ec442e337ccccb0e019c4a6c3bca93cb32b63c",
    "srcmap03a/certificate.json": "d0c89b53a343c245c5a2d81f04ce1988a842d6422dca1ea09b2c4e5aef11bdaa",
    "srcmap03a/SHA256SUMS": "72dddb9856ffb0a800414ebef42510af8469bc6bd4197f806689b6e4a116c18d",
    "srcmap03a/prerun_freeze.json": "cc983e3a4eefa6026e25334fe422907eb23ae11ed3d7b5a2d882c1ec0670af0c",
    "p22_v2_migration_proposal.md": "5c64e43e118aba12bb69996a94b2ed86d2ffe0895570bcf89b8b44bc35b19f85",
    "sdf_native_genesis_v17_2026_09.json": "8335cb7569dae7f75780b133e3f588b802e3b13258f012c391339ffc6a1c10b5",
    "v1_registration.json": "0142ace4de9419dd73cc27e90135ed1fe1f847b074ca2faa37fdb0962505bbce",
}
SRCMAP03A_MERGE_COMMIT = "e1e858772c9938de9771af90c741a741c7e47581"
STL_SHA = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
BASELINE_PHI_C_BYTES_SHA = "f6419547c7b58991462a19f8116b819e7bbe60074fa524c01a51ef41cc0e3b1f"
PARENT_STATE_SHA = "81d24fe4a66704ed469f560b7396b4c0cbf6810ef8082e710f002145ca6e3a65"
PARENT_NPZ_SHA = "0ce3256b0f3e5c919caeb2ac1b36f1a33838f34c767c091cb89bda0234ac750b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond: raise SystemExit(f"integrity failure: {msg}")


def measure(state: SDFDesignState) -> dict:
    v1, v2 = smoothed_volume_and_gradient(state), V2.smoothed_volume_and_gradient_v2(state)
    n = sampled_solid_centers_count(state)
    return {"state_sha256": state.state_sha256, "sampled_solid_centers": n, "sharp_volume_m3": sharp_volume_m3(state), "hard_count_residual_v2": V2.hard_count_residual(state),
            "hard_feasible_v2": V2.hard_feasible(state), "smoothed_volume_m3": v2.smoothed_volume_m3,
            "constraint_residual_v2": v2.constraint_residual, "constraint_residual_v1": v1.constraint_residual,
            "v1_sharp_residual_m3": v1.sharp_volume_residual_m3, "v1_sharp_feasible": v1.sharp_volume_feasible,
            "gradient_sha256_v2": v2.to_dict()["gradient_sha256"], "constraint_gradient_sha256_v2": v2.to_dict()["constraint_gradient_sha256"]}


def main() -> None:
    got = {"srcmap03a/classification.json": sha(S3A / "classification.json"), "srcmap03a/certificate.json": sha(S3A / "certificate.json"),
           "srcmap03a/SHA256SUMS": sha(S3A / "SHA256SUMS"), "srcmap03a/prerun_freeze.json": sha(S3A / "prerun_freeze.json"),
           "p22_v2_migration_proposal.md": sha(EV / "p22_v17_volume_semantics_bridge_2026_10_11/p22_v2_migration_proposal.md"),
           "sdf_native_genesis_v17_2026_09.json": sha(EV / "sdf_native_genesis_v17_2026_09.json"),
           "v1_registration.json": sha(EV / "sdf_native_volume_semantics_v1_2026_09.json")}
    require(all(got[k] == PINNED[k] for k in got), f"pinned artifact hashes differ: {[k for k in got if got[k] != PINNED[k]]}")
    for line in (S3A / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1); require(sha(ROOT / name.strip()) == digest, f"SRCMAP-03a evidence {name}")
    cls = json.loads((S3A / "classification.json").read_text())
    require(cls["terminal_classification"] == "P22_V17_SIGN_INVARIANCE_CERTIFIED" and all(cls["predicates"].values()), "SRCMAP-03a is not CERTIFIED")
    blocker_path = EV / "lowdim04_dual_grid_local_model_2026_10_11/pre_registration_blocker.json"
    blocker_sha = sha(blocker_path); require(blocker_sha == (blocker_path.parent / "pre_registration_blocker.json.sha256").read_text().split()[0], "LOWDIM-04A blocker sidecar")
    require(sha(INPUTS / "v17_baseline.npz") == V2.REFERENCE_NPZ_SHA256 and sha(INPUTS / "lowdim03_parent.npz") == PARENT_NPZ_SHA, "retained state NPZ hashes")
    base, parent = SDFDesignState.load(INPUTS / "v17_baseline.npz"), SDFDesignState.load(INPUTS / "lowdim03_parent.npz")
    require(base.state_sha256 == V2.REFERENCE_STATE_SHA256 and parent.state_sha256 == PARENT_STATE_SHA, "retained state hashes")
    require(hashlib.sha256(np.ascontiguousarray(base.phi, dtype="<f4").tobytes()).hexdigest() == BASELINE_PHI_C_BYTES_SHA, "baseline phi bytes")
    h3 = V2.SPACING_M ** 3
    blocker = json.loads(blocker_path.read_text())
    perturbations = []
    for s in blocker["existing_lowdim_geometry_preflight"]["states"]:
        n = s["sharp_volume_m3"] / h3; require(abs(n - round(n)) < 1e-6, f"{s['state_name']} volume is not an integer count")
        perturbations.append({"state_name": s["state_name"], "state_sha256": s["state_sha256"], "recorded_sharp_volume_m3": s["sharp_volume_m3"], "sampled_solid_centers": int(round(n)),
                              "hard_count_residual_v2": int(round(n)) - V2.MAX_SOLID_CENTERS, "hard_feasible_v2": int(round(n)) <= V2.MAX_SOLID_CENTERS})
    measured = {"baseline": measure(base), "lowdim03_parent": measure(parent), "lowdim04a_perturbations_recorded_not_rederived": perturbations}
    require(measured["baseline"]["sampled_solid_centers"] == V2.MAX_SOLID_CENTERS and V2.VOLUME_LIMIT_M3 == measured["baseline"]["sharp_volume_m3"], "baseline count is not N_max")
    require(V1_CONTRACT_SHA256 == "56825cd50c0916c5659badd21c84bab517ddb370085a92056d40a9028e8a7969", "v1 contract changed")
    reg = {
        "registration_id": V2.REGISTRATION_ID, "kind": "sdf_native_volume_semantics", "schema_version": V2.SCHEMA_VERSION, "evidence_class": "contract", "immutable": True,
        "contract": {
            "scope": "representation-specific discrete constraint on the registered v17 design lattice; not a physical or continuum volume constraint; N <= N_max is not equivalent to V <= 0.12925 m^3 physical",
            "first_sdf_volume_constraint": "N_phi <= N_max (integer comparison)", "sampled_solid_centers_max": V2.MAX_SOLID_CENTERS,
            "volume_limit_m3_derived": V2.VOLUME_LIMIT_M3, "volume_limit_note": "derived as N_max * h**3, never the acceptance quantity",
            "lattice": {"origin_m": list(V2.ORIGIN_M), "spacing_m": V2.SPACING_M, "node_shape": list(V2.NODE_SHAPE), "cell_shape": [n - 1 for n in V2.NODE_SHAPE], "all_cells": int(np.prod([n - 1 for n in V2.NODE_SHAPE]))},
            "volume_definition": "N_phi = |{h-cubes whose ordered Float32 eight-corner mean * Float32(0.125) is < 0}|; exact zero is fluid; masks do not filter samples; every other lattice is refused",
            "evaluator": "cfd_sdf.design.volume_semantics.sampled_solid_centers_count (unchanged v1 evaluator)",
            "smooth_contract": {"id": V2.CONTRACT_ID, "sha256": V2.CONTRACT_SHA256, "v1_contract_sha256": V1_CONTRACT_SHA256,
                                "rule": "v1 primitive unchanged; constraint denominator bound to the derived v2 limit; the smooth value never substitutes for the hard count"},
        },
        "reference": {
            "canonical_reference_artifact": {"state_sha256": V2.REFERENCE_STATE_SHA256, "npz_sha256": V2.REFERENCE_NPZ_SHA256, "phi_float32_c_bytes_sha256": BASELINE_PHI_C_BYTES_SHA,
                                             "path": "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/v17_baseline.npz", "genesis_evidence_sha256": PINNED["sdf_native_genesis_v17_2026_09.json"]},
            "physical_provenance": {"source_stl_sha256": STL_SHA, "role": "provenance of the artifact; STL polyhedral volume is a corroborating observation only, not the limit"},
            "not_the_reference": {"lowdim03_parent_state_sha256": PARENT_STATE_SHA, "reason": "the optimized selected parent must never define the reference"},
        },
        "mapping_reproducibility": {
            "status": "UNRESOLVED", "issues": ["#52 SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC", "#53 SRCMAP02_INCONCLUSIVE (open)"],
            "classification_for_this_contract": "non_blocking",
            "basis": {"result": "P22_V17_SIGN_INVARIANCE_CERTIFIED", "issue": "#54", "integration_merge_commit": SRCMAP03A_MERGE_COMMIT, "artifact_sha256": {k: v for k, v in PINNED.items() if k.startswith("srcmap03a/")}},
            "validity": "only for the immutable reference artifact above on this lattice; regenerating the SDF from the STL, other STLs, lattices or states are outside this contract",
        },
        "supersession": {
            "supersedes": "the precondition 'source-mapping reproducibility must be resolved' in p22_v2_migration_proposal.md (sha256 " + PINNED["p22_v2_migration_proposal.md"] + ")",
            "v1": {"registration_sha256": PINNED["v1_registration.json"], "limit_m3": V1_LIMIT_M3, "sampled_solid_centers": 1009, "status": "unchanged, immutable, historical authority for the v16 lattice (61x33x25)"},
            "decision_record": "docs/evidence/p22_v2_registration_2026_10_13/decision_record.md",
        },
        "measured": measured,
        "zero_slack": "the baseline and the LOWDIM-03 parent sit exactly at N_max: the hard count constraint is active and integer-quantized; a candidate with one more solid centre is infeasible",
        "lowdim04a_blocker_sha256": blocker_sha,
        "flags": {"sdf_gradient_qualified": False, "shape_update_allowed": False, "topology_birth_qualified": False, "waterlily_reverse_cpu_qualified": False, "waterlily_reverse_cuda_qualified": False},
        "selected_delta": None, "solver_started": False, "cfd_runs": 0, "kaggle_submissions": 0,
        "claims_not_supported": ["mapping reproducibility or signer qualification", "physical or continuum volume, grid convergence", "feasibility or optimality of any candidate", "any state on another lattice",
                                 "that LOWDIM-04A may restart (a separate decision and preregistration are required)", "differentiability of the hard count"],
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
    }
    payload = (json.dumps(reg, indent=2, sort_keys=True) + "\n").encode()
    if OUT.exists():
        require(OUT.read_bytes() == payload, "refusing to overwrite the immutable registration")
    else:
        OUT.write_bytes(payload)
    side = OUT.with_suffix(".json.sha256"); side.write_text(hashlib.sha256(payload).hexdigest() + "\n")
    print(OUT.name, hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
