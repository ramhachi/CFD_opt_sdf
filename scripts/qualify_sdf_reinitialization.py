#!/usr/bin/env python3
"""Run the immutable solver-free SDF reinitialization contract round."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy

from cfd_sdf.design.sdf_reinitialization import (
    REINIT_CONTRACT_ID,
    REINIT_CONTRACT_SHA256,
    TOLERANCES,
    SDFReinitializationError,
    reinitialize_sdf,
)
from cfd_sdf.design.sdf_state import SDFDesignState

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = ROOT / "docs/evidence/sdf_native_reinitialization_godunov2_v2_round1_2026_10.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _state(phi: np.ndarray, *, spacing_m: float, origin_m: tuple[float, float, float]) -> SDFDesignState:
    return SDFDesignState.create(
        phi=np.asarray(phi, dtype=np.float32), origin_m=origin_m, spacing_m=spacing_m,
        narrow_band_width_m=3.0 * spacing_m,
    )


def analytic_fixture(spec: dict) -> SDFDesignState:
    shape = tuple(int(value) for value in spec["shape"])
    spacing = float(spec["spacing_m"])
    origin = tuple(float(value) for value in spec["origin_m"])
    axes = [origin[i] + np.arange(shape[i], dtype=np.float64) * spacing for i in range(3)]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    center = np.asarray(spec["center_m"], dtype=np.float64)
    if spec["shape_kind"] == "sphere":
        phi = np.sqrt((x - center[0])**2 + (y - center[1])**2 + (z - center[2])**2) - float(spec["radius_m"])
    elif spec["shape_kind"] == "sphere_pair":
        radii = [float(value) for value in spec["radii_m"]]
        centers = [np.asarray(value, dtype=np.float64) for value in spec["centers_m"]]
        phi = np.minimum.reduce([
            np.sqrt((x - item[0])**2 + (y - item[1])**2 + (z - item[2])**2) - radius
            for item, radius in zip(centers, radii)
        ])
    elif spec["shape_kind"] == "box":
        half = np.asarray(spec["half_extents_m"], dtype=np.float64)
        q = np.stack((np.abs(x - center[0]), np.abs(y - center[1]), np.abs(z - center[2])), axis=-1) - half
        phi = np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(np.max(q, axis=-1), 0.0)
    else:
        raise ValueError(f"unsupported registered analytic fixture: {spec['shape_kind']}")
    return _state(phi, spacing_m=spacing, origin_m=origin)


def verify_criteria(criteria_path: Path, criteria: dict) -> tuple[str, dict]:
    digest = sha256(criteria_path)
    canonical = {key: value for key, value in criteria.items() if key != "criteria_sha256"}
    declared_criteria_sha = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != digest:
        raise ValueError("criteria SHA sidecar missing or mismatched")
    if (criteria.get("immutable") is not True or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False
            or criteria.get("criteria_id") != "sdf_native_reinitialization_godunov2_v2_round2_2026_10"):
        raise ValueError("criteria is not the immutable unrun reinitialization round")
    if criteria.get("criteria_sha256") != declared_criteria_sha:
        raise ValueError("criteria canonical digest mismatch")
    if (criteria.get("method_contract_id") != REINIT_CONTRACT_ID
            or criteria.get("method_contract_sha256") != REINIT_CONTRACT_SHA256
            or criteria.get("tolerances") != TOLERANCES):
        raise ValueError("criteria method identity does not match the implementation")
    registered_commit = criteria["source_commit"]
    current_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    subprocess.check_call(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", registered_commit, current_commit])
    dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip()
    if dirty:
        raise ValueError("qualification requires a clean source checkout")
    observed = {}
    for entry in criteria["source_inputs"]:
        path = ROOT / entry["path"]
        actual = sha256(path) if path.is_file() else None
        observed[entry["path"]] = actual
        if actual != entry["sha256"]:
            raise ValueError(f"registered source SHA mismatch: {entry['path']}")
    return digest, observed


def run(criteria_path: Path, canonical_path: Path, output_dir: Path) -> dict:
    criteria = json.loads(criteria_path.read_text())
    criteria_sha, source_hashes = verify_criteria(criteria_path, criteria)
    if output_dir.exists():
        raise FileExistsError(f"append-only result directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    if sha256(canonical_path) != criteria["canonical_v16"]["state_npz_sha256"]:
        raise ValueError("canonical v16 state input SHA mismatch")
    cases = []
    state_inputs = []
    for fixture in criteria["analytic_fixtures"]:
        state_inputs.append((fixture["case_id"], analytic_fixture(fixture)))
    canonical_state = SDFDesignState.load(canonical_path)
    if (canonical_state.state_sha256 != criteria["canonical_v16"]["state_sha256"]
            or canonical_state.phi_sha256() != criteria["canonical_v16"]["phi_sha256"]):
        raise ValueError("canonical v16 state identity mismatch")
    state_inputs.append(("canonical_v16", canonical_state))
    for case_id, before in state_inputs:
        profile = "canonical" if case_id == "canonical_v16" else "fixture"
        input_state = before.to_dict()
        try:
            result = reinitialize_sdf(before, profile=profile, fail_closed=False)
            target = output_dir / f"{case_id}_reinitialized.npz"
            result.state.save(target)
            cases.append({
                "case_id": case_id,
                "status": "PASS" if result.report["admissible"] else "FAIL",
                "input_state": input_state,
                "output_state": result.state.to_dict(),
                "output_npz": {"path": target.name, "sha256": sha256(target)},
                "report": result.report,
            })
        except SDFReinitializationError as error:
            cases.append({"case_id": case_id, "status": "UNRESOLVED",
                "input_state": input_state, "output_state": None, "output_npz": None,
                "error": str(error), "convergence": "not reached or no valid interface"})
    overall = "FAIL" if any(case["status"] == "FAIL" for case in cases) else (
        "UNRESOLVED" if any(case["status"] == "UNRESOLVED" for case in cases) else "PASS")
    evidence = {
        "schema_version": 1,
        "criteria_id": criteria["criteria_id"],
        "criteria_sha256": criteria_sha,
        "method_id": REINIT_CONTRACT_ID,
        "method_contract_sha256": REINIT_CONTRACT_SHA256,
        "source_commit": criteria["source_commit"],
        "source_sha256": source_hashes,
        "canonical_input": {"path": str(canonical_path), "sha256": sha256(canonical_path)},
        "runtime": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__},
        "execution_scope": "CPU only; no solver, GPU, optimizer, or finite-difference forward path",
        "qualification_flags_changed": False,
        "tolerances": TOLERANCES,
        "cases": cases,
        "verdict": overall,
        "claim_limit": "operator-effect qualification only; no optimizer descent, FD, solver, or physical claim",
    }
    path = output_dir / "reinitialization_evidence.json"
    path.write_text(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n")
    path.with_suffix(path.suffix + ".sha256").write_text(sha256(path) + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--canonical-state", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.criteria.resolve(), args.canonical_state.resolve(), args.output_dir.resolve())
    print(json.dumps({"verdict": result["verdict"], "criteria_sha256": result["criteria_sha256"],
        "case_count": len(result["cases"]), "output_dir": str(args.output_dir.resolve())}, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
