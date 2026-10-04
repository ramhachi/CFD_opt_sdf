import gzip
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_xfid_gridphase_x3_calibration as an  # noqa: E402
import prepare_kaggle_xfid_gridphase_x3 as prep  # noqa: E402

R5 = ROOT / "docs/evidence/xfid_v16_environment_reproduction_2026_10_02_round5/terminal_kernel_v4_parent_verified"
spec = importlib.util.spec_from_file_location("x3_runner", ROOT / "infra/kaggle/kernel_openfoam_xfid_gridphase_x3/runner.py")
x3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x3)


def test_shift_set_is_mirrored_nonzero_in_range_and_deterministic():
    cases = prep.phase_cases("baseline", "cal", 16)
    assert len(cases) == 32 and cases == prep.phase_cases("baseline", "cal", 16)
    for p, m in zip(cases[0::2], cases[1::2]):
        assert np.allclose(np.array(p["shift_m"]), -np.array(m["shift_m"]), atol=0, rtol=0) and p["id"][:-1] == m["id"][:-1]
        assert all(0.5e-3 <= abs(x) <= 4.0e-3 for x in p["shift_m"])


def test_translation_uses_all_three_components():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=float)
    shifted = np.frombuffer(x3.translated_stl(tri, [0.001, -0.002, 0.003])[84:], dtype=x3.STL_DTYPE)["t"].astype(float)
    assert np.allclose(shifted - tri, [0.001, -0.002, 0.003], atol=1e-7)


def test_analysis_on_planted_linear_plus_iid_noise_accepts_averaging():
    rng = np.random.default_rng(3)
    cases = []
    for c in prep.phase_cases("baseline", "cal", 16):
        v = np.array(c["shift_m"]) * 1000
        f = lambda scale: 0.3 + scale * (2e-5 * v[0] - 1e-5 * v[2]) + rng.normal(0, scale * 3e-4)
        cases.append({"id": c["id"], "status": "COMPLETED", "shift_m": c["shift_m"],
                      "forces": {"drag_n": {"window_mean": f(0.3)}, "downforce_n": {"window_mean": f(1.0)}}})
    res = an.analyze({"cases": cases})["responses"]["downforce_n"]
    assert res["averaging_model_accepted"] and 1e-4 < res["sigma_e_n"] < 6e-4
    assert abs(res["linear_translation_n_per_mm"]["x"] - 2e-5) < 5e-5


def test_runner_end_to_end_with_fake_openfoam_and_state_selection(tmp_path):
    bin_dir, real = tmp_path / "fakebin", tmp_path / "real"
    bin_dir.mkdir(); real.mkdir()
    for name in ("log.checkMesh", "log.simpleFoam", "coefficient.dat"):
        (real / name).write_text(gzip.open(R5 / (name + ".gz"), "rt").read())
    scripts = {"blockMesh": "echo b", "surfaceFeatureExtract": "echo s",
               "snappyHexMesh": "printf 'Cells per refinement level:\\n    0\\t10\\n\\n'",
               "checkMesh": f"cat {real}/log.checkMesh; exit 1",
               "simpleFoam": f"cat {real}/log.simpleFoam; mkdir -p postProcessing/forceCoeffs/0; cp {real}/coefficient.dat postProcessing/forceCoeffs/0/"}
    for name, body in scripts.items():
        f = bin_dir / name
        f.write_text("#!/usr/bin/env bash\n" + body + "\n")
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "bashrc").write_text(f'export PATH="{bin_dir}:$PATH"\n')
    data = tmp_path / "data" / "ds"
    (data / "case_template/constant/triSurface").mkdir(parents=True)
    (data / "states").mkdir()
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=float)
    (data / "states/baseline.stl").write_bytes(x3.stl_bytes(tri))
    (data / "openfoam_package_lock_jammy.json").write_text("{}")
    inputs = {p.relative_to(data).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data.rglob("*")) if p.is_file()}
    cases = [{"id": "c1", "state": "baseline", "shift_m": [0.001, -0.002, 0.003]}]
    criteria = {"immutable": True, "registered_before_run": True, "round_id": "t",
                "environment": {"foam_version": "x", "registered_lock_suites": ["jammy"]},
                "states": {"baseline": {"file": "states/baseline.stl", "triangles": 1}}, "inputs": inputs,
                "case_order": cases, "launch_deadline_hours": 1.0, "stage_timeout_s": 60, "stop_after_consecutive_failures": 3,
                "force_window": {"minimum_rows": 20, "tail_fraction": 0.25, "force_n_per_coefficient": 0.32},
                "qualification_flags": {"optimizer": False}}
    text = json.dumps(criteria)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (data / "x3_criteria.json").write_text(text)
    (data / "x3_criteria.json.sha256").write_text(digest + "\n")
    x3.OUTPUT, x3.INPUT_ROOT, x3.OPENFOAM_BASHRC, x3.CRITERIA_SHA256 = tmp_path / "out", tmp_path / "data", str(tmp_path / "bashrc"), digest
    os.environ["X3_SKIP_INSTALL"] = "1"
    try:
        x3.main()
    finally:
        del os.environ["X3_SKIP_INSTALL"]
    result = json.loads((tmp_path / "out/result.json").read_text())
    c = result["cases"][0]
    assert c["status"] == "COMPLETED" and c["state"] == "baseline" and c["shift_m"] == [0.001, -0.002, 0.003]
    assert abs(c["forces"]["drag_n"]["window_mean"] - 0.37426349429041095) < 1e-9


def test_formal_analysis_recovers_planted_contrasts_and_verdict_rules():
    import analyze_xfid_formal_openfoam as fo

    rng = np.random.default_rng(5)
    cases = []
    planted = {"D0_interface_offset": (-6e-4, 3.7e-3), "D1_filtered_seed11": (-3e-4, -5e-4), "D2_filtered_seed2026": (-8e-4, -5e-4)}
    for c0 in prep.formal_cases():
        state = c0["state"]
        v = np.array(c0["shift_m"]) * 1000
        d = next((k for k in planted if state.startswith(k)), None)
        sgn = {"plus": 1, "minus": -1}.get(state.rsplit("_", 1)[-1], 0)
        def val(i, scale):
            base = 0.3 + scale * 2e-5 * v[0] + rng.normal(0, 1e-4 * scale)
            return base + (sgn * planted[d][i] if d else 0.0)
        cases.append({"id": c0["id"], "status": "COMPLETED", "shift_m": c0["shift_m"],
                      "forces": {"drag_n": {"window_mean": val(0, 1.0)}, "downforce_n": {"window_mean": val(1, 5.0)}}})
    res = fo.analyze({"cases": cases})
    c = res["contrasts"]["D0_interface_offset:downforce_n"]
    assert abs(c["S_n"] - 3.7e-3) < 5 * c["SE_n"] and c["resolved"] and c["sign"] == 1 and c["matched_phases"] == 32
    wl_ok = {k: {"S_n": v["S_n"] * 1.1, "floor_n": 1e-9} for k, v in res["contrasts"].items()}
    resolved = all(v["resolved"] for v in res["contrasts"].values())
    assert fo.verdict(res, wl_ok) == ("AGREE" if resolved else "UNRESOLVED")
    wl_bad = dict(wl_ok); wl_bad["D0_interface_offset:downforce_n"] = {"S_n": -3.7e-3, "floor_n": 1e-9}
    assert fo.verdict(res, wl_bad) == "DISAGREE"
    wl_float = dict(wl_ok); wl_float["D0_interface_offset:downforce_n"] = {"S_n": 3.7e-3, "floor_n": 1.0}
    assert fo.verdict(res, wl_float) == "UNRESOLVED"
