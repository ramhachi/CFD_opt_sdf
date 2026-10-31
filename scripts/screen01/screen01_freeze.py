#!/usr/bin/env python3
"""SCREEN-01 (#64) freeze records (registration §10): SHA-256 of every bound file at a clean, pushed commit.

    python scripts/screen01/screen01_freeze.py freeze1                                   # sources, P0 record, states + raws, OC, reused code, versions
    python scripts/screen01/screen01_freeze.py freeze2 --smoke-table T                   # exploration campaign (screen01) + its harness prerun freeze; T verifies kernel g1k11
    python scripts/screen01/screen01_freeze.py freeze2_1 [--rs rs.json] [--budget B --smoke-table T]   # rs.json, proposal states, the G2 campaign (byte-checked), its
                                                                                                        # smoke (kernel g2) and the §4.3 budget record of the G2 push
    python scripts/screen01/screen01_freeze.py freeze3 [--finalist finalist.json] [--rs rs.json] [--budget B --smoke-table-f T --smoke-table-f48 T48]
        # always written after `finalist`; iff F is pushed: the confirmation campaigns, their smokes (f32smk, f48smk), the budget record, the handoff skeleton
Budget records are written by `analyze_screen01.py budget --out`; smoke tables by `harness.py verify --smoke --out`; smoke outputs live under docs/evidence/screen01_2026_10_30/wl/
(smoke, smoke_g2, smoke_f, smoke_f48).  Refuses to overwrite, on a dirty tracked tree, on an untracked file under the registered directories, when HEAD is not on a remote branch,
when a regenerated (byte-checked) file differs, and (freezes 2-3) when the harness tools differ from freeze 1's.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01"), str(ROOT / "scripts/screen01")]
from cfd_harness import campaign_schema as SC  # noqa: E402
import screen01_build as SB  # noqa: E402
import screen01_pool as P  # noqa: E402

EV = SB.EV
REG = "docs/screen01_registration_2026_10_30.md"
ADOPTION = "docs/evidence/screen01_2026_10_30/plan_review/adoption.md"
BOUND_EVIDENCE = ["docs/evidence/screen01_2026_10_30/infra_signatures.json", "docs/evidence/screen01_2026_10_30/crosscheck_reconciliation.md", "scripts/screen01/INTERFACE.md",
                  "docs/evidence/screen01_2026_10_30/source_review/adoption.md"]
PROFILE = "docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json"
POLICY = "docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json"
FID_ANALYSIS, UNC_ANALYSIS = "docs/evidence/fid01_2026_10_21/analysis.json", "docs/evidence/unc01_2026_10_20/analysis.json"
CAP_S = 86400                                                  # registration §4.3: 24 GPU h of formal session wall
GUARDED = ("scripts/screen01/", "tests/screen01/", "src/", "docs/harness/", "docs/evidence/screen01_2026_10_30/")   # an untracked, not gitignored file here refuses every freeze (§10)
REUSED = sorted(set(P.DEPENDENCIES) | {"scripts/fid01/fid01_harness.py", "scripts/v18_plate.py", "scripts/mode01_v18_prescreen.py", "scripts/mode01_prescreen.py", "scripts/mode01_modes.py",
                                       "scripts/step01_states.py", "scripts/geom02_canonical.py", "scripts/build_xfid45_stage_v_input_2026_10_04.py", "scripts/unc01_u3_prepare.py",
                                       "scripts/unc01_build.py", "scripts/unc01_verify.py", "scripts/analyze_unc01.py", "scripts/width_rule_study.py", "src/cfd_sdf/fd08_v2_campaign.py",
                                       FID_ANALYSIS, UNC_ANALYSIS, "docs/evidence/unc01_2026_10_20/states.json", "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json",
                                       "docs/evidence/unc01_2026_10_20/inputs/v18__roll_p25.dir_f4_fortran.raw"})   # screen01_pool.DEPENDENCIES + the rest of registration §10's list
assert set(P.DEPENDENCIES) <= set(REUSED)


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
    untracked = [x[3:] for x in git("status", "--porcelain").splitlines() if x.startswith("??") and x[3:].startswith(GUARDED)]
    SC.req(not untracked, f"untracked files under the registered directories (commit or ignore them): {untracked}")
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


def check_tools():
    """Freezes 2, 2.1 and 3: the harness tools running now are the ones freeze 1 recorded."""
    SC.req(SC.jload(EV / "freeze1.json")["harness_tool_sha256"] == SC.tool_hashes(), "the harness tool hashes differ from freeze 1's")


def campaign_record(cid, smoke_table):
    """SHA-256 of a campaign, its harness prerun freeze and the smoke table, and the kernel sizes.  The campaign must be the one the prerun freeze names, and the smoke table the one
    that freeze verified (SHA-256) for exactly the registered smoke kernel of this campaign (registration §4.2); the table is bound by the freeze."""
    c = SB.HARNESS / f"{cid}_campaign.json"
    fz = c.with_name(c.stem + ".prerun_freeze.json")
    freeze, kernel = json.loads(fz.read_text()), SB.SMOKE_KERNEL[cid]
    SC.req(freeze["campaign_sha256"] == SC.sha256_path(c), f"{cid}: the prerun freeze belongs to another campaign file")
    SC.req(smoke_table is not None and smoke_table.is_file(), f"{cid}: the smoke table is missing (--smoke-table)")
    table = SC.jload(smoke_table)
    SC.req(SC.sha256_path(smoke_table) == freeze["smoke_verified_sha256"], f"{cid}: the smoke table is not the one the prerun freeze verified")
    SC.req(table.get("kind") == SC.TABLE_KIND and table.get("smoke") is True and table.get("campaign_sha256") == freeze["campaign_sha256"]
           and set(table.get("kernel_manifest_sha256", {})) == {kernel}, f"{cid}: the smoke table must verify exactly kernel {kernel} of this campaign")
    kernels = json.loads(c.read_text())["kernels"]
    return {"campaign_sha256": freeze["campaign_sha256"], "prerun_freeze_sha256": SC.sha256_path(fz), "smoke_verified_sha256": freeze["smoke_verified_sha256"], "smoke_kernel": kernel,
            "source_commit": freeze["source_commit"], "kernels": {k: {"runs": len(v["runs"]), "estimate_s": SB.FB.estimate_s(v)} for k, v in kernels.items()}}, \
        [SB.rel(p) for p in (c, fz, fz.with_name(fz.name + ".sha256"), smoke_table.resolve())]


def smoke_dirs(*names):
    missing = [n for n in names if not (EV / "wl" / n).is_dir()]
    SC.req(not missing, f"smoke output directories missing under wl/: {missing}")
    return [SB.rel(EV / "wl" / n) for n in names]


def freeze1():
    summ, dc = json.loads((SB.P0 / "summary.json").read_text()), json.loads((SB.P0 / "design_check.json").read_text())
    SC.req(summ.get("fingerprint") == P.fingerprint(), "the P0 record was not produced under the running screen01_pool.fingerprint(): re-run P0 from empty caches (registration §3.3, §3.4)")
    SC.req(summ.get("dependencies") == P.DEPENDENCIES, "the P0 record's dependency list differs from screen01_pool.DEPENDENCIES")
    SC.req(all(v.get("error_rows") == [] for v in summ["pools"].values()), "P0: a pool member's gate evaluation raised (error_rows must be empty, registration §3.3)")
    SC.req(dc["design_admissible"] and dc["rand3"]["complete"] and summ["pools"]["rand3"]["complete"], "P0: design not admissible or random-control set incomplete (registration §3.3)")
    SC.req((ROOT / BOUND_EVIDENCE[0]).exists(), "infra_signatures.json (the §9 INFRA_LOSS signature table) is missing: freeze 1 is not written (registration §10)")
    SB.emit(SB.states_files(), True)   # states.json and every raw re-derive byte for byte
    rows = SB.p0_record()[1]
    man = json.loads((SB.P0 / "pools.json").read_text())["pools"]["manual"]
    paths = [REG, ADOPTION, "docs/evidence/screen01_2026_10_30/decision_memo.md", *BOUND_EVIDENCE, "scripts/screen01/*.py", "tests/screen01/*.py", "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1",
             "docs/evidence/screen01_2026_10_30/states.json", "docs/evidence/screen01_2026_10_30/inputs", "docs/evidence/screen01_2026_10_30/oc.json", *REUSED]
    extra = {"status": "plan and sources frozen (freeze 1); REGISTERED_FROZEN from freeze 2", "plan_review": "one, three angles, registration §12", "source_review": "one, registration §13",
             "p0": {"fingerprint": summ["fingerprint"], "n_dependencies": len(summ["dependencies"]), "parent_stl": summ["parent_stl"],
                    "stl_sha256": {n: r["x1"]["stl_sha256"] for n, r in sorted(rows.items()) if r["admissible"]},
                    "ladder": {"specs": man, "M": {k: v for k, v in summ["pools"]["manual"].items() if k.startswith("M_for")}},
                    "random_control": {"names": summ["pools"]["rand3"]["control_set"], "abs_u_inf": dc["rand3"]["abs_u_inf"], "n_consumed": dc["rand3"]["n_consumed"]},
                    "design": {"names": dc["design_points"], "abs_u_inf": dc["abs_u_inf_design"], "rank": dc["rank"], "cond": dc["cond"]}},
             "analysis_sha256": {"fid01": SC.sha256_path(ROOT / FID_ANALYSIS), "unc01": SC.sha256_path(ROOT / UNC_ANALYSIS)}}
    return record("freeze1", paths, extra)


def freeze2(smoke_table):
    check_tools()
    SB.emit(SB.campaign_files("g1"), True)
    rec, files = campaign_record("screen01", smoke_table)
    return record("freeze2", [SB.rel(EV / "freeze1.json"), REG, *files, *smoke_dirs("smoke")], {"status": "REGISTERED_FROZEN (freeze 2)", "campaign": rec})


def budget(path: Path, expected: dict, finished: set) -> dict:
    """The analyzer's §4.3 record (`analyze_screen01.py budget --out`), the only budget source: it must exist, say `go`, list exactly the finished formal kernels and exactly the unfinished
    ones (`expected` = {kernel: estimate_s}, the campaigns being frozen; an R-best that is dropped lowers them), each with that estimate, and add up."""
    SC.req(path is not None and path.is_file(), f"budget record missing: {path} (run `analyze_screen01.py budget --finished ... --pending ... --out`)")
    b = SC.jload(path)
    SC.req(b.get("kind") == "screen01_budget_decision" and b.get("rule") == "registration §4.3" and b.get("cap_s") == CAP_S, f"{path.name}: not the registered §4.3 budget record")
    SC.req(b["decision"] == "go" and b["T_s"] <= CAP_S, f"the budget record says {b['decision']} (T = {b['T_s']:.0f} s, cap {CAP_S} s): the pushes stop and the decision goes to the user (registration §4.3)")
    SC.req(set(b["finished_session_wall_s"]) == finished, f"the budget record's finished kernels are not exactly {sorted(finished)}")
    SC.req(set(b["pending_estimate_s"]) == set(expected) and all(v and set(v) == {expected[k]} for k, v in b["pending_estimate_s"].items()),
           f"the budget record's pending kernels / estimates differ from the campaigns being frozen: {expected}")
    SC.req(math.isclose(sum(b["finished_session_wall_s"].values()) + sum(map(sum, b["pending_estimate_s"].values())), b["T_s"], rel_tol=1e-9), "the budget record's T_s is not the sum of its parts")
    return {**b, "record_sha256": SC.sha256_path(path)}


def freeze2_1(rs_path, budget_path=None, smoke_table=None):
    check_tools()
    rs = json.loads(rs_path.read_text())
    invalid = SB.invalid_at_step_2(rs)
    files = {} if invalid else SB.campaign_files("g2", rs_path)
    SB.emit(files, True)
    paths = [SB.rel(EV / "freeze2.json"), SB.rel(rs_path.resolve()), REG]
    extra = {"status": "REGISTERED_FROZEN (freeze 2.1)", "rs_json_sha256": SC.sha256_path(rs_path), "invalid_at_step_2": invalid,
             "g2": "none (invalid_at_step_2: the outcome is decided, registration §5.4)" if invalid else "none (no proposal; no g2 kernel, registration §2)"}
    if files:
        states = json.loads(SB.STATES_G2.read_text())["states"]
        camp, cfiles = campaign_record("screen01_g2", smoke_table)
        gating = {g["name"]: g for g in rs["gating"]}
        # §4.3: every unfinished formal kernel counts, the confirmation kernels at their registered run counts (the finalist, hence an empty R-best, is not known yet)
        expected = {"g2": camp["kernels"]["g2"]["estimate_s"], **{k: SB.max_estimate_s(k) for k in SB.FORMAL if k.startswith("f")}}
        extra.update(g2=camp, budget=budget(budget_path, expected, {"g1k11", "g1k12"}), proposals={n: {**{k: r[k] for k in (
            "order", "u", "spec", "step_mm", "direction_sha256_fortran_raw", "state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256")}, "gating_row": gating[n]}
            for n, r in states.items()})
        paths += [SB.rel(SB.STATES_G2), SB.rel(EV / "inputs"), SB.rel(budget_path.resolve()), *cfiles, *smoke_dirs("smoke_g2")]
    return record("freeze2_1", paths, extra)


def handoff_skeleton(fin: str, rows: dict, rs: dict, camps: dict) -> dict:
    """§11 with every hash known at freeze 3: the identity of the parent and finalist and the finalist's admissibility row (P0 row, or the rs.json gating row of a proposal)."""
    pick = lambda r: {k: r.get(k) for k in ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "direction_sha256_fortran_raw", "step_mm", "spec")}  # noqa: E731
    adm = SB.p0_record()[1].get(fin) or next(g for g in rs["gating"] if g["name"] == fin)
    return {"parent": {"name": SB.PARENT, **pick(rows[SB.PARENT])}, "finalist": {"name": fin, **pick(rows[fin]), "admissibility_row": adm}, "gate_profile_sha256": SC.sha256_path(ROOT / PROFILE),
            "policy_sha256": SC.sha256_path(ROOT / POLICY), "campaigns": camps, "registration_sha256": SC.sha256_path(ROOT / REG), "adoption_sha256": SC.sha256_path(ROOT / ADOPTION),
            "source_review_adoption_sha256": SC.sha256_path(ROOT / BOUND_EVIDENCE[3]), "phases": {"exploration": [11, 12], "confirmation_flow_32": [13, 14, 15, 16],
            "confirmation_flow_48": [13, 14]}, "z": "in-plane placement phases only; z never moves"}


def freeze3(finalist_path, rs_path, budget_path=None, smoke_f=None, smoke_f48=None):
    """Always written after `finalist`; the campaigns, budget record and handoff skeleton only when F is pushed (a finalist exists and the G1 chain controls are clean, §5.4)."""
    check_tools()
    fin = json.loads(finalist_path.read_text())
    SC.req(SC.sha256_path(rs_path) == SC.jload(EV / "freeze2_1.json")["rs_json_sha256"], "rs.json is not the one frozen in freeze2_1.json")
    invalid = SB.invalid_at_step_2(fin)
    pushed = bool(fin.get("finalist")) and not invalid
    paths = [SB.rel(EV / "freeze2_1.json"), SB.rel(finalist_path.resolve()), SB.rel(rs_path.resolve()), REG]
    extra = {"status": "REGISTERED_FROZEN (freeze 3)", "finalist_json_sha256": SC.sha256_path(finalist_path), "finalist": fin.get("finalist"), "r_best": fin.get("r_best"),
             "invalid_at_step_2": invalid, "pushed": pushed}
    if pushed:
        SB.emit(SB.campaign_files("f", finalist_path=finalist_path), True)
        rows, rs = SB.load_rows(), json.loads(rs_path.read_text())
        f_kernels = SB.f_kernels(rows, fin["finalist"], fin.get("r_best"))
        camps, files = {}, []
        for cid, table in (("screen01_f", smoke_f), ("screen01_f48", smoke_f48)):
            camps[cid], cf = campaign_record(cid, table)
            files += cf
        expected = {k: SB.FB.estimate_s(v) for ks in f_kernels.values() for k, v in ks.items() if k in SB.FORMAL}
        extra.update(campaigns=camps, budget=budget(budget_path, expected, {"g1k11", "g1k12"} | ({"g2"} if SB.STATES_G2.exists() else set())),
                     handoff_skeleton=handoff_skeleton(fin["finalist"], rows, rs, camps))
        paths += [SB.rel(budget_path.resolve()), *files, *smoke_dirs("smoke_f", "smoke_f48")]
    return record("freeze3", paths, extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["freeze1", "freeze2", "freeze2_1", "freeze3"])
    ap.add_argument("--rs", type=Path, default=EV / "rs.json")
    ap.add_argument("--finalist", type=Path, default=EV / "finalist.json")
    ap.add_argument("--budget", type=Path, help="freeze2_1 (when a G2 campaign exists) and freeze3 (when F is pushed): the record written by `analyze_screen01.py budget --out`")
    ap.add_argument("--smoke-table", type=Path, help="freeze2: the screen01 smoke table (kernel g1k11); freeze2_1: the screen01_g2 smoke table (kernel g2)")
    ap.add_argument("--smoke-table-f", type=Path, help="freeze3: the screen01_f smoke table (kernel f32smk)")
    ap.add_argument("--smoke-table-f48", type=Path, help="freeze3: the screen01_f48 smoke table (kernel f48smk)")
    a = ap.parse_args()
    print({"freeze1": freeze1, "freeze2": lambda: freeze2(a.smoke_table), "freeze2_1": lambda: freeze2_1(a.rs, a.budget, a.smoke_table),
           "freeze3": lambda: freeze3(a.finalist, a.rs, a.budget, a.smoke_table_f, a.smoke_table_f48)}[a.kind]())


if __name__ == "__main__":
    main()
