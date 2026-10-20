#!/usr/bin/env python3
"""Local OpenFOAM environment gate LOCAL-OF-01: compare the local Docker runs with the Kaggle CPU references
(registration docs/local_openfoam_env_gate_2026_10_20.md, section 5; this file is frozen with it).

  local_openfoam_gate.py --runs RUNS --u3-kaggle DIR --u3-kaggle-raw DIR --out FILE

RUNS holds the registered runs (scripts/local_openfoam.py run), each with its local_run.json and the runner's DONE:
  t20c_smoke2_a/t20c, t20c_smoke2_b/t20c     the T2-0c smoke-2 runner replayed unchanged, twice
  t20b_a, t20b_b (t20b_c, t20b_d)/subset_t20b   the T2-0b wf runner's own run_case for T20B_CASES (extra replicates only under section 6)
  x3_a, x3_b/subset_x3                        the XFID X3 formal runner's own run_case for X3_CASES, twice
  u3_smoke_a, u3_smoke_b/openfoam_xfid_gridphase_x3   the UNC-01 U3 smoke runner replayed unchanged, twice (raw; read only by the blinded U4)
  u3_smoke_a_sanitized/openfoam_xfid_gridphase_x3     run a sanitised by scripts/unc01_u3_prepare.py strip-smoke
A run directory named NAME.attempt2 replaces NAME only when NAME is an infrastructure loss (section 6). --u3-kaggle is the sanitised Kaggle U3 smoke
archive (M2), --u3-kaggle-raw its unsanitised original; raw U3 outputs are read only by u3_forces_blinded, which returns no force value.
FILE is created exclusively; every invocation is appended to gate_ledger.jsonl next to the freeze record.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import math
import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/evidence/local_openfoam_env_2026_10_20"
FREEZE = EVID / "freeze.json"
LEDGER = EVID / "gate_ledger.jsonl"
REF_T20C = EVID / "reference/t20c_smoke2"
REF_T20B = ROOT / "docs/evidence/t20b_registered_2026_10_19/kernel_wf_run1/t20b"
REF_X3 = ROOT / "docs/evidence/xfid_gridphase_x3_2026_10_04/formal_result"

T20C_EXCLUDED = {"sa-wf_h0.09_coa30_da0_mesh"}   # the geometry of the pre-freeze generator probe (section 3)
T20B_UNSTEADY = "sa-wf_h0.09_fine30_da+1"         # T2-0b's one unsteady wall-function case (raw tail Cl rel. std 1.9 %)
T20B_CASES = ["sa-wf_h0.224_fine30_da-1", "sa-wf_h0.224_fine30_da+1", "sa-wf_h0.134_med30_da-0.25", "sa-wf_h0.134_med30_da+0.25", T20B_UNSTEADY]
T_MEAN_FRAC, T_STD_REL = 0.1, 0.10                 # same mesh file, not bitwise: |delta Cl tail mean| <= 0.1 Kaggle tail std; tail std within 10 %
T_SPREAD_SCALE = 0.1 * 0.0022821764566427556       # variant-spread label scale: 0.1 x T2-0b G6 sigma_mesh at h/c 0.224
X3_STATES = ["baseline", "D0_interface_offset_minus", "D0_interface_offset_plus", "D1_filtered_seed11_minus", "D1_filtered_seed11_plus",
             "D2_filtered_seed2026_minus", "D2_filtered_seed2026_plus"]
X3_DIRECTIONS = ["D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026"]
X3_SHIFTS = ["17p", "17m"]                          # the first mirror pair of the X3 formal case order (Halton index 17)
X3_CASES = [f"frm_{s}_{k}" for k in X3_SHIFTS for s in X3_STATES]
RESP = ("drag_n", "downforce_n")
SIGMA_U = {"drag_n": 0.0002009583555024794, "downforce_n": 0.0005762593367372587}   # X3 formal pooled per-case residual std
SE_U = {"drag_n": 2.5119794437809924e-05, "downforce_n": 7.203241709215734e-05}     # X3 formal SE of a 32-phase contrast
FLOOR_U = {"drag_n": 3.9375e-05, "downforce_n": 0.00022275000000000002}             # X3 formal calibration floor
TOL_U_CASE = {r: 0.1 * SIGMA_U[r] for r in RESP}
TOL_U_BIAS = {r: 0.1 * FLOOR_U[r] for r in RESP}
TOL_U_CONTRAST = {r: 0.1 * max(3 * SE_U[r], FLOOR_U[r]) for r in RESP}
U3_PARENT = "u3_v18__parent_33p"
REL, ABS = 1e-6, 1e-12
TIMING = {"generator_wall_s", "total_wall_s", "pre_solver_wall_s", "wall_s", "elapsed_s", "child_user_s", "child_sys_s", "peak_rss_mb_sampled",
          "refinement_block_raw"}   # the raw snappy log block carries "Wrote mesh in = 0.11 s." lines; its parsed cell counts are compared
DESCRIPTIVE_T20C = {"solver", "solver_cont", "yplus", "yplus_returncode", "residual_converged", "forces", "continued_to", "deadline_limited"}
MESH_SHA = {"mesh_msh_sha256", "base_mesh_msh_sha256", "topology", "base_topology"}   # gmsh is not run-to-run deterministic (section 3)
INT_STR = re.compile(r"^-?\d+$")


class Missing(Exception):
    """A required run or reference is absent or is an infrastructure loss (section 6): the part is INCOMPLETE, not FAIL."""


def load(path: Path):
    path = Path(path)
    if not path.is_file():
        raise Missing(f"missing {path}")
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def coefficient_text(case_dir: Path) -> str | None:
    hits = sorted(Path(case_dir).rglob("coefficient.dat.gz"))
    return gzip.decompress(hits[0].read_bytes()).decode() if hits else None


def coefficient_rows(text: str) -> list[dict]:
    header, rows = None, []
    for line in text.splitlines():
        if line.startswith("#"):
            header = line.lstrip("#").split()
        elif line.strip():
            rows.append(dict(zip(header, map(float, line.split()))))
    return rows


def mean_std(v: list[float]) -> tuple[float, float]:
    m = math.fsum(v) / len(v)
    return m, math.sqrt(math.fsum((x - m) ** 2 for x in v) / len(v))


def t20b_recompute(text: str) -> dict:
    """T2-0b force_summary tail (last 20 %, at least 50 rows) recomputed independently from one coefficient.dat (no continuation)."""
    rows = coefficient_rows(text)
    n = min(len(rows), max(50, math.ceil(len(rows) * 0.2)))
    cl, cd = mean_std([r["Cl"] for r in rows[-n:]]), mean_std([r["Cd"] for r in rows[-n:]])
    return {"Cl_tail_mean": cl[0], "Cl_tail_std": cl[1], "Cd_tail_mean": cd[0]}


def x3_recompute(text: str) -> dict:
    """X3 force_window (last 25 %, at least 20 rows; 0.32 N per coefficient; downforce = -Cl) recomputed independently from coefficient.dat."""
    rows = coefficient_rows(text)
    n = max(20, math.ceil(len(rows) * 0.25))
    return {"drag_n": mean_std([0.32 * r["Cd"] for r in rows[-n:]])[0], "downforce_n": mean_std([-0.32 * r["Cl"] for r in rows[-n:]])[0]}


def close(a: float, b: float, rel: float = 1e-9) -> bool:
    return abs(a - b) <= max(rel * max(abs(a), abs(b)), ABS)


def _num(x):
    if isinstance(x, bool) or (isinstance(x, str) and (len(x) == 64 or INT_STR.match(x))):   # hashes, ids and integer strings compare exactly
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def same(a, b) -> bool:
    """Integers, booleans, hashes, integer strings and other strings: exact. Floats and decimal strings: relative REL with an absolute floor ABS."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    fa, fb = _num(a), _num(b)
    if fa is not None and fb is not None and not (isinstance(a, str) and isinstance(b, str) and a == b):
        return math.isfinite(fa) and math.isfinite(fb) and abs(fa - fb) <= max(REL * max(abs(fa), abs(fb)), ABS)
    return a == b


def diff_keys(a, b, prefix="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += diff_keys(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{prefix}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff_keys(x, y, f"{prefix}[{i}]")]
    return [] if same(a, b) else [prefix or "."]


def strip_timing(x):
    if isinstance(x, dict):
        return {k: strip_timing(v) for k, v in x.items() if k not in TIMING}
    if isinstance(x, list):
        return [strip_timing(v) for v in x]
    return x


def drop(x, keys):
    if isinstance(x, dict):
        return {k: drop(v, keys) for k, v in x.items() if k not in keys}
    if isinstance(x, list):
        return [drop(v, keys) for v in x]
    return x


def cases_by_id(result_path: Path) -> dict:
    return {c["id"]: c for c in load(result_path)["cases"]}


def peak_rss(cases) -> float | None:
    vals = [s.get("peak_rss_mb_sampled") or 0 for c in cases for s in c.get("stages", [])]
    return max(vals) if vals else None


def failed(p) -> bool:
    return isinstance(p, dict) and ("incomplete" in p or "error" in p)


# ---- what ran (section 6: a run counts only with its wrapper record, the frozen identities and the runner's DONE) ------------------------------

def run_dir(runs: Path, name: str, sub: str, kind: str, freeze: dict) -> Path:
    """The authoritative attempt of run NAME: NAME, or NAME.attempt2 when NAME is an infrastructure loss. Raises Missing otherwise."""
    reasons = []
    for cand in (runs / name, runs / f"{name}.attempt2"):
        try:
            rec = load(cand / "local_run.json")
            args = rec["docker_args"]
            checks = (("returncode", rec["returncode"] == 0), ("image_id", rec["image_id"] == freeze["image_id"]),
                      ("lock_sha256", rec["lock_sha256"] == freeze["lock_sha256"]),
                      ("script_sha256", rec["script_sha256"] in freeze["script_sha256_allowed"]),
                      ("runner_sha256", rec["runner_sha256"] == freeze["runner_sha256"][kind]),
                      ("dpkg_after_matches_lock", rec.get("dpkg_after_matches_lock") is True),
                      ("cpus", args[args.index("--cpus") + 1] == freeze["cpus"][kind]), ("memory", args[args.index("--memory") + 1] == "8g"))
            bad = [k for k, ok in checks if not ok]
            if bad:
                raise Missing(f"{cand.name}: wrapper record differs from the freeze: {bad}")
            if not (cand / sub / "DONE").is_file():
                raise Missing(f"{cand.name}: no DONE")
            return cand / sub
        except Missing as exc:
            reasons.append(str(exc))
    raise Missing("; ".join(reasons))


# ---- T family (T2-0c / T2-0b pipeline) ---------------------------------------------------------------------------

def t20c_mesh_replay(local: Path, ref: Path) -> dict:
    """T1: every Kaggle smoke-2 geometry (minus the probe): the record without timings, mesh-file/topology hashes and descriptive solver fields
    agrees; solver paths with an identical mesh file: last initial residuals within REL 1e-3 (bitwise expected)."""
    rows, mismatches, desc = {}, [], {"solver_paths": 0, "same_mesh": 0, "same_mesh_solver_fields_identical": 0, "differing": []}
    ref_ids = {p.parent.name for p in (ref / "cases").glob("*/case_result.json")}
    for cid in sorted(ref_ids - T20C_EXCLUDED):
        k = strip_timing(load(ref / "cases" / cid / "case_result.json"))
        lf = local / "cases" / cid / "case_result.json"
        if not lf.is_file():
            mismatches.append({"id": cid, "keys": ["<missing locally>"]})
            continue
        l = strip_timing(load(lf))
        keys = diff_keys(drop({x: v for x, v in k.items() if x not in DESCRIPTIVE_T20C}, MESH_SHA),
                         drop({x: v for x, v in l.items() if x not in DESCRIPTIVE_T20C}, MESH_SHA))
        rows[cid] = {"agrees": not keys, "mesh_sha_identical": k.get("mesh_msh_sha256") == l.get("mesh_msh_sha256")}
        if k.get("status") == "COMPLETED":
            desc["solver_paths"] += 1
            same_mesh = rows[cid]["mesh_sha_identical"]
            dk = sorted(x for x in DESCRIPTIVE_T20C - {"forces"} if k.get(x) != l.get(x))
            desc["same_mesh"] += same_mesh
            desc["same_mesh_solver_fields_identical"] += same_mesh and not dk
            if dk:
                desc["differing"].append({"id": cid, "keys": dk, "same_mesh_file": same_mesh})
            if same_mesh and any(v is not None and not close(float(v), float((l.get(s) or {}).get("last_initial_residuals", {}).get(f) or "nan"), 1e-3)
                                 for s in ("solver", "solver_cont") if k.get(s) for f, v in k[s]["last_initial_residuals"].items()):
                keys.append(".solver residuals beyond REL 1e-3 on an identical mesh file")
                rows[cid]["agrees"] = False
        if keys:
            mismatches.append({"id": cid, "keys": keys})
    extra = sorted({p.parent.name for p in (local / "cases").glob("*/case_result.json")} - ref_ids)
    kb, lb = strip_timing(load(ref / "bases.json")), strip_timing(load(local / "bases.json"))
    bases = diff_keys(drop(kb, MESH_SHA), drop(lb, MESH_SHA))
    done_k, done_l = load(ref / "DONE"), load(local / "DONE")
    return {"compared": len(rows), "agree": sum(r["agrees"] for r in rows.values()), "mesh_sha_identical": sum(r["mesh_sha_identical"] for r in rows.values()),
            "bases_mesh_sha_identical": sum(x.get("mesh_msh_sha256") == y.get("mesh_msh_sha256") for x, y in zip(kb, lb)), "bases": len(kb),
            "mismatches": mismatches, "extra_local_ids": extra, "bases_json_differing_keys": bases,
            "status_counts": {"kaggle": done_k["status_counts"], "local": done_l["status_counts"]}, "solver_paths_descriptive": desc,
            "pass": bool(rows) and not mismatches and not extra and not bases and done_k["status_counts"] == done_l["status_counts"]}


def t20c_determinism(a: Path, b: Path) -> dict:
    """T2 part: the two local smoke replays; every solver path whose mesh file is identical in both has identical solver, continuation and y+ blocks."""
    out = []
    for f in sorted((a / "cases").glob("*_smoke/case_result.json")):
        ra, rb = load(f), load(b / "cases" / f.parent.name / "case_result.json")
        if ra.get("mesh_msh_sha256") == rb.get("mesh_msh_sha256"):
            out.append({"id": f.parent.name, "identical": all(ra.get(x) == rb.get(x) for x in ("solver", "solver_cont", "yplus", "status"))})
    return {"same_mesh_solver_paths": out, "pass": all(r["identical"] for r in out)}


def t20b_manifest(case_dir: Path) -> dict:
    return json.loads(gzip.decompress((case_dir / "case_manifest.json.gz").read_bytes()))


def t20b_side(rec: dict, case_dir: Path) -> dict:
    coef = coefficient_text(case_dir) if rec["status"] == "COMPLETED" else None
    side = {"rec": rec, "mesh": t20b_manifest(case_dir)["mesh_msh_sha256"] if coef is not None else None, "coef": coef, "record_consistent": False}
    if coef is not None and not rec.get("continued_to"):   # the runner's tail statistics must match an independent recomputation from coefficient.dat
        rc, f = t20b_recompute(coef), rec["forces"]
        side["record_consistent"] = (close(rc["Cl_tail_mean"], f["Cl"]["tail_mean"]) and close(rc["Cl_tail_std"], f["Cl"]["tail_std"], 1e-6)
                                     and close(rc["Cd_tail_mean"], f["Cd"]["tail_mean"]))
    return side


def t20b_forces(local_dirs: dict, ref: Path) -> tuple[dict, dict, dict]:
    """T2 (local pairs with the same mesh file: byte-identical coefficient.dat), T3 (local-Kaggle pairs with the same mesh file: bitwise, or the
    same-mesh tolerance of section 5), and the descriptive generator-variant spread."""
    kag = cases_by_id(ref / "result.json")
    local = {n: cases_by_id(d / "result.json") for n, d in local_dirs.items()}
    det_pairs, env_pairs, variant_pairs, rows = [], [], [], {}
    names = sorted(local)
    for cid in T20B_CASES:
        ks = t20b_side(kag[cid], ref / "cases" / cid)
        sides = {}
        for n in names:
            rec = local[n].get(cid)
            if rec is None:
                raise Missing(f"{n}: no record for {cid}")
            sides[n] = l = t20b_side(rec, local_dirs[n] / "cases" / cid)
            ok = rec["status"] == "COMPLETED" and not rec.get("deadline_limited") and l["record_consistent"] and ks["record_consistent"]
            agree = ok and kag[cid]["mesh_cells_3d"] == rec["mesh_cells_3d"] and not diff_keys(strip_timing(kag[cid]["check_mesh"]), strip_timing(rec["check_mesh"]))
            rows[f"{n}:{cid}"] = {"completed_consistent": ok, "cells_and_check_mesh_agree": agree, "mesh_identical_to_kaggle": ok and l["mesh"] == ks["mesh"],
                                  "status": rec["status"], "wall_s_local": rec.get("total_wall_s"), "wall_s_kaggle": kag[cid].get("total_wall_s"),
                                  "cells": rec.get("mesh_cells_3d"), "peak_rss_mb": peak_rss([rec])}
            if not ok:
                continue
            kf, lf = kag[cid]["forces"], rec["forces"]
            row = {"case": cid, "run": n, "d_cl_tail_mean": lf["Cl"]["tail_mean"] - kf["Cl"]["tail_mean"],
                   "d_cd_tail_mean": lf["Cd"]["tail_mean"] - kf["Cd"]["tail_mean"],
                   "cl_tail_std": {"kaggle": kf["Cl"]["tail_std"], "local": lf["Cl"]["tail_std"]},
                   "unsteady_class": {"kaggle": kf["Cl"]["tail_rel_std"] > 0.005, "local": lf["Cl"]["tail_rel_std"] > 0.005}}
            if l["mesh"] == ks["mesh"]:
                row["coefficient_dat_bitwise"] = l["coef"] == ks["coef"]
                flags = (all(kf.get(x) == lf.get(x) for x in ("cl_plateau", "force_plateau", "rows")) and kag[cid].get("continued_to") == rec.get("continued_to")
                         and kag[cid]["solver"]["iterations"] == rec["solver"]["iterations"] and row["unsteady_class"]["kaggle"] == row["unsteady_class"]["local"])
                ratio = lf["Cl"]["tail_std"] / kf["Cl"]["tail_std"] if kf["Cl"]["tail_std"] else None
                row["tolerance"] = {"mean": T_MEAN_FRAC * kf["Cl"]["tail_std"], "flags_and_iterations_equal": flags, "tail_std_ratio": ratio}
                row["pass"] = row["coefficient_dat_bitwise"] or (flags and abs(row["d_cl_tail_mean"]) <= row["tolerance"]["mean"]
                                                                 and ratio is not None and abs(ratio - 1) <= T_STD_REL)
                env_pairs.append(row)
            else:
                variant_pairs.append({**row, "pair": "local-kaggle"})
        for i, n in enumerate(names):
            for m in names[i + 1:]:
                a, b = sides[n], sides[m]
                if a["coef"] is None or b["coef"] is None:
                    continue
                d = b["rec"]["forces"]["Cl"]["tail_mean"] - a["rec"]["forces"]["Cl"]["tail_mean"]
                if a["mesh"] == b["mesh"]:
                    det_pairs.append({"case": cid, "runs": [n, m], "coefficient_dat_identical": a["coef"] == b["coef"], "d_cl_tail_mean": d})
                else:
                    variant_pairs.append({"case": cid, "runs": [n, m], "pair": "local-local", "d_cl_tail_mean": d})
    complete = all(r["completed_consistent"] for r in rows.values())
    env_cases = sorted({r["case"] for r in env_pairs})
    det = {"pairs": det_pairs, "runs": names, "enough_pairs": len(det_pairs) >= 1,
           "pass": complete and len(det_pairs) >= 1 and all(p["coefficient_dat_identical"] for p in det_pairs)}
    force = {"pairs_same_mesh_as_kaggle": env_pairs, "cases_with_same_mesh_pair": env_cases, "rows": rows, "enough_pairs": len(env_cases) >= 2,
             "bitwise": bool(env_pairs) and all(r["coefficient_dat_bitwise"] for r in env_pairs),
             "max_abs_d_cl_same_mesh": max((abs(r["d_cl_tail_mean"]) for r in env_pairs), default=None),
             "pass": complete and len(env_cases) >= 2 and all(r["pass"] for r in env_pairs) and all(r["cells_and_check_mesh_agree"] for r in rows.values())}
    steady = [abs(r["d_cl_tail_mean"]) for r in variant_pairs if r["case"] != T20B_UNSTEADY]
    spread = max(steady, default=None)
    variants = {"pairs": variant_pairs, "max_abs_d_cl_steady_cases": spread, "scale": T_SPREAD_SCALE,
                "label": None if spread is None else ("VARIANT_SPREAD_WITHIN_SCALE" if spread <= T_SPREAD_SCALE else "VARIANT_SPREAD_ABOVE_SCALE")}
    return det, force, variants


def kaggle_self_consistency(ref_t20b: Path, ref_t20c: Path) -> dict:
    """Descriptive: mesh-file SHA-256 of the same geometry in two Kaggle sessions (T2-0b wf 2026-10-19 vs T2-0c smoke 2 2026-10-20)."""
    out = {}
    for d in sorted((ref_t20b / "cases").iterdir()):
        s = ref_t20c / "cases" / f"{d.name}_mesh" / "case_result.json"
        if d.name.startswith("sa-wf") and s.is_file():
            out[d.name] = t20b_manifest(d)["mesh_msh_sha256"] == load(s)["mesh_msh_sha256"]
    return {"geometries": len(out), "identical": sum(out.values()), "differing": sorted(k for k, v in out.items() if not v)}


# ---- U family (U3 / XFID X3 pipeline) ----------------------------------------------------------------------------

MESH_FIELDS = ("status", "stl_sha256", "triangles", "mesh", "snappy")


def x3_value(rec: dict, case_dir: Path) -> dict:
    """Window means of one X3-type case, checked against an independent recomputation from its coefficient.dat."""
    rc = x3_recompute(coefficient_text(case_dir))
    if not all(close(rc[r], rec["forces"][r]["window_mean"]) for r in RESP):
        raise ValueError(f"{case_dir.name}: runner window means differ from the recomputation")
    return {r: rec["forces"][r]["window_mean"] for r in RESP}


def contrast_checks(val: dict, cases: list[str], pairs: dict) -> dict:
    """Signed mean bias over the cases and the local-minus-Kaggle discrepancy of every difference; val[side][case][response]."""
    bias = {r: math.fsum(val["local"][c][r] - val["kaggle"][c][r] for c in cases) / len(cases) for r in RESP}
    disc = {}
    for name, (plus, minus, half) in pairs.items():
        f = 0.5 if half else 1.0
        for r in RESP:
            disc[f"{r}:{name}"] = f * (val["local"][plus][r] - val["local"][minus][r]) - f * (val["kaggle"][plus][r] - val["kaggle"][minus][r])
    return {"mean_bias": bias, "bias_within": {r: abs(bias[r]) <= TOL_U_BIAS[r] for r in RESP}, "difference_discrepancy": disc,
            "differences_within": all(abs(v) <= TOL_U_CONTRAST[k.split(":")[0]] for k, v in disc.items())}


def x3_forces(a: Path, b: Path, ref: Path) -> tuple[dict, dict]:
    ka, la, lb = cases_by_id(ref / "result.json"), cases_by_id(a / "result.json"), cases_by_id(b / "result.json")
    det, rows, val = {}, {}, {"kaggle": {}, "local": {}}
    for cid in X3_CASES:
        if cid not in la or cid not in lb:
            raise Missing(f"no local record for {cid}")
        k, l = ka[cid], la[cid]
        done = k["status"] == l["status"] == lb[cid]["status"] == "COMPLETED"
        ca, cb = coefficient_text(a / "cases" / cid), coefficient_text(b / "cases" / cid)
        det[cid] = {"completed_both": done, "coefficient_dat_identical": ca is not None and ca == cb}
        if not done:
            rows[cid] = {"pass": False, "status_local": l["status"]}
            continue
        val["kaggle"][cid], val["local"][cid] = x3_value(k, ref / "cases" / cid), x3_value(l, a / "cases" / cid)
        keys = diff_keys({f: strip_timing(k.get(f)) for f in MESH_FIELDS}, {f: strip_timing(l.get(f)) for f in MESH_FIELDS})
        d = {r: val["local"][cid][r] - val["kaggle"][cid][r] for r in RESP}
        rows[cid] = {"mesh_fields_differing": keys, "coefficient_dat_bitwise": ca == coefficient_text(ref / "cases" / cid), "difference": d,
                     "within_tol": {r: abs(d[r]) <= TOL_U_CASE[r] for r in RESP},
                     "solver_identical": strip_timing(k.get("solver")) == strip_timing(l.get("solver")),
                     "wall_s_local": l.get("total_wall_s"), "wall_s_kaggle": k.get("total_wall_s"), "peak_rss_mb": peak_rss([l])}
        rows[cid]["pass"] = not keys and all(rows[cid]["within_tol"].values())
    out = {"cases": rows, "tolerance_case": TOL_U_CASE, "tolerance_bias": TOL_U_BIAS, "tolerance_contrast": TOL_U_CONTRAST,
           "bitwise": all(r.get("coefficient_dat_bitwise") for r in rows.values()), "pass": False}
    if all(r["pass"] for r in rows.values()):
        pairs = {}
        for j in X3_SHIFTS:
            pairs.update({f"{s}-baseline:{j}": (f"frm_{s}_{j}", f"frm_baseline_{j}", False) for s in X3_STATES[1:]})
            pairs.update({f"{d}(plus-minus)/2:{j}": (f"frm_{d}_plus_{j}", f"frm_{d}_minus_{j}", True) for d in X3_DIRECTIONS})
        out.update(contrast_checks(val, X3_CASES, pairs))
        out["pair_mean_contrasts"] = {}
        for r in RESP:   # mirror-pair mean of each direction contrast next to the X3 formal SE (X3 values are public)
            for d in X3_DIRECTIONS:
                c = {s: math.fsum((val[s][f"frm_{d}_plus_{j}"][r] - val[s][f"frm_{d}_minus_{j}"][r]) / 2 for j in X3_SHIFTS) / 2 for s in val}
                out["pair_mean_contrasts"][f"{r}:{d}"] = {**c, "discrepancy": c["local"] - c["kaggle"], "se_32_phase": SE_U[r]}
                out["differences_within"] = out["differences_within"] and abs(c["local"] - c["kaggle"]) <= TOL_U_CONTRAST[r]
        out["pass"] = all(out["bias_within"].values()) and out["differences_within"]
    return {"cases": det, "pass": all(d["completed_both"] and d["coefficient_dat_identical"] for d in det.values())}, out


def sanitised_records(root: Path) -> dict:
    """The one result.json of a sanitised U3 smoke archive, refusing any force field or force file (UNC-01 blinding)."""
    results = sorted(Path(root).rglob("result.json"))
    if len(results) != 1 or not any(Path(root).rglob("EXCLUDED_SHA256.json")):
        raise Missing(f"{root}: expected exactly one result.json and an EXCLUDED_SHA256.json")
    if any(Path(root).rglob("coefficient.dat*")) or any(Path(root).rglob("log.simpleFoam*")):
        raise ValueError(f"{root}: force files present in a sanitised archive")
    recs = cases_by_id(results[0])
    if any("forces" in c for c in recs.values()):
        raise ValueError(f"{root}: force fields present in a sanitised archive")
    return recs


def u3_mesh_replay(local: Path, ref: Path) -> dict:
    """U3: sanitised v18 smoke: statuses, stage return codes, STL hashes, mesh and snappy statistics agree; solver blocks compared descriptively."""
    k, l = sanitised_records(ref), sanitised_records(local)
    rows = {}
    for cid, kc in k.items():
        lc = l.get(cid)
        f = (*MESH_FIELDS, "stages")
        keys = ["<missing locally>"] if lc is None else diff_keys({x: strip_timing(kc.get(x)) for x in f}, {x: strip_timing(lc.get(x)) for x in f})
        rows[cid] = {"agrees": not keys, "differing": keys, "solver_identical": lc is not None and strip_timing(kc.get("solver")) == strip_timing(lc.get("solver"))}
    env = next(Path(ref).rglob("environment.json"), None)
    codename = (json.loads(env.read_text()).get("os_release") or {}).get("VERSION_CODENAME") if env else None
    return {"compared": len(rows), "cases": rows, "extra_local_ids": sorted(set(l) - set(k)), "kaggle_os_codename": codename,
            "pass": bool(rows) and all(r["agrees"] for r in rows.values()) and not set(l) - set(k)}


def u3_forces_blinded(local_a: Path, local_b: Path, kaggle_raw: Path) -> dict:
    """U4: the 8 v18 smoke cases with forces, blinded. Only local-minus-Kaggle discrepancies, byte identities and pass flags leave this function;
    no force value and no state difference is returned (UNC-01 keeps v18 forces out of every record)."""
    k = cases_by_id(next(Path(kaggle_raw).rglob("result.json")))
    la, lb = cases_by_id(local_a / "result.json"), cases_by_id(local_b / "result.json")
    rows, val, ok = {}, {"kaggle": {}, "local": {}}, True
    for cid in sorted(k):
        if cid not in la or cid not in lb:
            raise Missing(f"no local record for {cid}")
        if not k[cid]["status"] == la[cid]["status"] == lb[cid]["status"] == "COMPLETED":
            rows[cid], ok = {"completed": False}, False
            continue
        kdir = next(Path(kaggle_raw).rglob(f"cases/{cid}"))
        ck, ca, cb = coefficient_text(kdir), coefficient_text(local_a / "cases" / cid), coefficient_text(local_b / "cases" / cid)
        val["kaggle"][cid], val["local"][cid] = x3_value(k[cid], kdir), x3_value(la[cid], local_a / "cases" / cid)
        d = {r: abs(val["local"][cid][r] - val["kaggle"][cid][r]) for r in RESP}
        rows[cid] = {"completed": True, "abs_discrepancy": d, "within_tol": all(d[r] <= TOL_U_CASE[r] for r in RESP),
                     "coefficient_dat_bitwise": ck == ca, "local_runs_identical": ca == cb}
        ok &= rows[cid]["within_tol"]
    out = {"cases": rows, "bitwise": bool(rows) and all(r.get("coefficient_dat_bitwise") for r in rows.values()),
           "determinism_pass": bool(rows) and all(r.get("local_runs_identical") for r in rows.values()), "pass": False}
    if ok and U3_PARENT in val["local"]:
        c = contrast_checks(val, sorted(val["local"]), {cid: (cid, U3_PARENT, False) for cid in sorted(val["local"]) if cid != U3_PARENT})
        out.update({"mean_bias_abs": {r: abs(v) for r, v in c["mean_bias"].items()}, "bias_within": c["bias_within"],
                    "max_abs_difference_discrepancy": {r: max(abs(v) for kk, v in c["difference_discrepancy"].items() if kk.startswith(r)) for r in RESP},
                    "differences_within": c["differences_within"]})
        out["pass"] = all(c["bias_within"].values()) and c["differences_within"]
    return out


# ---- verdict -----------------------------------------------------------------------------------------------------

def part(fn, *args):
    """Run one part: Missing -> INCOMPLETE marker; any other exception is recorded as an error (a failed part), never swallowed silently."""
    try:
        return fn(*args)
    except Missing as exc:
        return {"incomplete": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"pass": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(limit=3)}


def verdict(parts: dict, bitwise: bool) -> str:
    """A definite failure dominates; then any missing part or missing same-mesh pairs make the family INCOMPLETE."""
    done = [p for p in parts.values() if "incomplete" not in p]
    if any(p.get("pass") is False and p.get("enough_pairs") is not False for p in done):
        return "LOCAL_ENV_FAIL"
    if len(done) < len(parts) or any(p.get("enough_pairs") is False for p in done):
        return "INCOMPLETE"
    return "LOCAL_ENV_PASS_BITWISE" if bitwise else "LOCAL_ENV_PASS_TOLERANCE"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--u3-kaggle", type=Path, required=True, help="sanitised Kaggle U3 smoke archive (M2, commit 011066ba)")
    ap.add_argument("--u3-kaggle-raw", type=Path, required=True, help="unsanitised Kaggle U3 smoke output (outside the repository), read only by U4")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    fz, R = load(FREEZE), a.runs
    out_file = open(a.out, "x")   # created exclusively before any comparison: one result per invocation
    rd = lambda name, sub, kind: run_dir(R, name, sub, kind, fz)
    t1 = part(lambda: t20c_mesh_replay(rd("t20c_smoke2_a", "t20c", "t20c_smoke2"), REF_T20C))
    t2s = part(lambda: t20c_determinism(rd("t20c_smoke2_a", "t20c", "t20c_smoke2"), rd("t20c_smoke2_b", "t20c", "t20c_smoke2")))
    extra = [x.name for x in sorted(R.glob("t20b_[cd]")) if x.is_dir()]
    tb = part(lambda: t20b_forces({n: rd(n, "subset_t20b", "t20b") for n in ["t20b_a", "t20b_b", *extra]}, REF_T20B))
    t2b, t3, tvar = (tb, tb, tb) if failed(tb) else tb
    t2 = t2b if failed(t2b) else (t2s if failed(t2s) else {**t2b, "smoke_replays": t2s, "pass": t2b["pass"] and t2s["pass"]})
    ub = part(lambda: x3_forces(rd("x3_a", "subset_x3", "x3"), rd("x3_b", "subset_x3", "x3"), REF_X3))
    u1, u2 = (ub, ub) if failed(ub) else ub
    u3 = part(lambda: u3_mesh_replay(rd("u3_smoke_a_sanitized", "openfoam_xfid_gridphase_x3", "u3_smoke"), a.u3_kaggle))
    u4 = part(lambda: u3_forces_blinded(rd("u3_smoke_a", "openfoam_xfid_gridphase_x3", "u3_smoke"),
                                        rd("u3_smoke_b", "openfoam_xfid_gridphase_x3", "u3_smoke"), a.u3_kaggle_raw))
    if not failed(u1) and not failed(u4):
        u1 = {**u1, "v18_local_runs_identical": u4["determinism_pass"], "pass": u1["pass"] and u4["determinism_pass"]}
    sp = t1.get("solver_paths_descriptive")
    t_bitwise = bool(t3.get("bitwise") and sp and sp["same_mesh_solver_fields_identical"] == sp["same_mesh"])
    u_bitwise = bool(u2.get("bitwise") and u4.get("bitwise"))
    result = {
        "registration": "docs/local_openfoam_env_gate_2026_10_20.md", "freeze_sha256": sha(FREEZE), "comparator_sha256": sha(Path(__file__)),
        "T": {"verdict": verdict({"T1_mesh_replay": t1, "T2_determinism": t2, "T3_environment_identity": t3}, t_bitwise),
              "T1_mesh_replay": t1, "T2_determinism": t2, "T3_environment_identity": t3, "generator_variant_spread_descriptive": tvar,
              "kaggle_self_consistency_descriptive": part(kaggle_self_consistency, REF_T20B, REF_T20C)},
        "U": {"verdict": verdict({"U1_determinism": u1, "U2_x3_forces": u2, "U3_v18_mesh_replay": u3, "U4_v18_forces_blinded": u4}, u_bitwise),
              "U1_determinism": u1, "U2_x3_forces": u2, "U3_v18_mesh_replay": u3, "U4_v18_forces_blinded": u4},
        "qualification_flags": "unchanged (all false); environment evidence only",
    }
    out_file.write(json.dumps(result, indent=1, sort_keys=True, default=lambda v: None) + "\n")
    out_file.close()
    inputs = sorted(p for p in R.rglob("*") if p.is_file() and p.name in ("local_run.json", "result.json", "DONE", "bases.json"))
    with open(LEDGER, "a") as led:
        led.write(json.dumps({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "out": str(a.out), "out_sha256": sha(a.out),
                              "comparator_sha256": result["comparator_sha256"], "freeze_sha256": result["freeze_sha256"],
                              "verdicts": {"T": result["T"]["verdict"], "U": result["U"]["verdict"]},
                              "inputs_sha256": hashlib.sha256("".join(f"{p.relative_to(R)}:{sha(p)}\n" for p in inputs).encode()).hexdigest()},
                             sort_keys=True) + "\n")
    print(json.dumps({"T": result["T"]["verdict"], "U": result["U"]["verdict"]}))


if __name__ == "__main__":
    main()
