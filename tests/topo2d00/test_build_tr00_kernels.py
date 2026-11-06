"""Local rendering only; scripts install or solve nothing during these tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/topo2d00"))
import build_tr00_kernels as K
import run_rans as R


def geometry_files(tmp_path, configs=K.C.CONFIGS):
    paths = {}
    for c in configs:
        p = tmp_path / f"{c}.json"
        p.write_text(json.dumps({"config": c, "main_chord_m": .2234, "elements": [
            {"name": f"element{i+1}", "points_m": (
                [[i*.1+.09,.1], [i*.1+.04,.09], [i*.1,.1], [i*.1+.04,.11], [i*.1+.09,.1]] if c.endswith("_sharp") else
                [[i*.1+.09,.095], [i*.1+.04,.09], [i*.1,.1], [i*.1+.04,.11], [i*.1+.09,.105], [i*.1+.09,.095]]),
             "te_kind": "sharp" if c.endswith("_sharp") else "blunt"}
            for i in range(int(c[1]))]}))
        paths[c] = p
    return paths


def test_plan_counts_partitions_and_execution_gate():
    tr, main = K.make_plan("tr00"), K.make_plan("main")
    assert len(tr["runs"]) == 64 and len(tr["kernels"]) == 6
    assert len(main["runs"]) == 96 and len(main["kernels"]) == 8
    assert tr["ready_for_execution"]
    assert not main["ready_for_execution"]
    for plan in (tr, main):
        ids = [K.C.run_id(r) for k in plan["kernels"] for r in k["runs"]]
        assert len(set(ids)) == len(ids) == len(plan["runs"])
        assert all(len(k["runs"]) <= 12 for k in plan["kernels"])
        assert max(k["wave"] for k in plan["kernels"]) == 2
        assert plan["session_budget_s"] == 39600 and plan["workers"] == 4
    main = K.make_plan("main", [("sa-wf", "fine30")])
    assert main["ready_for_execution"] and len(main["runs"]) == 24
    assert {r["model"] for r in main["runs"]} == {"sa-wf"}


def test_plan_only_requires_no_geometry_and_creates_no_runner(tmp_path):
    out = tmp_path / "plan"
    assert K.main(["--stage", "tr00", "--plan-only", "--out", str(out)]) == 0
    assert len(json.loads((out / "run_plan.json").read_text())["runs"]) == 64
    assert not list(out.rglob("runner.py"))


def test_render_is_deterministic_embedded_and_cpu_private(tmp_path):
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


def test_driver_uses_inherited_continuation_and_retains_distinct_objects(tmp_path, monkeypatch):
    output = tmp_path / "measurement"
    (output / "work").mkdir(parents=True)
    helper = R.inherited_runner()
    calls = []
    spec = {**K.C.expected_runs()[32], "mode": "production", "iters": 5000, "cont_iters": 15000, "case_cap_s": 9000,
            "geometry_file": "geometry/E2_sharp.json", "geometry_sha256": "a"*64,
            "elements": [{"name": "main", "patch": "airfoil"}, {"name": "flap", "patch": "airfoil_2"}]}

    def generate(command, **kwargs):
        case = Path(command[command.index("--out")+1])
        (case / "system").mkdir(parents=True)
        (case / "system/controlDict").write_text("startFrom startTime;\nendTime 5000;\n")
        (case / "mesh.msh").write_text("synthetic mesh")
        (case / "case_manifest.json").write_text(json.dumps({"geometry_sha256": spec["geometry_sha256"], "mesh_quality_failures": []}))
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
    rec = R.run_case(spec, ROOT, output, time.monotonic()+10000, helper)
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
    with pytest.raises(ValueError, match="only run on Kaggle"):
        R.execute(p, ROOT, tmp_path / "out")
    assert not (tmp_path / "out").exists()
