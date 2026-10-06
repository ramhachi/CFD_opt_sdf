"""Fail-closed checks for registered FD-08 v2 input and state inventories."""

import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_fd08_v2_r6 import (
    verify_registered_dataset,
    verify_registered_state_inventory,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_dataset_verifier_binds_exact_input_bytes_and_manifest(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    data = b"registered state"
    criteria_blob = b'{"kind":"fd08_v2_r6_calibration"}\n'
    criteria_sha = _sha(criteria_blob)
    sidecar = (criteria_sha + "\n").encode()
    (dataset / "state.bin").write_bytes(data)
    (dataset / "criteria.json").write_bytes(criteria_blob)
    (dataset / "criteria.json.sha256").write_bytes(sidecar)
    registered = {
        "state.bin": _sha(data),
        "criteria.json": criteria_sha,
        "criteria.json.sha256": _sha(sidecar),
    }
    manifest = {
        "criteria_sha256": criteria_sha,
        "files": registered,
    }
    manifest_blob = json.dumps(manifest, sort_keys=True).encode()
    (dataset / "fd08_v2_dataset_manifest.json").write_bytes(manifest_blob)
    (dataset / "dataset-metadata.json").write_text("upload control file")
    criteria = {"dataset_files": {"state.bin": _sha(data)}}

    assert verify_registered_dataset(dataset, criteria, criteria_sha) == _sha(manifest_blob)

    (dataset / "unexpected.bin").write_bytes(b"unregistered")
    with pytest.raises(ValueError, match="inventory mismatch"):
        verify_registered_dataset(dataset, criteria, criteria_sha)


def test_state_verifier_rejects_unexpected_directories_and_done_count(tmp_path):
    output = tmp_path / "output"
    state_root = output / "states"
    (state_root / "baseline").mkdir(parents=True)
    (state_root / "plus").mkdir()
    rows = [{"name": "baseline"}, {"name": "plus"}]
    for row in rows:
        (state_root / row["name"] / "state_result.json").write_text("{}")
    criteria = {"state_inventory": rows}
    result = {
        "state_count": 2,
        "expected_state_count": 2,
        "states": {
            name: {"state_name": name, "status": "COMPLETE"}
            for name in ("baseline", "plus")
        },
    }
    done = {"file_count": 1}
    manifest = {"result.json": _sha(b"result")}

    verify_registered_state_inventory(output, criteria, result, done, manifest)

    (state_root / "unexpected").mkdir()
    with pytest.raises(ValueError, match="state directories mismatch"):
        verify_registered_state_inventory(output, criteria, result, done, manifest)

    (state_root / "unexpected").rmdir()
    done["file_count"] = 2
    with pytest.raises(ValueError, match="DONE file count"):
        verify_registered_state_inventory(output, criteria, result, done, manifest)
