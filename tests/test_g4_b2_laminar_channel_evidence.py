from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfd_sdf.g4_b2_laminar_channel import compile_g4_b2_channel_benchmark
from cfd_sdf.g4_b2_laminar_channel_evidence import (
    _compare_postprocess_coordinates,
    evaluate_g4_b2_channel_runtime_evidence,
    extract_g4_b2_channel_runtime_evidence,
    write_g4_b2_channel_runtime_evidence,
)


SPEC = Path("examples/g4_b2_laminar/channel.yaml")
IMAGE = "opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"


def _field(name: str, values: list[str], kind: str) -> str:
    field_class, dimensions = {
        "U": ("volVectorField", "[0 1 -1 0 0 0 0]"),
        "p": ("volScalarField", "[0 2 -2 0 0 0 0]"),
        "phi": ("surfaceScalarField", "[0 3 -1 0 0 0 0]"),
    }[name]
    return (
        f"FoamFile\n{{\n    version 2.0;\n    format ascii;\n    class {field_class};\n    object {name};\n}}\n\n"
        + f"dimensions      {dimensions};\n\ninternalField   nonuniform List<"
        + ("vector" if kind == "vector" else "scalar")
        + f">\n{len(values)}\n(\n"
        + "\n".join(values)
        + "\n)\n;\n"
    )


def _block_mesh_log(*, nx: int, ny: int, nz: int, length: float, half_height: float, span: float) -> str:
    return (
        "Block 0 cell size :\n"
        f"    i : {length / nx:.17g} .. {length / nx:.17g}\n"
        f"    j : {2.0 * half_height / ny:.17g} .. {2.0 * half_height / ny:.17g}\n"
        f"    k : {span / nz:.17g} .. {span / nz:.17g}\n"
        "Mesh Information\n"
        f"  boundingBox: (0 {-half_height:.17g} 0) ({length:.17g} {half_height:.17g} {span:.17g})\n"
        f"  nCells: {nx * ny * nz}\n"
        "End\n"
    )


def _runtime(tmp_path: Path) -> tuple[Path, Path]:
    compiled = compile_g4_b2_channel_benchmark(spec_path=SPEC, output_dir=tmp_path / "compiled")
    index = json.loads(compiled.index_path.read_text(encoding="utf-8"))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    # v4 must name and bind the retained v2 source records, but never trusts
    # their content as qualification metrics.
    for name in ("channel_evidence_v2_20260804.json", "channel_qualification_v2_20260804.json"):
        (tmp_path / name).write_text(json.dumps({"kind": "superseded_v2", "name": name}), encoding="utf-8")
    attempted_cases = []
    gradient = index["analytic_solution"]["negative_dp_dx_pa_per_m"]
    rho = index["physics"]["density_kg_m3"]
    length = index["geometry"]["length_m"]
    height = index["geometry"]["half_height_m"]
    bulk = index["physics"]["bulk_velocity_mps"]
    # The cell-centre bulk quadrature adds its own O(h^2) term.  Keep the
    # manufactured solver error below the fine-grid 0.5% bulk criterion while
    # retaining a resolvable h/h2/h4 series.
    errors = {"coarse": 0.072, "medium": 0.018, "fine": 0.0045}
    for case in index["cases"]:
        grid_id = case["grid_id"]
        source, target = compiled.root / grid_id, runtime / "cases" / grid_id
        target.parent.mkdir(parents=True, exist_ok=True)
        # The compiled dictionary files are copied exactly, preserving their
        # compiler-owned hashes.  Runtime mesh/fields are written separately.
        import shutil
        shutil.copytree(source, target)
        nx, ny, nz = case["cells"]
        assert nz == 1
        error = errors[grid_id]
        u_rows: list[str] = []
        p_rows: list[str] = []
        for j in range(ny):
            y = -height + (j + 0.5) * 2.0 * height / ny
            u = 1.5 * bulk * (1.0 - (y / height) ** 2) * (1.0 + error)
            for i in range(nx):
                x = (i + 0.5) * length / nx
                u_rows.append(f"({u:.17g} 0 0)")
                p_rows.append(f"{((length - x) * gradient * (1.0 + error) / rho):.17g}")
        final = target / "2000"
        final.mkdir()
        (final / "U").write_text(_field("U", u_rows, "vector"), encoding="utf-8")
        (final / "p").write_text(_field("p", p_rows, "scalar"), encoding="utf-8")
        (final / "phi").write_text(_field("phi", ["0"] * (nx * ny), "scalar"), encoding="utf-8")
        mesh = target / "constant" / "polyMesh"
        mesh.mkdir(parents=True)
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            (mesh / name).write_text("synthetic mesh binding\n", encoding="utf-8")
        log: list[str] = []
        for time in range(1901, 2001):
            log.extend([
                f"Time = {time}",
                "smoothSolver: Solving for Ux, Initial residual = 1e-11, Final residual = 1e-12, No Iterations 1",
                "smoothSolver: Solving for Uy, Initial residual = 1e-11, Final residual = 1e-12, No Iterations 1",
                "DICPCG: Solving for p, Initial residual = 1e-11, Final residual = 1e-12, No Iterations 1",
                "time step continuity errors : sum local = 1e-12, global = 1e-12, cumulative = 1e-10",
            ])
        log.append("End")
        (target / "log.simpleFoam").write_text("\n".join(log) + "\n", encoding="utf-8")
        (target / "log.blockMesh").write_text(
            _block_mesh_log(nx=nx, ny=ny, nz=nz, length=length, half_height=height, span=index["geometry"]["span_m"]),
            encoding="utf-8",
        )
        (target / "log.runOpenFOAM.stdout").write_text("", encoding="utf-8")
        (target / "log.runOpenFOAM.stderr").write_text("", encoding="utf-8")
        attempted_cases.append({
            "grid_id": grid_id, "case_sha256": case["case_sha256"], "case_contract_sha256": case["case_contract_sha256"],
            "status": "runtime_completed_metrics_not_extracted",
            "run": {"backend": "docker", "dry_run": False, "returncode": 0, "timed_out": False, "error": None,
                    "solver_error_logs": [], "ok": True,
                    "command_executed": ["docker", "run", "type=bind,source=.tmp-synthetic,target=/case", IMAGE, "-lc", "./Allrun"],
                    "command_executed_sha256": "a" * 64,
                    "published_case_relpath": f"cases/{grid_id}",
                    "stdout_relpath": f"cases/{grid_id}/log.runOpenFOAM.stdout",
                    "stderr_relpath": f"cases/{grid_id}/log.runOpenFOAM.stderr",
                    "summary_relpath": f"cases/{grid_id}/openfoam_run_summary.json",
                    "replay_command": ["docker", "run", f"type=bind,source=cases/{grid_id},target=/case", IMAGE, "-lc", "./Allrun"]},
        })
    (runtime / "g4_b2_channel_runtime_attempt.json").write_text(json.dumps({
        "schema_version": 1, "kind": "g4_b2_channel_runtime_attempt", "compilation_sha256": index["compilation_sha256"],
        "spec_sha256": index["spec_sha256"], "execute_requested": True, "status": "runtime_completed_metrics_not_extracted", "cases": attempted_cases,
    }), encoding="utf-8")
    return compiled.root, runtime


def test_direct_extractor_binds_runtime_fields_and_internal_qualification(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compilation, runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        "cfd_sdf.g4_b2_laminar_channel_evidence._postprocess_check",
        lambda *_args, **_kwargs: {"status": "verified", "backend": "synthetic"},
    )

    evidence = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)

    assert evidence["schema_version"] == 4
    assert evidence["status"] == "complete"
    assert evidence["decision_records"] == [
        "docs/decisions/2026-08-04-g4-b2-laminar-scope.md",
        "docs/decisions/2026-08-04-g4-b2-channel-evidence-extraction.md",
    ]
    assert [record["relative_path"] for record in evidence["source_artifacts"]] == [
        "channel_evidence_v2_20260804.json", "channel_qualification_v2_20260804.json",
    ]
    assert evidence["canonical_commands"]["direct_parser"]["argv"][0:2] == ["cfd-sdf", "extract-g4-b2-channel-evidence"]
    assert evidence["binding"]["runtime_attempt"]["sha256"]
    fine = evidence["cases"]["fine"]
    assert fine["case"]["mesh_layout"]["ordering"] == "x_fastest_then_y_then_z"
    assert len(fine["values"]["profile"]["y_m"]) == 80
    assert fine["values"]["bulk_velocity"]["value_mps"] == pytest.approx(0.015 * (1.0 + 0.0045) * (1.0 + 1.0 / (2.0 * 80**2)))
    assert fine["values"]["pressure_gradient"]["negative_dp_dx_pa_per_m"] == pytest.approx(0.00826875 * 1.0045)
    assert fine["runtime"]["stationarity"]["status"] == "passed"
    assert fine["runtime"]["mesh_check"]["status"] == "verified"
    assert fine["runtime"]["mesh_check"]["observed"]["n_cells"] == 19200
    qualification = evaluate_g4_b2_channel_runtime_evidence(compilation_dir=compilation, evidence=evidence)
    assert qualification["status"] == "passed"
    assert qualification["decision_records"] == evidence["decision_records"]
    assert qualification["source_artifacts"] == evidence["source_artifacts"]
    legacy_runtime = qualification["cases"]["fine"]["runtime"]
    assert legacy_runtime["command"] == fine["runtime"]["run"]["replay_command"]
    assert legacy_runtime["solver_log_sha256"] == fine["runtime"]["log_sha256"]["log.simpleFoam"]["sha256"]
    assert legacy_runtime["solver_log_sha256"] != "a" * 64
    destination = write_g4_b2_channel_runtime_evidence(evidence, tmp_path / "evidence.json")
    assert json.loads(destination.read_text(encoding="utf-8"))["complete"] is True


def test_postprocess_not_verified_cannot_qualify(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compilation, runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        "cfd_sdf.g4_b2_laminar_channel_evidence._postprocess_check",
        lambda *_args, **_kwargs: {"status": "unavailable", "reason": "test"},
    )

    evidence = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)
    qualification = evaluate_g4_b2_channel_runtime_evidence(compilation_dir=compilation, evidence=evidence)

    assert evidence["status"] == "inconclusive"
    assert "fine:postprocess_independent_check_not_verified" in evidence["reasons"]
    assert qualification["status"] == "inconclusive"
    assert qualification["qualified"] is False


def test_runtime_attempt_hash_mismatch_is_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compilation, runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        "cfd_sdf.g4_b2_laminar_channel_evidence._postprocess_check",
        lambda *_args, **_kwargs: {"status": "verified"},
    )
    attempt = runtime / "g4_b2_channel_runtime_attempt.json"
    raw = json.loads(attempt.read_text(encoding="utf-8"))
    raw["compilation_sha256"] = "0" * 64
    attempt.write_text(json.dumps(raw), encoding="utf-8")

    evidence = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)

    assert evidence["status"] == "inconclusive"
    assert "runtime_attempt_compilation_binding_mismatch" in evidence["reasons"]


def test_public_evidence_is_canonical_and_has_no_transient_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compilation, runtime = _runtime(tmp_path)

    def _verified(_case: Path, _direct: object, **kwargs: object) -> dict[str, object]:
        locator = str(kwargs["published_case_locator"])
        return {
            "status": "verified", "backend": "docker", "container_image": IMAGE,
            "case_locator": locator, "command_cwd_locator": "runtime_bundle_root",
            "command": ["docker", "run", f"type=bind,source={locator},target=/case", IMAGE],
        }

    monkeypatch.setattr("cfd_sdf.g4_b2_laminar_channel_evidence._postprocess_check", _verified)
    first = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)
    second = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)

    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(second, sort_keys=True, separators=(",", ":"))
    assert ".tmp-" not in json.dumps(first, sort_keys=True)
    fine = first["cases"]["fine"]
    assert fine["postprocess"]["case_locator"] == "cases/fine"
    assert any("source=cases/fine," in item for item in fine["postprocess"]["command"])


def test_blockmesh_contract_mismatch_is_inconclusive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compilation, runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        "cfd_sdf.g4_b2_laminar_channel_evidence._postprocess_check",
        lambda *_args, **_kwargs: {"status": "verified"},
    )
    log = runtime / "cases" / "fine" / "log.blockMesh"
    log.write_text(log.read_text(encoding="utf-8").replace("nCells: 19200", "nCells: 19199"), encoding="utf-8")

    evidence = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)
    qualification = evaluate_g4_b2_channel_runtime_evidence(compilation_dir=compilation, evidence=evidence)

    assert evidence["status"] == "inconclusive"
    assert "fine:blockmesh_ncells_mismatch" in evidence["reasons"]
    assert evidence["cases"]["fine"]["runtime"]["mesh_check"]["status"] == "inconclusive"
    assert qualification["status"] == "inconclusive"


def test_final_field_header_dimension_mismatch_is_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    compilation, runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        "cfd_sdf.g4_b2_laminar_channel_evidence._postprocess_check",
        lambda *_args, **_kwargs: {"status": "verified"},
    )
    path = runtime / "cases" / "fine" / "2000" / "p"
    path.write_text(path.read_text(encoding="utf-8").replace("dimensions      [0 2 -2 0 0 0 0];", "dimensions      [0 1 -1 0 0 0 0];"), encoding="utf-8")

    evidence = extract_g4_b2_channel_runtime_evidence(compilation_dir=compilation, runtime_dir=runtime)

    assert evidence["status"] == "inconclusive"
    assert "fine:final_field_header_dimensions_mismatch:p" in evidence["reasons"]
    assert evidence["cases"]["fine"]["case"]["final_field_headers"]["p"]["expected"]["dimensions"] == "[0 2 -2 0 0 0 0]"


def test_coordinate_crosscheck_rejects_non_x_fastest_or_sampling_contract() -> None:
    contract = {
        "ordering": "x_fastest_then_y_then_z",
        "cell_count": 4,
        "x_cell_centres_m": [0.01, 0.03],
        "y_cell_centres_m": [-0.005, 0.005],
        "z_cell_centres_m": [0.0005],
        "profile_sampling": {"x_m": 0.03, "cell_indices": [0, 1], "cell_centres_m": [0.01, 0.03], "right_weight": 0.5},
        "pressure_sampling": {"x_m": [0.015, 0.045], "cell_indices": [[0, 1], [0, 1]], "cell_centres_m": [[0.01, 0.03], [0.01, 0.03]], "right_weight": [0.5, 0.5]},
    }
    centres = [(0.01, -0.005, 0.0005), (0.03, -0.005, 0.0005), (0.01, 0.005, 0.0005), (0.03, 0.005, 0.0005)]

    assert _compare_postprocess_coordinates(centres, contract)["status"] == "verified"
    swapped = [centres[1], centres[0], *centres[2:]]
    assert _compare_postprocess_coordinates(swapped, contract)["reason"] == "postprocess_cell_centres_x_fastest_order_or_location_mismatch"
    contract["pressure_sampling"]["x_m"] = [0.014, 0.045]
    assert _compare_postprocess_coordinates(centres, contract)["reason"] == "direct_coordinate_sampling_locations_mismatch"
