"""Deterministic B2.0 circular-cylinder cross-fidelity case compiler.

This module deliberately stops at case compilation and execution provenance.
It does not extract forces or probes and it never labels a completed solver
process as a cylinder qualification.  Those evidence calculations need the
separate, source-bound B2.0 evaluator described by the decision record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import cos, isfinite, pi, sin, sqrt
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any

import yaml

from .execution import run_openfoam_case
from .convergence_qualification import has_fatal_openfoam_log


G4_B2_CYLINDER_SPEC_KIND = "g4_b2_laminar_cylinder_spec"
G4_B2_CYLINDER_COMPILATION_KIND = "g4_b2_cylinder_compilation"
G4_B2_CYLINDER_COMPILATION_FILENAME = "g4_b2_cylinder_compilation.json"
G4_B2_CYLINDER_RUN_KIND = "g4_b2_cylinder_runtime_attempt"
G4_B2_CYLINDER_RUN_FILENAME = "g4_b2_cylinder_runtime_attempt.json"
G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME = "extension_source_manifest.json"
DEFAULT_G4_B2_CYLINDER_SPEC_PATH = Path("examples/g4_b2_laminar/cylinder.yaml")

_GRID_IDS = ("coarse", "medium", "fine")
_GRID_FACTORS = (1, 2, 4)
_REPRESENTATIONS = ("body_fitted", "porous_cartesian")
_SECTOR_ANGLES_DEG = (0, 45, 90, 135, 180, 225, 270, 315)
_PHASE_TIMEOUTS_SECONDS = {
    "coarse": {"phase_a": 900, "phase_b": 300},
    "medium": {"phase_a": 1800, "phase_b": 600},
    "fine": {"phase_a": 5400, "phase_b": 1800},
}
_PHASE_RUNTIME_ARTIFACTS = {
    "phase_a": {
        "solver_log_filename": "log.simpleFoam.phaseA",
        "final_time_filename": "runtime_phase_a_final_time.txt",
    },
    "phase_b": {
        "solver_log_filename": "log.simpleFoam.phaseB",
        "final_time_filename": "runtime_phase_b_final_time.txt",
    },
}
_PHASE_A_RESTART_ARCHIVE_RELATIVE = Path("evidence/phase_a_restart")
_PHASE_A_RESTART_ARCHIVE_MANIFEST_RELATIVE = Path("evidence/phase_a_restart_manifest.json")
_CASE_EVIDENCE_MANIFEST_RELATIVE = Path("evidence/case_evidence_manifest.json")
_PHASE_A_RESTART_FIELDS = ("U", "p", "phi")
_PHASE_B_FINAL_FIELDS = ("U", "p")
_PHASE_B_MEASUREMENT_ROWS = 200


@dataclass(frozen=True)
class G4B2CylinderCompilation:
    """A published, immutable six-case cylinder source bundle."""

    root: Path
    index_path: Path
    spec_sha256: str
    compilation_sha256: str


def compile_g4_b2_cylinder_benchmark(
    *, spec_path: str | Path = DEFAULT_G4_B2_CYLINDER_SPEC_PATH, output_dir: str | Path
) -> G4B2CylinderCompilation:
    """Compile the declared O-grid and Cartesian h/h2/h4 cases.

    No mesher or solver is run here.  The published directory is immutable so
    later runtime evidence can bind every mesh/dictionary/field to this exact
    contract rather than a mutable working directory.
    """

    source = Path(spec_path)
    spec = load_g4_b2_cylinder_spec(source)
    extension_source = _extension_source_contract()
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite B2 cylinder compilation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        extension_manifest = _copy_extension_source_snapshot(staging, extension_source)
        cases: list[dict[str, Any]] = []
        for representation in _REPRESENTATIONS:
            for grid_id, factor in zip(_GRID_IDS, _GRID_FACTORS, strict=True):
                case_dir = staging / representation / grid_id
                if representation == "body_fitted":
                    case = _compile_body_fitted_case(case_dir, spec, grid_id=grid_id, factor=factor)
                else:
                    case = _compile_porous_case(
                        case_dir, spec, grid_id=grid_id, factor=factor,
                        extension_source=extension_source,
                    )
                cases.append(case)
        index = {
            "schema_version": 1,
            "kind": G4_B2_CYLINDER_COMPILATION_KIND,
            "benchmark_id": spec["benchmark_id"],
            "spec_path": source.as_posix(),
            "spec_source_sha256": _sha256_file(source),
            "spec_sha256": _sha256_json(spec),
            "physics": spec["physics"],
            "geometry": spec["geometry"],
            "boundary_conditions": spec["boundary_conditions"],
            "grids": spec["grids"],
            "extension": spec["extension"],
            "extension_source_contract": extension_source,
            "extension_source_manifest_sha256": _sha256_file(
                staging / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME
            ),
            "extension_source_manifest": extension_manifest,
            "force_and_probe_contract": _force_and_probe_contract(spec),
            "runtime_evidence_requirements": _runtime_evidence_requirements(),
            "two_phase_runtime_protocol": _two_phase_runtime_protocol(),
            "cases": cases,
            "status": "compiled_not_runtime_qualified",
            "limitations": [
                "compilation_does_not_execute_openfoam",
                "no_cylinder_force_or_cp_extraction_is_implemented_here",
                "completed_runtime_is_not_a_b2_cylinder_qualification",
                "porous_execution_requires_the_pinned_project_extension",
            ],
        }
        index["compilation_sha256"] = _sha256_json(index)
        index_path = staging / G4_B2_CYLINDER_COMPILATION_FILENAME
        _write_json(index_path, index)
        shutil.move(str(staging), str(destination))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    final = destination / G4_B2_CYLINDER_COMPILATION_FILENAME
    return G4B2CylinderCompilation(
        root=destination,
        index_path=final,
        spec_sha256=str(index["spec_sha256"]),
        compilation_sha256=str(index["compilation_sha256"]),
    )


def load_g4_b2_cylinder_spec(path: str | Path) -> dict[str, Any]:
    """Load and strictly validate the source-owned B2.0 cylinder contract."""

    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"unable to read B2 cylinder spec: {source}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("B2 cylinder spec must be a mapping")
    _exact_keys(raw, {"schema_version", "kind", "benchmark_id", "physics", "geometry", "boundary_conditions", "grids", "extension"}, "B2 cylinder spec")
    if raw.get("schema_version") != 1 or raw.get("kind") != G4_B2_CYLINDER_SPEC_KIND:
        raise ValueError("unsupported B2 cylinder spec schema or kind")
    if raw.get("benchmark_id") != "circular_cylinder_cross_fidelity":
        raise ValueError("B2.0 supports only circular_cylinder_cross_fidelity")
    physics = _mapping(raw["physics"], "physics")
    geometry = _mapping(raw["geometry"], "geometry")
    boundaries = _mapping(raw["boundary_conditions"], "boundary_conditions")
    grids = _mapping(raw["grids"], "grids")
    extension = _mapping(raw["extension"], "extension")
    _exact_keys(physics, {"openfoam_version", "solver", "flow", "density_kg_m3", "kinematic_viscosity_m2_s", "freestream_velocity_mps"}, "physics")
    _exact_keys(geometry, {"analytic_shape", "diameter_m", "span_m", "x_bounds_in_diameters", "y_bounds_in_diameters"}, "geometry")
    _exact_keys(boundaries, {"inlet", "outlet", "top_bottom", "cylinder_wall", "front_back"}, "boundary_conditions")
    _exact_keys(grids, {"nominal_h_over_diameter", "refinement_factors", "body_fitted", "porous_cartesian"}, "grids")
    _exact_keys(extension, {"library", "fv_option_type", "option_name", "area_fraction_field", "beta_max_m_inv_s", "darcy_number", "beta_mapping"}, "extension")
    if (physics["openfoam_version"], physics["solver"], physics["flow"]) != ("v2512", "simpleFoam", "incompressible_steady_newtonian_laminar"):
        raise ValueError("B2 cylinder requires OpenFOAM v2512 steady laminar simpleFoam")
    if boundaries != {
        "inlet": "uniform_freestream_fixed_value", "outlet": "fixed_kinematic_pressure_reference",
        "top_bottom": "symmetry", "cylinder_wall": "stationary_no_slip", "front_back": "empty",
    }:
        raise ValueError("B2 cylinder boundary conditions differ from the approved contract")
    if geometry["analytic_shape"] != "circular_cylinder":
        raise ValueError("B2 cylinder requires analytic circular_cylinder geometry")
    rho = _positive(physics["density_kg_m3"], "physics.density_kg_m3")
    nu = _positive(physics["kinematic_viscosity_m2_s"], "physics.kinematic_viscosity_m2_s")
    uinf = _positive(physics["freestream_velocity_mps"], "physics.freestream_velocity_mps")
    diameter = _positive(geometry["diameter_m"], "geometry.diameter_m")
    span = _positive(geometry["span_m"], "geometry.span_m")
    x_bounds = _float_pair(geometry["x_bounds_in_diameters"], "geometry.x_bounds_in_diameters")
    y_bounds = _float_pair(geometry["y_bounds_in_diameters"], "geometry.y_bounds_in_diameters")
    if x_bounds != (-15.0, 25.0) or y_bounds != (-15.0, 15.0):
        raise ValueError("B2 cylinder domain must remain [-15D,+25D] x [-15D,+15D]")
    if abs(uinf * diameter / nu - 20.0) > 1.0e-12:
        raise ValueError("B2 cylinder requires Re_D=20 exactly")
    if abs(span - diameter) > 1.0e-14 * diameter:
        raise ValueError("B2 cylinder requires declared one-cell span Lz=D")
    factors = _integer_sequence(grids["refinement_factors"], "grids.refinement_factors")
    h_over_d = _float_sequence(grids["nominal_h_over_diameter"], "grids.nominal_h_over_diameter")
    if factors != _GRID_FACTORS or h_over_d != (1.0 / 8.0, 1.0 / 16.0, 1.0 / 32.0):
        raise ValueError("B2 cylinder grids must be h=D/8,D/16,D/32 with factors [1,2,4]")
    body = _mapping(grids["body_fitted"], "grids.body_fitted")
    cart = _mapping(grids["porous_cartesian"], "grids.porous_cartesian")
    _exact_keys(body, {"azimuthal_cells_per_sector_base", "radial_cells_per_sector_base", "grading"}, "grids.body_fitted")
    _exact_keys(cart, {"area_fraction_rule"}, "grids.porous_cartesian")
    azimuthal = _positive_int(body["azimuthal_cells_per_sector_base"], "body_fitted.azimuthal_cells_per_sector_base")
    radial = _positive_int(body["radial_cells_per_sector_base"], "body_fitted.radial_cells_per_sector_base")
    grading = _float_triplet(body["grading"], "body_fitted.grading")
    if grading != (1.0, 1.0, 1.0):
        raise ValueError("B2 body-fitted grading must remain fixed at simpleGrading (1 1 1)")
    if cart["area_fraction_rule"] != "fixed_16x16_midpoint_subcells":
        raise ValueError("B2 porous area fraction requires fixed_16x16_midpoint_subcells")
    if extension["library"] != "libcfdSdfLinearBrinkman.so" or extension["fv_option_type"] != "cfdSdfLinearBrinkman":
        raise ValueError("B2 porous extension identity differs from the project-owned contract")
    if extension["option_name"] != "porousCylinderResistance" or extension["area_fraction_field"] != "beta":
        raise ValueError("B2 porous extension field/option contract differs")
    beta = _positive(extension["beta_max_m_inv_s"], "extension.beta_max_m_inv_s")
    da = _positive(extension["darcy_number"], "extension.darcy_number")
    derived_da = nu / (beta * diameter * diameter)
    if beta != 1.5e5 or da != 1.0e-6 or abs(da - derived_da) > 1.0e-14 or extension["beta_mapping"] != "source=-betaMax*beta*U;resistance=betaMax*beta*U":
        raise ValueError("B2 porous betaMax/Da/mapping differ from the fixed benchmark contract")
    return {
        "schema_version": 1, "kind": G4_B2_CYLINDER_SPEC_KIND, "benchmark_id": "circular_cylinder_cross_fidelity",
        "physics": {"openfoam_version": "v2512", "solver": "simpleFoam", "flow": "incompressible_steady_newtonian_laminar", "density_kg_m3": rho, "kinematic_viscosity_m2_s": nu, "freestream_velocity_mps": uinf},
        "geometry": {"analytic_shape": "circular_cylinder", "diameter_m": diameter, "span_m": span, "x_bounds_in_diameters": list(x_bounds), "y_bounds_in_diameters": list(y_bounds)},
        "boundary_conditions": dict(boundaries),
        "grids": {"nominal_h_over_diameter": list(h_over_d), "refinement_factors": list(factors), "body_fitted": {"azimuthal_cells_per_sector_base": azimuthal, "radial_cells_per_sector_base": radial, "grading": list(grading)}, "porous_cartesian": {"area_fraction_rule": cart["area_fraction_rule"]}},
        "extension": {"library": str(extension["library"]), "fv_option_type": str(extension["fv_option_type"]), "option_name": str(extension["option_name"]), "area_fraction_field": str(extension["area_fraction_field"]), "beta_max_m_inv_s": beta, "darcy_number": da, "darcy_number_formula": "nu/(betaMax*D^2)", "darcy_number_derived": derived_da, "beta_mapping": str(extension["beta_mapping"])},
    }


def run_g4_b2_cylinder_cases(
    *, compilation_dir: str | Path, output_dir: str | Path, backend: str = "auto",
    through_grid: str, execute: bool = False, timeout_seconds: int | None = None,
    docker_image: str | None = None,
) -> Path:
    """Run a fresh canonical prefix through one explicitly selected grid.

    The original compilation remains untouched.  This does not claim that an
    extension is installed or that any force/probe data has been extracted.
    """

    source_root = Path(compilation_dir)
    index = _read_compilation(source_root / G4_B2_CYLINDER_COMPILATION_FILENAME)
    requested_through_grid = _validate_through_grid(through_grid)
    extension_snapshot = _verify_extension_source_snapshot(source_root, index)
    if execute and (backend != "docker" or not _is_digest_pinned_v2512_image(docker_image)):
        raise ValueError("executed B2 cylinder pack requires --backend docker and a digest-pinned v2512 --docker-image")
    if timeout_seconds is not None:
        raise ValueError("B2 cylinder uses the fixed per-phase timeout table; --timeout-seconds is not permitted")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite B2 cylinder runtime attempt: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        # A runtime artifact must remain independently auditable after the
        # compilation bundle is moved or deleted.  Copy only the verified,
        # source-only extension snapshot and its manifest into fresh staging;
        # porous Phase A mounts this copy, never the mutable compilation tree.
        runtime_extension_snapshot = _stage_extension_source_snapshot(
            source_root, staging, index, extension_snapshot=extension_snapshot,
        )
        attempts: list[dict[str, Any]] = []
        cases = {(str(case["representation"]), str(case["grid_id"])): case for case in index["cases"]}
        canonical_case_ids = [f"{representation}/{grid_id}" for grid_id in _GRID_IDS for representation in _REPRESENTATIONS]
        selected_grids = _GRID_IDS[: _GRID_IDS.index(requested_through_grid) + 1]
        stopped_by: str | None = None
        for grid_id in selected_grids:
            for representation in _REPRESENTATIONS:
                case = cases[(representation, grid_id)]
                if stopped_by == "runtime_failure":
                    continue
                source_case = source_root / str(case["case_directory"])
                _verify_compiled_case_files(source_case, case)
                case_relpath = Path("cases") / str(case["case_directory"])
                runtime_case = staging / case_relpath
                shutil.copytree(source_case, runtime_case)
                if representation == "porous_cartesian":
                    _verify_porous_case_semantics(runtime_case)
                run_record = _run_cylinder_case_two_phase(
                    runtime_case, representation=representation, grid_id=grid_id,
                    snapshot_dir=runtime_extension_snapshot if representation == "porous_cartesian" else None,
                    case_relpath=case_relpath, execute=execute, docker_image=docker_image,
                    expected_snapshot_manifest_sha256=str(index["extension_source_manifest_sha256"]),
                    expected_snapshot_tree_sha256=str(_mapping(index["extension_source_contract"], "extension_source_contract")["source_tree_sha256"]),
                )
                run_ok = bool(run_record["ok"])
                _write_json(runtime_case / "openfoam_run_summary.json", run_record)
                attempts.append({
                    "representation": case["representation"], "grid_id": case["grid_id"], "case_sha256": case["case_sha256"],
                    "case_contract_sha256": case["case_contract_sha256"], "run": run_record,
                    "status": "contract_only_not_executed" if not execute else ("runtime_raw_evidence_complete_unqualified" if run_ok else "runtime_failed"),
                })
                if execute and not run_ok:
                    stopped_by = "runtime_failure"
        if stopped_by is None:
            stopped_by = "requested_grid"
        complete_prefix = len(attempts) == len(selected_grids) * len(_REPRESENTATIONS)
        execution_succeeded = execute and complete_prefix and all(item["status"] == "runtime_raw_evidence_complete_unqualified" for item in attempts)
        status = "contract_only_not_executed" if not execute else ("partial_runtime_completed_unqualified" if execution_succeeded else "runtime_failed")
        executed_through_grid = attempts[-1]["grid_id"] if attempts else None
        artifact = {
            "schema_version": 1, "kind": G4_B2_CYLINDER_RUN_KIND,
            "compilation_sha256": index["compilation_sha256"], "spec_sha256": index["spec_sha256"],
            "extension_source_manifest_sha256": index["extension_source_manifest_sha256"],
            "docker_image_digest": docker_image if execute else None,
            "execute_requested": execute, "backend_requested": backend, "status": status, "qualified": False,
            "requested_through_grid": requested_through_grid, "executed_through_grid": executed_through_grid,
            "canonical_case_ids": canonical_case_ids,
            "ordered_executed_case_ids": [f"{item['representation']}/{item['grid_id']}" for item in attempts],
            "stopped_by": stopped_by,
            "phase_timeouts_seconds": _PHASE_TIMEOUTS_SECONDS,
            "cases": attempts, "next_required_evidence": _runtime_evidence_requirements(),
            "force_cp_evaluation": {"evaluated": False, "reason": "runner_does_not_extract_force_cp_richardson_gci_or_cross_fidelity"},
            "solver_evaluation": _unevaluated_solver_evaluation_state(),
            "evaluation_precondition": {"requires_single_through_grid_fine_artifact": True, "requires_all_six_canonical_case_records": True, "requires_complete_bound_force_cp_raw_evidence": True, "requires_force_cp_grid_series_extractor": True},
            "next_required_condition": "run a new --through-grid fine prefix" if requested_through_grid != "fine" else "run the force_cp_grid_series_extractor on this single six-case artifact",
        }
        _write_json(staging / G4_B2_CYLINDER_RUN_FILENAME, artifact)
        shutil.move(str(staging), str(destination))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / G4_B2_CYLINDER_RUN_FILENAME


def _compile_body_fitted_case(case_dir: Path, spec: Mapping[str, Any], *, grid_id: str, factor: int) -> dict[str, Any]:
    geometry, grids, physics = _mapping(spec["geometry"], "geometry"), _mapping(spec["grids"], "grids"), _mapping(spec["physics"], "physics")
    diameter, span = float(geometry["diameter_m"]), float(geometry["span_m"])
    body = _mapping(grids["body_fitted"], "grids.body_fitted")
    azimuthal = int(body["azimuthal_cells_per_sector_base"]) * factor
    radial = int(body["radial_cells_per_sector_base"]) * factor
    mesh, mesh_contract = _body_fitted_block_mesh_dict(diameter, span, azimuthal, radial)
    texts = _common_case_files(spec, representation="body_fitted", block_mesh=mesh)
    texts.update(_phase_dictionary_files(spec, representation="body_fitted"))
    _write_case_texts(case_dir, texts)
    return _case_contract(case_dir, spec, representation="body_fitted", grid_id=grid_id, factor=factor, mesh_contract=mesh_contract, area_fraction=None)


def _compile_porous_case(
    case_dir: Path, spec: Mapping[str, Any], *, grid_id: str, factor: int,
    extension_source: Mapping[str, Any],
) -> dict[str, Any]:
    geometry, grids = _mapping(spec["geometry"], "geometry"), _mapping(spec["grids"], "grids")
    diameter, span = float(geometry["diameter_m"]), float(geometry["span_m"])
    h = diameter / (8 * factor)
    nx, ny = int(round(40 * diameter / h)), int(round(30 * diameter / h))
    mesh, mesh_contract = _cartesian_block_mesh_dict(diameter, span, nx, ny)
    fractions, fraction_contract = _circular_area_fraction_field(diameter, nx, ny, rule=str(_mapping(grids["porous_cartesian"], "grids.porous_cartesian")["area_fraction_rule"]))
    texts = _common_case_files(spec, representation="porous_cartesian", block_mesh=mesh)
    texts.update(_phase_dictionary_files(spec, representation="porous_cartesian"))
    texts["constant/fvOptions"] = _brinkman_fv_options(spec)
    texts["0/beta"] = _scalar_field("beta", fractions)
    _write_case_texts(case_dir, texts)
    return _case_contract(
        case_dir, spec, representation="porous_cartesian", grid_id=grid_id,
        factor=factor, mesh_contract=mesh_contract, area_fraction=fraction_contract,
        extension_source=extension_source,
    )


def _common_case_files(spec: Mapping[str, Any], *, representation: str, block_mesh: str) -> dict[str, str]:
    nu = float(_mapping(spec["physics"], "physics")["kinematic_viscosity_m2_s"])
    uinf = float(_mapping(spec["physics"], "physics")["freestream_velocity_mps"])
    return {
        "system/blockMeshDict": block_mesh,
        "system/fvSchemes": _fv_schemes(),
        "constant/transportProperties": _transport_properties(nu), "constant/turbulenceProperties": _turbulence_properties(),
        "0/U": _velocity_field(uinf, representation=representation), "0/p": _pressure_field(representation=representation),
        "Allrun": _allrun(porous=representation == "porous_cartesian"), "Allclean": _allclean(),
    }


def _phase_dictionary_files(spec: Mapping[str, Any], *, representation: str) -> dict[str, str]:
    """Emit both immutable phase templates plus phase-A active defaults."""

    phase_a_control = _control_dict(spec, representation=representation, phase="phase_a")
    phase_b_template = _control_dict(spec, representation=representation, phase="phase_b")
    phase_a_solution = _fv_solution(phase="phase_a")
    phase_b_solution = _fv_solution(phase="phase_b")
    return {
        "system/controlDict": phase_a_control,
        "system/controlDict.phaseA": phase_a_control,
        "system/controlDict.phaseB.template": phase_b_template,
        "system/fvSolution": phase_a_solution,
        "system/fvSolution.phaseA": phase_a_solution,
        "system/fvSolution.phaseB": phase_b_solution,
    }


def _write_case_texts(case_dir: Path, texts: Mapping[str, str]) -> None:
    case_dir.mkdir(parents=True)
    for relative, text in texts.items():
        target = case_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    (case_dir / "Allrun").chmod(0o755)
    (case_dir / "Allclean").chmod(0o755)


def _case_contract(
    case_dir: Path, spec: Mapping[str, Any], *, representation: str, grid_id: str,
    factor: int, mesh_contract: Mapping[str, Any], area_fraction: Mapping[str, Any] | None,
    extension_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    file_hashes = {path.relative_to(case_dir).as_posix(): _sha256_file(path) for path in sorted(case_dir.rglob("*")) if path.is_file()}
    contract: dict[str, Any] = {
        "representation": representation, "grid_id": grid_id, "refinement_factor": factor,
        "nominal_h_m": float(_mapping(spec["geometry"], "geometry")["diameter_m"]) / (8 * factor),
        "one_z_cell": True, "physics_sha256": _sha256_json(spec["physics"]),
        "geometry_sha256": _sha256_json(spec["geometry"]), "boundary_conditions_sha256": _sha256_json(spec["boundary_conditions"]),
        "two_phase_runtime_protocol": _two_phase_runtime_protocol(),
        "mesh_contract": dict(mesh_contract), "file_sha256": dict(sorted(file_hashes.items())),
    }
    if representation == "porous_cartesian":
        contract["extension_contract"] = _json_copy(spec["extension"])
        contract["extension_source_contract"] = _json_copy(extension_source)
        contract["area_fraction_contract"] = _json_copy(area_fraction)
    contract["case_sha256"] = _sha256_json(contract)
    contract_name = "cylinder_case_contract.json"
    _write_json(case_dir / contract_name, contract)
    return {**contract, "case_directory": f"{representation}/{grid_id}", "case_contract_sha256": _sha256_file(case_dir / contract_name)}


def _body_fitted_block_mesh_dict(diameter: float, span: float, azimuthal: int, radial: int) -> tuple[str, dict[str, Any]]:
    radius, xlo, xhi, ylo, yhi = diameter / 2.0, -15.0 * diameter, 25.0 * diameter, -15.0 * diameter, 15.0 * diameter
    inner = [(radius * cos(angle * pi / 180.0), radius * sin(angle * pi / 180.0)) for angle in _SECTOR_ANGLES_DEG]
    outer = [(xhi, 0.0), (yhi, yhi), (0.0, yhi), (xlo, yhi), (xlo, 0.0), (xlo, ylo), (0.0, ylo), (yhi, ylo)]
    # The ordered bottom vertices are inner 0..7 then outer 0..7; top repeats
    # at +span.  This order is a public contract, not an inferred O-grid.
    planar = inner + outer
    vertices = [(x, y, z) for z in (0.0, span) for x, y in planar]
    vertex_text = "\n".join(f"    ({x:.16g} {y:.16g} {z:.16g})" for x, y, z in vertices)
    blocks: list[str] = []
    arcs: list[str] = []
    cylinder_faces: list[str] = []
    patch_faces: dict[str, list[str]] = {"inlet": [], "outlet": [], "top": [], "bottom": []}
    front_back: list[str] = []
    outer_patches = ("outlet", "top", "top", "inlet", "inlet", "bottom", "bottom", "outlet")
    block_contract: list[dict[str, Any]] = []
    for sector, angle in enumerate(_SECTOR_ANGLES_DEG):
        next_sector = (sector + 1) % 8
        a, b, c, d = sector, next_sector, 8 + next_sector, 8 + sector
        e, f, g, h = a + 16, b + 16, c + 16, d + 16
        # blockMesh requires a right-handed local coordinate system.  The
        # planar ring ordering is counter-clockwise when viewed from +z, so
        # place the +z face first and the z=0 face second to give every
        # sector a positive cell volume.
        winding = [e, f, g, h, a, b, c, d]
        blocks.append(f"    hex ({' '.join(str(vertex) for vertex in winding)}) ({azimuthal} {radial} 1) simpleGrading (1 1 1)")
        mid_angle = (angle + 22.5) * pi / 180.0
        midpoint = (radius * cos(mid_angle), radius * sin(mid_angle))
        arcs.extend((f"    arc {a} {b} ({midpoint[0]:.16g} {midpoint[1]:.16g} 0)", f"    arc {e} {f} ({midpoint[0]:.16g} {midpoint[1]:.16g} {span:.16g})"))
        cylinder_faces.append(f"({a} {e} {f} {b})")
        patch_faces[outer_patches[sector]].append(f"({d} {c} {g} {h})")
        front_back.extend((f"({a} {b} {c} {d})", f"({e} {h} {g} {f})"))
        block_contract.append({"sector": sector, "theta_start_deg": angle, "vertices": winding, "cells": [azimuthal, radial, 1], "grading": [1.0, 1.0, 1.0]})
    boundary = "\n".join(
        [f"    {name} {{ type {'symmetryPlane' if name in {'top', 'bottom'} else 'patch'}; faces ({' '.join(faces)}); }}" for name, faces in patch_faces.items()]
        + [f"    cylinder {{ type wall; faces ({' '.join(cylinder_faces)}); }}", f"    frontAndBack {{ type empty; faces ({' '.join(front_back)}); }}"]
    )
    text = (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object blockMeshDict;\n}\n\nconvertToMeters 1;\n\nvertices\n(\n" + vertex_text
        + "\n);\n\nblocks\n(\n" + "\n".join(blocks) + "\n);\n\nedges\n(\n" + "\n".join(arcs)
        + "\n);\n\nboundary\n(\n" + boundary + "\n);\n\nmergePatchPairs\n(\n);\n"
    )
    radial_widths = [sqrt((outer[index][0] - inner[index][0]) ** 2 + (outer[index][1] - inner[index][1]) ** 2) / radial for index in range(8)]
    azimuthal_width = (2.0 * pi * radius / 8.0) / azimuthal
    return text, {"mesh_type": "deterministic_blockMesh_o_grid", "vertices": [[x, y, z] for x, y, z in vertices], "arc_controls": [{"sector": index, "midpoint": [radius * cos((angle + 22.5) * pi / 180.0), radius * sin((angle + 22.5) * pi / 180.0)]} for index, angle in enumerate(_SECTOR_ANGLES_DEG)], "block_order": block_contract, "cells_per_block": [azimuthal, radial, 1], "total_cells": 8 * azimuthal * radial, "actual_in_plane_spacing_m": {"min": min(min(radial_widths), azimuthal_width), "max": max(max(radial_widths), azimuthal_width)}, "outer_domain_m": {"x": [xlo, xhi], "y": [ylo, yhi]}, "cylinder_radius_m": radius}


def _cartesian_block_mesh_dict(diameter: float, span: float, nx: int, ny: int) -> tuple[str, dict[str, Any]]:
    xlo, xhi, ylo, yhi = -15.0 * diameter, 25.0 * diameter, -15.0 * diameter, 15.0 * diameter
    vertices = [(xlo, ylo, 0.0), (xhi, ylo, 0.0), (xhi, yhi, 0.0), (xlo, yhi, 0.0), (xlo, ylo, span), (xhi, ylo, span), (xhi, yhi, span), (xlo, yhi, span)]
    vertex_text = "\n".join(f"    ({x:.16g} {y:.16g} {z:.16g})" for x, y, z in vertices)
    text = "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object blockMeshDict;\n}\n\nconvertToMeters 1;\n\nvertices\n(\n" + vertex_text + "\n);\n\nblocks\n(\n" + f"    hex (0 1 2 3 4 5 6 7) ({nx} {ny} 1) simpleGrading (1 1 1)\n" + ");\n\nedges\n(\n);\n\nboundary\n(\n    inlet { type patch; faces ((0 3 7 4)); }\n    outlet { type patch; faces ((1 5 6 2)); }\n    bottom { type symmetryPlane; faces ((0 4 5 1)); }\n    top { type symmetryPlane; faces ((3 2 6 7)); }\n    frontAndBack { type empty; faces ((0 1 2 3) (4 7 6 5)); }\n);\n\nmergePatchPairs\n(\n);\n"
    spacing = {"x": (xhi - xlo) / nx, "y": (yhi - ylo) / ny}
    return text, {"mesh_type": "deterministic_uniform_cartesian_blockMesh", "vertices": [[x, y, z] for x, y, z in vertices], "cells": [nx, ny, 1], "total_cells": nx * ny, "actual_in_plane_spacing_m": {"min": min(spacing.values()), "max": max(spacing.values()), **spacing}, "outer_domain_m": {"x": [xlo, xhi], "y": [ylo, yhi]}}


def _circular_area_fraction_field(diameter: float, nx: int, ny: int, *, rule: str) -> tuple[list[float], dict[str, Any]]:
    """Return fixed 16x16 midpoint fractions in blockMesh x-fastest order."""

    if rule != "fixed_16x16_midpoint_subcells":
        raise ValueError("unsupported B2 area fraction rule")
    radius, xlo, xhi, ylo, yhi = diameter / 2.0, -15.0 * diameter, 25.0 * diameter, -15.0 * diameter, 15.0 * diameter
    dx, dy = (xhi - xlo) / nx, (yhi - ylo) / ny
    fractions: list[float] = []
    boundary_cells = 0
    offsets = tuple((index + 0.5) / 16.0 for index in range(16))
    for j in range(ny):
        ya, yb = ylo + j * dy, ylo + (j + 1) * dy
        for i in range(nx):
            xa, xb = xlo + i * dx, xlo + (i + 1) * dx
            near_x = 0.0 if xa <= 0.0 <= xb else min(abs(xa), abs(xb))
            near_y = 0.0 if ya <= 0.0 <= yb else min(abs(ya), abs(yb))
            far_x, far_y = max(abs(xa), abs(xb)), max(abs(ya), abs(yb))
            if far_x * far_x + far_y * far_y <= radius * radius:
                fraction = 1.0
            elif near_x * near_x + near_y * near_y >= radius * radius:
                fraction = 0.0
            else:
                boundary_cells += 1
                hits = sum(1 for oy in offsets for ox in offsets if (xa + ox * dx) ** 2 + (ya + oy * dy) ** 2 <= radius * radius)
                fraction = hits / 256.0
            fractions.append(fraction)
    return fractions, {"field": "beta", "meaning": "dimensionless_circular_solid_area_fraction_one_is_solid", "algorithm": "fixed_16x16_midpoint_subcells", "subcells_per_cell": 256, "cell_order": "blockMesh_x_fastest_then_y", "count": len(fractions), "boundary_cell_count": boundary_cells, "disk_radius_m": radius, "cell_size_m": {"x": dx, "y": dy}, "area_fraction_sha256": _sha256_json(fractions)}


def _control_dict(spec: Mapping[str, Any], *, representation: str, phase: str) -> str:
    rho = float(_mapping(spec["physics"], "physics")["density_kg_m3"])
    library = "" if representation == "body_fitted" else "\nlibs (\"./lib/%s\");\n" % _mapping(spec["extension"], "extension")["library"]
    if phase == "phase_a":
        return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object controlDict;\n}\n\napplication simpleFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 4000;\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval 4000;\nwriteAtEnd yes;\npurgeWrite 0;\nwriteFormat ascii;\nwritePrecision 12;\nrunTimeModifiable false;\n" + library
    if phase != "phase_b":
        raise ValueError(f"unsupported B2 cylinder phase: {phase}")
    function = _measurement_functions(spec, representation=representation, rho=rho)
    # Phase B is intentionally a 200-step evidence tail.  The explicit
    # timeStep/1 write contract is needed for the exact log/history evidence;
    # do not substitute writeAtEnd, which cannot establish this sequence.
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object controlDict;\n}\n\napplication simpleFoam;\nstartFrom latestTime;\nstartTime 0;\nstopAt endTime;\nendTime __PHASE_B_END_TIME__;\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval 1;\npurgeWrite 1;\nwriteFormat ascii;\nwritePrecision 12;\nrunTimeModifiable false;\n" + library + function


def _measurement_functions(spec: Mapping[str, Any], *, representation: str, rho: float) -> str:
    diameter = float(_mapping(spec["geometry"], "geometry")["diameter_m"])
    probe_locations = "\n".join(
        f"            ({0.75 * diameter * cos(theta * pi / 180.0):.16g} {0.75 * diameter * sin(theta * pi / 180.0):.16g} 0)"
        for theta in _SECTOR_ANGLES_DEG
    )
    probes = "\n    pressureProbes\n    {\n        type probes;\n        libs (\"libsampling.so\");\n        fields (p);\n        probeLocations\n        (\n" + probe_locations + "\n        );\n        writeControl timeStep;\n        writeInterval 1;\n    }\n"
    if representation == "porous_cartesian":
        force = "\n    porousResistance\n    {\n        type volFieldValue;\n        libs (\"libfieldFunctionObjects.so\");\n        operation volIntegrate;\n        fields (brinkmanResistance);\n        writeControl timeStep;\n        writeInterval 1;\n    }\n"
    else:
        force = (
        "\nfunctions\n{\n    cylinderForces\n    {\n        type forces;\n        libs (\"libforces.so\");\n        patches (cylinder);\n        rho rhoInf;\n        rhoInf %.16g;\n        CofR (0 0 0);\n        writeControl timeStep;\n        writeInterval 1;\n    }\n}\n" % rho
        )
        # The body case's force object retains its own function wrapper.
        return force[:-3] + probes + "}\n"
    return "\nfunctions\n{" + force + probes + "}\n"


def _fv_schemes() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object fvSchemes;\n}\n\nddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\ndivSchemes { default none; div(phi,U) Gauss linear; div((nuEff*dev2(T(grad(U))))) Gauss linear; }\nlaplacianSchemes { default Gauss linear corrected; }\ninterpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\nwallDist { method meshWave; }\n"


def _fv_solution(*, phase: str) -> str:
    residual = "    residualControl { p 1e-8; U 1e-8; }\n" if phase == "phase_a" else ""
    if phase not in {"phase_a", "phase_b"}:
        raise ValueError(f"unsupported B2 cylinder phase: {phase}")
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object fvSolution;\n}\n\nsolvers\n{\n    p { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-10; relTol 0; }\n}\nSIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n    pRefCell 0;\n    pRefValue 0;\n" + residual + "}\nrelaxationFactors\n{\n    fields { p 0.3; }\n    equations { U 0.7; }\n}\n"


def _transport_properties(nu: float) -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object transportProperties;\n}\n\ntransportModel Newtonian;\nnu [0 2 -1 0 0 0 0] %.16g;\n" % nu


def _turbulence_properties() -> str:
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object turbulenceProperties;\n}\n\nsimulationType laminar;\n"


def _velocity_field(uinf: float, *, representation: str) -> str:
    wall = "    cylinder { type noSlip; }\n" if representation == "body_fitted" else ""
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class volVectorField;\n    object U;\n}\n\ndimensions [0 1 -1 0 0 0 0];\ninternalField uniform (%.16g 0 0);\nboundaryField\n{\n    inlet { type fixedValue; value uniform (%.16g 0 0); }\n    outlet { type zeroGradient; }\n    top { type symmetryPlane; }\n    bottom { type symmetryPlane; }\n%s    frontAndBack { type empty; }\n}\n" % (uinf, uinf, wall)


def _pressure_field(*, representation: str) -> str:
    wall = "    cylinder { type zeroGradient; }\n" if representation == "body_fitted" else ""
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class volScalarField;\n    object p;\n}\n\ndimensions [0 2 -2 0 0 0 0];\ninternalField uniform 0;\nboundaryField\n{\n    inlet { type zeroGradient; }\n    outlet { type fixedValue; value uniform 0; }\n    top { type symmetryPlane; }\n    bottom { type symmetryPlane; }\n%s    frontAndBack { type empty; }\n}\n" % wall


def _scalar_field(name: str, values: Sequence[float]) -> str:
    rows = "\n".join("        " + " ".join(f"{value:.16g}" for value in values[index:index + 8]) for index in range(0, len(values), 8))
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class volScalarField;\n    object %s;\n}\n\ndimensions [0 0 0 0 0 0 0];\ninternalField nonuniform List<scalar>\n%d\n(\n%s\n);\nboundaryField\n{\n    inlet { type zeroGradient; }\n    outlet { type zeroGradient; }\n    top { type symmetryPlane; }\n    bottom { type symmetryPlane; }\n    frontAndBack { type empty; }\n}\n" % (name, len(values), rows)


def _brinkman_fv_options(spec: Mapping[str, Any]) -> str:
    ext = _mapping(spec["extension"], "extension")
    return "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object fvOptions;\n}\n\n%s\n{\n    type %s;\n    active yes;\n    selectionMode all;\n    U U;\n    betaField %s;\n    betaMax [0 0 -1 0 0 0 0] %.16g;\n    resistanceField brinkmanResistance;\n}\n" % (ext["option_name"], ext["fv_option_type"], ext["area_fraction_field"], float(ext["beta_max_m_inv_s"]))


def _allrun(*, porous: bool) -> str:
    phase_a_log = _phase_artifact("phase_a")["solver_log_filename"]
    phase_b_log = _phase_artifact("phase_b")["solver_log_filename"]
    materialize_beta = "" if not porous else "test -f 0/beta\ntest -d \"$phase_a_time\"\ncp 0/beta \"$phase_a_time/beta\"\n"
    return f"#!/usr/bin/env bash\nset -eu\ncp system/controlDict.phaseA system/controlDict\ncp system/fvSolution.phaseA system/fvSolution\nblockMesh > log.blockMesh 2>&1\ncheckMesh -allGeometry -allTopology > log.checkMesh 2>&1\nsimpleFoam > {phase_a_log} 2>&1\nphase_a_time=$(foamListTimes -latestTime)\n{materialize_beta}phase_b_end=$(awk -v start=\"$phase_a_time\" 'BEGIN {{ printf \"%.12g\", start + 200 }}')\nsed \"s/__PHASE_B_END_TIME__/$phase_b_end/\" system/controlDict.phaseB.template > system/controlDict.phaseB\ncp system/controlDict.phaseB system/controlDict\ncp system/fvSolution.phaseB system/fvSolution\nsimpleFoam > {phase_b_log} 2>&1\n"


def _allclean() -> str:
    phase_a = _phase_artifact("phase_a")
    phase_b = _phase_artifact("phase_b")
    return f"#!/usr/bin/env bash\nset -eu\nrm -rf constant/polyMesh [1-9]* 0/uniform lib log.blockMesh log.checkMesh {phase_a['solver_log_filename']} {phase_b['solver_log_filename']} log.extension-build log.extension-foam-environment {phase_a['final_time_filename']} {phase_b['final_time_filename']}\n"


def _force_and_probe_contract(spec: Mapping[str, Any]) -> dict[str, Any]:
    geometry, physics = _mapping(spec["geometry"], "geometry"), _mapping(spec["physics"], "physics")
    diameter = float(geometry["diameter_m"])
    return {"body_fitted_force": {"patch": "cylinder", "components": ["pressure", "viscous", "total"], "positive_streamwise_force": "drag", "coefficient": "Cd=Fx/(0.5*rho*Uinf^2*D*Lz)"}, "porous_force": {"components": ["total_linear_brinkman_resistance_only"], "prohibited_labels": ["pressure_drag", "skin_friction_drag"]}, "cp_probes": [{"theta_deg": theta, "x_m": 0.75 * diameter * cos(theta * pi / 180.0), "y_m": 0.75 * diameter * sin(theta * pi / 180.0)} for theta in _SECTOR_ANGLES_DEG], "cp": {"formula": "Cp=(p-pInfinity)/(0.5*Uinf^2)", "pressure": "kinematic", "reference_pressure": 0.0, "interpolation": "must_be_declared_by_evidence_extractor"}, "reynolds_number": float(physics["freestream_velocity_mps"]) * diameter / float(physics["kinematic_viscosity_m2_s"])}


def _runtime_evidence_requirements() -> dict[str, Any]:
    return {
        "all_cases_required": [f"{rep}/{grid}" for rep in _REPRESENTATIONS for grid in _GRID_IDS],
        "per_case": [
            "case_sha256", "dictionary_file_sha256", "mesh_hash", "image_digest", "command",
            "final_time", "fatal_log", "residual_history", "mass_balance", "stationarity",
            "phase_a_restart_archive_representation_specific_hashes", "phase_a_convergence_marker",
            "phase_b_active_control_timeStep_interval_1_purge_1",
            "phase_b_exact_final_time_fields_u_p", "phase_b_log_200_unique_step_times",
            "phase_b_force_and_probe_200_unique_history_rows", "case_evidence_manifest_tree_hash",
        ],
        "body_fitted": ["force_pressure_viscous_total", "eight_cp_probes", "three_grid_gci_inputs"],
        "porous": [
            "extension_source_hash", "extension_build_hash", "area_fraction_field_hash",
            "total_linear_brinkman_force", "eight_cp_probes", "phase_b_exact_final_time_brinkmanResistance",
            "phase_a_materialized_beta_origin_and_hash", "extension_source_build_load_assertions",
        ],
        "status_rule": "missing_or_unbound_evidence_is_inconclusive_not_qualified",
    }


def _phase_artifact(phase: str) -> Mapping[str, str]:
    """Return the single public artifact-name contract for one internal phase."""

    try:
        return _PHASE_RUNTIME_ARTIFACTS[phase]
    except KeyError as exc:
        raise ValueError(f"unsupported B2 cylinder phase: {phase}") from exc


def _two_phase_runtime_protocol() -> dict[str, dict[str, str]]:
    """Publish only the logs the generated two-phase scripts actually emit."""

    return {
        phase: {"solver_log_relpath": str(_phase_artifact(phase)["solver_log_filename"])}
        for phase in ("phase_a", "phase_b")
    }


def _extension_source_contract() -> dict[str, Any]:
    """Hash build inputs only; never allow an incidental local `.so` to bind it."""

    root = Path(__file__).resolve().parents[2] / "openfoam_extensions" / "cfdSdfLinearBrinkman"
    relative_paths = ("cfdSdfLinearBrinkman.C", "cfdSdfLinearBrinkman.H", "Make/files", "Make/options")
    entries: list[dict[str, str]] = []
    for relative in relative_paths:
        source = root / relative
        if not source.is_file():
            raise ValueError(f"required project-owned Brinkman extension source is missing: {source}")
        entries.append({"path": relative, "sha256": _sha256_file(source)})
    return {
        "source_root": "openfoam_extensions/cfdSdfLinearBrinkman",
        "library": "libcfdSdfLinearBrinkman.so",
        "openfoam_version": "v2512",
        "source_files": entries,
        "source_tree_sha256": _sha256_json(entries),
        "build_hash_rule": "runtime_manifest_must_bind_compiled_library_sha256_and_exact_build_command",
    }


def _copy_extension_source_snapshot(
    compilation_root: Path, extension_source: Mapping[str, Any]
) -> dict[str, Any]:
    """Byte-copy the four build inputs and publish their source-only index."""

    source_root = Path(__file__).resolve().parents[2] / "openfoam_extensions" / "cfdSdfLinearBrinkman"
    snapshot = compilation_root / "extension_source"
    copied: list[dict[str, str]] = []
    for entry in extension_source["source_files"]:
        relative = str(_mapping(entry, "extension source file")["path"])
        source, target = source_root / relative, snapshot / relative
        if not source.is_file():
            raise ValueError(f"required Brinkman source vanished during compilation: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        digest = _sha256_file(target)
        if digest != entry["sha256"]:
            raise ValueError(f"Brinkman source snapshot hash mismatch: {relative}")
        copied.append({"path": relative, "sha256": digest})
    manifest = {
        "schema_version": 1,
        "kind": "g4_b2_cylinder_extension_source_snapshot",
        "source_root": "extension_source",
        "library": extension_source["library"],
        "openfoam_version": "v2512",
        "source_files": copied,
        "source_tree_sha256": _sha256_json(copied),
        "contains_prebuilt_library": False,
    }
    if manifest["source_tree_sha256"] != extension_source["source_tree_sha256"]:
        raise ValueError("copied Brinkman source tree hash does not match compilation contract")
    _write_json(compilation_root / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME, manifest)
    return manifest


def _verify_compiled_case_files(case_dir: Path, case: Mapping[str, Any]) -> None:
    files = case.get("file_sha256")
    if not isinstance(files, Mapping):
        raise ValueError("compiled B2 cylinder case has no file hash contract")
    for relative, expected in files.items():
        path = case_dir / str(relative)
        if not path.is_file() or _sha256_file(path) != expected:
            raise ValueError(f"compiled B2 cylinder case file hash mismatch: {case_dir}/{relative}")
    contract = case_dir / "cylinder_case_contract.json"
    if not contract.is_file() or _sha256_file(contract) != case.get("case_contract_sha256"):
        raise ValueError(f"compiled B2 cylinder case contract hash mismatch: {case_dir}")


def _verify_extension_source_snapshot(source_root: Path, index: Mapping[str, Any]) -> Path:
    contract = _mapping(index.get("extension_source_contract"), "extension_source_contract")
    provenance = _extension_snapshot_provenance(
        source_root / "extension_source",
        expected_manifest_sha256=str(index.get("extension_source_manifest_sha256", "")),
        expected_tree_sha256=str(contract.get("source_tree_sha256", "")),
    )
    if not provenance["complete"]:
        raise ValueError("B2 cylinder extension source snapshot is invalid: " + ",".join(provenance["missing_or_invalid"]))
    return source_root / "extension_source"


def _stage_extension_source_snapshot(
    source_root: Path, staging_root: Path, index: Mapping[str, Any], *, extension_snapshot: Path,
) -> Path:
    """Copy and re-verify the sole Phase-A extension source authority."""

    target_snapshot = staging_root / "extension_source"
    target_manifest = staging_root / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME
    if target_snapshot.exists() or target_manifest.exists():
        raise ValueError("fresh B2 cylinder runtime staging already contains extension snapshot material")
    shutil.copytree(extension_snapshot, target_snapshot)
    shutil.copy2(source_root / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME, target_manifest)
    # This checks both the copied manifest bytes and every copied source byte
    # against the immutable compilation contract before any Docker command is
    # formed.
    _verify_extension_source_snapshot(staging_root, index)
    return target_snapshot


def _extension_snapshot_provenance(
    snapshot_dir: Path | None, *, expected_manifest_sha256: str | None = None,
    expected_tree_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a fail-closed, hash-bound extension snapshot assertion set."""

    missing: list[str] = []
    manifest: dict[str, Any] = {}
    manifest_sha256: str | None = None
    snapshot_root = snapshot_dir.parent if snapshot_dir is not None else None
    manifest_path = snapshot_root / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME if snapshot_root is not None else None
    if snapshot_dir is None or not snapshot_dir.is_dir():
        missing.append("extension_source_snapshot_missing")
    if manifest_path is None or not manifest_path.is_file():
        missing.append("extension_source_manifest_missing")
    else:
        try:
            decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("manifest_not_mapping")
            manifest = decoded
            manifest_sha256 = _sha256_file(manifest_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            missing.append("extension_source_manifest_unreadable")
    if expected_manifest_sha256 and manifest_sha256 != expected_manifest_sha256:
        missing.append("extension_source_manifest_sha256_mismatch")
    entries = manifest.get("source_files")
    manifest_entries: list[dict[str, str]] = []
    if not isinstance(entries, list) or len(entries) != 4:
        missing.append("extension_source_manifest_file_set_invalid")
    else:
        seen_paths: set[str] = set()
        for raw in entries:
            if not isinstance(raw, Mapping) or not isinstance(raw.get("path"), str) or not isinstance(raw.get("sha256"), str):
                missing.append("extension_source_manifest_entry_invalid")
                continue
            relative, expected = str(raw["path"]), str(raw["sha256"])
            if not _is_safe_snapshot_relative_path(relative) or relative in seen_paths:
                missing.append(f"extension_source_manifest_entry_path_invalid:{relative}")
                continue
            seen_paths.add(relative)
            manifest_entries.append({"path": relative, "sha256": expected})

    actual_paths, filesystem_errors = _snapshot_regular_file_paths(snapshot_dir)
    missing.extend(filesystem_errors)
    manifest_paths = {entry["path"] for entry in manifest_entries}
    actual_path_set = set(actual_paths)
    for relative in sorted(actual_path_set - manifest_paths):
        missing.append(f"extension_source_snapshot_unlisted_file:{relative}")
    for relative in sorted(manifest_paths - actual_path_set):
        missing.append(f"extension_source_snapshot_missing_manifest_file:{relative}")

    observed_entries: list[dict[str, str]] = []
    if snapshot_dir is not None and actual_path_set == manifest_paths and not filesystem_errors:
        for entry in manifest_entries:
            relative, expected = entry["path"], entry["sha256"]
            source = snapshot_dir / relative
            # _snapshot_regular_file_paths() just proved this is a real regular
            # file inside the snapshot.  Hash the actual tree only after its
            # complete file set has been checked against the manifest.
            try:
                if _snapshot_entry_kind(source) != "regular":
                    missing.append(f"extension_source_snapshot_entry_changed:{relative}")
                    continue
                actual_sha256 = _sha256_file(source)
            except OSError:
                missing.append(f"extension_source_snapshot_entry_unreadable:{relative}")
                continue
            if actual_sha256 != expected:
                missing.append(f"extension_source_file_hash_mismatch:{relative}")
                continue
            observed_entries.append({"path": relative, "sha256": actual_sha256})
    observed_tree_sha256 = _sha256_json(observed_entries) if len(observed_entries) == len(manifest_entries) == 4 else None
    if observed_tree_sha256 is None or manifest.get("source_tree_sha256") != observed_tree_sha256:
        missing.append("extension_source_tree_hash_mismatch")
    if expected_tree_sha256 and observed_tree_sha256 != expected_tree_sha256:
        missing.append("extension_source_tree_contract_mismatch")
    if any(relative.endswith(".so") for relative in actual_paths):
        missing.append("extension_source_snapshot_contains_prebuilt_library")
    if manifest.get("contains_prebuilt_library") is not False:
        missing.append("extension_source_manifest_prebuilt_library_assertion_invalid")
    assertions = {
        "source_snapshot_present": snapshot_dir is not None and snapshot_dir.is_dir(),
        "source_manifest_present_and_readable": manifest_sha256 is not None,
        "source_manifest_sha256_bound": not expected_manifest_sha256 or manifest_sha256 == expected_manifest_sha256,
        "source_files_hash_bound": not any(item.startswith("extension_source_file_hash_mismatch") for item in missing),
        "source_files_exact_set_bound": not any(
            item.startswith("extension_source_snapshot_unlisted_file")
            or item.startswith("extension_source_snapshot_missing_manifest_file")
            or item.startswith("extension_source_snapshot_reparse_point")
            or item.startswith("extension_source_snapshot_special_file")
            or item.startswith("extension_source_snapshot_entry_unreadable")
            or item.startswith("extension_source_snapshot_entry_changed")
            for item in missing
        ),
        "source_tree_sha256_bound": observed_tree_sha256 is not None and manifest.get("source_tree_sha256") == observed_tree_sha256 and (not expected_tree_sha256 or observed_tree_sha256 == expected_tree_sha256),
        "no_prebuilt_library": "extension_source_snapshot_contains_prebuilt_library" not in missing and manifest.get("contains_prebuilt_library") is False,
    }
    return {
        "complete": not missing and all(assertions.values()), "assertions": assertions,
        "missing_or_invalid": missing, "manifest_relpath": G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME,
        "manifest_sha256": manifest_sha256, "source_tree_sha256": observed_tree_sha256,
        "manifest": manifest,
    }


def _is_safe_snapshot_relative_path(relative: str) -> bool:
    """Accept only canonical, relative POSIX source paths from the manifest."""

    return bool(relative) and "\\" not in relative and not relative.startswith("/") and all(
        part not in {"", ".", ".."} for part in relative.split("/")
    )


def _snapshot_entry_kind(path: Path) -> str:
    """Classify one lstat() entry without following links or Windows reparse points."""

    details = os.lstat(path)
    attributes = int(getattr(details, "st_file_attributes", 0) or 0)
    if stat.S_ISLNK(details.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        return "reparse"
    if stat.S_ISDIR(details.st_mode):
        return "directory"
    if stat.S_ISREG(details.st_mode):
        return "regular"
    return "special"


def _snapshot_regular_file_paths(snapshot_dir: Path | None) -> tuple[list[str], list[str]]:
    """Enumerate real snapshot entries, rejecting links/reparse and special files.

    ``Path.rglob`` can hide traversal details and follows platform-specific
    directory semantics.  The source bundle is an immutable build input, so
    inspect every entry with ``lstat`` and descend only into proven directories.
    """

    if snapshot_dir is None:
        return [], []
    try:
        root_kind = _snapshot_entry_kind(snapshot_dir)
    except OSError:
        return [], ["extension_source_snapshot_entry_unreadable:."]
    if root_kind == "reparse":
        return [], ["extension_source_snapshot_reparse_point:."]
    if root_kind != "directory":
        return [], ["extension_source_snapshot_missing"] if root_kind == "special" else ["extension_source_snapshot_not_directory"]

    files: list[str] = []
    errors: list[str] = []
    pending = [snapshot_dir]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(Path(entry.path) for entry in os.scandir(directory))
        except OSError:
            relative = directory.relative_to(snapshot_dir).as_posix() if directory != snapshot_dir else "."
            errors.append(f"extension_source_snapshot_entry_unreadable:{relative}")
            continue
        for child in children:
            relative = child.relative_to(snapshot_dir).as_posix()
            try:
                kind = _snapshot_entry_kind(child)
            except OSError:
                errors.append(f"extension_source_snapshot_entry_unreadable:{relative}")
                continue
            if kind == "directory":
                pending.append(child)
            elif kind == "regular":
                files.append(relative)
            elif kind == "reparse":
                errors.append(f"extension_source_snapshot_reparse_point:{relative}")
            else:
                errors.append(f"extension_source_snapshot_special_file:{relative}")
    return sorted(files), errors


def _is_digest_pinned_v2512_image(image: str | None) -> bool:
    return isinstance(image, str) and bool(re.fullmatch(r"[^\s@]+@sha256:[0-9a-fA-F]{64}", image)) and "2512" in image


def _verify_porous_case_semantics(case_dir: Path) -> None:
    """Parse fixed fvOptions meanings; matching hashes alone is insufficient."""

    control = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    fv_options = (case_dir / "constant" / "fvOptions").read_text(encoding="utf-8")
    if not re.search(r'libs\s*\(\s*"\./lib/libcfdSdfLinearBrinkman\.so"\s*\)\s*;', control):
        raise ValueError("porous controlDict must load only the case-local Brinkman library")
    match = re.search(r"porousCylinderResistance\s*\{(?P<body>.*?)\}", fv_options, flags=re.DOTALL)
    if not match:
        raise ValueError("porous fvOptions has no porousCylinderResistance entry")
    body = match.group("body")
    required = {
        "type": r"\btype\s+cfdSdfLinearBrinkman\s*;",
        "active": r"\bactive\s+(?:yes|true)\s*;",
        "selectionMode": r"\bselectionMode\s+all\s*;",
        "U": r"\bU\s+U\s*;",
        "betaField": r"\bbetaField\s+beta\s*;",
        "betaMax": r"\bbetaMax\s+\[\s*0\s+0\s+-1\s+0\s+0\s+0\s+0\s*\]\s+(?:150000(?:\.0*)?|1\.5e\+?5)\s*;",
        "resistanceField": r"\bresistanceField\s+brinkmanResistance\s*;",
    }
    invalid = [name for name, pattern in required.items() if not re.search(pattern, body)]
    if invalid:
        raise ValueError("porous fvOptions semantic contract mismatch: " + ",".join(invalid))
    beta = (case_dir / "0" / "beta").read_text(encoding="utf-8")
    if "dimensions [0 0 0 0 0 0 0];" not in beta:
        raise ValueError("porous beta field must be dimensionless")


def _run_cylinder_case_two_phase(
    case_dir: Path, *, representation: str, grid_id: str, snapshot_dir: Path | None,
    case_relpath: Path, execute: bool, docker_image: str | None,
    expected_snapshot_manifest_sha256: str | None = None,
    expected_snapshot_tree_sha256: str | None = None,
) -> dict[str, Any]:
    """Run exactly A then B; B is never started after an A failure."""

    rel = case_relpath.as_posix()
    timeouts = _PHASE_TIMEOUTS_SECONDS[grid_id]
    phase_a = _phase_manifest(case_dir, phase="phase_a", timeout_seconds=timeouts["phase_a"], image=docker_image)
    phase_b = _phase_manifest(case_dir, phase="phase_b", timeout_seconds=timeouts["phase_b"], image=docker_image)
    base: dict[str, Any] = {
        "backend": "docker", "dry_run": not execute, "published_case_relpath": rel,
        "stdout_relpath": f"{rel}/log.runOpenFOAM.stdout", "stderr_relpath": f"{rel}/log.runOpenFOAM.stderr",
        "summary_relpath": f"{rel}/openfoam_run_summary.json", "representation": representation,
        "grid_id": grid_id, "phase_a": phase_a, "phase_b": phase_b,
        "protocol": "g4_b2_cylinder_two_phase_runtime_v1",
        "solver_evaluation": _unevaluated_solver_evaluation_state(),
    }
    if not execute:
        base.update({"returncode": None, "timed_out": False, "error": None, "solver_error_logs": [], "ok": True, "command_executed": {"phase_a": phase_a["canonical_container_command"], "phase_b": phase_b["canonical_container_command"]}, "command_executed_sha256": _sha256_json([phase_a["canonical_container_command"], phase_b["canonical_container_command"]]), "replay_command": {"phase_a": phase_a["canonical_container_command"], "phase_b": phase_b["canonical_container_command"]}})
        if representation == "porous_cartesian":
            base["extension"] = _not_executed_extension_contract(case_dir, snapshot_dir, rel)
        return base

    assert docker_image is not None
    snapshot_provenance: dict[str, Any] | None = None
    if representation == "porous_cartesian":
        snapshot_provenance = _extension_snapshot_provenance(
            snapshot_dir,
            expected_manifest_sha256=expected_snapshot_manifest_sha256,
            expected_tree_sha256=expected_snapshot_tree_sha256,
        )
        if not snapshot_provenance["complete"]:
            phase_a.update({
                "ok": False, "status": "failed",
                "error": "porous_extension_snapshot_provenance_failed",
                "snapshot_provenance": snapshot_provenance,
            })
            base["extension"] = _extension_runtime_contract(
                case_dir, snapshot_dir, rel, docker_image, phase_a, None,
                expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
                expected_snapshot_tree_sha256=expected_snapshot_tree_sha256,
                snapshot_provenance=snapshot_provenance,
            )
            base.update(_two_phase_terminal(base, phase_a, phase_b, failed_phase="phase_a"))
            return base
    phase_a_result = _run_docker_phase(
        case_dir, phase="phase_a", representation=representation, snapshot_dir=snapshot_dir,
        image=docker_image, timeout_seconds=timeouts["phase_a"], case_relpath=case_relpath,
    )
    phase_a.update(phase_a_result)
    if not phase_a_result["ok"]:
        base.update(_two_phase_terminal(base, phase_a, phase_b, failed_phase="phase_a"))
        if representation == "porous_cartesian":
            base["extension"] = _extension_runtime_contract(
                case_dir, snapshot_dir, rel, docker_image, phase_a, None,
                expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
                expected_snapshot_tree_sha256=expected_snapshot_tree_sha256,
                snapshot_provenance=snapshot_provenance,
            )
        return base
    start = _read_phase_time(case_dir / "runtime_phase_a_final_time.txt")
    phase_a["final_time"] = start
    phase_a["control_dict_active_relpath"] = "system/controlDict"
    phase_a["control_dict_active_sha256"] = _sha256_file(case_dir / "system" / "controlDict")
    restart_archive = _archive_phase_a_restart_fields(
        case_dir, start, porous=representation == "porous_cartesian",
        beta_origin_sha256=phase_a.get("beta_origin_sha256"),
    )
    phase_a["restart_archive"] = restart_archive
    if not restart_archive["complete"]:
        phase_a["ok"] = False
        phase_a["status"] = "failed"
        phase_a["error"] = "phase_a_restart_archive_failed"
        base.update(_two_phase_terminal(base, phase_a, phase_b, failed_phase="phase_a"))
        if representation == "porous_cartesian":
            base["extension"] = _extension_runtime_contract(
                case_dir, snapshot_dir, rel, docker_image, phase_a, None,
                expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
                expected_snapshot_tree_sha256=expected_snapshot_tree_sha256,
                snapshot_provenance=snapshot_provenance,
            )
        return base
    phase_b_result = _run_docker_phase(
        case_dir, phase="phase_b", representation=representation, snapshot_dir=None,
        image=docker_image, timeout_seconds=timeouts["phase_b"], case_relpath=case_relpath,
        phase_start_time=start,
    )
    phase_b.update(phase_b_result)
    final_fields = phase_b_result.get("final_fields")
    if isinstance(final_fields, Mapping) and isinstance(final_fields.get("active_control"), Mapping):
        phase_b["active_control"] = dict(final_fields["active_control"])
    final = _read_phase_time(case_dir / "runtime_phase_b_final_time.txt") if phase_b_result["ok"] else None
    if final is not None:
        phase_b["start_time"] = start
        phase_b["final_time"] = final
        phase_b["control_dict_active_relpath"] = "system/controlDict.phaseB"
        phase_b["control_dict_active_sha256"] = _sha256_file(case_dir / "system" / "controlDict.phaseB") if (case_dir / "system" / "controlDict.phaseB").is_file() else None
        phase_b["expected_final_time"] = start + 200.0
        phase_b["exact_200_iterations"] = abs(final - (start + 200.0)) <= 1.0e-9
        phase_b["phase_a_restart_archive"] = _verify_phase_a_restart_archive(case_dir, restart_archive)
        phase_b["log_time_contract"] = _phase_b_log_time_contract(
            case_dir / _phase_artifact("phase_b")["solver_log_filename"], start=start, end=final,
        )
        if not phase_b["exact_200_iterations"] or not phase_b["phase_a_restart_archive"]["complete"] or not phase_b["log_time_contract"]["complete"]:
            phase_b["ok"] = False
            if not phase_b["exact_200_iterations"]:
                phase_b["error"] = "phase_b_did_not_run_exactly_200_iterations"
            elif not phase_b["phase_a_restart_archive"]["complete"]:
                phase_b["error"] = "phase_a_restart_archive_hash_mismatch_after_phase_b"
            else:
                phase_b["error"] = "phase_b_log_time_contract_failed"
    extension: dict[str, Any] | None = None
    if representation == "porous_cartesian":
        extension = _extension_runtime_contract(
            case_dir, snapshot_dir, rel, docker_image, phase_a, phase_b,
            expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
            expected_snapshot_tree_sha256=expected_snapshot_tree_sha256,
            snapshot_provenance=snapshot_provenance,
        )
        base["extension"] = extension
        if not extension.get("complete"):
            phase_b["ok"] = False
            phase_b["status"] = "failed"
            phase_b["error"] = "porous_extension_source_build_load_assertions_failed"
    evidence = _bind_case_evidence(
        case_dir, representation=representation, case_relpath=case_relpath, image=docker_image,
        phase_a=phase_a, phase_b=phase_b, extension=extension,
    )
    base["case_evidence"] = evidence
    if not evidence.get("complete"):
        phase_b["ok"] = False
        phase_b["status"] = "failed"
        phase_b["error"] = "case_evidence_manifest_incomplete"
    all_ok = bool(phase_a.get("ok")) and bool(phase_b.get("ok"))
    base.update(_two_phase_terminal(base, phase_a, phase_b, failed_phase=None if all_ok else "phase_b"))
    return base


def _phase_manifest(case_dir: Path, *, phase: str, timeout_seconds: int, image: str | None) -> dict[str, Any]:
    artifacts = _phase_artifact(phase)
    if phase == "phase_a":
        control, solution = case_dir / "system" / "controlDict.phaseA", case_dir / "system" / "fvSolution.phaseA"
        template = None
    else:
        control, solution = case_dir / "system" / "controlDict.phaseB.template", case_dir / "system" / "fvSolution.phaseB"
        template = "system/controlDict.phaseB.template"
    manifest = {
        "phase": phase, "status": "planned", "timeout_seconds": timeout_seconds,
        "control_dict_source_relpath": str(control.relative_to(case_dir)).replace("\\", "/"),
        "control_dict_source_sha256": _sha256_file(control),
        "fv_solution_relpath": str(solution.relative_to(case_dir)).replace("\\", "/"),
        "fv_solution_sha256": _sha256_file(solution), "phase_b_template_relpath": template,
        "solver_log_relpath": str(artifacts["solver_log_filename"]),
        "canonical_container_command": _canonical_phase_container_command(phase, str(image) if image else "<digest-pinned-image>", porous=(case_dir / "constant" / "fvOptions").is_file()),
    }
    if phase == "phase_a" and (case_dir / "constant" / "fvOptions").is_file():
        beta = case_dir / "0" / "beta"
        manifest["beta_origin_relpath"] = "0/beta"
        manifest["beta_origin_sha256"] = _sha256_file(beta) if beta.is_file() else None
    return manifest


def _run_docker_phase(
    case_dir: Path, *, phase: str, representation: str, snapshot_dir: Path | None,
    image: str, timeout_seconds: int, case_relpath: Path, phase_start_time: float | None = None,
) -> dict[str, Any]:
    porous = representation == "porous_cartesian"
    if (phase == "phase_a" and porous != (snapshot_dir is not None)) or (phase == "phase_b" and snapshot_dir is not None):
        raise ValueError("only porous phase A may receive the immutable extension snapshot")
    script = _phase_container_script(phase, porous=porous)
    command = ["docker", "run", "--rm", "--entrypoint", "bash", "--mount", f"type=bind,source={case_dir.resolve()},target=/case"]
    if snapshot_dir is not None:
        command.extend(["--mount", f"type=bind,source={snapshot_dir.resolve()},target=/extension-source,readonly"])
    command.extend(["-w", "/case", image, "-lc", script])
    stdout = case_dir / f"log.runOpenFOAM.{phase}.stdout"
    stderr = case_dir / f"log.runOpenFOAM.{phase}.stderr"
    try:
        with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
            completed = subprocess.run(command, cwd=case_dir, stdout=out, stderr=err, text=True, timeout=timeout_seconds, check=False)
        returncode, timed_out, error = int(completed.returncode), False, None
    except subprocess.TimeoutExpired as exc:
        returncode, timed_out, error = None, True, f"phase {phase} timed out after {exc.timeout} seconds"
        stderr.write_text(error, encoding="utf-8")
    except OSError as exc:
        returncode, timed_out, error = None, False, str(exc)
        stderr.write_text(error, encoding="utf-8")
    artifacts = _phase_artifact(phase)
    solver_log = case_dir / artifacts["solver_log_filename"]
    final_file = case_dir / artifacts["final_time_filename"]
    required_fields = _phase_required_fields(
        case_dir, final_file, phase=phase, require_measurements=phase == "phase_b", porous=porous,
        phase_start_time=phase_start_time,
    )
    fatal = _solver_log_has_fatal(solver_log)
    convergence = _phase_a_convergence_contract(solver_log, required_fields) if phase == "phase_a" else None
    ok = returncode == 0 and not timed_out and error is None and solver_log.is_file() and not fatal and required_fields["complete"] and (convergence is None or convergence["complete"])
    result = {"status": "completed" if ok else "failed", "returncode": returncode, "timed_out": timed_out, "error": error, "ok": ok, "stdout_relpath": f"{case_relpath.as_posix()}/{stdout.name}", "stderr_relpath": f"{case_relpath.as_posix()}/{stderr.name}", "solver_log_relpath": f"{case_relpath.as_posix()}/{solver_log.name}", "solver_log_sha256": _sha256_file(solver_log) if solver_log.is_file() else None, "fatal_log_clear": not fatal, "final_fields": required_fields, "replay_command": _canonical_phase_container_command(phase, image, porous=porous)}
    if convergence is not None:
        result["convergence"] = convergence
    return result


def _phase_container_script(phase: str, *, porous: bool) -> str:
    preamble = ". /usr/lib/openfoam/openfoam2512/etc/bashrc\nset -eu\n"
    build = "" if not porous else "build_dir=$(mktemp -d /tmp/cfd-sdf-brinkman.XXXXXX)\ntrap 'rm -rf \"$build_dir\"' EXIT\ntest ! -e \"$build_dir/lib/libcfdSdfLinearBrinkman.so\"\ncp -a /extension-source/. \"$build_dir/\"\ntest ! -e \"$build_dir/lib/libcfdSdfLinearBrinkman.so\"\nexport FOAM_USER_LIBBIN=\"$build_dir/lib\"\ncd \"$build_dir\"\nwmake libso > /case/log.extension-build 2>&1\ntest -f \"$FOAM_USER_LIBBIN/libcfdSdfLinearBrinkman.so\"\ntest ! -e /case/lib/libcfdSdfLinearBrinkman.so\nmkdir -p /case/lib\ncp \"$FOAM_USER_LIBBIN/libcfdSdfLinearBrinkman.so\" /case/lib/libcfdSdfLinearBrinkman.so\ncd /case\n"
    if phase == "phase_a":
        artifacts = _phase_artifact(phase)
        materialize_beta = "" if not porous else "phase_a_time=$(foamListTimes -latestTime)\ntest -f 0/beta\ntest -d \"$phase_a_time\"\ncp 0/beta \"$phase_a_time/beta\"\nprintf '%s\\n' \"$phase_a_time\" > " + artifacts["final_time_filename"] + "\n"
        time_capture = "foamListTimes -latestTime > " + artifacts["final_time_filename"] + "\ntest -s " + artifacts["final_time_filename"] + "\n"
        return preamble + build + f"cp system/controlDict.phaseA system/controlDict\ncp system/fvSolution.phaseA system/fvSolution\nblockMesh > log.blockMesh 2>&1\ncheckMesh -allGeometry -allTopology > log.checkMesh 2>&1\nsimpleFoam > {artifacts['solver_log_filename']} 2>&1\n" + (materialize_beta if porous else time_capture)
    if phase == "phase_b" and not porous:
        return preamble + _phase_b_tail_script()
    if phase == "phase_b" and porous:
        return preamble + _phase_b_tail_script()
    raise ValueError(f"unsupported B2 cylinder phase: {phase}")


def _phase_b_tail_script() -> str:
    phase_a = _phase_artifact("phase_a")
    phase_b = _phase_artifact("phase_b")
    return f"test -s {phase_a['final_time_filename']}\nphase_a_time=$(cat {phase_a['final_time_filename']})\nphase_b_end=$(awk -v start=\"$phase_a_time\" 'BEGIN {{ printf \"%.12g\", start + 200 }}')\nsed \"s/__PHASE_B_END_TIME__/$phase_b_end/\" system/controlDict.phaseB.template > system/controlDict.phaseB\ncp system/controlDict.phaseB system/controlDict\ncp system/fvSolution.phaseB system/fvSolution\nsimpleFoam > {phase_b['solver_log_filename']} 2>&1\nfoamListTimes -latestTime > {phase_b['final_time_filename']}\ntest -s {phase_b['final_time_filename']}\n"


def _canonical_phase_container_command(phase: str, image: str, *, porous: bool) -> list[str]:
    command = ["docker", "run", "--rm", "--entrypoint", "bash", "--mount", "type=bind,source=<case-runtime>,target=/case"]
    if porous and phase == "phase_a":
        command.extend(["--mount", "type=bind,source=<immutable-extension-source>,target=/extension-source,readonly"])
    return command + ["-w", "/case", image, "-lc", _phase_container_script(phase, porous=porous)]


def _phase_required_fields(
    case_dir: Path, final_file: Path, *, phase: str, require_measurements: bool, porous: bool,
    phase_start_time: float | None,
) -> dict[str, Any]:
    try:
        time_name = final_file.read_text(encoding="utf-8").strip()
        float(time_name)
    except (OSError, ValueError):
        return {"complete": False, "reason": "missing_or_invalid_final_time"}
    time_dir = case_dir / time_name
    required_names = _PHASE_A_RESTART_FIELDS if phase == "phase_a" else _PHASE_B_FINAL_FIELDS
    required = {name: (time_dir / name).is_file() for name in required_names}
    if phase == "phase_a" and porous:
        required["beta"] = (time_dir / "beta").is_file()
    if phase == "phase_b" and porous:
        required["brinkmanResistance"] = (time_dir / "brinkmanResistance").is_file()
    active_control: dict[str, Any] | None = None
    if phase == "phase_b":
        active_control = _phase_b_active_control_contract(case_dir / "system" / "controlDict.phaseB")
        required["active_control_timeStep_interval_1_purge_1"] = active_control["complete"]
    if require_measurements:
        function = "porousResistance" if porous else "cylinderForces"
        expected = _expected_phase_b_times(phase_start_time) if phase_start_time is not None else None
        probes = _history_time_contract(case_dir / "postProcessing" / "pressureProbes", expected)
        forces = _history_time_contract(case_dir / "postProcessing" / function, expected)
        required["pressure_probes_200_unique_rows"] = probes["complete"]
        required["force_history_200_unique_rows"] = forces["complete"]
    result: dict[str, Any] = {"complete": all(required.values()), "time": time_name, "required_files": required}
    if active_control is not None:
        result["active_control"] = active_control
    if require_measurements:
        result["measurement_history"] = {"pressure_probes": probes, "force": forces}
    return result


def _phase_a_convergence_contract(solver_log: Path, final_fields: Mapping[str, Any]) -> dict[str, Any]:
    """Require the solver's explicit SIMPLE convergence declaration, never an inferred threshold."""

    text = solver_log.read_text(encoding="utf-8", errors="ignore") if solver_log.is_file() else ""
    match = re.search(r"(?m)^\s*SIMPLE solution converged in\s+(\d+)\s+iterations\s*$", text)
    try:
        final_time = float(final_fields.get("time"))
    except (TypeError, ValueError):
        final_time = float("nan")
    checks = {
        "simple_solution_converged_marker": match is not None,
        "final_time_finite_and_at_most_4000": isfinite(final_time) and 0.0 <= final_time <= 4000.0,
        "required_phase_a_fields": bool(final_fields.get("complete")),
    }
    return {
        "complete": all(checks.values()), "checks": checks,
        "iterations": int(match.group(1)) if match is not None else None,
        "solver_log_sha256": _sha256_file(solver_log) if solver_log.is_file() else None,
        "final_time": final_time if isfinite(final_time) else None,
    }


def _phase_b_active_control_contract(path: Path) -> dict[str, Any]:
    """Bind the rendered Phase-B control, not merely its source template hash."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"complete": False, "reason": "missing_active_phase_b_control", "relpath": "system/controlDict.phaseB", "sha256": None}
    checks = {
        "write_control_timeStep": bool(re.search(r"\bwriteControl\s+timeStep\s*;", text)),
        "write_interval_1": bool(re.search(r"\bwriteInterval\s+1\s*;", text)),
        "purge_write_1": bool(re.search(r"\bpurgeWrite\s+1\s*;", text)),
        "write_at_end_absent": not bool(re.search(r"\bwriteAtEnd\b", text)),
    }
    return {
        "complete": all(checks.values()), "relpath": "system/controlDict.phaseB",
        "sha256": _sha256_file(path), "checks": checks,
    }


def _expected_phase_b_times(start: float) -> tuple[float, ...] | None:
    """Return the one-based 200-step tail only for an integral solver time."""

    if not isfinite(start) or abs(start - round(start)) > 1.0e-9:
        return None
    initial = int(round(start))
    return tuple(float(initial + offset) for offset in range(1, _PHASE_B_MEASUREMENT_ROWS + 1))


def _numeric_time_rows(path: Path) -> list[float]:
    """Read OpenFOAM function-object rows whose first token is a time value."""

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    rows: list[float] = []
    for line in lines:
        match = re.match(r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\b", line)
        if match is None:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if isfinite(value):
            rows.append(value)
    return rows


def _time_rows_contract(rows: Sequence[float], expected: Sequence[float] | None) -> dict[str, Any]:
    if expected is None:
        return {"complete": False, "reason": "missing_or_nonintegral_phase_b_start_time"}
    counts: dict[float, int] = {}
    for value in rows:
        counts[value] = counts.get(value, 0) + 1
    expected_counts = {value: counts.get(value, 0) for value in expected}
    unexpected = sorted(value for value in counts if value not in set(expected))
    complete = len(rows) == len(expected) and not unexpected and all(count == 1 for count in expected_counts.values())
    return {
        "complete": complete, "expected_row_count": len(expected), "observed_row_count": len(rows),
        "expected_start": expected[0], "expected_end": expected[-1],
        "missing_times": [value for value, count in expected_counts.items() if count == 0],
        "duplicate_times": [value for value, count in counts.items() if count > 1],
        "unexpected_times": unexpected,
    }


def _history_time_contract(directory: Path, expected: Sequence[float] | None) -> dict[str, Any]:
    if not directory.is_dir():
        return {"complete": False, "reason": "missing_history_directory", "directory": directory.as_posix()}
    candidates: list[dict[str, Any]] = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        contract = _time_rows_contract(_numeric_time_rows(path), expected)
        contract["relpath"] = path.relative_to(directory).as_posix()
        candidates.append(contract)
    complete = next((item for item in candidates if item["complete"]), None)
    if complete is not None:
        return {"complete": True, "selected": complete, "candidates": candidates}
    return {"complete": False, "reason": "no_single_history_file_has_exact_200_unique_phase_b_times", "candidates": candidates}


def _phase_b_log_time_contract(path: Path, *, start: float, end: float) -> dict[str, Any]:
    expected = _expected_phase_b_times(start)
    if expected is None or not isfinite(end) or abs(end - expected[-1]) > 1.0e-9:
        return {"complete": False, "reason": "phase_b_end_does_not_match_exact_200_step_contract"}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"complete": False, "reason": "missing_phase_b_solver_log"}
    rows = [float(match.group(1)) for match in re.finditer(r"(?m)^\s*Time\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$", text)]
    return _time_rows_contract(rows, expected)


def _archive_phase_a_restart_fields(
    case_dir: Path, final_time: float, *, porous: bool = False, beta_origin_sha256: object = None,
) -> dict[str, Any]:
    """Copy Phase-A restart state outside time directories before B can purge it."""

    final_file = case_dir / _phase_artifact("phase_a")["final_time_filename"]
    try:
        time_name = final_file.read_text(encoding="utf-8").strip()
        if abs(float(time_name) - final_time) > 1.0e-9:
            raise ValueError("phase_a_final_time_mismatch")
    except (OSError, ValueError) as exc:
        return {"complete": False, "reason": "missing_or_invalid_phase_a_restart_time", "error": str(exc)}
    source_dir = case_dir / time_name
    archive_dir = case_dir / _PHASE_A_RESTART_ARCHIVE_RELATIVE / time_name
    manifest_path = case_dir / _PHASE_A_RESTART_ARCHIVE_MANIFEST_RELATIVE
    if archive_dir.exists() or manifest_path.exists():
        return {"complete": False, "reason": "phase_a_restart_archive_already_exists"}
    restart_fields = _PHASE_A_RESTART_FIELDS + (("beta",) if porous else ())
    missing = [name for name in restart_fields if not (source_dir / name).is_file()]
    if missing:
        return {"complete": False, "reason": "missing_phase_a_restart_field", "missing_fields": missing, "source_time": time_name}
    beta_provenance: dict[str, str] | None = None
    if porous:
        origin = case_dir / "0" / "beta"
        materialized = source_dir / "beta"
        origin_hash = _sha256_file(origin) if origin.is_file() else None
        materialized_hash = _sha256_file(materialized) if materialized.is_file() else None
        if not isinstance(beta_origin_sha256, str) or origin_hash != beta_origin_sha256 or materialized_hash != origin_hash:
            return {
                "complete": False, "reason": "phase_a_materialized_beta_does_not_match_immutable_origin",
                "origin_relpath": "0/beta", "expected_origin_sha256": beta_origin_sha256,
                "observed_origin_sha256": origin_hash, "materialized_sha256": materialized_hash,
            }
        beta_provenance = {
            "origin_relpath": "0/beta", "origin_sha256": origin_hash,
            "materialized_relpath": f"{time_name}/beta", "materialized_sha256": materialized_hash,
        }
    try:
        archive_dir.mkdir(parents=True, exist_ok=False)
        files: list[dict[str, str]] = []
        for name in restart_fields:
            source, target = source_dir / name, archive_dir / name
            source_hash = _sha256_file(source)
            shutil.copyfile(source, target)
            archive_hash = _sha256_file(target)
            if archive_hash != source_hash:
                raise ValueError(f"phase_a_restart_archive_hash_mismatch:{name}")
            files.append({"path": name, "source_sha256": source_hash, "archive_sha256": archive_hash})
        archive_entries = [{"path": item["path"], "sha256": item["archive_sha256"]} for item in files]
        manifest = {
            "schema_version": 1, "kind": "g4_b2_phase_a_restart_archive", "source_time": time_name,
            "source_time_relpath": time_name, "archive_relpath": archive_dir.relative_to(case_dir).as_posix(),
            "files": files, "archive_tree_sha256": _sha256_json(archive_entries),
        }
        if beta_provenance is not None:
            manifest["materialized_beta"] = beta_provenance
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(manifest_path, manifest)
        result: dict[str, Any] = {
            "complete": True, "source_time": time_name, "archive_relpath": manifest["archive_relpath"],
            "manifest_relpath": _PHASE_A_RESTART_ARCHIVE_MANIFEST_RELATIVE.as_posix(),
            "manifest_sha256": _sha256_file(manifest_path), "archive_tree_sha256": manifest["archive_tree_sha256"],
            "files": files,
        }
        if beta_provenance is not None:
            result["materialized_beta"] = beta_provenance
        return result
    except (OSError, ValueError) as exc:
        return {"complete": False, "reason": "phase_a_restart_archive_write_failed", "error": str(exc)}


def _verify_phase_a_restart_archive(case_dir: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    """Verify that the pre-B archive still equals the hashes captured before B."""

    if not expected.get("complete"):
        return {"complete": False, "reason": "phase_a_restart_archive_was_not_complete_before_phase_b"}
    manifest_path = case_dir / _PHASE_A_RESTART_ARCHIVE_MANIFEST_RELATIVE
    try:
        if _sha256_file(manifest_path) != expected.get("manifest_sha256"):
            return {"complete": False, "reason": "phase_a_restart_manifest_hash_changed"}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, Mapping) or manifest.get("source_time") != expected.get("source_time"):
            return {"complete": False, "reason": "phase_a_restart_manifest_content_mismatch"}
        files = manifest.get("files")
        expected_fields = list(_PHASE_A_RESTART_FIELDS) + (["beta"] if "materialized_beta" in manifest else [])
        if not isinstance(files, list) or [item.get("path") for item in files if isinstance(item, Mapping)] != expected_fields:
            return {"complete": False, "reason": "phase_a_restart_manifest_file_set_mismatch"}
        archive_dir = case_dir / str(manifest.get("archive_relpath", ""))
        actual_entries: list[dict[str, str]] = []
        for item in files:
            assert isinstance(item, Mapping)
            name, expected_hash = item.get("path"), item.get("archive_sha256")
            if not isinstance(name, str) or not isinstance(expected_hash, str):
                return {"complete": False, "reason": "phase_a_restart_manifest_file_hash_invalid"}
            field = archive_dir / name
            if not field.is_file() or _sha256_file(field) != expected_hash or item.get("source_sha256") != expected_hash:
                return {"complete": False, "reason": "phase_a_restart_archive_file_hash_mismatch", "field": name}
            actual_entries.append({"path": name, "sha256": expected_hash})
        if _sha256_json(actual_entries) != manifest.get("archive_tree_sha256") or manifest.get("archive_tree_sha256") != expected.get("archive_tree_sha256"):
            return {"complete": False, "reason": "phase_a_restart_archive_tree_hash_mismatch"}
        if "materialized_beta" in manifest:
            beta = manifest["materialized_beta"]
            if not isinstance(beta, Mapping) or beta != expected.get("materialized_beta"):
                return {"complete": False, "reason": "phase_a_materialized_beta_provenance_mismatch"}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"complete": False, "reason": "phase_a_restart_archive_manifest_unreadable"}
    return {
        "complete": True, "source_time": expected["source_time"], "manifest_relpath": _PHASE_A_RESTART_ARCHIVE_MANIFEST_RELATIVE.as_posix(),
        "manifest_sha256": expected["manifest_sha256"], "archive_tree_sha256": expected["archive_tree_sha256"],
    }


def _bind_case_evidence(
    case_dir: Path, *, representation: str, case_relpath: Path, image: str,
    phase_a: Mapping[str, Any], phase_b: Mapping[str, Any], extension: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed unless every runtime input and selected raw output is hash-bound.

    This deliberately records raw solver residual/continuity logs and raw
    force/probe histories without attaching any new numerical threshold to
    them.  Evaluation belongs to the separate B2 extractor.
    """

    manifest_path = case_dir / _CASE_EVIDENCE_MANIFEST_RELATIVE
    if manifest_path.exists():
        return {"complete": False, "reason": "case_evidence_manifest_already_exists"}
    entries: list[dict[str, Any]] = []
    missing: list[str] = []

    def bind_file(role: str, relative: str | Path) -> None:
        path = case_dir / relative
        relpath = Path(relative).as_posix()
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(f"missing_or_empty:{role}:{relpath}")
            return
        entries.append({"role": role, "path": relpath, "sha256": _sha256_file(path)})

    def bind_tree(role: str, relative: str | Path) -> None:
        path = case_dir / relative
        relpath = Path(relative).as_posix()
        tree = _sha256_tree(path)
        if tree is None:
            missing.append(f"missing_or_empty_tree:{role}:{relpath}")
            return
        entries.append({"role": role, "path": relpath, "tree_sha256": tree["tree_sha256"], "files": tree["files"]})

    bind_tree("generated_poly_mesh", "constant/polyMesh")
    for role, path in (
        ("block_mesh_log", "log.blockMesh"), ("check_mesh_log", "log.checkMesh"),
        ("phase_a_control", "system/controlDict.phaseA"),
        ("phase_b_control_template", "system/controlDict.phaseB.template"),
        ("phase_b_control_active", "system/controlDict.phaseB"),
        ("phase_a_solution", "system/fvSolution.phaseA"), ("phase_b_solution", "system/fvSolution.phaseB"),
        ("phase_a_solver_raw_residual_continuity", _phase_artifact("phase_a")["solver_log_filename"]),
        ("phase_b_solver_raw_residual_continuity", _phase_artifact("phase_b")["solver_log_filename"]),
        ("phase_a_restart_manifest", _PHASE_A_RESTART_ARCHIVE_MANIFEST_RELATIVE),
    ):
        bind_file(role, path)

    mesh = _mesh_log_contract(case_dir / "log.blockMesh", case_dir / "log.checkMesh")
    raw_logs = _raw_solver_sources_contract(
        case_dir / _phase_artifact("phase_a")["solver_log_filename"],
        case_dir / _phase_artifact("phase_b")["solver_log_filename"],
    )
    if not mesh["complete"]:
        missing.append("mesh_generation_or_check_contract_failed")
    if not raw_logs["complete"]:
        missing.append("residual_continuity_raw_sources_missing")
    restart = phase_a.get("restart_archive")
    if not isinstance(restart, Mapping) or not restart.get("complete"):
        missing.append("phase_a_restart_archive_not_complete")
    else:
        archive_rel = restart.get("archive_relpath")
        if not isinstance(archive_rel, str):
            missing.append("phase_a_restart_archive_relpath_missing")
        else:
            bind_tree("phase_a_restart_state", archive_rel)

    final = phase_b.get("final_time")
    try:
        final_name = str(int(final)) if isinstance(final, float) and final.is_integer() else str(final)
    except (TypeError, ValueError):
        final_name = ""
    if not final_name:
        missing.append("terminal_phase_b_time_missing")
    else:
        bind_file("terminal_U", f"{final_name}/U")
        bind_file("terminal_p", f"{final_name}/p")
        if representation == "porous_cartesian":
            bind_file("terminal_brinkmanResistance", f"{final_name}/brinkmanResistance")

    final_fields = phase_b.get("final_fields")
    histories = final_fields.get("measurement_history") if isinstance(final_fields, Mapping) else None
    for role, function in (("pressure_probe_raw_history", "pressure_probes"), ("force_raw_history", "force")):
        selected = histories.get(function, {}).get("selected") if isinstance(histories, Mapping) and isinstance(histories.get(function), Mapping) else None
        relative = selected.get("relpath") if isinstance(selected, Mapping) else None
        root = "postProcessing/pressureProbes" if function == "pressure_probes" else ("postProcessing/porousResistance" if representation == "porous_cartesian" else "postProcessing/cylinderForces")
        if not isinstance(relative, str):
            missing.append(f"selected_{role}_missing")
        else:
            bind_file(role, f"{root}/{relative}")

    if representation == "porous_cartesian":
        for role, path in (("porous_fv_options", "constant/fvOptions"), ("porous_immutable_beta_origin", "0/beta"), ("porous_extension_build_log", "log.extension-build"), ("porous_extension_library", "lib/libcfdSdfLinearBrinkman.so")):
            bind_file(role, path)
        beta = restart.get("materialized_beta") if isinstance(restart, Mapping) else None
        if not isinstance(beta, Mapping) or not all(isinstance(beta.get(key), str) for key in ("origin_relpath", "origin_sha256", "materialized_relpath", "materialized_sha256")):
            missing.append("materialized_beta_provenance_missing")
        if not isinstance(extension, Mapping) or not extension.get("complete"):
            missing.append("extension_source_build_load_assertions_not_complete")

    if missing:
        return {"complete": False, "reason": "case_evidence_requirements_missing", "missing": missing, "mesh": mesh, "raw_solver_sources": raw_logs}
    entries.sort(key=lambda item: (str(item["role"]), str(item["path"])))
    commands = {"phase_a": phase_a.get("canonical_container_command"), "phase_b": phase_b.get("canonical_container_command")}
    payload = {
        "schema_version": 1, "kind": "g4_b2_cylinder_case_evidence", "case_relpath": case_relpath.as_posix(),
        "representation": representation, "image_digest": image, "commands": commands,
        "commands_sha256": _sha256_json(commands), "mesh_contract": mesh,
        "raw_solver_sources": raw_logs, "entries": entries,
        "evidence_tree_sha256": _sha256_json(entries),
        # Raw logs remain hash-bound above.  Their residual, continuity/mass
        # balance, and stationarity values are intentionally not evaluated by
        # the runner: the acceptance comparison is a later fine six-case task.
        "solver_evaluation": _unevaluated_solver_evaluation_state(),
    }
    if representation == "porous_cartesian":
        assert isinstance(extension, Mapping)  # enforced by the missing gate above
        source = extension.get("source_snapshot")
        build = extension.get("build")
        runtime_load = extension.get("runtime_load")
        payload["porous_extension_evidence"] = {
            "assertions": extension.get("assertions"),
            "source_manifest_relpath": source.get("manifest_relpath") if isinstance(source, Mapping) else None,
            "source_manifest_sha256": source.get("manifest_sha256") if isinstance(source, Mapping) else None,
            "source_tree_sha256": source.get("source_tree_sha256") if isinstance(source, Mapping) else None,
            "source_snapshot_assertions": source.get("assertions") if isinstance(source, Mapping) else None,
            "build": build,
            "runtime_load": runtime_load,
        }
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(manifest_path, payload)
    except OSError as exc:
        return {"complete": False, "reason": "case_evidence_manifest_write_failed", "error": str(exc)}
    return {
        "complete": True, "manifest_relpath": _CASE_EVIDENCE_MANIFEST_RELATIVE.as_posix(),
        "manifest_sha256": _sha256_file(manifest_path), "evidence_tree_sha256": payload["evidence_tree_sha256"],
        "entry_count": len(entries),
    }


def _mesh_log_contract(block_mesh_log: Path, check_mesh_log: Path) -> dict[str, Any]:
    block_text = block_mesh_log.read_text(encoding="utf-8", errors="ignore") if block_mesh_log.is_file() else ""
    check_text = check_mesh_log.read_text(encoding="utf-8", errors="ignore") if check_mesh_log.is_file() else ""
    checks = {
        "block_mesh_log_present_and_nonfatal": bool(block_text) and not has_fatal_openfoam_log(block_text),
        "check_mesh_mesh_ok": bool(re.search(r"\bMesh\s+OK\b", check_text)),
        "check_mesh_nonfatal": bool(check_text) and not has_fatal_openfoam_log(check_text),
    }
    return {"complete": all(checks.values()), "checks": checks, "block_mesh_log_sha256": _sha256_file(block_mesh_log) if block_mesh_log.is_file() else None, "check_mesh_log_sha256": _sha256_file(check_mesh_log) if check_mesh_log.is_file() else None}


def _raw_solver_sources_contract(phase_a_log: Path, phase_b_log: Path) -> dict[str, Any]:
    logs = {"phase_a": phase_a_log, "phase_b": phase_b_log}
    entries: list[dict[str, str]] = []
    missing: list[str] = []
    for phase, path in logs.items():
        text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        # Presence only: no residual or continuity magnitude becomes a physics threshold here.
        if not re.search(r"\bInitial\s+residual\s*=", text) or "time step continuity errors" not in text:
            missing.append(phase)
        elif path.is_file():
            entries.append({"phase": phase, "sha256": _sha256_file(path)})
    return {"complete": not missing, "missing_raw_sources": missing, "entries": entries, "tree_sha256": _sha256_json(entries)}


def _unevaluated_solver_evaluation_state() -> dict[str, Any]:
    """Declare raw CFD sources as unevaluated without suggesting a pass.

    The later evaluator must consume one fresh ``--through-grid fine`` artifact
    containing all six ordered cases.  Until then this runner only binds raw
    sources; it does not attach residual, continuity/mass-balance, or
    stationarity acceptance values to a single case or partial grid prefix.
    """

    reason = "awaits_later_fine_six_case_evaluator"
    return {
        "evaluated": False,
        "reason": reason,
        "status": "not_evaluated_not_passed",
        "residual": {"evaluated": False, "reason": reason, "status": "not_evaluated_not_passed"},
        "continuity_mass_balance": {"evaluated": False, "reason": reason, "status": "not_evaluated_not_passed"},
        "stationarity": {"evaluated": False, "reason": reason, "status": "not_evaluated_not_passed"},
    }


def _read_phase_time(path: Path) -> float:
    try:
        value = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise ValueError(f"missing or invalid phase restart time: {path}") from exc
    if not isfinite(value) or value < 0:
        raise ValueError(f"invalid phase restart time: {path}")
    return value


def _solver_log_has_fatal(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    return has_fatal_openfoam_log(text)


def _two_phase_terminal(base: Mapping[str, Any], phase_a: Mapping[str, Any], phase_b: Mapping[str, Any], *, failed_phase: str | None) -> dict[str, Any]:
    ok = failed_phase is None
    commands = {"phase_a": phase_a["canonical_container_command"], "phase_b": phase_b["canonical_container_command"]}
    return {"returncode": phase_b.get("returncode") if failed_phase == "phase_b" else phase_a.get("returncode"), "timed_out": bool(phase_a.get("timed_out")) or bool(phase_b.get("timed_out")), "error": None if ok else f"two_phase_runtime_failed:{failed_phase}", "solver_error_logs": [], "ok": ok, "command_executed": commands, "command_executed_sha256": _sha256_json(commands), "replay_command": commands, "failed_phase": failed_phase}


def _not_executed_extension_contract(case_dir: Path, snapshot_dir: Path | None, rel: str) -> dict[str, Any]:
    source = _extension_snapshot_provenance(snapshot_dir)
    return {"source_snapshot": source, "build": {"status": "not_executed", "canonical_container_command": _canonical_phase_container_command("phase_a", "<digest-pinned-image>", porous=True)}, "runtime_load": {"status": "not_executed", "controlDict_sha256": _sha256_file(case_dir / "system" / "controlDict.phaseA"), "fvOptions_sha256": _sha256_file(case_dir / "constant" / "fvOptions"), "beta_field_sha256": _sha256_file(case_dir / "0" / "beta"), "selected_option_type": "cfdSdfLinearBrinkman", "selected_option_name": "porousCylinderResistance"}}


def _extension_runtime_contract(
    case_dir: Path, snapshot_dir: Path | None, rel: str, image: str,
    phase_a: Mapping[str, Any], phase_b: Mapping[str, Any] | None,
    *, expected_snapshot_manifest_sha256: str | None = None,
    expected_snapshot_tree_sha256: str | None = None,
    snapshot_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # Re-check after the Phase-A container exits: the mount is read-only in
    # Docker, but the host-side runtime artifact must also fail closed if the
    # copied source or manifest was altered while the solver was running.
    source = _extension_snapshot_provenance(
        snapshot_dir,
        expected_manifest_sha256=expected_snapshot_manifest_sha256,
        expected_tree_sha256=expected_snapshot_tree_sha256,
    )
    library = case_dir / "lib" / "libcfdSdfLinearBrinkman.so"
    build_log = case_dir / "log.extension-build"
    phase_a_log = case_dir / _phase_artifact("phase_a")["solver_log_filename"]
    phase_b_log = case_dir / _phase_artifact("phase_b")["solver_log_filename"]
    phase_a_load = _extension_selection_assertions(phase_a_log)
    final_time_name = _time_directory_name(phase_b.get("final_time") if phase_b else None)
    phase_b_load = _extension_load_assertions(
        phase_b_log, case_dir / final_time_name / "brinkmanResistance",
    )
    assertions = {
        "immutable_source_snapshot_verified": bool(source.get("complete")),
        "immutable_source_manifest_hash_bound": isinstance(source.get("manifest_sha256"), str),
        "immutable_source_tree_hash_bound": isinstance(source.get("source_tree_sha256"), str),
        "build_log_present": build_log.is_file() and build_log.stat().st_size > 0,
        "library_present": library.is_file() and library.stat().st_size > 0,
        "phase_a_option_loaded": all(phase_a_load.values()),
        "phase_b_option_loaded_and_resistance_written": all(phase_b_load.values()),
    }
    return {
        "complete": all(assertions.values()), "assertions": assertions, "source_snapshot": source,
        "build": {"container_image_digest": image, "openfoam_distribution": "OpenCFD", "openfoam_version": "v2512", "canonical_container_command": phase_a["canonical_container_command"], "build_log_relpath": f"{rel}/log.extension-build", "build_log_sha256": _sha256_file(build_log) if build_log.is_file() else None, "library_relative_path": "lib/libcfdSdfLinearBrinkman.so", "library_sha256": _sha256_file(library) if library.is_file() else None},
        "runtime_load": {"controlDict_sha256": _sha256_file(case_dir / "system" / "controlDict.phaseB") if (case_dir / "system" / "controlDict.phaseB").is_file() else None, "fvOptions_sha256": _sha256_file(case_dir / "constant" / "fvOptions"), "beta_field_sha256": _sha256_file(case_dir / "0" / "beta"), "library_sha256": _sha256_file(library) if library.is_file() else None, "selected_option_type": "cfdSdfLinearBrinkman", "selected_option_name": "porousCylinderResistance", "phase_a_solver_log_sha256": _sha256_file(phase_a_log) if phase_a_log.is_file() else None, "solver_log_sha256": _sha256_file(phase_b_log) if phase_b_log.is_file() else None, "phase_a_load_assertions": phase_a_load, "load_log_assertions": phase_b_load},
    }


def _run_porous_case_with_fresh_extension(
    case_dir: Path, *, snapshot_dir: Path, case_relpath: Path, staging_root: Path,
    destination_root: Path, execute: bool, timeout_seconds: int | None,
    docker_image: str | None,
) -> dict[str, Any]:
    """Build a source snapshot in-container, then run this one porous case."""

    rel = case_relpath.as_posix()
    library_relpath = "lib/libcfdSdfLinearBrinkman.so"
    library = case_dir / library_relpath
    if library.exists():
        raise ValueError("refusing a pre-existing porous-case Brinkman library")
    control_hash = _sha256_file(case_dir / "system" / "controlDict")
    fv_options_hash = _sha256_file(case_dir / "constant" / "fvOptions")
    beta_hash = _sha256_file(case_dir / "0" / "beta")
    snapshot_manifest = json.loads((snapshot_dir.parent / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    canonical = _canonical_porous_container_command(str(docker_image) if docker_image else "<digest-pinned-image>")
    if not execute:
        run = run_openfoam_case(case_dir, backend="docker", dry_run=True, docker_image=docker_image)
        base = _published_run_record(run, case_relpath=case_relpath, staging_root=staging_root, destination_root=destination_root)
        base["extension"] = {
            "source_snapshot": snapshot_manifest,
            "build": {"status": "not_executed", "canonical_container_command": canonical},
            "runtime_load": {"status": "not_executed", "controlDict_sha256": control_hash, "fvOptions_sha256": fv_options_hash, "beta_field_sha256": beta_hash, "selected_option_type": "cfdSdfLinearBrinkman", "selected_option_name": "porousCylinderResistance"},
        }
        return base
    assert docker_image is not None
    script = _porous_container_script()
    command = [
        "docker", "run", "--rm", "--entrypoint", "bash",
        "--mount", f"type=bind,source={case_dir.resolve()},target=/case",
        "--mount", f"type=bind,source={snapshot_dir.resolve()},target=/extension-source,readonly",
        "-w", "/case", docker_image, "-lc", script,
    ]
    stdout, stderr = case_dir / "log.runOpenFOAM.stdout", case_dir / "log.runOpenFOAM.stderr"
    returncode: int | None = None
    timed_out, error = False, None
    try:
        with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
            completed = subprocess.run(command, cwd=case_dir, stdout=out, stderr=err, text=True, timeout=timeout_seconds, check=False)
        returncode = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out, error = True, f"OpenFOAM execution timed out after {exc.timeout} seconds"
        stderr.write_text(error, encoding="utf-8")
    except OSError as exc:
        error = str(exc)
        stderr.write_text(error, encoding="utf-8")
    build_log = case_dir / "log.extension-build"
    # This legacy private helper invokes the same generated two-phase Allrun;
    # its only solver-log provenance is therefore the public Phase-B artifact.
    solver_log = case_dir / _phase_artifact("phase_b")["solver_log_filename"]
    foam_environment = case_dir / "log.extension-foam-environment"
    assertions = _extension_load_assertions(solver_log, case_dir / "4000" / "brinkmanResistance")
    library_hash = _sha256_file(library) if library.is_file() else None
    ok = returncode == 0 and not timed_out and error is None and solver_log.is_file() and not _solver_log_has_fatal(solver_log) and library_hash is not None and all(assertions.values())
    return {
        "backend": "docker", "dry_run": False, "returncode": returncode, "timed_out": timed_out,
        "error": error, "solver_error_logs": [], "ok": ok, "published_case_relpath": rel,
        "stdout_relpath": f"{rel}/log.runOpenFOAM.stdout", "stderr_relpath": f"{rel}/log.runOpenFOAM.stderr",
        "summary_relpath": f"{rel}/openfoam_run_summary.json", "command_executed": canonical,
        "command_executed_sha256": _sha256_json(canonical), "replay_command": canonical,
        "extension": {
            "source_snapshot": snapshot_manifest,
            "build": {"container_image_digest": docker_image, "openfoam_distribution": "OpenCFD", "openfoam_version": "v2512", "foam_environment_identity": foam_environment.read_text(encoding="utf-8").strip() if foam_environment.is_file() else None, "canonical_container_command": canonical, "build_log_relpath": f"{rel}/log.extension-build", "build_log_sha256": _sha256_file(build_log) if build_log.is_file() else None, "library_relative_path": library_relpath, "library_sha256": library_hash},
            "runtime_load": {"controlDict_sha256": control_hash, "fvOptions_sha256": fv_options_hash, "beta_field_sha256": beta_hash, "library_sha256": library_hash, "selected_option_type": "cfdSdfLinearBrinkman", "selected_option_name": "porousCylinderResistance", "solver_log_sha256": _sha256_file(solver_log) if solver_log.is_file() else None, "load_log_assertions": assertions},
        },
    }


def _canonical_porous_container_command(image: str) -> list[str]:
    return ["docker", "run", "--rm", "--entrypoint", "bash", "--mount", "type=bind,source=<case-runtime>,target=/case", "--mount", "type=bind,source=<immutable-extension-source>,target=/extension-source,readonly", "-w", "/case", image, "-lc", _porous_container_script()]


def _porous_container_script() -> str:
    return ". /usr/lib/openfoam/openfoam2512/etc/bashrc\nset -eu\nprintf 'WM_PROJECT=%s\\nWM_PROJECT_VERSION=%s\\nFOAM_API=%s\\nWM_OPTIONS=%s\\n' \"${WM_PROJECT:-}\" \"${WM_PROJECT_VERSION:-}\" \"${FOAM_API:-}\" \"${WM_OPTIONS:-}\" > /case/log.extension-foam-environment\nbuild_dir=$(mktemp -d /tmp/cfd-sdf-brinkman.XXXXXX)\ntrap 'rm -rf \"$build_dir\"' EXIT\ntest ! -e \"$build_dir/lib/libcfdSdfLinearBrinkman.so\"\ncp -a /extension-source/. \"$build_dir/\"\ntest ! -e \"$build_dir/lib/libcfdSdfLinearBrinkman.so\"\nexport FOAM_USER_LIBBIN=\"$build_dir/lib\"\ncd \"$build_dir\"\nwmake libso > /case/log.extension-build 2>&1\ntest -f \"$FOAM_USER_LIBBIN/libcfdSdfLinearBrinkman.so\"\ntest ! -e /case/lib/libcfdSdfLinearBrinkman.so\nmkdir -p /case/lib\ncp \"$FOAM_USER_LIBBIN/libcfdSdfLinearBrinkman.so\" /case/lib/libcfdSdfLinearBrinkman.so\ncd /case\nchmod +x Allrun Allclean\n./Allrun\n"


def _extension_load_assertions(solver_log: Path, resistance_field: Path) -> dict[str, bool]:
    return {
        **_extension_selection_assertions(solver_log),
        "resistance_field_written_at_final_time": resistance_field.is_file(),
    }


def _extension_selection_assertions(solver_log: Path) -> dict[str, bool]:
    text = solver_log.read_text(encoding="utf-8", errors="ignore") if solver_log.is_file() else ""
    return {
        "selected_option_type_in_solver_log": "cfdSdfLinearBrinkman" in text,
        "selected_option_name_in_solver_log": "porousCylinderResistance" in text,
    }


def _time_directory_name(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not isfinite(number):
        return ""
    return str(int(number)) if number.is_integer() else format(number, ".12g")


def _published_run_record(run: Any, *, case_relpath: Path, staging_root: Path, destination_root: Path) -> dict[str, Any]:
    command = [str(value) for value in run.command]
    staging_text, destination_text = str(staging_root.resolve()), str(destination_root.resolve())
    rel = case_relpath.as_posix()
    return {"backend": str(run.backend), "dry_run": bool(run.dry_run), "returncode": run.returncode, "timed_out": bool(run.timed_out), "error": run.error, "solver_error_logs": list(run.solver_error_logs), "ok": bool(run.ok), "published_case_relpath": rel, "stdout_relpath": f"{rel}/log.runOpenFOAM.stdout", "stderr_relpath": f"{rel}/log.runOpenFOAM.stderr", "summary_relpath": f"{rel}/openfoam_run_summary.json", "command_executed": command, "command_executed_sha256": _sha256_json(command), "replay_command": [argument.replace(staging_text, destination_text) for argument in command]}


def _read_compilation(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read B2 cylinder compilation: {path}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or raw.get("kind") != G4_B2_CYLINDER_COMPILATION_KIND:
        raise ValueError("unsupported B2 cylinder compilation artifact")
    expected = dict(raw)
    observed = expected.pop("compilation_sha256", None)
    if not isinstance(observed, str) or _sha256_json(expected) != observed:
        raise ValueError("B2 cylinder compilation hash is invalid")
    expected_order = [(rep, grid) for rep in _REPRESENTATIONS for grid in _GRID_IDS]
    if [(case.get("representation"), case.get("grid_id")) for case in raw.get("cases", []) if isinstance(case, Mapping)] != expected_order:
        raise ValueError("B2 cylinder compilation does not contain canonical six cases")
    return raw


def _validate_through_grid(value: str) -> str:
    if value not in _GRID_IDS:
        raise ValueError("B2 cylinder through_grid must be exactly one of coarse, medium, fine")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} has an unsupported key set")


def _finite(value: Any, name: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if isfinite(result) else None


def _positive(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result is None or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _integer_sequence(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    return tuple(_positive_int(item, name) for item in value)


def _float_sequence(value: Any, name: str) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    values = tuple(_positive(item, name) for item in value)
    return values


def _float_pair(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError(f"{name} must contain two finite numbers")
    values = tuple(_finite(item, name) for item in value)
    if any(item is None for item in values):
        raise ValueError(f"{name} must contain finite numbers")
    return values  # type: ignore[return-value]


def _float_triplet(value: Any, name: str) -> tuple[float, float, float]:
    values = _float_sequence(value, name)
    if len(values) != 3:
        raise ValueError(f"{name} must contain three positive numbers")
    return values  # type: ignore[return-value]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_tree(root: Path) -> dict[str, Any] | None:
    """Return a deterministic recursive file hash, or None for absent/empty trees."""

    if not root.is_dir():
        return None
    files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    if not files:
        return None
    entries = [{"path": path.relative_to(root).as_posix(), "sha256": _sha256_file(path)} for path in files]
    return {"files": entries, "tree_sha256": _sha256_json(entries)}


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))


__all__ = [
    "DEFAULT_G4_B2_CYLINDER_SPEC_PATH", "G4_B2_CYLINDER_COMPILATION_FILENAME",
    "G4_B2_CYLINDER_COMPILATION_KIND", "G4_B2_CYLINDER_RUN_FILENAME",
    "G4_B2_CYLINDER_RUN_KIND", "G4_B2_CYLINDER_SPEC_KIND", "G4B2CylinderCompilation",
    "compile_g4_b2_cylinder_benchmark", "load_g4_b2_cylinder_spec", "run_g4_b2_cylinder_cases",
]
