#!/usr/bin/env python3
"""Immutable, fixed-set inventory v2 for the SDF-native architecture line.

Supersession reason: the v1 generator enumerated a live glob
(``src/cfd_sdf/**``, ``scripts/**``, sdf-pattern tests) and compared the
whole live tree against the registration snapshot, so any legitimate
downstream addition (a new contract module or test) failed ``--verify``
even though no registered byte had changed.  The v1 artifact and its
generator stay untouched (append-only); this script mints the successor:

- ``--register`` writes ``docs/evidence/repo_inventory_sdf_native_v2.json``
  exactly once (refuses overwrite), hashing the same discovery globs;
- ``--verify`` replays the *registered* fixed set: every recorded file must
  still exist with the recorded sha256, and the recorded symbol inventories
  must still parse to the recorded symbols.  Files added after registration
  do not fail verification; they require the next append-only registration.

Reads files and hashes them only; never starts a solver or mutates
existing evidence.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FORK_BASE_COMMIT = "ebdd01f293636b2fc736885a1032d466e6632e9a"
REPOSITORY = "https://github.com/ramhachi/CFD_opt_sdf.git"
OUTPUT = ROOT / "docs/evidence/repo_inventory_sdf_native_v2.json"
SUPERSEDED = ROOT / "docs/evidence/repo_inventory_sdf_native_v1.json"
TEST_PATTERN = re.compile(r"geometry|openfoam|adjoint|sdf|(^|_)fd(_|$)|directional|perturbation")
SDF_SYMBOL_MODULES = (
    "src/cfd_sdf/sdf.py",
    "src/cfd_sdf/design/sdf_state.py",
    "src/cfd_sdf/design/genesis.py",
)
ASSETS: tuple[tuple[str, str], ...] = (
    ("v16_candidate_stl", "docs/evidence/assets/stage_v_v16_physical_profile_v2/v16_candidate_threshold_0p5.iso_surface.stl"),
    ("v16_physical_profile_contract_v2", "docs/evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json"),
    ("v16_physical_profile_expanded_domain_v2", "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json"),
    ("v16_physical_profile_domain_convergence_result", "docs/evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json"),
    ("v16_candidate_lineage_v2", "docs/evidence/stage_v_v16_physical_profile_candidate_lineage_v2_2026_09.json"),
    ("stage_s_reduced_basis_fd_manifest_v1", "docs/evidence/stage_s_reduced_basis_fd_manifest_2026_09.json"),
    ("stage_s_reduced_basis_mode_preflight_v1", "docs/evidence/stage_s_reduced_basis_mode_preflight_2026_09.json"),
    ("stage_s_reduced_basis_fd_v2_manifest", "docs/evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json"),
    ("stage_s_reduced_basis_fd_v2_preflight", "docs/evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json"),
)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_path(path)


def _artifact(role: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"inventory input is missing: {relative}")
    return {"role": role, "path": relative, "sha256": _sha256(path)}


def _files(*patterns: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                entries.append({"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)})
    return sorted(entries, key=lambda entry: entry["path"])


def _symbols(relative: str) -> dict[str, list[str]]:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    return {
        "classes": sorted(node.name for node in tree.body if isinstance(node, ast.ClassDef)),
        "functions": sorted(
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
    }


def _documents() -> dict[str, Any]:
    tests = [
        entry
        for entry in _files("tests/test_*.py")
        if TEST_PATTERN.search(Path(entry["path"]).stem)
    ]
    superseded = json.loads(SUPERSEDED.read_text(encoding="utf-8"))
    return {
        "kind": "repo_inventory_sdf_native_v2",
        "schema_version": 1,
        "immutable": True,
        "repository": REPOSITORY,
        "fork_base_commit": FORK_BASE_COMMIT,
        "supersedes": {
            "path": "docs/evidence/repo_inventory_sdf_native_v1.json",
            "sha256": _sha256(SUPERSEDED),
            "reason": "the v1 live-glob verification cannot accept append-only code additions; v2 verifies the registered fixed set",
        },
        "source_modules": _files("src/cfd_sdf/**/*.py"),
        "scripts": _files("scripts/**/*.py"),
        "tests_sdf_native_relevant": tests,
        "sdf_symbols": {relative: _symbols(relative) for relative in SDF_SYMBOL_MODULES},
        "assets": [_artifact(role, relative) for role, relative in ASSETS],
        "solver_started": False,
        "existing_evidence_modified": False,
    }


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(payload, encoding="utf-8", newline="\n")
    digest = _sha256(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"inventory sidecar mismatch: {sidecar.relative_to(ROOT)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8", newline="\n")
    return digest


def register() -> dict[str, Any]:
    if OUTPUT.exists():
        raise SystemExit("repo inventory v2 already exists; refuse overwrite")
    documents = _documents()
    digest = _write_immutable(OUTPUT, documents)
    result = {
        "status": "registered",
        "inventory": OUTPUT.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "solver_started": False,
    }
    print(json.dumps(result, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    if not OUTPUT.is_file():
        raise SystemExit("repo inventory v2 is missing")
    stored = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for key in ("source_modules", "scripts", "tests_sdf_native_relevant", "assets"):
        for entry in stored.get(key, []):
            path = ROOT / entry["path"]
            if not path.is_file():
                raise SystemExit(f"registered inventory entry is missing: {entry['path']}")
            if _sha256(path) != entry["sha256"]:
                raise SystemExit(
                    f"registered inventory entry changed since registration: {entry['path']}"
                )
    for relative, recorded in stored.get("sdf_symbols", {}).items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"registered symbol module is missing: {relative}")
        live_symbols = _symbols(relative)
        if (
            recorded.get("classes") != live_symbols.get("classes")
            or recorded.get("functions") != live_symbols.get("functions")
        ):
            raise SystemExit(f"registered symbols changed for {relative}")
    if stored.get("solver_started") is not False or stored.get(
        "existing_evidence_modified"
    ) is not False or stored.get("immutable") is not True:
        raise SystemExit("registered inventory discipline fields were altered")
    result = {
        "status": "pass",
        "inventory": OUTPUT.relative_to(ROOT).as_posix(),
        "sha256": _sha256(OUTPUT),
        "solver_started": False,
    }
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="register/verify the SDF-native repo inventory v2")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    else:
        verify()


if __name__ == "__main__":
    main()
