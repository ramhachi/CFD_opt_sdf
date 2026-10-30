"""Synthetic G2 outputs with an analytic alpha-dependence (value and tangent), for verifier/analyzer tests."""
import csv
import json
import math
from pathlib import Path

from scripts import grad_g2_window as W

DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")


def make_rows(alpha=0.0, k=1.0, steps=range(8, 9033, 8), dt_per_step=120.0 / 8738.0):
    rows = []
    for s in steps:
        t0 = dt_per_step * s
        row = {"step": float(s), "t_u_l": t0 * (1 + 0.5 * alpha * k), "t_u_l_tan": 0.5 * k * t0}
        for i, name in enumerate(W.SERIES):
            base = (300.0 + 40 * i) + 0.02 * s + 5 * math.sin(0.001 * s + i)
            row[name] = base + alpha * k * (200.0 + 0.1 * s + 10 * i)
            row[name + "_tan"] = k * (200.0 + 0.1 * s + 10 * i)
        rows.append(row)
    return rows


def write_history(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(W.HEADER)
        for r in rows:
            writer.writerow([repr(r[c]) for c in W.HEADER])


def summary_for(rows, label, real_type):
    out = {"label": label, "real_type": real_type, "steps": int(rows[-1]["step"]), "total_seconds": 12.0, "peak_vram_bytes": 1,
           "fields_finite_incl_partials": True, "sample_count": len(rows)}
    for kernel_name, series in (("fx", "fx"), ("fz", "-fz")):
        for variant, flag in (("dual_time", True), ("frozen_time", False)):
            v, d = W.window_mean(rows, series, 80.0, 120.0, time_tangent=flag)
            sign = 1.0 if series == "fx" else -1.0  # kernel reports the raw Fz mean; the host negates it for downforce
            out[f"window_mean_{kernel_name}_{variant}"] = {"value": sign * v, "tangent": sign * d}
    return out


def build_output(out_dir: Path, freeze: dict, *, plain_scale=1.0, damage=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    plain = make_rows(0.0)
    for r in plain:
        for c in list(r):
            if c.endswith("_tan"):
                r[c] = 0.0
    write_history(out_dir / "plain.history.csv", plain)
    (out_dir / "plain.summary.json").write_text(json.dumps(summary_for(plain, "plain", "Float32")))
    for k, name in enumerate(DIRECTIONS, start=1):
        rows = make_rows(0.0, k=float(k))
        write_history(out_dir / f"{name}.history.csv", rows)
        (out_dir / f"{name}.summary.json").write_text(json.dumps(summary_for(rows, name, "Dual")))
    index = {"status": "COMPLETE", "run_order": ["plain", *DIRECTIONS], "runs": {n: 1.0 for n in ["plain", *DIRECTIONS]},
             "window_t_u_l": [80.0, 120.0], "sample_every": 8, "backend": "cuda", "gpu_name": "Tesla T4",
             **freeze["runtime_pins"]}
    (out_dir / "g2_run_index.json").write_text(json.dumps(index))
    identity = {"source_commit": freeze["source_commit"], "failure_stage": None, "spike_exit_code": 0, "verified": dict(freeze["pins"])}
    (out_dir / "run_identity.json").write_text(json.dumps(identity))
    (out_dir / "DONE").write_text("ok\n")
    import hashlib
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out_dir.iterdir()) if p.name != "output_manifest.json"}
    (out_dir / "output_manifest.json").write_text(json.dumps({"files": files}))
    return plain


def freeze_stub():
    return {"source_commit": "a" * 40, "pins": {"scripts/x.jl": "b" * 64},
            "runtime_pins": {"julia": "1.12.6", "waterlily": "1.8.0", "forwarddiff": "1.4.5", "cuda_jl": "6.3.1"}}


def formal_stub(path: Path, plain_rows):
    v, _ = W.window_mean(plain_rows, "fx", 80.0, 120.0)
    z, _ = W.window_mean(plain_rows, "-fz", 80.0, 120.0)
    path.write_text(json.dumps({"states": [{"name": "baseline_v17", "host_recomputed_physical_forces": {
        "drag_n": v * W.FORCE_SCALE_N_PER_SOLVER, "downforce_n": z * W.FORCE_SCALE_N_PER_SOLVER}}]}))
