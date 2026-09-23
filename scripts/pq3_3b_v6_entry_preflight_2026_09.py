"""PQ3.3b v6 entry preflight (D3): two bounded one-step qualifications.

Stage A: one inequality-policy step at the v5 stopped b=8 parent (fresh real
primal for every bracket pair endpoint and the trial; the registered thresholds
are not changed).

Stage B: b=16 level transition on Stage A's accepted rho, the projected-volume
drop measurement, the Phase 1 target restoration to the formation target
0.018, and one inequality-policy step at b=16.

Both stages must pass before any long v6 campaign could be started; the long
campaign remains explicitly out of scope and unstarted. The artifact is
append-only.
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
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_inequality_policy import evaluate_phase2_inequality  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import phi_of, run_evidence, run_restoration, sha256_array  # noqa: E402

ROOT_MANIFESTS = ROOT / "docs/evidence"
D2_MANIFEST = ROOT_MANIFESTS / "pq3_3b_d2_change_manifest_2026_09.json"
V6_MANIFEST = ROOT_MANIFESTS / "pq3_3b_campaign_manifest_v6_2026_09.json"
D1_OUTCOME = ROOT_MANIFESTS / "pq3_3b_d1_discriminant_outcome_2026_09.json"
OUTPUT = ROOT / "work/pq3_3b_v6_entry_preflight"
ARTIFACT = ROOT_MANIFESTS / "pq3_3b_v6_entry_preflight_2026_09.json"
WORK = ROOT / "work/df2_fd_refresh"
SHAPE = (60, 32, 24)
SPACING_M = 0.05


def verify_preconditions() -> tuple[dict, dict]:
    for manifest in (D2_MANIFEST, V6_MANIFEST):
        if not manifest.is_file():
            raise SystemExit(f"registration missing: {manifest}")
        sidecar = manifest.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
        if ca.sha256_file(manifest) != sidecar:
            raise SystemExit(f"sidecar mismatch: {manifest}")
    d2 = ca.load_json(D2_MANIFEST)
    v6 = ca.load_json(V6_MANIFEST)
    if ca.sha256_file(D1_OUTCOME) != d2["discriminant_evidence"]["sha256"]:
        raise SystemExit("D1 outcome hash mismatch")
    if v6["change_manifest_d2"]["sha256"] != ca.sha256_file(D2_MANIFEST):
        raise SystemExit("v6 manifest does not reference the registered D2 change manifest")
    if ca.sha256_file(__file__) != v6["entry_preflight"]["script_sha256"]:
        raise SystemExit("entry preflight script hash mismatch")
    rho_ref = v6["input_stop_state"]
    rho_path = ROOT / rho_ref["rho_path"]
    if ca.sha256_file(rho_path) != rho_ref["rho_file_sha256"]:
        raise SystemExit("stopped rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != rho_ref["rho_sha256"]:
        raise SystemExit("stopped rho array hash mismatch")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != v6["source_tree_python_sha256"]:
        raise SystemExit("src/cfd_sdf tree differs from the v6 registration")
    if OUTPUT.exists() or ARTIFACT.exists():
        raise SystemExit("entry preflight artifacts already exist")
    return d2, v6


def _trial(oracle):
    def evaluate(candidate):
        result = oracle.evaluate_values(candidate)
        return result, run_evidence(result)

    return evaluate


def _oracle(v6: dict, transform, compiled, run_root: Path):
    adapter = OpenFoamOracle(
        OpenFoamOracleConfig(
            work_root=WORK,
            canonical_topology_state_json=ROOT / v6["registered_inputs"]["canonical_grid"]["path"],
            template_parent=ROOT / v6["registered_inputs"]["template_parent"]["path"],
            template_trial=OUTPUT / "template_trial",
            flow_case_id="straight",
            responses=("downforce",),
            run_root=run_root,
            timeout_seconds=1800,
            docker_image=v6["openfoam_image"],
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


def run() -> dict:
    d2, v6 = verify_preconditions()
    OUTPUT.mkdir(parents=True)
    shutil.copytree(ROOT / v6["registered_inputs"]["template_trial"]["path"], OUTPUT / "template_trial")
    grid = load_fixed_grid_density_state(ROOT / v6["registered_inputs"]["canonical_grid"]["path"])
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    forbidden = np.asarray(arrays["forbidden_mask"]) > 0
    fixed = np.asarray(arrays["fixed_solid_mask"]) > 0
    spec = load_problem_spec(ROOT / v6["registered_inputs"]["problem_spec"]["path"])
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", v6["v_max_projected"])
    )
    rho_stop = np.load(ROOT / v6["input_stop_state"]["rho_path"], allow_pickle=False)
    bracket = BracketSpec(
        epsilon=v6["path_b"]["epsilon"], noise_floor_abs=v6["path_b"]["noise_floor_abs"]
    )
    ladder = tuple(v6["phase2_policy"]["alpha_ladder"])

    # ---------------- Stage A: one inequality step at the b=8 stop point
    level_a = v6["levels"][1]
    transform_a = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=v6["filter_radius_m"]),
        projection=TanhProjection(level_a["b"], v6["projection_eta"]),
        ramp=RampInterpolation(level_a["q"]),
    )
    oracle_a = _oracle(v6, transform_a, compiled, OUTPUT / "stage_a/runs")
    parent_a = oracle_a.evaluate_parent(rho_stop)
    parent_a_run = run_evidence(parent_a)
    parent_a_df = float(parent_a_run["downforce_coefficient"])
    payload_a, accepted_a = evaluate_phase2_inequality(
        transform=transform_a,
        parent_result=parent_a,
        rho_parent=rho_stop,
        parent_downforce=parent_a_df,
        move_limit=float(level_a["move_limit"]),
        ladder=ladder,
        v_max=v6["v_max_projected"],
        objective_noise_threshold=v6["noise_thresholds"]["objective"],
        downforce_noise_threshold=v6["noise_thresholds"]["downforce"],
        bracket_spec=bracket,
        evaluate_values=oracle_a.evaluate_values,
        evaluate_trial=_trial(oracle_a),
        return_rho=True,
        min_update_inf_norm=d2["change"]["min_corrected_update_inf_norm"],
        extractability_fraction=d2["change"]["extractability_fraction"],
    )
    stage_a = {
        "level": level_a["name"],
        "parent_run": parent_a_run,
        "phase2": payload_a,
        "accepted_rho_sha256": payload_a["corrected_rho_sha256"] if accepted_a is not None else None,
        "pass": bool(payload_a["successful"]),
    }
    if accepted_a is None:
        artifact = _finalize(v6, d2, stage_a, None, bool(payload_a["successful"]))
        return artifact

    # ---------------- Stage B: b=16 transition + restoration + one step
    level_b = v6["levels"][2]
    transform_b = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=v6["filter_radius_m"]),
        projection=TanhProjection(level_b["b"], v6["projection_eta"]),
        ramp=RampInterpolation(level_b["q"]),
    )
    oracle_b = _oracle(v6, transform_b, compiled, OUTPUT / "stage_b/runs")
    phi_before = phi_of(transform_b, accepted_a, active)
    restoration, restored = run_restoration(
        transform_b,
        oracle_b,
        active,
        forbidden,
        fixed,
        accepted_a,
        float(level_b["move_limit"]),
        level_b["name"],
    )
    stage_b: dict = {
        "level": level_b["name"],
        "phi_before_restoration": float(phi_before),
        "phi_drop_vs_formation_target": float(v6["registered_target"] - phi_before),
        "restoration": restoration,
    }
    if not restoration["reached_target"] or not all(step["accepted"] for step in restoration["steps"]):
        stage_b["phase2"] = None
        stage_b["pass"] = False
        artifact = _finalize(v6, d2, stage_a, stage_b, False)
        return artifact
    parent_b = oracle_b.evaluate_parent(restored)
    parent_b_run = run_evidence(parent_b)
    payload_b, accepted_b = evaluate_phase2_inequality(
        transform=transform_b,
        parent_result=parent_b,
        rho_parent=restored,
        parent_downforce=float(parent_b_run["downforce_coefficient"]),
        move_limit=float(level_b["move_limit"]),
        ladder=ladder,
        v_max=v6["v_max_projected"],
        objective_noise_threshold=v6["noise_thresholds"]["objective"],
        downforce_noise_threshold=v6["noise_thresholds"]["downforce"],
        bracket_spec=bracket,
        evaluate_values=oracle_b.evaluate_values,
        evaluate_trial=_trial(oracle_b),
        return_rho=True,
        min_update_inf_norm=d2["change"]["min_corrected_update_inf_norm"],
        extractability_fraction=d2["change"]["extractability_fraction"],
    )
    stage_b.update(
        {
            "parent_run": parent_b_run,
            "phase2": payload_b,
            "accepted_rho_sha256": payload_b["corrected_rho_sha256"] if accepted_b is not None else None,
            "pass": bool(payload_b["successful"]),
        }
    )
    artifact = _finalize(v6, d2, stage_a, stage_b, bool(payload_b["successful"]))
    return artifact


def _finalize(v6: dict, d2: dict, stage_a: dict, stage_b: dict | None, stage_b_pass: bool) -> dict:
    entry_pass = bool(stage_a["pass"] and stage_b_pass and stage_b is not None)
    artifact = {
        "kind": "pq3_3b_v6_entry_preflight",
        "schema_version": 1,
        "campaign_manifest_v6": {
            "path": str(V6_MANIFEST.relative_to(ROOT)),
            "sha256": ca.sha256_file(V6_MANIFEST),
        },
        "change_manifest_d2": {
            "path": str(D2_MANIFEST.relative_to(ROOT)),
            "sha256": ca.sha256_file(D2_MANIFEST),
        },
        "discriminant_outcome_d1": {
            "path": str(D1_OUTCOME.relative_to(ROOT)),
            "sha256": ca.sha256_file(D1_OUTCOME),
        },
        "stage_a_b8_stop_point": stage_a,
        "stage_b_b16_transition": stage_b,
        "summary": {
            "stage_a_pass": bool(stage_a["pass"]),
            "stage_b_pass": bool(stage_b_pass),
            "entry_preflight_pass": entry_pass,
            "long_campaign_started": False,
        },
        "claims_supported": [
            "one inequality-policy step was qualified at the v5 stopped b=8 parent with fresh real primals",
            "the b=16 transition and formation-target restoration were measured under the registered rules",
        ],
        "claims_not_supported": [
            "the long v6 campaign is not started and no terminal or Stage S qualification is included",
        ],
    }
    if ARTIFACT.exists():
        raise SystemExit("entry preflight artifact already exists")
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v6 entry preflight")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.verify_preconditions:
        d2, v6 = verify_preconditions()
        print(json.dumps({"status": "preconditions_ok", "policy": d2["change"]["id"]}))
    elif args.run:
        run()
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
