"""Register the immutable, one-step-only v13 direction discriminant."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

V12_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v12_2026_09.json"
V12_STATE = ROOT / "work/pq3_3b_campaign_v12/checkpoints/state_0001.json"
V12_RHO = ROOT / "work/pq3_3b_campaign_v12/checkpoints/rho_0001.npy"
V12_EVENTS = ROOT / "work/pq3_3b_campaign_v12/events.jsonl"
V12_META = ROOT / "work/pq3_3b_campaign_v12/campaign_meta.json"
V12_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v12_outcome_2026_09.json"
V12_PARENT_SUMMARY = ROOT / "work/pq3_3b_campaign_v12/runs/parent_3603a5b04721/case/fixed_grid_primal_summary.json"
DIRECTION_AUDIT = ROOT / "docs/evidence/pq3_3b_v13_direction_audit_2026_09.json"
DIRECTION_AUDIT_SCRIPT = ROOT / "scripts/pq3_3b_v13_direction_audit_2026_09.py"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v13_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_v13_discriminant_manifest_2026_09.json"


def _ref(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": ca.sha256_file(path)}


def build() -> dict:
    v12 = ca.load_json(V12_MANIFEST)
    state = ca.load_json(V12_STATE)
    audit = ca.load_json(DIRECTION_AUDIT)
    rho = np.load(V12_RHO, allow_pickle=False)
    if state.get("checkpoint_index") != 1 or state.get("accepted_count") != 6:
        raise ValueError("v12 checkpoint 1 lineage mismatch")
    if state.get("rho_sha256") != sha256_array(rho):
        raise ValueError("v12 checkpoint 1 array hash mismatch")
    if audit["summary"].get("solver_invocations") != 0:
        raise ValueError("v13 direction audit must be solver-free")
    if audit["summary"].get("transform_feasible_candidate_found") is not True:
        raise ValueError("v13 direction audit found no transform-feasible candidate")
    level = next(
        item for item in v12["levels"] if item["name"] == state.get("level", v12["input_stop_state"]["level"])
    )
    return {
        "kind": "pq3_3b_v13_discriminant_manifest",
        "schema_version": 1,
        "immutable": True,
        "status": "registered_preflight_pending",
        "scope": "one_step_preflight_only",
        "long_campaign_registered": False,
        "change": {
            "id": "raw-gradient-projected-to-discreteness-tangent",
            "reason": (
                "v12 checkpoint 1 remains inside mean_nd <= 0.01, but every registered "
                "sign-step alpha increases mean_nd above the bound"
            ),
            "does_not_relax": [
                "mean_nd <= 0.01",
                "projected volume <= Vmax",
                "Path B, real-primal response, occupancy, mask, or move-box gates",
            ],
        },
        "pinned_inputs": {
            "v12_manifest": _ref(V12_MANIFEST),
            "v12_checkpoint_state": _ref(V12_STATE),
            "v12_checkpoint_rho": _ref(V12_RHO),
            "v12_events": _ref(V12_EVENTS),
            "v12_campaign_meta": _ref(V12_META),
            "v12_outcome": _ref(V12_OUTCOME),
            "v12_cached_parent_summary": _ref(V12_PARENT_SUMMARY),
            "v13_direction_audit_script": _ref(DIRECTION_AUDIT_SCRIPT),
        },
        "input_stop_state": {
            "source": "v12 accepted checkpoint 1 immediately before objective_rejected",
            "level": level["name"],
            "state_path": str(V12_STATE.relative_to(ROOT)),
            "state_sha256": ca.sha256_file(V12_STATE),
            "rho_path": str(V12_RHO.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(V12_RHO),
            "rho_sha256": sha256_array(rho),
            "accepted_count": int(state["accepted_count"]),
        },
        "direction_audit": _ref(DIRECTION_AUDIT),
        "direction_policy": {
            "id": "objective-gradient-discreteness-projected-v1",
            "objective_direction": "d0 = -gJ on free active cells",
            "discreteness_gradient": (
                "gD = pullback_from_projected(4*(1-2*rho_projection)/Nactive)"
            ),
            "projection": (
                "if gD dot d0 > 0: d = d0 - (gD dot d0 / ||gD_free||^2) gD_free"
            ),
            "normalization": "d = d / ||d||_inf after mask and box-face freeze",
            "freeze_exact_box_faces": True,
            "module": "src/cfd_sdf/phase2_discreteness_direction.py",
        },
        "alpha_ladder": v12["phase2_policy"]["alpha_ladder"],
        "level": {
            key: level[key] for key in ("name", "b", "q", "move_limit")
        },
        "gates": {
            "discreteness_field": "rho_projection",
            "discreteness_scope": "active",
            "discreteness_metric": "mean(4*rho*(1-rho))",
            "discreteness_mean_nd_max": v12["phase2_policy"]["discreteness_mean_nd_max"],
            "v_max_projected": v12["v_max_projected"],
            "min_corrected_update_inf_norm": v12["phase2_policy"]["min_corrected_update_inf_norm"],
            "extractability_fraction": v12["phase2_policy"]["extractability_fraction"],
            "extractability_thresholds": v12["phase2_policy"]["extractability_thresholds"],
        },
        "registered_inputs": v12["registered_inputs"],
        "margin_mask": v12["margin_mask"],
        "filter_radius_m": v12["filter_radius_m"],
        "projection_eta": v12["projection_eta"],
        "openfoam_image": v12["openfoam_image"],
        "openfoam_image_id": v12["openfoam_image_id"],
        "objective": v12["objective"],
        "path_b": v12["path_b"],
        "noise_thresholds": v12["noise_thresholds"],
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v13_entry_preflight_2026_09.json",
            "output_directory": "work/pq3_3b_v13_entry_preflight",
            "bounded_calls": (
                "reuse one cached parent/adjoint; first transform-feasible candidate "
                "only: one centered Path B pair and at most one fresh candidate primal"
            ),
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "registration and transform feasibility do not establish a real-primal improvement",
            "v13 does not register or start a long campaign",
            "one preflight step cannot establish convergence or Stage S readiness",
            "the result is not grid-independent or target-physics evidence",
        ],
    }


def main() -> None:
    sidecar = MANIFEST.with_suffix(".json.sha256")
    if MANIFEST.exists() or sidecar.exists():
        raise SystemExit("v13 discriminant manifest already exists")
    manifest = build()
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sidecar.write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "sha256": ca.sha256_file(MANIFEST),
                "selected_alpha": ca.load_json(DIRECTION_AUDIT)["selected"]["alpha"],
                "scope": manifest["scope"],
            }
        )
    )


if __name__ == "__main__":
    main()
