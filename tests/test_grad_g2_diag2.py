"""G2-DIAG2: analyzer classification on synthetic outputs, integrity, fail-closed runner, counterfactual isolation in the source."""
import glob
import importlib.util
import json
import re
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag2 as A
from tests import grad_g2_diag2_synthetic as S

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts/waterlily_grad_g2_diag2_d0_tangent_counterfactual_2026_10_08.jl"
STAGES2 = ROOT / "scripts/waterlily_grad_g2_diag2_stages.jl"
STAGES1 = ROOT / "scripts/waterlily_grad_g2_diag1_stages.jl"
DIAG1_JOB = ROOT / "scripts/waterlily_grad_g2_diag1_d0_nonfinite_2026_10_08.jl"
G2 = ROOT / "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl"
RUNNER = ROOT / "infra/kaggle/kernel_grad_g2_diag2/runner.py"


# ---- analyzer ---------------------------------------------------------------------------------------------------------------
def test_slope_and_class_rules():
    xs = list(range(880, 981))
    assert abs(A.fit_slope(xs, [0.09 * x for x in xs]) - 0.09) < 1e-12
    c = A.classify
    assert c(0.005, 0.005, 0.09, 0.09, None) == "suppresses" and c(0.04, 0.04, 0.09, 0.09, None) == "reduces" and c(0.08, 0.08, 0.09, 0.09, None) == "no_effect"
    assert c(0.0, 0.0, 0.09, 0.09, 950) == "diverged" and c(float("nan"), 0.0, 0.09, 0.09, None) == "undetermined" and c(0.0, float("nan"), 0.09, 0.09, None) == "undetermined"
    assert c(0.045, 0.045, 0.09, 0.09, None) == "reduces" and c(0.0451, 0.045, 0.09, 0.09, None) == "no_effect"      # boundary: <= 0.5 * s0


def test_a_slowed_mode_hidden_under_the_near_body_floor_is_not_called_suppressed(tmp_path):
    # global max flat (the mode is still below the body floor) but the corner box keeps growing at 0.02 decade/step
    out = S.make_output(tmp_path / "o", {"V1b_poisson_n16": 0.0}, boxslopes={"V1b_poisson_n16": 0.02})
    v = A.analyze(out)["variants"]["V1b_poisson_n16"]
    assert v["slope_decade_per_step"] == pytest.approx(0.0, abs=1e-9) and v["box_slope_decade_per_step"] == pytest.approx(0.02, abs=1e-6) and v["class"] == "reduces"
    out = S.make_output(tmp_path / "p", {"V1b_poisson_n16": 0.0}, boxslopes={"V1b_poisson_n16": 0.06})
    assert A.analyze(out)["variants"]["V1b_poisson_n16"]["class"] == "no_effect"
    out = S.make_output(tmp_path / "q", {"V1b_poisson_n16": 0.0}, boxslopes={"V1b_poisson_n16": 0.0})
    assert A.analyze(out)["variants"]["V1b_poisson_n16"]["class"] == "suppresses"


def test_v0_must_run_to_the_end(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", stopped={"V0_baseline": 900}))
    assert r["v0"]["complete_run"] is False and r["verdict"] == "DIAG2_INCOMPLETE"


def test_julia_constants_are_pinned_to_the_analyzer():
    t = JOB.read_text()
    for pattern, value in ((r"const FORK_STEP = .*? : (\d+)", A.FORK_STEP), (r"const N_STEPS = .*? : (\d+)", A.END_STEP - A.FORK_STEP),
                           (r"const BASELINE_MIN_SLOPE = ([\d.]+)", A.BASELINE_MIN_SLOPE), (r"const SUPPRESS_SLOPE = ([\d.]+)", A.SUPPRESS_SLOPE),
                           (r"const REDUCE_FACTOR = ([\d.]+)", A.REDUCE_FACTOR)):
        assert float(re.search(pattern, t).group(1)) == value, pattern
    assert "const SLOPE_FROM = FORK_STEP + N_STEPS ÷ 2" in t and A.SLOPE_FROM == A.FORK_STEP + (A.END_STEP - A.FORK_STEP) // 2
    assert "n < (DRYRUN ? 3 : 10) && return NaN" in t and A.MIN_POINTS == 10 and "1e-300" in t
    assert tuple(re.findall(r"^\s+\(name=\"(V\w+)\"", t, re.M)) == A.VARIANTS


def test_h11_supported_when_forced_poisson_iterations_remove_the_growth(tmp_path):
    out = S.make_output(tmp_path / "o", {"V1b_poisson_n16": 0.0, "V1c_poisson_n32": 0.0, "V1a_poisson_n4": 0.05})
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    r = A.analyze(out)
    assert r["verdict"] == "DIAG2_LOCALIZED" and r["verdict_matches_kernel"] and r["v0"]["bitwise_equal_to_straight"]
    assert r["hypotheses"]["H11"] == "supports" and r["hypotheses"]["H12"] == "refutes" and r["hypotheses"]["H8"] == "refutes"
    assert r["variants"]["V1a_poisson_n4"]["class"] == "no_effect" and r["faces_that_suppress"] == []
    assert any("Poisson stopping rule" in p for p in r["next_experiment_proposal"])


def test_boundary_kill_variants_name_the_face(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", {"V3_kill_corner_box": 0.0, "V4a_kill_slab_xmin": 0.0, "V4d_kill_slabs_all": 0.0, "V4b_kill_slab_ymin": 0.06}))
    assert r["hypotheses"]["H8"] == "supports" and r["faces_that_suppress"] == ["x-min"] and r["variants"]["V4b_kill_slab_ymin"]["class"] == "no_effect"
    assert r["hypotheses"]["H11"] == "refutes" and any("boundary tangent path" in p for p in r["next_experiment_proposal"])


def test_weak_and_unresolved_statuses(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", {"V2_dt_tangent_frozen": 0.04}, stopped={"V6_kill_exit_slab": 900}))
    assert r["hypotheses"]["H12"] == "weakly_supports" and r["hypotheses"]["H7"] == "unresolved" and r["variants"]["V6_kill_exit_slab"]["class"] == "diverged"


def test_nothing_helps_proposes_the_second_wave(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o"))
    assert set(r["hypotheses"][h] for h in ("H11", "H12", "H8", "H7", "H13")) == {"refutes"} and "second wave" in r["next_experiment_proposal"][0]


def test_baseline_not_reproduced_is_saved_without_proposal(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", {"V0_baseline": 0.01}))
    assert r["verdict"] == "DIAG2_NOT_REPRODUCED" and "hypotheses" not in r and "user decision" in r["next_decision"]


def test_v0_mismatch_exception_or_missing_variant_is_incomplete(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "m", v0_mismatch=True))
    assert r["verdict"] == "DIAG2_INCOMPLETE" and r["v0"]["bitwise_equal_to_straight"] is False
    assert A.analyze(S.make_output(tmp_path / "e", exception="boom"))["verdict"] == "DIAG2_INCOMPLETE"
    r = A.analyze(S.make_output(tmp_path / "d", drop="V5_kill_ghost_layers"))
    assert r["verdict"] == "DIAG2_INCOMPLETE" and r["missing_variants"] == ["V5_kill_ghost_layers"]


def test_descriptive_tables_exist(tmp_path):
    v = A.analyze(S.make_output(tmp_path / "o"))["variants"]["V0_baseline"]
    assert set(v["stage_gain_box_mean_last50"]) == {f"{a}->{b}" for a, b in zip(A.STAGES_U, A.STAGES_U[1:])}
    assert v["tangent_relative_residual_first_projection_mean_last50"] == pytest.approx(0.1 / 5.0)
    assert v["primal_relative_residual_first_projection_mean_last50"] == pytest.approx(1e-6 / 1e-3)


def test_integrity_detects_tamper_flags_dryrun_and_registered_window(tmp_path):
    out = S.make_output(tmp_path / "ok")
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    bad = S.make_output(tmp_path / "t"); (bad / "variant_V3_kill_corner_box.steps.csv").write_text("tampered\n")
    assert any("SHA mismatch" in f for f in A.verify_integrity(bad, S.FREEZE)["failures"])
    assert not A.verify_integrity(S.make_output(tmp_path / "f", flags=dict(S.FLAGS, reverse=True)), S.FREEZE)["pass"]
    assert not A.verify_integrity(S.make_output(tmp_path / "d", dryrun=True), S.FREEZE)["pass"]
    assert not A.verify_integrity(S.make_output(tmp_path / "w", forks=(770, 970)), S.FREEZE)["pass"]
    assert any("source_commit" in f for f in A.verify_integrity(out, dict(S.FREEZE, source_commit="b" * 40))["failures"])


def test_analyzer_writes_once(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", {"V1c_poisson_n32": 0.0})
    freeze = tmp_path / "freeze.json"; freeze.write_text(json.dumps(S.FREEZE))
    target = tmp_path / "analysis.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(freeze), "--write", str(target)])
    A.main()
    assert json.loads(target.read_text())["integrity"]["pass"]
    with pytest.raises(SystemExit):
        A.main()


# ---- source: interventions are isolated, V0 is the observation-only baseline -------------------------------------------------
def block(text, name):
    m = re.search(rf"^(?:@fastmath )?function {re.escape(name)}\(.*?^end\n", text, re.S | re.M)
    assert m, name
    return m.group(0)


def test_g2_copies_are_verbatim():
    job, g2 = JOB.read_text(), G2.read_text()
    for name in ("load_raw", "build"):
        assert block(job, name) == block(g2, name), name
    for line in ("const SHAPE = (121, 65, 49)", "const ORIGIN = (-1.0, -0.8, -0.6)", "const SPACING = 0.025", "const TRANSITION = Float32(1.1444091796875e-4)",
                 "vp(x::FD.Dual) = (Float64(FD.value(x)), Float64(FD.partials(x, 1)))", "real_type(::Type{<:FD.Dual{Tag,V}}) where {Tag,V} = V"):
        assert line in job and line in g2, line


def test_variant_table_is_the_registered_one_and_v0_has_no_intervention():
    text = JOB.read_text()
    names = re.findall(r'\(name="([^"]+)", kill=([^,]+), poisson=(nothing|\([^)]*\)), freeze_dt=(\w+)\)', text)
    assert [n[0] for n in names] == list(A.VARIANTS)
    assert names[0] == ("V0_baseline", "nothing", "nothing", "false")          # the baseline has no intervention of any kind
    assert [n[0] for n in names if n[2] != "nothing"] == ["V1a_poisson_n4", "V1b_poisson_n16", "V1c_poisson_n32"]
    assert [n[2] for n in names if n[2] != "nothing"] == [f"(tol=0.0, itmx={k})" for k in (4, 16, 32)]
    assert [n[0] for n in names if n[3] == "true"] == ["V2_dt_tangent_frozen"]
    assert [n[0] for n in names if n[1] != "nothing"] == [v for v in A.VARIANTS if v.startswith(("V3", "V4", "V5", "V6"))]
    assert dict((n[0], n[1]) for n in names if n[1] != "nothing") == {
        "V3_kill_corner_box": ":box", "V4a_kill_slab_xmin": ":xmin", "V4b_kill_slab_ymin": ":ymin", "V4c_kill_slab_zmax": ":zmax",
        "V4d_kill_slabs_all": ":far", "V5_kill_ghost_layers": ":ghost", "V6_kill_exit_slab": ":xmax"}


def test_interventions_only_after_the_fork_and_only_on_a_bc_stage_and_only_when_requested():
    text = JOB.read_text()
    assert "if p.spec.kill !== nothing && p.step > FORK_STEP && stage in KILL_STAGES && haskey(fields, :u)" in text
    assert "const KILL_STAGES = (:predict_bc, :predict_exitbc, :project1_bc, :correct_bc, :project2_bc)" in text
    before_main, main_part = text.split("function main()")
    assert before_main.count("kill_tangent!(") == 2 and before_main.count("freeze_dt!(") == 3   # definition + the probe call; definition + the two call sites
    assert main_part.count("kill_tangent!(") == 2 and "freeze_dt!(" not in main_part             # preflight only
    assert "spec.freeze_dt && freeze_dt!(sim)" in text and "probe.spec.freeze_dt && freeze_dt!(sim)" in text
    # the Poisson counterfactual goes only through solver_step!; nothing else passes tol/itmx
    assert "solver!(b)" in STAGES2.read_text() and "tol=" not in re.sub(r"solver!\(b; tol=poisson.tol, itmx=poisson.itmx\)", "", STAGES2.read_text())
    assert "DIAG2 dry-run switches are only allowed with DIAG2_BACKEND=cpu" in text


def test_no_state_modifying_operation_beyond_the_declared_interventions():
    for path in (JOB, STAGES2):
        t = path.read_text()
        for forbidden in ("clamp(", "clip(", "rescale(", "rescale!(", "renormaliz", "nan_to_num"):
            assert forbidden not in t, (path.name, forbidden)
    t = JOB.read_text()
    assert t.count("DT = FD.Dual{typeof(tag),Float32,1}") == 1 and "D1_filtered" not in t and "P1_upstream" not in t and "D2_filtered" not in t
    assert "Float64}" not in t.split("const DRYRUN")[0]


def split_top(line):
    parts, depth, cur = [], 0, ""
    for ch in line:
        depth += ch in "([{"; depth -= ch in ")]}"
        if ch == ";" and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    return parts + [cur]


def norm_statements(body):
    out = []
    for line in body.splitlines()[1:-1]:
        line = re.sub(r";udf(,kwargs\.\.\.)?\)", ")", re.sub(r"#.*", "", line))
        for stmt in (x.strip() for x in split_top(line)):
            if stmt and not stmt.startswith(("@log", "udf!", "probe(", "end")):
                out.append(stmt.replace(" ", ""))
    return out


@pytest.mark.skipif(not glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")), reason="WaterLily 1.8.0 source not installed")
def test_diag2_stage_copies_keep_the_statement_order_of_waterlily_flow_jl():
    flow = Path(sorted(glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")))[-1]).read_text()
    mine = STAGES2.read_text()
    assert "@fastmath function diag2_mom_step!" in mine
    for orig, copy in {"mom_step!": "diag2_mom_step!", "mom_project!": "diag2_mom_project!"}.items():
        o = norm_statements(re.search(rf"function {re.escape(orig)}\(.*?^end\n", flow, re.S | re.M).group(0))
        c = [re.sub(r"diag2?_|,probe(,:project\d)?(,poisson)?|,poisson|solver_step!\(b,poisson\)", lambda m: "solver!(b)" if m.group(0).startswith("solver_step") else "", x)
             for x in norm_statements(block(mine, copy))]
        c = [x.replace("mom_project!(a,b,1,t₁,:project1)", "mom_project!(a,b,1,t₁)").replace("mom_project!(a,b,0.5,t₁,:project2)", "mom_project!(a,b,0.5,t₁)") for x in c]
        c = [re.sub(r"(mom_project!\(a,b,[\d.]+,t₁),:project\d(,poisson)?\)", r"\1)", x) for x in c]
        o = [x for x in o]
        assert o == c, (orig, o, c)
    assert "solver_step!(b, ::Nothing) = solver!(b)" in mine


# ---- fail-closed runner --------------------------------------------------------------------------------------------------------
@pytest.fixture()
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("diag2_runner", RUNNER)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path / "out")
    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", lambda **kw: _TD(tmp_path))
    return module


class _TD:
    def __init__(self, base): self.base = base / "work"
    def __enter__(self): self.base.mkdir(exist_ok=True); return str(self.base)
    def __exit__(self, *a): return False


def fake_environment(module, monkeypatch, *, code=0, tamper=False):
    source = module.OUT.parent / "src"
    for rel in module.PINS:
        (source / rel).parent.mkdir(parents=True, exist_ok=True); (source / rel).write_bytes(b"x")
    monkeypatch.setattr(module, "PINS", {rel: __import__("hashlib").sha256(b"x" + (b"!" if tamper else b"")).hexdigest() for rel in module.PINS})
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-x, 15360 MiB, 580\n")
    monkeypatch.setattr(module, "fetch_source", lambda base: (source, True))
    monkeypatch.setattr(module, "install_julia", lambda base: Path("julia"))
    seen = []

    def fake_run(args, log, env=None, timeout=0, cwd=None):
        seen.append((args, env)); Path(log).write_text("log\n")
        return code if "diagnostic" in str(log) else 0
    monkeypatch.setattr(module, "run", fake_run)
    return seen


def test_runner_pins_and_identity_are_well_formed():
    spec = importlib.util.spec_from_file_location("diag2_runner_static", RUNNER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert re.search(r'SOURCE_COMMIT = "(PIN_SOURCE_COMMIT|[0-9a-f]{40})"', RUNNER.read_text())
    manifest = json.loads((ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json").read_text())["directions"]
    assert m.DIRECTION_INPUTS == (("D0_interface_offset", manifest["D0_interface_offset"]["sha256_fortran_raw"]),)
    assert {m.SCRIPT, m.STAGES, m.STAGES_DIAG1} <= set(m.PINS)
    meta = json.loads((RUNNER.parent / "kernel-metadata.json").read_text())
    assert meta["id"].split("/")[1] == re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-") == "cfd-opt-sdf-grad-g2-d0-tangent-diag2"
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag2"}
    assert meta["id"] not in used and meta["dataset_sources"] == [] and meta["enable_gpu"] and meta["machine_shape"] == "NvidiaTeslaT4"


def test_success_writes_done_and_failure_never_does(runner, monkeypatch):
    fake_environment(runner, monkeypatch)
    runner.main()
    assert (runner.OUT / "DONE").is_file() and not (runner.OUT / "ERROR.txt").exists()


@pytest.mark.parametrize("kind", ["script_nonzero", "pin_mismatch"])
def test_failure_exits_nonzero_writes_error_and_never_done(runner, monkeypatch, kind):
    fake_environment(runner, monkeypatch, code=2 if kind == "script_nonzero" else 0, tamper=(kind == "pin_mismatch"))
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code not in (0, None) and (runner.OUT / "ERROR.txt").is_file() and not (runner.OUT / "DONE").exists()


def test_runner_strips_dryrun_switches(runner, monkeypatch):
    for k in ("DIAG2_FORK_STEP", "DIAG2_STEPS", "DIAG2_ONLY", "DIAG2_RAISE_VARIANT"):
        monkeypatch.setenv(k, "1")
    seen = fake_environment(runner, monkeypatch)
    runner.main()
    args, env = seen[-1]
    assert not any(k in env for k in ("DIAG2_FORK_STEP", "DIAG2_STEPS", "DIAG2_ONLY", "DIAG2_RAISE_VARIANT")) and env["DIAG2_BACKEND"] == "cuda"
    assert sum("dir_f4_fortran.raw" in str(a) for a in args) == 1 and "D0_interface_offset" in str(args[-2])
