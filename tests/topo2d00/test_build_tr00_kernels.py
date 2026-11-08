"""Local rendering only; scripts install or solve nothing during these tests."""
from __future__ import annotations

import json
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/topo2d00"))
import build_tr00_kernels as K
import run_rans as R
import t2d_multibody_case as M


def geometry_files(tmp_path, configs=K.C.CONFIGS, verification="DEVELOPMENT_SYNTHETIC", height_m=.1):
    """Dense synthetic WP4 scenes; no source coordinates or figure are inferred."""
    from test_multibody_case import wp4_scene
    paths = {}
    for c in configs:
        scene = wp4_scene()
        prototype = scene['elements'][0]
        elements = []
        for i in range(int(c[1])):
            element = copy.deepcopy(prototype)
            shift = [i*240., height_m*1000-scene['height_mm']]
            for key in ('suction_mm', 'pressure_mm', 'polygon_mm'):
                element[key] = (np.asarray(element[key])+shift).tolist()
            element['name'] = f'element{i+1}'
            elements.append(element)
        p = tmp_path / f"{c}.json"
        scene.update(configuration=c, height_mm=height_m*1000, elements=elements,
                     sources=[{"path": "<synthetic fixture>", "verification": verification}])
        p.write_text(json.dumps(scene))
        paths[c] = p
    return paths


def git_state(monkeypatch, dirty=""):
    calls = []

    def check_output(command, **kwargs):
        calls.append(command)
        if "rev-parse" in command:
            return "c"*40+"\n"
        assert "status" in command
        # A modified or untracked file outside SOURCE_FILES must block ready.
        assert "--" not in command and "--untracked-files=all" in command
        return dirty

    monkeypatch.setattr(K.subprocess, "check_output", check_output)
    return calls


def freeze_file(tmp_path, plan, **updates):
    record = {"schema": "topo2d00-rans-freeze1-v1", "stage": "freeze1",
              "source_commit": plan["source_commit"], "input_sha256": plan["input_sha256"],
              "geometry_sha256": plan["geometry_input_sha256"], **updates}
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(record))
    return path


def test_plan_counts_partitions_and_execution_gate():
    tr, main = K.make_plan("tr00"), K.make_plan("main")
    assert len(tr["runs"]) == 64 and len(tr["kernels"]) == 6
    assert len(main["runs"]) == 96 and len(main["kernels"]) == 8
    assert not tr["ready_for_execution"] and not main["ready_for_execution"]
    for plan in (tr, main):
        ids = [K.C.run_id(r) for k in plan["kernels"] for r in k["runs"]]
        assert len(set(ids)) == len(ids) == len(plan["runs"])
        assert all(len(k["runs"]) <= 12 for k in plan["kernels"])
        assert max(k["wave"] for k in plan["kernels"]) == 2
        assert plan["session_budget_s"] == 39600 and plan["workers"] == 4
        assert plan["render_kind"] == "development" and plan["push_plan"] == []
    main = K.make_plan("main", [("sa-wf", "fine30")])
    assert not main["ready_for_execution"] and len(main["runs"]) == 24
    assert {r["model"] for r in main["runs"]} == {"sa-wf"}


def test_plan_only_requires_no_geometry_and_creates_no_runner(tmp_path):
    out = tmp_path / "plan"
    assert K.main(["--stage", "tr00", "--plan-only", "--out", str(out)]) == 0
    assert len(json.loads((out / "run_plan.json").read_text())["runs"]) == 64
    assert not list(out.rglob("runner.py"))


def test_render_is_deterministic_embedded_and_cpu_private(tmp_path, monkeypatch):
    git_state(monkeypatch)
    geometries = geometry_files(tmp_path, K.C.CONFIGS[:2])
    a, b = tmp_path / "a", tmp_path / "b"
    K.render(a, geometries, "tr00")
    K.render(b, geometries, "tr00")
    for pa in a.rglob("*"):
        if pa.is_file():
            assert pa.read_bytes() == (b / pa.relative_to(a)).read_bytes()
    runner = next(a.rglob("runner.py"))
    ns = {"__name__": "test_embedded_runner"}
    exec(compile(runner.read_text(), str(runner), "exec"), ns)
    assert callable(ns["unpack_bundle"])
    target = tmp_path / "unpacked"
    ns["unpack_bundle"](target)
    assert (target / "scripts/topo2d00/run_rans.py").is_file()
    assert (target / "geometry/E2_sharp.json").read_bytes() == geometries["E2_sharp"].read_bytes()
    assert K.C.sha256(target / "scripts/t20_case.py") == K.C.sha256(ROOT / "scripts/t20_case.py")
    boundary = target / "boundary_layer_plan.json"
    assert K.C.sha256(boundary) == M.plan_sha256(json.loads(boundary.read_text()))
    assert boundary.read_bytes().endswith(b"}")  # canonical compact JSON, no newline
    assert ns["PLAN"]["render_kind"] == "development" and ns["PLAN"]["push_plan"] == []
    with pytest.raises(ValueError, match="freeze1"):
        ns["main"]()  # Block before any runtime extraction or solver work.
    for row in ns["PLAN"]["runs"]:
        assert row["boundary_layer_plan_file"] == "boundary_layer_plan.json"
        assert row["boundary_layer_plan_sha256"] == K.C.sha256(boundary)
    meta = json.loads(runner.with_name("kernel-metadata.json").read_text())
    assert not meta["enable_gpu"] and meta["is_private"] and meta["enable_internet"]
    assert meta["dataset_sources"] == []
    source = runner.read_text()
    assert "git clone" not in source and "kaggle kernels push" not in source
    with pytest.raises(FileExistsError):
        K.render(a, geometries, "tr00")


def test_bundle_refuses_corruption_and_paths(tmp_path):
    geometries = geometry_files(tmp_path, K.C.CONFIGS[:2])
    out = tmp_path / "out"
    K.render(out, geometries, "tr00")
    runner = next(out.rglob("runner.py"))
    ns = {"__name__": "test_embedded_runner"}
    exec(compile(runner.read_text(), str(runner), "exec"), ns)
    ns["BUNDLE_SHA256"] = "f" * 64
    with pytest.raises(ValueError, match="bundle SHA"):
        ns["unpack_bundle"](tmp_path / "bad")


def test_missing_or_mislabeled_geometry_fails_before_writing(tmp_path):
    geometries = geometry_files(tmp_path, ("E1_sharp",))
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="geometry"):
        K.render(out, geometries, "tr00")
    assert not out.exists()


def test_smoke_uses_one_mesh_then_200_iterations_per_configuration(tmp_path):
    geometries = geometry_files(tmp_path, ("E2_sharp", "E2"))
    out = tmp_path / "smoke"
    p = K.render(out, geometries, "smoke")
    assert len(p["runs"]) == 2 and len(p["kernels"]) == 1
    assert [r["mode"] for r in p["runs"]] == ["smoke", "smoke"]
    assert all(r["model"] == "sa-wf" and r["family"] == "fine30" and r["realisation"] == 0 for r in p["runs"])
    assert all(r["iters"] <= 200 and r["cont_iters"] is None for r in p["runs"])
    assert (out / "smoke_01/runner.py").is_file()
    assert not p["ready_for_execution"] and p["push_plan"] == []


def test_ready_requires_clean_frozen_verified_six_geometry_inputs(tmp_path, monkeypatch):
    git_state(monkeypatch)
    calls = []
    original = M.boundary_layer_plan

    def once_per_render(*args, **kwargs):
        calls.append(set(args[0]))
        return original(*args, **kwargs)

    monkeypatch.setattr(M, "boundary_layer_plan", once_per_render)
    geometries = geometry_files(tmp_path, sorted(M.STUDY_CONFIGS), verification="VERIFIED")
    run_geometries = {c: geometries[c] for c in K.C.CONFIGS[:2]}
    heights = {c: .1 for c in geometries}
    draft = K.render(tmp_path / "draft", run_geometries, study_geometries=geometries, expected_heights_m=heights)
    assert calls == [M.STUDY_CONFIGS]
    assert not draft["ready_for_execution"] and draft["push_plan"] == []
    freeze = freeze_file(tmp_path, draft)
    plan = K.render(tmp_path / "ready", run_geometries, study_geometries=geometries, freeze=freeze, expected_heights_m=heights)
    assert calls == [M.STUDY_CONFIGS, M.STUDY_CONFIGS]
    assert plan["ready_for_execution"] and plan["render_kind"] == "ready"
    assert len(plan["push_plan"]) == len(plan["kernels"]) == 6
    assert set(plan["geometry_input_sha256"]) == M.STUDY_CONFIGS
    assert {r["config"] for r in plan["runs"]} == {"E1_sharp", "E2_sharp"}
    assert plan["freeze1"]["sha256"] == K.C.sha256(freeze)
    assert "scripts/topo2d00/build_tr00_kernels.py" in plan["input_sha256"]
    assert "docs/topo2d00_registration_2026_11_01.md" in plan["input_sha256"]
    assert "geometry/E3_sharp.json" in plan["input_sha256"]
    assert not any("t20d" in key for key in plan["input_sha256"])
    assert plan['height_m_by_config'] == heights
    assert all(r['height_m'] == .1 and r['n_layers'] > 0 for r in plan['runs'])
    assert 'study_heights.json' in plan['input_sha256']


def test_scene_height_must_match_declared_height_before_render_writes(tmp_path):
    geometries = geometry_files(tmp_path, K.C.CONFIGS[:2], height_m=.08)
    with pytest.raises(ValueError, match='height'):
        K.render(tmp_path/'out', geometries, expected_heights_m={c: .1 for c in geometries})
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('height', [None, True, 0, float('nan')])
def test_render_refuses_invalid_explicit_height_declarations(tmp_path, height):
    geometries = geometry_files(tmp_path, K.C.CONFIGS[:2])
    with pytest.raises(ValueError, match='height'):
        K.render(tmp_path/'out', geometries, expected_heights_m={c: height for c in geometries})
    assert not (tmp_path/'out').exists()


def test_verified_clean_frozen_render_without_height_declaration_stays_development(tmp_path, monkeypatch):
    git_state(monkeypatch)
    geometries = geometry_files(tmp_path, sorted(M.STUDY_CONFIGS), verification='VERIFIED')
    runs = {c: geometries[c] for c in K.C.CONFIGS[:2]}
    draft = K.render(tmp_path/'draft', runs, study_geometries=geometries)
    frozen = freeze_file(tmp_path, draft)
    plan = K.render(tmp_path/'undeclared', runs, study_geometries=geometries, freeze=frozen)
    assert not plan['ready_for_execution'] and plan['push_plan'] == []
    assert 'height' in plan['blocked_reason']


@pytest.mark.parametrize("payload", [None, "not JSON", "[]"])
def test_missing_or_invalid_freeze_is_a_blocked_development_render(tmp_path, payload):
    geometries = geometry_files(tmp_path, K.C.CONFIGS[:2])
    freeze = tmp_path / "missing-or-invalid-freeze.json"
    if payload is not None:
        freeze.write_text(payload)
    plan = K.render(tmp_path / "blocked", geometries, freeze=freeze)
    assert not plan["ready_for_execution"] and plan["push_plan"] == []
    assert not plan["freeze1"]["matches"] and "freeze1" in plan["blocked_reason"]


@pytest.mark.parametrize("mutation", ["source_commit", "input_sha256", "geometry_sha256", "schema", "stage"])
def test_mismatched_freeze_stays_development(tmp_path, monkeypatch, mutation):
    git_state(monkeypatch)
    geometries = geometry_files(tmp_path, sorted(M.STUDY_CONFIGS), verification="VERIFIED")
    run_geometries = {c: geometries[c] for c in K.C.CONFIGS[:2]}
    draft = K.render(tmp_path / "draft", run_geometries, study_geometries=geometries)
    replacements = {"source_commit": "f"*40, "input_sha256": {}, "geometry_sha256": {},
                    "schema": "topo2d00-analysis-freeze-v1", "stage": "postrun"}
    freeze = freeze_file(tmp_path, draft, **{mutation: replacements[mutation]})
    plan = K.render(tmp_path / "blocked", run_geometries, study_geometries=geometries, freeze=freeze)
    assert not plan["ready_for_execution"] and plan["render_kind"] == "development"
    assert plan["push_plan"] == [] and "freeze" in plan["blocked_reason"]


@pytest.mark.parametrize("dirty", [" M unrelated.py\n", "?? unrelated.txt\n"])
def test_whole_tree_dirty_blocks_matching_freeze(tmp_path, monkeypatch, dirty):
    git_state(monkeypatch)
    geometries = geometry_files(tmp_path, sorted(M.STUDY_CONFIGS), verification="VERIFIED")
    run_geometries = {c: geometries[c] for c in K.C.CONFIGS[:2]}
    draft = K.render(tmp_path / "draft", run_geometries, study_geometries=geometries)
    freeze = freeze_file(tmp_path, draft)
    git_state(monkeypatch, dirty)
    plan = K.render(tmp_path / "dirty", run_geometries, study_geometries=geometries, freeze=freeze)
    assert plan["source_dirty"] and not plan["ready_for_execution"]
    assert plan["push_plan"] == [] and "dirty" in plan["blocked_reason"]


@pytest.mark.parametrize("verification", ["UNVERIFIED_OCR", "DEVELOPMENT_SYNTHETIC", None])
def test_nonverified_geometry_blocks_even_matching_freeze(tmp_path, monkeypatch, verification):
    git_state(monkeypatch)
    geometries = geometry_files(tmp_path, sorted(M.STUDY_CONFIGS), verification=verification)
    run_geometries = {c: geometries[c] for c in K.C.CONFIGS[:2]}
    draft = K.render(tmp_path / "draft", run_geometries, study_geometries=geometries)
    freeze = freeze_file(tmp_path, draft)
    plan = K.render(tmp_path / "unverified", run_geometries, study_geometries=geometries, freeze=freeze)
    assert not plan["ready_for_execution"] and plan["push_plan"] == []
    assert "verified" in plan["blocked_reason"].lower()


def test_cli_study_geometry_and_freeze_keep_missing_sixth_development(tmp_path, monkeypatch):
    git_state(monkeypatch)
    geometries = geometry_files(tmp_path, K.C.CONFIGS, verification="VERIFIED")
    run_geometries = {c: geometries[c] for c in K.C.CONFIGS[:2]}
    draft = K.render(tmp_path / "draft", run_geometries, study_geometries=geometries)
    freeze = freeze_file(tmp_path, draft)
    args = ["--stage", "tr00", "--freeze", str(freeze), "--out", str(tmp_path / "cli")]
    for name, path in run_geometries.items():
        args += ["--geometry", f"{name}={path}"]
    for name, path in geometries.items():
        args += ["--study-geometry", f"{name}={path}"]
    assert K.main(args) == 0
    plan = json.loads((tmp_path / "cli/run_plan.json").read_text())
    assert plan["boundary_layer_plan_scope"] == "development"
    assert not plan["ready_for_execution"] and plan["push_plan"] == []


def test_driver_uses_inherited_continuation_and_retains_distinct_objects(tmp_path, monkeypatch):
    output = tmp_path / "measurement"
    (output / "work").mkdir(parents=True)
    helper = R.inherited_runner()
    calls = []
    geometries = geometry_files(tmp_path, ("E2_sharp",))
    boundary_layers = M.boundary_layer_plan(geometries, require_complete=False)
    source = tmp_path / "source"
    (source / "geometry").mkdir(parents=True)
    (source / "geometry/E2_sharp.json").write_bytes(geometries["E2_sharp"].read_bytes())
    (source / "boundary_layer_plan.json").write_bytes(json.dumps(boundary_layers, sort_keys=True, separators=(",", ":")).encode())
    n_layers = boundary_layers["families"]["fine30"]["n_layers"]
    spec = {**K.C.expected_runs()[32], "mode": "production", "iters": 5000, "cont_iters": 15000, "case_cap_s": 9000,
            "height_m": .1,
            "geometry_file": "geometry/E2_sharp.json", "geometry_sha256": K.C.sha256(geometries["E2_sharp"]),
            "boundary_layer_plan_file": "boundary_layer_plan.json", "boundary_layer_plan_sha256": M.plan_sha256(boundary_layers),
            "elements": [{"name": "main", "patch": "airfoil"}, {"name": "flap", "patch": "airfoil_2"}]}

    def generate(command, **kwargs):
        assert command[command.index("--boundary-layer-plan")+1] == str(source / "boundary_layer_plan.json")
        case = Path(command[command.index("--out")+1])
        (case / "system").mkdir(parents=True)
        (case / "system/controlDict").write_text("startFrom startTime;\nendTime 5000;\n")
        (case / "mesh.msh").write_text("synthetic mesh")
        (case / "case_manifest.json").write_text(json.dumps({"geometry_sha256": spec["geometry_sha256"], "mesh_quality_failures": [],
                                                           "height_m": .1, "h_over_c1": .1/.2234, "h_over_c": .1/.380,
                                                           "mesh_msh_sha256": K.C.sha256(case/'mesh.msh'),
                                                           "n_layers": n_layers, "mesh_stats": {"n_layers": n_layers}, "convergence": K.C.CONVERGENCE,
                                                           "boundary_layer_plan_sha256": spec["boundary_layer_plan_sha256"]}))
        return type("Result", (), {"returncode": 0, "stdout": "generated", "stderr": ""})()

    def timed(name, command, case, timeout):
        calls.append(name)
        if name == "gmshToFoam":
            (case / "constant/polyMesh").mkdir(parents=True)
            (case / "constant/polyMesh/boundary").write_text("\n".join(f"{p} {{ type patch; }}" for p in ("airfoil", "airfoil_2", "front", "back", "ground")))
        elif name == "checkMesh":
            (case / "log.checkMesh").write_text("cells: 2000\nMesh OK.\n")
        else:
            cont = name == "simpleFoam_cont"
            start, end = (5001, 15000) if cont else (1, 5000)
            if cont:
                assert "startFrom latestTime;" in (case / "system/controlDict").read_text()
                assert "endTime 15000;" in (case / "system/controlDict").read_text()
            q = .5*30**2*.0004468
            for patch, scale in (("total", 1.), ("airfoil", .7), ("airfoil_2", .3)):
                label = "forceCoeffs" if patch == "total" else "forceCoeffs_"+patch
                force = "forces" if patch == "total" else "forces_"+patch
                folder = case / "postProcessing" / label / ("5000" if cont else "0")
                ff = case / "postProcessing" / force / ("5000" if cont else "0")
                folder.mkdir(parents=True)
                ff.mkdir(parents=True)
                coefficients, vectors = [], []
                for i in range(start, end+1):
                    cl = ((2.0 if i <= 13000 else 2.5) if cont else 1+i*.0004)*scale
                    coefficients.append(f"{i} {.1*scale:.12g} {cl:.12g}\n")
                    vectors.append(f"{i} {q*.1*scale:.12g} {-q*cl:.12g} 0 {q*.08*scale:.12g} {-q*cl*.95:.12g} 0 {q*.02*scale:.12g} {-q*cl*.05:.12g} 0\n")
                (folder / "coefficient.dat").write_text("# Time Cd Cl\n"+"".join(coefficients))
                (ff / "force.dat").write_text("# Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x viscous_y viscous_z\n"+"".join(vectors))
            (case / ("log."+name)).write_text(f"Time = {end}\n")
        return {"stage": name, "returncode": 0, "timed_out": False, "wall_s": .1}

    monkeypatch.setattr(R.subprocess, "run", generate)
    monkeypatch.setattr(helper, "timed_run", timed)
    import time
    rec = R.run_case(spec, source, output, time.monotonic()+10000, helper)
    assert rec["status"] == "COMPLETED" and rec["continued_to"] == 15000
    assert calls == ["gmshToFoam", "checkMesh", "simpleFoam", "simpleFoam_cont"]
    assert rec["mesh_only_stage"]["passed"]
    assert rec["mesh_only_stage"]["mesh_msh_sha256"] == rec["mesh_msh_sha256"]
    assert len(rec["coefficient_files"]["airfoil_2"]) == 2
    path = output / "cases" / R._spec_id(spec) / "case_result.json"
    got = K.C.collect([path], expected=[spec])["results"][0]
    assert got["usable"] and got["coefficients"]["total"]["Cl"] == pytest.approx(2.5)


def test_production_guard_is_fail_closed_before_output(tmp_path, monkeypatch):
    monkeypatch.delenv("KAGGLE_KERNEL_RUN_TYPE", raising=False)
    p = K.make_plan("tr00")
    p["ready_for_execution"] = True  # Exercise the independent host guard only.
    with pytest.raises(ValueError, match="only run on Kaggle"):
        R.execute(p, ROOT, tmp_path / "out")
    assert not (tmp_path / "out").exists()
