#!/usr/bin/env python3
"""T2-0a kernel (#57, EXPLORATORY_COMMITTED): 2D RANS Tyrrell 026 ground-effect cases on Kaggle CPU, OpenFOAM v2512.

Template: scripts/build_t20a_kernel.py replaces PIN_SOURCE_COMMIT and PIN_PINS and verifies the pins against the commit.
Order (cheap failures first): environment -> pinned source -> gmsh install + one meshing probe -> OpenFOAM install (hash-locked, copied from the
XFID X3 runner) -> smoke stage (3 coarse cases, 200 iterations; only SA-WF and SST-WF gate the kernel) -> registered case list, independent cases concurrently.
MODE (rendered by the builder) "mesh_only": generate every registered (mesh spec, ride height) mesh, gmshToFoam + boundary fix + checkMesh, write meshcheck.json/.md, no solver.
kOmegaSSTLM runs as a continuation: kOmegaSST on the same mesh, then the model is switched (low relaxation, gammaInt/ReThetat added); a failure of either LM stage is the
case result LM_DIVERGED with diagnostics and never stops the kernel.
Measurement only: no PASS/FAIL on physics, no flag. Kernel-level failures write ERROR.json and raise; DONE is written last.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

try:
    import psutil
except ImportError:
    psutil = None

SOURCE_COMMIT = "PIN_SOURCE_COMMIT"
MODE = "PIN_MODE"                          # "full" | "mesh_only", rendered by scripts/build_t20a_kernel.py
PINS = PIN_PINS  # {repo path: sha256}, rendered
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
LOCKS = {"jammy": "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json", "noble": "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json"}  # the two hash-pinned OpenCFD v2512 locks registered by XFID X2/X3; chosen by the observed Ubuntu codename
GMSH_PIN = "gmsh==4.15.2"
FOAM_VERSION = "OpenFOAM-v2512"
OUTPUT = Path(os.environ.get("T20A_OUTPUT", "/kaggle/working/t20a"))
BASHRC = os.environ.get("T20A_BASHRC", "/usr/lib/openfoam/openfoam2512/etc/bashrc")
BUDGET_S, WORKERS, RESERVE_S = 10.5 * 3600, 4, 600     # kernel budget (Kaggle limit 12 h), concurrent independent cases (4 vCPU)
CASE_CAP_S = {"wf": 2.5 * 3600, "wr": 5 * 3600}        # per-case solver timeout, by wall treatment
HEIGHTS = (0.671, 0.448, 0.224, 0.134, 0.09)
SMOKE = [("sa-wf", 0.448, "coa30"), ("sst-wf", 0.448, "coa30"), ("sst-lm", 0.448, "wrc")]  # 200 iterations each
CASES = [("sst-lm", h, "wr2") for h in (0.09, 0.134, 0.224)] + [(m, h, "med30") for h in reversed(HEIGHTS) for m in ("sa-wf", "sst-wf")]
SMOKE_ITERS = 200
TAIL_FRACTION, PLATEAU_REL = 0.2, 0.005                # descriptive force-plateau flag: last 20 % of iterations, relative std and drift < 0.5 %
NUM = r"[-+0-9.eE]+"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


# ---- process control (from the XFID X3 runner) -----------------------------------

def timed_run(name: str, command: str, cwd: Path, timeout_s: float, env_extra=None) -> dict:
    """One OpenFOAM stage in a bash login shell with the v2512 bashrc sourced; log.<name>; peak process-tree RSS sampled."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak, start = [0], time.monotonic()
    with open(cwd / f"log.{name}", "wb") as log:
        proc = subprocess.Popen(["bash", "-lc", f"source {BASHRC} && {command}"], cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, env={**os.environ, **(env_extra or {})})
        stop = threading.Event()

        def sample():
            while psutil is not None and not stop.is_set():
                try:
                    root = psutil.Process(proc.pid)
                    peak[0] = max(peak[0], sum(p.memory_info().rss for p in [root, *root.children(recursive=True)]))
                except psutil.Error:
                    pass
                stop.wait(1.0)

        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        timed_out = False
        try:
            rc = proc.wait(timeout=max(timeout_s, 1))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            rc, timed_out = proc.wait(), True
        stop.set()
        thread.join()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"stage": name, "returncode": rc, "timed_out": timed_out, "wall_s": time.monotonic() - start,
            "peak_rss_mb_sampled": (peak[0] / 1e6) if psutil is not None else None}


# ---- parsers -------------------------------------------------------------------

def parse_check_mesh(text: str) -> dict:
    cells = re.search(r"^[ \t]*cells:\s*(\d+)\s*$", text, re.M)
    first = lambda pattern: next(iter(re.findall(pattern, text)), None)
    return {"cells": int(cells.group(1)) if cells else None, "mesh_ok": "Mesh OK." in text,
            "failed_check_counts": [int(v) for v in re.findall(r"^[ \t]*Failed (\d+) mesh checks?\.", text, re.M)],
            "diagnostic_lines": [d.strip() for d in re.findall(r"^[ \t]*\*\*\*.*$", text, re.M)],
            "unused_points": int(first(r"number unused by cells: (\d+)") or 0),
            "max_non_orthogonality": first(r"Mesh non-orthogonality Max: (" + NUM + ")"),
            "severe_non_orthogonal_faces": int(first(r"Number of severely non-orthogonal \(> 70 degrees\) faces: (\d+)") or 0),
            "max_skewness": first(r"Max skewness = (" + NUM + ")"),
            "max_aspect_ratio": first(r"Max aspect ratio = (" + NUM + ")"),
            "min_determinant": first(r"Cell determinant \(wellposedness\) : minimum: (" + NUM + ")"),
            "min_face_weight": first(r"Face interpolation weight : minimum: (" + NUM + ")"),
            "min_volume_ratio": first(r"Face volume ratio : minimum: (" + NUM + ")")}


def parse_solver(text: str) -> dict:
    res = {}
    for f in ("Ux", "Uy", "p", "k", "omega", "nuTilda", "ReThetat", "gammaInt"):
        m = re.findall(rf"Solving for {f}, Initial residual = ({NUM}), Final residual = {NUM}", text)
        res[f] = float(m[-1]) if m else None
    conv = re.search(r"SIMPLE solution converged in (\d+) iterations", text)
    times = re.findall(r"^Time = (" + NUM + ")", text, re.M)
    return {"iterations": len(times), "last_time": float(times[-1]) if times else None, "converged_in": int(conv.group(1)) if conv else None,
            "last_initial_residuals": res, "nan_in_log": bool(re.search(r"\bnan\b", text, re.I)),
            "sigfpe": "sigFpe::sigHandler" in text,   # the startup line "trapFpe: Floating point exception trapping enabled" is NOT a crash (attempt 2 mis-read it)
            "foam_fatal": "FOAM FATAL" in text}


def force_summary(dat: Path) -> dict:
    header, rows = None, []
    for line in dat.read_text().splitlines():
        if line.startswith("#"):
            header = line.lstrip("#").split()
        elif line.strip():
            rows.append(dict(zip(header, (float(x) for x in line.split()))))
    require(len(rows) > 1 and all(math.isfinite(v) for r in rows for v in r.values()), "force coefficient history empty or non-finite")
    n = max(50, math.ceil(len(rows) * TAIL_FRACTION))
    out = {"rows": len(rows), "last_iteration": rows[-1]["Time"], "tail_rows": min(n, len(rows)), "columns": header}
    for key in ("Cl", "Cd"):
        v = np.array([r[key] for r in rows[-n:]])
        x = np.arange(len(v)) - (len(v) - 1) / 2
        drift = float((x * (v - v.mean())).sum() / (x * x).sum() * (len(v) - 1))
        out[key] = {"last": float(rows[-1][key]), "tail_mean": float(v.mean()), "tail_std": float(v.std()), "tail_min": float(v.min()),
                    "tail_max": float(v.max()), "tail_rel_std": float(v.std() / abs(v.mean())), "tail_rel_drift": abs(drift) / abs(float(v.mean()))}
    out["force_plateau"] = all(out[k]["tail_rel_std"] < PLATEAU_REL and out[k]["tail_rel_drift"] < PLATEAU_REL for k in ("Cl", "Cd"))
    return out


# ---- environment and installs ------------------------------------------------------

def install_openfoam(work: Path, locks: dict) -> dict:
    """Copied from infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py (hash-locked packages, explicit alias sourcing for the PS1 pitfall)."""
    release = dict(l.split("=", 1) for l in Path("/etc/os-release").read_text().splitlines() if "=" in l)
    codename = release.get("VERSION_CODENAME", "").strip('"')
    arch = subprocess.run(["dpkg", "--print-architecture"], check=True, text=True, capture_output=True).stdout.strip()
    require(release.get("ID", "").strip('"') == "ubuntu", f"unsupported OS ID: {release.get('ID')}")
    require(codename in locks, f"no registered OpenCFD v2512 lock for Ubuntu {codename!r}; registered: {sorted(locks)}")
    lock = locks[codename]
    require(codename == lock["suite"], "lock suite differs from the observed Ubuntu codename")
    require(arch == lock["architecture"], f"unsupported architecture: {arch}")
    installer = work / "add-debian-repo.sh"
    with installer.open("wb") as stream:
        run(["curl", "-fsSL", "https://dl.openfoam.com/add-debian-repo.sh"], stdout=stream)
    require(sha(installer) == lock["official_installer_sha256"], "official repository installer SHA mismatch")
    run(["bash", str(installer)])
    for name, record in lock["indexes"].items():
        target = work / name
        with urllib.request.urlopen(record["url"], timeout=60) as response, target.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        require(sha(target) == record["sha256"], f"official apt index SHA mismatch for {name}")
    run(["apt-get", "update"])
    names = list(lock["packages"])
    run(["apt-get", "download", *[f"{n}={lock['version']}" for n in names]], cwd=work)
    debs = []
    for n in names:
        deb = work / f"{n}_{lock['version']}_{lock['package_architectures'][n]}.deb"
        require(deb.is_file() and sha(deb) == lock["packages"][n], f"{n} package missing or SHA mismatch")
        debs.append(str(deb))
    run(["apt-get", "install", "-y", *debs])
    for d in debs:
        Path(d).unlink()
    installed = subprocess.run(["dpkg-query", "-W", "-f=${Package}=${Version}\n", *names], check=True, text=True, capture_output=True).stdout.splitlines()
    require(sorted(installed) == sorted(f"{n}={lock['version']}" for n in names), "installed OpenFOAM package set differs from lock")
    # foamVersion is an alias function defined only by etc/config.sh/aliases, which setup sources only when PS1 is set: source it explicitly.
    probe = subprocess.run(["bash", "-lc", f'source {BASHRC} && source "$WM_PROJECT_DIR/etc/config.sh/aliases" && foamVersion'], text=True, capture_output=True)
    lines = [l.strip() for s in (probe.stdout, probe.stderr) for l in s.splitlines() if re.fullmatch(r"OpenFOAM-[A-Za-z0-9._+-]+", l.strip())]
    require(lines == [FOAM_VERSION], f"expected one {FOAM_VERSION!r} foamVersion line; found {lines}; rc={probe.returncode} stdout={probe.stdout[-300:]!r} stderr={probe.stderr[-300:]!r}")
    return {"installed_packages": installed, "foamVersion": lines[0], "architecture": arch, "lock_suite": codename}


def fetch_source(base: Path) -> Path:
    source = base / "source"
    source.mkdir()
    git = ["git", "-C", str(source)]
    run(git + ["init", "-q"])
    run(git + ["remote", "add", "origin", REPO_URL])
    run(git + ["config", "core.sparseCheckout", "true"])
    (source / ".git/info/sparse-checkout").write_text("\n".join("/" + p for p in PINS) + "\n")
    if subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", SOURCE_COMMIT]).returncode:
        run(git + ["fetch", "-q", "--depth", "1", "origin", SOURCE_COMMIT])
    run(git + ["checkout", "-q", "--detach", "FETCH_HEAD"])
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    require(head == SOURCE_COMMIT, f"checked-out commit {head} != pinned {SOURCE_COMMIT}")
    for rel, digest in PINS.items():
        require(sha(source / rel) == digest, f"pinned file differs: {rel}")
    return source


def install_gmsh() -> str:
    run([sys.executable, "-m", "pip", "install", "-q", GMSH_PIN])
    probe = [sys.executable, "-c", "import gmsh; print(gmsh.__version__)"]
    got = subprocess.run(probe, capture_output=True, text=True)
    if got.returncode:  # the PyPI wheel links GL libraries that slim images may lack
        run(["apt-get", "install", "-y", "-q", "libglu1-mesa", "libgl1", "libxft2", "libxinerama1", "libxcursor1", "libxrender1", "libxfixes3"])
        got = subprocess.run(probe, capture_output=True, text=True)
    require(got.returncode == 0 and got.stdout.strip() == GMSH_PIN.split("==")[1], f"gmsh import failed: {got.stdout[-200:]} {got.stderr[-400:]}")
    return got.stdout.strip()


# ---- one case ----------------------------------------------------------------------

def _latest_time(case: Path) -> Path:
    return max((d for d in case.iterdir() if d.is_dir() and re.fullmatch(r"[0-9.]+", d.name) and d.name != "0"), key=lambda d: float(d.name))


def _switch_to_lm(case: Path, with_options: bool) -> Path:
    """Stage 2 setup: gammaInt/ReThetat (initialised from the inlet values in 0/) join the latest kOmegaSST time, and the LM dictionaries replace the stage-1 ones."""
    latest = _latest_time(case)
    for f in ("gammaInt", "ReThetat"):
        shutil.copy(case / "0" / f, latest / f)
    for src in (case / "stage2").rglob("*"):
        if src.is_file() and (with_options or src.name != "fvOptions"):
            shutil.copy(src, case / src.relative_to(case / "stage2"))
    if not with_options:
        (case / "system/fvOptions").unlink(missing_ok=True)
    return latest


def run_lm_stage(case: Path, timeout: float) -> dict:
    """kOmegaSSTLM continuation from the latest kOmegaSST time. The optional velocity limiter in system/fvOptions (t20_foam.fv_options, UNCERTAIN syntax) is tried
    first; if the stage dies before its first iteration with a FOAM FATAL it is removed once and the stage reruns (recorded as limiter_dropped)."""
    _switch_to_lm(case, True)
    stage = timed_run("simpleFoam_lm", "simpleFoam", case, timeout)
    stage["limiter"] = "velocityDampingConstraint"
    log = (case / "log.simpleFoam_lm").read_text(errors="replace")
    if stage["returncode"] and "FOAM FATAL" in log and not re.search(r"^Time = ", log, re.M):
        (case / "log.simpleFoam_lm_with_limiter").write_text(log)
        (case / "system/fvOptions").unlink(missing_ok=True)
        stage = timed_run("simpleFoam_lm", "simpleFoam", case, timeout)
        stage["limiter"] = "dropped (the limiter dictionary was rejected at startup)"
    return stage


def blown_up(forces) -> bool:
    return bool(forces) and any(abs(forces[k][m]) > 100 for k in ("Cl", "Cd") for m in ("last", "tail_min", "tail_max"))   # a wing at these Re has |Cl|, |Cd| of order 1


def run_case(spec: dict, source: Path, deadline: float) -> dict:
    cid = spec["id"]
    solve = spec.get("solve", True)
    lm = spec["model"] == "sst-lm"
    case = OUTPUT / "work" / cid
    keep = OUTPUT / "cases" / cid
    keep.mkdir(parents=True)
    rec = {"id": cid, "model": spec["model"], "h_over_c": spec["h"], "mesh": spec["mesh"], "iterations_requested": spec["iters"], "stages": [], "status": "COMPLETED"}
    t0 = time.monotonic()
    env = {"PYTHONPATH": f"{source}/scripts"}
    cmd = [sys.executable, str(source / "scripts/t20_case.py"), "--h-over-c", str(spec["h"]), "--model", spec["model"], "--mesh", spec["mesh"],
           "--iters", str(spec["iters"]), "--out", str(case)]
    gen = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **env})
    (keep / "log.t20_case").write_text(gen.stdout + gen.stderr)
    if gen.returncode:
        rec["status"] = "GENERATOR_FAILED"
    cap = CASE_CAP_S[spec["wall"]]
    for name, command in (("gmshToFoam", "gmshToFoam mesh.msh"), ("checkMesh", "checkMesh -allGeometry -allTopology"), ("simpleFoam", "simpleFoam")):
        if rec["status"] != "COMPLETED" or (name == "simpleFoam" and not solve):
            break
        timeout = min(cap * (0.3 if lm else 1), deadline - time.monotonic()) if name == "simpleFoam" else 900
        if name == "checkMesh":  # gmshToFoam writes every patch as `patch`: front/back must be empty and airfoil/ground wall
            sys.path.insert(0, str(source / "scripts"))
            import t20_foam
            b = case / "constant/polyMesh/boundary"
            b.write_text(t20_foam.fix_boundary(b.read_text()))
        stage = timed_run(name, command, case, timeout)
        rec["stages"].append(stage)
        if name == "checkMesh":
            rec["check_mesh_returncode"] = stage["returncode"]   # a failed check is recorded, not fatal (exploratory)
        elif stage["returncode"] or stage["timed_out"]:
            rec["status"] = f"{name}_{'TIMEOUT' if stage['timed_out'] else 'FAILED'}"
    text = lambda n: (case / f"log.{n}").read_text(errors="replace") if (case / f"log.{n}").is_file() else ""
    if lm and solve and rec["status"] == "simpleFoam_FAILED":
        rec["status"], rec["lm_failed_stage"] = "LM_DIVERGED", "stage1_kOmegaSST"
    if lm and solve and rec["status"] == "COMPLETED":
        stage = run_lm_stage(case, min(cap - rec["stages"][-1]["wall_s"], deadline - time.monotonic()))
        rec["stages"].append(stage)
        if stage["returncode"] or stage["timed_out"]:
            rec["status"], rec["lm_failed_stage"] = ("SOLVER_TIMEOUT_PARTIAL" if stage["timed_out"] else "LM_DIVERGED"), "stage2_kOmegaSSTLM"
    rec["total_wall_s"] = time.monotonic() - t0
    try:
        rec["check_mesh"] = parse_check_mesh(text("checkMesh"))
        rec["solver"] = parse_solver(text("simpleFoam"))
        if lm:
            rec["solver_lm"] = parse_solver(text("simpleFoam_lm"))
        dats = {d.parent.name: d for d in case.glob("postProcessing/forceCoeffs/*/coefficient.dat")}   # stage 2 of an LM case writes to <stage-1 end time>/
        if lm and "0" in dats:
            rec["forces_stage1_kOmegaSST"] = force_summary(dats.pop("0"))
        if dats:   # an LM case reports `forces` for the LM stage only: a diverged LM case does not inherit the SST numbers
            rec["forces"] = force_summary(dats[max(dats, key=float)])
        rec["residual_converged"] = (rec["solver_lm"] if lm and rec["solver_lm"]["iterations"] else rec["solver"])["converged_in"] is not None
        if rec["status"] in ("simpleFoam_TIMEOUT", "simpleFoam_lm_TIMEOUT") and "forces" in rec:
            rec["status"] = "SOLVER_TIMEOUT_PARTIAL"
        if lm and rec["status"] == "COMPLETED" and (blown_up(rec.get("forces")) or rec["solver_lm"]["nan_in_log"]):
            rec["status"], rec["lm_failed_stage"] = "LM_DIVERGED", "stage2_kOmegaSSTLM"
    except Exception as exc:
        rec["parse_error"] = f"{type(exc).__name__}: {exc}"
        rec["status"] = rec["status"] if rec["status"] != "COMPLETED" else "PARSE_FAILED"
    if rec["status"] == "LM_DIVERGED":
        log = text("simpleFoam_lm") if rec.get("lm_failed_stage") == "stage2_kOmegaSSTLM" else text("simpleFoam")
        rec["lm_diagnostics"] = {"log_tail": log.splitlines()[-40:], "check_mesh_failed_counts": rec.get("check_mesh", {}).get("failed_check_counts"),
                                 "solver": rec.get("solver_lm") if rec.get("lm_failed_stage") == "stage2_kOmegaSSTLM" else rec.get("solver")}
    if not solve and "check_mesh" in rec:
        rec["status"] = "MESH_OK" if rec["status"] == "COMPLETED" and rec["check_mesh"]["mesh_ok"] and not rec["check_mesh"]["failed_check_counts"] else (
            "MESH_FAILED" if rec["status"] == "COMPLETED" else rec["status"])
    if (case / "case_manifest.json").is_file():
        man = json.loads((case / "case_manifest.json").read_text())
        rec["mesh_cells_3d"], rec["mesh_proxy"], rec["mesh_proxy_failures"] = man["mesh_stats"]["cells_3d"], man["mesh_stats"]["quality"], man["mesh_quality_failures"]
    if case.exists():
        for p in [*case.glob("log.*"), *case.glob("postProcessing/*/*/*.dat"), case / "mesh.msh", case / "case_manifest.json"]:
            if p.is_file() and not (p.name == "mesh.msh" and not solve):   # mesh-only: the 25 meshes are regenerable from the manifest, keep logs and stats only
                prefix = "" if p.parent.name in ("0", case.name) else f"t{p.parent.name}_"
                with p.open("rb") as src, gzip.open(keep / (prefix + p.name + ".gz"), "wb") as dst:
                    shutil.copyfileobj(src, dst)
        for d in ("0", "system", "constant", "stage2"):
            if (case / d).is_dir():
                shutil.copytree(case / d, keep / "case_dict" / d, ignore=shutil.ignore_patterns("polyMesh"))
        shutil.rmtree(case, ignore_errors=True)
    write_json(keep / "case_result.json", rec)
    return rec


def make_specs(items, iters=None):
    sys.path.insert(0, str(SOURCE / "scripts"))
    import t20_case
    return [{"id": f"{m}_h{h}_{mesh}" + ("_smoke" if iters else ""), "model": m, "h": h, "mesh": mesh, "wall": t20_case.MODELS[m]["wall"],
             "iters": iters or t20_case.MODELS[m]["iters"]} for m, h, mesh in items]


def make_mesh_specs():
    """MESH_ONLY: every registered mesh spec at every registered ride height (the model only selects the wall treatment; no solver runs)."""
    sys.path.insert(0, str(SOURCE / "scripts"))
    import t20_case
    return [{"id": f"mesh_{mesh}_h{h}", "model": "sa-wf" if spec["wall"] == "wf" else "sst-lm", "h": h, "mesh": mesh, "wall": spec["wall"], "iters": 2, "solve": False}
            for mesh, spec in t20_case.MESHES.items() for h in HEIGHTS]


def mesh_table(cases) -> str:
    """Markdown table: OpenFOAM checkMesh next to the local proxy (scripts/t20_case.mesh_quality) per (mesh spec, height)."""
    f = lambda v, spec=".3g": "-" if v is None else format(float(v), spec)
    lines = ["| case | status | cells | checkMesh failed | unused pts | non-orth max (cm/proxy) | skew max (cm/proxy) | AR max (cm/proxy) | det min (cm/proxy) | weight min (cm/proxy) | vol ratio min (cm/proxy) | failure lines |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(cases, key=lambda c: c["id"]):
        m, q = c.get("check_mesh", {}), c.get("mesh_proxy", {})
        lines.append(f"| {c['id']} | {c['status']} | {m.get('cells', '-')} | {m.get('failed_check_counts', '-')} | {m.get('unused_points', '-')} | "
                     f"{f(m.get('max_non_orthogonality'))}/{f(q.get('nonorth_max'))} | {f(m.get('max_skewness'))}/{f(q.get('skew_max'))} | {f(m.get('max_aspect_ratio'))}/{f(q.get('aspect_ratio_max'))} | "
                     f"{f(m.get('min_determinant'))}/{f(q.get('det_min'))} | {f(m.get('min_face_weight'))}/{f(q.get('weight_min'))} | {f(m.get('min_volume_ratio'))}/{f(q.get('vol_ratio_min'))} | "
                     f"{'; '.join(m.get('diagnostic_lines', []))[:300] or '-'} |")
    return "\n".join(lines) + "\n"


def infrastructure_ok(r: dict) -> bool:
    s = r.get("solver", {})
    return r["status"] == "COMPLETED" and "forces" in r and s.get("iterations", 0) >= SMOKE_ITERS - 1 and not s.get("nan_in_log") and r["forces"]["last_iteration"] >= SMOKE_ITERS - 1


def smoke_failures(smoke) -> list:
    """The infrastructure gate: SA-WF and SST-WF must run clean. The LM smoke case is diagnostic only (LM_DIVERGED is a recorded result, never a kernel failure)."""
    return [r for r in smoke if "sst-lm" not in r["id"] and not infrastructure_ok(r)]


def main() -> None:
    global SOURCE
    require(SOURCE_COMMIT != "PIN_SOURCE_COMMIT" and MODE in ("full", "mesh_only"), "runner has not been rendered by scripts/build_t20a_kernel.py")
    require(not OUTPUT.exists(), f"refusing to overwrite prior output: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "work").mkdir()
    started = time.monotonic()
    meminfo = Path("/proc/meminfo").read_text().splitlines()[0] if Path("/proc/meminfo").exists() else None
    write_json(OUTPUT / "environment.json", {"python": sys.version, "cpu_count": os.cpu_count(), "meminfo_first_line": meminfo, "uname": list(os.uname()),
                                             "source_commit": SOURCE_COMMIT, "mode": MODE, "pins": PINS, "runner_sha256": sha(Path(__file__).resolve())})
    SOURCE = fetch_source(OUTPUT / "work")
    gmsh_version = install_gmsh()
    sys.path.insert(0, str(SOURCE / "scripts"))
    import t20_case
    probe = OUTPUT / "work" / "mesh_probe"
    probe_man = t20_case.write_case(probe, 0.09, "sa-wf", "coa30", iters=1)   # fail fast on meshing before the OpenFOAM install
    stats = probe_man["mesh_stats"]
    require(stats["gap_cells_at_lowest_point"] >= 15, f"mesh probe gap cells {stats['gap_cells_at_lowest_point']}")
    require(MODE == "mesh_only" or not probe_man["mesh_quality_failures"], f"mesh probe fails the local quality proxy: {probe_man['mesh_quality_failures']}")
    shutil.rmtree(probe)
    locks = {name: json.loads((SOURCE / rel).read_text()) for name, rel in LOCKS.items()}
    install = install_openfoam(OUTPUT / "work", locks)
    write_json(OUTPUT / "install.json", {**install, "gmsh_version": gmsh_version, "mesh_probe_cells": stats["cells_3d"]})
    deadline = started + BUDGET_S - RESERVE_S

    results, lock_ = [], threading.Lock()

    def summary():
        return {"runner_sha256": sha(Path(__file__).resolve()), "source_commit": SOURCE_COMMIT, "mode": MODE, "install": install, "gmsh_version": gmsh_version,
                "elapsed_s": time.monotonic() - started, "workers": WORKERS, "cases": results,
                "qualification_flags": "none (EXPLORATORY_COMMITTED; no flag, threshold or verdict)"}

    def execute(specs, record):
        def work(s):
            try:
                r = run_case(s, SOURCE, deadline) if deadline - time.monotonic() > 900 else {"id": s["id"], "status": "NOT_RUN_TIME_BUDGET"}
            except Exception as exc:
                r = {"id": s["id"], "status": "RUNNER_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}
            with lock_:
                record.append(r)
                write_json(OUTPUT / "result.json", summary())   # rewritten as each case ends: survives a kernel kill
            return r
        with ThreadPoolExecutor(WORKERS) as pool:
            return list(pool.map(work, specs))

    if MODE == "mesh_only":
        execute(make_mesh_specs(), results)
        write_json(OUTPUT / "meshcheck.json", sorted(results, key=lambda c: c["id"]))
        (OUTPUT / "meshcheck.md").write_text(mesh_table(results))
    else:
        smoke = execute(make_specs(SMOKE, SMOKE_ITERS), [])
        write_json(OUTPUT / "smoke.json", smoke)
        bad = smoke_failures(smoke)
        require(not bad, f"smoke stage failed (infrastructure): {[(r['id'], r['status']) for r in bad]}")
        execute(make_specs(CASES), results)
    shutil.rmtree(OUTPUT / "work", ignore_errors=True)
    manifest = {str(p.relative_to(OUTPUT)): sha(p) for p in sorted(OUTPUT.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    write_json(OUTPUT / "artifact_manifest.json", manifest)
    counts = {}
    for c in results:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    (OUTPUT / "DONE").write_text(json.dumps({"status": "FINISHED_MESH_CHECK" if MODE == "mesh_only" else "FINISHED_CASE_LIST", "status_counts": counts, "artifact_manifest_sha256": sha(OUTPUT / "artifact_manifest.json")}, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        err = OUTPUT / "ERROR.json" if OUTPUT.exists() else OUTPUT.parent / "t20a_startup_ERROR.json"
        err.parent.mkdir(parents=True, exist_ok=True)
        write_json(err, {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
