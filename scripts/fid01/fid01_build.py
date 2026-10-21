#!/usr/bin/env python3
"""FID-01 (#62, M3a) builder: the registered states through the harness state model, the WaterLily harness campaign and the OpenFOAM inputs
(STL exports, per-kernel datasets, criteria, local kernels).  Solver-free and deterministic.  Registration: docs/fid01_registration_2026_10_21.md.

    python scripts/fid01/fid01_build.py states              # direction raws + states.json from designs.json (refuses unless every state reproduces its gated bytes)
    python scripts/fid01/fid01_build.py campaign            # docs/harness/fid01_campaign.json (§4)
    python scripts/fid01/fid01_build.py of-export [--workers N]   # STL exports (r = 8; EX r = 16) + X1 gate + STL volumes -> of/export.json, work/fid01_of/stl/
    python scripts/fid01/fid01_build.py of-prepare [--smoke]      # per-kernel datasets (work/fid01_of/), criteria (of/criteria/), kernels (infra/fid01/)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
import fid01_designs as D  # noqa: E402
import step01_states as S  # noqa: E402
import unc01_build as B  # noqa: E402

OUT = D.OUT
INPUTS = OUT / "inputs"
OF = OUT / "of"
WORK = ROOT / "work/fid01_of"
KERNELS = ROOT / "infra/fid01"
CAMPAIGN = ROOT / "docs/harness/fid01_campaign.json"
ROLL = "v18__roll_p25"
PARENT = "v18__parent"
UNC01_STATES = B.OUT / "states.json"

# WaterLily (§4): flow_32 phases 7-10 (P = 4), one kernel per phase; flow_48 phase 7 for the d_set run set (second campaign fid01_f48)
PHASES = {"flow_32": (7, 8, 9, 10), "flow_48": (7,)}
F32 = {f"f32k{k}": (k,) for k in PHASES["flow_32"]}
F32_CFG = (900, 13000, 16000)                                    # per-state / aggregate cap / kernel timeout (s)
CAMPAIGN48 = ROOT / "docs/harness/fid01_f48_campaign.json"
DSET = OUT / "d_set.json"
EST_S = {"flow_32": 415, "flow_48": 2340}
SETUP_S = 260

# OpenFOAM (§5): levels, template changes, shifts (X3 generator Halton indices), kernels
PAIR_TAGS = lambda pairs: [f"{i}{m}" for i in pairs for m in "pm"]  # noqa: E731
LEVELS = {"V1": {"blocks": None, "end_time": None, "shifts": PAIR_TAGS(range(49, 65))},
          "V2": {"blocks": (50, 26, 18), "end_time": None, "shifts": PAIR_TAGS(range(49, 51))},
          "V3": {"blocks": (100, 52, 36), "end_time": 6000, "shifts": ["49p"]}}
EXTENSION_SHIFTS = {"V1": PAIR_TAGS(range(65, 73)), "V2": PAIR_TAGS(range(51, 53)), "V3": ["49m"]}
EX_SLOTS = ("W4", "W6")                       # + the parent: exported at r = 16 and run on V1 at every V1 shift (§3.4)
EX_REFINEMENT = 16
V3_GROUP = 6
SMOKE_SHIFT = "80p"
STAGE_TIMEOUT_S = {"V1": 7200, "V2": 43200, "V3": 259200}   # hang detectors (>= 8x the measured need); a timeout is INFRA_LOSS (§10)
STOP_AFTER_FAILURES = 10


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def designs() -> dict:
    """slot -> chosen design (registration §3.2), in slot order; empty slots dropped."""
    rec = json.loads((OUT / "designs.json").read_text())
    return {k: v for k, v in rec["designs"].items() if v is not None}


def state_names() -> list[str]:
    return [PARENT, *(d["name"] for d in designs().values()), ROLL]


def wide_names() -> list[str]:
    return [d["name"] for d in designs().values() if d["stratum"] == "wide"]


def dir_rel(name: str) -> str:
    return B.dir_rel(name) if name == ROLL else f"docs/evidence/fid01_2026_10_21/inputs/{name}.dir_f4_fortran.raw"


def build_states(write: bool = True) -> dict:
    """Every design through the harness model; its Fortran phi SHA must equal the prescreen gated bytes and the runner regeneration must reproduce it.
    The parent and the roll are taken from UNC-01 states.json unchanged (same bytes, same raws)."""
    import mode01_v18_prescreen as P18
    import v18_plate as V
    from cfd_sdf.fd08_v2_campaign import construct_state, state_identity
    s, p = P18.load_parent()
    gated = {r["name"]: r for r in json.loads((OUT / "designs.json").read_text())["rows"]}
    unc = json.loads(UNC01_STATES.read_text())
    parent_raw = S.read_f4(ROOT / B.PARENT_RAW)
    rows = {n: {**unc["states"][n], "direction_path": None if n == PARENT else dir_rel(n), "slot": None} for n in (PARENT, ROLL)}
    if len(designs()) < 12 or len({d["family"] for d in designs().values()}) < 4:
        raise SystemExit("fewer than 12 designs or 4 families (registration §3.2)")
    for slot, d in designs().items():
        dvec, step = V.harness_direction(s, D.design_phi(s, p, d["spec"]))
        child, audit = construct_state(s, dvec, step, 1)
        ident = state_identity(child)
        if ident["phi_fortran_order_sha256"] != gated[d["name"]]["phi_fortran_sha256"]:
            raise SystemExit(f"{d['name']}: harness bytes differ from the prescreen gated bytes")
        raw = S.to_raw(dvec)
        if write:
            INPUTS.mkdir(parents=True, exist_ok=True)
            (ROOT / dir_rel(d["name"])).write_bytes(raw)
        regen = S.perturb(parent_raw, np.frombuffer(raw, "<f4").reshape(S.SHAPE, order="F"), step, 1)
        if S.sha256_bytes(S.to_raw(regen)) != ident["phi_fortran_order_sha256"]:
            raise SystemExit(f"{d['name']}: runner regeneration differs")
        rows[d["name"]] = {"mode": d["spec"], "amplitude": None, "kind": "candidate", "direction": d["name"], "direction_path": dir_rel(d["name"]),
                           "step_mm": float(step), "sign": 1, "direction_sha256_fortran_raw": S.sha256_bytes(raw), "state_sha256": ident["state_sha256"],
                           "npz_sha256": B.npz_sha(child), "phi_fortran_order_sha256": ident["phi_fortran_order_sha256"], "phi_c_order_sha256": ident["phi_c_order_sha256"],
                           "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": 1e-6, "changed_node_count": int(audit["changed_node_count"]),
                           "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]), "slot": slot, "stratum": d["stratum"], "family": d["family"],
                           "spec": d["spec"]}
    rows[ROLL]["direction_path"] = dir_rel(ROLL)
    rec = {"kind": "fid01_states", "parent": unc["parent"], "v18_plate_sha256": sha(ROOT / "scripts/v18_plate.py"), "designs_sha256": sha(OUT / "designs.json"),
           "unc01_states_sha256": sha(UNC01_STATES), "states": rows,
           "check": "every design's Fortran phi SHA equals its prescreen gated bytes; step01_states.perturb on the written raw reproduces it; parent and roll = UNC-01 rows"}
    if write:
        (OUT / "states.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


# ---- WaterLily campaign ----------------------------------------------------------------------------------------------------------------------------
def kernels() -> dict:
    st = state_names()
    return {k: B.kernel("fid01", k, "flow_32", [B.run(s, "flow_32", ph) for ph in phases for s in st], *F32_CFG) for k, phases in F32.items()}


def kernels48(run_set: list[str]) -> dict:
    """The flow_48 kernel of the second campaign: the d_set run set (parent first) at k = 7; aggregate cap 1.3x the estimate."""
    n = len(run_set)
    cap = max(int(1.3 * n * EST_S["flow_48"]), 6000)
    return {"f48": B.kernel("fid01_f48", "f48", "flow_48", [B.run(s, "flow_48", PHASES["flow_48"][0]) for s in run_set], 6000, cap, cap + 3300)}


def estimate_s(kern: dict) -> int:
    return len(kern["runs"]) * EST_S[kern["case"]["case_id"]] + SETUP_S


def write_campaign(which: str = "f32") -> Path:
    from cfd_harness import campaign_schema as SC
    rec = json.loads((OUT / "states.json").read_text())
    if build_states(write=False)["states"] != rec["states"]:
        raise SystemExit("states.json no longer re-derives")
    if which == "f32":
        c, path = B.campaign("fid01", kernels(), rec), CAMPAIGN
    else:
        ds = json.loads(DSET.read_text())
        c, path = B.campaign("fid01_f48", kernels48(ds["run_sets"]["flow_48"]), rec), CAMPAIGN48
    c["directions"] = {n: {"path": rec["states"][n]["direction_path"], "sha256_fortran_raw": rec["states"][n]["direction_sha256_fortran_raw"]}
                       for n in c["states"] if rec["states"][n]["direction"]}
    SC.validate_campaign(c)
    text = json.dumps(c, indent=1, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != text:
        raise SystemExit(f"refusing to overwrite a different {path}")
    path.write_text(text)
    return path


# ---- OpenFOAM inputs --------------------------------------------------------------------------------------------------------------------------------
def state_bytes(name: str):
    import mode01_modes as M
    rec = json.loads((OUT / "states.json").read_text())["states"][name]
    parent, _ = B.load_parent()
    raw = S.read_f4(ROOT / B.PARENT_RAW)
    phi = raw if rec["direction"] is None else S.perturb(raw, S.read_f4(ROOT / rec["direction_path"]), rec["step_mm"], rec["sign"])
    if S.sha256_bytes(S.to_raw(phi)) != rec["phi_fortran_order_sha256"]:
        raise SystemExit(f"{name}: rebuilt phi differs from states.json")
    return parent if rec["direction"] is None else M.with_phi(parent, np.ascontiguousarray(phi, dtype="<f4"))


def stl_volume(blob: bytes) -> float:
    import build_xfid45_stage_v_input_2026_10_04 as x1
    v, f = x1.read_stl(blob)
    t = np.asarray(v, np.float64)[np.asarray(f)]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def ex_names() -> list[str]:
    d = designs()
    return [PARENT, *(d[s]["name"] for s in EX_SLOTS if s in d)]


def _export_one(task):
    """r = 8 STLs of the designs were written by `fid01_designs.py select` (same bytes, X1-gated); they are reused after a hash check."""
    import unc01_u3_prepare as U
    name, r = task
    x1 = json.loads((OUT / "designs.json").read_text()).get("x1", {}).get(name)
    f = WORK / "stl" / stl_file(name, r)
    if r == 8 and x1 and f.exists() and sha(f) == x1["stl_sha256"]:
        blob, rec = f.read_bytes(), dict(x1)
        return name, r, {**rec, "stl_volume_m3": stl_volume(blob), "refinement": r, "reused_from_select": True}
    profile = json.loads(U.PROFILE.read_text())
    profile["export"]["refinement"] = r
    blob, rec = U.export(state_bytes(name), profile)
    rec["stl_volume_m3"] = stl_volume(blob)
    rec["refinement"] = r
    (WORK / "stl").mkdir(parents=True, exist_ok=True)
    (WORK / "stl" / stl_file(name, r)).write_bytes(blob)
    return name, r, rec


def export_key(state: str) -> str:
    """export.json key of a case state: '<name>|r8', or '<name>|r16' for the EX states '<name>__r16' (names may contain '__r', e.g. reflex, roll)."""
    suffix = f"__r{EX_REFINEMENT}"
    return f"{state[:-len(suffix)]}|r{EX_REFINEMENT}" if state.endswith(suffix) else f"{state}|r8"


def stl_file(name: str, r: int) -> str:
    return f"{name}.stl" if r == 8 else f"{name}__r{r}.stl"


def of_export(workers: int) -> dict:
    import multiprocessing as mp
    tasks = [(n, 8) for n in state_names()] + [(n, EX_REFINEMENT) for n in ex_names()]
    with mp.get_context("spawn").Pool(workers) as pool:
        res = pool.map(_export_one, tasks)
    recs = {f"{n}|r{r}": rec for n, r, rec in res}
    v0 = recs[f"{PARENT}|r8"]["stl_volume_m3"]
    sdf = {r["name"]: r["volume_vs_parent"] for r in json.loads((OUT / "designs.json").read_text())["rows"]}
    for k, rec in recs.items():
        rec["stl_volume_vs_parent"] = rec["stl_volume_m3"] / v0 - 1.0
        rec["sdf_smoothed_volume_vs_parent"] = 0.0 if k.startswith(PARENT) else sdf.get(k.split("|")[0])   # G5a chain check (§6.3)
    out = {"kind": "fid01_of_export", "pipeline": "geom02_canonical.export_from_state (r = 8; EX r = 16) + X1 practical gate (double and float32 STL)",
           "states_sha256": sha(OUT / "states.json"), "exports": recs, "all_pass": all(r["pass"] for r in recs.values())}
    OF.mkdir(parents=True, exist_ok=True)
    (OF / "export.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


def shifts(tags) -> list[tuple[str, list]]:
    """(tag, shift_m) for every tag '<Halton index><p|m>' (X3 generator: + is the vector, - its exact mirror)."""
    import prepare_kaggle_xfid_gridphase_x3 as x3
    out = []
    for tag in tags:
        c = x3.phase_cases("s", "t", 1, start=int(tag[:-1]))[0 if tag.endswith("p") else 1]
        out.append((tag, c["shift_m"]))
    return out


def of_kernels(extension: dict | None = None, stage: str = "v1") -> dict:
    """kernel -> (level, [(case id, state, stl file, shift_m)]) in shift-major order.  Stage v1 (freeze 2): V1, every state and the EX r = 16 STLs,
    four kernels of four whole mirror pairs.  Stage v23 (freeze 3, after d_set): V2 one kernel per shift for the d_set V2 run set; V3 one kernel per
    shift for the V3 run set in groups of <= V3_GROUP cases.  extension = {level: [state names]} builds the §6.8 kernels instead."""
    out = {}
    if extension:
        for lev, names in extension.items():
            sts = [PARENT] + [n for n in names if n != PARENT]
            cases = [(f"{lev}_{n}_{tag}", n, stl_file(n, 8), sh) for tag, sh in shifts(EXTENSION_SHIFTS[lev]) for n in sts]
            out[f"ext_{lev.lower()}"] = (lev, cases)
        return out
    if stage == "v1":
        v1 = LEVELS["V1"]["shifts"]
        ex = [(f"{n}__r{EX_REFINEMENT}", stl_file(n, EX_REFINEMENT)) for n in ex_names()]
        for g in range(4):   # four kernels of four whole mirror pairs each
            out[f"v1_{g + 1}"] = ("V1", [(f"V1_{n}_{tag}", n, f, sh) for tag, sh in shifts(v1[8 * g:8 * g + 8])
                                         for n, f in [(s, stl_file(s, 8)) for s in state_names()] + ex])
        return out
    sets = json.loads(DSET.read_text())["run_sets"]
    for lev in ("V2", "V3"):
        for tag, sh in shifts(LEVELS[lev]["shifts"]):
            cases = [(f"{lev}_{n}_{tag}", n, stl_file(n, 8), sh) for n in sets[lev]]
            if lev == "V2":
                out[f"v2_{tag}"] = (lev, cases)
                continue
            for g in range(0, len(cases), V3_GROUP):
                out[f"v3_{tag}_{g // V3_GROUP + 1}"] = (lev, cases[g:g + V3_GROUP])
    return out


def template(dst: Path, lev: str) -> None:
    import prepare_kaggle_xfid_gridphase_x3 as x3
    src = x3.R5 / "case_template"
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if f.is_file() and rel.as_posix() != "constant/triSurface/design_candidate.stl":
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)
    cfg = LEVELS[lev]
    if cfg["blocks"]:
        p = dst / "system/blockMeshDict"
        t = p.read_text()
        if t.count("(25 13 9)") != 1:
            raise SystemExit("unexpected blockMeshDict")
        p.write_text(t.replace("(25 13 9)", "({} {} {})".format(*cfg["blocks"])))
    if cfg["end_time"]:
        p = dst / "system/controlDict"
        t, n = re.subn(r"^endTime\s+3000;$", f"endTime         {cfg['end_time']};", p.read_text(), flags=re.M)
        if n != 1:
            raise SystemExit("unexpected controlDict")
        p.write_text(t)


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def of_prepare(smoke: bool = False, extension: dict | None = None, stage: str = "v1") -> dict:
    """Datasets under work/fid01_of/<kernel>/ (untracked; re-derivable), criteria under of/criteria/ (tracked), kernels under infra/fid01/<kernel>/.
    smoke: the parent and the first design on every level at its first shift (statuses only, §2)."""
    import prepare_kaggle_xfid_gridphase_x3 as x3
    import unc01_u3_prepare as U
    exp = json.loads((OF / "export.json").read_text())
    if exp["states_sha256"] != sha(OUT / "states.json") or not exp["all_pass"]:
        raise SystemExit("export.json does not belong to states.json or an export failed the X1 gate")
    x3c = json.loads((x3.EVID / "formal/x3_criteria.json").read_text())
    if smoke:   # V1 and V2: the parent and the first design at a shift outside every registered set (Halton 80 +), V1 also the parent's r = 16 STL;
        first = state_names()[1]          # V3: the timing probe (§2)
        (tag, sh), = shifts([SMOKE_SHIFT])
        r16 = [(f"V1_{PARENT}__r{EX_REFINEMENT}_{tag}", f"{PARENT}__r{EX_REFINEMENT}", stl_file(PARENT, EX_REFINEMENT), sh)]
        ks = {f"smoke_{lev.lower()}": (lev, [(f"{lev}_{n}_{tag}", n, stl_file(n, 8), sh) for n in (PARENT, first)] + (r16 if lev == "V1" else []))
              for lev in ("V1", "V2")}
    else:
        ks = of_kernels(extension, stage)
    summary = {}
    for kname, (lev, cases) in ks.items():
        ds, kd = WORK / kname, KERNELS / kname
        if ds.exists():
            shutil.rmtree(ds)
        template(ds / "case_template", lev)
        files = {}
        for _, state, f, _ in cases:
            _link(WORK / "stl" / f, ds / "states" / f)
            key = export_key(state)
            files[state] = {"file": f"states/{f}", "sha256": exp["exports"][key]["stl_sha256"], "triangles": exp["exports"][key]["triangles"]}
        shutil.copy2(x3.R5 / "openfoam_package_lock.json", ds / "openfoam_package_lock_jammy.json")
        shutil.copy2(x3.NOBLE / "openfoam_package_lock.json", ds / "openfoam_package_lock_noble.json")
        crit = {"round_id": f"fid01_{kname}", "date": "2026-10-21", "registration": "docs/fid01_registration_2026_10_21.md §5",
                "evidence_class": "fid01_openfoam_uncertified_geometry" + (" (development smoke: statuses only)" if smoke else ""),
                "purpose": f"FID-01 M3a OpenFOAM level {lev}: registered v18 designs, matched rigid shifts (X3 generator), U3 pipeline",
                "level": lev, "template_changes": {"blockMesh_cells": LEVELS[lev]["blocks"], "endTime": LEVELS[lev]["end_time"]},
                "states_sha256": sha(OUT / "states.json"), "export_sha256": sha(OF / "export.json"),
                "environment": x3c["environment"], "force_window": x3c["force_window"], "stage_timeout_s": STAGE_TIMEOUT_S[lev],
                "per_case_failure_policy": x3c["per_case_failure_policy"], "stop_after_consecutive_failures": STOP_AFTER_FAILURES,
                "launch_deadline_hours": 200.0, "case_template_origin": x3c["case_template_origin"] + f"; level {lev} changes only the listed template entries",
                "shift_design": {**x3c["shift_design"], "shift_tags": sorted({c[0].rsplit("_", 1)[1] for c in cases})},
                "states": files, "not_run_export_gate": [], "export": {"profile": str(U.PROFILE.relative_to(ROOT)), "profile_sha256": sha(U.PROFILE)},
                "inputs": {q.relative_to(ds).as_posix(): sha(q) for q in sorted(ds.rglob("*")) if q.is_file()},
                "case_order": [{"id": cid, "state": state, "shift_m": sh} for cid, state, _, sh in cases],
                "analysis": {"script": "scripts/fid01/analyze_fid01.py", "rule": "registration §6"},
                "qualification_flags": x3c["qualification_flags"], "immutable": True, "registered_before_run": not smoke}
        text = json.dumps(crit, indent=2, sort_keys=True) + "\n"
        digest = hashlib.sha256(text.encode()).hexdigest()
        cdir = OF / ("smoke/criteria" if smoke else "criteria")
        cdir.mkdir(parents=True, exist_ok=True)
        target = cdir / f"{kname}.json"
        if target.exists() and target.read_text() != text:
            raise SystemExit(f"refusing to overwrite different criteria {target}")
        target.write_text(text)
        (ds / "x3_criteria.json").write_text(text)
        (ds / "x3_criteria.json.sha256").write_text(digest + "\n")
        slug = f"ramhachi888/fid01-of-{kname.replace('_', '-')}-inputs"
        (ds / "dataset-metadata.json").write_text(json.dumps({"title": slug.split("/")[1], "id": slug, "licenses": [{"name": "other"}]}, indent=2, sort_keys=True) + "\n")
        kd.mkdir(parents=True, exist_ok=True)
        (kd / "runner.py").write_text(re.sub(r'CRITERIA_SHA256 = "[^"]*"', f'CRITERIA_SHA256 = "{digest}"', U.X3_RUNNER.read_text(), count=1))
        meta = json.loads((U.X3_RUNNER.parent / "kernel-metadata.json").read_text())
        meta.update({"id": slug.replace("-inputs", ""), "title": slug.split("/")[1].replace("-inputs", ""), "dataset_sources": [slug]})
        (kd / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
        summary[kname] = {"level": lev, "cases": len(cases), "criteria_sha256": digest}
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["states", "campaign", "campaign48", "of-export", "of-prepare"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--stage", choices=["v1", "v23"], default="v1")
    a = ap.parse_args()
    if a.cmd == "states":
        rec = build_states()
        print(json.dumps({n: (r["step_mm"], r["phi_fortran_order_sha256"][:12]) for n, r in rec["states"].items()}, indent=1))
    elif a.cmd in ("campaign", "campaign48"):
        print(write_campaign("f32" if a.cmd == "campaign" else "f48"))
    elif a.cmd == "of-export":
        out = of_export(a.workers)
        print(json.dumps({k: (v["pass"], v["triangles"], round(v["stl_volume_vs_parent"], 4)) for k, v in out["exports"].items()}, indent=1))
    else:
        print(json.dumps(of_prepare(a.smoke, stage=a.stage), indent=1))


if __name__ == "__main__":
    main()
