#!/usr/bin/env python3
"""Register the SDF-native sharp volume semantics against the v16 genesis.

Plan correction v2.1, contract 2: the SDF-native constraint volume is the
voxel-equivalent sharp volume of the canonical state, and the first SDF
volume limit is the genesis sharp volume of the registered v16 baseline
state.  This script re-measures the registered genesis state and records
the immutable registration.  No solver runs.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import (  # noqa: E402
    VOLUME_SEMANTICS_KIND,
    sharp_volume_m3,
    volume_semantics_report,
)

GENESIS_EVIDENCE = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"
GENESIS_STATE = ROOT / "work/sdf_native_genesis_v16/sdf_design_state.npz"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_volume_semantics_v1_2026_09.json"
EXPECTED_STATE_SHA256 = "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"
EXPECTED_GENESIS_CELL_MATERIAL_VOLUME_M3 = 0.12925000000000003


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise SystemExit(f"refusing to overwrite immutable artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    if not GENESIS_EVIDENCE.is_file():
        raise SystemExit("genesis evidence is missing")
    if not GENESIS_STATE.is_file():
        raise SystemExit(
            "genesis state npz is missing locally; the WorkSpace artifact for "
            f"{EVIDENCE_PATH.name} would be unbounded"
        )
    genesis_evidence_bytes = GENESIS_EVIDENCE.read_bytes()
    genesis = json.loads(genesis_evidence_bytes.decode("utf-8"))
    if genesis.get("kind") != "sdf_native_genesis_v16" and genesis.get("kind") != "sdf_native_genesis":
        raise SystemExit("genesis evidence has the wrong kind")
    registered_state_sha = genesis.get("state", {}).get("state_sha256") or genesis.get("state_sha256")
    if registered_state_sha != EXPECTED_STATE_SHA256:
        raise SystemExit(
            f"registered genesis state changed: {registered_state_sha}"
        )
    registered_material_volume = (
        genesis.get("material_diagnostics", {}).get("material_volume_m3")
    )
    if registered_material_volume != EXPECTED_GENESIS_CELL_MATERIAL_VOLUME_M3:
        raise SystemExit(f"registered genesis material volume changed: {registered_material_volume}")
    genesis_sha = _sha256_path(GENESIS_EVIDENCE)
    # The evidence JSON is already committed; its sha must equal the recorded
    # registration value from the genesis slice.
    recorded_genesis_sha = None
    registration_file = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json.sha256"
    if registration_file.is_file():
        recorded_genesis_sha = registration_file.read_text().strip()
    if recorded_genesis_sha != genesis_sha:
        raise SystemExit("genesis evidence sidecar mismatch")

    state = SDFDesignState.load(GENESIS_STATE)
    if state.state_sha256 != registered_state_sha:
        raise SystemExit(
            f"located state sha mismatch: signed {state.state_sha256} vs {registered_state_sha}"
        )
    # The contract limit is re-measured from the registered genesis state
    # itself; a hardcoded expectation would print a contract value without
    # proving it. The handoff's revoxelized cell material is the mesh-side
    # volume; the state-trilinear contract measure differs by registered
    # boundary-cell discretization (both are recorded, never conflated).
    volume_limit_m3 = sharp_volume_m3(state)
    if not (volume_limit_m3 > 0.0):
        raise SystemExit("measured genesis contract volume is not positive")
    cell_material_to_contract_ratio = float(registered_material_volume / volume_limit_m3)
    report = volume_semantics_report(state, volume_limit_m3=volume_limit_m3)
    if report["volume_m3"] != volume_limit_m3 or report["volume_violation_m3"] != 0.0:
        raise SystemExit("the baseline state must be feasible at its own re-measured limit")
    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": VOLUME_SEMANTICS_KIND,
        "registration_id": "sdf_native_volume_semantics_v1_2026_09",
        "evidence_class": "contract",
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "contract": {
            "volume_definition": report["volume_definition"],
            "first_sdf_volume_constraint": "V_phi <= V_phi_0",
            "volume_limit_m3": float(volume_limit_m3),
            "volume_limit_source": (
                "re-measured voxel-equivalent sharp volume of the registered v16 genesis state "
                f"({report['sampled_solid_centers']} sampled solid centers)"
            ),
            "cell_material_to_contract_volume_ratio": cell_material_to_contract_ratio,
            "discretization": "one sampled center per h-cube; zero-level values are not solid",
            "sub_voxel_sensitivity": "none",
            "differentiability": (
                "not claimed; a smoothed H_eps volume would be a separate later contract"
            ),
            "stage_t_density_volume": {
                "v_rho_m3": 0.0719735015,
                "stage_t_vmax_m3": 0.0763256681,
                "role": (
                    "Stage T diagnostic and Stage S entry fidelity observable only; "
                    "not an SDF-native constraint"
                ),
                "carried_into_sdf_stage_s": False,
            },
        },
        "measured": report,
        "input_lineage": {
            "genesis_evidence": {
                "path": GENESIS_EVIDENCE.relative_to(ROOT).as_posix(),
                "sha256": genesis_sha,
            },
            "genesis_state_npz": {
                "path": GENESIS_STATE.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(GENESIS_STATE),
            },
        },
        "claims_supported": [
            "the SDF-native volume contract is registered with its limit equal to the re-measured genesis contract volume",
            "the recorded handoff cell-material volume and the measured node-occupancy diagnostic are distinct samplings and were not conflated with the contract measure",
        ],
        "claims_not_supported": [
            "this is a semantics registration, not an optimizer qualification or a shape update",
            "no differentiable-volume or gradient claim",
            "no absolute, grid-independent, high-Re or full-vehicle downforce claim",
        ],
        "flags": {
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }
    payload = (
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit(f"evidence sidecar mismatch: {sidecar.relative_to(ROOT)}")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))
    summary = {
        "status": "registered",
        "registration_id": document["registration_id"],
        "volume_limit_m3": document["contract"]["volume_limit_m3"],
        "sampled_solid_centers": report["sampled_solid_centers"],
        "node_occupancy_diagnostic_m3": report["node_occupancy_diagnostic"]["volume_m3"],
        "cell_material_to_contract_ratio": cell_material_to_contract_ratio,
        "evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "evidence_sha256": digest,
        "solver_started": False,
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
