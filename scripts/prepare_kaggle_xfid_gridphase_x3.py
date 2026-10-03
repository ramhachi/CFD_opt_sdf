"""Register XFID X3 criteria and stage the private Kaggle input dataset.

Usage: prepare_kaggle_xfid_gridphase_x3.py calibration [--bind-runner]
Writes docs/evidence/xfid_gridphase_x3_2026_10_04/<mode>/x3_criteria.json(+.sha256) and
work/kaggle_xfid_gridphase_x3_<mode>_dataset/. State STLs are re-derived with the X1 build
functions from the saved Round 3 r=8 surfaces and must match the X1 result hashes.
"""

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_xfid45_stage_v_input_2026_10_04 as x1  # noqa: E402

R5 = ROOT / "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5"
NOBLE = ROOT / "infra/kaggle/kernel_openfoam_xfid_v16"
KERNEL = ROOT / "infra/kaggle/kernel_openfoam_xfid_gridphase_x3"
X1_RESULT = ROOT / "docs/evidence/xfid45_stage_v_input_2026_10_04/result.json"
EVID = ROOT / "docs/evidence/xfid_gridphase_x3_2026_10_04"
SHIFT_RANGE_MM = (0.5, 4.0)  # per-axis magnitude, all three components non-zero


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def halton(i, base):
    f, r = 1.0, 0.0
    while i > 0:
        f /= base
        r += f * (i % base)
        i //= base
    return r


def shift_set(n_pairs):
    """Deterministic low-discrepancy shift vectors in mm with exact mirror pairs (v, -v)."""
    lo, hi = SHIFT_RANGE_MM
    out = []
    for k in range(1, n_pairs + 1):
        v = [round((1 if halton(k, sb) < 0.5 else -1) * (lo + (hi - lo) * halton(k, mb)), 6)
             for mb, sb in ((2, 7), (3, 11), (5, 13))]
        out.append(v)
    return out


def phase_cases(state, tag, n_pairs):
    cases = []
    for k, v in enumerate(shift_set(n_pairs), 1):
        for sign, t in ((1, "p"), (-1, "m")):
            cases.append({"id": f"{tag}_{state}_{k:02d}{t}", "state": state, "shift_m": [sign * x / 1000 for x in v]})
    return cases


def state_stl(state):
    z = np.load(x1.R3 / state / "surface.npz")
    v, f, _ = x1.remove_small_components(z["vertices"], z["faces"])
    blob = x1.stl_bytes(v, f)
    expected = json.loads(X1_RESULT.read_text())["cases"][state]["derived_stl_sha256"]
    assert hashlib.sha256(blob).hexdigest() == expected, f"{state}: STL differs from the X1 result"
    return blob, int(len(f))


def main(mode, bind_runner):
    assert mode == "calibration", "formal mode is registered separately after the calibration result"
    states = ["baseline"]
    dataset = ROOT / f"work/kaggle_xfid_gridphase_x3_{mode}_dataset"
    if dataset.exists():
        shutil.rmtree(dataset)
    (dataset / "case_template").mkdir(parents=True)
    (dataset / "states").mkdir()
    state_info = {}
    for s in states:
        blob, tri = state_stl(s)
        (dataset / f"states/{s}.stl").write_bytes(blob)
        state_info[s] = {"file": f"states/{s}.stl", "sha256": hashlib.sha256(blob).hexdigest(), "triangles": tri}
    for src in sorted((R5 / "case_template").rglob("*")):
        rel = src.relative_to(R5 / "case_template")
        if src.is_file() and rel.as_posix() != "constant/triSurface/design_candidate.stl":
            (dataset / "case_template" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dataset / "case_template" / rel)
    shutil.copy2(R5 / "openfoam_package_lock.json", dataset / "openfoam_package_lock_jammy.json")
    shutil.copy2(NOBLE / "openfoam_package_lock.json", dataset / "openfoam_package_lock_noble.json")
    r5 = json.loads((R5 / "criteria.json").read_text())
    inputs = {p.relative_to(dataset).as_posix(): sha(p) for p in sorted(dataset.rglob("*")) if p.is_file()}
    cases = phase_cases("baseline", "cal", 16)
    criteria = {
        "round_id": "xfid45_x3_calibration_r1",
        "date": "2026-10-04",
        "evidence_class": "openfoam_stage_v_gridphase_calibration_uncertified_geometry",
        "authority": "docs/issues/45_x3_design_2026_10_04.md (user-approved defaults) and docs/issues/45_xfid_gridphase_x2_result_2026_10_04.md",
        "purpose": "calibration (disjoint from every formal XFID case): phase noise of a single OpenFOAM state under 32 registered rigid sub-cell shifts of the unperturbed baseline, and a test that ensemble means average as 1/sqrt(M); calibration cases cannot satisfy formal evidence",
        "environment": {**r5["environment"], "registered_lock_suites": ["jammy", "noble"],
                        "note": "lock chosen by the observed Ubuntu codename (X2: Jammy and Noble are bit-identical for the v16 fixture); host recorded in environment.json; any other OS fails closed with diagnostics"},
        "states": state_info,
        "inputs": inputs,
        "case_template_origin": "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template (hash-identical, minus the v16 candidate STL)",
        "force_window": {"minimum_rows": 20, "tail_fraction": 0.25, "force_n_per_coefficient": r5["fixture"]["force_reference"]["force_n_per_coefficient"],
                         "rule": "last-25% iteration-tail window as in Round 5 and X2; forces in N from forceCoeffs Cd and -Cl"},
        "shift_design": {"n_pairs": 16, "range_mm_per_axis_magnitude": list(SHIFT_RANGE_MM),
                         "generator": "Halton bases (2,3,5) for magnitudes and (7,11,13) for signs, indices 1..16, rounded to 1e-6 mm; every vector is paired with its exact mirror (-v); all three components non-zero so no member sits on a symmetric grid phase (X2)"},
        "case_order": cases,
        "launch_deadline_hours": 3.0,
        "stage_timeout_s": 1800,
        "stop_after_consecutive_failures": 3,
        "per_case_failure_policy": "record the failing stage and continue; checkMesh exit 1 with exactly one concave-cell failure and fraction <= 0.08 is allowed; no retries; result.json rewritten after every case",
        "analysis": {
            "script": "scripts/analyze_xfid_gridphase_x3_calibration.py",
            "model": "per response, R_k = a + b.v_k + e_k over the 32 members (linear translation term), sigma_e = residual std with 28 degrees of freedom; sigma_S_single = sigma_e (one state of a contrast pair has this phase noise)",
            "averaging_check": "over all balanced splits of the 16 mirror pairs into two sets of 8 pairs, the RMS difference of the two set means is compared with the prediction sigma_e*sqrt(2/16); the 1/sqrt(M) model is accepted for that response only if the ratio observed/predicted lies in [0.5, 2.0] (fixed before the run); otherwise the formal design must not assume 1/sqrt(M)",
            "reported_not_adopted": ["sigma_e", "standard error of the 32-member mean", "linear translation coefficients", "baseline (unshifted, X2) force versus the ensemble mean"]},
        "not_claimed": ["XFID response, sign or ranking", "an adopted response floor (the formal registration adopts floors)", "certified geometry", "physical accuracy or grid independence", "any qualification flag change"],
        "qualification_flags": {k: False for k in ("shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")},
        "immutable": True,
        "registered_before_run": True,
    }
    out = EVID / mode
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(criteria, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    for d in (out, dataset):
        (d / "x3_criteria.json").write_text(text)
        (d / "x3_criteria.json.sha256").write_text(digest + "\n")
    (dataset / "dataset-metadata.json").write_text(json.dumps({"title": "CFD Opt SDF XFID X3 Inputs", "id": "ramhachi888/cfd-opt-sdf-xfid-x3-inputs", "licenses": [{"name": "other"}]}, indent=2, sort_keys=True) + "\n")
    if bind_runner:
        runner = KERNEL / "runner.py"
        runner.write_text(re.sub(r'CRITERIA_SHA256 = "[^"]*"', f'CRITERIA_SHA256 = "{digest}"', runner.read_text(), count=1))
    print(json.dumps({"criteria_sha256": digest, "cases": len(cases), "dataset_files": len(inputs)}))


if __name__ == "__main__":
    main(sys.argv[1], "--bind-runner" in sys.argv)
