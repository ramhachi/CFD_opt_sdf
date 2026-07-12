"""Produce explicit, patch-flux based normalized mass-imbalance evidence.

This module deliberately does not inspect OpenFOAM solver logs.  The
``surfaceFieldValue`` function objects measure the solved ``phi`` field on the
open boundaries, and the resulting JSON is the only source consumed by the
convergence-evidence extractor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
from typing import Any

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE


NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME = "cfd_sdf_normalized_mass_imbalance.json"
MASS_IMBALANCE_FUNCTION_DICT_RELATIVE = "system/cfdSdfMassImbalanceDict"
MASS_IMBALANCE_SCHEMA_VERSION = 1
MASS_IMBALANCE_EPSILON = 1.0e-30
MASS_IMBALANCE_FORMULA = "abs(sum signed flux)/max(sum abs(flux)/2, epsilon)"
_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_PROCESSOR_PATTERN = re.compile(r"^processor([0-9]+)$")


def mass_imbalance_open_patch_ids(boundary_conditions: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the only patch kinds whose signed flow belongs in the balance."""

    if not isinstance(boundary_conditions, Mapping):
        raise ValueError("generated.boundary_conditions must be a mapping")
    patches: list[str] = []
    for patch_id, specification in boundary_conditions.items():
        if not isinstance(patch_id, str) or not _ID_PATTERN.fullmatch(patch_id):
            raise ValueError(f"Invalid OpenFOAM patch id: {patch_id!r}")
        if not isinstance(specification, Mapping):
            raise ValueError(f"Invalid generated boundary specification: {patch_id}")
        kind = specification.get("kind")
        # The renderer's generated form has no kind; its caller supplies the
        # requested kinds as a fallback.  Supporting kind here keeps this pure
        # helper useful for the persisted contract and tests.
        if kind in {"freestream", "pressure_outlet"}:
            patches.append(patch_id)
    return tuple(sorted(patches))


def render_openfoam_mass_imbalance_function_dict(open_patch_ids: Sequence[str]) -> str:
    """Render a deterministic ``postProcess`` dictionary for ``phi`` fluxes."""

    patches = _normalize_open_patch_ids(open_patch_ids)
    if not patches:
        raise ValueError("Normalized mass imbalance requires at least one open patch")
    entries: list[str] = []
    for index, patch in enumerate(patches):
        entries.append(_surface_field_value_entry(f"cfdSdfMassSigned{index}", patch, "sum"))
        entries.append(_surface_field_value_entry(f"cfdSdfMassMagnitude{index}", patch, "sumMag"))
    return (
        "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
        "    class       dictionary;\n    object      cfdSdfMassImbalanceDict;\n}\n\n"
        "application     postProcess;\n\nfunctions\n{\n"
        + "\n".join(entries)
        + "}\n"
    )


def normalized_mass_imbalance_contract(open_patch_ids: Sequence[str]) -> dict[str, Any]:
    """Return JSON-safe renderer metadata defining the producer contract."""

    patches = _normalize_open_patch_ids(open_patch_ids)
    return {
        "artifact_name": NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME,
        "function_dict": MASS_IMBALANCE_FUNCTION_DICT_RELATIVE,
        "function_object_prefix": "cfdSdfMass",
        "open_patch_ids": list(patches),
        "formula": MASS_IMBALANCE_FORMULA,
        "epsilon": MASS_IMBALANCE_EPSILON,
    }


def produce_openfoam_normalized_mass_imbalance(
    case_dir: str | Path,
    *,
    backend: str = "auto",
    docker_image: str | None = None,
    timeout_seconds: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Run deterministic ``postProcess`` flux measurements and write JSON.

    Existing evidence is never silently replaced.  Callers should run this
    only after the primal/adjoint case has produced a time directory.
    """

    target = Path(case_dir).resolve()
    contract, physics_sha256 = _load_contract(target)
    output = target / NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME
    if output.exists() and not overwrite:
        raise FileExistsError(f"Mass-imbalance artifact already exists; use overwrite=True: {output}")

    selected_backend = _select_backend(backend)
    image = docker_image or os.environ.get("CFD_SDF_OPENFOAM_IMAGE", DEFAULT_OPENFOAM_DOCKER_IMAGE)
    processor_count = _processor_count(target)
    command = _postprocess_command(selected_backend, target, image, processor_count)
    stdout_path = target / "log.cfdSdfMassImbalance.stdout"
    stderr_path = target / "log.cfdSdfMassImbalance.stderr"
    started_at = time.time_ns()
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(command, cwd=target, stdout=stdout, stderr=stderr, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"OpenFOAM mass-imbalance postProcess timed out after {exc.timeout} seconds") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start OpenFOAM mass-imbalance postProcess: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"OpenFOAM mass-imbalance postProcess failed with exit code {completed.returncode}; see {stderr_path.name}")

    rows = _read_function_measurements(target, contract["open_patch_ids"])
    artifact = {
        "schema_version": MASS_IMBALANCE_SCHEMA_VERSION,
        "kind": "openfoam_normalized_mass_imbalance",
        "flow_case_id": contract["flow_case_id"],
        "open_patch_ids": contract["open_patch_ids"],
        "epsilon": MASS_IMBALANCE_EPSILON,
        "formula": MASS_IMBALANCE_FORMULA,
        "measurements": rows,
        "sources": {
            "generated_openfoam_physics_sha256": physics_sha256,
            "function_dict": MASS_IMBALANCE_FUNCTION_DICT_RELATIVE,
            "postprocess_backend": selected_backend,
            "postprocess_command": command,
            "postprocess_started_at_ns": started_at,
        },
    }
    _write_json(output, artifact)
    return artifact


def validate_normalized_mass_imbalance_artifact(
    raw: Any,
    *,
    expected_flow_case_id: str | None = None,
    expected_open_patch_ids: Sequence[str] | None = None,
) -> list[float]:
    """Fail closed and return the usable normalized-mass history."""

    if not isinstance(raw, Mapping) or raw.get("schema_version") != MASS_IMBALANCE_SCHEMA_VERSION:
        raise ValueError("unsupported normalized mass-imbalance artifact schema")
    if raw.get("kind") != "openfoam_normalized_mass_imbalance":
        raise ValueError("invalid normalized mass-imbalance artifact kind")
    if expected_flow_case_id is not None and raw.get("flow_case_id") != expected_flow_case_id:
        raise ValueError("normalized mass-imbalance flow_case_id does not match physics metadata")
    patches = _normalize_open_patch_ids(raw.get("open_patch_ids", ()))
    if expected_open_patch_ids is not None and patches != _normalize_open_patch_ids(expected_open_patch_ids):
        raise ValueError("normalized mass-imbalance patch set does not match physics metadata")
    epsilon = _finite_positive(raw.get("epsilon"))
    if epsilon is None or not math.isclose(epsilon, MASS_IMBALANCE_EPSILON, rel_tol=0.0, abs_tol=0.0):
        raise ValueError("invalid normalized mass-imbalance epsilon")
    if raw.get("formula") != MASS_IMBALANCE_FORMULA:
        raise ValueError("unsupported normalized mass-imbalance formula")
    measurements = raw.get("measurements")
    if not isinstance(measurements, Sequence) or isinstance(measurements, (str, bytes)) or not measurements:
        raise ValueError("missing normalized mass-imbalance measurements")
    history: list[float] = []
    last_time = -math.inf
    for measurement in measurements:
        if not isinstance(measurement, Mapping):
            raise ValueError("invalid normalized mass-imbalance measurement")
        moment = _finite_number(measurement.get("time"))
        if moment is None or moment <= last_time:
            raise ValueError("normalized mass-imbalance measurement times must be finite and increasing")
        last_time = moment
        signed = _finite_patch_values(measurement.get("signed_flux_by_patch"), patches)
        absolute = _finite_patch_values(measurement.get("absolute_flux_by_patch"), patches)
        if any(value < 0.0 for value in absolute.values()):
            raise ValueError("absolute patch flux must be non-negative")
        computed = _measurement(signed, absolute, moment)
        for key in ("net_signed_flux", "absolute_flux_sum", "throughput", "denominator", "normalized_mass_imbalance"):
            observed = _finite_number(measurement.get(key))
            if observed is None or not math.isclose(observed, computed[key], rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"invalid normalized mass-imbalance measurement field: {key}")
        history.append(computed["normalized_mass_imbalance"])
    return history


def _surface_field_value_entry(name: str, patch: str, operation: str) -> str:
    return (
        f"    {name}\n    {{\n        type            surfaceFieldValue;\n"
        "        libs            (fieldFunctionObjects);\n        writeControl    writeTime;\n"
        "        log             false;\n        writeFields     false;\n        regionType      patch;\n"
        f"        name            {patch};\n        operation       {operation};\n        fields          (phi);\n    }}\n"
    )


def _normalize_open_patch_ids(values: Sequence[str] | Any) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("open_patch_ids must be a sequence")
    patches = tuple(str(value) for value in values)
    if not patches or len(set(patches)) != len(patches) or any(not _ID_PATTERN.fullmatch(value) for value in patches):
        raise ValueError("open_patch_ids must be unique valid OpenFOAM patch ids")
    return tuple(sorted(patches))


def _load_contract(case_dir: Path) -> tuple[dict[str, Any], str]:
    path = case_dir / "generated_openfoam_physics.json"
    try:
        payload = path.read_bytes()
        raw = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read generated OpenFOAM physics metadata: {path}") from exc
    if not isinstance(raw, Mapping) or raw.get("kind") != "generated_openfoam_physics":
        raise ValueError("Invalid generated OpenFOAM physics metadata")
    contract = raw.get("normalized_mass_imbalance")
    if not isinstance(contract, Mapping):
        raise ValueError("Physics metadata has no normalized mass-imbalance contract")
    flow_case_id = raw.get("flow_case_id")
    if not isinstance(flow_case_id, str) or not flow_case_id:
        raise ValueError("Physics metadata has invalid flow_case_id")
    if contract.get("artifact_name") != NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME or contract.get("function_dict") != MASS_IMBALANCE_FUNCTION_DICT_RELATIVE:
        raise ValueError("Physics metadata has an unsupported mass-imbalance contract")
    if contract.get("formula") != MASS_IMBALANCE_FORMULA or contract.get("epsilon") != MASS_IMBALANCE_EPSILON:
        raise ValueError("Physics metadata has an unsupported mass-imbalance formula")
    return {"flow_case_id": flow_case_id, "open_patch_ids": list(_normalize_open_patch_ids(contract.get("open_patch_ids", ())))}, hashlib.sha256(payload).hexdigest()


def _processor_count(case_dir: Path) -> int:
    indices = sorted(int(match.group(1)) for path in case_dir.iterdir() if (match := _PROCESSOR_PATTERN.fullmatch(path.name)) and path.is_dir())
    if not indices:
        return 1
    if indices != list(range(len(indices))):
        raise ValueError("OpenFOAM processor directories must be contiguous from processor0")
    return len(indices)


def _select_backend(backend: str) -> str:
    selected = backend.lower()
    if selected not in {"auto", "local", "wsl", "docker"}:
        raise ValueError(f"Unsupported OpenFOAM backend: {backend}")
    if selected != "auto":
        return selected
    if shutil.which("postProcess"):
        return "local"
    if platform.system().lower().startswith("win") and shutil.which("wsl") and _wsl_has_postprocess():
        return "wsl"
    if shutil.which("docker") and _docker_is_ready():
        return "docker"
    return "local"


def _wsl_has_postprocess() -> bool:
    return _command_succeeds(["wsl", "bash", "-lc", "command -v postProcess >/dev/null"])


def _docker_is_ready() -> bool:
    return _command_succeeds(["docker", "info", "--format", "{{.ServerVersion}}"])


def _command_succeeds(command: Sequence[str]) -> bool:
    try:
        completed = subprocess.run(
            list(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _postprocess_command(backend: str, case_dir: Path, image: str, processors: int) -> list[str]:
    command = "postProcess -latestTime -field phi -dict system/cfdSdfMassImbalanceDict"
    if processors > 1:
        command = f"mpirun -np {processors} {command} -parallel"
    if backend == "local":
        return ["bash", "-lc", command]
    if backend == "wsl":
        script = 'case_dir="$(wslpath -a "$1")" && cd "$case_dir" && ' + command
        return ["wsl", "bash", "-lc", script, "bash", str(case_dir)]
    if backend == "docker":
        prefix = "export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1; " if processors > 1 else ""
        return ["docker", "run", "--rm", "--entrypoint", "bash", "--mount", f"type=bind,source={case_dir},target=/case", "-w", "/case", image, "-lc", prefix + command]
    raise ValueError(f"Unsupported OpenFOAM backend: {backend}")


def _read_function_measurements(case_dir: Path, patches: Sequence[str]) -> list[dict[str, Any]]:
    values: dict[str, dict[float, float]] = {}
    for index, patch in enumerate(patches):
        values[f"signed:{patch}"] = _read_surface_field_values(case_dir, f"cfdSdfMassSigned{index}")
        values[f"absolute:{patch}"] = _read_surface_field_values(case_dir, f"cfdSdfMassMagnitude{index}")
    times = set.intersection(*(set(item) for item in values.values())) if values else set()
    if not times or any(set(item) != times for item in values.values()):
        raise ValueError("Mass-imbalance function-object outputs have inconsistent time series")
    return [_measurement({patch: values[f"signed:{patch}"][moment] for patch in patches}, {patch: values[f"absolute:{patch}"][moment] for patch in patches}, moment) for moment in sorted(times)]


def _read_surface_field_values(case_dir: Path, function_name: str) -> dict[float, float]:
    directory = case_dir / "postProcessing" / function_name
    # OpenFOAM v2512 puts parallel output in a time subdirectory, whereas
    # some serial versions write directly below the function-object directory.
    paths = sorted(directory.rglob("surfaceFieldValue*.dat"))
    if not paths:
        raise ValueError(f"Missing mass-imbalance function output: {function_name}")
    values: dict[float, float] = {}
    for path in paths:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            columns = line.split()
            if len(columns) < 2:
                continue
            moment, value = _finite_number(columns[0]), _finite_number(columns[1])
            if moment is None or value is None:
                raise ValueError(f"Invalid mass-imbalance function row: {path}")
            if moment in values:
                if not math.isclose(values[moment], value, rel_tol=1e-12, abs_tol=1e-15):
                    raise ValueError(f"Conflicting mass-imbalance function rows: {path}")
                continue
            values[moment] = value
    if not values:
        raise ValueError(f"No mass-imbalance measurements found: {function_name}")
    return values


def _measurement(signed: Mapping[str, float], absolute: Mapping[str, float], moment: float) -> dict[str, Any]:
    net = math.fsum(signed.values())
    absolute_sum = math.fsum(absolute.values())
    throughput = absolute_sum / 2.0
    denominator = max(throughput, MASS_IMBALANCE_EPSILON)
    return {"time": moment, "signed_flux_by_patch": dict(signed), "absolute_flux_by_patch": dict(absolute), "net_signed_flux": net, "absolute_flux_sum": absolute_sum, "throughput": throughput, "denominator": denominator, "normalized_mass_imbalance": abs(net) / denominator}


def _finite_patch_values(raw: Any, patches: Sequence[str]) -> dict[str, float]:
    if not isinstance(raw, Mapping) or set(raw) != set(patches):
        raise ValueError("mass-imbalance patch measurement keys do not match contract")
    result = {patch: _finite_number(raw[patch]) for patch in patches}
    if any(value is None for value in result.values()):
        raise ValueError("mass-imbalance patch measurement is not finite")
    return {patch: float(value) for patch, value in result.items()}


def _finite_number(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _finite_positive(value: Any) -> float | None:
    converted = _finite_number(value)
    return converted if converted is not None and converted > 0.0 else None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False), encoding="utf-8", newline="\n")


__all__ = [
    "MASS_IMBALANCE_EPSILON",
    "MASS_IMBALANCE_FORMULA",
    "MASS_IMBALANCE_FUNCTION_DICT_RELATIVE",
    "MASS_IMBALANCE_SCHEMA_VERSION",
    "NORMALIZED_MASS_IMBALANCE_ARTIFACT_NAME",
    "normalized_mass_imbalance_contract",
    "produce_openfoam_normalized_mass_imbalance",
    "render_openfoam_mass_imbalance_function_dict",
    "validate_normalized_mass_imbalance_artifact",
]
