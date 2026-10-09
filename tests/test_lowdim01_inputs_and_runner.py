"""LOWDIM-01 inputs (proposal direction, candidate states, registered geometry gates) and the Kaggle runner (fail-closed with a fake job)."""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import build_lowdim01_kernel as B  # noqa: E402
import lowdim01_states as L  # noqa: E402
import step01_states as S  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
INV = json.loads((E / "inventory.json").read_text())
STEP01 = json.loads((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json").read_text())
IN = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
BASE = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"


def test_the_coefficient_gradient_is_the_bound_step01_centered_difference_and_the_proposal_follows_from_it():
    g = {}
    for d in L.BASIS:
        row = STEP01["series"][f"{d}|downforce"]["rows"][0]
        assert row["step_mm"] == 2.5 and INV["coefficient_gradient"]["values"][d]["g_sec_n_per_m"] == row["g_sec_n_per_m"] == (row["r_plus_n"] - row["r_minus_n"]) / (2 * 0.0025)
        g[d] = row["g_sec_n_per_m"]
    assert INV["coefficient_gradient"]["step01_analysis_sha256"] == hashlib.sha256((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json").read_bytes()).hexdigest()
    dirs = {n: S.read_f4(IN / e["file"]) for n, e in INV["directions"].items()}
    d, info = L.coefficient_direction(g, dirs)
    assert S.sha256_bytes(S.to_raw(d)) == INV["proposal"]["sha256_fortran_raw"] == S.sha256_bytes((ROOT / INV["proposal"]["file"]).read_bytes())
    assert float(np.max(np.abs(d))) == 1.0 and info["coefficient_unit_vector"] == INV["proposal"]["coefficient_unit_vector"]
    assert pytest.approx(1.0) == float(np.linalg.norm(list(info["coefficient_unit_vector"].values())))
    assert INV["proposal"]["metric"].startswith("Euclidean")


def test_the_proposal_direction_for_a_unit_gradient_is_that_basis_direction():
    dirs = {n: S.read_f4(IN / e["file"]) for n, e in INV["directions"].items()}
    d, info = L.coefficient_direction({"D0_interface_offset": 1.0, "D1_filtered_seed11": 0.0, "D2_filtered_seed2026": 0.0, "P1_upstream_lobe": 0.0}, dirs)
    assert np.array_equal(d, dirs["D0_interface_offset"].astype("<f4")) and info["m_max_abs_sum"] == 1.0
    with pytest.raises(ValueError):
        L.coefficient_direction({n: 0.0 for n in L.BASIS}, dirs)


def test_every_registered_state_is_reproduced_by_the_runner_numpy_function():
    phi = S.read_f4(BASE)
    assert S.sha256_bytes(S.to_raw(phi)) == INV["baseline"]["phi_fortran_sha256"]
    prop = S.read_f4(ROOT / INV["proposal"]["file"])
    assert [r["name"] for r in INV["states"]] == [p["name"] for p in L.plan()] == INV["kernels"]["a"] and INV["candidate_step_mm"] == [1.25, 2.5, 5.0, 7.5] and INV["control_step_mm"] == [1.25, 2.5]
    assert [r["kind"] for r in INV["states"]] == ["baseline"] + ["candidate"] * 4 + ["control"] * 2 and [r["sign"] for r in INV["states"]] == [0, 1, 1, 1, 1, -1, -1]
    for row in INV["states"]:
        if row["kind"] == "baseline":
            assert row["phi_fortran_order_sha256"] == INV["baseline"]["phi_fortran_sha256"]
            continue
        raw = S.to_raw(S.perturb(phi, prop, row["step_mm"], row["sign"]))
        assert S.sha256_bytes(raw) == row["phi_fortran_order_sha256"] and row["maximum_pointwise_change_m"] == pytest.approx(row["step_mm"] / 1000.0, rel=1e-6)
        assert int(np.count_nonzero(np.frombuffer(raw, "<f4") != np.frombuffer(S.to_raw(phi), "<f4"))) == row["changed_node_count"] > 0


def test_registered_geometry_thresholds_and_the_candidate_gate_results():
    t = INV["geometry_gate_thresholds"]
    assert t["smoothed_volume_band"] == 0.10 and t["eikonal_median_abs_deviation_max"] == 0.10 and t["cell_components"] == 1 and t["clearance_m"] == 0.15 and "none" in t["reinitialization"]
    by = {r["step_mm"]: r["geometry_gates"] for r in INV["states"] if r["kind"] == "candidate"}
    assert [by[s]["all_hard_gates_pass"] for s in (1.25, 2.5, 5.0, 7.5)] == [True, True, True, False]
    assert not by[7.5]["gates"]["smoothed_volume_band"] and not by[7.5]["gates"]["eikonal_median_within_limit"]
    for s, g in by.items():
        assert g["relative_smoothed_volume_change"] < 0 and abs(g["relative_smoothed_volume_change"]) <= 0.12 and g["gates"]["clearance"] and g["gates"]["masks_and_support_preserved"]
    exp = json.loads((E / "geometry_exploration_step01_states.json").read_text())
    assert exp["evidence_class"] == "solver_free_exploratory_unregistered" and len(exp["states"]) == 45


# ---- the runner -------------------------------------------------------------------------------------------------------------------------------------------------------------
BASELINE_CSV = b"step,t_u_l,fx_solver\n8,0.09,544.8\n"


def load_runner(tmp_path):
    path = tmp_path / "runner.py"
    path.write_text(B.render("0" * 40))
    spec = importlib.util.spec_from_file_location("lowdim_runner", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def patch_environment(mod, monkeypatch, tmp_path, job_behaviour):
    real_tmp = tempfile.TemporaryDirectory
    monkeypatch.setattr(mod.tempfile, "TemporaryDirectory", lambda prefix, dir: real_tmp(prefix=prefix, dir=tmp_path))
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    monkeypatch.setattr(mod.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-abc, 15360 MiB, 535.1\n")
    monkeypatch.setattr(mod, "fetch_source", lambda base: ROOT)
    monkeypatch.setattr(mod, "install_julia", lambda base: Path("julia"))
    monkeypatch.setattr(mod, "FD08_BASELINE_CSV_SHA256", hashlib.sha256(BASELINE_CSV).hexdigest())
    calls = []

    def fake_run(args, log_path, env=None, timeout=3600):
        Path(log_path).write_text("fake")
        if "Pkg.instantiate()" in " ".join(map(str, args)):
            return 0
        phi, outdir = Path(args[-2]), Path(args[-1])
        calls.append((phi.name, env["W4_PHI_FORTRAN_SHA256"], hashlib.sha256(phi.read_bytes()).hexdigest()))
        return job_behaviour(len(calls), outdir)
    monkeypatch.setattr(mod, "run", fake_run)
    return calls


def good_job(n, outdir, baseline=BASELINE_CSV):
    (outdir / "flow_24.forces.csv").write_bytes(baseline if n == 1 else b"step,t_u_l\n" + str(n).encode() + b"\n")
    (outdir / "flow_24.summary.json").write_text("{}"); (outdir / "W4_JOB_DONE").write_text("x")
    return 0


def test_rendering_fills_every_pin_and_the_kernel_identity_is_new(tmp_path):
    text = B.render("a" * 40)
    assert "PIN_" not in text and B.metadata()["id"] == "ramhachi888/cfd-opt-sdf-lowdim01-a" and B.metadata()["id"].split("/")[1] == B.slugify(B.TITLE)
    meta = B.metadata()
    assert meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == [] and B.TIMEOUT_S == 3600
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != "kernel_lowdim01_a"}
    assert meta["id"] not in used


def test_a_complete_kernel_writes_done_and_runs_the_baseline_first_with_the_registered_phi(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    calls = patch_environment(mod, monkeypatch, tmp_path, good_job)
    mod.main()
    out = tmp_path / "out"
    index = json.loads((out / "lowdim01_index.json").read_text())
    assert (out / "DONE").is_file() and not (out / "ERROR.txt").exists() and index["status"] == "COMPLETE"
    assert [e["name"] for e in index["states"]] == [p["name"] for p in L.plan()] and index["states"][0]["matches_fd08_baseline_v17"] is True and all(c[1] == c[2] for c in calls)


def test_a_baseline_that_differs_from_fd08_stops_before_any_candidate(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    calls = patch_environment(mod, monkeypatch, tmp_path, lambda n, o: good_job(n, o, baseline=BASELINE_CSV + b"x"))
    with pytest.raises(SystemExit):
        mod.main()
    out = tmp_path / "out"
    assert not (out / "DONE").exists() and "differs from FD-08" in (out / "ERROR.txt").read_text() and len(calls) == 1


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


def test_the_generated_phi_of_every_registered_state_matches_the_inventory(tmp_path):
    mod = load_runner(tmp_path)
    for row in INV["states"]:
        assert hashlib.sha256(mod.generate_phi(S, ROOT, INV, row)).hexdigest() == row["phi_fortran_order_sha256"]
    row = {**INV["states"][1], "phi_fortran_order_sha256": "0" * 64}
    with pytest.raises(RuntimeError, match="differs from the registered inventory"):
        mod.generate_phi(S, ROOT, INV, row)


def test_the_job_environment_of_the_baseline_equals_the_fd08_runner_state_env(tmp_path):
    spec = importlib.util.spec_from_file_location("fd08_r6_runner", ROOT / "infra/kaggle/kernel_fd08_v2_r6/runner.py")
    fd08 = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(fd08)
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"the FD-08 runner cannot be imported here: {err}")
    formal = json.loads((ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json").read_text())
    b = next(r for r in formal["state_inventory"] if r["name"] == "baseline_v17")
    theirs = fd08.state_env({}, {"state_sha256": b["state_sha256"], "npz_sha256": b["npz_sha256"], "phi_c_order_sha256": b["phi_c_order_sha256"],
                                 "phi_fortran_order_sha256": b["phi_fortran_order_sha256"], "margin_m": b["margin_m"]}, formal, "GPU-x")
    mod = load_runner(tmp_path)
    assert mod.state_env({}, INV, INV["states"][0], "GPU-x") == theirs


# ---- cases added after the independent review ---------------------------------------------------------------------------------------------------------------------
import build_lowdim01_inputs as BI  # noqa: E402


def test_a_negative_gradient_component_gives_a_negative_coefficient_and_the_coefficients_rebuild_the_direction():
    dirs = {n: S.read_f4(IN / e["file"]) for n, e in INV["directions"].items()}
    d, info = L.coefficient_direction({"D0_interface_offset": -1.0, "D1_filtered_seed11": 0.0, "D2_filtered_seed2026": 0.0, "P1_upstream_lobe": 0.0}, dirs)
    assert np.array_equal(d, (-dirs["D0_interface_offset"]).astype("<f4")) and info["per_unit_step_basis_coefficients"]["D0_interface_offset"] == -1.0
    prop = S.read_f4(ROOT / INV["proposal"]["file"]).astype(np.float64)
    rebuilt = sum(INV["proposal"]["per_unit_step_basis_coefficients"][n] * dirs[n].astype(np.float64) for n in L.BASIS)
    assert np.allclose(rebuilt, prop, atol=1e-6)                                  # sum_i (c_i/m) d_i == d_prop
    assert all(INV["proposal"]["per_unit_step_basis_coefficients"][n] * INV["coefficient_gradient"]["values"][n]["g_sec_n_per_m"] > 0 for n in L.BASIS)       # every term raises downforce to first order


def test_the_linear_prediction_is_g_dot_coefficients_times_the_step_in_metres():
    for name, v in INV["linear_prediction_reference_only"].items():
        s = next(r["step_mm"] * r["sign"] for r in INV["states"] if r["name"] == name)
        want = sum(INV["coefficient_gradient"]["values"][n]["g_sec_n_per_m"] * INV["proposal"]["per_unit_step_basis_coefficients"][n] * s / 1000.0 for n in L.BASIS)
        assert v["linear_predicted_downforce_change_n"] == pytest.approx(want, rel=1e-12)
    assert INV["linear_prediction_reference_only"]["lowdim01__prop__s1.25mm"]["linear_predicted_downforce_change_n"] == pytest.approx(7.85e-4, rel=2e-3)


def test_the_gate_function_fails_at_the_registered_boundaries():
    base = {"smoothed_volume_m3": 1.0, "sharp_volume_m3": 1.0, "cell_components": 1}
    ok = {"smoothed_volume_m3": 0.90, "sharp_volume_m3": 1.0, "cell_components": 1, "eikonal_median_abs_deviation": 0.10}
    audit = {"zero_level_margin_m": 0.15, "masks_equal": True, "support_outside_active_exactly_unchanged": True}
    assert BI.gates(base, ok, audit)["all_hard_gates_pass"] is True                                                    # exactly at the limits is inside
    assert BI.gates(base, {**ok, "smoothed_volume_m3": 0.8999}, audit)["gates"]["smoothed_volume_band"] is False
    assert BI.gates(base, {**ok, "smoothed_volume_m3": 1.1001}, audit)["gates"]["smoothed_volume_band"] is False        # the band is two-sided
    assert BI.gates(base, {**ok, "eikonal_median_abs_deviation": 0.1001}, audit)["gates"]["eikonal_median_within_limit"] is False
    assert BI.gates(base, {**ok, "cell_components": 2}, audit)["gates"]["cell_components_equal_baseline"] is False
    assert BI.gates(base, ok, {**audit, "zero_level_margin_m": 0.1499})["gates"]["clearance"] is False
    assert BI.gates(base, ok, {**audit, "masks_equal": False})["gates"]["masks_and_support_preserved"] is False


def test_all_registered_states_have_distinct_phi_and_the_exploration_baseline_matches_the_inventory():
    cands = [r["phi_fortran_order_sha256"] for r in INV["states"] if r["kind"] == "candidate"]
    assert len(set(cands)) == 4 and INV["states"][0]["phi_fortran_order_sha256"] not in cands
    assert len({r["phi_fortran_order_sha256"] for r in INV["states"][1:]}) == 6
    exp = json.loads((E / "geometry_exploration_step01_states.json").read_text())
    g = INV["states"][0]["geometry"]
    for key in ("sharp_volume_m3", "smoothed_volume_m3", "cell_components", "node_components"):
        assert exp["baseline"][key] == g[key]
    assert exp["baseline"]["eikonal"]["median_abs_gradient_deviation"] == g["eikonal_median_abs_deviation"]


def test_the_sparse_checkout_covers_every_path_the_runner_and_the_job_read():
    mod_text = (ROOT / "scripts/lowdim01_runner_template.py").read_text()
    sparse = ["julia", "scripts", "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs", "docs/evidence/lowdim01_four_direction_capability_2026_10_09"]
    assert 'SPARSE = ["julia", "scripts", BASELINE_DIR, EVIDENCE]' in mod_text
    for rel in B.pins():
        assert any(rel == s or rel.startswith(s + "/") for s in sparse), rel
