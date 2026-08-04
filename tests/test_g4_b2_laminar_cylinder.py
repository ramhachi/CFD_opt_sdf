from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cfd_sdf.cli import app
import cfd_sdf.g4_b2_laminar_cylinder as cylinder_module
from cfd_sdf.g4_b2_laminar_cylinder import (
    G4_B2_CYLINDER_COMPILATION_FILENAME,
    G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME,
    _verify_porous_case_semantics,
    compile_g4_b2_cylinder_benchmark,
    run_g4_b2_cylinder_cases,
)


SPEC = Path("examples/g4_b2_laminar/cylinder.yaml")
runner = CliRunner()


@pytest.fixture(scope="module")
def compiled(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("g4_b2_cylinder") / "compiled"
    result = compile_g4_b2_cylinder_benchmark(spec_path=SPEC, output_dir=root)
    return result.root, json.loads(result.index_path.read_text(encoding="utf-8"))


def _case(index: dict, representation: str, grid_id: str) -> dict:
    return next(case for case in index["cases"] if case["representation"] == representation and case["grid_id"] == grid_id)


def test_contract_binds_fixed_laminar_cylinder_physics_and_three_grids(compiled: tuple[Path, dict]) -> None:
    _, index = compiled

    assert index["status"] == "compiled_not_runtime_qualified"
    assert index["physics"] == {
        "openfoam_version": "v2512", "solver": "simpleFoam",
        "flow": "incompressible_steady_newtonian_laminar", "density_kg_m3": 1.225,
        "kinematic_viscosity_m2_s": 1.5e-5, "freestream_velocity_mps": 0.03,
    }
    assert index["geometry"]["x_bounds_in_diameters"] == [-15.0, 25.0]
    assert index["geometry"]["y_bounds_in_diameters"] == [-15.0, 15.0]
    assert index["grids"]["nominal_h_over_diameter"] == [0.125, 0.0625, 0.03125]
    assert [(case["representation"], case["grid_id"]) for case in index["cases"]] == [
        ("body_fitted", "coarse"), ("body_fitted", "medium"), ("body_fitted", "fine"),
        ("porous_cartesian", "coarse"), ("porous_cartesian", "medium"), ("porous_cartesian", "fine"),
    ]
    assert [case["nominal_h_m"] for case in index["cases"][:3]] == pytest.approx([0.01 / 8, 0.01 / 16, 0.01 / 32])
    assert all(case["one_z_cell"] for case in index["cases"])
    expected_phase_logs = {
        "phase_a": {"solver_log_relpath": "log.simpleFoam.phaseA"},
        "phase_b": {"solver_log_relpath": "log.simpleFoam.phaseB"},
    }
    assert index["two_phase_runtime_protocol"] == expected_phase_logs
    assert all(case["two_phase_runtime_protocol"] == expected_phase_logs for case in index["cases"])


def test_body_fitted_o_grid_uses_fixed_eight_sector_arc_topology_and_no_slip_wall(compiled: tuple[Path, dict]) -> None:
    root, index = compiled
    coarse = _case(index, "body_fitted", "coarse")
    medium = _case(index, "body_fitted", "medium")
    fine = _case(index, "body_fitted", "fine")

    assert [case["mesh_contract"]["cells_per_block"] for case in (coarse, medium, fine)] == [[3, 120, 1], [6, 240, 1], [12, 480, 1]]
    assert [case["mesh_contract"]["total_cells"] for case in (coarse, medium, fine)] == [2880, 11520, 46080]
    assert len(coarse["mesh_contract"]["arc_controls"]) == 8
    assert len(coarse["mesh_contract"]["block_order"]) == 8
    block_mesh = (root / "body_fitted" / "coarse" / "system" / "blockMeshDict").read_text(encoding="utf-8")
    velocity = (root / "body_fitted" / "coarse" / "0" / "U").read_text(encoding="utf-8")
    control = (root / "body_fitted" / "coarse" / "system" / "controlDict.phaseB.template").read_text(encoding="utf-8")
    assert block_mesh.count("    arc ") == 16
    assert block_mesh.count("    hex ") == 8
    assert "cylinder { type wall;" in block_mesh
    assert "frontAndBack { type empty;" in block_mesh
    assert "cylinder { type noSlip; }" in velocity
    assert "patches (cylinder);" in control
    assert "rhoInf 1.225;" in control


def test_body_fitted_o_grid_contract_records_positive_blockmesh_winding(compiled: tuple[Path, dict]) -> None:
    root, index = compiled
    coarse = _case(index, "body_fitted", "coarse")
    vertices = coarse["mesh_contract"]["vertices"]
    blocks = coarse["mesh_contract"]["block_order"]
    block_mesh = (root / "body_fitted" / "coarse" / "system" / "blockMeshDict").read_text(encoding="utf-8")

    # The first four vertices are the +z face and the final four are z=0.
    # This is the exact right-handed hex contract expected by blockMesh.
    assert blocks[0]["vertices"] == [16, 17, 25, 24, 0, 1, 9, 8]
    assert "hex (16 17 25 24 0 1 9 8)" in block_mesh

    for block in blocks:
        first, second, _, fourth, fifth, *_ = (vertices[index] for index in block["vertices"])
        edge_a = [second[axis] - first[axis] for axis in range(3)]
        edge_b = [fourth[axis] - first[axis] for axis in range(3)]
        edge_c = [fifth[axis] - first[axis] for axis in range(3)]
        cross = [
            edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
            edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
            edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0],
        ]
        assert sum(cross[axis] * edge_c[axis] for axis in range(3)) > 0.0


def test_cartesian_refinement_and_area_fraction_are_deterministic_nonbinary_and_hash_bound(compiled: tuple[Path, dict]) -> None:
    root, index = compiled
    cases = [_case(index, "porous_cartesian", grid) for grid in ("coarse", "medium", "fine")]

    assert [case["mesh_contract"]["cells"] for case in cases] == [[320, 240, 1], [640, 480, 1], [1280, 960, 1]]
    assert [case["mesh_contract"]["total_cells"] for case in cases] == [76800, 307200, 1228800]
    assert [case["area_fraction_contract"]["count"] for case in cases] == [76800, 307200, 1228800]
    assert all(case["area_fraction_contract"]["algorithm"] == "fixed_16x16_midpoint_subcells" for case in cases)
    assert all(case["area_fraction_contract"]["subcells_per_cell"] == 256 for case in cases)
    beta_text = (root / "porous_cartesian" / "fine" / "0" / "beta").read_text(encoding="utf-8")
    assert "object beta;" in beta_text
    assert "1228800" in beta_text
    # The fixed subcell rule creates fractional values at disk-cut cells;
    # no centre-cell binary mask can satisfy this property.
    assert "0.0390625" in beta_text
    assert _case(index, "porous_cartesian", "fine")["file_sha256"]["0/beta"] == hashlib.sha256(beta_text.encode("utf-8")).hexdigest()


def test_porous_extension_contract_and_allrun_are_exact_and_source_bound(compiled: tuple[Path, dict]) -> None:
    root, index = compiled
    case = _case(index, "porous_cartesian", "medium")
    fv_options = (root / "porous_cartesian" / "medium" / "constant" / "fvOptions").read_text(encoding="utf-8")
    control = (root / "porous_cartesian" / "medium" / "system" / "controlDict").read_text(encoding="utf-8")
    allrun = (root / "porous_cartesian" / "medium" / "Allrun").read_text(encoding="utf-8")

    assert index["extension"] == {
        "library": "libcfdSdfLinearBrinkman.so", "fv_option_type": "cfdSdfLinearBrinkman",
        "option_name": "porousCylinderResistance", "area_fraction_field": "beta",
        "beta_max_m_inv_s": 150000.0, "darcy_number": 1.0e-6,
        "darcy_number_formula": "nu/(betaMax*D^2)", "darcy_number_derived": 1.0e-6,
        "beta_mapping": "source=-betaMax*beta*U;resistance=betaMax*beta*U",
    }
    for line in ("active yes;", "selectionMode all;", "U U;", "betaField beta;", "betaMax [0 0 -1 0 0 0 0] 150000;", "resistanceField brinkmanResistance;"):
        assert line in fv_options
    assert 'libs ("./lib/libcfdSdfLinearBrinkman.so");' in control
    assert "cp system/controlDict.phaseA system/controlDict" in allrun
    assert "blockMesh > log.blockMesh 2>&1" in allrun
    assert "checkMesh -allGeometry -allTopology > log.checkMesh 2>&1" in allrun
    assert "simpleFoam > log.simpleFoam.phaseA 2>&1" in allrun
    assert "simpleFoam > log.simpleFoam.phaseB 2>&1" in allrun
    assert case["extension_contract"] == index["extension"]
    assert case["extension_source_contract"] == index["extension_source_contract"]
    assert index["extension_source_contract"]["source_tree_sha256"]
    assert [item["path"] for item in index["extension_source_contract"]["source_files"]] == [
        "cfdSdfLinearBrinkman.C", "cfdSdfLinearBrinkman.H", "Make/files", "Make/options",
    ]
    source_manifest = json.loads((root / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert source_manifest == index["extension_source_manifest"]
    assert source_manifest["contains_prebuilt_library"] is False
    for item in source_manifest["source_files"]:
        snapshot = root / "extension_source" / item["path"]
        project_source = Path("openfoam_extensions/cfdSdfLinearBrinkman") / item["path"]
        assert snapshot.read_bytes() == project_source.read_bytes()
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == item["sha256"]
    assert not list((root / "extension_source").rglob("*.so"))
    assert "extension_source_hash" in index["runtime_evidence_requirements"]["porous"]
    assert "extension_build_hash" in index["runtime_evidence_requirements"]["porous"]


def test_two_phase_dictionaries_preserve_physics_and_make_measurement_tail_exact(compiled: tuple[Path, dict]) -> None:
    root, _ = compiled
    case = root / "body_fitted" / "coarse"
    control_a = (case / "system" / "controlDict.phaseA").read_text(encoding="utf-8")
    control_b = (case / "system" / "controlDict.phaseB.template").read_text(encoding="utf-8")
    solution_a = (case / "system" / "fvSolution.phaseA").read_text(encoding="utf-8")
    solution_b = (case / "system" / "fvSolution.phaseB").read_text(encoding="utf-8")

    assert "startFrom startTime;" in control_a
    assert "endTime 4000;" in control_a
    assert "writeAtEnd yes;" in control_a
    assert "residualControl { p 1e-8; U 1e-8; }" in solution_a
    assert "startFrom latestTime;" in control_b
    assert "endTime __PHASE_B_END_TIME__;" in control_b
    assert "writeInterval 200;" in control_b
    assert "residualControl" not in solution_b
    assert "tolerance 1e-10;" in solution_a and "tolerance 1e-10;" in solution_b
    assert "rhoInf 1.225;" in control_b
    assert "writeInterval 1;" in control_b
    assert "pressureProbes" in control_b


def test_compilation_is_immutable_and_dry_runner_keeps_source_bundle_unchanged(compiled: tuple[Path, dict], tmp_path: Path) -> None:
    root, index = compiled
    source_hash = hashlib.sha256((root / G4_B2_CYLINDER_COMPILATION_FILENAME).read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        compile_g4_b2_cylinder_benchmark(spec_path=SPEC, output_dir=root)

    artifact = run_g4_b2_cylinder_cases(compilation_dir=root, output_dir=tmp_path / "runtime", through_grid="fine", backend="docker", execute=False)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "contract_only_not_executed"
    assert len(payload["cases"]) == 6
    assert all(case["status"] == "contract_only_not_executed" for case in payload["cases"])
    assert hashlib.sha256((root / G4_B2_CYLINDER_COMPILATION_FILENAME).read_bytes()).hexdigest() == source_hash
    assert (artifact.parent / "cases" / "body_fitted" / "fine" / "openfoam_run_summary.json").is_file()
    assert (artifact.parent / "cases" / "porous_cartesian" / "fine" / "openfoam_run_summary.json").is_file()
    porous = next(item for item in payload["cases"] if item["representation"] == "porous_cartesian")
    assert porous["run"]["extension"]["build"]["status"] == "not_executed"
    assert "C:" not in json.dumps(porous["run"]["extension"]["build"]["canonical_container_command"])
    assert [(item["grid_id"], item["representation"]) for item in payload["cases"]] == [
        ("coarse", "body_fitted"), ("coarse", "porous_cartesian"),
        ("medium", "body_fitted"), ("medium", "porous_cartesian"),
        ("fine", "body_fitted"), ("fine", "porous_cartesian"),
    ]
    assert payload["phase_timeouts_seconds"] == {
        "coarse": {"phase_a": 900, "phase_b": 300},
        "medium": {"phase_a": 1800, "phase_b": 600},
        "fine": {"phase_a": 5400, "phase_b": 1800},
    }
    assert all(item["run"]["phase_a"]["status"] == "planned" for item in payload["cases"])
    assert all(item["run"]["phase_b"]["status"] == "planned" for item in payload["cases"])


def test_porous_semantic_check_rejects_changed_beta_contract(compiled: tuple[Path, dict], tmp_path: Path) -> None:
    root, _ = compiled
    copied = tmp_path / "porous"
    import shutil
    shutil.copytree(root / "porous_cartesian" / "coarse", copied)
    fv_options = copied / "constant" / "fvOptions"
    fv_options.write_text(fv_options.read_text(encoding="utf-8").replace("betaField beta;", "betaField betaOther;"), encoding="utf-8")
    with pytest.raises(ValueError, match="betaField"):
        _verify_porous_case_semantics(copied)


def test_executed_sequence_stops_before_later_grids_after_phase_failure(
    compiled: tuple[Path, dict], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = compiled

    def fail_first(*args: object, **kwargs: object) -> dict:
        return {"ok": False, "phase_a": {"status": "failed"}, "phase_b": {"status": "planned"}}

    monkeypatch.setattr(cylinder_module, "_run_cylinder_case_two_phase", fail_first)
    artifact = run_g4_b2_cylinder_cases(
        compilation_dir=root, output_dir=tmp_path / "failed", backend="docker", execute=True,
        through_grid="fine",
        docker_image="opencfd/openfoam-default:2512@sha256:" + "a" * 64,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_failed"
    assert payload["stopped_by"] == "runtime_failure"
    assert payload["requested_through_grid"] == "fine"
    assert payload["executed_through_grid"] == "coarse"
    assert [(item["grid_id"], item["representation"]) for item in payload["cases"]] == [("coarse", "body_fitted")]


def _write_phase_final_fields(case: Path, *, phase: str, time_name: str) -> None:
    (case / ("runtime_phase_a_final_time.txt" if phase == "phase_a" else "runtime_phase_b_final_time.txt")).write_text(
        time_name + "\n", encoding="utf-8"
    )
    final = case / time_name
    final.mkdir(exist_ok=True)
    (final / "U").write_text("U\n", encoding="utf-8")
    (final / "p").write_text("p\n", encoding="utf-8")


def test_phase_a_accepts_emitted_camel_case_log_and_hashes_it(
    compiled: tuple[Path, dict], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = compiled
    import shutil

    case = tmp_path / "body_fitted"
    shutil.copytree(root / "body_fitted" / "coarse", case)

    def complete_phase_a(*args: object, **kwargs: object) -> SimpleNamespace:
        (case / "log.simpleFoam.phaseA").write_text(
            "  TRAPFPE : Floating   point exception trapping enabled ( FOAM_SIGFPE ) .  \n"
            "normal simpleFoam output\n",
            encoding="utf-8",
        )
        _write_phase_final_fields(case, phase="phase_a", time_name="1255")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cylinder_module.subprocess, "run", complete_phase_a)
    result = cylinder_module._run_docker_phase(
        case, phase="phase_a", representation="body_fitted", snapshot_dir=None,
        image="opencfd/openfoam-default:2512@sha256:" + "a" * 64,
        timeout_seconds=1, case_relpath=Path("cases/body_fitted/coarse"),
    )

    assert result["ok"] is True
    assert result["solver_log_relpath"] == "cases/body_fitted/coarse/log.simpleFoam.phaseA"
    assert result["solver_log_sha256"] == hashlib.sha256((case / "log.simpleFoam.phaseA").read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("log", "fatal"),
    [
        ("trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\n", False),
        (
            "trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\n"
            "Floating point exception (8)\n",
            True,
        ),
        ("Floating point exception (core dumped)\n", True),
        ("FOAM FATAL ERROR:\n", True),
        ("Segmentation fault (core dumped)\n", True),
        ("FOAM_SIGFPE signal received\n", True),
        ("MPI_ABORT was invoked\n", True),
    ],
)
def test_solver_log_fatal_classifier_is_line_aware_for_trap_fpe_banner(
    tmp_path: Path, log: str, fatal: bool,
) -> None:
    solver_log = tmp_path / "log.simpleFoam.phaseA"
    solver_log.write_text(log, encoding="utf-8")

    assert cylinder_module._solver_log_has_fatal(solver_log) is fatal


def test_missing_phase_a_log_fails_and_never_starts_phase_b(
    compiled: tuple[Path, dict], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = compiled
    import shutil

    case = tmp_path / "body_fitted"
    shutil.copytree(root / "body_fitted" / "coarse", case)
    calls: list[str] = []

    def complete_without_log(command: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        script = command[-1]
        calls.append(script)
        assert "log.simpleFoam.phaseA" in script
        assert "log.simpleFoam.phaseB" not in script
        _write_phase_final_fields(case, phase="phase_a", time_name="1255")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cylinder_module.subprocess, "run", complete_without_log)
    result = cylinder_module._run_cylinder_case_two_phase(
        case, representation="body_fitted", grid_id="coarse", snapshot_dir=None,
        case_relpath=Path("cases/body_fitted/coarse"), execute=True,
        docker_image="opencfd/openfoam-default:2512@sha256:" + "a" * 64,
    )

    assert result["ok"] is False
    assert result["phase_a"]["solver_log_relpath"] == "cases/body_fitted/coarse/log.simpleFoam.phaseA"
    assert result["phase_a"]["solver_log_sha256"] is None
    assert result["phase_b"]["status"] == "planned"
    assert len(calls) == 1


def test_porous_extension_load_assertions_read_only_phase_b_log(
    compiled: tuple[Path, dict], tmp_path: Path,
) -> None:
    root, _ = compiled
    import shutil

    case = tmp_path / "porous"
    shutil.copytree(root / "porous_cartesian" / "coarse", case)
    phase_b_log = case / "log.simpleFoam.phaseB"
    phase_b_log.write_text("Selecting fvOption cfdSdfLinearBrinkman porousCylinderResistance\n", encoding="utf-8")
    (case / "log.simpleFoam").write_text("decoy log without extension identity\n", encoding="utf-8")
    resistance = case / "1455" / "brinkmanResistance"
    resistance.parent.mkdir()
    resistance.write_text("field\n", encoding="utf-8")

    contract = cylinder_module._extension_runtime_contract(
        case, snapshot_dir=None, rel="cases/porous_cartesian/coarse",
        image="opencfd/openfoam-default:2512@sha256:" + "a" * 64,
        phase_a={"canonical_container_command": ["phase-a"]}, phase_b={"final_time": "1455"},
    )

    runtime = contract["runtime_load"]
    assert runtime["solver_log_sha256"] == hashlib.sha256(phase_b_log.read_bytes()).hexdigest()
    assert all(runtime["load_log_assertions"].values())


@pytest.mark.parametrize(
    ("through_grid", "expected_ids"),
    [
        ("coarse", ["body_fitted/coarse", "porous_cartesian/coarse"]),
        ("medium", ["body_fitted/coarse", "porous_cartesian/coarse", "body_fitted/medium", "porous_cartesian/medium"]),
        ("fine", ["body_fitted/coarse", "porous_cartesian/coarse", "body_fitted/medium", "porous_cartesian/medium", "body_fitted/fine", "porous_cartesian/fine"]),
    ],
)
def test_dry_run_writes_only_requested_canonical_prefix(
    compiled: tuple[Path, dict], tmp_path: Path, through_grid: str, expected_ids: list[str],
) -> None:
    root, _ = compiled
    artifact = run_g4_b2_cylinder_cases(
        compilation_dir=root, output_dir=tmp_path / through_grid, through_grid=through_grid,
        backend="docker", execute=False,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "contract_only_not_executed"
    assert payload["requested_through_grid"] == through_grid
    assert payload["executed_through_grid"] == through_grid
    assert payload["stopped_by"] == "requested_grid"
    assert payload["ordered_executed_case_ids"] == expected_ids
    assert payload["canonical_case_ids"][-2:] == ["body_fitted/fine", "porous_cartesian/fine"]


def test_complete_executed_prefix_is_unqualified_until_force_cp_evaluation(
    compiled: tuple[Path, dict], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = compiled

    def succeed(*args: object, **kwargs: object) -> dict:
        return {"ok": True, "phase_a": {"status": "completed"}, "phase_b": {"status": "completed"}}

    monkeypatch.setattr(cylinder_module, "_run_cylinder_case_two_phase", succeed)
    artifact = run_g4_b2_cylinder_cases(
        compilation_dir=root, output_dir=tmp_path / "coarse-success", through_grid="coarse",
        backend="docker", execute=True, docker_image="opencfd/openfoam-default:2512@sha256:" + "a" * 64,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "partial_runtime_completed_unqualified"
    assert payload["qualified"] is False
    assert payload["stopped_by"] == "requested_grid"
    assert payload["next_required_condition"] == "run a new --through-grid fine prefix"
    assert payload["force_cp_evaluation"]["evaluated"] is False


def test_cli_requires_through_grid_for_cylinder_run(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run-g4-b2-cylinder", str(tmp_path / "input"), str(tmp_path / "output")])

    assert result.exit_code != 0
    assert "--through-grid" in result.output


def test_cli_compiles_source_snapshot_without_runtime_claim(tmp_path: Path) -> None:
    output = tmp_path / "cli"
    result = runner.invoke(app, ["compile-g4-b2-cylinder", str(output), "--spec", str(SPEC)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "compiled_not_runtime_qualified"
    assert (output / G4_B2_CYLINDER_EXTENSION_SOURCE_MANIFEST_FILENAME).is_file()
