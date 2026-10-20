#!/usr/bin/env python3
"""Local Docker runtime for the registered Kaggle CPU OpenFOAM runners (decision 2026-10-20; gate: docs/local_openfoam_env_gate_2026_10_20.md).

  build                         build infra/local_openfoam/Dockerfile and write infra/local_openfoam/local_openfoam_lock.json (+ dpkg_list.txt)
  run KERNEL_DIR --out DIR [--dataset DIR]
                                run a Kaggle kernel's runner.py unchanged in the locked image: DIR is mounted at /kaggle/working, the dataset at
                                /kaggle/input/<dataset slug>; nothing else of Kaggle is emulated. Writes DIR/local_run.json.
  run RUNNER --out DIR --subset KIND ID... [--dataset DIR]
                                the gate's case subsets: the registered runner's own functions (fetch_source/install_*/run_case) for the listed ids
  stage-x3 DIR                  re-derive the XFID X3 formal Kaggle dataset (states from the X1 surfaces) and verify it against its criteria

The image identity (Docker image ID) is checked against the lock before every run; any mismatch refuses to run.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra/local_openfoam"
LOCK = INFRA / "local_openfoam_lock.json"
FREEZE = ROOT / "docs/evidence/local_openfoam_env_2026_10_20/freeze.json"   # once it exists the lock may not change (gate section 6)
IMAGE_TAR = ROOT / "work/local_openfoam/image"   # docker save of the locked image (git-ignored; restore with docker load -i)
DPKG_FMT = "${Package}=${Version} ${Architecture}\\n"
TAG = "cfd-local-openfoam:2512-noble-amd64"
PLATFORM = "linux/amd64"
X3_FORMAL = ROOT / "infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal"
OF_LOCKS = {"jammy": ROOT / "infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/openfoam_package_lock.json",
            "noble": ROOT / "infra/kaggle/kernel_openfoam_xfid_v16/openfoam_package_lock.json"}
DEFAULT_CPUS, DEFAULT_MEMORY = "4", "8g"   # Kaggle CPU: 4 vCPU; the host is shared with other studies


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def docker(*args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, text=True, capture_output=True, **kw)


def image_id(tag: str = TAG) -> str:
    return docker("image", "inspect", tag, "--format", "{{.Id}}").stdout.strip()


def in_image(script: str) -> str:
    return docker("run", "--rm", "--platform", PLATFORM, TAG, "bash", "-lc", script).stdout


def host_load() -> dict:
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], text=True, capture_output=True).stdout.strip()
    return {"loadavg": list(os.getloadavg()), "swap": swap, "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}


# ---- build --------------------------------------------------------------------------------------------

def refuse_after_freeze() -> None:
    if FREEZE.exists():
        raise SystemExit(f"refusing: {FREEZE} exists; a new image is a new environment and needs a new gate round")


def build() -> dict:
    refuse_after_freeze()
    with tempfile.TemporaryDirectory() as ctx:
        ctx = Path(ctx)
        for name in ("Dockerfile", "requirements.lock"):
            shutil.copy2(INFRA / name, ctx / name)
        shutil.copy2(X3_FORMAL / "runner.py", ctx / "runner_x3_formal.py")
        for suite, path in OF_LOCKS.items():
            shutil.copy2(path, ctx / f"openfoam_package_lock_{suite}.json")
        subprocess.run(["docker", "build", "--platform", PLATFORM, "-t", TAG, str(ctx)], check=True)
    return write_lock()


def write_lock() -> dict:
    refuse_after_freeze()
    sh = lambda script: in_image(script).strip()
    of = "source /usr/lib/openfoam/openfoam2512/etc/bashrc && source \"$WM_PROJECT_DIR/etc/config.sh/aliases\" && "
    probe = {"openfoam_packages": sh("dpkg-query -W -f='${Package}=${Version}\\n' openfoam2512 openfoam2512-common openfoam2512-tools").splitlines(),
             "foam_version": sh(of + "foamVersion 2>&1"), "wm_options": sh(of + "echo $WM_OPTIONS"), "mpi": sh(of + "echo $FOAM_MPI"),
             "os_release": sh("grep -E '^(PRETTY_NAME|VERSION_CODENAME)=' /etc/os-release"), "arch": sh("dpkg --print-architecture"),
             "cpu_flags": sh("grep -m1 ^flags /proc/cpuinfo"), "cpu_model": sh("grep -m1 '^model name' /proc/cpuinfo"),
             "pip_freeze": sh("pip freeze").splitlines(),
             **json.loads(sh("python -c 'import json, sys, gmsh, numpy, scipy, psutil; print(json.dumps({\"python\": sys.version, \"gmsh\": gmsh.__version__, "
                             "\"numpy\": numpy.__version__, \"scipy\": scipy.__version__, \"psutil\": psutil.__version__}))'"))}
    dpkg = in_image(f"dpkg-query -W -f='{DPKG_FMT}' | LC_ALL=C sort")
    (INFRA / "dpkg_list.txt").write_text(dpkg)
    inspect = json.loads(docker("image", "inspect", TAG).stdout)[0]
    IMAGE_TAR.mkdir(parents=True, exist_ok=True)
    tar = IMAGE_TAR / f"{inspect['Id'].split(':')[1][:16]}.tar"
    if not tar.exists():
        subprocess.run(["docker", "save", "-o", str(tar), inspect["Id"]], check=True)
    lock = {
        "schema_version": 1,
        "purpose": "local Docker runtime of the registered Kaggle CPU OpenFOAM runners (gate docs/local_openfoam_env_gate_2026_10_20.md)",
        "image": {"tag": TAG, "image_id": inspect["Id"], "platform": PLATFORM, "created": inspect["Created"],
                  "base": "ubuntu:24.04@sha256:a2d43bffc46670d7108bb3c0468c67c5557c4c92e83e1e34cbff1322ad1b94dc (linux/amd64 manifest of the index "
                          "sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac)",
                  "dockerfile_sha256": sha(INFRA / "Dockerfile"), "requirements_lock_sha256": sha(INFRA / "requirements.lock"),
                  "install_helper": {"path": "infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py", "sha256": sha(X3_FORMAL / "runner.py")},
                  "dpkg_list": {"path": "infra/local_openfoam/dpkg_list.txt", "sha256": sha(INFRA / "dpkg_list.txt"), "packages": len(dpkg.splitlines())},
                  "saved_tar": {"path": tar.relative_to(ROOT).as_posix(), "sha256": sha(tar), "bytes": tar.stat().st_size,
                                "restore": f"docker load -i {tar.relative_to(ROOT).as_posix()} (the image ID must equal image_id)"}},
        "openfoam": {"package_locks": {s: {"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for s, p in OF_LOCKS.items()},
                     "lock_suite_used": "noble", "installed": probe["openfoam_packages"], "foam_version": probe["foam_version"],
                     "wm_options": probe["wm_options"], "mpi": probe["mpi"]},
        "python": {k: probe[k] for k in ("python", "gmsh", "numpy", "scipy", "psutil", "pip_freeze")},
        "os": {"os_release": probe["os_release"], "dpkg_architecture": probe["arch"]},
        "emulation": {"cpu_model": probe["cpu_model"], "cpu_flags": probe["cpu_flags"],
                      "note": "amd64 binaries under Rosetta on Apple silicon (Docker Desktop); the Kaggle CPU reports Intel Xeon @ 2.20GHz"},
        "host": {"machine": platform.machine(), "macos": platform.mac_ver()[0],
                 "cpu": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], text=True, capture_output=True).stdout.strip(),
                 "docker_server": docker("version", "--format", "{{.Server.Version}}").stdout.strip(),
                 "docker_desktop": subprocess.run(["defaults", "read", "/Applications/Docker.app/Contents/Info.plist", "CFBundleShortVersionString"],
                                                  text=True, capture_output=True).stdout.strip()},
        "run_defaults": {"cpus": DEFAULT_CPUS, "memory": DEFAULT_MEMORY},
    }
    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return lock


# ---- run ----------------------------------------------------------------------------------------------

def locked_image() -> dict:
    lock = json.loads(LOCK.read_text())
    if FREEZE.exists() and sha(LOCK) != json.loads(FREEZE.read_text())["lock_sha256"]:
        raise SystemExit("refusing to run: the lock differs from the frozen lock")
    got = image_id(lock["image"]["image_id"])
    if got != lock["image"]["image_id"]:
        raise SystemExit(f"refusing to run: image {got} differs from the lock's {lock['image']['image_id']}")
    return lock


def run(target: Path, out: Path, dataset: Path | None, subset: list[str] | None, cpus: str, memory: str) -> int:
    lock = locked_image()
    runner = target / "runner.py" if target.is_dir() else target
    meta_path = runner.parent / "kernel-metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else None
    out.mkdir(parents=True, exist_ok=True)
    if (out / "local_run.json").exists():
        raise SystemExit(f"refusing to overwrite: {out / 'local_run.json'}")
    mounts = ["-v", f"{runner.resolve()}:/kaggle/src/runner.py:ro", "-v", f"{out.resolve()}:/kaggle/working"]
    if dataset:
        slug = meta["dataset_sources"][0].split("/")[1] if meta and meta.get("dataset_sources") else dataset.name
        mounts += ["-v", f"{dataset.resolve()}:/kaggle/input/{slug}:ro"]
    command = ["python", "/kaggle/src/runner.py"]
    if subset:
        mounts += ["-v", f"{Path(__file__).resolve()}:/kaggle/src/local_openfoam.py:ro"]
        command = ["python", "/kaggle/src/local_openfoam.py", "subset", "/kaggle/src/runner.py", *subset]
    # after the runner: the image's package list again (the runners re-run install_openfoam at start; it must change nothing)
    after = f"rc=$?; dpkg-query -W -f='{DPKG_FMT}' | LC_ALL=C sort | sha256sum | cut -c1-64 > /kaggle/working/dpkg_after.sha256; exit $rc"
    args = ["run", "--rm", "--platform", PLATFORM, "--cpus", cpus, "--memory", memory, "--memory-swap", memory, *mounts,
            "-w", "/kaggle/working", lock["image"]["image_id"], "bash", "-c", f'"$@"; {after}', "_", *command]
    record = {"lock_sha256": sha(LOCK), "image_id": lock["image"]["image_id"], "runner": str(runner), "runner_sha256": sha(runner),
              "kernel_metadata": meta, "dataset": str(dataset) if dataset else None, "subset": subset, "docker_args": args,
              "host_before": host_load(), "script_sha256": sha(Path(__file__))}
    t0 = time.monotonic()
    with open(out / "local_run.log", "wb") as log:
        rc = subprocess.run(["docker", *args], stdout=log, stderr=subprocess.STDOUT).returncode
    dpkg_after = (out / "dpkg_after.sha256").read_text().strip() if (out / "dpkg_after.sha256").is_file() else None
    record.update({"returncode": rc, "wall_s": time.monotonic() - t0, "host_after": host_load(), "dpkg_after_sha256": dpkg_after,
                   "dpkg_after_matches_lock": dpkg_after == lock["image"]["dpkg_list"]["sha256"]})
    (out / "local_run.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return rc


# ---- subset (runs inside the container) ---------------------------------------------------------------

def subset(runner_path: Path, kind: str, ids: list[str]) -> None:
    """Call the registered runner's own functions for the listed case ids (the gate's subsets; no runner byte is changed)."""
    import importlib.util
    import threading
    from concurrent.futures import ThreadPoolExecutor
    out = Path(os.environ.get("LOCAL_OF_WORKING", "/kaggle/working")) / f"subset_{kind}"   # override only for tests
    os.environ["T20B_OUTPUT" if kind == "t20b" else "X3_OUTPUT"] = str(out)
    spec = importlib.util.spec_from_file_location("runner", runner_path)
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    if out.exists():
        raise SystemExit(f"refusing to overwrite prior output: {out}")
    out.mkdir(parents=True)
    started, results, lock_ = time.monotonic(), [], threading.Lock()
    env = {"python": sys.version, "cpu_count": os.cpu_count(), "uname": list(os.uname()), "runner_sha256": sha(runner_path), "kind": kind, "ids": ids}

    def summary(install):
        return {**env, "install": install, "elapsed_s": time.monotonic() - started, "cases": results}

    if kind == "t20b":
        (out / "work").mkdir()
        r.SOURCE = r.fetch_source(out / "work")
        env["gmsh_version"] = r.install_gmsh()
        locks = {name: json.loads((r.SOURCE / rel).read_text()) for name, rel in r.LOCKS.items()}
        install = r.install_openfoam(out / "work", locks)
        by_id = {s["id"]: s for s in r.make_specs(r.WF_CASES)}   # the wf kernel's registered specs (iterations, continuation)
        specs = [by_id[i] for i in ids]

        def work(s):
            res = r.run_case(s, r.SOURCE, started + 6 * 3600)
            with lock_:
                results.append(res)
                r.write_json(out / "result.json", summary(install))

        with ThreadPoolExecutor(r.WORKERS) as pool:
            list(pool.map(work, specs))
        shutil.rmtree(out / "work", ignore_errors=True)
    elif kind == "x3":
        data = r.discover_inputs()
        if r.sha(data / "x3_criteria.json") != r.CRITERIA_SHA256:
            raise SystemExit("criteria SHA mismatch")
        criteria = json.loads((data / "x3_criteria.json").read_text())
        for rel, expected in criteria["inputs"].items():
            if r.sha(data / rel) != expected:
                raise SystemExit(f"input SHA mismatch: {rel}")
        locks = {s: json.loads((data / f"openfoam_package_lock_{s}.json").read_text()) for s in criteria["environment"]["registered_lock_suites"]}
        install = r.install_openfoam(out, locks, criteria["environment"]["foam_version"])
        by_id = {c["id"]: c for c in criteria["case_order"]}
        tri = {}
        for i in ids:
            c = by_id[i]
            if c["state"] not in tri:
                tri[c["state"]] = r.read_stl(data / criteria["states"][c["state"]]["file"])
            results.append(r.run_case(c, criteria, data / "case_template", tri[c["state"]], out))
            r.write_json(out / "result.json", summary(install))
    else:
        raise SystemExit(f"unknown subset kind {kind}")
    r.write_json(out / "result.json", summary(install))
    (out / "DONE").write_text(json.dumps({"cases": len(results), "statuses": sorted({c["status"] for c in results})}) + "\n")


# ---- X3 formal dataset ------------------------------------------------------------------------------

def stage_x3(dest: Path) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import prepare_kaggle_xfid_gridphase_x3 as x3
    crit_path = ROOT / "docs/evidence/xfid_gridphase_x3_2026_10_04/formal/x3_criteria.json"
    criteria = json.loads(crit_path.read_text())
    if dest.exists():
        raise SystemExit(f"refusing to overwrite: {dest}")
    (dest / "states").mkdir(parents=True)
    for s in criteria["states"]:
        (dest / f"states/{s}.stl").write_bytes(x3.state_stl(s)[0])   # asserts the X1 result hash
    for src in sorted((x3.R5 / "case_template").rglob("*")):
        rel = src.relative_to(x3.R5 / "case_template")
        if src.is_file() and rel.as_posix() != "constant/triSurface/design_candidate.stl":
            (dest / "case_template" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / "case_template" / rel)
    shutil.copy2(x3.R5 / "openfoam_package_lock.json", dest / "openfoam_package_lock_jammy.json")
    shutil.copy2(x3.NOBLE / "openfoam_package_lock.json", dest / "openfoam_package_lock_noble.json")
    shutil.copy2(crit_path, dest / "x3_criteria.json")
    shutil.copy2(crit_path.with_name("x3_criteria.json.sha256"), dest / "x3_criteria.json.sha256")
    got = {p.relative_to(dest).as_posix(): sha(p) for p in sorted(dest.rglob("*")) if p.is_file() and not p.name.startswith("x3_criteria")}
    if got != criteria["inputs"]:
        raise SystemExit(f"staged X3 dataset differs from the criteria inputs: {sorted(set(got.items()) ^ set(criteria['inputs'].items()))[:4]}")
    return {"files": len(got), "criteria_sha256": sha(dest / "x3_criteria.json")}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("lock", help="rewrite the lock from the existing image (no build)")
    p = sub.add_parser("run")
    p.add_argument("target", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dataset", type=Path)
    p.add_argument("--subset", nargs="+", metavar="KIND_AND_IDS")
    p.add_argument("--cpus", default=DEFAULT_CPUS)
    p.add_argument("--memory", default=DEFAULT_MEMORY)
    p = sub.add_parser("subset")
    p.add_argument("runner", type=Path)
    p.add_argument("kind", choices=("t20b", "x3"))
    p.add_argument("ids", nargs="+")
    p = sub.add_parser("stage-x3")
    p.add_argument("dest", type=Path)
    a = ap.parse_args(argv)
    if a.cmd in ("build", "lock"):
        print(json.dumps((build() if a.cmd == "build" else write_lock())["image"], indent=1))
    elif a.cmd == "run":
        sys.exit(run(a.target, a.out, a.dataset, a.subset, a.cpus, a.memory))
    elif a.cmd == "subset":
        subset(a.runner, a.kind, a.ids)
    else:
        print(json.dumps(stage_x3(a.dest)))


if __name__ == "__main__":
    main()
