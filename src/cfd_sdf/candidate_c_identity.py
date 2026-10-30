"""Fail-closed binding to the frozen Candidate C composite operator identity.

The identity freeze fixes source and wrapper semantics for downstream
measurement. It does not qualify the operator's physics or any derivative.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from cfd_sdf.criteria_supersession import SupersessionError, _load_immutable


CONTRACT_RELATIVE_PATH = Path(
    "docs/evidence/candidate_c_composite_operator_identity_v1_2026_10.json"
)
OPERATOR_IDENTITY = "candidate_c_moment_blend+normal_floor_0.25"
PINNED_SOURCES = {
    "candidate_c_body_source": (
        "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
        "2a4b056a1a4a23dc5699ad340faed8ad35bfab4c103302169a93150feedd04c6",
    ),
    "normal_floor_body_source": (
        "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
        "6686585c205eb07508979b3fdba8bf7aab28c0b29a0d021606a2a1280d031ecf",
    ),
}
QUALIFICATION_FLAGS = (
    "shape_update_allowed",
    "fd_oracle",
    "field_gradient",
    "reverse",
    "optimizer",
    "topology",
)
TRANSITION_WIDTH_SOLVER = 1.1444091796875e-4


class CandidateCIdentityError(ValueError):
    """The required immutable Candidate C source identity is absent or invalid."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_candidate_c_identity(repository: Path) -> dict[str, Any]:
    """Load and verify the exact #44 composite identity contract and its sources."""
    repository = Path(repository).resolve()
    path = repository / CONTRACT_RELATIVE_PATH
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise CandidateCIdentityError(
            f"frozen Candidate C identity contract and SHA-256 sidecar are required: {path}"
        )
    try:
        contract, digest = _load_immutable(path)
    except SupersessionError as exc:
        raise CandidateCIdentityError(str(exc)) from exc
    if (contract.get("immutable") is not True
            or contract.get("status") != "identity_frozen_not_physical_qualification"
            or contract.get("registered_before_downstream_measurement") is not True):
        raise CandidateCIdentityError("Candidate C contract is not the required frozen identity")

    operator = contract.get("operator")
    if not isinstance(operator, dict) or operator.get("identity") != OPERATOR_IDENTITY:
        raise CandidateCIdentityError("Candidate C composite operator identity mismatch")
    for key, (relative_path, pinned_sha) in PINNED_SOURCES.items():
        source = operator.get(key)
        if not isinstance(source, dict):
            raise CandidateCIdentityError(f"Candidate C contract is missing {key}")
        if source.get("path") != relative_path or source.get("sha256") != pinned_sha:
            raise CandidateCIdentityError(f"Candidate C pinned source binding mismatch: {key}")
        source_path = repository / relative_path
        if not source_path.is_file() or _sha256(source_path) != pinned_sha:
            raise CandidateCIdentityError(f"Candidate C source bytes do not match pin: {relative_path}")

    floor = operator.get("normal_floor")
    width = operator.get("transition_width_solver")
    if isinstance(floor, bool) or floor != 0.25:
        raise CandidateCIdentityError("Candidate C normal_floor must be exactly 0.25")
    if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isclose(
        float(width), TRANSITION_WIDTH_SOLVER, rel_tol=0.0, abs_tol=0.0
    ):
        raise CandidateCIdentityError("Candidate C transition width mismatch")
    if operator.get("simulation_body") != (
        "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid)+moving_ground)"
    ):
        raise CandidateCIdentityError("Candidate C simulation body composition mismatch")
    if operator.get("force_integration_body") != (
        "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))"
    ):
        raise CandidateCIdentityError("Candidate C force integration body composition mismatch")

    flags = contract.get("qualification_flags")
    if not isinstance(flags, dict):
        raise CandidateCIdentityError("Candidate C qualification_flags object is required")
    for flag in QUALIFICATION_FLAGS:
        if flags.get(flag) is not False:
            raise CandidateCIdentityError(f"qualification flag must remain literal false: {flag}")
    if set(flags) != set(QUALIFICATION_FLAGS):
        raise CandidateCIdentityError("Candidate C contract must contain exactly the six pinned flags")

    return {
        "contract_path": CONTRACT_RELATIVE_PATH.as_posix(),
        "contract_sha256": digest,
        "operator_identity": OPERATOR_IDENTITY,
        "body_source_sha256": {
            key: pinned_sha for key, (_, pinned_sha) in PINNED_SOURCES.items()
        },
        "qualification_flags": {flag: False for flag in QUALIFICATION_FLAGS},
        "physical_qualification": False,
    }


__all__ = ["CandidateCIdentityError", "load_candidate_c_identity"]
