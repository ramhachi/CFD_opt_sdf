"""Register XFID X2 criteria and stage the private Kaggle input dataset.

Writes docs/evidence/xfid_gridphase_x2_2026_10_04/x2_criteria.json(+.sha256) and
work/kaggle_xfid_gridphase_x2_dataset/. The baseline STL is re-derived with the X1 build
functions from the saved Round 3 r=8 surface and must match the X1 sha256.
Usage: prepare_kaggle_xfid_gridphase_x2.py [--bind-runner]   (bind: write the criteria hash into runner.py)
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_xfid45_stage_v_input_2026_10_04 as x1  # noqa: E402

R5 = ROOT / "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5"
KERNEL = ROOT / "infra/kaggle/kernel_openfoam_xfid_gridphase_x2"
EVID = ROOT / "docs/evidence/xfid_gridphase_x2_2026_10_04"
DATASET = ROOT / "work/kaggle_xfid_gridphase_x2_dataset"
BASELINE_STL_SHA = "1d0f25786aebf771a73e884e3e52f92073ddff82e80ba501104b18e775f7fc2a"
SHIFTS_MM = [1, 2, 0.5, 4, 8]  # execution priority: D1/D2-relevant sub-2-mm shifts first
AXES = ["z", "y", "x"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def case_order():
    cases = [{"id": "baseline", "axis": "x", "shift_m": 0.0}, {"id": "baseline_repeat", "axis": "x", "shift_m": 0.0}]
    for mm in SHIFTS_MM:
        for axis in AXES:
            for sign, tag in ((1, "p"), (-1, "m")):
                cases.append({"id": f"{axis}_{tag}{str(mm).replace('.', 'p')}mm", "axis": axis, "shift_m": sign * mm / 1000})
    return cases


def main(bind_runner):
    z = np.load(x1.R3 / "baseline/surface.npz")
    v, f, removed = x1.remove_small_components(z["vertices"], z["faces"])
    assert not removed
    stl = x1.stl_bytes(v, f)
    assert hashlib.sha256(stl).hexdigest() == BASELINE_STL_SHA, "baseline STL differs from the X1 result"
    if DATASET.exists():
        shutil.rmtree(DATASET)
    (DATASET / "case_template").mkdir(parents=True)
    (DATASET / "baseline_stage_v.stl").write_bytes(stl)
    for src in sorted((R5 / "case_template").rglob("*")):
        rel = src.relative_to(R5 / "case_template")
        if src.is_file() and rel.as_posix() != "constant/triSurface/design_candidate.stl":
            (DATASET / "case_template" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, DATASET / "case_template" / rel)
    shutil.copy2(R5 / "openfoam_package_lock.json", DATASET / "openfoam_package_lock.json")
    r5 = json.loads((R5 / "criteria.json").read_text())
    inputs = {p.relative_to(DATASET).as_posix(): sha(p) for p in sorted(DATASET.rglob("*")) if p.is_file()}
    criteria = {
        "round_id": "xfid45_gridphase_x2_r1",
        "date": "2026-10-04",
        "evidence_class": "openfoam_stage_v_gridphase_probe_diagnostic_uncertified_geometry",
        "authority": "docs/issues/45_next_steps_plan_2026_10_04.md (X2) and the 2026-10-04 phase_plan entry",
        "purpose": "empirical grid-phase sensitivity of OpenFOAM Stage V forces to rigid sub-cell translation of the baseline STL; meshing cost; basis for an OpenFOAM response floor in the later XFID registration",
        "interpretation": "axis responses are NOT assumed null: x changes inlet/outlet/wake distance, z changes ground clearance, y is approximately symmetric but not assumed; each axis is split into a smooth part and a residual and reported separately",
        "environment": r5["environment"],
        "baseline": {"stl_sha256": BASELINE_STL_SHA, "triangles": int(len(f)), "source": "docs/evidence/xfid45_stage_v_input_2026_10_04/result.json (baseline derived STL)"},
        "inputs": inputs,
        "case_template_origin": "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template (hash-identical, minus the v16 candidate STL)",
        "force_window": {"minimum_rows": 20, "tail_fraction": 0.25, "force_n_per_coefficient": r5["fixture"]["force_reference"]["force_n_per_coefficient"],
                         "rule": "same last-25% iteration-tail rule as the Round 5 reproduction; forces in N from forceCoeffs Cd and -Cl"},
        "case_order": case_order(),
        "launch_deadline_hours": 9.0,
        "per_case_failure_policy": "record the failing stage and continue; checkMesh exit 1 with exactly one concave-cell failure and concave fraction <= 0.08 is allowed (as in Round 5); no case is retried",
        "recorded_per_case": ["stl sha256", "per-stage wall time, child CPU time, sampled peak RSS (0.5 s polling)", "checkMesh cells/points/concave/failed checks", "snappyHexMesh cells per refinement level (raw block also kept)", "simpleFoam iterations, convergence, final residuals", "drag and downforce window mean/std/drift and last value in N", "gzipped logs and force history"],
        "analysis": {"script": "scripts/analyze_xfid_gridphase_x2.py",
                     "method": "per axis and response: quadratic least-squares fit of force versus signed shift over all points including both baselines; report slope, residual RMS and max residual, odd and even parts per shift, consecutive-shift jumps, baseline-repeat difference; floor candidates are reported, not adopted"},
        "not_claimed": ["XFID response, sign or ranking", "an adopted response floor (X3 registers floors)", "certified geometry", "physical accuracy or grid independence", "any qualification flag change"],
        "qualification_flags": {k: False for k in ("shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")},
        "immutable": True,
        "registered_before_run": True,
    }
    EVID.mkdir(parents=True, exist_ok=True)
    text = json.dumps(criteria, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    for d in (EVID, DATASET):
        (d / "x2_criteria.json").write_text(text)
        (d / "x2_criteria.json.sha256").write_text(digest + "\n")
    (DATASET / "dataset-metadata.json").write_text(json.dumps({"title": "CFD Opt SDF XFID X2 Inputs", "id": "ramhachi888/cfd-opt-sdf-xfid-x2-inputs", "licenses": [{"name": "other"}]}, indent=2, sort_keys=True) + "\n")
    if bind_runner:
        runner = KERNEL / "runner.py"
        s = runner.read_text()
        import re
        runner.write_text(re.sub(r'CRITERIA_SHA256 = "[^"]*"', f'CRITERIA_SHA256 = "{digest}"', s, count=1))
    print(json.dumps({"criteria_sha256": digest, "cases": len(criteria["case_order"]), "dataset_files": len(inputs)}))


if __name__ == "__main__":
    main("--bind-runner" in sys.argv)
