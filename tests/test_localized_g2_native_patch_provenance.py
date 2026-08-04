from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.localized_g2_native_patch_provenance import (
    LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_FILENAME,
    validate_localized_g2_native_patch_provenance,
)


def test_accepts_hash_bound_unqualified_native_patch_evidence(tmp_path: Path) -> None:
    case, contract, provenance = _native_patch_evidence(tmp_path)

    result = validate_localized_g2_native_patch_provenance(provenance, contract)

    assert result.provenance_json == provenance
    assert result.gradient_npy == case / "postProcessing/cfdSdfLocalizedG2/10/d_coefficient_d_raw_alpha.npy"
    assert result.flow_case_id == "straight"
    assert result.response_id == "drag"
    assert result.adjoint_name == "resp_drag"
    assert result.final_time == "10"
    assert result.cfd_cell_count == 4


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["native_build"]["container_image"].update({"digest": "sha256:" + "A" * 64}), "container image digest"),
        (lambda data: data["native_build"]["patch"].update({"sha256": "0" * 64}), "native patch hash mismatch"),
        (lambda data: data["response_binding"].update({"conversion": {"kind": "identity", "factor": 1.0, "conversion": "none"}}), "coefficient conversion"),
        (lambda data: data["emitted_gradient"].update({"field_name": "topOSensdrag"}), "dedicated d_coefficient"),
        (lambda data: data["legacy_field_substitution"].update({"topologySens": "allowed"}), "explicitly forbid legacy"),
    ],
)
def test_rejects_missing_or_tampered_native_patch_bindings(
    tmp_path: Path, mutate: object, message: str,
) -> None:
    _, contract, provenance = _native_patch_evidence(tmp_path)
    data = json.loads(provenance.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(data)
    provenance.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        validate_localized_g2_native_patch_provenance(provenance, contract)


def test_rejects_gradient_path_that_does_not_match_exact_final_time_contract(tmp_path: Path) -> None:
    _, contract, provenance = _native_patch_evidence(tmp_path)
    data = json.loads(provenance.read_text(encoding="utf-8"))
    data["emitted_gradient"]["relative_path"] = "postProcessing/cfdSdfLocalizedG2/9/d_coefficient_d_raw_alpha.npy"
    provenance.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="final-time source contract"):
        validate_localized_g2_native_patch_provenance(provenance, contract)


def test_rejects_tampered_strict_alpha_codec_or_hashed_response_value(tmp_path: Path) -> None:
    case, contract, provenance = _native_patch_evidence(tmp_path)
    alpha = case / "0.orig/alpha"
    alpha.write_text(alpha.read_text(encoding="utf-8").replace("0.25", "0.75", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="alpha case manifest/codec|source/adjoint alpha hashes"):
        validate_localized_g2_native_patch_provenance(provenance, contract)

    case, contract, provenance = _native_patch_evidence(tmp_path / "response")
    response = case / "postProcessing/cfdSdfLocalizedG2/10/response_coefficient.json"
    response.write_text('{"coefficient": 99.0}', encoding="utf-8")
    with pytest.raises(ValueError, match="native response file hash mismatch"):
        validate_localized_g2_native_patch_provenance(provenance, contract)


def _native_patch_evidence(tmp_path: Path) -> tuple[Path, Path, Path]:
    case = tmp_path / "case"
    case.mkdir(parents=True)
    contract = tmp_path / "localized_g2_response_gradient_contract.json"
    grid_sha = "1" * 64
    block_sha = "2" * 64
    runtime_sha = "3" * 64
    scale = {
        "kind": "coefficient_to_force_N", "factor": 6.0, "conversion": "q_ref_times_area",
        "q_ref_pa": 2.0, "density_kg_m3": 1.0, "speed_mps": 2.0, "area_m2": 3.0,
    }
    _write_json(contract, {
        "schema_version": 2, "kind": "localized_g2_openfoam_response_gradient_contract", "status": "compiled",
        "flow_case_id": "straight", "response_id": "drag", "named_adjoint_id": "resp_drag",
        "compiler": {"compilation_metadata_sha256": "4" * 64, "serial_runtime_sha256": runtime_sha},
        "cfd_grid_sha256": grid_sha, "cfd_cell_count": 4, "cell_order": "x-fastest", "block_mesh_sha256": block_sha,
        "primal_response": {
            "source": {"relative_path_template": "postProcessing/cfdSdfLocalizedG2/{final_time}/response_coefficient.json", "format": "json", "json_pointer": "/coefficient"},
            "units": "N", "scale": scale, "final_time_selection": "recorded_attempt_final_time",
        },
        "adjoint_gradient": {
            "source": {"relative_path_template": "postProcessing/cfdSdfLocalizedG2/{final_time}/d_coefficient_d_raw_alpha.npy", "format": "npy"},
            "variable": "raw_alpha", "meaning": "dJ=sum_i g_alpha[i]*d(alpha_i)", "units": "N", "scale": scale,
            "final_time_selection": "recorded_attempt_final_time",
            "decomposition": {"kind": "single_case_canonical_x_fastest", "global_cell_order": "x-fastest"},
        },
    })
    proof = case / "localized_g2_cell_centre_ordering.json"
    _write_json(proof, {
        "schema_version": 1, "kind": "localized_g2_cell_centre_x_fastest_proof", "status": "proved",
        "block_mesh_sha256": block_sha, "grid_sha256": grid_sha, "cell_count": 4, "cell_order": "x-fastest",
    })
    for relative, contents in {
        "evidence/openfoam-v2512.tar": b"pinned source tree archive",
        "evidence/native.patch": b"native patch bytes",
        "evidence/build.log": b"wmake log",
        "lib/libstagedRawAlpha.so": b"ELF not executed by this test",
    }.items():
        target = case / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
    gradient = case / "postProcessing/cfdSdfLocalizedG2/10/d_coefficient_d_raw_alpha.npy"
    gradient.parent.mkdir(parents=True)
    values = np.array([0.5, -1.0, 0.0, 2.0], dtype=np.float64)
    np.save(gradient, values, allow_pickle=False)
    alpha_values = np.array([0.25, 0.5, 0.75, 1.0], dtype=np.float64)
    alpha_path = case / "0.orig/alpha"
    alpha_path.parent.mkdir()
    alpha_path.write_text(
        "FoamFile\n{\n    class volScalarField;\n    object alpha;\n}\n"
        "internalField nonuniform List<scalar>\n4\n(\n0.25\n0.5\n0.75\n1\n)\n;\n",
        encoding="utf-8",
    )
    alpha_binding_sha = "d" * 64
    alpha_value_sha = _sha256_array(alpha_values)
    alpha_manifest = case / "localized_openfoam_alpha_case.json"
    _write_json(alpha_manifest, {
        "schema_version": 1, "kind": "localized_openfoam_alpha_case", "status": "prepared",
        "alpha_source": {
            "path": "0.orig/alpha", "values_sha256": alpha_value_sha, "cell_count": 4,
            "cfd_grid_sha256": grid_sha, "cfd_cell_count": 4, "cell_order": "x-fastest",
            "binding_sha256": alpha_binding_sha,
        },
        "alpha_binding": {"binding_sha256": alpha_binding_sha, "cfd_grid_sha256": grid_sha, "cfd_cell_count": 4},
    })
    response = case / "postProcessing/cfdSdfLocalizedG2/10/response_coefficient.json"
    response.write_text('{"coefficient": 1.25}', encoding="utf-8")
    provenance = case / LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_FILENAME
    _write_json(provenance, {
        "schema_version": 1, "kind": "localized_g2_native_raw_alpha_patch_provenance", "status": "emitted_unqualified",
        "response_gradient_contract": {"sha256": _sha256_file(contract), "serial_runtime_sha256": runtime_sha},
        "native_build": {
            "openfoam_distribution": "OpenCFD", "openfoam_version": "v2512", "source_revision_sha1": "a" * 40,
            "source_tree_archive": _hash_ref(case, "evidence/openfoam-v2512.tar"),
            "container_image": {"reference": "openfoam/openfoam-v2512", "digest": "sha256:" + "b" * 64},
            "patch": _hash_ref(case, "evidence/native.patch"), "build_log": _hash_ref(case, "evidence/build.log"),
            "library": {**_hash_ref(case, "lib/libstagedRawAlpha.so"), "soname": "libstagedRawAlpha.so"},
        },
        "execution_binding": {
            "serial_execution": "required_non_decomposed", "block_mesh_sha256": block_sha,
            "cell_centre_ordering_proof": _hash_ref(case, proof.name),
        },
        "response_binding": {
            "flow_case_id": "straight", "response_id": "drag", "named_adjoint_id": "resp_drag", "final_time": "10",
            "native_coefficient_units": "1", "native_coefficient_value": 1.25,
            "converted_units": "N", "conversion": scale,
            "response_file": {**_hash_ref(case, "postProcessing/cfdSdfLocalizedG2/10/response_coefficient.json"), "json_pointer": "/coefficient"},
        },
        "alpha_grid_binding": {
            "alpha_case_manifest": _hash_ref(case, alpha_manifest.name),
            "source_alpha_values_sha256": alpha_value_sha, "adjoint_used_alpha_values_sha256": alpha_value_sha,
            "alpha_binding_sha256": alpha_binding_sha, "cfd_grid_sha256": grid_sha,
            "cfd_cell_count": 4, "cell_order": "x-fastest",
        },
        "emitted_gradient": {
            "field_name": "d_coefficient_d_raw_alpha", "variable": "raw_alpha",
            "meaning": "dJ=sum_i g_alpha[i]*d(alpha_i)",
            "chain_stage": "alpha->alphaTilda->beta->named_response_adjoint",
            "relative_path": "postProcessing/cfdSdfLocalizedG2/10/d_coefficient_d_raw_alpha.npy",
            "sha256": _sha256_file(gradient), "array_value_sha256": _sha256_array(values),
            "dtype": "float64", "shape": [4],
        },
        "legacy_field_substitution": {"topOSens": "forbidden", "topologySens": "forbidden"},
        "limitations": [
            "provenance_validation_does_not_prove_native_gradient_correctness",
            "directional_fd_qualification_remains_required",
            "legacy_topOSens_and_topologySens_are_not_substitutes",
        ],
    })
    return case, contract, provenance


def _hash_ref(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    return {"relative_path": relative, "sha256": _sha256_file(path)}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
