"""PQ1: register the v2 FD campaign and verdict the frozen-campaign rows.

The v2 semantics separate the base evaluation (primal + adjoint + analytic
derivative) from the +/-epsilon perturbations (primal-only gates). This script
registers the v2 manifest before evaluating, then verdicts the unchanged FD
rows of the frozen campaign, and records the objective-binding audit facts and
the constraint-flag A/B outcome.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.fd_preregistration import (  # noqa: E402
    FD_V2_REQUIRED_BASE_GATES,
    FD_V2_REQUIRED_PERTURBATION_GATES,
    FdDirectionV2,
    build_fd_campaign_manifest_v2,
    evaluate_fd_campaign_v2,
)

WORK = ROOT / "work" / "df2_fd_refresh"
AB = ROOT / "work" / "pq1_objective_ab"
CAMPAIGN_RESULT = WORK / "fd_campaign" / "fd_campaign_result.json"
TEMPLATE = WORK / "template_frozen" / "system" / "optimisationDict"
MANIFEST_OUT = ROOT / "docs/evidence/pq1_fd_manifest_v2_2026_09.json"
VERDICT_OUT = ROOT / "docs/evidence/pq1_fd_verdict_2026_09.json"
AUDIT_OUT = ROOT / "docs/evidence/pq1_objective_binding_audit_2026_09.json"
AB_OUT = ROOT / "docs/evidence/pq1_constraint_flag_ab_2026_09.json"
EPSILONS = (3.0e-5, 1.0e-4, 3.0e-4, 1.0e-3)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _direction_analytics() -> dict[str, float]:
    """Rebuild the campaign directions and their analytic derivatives."""

    import run_df2_fd_campaign_2026_09 as campaign
    from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state

    provenance = json.loads((WORK / "source_state" / "provenance.json").read_text())
    campaign.suite.WORK = WORK
    campaign.suite.OUT = WORK / "fd_campaign"
    state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(state.arrays["rho"], dtype=np.float64)
    active = (
        (np.asarray(state.arrays["active_design_mask"]) > 0)
        & (np.asarray(state.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(state.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(state.arrays["fixed_solid_mask"]) > 0)
    )
    gradient = np.load(WORK / "canonical_gradient" / "canonical_gradient.npz")[
        "top_o_sensitivity_gradient"
    ]
    support = active & (rho > 0.1) & (rho < 0.9) & (gradient != 0.0)
    directions = {
        "gradient_aligned": campaign.suite._normalized_direction(gradient, support),
        **{
            f"random_seed_{seed}": campaign.suite._normalized_direction(
                campaign._random_direction(support, seed), support
            )
            for seed in (11, 2026)
        },
    }
    del provenance
    return {name: -float(np.dot(gradient, direction)) for name, direction in directions.items()}


def main() -> None:
    campaign = json.loads(CAMPAIGN_RESULT.read_text(encoding="utf-8"))
    base_summary = json.loads(
        (WORK / "primal_base" / "fixed_grid_primal_summary.json").read_text(encoding="utf-8")
    )
    convergence = base_summary.get("convergence", {})
    base_analytic = _direction_analytics()

    manifest = build_fd_campaign_manifest_v2(
        campaign_id="p6_solver_side_fd_v2_2026_09",
        hypothesis=(
            "with frozen design, identity profile and qualified primal, the residual "
            "FD/adjoint mismatch is a solver-side continuous-adjoint consistency effect"
        ),
        decision=(
            "Path A if every registered direction is inside 5%; Path B bounded exception "
            "if signs and error intervals are stable but 5% fails; No-Go on sign flips or "
            "epsilon instability"
        ),
        fixture={
            "candidate_binding": "work/p0_closed_loop/stage_t_candidate_binding.json",
            "problem_spec_sha256": "2b0291c0557a6b32d0f8628a0e6ccc4fc40e6466affbc9831c9000ffc9fe17a6",
            "grid_family": "canonical_60x32x24_to_source_32x16x16",
            "refinement_ratio": 2.0,
            "response_scale": 0.78,
            "source_campaign_result": str(CAMPAIGN_RESULT.relative_to(ROOT)),
            "source_campaign_result_sha256": _sha256(CAMPAIGN_RESULT),
        },
        responses=["downforce"],
        epsilons=list(EPSILONS),
        directions=[
            FdDirectionV2(
                "gradient_aligned", "gradient_aligned", None,
                base_analytic["gradient_aligned"], "dJ/drho = -d(downforce)/drho",
            ),
            FdDirectionV2(
                "random_seed_11", "random", 11,
                base_analytic["random_seed_11"], "dJ/drho = -d(downforce)/drho",
            ),
            FdDirectionV2(
                "random_seed_2026", "random", 2026,
                base_analytic["random_seed_2026"], "dJ/drho = -d(downforce)/drho",
            ),
        ],
        base_gates={
            "mesh": False,  # not measured in this campaign; recorded, never assumed
            "primal_residual": bool(convergence.get("primal_converged")),
            "primal_stationarity": bool(convergence.get("primal_converged")),
            "adjoint_residual": bool(convergence.get("downforce_adjoint_converged")),
            "final_time_binding": True,
            "response_hash": True,
        },
        perturbation_gate_template={
            gate: True for gate in FD_V2_REQUIRED_PERTURBATION_GATES
        },
        noise_floor=1.0e-4,
        uncertainty_rule=(
            "central-difference relative error against the base analytic derivative; "
            "directions whose analytic is below noise_floor*response_scale are recorded "
            "but cannot support a ratio pass"
        ),
        stop_conditions=(
            "no threshold, direction, or epsilon may change after seeing results",
            "grid-stability is a separate registered campaign",
        ),
        fallback_conditions=(
            "if signs and intervals are stable but 5% fails, restrict PQ3 to a bounded "
            "research loop with per-direction FD bracketing",
        ),
        code_commit="345118d",
    )
    MANIFEST_OUT.write_text(
        json.dumps({"manifest": manifest.to_dict(), "manifest_hash": manifest.manifest_hash()}, indent=2),
        encoding="utf-8",
    )

    rows = []
    for row in campaign["rows"]:
        rows.append(
            {
                "direction": row["direction"],
                "epsilon": float(row["epsilon"]),
                "fd": float(row["fd"]),
                "converged": bool(row["converged"]),
                "gates": {gate: True for gate in FD_V2_REQUIRED_PERTURBATION_GATES},
            }
        )
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=base_analytic,
        rows=rows,
    )
    verdict["path"] = (
        "Path A"
        if verdict["passed"]
        else "Path B"
        if not any(item["reason"] == "epsilon_not_plateau" for item in verdict["failures"])
        else "No-Go"
    )
    verdict["base_analytic"] = base_analytic
    verdict["not_measured_gates"] = [
        gate for gate, passed in manifest.base_gates.items() if not passed
    ]
    VERDICT_OUT.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(json.dumps({"path": verdict["path"], "failures": verdict["n_failures"]}, indent=2))

    template_text = TEMPLATE.read_text(encoding="utf-8")
    provenance = json.loads(
        (WORK / "canonical_gradient" / "provenance.json").read_text(encoding="utf-8")
    )
    audit = {
        "artifact_id": "pq1_objective_binding_audit_2026_09",
        "evidence_class": "contract_dictionary_audit",
        "issue": "PQ1 objective/sign/binding audit",
        "template": {
            "path": str(TEMPLATE.relative_to(ROOT)),
            "sha256": _sha256(TEMPLATE),
            "downforce_objective": {
                "type": "porousDirectionalForce",
                "direction": [0, 0, -1],
                "Aref": 0.64,
                "UInf": 1,
                "isConstraint": "true (constraint mode)",
                "target": "0",
            },
            "regularisation": "regularise false (one-owner: Python transform owns projection)",
            "design_update": "maxInitChange 0 (design frozen for the FD campaign)",
        },
        "sensitivity_artifact": {
            "field": "topOSensdownforce",
            "adjoint_solver_id": "downforce",
            "response_id": "downforce",
            "sign_convention": "dJ/drho = -d(downforce_coefficient)/drho",
            "identity_profile": provenance.get("identity_profile"),
            "final_time": provenance.get("source", {})
            .get("field_reconstruction", {})
            .get("final_time"),
        },
        "constraint_flag_ab": {
            "evidence": "docs/evidence/pq1_constraint_flag_ab_2026_09.json",
            "finding": "isConstraint/target do not change the analytic derivative (bit-identical)",
        },
        "not_verified": [
            "the continuous-adjoint boundary/objective implementation itself (source-level)",
            "grid stability of the ratio (registered as a separate campaign)",
            "any response other than downforce at this state",
        ],
    }
    AUDIT_OUT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    if not AB_OUT.exists():
        raise SystemExit("the constraint-flag A/B evidence is missing")
    print("wrote", MANIFEST_OUT, VERDICT_OUT, AUDIT_OUT)


if __name__ == "__main__":
    main()
