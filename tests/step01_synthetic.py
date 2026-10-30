"""Synthetic STEP-01 kernel outputs (analytic responses) for analyzer tests."""
import copy
import csv
import hashlib
import json
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_step01 as A  # noqa: E402
import step01_states as S  # noqa: E402
from fd08_v2_campaign_io import FORCE_COLUMNS  # noqa: E402

INV = json.loads((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json").read_text())
FORMAL = json.loads(A.FORMAL_CRITERIA.read_text())
SCALE = 1.0 / 900.0                                     # N per solver force unit (flow_24)
BASE = {"drag": 0.3239039699743226, "downforce": 0.3316344583180616}
PINS = {"scripts/x.jl": "11" * 32}
DIRFILES = {"docs/x.raw": "22" * 32}


def ghat(direction, resp):
    return float(FORMAL["calibration_binding"]["fits"][f"{direction}|{resp}"]["g_n_per_m"])


GHAT_SCALE = {"value": 1.0}


def model(direction, resp, s_mm, curvature=0.0, flip_at=None):
    """R - R0 of a single direction at the signed step s_mm: linear (g_hat) + even quadratic + an optional sign reversal of the slope at |s| >= flip_at."""
    g = ghat(direction, resp) * (0.8 if resp == "drag" else 1.0) * GHAT_SCALE["value"]
    s = s_mm / 1000.0
    out = g * s + curvature * abs(g) * s * s * 50.0
    if flip_at is not None and abs(s_mm) >= flip_at:
        out = -out
    return out


def force_csv(path, drag_n, down_n):
    drag_s, down_s = drag_n / SCALE, down_n / SCALE
    with Path(path).open("w", newline="") as handle:
        w = csv.writer(handle); w.writerow(FORCE_COLUMNS)
        for step, t in ((8, 79.0), (500, 90.0), (900, 110.0), (1000, 121.0)):
            w.writerow([step, t, drag_s, 0.0, -down_s, drag_s, down_s, drag_s, 0.0, -down_s, 0.0, 0.0, 0.0])


def make_kernel(root, kernel, inv, responses, *, break_baseline=False, drop=None, failed=None, gpu="Tesla T4", flip=None, break_baseline_kernel=None, empty_manifest=False):
    out = Path(root) / f"step01_{kernel}"
    (out / "states").mkdir(parents=True)
    rows = {r["name"]: r for r in inv["states"] if r["kernel"] == kernel}
    index = {"kernel": kernel, "states": [], "status": "COMPLETE"}
    for name in inv["kernels"][kernel]:
        row = rows[name]
        if name == drop:
            continue
        d = out / "states" / name; d.mkdir()
        drag, down = responses(row)
        if row["kind"] == "baseline" and (break_baseline or break_baseline_kernel == kernel):
            drag *= 1.001
        force_csv(d / "flow_24.forces.csv", drag, down)
        host = A.recompute_force_n(d / "flow_24.forces.csv", {"measurement": FORMAL["measurement"]})
        (d / "flow_24.summary.json").write_text(json.dumps({
            "phi_fortran_sha256": row["phi_fortran_order_sha256"], "state_sha256": row["state_sha256"], "state_npz_sha256": row["npz_sha256"], "phi_c_order_sha256": row["phi_c_order_sha256"],
            "gpu_name": gpu, "phi_margin_m": row["zero_level_margin_m"], "phi_margin_gate_m": 0.15, "finite_u": True, "finite_p": True, "finite_forces": True, "case_id": "flow_24",
            "t_end_reached": 120.0028, "julia_threads": 1, "drag_time_weighted_n": host["drag_n"], "downforce_time_weighted_n": host["downforce_n"]}))
        (d / "W4_JOB_DONE").write_text("x")
        index["states"].append({"name": name, "kind": row["kind"], "exit_code": 0, "complete": name != failed, "forces_csv_sha256": A.sha256(d / "flow_24.forces.csv")})
    (out / "step01_index.json").write_text(json.dumps(index))
    (out / "run_identity.json").write_text(json.dumps({"kernel": kernel, "source_commit": "a" * 40, "failure_stage": None, "fd08_baseline_csv_sha256": inv["fd08_baseline_reference"]["forces_csv_sha256"],
                                                        "verified": {**PINS, **DIRFILES}}))
    (out / "nvidia_smi.csv").write_text(f"0, {gpu}, GPU-abc, 15360 MiB, 535.1\n")
    (out / "DONE").write_text("x")
    files = {str(p.relative_to(out)): A.sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": {} if empty_manifest else files}))
    return out


def make_all(root, *, curvature=0.0, flip_at=None, flip_series=None, combo_defect=0.0, amplitude=1.0, ghat_scale=1.0, combo_curvature=None, empty_pins=False, **kw):
    Path(root).mkdir(parents=True, exist_ok=True)
    GHAT_SCALE["value"] = ghat_scale
    inv = copy.deepcopy(INV)
    # the synthetic baseline replaces FD-08's reference (the real one cannot be produced by an analytic fixture)
    tmp = Path(root) / "ref.csv"; force_csv(tmp, BASE["drag"], BASE["downforce"])
    inv["fd08_baseline_reference"]["forces_csv_sha256"] = A.sha256(tmp)
    inv["fd08_baseline_reference"]["host_recomputed_n"] = A.recompute_force_n(tmp, {"measurement": FORMAL["measurement"]}) and {
        k: A.recompute_force_n(tmp, {"measurement": FORMAL["measurement"]})[k] for k in ("drag_n", "downforce_n")}

    def responses(row):
        if row["kind"] == "baseline":
            return BASE["drag"], BASE["downforce"]
        sign = row["sign"]
        if row["kind"] == "single":
            d = row["directions"][0]
            fa = flip_at if (flip_series is None or d == flip_series) else None
            return tuple(BASE[r] + amplitude * model(d, r, sign * row["step_mm"], curvature, fa) for r in ("drag", "downforce"))
        comp = row["component_step_mm"]
        vals = []
        for r in ("drag", "downforce"):
            total = BASE[r] + sum(amplitude * model(d, r, sign * comp, curvature if combo_curvature is None else combo_curvature, None) for d in row["directions"])
            vals.append(total + combo_defect * sign * 1e-3)
        return tuple(vals)

    dirs = {k: make_kernel(root, k, inv, responses, **kw) for k in S.KERNELS}
    fits = {k: {"g_n_per_m": v["g_n_per_m"], "se_g_n_per_m": v["se_g_n_per_m"]} for k, v in FORMAL["calibration_binding"]["fits"].items()}
    freeze = {"source_commit": "a" * 40, "pins": {} if empty_pins else PINS, "direction_files": {} if empty_pins else DIRFILES,
              "fd08_baseline": {"forces_csv_sha256": inv["fd08_baseline_reference"]["forces_csv_sha256"]}, "fd08_g_hat_fits": fits,
              "file_hashes": {"analyzer": A.sha256(Path(A.__file__)), "contract": A.sha256(ROOT / "src/cfd_sdf/step01_contract.py"), "states_module": A.sha256(ROOT / "scripts/step01_states.py"),
                              "force_io": A.sha256(ROOT / "scripts/fd08_v2_campaign_io.py"), "formal_criteria": A.sha256(A.FORMAL_CRITERIA),
                              "inventory_canonical_json": hashlib.sha256((json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()).hexdigest()}}
    return dirs, freeze, inv
