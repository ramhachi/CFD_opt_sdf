from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

sys.path.append(str(Path(__file__).parent))
from test_localized_g2_fd_preparation import _prepared  # noqa: E402

from cfd_sdf.cli import app
from cfd_sdf.localized_g2_fd_response_gradient import (
    LOCALIZED_G2_FD_RESPONSE_GRADIENT_FILENAME,
    extract_localized_g2_fd_response_gradient,
)
from cfd_sdf.localized_g2_fd_runner import run_localized_g2_openfoam_fd_direction
from cfd_sdf.localized_alpha_reference_binding import load_and_verify_localized_alpha_reference_binding
from cfd_sdf.localized_design_state_manifest import read_localized_design_state_manifest


runner = CliRunner()


def test_extracts_explicit_raw_alpha_response_gradient_artifact(tmp_path: Path) -> None:
    prepared, inputs = _prepared(tmp_path)
    state = read_localized_design_state_manifest(inputs["bundle"] / "localized_design_state_manifest.json")
    gradient = np.arange(state.grid.cell_count, dtype=np.float64)
    run = _run_with_explicit_field_tree(prepared.path, tmp_path / "run", gradient)
    binding = load_and_verify_localized_alpha_reference_binding(inputs["binding"])
    contract = _write_contract(tmp_path, inputs["compiled"], binding.binding.cfd_grid_sha256, binding.binding.cfd_grid.cell_count)

    extracted = extract_localized_g2_fd_response_gradient(
        prepared.path, run.report_json, contract,
        flow_case_id="straight", response_id="drag", adjoint_name="dragAdjoint", output_dir=tmp_path / "extracted",
    )

    report = json.loads(extracted.report_json.read_text(encoding="utf-8"))
    assert report["status"] == "extracted"
    assert [item["label"] for item in report["primal_responses"]] == [
        "reference_001", "reference_002", "plus_h0.01", "plus_h0.0050000000000000001", "plus_h0.0025000000000000001",
    ]
    assert report["adjoint_gradient"]["variable"] == "raw_alpha"
    assert report["adjoint_gradient"]["meaning"] == "dJ=sum_i g_alpha[i]*d(alpha_i)"
    assert report["cfd_grid"]["cell_order"] == "x-fastest"
    assert np.array_equal(np.load(extracted.gradient_npy, allow_pickle=False), gradient)


def test_rejects_non_scalar_response_tampering_and_bad_decomposition_without_publish(tmp_path: Path) -> None:
    prepared, inputs = _prepared(tmp_path)
    state = read_localized_design_state_manifest(inputs["bundle"] / "localized_design_state_manifest.json")
    run = _run_with_explicit_field_tree(prepared.path, tmp_path / "run", np.ones(state.grid.cell_count, dtype=np.float64))
    binding = load_and_verify_localized_alpha_reference_binding(inputs["binding"])
    contract = _write_contract(tmp_path, inputs["compiled"], binding.binding.cfd_grid_sha256, binding.binding.cfd_grid.cell_count)
    data = json.loads(contract.read_text(encoding="utf-8"))
    data["primal_response"]["source"]["json_pointer"] = "/response"
    bad = tmp_path / "non_scalar.json"; bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one finite numeric scalar"):
        extract_localized_g2_fd_response_gradient(prepared.path, run.report_json, bad, flow_case_id="straight", response_id="drag", adjoint_name="dragAdjoint", output_dir=tmp_path / "must_not_publish")
    assert not (tmp_path / "must_not_publish").exists()

    data = json.loads(contract.read_text(encoding="utf-8"))
    data["adjoint_gradient"]["decomposition"] = {"kind": "single_case_canonical_x_fastest", "global_cell_order": "unknown"}
    bad = tmp_path / "bad_order.json"; bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="decomposition/global order"):
        extract_localized_g2_fd_response_gradient(prepared.path, run.report_json, bad, flow_case_id="straight", response_id="drag", adjoint_name="dragAdjoint", output_dir=tmp_path / "bad_order_out")
    assert not (tmp_path / "bad_order_out").exists()

    response = tmp_path / "run" / "primal" / "reference_001" / "post" / "1.0" / "response.json"
    response.write_text('{"response":{"value":999.0}}', encoding="utf-8")
    with pytest.raises(ValueError, match="output hash mismatch"):
        extract_localized_g2_fd_response_gradient(prepared.path, run.report_json, contract, flow_case_id="straight", response_id="drag", adjoint_name="dragAdjoint", output_dir=tmp_path / "tampered_out")
    assert not (tmp_path / "tampered_out").exists()


def test_cli_extracts_no_chain_rule(tmp_path: Path) -> None:
    prepared, inputs = _prepared(tmp_path)
    state = read_localized_design_state_manifest(inputs["bundle"] / "localized_design_state_manifest.json")
    run = _run_with_explicit_field_tree(prepared.path, tmp_path / "run", np.ones(state.grid.cell_count, dtype=np.float64))
    binding = load_and_verify_localized_alpha_reference_binding(inputs["binding"])
    contract = _write_contract(tmp_path, inputs["compiled"], binding.binding.cfd_grid_sha256, binding.binding.cfd_grid.cell_count)
    output = tmp_path / "cli"
    result = runner.invoke(app, ["extract-localized-g2-fd-response-gradient", str(prepared.path), str(run.report_json), str(contract), "straight", "drag", "dragAdjoint", str(output)])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["report_path"] == str(output / LOCALIZED_G2_FD_RESPONSE_GRADIENT_FILENAME)


def test_reconstructs_declared_processor_global_labels_in_canonical_order(tmp_path: Path) -> None:
    prepared, inputs = _prepared(tmp_path)
    state = read_localized_design_state_manifest(inputs["bundle"] / "localized_design_state_manifest.json")
    gradient = np.arange(state.grid.cell_count, dtype=np.float64)
    run = _run_with_explicit_field_tree(prepared.path, tmp_path / "run", gradient, processor_shards=True)
    binding = load_and_verify_localized_alpha_reference_binding(inputs["binding"])
    contract = _write_contract(tmp_path, inputs["compiled"], binding.binding.cfd_grid_sha256, binding.binding.cfd_grid.cell_count)
    data = json.loads(contract.read_text(encoding="utf-8"))
    data["adjoint_gradient"]["source"] = {"kind": "declared_processor_shards"}
    data["adjoint_gradient"]["decomposition"] = {
        "kind": "processor_global_labels", "global_cell_order": "x-fastest", "reconstruction": "scatter_by_explicit_global_labels",
        "processors": [
            {"label": "processor0", "gradient_source": {"relative_path_template": "post/{final_time}/processor0_gradient.npy", "format": "npy"}, "global_labels_source": {"relative_path_template": "post/{final_time}/processor0_labels.npy", "format": "npy"}},
            {"label": "processor1", "gradient_source": {"relative_path_template": "post/{final_time}/processor1_gradient.npy", "format": "npy"}, "global_labels_source": {"relative_path_template": "post/{final_time}/processor1_labels.npy", "format": "npy"}},
        ],
    }
    contract.write_text(json.dumps(data), encoding="utf-8")
    extracted = extract_localized_g2_fd_response_gradient(prepared.path, run.report_json, contract, flow_case_id="straight", response_id="drag", adjoint_name="dragAdjoint", output_dir=tmp_path / "processor_extracted")
    assert np.array_equal(np.load(extracted.gradient_npy, allow_pickle=False), gradient)


def test_v2_coefficient_contract_converts_response_and_raw_alpha_gradient_to_newtons(tmp_path: Path) -> None:
    prepared, inputs = _prepared(tmp_path)
    state = read_localized_design_state_manifest(inputs["bundle"] / "localized_design_state_manifest.json")
    gradient = np.ones(state.grid.cell_count, dtype=np.float64)
    binding = load_and_verify_localized_alpha_reference_binding(inputs["binding"])
    contract = _write_contract(tmp_path, inputs["compiled"], binding.binding.cfd_grid_sha256, binding.binding.cfd_grid.cell_count)
    data = json.loads(contract.read_text(encoding="utf-8"))
    factor = 661.5
    scale = {
        "kind": "coefficient_to_force_N", "factor": factor,
        "conversion": "q_ref_times_area", "q_ref_pa": 551.25,
        "density_kg_m3": 1.225, "speed_mps": 30.0, "area_m2": 1.2,
    }
    data["schema_version"] = 2
    data["block_mesh_sha256"] = hashlib.sha256((inputs["compiled"] / "system" / "blockMeshDict").read_bytes()).hexdigest()
    data["compiler"] = {
        "compilation_metadata_sha256": data["compiler"]["compilation_metadata_sha256"],
        "serial_runtime_sha256": "a" * 64,
    }
    data["primal_response"]["scale"] = scale
    data["adjoint_gradient"]["scale"] = scale
    script = b"#!/bin/sh\nexit 0\n"
    proof = {
        "status": "proved", "block_mesh_sha256": data["block_mesh_sha256"],
        "grid_sha256": data["cfd_grid_sha256"], "cell_count": data["cfd_cell_count"],
        "cell_order": "x-fastest",
    }
    for case in (prepared.path / "cases").iterdir():
        (case / "AllrunAdjoint").write_bytes(script)
        proof_path = case / "localized_g2_cell_centre_ordering.json"
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
        runtime = {
            "schema_version": 1, "kind": "localized_g2_serial_runtime_contract", "status": "compiled",
            "flow_case_id": "straight", "response_id": "drag", "named_adjoint_id": "dragAdjoint",
            "compiler": {"compilation_metadata_sha256": data["compiler"]["compilation_metadata_sha256"]},
            "serial_execution": {"required": True, "decomposition": "forbidden"},
            "block_mesh": {
                "sha256": data["block_mesh_sha256"], "grid_sha256": data["cfd_grid_sha256"],
                "cell_count": data["cfd_cell_count"], "cell_order": "x-fastest",
            },
            "adjoint_script": {"path": "AllrunAdjoint", "sha256": hashlib.sha256(script).hexdigest()},
            "cell_centre_ordering_proof": {"path": proof_path.name, "sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest()},
        }
        runtime_path = case / "localized_g2_serial_runtime.json"
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        data["compiler"]["serial_runtime_sha256"] = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    contract.write_text(json.dumps(data), encoding="utf-8")
    run = _run_with_explicit_field_tree(prepared.path, tmp_path / "run", gradient)
    extracted = extract_localized_g2_fd_response_gradient(
        prepared.path, run.report_json, contract,
        flow_case_id="straight", response_id="drag", adjoint_name="dragAdjoint", output_dir=tmp_path / "converted",
    )
    report = json.loads(extracted.report_json.read_text(encoding="utf-8"))
    assert report["primal_responses"][0]["value"] == pytest.approx(10.0 * factor)
    assert np.array_equal(np.load(extracted.gradient_npy, allow_pickle=False), gradient * factor)


def _run_with_explicit_field_tree(prepared: Path, output: Path, gradient: np.ndarray, *, processor_shards: bool = False):
    def synthetic(**kwargs):
        case = kwargs["case_dir"]
        field_dir = case / "post" / "1.0"; field_dir.mkdir(parents=True, exist_ok=True)
        (field_dir / "response.json").write_text('{"response":{"value":10.0}}', encoding="utf-8")
        if kwargs["phase"] == "adjoint":
            np.save(field_dir / "gradient.npy", gradient)
            if processor_shards:
                even = np.arange(0, gradient.size, 2, dtype=np.int64)
                odd = np.arange(1, gradient.size, 2, dtype=np.int64)
                np.save(field_dir / "processor0_gradient.npy", gradient[odd])
                np.save(field_dir / "processor0_labels.npy", odd)
                np.save(field_dir / "processor1_gradient.npy", gradient[even])
                np.save(field_dir / "processor1_labels.npy", even)
        return {
            "ok": True, "command": ["synthetic", kwargs["label"]], "backend": "synthetic",
            "execution_identity": {"runner": "synthetic", "backend": "synthetic", "container_image": None, "openfoam_version": "synthetic"},
            "convergence": {"status": "converged"}, "final_time": 1.0,
            "response_provenance": {"flow_case_id": "straight", "response_id": "drag"},
        }
    return run_localized_g2_openfoam_fd_direction(prepared, output_dir=output, adjoint_name="dragAdjoint", execute=True, runner=synthetic)


def _write_contract(tmp_path: Path, compiled: Path, grid_sha256: str, count: int) -> Path:
    path = tmp_path / "compiler_response_gradient_contract.json"
    path.write_text(json.dumps({
        "schema_version": 1, "kind": "localized_g2_openfoam_response_gradient_contract", "status": "compiled",
        "flow_case_id": "straight", "response_id": "drag", "named_adjoint_id": "dragAdjoint",
        "compiler": {"compilation_metadata_sha256": hashlib.sha256((compiled / "openfoam_case_compilation.json").read_bytes()).hexdigest()},
        "cfd_grid_sha256": grid_sha256, "cfd_cell_count": count, "cell_order": "x-fastest",
        "primal_response": {
            "source": {"relative_path_template": "post/{final_time}/response.json", "format": "json", "json_pointer": "/response/value"},
            "units": "N", "scale": {"kind": "identity", "factor": 1.0, "conversion": "none"}, "final_time_selection": "recorded_attempt_final_time",
        },
        "adjoint_gradient": {
            "source": {"relative_path_template": "post/{final_time}/gradient.npy", "format": "npy"}, "variable": "raw_alpha",
            "meaning": "dJ=sum_i g_alpha[i]*d(alpha_i)", "units": "N", "scale": {"kind": "identity", "factor": 1.0, "conversion": "none"},
            "final_time_selection": "recorded_attempt_final_time", "decomposition": {"kind": "single_case_canonical_x_fastest", "global_cell_order": "x-fastest"},
        },
    }, sort_keys=True), encoding="utf-8")
    return path
