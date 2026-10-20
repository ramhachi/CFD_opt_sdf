#!/usr/bin/env python3
"""Fail-closed GRIDRES-01 analyzer: one finer-grid Kaggle kernel output (flow_40, or flow_48) + the retained OPT-01 Stage B flow_24/flow_32 force CSVs -> the grid-response verdict.

Copy-adapted from the frozen analyze_opt01b (never edited).  Per grid: downforce/drag changes relative to the parent (time-weighted window means exactly as the Stage B analyzer, through the
production `recompute_force_n`), a no-intercept least-squares fit Delta(s) = a*s + b*s^2 on the matched steps (+0.3125, +0.625, +1.25, -1.25 mm; the parent adds a zero row) and the forward-only fit,
the max fit residual, and the capability G_max = max(0, sup over s in (0, 1.25] mm of a*s + b*s^2).  Verdict on the analysed fine grid (plan Amendment 1 G4, downforce):
FLOWxx_SIDES_WITH_FLOW32 iff G_max > 4e-5 N; FLOWxx_SIDES_WITH_FLOW24 iff G_max < 2e-5 N; AMBIGUOUS otherwise; INCOMPLETE on an integrity failure or any fit residual above 2e-5 N.
--check verifies integrity and prints the verdict; --write writes the analysis once (never overwrites).  Amendment 2: the kernel also reruns the OPT-01 parent on flow_24 and flow_32 with the passive Poisson probe
(their force CSVs must equal the retained Stage B ones byte for byte), and every run's Poisson statistics are reported with the descriptive label POISSON_CONFOUNDED (see gridres01_states).  A residual-gate INCOMPLETE is a
scientific outcome and IS written (all deltas, fits, labelled verdict and reason); only integrity failures refuse to write.
The joint reading of flow_40 and flow_48 is not defined here: a flow_48 freeze states it (plan G2: reviewed separately).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_gridres01_kernel as K  # noqa: E402
import gridres01_states as G  # noqa: E402
from analyze_lowdim04b import FLAGS, SUMMARY_REL, _equal, _is_sha, _rel_error, git_tree_sha, jload, sha256  # noqa: E402,F401
from cfd_sdf.lowdim03_contract import DRAG_ALLOWANCE_N, MIN_DOWNFORCE_GAIN_N, finite  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402
from grid01_gpu import select_worker_gpu  # noqa: E402

EVIDENCE_REL = "docs/evidence/gridres01_2026_10_20"
FREEZE_KIND = "gridres01_prerun_freeze"
INFRA = ROOT / "infra/kaggle"
PARENT_INTEGRATION_COMMIT = "d0e79b4696d8b28d4f02e5fff272efa9ee0c28cb"  # the committed plan with Amendments 1 and 2: the source must descend from it
RETAINED = G.RETAINED_KERNEL  # OPT-01 Stage B kernel letters
Q = ("downforce", "drag")
EDGE_MM, HI_N, LO_N, RESIDUAL_MAX_N = 1.25, 4e-5, 2e-5, 2e-5
REQUIRED_FILES = {f"scripts/{n}.py" for n in ("analyze_gridres01", "gridres01_states", "gridres01_runner_template", "build_gridres01_kernel", "build_gridres01_inputs", "freeze_gridres01",
                                              "step01_states", "grid01_gpu")} | {"scripts/waterlily_gridres01_job.jl", "scripts/gridres01_poisson_probe.jl", "scripts/gridres01_poisson_passivity_check.jl", "src/cfd_sdf/lowdim03_contract.py", "docs/gridres01_plan_2026_10_20.md"}
FROZEN_PARAMETERS = {"min_downforce_gain_n": MIN_DOWNFORCE_GAIN_N, "drag_allowance_n": DRAG_ALLOWANCE_N, "steps_mm": list(G.STEPS_MM), "edge_mm": EDGE_MM, "g_max_sides_with_flow32_above_n": HI_N,
                     "g_max_sides_with_flow24_below_n": LO_N, "fit_residual_incomplete_above_n": RESIDUAL_MAX_N,
                     "poisson_iteration_cap": G.POISSON_ITERATION_CAP, "poisson_confounded_cap_fraction_excess_above": G.POISSON_MATERIAL_ABS, "parent_reruns": list(G.GRIDS["flow_40"]["parent_reruns"])}


def runtime_fixed(case: str) -> dict:
    spec = G.GRIDS[case]
    return {"machine_shape": "NvidiaTeslaT4", "kernel_timeout_s": spec["kernel_timeout_s"], "timeout_s": spec["kernel_timeout_s"], "per_state_timeout_s": spec["per_state_timeout_s"],
            "solver_wall_time_cap_s": spec["solver_wall_time_cap_s"], "instantiate_timeout_s": 2400, "gpu_probe_timeout_s": 300, "reserve_s": 300, "julia_threads": 1,
            "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0", "selected_gpu_physical_index": 0, "used_gpu_count": 1, "dataset_sources": []}


# ---- pure analysis (no I/O) -------------------------------------------------------------------------------------------------------------------------------------------------------------
def lsq(deltas: dict) -> dict:
    """No-intercept least squares of {step_mm: change} to a*s + b*s^2; a in N/mm, b in N/mm^2."""
    s = np.array(list(deltas), dtype=float)
    d = np.array(list(deltas.values()), dtype=float)
    a, b = np.linalg.lstsq(np.c_[s, s ** 2], d, rcond=None)[0]
    return {"a": float(a), "b": float(b), "max_residual_n": float(np.max(np.abs(d - (a * s + b * s * s))))}


def g_max(a: float, b: float) -> float:
    """sup over s in (0, 1.25] mm of a*s + b*s^2, floored at 0 (the s -> 0 limit): the endpoint, and the interior vertex when b < 0."""
    best = max(0.0, a * EDGE_MM + b * EDGE_MM ** 2)
    if b < 0 and 0 < -a / (2 * b) < EDGE_MM:
        best = max(best, -a * a / (4 * b))
    return best


def classify(g: float) -> str:
    return "SIDES_WITH_FLOW32" if g > HI_N else "SIDES_WITH_FLOW24" if g < LO_N else "AMBIGUOUS"


def grid_report(states: dict) -> dict:
    """states: state name -> {downforce_n, drag_n} for one grid (the five GRIDRES-01 states)."""
    out = {"delta_n": {}, "fit": {}, "forward_fit": {}}
    for q in Q:
        base = states[G.PARENT_NAME][f"{q}_n"]
        delta = {s: states[G.state_name(s)][f"{q}_n"] - base for s in G.STEPS_MM}
        out["delta_n"][q] = {f"{s:g}": v for s, v in delta.items()}
        out["fit"][q] = lsq(delta)
        out["forward_fit"][q] = lsq({s: v for s, v in delta.items() if s > 0})
    f = out["fit"]["downforce"]
    out["g_max_n"] = g_max(f["a"], f["b"])
    out["g_max_forward_fit_n"] = g_max(out["forward_fit"]["downforce"]["a"], out["forward_fit"]["downforce"]["b"])
    out["acceptance_emulation"] = {f"{s:g}": {"downforce_gain_n": out["delta_n"]["downforce"][f"{s:g}"], "drag_change_n": out["delta_n"]["drag"][f"{s:g}"],
                                              "accepted": bool(out["delta_n"]["downforce"][f"{s:g}"] > MIN_DOWNFORCE_GAIN_N and out["delta_n"]["drag"][f"{s:g}"] <= DRAG_ALLOWANCE_N)}
                                   for s in G.STEPS_MM if s > 0}
    return out


def labels(grids: dict, fine: str) -> dict:
    """Report-only: contraction ratios |x_fine - x_32| / |x_32 - x_24| for a and b, CONTRACTING if both <= 0.6, THIRD_VALUE if the fine value is more than half the 24-32 spread from both."""
    out, third = {"ratios": {}}, False
    for k in ("a", "b"):
        x24, x32, xf = (grids[g]["fit"]["downforce"][k] for g in ("flow_24", "flow_32", fine))
        spread = abs(x32 - x24)
        out["ratios"][k] = abs(xf - x32) / spread if spread > 0 else None
        third |= spread > 0 and abs(xf - x24) > spread / 2 and abs(xf - x32) > spread / 2
    out["contracting"] = all(r is not None and r <= 0.6 for r in out["ratios"].values())
    out["third_value"] = bool(third)
    return out


def report(tables: dict, fine: str) -> dict:
    """tables: grid -> state -> {downforce_n, drag_n} for flow_24, flow_32 and the fine grid."""
    grids = {g: grid_report(tables[g]) for g in ("flow_24", "flow_32", fine)}
    worst = max(r["fit"]["downforce"]["max_residual_n"] for r in grids.values())
    incomplete = not all(math.isfinite(x) for x in (worst, *[r["g_max_n"] for r in grids.values()])) or worst > RESIDUAL_MAX_N
    verdict = "INCOMPLETE" if incomplete else f"{fine.upper().replace('_', '')}_{classify(grids[fine]['g_max_n'])}"
    over = sorted(g for g, r in grids.items() if not r["fit"]["downforce"]["max_residual_n"] <= RESIDUAL_MAX_N)
    reason = (f"downforce fit residual above {RESIDUAL_MAX_N:g} N (or not finite) on {over}: the quadratic model does not hold there" if incomplete
              else f"G_max({fine}) = {grids[fine]['g_max_n']:.3e} N against the guard band [{LO_N:g}, {HI_N:g}] N")
    return {"verdict": verdict, "verdict_reason": reason, "fine_grid": fine, "grids": grids, "max_downforce_fit_residual_n": worst, "report_only_labels": labels(grids, fine)}


# ---- Poisson statistics (Amendment 2 H1/H3) -------------------------------------------------------------------------------------------------------------------------------------------------
def csv_steps(path: Path) -> list:
    return [int(float(line.split(",")[0])) for line in Path(path).read_text().splitlines()[1:]]


def poisson_summary(path: Path, steps: list | None = None) -> dict:
    """Parse one run's <case>.poisson.csv (header, one row per force sample): the solves at the iteration cap, iteration quantiles over all solves, residual (final r.r of the last solve of each sample) quantiles."""
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != "step,t_u_l,solves,iters_sum,iters_max,solves_at_cap,final_residual_l2,iters":
        raise ValueError("poisson CSV header differs")
    steps_seen, iters, resid = [], [], []
    for line in lines[1:]:
        f = line.split(",")
        if len(f) != 8:
            raise ValueError("poisson CSV row is malformed")
        n = [int(x) for x in f[7].split()]
        if not n or not all(0 <= v <= G.POISSON_ITERATION_CAP for v in n):
            raise ValueError("poisson iteration counts are missing or exceed the solver cap")
        if (int(f[2]), int(f[3]), int(f[4]), int(f[5])) != (len(n), sum(n), max(n), sum(v == G.POISSON_ITERATION_CAP for v in n)):
            raise ValueError("poisson CSV row aggregates differ from its iteration counts")
        r = float(f[6])
        if not math.isfinite(r) or r < 0:
            raise ValueError("poisson residual is not a finite non-negative number")
        steps_seen.append(int(float(f[0]))); iters += n; resid.append(r)
    if not steps_seen:
        raise ValueError("poisson CSV has no samples")
    if steps is not None and steps_seen != steps:
        raise ValueError("poisson samples do not match the force samples")
    q = lambda x: {k: float(np.percentile(x, p)) for k, p in (("p50", 50), ("p90", 90), ("p99", 99))} | {"min": float(np.min(x)), "max": float(np.max(x)), "mean": float(np.mean(x))}
    at_cap = sum(v == G.POISSON_ITERATION_CAP for v in iters)
    return {"samples": len(steps_seen), "solves": len(iters), "solves_at_cap": at_cap, "cap_fraction": at_cap / len(iters), "iterations": q(iters), "final_residual_l2": q(resid)}


def poisson_report(stats: dict, fine: str) -> dict:
    """stats: 'flow_24' / 'flow_32' -> summary of the parent rerun, fine grid -> {state name -> summary}.  Descriptive only: POISSON_CONFOUNDED iff the cap-hit fraction of flow_24 or of the worst flow_40 state
    exceeds flow_32's by more than G.POISSON_MATERIAL_ABS (absolute); it never changes the verdict."""
    frac = {"flow_24": stats["flow_24"]["cap_fraction"], "flow_32": stats["flow_32"]["cap_fraction"], fine: max(v["cap_fraction"] for v in stats[fine].values())}
    excess = {g: frac[g] - frac["flow_32"] for g in ("flow_24", fine)}
    confounded = any(e > G.POISSON_MATERIAL_ABS for e in excess.values())
    return {"cap_fraction_by_grid": frac, "cap_fraction_excess_over_flow_32": excess, "material_threshold_abs": G.POISSON_MATERIAL_ABS, "iteration_cap": G.POISSON_ITERATION_CAP,
            "label": "POISSON_CONFOUNDED" if confounded else None,
            "note": "descriptive: the grids differ in multigrid depth (WaterLily 1.8.0: flow_24 4, flow_32 6, flow_40 4, flow_48 5 levels) and the Poisson solve is capped; a label of None does not exclude a pressure-solver effect"}


# ---- retained flow_24 / flow_32 values (OPT-01 Stage B), hash-checked ---------------------------------------------------------------------------------------------------------------------
def retained_tables(root: Path = ROOT) -> dict:
    ana_path = root / G.OPT01B_REL / "opt01b_analysis.json"
    if sha256(ana_path) != G.OPT01B_ANALYSIS_SHA or sha256(root / G.OPT01B_REL / "inventory.json") != G.OPT01B_INVENTORY_SHA:
        raise ValueError("the OPT-01 Stage B analysis or inventory differs from its pinned hash")
    ana, inv = jload(ana_path), jload(root / G.OPT01B_REL / "inventory.json")
    tables = {}
    for grid, kernel in RETAINED.items():
        tables[grid] = {}
        for name in G.NAMES:
            csv = root / G.OPT01B_REL / f"kernel_output/opt01b_{kernel}/states/{name}/{grid}.forces.csv"
            rec = ana["state_forces_n"][grid][name]
            if sha256(csv) != rec["forces_csv_sha256"]:
                raise ValueError(f"retained force CSV differs from the Stage B analysis: {grid} {name}")
            host = recompute_force_n(csv, {"measurement": inv["grids"][kernel]["measurement"]})
            if any(_rel_error(host[f"{q}_n"], rec[f"{q}_n"]) > SUMMARY_REL for q in Q):
                raise ValueError(f"retained force CSV does not reproduce the Stage B value: {grid} {name}")
            tables[grid][name] = {f"{q}_n": host[f"{q}_n"] for q in Q}
    return tables


# ---- registration and kernel integrity (adapted from analyze_opt01b) -------------------------------------------------------------------------------------------------------------------
def validate_registration(freeze: Any, inventory: Any, case: str, *, check_tree: bool = True, infra: Path = INFRA) -> None:
    """The freeze binds every source file by hash, the rendered worker by re-rendering, the fixed budgets and the source commit by its tree id."""
    if not isinstance(freeze, dict) or freeze.get("kind") != FREEZE_KIND or freeze.get("case_id") != case:
        raise ValueError("freeze kind or case differs")
    _equal(freeze.get("qualification_flags"), {k: False for k in FLAGS}, "qualification flags")
    _equal(freeze.get("frozen_parameters"), FROZEN_PARAMETERS, "frozen parameters")
    inv_path = ROOT / EVIDENCE_REL / "inventory.json"
    if freeze.get("inventory_sha256") != sha256(inv_path) or inventory != jload(inv_path):
        raise ValueError("inventory differs from the frozen inventory")
    identity = ROOT / EVIDENCE_REL / f"identity_free_check_{case}.json"
    proof = freeze.get("identity_free_check", {})
    if proof.get("all_free") is not True or proof.get("owner") != "ramhachi888" or proof != jload(identity):
        raise ValueError("the authenticated identity-free check differs from the committed record")
    _equal(freeze.get("parent_integration_commit"), PARENT_INTEGRATION_COMMIT, "parent integration commit")
    required = REQUIRED_FILES | {inventory["parent"]["raw_path"], inventory["proposal"]["file"], inventory["opt01b_inventory"]["path"], inventory["opt01b_analysis"]["path"],
                                 f"{EVIDENCE_REL}/inventory.json", f"{EVIDENCE_REL}/prerun_note.md"}
    required |= {f"{G.OPT01B_REL}/kernel_output/opt01b_{k}/states/{n}/{g}.forces.csv" for g, k in RETAINED.items() for n in G.NAMES}
    if not required <= set(freeze["file_hashes"]):
        raise ValueError(f"the freeze omits required files: {sorted(required - set(freeze['file_hashes']))}")
    for rel, digest in freeze["file_hashes"].items():
        if not _is_sha(digest) or sha256(ROOT / rel) != digest:
            raise ValueError(f"frozen file differs: {rel}")
    if check_tree and git_tree_sha(freeze["source_commit"]) != freeze.get("source_tree_id"):
        raise ValueError("source commit tree differs from the frozen tree id")
    runtime = freeze["runtime"]
    _equal({key: runtime.get(key) for key in runtime_fixed(case)}, runtime_fixed(case), "fixed runtime budgets")
    _equal((runtime.get("kernel_id"), runtime.get("case_id")), (K.KERNEL_IDS[case], case), "kernel identity")
    runner = infra / f"kernel_gridres01_{G.GRIDS[case]['kernel_suffix']}/runner.py"
    if sha256(runner) != runtime["runner_sha256"] or runner.read_text() != K.render(freeze["source_commit"], case):
        raise ValueError("rendered worker differs from the reviewed source")
    if jload(runner.with_name("kernel-metadata.json")) != K.metadata(case) or sha256(runner.with_name("kernel-metadata.json")) != runtime["metadata_sha256"]:
        raise ValueError("kernel metadata differs")
    if freeze["pins"] != K.pins(case):
        raise ValueError("pin map differs from the current files")
    _equal([{k: r.get(k) for k in ("name", "kind", "direction", "step_mm", "sign")} for r in inventory["states"]], G.plan(), "state plan")
    if inventory.get("kernels", {}).get(case) != list(G.NAMES) or inventory.get("stage_status") != "READY" or inventory.get("blockers"):
        raise ValueError("kernel plan differs or the inventory is blocked")
    if inventory["grids"][case]["limits"] != {k: G.GRIDS[case][k] for k in ("per_state_timeout_s", "solver_wall_time_cap_s", "kernel_timeout_s")}:
        raise ValueError("registered caps differ")
    for row in inventory["states"]:
        if len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) != 2:
            raise ValueError("Fortran and C order hashes must be distinct named fields")


def _manifest(out: Path, grid: str) -> None:
    files = jload(out / "output_manifest.json")["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files map is missing or empty")
    if set(files) != {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p != out / "output_manifest.json"}:
        raise ValueError("manifest path set differs from actual output")
    if any(p.is_symlink() for p in out.rglob("*")):
        raise ValueError("symlinks are not permitted in retained kernel output")
    required = {"gridres01_index.json", "run_identity.json", "nvidia_smi.csv", "gpu_device_probe.json", "DONE"} | {f"states/{n}/{f}" for n in G.NAMES for f in (f"{grid}.forces.csv", f"{grid}.poisson.csv", f"{grid}.summary.json", "W4_JOB_DONE")}
    required |= {f"parent_reruns/{g}/{f}" for g in G.GRIDS[grid]["parent_reruns"] for f in (f"{g}.forces.csv", f"{g}.poisson.csv", f"{g}.summary.json", "W4_JOB_DONE")}
    if not required <= set(files):
        raise ValueError("manifest omits required output files")
    for relative, digest in files.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or not _is_sha(digest) or sha256(out / rel) != digest:
            raise ValueError(f"unsafe manifest path, malformed digest or hash mismatch: {relative}")


def check_parent_reruns(out: Path, case: str, freeze: dict, inventory: dict, index: dict, selected: dict) -> tuple:
    """Amendment 2 H2: the instrumented parent reruns on the retained grids.  Each force CSV must equal the retained Stage B parent CSV byte for byte (hash from the inventory, itself pinned to the Stage B
    analysis): otherwise the instrumentation is not passive (or the run is not reproducible) and the record is refused.  Returns (poisson summaries by grid, process seconds, Julia summary seconds)."""
    plan, runtime = inventory["grids"][case]["parent_reruns"], freeze["runtime"]
    entries = index.get("parent_reruns")
    if not isinstance(entries, list) or [e.get("case_id") for e in entries] != [r["case_id"] for r in plan]:
        raise ValueError("parent reruns differ from the registered plan")
    rerun_dir = out / "parent_reruns"
    if ({p.name for p in rerun_dir.iterdir() if p.is_dir()} if rerun_dir.exists() else set()) != {r["case_id"] for r in plan}:
        raise ValueError("parent rerun directories differ from the plan")
    parent, stats, process_total, summary_total = inventory["states"][0], {}, 0.0, 0.0
    for rec, entry in zip(plan, entries):
        g, directory = rec["case_id"], out / "parent_reruns" / rec["case_id"]
        csv, poisson_path, summary_path = directory / f"{g}.forces.csv", directory / f"{g}.poisson.csv", directory / f"{g}.summary.json"
        if entry.get("complete") is not True or type(entry.get("exit_code")) is not int or entry["exit_code"] != 0 or entry.get("name") != parent["name"]:
            raise ValueError("parent rerun process is incomplete")
        seconds = finite(entry.get("seconds"), "parent rerun process wall time")
        if not 0 < seconds <= runtime["per_state_timeout_s"]:
            raise ValueError("parent rerun process wall time exceeds budget")
        process_total += seconds
        digest = sha256(csv)
        if entry.get("forces_csv_sha256") != digest or entry.get("poisson_csv_sha256") != sha256(poisson_path):
            raise ValueError("parent rerun CSV differs from index")
        if digest != rec["retained_forces_csv_sha256"] or entry.get("retained_forces_csv_sha256") != digest or entry.get("byte_identical_to_retained") is not True:
            raise ValueError(f"instrumented {g} parent is not byte-identical to the retained Stage B force CSV: the instrumentation is not passive (or the run is not reproducible)")
        summary = jload(summary_path)
        for key, want in (("case_id", g), ("cells_per_reference_length", rec["cells"]), ("flow_dims", rec["flow_dims"]), ("gpu_name", "Tesla T4"), ("gpu_uuid", selected["uuid"]),
                          ("phi_fortran_sha256", parent["phi_fortran_order_sha256"]), ("phi_c_order_sha256", parent["phi_c_order_sha256"]), ("state_sha256", parent["state_sha256"]), ("julia_threads", 1)):
            _equal(summary.get(key), want, f"parent rerun summary {key}")
        if any(summary.get(key) is not True for key in ("finite_u", "finite_p", "finite_forces")):
            raise ValueError("parent rerun fields or forces are not finite")
        wall = finite(summary.get("wall_seconds"), "parent rerun Julia wall time")
        if not 0 < wall <= runtime["per_state_timeout_s"]:
            raise ValueError("parent rerun Julia wall time exceeds budget")
        summary_total += wall
        stats[g] = poisson_summary(poisson_path, csv_steps(csv))
    return stats, process_total, summary_total


def check_kernel(out: Path, case: str, freeze: dict, inventory: dict) -> dict:
    config, runtime, rows = inventory["grids"][case], freeze["runtime"], inventory["states"]
    names = [r["name"] for r in rows]
    if not (out / "DONE").is_file() or any(out.rglob("ERROR.txt")):
        raise ValueError("DONE must exist and ERROR.txt must not")
    _manifest(out, case)
    index, identity = jload(out / "gridres01_index.json"), jload(out / "run_identity.json")
    for record in (index, identity):
        for key, want in (("kernel", case), ("kernel_id", runtime["kernel_id"]), ("case_id", case)):
            if record.get(key) != want:
                raise ValueError(f"output {key} identity differs")
    if index.get("status") != "COMPLETE" or identity.get("source_commit") != freeze["source_commit"] or identity.get("failure_stage") is not None:
        raise ValueError("terminal/source/failure-stage identity differs")
    if identity.get("runner_sha256") != runtime["runner_sha256"] or identity.get("pins") != freeze["pins"] or identity.get("verified") != freeze["pins"]:
        raise ValueError("runner identity or verified pin map differs")
    selected = select_worker_gpu((out / "nvidia_smi.csv").read_text())
    _equal(identity.get("selected_gpu"), selected, "physical GPU selection")
    for key in ("cuda_device_order", "cuda_visible_devices"):
        if identity.get(key) != runtime[key]:
            raise ValueError("run identity CUDA environment differs")
    _equal(jload(out / "gpu_device_probe.json"), {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [selected["uuid"]],
                                                  "default_device_uuid": selected["uuid"], "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}, "CUDA identity")
    entries = index.get("states")
    if not isinstance(entries, list) or [r.get("name") for r in entries] != names:
        raise ValueError("completed entries differ from the exact five-state plan")
    if {p.name for p in (out / "states").iterdir() if p.is_dir()} != set(names):
        raise ValueError("state directories differ from the exact plan")
    states, process_total, summary_total = {}, 0.0, 0.0
    for row, entry in zip(rows, entries):
        for key in ("name", "kind", "direction", "step_mm", "sign"):
            _equal(entry.get(key), row[key], f"index state {key}")
        if entry.get("complete") is not True or type(entry.get("exit_code")) is not int or entry["exit_code"] != 0:
            raise ValueError("state process is incomplete")
        process_seconds = finite(entry.get("seconds"), "state process wall time")
        if not 0 < process_seconds <= runtime["per_state_timeout_s"]:
            raise ValueError("state process wall time exceeds budget")
        process_total += process_seconds
        directory = out / "states" / row["name"]
        csv, summary_path = directory / f"{case}.forces.csv", directory / f"{case}.summary.json"
        if entry.get("forces_csv_sha256") != sha256(csv):
            raise ValueError("state force CSV differs from index")
        poisson_path = directory / f"{case}.poisson.csv"
        if entry.get("poisson_csv_sha256") != sha256(poisson_path):
            raise ValueError("state Poisson CSV differs from index")
        poisson = poisson_summary(poisson_path, csv_steps(csv))
        summary, job_env = jload(summary_path), inventory["job_env_common"]
        for key, want in (("canonical_sdf_origin_m", [float(v) for v in job_env["W4_CANONICAL_ORIGIN_M"].split(",")]), ("canonical_design_spacing_m", float(job_env["W4_CANONICAL_DESIGN_SPACING_M"])),
                          ("canonical_state_label", job_env["W4_CANONICAL_STATE_LABEL"]), ("canonical_design_point_shape", [int(v) for v in job_env["W4_POINT_SHAPE"].split(",")]),
                          ("canonical_design_cell_shape", [int(v) for v in job_env["W4_CELL_SHAPE"].split(",")]), ("source_surface_sha256", job_env["W4_SOURCE_SURFACE_SHA256"]),
                          ("device_roundtrip_sha256", row["phi_fortran_order_sha256"]), ("cells_per_reference_length", G.GRIDS[case]["cells"])):
            _equal(summary.get(key), want, f"summary {key}")
        for key, want in (("case_id", case), ("gpu_name", "Tesla T4"), ("gpu_uuid", selected["uuid"]), ("phi_fortran_sha256", row["phi_fortran_order_sha256"]),
                          ("phi_c_order_sha256", row["phi_c_order_sha256"]), ("state_sha256", row["state_sha256"]), ("state_npz_sha256", row["npz_sha256"]),
                          ("force_integration_body", config["measurement"]["candidate_operator"]), ("force_projection_semantics", "drag=+Fx; downforce=-Fz")):
            if summary.get(key) != want:
                raise ValueError(f"state summary {key} differs")
        case_cfg = config["measurement"]["case"]
        _equal(summary.get("flow_dims"), case_cfg["flow_dims"], "summary grid dimensions")
        for key in ("flow_spacing_m", "solver_length", "solver_time_unit_s", "solver_viscosity", "reynolds", "density_kg_m3", "dynamic_viscosity_pa_s", "reference_length_m", "reference_area_m2"):
            if not math.isclose(finite(summary.get(key), key), finite(case_cfg[key], key), rel_tol=1e-12, abs_tol=1e-15):
                raise ValueError(f"summary {key} differs from grid-specific measurement")
        _equal(summary.get("freestream_mps"), case_cfg["freestream_mps"], "summary freestream")
        if any(summary.get(key) is not True for key in ("finite_u", "finite_p", "finite_forces")):
            raise ValueError("state fields or forces are not finite")
        if type(summary.get("julia_threads")) is not int or summary["julia_threads"] != 1:
            raise ValueError("summary Julia thread count differs")
        if finite(summary.get("t_end_reached"), "horizon") < 120 or finite(summary.get("burn_in_t_u_l"), "burn in") != 80:
            raise ValueError("summary time window/horizon differs")
        if abs(finite(summary.get("phi_margin_m"), "SDF margin") - row["zero_level_margin_m"]) > row["margin_tolerance_m"] or finite(summary.get("phi_margin_gate_m"), "margin gate") != inventory["margin_gate_m"]:
            raise ValueError("summary SDF margin differs")
        wall = finite(summary.get("wall_seconds"), "Julia wall time")
        if not 0 < wall <= runtime["per_state_timeout_s"]:
            raise ValueError("Julia summary wall time exceeds budget")
        summary_total += wall
        host = recompute_force_n(csv, {"measurement": config["measurement"]})
        for q in Q:
            if _rel_error(host[f"{q}_n"], finite(summary.get(f"{q}_time_weighted_n"), f"summary {q}")) > SUMMARY_REL:
                raise ValueError("host recomputation differs from Julia force summary")
        states[row["name"]] = {f"{q}_n": host[f"{q}_n"] for q in Q}
        states[row["name"]].update({"poisson": poisson, "forces_csv_sha256": sha256(csv), "summary_sha256": sha256(summary_path), "solver_process_wall_seconds": process_seconds, "julia_summary_wall_seconds": wall,
                                    "peak_vram_bytes": summary.get("peak_vram_bytes")})
    _, rerun_process, rerun_summary = check_parent_reruns(out, case, freeze, inventory, index, selected)
    process_total, summary_total = process_total + rerun_process, summary_total + rerun_summary
    if finite(index.get("solver_process_wall_seconds_total"), "total process time") != process_total or process_total > runtime["solver_wall_time_cap_s"] or summary_total > runtime["solver_wall_time_cap_s"]:
        raise ValueError("aggregate wall-time budget or recorded process sum differs")
    return states


def rerun_poisson(out: Path, case: str, freeze: dict, inventory: dict) -> dict:
    selected = select_worker_gpu((out / "nvidia_smi.csv").read_text())
    return check_parent_reruns(out, case, freeze, inventory, jload(out / "gridres01_index.json"), selected)[0]


def analyze(case: str, kernel_dir: Path, freeze: Any, inventory: Any | None = None) -> dict:
    base = {"kind": "gridres01_analysis", "fine_grid": case, "verdict": "INCOMPLETE", "integrity": {"pass": False, "failures": []}, "no_gradient_claim": True, "not_grid_converged": True,
            "record_level_status_only": True}
    try:
        inventory = inventory if inventory is not None else jload(ROOT / EVIDENCE_REL / "inventory.json")
        validate_registration(freeze, inventory, case)
        fine = check_kernel(Path(kernel_dir), case, freeze, inventory)
        poisson = {**rerun_poisson(Path(kernel_dir), case, freeze, inventory), case: {n: v["poisson"] for n, v in fine.items()}}
        rep = report({**retained_tables(), case: fine}, case)
        base.update(rep)
        base["integrity"] = {"pass": True, "failures": []}   # H3: a residual-gate INCOMPLETE is a scientific outcome (verdict + verdict_reason), written like any other; only integrity failures are not
        base["poisson"] = {"per_run": poisson, **poisson_report(poisson, case)}
        base.update({"state_forces_n": {case: {n: {k: v for k, v in rec.items() if k != "poisson"} for n, rec in fine.items()}}, "frozen_parameters": FROZEN_PARAMETERS, "qualification_flags": {k: False for k in FLAGS},
                     "provenance": {"source_commit": freeze["source_commit"], "source_tree_id": freeze["source_tree_id"], "inventory_sha256": freeze["inventory_sha256"], "analyzer_sha256": sha256(Path(__file__)),
                                    "kernel_manifest_sha256": sha256(Path(kernel_dir) / "output_manifest.json")},
                     "disclosures": ("Non-blind: the flow_24/flow_32 values and the quadratic structure were known before the run.  The direction was selected as the max-min of the flow_24/flow_32 predictions: a selected line, not a random draw.  "
                                     "Lattice commensurability confound: the design lattice (0.025 m) equals the flow_32 spacing, flow_24 is coarser, flow_40/48 finer; resolution and lattice alignment change together, "
                                     "and any convergence is that of this interpolated-lattice body only.  The 3e-5 N floor is nominal, the 1e-5 N guard band is the scale of the fit residuals, not a noise measurement.  "
                                     "Multigrid-depth confound: WaterLily 1.8.0 builds 4, 6, 4 and 5 multigrid levels on flow_24, flow_32, flow_40 and flow_48 and caps the pressure solve at 32 iterations (tol 1e-4), so part of any flow_24/flow_32 "
                                     "difference may be pressure-solver convergence rather than resolution; the Poisson statistics above are descriptive, reported not gating.  "
                                     "The verdict uses the fit including the -1.25 mm reverse state (a report-only probe for the gates); the forward-only G_max is reported without classification; with 3 dof per fit one outlier is partly absorbed, "
                                     "so read G_max together with the acceptance emulation.  Not claimed: grid independence, physical or Stage V downforce, a gradient, optimizer behaviour.  "
                                     "No GRIDRES-01 result alone supports a GRID-01 amendment.")})
    except Exception as exc:  # noqa: BLE001 -- every untrusted-input failure is fail-closed
        base["integrity"] = {"pass": False, "failures": [f"{type(exc).__name__}: {exc}"]}
        base["verdict"] = "INCOMPLETE"
        base["verdict_reason"] = "integrity failure: no analysis is written"
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", required=True, choices=sorted(G.GRIDS))
    parser.add_argument("--kernel-dir", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", type=Path)
    args = parser.parse_args()
    if args.write is not None and args.write.exists():
        raise SystemExit("refusing to overwrite an existing GRIDRES-01 analysis")
    try:
        freeze_sha = sha256(args.freeze)
        if args.freeze.with_name(args.freeze.name + ".sha256").read_text().strip() != freeze_sha:
            raise ValueError("freeze SHA-256 sidecar mismatch")
        freeze = jload(args.freeze)
    except Exception as exc:  # noqa: BLE001
        print(f"invalid freeze: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    result = analyze(args.grid, args.kernel_dir, freeze)
    if args.check or result["integrity"]["pass"] is not True:
        print(json.dumps({"integrity": result["integrity"], "verdict": result["verdict"], "verdict_reason": result.get("verdict_reason")}, indent=2, sort_keys=True, allow_nan=False))
        if result["integrity"]["pass"] is not True:
            raise SystemExit(3)   # integrity failures never write an analysis
        return
    result["provenance"]["freeze_sha256"] = freeze_sha
    data = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(result["verdict"], result["verdict_reason"], hashlib.sha256(data.encode()).hexdigest())


if __name__ == "__main__":
    main()
