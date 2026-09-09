from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import typer
from rich.console import Console

from .adjoint import run_openfoam_adjoint_adapter
from .adjoint_calibration import (
    run_adjoint_calibration_summary,
    run_adjoint_direction_check,
    run_paired_adjoint_direction_check,
)
from .adjoint_topology import run_adjoint_topology_optimization
from .config import load_project
from .constraints import check_constraints
from .convergence_qualification import (
    evaluate_openfoam_convergence_bundle,
    write_openfoam_convergence_qualification,
)
from .cfd import write_cfd_summary
from .density_optimizer import DensityOptimizerControls, run_density_optimization
from .execution import run_openfoam_case
from .export_vtk import export_vti, export_zero_surface
from .fixed_grid_backend import probe_openfoam_fixed_grid_backend
from .fixed_grid_contract import (
    build_fixed_grid_contract_from_density_design_state,
    build_openfoam_fixed_grid_contract,
    validate_fixed_grid_contract as validate_fixed_grid_contract_artifacts,
)
from .fixed_grid_connectivity import (
    build_fixed_grid_connectivity_derivatives,
    build_fixed_grid_connectivity_state,
)
from .fixed_grid_optimizer import (
    FixedGridOptimizerControls,
    run_fixed_grid_constrained_density_step,
)
from .fixed_grid_primal import (
    prepare_fixed_grid_primal_case,
    run_fixed_grid_primal_case,
    run_fixed_grid_primal_suite as run_fixed_grid_primal_suite_artifacts,
)
from .fixed_grid_sensitivity import (
    build_fixed_grid_sensitivity_from_primal_case,
    run_fixed_grid_sensitivity_direction_suite,
    validate_fixed_grid_sensitivity_direction,
)
from .gradient_check import run_finite_difference_gradient_check
from .openfoam import generate_openfoam_case
from .optimization import run_parametric_optimization
from .openfoam_evidence import extract_openfoam_flow_case_evidence
from .openfoam_mass_imbalance import produce_openfoam_normalized_mass_imbalance
from .openfoam_native_artifacts import assess_native_openfoam_v2_artifact_readiness
from .parametric import default_parameters, parameters_to_dict, write_parametric_front_wing_stl
from .porous_force_validation import (
    validate_efficiency_constraint_gradient,
    validate_porous_force_gradient,
)
from .problem_spec import (
    load_problem_spec,
    problem_spec_sha256,
    topology_constraint_ids,
    write_problem_spec_snapshot,
)
from .projection import project_surface_sensitivity_to_density, write_mock_surface_sensitivity_csv
from .runner import run_practical_optimization
from .sample_geometry import write_front_wing_demo_geometry
from .sensitivity import write_density_update_preview, write_mock_sensitivity_artifacts
from .sdf import build_fields, cache_path, load_cache
from .solver_case_compiler import (
    DEFAULT_FIXED_GRID_PATCH_IDS,
    compile_openfoam_solver_case_bundle,
)
from .solver_case_manifest import build_openfoam_solver_case_manifest
from .topology import run_topology_exploration
from .validation import validate_outputs
from .research_cli import app as research_app

app = typer.Typer(help="Generic topology and SDF tools for CFD optimization problems.")
app.add_typer(research_app, name="research")
console = Console()

_OPENFOAM_FLOW_CASE_EVIDENCE_KIND = "openfoam_flow_case_convergence_evidence"
_OPENFOAM_EVIDENCE_PROVENANCE_KIND = "openfoam_convergence_evidence_provenance"
_OPENFOAM_EVIDENCE_PROVENANCE_SCHEMA_VERSION = 1
_COMPILED_OPENFOAM_MANIFEST_NAME = "openfoam_solver_case_manifest.json"


@app.command()
def init(
    project_dir: Path = typer.Argument(..., help="Directory to create or update."),
    with_sample_geometry: bool = typer.Option(True, help="Generate simple front-wing demo STL files."),
) -> None:
    """Create a front-wing SDF benchmark demo project."""
    project_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir = project_dir / "geometry"
    if with_sample_geometry:
        written = write_front_wing_demo_geometry(geometry_dir)
        console.print(f"Wrote {len(written)} demo STL files to {geometry_dir}")
    project_yaml = project_dir / "project.yaml"
    if not project_yaml.exists():
        project_yaml.write_text(_default_project_yaml(), encoding="utf-8")
        console.print(f"Wrote {project_yaml}")
    else:
        console.print(f"Kept existing {project_yaml}")


@app.command("validate-problem-spec")
def validate_problem_spec(
    problem_yaml: Path = typer.Argument(..., help="Generic problem specification YAML."),
    output_dir: Path | None = typer.Option(
        None, help="Optional directory for the canonical snapshot and validation report."
    ),
    require_execution_ready: bool = typer.Option(
        False,
        "--require-execution-ready/--allow-incomplete",
        help="Fail after reporting when the contract is not execution-ready.",
    ),
) -> None:
    """Validate and fingerprint a generic CFD optimization problem contract."""
    try:
        spec = load_problem_spec(problem_yaml)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="problem_yaml") from exc

    geometry_role_counts = {
        role: sum(region.role == role for region in spec.geometry_regions)
        for role in (
            "fixed_solid",
            "initial_design",
            "design_domain",
            "forbidden_region",
            "root",
        )
    }
    summary = {
        "kind": "problem_spec_validation",
        "schema_version": spec.schema_version,
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "migrated": spec.migration.migrated,
        "source_schema_version": spec.migration.source_schema_version,
        "execution_ready": spec.migration.execution_ready,
        "geometry_role_counts": geometry_role_counts,
        "flow_case_ids": [case.id for case in spec.flow_cases],
        "response_ids": [response.id for response in spec.responses],
        "objective_ids": [objective.id for objective in spec.objectives],
        "aggregate_constraint_ids": [constraint.id for constraint in spec.constraints],
        "topology_constraint_ids": list(topology_constraint_ids(spec)),
    }
    typer.echo(json.dumps(summary, indent=2))

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = write_problem_spec_snapshot(
            spec, output_dir / "problem_spec_snapshot.json"
        )
        validation_path = output_dir / "problem_spec_validation.json"
        validation_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        typer.echo(f"Wrote {snapshot_path}")
        typer.echo(f"Wrote {validation_path}")

    if require_execution_ready and not spec.migration.execution_ready:
        raise typer.Exit(code=1)


@app.command("compile-openfoam-problem-cases")
def compile_openfoam_problem_cases(
    problem_yaml: Path = typer.Argument(..., help="Generic problem specification YAML."),
    template_case_dir: Path = typer.Argument(..., help="OpenFOAM fixed-grid template case."),
    output_dir: Path = typer.Argument(..., help="Output directory for the compiled case bundle."),
    patch_id: list[str] | None = typer.Option(
        None,
        "--patch-id",
        help="Available template patch ID; repeat for each patch. Defaults to the fixed-grid profile.",
    ),
    adjoint_iterations: int = typer.Option(1, help="Adjoint iterations written per force response."),
    overwrite: bool = typer.Option(False, help="Replace a compiler-owned bundle only."),
    require_compile_ready: bool = typer.Option(
        True,
        "--require-compile-ready/--allow-unsupported",
        help="Require all requested features to be supported by this compiler slice.",
    ),
) -> None:
    """Compile OpenFOAM cases only; this does not execute or qualify the solver."""
    try:
        spec = load_problem_spec(problem_yaml)
        artifacts = compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=template_case_dir,
            output_dir=output_dir,
            available_patch_ids=(
                tuple(patch_id) if patch_id else DEFAULT_FIXED_GRID_PATCH_IDS
            ),
            adjoint_iterations=adjoint_iterations,
            overwrite=overwrite,
            require_compile_ready=False,
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    bundle = json.loads(artifacts.bundle_metadata_json.read_text(encoding="utf-8"))
    unsupported = [
        *artifacts.manifest.unsupported,
        *(
            reason
            for plan in artifacts.manifest.flow_cases
            for reason in plan.unsupported
        ),
    ]
    summary = {
        "kind": "openfoam_problem_case_compilation",
        "problem_id": artifacts.manifest.problem_id,
        "problem_spec_sha256": artifacts.manifest.problem_spec_sha256,
        "compile_ready": artifacts.manifest.compile_ready,
        "status": bundle["status"],
        "execution_qualification": "not_run",
        "unsupported": unsupported,
        "flow_case_dirs": {
            flow_case_id: str(case_dir)
            for flow_case_id, case_dir in artifacts.case_dirs.items()
        },
        "manifest_json": str(artifacts.manifest_json),
        "bundle_metadata_json": str(artifacts.bundle_metadata_json),
    }
    typer.echo(json.dumps(summary, indent=2))
    if require_compile_ready and not artifacts.manifest.compile_ready:
        raise typer.Exit(code=1)


@app.command("qualify-openfoam-convergence")
def qualify_openfoam_convergence(
    problem_yaml: Path = typer.Argument(..., help="Generic problem specification YAML."),
    evidence_json: Path = typer.Argument(
        ..., help="Post-run numerical convergence evidence JSON."
    ),
    output_json: Path = typer.Argument(..., help="Qualification artifact JSON."),
) -> None:
    """Numerically qualify every flow case without executing OpenFOAM."""
    try:
        spec = load_problem_spec(problem_yaml)
        manifest = build_openfoam_solver_case_manifest(
            spec, available_patch_ids=None
        )
        evidence_payload = evidence_json.read_bytes()
        raw = json.loads(evidence_payload)
        if not isinstance(raw, dict) or set(raw) != {"flow_cases"}:
            raise ValueError("evidence JSON must contain only a flow_cases mapping")
        evidence = raw["flow_cases"]
        if not isinstance(evidence, dict):
            raise ValueError("evidence flow_cases must be a mapping")
        _validate_openfoam_evidence_provenance(
            evidence_json,
            evidence_payload=evidence_payload,
            evidence_by_flow_case=evidence,
            expected_problem_id=spec.problem_id,
            expected_problem_spec_sha256=problem_spec_sha256(spec),
        )
        result = evaluate_openfoam_convergence_bundle(manifest, evidence)
        artifact = write_openfoam_convergence_qualification(result, output_json)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        json.dumps(
            {
                "kind": result["kind"],
                "status": result["status"],
                "qualified": result["qualified"],
                "flow_cases": {
                    flow_case_id: value["status"]
                    for flow_case_id, value in result["flow_cases"].items()
                },
                "artifact_json": str(artifact.resolve()),
            },
            indent=2,
        )
    )
    if not result["qualified"]:
        raise typer.Exit(code=1)


@app.command("extract-openfoam-convergence-evidence")
def extract_openfoam_convergence_evidence(
    bundle_dir: Path = typer.Argument(
        ..., help="Compiled OpenFOAM case-bundle directory."
    ),
    output_json: Path = typer.Argument(
        ..., help="Output JSON consumable by qualify-openfoam-convergence."
    ),
) -> None:
    """Extract post-run numerical evidence without claiming qualification."""
    try:
        (
            bundle,
            flow_case_dirs,
            metadata_path,
        ) = _load_compiled_openfoam_bundle_flow_case_dirs(bundle_dir)
        evidence = {
            flow_case_id: extract_openfoam_flow_case_evidence(case_dir)
            for flow_case_id, case_dir in flow_case_dirs.items()
        }
        artifact, provenance = _write_openfoam_convergence_evidence_bundle(
            evidence,
            output_json,
            bundle=bundle,
            metadata_path=metadata_path,
            flow_case_dirs=flow_case_dirs,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    complete = all(item["complete"] for item in evidence.values())
    typer.echo(
        json.dumps(
            {
                "kind": "openfoam_convergence_evidence_extraction",
                "status": "complete" if complete else "incomplete",
                "complete": complete,
                "problem_id": bundle["problem_id"],
                "flow_cases": {
                    flow_case_id: item["status"]
                    for flow_case_id, item in evidence.items()
                },
                "artifact_json": str(artifact.resolve()),
                "provenance_json": str(provenance.resolve()),
            },
            indent=2,
        )
    )


@app.command("assess-native-openfoam-v2-artifact-readiness")
def assess_native_openfoam_v2_artifact_readiness_command(
    project_yaml: Path = typer.Argument(..., help="Generic problem specification YAML."),
    bundle_dir: Path = typer.Argument(..., help="Completed OpenFOAM case-bundle directory."),
    output_json: Path = typer.Argument(..., help="Output readiness diagnostic JSON."),
) -> None:
    """Assess whether qualified OpenFOAM output has the semantic bindings required by v2.

    An unready result is a diagnostic outcome, not a command failure.  The
    native writer remains fail-closed and will refuse to write v2 artifacts
    until this artifact reports ``ready: true``.
    """

    try:
        assessment = assess_native_openfoam_v2_artifact_readiness(
            project_yaml=project_yaml,
            bundle_dir=bundle_dir,
        )
        target = output_json.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(assessment, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps({**assessment, "artifact_json": str(target)}, indent=2))


@app.command("produce-openfoam-normalized-mass-imbalance")
def produce_openfoam_normalized_mass_imbalance_command(
    case_dir: Path = typer.Argument(
        ..., help="Compiled, already-run OpenFOAM flow-case directory."
    ),
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    docker_image: str | None = typer.Option(None, help="Docker image when backend=docker."),
    timeout_seconds: int | None = typer.Option(None, min=1, help="Optional postProcess timeout."),
    overwrite: bool = typer.Option(False, help="Replace an existing structured flux artifact."),
) -> None:
    """Measure open-patch ``phi`` fluxes and write normalized mass evidence."""
    try:
        artifact = produce_openfoam_normalized_mass_imbalance(
            case_dir,
            backend=backend,
            docker_image=docker_image,
            timeout_seconds=timeout_seconds,
            overwrite=overwrite,
        )
    except (OSError, RuntimeError, ValueError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        json.dumps(
            {
                "kind": artifact["kind"],
                "flow_case_id": artifact["flow_case_id"],
                "measurements": len(artifact["measurements"]),
                "artifact_json": str(
                    (case_dir / "cfd_sdf_normalized_mass_imbalance.json").resolve()
                ),
            },
            indent=2,
        )
    )


@app.command("build-sdf")
def build_sdf(project_yaml: Path) -> None:
    """Build and cache SDF fields from the project STL files."""
    config = load_project(project_yaml)
    bundle = build_fields(config)
    out = cache_path(config)
    bundle.save(out)
    console.print(f"Saved SDF cache: {out}")
    console.print(f"Grid shape: {bundle.grid.shape}, spacing={bundle.grid.spacing:g} m")


@app.command("check-constraints")
def check(project_yaml: Path) -> None:
    """Check rule, forbidden-region, root-connectivity, and thickness constraints."""
    config = load_project(project_yaml)
    bundle = _load_or_build(config)
    report, derived = check_constraints(config, bundle)
    out_dir = config.resolved_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    export_vti(bundle, out_dir, derived)
    console.print(json.dumps(report.to_dict(), indent=2))
    console.print(f"Wrote {report_path}")


@app.command("export-vtk")
def export(project_yaml: Path) -> None:
    """Export cached SDF fields as VTI and a zero-level PLY surface."""
    config = load_project(project_yaml)
    bundle = _load_or_build(config)
    extra = {}
    try:
        _, extra = check_constraints(config, bundle)
    except ValueError:
        extra = {}
    paths = export_vti(bundle, config.resolved_output_dir, extra)
    surface = export_zero_surface(bundle, config.resolved_output_dir)
    for path in paths:
        console.print(f"Wrote {path}")
    if surface:
        console.print(f"Wrote {surface}")


@app.command("validate-outputs")
def validate(
    project_yaml: Path,
    expect_ok: bool = typer.Option(True, help="Require report.json to contain ok=true."),
) -> None:
    """Validate report.json, VTI arrays, and zero-surface export."""
    config = load_project(project_yaml)
    result = validate_outputs(config, expect_ok=expect_ok)
    console.print(json.dumps(result.to_dict(), indent=2))
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("prepare-openfoam")
def prepare_openfoam(
    project_yaml: Path,
    case_dir: Path | None = typer.Option(None, help="Output OpenFOAM case directory."),
) -> None:
    """Generate an OpenFOAM-ready front-wing case from the SDF project."""
    config = load_project(project_yaml)
    bundle = _load_or_build(config)
    report, derived = check_constraints(config, bundle)
    export_vti(bundle, config.resolved_output_dir, derived)
    export_zero_surface(bundle, config.resolved_output_dir)
    target = case_dir or (config.resolved_output_dir / "openfoam_front_wing")
    summary = generate_openfoam_case(config, bundle, target)
    summary_path = target / "openfoam_case_summary.json"
    summary_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {summary_path}")


@app.command("postprocess-openfoam")
def postprocess_openfoam(
    case_dir: Path,
    efficiency_min: float = typer.Option(3.0, help="Minimum downforce/drag efficiency."),
) -> None:
    """Parse OpenFOAM forceCoeffs output and write cfd_summary.json."""
    path = write_cfd_summary(case_dir, efficiency_min)
    console.print(path.read_text(encoding="utf-8"))
    console.print(f"Wrote {path}")


@app.command("run-openfoam")
def run_openfoam(
    case_dir: Path,
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    execute: bool = typer.Option(False, help="Actually execute OpenFOAM. Default only writes the run plan."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual execution."),
) -> None:
    """Run or dry-run the generated OpenFOAM case."""
    result = run_openfoam_case(
        case_dir,
        backend=backend,
        dry_run=not execute,
        timeout_seconds=timeout_seconds,
    )
    console.print(json.dumps(result.to_dict(), indent=2))
    if execute and not result.ok:
        raise typer.Exit(code=result.returncode or 1)


@app.command("probe-fixed-grid-backend")
def probe_fixed_grid_backend(
    tutorial_case_dir: Path,
    output_dir: Path = typer.Option(
        Path("examples/fixed_grid_backend_spike/report"),
        help="Directory for JSON and Markdown capability evidence.",
    ),
    docker_image: str = typer.Option(
        "opencfd/openfoam-default:2512",
        help="OpenFOAM Docker image to inspect.",
    ),
    command_timeout_seconds: int = typer.Option(
        60,
        help="Timeout for each Docker inspection command.",
    ),
    porous_force_validation_json: Path | None = typer.Option(
        None,
        help="Optional validated porous-force gradient report.",
    ),
    downforce_validation_json: Path | None = typer.Option(
        None,
        help="Optional downforce-direction gradient report.",
    ),
    efficiency_validation_json: Path | None = typer.Option(
        None,
        help="Optional efficiency-constraint gradient report.",
    ),
) -> None:
    """Inspect OpenFOAM fixed-grid topology capabilities and a completed tutorial."""
    artifacts = probe_openfoam_fixed_grid_backend(
        tutorial_case_dir,
        output_dir=output_dir,
        docker_image=docker_image,
        command_timeout_seconds=command_timeout_seconds,
        porous_force_validation_json=porous_force_validation_json,
        downforce_validation_json=downforce_validation_json,
        efficiency_validation_json=efficiency_validation_json,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.summary_json}")
    console.print(f"Wrote {artifacts.summary_markdown}")


@app.command("build-fixed-grid-contract")
def build_fixed_grid_contract(
    case_dir: Path,
    output_dir: Path | None = typer.Option(
        None,
        help="T1 artifact directory. Defaults to fixed_grid_contract under the case.",
    ),
    efficiency_min: float = typer.Option(
        3.0,
        help="Minimum downforce-to-drag ratio used by the efficiency constraint.",
    ),
    docker_image: str = typer.Option(
        "opencfd/openfoam-default:2512",
        help="Docker image recorded in source-solver metadata.",
    ),
    solver_version: str = typer.Option(
        "2512",
        help="OpenFOAM version recorded in source-solver metadata.",
    ),
    drag_validation_json: Path | None = typer.Option(
        None,
        help="Optional passing drag directional-check report.",
    ),
    downforce_validation_json: Path | None = typer.Option(
        None,
        help="Optional passing downforce directional-check report.",
    ),
    efficiency_validation_json: Path | None = typer.Option(
        None,
        help="Optional passing efficiency directional-check report.",
    ),
) -> None:
    """Build and validate the authoritative Stage T1 fixed-grid artifacts."""
    target = output_dir or (case_dir / "fixed_grid_contract")
    artifacts = build_openfoam_fixed_grid_contract(
        case_dir,
        output_dir=target,
        efficiency_min=efficiency_min,
        docker_image=docker_image,
        solver_version=solver_version,
        drag_validation_json=drag_validation_json,
        downforce_validation_json=downforce_validation_json,
        efficiency_validation_json=efficiency_validation_json,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    if not artifacts.ok:
        raise typer.Exit(code=1)


@app.command("build-fixed-grid-contract-from-density")
def build_fixed_grid_contract_from_density(
    design_state_json: Path,
    output_dir: Path = typer.Option(
        ...,
        help="Output fixed-grid contract directory.",
    ),
    project_yaml: Path | None = typer.Option(
        None,
        help="Optional project.yaml used to rebuild allowed/forbidden/fixed/root role masks.",
    ),
    beta_max: float = typer.Option(
        2500.0,
        help="Brinkman betaMax used to write the contract alpha field.",
    ),
    efficiency_min: float = typer.Option(
        3.0,
        help="Minimum downforce-to-drag ratio recorded for the efficiency constraint.",
    ),
) -> None:
    """Convert a legacy point-data density_design_state into T1 cell-data artifacts."""
    artifacts = build_fixed_grid_contract_from_density_design_state(
        design_state_json,
        output_dir=output_dir,
        project_yaml=project_yaml,
        beta_max=beta_max,
        efficiency_min=efficiency_min,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    if not artifacts.ok:
        raise typer.Exit(code=1)


@app.command("validate-fixed-grid-contract")
def validate_fixed_grid_contract(
    topology_state_json: Path,
    output_path: Path | None = typer.Option(
        None,
        help="Validation JSON path. Defaults next to topology_state.json.",
    ),
) -> None:
    """Validate Stage T1 schemas, arrays, masks, metadata, and grid identity."""
    result = validate_fixed_grid_contract_artifacts(
        topology_state_json,
        output_path=output_path,
    )
    console.print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise typer.Exit(code=1)


@app.command("prepare-fixed-grid-primal")
def prepare_fixed_grid_primal(
    topology_state_json: Path,
    case_dir: Path = typer.Option(
        ...,
        help="Output OpenFOAM case directory for the fixed-grid primal run.",
    ),
    template_case_dir: Path | None = typer.Option(
        None,
        help="OpenFOAM topO template case. Defaults to source_solver.case_dir.",
    ),
    density_variant: str = typer.Option(
        "seed",
        help="Density variant: seed, all-fluid, threshold-solid, or filtered-perturbation.",
    ),
    overwrite: bool = typer.Option(False, help="Overwrite a previously generated T2 case."),
    perturbation_seed: int = typer.Option(1, help="Random seed for filtered-perturbation."),
    perturbation_amplitude: float = typer.Option(0.05, help="Filtered perturbation amplitude."),
    smoothing_radius_cells: float = typer.Option(1.0, help="Gaussian smoothing radius in cells."),
    solid_threshold: float = typer.Option(0.5, help="Threshold used by threshold-solid."),
    adjoint_iterations: int = typer.Option(1, help="Adjoint iterations kept minimal for primal-only T2 checks."),
    docker_image: str = typer.Option(
        "opencfd/openfoam-default:2512",
        help="Docker image recorded in source-solver metadata.",
    ),
) -> None:
    """Generate a T2 fixed-grid Brinkman primal OpenFOAM case from density.vti."""
    artifacts = prepare_fixed_grid_primal_case(
        topology_state_json,
        case_dir=case_dir,
        template_case_dir=template_case_dir,
        density_variant=density_variant,
        overwrite=overwrite,
        perturbation_seed=perturbation_seed,
        perturbation_amplitude=perturbation_amplitude,
        smoothing_radius_cells=smoothing_radius_cells,
        solid_threshold=solid_threshold,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.case_metadata_json}")
    console.print(f"Wrote {artifacts.primal_summary_json}")


@app.command("run-fixed-grid-primal")
def run_fixed_grid_primal(
    topology_state_json: Path,
    case_dir: Path = typer.Option(
        ...,
        help="Output OpenFOAM case directory for the fixed-grid primal run.",
    ),
    template_case_dir: Path | None = typer.Option(
        None,
        help="OpenFOAM topO template case. Defaults to source_solver.case_dir.",
    ),
    density_variant: str = typer.Option(
        "seed",
        help="Density variant: seed, all-fluid, threshold-solid, or filtered-perturbation.",
    ),
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    execute: bool = typer.Option(False, help="Actually run OpenFOAM. Default creates a dry-run summary."),
    timeout_seconds: int | None = typer.Option(None, help="Optional OpenFOAM execution timeout."),
    overwrite: bool = typer.Option(False, help="Overwrite a previously generated T2 case."),
    perturbation_seed: int = typer.Option(1, help="Random seed for filtered-perturbation."),
    perturbation_amplitude: float = typer.Option(0.05, help="Filtered perturbation amplitude."),
    smoothing_radius_cells: float = typer.Option(1.0, help="Gaussian smoothing radius in cells."),
    solid_threshold: float = typer.Option(0.5, help="Threshold used by threshold-solid."),
    adjoint_iterations: int = typer.Option(1, help="Adjoint iterations kept minimal for primal-only T2 checks."),
    docker_image: str = typer.Option(
        "opencfd/openfoam-default:2512",
        help="OpenFOAM Docker image.",
    ),
) -> None:
    """Prepare, optionally execute, and summarize one T2 fixed-grid primal case."""
    artifacts = run_fixed_grid_primal_case(
        topology_state_json,
        case_dir=case_dir,
        template_case_dir=template_case_dir,
        density_variant=density_variant,
        backend=backend,
        execute=execute,
        timeout_seconds=timeout_seconds,
        overwrite=overwrite,
        perturbation_seed=perturbation_seed,
        perturbation_amplitude=perturbation_amplitude,
        smoothing_radius_cells=smoothing_radius_cells,
        solid_threshold=solid_threshold,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    if execute and artifacts.summary.get("status") not in {"converged", "completed"}:
        raise typer.Exit(code=1)


@app.command("run-fixed-grid-primal-suite")
def run_fixed_grid_primal_suite(
    topology_state_json: Path,
    run_dir: Path = typer.Option(
        Path("examples/fixed_grid_backend_spike/report/3d/t2_primal_suite"),
        help="Output directory for all T2 primal verification cases.",
    ),
    template_case_dir: Path | None = typer.Option(
        None,
        help="OpenFOAM topO template case. Defaults to source_solver.case_dir.",
    ),
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    execute: bool = typer.Option(False, help="Actually run OpenFOAM for each suite case."),
    timeout_seconds: int | None = typer.Option(None, help="Optional OpenFOAM execution timeout per case."),
    overwrite: bool = typer.Option(False, help="Overwrite a previously generated T2 suite."),
    include_reproducibility_repeat: bool = typer.Option(
        True,
        help="Also build a repeated seed case for reproducibility checks.",
    ),
    perturbation_seed: int = typer.Option(1, help="Random seed for filtered-perturbation."),
    perturbation_amplitude: float = typer.Option(0.05, help="Filtered perturbation amplitude."),
    smoothing_radius_cells: float = typer.Option(1.0, help="Gaussian smoothing radius in cells."),
    solid_threshold: float = typer.Option(0.5, help="Threshold used by threshold-solid."),
    adjoint_iterations: int = typer.Option(1, help="Adjoint iterations kept minimal for primal-only T2 checks."),
    docker_image: str = typer.Option(
        "opencfd/openfoam-default:2512",
        help="OpenFOAM Docker image.",
    ),
) -> None:
    """Run the T2 all-fluid, solid, seed, perturbation, and repeat suite."""
    artifacts = run_fixed_grid_primal_suite_artifacts(
        topology_state_json,
        run_dir=run_dir,
        template_case_dir=template_case_dir,
        backend=backend,
        execute=execute,
        timeout_seconds=timeout_seconds,
        overwrite=overwrite,
        include_reproducibility_repeat=include_reproducibility_repeat,
        perturbation_seed=perturbation_seed,
        perturbation_amplitude=perturbation_amplitude,
        smoothing_radius_cells=smoothing_radius_cells,
        solid_threshold=solid_threshold,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.summary_json}")
    console.print(f"Wrote {artifacts.history_csv}")
    if execute and not artifacts.summary["ok"]:
        raise typer.Exit(code=1)


@app.command("extract-fixed-grid-sensitivity")
def extract_fixed_grid_sensitivity(
    case_dir: Path,
    output_dir: Path | None = typer.Option(
        None,
        help="Output directory. Defaults to the fixed-grid primal case directory.",
    ),
    topology_state_json: Path | None = typer.Option(
        None,
        help="Override topology_state.json. Defaults to case metadata.",
    ),
    efficiency_min: float | None = typer.Option(
        None,
        help="Efficiency constraint coefficient. Defaults to the primal summary or 3.0.",
    ),
    drag_field: str = typer.Option(
        "topOSensas1",
        help="OpenFOAM volScalarField for d_drag_d_rho.",
    ),
    downforce_field: str = typer.Option(
        "topOSensdownforce",
        help="OpenFOAM volScalarField for d_downforce_d_rho.",
    ),
    time_name: str | None = typer.Option(
        None,
        help="OpenFOAM time directory. Defaults to latest time containing both fields.",
    ),
) -> None:
    """Extract T3 fixed-grid aerodynamic sensitivities from a completed T2 case."""
    artifacts = build_fixed_grid_sensitivity_from_primal_case(
        case_dir,
        output_dir=output_dir,
        topology_state_json=topology_state_json,
        efficiency_min=efficiency_min,
        drag_field=drag_field,
        downforce_field=downforce_field,
        time_name=time_name,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.sensitivity_vti}")
    console.print(f"Wrote {artifacts.sensitivity_summary_json}")


@app.command("evaluate-fixed-grid-connectivity")
def evaluate_fixed_grid_connectivity(
    topology_state_json: Path,
    output_dir: Path | None = typer.Option(
        None,
        help="Output directory. Defaults to the topology_state.json directory.",
    ),
    density_array: str = typer.Option(
        "rho",
        help="Density array used for T4 connectivity evaluation.",
    ),
    solid_threshold: float = typer.Option(
        0.5,
        help="Density threshold used for discrete component validation.",
    ),
    min_connection_width_mm: float = typer.Option(
        10.0,
        help="Minimum connection width used for eroded connectivity checks.",
    ),
    require_eroded_connectivity: bool = typer.Option(
        True,
        "--require-eroded-connectivity/--no-require-eroded-connectivity",
        help="Require eroded density to remain root-connected.",
    ),
) -> None:
    """Generate T4 fixed-grid nominal and eroded connectivity state fields."""
    artifacts = build_fixed_grid_connectivity_state(
        topology_state_json,
        output_dir=output_dir,
        density_array=density_array,
        solid_threshold=solid_threshold,
        min_connection_width_m=min_connection_width_mm * 1.0e-3,
        require_eroded_connectivity=require_eroded_connectivity,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.connectivity_state_vti}")
    console.print(f"Wrote {artifacts.connectivity_summary_json}")
    if not artifacts.ok:
        raise typer.Exit(code=1)


@app.command("differentiate-fixed-grid-connectivity")
def differentiate_fixed_grid_connectivity(
    topology_state_json: Path,
    output_dir: Path | None = typer.Option(
        None,
        help="Output directory. Defaults to the topology_state.json directory.",
    ),
    density_array: str = typer.Option(
        "rho",
        help="Density array used for T4 connectivity differentiation.",
    ),
    base_sensitivity_vti: Path | None = typer.Option(
        None,
        help="Optional T3 sensitivity VTI whose aero derivatives are preserved.",
    ),
    epsilon: float = typer.Option(
        1.0e-4,
        help="Finite-difference density perturbation.",
    ),
    max_cells: int | None = typer.Option(
        None,
        help="Optional active-cell sample limit. Omit for all candidate cells.",
    ),
    sample_seed: int = typer.Option(
        1,
        help="Random seed used when max-cells samples a subset.",
    ),
    solid_threshold: float = typer.Option(
        0.5,
        help="Density threshold used for discrete component validation.",
    ),
    min_connection_width_mm: float = typer.Option(
        10.0,
        help="Minimum connection width used for eroded connectivity derivatives.",
    ),
    require_eroded_connectivity: bool = typer.Option(
        True,
        "--require-eroded-connectivity/--no-require-eroded-connectivity",
        help="Record whether the optimizer should enforce eroded connectivity.",
    ),
) -> None:
    """Generate T4 finite-difference reference connectivity derivatives."""
    artifacts = build_fixed_grid_connectivity_derivatives(
        topology_state_json,
        output_dir=output_dir,
        density_array=density_array,
        base_sensitivity_vti=base_sensitivity_vti,
        epsilon=epsilon,
        max_cells=max_cells,
        sample_seed=sample_seed,
        solid_threshold=solid_threshold,
        min_connection_width_m=min_connection_width_mm * 1.0e-3,
        require_eroded_connectivity=require_eroded_connectivity,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.sensitivity_vti}")
    console.print(f"Wrote {artifacts.derivative_summary_json}")
    if not artifacts.ok:
        raise typer.Exit(code=1)


@app.command("run-fixed-grid-constrained-step")
def run_fixed_grid_constrained_step(
    topology_state_json: Path,
    sensitivity_vti: Path = typer.Option(
        ...,
        help="Fixed-grid sensitivity VTI containing T3 aero and T4 connectivity derivatives.",
    ),
    output_dir: Path = typer.Option(
        ...,
        help="Output directory for the T5 constrained density step.",
    ),
    sensitivity_summary_json: Path | None = typer.Option(
        None,
        help="Optional fixed_grid_sensitivity_summary.json. Defaults next to sensitivity VTI.",
    ),
    primal_summary_json: Path | None = typer.Option(
        None,
        help="Optional fixed_grid_primal_summary.json for current aero constraint values.",
    ),
    connectivity_summary_json: Path | None = typer.Option(
        None,
        help="Optional fixed_grid_connectivity_summary.json for current connectivity values.",
    ),
    move_limit: float = typer.Option(
        0.03,
        help="Maximum absolute density change per active cell.",
    ),
    volume_fraction_min: float = typer.Option(
        0.05,
        help="Minimum mean active density.",
    ),
    volume_fraction_max: float = typer.Option(
        0.55,
        help="Maximum mean active density.",
    ),
    efficiency_constraint_limit: float = typer.Option(
        0.0,
        help="Limit for efficiency_min*C_D-C_DF.",
    ),
    connectivity_nominal_limit: float | None = typer.Option(
        None,
        help="Nominal connectivity violation_l1 limit. Defaults to current value.",
    ),
    connectivity_eroded_limit: float | None = typer.Option(
        None,
        help="Eroded connectivity violation_l1 limit. Defaults to current value.",
    ),
    enforce_efficiency: bool = typer.Option(
        True,
        "--enforce-efficiency/--no-enforce-efficiency",
        help="Include the efficiency constraint in the linearized step.",
    ),
    enforce_connectivity: bool = typer.Option(
        True,
        "--enforce-connectivity/--no-enforce-connectivity",
        help="Include nominal and eroded connectivity constraints.",
    ),
    enforce_volume: bool = typer.Option(
        True,
        "--enforce-volume/--no-enforce-volume",
        help="Include active-density volume fraction constraints.",
    ),
    allow_sampled_connectivity_derivatives: bool = typer.Option(
        False,
        "--allow-sampled-connectivity-derivatives/--reject-sampled-connectivity-derivatives",
        help="Allow diagnostic sampled T4 connectivity derivatives.",
    ),
    optimizer_backend: str = typer.Option(
        "projected-gradient",
        help="Optimizer backend: projected-gradient or slsqp-linearized.",
    ),
    subproblem_regularization: float = typer.Option(
        1.0,
        help="Positive proximal regularization for slsqp-linearized.",
    ),
    max_optimizer_iterations: int = typer.Option(
        200,
        help="Maximum optimizer iterations for slsqp-linearized.",
    ),
    optimizer_ftol: float = typer.Option(
        1.0e-9,
        help="Optimizer tolerance for slsqp-linearized.",
    ),
) -> None:
    """Run one T5 fixed-grid constrained density-update step."""
    controls = FixedGridOptimizerControls(
        optimizer_backend=optimizer_backend,
        move_limit=move_limit,
        volume_fraction_min=volume_fraction_min,
        volume_fraction_max=volume_fraction_max,
        efficiency_constraint_limit=efficiency_constraint_limit,
        connectivity_nominal_limit=connectivity_nominal_limit,
        connectivity_eroded_limit=connectivity_eroded_limit,
        enforce_efficiency=enforce_efficiency,
        enforce_connectivity=enforce_connectivity,
        enforce_volume=enforce_volume,
        allow_sampled_connectivity_derivatives=allow_sampled_connectivity_derivatives,
        subproblem_regularization=subproblem_regularization,
        max_optimizer_iterations=max_optimizer_iterations,
        optimizer_ftol=optimizer_ftol,
    )
    artifacts = run_fixed_grid_constrained_density_step(
        topology_state_json,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        controls=controls,
        sensitivity_summary_json=sensitivity_summary_json,
        primal_summary_json=primal_summary_json,
        connectivity_summary_json=connectivity_summary_json,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.update_vti}")
    console.print(f"Wrote {artifacts.output_density_vti}")
    console.print(f"Wrote {artifacts.summary_json}")
    if not artifacts.accepted_by_linearization:
        raise typer.Exit(code=1)


@app.command("validate-fixed-grid-sensitivity-direction")
def validate_fixed_grid_sensitivity_direction_command(
    baseline_case_dir: Path,
    plus_case_dir: Path,
    minus_case_dir: Path,
    sensitivity_vti: Path | None = typer.Option(
        None,
        help="Sensitivity VTI. Defaults to extraction from the baseline case.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        help="Output directory. Defaults under the baseline case.",
    ),
    objective: str = typer.Option(
        "efficiency_constraint",
        help="Objective to check: drag, downforce, or efficiency_constraint.",
    ),
    epsilon: float = typer.Option(
        1.0e-3,
        help="Scalar perturbation used to generate plus/minus density cases.",
    ),
    relative_error_tolerance: float = typer.Option(
        0.25,
        help="Allowed relative error between finite difference and adjoint direction.",
    ),
) -> None:
    """Compare fixed-grid density sensitivity against plus/minus primal cases."""
    result = validate_fixed_grid_sensitivity_direction(
        baseline_case_dir,
        plus_case_dir,
        minus_case_dir,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        objective=objective,
        epsilon=epsilon,
        relative_error_tolerance=relative_error_tolerance,
    )
    console.print(json.dumps(result.to_dict(), indent=2))
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("run-fixed-grid-sensitivity-direction-suite")
def run_fixed_grid_sensitivity_direction_suite_command(
    baseline_case_dir: Path,
    run_dir: Path = typer.Option(
        ...,
        help="Output directory for plus/minus density contracts, cases, and reports.",
    ),
    sensitivity_vti: Path | None = typer.Option(
        None,
        help="Sensitivity VTI. Defaults to extraction from the baseline case.",
    ),
    objective: str = typer.Option(
        "efficiency_constraint",
        help="Objective to check: drag, downforce, or efficiency_constraint.",
    ),
    direction_mode: str = typer.Option(
        "cellwise",
        help="Direction mode: cellwise, filtered-random, or sensitivity.",
    ),
    cell_index: int | None = typer.Option(
        None,
        help="Explicit cell index for cellwise mode. Defaults to largest active sensitivity.",
    ),
    epsilon: float = typer.Option(
        1.0e-2,
        help="Scalar density perturbation used for plus/minus cases.",
    ),
    relative_error_tolerance: float = typer.Option(
        0.25,
        help="Allowed relative error for executed finite-difference validation.",
    ),
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    execute: bool = typer.Option(False, help="Actually run plus/minus OpenFOAM cases."),
    timeout_seconds: int | None = typer.Option(None, help="Optional OpenFOAM timeout per case."),
    overwrite: bool = typer.Option(False, help="Overwrite a previously generated direction suite."),
    template_case_dir: Path | None = typer.Option(
        None,
        help="OpenFOAM topO template case. Defaults to baseline metadata.",
    ),
    perturbation_seed: int = typer.Option(1, help="Random seed for filtered-random mode."),
    smoothing_radius_cells: float = typer.Option(
        1.0,
        help="Gaussian smoothing radius for filtered-random mode.",
    ),
    adjoint_iterations: int = typer.Option(
        1,
        help="Adjoint iterations in plus/minus runs; primal values are the validation target.",
    ),
    docker_image: str = typer.Option(
        "opencfd/openfoam-default:2512",
        help="OpenFOAM Docker image.",
    ),
) -> None:
    """Generate plus/minus T2 cases and optionally validate a T3 sensitivity direction."""
    artifacts = run_fixed_grid_sensitivity_direction_suite(
        baseline_case_dir,
        run_dir=run_dir,
        sensitivity_vti=sensitivity_vti,
        objective=objective,
        direction_mode=direction_mode,
        cell_index=cell_index,
        epsilon=epsilon,
        relative_error_tolerance=relative_error_tolerance,
        backend=backend,
        execute=execute,
        timeout_seconds=timeout_seconds,
        overwrite=overwrite,
        template_case_dir=template_case_dir,
        perturbation_seed=perturbation_seed,
        smoothing_radius_cells=smoothing_radius_cells,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.summary_json}")
    console.print(f"Wrote {artifacts.direction_summary_json}")
    if execute and not artifacts.summary.get("ok"):
        raise typer.Exit(code=1)


@app.command("validate-porous-force-gradient")
def validate_porous_force_gradient_command(
    baseline_case_dir: Path,
    plus_case_dir: Path,
    minus_case_dir: Path,
    output_dir: Path = typer.Option(
        Path("examples/fixed_grid_backend_spike/report"),
        help="Directory for the JSON and Markdown validation report.",
    ),
    epsilon: float = typer.Option(0.01, help="Centered finite-difference perturbation."),
    baseline_alpha: float = typer.Option(0.5, help="Alpha value identifying perturbed cells."),
    objective_name: str = typer.Option("drag", help="OpenFOAM objective file prefix."),
    sensitivity_array: str = typer.Option("topOSensas1", help="Final topology sensitivity array."),
    relative_error_tolerance: float = typer.Option(
        0.1,
        help="Maximum symmetric relative error for a passing result.",
    ),
) -> None:
    """Compare a porous-force adjoint direction with centered finite differences."""
    result = validate_porous_force_gradient(
        baseline_case_dir,
        plus_case_dir,
        minus_case_dir,
        output_dir=output_dir,
        epsilon=epsilon,
        baseline_alpha=baseline_alpha,
        objective_name=objective_name,
        sensitivity_array=sensitivity_array,
        relative_error_tolerance=relative_error_tolerance,
    )
    console.print(json.dumps(result.to_dict(), indent=2))
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("validate-efficiency-gradient")
def validate_efficiency_gradient_command(
    baseline_case_dir: Path,
    plus_case_dir: Path,
    minus_case_dir: Path,
    output_dir: Path = typer.Option(
        Path("examples/fixed_grid_backend_spike/report/efficiency"),
        help="Directory for the report and combined sensitivity VTK.",
    ),
    efficiency_min: float = typer.Option(3.0, help="Minimum downforce-to-drag ratio."),
    epsilon: float = typer.Option(0.005, help="Centered finite-difference perturbation."),
    baseline_alpha: float = typer.Option(0.5, help="Alpha value identifying perturbed cells."),
    drag_objective_name: str = typer.Option("drag", help="Drag objective file prefix."),
    downforce_objective_name: str = typer.Option(
        "downforce2d",
        help="Downforce objective file prefix.",
    ),
    drag_sensitivity_array: str = typer.Option(
        "topOSensas1",
        help="Drag topology sensitivity array.",
    ),
    downforce_sensitivity_array: str = typer.Option(
        "topOSensdownforce2d",
        help="Downforce topology sensitivity array.",
    ),
    relative_error_tolerance: float = typer.Option(
        0.1,
        help="Maximum symmetric relative error for a passing result.",
    ),
) -> None:
    """Validate E_min*dCd/dalpha-dCdf/dalpha and export the combined field."""
    result = validate_efficiency_constraint_gradient(
        baseline_case_dir,
        plus_case_dir,
        minus_case_dir,
        output_dir=output_dir,
        efficiency_min=efficiency_min,
        epsilon=epsilon,
        baseline_alpha=baseline_alpha,
        drag_objective_name=drag_objective_name,
        downforce_objective_name=downforce_objective_name,
        drag_sensitivity_array=drag_sensitivity_array,
        downforce_sensitivity_array=downforce_sensitivity_array,
        relative_error_tolerance=relative_error_tolerance,
    )
    console.print(json.dumps(result.to_dict(), indent=2))
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("evaluate")
def evaluate(
    project_yaml: Path,
    case_dir: Path | None = typer.Option(None, help="Output OpenFOAM case directory."),
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    execute: bool = typer.Option(False, help="Actually run OpenFOAM. Default prepares and dry-runs."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual OpenFOAM execution."),
) -> None:
    """Prepare, optionally run, and summarize a single-point CFD evaluation."""
    config = load_project(project_yaml)
    bundle = _load_or_build(config)
    report, derived = check_constraints(config, bundle)
    out_dir = config.resolved_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    export_vti(bundle, out_dir, derived)
    export_zero_surface(bundle, out_dir)

    target = case_dir or (out_dir / "openfoam_front_wing")
    case_summary = generate_openfoam_case(config, bundle, target)
    (target / "openfoam_case_summary.json").write_text(
        json.dumps(case_summary.to_dict(), indent=2),
        encoding="utf-8",
    )
    run_result = run_openfoam_case(
        target,
        backend=backend,
        dry_run=not execute,
        timeout_seconds=timeout_seconds,
    )

    cfd_summary = None
    cfd_summary_error = None
    if execute and run_result.ok:
        try:
            cfd_summary_path = write_cfd_summary(target, config.objective.efficiency_min)
            cfd_summary = json.loads(cfd_summary_path.read_text(encoding="utf-8"))
        except Exception as exc:
            cfd_summary_error = str(exc)

    evaluation = {
        "ok": bool(report.ok and run_result.ok and (not execute or cfd_summary is not None)),
        "project": str(config.path),
        "constraint_report": report.to_dict(),
        "openfoam_case": case_summary.to_dict(),
        "openfoam_run": run_result.to_dict(),
        "cfd_summary": cfd_summary,
        "cfd_summary_error": cfd_summary_error,
    }
    evaluation_path = target / "evaluation_summary.json"
    evaluation_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    console.print(json.dumps(evaluation, indent=2))
    console.print(f"Wrote {evaluation_path}")
    if execute and not evaluation["ok"]:
        raise typer.Exit(code=1)


@app.command("write-parametric-wing")
def write_parametric_wing(
    output_stl: Path,
) -> None:
    """Write the default parametric front-wing STL."""
    params = default_parameters()
    path = write_parametric_front_wing_stl(output_stl, params)
    console.print(json.dumps(parameters_to_dict(params), indent=2))
    console.print(f"Wrote {path}")


@app.command("optimize-parametric")
def optimize_parametric(
    project_yaml: Path,
    iterations: int = typer.Option(4, help="Number of candidate designs to evaluate."),
    run_dir: Path | None = typer.Option(None, help="Output optimization run directory."),
    evaluator: str = typer.Option("mock", help="Evaluator: mock or openfoam-dry-run."),
    seed: int = typer.Option(1, help="Random seed for candidate sampling."),
    voxel_size_m: float = typer.Option(0.08, help="SDF voxel size for optimization candidates."),
    backend: str = typer.Option("auto", help="OpenFOAM backend for openfoam-dry-run."),
    resume: bool = typer.Option(False, help="Reuse existing candidate_result.json files."),
    reject_before_cfd: bool = typer.Option(True, help="Skip OpenFOAM preparation for rejected candidates."),
) -> None:
    """Run a low-dimensional parametric front-wing optimization loop."""
    config = load_project(project_yaml)
    target = run_dir or (config.resolved_output_dir / "parametric_optimization")
    summary = run_parametric_optimization(
        project_yaml,
        run_dir=target,
        iterations=iterations,
        evaluator=evaluator,
        seed=seed,
        voxel_size_m=voxel_size_m,
        backend=backend,
        resume=resume,
        reject_before_cfd=reject_before_cfd,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {target / 'optimization_summary.json'}")


@app.command("explore-topology")
def explore_topology(
    project_yaml: Path,
    iterations: int = typer.Option(3, help="Number of topology density candidates."),
    run_dir: Path | None = typer.Option(None, help="Output topology run directory."),
    seed: int = typer.Option(1, help="Random seed for topology controls."),
    voxel_size_m: float = typer.Option(0.08, help="SDF/density voxel size for topology candidates."),
    evaluator: str = typer.Option("low-fi", help="Evaluator: low-fi, openfoam-dry-run, or openfoam."),
    backend: str = typer.Option("auto", help="OpenFOAM backend for openfoam/openfoam-dry-run."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual OpenFOAM execution."),
    resume: bool = typer.Option(False, help="Reuse existing topology_result.json files."),
    reject_before_cfd: bool = typer.Option(True, help="Skip OpenFOAM preparation for rejected candidates."),
) -> None:
    """Run a density-field topology exploration loop with low-fidelity scoring."""
    config = load_project(project_yaml)
    target = run_dir or (config.resolved_output_dir / "topology_exploration")
    summary = run_topology_exploration(
        project_yaml,
        run_dir=target,
        iterations=iterations,
        seed=seed,
        voxel_size_m=voxel_size_m,
        evaluator=evaluator,
        backend=backend,
        timeout_seconds=timeout_seconds,
        resume=resume,
        reject_before_cfd=reject_before_cfd,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {target / 'topology_summary.json'}")


@app.command("write-mock-sensitivity")
def write_mock_sensitivity(
    design_state_json: Path,
    output_dir: Path | None = typer.Option(None, help="Output directory. Defaults to the design-state directory."),
) -> None:
    """Write mock density sensitivities for a topology design state."""
    artifacts = write_mock_sensitivity_artifacts(design_state_json, output_dir=output_dir)
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.sensitivity_vti}")
    console.print(f"Wrote {artifacts.sensitivity_summary_json}")


@app.command("preview-density-update")
def preview_density_update(
    design_state_json: Path,
    sensitivity_vti: Path | None = typer.Option(None, help="Sensitivity VTI. Defaults to sensitivity.vti next to design_state.json."),
    output_dir: Path | None = typer.Option(None, help="Output directory. Defaults to the design-state directory."),
    move_limit: float = typer.Option(0.05, help="Maximum absolute density change per update."),
    step_size: float = typer.Option(1.0, help="Gradient-descent step multiplier before move-limit clipping."),
    density_lower: float = typer.Option(0.0, help="Lower density bound."),
    density_upper: float = typer.Option(1.0, help="Upper density bound."),
) -> None:
    """Write a density_update.vti preview from objective density sensitivity."""
    preview = write_density_update_preview(
        design_state_json,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        move_limit=move_limit,
        step_size=step_size,
        density_lower=density_lower,
        density_upper=density_upper,
    )
    console.print(json.dumps(preview.to_dict(), indent=2))
    console.print(f"Wrote {preview.density_update_vti}")


@app.command("optimize-density")
def optimize_density(
    design_state_json: Path,
    iterations: int = typer.Option(2, help="Number of density update steps."),
    run_dir: Path | None = typer.Option(None, help="Output density optimization run directory."),
    move_limit: float = typer.Option(0.05, help="Maximum absolute density change per update."),
    step_size: float = typer.Option(1.0, help="Gradient-descent step multiplier before move-limit clipping."),
    density_lower: float = typer.Option(0.0, help="Lower density bound."),
    density_upper: float = typer.Option(1.0, help="Upper density bound."),
    volume_fraction_min: float = typer.Option(0.05, help="Minimum mean density over the active design domain."),
    volume_fraction_max: float = typer.Option(0.55, help="Maximum mean density over the active design domain."),
    smoothing_radius_cells: float = typer.Option(1.0, help="Gaussian density filter radius in grid cells."),
    minimum_thickness_radius_cells: int = typer.Option(1, help="Neighbor radius for the minimum-thickness proxy."),
    minimum_thickness_neighbor_fraction: float = typer.Option(0.25, help="Minimum local density fraction for thin-cell damping."),
    root_preserve_distance_m: float = typer.Option(0.12, help="Distance around root SDF where density is preserved."),
    heavi_beta: float = typer.Option(0.0, help="Optional Heaviside projection beta. 0 disables projection."),
    heavi_eta: float = typer.Option(0.5, help="Heaviside projection threshold."),
    resume: bool = typer.Option(False, help="Reuse existing density_step_result.json files."),
) -> None:
    """Run a mock-sensitivity density optimization loop."""
    target = run_dir or (design_state_json.parent / "density_optimization")
    controls = DensityOptimizerControls(
        move_limit=move_limit,
        step_size=step_size,
        density_lower=density_lower,
        density_upper=density_upper,
        volume_fraction_min=volume_fraction_min,
        volume_fraction_max=volume_fraction_max,
        smoothing_radius_cells=smoothing_radius_cells,
        minimum_thickness_radius_cells=minimum_thickness_radius_cells,
        minimum_thickness_neighbor_fraction=minimum_thickness_neighbor_fraction,
        root_preserve_distance_m=root_preserve_distance_m,
        heavi_beta=heavi_beta,
        heavi_eta=heavi_eta,
    )
    summary = run_density_optimization(
        design_state_json,
        run_dir=target,
        iterations=iterations,
        controls=controls,
        resume=resume,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {target / 'density_optimization_summary.json'}")


@app.command("check-gradient")
def check_gradient(
    design_state_json: Path,
    sensitivity_vti: Path | None = typer.Option(None, help="Sensitivity VTI. Defaults to a generated mock sensitivity in the output directory."),
    output_dir: Path | None = typer.Option(None, help="Output directory. Defaults to gradient_check next to design_state.json."),
    sample_count: int = typer.Option(8, help="Number of active density cells to perturb."),
    epsilon: float = typer.Option(1.0e-3, help="Finite-difference perturbation magnitude."),
    method: str = typer.Option("auto", help="Finite-difference method: auto, forward, or central."),
    tolerance: float = typer.Option(1.0e-2, help="Relative-error tolerance for ok classification."),
    seed: int = typer.Option(1, help="Random seed for selecting active cells."),
) -> None:
    """Compare mock density sensitivity against finite differences."""
    summary = run_finite_difference_gradient_check(
        design_state_json,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        sample_count=sample_count,
        epsilon=epsilon,
        method=method,
        tolerance=tolerance,
        seed=seed,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {summary.report_json}")
    console.print(f"Wrote {summary.samples_csv}")
    console.print(f"Wrote {summary.check_vti}")


@app.command("check-adjoint-direction")
def check_adjoint_direction(
    step_result_json: Path,
    output_dir: Path | None = typer.Option(None, help="Output directory for adjoint direction diagnostics."),
    sign_tolerance: float = typer.Option(1.0e-9, help="Tolerance used when comparing predicted and actual delta signs."),
) -> None:
    """Compare projected adjoint direction with realized pre/post primal CFD deltas."""
    summary = run_adjoint_direction_check(
        step_result_json,
        output_dir=output_dir,
        sign_tolerance=sign_tolerance,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {summary.report_json}")
    console.print(f"Wrote {summary.report_markdown}")
    console.print(f"Wrote {summary.diagnostics_vti}")


@app.command("check-adjoint-paired-directions")
def check_adjoint_paired_directions(
    step_result_json: Path,
    output_dir: Path | None = typer.Option(None, help="Output directory for paired adjoint direction diagnostics."),
    execute_primal: bool = typer.Option(False, help="Execute primal CFD for directions without reusable CFD results."),
    backend: str = typer.Option("auto", help="OpenFOAM backend: auto, local, wsl, or docker."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for primal OpenFOAM execution."),
    reuse_existing_positive: bool = typer.Option(True, help="Reuse the step post-update primal CFD result for the positive direction."),
    centered: bool = typer.Option(False, help="Use a centered baseline so positive and negative directions can both move away from density bounds."),
    perturbation_scale: float = typer.Option(1.0, help="Scale applied to the stored density_delta before building positive/negative perturbations."),
    sign_tolerance: float = typer.Option(1.0e-9, help="Tolerance used when comparing predicted and actual delta signs."),
) -> None:
    """Compare positive and negative projected-adjoint update directions."""
    summary = run_paired_adjoint_direction_check(
        step_result_json,
        output_dir=output_dir,
        execute_primal=execute_primal,
        backend=backend,
        timeout_seconds=timeout_seconds,
        reuse_existing_positive=reuse_existing_positive,
        centered=centered,
        perturbation_scale=perturbation_scale,
        sign_tolerance=sign_tolerance,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {summary.report_json}")
    console.print(f"Wrote {summary.report_markdown}")


@app.command("summarize-adjoint-calibration")
def summarize_adjoint_calibration(
    paired_report_jsons: list[Path],
    output_dir: Path | None = typer.Option(None, help="Output directory for aggregate adjoint calibration diagnostics."),
    min_density_delta_l2: float = typer.Option(1.0e-12, help="Ignore candidates with density_delta_l2 at or below this value."),
    min_abs_predicted_delta: float = typer.Option(1.0e-12, help="Ignore candidates with near-zero predicted objective delta."),
) -> None:
    """Aggregate paired adjoint direction checks into sign/scale diagnostics."""
    summary = run_adjoint_calibration_summary(
        paired_report_jsons,
        output_dir=output_dir,
        min_density_delta_l2=min_density_delta_l2,
        min_abs_predicted_delta=min_abs_predicted_delta,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {summary.report_json}")
    console.print(f"Wrote {summary.report_markdown}")


@app.command("run-adjoint")
def run_adjoint(
    design_state_json: Path,
    primal_case_dir: Path | None = typer.Option(None, help="Existing OpenFOAM primal case. Defaults to the candidate project output case."),
    adjoint_case_dir: Path | None = typer.Option(None, help="Output adjoint adapter case directory."),
    backend: str = typer.Option("auto", help="OpenFOAM adjoint backend: auto, local, wsl, or docker."),
    execute: bool = typer.Option(False, help="Actually execute adjointOptimisationFoam. Default only writes the run plan."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual adjoint execution."),
    mock_fallback: bool = typer.Option(True, help="Write mock sensitivity.vti when no raw adjoint sensitivity is available."),
) -> None:
    """Prepare and optionally run the initial OpenFOAM adjoint adapter."""
    result = run_openfoam_adjoint_adapter(
        design_state_json,
        primal_case_dir=primal_case_dir,
        adjoint_case_dir=adjoint_case_dir,
        solver_backend=backend,
        dry_run=not execute,
        timeout_seconds=timeout_seconds,
        mock_fallback=mock_fallback,
    )
    console.print(json.dumps(result.to_dict(), indent=2))
    console.print(f"Wrote {result.summary_path}")
    if execute and not result.ok:
        raise typer.Exit(code=result.returncode or 1)


@app.command("write-mock-surface-sensitivity")
def write_mock_surface_sensitivity(
    design_state_json: Path,
    output_csv: Path | None = typer.Option(None, help="Output CSV. Defaults to surface_sensitivity.csv next to design_state.json."),
    max_points: int = typer.Option(2000, help="Maximum surface samples to write."),
) -> None:
    """Write a mock surface sensitivity CSV for projection testing."""
    target = output_csv or (design_state_json.parent / "surface_sensitivity.csv")
    path = write_mock_surface_sensitivity_csv(
        design_state_json,
        output_csv=target,
        max_points=max_points,
    )
    console.print(f"Wrote {path}")


@app.command("project-sensitivity")
def project_sensitivity(
    design_state_json: Path,
    surface_sensitivity_csv: Path,
    output_dir: Path | None = typer.Option(None, help="Output directory. Defaults to the design-state directory."),
    projection_radius_m: float | None = typer.Option(None, help="Projection radius. Defaults to 2.5 grid spacings."),
    smoothing_radius_cells: float = typer.Option(1.0, help="Gaussian smoothing radius in grid cells."),
    max_neighbors: int = typer.Option(8, help="Maximum surface sensitivity points used for each grid cell."),
) -> None:
    """Project surface sensitivity CSV onto the density/SDF grid."""
    artifacts = project_surface_sensitivity_to_density(
        design_state_json,
        surface_sensitivity_csv,
        output_dir=output_dir,
        projection_radius_m=projection_radius_m,
        smoothing_radius_cells=smoothing_radius_cells,
        max_neighbors=max_neighbors,
    )
    console.print(json.dumps(artifacts.to_dict(), indent=2))
    console.print(f"Wrote {artifacts.sensitivity_vti}")
    console.print(f"Wrote {artifacts.sensitivity_summary_json}")
    console.print(f"Wrote {artifacts.projection_diagnostics_vti}")


@app.command("run-adjoint-topology")
def run_adjoint_topology(
    design_state_json: Path,
    iterations: int = typer.Option(1, help="Number of adjoint-driven topology steps."),
    run_dir: Path | None = typer.Option(None, help="Output adjoint topology run directory."),
    backend: str = typer.Option("auto", help="OpenFOAM adjoint backend: auto, local, wsl, or docker."),
    execute_primal: bool = typer.Option(False, help="Execute a real primal OpenFOAM case before the adjoint step."),
    execute_adjoint: bool = typer.Option(False, help="Actually execute adjointOptimisationFoam. Default dry-runs the adapter."),
    execute_updated_primal: bool = typer.Option(False, help="Execute a real primal OpenFOAM case after the density update and use it for step ranking."),
    primal_timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual primal OpenFOAM execution."),
    updated_primal_timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual post-update primal OpenFOAM execution."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual adjoint execution."),
    move_limit: float = typer.Option(0.05, help="Maximum absolute density change per update."),
    volume_fraction_min: float = typer.Option(0.05, help="Minimum mean density over the active design domain."),
    volume_fraction_max: float = typer.Option(0.55, help="Maximum mean density over the active design domain."),
    smoothing_radius_cells: float = typer.Option(1.0, help="Gaussian density filter radius in grid cells."),
    constraint_sensitivity_weight: float = typer.Option(0.0, help="Blend normalized constraint_sensitivity into the density-update gradient; 0 keeps objective-only behavior."),
    calibration_summary: Path | None = typer.Option(None, help="adjoint_calibration_summary.json used to set sensitivity multipliers."),
    sensitivity_update_multiplier: float | None = typer.Option(None, help="Override the multiplier applied before density update; defaults to calibration recommendation or 1.0."),
    sensitivity_derivative_multiplier: float | None = typer.Option(None, help="Optional metadata multiplier for interpreting raw adjoint sensitivity as a derivative."),
    efficiency_min_override: float | None = typer.Option(None, help="Override objective.efficiency_min for this adjoint-topology run; recorded in the run summary."),
    resume: bool = typer.Option(False, help="Reuse existing adjoint_topology_step_result.json files."),
    stop_on_rejection: bool = typer.Option(False, help="Stop before the next iteration when a step is rejected."),
    continue_on_constraint_improvement: bool = typer.Option(False, help="With --stop-on-rejection, continue from an infeasible post-update design only when enforced constraint violation decreases."),
) -> None:
    """Run the initial adjoint-driven topology loop."""
    target = run_dir or (design_state_json.parent / "adjoint_topology")
    controls = DensityOptimizerControls(
        move_limit=move_limit,
        volume_fraction_min=volume_fraction_min,
        volume_fraction_max=volume_fraction_max,
        smoothing_radius_cells=smoothing_radius_cells,
        constraint_sensitivity_weight=constraint_sensitivity_weight,
    )
    summary = run_adjoint_topology_optimization(
        design_state_json,
        run_dir=target,
        iterations=iterations,
        backend=backend,
        primal_execute=execute_primal,
        adjoint_execute=execute_adjoint,
        post_update_primal_execute=execute_updated_primal,
        primal_timeout_seconds=primal_timeout_seconds,
        post_update_primal_timeout_seconds=updated_primal_timeout_seconds,
        timeout_seconds=timeout_seconds,
        density_controls=controls,
        resume=resume,
        stop_on_rejection=stop_on_rejection,
        continue_on_constraint_improvement=continue_on_constraint_improvement,
        calibration_summary_json=calibration_summary,
        sensitivity_update_multiplier=sensitivity_update_multiplier,
        sensitivity_derivative_multiplier=sensitivity_derivative_multiplier,
        efficiency_min_override=efficiency_min_override,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {target / 'adjoint_topology_summary.json'}")


@app.command("run-optimization")
def run_optimization(
    project_yaml: Path,
    mode: str = typer.Option("topology", help="Optimization mode: topology or parametric."),
    iterations: int = typer.Option(8, help="Number of candidates to evaluate."),
    run_dir: Path | None = typer.Option(None, help="Output practical run directory."),
    evaluator: str | None = typer.Option(None, help="Evaluator override. topology: low-fi/openfoam-dry-run/openfoam; parametric: mock/openfoam-dry-run."),
    seed: int = typer.Option(1, help="Random seed for candidate sampling."),
    voxel_size_m: float = typer.Option(0.08, help="SDF/density voxel size for candidates."),
    backend: str = typer.Option("auto", help="OpenFOAM backend for openfoam-dry-run."),
    timeout_seconds: int | None = typer.Option(None, help="Optional timeout for actual OpenFOAM execution."),
    resume: bool = typer.Option(True, help="Reuse existing candidate result files where possible."),
    reject_before_cfd: bool = typer.Option(True, help="Skip OpenFOAM preparation for rejected candidates."),
) -> None:
    """Run a practical resumable optimization job with manifest, progress, and best export."""
    config = load_project(project_yaml)
    target = run_dir or (config.resolved_output_dir / "practical_optimization")
    summary = run_practical_optimization(
        project_yaml,
        run_dir=target,
        mode=mode,
        iterations=iterations,
        evaluator=evaluator,
        seed=seed,
        voxel_size_m=voxel_size_m,
        backend=backend,
        timeout_seconds=timeout_seconds,
        resume=resume,
        reject_before_cfd=reject_before_cfd,
    )
    console.print(json.dumps(summary.to_dict(), indent=2))
    console.print(f"Wrote {target / 'runner_summary.json'}")


@app.command("clean")
def clean(project_yaml: Path) -> None:
    """Remove generated run outputs for a project."""
    config = load_project(project_yaml)
    if config.resolved_output_dir.exists():
        shutil.rmtree(config.resolved_output_dir)
        console.print(f"Removed {config.resolved_output_dir}")


def _load_compiled_openfoam_bundle_flow_case_dirs(
    bundle_dir: Path,
) -> tuple[dict, dict[str, Path], Path]:
    """Read only compiler-declared, contained flow-case directories."""

    root = bundle_dir.resolve()
    if not root.is_dir():
        raise ValueError(f"Compiled OpenFOAM bundle directory does not exist: {root}")

    metadata_path = root / "openfoam_case_bundle.json"
    if not metadata_path.is_file():
        raise ValueError(f"Missing compiled bundle metadata: {metadata_path}")
    metadata_path = metadata_path.resolve()
    try:
        metadata_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Bundle metadata escapes the bundle directory") from exc
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("kind") != "openfoam_case_bundle":
        raise ValueError("Bundle metadata must have kind=openfoam_case_bundle")
    if raw.get("status") != "compiled" or raw.get("compile_ready") is not True:
        raise ValueError("Bundle metadata is not a compile-ready compiled bundle")
    if not isinstance(raw.get("problem_id"), str) or not raw["problem_id"]:
        raise ValueError("Bundle metadata has an invalid problem_id")
    if not _is_sha256(raw.get("problem_spec_sha256")):
        raise ValueError("Bundle metadata has an invalid problem_spec_sha256")

    flow_cases = raw.get("flow_cases")
    if not isinstance(flow_cases, dict) or not flow_cases:
        raise ValueError("Bundle metadata must declare at least one flow case")
    if any(
        not isinstance(flow_case_id, str) or not flow_case_id
        for flow_case_id in flow_cases
    ):
        raise ValueError("Bundle metadata has an invalid flow-case ID")

    case_dirs: dict[str, Path] = {}
    seen_dirs: set[Path] = set()
    for flow_case_id in sorted(flow_cases):
        flow_metadata = flow_cases[flow_case_id]
        if not isinstance(flow_metadata, dict):
            raise ValueError(
                f"Bundle metadata flow case {flow_case_id!r} must be a mapping"
            )
        if flow_metadata.get("status") != "compiled":
            raise ValueError(
                f"Bundle metadata flow case {flow_case_id!r} is not compiled"
            )
        case_dir_name = flow_metadata.get("case_dir")
        if not isinstance(case_dir_name, str):
            raise ValueError(
                f"Bundle metadata flow case {flow_case_id!r} has no case_dir"
            )
        relative_case_dir = Path(case_dir_name)
        if relative_case_dir.is_absolute() or len(relative_case_dir.parts) != 1:
            raise ValueError(f"Unsafe case directory name: {case_dir_name!r}")
        case_dir = (root / relative_case_dir).resolve()
        try:
            case_dir.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Case directory escapes bundle: {case_dir_name!r}"
            ) from exc
        if case_dir == root or case_dir in seen_dirs:
            raise ValueError(f"Invalid duplicate case directory: {case_dir_name!r}")
        if not case_dir.is_dir():
            raise ValueError(f"Compiled flow-case directory does not exist: {case_dir}")
        seen_dirs.add(case_dir)
        case_dirs[flow_case_id] = case_dir
    return raw, case_dirs, metadata_path


def _write_openfoam_convergence_evidence_bundle(
    evidence_by_flow_case: dict[str, dict],
    output_json: Path,
    *,
    bundle: dict,
    metadata_path: Path,
    flow_case_dirs: dict[str, Path],
) -> tuple[Path, Path]:
    """Write qualifier-compatible evidence and a separately bound provenance record."""

    target = output_json.resolve()
    provenance_path = _openfoam_evidence_provenance_path(target)
    _validate_openfoam_evidence_output_paths(
        (target, provenance_path),
        bundle=bundle,
        metadata_path=metadata_path,
        flow_case_dirs=flow_case_dirs,
    )
    evidence_payload = json.dumps(
        {
            "flow_cases": {
                flow_case_id: evidence_by_flow_case[flow_case_id]
                for flow_case_id in sorted(evidence_by_flow_case)
            }
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(evidence_payload)
    provenance = {
        "schema_version": _OPENFOAM_EVIDENCE_PROVENANCE_SCHEMA_VERSION,
        "kind": _OPENFOAM_EVIDENCE_PROVENANCE_KIND,
        "problem_id": bundle["problem_id"],
        "problem_spec_sha256": bundle["problem_spec_sha256"],
        "bundle_metadata_sha256": hashlib.sha256(
            metadata_path.read_bytes()
        ).hexdigest(),
        "evidence_sha256": hashlib.sha256(evidence_payload).hexdigest(),
        "flow_case_ids": sorted(evidence_by_flow_case),
    }
    provenance_path.write_text(
        json.dumps(
            provenance,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return target, provenance_path


def _openfoam_evidence_provenance_path(evidence_json: Path) -> Path:
    target = evidence_json.resolve()
    return target.with_name(f"{target.name}.provenance.json")


def _validate_openfoam_evidence_output_paths(
    targets: tuple[Path, ...],
    *,
    bundle: dict,
    metadata_path: Path,
    flow_case_dirs: dict[str, Path],
) -> None:
    root = metadata_path.resolve().parent
    protected = {
        metadata_path.resolve(): "openfoam_case_bundle.json",
        (root / _COMPILED_OPENFOAM_MANIFEST_NAME).resolve(): (
            "compiled OpenFOAM manifest"
        ),
    }
    manifest_path = bundle.get("manifest_path")
    if isinstance(manifest_path, str):
        declared = _contained_bundle_path(root, manifest_path)
        if declared is not None:
            protected[declared] = "compiled OpenFOAM manifest"

    for target in targets:
        for protected_path, description in protected.items():
            if _same_existing_path(target, protected_path):
                if description == "openfoam_case_bundle.json":
                    raise ValueError(
                        "Evidence output must not replace openfoam_case_bundle.json"
                    )
                raise ValueError("Evidence output must not replace compiled OpenFOAM manifest")
        for flow_case_id, case_dir in flow_case_dirs.items():
            if _is_within(target, case_dir):
                raise ValueError(
                    "Evidence output must not be placed inside compiled flow-case "
                    f"directory {flow_case_id!r}"
                )


def _validate_openfoam_evidence_provenance(
    evidence_json: Path,
    *,
    evidence_payload: bytes,
    evidence_by_flow_case: dict,
    expected_problem_id: str,
    expected_problem_spec_sha256: str,
) -> None:
    provenance_path = _openfoam_evidence_provenance_path(evidence_json)
    requires_provenance = any(
        isinstance(item, dict)
        and item.get("kind") == _OPENFOAM_FLOW_CASE_EVIDENCE_KIND
        for item in evidence_by_flow_case.values()
    )
    if not provenance_path.is_file():
        if requires_provenance:
            raise ValueError(
                "Extractor-shaped evidence requires an adjacent provenance sidecar: "
                f"{provenance_path}"
            )
        return

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if not isinstance(provenance, dict):
        raise ValueError("Evidence provenance sidecar must be a mapping")
    if provenance.get("schema_version") != _OPENFOAM_EVIDENCE_PROVENANCE_SCHEMA_VERSION:
        raise ValueError("Evidence provenance sidecar has an unsupported schema_version")
    if provenance.get("kind") != _OPENFOAM_EVIDENCE_PROVENANCE_KIND:
        raise ValueError("Evidence provenance sidecar has an invalid kind")
    if provenance.get("evidence_sha256") != hashlib.sha256(evidence_payload).hexdigest():
        raise ValueError("Evidence provenance sidecar does not match evidence JSON bytes")
    if provenance.get("problem_id") != expected_problem_id:
        raise ValueError("Evidence provenance problem_id does not match the problem specification")
    if provenance.get("problem_spec_sha256") != expected_problem_spec_sha256:
        raise ValueError(
            "Evidence provenance problem_spec_sha256 does not match the problem specification"
        )
    if not _is_sha256(provenance.get("bundle_metadata_sha256")):
        raise ValueError("Evidence provenance has an invalid bundle_metadata_sha256")
    if provenance.get("flow_case_ids") != sorted(evidence_by_flow_case):
        raise ValueError("Evidence provenance flow_case_ids do not match evidence JSON")


def _contained_bundle_path(root: Path, relative_path: str) -> Path | None:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return None
    resolved = (root / candidate).resolve()
    return resolved if _is_within(resolved, root) else None


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _same_existing_path(left: Path, right: Path) -> bool:
    if left == right:
        return True
    if not left.exists() or not right.exists():
        return False
    try:
        return left.samefile(right)
    except OSError:
        return False


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _load_or_build(config):
    path = cache_path(config)
    if path.exists():
        return load_cache(config)
    bundle = build_fields(config)
    bundle.save(path)
    return bundle


def _default_project_yaml() -> str:
    return """geometry:
  fixed_solids:
    - id: vehicle_nose
      file: geometry/vehicle_nose.stl
    - id: tire_fl
      file: geometry/tire_fl.stl
    - id: tire_fr
      file: geometry/tire_fr.stl
    - id: ground
      file: geometry/ground.stl

  design_geometry:
    - id: front_wing_initial
      file: geometry/front_wing_initial.stl

  design_domains:
    - id: allowed_front_box
      file: geometry/allowed_front_box.stl

  forbidden_regions:
    - id: forbidden_tire_clearance
      file: geometry/forbidden_tire_clearance.stl

roots:
  - id: root_mount_left
    type: stl
    file: geometry/root_mount_left.stl
  - id: root_mount_right
    type: stl
    file: geometry/root_mount_right.stl

grid:
  voxel_size_m: 0.04
  padding_m: 0.12
  band_width_m: 0.20
  max_points: 8000000

constraints:
  min_thickness_mm: 10.0
  rule_margin_mm: 5.0
  require_eroded_connectivity: true
  front_downforce_ratio:
    enabled: true
    enforce: false
    x_split_m: 0.0
    min: 0.40
    max: 0.60

objective:
  type: maximize_downforce_with_efficiency_constraint
  efficiency_min: 3.0

operating_point:
  velocity_mps: 11.0
  density: 1.229
  viscosity: 1.73e-5

output_dir: runs/front_wing_demo
"""
