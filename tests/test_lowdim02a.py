"""LOWDIM-02A (#49): the Stage A contract, the analyzer on synthetic outputs, the registered inputs and the fail-closed runner."""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_lowdim02a as A  # noqa: E402
import build_lowdim02a_kernel as B  # noqa: E402
import lowdim02a_synthetic as SYN  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf import lowdim02a_contract as C  # noqa: E402

E = ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
INV = json.loads((E / "inventory.json").read_text())
L1 = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
L1INV = json.loads((L1 / "inventory.json").read_text())
BASELINE_RAW = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"


# ---- the contract ---------------------------------------------------------------------------------------------------------------------------------------------------------
def v(base=(0.36, 0.35), rep=(0.36, 0.35), plus=(0.3602, 0.3499), minus=(0.359, 0.3499), gates=True):
    f = lambda t: {"downforce_n": t[0], "drag_n": t[1]}  # noqa: E731
    return C.stage_a_verdict(f(base), f(rep), f(plus), f(minus), gates)


def test_a_resolved_positive_gain_with_the_drag_control_and_gates_is_a_pass():
    r = v()
    assert r["verdict"] == "STAGE_A_PASS" and r["downforce_gain_n"] == pytest.approx(2e-4) and r["control_resolvably_loses_downforce"] and r["drag_constraint_ok"]


def test_a_resolved_loss_is_a_sign_flip_and_a_small_change_is_unresolved():
    assert v(plus=(0.36 - 1e-4, 0.35))["verdict"] == "STAGE_A_SIGN_FLIP"
    assert v(plus=(0.36 + 2e-5, 0.35))["verdict"] == "STAGE_A_UNRESOLVED" and v(plus=(0.36 - 2e-5, 0.35))["verdict"] == "STAGE_A_UNRESOLVED"
    z = lambda plus, minus=-1.0, rep=0.0, drag=0.0: C.stage_a_verdict({"downforce_n": 0.0, "drag_n": 0.0}, {"downforce_n": rep, "drag_n": 0.0}, {"downforce_n": plus, "drag_n": drag},  # noqa: E731
                                                                      {"downforce_n": minus, "drag_n": 0.0}, True)
    assert z(C.MIN_RESOLVED_N)["verdict"] == "STAGE_A_UNRESOLVED" and z(-C.MIN_RESOLVED_N)["verdict"] == "STAGE_A_UNRESOLVED"        # exactly at the resolution is not resolved
    assert z(C.MIN_RESOLVED_N * 1.0001)["verdict"] == "STAGE_A_PASS" and z(-C.MIN_RESOLVED_N * 1.0001)["verdict"] == "STAGE_A_SIGN_FLIP"


def test_a_resolved_gain_with_a_failed_condition_is_a_constraint_fail_and_never_a_pass():
    assert v(plus=(0.3602, 0.35 + 1e-3))["verdict"] == "STAGE_A_CONSTRAINT_FAIL"                          # the drag grew
    assert v(minus=(0.36 + 2e-4, 0.35))["verdict"] == "STAGE_A_CONSTRAINT_FAIL"                          # the reverse control is not worse than the forward step
    assert v(minus=(0.36 + 1.5e-4, 0.35))["verdict"] == "STAGE_A_CONSTRAINT_FAIL"                        # the reverse control GAINS too: a pure even (curvature) response is no pass
    assert v(minus=(0.36 - 2e-5, 0.35))["verdict"] == "STAGE_A_CONSTRAINT_FAIL"                          # the control loses by less than the resolution
    z = lambda minus, drag=0.0: C.stage_a_verdict({"downforce_n": 0.0, "drag_n": 0.0}, {"downforce_n": 0.0, "drag_n": 0.0}, {"downforce_n": 1e-3, "drag_n": drag}, {"downforce_n": minus, "drag_n": 0.0}, True)  # noqa: E731
    assert z(-C.MIN_RESOLVED_N)["verdict"] == "STAGE_A_CONSTRAINT_FAIL" and z(-C.MIN_RESOLVED_N * 1.0001)["verdict"] == "STAGE_A_PASS"      # the control boundary is strict
    assert z(-1e-3, drag=C.MIN_RESOLVED_N)["verdict"] == "STAGE_A_PASS" and z(-1e-3, drag=C.MIN_RESOLVED_N * 1.0001)["verdict"] == "STAGE_A_CONSTRAINT_FAIL"   # the drag boundary is inclusive
    assert v(gates=False)["verdict"] == "STAGE_A_CONSTRAINT_FAIL"


def test_the_odd_and_even_parts_and_the_resolution_source_are_reported_and_a_sign_flip_does_not_assert_its_cause():
    r = C.stage_a_verdict({"downforce_n": 0.0, "drag_n": 0.0}, {"downforce_n": 0.0, "drag_n": 0.0}, {"downforce_n": -1e-4, "drag_n": 0.0}, {"downforce_n": -1.3e-3, "drag_n": 0.0}, True)
    assert r["verdict"] == "STAGE_A_SIGN_FLIP" and r["odd_part_n"] == pytest.approx(6e-4) and r["even_part_n"] == pytest.approx(-7e-4) and r["odd_part_resolved_positive"] is True    # the odd part survived
    assert r["resolution_source"] == "nominal_floor"
    r2 = C.stage_a_verdict({"downforce_n": 0.0, "drag_n": 0.0}, {"downforce_n": 1e-4, "drag_n": 0.0}, {"downforce_n": 5e-3, "drag_n": 0.0}, {"downforce_n": -5e-3, "drag_n": 0.0}, True)
    assert r2["resolution_source"] == "repeat_noise" and r2["marginal"] is False and C.stage_a_verdict(*[{"downforce_n": x, "drag_n": 0.0} for x in (0.0, 0.0, 4e-5, -1e-3)], True)["marginal"] is True


def test_the_baseline_repeat_raises_the_resolution_and_non_finite_responses_raise():
    assert C.resolution_n(0.0) == pytest.approx(3e-5) and C.resolution_n(1e-4) == pytest.approx(1e-3) and C.resolution_n(-1e-4) == pytest.approx(1e-3)
    assert v(rep=(0.36 + 5e-5, 0.35))["verdict"] == "STAGE_A_UNRESOLVED"                                  # a 2e-4 gain is below 10 x 5e-5
    with pytest.raises(ValueError):
        v(plus=(float("nan"), 0.35))


# ---- the analyzer on synthetic outputs ------------------------------------------------------------------------------------------------------------------------------
def run(tmp_path, **kw):
    out, freeze, inv = SYN.make_all(tmp_path, **kw)
    return A.analyze(out, freeze, inventory=inv, formal=SYN.FORMAL), out, freeze, inv


def test_the_default_synthetic_run_is_a_pass_and_carries_the_descriptive_comparison(tmp_path):
    r, *_ = run(tmp_path)
    assert r["verdict"] == "STAGE_A_PASS" and r["integrity"]["pass"] is True and r["qualification_flags"] == {k: False for k in A.FLAGS} and r["selected_delta"] is None and r["not_grid01"]
    d = r["descriptive_comparison_with_flow_24"]
    assert d["resolved_sign_positive_on_flow32"]["+1.25"] is True and d["resolved_sign_positive_on_flow32"]["-1.25"] is False and d["resolved_sign_positive_on_flow24"]["+1.25"] is True
    assert d["flow32_over_flow24_downforce_change"]["+1.25"] == pytest.approx(2e-4 / 4.0517653513449936e-4, rel=1e-6) and "+2.5" not in d["flow32_over_flow24_downforce_change"]
    assert d["odd_part_n"]["flow_32"] == pytest.approx(6e-4) and d["baseline_downforce_n"]["relative_difference"] == pytest.approx(0.0894, abs=1e-3) and "byte-identical" in r["interpretation"] and "no flow_32 noise evidence" in r["interpretation"]
    assert d["baseline_repeat_forces_csv_byte_identical"] is True and r["stage_a"]["downforce_gain_n"] == pytest.approx(2e-4, rel=1e-6)


def test_each_verdict_is_reachable_through_the_analyzer(tmp_path):
    assert run(tmp_path / "a", plus=-1e-3)[0]["verdict"] == "STAGE_A_SIGN_FLIP"
    assert run(tmp_path / "b", plus=1e-5)[0]["verdict"] == "STAGE_A_UNRESOLVED"
    assert run(tmp_path / "c", drag_plus=1e-3)[0]["verdict"] == "STAGE_A_CONSTRAINT_FAIL"
    assert run(tmp_path / "d", gates_fail=True)[0]["verdict"] == "STAGE_A_CONSTRAINT_FAIL"
    assert run(tmp_path / "e", repeat_shift=5e-5)[0]["verdict"] == "STAGE_A_UNRESOLVED"
    assert run(tmp_path / "f", minus=1.5e-4)[0]["verdict"] == "STAGE_A_CONSTRAINT_FAIL"                      # the reverse control also gains: no pass
    r = run(tmp_path / "g", repeat_shift=1e-6)[0]
    assert r["stage_a"]["resolution_source"] == "nominal_floor" and "differed" in r["interpretation"]


def test_the_plus_2p5_state_never_changes_the_verdict(tmp_path):
    assert run(tmp_path / "a", plus25=-5e-3)[0]["verdict"] == run(tmp_path / "b", plus25=5e-3)[0]["verdict"] == "STAGE_A_PASS"


@pytest.mark.parametrize("kw,needle", [({"break_baseline": True}, "baseline"), ({"drop": "lowdim02a__baseline_repeat"}, "plan"), ({"failed": "lowdim02a__ctrl_reverse__s1.25mm"}, "plan"),
                                      ({"gpu": "Tesla P100"}, "T4"), ({"empty_manifest": True}, "manifest"), ({"wrong_case": True}, "summary finiteness")])
def test_an_integrity_failure_is_incomplete_and_never_a_verdict(tmp_path, kw, needle):
    r, *_ = run(tmp_path, **kw)
    assert r["verdict"] == "STAGE_A_INCOMPLETE" and r["integrity"]["pass"] is False and any(needle in f for f in r["integrity"]["failures"]) and "stage_a" not in r


def test_a_modified_inventory_or_missing_freeze_pins_or_a_changed_file_hash_fail_closed(tmp_path):
    out, freeze, inv = SYN.make_all(tmp_path)
    bad = json.loads(json.dumps(inv)); bad["rules"]["noise_factor"] = 1.0
    assert A.analyze(out, freeze, inventory=bad, formal=SYN.FORMAL)["verdict"] == "STAGE_A_INCOMPLETE"
    assert A.analyze(out, {**freeze, "pins": {}}, inventory=inv, formal=SYN.FORMAL)["verdict"] == "STAGE_A_INCOMPLETE"
    fh = dict(freeze["file_hashes"]); fh["job"] = "0" * 64
    assert A.analyze(out, {**freeze, "file_hashes": fh}, inventory=inv, formal=SYN.FORMAL)["verdict"] == "STAGE_A_INCOMPLETE"


def test_the_flow32_force_scale_is_applied_and_reproduces_the_w4_round2_baseline():
    host = A.recompute_force_n(ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv", A.flow32_criteria(SYN.FORMAL))
    ref = INV["flow32_baseline_reference"]
    assert host["downforce_n"] == ref["w4_result_total_downforce_n"] == ref["host_recomputed_n"]["downforce_n"] and host["drag_n"] == ref["w4_result_total_drag_n"]
    assert host["force_scale_n_per_solver_force"] == pytest.approx(6.25e-4) and A.sha256(ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv") == ref["forces_csv_sha256"]


# ---- the registered inputs ------------------------------------------------------------------------------------------------------------------------------------------
def test_the_inventory_is_a_hash_bound_subset_of_lowdim01_plus_a_baseline_repeat():
    assert INV["lowdim01_inventory_sha256"] == hashlib.sha256((L1 / "inventory.json").read_bytes()).hexdigest()
    names = [r["name"] for r in INV["states"]]
    assert names == INV["kernels"]["a"] == ["lowdim02a__baseline", "lowdim02a__baseline_repeat", "lowdim02a__prop__s1.25mm", "lowdim02a__ctrl_reverse__s1.25mm", "lowdim02a__prop__s2.5mm"]
    assert [r["kind"] for r in INV["states"]] == ["baseline", "baseline_repeat", "candidate", "control", "descriptive"]
    src = {r["name"]: r for r in L1INV["states"]}
    for r in INV["states"]:
        s = src[r["source_lowdim01_state"]]
        for k in ("phi_fortran_order_sha256", "state_sha256", "npz_sha256", "changed_node_count", "geometry_gates"):
            assert r[k] == s[k], (r["name"], k)
    assert INV["states"][0]["phi_fortran_order_sha256"] == INV["states"][1]["phi_fortran_order_sha256"] == INV["baseline"]["phi_fortran_sha256"]


def test_every_registered_phi_is_reproduced_by_the_runner_numpy_function_and_the_accepted_gates_pass():
    phi = S.read_f4(BASELINE_RAW)
    prop = S.read_f4(ROOT / INV["proposal"]["file"])
    assert S.sha256_bytes((ROOT / INV["proposal"]["file"]).read_bytes()) == INV["proposal"]["sha256_fortran_raw"]
    for r in INV["states"]:
        raw = S.to_raw(phi) if r["sign"] == 0 else S.to_raw(S.perturb(phi, prop, r["step_mm"], r["sign"]))
        assert S.sha256_bytes(raw) == r["phi_fortran_order_sha256"], r["name"]
    plus = INV["states"][2]
    assert plus["geometry_gates"]["all_hard_gates_pass"] is True and plus["step_mm"] == 1.25 and plus["sign"] == 1
    assert INV["flow24_reference_lowdim01"]["downforce_change_n"]["+1.25"] > 0 > INV["flow24_reference_lowdim01"]["downforce_change_n"]["-1.25"]


# ---- the runner -----------------------------------------------------------------------------------------------------------------------------------------------------
BASELINE_CSV = b"step,t_u_l,fx_solver\n8,0.09,544.8\n"


def load_runner(tmp_path):
    path = tmp_path / "runner.py"
    path.write_text(B.render("0" * 40))
    spec = importlib.util.spec_from_file_location("lowdim02a_runner", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def patch_environment(mod, monkeypatch, tmp_path, job_behaviour):
    real_tmp = tempfile.TemporaryDirectory
    monkeypatch.setattr(mod.tempfile, "TemporaryDirectory", lambda prefix, dir: real_tmp(prefix=prefix, dir=tmp_path))
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    monkeypatch.setattr(mod.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-abc, 15360 MiB, 535.1\n")
    monkeypatch.setattr(mod, "fetch_source", lambda base: ROOT)
    monkeypatch.setattr(mod, "install_julia", lambda base: Path("julia"))
    monkeypatch.setattr(mod, "FLOW32_BASELINE_CSV_SHA256", hashlib.sha256(BASELINE_CSV).hexdigest())
    calls = []

    def fake_run(args, log_path, env=None, timeout=3600):
        Path(log_path).write_text("fake")
        if "Pkg.instantiate()" in " ".join(map(str, args)):
            return 0
        phi, outdir = Path(args[-2]), Path(args[-1])
        calls.append((phi.name, env["W4_PHI_FORTRAN_SHA256"], hashlib.sha256(phi.read_bytes()).hexdigest(), Path(args[-3]).name))
        return job_behaviour(len(calls), outdir)
    monkeypatch.setattr(mod, "run", fake_run)
    return calls


def good_job(n, outdir, baseline=BASELINE_CSV):
    (outdir / "flow_32.forces.csv").write_bytes(baseline if n == 1 else b"step,t_u_l\n" + str(n).encode() + b"\n")
    (outdir / "flow_32.summary.json").write_text("{}"); (outdir / "W4_JOB_DONE").write_text("x")
    return 0


def test_rendering_fills_every_pin_and_the_kernel_identity_is_new():
    text = B.render("a" * 40)
    meta = B.metadata()
    assert "PIN_" not in text and meta["id"].split("/")[1] == B.slugify(B.TITLE) and meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == [] and B.TIMEOUT_S == 10800
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_lowdim02a_a"}
    assert meta["id"] not in used and "waterlily_lowdim02_flow32_job.jl" in text and "flow_24" not in text.replace("FD-08", "")


def test_a_complete_kernel_writes_done_runs_the_baseline_first_with_the_flow32_job_and_the_registered_phi(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    calls = patch_environment(mod, monkeypatch, tmp_path, good_job)
    mod.main()
    out = tmp_path / "out"
    index = json.loads((out / "lowdim02a_index.json").read_text())
    assert (out / "DONE").is_file() and not (out / "ERROR.txt").exists() and index["status"] == "COMPLETE"
    assert [e["name"] for e in index["states"]] == INV["kernels"]["a"] and index["states"][0]["matches_w4_v17_flow32_baseline"] is True
    assert all(c[1] == c[2] and c[3] == "waterlily_lowdim02_flow32_job.jl" for c in calls) and len(calls) == 5


def test_a_baseline_that_differs_from_the_w4_flow32_baseline_stops_before_any_other_state(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    calls = patch_environment(mod, monkeypatch, tmp_path, lambda n, o: good_job(n, o, baseline=BASELINE_CSV + b"x"))
    with pytest.raises(SystemExit):
        mod.main()
    out = tmp_path / "out"
    assert not (out / "DONE").exists() and "differs from the W4 v17" in (out / "ERROR.txt").read_text() and len(calls) == 1


def test_a_failing_job_a_pin_mismatch_or_a_wrong_gpu_never_writes_done(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, lambda n, o: good_job(n, o) if n < 3 else 2)
    with pytest.raises(SystemExit):
        mod.main()
    assert not (tmp_path / "out" / "DONE").exists()
    d2 = tmp_path / "p"; d2.mkdir()
    mod2 = load_runner(d2); patch_environment(mod2, monkeypatch, d2, good_job)
    pins = dict(mod2.PINS); pins[mod2.PROPOSAL_RAW] = "0" * 64
    monkeypatch.setattr(mod2, "PINS", pins)
    with pytest.raises(SystemExit):
        mod2.main()
    assert "pinned file SHA-256 mismatch" in (d2 / "out" / "ERROR.txt").read_text()
    d3 = tmp_path / "g"; d3.mkdir()
    mod3 = load_runner(d3); patch_environment(mod3, monkeypatch, d3, good_job)
    monkeypatch.setattr(mod3.subprocess, "check_output", lambda *a, **k: "0, Tesla P100, GPU-abc, 16384 MiB, 535.1\n")
    with pytest.raises(SystemExit):
        mod3.main()
    assert "T4 worker was not present" in (d3 / "out" / "ERROR.txt").read_text()


def test_the_generated_phi_of_every_state_matches_the_inventory_and_a_tampered_row_fails(tmp_path):
    mod = load_runner(tmp_path)
    for row in INV["states"]:
        assert hashlib.sha256(mod.generate_phi(S, ROOT, INV, row)).hexdigest() == row["phi_fortran_order_sha256"]
    with pytest.raises(RuntimeError, match="differs from the registered inventory"):
        mod.generate_phi(S, ROOT, INV, {**INV["states"][2], "phi_fortran_order_sha256": "0" * 64})
    with pytest.raises(RuntimeError, match="changed node count"):
        mod.generate_phi(S, ROOT, INV, {**INV["states"][2], "changed_node_count": 1})


def test_the_job_is_the_xfid_job_with_only_the_case_and_messages_changed():
    a = (ROOT / "scripts/waterlily_xfid_candidate_c_job.jl").read_text().splitlines()
    b = (ROOT / "scripts/waterlily_lowdim02_flow32_job.jl").read_text().splitlines()
    assert len(a) == len(b)
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert [i for i in changed if i > 2] == [29, 60, 347, 365]
    assert 'EXPECTED_CASE_IDS = ("flow_32",)' in b[60] and 'c.case_id == "flow_32"' in b[347]


def test_the_sparse_checkout_covers_every_pinned_path():
    sparse = ["julia", "scripts", "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs", "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09",
              "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inputs"]
    text = (ROOT / "scripts/lowdim02a_runner_template.py").read_text()
    assert 'SPARSE = ["julia", "scripts", BASELINE_DIR, EVIDENCE, f"{LOWDIM01_EVIDENCE}/inputs"]' in text
    for rel in B.pins():
        assert any(rel == s or rel.startswith(s + "/") for s in sparse), rel


def test_the_first_registered_state_must_be_the_single_baseline(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, good_job)
    inv = json.loads(json.dumps(INV)); inv["kernels"]["a"] = inv["kernels"]["a"][1:] + inv["kernels"]["a"][:1]
    real = mod.json.loads
    monkeypatch.setattr(mod.json, "loads", lambda t: inv if '"lowdim02a_state_inventory"' in t else real(t))
    with pytest.raises(SystemExit):
        mod.main()
    assert "single baseline" in (tmp_path / "out" / "ERROR.txt").read_text()
