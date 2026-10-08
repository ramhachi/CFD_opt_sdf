#!/usr/bin/env python3
"""Host terminal verification of the G2 kernel output; must pass before the bridge analyzer is run.

Recomputes every window mean (primal and tangent, with and without the time tangent) from the saved histories and
compares with the kernel's own summaries; checks run inventory, hashes, runtime pins, the Dual-vs-plain primal gate and
the plain-baseline reproduction of the registered FD-08 baseline_v17 measurement. No scientific threshold is applied
to the AD-vs-FD-08 discrepancy (that is the measured quantity).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grad_g2_window as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
WINDOW = (80.0, 120.0)
PRIMAL_GATE = 1e-3          # Dual window-mean primal vs plain (pre-registered)
BASELINE_GATE = 1e-6        # plain window mean vs registered FD-08 baseline_v17 (pre-registered harness gate)
SUMMARY_AGREEMENT = 1e-9    # host recomputation vs kernel summary
FORMAL_VERIFICATION = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_terminal_verification.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-300)


def close(a, b):
    return abs(a - b) <= SUMMARY_AGREEMENT * max(abs(a), abs(b), 1e-12)


def verify(out_dir: Path, freeze: dict, formal_verification: Path = FORMAL_VERIFICATION) -> dict:
    out_dir = Path(out_dir)
    problems: list[str] = []
    note = problems.append
    if not (out_dir / "DONE").is_file():
        note("DONE marker missing")
    if (out_dir / "ERROR.txt").exists() or (out_dir / "ERROR.json").exists():
        note("ERROR artifact present")
    identity = json.loads((out_dir / "run_identity.json").read_text())
    if identity.get("failure_stage") is not None or identity.get("spike_exit_code") != 0:
        note(f"runner reports failure: stage={identity.get('failure_stage')} exit={identity.get('spike_exit_code')}")
    if identity.get("source_commit") != freeze["source_commit"]:
        note("source commit differs from freeze")
    for rel_path, expected in freeze["pins"].items():
        if identity.get("verified", {}).get(rel_path) != expected:
            note(f"pin mismatch: {rel_path}")
    manifest = json.loads((out_dir / "output_manifest.json").read_text())["files"]
    for name, digest in manifest.items():
        if not (out_dir / name).is_file() or sha256(out_dir / name) != digest:
            note(f"output SHA mismatch: {name}")
    index = json.loads((out_dir / "g2_run_index.json").read_text())
    if index.get("status") != "COMPLETE":
        note(f"run index status {index.get('status')}")
    expected_runs = ["plain", *DIRECTIONS]
    if list(index.get("run_order", [])) != expected_runs or sorted(index.get("runs", {})) != sorted(expected_runs):
        note("run inventory differs from the registered five runs")
    extra = sorted(p.name for p in out_dir.glob("*.history.csv") if p.name[:-len(".history.csv")] not in expected_runs)
    if extra:
        note(f"unexpected histories: {extra}")
    if index.get("window_t_u_l") != list(WINDOW) or index.get("sample_every") != 8:
        note("window/sampling differs from the registered measurement")
    if "Tesla T4" not in str(index.get("gpu_name", "")) or index.get("backend") != "cuda":
        note("not a T4/CUDA run")
    for key, expected in freeze["runtime_pins"].items():
        if str(index.get(key)) != expected:
            note(f"runtime pin differs: {key}={index.get(key)} expected {expected}")

    recomputed: dict[str, dict] = {}
    histories = {}
    for label in expected_runs:
        try:
            rows = W.read_history(out_dir / f"{label}.history.csv")
        except Exception as error:  # noqa: BLE001 - recorded as a verification failure
            note(f"{label}: history unreadable: {error}"); continue
        histories[label] = rows
        summary = json.loads((out_dir / f"{label}.summary.json").read_text())
        if rows[0]["t_u_l"] > WINDOW[0] or rows[-1]["t_u_l"] < WINDOW[1]:
            note(f"{label}: window not reached"); continue
        entry = {"samples": len(rows), "t_last": rows[-1]["t_u_l"], "steps": summary.get("steps"),
                 "total_seconds": summary.get("total_seconds"), "peak_vram_bytes": summary.get("peak_vram_bytes")}
        if not summary.get("fields_finite_incl_partials"):
            note(f"{label}: fields not finite incl. partials")
        for kernel_name, series in (("fx", "fx"), ("fz", "-fz")):
            for variant, flag in (("dual_time", True), ("frozen_time", False)):
                v, d = W.window_mean(rows, series, *WINDOW, time_tangent=flag)
                k = summary[f"window_mean_{kernel_name}_{variant}"]
                kv, kd = (k["value"], k["tangent"]) if series == "fx" else (-k["value"], -k["tangent"])
                if not (close(v, kv) and close(d, kd)):
                    note(f"{label}: host recomputation differs from kernel summary ({kernel_name},{variant})")
                entry[f"{kernel_name}_{variant}"] = {"value": v, "tangent": d}
        recomputed[label] = entry
        if label == "plain" and any(r[c] != 0.0 for r in rows for c in W.HEADER if c.endswith("_tan")):
            note("plain history carries a non-zero tangent")
        if label != "plain" and not all(math.isfinite(e) and e != 0.0 for e in
                                         (entry["fx_dual_time"]["tangent"], entry["fz_dual_time"]["tangent"])):
            note(f"{label}: tangent non-finite or zero")

    integrity: dict = {}
    if "plain" in recomputed:
        plain = recomputed["plain"]
        scale = W.FORCE_SCALE_N_PER_SOLVER
        formal = json.loads(Path(formal_verification).read_text())
        base = next(s for s in formal["states"] if s["name"] == "baseline_v17")["host_recomputed_physical_forces"]
        drag_n, down_n = plain["fx_dual_time"]["value"] * scale, plain["fz_dual_time"]["value"] * scale
        integrity["plain_vs_formal_baseline_v17"] = {"drag_n": drag_n, "downforce_n": down_n,
                                                      "formal_drag_n": base["drag_n"], "formal_downforce_n": base["downforce_n"],
                                                      "rel_drag": rel(drag_n, base["drag_n"]), "rel_downforce": rel(down_n, base["downforce_n"])}
        if max(integrity["plain_vs_formal_baseline_v17"]["rel_drag"], integrity["plain_vs_formal_baseline_v17"]["rel_downforce"]) > BASELINE_GATE:
            note("plain baseline does not reproduce the registered FD-08 baseline_v17 measurement")
        for label in DIRECTIONS:
            if label not in recomputed:
                continue
            mean_diff = max(rel(recomputed[label]["fx_dual_time"]["value"], plain["fx_dual_time"]["value"]),
                            rel(recomputed[label]["fz_dual_time"]["value"], plain["fz_dual_time"]["value"]))
            by_step = {r["step"]: r for r in histories["plain"]}
            series_diff = max((rel(r[c], by_step[r["step"]][c]) for r in histories[label] if r["step"] in by_step for c in ("fx", "fz")), default=None)
            integrity[label] = {"window_mean_primal_rel_diff_max": mean_diff, "series_primal_rel_diff_max_report_only": series_diff}
            if mean_diff > PRIMAL_GATE:
                note(f"{label}: Dual window-mean primal differs from plain by {mean_diff:.3e}")

    return {
        "kind": "grad_g2_host_terminal_verification",
        "status": "PASS_G2_TERMINAL_INTEGRITY" if not problems else "FAIL_G2_TERMINAL_INTEGRITY",
        "problems": problems, "source_commit": identity.get("source_commit"), "runs": recomputed, "integrity": integrity,
        "gates": {"primal_window_mean_rel": PRIMAL_GATE, "baseline_reproduction_rel": BASELINE_GATE, "summary_agreement_rel": SUMMARY_AGREEMENT},
        "runtime": {k: index.get(k) for k in ("gpu_name", "cuda_jl", "julia", "waterlily", "forwarddiff", "backend")},
        "force_scale_n_per_solver_force": W.FORCE_SCALE_N_PER_SOLVER,
        "output_manifest_sha256": sha256(out_dir / "output_manifest.json"),
        "qualification_flags": {k: False for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        sys.exit("refusing to overwrite evidence")
    result = verify(args.out_dir, json.loads(args.freeze.read_text()))
    data = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    args.output.write_bytes(data)
    args.output.with_name(args.output.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(result["status"], *result["problems"], sep="\n")
    sys.exit(0 if result["status"].startswith("PASS") else 1)


if __name__ == "__main__":
    main()
