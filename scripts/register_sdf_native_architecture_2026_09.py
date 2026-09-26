#!/usr/bin/env python3
"""Register the SDF-native architecture fork and freeze legacy Stage S.

Solver-free.  Appends two immutable records:

- ``stage_s_reduced_basis_fd_v2_supersession_2026_09.json`` marks the K=16
  B-spline reduced-basis path as ``superseded_reference`` without touching
  any existing manifest or evidence;
- ``sdf_native_architecture_registration_2026_09.json`` binds the fork base
  commit, the handoff bundle, the new contracts and the conservative flags.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FORK_BASE_COMMIT = "ebdd01f293636b2fc736885a1032d466e6632e9a"
FORK_BASE_BRANCH = "feat/p0-openfoam-closed-loop"
BUNDLE_DIR = ROOT / "docs/CFD_opt_sdf_SDF_native_handoff"
SUPERSESSION = ROOT / "docs/evidence/stage_s_reduced_basis_fd_v2_supersession_2026_09.json"
REGISTRATION = ROOT / "docs/evidence/sdf_native_architecture_registration_2026_09.json"
INVENTORY = ROOT / "docs/evidence/repo_inventory_sdf_native_v1.json"
V2_MANIFEST = ROOT / "docs/evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json"
V2_PREFLIGHT = ROOT / "docs/evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json"
MODULES = (
    "src/cfd_sdf/design/sdf_state.py",
    "src/cfd_sdf/oracles/base.py",
    "src/cfd_sdf/gradients/base.py",
    "src/cfd_sdf/runtime/fingerprint.py",
    "src/cfd_sdf/canonical_objective.py",
)
FLAGS: dict[str, Any] = {
    "shape_update_allowed": False,
    "sdf_gradient_qualified": False,
    "waterlily_reverse_cpu_qualified": False,
    "waterlily_reverse_cuda_qualified": False,
    "topology_birth_qualified": False,
    "topology_birth_implemented": False,
}
WATERLILY_PR = {
    "repository": "https://github.com/WaterLily-jl/WaterLily.jl",
    "pull_request": 285,
    "title": "Reverse AD via Enzyme extension",
    "head_sha": "feed49f480b52047b4e9b8bfacdf3e4f8201106b",
    "state": "open",
    "verified_on": "2026-09-26",
    "role": "experimental_cpu_reverse_ad_poc_only",
    "gpu_reverse_status": "blocked_missing_cuda_driver_rule_cuMemcpyHtoDAsync_v2",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {path.relative_to(ROOT)}")
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}


def _bundle_files() -> list[dict[str, str]]:
    sums = (BUNDLE_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8")
    entries: list[dict[str, str]] = []
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        path = BUNDLE_DIR / name.strip()
        if not path.is_file() or _sha256(path) != digest:
            raise SystemExit(f"handoff bundle checksum failed: {name}")
        entries.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest})
    if not entries:
        raise SystemExit("handoff bundle checksum list is empty")
    return sorted(entries, key=lambda entry: entry["path"])


def _supersession_document() -> dict[str, Any]:
    return {
        "kind": "stage_s_reduced_basis_fd_v2_supersession",
        "schema_version": 1,
        "immutable": True,
        "status": "superseded_reference",
        "superseded_by": "sdf_native_architecture_v1",
        "reason": "canonical design representation changes from B-spline control points to an SDF field",
        "preserved_artifacts": [
            {**_artifact(V2_MANIFEST), "role": "v2_contract"},
            {**_artifact(V2_PREFLIGHT), "role": "s0r_s1r_preflight"},
        ],
        "existing_evidence_modified": False,
        "s2_campaign_started": False,
        "preserved_flags": {
            "reduced_basis_fd_qualified": "pending",
            "shape_update_allowed": False,
            "original_adjoint_derivative_qualified": False,
        },
        "claims_not_supported": [
            "the S0R/S1R pass is geometry/morpher evidence only; no flow response was evaluated",
            "a qualified reduced-basis FD gradient, shape update, or S2-S5 result does not exist",
            "this supersession record changes no existing manifest or evidence",
        ],
    }


def _registration_document(supersession_digest: str) -> dict[str, Any]:
    return {
        "kind": "sdf_native_architecture_registration",
        "schema_version": 1,
        "immutable": True,
        "status": "registered",
        "architecture_id": "sdf_native_v1",
        "repository": "https://github.com/ramhachi/CFD_opt_sdf.git",
        "fork_base_commit": FORK_BASE_COMMIT,
        "fork_base_branch": FORK_BASE_BRANCH,
        "canonical_design_state": {
            **_artifact(ROOT / MODULES[0]),
            "module": MODULES[0],
            "sign_convention": "phi < 0 solid",
        },
        "contracts": {
            "oracle": _artifact(ROOT / MODULES[1]),
            "gradient": _artifact(ROOT / MODULES[2]),
            "runtime_fingerprint": _artifact(ROOT / MODULES[3]),
            "canonical_semantics": {
                **_artifact(ROOT / MODULES[4]),
                "objective": "f = -CDF",
                "efficiency": "g_R = R_min*CD - CDF <= 0",
                "volume": "g_V = V/V_max - 1 <= 0",
            },
        },
        "handoff_bundle": {
            "path": BUNDLE_DIR.relative_to(ROOT).as_posix(),
            "sha256sums_verified": True,
            "files": _bundle_files(),
        },
        "legacy_stage_s": {
            "supersession": {"path": SUPERSESSION.relative_to(ROOT).as_posix(), "sha256": supersession_digest},
            "s2_campaign_started": False,
            "existing_evidence_modified": False,
        },
        "repo_inventory": _artifact(INVENTORY),
        "waterlily": WATERLILY_PR,
        "registration_script": _artifact(Path(__file__)),
        "solver_started": False,
        "cdf_campaign_started": False,
        "flags": dict(FLAGS),
        "claims_not_supported": [
            "no SDF gradient, WaterLily primal, reverse-AD, topology-birth, or optimizer qualification",
            "the old K=16 reduced-basis S2 campaign is intentionally not started",
            "no absolute, grid-independent, high-Re, or full-vehicle downforce claim",
        ],
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
        raise SystemExit(f"sidecar mismatch: {sidecar.relative_to(ROOT)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8", newline="\n")
    return digest


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required JSON is missing: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def register() -> dict[str, Any]:
    if SUPERSESSION.exists() or REGISTRATION.exists():
        raise SystemExit("SDF-native architecture registration already exists; refuse overwrite")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    if head != FORK_BASE_COMMIT:
        raise SystemExit(
            f"architecture fork must be registered from base {FORK_BASE_COMMIT}; current HEAD is {head}"
        )
    for relative in MODULES:
        if not (ROOT / relative).is_file():
            raise SystemExit(f"required module is missing: {relative}")
    if not INVENTORY.is_file():
        raise SystemExit("repo inventory must be registered before the architecture registration")
    supersession_digest = _write_immutable(SUPERSESSION, _supersession_document())
    registration_digest = _write_immutable(
        REGISTRATION, _registration_document(supersession_digest)
    )
    result = {
        "status": "registered",
        "supersession_sha256": supersession_digest,
        "registration_sha256": registration_digest,
        "solver_started": False,
    }
    print(json.dumps(result, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    document = _load(REGISTRATION)
    if document.get("fork_base_commit") != FORK_BASE_COMMIT or document.get("status") != "registered":
        raise SystemExit("SDF-native architecture registration has the wrong base or status")
    supersession = _load(SUPERSESSION)
    if document["legacy_stage_s"]["supersession"]["sha256"] != _sha256(SUPERSESSION):
        raise SystemExit("supersession sidecar changed after registration")
    if supersession.get("status") != "superseded_reference":
        raise SystemExit("legacy Stage S is not marked superseded_reference")
    for name, ref in document["contracts"].items():
        if name == "canonical_semantics":
            if _sha256(ROOT / ref["path"]) != ref["sha256"]:
                raise SystemExit("registered canonical semantics changed")
        elif _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"registered contract changed: {name}")
    if _sha256(ROOT / document["canonical_design_state"]["module"]) != document["canonical_design_state"]["sha256"]:
        raise SystemExit("registered SDF design state module changed")
    if _sha256(ROOT / document["registration_script"]["path"]) != document["registration_script"]["sha256"]:
        raise SystemExit("registration script changed")
    if _sha256(INVENTORY) != document["repo_inventory"]["sha256"]:
        raise SystemExit("repo inventory changed after registration")
    if _bundle_files() != document["handoff_bundle"]["files"]:
        raise SystemExit("handoff bundle changed after registration")
    for flag, value in FLAGS.items():
        if document["flags"].get(flag) != value:
            raise SystemExit(f"conservative flag changed: {flag}")
    if _supersession_document() != supersession:
        raise SystemExit("supersession record is not reproducible")
    if _registration_document(_sha256(SUPERSESSION)) != document:
        raise SystemExit("architecture registration is not reproducible")
    result = {"status": "pass", "registration_sha256": _sha256(REGISTRATION), "solver_started": False}
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="register/verify the SDF-native architecture fork")
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
