"""SDF genesis runner for the registered v16 Stage S baseline lineage.

This slice is the first gate of the SDF-native gate order
(``sdf_native_genesis_v16_2026_09``): build the canonical
:class:`~cfd_sdf.design.sdf_state.SDFDesignState` from the already
registered, hash-frozen v16 handoff and record an immutable contract
evidence artifact.  No solver runs, no CFD, no responses.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.genesis import (  # noqa: E402
    GENESIS_MASK_PROJECTION_POLICY,
    persist_genesis_report,
    sdf_state_from_handoff,
)

BASELINE_JSON = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
OUTPUT_DIR = ROOT / "work/sdf_native_genesis_v16"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"

HANDOFF_MANIFEST_RELATIVE = "work/pq4_1_v16_state_v2/sweep/threshold_0.5/handoff_manifest.json"


def _sha256_path(path: Path) -> str:
    import hashlib

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


def build_genesis_evidence() -> dict[str, Any]:
    baseline_bytes = BASELINE_JSON.read_bytes()
    baseline_lines = json.loads(baseline_bytes.decode("utf-8"))

    registered_handoff = baseline_lines.get("handoff", {}).get("manifest", {})
    if registered_handoff.get("path") != HANDOFF_MANIFEST_RELATIVE:
        raise SystemExit(
            f"baseline v2 handoff manifest path changed: {registered_handoff.get('path')!r}"
        )
    registered_handoff_sha = registered_handoff.get("sha256")
    handoff_manifest_path = ROOT / HANDOFF_MANIFEST_RELATIVE
    handoff_sha = _sha256_path(handoff_manifest_path)
    if handoff_sha != registered_handoff_sha:
        raise SystemExit(
            f"handoff manifest hash mismatch: baseline says {registered_handoff_sha}, "
            f"file is {handoff_sha}"
        )

    registered_surface_sha = baseline_lines.get("clearance", {}).get("surface_stl_sha256")
    if not registered_surface_sha:
        raise SystemExit("baseline v2 records no surface STL hash")

    result = sdf_state_from_handoff(
        handoff_manifest_path,
        output_dir=OUTPUT_DIR,
        expected_surface_sha256=registered_surface_sha,
        persist=True,
    )
    report_path = persist_genesis_report(result, output_dir=OUTPUT_DIR)
    state_path = result.state_path or (OUTPUT_DIR / "sdf_design_state.npz")

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "kind": "sdf_native_genesis_v16",
        "genesis_id": "sdf_native_genesis_v16_2026_09",
        "evidence_class": "contract_and_capability",
        "mask_projection_policy": GENESIS_MASK_PROJECTION_POLICY,
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "lineage": {
            "baseline_evidence": {
                "path": BASELINE_JSON.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(BASELINE_JSON),
            },
            "handoff_manifest": {
                "path": HANDOFF_MANIFEST_RELATIVE,
                "sha256": handoff_sha,
            },
            "surface_stl_sha256": registered_surface_sha,
        },
        "state": {
            "state_sha256": result.state.state_sha256,
            "phi_sha256": result.state.phi_sha256(),
            "state_path": state_path.relative_to(ROOT).as_posix(),
            "state_file_sha256": _sha256_path(state_path),
            "genesis_report_path": report_path.relative_to(ROOT).as_posix(),
            "genesis_report_sha256": _sha256_path(report_path),
        },
        "grid_identity": dict(result.report["grid_identity"]),
        "mask_cell_counts": dict(result.report["mask_cell_counts"]),
        "mask_point_counts": dict(result.report["mask_point_counts"]),
        "mask_checks": dict(result.report["mask_checks"]),
        "material_diagnostics": dict(result.report["material_diagnostics"]),
        "genesis_report": dict(result.report["handoff_artifacts_verified"]),
        "claims_supported": [
            "the canonical SDFDesignState is built hash-faithfully from the registered v16 handoff artifacts with all mask contract checks passing",
            "the state binds the registered baseline surface STL sha256 as source_sha256",
        ],
        "claims_not_supported": [
            "no WaterLily primal, SDF gradient, reverse-AD, topology-birth, optimizer or campaign qualification",
            "no absolute, grid-independent, high-Re or full-vehicle downforce claim; the v16 candidate itself is a blocked-stop checkpoint",
            "genesis proves no downstream consumer behavior",
        ],
        "flags": {
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }
    return evidence


def main() -> None:
    evidence = build_genesis_evidence()
    payload = (
        json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit(f"evidence sidecar mismatch: {sidecar.relative_to(ROOT)}")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))
    summary = {
        "status": "pass",
        "genesis_id": evidence["genesis_id"],
        "state_sha256": evidence["state"]["state_sha256"],
        "state_path": evidence["state"]["state_path"],
        "evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "evidence_sha256": digest,
        "solver_started": False,
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
