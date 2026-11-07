"""Runner result/infrastructure boundaries using synthetic files and processes."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/topo2d00"))
import collect_rans as C
import run_rans as R
import t2d_multibody_case as M


@pytest.fixture
def driver(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "output"
    geometry_path = source / "geometry/E1_sharp.json"
    geometry_path.parent.mkdir(parents=True)
    a = np.linspace(0, 2*np.pi, 201)
    points = np.column_stack((.01*np.cos(a), .11+.01*np.sin(a)))
    points[-1] = points[0]
    geometry_path.write_text(json.dumps({"config": "E1_sharp", "elements": [
        {"name": "main", "te_kind": "sharp", "points_m": points.tolist()}]}))
    (output / "work").mkdir(parents=True)
    spec = {**C.expected_runs()[0], "mode": "production", "iters": 5000, "cont_iters": None,
            "case_cap_s": 9000, "geometry_file": "geometry/E1_sharp.json",
            "geometry_sha256": C.sha256(geometry_path), "height_m": .1,
            "elements": [{"name": "main", "patch": "airfoil"}]}
    state = SimpleNamespace(spec=spec, source=source, output=output, geometry_path=geometry_path,
                            clock=0., calls=[], commands=[], generator_rc=0, generator_timeout=False,
                            manifest_changes={}, results={}, stage_error=None, deadline_stage=None,
                            nonfinite=False, change_mesh=False, continuation=False)
    inherited = R.inherited_runner()

    def generate(command, **kwargs):
        state.commands.append(command)
        if state.generator_timeout:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        case = Path(command[command.index("--out")+1])
        case.mkdir(parents=True)
        (case / "mesh.msh").write_text("synthetic mesh\n")
        manifest = {"geometry_sha256": spec["geometry_sha256"], "n_layers": spec.get("n_layers", 4),
                    "convergence": C.CONVERGENCE, "mesh_quality_failures": [],
                    "mesh_msh_sha256": C.sha256(case / "mesh.msh"),
                    "height_m": .1, "h_over_c1": .1/C.T.CHORD, "h_over_c": .1/.380}
        if "boundary_layer_plan_sha256" in spec:
            manifest["boundary_layer_plan_sha256"] = spec["boundary_layer_plan_sha256"]
        manifest.update(state.manifest_changes)
        (case / "case_manifest.json").write_text(json.dumps(manifest))
        return SimpleNamespace(returncode=state.generator_rc, stdout="synthetic generation\n", stderr="")

    def timed(stage, command, case, timeout):
        state.calls.append(stage)
        if state.stage_error:
            raise state.stage_error
        if stage == "gmshToFoam":
            boundary = case / "constant/polyMesh/boundary"
            boundary.parent.mkdir(parents=True)
            boundary.write_text("\n".join(f"{p} {{ type patch; }}" for p in ("airfoil", "front", "back", "ground")))
        elif stage == "checkMesh":
            (case / "log.checkMesh").write_text("cells: 2000\nMesh OK.\n")
        elif state.nonfinite or state.continuation:
            for obj in ("forceCoeffs", "forceCoeffs_airfoil"):
                path = case / "postProcessing" / obj / "0/coefficient.dat"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Time Cd Cl\n" + ("1 .1 nan\n" if state.nonfinite else "1 .1 2\n2 .1 2\n"))
        if state.change_mesh and stage == "simpleFoam":
            (case / "mesh.msh").write_text("changed after checkMesh\n")
        if state.deadline_stage == stage:
            state.clock = 10001.
            if stage == "checkMesh":
                (case / "log.checkMesh").write_text("cells: 2000\n")
        return {"stage": stage, "returncode": 0, "timed_out": False, "wall_s": .1, **state.results.get(stage, {})}

    monkeypatch.setattr(R.subprocess, "run", generate)
    monkeypatch.setattr(R, "time", SimpleNamespace(monotonic=lambda: state.clock))
    helper = SimpleNamespace(timed_run=timed, parse_check_mesh=inherited.parse_check_mesh,
                             parse_solver=inherited.parse_solver, _continue=lambda *args: None)
    state.run = lambda: R.run_case(spec, source, output, 10000., helper)
    return state


@pytest.mark.parametrize("failure", ["source_geometry", "layer_plan_file", "layer_geometry", "layer_count", "manifest_geometry", "policy", "n_layers", "manifest_mesh", "manifest_layer_plan"])
def test_integrity_failures_are_runner_exceptions(driver, failure):
    if failure == "source_geometry":
        driver.spec["geometry_sha256"] = "f"*64
    elif failure in ("layer_plan_file", "layer_geometry", "layer_count", "manifest_layer_plan"):
        plan = M.boundary_layer_plan({"E1_sharp": driver.geometry_path}, require_complete=False)
        if failure == "layer_geometry":
            plan["geometry_sha256"]["E1_sharp"] = "f"*64
        plan_path = driver.source / "boundary_layers.json"
        plan_path.write_text(json.dumps(plan, sort_keys=True, separators=(",", ":")))
        driver.spec.update(boundary_layer_plan_file=plan_path.name, boundary_layer_plan_sha256=C.sha256(plan_path),
                           n_layers=plan["families"]["fine30"]["n_layers"])
        if failure == "layer_plan_file":
            driver.spec["boundary_layer_plan_sha256"] = "f"*64
        elif failure == "layer_count":
            driver.spec["n_layers"] += 1
        elif failure == "manifest_layer_plan":
            driver.manifest_changes["boundary_layer_plan_sha256"] = "f"*64
    elif failure == "manifest_geometry":
        driver.manifest_changes["geometry_sha256"] = "f"*64
    elif failure == "policy":
        driver.manifest_changes["convergence"] = {**C.CONVERGENCE, "tail_fraction": .3}
    elif failure == "manifest_mesh":
        driver.manifest_changes["mesh_msh_sha256"] = "f"*64
    else:
        driver.spec["n_layers"] = 4
        driver.manifest_changes["n_layers"] = 3
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert result["error"]
    assert "simpleFoam" not in driver.calls
    path = driver.output / "cases" / R._spec_id(driver.spec) / "case_result.json"
    row = C.collect_case(path)
    assert row["convergence"]["raw_class"] == "INFRA_LOSS"
    assert not row["usable"]


@pytest.mark.parametrize("stage", ["generator", "gmshToFoam", "checkMesh"])
def test_completed_meshing_failures_remain_mesh_failed(driver, stage):
    if stage == "generator":
        driver.generator_rc = 1
    else:
        driver.results[stage] = {"returncode": 1}
    result = driver.run()
    assert result["status"] == "MESH_FAILED"
    assert result["failure_stage"] == stage
    assert "simpleFoam" not in driver.calls


@pytest.mark.parametrize("stage", ["gmshToFoam", "checkMesh", "simpleFoam"])
def test_session_deadline_interruptions_are_infrastructure(driver, stage):
    # The process result explicitly records interruption. In particular, an
    # incomplete checkMesh log must not overwrite the infrastructure status.
    driver.deadline_stage = stage
    driver.results[stage] = {"returncode": -9, "timed_out": True}
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert result["failure_stage"] == stage
    assert "deadline" in result["error"].lower()
    if stage != "simpleFoam":
        assert not result.get("mesh_only_stage", {}).get("passed", False)


def test_generator_timeout_is_infrastructure(driver):
    driver.generator_timeout = True
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert result["failure_stage"] == "generator"


def test_session_deadline_interrupting_continuation_is_infrastructure(driver, monkeypatch):
    driver.spec["cont_iters"] = 15000
    driver.continuation = True
    driver.deadline_stage = "simpleFoam_cont"
    driver.results["simpleFoam_cont"] = {"returncode": -9, "timed_out": True}
    monkeypatch.setattr(C, "cl_summary", lambda history: {"cl_plateau": False})
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert result["failure_stage"] == "simpleFoam_cont"
    assert "deadline" in result["error"].lower()
    assert driver.calls[-1] == "simpleFoam_cont"


def test_unstarted_time_budget_record_retains_declared_height(driver):
    driver.clock = 9501.
    result = driver.run()
    assert result["status"] == "NOT_RUN_TIME_BUDGET"
    assert result["height_m"] == .1
    path = driver.output / "cases" / R._spec_id(driver.spec) / "case_result.json"
    assert C.collect_case(path)["convergence"]["raw_class"] == "INFRA_LOSS"
    assert not driver.commands


@pytest.mark.parametrize("stage", ["gmshToFoam", "checkMesh"])
def test_mesh_stage_timeout_without_a_completed_result_is_infrastructure(driver, stage):
    driver.results[stage] = {"returncode": -9, "timed_out": True}
    assert driver.run()["status"] == "RUNNER_EXCEPTION"


def test_unexpected_mesh_infrastructure_error_is_not_a_mesh_result(driver):
    driver.stage_error = OSError("cannot launch process")
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert "cannot launch process" in result["error"]


def test_nonfinite_coefficients_remain_diverged_at_solver_case_cap(driver):
    driver.nonfinite = True
    driver.results["simpleFoam"] = {"returncode": -9, "timed_out": True}
    assert driver.run()["status"] == "SOLVER_DIVERGED"


def test_mesh_integrity_failure_takes_precedence_over_nonfinite_coefficients(driver):
    driver.change_mesh = driver.nonfinite = True
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert "mesh changed" in result["error"]


def test_history_sha_failure_during_continuation_check_is_infrastructure(driver, monkeypatch):
    driver.spec["cont_iters"] = 15000
    driver.continuation = True
    read_history, calls = C.read_history, []

    def changed_history(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError("coefficient SHA mismatch: synthetic concurrent corruption")
        return read_history(*args, **kwargs)

    monkeypatch.setattr(C, "read_history", changed_history)
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert "SHA mismatch" in result["error"]
    assert "simpleFoam_cont" not in driver.calls


@pytest.mark.parametrize("height_m", [.08, .1])
def test_scene_height_is_bound_and_propagated_without_a_default(driver, height_m):
    geometry = json.loads(driver.geometry_path.read_text())
    for point in geometry["elements"][0]["points_m"]:
        point[1] += height_m-.1
    driver.geometry_path.write_text(json.dumps(geometry))
    driver.spec.update(mode="mesh-only", iters=200, height_m=height_m,
                       geometry_sha256=C.sha256(driver.geometry_path))
    driver.manifest_changes.update(height_m=height_m, h_over_c1=height_m/C.T.CHORD, h_over_c=height_m/.380)
    result = driver.run()
    assert result["status"] == "MESH_OK"
    assert result["height_m"] == height_m
    assert result["h_over_c1"] == pytest.approx(height_m/C.T.CHORD)
    assert result["h_over_c"] == pytest.approx(height_m/.380)
    command = driver.commands[0]
    assert float(command[command.index("--expected-height-m")+1]) == height_m


def test_declared_height_mismatch_is_refused_before_meshing(driver):
    driver.spec["height_m"] = .08
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert "height" in result["error"].lower()
    assert not driver.commands


def test_production_without_declared_height_is_refused(driver):
    driver.spec.pop("height_m")
    result = driver.run()
    assert result["status"] == "RUNNER_EXCEPTION"
    assert "height" in result["error"].lower()
    assert not driver.commands
