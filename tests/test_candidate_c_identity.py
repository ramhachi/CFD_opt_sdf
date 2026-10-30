from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfd_sdf.candidate_c_identity import (
    CONTRACT_RELATIVE_PATH,
    CandidateCIdentityError,
    load_candidate_c_identity,
)
import cfd_sdf.candidate_c_identity as identity


def test_candidate_c_identity_fails_closed_until_frozen_contract_exists(tmp_path: Path):
    with pytest.raises(CandidateCIdentityError, match="required"):
        load_candidate_c_identity(tmp_path)


def test_candidate_c_identity_requires_exact_flags_and_hash_sidecar(tmp_path: Path, monkeypatch):
    path = tmp_path / CONTRACT_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    sources = {}
    for key, (relative, _) in identity.PINNED_SOURCES.items():
        source = tmp_path / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(key.encode())
        sources[key] = (relative, hashlib.sha256(key.encode()).hexdigest())
    monkeypatch.setattr(identity, "PINNED_SOURCES", sources)
    contract = {
        "immutable": True,
        "status": "identity_frozen_not_physical_qualification",
        "registered_before_downstream_measurement": True,
        "operator": {
            "identity": "candidate_c_moment_blend+normal_floor_0.25",
            "candidate_c_body_source": {
                "path": sources["candidate_c_body_source"][0],
                "sha256": sources["candidate_c_body_source"][1],
            },
            "normal_floor_body_source": {
                "path": sources["normal_floor_body_source"][0],
                "sha256": sources["normal_floor_body_source"][1],
            },
            "normal_floor": 0.25,
            "transition_width_solver": 1.1444091796875e-4,
            "simulation_body": "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid)+moving_ground)",
            "force_integration_body": "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))",
        },
        "qualification_flags": {
            "shape_update_allowed": False,
            "fd_oracle": False,
            "field_gradient": False,
            "reverse": False,
            "optimizer": False,
            "topology": False,
        },
    }
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(payload)
    path.with_suffix(path.suffix + ".sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")
    assert load_candidate_c_identity(tmp_path)["operator_identity"] == identity.OPERATOR_IDENTITY

    contract["qualification_flags"]["fd_oracle"] = 0
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(payload)
    path.with_suffix(path.suffix + ".sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")
    with pytest.raises(CandidateCIdentityError, match="literal false"):
        load_candidate_c_identity(tmp_path)
