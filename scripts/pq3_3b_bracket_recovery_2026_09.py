"""Bounded diagnostic at the blocked b=8 parent; never resumes the campaign.

The registered v4 bracket used epsilon=1e-4. Test larger centered pairs at
the exact rejected parent without lowering its 1e-6 objective-noise floor.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cfd_sdf import campaign_assertions as ca
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state
from cfd_sdf.path_b_bracket import BracketSpec
from cfd_sdf.phase2_policy import evaluate_phase2_candidate
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem
from scripts.pq3_3b_campaign_v4_2026_09 import ROOT, MANIFEST, SHAPE, SPACING_M, _load_checkpoint, _oracle, _path
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence, sha256_array

CAMPAIGN = ROOT / "work/pq3_3b_campaign_v4"
OUT = ROOT / "work/pq3_3b_bracket_recovery_v1"
EVIDENCE = ROOT / "docs/evidence/pq3_3b_bracket_recovery_v1_2026_09.json"
EPSILONS = (2e-4, 4e-4, 8e-4)


def main() -> None:
    if OUT.exists() or EVIDENCE.exists():
        raise SystemExit("bracket recovery artifacts exist; refusing overwrite")
    manifest_sha = MANIFEST.with_suffix(".json.sha256").read_text().strip()
    ca.assert_manifest_sha(MANIFEST, manifest_sha)
    manifest = ca.load_json(MANIFEST)
    campaign_meta = ca.load_json(CAMPAIGN / "campaign_meta.json")
    if campaign_meta != {
        "manifest_sha256": manifest_sha, "status": "blocked",
        "reason": "objective_rejected", "level": "level_1_b8_q30",
    }:
        raise ValueError("campaign stop state differs from the registered diagnostic input")
    state, rho = _load_checkpoint(CAMPAIGN)
    if state["level_index"] != 1 or state["accepted_count"] != 8:
        raise ValueError("not the b=8 eighth accepted checkpoint")
    outcome = ca.load_json(ROOT / "docs/evidence/pq3_3b_campaign_v4_outcome_2026_09.json")
    if state["rho_sha256"] != outcome["checkpoint"]["rho_sha256"]:
        raise ValueError("checkpoint differs from immutable campaign outcome")

    grid = load_fixed_grid_density_state(_path(manifest["canonical_grid"]))
    arrays = grid.arrays
    active = ((np.asarray(arrays["active_design_mask"]) > 0)
              & (np.asarray(arrays["allowed_mask"]) > 0)
              & ~(np.asarray(arrays["forbidden_mask"]) > 0)
              & ~(np.asarray(arrays["fixed_solid_mask"]) > 0))
    level = manifest["levels"][1]
    transform = DesignTransform(
        shape=SHAPE, spacing_m=SPACING_M, active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=manifest["filter_radius_m"]),
        projection=TanhProjection(level["b"], manifest["projection_eta"]),
        ramp=RampInterpolation(level["q"]),
    )
    spec = load_problem_spec(_path(manifest["problem_spec"]))
    compiled = compile_problem(spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]))
    OUT.mkdir(parents=True)
    shutil.copytree(_path(manifest["template_trial"]), OUT / "template_trial")
    oracle = _oracle(transform, compiled, manifest, OUT, OUT / "runs")
    parent = oracle.evaluate_parent(rho)
    parent_run = run_evidence(parent)
    original_parent = next(
        event["parent_run"] for event in reversed([
            json.loads(line) for line in (CAMPAIGN / "events.jsonl").read_text().splitlines()
        ]) if event["kind"] == "objective_attempt"
    )
    parent_spread = abs(float(parent.objective) + float(original_parent["downforce_coefficient"]))
    candidates = []
    for epsilon in EPSILONS:
        bracket_runs = []

        def evaluate_values(values):
            result = oracle.evaluate_values(values)
            bracket_runs.append({"rho_sha256": sha256_array(values), "run": run_evidence(result)})
            return result

        def evaluate_trial(values):
            result = oracle.evaluate_values(values)
            return result, run_evidence(result)

        candidate, corrected = evaluate_phase2_candidate(
            transform=transform, parent_result=parent, rho_parent=rho,
            parent_downforce=float(parent_run["downforce_coefficient"]),
            alpha=1.0, move_limit=level["move_limit"],
            target=manifest["registered_target"], v_max=manifest["v_max_projected"],
            volume_tolerance=manifest["volume_tolerance"],
            objective_noise_threshold=manifest["noise_thresholds"]["objective"],
            downforce_noise_threshold=manifest["noise_thresholds"]["downforce"],
            bracket_spec=BracketSpec(epsilon=epsilon, noise_floor_abs=manifest["path_b"]["noise_floor_abs"]),
            evaluate_values=evaluate_values, evaluate_trial=evaluate_trial,
            freeze_box_faces=True,
        )
        candidates.append({"epsilon": epsilon, "candidate": candidate.to_jsonable(),
                           "corrected_rho_sha256": sha256_array(corrected), "bracket_runs": bracket_runs})
        print(f"epsilon={epsilon} bracket={candidate.bracket['reason']} diff={candidate.bracket['details'].get('difference')} accepted={candidate.accepted}", flush=True)

    passing = [entry for entry in candidates if entry["candidate"]["accepted"]]
    slopes = [entry["candidate"]["bracket"]["d_fd"] for entry in passing]
    stable = bool(len(slopes) >= 2 and max(slopes) < 0 and
                  (max(slopes) - min(slopes)) / abs(float(np.mean(slopes))) <= 0.2)
    artifact = {
        "kind": "pq3_3b_bracket_recovery_v1", "schema_version": 1,
        "input_manifest_sha256": manifest_sha,
        "blocked_campaign_outcome_sha256": ca.sha256_file(ROOT / "docs/evidence/pq3_3b_campaign_v4_outcome_2026_09.json"),
        "input_checkpoint_rho_sha256": state["rho_sha256"],
        "checkpoint_chain_verified": True,
        "original_centered_epsilon": manifest["path_b"]["epsilon"],
        "unchanged_noise_floor_abs": manifest["path_b"]["noise_floor_abs"],
        "parent": {"objective": float(parent.objective), "run": parent_run,
                   "original_campaign_parent_run": original_parent,
                   "independent_parent_objective_spread": parent_spread},
        "candidates": candidates,
        "at_least_two_passing_stable_slopes": stable,
        "claims_not_supported": ["diagnostic does not resume the campaign", "no b16 or Stage S qualification"],
    }
    EVIDENCE.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"at_least_two_passing_stable_slopes": stable, "passing_epsilons": [x["epsilon"] for x in passing]}), flush=True)


if __name__ == "__main__":
    main()
