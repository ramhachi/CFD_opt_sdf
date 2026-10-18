#!/usr/bin/env python3
"""T2-0b kernel (#57, REGISTERED_FROZEN; fork of infra/kaggle/kernel_t20a_cpu/runner.py): 2D RANS Tyrrell 026 ground-effect cases on Kaggle CPU, OpenFOAM v2512.

Registration: docs/t20b_registration_2026_10_19.md. Template: scripts/build_t20b_kernel.py fills PIN_SOURCE_COMMIT, PIN_MODE and PIN_PINS and verifies the pins.
Order (cheap failures first): environment -> pinned source -> gmsh install + one meshing probe -> OpenFOAM install (hash-locked, from the XFID X3 runner)
-> smoke stage (infrastructure gate) -> registered case list, independent cases concurrently.
MODE "wf" (kernel W): wall-function sweep and incidence cases, plus the adjointOptimisationFoam feasibility run attached to one case.
MODE "lm" (kernel L): kOmegaSSTLM continuation cases (kOmegaSST, then the model switched; a failure of either stage is the case result LM_DIVERGED).
MODE "smoke": development smoke before the code freeze (every code path at <= 200 iterations; force values are not analysed).
Measurement only: no verdict here (scripts/analyze_t20b.py computes it). Kernel-level failures write ERROR.json and raise; DONE is written last.
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
MODE = "PIN_MODE"                          # "smoke" | "wf" | "lm", rendered by scripts/build_t20b_kernel.py
PINS = PIN_PINS  # {repo path: sha256}, rendered
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
LOCKS = {"jammy": "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json", "noble": "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json"}  # the two hash-pinned OpenCFD v2512 locks registered by XFID X2/X3; chosen by the observed Ubuntu codename
GMSH_PIN = "gmsh==4.15.2"
FOAM_VERSION = "OpenFOAM-v2512"
OUTPUT = Path(os.environ.get("T20B_OUTPUT", "/kaggle/working/t20b"))
BASHRC = os.environ.get("T20B_BASHRC", "/usr/lib/openfoam/openfoam2512/etc/bashrc")
WORKERS, RESERVE_S = 4, 600                            # concurrent independent cases (4 vCPU)
BUDGET_S = {"smoke": 3 * 3600, "wf": 11 * 3600, "lm": 11.5 * 3600}   # kernel budget per mode (Kaggle limit 12 h)
CASE_CAP_S = {"wf": 2.5 * 3600, "wr": 11 * 3600}       # per-case solver cap, by wall treatment
ADJ_TIMEOUT_S = 2 * 3600
HEIGHTS = (0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09)
INC_HEIGHTS, SCAN_HEIGHTS = (0.224, 0.134, 0.09), (0.224, 0.134)
MESH_ORDER = {"fine30": 0, "med30": 1, "coa30": 2}     # expected cost, largest first
# registered case lists (docs/t20b_registration_2026_10_19.md section 5): (model, h/c, mesh, delta alpha [deg])
WF_CASES = sorted([("sa-wf", h, m, 0.0) for m in MESH_ORDER for h in HEIGHTS]
                  + [("sa-wf", h, m, da) for m in MESH_ORDER for h in INC_HEIGHTS for da in (-1.0, 1.0)]
                  + [("sa-wf", h, "med30", da) for h in SCAN_HEIGHTS for da in (-0.5, -0.25, 0.25, 0.5)]
                  + [("sst-wf", h, "med30", 0.0) for h in HEIGHTS]
                  + [("sst-wf", h, "med30", da) for h in INC_HEIGHTS for da in (-1.0, 1.0)], key=lambda c: (MESH_ORDER[c[2]], c[0], -c[1], c[3]))
LM_CASES = [("sst-lm", h, "wr2", 0.0) for h in (0.224, 0.134, 0.09)] + [("sa-wf", 0.224, "med30", 0.0)]   # the sa-wf case carries the adjoint
LM_ITERS = 14000                                       # 2000 kOmegaSST + 12000 kOmegaSSTLM (t20_case: sst_iters = min(2000, iters // 2))
ADJOINT = {"case": ("sa-wf", 0.224, "med30", 0.0), "primal_iters": 300, "adjoint_iters": 5000}
GATE_SMOKE = {"wf": [("sa-wf", 0.224, "coa30", 0.0), ("sst-wf", 0.224, "coa30", 0.0)], "lm": [("sa-wf", 0.224, "coa30", 0.0)]}
SMOKE_ITERS = 200
# development smoke (MODE "smoke"): every solver path at <= 200 iterations; force/derivative values are deleted before output
DEV_SMOKE = [("sa-wf", 0.224, "coa30", 1.0), ("sst-wf", 0.224, "coa30", 0.0), ("sst-lm", 0.224, "wrc", 0.0), ("sa-wf", 0.224, "coa30", 0.0)]
DEV_ADJOINT = {"case": ("sa-wf", 0.224, "coa30", 0.0), "primal_iters": 20, "adjoint_iters": 30}
CONT_ITERS = 15000                                     # one continuation when the Cl plateau fails at the registered iteration count
TAIL_FRACTION, PLATEAU_REL, BLOCK, SETTLE_REL = 0.2, 0.005, 20, 0.002
NUM = r"[-+0-9.eE]+"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value) -> None:
    """Atomic (temp file + rename): a kernel kill never leaves a truncated JSON."""
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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


def read_coefficients(dats) -> list[dict]:
    """Rows of one or more forceCoeffs coefficient.dat files, in the given order (a continuation writes a second file)."""
    rows = []
    for dat in dats:
        header = None
        for line in Path(dat).read_text().splitlines():
            if line.startswith("#"):
                header = line.lstrip("#").split()
            elif line.strip():
                rows.append(dict(zip(header, (float(x) for x in line.split()))))
    require(len(rows) > 1 and all(math.isfinite(v) for r in rows for v in r.values()), "force coefficient history empty or non-finite")
    return rows


def _rel_drift(v: np.ndarray) -> float:
    x = np.arange(len(v)) - (len(v) - 1) / 2
    return abs(float((x * (v - v.mean())).sum() / (x * x).sum() * (len(v) - 1))) / abs(float(v.mean()))


def force_summary(rows: list[dict], history: list[dict] | None = None) -> dict:
    """Tail statistics over the last 20 % of `rows` (at least 50). Registered validity: `cl_plateau` = relative std and relative linear drift of the
    BLOCK-iteration block means of Cl over the tail both < 0.5 % (a period-2 alternation averages out). `force_plateau` (Cl and Cd, raw) is descriptive.
    `iterations_to_plateau`: first iteration of `history` (default rows) after which Cl stays within 0.2 % of the tail mean. Half-window means for LM cycles."""
    n = min(len(rows), max(50, math.ceil(len(rows) * TAIL_FRACTION)))
    out = {"rows": len(rows), "last_iteration": rows[-1]["Time"], "tail_rows": n}
    for key in ("Cl", "Cd"):
        v = np.array([r[key] for r in rows[-n:]])
        half = len(v) // 2
        out[key] = {"last": float(rows[-1][key]), "tail_mean": float(v.mean()), "tail_std": float(v.std()), "tail_min": float(v.min()),
                    "tail_max": float(v.max()), "tail_rel_std": float(v.std() / abs(v.mean())), "tail_rel_drift": _rel_drift(v),
                    "half_window_rel_diff": abs(float(v[:half].mean() - v[half:].mean())) / abs(float(v.mean()))}
    out["force_plateau"] = all(out[k]["tail_rel_std"] < PLATEAU_REL and out[k]["tail_rel_drift"] < PLATEAU_REL for k in ("Cl", "Cd"))
    cl = np.array([r["Cl"] for r in rows[-n:]])
    blocks = cl[len(cl) % BLOCK:].reshape(-1, BLOCK).mean(1)
    ok = len(blocks) > 2   # fewer than 3 blocks (a history of about 280 rows or less): no plateau, statistics recorded as None (JSON has no inf/nan)
    out["cl_block_rel_std"] = float(blocks.std() / abs(blocks.mean())) if ok else None
    out["cl_block_rel_drift"] = _rel_drift(blocks) if ok else None
    out["cl_plateau"] = bool(ok and out["cl_block_rel_std"] < PLATEAU_REL and out["cl_block_rel_drift"] < PLATEAU_REL)
    hist = np.array([r["Cl"] for r in (history or rows)])
    off = np.flatnonzero(np.abs(hist / out["Cl"]["tail_mean"] - 1) > SETTLE_REL)
    out["iterations_to_plateau"] = int(off[-1] + 2) if len(off) else 1   # 1-based iteration after the last excursion
    out["history_rows"] = len(hist)
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


def run_adjoint(case: Path, keep: Path, source: Path, spec: dict, timeout: float) -> dict:
    """adjointOptimisationFoam (singleRun) on a copy of the converged primal case; returns the ADJ_* record (the analyzer decides ADJ_CONSISTENT).
    Asserted before trusting a projection: the control box contains every section point, the derivative varIDs cover every control point."""
    sys.path.insert(0, str(source / "scripts"))
    import t20_case
    import t20b_adjoint as adj
    rec = {"status": "ADJ_NOT_RUN", **spec["adjoint"]}
    probe = subprocess.run(["bash", "-lc", f"source {BASHRC} && command -v adjointOptimisationFoam"], capture_output=True, text=True)
    rec["binary"] = probe.stdout.strip() or None
    if probe.returncode or not rec["binary"]:
        return rec
    man = json.loads((case / "case_manifest.json").read_text())
    q, _, i_le = t20_case.airfoil_points(spec["h"], spec["da"])
    x_low, y_le = man["mesh_stats"]["x_lowest_m"], float(q[i_le, 1])
    lo, hi = adj.box_bounds(man["h_m"], man["chord_m"], man["z_m"])
    rec.update(x_low_m=x_low, y_le_m=y_le, box=[list(lo), list(hi)],
               box_contains_section=bool((q[:, 0] > lo[0]).all() and (q[:, 0] < hi[0]).all() and (q[:, 1] > lo[1]).all() and (q[:, 1] < hi[1]).all()))
    a = case / "adjoint"
    shutil.copytree(case / "constant", a / "constant")
    shutil.copytree(case / "system", a / "system")
    (a / "0").mkdir()
    for f in _latest_time(case).iterdir():
        if f.is_file():
            shutil.copy(f, a / "0" / f.name)
    files = {"system/optimisationDict": adj.optimisation_dict(man["U_inf"], man["Aref_m2"], rec["primal_iters"], rec["adjoint_iters"]),
             "constant/dynamicMeshDict": adj.dynamic_mesh_dict(lo, hi), **adj.adjoint_fields(),
             "system/controlDict": adj.control_dict((case / "system/controlDict").read_text()),
             "system/fvSchemes": adj.fv_schemes((case / "system/fvSchemes").read_text()),
             "system/fvSolution": adj.fv_solution((case / "system/fvSolution").read_text())}
    for rel, txt in files.items():
        (a / rel).write_text(txt)
    stage = timed_run("adjointOptimisationFoam", "adjointOptimisationFoam", a, timeout)
    log = (a / "log.adjointOptimisationFoam").read_text(errors="replace")
    first_ua = log.find("Solving for Ua")
    rec.update(stage=stage, foam_fatal="FOAM FATAL" in log, sigfpe="sigFpe::sigHandler" in log, adjoint_iterations_logged=len(re.findall(r"Solving for Ua\w*x,", log)),
               converged_in={k: int(m.group(1)) for k in ("op1", adj.SOLVER) for m in [re.search(rf"^{k} solution converged in (\d+) iterations", log, re.M)] if m},
               primal=parse_solver(log[:first_ua] if first_ua >= 0 else log), log_tail=_keep_text("\n".join(log.splitlines()[-40:])).splitlines())
    ders = sorted((a / "optimisation/derivatives").glob("*"), key=lambda p: p.stat().st_mtime) if (a / "optimisation/derivatives").is_dir() else []
    csvs = sorted((a / "optimisation/controlPoints").glob("*.csv")) if (a / "optimisation/controlPoints").is_dir() else []
    rec["derivative_files"], rec["control_point_files"] = [p.name for p in ders], [p.name for p in csvs]
    kept = [a / "log.adjointOptimisationFoam", a / "system/optimisationDict", a / "constant/dynamicMeshDict"] + ([] if MODE == "smoke" else [*ders, *csvs])
    for p in kept:
        if p.is_file():
            data = _keep_text(p.read_text(errors="replace")).encode() if p.name.startswith("log.") else p.read_bytes()
            with gzip.open(keep / f"adjoint_{p.name}.gz", "wb") as dst:
                dst.write(data)
    if rec["adjoint_iterations_logged"] == 0:
        return rec   # ADJ_NOT_RUN: fatal or missing before the first adjoint iteration
    rec["status"] = "ADJ_FAILED"
    if not ders or not csvs or not rec["box_contains_section"]:   # a nonzero return code with finite derivatives is still ADJ_RUNS (registered definition)
        return rec
    try:
        rec["projection"] = adj.projected_derivatives(ders[-1].read_text(), csvs[0].read_text(), x_low, y_le)
        p = rec["projection"]
        rec["projection"]["box_contains_section"] = rec["box_contains_section"]
        if p["varids_complete"] and all(math.isfinite(p[k]) for k in ("rotation_per_deg", "x_translation_per_mm", "y_translation_per_mm")):
            rec["status"] = "ADJ_RUNS"
    except Exception as exc:
        rec["projection_error"] = f"{type(exc).__name__}: {exc}"
    return rec


def blown_up(forces) -> bool:
    return bool(forces) and any(abs(forces[k][m]) > 100 for k in ("Cl", "Cd") for m in ("last", "tail_min", "tail_max"))   # a wing at these Re has |Cl|, |Cd| of order 1


FORCE_LINE = re.compile(r"\b(C[dlmsy]\w*|\w*[Ff]orces?|[Mm]oments?|Total|Pressure|Viscous|Internal|Coefficients?)\b|^\s*\w+\s*:\s*" + NUM + r"\s*$")   # forces/forceCoeffs/objective lines


def _keep_text(text: str) -> str:
    """Smoke mode: drop every log line that could carry a force or coefficient value."""
    return "\n".join(l for l in text.splitlines() if not FORCE_LINE.search(l)) if MODE == "smoke" else text


def parse_yplus(text: str) -> dict:
    """`simpleFoam -postProcess -func yPlus` log: per patch min/max/average (the last occurrence per patch)."""
    out = {}
    for patch, lo, hi, avg in re.findall(rf"patch (\w+) y\+ : min = ({NUM}), max = ({NUM}), average = ({NUM})", text):
        out[patch] = {"min": float(lo), "max": float(hi), "average": float(avg)}
    return out


def _continue(case: Path, end: int) -> None:
    """Continuation from the latest time to `end` iterations (the registered one-time extension when the Cl plateau fails)."""
    cd = case / "system/controlDict"
    text = re.sub(r"^startFrom .*;$", "startFrom latestTime;", cd.read_text(), count=1, flags=re.M)
    cd.write_text(re.sub(r"^endTime .*;$", f"endTime {end};", text, count=1, flags=re.M))


def run_case(spec: dict, source: Path, deadline: float) -> dict:
    cid, solve, lm = spec["id"], spec.get("solve", True), spec["model"] == "sst-lm"
    case = OUTPUT / "work" / cid
    keep = OUTPUT / "cases" / cid
    keep.mkdir(parents=True)
    rec = {"id": cid, "model": spec["model"], "h_over_c": spec["h"], "mesh": spec["mesh"], "delta_alpha_deg": spec["da"], "iterations_requested": spec["iters"],
           "stages": [], "status": "COMPLETED", "mode": MODE}
    t0 = time.monotonic()
    cmd = [sys.executable, str(source / "scripts/t20_case.py"), "--h-over-c", str(spec["h"]), "--model", spec["model"], "--mesh", spec["mesh"],
           "--delta-alpha-deg", str(spec["da"]), "--iters", str(spec["iters"]), "--out", str(case)]
    gen = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": f"{source}/scripts"})
    (keep / "log.t20_case").write_text(gen.stdout + gen.stderr)
    rec["generator_wall_s"] = time.monotonic() - t0
    if gen.returncode:
        rec["status"] = "GENERATOR_FAILED"
    cap = CASE_CAP_S[spec["wall"]]
    for name, command in (("gmshToFoam", "gmshToFoam mesh.msh"), ("checkMesh", "checkMesh -allGeometry -allTopology"), ("simpleFoam", "simpleFoam")):
        if rec["status"] != "COMPLETED" or (name == "simpleFoam" and not solve):
            break
        if name == "simpleFoam":
            rec["pre_solver_wall_s"] = time.monotonic() - t0
        timeout = min(cap * (0.3 if lm else 1), deadline - time.monotonic()) if name == "simpleFoam" else 900
        if name == "simpleFoam" and timeout < cap * (0.3 if lm else 1):
            rec["deadline_limited"] = True
        if name == "checkMesh":  # gmshToFoam writes every patch as `patch`: front/back must be empty and airfoil/ground wall
            sys.path.insert(0, str(source / "scripts"))
            import t20_foam
            b = case / "constant/polyMesh/boundary"
            b.write_text(t20_foam.fix_boundary(b.read_text()))
        stage = timed_run(name, command, case, timeout)
        rec["stages"].append(stage)
        if name == "checkMesh":
            rec["check_mesh_returncode"] = stage["returncode"]
        elif stage["returncode"] or stage["timed_out"]:
            rec["status"] = f"{name}_{'TIMEOUT' if stage['timed_out'] else 'FAILED'}"
    text = lambda n: (case / f"log.{n}").read_text(errors="replace") if (case / f"log.{n}").is_file() else ""
    dats = lambda: sorted(case.glob("postProcessing/forceCoeffs/*/coefficient.dat"), key=lambda d: float(d.parent.name))
    if lm and solve and rec["status"] == "simpleFoam_FAILED":
        rec["status"], rec["lm_failed_stage"] = "LM_DIVERGED", "stage1_kOmegaSST"
    if lm and solve and rec["status"] == "COMPLETED":
        rec["deadline_limited"] = rec.get("deadline_limited") or deadline - time.monotonic() < cap - rec["stages"][-1]["wall_s"]
        stage = run_lm_stage(case, min(cap - rec["stages"][-1]["wall_s"], deadline - time.monotonic()))
        rec["stages"].append(stage)
        if stage["returncode"] or stage["timed_out"]:
            rec["status"], rec["lm_failed_stage"] = ("SOLVER_TIMEOUT_PARTIAL" if stage["timed_out"] else "LM_DIVERGED"), "stage2_kOmegaSSTLM"
    if not lm and solve and rec["status"] == "COMPLETED" and (spec["iters"] >= 5000 or spec.get("force_continuation")):   # registered one-time continuation if the Cl plateau fails
        try:
            plateau = force_summary(read_coefficients(dats()))["cl_plateau"] and not spec.get("force_continuation")
        except Exception:
            plateau = True   # unreadable history: left to the parser below, not continued
        if not plateau:
            _continue(case, spec["cont_iters"])
            rec["deadline_limited"] = rec.get("deadline_limited") or deadline - time.monotonic() < cap - rec["stages"][-1]["wall_s"]
            stage = timed_run("simpleFoam_cont", "simpleFoam", case, min(cap - rec["stages"][-1]["wall_s"], deadline - time.monotonic()))
            rec["stages"].append(stage)
            rec["continued_to"] = spec["cont_iters"]
            if stage["returncode"] or stage["timed_out"]:
                rec["status"] = f"simpleFoam_cont_{'TIMEOUT' if stage['timed_out'] else 'FAILED'}"
    if solve and rec["status"] in ("COMPLETED", "SOLVER_TIMEOUT_PARTIAL"):
        y = timed_run("yPlus", "simpleFoam -postProcess -func yPlus -latestTime", case, 600)
        rec["yplus"] = parse_yplus(text("yPlus"))
        rec["yplus_returncode"] = y["returncode"]
    rec["total_wall_s"] = time.monotonic() - t0
    try:
        rec["check_mesh"] = parse_check_mesh(text("checkMesh"))
        rec["solver"] = parse_solver(text("simpleFoam"))
        if lm:
            rec["solver_lm"] = parse_solver(text("simpleFoam_lm"))
        if "continued_to" in rec:
            rec["solver_cont"] = parse_solver(text("simpleFoam_cont"))
        files = dats()
        if files:
            if lm:   # stage 2 writes to <stage-1 end time>/; an LM case reports `forces` for the LM stage only
                if files[0].parent.name == "0":
                    rec["forces_stage1_kOmegaSST"] = force_summary(read_coefficients(files[:1]))
                if len(files) > 1 or files[0].parent.name != "0":
                    rec["forces"] = force_summary(read_coefficients(files[-1:]))
            else:    # a continued case is judged on the continuation, iterations to plateau on the whole history
                rec["forces"] = force_summary(read_coefficients(files[-1:]), read_coefficients(files))
        last = rec.get("solver_lm") if lm else rec.get("solver_cont", rec["solver"])
        rec["residual_converged"] = bool(last and last["converged_in"] is not None)
        if rec["status"].endswith("_TIMEOUT") and "forces" in rec:
            rec["status"] = "SOLVER_TIMEOUT_PARTIAL"
        if rec["status"] == "COMPLETED" and (blown_up(rec.get("forces")) or (last or {}).get("nan_in_log")):
            rec["status"] = "LM_DIVERGED" if lm else "SOLVER_DIVERGED"
            rec["lm_failed_stage"] = "stage2_kOmegaSSTLM" if lm else None
    except Exception as exc:
        rec["parse_error"] = f"{type(exc).__name__}: {exc}"
        rec["status"] = rec["status"] if rec["status"] != "COMPLETED" else "PARSE_FAILED"
    if rec["status"] in ("LM_DIVERGED", "SOLVER_DIVERGED") or rec["status"].endswith("_FAILED"):
        log = text("simpleFoam_lm") if rec.get("lm_failed_stage") == "stage2_kOmegaSSTLM" else text("simpleFoam_cont") or text("simpleFoam")
        rec["failure_log_tail"] = _keep_text("\n".join(log.splitlines()[-40:])).splitlines()
    if rec.get("deadline_limited") and ("TIMEOUT" in rec["status"] or rec["status"] == "SOLVER_TIMEOUT_PARTIAL"):
        rec["status"] = "DEADLINE_LIMITED"   # cut by the kernel budget, not by the per-case cap: an infrastructure loss (registration section 6)
    if not solve and "check_mesh" in rec:
        rec["status"] = "MESH_OK" if rec["status"] == "COMPLETED" and rec["check_mesh"]["mesh_ok"] and not rec["check_mesh"]["failed_check_counts"] else (
            "MESH_FAILED" if rec["status"] == "COMPLETED" else rec["status"])
    if (case / "case_manifest.json").is_file():
        man = json.loads((case / "case_manifest.json").read_text())
        rec["mesh_cells_3d"], rec["mesh_proxy_failures"] = man["mesh_stats"]["cells_3d"], man["mesh_quality_failures"]
        rec["h_m"], rec["x_lowest_m"] = man["h_m"], man["mesh_stats"]["x_lowest_m"]
    if solve and spec.get("adjoint") and rec["status"] == "COMPLETED":
        left = deadline - time.monotonic()
        try:
            rec["adjoint"] = run_adjoint(case, keep, source, spec, min(ADJ_TIMEOUT_S, left)) if left > 600 else {"status": "ADJ_NOT_RUN", "reason": "kernel budget"}
        except Exception as exc:
            rec["adjoint"] = {"status": "ADJ_FAILED", "error": f"{type(exc).__name__}: {exc}"}
    if MODE == "smoke":   # registration section 8: no force, coefficient or derivative value leaves the smoke kernel
        for k in ("forces", "forces_stage1_kOmegaSST"):
            if k in rec:
                rec[k] = {"rows": rec[k]["rows"], "values": "suppressed (smoke), including the force-derived plateau flag"}
        if "adjoint" in rec and "projection" in rec["adjoint"]:
            rec["adjoint"]["projection"] = {k: v for k, v in rec["adjoint"]["projection"].items() if k in ("n_vars", "n_cps", "varids_complete", "box_contains_section")}
    if case.exists():
        logs = [*case.glob("log.*")]
        kept = logs + ([] if MODE == "smoke" else [*case.glob("postProcessing/*/*/*.dat"), case / "mesh.msh"]) + [case / "case_manifest.json"]
        for p in kept:
            if p.is_file() and not (p.name == "mesh.msh" and not solve):
                prefix = "" if p.parent.name in ("0", case.name) else f"t{p.parent.name}_"
                data = p.read_bytes() if not p.name.startswith("log.") else _keep_text(p.read_text(errors="replace")).encode()
                with gzip.open(keep / (prefix + p.name + ".gz"), "wb") as dst:
                    dst.write(data)
        for d in ("0", "system", "constant", "stage2"):
            if (case / d).is_dir():
                shutil.copytree(case / d, keep / "case_dict" / d, ignore=shutil.ignore_patterns("polyMesh"))
        shutil.rmtree(case, ignore_errors=True)
    write_json(keep / "case_result.json", rec)
    return rec


def make_specs(items, iters=None, adjoint=None, cont_iters=CONT_ITERS, solve=True, force_continuation=False):
    sys.path.insert(0, str(SOURCE / "scripts"))
    import t20_case
    out = []
    for m, h, mesh, da in items:
        tag = f"{m}_h{h}_{mesh}_da{'0' if da == 0 else format(da, '+g')}" + ("" if solve else "_mesh") + ("_smoke" if iters else "")
        it = iters or (LM_ITERS if m == "sst-lm" else t20_case.MODELS[m]["iters"])
        spec = {"id": tag, "model": m, "h": h, "mesh": mesh, "da": da, "wall": t20_case.MODELS[m]["wall"], "iters": it, "solve": solve,
                "cont_iters": cont_iters, "force_continuation": force_continuation and m != "sst-lm"}
        if adjoint and (m, h, mesh, da) == adjoint["case"] and solve:
            spec["adjoint"] = {"primal_iters": adjoint["primal_iters"], "adjoint_iters": adjoint["adjoint_iters"]}
        out.append(spec)
    return out


def infrastructure_ok(r: dict) -> bool:
    s = r.get("solver", {})
    return r["status"] == "COMPLETED" and "forces" in r and s.get("iterations", 0) >= SMOKE_ITERS - 1 and not s.get("nan_in_log") and r["forces"]["last_iteration"] >= SMOKE_ITERS - 1


def unique_geometries(items):
    """(wall-treatment model, h, mesh, da) once per geometry: sa-wf and sst-wf on the same mesh spec share it."""
    seen, out = set(), []
    for m, h, mesh, da in items:
        if (h, mesh, da) not in seen:
            seen.add((h, mesh, da))
            out.append((m, h, mesh, da))
    return out


def main() -> None:
    global SOURCE
    require(SOURCE_COMMIT != "PIN_SOURCE_COMMIT" and MODE in BUDGET_S, "runner has not been rendered by scripts/build_t20b_kernel.py")
    require(not OUTPUT.exists(), f"refusing to overwrite prior output: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "work").mkdir()
    started = time.monotonic()
    cpuinfo = Path("/proc/cpuinfo").read_text() if Path("/proc/cpuinfo").exists() else ""
    cpu_model = next((l.split(":", 1)[1].strip() for l in cpuinfo.splitlines() if l.startswith("model name")), None)
    meminfo = Path("/proc/meminfo").read_text().splitlines()[0] if Path("/proc/meminfo").exists() else None
    write_json(OUTPUT / "environment.json", {"python": sys.version, "cpu_count": os.cpu_count(), "cpu_model": cpu_model, "meminfo_first_line": meminfo,
                                             "uname": list(os.uname()), "source_commit": SOURCE_COMMIT, "mode": MODE, "pins": PINS,
                                             "runner_sha256": sha(Path(__file__).resolve())})
    SOURCE = fetch_source(OUTPUT / "work")
    gmsh_version = install_gmsh()
    sys.path.insert(0, str(SOURCE / "scripts"))
    import t20_case
    probe = OUTPUT / "work" / "mesh_probe"
    probe_man = t20_case.write_case(probe, 0.09, "sa-wf", "coa30", iters=1)   # fail fast on meshing before the OpenFOAM install
    require(probe_man["mesh_stats"]["gap_cells_at_lowest_point"] >= 15, f"mesh probe gap cells {probe_man['mesh_stats']['gap_cells_at_lowest_point']}")
    require(not probe_man["mesh_quality_failures"], f"mesh probe fails the local quality proxy: {probe_man['mesh_quality_failures']}")
    shutil.rmtree(probe)
    locks = {name: json.loads((SOURCE / rel).read_text()) for name, rel in LOCKS.items()}
    install = install_openfoam(OUTPUT / "work", locks)
    write_json(OUTPUT / "install.json", {**install, "gmsh_version": gmsh_version, "mesh_probe_cells": probe_man["mesh_stats"]["cells_3d"]})
    deadline = started + BUDGET_S[MODE] - RESERVE_S
    results, lock_ = [], threading.Lock()

    def summary():
        return {"runner_sha256": sha(Path(__file__).resolve()), "source_commit": SOURCE_COMMIT, "mode": MODE, "install": install, "gmsh_version": gmsh_version,
                "elapsed_s": time.monotonic() - started, "workers": WORKERS, "cpu_model": cpu_model, "cases": results,
                "qualification_flags": "none (T2-0b measurement; the verdict is computed by scripts/analyze_t20b.py)"}

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

    if MODE == "smoke":
        execute(make_specs(unique_geometries(WF_CASES + LM_CASES), solve=False), results)
        execute(make_specs(DEV_SMOKE, SMOKE_ITERS // 2, DEV_ADJOINT, cont_iters=SMOKE_ITERS, force_continuation=True), results)
    else:
        smoke = execute(make_specs(GATE_SMOKE[MODE], SMOKE_ITERS), [])
        write_json(OUTPUT / "smoke.json", smoke)
        bad = [r for r in smoke if not infrastructure_ok(r)]
        require(not bad, f"smoke stage failed (infrastructure): {[(r['id'], r['status']) for r in bad]}")
        execute(make_specs(WF_CASES if MODE == "wf" else LM_CASES, adjoint=ADJOINT if MODE == "lm" else None), results)
    shutil.rmtree(OUTPUT / "work", ignore_errors=True)
    manifest = {str(p.relative_to(OUTPUT)): sha(p) for p in sorted(OUTPUT.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    write_json(OUTPUT / "artifact_manifest.json", manifest)
    counts = {}
    for c in results:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    (OUTPUT / "DONE").write_text(json.dumps({"status": f"FINISHED_{MODE.upper()}", "status_counts": counts, "artifact_manifest_sha256": sha(OUTPUT / "artifact_manifest.json")}, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        err = OUTPUT / "ERROR.json" if OUTPUT.exists() else OUTPUT.parent / "t20b_startup_ERROR.json"
        err.parent.mkdir(parents=True, exist_ok=True)
        write_json(err, {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
