#!/usr/bin/env python3
"""Measurement driver used by locally rendered WP5 CPU kernels.

Production is restricted to Kaggle; local use is mesh-only/200-iteration smoke.
No analysis verdict, geometry reconstruction or TR-00 qualification happens here.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_rans as C
import t2d_multibody_case as M

ROOT = Path(__file__).resolve().parents[2]


inherited_runner = C.inherited_runner


def _atomic(path: Path, value) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(C._finite_json(value), sort_keys=True, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def _runtime(source: Path, output: Path, stage: str, helper) -> dict:
    if stage == "smoke":
        import gmsh
        import scipy
        if gmsh.__version__ != helper.GMSH_PIN.split("==")[1]:
            raise ValueError("local gmsh does not match the inherited pin")
        release = dict(l.split("=", 1) for l in Path("/etc/os-release").read_text().splitlines() if "=" in l)
        suite = release.get("VERSION_CODENAME", "").strip('"')
        if suite not in helper.LOCKS:
            raise ValueError(f"unregistered OpenFOAM suite: {suite}")
        lock = json.loads((source / helper.LOCKS[suite]).read_text())
        installed = subprocess.check_output(["dpkg-query", "-W", "-f=${Package}=${Version}\n", *lock["packages"]], text=True).splitlines()
        if sorted(installed) != sorted(f"{n}={lock['version']}" for n in lock["packages"]):
            raise ValueError("local OpenFOAM package versions differ from lock")
        probe = subprocess.run(["bash", "-lc", f'source {helper.BASHRC} && source "$WM_PROJECT_DIR/etc/config.sh/aliases" && foamVersion'], capture_output=True, text=True, check=True)
        lines = [l.strip() for l in (probe.stdout + "\n" + probe.stderr).splitlines() if l.strip() == helper.FOAM_VERSION]
        if len(lines) != 1:
            raise ValueError("existing runtime is not OpenFOAM-v2512")
        return {"mode": "existing locked local runtime; no install", "foamVersion": lines[0], "installed_packages": installed,
                "gmsh": gmsh.__version__, "numpy": np.__version__, "scipy": scipy.__version__}
    gmsh = helper.install_gmsh()
    locks = {name: json.loads((source / rel).read_text()) for name, rel in helper.LOCKS.items()}
    installed = helper.install_openfoam(output / "work", locks)
    import scipy
    return {**installed, "gmsh": gmsh, "numpy": np.__version__, "scipy": scipy.__version__}


def _spec_id(spec: dict) -> str:
    return C.run_id(spec) + ({"production": "", "mesh-only": "__mesh", "smoke": "__smoke"}[spec["mode"]])


def _files(case: Path, object_name: str, filename: str) -> list[Path]:
    return sorted(case.glob(f"postProcessing/{object_name}/*/{filename}"), key=lambda p: float(p.parent.name))


def _archive_files(case: Path, keep: Path, object_name: str, filename: str) -> list[dict]:
    entries = []
    for p in _files(case, object_name, filename):
        rel = Path("postProcessing") / object_name / p.parent.name / filename
        target = keep / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        entries.append({"path": rel.as_posix(), "sha256": C.sha256(target)})
    return entries


def _record_stage(rec: dict, result: dict, deadline: float, deadline_limited: bool) -> None:
    """Only a completed meshing result can reject a mesh (Amendment 3 §3)."""
    rec["stages"].append(result)
    if not (result["returncode"] or result["timed_out"]):
        return
    stage = result["stage"]
    rec["failure_stage"] = stage
    if result["timed_out"] and (deadline_limited or time.monotonic() >= deadline):
        rec["status"], rec["error"] = "RUNNER_EXCEPTION", f"session deadline interrupted {stage}"
    elif result["timed_out"] and not stage.startswith("simpleFoam"):
        rec["status"], rec["error"] = "RUNNER_EXCEPTION", f"{stage} exceeded its infrastructure time budget without a completed mesh result"
    elif stage.startswith("simpleFoam"):
        rec["status"] = f"{stage}_{'TIMEOUT' if result['timed_out'] else 'FAILED'}"
    else:
        rec["status"] = "MESH_FAILED"


def run_case(spec: dict, source: Path, output: Path, deadline: float, helper=None) -> dict:
    """One isolated generation/mesh/solve path; bounded by session deadline."""
    helper = helper or inherited_runner(source)
    if spec["mode"] != "production" and (spec["iters"] > 200 or spec.get("cont_iters") is not None):
        raise ValueError("local smoke may not exceed 200 iterations or continue")
    cid = _spec_id(spec)
    case, keep = output / "work" / cid, output / "cases" / cid
    keep.mkdir(parents=True)
    rec = {"schema_version": "topo2d00-case-v1", "id": C.run_id(spec), **C.key_of(spec), "mode": spec["mode"],
           "iterations_requested": spec["iters"], "status": "COMPLETED", "stages": [], "geometry_sha256": spec["geometry_sha256"],
           "normalization": C.NORMALIZATION, "force_convention": C.FORCE_CONVENTION, "elements": spec["elements"]}
    started = time.monotonic()
    cmd = [sys.executable, str(source / "scripts/topo2d00/t2d_foam_case.py"), "--geometry", str(source / spec["geometry_file"]),
           "--out", str(case), "--model", spec["model"], "--family", spec["family"], "--realisation", str(spec["realisation"]), "--iters", str(spec["iters"])]
    phase = "integrity"
    try:
        # Retain the declared height even if input integrity prevents reading
        # the scene. Such records remain infrastructure losses, never usable.
        if spec.get("height_m") is not None:
            rec["height_m"] = C._number(spec["height_m"], "declared height")
            if rec["height_m"] <= 0:
                raise ValueError("declared height must be positive")
            rec["h_over_c1"] = rec["height_m"] / C.T.CHORD
            rec["h_over_c"] = rec["height_m"] / C.COMBINED_CHORD_M
        if spec["mode"] == "production" and spec.get("height_m") is None:
            raise ValueError("production requires an explicit declared height_m")
        if deadline - started < 900:
            rec["status"] = "NOT_RUN_TIME_BUDGET"
            return rec
        geometry_path = source / spec["geometry_file"]
        if C.sha256(geometry_path) != C._digest(spec["geometry_sha256"], "geometry"):
            raise ValueError("geometry source SHA differs from bundled input")
        geometry = M.load_geometry(geometry_path, spec["family"], expected_height_m=spec.get("height_m"))
        if geometry["config"] != spec["config"]:
            raise ValueError("geometry configuration differs from run plan")
        rec["height_m"] = geometry["height_m"]
        rec["h_over_c1"] = rec["height_m"] / C.T.CHORD
        rec["h_over_c"] = rec["height_m"] / C.COMBINED_CHORD_M
        if spec.get("height_m") is not None:
            cmd += ["--expected-height-m", str(spec["height_m"])]
        expected_layers = spec.get("n_layers")
        boundary_plan = None
        if spec.get("boundary_layer_plan_file"):
            plan_path = source / spec["boundary_layer_plan_file"]
            if C.sha256(plan_path) != C._digest(spec.get("boundary_layer_plan_sha256"), "boundary-layer plan"):
                raise ValueError("boundary-layer plan SHA differs from bundled input")
            boundary_plan = json.loads(plan_path.read_text())
            fixed = M.boundary_layer_settings(boundary_plan, geometry, spec["family"])
            if expected_layers is not None and expected_layers != fixed["n_layers"]:
                raise ValueError("run-plan n_layers differs from boundary-layer plan")
            expected_layers = fixed["n_layers"]
            cmd += ["--boundary-layer-plan", str(plan_path)]
        phase = "generator"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("session deadline before generator")
        generated = subprocess.run(cmd, capture_output=True, text=True, timeout=min(900, remaining),
                                   env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})
        (keep / "log.generator").write_text(generated.stdout + generated.stderr)
        rec["generator_wall_s"] = time.monotonic() - started
        if generated.returncode:
            rec["status"], rec["failure_stage"] = "MESH_FAILED", "generator"
        if rec["status"] == "COMPLETED":
            phase = "manifest integrity"
            manifest = json.loads((case / "case_manifest.json").read_text())
            if manifest.get("geometry_sha256") != spec["geometry_sha256"]:
                raise ValueError("generated geometry SHA differs from bundled input")
            rec["mesh_msh_sha256"] = C.sha256(case / "mesh.msh")
            if manifest.get("mesh_msh_sha256") != rec["mesh_msh_sha256"]:
                raise ValueError("generated mesh SHA differs from manifest")
            rec["mesh_proxy_failures"] = manifest["mesh_quality_failures"]
            # T2-0 mesh_quality proxies (including UNVERIFIED boundary skew)
            # are informational. checkMesh below decides mesh acceptance.
            rec["n_layers"] = manifest["n_layers"]
            if type(rec["n_layers"]) is not int or rec["n_layers"] < 1:
                raise ValueError("manifest n_layers must be a positive integer")
            if expected_layers is not None and rec["n_layers"] != expected_layers:
                raise ValueError("manifest n_layers differs from boundary-layer/run plan")
            if boundary_plan is not None and manifest.get("boundary_layer_plan_sha256") != M.plan_sha256(boundary_plan):
                raise ValueError("manifest boundary-layer plan SHA differs from bundled plan")
            rec["convergence_policy"] = manifest["convergence"]
            if rec["convergence_policy"] != C.CONVERGENCE:
                raise ValueError("manifest convergence policy differs from T2-0c collector policy")
            for key in ("height_m", "h_over_c1", "h_over_c"):
                value = C._number(manifest.get(key), f"manifest {key}")
                if not math.isclose(value, rec[key], rel_tol=0, abs_tol=1e-9):
                    raise ValueError(f"manifest {key} differs from source scene height")
                rec[key] = value
        solve = spec["mode"] != "mesh-only"
        for stage, command in (("gmshToFoam", "gmshToFoam mesh.msh"), ("checkMesh", "checkMesh -allGeometry -allTopology"), ("simpleFoam", "simpleFoam")):
            if rec["status"] != "COMPLETED" or stage == "simpleFoam" and not solve:
                break
            phase = stage
            if stage == "checkMesh":
                sys.path.insert(0, str(source / "scripts/topo2d00"))
                from t2d_foam_case import fix_boundary
                p = case / "constant/polyMesh/boundary"
                p.write_text(fix_boundary(p.read_text(), [e["patch"] for e in spec["elements"]]))
            cap = spec["case_cap_s"] if stage == "simpleFoam" else 900
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"session deadline before {stage}")
            timeout = min(cap, remaining)
            result = helper.timed_run(stage, command, case, timeout)
            _record_stage(rec, result, deadline, remaining <= cap)
            if stage == "checkMesh" and not result["timed_out"]:
                cm = helper.parse_check_mesh((case / "log.checkMesh").read_text(errors="replace"))
                rec["check_mesh"] = cm
                rec["mesh_only_stage"] = {"mesh_msh_sha256": rec["mesh_msh_sha256"], "check_mesh": cm,
                                          "returncode": result["returncode"], "passed": bool(cm["mesh_ok"] and not cm["failed_check_counts"] and not result["returncode"])}
                if not cm["mesh_ok"] or cm["failed_check_counts"]:
                    rec["status"] = "MESH_FAILED"
        if solve and rec["status"] == "COMPLETED" and spec.get("cont_iters"):
            # Exactly the inherited T2-0c/T2-0b continuation trigger: Cl block plateau,
            # not residual convergence and not raw-tail convergence.
            paths = _files(case, "forceCoeffs", "coefficient.dat")
            try:
                history = C.read_history(case, [{"path": p.relative_to(case).as_posix(), "sha256": C.sha256(p)} for p in paths])
                if not np.isfinite(history[:, 1:]).all() or np.abs(history[:, 1:]).max() > C.BLOWUP_ABS:
                    rec["status"], rec["force_values_finite"] = "SOLVER_DIVERGED", bool(np.isfinite(history).all())
                    plateau = True  # Divergence is a result; never continue it.
                else:
                    plateau = C.cl_summary(history)["cl_plateau"]
            except C.HistoryUnavailable as exc:
                rec["status"], rec["error"] = "PARSE_FAILED", f"{type(exc).__name__}: {exc}"
                plateau = True
            if not plateau and rec["status"] == "COMPLETED":
                phase = "simpleFoam_cont"
                helper._continue(case, spec["cont_iters"])
                already = sum(s["wall_s"] for s in rec["stages"] if s["stage"].startswith("simpleFoam"))
                cap, remaining = max(1, spec["case_cap_s"] - already), deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("session deadline before simpleFoam_cont")
                timeout = min(cap, remaining)
                result = helper.timed_run("simpleFoam_cont", "simpleFoam", case, timeout)
                _record_stage(rec, result, deadline, remaining <= cap)
                rec["continued_to"] = spec["cont_iters"]
        logs = [p for p in (case / "log.simpleFoam", case / "log.simpleFoam_cont") if p.is_file()]
        if logs:
            rec["solver"] = helper.parse_solver(logs[-1].read_text(errors="replace"))
            if rec["status"] == "COMPLETED" and any(rec["solver"].get(k) for k in ("nan_in_log", "sigfpe", "foam_fatal")):
                rec["status"] = "SOLVER_DIVERGED"
        objects = {"total": ("forceCoeffs", "forces"), **{e["patch"]: (f"forceCoeffs_{e['patch']}", f"forces_{e['patch']}") for e in spec["elements"]}}
        rec["coefficient_files"] = {k: _archive_files(case, keep, names[0], "coefficient.dat") for k, names in objects.items()}
        rec["force_files"] = {k: _archive_files(case, keep, names[1], "force.dat") for k, names in objects.items()}
        if solve and rec["status"] not in C.MECHANICAL_STATUSES | C.INFRA_STATUSES and C.divergent_coefficients(keep, rec["coefficient_files"]):
            rec["status"] = "SOLVER_DIVERGED"
        if rec["status"] == "COMPLETED" and solve:
            histories = {name: C.read_history(keep, parts) for name, parts in rec["coefficient_files"].items()}
            dimensional = {name: C.read_force_parts(keep, parts) for name, parts in rec["force_files"].items()}
            all_histories = [*histories.values(), *(h for parts in dimensional.values() for h in parts.values())]
            rec["force_values_finite"] = all(np.isfinite(h).all() for h in all_histories)
            if not rec["force_values_finite"] or any(np.abs(h[:, 1:]).max() > C.BLOWUP_ABS for h in all_histories):
                rec["status"] = "SOLVER_DIVERGED"
            if spec["mode"] == "smoke" and histories["total"][-1, 0] != spec["iters"]:
                rec["status"] = "PARSE_FAILED"
                rec["error"] = "smoke did not reach the requested 200 iterations"
        if not solve and rec["status"] == "COMPLETED":
            rec["status"] = "MESH_OK"
    except subprocess.TimeoutExpired:
        rec["status"], rec["failure_stage"] = "RUNNER_EXCEPTION", phase
        rec["error"] = f"session deadline interrupted {phase}" if time.monotonic() >= deadline else f"{phase} exceeded its infrastructure time budget"
    except Exception as exc:
        rec["status"] = "RUNNER_EXCEPTION"
        rec["failure_stage"] = phase
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if case.exists():
            for p in [*case.glob("log.*"), case / "case_manifest.json", case / "mesh.msh"]:
                if p.is_file():
                    shutil.copy2(p, keep / p.name)
            if (keep / "mesh.msh").exists():
                rec["mesh_file"] = "mesh.msh"
                rec["mesh_msh_sha256"] = C.sha256(keep / "mesh.msh")
                if rec.get("mesh_only_stage", {}).get("mesh_msh_sha256", rec["mesh_msh_sha256"]) != rec["mesh_msh_sha256"]:
                    rec["status"] = "RUNNER_EXCEPTION"
                    rec["error"] = "mesh changed between the mesh-only gate and solve"
            # Dictionaries keep exact numerical setup; solved fields are not required
            # for the WP4 analyzer and are intentionally excluded from kernel output.
            for name in ("0", "system", "constant", "continuation"):
                if (case / name).is_dir():
                    shutil.copytree(case / name, keep / "case_dict" / name, ignore=shutil.ignore_patterns("polyMesh"))
            shutil.rmtree(case)
        rec["total_wall_s"] = time.monotonic() - started
        _atomic(keep / "case_result.json", rec)
    return rec


def execute(plan: dict, source: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite: {output}")
    if not plan["ready_for_execution"]:
        raise ValueError(plan.get("blocked_reason") or "execution requires a ready frozen render")
    if plan["stage"] != "smoke" and os.environ.get("KAGGLE_KERNEL_RUN_TYPE") not in ("Batch", "Interactive"):
        raise ValueError("production RANS may only run on Kaggle; local scope is <=200-iteration smoke")
    output.mkdir(parents=True)
    (output / "work").mkdir()
    started = time.monotonic()
    helper = inherited_runner(source)
    environment = {"python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count(),
                   "stage": plan["stage"], "kernel": plan["kernel_name"], "pins": plan["input_sha256"],
                   "source_commit": plan["source_commit"], "source_dirty": plan["source_dirty"],
                   "source_archive_sha256": plan["bundle_sha256"]}
    _atomic(output / "environment.json", environment)
    install = _runtime(source, output, plan["stage"], helper)
    _atomic(output / "install.json", install)
    results, lock = [], threading.Lock()
    deadline = started + plan["session_budget_s"] - plan["reserve_s"]

    def work(spec):
        r = run_case(spec, source, output, deadline, helper)
        with lock:
            results.append(r)
            _atomic(output / "result.json", {"stage": plan["stage"], "cases": results, "evidence_class": "LOCAL_SMOKE" if plan["stage"] == "smoke" else "RANS_MEASUREMENT_UNQUALIFIED"})
        return r

    if plan["stage"] == "smoke":
        # Each mesh gate precedes its solve, on the same single realization.
        for spec in plan["runs"]:
            result = work(spec)
            if result["status"] not in ("MESH_OK", "COMPLETED"):
                break
    else:
        with ThreadPoolExecutor(plan["workers"]) as pool:
            list(pool.map(work, plan["runs"]))
    summary = {"expected": len(plan["runs"]), "recorded": len(results), "elapsed_s": time.monotonic() - started,
               "status_counts": {s: sum(r["status"] == s for r in results) for s in sorted({r["status"] for r in results})}}
    _atomic(output / "summary.json", summary)
    manifest = {p.relative_to(output).as_posix(): C.sha256(p) for p in sorted(output.rglob("*")) if p.is_file()}
    _atomic(output / "artifact_manifest.json", manifest)
    _atomic(output / "DONE", {**summary, "artifact_manifest_sha256": C.sha256(output / "artifact_manifest.json")})
    if plan["stage"] == "smoke" and (len(results) != len(plan["runs"]) or any(r["status"] != "COMPLETED" for r in results)):
        raise RuntimeError("local smoke failed; inspect summary and preserved case records")
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    return execute(json.loads(args.plan.read_text()), ROOT, args.out)


if __name__ == "__main__":
    main()
