"""Fail-closed B2.0 plane-Poiseuille channel benchmark contract.

This is deliberately a benchmark *pack*, not a replacement CFD solver.  It
creates three serial, one-cell-z OpenFOAM cases from a small YAML contract and
evaluates only explicitly supplied post-run evidence against the analytic
parallel-plate solution.  A compiled case, a dry run, or synthetic values
never becomes an OpenFOAM qualification merely by passing through this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import isfinite, log, sqrt
from pathlib import Path
import shutil
import tempfile
from typing import Any

import yaml

from .execution import run_openfoam_case


G4_B2_CHANNEL_SPEC_KIND = "g4_b2_laminar_benchmark_spec"
G4_B2_CHANNEL_SPEC_SCHEMA_VERSION = 1
G4_B2_CHANNEL_COMPILATION_KIND = "g4_b2_channel_compilation"
G4_B2_CHANNEL_COMPILATION_FILENAME = "g4_b2_channel_compilation.json"
G4_B2_CHANNEL_QUALIFICATION_KIND = "g4_b2_channel_qualification"
G4_B2_CHANNEL_QUALIFICATION_SCHEMA_VERSION = 1
G4_B2_CHANNEL_RUN_KIND = "g4_b2_channel_runtime_attempt"
G4_B2_CHANNEL_RUN_FILENAME = "g4_b2_channel_runtime_attempt.json"
DEFAULT_G4_B2_CHANNEL_SPEC_PATH = Path("examples/g4_b2_laminar/channel.yaml")

_GRID_IDS = ("coarse", "medium", "fine")
_GRID_FACTORS = (1, 2, 4)
_REQUIRED_RUNTIME_FIELDS = (
    "status",
    "container_image",
    "command",
    "final_time_s",
    "solver_log_sha256",
    "fatal_log_clear",
    "primal_final_residual",
    "normalized_mass_imbalance",
    "stationarity",
)


@dataclass(frozen=True)
class G4B2ChannelCompilation:
    """A published channel-case compilation and its immutable index."""

    root: Path
    index_path: Path
    spec_sha256: str
    compilation_sha256: str


def compile_g4_b2_channel_benchmark(
    *, spec_path: str | Path = DEFAULT_G4_B2_CHANNEL_SPEC_PATH, output_dir: str | Path
) -> G4B2ChannelCompilation:
    """Compile the h/h2/h4 channel cases without running OpenFOAM.

    The destination is immutable.  Each generated dictionary has a hash in
    the index, enabling later runtime evidence to prove that all grids used
    the same physics, boundary conditions, and benchmark specification.
    """

    source = Path(spec_path)
    spec = load_g4_b2_channel_spec(source)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite B2 channel compilation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        cases: list[dict[str, Any]] = []
        for grid_id, factor in zip(_GRID_IDS, _GRID_FACTORS, strict=True):
            case_dir = staging / grid_id
            case = _compile_case(case_dir, spec, grid_id=grid_id, factor=factor)
            cases.append(case)
        source_sha256 = _sha256_file(source)
        spec_sha256 = _sha256_json(spec)
        index = {
            "schema_version": 1,
            "kind": G4_B2_CHANNEL_COMPILATION_KIND,
            "benchmark_id": spec["benchmark_id"],
            "spec_path": source.as_posix(),
            "spec_source_sha256": source_sha256,
            "spec_sha256": spec_sha256,
            "physics": spec["physics"],
            "geometry": spec["geometry"],
            "boundary_conditions": spec["boundary_conditions"],
            "analytic_solution": _analytic_contract(spec),
            "acceptance_criteria": _acceptance_criteria(),
            "runtime_evidence_requirements": _runtime_evidence_requirements(),
            "cases": cases,
            "status": "compiled_not_runtime_qualified",
            "limitations": [
                "compilation_does_not_execute_openfoam",
                "runtime_evidence_is_required_for_qualification",
                "channel_gate_only_no_cylinder_naca_or_external_body_claim",
            ],
        }
        # The index hash deliberately excludes itself; it is the evidence
        # binding used by the later evaluator.
        index["compilation_sha256"] = _sha256_json(index)
        index_path = staging / G4_B2_CHANNEL_COMPILATION_FILENAME
        _write_json(index_path, index)
        shutil.move(str(staging), str(destination))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    final = destination / G4_B2_CHANNEL_COMPILATION_FILENAME
    return G4B2ChannelCompilation(
        root=destination,
        index_path=final,
        spec_sha256=str(index["spec_sha256"]),
        compilation_sha256=str(index["compilation_sha256"]),
    )


def load_g4_b2_channel_spec(path: str | Path) -> dict[str, Any]:
    """Load the narrow, generic B2.0 channel YAML contract."""

    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"unable to read B2 channel spec: {source}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("B2 channel spec must be a mapping")
    required = {
        "schema_version", "kind", "benchmark_id", "physics", "geometry",
        "boundary_conditions", "grids",
    }
    if set(raw) != required:
        raise ValueError("B2 channel spec has an unsupported key set")
    if raw.get("schema_version") != G4_B2_CHANNEL_SPEC_SCHEMA_VERSION:
        raise ValueError("unsupported B2 channel spec schema_version")
    if raw.get("kind") != G4_B2_CHANNEL_SPEC_KIND:
        raise ValueError("invalid B2 channel spec kind")
    if raw.get("benchmark_id") != "parallel_plate_channel":
        raise ValueError("B2.0 supports only benchmark_id parallel_plate_channel")
    physics = _mapping(raw["physics"], "physics")
    geometry = _mapping(raw["geometry"], "geometry")
    boundaries = _mapping(raw["boundary_conditions"], "boundary_conditions")
    grids = _mapping(raw["grids"], "grids")
    _exact_keys(physics, {"openfoam_version", "solver", "flow", "density_kg_m3", "kinematic_viscosity_m2_s", "bulk_velocity_mps"}, "physics")
    _exact_keys(geometry, {"half_height_m", "length_m", "span_m"}, "geometry")
    _exact_keys(boundaries, {"inlet", "outlet", "walls", "front_back"}, "boundary_conditions")
    _exact_keys(grids, {"base_cells", "refinement_factors"}, "grids")
    if physics["openfoam_version"] != "v2512" or physics["solver"] != "simpleFoam":
        raise ValueError("B2 channel requires OpenFOAM v2512 and simpleFoam")
    if physics["flow"] != "incompressible_steady_newtonian_laminar":
        raise ValueError("B2 channel requires incompressible steady Newtonian laminar flow")
    if boundaries != {
        "inlet": "analytic_plane_poiseuille_fixed_value",
        "outlet": "fixed_pressure_reference",
        "walls": "no_slip",
        "front_back": "empty",
    }:
        raise ValueError("B2 channel boundary conditions must be the declared Poiseuille contract")
    rho = _positive(physics["density_kg_m3"], "physics.density_kg_m3")
    nu = _positive(physics["kinematic_viscosity_m2_s"], "physics.kinematic_viscosity_m2_s")
    bulk = _positive(physics["bulk_velocity_mps"], "physics.bulk_velocity_mps")
    half_height = _positive(geometry["half_height_m"], "geometry.half_height_m")
    length = _positive(geometry["length_m"], "geometry.length_m")
    span = _positive(geometry["span_m"], "geometry.span_m")
    base = _integer_triplet(grids["base_cells"], "grids.base_cells")
    factors = _integer_sequence(grids["refinement_factors"], "grids.refinement_factors")
    if factors != _GRID_FACTORS:
        raise ValueError("B2 channel grid refinement_factors must be [1, 2, 4]")
    if base[2] != 1:
        raise ValueError("B2 channel must use exactly one z cell")
    if abs(length / base[0] - (2.0 * half_height) / base[1]) > 1.0e-14 * max(length, 2.0 * half_height):
        raise ValueError("B2 channel base grid must have equal x/y in-plane spacing")
    reynolds = 2.0 * half_height * bulk / nu
    if abs(reynolds - 20.0) > 1.0e-12:
        raise ValueError(f"B2 channel must bind Re=20 exactly; got {reynolds!r}")
    return {
        "schema_version": 1,
        "kind": G4_B2_CHANNEL_SPEC_KIND,
        "benchmark_id": "parallel_plate_channel",
        "physics": {
            "openfoam_version": "v2512", "solver": "simpleFoam", "flow": physics["flow"],
            "density_kg_m3": rho, "kinematic_viscosity_m2_s": nu, "bulk_velocity_mps": bulk,
        },
        "geometry": {"half_height_m": half_height, "length_m": length, "span_m": span},
        "boundary_conditions": dict(boundaries),
        "grids": {"base_cells": list(base), "refinement_factors": list(factors)},
    }


def evaluate_g4_b2_channel_qualification(
    *, compilation_dir: str | Path, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate supplied three-grid runtime evidence; missing evidence is inconclusive.

    This function never runs a solver and never accepts a compiler result as a
    runtime result.  Every principal metric requires a valid coarse/medium/
    fine series before it can pass the Richardson-order gate.
    """

    index_path = Path(compilation_dir) / G4_B2_CHANNEL_COMPILATION_FILENAME
    index = _read_compilation(index_path)
    cases = {str(item["grid_id"]): item for item in index["cases"]}
    if not isinstance(evidence, Mapping) or set(evidence) != {"compilation_sha256", "cases"}:
        return _inconclusive(index, ["invalid_evidence_envelope"])
    if evidence.get("compilation_sha256") != index["compilation_sha256"]:
        return _inconclusive(index, ["compilation_sha256_mismatch"])
    submitted = evidence.get("cases")
    if not isinstance(submitted, Mapping) or set(submitted) != set(_GRID_IDS):
        return _inconclusive(index, ["evidence_cases_must_exactly_match_three_grids"])
    parsed: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for grid_id in _GRID_IDS:
        parsed_case, case_reasons = _parse_case_evidence(submitted[grid_id], cases[grid_id], index)
        parsed[grid_id] = parsed_case
        reasons.extend(f"{grid_id}:{reason}" for reason in case_reasons)
    if reasons:
        return _inconclusive(index, sorted(reasons), cases=parsed)
    metrics = {
        "velocity_l2_relative": [parsed[grid_id]["velocity_l2_relative"] for grid_id in _GRID_IDS],
        "bulk_flow_relative_error": [parsed[grid_id]["bulk_flow_relative_error"] for grid_id in _GRID_IDS],
        "pressure_gradient_relative_error": [parsed[grid_id]["pressure_gradient_relative_error"] for grid_id in _GRID_IDS],
    }
    criteria = _acceptance_criteria()
    metric_results = {
        "velocity_l2_relative": _evaluate_metric(metrics["velocity_l2_relative"], criteria["velocity_l2_relative_max"]),
        "bulk_flow_relative_error": _evaluate_metric(metrics["bulk_flow_relative_error"], criteria["bulk_flow_relative_error_max"]),
        "pressure_gradient_relative_error": _evaluate_metric(metrics["pressure_gradient_relative_error"], criteria["pressure_gradient_relative_error_max"]),
    }
    failed = [name for name, value in metric_results.items() if value["status"] != "pass"]
    status = "passed" if not failed else "failed"
    return {
        "schema_version": G4_B2_CHANNEL_QUALIFICATION_SCHEMA_VERSION,
        "kind": G4_B2_CHANNEL_QUALIFICATION_KIND,
        "benchmark_id": index["benchmark_id"],
        "compilation_sha256": index["compilation_sha256"],
        "spec_sha256": index["spec_sha256"],
        "status": status,
        "qualified": status == "passed",
        "analytic_solution": index["analytic_solution"],
        "acceptance_criteria": criteria,
        "cases": parsed,
        "metrics": metric_results,
        "reasons": [f"metric_failed:{name}" for name in failed],
        "limitations": [
            "only_actual_runtime_evidence_with_bound_hashes_can_pass",
            "channel_gate_only_no_cylinder_naca_or_external_body_claim",
        ],
    }


def write_g4_b2_channel_qualification(result: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, result)
    return target


def run_g4_b2_channel_cases(
    *,
    compilation_dir: str | Path,
    output_dir: str | Path,
    backend: str = "auto",
    execute: bool = False,
    timeout_seconds: int | None = None,
    docker_image: str | None = None,
) -> Path:
    """Copy and run the three compiled cases through the shared OpenFOAM runner.

    Compilation remains immutable: runtime files are created only in the new
    output directory.  Even a successful solver process is published as
    ``runtime_completed_metrics_not_extracted``; the evaluator still requires
    profile, bulk, pressure-plane, residual, mass, and stationarity evidence.
    """

    source_root = Path(compilation_dir)
    index = _read_compilation(source_root / G4_B2_CHANNEL_COMPILATION_FILENAME)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite B2 channel runtime attempt: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        attempts: list[dict[str, Any]] = []
        for case in index["cases"]:
            case_dir = source_root / str(case["case_directory"])
            _verify_compiled_case_files(case_dir, case)
            runtime_case_dir = staging / "cases" / str(case["grid_id"])
            shutil.copytree(case_dir, runtime_case_dir)
            run = run_openfoam_case(
                runtime_case_dir,
                backend=backend,
                dry_run=not execute,
                timeout_seconds=timeout_seconds,
                docker_image=docker_image,
            )
            attempts.append({
                "grid_id": case["grid_id"],
                "case_sha256": case["case_sha256"],
                "case_contract_sha256": case["case_contract_sha256"],
                "run": run.to_dict(),
                "status": "contract_only_not_executed" if not execute else (
                    "runtime_completed_metrics_not_extracted" if run.ok else "runtime_failed"
                ),
            })
        artifact = {
            "schema_version": 1,
            "kind": G4_B2_CHANNEL_RUN_KIND,
            "compilation_sha256": index["compilation_sha256"],
            "spec_sha256": index["spec_sha256"],
            "execute_requested": execute,
            "backend_requested": backend,
            "status": "contract_only_not_executed" if not execute else (
                "runtime_completed_metrics_not_extracted" if all(item["status"] == "runtime_completed_metrics_not_extracted" for item in attempts) else "runtime_failed"
            ),
            "qualified": False,
            "cases": attempts,
            "next_required_evidence": _runtime_evidence_requirements(),
            "limitation": "this runner does_not_extract_or_qualify_channel_metrics",
        }
        _write_json(staging / G4_B2_CHANNEL_RUN_FILENAME, artifact)
        shutil.move(str(staging), str(destination))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / G4_B2_CHANNEL_RUN_FILENAME


def _compile_case(case_dir: Path, spec: Mapping[str, Any], *, grid_id: str, factor: int) -> dict[str, Any]:
    geometry = _mapping(spec["geometry"], "geometry")
    physics = _mapping(spec["physics"], "physics")
    base = _integer_triplet(_mapping(spec["grids"], "grids")["base_cells"], "grids.base_cells")
    cells = (base[0] * factor, base[1] * factor, 1)
    half_height = float(geometry["half_height_m"])
    length = float(geometry["length_m"])
    span = float(geometry["span_m"])
    bulk = float(physics["bulk_velocity_mps"])
    nu = float(physics["kinematic_viscosity_m2_s"])
    case_dir.mkdir(parents=True)
    texts = {
        "system/blockMeshDict": _block_mesh_dict(length, half_height, span, cells),
        "system/controlDict": _control_dict(),
        "system/fvSchemes": _fv_schemes(),
        "system/fvSolution": _fv_solution(),
        "constant/transportProperties": _transport_properties(nu),
        "constant/turbulenceProperties": _turbulence_properties(),
        "0/U": _velocity_field(half_height, bulk, cells[1]),
        "0/p": _pressure_field(),
        "Allrun": _allrun(),
        "Allclean": _allclean(),
    }
    file_hashes: dict[str, str] = {}
    for relative, text in texts.items():
        target = case_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        file_hashes[relative] = _sha256_bytes(text.encode("utf-8"))
    (case_dir / "Allrun").chmod(0o755)
    (case_dir / "Allclean").chmod(0o755)
    contract = {
        "grid_id": grid_id,
        "refinement_factor": factor,
        "cells": list(cells),
        "in_plane_cell_size_m": length / cells[0],
        "one_z_cell": True,
        "physics_sha256": _sha256_json(spec["physics"]),
        "geometry_sha256": _sha256_json(spec["geometry"]),
        "boundary_conditions_sha256": _sha256_json(spec["boundary_conditions"]),
        "file_sha256": dict(sorted(file_hashes.items())),
    }
    contract["case_sha256"] = _sha256_json(contract)
    _write_json(case_dir / "channel_case_contract.json", contract)
    return {**contract, "case_directory": grid_id, "case_contract_sha256": _sha256_file(case_dir / "channel_case_contract.json")}


def _verify_compiled_case_files(case_dir: Path, case: Mapping[str, Any]) -> None:
    files = case.get("file_sha256")
    if not isinstance(files, Mapping):
        raise ValueError("compiled B2 channel case has no file hash contract")
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("compiled B2 channel file hash contract is invalid")
        path = case_dir / relative
        if not path.is_file() or _sha256_file(path) != expected:
            raise ValueError(f"compiled B2 channel case file hash mismatch: {case_dir.name}/{relative}")
    contract = case_dir / "channel_case_contract.json"
    if not contract.is_file() or _sha256_file(contract) != case.get("case_contract_sha256"):
        raise ValueError(f"compiled B2 channel case contract hash mismatch: {case_dir.name}")


def _parse_case_evidence(raw: Any, case: Mapping[str, Any], index: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {"grid_id": case["grid_id"], "status": "inconclusive"}
    if not isinstance(raw, Mapping):
        return result, ["case_evidence_must_be_mapping"]
    required = {"case_sha256", "runtime", "profile", "bulk_velocity_mps", "pressure_gradient"}
    if set(raw) != required:
        return result, ["case_evidence_has_unsupported_key_set"]
    if raw.get("case_sha256") != case.get("case_sha256"):
        return result, ["case_sha256_mismatch"]
    runtime = raw.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != set(_REQUIRED_RUNTIME_FIELDS):
        return result, ["runtime_evidence_has_unsupported_key_set"]
    runtime_reasons = _validate_runtime(runtime)
    if runtime_reasons:
        return result, runtime_reasons
    analytic = _mapping(index["analytic_solution"], "analytic_solution")
    profile = raw.get("profile")
    l2, profile_reasons = _profile_l2(profile, analytic, int(case["cells"][1]))
    if profile_reasons:
        return result, profile_reasons
    bulk = _finite(raw.get("bulk_velocity_mps"), "bulk_velocity_mps")
    gradient, gradient_reasons = _pressure_gradient(raw.get("pressure_gradient"), index["geometry"])
    if gradient_reasons:
        return result, gradient_reasons
    if bulk is None or gradient is None or gradient <= 0.0:
        return result, ["invalid_bulk_or_pressure_gradient_metric"]
    expected_bulk = float(analytic["bulk_velocity_mps"])
    expected_gradient = float(analytic["negative_dp_dx_pa_per_m"])
    result.update({
        "status": "runtime_evidence_bound",
        "case_sha256": case["case_sha256"],
        "runtime": _json_copy(runtime),
        "profile": _json_copy(profile),
        "pressure_gradient": _json_copy(raw["pressure_gradient"]),
        "velocity_l2_relative": l2,
        "bulk_velocity_mps": bulk,
        "negative_dp_dx_pa_per_m": gradient,
        "bulk_flow_relative_error": abs(bulk - expected_bulk) / expected_bulk,
        "pressure_gradient_relative_error": abs(gradient - expected_gradient) / expected_gradient,
    })
    return result, []


def _validate_runtime(runtime: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if runtime.get("status") != "completed":
        reasons.append("runtime_not_completed")
    image = runtime.get("container_image")
    if not isinstance(image, str) or "@sha256:" not in image:
        reasons.append("container_image_must_be_digest_pinned")
    command = runtime.get("command")
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)) or not command or not all(isinstance(x, str) and x for x in command):
        reasons.append("invalid_runtime_command")
    if _finite(runtime.get("final_time_s"), "final_time_s") is None:
        reasons.append("invalid_final_time")
    digest = runtime.get("solver_log_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        reasons.append("invalid_solver_log_sha256")
    if runtime.get("fatal_log_clear") is not True:
        reasons.append("fatal_log_not_cleared")
    residual = _finite(runtime.get("primal_final_residual"), "primal_final_residual")
    if residual is None or residual < 0.0:
        reasons.append("invalid_primal_final_residual")
    mass = _finite(runtime.get("normalized_mass_imbalance"), "normalized_mass_imbalance")
    if mass is None:
        reasons.append("invalid_normalized_mass_imbalance")
    stationarity = runtime.get("stationarity")
    if not isinstance(stationarity, Mapping) or stationarity.get("status") != "passed":
        reasons.append("stationarity_not_proven")
    return reasons


def _profile_l2(raw: Any, analytic: Mapping[str, Any], ny: int) -> tuple[float | None, list[str]]:
    if not isinstance(raw, Mapping) or set(raw) != {"y_m", "u_x_mps", "sampling"}:
        return None, ["profile_has_unsupported_key_set"]
    if raw.get("sampling") != "developed_plane_cell_centres":
        return None, ["profile_sampling_must_be_developed_plane_cell_centres"]
    ys, us = raw.get("y_m"), raw.get("u_x_mps")
    if not isinstance(ys, Sequence) or isinstance(ys, (str, bytes)) or not isinstance(us, Sequence) or isinstance(us, (str, bytes)) or len(ys) != ny or len(us) != ny:
        return None, ["invalid_profile_vectors"]
    half_height = float(analytic["half_height_m"])
    bulk = float(analytic["bulk_velocity_mps"])
    y_values: list[float] = []
    u_values: list[float] = []
    for y, u in zip(ys, us, strict=True):
        yy = _finite(y, "profile.y_m")
        uu = _finite(u, "profile.u_x_mps")
        if yy is None or uu is None or yy <= -half_height or yy >= half_height:
            return None, ["invalid_profile_sample"]
        y_values.append(yy)
        u_values.append(uu)
    expected_y = [-half_height + (index + 0.5) * (2.0 * half_height / ny) for index in range(ny)]
    if any(abs(observed - expected) > 1.0e-12 * max(half_height, 1.0) for observed, expected in zip(y_values, expected_y, strict=True)):
        return None, ["profile_y_coordinates_must_match_declared_grid_cell_centres"]
    expected = [1.5 * bulk * (1.0 - (y / half_height) ** 2) for y in y_values]
    denominator = sum(value * value for value in expected)
    if denominator <= 0.0:
        return None, ["degenerate_analytic_profile"]
    return sqrt(sum((actual - exact) ** 2 for actual, exact in zip(u_values, expected, strict=True)) / denominator), []


def _pressure_gradient(raw: Any, geometry: Any) -> tuple[float | None, list[str]]:
    if not isinstance(raw, Mapping) or set(raw) != {"x0_m", "x1_m", "mean_p0_pa", "mean_p1_pa", "sampling"}:
        return None, ["pressure_gradient_has_unsupported_key_set"]
    if raw.get("sampling") != "developed_area_weighted_cross_sections":
        return None, ["pressure_gradient_sampling_must_be_developed_area_weighted_cross_sections"]
    length = float(_mapping(geometry, "geometry")["length_m"])
    x0 = _finite(raw.get("x0_m"), "pressure_gradient.x0_m")
    x1 = _finite(raw.get("x1_m"), "pressure_gradient.x1_m")
    p0 = _finite(raw.get("mean_p0_pa"), "pressure_gradient.mean_p0_pa")
    p1 = _finite(raw.get("mean_p1_pa"), "pressure_gradient.mean_p1_pa")
    if x0 is None or x1 is None or p0 is None or p1 is None or not (0.0 < x0 < x1 < length):
        return None, ["invalid_pressure_gradient_cross_sections"]
    gradient = (p0 - p1) / (x1 - x0)
    if not isfinite(gradient) or gradient <= 0.0:
        return None, ["invalid_negative_dp_dx"]
    return gradient, []


def _evaluate_metric(values: Sequence[float], maximum: float) -> dict[str, Any]:
    coarse, medium, fine = values
    # The decision record names phi_1/phi_2/phi_3 in fine/medium/coarse
    # order.  Preserve that exact formula here even though evidence itself is
    # reported coarsest-to-finest for human readability.
    delta_phi3_phi2 = coarse - medium
    delta_phi2_phi1 = medium - fine
    same_signed = delta_phi3_phi2 * delta_phi2_phi1 > 0.0
    observable = abs(delta_phi3_phi2) > 0.0 and abs(delta_phi2_phi1) > 0.0
    order = log(abs(delta_phi3_phi2 / delta_phi2_phi1)) / log(2.0) if observable else None
    passed = fine <= maximum and same_signed and observable and order is not None and order >= 1.5
    reasons: list[str] = []
    if fine > maximum:
        reasons.append("fine_grid_error_exceeds_limit")
    if not same_signed:
        reasons.append("three_grid_differences_not_same_signed")
    if not observable:
        reasons.append("three_grid_order_not_observable")
    elif order is not None and order < 1.5:
        reasons.append("observed_order_below_1_5")
    return {
        "status": "pass" if passed else "fail",
        "values_coarse_medium_fine": list(values),
        "fine_grid_threshold": maximum,
        "fine_grid_value": fine,
        "phi_1_fine": fine,
        "phi_2_medium": medium,
        "phi_3_coarse": coarse,
        "delta_phi3_phi2": delta_phi3_phi2,
        "delta_phi2_phi1": delta_phi2_phi1,
        "same_signed_three_grid_differences": same_signed,
        "observed_order": order,
        "observed_order_threshold": 1.5,
        "reasons": reasons,
    }


def _analytic_contract(spec: Mapping[str, Any]) -> dict[str, Any]:
    physics, geometry = _mapping(spec["physics"], "physics"), _mapping(spec["geometry"], "geometry")
    rho = float(physics["density_kg_m3"])
    nu = float(physics["kinematic_viscosity_m2_s"])
    bulk = float(physics["bulk_velocity_mps"])
    half_height = float(geometry["half_height_m"])
    return {
        "velocity_profile": "u_x(y)=1.5*U_bulk*(1-(y/H)^2)",
        "bulk_velocity_mps": bulk,
        "half_height_m": half_height,
        "dynamic_viscosity_pa_s": rho * nu,
        "negative_dp_dx_formula": "3*mu*U_bulk/H^2",
        "negative_dp_dx_pa_per_m": 3.0 * rho * nu * bulk / half_height**2,
        "reynolds_number": 2.0 * half_height * bulk / nu,
    }


def _acceptance_criteria() -> dict[str, float]:
    return {
        "velocity_l2_relative_max": 0.02,
        "bulk_flow_relative_error_max": 0.005,
        "pressure_gradient_relative_error_max": 0.02,
        "observed_order_min": 1.5,
    }


def _runtime_evidence_requirements() -> dict[str, Any]:
    return {
        "all_three_grids_required": list(_GRID_IDS),
        "binding": ["compilation_sha256", "case_sha256", "spec_sha256", "dictionary_file_sha256"],
        "runtime": list(_REQUIRED_RUNTIME_FIELDS),
        "metrics": {
            "profile": "strictly increasing developed_plane_cell_centres y_m and u_x_mps",
            "bulk_velocity_mps": "area_weighted developed bulk velocity",
            "pressure_gradient": "two developed area-weighted cross sections; -dp/dx is reconstructed from their positions and means",
        },
        "status_rule": "missing_or_invalid_runtime_evidence_is_inconclusive_not_qualified",
    }


def _inconclusive(index: Mapping[str, Any], reasons: Sequence[str], *, cases: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": G4_B2_CHANNEL_QUALIFICATION_SCHEMA_VERSION,
        "kind": G4_B2_CHANNEL_QUALIFICATION_KIND,
        "benchmark_id": index["benchmark_id"],
        "compilation_sha256": index["compilation_sha256"],
        "spec_sha256": index["spec_sha256"],
        "status": "inconclusive",
        "qualified": False,
        "analytic_solution": index["analytic_solution"],
        "acceptance_criteria": _acceptance_criteria(),
        "cases": _json_copy(cases or {}),
        "metrics": {},
        "reasons": list(reasons),
        "limitations": ["no_openfoam_qualification_without_complete_bound_runtime_evidence"],
    }


def _read_compilation(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read B2 channel compilation: {path}") from exc
    if not isinstance(raw, dict) or raw.get("kind") != G4_B2_CHANNEL_COMPILATION_KIND or raw.get("schema_version") != 1:
        raise ValueError("unsupported B2 channel compilation artifact")
    expected = dict(raw)
    observed = expected.pop("compilation_sha256", None)
    if not isinstance(observed, str) or _sha256_json(expected) != observed:
        raise ValueError("B2 channel compilation hash is invalid")
    cases = raw.get("cases")
    if not isinstance(cases, list) or [item.get("grid_id") if isinstance(item, Mapping) else None for item in cases] != list(_GRID_IDS):
        raise ValueError("B2 channel compilation does not contain canonical three grids")
    return raw


def _block_mesh_dict(length: float, half_height: float, span: float, cells: tuple[int, int, int]) -> str:
    vertices = [(0, -half_height, 0), (length, -half_height, 0), (length, half_height, 0), (0, half_height, 0), (0, -half_height, span), (length, -half_height, span), (length, half_height, span), (0, half_height, span)]
    vertex_text = "\n".join(f"    ({x:.16g} {y:.16g} {z:.16g})" for x, y, z in vertices)
    nx, ny, nz = cells
    return (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object blockMeshDict;\n}\n\n"
        "convertToMeters 1;\n\nvertices\n(\n" + vertex_text + "\n);\n\nblocks\n(\n"
        f"    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n);\n\n"
        "edges\n(\n);\n\nboundary\n(\n"
        "    inlet { type patch; faces ((0 3 7 4)); }\n"
        "    outlet { type patch; faces ((1 5 6 2)); }\n"
        "    lowerWall { type wall; faces ((0 4 5 1)); }\n"
        "    upperWall { type wall; faces ((3 2 6 7)); }\n"
        "    frontAndBack { type empty; faces ((0 1 2 3) (4 7 6 5)); }\n"
        ");\n\nmergePatchPairs\n(\n);\n"
    )


def _control_dict() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object controlDict;\n}\n\napplication simpleFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 2000;\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval 2000;\npurgeWrite 0;\nwriteFormat ascii;\nwritePrecision 12;\nrunTimeModifiable false;\n"


def _fv_schemes() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object fvSchemes;\n}\n\nddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\ndivSchemes { default none; div(phi,U) Gauss linear; }\nlaplacianSchemes { default Gauss linear corrected; }\ninterpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\nwallDist { method meshWave; }\n"


def _fv_solution() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object fvSolution;\n}\n\nsolvers\n{\n    p { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-10; relTol 0; }\n}\nSIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n    pRefCell 0;\n    pRefValue 0;\n}\nrelaxationFactors\n{\n    fields { p 0.3; }\n    equations { U 0.7; }\n}\n"


def _transport_properties(nu: float) -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object transportProperties;\n}\n\ntransportModel Newtonian;\nnu [0 2 -1 0 0 0 0] %.16g;\n" % nu


def _turbulence_properties() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object turbulenceProperties;\n}\n\nsimulationType laminar;\n"


def _velocity_field(half_height: float, bulk: float, ny: int) -> str:
    values = [1.5 * bulk * (1.0 - ((-half_height + (index + 0.5) * (2.0 * half_height / ny)) / half_height) ** 2) for index in range(ny)]
    inlet = "\n".join(f"            ({value:.16g} 0 0)" for value in values)
    common_empty = "type empty;"
    return (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class volVectorField;\n    object U;\n}\n\n"
        "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\nboundaryField\n{\n"
        f"    inlet {{ type fixedValue; value nonuniform List<vector>\n        {ny}\n        (\n{inlet}\n        ); }}\n"
        "    outlet { type zeroGradient; }\n    lowerWall { type noSlip; }\n    upperWall { type noSlip; }\n"
        f"    frontAndBack {{ {common_empty} }}\n}}\n"
    )


def _pressure_field() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class volScalarField;\n    object p;\n}\n\ndimensions [0 2 -2 0 0 0 0];\ninternalField uniform 0;\nboundaryField\n{\n    inlet { type zeroGradient; }\n    outlet { type fixedValue; value uniform 0; }\n    lowerWall { type zeroGradient; }\n    upperWall { type zeroGradient; }\n    frontAndBack { type empty; }\n}\n"


def _allrun() -> str:
    return "#!/usr/bin/env bash\nset -eu\nblockMesh > log.blockMesh 2>&1\nsimpleFoam > log.simpleFoam 2>&1\n"


def _allclean() -> str:
    return "#!/usr/bin/env bash\nset -eu\nrm -rf constant/polyMesh [1-9]* 0/uniform log.blockMesh log.simpleFoam\n"


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} has an unsupported key set")


def _positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number is None or number <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def _finite(value: Any, name: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _integer_triplet(value: Any, name: str) -> tuple[int, int, int]:
    numbers = _integer_sequence(value, name)
    if len(numbers) != 3:
        raise ValueError(f"{name} must contain three positive integers")
    return tuple(numbers)  # type: ignore[return-value]


def _integer_sequence(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    values: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError(f"{name} must contain positive integers")
        values.append(item)
    return tuple(values)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))


__all__ = [
    "DEFAULT_G4_B2_CHANNEL_SPEC_PATH",
    "G4_B2_CHANNEL_COMPILATION_FILENAME",
    "G4_B2_CHANNEL_COMPILATION_KIND",
    "G4_B2_CHANNEL_QUALIFICATION_KIND",
    "G4_B2_CHANNEL_RUN_FILENAME",
    "G4_B2_CHANNEL_RUN_KIND",
    "G4_B2_CHANNEL_SPEC_KIND",
    "G4B2ChannelCompilation",
    "compile_g4_b2_channel_benchmark",
    "evaluate_g4_b2_channel_qualification",
    "load_g4_b2_channel_spec",
    "run_g4_b2_channel_cases",
    "write_g4_b2_channel_qualification",
]
