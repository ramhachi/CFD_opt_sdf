"""Create the immutable pre-run identity for the FD-07 replacement diagnostic."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "exp/issue-37-continuous-sign-consistency"
BASE_HEAD = "ecaa1572734596130ffefdd0d7b0ab3c2af67c15"
EVIDENCE = Path("docs/evidence/sdf_native_fd07_continuous_replacement_attempt02_2026_10")
CAUSAL = Path("docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10")
FAILED_ATTEMPT = Path("docs/evidence/sdf_native_fd07_continuous_replacement_2026_10")
BODY_JL = Path("/Users/sota/.julia/packages/WaterLily/yOkji/src/Body.jl")
BODY_SHA256 = "aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee"
WATERLILY_TAG_COMMIT = "9f0f46fafb758f9f719dcc63d69ee6471358d8f8"
MAX_REALIZED_NODE_SHIFT_M = 4.76837158203125e-7
FLOW_SPACING_M = 1.0 / 30.0
DELTA = 8.0 * MAX_REALIZED_NODE_SHIFT_M / FLOW_SPACING_M

SOURCE_FILES = (
    "docs/issues/37_fd07_continuous_replacement_design.md",
    "scripts/sdf_native_fd07_continuous_sign_operators.jl",
    "scripts/sdf_native_fd07_continuous_replacement_fixtures.jl",
    "scripts/sdf_native_fd07_continuous_replacement_probe.jl",
    "scripts/sdf_native_fd07_continuous_replacement_analysis.py",
    "scripts/sdf_native_fd07_continuous_replacement_prepare.py",
    "tests/test_sdf_native_fd07_continuous_replacement.py",
    "julia/CFDSDFWaterLily/Project.toml",
    "julia/CFDSDFWaterLily/Manifest.toml",
    "julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl",
    "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl",
    "julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl",
    "docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10/plan.json",
    "docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10/summary.json",
    "docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10/initialization.csv",
    "docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10/realized_noise.csv",
)


def sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def prepare() -> dict:
    outdir = ROOT / EVIDENCE
    if outdir.exists():
        raise FileExistsError(f"refusing to overwrite preregistered evidence: {outdir}")
    branch, head = git("branch", "--show-current"), git("rev-parse", "HEAD")
    if branch != BRANCH or head != BASE_HEAD:
        raise ValueError(f"expected {BRANCH}@{BASE_HEAD}, found {branch}@{head}")
    dirty_paths = {
        line[3:]
        for line in git("status", "--porcelain", "--untracked-files=all").splitlines()
        if line
    }
    failure_record = ROOT / FAILED_ATTEMPT / "stage3_attempt_failure.txt"
    if not failure_record.is_file() or "recovery=new_source_hash_and_new_preregistered_attempt_required" not in failure_record.read_text():
        raise ValueError("the preserved failed attempt must be explicitly recorded before retry registration")
    allowed_existing_evidence = {
        name for name in dirty_paths if name.startswith(FAILED_ATTEMPT.as_posix() + "/")
    }
    unexpected = dirty_paths - set(SOURCE_FILES) - allowed_existing_evidence
    if unexpected:
        unexpected = sorted(unexpected)
        raise ValueError(f"unregistered working-tree changes are present: {unexpected}")
    if sha(BODY_JL) != BODY_SHA256:
        raise ValueError("pinned WaterLily Body.jl hash mismatch")

    previous = json.loads((ROOT / CAUSAL / "plan.json").read_text())
    cases = {}
    for case_id, old in previous["input_cases"].items():
        path = CAUSAL / old["phi_file"]
        actual = sha(ROOT / path)
        if actual != old["phi_sha256"]:
            raise ValueError(f"prior phi input hash mismatch: {path}")
        cases[case_id] = {"repository_path": path.as_posix(), "sha256": actual}

    source_hashes = {name: sha(ROOT / name) for name in SOURCE_FILES}
    source_hashes["pinned_WaterLily_Body.jl"] = sha(BODY_JL)
    source_payload = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(source_hashes.items())
    ).encode()
    input_payload = "".join(
        f"{item['sha256']}  {item['repository_path']}\n"
        for _, item in sorted(cases.items())
    ).encode()

    source_manifest_sha = sha_bytes(source_payload)
    input_manifest_sha = sha_bytes(input_payload)
    plan = {
        "kind": "fd07_continuous_sign_consistency_replacement_preregistration",
        "issue": "#37",
        "evidence_class": "bounded_diagnostic_only",
        "attempt": 2,
        "supersedes_incomplete_attempt": {
            "path": FAILED_ATTEMPT.as_posix(),
            "plan_sha256": "c3959a55122c87386d0eb061f22f1dea3538697923bf1c1198dc9b5a6b8bb366",
            "reason": "first short-flow run completed but its execution recorder hit a Julia local-scope error",
        },
        "created_before_stage1_coefficient_matrix_and_stage2_geometry_matrix": True,
        "source": {
            "base_head": head,
            "branch": branch,
            "pinned_waterlily_version": "1.8.0",
            "pinned_waterlily_tag_commit": WATERLILY_TAG_COMMIT,
            "waterlily_body_jl_path": str(BODY_JL),
            "waterlily_body_jl_sha256": BODY_SHA256,
            "repository_source_sha256": source_hashes,
            "repository_sources_manifest_sha256": source_manifest_sha,
        },
        "input_identity": {
            "canonical_state": previous["canonical_state"],
            "flow_case": "flow_24",
            "phi_cases": cases,
            "input_files_manifest_sha256": input_manifest_sha,
            "reused_from_immutable_evidence": CAUSAL.as_posix(),
        },
        "parameters": {
            "flow_spacing_m": FLOW_SPACING_M,
            "half_cell_threshold_solver_units": 0.5,
            "largest_prior_realized_float32_node_shift_m": MAX_REALIZED_NODE_SHIFT_M,
            "one_input_shift_bound_solver_units": MAX_REALIZED_NODE_SHIFT_M / FLOW_SPACING_M,
            "transition_delta_solver_units": DELTA,
            "transition_delta_m": DELTA * FLOW_SPACING_M,
            "transition_derivation": "8 * max realized Float32 nodal shift at 1e-7 m / flow_24 spacing",
            "activation": "C1 cubic smoothstep 3q^2-2q^3, clamped to [0,1]",
            "center_sign": "2*smoothstep((d_center+delta)/(2*delta))-1",
            "normal_floor": 0.25,
            "bdim_width_solver_units": 1.0,
        },
        "candidates": {
            "controls": ["UPSTREAM", "NO_SIGN_CORRECTION"],
            "A_THRESHOLD": {
                "distance_blend": "w=smoothstep((abs(d_face)-(0.5-delta))/(2*delta)); d_eff=(1-w)d_face+w*copysign(abs(d_face),d_center)",
                "center_sign_is_hard": True,
            },
            "B_CENTER_SIGN": {
                "distance_blend": "same centered threshold weight as A; corrected distance is abs(d_face)*smooth_sign(d_center,delta)",
            },
            "C_MOMENT_BLEND": {
                "weight": "alpha=smoothstep((abs(d_face)-0.5)/delta)*smoothstep(-sign(d_face)*d_center/delta)",
                "mu0": "mu0_raw + alpha*(mu0_upstream_corrected-mu0_raw)",
                "mu1": "unchanged; pinned mu1(d) is even and upstream sign flip preserves abs(d)",
            },
        },
        "stage1": {
            "solver_steps": 0,
            "modes": ["UPSTREAM", "NO_SIGN_CORRECTION", "A_THRESHOLD", "B_CENTER_SIGN", "C_MOMENT_BLEND"],
            "comparisons": ["baseline", "seeds 1/11/2026", "paired +/-1e-8 m and +/-1e-7 m"],
            "record": ["branch disagreement", "mu0/mu1 coefficient deltas", "odd/even", "10x ratio", "nonfinite", "support", "distance and input hashes", "changed face coordinates"],
        },
        "stage2": {
            "solver_steps": 0,
            "fixtures": ["plane center-aligned", "plane face-aligned", "plane face-offset 1e-4 solver units", "plane near-center offset 1e-4 solver units", "sphere", "one-cell plate", "two-cell plate", "synthetic sign-disagreeing center/face pair"],
            "tests": ["inside/outside sign counts", "legal half-cell crossing preservation", "moment continuity under center and face translation", "reflection symmetry", "monotonicity", "thin-body face-moment preservation"],
        },
        "stage3": {
            "allowed_after_stage1_and_stage2": ["at most two candidates passing the fixed semantic criteria"],
            "solver_setup": previous["solver"],
            "run_count_per_arm": 13,
            "arms": ["UPSTREAM", "NO_SIGN_CORRECTION", "selected candidate(s)"],
            "analysis_window_u_l": [2.0, 3.0],
            "force_conversion_n_per_solver_force": 1.0 / 900.0,
            "no_formal_fd_threshold": True,
        },
        "fixed_rejection_conditions": [
            "O(1) coefficient jump remains in the registered perturbation band",
            "response does not change monotonically from 1e-8 m to 1e-7 m",
            "candidate changes an exact analytic SDF legal half-cell sign crossing or the one/two-cell plate moments",
            "moving-ground-only geometry, velocity, or coefficient initialization changes",
            "wide baseline coefficient-map change, NaN/Inf, or broad support-membership change",
            "no isolated continuous candidate has coherent lower short-window force irregularity while retaining semantic checks",
        ],
        "stop_before": ["production adoption", "formal FD", "FD-08", "W3/W4 requalification", "Kaggle", "v18", "gradient", "optimizer"],
        "runtime_preparation": {
            "python": sys.version,
            "julia": subprocess.check_output(["julia", "--version"], text=True).strip(),
            "platform": platform.platform(),
        },
    }
    outdir.mkdir(parents=True)
    write_exclusive(outdir / "repository_sources.sha256", source_payload)
    write_exclusive(outdir / "input_files.sha256", input_payload)
    payload = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
    write_exclusive(outdir / "plan.json", payload)
    plan_sha = sha(outdir / "plan.json")
    write_exclusive(outdir / "plan.sha256", f"{plan_sha}  plan.json\n".encode())
    return {"plan_sha256": plan_sha, "input_files": len(cases), "source_files": len(source_hashes)}


if __name__ == "__main__":
    print(json.dumps(prepare(), sort_keys=True))
