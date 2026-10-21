#!/usr/bin/env python3
"""FID-01 (#62, M3a) freeze records (registration §11): SHA-256 of every bound file at a clean, pushed commit.

    python scripts/fid01/fid01_freeze.py freeze1                      # plan, sources, designs, states, raws, export, STLs, OC
    python scripts/fid01/fid01_freeze.py freeze2 --levels V1,V2,V3    # flow_32 campaign + prerun freeze, V1 criteria, OpenFOAM smoke, of_levels
    python scripts/fid01/fid01_freeze.py freeze3                      # d_set, flow_48 campaign + prerun freeze, V2/V3 criteria
    python scripts/fid01/fid01_freeze.py freeze4 --main analysis.json # §6.8 extension: the main analysis and the extension criteria
Refuses to overwrite, on a dirty tracked tree, or when HEAD is not on a remote branch.
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
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
from cfd_harness import campaign_schema as SC  # noqa: E402

EV = ROOT / "docs/evidence/fid01_2026_10_21"
REG = "docs/fid01_registration_2026_10_21.md"
REUSED = ["scripts/v18_plate.py", "scripts/mode01_v18_prescreen.py", "scripts/mode01_prescreen.py", "scripts/mode01_modes.py", "scripts/step01_states.py",
          "scripts/geom02_canonical.py", "scripts/build_xfid45_stage_v_input_2026_10_04.py", "scripts/prepare_kaggle_xfid_gridphase_x3.py",
          "scripts/unc01_u3_prepare.py", "scripts/unc01_build.py", "scripts/unc01_verify.py", "scripts/analyze_unc01.py", "scripts/width_rule_study.py",
          "scripts/local_openfoam.py", "src/cfd_sdf/fd08_v2_campaign.py", "infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py",
          "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template", "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json",
          "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json", "infra/local_openfoam/local_openfoam_lock.json",
          "docs/evidence/unc01_2026_10_20/analysis.json", "docs/evidence/unc01_2026_10_20/states.json", "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json",
          "docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json", "docs/architecture_effectiveness_2026_09.md"]


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
    rec = {"kind": f"fid01_{kind}", "registration": REG, "source_commit": head, "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "file_sha256": {f: SC.sha256_path(ROOT / f) for f in files},
           "environment": {"python": platform.python_version(), **{m: importlib.metadata.version(m) for m in ("numpy", "scipy", "scikit-image")}},
           "harness_tool_sha256": SC.tool_hashes(), "qualification_flags": "all false (unchanged)", "shape_update_allowed": False, **extra}
    target.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return target


def criteria_hashes(stage):
    import fid01_build as B
    names = [k for k, (lev, _) in B.of_kernels(stage=stage).items()]
    return sorted(SC.sha256_path(EV / "of/criteria" / f"{k}.json") for k in names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["freeze1", "freeze2", "freeze3", "freeze4"])
    ap.add_argument("--levels", default="V1,V2,V3")
    ap.add_argument("--main", type=Path)
    a = ap.parse_args()
    if a.kind == "freeze1":
        d = json.loads((EV / "designs.json").read_text())["designs"]
        filled = [v for v in d.values() if v]
        SC.req(len(filled) >= 12 and len({v["family"] for v in filled}) >= 4, "fewer than 12 designs or 4 families (registration §3.2)")
        paths = [REG, "scripts/fid01", "tests/fid01", "docs/evidence/fid01_2026_10_21/designs.json", "docs/evidence/fid01_2026_10_21/states.json",
                 "docs/evidence/fid01_2026_10_21/inputs", "docs/evidence/fid01_2026_10_21/of/export.json", "docs/evidence/fid01_2026_10_21/oc.json",
                 "docs/evidence/fid01_2026_10_21/p0_probe", "docs/harness/fid01_campaign.json", *REUSED]
        exp = json.loads((EV / "of/export.json").read_text())["exports"]
        extra = {"status": "plan and sources frozen (freeze 1); REGISTERED_FROZEN from freeze 2", "stl_sha256": {k: v["stl_sha256"] for k, v in exp.items()},
                 "plan_review": "one, three angles (numerical 16, controls 14, strategy 14 findings), registration §12a", "source_review": "one, registration §13"}
        print(record("freeze1", paths, extra))
    elif a.kind == "freeze2":
        levels = a.levels.split(",")
        SC.req(levels in (["V1", "V2", "V3"], ["V1", "V2"]), "of_levels must be V1,V2,V3 or V1,V2 (§5.3 contingency)")
        paths = ["docs/evidence/fid01_2026_10_21/freeze1.json", "docs/harness/fid01_campaign.json", "docs/harness/fid01_campaign.prerun_freeze.json",
                 "docs/evidence/fid01_2026_10_21/of/criteria", "docs/evidence/fid01_2026_10_21/of/smoke", "infra/fid01", "docs/evidence/fid01_2026_10_21/p0_probe", REG]
        extra = {"status": "REGISTERED_FROZEN (freeze 2)", "of_levels": levels, "of_criteria_sha256": criteria_hashes("v1")}
        print(record("freeze2", paths, extra))
    elif a.kind == "freeze4":
        main = json.loads(a.main.read_text())
        SC.req(main["outcome"] == "EXTENSION_REQUIRED", "freeze 4 only for a main analysis that requires the extension")
        crit = sorted(SC.sha256_path(p) for p in (EV / "of/ext_criteria").glob("*.json"))
        extra = {"status": "REGISTERED_FROZEN (freeze 4, §6.8 extension)", "main_analysis_sha256": SC.sha256_path(a.main), "of_criteria_sha256": crit,
                 "extension_plan": main["extension_plan"]}
        print(record("freeze4", ["docs/evidence/fid01_2026_10_21/freeze3.json", "docs/evidence/fid01_2026_10_21/of/ext_criteria", "infra/fid01",
                                 str(a.main.resolve().relative_to(ROOT))], extra))
    else:
        paths = ["docs/evidence/fid01_2026_10_21/freeze2.json", "docs/evidence/fid01_2026_10_21/d_set.json", "docs/harness/fid01_f48_campaign.json",
                 "docs/harness/fid01_f48_campaign.prerun_freeze.json", "docs/evidence/fid01_2026_10_21/of/criteria", "infra/fid01", REG]
        extra = {"status": "REGISTERED_FROZEN (freeze 3)", "of_criteria_sha256": criteria_hashes("v23"), "d_set_sha256": SC.sha256_path(EV / "d_set.json")}
        print(record("freeze3", paths, extra))


if __name__ == "__main__":
    main()
