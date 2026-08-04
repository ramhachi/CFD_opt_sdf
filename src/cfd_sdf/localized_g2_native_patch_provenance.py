"""Fail-closed provenance checks for a future native localized-G2 patch.

The selected native path is a patch to a pinned OpenCFD v2512 solver/adjoint
tree.  This module intentionally contains no OpenFOAM API assumptions and no
claim that a field is mathematically correct.  It only verifies that an
already-emitted raw-``alpha`` coefficient gradient is bound to the exact
compiler contract, immutable build inputs, and serial mesh/alpha identities
required before the later extractor may consider it.

In particular, this is not a compatibility layer for ``topOSens`` or
``topologySens``.  Those legacy field names are rejected rather than being
given new provenance labels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

import numpy as np

from .localized_g2_fd_response_gradient import _read_contract
from .openfoam_alpha_codec import read_openfoam_alpha_field
from .openfoam_grid_transfer import CANONICAL_CELL_ORDER


LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_SCHEMA_VERSION = 1
LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_KIND = "localized_g2_native_raw_alpha_patch_provenance"
LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_FILENAME = "localized_g2_native_raw_alpha_patch_provenance.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_TIME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")


@dataclass(frozen=True)
class LocalizedG2NativePatchProvenance:
    """A provenance-bound, but deliberately unqualified, native field."""

    provenance_json: Path
    gradient_npy: Path
    flow_case_id: str
    response_id: str
    adjoint_name: str
    final_time: str
    cfd_cell_count: int

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["provenance_json"] = str(self.provenance_json)
        data["gradient_npy"] = str(self.gradient_npy)
        return data


def validate_localized_g2_native_patch_provenance(
    provenance_path: str | Path,
    response_gradient_contract_path: str | Path,
) -> LocalizedG2NativePatchProvenance:
    """Validate strict evidence for a future v2512 raw-alpha patch.

    The provenance file lives at the root of the serial runtime case.  All
    mutable build/evidence files it names must be case-relative and their
    file digests are recomputed.  ``status='emitted_unqualified'`` is
    intentionally *not* a proof of derivative correctness;
    directional FD qualification remains a separate later step.
    """

    path = Path(provenance_path).resolve()
    root = path.parent
    payload = _read_json(path)
    _require_exact_keys(
        payload,
        {
            "schema_version", "kind", "status", "response_gradient_contract",
            "native_build", "execution_binding", "response_binding",
            "alpha_grid_binding", "emitted_gradient", "legacy_field_substitution",
            "limitations",
        },
        "native patch provenance",
    )
    if payload.get("schema_version") != LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_SCHEMA_VERSION:
        raise ValueError("native patch provenance schema_version is unsupported")
    if payload.get("kind") != LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_KIND:
        raise ValueError("native patch provenance kind is invalid")
    if payload.get("status") != "emitted_unqualified":
        raise ValueError("native patch provenance status must be emitted_unqualified")

    contract_path, contract = _read_contract(response_gradient_contract_path)
    if contract.get("schema_version") != 2:
        raise ValueError("native patch provenance requires the v2 serial response/gradient contract")
    _validate_contract_binding(_mapping(payload, "response_gradient_contract"), contract_path, contract)
    _validate_native_build(root, _mapping(payload, "native_build"))
    _validate_execution(root, _mapping(payload, "execution_binding"), contract)
    _validate_response(root, _mapping(payload, "response_binding"), contract)
    _validate_alpha_grid(root, _mapping(payload, "alpha_grid_binding"), contract)
    gradient = _validate_emitted_gradient(
        root, _mapping(payload, "emitted_gradient"), contract,
        final_time=str(_mapping(payload, "response_binding")["final_time"]),
    )
    _validate_legacy_rejection(_mapping(payload, "legacy_field_substitution"))
    _validate_limitations(payload.get("limitations"))

    response = _mapping(payload, "response_binding")
    alpha = _mapping(payload, "alpha_grid_binding")
    return LocalizedG2NativePatchProvenance(
        provenance_json=path,
        gradient_npy=gradient,
        flow_case_id=str(response["flow_case_id"]),
        response_id=str(response["response_id"]),
        adjoint_name=str(response["named_adjoint_id"]),
        final_time=str(response["final_time"]),
        cfd_cell_count=int(alpha["cfd_cell_count"]),
    )


def _validate_contract_binding(value: Mapping[str, object], path: Path, contract: Mapping[str, object]) -> None:
    _require_exact_keys(value, {"sha256", "serial_runtime_sha256"}, "response_gradient_contract")
    _require_sha(value.get("sha256"), "response_gradient_contract sha256")
    _require_sha(value.get("serial_runtime_sha256"), "response_gradient_contract serial_runtime_sha256")
    if value["sha256"] != _sha256_file(path):
        raise ValueError("native patch provenance response/gradient contract hash mismatch")
    compiler = _mapping(contract, "compiler")
    if value["serial_runtime_sha256"] != compiler.get("serial_runtime_sha256"):
        raise ValueError("native patch provenance serial runtime hash does not match compiler contract")


def _validate_native_build(root: Path, value: Mapping[str, object]) -> None:
    _require_exact_keys(
        value,
        {"openfoam_distribution", "openfoam_version", "source_revision_sha1", "source_tree_archive", "container_image", "patch", "build_log", "library"},
        "native_build",
    )
    if value.get("openfoam_distribution") != "OpenCFD" or value.get("openfoam_version") != "v2512":
        raise ValueError("native patch provenance requires the pinned OpenCFD v2512 source")
    revision = value.get("source_revision_sha1")
    if not isinstance(revision, str) or _SHA1.fullmatch(revision) is None:
        raise ValueError("native patch provenance source_revision_sha1 must be a lowercase Git SHA-1")
    _validate_hashed_file(root, _mapping(value, "source_tree_archive"), "source tree archive")
    image = _mapping(value, "container_image")
    _require_exact_keys(image, {"reference", "digest"}, "container_image")
    if not isinstance(image.get("reference"), str) or not image["reference"]:
        raise ValueError("native patch provenance container image reference is required")
    digest = image.get("digest")
    if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise ValueError("native patch provenance container image digest must be sha256:<64 lowercase hex>")
    _validate_hashed_file(root, _mapping(value, "patch"), "native patch")
    _validate_hashed_file(root, _mapping(value, "build_log"), "native patch build log")
    library = _mapping(value, "library")
    _require_exact_keys(library, {"relative_path", "sha256", "soname"}, "native patch library")
    if not isinstance(library.get("soname"), str) or not library["soname"].endswith(".so"):
        raise ValueError("native patch library soname must name a shared object")
    _require_sha(library.get("sha256"), "native patch library sha256")
    library_path = _relative_file(root, library.get("relative_path"), "native patch library")
    if library["sha256"] != _sha256_file(library_path):
        raise ValueError("native patch library hash mismatch")


def _validate_execution(root: Path, value: Mapping[str, object], contract: Mapping[str, object]) -> None:
    _require_exact_keys(value, {"serial_execution", "block_mesh_sha256", "cell_centre_ordering_proof"}, "execution_binding")
    if value.get("serial_execution") != "required_non_decomposed":
        raise ValueError("native patch provenance requires explicit serial non-decomposed execution")
    _require_sha(value.get("block_mesh_sha256"), "execution block_mesh_sha256")
    if value["block_mesh_sha256"] != contract.get("block_mesh_sha256"):
        raise ValueError("native patch provenance blockMesh hash does not match compiler contract")
    # The proof is retained as an immutable evidence file rather than merely
    # copying a claimed digest into this manifest.
    proof = _mapping(value, "cell_centre_ordering_proof")
    proof_path = _validate_hashed_file(root, proof, "cell-centre ordering proof")
    proof_data = _read_json(proof_path)
    if (
        proof_data.get("kind") != "localized_g2_cell_centre_x_fastest_proof"
        or proof_data.get("status") != "proved"
        or proof_data.get("block_mesh_sha256") != contract.get("block_mesh_sha256")
        or proof_data.get("grid_sha256") != contract.get("cfd_grid_sha256")
        or proof_data.get("cell_count") != contract.get("cfd_cell_count")
        or proof_data.get("cell_order") != CANONICAL_CELL_ORDER
    ):
        raise ValueError("native patch provenance cell-centre proof does not match the serial compiler contract")


def _validate_response(root: Path, value: Mapping[str, object], contract: Mapping[str, object]) -> None:
    _require_exact_keys(
        value,
        {"flow_case_id", "response_id", "named_adjoint_id", "final_time", "native_coefficient_units", "native_coefficient_value", "converted_units", "conversion", "response_file"},
        "response_binding",
    )
    for key in ("flow_case_id", "response_id", "named_adjoint_id"):
        if value.get(key) != contract.get(key):
            raise ValueError(f"native patch provenance {key} does not match compiler contract")
    final_time = value.get("final_time")
    if not isinstance(final_time, str) or not _SAFE_TIME.fullmatch(final_time) or final_time in {".", ".."}:
        raise ValueError("native patch provenance final_time must be an explicit safe token")
    if value.get("native_coefficient_units") != "1":
        raise ValueError("native patch provenance raw derivative must retain dimensionless coefficient units")
    coefficient = value.get("native_coefficient_value")
    if isinstance(coefficient, bool) or not isinstance(coefficient, (int, float)) or not np.isfinite(float(coefficient)):
        raise ValueError("native patch provenance native coefficient response value must be finite")
    response = _mapping(contract, "primal_response")
    gradient = _mapping(contract, "adjoint_gradient")
    if value.get("converted_units") != response.get("units") or response.get("units") != gradient.get("units"):
        raise ValueError("native patch provenance converted units do not match compiler response/gradient contract")
    if value.get("conversion") != response.get("scale") or response.get("scale") != gradient.get("scale"):
        raise ValueError("native patch provenance coefficient conversion must exactly match compiler contract")
    source = _mapping(response, "source")
    template = source.get("relative_path_template")
    pointer = source.get("json_pointer")
    response_file = _mapping(value, "response_file")
    _require_exact_keys(response_file, {"relative_path", "sha256", "json_pointer"}, "native response file")
    if not isinstance(template, str) or template.count("{final_time}") != 1 or not isinstance(pointer, str):
        raise ValueError("compiler response source is invalid")
    if response_file.get("relative_path") != template.replace("{final_time}", final_time):
        raise ValueError("native patch provenance response path does not match compiler final-time source contract")
    if response_file.get("json_pointer") != pointer:
        raise ValueError("native patch provenance response JSON selector does not match compiler contract")
    _require_sha(response_file.get("sha256"), "native response file sha256")
    response_path = _relative_file(root, response_file.get("relative_path"), "native response file")
    if response_file["sha256"] != _sha256_file(response_path):
        raise ValueError("native response file hash mismatch")
    observed = _read_json_scalar(response_path, pointer)
    if observed != float(coefficient):
        raise ValueError("native patch provenance response coefficient value does not match the hashed response file")


def _validate_alpha_grid(root: Path, value: Mapping[str, object], contract: Mapping[str, object]) -> None:
    _require_exact_keys(
        value,
        {"alpha_case_manifest", "source_alpha_values_sha256", "adjoint_used_alpha_values_sha256", "alpha_binding_sha256", "cfd_grid_sha256", "cfd_cell_count", "cell_order"},
        "alpha_grid_binding",
    )
    _require_sha(value.get("source_alpha_values_sha256"), "source alpha values sha256")
    _require_sha(value.get("adjoint_used_alpha_values_sha256"), "adjoint-used alpha values sha256")
    _require_sha(value.get("alpha_binding_sha256"), "alpha binding sha256")
    _require_sha(value.get("cfd_grid_sha256"), "CFD grid sha256")
    if value.get("cfd_grid_sha256") != contract.get("cfd_grid_sha256"):
        raise ValueError("native patch provenance CFD grid does not match compiler contract")
    if value.get("cfd_cell_count") != contract.get("cfd_cell_count") or not isinstance(value.get("cfd_cell_count"), int) or isinstance(value.get("cfd_cell_count"), bool):
        raise ValueError("native patch provenance CFD cell count does not match compiler contract")
    if value.get("cell_order") != CANONICAL_CELL_ORDER or contract.get("cell_order") != CANONICAL_CELL_ORDER:
        raise ValueError("native patch provenance requires canonical x-fastest cell ordering")
    manifest_ref = _mapping(value, "alpha_case_manifest")
    manifest_path = _validate_hashed_file(root, manifest_ref, "localized OpenFOAM alpha-case manifest")
    manifest = _read_json(manifest_path)
    if manifest.get("kind") != "localized_openfoam_alpha_case" or manifest.get("status") != "prepared":
        raise ValueError("native patch provenance alpha case manifest is not a prepared localized alpha case")
    source = _mapping(manifest, "alpha_source")
    binding = _mapping(manifest, "alpha_binding")
    if source.get("path") != "0.orig/alpha":
        raise ValueError("native patch provenance alpha case manifest does not bind the strict 0.orig/alpha field")
    alpha = read_openfoam_alpha_field(root / "0.orig" / "alpha")
    if (
        source.get("values_sha256") != alpha.value_sha256
        or source.get("cell_count") != alpha.cell_count
        or source.get("cfd_grid_sha256") != value.get("cfd_grid_sha256")
        or source.get("cfd_cell_count") != value.get("cfd_cell_count")
        or source.get("cell_order") != CANONICAL_CELL_ORDER
        or source.get("binding_sha256") != value.get("alpha_binding_sha256")
        or binding.get("binding_sha256") != value.get("alpha_binding_sha256")
        or binding.get("cfd_grid_sha256") != value.get("cfd_grid_sha256")
        or binding.get("cfd_cell_count") != value.get("cfd_cell_count")
    ):
        raise ValueError("native patch provenance alpha case manifest/codec does not match declared alpha-grid binding")
    if value.get("source_alpha_values_sha256") != alpha.value_sha256 or value.get("adjoint_used_alpha_values_sha256") != alpha.value_sha256:
        raise ValueError("native patch provenance source/adjoint alpha hashes do not match the strict alpha codec")


def _validate_emitted_gradient(
    root: Path,
    value: Mapping[str, object],
    contract: Mapping[str, object],
    *,
    final_time: str,
) -> Path:
    _require_exact_keys(
        value,
        {"field_name", "variable", "meaning", "chain_stage", "relative_path", "sha256", "array_value_sha256", "dtype", "shape"},
        "emitted_gradient",
    )
    if value.get("field_name") != "d_coefficient_d_raw_alpha":
        raise ValueError("native patch provenance requires the dedicated d_coefficient_d_raw_alpha field name")
    if value.get("variable") != "raw_alpha" or value.get("meaning") != "dJ=sum_i g_alpha[i]*d(alpha_i)":
        raise ValueError("native patch provenance emitted gradient is not the declared raw-alpha derivative")
    if value.get("chain_stage") != "alpha->alphaTilda->beta->named_response_adjoint":
        raise ValueError("native patch provenance does not bind the complete declared adjoint chain")
    source = _mapping(contract, "adjoint_gradient").get("source")
    if not isinstance(source, Mapping):
        raise ValueError("compiler adjoint-gradient source is invalid")
    template = source.get("relative_path_template")
    raw_relative = value.get("relative_path")
    if not isinstance(raw_relative, str) or not raw_relative.endswith(".npy") or "topOSens" in raw_relative or "topologySens" in raw_relative:
        raise ValueError("native patch provenance gradient must be a dedicated non-legacy NPY field")
    # The field must use the compiler's exact time-expanded source path.  The
    # final time itself is checked in response_binding before this comparison.
    # Derive it from the only contract source rather than inferring a filename.
    # (The template is deliberately exact in the serial runtime contract.)
    if not isinstance(template, str) or template.count("{final_time}") != 1:
        raise ValueError("compiler gradient source does not contain an explicit final-time placeholder")
    if raw_relative != template.replace("{final_time}", final_time):
        raise ValueError("native patch provenance gradient path does not match compiler final-time source contract")
    gradient = _relative_file(root, raw_relative, "emitted native gradient")
    _require_sha(value.get("sha256"), "emitted gradient file sha256")
    _require_sha(value.get("array_value_sha256"), "emitted gradient array value sha256")
    if value["sha256"] != _sha256_file(gradient):
        raise ValueError("native patch provenance emitted gradient file hash mismatch")
    array = np.load(gradient, allow_pickle=False)
    if not isinstance(array, np.ndarray) or array.dtype != np.dtype(np.float64) or not array.dtype.isnative or array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("native patch provenance emitted gradient must be a finite native float64 vector")
    if value.get("shape") != [int(array.size)] or array.size != contract.get("cfd_cell_count"):
        raise ValueError("native patch provenance emitted gradient shape does not match compiler CFD cell count")
    if value.get("dtype") != "float64" or value["array_value_sha256"] != _sha256_array(array):
        raise ValueError("native patch provenance emitted gradient value identity is invalid")
    return gradient


def _validate_legacy_rejection(value: Mapping[str, object]) -> None:
    _require_exact_keys(value, {"topOSens", "topologySens"}, "legacy_field_substitution")
    if value.get("topOSens") != "forbidden" or value.get("topologySens") != "forbidden":
        raise ValueError("native patch provenance must explicitly forbid legacy topOSens/topologySens substitution")


def _validate_limitations(value: object) -> None:
    required = {
        "provenance_validation_does_not_prove_native_gradient_correctness",
        "directional_fd_qualification_remains_required",
        "legacy_topOSens_and_topologySens_are_not_substitutes",
    }
    if not isinstance(value, list) or set(value) != required:
        raise ValueError("native patch provenance limitations must explicitly retain the qualification boundary")


def _validate_hashed_file(root: Path, value: Mapping[str, object], context: str) -> Path:
    _require_exact_keys(value, {"relative_path", "sha256"}, context)
    _require_sha(value.get("sha256"), f"{context} sha256")
    path = _relative_file(root, value.get("relative_path"), context)
    if value["sha256"] != _sha256_file(path):
        raise ValueError(f"{context} hash mismatch")
    return path


def _relative_file(root: Path, raw: object, context: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{context} relative_path must be non-empty text")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{context} relative_path must stay within the runtime case")
    path = (root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{context} relative_path escapes the runtime case") from exc
    if not path.is_file():
        raise FileNotFoundError(f"{context} is missing: {path}")
    return path


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{key} must be an object")
    return result


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read native patch provenance JSON: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("native patch provenance JSON root must be an object")
    return value


def _read_json_scalar(path: Path, pointer: str) -> float:
    """Resolve the compiler-declared RFC-6901 scalar without filename inference."""

    value: object = _read_json(path)
    if not pointer.startswith("/"):
        raise ValueError("compiler response JSON pointer must start with '/'")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, Mapping) and token in value:
            value = value[token]
        elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
            value = value[int(token)]
        else:
            raise ValueError("native patch provenance response JSON selector does not select exactly one scalar")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(float(value)):
        raise ValueError("native patch provenance response JSON selector does not select a finite scalar")
    return float(value)


def _require_exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{context} has unexpected or missing fields")


def _require_sha(value: object, context: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{context} must be a lowercase SHA-256 hex digest")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


__all__ = [
    "LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_FILENAME",
    "LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_KIND",
    "LOCALIZED_G2_NATIVE_PATCH_PROVENANCE_SCHEMA_VERSION",
    "LocalizedG2NativePatchProvenance",
    "validate_localized_g2_native_patch_provenance",
]
