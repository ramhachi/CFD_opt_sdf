#!/usr/bin/env python3
"""Fail-closed GRID-02 analysis (#56): five Kaggle kernel outputs -> response slope/curvature per grid and placement -> pre-registered alignment/fine classification.

Copy-adapted from analyze_lowdim03 / analyze_opt01b (never edited).  CLI: ONE `--kernel-root` directory holding the five output directories `grid02_<k>` (k in f16, f48a, f48b, s24, s32),
`--freeze`, and exactly one of `--check` (integrity + verdict only, writes nothing) / `--write PATH` (writes once, never overwrites, refuses on any integrity or computation failure).
Verdicts: GRID02_RECORDED (integrity passed; the alignment/fine classifications and the STABLE flag are fields) or GRID02_INCOMPLETE (nothing is concluded, nothing is written).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_sdf import grid02_contract as C  # noqa: E402
from cfd_sdf.lowdim03_contract import QUALIFICATION_FLAGS  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402
from grid01_gpu import select_worker_gpu  # noqa: E402
from analyze_grid01 import sha256, _source_commit_failures  # noqa: E402
import build_grid02_inputs as B  # noqa: E402
import build_grid02_kernel as K  # noqa: E402

EVIDENCE_REL = "docs/evidence/grid02_trend_2026_10_16"
OPT01B_REL = "docs/evidence/opt01b_stage_b_2026_10_15"
FORMAL_REL = "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
PLAN_REL = "docs/grid02_plan_2026_10_15.md"
FREEZE_KIND = "grid02_trend_prerun_freeze"
PARENT_COMMIT = "ced45f1c72546ad1bd32b2ccfb9d6fa8795f4886"  # the approved OPT-01 v1 integration commit the source must descend from
SUMMARY_REL = 1e-9
CELL_LABELS = ("16n", "24n", "24s", "32n", "32s", "48n")
FLOW_ORIGIN_M, BOX_MAX_M = [-2.5, -1.2, -0.9], [2.5, 1.2, 0.9]
HINDCAST_BAND_N = [0.38, 0.40]
RULES = {"resolution": "max(3e-5 N, largest observed parent-pair |difference| of downforce and drag on the grid); the floor is nominal flow_24, unmeasured elsewhere", "resolution_floor_n": C.RESOLUTION_FLOOR_N,
         "reference": "dL, dD against the SAME kernel's parent (flow_48: +1.25 mm and reverse 1.25 mm against the parent repeat of f48b)", "fit": "dL = b s + a s^2, s in mm, least squares on the forward points (no intercept); intercept check on forward points plus the parent point; reverse points are a check only",
         "alignment": {"G": "b_32n - b_24n", "m24": "(b_24s - b_24n)/G", "m32": "(b_32n - b_32s)/G", "dominant": "m24 >= 0.5 and m32 >= 0.5", "negligible": "|m24| <= 0.2 and |m32| <= 0.2", "else": "partial_or_mixed"},
         "fine": {"r": "(b_48n - b_24n)/G", "continues_to_flow32": "r >= 0.5", "reverses_toward_flow24": "r <= 0.2", "else": "intermediate", "stable_32_to_48": "|b_48n - b_32n| <= 0.3 |b_32n|"},
         "both_grid_rule": "descriptive only: downforce gain > 3e-5 N and drag change <= 0 on every listed grid", "hindcast_band_flow_48_parent_downforce_n": HINDCAST_BAND_N, "verdicts": ["GRID02_RECORDED", "GRID02_INCOMPLETE"],
         "decision_map": C.DECISIONS, "decision_map_note": C.DECISION_MAP_NOTE,
         "descriptive_robustness": "never changes the verdict: per cell b_c = (dL(+1.25 mm) - dL(-1.25 mm))/2.5, b with intercept, leave-one-out b, b_48n with all forward points against the f48a parent, and whether the alignment/fine/stable results would change if b_c / b_with_intercept / that b_48n replaced b",
         "shift_integrity": "the shifted flow_24 and flow_32 parents must differ from the native parents in downforce or drag, else GRID02_INCOMPLETE (shift ineffective)",
         "peak": "for a < 0 and b > 0: peak step b/(2|a|), attainable gain b^2/(4|a|), zero crossing b/|a|, peak within tested range iff b/(2|a|) <= 1.25 mm, in-range maximum at min(peak step, 1.25 mm); beyond the range it is an extrapolation"}
KNOWN_BEFORE_RUN = ("OPT-01 v1 Stage B, GRID-01, the W4 history and the retained quadratic refit are visible. Hindcast, not a precise prediction: with baseline downforce 0.2545 / 0.3316 / 0.3613 N at n = 16 / 24 / 32 "
                    "and 1/n or 1/n^2 scaling of the changes, the flow_48 parent downforce is expected near 0.38-0.40 N. No prediction is registered for b_48 or a_48. FD-07 (a lattice-phase shift changed the flow_24 short-window "
                    "baseline by +11.9% drag, +7.2% downforce, a re-sampling not a pure translation) is weak prior support that placement matters. The 3e-5 N floor is unmeasured on flow_16/32/48. "
                    "G = b_32n - b_24n = 3.95e-4 N/mm is already known from the retained OPT-01 Stage B data (b_24n = 9.4e-5, b_32n = 4.9e-4, intercept-free fits); only b_24s, b_32s and b_48n are new. "
                    "The absolute thresholds are |db| >= 1.98e-4 N/mm (0.5 G) and |db| <= 7.9e-5 N/mm (0.2 G); with these retained b values STABLE_32_TO_48 implies r in [0.63, 1.38], i.e. FINE_CONTINUES_TO_FLOW32.")
PROHIBITIONS = ["no grid-convergence/GCI claim", "no true-grid or physical downforce/drag claim", "no gradient, optimizer or second-iteration claim", "no amendment of any threshold or rule after the run, no rule change of OPT-01",
                "no automatic repair or resubmission after an integrity failure", "no claim that the shift control is a full alignment control (z unshifted)"]
INTERPRETATION = {
    "common": ("One parent (OPT-01 v1, generation 1), one direction (the Stage B robust direction), steps <= 1.25 mm, one design lattice, Re 80, Float32 T4: the slope b, curvature a, zero crossing and attainable gain of the downforce response "
               "per grid and placement are recorded; the classifications are fields of that record. Not grid convergence or GCI, not a true grid, not physical downforce or drag, not a gradient, not an optimizer or second-iteration qualification; "
               "OPT-01 is not re-opened and its dual-grid rule is unchanged; all qualification flags are false, shape_update_allowed is false, delta is unset. The shift control is PARTIAL: the body moves (h/2, h/2, 0) against the flow grid and z is unshifted, "
               "so z-plane alignment is only partly inverted. The 3e-5 N floor is a nominal flow_24 value, unmeasured on the other grids, and a byte-identical parent pair measures reproducibility, not noise; the flow_24/flow_32 native pair difference is taken as 0 "
               "(the OPT-01 Stage B parents were byte-identical to the retained references), and the shifted flow_24/flow_32 kernels have no pair, so their resolution is the floor."),
    "GRID02_ALIGNMENT_DOMINANT": ("Alignment dominant: under the shift the flow_24 slope moves by at least G/2 toward the native flow_32 slope and the flow_32 slope by at least G/2 toward the native flow_24 slope, so the slopes are sensitive to the (h/2, h/2, 0) shift of this partial control. "
                                  "No lattice-phase mapping is assumed (shifted flow_24 sits at phases 1/2, 5/6, 1/6 in x and y, shifted flow_32 becomes node-aligned in x and y); this is not an identification of the placement as the cause."),
    "GRID02_ALIGNMENT_NEGLIGIBLE": "Alignment negligible: the placement shift moves both slopes by at most a fifth of the gap, so the disagreement is not explained by the (h/2, h/2, 0) shift of this partial control.",
    "GRID02_ALIGNMENT_PARTIAL_OR_MIXED": "Alignment partial or mixed: the shift moves the slopes by an intermediate amount or in different directions; the control neither isolates nor excludes placement.",
    "FINE_CONTINUES_TO_FLOW32": "flow_48 continues the 24 -> 32 change in slope (r >= 0.5).",
    "FINE_REVERSES_TOWARD_FLOW24": "flow_48 reverses toward the flow_24 slope (r <= 0.2).",
    "FINE_INTERMEDIATE": "flow_48 lies between the continuation and the reversal (0.2 < r < 0.5).",
    "stable": "STABLE_32_TO_48 is true: the slope changes by at most 30% from flow_32 to flow_48.", "unstable": "STABLE_32_TO_48 is false: the slope changes by more than 30% from flow_32 to flow_48 (still growing or turning back; the map does not distinguish).",
}


def jload(path: Path) -> Any:
    def reject(value):
        raise ValueError(f"nonfinite JSON constant {value}")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def _sha(v: Any) -> bool:
    return isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v) is not None


def _path(relative: Any) -> Path:
    if not isinstance(relative, str):
        raise ValueError("repository path is not a string")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel == Path("."):
        raise ValueError(f"unsafe repository path: {relative!r}")
    path = ROOT / rel
    if not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"repository path escapes checkout: {relative!r}")
    return path


def _equal(actual: Any, expected: Any, label: str) -> None:
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):  # keeps the bool-versus-number distinction
        raise ValueError(f"{label} differs from the fixed declaration")


def _rel(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), 1e-300)


def required_file_paths(inventory: dict) -> set[str]:
    """Regular source/input closure bound by the freeze (generated runners and metadata are bound separately, by re-rendering)."""
    paths = {f"scripts/{n}.py" for n in ("analyze_grid02", "freeze_grid02", "build_grid02_inputs", "build_grid02_kernel", "grid02_runner_template", "step01_states", "grid01_gpu", "fd08_v2_campaign_io",
                                         "build_grid01_inputs", "analyze_grid01", "analyze_lowdim02a", "build_grid01_kernel", "build_lowdim01_inputs", "lowdim01_states")}
    paths |= {"scripts/waterlily_grid02_job.jl", "scripts/grid02_case.jl", FORMAL_REL, PLAN_REL, "julia/CFDSDFWaterLilyT4/Project.toml", "julia/CFDSDFWaterLilyT4/Manifest.toml",
              *(f"tests/test_grid02_{n}.py" for n in ("analyzer", "prereg", "contract", "inputs_and_runner", "job")),
              *(f"{EVIDENCE_REL}/{n}" for n in ("inventory.json", "inventory.json.sha256", "prerun_note.md", "identity_free_check.json", "identity_free_check.json.sha256"))}
    for directory, pattern in (("src/cfd_sdf", "*.py"), ("julia/CFDSDFWaterLily/src", "*")):
        paths |= {str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob(pattern) if p.is_file() and "__pycache__" not in p.parts}
    paths |= {inventory["source"]["opt01b_inventory_path"], inventory["source"]["opt01b_analysis_path"], inventory["native_reference"]["analysis_path"], inventory["parent"]["raw_path"], inventory["proposal"]["file"]}
    paths |= {cfg["job"] for cfg in inventory["kernel_config"].values()}
    return paths


def expected_runtime(kernel: str, cfg: dict, runner_sha256: str, metadata_sha256: str) -> dict:
    """The frozen per-kernel runtime declaration (shared with the freeze script)."""
    return {"kernel_id": K.KERNEL_IDS[kernel], "case_id": cfg["case_id"], "job": cfg["job"], "placement": cfg["placement"], "canonical_origin_m": cfg["canonical_origin_m"], "W4_CANONICAL_ORIGIN_M": cfg["W4_CANONICAL_ORIGIN_M"],
            "GRID02_CASE": cfg["GRID02_CASE"], "runner_sha256": runner_sha256, "metadata_sha256": metadata_sha256, "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "kernel_timeout_s": cfg["kernel_timeout_s"],
            "timeout_s": cfg["kernel_timeout_s"], "per_state_timeout_s": cfg["per_state_timeout_s"], "solver_wall_time_cap_s": cfg["solver_wall_time_cap_s"], "instantiate_timeout_s": cfg["instantiate_timeout_s"],
            "gpu_probe_timeout_s": cfg["gpu_probe_timeout_s"], "reserve_s": cfg["reserve_s"], "julia_threads": 1, "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0", "selected_gpu_physical_index": 0, "used_gpu_count": 1}


def _check_config(kernel: str, cfg: dict, formal: dict) -> None:
    spec = C.KERNELS[kernel]
    case = spec["case"]
    want = {"kernel_id": K.KERNEL_IDS[kernel], "case_id": case, "job": spec["job"], "placement": spec["placement"], "canonical_origin_m": list(C.PLACEMENTS[spec["placement"]]), "W4_CANONICAL_ORIGIN_M": C.origin_env(spec["placement"]),
            "GRID02_CASE": spec["grid02_case"], "per_state_timeout_s": spec["per_state_timeout_s"], "solver_wall_time_cap_s": C.aggregate_cap_s(kernel), "kernel_timeout_s": spec["kernel_timeout_s"],
            "instantiate_timeout_s": B.INSTANTIATE_TIMEOUT_S, "gpu_probe_timeout_s": B.GPU_PROBE_TIMEOUT_S, "reserve_s": B.RESERVE_S, "force_scale_n_per_solver_force": C.force_scale_n(case)}
    _equal({k: cfg.get(k) for k in want}, want, f"{kernel} kernel configuration")
    m, override = cfg["measurement"], C.case_dict(case)
    _equal({k: m["case"].get(k) for k in override}, override, f"{kernel} grid case")
    for key, val in (("case_id", case), ("force_unit", "N"), ("time_window_t_u_l", [80.0, 120.0]), ("candidate_operator", formal["candidate_operator"]), ("per_state_timeout_s", spec["per_state_timeout_s"]),
                     ("solver_wall_time_cap_s", C.aggregate_cap_s(kernel)), ("kernel_execution_allowance_s", spec["kernel_timeout_s"])):
        _equal(m.get(key), val, f"{kernel} measurement {key}")
    _equal({k: v for k, v in m["case"].items() if k not in override and k in formal["case"]}, {k: v for k, v in formal["case"].items() if k not in override}, f"{kernel} shared measurement case")


def validate_registration(freeze: Any, inventory: Any) -> None:
    if not isinstance(freeze, dict) or not isinstance(inventory, dict):
        raise ValueError("freeze and inventory must be objects")
    if freeze.get("kind") != FREEZE_KIND or freeze.get("parent_integration_commit") != PARENT_COMMIT:
        raise ValueError("freeze kind or approved integration parent differs")
    _equal(freeze.get("rules"), RULES, "frozen rules and thresholds")
    _equal(freeze.get("qualification_flags"), {k: False for k in QUALIFICATION_FLAGS}, "frozen qualification flags")
    _equal(freeze.get("known_before_run"), KNOWN_BEFORE_RUN, "known-before-run disclosure")
    _equal(freeze.get("prohibitions"), PROHIBITIONS, "frozen prohibitions")
    if freeze.get("selected_delta") is not None or freeze.get("reinitialization") != "none" or freeze.get("shape_update_allowed") is not False:
        raise ValueError("freeze must not select delta, authorize reinitialization or a shape update")
    frozen_at = datetime.fromisoformat(freeze["frozen_utc"].replace("Z", "+00:00"))
    if frozen_at.tzinfo is None or frozen_at > datetime.now(timezone.utc):
        raise ValueError("freeze time must be aware and not in the future")
    from freeze_grid02 import require_identity
    _equal(freeze.get("identity_free_check"), jload(_path(f"{EVIDENCE_REL}/identity_free_check.json")), "provider identity evidence")
    require_identity(freeze["identity_free_check"], as_of=frozen_at)
    inv_path = _path(f"{EVIDENCE_REL}/inventory.json")
    inv_sha = sha256(inv_path)
    if inventory.get("kind") != "grid02_inventory" or inventory.get("stage_status") != "READY" or inventory.get("blockers"):
        raise ValueError("inventory is not a READY GRID-02 inventory")
    if freeze.get("inventory_sha256") != inv_sha or jload(inv_path) != inventory or _path(f"{EVIDENCE_REL}/inventory.json.sha256").read_text().strip() != inv_sha:
        raise ValueError("inventory does not match its frozen bytes or sidecar")
    hashes = freeze.get("file_hashes")
    if not isinstance(hashes, dict) or not required_file_paths(inventory) <= set(hashes):
        raise ValueError("frozen file/source closure is incomplete")
    for rel, digest in hashes.items():
        path = _path(rel)
        if not _sha(digest) or not path.is_file() or sha256(path) != digest:
            raise ValueError(f"frozen file hash mismatch: {rel}")
    failures = _source_commit_failures(freeze.get("source_commit", ""), hashes, root=ROOT, file_paths={p: p for p in hashes}, exceptions=set(), parent_commit=PARENT_COMMIT)
    if failures:
        raise ValueError("source commit binding failed: " + "; ".join(failures))
    rows = inventory["states"]
    _equal([r["name"] for r in rows], list(C.SEVEN) + [C.REPEAT], "inventory state order")
    _equal(inventory["kernels"], {k: list(v["states"]) for k, v in C.KERNELS.items()}, "kernel plans")
    for r in rows:
        if any(not _sha(r.get(k)) for k in B.IDENTITY_KEYS if k.endswith("_sha256")) or type(r.get("changed_node_count")) is not int:
            raise ValueError(f"state identity is malformed: {r['name']}")
    if any(rows[7][k] != rows[0][k] for k in B.IDENTITY_KEYS) or len({r["phi_fortran_order_sha256"] for r in rows}) != 7:
        raise ValueError("the parent repeat is not the parent identity or the seven geometries are not distinct")
    for r in rows[1:7]:
        if r["direction"] != "robust_opt01a" or r["sign"] not in (1, -1) or not r["step_mm"] > 0 or r["changed_node_count"] == 0:
            raise ValueError(f"unregistered perturbation state: {r['name']}")
    src = inventory["source"]
    if (src["opt01b_inventory_sha256"], src["opt01b_analysis_sha256"], inventory["native_reference"]["analysis_sha256"]) != (B.OPT01B_INVENTORY_SHA, B.OPT01B_ANALYSIS_SHA, B.OPT01B_ANALYSIS_SHA):
        raise ValueError("the inventory does not bind the pinned OPT-01 Stage B inventory/analysis")
    if sha256(_path(src["opt01b_inventory_path"])) != B.OPT01B_INVENTORY_SHA or sha256(_path(src["opt01b_analysis_path"])) != B.OPT01B_ANALYSIS_SHA:
        raise ValueError("OPT-01 Stage B inventory/analysis bytes differ from the pinned immutable result")
    if sha256(_path(inventory["parent"]["raw_path"])) != inventory["parent"]["phi_fortran_order_sha256"] or sha256(_path(inventory["proposal"]["file"])) != inventory["proposal"]["sha256_fortran_raw"]:
        raise ValueError("the parent or the direction raw bytes differ from the inventory")
    if inventory["states"][:7] != jload(_path(src["opt01b_inventory_path"]))["states"]:
        raise ValueError("inventory states differ from the OPT-01 Stage B inventory rows")
    formal = jload(_path(FORMAL_REL))["measurement"]
    if set(freeze.get("runtime", {})) != set(C.KERNELS) or set(freeze.get("pins", {})) != set(C.KERNELS) or set(inventory["kernel_config"]) != set(C.KERNELS):
        raise ValueError("all five kernels' configuration, runtime and pins are required")
    for kernel in C.KERNELS:
        cfg, runtime = inventory["kernel_config"][kernel], freeze["runtime"][kernel]
        _check_config(kernel, cfg, formal)
        runner = _path(f"infra/kaggle/kernel_grid02_{kernel}/runner.py")
        meta = runner.with_name("kernel-metadata.json")
        if runner.read_text() != K.render(freeze["source_commit"], kernel) or jload(meta) != K.metadata(kernel):
            raise ValueError(f"rendered worker or metadata does not reproduce from the reviewed source: {kernel}")
        _equal(runtime, expected_runtime(kernel, cfg, sha256(runner), sha256(meta)), f"{kernel} frozen runtime")
        _equal(freeze["pins"][kernel], K.pins(kernel), f"{kernel} complete runtime pin map")
        for rel, digest in freeze["pins"][kernel].items():
            if not _sha(digest) or sha256(_path(rel)) != digest:
                raise ValueError(f"runtime pin hash mismatch: {rel}")


def _manifest(out: Path, names: list[str], case: str) -> None:
    if out.is_symlink() or any(p.is_symlink() for p in out.rglob("*")):
        raise ValueError("symlinks are not permitted in retained kernel output")
    files = jload(out / "output_manifest.json")["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files map is missing or empty")
    if set(files) != {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p != out / "output_manifest.json"}:
        raise ValueError("manifest path set differs from actual output")
    required = {"grid02_index.json", "run_identity.json", "nvidia_smi.csv", "gpu_device_probe.json", "gpu_device_probe.log", "DONE"}
    required |= {f"states/{n}/{f}" for n in names for f in (f"{case}.forces.csv", f"{case}.summary.json", "W4_JOB_DONE")}
    if not required <= set(files):
        raise ValueError("manifest omits required output files")
    for relative, digest in files.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or not _sha(digest):
            raise ValueError("unsafe manifest path or malformed digest")
        if sha256(out / rel) != digest:
            raise ValueError(f"manifest hash mismatch: {relative}")


def check_kernel(out: Path, kernel: str, freeze: dict, inventory: dict) -> dict:
    """Integrity of one kernel output; returns the host-recomputed forces by state."""
    out = Path(out)
    cfg, runtime = inventory["kernel_config"][kernel], freeze["runtime"][kernel]
    case, names = cfg["case_id"], inventory["kernels"][kernel]
    rows = {r["name"]: r for r in inventory["states"]}
    if not out.is_dir() or not (out / "DONE").is_file() or any(out.rglob("ERROR.txt")):
        raise ValueError("DONE must exist and ERROR.txt must not")
    _manifest(out, names, case)
    index, identity = jload(out / "grid02_index.json"), jload(out / "run_identity.json")
    for record in (index, identity):
        for key, want in (("kernel", kernel), ("kernel_id", runtime["kernel_id"]), ("case_id", case)):
            if record.get(key) != want:
                raise ValueError(f"output {key} identity differs")
    if index.get("status") != "COMPLETE" or identity.get("source_commit") != freeze["source_commit"] or identity.get("failure_stage") is not None:
        raise ValueError("terminal/source/failure-stage identity differs")
    if identity.get("runner_sha256") != runtime["runner_sha256"] or identity.get("pins") != freeze["pins"][kernel] or identity.get("verified") != freeze["pins"][kernel]:
        raise ValueError("runner identity or verified pin map differs")
    _equal(identity.get("config"), {k: cfg[k] for k in K.RUNTIME_KEYS}, "run identity kernel configuration")
    _equal(identity.get("expected_names"), names, "run identity state plan")
    selected = select_worker_gpu((out / "nvidia_smi.csv").read_text())
    _equal(identity.get("selected_gpu"), selected, "physical GPU selection")
    for key, want in (("cuda_device_order", "PCI_BUS_ID"), ("cuda_visible_devices", "0")):
        if identity.get(key) != want:
            raise ValueError("run identity CUDA environment differs")
    _equal(jload(out / "gpu_device_probe.json"), {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [selected["uuid"]], "default_device_uuid": selected["uuid"],
                                                  "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}, "independently observed CUDA singleton/default identity")
    entries = index.get("states")
    if not isinstance(entries, list) or [e.get("name") for e in entries] != names:
        raise ValueError("completed entries differ from the exact registered state order")
    if {p.name for p in (out / "states").iterdir() if p.is_dir()} != set(names):
        raise ValueError("state directories differ from the exact plan")
    first_kind = rows[names[0]]["kind"]
    if first_kind not in ("parent", "parent_repeat") or any(rows[n]["kind"] == "parent" for n in names[1:]):
        raise ValueError("the parent (or the parent repeat) must come first and the parent only once")
    states, process_total, summary_total = {}, 0.0, 0.0
    job_env, m = inventory["job_env_common"], cfg["measurement"]
    for name, entry in zip(names, entries):
        row = rows[name]
        for key in ("name", "kind", "direction", "step_mm", "sign"):
            _equal(entry.get(key), row[key], f"index state {key}")
        if entry.get("complete") is not True or type(entry.get("exit_code")) is not int or entry["exit_code"] != 0:
            raise ValueError("state process is incomplete")
        seconds = C.finite(entry.get("seconds"), "state process wall time")
        if not 0 < seconds <= cfg["per_state_timeout_s"]:
            raise ValueError("state process wall time exceeds budget")
        process_total += seconds
        directory = out / "states" / name
        csv, summary_path = directory / f"{case}.forces.csv", directory / f"{case}.summary.json"
        if entry.get("forces_csv_sha256") != sha256(csv):
            raise ValueError("state force CSV differs from index")
        summary = jload(summary_path)
        for key, want in (("canonical_sdf_origin_m", cfg["canonical_origin_m"]), ("canonical_design_spacing_m", float(job_env["W4_CANONICAL_DESIGN_SPACING_M"])), ("canonical_state_label", job_env["W4_CANONICAL_STATE_LABEL"]),
                          ("canonical_design_point_shape", [int(v) for v in job_env["W4_POINT_SHAPE"].split(",")]), ("canonical_design_cell_shape", [int(v) for v in job_env["W4_CELL_SHAPE"].split(",")]),
                          ("source_surface_sha256", job_env["W4_SOURCE_SURFACE_SHA256"]), ("device_roundtrip_sha256", row["phi_fortran_order_sha256"]),  # DeviceGridSDF hashes the Fortran-order bytes
                          ("flow_origin_m", FLOW_ORIGIN_M), ("physical_box_max_m", BOX_MAX_M), ("cells_per_reference_length", C.CELLS[case])):
            _equal(summary.get(key), want, f"summary {key}")
        for key, want in (("case_id", case), ("gpu_name", "Tesla T4"), ("gpu_uuid", selected["uuid"]), ("phi_fortran_sha256", row["phi_fortran_order_sha256"]), ("phi_c_order_sha256", row["phi_c_order_sha256"]),
                          ("state_sha256", row["state_sha256"]), ("state_npz_sha256", row["npz_sha256"]), ("force_integration_body", m["candidate_operator"]), ("force_projection_semantics", "drag=+Fx; downforce=-Fz")):
            if summary.get(key) != want:
                raise ValueError(f"state summary {key} differs")
        grid_case = m["case"]
        _equal(summary.get("flow_dims"), grid_case["flow_dims"], "summary grid dimensions")
        for key in ("flow_spacing_m", "solver_length", "solver_time_unit_s", "solver_viscosity", "reynolds", "density_kg_m3", "dynamic_viscosity_pa_s", "reference_length_m", "reference_area_m2"):
            if not math.isclose(C.finite(summary.get(key), key), C.finite(grid_case[key], key), rel_tol=1e-12, abs_tol=1e-15):
                raise ValueError(f"summary {key} differs from grid-specific measurement")
        _equal(summary.get("freestream_mps"), grid_case["freestream_mps"], "summary freestream")
        if any(summary.get(key) is not True for key in ("finite_u", "finite_p", "finite_forces")):
            raise ValueError("state fields or forces are not finite")
        if type(summary.get("julia_threads")) is not int or summary["julia_threads"] != 1:
            raise ValueError("summary Julia thread count differs")
        if C.finite(summary.get("t_end_reached"), "horizon") < 120 or C.finite(summary.get("burn_in_t_u_l"), "burn in") != 80:
            raise ValueError("summary time window/horizon differs")
        if abs(C.finite(summary.get("phi_margin_m"), "SDF margin") - row["zero_level_margin_m"]) > row["margin_tolerance_m"] or C.finite(summary.get("phi_margin_gate_m"), "margin gate") != 0.15:
            raise ValueError("summary SDF margin differs")
        wall = C.finite(summary.get("wall_seconds"), "Julia wall time")
        if not 0 < wall <= cfg["per_state_timeout_s"]:
            raise ValueError("Julia summary wall time exceeds budget")
        summary_total += wall
        host = recompute_force_n(csv, {"measurement": m})
        if host["force_scale_n_per_solver_force"] != cfg["force_scale_n_per_solver_force"]:
            raise ValueError("host force scale differs from the registered grid scale")
        for q in ("drag", "downforce"):
            if _rel(host[f"{q}_n"], C.finite(summary.get(f"{q}_time_weighted_n"), f"summary {q}")) > SUMMARY_REL:
                raise ValueError("host recomputation differs from Julia force summary")
        states[name] = {"drag_n": host["drag_n"], "downforce_n": host["downforce_n"], "forces_csv_sha256": sha256(csv), "summary_sha256": sha256(summary_path), "solver_process_wall_seconds": seconds, "julia_summary_wall_seconds": wall}
    total = C.finite(index.get("solver_process_wall_seconds_total"), "total process time")
    if not math.isclose(total, process_total, rel_tol=1e-12) or process_total > cfg["solver_wall_time_cap_s"] or summary_total > cfg["solver_wall_time_cap_s"] or process_total + cfg["reserve_s"] > cfg["kernel_timeout_s"]:
        raise ValueError("aggregate or kernel wall-time budget exceeded or the recorded process sum differs")
    if index.get("parent_forces_csv_sha256") != states[names[0]]["forces_csv_sha256"]:
        raise ValueError("recorded first-state (parent) force CSV hash differs")
    return states


def check_native(inventory: dict) -> dict:
    """Native flow_24/flow_32 values from the hash-bound OPT-01 Stage B analysis (not re-run)."""
    ref = inventory["native_reference"]
    path = _path(ref["analysis_path"])
    if sha256(path) != ref["analysis_sha256"] or ref["analysis_sha256"] != B.OPT01B_ANALYSIS_SHA:
        raise ValueError("OPT-01 Stage B analysis differs from its pinned hash")
    analysis = jload(path)
    if analysis.get("kind") != "opt01b_stage_b_analysis" or analysis.get("integrity") != {"pass": True, "failures": []}:
        raise ValueError("OPT-01 Stage B analysis is not an integrity-passed record")
    _equal({c: analysis["state_forces_n"][c] for c in ("flow_24", "flow_32")}, ref["state_forces_n"], "native reference forces")
    out = {}
    for case, forces in ref["state_forces_n"].items():
        if sorted(forces) != sorted(C.SEVEN):
            raise ValueError(f"native {case} lacks the seven states")
        out[case] = {n: {"downforce_n": C.finite(f["downforce_n"], "native downforce"), "drag_n": C.finite(f["drag_n"], "native drag")} for n, f in forces.items()}
    return out


STEP = {**dict(zip(C.FORWARD, C.FORWARD_MM)), **{n: -s for n, s in zip(C.REVERSE, C.REVERSE_MM)}}


def cell_report(case: str, placement: str, points: dict, parent: dict, pair: dict | None) -> dict:
    """points: state name -> (forces, reference forces); pair: {downforce_n, drag_n} signed parent-pair differences or None (floor only)."""
    res = C.resolution([] if pair is None else [pair["downforce_n"], pair["drag_n"]])
    st = {}
    for name, (f, ref) in points.items():
        dl, dd = f["downforce_n"] - ref["downforce_n"], f["drag_n"] - ref["drag_n"]
        st[name] = {"step_mm": STEP[name], "dL_n": dl, "dD_n": dd, "dL_status": C.sign_status(dl, res), "dD_status": C.sign_status(dd, res), "downforce_n": f["downforce_n"], "drag_n": f["drag_n"]}
    fwd = [n for n in C.FORWARD if n in st]
    s, y = [st[n]["step_mm"] for n in fwd], [st[n]["dL_n"] for n in fwd]
    fit = C.fit_quadratic(s, y)
    rev = {}
    for n in C.REVERSE:
        if n in st:
            pred = fit["b_n_per_mm"] * st[n]["step_mm"] + fit["a_n_per_mm2"] * st[n]["step_mm"] ** 2
            rev[n] = {"step_mm": st[n]["step_mm"], "measured_dL_n": st[n]["dL_n"], "predicted_dL_n": pred, "residual_n": st[n]["dL_n"] - pred}
    hi, lo = st.get(C.FORWARD[3]), st.get(C.REVERSE[1])
    check = C.fit_with_intercept([0.0] + s, [0.0] + y)
    return {"case": case, "placement": placement, "parent_downforce_n": parent["downforce_n"], "parent_drag_n": parent["drag_n"], "pair_difference_n": pair, "resolution_n": res, "states": st,
            "fit": {**fit, "forward_steps_mm": s}, "fit_with_intercept": check, "reverse_check": rev,
            # descriptive robustness (never enters a classification): model-free central slope, intercept-fit slope, leave-one-out slopes
            "b_central_n_per_mm": None if hi is None or lo is None else (hi["dL_n"] - lo["dL_n"]) / (2 * C.MAX_STEP_MM), "b_with_intercept_n_per_mm": check["b_n_per_mm"],
            "b_leave_one_out": [{"dropped_step_mm": s[i], "b_n_per_mm": C.fit_quadratic(s[:i] + s[i + 1:], y[:i] + y[i + 1:])["b_n_per_mm"]} for i in range(len(s))]}


def _pair(a: dict, b: dict) -> dict:
    return {"downforce_n": b["downforce_n"] - a["downforce_n"], "drag_n": b["drag_n"] - a["drag_n"], "forces_csv_byte_identical": a["forces_csv_sha256"] == b["forces_csv_sha256"]}


def class_changes(b: dict, align: dict, fine: dict) -> dict:
    """Would the alignment / fine class / STABLE flag change if the slopes `b` (cell label -> value) replaced the registered ones?  'unchanged', the other value, or 'not computable'."""
    out = {}
    try:
        got = C.alignment_classification(b["24n"], b["24s"], b["32n"], b["32s"])["classification"]
        out["alignment"] = "unchanged" if got == align["classification"] else got
    except ValueError:
        out["alignment"] = "not computable"
    try:
        got = C.fine_classification(b["24n"], b["32n"], b["48n"])
        out["fine"] = "unchanged" if got["classification"] == fine["classification"] else got["classification"]
        out["stable_32_to_48"] = "unchanged" if got["stable_32_to_48"] == fine["stable_32_to_48"] else got["stable_32_to_48"]
    except ValueError:
        out["fine"] = out["stable_32_to_48"] = "not computable"
    return out


def analysis(states: dict, native: dict) -> dict:
    """The registered quantities and classifications from integrity-checked per-kernel forces (every state vs the SAME kernel's parent)."""
    cells, pairs = {}, {}

    def single(kernel):
        s = states[kernel]
        return {n: (s[n], s[C.PARENT]) for n in C.SEVEN[1:] if n in s}, s[C.PARENT]

    pairs["f16"] = _pair(states["f16"][C.PARENT], states["f16"][C.REPEAT])
    pts, par = single("f16")
    cells["16n"] = cell_report("flow_16", "native", pts, par, pairs["f16"])
    a, b = states["f48a"], states["f48b"]
    pairs["f48"] = _pair(a[C.PARENT], b[C.REPEAT])
    pts = {n: (a[n], a[C.PARENT]) for n in C.FORWARD[:3]}
    pts[C.FORWARD[3]], pts[C.REVERSE[1]] = (b[C.FORWARD[3]], b[C.REPEAT]), (b[C.REVERSE[1]], b[C.REPEAT])
    cells["48n"] = cell_report("flow_48", "native", pts, a[C.PARENT], pairs["f48"])
    for case, label in (("flow_24", "24n"), ("flow_32", "32n")):
        nat = native[case]
        cells[label] = cell_report(case, "native", {n: (nat[n], nat[C.PARENT]) for n in C.SEVEN[1:]}, nat[C.PARENT], None)
        pairs[f"native_{case}"] = {"downforce_n": 0.0, "drag_n": 0.0, "basis": "taken as 0: the OPT-01 Stage B parents were byte-identical to the retained references (integrity-checked by that analysis)"}
    for kernel, label in (("s24", "24s"), ("s32", "32s")):
        pts, par = single(kernel)
        ref = native[C.KERNELS[kernel]["case"]][C.PARENT]
        if par["downforce_n"] == ref["downforce_n"] and par["drag_n"] == ref["drag_n"]:
            raise ValueError(f"shift ineffective: the {kernel} job ignored the origin (shifted parent identical to the native parent)")
        cells[label] = cell_report(C.KERNELS[kernel]["case"], "shifted", pts, par, None)
        pairs[kernel] = {"basis": "no parent pair was run on this kernel: resolution is the nominal floor only"}
    b_of = {k: cells[k]["fit"]["b_n_per_mm"] for k in CELL_LABELS}
    align, fine = C.alignment_classification(b_of["24n"], b_of["24s"], b_of["32n"], b_of["32s"]), C.fine_classification(b_of["24n"], b_of["32n"], b_of["48n"])
    align = {**align, "gap_after_shift_ratio": 1 - align["m24"] - align["m32"], "abs_b_24s_minus_b_32s": abs(b_of["24s"] - b_of["32s"])}  # (b_32s - b_24s)/G and its magnitude
    ref48 = a[C.PARENT]["downforce_n"]
    alt48 = C.fit_quadratic(list(C.FORWARD_MM), [(a[n] if n in a else b[n])["downforce_n"] - ref48 for n in C.FORWARD])
    variants = {"b_central": {k: cells[k]["b_central_n_per_mm"] for k in CELL_LABELS}, "b_with_intercept": {k: cells[k]["b_with_intercept_n_per_mm"] for k in CELL_LABELS}, "b_48n_all_vs_f48a_parent": {**b_of, "48n": alt48["b_n_per_mm"]}}
    robustness = {"descriptive_only": True, "b_48n_all_vs_f48a_parent": {k: alt48[k] for k in ("b_n_per_mm", "a_n_per_mm2", "max_residual_n")}, "would_change_if_slopes_were": {k: class_changes(v, align, fine) for k, v in variants.items()}}
    table = {str(n): {"cell": lab, "b_n_per_mm": cells[lab]["fit"]["b_n_per_mm"], "a_n_per_mm2": cells[lab]["fit"]["a_n_per_mm2"], "parent_downforce_n": cells[lab]["parent_downforce_n"], "parent_drag_n": cells[lab]["parent_drag_n"],
                       "dD_at_1.25mm_n": cells[lab]["states"][C.FORWARD[3]]["dD_n"], "dL_at_1.25mm_n": cells[lab]["states"][C.FORWARD[3]]["dL_n"]} for n, lab in ((16, "16n"), (24, "24n"), (32, "32n"), (48, "48n"))}
    placement = {str(n): {"parent_downforce_shifted_minus_native_n": cells[f"{n}s"]["parent_downforce_n"] - cells[f"{n}n"]["parent_downforce_n"], "parent_drag_shifted_minus_native_n": cells[f"{n}s"]["parent_drag_n"] - cells[f"{n}n"]["parent_drag_n"],
                     "b_shifted_minus_native_n_per_mm": b_of[f"{n}s"] - b_of[f"{n}n"], "a_shifted_minus_native_n_per_mm2": cells[f"{n}s"]["fit"]["a_n_per_mm2"] - cells[f"{n}n"]["fit"]["a_n_per_mm2"]} for n in (24, 32)}
    both = {}
    for tag, group in (("24n_32n", ("24n", "32n")), ("24s_32s", ("24s", "32s")), ("32n_48n", ("32n", "48n")), ("48n_alone", ("48n",))):
        per_step = {f"{s:g}": C.both_grid_rule({g: cells[g]["states"][n]["dL_n"] for g in group}, {g: cells[g]["states"][n]["dD_n"] for g in group}) for n, s in zip(C.FORWARD, C.FORWARD_MM)}
        both[tag] = {"descriptive_only": True, "per_step": per_step, "passing_steps_mm": [float(s) for s, v in per_step.items() if v["pass"]]}
    p48 = cells["48n"]["parent_downforce_n"]
    stable = fine["stable_32_to_48"]
    return {"cells": cells, "pair_differences": pairs, "four_point_table": table, "placement_effect": placement, "both_grid_rule_descriptive": both,
            "alignment": align, "fine": fine, "stable_32_to_48": stable, "slope_robustness": robustness, "decision_text": C.decision_text(align["classification"], fine["classification"], stable),
            "hindcast_flow_48_parent_downforce": {"downforce_n": p48, "band_n": HINDCAST_BAND_N, "within_band": HINDCAST_BAND_N[0] <= p48 <= HINDCAST_BAND_N[1], "descriptive_only": True},
            "interpretation": " ".join([INTERPRETATION["common"], INTERPRETATION[align["classification"]], INTERPRETATION[fine["classification"]], INTERPRETATION["stable" if stable else "unstable"]])}


def analyze(dirs: dict, freeze: Any, inventory: Any | None = None) -> dict:
    """dirs: kernel id -> output directory.  Any integrity or computation failure -> GRID02_INCOMPLETE with no analysis fields."""
    report = {"kind": "grid02_trend_analysis", "verdict": "GRID02_INCOMPLETE", "integrity": {"pass": False, "failures": []}, "selected_delta": None, "shape_update_allowed": False,
              "qualification_flags": {k: False for k in QUALIFICATION_FLAGS}, "no_gradient_claim": True, "not_grid_converged": True, "no_gci_claim": True, "opt01_rule_unchanged": True,
              "fd08_verdict_unchanged": True, "reinitialization": "none", "evidence_class": "bounded_four_grid_response_slope_study_one_parent_one_direction_partial_shift_control"}
    try:
        inventory = inventory if inventory is not None else jload(_path(f"{EVIDENCE_REL}/inventory.json"))
        if set(dirs) != set(C.KERNELS):
            raise ValueError("exactly the five registered kernel directories are required")
        validate_registration(freeze, inventory)
        states = {k: check_kernel(Path(dirs[k]), k, freeze, inventory) for k in C.KERNELS}
        result = analysis(states, check_native(inventory))
        report.update(result)
        report.update({"verdict": "GRID02_RECORDED", "integrity": {"pass": True, "failures": []}, "state_forces_n": states,
                       "provenance": {"source_commit": freeze["source_commit"], "inventory_sha256": freeze["inventory_sha256"], "analyzer_sha256": sha256(Path(__file__)), "native_reference_sha256": B.OPT01B_ANALYSIS_SHA,
                                      "kernel_manifest_sha256": {k: sha256(Path(dirs[k]) / "output_manifest.json") for k in C.KERNELS}}})
    except Exception as exc:  # noqa: BLE001 -- every untrusted-input or computation failure is fail-closed
        report = {k: v for k, v in report.items() if k in ("kind", "selected_delta", "shape_update_allowed", "qualification_flags", "no_gradient_claim", "not_grid_converged", "no_gci_claim", "opt01_rule_unchanged",
                                                           "fd08_verdict_unchanged", "reinitialization", "evidence_class")}
        report.update({"verdict": "GRID02_INCOMPLETE", "integrity": {"pass": False, "failures": [f"{type(exc).__name__}: {exc}"]}})
    return report


def check_committed_freeze(freeze_path: Path) -> None:
    """If the freeze is committed at the repository HEAD, the file given must be byte-identical to that blob."""
    rel = f"{EVIDENCE_REL}/prerun_freeze.json"
    blob = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"], capture_output=True)
    if blob.returncode == 0 and Path(freeze_path).read_bytes() != blob.stdout:
        raise ValueError(f"--freeze differs from the committed {rel} at HEAD")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kernel-root", type=Path, required=True, help="directory containing grid02_f16, grid02_f48a, grid02_f48b, grid02_s24, grid02_s32")
    p.add_argument("--freeze", type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", type=Path)
    args = p.parse_args()
    sidecar = None if args.write is None else args.write.with_name(args.write.name + ".sha256")
    if args.write is not None and (args.write.exists() or sidecar.exists()):
        raise SystemExit("refusing to overwrite an existing GRID-02 analysis")
    try:
        check_committed_freeze(args.freeze)
        freeze_sha = sha256(args.freeze)
        if args.freeze.with_name(args.freeze.name + ".sha256").read_text().strip() != freeze_sha:
            raise ValueError("freeze SHA-256 sidecar mismatch")
        freeze = jload(args.freeze)
    except Exception as exc:  # noqa: BLE001
        print(f"invalid freeze: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    report = analyze({k: args.kernel_root / f"grid02_{k}" for k in C.KERNELS}, freeze)
    if args.check or report["integrity"]["pass"] is not True:
        print(json.dumps({"integrity": report["integrity"], "verdict": report["verdict"]}, indent=2, sort_keys=True, allow_nan=False))
        if report["integrity"]["pass"] is not True:
            raise SystemExit(3)
        return
    report["provenance"]["freeze_sha256"] = freeze_sha
    data = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    digest = hashlib.sha256(data.encode()).hexdigest()
    with args.write.open("x") as handle:
        handle.write(data)
    with sidecar.open("x") as handle:
        handle.write(digest + "\n")
    print(report["verdict"], digest)


if __name__ == "__main__":
    main()
