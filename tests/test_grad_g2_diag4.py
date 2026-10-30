"""G2-DIAG4: analyzer classification on synthetic outputs, regression gates, integrity, fail-closed runner, lineage of the job source."""
import glob
import importlib.util
import json
import re
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag4 as A
from tests import grad_g2_diag4_synthetic as S

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts/waterlily_grad_g2_diag4_forced32_horizon_2026_10_09.jl"
STAGES3 = ROOT / "scripts/waterlily_grad_g2_diag3_stages.jl"
G2 = ROOT / "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl"
DIAG2_JOB = ROOT / "scripts/waterlily_grad_g2_diag2_d0_tangent_counterfactual_2026_10_08.jl"
RUNNER = ROOT / "infra/kaggle/kernel_grad_g2_diag4/runner.py"


# ---- the registered windows and gates -------------------------------------------------------------------------------------------------------
def test_registered_windows_and_constants():
    assert A.INTERVALS == ((880, 980), (980, 1100), (1100, 1200), (1200, 1350), (1350, 1500))
    assert len(A.ROLLING) == 25 and A.ROLLING[0] == (800, 900) and A.ROLLING[1] == (825, 925) and A.ROLLING[-1] == (1400, 1500) and all(hi - lo == 100 for lo, hi in A.ROLLING)
    assert (A.GROWTH_SLOPE, A.GROWTH_R2, A.BOX_MAX_GATE, A.GLOBAL_MAX_GATE, A.BOX_ENERGY_FRACTION, A.MIN_POINTS) == (0.02, 0.9, 1e3, 1e6, 0.90, 10)


def test_fit_returns_slope_and_r2():
    xs = list(range(100))
    s, r2 = A.fit(xs, [0.05 * x for x in xs])
    assert s == pytest.approx(0.05) and r2 == pytest.approx(1.0)
    assert A.fit([1, 2, 3], [1, 2, 3])[0] != A.fit([1, 2, 3], [1, 2, 3])[0]        # too few points -> NaN
    s, r2 = A.fit(xs, [(0.5 if i == 50 else 0.0) for i in xs])
    assert r2 < 0.1                                                                  # a single spike is not a trend


# ---- classification --------------------------------------------------------------------------------------------------------------------------
def analyze(tmp_path, monkeypatch, **kw):
    out = S.make_output(tmp_path / "o", monkeypatch=monkeypatch, **kw)
    return out, A.analyze(out)


def test_spiky_but_bounded_forced32_is_no_onset_observed(tmp_path, monkeypatch):
    out, r = analyze(tmp_path, monkeypatch)
    assert r["verdict"] == "FORCED32_NO_ONSET_OBSERVED_TO_1500" and r["control_b0_reproduces_the_corner_mode"] is True and r["regression"]["pass"] is True
    assert r["arms"]["B32fork"]["growth_event"] is False and r["arms"]["B32fork"]["classification"] == "NO_ONSET_OBSERVED_TO_1500"
    assert "not an elimination claim" in r["interpretation"] and "not an AD fix" in r["interpretation"]
    assert r["selected_delta"] is None and r["grad03_verdict"] is None and r["no_bridge_value"] is True and r["forced32_is_a_different_solver_candidate"] is True
    assert A.verify_integrity(out, S.FREEZE)["pass"]


def test_control_b0_growth_is_detected_and_localised_in_the_corner(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch)
    b0 = r["arms"]["B0"]
    assert b0["growth_event"] and b0["magnitude_breach_step"] is not None and 830 < b0["magnitude_breach_step"] < 900
    assert b0["mode"]["evaluated"] and b0["mode"]["median_box_energy_fraction"] >= 0.9 and b0["mode"]["corner_localised"] is True
    assert b0["classification"] == "DELAYED_ONSET"          # the control grows in the corner: the same rule applied to B0


def test_delayed_onset_of_the_corner_mode(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch, fork=S.profile("grow", onset=1200))
    assert r["verdict"] == "FORCED32_DELAYED_ONSET" and r["arms"]["B32fork"]["growth_event"] and r["arms"]["B32fork"]["growth_event_step"] > 1200
    assert "DIAG5" in r["next_decision"]


def test_different_mode_when_the_growth_is_outside_the_corner_box(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch, fork=S.profile("grow", onset=1200, location=S.OUTSIDE))
    assert r["verdict"] == "FORCED32_DIFFERENT_MODE" and r["arms"]["B32fork"]["mode"]["corner_localised"] is False


def test_nonfinite_tangent_is_a_growth_event(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch, fork=S.profile("grow", onset=1200), fork_stops=1300)
    assert r["arms"]["B32fork"]["first_nonfinite_step"] == 1300 and r["arms"]["B32fork"]["growth_event"] and r["verdict"] in ("FORCED32_DELAYED_ONSET", "FORCED32_GROWTH_UNLOCALIZED")


def test_persistent_gate_needs_two_adjacent_windows_and_a_trend_not_a_spike(tmp_path, monkeypatch):
    # a slow genuine trend of 0.03 decade/step over ~150 steps (amplitude stays far below both magnitude gates): two adjacent windows satisfy slope/R2
    slow = S.profile("grow", onset=1000, rate=0.03, spike=False)
    _, r = analyze(tmp_path / "a", monkeypatch, fork=lambda s: (min(slow(s)[0], 5.0), 21.0, S.BODY))
    a = r["arms"]["B32fork"]
    assert a["persistent_declared_at_step"] is not None and a["magnitude_breach_step"] is None and a["growth_event"] is True
    # a single isolated burst is not sustained growth and does not trip the gates
    burst = lambda s: (2.0e-1 if 1100 <= s <= 1110 else 1.3e-2, 21.0, S.BODY)  # noqa: E731
    _, r = analyze(tmp_path / "b", monkeypatch, fork=burst)
    assert r["arms"]["B32fork"]["growth_event"] is False and r["verdict"] == "FORCED32_NO_ONSET_OBSERVED_TO_1500"


def test_growth_below_the_dominance_level_is_unlocalised(tmp_path, monkeypatch):
    slow = S.profile("grow", onset=1000, rate=0.03, spike=False)
    _, r = analyze(tmp_path, monkeypatch, fork=lambda s: (min(slow(s)[0], 5.0), 21.0, S.BODY))
    assert r["arms"]["B32fork"]["mode"]["evaluated"] is False and r["verdict"] == "FORCED32_GROWTH_UNLOCALIZED"


def test_history_dependence_reading_is_secondary_and_mechanical(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch, fresh=S.profile("grow", onset=1100))
    d = r["history_dependence_reading_secondary_only"]
    assert d["fork"] == "NO_ONSET_OBSERVED_TO_1500" and d["fresh"] == "DELAYED_ONSET" and "history" in d["reading"] and r["verdict"] == "FORCED32_NO_ONSET_OBSERVED_TO_1500"   # fresh never changes the primary verdict
    _, r = analyze(tmp_path / "x", monkeypatch, fork=S.profile("grow", onset=1200), fresh=S.profile("grow", onset=1200))
    assert "delay or a transient" in r["history_dependence_reading_secondary_only"]["reading"]


def test_interpretation_follows_the_verdict_and_never_claims_no_onset_when_growth_was_seen(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch, fork=S.profile("grow", onset=1200))
    assert r["verdict"] == "FORCED32_DELAYED_ONSET" and "no onset was observed" not in r["interpretation"] and "delayed" in r["interpretation"]
    _, r = analyze(tmp_path / "d", monkeypatch, fork=S.profile("grow", onset=1200, location=S.OUTSIDE))
    assert "not corner-localised" in r["interpretation"] and "DIAG5" not in r["next_decision"]
    assert set(A.INTERPRETATION) == {"FORCED32_NO_ONSET_OBSERVED_TO_1500", "FORCED32_DELAYED_ONSET", "FORCED32_DIFFERENT_MODE", "FORCED32_GROWTH_UNLOCALIZED"}


def test_history_defects_never_read_as_no_onset(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", monkeypatch=monkeypatch)
    rows = A.read_csv(out / "arm_B32fork.steps.csv")
    assert A.data_defects(rows, A.FORK_STEP + 1) == [] and A.data_defects(rows, 1) == ["first step 781 != 1"]
    gap = rows[:100] + rows[101:]
    assert "steps are not consecutive" in A.data_defects(gap, A.FORK_STEP + 1)
    bad = [dict(r) for r in rows]
    bad[50]["box_max_tangent_u"] = "nan"
    assert "non-numeric tangent maximum on a row flagged finite" in A.data_defects(bad, A.FORK_STEP + 1)
    a = A.analyse_arm(gap, 21.0, A.FORK_STEP + 1)
    assert A.classify_arm(a) == "INCOMPLETE_ARM"


def test_unknown_argmax_location_counts_as_outside_the_box():
    rows = [dict(step=str(s), glob_max_tangent_u="5000", box_max_tangent_u="5000", glob_energy_tangent="1", box_energy_tangent="1", argmax_tangent_u="", nonfinite_primal_u="0",
                 nonfinite_tangent_u="0") for s in range(1, 60)]
    m = A.analyse_arm(rows, 21.0)["mode"]
    assert m["evaluated"] and m["fraction_of_steps_with_argmax_outside_box"] == 1.0 and m["corner_localised"] is False


def test_integrity_requires_a_frozen_analyzer_and_the_kernel_clone_and_independence_records(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", monkeypatch=monkeypatch)
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    assert not A.verify_integrity(out, {**S.FREEZE, "file_hashes": {}})["pass"]
    idx = json.loads((out / "diag_index.json").read_text()); idx["independence_checked"] = False
    (out / "diag_index.json").write_text(json.dumps(idx))
    assert not A.verify_integrity(out, S.FREEZE)["pass"]


def test_synthetic_headers_match_the_job_headers():
    text = JOB.read_text()
    for name, header in (("ARM_HEADER", S.HEADER), ("CMP_HEADER", S.CMP_HEADER)):
        body = re.search(rf"const {name} = \[(.*?)\]\n", text, re.S).group(1)
        names = re.findall(r'"([^"]+)"', body)
        if name == "ARM_HEADER":
            assert names[:22] == header[:22]          # the explicit columns; the checksum columns come from CS_HEADER / VCS_HEADER
        else:
            assert names == header


# ---- gates -------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm", ["B0", "B32fork"])
def test_regression_mismatch_makes_the_run_incomplete(tmp_path, monkeypatch, arm):
    _, r = analyze(tmp_path, monkeypatch, ref_break=arm)
    key = "b0_vs_diag3_straight" if arm == "B0" else "b32fork_vs_diag3_f32"
    assert r["regression"]["pass"] is False and r["regression"][key]["mismatch_steps"] == [900] and r["verdict"] == "DIAG4_INCOMPLETE"


def test_missing_arm_or_failed_control_is_incomplete(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", monkeypatch=monkeypatch)
    (out / "arm_B32fresh.steps.csv").unlink()
    r = A.analyze(out)
    assert r["verdict"] == "DIAG4_INCOMPLETE" and r["missing_arms"] == ["B32fresh"]
    _, r = analyze(tmp_path / "c", monkeypatch, b0=S.profile("stable"))
    assert r["control_b0_reproduces_the_corner_mode"] is False and r["verdict"] == "DIAG4_INCOMPLETE"       # the rules failed on their own control


def test_integrity_status_flags_dryrun_and_frozen_analyzer(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "ok", monkeypatch=monkeypatch)
    assert A.verify_integrity(out, S.FREEZE)["pass"]
    assert any("not COMPLETE" in f for f in A.verify_integrity(S.make_output(tmp_path / "s", status="RUNNING"), S.FREEZE)["failures"])
    assert not A.verify_integrity(S.make_output(tmp_path / "f", flags=dict(S.FLAGS, reverse=True)), S.FREEZE)["pass"]
    assert not A.verify_integrity(S.make_output(tmp_path / "d", dryrun=True), S.FREEZE)["pass"]
    assert any("frozen analyzer" in f for f in A.verify_integrity(out, dict(S.FREEZE, file_hashes={"analyzer": "0" * 64}))["failures"])
    assert any("source_commit" in f for f in A.verify_integrity(out, dict(S.FREEZE, source_commit="b" * 40))["failures"])


def test_analyzer_writes_once_and_a_truncated_index_gives_a_stub(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", monkeypatch=monkeypatch)
    freeze = tmp_path / "freeze.json"; freeze.write_text(json.dumps(S.FREEZE))
    target = tmp_path / "analysis.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(freeze), "--write", str(target)])
    A.main()
    assert json.loads(target.read_text())["integrity"]["pass"] and json.loads(target.read_text())["verdict"] == "FORCED32_NO_ONSET_OBSERVED_TO_1500"
    with pytest.raises(SystemExit):
        A.main()
    broken = S.make_output(tmp_path / "t", monkeypatch=monkeypatch); (broken / "diag_index.json").write_text('{"tier": "G2-DI')
    t2 = tmp_path / "a2.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(broken), "--freeze", str(freeze), "--write", str(t2)])
    with pytest.raises(SystemExit):
        A.main()
    assert json.loads(t2.read_text())["verdict"] == "DIAG4_INCOMPLETE"


def test_primal_comparison_summaries_are_reported(tmp_path, monkeypatch):
    _, r = analyze(tmp_path, monkeypatch)
    c = r["comparisons"]["B32fork_vs_B0"]
    assert c["first_step"] == 781 and c["last_step"] == 1500 and c["rel_l2_u"]["max"] > 0 and c["largest_primal_u_difference"]["index"] == "86;31;25;3"


# ---- lineage of the job source ----------------------------------------------------------------------------------------------------------------
def block(text, name):
    m = re.search(rf"^(?:@fastmath )?function {re.escape(name)}\(.*?^end\n", text, re.S | re.M)
    assert m, name
    return m.group(0)


def test_g2_copies_in_the_job_are_verbatim_and_the_forced_solver_is_the_diag2_one():
    job, g2 = JOB.read_text(), G2.read_text()
    for name in ("load_raw", "build"):
        assert block(job, name) == block(g2, name), name
    for line in ("const SHAPE = (121, 65, 49)", "const ORIGIN = (-1.0, -0.8, -0.6)", "const SPACING = 0.025", "const TRANSITION = Float32(1.1444091796875e-4)",
                 "vp(x::FD.Dual) = (Float64(FD.value(x)), Float64(FD.partials(x, 1)))"):
        assert line in job and line in g2, line
    assert "solver!(b; tol=0.0, itmx=h.itmx)" in STAGES3.read_text() and "solver!(b; tol=poisson.tol, itmx=poisson.itmx)" in (ROOT / "scripts/waterlily_grad_g2_diag2_stages.jl").read_text()
    assert "const FORCED_ITERATIONS = 32" in job and "WaterLily.ForcedSolve(FORCED_ITERATIONS" in job and "tol=" not in job.replace("tol=0", "")
    assert "WaterLily.sim_step!(a.sim)" in job                      # B0: the original semantics
    assert job.count("WaterLily.ForcedSolve(") == 1 and job.count("diag3_mom_step!") == 1


def test_clone_independence_and_fork_ordering_in_the_source():
    t = JOB.read_text()
    assert "phi_dev = to_device(copy(phi_host))" in t                # every simulation owns its geometry
    assert "assert_independent(b0, fresh, fork)" in t and "Base.mightalias" in t
    assert "copyto!(fork.sim.flow.u, to_device(r.u)); copyto!(fork.sim.flow.p, to_device(r.p))" in t and "append!(fork.sim.flow.Δt, copy(b0.sim.flow.Δt))" in t
    assert 'the B32fork clone is not bit-identical to B0 at the fork step' in t
    assert t.index("clone_check") < t.index("compare!(cmp_fork")
    for forbidden in ("clamp(", "clip(", "rescale(", "rescale!(", "renormaliz", "nan_to_num", "isnan("):
        assert forbidden not in t
    assert t.count("DT = FD.Dual{typeof(tag),Float32,1}") == 1 and "D1_filtered" not in t and "P1_upstream" not in t and "D2_filtered" not in t
    assert "DIAG4 dry-run switches are only allowed with DIAG4_BACKEND=cpu" in t
    for pattern, value in ((r"const FORK_STEP = .*? : (\d+)", A.FORK_STEP), (r"const END_STEP = .*? : (\d+)", A.END_STEP), (r"const REF_LAST_STEP = (\d+)", A.REF_LAST_STEP)):
        assert int(re.search(pattern, t).group(1)) == value, pattern
    assert "const SNAPSHOT_STEPS = (1000, 1250, 1500)" in t


# ---- fail-closed runner -----------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("diag4_runner", RUNNER)
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
    spec = importlib.util.spec_from_file_location("diag4_runner_static", RUNNER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert re.search(r'SOURCE_COMMIT = "(PIN_SOURCE_COMMIT|[0-9a-f]{40})"', RUNNER.read_text())
    manifest = json.loads((ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json").read_text())["directions"]
    assert m.DIRECTION_INPUTS == (("D0_interface_offset", manifest["D0_interface_offset"]["sha256_fortran_raw"]),)
    assert {m.SCRIPT, m.STAGES, m.STAGES_DIAG1, m.REF_STRAIGHT, m.REF_F32} <= set(m.PINS) and m.SCRIPT_TIMEOUT_S < m.KERNEL_TIMEOUT_S
    assert "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/kernel_output" in m.SPARSE
    meta = json.loads((RUNNER.parent / "kernel-metadata.json").read_text())
    assert meta["id"].split("/")[1] == re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-") == "cfd-opt-sdf-grad-g2-d0-forced32-horizon-diag4"
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_grad_g2_diag4"}
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
    for k in ("DIAG4_FORK_STEP", "DIAG4_END_STEP", "DIAG4_REF_STRAIGHT", "DIAG4_REF_F32", "DIAG4_NO_REF", "DIAG4_RAISE_STEP"):
        monkeypatch.setenv(k, "1")
    seen = fake_environment(runner, monkeypatch)
    runner.main()
    args, env, timeout = seen[-1]
    assert not any(k.startswith("DIAG4_") and k != "DIAG4_BACKEND" for k in env) and env["DIAG4_BACKEND"] == "cuda"
    assert sum("dir_f4_fortran.raw" in str(a) for a in args) == 1 and timeout <= runner.KERNEL_TIMEOUT_S - runner.MARGIN_S
