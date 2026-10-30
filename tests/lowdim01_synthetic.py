"""Synthetic LOWDIM-01 kernel output (analytic responses) for analyzer tests."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import analyze_lowdim01 as A  # noqa: E402
import lowdim01_states as L  # noqa: E402
import step01_synthetic as S1  # noqa: E402

INV = json.loads((ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json").read_text())
FORMAL = json.loads(A.FORMAL_CRITERIA.read_text())
PINS = {"scripts/x.jl": "11" * 32}
BASE = {"drag": 0.3239039699743226, "downforce": 0.3316344583180616}


def make_kernel(root, inv, responses, *, break_baseline=False, drop=None, failed=None, gpu="Tesla T4", empty_manifest=False):
    out = Path(root) / "lowdim01_a"
    (out / "states").mkdir(parents=True)
    rows = {r["name"]: r for r in inv["states"]}
    index = {"kernel": "a", "states": [], "status": "COMPLETE"}
    for name in inv["kernels"]["a"]:
        row = rows[name]
        if name == drop:
            continue
        d = out / "states" / name; d.mkdir()
        drag, down = responses(row)
        if break_baseline and row["kind"] == "baseline":
            drag *= 1.001
        S1.force_csv(d / "flow_24.forces.csv", drag, down)
        host = A.recompute_force_n(d / "flow_24.forces.csv", {"measurement": FORMAL["measurement"]})
        (d / "flow_24.summary.json").write_text(json.dumps({
            "phi_fortran_sha256": row["phi_fortran_order_sha256"], "state_sha256": row["state_sha256"], "state_npz_sha256": row["npz_sha256"], "phi_c_order_sha256": row["phi_c_order_sha256"],
            "gpu_name": gpu, "phi_margin_m": row["zero_level_margin_m"], "phi_margin_gate_m": 0.15, "finite_u": True, "finite_p": True, "finite_forces": True, "case_id": "flow_24",
            "t_end_reached": 120.0028, "julia_threads": 1, "drag_time_weighted_n": host["drag_n"], "downforce_time_weighted_n": host["downforce_n"]}))
        (d / "W4_JOB_DONE").write_text("x")
        index["states"].append({"name": name, "kind": row["kind"], "exit_code": 0, "complete": name != failed, "forces_csv_sha256": A.sha256(d / "flow_24.forces.csv")})
    (out / "lowdim01_index.json").write_text(json.dumps(index))
    (out / "run_identity.json").write_text(json.dumps({"kernel": "a", "source_commit": "a" * 40, "failure_stage": None, "fd08_baseline_csv_sha256": inv["fd08_baseline_reference"]["forces_csv_sha256"],
                                                        "verified": PINS}))
    (out / "nvidia_smi.csv").write_text(f"0, {gpu}, GPU-abc, 15360 MiB, 535.1\n")
    (out / "DONE").write_text("x")
    files = {str(p.relative_to(out)): A.sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": {} if empty_manifest else files}))
    return out


def make_all(root, *, gains=None, drags=None, gates_fail=(), control_gains=None, nan_candidate=None, **kw):
    """gains: {step_mm: downforce change in N}; drags: {step_mm: drag change in N}; gates_fail: step_mm values whose registered hard gates fail."""
    Path(root).mkdir(parents=True, exist_ok=True)
    inv = copy.deepcopy(INV)
    tmp = Path(root) / "ref.csv"; S1.force_csv(tmp, BASE["drag"], BASE["downforce"])
    host = A.recompute_force_n(tmp, {"measurement": FORMAL["measurement"]})
    inv["fd08_baseline_reference"]["forces_csv_sha256"] = A.sha256(tmp)
    inv["fd08_baseline_reference"]["host_recomputed_n"] = {k: host[k] for k in ("drag_n", "downforce_n")}
    for r in inv["states"]:
        if r["kind"] in ("candidate", "control"):
            ok = r["step_mm"] not in gates_fail or r["kind"] == "control"
            r["geometry_gates"]["gates"] = {k: True for k in r["geometry_gates"]["gates"]}
            r["geometry_gates"]["gates"]["smoothed_volume_band"] = ok
            r["geometry_gates"]["all_hard_gates_pass"] = ok
    gains = gains or {}
    drags = drags or {}

    def responses(row):
        if row["kind"] == "baseline":
            return BASE["drag"], BASE["downforce"]
        s = row["step_mm"]
        if row["kind"] == "control":
            return BASE["drag"] - 1e-4, BASE["downforce"] + (control_gains or {}).get(s, -2e-3)
        return BASE["drag"] + drags.get(s, -1e-4), BASE["downforce"] + gains.get(s, -1e-3)

    out = make_kernel(root, inv, responses, **kw)
    if nan_candidate is not None:
        p = out / "states" / nan_candidate / "flow_24.forces.csv"
        p.write_text(p.read_text().replace("\n500,", "\n500,nan,", 1))
    freeze = {"source_commit": "a" * 40, "pins": PINS, "fd08_baseline": {"forces_csv_sha256": inv["fd08_baseline_reference"]["forces_csv_sha256"]},
              "step01_analysis_sha256": A.sha256(ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json"),
              "file_hashes": {"analyzer": A.sha256(Path(A.__file__)), "contract": A.sha256(ROOT / "src/cfd_sdf/lowdim01_contract.py"), "states_module": A.sha256(ROOT / "scripts/lowdim01_states.py"),
                              "step01_states_module": A.sha256(ROOT / "scripts/step01_states.py"), "force_io": A.sha256(ROOT / "scripts/fd08_v2_campaign_io.py"),
                              "formal_criteria": A.sha256(A.FORMAL_CRITERIA),
                              "inventory_canonical_json": hashlib.sha256((json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()).hexdigest()}}
    return out, freeze, inv
