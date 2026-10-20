#!/usr/bin/env python3
"""UNC-01 (#61) freeze records (registration §9): SHA-256 of every bound file at a clean, pushed commit.

    python scripts/unc01_freeze.py freeze1   # docs/evidence/unc01_2026_10_20/freeze1.json (refuses unless regate passed and is identical)
    python scripts/unc01_freeze.py freeze2   # docs/evidence/unc01_2026_10_20/freeze2.json (U1 selection, U2 campaign + harness freeze, U3 criteria/smoke/runner)
Refuses to overwrite, on a dirty tracked tree, or when HEAD is not on origin.
"""
from __future__ import annotations

import datetime
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import unc01_build as B  # noqa: E402
from cfd_harness import campaign_schema as SC  # noqa: E402

EV = B.OUT
FREEZE1 = ["docs/unc01_registration_2026_10_20.md", "scripts/unc01_build.py", "scripts/analyze_unc01.py", "scripts/unc01_u3_prepare.py", "scripts/unc01_freeze.py",
           "tests/test_unc01.py", "scripts/step01_states.py", "scripts/v18_plate.py", "scripts/mode01_v18_prescreen.py", "scripts/mode01_prescreen.py",
           "scripts/mode01_modes.py", "scripts/geom02_canonical.py", "scripts/build_xfid45_stage_v_input_2026_10_04.py", "scripts/xfid45_round3_export.py",
           "scripts/prepare_kaggle_xfid_gridphase_x3.py", "scripts/fd08_v2_campaign_io.py", "src/cfd_sdf/fd08_v2_campaign.py",
           "docs/evidence/unc01_2026_10_20/states.json", "docs/evidence/unc01_2026_10_20/regate.json", "docs/evidence/unc01_2026_10_20/inputs",
           "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz", B.PARENT_RAW, "docs/evidence/v18_genesis_2026_10_19/genesis.json",
           "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json", "docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json",
           "docs/evidence/grid02_trend_2026_10_16/grid02_analysis.json", "docs/evidence/job02_gate_2026_10_19/state_force_table.json",
           "docs/architecture_effectiveness_2026_09.md", "infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py",
           "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template", "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json",
           "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json", "docs/evidence/xfid_gridphase_x3_2026_10_04/formal/x3_criteria.json",
           "docs/harness/unc01_u01_campaign.json"]
FREEZE2 = ["docs/evidence/unc01_2026_10_20/freeze1.json", "docs/evidence/unc01_2026_10_20/u01/u1_selection.json", "docs/harness/unc01_u2_campaign.json",
           "docs/harness/unc01_u2_campaign.prerun_freeze.json", "docs/evidence/unc01_2026_10_20/u3/u3_criteria.json", "docs/evidence/unc01_2026_10_20/u3/export.json",
           "docs/evidence/unc01_2026_10_20/u3/smoke", "infra/kaggle/kernel_unc01_u3/runner.py", "infra/kaggle/kernel_unc01_u3/kernel-metadata.json",
           "docs/unc01_registration_2026_10_20.md", "scripts/unc01_verify.py", "scripts/analyze_unc01.py", "docs/evidence/unc01_2026_10_20/u01/state_force_table.json",
           "docs/evidence/unc01_2026_10_20/u01/u0_gate.json"]


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()


def record(kind, paths, extra):
    target = EV / f"{kind}.json"
    SC.req(not target.exists(), f"refusing to overwrite {target.name}")
    SC.req(not git("status", "--porcelain", "--untracked-files=no"), "tracked files have uncommitted changes")
    head = git("rev-parse", "HEAD")
    git("fetch", "-q", "origin")
    SC.req(any(subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", head, h.split()[0]]).returncode == 0
               for h in git("ls-remote", "--heads", "origin").splitlines()), "HEAD is not on a remote branch: push first")
    for p in paths:
        SC.req(subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", p], capture_output=True).returncode == 0, f"not tracked: {p}")
    rec = {"kind": f"unc01_{kind}", "registration": "docs/unc01_registration_2026_10_20.md", "source_commit": head,
           "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "file_sha256": {p: SC.sha256_path(ROOT / p) for p in paths},
           "environment": {"python": platform.python_version(), **{m: importlib.metadata.version(m) for m in ("numpy", "scipy", "scikit-image")}},
           "harness_tool_sha256": SC.tool_hashes(), **extra}
    target.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return target


def main():
    kind = sys.argv[1]
    if kind == "freeze1":
        rg = json.loads((EV / "regate.json").read_text())
        SC.req(rg["all_pass"] and rg["identical_to_prescreen"] and rg["all_same_bytes_as_states_json"], "regate did not pass identically: freeze refused")
        extra = {"status": "plan and sources frozen (freeze 1); REGISTERED_FROZEN from freeze 2", "job02_integration_commit": "58425e70",
                 "p22_statement": "P22-v2 is applied unchanged to a second parent and is not binding by design (v18 N_phi 7544 vs cap 8272); the 10 % smoothed-volume band carries the volume constraint",
                 "plan_review": "one, three angles (numerical 19, controls 22, strategy 11 findings), registration §12", "source_review": "one, recorded in the registration §13"}
        print(record("freeze1", FREEZE1, extra))
    elif kind == "freeze2":
        sel = json.loads((EV / "u01/u1_selection.json").read_text())
        SC.req(sel.get("verdict") == "SELECTED", "freeze 2 needs a SELECTED U1 record")
        extra = {"status": "REGISTERED_FROZEN (freeze 2)", "selection": sel["selection"], "u01_table_sha256": sel["table_sha256"], "u1_analyzer_sha256": sel["analyzer_sha256"],
                 "u3_environment": "registration §15: local OpenFOAM after a passed environment gate and a REGISTERED_AMENDED record, else Kaggle CPU as frozen",
                 "freeze1_amendment1_sha256": SC.sha256_path(EV / "freeze1_amendment1.json"), "registration_sha256": SC.sha256_path(ROOT / "docs/unc01_registration_2026_10_20.md")}
        print(record("freeze2", FREEZE2, extra))
    else:
        raise SystemExit("freeze1 | freeze2")


if __name__ == "__main__":
    main()
