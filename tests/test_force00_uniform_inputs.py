"""Registered geometry/placement provenance for the CPU closure runner."""
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location("force00_uniform_inputs", ROOT / "scripts/force00_uniform_inputs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_registered_parent_and_all_phases():
    data = module().inputs()
    assert data["shape"] == [121, 65, 49]
    assert data["spacing_m"] == 0.025
    assert len(data["placements"]) == 40
    assert len(data["sphere_placements"]) == 8
    registered = data["placements"][:32]
    assert {row["phase_id"] for row in registered} == {f"{i}{s}" for i in range(49, 65) for s in "mp"}
    shifts = {row["phase_id"]: row["shift_m"] for row in registered}
    for i in range(49, 65):
        assert shifts[f"{i}m"] == [-x for x in shifts[f"{i}p"]]
    assert all(row["shift_m"][:2] == [0.0, 0.0] for row in data["placements"][32:])
    assert data["planform_area_m2"] > 0.64


def test_registered_hash_rejects_tampering(tmp_path):
    mod = module()
    path = tmp_path / "raw"
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        mod.verified(path, "0" * 64)
