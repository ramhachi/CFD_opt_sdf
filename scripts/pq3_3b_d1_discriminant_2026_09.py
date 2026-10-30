"""PQ3.3b D1 bounded discriminant (docs/pq3_3b_post_v5_plan_2026_09.md).

Executes the pre-registered bounded experiment at the v5 stopped b=8 parent:

- two independent fresh parent primals in separate run roots (no case reuse),
- the four registered directions (d1 corrected alpha=1, d2 objective-only
  without the volume pullback, d3 volume-exchange orthogonal, d4 one-sided
  inward from box faces) at amplitudes 1.0 and 0.5,
- total new primals <= 10; the registered thresholds are not changed.

This is diagnostic evidence: it never accepts a step, never resumes the
campaign and never closes a level. The outcome artifact is append-only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.canonical_objective import canonical_objective_from  # noqa: E402
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence  # noqa: E402
from scripts.pq3_3b_stopped_state_d0_2026_09 import (  # noqa: E402
    _array_sha256,
    _projected_field,
    proposal_and_correction,
)

MANIFEST = ROOT / "docs/evidence/pq3_3b_d1_manifest_2026_09.json"
MANIFEST_V5 = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v5_2026_09.json"
D0 = ROOT / "docs/evidence/pq3_3b_stopped_state_diagnosis_2026_09.json"
OUTPUT = ROOT / "work/pq3_3b_d1"
OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
WORK = ROOT / "work/df2_fd_refresh"
SHAPE = (60, 32, 24)
SPACING_M = 0.05
MASK_TOLERANCE = 1e-12


def verify_preconditions() -> tuple[dict, dict, np.ndarray]:
    if not MANIFEST.is_file():
        raise SystemExit("D1 manifest missing")
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(MANIFEST) != sidecar:
        raise SystemExit("D1 manifest sidecar hash mismatch")
    manifest = ca.load_json(MANIFEST)
    if manifest["status"] != "registered_awaiting_execution":
        raise SystemExit("D1 manifest is not awaiting execution")
    if ca.sha256_file(D0) != manifest["diagnosis"]["sha256"]:
        raise SystemExit("D0 diagnosis artifact hash mismatch")
    if ca.sha256_file(MANIFEST_V5) != manifest["source_registration"]["manifest_v5"]["sha256"]:
        raise SystemExit("manifest v5 hash mismatch")
    rho_path = ROOT / manifest["stop_state"]["rho_path"]
    if ca.sha256_file(rho_path) != manifest["stop_state"]["rho_file_sha256"]:
        raise SystemExit("stopped rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if _array_sha256(rho) != manifest["stop_state"]["rho_sha256"]:
        raise SystemExit("stopped rho array hash mismatch")
    if OUTPUT.exists():
        raise SystemExit(f"D1 output directory already exists: {OUTPUT}")
    m5 = ca.load_json(MANIFEST_V5)
    for key in ("canonical_grid", "problem_spec", "template_parent", "template_trial"):
        ref = m5[key]
        path = ROOT / ref["path"]
        actual = ca.tree_sha256(path) if path.is_dir() else ca.sha256_file(path)
        if actual != ref["sha256"]:
            raise SystemExit(f"registered input mismatch: {key}")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != m5["source_tree_python_sha256"]:
        raise SystemExit("src/cfd_sdf tree differs from the v5 registration")
    return manifest, m5, np.asarray(rho, dtype=np.float64)


def _transform_for(m5: dict, active: np.ndarray, level: dict) -> DesignTransform:
    return DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=m5["filter_radius_m"]),
        projection=TanhProjection(level["b"], m5["projection_eta"]),
        ramp=RampInterpolation(level["q"]),
    )


def _oracle(m5: dict, transform, compiled, run_root: Path):
    adapter = OpenFoamOracle(
        OpenFoamOracleConfig(
            work_root=WORK,
            canonical_topology_state_json=ROOT / m5["canonical_grid"]["path"],
            template_parent=ROOT / m5["template_parent"]["path"],
            template_trial=OUTPUT / "template_trial",
            flow_case_id="straight",
            responses=("downforce",),
            run_root=run_root,
            timeout_seconds=1800,
            docker_image=m5["openfoam_image"],
        ),
        transform,
    )
    return make_oracle_from_compiled(
        transform=transform,
        compiled=compiled,
        primal_evaluator=adapter.primal_evaluator,
        parent_evaluator=adapter.parent_evaluator,
        adjoint_evaluator=None,
    )


def build_directions(*, transform, rho, grad_j, grad_v, active, move_limit, target, volume_tolerance):
    """Construct the four registered directions; every field is explicit."""
    frozen = active & ((rho == 0.0) | (rho == 1.0))
    proposal1, corrected1, kappa1 = proposal_and_correction(
        transform=transform,
        rho=rho,
        grad_j=grad_j,
        alpha=1.0,
        move_limit=move_limit,
        target=target,
        volume_tolerance=volume_tolerance,
    )
    if corrected1 is None:
        raise SystemExit("registered alpha=1 volume correction did not bracket")
    directions = []
    directions.append(
        {
            "id": "d1_corrected_alpha1",
            "delta": corrected1 - rho,
            "scale": 1.0,
            "apply_freeze": True,
            "one_sided": False,
            "kappa_volume": float(kappa1),
        }
    )
    directions.append(
        {
            "id": "d2_objective_only_no_volume_pullback",
            "delta": proposal1 - rho,
            "scale": 1.0,
            "apply_freeze": True,
            "one_sided": False,
            "kappa_volume": None,
        }
    )
    movable = active & ~frozen
    d3 = np.zeros_like(rho)
    if bool(movable.any()):
        g_s = grad_j[movable]
        v_s = grad_v[movable]
        denom = float(np.dot(v_s, v_s))
        if denom > 0.0:
            orth = g_s - (float(np.dot(g_s, v_s)) / denom) * v_s
            raw = np.zeros_like(rho)
            raw[movable] = -orth
            peak = float(np.max(np.abs(raw[movable])))
            if peak > 0.0:
                d3 = raw / peak
    directions.append(
        {
            "id": "d3_volume_exchange_orthogonal",
            "delta": d3,
            "scale": move_limit,
            "apply_freeze": True,
            "one_sided": False,
            "kappa_volume": None,
        }
    )
    descent = -np.sign(grad_j)
    d4 = np.zeros_like(rho)
    at_zero = frozen & (rho == 0.0)
    at_one = frozen & (rho == 1.0)
    d4[at_zero & (descent > 0)] = 1.0
    d4[at_one & (descent < 0)] = -1.0
    directions.append(
        {
            "id": "d4_inward_from_box_faces",
            "delta": d4,
            "scale": move_limit,
            "apply_freeze": False,
            "one_sided": True,
            "kappa_volume": None,
        }
    )
    return directions, frozen


def candidate_for(*, rho, direction, amplitude, move_limit, active, frozen):
    box_low = np.clip(rho - move_limit, 0.0, 1.0)
    box_high = np.clip(rho + move_limit, 0.0, 1.0)
    candidate = np.clip(
        rho + amplitude * direction["scale"] * direction["delta"], box_low, box_high
    )
    candidate[~active] = rho[~active]
    if direction["apply_freeze"]:
        candidate[frozen] = rho[frozen]
    return candidate, box_low, box_high


def direction_verdict(records: list[dict]) -> str:
    if any(not record["constraints_ok"] for record in records):
        return "infeasible"
    flags = [record["detectable_improvement"] for record in records]
    if all(flags):
        return "detectable_improvement"
    if not any(flags):
        return "below_threshold"
    return "amplitude_inconsistent"


def run() -> dict:
    manifest, m5, rho = verify_preconditions()
    OUTPUT.mkdir(parents=True)
    shutil.copytree(ROOT / m5["template_trial"]["path"], OUTPUT / "template_trial")

    grid = load_fixed_grid_density_state(ROOT / m5["canonical_grid"]["path"])
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    level = manifest["fixed_configuration"]["level"]
    transform = _transform_for(m5, active, level)
    spec = load_problem_spec(ROOT / m5["problem_spec"]["path"])
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["fixed_configuration"]["v_max_projected"])
    )

    parent_a = _oracle(m5, transform, compiled, OUTPUT / "parent_repeat_a/runs").evaluate_parent(rho)
    parent_b = _oracle(m5, transform, compiled, OUTPUT / "parent_repeat_b/runs").evaluate_parent(rho)
    run_a = run_evidence(parent_a)
    run_b = run_evidence(parent_b)
    if run_a.get("reused") or run_b.get("reused"):
        raise SystemExit("parent repeat must use independent fresh runs")
    if bool(parent_a.primal_converged) is not True or bool(parent_b.primal_converged) is not True:
        raise SystemExit("parent repeat did not converge")
    j_parent = float(parent_a.objective)
    df_parent = float(run_a["downforce_coefficient"])
    spread_j = abs(j_parent - float(parent_b.objective))
    spread_df = abs(df_parent - float(run_b["downforce_coefficient"]))
    _parent_objective, grad_j = canonical_objective_from(parent_a)
    indicator = np.zeros_like(rho, dtype=np.float64)
    indicator[active] = 1.0 / float(np.count_nonzero(active))
    grad_v = transform.pullback_from_projected(rho, indicator)

    move_limit = float(level["move_limit"])
    target = manifest["fixed_configuration"]["registered_target"]
    tolerance = manifest["fixed_configuration"]["volume_tolerance"]
    v_max = manifest["fixed_configuration"]["v_max_projected"]
    threshold = manifest["noise"]["improvement_threshold_objective"]
    directions, frozen = build_directions(
        transform=transform,
        rho=rho,
        grad_j=grad_j,
        grad_v=grad_v,
        active=active,
        move_limit=move_limit,
        target=target,
        volume_tolerance=tolerance,
    )
    phi_parent = float(_projected_field(transform, rho)[active].mean())
    oracle_dir = _oracle(m5, transform, compiled, OUTPUT / "directions/runs")

    direction_records = []
    registered_specs = manifest["directions"]
    if [spec["id"] for spec in registered_specs] != [entry["id"] for entry in directions]:
        raise SystemExit("constructed directions differ from the registered manifest")
    for direction, spec in zip(directions, registered_specs, strict=True):
        records = []
        delta = direction["delta"]
        for amplitude in spec["amplitudes"]:
            candidate, box_low, box_high = candidate_for(
                rho=rho,
                direction=direction,
                amplitude=float(amplitude),
                move_limit=move_limit,
                active=active,
                frozen=frozen,
            )
            actual_delta = candidate - rho
            phi_candidate = float(_projected_field(transform, candidate)[active].mean())
            mask_drift = (
                float(np.max(np.abs(candidate[~active] - rho[~active])))
                if bool((~active).any())
                else 0.0
            )
            box_violation = float(
                max(0.0, np.max(np.maximum(candidate - box_high, box_low - candidate)))
            )
            result = oracle_dir.evaluate_values(candidate)
            run = run_evidence(result)
            improvement_j = j_parent - float(result.objective)
            improvement_df = float(run["downforce_coefficient"]) - df_parent
            constraints_ok = bool(
                result.primal_converged
                and run.get("solver_status") == "converged"
                and phi_candidate <= v_max
                and mask_drift <= MASK_TOLERANCE
                and box_violation <= MASK_TOLERANCE
            )
            detectable = bool(
                improvement_j > max(threshold, spread_j)
                and improvement_df > max(threshold, spread_df)
            )
            records.append(
                {
                    "amplitude": float(amplitude),
                    "delta_inf_norm": float(np.max(np.abs(actual_delta))),
                    "delta_l2_norm": float(np.linalg.norm(actual_delta)),
                    "phi_candidate": phi_candidate,
                    "projected_volume_delta": phi_candidate - phi_parent,
                    "gradJ_dot_delta": float(np.dot(grad_j, actual_delta)),
                    "gradV_dot_delta": float(np.dot(grad_v, actual_delta)),
                    "mask_drift_max": mask_drift,
                    "move_box_violation_max": box_violation,
                    "constraints_ok": constraints_ok,
                    "canonical_objective": float(result.objective),
                    "downforce_coefficient": float(run["downforce_coefficient"]),
                    "improvement_canonical": improvement_j,
                    "improvement_downforce": improvement_df,
                    "detectable_improvement": detectable,
                    "trial_run": run,
                }
            )
            print(
                json.dumps(
                    {
                        "direction": direction["id"],
                        "amplitude": amplitude,
                        "phi": round(phi_candidate, 6),
                        "J": round(float(result.objective), 9),
                        "df": round(float(run["downforce_coefficient"]), 9),
                        "imp_J": improvement_j,
                        "imp_df": improvement_df,
                        "detectable": detectable,
                        "constraints_ok": constraints_ok,
                    }
                ),
                flush=True,
            )
        direction_records.append(
            {
                "id": direction["id"],
                "one_sided": direction["one_sided"],
                "path_b_qualified_aspiration": not direction["one_sided"],
                "kappa_volume": direction["kappa_volume"],
                "delta_inf_norm": float(np.max(np.abs(delta))),
                "delta_l2_norm": float(np.linalg.norm(delta)),
                "gradJ_dot_delta": float(np.dot(grad_j, delta)),
                "gradV_dot_delta": float(np.dot(grad_v, delta)),
                "records": records,
                "verdict": direction_verdict(records),
            }
        )

    new_primals = 2 + sum(len(entry["records"]) for entry in direction_records)
    summary = {
        "parent_repeat": {
            "canonical_objective_a": j_parent,
            "canonical_objective_b": float(parent_b.objective),
            "downforce_a": df_parent,
            "downforce_b": float(run_b["downforce_coefficient"]),
            "spread_canonical": spread_j,
            "spread_downforce": spread_df,
        },
        "direction_verdicts": {entry["id"]: entry["verdict"] for entry in direction_records},
        "any_detectable_improvement": any(
            entry["verdict"] == "detectable_improvement" for entry in direction_records
        ),
        "new_primals_used": new_primals,
        "budget_max_new_primals": manifest["budget"]["max_new_primals"],
        "budget_respected": new_primals <= manifest["budget"]["max_new_primals"],
    }
    outcome = {
        "kind": "pq3_3b_d1_discriminant_outcome",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(MANIFEST)},
        "output_directory": str(OUTPUT.relative_to(ROOT)),
        "stopped_rho_sha256": _array_sha256(rho),
        "level": level["name"],
        "parent_repeat_runs": {"a": run_a, "b": run_b},
        "directions": direction_records,
        "summary": summary,
        "claims_supported": [
            "the registered bounded directions were measured with fresh real primals under the registered thresholds",
            "parent repeat spread and per-direction detectability are recorded",
        ],
        "claims_not_supported": [
            "no convergence or KKT stationarity conclusion from a finite direction set",
            "no acceptance, level resume, b16 transition or Stage S qualification",
        ],
    }
    if OUTCOME.exists():
        raise SystemExit("D1 outcome already exists; refusing to overwrite")
    OUTCOME.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT / "outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b D1 bounded discriminant")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--manifest-sha", required=True)
    args = parser.parse_args()
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if args.manifest_sha != sidecar:
        raise SystemExit("--manifest-sha does not match the registered sidecar")
    if args.verify_preconditions:
        manifest, _m5, _rho = verify_preconditions()
        print(json.dumps({"status": "preconditions_ok", "manifest": manifest["kind"]}))
    elif args.run:
        run()
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
