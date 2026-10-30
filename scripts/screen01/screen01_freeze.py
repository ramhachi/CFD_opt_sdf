#!/usr/bin/env python3
"""SCREEN-01 (#64) freeze records (registration §10): SHA-256 of every bound file at a clean, pushed commit.

    python scripts/screen01/screen01_freeze.py freeze1                                   # sources, P0 record, states + raws, OC, reused code, versions
    python scripts/screen01/screen01_freeze.py freeze2                                   # exploration campaign (screen01) + its harness prerun freeze
    python scripts/screen01/screen01_freeze.py freeze2_1 [--rs rs.json]                  # rs.json, proposal states, the G2 campaign (byte-checked)
    python scripts/screen01/screen01_freeze.py freeze3 [--finalist finalist.json] --wall g1k11=SECONDS ...   # finalist.json, confirmation campaigns, budget, handoff skeleton
Refuses to overwrite, on a dirty tracked tree, when HEAD is not on a remote branch, or when a regenerated (byte-checked) file differs.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01"), str(ROOT / "scripts/screen01")]
from cfd_harness import campaign_schema as SC  # noqa: E402
import fid01_designs as D  # noqa: E402
import screen01_build as SB  # noqa: E402

EV = SB.EV
REG = "docs/screen01_registration_2026_10_30.md"
ADOPTION = "docs/evidence/screen01_2026_10_30/plan_review/adoption.md"
PROFILE = "docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json"
FID_ANALYSIS, UNC_ANALYSIS = "docs/evidence/fid01_2026_10_21/analysis.json", "docs/evidence/unc01_2026_10_20/analysis.json"
CAP_S = 86400                                                  # registration §4.3: 24 GPU h of formal session wall
REUSED = ["scripts/fid01/fid01_designs.py", "scripts/fid01/fid01_build.py", "scripts/fid01/fid01_harness.py", "scripts/v18_plate.py", "scripts/mode01_v18_prescreen.py",
          "scripts/mode01_prescreen.py", "scripts/mode01_modes.py", "scripts/step01_states.py", "scripts/geom02_canonical.py", "scripts/build_xfid45_stage_v_input_2026_10_04.py",
          "scripts/unc01_u3_prepare.py", "scripts/unc01_build.py", "scripts/unc01_verify.py", "scripts/analyze_unc01.py", "scripts/width_rule_study.py",
          "src/cfd_sdf/fd08_v2_campaign.py", *D.DEPENDENCIES, FID_ANALYSIS, UNC_ANALYSIS,
          "docs/evidence/unc01_2026_10_20/states.json", "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json", "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz",
          "docs/evidence/v18_genesis_2026_10_19/v18_parent.phi_f4_fortran.raw", "docs/evidence/unc01_2026_10_20/inputs/v18__roll_p25.dir_f4_fortran.raw"]


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()


def tracked(p):
    out = git("ls-files", p)
    SC.req(bool(out), f"not tracked: {p}")
    return out.splitlines()


def record(kind, paths, extra):
    target = EV / f"{kind}.json"
    SC.req(not target.exists(), f"refusing to overwrite {target.name}")
    SC.req(not git("status", "--porcelain", "--untracked-files=no"), "tracked files have uncommitted changes")
    head = git("rev-parse", "HEAD")
    git("fetch", "-q", "origin")
    SC.req(any(subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", head, h.split()[0]]).returncode == 0
               for h in git("ls-remote", "--heads", "origin").splitlines()), "HEAD is not on a remote branch: push first")
    files = sorted({f for p in paths for f in tracked(p)})
    rec = {"kind": f"screen01_{kind}", "registration": REG, "source_commit": head, "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "file_sha256": {f: SC.sha256_path(ROOT / f) for f in files},
           "environment": {"python": platform.python_version(), **{m: importlib.metadata.version(m) for m in ("numpy", "scipy", "scikit-image")}},
           "harness_tool_sha256": SC.tool_hashes(), "qualification_flags": "all false (unchanged)", "shape_update_allowed": False, **extra}
    target.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return target


def campaign_record(cid):
    """SHA-256 of a campaign, its harness prerun freeze and the smoke table the freeze verified, and the kernel sizes; the campaign must be the one the freeze names."""
    c = SB.HARNESS / f"{cid}_campaign.json"
    fz = c.with_name(c.stem + ".prerun_freeze.json")
    freeze = json.loads(fz.read_text())
    SC.req(freeze["campaign_sha256"] == SC.sha256_path(c), f"{cid}: the prerun freeze belongs to another campaign file")
    kernels = json.loads(c.read_text())["kernels"]
    return {"campaign_sha256": freeze["campaign_sha256"], "prerun_freeze_sha256": SC.sha256_path(fz), "smoke_verified_sha256": freeze["smoke_verified_sha256"],
            "source_commit": freeze["source_commit"], "kernels": {k: {"runs": len(v["runs"]), "estimate_s": SB.FB.estimate_s(v)} for k, v in kernels.items()}}, \
        [SB.rel(p) for p in (c, fz, fz.with_name(fz.name + ".sha256"))]


def smoke_dirs(*names):
    return [SB.rel(EV / "wl" / n) for n in names if (EV / "wl" / n).exists()]


def freeze1():
    summ, dc = json.loads((SB.P0 / "summary.json").read_text()), json.loads((SB.P0 / "design_check.json").read_text())
    SC.req(summ["d_fingerprint"] == D.fingerprint(), "the P0 record was not produced under the current fid01_designs fingerprint: re-validate it (registration §10)")
    SC.req(dc["design_admissible"] and dc["rand3"]["complete"] and summ["pools"]["rand3"]["complete"], "P0: design not admissible or random-control set incomplete (registration §3.3)")
    SB.emit(SB.states_files(), True)   # states.json and every raw re-derive byte for byte
    rows = SB.p0_record()[1]
    man = json.loads((SB.P0 / "pools.json").read_text())["pools"]["manual"]
    paths = [REG, ADOPTION, "docs/evidence/screen01_2026_10_30/decision_memo.md", "scripts/screen01/*.py", "tests/screen01/*.py", "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1",
             "docs/evidence/screen01_2026_10_30/states.json", "docs/evidence/screen01_2026_10_30/inputs", "docs/evidence/screen01_2026_10_30/oc.json", *REUSED]
    extra = {"status": "plan and sources frozen (freeze 1); REGISTERED_FROZEN from freeze 2", "plan_review": "one, three angles, registration §12", "source_review": "one, registration §13",
             "p0": {"d_fingerprint": summ["d_fingerprint"], "parent_stl": summ["parent_stl"], "stl_sha256": {n: r["x1"]["stl_sha256"] for n, r in sorted(rows.items()) if r["admissible"]},
                    "ladder": {"specs": man, "M": {k: v for k, v in summ["pools"]["manual"].items() if k.startswith("M_for")}},
                    "random_control": {"names": summ["pools"]["rand3"]["control_set"], "abs_u_inf": dc["rand3"]["abs_u_inf"], "n_consumed": dc["rand3"]["n_consumed"]},
                    "design": {"names": dc["design_points"], "abs_u_inf": dc["abs_u_inf_design"], "rank": dc["rank"], "cond": dc["cond"]}},
             "analysis_sha256": {"fid01": SC.sha256_path(ROOT / FID_ANALYSIS), "unc01": SC.sha256_path(ROOT / UNC_ANALYSIS)}}
    return record("freeze1", paths, extra)


def freeze2():
    SB.emit(SB.campaign_files("g1"), True)
    rec, files = campaign_record("screen01")
    return record("freeze2", [SB.rel(EV / "freeze1.json"), REG, *files, *smoke_dirs("smoke")], {"status": "REGISTERED_FROZEN (freeze 2)", "campaign": rec})


def freeze2_1(rs_path):
    rs = json.loads(rs_path.read_text())
    files = SB.campaign_files("g2", rs_path)
    SB.emit(files, True)
    paths = [SB.rel(EV / "freeze2.json"), SB.rel(rs_path.resolve()), REG]
    extra = {"status": "REGISTERED_FROZEN (freeze 2.1)", "rs_json_sha256": SC.sha256_path(rs_path), "g2": "none (no proposal; no g2 kernel, registration §2)"}
    if files:
        states = json.loads(SB.STATES_G2.read_text())["states"]
        camp, cfiles = campaign_record("screen01_g2")
        gating = {g["name"]: g for g in rs["gating"]}
        extra.update(g2=camp, proposals={n: {**{k: r[k] for k in ("order", "u", "spec", "step_mm", "direction_sha256_fortran_raw", "state_sha256", "npz_sha256", "phi_fortran_order_sha256",
                                                "phi_c_order_sha256")}, "gating_row": gating[n]} for n, r in states.items()})
        paths += [SB.rel(SB.STATES_G2), SB.rel(EV / "inputs"), *cfiles, *smoke_dirs("smoke_g2")]
    return record("freeze2_1", paths, extra)


def budget(walls: dict, f_kernels: dict, finished: set) -> dict:
    """Registration §4.3 before the first push of F: T = finished session wall (reruns included) + the estimates of the unfinished formal kernels <= the cap."""
    SC.req(set(walls) == finished, f"--wall needs exactly the finished formal kernels {sorted(finished)}")
    est = {k: SB.FB.estimate_s(v) for ks in f_kernels.values() for k, v in ks.items() if k in SB.FORMAL}
    total = sum(walls.values()) + sum(est.values())
    SC.req(total <= CAP_S, f"T = {total:.0f} s exceeds the {CAP_S} s cap: the pushes stop and the decision goes to the user (registration §4.3)")
    return {"cap_s": CAP_S, "finished_session_wall_s": walls, "unfinished_estimate_s": est, "T_s": total, "rule": "registration §4.3"}


def handoff_skeleton(fin: str, rows: dict, rs: dict, camps: dict) -> dict:
    """§11 with every hash known at freeze 3: the identity of the parent and finalist and the finalist's admissibility row (P0 row, or the rs.json gating row of a proposal)."""
    pick = lambda r: {k: r.get(k) for k in ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "direction_sha256_fortran_raw", "step_mm", "spec")}  # noqa: E731
    adm = SB.p0_record()[1].get(fin) or next(g for g in rs["gating"] if g["name"] == fin)
    return {"parent": {"name": SB.PARENT, **pick(rows[SB.PARENT])}, "finalist": {"name": fin, **pick(rows[fin]), "admissibility_row": adm}, "gate_profile_sha256": SC.sha256_path(ROOT / PROFILE),
            "campaigns": camps, "registration_sha256": SC.sha256_path(ROOT / REG), "adoption_sha256": SC.sha256_path(ROOT / ADOPTION), "phases": {"exploration": [11, 12],
            "confirmation_flow_32": [13, 14, 15, 16], "confirmation_flow_48": [13, 14]}, "z": "in-plane placement phases only; z never moves"}


def freeze3(finalist_path, walls):
    fin = json.loads(finalist_path.read_text())
    SC.req(bool(fin.get("finalist")), "no finalist: freeze 3 is not written (registration §5.4)")
    SB.emit(SB.campaign_files("f", finalist_path=finalist_path), True)
    rows, rs = SB.load_rows(), json.loads((EV / "rs.json").read_text())   # rs.json exists: freeze 2.1 recorded it
    f_kernels = SB.f_kernels(rows, fin["finalist"], fin.get("r_best"))
    finished = {"g1k11", "g1k12"} | ({"g2"} if SB.STATES_G2.exists() else set())
    camps, files = {}, []
    for cid in f_kernels:
        camps[cid], cf = campaign_record(cid)
        files += cf
    extra = {"status": "REGISTERED_FROZEN (freeze 3)", "finalist_json_sha256": SC.sha256_path(finalist_path), "finalist": fin["finalist"], "r_best": fin.get("r_best"),
             "campaigns": camps, "budget": budget(walls, f_kernels, finished), "handoff_skeleton": handoff_skeleton(fin["finalist"], rows, rs, camps)}
    return record("freeze3", [SB.rel(EV / "freeze2_1.json"), SB.rel(finalist_path.resolve()), REG, *files, *smoke_dirs("smoke_f", "smoke_f48")], extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["freeze1", "freeze2", "freeze2_1", "freeze3"])
    ap.add_argument("--rs", type=Path, default=EV / "rs.json")
    ap.add_argument("--finalist", type=Path, default=EV / "finalist.json")
    ap.add_argument("--wall", action="append", default=[], metavar="KERNEL=SECONDS", help="freeze3: session wall of a finished formal kernel (repeat a kernel to add a rerun)")
    a = ap.parse_args()
    walls = {}
    for w in a.wall:
        k, v = w.split("=")
        walls[k] = walls.get(k, 0.0) + float(v)
    print({"freeze1": freeze1, "freeze2": freeze2, "freeze2_1": lambda: freeze2_1(a.rs), "freeze3": lambda: freeze3(a.finalist, walls)}[a.kind]())


if __name__ == "__main__":
    main()
