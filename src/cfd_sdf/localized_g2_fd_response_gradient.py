"""Extract immutable raw-``alpha`` response/gradient evidence from a G2 FD run.

This is deliberately *not* the localized FD validator.  It reads a completed,
hash-verified runtime evidence directory through an explicit compiler contract,
copies the named-adjoint ``dJ_dalpha`` vector into a new immutable artifact,
and records the scalar response values used by the later validator.  In
particular it does not apply ``E.T``, projection, filtering, or any numerical
acceptance rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

import numpy as np

from .localized_g2_fd_preparation import LOCALIZED_G2_FD_PREPARATION_FILENAME
from .localized_g2_fd_runner import LOCALIZED_G2_FD_RUN_FILENAME, _verify_prepared_experiment
from .localized_g2_fd_validation import _verified_attempts, _verify_run_report
from .localized_openfoam_alpha_case import validate_localized_openfoam_alpha_case
from .openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from .openfoam_grid_transfer import CANONICAL_CELL_ORDER


LOCALIZED_G2_FD_RESPONSE_GRADIENT_SCHEMA_VERSION = 1
LOCALIZED_G2_FD_RESPONSE_GRADIENT_KIND = "localized_g2_openfoam_fd_response_gradient"
LOCALIZED_G2_FD_RESPONSE_GRADIENT_FILENAME = "localized_g2_openfoam_fd_response_gradient.json"
LOCALIZED_G2_FD_RESPONSE_GRADIENT_ARRAY_FILENAME = "dJ_dalpha.npy"
LOCALIZED_G2_FD_RESPONSE_GRADIENT_CONTRACT_KIND = "localized_g2_openfoam_response_gradient_contract"
LOCALIZED_G2_FD_RESPONSE_GRADIENT_CONTRACT_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class LocalizedG2FdResponseGradient:
    path: Path
    report_json: Path
    gradient_npy: Path
    flow_case_id: str
    response_id: str
    adjoint_name: str
    cfd_cell_count: int

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("path", "report_json", "gradient_npy"):
            data[key] = str(data[key])
        return data


def extract_localized_g2_fd_response_gradient(
    prepared_experiment_path: str | Path,
    run_report_path: str | Path,
    response_gradient_contract_path: str | Path,
    *,
    flow_case_id: str,
    response_id: str,
    adjoint_name: str,
    output_dir: str | Path,
) -> LocalizedG2FdResponseGradient:
    """Publish strict response and ``dJ/d(raw_alpha)`` evidence.

    The compiler contract is intentionally narrow: response values are a
    single finite JSON scalar selected by an RFC-6901 JSON pointer, and the
    adjoint field is either one native ``float64`` NPY in canonical order or
    explicit processor shards with declared global labels.  Guessing an
    objective filename, a ``topologySens`` field, a time directory, or a
    decomposed ordering is forbidden.
    """

    _require_identifier(flow_case_id, "flow_case_id")
    _require_identifier(response_id, "response_id")
    _require_identifier(adjoint_name, "adjoint_name")
    prepared_root, prepared = _verify_prepared_experiment(prepared_experiment_path)
    run_root, run = _verify_run_report(run_report_path, prepared_root, prepared)
    if run.get("execution_status") != "complete":
        raise ValueError("response/gradient extraction requires a completed localized G2 FD run")
    contract_path, contract = _read_contract(response_gradient_contract_path)
    _validate_contract_identity(
        contract, flow_case_id=flow_case_id, response_id=response_id, adjoint_name=adjoint_name,
    )
    if _mapping(run, "adjoint").get("name") != adjoint_name:
        raise ValueError("completed run named adjoint does not match the requested extraction")
    attempts = _verified_attempts(run_root, run, prepared)
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite localized G2 FD response/gradient artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        baseline_time = _time_token(attempts["reference_001"].get("final_time"), "reference baseline")
        primal_labels = [label for label in attempts if label != "adjoint"]
        responses: list[dict[str, object]] = []
        common_case_contract: dict[str, object] | None = None
        for label in primal_labels:
            attempt = attempts[label]
            _require_attempt_response_identity(attempt, flow_case_id, response_id, label)
            time_token = _time_token(attempt.get("final_time"), f"attempt {label}")
            if time_token != baseline_time:
                raise ValueError(f"attempt {label} final_time does not match the reference baseline")
            record = _verify_case_contract(
                run_root, attempt, contract, label=label,
            )
            common_case_contract = _require_same_case_contract(common_case_contract, record, label)
            source = _resolve_source(record["case"], _mapping(_mapping(contract, "primal_response"), "source"), time_token, "primal response")
            value = _read_json_scalar(source, str(_mapping(_mapping(contract, "primal_response"), "source")["json_pointer"]))
            responses.append({
                "label": label,
                "value": value,
                "units": _mapping(contract, "primal_response")["units"],
                "scale": _mapping(contract, "primal_response")["scale"],
                "final_time": time_token,
                "source": {"relative_path": str(source.relative_to(record["case"]).as_posix()), "sha256": _sha256_file(source)},
                "case": _case_record(attempt, record),
            })

        adjoint_attempt = attempts["adjoint"]
        _require_attempt_response_identity(adjoint_attempt, flow_case_id, response_id, "adjoint")
        adjoint_time = _time_token(adjoint_attempt.get("final_time"), "named adjoint")
        if adjoint_time != baseline_time:
            raise ValueError("named adjoint final_time does not match the reference baseline")
        adjoint_case = _verify_case_contract(run_root, adjoint_attempt, contract, label="adjoint")
        common_case_contract = _require_same_case_contract(common_case_contract, adjoint_case, "adjoint")
        gradient, gradient_sources = _read_gradient(adjoint_case["case"], _mapping(contract, "adjoint_gradient"), adjoint_time, int(common_case_contract["cfd_cell_count"]))
        if gradient.dtype != np.dtype(np.float64) or not gradient.dtype.isnative or gradient.ndim != 1 or not np.isfinite(gradient).all():
            raise ValueError("named adjoint dJ_dalpha must be a finite native float64 vector")
        gradient_path = staging / LOCALIZED_G2_FD_RESPONSE_GRADIENT_ARRAY_FILENAME
        np.save(gradient_path, gradient, allow_pickle=False)
        if _sha256_array(gradient) != _sha256_array(np.load(gradient_path, allow_pickle=False)):
            raise ValueError("published dJ_dalpha readback hash mismatch")
        report = {
            "schema_version": LOCALIZED_G2_FD_RESPONSE_GRADIENT_SCHEMA_VERSION,
            "kind": LOCALIZED_G2_FD_RESPONSE_GRADIENT_KIND,
            "status": "extracted",
            "flow_case_id": flow_case_id,
            "response_id": response_id,
            "named_adjoint_id": adjoint_name,
            "prepared_experiment": {
                "path": str(prepared_root),
                "sha256": _sha256_file(prepared_root / LOCALIZED_G2_FD_PREPARATION_FILENAME),
                "provenance": prepared["provenance"],
            },
            "run_report": {"path": str(run_root / LOCALIZED_G2_FD_RUN_FILENAME), "sha256": _sha256_file(run_root / LOCALIZED_G2_FD_RUN_FILENAME)},
            "response_gradient_contract": {"path": str(contract_path), "sha256": _sha256_file(contract_path)},
            "cfd_grid": {key: common_case_contract[key] for key in ("cfd_grid_sha256", "cfd_cell_count", "cell_order")},
            "primal_responses": responses,
            "adjoint_gradient": {
                "variable": "raw_alpha",
                "meaning": "dJ=sum_i g_alpha[i]*d(alpha_i)",
                "units": _mapping(contract, "adjoint_gradient")["units"],
                "scale": _mapping(contract, "adjoint_gradient")["scale"],
                "final_time": adjoint_time,
                "case": _case_record(adjoint_attempt, adjoint_case),
                "sources": gradient_sources,
                "relative_path": LOCALIZED_G2_FD_RESPONSE_GRADIENT_ARRAY_FILENAME,
                "sha256": _sha256_file(gradient_path),
                "array_value_sha256": _sha256_array(gradient),
                "dtype": "float64",
                "shape": [int(gradient.size)],
                "cell_order": CANONICAL_CELL_ORDER,
            },
            "limitations": [
                "extracts_only_outer_cfd_raw_alpha_evidence",
                "does_not_apply_E_transpose_projection_derivative_or_filter_adjoint",
                "does_not_compute_an_fd_derivative_or_numerical_acceptance",
                "requires_a_compiler_generated_explicit_contract_not_filename_heuristics",
                "validator_integration_is_deferred_until_this_artifact_has_actual_openfoam_evidence",
            ],
        }
        _write_json(staging / LOCALIZED_G2_FD_RESPONSE_GRADIENT_FILENAME, report)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalizedG2FdResponseGradient(
        path=destination,
        report_json=destination / LOCALIZED_G2_FD_RESPONSE_GRADIENT_FILENAME,
        gradient_npy=destination / LOCALIZED_G2_FD_RESPONSE_GRADIENT_ARRAY_FILENAME,
        flow_case_id=flow_case_id,
        response_id=response_id,
        adjoint_name=adjoint_name,
        cfd_cell_count=int(common_case_contract["cfd_cell_count"]),
    )


def _read_contract(path: str | Path) -> tuple[Path, Mapping[str, object]]:
    source = Path(path).resolve()
    data = _read_json(source)
    if data.get("schema_version") != LOCALIZED_G2_FD_RESPONSE_GRADIENT_CONTRACT_SCHEMA_VERSION or data.get("kind") != LOCALIZED_G2_FD_RESPONSE_GRADIENT_CONTRACT_KIND or data.get("status") != "compiled":
        raise ValueError("response/gradient contract has an unsupported compiler-generated schema")
    required = {"schema_version", "kind", "status", "flow_case_id", "response_id", "named_adjoint_id", "compiler", "cfd_grid_sha256", "cfd_cell_count", "cell_order", "primal_response", "adjoint_gradient"}
    if set(data) != required:
        raise ValueError("response/gradient contract has unexpected or missing fields")
    _require_sha(data.get("cfd_grid_sha256"), "contract cfd_grid_sha256")
    if not isinstance(data.get("cfd_cell_count"), int) or isinstance(data.get("cfd_cell_count"), bool) or int(data["cfd_cell_count"]) <= 0:
        raise ValueError("contract cfd_cell_count must be a positive integer")
    if data.get("cell_order") != CANONICAL_CELL_ORDER:
        raise ValueError("contract must declare canonical x-fastest CFD cell order")
    compiler = _mapping(data, "compiler")
    if set(compiler) != {"compilation_metadata_sha256"}:
        raise ValueError("response/gradient contract compiler provenance is invalid")
    _require_sha(compiler.get("compilation_metadata_sha256"), "contract compilation_metadata_sha256")
    _validate_response_contract(_mapping(data, "primal_response"))
    _validate_gradient_contract(_mapping(data, "adjoint_gradient"))
    if _mapping(data, "primal_response")["units"] != _mapping(data, "adjoint_gradient")["units"]:
        raise ValueError("primal response and raw-alpha gradient units must match for dimensionless alpha")
    return source, data


def _validate_contract_identity(contract: Mapping[str, object], *, flow_case_id: str, response_id: str, adjoint_name: str) -> None:
    for key, expected in (("flow_case_id", flow_case_id), ("response_id", response_id), ("named_adjoint_id", adjoint_name)):
        if contract.get(key) != expected:
            raise ValueError(f"response/gradient contract {key} does not match the requested extraction")


def _require_attempt_response_identity(attempt: Mapping[str, object], flow_case_id: str, response_id: str, label: str) -> None:
    response = _mapping(attempt, "response_provenance")
    if response.get("flow_case_id") != flow_case_id or response.get("response_id") != response_id:
        raise ValueError(f"run attempt {label} does not explicitly bind the requested flow_case_id/response_id")


def _validate_response_contract(value: Mapping[str, object]) -> None:
    if set(value) != {"source", "units", "scale", "final_time_selection"}:
        raise ValueError("primal response contract is invalid")
    _validate_json_scalar_source(_mapping(value, "source"), "primal response")
    _require_text(value.get("units"), "primal response units")
    _validate_identity_scale(_mapping(value, "scale"), "primal response")
    if value.get("final_time_selection") != "recorded_attempt_final_time":
        raise ValueError("primal response final-time selection must be recorded_attempt_final_time")


def _validate_gradient_contract(value: Mapping[str, object]) -> None:
    if set(value) != {"source", "variable", "meaning", "units", "scale", "final_time_selection", "decomposition"}:
        raise ValueError("adjoint gradient contract is invalid")
    if value.get("variable") != "raw_alpha" or value.get("meaning") != "dJ=sum_i g_alpha[i]*d(alpha_i)":
        raise ValueError("adjoint gradient must explicitly be dJ/d(raw_alpha) with the declared meaning")
    _require_text(value.get("units"), "adjoint gradient units")
    _validate_identity_scale(_mapping(value, "scale"), "adjoint gradient")
    if value.get("final_time_selection") != "recorded_attempt_final_time":
        raise ValueError("adjoint gradient final-time selection must be recorded_attempt_final_time")
    decomposition = _mapping(value, "decomposition")
    kind = decomposition.get("kind")
    if kind == "single_case_canonical_x_fastest":
        if set(decomposition) != {"kind", "global_cell_order"} or decomposition.get("global_cell_order") != CANONICAL_CELL_ORDER:
            raise ValueError("single-case gradient decomposition/global order is invalid")
        _validate_npy_source(_mapping(value, "source"), "adjoint gradient")
    elif kind == "processor_global_labels":
        if set(decomposition) != {"kind", "global_cell_order", "reconstruction", "processors"} or decomposition.get("global_cell_order") != CANONICAL_CELL_ORDER or decomposition.get("reconstruction") != "scatter_by_explicit_global_labels":
            raise ValueError("processor gradient decomposition/global order is invalid")
        processors = decomposition.get("processors")
        if not isinstance(processors, list) or not processors:
            raise ValueError("processor gradient decomposition requires a non-empty explicit processor list")
        seen: set[str] = set()
        for processor in processors:
            if not isinstance(processor, Mapping) or set(processor) != {"label", "gradient_source", "global_labels_source"}:
                raise ValueError("processor gradient decomposition member is invalid")
            label = processor.get("label")
            if not isinstance(label, str) or not _SAFE_ID.fullmatch(label) or label in seen:
                raise ValueError("processor gradient decomposition labels must be unique safe labels")
            seen.add(label)
            _validate_npy_source(_mapping(processor, "gradient_source"), "processor gradient")
            _validate_npy_source(_mapping(processor, "global_labels_source"), "processor global labels")
        if value.get("source") != {"kind": "declared_processor_shards"}:
            raise ValueError("processor gradient source must declare declared_processor_shards")
    else:
        raise ValueError("adjoint gradient decomposition rule is unknown")


def _validate_json_scalar_source(value: Mapping[str, object], context: str) -> None:
    if set(value) != {"relative_path_template", "format", "json_pointer"} or value.get("format") != "json":
        raise ValueError(f"{context} source must explicitly be a JSON scalar source")
    _validate_relative_template(value.get("relative_path_template"), context)
    pointer = value.get("json_pointer")
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError(f"{context} source must declare an RFC-6901 JSON pointer")


def _validate_npy_source(value: Mapping[str, object], context: str) -> None:
    if set(value) != {"relative_path_template", "format"} or value.get("format") != "npy":
        raise ValueError(f"{context} source must explicitly be an NPY source")
    _validate_relative_template(value.get("relative_path_template"), context)


def _validate_relative_template(value: object, context: str) -> None:
    if not isinstance(value, str) or value.count("{final_time}") != 1:
        raise ValueError(f"{context} source path must contain exactly one {{final_time}} placeholder")
    candidate = Path(value.replace("{final_time}", "time"))
    if candidate.is_absolute() or ".." in candidate.parts or not value:
        raise ValueError(f"{context} source path must be a safe case-relative path")


def _validate_identity_scale(value: Mapping[str, object], context: str) -> None:
    if value != {"kind": "identity", "factor": 1.0, "conversion": "none"}:
        raise ValueError(f"{context} scale/conversion is unknown or non-identity")


def _verify_case_contract(run_root: Path, attempt: Mapping[str, object], contract: Mapping[str, object], *, label: str) -> dict[str, object]:
    case = (run_root / _require_text(attempt.get("case_relative_path"), f"attempt {label} case_relative_path")).resolve()
    _descendant(case, run_root, "runtime case escapes run evidence root")
    alpha = validate_localized_openfoam_alpha_case(case)
    manifest = _read_json(alpha.manifest_json)
    mesh = read_openfoam_blockmesh_uniform_cartesian_grid(case / "system" / "blockMeshDict")
    grid_hash, cell_count = contract["cfd_grid_sha256"], contract["cfd_cell_count"]
    if mesh.grid_sha256 != grid_hash or mesh.grid.cell_count != cell_count or mesh.grid.cell_order != CANONICAL_CELL_ORDER:
        raise ValueError(f"runtime case {label} blockMesh/grid does not match the response/gradient contract")
    source = _mapping(manifest, "alpha_source")
    binding = _mapping(manifest, "alpha_binding")
    block = _mapping(manifest, "block_mesh")
    if source.get("cfd_grid_sha256") != grid_hash or source.get("cfd_cell_count") != cell_count or source.get("cell_order") != CANONICAL_CELL_ORDER or binding.get("cfd_grid_sha256") != grid_hash or binding.get("cfd_cell_count") != cell_count or block.get("grid_sha256") != grid_hash or block.get("staged_block_mesh_sha256") != mesh.block_mesh_sha256:
        raise ValueError(f"runtime case {label} alpha/staged-manifest/blockMesh binding mismatch")
    template = _mapping(manifest, "template")
    compiler = _mapping(contract, "compiler")
    if template.get("compilation_metadata_sha256") != compiler.get("compilation_metadata_sha256"):
        raise ValueError(f"runtime case {label} is not bound to the compiler contract")
    return {
        "case": case,
        "cfd_grid_sha256": mesh.grid_sha256,
        "cfd_cell_count": mesh.grid.cell_count,
        "cell_order": mesh.grid.cell_order,
        "block_mesh_sha256": mesh.block_mesh_sha256,
        "staged_alpha_manifest_sha256": _sha256_file(alpha.manifest_json),
        "alpha_values_sha256": alpha.alpha_values_sha256,
        "alpha_binding_sha256": binding.get("binding_sha256"),
    }


def _require_same_case_contract(previous: dict[str, object] | None, current: dict[str, object], label: str) -> dict[str, object]:
    comparable = ("cfd_grid_sha256", "cfd_cell_count", "cell_order", "block_mesh_sha256", "alpha_binding_sha256")
    if previous is not None and any(previous[key] != current[key] for key in comparable):
        raise ValueError(f"runtime case {label} has a mismatched grid, blockMesh, or alpha binding")
    return current if previous is None else previous


def _case_record(attempt: Mapping[str, object], case: Mapping[str, object]) -> dict[str, object]:
    return {
        "case_relative_path": attempt["case_relative_path"],
        "case_input_tree_sha256": attempt["case_input_tree_sha256"],
        "case_output_tree_sha256": attempt["case_output_tree_sha256"],
        "block_mesh_sha256": case["block_mesh_sha256"],
        "staged_alpha_manifest_sha256": case["staged_alpha_manifest_sha256"],
        "alpha_values_sha256": case["alpha_values_sha256"],
        "alpha_binding_sha256": case["alpha_binding_sha256"],
    }


def _read_gradient(case: Path, contract: Mapping[str, object], final_time: str, count: int) -> tuple[np.ndarray, list[dict[str, object]]]:
    decomposition = _mapping(contract, "decomposition")
    if decomposition["kind"] == "single_case_canonical_x_fastest":
        source = _resolve_source(case, _mapping(contract, "source"), final_time, "adjoint gradient")
        values = _read_float64_npy(source, "adjoint dJ_dalpha")
        if values.size != count:
            raise ValueError("adjoint dJ_dalpha length does not match the verified CFD grid")
        return values, [{"relative_path": str(source.relative_to(case).as_posix()), "sha256": _sha256_file(source)}]
    result = np.empty(count, dtype=np.float64)
    occupied = np.zeros(count, dtype=np.bool_)
    sources: list[dict[str, object]] = []
    for entry in decomposition["processors"]:
        assert isinstance(entry, Mapping)
        label = str(entry["label"])
        gradient_path = _resolve_source(case, _mapping(entry, "gradient_source"), final_time, f"processor {label} gradient")
        labels_path = _resolve_source(case, _mapping(entry, "global_labels_source"), final_time, f"processor {label} labels")
        values = _read_float64_npy(gradient_path, f"processor {label} gradient")
        labels = _read_int64_npy(labels_path, f"processor {label} global labels")
        if values.size != labels.size or np.any(labels < 0) or np.any(labels >= count) or np.any(occupied[labels]):
            raise ValueError("processor gradient global labels are duplicate, out of range, or length-mismatched")
        result[labels] = values
        occupied[labels] = True
        sources.append({"processor_label": label, "gradient_relative_path": str(gradient_path.relative_to(case).as_posix()), "gradient_sha256": _sha256_file(gradient_path), "global_labels_relative_path": str(labels_path.relative_to(case).as_posix()), "global_labels_sha256": _sha256_file(labels_path)})
    if not bool(np.all(occupied)):
        raise ValueError("processor gradient global labels do not cover every CFD cell exactly once")
    return result, sources


def _resolve_source(case: Path, source: Mapping[str, object], final_time: str, context: str) -> Path:
    template = _require_text(source.get("relative_path_template"), f"{context} relative_path_template")
    candidate = (case / template.replace("{final_time}", final_time)).resolve()
    _descendant(candidate, case, f"{context} source escapes runtime case")
    if not candidate.is_file():
        raise FileNotFoundError(f"{context} source is missing: {candidate}")
    return candidate


def _read_json_scalar(path: Path, pointer: str) -> float:
    value: object = _read_json(path)
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, Mapping):
            if token not in value:
                raise ValueError(f"response JSON pointer does not select a value: {pointer}")
            value = value[token]
        elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
            value = value[int(token)]
        else:
            raise ValueError(f"response JSON pointer does not select exactly one scalar: {pointer}")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError("response source must select exactly one finite numeric scalar")
    return float(value)


def _read_float64_npy(path: Path, context: str) -> np.ndarray:
    value = np.load(path, allow_pickle=False)
    if not isinstance(value, np.ndarray) or value.dtype != np.dtype(np.float64) or not value.dtype.isnative or value.ndim != 1 or not np.isfinite(value).all():
        raise ValueError(f"{context} must be a finite native float64 vector")
    return value


def _read_int64_npy(path: Path, context: str) -> np.ndarray:
    value = np.load(path, allow_pickle=False)
    if not isinstance(value, np.ndarray) or value.dtype != np.dtype(np.int64) or not value.dtype.isnative or value.ndim != 1:
        raise ValueError(f"{context} must be a native int64 vector")
    return value


def _time_token(value: object, context: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{context} final_time is invalid")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{context} final_time is non-finite")
    token = str(value)
    if not token or "/" in token or "\\" in token or token in {".", ".."}:
        raise ValueError(f"{context} final_time is not a safe explicit path token")
    return token


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{key} must be an object")
    return result


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _require_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be non-empty text")
    return value


def _require_identifier(value: object, context: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{context} must be a safe non-empty identifier")


def _require_sha(value: object, context: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{context} must be a SHA-256 hex digest")


def _descendant(path: Path, parent: Path, message: str) -> None:
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


def _sha256_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


__all__ = [
    "LOCALIZED_G2_FD_RESPONSE_GRADIENT_ARRAY_FILENAME",
    "LOCALIZED_G2_FD_RESPONSE_GRADIENT_CONTRACT_KIND",
    "LOCALIZED_G2_FD_RESPONSE_GRADIENT_CONTRACT_SCHEMA_VERSION",
    "LOCALIZED_G2_FD_RESPONSE_GRADIENT_FILENAME",
    "LOCALIZED_G2_FD_RESPONSE_GRADIENT_KIND",
    "LOCALIZED_G2_FD_RESPONSE_GRADIENT_SCHEMA_VERSION",
    "LocalizedG2FdResponseGradient",
    "extract_localized_g2_fd_response_gradient",
]
