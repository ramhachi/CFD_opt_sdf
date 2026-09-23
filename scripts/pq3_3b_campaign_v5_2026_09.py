"""Resume PQ3.3b from the v4 b=8 accepted checkpoint under a new FD bracket.

This wrapper preserves the v4 run and its manifest. It verifies the old
checkpoint/outcome, creates a new output and seeds the v4 campaign engine with
the eight already accepted b=8 iterations. Only --run starts OpenFOAM.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts import pq3_3b_campaign_v4_2026_09 as base  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v5_2026_09.json"
PREVIOUS_OUTPUT = ROOT / "work/pq3_3b_campaign_v4"


def verify_bootstrap(manifest_sha: str) -> tuple[dict, Path, dict, np.ndarray]:
    """Read-only verification of the new registration and its source chain."""
    base.MANIFEST = MANIFEST
    manifest, output = base.verify_preconditions(manifest_sha, resume=False)
    if manifest.get("kind") != "pq3_3b_campaign_manifest_v5":
        raise ValueError("not the registered continuation manifest")
    if ca.sha256_file(ROOT / "scripts/pq3_3b_campaign_v4_2026_09.py") != manifest["base_runner_sha256"]:
        raise ValueError("base campaign engine changed after continuation registration")
    recovery_path = base._path(manifest["bracket_recovery"])
    if ca.sha256_file(recovery_path) != manifest["bracket_recovery"]["sha256"]:
        raise ValueError("bracket recovery evidence hash mismatch")
    recovery = ca.load_json(recovery_path)
    epsilon = manifest["path_b"]["epsilon"]
    if not recovery.get("at_least_two_passing_stable_slopes") or not any(
        item["epsilon"] == epsilon and item["candidate"]["accepted"]
        for item in recovery["candidates"]
    ):
        raise ValueError("new epsilon lacks an accepted, stable bracket diagnostic")
    outcome_path = base._path(manifest["source_campaign_outcome"])
    if ca.sha256_file(outcome_path) != manifest["source_campaign_outcome"]["sha256"]:
        raise ValueError("source campaign outcome hash mismatch")
    outcome = ca.load_json(outcome_path)
    previous_meta = ca.load_json(PREVIOUS_OUTPUT / "campaign_meta.json")
    if previous_meta != outcome["status"] or previous_meta.get("reason") != "objective_rejected":
        raise ValueError("source campaign stop state changed")
    for name, expected in (
        ("campaign_meta.json", outcome["output_hashes"]["campaign_meta_json"]),
        ("events.jsonl", outcome["output_hashes"]["events_jsonl"]),
        ("latest.json", outcome["output_hashes"]["latest_json"]),
    ):
        if ca.sha256_file(PREVIOUS_OUTPUT / name) != expected:
            raise ValueError(f"source campaign {name} differs from frozen outcome")
    state, rho = base._load_checkpoint(PREVIOUS_OUTPUT)
    if (state["level_index"], state["accepted_count"]) != (1, 8):
        raise ValueError("source checkpoint is not the eighth b=8 accepted state")
    if state["checkpoint_index"] != outcome["checkpoint"]["index"] or state["metrics"] != outcome["checkpoint"]["last_metrics"]:
        raise ValueError("source checkpoint history differs from frozen outcome")
    if state["rho_sha256"] != outcome["checkpoint"]["rho_sha256"]:
        raise ValueError("source checkpoint and immutable outcome disagree")
    snapshot = ca.load_json(base._path(manifest["input_checkpoint"]))
    if snapshot["source_rho_sha256"] != state["rho_sha256"] or base.sha256_array(np.asarray(snapshot["rho"], dtype=np.float64)) != state["rho_sha256"]:
        raise ValueError("bootstrap rho differs from the verified source checkpoint")
    if recovery["input_checkpoint_rho_sha256"] != state["rho_sha256"]:
        raise ValueError("bracket recovery tested a different source checkpoint")
    if outcome["levels"][0]["converged"] is not True or outcome["levels"][1]["accepted"] != 8:
        raise ValueError("source campaign did not qualify the bootstrap history")
    return manifest, output, state, rho


def run(manifest_sha: str) -> dict:
    manifest, output, previous, rho = verify_bootstrap(manifest_sha)
    output.mkdir(parents=True)
    shutil.copytree(base._path(manifest["template_trial"]), output / "template_trial")
    base._write_json_atomic(output / "campaign_meta.json", {"manifest_sha256": manifest_sha, "status": "running"})
    state = {
        "checkpoint_index": 0,
        "level_index": 1,
        "accepted_count": 8,
        "metrics": previous["metrics"],
        "completed_levels": [manifest["levels"][0]["name"]],
        "phase1_done": True,
        "last_trial_objective": previous["last_trial_objective"],
        "last_trial_downforce": previous["last_trial_downforce"],
        "source_campaign_rho_sha256": previous["rho_sha256"],
    }
    base._checkpoint(output, state, rho)
    return base.run_campaign(manifest_sha, resume=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v5 continuation")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--manifest-sha", required=True)
    args = parser.parse_args()
    if args.verify_preconditions:
        if args.resume:
            base.MANIFEST = MANIFEST
            manifest, output = base.verify_preconditions(args.manifest_sha, resume=True)
        else:
            manifest, output, _, _ = verify_bootstrap(args.manifest_sha)
        print(json.dumps({"status": "preconditions_ok", "manifest": manifest["kind"], "output": str(output)}))
    elif args.run:
        if args.resume:
            base.MANIFEST = MANIFEST
            print(json.dumps(base.run_campaign(args.manifest_sha, resume=True)))
        else:
            print(json.dumps(run(args.manifest_sha)))
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
