#!/usr/bin/env python3
"""T2-0c kernel (#57, registration docs/t20c_registration_2026_10_20.md; fork of infra/kaggle/kernel_t20b_cpu/runner.py): 2D RANS Tyrrell 026 ground-effect
cases on Kaggle CPU, OpenFOAM v2512, SA wall functions; remeshed and fixed-topology morphed incidence scans on four mesh levels.

Template: scripts/build_t20c_kernel.py fills PIN_SOURCE_COMMIT, PIN_MODE and PIN_PINS and verifies the pins.
Order (cheap failures first): environment -> pinned source -> gmsh install + one meshing probe -> OpenFOAM install (hash-locked, as T2-0b)
-> smoke stage (infrastructure gate) -> [morph, shape, smoke: base stage, the base meshes generated once] -> registered case list, cases concurrently.
MODE "remesh" (kernel R): the 0-deg sweep and the remeshed incidence scans (every geometry meshed by the pinned generator).
MODE "morph" (kernel M): the 0-deg baselines solved, the morphed incidence scans, the second-baseline (B', +0.5 deg) morphs and the linear-blend morphs.
MODE "shape" (kernel S): the 0-deg baselines solved, the morphed shape cases and the remeshed shape cases.
A morphed case must keep its base's polyMesh topology (faces, owner, neighbour, boundary SHA-256 recorded in the base stage), else TOPOLOGY_CHANGED
(BASE_TOPOLOGY_MISSING if the base had none); a case failing checkMesh is not solved (checkMesh_FAILED). All three are mechanical failures.
MODE "smoke": development smoke before the code freeze (mesh-only pass over every registered geometry of the three kernels, each solver path at <= 200
iterations; force values are removed before output). Measurement only: no verdict here (scripts/analyze_t20c.py). Kernel-level failures write ERROR.json and raise; DONE last.
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
MODE = "PIN_MODE"                          # "smoke" | "remesh" | "morph" | "shape", rendered by scripts/build_t20c_kernel.py
PINS = PIN_PINS  # {repo path: sha256}, rendered
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
LOCKS = {"jammy": "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json", "noble": "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json"}  # the two hash-pinned OpenCFD v2512 locks registered by XFID X2/X3; chosen by the observed Ubuntu codename
GMSH_PIN = "gmsh==4.15.2"
FOAM_VERSION = "OpenFOAM-v2512"
OUTPUT = Path(os.environ.get("T20C_OUTPUT", "/kaggle/working/t20c"))
BASHRC = os.environ.get("T20C_BASHRC", "/usr/lib/openfoam/openfoam2512/etc/bashrc")
WORKERS, RESERVE_S = 4, 600                            # concurrent independent cases (4 vCPU)
BUDGET_S = {"smoke": 3 * 3600, "remesh": 11 * 3600, "morph": 11 * 3600, "shape": 11 * 3600}   # kernel budget per mode (Kaggle limit 12 h)
CASE_CAP_S = 2.5 * 3600                                # per-case solver cap
ITERS, CONT_ITERS = 5000, 15000                        # registered iterations; one continuation when the Cl plateau fails
HEIGHTS = (0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09)
SCAN_H = (0.224, 0.134, 0.09)
SCAN_DA = (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0)          # nonzero scan incidences [deg]; 0 is the sweep case (R) or the baseline (M)
SHAPES, SHAPE_AMPS, SHAPE_MESHES = ("camber", "flap", "heave"), (-0.5, -0.25, 0.25, 0.5), ("med30", "fine30")   # mm
MESH_ORDER = {"xfine30": 0, "fine30": 1, "med30": 2, "coa30": 3}   # expected cost, largest first
LEVELS = ("xfine30", "fine30", "med30")                # scanned levels (coa30: sweep only)
B2_DA, B2_TARGETS, B2_MESHES = 0.5, (-1.0, -0.25, 0.25, 1.0), ("fine30", "med30")   # second baseline B' (+0.5 deg) and its morph targets
# registered case lists (registration section 5): (method, h/c, mesh, mode, amp, variant); method remesh | base | morph; amp in deg (incidence) or mm (shapes);
# variant "" (0-deg base, smoothstep blend), "B2" (from B'), "lin" (linear blend)
_order = lambda c: (MESH_ORDER[c[2]], -c[1], c[0], c[5], c[3], c[4])
R_CASES = sorted([("remesh", h, m, "incidence", 0.0, "") for m in MESH_ORDER for h in HEIGHTS]
                 + [("remesh", h, m, "incidence", da, "") for m in LEVELS for h in SCAN_H for da in SCAN_DA], key=_order)
M_CASES = sorted([("base", h, m, "incidence", 0.0, "") for m in LEVELS for h in SCAN_H]
                 + [("morph", h, m, "incidence", da, "") for m in LEVELS for h in SCAN_H for da in SCAN_DA]
                 + [("morph", h, m, "incidence", da, "B2") for m in B2_MESHES for h in SCAN_H for da in B2_TARGETS]
                 + [("morph", h, "fine30", "incidence", da, "lin") for h in SCAN_H for da in (-1.0, 1.0)], key=_order)
S_CASES = sorted([("base", h, m, "incidence", 0.0, "") for m in SHAPE_MESHES for h in SCAN_H]
                 + [("morph", h, m, mode, a, "") for m in SHAPE_MESHES for h in SCAN_H for mode in SHAPES for a in SHAPE_AMPS]
                 + [("remesh", h, "fine30", mode, a, "") for h in SCAN_H for mode in SHAPES for a in (-0.5, 0.5)], key=_order)
CASES = {"remesh": R_CASES, "morph": M_CASES, "shape": S_CASES}
BASES = {"remesh": [], "morph": [(m, h, 0.0) for m in LEVELS for h in SCAN_H] + [(m, h, B2_DA) for m in B2_MESHES for h in SCAN_H],
         "shape": [(m, h, 0.0) for m in SHAPE_MESHES for h in SCAN_H]}
BASES["smoke"] = BASES["morph"]                        # a superset of the shape kernel's
GATE_SMOKE = [("remesh", 0.224, "coa30", "incidence", 0.0, "")]
SMOKE_ITERS = 200
TOPOLOGY_FILES = ("faces", "owner", "neighbour", "boundary")
# development smoke (MODE "smoke"): each solver path at <= 200 iterations (the continuation forced); force values are deleted before output
DEV_SMOKE = [("remesh", 0.09, "xfine30", "incidence", 1.0, ""), ("morph", 0.09, "xfine30", "incidence", 1.0, ""), ("morph", 0.134, "fine30", "incidence", -1.0, "B2"),
             ("morph", 0.224, "fine30", "incidence", 1.0, "lin"), ("morph", 0.134, "fine30", "flap", 0.5, ""), ("remesh", 0.09, "fine30", "camber", 0.5, ""),
             ("base", 0.224, "med30", "incidence", 0.0, "")]
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


def _set_iters(case: Path, n: int) -> None:
    """endTime and writeInterval = n (a morphed or copied case inherits the baseline's registered 5000)."""
    cd = case / "system/controlDict"
    text = re.sub(r"^endTime .*;$", f"endTime {n};", cd.read_text(), count=1, flags=re.M)
    cd.write_text(re.sub(r"^writeInterval .*;$", f"writeInterval {n};", text, count=1, flags=re.M))


def base_da(spec: dict) -> float:
    return B2_DA if spec["variant"] == "B2" else 0.0


def base_dir(mesh: str, h: float, da: float = 0.0) -> Path:
    return OUTPUT / "work" / "base" / f"{mesh}_h{h}_da{'0' if da == 0 else format(da, '+g')}"


def generate(spec: dict, source: Path, case: Path) -> subprocess.CompletedProcess:
    """remesh: the pinned generator through scripts/t20c_case.py (incidence or a shape contour); base: a copy of the kernel's 0-deg baseline;
    morph: scripts/t20c_case.py --base (the variant picks the base and the blend). A copied or morphed case inherits the base's iteration count."""
    py = [sys.executable, str(source / "scripts/t20c_case.py"), "--out", str(case)]
    if spec["method"] == "remesh":
        cmd = py + ["--h-over-c", str(spec["h"]), "--mesh", spec["mesh"], "--iters", str(spec["iters"])]
        cmd += ["--delta-alpha-deg", str(spec["amp"])] if spec["mode"] == "incidence" else ["--shape", spec["mode"], "--shape-amp", str(spec["amp"])]
    elif spec["method"] == "morph":
        cmd = py + ["--base", str(base_dir(spec["mesh"], spec["h"], base_da(spec))), "--mode", spec["mode"], "--amp", str(spec["amp"])]
        cmd += ["--blend", "linear"] if spec["variant"] == "lin" else []
    else:   # a missing base (its generation failed) is a generator failure of this case, not an infrastructure loss
        try:
            shutil.copytree(base_dir(spec["mesh"], spec["h"]), case)
            gen = subprocess.CompletedProcess([], 0, f"copied {base_dir(spec['mesh'], spec['h'])}\n", "")
        except OSError as exc:
            gen = subprocess.CompletedProcess([], 1, "", f"base copy failed: {type(exc).__name__}: {exc}\n")
    if spec["method"] != "base":
        gen = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": f"{source}/scripts"})
    if not gen.returncode and spec["method"] != "remesh" and spec["iters"] != BASE_ITERS[0]:
        _set_iters(case, spec["iters"])
    return gen


def topology(case: Path) -> dict:
    return {f: sha(case / "constant/polyMesh" / f) for f in TOPOLOGY_FILES}


def run_case(spec: dict, source: Path, deadline: float) -> dict:
    cid, solve = spec["id"], spec.get("solve", True)
    case = OUTPUT / "work" / cid
    keep = OUTPUT / "cases" / cid
    keep.mkdir(parents=True)
    rec = {"id": cid, "method": spec["method"], "variant": spec["variant"], "model": "sa-wf", "h_over_c": spec["h"], "mesh": spec["mesh"], "shape_mode": spec["mode"],
           "amp": spec["amp"], "delta_alpha_deg": spec["amp"] if spec["mode"] == "incidence" else 0.0, "iterations_requested": spec["iters"], "stages": [],
           "status": "COMPLETED", "mode": MODE}
    t0 = time.monotonic()
    gen = generate(spec, source, case)
    (keep / "log.t20c_case").write_text(gen.stdout + gen.stderr)
    rec["generator_wall_s"] = time.monotonic() - t0
    if gen.returncode:
        rec["status"] = "GENERATOR_FAILED"
    for name, command in (("gmshToFoam", "gmshToFoam mesh.msh"), ("checkMesh", "checkMesh -allGeometry -allTopology"), ("simpleFoam", "simpleFoam")):
        if rec["status"] != "COMPLETED" or (name == "simpleFoam" and not solve):
            break
        if name == "simpleFoam":
            rec["pre_solver_wall_s"] = time.monotonic() - t0
        timeout = min(CASE_CAP_S, deadline - time.monotonic()) if name == "simpleFoam" else 900
        if name == "simpleFoam" and timeout < CASE_CAP_S:
            rec["deadline_limited"] = True
        if name == "checkMesh":  # gmshToFoam writes every patch as `patch`: front/back must be empty and airfoil/ground wall
            b = case / "constant/polyMesh/boundary"
            b.write_text(t20_foam.fix_boundary(b.read_text()))
            if spec["method"] == "morph":   # registration section 4: only `points` may differ from the base's polyMesh
                rec["topology"] = topology(case)
                rec["base_topology"] = BASE_TOPOLOGY.get(base_dir(spec["mesh"], spec["h"], base_da(spec)).name)
                if rec["topology"] != rec["base_topology"]:
                    rec["status"] = "TOPOLOGY_CHANGED" if rec["base_topology"] else "BASE_TOPOLOGY_MISSING"
                    break
        stage = timed_run(name, command, case, timeout)
        rec["stages"].append(stage)
        if name == "checkMesh":
            rec["check_mesh_returncode"] = stage["returncode"]
            cm = parse_check_mesh((case / "log.checkMesh").read_text(errors="replace")) if (case / "log.checkMesh").is_file() else {}
            if solve and (not cm.get("mesh_ok") or cm.get("failed_check_counts")):
                rec["status"] = "checkMesh_FAILED"   # mechanical either way; not solving keeps the kernel budget for the other cases
        elif stage["returncode"] or stage["timed_out"]:
            rec["status"] = f"{name}_{'TIMEOUT' if stage['timed_out'] else 'FAILED'}"
    text = lambda n: (case / f"log.{n}").read_text(errors="replace") if (case / f"log.{n}").is_file() else ""
    dats = lambda: sorted(case.glob("postProcessing/forceCoeffs/*/coefficient.dat"), key=lambda d: float(d.parent.name))
    if solve and rec["status"] == "COMPLETED" and (spec["iters"] >= ITERS or spec.get("force_continuation")):   # registered one-time continuation if the Cl plateau fails
        try:
            plateau = force_summary(read_coefficients(dats()))["cl_plateau"] and not spec.get("force_continuation")
        except Exception:
            plateau = True   # unreadable history: left to the parser below, not continued
        if not plateau:
            _continue(case, spec["cont_iters"])
            rec["deadline_limited"] = rec.get("deadline_limited") or deadline - time.monotonic() < CASE_CAP_S - rec["stages"][-1]["wall_s"]
            stage = timed_run("simpleFoam_cont", "simpleFoam", case, min(CASE_CAP_S - rec["stages"][-1]["wall_s"], deadline - time.monotonic()))
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
        if "continued_to" in rec:
            rec["solver_cont"] = parse_solver(text("simpleFoam_cont"))
        files = dats()
        if files:   # a continued case is judged on the continuation, iterations to plateau on the whole history
            rec["forces"] = force_summary(read_coefficients(files[-1:]), read_coefficients(files))
        last = rec.get("solver_cont", rec["solver"])
        rec["residual_converged"] = bool(last and last["converged_in"] is not None)
        if rec["status"].endswith("_TIMEOUT") and "forces" in rec:
            rec["status"] = "SOLVER_TIMEOUT_PARTIAL"
        if rec["status"] == "COMPLETED" and (blown_up(rec.get("forces")) or (last or {}).get("nan_in_log")):
            rec["status"] = "SOLVER_DIVERGED"
    except Exception as exc:
        rec["parse_error"] = f"{type(exc).__name__}: {exc}"
        rec["status"] = rec["status"] if rec["status"] != "COMPLETED" else "PARSE_FAILED"
    if rec["status"] == "SOLVER_DIVERGED" or rec["status"].endswith("_FAILED"):
        log = text("simpleFoam_cont") or text("simpleFoam") or (gen.stdout + gen.stderr)
        rec["failure_log_tail"] = _keep_text("\n".join(log.splitlines()[-40:])).splitlines()
    if rec.get("deadline_limited") and ("TIMEOUT" in rec["status"] or rec["status"] == "SOLVER_TIMEOUT_PARTIAL"):
        rec["status"] = "DEADLINE_LIMITED"   # cut by the kernel budget, not by the per-case cap: an infrastructure loss (registration section 6)
    if not solve and "check_mesh" in rec:
        rec["status"] = "MESH_OK" if rec["status"] == "COMPLETED" and rec["check_mesh"]["mesh_ok"] and not rec["check_mesh"]["failed_check_counts"] else (
            "MESH_FAILED" if rec["status"] == "COMPLETED" else rec["status"])
    if (case / "case_manifest.json").is_file():
        man = json.loads((case / "case_manifest.json").read_text())
        rec["mesh_cells_3d"], rec["mesh_proxy_failures"] = man["mesh_stats"]["cells_3d"], man["mesh_quality_failures"]
        rec["h_m"], rec["x_lowest_m"], rec["mesh_msh_sha256"] = man["h_m"], man["mesh_stats"]["x_lowest_m"], man["mesh_msh_sha256"]
        rec["n_layers"], rec["bl_thickness_m"] = man["mesh_stats"]["n_layers"], man["mesh_stats"]["bl_thickness_m"]
        for k in ("morph", "shape"):
            if k in man:
                rec[k] = man[k]
    if MODE == "smoke" and "forces" in rec:   # registration section 8: no force or coefficient value leaves the smoke kernel
        rec["forces"] = {"rows": rec["forces"]["rows"], "values": "suppressed (smoke), including the force-derived plateau flag"}
    if case.exists():
        logs = [*case.glob("log.*")]
        kept = logs + ([] if MODE == "smoke" else [*case.glob("postProcessing/*/*/*.dat"), case / "mesh.msh"]) + [case / "case_manifest.json"]
        for p in kept:
            if p.is_file() and not (p.name == "mesh.msh" and not solve):
                prefix = "" if p.parent.name in ("0", case.name) else f"t{p.parent.name}_"
                data = p.read_bytes() if not p.name.startswith("log.") else _keep_text(p.read_text(errors="replace")).encode()
                with gzip.open(keep / (prefix + p.name + ".gz"), "wb") as dst:
                    dst.write(data)
        for d in ("0", "system", "constant"):
            if (case / d).is_dir():
                shutil.copytree(case / d, keep / "case_dict" / d, ignore=shutil.ignore_patterns("polyMesh"))
        shutil.rmtree(case, ignore_errors=True)
    write_json(keep / "case_result.json", rec)
    return rec


def case_id(method, h, mesh, mode, amp, variant="") -> str:
    """remesh/base incidence: the T2-0b id (sa-wf_h{h}_{mesh}_da{..}); remeshed shape: ..._{mode}{..}mm; morph: ..._morph-da{..} (morphB2-, morphLin- for the
    variants) or ..._morph-{mode}{..}mm."""
    a = "0" if amp == 0 else format(amp, "+g")
    tail = f"da{a}" if mode == "incidence" else f"{mode}{a}mm"
    if method in ("remesh", "base"):
        return f"sa-wf_h{h}_{mesh}_{tail}"
    return f"sa-wf_h{h}_{mesh}_morph{ {'': '', 'B2': 'B2', 'lin': 'Lin'}[variant]}-{tail}"


def make_specs(items, iters=ITERS, cont_iters=CONT_ITERS, solve=True, force_continuation=False, suffix=""):
    return [{"id": case_id(*c) + ("" if solve else "_mesh") + suffix, "method": c[0], "h": c[1], "mesh": c[2], "mode": c[3], "amp": c[4], "variant": c[5],
             "iters": iters, "solve": solve, "cont_iters": cont_iters, "force_continuation": force_continuation} for c in items]


BASE_ITERS, BASE_TOPOLOGY = [ITERS], {}


def make_bases(source: Path, bases, iters: int) -> list[dict]:
    """The kernel's base meshes, generated once (concurrently) by the pinned generator, and their polyMesh topology hashes (gmshToFoam and the patch fix on a
    scratch copy); morphs and baseline solves read them. A failed base fails its cases (their generator or topology check fails)."""
    BASE_ITERS[0] = iters

    def one(item):
        mesh, h, da = item
        d = base_dir(mesh, h, da)
        d.parent.mkdir(parents=True, exist_ok=True)
        t = time.monotonic()
        gen = subprocess.run([sys.executable, str(source / "scripts/t20c_case.py"), "--out", str(d), "--h-over-c", str(h), "--mesh", mesh, "--iters", str(iters),
                              "--delta-alpha-deg", str(da)], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": f"{source}/scripts"})
        rec = {"base": d.name, "mesh": mesh, "h_over_c": h, "delta_alpha_deg": da, "returncode": gen.returncode, "wall_s": time.monotonic() - t,
               "log_tail": (gen.stdout + gen.stderr)[-2000:]}
        if not gen.returncode:
            man = json.loads((d / "case_manifest.json").read_text())
            rec.update(mesh_msh_sha256=man["mesh_msh_sha256"], cells_3d=man["mesh_stats"]["cells_3d"], bl_thickness_m=man["mesh_stats"]["bl_thickness_m"],
                       mesh_quality_failures=man["mesh_quality_failures"])
            scratch = d.parent / f"{d.name}_topology"
            shutil.copytree(d, scratch)
            stage = timed_run("gmshToFoam", "gmshToFoam mesh.msh", scratch, 900)
            if not stage["returncode"]:
                b = scratch / "constant/polyMesh/boundary"
                b.write_text(t20_foam.fix_boundary(b.read_text()))
                rec["topology"] = BASE_TOPOLOGY[d.name] = topology(scratch)
            shutil.rmtree(scratch)
        return rec
    with ThreadPoolExecutor(WORKERS) as pool:
        out = list(pool.map(one, bases))
    write_json(OUTPUT / "bases.json", out)
    return out


def infrastructure_ok(r: dict) -> bool:
    s = r.get("solver", {})
    return r["status"] == "COMPLETED" and "forces" in r and s.get("iterations", 0) >= SMOKE_ITERS - 1 and not s.get("nan_in_log") and r["forces"]["last_iteration"] >= SMOKE_ITERS - 1


def main() -> None:
    global SOURCE, t20_foam
    require(SOURCE_COMMIT != "PIN_SOURCE_COMMIT" and MODE in BUDGET_S, "runner has not been rendered by scripts/build_t20c_kernel.py")
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
    import t20_foam
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
                "qualification_flags": "none (T2-0c measurement; the verdict is computed by scripts/analyze_t20c.py)"}

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
        make_bases(SOURCE, BASES["smoke"], SMOKE_ITERS // 2)
        unique = {}
        for sp in make_specs(M_CASES + S_CASES + R_CASES, solve=False):   # one per id: the base copies win over the identical remeshed 0-deg geometry
            unique.setdefault(sp["id"], sp)
        execute(list(unique.values()), results)
        execute(make_specs(DEV_SMOKE, SMOKE_ITERS // 2, cont_iters=SMOKE_ITERS, force_continuation=True, suffix="_smoke"), results)
    else:
        smoke = execute(make_specs(GATE_SMOKE, SMOKE_ITERS, suffix="_smoke"), [])
        write_json(OUTPUT / "smoke.json", smoke)
        bad = [r for r in smoke if not infrastructure_ok(r)]
        require(not bad, f"smoke stage failed (infrastructure): {[(r['id'], r['status']) for r in bad]}")
        make_bases(SOURCE, BASES[MODE], ITERS)
        execute(make_specs(CASES[MODE]), results)
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
        err = OUTPUT / "ERROR.json" if OUTPUT.exists() else OUTPUT.parent / "t20c_startup_ERROR.json"
        err.parent.mkdir(parents=True, exist_ok=True)
        write_json(err, {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
