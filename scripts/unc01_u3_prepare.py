#!/usr/bin/env python3
"""UNC-01 U3 (#61, registration §6): OpenFOAM inputs for the U2 flow_32 states.

The harness bytes of every state (rebuilt from the parent and direction raws, checked against states.json) go through the GEOM-02 / XFID r = 8
export (geom02_canonical.export_from_state) and the X1 practical gate on the double mesh and on the float32 STL; the 32 registered rigid shifts are
the X3 generator at Halton indices 33-48 (16 exact mirror pairs, disjoint from X2/X3), identical for every state, pair-major order.  The runner is
the X3 formal runner byte for byte except the bound criteria SHA (it discovers `x3_criteria.json`, so the criteria keep that file name).

    python scripts/unc01_u3_prepare.py prepare --u1 SEL [--smoke] [--dataset DIR]
    python scripts/unc01_u3_prepare.py strip-smoke RESULT_IN RESULT_OUT      # the archived smoke copy without force fields
Writes docs/evidence/unc01_2026_10_20/u3[/smoke]/{u3_criteria.json(+.sha256),export.json}, the dataset directory (untracked, under work/; STLs are re-derivable)
and infra/kaggle/kernel_unc01_u3[_smoke]/{runner.py,kernel-metadata.json}.  Refuses to overwrite different criteria.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import build_xfid45_stage_v_input_2026_10_04 as x1  # noqa: E402
import prepare_kaggle_xfid_gridphase_x3 as x3  # noqa: E402
import step01_states as S  # noqa: E402
import unc01_build as B  # noqa: E402

PROFILE = ROOT / "docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json"   # the prescreen's gate profile (export r = 8, sub-cell components 25 mm)
X3_RUNNER = ROOT / "infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py"
KERNEL = ROOT / "infra/kaggle/kernel_unc01_u3"
OUT = B.OUT / "u3"
SLUG, DATASET_SLUG = "ramhachi888/cfd-opt-sdf-unc01-u3", "ramhachi888/cfd-opt-sdf-unc01-u3-inputs"
HALTON_START, N_PAIRS = 33, 16


def states_bytes(names):
    """name -> SDFDesignState rebuilt the way the harness runner does; Fortran SHA must equal states.json."""
    import mode01_modes as M
    rec = json.loads((B.OUT / "states.json").read_text())
    parent, _ = B.load_parent()
    raw = S.read_f4(ROOT / B.PARENT_RAW)
    out = {}
    for n in names:
        r = rec["states"][n]
        phi = raw if r["direction"] is None else S.perturb(raw, S.read_f4(ROOT / B.dir_rel(n)), r["step_mm"], r["sign"])
        if S.sha256_bytes(S.to_raw(phi)) != r["phi_fortran_order_sha256"]:
            raise SystemExit(f"{n}: rebuilt phi differs from states.json")
        out[n] = parent if r["direction"] is None else M.with_phi(parent, np.ascontiguousarray(phi, dtype="<f4"))
    return out


def export(state, profile):
    import geom02_canonical as canon
    e = canon.export_from_state(state, profile)
    origin = np.asarray(state.origin_m, dtype=np.float64)
    gd, md = x1.gates(e["vertices"], e["faces"], state.phi, origin)
    blob = x1.stl_bytes(e["vertices"], e["faces"])
    v32, f32 = x1.read_stl(blob)
    g32, m32 = x1.gates(v32, f32, state.phi, origin)
    return blob, {"double_gates": gd, "double_measures": md, "float32_stl_gates": g32, "float32_stl_measures": m32, "removed_components": e["removed_components"],
                  "triangles": int(len(e["faces"])), "stl_sha256": hashlib.sha256(blob).hexdigest(),
                  "pass": bool(gd["practical_gate_pass"] and g32["practical_gate_pass"])}


def case_order(states):
    by = {s: x3.phase_cases(s, "u3", N_PAIRS, start=HALTON_START) for s in states}
    return [by[s][i] for i in range(2 * N_PAIRS) for s in states]   # pair-major: all states of a shift before the next


def strip_smoke(src: Path, dst: Path) -> dict:
    """The development smoke keeps statuses, stage return codes, mesh statistics and times only: force fields are removed (registration §6)."""
    res = json.loads(src.read_text())
    for c in res.get("cases", []):
        c.pop("forces", None)
    res["forces_removed_from"] = {"path": src.name, "sha256": B.sha(src)}
    dst.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "strip-smoke"])
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--u1", type=Path, help="U1 selection record (analyze_unc01.py u1)")
    ap.add_argument("--smoke", action="store_true", help="development smoke: all states at the first shift only")
    ap.add_argument("--dataset", type=Path)
    a = ap.parse_args()
    if a.cmd == "strip-smoke":
        strip_smoke(*a.paths)
        return
    sel = json.loads(a.u1.read_text())
    if sel.get("verdict") != "SELECTED":
        raise SystemExit("needs a SELECTED U1 record")
    L, L2 = sel["selection"]["L"], sel["selection"]["L2"]
    tag = "_smoke" if a.smoke else ""
    out, kdir = OUT / ("smoke" if a.smoke else ""), KERNEL.with_name(KERNEL.name + tag)
    slug, dslug = SLUG + tag.replace("_", "-"), DATASET_SLUG.replace("-inputs", tag.replace("_", "-") + "-inputs")
    dataset = a.dataset or ROOT / f"work/kaggle_unc01_u3{tag}_dataset"
    names = B.u2_states(L, L2)["flow_32"]
    profile = json.loads(PROFILE.read_text())
    if dataset.exists():
        shutil.rmtree(dataset)
    (dataset / "states").mkdir(parents=True)
    exports, info, not_run = {}, {}, []
    for n, st in states_bytes(names).items():
        blob, rec = export(st, profile)
        exports[n] = rec
        print(n, rec["pass"], rec["triangles"], flush=True)
        if rec["pass"]:
            (dataset / f"states/{n}.stl").write_bytes(blob)
            info[n] = {"file": f"states/{n}.stl", "sha256": rec["stl_sha256"], "triangles": rec["triangles"]}
        else:
            not_run.append(n)
    for src in sorted((x3.R5 / "case_template").rglob("*")):
        rel = src.relative_to(x3.R5 / "case_template")
        if src.is_file() and rel.as_posix() != "constant/triSurface/design_candidate.stl":
            (dataset / "case_template" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dataset / "case_template" / rel)
    shutil.copy2(x3.R5 / "openfoam_package_lock.json", dataset / "openfoam_package_lock_jammy.json")
    shutil.copy2(x3.NOBLE / "openfoam_package_lock.json", dataset / "openfoam_package_lock_noble.json")
    x3c = json.loads((x3.EVID / "formal/x3_criteria.json").read_text())
    order = case_order(list(info))
    if a.smoke:
        order = order[:len(info)]   # every state at the first shift (Halton 33, +)
    criteria = {
        "round_id": "unc01_u3" + ("_smoke" if a.smoke else "_r1"), "date": "2026-10-20", "registration": "docs/unc01_registration_2026_10_20.md §5.6, §6",
        "evidence_class": "unc01_u3_openfoam_phase_ensemble_uncertified_geometry" + (" (development smoke: statuses only)" if a.smoke else ""),
        "purpose": f"UNC-01 U3: the U2 flow_32 states of the v18 parent (L = {L}, L2 = {L2}) x 32 registered rigid shifts (X3 generator, Halton 33-48, 16 exact mirror "
                   "pairs, disjoint from X2/X3), identical shifts for every state, on the XFID X3 coarse Stage V mesh" + ("; smoke: first shift only" if a.smoke else ""),
        "u1_selection_sha256": B.sha(a.u1),
        "environment": x3c["environment"], "force_window": x3c["force_window"], "stage_timeout_s": x3c["stage_timeout_s"],
        "per_case_failure_policy": x3c["per_case_failure_policy"], "stop_after_consecutive_failures": 3, "launch_deadline_hours": 9.0,
        "case_template_origin": x3c["case_template_origin"],
        "shift_design": {**x3c["shift_design"], "halton_index_range": [HALTON_START, HALTON_START + N_PAIRS - 1]},
        "states": info, "not_run_export_gate": not_run,
        "export": {"pipeline": "geom02_canonical.export_from_state (r = 8) + X1 practical gate (double and float32 STL)", "profile": str(PROFILE.relative_to(ROOT)),
                   "profile_sha256": B.sha(PROFILE)},
        "inputs": {q.relative_to(dataset).as_posix(): B.sha(q) for q in sorted(dataset.rglob("*")) if q.is_file()},
        "case_order": order,
        "analysis": {"script": "scripts/analyze_unc01.py u2", "rule": "registration §5.6: mirror-pair means of matched-shift differences vs the parent, retention vs the WaterLily flow_32 U2 mean"},
        "qualification_flags": x3c["qualification_flags"], "immutable": True, "registered_before_run": True,
    }
    text = json.dumps(criteria, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    out.mkdir(parents=True, exist_ok=True)
    target = out / "u3_criteria.json"
    if target.exists() and target.read_text() != text:
        raise SystemExit("refusing to overwrite different U3 criteria")
    for path in (target, dataset / "x3_criteria.json"):
        path.write_text(text)
        path.with_name(path.name + ".sha256").write_text(digest + "\n")
    (out / "export.json").write_text(json.dumps({"kind": "unc01_u3_export", "L": L, "L2": L2, "states": exports, "criteria_sha256": digest}, indent=1, sort_keys=True) + "\n")
    (dataset / "dataset-metadata.json").write_text(json.dumps({"title": dslug.split("/")[1], "id": dslug, "licenses": [{"name": "other"}]}, indent=2, sort_keys=True) + "\n")
    kdir.mkdir(exist_ok=True)
    runner = re.sub(r'CRITERIA_SHA256 = "[^"]*"', f'CRITERIA_SHA256 = "{digest}"', X3_RUNNER.read_text(), count=1)
    (kdir / "runner.py").write_text(runner)
    meta = json.loads((X3_RUNNER.parent / "kernel-metadata.json").read_text())
    meta.update({"id": slug, "title": slug.split("/")[1], "dataset_sources": [dslug]})
    (kdir / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"criteria_sha256": digest, "states": list(info), "not_run_export_gate": not_run, "cases": len(order), "kernel": str(kdir.relative_to(ROOT))}))


if __name__ == "__main__":
    main()
