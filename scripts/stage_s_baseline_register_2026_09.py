"""Register the Stage S baseline from the PQ4.1 v16-state pass (no solver run).

Binds the selected ``rho_projection`` iso surface (iso 0.5), the transform, the
candidate lineage and the handoff artifact hashes into one append-only record,
re-runs the registered ``stage_v_clearance_v1`` preflight on the selected
surface, and pins the Work F qualification profiles. Refuses to overwrite an
existing record.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1  # noqa: E402
from cfd_sdf.fd_preregistration import FD_QUALIFICATION_PROFILE_V1  # noqa: E402
from cfd_sdf.fixed_grid_contract import _read_cell_vti  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import (  # noqa: E402
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
)

V16_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v16_2026_09.json"
V16_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v16_outcome_2026_09.json"
PQ41_ARTIFACT = ROOT / "docs/evidence/pq4_1_v16_state_stage_s_entry_2026_09.json"
PQ41_BUNDLE = ROOT / "work/pq4_1_v16_state"
SELECTED_MANIFEST = PQ41_BUNDLE / "sweep/threshold_0.5/handoff_manifest.json"
GATE_SPEC = ROOT / "work/pq4_candidate/project.yaml"
ARTIFACT = ROOT / "docs/evidence/stage_s_baseline_v16_2026_09.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    raw = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(raw.tobytes()).hexdigest()


def build() -> dict:
    if ARTIFACT.exists():
        raise SystemExit("Stage S baseline artifact already exists; refuse overwrite")
    manifest = ca.load_json(V16_MANIFEST)
    outcome = ca.load_json(V16_OUTCOME)
    pq41 = ca.load_json(PQ41_ARTIFACT)
    verdict = pq41["stage_s_entry_verdict"]
    if verdict["ready_for_stage_s"] is not True:
        raise SystemExit("PQ4.1 verdict is not ready_for_stage_s=true")
    if verdict["selected_threshold"] != 0.5:
        raise SystemExit("PQ4.1 selected threshold is not the registered iso 0.5")
    if pq41["selection_rule"].get("require_ready_for_stage_s") is not True:
        raise SystemExit("PQ4.1 selection rule does not require ready_for_stage_s")
    if pq41["input"]["campaign_manifest_sha256"] != _sha256(V16_MANIFEST):
        raise SystemExit("PQ4.1 input does not match the v16 manifest")
    if pq41["input"]["campaign_outcome"]["sha256"] != _sha256(V16_OUTCOME):
        raise SystemExit("PQ4.1 input does not match the v16 outcome")
    sidecar = V16_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if _sha256(V16_MANIFEST) != sidecar:
        raise SystemExit("v16 manifest sidecar mismatch")

    # handoff manifest and its artifacts
    selected_row = next(
        row for row in pq41["extraction_sweep"]["rows"] if row["threshold"] == 0.5
    )
    if _sha256(SELECTED_MANIFEST) != selected_row["manifest_sha256"]:
        raise SystemExit("selected handoff manifest hash mismatch")
    handoff = ca.load_json(SELECTED_MANIFEST)
    handoff_base = SELECTED_MANIFEST.parent
    handoff_artifacts: dict[str, dict[str, str]] = {}
    for key, record in handoff["artifacts"].items():
        path = handoff_base / record["path"]
        actual = _sha256(path)
        if actual != record["sha256"]:
            raise SystemExit(f"handoff artifact changed: {key}")
        handoff_artifacts[key] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": actual,
        }

    # four-field bundle: file hashes plus the geometry/solver array hashes
    bundle_files: dict[str, dict[str, str]] = {}
    for name, path_str in pq41["fields"]["bundle"].items():
        path = ROOT / path_str
        bundle_files[name] = {"path": path_str, "sha256": _sha256(path)}
    _, projection_arrays = _read_cell_vti(
        ROOT / pq41["fields"]["bundle"]["rho_projection"],
        expected_kind="stage_t_field_rho_projection",
    )
    _, beta_arrays = _read_cell_vti(
        ROOT / pq41["fields"]["bundle"]["beta_solver"],
        expected_kind="stage_t_field_beta_solver",
    )
    if _array_sha256(projection_arrays["rho_projection"]) != pq41["fields"]["rho_projection_sha256"]:
        raise SystemExit("rho_projection array hash mismatch")
    if _array_sha256(beta_arrays["beta_solver"]) != pq41["fields"]["beta_solver_sha256"]:
        raise SystemExit("beta_solver array hash mismatch")

    # registered clearance preflight on the selected surface
    spec = load_problem_spec(GATE_SPEC)
    preflight = evaluate_stage_v_domain_preflight(
        spec,
        ROOT / handoff_artifacts["surface_stl"]["path"],
        float(spec.grid.voxel_size_m),
        profile=STAGE_V_CLEARANCE_PROFILE_V1,
    )
    if not preflight.qualified:
        raise SystemExit(f"selected surface fails the clearance preflight: {preflight.reasons}")

    sub_summary = {
        key: bool(sub.get("pass")) if isinstance(sub, dict) else None
        for key, sub in verdict["sub_verdicts"].items()
        if key != "lineage"
    }
    artifact = {
        "kind": "stage_s_baseline_v16",
        "schema_version": 1,
        "baseline_id": "stage_s_baseline_v16_2026_09",
        "candidate": {
            "label": "v16 final accepted checkpoint (checkpoint 87, blocked stop)",
            "campaign_manifest": {
                "path": str(V16_MANIFEST.relative_to(ROOT)),
                "sha256": _sha256(V16_MANIFEST),
            },
            "campaign_outcome": {
                "path": str(V16_OUTCOME.relative_to(ROOT)),
                "sha256": _sha256(V16_OUTCOME),
            },
            "checkpoint_index": pq41["input"]["checkpoint_index"],
            "checkpoint_state": {
                "path": outcome["checkpoint"]["state_path"],
                "sha256": pq41["input"]["checkpoint_state_sha256"],
            },
            "rho_sha256": pq41["input"]["candidate_rho_sha256"],
            "rho_file_sha256": pq41["input"]["candidate_rho_file_sha256"],
            "final_downforce": outcome["level_records"]["level_3_b128_margin"]["last_trial_downforce"],
            "projected_volume": pq41["projected_volume"],
            "v_max_projected": pq41["volume_constraint"]["limit"],
            "volume_tolerance": pq41["volume_constraint"]["absolute_tolerance"],
        },
        "handoff": {
            "pq4_1_artifact": {
                "path": str(PQ41_ARTIFACT.relative_to(ROOT)),
                "sha256": _sha256(PQ41_ARTIFACT),
            },
            "selected_threshold": pq41["stage_s_entry_verdict"]["selected_threshold"],
            "selection_rule": pq41["selection_rule"],
            "manifest": {
                "path": str(SELECTED_MANIFEST.relative_to(ROOT)),
                "sha256": selected_row["manifest_sha256"],
            },
            "artifacts": handoff_artifacts,
        },
        "fields": {
            "bundle": bundle_files,
            "rho_projection_array_sha256": pq41["fields"]["rho_projection_sha256"],
            "beta_solver_array_sha256": pq41["fields"]["beta_solver_sha256"],
            "transform": pq41["transform"],
            "beta_equals_ramp_of_projection_max_abs_difference": pq41["fields"][
                "beta_equals_ramp_of_projection_max_abs_difference"
            ],
            "geometry_basis": "rho_projection",
            "solver_audit_field": "beta_solver",
            "field_distinction": (
                "Stage T solver response uses beta_solver = p / (1 + q(1 - p)) with "
                "p = rho_projection and q = 100; Stage S geometry uses rho_projection. "
                "The two arrays are never interchangeable."
            ),
        },
        "clearance": {
            "profile_id": STAGE_V_CLEARANCE_PROFILE_V1["profile_id"],
            "minimum_clearance_m": STAGE_V_CLEARANCE_PROFILE_V1["minimum_clearance_m"],
            "qualified": bool(preflight.qualified),
            "reasons": list(preflight.reasons),
            "surface_stl_sha256": handoff_artifacts["surface_stl"]["sha256"],
            "problem_spec": {
                "path": str(GATE_SPEC.relative_to(ROOT)),
                "sha256": _sha256(GATE_SPEC),
            },
        },
        "gate": {
            "profile_id": "stage_s_entry_v1",
            "ready_for_stage_s": True,
            "sub_verdicts": sub_summary,
            "pq4_1_artifact_sha256": _sha256(PQ41_ARTIFACT),
        },
        "work_f_profiles": {
            "mesh_and_solver": {
                "profile_id": STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"],
                "check_mesh": STAGE_V_QUALIFICATION_PROFILE_V1["check_mesh"],
                "force_stationarity": STAGE_V_QUALIFICATION_PROFILE_V1["force_stationarity"],
            },
            "surface_fd": FD_QUALIFICATION_PROFILE_V1,
            "clearance": {
                "profile_id": STAGE_V_CLEARANCE_PROFILE_V1["profile_id"],
                "minimum_clearance_m": STAGE_V_CLEARANCE_PROFILE_V1["minimum_clearance_m"],
            },
            "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        },
        "claims_supported": [
            "one candidate passed the repaired composite Stage S entry gate and is bound with its handoff, transform, field and clearance hashes",
            "the selected iso-0.5 surface passes the registered stage_v_clearance_v1 preflight",
        ],
        "claims_not_supported": [
            "this is a baseline registration, not a Stage S qualification or a shape step",
            "no grid independence, target-physics or full-vehicle claim; the candidate is a blocked-stop checkpoint, not a converged terminal",
            "the solver-execution clearance reconfirmation (P17) is not performed here",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "baseline_id": artifact["baseline_id"],
                "sha256": _sha256(ARTIFACT),
                "selected_threshold": artifact["handoff"]["selected_threshold"],
                "ready_for_stage_s": artifact["gate"]["ready_for_stage_s"],
            },
            indent=2,
        )
    )
    return artifact


if __name__ == "__main__":
    build()
