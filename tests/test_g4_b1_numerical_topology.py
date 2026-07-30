from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.g4_b1_numerical_topology import (
    G4_B1_NUMERICAL_TOPOLOGY_FILENAME,
    run_g4_b1_numerical_topology_benchmark,
)


runner = CliRunner()


def test_canonical_b1_pack_binds_checker_outcomes_and_transform_derivatives(tmp_path: Path) -> None:
    result = run_g4_b1_numerical_topology_benchmark(output_dir=tmp_path / "b1")
    payload = json.loads(result.path.read_text(encoding="utf-8"))

    assert result.status == "success"
    assert payload["scope"] == "stl_independent_discrete_voxel_topology_and_filter_projection_derivative_only"
    assert payload["cell_order"] == "x-fastest"
    fixtures = {item["fixture_id"]: item for item in payload["fixtures"]}
    assert fixtures["unrooted_island"]["status"] == "rejected"
    assert "solid_component_without_root_nominal" in fixtures["unrooted_island"]["reasons"]
    for width in range(1, 5):
        item = fixtures[f"root_attached_bridge_{width}_cells"]
        assert item["status"] == "rejected"
        assert "minimum_solid_width" in item["reasons"]
    for width in (5, 6):
        item = fixtures[f"root_attached_bridge_{width}_cells"]
        assert item["status"] == "success"
        assert item["reasons"] == []
        assert item["checker"]["grid"]["spacing"] == [0.002, 0.002, 0.002]
        assert item["checker"]["policy"]["minimum_solid_width_m"] == 0.01
        assert len(item["checker_sha256"]) == 64
        active_mask = np.load(result.path.parent / item["array_files"]["active_mask"], allow_pickle=False)
        root_mask = np.load(result.path.parent / item["array_files"]["root_mask"], allow_pickle=False)
        assert not np.any(active_mask & root_mask)

    derivative = payload["transform_derivative"]
    assert derivative["h_1e-5_acceptance_passed"] is True
    assert derivative["error_improves_1e-4_to_1e-5"] is True
    assert derivative["inactive_entries_exact_zero"] is True
    assert derivative["direction_seed"] == 20_260_730
    assert derivative["direction_indices"] == [0, 1, 2]
    assert derivative["epsilon_ladder"] == [1.0e-4, 1.0e-5, 1.0e-6]

    active = np.load(result.path.parent / derivative["array_files"]["derivative_active_mask.npy"], allow_pickle=False)
    directions = np.load(result.path.parent / derivative["array_files"]["derivative_directions.npy"], allow_pickle=False)
    analytic = np.load(result.path.parent / derivative["array_files"]["derivative_analytic.npy"], allow_pickle=False)
    cellwise = np.load(result.path.parent / derivative["array_files"]["derivative_cellwise_fd.npy"], allow_pickle=False)
    assert np.all(directions[:, ~active] == 0.0)
    assert np.all(analytic[~active] == 0.0)
    assert np.all(cellwise[:, ~active] == 0.0)


def test_b1_replay_has_byte_identical_index_and_numerical_array_hashes(tmp_path: Path) -> None:
    first = run_g4_b1_numerical_topology_benchmark(output_dir=tmp_path / "first")
    second = run_g4_b1_numerical_topology_benchmark(output_dir=tmp_path / "second")
    assert first.path.read_bytes() == second.path.read_bytes()
    one = json.loads(first.path.read_text(encoding="utf-8"))
    two = json.loads(second.path.read_text(encoding="utf-8"))
    assert one["artifact_sha256"] == two["artifact_sha256"]
    for relative, expected_hash in one["artifact_sha256"].items():
        assert _sha256(first.path.parent / relative) == expected_hash
        assert _sha256(second.path.parent / relative) == expected_hash


def test_b1_cli_publishes_a_successful_immutable_index(tmp_path: Path) -> None:
    output = tmp_path / "cli-b1"
    result = runner.invoke(app, ["run-g4-b1-numerical-topology-benchmark", str(output)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert (output / G4_B1_NUMERICAL_TOPOLOGY_FILENAME).is_file()
    second = runner.invoke(app, ["run-g4-b1-numerical-topology-benchmark", str(output)])
    assert second.exit_code != 0
    assert "refusing to overwrite" in second.output


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
