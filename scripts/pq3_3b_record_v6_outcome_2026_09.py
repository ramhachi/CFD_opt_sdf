"""Record a PQ3.3b campaign outcome from its output directory (no solver run).

Generic over the campaign manifest: reads campaign_meta, the verified
checkpoint chain and events, recomputes the final projected volume through the
registered transform, and writes an append-only outcome artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import _path  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import phi_of, sha256_array  # noqa: E402

SHAPE = (60, 32, 24)
SPACING_M = 0.05


def _final_rho_and_state(campaign_dir: Path) -> tuple[np.ndarray, dict]:
    pointer = ca.load_json(campaign_dir / "latest.json")
    state_path = campaign_dir / pointer["state_path"]
    if ca.sha256_file(state_path) != pointer["state_sha256"]:
        raise SystemExit("latest checkpoint hash mismatch")
    state = ca.load_json(state_path)
    rho = np.load(campaign_dir / state["rho_path"], allow_pickle=False)
    if sha256_array(rho) != state["rho_sha256"]:
        raise SystemExit("final rho hash mismatch")
    return rho, state


def record(manifest_path: Path, campaign_dir: Path, outcome_path: Path, kind: str) -> dict:
    manifest = ca.load_json(manifest_path)
    meta = ca.load_json(campaign_dir / "campaign_meta.json")
    terminal = None
    if meta.get("status") == "terminal_evaluated_not_stage_s_qualified":
        terminal_path = campaign_dir / "terminal.json"
        if not terminal_path.is_file():
            raise SystemExit("terminal campaign lacks terminal.json")
        terminal = ca.load_json(terminal_path)
    elif meta.get("status") != "blocked":
        raise SystemExit("campaign is not in a recorded state; outcome not recorded")
    rho, state = _final_rho_and_state(campaign_dir)
    levels = {level["name"]: level for level in manifest["levels"]}
    level = levels[meta.get("level") or manifest["input_stop_state"]["level"]]
    grid = load_fixed_grid_density_state(_path(manifest["registered_inputs"]["canonical_grid"]))
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=manifest["filter_radius_m"]),
        projection=TanhProjection(level["b"], manifest["projection_eta"]),
        ramp=RampInterpolation(level["q"]),
    )
    phi_final = phi_of(transform, rho, active)
    attempts: list[dict] = []
    accepted: list[dict] = []
    with (campaign_dir / "events.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            if payload.get("kind") == "objective_attempt":
                attempts.append(payload)
            elif payload.get("kind") == "objective_accepted":
                accepted.append(payload)
    stopping = attempts[-1]
    per_alpha = [
        {
            "alpha": candidate["alpha"],
            "phi_after": candidate["phi_after"],
            "projected_volume_within_v_max": candidate["gates"].get("projected_volume_within_v_max"),
            "corrected_update_inf_norm": candidate["corrected_update_inf_norm"],
            "volume_cap_correction_applied": candidate.get("volume_cap_correction_applied"),
            "volume_cap_kappa": candidate.get("volume_cap_kappa"),
            "reason": candidate["reason"],
        }
        for candidate in stopping["phase2"]["candidates"]
    ]
    cycle_metrics = [entry["metric"] for entry in accepted]
    outcome = {
        "kind": kind,
        "schema_version": 1,
        "manifest_sha256": ca.sha256_file(manifest_path),
        "output_directory": str(campaign_dir.relative_to(ROOT)),
        "status": {
            "status": meta["status"],
            "reason": meta.get("reason"),
            "level": meta.get("level") or manifest["input_stop_state"]["level"],
        },
        "level_records": {
            level["name"]: {
                "start_rho_sha256": manifest["input_stop_state"]["rho_sha256"],
                "accepted_steps": len(accepted),
                "last_trial_objective": (terminal or state).get("objective", state.get("last_trial_objective")),
                "last_trial_downforce": (terminal or {}).get("run", {}).get("downforce_coefficient", state.get("last_trial_downforce")),
                "last_metrics": cycle_metrics[-manifest["convergence"]["window_accepted"]:],
                "final_rho_sha256": sha256_array(rho),
                "projected_volume_final": phi_final,
                "projected_volume_fraction_of_v_max": phi_final / manifest["v_max_projected"],
                "stopping_attempt": {
                    "attempt": stopping["attempt"],
                    "parent_downforce_coefficient": stopping["parent_run"]["downforce_coefficient"],
                    "candidates": per_alpha,
                },
            }
        },
        "convergence": {
            "min_accepted_iterations": level["min_accepted_iterations"],
            "window_accepted": manifest["convergence"]["window_accepted"],
            "objective_delta_abs_max": manifest["convergence"]["objective_delta_abs_max"],
            "level_converged": bool(meta.get("status") == "terminal_evaluated_not_stage_s_qualified"),
            "reason": (
                "the registered convergence window was met and the terminal evaluation ran"
                if meta.get("status") == "terminal_evaluated_not_stage_s_qualified"
                else "the registered convergence window was not met before the policy stop"
            ),
        },
        "terminal": terminal,
        "checkpoint": {
            "index": state["checkpoint_index"],
            "level_index": state["level_index"],
            "accepted_count": state["accepted_count"],
            "rho_sha256": state["rho_sha256"],
            "rho_file_sha256": state["rho_file_sha256"],
            "verified_chain": True,
        },
        "output_hashes": {
            "campaign_meta_json": ca.sha256_file(campaign_dir / "campaign_meta.json"),
            "events_jsonl": ca.sha256_file(campaign_dir / "events.jsonl"),
            "latest_json": ca.sha256_file(campaign_dir / "latest.json"),
        },
        "claims_supported": [
            "the accepted steps and the stopping attempt are recorded with their gate verdicts and projections",
            "the final rho and the checkpoint chain are hash-verified",
        ],
        "claims_not_supported": [
            "no convergence or stationarity certificate; the registered window governs",
            "no terminal independent evaluation and no Stage S readiness",
        ],
    }
    outcome_path.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a PQ3.3b campaign outcome")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--kind", required=True)
    args = parser.parse_args()
    outcome_path = Path(args.outcome)
    if outcome_path.exists():
        raise SystemExit("campaign outcome already exists")
    outcome = record(
        Path(args.manifest).resolve(),
        Path(args.campaign).resolve(),
        outcome_path.resolve(),
        args.kind,
    )
    print(json.dumps({"status": outcome["status"], "path": str(outcome_path)}))


if __name__ == "__main__":
    main()
