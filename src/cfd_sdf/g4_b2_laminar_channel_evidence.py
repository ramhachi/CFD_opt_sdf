"""Fail-closed extraction of B2.0 channel runtime evidence.

The channel qualification deliberately does not accept hand-authored metric
JSON.  This module binds a compiled three-grid pack to a completed runtime
attempt, reads the final ASCII OpenFOAM fields directly, and records every
input hash needed to replay that conclusion.  A temporary ``postProcess``
copy is an independent OpenFOAM-v2512 check; inability to run it, or a
disagreement with the direct field reader, is *inconclusive*, never a pass.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from .g4_b2_laminar_channel import (
    G4_B2_CHANNEL_COMPILATION_FILENAME,
    G4_B2_CHANNEL_RUN_FILENAME,
    evaluate_g4_b2_channel_qualification,
)


G4_B2_CHANNEL_RUNTIME_EVIDENCE_KIND = "g4_b2_channel_runtime_evidence"
G4_B2_CHANNEL_RUNTIME_EVIDENCE_SCHEMA_VERSION = 4
G4_B2_CHANNEL_EVIDENCE_EXTRACTOR_VERSION = "4"
G4_B2_CHANNEL_EVIDENCE_FILENAME = "g4_b2_channel_runtime_evidence.json"
_GRID_IDS = ("coarse", "medium", "fine")
_EXPECTED_IMAGE = "opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"
_FINAL_TIME = 2000.0
_PROFILE_X_M = 0.030
_PRESSURE_X0_M = 0.015
_PRESSURE_X1_M = 0.045
_DECISION_RECORDS = (
    "docs/decisions/2026-08-04-g4-b2-laminar-scope.md",
    "docs/decisions/2026-08-04-g4-b2-channel-evidence-extraction.md",
)
_SUPERSEDED_V2_ARTIFACTS = (
    "channel_evidence_v2_20260804.json",
    "channel_qualification_v2_20260804.json",
)
_FIELD_HEADER_CONTRACTS = {
    "U": {"class": "volVectorField", "dimensions": "[0 1 -1 0 0 0 0]"},
    "p": {"class": "volScalarField", "dimensions": "[0 2 -2 0 0 0 0]"},
    "phi": {"class": "surfaceScalarField", "dimensions": "[0 3 -1 0 0 0 0]"},
}
_FATAL_SIGNATURES = (
    "foam fatal",
    "segmentation fault",
    "floating point exception (core dumped)",
    "mpirun has detected an attempt to run as root",
)
_VECTOR_LINE = re.compile(r"^\(\s*([^\s()]+)\s+([^\s()]+)\s+([^\s()]+)\s*\)$")
_SCALAR_LINE = re.compile(r"^([^\s()]+)$")
_TIME_RE = re.compile(r"^Time\s*=\s*([^\s]+)\s*$")
_SOLVE_RE = re.compile(
    r"Solving for\s+(Ux|Uy|p),\s+Initial residual\s*=\s*([^,]+),\s*Final residual\s*=\s*([^,]+)",
)
_CONTINUITY_RE = re.compile(r"global\s*=\s*([^,\s]+)")
_BLOCK_MESH_NCELLS_RE = re.compile(r"\bnCells:\s*(\d+)\s*$", re.MULTILINE)
_BLOCK_MESH_BOUNDING_BOX_RE = re.compile(
    r"\bboundingBox:\s*\(([^()]*)\)\s*\(([^()]*)\)", re.MULTILINE
)
_BLOCK_MESH_CELL_SIZE_RE = re.compile(
    r"\bBlock\s+0\s+cell\s+size\s*:\s*"
    r"i\s*:\s*([^\s]+)\s*\.\.\s*([^\s]+)\s*"
    r"j\s*:\s*([^\s]+)\s*\.\.\s*([^\s]+)\s*"
    r"k\s*:\s*([^\s]+)\s*\.\.\s*([^\s]+)",
    re.MULTILINE,
)


def extract_g4_b2_channel_runtime_evidence(
    *,
    compilation_dir: str | Path,
    runtime_dir: str | Path,
    postprocess_backend: str = "auto",
    docker_image: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Extract deterministic, source-bound evidence from one runtime bundle.

    Any malformed or incomplete source is retained as an ``inconclusive``
    reason.  This makes the result useful as a forensic artifact without
    allowing missing facts to become a numerical qualification.
    """

    compilation_root = Path(compilation_dir).resolve()
    runtime_root = Path(runtime_dir).resolve()
    index_path = compilation_root / G4_B2_CHANNEL_COMPILATION_FILENAME
    attempt_path = runtime_root / G4_B2_CHANNEL_RUN_FILENAME
    reasons: list[str] = []
    index = _read_json(index_path, "compilation", reasons)
    attempt = _read_json(attempt_path, "runtime_attempt", reasons)
    source = Path(__file__).resolve()
    source_artifacts = _source_artifact_bindings(runtime_root, reasons)
    evidence: dict[str, Any] = {
        "schema_version": G4_B2_CHANNEL_RUNTIME_EVIDENCE_SCHEMA_VERSION,
        "kind": G4_B2_CHANNEL_RUNTIME_EVIDENCE_KIND,
        "status": "inconclusive",
        "complete": False,
        "binding": {
            "compilation": {**_file_binding(index_path), "compilation_sha256": index.get("compilation_sha256") if isinstance(index, Mapping) else None},
            "runtime_attempt": _file_binding(attempt_path),
            "extractor": {
                "version": G4_B2_CHANNEL_EVIDENCE_EXTRACTOR_VERSION,
                "source_path": source.name,
                "source_sha256": _sha256_file(source),
                "expected_container_image": _EXPECTED_IMAGE,
            },
        },
        "decision_records": list(_DECISION_RECORDS),
        "source_artifacts": source_artifacts,
        "canonical_commands": {
            "direct_parser": _canonical_direct_parser_command(),
        },
        "cases": {},
        "reasons": reasons,
        "limitations": [
            "direct_ascii_final_field_extraction_only",
            "postprocess_check_is_required_for_complete_evidence",
            "no_cylinder_naca_or_external_body_claim",
        ],
    }
    if not isinstance(index, Mapping) or not isinstance(attempt, Mapping):
        return evidence
    cases_by_grid = _validate_roots(index, attempt, reasons)
    if cases_by_grid is None:
        evidence["reasons"] = sorted(set(reasons))
        return evidence
    for grid_id in _GRID_IDS:
        evidence["cases"][grid_id] = _extract_case(
            grid_id=grid_id,
            compilation_case=cases_by_grid[grid_id][0],
            attempt_case=cases_by_grid[grid_id][1],
            runtime_root=runtime_root,
            index=index,
            postprocess_backend=postprocess_backend,
            docker_image=docker_image,
            timeout_seconds=timeout_seconds,
        )
    for grid_id, case in evidence["cases"].items():
        for reason in case["reasons"]:
            reasons.append(f"{grid_id}:{reason}")
    evidence["reasons"] = sorted(set(reasons))
    evidence["complete"] = not reasons and all(
        case["status"] == "complete" for case in evidence["cases"].values()
    )
    evidence["status"] = "complete" if evidence["complete"] else "inconclusive"
    return evidence


def write_g4_b2_channel_runtime_evidence(evidence: Mapping[str, Any], path: str | Path) -> Path:
    """Write a deterministic extractor artifact, refusing an overwrite."""

    target = Path(path)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite channel runtime evidence: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json_bytes(evidence).decode("utf-8") + "\n", encoding="utf-8", newline="\n")
    return target


def evaluate_g4_b2_channel_runtime_evidence(
    *, compilation_dir: str | Path, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Feed only a complete extractor v2 artifact into the existing evaluator."""

    legacy, reasons = _legacy_evidence(evidence)
    if reasons:
        # Keep the established evaluator's qualification envelope and make the
        # inability to bind extractor evidence visible as an inconclusive gate.
        result = evaluate_g4_b2_channel_qualification(
            compilation_dir=compilation_dir, evidence={"invalid": True}
        )
        result["reasons"] = sorted(set([*result["reasons"], *reasons]))
        result["extractor_evidence"] = _json_copy(evidence)
        _attach_v4_provenance(result, evidence)
        return result
    result = evaluate_g4_b2_channel_qualification(compilation_dir=compilation_dir, evidence=legacy)
    result["extractor_evidence"] = _json_copy(evidence)
    _attach_v4_provenance(result, evidence)
    return result


def _attach_v4_provenance(result: dict[str, Any], evidence: Mapping[str, Any]) -> None:
    """Keep v4 decision/source/command records visible on the qualification."""

    result["decision_records"] = _json_copy(evidence.get("decision_records"))
    result["source_artifacts"] = _json_copy(evidence.get("source_artifacts"))
    result["canonical_commands"] = _json_copy(evidence.get("canonical_commands"))


def _source_artifact_bindings(runtime_root: Path, reasons: list[str]) -> list[dict[str, Any]]:
    """Bind the explicitly retained, superseded v2 records without trusting them."""

    bindings: list[dict[str, Any]] = []
    for filename in _SUPERSEDED_V2_ARTIFACTS:
        path = runtime_root.parent / filename
        binding = _file_binding(path)
        record = {
            "relative_path": filename,
            "role": "superseded_v2_source_artifact_not_qualification_evidence",
            "binding": binding,
        }
        bindings.append(record)
        if binding.get("status") == "missing":
            reasons.append(f"superseded_v2_source_artifact_missing:{filename}")
    return bindings


def _canonical_direct_parser_command() -> dict[str, Any]:
    """Path-independent public contract for the authoritative direct parser."""

    argv = [
        "cfd-sdf",
        "extract-g4-b2-channel-evidence",
        "<compiled-channel-pack>",
        "<runtime-bundle>",
        "<new-evidence-json>",
        "--postprocess-backend",
        "docker",
    ]
    return {
        "cwd_locator": "runs_root",
        "argv": argv,
        "argv_sha256": _sha256_json(argv),
        "output": "<new-evidence-json>",
    }


def _validate_roots(index: Mapping[str, Any], attempt: Mapping[str, Any], reasons: list[str]) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] | None:
    if index.get("kind") != "g4_b2_channel_compilation" or index.get("schema_version") != 1:
        reasons.append("invalid_compilation_artifact")
        return None
    expected_index = dict(index)
    observed_hash = expected_index.pop("compilation_sha256", None)
    if not _sha256(observed_hash) or _sha256_json(expected_index) != observed_hash:
        reasons.append("compilation_sha256_invalid")
        return None
    if attempt.get("kind") != "g4_b2_channel_runtime_attempt" or attempt.get("schema_version") != 1:
        reasons.append("invalid_runtime_attempt_artifact")
        return None
    if attempt.get("compilation_sha256") != observed_hash or attempt.get("spec_sha256") != index.get("spec_sha256"):
        reasons.append("runtime_attempt_compilation_binding_mismatch")
    if attempt.get("execute_requested") is not True:
        reasons.append("runtime_attempt_was_not_executed")
    compiled = _grid_mapping(index.get("cases"), "compiled_cases", reasons)
    attempted = _grid_mapping(attempt.get("cases"), "runtime_cases", reasons)
    if compiled is None or attempted is None:
        return None
    paired: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for grid_id in _GRID_IDS:
        compiled_case, attempt_case = compiled[grid_id], attempted[grid_id]
        if attempt_case.get("case_sha256") != compiled_case.get("case_sha256"):
            reasons.append(f"{grid_id}:runtime_case_sha256_mismatch")
        if attempt_case.get("case_contract_sha256") != compiled_case.get("case_contract_sha256"):
            reasons.append(f"{grid_id}:runtime_case_contract_sha256_mismatch")
        paired[grid_id] = (compiled_case, attempt_case)
    return paired


def _extract_case(
    *, grid_id: str, compilation_case: Mapping[str, Any], attempt_case: Mapping[str, Any], runtime_root: Path,
    index: Mapping[str, Any], postprocess_backend: str, docker_image: str | None, timeout_seconds: int | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    case_rel = Path("cases") / grid_id
    case_dir = runtime_root / case_rel
    result: dict[str, Any] = {
        "status": "inconclusive", "grid_id": grid_id, "reasons": reasons,
        "binding": {
            "case_sha256": compilation_case.get("case_sha256"),
            "case_contract_sha256": compilation_case.get("case_contract_sha256"),
            "runtime_case_relpath": case_rel.as_posix(),
            "dictionary_file_sha256": _json_copy(compilation_case.get("file_sha256", {})),
        },
        "case": {}, "runtime": {}, "values": {}, "postprocess": {},
    }
    if not case_dir.is_dir():
        reasons.append("runtime_case_directory_missing")
        return result
    _verify_case_contract(case_dir, compilation_case, reasons)
    runtime = _runtime_facts(case_dir, attempt_case, compilation_case, index, reasons)
    result["runtime"] = runtime
    final_time = _final_time_directory(case_dir, reasons)
    if final_time is None:
        return result
    field_bindings = {name: _file_binding(final_time / name) for name in ("U", "p", "phi")}
    field_headers = {
        name: _parse_field_header(
            final_time / name, expected=_FIELD_HEADER_CONTRACTS[name], reasons=reasons, label=name
        )
        for name in ("U", "p", "phi")
    }
    mesh_bindings = {name: _file_binding(case_dir / "constant" / "polyMesh" / name) for name in ("points", "faces", "owner", "neighbour", "boundary")}
    if any(item.get("status") == "missing" for item in mesh_bindings.values()):
        reasons.append("runtime_mesh_files_missing")
    result["case"] = {
        "final_time": "2000", "final_field_sha256": field_bindings,
        "final_field_headers": field_headers,
        "mesh_sha256": mesh_bindings,
    }
    layout = _single_block_layout(case_dir, compilation_case, reasons)
    result["case"]["mesh_layout"] = layout
    u_values = _read_field(final_time / "U", vector=True, reasons=reasons, label="U")
    p_values = _read_field(final_time / "p", vector=False, reasons=reasons, label="p")
    _read_field(final_time / "phi", vector=False, reasons=reasons, label="phi")
    if layout is not None and u_values is not None and p_values is not None:
        values = _extract_values(u_values, p_values, layout, index, reasons)
        result["values"] = values
        coordinate_contract = _direct_coordinate_contract(layout, index, reasons)
        result["case"]["direct_coordinate_contract"] = coordinate_contract
        direct = {
            "u_x": [item[0] for item in u_values],
            "p_kinematic": p_values,
            "coordinates": coordinate_contract,
        }
        result["postprocess"] = _postprocess_check(
            case_dir, direct, published_case_locator=case_rel.as_posix(),
            postprocess_backend=postprocess_backend,
            docker_image=docker_image, timeout_seconds=timeout_seconds,
        )
        if result["postprocess"].get("status") != "verified":
            reasons.append("postprocess_independent_check_not_verified")
    result["status"] = "complete" if not reasons else "inconclusive"
    return result


def _verify_case_contract(case_dir: Path, compiled: Mapping[str, Any], reasons: list[str]) -> None:
    contract_path = case_dir / "channel_case_contract.json"
    if not contract_path.is_file() or _sha256_file(contract_path) != compiled.get("case_contract_sha256"):
        reasons.append("case_contract_hash_mismatch")
    files = compiled.get("file_sha256")
    if not isinstance(files, Mapping):
        reasons.append("compiled_dictionary_hashes_missing")
        return
    for relative, expected in files.items():
        path = case_dir / str(relative)
        if not isinstance(expected, str) or not path.is_file() or _sha256_file(path) != expected:
            reasons.append(f"compiled_dictionary_hash_mismatch:{relative}")


def _runtime_facts(
    case_dir: Path,
    attempt_case: Mapping[str, Any],
    compilation_case: Mapping[str, Any],
    index: Mapping[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    run = attempt_case.get("run")
    facts: dict[str, Any] = {"attempt_status": attempt_case.get("status")}
    if attempt_case.get("status") != "runtime_completed_metrics_not_extracted":
        reasons.append("runtime_attempt_not_completed")
    if not isinstance(run, Mapping):
        reasons.append("runtime_run_record_missing")
        return facts
    public_run = _public_runtime_run_record(run, reasons)
    if public_run is not None:
        facts["run"] = public_run
    image = _command_image(run.get("replay_command"))
    facts["container_image"] = image
    if image != _EXPECTED_IMAGE:
        reasons.append("runtime_container_image_digest_mismatch")
    if run.get("returncode") != 0 or run.get("timed_out") is not False or run.get("error") is not None or run.get("ok") is not True:
        reasons.append("runtime_process_not_successful")
    if run.get("dry_run") is not False:
        reasons.append("runtime_is_dry_run")
    if run.get("solver_error_logs") != []:
        reasons.append("runtime_reports_solver_error_logs")
    log_bindings: dict[str, Any] = {}
    for name in ("log.runOpenFOAM.stdout", "log.runOpenFOAM.stderr", "log.simpleFoam", "log.blockMesh"):
        path = case_dir / name
        log_bindings[name] = _file_binding(path)
        if not path.is_file():
            reasons.append(f"runtime_log_missing:{name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(signature in text.lower() for signature in _FATAL_SIGNATURES):
            reasons.append(f"fatal_signature_in:{name}")
    facts["log_sha256"] = log_bindings
    block_mesh_log = case_dir / "log.blockMesh"
    if block_mesh_log.is_file():
        facts["mesh_check"] = _parse_block_mesh_log(
            block_mesh_log.read_text(encoding="utf-8", errors="replace"),
            compilation_case,
            index,
            reasons,
        )
    log = case_dir / "log.simpleFoam"
    if log.is_file():
        parsed = _parse_solver_log(log.read_text(encoding="utf-8", errors="replace"), index, reasons)
        facts.update(parsed)
    return facts


def _public_runtime_run_record(run: Mapping[str, Any], reasons: list[str]) -> dict[str, Any] | None:
    """Expose only relocation-safe execution facts in extractor evidence.

    The immutable runtime attempt retains the exact staging argv as the raw
    execution record.  Evidence must instead bind its replay command to the
    published bundle.  This prevents a removed ``.tmp-...`` path from becoming
    either a public locator or a false qualification input.
    """

    replay = run.get("replay_command")
    case_locator = run.get("published_case_relpath")
    if (
        not isinstance(replay, Sequence)
        or isinstance(replay, (str, bytes))
        or not replay
        or not all(isinstance(item, str) and item for item in replay)
    ):
        reasons.append("runtime_replay_command_missing_or_invalid")
        return None
    if any(".tmp-" in item for item in replay):
        reasons.append("runtime_replay_command_contains_transient_path")
        return None
    if not isinstance(case_locator, str) or not case_locator or Path(case_locator).is_absolute() or ".." in Path(case_locator).parts:
        reasons.append("runtime_published_case_locator_invalid")
        return None
    return {
        "backend": run.get("backend"),
        "dry_run": run.get("dry_run"),
        "returncode": run.get("returncode"),
        "timed_out": run.get("timed_out"),
        "error": run.get("error"),
        "solver_error_logs": _json_copy(run.get("solver_error_logs")),
        "ok": run.get("ok"),
        "published_case_relpath": case_locator,
        "stdout_relpath": run.get("stdout_relpath"),
        "stderr_relpath": run.get("stderr_relpath"),
        "summary_relpath": run.get("summary_relpath"),
        "replay_command": list(replay),
        "replay_command_sha256": _sha256_json(list(replay)),
    }


def _parse_block_mesh_log(
    text: str,
    compilation_case: Mapping[str, Any],
    index: Mapping[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    """Bind the emitted mesh to the declared single-block channel contract."""

    cells = compilation_case.get("cells")
    geometry = index.get("geometry")
    if (
        not isinstance(cells, Sequence)
        or len(cells) != 3
        or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in cells)
        or not isinstance(geometry, Mapping)
    ):
        reasons.append("blockmesh_declared_contract_invalid")
        return {"status": "inconclusive"}
    try:
        nx, ny, nz = (int(item) for item in cells)
        length = float(geometry["length_m"])
        half_height = float(geometry["half_height_m"])
        span = float(geometry["span_m"])
    except (KeyError, TypeError, ValueError):
        reasons.append("blockmesh_declared_geometry_invalid")
        return {"status": "inconclusive"}
    if not all(math.isfinite(item) and item > 0.0 for item in (length, half_height, span)):
        reasons.append("blockmesh_declared_geometry_invalid")
        return {"status": "inconclusive"}

    expected = {
        "n_cells": nx * ny * nz,
        "bounding_box_m": {"min": [0.0, -half_height, 0.0], "max": [length, half_height, span]},
        "cell_size_m": [length / nx, 2.0 * half_height / ny, span / nz],
    }
    observed: dict[str, Any] = {}
    parsed = True
    n_cells = _BLOCK_MESH_NCELLS_RE.search(text)
    if n_cells is None:
        reasons.append("blockmesh_ncells_unparseable")
        parsed = False
    else:
        observed["n_cells"] = int(n_cells.group(1))
    bounding_box = _BLOCK_MESH_BOUNDING_BOX_RE.search(text)
    if bounding_box is None:
        reasons.append("blockmesh_bounding_box_unparseable")
        parsed = False
    else:
        lower, upper = _parse_float_triplet(bounding_box.group(1)), _parse_float_triplet(bounding_box.group(2))
        if lower is None or upper is None:
            reasons.append("blockmesh_bounding_box_unparseable")
            parsed = False
        else:
            observed["bounding_box_m"] = {"min": lower, "max": upper}
    cell_sizes = _BLOCK_MESH_CELL_SIZE_RE.search(text)
    if cell_sizes is None:
        reasons.append("blockmesh_cell_size_unparseable")
        parsed = False
    else:
        values = [_finite(cell_sizes.group(index)) for index in range(1, 7)]
        if any(value is None for value in values):
            reasons.append("blockmesh_cell_size_unparseable")
            parsed = False
        else:
            observed["cell_size_range_m"] = [
                [float(values[0]), float(values[1])],
                [float(values[2]), float(values[3])],
                [float(values[4]), float(values[5])],
            ]
    if parsed:
        if observed["n_cells"] != expected["n_cells"]:
            reasons.append("blockmesh_ncells_mismatch")
        observed_box = observed["bounding_box_m"]
        if not _float_vectors_close(observed_box["min"], expected["bounding_box_m"]["min"]) or not _float_vectors_close(observed_box["max"], expected["bounding_box_m"]["max"]):
            reasons.append("blockmesh_bounding_box_mismatch")
        observed_sizes = observed["cell_size_range_m"]
        if any(
            not _float_close(value, expected["cell_size_m"][axis])
            for axis, pair in enumerate(observed_sizes)
            for value in pair
        ):
            reasons.append("blockmesh_cell_size_mismatch")
    return {
        "status": "verified" if parsed and not any(reason.startswith("blockmesh_") and reason.endswith(("_mismatch", "_unparseable")) for reason in reasons) else "inconclusive",
        "declared": expected,
        "observed": observed,
    }


def _parse_float_triplet(text: str) -> list[float] | None:
    parts = text.split()
    if len(parts) != 3:
        return None
    values = [_finite(part) for part in parts]
    return [float(value) for value in values] if all(value is not None for value in values) else None


def _float_close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1.0e-10, abs_tol=1.0e-14)


def _float_vectors_close(actual: Sequence[float], expected: Sequence[float]) -> bool:
    return len(actual) == len(expected) and all(_float_close(a, b) for a, b in zip(actual, expected, strict=True))


def _final_time_directory(case_dir: Path, reasons: list[str]) -> Path | None:
    target = case_dir / "2000"
    if not target.is_dir():
        reasons.append("final_time_directory_2000_missing")
        return None
    return target


def _single_block_layout(case_dir: Path, compiled: Mapping[str, Any], reasons: list[str]) -> dict[str, Any] | None:
    cells = compiled.get("cells")
    if not isinstance(cells, Sequence) or len(cells) != 3 or any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in cells):
        reasons.append("compiled_cells_invalid")
        return None
    nx, ny, nz = (int(item) for item in cells)
    if nz != 1 or compiled.get("one_z_cell") is not True:
        reasons.append("one_z_cell_contract_violated")
    block_mesh = case_dir / "system" / "blockMeshDict"
    if not block_mesh.is_file():
        reasons.append("blockMeshDict_missing")
        return None
    text = block_mesh.read_text(encoding="utf-8", errors="replace")
    if len(re.findall(r"\bhex\s*\(", text)) != 1 or f"({nx} {ny} {nz}) simpleGrading (1 1 1)" not in text:
        reasons.append("mesh_is_not_declared_single_uniform_block")
    return {"ordering": "x_fastest_then_y_then_z", "cells": [nx, ny, nz], "one_z_cell": nz == 1}


def _direct_coordinate_contract(
    layout: Mapping[str, Any], index: Mapping[str, Any], reasons: list[str]
) -> dict[str, Any]:
    """Record every direct-parser coordinate assumption used for reductions."""

    try:
        nx, ny, nz = (int(item) for item in layout["cells"])
        geometry = index["geometry"]
        if not isinstance(geometry, Mapping):
            raise KeyError("geometry")
        length = float(geometry["length_m"])
        height = float(geometry["half_height_m"])
        span = float(geometry["span_m"])
        profile_i0, profile_i1, profile_weight = _face_interpolation(_PROFILE_X_M, length, nx)
        p0_i0, p0_i1, p0_weight = _face_interpolation(_PRESSURE_X0_M, length, nx)
        p1_i0, p1_i1, p1_weight = _face_interpolation(_PRESSURE_X1_M, length, nx)
    except (KeyError, TypeError, ValueError):
        reasons.append("direct_coordinate_contract_invalid")
        return {}
    x_centres = [_x_center(i, length, nx) for i in range(nx)]
    y_centres = [-height + (j + 0.5) * (2.0 * height / ny) for j in range(ny)]
    z_centres = [(k + 0.5) * span / nz for k in range(nz)]
    return {
        "status": "declared",
        "ordering": "x_fastest_then_y_then_z",
        "cell_count": nx * ny * nz,
        "x_cell_centres_m": x_centres,
        "y_cell_centres_m": y_centres,
        "z_cell_centres_m": z_centres,
        "profile_sampling": {
            "x_m": _PROFILE_X_M,
            "cell_indices": [profile_i0, profile_i1],
            "cell_centres_m": [x_centres[profile_i0], x_centres[profile_i1]],
            "right_weight": profile_weight,
        },
        "pressure_sampling": {
            "x_m": [_PRESSURE_X0_M, _PRESSURE_X1_M],
            "cell_indices": [[p0_i0, p0_i1], [p1_i0, p1_i1]],
            "cell_centres_m": [
                [x_centres[p0_i0], x_centres[p0_i1]],
                [x_centres[p1_i0], x_centres[p1_i1]],
            ],
            "right_weight": [p0_weight, p1_weight],
        },
    }


def _extract_values(u_values: list[tuple[float, float, float]], p_values: list[float], layout: Mapping[str, Any], index: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    nx, ny, nz = (int(item) for item in layout["cells"])
    expected = nx * ny * nz
    if len(u_values) != expected or len(p_values) != expected:
        reasons.append("final_field_cell_count_does_not_match_single_block_contract")
        return {}
    geometry, physics = index.get("geometry"), index.get("physics")
    if not isinstance(geometry, Mapping) or not isinstance(physics, Mapping):
        reasons.append("compilation_geometry_or_physics_missing")
        return {}
    length = float(geometry["length_m"])
    height = float(geometry["half_height_m"])
    span = float(geometry["span_m"])
    rho = float(physics["density_kg_m3"])
    try:
        profile_i0, profile_i1, profile_weight = _face_interpolation(_PROFILE_X_M, length, nx)
        p0_i0, p0_i1, p0_weight = _face_interpolation(_PRESSURE_X0_M, length, nx)
        p1_i0, p1_i1, p1_weight = _face_interpolation(_PRESSURE_X1_M, length, nx)
    except ValueError as exc:
        reasons.append(str(exc))
        return {}
    profile_y = [-height + (j + 0.5) * (2.0 * height / ny) for j in range(ny)]
    profile_u = [_interpolate_x(u_values, nx, j, profile_i0, profile_i1, profile_weight)[0] for j in range(ny)]
    p0_kinematic = sum(_interpolate_x_scalar(p_values, nx, j, p0_i0, p0_i1, p0_weight) for j in range(ny)) / ny
    p1_kinematic = sum(_interpolate_x_scalar(p_values, nx, j, p1_i0, p1_i1, p1_weight) for j in range(ny)) / ny
    bulk = sum(profile_u) / ny
    return {
        "profile": {
            "sampling": "developed_plane_cell_centres_x_linear_interpolation",
            "x_m": _PROFILE_X_M, "y_m": profile_y, "u_x_mps": profile_u,
            "x_cell_centres_m": [_x_center(profile_i0, length, nx), _x_center(profile_i1, length, nx)], "x_right_weight": profile_weight,
        },
        "bulk_velocity": {
            "sampling": "y_area_weighted_at_x_linear_interpolation", "x_m": _PROFILE_X_M,
            "value_mps": bulk, "area_m2": 2.0 * height * span,
        },
        "pressure_gradient": {
            "sampling": "y_area_weighted_cell_faces_x_linear_interpolation", "x0_m": _PRESSURE_X0_M, "x1_m": _PRESSURE_X1_M,
            "mean_p0_kinematic_m2_s2": p0_kinematic, "mean_p1_kinematic_m2_s2": p1_kinematic,
            "density_kg_m3": rho, "mean_p0_pa": p0_kinematic * rho, "mean_p1_pa": p1_kinematic * rho,
            "negative_dp_dx_pa_per_m": (p0_kinematic - p1_kinematic) * rho / (_PRESSURE_X1_M - _PRESSURE_X0_M),
            "x0_cell_centres_m": [_x_center(p0_i0, length, nx), _x_center(p0_i1, length, nx)], "x1_cell_centres_m": [_x_center(p1_i0, length, nx), _x_center(p1_i1, length, nx)],
        },
    }


def _face_interpolation(x: float, length: float, nx: int) -> tuple[int, int, float]:
    dx = length / nx
    position = x / dx - 0.5
    low = math.floor(position)
    high = low + 1
    weight = position - low
    if low < 0 or high >= nx or not math.isclose(weight, 0.5, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("declared_channel_sampling_position_is_not_an_interior_cell_face")
    return low, high, weight


def _interpolate_x(values: Sequence[tuple[float, float, float]], nx: int, j: int, low: int, high: int, weight: float) -> tuple[float, float, float]:
    a, b = values[j * nx + low], values[j * nx + high]
    return tuple((1.0 - weight) * a[i] + weight * b[i] for i in range(3))  # type: ignore[return-value]


def _interpolate_x_scalar(values: Sequence[float], nx: int, j: int, low: int, high: int, weight: float) -> float:
    return (1.0 - weight) * values[j * nx + low] + weight * values[j * nx + high]


def _x_center(i: int, length: float, nx: int) -> float:
    return (i + 0.5) * length / nx


def _parse_solver_log(text: str, index: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    by_time: dict[float, dict[str, tuple[float, float]]] = {}
    continuity: dict[float, float] = {}
    current: float | None = None
    for raw in text.splitlines():
        match = _TIME_RE.match(raw.strip())
        if match:
            current = _finite(match.group(1))
            continue
        solve = _SOLVE_RE.search(raw)
        if solve and current is not None:
            initial, final = _finite(solve.group(2)), _finite(solve.group(3))
            if initial is not None and final is not None:
                by_time.setdefault(current, {})[solve.group(1)] = (initial, final)
            continue
        global_match = _CONTINUITY_RE.search(raw)
        if global_match and current is not None:
            value = _finite(global_match.group(1))
            if value is not None:
                continuity[current] = value
    if _FINAL_TIME not in by_time or set(by_time[_FINAL_TIME]) != {"Ux", "Uy", "p"}:
        reasons.append("final_Ux_Uy_p_residuals_missing_at_time_2000")
    if _FINAL_TIME not in continuity:
        reasons.append("final_global_continuity_missing_at_time_2000")
    fields = by_time.get(_FINAL_TIME, {})
    finals = {name: pair[1] for name, pair in fields.items()}
    physics, geometry = index.get("physics"), index.get("geometry")
    normalized_mass: float | None = None
    if isinstance(physics, Mapping) and isinstance(geometry, Mapping) and _FINAL_TIME in continuity:
        denominator = float(physics["bulk_velocity_mps"]) * 2.0 * float(geometry["half_height_m"]) * float(geometry["span_m"])
        normalized_mass = abs(continuity[_FINAL_TIME]) / denominator
    last_times = sorted(time for time in by_time if time <= _FINAL_TIME)[-100:]
    stationary = len(last_times) == 100 and all(set(by_time[time]) == {"Ux", "Uy", "p"} for time in last_times)
    initial_max = max((value[0] for time in last_times for value in by_time[time].values()), default=math.inf)
    final_max_window = max((value[1] for time in last_times for value in by_time[time].values()), default=math.inf)
    stationarity_passed = stationary and initial_max <= 1.0e-6 and final_max_window <= 1.0e-10 and normalized_mass is not None and normalized_mass <= 1.0e-4
    if not stationarity_passed:
        reasons.append("nonlinear_residual_stationarity_not_proven")
    return {
        "final_time_s": _FINAL_TIME, "final_residual_by_field": finals,
        "primal_final_residual_max": max(finals.values(), default=None),
        "final_global_continuity": continuity.get(_FINAL_TIME), "normalized_mass_imbalance": normalized_mass,
        "stationarity": {"status": "passed" if stationarity_passed else "not_proven", "window_steps": len(last_times), "initial_residual_max": initial_max, "final_residual_max": final_max_window, "initial_residual_max_limit": 1.0e-6, "final_residual_max_limit": 1.0e-10, "normalized_mass_limit": 1.0e-4},
    }


def _postprocess_check(
    case_dir: Path,
    direct: Mapping[str, Sequence[float]],
    *,
    published_case_locator: str,
    postprocess_backend: str,
    docker_image: str | None,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    """Cross-check fields and mesh coordinates in a disposable v2512 copy.

    The public command contract is relative to the immutable runtime bundle;
    temporary copy locations are intentionally never emitted.  Both outputs
    are hash-bound: ``Ux`` checks the direct U reader and ``C`` checks the
    x-fastest cell ordering and every location used by the reductions.
    """

    backend = _select_postprocess_backend(postprocess_backend)
    image = docker_image or os.environ.get("CFD_SDF_OPENFOAM_IMAGE", _EXPECTED_IMAGE)
    if backend is None:
        return {"status": "unavailable", "reason": "postprocess_backend_unavailable"}
    components_public = _public_postprocess_command(
        backend, published_case_locator, image,
        function='components(U)', output_relative_path="2000/Ux",
    )
    centres_public = _public_postprocess_command(
        backend, published_case_locator, image,
        function="writeCellCentres", output_relative_path="2000/C",
    )
    public = {
        "backend": backend,
        "container_image": image if backend == "docker" else None,
        "case_locator": published_case_locator,
        "command_cwd_locator": "runtime_bundle_root",
        # Retained for v3 readers; canonical v4 records live in commands.
        "command": components_public["command"],
        "commands": {
            "components_U": components_public,
            "write_cell_centres": centres_public,
        },
    }
    if backend == "docker" and image != _EXPECTED_IMAGE:
        return {**public, "status": "unavailable", "reason": "postprocess_container_image_digest_mismatch"}
    with tempfile.TemporaryDirectory(prefix=".g4-b2-channel-postprocess-", dir=case_dir.parent) as temp:
        temporary = Path(temp) / "case"
        shutil.copytree(case_dir, temporary, ignore=shutil.ignore_patterns("postProcessing", ".g4-b2-channel-postprocess-*"))
        component_run = _run_postprocess(
            backend, temporary, image, function='components(U)', timeout_seconds=timeout_seconds,
        )
        if component_run["status"] != "success":
            return {**public, "status": "unavailable", "reason": component_run["reason"], "components_run": component_run}
        ux = _read_field(temporary / "2000" / "Ux", vector=False, reasons=[], label="postprocess_Ux")
        if ux is None:
            return {**public, "status": "unavailable", "reason": "postprocess_Ux_output_missing"}
        expected = direct["u_x"]
        if len(ux) != len(expected) or any(a != b for a, b in zip(ux, expected, strict=True)):
            return {**public, "status": "mismatch", "reason": "postprocess_Ux_disagrees_with_direct_U"}
        ux_path = temporary / "2000" / "Ux"
        ux_header = _parse_field_header(
            ux_path, expected={"class": "volScalarField", "dimensions": "[0 1 -1 0 0 0 0]"},
            reasons=[], label="postprocess_Ux",
        )
        if ux_header.get("status") != "verified":
            return {**public, "status": "unavailable", "reason": "postprocess_Ux_header_invalid"}
        centres_run = _run_postprocess(
            backend, temporary, image, function="writeCellCentres", timeout_seconds=timeout_seconds,
        )
        if centres_run["status"] != "success":
            return {**public, "status": "unavailable", "reason": centres_run["reason"], "write_cell_centres_run": centres_run}
        centres_path = temporary / "2000" / "C"
        centres = _read_field(centres_path, vector=True, reasons=[], label="postprocess_C")
        if centres is None:
            return {**public, "status": "unavailable", "reason": "postprocess_cell_centres_output_missing"}
        centres_header = _parse_field_header(
            centres_path, expected={"class": "volVectorField", "dimensions": "[0 1 0 0 0 0 0]"},
            reasons=[], label="postprocess_C",
        )
        if centres_header.get("status") != "verified":
            return {**public, "status": "unavailable", "reason": "postprocess_cell_centres_header_invalid"}
        coordinate_check = _compare_postprocess_coordinates(centres, direct.get("coordinates"))
        if coordinate_check["status"] != "verified":
            return {**public, "status": "mismatch", "reason": coordinate_check["reason"], "coordinates": coordinate_check}
        return {
            **public,
            "status": "verified",
            "output": {
                "Ux": {**_file_binding(ux_path), "header": ux_header, "field_count": len(ux)},
                "C": {**_file_binding(centres_path), "header": centres_header, "field_count": len(centres)},
            },
            "coordinates": coordinate_check,
        }


def _select_postprocess_backend(requested: str) -> str | None:
    if requested not in {"auto", "local", "wsl", "docker"}:
        return None
    if requested == "auto":
        if shutil.which("postProcess"):
            return "local"
        if shutil.which("docker") and _command_ok(["docker", "info", "--format", "{{.ServerVersion}}"]):
            return "docker"
        return None
    return requested


def _run_postprocess(
    backend: str, case_dir: Path, image: str, *, function: str, timeout_seconds: int | None,
) -> dict[str, Any]:
    command = _postprocess_command(backend, case_dir, image, function=function)
    try:
        done = subprocess.run(command, cwd=case_dir, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "failed", "reason": "postprocess_execution_failed"}
    if done.returncode != 0:
        return {
            "status": "failed", "reason": "postprocess_nonzero_exit", "returncode": done.returncode,
            "stderr_sha256": _sha256_bytes(done.stderr.encode("utf-8", errors="replace")),
        }
    return {"status": "success"}


def _postprocess_command(backend: str, case_dir: Path, image: str, *, function: str) -> list[str]:
    command = f'postProcess -time 2000 -func "{function}"'
    if backend == "local":
        return ["bash", "-lc", command]
    if backend == "wsl":
        return ["wsl", "bash", "-lc", 'case_dir="$(wslpath -a "$1")" && cd "$case_dir" && ' + command, "bash", str(case_dir)]
    return ["docker", "run", "--rm", "--entrypoint", "bash", "--mount", f"type=bind,source={case_dir},target=/case", "-w", "/case", image, "-lc", command]


def _public_postprocess_command(
    backend: str, case_locator: str, image: str, *, function: str, output_relative_path: str,
) -> dict[str, Any]:
    """Return a deterministic, published-bundle locator for postProcess.

    The actual run uses a disposable copied case and therefore cannot be a
    replay locator.  The public argv is deliberately relative to the runtime
    bundle root; it contains no random temporary directory and is executable
    after resolving ``case_locator`` against that root.
    """

    command = f'postProcess -time 2000 -func "{function}"'
    if backend == "local":
        argv = ["bash", "-lc", command]
    elif backend == "wsl":
        argv = ["wsl", "bash", "-lc", command]
    else:
        argv = [
            "docker", "run", "--rm", "--entrypoint", "bash", "--mount",
            f"type=bind,source={case_locator},target=/case", "-w", "/case",
            image, "-lc", command,
        ]
    return {
        "backend": backend,
        "container_image": image if backend == "docker" else None,
        "case_locator": case_locator,
        "command_cwd_locator": "runtime_bundle_root",
        "command": argv,
        "command_sha256": _sha256_json(argv),
        "output_relative_path": output_relative_path,
    }


def _compare_postprocess_coordinates(
    centres: Sequence[Any], contract: Any,
) -> dict[str, Any]:
    """Fail closed unless v2512 centre output proves every direct assumption."""

    if not isinstance(contract, Mapping) or contract.get("ordering") != "x_fastest_then_y_then_z":
        return {"status": "inconclusive", "reason": "direct_coordinate_contract_missing_or_invalid"}
    x_values, y_values, z_values = (
        contract.get("x_cell_centres_m"),
        contract.get("y_cell_centres_m"),
        contract.get("z_cell_centres_m"),
    )
    if not all(isinstance(values, Sequence) and not isinstance(values, (str, bytes)) for values in (x_values, y_values, z_values)):
        return {"status": "inconclusive", "reason": "direct_coordinate_axes_missing"}
    if not all(all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values) for values in (x_values, y_values, z_values)):
        return {"status": "inconclusive", "reason": "direct_coordinate_axes_invalid"}
    nx, ny, nz = len(x_values), len(y_values), len(z_values)
    expected_count = nx * ny * nz
    if contract.get("cell_count") != expected_count or len(centres) != expected_count:
        return {"status": "inconclusive", "reason": "postprocess_cell_centres_count_mismatch"}
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                index = (k * ny + j) * nx + i
                observed = centres[index]
                expected = (float(x_values[i]), float(y_values[j]), float(z_values[k]))
                if (
                    not isinstance(observed, tuple)
                    or len(observed) != 3
                    or any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in observed)
                    or not _float_vectors_close([float(value) for value in observed], expected)
                ):
                    return {
                        "status": "inconclusive",
                        "reason": "postprocess_cell_centres_x_fastest_order_or_location_mismatch",
                        "first_mismatch_flat_index": index,
                    }
    profile = contract.get("profile_sampling")
    pressure = contract.get("pressure_sampling")
    if not isinstance(profile, Mapping) or not isinstance(pressure, Mapping):
        return {"status": "inconclusive", "reason": "direct_coordinate_sampling_missing"}
    if profile.get("x_m") != _PROFILE_X_M or pressure.get("x_m") != [_PRESSURE_X0_M, _PRESSURE_X1_M]:
        return {"status": "inconclusive", "reason": "direct_coordinate_sampling_locations_mismatch"}
    try:
        profile_indices = [int(value) for value in profile["cell_indices"]]
        pressure_indices = [[int(value) for value in pair] for pair in pressure["cell_indices"]]
        profile_centres = [float(value) for value in profile["cell_centres_m"]]
        pressure_centres = [[float(value) for value in pair] for pair in pressure["cell_centres_m"]]
    except (KeyError, TypeError, ValueError):
        return {"status": "inconclusive", "reason": "direct_coordinate_sampling_contract_invalid"}
    sampled_expected = [
        [float(x_values[index]) for index in profile_indices],
        *[[float(x_values[index]) for index in pair] for pair in pressure_indices],
    ]
    if (
        len(profile_indices) != 2
        or len(pressure_indices) != 2
        or profile_centres != sampled_expected[0]
        or pressure_centres != sampled_expected[1:]
        or profile.get("right_weight") != 0.5
        or pressure.get("right_weight") != [0.5, 0.5]
    ):
        return {"status": "inconclusive", "reason": "direct_coordinate_sampling_cell_centres_mismatch"}
    return {
        "status": "verified",
        "ordering": "x_fastest_then_y_then_z",
        "cell_count": expected_count,
        "profile_x_m": _PROFILE_X_M,
        "pressure_x_m": [_PRESSURE_X0_M, _PRESSURE_X1_M],
        "y_cell_centres_m": [float(value) for value in y_values],
    }


def _parse_field_header(
    path: Path, *, expected: Mapping[str, str], reasons: list[str], label: str,
) -> dict[str, Any]:
    """Parse and bind the OpenFOAM class/dimensions before reading values."""

    if not path.is_file():
        reasons.append(f"final_field_missing:{label}")
        return {"status": "missing"}
    text = path.read_text(encoding="utf-8", errors="replace")
    foam_file = re.search(r"\bFoamFile\s*\{(.*?)\}", text, re.DOTALL)
    if foam_file is None:
        reasons.append(f"final_field_header_missing:{label}")
        return {"status": "inconclusive"}
    class_match = re.search(r"\bclass\s+([^;\s]+)\s*;", foam_file.group(1))
    dimensions_match = re.search(r"\bdimensions\s+(\[[^\]]+\])\s*;", text)
    observed = {
        "class": class_match.group(1) if class_match else None,
        "dimensions": dimensions_match.group(1) if dimensions_match else None,
    }
    if observed["class"] is None or observed["dimensions"] is None:
        reasons.append(f"final_field_header_missing:{label}")
        return {"status": "inconclusive", "observed": observed, "expected": dict(expected)}
    if observed["class"] != expected["class"]:
        reasons.append(f"final_field_header_class_mismatch:{label}")
    if observed["dimensions"] != expected["dimensions"]:
        reasons.append(f"final_field_header_dimensions_mismatch:{label}")
    status = "verified" if observed == dict(expected) else "inconclusive"
    return {"status": status, "observed": observed, "expected": dict(expected)}


def _read_field(path: Path, *, vector: bool, reasons: list[str], label: str) -> list[Any] | None:
    if not path.is_file():
        reasons.append(f"final_field_missing:{label}")
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "internalField   nonuniform List<vector>" if vector else "internalField   nonuniform List<scalar>"
    match = re.search(re.escape(marker) + r"\s*(\d+)\s*\(\s*(.*?)\s*\)\s*;", text, re.DOTALL)
    if not match:
        reasons.append(f"final_field_not_ascii_nonuniform:{label}")
        return None
    count = int(match.group(1))
    values: list[Any] = []
    for raw in match.group(2).splitlines():
        line = raw.strip()
        if not line:
            continue
        parsed = _VECTOR_LINE.match(line) if vector else _SCALAR_LINE.match(line)
        if not parsed:
            reasons.append(f"final_field_value_invalid:{label}")
            return None
        if vector:
            row = tuple(_finite(item) for item in parsed.groups())
            if any(item is None for item in row):
                reasons.append(f"final_field_value_nonfinite:{label}")
                return None
            values.append(tuple(float(item) for item in row))
        else:
            value = _finite(parsed.group(1))
            if value is None:
                reasons.append(f"final_field_value_nonfinite:{label}")
                return None
            values.append(value)
    if len(values) != count:
        reasons.append(f"final_field_count_invalid:{label}")
        return None
    return values


def _legacy_evidence(evidence: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    if not isinstance(evidence, Mapping) or evidence.get("schema_version") != G4_B2_CHANNEL_RUNTIME_EVIDENCE_SCHEMA_VERSION or evidence.get("kind") != G4_B2_CHANNEL_RUNTIME_EVIDENCE_KIND:
        return {}, ["unsupported_runtime_evidence_schema"]
    if evidence.get("status") != "complete" or evidence.get("complete") is not True:
        return {}, ["extractor_evidence_incomplete"]
    binding = evidence.get("binding")
    cases = evidence.get("cases")
    if not isinstance(binding, Mapping) or not isinstance(cases, Mapping) or set(cases) != set(_GRID_IDS):
        return {}, ["extractor_evidence_binding_or_cases_invalid"]
    compilation = binding.get("compilation")
    runtime_attempt = binding.get("runtime_attempt")
    extractor = binding.get("extractor")
    if not isinstance(compilation, Mapping) or not _sha256(compilation.get("sha256")) or not isinstance(runtime_attempt, Mapping) or not _sha256(runtime_attempt.get("sha256")) or not isinstance(extractor, Mapping) or extractor.get("version") != G4_B2_CHANNEL_EVIDENCE_EXTRACTOR_VERSION or not _sha256(extractor.get("source_sha256")):
        return {}, ["extractor_evidence_global_binding_invalid"]
    legacy_cases: dict[str, Any] = {}
    for grid_id in _GRID_IDS:
        case = cases[grid_id]
        if not isinstance(case, Mapping) or case.get("status") != "complete":
            reasons.append(f"{grid_id}:extractor_case_incomplete")
            continue
        case_binding, runtime, values, postprocess = case.get("binding"), case.get("runtime"), case.get("values"), case.get("postprocess")
        if not isinstance(case_binding, Mapping) or not _sha256(case_binding.get("case_sha256")) or not isinstance(runtime, Mapping) or not isinstance(values, Mapping) or not isinstance(postprocess, Mapping) or postprocess.get("status") != "verified":
            reasons.append(f"{grid_id}:extractor_case_binding_invalid")
            continue
        profile, bulk, pressure = values.get("profile"), values.get("bulk_velocity"), values.get("pressure_gradient")
        if not isinstance(profile, Mapping) or not isinstance(bulk, Mapping) or not isinstance(pressure, Mapping):
            reasons.append(f"{grid_id}:extractor_values_missing")
            continue
        residual = runtime.get("primal_final_residual_max")
        mass = runtime.get("normalized_mass_imbalance")
        stationarity = runtime.get("stationarity")
        run = runtime.get("run")
        log_sha256 = runtime.get("log_sha256")
        solver_log = log_sha256.get("log.simpleFoam") if isinstance(log_sha256, Mapping) else None
        replay_command = run.get("replay_command") if isinstance(run, Mapping) else None
        solver_log_sha256 = solver_log.get("sha256") if isinstance(solver_log, Mapping) else None
        if (
            not isinstance(residual, (int, float))
            or not isinstance(mass, (int, float))
            or not isinstance(stationarity, Mapping)
            or stationarity.get("status") != "passed"
            or not isinstance(replay_command, Sequence)
            or isinstance(replay_command, (str, bytes))
            or not replay_command
            or not all(isinstance(item, str) and item and ".tmp-" not in item for item in replay_command)
            or not _sha256(solver_log_sha256)
        ):
            reasons.append(f"{grid_id}:runtime_outcomes_invalid")
            continue
        legacy_cases[grid_id] = {
            "case_sha256": case_binding["case_sha256"],
            "runtime": {"status": "completed", "container_image": _EXPECTED_IMAGE, "command": list(replay_command), "final_time_s": _FINAL_TIME, "solver_log_sha256": solver_log_sha256, "fatal_log_clear": True, "primal_final_residual": float(residual), "normalized_mass_imbalance": float(mass), "stationarity": {"status": "passed"}},
            "profile": {"sampling": "developed_plane_cell_centres", "y_m": profile["y_m"], "u_x_mps": profile["u_x_mps"]},
            "bulk_velocity_mps": bulk["value_mps"],
            "pressure_gradient": {"sampling": "developed_area_weighted_cross_sections", "x0_m": pressure["x0_m"], "x1_m": pressure["x1_m"], "mean_p0_pa": pressure["mean_p0_pa"], "mean_p1_pa": pressure["mean_p1_pa"]},
        }
    if reasons:
        return {}, reasons
    declared_compilation_sha256 = compilation.get("compilation_sha256")
    if not _sha256(declared_compilation_sha256):
        return {}, ["extractor_evidence_compilation_identity_invalid"]
    return {"compilation_sha256": declared_compilation_sha256, "cases": legacy_cases}, []


def _grid_mapping(raw: Any, label: str, reasons: list[str]) -> dict[str, Mapping[str, Any]] | None:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        reasons.append(f"{label}_not_sequence")
        return None
    mapped = {item.get("grid_id"): item for item in raw if isinstance(item, Mapping)}
    if set(mapped) != set(_GRID_IDS) or len(mapped) != len(raw):
        reasons.append(f"{label}_must_exactly_match_three_grids")
        return None
    return {grid_id: mapped[grid_id] for grid_id in _GRID_IDS}


def _command_image(command: Any) -> str | None:
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        return None
    images = [item for item in command if isinstance(item, str) and "openfoam-default" in item]
    return images[0] if len(images) == 1 else None


def _file_binding(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": path.name, "status": "missing"}
    return {"path": path.name, "sha256": _sha256_file(path), "bytes": path.stat().st_size}


def _read_json(path: Path, label: str, reasons: list[str]) -> Mapping[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reasons.append(f"{label}_json_unreadable")
        return None
    if not isinstance(raw, Mapping):
        reasons.append(f"{label}_json_not_mapping")
        return None
    return raw


def _command_ok(command: Sequence[str]) -> bool:
    try:
        return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))


__all__ = [
    "G4_B2_CHANNEL_EVIDENCE_FILENAME",
    "G4_B2_CHANNEL_RUNTIME_EVIDENCE_KIND",
    "G4_B2_CHANNEL_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "evaluate_g4_b2_channel_runtime_evidence",
    "extract_g4_b2_channel_runtime_evidence",
    "write_g4_b2_channel_runtime_evidence",
]
