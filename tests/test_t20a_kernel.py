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


def test_render_mesh_only_sets_the_mode_and_a_separate_slug(repo):
    commit = git(repo, "rev-parse", "HEAD")
    assert "MODE = 'mesh_only'" in B.render(commit, "mesh_only") and "MODE = 'full'" in B.render(commit)
    with pytest.raises(ValueError, match="mode must be"):
        B.render(commit, "bogus")
    out = repo / "out_mesh"
    B.main(["--source-commit", commit, "--out", str(out), "--mode", "mesh_only"])
    meta = json.loads((out / "kernel-metadata.json").read_text())
    assert meta["title"] == meta["id"].split("/")[1] == "cfd-opt-sdf-t20a-meshcheck" and not meta["enable_gpu"] and meta["is_private"] and meta["enable_internet"]
    assert "MODE = 'mesh_only'" in (out / "runner.py").read_text()
    full = repo / "out_full"
    B.main(["--source-commit", commit, "--out", str(full)])
    assert json.loads((full / "kernel-metadata.json").read_text())["title"] == "cfd-opt-sdf-t20a-cpu" and "MODE = 'full'" in (full / "runner.py").read_text()


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
checkMesh() { if [ -n "$FAKE_BAD_MESH" ]; then printf 'cells:            9\n ***Unused points found in the mesh, number unused by faces: 5 number unused by cells: 5\nFailed 1 mesh checks.\n'; else printf 'cells:            13802\nMax aspect ratio = 20.5 OK.\nMesh OK.\n'; fi; }
simpleFoam() {
  local start end n1 d
  start=$(sed -n 's/^startFrom \(.*\);/\1/p' system/controlDict); end=$(sed -n 's/^endTime \([0-9]*\);/\1/p' system/controlDict)
  n1=0
  if [ "$start" = latestTime ]; then   # LM continuation: needs the SST time dir with gammaInt/ReThetat and the LM model
    n1=$(ls -d [0-9]* | sort -n | tail -1)
    [ -f $n1/gammaInt ] && [ -f $n1/ReThetat ] && grep -q kOmegaSSTLM constant/momentumTransport || { echo "FOAM FATAL ERROR: LM stage setup missing"; return 1; }
    if [ -f system/fvOptions ] && [ -n "$FAKE_REJECT_LIMITER" ]; then echo "--> FOAM FATAL IO ERROR: Unknown fvOption type velocityDampingConstraint"; return 1; fi
    if [ -n "$FAKE_LM_DIVERGE" ]; then echo "Time = $((n1 + 1))"; echo "#1  Foam::sigFpe::sigHandler(int) in libOpenFOAM.so"; return 136; fi
  fi
  mkdir -p postProcessing/forceCoeffs/$n1 postProcessing/forces/$n1 $end
  printf '# Force coefficients\n# Time          Cm              Cd              Cl              Cl(f)           Cl(r)\n' > postProcessing/forceCoeffs/$n1/coefficient.dat
  printf '# Time Fx\n' > postProcessing/forces/$n1/force.dat
  for i in $(seq $((n1 + 1)) $end); do echo "Time = $i"; echo "smoothSolver:  Solving for Ux, Initial residual = 1e-3, Final residual = 1e-5, No Iterations 1"
    echo "$i 0 0.05 1.30 0.6 0.7" >> postProcessing/forceCoeffs/$n1/coefficient.dat; echo "$i 1 2 3" >> postProcessing/forces/$n1/force.dat; done
  echo kOmega > $end/k
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


# ---- LM continuation, LM_DIVERGED policy, smoke gate, MESH_ONLY ---------------------------------------------------------------------------------------

def _lm(runner, tmp_path):
    import time
    runner.SOURCE = REAL
    (spec,) = runner.make_specs([("sst-lm", 0.448, "wrc")], 200)
    return spec, runner.run_case(spec, REAL, time.monotonic() + 900), Path(runner.OUTPUT) / "cases" / spec["id"]


def test_lm_runs_as_a_continuation_of_the_sst_stage(runner, tmp_path):
    spec, rec, kept = _lm(runner, tmp_path)
    assert rec["status"] == "COMPLETED", rec
    assert [s["stage"] for s in rec["stages"]] == ["gmshToFoam", "checkMesh", "simpleFoam", "simpleFoam_lm"] and rec["stages"][-1]["limiter"] == "velocityDampingConstraint"
    assert rec["solver"]["iterations"] == 100 and rec["solver_lm"]["iterations"] == 100 and rec["solver_lm"]["last_time"] == 200 and not rec["solver_lm"]["sigfpe"]
    assert rec["forces"]["last_iteration"] == 200 and rec["forces_stage1_kOmegaSST"]["last_iteration"] == 100            # stage 2 writes to postProcessing/.../<stage-1 end time>/
    names = {p.name for p in kept.rglob("*") if p.is_file()}
    assert {"coefficient.dat.gz", "t100_coefficient.dat.gz", "log.simpleFoam_lm.gz", "fvOptions"} <= names
    assert rec["mesh_proxy"]["unused_nodes"] == 0 and rec["mesh_proxy_failures"] == []


def test_lm_divergence_is_a_result_with_diagnostics_not_a_kernel_failure(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_LM_DIVERGE", "1")
    spec, rec, kept = _lm(runner, tmp_path)
    assert rec["status"] == "LM_DIVERGED" and rec["lm_failed_stage"] == "stage2_kOmegaSSTLM"
    d = rec["lm_diagnostics"]
    assert d["solver"]["sigfpe"] is True and d["solver"]["last_time"] == 101 and any("sigHandler" in l for l in d["log_tail"])
    assert (kept / "case_result.json").is_file() and rec["forces_stage1_kOmegaSST"]["rows"] == 100


def test_lm_limiter_rejected_at_startup_is_dropped_and_the_stage_rerun(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_REJECT_LIMITER", "1")
    spec, rec, kept = _lm(runner, tmp_path)
    assert rec["status"] == "COMPLETED" and rec["stages"][-1]["limiter"].startswith("dropped") and rec["solver_lm"]["iterations"] == 100
    assert "log.simpleFoam_lm_with_limiter.gz" in {p.name for p in kept.rglob("*")}


def test_smoke_gate_needs_sa_wf_and_sst_wf_only(runner):
    ok = {"id": "sa-wf_h0.448_coa30_smoke", "status": "COMPLETED", "forces": {"last_iteration": 200}, "solver": {"iterations": 200}}
    sst = {**ok, "id": "sst-wf_h0.448_coa30_smoke"}
    lm = {"id": "sst-lm_h0.448_wrc_smoke", "status": "LM_DIVERGED"}
    assert runner.smoke_failures([ok, sst, lm]) == []
    assert [r["id"] for r in runner.smoke_failures([{**ok, "status": "simpleFoam_FAILED"}, sst, lm])] == [ok["id"]]
    assert [r["id"] for r in runner.smoke_failures([ok, {"id": sst["id"], "status": "RUNNER_EXCEPTION"}, lm])] == [sst["id"]]


def test_parsers_on_real_attempt2_log_excerpts(runner):
    cm = runner.parse_check_mesh("""    cells:            12708
    Max aspect ratio = 797.8572 OK.
    Mesh non-orthogonality Max: 89.938315 average: 7.1987195
   *Number of severely non-orthogonal (> 70 degrees) faces: 116.
 ***Max skewness = 11.667489, 29 highly skew faces detected which may impair the quality of the results
    Cell determinant (wellposedness) : minimum: 3.8133822e-08 average: 0.16977767
 ***Cells with small determinant (< 0.001) found, number of cells: 2359
    Face interpolation weight : minimum: 0.00056169696 average: 0.46449491
    Face volume ratio : minimum: 0.00042150824 average: 0.87173558
 ***Unused points found in the mesh, number unused by faces: 1024 number unused by cells: 1024
Failed 5 mesh checks.
""")
    assert cm["unused_points"] == 1024 and cm["failed_check_counts"] == [5] and not cm["mesh_ok"] and len(cm["diagnostic_lines"]) == 3
    assert float(cm["max_non_orthogonality"]) == pytest.approx(89.938315) and cm["severe_non_orthogonal_faces"] == 116 and float(cm["max_aspect_ratio"]) == pytest.approx(797.8572)
    assert float(cm["min_determinant"]) == pytest.approx(3.8133822e-08) and float(cm["min_face_weight"]) == pytest.approx(0.00056169696) and float(cm["min_volume_ratio"]) == pytest.approx(0.00042150824)
    start = "trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\nTime = 1\n"
    assert runner.parse_solver(start)["sigfpe"] is False                      # attempt 2 counted this startup line as a crash
    assert runner.parse_solver(start + "#1  Foam::sigFpe::sigHandler(int) in /usr/lib/openfoam/libOpenFOAM.so\n")["sigfpe"] is True


def test_mesh_only_registers_every_spec_at_every_height_and_runs_no_solver(runner, tmp_path, monkeypatch):
    import time
    runner.SOURCE = REAL
    specs = runner.make_mesh_specs()
    from scripts import t20_case as T
    assert len(specs) == len(T.MESHES) * len(runner.HEIGHTS) == 25 and len({s["id"] for s in specs}) == 25 and not any(s["solve"] for s in specs)
    assert {(s["mesh"], s["h"]) for s in specs} == {(m, h) for m in T.MESHES for h in runner.HEIGHTS}
    assert all(T.MODELS[s["model"]]["wall"] == T.MESHES[s["mesh"]]["wall"] == s["wall"] for s in specs)
    spec = next(s for s in specs if s["mesh"] == "coa30" and s["h"] == 0.448)
    rec = runner.run_case(spec, REAL, time.monotonic() + 600)
    assert rec["status"] == "MESH_OK" and [s["stage"] for s in rec["stages"]] == ["gmshToFoam", "checkMesh"] and "solver" in rec and rec["solver"]["iterations"] == 0
    kept = Path(runner.OUTPUT) / "cases" / spec["id"]
    assert not (kept / "mesh.msh.gz").exists() and (kept / "log.checkMesh.gz").is_file() and rec["mesh_proxy"]["unused_nodes"] == 0
    table = runner.mesh_table([rec])
    assert spec["id"] in table and "MESH_OK" in table and table.count("\n") == 3
    monkeypatch.setenv("FAKE_BAD_MESH", "1")
    (bad,) = [s for s in specs if s["mesh"] == "med30" and s["h"] == 0.09]
    rec = runner.run_case(bad, REAL, time.monotonic() + 600)
    assert rec["status"] == "MESH_FAILED" and rec["check_mesh"]["unused_points"] == 5
    assert "Unused points" in runner.mesh_table([rec])
