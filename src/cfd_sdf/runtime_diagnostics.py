"""Read-only, bounded local runtime diagnostics.

Tool availability is reported separately from solver and physics
qualification. No installer, daemon startup, image pull, or solver run occurs.
"""

from __future__ import annotations

import csv
import ctypes
import importlib
import importlib.metadata
import io
import math
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE

RUNTIME_DIAGNOSTICS_SCHEMA_VERSION = 1
DEFAULT_RUNTIME_DIAGNOSTICS_TIMEOUT_SECONDS = 2.0
MAX_RUNTIME_DIAGNOSTICS_TIMEOUT_SECONDS = 10.0
_OPENFOAM_COMMANDS = ("simpleFoam", "blockMesh")
_DISTRIBUTIONS = {"mlx": ("mlx",), "warp": ("warp-lang", "warp", "nvidia-warp"), "xlb": ("xlb",)}


class _MemoryStatus(ctypes.Structure):
    _fields_ = [(name, ctype) for name, ctype in (
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    )]


def collect_runtime_diagnostics(*, timeout_seconds: float = DEFAULT_RUNTIME_DIAGNOSTICS_TIMEOUT_SECONDS, docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE) -> dict[str, Any]:
    """Collect bounded local facts without claiming solver qualification."""
    timeout = _timeout(timeout_seconds)
    if not isinstance(docker_image, str) or not docker_image.strip():
        raise ValueError("docker_image must be a non-empty string")
    system, architecture = platform.system() or "unknown", platform.machine() or "unknown"
    packages = _packages()
    return {
        "schema_version": RUNTIME_DIAGNOSTICS_SCHEMA_VERSION,
        "kind": "runtime_diagnostics",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {"host": "local_device", "target_windows_user_config": "unavailable"},
        "host": {"os": {"name": system, "release": _text(platform.release()), "version": _text(platform.version())}, "architecture": architecture},
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation(), "executable": _text(sys.executable)},
        "hardware": {"cpu_count": os.cpu_count(), "memory": _memory(system, timeout), "mac_chip": _mac_chip(system, architecture, timeout)},
        "packages": packages,
        "gpu": {"nvidia": _nvidia(timeout), "metal": _metal(system, architecture, packages["mlx"])},
        "docker": _docker(timeout, docker_image),
        "openfoam": {"local": _local_openfoam(timeout), "wsl": _wsl(system, timeout)},
        "target_windows_user_config": {"status": "unavailable", "reason": "Only the local device was inspected; no target Windows user configuration was supplied."},
        "solver_physics": {"status": "not_evaluated", "reason": "Runtime diagnostics do not execute or numerically qualify a solver case."},
    }


def parse_nvidia_smi_output(output: str) -> list[dict[str, Any]]:
    """Parse no-header ``nvidia-smi`` CSV without inventing missing values."""
    parsed = []
    for row in csv.reader(io.StringIO(output), skipinitialspace=True):
        row = [value.strip() for value in row]
        if len(row) < 3 or not any(row) or row[-2].lower().startswith("memory"):
            continue
        name = ",".join(row[:-2]).strip()
        if name:
            parsed.append({"name": name, "memory_total_mib": _memory_mib(row[-2]), "memory_free_mib": _memory_mib(row[-1])})
    return parsed


def _timeout(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be a finite positive number") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("timeout_seconds must be a finite positive number")
    return min(result, MAX_RUNTIME_DIAGNOSTICS_TIMEOUT_SECONDS)


def _run(command: list[str], timeout: float) -> dict[str, Any]:
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": None, "stdout": None, "timed_out": True}
    except FileNotFoundError:
        return {"status": "missing", "returncode": None, "stdout": None, "timed_out": False}
    except OSError as exc:
        return {"status": "error", "returncode": None, "stdout": None, "timed_out": False, "error": type(exc).__name__}
    return {"status": "ok" if process.returncode == 0 else "nonzero_exit", "returncode": process.returncode, "stdout": _text(process.stdout), "timed_out": False}


def _observed(result: Mapping[str, Any]) -> bool | None:
    """Timeout/error means unknown; only an observed failure is false."""
    return True if result.get("status") == "ok" else False if result.get("status") in {"missing", "nonzero_exit"} else None


def _memory(system: str, timeout: float) -> dict[str, Any]:
    if system == "Darwin":
        probe = _run(["sysctl", "-n", "hw.memsize"], timeout)
        total = _positive(probe.get("stdout")) if probe["status"] == "ok" else None
        return {"total_bytes": total, "available_bytes": None, "source": "sysctl.hw.memsize" if total is not None else None, "status": "ok" if total is not None else probe["status"]}
    if system == "Linux":
        values: dict[str, int] = {}
        try:
            with open("/proc/meminfo", encoding="utf-8") as stream:
                for line in stream:
                    key, _, raw = line.partition(":")
                    fields = raw.strip().split()
                    if key in {"MemTotal", "MemAvailable"} and fields and (value := _positive(fields[0])) is not None:
                        values[key] = value * 1024
        except (OSError, UnicodeError):
            pass
        total, available = values.get("MemTotal"), values.get("MemAvailable")
        return {"total_bytes": total, "available_bytes": available, "source": "/proc/meminfo" if total is not None else None, "status": "ok" if total is not None else "unavailable"}
    if system == "Windows":
        try:
            status = _MemoryStatus()
            status.dwLength = ctypes.sizeof(_MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return {"total_bytes": int(status.ullTotalPhys), "available_bytes": int(status.ullAvailPhys), "source": "GlobalMemoryStatusEx", "status": "ok"}
        except (AttributeError, OSError, TypeError):
            pass
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total, available = page_size * int(os.sysconf("SC_PHYS_PAGES")), page_size * int(os.sysconf("SC_AVPHYS_PAGES"))
    except (OSError, ValueError, TypeError):
        total = available = 0
    return {"total_bytes": total if total > 0 else None, "available_bytes": available if available > 0 else None, "source": "os.sysconf" if total > 0 else None, "status": "ok" if total > 0 else "unavailable"}


def _mac_chip(system: str, architecture: str, timeout: float) -> dict[str, Any]:
    if system != "Darwin":
        return {"status": "not_applicable", "name": None, "arm64_supported": None}
    brand, arm64 = _run(["sysctl", "-n", "machdep.cpu.brand_string"], timeout), _run(["sysctl", "-n", "hw.optional.arm64"], timeout)
    value = _text(arm64.get("stdout"))
    supported = True if value in {"1", "true", "yes"} else False if value in {"0", "false", "no"} else None
    return {"status": "ok" if brand["status"] == "ok" and _text(brand.get("stdout")) else brand["status"], "name": _text(brand.get("stdout")) if brand["status"] == "ok" else None, "arm64_supported": supported, "architecture": architecture}


def _packages() -> dict[str, dict[str, Any]]:
    result = {}
    for name, distributions in _DISTRIBUTIONS.items():
        for distribution in distributions:
            try:
                version = str(importlib.metadata.version(distribution))
            except importlib.metadata.PackageNotFoundError:
                continue
            except Exception as exc:
                result[name] = {"status": "error", "installed": None, "version": None, "distribution": distribution, "error": type(exc).__name__}
                break
            result[name] = {"status": "installed", "installed": True, "version": version, "distribution": distribution}
            break
        else:
            result[name] = {"status": "missing", "installed": False, "version": None, "distribution": None}
    return result


def _metal(system: str, architecture: str, mlx: Mapping[str, Any]) -> dict[str, Any]:
    if mlx.get("installed") is not True:
        return {"status": "not_checked", "checked": False, "available": None, "reason": "mlx is not installed according to importlib.metadata."}
    if system != "Darwin" or architecture.lower() not in {"arm64", "aarch64"}:
        return {"status": "not_supported", "checked": False, "available": None, "reason": "Metal verification is supported here only for macOS arm64."}
    try:
        available = bool(importlib.import_module("mlx.core").metal.is_available())
    except Exception as exc:
        return {"status": "error", "checked": True, "available": None, "error": type(exc).__name__}
    return {"status": "available" if available else "unavailable", "checked": True, "available": available}


def _nvidia(timeout: float) -> dict[str, Any]:
    path = shutil.which("nvidia-smi")
    result = {"tool": "nvidia-smi", "path": path, "installed": path is not None, "reachable": False, "query_succeeded": False, "gpus": [], "status": "missing"}
    if path is None:
        return result
    probe = _run([path, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"], timeout)
    result.update({"reachable": _observed(probe), "query_succeeded": _observed(probe), "status": probe["status"], "timed_out": probe["timed_out"]})
    if probe["status"] == "ok":
        result["gpus"] = parse_nvidia_smi_output(probe.get("stdout") or "")
        if not result["gpus"]:
            result["status"] = "parse_error"
    return result


def _docker(timeout: float, image: str) -> dict[str, Any]:
    path = shutil.which("docker")
    result = {"tool": "docker", "path": path, "installed": path is not None, "reachable": False, "server_version": None, "expected_openfoam_image": image, "image_available": None, "status": "missing"}
    if path is None:
        return result
    info = _run([path, "info", "--format", "{{.ServerVersion}}"], timeout)
    result.update({"status": info["status"], "reachable": _observed(info), "timed_out": info["timed_out"]})
    if info["status"] != "ok":
        return result
    result["server_version"] = _text(info.get("stdout"))
    inspect = _run([path, "image", "inspect", image, "--format", "{{.Id}}"], timeout)
    result.update({"image_available": _observed(inspect), "image_status": inspect["status"], "image_id_observed": _text(inspect.get("stdout")) if inspect["status"] == "ok" else None})
    return result


def _local_openfoam(timeout: float) -> dict[str, Any]:
    paths = {name: shutil.which(name) for name in _OPENFOAM_COMMANDS}
    checks = {}
    for name, path in paths.items():
        if path is None:
            checks[name] = {"path": None, "status": "missing", "reachable": False}
            continue
        probe = _run([path, "-help"], timeout)
        checks[name] = {"path": path, "status": probe["status"], "returncode": probe["returncode"], "timed_out": probe["timed_out"], "reachable": _observed(probe)}
    values = [check["reachable"] for check in checks.values()]
    reachable = False if any(value is False for value in values) else True if values and all(value is True for value in values) else None
    return {"required_commands": list(_OPENFOAM_COMMANDS), "installed": all(path is not None for path in paths.values()), "reachable": reachable, "status": "reachable" if reachable is True else "unavailable", "commands": checks}


def _wsl(system: str, timeout: float) -> dict[str, Any]:
    result = {"applicable": system == "Windows", "installed": None, "reachable": None, "status": "not_applicable" if system != "Windows" else "missing"}
    if system != "Windows":
        return result
    path = shutil.which("wsl") or shutil.which("wsl.exe")
    result["path"], result["installed"] = path, path is not None
    if path is None:
        result["reachable"] = False
        return result
    status = _run([path, "--status"], timeout)
    result.update({"status": status["status"], "reachable": _observed(status), "timed_out": status["timed_out"]})
    if status["status"] == "ok":
        openfoam = _run([path, "bash", "-lc", "command -v simpleFoam >/dev/null && command -v blockMesh >/dev/null"], timeout)
        result["openfoam"] = {"installed": _observed(openfoam), "reachable": _observed(openfoam), "status": openfoam["status"]}
    return result


def _memory_mib(value: str) -> int | float | None:
    if value.strip().lower() in {"", "n/a", "na", "-", "none"}:
        return None
    try:
        number = float(value.strip().split()[0])
    except (ValueError, IndexError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number) if number.is_integer() else number


def _positive(value: Any) -> int | None:
    try:
        value = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _text(value: Any) -> str | None:
    value = "" if value is None else str(value).strip()
    return value or None


__all__ = ["collect_runtime_diagnostics"]
