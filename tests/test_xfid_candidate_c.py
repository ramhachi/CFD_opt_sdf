import ast
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import xfid_final_verdict as fv  # noqa: E402

RUNNER = ROOT / "infra/kaggle/kernel_xfid_candidate_c/runner.py"
W4 = ROOT / "infra/kaggle/kernel_w4_v17_candidate_c/runner.py"
spec = importlib.util.spec_from_file_location("xc_runner", RUNNER)
xc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xc)


def func_sources(path):
    src = path.read_text()
    return {n.name: ast.get_source_segment(src, n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}


def test_copied_helpers_are_verbatim_from_the_w4c_runner():
    a, b = func_sources(RUNNER), func_sources(W4)
    copied = ["sha256", "sha256_bytes", "write_json", "command", "install_julia", "zero_level_margin_m", "parse_force_csv",
              "time_weighted_mean", "clipped_force_window", "recompute_case_metrics", "force_components_close", "close_summary"]
    assert all(a[n] == b[n] for n in copied)


def test_job_differs_from_w4c_job_only_in_case_inventory_and_messages():
    old = (ROOT / "scripts/waterlily_w4_v17_candidate_c_job.jl").read_text().splitlines()
    new = (ROOT / "scripts/waterlily_xfid_candidate_c_job.jl").read_text().splitlines()
    import difflib
    changed = [l for l in difflib.unified_diff(old, new, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    code = [l for l in changed if not l[1:].lstrip().startswith("#")]
    assert 8 <= len(changed) <= 20 and not any("sim_step" in l or "CandidateCWaterLilyBody" in l or "Simulation" in l for l in code)


def synthetic_csv(path, drag, downforce):
    cols = xc.FORCE_COLUMNS
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        step = 0
        for t in np.arange(8, 120.0 + 1e-9, 1.0):
            step += 8
            row = {c: 0.0 for c in cols}
            row.update(step=step, t_u_l=float(t), drag_solver=drag, downforce_solver=downforce, fx_solver=drag, fz_solver=-downforce)
            w.writerow([row[c] for c in cols])


def test_verdict_pipeline_on_synthetic_waterlily_output(tmp_path):
    scale = fv.FORCE_SCALE_N
    S = {"D0_interface_offset": (-6e-4, 3.7e-3), "D1_filtered_seed11": (-3e-4, -5e-4), "D2_filtered_seed2026": (-8e-4, -5e-4)}
    states, openfoam = {}, {"contrasts": {}}
    for name in ["baseline", "baseline_repeat"]:
        (tmp_path / "states" / name).mkdir(parents=True)
        synthetic_csv(tmp_path / "states" / name / "flow_24.forces.csv", 0.3 / scale, 0.3 / scale)
        states[name] = {"status": "COMPLETED", "forces_n": {"drag_time_weighted_n": 0.3}}
    for d, (sd, sf) in S.items():
        for sign, tag in ((1, "plus"), (-1, "minus")):
            name = f"{d}_{tag}"
            (tmp_path / "states" / name).mkdir(parents=True)
            synthetic_csv(tmp_path / "states" / name / "flow_24.forces.csv", (0.3 + sign * sd) / scale, (0.3 + sign * sf) / scale)
            states[name] = {"status": "COMPLETED", "forces_n": {"drag_time_weighted_n": 0.3 + sign * sd}}
        for r, v in (("drag_n", sd), ("downforce_n", sf)):
            openfoam["contrasts"][f"{d}:{r}"] = {"S_n": v, "resolved": True, "sign": int(np.sign(v))}
    wl = fv.waterlily_contrasts(tmp_path, {"states": states})
    assert abs(wl["D0_interface_offset:downforce_n"]["S_n"] - 3.7e-3) < 1e-9 and wl["D0_interface_offset:downforce_n"]["floor_n"] == 1e-8
    assert fv.verdict(openfoam, wl) == "AGREE"
    openfoam["contrasts"]["D1_filtered_seed11:downforce_n"]["sign"] = 1  # OpenFOAM disagrees on one resolved contrast
    assert fv.verdict(openfoam, wl) == "DISAGREE"


def test_runner_refuses_unbound_criteria(tmp_path):
    (tmp_path / "xfidc_criteria.json").write_text("{}")
    try:
        xc.read_criteria(tmp_path)
    except RuntimeError as e:
        assert "not been bound" in str(e)
    else:
        raise AssertionError("expected refusal")


def _w4_criteria():
    return json.loads((ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json").read_text())


def test_verify_state_accepts_the_real_baseline_and_rejects_a_corrupted_raw(tmp_path):
    import prepare_kaggle_xfid_candidate_c as prep

    w4 = _w4_criteria()
    entry = prep.state_entry("baseline", ROOT / "docs/evidence/xfid01_geometry_preflight_2026_10_03/canonical_state.npz", tmp_path)
    criteria = {"geometry": {k: w4["geometry"][k] for k in ("point_shape", "cell_shape", "design_lattice_spacing_m", "canonical_sdf_origin_m",
                                                            "source_surface_sha256", "phi_margin_gate_m", "phi_margin_tolerance_m")}}
    raw, margin = xc.verify_state("baseline", entry, criteria, tmp_path)
    assert abs(margin - 0.3499999939931499) < 1e-9 and entry["state_sha256"] == w4["geometry"]["canonical_state_sha256"]
    assert entry["phi_fortran_sha256"] == w4["geometry"]["canonical_phi_fortran_sha256"]
    blob = bytearray(raw.read_bytes())
    blob[100] ^= 1
    raw.write_bytes(bytes(blob))
    try:
        xc.verify_state("baseline", entry, criteria, tmp_path)
    except RuntimeError as e:
        assert "mismatch" in str(e) or "differs" in str(e)
    else:
        raise AssertionError("corrupted raw phi must be rejected")


def test_evaluate_state_end_to_end_on_a_synthetic_job_output(tmp_path):
    w4 = _w4_criteria()
    case = next(c for c in w4["cases"] if c["case_id"] == "flow_24")
    criteria = {"measurement": w4["measurement"], "case": case, "backend": w4["backend"]}
    outdir = tmp_path / "s"
    outdir.mkdir()
    cols = xc.FORCE_COLUMNS
    with (outdir / "flow_24.forces.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        step = 0
        for t in np.arange(8, 128.0, 1.0):
            step += 8
            drag, down = 10.0 + 0.001 * t, 5.0
            row = dict(step=step, t_u_l=float(t), fx_solver=drag, fy_solver=0.0, fz_solver=-down, drag_solver=drag, downforce_solver=down,
                       pressure_fx_solver=drag, pressure_fy_solver=0.0, pressure_fz_solver=-down, viscous_fx_solver=0.0, viscous_fy_solver=0.0, viscous_fz_solver=0.0)
            w.writerow([row[c] for c in cols])
    rows = xc.parse_force_csv(outdir / "flow_24.forces.csv")
    metrics = xc.recompute_case_metrics(rows, case, w4["measurement"])
    st = {"state_sha256": "a", "phi_fortran_sha256": "b"}
    summary = dict(metrics, force_csv_sha256=xc.sha256(outdir / "flow_24.forces.csv"), finite_u=True, finite_p=True, finite_forces=True,
                   t_end_reached=127.0, state_sha256="a", phi_fortran_sha256="b", device_roundtrip_sha256="b",
                   force_integration_body=w4["measurement"]["force_integration_body"], waterlily_version=w4["backend"]["waterlily_version"],
                   cuda_jl_version=w4["backend"]["cuda_jl_version"], julia_version=w4["backend"]["julia_version"], gpu_name="Tesla T4",
                   peak_vram_bytes=5, vram_total_bytes=10, wall_seconds=1.0, steps=step)
    (outdir / "flow_24.summary.json").write_text(json.dumps(summary))
    log = "W4_SOLVER_STEP_INVOKED flow_24\nW4_SOLVER_STEP_RETURNED flow_24\n"
    res = xc.evaluate_state("s", st, criteria, outdir, log, 0.35)
    assert res["status"] == "COMPLETED" and all(res["gates"].values()), res["gates"]
    assert abs(res["forces_n"]["drag_time_weighted_n"] - metrics["drag_time_weighted_n"]) < 1e-12
    summary["state_sha256"] = "tampered"
    (outdir / "flow_24.summary.json").write_text(json.dumps(summary))
    assert xc.evaluate_state("s", st, criteria, outdir, log, 0.35)["status"] == "GATE_FAILED"
