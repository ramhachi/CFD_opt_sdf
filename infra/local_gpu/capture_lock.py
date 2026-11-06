#!/usr/bin/env python3
"""Capture LOCAL-GPU-01 in WSL2. Missing measurements are errors, never nulls.

Only environment is compared by check-lock; timestamp and volatile versioninfo
remain observations. The sidecar hashes the entire canonical JSON document.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import csv
import datetime as dt
import hashlib
import io
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "julia/CFDSDFWaterLilyT4"
LOCK = Path(__file__).with_name("lock.json")
PROFILE = "local_rtx4070ti"
GPU_FIELDS = ("name", "memory.total", "driver_version", "compute_cap", "power.limit")


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def jload(path):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError(f"duplicate JSON key: {k}")
            result[k] = v
        return result

    def invalid(value):
        raise ValueError(f"non-finite JSON constant: {value}")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"JSON number overflows: {value}")
        return result

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=invalid, parse_float=number)


def error(reason):
    return {"error": str(reason)}


def decode(data):
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-16-le" if b"\x00" in data else "utf-8"
    return data.decode(encoding, errors="replace").strip()


def probe(argv, timeout=30, env=None):
    try:
        p = subprocess.run(list(map(str, argv)), capture_output=True, timeout=timeout, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return error(f"{argv[0]}: {exc}")
    if p.returncode:
        return error(f"{argv[0]} exit {p.returncode}: {decode(p.stderr) or decode(p.stdout)}")
    text = decode(p.stdout)
    return text if text else error(f"{argv[0]} returned empty output")


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        return error(exc)


def file_sha(path):
    try:
        return sha(path)
    except OSError as exc:
        return error(exc)


def literal_constants(path, names):
    tree = ast.parse(Path(path).read_text())
    return {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in names}


def runner_constants():
    return literal_constants(ROOT / "src/cfd_harness/campaign_runner_template.py", ("JULIA_URL", "JULIA_SHA256"))


def config_keys(path, wanted):
    if isinstance(path, dict):
        return {f"{section}.{key}": dict(path) for section, key in wanted}
    content = read_text(path)
    if isinstance(content, dict):
        return {f"{section}.{key}": dict(content) for section, key in wanted}
    try:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(content)
        return {f"{section}.{key}": parser.get(section, key) if parser.has_option(section, key)
                else error(f"{path}: missing [{section}] {key} (OS default is not an observed setting)") for section, key in wanted}
    except configparser.Error as exc:
        return {f"{section}.{key}": error(exc) for section, key in wanted}


def windows_wslconfig():
    profile = probe(["cmd.exe", "/c", "echo", "%USERPROFILE%"])
    if not isinstance(profile, str) or "%USERPROFILE%" in profile:
        return error("cannot locate Windows USERPROFILE through cmd.exe")
    path = probe(["wslpath", "-u", profile + "\\.wslconfig"])
    return Path(path) if isinstance(path, str) else path


def capture(*, julia=None, wslconfig=None):
    """Return a full capture, including reasons when the current host is unsuitable."""
    commands = {}
    raw = probe(["nvidia-smi", "--query-gpu=" + ",".join(GPU_FIELDS), "--format=csv,noheader"])
    commands["nvidia_smi"] = raw
    values = {}
    if isinstance(raw, str):
        rows = list(csv.reader(io.StringIO(raw)))
        if len(rows) == 1 and len(rows[0]) == len(GPU_FIELDS):
            values = dict(zip(GPU_FIELDS, (x.strip() for x in rows[0])))
        else:
            commands["nvidia_smi"] = error("exactly one physical GPU and five inventory fields are required")
    # WSL NVML may reject a field for the whole query. Preserve that failure but
    # independently acquire name/driver, rather than losing every inventory item.
    if not values:
        for field in GPU_FIELDS:
            got = probe(["nvidia-smi", "--query-gpu=" + field, "--format=csv,noheader"])
            values[field] = got if isinstance(got, dict) or "\n" not in got else error("expected one GPU, got multiple rows")
    for field, value in values.items():
        if isinstance(value, str) and (not value or value.lower() in ("n/a", "[n/a]", "not supported", "[not supported]")):
            values[field] = error(f"nvidia-smi field {field} unavailable: {value}")
    uuid = probe(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"])
    if isinstance(uuid, str) and (not uuid.startswith("GPU-") or "\n" in uuid):
        uuid = error(f"nvidia-smi UUID unavailable or ambiguous: {uuid}")
    gpu = {"name": values["name"], "driver_version": values["driver_version"], "memory_total": values["memory.total"],
           "compute_cap": values["compute_cap"], "power_limit": values["power.limit"], "uuid": uuid}
    executable = shutil.which(str(julia or os.environ.get("LOCAL_GPU_JULIA", "julia")))
    julia_path = Path(executable).resolve() if executable else None
    constants = runner_constants()
    julia_info = {"version": probe([str(julia_path), "--startup-file=no", "--version"]) if julia_path else error("Julia executable not found"),
                  "executable": str(julia_path) if julia_path else error("Julia executable not found"),
                  "sha256": file_sha(julia_path) if julia_path else error("Julia executable not found"),
                  "archive_url": constants["JULIA_URL"], "archive_sha256": constants["JULIA_SHA256"]}
    child_env = dict(os.environ, CUDA_VISIBLE_DEVICES="0", CUDA_DEVICE_ORDER="PCI_BUS_ID", JULIA_NUM_THREADS="1")
    cuda = error("CUDA probe skipped: nvidia-smi GPU/driver unavailable")
    cuda_identity = error("CUDA probe unavailable")
    if julia_path and isinstance(gpu["name"], str) and isinstance(gpu["driver_version"], str):
        code = ('using CUDA; try CUDA.versioninfo() catch e; '
                'println("LOCAL_GPU_VERSIONINFO_ERROR=", sprint(showerror, e)); end; '
                'println("LOCAL_GPU_FUNCTIONAL=", CUDA.functional()); '
                'println("LOCAL_GPU_CUDA_VERSION=", pkgversion(CUDA)); '
                'println("LOCAL_GPU_RUNTIME=", CUDA.runtime_version()); '
                'println("LOCAL_GPU_DRIVER=", CUDA.driver_version()); '
                'println("LOCAL_GPU_DEVICE_COUNT=", length(collect(CUDA.devices())))')
        cuda = probe([str(julia_path), "--startup-file=no", f"--project={PROJECT}", "-e", code], timeout=300, env=child_env)
        if isinstance(cuda, str):
            markers = dict(line.split("=", 1) for line in cuda.splitlines() if line.startswith("LOCAL_GPU_") and "=" in line)
            cuda_identity = {k.removeprefix("LOCAL_GPU_").lower(): v for k, v in markers.items() if k != "LOCAL_GPU_VERSIONINFO_ERROR"}
            if cuda_identity.get("functional") != "true" or cuda_identity.get("device_count") != "1":
                cuda_identity = error("CUDA.functional() must be true with exactly one visible device")
    config = Path(wslconfig) if wslconfig else windows_wslconfig()
    try:
        numpy_version = importlib.metadata.version("numpy")
    except importlib.metadata.PackageNotFoundError:
        numpy_version = error("NumPy is not installed in the capture/runner Python environment")
    environment = {
        "backend_profile": PROFILE,
        "host": {"proc_version": read_text("/proc/version"), "windows_ver": probe(["cmd.exe", "/c", "ver"])},
        "wsl": {"version": probe(["wsl.exe", "--version"]), "kernel": platform.release(), "distro": read_text("/etc/os-release"),
                "settings": {"wsl_conf": config_keys("/etc/wsl.conf", (("gpu", "appendLibPath"), ("automount", "ldconfig"))),
                             "wslconfig_path": str(config.resolve()) if isinstance(config, Path) else config,
                             "wslconfig": config_keys(config, (("wsl2", "memory"), ("wsl2", "processors"), ("wsl2", "swap"))) }},
        "gpu": gpu, "julia": julia_info,
        "python": {"version": sys.version, "executable": str(Path(sys.executable).resolve()),
                   "sha256": file_sha(Path(sys.executable).resolve()), "numpy_version": numpy_version},
        "project": {"path": "julia/CFDSDFWaterLilyT4", "manifest_sha256": file_sha(PROJECT / "Manifest.toml"),
                    "project_sha256": file_sha(PROJECT / "Project.toml")},
        "cuda": cuda_identity, "cuda_visible_devices": "0", "cuda_device_order": "PCI_BUS_ID",
        "julia_depot_path": os.environ.get("JULIA_DEPOT_PATH", str(Path.home() / ".julia")), "path_mode": "CAMPAIGN_WORK_ROOT",
    }
    result = {"schema_version": 1, "captured_utc": utc(), "environment": environment,
              "observations": {"cuda_versioninfo": cuda, "commands": commands}, "errors": []}
    result["errors"] = required_errors(result)
    return result


def required_errors(lock):
    if not isinstance(lock, dict) or not isinstance(lock.get("environment"), dict):
        return ["mandatory environment object missing"]
    env = lock.get("environment", {})
    errors = []
    for section, key in (("gpu", "name"), ("gpu", "driver_version"), ("julia", "sha256"), ("project", "manifest_sha256")):
        value = env.get(section, {}).get(key) if isinstance(env.get(section), dict) else error(f"{section} is not an object")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"mandatory {section}.{key} missing: {value!r}")
    return errors


def load_lock(path=LOCK):
    path = Path(path)
    lock = jload(path)
    raw = path.read_bytes()
    if raw != canonical_bytes(lock):
        raise ValueError("lock JSON is not canonical")
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != sha(path):
        raise ValueError("lock SHA-256 sidecar missing or mismatched")
    errors = required_errors(lock)
    if errors:
        raise ValueError("; ".join(errors))
    if type(lock.get("schema_version")) is not int or lock["schema_version"] != 1 or not isinstance(lock.get("errors"), list) or lock["errors"]:
        raise ValueError("unsupported or failed environment lock")
    return lock


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=LOCK)
    p.add_argument("--julia")
    p.add_argument("--wslconfig", type=Path)
    args = p.parse_args(argv)
    try:
        if args.out.exists() or args.out.with_name(args.out.name + ".sha256").exists():
            raise ValueError(f"refusing to overwrite lock: {args.out}")
        lock = capture(julia=args.julia, wslconfig=args.wslconfig)
        if lock["errors"]:
            print(canonical_bytes({"status": "ERROR", **lock}).decode(), end="")
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("xb") as handle:
            handle.write(canonical_bytes(lock))
        with args.out.with_name(args.out.name + ".sha256").open("x") as handle:
            handle.write(sha(args.out) + "\n")
        print(canonical_bytes({"status": "CAPTURED", "path": str(args.out), "sha256": sha(args.out)}).decode(), end="")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(canonical_bytes({"status": "ERROR", "errors": [str(exc)]}).decode(), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
