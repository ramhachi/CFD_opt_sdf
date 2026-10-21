#!/usr/bin/env python3
"""T2-0d kernel (#57, registration docs/t20d_registration_2026_10_21.md; fork of infra/kaggle/kernel_t20c_cpu/runner.py): 2D Tyrrell 026 ground-effect
cases on Kaggle CPU, OpenFOAM v2512, SA wall functions; every geometry runs the T2-0c steady case (S0) and then stage-2 runs on copies of it: time-averaged
URANS (U, dt 1e-5 s), its time-step control (Udt2, dt 2e-5 s) and a relaxed steady control (S1) (scripts/t20d_case.py).

Template: scripts/build_t20d_kernel.py fills PIN_SOURCE_COMMIT, PIN_MODE and PIN_PINS and verifies the pins.
Order (cheap failures first): environment -> pinned source -> gmsh install + one meshing probe -> OpenFOAM install (hash-locked, as T2-0b/T2-0c)
-> infrastructure smoke -> bases generated once -> phase 1: every S0 (4 concurrent) -> phase 2: every stage-2 run (4 concurrent, longest first).
MODE "xp1", "xp2", "xo1", "xo2", "f1", "f2": the registered kernels (registration section 5). MODE "smoke": development smoke before the code freeze (mesh-only pass over
every registered geometry of the four kernels, each solver path shortened; coefficient files, force values and force log lines are removed before output).
A morphed geometry must keep its base's polyMesh topology (TOPOLOGY_CHANGED / BASE_TOPOLOGY_MISSING), a geometry failing checkMesh is not solved
(checkMesh_FAILED); all mechanical. Measurement only: no statistic or verdict here (scripts/analyze_t20d.py). Kernel-level failures write ERROR.json and raise;
DONE last. The case files leave as one uncompressed tar, cases.tar (Kaggle's output API rate-limits per-file downloads); artifact_manifest.json, written before
packing, lists every file inside it with its SHA-256.
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
import tarfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

SOURCE_COMMIT = "PIN_SOURCE_COMMIT"
MODE = "PIN_MODE"                          # "smoke" | "xp1" | "xp2" | "xo1" | "xo2" | "f1" | "f2", rendered by scripts/build_t20d_kernel.py
PINS = PIN_PINS  # {repo path: sha256}, rendered
ONLY = PIN_ONLY  # None, or (resubmission, registration section 8) the geometry ids of the sets with a lost run, rendered
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
LOCKS = {"jammy": "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json", "noble": "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json"}  # the two hash-pinned OpenCFD v2512 locks registered by XFID X2/X3; chosen by the observed Ubuntu codename
GMSH_PIN = "gmsh==4.15.2"
FOAM_VERSION = "OpenFOAM-v2512"
OUTPUT = Path(os.environ.get("T20D_OUTPUT", "/kaggle/working/t20d"))
BASHRC = os.environ.get("T20D_BASHRC", "/usr/lib/openfoam/openfoam2512/etc/bashrc")
WORKERS, RESERVE_S = 4, 600                            # concurrent independent runs (4 vCPU)
BUDGET_S = {"smoke": 3 * 3600, **{m: 11 * 3600 for m in ("xp1", "xp2", "xo1", "xo2", "f1", "f2")}}   # kernel budget per mode (Kaggle limit 12 h)
RUN_CAP_S = 5.5 * 3600                                 # per-run solver cap
S0_ITERS = 5000                                        # registered S0 (T2-0c's steady case, no continuation)
B2_DA = 0.5                                            # second base B' (+0.5 deg)
INC, A6 = "incidence", (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0)
U, UDT2, UDT05, S1, US1 = "U", "Udt2", "Udt05", "S1", "US1"
# registered geometries per kernel (registration section 5): ((method, h/c, mesh, mode, amp, variant), stage-2 kinds); method remesh | base | morph;
# amp in deg (incidence) or mm (camber, flap); variant "" (the kernel's 0-deg base at that h/c) or "B2" (from B'); kinds () = S0 only
G = lambda method, h, mesh, amp=0.0, mode=INC, variant="": (method, h, mesh, mode, amp, variant)
XP1 = ([(G("base", 0.134, "xfine30"), (U, UDT2, UDT05, S1, US1))]
       + [(G("morph", 0.134, "xfine30", a), (U, UDT2, S1) if abs(a) == 1 else (U,)) for a in A6])
XP2 = ([(G("morph", 0.134, "xfine30", a, variant="B2"), (U,)) for a in (-1.0, -0.25, 0.25, 1.0)]
       + [(G("morph", 0.134, "xfine30", a, mode=m), (U,)) for m in ("camber", "flap") for a in (-0.25, 0.25)])
XO1 = ([(G("remesh", 0.224, "xfine30"), (U, UDT2, S1))] + [(G("remesh", 0.224, "xfine30", a), (U,)) for a in (-1.0, 1.0)]
       + [(G("remesh", 0.09, "xfine30"), (U, UDT2, UDT05, S1, US1))] + [(G("remesh", 0.09, "xfine30", a), (U, UDT2, S1)) for a in (-1.0, 1.0)])
XO2 = ([(G("remesh", h, "xfine30"), (U,)) for h in (0.671, 0.448, 0.313)] + [(G("base", 0.179, "xfine30"), (U,))]
       + [(G("morph", 0.179, "xfine30", a), ()) for a in A6] + [(G("remesh", 0.134, "xfine30", a), (U,)) for a in (-1.0, 1.0)])
F1 = ([(G("remesh", h, "fine30"), (U,)) for h in (0.671, 0.448, 0.313, 0.224)] + [(G("base", 0.179, "fine30"), (U,))]
      + [(G("morph", 0.179, "fine30", a), ()) for a in A6] + [(G("remesh", 0.134, "fine30"), (U,)), (G("remesh", 0.09, "fine30"), (U, S1))]
      + [(G("remesh", h, "fine30", a), (U,)) for h in (0.224, 0.134) for a in (-1.0, 1.0)]
      + [(G("remesh", 0.09, "fine30", -1.0), (U,)), (G("remesh", 0.09, "fine30", 1.0), (U, UDT2, S1))])
F2 = ([(G("base", 0.134, "fine30"), (U,))] + [(G("morph", 0.134, "fine30", a), (U,)) for a in A6]
      + [(G("morph", 0.134, "fine30", a, variant="B2"), (U,)) for a in (-1.0, -0.25, 0.25, 1.0)])
GEOMETRIES = {"xp1": XP1, "xp2": XP2, "xo1": XO1, "xo2": XO2, "f1": F1, "f2": F2}
BASES = {"xp1": [("xfine30", 0.134, 0.0)], "xp2": [("xfine30", 0.134, 0.0), ("xfine30", 0.134, B2_DA)], "xo1": [], "xo2": [("xfine30", 0.179, 0.0)],
         "f1": [("fine30", 0.179, 0.0)], "f2": [("fine30", 0.134, 0.0), ("fine30", 0.134, B2_DA)]}
GATE_SMOKE = G("remesh", 0.224, "coa30")
SMOKE_ITERS = 200
# development smoke (MODE "smoke", registration section 8): (geometry, S0 iterations, {kind: end}); end = end time [s] (URANS kinds) or end iteration (S1)
DEV_SMOKE = [(G("remesh", 0.09, "xfine30"), 1000, {U: 3000e-5, UDT2: 1500 * 2e-5, UDT05: 1000 * 5e-6, S1: 1200, US1: 500e-5}),
             (G("morph", 0.134, "xfine30", 1.0), 1000, {U: 3000e-5}), (G("morph", 0.134, "xfine30", -0.25, variant="B2"), 100, {U: 200e-5}),
             (G("morph", 0.134, "xfine30", 0.25, mode="camber"), 100, {U: 200e-5}), (G("remesh", 0.09, "fine30", 1.0), 100, {U: 200e-5, S1: 300})]
EXPECTED_COST = {"xfine30": {U: 2.35, UDT2: 1.1, UDT05: 3.4, S1: 0.7, US1: 2.35}, "fine30": {U: 1.2, UDT2: 0.55, UDT05: 1.7, S1: 0.35, US1: 1.2}}   # h, ordering only
TOPOLOGY_FILES = ("faces", "owner", "neighbour", "boundary")
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






# ---- one geometry (S0) and one stage-2 run -------------------------------------------

FORCE_LINE = re.compile(r"\b(C[dlmsy]\w*|\w*[Ff]orces?|[Mm]oments?|Total|Pressure|Viscous|Internal|Coefficients?)\b|^\s*\w+\s*:\s*" + NUM + r"\s*$")   # forces/forceCoeffs/objective lines (T2-0c)
LOG_TAIL = 200                                         # lines of a stage-2 solver log kept uncompressed in the record directory


def _keep_text(text: str) -> str:
    """Smoke mode: drop every log line that could carry a force or coefficient value."""
    return "\n".join(l for l in text.splitlines() if not FORCE_LINE.search(l)) if MODE == "smoke" else text


def parse_yplus(text: str) -> dict:
    """`simpleFoam -postProcess -func yPlus` log: per patch min/max/average (the last occurrence per patch)."""
    out = {}
    for patch, lo, hi, avg in re.findall(rf"patch (\w+) y\+ : min = ({NUM}), max = ({NUM}), average = ({NUM})", text):
        out[patch] = {"min": float(lo), "max": float(hi), "average": float(avg)}
    return out


def parse_courant(text: str) -> dict:
    """pimpleFoam: largest and last 'Courant Number mean: .. max: ..' values."""
    m = re.findall(r"^Courant Number mean: (" + NUM + ") max: (" + NUM + ")", text, re.M)
    return {"max": max(float(x) for _, x in m), "last_mean": float(m[-1][0]), "last_max": float(m[-1][1])} if m else None


def _set_iters(case: Path, n: int) -> None:
    """endTime and writeInterval = n (a copied base or a morph inherits the base's registered 5000)."""
    cd = case / "system/controlDict"
    text = re.sub(r"^endTime .*;$", f"endTime {n};", cd.read_text(), count=1, flags=re.M)
    cd.write_text(re.sub(r"^writeInterval .*;$", f"writeInterval {n};", text, count=1, flags=re.M))


def base_dir(mesh: str, h: float, da: float = 0.0) -> Path:
    return OUTPUT / "work" / "base" / f"{mesh}_h{h}_da{'0' if da == 0 else format(da, '+g')}"


def case_id(method, h, mesh, mode, amp, variant="") -> str:
    """T2-0c ids: remeshed/base sa-wf_h{h}_{mesh}_da{..}; morph ..._morph-da{..}, ..._morphB2-da{..} or ..._morph-{mode}{..}mm."""
    a = "0" if amp == 0 else format(amp, "+g")
    tail = f"da{a}" if mode == INC else f"{mode}{a}mm"
    if method in ("remesh", "base"):
        return f"sa-wf_h{h}_{mesh}_{tail}"
    return f"sa-wf_h{h}_{mesh}_morph{ {'': '', 'B2': 'B2'}[variant]}-{tail}"


def generate(g: dict, source: Path, case: Path) -> subprocess.CompletedProcess:
    """remesh: the pinned generator through scripts/t20c_case.py; base: a copy of the kernel's 0-deg base; morph: scripts/t20c_case.py --base."""
    py = [sys.executable, str(source / "scripts/t20c_case.py"), "--out", str(case)]
    if g["method"] == "remesh":
        return subprocess.run(py + ["--h-over-c", str(g["h"]), "--mesh", g["mesh"], "--iters", str(g["iters"]), "--delta-alpha-deg", str(g["amp"])],
                              capture_output=True, text=True, env={**os.environ, "PYTHONPATH": f"{source}/scripts"})
    if g["method"] == "morph":
        gen = subprocess.run(py + ["--base", str(base_dir(g["mesh"], g["h"], B2_DA if g["variant"] == "B2" else 0.0)), "--mode", g["mode"], "--amp", str(g["amp"])],
                             capture_output=True, text=True, env={**os.environ, "PYTHONPATH": f"{source}/scripts"})
    else:   # a missing base (its generation failed) is a generator failure of this geometry, not an infrastructure loss
        try:
            shutil.copytree(base_dir(g["mesh"], g["h"]), case)
            gen = subprocess.CompletedProcess([], 0, f"copied {base_dir(g['mesh'], g['h'])}\n", "")
        except OSError as exc:
            gen = subprocess.CompletedProcess([], 1, "", f"base copy failed: {type(exc).__name__}: {exc}\n")
    if not gen.returncode:   # a copied base or a morph inherits the base's iteration count
        _set_iters(case, g["iters"])
    return gen


def topology(case: Path) -> dict:
    return {f: sha(case / "constant/polyMesh" / f) for f in TOPOLOGY_FILES}


def _gz(src: Path, dst: Path, text: bool) -> None:
    data = _keep_text(src.read_text(errors="replace")).encode() if text else src.read_bytes()
    with gzip.open(dst, "wb") as out:
        out.write(data)


def _keep(case: Path, keep: Path, coefficient: bool) -> None:
    """Logs (gzipped; smoke: force lines removed), the coefficient file (not in smoke), the manifest and the dictionaries of a run."""
    keep.mkdir(parents=True, exist_ok=True)
    for p in case.glob("log.*"):
        _gz(p, keep / f"{p.name}.gz", True)
        lines = _keep_text(p.read_text(errors="replace")).splitlines()
        (keep / f"{p.name}.tail").write_text("\n".join(lines[-LOG_TAIL:]) + "\n")
    if coefficient and MODE != "smoke":
        for i, p in enumerate(sorted(case.glob("postProcessing/forceCoeffs/*/coefficient.dat"), key=lambda d: float(d.parent.name))):
            _gz(p, keep / f"coefficient{'' if i == 0 else i}.dat.gz", False)
    if (case / "case_manifest.json").is_file():
        shutil.copy2(case / "case_manifest.json", keep / "case_manifest.json")
    for d in ("system", "constant"):
        if (case / d).is_dir():
            shutil.copytree(case / d, keep / "case_dict" / d, ignore=shutil.ignore_patterns("polyMesh"), dirs_exist_ok=True)


def _solver_status(rec: dict, name: str, stage: dict, log: str) -> None:
    rec["stages"].append(stage)
    s = parse_solver(log)
    rec["solver"] = s
    if stage["timed_out"]:
        rec["status"] = "DEADLINE_LIMITED" if rec.get("deadline_limited") else f"{name}_TIMEOUT"
    elif stage["returncode"] or s["foam_fatal"] or s["sigfpe"]:
        rec["status"] = f"{name}_FAILED"
    elif s["nan_in_log"]:
        rec["status"] = "SOLVER_DIVERGED"


def run_s0(g: dict, source: Path, deadline: float) -> dict:
    """Phase 1: generate the geometry, gmshToFoam, boundary fix, topology check (morph), checkMesh, S0 (simpleFoam, S0 iterations), yPlus.
    The work directory is kept for phase 2."""
    case = OUTPUT / "work" / g["id"]
    rec = {"id": f"{g['id']}__S0", "geometry": g["id"], "kind": "S0", "method": g["method"], "variant": g["variant"], "h_over_c": g["h"], "mesh": g["mesh"],
           "shape_mode": g["mode"], "amp": g["amp"], "delta_alpha_deg": g["amp"] if g["mode"] == INC else 0.0, "iterations_requested": g["iters"],
           "stages": [], "status": "COMPLETED", "mode": MODE}
    t0 = time.monotonic()
    gen = generate(g, source, case)
    rec["generator_wall_s"] = time.monotonic() - t0
    rec["generator_log_tail"] = (gen.stdout + gen.stderr)[-2000:]
    if gen.returncode:
        rec["status"] = "GENERATOR_FAILED"
    for name, command in (("gmshToFoam", "gmshToFoam mesh.msh"), ("checkMesh", "checkMesh -allGeometry -allTopology")):
        if rec["status"] != "COMPLETED":
            break
        if name == "checkMesh":   # gmshToFoam writes every patch as `patch`: front/back must be empty and airfoil/ground wall
            b = case / "constant/polyMesh/boundary"
            b.write_text(t20_foam.fix_boundary(b.read_text()))
            if g["method"] == "morph":   # T2-0c section 4: only `points` may differ from the base's polyMesh
                rec["topology"] = topology(case)
                rec["base_topology"] = BASE_TOPOLOGY.get(base_dir(g["mesh"], g["h"], B2_DA if g["variant"] == "B2" else 0.0).name)
                if rec["topology"] != rec["base_topology"]:
                    rec["status"] = "TOPOLOGY_CHANGED" if rec["base_topology"] else "BASE_TOPOLOGY_MISSING"
                    break
        stage = timed_run(name, command, case, 900)
        rec["stages"].append(stage)
        if stage["returncode"] or stage["timed_out"]:
            rec["status"] = f"{name}_{'TIMEOUT' if stage['timed_out'] else 'FAILED'}"
    text = lambda n: (case / f"log.{n}").read_text(errors="replace") if (case / f"log.{n}").is_file() else ""
    if rec["status"] == "COMPLETED":
        cm = rec["check_mesh"] = parse_check_mesh(text("checkMesh"))
        if not cm["mesh_ok"] or cm["failed_check_counts"]:
            rec["status"] = "checkMesh_FAILED" if g["solve"] else "MESH_FAILED"
    rec["pre_solver_wall_s"] = time.monotonic() - t0
    if rec["status"] == "COMPLETED" and g["solve"]:
        timeout = min(RUN_CAP_S, deadline - time.monotonic())
        rec["deadline_limited"] = timeout < RUN_CAP_S
        _solver_status(rec, "simpleFoam", timed_run("simpleFoam", "simpleFoam", case, timeout), text("simpleFoam"))
        if rec["status"] == "COMPLETED":
            y = timed_run("yPlus", "simpleFoam -postProcess -func yPlus -latestTime", case, 600)
            rec["yplus"], rec["yplus_returncode"] = parse_yplus(text("yPlus")), y["returncode"]
    elif rec["status"] == "COMPLETED":
        rec["status"] = "MESH_OK"
    if (case / "case_manifest.json").is_file():
        man = json.loads((case / "case_manifest.json").read_text())
        rec["mesh_cells_3d"], rec["mesh_proxy_failures"] = man["mesh_stats"]["cells_3d"], man["mesh_quality_failures"]
        rec["h_m"], rec["x_lowest_m"], rec["mesh_msh_sha256"] = man["h_m"], man["mesh_stats"]["x_lowest_m"], man["mesh_msh_sha256"]
        rec["n_layers"], rec["bl_thickness_m"] = man["mesh_stats"]["n_layers"], man["mesh_stats"]["bl_thickness_m"]
        if "morph" in man:
            rec["morph"] = man["morph"]
    if rec["status"] in ("SOLVER_DIVERGED",) or rec["status"].endswith("_FAILED"):
        rec["failure_log_tail"] = _keep_text("\n".join((text("simpleFoam") or rec["generator_log_tail"]).splitlines()[-40:])).splitlines()
    rec["total_wall_s"] = time.monotonic() - t0
    keep = OUTPUT / "cases" / rec["id"]
    keep.mkdir(parents=True, exist_ok=True)
    if case.exists():
        _keep(case, keep, coefficient=True)
    write_json(keep / "case_result.json", rec)
    return rec


def run_stage2(g: dict, kind: str, src: dict, source: Path, deadline: float) -> dict:
    """Phase 2: copy the solved source run (S0; the S1 run for US1) with scripts/t20d_case.py and run pimpleFoam (U, Udt2, Udt05, US1) or the relaxed simpleFoam
    continuation (S1). The S1 work directory is kept for a US1 of the same geometry; every other stage-2 work directory is removed after its record."""
    rec = {"id": f"{g['id']}__{kind}", "geometry": g["id"], "kind": kind, "method": g["method"], "variant": g["variant"], "h_over_c": g["h"], "mesh": g["mesh"],
           "shape_mode": g["mode"], "amp": g["amp"], "delta_alpha_deg": g["amp"] if g["mode"] == INC else 0.0, "stages": [], "status": "COMPLETED", "mode": MODE,
           "source_run": src["id"], "source_status": src["status"], "s0_wall_s": g["s0_wall_s"], "pre_solver_wall_s": g["pre_solver_wall_s"],
           "mesh_msh_sha256": g["mesh_msh_sha256"], "mesh_cells_3d": g["mesh_cells_3d"]}
    case = OUTPUT / "work" / rec["id"]
    if src["status"] != "COMPLETED":
        rec["status"] = "SOURCE_NOT_COMPLETED"
        return _finish_stage2(rec, None, False)
    t0 = time.monotonic()
    try:
        src_dir = OUTPUT / "work" / (f"{g['id']}__{S1}" if kind == US1 else g["id"])   # run_s0 works in work/<geometry>, an S1 in work/<geometry>__S1
        rec["stage2"] = t20d_case.stage2_case(src_dir, case, U if kind == US1 else kind, g["ends"].get(kind))
        rec["stage2"]["kind"] = kind
    except Exception as exc:   # a copy or dictionary failure of our pipeline (mechanical)
        rec["status"], rec["error"] = "STAGE2_PREP_FAILED", f"{type(exc).__name__}: {exc}"
        return _finish_stage2(rec, case, False)
    name = "simpleFoam" if kind == S1 else "pimpleFoam"
    timeout = min(RUN_CAP_S, deadline - time.monotonic())
    rec["deadline_limited"] = timeout < RUN_CAP_S
    log = lambda: (case / f"log.{name}").read_text(errors="replace") if (case / f"log.{name}").is_file() else ""
    _solver_status(rec, name, timed_run(name, name, case, timeout), log())
    if kind != S1:
        rec["courant"] = parse_courant(log())
    rec["stage2_wall_s"] = time.monotonic() - t0
    return _finish_stage2(rec, case, kind == S1 and US1 in g["kinds"])


def _finish_stage2(rec: dict, case: Path | None, keep_work: bool) -> dict:
    keep = OUTPUT / "cases" / rec["id"]
    keep.mkdir(parents=True, exist_ok=True)
    if case is not None and case.exists():
        _keep(case, keep, coefficient=True)
        if not keep_work:
            shutil.rmtree(case, ignore_errors=True)
    write_json(keep / "case_result.json", rec)
    return rec


def make_geometries(items, iters=S0_ITERS, solve=True, suffix="", ends=None):
    """items: [(geometry tuple, kinds)] or, with `ends` None and 3-tuples, the development smoke's [(geometry, S0 iterations, {kind: end})]."""
    out = []
    for item in items:
        c, kinds = item[0], item[1]
        n, e = iters, ends or {}
        if len(item) == 3:
            n, e = item[1], item[2]
            kinds = tuple(e)
        cid = case_id(*c) + suffix
        out.append({"id": cid, "method": c[0], "h": c[1], "mesh": c[2], "mode": c[3], "amp": c[4], "variant": c[5], "iters": n, "solve": solve,
                    "kinds": kinds, "ends": e})
    return out


BASE_TOPOLOGY = {}


def make_bases(source: Path, bases, iters: int) -> list[dict]:
    """The kernel's base meshes, generated once (concurrently) by the pinned generator, and their polyMesh topology hashes (gmshToFoam and the patch fix on a
    scratch copy); morphs and copied bases read them (T2-0c)."""
    def one(item):
        mesh, h, da = item
        d = base_dir(mesh, h, da)
        d.parent.mkdir(parents=True, exist_ok=True)
        t = time.monotonic()
        gen = subprocess.run([sys.executable, str(SOURCE / "scripts/t20c_case.py"), "--out", str(d), "--h-over-c", str(h), "--mesh", mesh, "--iters", str(iters),
                              "--delta-alpha-deg", str(da)], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": f"{SOURCE}/scripts"})
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


def pack_cases() -> str:
    """cases/ -> cases.tar (sorted members, arcname cases/...), then cases/ removed; returns the tar's SHA-256."""
    tar = OUTPUT / "cases.tar"
    with tarfile.open(tar, "w", format=tarfile.PAX_FORMAT) as t:
        t.add(OUTPUT / "cases", arcname="cases")
    shutil.rmtree(OUTPUT / "cases")
    return sha(tar)


def main() -> None:
    global SOURCE, t20_foam, t20d_case
    require(SOURCE_COMMIT != "PIN_SOURCE_COMMIT" and MODE in BUDGET_S, "runner has not been rendered by scripts/build_t20d_kernel.py")
    require(not OUTPUT.exists(), f"refusing to overwrite prior output: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "work").mkdir()
    (OUTPUT / "cases").mkdir()
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
    import t20d_case
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
                "elapsed_s": time.monotonic() - started, "workers": WORKERS, "cpu_model": cpu_model, "runs": results,
                "qualification_flags": "none (T2-0d measurement; the verdict is computed by scripts/analyze_t20d.py)"}

    def execute(jobs):
        """jobs: [(id, callable)] run 4 at a time in list order; each callable gets the deadline. A job that would start with less than 15 min left is
        NOT_RUN_TIME_BUDGET."""
        def work(job):
            jid, fn = job
            try:
                r = fn(deadline) if deadline - time.monotonic() > 900 else {"id": jid, "status": "NOT_RUN_TIME_BUDGET"}
            except Exception as exc:
                r = {"id": jid, "status": "RUNNER_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}
            with lock_:
                results.append(r)
                write_json(OUTPUT / "result.json", summary())   # rewritten as each run ends: survives a kernel kill
            return r
        with ThreadPoolExecutor(WORKERS) as pool:
            return list(pool.map(work, jobs))

    def phases(geoms):
        """Phase 1: every S0. Phase 2: the stage-2 runs; S1 runs that feed a US1 first, then longest first; a US1 waits for its S1 (an Event), so a worker
        never idles on it in practice (the S1 runs are at the head of the queue)."""
        s0 = dict(zip([g["id"] for g in geoms], execute([(f"{g['id']}__S0", lambda dl, g=g: run_s0(g, SOURCE, dl)) for g in geoms])))
        for g in geoms:
            r = s0[g["id"]]
            g.update(s0_wall_s=sum(s["wall_s"] for s in r.get("stages", []) if s["stage"] == "simpleFoam"), pre_solver_wall_s=r.get("pre_solver_wall_s"),
                     mesh_msh_sha256=r.get("mesh_msh_sha256"), mesh_cells_3d=r.get("mesh_cells_3d"))
        s1_done, s1_rec = {g["id"]: threading.Event() for g in geoms}, {}

        def stage2(g, k, dl):
            if k == US1:
                if not s1_done[g["id"]].wait(timeout=max(0.0, dl - time.monotonic())):
                    return {"id": f"{g['id']}__{k}", "status": "NOT_RUN_TIME_BUDGET"}
                return run_stage2(g, k, s1_rec[g["id"]], SOURCE, dl)
            r = run_stage2(g, k, s0[g["id"]], SOURCE, dl)
            if k == S1:
                s1_rec[g["id"]] = r
                s1_done[g["id"]].set()
            return r

        def stage2_job(g, k):
            def fn(dl):
                try:
                    return stage2(g, k, dl)
                finally:
                    if k == S1 and not s1_done[g["id"]].is_set():   # a failed or skipped S1 still releases its US1 (which then reports the source status)
                        s1_rec.setdefault(g["id"], {"id": f"{g['id']}__S1", "status": "NOT_RUN"})
                        s1_done[g["id"]].set()
            return (f"{g['id']}__{k}", fn)

        runs = [(g, k) for g in geoms for k in g["kinds"]]
        first = [gk for gk in runs if gk[1] == S1 and US1 in gk[0]["kinds"]]
        rest = sorted((gk for gk in runs if gk not in first and gk[1] != US1), key=lambda gk: -EXPECTED_COST[gk[0]["mesh"]][gk[1]])
        last = [gk for gk in runs if gk[1] == US1]
        execute([stage2_job(g, k) for g, k in first + rest + last])
        # a S1 work directory kept for its US1, and every S0 work directory, are removed with work/ at the end

    if MODE == "smoke":   # bases of all six kernels once; the mesh-only pass (one per id), then the shortened solver paths
        make_bases(SOURCE, sorted({b for m in GEOMETRIES for b in BASES[m]}), 100)
        unique = {}
        for g in make_geometries([(c, ()) for m in GEOMETRIES for c, _ in GEOMETRIES[m]], 100, solve=False, suffix="_mesh"):
            unique.setdefault(g["id"], g)
        execute([(f"{g['id']}__S0", lambda dl, g=g: run_s0(g, SOURCE, dl)) for g in unique.values()])
        for g in unique.values():
            shutil.rmtree(OUTPUT / "work" / g["id"], ignore_errors=True)
        phases(make_geometries(DEV_SMOKE, suffix="_smoke"))
    else:
        gate = execute([("gate_smoke", lambda dl: run_s0(make_geometries([(GATE_SMOKE, ())], SMOKE_ITERS, suffix="_smoke")[0], SOURCE, dl))])
        write_json(OUTPUT / "smoke.json", gate)
        bad = [r for r in gate if r["status"] != "COMPLETED" or (r.get("solver") or {}).get("iterations", 0) < SMOKE_ITERS - 1
               or not list((OUTPUT / "cases" / r["id"]).glob("coefficient*.dat.gz"))]
        require(not bad, f"smoke stage failed (infrastructure): {[(r['id'], r['status']) for r in bad]}")
        make_bases(SOURCE, BASES[MODE], S0_ITERS)
        phases([g for g in make_geometries(GEOMETRIES[MODE]) if ONLY is None or g["id"] in ONLY])
    shutil.rmtree(OUTPUT / "work", ignore_errors=True)
    manifest = {str(p.relative_to(OUTPUT)): sha(p) for p in sorted(OUTPUT.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    write_json(OUTPUT / "artifact_manifest.json", manifest)
    tar_sha = pack_cases()
    counts = {}
    for c in results:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    (OUTPUT / "DONE").write_text(json.dumps({"status": f"FINISHED_{MODE.upper()}", "status_counts": counts, "artifact_manifest_sha256": sha(OUTPUT / "artifact_manifest.json"),
                                             "cases_tar_sha256": tar_sha}, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        err = OUTPUT / "ERROR.json" if OUTPUT.exists() else OUTPUT.parent / "t20d_startup_ERROR.json"
        err.parent.mkdir(parents=True, exist_ok=True)
        write_json(err, {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
