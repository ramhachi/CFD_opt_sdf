#!/usr/bin/env python3
"""Gate for evidence manifests: every SHA256SUMS entry must exist, hash correctly and be tracked by git (not ignored).

Usage: check_sha256sums_tracked.py <SHA256SUMS> [--root DIR] [--except PATH ...]   (exit 1 and the list of problems otherwise)
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


def check(manifest: Path, root: Path, excepted: tuple[str, ...] = ()) -> list[str]:
    entries = []
    for line in Path(manifest).read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            entries.append((digest, name.strip()))
    tracked = set(subprocess.run(["git", "-C", str(root), "ls-files", "--", *[n for _, n in entries]], capture_output=True, text=True, check=True).stdout.splitlines())
    problems = []
    for digest, name in entries:
        if name in excepted:
            continue
        path = Path(root) / name
        if not path.is_file():
            problems.append(f"missing: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"hash mismatch: {name}")
        if name not in tracked:
            problems.append(f"not tracked by git (ignored or uncommitted): {name}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--except", dest="excepted", nargs="*", default=[])
    args = ap.parse_args()
    problems = check(args.manifest, args.root, tuple(args.excepted))
    print("\n".join(problems) if problems else f"ok: {args.manifest}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
