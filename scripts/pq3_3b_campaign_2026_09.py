"""PQ3.3b campaign runner (static implementation; DO NOT run until user go).

Refuses to start unless the immutable manifest v3 asserts SHA-256-verified,
preflight v4 passed, backend ids match the registered two-phase policy, and
the fresh output directory is free. Phase 1 states are recorded as
restoration_feasible only; objective_accepted requires the full Phase 2 gate
set (real trial primal, Path B bracket, canonical objective improvement, raw
downforce improvement, mask invariance, projected-volume upper bound).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402

MANIFEST = ROOT / "docs" / "evidence" / "pq3_3b_campaign_manifest_v3_2026_09.json"
MANIFEST_SIDE_CAR = MANIFEST.with_suffix(".json.sha256")
PREFLIGHT_V4 = ROOT / "docs" / "evidence" / "pq3_3b_preflight_v4_2026_09.json"
NOISE = ROOT / "docs" / "evidence" / "pq3_3b_noise_calibration_2026_09.json"
DEFAULT_OUTPUT = ROOT / "work" / "pq3_3b_campaign"
REGISTERED_TARGET = 0.018
V_MAX = 0.07632566813424899
ALPHA_LADDER = (1.0, 0.5, 0.25, 0.125, 0.0625)


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field} must be a registered SHA-256 digest")
    return value


def _referenced_path(reference: dict, field: str) -> Path:
    if not isinstance(reference, dict) or not reference.get("path"):
        raise ValueError(f"{field} path is missing")
    path = Path(reference["path"])
    return path if path.is_absolute() else ROOT / path


def _assert_file_reference(reference: dict, field: str) -> Path:
    path = _referenced_path(reference, field)
    expected = _sha256(reference.get("sha256"), f"{field}.sha256")
    if not path.is_file() or ca.sha256_file(path) != expected:
        raise ValueError(f"{field} file is missing or SHA-256 mismatched: {path}")
    return path


def _assert_registered_inputs(manifest: dict) -> Path:
    ca.assert_manifest_complete(manifest)
    _sha256(manifest.get("input_rho_sha256"), "input_rho_sha256")
    _sha256(manifest.get("compiled_problem_hash"), "compiled_problem_hash")
    checkpoint = _assert_file_reference(manifest.get("input_checkpoint"), "input_checkpoint")
    rho = np.ascontiguousarray(np.asarray(ca.load_json(checkpoint)["rho"], dtype=np.float64))
    if hashlib.sha256(rho.tobytes()).hexdigest() != manifest["input_rho_sha256"]:
        raise ValueError("input_rho_sha256 does not match the checkpoint rho")
    _assert_file_reference(manifest.get("problem_spec"), "problem_spec")
    grid = manifest.get("canonical_grid") or {}
    grid_path = _referenced_path(grid, "canonical_grid")
    grid_sha = _sha256(grid.get("sha256"), "canonical_grid.sha256")
    if not grid_path.is_file() or ca.sha256_file(grid_path) != grid_sha:
        raise ValueError("canonical_grid file is missing or SHA-256 mismatched")
    if "source_grid" in manifest:
        _assert_file_reference(manifest["source_grid"], "source_grid")
    template = _referenced_path(manifest.get("template_parent"), "template_parent")
    if not template.is_dir() or ca.tree_sha256(template) != _sha256(
        manifest.get("template_tree_hash"), "template_tree_hash"
    ):
        raise ValueError("template_parent tree is missing or SHA-256 mismatched")
    controls = _referenced_path(manifest.get("solver_controls"), "solver_controls")
    if controls.is_dir():
        controls_sha = ca.tree_sha256(controls)
    elif controls.is_file():
        controls_sha = ca.sha256_file(controls)
    else:
        raise ValueError("solver_controls path is missing")
    if controls_sha != _sha256(manifest.get("solver_controls_hash"), "solver_controls_hash"):
        raise ValueError("solver_controls SHA-256 mismatch")
    noise = _assert_file_reference(manifest.get("noise_calibration"), "noise_calibration")
    preflight = _assert_file_reference(manifest.get("preflight_v4"), "preflight_v4")
    if preflight.resolve() != PREFLIGHT_V4.resolve() or noise.resolve() != NOISE.resolve():
        raise ValueError("manifest references unregistered preflight or noise evidence")
    return preflight


def verify_preconditions(output_dir: Path, *, expected_manifest_sha: str | None = None) -> dict:
    """Assert every campaign precondition; fail-closed, no outputs created."""
    if not MANIFEST.is_file():
        raise SystemExit("manifest v3 missing")
    manifest = ca.load_json(MANIFEST)
    recorded_sha = _sha256(MANIFEST_SIDE_CAR.read_text(encoding="utf-8").strip(), "manifest sidecar")
    if expected_manifest_sha is not None and _sha256(expected_manifest_sha, "--manifest-sha") != recorded_sha:
        raise SystemExit("manifest SHA-256 does not match the pinned --manifest-sha")
    observed_sha = ca.sha256_file(MANIFEST)
    if observed_sha != recorded_sha:
        raise SystemExit(
            f"manifest sidecar sha mismatch: {recorded_sha!r} vs manifest {observed_sha}"
        )
    ca.assert_manifest_sha(MANIFEST, recorded_sha)
    if manifest["status"] != ca.STATUS_AWAITING_GO:
        raise SystemExit(
            "manifest v3 status is not awaiting the campaign go; the runner "
            "refuses to start"
        )
    preflight = _assert_registered_inputs(manifest)
    ca.assert_preflight_v4_pass(preflight)
    ca.assert_backend_ids(manifest)
    ca.assert_no_legacy_backend(manifest)
    ca.assert_compiled_objective_sense(manifest)
    ca.assert_fresh_output_directory(output_dir)
    return manifest


def run_campaign(output_dir: Path, *, expected_manifest_sha: str | None = None) -> dict:
    """Run the two-phase campaign under manifest v3's registered schedule."""
    verify_preconditions(output_dir, expected_manifest_sha=expected_manifest_sha)

    raise NotImplementedError(
        "campaign body is not implemented; preconditions were verified but "
        "no campaign output was created"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b campaign runner")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--manifest-sha", default=None,
                        help="pinned manifest sha256; required for --run")
    args = parser.parse_args()
    if args.verify_preconditions:
        manifest = verify_preconditions(Path(args.output), expected_manifest_sha=args.manifest_sha)
        print(json.dumps({"status": "preconditions_ok", "manifest_status": manifest["status"]}))
        return
    if args.run:
        if args.manifest_sha is None:
            raise SystemExit("--run requires a pinned --manifest-sha")
        run_campaign(Path(args.output), expected_manifest_sha=args.manifest_sha)
        return
    raise SystemExit("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
