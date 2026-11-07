#!/usr/bin/env python3
"""Render self-contained TR-00/main CPU kernels locally; never contact Kaggle.

Geometry files must be supplied explicitly. --plan-only needs no geometry.
Every render is development until --freeze binds the clean HEAD and every
input hash, all six study geometries are declared and their source metadata
explicitly says VERIFIED. This token is a new interface; WP4 currently emits
UNVERIFIED_OCR, and the owner must substantiate verification before freeze.
Main additionally requires --qualified-cell MODEL/FAMILY after TR-00 judgment.
This renderer never pushes kernels or creates a freeze.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_rans as C
import t2d_multibody_case as M

ROOT = Path(__file__).resolve().parents[2]
# Registration §7: four workers x three waves; 3*2.5 h = 7.5 h solving,
# 3*(3*900 s) = 2.25 h generation/mesh, plus 600 s reserve fits 11 h.
MAX_RUNS, WORKERS, SESSIONS = 12, 4, 5
SESSION_S, RESERVE_S, CASE_CAP_S = 11*3600, 600, 2.5*3600
# Existing imports' transitive source dependencies; no unchanged source is copied
# into a new implementation. It is bundled byte-for-byte and imported at runtime.
SOURCE_FILES = (
    "scripts/t20_case.py", "scripts/t20_foam.py",
    "scripts/analyze_t20b.py", "scripts/analyze_t20c.py", "scripts/build_t20a_kernel.py",
    "scripts/topo2d00/t2d_multibody_case.py", "scripts/topo2d00/t2d_foam_case.py",
    "scripts/topo2d00/collect_rans.py", "scripts/topo2d00/run_rans.py",
    "scripts/topo2d00/build_tr00_kernels.py", "docs/topo2d00_registration_2026_11_01.md",
    "infra/kaggle/kernel_t20b_cpu/runner.py",
    "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json",
    "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json",
    "data/t20/tyrrell026s_genua2009.dat",
    "docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_result_schema.json",
    "docs/codex/gen01_w1_2026_11_06/reports/topo2d00_rans_measurement_schema.json",
)


def make_plan(stage: str, qualified_cells=None) -> dict:
    if stage == "smoke":
        # Each case proves its mesh gate, then solves on THAT mesh. A separate
        # mesh-only spec would make an unintended second gmsh realization.
        runs = [{"config": c, "model": "sa-wf", "family": "fine30", "realisation": 0, "iters": 200,
                 "cont_iters": None, "mode": "smoke", "case_cap_s": 900} for c in ("E2_sharp", "E2")]
    else:
        runs = [{**k, "iters": 5000, "cont_iters": 15000, "mode": "production", "case_cap_s": CASE_CAP_S}
                for k in C.expected_runs(stage, qualified_cells)]
    chunks = [runs[i:i+MAX_RUNS] for i in range(0, len(runs), MAX_RUNS)]
    return {"schema_version": "topo2d00-run-plan-v1", "stage": stage, "ready_for_execution": False,
            "render_kind": "development", "push_plan": [],
            "blocked_reason": "development plan: clean source, freeze1 and verified study geometry have not been bound",
            "qualified_cells": [list(c) for c in qualified_cells] if qualified_cells is not None else None,
            "workers": WORKERS, "session_budget_s": SESSION_S, "reserve_s": RESERVE_S,
            "max_concurrent_sessions": SESSIONS, "runs": runs,
            "kernels": [{"name": f"{stage}_{i+1:02d}", "wave": i//SESSIONS+1, "runs": chunk} for i, chunk in enumerate(chunks)],
            "cost_estimate": {
                "historical_5000_min": [13, 21], "historical_source": "TOPO-2D-00 registration section 7",
                "source_caveat": "T2-0 summary associates 13-21 min with xfine30, fine30 with 6-11; multibody timing is unmeasured",
                "conservative_5000_min": 60, "continuation_factor": 3,
                "planning_wave_hours": 9, "hard_session_hours": 11,
                "cpu_budget_h": 160, "estimate_is_measurement": False,
                "global_budget_enforced": False,
                "global_budget_accounting": "User must maintain the 160 CPU h study ledger across all sessions before launching and while running",
                "unconstrained_case_cap_total_h": len(runs)*CASE_CAP_S/3600 if stage != "smoke" else None,
            }}


def _json(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for rel, data in sorted(files.items()):
            info = tarfile.TarInfo(rel)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tf.addfile(info, io.BytesIO(data))
    return gzip.compress(buffer.getvalue(), mtime=0)


WRAPPER = '''#!/usr/bin/env python3
"""Locally rendered WP5 CPU kernel. This source contains all exact run inputs.
No source checkout or qualification decision occurs during execution.
"""
import base64
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

BUNDLE_B64 = __BUNDLE__
BUNDLE_SHA256 = __DIGEST__
INPUT_SHA256 = __INPUTS__
PLAN = __PLAN__

def unpack_bundle(target):
    target = Path(target)
    if target.exists():
        raise FileExistsError("refusing to overwrite extracted source: " + str(target))
    data = base64.b64decode(BUNDLE_B64, validate=True)
    if hashlib.sha256(data).hexdigest() != BUNDLE_SHA256:
        raise ValueError("source bundle SHA mismatch")
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(data)), mode="r:") as archive:
        members = archive.getmembers()
        if len(members) != len(INPUT_SHA256) or {m.name for m in members} != set(INPUT_SHA256):
            raise ValueError("bundle inventory mismatch")
        contents = {}
        for member in members:
            rel = Path(member.name)
            if not member.isfile() or rel.is_absolute() or ".." in rel.parts:
                raise ValueError("unsafe source bundle member")
            content = archive.extractfile(member).read()
            if hashlib.sha256(content).hexdigest() != INPUT_SHA256[member.name]:
                raise ValueError("bundled source SHA mismatch: " + member.name)
            contents[member.name] = content
    target.mkdir(parents=True)
    for rel, content in contents.items():
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return target

def main():
    if not PLAN["ready_for_execution"]:
        raise ValueError(PLAN["blocked_reason"])
    working = Path(os.environ.get("TR00_WORKING", "/kaggle/working"))
    source = unpack_bundle(working / ("source_" + PLAN["kernel_name"]))
    plan_path = source / "kernel_plan.json"
    plan_path.write_text(json.dumps(PLAN, sort_keys=True, indent=2) + "\\n")
    subprocess.run([sys.executable, str(source / "scripts/topo2d00/run_rans.py"),
                    "--plan", str(plan_path), "--out", str(working / PLAN["kernel_name"])], check=True)

if __name__ == "__main__":
    main()
'''


def render(out: Path, geometries: dict[str, Path], stage="tr00", qualified_cells=None, owner="ramhachi888", *,
           study_geometries: dict[str, Path] | None = None, freeze: Path | None = None) -> dict:
    """Bundle inputs locally; freeze1 is a supplied record, never inferred.

    Freeze schema: topo2d00-rans-freeze1-v1, stage=freeze1, source_commit=HEAD,
    input_sha256=the exact bundled member/hash map, geometry_sha256=all six
    study config/hash pairs. No post-run analysis freeze is accepted here.
    """
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite: {out}")
    plan = make_plan(stage, qualified_cells)
    needed = {r["config"] for r in plan["runs"]}
    if set(geometries) != needed:
        raise ValueError(f"geometry keys must be exactly {sorted(needed)}")
    if not owner or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in owner):
        raise ValueError("invalid Kaggle owner")
    study = {c: Path(p) for c, p in geometries.items()}
    for config, path in (study_geometries or {}).items():
        if config not in M.STUDY_CONFIGS:
            raise ValueError(f"unknown study geometry: {config}")
        path = Path(path)
        if config in study and study[config].read_bytes() != path.read_bytes():
            raise ValueError(f"run and study geometry inputs differ: {config}")
        study[config] = path
    # Compute ONE family stack over the declared study, including E3_sharp.
    # Missing configurations make a development stack, never a production one.
    boundary_layers = M.boundary_layer_plan(study, require_complete=set(study) == M.STUDY_CONFIGS)
    files = {rel: (ROOT / rel).read_bytes() for rel in SOURCE_FILES}
    files["boundary_layer_plan.json"] = json.dumps(boundary_layers, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    boundary_digest = M.plan_sha256(boundary_layers)
    from build_t20a_kernel import LOCK_SHA256
    for suite, rel in (("jammy", "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json"),
                       ("noble", "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json")):
        if hashlib.sha256(files[rel]).hexdigest() != LOCK_SHA256[suite]:
            raise ValueError("OpenFOAM package lock differs from the registered T2-0 lock")
    geometry_info, verified = {}, {}
    for config, path in sorted(study.items()):
        # Loader validates the actual supplied WP4 vertices, never resampling.
        geometry = M.load_geometry(path)
        if geometry["config"] != config:
            raise ValueError(f"geometry config differs: {path}")
        rel = f"geometry/{config}{path.suffix.lower()}"
        data = path.read_bytes()
        files[rel] = data
        geometry_info[config] = {"geometry_file": rel, "geometry_sha256": hashlib.sha256(data).hexdigest(),
                                 "elements": [{"name": e["name"], "patch": e["patch"]} for e in geometry["elements"]]}
        sources = geometry.get("source_scene_metadata", {}).get("sources", [])
        # Explicit future contract; missing/unknown/UNVERIFIED_OCR is blocked.
        verified[config] = isinstance(sources, list) and bool(sources) and all(
            isinstance(s, dict) and s.get("verification") == "VERIFIED" for s in sources)
    for row in plan["runs"]:
        row.update(geometry_info[row["config"]])
        row.update(boundary_layer_plan_file="boundary_layer_plan.json", boundary_layer_plan_sha256=boundary_digest)
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"], text=True).strip())
    inputs = {p: hashlib.sha256(data).hexdigest() for p, data in sorted(files.items())}
    archive = _archive(files)
    digest = hashlib.sha256(archive).hexdigest()
    plan.update(source_commit=head, source_dirty=dirty, input_sha256=inputs, bundle_sha256=digest,
                geometry_input_sha256={c: v["geometry_sha256"] for c, v in geometry_info.items()},
                geometry_verified=verified, boundary_layer_plan_sha256=boundary_digest,
                boundary_layer_plan_scope=boundary_layers["scope"])
    failures = []
    if dirty:
        failures.append("whole source tree is dirty")
    if boundary_layers["scope"] != "study":
        failures.append("six study geometries have not been supplied")
    if not all(verified.values()):
        failures.append("all geometry source records must be explicitly VERIFIED")
    if stage == "main" and qualified_cells is None:
        failures.append("TR-00 qualification has not been supplied")
    freeze_info = {"path": None if freeze is None else str(Path(freeze).resolve()), "sha256": None, "matches": False}
    frozen = None
    if freeze is not None:
        try:
            payload = Path(freeze).read_bytes()
            freeze_info["sha256"] = hashlib.sha256(payload).hexdigest()
            frozen = json.loads(payload)
        except (OSError, ValueError, UnicodeError) as exc:
            failures.append(f"freeze1 record could not be read: {type(exc).__name__}")
    if not isinstance(frozen, dict):
        failures.append("freeze1 record is absent or invalid")
    else:
        expected = {"schema": "topo2d00-rans-freeze1-v1", "stage": "freeze1", "source_commit": head,
                    "input_sha256": inputs, "geometry_sha256": plan["geometry_input_sha256"]}
        mismatches = [key for key, value in expected.items() if frozen.get(key) != value]
        failures.extend(f"freeze1 {key} mismatch" for key in mismatches)
        freeze_info["matches"] = not mismatches
    plan.update(freeze1=freeze_info, readiness_failures=failures, ready_for_execution=not failures,
                render_kind="development" if failures else "ready", blocked_reason="; ".join(failures) if failures else None)
    if not failures:
        plan["push_plan"] = [{"name": k["name"], "directory": k["name"]} for k in plan["kernels"]]
    rendered = []
    for kernel in plan["kernels"]:
        kp = {k: v for k, v in plan.items() if k not in ("kernels", "runs")}
        kp.update(kernel_name=kernel["name"], runs=kernel["runs"])
        text = WRAPPER.replace("__BUNDLE__", repr(base64.b64encode(archive).decode())).replace("__DIGEST__", repr(digest))
        text = text.replace("__INPUTS__", repr(inputs)).replace("__PLAN__", repr(kp))
        compile(text, "runner.py", "exec")
        slug = f"cfd-opt-sdf-tr00-{kernel['name'].replace('_', '-')}"
        metadata = {"id": f"{owner}/{slug}", "title": slug, "code_file": "runner.py", "language": "python", "kernel_type": "script",
                    "is_private": True, "enable_gpu": False, "enable_internet": True,
                    "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}
        rendered.append((kernel["name"], text.encode(), _json(metadata), _json(kp)))
    # All validation completes before the destination directory is created.
    out.mkdir(parents=True)
    (out / "run_plan.json").write_bytes(_json(plan))
    (out / "source_bundle.tar.gz").write_bytes(archive)
    (out / "input_sha256.json").write_bytes(_json(inputs))
    for name, runner, metadata, kp in rendered:
        d = out / name
        d.mkdir()
        (d / "runner.py").write_bytes(runner)
        (d / "kernel-metadata.json").write_bytes(metadata)
        (d / "kernel_plan.json").write_bytes(kp)
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("tr00", "main", "smoke"), required=True)
    ap.add_argument("--geometry", action="append", default=[], metavar="CONFIG=PATH")
    ap.add_argument("--study-geometry", action="append", default=[], metavar="CONFIG=PATH",
                    help="complete six-config thick/sharp geometry set for one fixed boundary-layer stack")
    ap.add_argument("--freeze", type=Path, help="supplied topo2d00-rans-freeze1-v1 binding; absent/mismatched stays development")
    ap.add_argument("--qualified-cell", action="append", metavar="MODEL/FAMILY")
    ap.add_argument("--owner", default="ramhachi888", help="Kaggle metadata only; no API is called")
    ap.add_argument("--plan-only", action="store_true", help="write run_plan.json without claiming runnable kernels")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    cells = None
    if args.qualified_cell is not None:
        cells = [tuple(x.split("/")) for x in args.qualified_cell]
        if any(len(c) != 2 for c in cells):
            raise ValueError("qualified cells use MODEL/FAMILY")
        if args.stage != "main":
            raise ValueError("--qualified-cell applies to main only")
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite: {args.out}")
    if args.plan_only:
        if args.geometry or args.study_geometry or args.freeze:
            raise ValueError("--plan-only does not consume geometry or freeze records")
        plan = make_plan(args.stage, cells)
        plan["ready_for_execution"] = False
        plan["blocked_reason"] = "plan only: geometry and source have not been bundled"
        args.out.mkdir(parents=True)
        (args.out / "run_plan.json").write_bytes(_json(plan))
    else:
        geometries, study_geometries = {}, {}
        for values, target in ((args.geometry, geometries), (args.study_geometry, study_geometries)):
            for value in values:
                name, sep, path = value.partition("=")
                if not sep or not name or not path or name in target:
                    raise ValueError("geometry must be unique CONFIG=PATH pairs")
                target[name] = Path(path)
        plan = render(args.out, geometries, args.stage, cells, args.owner, study_geometries=study_geometries, freeze=args.freeze)
    print(json.dumps({"out": str(args.out), "runs": len(plan["runs"]), "kernels": len(plan["kernels"]), "ready": plan["ready_for_execution"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
