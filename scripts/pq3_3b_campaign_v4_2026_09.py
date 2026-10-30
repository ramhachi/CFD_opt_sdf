"""Registered PQ3.3b two-phase campaign. Importing or verifying never runs CFD.

The long campaign starts only with --run and the exact manifest SHA-256. Each
accepted objective state is checkpointed. Resume reads only a verified accepted
checkpoint and refuses incomplete solver cases for explicit recovery.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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
from cfd_sdf.phase2_policy import evaluate_phase2  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import (  # noqa: E402
    REGISTERED_TARGET, STEP_CAP, V_MAX_PROJECTED,
    phi_of, run_evidence, run_restoration, sha256_array,
)

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v4_2026_09.json"
WORK = ROOT / "work/df2_fd_refresh"
SHAPE = (60, 32, 24)
SPACING_M = 0.05


def _path(ref: dict) -> Path:
    value = Path(ref["path"])
    return value if value.is_absolute() else ROOT / value


def _verify_ref(ref: dict, *, directory: bool = False) -> Path:
    path = _path(ref)
    actual = ca.tree_sha256(path) if directory and path.is_dir() else ca.sha256_file(path) if path.is_file() else None
    if actual != ref.get("sha256"):
        raise ValueError(f"registered input missing or SHA-256 mismatched: {path}")
    return path


def verify_preconditions(manifest_sha: str, *, resume: bool = False) -> tuple[dict, Path]:
    """Verify the complete immutable registration without creating output."""
    ca.assert_manifest_sha(MANIFEST, manifest_sha)
    if MANIFEST.with_suffix(".json.sha256").read_text().strip() != manifest_sha:
        raise ValueError("manifest sidecar does not match the pinned SHA-256")
    manifest = ca.load_json(MANIFEST)
    if manifest.get("status") != ca.STATUS_AWAITING_GO or manifest.get("schema_version") != 4:
        raise ValueError("campaign manifest is not registered for a go decision")
    if manifest["phase1_policy"]["id"] != "projected-volume-restoration-oc":
        raise ValueError("unregistered Phase 1 backend")
    if (manifest["registered_target"] != REGISTERED_TARGET
        or manifest["v_max_projected"] != V_MAX_PROJECTED
        or manifest["restoration_step_cap"] != STEP_CAP):
        raise ValueError("campaign restoration constants differ from qualified v6 code")
    phase2 = manifest["phase2_policy"]
    if phase2["id"] != "volume-corrected-objective-oc" or phase2["freeze_exact_box_faces"] is not True:
        raise ValueError("unregistered Phase 2 boundary policy")
    for key in ("input_checkpoint", "problem_spec", "canonical_grid", "source_grid", "preflight_v6", "preflight_script", "noise_calibration"):
        _verify_ref(manifest[key])
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise ValueError("campaign source tree SHA-256 mismatch")
    _verify_ref(manifest["runner_source"])
    for key in ("template_parent", "template_trial", "solver_controls"):
        _verify_ref(manifest[key], directory=True)
    checkpoint = ca.load_json(_path(manifest["input_checkpoint"]))
    input_rho = np.asarray(checkpoint["rho"], dtype=np.float64)
    if input_rho.size != int(np.prod(SHAPE)) or sha256_array(input_rho) != manifest["input_rho_sha256"]:
        raise ValueError("checkpoint rho does not match registered input rho")
    spec = load_problem_spec(_path(manifest["problem_spec"]))
    compiled = compile_problem(spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]))
    if ca.compiled_problem_sha256(compiled) != manifest["compiled_problem_hash"]:
        raise ValueError("compiled problem hash mismatch")
    if spec.objectives[0].sense != "maximize" or manifest["objective"]["canonical"] != "J = -downforce":
        raise ValueError("canonical objective contract mismatch")
    evidence = ca.load_json(_path(manifest["preflight_v6"]))
    if evidence.get("kind") != "pq3_3b_preflight_v6" or evidence.get("summary", {}).get("preflight_pass") is not True:
        raise ValueError("qualified v6 preflight evidence is missing")
    if len(evidence.get("levels", [])) != len(manifest["levels"]) or any(
        level.get("objective_accepted") is None for level in evidence["levels"]
    ):
        raise ValueError("v6 preflight lacks an objective-accepted level")
    for registered, measured in zip(manifest["levels"], evidence["levels"], strict=True):
        if (registered["name"], registered["b"], registered["q"], registered["move_limit"]) != (
            measured["level"], measured["b"], measured["q"], measured["move_limit"]
        ):
            raise ValueError("campaign schedule differs from qualified preflight")
    if manifest["reject_stop_count"] != 1:
        raise ValueError("runner supports only fail-closed first all-alpha rejection stop")
    noise = ca.load_json(_path(manifest["noise_calibration"]))
    if noise.get("independent_runs") is not True:
        raise ValueError("noise calibration did not use independent runs")
    if manifest["noise_thresholds"] != {"objective": noise["objective_noise_threshold"], "downforce": noise["downforce_noise_threshold"]}:
        raise ValueError("noise thresholds disagree with the registered evidence")
    image = subprocess.run(
        ["docker", "image", "inspect", manifest["openfoam_image"], "--format", "{{.Id}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if image != manifest["openfoam_image_id"]:
        raise ValueError("OpenFOAM image ID differs from the registered image")
    output = ROOT / manifest["output_directory"]
    if resume:
        if not output.is_dir():
            raise ValueError("resume output directory does not exist")
        incomplete = [case for root in (output / "runs", output / "terminal_independent")
                      if root.is_dir() for case in root.glob("*/case")
                      if not (case / "fixed_grid_primal_summary.json").is_file()]
        if incomplete:
            raise ValueError(f"incomplete solver cases require recovery before resume: {incomplete}")
        metadata = ca.load_json(output / "campaign_meta.json")
        if metadata.get("manifest_sha256") != manifest_sha or metadata.get("status") != "running":
            raise ValueError("resume manifest or campaign status mismatch")
        first = ca.load_json(output / "checkpoints/state_0000.json")
        if first.get("rho_sha256") != manifest["input_rho_sha256"]:
            raise ValueError("resume initial rho differs from registration")
        _load_checkpoint(output)
    else:
        ca.assert_fresh_output_directory(output)
    return manifest, output


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _append_event(output: Path, payload: dict) -> None:
    with (output / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _checkpoint(output: Path, state: dict, rho: np.ndarray) -> None:
    """Write accepted rho first, then state, then atomically advance latest."""
    checkpoint_dir = output / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    index = int(state["checkpoint_index"])
    rho_path = checkpoint_dir / f"rho_{index:04d}.npy"
    state_path = checkpoint_dir / f"state_{index:04d}.json"
    if rho_path.exists() or state_path.exists():
        raise ValueError("checkpoint index already exists; refusing to overwrite")
    previous_state_sha = None
    previous_rho_sha = None
    pointer_path = output / "latest.json"
    if pointer_path.exists():
        pointer = ca.load_json(pointer_path)
        previous_state_sha = pointer["state_sha256"]
        previous = ca.load_json(output / pointer["state_path"])
        previous_rho_sha = previous["rho_sha256"]
    with rho_path.open("wb") as handle:
        np.save(handle, np.asarray(rho, dtype=np.float64), allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    state = {**state, "rho_path": str(rho_path.relative_to(output)), "rho_file_sha256": ca.sha256_file(rho_path), "rho_sha256": sha256_array(rho),
             "previous_state_sha256": previous_state_sha, "previous_rho_sha256": previous_rho_sha}
    _write_json_atomic(state_path, state)
    _write_json_atomic(pointer_path, {
        "state_path": str(state_path.relative_to(output)),
        "state_sha256": ca.sha256_file(state_path),
    })


def _load_checkpoint(output: Path) -> tuple[dict, np.ndarray]:
    pointer = ca.load_json(output / "latest.json")
    state_path = output / pointer["state_path"]
    if ca.sha256_file(state_path) != pointer["state_sha256"]:
        raise ValueError("latest checkpoint state SHA-256 mismatch")
    latest_state = ca.load_json(state_path)
    current_hash = pointer["state_sha256"]
    current_index = int(latest_state["checkpoint_index"])
    latest_rho = None
    for index in range(current_index, -1, -1):
        path = output / "checkpoints" / f"state_{index:04d}.json"
        if ca.sha256_file(path) != current_hash:
            raise ValueError("checkpoint state lineage SHA-256 mismatch")
        state = ca.load_json(path)
        if state["checkpoint_index"] != index:
            raise ValueError("checkpoint index lineage mismatch")
        rho_path = output / state["rho_path"]
        if ca.sha256_file(rho_path) != state["rho_file_sha256"]:
            raise ValueError("checkpoint rho file SHA-256 mismatch")
        rho = np.load(rho_path, allow_pickle=False)
        if sha256_array(rho) != state["rho_sha256"]:
            raise ValueError("checkpoint rho array SHA-256 mismatch")
        if latest_rho is None:
            latest_rho = rho
        if index == 0:
            if state["previous_state_sha256"] is not None:
                raise ValueError("initial checkpoint has a predecessor")
        else:
            previous = ca.load_json(output / "checkpoints" / f"state_{index-1:04d}.json")
            if state["previous_rho_sha256"] != previous["rho_sha256"]:
                raise ValueError("checkpoint rho predecessor mismatch")
        current_hash = state["previous_state_sha256"]
    return latest_state, latest_rho


def _oracle(transform, compiled, manifest: dict, output: Path, run_root: Path):
    adapter = OpenFoamOracle(
        OpenFoamOracleConfig(
            work_root=WORK,
            canonical_topology_state_json=_path(manifest["canonical_grid"]),
            template_parent=_path(manifest["template_parent"]),
            template_trial=output / "template_trial",
            flow_case_id="straight",
            responses=("downforce",),
            run_root=run_root,
            timeout_seconds=1800,
            docker_image=manifest["openfoam_image"],
        ), transform,
    )
    return make_oracle_from_compiled(
        transform=transform, compiled=compiled,
        primal_evaluator=adapter.primal_evaluator,
        parent_evaluator=adapter.parent_evaluator,
        adjoint_evaluator=None,
    )


def run_campaign(manifest_sha: str, *, resume: bool = False) -> dict:
    manifest, output = verify_preconditions(manifest_sha, resume=resume)
    spec = load_problem_spec(_path(manifest["problem_spec"]))
    compiled = compile_problem(spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]))
    grid = load_fixed_grid_density_state(_path(manifest["canonical_grid"]))
    arrays = grid.arrays
    active = ((np.asarray(arrays["active_design_mask"]) > 0)
              & (np.asarray(arrays["allowed_mask"]) > 0)
              & ~(np.asarray(arrays["forbidden_mask"]) > 0)
              & ~(np.asarray(arrays["fixed_solid_mask"]) > 0))
    forbidden = np.asarray(arrays["forbidden_mask"]) > 0
    fixed = np.asarray(arrays["fixed_solid_mask"]) > 0
    if resume:
        state, rho = _load_checkpoint(output)
    else:
        output.mkdir(parents=True)
        shutil.copytree(_path(manifest["template_trial"]), output / "template_trial")
        _write_json_atomic(output / "campaign_meta.json", {"manifest_sha256": manifest_sha, "status": "running"})
        rho = np.asarray(ca.load_json(_path(manifest["input_checkpoint"]))["rho"], dtype=np.float64)
        state = {"checkpoint_index": 0, "level_index": 0, "accepted_count": 0, "metrics": [], "completed_levels": [], "phase1_done": False}
        _checkpoint(output, state, rho)
    bracket = BracketSpec(epsilon=manifest["path_b"]["epsilon"], noise_floor_abs=manifest["path_b"]["noise_floor_abs"])
    for level_index in range(state["level_index"], len(manifest["levels"])):
        level = manifest["levels"][level_index]
        transform = DesignTransform(
            shape=SHAPE, spacing_m=SPACING_M, active_mask=active,
            filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=manifest["filter_radius_m"]),
            projection=TanhProjection(level["b"], manifest["projection_eta"]),
            ramp=RampInterpolation(level["q"]),
        )
        oracle = _oracle(transform, compiled, manifest, output, output / "runs")
        if not state["phase1_done"]:
            phase1, restored = run_restoration(transform, oracle, active, forbidden, fixed, rho, level["move_limit"], level["name"])
            _append_event(output, {"kind": "restoration", "level": level["name"], "record": phase1})
            if not phase1["reached_target"] or not all(step["accepted"] for step in phase1["steps"]):
                return _stop(output, "restoration_failed", level["name"])
            rho = restored
        for attempt in range(state["accepted_count"], level["max_attempts"]):
            parent = oracle.evaluate_parent(rho)
            parent_run = run_evidence(parent)
            parent_downforce = float(parent_run["downforce_coefficient"])
            before = np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)

            def trial(candidate):
                result = oracle.evaluate_values(candidate)
                return result, run_evidence(result)

            payload, accepted = evaluate_phase2(
                transform=transform, parent_result=parent, rho_parent=rho,
                parent_downforce=parent_downforce, move_limit=level["move_limit"],
                ladder=tuple(manifest["phase2_policy"]["alpha_ladder"]),
                target=manifest["registered_target"], v_max=manifest["v_max_projected"],
                volume_tolerance=manifest["volume_tolerance"],
                objective_noise_threshold=manifest["noise_thresholds"]["objective"],
                downforce_noise_threshold=manifest["noise_thresholds"]["downforce"],
                bracket_spec=bracket, evaluate_values=oracle.evaluate_values,
                evaluate_trial=trial, return_rho=True, freeze_box_faces=True,
            )
            _append_event(output, {"kind": "objective_attempt", "level": level["name"], "attempt": attempt + 1, "input_rho_sha256": sha256_array(rho), "parent_run": parent_run, "phase2": payload})
            if accepted is None:
                return _stop(output, "objective_rejected", level["name"])
            candidate = payload["candidates"][-1]
            if not candidate["accepted"] or payload["corrected_rho_sha256"] != sha256_array(accepted):
                raise ValueError("Phase 2 acceptance or rho lineage mismatch")
            after = np.asarray(transform.forward(accepted).rho_projected, dtype=np.float64)
            metric = {
                "objective_delta_abs": float(parent.objective - candidate["trial_objective"]),
                "projected_field_mean_abs_delta": float(np.mean(np.abs(after[active] - before[active]))),
                "volume_residual": abs(phi_of(transform, accepted, active) - manifest["registered_target"]),
            }
            rho = accepted
            state = {**state, "checkpoint_index": state["checkpoint_index"] + 1,
                     "level_index": level_index, "accepted_count": state["accepted_count"] + 1,
                     "metrics": (state["metrics"] + [metric])[-manifest["convergence"]["window_accepted"]:],
                     "phase1_done": True, "last_trial_objective": candidate["trial_objective"],
                     "last_trial_downforce": candidate["trial_downforce"]}
            _checkpoint(output, state, rho)
            _append_event(output, {"kind": "objective_accepted", "level": level["name"], "rho_sha256": sha256_array(rho), "metric": metric})
            limits = manifest["convergence"]
            window = state["metrics"]
            converged = (state["accepted_count"] >= level["min_accepted_iterations"]
                         and len(window) == limits["window_accepted"]
                         and all(0 < item["objective_delta_abs"] <= limits["objective_delta_abs_max"]
                                 and item["projected_field_mean_abs_delta"] <= limits["projected_field_mean_abs_delta_max"]
                                 and item["volume_residual"] <= limits["volume_residual_max"]
                                 for item in window))
            if converged:
                _append_event(output, {"kind": "level_converged", "level": level["name"], "accepted_count": state["accepted_count"], "rho_sha256": sha256_array(rho)})
                state = {**state, "checkpoint_index": state["checkpoint_index"] + 1,
                         "level_index": level_index + 1, "accepted_count": 0, "metrics": [],
                         "completed_levels": state["completed_levels"] + [level["name"]], "phase1_done": False}
                _checkpoint(output, state, rho)
                break
        else:
            return _stop(output, "level_not_converged", level["name"])
    terminal_level = manifest["levels"][-1]
    terminal_transform = DesignTransform(
        shape=SHAPE, spacing_m=SPACING_M, active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=manifest["filter_radius_m"]),
        projection=TanhProjection(terminal_level["b"], manifest["projection_eta"]),
        ramp=RampInterpolation(terminal_level["q"]),
    )
    terminal_oracle = _oracle(terminal_transform, compiled, manifest, output, output / "terminal_independent")
    terminal = terminal_oracle.evaluate_values(rho)
    phi = phi_of(terminal_transform, rho, active)
    ca.assert_projected_volume_upper_bound(phi, manifest["v_max_projected"])
    terminal_run = run_evidence(terminal)
    if (not terminal.primal_converged
        or abs(float(terminal.objective) - float(state["last_trial_objective"])) > manifest["noise_thresholds"]["objective"]
        or abs(float(terminal_run["downforce_coefficient"]) - float(state["last_trial_downforce"])) > manifest["noise_thresholds"]["downforce"]):
        return _stop(output, "independent_terminal_response_mismatch", terminal_level["name"])
    result = {"status": "terminal_evaluated_not_stage_s_qualified", "rho_sha256": sha256_array(rho),
              "projected_volume": phi, "objective": float(terminal.objective), "run": terminal_run}
    _write_json_atomic(output / "terminal.json", result)
    _write_json_atomic(output / "campaign_meta.json", {"manifest_sha256": manifest_sha, "status": result["status"]})
    return result


def _stop(output: Path, reason: str, level: str) -> dict:
    meta = ca.load_json(output / "campaign_meta.json")
    _write_json_atomic(output / "campaign_meta.json", {**meta, "status": "blocked", "reason": reason, "level": level})
    return {"status": "blocked", "reason": reason, "level": level}


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v4 registered campaign")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--manifest-sha", required=True)
    args = parser.parse_args()
    if args.verify_preconditions:
        manifest, output = verify_preconditions(args.manifest_sha, resume=args.resume)
        print(json.dumps({"status": "preconditions_ok", "manifest": manifest["kind"], "output": str(output)}))
    elif args.run:
        print(json.dumps(run_campaign(args.manifest_sha, resume=args.resume)))
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
