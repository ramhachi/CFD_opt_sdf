"""T2-0a kernel template and render script (no OpenFOAM, no network): placeholders, pins verified against a commit, registered case list."""
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import build_t20a_kernel as B

REAL = Path(B.ROOT)
TEMPLATE = REAL / "infra/kaggle/kernel_t20a_cpu/runner.py"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    for rel in (*B.FILES, *B.lock_paths(TEMPLATE.read_text()).values(), "infra/kaggle/kernel_t20a_cpu/runner.py", "infra/kaggle/kernel_t20a_cpu/kernel-metadata.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL / rel, tmp_path / rel)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "x")
    monkeypatch.setattr(B, "ROOT", tmp_path)
    monkeypatch.setattr(B, "TEMPLATE_DIR", tmp_path / "infra/kaggle/kernel_t20a_cpu")
    return tmp_path


def test_render_pins_the_commit_and_every_file(repo):
    commit = git(repo, "rev-parse", "HEAD")
    text = B.render(commit)
    tree = ast.parse(text)
    consts = {t.targets[0].id: ast.literal_eval(t.value) for t in tree.body if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name)
              and t.targets[0].id in ("SOURCE_COMMIT", "PINS", "GMSH_PIN")}
    assert consts["SOURCE_COMMIT"] == commit and consts["GMSH_PIN"] == "gmsh==4.15.2"
    assert set(consts["PINS"]) == {*B.FILES, "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json", "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in consts["PINS"].values())
    out = repo / "out"
    B.main(["--source-commit", commit, "--out", str(out)])
    assert json.loads((out / "kernel-metadata.json").read_text())["title"] == "cfd-opt-sdf-t20a-cpu"
    with pytest.raises(SystemExit):
        B.main(["--source-commit", commit, "--out", str(out)])


def test_render_refuses_a_pin_that_differs_from_the_commit_or_a_bad_commit(repo):
    commit = git(repo, "rev-parse", "HEAD")
    (repo / "scripts/t20_foam.py").write_text("# edited after the commit\n")
    with pytest.raises(ValueError, match="committed source differs"):
        B.render(commit)
    with pytest.raises(ValueError, match="full lowercase SHA"):
        B.render("abc123")


def test_template_case_list_and_metadata():
    src = TEMPLATE.read_text()
    ns = {}
    exec(compile(src.split("def require")[0].replace("PINS = PIN_PINS", "PINS = {}"), "r", "exec"), ns)   # constants only
    cases = ns["CASES"]
    assert len(cases) == 13 and len(set(cases)) == 13
    assert {(m, h) for m, h, mesh in cases if m == "sst-lm"} == {("sst-lm", 0.224), ("sst-lm", 0.134), ("sst-lm", 0.09)}
    assert {(m, h) for m, h, _ in cases if m != "sst-lm"} == {(m, h) for m in ("sa-wf", "sst-wf") for h in ns["HEIGHTS"]}
    assert {mesh for m, _, mesh in cases if m != "sst-lm"} == {"med30"} and {mesh for m, _, mesh in cases if m == "sst-lm"} == {"wr2"}
    assert [m for m, _, _ in ns["SMOKE"]] == ["sa-wf", "sst-wf", "sst-lm"] and ns["SMOKE_ITERS"] == 200
    assert ns["BUDGET_S"] < 12 * 3600 and ns["WORKERS"] == 4
    meta = json.loads((TEMPLATE.parent / "kernel-metadata.json").read_text())
    assert meta["title"] == meta["id"].split("/")[1] == "cfd-opt-sdf-t20a-cpu" and meta["enable_gpu"] is False and meta["enable_internet"] and meta["is_private"]
    # every registered case must be generable (model/mesh wall treatment match)
    from scripts import t20_case as T
    assert all(T.MODELS[m]["wall"] == T.MESHES[mesh]["wall"] for m, _, mesh in [*cases, *ns["SMOKE"]])


FAKE_BASHRC = r"""
gmshToFoam() { mkdir -p constant/polyMesh; printf '7\n(\n' > constant/polyMesh/boundary; for n in inlet outlet top ground airfoil front back; do printf '    %s\n    {\n        type patch;\n        nFaces 1;\n    }\n' $n >> constant/polyMesh/boundary; done; printf ')\n' >> constant/polyMesh/boundary; }
checkMesh() { printf 'cells:            13802\nMax aspect ratio = 20.5 OK.\nMesh OK.\n'; }
simpleFoam() {
  mkdir -p postProcessing/forceCoeffs/0 postProcessing/forces/0
  printf '# Force coefficients\n# Time          Cm              Cd              Cl              Cl(f)           Cl(r)\n' > postProcessing/forceCoeffs/0/coefficient.dat
  printf '# Time Fx\n' > postProcessing/forces/0/force.dat
  for i in $(seq 1 200); do echo "Time = $i"; echo "smoothSolver:  Solving for Ux, Initial residual = 1e-3, Final residual = 1e-5, No Iterations 1"
    echo "$i 0 0.05 1.30 0.6 0.7" >> postProcessing/forceCoeffs/0/coefficient.dat; echo "$i 1 2 3" >> postProcessing/forces/0/force.dat; done
}
"""


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    import importlib.util
    (tmp_path / "bashrc").write_text(FAKE_BASHRC)
    monkeypatch.setenv("T20A_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("T20A_BASHRC", str(tmp_path / "bashrc"))
    path = tmp_path / "runner_rendered.py"
    path.write_text(TEMPLATE.read_text().replace("PINS = PIN_PINS", "PINS = {}"))
    spec = importlib.util.spec_from_file_location("t20a_runner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_case_orchestration_with_a_fake_openfoam(runner, tmp_path):
    """Exercises generate -> gmshToFoam -> boundary fix -> checkMesh -> simpleFoam -> parse -> retain, with shell stubs for the OpenFOAM tools only."""
    import time
    runner.SOURCE = REAL
    (spec,) = runner.make_specs([("sa-wf", 0.448, "coa30")], 200)
    rec = runner.run_case(spec, REAL, time.monotonic() + 600)
    assert rec["status"] == "COMPLETED" and runner.infrastructure_ok(rec), rec
    assert rec["solver"]["iterations"] == 200 and rec["check_mesh"]["mesh_ok"] and rec["forces"]["Cl"]["tail_mean"] == pytest.approx(1.30)
    assert rec["forces"]["force_plateau"] and rec["residual_converged"] is False
    kept = Path(runner.OUTPUT) / "cases" / spec["id"]
    names = {p.name for p in kept.rglob("*") if p.is_file()}
    assert {"log.simpleFoam.gz", "log.checkMesh.gz", "coefficient.dat.gz", "force.dat.gz", "mesh.msh.gz", "case_manifest.json.gz", "case_result.json", "controlDict"} <= names
    assert not (Path(runner.OUTPUT) / "work" / spec["id"]).exists()
    assert runner.infrastructure_ok({**rec, "status": "SOLVER_FAILED"}) is False


def test_force_summary_flags_a_drifting_history_as_not_plateaued(runner, tmp_path):
    dat = tmp_path / "c.dat"
    dat.write_text("# Time Cm Cd Cl\n" + "".join(f"{i} 0 0.05 {1 + i * 1e-3}\n" for i in range(1, 400)))
    s = runner.force_summary(dat)
    assert s["force_plateau"] is False and s["Cl"]["tail_rel_drift"] > 0.05 and s["Cd"]["tail_rel_std"] < 1e-12


def test_analyzer_tabulates_against_genua_and_experiment(tmp_path):
    from scripts import analyze_t20a as A
    ref = json.loads(A.REF.read_text())
    assert ref["experimental"]["Cl"] == {"free_stream": 0.766, "0.224": 1.286, "0.09": 1.371}
    assert A.genua_value(ref, "sa-wf", 0.134, "Cl") == 1.409 and A.genua_value(ref, "sa-wf", 0.134, "Cd") == 0.062
    assert A.genua_value(ref, "sst-wf", 0.09, "Cl") == 1.779 and A.genua_value(ref, "sst-wf", 0.134, "Cl") is None and A.genua_value(ref, "sst-lm", 0.09, "Cl") is None
    f = lambda cl: {"Cl": {"tail_mean": cl}, "Cd": {"tail_mean": 0.075}, "force_plateau": True}
    d = tmp_path / "cases"
    for cid, h, cl in (("sa-wf_h0.09_med30", 0.09, 1.3810), ("sa-wf_h0.224_med30", 0.224, 1.3)):
        (d / cid).mkdir(parents=True)
        (d / cid / "case_result.json").write_text(json.dumps({"id": cid, "model": "sa-wf", "h_over_c": h, "mesh": "med30", "status": "COMPLETED", "forces": f(cl),
                                                              "solver": {"iterations": 5000}, "total_wall_s": 600, "stages": [{"stage": "simpleFoam", "wall_s": 500}]}))
    text = A.report(A.load(tmp_path), ref)
    assert "| 0.09 | med30 | COMPLETED | 1.381 | 1.381 | 0.0 | 1.371 | 0.7 |" in text
    assert "| 0.224 | med30 | COMPLETED | 1.300 | 1.255 | 3.6 | 1.286 | 1.1 |" in text and "- sa-wf: 0.09 " in text
