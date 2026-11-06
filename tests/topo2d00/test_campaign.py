"""The scene path must preserve legacy campaigns and reject forged job identities."""
import csv
import json
from pathlib import Path
import shutil

import pytest

from cfd_harness import campaign_schema as SC
from cfd_harness import scene_campaign as S


def test_existing_campaign_still_uses_legacy_contract():
    root = Path(__file__).resolve().parents[2]
    campaign = SC.jload(root / "docs/harness/screen01_campaign.json")
    SC.validate_campaign(campaign)
    assert not S.is_scene_campaign(campaign)


def test_provider_pins_follow_gen01_placement_and_legacy_fallback(tmp_path):
    for name in ("Checkpoint.jl", "Force00.jl"):
        for folder in ("src", "gen01"):
            path = tmp_path / "julia/CFDSDFWaterLily" / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# independently pinned provider fixture\n")
        selected = S.source_paths(repo=tmp_path)
        assert f"julia/CFDSDFWaterLily/gen01/{name}" in selected
        assert f"julia/CFDSDFWaterLily/src/{name}" not in selected
        (tmp_path / "julia/CFDSDFWaterLily/gen01" / name).unlink()
        assert f"julia/CFDSDFWaterLily/src/{name}" in S.source_paths(repo=tmp_path)


def test_scene_wire_checks_hash_and_geometry_before_solver(tmp_path):
    from cfd_sdf.topo2d.geometry import build_scene
    scene = build_scene("E1", height_mm=100, dx_mm=223.4 / 120)
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(scene))
    sha = SC.sha256_path(path)
    assert S.scene_wire(path, sha).splitlines()[:2] == ["topo2d-scene-v1", "E1"]
    with pytest.raises(ValueError, match="hash"):
        S.scene_wire(path, "0" * 64)
    scene["gates"]["accepted"] = False
    path.write_text(json.dumps(scene))
    with pytest.raises(ValueError, match="gate"):
        S.scene_wire(path, SC.sha256_path(path))


def test_scene_wire_recomputes_gates_even_with_a_fresh_hash(tmp_path):
    from cfd_sdf.topo2d.geometry import build_scene, GeometryError
    scene = build_scene("E1", height_mm=100, dx_mm=223.4 / 120)
    scene["elements"][0]["polygon_mm"][4], scene["elements"][0]["polygon_mm"][40] = scene["elements"][0]["polygon_mm"][40], scene["elements"][0]["polygon_mm"][4]
    path = tmp_path / "forged_scene.json"
    path.write_text(json.dumps(scene))
    with pytest.raises(GeometryError):
        S.scene_wire(path, SC.sha256_path(path))


def test_extended_force_csv_reconstruction_and_batch_endpoints(tmp_path):
    path = tmp_path / "forces.csv"
    cols = [*SC.FORCE_COLUMNS, "cur_drag_solver", "cur_downforce_solver", "nds_drag_solver", "nds_downforce_solver", "cv_drag_solver", "cv_downforce_solver"]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(cols)
        for i in range(6):
            # Piecewise-linear force. Window endpoints fall between samples.
            drag, down = 2 + i, 3 + 2 * i
            writer.writerow([i, i, drag, 0, -down, drag, down, drag, 0, -down, 0, 0, 0, drag, down, "NaN", "NaN", "NaN", "NaN"])
    got = S.host_readouts(path, start=0.5, end=4.5, solver_length=80, force_scale=0.002, available={"cur": True, "nds": False, "cv": False}, batches=4)
    assert got["readouts"]["cur"]["drag"] == pytest.approx(2 * 4.5 / 80)
    assert got["readouts"]["cur"]["downforce"] == pytest.approx(2 * 8 / 80)
    assert len(got["readouts"]["cur"]["batches"]) == 4
    assert got["readouts"]["nds"] is None
    assert got["drag_n"] == pytest.approx(0.009)
    path.write_text(path.read_text().replace("NaN", "0", 1))
    with pytest.raises(ValueError, match="unavailable"):
        S.host_readouts(path, start=0.5, end=4.5, solver_length=80, force_scale=0.002, available={"cur": True, "nds": False, "cv": False}, batches=4)


def test_scene_formal_runner_is_explicitly_unavailable():
    with pytest.raises(ValueError, match="formal.*runner"):
        S.refuse_formal_runner()


def test_parent_window_registered_formula_and_cap():
    assert S.parent_window(2, 0, 80) == [80, 130]
    assert S.parent_window(2, 0.046, 80) == [80, 180]
    with pytest.raises(ValueError, match="400"):
        S.parent_window(2, 1, 80)
    with pytest.raises(ValueError, match="parent"):
        S.parent_window(0, 1, 80)


def test_formal_admission_cannot_promote_cpu_evidence():
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/harness/topo2d00_campaign.json"
    campaign = SC.jload(path)
    freeze = {"kind": SC.FREEZE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_sha256": SC.sha256_path(path), "source_commit": "a" * 40,
              "scene_runner_approved": True, "runtime": {"re1000": {"backend": "WaterLily CPU", "identity": {"memory": "Array"}}}}
    with pytest.raises(ValueError, match="never CPU"):
        S.formal_context(campaign, path, "re1000", freeze)


def test_future_local_runner_renders_without_loading_cuda(monkeypatch):
    from cfd_harness import campaign_build as B
    calls = []
    monkeypatch.setattr(B, "verify_source", lambda repo, commit, paths: calls.append((commit, set(paths))))
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/harness/topo2d00_campaign.json"
    code = S.render(path, "a" * 40, "re3000")
    compile(code, "scene_runner.py", "exec")
    assert calls and calls[0][0] == "a" * 40
    assert "julia/CFDSDFWaterLilyT4/Manifest.toml" in calls[0][1]
    assert "data/zz2003/main_element_table3.dat" in calls[0][1]
    assert "run_frozen_kernel" in code and "TOPO2D_FREEZE" in code
    assert "import CUDA" not in code


def test_scene_verify_recomputes_full_cpu_output_and_rejects_missing_elements(tmp_path):
    root = Path(__file__).resolve().parents[2]
    campaign = S.make_campaign()
    kernel = campaign["kernels"]["re1000"]
    kernel["runs"] = kernel["runs"][:1]
    name = kernel["runs"][0]["state"]
    state = campaign["states"][name]
    campaign["kernels"], campaign["states"] = {"re1000": kernel}, {name: state}
    campaign_rel = "docs/harness/cpu_scene_test.json"
    for relative in {*S.source_paths(), *SC.TOOL_FILES, state["scene_path"]}:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    campaign_path = tmp_path / campaign_rel
    campaign_path.parent.mkdir(parents=True, exist_ok=True)
    campaign_path.write_text(json.dumps(campaign))
    output = tmp_path / "output"
    directory = output / "states" / name
    directory.mkdir(parents=True)
    csv_path = directory / SC.forces_name("re1000")
    cols = [*SC.FORCE_COLUMNS, *(f"{readout}_{axis}_solver" for readout in S.READOUTS for axis in ("fx", "fy", "fz", "drag", "downforce")), *(f"element_main_{axis}_solver" for axis in ("fx", "fy", "fz", "drag", "downforce"))]
    rows = [[i, i, 2, 0, -3, 2, 3, 2, 0, -3, 0, 0, 0, 2, 0, -3, 2, 3, *(["NaN"] * 10), 2, 0, -3, 2, 3] for i in range(6)]
    def write_csv():
        with csv_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(cols)
            writer.writerows(rows)
    write_csv()
    pins = {relative: SC.sha256_path(tmp_path / relative) for relative in {*S.source_paths(), *SC.TOOL_FILES, state["scene_path"], campaign_rel}}
    summary = {"source_sha256": {p: pins[p] for p in S.source_paths()}, "force_csv_sha256": SC.sha256_path(csv_path), "scene_sha256": state["scene_sha256"], "topo2d": state["topo2d"],
               "phase_shift_m": SC.floats(kernel["runs"][0]["env"][SC.ORIGIN_ENV]), "force_unit": "N/m", "reference_chord_mm": 223.4,
               "backend": "WaterLily CPU", "smoke": True, "runtime": {"waterlily_version": "1.8.0", "scalar_type": "Float32", "scheme": "quick", "threads": 1},
               "finite_u": True, "finite_p": True, "finite_forces": True, "flow_dims": kernel["case"]["flow_dims"], "top_factor": 1.0,
               "flow_origin_m": [-0.4468, 0, -8 * kernel["case"]["flow_spacing_m"]],
               "solver_length": 120.0, "reynolds": 1000.0, "window_t_u_l": [0.5, 4.5], "t_end_reached": 5, "wall_seconds": 1.0,
               "readout_available": {"cur": True, "nds": False, "cv": False}, "batch_count": 4,
               "drag_time_weighted_n_per_m": 2 * kernel["case"]["flow_spacing_m"], "downforce_time_weighted_n_per_m": 3 * kernel["case"]["flow_spacing_m"]}
    index = {"kernel": "re1000", "status": "COMPLETE", "states": [{"name": name, "complete": True, "exit_code": 0, "seconds": 2.0, "forces_csv_sha256": SC.sha256_path(csv_path)}], "solver_process_wall_seconds_total": 2.0}
    identity = {"campaign_sha256": SC.sha256_path(campaign_path), "smoke": True, "expected_names": [name], "source_commit": "a" * 40, "pins": pins}
    def receipts():
        (directory / SC.summary_name("re1000")).write_text(json.dumps(summary))
        (directory / SC.JOB_DONE_NAME).write_text("done")
        (output / SC.DONE_NAME).write_text("CPU smoke")
        (output / SC.INDEX_NAME_DEFAULT).write_text(json.dumps(index))
        (output / SC.IDENTITY_NAME).write_text(json.dumps(identity))
        (output / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output)))
    receipts()
    table = S.verify(campaign_path, [output], smoke=True, repo=tmp_path)
    result = table["state_forces_n"]["re1000"][name]
    assert result["readouts"]["cur"]["downforce"] == pytest.approx(0.05)
    assert result["ok"] and result["finite"] and result["complete"]
    assert table["smoke"] is True and table["force_unit"] == "N/m"
    with pytest.raises(ValueError, match="smoke"):
        SC.require_formal_table(table)
    # Forge consistent file receipts after dropping all element columns. The
    # schema/physics verifier must reject it independently of those receipts.
    cols[:] = cols[:-5]
    rows[:] = [row[:-5] for row in rows]
    write_csv()
    index["states"][0]["forces_csv_sha256"] = summary["force_csv_sha256"] = SC.sha256_path(csv_path)
    receipts()
    with pytest.raises(ValueError, match="element CSV columns"):
        S.verify(campaign_path, [output], smoke=True, repo=tmp_path)


def test_draft_campaign_phase_pairing_controls_and_scene_hashes():
    campaign = S.make_campaign()
    S.validate_campaign(campaign)
    assert set(campaign["kernels"]) == {"re1000", "re3000", "confirmation"}
    assert len(campaign["states"]) == 125
    assert campaign["measurement"]["time_window_t_u_l"] is None
    for key in ("re1000", "re3000"):
        runs = campaign["kernels"][key]["runs"]
        primary = [r for r in runs if campaign["states"][r["state"]]["topo2d"]["role"] == "primary"]
        assert len(primary) == 48
        for phase in range(16):
            cohort = primary[3 * phase:3 * phase + 3]
            assert len({r["env"][SC.ORIGIN_ENV] for r in cohort}) == 1
        for pair in range(8):
            a, b = (SC.floats(primary[i]["env"][SC.ORIGIN_ENV]) for i in (6 * pair, 6 * pair + 3))
            assert a == [-v for v in b]
    domain = [r for r in campaign["states"].values() if r["topo2d"]["role"] == "domain"]
    assert {(r["topo2d"]["configuration"], r["topo2d"]["phase"]) for r in domain} == {("E1", "1"), ("E2", "1"), ("E1", "2"), ("E2", "2")}
    # The checked-in draft can never silently go stale after a scene rebuild.
    root = Path(__file__).resolve().parents[2]
    recorded = SC.jload(root / "docs/harness/topo2d00_campaign.json")
    assert recorded == campaign


def write_synthetic_numerical_kernel(tmp_path, smoke=True):
    """Raw receipts for boundary tests; no solver or backend qualification."""
    root = Path(__file__).resolve().parents[2]
    campaign = SC.jload(root / "docs/harness/topo2d00_campaign.json")
    kernel = campaign["kernels"]["re1000"]
    kernel["runs"] = [kernel["runs"][i] for i in (0, 1, 3)]
    names = SC.run_names(kernel)
    campaign["kernels"] = {"re1000": kernel}
    campaign["states"] = {n: campaign["states"][n] for n in names}
    backend = "cpu" if smoke else "cuda"
    relative = "docs/harness/synthetic_numerical_scene.json"
    paths = {*S.source_paths(backend), *SC.TOOL_FILES, *(r["scene_path"] for r in campaign["states"].values())}
    for rel in paths:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest)
    campaign_path = tmp_path / relative
    campaign_path.write_text(json.dumps(campaign))
    paths.add(relative)
    pins = {p: SC.sha256_path(tmp_path / p) for p in sorted(paths)}
    source = {p: pins[p] for p in S.source_paths(backend, tmp_path)}
    runtime = {"waterlily_version": "1.8.0", "scalar_type": "Float32", "scheme": "quick", "threads": 1, "memory": "Array" if smoke else "CuArray"}
    output = tmp_path / "numerical_output"
    dirs = [output / "states" / n for n in names]
    for d in dirs:
        d.mkdir(parents=True)
    failed = campaign["states"][names[0]]
    failure = {"schema": "topo2d-job-failure-v1", "status": "NUMERICAL", "topo2d": failed["topo2d"], "scene_sha256": failed["scene_sha256"],
               "source_sha256": source, "runtime": runtime, "phase_shift_m": SC.floats(kernel["runs"][0]["env"][SC.ORIGIN_ENV]),
               "window_t_u_l": [0.5, 4.5], "flow_dims": kernel["case"]["flow_dims"], "contract_fingerprint": "f" * 64,
               "smoke": smoke, "reason": "synthetic nonfinite-force injection", "wall_seconds": 1.0}
    failure_path = dirs[0] / "numerical_failure.json"
    failure_path.write_text(json.dumps(failure))
    digest = SC.sha256_path(failure_path)
    (dirs[0] / SC.ERROR_NAME).write_text("NUMERICAL synthetic fixture\n")
    (dirs[2] / SC.ERROR_NAME).write_text("SKIPPED_NUMERICAL synthetic fixture\n")
    good = campaign["states"][names[1]]
    csv_path = dirs[1] / SC.forces_name("re1000")
    axes = ("fx", "fy", "fz", "drag", "downforce")
    cols = [*SC.FORCE_COLUMNS, *(f"{r}_{a}_solver" for r in S.READOUTS for a in axes), *(f"element_{n}_{a}_solver" for n in ("main", "flap1") for a in axes)]
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(cols)
        writer.writerows([[i, i, 2, 0, -3, 2, 3, 2, 0, -3, 0, 0, 0, 2, 0, -3, 2, 3, *(["NaN"] * 10), 1, 0, -1.5, 1, 1.5, 1, 0, -1.5, 1, 1.5] for i in range(6)])
    summary = {"source_sha256": source, "force_csv_sha256": SC.sha256_path(csv_path), "scene_sha256": good["scene_sha256"], "topo2d": good["topo2d"],
               "phase_shift_m": SC.floats(kernel["runs"][1]["env"][SC.ORIGIN_ENV]), "force_unit": "N/m", "reference_chord_mm": 223.4,
               "backend": "WaterLily CPU" if smoke else "WaterLily CUDA", "smoke": smoke, "runtime": runtime,
               "finite_u": True, "finite_p": True, "finite_forces": True, "flow_dims": kernel["case"]["flow_dims"], "top_factor": 1.0,
               "flow_origin_m": [-0.4468, 0, -8 * kernel["case"]["flow_spacing_m"]], "solver_length": 120.0, "reynolds": 1000.0,
               "window_t_u_l": [0.5, 4.5], "t_end_reached": 5, "wall_seconds": 1.0, "readout_available": {"cur": True, "nds": False, "cv": False}, "batch_count": 4,
               "drag_time_weighted_n_per_m": 2 * kernel["case"]["flow_spacing_m"], "downforce_time_weighted_n_per_m": 3 * kernel["case"]["flow_spacing_m"]}
    (dirs[1] / SC.summary_name("re1000")).write_text(json.dumps(summary))
    (dirs[1] / SC.JOB_DONE_NAME).write_text("synthetic job success\n")
    index = {"kernel": "re1000", "status": "NUMERICAL", "states": [
        {"name": names[0], "complete": False, "status": "NUMERICAL", "exit_code": 42, "seconds": 2, "failure_sha256": digest},
        {"name": names[1], "complete": True, "exit_code": 0, "seconds": 2, "forces_csv_sha256": SC.sha256_path(csv_path)},
        {"name": names[2], "complete": False, "status": "SKIPPED_NUMERICAL", "seconds": 0, "prior_failure_sha256": digest}], "solver_process_wall_seconds_total": 4.0}
    identity = {"campaign_sha256": SC.sha256_path(campaign_path), "smoke": smoke, "expected_names": names, "source_commit": "a" * 40, "pins": pins}
    (output / SC.ERROR_NAME).write_text("NUMERICAL synthetic kernel fixture\n")
    (output / SC.INDEX_NAME_DEFAULT).write_text(json.dumps(index))
    (output / SC.IDENTITY_NAME).write_text(json.dumps(identity))
    (output / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output)))
    freeze_path = None
    if not smoke:
        freeze_path = tmp_path / "synthetic_freeze.json"
        freeze_path.write_text(json.dumps({"kind": SC.FREEZE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_sha256": SC.sha256_path(campaign_path),
                                          "source_commit": "a" * 40, "scene_runner_approved": True, "pins": {"re1000": pins}, "windows": {"re1000": [0.5, 4.5]},
                                          "runtime": {"re1000": {"backend": "WaterLily CUDA", "identity": runtime}}}))
        Path(str(freeze_path) + ".sha256").write_text(SC.sha256_path(freeze_path))
    return campaign_path, output, freeze_path


def test_numerical_failure_transport_authenticates_failure_and_skip(tmp_path, monkeypatch):
    campaign, output, freeze = write_synthetic_numerical_kernel(tmp_path, smoke=False)
    # Only the synthetic external qualification context is waived. All raw
    # state/file/scene/source/runtime/force checks below execute unchanged.
    monkeypatch.setattr(S, "formal_context", lambda *args: [0.5, 4.5])
    table = S.verify(campaign, [output], freeze, repo=tmp_path)
    rows = list(table["state_forces_n"]["re1000"].values())
    assert rows[0]["status"] == "NUMERICAL" and rows[0]["finite"] is False
    assert rows[0]["readouts"] == {"cur": None, "nds": None, "cv": None}
    assert rows[1]["ok"] is True
    assert rows[2]["status"] == "SKIPPED_NUMERICAL" and rows[2]["finite"] is None
    assert rows[2]["prior_failure_sha256"] == rows[0]["failure_sha256"]
    index_path = output / SC.INDEX_NAME_DEFAULT
    index = SC.jload(index_path)
    index["states"][2]["prior_failure_sha256"] = "0" * 64
    index_path.write_text(json.dumps(index))
    (output / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output)))
    with pytest.raises(ValueError, match="earlier authenticated failure"):
        S.verify(campaign, [output], freeze, repo=tmp_path)


def test_runner_stops_only_failed_configuration_and_continues_others(tmp_path, monkeypatch):
    from types import SimpleNamespace
    campaign, planted, _ = write_synthetic_numerical_kernel(tmp_path)
    c = SC.jload(campaign)
    names = SC.run_names(c["kernels"]["re1000"])
    launched = []
    monkeypatch.setattr(S.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    def fake_job(command, **kwargs):
        dest = Path(command[-1])
        launched.append(dest.name)
        source = planted / "states" / dest.name
        if dest.name == names[0]:
            failure = SC.jload(source / "numerical_failure.json")
            failure["wall_seconds"] = 1e-10
            (dest / "numerical_failure.json").write_text(json.dumps(failure))
            (dest / SC.ERROR_NAME).write_text("synthetic nonfinite job\n")
            return SimpleNamespace(returncode=42)
        for suffix in (SC.forces_name("re1000"), SC.JOB_DONE_NAME):
            shutil.copy2(source / suffix, dest / suffix)
        summary = SC.jload(source / SC.summary_name("re1000"))
        summary["wall_seconds"] = 1e-10
        (dest / SC.summary_name("re1000")).write_text(json.dumps(summary))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(S.subprocess, "run", fake_job)
    output = S.run_cpu_smoke(campaign, "re1000", tmp_path / "run", window=[0.5, 4.5], count=3, repo=tmp_path)
    assert launched == names[:2]
    index = SC.jload(output / SC.INDEX_NAME_DEFAULT)
    assert index["status"] == "NUMERICAL"
    assert index["states"][2]["status"] == "SKIPPED_NUMERICAL"
    table = S.verify(campaign, [output], smoke=True, repo=tmp_path)
    assert table["state_forces_n"]["re1000"][names[1]]["ok"] is True


def write_synthetic_incomplete_kernel(tmp_path, smoke=True, reason="STATE_TIMEOUT"):
    """A completed E2 followed by an authenticated budget stop, no solver."""
    campaign_path, output, freeze_path = write_synthetic_numerical_kernel(tmp_path, smoke)
    campaign = SC.jload(campaign_path)
    kernel = campaign["kernels"]["re1000"]
    overrun = reason == "WALL_TIME_OVERRUN"
    kernel["runs"] = [kernel["runs"][i] for i in ((1,) if overrun else (1, 0, 2))]
    if reason in ("SOLVER_WALL_CAP", "WALL_TIME_OVERRUN"):
        kernel["config"]["per_state_timeout_s"] = kernel["config"]["solver_wall_time_cap_s"] = 2
    names = SC.run_names(kernel)
    campaign["states"] = {n: campaign["states"][n] for n in names}
    campaign_path.write_text(json.dumps(campaign))
    if overrun:
        for path in (output / "states").iterdir():
            if path.name not in names:
                shutil.rmtree(path)
    identity = SC.jload(output / SC.IDENTITY_NAME)
    identity["campaign_sha256"] = SC.sha256_path(campaign_path)
    identity["expected_names"] = names
    relative = str(campaign_path.relative_to(tmp_path))
    identity["pins"][relative] = SC.sha256_path(campaign_path)
    backend = "cpu" if smoke else "cuda"
    source = {p: identity["pins"][p] for p in S.source_paths(backend, tmp_path)}
    current_dir = output / "states" / names[0 if overrun else 1]
    if (current_dir / "numerical_failure.json").exists():
        (current_dir / "numerical_failure.json").unlink()
    runtime = SC.jload(output / "states" / names[0] / SC.summary_name("re1000"))["runtime"]
    limit = kernel["config"]["per_state_timeout_s"] if reason in ("STATE_TIMEOUT", "WALL_TIME_OVERRUN") else 0
    receipt = {"schema": "topo2d-cap-receipt-v1", "kernel": "re1000", "reason": reason, "state": names[0 if overrun else 1], "smoke": smoke,
               "campaign_sha256": identity["campaign_sha256"], "source_commit": identity["source_commit"], "source_sha256": source,
               "prior_solver_wall_seconds": 0 if overrun else 2, "elapsed_seconds": 3 if overrun else limit, "limit_seconds": limit,
               "per_state_timeout_s": kernel["config"]["per_state_timeout_s"], "solver_wall_time_cap_s": kernel["config"]["solver_wall_time_cap_s"],
               "runtime_expected": None if smoke else runtime, "runtime_observed": None, "preflight_sha256": None}
    if reason == "STATE_TIMEOUT":
        preflight = {"schema": "topo2d-job-preflight-v1", "topo2d": campaign["states"][names[1]]["topo2d"], "scene_sha256": campaign["states"][names[1]]["scene_sha256"],
                     "source_sha256": source, "runtime": runtime, "smoke": smoke, "phase_shift_m": SC.floats(kernel["runs"][1]["env"][SC.ORIGIN_ENV]),
                     "contract_fingerprint": "f" * 64, "flow_dims": kernel["case"]["flow_dims"], "window_t_u_l": [0.5, 4.5]}
        preflight_path = current_dir / "job_preflight.json"
        preflight_path.write_text(json.dumps(preflight))
        receipt["preflight_sha256"], receipt["runtime_observed"] = SC.sha256_path(preflight_path), runtime
        (current_dir / "job.log").write_text("synthetic subprocess.TimeoutExpired\n")
    receipt_path = output / "cap_receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    digest = SC.sha256_path(receipt_path)
    index = SC.jload(output / SC.INDEX_NAME_DEFAULT)
    completed = index["states"][1]
    if overrun:
        completed["seconds"] = 3
    markers = [{"name": n, "status": "INCOMPLETE_TIMEOUT" if i == 0 and reason == "STATE_TIMEOUT" else "UNRUN_CAP", "seconds": limit if i == 0 else 0, "cap_receipt_sha256": digest} for i, n in enumerate(names[1:])]
    index.update(status="INCOMPLETE", states=[completed, *markers], solver_process_wall_seconds_total=3 if overrun else 2 + limit)
    (output / SC.INDEX_NAME_DEFAULT).write_text(json.dumps(index))
    (output / SC.IDENTITY_NAME).write_text(json.dumps(identity))
    (output / SC.ERROR_NAME).write_text("INCOMPLETE synthetic cap fixture\n")
    (output / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output)))
    if freeze_path is not None:
        freeze = SC.jload(freeze_path)
        freeze["campaign_sha256"], freeze["pins"]["re1000"] = identity["campaign_sha256"], identity["pins"]
        freeze_path.write_text(json.dumps(freeze))
        Path(str(freeze_path) + ".sha256").write_text(SC.sha256_path(freeze_path))
    return campaign_path, output, freeze_path


@pytest.mark.parametrize("reason", ["STATE_TIMEOUT", "SOLVER_WALL_CAP", "WALL_TIME_OVERRUN"])
def test_incomplete_transport_authenticates_budgets_without_fake_forces(tmp_path, monkeypatch, reason):
    campaign, output, freeze = write_synthetic_incomplete_kernel(tmp_path, smoke=False, reason=reason)
    monkeypatch.setattr(S, "formal_context", lambda *args: [0.5, 4.5])
    table = S.verify(campaign, [output], freeze, repo=tmp_path)
    assert table["cap_hit"] and table["cap_receipts"]["re1000"]["record"]["reason"] == reason
    rows = list(table["state_forces_n"]["re1000"].values())
    assert rows[0]["ok"] is True
    assert all(set(row) == {"status", "topo2d", "scene_sha256", "cap_receipt_sha256"} for row in rows[1:])
    receipt_path = output / "cap_receipt.json"
    receipt = SC.jload(receipt_path)
    receipt["reason"] = "UNKNOWN_PROCESS_ERROR"
    receipt_path.write_text(json.dumps(receipt))
    index = SC.jload(output / SC.INDEX_NAME_DEFAULT)
    for entry in index["states"][1:]:
        entry["cap_receipt_sha256"] = SC.sha256_path(receipt_path)
    (output / SC.INDEX_NAME_DEFAULT).write_text(json.dumps(index))
    (output / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(output)))
    with pytest.raises(ValueError, match="kind/reason"):
        S.verify(campaign, [output], freeze, repo=tmp_path)


def test_runner_timeout_before_runtime_observation_has_authenticated_cap(tmp_path, monkeypatch):
    campaign, _, _ = write_synthetic_numerical_kernel(tmp_path)
    monkeypatch.setattr(S.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    ticks = iter([0.0, 3600.0])
    monkeypatch.setattr(S.time, "monotonic", lambda: next(ticks, 3600.0))
    def timed_out(command, **kwargs):
        raise S.subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr(S.subprocess, "run", timed_out)
    output = S.run_cpu_smoke(campaign, "re1000", tmp_path / "timed_out", window=[0.5, 4.5], count=3, repo=tmp_path)
    receipt = SC.jload(output / "cap_receipt.json")
    assert receipt["runtime_observed"] is None and receipt["preflight_sha256"] is None
    table = S.verify(campaign, [output], smoke=True, repo=tmp_path)
    assert table["cap_hit"] is True
    assert [r["status"] for r in table["state_forces_n"]["re1000"].values()] == ["INCOMPLETE_TIMEOUT", "UNRUN_CAP", "UNRUN_CAP"]


def test_last_successful_process_wall_overrun_is_incomplete(tmp_path, monkeypatch):
    from types import SimpleNamespace
    campaign, planted, _ = write_synthetic_incomplete_kernel(tmp_path, reason="WALL_TIME_OVERRUN")
    name = SC.run_names(SC.jload(campaign)["kernels"]["re1000"])[0]
    monkeypatch.setattr(S.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    ticks = iter([0.0, 3.0])
    monkeypatch.setattr(S.time, "monotonic", lambda: next(ticks, 3.0))
    def successful(command, **kwargs):
        dest, source = Path(command[-1]), planted / "states" / name
        for suffix in (SC.forces_name("re1000"), SC.summary_name("re1000"), SC.JOB_DONE_NAME):
            shutil.copy2(source / suffix, dest / suffix)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(S.subprocess, "run", successful)
    output = S.run_cpu_smoke(campaign, "re1000", tmp_path / "overrun", window=[0.5, 4.5], repo=tmp_path)
    table = S.verify(campaign, [output], smoke=True, repo=tmp_path)
    assert table["cap_hit"] is True
    assert table["cap_receipts"]["re1000"]["record"]["reason"] == "WALL_TIME_OVERRUN"
    # The measured row remains measured; the pinned budget is still exceeded.
    assert table["state_forces_n"]["re1000"][name]["ok"] is True
    assert SC.jload(output / SC.INDEX_NAME_DEFAULT)["status"] == "INCOMPLETE"
