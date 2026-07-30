"""Execute, but never interpret, a prepared localized G2 FD experiment.

This module is deliberately the middle boundary of the localized FD protocol:
preparation creates immutable inputs, this runner creates fresh solver copies
and records execution provenance, and a later validator performs every
numerical acceptance decision.  In particular, this module never calculates
an FD derivative or declares qualification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping, Protocol

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE, _select_backend, run_openfoam_case
from .localized_g2_fd_preparation import (
    LOCALIZED_G2_FD_PREPARATION_FILENAME,
    LOCALIZED_G2_FD_PREPARATION_KIND,
    LOCALIZED_G2_FD_PREPARATION_SCHEMA_VERSION,
)
from .localized_alpha_reference_binding import load_and_verify_localized_alpha_reference_binding
from .localized_design_state_manifest import localized_design_state_manifest_sha256
from .localized_reference_state_bundle import LOCALIZED_REFERENCE_STATE_FILENAME
from .localized_openfoam_alpha_case import validate_localized_openfoam_alpha_case


LOCALIZED_G2_FD_RUN_SCHEMA_VERSION = 1
LOCALIZED_G2_FD_RUN_KIND = "localized_g2_openfoam_fd_run"
LOCALIZED_G2_FD_RUN_FILENAME = "localized_g2_openfoam_fd_run.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class LocalizedG2FdRunner(Protocol):
    """Injectable execution seam used by the real and synthetic runners.

    The runner receives only a newly copied case below the unpublished run
    staging tree.  It must return a mapping (or an object with equivalent
    attributes) containing ``ok``/``success`` and may report command,
    execution identity, convergence, final time, and response provenance.
    """

    def __call__(self, *, phase: str, label: str, case_dir: Path,
                 reference_case_dir: Path | None, adjoint_name: str) -> object: ...


@dataclass(frozen=True)
class LocalizedG2FdRun:
    path: Path
    report_json: Path
    status: str
    execution_status: str
    mode: str
    baseline_repeats: int

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["report_json"] = str(self.report_json)
        return data


def run_localized_g2_openfoam_fd_direction(
    prepared_experiment_path: str | Path,
    *,
    output_dir: str | Path,
    adjoint_name: str,
    baseline_repeats: int = 2,
    execute: bool = False,
    backend: str = "auto",
    docker_image: str | None = None,
    timeout_seconds: int | None = None,
    adjoint_script: str = "AllrunAdjoint",
    runner: LocalizedG2FdRunner | None = None,
) -> LocalizedG2FdRun:
    """Run fresh cases from one immutable prepared FD experiment.

    ``execute=True`` is intentionally mandatory: this command is the only
    boundary that may launch OpenFOAM.  It writes a provenance report for a
    complete or failed execution, but deliberately leaves
    ``validation_status`` as ``not_run``.
    """

    if execute is not True:
        raise ValueError("localized G2 FD runtime is opt-in; pass execute=True explicitly")
    if not isinstance(baseline_repeats, int) or isinstance(baseline_repeats, bool) or baseline_repeats < 2:
        raise ValueError("baseline_repeats must be an integer >= 2")
    if not isinstance(adjoint_name, str) or not _SAFE_NAME.fullmatch(adjoint_name):
        raise ValueError("adjoint_name must be a non-empty safe name")
    if not isinstance(adjoint_script, str) or not _SAFE_NAME.fullmatch(adjoint_script):
        raise ValueError("adjoint_script must be a safe relative script name")
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite localized G2 FD run: {destination}")
    prepared_root, prepared = _verify_prepared_experiment(prepared_experiment_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    execution_runner = runner or _default_runner(
        backend=backend, docker_image=docker_image, timeout_seconds=timeout_seconds, adjoint_script=adjoint_script,
    )

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    attempts: list[dict[str, object]] = []
    failure: dict[str, object] | None = None
    try:
        # Reference copies are independently fresh.  The first one is also the
        # *only* source baseline for the named adjoint, proving the exact alpha
        # and preparation binding instead of accepting an old solver case.
        reference_source = prepared_root / str(_mapping(prepared, "cases")["reference"]["case_relative_path"])
        reference_runs: list[Path] = []
        for index in range(1, baseline_repeats + 1):
            label = f"reference_{index:03d}"
            case = _fresh_copy(reference_source, staging / "primal" / label)
            record = _execute_attempt(
                execution_runner, phase="primal", label=label, case_dir=case,
                reference_case_dir=None, adjoint_name=adjoint_name, staging_root=staging,
            )
            attempts.append(record)
            reference_runs.append(case)
            if record["status"] != "success":
                failure = {"phase": "primal", "label": label, "message": str(record.get("error", "runner failed"))}
                break
        if failure is None:
            adjoint_case = _fresh_copy(reference_runs[0], staging / "adjoint" / adjoint_name / "reference")
            record = _execute_attempt(
                execution_runner, phase="adjoint", label=adjoint_name, case_dir=adjoint_case,
                reference_case_dir=reference_runs[0], adjoint_name=adjoint_name, staging_root=staging,
            )
            record["reference_primal_relative_path"] = str(reference_runs[0].relative_to(staging).as_posix())
            attempts.append(record)
            if record["status"] != "success":
                failure = {"phase": "adjoint", "label": adjoint_name, "message": str(record.get("error", "runner failed"))}
        if failure is None:
            cases = _mapping(prepared, "cases")
            labels = [key for key in cases if key != "reference"]
            # Preparation emits deterministic key ordering, but make ordering
            # explicit: all plus directions, then minus directions, each h..h/4.
            ladder = [float(value) for value in prepared["epsilon_ladder"]]
            labels = [label for sign in ("plus", "minus") for epsilon in ladder
                      for label in [_label(sign, epsilon)] if label in cases]
            for label in labels:
                case = _fresh_copy(prepared_root / str(cases[label]["case_relative_path"]), staging / "primal" / label)
                record = _execute_attempt(
                    execution_runner, phase="primal", label=label, case_dir=case,
                    reference_case_dir=None, adjoint_name=adjoint_name, staging_root=staging,
                )
                attempts.append(record)
                if record["status"] != "success":
                    failure = {"phase": "primal", "label": label, "message": str(record.get("error", "runner failed"))}
                    break
        status = "run_complete" if failure is None else "execution_failed"
        report = {
            "schema_version": LOCALIZED_G2_FD_RUN_SCHEMA_VERSION,
            "kind": LOCALIZED_G2_FD_RUN_KIND,
            "status": status,
            "execution_status": "complete" if failure is None else "failed",
            "validation_status": "not_run",
            "independent_variable": prepared["independent_variable"],
            "raw_chain_rule": prepared["raw_chain_rule"],
            "mode": prepared["mode"],
            "epsilon_ladder": prepared["epsilon_ladder"],
            "baseline_repeats": baseline_repeats,
            "adjoint": {"name": adjoint_name, "script": adjoint_script, "fresh_reference_label": "reference_001"},
            "prepared_experiment": {
                "path": str(prepared_root),
                "report_sha256": _sha256_file(prepared_root / LOCALIZED_G2_FD_PREPARATION_FILENAME),
                "provenance": prepared["provenance"],
                "case_manifest_sha256": {key: value["case_manifest_sha256"] for key, value in _mapping(prepared, "cases").items()},
            },
            "attempts": attempts,
            "failure": failure,
            "limitations": [
                "run_records_execution_only_and_does_not_select_an_fd_step",
                "run_does_not_compute_an_fd_derivative_or_adjoint_comparison",
                "validation_status_remains_not_run",
            ],
        }
        _write_json(staging / LOCALIZED_G2_FD_RUN_FILENAME, report)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalizedG2FdRun(
        path=destination, report_json=destination / LOCALIZED_G2_FD_RUN_FILENAME,
        status=status, execution_status=str(report["execution_status"]), mode=str(prepared["mode"]),
        baseline_repeats=baseline_repeats,
    )


def _verify_prepared_experiment(path: str | Path) -> tuple[Path, Mapping[str, object]]:
    root = Path(path).resolve()
    report_path = root / LOCALIZED_G2_FD_PREPARATION_FILENAME
    report = _read_json(report_path)
    if (report.get("schema_version") != LOCALIZED_G2_FD_PREPARATION_SCHEMA_VERSION
            or report.get("kind") != LOCALIZED_G2_FD_PREPARATION_KIND
            or report.get("status") not in {"prepared_one_sided", "prepared_central"}
            or report.get("execution_status") != "not_run" or report.get("validation_status") != "not_run"):
        raise ValueError("prepared experiment has an unsupported or already-executed contract")
    if report.get("independent_variable") != "rho_raw" or report.get("raw_chain_rule") != "rho_raw -> active_cone_filter -> tanh_heaviside_projection -> E -> alpha":
        raise ValueError("prepared experiment must use the declared localized raw-density alpha chain")
    if report.get("mode") not in {"one_sided", "central"}:
        raise ValueError("prepared experiment mode is invalid")
    ladder = report.get("epsilon_ladder")
    if not isinstance(ladder, list) or len(ladder) != 3 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 for value in ladder):
        raise ValueError("prepared experiment epsilon ladder is invalid")
    if [float(ladder[1]), float(ladder[2])] != [float(ladder[0]) / 2.0, float(ladder[0]) / 4.0]:
        raise ValueError("prepared experiment epsilon ladder is not h,h/2,h/4")
    provenance = _mapping(report, "provenance")
    for key in ("reference_bundle_ledger_sha256", "reference_state_manifest_sha256", "reference_rho_projected_sha256", "alpha_reference_binding_sha256", "prepared_direction_npy_sha256"):
        value = provenance.get(key)
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise ValueError(f"prepared experiment provenance {key} is invalid")
    _verify_external_preparation_provenance(root, provenance)
    cases = _mapping(report, "cases")
    expected = {"reference"} | {_label("plus", float(item)) for item in ladder}
    if report["mode"] == "central":
        expected |= {_label("minus", float(item)) for item in ladder}
    if set(cases) != expected:
        raise ValueError("prepared experiment does not contain exactly the declared staged FD cases")
    reference_hash: str | None = None
    for label, raw_case in cases.items():
        if not isinstance(raw_case, Mapping):
            raise ValueError(f"prepared case {label} is invalid")
        relative = raw_case.get("case_relative_path")
        manifest_sha = raw_case.get("case_manifest_sha256")
        alpha_sha = raw_case.get("alpha_values_sha256")
        if not isinstance(relative, str) or not isinstance(manifest_sha, str) or not isinstance(alpha_sha, str):
            raise ValueError(f"prepared case {label} provenance is incomplete")
        case = (root / relative).resolve()
        _require_descendant(case, root, "prepared case escapes prepared experiment")
        artifact = validate_localized_openfoam_alpha_case(case)
        if _sha256_file(artifact.manifest_json) != manifest_sha or artifact.alpha_values_sha256 != alpha_sha:
            raise ValueError(f"prepared case {label} was modified after preparation")
        manifest = _read_json(artifact.manifest_json)
        source = _mapping(manifest, "alpha_source")
        if source.get("binding_sha256") != provenance["alpha_reference_binding_sha256"]:
            raise ValueError(f"prepared case {label} alpha binding differs from prepared experiment")
        state_sha = source.get("current_state_manifest_sha256")
        if not isinstance(state_sha, str) or _SHA256.fullmatch(state_sha) is None:
            raise ValueError(f"prepared case {label} has invalid current-state provenance")
        if label == "reference":
            if state_sha != provenance["reference_state_manifest_sha256"]:
                raise ValueError("prepared reference case is not bound to the exact reference state")
            reference_hash = artifact.alpha_values_sha256
        else:
            if raw_case.get("state_manifest_sha256") != state_sha:
                raise ValueError(f"prepared perturbation {label} state provenance does not match its alpha case")
            if raw_case.get("alpha_values_sha256") == reference_hash:
                # This is allowed mathematically for an E-null direction, but
                # the runtime must not use it as a replacement baseline.  The
                # distinct staged label remains the authoritative provenance.
                pass
    if reference_hash is None:
        raise ValueError("prepared experiment reference case is missing")
    return root, report


def _verify_external_preparation_provenance(root: Path, provenance: Mapping[str, object]) -> None:
    """Recheck every non-copied provenance input before any solver copy exists."""
    direction = root / "direction.npy"
    if _sha256_file(direction) != provenance["prepared_direction_npy_sha256"]:
        raise ValueError("prepared experiment direction.npy hash mismatch")
    topology_path = Path(str(provenance.get("topology_report_path", ""))).resolve()
    if _sha256_file(topology_path) != provenance.get("topology_report_sha256"):
        raise ValueError("prepared experiment topology report hash mismatch")
    bundle = Path(str(provenance.get("reference_bundle_path", ""))).resolve()
    if _sha256_file(bundle / LOCALIZED_REFERENCE_STATE_FILENAME) != provenance["reference_bundle_ledger_sha256"]:
        raise ValueError("prepared experiment reference-bundle ledger hash mismatch")
    binding_path = Path(str(provenance.get("alpha_reference_binding_path", ""))).resolve()
    binding = load_and_verify_localized_alpha_reference_binding(binding_path)
    if binding.binding.sha256 != provenance["alpha_reference_binding_sha256"]:
        raise ValueError("prepared experiment alpha-reference binding hash mismatch")
    if localized_design_state_manifest_sha256(binding.reference_state.manifest) != provenance["reference_state_manifest_sha256"]:
        raise ValueError("prepared experiment alpha reference state binding mismatch")
    if binding.reference_state.manifest.states["rho_projected"].byte_sha256 != provenance["reference_rho_projected_sha256"]:
        raise ValueError("prepared experiment alpha reference projected state mismatch")


def _fresh_copy(source: Path, destination: Path) -> Path:
    if destination.exists():
        raise FileExistsError(f"fresh runtime case already exists: {destination}")
    _require_descendant(destination, destination.parents[2], "runtime destination escapes staging tree")
    shutil.copytree(source, destination)
    # Recheck after copying.  This catches platform-level copying changes and
    # proves no previous run output was the input to a different case.
    validate_localized_openfoam_alpha_case(destination)
    return destination


def _execute_attempt(runner: LocalizedG2FdRunner, *, phase: str, label: str, case_dir: Path,
                     reference_case_dir: Path | None, adjoint_name: str, staging_root: Path) -> dict[str, object]:
    input_hash = _sha256_tree(case_dir)
    started_ns = time.time_ns()
    try:
        raw = runner(phase=phase, label=label, case_dir=case_dir, reference_case_dir=reference_case_dir, adjoint_name=adjoint_name)
        normalized = _normalize_runner_result(raw)
    except Exception as exc:  # publish the execution failure as evidence
        normalized = {
            "ok": False, "command": [], "backend": "runner_exception",
            "execution_identity": {"runner": "exception", "openfoam_version": "not_available"},
            "convergence": {"status": "not_reported_due_to_runner_exception"},
            "final_time": "not_reported_due_to_runner_exception",
            "response_provenance": {"status": "not_reported_due_to_runner_exception"},
            "error": f"runner raised {type(exc).__name__}: {exc}",
        }
    ended_ns = time.time_ns()
    output_hash = _sha256_tree(case_dir)
    status = "success" if normalized["ok"] is True else "failed"
    return {
        "phase": phase,
        "label": label,
        "status": status,
        "case_relative_path": str(case_dir.relative_to(staging_root).as_posix()),
        "case_input_tree_sha256": input_hash,
        "case_output_tree_sha256": output_hash,
        "started_at_unix_ns": started_ns,
        "ended_at_unix_ns": ended_ns,
        "command": normalized["command"],
        "backend": normalized["backend"],
        "execution_identity": normalized["execution_identity"],
        "convergence": normalized["convergence"],
        "final_time": normalized["final_time"],
        "response_provenance": normalized["response_provenance"],
        "error": normalized["error"],
    }


def _normalize_runner_result(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        raw: Mapping[str, object] = value
    else:
        raw = {name: getattr(value, name) for name in (
            "ok", "success", "command", "backend", "execution_identity", "convergence", "final_time",
            "response_provenance", "error", "docker_image", "returncode", "timed_out", "dry_run",
        ) if hasattr(value, name)}
    ok = raw.get("ok", raw.get("success"))
    if not isinstance(ok, bool):
        raise ValueError("runner result must provide boolean ok or success")
    command = raw.get("command", [])
    if not isinstance(command, (list, tuple)) or not all(isinstance(item, str) for item in command):
        raise ValueError("runner command must be a list of strings")
    backend = raw.get("backend", "declared_by_runner")
    if not isinstance(backend, str) or not backend:
        raise ValueError("runner backend must be a non-empty string")
    identity = raw.get("execution_identity")
    if identity is None:
        identity = {
            "backend": backend, "container_image": raw.get("docker_image"),
            "openfoam_version": "not_reported_by_runner", "runner": "injected",
        }
    if not isinstance(identity, Mapping):
        raise ValueError("runner execution_identity must be an object")
    identity = dict(identity)
    identity.setdefault("runner", "injected")
    identity.setdefault("backend", backend)
    identity.setdefault("container_image", raw.get("docker_image"))
    identity.setdefault("openfoam_version", "not_reported_by_runner")
    convergence = raw.get("convergence", {"status": "not_reported_by_runner"})
    response = raw.get("response_provenance", {"status": "not_reported_by_runner"})
    if not isinstance(convergence, Mapping) or not isinstance(response, Mapping):
        raise ValueError("runner convergence and response_provenance must be objects")
    final_time = raw.get("final_time", "not_reported_by_runner")
    if not isinstance(final_time, (str, int, float)) or isinstance(final_time, bool):
        raise ValueError("runner final_time must be a scalar or declared status string")
    error = raw.get("error")
    if error is not None and not isinstance(error, str):
        raise ValueError("runner error must be a string or null")
    return {"ok": ok, "command": list(command), "backend": backend, "execution_identity": identity,
            "convergence": dict(convergence), "final_time": final_time, "response_provenance": dict(response), "error": error}


def _default_runner(*, backend: str, docker_image: str | None, timeout_seconds: int | None,
                    adjoint_script: str) -> LocalizedG2FdRunner:
    selected_backend = _select_backend(backend)
    image = docker_image or os.environ.get("CFD_SDF_OPENFOAM_IMAGE", DEFAULT_OPENFOAM_DOCKER_IMAGE)

    def execute(*, phase: str, label: str, case_dir: Path, reference_case_dir: Path | None,
                adjoint_name: str) -> object:
        if phase == "primal":
            result = run_openfoam_case(case_dir, backend=selected_backend, dry_run=False, timeout_seconds=timeout_seconds, docker_image=image)
            return {
                "ok": result.ok, "command": result.command, "backend": result.backend,
                "execution_identity": _runtime_identity(result.backend, result.docker_image),
                "convergence": _convergence_from_case(case_dir, ok=result.ok), "final_time": _final_time(case_dir),
                "response_provenance": _response_provenance(case_dir), "error": result.error,
            }
        if phase != "adjoint":
            raise ValueError(f"unsupported FD runner phase: {phase}")
        script = case_dir / adjoint_script
        if not script.is_file():
            raise FileNotFoundError(f"named localized FD adjoint script is missing: {script}")
        command = _adjoint_command(selected_backend, case_dir, image, adjoint_script)
        completed = subprocess.run(command, cwd=case_dir, timeout=timeout_seconds, check=False, capture_output=True, text=True)
        stdout = case_dir / "log.localizedG2Adjoint.stdout"; stderr = case_dir / "log.localizedG2Adjoint.stderr"
        stdout.write_text(completed.stdout, encoding="utf-8"); stderr.write_text(completed.stderr, encoding="utf-8")
        ok = completed.returncode == 0
        return {"ok": ok, "command": command, "backend": selected_backend, "execution_identity": _runtime_identity(selected_backend, image if selected_backend == "docker" else None),
                "convergence": _convergence_from_case(case_dir, ok=ok), "final_time": _final_time(case_dir),
                "response_provenance": _response_provenance(case_dir), "error": None if ok else f"adjoint return code {completed.returncode}"}
    return execute


def _adjoint_command(backend: str, case_dir: Path, docker_image: str, script: str) -> list[str]:
    shell = f"chmod +x {script} && ./{script}"
    if backend == "local":
        return ["bash", "-lc", shell]
    if backend == "wsl":
        bridge = 'case_dir="$(wslpath -a "$1")" && cd "$case_dir" && ' + shell
        return ["wsl", "bash", "-lc", bridge, "bash", str(case_dir)]
    if backend == "docker":
        return ["docker", "run", "--rm", "--entrypoint", "bash", "--mount",
                f"type=bind,source={case_dir},target=/case", "-w", "/case", docker_image, "-lc", shell]
    raise ValueError(f"unsupported named-adjoint backend: {backend}")


def _runtime_identity(backend: str, docker_image: str | None) -> dict[str, object]:
    return {"runner": "cfd_sdf.localized_g2_fd_runner.default", "backend": backend,
            "container_image": docker_image if backend == "docker" else None,
            "openfoam_version": "not_queried_by_runner", "host_platform": platform.platform(),
            "declared_default_image": DEFAULT_OPENFOAM_DOCKER_IMAGE if backend == "docker" else None}


def _convergence_from_case(case_dir: Path, *, ok: bool) -> dict[str, object]:
    summary = case_dir / "openfoam_run_summary.json"
    if summary.is_file():
        return {"status": "runner_completed" if ok else "runner_failed", "summary_sha256": _sha256_file(summary)}
    return {"status": "not_reported_by_solver", "runner_ok": ok}


def _final_time(case_dir: Path) -> str | float:
    values: list[float] = []
    for child in case_dir.iterdir():
        if child.is_dir():
            try:
                values.append(float(child.name))
            except ValueError:
                pass
    return max(values) if values else "not_reported_by_solver"


def _response_provenance(case_dir: Path) -> dict[str, object]:
    candidate = case_dir / "optimisation" / "objective"
    if not candidate.is_dir():
        return {"status": "response_output_not_found"}
    return {"status": "output_present_not_interpreted", "objective_tree_sha256": _sha256_tree(candidate)}


def _sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        if item.is_symlink():
            raise ValueError(f"symlinks are forbidden in localized FD case evidence: {item}")
        if item.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif item.is_file():
            digest.update(b"F\0" + relative + b"\0")
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            raise ValueError(f"unsupported localized FD evidence entry: {item}")
    return digest.hexdigest()


def _label(sign: str, epsilon: float) -> str:
    return f"{sign}_h{epsilon:.17g}".replace("+", "p").replace("-", "m")


def _read_json(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(result, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return result


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{key} must be an object")
    return result


def _require_descendant(path: Path, parent: Path, message: str) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError as exc:
        raise ValueError(message) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


__all__ = [
    "LOCALIZED_G2_FD_RUN_FILENAME", "LOCALIZED_G2_FD_RUN_KIND", "LOCALIZED_G2_FD_RUN_SCHEMA_VERSION",
    "LocalizedG2FdRun", "LocalizedG2FdRunner", "run_localized_g2_openfoam_fd_direction",
]
