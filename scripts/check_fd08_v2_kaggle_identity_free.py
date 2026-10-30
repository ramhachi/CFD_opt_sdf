#!/usr/bin/env python3
"""Fail unless the intended Kaggle kernel/dataset slugs are unused (kernel and dataset titles share one slug namespace).

Run BEFORE creating the dataset: afterwards the dataset itself is (correctly) reported as used."""
import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def kaggle(*args):
    done = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=600)
    return done.returncode, done.stdout, done.stderr


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner", default="ramhachi888")
    p.add_argument("--slug", action="append", required=True, help="intended slug (kernel or dataset)")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if len(set(args.slug)) != len(args.slug):
        sys.exit("intended slugs must be pairwise distinct (a kernel and dataset may not share one)")
    if args.output.exists():
        sys.exit("refusing to overwrite evidence")
    version = kaggle("--version")[1].strip()
    if "2.2.4" not in version:
        sys.exit(f"pinned Kaggle CLI 2.2.4 required, got {version!r}")
    mine = {}
    for kind in ("kernels", "datasets"):
        code, out, err = kaggle(kind, "list", "-m", "--page-size", "200", "--format", "csv")
        if code:
            sys.exit(f"{kind} list failed: {err.strip()}")
        mine[kind] = list(csv.DictReader(io.StringIO(out)))
        if len(mine[kind]) >= 100:  # CLI 2.2.4 clamps a list page to 100; no paging here, so refuse to guess
            sys.exit(f"{kind} listing may be truncated ({len(mine[kind])} rows); add paging before trusting this check")
    taken = {}
    for kind, rows in mine.items():
        for row in rows:
            ref = (row.get("ref") or "").split("/")[-1]
            for s in (ref, slug(row.get("title", ""))):
                if s:
                    taken.setdefault(s, set()).add(kind)
    probes, clashes = {}, {}
    for s in args.slug:
        probes[s] = {}
        for kind in ("kernels", "datasets"):
            code, out, err = kaggle(kind, "status", f"{args.owner}/{s}")
            # a missing item must not look like an existing one; record the raw outcome
            probes[s][kind] = {"exit_code": code, "stdout": out.strip()[:300], "stderr": err.strip()[:300]}
        if s in taken:
            clashes[s] = sorted(taken[s])
    result = {"kind": "fd08_v2_kaggle_identity_free_check", "captured_utc": datetime.now(timezone.utc).isoformat(),
              "cli_version": version, "owner": args.owner, "intended_slugs": args.slug,
              "owned_kernel_count": len(mine["kernels"]), "owned_dataset_count": len(mine["datasets"]),
              "listed_slug_clashes": clashes, "status_probes": probes, "all_free": not clashes}
    data = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    args.output.write_bytes(data)
    args.output.with_name(args.output.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(json.dumps({"all_free": result["all_free"], "listed_slug_clashes": clashes}))
    sys.exit(0 if result["all_free"] else 1)


if __name__ == "__main__":
    main()
