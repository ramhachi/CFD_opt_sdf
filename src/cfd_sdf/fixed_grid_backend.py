from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE


FIXED_GRID_PROBE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FixedGridBackendProbeArtifacts:
    output_dir: Path
    environment_json: Path
    capability_matrix_json: Path
    summary_json: Path
    summary_markdown: Path
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "output_dir",
            "environment_json",
            "capability_matrix_json",
            "summary_json",
            "summary_markdown",
        ):
            data[key] = str(data[key])
        return data


def probe_openfoam_fixed_grid_backend(
    tutorial_case_dir: Path,
    *,
    output_dir: Path,
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
    command_timeout_seconds: int = 60,
    porous_force_validation_json: Path | None = None,
    downforce_validation_json: Path | None = None,
    efficiency_validation_json: Path | None = None,
) -> FixedGridBackendProbeArtifacts:
    tutorial_case_dir = tutorial_case_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    environment = inspect_openfoam_topology_environment(
        docker_image=docker_image,
        timeout_seconds=command_timeout_seconds,
    )
    case_analysis = analyze_openfoam_topology_case(tutorial_case_dir)
    porous_force_validation = (
        _read_json_if_present(porous_force_validation_json.resolve())
        if porous_force_validation_json is not None
        else None
    )
    downforce_validation = (
        _read_json_if_present(downforce_validation_json.resolve())
        if downforce_validation_json is not None
        else None
    )
    efficiency_validation = (
        _read_json_if_present(efficiency_validation_json.resolve())
        if efficiency_validation_json is not None
        else None
    )
    capabilities = build_openfoam_capability_matrix(
        environment,
        case_analysis,
        porous_force_validation,
        downforce_validation,
        efficiency_validation,
    )
    overall_status = _overall_status(capabilities)

    environment_json = output_dir / "backend_environment.json"
    capability_matrix_json = output_dir / "capability_matrix.json"
    summary_json = output_dir / "fixed_grid_backend_probe_summary.json"
    summary_markdown = output_dir / "fixed_grid_backend_probe_summary.md"

    environment_json.write_text(json.dumps(environment, indent=2), encoding="utf-8")
    capability_matrix_json.write_text(json.dumps(capabilities, indent=2), encoding="utf-8")

    summary = {
        "schema_version": FIXED_GRID_PROBE_SCHEMA_VERSION,
        "kind": "fixed_grid_backend_probe",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": "openfoam-v2512-topO",
        "docker_image": docker_image,
        "tutorial_case_dir": str(tutorial_case_dir),
        "overall_status": overall_status,
        "environment_json": str(environment_json),
        "capability_matrix_json": str(capability_matrix_json),
        "case_analysis": case_analysis,
        "porous_force_validation_json": (
            str(porous_force_validation_json.resolve())
            if porous_force_validation_json is not None
            else None
        ),
        "porous_force_validation": porous_force_validation,
        "downforce_validation_json": (
            str(downforce_validation_json.resolve())
            if downforce_validation_json is not None
            else None
        ),
        "downforce_validation": downforce_validation,
        "efficiency_validation_json": (
            str(efficiency_validation_json.resolve())
            if efficiency_validation_json is not None
            else None
        ),
        "efficiency_validation": efficiency_validation,
        "capabilities": capabilities,
        "next_required_action": _next_required_action(capabilities),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary_markdown.write_text(_probe_markdown(summary), encoding="utf-8")
    return FixedGridBackendProbeArtifacts(
        output_dir=output_dir,
        environment_json=environment_json,
        capability_matrix_json=capability_matrix_json,
        summary_json=summary_json,
        summary_markdown=summary_markdown,
        summary=summary,
    )


def inspect_openfoam_topology_environment(
    *,
    docker_image: str,
    timeout_seconds: int = 60,
) -> dict[str, object]:
    docker_version = _run_command(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        timeout_seconds=timeout_seconds,
    )
    image_inspect = _run_command(
        ["docker", "image", "inspect", docker_image, "--format", "{{.Id}}"],
        timeout_seconds=timeout_seconds,
    )
    script = r"""
source /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
root="$WM_PROJECT_DIR/src/optimisation/adjointOptimisation/adjoint"
tutorial="$FOAM_TUTORIALS/incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero"
check()
{
    if [ -e "$2" ]; then
        printf '%s=1\n' "$1"
    else
        printf '%s=0\n' "$1"
    fi
}
printf 'wm_project_version=%s\n' "$WM_PROJECT_VERSION"
printf 'wm_project_dir=%s\n' "$WM_PROJECT_DIR"
printf 'foam_tutorials=%s\n' "$FOAM_TUTORIALS"
printf 'adjoint_executable=%s\n' "$(command -v adjointOptimisationFoam)"
check porosity_tutorial "$tutorial/laminar/1_Inlet_2_Outlet/porosityBased/R_10x-init"
check level_set_tutorial "$tutorial/laminar/1_Inlet_2_Outlet/levelSet/R_10x_NB_01x"
check turbulent_porosity_tutorial "$tutorial/turbulent/1_Inlet_2_Outlet/porosityBased"
check topo_source "$root/fvOptions/sources/TopO/topOSource/topOSource.C"
check topo_design_variables "$root/optimisation/designVariables/topODesignVariables/topODesignVariables.C"
check topo_sensitivity "$root/optimisation/adjointSensitivity/adjointSensitivity/topO/sensitivityTopO.C"
check force_objective "$root/objectives/incompressible/objectiveForce/objectiveForce.C"
check mma_update "$root/optimisation/updateMethod/MMA"
check gcmma_line_search "$root/optimisation/lineSearch/GCMMA"
check helmholtz_regularisation "$root/optimisation/designVariables/topODesignVariables/regularisation/regularisationPDE/Helmoltz"
if grep -q 'dict.get<wordRes>("patches")' "$root/objectives/incompressible/objectiveForce/objectiveForce.C"; then
    printf 'force_objective_patch_based=1\n'
else
    printf 'force_objective_patch_based=0\n'
fi
"""
    runtime = _run_command(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            docker_image,
            "-lc",
            script,
        ],
        timeout_seconds=timeout_seconds,
    )
    facts = _parse_key_value_lines(str(runtime["stdout"]))
    return {
        "docker_version": docker_version,
        "image_inspect": image_inspect,
        "runtime_inspection": runtime,
        "facts": facts,
    }


def analyze_openfoam_topology_case(case_dir: Path) -> dict[str, object]:
    case_dir = case_dir.resolve()
    run_summary_path = case_dir / "openfoam_run_summary.json"
    solver_log = case_dir / "log.adjointOptimisationFoam"
    merit_path = case_dir / "optimisation" / "objective" / "0" / "meritFunction"

    run_summary = _read_json_if_present(run_summary_path)
    log_text = solver_log.read_text(encoding="utf-8", errors="ignore") if solver_log.exists() else ""
    merit_rows = parse_merit_function(merit_path)
    fatal_patterns = [
        "FOAM FATAL",
        "mpirun has detected an attempt to run as root",
        "Segmentation fault",
        "Floating point exception (core dumped)",
    ]
    fatal_matches = [pattern for pattern in fatal_patterns if pattern.lower() in log_text.lower()]
    actual_solver_completed = (
        "Finalising parallel run" in log_text
        and "\nEnd\n" in log_text
        and not fatal_matches
    )
    brinkman_sensitivity_observed = "Postprocessing Brinkman sensitivities" in log_text
    alpha_design_observed = "Setting design variables based on the alpha field" in log_text

    latest_time = _latest_numeric_directory(case_dir)
    if latest_time is None:
        latest_time = _latest_numeric_directory(case_dir / "processor0")
    latest_fields = sorted(path.name for path in latest_time.iterdir() if path.is_file()) if latest_time else []
    vtk_files = sorted(
        str(path)
        for path in (case_dir / "VTK").rglob("*")
        if path.is_file() and path.suffix.lower() in {".vtm", ".vtu", ".vtp"}
    ) if (case_dir / "VTK").exists() else []

    allrun_text = (case_dir / "Allrun").read_text(encoding="utf-8", errors="ignore") if (case_dir / "Allrun").exists() else ""
    mesh_build_count = len(re.findall(r"\brunApplication\s+blockMesh\b", allrun_text))
    remeshing_command_count = len(re.findall(r"\b(?:snappyHexMesh|cartesianMesh|cfMesh)\b", allrun_text))
    fixed_mesh_updates_observed = (
        actual_solver_completed
        and len(merit_rows) > 1
        and mesh_build_count == 1
        and remeshing_command_count == 0
    )

    first_merit = merit_rows[0] if merit_rows else None
    last_merit = merit_rows[-1] if merit_rows else None
    objective_reduction = None
    if first_merit is not None and last_merit is not None:
        objective_reduction = float(first_merit["objective"] - last_merit["objective"])

    return {
        "case_dir": str(case_dir),
        "run_summary_path": str(run_summary_path),
        "run_summary": run_summary,
        "solver_log": str(solver_log),
        "solver_log_exists": solver_log.exists(),
        "actual_solver_completed": actual_solver_completed,
        "fatal_log_patterns": fatal_matches,
        "alpha_design_observed": alpha_design_observed,
        "brinkman_sensitivity_observed": brinkman_sensitivity_observed,
        "fixed_mesh_updates_observed": fixed_mesh_updates_observed,
        "mesh_build_count": mesh_build_count,
        "remeshing_command_count": remeshing_command_count,
        "optimisation_iteration_count": len(merit_rows),
        "first_merit": first_merit,
        "last_merit": last_merit,
        "objective_reduction": objective_reduction,
        "latest_time_dir": str(latest_time) if latest_time else None,
        "latest_fields": latest_fields,
        "has_alpha_tilda": any(name.startswith("alphaTilda") for name in latest_fields),
        "has_beta": any(name.startswith("beta") for name in latest_fields),
        "vtk_files": vtk_files,
    }


def parse_merit_function(path: Path) -> list[dict[str, float | int]]:
    if not path.exists():
        return []
    rows: list[dict[str, float | int]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(
            r"^\s*(\d+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+",
            line,
        )
        if not match:
            continue
        groups = re.findall(r"\(([^)]*)\)", line)
        constraint = _last_float(groups[-1]) if groups else None
        rows.append(
            {
                "iteration": int(match.group(1)),
                "merit": float(match.group(2)),
                "objective": float(match.group(3)),
                "constraint": float(constraint) if constraint is not None else 0.0,
            }
        )
    return rows


def build_openfoam_capability_matrix(
    environment: dict[str, object],
    case_analysis: dict[str, object],
    porous_force_validation: dict[str, object] | None = None,
    downforce_validation: dict[str, object] | None = None,
    efficiency_validation: dict[str, object] | None = None,
) -> dict[str, object]:
    facts = dict(environment.get("facts") or {})
    runtime_ok = bool(dict(environment.get("runtime_inspection") or {}).get("ok"))
    porous_force_passed = bool(
        porous_force_validation
        and porous_force_validation.get("status") == "pass"
        and porous_force_validation.get("sign_match") is True
    )
    downforce_passed = bool(
        downforce_validation
        and downforce_validation.get("status") == "pass"
        and downforce_validation.get("sign_match") is True
    )
    efficiency_passed = bool(
        efficiency_validation
        and efficiency_validation.get("status") == "pass"
        and efficiency_validation.get("sign_match") is True
        and efficiency_validation.get("separate_sensitivity_fields") is True
    )
    if porous_force_passed and downforce_passed:
        separate_status = "pass"
        separate_note = "Independent directional derivatives passed centered checks."
    elif efficiency_passed:
        separate_status = "partial_downforce_accuracy_pending"
        separate_note = (
            "Separate fields and their efficiency combination are verified, but the "
            "downforce-only directional error remains above the strict tolerance."
        )
    elif porous_force_passed:
        separate_status = "partial_single_direction_verified"
        separate_note = (
            "Instantiate separate adjoint solvers for drag and downforce and export both fields."
        )
    else:
        separate_status = "blocked"
        separate_note = (
            "Separate derivatives require a porous directional-force objective or equivalent "
            "source-term functional."
        )

    def capability(status: str, evidence: list[str], note: str) -> dict[str, object]:
        return {"status": status, "evidence": evidence, "note": note}

    return {
        "fixed_mesh_density_design_variable": capability(
            "pass" if case_analysis["alpha_design_observed"] and facts.get("topo_design_variables") == "1" else "fail",
            ["topODesignVariables source", "runtime alpha design-variable log"],
            "The tutorial updates alpha-derived topology variables without remeshing.",
        ),
        "brinkman_darcy_primal": capability(
            "pass" if facts.get("topo_source") == "1" and case_analysis["actual_solver_completed"] else "fail",
            ["topOSource source", "completed porosity-based tutorial"],
            "OpenFOAM topOSource implements the Brinkman momentum source.",
        ),
        "volume_topology_adjoint": capability(
            "pass" if facts.get("topo_sensitivity") == "1" and case_analysis["brinkman_sensitivity_observed"] else "fail",
            ["sensitivityTopO source", "runtime Brinkman sensitivity log"],
            "The topology adjoint assembles cell sensitivities with respect to beta/alpha.",
        ),
        "constrained_update_method": capability(
            "pass" if facts.get("mma_update") == "1" and len(case_analysis["latest_fields"]) > 0 else "fail",
            ["MMA source", "tutorial ISQP volume-constrained optimization history"],
            "MMA exists and the tutorial demonstrates an ISQP constrained update.",
        ),
        "helmholtz_regularisation": capability(
            "pass" if facts.get("helmholtz_regularisation") == "1" else "fail",
            ["Helmholtz regularisation source"],
            "Density regularisation is available in the installed source tree.",
        ),
        "exportable_volume_fields": capability(
            "pass" if case_analysis["has_alpha_tilda"] and case_analysis["has_beta"] and case_analysis["vtk_files"] else "partial",
            ["reconstructed alphaTilda/beta", "foamToVTK output"],
            "Final density and interpolation fields are available for ParaView.",
        ),
        "turbulent_topology_path": capability(
            "available_not_executed" if facts.get("turbulent_porosity_tutorial") == "1" else "missing",
            ["installed turbulent porosity-based tutorials"],
            "The installed image includes turbulent examples; this spike has not run them.",
        ),
        "patch_force_objective": capability(
            "pass" if facts.get("force_objective") == "1" and facts.get("force_objective_patch_based") == "1" else "fail",
            ["objectiveForce source"],
            "The existing force objective integrates pressure and viscous force on boundary patches.",
        ),
        "porous_body_directional_force_objective": capability(
            "pass" if porous_force_passed else "blocked_custom_objective_required",
            (
                ["custom porousDirectionalForce objective", "centered finite-difference validation"]
                if porous_force_passed
                else ["objectiveForce is patch-based", "topOSource is an internal volume source"]
            ),
            (
                "The custom objective passed a centered directional derivative check."
                if porous_force_passed
                else "No verified objective directly integrates directional Brinkman reaction over the porous design field."
            ),
        ),
        "separate_downforce_drag_density_derivatives": capability(
            separate_status,
            (
                [
                    "directional objective supports arbitrary direction",
                    "separate drag/downforce topology fields",
                    "centered efficiency-combination validation",
                ]
                if efficiency_passed
                else ["directional objective supports arbitrary direction", "streamwise derivative validated"]
                if porous_force_passed
                else ["volume topology adjoint exists", "porous directional-force objective is missing"]
            ),
            separate_note,
        ),
        "efficiency_constraint_density_derivative": capability(
            "pass" if efficiency_passed else "blocked",
            (
                ["E_min*dCd/dalpha-dCdf/dalpha VTK", "centered finite-difference validation"]
                if efficiency_passed
                else ["separate downforce/drag derivatives are not yet available"]
            ),
            (
                "The combined efficiency derivative passed its centered directional check."
                if efficiency_passed
                else "The efficiency derivative cannot be accepted until both aerodynamic derivatives exist."
            ),
        ),
        "docker_automation": capability(
            "pass" if runtime_ok and case_analysis["actual_solver_completed"] else "fail",
            ["Docker runtime inspection", "completed mounted tutorial case"],
            "The case executes through the existing Windows-to-Docker path.",
        ),
    }


def _overall_status(capabilities: dict[str, object]) -> str:
    porous_status = dict(capabilities["porous_body_directional_force_objective"])["status"]
    separate_status = dict(capabilities["separate_downforce_drag_density_derivatives"])["status"]
    efficiency_status = dict(capabilities["efficiency_constraint_density_derivative"])["status"]
    if porous_status != "pass":
        return "partial_pass_custom_force_objective_required"
    if separate_status != "pass":
        if separate_status == "partial_downforce_accuracy_pending":
            return "partial_pass_downforce_accuracy_required"
        return "partial_pass_separate_force_adjoint_required"
    if efficiency_status != "pass":
        return "partial_pass_efficiency_derivative_required"
    statuses = {dict(value)["status"] for value in capabilities.values()}
    if statuses == {"pass"}:
        return "pass"
    if statuses <= {"pass", "available_not_executed"}:
        return "pass_t0"
    return "partial"


def _next_required_action(capabilities: dict[str, object]) -> str:
    if dict(capabilities["porous_body_directional_force_objective"])["status"] != "pass":
        return (
            "Implement and verify a porous-body directional-force objective "
            "that exposes separate downforce and drag density derivatives."
        )
    if dict(capabilities["separate_downforce_drag_density_derivatives"])["status"] != "pass":
        if dict(capabilities["efficiency_constraint_density_derivative"])["status"] == "pass":
            return (
                "Reduce the downforce-only directional derivative error on a canonical "
                "three-dimensional force case before closing T0."
            )
        return (
            "Instantiate separate drag and downforce adjoint solvers, export both "
            "topology sensitivity fields, and validate each direction."
        )
    if dict(capabilities["efficiency_constraint_density_derivative"])["status"] != "pass":
        return (
            "Construct the efficiency-constraint density derivative from the separate "
            "drag and downforce fields and validate it with centered differences."
        )
    return (
        "Proceed to T1: define the fixed-grid topology data contract and connect "
        "the verified three-dimensional force sensitivities to its artifacts."
    )


def _run_command(command: list[str], *, timeout_seconds: int) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command": command,
            "returncode": int(completed.returncode),
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "ok": completed.returncode == 0,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "ok": False,
        }


def _parse_key_value_lines(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            result[key.strip()] = value.strip()
    return result


def _read_json_if_present(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _latest_numeric_directory(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        candidates.append((value, path))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _last_float(text: str) -> float | None:
    values = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
    return float(values[-1]) if values else None


def _probe_markdown(summary: dict[str, object]) -> str:
    capabilities = dict(summary["capabilities"])
    case_analysis = dict(summary["case_analysis"])
    rows = "\n".join(
        f"| {name} | {dict(record)['status']} | {dict(record)['note']} |"
        for name, record in capabilities.items()
    )
    return f"""# Fixed-Grid Backend Probe

| Field | Value |
| --- | --- |
| Backend | {summary['backend']} |
| Docker image | `{summary['docker_image']}` |
| Overall status | `{summary['overall_status']}` |
| Actual solver completed | {case_analysis['actual_solver_completed']} |
| Fixed-mesh updates observed | {case_analysis['fixed_mesh_updates_observed']} |
| Optimisation iterations | {case_analysis['optimisation_iteration_count']} |
| Objective reduction | {case_analysis['objective_reduction']} |
| ParaView files | {len(case_analysis['vtk_files'])} |

## Capabilities

| Capability | Status | Note |
| --- | --- | --- |
{rows}

## Next Required Action

{summary['next_required_action']}
"""
