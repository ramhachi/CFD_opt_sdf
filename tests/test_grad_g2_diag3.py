"""G2-DIAG3: analyzer classification / plateau / selection on synthetic outputs, integrity, fail-closed runner, tangent-only isolation in the source."""
import glob
import importlib.util
import json
import re
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag3 as A
from tests import grad_g2_diag3_synthetic as S

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts/waterlily_grad_g2_diag3_poisson_tangent_2026_10_08.jl"
STAGES3 = ROOT / "scripts/waterlily_grad_g2_diag3_stages.jl"
FIXTURE = ROOT / "scripts/waterlily_grad_g2_diag3_fixture.jl"
FIXTURE_TEST = ROOT / "scripts/test_grad_g2_diag3_poisson_fixture.jl"
G2 = ROOT / "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl"
RUNNER = ROOT / "infra/kaggle/kernel_grad_g2_diag3/runner.py"
TH = ["A1_tau_1e-4", "A1_tau_1e-5", "A1_tau_1e-6", "A1_tau_1e-7"]
CYC = {"A1_tau_1e-4": 2, "A1_tau_1e-5": 3, "A1_tau_1e-6": 4, "A1_tau_1e-7": 6}


# ---- classification, plateau, selection (the pre-registered rules) ----------------------------------------------------------
def test_suppression_gate_slope_endpoint_and_box_slope():
    c = A.classify
    assert c(0.004, 0.004, 21.0, 0.1, 0.1, 21.0, None) == "suppresses"
    assert c(0.006, 0.004, 21.0, 0.1, 0.1, 21.0, None) == "reduces"         # global slope above 0.005
    assert c(0.004, 0.006, 21.0, 0.1, 0.1, 21.0, None) == "reduces"         # box slope above 0.005 (mode hidden under the floor)
    assert c(0.004, 0.004, 42.1, 0.1, 0.1, 21.0, None) == "reduces"         # endpoint above 2 x floor
    assert c(0.051, 0.051, 1e12, 0.1, 0.1, 21.0, None) == "no_effect" and c(0.05, 0.05, 1e12, 0.1, 0.1, 21.0, None) == "reduces"
    assert c(0.0, 0.0, 21.0, 0.1, 0.1, 21.0, 950) == "diverged" and c(float("nan"), 0.0, 21.0, 0.1, 0.1, 21.0, None) == "undetermined"


def test_plateau_needs_three_consecutive_settings():
    ok = lambda *names: {n: n in names for n in TH}  # noqa: E731
    assert A.plateau_members(TH, ok("A1_tau_1e-6")) == []
    assert A.plateau_members(TH, ok("A1_tau_1e-4", "A1_tau_1e-6", "A1_tau_1e-7")) == []                    # not consecutive
    assert A.plateau_members(TH, ok("A1_tau_1e-5", "A1_tau_1e-6", "A1_tau_1e-7")) == TH[1:]
    assert A.plateau_members(TH, ok(*TH)) == TH


def test_selection_rule_margin_fewest_cycles_tie_tighter():
    ok = {n: True for n in TH}
    assert A.select_candidate(TH, ok, CYC) == "A1_tau_1e-5"                  # the loosest member has no looser neighbour, so it is excluded
    ok = {n: n != "A1_tau_1e-4" for n in TH}
    assert A.select_candidate(TH, ok, CYC) == "A1_tau_1e-6"
    assert A.select_candidate(TH, {n: n == "A1_tau_1e-6" for n in TH}, CYC) is None
    assert A.select_candidate(TH, {n: True for n in TH}, {n: 5 for n in TH}) == "A1_tau_1e-7"   # tie -> tighter


# ---- stage A verdicts --------------------------------------------------------------------------------------------------------------
def test_plateau_gives_causal_support_and_selects_a_threshold_candidate(tmp_path):
    out = S.make_output(tmp_path / "o", suppress=TH[1:], cycles=CYC, stage_b={})
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    r = A.analyze(out)
    assert r["verdict"] == "TANGENT_ONLY_CAUSAL_SUPPORT" and r["verdict_matches_kernel"] and r["classes_match_kernel"] and r["selection_matches_kernel"]
    assert r["stage_a"]["selected_candidate"] == "A1_tau_1e-6" and r["stage_a"]["baseline"]["identity_and_complete"] is True
    assert r["stage_b_verdict"] == "DIAG3_LONG_HORIZON_STABLE" and r["next_experiment_proposal"][0].startswith("propose a G2 bridge retry")
    assert r["selected_delta"] is None and r["grad03_verdict"] is None and r["no_bridge_value"] is True and set(r["qualification_flags"].values()) == {False}


def test_a_fixed_count_plateau_alone_supports_but_selects_no_stage_b_candidate(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=("A1_n24", "A1_n28", "A1_n32")))
    assert r["verdict"] == "TANGENT_ONLY_CAUSAL_SUPPORT" and r["stage_a"]["plateau"]["count"] == ["A1_n24", "A1_n28", "A1_n32"] and r["stage_a"]["selected_candidate"] is None
    assert r["stage_b_verdict"] == "SKIPPED_NO_CANDIDATE"


def test_isolated_suppression_is_no_support(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=("A1_n32", "A1_tau_1e-6")))
    assert r["verdict"] == "TANGENT_ONLY_NO_SUPPORT" and r["stage_a"]["plateau"] == {"threshold": [], "count": []}
    assert r["next_experiment_proposal"][0].startswith("tangent-only continuation does not remove")


def test_an_arm_that_changes_the_primal_cannot_support(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=TH[1:], broken_identity=("A1_tau_1e-6",)))
    assert r["stage_a"]["arms"]["A1_tau_1e-6"]["primal_value_identity"] is False and r["verdict"] == "TANGENT_ONLY_NO_SUPPORT"
    # the secondary Dual-stop arm may change the primal; that never counts as tangent-only support
    r = A.analyze(S.make_output(tmp_path / "d", suppress=("D_tau_1e-5", "D_tau_1e-6", "D_tau_1e-7"), broken_identity=("D_tau_1e-5", "D_tau_1e-6", "D_tau_1e-7")))
    assert r["verdict"] == "TANGENT_ONLY_NO_SUPPORT"


def test_baseline_gates(tmp_path):
    assert A.analyze(S.make_output(tmp_path / "a", a0_mismatch=True))["verdict"] == "DIAG3_INCONCLUSIVE"
    assert A.analyze(S.make_output(tmp_path / "b", slopes={"A0_baseline": 0.01}))["verdict"] == "DIAG3_NOT_REPRODUCED"
    assert A.analyze(S.make_output(tmp_path / "c", exception="boom"))["verdict"] == "DIAG3_INCONCLUSIVE"
    assert A.analyze(S.make_output(tmp_path / "d", stopped={"A0_baseline": 900}))["verdict"] == "DIAG3_INCONCLUSIVE"


def test_endpoint_floor_blocks_suppression(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=TH[1:], endpoints={"A1_tau_1e-6": 43.0}, cycles=CYC))
    assert r["stage_a"]["arms"]["A1_tau_1e-6"]["class"] == "reduces" and r["stage_a"]["plateau"]["threshold"] == []


def test_primal_drift_and_descriptive_tables(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=TH[1:]))
    d = r["stage_a"]["primal_drift_vs_straight"]["F32_forced_dual_32"]
    assert d["max_rel_l2_u"] == pytest.approx(1e-3) and d["max_rel_fx"] == pytest.approx(0.01) and d["max_rel_fz"] == 0.0
    a = r["stage_a"]["arms"]["A1_tau_1e-6"]
    assert a["tangent_relative_residual_before_mean"] == pytest.approx(0.02) and a["tangent_relative_residual_after_demeaned_mean"] == pytest.approx(1e-5)


# ---- stage B gates ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kw,expected", [({}, "DIAG3_LONG_HORIZON_STABLE"), ({"box_max": 2e3}, "DIAG3_LONG_HORIZON_NOT_STABLE"), ({"glob_max": 2e6}, "DIAG3_LONG_HORIZON_NOT_STABLE"),
                                          ({"completed": False}, "DIAG3_LONG_HORIZON_NOT_STABLE"), ({"nonfinite": True}, "DIAG3_LONG_HORIZON_NOT_STABLE"),
                                          ({"sample_failure": True}, "DIAG3_LONG_HORIZON_NOT_STABLE"), ({"host_mismatch": True}, "DIAG3_LONG_HORIZON_NOT_STABLE"),
                                          ({"primal_scale": 1.01}, "DIAG3_LONG_HORIZON_NOT_STABLE")])
def test_stage_b_gates(tmp_path, kw, expected):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=TH[1:], cycles=CYC, stage_b=kw))
    assert r["stage_b_verdict"] == expected
    if expected.endswith("NOT_STABLE"):
        assert r["next_experiment_proposal"] == ["dig further into the Poisson / linearized-solver semantics (the short-horizon support did not hold over the full horizon)"] or r["stage_b_verdict"] == expected


def test_a_cut_or_failed_stage_b_is_inconclusive_not_a_scientific_verdict(tmp_path):
    for name, kw in (("cut", {"cut_stage_b": True}), ("exc", {"stage_b_exception": True})):
        out = S.make_output(tmp_path / name, suppress=TH[1:], cycles=CYC, **kw)
        assert any("not COMPLETE" in f for f in A.verify_integrity(out, S.FREEZE)["failures"])      # only a COMPLETE kernel run passes the terminal verification
        r = A.analyze(out)
        assert r["verdict"] == "DIAG3_INCONCLUSIVE" and r["stage_b_verdict"] == "DIAG3_INCONCLUSIVE" and r["stage_a_verdict"] == "TANGENT_ONLY_CAUSAL_SUPPORT"
        assert "user decision required" in r["next_experiment_proposal"][0]


def test_count_only_plateau_asks_the_user(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=("A1_n24", "A1_n28", "A1_n32")))
    assert r["stage_b_verdict"] == "SKIPPED_NO_CANDIDATE" and "user decision required" in r["next_experiment_proposal"][0]


def test_cap_fraction_and_achieved_residual_are_reported(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=TH[1:], cycles={"A1_tau_1e-7": 32}))     # 32 + 32 = 64 per call pair is not a cap hit; the cap is 64 per projection
    a = r["stage_a"]["arms"]
    assert a["A1_tau_1e-6"]["fraction_of_projections_at_the_cycle_cap"] == 0.0 and a["A1_tau_1e-6"]["median_achieved_rel_after_demeaned"] == pytest.approx(1e-5)
    r = A.analyze(S.make_output(tmp_path / "p", suppress=TH[1:], cycles={"A1_tau_1e-7": 64}))
    assert r["stage_a"]["arms"]["A1_tau_1e-7"]["fraction_of_projections_at_the_cycle_cap"] == 1.0 and r["stage_a"]["arms"]["A1_n04"]["fraction_of_projections_at_the_cycle_cap"] is None


def test_the_frozen_analyzer_hash_is_checked(tmp_path):
    out = S.make_output(tmp_path / "o")
    good = dict(S.FREEZE, file_hashes={"analyzer": S.sha(Path(A.__file__))})
    assert A.verify_integrity(out, good)["pass"]
    assert any("frozen analyzer" in f for f in A.verify_integrity(out, dict(S.FREEZE, file_hashes={"analyzer": "0" * 64}))["failures"])


def test_stage_b_reports_tangent_finiteness_but_no_tangent_values(tmp_path):
    r = A.analyze(S.make_output(tmp_path / "o", suppress=TH[1:], cycles=CYC, stage_b={}))
    b = r["stage_b"]
    assert b["tangent_window_means_finite"] is True
    assert set(b) == {"kernel", "steps", "finite_all_steps", "max_box_max_tangent_u", "max_glob_max_tangent_u", "window_slopes_box_decade_per_step_500_step_windows", "tangent_cycles_mean",
                      "host_recomputation_matches_kernel", "tangent_window_means_finite", "primal_window_mean_rel_diff_vs_g2_plain", "primal_gate_pass", "host_notes", "verdict"}
    assert "dual_time" not in json.dumps(b) and "frozen_time" not in json.dumps(b)


# ---- integrity ---------------------------------------------------------------------------------------------------------------------------
def test_integrity_detects_tamper_flags_dryrun_window_and_inventory(tmp_path):
    out = S.make_output(tmp_path / "ok", suppress=TH[1:])
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    bad = S.make_output(tmp_path / "t"); (bad / "arm_A1_n08.steps.csv").write_text("tampered\n")
    assert any("SHA mismatch" in f for f in A.verify_integrity(bad, S.FREEZE)["failures"])
    assert not A.verify_integrity(S.make_output(tmp_path / "f", flags=dict(S.FLAGS, reverse=True)), S.FREEZE)["pass"]
    assert not A.verify_integrity(S.make_output(tmp_path / "d", dryrun=True), S.FREEZE)["pass"]
    assert any("source_commit" in f for f in A.verify_integrity(out, dict(S.FREEZE, source_commit="b" * 40))["failures"])
    both = S.make_output(tmp_path / "b"); (both / "ERROR.txt").write_text("x")
    assert not A.verify_integrity(both, S.FREEZE)["pass"]


def test_analyzer_writes_once_and_leaves_a_stub_on_truncated_index(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", suppress=TH[1:], cycles=CYC)
    freeze = tmp_path / "freeze.json"; freeze.write_text(json.dumps(S.FREEZE))
    target = tmp_path / "analysis.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(freeze), "--write", str(target)])
    A.main()
    assert json.loads(target.read_text())["integrity"]["pass"]
    with pytest.raises(SystemExit):
        A.main()
    broken = S.make_output(tmp_path / "t"); (broken / "diag_index.json").write_text('{"tier": "G2-DI')
    t2 = tmp_path / "a2.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(broken), "--freeze", str(freeze), "--write", str(t2)])
    with pytest.raises(SystemExit):
        A.main()
    assert json.loads(t2.read_text())["verdict"] == "DIAG3_INCONCLUSIVE"


# ---- source: the tangent-only arm never writes the primal ------------------------------------------------------------------------------------
def block(text, name):
    m = re.search(rf"^(?:@fastmath )?function {re.escape(name)}\(.*?^end\n", text, re.S | re.M)
    assert m, name
    return m.group(0)


def test_g2_copies_in_the_job_are_verbatim():
    job, g2 = JOB.read_text(), G2.read_text()
    for name in ("load_raw", "build", "sample_row", "window_mean", "summarize", "write_history"):
        assert block(job, name) == block(g2, name), name
    for line in ("const SHAPE = (121, 65, 49)", "const ORIGIN = (-1.0, -0.8, -0.6)", "const SPACING = 0.025", "const TRANSITION = Float32(1.1444091796875e-4)",
                 "const SAMPLE_EVERY = 8", "const WINDOW = (80.0, 120.0)", 'const SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")'):
        assert line in job and line in g2 or line == 'const WINDOW = (80.0, 120.0)' and line in job, line


def test_tangent_refine_writes_only_the_tangent_part_of_x():
    t = block(STAGES3.read_text(), "(h::TangentRefine)")  if False else STAGES3.read_text()
    body = re.search(r"function \(h::TangentRefine\)\(b\).*?^end\n", t, re.S | re.M).group(0)
    assert body.count("solver!(b)") == 1 and body.index("solver!(b)") < body.index("residual!(p)")              # the primal solve is the unchanged WaterLily one
    assigns = re.findall(r"^\s*(?:b\.x|p\.x|aux\.x|aux\.z|p\.r)\b.*?=.*$", body, re.M)
    writes_to_primal = [a for a in assigns if "b.x" in a or "p.x" in a]
    assert writes_to_primal == ["        b.x .= h.add_tan.(b.x, aux.x)                  # tangent part only; the primal bytes of x are not touched"]
    assert re.search(r"add_tan.*?FD\.value\(x\)", FIXTURE.read_text(), re.S) and "FD.Dual{T,V,1}(FD.value(x)" in FIXTURE.read_text()
    assert "tol=" not in body and "itmx" not in body.replace("maxit", "")


def test_arm_table_and_dry_run_guards():
    t = JOB.read_text()
    for expr in ('[(name="A0_baseline", kind=:none, tau=0.0, n=0)]', 'kind=:refine_threshold, tau=t, n=0) for t in TAUS]', 'kind=:refine_count, tau=0.0, n=n) for n in COUNTS]',
                 'kind=:dual_stop, tau=t, n=0) for t in TAUS]', '(name="F32_forced_dual_32", kind=:forced, tau=0.0, n=32)'):
        assert expr in t, expr
    assert "const TAUS = (1e-4, 1e-5, 1e-6, 1e-7)" in t and "const COUNTS = (1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64)" in t
    assert tuple(A.TAUS) == (1e-4, 1e-5, 1e-6, 1e-7) and tuple(A.COUNTS) == (1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64)
    assert "DIAG3 dry-run switches are only allowed with DIAG3_BACKEND=cpu" in t
    for pattern, value in ((r"const FORK_STEP = .*? : (\d+)", A.FORK_STEP), (r"const N_STEPS = .*? : (\d+)", A.N_STEPS), (r"const BASELINE_MIN_SLOPE = ([\d.]+)", A.BASELINE_MIN_SLOPE),
                           (r"const SUPPRESS_SLOPE = ([\d.]+)", A.SUPPRESS_SLOPE), (r"const FLOOR_FACTOR = ([\d.]+)", A.FLOOR_FACTOR), (r"const REDUCE_FACTOR = ([\d.]+)", A.REDUCE_FACTOR),
                           (r"const MAX_TANGENT_CYCLES = (\d+)", A.MAX_TANGENT_CYCLES), (r"const PLATEAU_RUN = (\d+)", A.PLATEAU_RUN), (r"const LONG_BOX_MAX = ([\d.e+]+)", A.LONG_BOX_MAX),
                           (r"const LONG_GLOBAL_MAX = ([\d.e+]+)", A.LONG_GLOBAL_MAX)):
        assert float(re.search(pattern, t).group(1)) == value, pattern
    assert "const SLOPE_FROM = FORK_STEP + N_STEPS ÷ 2" in t and "1e-300" in t and "n < (DRYRUN ? 3 : 10) && return NaN" in t


def test_no_forbidden_operations_and_no_other_directions():
    for path in (JOB, STAGES3, FIXTURE):
        t = path.read_text()
        for forbidden in ("clamp(", "clip(", "rescale(", "rescale!(", "renormaliz", "nan_to_num", "Float64}"):
            assert forbidden not in t.replace("Float64}()", "").replace("NTuple{7,Float64}", "").replace("Dict{String,Float64}", "").replace("Vector{Float64}", "").replace("Vector{Vector{Float64}}", ""), (path.name, forbidden)
    t = JOB.read_text()
    assert t.count("DT = FD.Dual{typeof(tag),Float32,1}") == 1 and "D1_filtered" not in t and "P1_upstream" not in t and "D2_filtered" not in t


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
def test_diag3_stage_copies_keep_the_statement_order_of_waterlily_flow_jl():
    flow = Path(sorted(glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")))[-1]).read_text()
    mine = STAGES3.read_text()
    assert "@fastmath function diag3_mom_step!" in mine and "solve_step!(b, ::Nothing) = solver!(b)" in mine
    for orig, copy in {"mom_step!": "diag3_mom_step!", "mom_project!": "diag3_mom_project!"}.items():
        o = norm_statements(re.search(rf"function {re.escape(orig)}\(.*?^end\n", flow, re.S | re.M).group(0))
        c = [re.sub(r"diag3?_", "", re.sub(r",probe(,:project\d)?(,hook)?", "", x)).replace("solve_step!(b,hook)", "solver!(b)") for x in norm_statements(block(mine, copy))]
        c = [re.sub(r"(mom_project!\(a,b,[\d.]+,t₁),:project\d(,hook)?\)", r"\1)", x) for x in c]
        c = [re.sub(r",hook\)", ")", x) for x in c]
        assert o == c, (orig, o, c)


def test_fixture_evidence_pins_the_mathematics():
    ev = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/fixture_results.json"
    if not ev.is_file():
        pytest.skip("fixture results not stored yet")
    d = json.loads(ev.read_text())
    assert d["limit_equivalence"]["tangent_rel_error_vs_converged_dual_modulo_constant"] < 1e-9 and d["limit_equivalence"]["primal_bytes_unchanged"] is True
    assert d["residual_evaluator"]["tangent_residual_rel_diff_vs_finite_difference"] < 1e-5 and d["residual_evaluator"]["max_tangent_residual"] > 1e-2
    assert all(v["tangent_rel_diff_dual_vs_tangent_only"] < 1e-12 and v["cycles_run"] == int(k) for k, v in d["k_cycles_equal"].items())
    t = d["truncated_case"]
    assert all(v["primal_bytes_unchanged"] and v["ghost_tangent_unchanged"] for v in t.values()) and t["tau1e-12_cap5"]["cycles"] == 5 and t["fixed7"]["cycles"] == 7
    assert t["tau1e-3"]["cycles"] < t["tau1e-6"]["cycles"] and t["tau1e-6"]["rel_after_demeaned"] <= 1e-6 and d["hook"]["primal_equals_plain_solver"] is True
    assert all(v["aux_operator_matches"] and v["primal_cycles"] == 1 for v in t.values()) and d["dual_stop"]["rel_after_demeaned"] <= 1e-6 and d["dual_stop"]["primal_cycles"] > 1
    assert d["residual_evaluator"]["dA_x_term_relative_to_tangent_residual"] > 1.0 and d["residual_evaluator"]["finite_difference_would_miss_dA_x_by"] > 1.0   # the finite-difference check is sensitive to dA x
    g = d["gauge"]
    assert g["primal_mean_abs"] < g["2eps"] and abs(g["tangent_mean_of_residual_before"] - g["tangent_mean_of_residual_after_30_dual_cycles"]) < 1e-9   # the Dual path never removes the tangent mean
    assert g["refine_rel_after_active_demeaned"] < 1e-6 and g["refine_rel_after_raw"] > 1e-2 and abs(g["refine_active_mean_removed"] - 0.5) < 1e-9


# ---- fail-closed runner --------------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("diag3_runner", RUNNER)
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
        seen.append((args, env, timeout)); Path(log).write_text("log\n")
        return code if "diagnostic" in str(log) else 0
    monkeypatch.setattr(module, "run", fake_run)
    return seen


def test_runner_pins_identity_and_budget_are_well_formed():
    spec = importlib.util.spec_from_file_location("diag3_runner_static", RUNNER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert re.search(r'SOURCE_COMMIT = "(PIN_SOURCE_COMMIT|[0-9a-f]{40})"', RUNNER.read_text())
    manifest = json.loads((ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json").read_text())["directions"]
    assert m.DIRECTION_INPUTS == (("D0_interface_offset", manifest["D0_interface_offset"]["sha256_fortran_raw"]),)
    assert {m.SCRIPT, m.STAGES, m.STAGES_DIAG1, m.FIXTURE} <= set(m.PINS) and m.KERNEL_TIMEOUT_S == 9000 and m.SCRIPT_TIMEOUT_S < m.KERNEL_TIMEOUT_S
    meta = json.loads((RUNNER.parent / "kernel-metadata.json").read_text())
    assert meta["id"].split("/")[1] == re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-") == "cfd-opt-sdf-grad-g2-d0-tangent-poisson-diag3"
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag3"}
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


def test_runner_strips_dryrun_switches_and_clamps_the_timeout(runner, monkeypatch):
    for k in ("DIAG3_FORK_STEP", "DIAG3_STEPS", "DIAG3_ONLY", "DIAG3_STAGE_B_STEPS", "DIAG3_FORCE_SELECT", "DIAG3_RAISE_ARM"):
        monkeypatch.setenv(k, "1")
    seen = fake_environment(runner, monkeypatch)
    runner.main()
    args, env, timeout = seen[-1]
    assert not any(k.startswith("DIAG3_") and k != "DIAG3_BACKEND" for k in env) and env["DIAG3_BACKEND"] == "cuda"
    assert sum("dir_f4_fortran.raw" in str(a) for a in args) == 1 and "D0_interface_offset" in str(args[-2]) and timeout <= runner.KERNEL_TIMEOUT_S - runner.MARGIN_S
