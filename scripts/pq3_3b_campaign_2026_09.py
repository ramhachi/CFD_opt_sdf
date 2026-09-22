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
import json
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


def verify_preconditions(output_dir: Path) -> dict:
    """Assert every campaign precondition; fail-closed, no outputs created."""
    if not MANIFEST.is_file():
        raise SystemExit("manifest v3 missing")
    manifest = ca.load_json(MANIFEST)
    expected_sha = ca.sha256_file(MANIFEST)
    recorded_sha = MANIFEST_SIDE_CAR.read_text(encoding="utf-8").strip()
    if expected_sha != recorded_sha:
        raise SystemExit(
            f"manifest sidecar sha mismatch: {recorded_sha!r} vs manifest {expected_sha}"
        )
    ca.assert_manifest_sha(MANIFEST, recorded_sha)
    if manifest["status"] != ca.STATUS_AWAITING_GO:
        raise SystemExit(
            "manifest v3 status is not awaiting the campaign go; the runner "
            "refuses to start"
        )
    ca.assert_preflight_v4_pass(PREFLIGHT_V4)
    ca.assert_backend_ids(manifest)
    ca.assert_no_legacy_backend(manifest)
    ca.assert_compiled_objective_sense(manifest)
    ca.assert_fresh_output_directory(output_dir)
    return manifest


def run_campaign(output_dir: Path) -> dict:
    """Run the two-phase campaign under manifest v3's registered schedule."""
    manifest = verify_preconditions(output_dir)
    from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
    from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
    from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
    from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
    from cfd_sdf.phase2_policy import evaluate_phase2 as _evaluate_phase2  # noqa: E402
    from cfd_sdf.preflight_v2 import measure_level  # noqa: E402
    from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402

    output_dir.mkdir(parents=True, exist_ok=True)
    raise NotImplementedError(
        "campaign body executes only after the explicit user go artifact is "
        "registered; the runner implementation is intentionally static in "
        "this slice"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b campaign runner")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "work" / "pq3_3b_campaign"))
    parser.add_argument("--manifest-sha", default=None,
                        help="expected manifest sha256; defaults to the sidecar")
    args = parser.parse_args()
    if args.verify_preconditions:
        manifest = verify_preconditions(Path(args.output))
        print(json.dumps({"status": "preconditions_ok", "manifest_status": manifest["status"]}))
        return
    if args.run:
        run_campaign(Path(args.output_dir))
        return
    raise SystemExit("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
