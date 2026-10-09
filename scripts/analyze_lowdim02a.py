#!/usr/bin/env python3
"""LOWDIM-02A (#49) host analyzer: integrity of the flow_32 T4 kernel, then the pre-registered Stage A verdict (run once).

One kernel, five flow_32 states: baseline, baseline repeat, the LOWDIM-01 accepted +1.25 mm step, its -1.25 mm reverse control and +2.5 mm (descriptive only).  The verdict is decided by the ACTUAL
primal responses only (host-recomputed with the flow_32 force scale).  Verdicts: STAGE_A_PASS | STAGE_A_SIGN_FLIP | STAGE_A_UNRESOLVED | STAGE_A_CONSTRAINT_FAIL | STAGE_A_INCOMPLETE.
Not a gradient qualification, not GRID-01 (#26), not OPT-01 (#30); no flag, FD-08 verdict, delta or GRAD-03 change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from cfd_sdf import lowdim02a_contract as C  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402

E = ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
FORMAL_CRITERIA = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
LOWDIM01_ANALYSIS = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09/lowdim01_analysis.json"
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
SUMMARY_REL = 1e-9
BASELINE_REL = 1e-12
MIN_T_END = 120.0
NAMES = {"base": "lowdim02a__baseline", "repeat": "lowdim02a__baseline_repeat", "plus": "lowdim02a__prop__s1.25mm", "minus": "lowdim02a__ctrl_reverse__s1.25mm", "plus25": "lowdim02a__prop__s2.5mm"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def jload(path: Path):
    return json.loads(Path(path).read_text())


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-300)


def flow32_criteria(formal: dict) -> dict:
    m = json.loads(json.dumps(formal["measurement"]))
    m["case"] = {**m["case"], **C.FLOW32_CASE}
    return {"measurement": m}


def check_kernel(out: Path, freeze: dict, inventory: dict, criteria: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    states: dict = {}
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done == error:
        failures.append(f"exactly one of DONE/ERROR.txt must exist (done={done}, error={error})")
    index = jload(out / "lowdim02a_index.json") if (out / "lowdim02a_index.json").is_file() else {}
    identity = jload(out / "run_identity.json") if (out / "run_identity.json").is_file() else {}
    if index.get("status") != "COMPLETE" or index.get("kernel") != "a":
        failures.append(f"lowdim02a_index status {index.get('status')!r}")
    if identity.get("source_commit") != freeze["source_commit"] or identity.get("failure_stage") is not None:
        failures.append("run identity source commit / failure stage")
    if not freeze["pins"]:
        failures.append("the freeze has no pins to verify")
    for rel_path, digest in freeze["pins"].items():
        if identity.get("verified", {}).get(rel_path) != digest:
            failures.append(f"pin not verified on the kernel: {rel_path}")
    if identity.get("flow32_baseline_csv_sha256") != freeze["flow32_baseline"]["forces_csv_sha256"]:
        failures.append("the flow_32 baseline CSV pin differs from the freeze")
    manifest = jload(out / "output_manifest.json").get("files") if (out / "output_manifest.json").is_file() else None
    plan = inventory["kernels"]["a"]
    if not isinstance(manifest, dict):
        failures.append("output_manifest.json missing or malformed")
    else:
        required = {"lowdim02a_index.json", "run_identity.json", "nvidia_smi.csv"} | {f"states/{n}/{f}" for n in plan for f in ("flow_32.forces.csv", "flow_32.summary.json", "W4_JOB_DONE")}
        if not required <= set(manifest):
            failures.append("the manifest does not list every required output file")
        for rel_path, digest in manifest.items():
            p = out / rel_path
            if not p.is_file() or sha256(p) != digest:
                failures.append(f"manifest mismatch: {rel_path}")
    gpu = (out / "nvidia_smi.csv").read_text() if (out / "nvidia_smi.csv").is_file() else ""
    if not gpu.strip() or any("Tesla T4" not in r for r in gpu.strip().splitlines()):
        failures.append("the recorded GPU is not a Tesla T4")
    listed = [e.get("name") for e in index.get("states", [])]
    if listed != plan or not all(e.get("complete") for e in index.get("states", [])):
        failures.append("the completed states are not exactly the registered plan")
    present = sorted(p.name for p in (out / "states").iterdir() if p.is_dir()) if (out / "states").is_dir() else []
    if present != sorted(plan):
        failures.append("the state directories differ from the plan")
    by_name = {r["name"]: r for r in inventory["states"]}
    for name in plan:
        row, d = by_name[name], out / "states" / name
        try:
            csv, summary_path = d / "flow_32.forces.csv", d / "flow_32.summary.json"
            if not (csv.is_file() and summary_path.is_file() and (d / "W4_JOB_DONE").is_file()):
                raise ValueError("a state output file is missing")
            entry = next(e for e in index["states"] if e["name"] == name)
            if entry.get("forces_csv_sha256") != sha256(csv):
                raise ValueError("the force CSV differs from the index")
            summary = jload(summary_path)
            for key, want in (("phi_fortran_sha256", row["phi_fortran_order_sha256"]), ("state_sha256", row["state_sha256"]), ("state_npz_sha256", row["npz_sha256"]),
                              ("phi_c_order_sha256", row["phi_c_order_sha256"]), ("gpu_name", "Tesla T4")):
                if summary.get(key) != want:
                    raise ValueError(f"summary {key} differs from the registered value")
            margin = summary.get("phi_margin_m")
            if not isinstance(margin, (int, float)) or not abs(margin - row["zero_level_margin_m"]) <= row["margin_tolerance_m"] or summary.get("phi_margin_gate_m") != 0.15:
                raise ValueError("summary margin differs from the registered value")
            t_end = summary.get("t_end_reached")
            if not (summary.get("finite_u") is True and summary.get("finite_p") is True and summary.get("finite_forces") is True and summary.get("case_id") == "flow_32"
                    and isinstance(t_end, (int, float)) and t_end >= MIN_T_END and summary.get("julia_threads") == 1):
                raise ValueError("summary finiteness / horizon / case / threads")
            host = recompute_force_n(csv, criteria)
            for host_q, summary_q in (("drag_n", "drag_time_weighted_n"), ("downforce_n", "downforce_time_weighted_n")):
                sv = summary.get(summary_q)
                if not isinstance(sv, (int, float)) or not math.isfinite(host[host_q]) or not rel(host[host_q], sv) <= SUMMARY_REL:
                    raise ValueError("the host recomputation differs from the Julia summary")
            states[name] = {"drag_n": host["drag_n"], "downforce_n": host["downforce_n"], "csv_sha256": entry["forces_csv_sha256"]}
        except Exception as err:  # noqa: BLE001
            failures.append(f"state {name}: {err}")
    return failures, states


def analyze(out: Path, freeze: dict, inventory: dict | None = None, formal: dict | None = None) -> dict:
    inventory = inventory if inventory is not None else jload(E / "inventory.json")
    formal = formal if formal is not None else jload(FORMAL_CRITERIA)
    report: dict = {"kind": "lowdim02a_flow32_cross_grid_analysis", "selected_delta": None, "grad03_verdict": None, "no_gradient_claim": True, "not_grid01": True, "not_opt01": True,
                    "fd08_verdict_unchanged": True, "reinitialization": "none", "qualification_flags": {k: False for k in FLAGS}}
    failures: list[str] = []
    for name, path in (("analyzer", Path(__file__)), ("contract", ROOT / "src/cfd_sdf/lowdim02a_contract.py"), ("step01_states_module", ROOT / "scripts/step01_states.py"),
                       ("force_io", ROOT / "scripts/fd08_v2_campaign_io.py"), ("formal_criteria", FORMAL_CRITERIA), ("job", ROOT / "scripts/waterlily_lowdim02_flow32_job.jl"),
                       ("lowdim01_analysis", LOWDIM01_ANALYSIS)):
        if sha256(path) != freeze["file_hashes"].get(name):
            failures.append(f"{name} differs from (or is missing in) the freeze")
    if hashlib.sha256((json.dumps(inventory, sort_keys=True, indent=2) + "\n").encode()).hexdigest() != freeze["file_hashes"].get("inventory_canonical_json"):
        failures.append("the inventory differs from the frozen inventory")
    f, res = check_kernel(out, freeze, inventory, flow32_criteria(formal))
    failures += f
    ref = inventory["flow32_baseline_reference"]
    base = res.get(NAMES["base"])
    if not base:
        failures.append("no baseline")
    else:
        if base["csv_sha256"] != ref["forces_csv_sha256"]:
            failures.append("the baseline force CSV differs from the W4 v17 round-2 flow_32 baseline")
        for q in ("drag_n", "downforce_n"):
            if not rel(base[q], ref["host_recomputed_n"][q]) <= BASELINE_REL:
                failures.append(f"baseline {q} differs from the W4 v17 round-2 flow_32 baseline")
    report["integrity"] = {"pass": not failures, "failures": failures}
    if failures:
        report["verdict"] = "STAGE_A_INCOMPLETE"
        return report
    try:
        report.update(decide(res, inventory))
    except Exception as err:  # noqa: BLE001  a computation failure after the gates is never a recorded verdict
        report["integrity"] = {"pass": False, "failures": [f"analysis error: {type(err).__name__}: {err}"]}
        report["verdict"] = "STAGE_A_INCOMPLETE"
    return report


GATE_KEYS = {"clearance", "masks_and_support_preserved", "cell_components_equal_baseline", "smoothed_volume_band", "eikonal_median_within_limit"}


def decide(res: dict, inventory: dict) -> dict:
    rows = {r["name"]: r for r in inventory["states"]}
    g = rows[NAMES["plus"]]["geometry_gates"]
    if set(g["gates"]) != GATE_KEYS or g["all_hard_gates_pass"] is not all(g["gates"].values()):
        raise ValueError("the registered geometry gates are inconsistent")
    r = {k: {"downforce_n": res[n]["downforce_n"], "drag_n": res[n]["drag_n"]} for k, n in NAMES.items()}
    v = C.stage_a_verdict(r["base"], r["repeat"], r["plus"], r["minus"], g["all_hard_gates_pass"])
    ref24 = inventory["flow24_reference_lowdim01"]
    res_df = v["downforce_resolution_n"]
    base32, base24 = r["base"]["downforce_n"], ref24["baseline"]["downforce_n"]
    d32 = {"+1.25": r["plus"]["downforce_n"] - base32, "-1.25": r["minus"]["downforce_n"] - base32, "+2.5": r["plus25"]["downforce_n"] - base32}
    dr32 = {"+1.25": r["plus"]["drag_n"] - r["base"]["drag_n"], "-1.25": r["minus"]["drag_n"] - r["base"]["drag_n"], "+2.5": r["plus25"]["drag_n"] - r["base"]["drag_n"]}
    d24 = ref24["downforce_change_n"]
    odd32, even32 = (d32["+1.25"] - d32["-1.25"]) / 2.0, (d32["+1.25"] + d32["-1.25"]) / 2.0
    odd24, even24 = (d24["+1.25"] - d24["-1.25"]) / 2.0, (d24["+1.25"] + d24["-1.25"]) / 2.0
    sign = lambda x: (x > 0) if abs(x) > res_df else None  # noqa: E731  a sign is reported only when the change is resolved on flow_32
    desc = {"downforce_change_n": {"flow_32": d32, "flow_24_lowdim01": d24},
            "downforce_change_relative_to_own_baseline": {"flow_32": {k: x / base32 for k, x in d32.items()}, "flow_24_lowdim01": {k: x / base24 for k, x in d24.items()}},
            "drag_change_n": {"flow_32": dr32, "flow_24_lowdim01": ref24["drag_change_n"]},
            "resolved_sign_positive_on_flow32": {"+1.25": sign(d32["+1.25"]), "-1.25": sign(d32["-1.25"])},
            "resolved_sign_positive_on_flow24": {"+1.25": d24["+1.25"] > 0, "-1.25": d24["-1.25"] > 0},
            "flow32_over_flow24_downforce_change": {k: (d32[k] / d24[k] if d24[k] else None) for k in ("+1.25", "-1.25")},
            "odd_part_n": {"flow_32": odd32, "flow_24_lowdim01": odd24, "flow32_over_flow24": odd32 / odd24 if odd24 else None},
            "even_part_n": {"flow_32": even32, "flow_24_lowdim01": even24, "flow32_over_flow24": even32 / even24 if even24 else None},
            "baseline_downforce_n": {"flow_32": base32, "flow_24": base24, "relative_difference": base32 / base24 - 1.0},
            "plus_2p5_mm_flow_32_n": d32["+2.5"], "plus_2p5_mm_flow_24_n_barely_resolved_on_flow_24": d24["+2.5"],
            "baseline_repeat_forces_csv_byte_identical": res[NAMES["repeat"]]["csv_sha256"] == res[NAMES["base"]]["csv_sha256"],
            "note": "descriptive only; the +2.5 mm state is not part of the verdict and its flow_24 value is barely resolved, so no ratio or sign comparison is made for it"}
    identical = desc["baseline_repeat_forces_csv_byte_identical"]
    return {"verdict": v.pop("verdict"), "stage_a": v, "flow_32": r, "descriptive_comparison_with_flow_24": desc,
            "rules": {"min_resolved_n": C.MIN_RESOLVED_N, "noise_factor": C.NOISE_FACTOR, "authority": "actual primal responses (host-recomputed, flow_32 scale); the geometry gates are those of the same LOWDIM-01 state"},
            "interpretation": INTERPRETATION + (REPEAT_IDENTICAL if identical else REPEAT_DIFFERENT)}


INTERPRETATION = ("Stage A compares the sign of the LOWDIM-01 accepted +1.25 mm step on flow_32 with flow_24 (one direction, one step, the [80,120] tU/L time-weighted force, Float32 T4 runs, no "
                  "reinitialization). The downforce change of a step is odd + even (curvature) part; a PASS only means the sign survived at this one step and grid with the reverse control losing, "
                  "and a SIGN_FLIP only means the step lost downforce (the cause is read from the reported odd/even parts, not asserted). It is a bounded cross-grid sign check, not GRID-01 (#26), "
                  "not a grid-converged or physical downforce, not a gradient qualification and not OPT-01 (#30); a PASS only permits pre-registering Stage B, it does not authorise it. ")
REPEAT_IDENTICAL = ("The baseline repeat was byte-identical, so it gives no flow_32 noise evidence and the resolution stays at the nominal floor (10 x the flow_24 nominal sigma0 = 3e-5 N), "
                    "against a flow_32 half-window drift of about 1e-5 N.")
REPEAT_DIFFERENT = "The baseline repeat differed; the resolution includes 10 x its downforce difference (resolution_source says whether it binds)."


def clean(x):
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kernel-dir", required=True, type=Path)
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--write", type=Path)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    freeze = jload(args.freeze)
    report = analyze(args.kernel_dir, freeze)
    report["provenance"] = {"freeze_sha256": sha256(args.freeze), "analyzer_sha256": sha256(Path(__file__)), "source_commit": freeze["source_commit"],
                            "kernel_manifest_sha256": sha256(args.kernel_dir / "output_manifest.json") if (args.kernel_dir / "output_manifest.json").is_file() else None}
    if args.check:
        print(json.dumps(clean({"integrity": report["integrity"], "verdict": report["verdict"]}), indent=2, sort_keys=True))
        return
    if args.write is None:
        sys.exit("--write is required unless --check")
    if args.write.exists():
        sys.exit("refusing to overwrite an existing analysis (the analyzer runs once)")
    data = json.dumps(clean(report), indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(report["verdict"], hashlib.sha256(data.encode()).hexdigest())
    if report["verdict"] == "STAGE_A_INCOMPLETE":
        sys.exit(3)


if __name__ == "__main__":
    main()
