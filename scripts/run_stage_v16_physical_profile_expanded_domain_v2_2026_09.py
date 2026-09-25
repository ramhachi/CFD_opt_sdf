#!/usr/bin/env python3
"""Run the single registered same-profile expanded-domain correction."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1, qualify_stage_v_case, write_stage_v_qualification
from cfd_sdf.execution import run_openfoam_case
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.sdf import build_fields
from cfd_sdf.stage_v_domain_preflight import STAGE_V_CLEARANCE_PROFILE_V1, evaluate_stage_v_domain_preflight, write_stage_v_domain_preflight_report
from cfd_sdf.stage_v_physical_profile import STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1, evaluate_boundary_metrics, evaluate_solver_residual_gate
import register_stage_v16_physical_profile_expanded_domain_v2_2026_09 as registration  # noqa: E402


MANIFEST = registration.MANIFEST
RUN_MANIFEST = registration.RUN_MANIFEST
EXPANDED_SPEC = registration.EXPANDED_SPEC
CANDIDATE = registration.CANDIDATE
CASE_DIR = registration.CASE_DIR
OUTCOME = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json"
OPENFOAM_IMAGE = registration.OPENFOAM_IMAGE


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _docker_image_id() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("docker is required for the controlled run")
    completed = subprocess.run(
        [docker, "image", "inspect", OPENFOAM_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit("registered Docker image is unavailable")
    return completed.stdout.strip()


def _write_outcome(document: dict[str, Any]) -> str:
    if OUTCOME.exists():
        raise SystemExit(f"expanded-domain outcome already exists; refuse overwrite: {_rel(OUTCOME)}")
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    OUTCOME.parent.mkdir(parents=True, exist_ok=True)
    OUTCOME.write_text(payload, encoding="utf-8", newline="\n")
    digest = _sha256(OUTCOME)
    OUTCOME.with_suffix(OUTCOME.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8", newline="\n")
    return digest


def _verify_registration(run_manifest: dict[str, Any]) -> None:
    registration.verify()
    if run_manifest["execution"]["new_run_count"] != 0 or run_manifest["execution"]["solver_started"]:
        raise SystemExit("expanded-domain run manifest already records an execution")
    if _docker_image_id() != run_manifest["docker"]["image_id"]:
        raise SystemExit("Docker image identity differs from the expanded-domain registration")
    if OUTCOME.exists():
        raise SystemExit("expanded-domain outcome already exists; refusing a second run")
    if CASE_DIR.exists():
        raise SystemExit(f"expanded-domain case already exists; refusing overwrite: {_rel(CASE_DIR)}")


def _identity_gate(case_dir: Path, run_manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = _load(case_dir / "case_metadata.json")
    expected = run_manifest["canonical_inputs"]
    checks = {
        "candidate_sha256": _sha256(case_dir / "constant/triSurface/design_candidate.stl") == expected["candidate"]["sha256"],
        "problem_spec_sha256": metadata.get("problem_spec_sha256") == expected["problem_spec_sha256"],
        "physical_profile_sha256": metadata.get("physical_profile", {}).get("sha256") == expected["physical_profile_sha256"],
        "expanded_problem_id": metadata.get("problem_id") == "stage_sv_v2_expanded_domain_v2",
        "profile_spec_source": metadata.get("source_project") == str(EXPANDED_SPEC.resolve()),
        "candidate_boundary_semantics": "design_candidate" in metadata.get("objective", {}).get("force_patches", []),
    }
    boundary_text = (case_dir / "system/blockMeshDict").read_text(encoding="utf-8")
    u_text = (case_dir / "0/U").read_text(encoding="utf-8")
    p_text = (case_dir / "0/p").read_text(encoding="utf-8")
    checks.update(
        {
            "outer_mesh_patches": all(f"{patch} {{ type patch;" in boundary_text for patch in ("inlet", "outlet", "sideMin", "sideMax", "top")),
            "moving_ground_mesh_wall": "bottom { type wall;" in boundary_text,
            "outer_velocity_freestream": all(f"{patch} {{ type freestreamVelocity;" in u_text for patch in ("inlet", "outlet", "sideMin", "sideMax", "top")),
            "moving_ground_velocity": "bottom { type translatingWallVelocity; U (1 0 0); value uniform (1 0 0);" in u_text,
            "outer_pressure_freestream": all(f"{patch} {{ type freestreamPressure;" in p_text for patch in ("inlet", "outlet", "sideMin", "sideMax", "top")),
        }
    )
    reasons = [name for name, passed in checks.items() if not passed]
    return {"status": "pass" if not reasons else "fail", "qualified": not reasons, "checks": checks, "reasons": reasons}


def _missing_stage_qualification(case_dir: Path, reason: str) -> dict[str, Any]:
    return {
        "case_dir": str(case_dir),
        "profile_id": STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"],
        "qualified": False,
        "reasons": [reason],
        "check_mesh": {"qualified": False, "reasons": [reason]},
        "solver": {"qualified": False, "reasons": [reason], "final_residuals": {}},
        "force_stationarity": {"qualified": False, "reasons": [reason]},
    }


def run(timeout_seconds: int) -> dict[str, Any]:
    run_manifest = _load(RUN_MANIFEST)
    _verify_registration(run_manifest)
    spec = load_problem_spec(EXPANDED_SPEC)
    CASE_DIR.mkdir(parents=True, exist_ok=False)
    preflight = evaluate_stage_v_domain_preflight(spec, CANDIDATE.resolve(), float(spec.grid.voxel_size_m), profile=STAGE_V_CLEARANCE_PROFILE_V1)
    preflight_path = write_stage_v_domain_preflight_report(CASE_DIR, preflight)
    if not preflight.qualified:
        outcome = {
            "kind": "stage_v_v16_physical_profile_expanded_domain",
            "schema_version": 1,
            "evidence_class": "qualification_result",
            "status": "no_launch_clearance_failed",
            "qualified": False,
            "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
            "preflight": {"path": _rel(preflight_path), "sha256": _sha256(preflight_path)},
            "gates": {"candidate_clearance": {"status": "fail", "reasons": list(preflight.reasons)}},
            "claims_not_supported": run_manifest["claims_not_supported"],
        }
        digest = _write_outcome(outcome)
        print(json.dumps({"status": outcome["status"], "outcome_sha256": digest}, ensure_ascii=False, sort_keys=True))
        return outcome

    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE, voxel_size_m=float(spec.grid.voxel_size_m))
    generate_openfoam_case(config, build_fields(config), CASE_DIR)
    identity = _identity_gate(CASE_DIR, run_manifest)
    (CASE_DIR / "qualification_registration.json").write_text(
        json.dumps(
            {
                "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
                "manifest": {"path": _rel(MANIFEST), "sha256": _sha256(MANIFEST)},
                "docker_image": run_manifest["docker"],
                "identity_gate": identity,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    run_result = run_openfoam_case(CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout_seconds, docker_image=OPENFOAM_IMAGE)
    solver_log = CASE_DIR / "log.simpleFoam"
    mesh_log = CASE_DIR / "log.checkMesh"
    if solver_log.is_file() and mesh_log.is_file():
        qualification_path = write_stage_v_qualification(CASE_DIR, STAGE_V_QUALIFICATION_PROFILE_V1)
        qualification = qualify_stage_v_case(CASE_DIR, STAGE_V_QUALIFICATION_PROFILE_V1).to_dict()
    else:
        qualification_path = None
        qualification = _missing_stage_qualification(CASE_DIR, "mesh_or_solver_log_missing")
    residual_gate = evaluate_solver_residual_gate(qualification)
    boundary_metrics = evaluate_boundary_metrics(CASE_DIR, profile=STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1)
    physical_gates = boundary_metrics.get("gates", {})
    gates = {
        "identity": identity,
        "candidate_clearance": {"status": "pass" if preflight.qualified else "fail", "preflight": preflight.to_dict()},
        "mesh_qualification": qualification.get("check_mesh", {}),
        "solver_convergence": {"status": "pass" if qualification.get("solver", {}).get("qualified") else "fail", "qualification": qualification.get("solver", {})},
        "solver_final_residuals": residual_gate,
        "force_stationarity": qualification.get("force_stationarity", {}),
        **physical_gates,
    }
    passed = all(gate.get("qualified", gate.get("status") == "pass") for gate in gates.values()) and bool(run_result.ok)
    outcome = {
        "kind": "stage_v_v16_physical_profile_expanded_domain",
        "schema_version": 1,
        "evidence_class": "qualification_result",
        "status": "pass" if passed else "fail",
        "qualified": passed,
        "question": run_manifest["question"],
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
        "manifest": {"path": _rel(MANIFEST), "sha256": _sha256(MANIFEST)},
        "parent_v1_outcome": {"path": run_manifest["parent_v1"]["outcome"]["path"], "sha256": run_manifest["parent_v1"]["outcome"]["sha256"]},
        "case_dir": _rel(CASE_DIR),
        "domain_factor": run_manifest["domain_factor"],
        "docker": run_manifest["docker"],
        "openfoam_run": run_result.to_dict(),
        "preflight": {"path": _rel(preflight_path), "sha256": _sha256(preflight_path)},
        "qualification": {"path": None if qualification_path is None else _rel(qualification_path), "sha256": None if qualification_path is None else _sha256(qualification_path), "record": qualification},
        "boundary_metrics": boundary_metrics,
        "gates": gates,
        "execution": {"solver_started": True, "mesh_generation_started": True, "optimization_campaign_started": False, "new_run_count": 1},
        "claims_not_supported": run_manifest["claims_not_supported"],
        "next_gate": "register at least two same-profile domains for convergence" if passed else "remain blocked; fix the failed physical-profile gate before domain convergence or Stage S",
    }
    digest = _write_outcome(outcome)
    print(json.dumps({"status": outcome["status"], "qualified": passed, "outcome": _rel(OUTCOME), "outcome_sha256": digest}, ensure_ascii=False, sort_keys=True))
    return outcome


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="run the single registered expanded-domain physical-profile case")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    if not args.run:
        parser.error("specify --run")
    run(args.timeout_seconds)


if __name__ == "__main__":
    main()
