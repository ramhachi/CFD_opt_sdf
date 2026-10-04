"""Register XFID part B (WaterLily Candidate C, T4) and stage the private Kaggle input dataset.

Usage: prepare_kaggle_xfid_candidate_c.py --source-commit <sha> [--bind-runner]
The source commit must already be pushed to origin/codex/kaggle-batch-migration and contain every
registered source input (the kernel fetches and checks it out). Writes
docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json(+.sha256) and
work/kaggle_xfid_candidate_c_dataset/.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
W4C = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json"
PRE = ROOT / "docs/evidence/xfid01_geometry_preflight_2026_10_03"
X1_RESULT = ROOT / "docs/evidence/xfid45_stage_v_input_2026_10_04/result.json"
FORMAL_CRITERIA = ROOT / "docs/evidence/xfid_gridphase_x3_2026_10_04/formal/x3_criteria.json"
KERNEL = ROOT / "infra/kaggle/kernel_xfid_candidate_c"
EVID = ROOT / "docs/evidence/xfid_candidate_c_2026_10_04"
DATASET = ROOT / "work/kaggle_xfid_candidate_c_dataset"
JOB = "scripts/waterlily_xfid_candidate_c_job.jl"
SOURCE_KEYS = ("candidate_c_body", "case_module", "device_grid", "kaggle_smoke", "manifest", "normal_floor_body",
               "operator_identity_helper", "operator_identity_dependency", "operator_identity_record", "operator_identity_sha256",
               "owner_run_type", "profile_adapter", "project")
STATES = ["baseline", "D0_interface_offset_minus", "D0_interface_offset_plus", "D1_filtered_seed11_minus",
          "D1_filtered_seed11_plus", "D2_filtered_seed2026_minus", "D2_filtered_seed2026_plus"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def margin_m(phi, spacing):
    solid = phi < 0.0
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing for n in phi.shape]
    gap = np.minimum(np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]), gaps[2][None, None, :])
    return float(np.min(gap[solid] + phi[solid]))


def state_entry(name, npz_path, dataset):
    with np.load(npz_path, allow_pickle=False) as a:
        meta = json.loads(str(a["metadata"].item()))
        phi = np.asarray(a["phi"], dtype="<f4")
    raw = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    npz_name, raw_name = f"{name}.npz", f"{name}.phi_f4_fortran.raw"
    shutil.copy2(npz_path, dataset / npz_name)
    (dataset / raw_name).write_bytes(raw)
    phi_c = hashlib.sha256(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
    assert meta["phi_sha256"] == phi_c
    return {"name": name, "npz_file": npz_name, "raw_file": raw_name, "npz_sha256": sha(npz_path), "state_sha256": meta["state_sha256"],
            "phi_c_order_sha256": phi_c, "phi_fortran_sha256": hashlib.sha256(raw).hexdigest(),
            "phi_expected_margin_m": margin_m(phi, meta["spacing_m"])}


def main(source_commit, bind_runner):
    w4 = json.loads(W4C.read_text())
    x1 = json.loads(X1_RESULT.read_text())
    formal_sha = sha(FORMAL_CRITERIA)
    source_inputs = {k: {"path": w4["inputs"][k]["path"], "sha256": sha(ROOT / w4["inputs"][k]["path"])} for k in SOURCE_KEYS}
    source_inputs["job"] = {"path": JOB, "sha256": sha(ROOT / JOB)}
    for k, e in source_inputs.items():  # the pinned commit must contain exactly these bytes
        blob = subprocess.run(["git", "show", f"{source_commit}:{e['path']}"], cwd=ROOT, capture_output=True, check=True).stdout
        assert hashlib.sha256(blob).hexdigest() == e["sha256"], f"source commit does not contain registered bytes for {k}"
    subprocess.run(["git", "merge-base", "--is-ancestor", source_commit, "origin/codex/kaggle-batch-migration"], cwd=ROOT, check=True)
    for k in ("operator_identity_record", "operator_identity_sha256", "candidate_c_body", "normal_floor_body"):
        assert source_inputs[k]["sha256"] == w4["inputs"][k]["sha256"], f"{k} drifted from the W4-C registration"
    if DATASET.exists():
        shutil.rmtree(DATASET)
    DATASET.mkdir(parents=True)
    order = []
    for name in STATES:
        path = PRE / ("canonical_state.npz" if name == "baseline" else f"state_snapshots/{name}.npz")
        e = state_entry(name, path, DATASET)
        e["stage_v_stl_sha256"] = x1["cases"][name]["derived_stl_sha256"]  # lineage to the OpenFOAM-side STL
        order.append(e)
    rep = dict(order[0], name="baseline_repeat")  # determinism check: same bytes, second run
    order.insert(1, rep)
    dataset_files = {p.relative_to(DATASET).as_posix(): sha(p) for p in sorted(DATASET.rglob("*")) if p.is_file()}
    geometry = {k: w4["geometry"][k] for k in ("point_shape", "cell_shape", "design_lattice_spacing_m", "canonical_sdf_origin_m",
                                               "source_surface_sha256", "phi_margin_gate_m", "phi_margin_tolerance_m")}
    case = next(c for c in w4["cases"] if c["case_id"] == "flow_24")
    backend = dict(w4["backend"], driver_version_policy="recorded_not_gated")
    backend.pop("driver_version")
    criteria = {
        "round_id": "xfid45_part_b_candidate_c_r1",
        "kind": "xfid_candidate_c_flow24_seven_states",
        "date": "2026-10-04",
        "evidence_class": "xfid_formal_waterlily_candidate_c_side_uncertified_geometry",
        "authority": "docs/issues/45_x3_design_2026_10_04.md and docs/issues/45_x3_formal_openfoam_registration_2026_10_04.md (part A)",
        "part_a_formal_criteria_sha256": formal_sha,
        "immutable": True, "registered_before_computation": True, "status": "registered_not_run",
        "qualification_flags": {k: False for k in ("shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")},
        "source_commit": source_commit,
        "source_inputs": source_inputs,
        "operator": w4["operator"],
        "operator_identity": {"contract_path": w4["operator_identity_record"]["path"], "contract_sha256": w4["operator_identity_record"]["sha256"]},
        "backend": backend,
        "measurement": w4["measurement"],
        "case": case,
        "geometry": geometry,
        "state_order": order,
        "dataset_files": dataset_files,
        "per_state_timeout_s": 5400,
        "perturbation_lineage": "the six perturbed states are the byte-frozen xfid01_geometry_preflight state snapshots (D0/D1/D2 at -/+0.005 m); each state's OpenFOAM-side STL hash is bound in stage_v_stl_sha256 (X1 result)",
        "waterlily_side_rules": {
            "response": "R = time-weighted [80,120] tU/L window means in N (drag = +Fx, downforce = -Fz); S_d,r = (R(d,+) - R(d,-))/2 per direction d in {D0,D1,D2} and response r in {drag, downforce}",
            "deterministic_floor_n": "floor = max(1e-8 N, 3 * |R(baseline) - R(baseline_repeat)|) per response (FD-06 recorded an absolute resolution floor of 1e-8 N and bit-identical repeats); S resolved iff |S| > floor, strict",
            "scope_limit": "the floor covers solver determinism only; known WaterLily response non-smoothness (FD-05/06 plateau deviations 5-9%) is NOT included, so a WaterLily-side sign is a statement about the realized +/-5 mm pair, not a derivative",
            "per_state_gates": "solver-step markers, force component consistency, host recomputation of every metric within the registered tolerance, finiteness, t_end reached, state/body/backend identity, VRAM; a failed gate makes the state GATE_FAILED and its contrasts UNRESOLVED",
            "stationarity": "drift is recorded per state and reported; it does not stop the run (W4-C registered 0.02 for the unperturbed state)",
        },
        "verdict_script": {"path": "scripts/xfid_final_verdict.py", "sha256": sha(ROOT / "scripts/xfid_final_verdict.py")},
        "verdict_rules": "exactly those of part A (criteria SHA-256 above): six required sign contrasts; AGREE / DISAGREE / UNRESOLVED; part B changes no rule",
        "not_claimed": ["XFID verdict (computed only by the verdict script after both sides exist)", "Candidate C physical qualification", "gradient, FD, optimizer, topology or shape-update qualification", "grid independence or high-Re/full-vehicle validity"],
    }
    EVID.mkdir(parents=True, exist_ok=True)
    text = json.dumps(criteria, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    for d in (EVID, DATASET):
        (d / "xfidc_criteria.json").write_text(text)
        (d / "xfidc_criteria.json.sha256").write_text(digest + "\n")
    (DATASET / "dataset-metadata.json").write_text(json.dumps({"title": "CFD Opt SDF XFID Candidate C Inputs", "id": "ramhachi888/cfd-opt-sdf-xfid-candidate-c-inputs", "licenses": [{"name": "other"}]}, indent=2, sort_keys=True) + "\n")
    if bind_runner:
        runner = KERNEL / "runner.py"
        runner.write_text(re.sub(r'CRITERIA_SHA256 = "[^"]*"', f'CRITERIA_SHA256 = "{digest}"', runner.read_text(), count=1))
    print(json.dumps({"criteria_sha256": digest, "states": len(order)}))


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[args.index("--source-commit") + 1], "--bind-runner" in args)
