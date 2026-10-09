#!/usr/bin/env python3
"""Fail-closed LOWDIM-03 analysis of both seven-state actual-primal outputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_sdf import lowdim03_contract as C  # noqa: E402
from cfd_sdf.lowdim02a_contract import FLOW32_CASE  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402
from grid01_gpu import select_worker_gpu  # noqa: E402
from analyze_grid01 import sha256, _source_commit_failures  # noqa: E402
import build_lowdim03_kernel as kernel_builder  # noqa: E402

EVIDENCE_REL = "docs/evidence/lowdim03_dual_grid_primal_2026_10_10"
FORMAL_REL = "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
GRID01_REL = "docs/evidence/grid01_cross_grid_secant_2026_10_09"
PARENT_COMMIT = "29fd60dd7b985e79b907700ab5600376b10ce230"
GRID01_ANALYSIS_SHA = "ec00ed9afe4f44926dd40ff1e87f303dd9baf89195b19cb550103606beedb69c"
PROPOSAL_SHA = "c0f69676929c3eb17b1b623c599bfd97ea286d09810c63848e0d7499437e0bf5"
SUMMARY_REL = 1e-9
BASELINE_REL = 1e-12
KERNELS = {"a": "flow_24", "b": "flow_32"}
JOBS = {"a": "scripts/waterlily_xfid_candidate_c_job.jl", "b": "scripts/waterlily_lowdim02_flow32_job.jl"}
RUNTIME_NUMBERS = {"per_state_timeout_s": 900, "solver_wall_time_cap_s": 6300,
                   "kernel_timeout_s": 10800, "gpu_probe_timeout_s": 300,
                   "instantiate_timeout_s": 2400, "julia_threads": 1}


def jload(path: Path) -> Any:
    def reject(value):
        raise ValueError(f"nonfinite JSON constant {value}")
    return json.loads(path.read_text(), parse_constant=reject)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


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
    # JSON serialization preserves the bool-versus-number distinction.
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError(f"{label} differs from the fixed declaration")


def _relative_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), 1e-300)


def required_file_paths(inventory: dict) -> set[str]:
    """Regular source/input closure for the registrar; generated runners are separate."""
    paths = {f"scripts/{name}.py" for name in (
        "lowdim03_states", "build_lowdim03_inputs", "lowdim03_runner_template", "build_lowdim03_kernel",
        "freeze_lowdim03", "analyze_lowdim03", "step01_states", "lowdim01_states", "build_lowdim01_inputs",
        "build_grid01_inputs", "analyze_lowdim02a", "analyze_grid01", "build_grid01_kernel",
        "grid01_gpu", "fd08_v2_campaign_io",
    )}
    paths |= {"tests/test_lowdim03_contract.py", "tests/test_lowdim03_analyzer.py", "tests/test_lowdim03_prereg.py", FORMAL_REL,
              f"{EVIDENCE_REL}/inventory.json", f"{EVIDENCE_REL}/inventory.json.sha256",
              f"{EVIDENCE_REL}/identity_free_check.json", f"{EVIDENCE_REL}/identity_free_check.json.sha256",
              f"{EVIDENCE_REL}/prerun_note.md",
              f"{GRID01_REL}/grid01_analysis.json", f"{GRID01_REL}/inventory.json",
              f"{GRID01_REL}/prerun_freeze_amend1.json",
              "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json",
              "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json",
              "julia/CFDSDFWaterLilyT4/Project.toml", "julia/CFDSDFWaterLilyT4/Manifest.toml"}
    for directory, pattern in (("src/cfd_sdf", "*.py"), ("julia/CFDSDFWaterLily/src", "*")):
        paths |= {str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob(pattern)
                  if p.is_file() and "__pycache__" not in p.parts}
    paths |= {inventory["proposal"]["file"], inventory["canonical_npz"]["path"], inventory["baseline"]["path"]}
    paths |= {row["path"] for row in inventory["directions"].values()}
    paths |= {row["baseline_reference"]["forces_csv_path"] for row in inventory["grids"].values()}
    paths |= set(JOBS.values())
    return paths


def validate_registration(freeze: Any, inventory: Any) -> None:
    if not isinstance(freeze, dict) or not isinstance(inventory, dict):
        raise ValueError("freeze and inventory must be objects")
    if freeze.get("kind") != "lowdim03_dual_grid_primal_prerun_freeze" or freeze.get("parent_integration_commit") != PARENT_COMMIT:
        raise ValueError("freeze kind or approved integration parent differs")
    _equal(freeze.get("rules"), C.RULES, "frozen acceptance rules")
    _equal(freeze.get("qualification_flags"), {key: False for key in C.QUALIFICATION_FLAGS}, "frozen qualification flags")
    if freeze.get("selected_delta") is not None or freeze.get("reinitialization") != "none":
        raise ValueError("freeze must not select delta or authorize reinitialization")
    frozen_at = datetime.fromisoformat(freeze["frozen_utc"].replace("Z", "+00:00"))
    if frozen_at.tzinfo is None or frozen_at > datetime.now(timezone.utc):
        raise ValueError("freeze time must be aware and not in the future")
    from freeze_lowdim03 import require_identity
    identity_path = _path(f"{EVIDENCE_REL}/identity_free_check.json")
    _equal(freeze.get("identity_free_check"), jload(identity_path), "provider identity evidence")
    require_identity(freeze["identity_free_check"], as_of=frozen_at)
    if inventory.get("kind") != "lowdim03_dual_grid_primal_inventory":
        raise ValueError("inventory kind differs")
    inv_path = _path(f"{EVIDENCE_REL}/inventory.json")
    inv_sha = sha256(inv_path)
    if freeze.get("inventory_sha256") != inv_sha or jload(inv_path) != inventory:
        raise ValueError("inventory does not match frozen bytes")
    if _path(f"{EVIDENCE_REL}/inventory.json.sha256").read_text().strip() != inv_sha:
        raise ValueError("inventory sidecar mismatch")
    hashes = freeze.get("file_hashes")
    if not isinstance(hashes, dict) or not required_file_paths(inventory) <= set(hashes):
        raise ValueError("frozen file/source closure is incomplete")
    for relative, digest in hashes.items():
        path = _path(relative)
        if not _sha(digest) or not path.is_file() or sha256(path) != digest:
            raise ValueError(f"frozen file hash mismatch: {relative}")
    failures = _source_commit_failures(freeze.get("source_commit", ""), hashes, root=ROOT,
                                       file_paths={p: p for p in hashes}, exceptions=set(), parent_commit=PARENT_COMMIT)
    if failures:
        raise ValueError("source commit binding failed: " + "; ".join(failures))
    plan = C.state_plan()
    rows = inventory["states"]
    if not isinstance(rows, list) or len(rows) != 7:
        raise ValueError("inventory must contain the ordered seven-state plan")
    names = [row["name"] for row in plan]
    _equal(inventory["kernels"], {k: names for k in KERNELS}, "kernel plans")
    for row, expected in zip(rows, plan):
        for key, value in expected.items():
            actual = row.get(key)
            if key == "step_mm":
                actual = C.finite(actual, "state step_mm")
            if key == "sign" and type(actual) is not int:
                raise ValueError("state sign must be an integer")
            if actual != value:
                raise ValueError(f"state {key} differs from the exact plan")
        for key in ("phi_fortran_order_sha256", "phi_c_order_sha256", "state_sha256", "npz_sha256"):
            if not _sha(row.get(key)):
                raise ValueError(f"state {key} is missing or malformed")
        if type(row.get("changed_node_count")) is not int or row["changed_node_count"] < 0:
            raise ValueError("changed_node_count must be a nonnegative integer")
        for key in ("maximum_pointwise_change_m", "zero_level_margin_m", "margin_tolerance_m"):
            if C.finite(row.get(key), key) < 0:
                raise ValueError(f"state {key} must be nonnegative")
        if row["kind"] == "baseline":
            if row["geometry_gates"] is not None or row["changed_node_count"] != 0 or row["maximum_pointwise_change_m"] != 0:
                raise ValueError("baseline perturbation metadata is malformed")
        else:
            if not C.geometry_pass(row["geometry_gates"]):
                raise ValueError("registered perturbation must pass every hard geometry gate")
            if row["changed_node_count"] == 0 or row["maximum_pointwise_change_m"] <= 0:
                raise ValueError("perturbation state is unchanged")
    if len({r["phi_fortran_order_sha256"] for r in rows}) != 7:
        raise ValueError("registered states are not distinct")
    historical = jload(_path(f"{GRID01_REL}/inventory.json"))
    if C.finite(inventory.get("margin_gate_m"), "geometry clearance gate") != 0.15:
        raise ValueError("clearance gate differs from the fixed geometry contract")
    _equal(inventory.get("geometry_gate_thresholds"),
           jload(_path("docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json"))["geometry_gate_thresholds"],
           "fixed geometry thresholds")
    for key in ("baseline", "directions", "canonical_npz", "job_env_common"):
        _equal(inventory[key], historical[key], f"immutable {key}")
    if sha256(_path(inventory["baseline"]["path"])) != inventory["baseline"]["phi_fortran_sha256"]:
        raise ValueError("immutable baseline SDF bytes differ")
    if sha256(_path(inventory["canonical_npz"]["path"])) != inventory["canonical_npz"]["sha256"]:
        raise ValueError("immutable canonical archive bytes differ")
    for direction in inventory["directions"].values():
        if sha256(_path(direction["path"])) != direction["sha256_fortran_raw"]:
            raise ValueError("immutable basis direction bytes differ")
    _equal(inventory.get("basis_order"), historical["basis_order"], "basis order")
    proposal = inventory["proposal"]
    analysis_path = _path(f"{GRID01_REL}/grid01_analysis.json")
    if sha256(analysis_path) != GRID01_ANALYSIS_SHA or proposal.get("analysis_sha256") != GRID01_ANALYSIS_SHA:
        raise ValueError("approved GRID-01 analysis hash mismatch")
    approved = jload(analysis_path)["proposal_predictions_with_actual_m"]["robust_cross_grid"]
    for key, source in (("coefficient_vector", "coefficient_vector"), ("m_max_abs_sum", "m_max_abs_sum_from_actual_four_direction_arrays"),
                        ("per_unit_step_basis_coefficients", "per_unit_step_basis_coefficients_c_over_m"), ("per_grid", "per_grid")):
        _equal(proposal[key], approved[source], f"frozen robust proposal {key}")
    if proposal.get("sha256_fortran_raw") != PROPOSAL_SHA or sha256(_path(proposal["file"])) != PROPOSAL_SHA:
        raise ValueError("approved proposal direction bytes differ")
    formal = jload(_path(FORMAL_REL))["measurement"]
    if set(inventory["grids"]) != set(KERNELS) or set(freeze.get("runtime", {})) != set(KERNELS) or set(freeze.get("pins", {})) != set(KERNELS):
        raise ValueError("both registered grids/runtime/pins are required")
    for kernel, grid in KERNELS.items():
        config, runtime, pins = inventory["grids"][kernel], freeze["runtime"][kernel], freeze["pins"][kernel]
        if config.get("case_id") != grid or config.get("job") != JOBS[kernel] or runtime.get("case_id") != grid:
            raise ValueError("grid/job/runtime identity differs")
        if runtime.get("kernel_id") != f"ramhachi888/cfd-opt-sdf-lowdim03-{kernel}":
            raise ValueError("kernel identity differs from the registered LOWDIM-03 identity")
        for key, want in RUNTIME_NUMBERS.items():
            if type(runtime.get(key)) is not int or runtime[key] != want:
                raise ValueError(f"runtime {key} differs")
        if runtime.get("cuda_device_order") != "PCI_BUS_ID" or runtime.get("cuda_visible_devices") != "0":
            raise ValueError("runtime CUDA selection differs")
        runner = _path(f"infra/kaggle/kernel_lowdim03_{kernel}/runner.py")
        if not _sha(runtime.get("runner_sha256")) or sha256(runner) != runtime["runner_sha256"]:
            raise ValueError("rendered runner hash differs from runtime freeze")
        if runner.read_text() != kernel_builder.render(freeze["source_commit"], kernel):
            raise ValueError("rendered runner does not reproduce from reviewed template/source")
        metadata = runner.with_name("kernel-metadata.json")
        if sha256(metadata) != runtime.get("metadata_sha256") or jload(metadata) != kernel_builder.metadata(kernel):
            raise ValueError("rendered kernel metadata differs")
        for key, want in (("timeout_s", 10800), ("selected_gpu_physical_index", 0), ("used_gpu_count", 1)):
            if type(runtime.get(key)) is not int or runtime[key] != want:
                raise ValueError(f"runtime {key} differs")
        if runtime.get("machine_shape") != "NvidiaTeslaT4" or runtime.get("dataset_sources") != []:
            raise ValueError("runtime provider machine/dataset binding differs")
        measurement = config["measurement"]
        expected_case = {**formal["case"], **(FLOW32_CASE if kernel == "b" else {})}
        _equal(measurement["case"], expected_case, f"{grid} physical/numerical case")
        for key, want in (("case_id", grid), ("force_unit", "N"), ("time_window_t_u_l", [80.0, 120.0]),
                          ("candidate_operator", formal["candidate_operator"])):
            _equal(measurement.get(key), want, f"{grid} measurement {key}")
        for key, runtime_key in (("per_state_timeout_s", "per_state_timeout_s"), ("solver_wall_time_cap_s", "solver_wall_time_cap_s"),
                                 ("kernel_execution_allowance_s", "kernel_timeout_s")):
            if type(measurement.get(key)) is not int or measurement[key] != runtime[runtime_key]:
                raise ValueError(f"{grid} measurement/runtime budget {key} differs")
        if not isinstance(pins, dict) or not pins:
            raise ValueError("kernel pins must be a nonempty map")
        required_pins = {config["job"], f"{EVIDENCE_REL}/inventory.json", inventory["baseline"]["path"],
                         proposal["file"], config["baseline_reference"]["forces_csv_path"], "scripts/lowdim03_states.py",
                         "scripts/step01_states.py", "scripts/grid01_gpu.py", "julia/CFDSDFWaterLilyT4/Project.toml",
                         "julia/CFDSDFWaterLilyT4/Manifest.toml", "julia/CFDSDFWaterLily/src"}
        if not required_pins <= set(pins):
            raise ValueError("runtime pin closure is incomplete")
        _equal(pins, kernel_builder.pins(kernel), "complete runtime pin map")
        for relative, digest in pins.items():
            if not _sha(digest) or sha256(_path(relative)) != digest:
                raise ValueError(f"runtime pin hash mismatch: {relative}")
        ref = config["baseline_reference"]
        approved_ref = (jload(_path("docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json"))["fd08_baseline_reference"]
                        if kernel == "a" else historical["flow32_baseline_reference"])
        if ref["forces_csv_sha256"] != approved_ref["forces_csv_sha256"]:
            raise ValueError("baseline reference is not the approved retained grid baseline")
        csv = _path(ref["forces_csv_path"])
        if not _sha(ref["forces_csv_sha256"]) or sha256(csv) != ref["forces_csv_sha256"]:
            raise ValueError("baseline reference bytes differ")
        host = recompute_force_n(csv, {"measurement": measurement})
        for q in C.RESPONSES:
            saved = C.finite(ref["host_recomputed_n"][f"{q}_n"], "baseline reference force")
            if _relative_error(host[f"{q}_n"], saved) > BASELINE_REL:
                raise ValueError("baseline reference host force differs")


def _manifest(out: Path, names: list[str], grid: str) -> dict:
    files = jload(out / "output_manifest.json")["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files map is missing or empty")
    actual = {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p != out / "output_manifest.json"}
    if set(files) != actual:
        raise ValueError("manifest path set differs from actual output")
    if any(p.is_symlink() for p in out.rglob("*")):
        raise ValueError("symlinks are not permitted in retained kernel output")
    required = {"lowdim03_index.json", "run_identity.json", "nvidia_smi.csv", "gpu_device_probe.json", "gpu_device_probe.log", "DONE"}
    required |= {f"states/{name}/{filename}" for name in names
                 for filename in (f"{grid}.forces.csv", f"{grid}.summary.json", "W4_JOB_DONE")}
    if not required <= set(files):
        raise ValueError("manifest omits required output files")
    for relative, digest in files.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or not _sha(digest):
            raise ValueError("unsafe manifest path or malformed digest")
        if sha256(out / rel) != digest:
            raise ValueError(f"manifest hash mismatch: {relative}")
    return files


def check_kernel(out: Path, kernel: str, freeze: dict, inventory: dict) -> dict:
    grid = KERNELS[kernel]
    config, runtime = inventory["grids"][kernel], freeze["runtime"][kernel]
    rows = inventory["states"]
    names = [r["name"] for r in rows]
    if not (out / "DONE").is_file() or any(out.rglob("ERROR.txt")):
        raise ValueError("DONE must exist and ERROR.txt must not")
    _manifest(out, names, grid)
    index, identity = jload(out / "lowdim03_index.json"), jload(out / "run_identity.json")
    for record in (index, identity):
        for key, want in (("kernel", kernel), ("kernel_id", runtime["kernel_id"]), ("case_id", grid)):
            if record.get(key) != want:
                raise ValueError(f"output {key} identity differs")
    if index.get("status") != "COMPLETE" or identity.get("source_commit") != freeze["source_commit"] or identity.get("failure_stage") is not None:
        raise ValueError("terminal/source/failure-stage identity differs")
    if identity.get("runner_sha256") != runtime["runner_sha256"] or identity.get("pins") != freeze["pins"][kernel] or identity.get("verified") != freeze["pins"][kernel]:
        raise ValueError("runner identity or verified pin map differs")
    ref = config["baseline_reference"]
    if identity.get("baseline_csv_sha256") != ref["forces_csv_sha256"]:
        raise ValueError("run identity baseline reference differs")
    selected = select_worker_gpu((out / "nvidia_smi.csv").read_text())
    _equal(identity.get("selected_gpu"), selected, "physical GPU selection")
    for key in ("cuda_device_order", "cuda_visible_devices"):
        if identity.get(key) != runtime[key]:
            raise ValueError("run identity CUDA environment differs")
    _equal(jload(out / "gpu_device_probe.json"), {
        "logical_device_count": 1, "visible_gpu_names": ["Tesla T4"],
        "visible_gpu_uuids": [selected["uuid"]], "default_device_uuid": selected["uuid"],
        "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0",
    }, "independently observed CUDA singleton/default identity")
    entries = index.get("states")
    if not isinstance(entries, list) or [r.get("name") for r in entries] != names:
        raise ValueError("completed entries differ from the exact seven-state plan")
    if {p.name for p in (out / "states").iterdir() if p.is_dir()} != set(names):
        raise ValueError("state directories differ from the exact plan")
    states, process_total, summary_total = {}, 0.0, 0.0
    for row, entry in zip(rows, entries):
        for key in ("name", "kind", "step_mm", "sign"):
            _equal(entry.get(key), row[key], f"index state {key}")
        if entry.get("complete") is not True or type(entry.get("exit_code")) is not int or entry["exit_code"] != 0:
            raise ValueError("state process is incomplete")
        process_seconds = C.finite(entry.get("seconds"), "state process wall time")
        if not 0 < process_seconds <= runtime["per_state_timeout_s"]:
            raise ValueError("state process wall time exceeds budget")
        process_total += process_seconds
        directory = out / "states" / row["name"]
        csv, summary_path = directory / f"{grid}.forces.csv", directory / f"{grid}.summary.json"
        if entry.get("forces_csv_sha256") != sha256(csv):
            raise ValueError("state force CSV differs from index")
        summary = jload(summary_path)
        job_env = inventory["job_env_common"]
        canonical_metadata = {
            "canonical_sdf_origin_m": [float(v) for v in job_env["W4_CANONICAL_ORIGIN_M"].split(",")],
            "canonical_design_spacing_m": float(job_env["W4_CANONICAL_DESIGN_SPACING_M"]),
            "canonical_state_label": job_env["W4_CANONICAL_STATE_LABEL"],
            "canonical_design_point_shape": [int(v) for v in job_env["W4_POINT_SHAPE"].split(",")],
            "canonical_design_cell_shape": [int(v) for v in job_env["W4_CELL_SHAPE"].split(",")],
            "source_surface_sha256": job_env["W4_SOURCE_SURFACE_SHA256"],
            "device_roundtrip_sha256": row["phi_c_order_sha256"],
        }
        for key, want in canonical_metadata.items():
            _equal(summary.get(key), want, f"summary {key}")
        for key, want in (("case_id", grid), ("gpu_name", "Tesla T4"), ("gpu_uuid", selected["uuid"]),
                          ("phi_fortran_sha256", row["phi_fortran_order_sha256"]), ("phi_c_order_sha256", row["phi_c_order_sha256"]),
                          ("state_sha256", row["state_sha256"]), ("state_npz_sha256", row["npz_sha256"]),
                          ("force_integration_body", config["measurement"]["candidate_operator"]),
                          ("force_projection_semantics", "drag=+Fx; downforce=-Fz")):
            if summary.get(key) != want:
                raise ValueError(f"state summary {key} differs")
        case = config["measurement"]["case"]
        _equal(summary.get("flow_dims"), case["flow_dims"], "summary grid dimensions")
        for key in ("flow_spacing_m", "solver_length", "solver_time_unit_s", "solver_viscosity", "reynolds",
                    "density_kg_m3", "dynamic_viscosity_pa_s", "reference_length_m", "reference_area_m2"):
            if not math.isclose(C.finite(summary.get(key), key), C.finite(case[key], key), rel_tol=1e-12, abs_tol=1e-15):
                raise ValueError(f"summary {key} differs from grid-specific measurement")
        _equal(summary.get("freestream_mps"), case["freestream_mps"], "summary freestream")
        if any(summary.get(key) is not True for key in ("finite_u", "finite_p", "finite_forces")):
            raise ValueError("state fields or forces are not finite")
        if type(summary.get("julia_threads")) is not int or summary["julia_threads"] != 1:
            raise ValueError("summary Julia thread count differs")
        if C.finite(summary.get("t_end_reached"), "horizon") < 120 or C.finite(summary.get("burn_in_t_u_l"), "burn in") != 80:
            raise ValueError("summary time window/horizon differs")
        margin = C.finite(summary.get("phi_margin_m"), "SDF margin")
        if abs(margin - row["zero_level_margin_m"]) > row["margin_tolerance_m"] or C.finite(summary.get("phi_margin_gate_m"), "margin gate") != 0.15:
            raise ValueError("summary SDF margin differs")
        wall = C.finite(summary.get("wall_seconds"), "Julia wall time")
        if not 0 < wall <= runtime["per_state_timeout_s"]:
            raise ValueError("Julia summary wall time exceeds budget")
        summary_total += wall
        host = recompute_force_n(csv, {"measurement": config["measurement"]})
        for q in C.RESPONSES:
            saved = C.finite(summary.get(f"{q}_time_weighted_n"), f"summary {q}")
            if _relative_error(host[f"{q}_n"], saved) > SUMMARY_REL:
                raise ValueError("host recomputation differs from Julia force summary")
        states[row["name"]] = {q: host[q] for q in ("drag_n", "downforce_n")}
        states[row["name"]].update({"forces_csv_sha256": sha256(csv), "summary_sha256": sha256(summary_path),
                                    "solver_process_wall_seconds": process_seconds, "julia_summary_wall_seconds": wall})
    if (C.finite(index.get("solver_process_wall_seconds_total"), "total process time") != process_total
            or process_total > runtime["solver_wall_time_cap_s"] or summary_total > runtime["solver_wall_time_cap_s"]):
        raise ValueError("aggregate wall-time budget or recorded process sum differs")
    baseline_csv = out / "states" / C.BASELINE_NAME / f"{grid}.forces.csv"
    if baseline_csv.read_bytes() != _path(ref["forces_csv_path"]).read_bytes():
        raise ValueError("fresh baseline CSV is not byte-identical to the registered reference")
    for q in C.RESPONSES:
        if _relative_error(states[C.BASELINE_NAME][f"{q}_n"], ref["host_recomputed_n"][f"{q}_n"]) > BASELINE_REL:
            raise ValueError("fresh baseline force differs from the registered reference")
    return states


INTERPRETATION = {
    "common": ("One frozen combined direction (the GRID-01 L1-sensitivity robust proposal; 'robust' means only the registered secant sensitivity, not a measured error bound), three shared positive "
               "steps and three paired reverse diagnostics; actual computed forces and geometry decide. A strict computed drag non-increase is a computed sign, not noise-resolved or physical "
               "non-increase (the GRID-01 flow_32 drag prediction is inside the nominal 3e-5 N floor, so a flow_32 drag sign is not expected to be noise-resolved). Finite-step model agreement is "
               "descriptive, not a trust-region/filter optimizer, gradient or grid qualification."),
    "LOWDIM03_ACCEPT": "A common step passed every registered condition on both grids: a bounded computed capability for this direction and ladder only.",
    "LOWDIM03_NO_ACCEPT": ("No common step passed every condition: a bounded No-Go for this direction and ladder, not proof that the four-direction basis is insufficient, and not evidence about physical "
                           "drag when the deciding drag change lies within +/-3e-5 N."),
    "LOWDIM03_INCOMPLETE": "The integrity gates failed: nothing is concluded.",
}


def selected_drag_note(report, candidates):
    name = report.get("selected")
    if not name:
        return ""
    near = [g for g, v in candidates[name]["per_grid"].items() if v["small_computed_drag_margin"]]
    return f" On the selected step the drag change is within +/-3e-5 N on: {', '.join(near)} (computed sign only)." if near else ""


def analyze(kernel_a: Path, kernel_b: Path, freeze: Any, inventory: Any | None = None) -> dict:
    report = {"kind": "lowdim03_dual_grid_actual_primal_analysis", "verdict": "LOWDIM03_INCOMPLETE",
              "integrity": {"pass": False, "failures": []}, "selected_delta": None, "grad03_verdict": None,
              "fd08_verdict_unchanged": True, "no_gradient_claim": True, "not_grid_converged": True,
              "not_opt01": True, "reinitialization": "none", "shape_update_allowed": False,
              "qualification_flags": {key: False for key in C.QUALIFICATION_FLAGS},
              "evidence_class": "bounded_two_grid_fixed_direction_actual_primal_trial"}
    try:
        inventory = inventory if inventory is not None else jload(_path(f"{EVIDENCE_REL}/inventory.json"))
        validate_registration(freeze, inventory)
        states = {KERNELS[k]: check_kernel(Path(out), k, freeze, inventory)
                  for k, out in (("a", kernel_a), ("b", kernel_b))}
        base = {g: states[g][C.BASELINE_NAME] for g in C.GRIDS}
        rows = {r["name"]: r for r in inventory["states"]}
        candidates, diagnostics = {}, {}
        for step in C.STEPS_MM:
            name = C.state_name(step, 1)
            plus = {g: states[g][name] for g in C.GRIDS}
            minus = {g: states[g][C.state_name(step, -1)] for g in C.GRIDS}
            candidates[name] = C.evaluate_candidate(base, plus, C.geometry_pass(rows[name]["geometry_gates"]))
            diagnostics[f"{step:g}"] = C.model_diagnostics(base, plus, minus, inventory["proposal"], step)
        report.update(C.select_trial(candidates, {C.state_name(s, 1): s for s in C.STEPS_MM}))
        report.update({"integrity": {"pass": True, "failures": []}, "candidates": candidates,
                       "state_forces_n": states, "paired_model_diagnostics": diagnostics,
                       "geometry_gates_by_state": {n: r["geometry_gates"] for n, r in rows.items()},
                       "rules": {"strict_downforce_gain_greater_than_n": C.MIN_DOWNFORCE_GAIN_N,
                                 "drag_allowance_n": C.DRAG_ALLOWANCE_N, "small_drag_margin_diagnostic_n": C.SMALL_DRAG_MARGIN_N,
                                 "rho_denominator": "raw finite-step linear gain, not sensitivity lower bound",
                                 "rho_denominator_floor_n": C.PREDICTION_DENOMINATOR_FLOOR_N,
                                 "reverse_controls_eligible": False, "rho_is_acceptance_gate": False},
                       "interpretation": INTERPRETATION["common"] + " " + INTERPRETATION[report["verdict"]] + selected_drag_note(report, candidates),
                       "provenance": {"source_commit": freeze["source_commit"], "inventory_sha256": freeze["inventory_sha256"],
                                      "analyzer_sha256": sha256(Path(__file__)),
                                      "kernel_manifest_sha256": {"a": sha256(Path(kernel_a) / "output_manifest.json"),
                                                                 "b": sha256(Path(kernel_b) / "output_manifest.json")}}})
    except Exception as exc:  # noqa: BLE001 -- every untrusted-input failure is fail-closed
        report["integrity"] = {"pass": False, "failures": [f"{type(exc).__name__}: {exc}"]}
        report["verdict"] = "LOWDIM03_INCOMPLETE"
        report.pop("selected", None)
        report.pop("selected_step_mm", None)
        report.pop("selection_objective", None)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-a-dir", type=Path, required=True)
    parser.add_argument("--kernel-b-dir", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", type=Path)
    args = parser.parse_args()
    if args.write is not None and args.write.exists():
        raise SystemExit("refusing to overwrite an existing LOWDIM-03 analysis")
    try:
        freeze_sha = sha256(args.freeze)
        if args.freeze.with_name(args.freeze.name + ".sha256").read_text().strip() != freeze_sha:
            raise ValueError("freeze SHA-256 sidecar mismatch")
        freeze = jload(args.freeze)
    except Exception as exc:  # noqa: BLE001
        print(f"invalid freeze: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    report = analyze(args.kernel_a_dir, args.kernel_b_dir, freeze)
    if args.check or report["integrity"]["pass"] is not True:
        print(json.dumps({"integrity": report["integrity"], "verdict": report["verdict"]}, indent=2, sort_keys=True, allow_nan=False))
        if report["integrity"]["pass"] is not True:
            raise SystemExit(3)
        return
    report["provenance"]["freeze_sha256"] = freeze_sha
    data = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(report["verdict"], hashlib.sha256(data.encode()).hexdigest())


if __name__ == "__main__":
    main()
