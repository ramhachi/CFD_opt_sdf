#!/usr/bin/env python3
"""Verify a downloaded Kaggle FD dataset against its registered criteria: exact path set, SHA-256 and size."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--criteria", type=Path, required=True)
    ap.add_argument("--local", type=Path, required=True, help="staged local dataset directory")
    ap.add_argument("--remote", type=Path, required=True, help="downloaded (unzipped) remote dataset directory")
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--create-command", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit("append-only evidence target already exists")
    criteria = json.loads(args.criteria.read_text())
    names = criteria["artifacts"]
    expected = dict(criteria["input_dataset_files"])
    manifest = names["dataset_manifest_filename"]
    criteria_name = names["dataset_criteria_filename"]
    control = {"dataset-metadata.json"}  # upload control file, not part of the solver inventory
    remote = {p.relative_to(args.remote).as_posix(): p for p in args.remote.rglob("*") if p.is_file()} 
    remote = {k: v for k, v in remote.items() if k not in control}
    local = {k: args.local / k for k in remote if (args.local / k).is_file()}
    allowed = set(expected) | {manifest, criteria_name, criteria_name + ".sha256"}
    missing = sorted(allowed - set(remote))
    extra = sorted(set(remote) - allowed)
    bad_sha = sorted(k for k, want in expected.items() if k in remote and sha256(remote[k]) != want)
    bad_size = sorted(k for k in remote if k in local and remote[k].stat().st_size != local[k].stat().st_size)
    bad_local = sorted(k for k in remote if k in local and sha256(remote[k]) != sha256(local[k]))
    inventory = {k: sha256(v) for k, v in sorted(remote.items())}
    ok = not (missing or extra or bad_sha or bad_size or bad_local)
    evidence = {
        "schema_version": 1, "kind": "fd_kaggle_dataset_remote_verification",
        "criteria_path": args.criteria.as_posix(), "criteria_file_sha256": sha256(args.criteria),
        "criteria_sha256": criteria["criteria_sha256"], "dataset_id": criteria["input_dataset_id"],
        "dataset_version": args.version, "create_command": args.create_command,
        "source_commit": criteria["source_commit"], "registered_input_file_count": len(expected),
        "remote_file_count": len(remote), "path_set_exact": not (missing or extra),
        "missing_paths": missing, "extra_paths": extra, "sha256_exact": not (bad_sha or bad_local),
        "sha256_mismatch_paths": bad_sha + bad_local, "size_exact": not bad_size,
        "size_mismatch_paths": bad_size, "remote_inventory_sha256": hashlib.sha256(
            (json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest(),
        "remote_inventory_hash_method": "SHA-256 of sorted compact JSON {remote_path: file_sha256}, followed by newline; "
                                        "dataset-metadata.json (upload control) excluded",
        "local_dataset_manifest_sha256": sha256(args.local / manifest),
        "remote_files": inventory, "verified": ok,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(sha256(args.output) + "\n")
    print(json.dumps({k: evidence[k] for k in ("verified", "remote_file_count", "path_set_exact", "sha256_exact",
                                                "size_exact", "remote_inventory_sha256")}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
