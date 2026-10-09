"""Synthetic LOWDIM-02A (flow_32) kernel output (analytic responses) for analyzer tests."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import analyze_lowdim02a as A  # noqa: E402
import step01_synthetic as S1  # noqa: E402

INV = json.loads((ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09/inventory.json").read_text())
FORMAL = json.loads(A.FORMAL_CRITERIA.read_text())
CRIT = A.flow32_criteria(FORMAL)
PINS = {"scripts/x.jl": "11" * 32}
BASE = {"drag": 0.35002673442739357, "downforce": 0.3612783598966907}
SCALE32 = 0.025 ** 2


def force_csv(path, drag_n, down_n):
    S1.force_csv(path, drag_n * S1.SCALE / SCALE32, down_n * S1.SCALE / SCALE32)     # the N values come back through the flow_32 scale


def make_kernel(root, inv, responses, *, drop=None, failed=None, gpu="Tesla T4", empty_manifest=False, wrong_case=False):
    out = Path(root) / "lowdim02a_a"
    (out / "states").mkdir(parents=True)
    rows = {r["name"]: r for r in inv["states"]}
    index = {"kernel": "a", "states": [], "status": "COMPLETE"}
    for name in inv["kernels"]["a"]:
        row = rows[name]
        if name == drop:
            continue
        d = out / "states" / name; d.mkdir()
        drag, down = responses(row)
        force_csv(d / "flow_32.forces.csv", drag, down)
        host = A.recompute_force_n(d / "flow_32.forces.csv", CRIT)
        (d / "flow_32.summary.json").write_text(json.dumps({
            "phi_fortran_sha256": row["phi_fortran_order_sha256"], "state_sha256": row["state_sha256"], "state_npz_sha256": row["npz_sha256"], "phi_c_order_sha256": row["phi_c_order_sha256"],
            "gpu_name": gpu, "phi_margin_m": row["zero_level_margin_m"], "phi_margin_gate_m": 0.15, "finite_u": True, "finite_p": True, "finite_forces": True,
            "case_id": "flow_24" if wrong_case else "flow_32", "t_end_reached": 120.0028, "julia_threads": 1, "drag_time_weighted_n": host["drag_n"], "downforce_time_weighted_n": host["downforce_n"]}))
        (d / "W4_JOB_DONE").write_text("x")
        index["states"].append({"name": name, "kind": row["kind"], "exit_code": 0, "complete": name != failed, "forces_csv_sha256": A.sha256(d / "flow_32.forces.csv")})
    (out / "lowdim02a_index.json").write_text(json.dumps(index))
    (out / "run_identity.json").write_text(json.dumps({"kernel": "a", "source_commit": "a" * 40, "failure_stage": None, "flow32_baseline_csv_sha256": inv["flow32_baseline_reference"]["forces_csv_sha256"],
                                                        "verified": PINS}))
    (out / "nvidia_smi.csv").write_text(f"0, {gpu}, GPU-abc, 15360 MiB, 535.1\n")
    (out / "DONE").write_text("x")
    files = {str(p.relative_to(out)): A.sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": {} if empty_manifest else files}))
    return out


def make_all(root, *, plus=2e-4, minus=-1e-3, plus25=-3e-5, drag_plus=-1e-4, repeat_shift=0.0, gates_fail=False, break_baseline=False, **kw):
    """plus/minus/plus25: downforce changes (N) of the +1.25 / -1.25 / +2.5 mm states; drag_plus: drag change of +1.25 mm; repeat_shift: downforce of the baseline repeat minus the baseline."""
    Path(root).mkdir(parents=True, exist_ok=True)
    inv = copy.deepcopy(INV)
    tmp = Path(root) / "ref.csv"; force_csv(tmp, BASE["drag"], BASE["downforce"])
    host = A.recompute_force_n(tmp, CRIT)
    inv["flow32_baseline_reference"]["forces_csv_sha256"] = A.sha256(tmp)
    inv["flow32_baseline_reference"]["host_recomputed_n"] = {k: host[k] for k in ("drag_n", "downforce_n")}
    for r in inv["states"]:
        if r["kind"] in ("candidate", "control", "descriptive"):
            r["geometry_gates"]["gates"] = {k: True for k in r["geometry_gates"]["gates"]}
            r["geometry_gates"]["gates"]["smoothed_volume_band"] = not (gates_fail and r["kind"] == "candidate")
            r["geometry_gates"]["all_hard_gates_pass"] = all(r["geometry_gates"]["gates"].values())

    def responses(row):
        d, f = BASE["drag"], BASE["downforce"]
        if row["kind"] == "baseline":
            return d * (1.001 if break_baseline else 1.0), f
        if row["kind"] == "baseline_repeat":
            return d, f + repeat_shift
        if row["kind"] == "candidate":
            return d + drag_plus, f + plus
        if row["kind"] == "control":
            return d - 1e-4, f + minus
        return d - 1e-4, f + plus25

    out = make_kernel(root, inv, responses, **kw)
    freeze = {"source_commit": "a" * 40, "pins": PINS, "flow32_baseline": {"forces_csv_sha256": inv["flow32_baseline_reference"]["forces_csv_sha256"]},
              "file_hashes": {"analyzer": A.sha256(Path(A.__file__)), "contract": A.sha256(ROOT / "src/cfd_sdf/lowdim02a_contract.py"), "step01_states_module": A.sha256(ROOT / "scripts/step01_states.py"),
                              "force_io": A.sha256(ROOT / "scripts/fd08_v2_campaign_io.py"), "formal_criteria": A.sha256(A.FORMAL_CRITERIA), "job": A.sha256(ROOT / "scripts/waterlily_lowdim02_flow32_job.jl"),
                              "lowdim01_analysis": A.sha256(A.LOWDIM01_ANALYSIS),
                              "inventory_canonical_json": hashlib.sha256((json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()).hexdigest()}}
    return out, freeze, inv
