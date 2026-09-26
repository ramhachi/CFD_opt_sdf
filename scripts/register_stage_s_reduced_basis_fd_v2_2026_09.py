#!/usr/bin/env python3
"""Register the profile-aware Stage S reduced-basis FD contract.

This is a solver-free registration step.  It deliberately reuses the exact
16 modes selected by the historical S0/S1 artifact, while rebinding them to
the qualified Stage V v2 profile and working domain.  The historical mode
selection is never rerun or silently replaced here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_reduced_basis import (  # noqa: E402
    EPSILON_LADDER_M,
    K_MODES,
    ModeCandidate,
    canonical_sign,
    mode_sha256,
    sine_mode_vector,
)
from cfd_sdf.stage_s_realized_direction import (  # noqa: E402
    DIRECTION_CP_ABS_TOLERANCE_M,
    EVEN_COMPONENT_ABS_TOLERANCE_M,
)

ASSET_ROOT = ROOT / "docs/evidence/assets/stage_s_reduced_basis_fd_v2"
STAGE_V_SPEC = (
    ROOT
    / "docs/evidence/assets/stage_v_v16_physical_profile_v2/"
    / "project_matched_re_laminar_moving_ground_far_field_v2_expanded_domain_v2.yaml"
)
STAGE_S_SPEC = ASSET_ROOT / "project_matched_re_laminar_moving_ground_far_field_v2_reduced_basis.yaml"
CANDIDATE = ROOT / "docs/evidence/assets/stage_v_v16_physical_profile_v2/v16_candidate_threshold_0p5.iso_surface.stl"
STAGE_V_RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_run_manifest_v1_2026_09.json"
STAGE_V_OUTCOME = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json"
DOMAIN_WITNESS = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json"
OLD_S0_MANIFEST = ROOT / "docs/evidence/stage_s_reduced_basis_fd_manifest_2026_09.json"
OLD_S1_EVIDENCE = ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_2026_09.json"
OLD_CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
OLD_QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
OLD_CP_CATALOG = ROOT / "work/stage_s_work_f_v1/adjoint/base/optimisation/controlPoints/boxcpsBsplines0.csv"
MORPHER = ROOT / "work/stage_s_work_f_v1/tools/moveControlPoints"
BASE_CASE = ROOT / "work/stage_v_v16_physical_profile_expanded_domain_v2_2026_09/case"
MANIFEST = ROOT / "docs/evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
PHYSICAL_PROFILE_SHA = "a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca"
DOCKER_IMAGE_ID = "sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _artifact(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    return {"path": _rel(path), "sha256": _sha256(path)}


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required JSON is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable artifact: {_rel(path)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(payload, encoding="utf-8", newline="\n")
    digest = _sha256(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"immutable sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8", newline="\n")
    return digest


def _docker_id() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("docker is required to bind the registered OpenFOAM image")
    result = subprocess.run(
        [docker, "image", "inspect", OPENFOAM_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit("the registered OpenFOAM image is unavailable")
    return result.stdout.strip()


def _build_stage_s_spec() -> dict[str, Any]:
    stage_v = yaml.safe_load(STAGE_V_SPEC.read_text(encoding="utf-8"))
    stage_s = copy.deepcopy(stage_v)
    stage_s["problem_id"] = "stage_s_reduced_basis_fd_v2"
    stage_s["objectives"] = [
        {
            "id": "maximize_downforce",
            "sense": "maximize",
            "terms": [
                {
                    "coefficient": 1.0,
                    "flow_case_id": "matched_re_laminar",
                    "response_id": "downforce",
                }
            ],
        }
    ]
    return stage_s


def _ensure_stage_s_spec() -> dict[str, Any]:
    expected = _build_stage_s_spec()
    if STAGE_S_SPEC.exists():
        existing = yaml.safe_load(STAGE_S_SPEC.read_text(encoding="utf-8"))
        if existing != expected:
            raise SystemExit("the existing Stage S v2 ProblemSpec differs from deterministic construction")
    else:
        STAGE_S_SPEC.parent.mkdir(parents=True, exist_ok=True)
        STAGE_S_SPEC.write_text(
            yaml.safe_dump(expected, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
            newline="\n",
        )
    stage_v = yaml.safe_load(STAGE_V_SPEC.read_text(encoding="utf-8"))
    diff_keys = sorted(key for key in set(stage_v) | set(expected) if stage_v.get(key) != expected.get(key))
    if diff_keys != ["objectives", "problem_id"]:
        raise SystemExit(f"Stage S v2 differs from Stage V beyond objective identity: {diff_keys}")
    objective = expected["objectives"]
    if len(objective) != 1 or objective[0]["sense"] != "maximize":
        raise SystemExit("Stage S v2 must contain exactly one maximize objective")
    term = objective[0]["terms"]
    if objective[0]["id"] != "maximize_downforce" or term != [
        {"coefficient": 1.0, "flow_case_id": "matched_re_laminar", "response_id": "downforce"}
    ]:
        raise SystemExit("Stage S v2 objective is not the registered downforce contract")
    return {
        "stage_v": {"path": _rel(STAGE_V_SPEC), "sha256": _sha256(STAGE_V_SPEC)},
        "stage_s": {"path": _rel(STAGE_S_SPEC), "sha256": _sha256(STAGE_S_SPEC)},
        "diff_keys": diff_keys,
        "objective_audit": {
            "stage_v_reference": "minimize_drag",
            "stage_s_objective": "maximize_downforce",
            "canonical_J": "J = -CDF",
            "drag": "report_only",
            "only_problem_spec_difference": diff_keys == ["objectives", "problem_id"],
        },
    }


def _mode_binding(old_s1: dict[str, Any], old_qualification: dict[str, Any]) -> dict[str, Any]:
    modes = old_s1.get("modes", [])
    candidate_records = {
        record["candidate"]["name"]: record for record in old_s1.get("candidates", [])
    }
    if len(modes) != K_MODES or old_s1.get("summary", {}).get("all_preflight_pass") is not True:
        raise SystemExit("the historical S1 artifact does not contain the exact passing K=16 basis")
    active_ids = tuple(int(value) for value in old_qualification["derivative_contract"]["active_var_ids"])
    active_ids_sha = hashlib.sha256(
        json.dumps(list(active_ids), separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    records: list[dict[str, Any]] = []
    for entry in modes:
        candidate = entry["candidate"]
        mode_candidate = ModeCandidate(
            a=int(candidate["a"]), b=int(candidate["b"]), c=int(candidate["c"]), axis=str(candidate["axis"])
        )
        if mode_candidate.name != candidate["name"]:
            raise SystemExit(f"historical mode name mismatch: {candidate}")
        historical_candidate = candidate_records.get(mode_candidate.name)
        if historical_candidate is None:
            raise SystemExit(f"historical candidate record is missing: {mode_candidate.name}")
        raw, sign_flipped = canonical_sign(sine_mode_vector(mode_candidate, active_ids=active_ids))
        # Reconstruct with the historical measured efficiency, rather than
        # the rounded reciprocal stored as ``normalization_factor``.  This
        # preserves the exact byte-level vector hash from S1.
        normalized = raw / float(historical_candidate["pass_a"]["normal_efficiency"])
        if mode_sha256(raw) != historical_candidate["raw_vector_sha256"]:
            raise SystemExit(f"historical raw mode hash mismatch: {mode_candidate.name}")
        if mode_sha256(normalized) != entry["vector_sha256"]:
            raise SystemExit(f"historical normalized mode hash mismatch: {mode_candidate.name}")
        if bool(sign_flipped) != bool(historical_candidate.get("sign_flipped", False)):
            raise SystemExit(f"historical mode sign mismatch: {mode_candidate.name}")
        records.append(
            {
                "order": int(entry["order"]),
                "candidate": candidate,
                "raw_vector_sha256": historical_candidate["raw_vector_sha256"],
                "normalized_vector_sha256": entry["vector_sha256"],
                "normalization_factor": float(entry["normalization_factor"]),
                "historical_normal_efficiency": float(entry["normal_efficiency"]),
                "sign_flipped": bool(historical_candidate.get("sign_flipped", False)),
            }
        )
    return {
        "k_modes": K_MODES,
        "selection_policy": "reuse_exact_historical_s1_basis; no response-dependent reselection or reserve substitution",
        "active_var_ids_sha256": active_ids_sha,
        "control_points": [8, 8, 8],
        "catalog": _artifact(OLD_CATALOG),
        "control_point_catalog": _artifact(OLD_CP_CATALOG),
        "modes": records,
    }


def _base_case_binding(stage_v_run: dict[str, Any], stage_v_spec: dict[str, Any]) -> dict[str, Any]:
    metadata_path = BASE_CASE / "case_metadata.json"
    boundary_path = BASE_CASE / "constant/polyMesh/boundary"
    points_path = BASE_CASE / "constant/polyMesh/points"
    faces_path = BASE_CASE / "constant/polyMesh/faces"
    for path in (metadata_path, boundary_path, points_path, faces_path):
        if not path.is_file():
            raise SystemExit(f"v2 body-fitted source case is incomplete: {_rel(path)}")
    metadata = _load(metadata_path)
    canonical_sha = stage_v_run["canonical_inputs"]["problem_spec_sha256"]
    if metadata.get("problem_id") != stage_v_spec["problem_id"]:
        raise SystemExit("v2 source case has the wrong ProblemSpec identity")
    if metadata.get("problem_spec_sha256") != canonical_sha:
        raise SystemExit("v2 source case canonical ProblemSpec hash mismatch")
    if metadata.get("physical_profile", {}).get("sha256") != PHYSICAL_PROFILE_SHA:
        raise SystemExit("v2 source case physical-profile hash mismatch")
    expected_bounds = stage_v_spec["grid"]["domain_bounds_m"]
    actual_bounds = metadata.get("grid", {}).get("bounds")
    if actual_bounds is None or any(
        abs(float(actual_bounds[i][j]) - float(expected_bounds["lower" if i == 0 else "upper"][j])) > 1e-9
        for i in range(2)
        for j in range(3)
    ):
        raise SystemExit("v2 source case domain bounds mismatch")
    if "design_candidate" not in metadata.get("objective", {}).get("force_patches", []):
        raise SystemExit("v2 source case lacks the registered design_candidate force patch")
    boundary_text = boundary_path.read_text(encoding="utf-8", errors="replace")
    required_patches = ("inlet", "outlet", "sideMin", "sideMax", "top", "bottom", "design_candidate")
    if any(patch not in boundary_text for patch in required_patches):
        raise SystemExit("v2 source case boundary contract is incomplete")
    files = [
        metadata_path,
        boundary_path,
        points_path,
        faces_path,
        BASE_CASE / "constant/polyMesh/owner",
        BASE_CASE / "constant/polyMesh/neighbour",
        BASE_CASE / "0/U",
        BASE_CASE / "0/p",
        BASE_CASE / "constant/triSurface/design_candidate.stl",
        BASE_CASE / "constant/triSurface/allowed_design_domain.stl",
    ]
    return {
        "case_dir": _rel(BASE_CASE),
        "problem_id": metadata["problem_id"],
        "problem_spec_sha256": metadata["problem_spec_sha256"],
        "physical_profile_sha256": metadata["physical_profile"]["sha256"],
        "domain_bounds_m": expected_bounds,
        "cell_count": int(metadata.get("mesh", {}).get("cell_count", metadata.get("mesh_refinement", {}).get("cell_count", 0))),
        "source_files": [_artifact(path) for path in files if path.is_file()],
    }


def _documents() -> dict[str, Any]:
    stage_v_run = _load(STAGE_V_RUN_MANIFEST)
    stage_v_outcome = _load(STAGE_V_OUTCOME)
    witness = _load(DOMAIN_WITNESS)
    old_s0 = _load(OLD_S0_MANIFEST)
    old_s1 = _load(OLD_S1_EVIDENCE)
    old_qualification = _load(OLD_QUALIFICATION)
    stage_v_spec = yaml.safe_load(STAGE_V_SPEC.read_text(encoding="utf-8"))
    spec_record = _ensure_stage_s_spec()
    if stage_v_outcome.get("qualified") is not True or stage_v_outcome.get("status") != "pass":
        raise SystemExit("the Stage V v2 physical-profile outcome is not qualified")
    if witness.get("qualified") is not True or witness.get("status") != "pass":
        raise SystemExit("the Stage V same-profile domain witness is not qualified")
    if stage_v_run["canonical_inputs"]["candidate"]["sha256"] != _sha256(CANDIDATE):
        raise SystemExit("candidate hash differs from the Stage V v2 registration")
    if stage_v_run["canonical_inputs"]["physical_profile_sha256"] != PHYSICAL_PROFILE_SHA:
        raise SystemExit("physical-profile hash differs from the Stage V v2 registration")
    if stage_v_run["docker"]["image_id"] != DOCKER_IMAGE_ID or _docker_id() != DOCKER_IMAGE_ID:
        raise SystemExit("Docker image identity differs from the registered Stage V image")
    old_s1_manifest_sha = _sha256(OLD_S0_MANIFEST)
    if old_s1["manifest"]["sha256"] != old_s1_manifest_sha:
        raise SystemExit("historical S1 evidence is not bound to the current old S0 manifest")
    mode_binding = _mode_binding(old_s1, old_qualification)
    base_case = _base_case_binding(stage_v_run, stage_v_spec)
    force_reference = {
        "area_m2": float(stage_v_spec["reference_values"]["area_m2"]),
        "length_m": float(stage_v_spec["reference_values"]["length_m"]),
        "moment_center_m": list(stage_v_spec["reference_values"]["moment_center_m"]),
        "density_kg_m3": 1.0,
        "freestream_speed_mps": 1.0,
        "dynamic_pressure_pa": 0.5,
        "drag_direction": list(stage_v_spec["responses"][0]["direction"]),
        "downforce_direction": list(stage_v_spec["responses"][1]["direction"]),
    }
    return {
        "kind": "stage_s_reduced_basis_fd_v2_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_preflight_pending",
        "architecture": {
            "id": "stage_s_reduced_basis_fd_v2",
            "class": "profile-aware bounded reduced-basis centered-FD architecture",
            "not": ["production optimizer", "qualified Stage S optimizer", "multi-step optimizer"],
        },
        "stage_v_reference": {
            "run_manifest": _artifact(STAGE_V_RUN_MANIFEST),
            "outcome": _artifact(STAGE_V_OUTCOME),
            "domain_convergence_witness": _artifact(DOMAIN_WITNESS),
            "problem_spec": _artifact(STAGE_V_SPEC),
            "canonical_problem_spec_sha256": stage_v_run["canonical_inputs"]["problem_spec_sha256"],
            "physical_profile_sha256": PHYSICAL_PROFILE_SHA,
            "candidate_sha256": _sha256(CANDIDATE),
            "working_domain_bounds_m": stage_v_spec["grid"]["domain_bounds_m"],
            "v3_role": "domain-convergence witness only; v2 is the working domain",
        },
        "stage_s_problem_spec": spec_record,
        "candidate": _artifact(CANDIDATE),
        "physical_profile": {
            "sha256": PHYSICAL_PROFILE_SHA,
            "scope": "registered reduced-laminar moving-ground/freestream profile only",
            "solver_gate_application": "required for every later S2-S5 primal; not evaluated by S0R/S1R",
        },
        "domain": {
            "working_bounds_m": stage_v_spec["grid"]["domain_bounds_m"],
            "working_spec_role": "v2 qualified physical-profile domain",
            "convergence_witness_role": "v3 is retained only as the registered same-profile witness",
        },
        "force_normalization": force_reference,
        "morpher": {
            "utility": _artifact(MORPHER),
            "source_contract": "the historical volumetricBSplines utility is reused unchanged",
            "box_m": _load(OLD_CATALOG)["shared_catalog"]["surface_basis"]["box_m"],
            "control_points": [8, 8, 8],
            "degree": [3, 3, 3],
        },
        "mode_basis": mode_binding,
        "epsilon_ladder_m": list(EPSILON_LADDER_M),
        "geometry_gates": {
            "max_epsilon_m": 1.0e-3,
            "direction_cosine_min": 0.999999,
            "direction_difference_max_m": DIRECTION_CP_ABS_TOLERANCE_M,
            "even_component_max_m": EVEN_COMPONENT_ABS_TOLERANCE_M,
            "minimum_clearance_m": 0.25,
            "minimum_solid_width_m": 0.01,
            "volume_relative_difference_max": 0.02,
            "minimum_width_method": "baseline_v2_revoxelized_width_minus_two_times_max_surface_displacement",
            "required": [
                "morpher_success",
                "fixed_boundary_control_points",
                "inactive_control_points_zero",
                "realized_equals_prescribed",
                "realized_direction",
                "watertight",
                "winding_consistent",
                "positive_volume",
                "no_self_intersection",
                "minimum_solid_width",
                "clearance",
                "checkMesh_profile",
            ],
        },
        "amplitude_calibration": {
            "purpose": "preserve the historical mode direction while mapping unit-normalized coefficients to the v2 morpher",
            "reference_coefficient_m": 1.0e-3,
            "per_mode_calibration_runs": 1,
            "calibrated_max_normal_displacement_target_m": 1.0e-3,
            "mode_selection_unchanged": True,
        },
        "s0r_s1r": {
            "solver_started": False,
            "solver_runs": 0,
            "flow_fields_not_evaluated": True,
            "cases": "all 16 historical modes x both signs at maximum epsilon, unless first hard failure stops the run",
            "failure_policy": "fail_closed; no reserve mode substitution and no post-response reselection",
        },
        "s2_calibration": {
            "max_primals": 24,
            "modes": "lowest, middle, highest frequency of the fixed 16-mode basis",
            "epsilons_m": list(EPSILON_LADDER_M),
            "sides": ["plus", "minus"],
            "primary_epsilon_rule": "largest ladder value passing all preregistered gates for all three calibration modes",
        },
        "s3_gradient": {"max_primals": 32, "reuses_s2": True, "claim_scope": "span(B) only"},
        "s4_holdout": {
            "directions": "two manifest-hash random mode directions plus one downforce projected-gradient direction",
            "primals": 6,
            "relative_error_max": 0.05,
        },
        "s5_one_step": {"max_shape_steps": 1, "requires_complete_s4_pass": True, "shape_update_allowed": False},
        "force_normalization_contract": {
            "canonical_objective": "J = -CDF",
            "response_id": "downforce",
            "sense": "maximize",
            "drag": "report_only",
            "no_constraints": True,
        },
        "flags": {
            "original_adjoint_derivative_qualified": False,
            "reduced_basis_fd_qualified": "pending",
            "shape_update_allowed": False,
            "solver_campaign_started": False,
        },
        "budget": {"s0r_solver_runs": 0, "s1r_flow_runs": 0, "s1r_morpher_runs_max": 48, "s2_primals_max": 24, "s3_primals_max": 32, "s4_primals": 6, "s5_shape_steps_max": 1},
        "base_case": base_case,
        "source_artifacts": {
            "registration_script": _artifact(Path(__file__)),
            "mode_generator": _artifact(ROOT / "src/cfd_sdf/stage_s_reduced_basis.py"),
            "old_s0_manifest": _artifact(OLD_S0_MANIFEST),
            "old_s1_evidence": _artifact(OLD_S1_EVIDENCE),
            "old_catalog": _artifact(OLD_CATALOG),
            "old_qualification": _artifact(OLD_QUALIFICATION),
            "stage_v_physical_profile_module": _artifact(ROOT / "src/cfd_sdf/stage_v_physical_profile.py"),
            "preflight_script": _artifact(ROOT / "scripts/stage_s_reduced_basis_fd_v2_preflight_2026_09.py"),
        },
        "execution": {"solver_started": False, "optimization_campaign_started": False, "preflight_started": False},
        "claims_not_supported": [
            "S0R/S1R is solver-free geometry/morpher/checkMesh evidence only",
            "reduced_basis_fd_qualified remains pending until S2-S4 pass",
            "no absolute or grid-independent downforce claim",
            "no shape update or optimization campaign is authorized",
        ],
    }


def register() -> dict[str, Any]:
    if MANIFEST.exists() or PREFLIGHT.exists():
        raise SystemExit("Stage S reduced-basis v2 manifest or preflight already exists; refuse overwrite")
    for path in (STAGE_V_SPEC, CANDIDATE, STAGE_V_RUN_MANIFEST, STAGE_V_OUTCOME, DOMAIN_WITNESS, OLD_S0_MANIFEST, OLD_S1_EVIDENCE, OLD_CATALOG, OLD_QUALIFICATION, OLD_CP_CATALOG, MORPHER):
        if not path.exists():
            raise SystemExit(f"required Stage S v2 input is missing: {_rel(path)}")
    document = _documents()
    digest = _write_immutable(MANIFEST, document)
    result = {"status": document["status"], "manifest": _rel(MANIFEST), "manifest_sha256": digest, "solver_started": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    document = _load(MANIFEST)
    if document.get("status") != "registered_preflight_pending" or document.get("immutable") is not True:
        raise SystemExit("Stage S v2 contract is not registered_preflight_pending")
    sidecar = MANIFEST.with_suffix(MANIFEST.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="utf-8").strip() != _sha256(MANIFEST):
        raise SystemExit("Stage S v2 manifest sidecar mismatch")
    for name, ref in document["source_artifacts"].items():
        if _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"Stage S v2 registered source changed: {name}")
    expected_spec = _ensure_stage_s_spec()
    if expected_spec["stage_s"]["sha256"] != document["stage_s_problem_spec"]["stage_s"]["sha256"]:
        raise SystemExit("Stage S v2 ProblemSpec changed")
    _documents_without_write = _documents()
    # Compare the deterministic contract while allowing only the source hash
    # of this registration script to be checked through source_artifacts above.
    if _documents_without_write != document:
        raise SystemExit("Stage S v2 contract is not reproducible from its registered inputs")
    result = {"status": "pass", "manifest_sha256": _sha256(MANIFEST), "solver_started": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="register/verify Stage S reduced-basis FD v2 contract")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.register == args.verify:
        parser.error("specify exactly one of --register or --verify")
    if args.register:
        register()
    else:
        verify()


if __name__ == "__main__":
    main()
