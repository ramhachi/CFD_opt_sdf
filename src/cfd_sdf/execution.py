from __future__ import annotations

import json
import platform
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEFAULT_OPENFOAM_DOCKER_IMAGE = "opencfd/openfoam-default:2512"


@dataclass(frozen=True)
class OpenFoamRunResult:
    case_dir: Path
    backend: str
    dry_run: bool
    command: list[str]
    returncode: int | None
    stdout_log: Path
    stderr_log: Path
    summary_path: Path
    docker_image: str | None = None
    timed_out: bool = False
    error: str | None = None
    solver_error_logs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.dry_run or (self.returncode == 0 and not self.timed_out and self.error is None)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("case_dir", "stdout_log", "stderr_log", "summary_path"):
            data[key] = str(data[key])
        data["ok"] = self.ok
        return data


def run_openfoam_case(
    case_dir: Path,
    *,
    backend: str = "auto",
    dry_run: bool = True,
    timeout_seconds: int | None = None,
    docker_image: str | None = None,
) -> OpenFoamRunResult:
    resolved = case_dir.resolve()
    image = docker_image or os.environ.get("CFD_SDF_OPENFOAM_IMAGE", DEFAULT_OPENFOAM_DOCKER_IMAGE)
    selected_backend = _select_backend(backend)
    command = _command_for_backend(selected_backend, resolved, image)
    stdout_log = resolved / "log.runOpenFOAM.stdout"
    stderr_log = resolved / "log.runOpenFOAM.stderr"
    summary_path = resolved / "openfoam_run_summary.json"

    resolved.mkdir(parents=True, exist_ok=True)
    returncode: int | None = None
    timed_out = False
    error = None
    solver_error_logs: list[str] = []
    if dry_run:
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
    else:
        started_at_ns = time.time_ns()
        try:
            with stdout_log.open("w", encoding="utf-8") as stdout, stderr_log.open("w", encoding="utf-8") as stderr:
                completed = subprocess.run(
                    command,
                    cwd=resolved,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            returncode = int(completed.returncode)
            solver_error_logs = _scan_recent_solver_logs(resolved, started_at_ns)
            if returncode == 0 and solver_error_logs:
                error = "OpenFOAM child solver log reported a fatal error: " + "; ".join(solver_error_logs)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            error = f"OpenFOAM execution timed out after {exc.timeout} seconds"
            stderr_log.write_text(error, encoding="utf-8")
            if not stdout_log.exists():
                stdout_log.write_text("", encoding="utf-8")
        except OSError as exc:
            error = str(exc)
            stderr_log.write_text(error, encoding="utf-8")
            if not stdout_log.exists():
                stdout_log.write_text("", encoding="utf-8")

    result = OpenFoamRunResult(
        case_dir=resolved,
        backend=selected_backend,
        dry_run=dry_run,
        command=command,
        returncode=returncode,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        summary_path=summary_path,
        docker_image=image if selected_backend == "docker" else None,
        timed_out=timed_out,
        error=error,
        solver_error_logs=solver_error_logs,
    )
    summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result


def _select_backend(backend: str) -> str:
    normalized = backend.lower()
    if normalized not in {"auto", "local", "wsl", "docker"}:
        raise ValueError(f"Unsupported OpenFOAM backend: {backend}")
    if normalized != "auto":
        return normalized
    if shutil.which("simpleFoam") and shutil.which("blockMesh"):
        return "local"
    if platform.system().lower().startswith("win") and shutil.which("wsl") and _wsl_has_openfoam():
        return "wsl"
    if shutil.which("docker") and _docker_is_ready():
        return "docker"
    return "local"


def _command_for_backend(backend: str, case_dir: Path, docker_image: str) -> list[str]:
    if backend == "local":
        return ["bash", "-lc", "chmod +x Allrun Allclean && ./Allrun"]
    if backend == "wsl":
        windows_path = str(case_dir)
        script = (
            'case_dir="$(wslpath -a "$1")" && '
            'cd "$case_dir" && '
            "chmod +x Allrun Allclean && "
            "./Allrun"
        )
        return ["wsl", "bash", "-lc", script, "bash", windows_path]
    if backend == "docker":
        return [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "--mount",
            f"type=bind,source={case_dir},target=/case",
            "-w",
            "/case",
            docker_image,
            "-lc",
            "chmod +x Allrun Allclean && ./Allrun",
        ]
    raise ValueError(f"Unsupported OpenFOAM backend: {backend}")


def _wsl_has_openfoam() -> bool:
    try:
        completed = subprocess.run(
            ["wsl", "bash", "-lc", "command -v simpleFoam >/dev/null && command -v blockMesh >/dev/null"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _docker_is_ready() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _scan_recent_solver_logs(case_dir: Path, started_at_ns: int) -> list[str]:
    patterns = (
        "FOAM FATAL",
        "mpirun has detected an attempt to run as root",
        "Segmentation fault",
        "Floating point exception (core dumped)",
    )
    threshold_ns = started_at_ns - 2_000_000_000
    matches: list[str] = []
    for path in case_dir.glob("log.*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime_ns < threshold_ns:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in patterns:
            if pattern.lower() in text.lower():
                matches.append(f"{path.name}:{pattern}")
                break
    return sorted(matches)
