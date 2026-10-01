#!/usr/bin/env python3
"""Create a solver-free, fail-closed GEOM-01 report for canonical v16."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cfd_sdf.design.geometry_gates import evaluate_geometry_gates
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.topology_policy import SDFTopologyPolicy
from cfd_sdf.design.volume_semantics import SMOOTHED_VOLUME_LIMIT_M3

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "work/issue_29/canonical_v16/sdf_design_state.npz"
GENESIS_PATH = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"
CONTRACT_PATH = ROOT / "docs/sdf_native_geometry_gates_contract_v1_2026_10.md"
PREREG_PATH = ROOT / "docs/evidence/sdf_native_geometry_gates_v16_prereg_2026_10.json"
OUTPUT_PATH = ROOT / "docs/evidence/sdf_native_geometry_gates_v16_2026_10.json"
EXPECTED_STATE_ARCHIVE_SHA256 = "3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe"
EXPECTED_STATE_SHA256 = "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"
EXPECTED_GENESIS_SHA256 = "3c8e241681c80962a7fd62f1926e382d473ec8e9f3e6b9140bea9600d41cf670"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    inputs = {
        STATE_PATH: EXPECTED_STATE_ARCHIVE_SHA256,
        GENESIS_PATH: EXPECTED_GENESIS_SHA256,
    }
    for path, expected in inputs.items():
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"input SHA-256 mismatch: {path}: {actual} != {expected}")
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    for relative, expected in prereg["source_sha256"].items():
        path = ROOT / relative
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"pre-registered source SHA-256 mismatch: {relative}: {actual} != {expected}")

    state = SDFDesignState.load(STATE_PATH)
    if state.state_sha256 != EXPECTED_STATE_SHA256:
        raise SystemExit(
            f"canonical state digest mismatch: {state.state_sha256} != {EXPECTED_STATE_SHA256}"
        )
    genesis = json.loads(GENESIS_PATH.read_text(encoding="utf-8"))
    if genesis["state"]["state_file_sha256"] != EXPECTED_STATE_ARCHIVE_SHA256:
        raise SystemExit("genesis manifest does not bind the supplied canonical state archive")
    if genesis["state"]["state_sha256"] != EXPECTED_STATE_SHA256:
        raise SystemExit("genesis manifest does not bind the supplied canonical state digest")
    report = evaluate_geometry_gates(
        state,
        policy=SDFTopologyPolicy.unresolved_registration(),
        parent_state=state,
        root_group_masks=None,
        volume_limit_m3=SMOOTHED_VOLUME_LIMIT_M3,
        min_clearance_m=None,
        eikonal_median_tolerance=None,
        low_gradient_norm_floor=None,
        policy_scope="canonical_unresolved",
    )
    artifact = {
        "schema_version": 1,
        "kind": "sdf_native_geometry_gates_v16",
        "contract_id": "sdf_native_geometry_gates_v1",
        "evidence_class": "solver_free_geometry_contract_and_capability",
        "solver_started": False,
        "input_manifest": {
            "canonical_state_archive": {
                "path": str(STATE_PATH.relative_to(ROOT)),
                "sha256": EXPECTED_STATE_ARCHIVE_SHA256,
                "state_sha256": EXPECTED_STATE_SHA256,
            },
            "genesis_report": {
                "path": str(GENESIS_PATH.relative_to(ROOT)),
                "sha256": EXPECTED_GENESIS_SHA256,
            },
            "contract": {
                "path": str(CONTRACT_PATH.relative_to(ROOT)),
                "sha256": sha256(CONTRACT_PATH),
            },
            "preregistration": {
                "path": str(PREREG_PATH.relative_to(ROOT)),
                "sha256": sha256(PREREG_PATH),
            },
            "runner": {
                "path": str(Path(__file__).resolve().relative_to(ROOT)),
                "sha256": sha256(Path(__file__).resolve()),
            },
            "canonical_gridsdf_zero_level_export_mesh": {
                "path": None,
                "sha256": None,
                "status": "not supplied; downstream Stage V/STL mesh integrity is unresolved",
            },
            "voxel_cell_union_surface": {
                "type": "in-memory diagnostic surface nets mesh derived from V_phi cell occupancy",
                "sha256": None,
                "status": "proxy checks are nested in geometry_report and do not qualify canonical export",
            },
        },
        "canonical_policy_status": "unresolved; no source ProblemSpec/mask binding or successor topology policy registered",
        "physical_feature_limits_status": "unregistered; no limits inferred from grid spacing",
        "flags": {
            "shape_update_allowed": False,
            "fd_oracle": False,
            "field_gradient": False,
            "reverse": False,
            "optimizer": False,
            "topology": False,
        },
        "geometry_report": report,
        "claims_supported": [
            "the exact hash-verified canonical v16 SDF state was evaluated by every registered solver-free GEOM-01 gate",
            "unresolved policy-dependent gates block the aggregate verdict",
            "component count, gradient-band distribution, export-surface checks, and inherited volume semantics are reported as measurements",
        ],
        "claims_not_supported": [
            "canonical topology policy qualification or disconnected-component permission",
            "physical minimum feature width, void width, gap, or domain-clearance qualification",
            "flow/force, solver, optimization, manufacturing, or shape-update qualification",
        ],
    }
    encoded = json.dumps(artifact, sort_keys=True, indent=2, allow_nan=False) + "\n"
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
    print(f"artifact={OUTPUT_PATH.relative_to(ROOT)}")
    print(f"artifact_sha256={sha256(OUTPUT_PATH)}")
    print(f"state_archive_sha256={EXPECTED_STATE_ARCHIVE_SHA256}")
    print(f"state_sha256={state.state_sha256}")
    print(f"preregistration_sha256={sha256(PREREG_PATH)}")
    print(f"verdict_pass={report['verdict']['pass']}")
    print(f"unmeasured_gates={','.join(report['verdict']['unmeasured'])}")


if __name__ == "__main__":
    main()
