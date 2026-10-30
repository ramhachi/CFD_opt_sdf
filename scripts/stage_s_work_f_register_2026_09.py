"""Register the Stage S Work F baseline manifest (baseline preparation only).

Binds the registered Stage S baseline v2, the matched-Re laminar problem spec,
the V1 voxel size, the exact case/output paths, the clearance and mesh
qualification profiles, the drag/downforce response identities, the mesh-only
command set and the fail-closed stop rules. Refuses to overwrite. The manifest
authorizes baseline case preparation and a mesh-only run; it does not authorize
``simpleFoam``, surface FD or a shape update.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import STAGE_V_CLEARANCE_PROFILE_V1  # noqa: E402

BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
PREFLIGHT_SCRIPT = ROOT / "scripts/stage_s_work_f_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
LEVEL_NAME = "V1"
VOXEL_SIZE_M = 0.05
CASE_DIR = "work/stage_s_work_f_v1/baseline/V1"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def build() -> dict:
    if MANIFEST.exists():
        raise SystemExit("Work F manifest already exists; refuse overwrite")
    baseline = ca.load_json(BASELINE)
    if baseline["gate"]["ready_for_stage_s"] is not True:
        raise SystemExit("baseline gate is not ready_for_stage_s=true")
    spec = load_problem_spec(SPEC)
    flow = spec.flow_cases[0]
    if len(spec.flow_cases) != 1:
        raise SystemExit("matched-Re spec must declare exactly one flow case")
    responses = {response.id: response for response in spec.responses}
    if set(responses) != {"drag", "downforce"}:
        raise SystemExit("matched-Re spec must declare the drag and downforce responses")
    reference = spec.reference_values
    bounds = spec.grid.domain_bounds_m
    image_id = subprocess.run(
        ["docker", "image", "inspect", OPENFOAM_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    manifest = {
        "kind": "stage_s_work_f_manifest_v1",
        "schema_version": 1,
        "immutable": True,
        "status": "registered_preflight_pending",
        "baseline": {"path": str(BASELINE.relative_to(ROOT)), "sha256": _sha256(BASELINE)},
        "problem_spec": {"path": str(SPEC.relative_to(ROOT)), "sha256": _sha256(SPEC)},
        "level": {"name": LEVEL_NAME, "voxel_size_m": VOXEL_SIZE_M},
        "case_dir": CASE_DIR,
        "preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": _sha256(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/stage_s_work_f_v1_preflight_2026_09.json",
            "requirement": "must pass before the mesh-only run",
        },
        "mesh_evidence_path": "docs/evidence/stage_s_work_f_v1_mesh_2026_09.json",
        "openfoam_image": OPENFOAM_IMAGE,
        "openfoam_image_id": image_id,
        "profiles": {
            "mesh_solver": STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"],
            "clearance": STAGE_V_CLEARANCE_PROFILE_V1["profile_id"],
            "surface_fd": "fd_gradient_v1",
        },
        "response_identities": {
            "drag": {
                "response_id": "drag",
                "direction": list(responses["drag"].direction),
                "coefficient": "Cd",
                "bound_kind": "relative",
                "grid_relative_max": STAGE_V_QUALIFICATION_PROFILE_V1["grid_convergence"]["relative_change_max"],
                "stationarity_relative_max": STAGE_V_QUALIFICATION_PROFILE_V1["force_stationarity"]["relative_drift_max"],
            },
            "downforce": {
                "response_id": "downforce",
                "direction": list(responses["downforce"].direction),
                "coefficient": "downforce",
                "bound_kind": "absolute",
                "grid_absolute_max": STAGE_V_QUALIFICATION_PROFILE_V1["grid_convergence"]["absolute_change_max"],
                "stationarity_absolute_max": STAGE_V_QUALIFICATION_PROFILE_V1["force_stationarity"]["absolute_drift_max"],
                "objective_sign": -1,
                "note": "the Stage T objective is J = -downforce; the solver's liftDir is the negated downforce direction",
            },
        },
        "expected_case": {
            "flow_case_id": flow.id,
            "turbulence_model": flow.turbulence.model,
            "operating_point": {
                "velocity_mps": flow.freestream_velocity_mps[0],
                "density": flow.fluid.density_kg_m3,
                "viscosity": flow.fluid.dynamic_viscosity_pa_s,
            },
            "force_reference": {
                "area_m2": reference.area_m2,
                "length_m": reference.length_m,
                "moment_center_m": list(reference.moment_center_m),
                "drag_dir": list(responses["drag"].direction),
                "lift_dir": [0.0 if c == 0.0 else -c for c in responses["downforce"].direction],
            },
            "force_patch": "design_candidate",
            "domain_bounds_m": {"lower": list(bounds.lower), "upper": list(bounds.upper)},
            "voxel_size_m": VOXEL_SIZE_M,
        },
        "mesh_gate": dict(STAGE_V_QUALIFICATION_PROFILE_V1),
        "solver_budget": {
            "mesh_timeout_seconds": 3600,
            "solver_timeout_seconds": 7200,
            "max_mesh_runs": 1,
            "max_solver_runs": 1,
        },
        "stop_rules": [
            "any pinned hash mismatch stops before any OpenFOAM command",
            "a failed clearance preflight or a failed case-metadata check stops before meshing",
            "a failed checkMesh profile stops before simpleFoam",
            "the mesh-only runner never starts simpleFoam",
        ],
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "registration and case preparation only; no mesh, solver, force or stationarity claim",
            "no adjoint, surface FD or shape update is authorized by this manifest",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(_sha256(MANIFEST) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "sha256": _sha256(MANIFEST),
                "baseline": manifest["baseline"],
                "level": manifest["level"],
                "openfoam_image_id": manifest["openfoam_image_id"],
            },
            indent=2,
        )
    )
    return manifest


if __name__ == "__main__":
    build()
