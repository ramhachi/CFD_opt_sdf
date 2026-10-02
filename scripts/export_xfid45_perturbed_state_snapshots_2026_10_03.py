#!/usr/bin/env python3
"""Save exact #45 perturbed GridSDF states bound by a geometry audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.gradients.directional_fd import (  # noqa: E402
    direction_sha256,
    generate_directions,
    perturbed_state,
    phi_sha256,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    audit_path = evidence / "geometry_audit.json"
    state_path = evidence / "canonical_state.npz"
    output = evidence / "state_snapshots"
    if not audit_path.is_file() or not state_path.is_file():
        raise SystemExit("geometry audit and canonical state must exist")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output: {output}")

    audit = json.loads(audit_path.read_text())
    if audit.get("kind") != "xfid01_geometry_preflight" or audit.get("solver_started") is not False:
        raise SystemExit("input is not a solver-free XFID geometry preflight")
    if sha256(state_path) != audit["canonical_state"]["file_sha256"]:
        raise SystemExit("canonical state file hash does not match geometry audit")
    if sha256(audit_path) != audit["artifact_sha256"] if "artifact_sha256" in audit else False:
        raise SystemExit("geometry audit self-hash mismatch")

    source_hashes = audit["source_sha256"]
    direction_path = ROOT / "src/cfd_sdf/gradients/directional_fd.py"
    state_source_path = ROOT / "src/cfd_sdf/design/sdf_state.py"
    if sha256(direction_path) != source_hashes["src/cfd_sdf/gradients/directional_fd.py"]:
        raise SystemExit("direction generator source changed since geometry audit")
    if sha256(state_source_path) != source_hashes["src/cfd_sdf/design/sdf_state.py"]:
        raise SystemExit("state serialization source changed since geometry audit")

    state = SDFDesignState.load(state_path)
    if state.state_sha256 != audit["canonical_state"]["state_sha256"]:
        raise SystemExit("canonical SDF state identity mismatch")
    epsilon = float(audit["direction_contract"]["primary_epsilon_m"])
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for direction_id, direction in generate_directions(state).items():
        direction_record = audit["direction_contract"]["directions"][direction_id]
        direction_hash = direction_sha256(direction)
        if direction_hash != direction_record["raw_sha256_float32_c_order"]:
            raise SystemExit(f"direction identity mismatch: {direction_id}")
        for sign, label in ((-1, "minus"), (1, "plus")):
            child, identity = perturbed_state(state, direction, epsilon_m=epsilon, sign=sign)
            expected = direction_record[label]
            for key in ("state_sha256", "phi_c_order_sha256", "phi_fortran_order_sha256"):
                if identity[key] != expected[key]:
                    raise SystemExit(f"perturbation identity mismatch: {direction_id}_{label} ({key})")
            path = output / f"{direction_id}_{label}.npz"
            child.save(path)
            restored = SDFDesignState.load(path)
            if restored.state_sha256 != expected["state_sha256"]:
                raise SystemExit(f"saved state round-trip mismatch: {path.name}")
            rows.append(
                {
                    "case_id": f"{direction_id}_{label}",
                    "path": path.relative_to(ROOT).as_posix(),
                    "file_sha256": sha256(path),
                    "state_sha256": restored.state_sha256,
                    "phi_c_order_sha256": phi_sha256(restored.phi, order="C"),
                    "phi_fortran_order_sha256": phi_sha256(restored.phi, order="F"),
                    "direction_sha256_float32_c_order": direction_hash,
                    "sign": sign,
                    "epsilon_m": epsilon,
                    "parent_state_sha256": state.state_sha256,
                }
            )

    manifest = {
        "schema_version": 1,
        "kind": "xfid01_perturbed_grid_sdf_snapshots",
        "source_geometry_audit_sha256": sha256(audit_path),
        "source_preflight_sha256": source_hashes[
            "scripts/audit_xfid45_geometry_preflight_2026_10_03.py"
        ],
        "snapshot_exporter_sha256": sha256(Path(__file__).resolve()),
        "canonical_state_sha256": state.state_sha256,
        "direction_generator_sha256": sha256(direction_path),
        "state_serialization_sha256": sha256(state_source_path),
        "snapshots": rows,
    }
    manifest_path = output / "snapshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    sidecar = output / "SHA256SUMS"
    sidecar.write_text(
        "".join(
            f"{sha256(path)}  {path.name}\n"
            for path in sorted([*output.glob("*.npz"), manifest_path], key=lambda p: p.name)
        )
    )
    print(
        json.dumps(
            {
                "snapshot_count": len(rows),
                "manifest": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256(manifest_path),
                "sha256sums": sidecar.relative_to(ROOT).as_posix(),
                "sha256sums_sha256": sha256(sidecar),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
