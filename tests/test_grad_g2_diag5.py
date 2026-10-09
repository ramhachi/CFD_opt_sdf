"""G2-DIAG5: analyzer classification on synthetic outputs, integrity, gates, the source lineage of the job, and the fail-closed driver."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_diag5 as A
from tests import grad_g2_diag5_synthetic as S

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts/waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl"
STAGES = ROOT / "scripts/waterlily_grad_g2_diag5_stages.jl"
DRIVER = ROOT / "scripts/run_grad_g2_diag5_local.py"
FLOW = Path.home() / ".julia/packages/WaterLily"


def test_registered_constants_and_matrix():
    assert A.STATES == ("S900", "S1000") and A.EPS_E3 == (1e-6, 1e-5, 1e-4, 1e-3, 1e-2) and A.EPS_E5 == ("1e-5", "1e-4", "1e-3", "1e-2") and A.K_STEPS == 40
    assert (A.AGREE_REL, A.AGREE_COS, A.AGREE_RATIO) == (0.10, 0.99, (0.95, 1.05)) and A.FD_LOWER_FACTOR == 0.5 and A.FD_MATCH == (0.7, 1.3) and A.LINEAR_AMPLITUDE == 0.1
    assert len(A.expected_groups()) == 1 + 2 * 10 and A.expected_groups()[0] == ("R1188", "E0")


def test_fit_and_rate():
    xs = list(range(50)); assert A.fit(xs, [0.05 * x for x in xs])[0] == pytest.approx(0.05) and A.fit([1, 2], [1, 2])[0] != A.fit([1, 2], [1, 2])[0]
    rows = [{"step": k, "l2_box": 10 ** (0.1 * k)} for k in range(41)]
    assert A.rate(rows, 20)["rate"] == pytest.approx(0.1) and A.rate(rows, 3)["rate"] != A.rate(rows, 3)["rate"]      # too few points -> NaN
    fd = [{"step": k, "bmax": 10 ** (0.1 * k)} for k in range(41)]
    assert A.linear_range(fd, 1e-3) == 20 and A.linear_range(fd, 1e-5) == 40               # eps * bmax <= 0.1


@pytest.mark.parametrize("scenario,label", [("R1", "R1_SELECTOR_CONVENTION"), ("R2", "R2_LINEARISATION_DEFECT"), ("R3", "R3_FINITE_INSTABILITY"), ("R4", "R4_INCONCLUSIVE")])
def test_scenarios_classify_as_registered(tmp_path, scenario, label):
    out = S.make_output(tmp_path / "o", scenario)
    r = A.analyze(out)
    assert r["gates"]["pass"] is True and r["labels"] == {"S900": label, "S1000": label} and r["verdict"] == label
    assert r["selected_delta"] is None and r["grad03_verdict"] is None and r["no_bridge_value"] is True and set(r["qualification_flags"].values()) == {False}
    assert A.verify_integrity(out, S.freeze_for(A.__file__))["pass"]


def test_interpretations_are_bounded_and_never_claim_a_bug_or_a_gradient():
    for text in A.INTERPRETATION.values():
        low = text.lower()
        for bad in ("is an ad bug", "the correct derivative", "full-field ad is impossible", "smooth map is unstable", "gradient is qualified"):
            assert bad not in low, bad
    assert "bounded No-Go" in A.INTERPRETATION["R4_INCONCLUSIVE"] and "not a statement about full-field AD in general" in A.INTERPRETATION["R4_INCONCLUSIVE"]
    assert "not an AD bug" in A.INTERPRETATION["R1_SELECTOR_CONVENTION"] and "finite-perturbation instability" in A.INTERPRETATION["R3_FINITE_INSTABILITY"]


def test_the_two_states_must_agree(tmp_path):
    out = S.make_output(tmp_path / "o", "R1")
    rows = A.read_csv(out / A.tag("S1000", "E3") / "e3_rows.csv")
    other = S.make_output(tmp_path / "p", "R3")
    (out / A.tag("S1000", "E3") / "e3_rows.csv").write_text((other / A.tag("S1000", "E3") / "e3_rows.csv").read_text())
    for e in A.EPS_E5:
        (out / A.tag("S1000", f"E5FD:{e}") / "e5fd_rows.csv").write_text((other / A.tag("S1000", f"E5FD:{e}") / "e5fd_rows.csv").read_text())
    r = A.analyze(out)
    assert r["labels"]["S900"] == "R1_SELECTOR_CONVENTION" and r["labels"]["S1000"] == "R3_FINITE_INSTABILITY" and r["verdict"] == "R4_INCONCLUSIVE" and rows


@pytest.mark.parametrize("gate", ["e0", "e3", "e5ad", "ident", "fd_incomplete", "dt"])
def test_a_failed_gate_makes_the_run_incomplete(tmp_path, gate):
    out = S.make_output(tmp_path / "o", "R3", break_gate=gate)
    r = A.analyze(out)
    assert r["gates"]["pass"] is False and r["verdict"] == "DIAG5_INCOMPLETE"


def test_integrity_status_dryrun_flags_threads_and_frozen_analyzer(tmp_path):
    out = S.make_output(tmp_path / "o", "R3")
    fz = S.freeze_for(A.__file__)
    assert A.verify_integrity(out, fz)["pass"]
    assert not A.verify_integrity(out, {**fz, "file_hashes": {}})["pass"]
    assert not A.verify_integrity(out, {**fz, "pins": {"scripts/y.jl": "22" * 32}})["pass"]
    assert not A.verify_integrity(out, {**fz, "source_commit": "b" * 40})["pass"]
    bad = S.make_output(tmp_path / "d", "R3", dryrun=True)
    assert not A.verify_integrity(bad, fz)["pass"]
    st = json.loads((out / A.tag("S900", "E6") / "status.json").read_text()); st["threads"] = 4
    (out / A.tag("S900", "E6") / "status.json").write_text(json.dumps(st))
    assert not A.verify_integrity(out, fz)["pass"]
    st["threads"] = 1; st["qualification_flags"]["reverse"] = True
    (out / A.tag("S900", "E6") / "status.json").write_text(json.dumps(st))
    assert not A.verify_integrity(out, fz)["pass"]
    (out / A.tag("S900", "E2") / "result.json").unlink()
    assert any("missing output" in f for f in A.verify_integrity(out, fz)["failures"])
    (out / "DONE").unlink()
    assert any("exactly one of DONE" in f for f in A.verify_integrity(out, fz)["failures"])


def test_the_analyzer_writes_once(tmp_path, monkeypatch):
    out = S.make_output(tmp_path / "o", "R1")
    fz = tmp_path / "freeze.json"; fz.write_text(json.dumps(S.freeze_for(A.__file__)))
    target = tmp_path / "a.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(fz), "--write", str(target)])
    A.main()
    assert json.loads(target.read_text())["verdict"] == "R1_SELECTOR_CONVENTION"
    with pytest.raises(SystemExit):
        A.main()


def test_descriptive_summaries_are_reported(tmp_path):
    out = S.make_output(tmp_path / "o", "R1")
    d = A.analyze(out)["states"]["S900"]["descriptive"]
    assert d["stage_l2_box_over_input"][0]["stage"] == "predict_bdim" and d["conv_diff_closure_rel"]["predict_conv"] == pytest.approx(1e-8) and d["e6"]["gain_range"] == pytest.approx([1.1, 1.14])


# ---- lineage of the job source ---------------------------------------------------------------------------------------------------------------------
def test_limiter_variants_keep_the_value_and_only_replace_the_partials():
    text = STAGES.read_text()
    assert "m = quick(u, c, d)" in text and "ForwardDiff.value(m)" in text and text.count("quick(u, c, d)") >= 3
    assert "@fastmath function diag5_mom_step!" in text and text.count("@fastmath") == 2           # the comment and the step function only
    for forbidden in ("clamp", "isnan", "isfinite", "nextfloat", "zero(", "sanitize", "Float64"):
        if forbidden == "zero(":
            continue
        assert forbidden not in text.split("# ---- the instrumented step")[1], forbidden


def test_instrumented_step_has_the_statement_order_of_mom_step():
    text = STAGES.read_text()
    flow = next(FLOW.glob("*/src/Flow.jl"), None)
    if flow is None:
        pytest.skip("WaterLily source not installed")
    src = flow.read_text()
    def order(t, names):
        pos = [t.index(n) for n in names]
        assert pos == sorted(pos), names
    order(src, ["conv_diff!(a.f,a.u⁰", "accelerate!(a.f,t₀", "BDIM!(a); BC!(a.u,a.uBC,a.exitBC,a.perdir,t₁)", "exitBC!(a.u,a.u⁰,a.Δt[end])", "conv_diff!(a.f,a.u,a.σ", "BDIM!(a); scale_u!(a,0.5)"])
    order(text, ["conv_diff!(a.f,a.u⁰", "accelerate!(a.f,t₀", "BDIM!(a)\n    probe(:predict_bdim", "BC!(a.u,a.uBC,a.exitBC,a.perdir,t₁)", "exitBC!(a.u,a.u⁰,a.Δt[end])", "conv_diff!(a.f,a.u,a.σ", "scale_u!(a,0.5)"])
    assert "a.u⁰ .= a.u; scale_u!(a,0); t₁ = sum(a.Δt); t₀ = t₁-a.Δt[end]" in text and "push!(a.Δt,CFL(a))" in text


def test_conv_diff5_is_a_copy_of_conv_diff_with_split_roles():
    text = STAGES.read_text()
    flow = next(FLOW.glob("*/src/Flow.jl"), None)
    if flow is None:
        pytest.skip("WaterLily source not installed")
    src = flow.read_text()
    for stmt in ("Φ[I] = ϕu(j,CI(I,i),u,ϕ(i,CI(I,j),u),λ) - ν*∂(j,CI(I,i),u)", "r[I-δ(j,I),i] -= Φ[I] over I ∈ inside_u(N,j)", "slice(N,2,j,2)", "slice(N,N[j],j,2)"):
        assert stmt in src
    for stmt in ("Φ[I] = ϕu(j,CI(I,i),ufld,ϕ(i,CI(I,j),uadv),λ) - ν*∂(j,CI(I,i),uvis)", "r[I-δ(j,I),i] -= Φ[I] over I ∈ inside_u(N,j)", "slice(N,2,j,2)", "slice(N,N[j],j,2)"):
        assert stmt in text


def test_job_constants_match_the_analyzer_and_the_prohibitions_hold():
    text = JOB.read_text()
    assert re.search(r"const EPS_E3 = \(1e-6, 1e-5, 1e-4, 1e-3, 1e-2\)", text) and re.search(r"const EPS_E5 = \(1e-5, 1e-4, 1e-3, 1e-2\)", text) and "K_STEPS = DRYRUN && haskey(ENV, \"DIAG5_K\") ? parse(Int, ENV[\"DIAG5_K\"]) : 40" in text
    assert "const BOXR = (1:12, 1:8, 49:56)" in text and "EPS_E5_VARIANT_B = (1e-4, 1e-3)" in text and "TIE_TAUS = (1f-5, 1f-4)" in text
    assert "ENSEMBLE_N = DRYRUN && haskey(ENV, \"DIAG5_ENSEMBLE\") ? parse(Int, ENV[\"DIAG5_ENSEMBLE\"]) : 16" in text
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    for forbidden in ("bridge_value", "g_forward", "selected_delta =", "clamp(", "isnan"):
        assert forbidden not in code, forbidden
    assert text.count("Float64") > 0 and "dual_sim(c::Ctx; seed_scale=0.0)" in text                   # Float64 only in statistics / the direction arithmetic, never a Float64 simulation
    assert "T=Float64" not in text and "build(c.phi, Float32, c.case)" in text
    assert "(group == \"E0\") == (state == \"R1188\")" in text and "refusing to overwrite" in text


def test_driver_pins_and_fail_closed(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("driver5", DRIVER)
    drv = importlib.util.module_from_spec(spec); spec.loader.exec_module(drv)
    assert len(drv.MATRIX) == 21 and drv.MATRIX[0] == ("R1188", "E0") and drv.tag("S900", "E5FD:1e-3") == "S900_E5FD_1e-3"
    assert drv.SRC_TREE in drv.PINS and drv.sha256(ROOT / drv.SRC_TREE) == drv.sha256(ROOT / drv.SRC_TREE) and len(drv.sha256(ROOT / drv.SRC_TREE)) == 64
    assert drv.PHI_SHA == "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431" and drv.D0_SHA == "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"
    out = tmp_path / "out"
    monkeypatch.setattr(drv, "PINS", {drv.JOB: "0" * 64})          # a mismatching pin: nothing runs (the real pins would start the real matrix)
    monkeypatch.setattr("sys.argv", ["x", "--snapdir", str(tmp_path), "--out", str(out)])
    with pytest.raises(SystemExit):
        drv.main()
    assert (out / "ERROR.txt").is_file() and not (out / "DONE").exists()
    monkeypatch.setattr("sys.argv", ["x", "--snapdir", str(tmp_path), "--out", str(out)])
    with pytest.raises(SystemExit):
        drv.main()                                          # refuses to overwrite


def test_driver_writes_done_only_when_every_process_completed(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("driver5b", DRIVER)
    drv = importlib.util.module_from_spec(spec); spec.loader.exec_module(drv)
    monkeypatch.setattr(drv, "PINS", {})
    monkeypatch.setattr(drv, "git_state", lambda: ("h", []))
    results = []
    def fake(julia, snapdir, out, state, group):
        ok = not (state == "S900" and group == "E6")
        results.append((state, group))
        return {"state": state, "group": group, "exit": 0 if ok else 2, "ok": ok, "seconds": 0.0}
    monkeypatch.setattr(drv, "run_one", fake)
    out = tmp_path / "o"
    monkeypatch.setattr("sys.argv", ["x", "--snapdir", str(tmp_path), "--out", str(out), "--jobs", "2"])
    with pytest.raises(SystemExit):
        drv.main()
    assert len(results) == 21 and (out / "ERROR.txt").is_file() and not (out / "DONE").exists()
    out2 = tmp_path / "o2"
    monkeypatch.setattr(drv, "run_one", lambda *a: {"state": a[3], "group": a[4], "exit": 0, "ok": True, "seconds": 0.0})
    monkeypatch.setattr("sys.argv", ["x", "--snapdir", str(tmp_path), "--out", str(out2)])
    drv.main()
    assert (out2 / "DONE").is_file() and json.loads((out2 / "driver_index.json").read_text())["status"] == "COMPLETE"


# ---- the cases the reviewer asked for ----------------------------------------------------------------------------------------------------------------
def classify(tmp_path, scenario, **kw):
    return A.analyze(S.make_output(tmp_path / "o", scenario, **kw))


def test_julia_style_keys_and_real_dry_run_output_pass_the_e3_gates():
    assert S.jstr(1e-6) == "1.0e-6" and S.jstr(1e-5) == "1.0e-5" and S.jstr(1e-4) == "0.0001" and S.jstr(1e-2) == "0.01"
    base = ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09/cpu_dryrun_diagnostic/S100_E3"
    if not base.is_dir():
        pytest.skip("dry-run evidence not copied yet")
    assert A.primal_bits_ok(json.loads((base / "result.json").read_text()))
    rows = A.read_csv(base / "e3_rows.csv")
    assert len(rows) == A.E3_ROWS and {(float(r["eps"]), r["lambda"], r["region"]) for r in rows} == {(e, lam, reg) for e in A.EPS_E3 for lam in A.LAMBDAS for reg in ("box", "interior")}
    assert A.e3_rows_complete(rows) is False          # step 100 has (almost) no corner tangent: the box gain is Inf/NaN and the gate must refuse it


def test_a_missing_or_nonfinite_e3_row_fails_the_gate_and_never_classifies(tmp_path):
    r = classify(tmp_path, "R3", drop_e3_eps=1e-4)
    assert r["gates"]["pass"] is False and r["verdict"] == "DIAG5_INCOMPLETE"
    r = classify(tmp_path / "n", "R3", nan_row=True)
    assert r["gates"]["pass"] is False and r["verdict"] == "DIAG5_INCOMPLETE"


def test_e6_must_have_the_registered_ensemble_size(tmp_path):
    assert classify(tmp_path, "R3", e6_n=2)["verdict"] == "DIAG5_INCOMPLETE"


def test_decaying_ad_and_fd_growth_never_makes_r3_or_r1(tmp_path):
    r = classify(tmp_path, "R3", overrides=dict(ad_rate=-0.1, fd_rate=-0.1, tie_rate=-0.1))
    assert r["verdict"] == "R4_INCONCLUSIVE"
    r = classify(tmp_path / "b", "R1", overrides=dict(ad_rate=-0.05, fd_rate=0.03, tie_rate=0.03))
    assert r["verdict"] == "R4_INCONCLUSIVE"


@pytest.mark.parametrize("override", [dict(tie_rel=0.5),                 # the surrogate does not close the mismatch
                                      dict(fd_rate=0.08),                # the finite growth is not clearly lower than the AD growth
                                      dict(tie_rate=0.1),                # the surrogate does not reproduce the finite growth
                                      dict(rel_by_eps={1e-6: 0.7, 1e-5: 0.7, 1e-4: 0.7, 1e-3: 0.7, 1e-2: 0.7}, flip_by_eps={1e-6: 0.2, 1e-5: 0.2, 1e-4: 0.2, 1e-3: 0.2, 1e-2: 0.2})])  # no flip dependence
def test_r1_needs_every_condition(tmp_path, override):
    assert classify(tmp_path, "R1", overrides=override)["verdict"] == "R4_INCONCLUSIVE"


def test_r1_is_not_reached_when_the_baseline_already_agrees(tmp_path):
    r = classify(tmp_path, "R1", overrides=dict(rel_by_eps={1e-6: 0.01, 1e-5: 0.02, 1e-4: 0.03, 1e-3: 0.04, 1e-2: 0.9}, tie_rel=0.01, fd_rate=0.1, tie_rate=0.1))
    assert r["verdict"] != "R1_SELECTOR_CONVENTION"


def test_r2_is_reached_only_when_a_smooth_amplitude_exists(tmp_path):
    r = classify(tmp_path, "R2")
    assert r["states"]["S900"]["r2_testable"] is True and r["verdict"] == "R2_LINEARISATION_DEFECT"
    flips = {e: 0.2 for e in A.EPS_E3}                                    # every amplitude has branch flips: a mismatch is not attributed to a defect
    r = classify(tmp_path / "f", "R2", overrides=dict(flip_by_eps=flips))
    assert r["states"]["S900"]["r2_testable"] is False and r["verdict"] != "R2_LINEARISATION_DEFECT"


def test_large_amplitude_nonlinearity_alone_is_not_r2(tmp_path):
    r = classify(tmp_path, "R3", overrides=dict(rel_by_eps={1e-6: 0.03, 1e-5: 0.03, 1e-4: 0.03, 1e-3: 0.03, 1e-2: 0.8}, flip_by_eps={e: 0.0 for e in A.EPS_E3}))
    assert r["verdict"] == "R3_FINITE_INSTABILITY"


def test_a_missing_mid_amplitude_cannot_give_r3_through_the_remaining_ones(tmp_path):
    out = S.make_output(tmp_path / "o", "R3")
    assert A.analyze(out)["verdict"] == "R3_FINITE_INSTABILITY"
    e3, fd, ad, e6, e3c = A.load_state(out, "S900")
    e3.pop(1e-4)
    assert A.classify_state(e3, fd, ad, e6, e3c)["label"] != "R3_FINITE_INSTABILITY"


def test_states_that_disagree_r1_with_r2_are_inconclusive(tmp_path):
    out = S.make_output(tmp_path / "o", "R1")
    other = S.make_output(tmp_path / "p", "R2")
    (out / A.tag("S1000", "E3") / "e3_rows.csv").write_text((other / A.tag("S1000", "E3") / "e3_rows.csv").read_text())
    r = A.analyze(out)
    assert r["labels"]["S1000"] == "R2_LINEARISATION_DEFECT" and r["verdict"] == "R4_INCONCLUSIVE"


def test_check_mode_writes_nothing_and_an_integrity_failure_writes_no_labels(tmp_path, monkeypatch, capsys):
    out = S.make_output(tmp_path / "o", "R1")
    fz = tmp_path / "freeze.json"; fz.write_text(json.dumps(S.freeze_for(A.__file__)))
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(fz), "--check"])
    A.main()
    assert json.loads(capsys.readouterr().out)["gates"]["pass"] is True
    (out / "DONE").unlink()
    target = tmp_path / "a.json"
    monkeypatch.setattr("sys.argv", ["x", "--out-dir", str(out), "--freeze", str(fz), "--write", str(target)])
    with pytest.raises(SystemExit):
        A.main()
    rep = json.loads(target.read_text())
    assert rep["verdict"] == "DIAG5_INCOMPLETE" and "labels" not in rep and "states" not in rep


def test_spearman_and_ranks():
    assert A.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0) and A.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert A.spearman([1, 2, 3], [1, 2, 3]) != A.spearman([1, 2, 3], [1, 2, 3])        # fewer than four points: NaN
    assert A.ranks([5, 1, 1, 3]) == [4.0, 1.5, 1.5, 3.0]


def test_driver_refuses_a_dirty_tree_or_an_unknown_source_commit(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("driver5c", DRIVER)
    drv = importlib.util.module_from_spec(spec); spec.loader.exec_module(drv)
    monkeypatch.setattr(drv, "SOURCE_COMMIT", "0" * 40)
    head, bad = drv.git_state()
    assert head and any("pinned source commit" in b for b in bad)          # a commit that is not an ancestor of HEAD
    monkeypatch.setattr(drv, "PINS", {drv.JOB: "0" * 64})
    monkeypatch.setattr("sys.argv", ["x", "--snapdir", str(tmp_path), "--out", str(tmp_path / "o")])
    with pytest.raises(SystemExit):
        drv.main()
    assert "pinned source commit" in (tmp_path / "o" / "ERROR.txt").read_text()


def test_driver_strips_the_dry_run_switches_and_requires_a_registered_status(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("driver5d", DRIVER)
    drv = importlib.util.module_from_spec(spec); spec.loader.exec_module(drv)
    seen = {}
    class Done:
        returncode = 0
    def fake_run(cmd, stdout=None, stderr=None, env=None):
        seen["env"] = env
        out = Path(cmd[-3]); out.mkdir(parents=True, exist_ok=True)           # the job's outdir is the third argument from the end (outdir, state, group)
        (out / "result.json").write_text("{}"); (out / "status.json").write_text(json.dumps({"status": "COMPLETE", "dryrun": True, "k_steps": 3}))
        return Done()
    monkeypatch.setenv("DIAG5_DRYRUN", "1")
    monkeypatch.setattr(drv.subprocess, "run", fake_run)
    (tmp_path / "o").mkdir()
    r = drv.run_one("julia", tmp_path, tmp_path / "o", "S900", "E6")
    assert not any(k.startswith("DIAG5_") for k in seen["env"]) and r["ok"] is False                 # a dry-run status is never accepted
