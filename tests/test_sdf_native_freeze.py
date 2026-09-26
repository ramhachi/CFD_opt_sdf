"""The architecture fork and legacy Stage S freeze must stay verifiable."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_V1 = ROOT / "docs/evidence/repo_inventory_sdf_native_v1.json"
INVENTORY_V2 = ROOT / "docs/evidence/repo_inventory_sdf_native_v2.json"
SUPERSESSION = ROOT / "docs/evidence/stage_s_reduced_basis_fd_v2_supersession_2026_09.json"
REGISTRATION = ROOT / "docs/evidence/sdf_native_architecture_registration_2026_09.json"


def _run(script: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--verify"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "pass"
    assert payload["solver_started"] is False
    return payload


def _sha256_path(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_registered_inventories_are_byte_frozen_to_their_sidecars():
    for inventory in (INVENTORY_V1, INVENTORY_V2):
        assert inventory.is_file(), f"missing {inventory.name}"
        sidecar = inventory.with_suffix(inventory.suffix + ".sha256")
        assert sidecar.read_text(encoding="utf-8").strip() == _sha256_path(inventory)


def test_architecture_registration_is_reproducible():
    _run("register_sdf_native_architecture_2026_09.py")


def test_legacy_stage_s_is_superseded_without_editing_evidence():
    record = json.loads(SUPERSESSION.read_text(encoding="utf-8"))
    assert record["status"] == "superseded_reference"
    assert record["existing_evidence_modified"] is False
    assert record["s2_campaign_started"] is False
    assert record["preserved_flags"]["reduced_basis_fd_qualified"] == "pending"
    assert record["preserved_flags"]["shape_update_allowed"] is False


def test_registration_keeps_all_conservative_flags_false():
    record = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    assert record["solver_started"] is False
    assert record["cdf_campaign_started"] is False
    for flag in (
        "shape_update_allowed",
        "sdf_gradient_qualified",
        "waterlily_reverse_cpu_qualified",
        "waterlily_reverse_cuda_qualified",
        "topology_birth_qualified",
    ):
        assert record["flags"][flag] is False
    assert record["waterlily"]["pull_request"] == 285
    assert record["waterlily"]["state"] == "open"
