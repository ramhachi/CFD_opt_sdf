#!/usr/bin/env python3
"""Fail-closed LOWDIM-04A Stage A analyzer (#51): two Kaggle kernel outputs -> centered secants at the parent -> dual-grid cone -> terminal verdict.

Forked from analyze_lowdim03 (integrity) and analyze_grid01 (cone) rather than imported: both pin their own step sizes, baselines and file closures.
--check verifies integrity and prints the verdict; --write writes the analysis once (never overwrites).  No partial analysis is ever written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_lowdim04a_kernel as K  # noqa: E402
import lowdim04a_contract as C  # noqa: E402
import lowdim04a_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402
from grid01_gpu import select_worker_gpu  # noqa: E402

EVIDENCE_REL = "docs/evidence/lowdim04a_stage_a_2026_10_13"
KERNELS = {"a": "flow_24", "b": "flow_32"}
SUMMARY_REL = 1e-9
FREEZE_KIND = "lowdim04a_stage_a_prerun_freeze"
INFRA = ROOT / "infra/kaggle"
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
RUNTIME_FIXED = {"machine_shape": "NvidiaTeslaT4", "kernel_timeout_s": 10800, "timeout_s": 10800, "per_state_timeout_s": 900, "solver_wall_time_cap_s": 8100, "instantiate_timeout_s": 2400,
                 "gpu_probe_timeout_s": 300, "reserve_s": 300, "julia_threads": 1, "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0", "selected_gpu_physical_index": 0,
                 "used_gpu_count": 1, "dataset_sources": []}
REQUIRED_FILES = {f"scripts/{n}.py" for n in ("analyze_lowdim04a", "lowdim04a_contract", "lowdim04a_states", "lowdim04a_runner_template", "build_lowdim04a_kernel", "build_lowdim04a_inputs",
                                              "freeze_lowdim04a", "step01_states", "grid01_gpu")} | {"src/cfd_sdf/grid01_contract.py", f"{EVIDENCE_REL}/inventory.json", f"{EVIDENCE_REL}/prerun_note.md"}
FROZEN_PARAMETERS = {"step_m": C.STEP_M, "min_resolved_n": C.MIN_RESOLVED_N, "epsilon_n_per_m": C.EPSILON_N_PER_M, "min_predicted_downforce_n": C.MIN_PREDICTED_DOWNFORCE_N}


def jload(path: Path) -> Any:
    return json.loads(Path(path).read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} differs")


def _rel_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), 1e-300)


def git_tree_sha(commit: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{commit}^{{tree}}"], capture_output=True, text=True, check=True).stdout.strip()


def validate_registration(freeze: Any, inventory: Any, *, check_tree: bool = True, infra: Path = INFRA) -> None:
    """The freeze binds every source file by hash, the rendered workers by re-rendering, the fixed budgets and the source commit by its tree id."""
    if not isinstance(freeze, dict) or freeze.get("kind") != FREEZE_KIND:
        raise ValueError("freeze kind differs")
    if freeze.get("selected_delta") is not None or freeze.get("reinitialization") != "none":
        raise ValueError("selected_delta must stay unset and reinitialization none")
    _equal(freeze.get("qualification_flags"), {k: False for k in FLAGS}, "qualification flags")
    _equal(freeze.get("frozen_parameters"), FROZEN_PARAMETERS, "frozen parameters")
    inv_path = ROOT / EVIDENCE_REL / "inventory.json"
    if freeze.get("inventory_sha256") != sha256(inv_path) or inventory != jload(inv_path):
        raise ValueError("inventory differs from the frozen inventory")
    proof = freeze.get("identity_free_check", {})
    if proof.get("all_free") is not True or proof.get("owner") != "ramhachi888" or not freeze.get("parent_integration_commit"):
        raise ValueError("authenticated identity-free check or parent integration commit is missing")
    required = REQUIRED_FILES | {inventory["parent"]["raw_path"]} | {g["baseline_reference"]["forces_csv_path"] for g in inventory["grids"].values()} | {d["path"] for d in inventory["directions"].values()}
    if not required <= set(freeze["file_hashes"]):
        raise ValueError(f"the freeze omits required files: {sorted(required - set(freeze['file_hashes']))}")
    for rel, digest in freeze["file_hashes"].items():
        if not _is_sha(digest) or sha256(ROOT / rel) != digest:
            raise ValueError(f"frozen file differs: {rel}")
    if check_tree and git_tree_sha(freeze["source_commit"]) != freeze.get("source_tree_id"):
        raise ValueError("source commit tree differs from the frozen tree id")
    for k, grid in KERNELS.items():
        runtime = freeze["runtime"][k]
        _equal({key: runtime.get(key) for key in RUNTIME_FIXED}, RUNTIME_FIXED, f"kernel {k} fixed runtime budgets")
        _equal((runtime.get("kernel_id"), runtime.get("case_id")), (K.KERNEL_IDS[k], grid), f"kernel {k} identity")
        runner = infra / f"kernel_lowdim04a_{k}/runner.py"
        if sha256(runner) != runtime["runner_sha256"] or runner.read_text() != K.render(freeze["source_commit"], k):
            raise ValueError(f"rendered worker {k} differs from the reviewed source")
        if jload(runner.with_name("kernel-metadata.json")) != K.metadata(k) or sha256(runner.with_name("kernel-metadata.json")) != runtime["metadata_sha256"]:
            raise ValueError(f"kernel {k} metadata differs")
        if freeze["pins"][k] != K.pins(k):
            raise ValueError(f"kernel {k} pin map differs from the current files")
    _equal([{k: r.get(k) for k in ("name", "kind", "direction", "step_mm", "sign")} for r in inventory["states"]], L.plan(), "state plan")
    names = [r["name"] for r in inventory["states"]]
    if inventory.get("kernels") != {"a": names, "b": names} or inventory.get("basis_order") != list(L.BASIS) or list(C.BASIS) != list(L.BASIS):
        raise ValueError("kernel plan or basis order differs")
    for row in inventory["states"]:
        if row["hard_count"]["residual_vs_n_max"] != 0 or row["geometry_gates"]["all_hard_gates_pass"] is not True:
            raise ValueError("a frozen state fails the pre-CFD gates")
        if len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) != 2:
            raise ValueError("Fortran and C order hashes must be distinct named fields")


def _manifest(out: Path, names: list[str], grid: str) -> dict:
    files = jload(out / "output_manifest.json")["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files map is missing or empty")
    actual = {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p != out / "output_manifest.json"}
    if set(files) != actual:
        raise ValueError("manifest path set differs from actual output")
    if any(p.is_symlink() for p in out.rglob("*")):
        raise ValueError("symlinks are not permitted in retained kernel output")
    required = {"lowdim04a_index.json", "run_identity.json", "nvidia_smi.csv", "gpu_device_probe.json", "DONE"}
    required |= {f"states/{n}/{f}" for n in names for f in (f"{grid}.forces.csv", f"{grid}.summary.json", "W4_JOB_DONE")}
    if not required <= set(files):
        raise ValueError("manifest omits required output files")
    for relative, digest in files.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or not _is_sha(digest):
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
    index, identity = jload(out / "lowdim04a_index.json"), jload(out / "run_identity.json")
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
        raise ValueError("run identity parent reference differs")
    selected = select_worker_gpu((out / "nvidia_smi.csv").read_text())
    _equal(identity.get("selected_gpu"), selected, "physical GPU selection")
    for key in ("cuda_device_order", "cuda_visible_devices"):
        if identity.get(key) != runtime[key]:
            raise ValueError("run identity CUDA environment differs")
    _equal(jload(out / "gpu_device_probe.json"), {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [selected["uuid"]],
                                                  "default_device_uuid": selected["uuid"], "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}, "CUDA identity")
    entries = index.get("states")
    if not isinstance(entries, list) or [r.get("name") for r in entries] != names:
        raise ValueError("completed entries differ from the exact nine-state plan")
    if {p.name for p in (out / "states").iterdir() if p.is_dir()} != set(names):
        raise ValueError("state directories differ from the exact plan")
    states, process_total, summary_total = {}, 0.0, 0.0
    for row, entry in zip(rows, entries):
        for key in ("name", "kind", "direction", "step_mm", "sign"):
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
        summary, job_env = jload(summary_path), inventory["job_env_common"]
        for key, want in (("canonical_sdf_origin_m", [float(v) for v in job_env["W4_CANONICAL_ORIGIN_M"].split(",")]),
                          ("canonical_design_spacing_m", float(job_env["W4_CANONICAL_DESIGN_SPACING_M"])), ("canonical_state_label", job_env["W4_CANONICAL_STATE_LABEL"]),
                          ("canonical_design_point_shape", [int(v) for v in job_env["W4_POINT_SHAPE"].split(",")]),
                          ("canonical_design_cell_shape", [int(v) for v in job_env["W4_CELL_SHAPE"].split(",")]),
                          ("source_surface_sha256", job_env["W4_SOURCE_SURFACE_SHA256"]), ("device_roundtrip_sha256", row["phi_fortran_order_sha256"])):
            _equal(summary.get(key), want, f"summary {key}")
        for key, want in (("case_id", grid), ("gpu_name", "Tesla T4"), ("gpu_uuid", selected["uuid"]), ("phi_fortran_sha256", row["phi_fortran_order_sha256"]),
                          ("phi_c_order_sha256", row["phi_c_order_sha256"]), ("state_sha256", row["state_sha256"]), ("state_npz_sha256", row["npz_sha256"]),
                          ("force_integration_body", config["measurement"]["candidate_operator"]), ("force_projection_semantics", "drag=+Fx; downforce=-Fz")):
            if summary.get(key) != want:
                raise ValueError(f"state summary {key} differs")
        case = config["measurement"]["case"]
        _equal(summary.get("flow_dims"), case["flow_dims"], "summary grid dimensions")
        for key in ("flow_spacing_m", "solver_length", "solver_time_unit_s", "solver_viscosity", "reynolds", "density_kg_m3", "dynamic_viscosity_pa_s", "reference_length_m", "reference_area_m2"):
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
            if _rel_error(host[f"{q}_n"], C.finite(summary.get(f"{q}_time_weighted_n"), f"summary {q}")) > SUMMARY_REL:
                raise ValueError("host recomputation differs from Julia force summary")
        states[row["name"]] = {f"{q}_n": host[f"{q}_n"] for q in C.RESPONSES}
        states[row["name"]].update({"forces_csv_sha256": sha256(csv), "summary_sha256": sha256(summary_path), "solver_process_wall_seconds": process_seconds, "julia_summary_wall_seconds": wall})
    if C.finite(index.get("solver_process_wall_seconds_total"), "total process time") != process_total or process_total > runtime["solver_wall_time_cap_s"] or summary_total > runtime["solver_wall_time_cap_s"]:
        raise ValueError("aggregate wall-time budget or recorded process sum differs")
    if (out / "states" / L.PARENT_NAME / f"{grid}.forces.csv").read_bytes() != (ROOT / ref["forces_csv_path"]).read_bytes():
        raise ValueError("fresh parent CSV is not byte-identical to the retained LOWDIM-03 s1.25 mm run")
    return states


def _grid_vectors(states: dict[str, dict]) -> tuple[dict, dict, dict]:
    """secants[grid][response][direction], lift/drag matrices (rows grids, columns basis) and unresolved list."""
    secants = {g: {q: {} for q in C.RESPONSES} for g in C.GRIDS}
    for g in C.GRIDS:
        for q in C.RESPONSES:
            for d in L.BASIS:
                secants[g][q][d] = C.secant_sample(states[g][L.PARENT_NAME][f"{q}_n"], states[g][L.state_name(d, 1)][f"{q}_n"], states[g][L.state_name(d, -1)][f"{q}_n"])
    mat = {q: [[secants[g][q][d]["g_sec_n_per_m"] for d in L.BASIS] for g in C.GRIDS] for q in C.RESPONSES}
    unresolved = [f"{g}|{q}|{d}" for g in C.GRIDS for q in C.RESPONSES for d in L.BASIS if not secants[g][q][d]["resolved"]]
    return secants, mat, unresolved


def _volume_projection(inventory: dict, solutions: dict, preds: dict) -> dict:
    """First-order signed volume change of each solved direction from the centered volume secants of the nine retained geometries (solver-free; reports only)."""
    rows = {r["name"]: r for r in inventory["states"]}
    parent_v = inventory["parent_volume"]
    gv = {key: [(rows[L.state_name(d, 1)]["volume"][key] - rows[L.state_name(d, -1)]["volume"][key]) / (2 * C.STEP_M) for d in L.BASIS] for key in ("v_eps_m3", "v_cont_m3")}
    out = {"volume_secants_m3_per_m": gv, "meaning": "lattice count N <= 8272 is exactly satisfied by construction in every state; it constrains no physical or sub-voxel volume"}
    for family in ("main_cross_grid", "robust_cross_grid"):
        w = np.asarray(preds[family]["normalization"]["basis_coefficients_m"])
        out[family] = {"basis_coefficients_m": w.tolist(), "d0_coefficient_m": float(w[0]),
                       **{f"predicted_{k}_change_m3": float(np.dot(gv[k], w)) for k in gv},
                       **{f"predicted_{k}_change_vs_parent": float(np.dot(gv[k], w)) / parent_v[k] for k in gv}}
    return out


def analysis_report(states: dict, inventory: dict, freeze: dict) -> dict:
    secants, mat, unresolved = _grid_vectors(states)
    lift, drag = np.array(mat["downforce"]), np.array(mat["drag"])
    solutions = C.solve(lift, drag)
    directions = {n: S.read_f4(ROOT / inventory["directions"][n]["path"]) for n in L.BASIS}
    preds = C.predictions(solutions, lift, drag, directions)
    verdict = C.verdict(solutions, preds)
    g01 = inventory["grid01_reference"]["coefficient_vectors_n_per_m"]
    components = {}
    for q in C.RESPONSES:
        for i, d in enumerate(L.BASIS):
            a, b = secants["flow_24"][q][d], secants["flow_32"][q][d]
            components[f"{q}|{d}"] = {"flow_24_g": a["g_sec_n_per_m"], "flow_32_g": b["g_sec_n_per_m"], "flow_24_resolved": a["resolved"], "flow_32_resolved": b["resolved"],
                                      "sign_status": "unresolved" if not (a["resolved"] and b["resolved"]) else ("sign_preserved_resolved" if (a["g_sec_n_per_m"] > 0) == (b["g_sec_n_per_m"] > 0) else "sign_flipped_resolved"),
                                      "grid01_flow_24_g_baseline_2p5mm": g01[q]["flow_24"][i], "grid01_flow_32_g_baseline_2p5mm": g01[q]["flow_32"][i]}
    cosines = {q: {"flow_24_vs_flow_32_at_parent": C.cosine_and_norm_ratio(mat[q][0], mat[q][1]), "flow_24_parent_vs_grid01_baseline": C.cosine_and_norm_ratio(g01[q]["flow_24"], mat[q][0]),
                   "flow_32_parent_vs_grid01_baseline": C.cosine_and_norm_ratio(g01[q]["flow_32"], mat[q][1])} for q in C.RESPONSES}
    prior = np.asarray(inventory["prior_robust_proposal"]["coefficient_vector"])
    gram = np.array([[float(np.sum(directions[a].astype(np.float64) * directions[b].astype(np.float64))) for b in L.BASIS] for a in L.BASIS])

    def spatial_cosine(u, v):
        u, v = np.asarray(u, dtype=np.float64), np.asarray(v, dtype=np.float64)
        den = float(np.sqrt((u @ gram @ u) * (v @ gram @ v)))
        return float(u @ gram @ v / den) if den > 0 else None

    prior_cos = {f: {"coefficient_space_cosine": C.cosine_and_norm_ratio(prior, solutions[f]["coefficient_vector"])["cosine"],
                     "spatial_cosine_via_gram_matrix": spatial_cosine(prior, solutions[f]["coefficient_vector"])} for f in ("main_cross_grid", "robust_cross_grid")}
    even = {f"{g}|{q}|{d}": {"even_part_n": secants[g][q][d]["even_part_n"], "eta_even": secants[g][q][d]["eta_even"]} for g in C.GRIDS for q in C.RESPONSES for d in L.BASIS}
    return {"kind": "lowdim04a_stage_a_analysis", "verdict": verdict["verdict"], "integrity": {"pass": True, "failures": []}, "verdict_detail": verdict,
            "secants": secants, "unresolved_components": unresolved, "unresolved_count": len(unresolved), "component_comparisons": components,
            "response_vector_comparisons": cosines, "cosine_to_prior_robust_direction": prior_cos, "even_parts_descriptive_not_used_in_solve": even,
            "solutions": solutions, "predictions_at_1p25mm": preds, "volume_projection": _volume_projection(inventory, solutions, preds),
            "state_forces_n": states, "hard_count": {r["name"]: r["hard_count"] for r in inventory["states"]},
            "frozen_parameters": FROZEN_PARAMETERS, "selected_delta": None, "reinitialization": "none", "shape_update_allowed": False,
            "qualification_flags": {k: False for k in freeze["qualification_flags"]}, "no_gradient_claim": True, "not_grid_converged": True, "not_opt01": True,
            "evidence_class": "bounded_two_grid_local_model_at_the_lowdim03_parent",
            "interpretation": ("FOUND/NOT_FOUND are statements about the linear model under the nominal 3e-5 N floors: not a gain forecast (the even part was 42% of the odd part at the previous step), "
                               "not drag nonincrease (flow_32 drag below the floor is 'unresolved, active at zero within the nominal floor'), not volume feasibility beyond the lattice count, "
                               "not grid convergence, not #26, not an optimizer qualification. No Stage B is authorized by this verdict.")}


def analyze(kernel_a: Path, kernel_b: Path, freeze: Any, inventory: Any | None = None) -> dict:
    report = {"kind": "lowdim04a_stage_a_analysis", "verdict": "LOWDIM04A_INCOMPLETE", "integrity": {"pass": False, "failures": []}, "selected_delta": None,
              "reinitialization": "none", "shape_update_allowed": False, "no_gradient_claim": True, "not_grid_converged": True, "not_opt01": True}
    try:
        inventory = inventory if inventory is not None else jload(ROOT / EVIDENCE_REL / "inventory.json")
        validate_registration(freeze, inventory)
        states = {KERNELS[k]: check_kernel(Path(out), k, freeze, inventory) for k, out in (("a", kernel_a), ("b", kernel_b))}
        report = analysis_report(states, inventory, freeze)
        report["provenance"] = {"source_commit": freeze["source_commit"], "source_tree_id": freeze["source_tree_id"], "inventory_sha256": freeze["inventory_sha256"],
                                "analyzer_sha256": sha256(Path(__file__)), "kernel_manifest_sha256": {"a": sha256(Path(kernel_a) / "output_manifest.json"), "b": sha256(Path(kernel_b) / "output_manifest.json")}}
    except Exception as exc:  # noqa: BLE001 -- every untrusted-input failure is fail-closed
        report["integrity"] = {"pass": False, "failures": [f"{type(exc).__name__}: {exc}"]}
        report["verdict"] = "LOWDIM04A_INCOMPLETE"
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
        raise SystemExit("refusing to overwrite an existing LOWDIM-04A analysis")
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
