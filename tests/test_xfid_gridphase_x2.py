import gzip
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "infra/kaggle/kernel_openfoam_xfid_gridphase_x2/runner.py"
R5 = ROOT / "docs/evidence/xfid_v16_environment_reproduction_2026_10_02_round5/terminal_kernel_v4_parent_verified"
spec = importlib.util.spec_from_file_location("x2_runner", RUNNER)
x2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x2)


def gz(name):
    return gzip.open(R5 / name, "rt").read()


def test_parsers_reproduce_round5_retained_logs():
    mesh = x2.parse_check_mesh(gz("log.checkMesh.gz"))
    assert mesh["cells"] == 42619 and mesh["concave_cells"] == 2969
    assert mesh["only_allowed_concave_failure"]
    sol = x2.parse_solver(gz("log.simpleFoam.gz"))
    assert sol["iterations"] == 584 and sol["final_residuals"]["p"] is not None
    f = x2.force_window(gz("coefficient.dat.gz"), {"minimum_rows": 20, "tail_fraction": 0.25, "force_n_per_coefficient": 0.32})
    # Round 5 host-verified result: drag 0.37426349429041095 N, downforce 0.24225913050301373 N
    assert abs(f["drag_n"]["window_mean"] - 0.37426349429041095) < 1e-9
    assert abs(f["downforce_n"]["window_mean"] - 0.24225913050301373) < 1e-9


def test_translation_is_deterministic_and_shifts_only_the_chosen_axis():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0, 1], [0, 1, 1], [1, 0, 1]]], dtype=float)
    p = ROOT / "x2_test.stl"
    try:
        p.write_bytes(x2.stl_bytes(tri))
        back = x2.read_stl(p)
    finally:
        p.unlink()
    assert np.array_equal(back, tri)
    a, b = x2.translated_stl(tri, "z", 0.001), x2.translated_stl(tri, "z", 0.001)
    assert a == b and a != x2.stl_bytes(tri)
    shifted = np.frombuffer(a[84:], dtype=x2.STL_DTYPE)["t"].astype(float)
    assert np.allclose(shifted - tri, [0, 0, 0.001], atol=1e-7)


def test_snappy_refinement_block_parser():
    text = "x\nCells per refinement level:\n    0\t1000\n    1\t200\n    2\t30\n\nnext"
    assert x2.parse_snappy(text)["cells_per_refinement_level"] == {0: 1000, 1: 200, 2: 30}


def test_analysis_recovers_a_planted_quadratic_with_no_residual():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import analyze_xfid_gridphase_x2 as an

    def case(cid, axis, mm):
        f = lambda s: 0.3 + 0.002 * s + 0.0001 * s * s
        return {"id": cid, "axis": axis, "shift_m": mm / 1000, "status": "COMPLETED", "mesh": {"cells": 100},
                "forces": {"drag_n": {"window_mean": f(mm)}, "downforce_n": {"window_mean": 2 * f(mm)}}, "stages": []}
    cases = [case("baseline", "x", 0), case("baseline_repeat", "x", 0)]
    for mm in (1, 2, 4, 8):
        cases += [case(f"z_p{mm}", "z", mm), case(f"z_m{mm}", "z", -mm)]
    res = an.analyze({"cases": cases})
    z = res["axes"]["z"]["drag_n"]
    assert abs(z["slope_n_per_mm"] - 0.002) < 1e-9 and z["residual_max_n"] < 1e-9
    assert res["baseline_repeat_difference_n"]["drag_n"] == 0


def _run_fake(tmp_path, snappy=None, deadline_hours=1.0):
    """Whole control flow (copy template, STL write, five stages, parse, retain, deadline) with stub binaries."""
    import hashlib
    import json
    import os
    import stat

    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    for name in ("log.checkMesh", "log.simpleFoam", "coefficient.dat"):
        (real / name).write_text(gz(name + ".gz"))
    scripts = {
        "blockMesh": "echo blockMesh",
        "surfaceFeatureExtract": "echo sfe",
        "snappyHexMesh": snappy or "printf 'Cells per refinement level:\\n    0\\t1000\\n    1\\t200\\n\\n'",
        "checkMesh": f"cat {real}/log.checkMesh; exit 1",
        "simpleFoam": f"cat {real}/log.simpleFoam; mkdir -p postProcessing/forceCoeffs/0; cp {real}/coefficient.dat postProcessing/forceCoeffs/0/",
    }
    for name, body in scripts.items():
        f = bin_dir / name
        f.write_text("#!/usr/bin/env bash\n" + body + "\n")
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    bashrc = tmp_path / "bashrc"
    bashrc.write_text(f'export PATH="{bin_dir}:$PATH"\n')

    data = tmp_path / "data" / "ds"
    (data / "case_template/constant/triSurface").mkdir(parents=True)
    (data / "case_template/system").mkdir()
    (data / "case_template/system/controlDict").write_text("x")
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=float)
    (data / "baseline_stage_v.stl").write_bytes(x2.stl_bytes(tri))
    (data / "openfoam_package_lock.json").write_text("{}")
    inputs = {p.relative_to(data).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data.rglob("*")) if p.is_file()}
    cases = [{"id": "baseline", "axis": "x", "shift_m": 0.0}, {"id": "z_p1mm", "axis": "z", "shift_m": 0.001}]
    criteria = {"immutable": True, "registered_before_run": True, "round_id": "t", "environment": {"foam_version": "x"},
                "baseline": {"triangles": 1}, "inputs": inputs, "case_order": cases, "launch_deadline_hours": deadline_hours,
                "force_window": {"minimum_rows": 20, "tail_fraction": 0.25, "force_n_per_coefficient": 0.32},
                "qualification_flags": {"optimizer": False}}
    text = json.dumps(criteria)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (data / "x2_criteria.json").write_text(text)
    (data / "x2_criteria.json.sha256").write_text(digest + "\n")

    out = tmp_path / "out"
    x2.OUTPUT, x2.INPUT_ROOT, x2.OPENFOAM_BASHRC, x2.CRITERIA_SHA256 = out, tmp_path / "data", str(bashrc), digest
    os.environ["X2_SKIP_INSTALL"] = "1"
    try:
        x2.main()
    finally:
        del os.environ["X2_SKIP_INSTALL"]
    return out, json.loads((out / "result.json").read_text())


def test_runner_end_to_end_with_fake_openfoam(tmp_path):
    out, result = _run_fake(tmp_path)
    assert [c["status"] for c in result["cases"]] == ["COMPLETED", "COMPLETED"]
    c = result["cases"][1]
    assert c["mesh"]["cells"] == 42619 and c["snappy"]["cells_per_refinement_level"] == {"0": 1000, "1": 200}
    assert abs(c["forces"]["drag_n"]["window_mean"] - 0.37426349429041095) < 1e-9
    assert (out / "DONE").is_file() and (out / "cases/z_p1mm/retained/log.simpleFoam.gz").is_file()
    assert not (out / "cases/z_p1mm/case").exists()


def test_stage_failure_is_recorded_and_later_cases_still_run(tmp_path):
    out, result = _run_fake(tmp_path, snappy="echo boom; exit 2")
    assert [c["status"] for c in result["cases"]] == ["snappyHexMesh_FAILED", "snappyHexMesh_FAILED"]
    assert result["cases"][0]["stages"][-1]["stage"] == "snappyHexMesh" and "forces" not in result["cases"][0]
    assert (out / "DONE").is_file()


def test_launch_deadline_marks_cases_not_run(tmp_path):
    _, result = _run_fake(tmp_path, deadline_hours=-1.0)
    assert [c["status"] for c in result["cases"]] == ["NOT_RUN_TIME_BUDGET"] * 2
