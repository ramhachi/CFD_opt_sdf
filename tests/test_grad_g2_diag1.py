"""G2-DIAG1: analyzer classification on synthetic outputs, integrity verification, fail-closed runner, observation-only source checks."""
import glob
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag1 as A
from tests import grad_g2_diag1_synthetic as S

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "scripts/waterlily_grad_g2_diag1_d0_nonfinite_2026_10_08.jl"
STAGES = ROOT / "scripts/waterlily_grad_g2_diag1_stages.jl"
G2 = ROOT / "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl"
RUNNER = ROOT / "infra/kaggle/kernel_grad_g2_diag1/runner.py"


# ---- analyzer: first-bad identity, growth, case and hypothesis classification -------------------------------------------
@pytest.mark.parametrize("scenario,case,h", [
    ("A", "A", {"H1": "supports", "H2": "supports", "H5": "refutes"}),
    ("B", "B", {"H1": "weakly_supports"}),
    ("C", "C", {"H4": "supports", "H1": "refutes"}),
    ("D", "D", {"H3": "supports"}),
    ("E", "E", {"H5": "supports", "H4": "refutes"}),
    ("A_in_solve", "A", {"H1": "supports", "H4": "refutes"}),     # overflow whose first Inf appears in the Poisson solution is still A (A is tested before C)
    ("F", "F", {"H5": "refutes"}),                                 # primal-first failure has its own case
])
def test_case_and_hypothesis_classification(tmp_path, scenario, case, h):
    out = S.make_output(tmp_path / scenario, scenario)
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    r = A.analyze(out)
    assert r["verdict"] == "DIAG_LOCALIZED" and r["verdict_matches_kernel"] and r["first_bad_consistent_with_kernel"]
    assert r["case"] == case
    for k, v in h.items():
        assert r["hypotheses"][k] == v, (k, r["hypotheses"])
    assert set(r["hypotheses"]) >= {f"H{i}" for i in range(1, 7)}
    assert r["hypotheses"]["H6"] == "refutes"
    assert r["selected_delta"] is None and r["grad03_verdict"] is None and r["no_bridge_value"] is True
    assert set(r["qualification_flags"].values()) == {False}


def test_primal_first_failure_is_reported_as_primal(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "f", "F"))
    assert r["failure_identity"]["first_bad_component"] == "primal" and r["failure_identity"]["first_bad_element_class"].startswith("C_")
    assert r["primal_health"]["first_primal_nonfinite"]["stage"] == "project2_bc"


def test_nonfinite_value_repr_is_carried_into_the_identity(tmp_path):
    fi = A.analyze(S.make_output(tmp_path / "o", "A"))["failure_identity"]
    assert fi["first_nonfinite_value"]["tangent_repr"] == "Inf"


def test_partial_outputs_without_index_or_selfcheck_still_analyse_as_incomplete(tmp_path):
    out = S.make_output(tmp_path / "o", "A")
    (out / "diag_index.json").unlink(); (out / "selfcheck.json").unlink()
    r = A.analyze(out)
    assert r["verdict"] == "DIAG_INCOMPLETE" and r["failure_identity"]["first_bad_step"] == 1198
    assert "growth" in r and "poisson" in r


def test_plain_consistency_is_informational(tmp_path):
    out = S.make_output(tmp_path / "o", "A")
    (out / "reference_forces.csv").write_text("step,t_u_l,t_u_l_tan,fx,fy,fz\n8,0.1,0,1.0,2.0,3.0\n16,0.2,0,1.1,2.0,3.0\n")
    (tmp_path / "plain.csv").write_text("step,t_u_l,t_u_l_tan,fx,fy,fz\n8,0.1,0,1.0,2.0,3.0\n16,0.2,0,1.0,2.0,3.0\n")
    pc = A.plain_consistency(out, tmp_path / "plain.csv")
    assert pc["common_steps"] == 2 and abs(pc["worst"]["fx"]["max_relative_difference"] - 0.1) < 1e-12 and pc["worst"]["fx"]["at_step"] == 16
    assert A.plain_consistency(out, None) is None


def test_failure_identity_is_machine_readable_and_complete(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", "A"))
    fi = r["failure_identity"]
    for key in ("first_bad_step", "first_bad_time_step_start_u_l", "first_bad_stage", "first_bad_field", "first_bad_component", "first_bad_index",
                "last_finite_value", "first_nonfinite_value", "first_bad_element_class", "last_fully_finite_stage", "first_nonfinite_stage", "location"):
        assert key in fi, key
    assert (fi["first_bad_step"], fi["first_bad_stage"], fi["first_bad_field"], fi["first_bad_component"]) == (1198, "project2_bc", "u", "tangent")
    assert fi["last_fully_finite_stage"][2] == "project2_solve" and fi["first_nonfinite_stage"][2] == "project2_bc"
    assert fi["first_bad_element_class"].startswith("B_primal_finite_tangent_nonfinite")


def test_growth_patterns_are_distinguished(tmp_path):
    assert A.analyze(S.make_output(tmp_path / "a", "A"))["growth"]["pattern"]["pattern"] == "roughly_exponential"
    assert A.analyze(S.make_output(tmp_path / "b", "B"))["growth"]["pattern"]["pattern"] == "sudden_jump"
    g = A.analyze(S.make_output(tmp_path / "s", "slow"))["growth"]
    assert g["pattern"]["pattern"] in ("slow_monotonic", "roughly_exponential") and len(g["pre_failure_curve"]) == A.PRE_FAILURE_STEPS
    assert all("ratio_to_previous" in p and "log10_maxabs_tangent" in p for p in g["pre_failure_curve"])


def test_primal_finite_tangent_nonfinite_is_reported_as_class_b(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", "A"))
    assert r["primal_health"]["first_primal_nonfinite"] is None
    assert r["failure_identity"]["first_bad_component"] == "tangent"


def test_not_reproduced_is_a_saved_result_without_extension(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", "notrepro"))
    assert r["verdict"] == "DIAG_NOT_REPRODUCED" and "user decision" in r["next_decision"] and "failure_identity" not in r


def test_selfcheck_mismatch_makes_the_run_incomplete_and_supports_h6(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", "A", selfcheck_ok=False))
    assert r["verdict"] == "DIAG_INCOMPLETE" and r["self_check"]["mismatch_steps"] == [500] and r["hypotheses"]["H6"] == "supports"


def test_instrumented_exception_is_incomplete(tmp_path):
    out = S.make_output(tmp_path / "o", "A", exception="boom")
    assert A.analyze(out)["verdict"] == "DIAG_INCOMPLETE"
    assert A.verify_integrity(out, S.FREEZE)["pass"] is True  # ERROR.txt present, DONE absent, consistent


# ---- integrity / terminal verification -----------------------------------------------------------------------------------
def test_integrity_detects_tamper_flags_dryrun_and_done_error_inconsistency(tmp_path):
    out = S.make_output(tmp_path / "ok", "A")
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    bad = S.make_output(tmp_path / "t", "A")
    (bad / "stage_ledger.csv").write_text("tampered\n")
    assert any("SHA mismatch" in f for f in A.verify_integrity(bad, S.FREEZE)["failures"])
    flags = dict(S.FLAGS, reverse=True)
    assert not A.verify_integrity(S.make_output(tmp_path / "f", "A", flags=flags), S.FREEZE)["pass"]
    assert not A.verify_integrity(S.make_output(tmp_path / "d", "A", dryrun=True), S.FREEZE)["pass"]
    both = S.make_output(tmp_path / "b", "A"); (both / "ERROR.txt").write_text("x")
    assert not A.verify_integrity(both, S.FREEZE)["pass"]
    wrong = dict(S.FREEZE, source_commit="b" * 40)
    assert any("source_commit" in f for f in A.verify_integrity(out, wrong)["failures"])
    snap = S.make_output(tmp_path / "sn", "A")
    (snap / "snapshots/step0000.u.raw").write_bytes(b"changed")
    assert any("snapshot SHA mismatch" in f or "manifest SHA mismatch" in f for f in A.verify_integrity(snap, S.FREEZE)["failures"])


def test_analyzer_writes_once(tmp_path, monkeypatch, capsys):
    out = S.make_output(tmp_path / "o", "A")
    freeze = tmp_path / "freeze.json"; freeze.write_text(json.dumps(S.FREEZE))
    target = tmp_path / "analysis.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(freeze), "--write", str(target)])
    A.main()
    assert json.loads(target.read_text())["integrity"]["pass"]
    with pytest.raises(SystemExit):
        A.main()


# ---- diagnostic ledger serialization (header contract between the Julia job and the analyzer) -----------------------------
def test_julia_ledger_headers_match_the_analyzer_contract():
    text = DIAG.read_text()
    stage_header = re.search(r"const STAGE_HEADER = \[(.*?)\]", text, re.S).group(1)
    assert [x.strip().strip('"') for x in stage_header.replace("\n", " ").split(",")] == [
        "step", "stage_idx", "stage", "field", "n", "nonfinite_primal", "nonfinite_tangent", "maxabs_primal", "maxabs_tangent",
        "rms_primal", "rms_tangent", "argmax_primal", "argmax_tangent"]
    assert re.search(r'const POISSON_HEADER = \["step", "stage", "iters", "dt_value", "dt_tangent", "r2_value", "r2_tangent"\]', text)
    assert 'const CS_HEADER = ["step", "u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits"]' in text


# ---- observation-only source checks --------------------------------------------------------------------------------------
def block(text, name):
    m = re.search(rf"^(?:@fastmath )?function {re.escape(name)}\(.*?^end\n", text, re.S | re.M)
    assert m, name
    return m.group(0)


def test_g2_copies_are_verbatim():
    diag, g2 = DIAG.read_text(), G2.read_text()
    for name in ("load_raw", "build", "sample_row"):
        assert block(diag, name) == block(g2, name), name
    for line in ("const SHAPE = (121, 65, 49)", "const ORIGIN = (-1.0, -0.8, -0.6)", "const SPACING = 0.025",
                 "const TRANSITION = Float32(1.1444091796875e-4)", "const SAMPLE_EVERY = 8",
                 "vp(x::FD.Dual) = (Float64(FD.value(x)), Float64(FD.partials(x, 1)))", "vp(x::Real) = (Float64(x), 0.0)",
                 "real_type(::Type{T}) where {T<:Real} = T", "real_type(::Type{<:FD.Dual{Tag,V}}) where {Tag,V} = V"):
        assert line in diag and line in g2, line


def test_no_state_modifying_operation_exists_in_the_diagnostic_code():
    for path in (DIAG, STAGES):
        text = path.read_text()
        for forbidden in ("clamp(", "clip(", "rescale(", "rescale!(", "renormaliz", "nan_to_num", "FD.Partials((zero", "tol=", "itmx="):
            assert forbidden not in text, (path.name, forbidden)
    assert "Float64}" not in DIAG.read_text().split("const DRYRUN")[0]  # no Float64 Dual simulation type is constructed
    assert "D1_filtered" not in DIAG.read_text() and "P1_upstream" not in DIAG.read_text() and "D2_filtered" not in DIAG.read_text()
    assert DIAG.read_text().count("DT = FD.Dual{typeof(tag),Float32,1}") == 1


def split_top(line):
    """Split on ';' outside parentheses (keyword separators inside calls stay)."""
    parts, depth, cur = [], 0, ""
    for ch in line:
        depth += ch in "([{"; depth -= ch in ")]}"
        if ch == ";" and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    return parts + [cur]


def norm_statements(body):
    """Work statements of a function body (signature and closing `end` excluded; probes, @log and the no-op udf! dropped)."""
    out = []
    for line in body.splitlines()[1:-1]:
        line = re.sub(r";udf(,kwargs\.\.\.)?\)", ")", re.sub(r"#.*", "", line))   # the no-op udf keyword of the original calls
        for stmt in (x.strip() for x in split_top(line)):
            if stmt and not stmt.startswith(("@log", "udf!", "probe(", "end")):
                out.append(stmt.replace(" ", ""))
    return out


def probes_in(text, name):
    return [m.group(1) or m.group(2) for m in re.finditer(r"probe\((?:Symbol\(tag, :(_\w+)\)|:(\w+))", block(text, name))]


@pytest.mark.skipif(not glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")), reason="WaterLily 1.8.0 source not installed")
def test_stage_copies_keep_the_statement_order_of_waterlily_flow_jl():
    flow = Path(sorted(glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")))[-1]).read_text()
    mine = STAGES.read_text()
    for orig, copy in {"mom_step!": "diag_mom_step!", "mom_predict!": "diag_mom_predict!", "mom_correct!": "diag_mom_correct!", "mom_project!": "diag_mom_project!"}.items():
        o = norm_statements(re.search(rf"function {re.escape(orig)}\(.*?^end\n", flow, re.S | re.M).group(0))
        c = [re.sub(r"diag_|,probe(,:project\d)?", "", x) for x in norm_statements(block(mine, copy))]
        assert o == c, (orig, o, c)


def test_stage_probe_order_declared_in_the_stage_file():
    t = STAGES.read_text()
    assert "@fastmath function diag_mom_step!" in t   # like mom_step!
    assert probes_in(t, "diag_mom_step!") == ["pre_scale", "cfl", "cfl_dt"]
    assert probes_in(t, "diag_mom_predict!") == ["predict_conv_diff", "predict_accelerate", "predict_bdim", "predict_bc", "predict_exitbc"]
    assert probes_in(t, "diag_mom_correct!") == ["correct_conv_diff", "correct_accelerate", "correct_bdim", "correct_scale", "correct_bc"]
    assert probes_in(t, "diag_mom_project!") == ["_rhs", "_solve", "_gradient", "_bc"]
    step = block(t, "diag_mom_step!")
    calls = re.findall(r"diag_mom_(predict|project|correct)!\(a,(?:b,)?([\w.]+)", step)
    assert [c[0] for c in calls] == ["predict", "project", "correct", "project"] and [c[1] for c in calls][1] == "1"


# ---- fail-closed runner --------------------------------------------------------------------------------------------------
@pytest.fixture()
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("diag1_runner", RUNNER)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path / "out")
    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", lambda **kw: _TD(tmp_path))
    return module


class _TD:
    def __init__(self, base): self.base = base / "work"
    def __enter__(self): self.base.mkdir(exist_ok=True); return str(self.base)
    def __exit__(self, *a): return False


def fake_environment(module, monkeypatch, *, code=0, tamper=False, make_snapshots=False):
    source = module.OUT.parent / "src"
    for rel in module.PINS:
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(b"x")
    monkeypatch.setattr(module, "PINS", {rel: __import__("hashlib").sha256(b"x" + (b"!" if tamper else b"")).hexdigest() for rel in module.PINS})
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-x, 15360 MiB, 580\n")
    monkeypatch.setattr(module, "fetch_source", lambda base: (source, True))
    monkeypatch.setattr(module, "install_julia", lambda base: Path("julia"))
    seen = []

    def fake_run(args, log, env=None, timeout=0, cwd=None):
        seen.append((args, env))
        Path(log).write_text("log\n")
        if "diagnostic" in str(log) and make_snapshots:
            (module.OUT / "snapshots").mkdir(exist_ok=True); (module.OUT / "snapshots/a.raw").write_bytes(b"1")
        return code if "diagnostic" in str(log) else 0
    monkeypatch.setattr(module, "run", fake_run)
    return seen


def test_runner_pins_are_d0_only_and_well_formed():
    text = RUNNER.read_text()
    assert re.search(r'SOURCE_COMMIT = "(PIN_SOURCE_COMMIT|[0-9a-f]{40})"', text)
    spec = importlib.util.spec_from_file_location("diag1_runner_static", RUNNER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    manifest = json.loads((ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json").read_text())["directions"]
    assert m.DIRECTION_INPUTS == (("D0_interface_offset", manifest["D0_interface_offset"]["sha256_fortran_raw"]),)
    assert {m.SCRIPT, m.STAGES} <= set(m.PINS)
    meta = json.loads((RUNNER.parent / "kernel-metadata.json").read_text())
    assert meta["id"].split("/")[1] == re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-") == "cfd-opt-sdf-grad-g2-d0-nonfinite-diag1"
    assert meta["dataset_sources"] == [] and meta["enable_gpu"] and meta["machine_shape"] == "NvidiaTeslaT4"
    other = json.loads((ROOT / "infra/kaggle/kernel_grad_g2_bridge/kernel-metadata.json").read_text())
    assert meta["id"] != other["id"]


def test_success_writes_done_and_manifest_covers_snapshots(runner, monkeypatch):
    fake_environment(runner, monkeypatch, make_snapshots=True)
    runner.main()
    assert (runner.OUT / "DONE").is_file() and not (runner.OUT / "ERROR.txt").exists()
    files = json.loads((runner.OUT / "output_manifest.json").read_text())["files"]
    assert "snapshots/a.raw" in files and "output_manifest.json" not in files


@pytest.mark.parametrize("kind", ["script_nonzero", "pin_mismatch"])
def test_failure_exits_nonzero_writes_error_and_never_done(runner, monkeypatch, kind):
    fake_environment(runner, monkeypatch, code=2 if kind == "script_nonzero" else 0, tamper=(kind == "pin_mismatch"))
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code not in (0, None)
    assert (runner.OUT / "ERROR.txt").is_file() and not (runner.OUT / "DONE").exists()
    assert json.loads((runner.OUT / "run_identity.json").read_text())["failure_stage"] is not None


def test_runner_forbids_dryrun_switches_and_passes_only_d0(runner, monkeypatch):
    monkeypatch.setenv("DIAG1_INJECT", "1:measure:sigma:primal_nan"); monkeypatch.setenv("DIAG1_HORIZON_STEPS", "3")
    seen = fake_environment(runner, monkeypatch)
    runner.main()
    args, env = seen[-1]
    assert "DIAG1_INJECT" not in env and "DIAG1_HORIZON_STEPS" not in env and env["DIAG1_BACKEND"] == "cuda"
    assert sum("dir_f4_fortran.raw" in str(a) for a in args) == 1 and "D0_interface_offset" in str(args[-2])


def test_non_t4_and_exhausted_budget_fail_closed(runner, monkeypatch):
    fake_environment(runner, monkeypatch)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **k: "0, Tesla V100, GPU-x, 16384 MiB, 580\n")
    with pytest.raises(SystemExit):
        runner.main()
    assert not (runner.OUT / "DONE").exists()
    shutil.rmtree(runner.OUT)
    fake_environment(runner, monkeypatch)
    monkeypatch.setattr(runner, "KERNEL_TIMEOUT_S", 300)
    with pytest.raises(SystemExit):
        runner.main()
    assert not (runner.OUT / "DONE").exists()
