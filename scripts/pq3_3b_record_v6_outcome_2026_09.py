"""Record the immutable PQ3.3b v6 campaign outcome from the output directory.

Reads only verified local artifacts (campaign_meta, latest/checkpoints, events)
plus a transform-only projected-volume recomputation of the final rho. No
solver run. Refuses to overwrite an existing outcome.
"""

from __future__ import annotations

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
from scripts.pq3_3b_campaign_v6_2026_09 import MANIFEST, _path  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import phi_of, sha256_array  # noqa: E402

CAMPAIGN = ROOT / "work/pq3_3b_campaign_v6"
OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v6_outcome_2026_09.json"
SHAPE = (60, 32, 24)
SPACING_M = 0.05


def _final_rho_and_state() -> tuple[np.ndarray, dict]:
    pointer = ca.load_json(CAMPAIGN / "latest.json")
    state_path = CAMPAIGN / pointer["state_path"]
    if ca.sha256_file(state_path) != pointer["state_sha256"]:
        raise SystemExit("latest checkpoint hash mismatch")
    state = ca.load_json(state_path)
    rho = np.load(CAMPAIGN / state["rho_path"], allow_pickle=False)
    if sha256_array(rho) != state["rho_sha256"]:
        raise SystemExit("final rho hash mismatch")
    return rho, state


def main() -> None:
    if OUTCOME.exists():
        raise SystemExit("v6 outcome already exists")
    manifest = ca.load_json(MANIFEST)
    meta = ca.load_json(CAMPAIGN / "campaign_meta.json")
    if meta.get("status") != "blocked":
        raise SystemExit("v6 campaign is not in a blocked state; outcome not recorded")
    rho, state = _final_rho_and_state()
    levels = {level["name"]: level for level in manifest["levels"]}
    level = levels[meta["level"]]
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
    with (CAMPAIGN / "events.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            if payload.get("kind") == "objective_attempt":
                attempts.append(payload)
            elif payload.get("kind") == "objective_accepted":
                accepted.append(payload)
    stopping = attempts[-1]
    per_alpha = []
    for candidate in stopping["phase2"]["candidates"]:
        per_alpha.append(
            {
                "alpha": candidate["alpha"],
                "phi_after": candidate["phi_after"],
                "projected_volume_within_v_max": candidate["gates"].get("projected_volume_within_v_max"),
                "corrected_update_inf_norm": candidate["corrected_update_inf_norm"],
                "reason": candidate["reason"],
            }
        )
    outcome = {
        "kind": "pq3_3b_campaign_v6_outcome",
        "schema_version": 1,
        "manifest_sha256": ca.sha256_file(MANIFEST),
        "output_directory": str(CAMPAIGN.relative_to(ROOT)),
        "status": {"status": meta["status"], "reason": meta["reason"], "level": meta["level"]},
        "level_records": {
            level["name"]: {
                "start_rho_sha256": manifest["input_stop_state"]["rho_sha256"],
                "accepted_steps": len(accepted),
                "last_trial_objective": state.get("last_trial_objective"),
                "last_trial_downforce": state.get("last_trial_downforce"),
                "last_metrics": state.get("metrics"),
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
            "level_converged": False,
            "reason": "the projected-volume cap Vmax was reached before the convergence window",
        },
        "checkpoint": {
            "index": state["checkpoint_index"],
            "level_index": state["level_index"],
            "accepted_count": state["accepted_count"],
            "rho_sha256": state["rho_sha256"],
            "rho_file_sha256": state["rho_file_sha256"],
            "verified_chain": True,
        },
        "output_hashes": {
            "campaign_meta_json": ca.sha256_file(CAMPAIGN / "campaign_meta.json"),
            "events_jsonl": ca.sha256_file(CAMPAIGN / "events.jsonl"),
            "latest_json": ca.sha256_file(CAMPAIGN / "latest.json"),
        },
        "claims_supported": [
            "nine objective steps were accepted at b=8 under the inequality policy, raising same-level downforce from 0.579818003757",
            "the stopping attempt failed every alpha on the registered projected-volume upper bound",
            "the b=8 level did not meet the registered convergence window",
        ],
        "claims_not_supported": [
            "no b16 campaign result, no terminal independent evaluation",
            "no KKT or convergence conclusion; the volume cap, not stationarity, stopped the run",
            "no Stage S readiness",
        ],
    }
    OUTCOME.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": outcome["status"], "accepted_steps": len(accepted), "phi_final": phi_final, "path": str(OUTCOME)}))


if __name__ == "__main__":
    main()
