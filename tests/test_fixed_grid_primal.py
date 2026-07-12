from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from cfd_sdf.fixed_grid_contract import FIXED_GRID_CONTRACT_SCHEMA_VERSION
from cfd_sdf.fixed_grid_primal import (
    prepare_fixed_grid_primal_case,
    run_fixed_grid_primal_suite,
    summarize_fixed_grid_primal_case,
)


def test_prepare_fixed_grid_primal_case_writes_density_alpha_and_no_remesh(
    tmp_path: Path,
) -> None:
    topology_state = _write_fixed_grid_state(tmp_path / "contract")
    template = _write_template_case(tmp_path / "template")

    artifacts = prepare_fixed_grid_primal_case(
        topology_state,
        case_dir=tmp_path / "case",
        template_case_dir=template,
        density_variant="threshold-solid",
    )

    assert artifacts.case_metadata_json.exists()
    assert artifacts.input_density_vti.exists()
    assert artifacts.primal_summary_json.exists()
    metadata = json.loads(artifacts.case_metadata_json.read_text(encoding="utf-8"))
    assert metadata["density_variant"] == "threshold-solid"
    assert metadata["run_policy"]["uses_remeshing"] is False
    assert metadata["mask_counts"]["fixed_zero"] == 2

    alpha = _read_internal_scalar_field(artifacts.case_dir / "0.orig" / "alpha")
    assert alpha.shape == (12,)
    assert np.count_nonzero(alpha == 1.0) == 3
    assert np.all(alpha[[0, 3]] == 0.0)

    allrun = (artifacts.case_dir / "Allrun").read_text(encoding="utf-8")
    assert "snappyHexMesh" not in allrun
    assert "setFields" not in allrun
    assert "write_fixed_grid_cell_zones.sh" in allrun
    optimisation = (artifacts.case_dir / "system" / "optimisationDict").read_text(
        encoding="utf-8"
    )
    assert "fixedZeroFromMask" in optimisation
    assert "nIters 1;" in optimisation
    control = (artifacts.case_dir / "system" / "controlDict").read_text(
        encoding="utf-8"
    )
    extension_library = Path(
        "openfoam_extensions/porousDirectionalForce/lib/libcfdSdfPorousObjectives.so"
    )
    if extension_library.exists():
        assert "./lib/libcfdSdfPorousObjectives.so" in control
    else:
        # The platform-specific OpenFOAM binary is intentionally not tracked.
        # A source-only checkout must preserve the declared library name and
        # report staging as unavailable rather than assuming a local .so.
        assert 'libs ("libcfdSdfPorousObjectives.so");' in control
        assert "./lib/libcfdSdfPorousObjectives.so" not in control


def test_filtered_perturbation_is_deterministic_and_masked(tmp_path: Path) -> None:
    topology_state = _write_fixed_grid_state(tmp_path / "contract")
    template = _write_template_case(tmp_path / "template")

    first = prepare_fixed_grid_primal_case(
        topology_state,
        case_dir=tmp_path / "case_a",
        template_case_dir=template,
        density_variant="filtered-perturbation",
        perturbation_seed=42,
        perturbation_amplitude=0.2,
    )
    second = prepare_fixed_grid_primal_case(
        topology_state,
        case_dir=tmp_path / "case_b",
        template_case_dir=template,
        density_variant="filtered-perturbation",
        perturbation_seed=42,
        perturbation_amplitude=0.2,
    )

    a = pv.read(first.input_density_vti).cell_data["rho_input"]
    b = pv.read(second.input_density_vti).cell_data["rho_input"]
    assert np.allclose(a, b)
    assert np.all((0.0 <= a) & (a <= 1.0))
    assert np.all(a[[0, 3]] == 0.0)


def test_summarize_fixed_grid_primal_case_parses_log_histories(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    objective_dir = case_dir / "optimisation" / "objective" / "0"
    objective_dir.mkdir(parents=True)
    _write_objective(objective_dir / "dragas1", 0.4)
    _write_objective(objective_dir / "downforcedownforce", 0.9)
    (case_dir / "fixed_grid_primal_case_metadata.json").write_text(
        json.dumps(
            {
                "kind": "fixed_grid_primal_case",
                "density_variant": "seed",
                "density_input": {
                    "hash_sha256_float32": "abc",
                    "statistics": {"mean": 0.1},
                },
                "mask_counts": {"active_design": 10},
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "log.adjointOptimisationFoam").write_text(
        "DILUPBiCGStab:  Solving for Ux, Initial residual = 1, Final residual = 0.01, No Iterations 2\n"
        "DICPCG:  Solving for p, Initial residual = 0.5, Final residual = 0.02, No Iterations 3\n"
        "time step continuity errors : sum local = 1e-05, global = 2e-07, cumulative = 3e-07\n"
        "drag : 0.4\n"
        "downforce : 0.9\n"
        "op1 solution converged in 12 iterations\n"
        "\nEnd\n\n"
        "Finalising parallel run\n",
        encoding="utf-8",
    )

    summary = summarize_fixed_grid_primal_case(case_dir)

    assert summary["status"] == "converged"
    assert summary["drag_coefficient"] == 0.4
    assert summary["downforce_coefficient"] == 0.9
    assert summary["efficiency_constraint"] == pytest.approx(0.3)
    assert summary["history"]["residual_rows"] == 2
    assert summary["history"]["mass_balance_rows"] == 1
    assert summary["history"]["force_rows"] == 1
    assert (case_dir / "fixed_grid_force_history.csv").exists()


def test_run_fixed_grid_primal_suite_dry_run_writes_all_variants(
    tmp_path: Path,
) -> None:
    topology_state = _write_fixed_grid_state(tmp_path / "contract")
    template = _write_template_case(tmp_path / "template")

    artifacts = run_fixed_grid_primal_suite(
        topology_state,
        run_dir=tmp_path / "suite",
        template_case_dir=template,
        execute=False,
        include_reproducibility_repeat=True,
    )

    assert artifacts.summary["ok"] is True
    assert artifacts.summary["case_count"] == 5
    assert artifacts.summary["reproducibility"]["status"] == "not_executed"
    assert artifacts.summary_json.exists()
    assert artifacts.summary_markdown.exists()
    assert artifacts.history_csv.exists()
    assert {case.case_dir.name for case in artifacts.cases} == {
        "all_fluid",
        "threshold_solid",
        "seed",
        "filtered_perturbation",
        "seed_repeat",
    }


def _write_fixed_grid_state(directory: Path) -> Path:
    directory.mkdir(parents=True)
    image = pv.ImageData(
        dimensions=(4, 3, 3),
        spacing=(0.5, 0.4, 0.3),
        origin=(-1.0, -0.4, -0.3),
    )
    count = image.n_cells
    rho = np.zeros(count, dtype=np.float32)
    rho[[4, 5, 6]] = 0.5
    allowed = np.ones(count, dtype=np.uint8)
    active = np.ones(count, dtype=np.uint8)
    allowed[[0, 3]] = 0
    active[[0, 3]] = 0
    image.cell_data["rho"] = rho
    image.cell_data["rho_filtered"] = rho
    image.cell_data["rho_projected"] = rho
    image.cell_data["alpha"] = 100.0 * rho
    image.cell_data["allowed_mask"] = allowed
    image.cell_data["forbidden_mask"] = np.zeros(count, dtype=np.uint8)
    image.cell_data["fixed_solid_mask"] = np.zeros(count, dtype=np.uint8)
    image.cell_data["root_mask"] = np.zeros(count, dtype=np.uint8)
    image.cell_data["active_design_mask"] = active
    image.field_data["schema_version"] = np.array(
        [FIXED_GRID_CONTRACT_SCHEMA_VERSION],
        dtype=np.int32,
    )
    image.field_data["kind"] = np.array(["fixed_grid_density"])
    image.field_data["cell_order"] = np.array(["vtk-x-fastest"])
    image.save(directory / "density.vti")
    vtk_dir = directory / "source_vtk"
    vtk_dir.mkdir()
    source = image.cast_to_unstructured_grid()
    source.cell_data["alpha"] = rho
    source.save(vtk_dir / "internal.vtu")
    state = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": {
            "location": "cell",
            "cell_order": "vtk-x-fastest",
            "origin": list(image.origin),
            "spacing": list(image.spacing),
            "cell_shape": [3, 2, 2],
            "point_dimensions": list(image.dimensions),
            "cell_count": count,
            "bounds": [[-1.0, -0.4, -0.3], [0.5, 0.4, 0.3]],
        },
        "density_vti": "density.vti",
        "source_solver": {
            "case_dir": str(directory / "template_placeholder"),
            "initial_vtk": str(vtk_dir / "internal.vtu"),
        },
    }
    path = directory / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def _write_template_case(case_dir: Path) -> Path:
    for relative in ("0.orig", "constant", "system"):
        (case_dir / relative).mkdir(parents=True)
    (case_dir / "0.orig" / "alpha").write_text(
        "FoamFile\n{\n    class volScalarField;\n    object alpha;\n}\n"
        "dimensions [0 0 0 0 0 0 0];\n"
        "internalField uniform 0;\n"
        "boundaryField\n"
        "{\n"
        "    inlet { type zeroGradient; }\n"
        "    outlet { type zeroGradient; }\n"
        "    spanMin { type symmetryPlane; }\n"
        "    spanMax { type symmetryPlane; }\n"
        "    lower { type symmetryPlane; }\n"
        "    upper { type symmetryPlane; }\n"
        "}\n",
        encoding="utf-8",
    )
    (case_dir / "0.orig" / "U").write_text("", encoding="utf-8")
    (case_dir / "0.orig" / "p").write_text("", encoding="utf-8")
    (case_dir / "system" / "optimisationDict").write_text(
        "primalSolvers { op1 { solutionControls { nIters 1000; } } }\n"
        "adjointManagers { adjManager1 { adjointSolvers { as1 { solutionControls { nIters 4000; } } } } }\n"
        "optimisation { designVariables { fixedZeroPorousZones ( oldZone ); betaMax 100; } }\n",
        encoding="utf-8",
    )
    (case_dir / "system" / "controlDict").write_text(
        "application adjointOptimisationFoam;\nlibs (\"libcfdSdfPorousObjectives.so\");\n",
        encoding="utf-8",
    )
    return case_dir


def _write_objective(path: Path, value: float) -> None:
    path.write_text(
        f"# J JCycle\n1 {value:.12g} {value:.12g}\n",
        encoding="utf-8",
    )


def _read_internal_scalar_field(path: Path) -> np.ndarray:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;",
        text,
        flags=re.DOTALL,
    )
    assert match is not None
    expected = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", dtype=np.float64)
    assert values.size == expected
    return values
