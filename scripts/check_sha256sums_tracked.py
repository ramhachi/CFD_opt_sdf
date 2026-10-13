#!/usr/bin/env python3
"""Gate for evidence manifests: every SHA256SUMS entry must exist, hash correctly and be tracked by git (not ignored).

Usage: check_sha256sums_tracked.py <SHA256SUMS> [--root DIR] [--except PATH ...]   (exit 1 and the list of problems otherwise)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path


def check(manifest: Path, root: Path, excepted: tuple[str, ...] = ()) -> list[str]:
    """Entries are repo-root relative, except names starting with './' which are relative to the manifest's own directory (the older manifests)."""
    root = Path(root).resolve()
    here = Path(manifest).resolve().parent.relative_to(root)
    entries = []
    for line in Path(manifest).read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            name = name.strip()
            rel = os.path.normpath(os.path.join(here, name) if name.startswith("./") else name)
            if os.path.isabs(rel) or rel.startswith(".."):
                raise ValueError(f"unsafe manifest path: {name}")
            entries.append((digest, name, rel))
    tracked = set(subprocess.run(["git", "--literal-pathspecs", "-C", str(root), "ls-files", "--", *[r for _, _, r in entries]], capture_output=True, text=True, check=True).stdout.splitlines())
    problems = []
    for digest, name, rel in entries:
        if name in excepted or rel in excepted:
            continue
        path = root / rel
        if not path.is_file():
            problems.append(f"missing: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"hash mismatch: {name}")
        if rel not in tracked:
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
