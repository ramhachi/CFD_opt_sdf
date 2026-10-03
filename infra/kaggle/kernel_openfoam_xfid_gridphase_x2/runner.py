#!/usr/bin/env python3
"""XFID X2 grid-phase probe: rigidly translate the registered baseline Stage V STL
against the fixed OpenFOAM background mesh and record forces, mesh and cost per case.

Measurement only: no PASS/FAIL verdict on the physics, no XFID response. Per-case
failures are recorded and do not abort later cases; kernel-level failures write ERROR.json.
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
from pathlib import Path

import numpy as np

try:
    import psutil
except ImportError:  # peak memory is then reported as null
    psutil = None

CRITERIA_SHA256 = "571d36fb7071415db6f96e6bf0d5e58fc9c5f4980b79df563ae24471940ea673"  # replaced at registration; runner refuses to run otherwise
OUTPUT = Path(os.environ.get("X2_OUTPUT", "/kaggle/working/openfoam_xfid_gridphase_x2"))
INPUT_ROOT = Path(os.environ.get("X2_INPUT", "/kaggle/input"))
OPENFOAM_BASHRC = os.environ.get("X2_BASHRC", "/usr/lib/openfoam/openfoam2512/etc/bashrc")
NUM = r"[-+0-9.eE]+"
STAGES = [
    ("blockMesh", ["blockMesh"]),
    ("surfaceFeatureExtract", ["surfaceFeatureExtract"]),
    ("snappyHexMesh", ["snappyHexMesh", "-overwrite"]),
    ("checkMesh", ["checkMesh", "-allGeometry", "-allTopology"]),
    ("simpleFoam", ["simpleFoam"]),
]
STL_DTYPE = np.dtype([("n", "<f4", 3), ("t", "<f4", (3, 3)), ("a", "<u2")])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


# ---- STL ------------------------------------------------------------------

def read_stl(path: Path) -> np.ndarray:
    blob = Path(path).read_bytes()
    n = int(np.frombuffer(blob[80:84], "<u4")[0])
    require(len(blob) == 84 + 50 * n, "binary STL size does not match its triangle count")
    return np.frombuffer(blob[84:], dtype=STL_DTYPE, count=n)["t"].astype(np.float64)


def stl_bytes(tri64: np.ndarray) -> bytes:
    """Deterministic binary STL: zero header, float32 vertices, unit normals from the float64 triangle."""
    n = np.cross(tri64[:, 1] - tri64[:, 0], tri64[:, 2] - tri64[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
    rec = np.zeros(len(tri64), dtype=STL_DTYPE)
    rec["n"], rec["t"] = n.astype(np.float32), tri64.astype(np.float32)
    return b"\0" * 80 + np.uint32(len(tri64)).tobytes() + rec.tobytes()


def translated_stl(tri64: np.ndarray, axis: str, shift_m: float) -> bytes:
    offset = np.zeros(3)
    offset["xyz".index(axis)] = shift_m
    return stl_bytes(tri64 + offset)


# ---- parsers (tested against retained Round 5 logs) -------------------------

def parse_check_mesh(text: str) -> dict:
    fail_counts = [int(v) for v in re.findall(r"^[ \t]*Failed (\d+) mesh checks?\.[ \t]*$", text, re.M)]
    diagnostics = re.findall(r"^[ \t]*\*\*\*.*$", text, re.M)
    concave = re.search(r"Concave cells \(using face planes\) found, number of cells:\s*(\d+)", text)
    cells = re.search(r"^[ \t]*cells:\s*(\d+)\s*$", text, re.M)
    points = re.search(r"^[ \t]*points:\s*(\d+)\s*$", text, re.M)
    return {
        "cells": int(cells.group(1)) if cells else None,
        "points": int(points.group(1)) if points else None,
        "concave_cells": int(concave.group(1)) if concave else 0,
        "failed_check_counts": fail_counts,
        "diagnostic_lines": [d.strip() for d in diagnostics],
        "only_allowed_concave_failure": bool(
            cells and concave and fail_counts == [1] and len(diagnostics) == 1
            and int(concave.group(1)) / int(cells.group(1)) <= 0.08
        ),
        "mesh_ok": "Mesh OK." in text,
    }


def parse_snappy(text: str) -> dict:
    blocks = [m.end() for m in re.finditer(r"Cells per refinement level:?", text)]
    levels, raw = None, None
    if blocks:
        raw = text[blocks[-1]:].splitlines()[:14]
        pairs = [re.match(r"^\s*(\d+)\s+(\d+)\s*$", line) for line in raw]
        levels = {int(m.group(1)): int(m.group(2)) for m in pairs if m}
    final_cells = re.findall(r"Final mesh\s*:?\s*(?:.*\n)*?\s*cells:\s*(\d+)", text)
    return {"cells_per_refinement_level": levels, "refinement_block_raw": raw,
            "snappy_final_cells": int(final_cells[-1]) if final_cells else None}


def parse_solver(text: str) -> dict:
    residuals = {}
    for field in ("Ux", "Uy", "Uz", "p"):
        m = re.findall(rf"Solving for {field}, Initial residual = {NUM}, Final residual = ({NUM})", text)
        residuals[field] = float(m[-1]) if m else None
    iterations = len(re.findall(r"^Time = \d+", text, re.M))
    conv = re.search(r"SIMPLE solution converged in (\d+) iterations", text)
    return {"iterations": iterations, "converged_in": int(conv.group(1)) if conv else None,
            "final_residuals": residuals}


def force_window(dat_text: str, spec: dict) -> dict:
    header, rows = None, []
    for line in dat_text.splitlines():
        if line.startswith("#"):
            header = line.lstrip("#").split()
        elif line.strip():
            require(header is not None, "force coefficient header is missing")
            rows.append(dict(zip(header, (float(x) for x in line.split()))))
    require(len(rows) >= spec["minimum_rows"], "insufficient force history")
    require(all(math.isfinite(v) for r in rows for v in r.values()), "non-finite force coefficient history")
    count = max(spec["minimum_rows"], math.ceil(len(rows) * spec["tail_fraction"]))
    tail = rows[-count:]
    scale = spec["force_n_per_coefficient"]
    out = {"rows": len(rows), "window_rows": count, "last_iteration": rows[-1].get("Time")}
    for name, key, sign in (("drag_n", "Cd", 1.0), ("downforce_n", "Cl", -1.0)):
        v = np.array([sign * scale * r[key] for r in tail])
        x = np.arange(len(v)) - (len(v) - 1) / 2
        slope = float((x * (v - v.mean())).sum() / (x * x).sum())
        out[name] = {"window_mean": float(v.mean()), "window_std": float(v.std()),
                     "window_linear_drift": abs(slope * (len(v) - 1)),
                     "last": float(sign * scale * rows[-1][key])}
    return out


# ---- process control ----------------------------------------------------------

def timed_run(name: str, command: list[str], cwd: Path, timeout_s: float | None = None) -> dict:
    """Run one OpenFOAM stage; log to log.<name>; sample peak process-tree RSS every 0.5 s."""
    shell = f"source {OPENFOAM_BASHRC} && " + " ".join(command)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak = [0]
    start = time.monotonic()
    with open(cwd / f"log.{name}", "wb") as log:
        proc = subprocess.Popen(["bash", "-lc", shell], cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        stop = threading.Event()

        def sample():
            if psutil is None:
                return
            while not stop.is_set():
                try:
                    root = psutil.Process(proc.pid)
                    rss = sum(p.memory_info().rss for p in [root, *root.children(recursive=True)])
                    peak[0] = max(peak[0], rss)
                except psutil.Error:
                    pass
                stop.wait(0.5)

        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        timed_out = False
        try:
            returncode = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            returncode, timed_out = proc.wait(), True
        stop.set()
        thread.join()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"stage": name, "returncode": returncode, "timed_out": timed_out, "wall_s": time.monotonic() - start,
            "child_user_s": after.ru_utime - before.ru_utime, "child_sys_s": after.ru_stime - before.ru_stime,
            "peak_rss_mb_sampled": (peak[0] / 1e6) if psutil is not None else None}


def run_case(spec: dict, criteria: dict, template: Path, tri64: np.ndarray, root: Path) -> dict:
    case_dir = root / "cases" / spec["id"]
    work = case_dir / "case"
    shutil.copytree(template, work)
    for p in work.rglob("*"):
        if p.is_file():
            p.chmod(p.stat().st_mode | 0o200)
    blob = translated_stl(tri64, spec["axis"], spec["shift_m"])
    stl_path = work / "constant/triSurface/design_candidate.stl"
    stl_path.write_bytes(blob)
    record = {"id": spec["id"], "axis": spec["axis"], "shift_m": spec["shift_m"],
              "stl_sha256": hashlib.sha256(blob).hexdigest(), "triangles": len(tri64),
              "stages": [], "status": "COMPLETED"}
    start = time.monotonic()
    for name, command in STAGES:
        stage = timed_run(name, command, work, criteria["stage_timeout_s"])
        record["stages"].append(stage)
        if stage["returncode"] != 0:
            allowed = name == "checkMesh" and parse_check_mesh((work / "log.checkMesh").read_text(errors="replace"))["only_allowed_concave_failure"]
            if not allowed:
                record["status"] = f"{name}_FAILED"
                break
    record["total_wall_s"] = time.monotonic() - start
    try:
        def text(name):
            p = work / f"log.{name}"
            return p.read_text(errors="replace") if p.is_file() else ""
        record["snappy"] = parse_snappy(text("snappyHexMesh"))
        record["mesh"] = parse_check_mesh(text("checkMesh"))
        if record["status"] == "COMPLETED":
            record["solver"] = parse_solver(text("simpleFoam"))
            dat = work / "postProcessing/forceCoeffs/0/coefficient.dat"
            record["forces"] = force_window(dat.read_text(), criteria["force_window"])
    except Exception as exc:  # parse failure is recorded, not fatal
        record["status"] = record["status"] if record["status"] != "COMPLETED" else "PARSE_FAILED"
        record["parse_error"] = f"{type(exc).__name__}: {exc}"
    keep = case_dir / "retained"
    keep.mkdir()
    for p in (*work.glob("log.*"), work / "postProcessing/forceCoeffs/0/coefficient.dat"):
        if p.is_file():
            with p.open("rb") as src, gzip.open(keep / (p.name + ".gz"), "wb") as dst:
                shutil.copyfileobj(src, dst)
    shutil.rmtree(work)  # meshes are large; logs and force history are retained
    write_json(case_dir / "case_result.json", record)
    return record


# ---- OpenFOAM installation (copied from the Round 5 runner; hash-pinned lock) ---

def install_openfoam(work: Path, lock: dict, expected_version: str) -> dict:
    release = dict(l.split("=", 1) for l in Path("/etc/os-release").read_text().splitlines() if "=" in l)
    arch = subprocess.run(["dpkg", "--print-architecture"], check=True, text=True, capture_output=True).stdout.strip()
    require(release.get("ID", "").strip('"') == "ubuntu", f"unsupported OS ID: {release.get('ID')}")
    require(release.get("VERSION_CODENAME", "").strip('"') == lock["suite"], "OpenCFD v2512 lock only supports Ubuntu Jammy")
    require(arch == lock["architecture"], f"unsupported architecture: {arch}")
    installer = work / "add-debian-repo.sh"
    with installer.open("wb") as stream:
        subprocess.run(["curl", "-fsSL", "https://dl.openfoam.com/add-debian-repo.sh"], check=True, stdout=stream)
    require(sha(installer) == lock["official_installer_sha256"], "official repository installer SHA mismatch")
    subprocess.run(["bash", str(installer)], check=True)
    for name, record in lock["indexes"].items():
        target = work / name
        with urllib.request.urlopen(record["url"], timeout=60) as response, target.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        require(sha(target) == record["sha256"], f"official apt index SHA mismatch for {name}")
    subprocess.run(["apt-get", "update"], check=True)
    names = list(lock["packages"])
    subprocess.run(["apt-get", "download", *[f"{n}={lock['version']}" for n in names]], cwd=work, check=True)
    debs = []
    for n in names:
        deb = work / f"{n}_{lock['version']}_{lock['package_architectures'][n]}.deb"
        require(deb.is_file() and sha(deb) == lock["packages"][n], f"{n} package missing or SHA mismatch")
        debs.append(str(deb))
    subprocess.run(["apt-get", "install", "-y", *debs], check=True)
    for d in debs:
        Path(d).unlink()  # hundreds of MB; hashes are verified and recorded by the lock
    installed = subprocess.run(["dpkg-query", "-W", "-f=${Package}=${Version}\n", *names], check=True, text=True, capture_output=True).stdout.splitlines()
    require(sorted(installed) == sorted(f"{n}={lock['version']}" for n in names), "installed OpenFOAM package set differs from lock")
    probe = subprocess.run(["bash", "-lc", f'source {OPENFOAM_BASHRC} && source "$WM_PROJECT_DIR/etc/config.sh/aliases" && foamVersion'],
                           text=True, capture_output=True)
    lines = [l.strip() for s in (probe.stdout, probe.stderr) for l in s.splitlines() if re.fullmatch(r"OpenFOAM-[A-Za-z0-9._+-]+", l.strip())]
    require(lines == [expected_version], f"expected one {expected_version!r} foamVersion line; found {lines}; rc={probe.returncode} stdout={probe.stdout[-300:]!r} stderr={probe.stderr[-300:]!r}")
    return {"installed_packages": installed, "foamVersion": lines[0], "os_release": release, "architecture": arch}


# ---- main ----------------------------------------------------------------------

def discover_inputs() -> Path:
    matches = sorted(INPUT_ROOT.rglob("x2_criteria.json"))
    require(len(matches) == 1, f"expected one attached x2_criteria.json, found {len(matches)}")
    return matches[0].parent


def main() -> None:
    require(CRITERIA_SHA256 != "__CRITERIA_SHA256__", "runner has not been bound to registered criteria")
    require(not OUTPUT.exists(), f"refusing to overwrite prior output: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    started = time.monotonic()
    data = discover_inputs()
    require(sha(data / "x2_criteria.json") == CRITERIA_SHA256, "criteria SHA mismatch")
    require((data / "x2_criteria.json.sha256").read_text().strip() == CRITERIA_SHA256, "criteria SHA sidecar mismatch")
    criteria = json.loads((data / "x2_criteria.json").read_text())
    require(criteria["immutable"] and criteria["registered_before_run"], "criteria are not an immutable preregistration")
    for rel, expected in criteria["inputs"].items():
        require(sha(data / rel) == expected, f"input SHA mismatch: {rel}")
    lock = json.loads((data / "openfoam_package_lock.json").read_text())
    install = {"skipped_for_test": True} if os.environ.get("X2_SKIP_INSTALL") else install_openfoam(OUTPUT, lock, criteria["environment"]["foam_version"])
    tri64 = read_stl(data / "baseline_stage_v.stl")
    require(len(tri64) == criteria["baseline"]["triangles"], "baseline triangle count mismatch")
    results, deadline = [], criteria["launch_deadline_hours"] * 3600
    limit, streak = criteria["stop_after_consecutive_failures"], 0

    def summary():
        return {"criteria_sha256": CRITERIA_SHA256, "runner_sha256": sha(Path(__file__).resolve()),
                "round_id": criteria["round_id"], "install": install, "elapsed_s": time.monotonic() - started,
                "cases": results, "qualification_flags": criteria["qualification_flags"]}

    for spec in criteria["case_order"]:
        if time.monotonic() - started > deadline:
            results.append({"id": spec["id"], "status": "NOT_RUN_TIME_BUDGET"})
        elif streak >= limit:
            results.append({"id": spec["id"], "status": "NOT_RUN_CONSECUTIVE_FAILURES"})
        else:
            try:
                results.append(run_case(spec, criteria, data / "case_template", tri64, OUTPUT))
            except Exception as exc:  # per-case fail-soft: record and continue
                shutil.rmtree(OUTPUT / "cases" / spec["id"] / "case", ignore_errors=True)
                results.append({"id": spec["id"], "status": "RUNNER_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"})
            streak = streak + 1 if results[-1]["status"] != "COMPLETED" else 0
        write_json(OUTPUT / "result.json", summary())  # rewritten every case: survives a kernel kill
    manifest = {str(p.relative_to(OUTPUT)): sha(p) for p in sorted(OUTPUT.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    write_json(OUTPUT / "artifact_manifest.json", manifest)
    counts = {}
    for c in results:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    (OUTPUT / "DONE").write_text(json.dumps({"status": "FINISHED_MEASUREMENT_LOOP", "status_counts": counts, "artifact_manifest_sha256": sha(OUTPUT / "artifact_manifest.json")}, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        err = OUTPUT / "ERROR.json" if OUTPUT.exists() else OUTPUT.parent / "x2_startup_ERROR.json"
        err.parent.mkdir(parents=True, exist_ok=True)
        write_json(err, {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
