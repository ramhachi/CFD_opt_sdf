"""Pre-registration engineering probe (timing/cells/convergence only; forces are never printed): v18 parent on V2/V3 refinements of the X3 template."""
import hashlib, json, re, shutil, sys
from pathlib import Path
ROOT = Path("/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/dreamy-wu-de3512")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import unc01_u3_prepare as U
import prepare_kaggle_xfid_gridphase_x3 as x3
OUT = Path(sys.argv[1])
LEVELS = {"V2": ((50, 26, 18), 3000), "V3": ((100, 52, 36), 6000)}
st = U.states_bytes(["v18__parent"])["v18__parent"]
blob, rec = U.export(st, json.loads(U.PROFILE.read_text()))
assert rec["stl_sha256"] == "41ceb0c6f75ab465d4d85627c53fe8c5333a36a53baba0515dff535ff80fd626", rec["stl_sha256"]
shift = x3.phase_cases("v18__parent", "probe", 1, start=49)[0]["shift_m"]
for lev, (cells, end) in LEVELS.items():
    ds = OUT / f"ds_{lev}"; kd = OUT / f"kernel_{lev}"
    (ds / "states").mkdir(parents=True); kd.mkdir(parents=True)
    (ds / "states/v18__parent.stl").write_bytes(blob)
    src = x3.R5 / "case_template"
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if f.is_file() and rel.as_posix() != "constant/triSurface/design_candidate.stl":
            (ds / "case_template" / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, ds / "case_template" / rel)
    bm = ds / "case_template/system/blockMeshDict"
    t = bm.read_text(); t2 = t.replace("(25 13 9)", "(%d %d %d)" % cells); assert t2 != t; bm.write_text(t2)
    cd = ds / "case_template/system/controlDict"
    t = cd.read_text(); t2 = re.sub(r"endTime\s+3000;", f"endTime         {end};", t); assert ("3000" in t); cd.write_text(t2)
    shutil.copy2(x3.R5 / "openfoam_package_lock.json", ds / "openfoam_package_lock_jammy.json")
    shutil.copy2(x3.NOBLE / "openfoam_package_lock.json", ds / "openfoam_package_lock_noble.json")
    c = json.loads((ROOT / "docs/evidence/unc01_2026_10_20/u3/u3_criteria.json").read_text())
    c.update(round_id=f"fid01_probe_{lev}", purpose="pre-registration timing probe", states={"v18__parent": {"file": "states/v18__parent.stl", "sha256": rec["stl_sha256"], "triangles": rec["triangles"]}},
             not_run_export_gate=[], stage_timeout_s=8 * 3600, launch_deadline_hours=20.0,
             inputs={q.relative_to(ds).as_posix(): hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(ds.rglob("*")) if q.is_file()},
             case_order=[{"id": f"probe_{lev}_49p", "state": "v18__parent", "shift_m": shift}])
    text = json.dumps(c, indent=2, sort_keys=True) + "\n"; dig = hashlib.sha256(text.encode()).hexdigest()
    (ds / "x3_criteria.json").write_text(text); (ds / "x3_criteria.json.sha256").write_text(dig + "\n")
    slug = f"ramhachi888/fid01-probe-{lev.lower()}-inputs"
    (ds / "dataset-metadata.json").write_text(json.dumps({"id": slug, "title": slug.split("/")[1], "licenses": [{"name": "other"}]}))
    runner = re.sub(r'CRITERIA_SHA256 = "[^"]*"', f'CRITERIA_SHA256 = "{dig}"', U.X3_RUNNER.read_text(), count=1)
    (kd / "runner.py").write_text(runner)
    meta = json.loads((U.X3_RUNNER.parent / "kernel-metadata.json").read_text()); meta.update(id=f"ramhachi888/fid01-probe-{lev.lower()}", title=f"fid01-probe-{lev.lower()}", dataset_sources=[slug])
    (kd / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))
    print(lev, kd, ds)
