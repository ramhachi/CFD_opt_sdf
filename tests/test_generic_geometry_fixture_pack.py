from __future__ import annotations

import hashlib
import json
from pathlib import Path

import trimesh
from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.generic_geometry_fixture_pack import (
    GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_KIND,
    run_generic_geometry_fixture_pack,
)


FIXTURE_ROOT = Path("examples/g4_b0_generic_geometry_fixtures")
CLI_RUNNER = CliRunner()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_pack_publishes_only_valid_hash_bound_results(tmp_path: Path) -> None:
    result = run_generic_geometry_fixture_pack(output_dir=tmp_path / "result", chunk_size=97)
    index = _read(result.index_path)

    assert index["kind"] == GENERIC_GEOMETRY_FIXTURE_RESULT_INDEX_KIND
    assert index["fixture_order"] == ["sphere", "box", "plate", "multi_component", "invalid_stl"]
    assert [record["status"] for record in index["results"]] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "rejected",
    ]
    assert not (result.index_path.parent / "invalid_stl").exists()

    for record in index["results"][:4]:
        assert len(record["input_sha256"]) == 64
        assert len(record["result_identity"]) == 64
        fixture_dir = result.index_path.parent / record["id"]
        fixture_result = _read(fixture_dir / "fixture_result.json")
        role_report = _read(fixture_dir / "problem_spec_validation.json")
        manifest = _read(fixture_dir / "canonical_geometry_mask_manifest.json")
        assert fixture_result["result_identity"] == record["result_identity"]
        assert role_report["kind"] == "problem_spec_validation"
        assert role_report["geometry_role_counts"] == {
            "design_domain": 1,
            "fixed_solid": 1,
            "forbidden_region": 1,
            "initial_design": 1,
            "root": 1,
        }
        assert manifest["canonical_grid_snapshot"]["sha256"] == hashlib.sha256(
            (fixture_dir / "canonical_grid_snapshot.json").read_bytes()
        ).hexdigest()

    rejected = index["results"][-1]
    assert rejected["result_identity"] is None
    assert "watertight" in rejected["reason"]


def test_fixture_pack_replay_and_result_order_are_deterministic(tmp_path: Path) -> None:
    first = run_generic_geometry_fixture_pack(output_dir=tmp_path / "first", chunk_size=71)
    second = run_generic_geometry_fixture_pack(output_dir=tmp_path / "second", chunk_size=113)

    assert first.index_path.read_bytes() == second.index_path.read_bytes()
    assert [record["id"] for record in first.records] == [
        "sphere",
        "box",
        "plate",
        "multi_component",
        "invalid_stl",
    ]


def test_plate_and_multi_component_assets_are_physical_closed_solids() -> None:
    plate = trimesh.load_mesh(FIXTURE_ROOT / "plate" / "geometry" / "initial_surface.stl", process=True)
    multi = trimesh.load_mesh(
        FIXTURE_ROOT / "multi_component" / "geometry" / "initial_surface.stl", process=True
    )

    assert plate.is_watertight
    assert plate.is_volume
    assert plate.volume > 0.0
    assert 0.0 < plate.extents[2] < min(plate.extents[0], plate.extents[1])
    assert multi.is_watertight
    assert multi.is_volume
    assert len(multi.split(only_watertight=False)) == 2


def test_fixture_role_report_is_the_existing_generic_preflight_report(tmp_path: Path) -> None:
    result = run_generic_geometry_fixture_pack(output_dir=tmp_path / "result")
    fixture_report = _read(result.index_path.parent / "sphere" / "problem_spec_validation.json")
    cli_result = CLI_RUNNER.invoke(
        app,
        ["validate-problem-spec", str(FIXTURE_ROOT / "sphere" / "project.yaml")],
    )

    assert cli_result.exit_code == 0, cli_result.output
    assert fixture_report == json.loads(cli_result.output)
