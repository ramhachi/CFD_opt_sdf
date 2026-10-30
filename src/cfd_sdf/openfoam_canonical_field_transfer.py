"""Fail-closed transfer of reconstructed OpenFOAM adjoint sensitivities.

This boundary binds four independently verified contracts: decomposed
OpenFOAM field reconstruction, a uniform ``blockMeshDict`` source grid, a
verified canonical-grid snapshot, and the exact Cartesian overlap operator.
Only ``topOSens`` is exported to the canonical grid.  It is a derivative
coefficient, so the safe operation is the Euclidean dual ``P.T @ g_source``.
An explicit artifact mapping x-fastest source indices to OpenFOAM global cell
labels is mandatory; global-label order is never assumed to be Cartesian.

``alphaTilda``, ``beta``, and raw ``alpha`` are state fields.  The available
operator maps target states to source averages (``source = P @ target``), and
its inverse is neither unique nor part of the contract.  This module therefore
refuses to manufacture canonical state fields from them.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

import numpy as np

from .canonical_grid_snapshot import (
    CANONICAL_MASK_IDS,
    VerifiedCanonicalGridSnapshot,
)
from .openfoam_blockmesh_grid import (
    OpenFoamBlockMeshGrid,
    read_openfoam_blockmesh_uniform_cartesian_grid,
)
from .openfoam_field_reconstruction import (
    GLOBAL_CELL_LABEL_ORDER,
    ReconstructedOpenFoamFields,
    reconstruct_final_decomposed_openfoam_fields,
)
from .openfoam_grid_transfer import (
    ExactCartesianOverlapTransfer,
    load_openfoam_cell_order_mapping,
)
from .cfd import _solver_fatal_patterns
from .problem_spec import ProblemSpec, problem_spec_sha256


_ARTIFACT_KIND = "openfoam_canonical_gradient_transfer"
_ARTIFACT_SCHEMA_VERSION = 1
_STATE_FIELDS = ("alpha_tilda", "beta", "raw_alpha")
_GRADIENT_CONVENTION = (
    "euclidean_discrete_derivative_coefficients: "
    "dObjective = g.dot(dstate); canonical_gradient = P.T @ openfoam_gradient. "
    "Objective is the OpenFOAM objective named by adjoint_solver_id, with that "
    "solver's own sign. It is not assumed to equal any downstream objective: a "
    "consumer minimizing a differently-signed J must apply the relation itself."
)


@dataclass(frozen=True)
class CanonicalGradientTransferArtifacts:
    """Paths to one atomically-written canonical gradient artifact set."""

    directory: Path
    fields_npz: Path
    provenance_json: Path


def reconstruct_and_write_canonical_gradient_transfer(
    *,
    case_dir: str | Path,
    adjoint_solver_id: str,
    block_mesh_dict: str | Path,
    verified_snapshot: VerifiedCanonicalGridSnapshot,
    source_global_cell_labels_by_xfastest: str | Path,
    output_directory: str | Path,
    response_id: str,
    problem_spec: ProblemSpec,
    final_time: str | None = None,
    adjoint_log_file: str = "log.adjointOptimisationFoam",
    allow_identity_profile: bool = False,
) -> CanonicalGradientTransferArtifacts:
    """Reconstruct and atomically persist a canonical ``topOSens`` gradient.

    The target snapshot must already have been verified against its
    :class:`~cfd_sdf.problem_spec.ProblemSpec`.  Its mask files are checked
    again here to close the verification-to-write time-of-check/time-of-use
    gap.  Source and target active masks are deliberately all-true: this
    operation proves full *grid-domain* coverage and does not silently crop to
    a design mask.

    ``problem_spec`` must be the exact spec bound to ``verified_snapshot`` and
    must declare ``response_id`` with ``options.openfoam_adjoint_solver_id``
    equal to ``adjoint_solver_id`` (or, if undeclared, the response id must
    equal the ``resp_<response_id>`` convention used by the generic OpenFOAM
    response renderer).  This is a *gradient export* boundary: before any
    field is reconstructed, ``adjoint_log_file`` inside ``case_dir`` must show
    that the requested ``adjoint_solver_id`` actually converged.  A finite,
    correctly shaped ``topOSens`` from an unconverged or mislabeled adjoint is
    refused, not merely recorded.  The current qualified runtime path is the
    fixed-grid Stage T case writer: its case metadata and hash-bound
    ``system/optimisationDict`` must also prove that no diagnostic adjoint
    iteration override was used.  Generic compiled cases remain governed by
    their separate convergence-qualification artifact and are not accepted by
    this Stage T export boundary yet.

    ``output_directory`` must not already exist.  A sibling temporary
    directory is fully written and validated before one directory rename makes
    the NPZ and provenance visible together.  The mapping NPY stores
    ``global_label = values[x_fastest_index]`` and must be a complete
    permutation of zero-based global labels.
    """

    reconstructed = reconstruct_final_decomposed_openfoam_fields(
        case_dir,
        adjoint_solver_id=adjoint_solver_id,
        final_time=final_time,
        allow_identity_profile=allow_identity_profile,
    )
    case_qualification = _require_gradient_export_qualified(
        Path(case_dir),
        adjoint_solver_id,
        reconstructed=reconstructed,
        log_file_name=adjoint_log_file,
    )
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(block_mesh_dict)
    return _write_canonical_gradient_transfer(
        reconstructed=reconstructed,
        source_mesh=source_mesh,
        verified_snapshot=verified_snapshot,
        source_global_cell_labels_by_xfastest=source_global_cell_labels_by_xfastest,
        output_directory=output_directory,
        response_id=response_id,
        problem_spec=problem_spec,
        adjoint_convergence=case_qualification["requested_adjoint"],
        case_qualification=case_qualification,
    )


def _write_canonical_gradient_transfer(
    *,
    reconstructed: ReconstructedOpenFoamFields,
    source_mesh: OpenFoamBlockMeshGrid,
    verified_snapshot: VerifiedCanonicalGridSnapshot,
    source_global_cell_labels_by_xfastest: str | Path,
    output_directory: str | Path,
    response_id: str,
    problem_spec: ProblemSpec,
    adjoint_convergence: dict[str, Any],
    case_qualification: dict[str, Any],
) -> CanonicalGradientTransferArtifacts:
    """Write a canonical adjoint gradient from already reconstructed inputs.

    This private writer exists only to keep the numerical transfer separate
    from filesystem reconstruction.  The public entry point above owns the
    fail-closed solver qualification.  Keeping this function private prevents
    callers from exporting a finite field while bypassing the primal/adjoint
    convergence and audit-only checks.
    """

    if case_qualification.get("qualified") is not True:
        raise ValueError("case_qualification must explicitly qualify gradient export")
    if case_qualification.get("requested_adjoint") != adjoint_convergence:
        raise ValueError("adjoint convergence does not match the qualified case")
    _validate_reconstructed_fields(reconstructed)
    _validate_source_mesh(source_mesh, reconstructed)
    _validate_verified_snapshot(verified_snapshot)
    response_binding = _validate_response_binding(
        problem_spec=problem_spec,
        verified_snapshot=verified_snapshot,
        response_id=response_id,
        reconstructed=reconstructed,
    )
    source_order_mapping = load_openfoam_cell_order_mapping(
        source_global_cell_labels_by_xfastest,
        cell_count=source_mesh.grid.cell_count,
    )
    source_order = source_order_mapping.global_cell_labels_by_xfastest

    source_grid = source_mesh.grid
    target_grid = verified_snapshot.snapshot.grid
    transfer = ExactCartesianOverlapTransfer.build(
        source_grid=source_grid,
        target_grid=target_grid,
        source_active_mask=np.ones(source_grid.cell_count, dtype=bool),
        target_active_mask=np.ones(target_grid.cell_count, dtype=bool),
        expected_source_grid_sha256=source_mesh.grid_sha256,
        expected_target_grid_sha256=verified_snapshot.snapshot.grid_sha256,
    )
    source_gradient_xfastest = np.asarray(reconstructed.top_o_sensitivity)[source_order]
    canonical_gradient = transfer.transfer_gradient_to_target(source_gradient_xfastest)
    target_indices = np.arange(target_grid.cell_count, dtype=np.int64)
    payload = {
        "top_o_sensitivity_gradient": canonical_gradient,
        "canonical_cell_indices": target_indices,
    }
    provenance = _provenance(
        reconstructed=reconstructed,
        source_mesh=source_mesh,
        verified_snapshot=verified_snapshot,
        transfer=transfer,
        source_order_reference=source_order_mapping.to_dict(),
        source_gradient_xfastest=source_gradient_xfastest,
        canonical_gradient=canonical_gradient,
        response_id=response_id,
        adjoint_convergence=adjoint_convergence,
        case_qualification=case_qualification,
        response_binding=response_binding,
    )
    return _write_atomically(output_directory, payload, provenance)


def _declared_adjoint_solver_id(response) -> str:
    """Return the response's declared OpenFOAM adjoint solver id.

    An explicit ``options.openfoam_adjoint_solver_id`` always wins (needed for
    hand-authored cases such as the P0 fixed-grid template, whose solver ids
    are ``as1``/``downforce`` and do not follow any formula).  Absent that,
    fall back to the generic response renderer's own convention
    (``openfoam_response_renderer.py``: ``adjoint_solver_id = f"resp_{response_id}"``).
    """

    declared = response.options.get("openfoam_adjoint_solver_id")
    if declared is not None:
        if not isinstance(declared, str) or not declared:
            raise ValueError(
                f"response {response.id!r} options.openfoam_adjoint_solver_id must be a non-empty string"
            )
        return declared
    return f"resp_{response.id}"


def _global_direction(spec: ProblemSpec, direction) -> tuple[float, float, float]:
    """Resolve a response direction declared in the problem frame to global axes."""

    basis = spec.coordinate_frame.basis
    x, y, z = direction
    resolved = [x * basis.x[axis] + y * basis.y[axis] + z * basis.z[axis] for axis in range(3)]
    norm = float(np.sqrt(sum(component * component for component in resolved)))
    if not np.isfinite(norm) or norm <= 0.0:
        raise ValueError("response direction must resolve to a finite non-zero global vector")
    return tuple(float(component / norm) for component in resolved)  # type: ignore[return-value]


def _response_semantic_binding(problem_spec: ProblemSpec, response_id: str) -> dict[str, Any]:
    """Fail-closed semantic binding of a response to direction, sign, and units.

    Gate 0 (WP4/C1) completion: response membership and the adjoint-solver id
    are necessary but not sufficient. A gradient export must also record the
    physical direction the force is projected on (resolved to global axes),
    which declared objectives/constraints consume the response and with what
    sense (the canonical objective sign a downstream optimizer must apply),
    and the value units of this template's objective functional.
    """

    responses_by_id = {response.id: response for response in problem_spec.responses}
    response = responses_by_id[response_id]
    if response.kind != "force":
        raise ValueError(
            f"gradient export supports only kind='force' responses; response "
            f"{response_id!r} declares kind {response.kind!r}"
        )
    if response.direction is None:
        raise ValueError(
            f"response {response_id!r} declares no direction; the gradient cannot "
            "be bound to a physical force direction"
        )
    objective_refs = [
        {"objective_id": objective.id, "sense": objective.sense}
        for objective in problem_spec.objectives
        for term in objective.terms
        if term.response_id == response_id
    ]
    constraint_refs = [
        {"constraint_id": constraint.id, "relation": constraint.relation, "limit": constraint.limit}
        for constraint in problem_spec.constraints
        for term in constraint.terms
        if term.response_id == response_id
    ]
    if not objective_refs and not constraint_refs:
        raise ValueError(
            f"response {response_id!r} is referenced by no declared objective and no "
            "constraint; a gradient with no declared consumer semantics is refused"
        )
    senses = sorted({ref["sense"] for ref in objective_refs})
    if len(senses) > 1:
        raise ValueError(
            f"response {response_id!r} is referenced by objectives with mixed senses "
            f"{senses!r}; the canonical objective sign is ambiguous"
        )
    canonical_sign = None
    if senses == ["minimize"]:
        canonical_sign = 1
    elif senses == ["maximize"]:
        canonical_sign = -1
    return {
        "problem_spec_response_id": response_id,
        "response_kind": response.kind,
        "flow_case_id": response.flow_case_id,
        "physical_direction_global": list(_global_direction(problem_spec, response.direction)),
        "referencing_objectives": objective_refs,
        "referencing_constraints": constraint_refs,
        "canonical_objective_sign": canonical_sign,
        "canonical_objective_sign_convention": (
            "downstream minimize J with J = sign * response: minimize -> +1, "
            "maximize -> -1. The exported array itself is d(+response)/dstate "
            "with the OpenFOAM objective's own sign"
        ),
        "value_units": (
            "dimensionless coefficient (porousDirectionalForce: "
            "2/(Aref UInf^2) * integral alpha beta (U . d) dV); not Newtons"
        ),
    }


def _validate_response_binding(
    *,
    problem_spec: ProblemSpec,
    verified_snapshot: VerifiedCanonicalGridSnapshot,
    response_id: str,
    reconstructed: ReconstructedOpenFoamFields,
) -> dict[str, Any]:
    if not isinstance(problem_spec, ProblemSpec):
        raise ValueError("problem_spec must be ProblemSpec")
    if problem_spec_sha256(problem_spec) != verified_snapshot.snapshot.problem_spec_sha256:
        raise ValueError(
            "problem_spec does not match the ProblemSpec bound to verified_snapshot; "
            "response binding cannot be checked against an unrelated spec"
        )
    responses_by_id = {response.id: response for response in problem_spec.responses}
    response = responses_by_id.get(response_id)
    if response is None:
        raise ValueError(
            f"response_id {response_id!r} is not declared by problem_spec; "
            "the canonical gradient cannot be bound to an undeclared response"
        )
    solver_ids_by_response = {
        candidate.id: _declared_adjoint_solver_id(candidate) for candidate in problem_spec.responses
    }
    if len(set(solver_ids_by_response.values())) != len(solver_ids_by_response):
        raise ValueError(
            "problem_spec responses resolve to ambiguous OpenFOAM adjoint solver ids: "
            f"{solver_ids_by_response!r}"
        )
    declared_solver_id = solver_ids_by_response[response_id]
    actual_solver_id = reconstructed.provenance.get("adjoint_solver_id")
    if actual_solver_id != declared_solver_id:
        raise ValueError(
            f"response_id {response_id!r} is bound to OpenFOAM adjoint solver "
            f"{declared_solver_id!r}, but the reconstructed sensitivity came from "
            f"adjoint_solver_id {actual_solver_id!r}; refusing to bind a gradient "
            "differentiated by one solver to a response declared for another"
        )
    return _response_semantic_binding(problem_spec, response_id)


def _require_gradient_export_qualified(
    case_dir: Path,
    adjoint_solver_id: str,
    *,
    reconstructed: ReconstructedOpenFoamFields,
    log_file_name: str,
) -> dict[str, Any]:
    """Require a converged primal and a non-audit case before exporting a gradient."""

    requested_adjoint = _require_adjoint_converged(
        case_dir, adjoint_solver_id, log_file_name=log_file_name
    )
    text = _read_openfoam_log(case_dir, log_file_name)
    primal_matches = list(
        re.finditer(r"\bop1\s+solution\s+converged\s+in\s+(\d+)\s+iterations\b", text)
    )
    if not primal_matches:
        raise ValueError(
            f"Primal solver 'op1' did not report convergence in {log_file_name}; "
            "a converged adjoint over an unqualified primal is not exportable"
        )

    primal = primal_matches[-1]
    adjoint_marker_offset = requested_adjoint.get("marker_offset")
    if not isinstance(adjoint_marker_offset, int) or primal.start() >= adjoint_marker_offset:
        raise ValueError(
            "The latest primal convergence marker does not precede the requested "
            "adjoint convergence marker; refusing an ambiguous multi-run log"
        )

    selected_final_time = reconstructed.provenance.get("final_time")
    identity_profile = bool(reconstructed.identity_profile)
    fields = reconstructed.provenance.get("fields")
    sensitivity = fields.get("top_o_sensitivity") if isinstance(fields, dict) else None
    sensitivity_time = sensitivity.get("time") if isinstance(sensitivity, dict) else None
    if (
        not isinstance(selected_final_time, str)
        or sensitivity_time != selected_final_time
    ):
        raise ValueError(
            "Reconstructed topOSens is not bound to the selected final OpenFOAM time"
        )

    metadata_path = case_dir / "fixed_grid_primal_case_metadata.json"
    metadata = _read_json_object(metadata_path, "fixed-grid primal case metadata")
    if metadata.get("kind") != "fixed_grid_primal_case":
        raise ValueError("fixed-grid primal case metadata has an unsupported kind")
    declared_case = metadata.get("case_dir")
    if not isinstance(declared_case, str) or Path(declared_case).resolve() != case_dir.resolve():
        raise ValueError("fixed-grid primal case metadata does not bind the exported case directory")
    source_solver = metadata.get("source_solver")
    if not isinstance(source_solver, dict):
        raise ValueError("fixed-grid primal case metadata is missing source_solver")
    if source_solver.get("audit_only") is not False:
        raise ValueError(
            "fixed-grid primal case is audit_only or lacks an explicit non-audit qualification; "
            "diagnostic adjoints must not be exported"
        )
    if "adjoint_iterations" not in source_solver:
        raise ValueError(
            "fixed-grid primal case metadata is missing source_solver.adjoint_iterations"
        )
    if source_solver["adjoint_iterations"] is not None:
        raise ValueError(
            "fixed-grid primal case overrides adjoint_iterations; gradients from an "
            "iteration-capped diagnostic case must not be exported"
        )
    qualification_inputs = metadata.get("qualification_inputs")
    if not isinstance(qualification_inputs, dict):
        raise ValueError("fixed-grid primal case metadata is missing qualification_inputs")
    optimisation_binding = qualification_inputs.get("optimisation_dict")
    if not isinstance(optimisation_binding, dict):
        raise ValueError("fixed-grid primal case metadata is missing optimisationDict binding")
    optimisation_path = case_dir / "system" / "optimisationDict"
    declared_optimisation_path = optimisation_binding.get("path")
    declared_optimisation_hash = optimisation_binding.get("sha256")
    if (
        not isinstance(declared_optimisation_path, str)
        or Path(declared_optimisation_path).resolve() != optimisation_path.resolve()
    ):
        raise ValueError("fixed-grid primal case metadata does not bind the case optimisationDict")
    try:
        actual_optimisation_hash = hashlib.sha256(optimisation_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"Unable to read bound optimisationDict: {optimisation_path}") from exc
    if (
        not isinstance(declared_optimisation_hash, str)
        or declared_optimisation_hash != actual_optimisation_hash
    ):
        raise ValueError(
            "fixed-grid primal case optimisationDict hash does not match metadata; "
            "solver qualification inputs changed after case preparation"
        )
    summary_binding = _verify_fixed_grid_runtime_summary(
        case_dir,
        adjoint_solver_id=adjoint_solver_id,
        metadata_path=metadata_path,
        optimisation_path=optimisation_path,
        log_file_name=log_file_name,
    )
    return {
        "qualified": True,
        "primal": {
            "solver_id": "op1",
            "converged": True,
            "iterations": int(primal.group(1)),
        },
        "convergence_contract": (
            "OpenFOAM solution-converged markers certify the residualControl "
            "criteria in the hash-bound system/optimisationDict"
        ),
        "requested_adjoint": requested_adjoint,
        "final_field": {
            "time": selected_final_time,
            "openfoam_field_name": sensitivity.get("openfoam_field_name"),
            "source_files": sensitivity.get("source_files"),
        },
        "case_metadata": {
            "path": str(metadata_path.resolve()),
            "sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
            "audit_only": False,
            "adjoint_iterations_override": None,
            "optimisation_dict": {
                "path": str(optimisation_path.resolve()),
                "sha256": actual_optimisation_hash,
            },
        },
        "runtime_summary": summary_binding,
    }


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def _verify_fixed_grid_runtime_summary(
    case_dir: Path,
    *,
    adjoint_solver_id: str,
    metadata_path: Path,
    optimisation_path: Path,
    log_file_name: str,
) -> dict[str, Any]:
    summary_path = case_dir / "fixed_grid_primal_summary.json"
    summary = _read_json_object(summary_path, "fixed-grid primal runtime summary")
    if summary.get("kind") != "fixed_grid_primal_summary":
        raise ValueError("fixed-grid primal runtime summary has an unsupported kind")
    declared_case = summary.get("case_dir")
    if not isinstance(declared_case, str) or Path(declared_case).resolve() != case_dir.resolve():
        raise ValueError("fixed-grid primal runtime summary does not bind the exported case")
    if summary.get("status") != "converged":
        raise ValueError("fixed-grid primal runtime summary is not converged")

    run = summary.get("openfoam_run")
    if not isinstance(run, dict) or not (
        run.get("ok") is True
        and run.get("returncode") == 0
        and run.get("dry_run") is False
        and run.get("timed_out") is False
    ):
        raise ValueError("fixed-grid primal runtime summary does not record a successful solver run")

    inputs = summary.get("qualification_inputs")
    if not isinstance(inputs, dict):
        raise ValueError("fixed-grid primal runtime summary is missing qualification_inputs")
    log_path = case_dir / log_file_name
    if not log_path.is_file():
        gz_path = case_dir / f"{log_file_name}.gz"
        log_path = gz_path if gz_path.is_file() else log_path
    for key, path in (
        ("case_metadata", metadata_path),
        ("optimisation_dict", optimisation_path),
        ("solver_log", log_path),
    ):
        binding = inputs.get(key)
        if not isinstance(binding, dict):
            raise ValueError(f"fixed-grid primal runtime summary is missing {key} binding")
        declared_path = binding.get("path")
        declared_hash = binding.get("sha256")
        if not isinstance(declared_path, str) or Path(declared_path).resolve() != path.resolve():
            raise ValueError(f"fixed-grid primal runtime summary does not bind {key} path")
        try:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError(f"Unable to read runtime summary input {key}: {path}") from exc
        if not isinstance(declared_hash, str) or declared_hash != actual_hash:
            raise ValueError(
                f"fixed-grid primal runtime summary {key} hash does not match the case"
            )

    qualification = summary.get("fixed_grid_convergence_qualification")
    if not isinstance(qualification, dict) or qualification.get("qualified") is not True:
        raise ValueError("fixed-grid primal runtime convergence qualification did not pass")
    if qualification.get("run_ok") is not True or qualification.get("solver_completed") is not True:
        raise ValueError("fixed-grid primal runtime did not complete successfully")
    solvers = qualification.get("solvers")
    requested = solvers.get(adjoint_solver_id) if isinstance(solvers, dict) else None
    primal = solvers.get("op1") if isinstance(solvers, dict) else None
    if not isinstance(primal, dict) or primal.get("qualified") is not True:
        raise ValueError("fixed-grid primal residual qualification did not pass")
    if not isinstance(requested, dict) or requested.get("qualified") is not True:
        raise ValueError(
            f"fixed-grid adjoint residual qualification did not pass for {adjoint_solver_id!r}"
        )
    return {
        "path": str(summary_path.resolve()),
        "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "status": "converged",
        "run_ok": True,
        "solver_completed": True,
        "primal_residual_qualification": primal,
        "requested_adjoint_residual_qualification": requested,
        "input_hashes_verified": True,
    }


_ADJOINT_LOG_FATAL_PATTERNS = (
    "foam fatal",
    "mpirun has detected an attempt to run as root",
    "segmentation fault",
    "floating point exception",
)


def _require_adjoint_converged(
    case_dir: Path, adjoint_solver_id: str, *, log_file_name: str
) -> dict[str, Any]:
    """Refuse gradient export unless the named adjoint solver reports convergence.

    This is the fail-closed check the P0 closed loop skipped: it consulted
    only ``primal_converged`` and array finiteness before consuming
    ``topOSens``.  A one-iteration adjoint (``nIters 1``) is finite and
    present but never converged, and must not silently qualify as a design
    gradient.
    """

    text = _read_openfoam_log(case_dir, log_file_name)

    # cfd._solver_fatal_patterns skips the trapFpe startup banner ("Floating
    # point exception trapping enabled"), which every OpenFOAM run prints; a
    # plain substring scan for "floating point exception" refused every log.
    lowered = text.lower()
    fatal = sorted(
        {p for p in _ADJOINT_LOG_FATAL_PATTERNS if "floating" not in p and p in lowered}
        | set(_solver_fatal_patterns(text))
    )
    if fatal:
        raise ValueError(
            f"{log_file_name} reports fatal errors; refusing gradient export: {fatal}"
        )
    matches = list(re.finditer(
        rf"\b{re.escape(adjoint_solver_id)}\s+solution\s+converged\s+in\s+(\d+)\s+iterations\b",
        text,
    ))
    if not matches:
        raise ValueError(
            f"Adjoint solver {adjoint_solver_id!r} did not report convergence in "
            f"{log_file_name}; gradient export requires a converged adjoint, not "
            "merely a finite topOSens"
        )
    match = matches[-1]
    return {
        "adjoint_solver_id": adjoint_solver_id,
        "converged": True,
        "iterations": int(match.group(1)),
        "log_file": log_file_name,
        "marker_offset": match.start(),
    }


def _read_openfoam_log(case_dir: Path, log_file_name: str) -> str:
    path = case_dir / log_file_name
    gz_path = case_dir / f"{log_file_name}.gz"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    elif gz_path.is_file():
        with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    raise ValueError(f"Adjoint convergence log not found for gradient export: {path}")


def _validate_reconstructed_fields(reconstructed: ReconstructedOpenFoamFields) -> None:
    if not isinstance(reconstructed, ReconstructedOpenFoamFields):
        raise ValueError("reconstructed must be ReconstructedOpenFoamFields")
    labels = np.asarray(reconstructed.global_cell_labels)
    count = labels.size
    if labels.dtype.kind not in "iu" or labels.shape != (count,):
        raise ValueError("reconstructed global_cell_labels must be a one-dimensional integer vector")
    if not np.array_equal(labels, np.arange(count, dtype=labels.dtype)):
        raise ValueError("reconstructed global_cell_labels must be contiguous zero-based global labels")
    if reconstructed.provenance.get("ordering") != GLOBAL_CELL_LABEL_ORDER:
        raise ValueError("reconstructed field provenance has an unsupported cell ordering")
    for field_name, values in (
        ("top_o_sensitivity", reconstructed.top_o_sensitivity),
        ("alpha_tilda", reconstructed.alpha_tilda),
        ("beta", reconstructed.beta),
        ("raw_alpha", reconstructed.raw_alpha),
    ):
        if values is None:
            raise ValueError(f"reconstructed {field_name} is required for provenance binding")
        array = np.asarray(values)
        if array.shape != (count,) or not np.issubdtype(array.dtype, np.number):
            raise ValueError(f"reconstructed {field_name} must have shape ({count},)")
        if not np.isfinite(array).all():
            raise ValueError(f"reconstructed {field_name} must contain finite values")
        _validate_source_file_hashes(reconstructed.provenance, field_name)


def _validate_source_file_hashes(provenance: dict[str, Any], field_name: str) -> None:
    fields = provenance.get("fields")
    if not isinstance(fields, dict) or not isinstance(fields.get(field_name), dict):
        raise ValueError(f"reconstructed provenance is missing {field_name} source files")
    sources = fields[field_name].get("source_files")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"reconstructed provenance is missing {field_name} source files")
    for source in sources:
        digest = source.get("sha256") if isinstance(source, dict) else None
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"reconstructed provenance has an invalid {field_name} source hash")


def _validate_source_mesh(source_mesh: OpenFoamBlockMeshGrid, reconstructed: ReconstructedOpenFoamFields) -> None:
    if not isinstance(source_mesh, OpenFoamBlockMeshGrid):
        raise ValueError("source_mesh must be OpenFoamBlockMeshGrid")
    count = int(np.asarray(reconstructed.global_cell_labels).size)
    if source_mesh.grid.cell_count != count:
        raise ValueError(
            "OpenFOAM source grid cell_count does not match reconstructed global-label count: "
            f"{source_mesh.grid.cell_count} != {count}"
        )
    if source_mesh.grid_sha256 != source_mesh.grid.sha256:
        raise ValueError("OpenFOAM source grid hash does not match its geometry")


def _validate_verified_snapshot(verified: VerifiedCanonicalGridSnapshot) -> None:
    if not isinstance(verified, VerifiedCanonicalGridSnapshot):
        raise ValueError("verified_snapshot must be VerifiedCanonicalGridSnapshot")
    snapshot = verified.snapshot
    if snapshot.grid_sha256 != snapshot.grid.sha256:
        raise ValueError("canonical snapshot grid hash does not match its geometry")
    if set(verified.masks) != set(CANONICAL_MASK_IDS):
        raise ValueError("verified canonical snapshot must contain every canonical mask")
    for mask_id in CANONICAL_MASK_IDS:
        artifact = snapshot.masks.get(mask_id)
        values = verified.masks[mask_id]
        if artifact is None or values.dtype != np.dtype(np.uint8) or values.shape != (snapshot.grid.cell_count,):
            raise ValueError(f"verified canonical snapshot mask is invalid: {mask_id}")
        if not np.logical_or(values == 0, values == 1).all():
            raise ValueError(f"verified canonical snapshot mask is non-binary: {mask_id}")
        artifact_path = snapshot.path.parent / artifact.relative_path
        try:
            raw_bytes = artifact_path.read_bytes()
            on_disk = np.load(artifact_path, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError(f"canonical snapshot mask cannot be revalidated: {mask_id}") from exc
        if hashlib.sha256(raw_bytes).hexdigest() != artifact.sha256:
            raise ValueError(f"canonical snapshot mask hash mismatch during transfer: {mask_id}")
        if on_disk.dtype != values.dtype or on_disk.shape != values.shape or not np.array_equal(on_disk, values):
            raise ValueError(f"canonical snapshot mask changed after verification: {mask_id}")


def _provenance(
    *,
    reconstructed: ReconstructedOpenFoamFields,
    source_mesh: OpenFoamBlockMeshGrid,
    verified_snapshot: VerifiedCanonicalGridSnapshot,
    transfer: ExactCartesianOverlapTransfer,
    source_order_reference: dict[str, Any],
    source_gradient_xfastest: np.ndarray,
    canonical_gradient: np.ndarray,
    response_id: str,
    adjoint_convergence: dict[str, Any] | None = None,
    case_qualification: dict[str, Any] | None = None,
    response_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = verified_snapshot.snapshot
    source_fields = {
        "top_o_sensitivity": _field_hash_record(
            reconstructed.top_o_sensitivity, reconstructed.provenance, "top_o_sensitivity"
        ),
        "alpha_tilda": _field_hash_record(reconstructed.alpha_tilda, reconstructed.provenance, "alpha_tilda"),
        "beta": _field_hash_record(reconstructed.beta, reconstructed.provenance, "beta"),
        "raw_alpha": _field_hash_record(reconstructed.raw_alpha, reconstructed.provenance, "raw_alpha"),
    }
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "kind": _ARTIFACT_KIND,
        "identity_profile": bool(reconstructed.identity_profile),
        "source": {
            "block_mesh": source_mesh.to_dict(),
            "global_label_count": int(reconstructed.global_cell_labels.size),
            "global_label_ordering": GLOBAL_CELL_LABEL_ORDER,
            "cell_order_mapping": source_order_reference,
            "field_reconstruction": reconstructed.provenance,
            "field_value_sha256": source_fields,
            "top_o_sensitivity_xfastest_sha256": _array_sha256(
                source_gradient_xfastest
            ),
        },
        "differentiated_response": {
            "problem_spec_response_id": response_id,
            "openfoam_adjoint_solver_id": reconstructed.provenance.get("adjoint_solver_id"),
            "binding": "verified: response_id resolves to this exact adjoint_solver_id in problem_spec",
            "adjoint_convergence": adjoint_convergence,
            "case_qualification": case_qualification,
            **(response_binding or {}),
        },
        "target": {
            "snapshot_path": str(snapshot.path.resolve()),
            "problem_id": snapshot.problem_id,
            "problem_spec_sha256": snapshot.problem_spec_sha256,
            "grid_sha256": snapshot.grid_sha256,
            "cell_order": snapshot.grid.cell_order,
            "cell_count": snapshot.grid.cell_count,
            "masks": {
                mask_id: {
                    "sha256": snapshot.masks[mask_id].sha256,
                    "true_count": snapshot.masks[mask_id].true_count,
                }
                for mask_id in CANONICAL_MASK_IDS
            },
        },
        "transfer": {
            "state_map": "source = P @ target",
            "gradient_map": "target_gradient = P.T @ source_gradient",
            "gradient_convention": _GRADIENT_CONVENTION,
            "source_grid_sha256": transfer.source_grid_sha256,
            "target_grid_sha256": transfer.target_grid_sha256,
            "source_active_mask_sha256": transfer.source_active_mask_sha256,
            "target_active_mask_sha256": transfer.target_active_mask_sha256,
            "coverage": "full source and target grid domains",
        },
        "exported_arrays": {
            "top_o_sensitivity_gradient": {
                "sha256": _array_sha256(canonical_gradient),
                "cell_count": int(canonical_gradient.size),
            }
        },
        "state_field_transfer": {
            field_name: {
                "status": "refused_not_provided",
                "reason": "source = P @ target has no qualified inverse for source-to-target state transfer",
            }
            for field_name in _STATE_FIELDS
        },
    }


def _field_hash_record(
    values: np.ndarray,
    provenance: dict[str, Any],
    field_name: str,
) -> dict[str, Any]:
    """Bind both the reconstructed vector and its source-file digests."""

    source_files = provenance["fields"][field_name]["source_files"]
    return {
        "value_sha256": _array_sha256(np.asarray(values)),
        "source_file_sha256": [item["sha256"] for item in source_files],
    }


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    header = json.dumps({"dtype": array.dtype.str, "shape": list(array.shape)}, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


def _write_atomically(
    output_directory: str | Path,
    payload: dict[str, np.ndarray],
    provenance: dict[str, Any],
) -> CanonicalGradientTransferArtifacts:
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError(f"output_directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.tmp-{uuid4().hex}"
    fields_npz = temporary / "canonical_gradient.npz"
    provenance_json = temporary / "provenance.json"
    try:
        temporary.mkdir()
        np.savez_compressed(fields_npz, **payload)
        provenance_json.write_text(
            json.dumps(provenance, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        with np.load(fields_npz, allow_pickle=False) as written:
            if set(written.files) != set(payload):
                raise ValueError("written canonical gradient NPZ has an unexpected array set")
            for key, expected in payload.items():
                if not np.array_equal(written[key], expected):
                    raise ValueError(f"written canonical gradient NPZ does not preserve {key}")
        json.loads(provenance_json.read_text(encoding="utf-8"))
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return CanonicalGradientTransferArtifacts(
        directory=output,
        fields_npz=output / fields_npz.name,
        provenance_json=output / provenance_json.name,
    )


__all__ = [
    "CanonicalGradientTransferArtifacts",
    "reconstruct_and_write_canonical_gradient_transfer",
]
