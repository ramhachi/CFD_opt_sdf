import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts/verify_kaggle_w3_v16_cuda_diagnostic.py"
spec = importlib.util.spec_from_file_location("w3_cuda_diagnostic_host", VERIFY_PATH)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def lattice_rows():
    rows = []
    for i, x in ((1, 0.5), (2, 1.5)):
        candidate = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0] if i == 1 else [0.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        ground = [0.5, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        combined = candidate if i == 1 else ground
        rows.append([i, 1, 1, x, 0.5, 0.5,
                     *candidate, *candidate, *ground, *ground, *combined, *combined,
                     *combined[:1], *combined[:1], 0.5, 0.5])
    return rows


def write_lattice(path: Path):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(host.expected_header())
        writer.writerows(lattice_rows())


def test_flow_lattice_csv_layout_and_ground_contract(tmp_path):
    path = tmp_path / "lattice.csv"
    write_lattice(path)

    result = host.read_lattice_csv(path, (2, 1, 1))

    assert result["row_count"] == 2
    assert result["candidate_cpu"][:, 0].tolist() == [0.0, 0.5]
    assert result["ground_cpu"][:, 0].tolist() == [0.5, 0.5]
    assert result["combined_cpu"][:, 0].tolist() == [0.0, 0.5]
    assert result["ground_cpu"][:, 3].tolist() == [1.0, 1.0]
    assert result["ground_cpu"][:, 4].tolist() == [1.0, 1.0]
    assert len(host.expected_header()) == 52


def test_numpy_reference_recomputes_candidate_distance_and_normal(tmp_path):
    lattice_path = tmp_path / "lattice.csv"
    write_lattice(lattice_path)
    lattice = host.read_lattice_csv(lattice_path, (2, 1, 1))
    x = (np.arange(5, dtype=np.float32) * np.float32(0.025) - np.float32(0.0125))
    phi = np.broadcast_to(x[:, None, None], (5, 3, 3)).copy()
    geometry = {"canonical_sdf_origin_m": [0.0, 0.0, 0.0], "spacing_m": 0.05}
    profile = {"flow_origin_m": [0.0, 0.0, 0.0]}

    result = host.host_candidate_reference(phi, lattice, geometry, profile)

    assert np.allclose(result["distance_solver"], [0.0, 0.5], atol=1e-6)
    assert np.allclose(result["normal"], [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], atol=1e-6)
    assert result["host_cpu_max_abs_distance_error_m"] == pytest.approx(0.0, abs=1e-7)


def test_force_snapshot_checks_component_closure_and_projection():
    snapshot = {
        "waterlily_pressure_force_raw": [-2.0, 0.5, 3.0],
        "waterlily_viscous_force_raw": [-1.0, -0.5, 1.0],
        "waterlily_total_force_raw": [-3.0, 0.0, 4.0],
        "registered_drag_plus_fx_from_raw": 3.0,
        "registered_downforce_minus_fz_from_raw": 4.0,
    }

    result = host.verify_force_snapshot(snapshot)

    assert result["pressure_plus_viscous_componentwise_residual"] == [0.0, 0.0, 0.0]
    assert result["repository_drag_plus_fx"] == 3.0
    assert result["repository_downforce_minus_fz"] == 4.0

    snapshot["waterlily_total_force_raw"] = [-4.0, 0.0, 4.0]
    with pytest.raises(ValueError, match="does not exactly close"):
        host.verify_force_snapshot(snapshot)


def test_w2b_sign_precedent_is_audited_without_extending_its_claim():
    audit = host.audit_w2b_drag_sign_precedent()

    assert audit["registered_T4_drag_sign_gate"] is True
    assert all(value > 0 for value in audit["time_weighted_drag_solver_units_by_cells_per_diameter"].values())
    assert "no v16 target" in audit["interpretation"]


def test_error_bundle_can_be_verified_as_diagnostic_only(tmp_path):
    output = tmp_path / "w3_v16_cuda_diagnostic"
    output.mkdir()
    (output / "ERROR.txt").write_text("CUDA diagnostic stage failed\n")
    payload_sha = hashlib.sha256((output / "ERROR.txt").read_bytes()).hexdigest()
    (output / "sha256.json").write_text(json.dumps({"ERROR.txt": payload_sha}))

    manifest, manifest_sha, status = host.verify_output_files(output)

    assert manifest == {"ERROR.txt": payload_sha}
    assert len(manifest_sha) == 64
    assert status == "ERROR"


def test_error_classification_uses_julia_exception_after_last_checkpoint(tmp_path):
    (tmp_path / "ERROR.txt").write_text("Julia job failed\n")
    (tmp_path / "w3_cuda_diagnostic.log").write_text(
        "ERROR: LoadError: UndefVarError: `f` not defined in `Main`\n"
        " [1] v16_representative_probes(grid::GridSDF)\n")

    result = host.classify_failure(
        tmp_path, {"last_completed_stage": "input_and_device_identity"}, None)

    assert result["last_completed_stage"] == "input_and_device_identity"
    assert result["failed_stage"] == "representative_probe_definitions"
    assert result["failure_class"] == "julia_diagnostic_probe_fixture_bug"
    assert result["solver_started"] is False
    assert "UndefVarError" in result["exact_exception"]
