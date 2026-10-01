import copy
import json
from pathlib import Path

import pytest

from cfd_sdf.criteria_supersession import (
    SupersessionError,
    build_successor,
    canonical_sha256,
    git_source_reader,
    validate_successor,
    verify_successor_submission,
    write_successor,
)


ROOT = Path(__file__).resolve().parents[1]
ROUND4 = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round4.json"
ROUND4_DIAGNOSTIC = ROOT / "docs/evidence/sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json"
ROUND5 = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round5.json"
ROUND5_COMMIT = "a07bba2fd1dcf0d3d28b211eef58d91309a24a75"


def _read(path):
    return json.loads(path.read_text())


def _round4_to_round5_allowlist(predecessor, expected):
    return {
        name: {
            "path": predecessor["inputs"][name]["path"],
            "reason": "Round-4 terminal diagnostic requires this source-only correction.",
        }
        for name in predecessor["inputs"]
        if predecessor["inputs"][name] != expected["inputs"][name]
    }


def _resign(criteria):
    criteria["criteria_sha256"] = canonical_sha256(criteria)


def test_historical_round4_to_round5_source_only_successor_is_accepted():
    predecessor, expected = _read(ROUND4), _read(ROUND5)
    allowlist = _round4_to_round5_allowlist(predecessor, expected)
    assert set(allowlist) == {"criteria_draft", "criteria_registrar", "harness_tests", "kernel_runner"}

    validate_successor(predecessor, expected, allowlist)
    successor = build_successor(
        ROUND4,
        ROUND4_DIAGNOSTIC,
        source_commit=ROUND5_COMMIT,
        source_reader=git_source_reader(ROOT),
        allowed_source_changes=allowlist,
        registered_at_utc=expected["registered_at_utc"],
    )

    assert successor["criteria_round"] == 5
    assert successor["supersedes"]["criteria_file_sha256"] == ROUND4.with_suffix(".json.sha256").read_text().strip()
    assert successor["supersedes"]["terminal_status"].endswith('KernelWorkerStatus.ERROR"')
    identity = successor["supersedes"]["successor_identity"]
    assert identity["kernel_version"] == {
        "status": "pending_at_registration",
        "must_be_greater_than_predecessor": 3,
    }
    dataset_files = predecessor["input_dataset_files"]
    verify_successor_submission(
        successor,
        kernel_id=identity["kernel_id"],
        kernel_version=4,
        dataset_id=identity["dataset"]["id"],
        dataset_version=identity["dataset"]["version"],
        dataset_files=dataset_files,
    )
    with pytest.raises(SupersessionError, match="version"):
        verify_successor_submission(
            successor,
            kernel_id=identity["kernel_id"],
            kernel_version=3,
            dataset_id=identity["dataset"]["id"],
            dataset_version=identity["dataset"]["version"],
            dataset_files=dataset_files,
        )
    with pytest.raises(SupersessionError, match="dataset version"):
        verify_successor_submission(
            successor,
            kernel_id=identity["kernel_id"],
            kernel_version=4,
            dataset_id=identity["dataset"]["id"],
            dataset_version=identity["dataset"]["version"] + 1,
            dataset_files=dataset_files,
        )
    assert successor["source_input_sha256"] == {
        name: entry["sha256"] for name, entry in successor["inputs"].items()
        if entry["location"] == "source_repo"
    }
    for field in ("measurement", "directions", "perturbation", "backend", "geometry", "gates", "run_order"):
        assert successor[field] == predecessor[field]


@pytest.mark.parametrize("field", ["measurement", "directions", "perturbation", "backend", "geometry", "gates", "run_order"])
def test_measurement_contract_changes_are_rejected(field):
    predecessor, successor = _read(ROUND4), _read(ROUND5)
    allowlist = _round4_to_round5_allowlist(predecessor, successor)
    changed = copy.deepcopy(successor)
    changed[field] = copy.deepcopy(changed[field])
    if isinstance(changed[field], dict):
        changed[field]["unregistered_change"] = True
    else:
        changed[field] = [*changed[field], "unregistered_change"]
    _resign(changed)
    with pytest.raises(SupersessionError, match="measurement contract"):
        validate_successor(predecessor, changed, allowlist)


def test_epsilon_change_is_rejected():
    predecessor, successor = _read(ROUND4), _read(ROUND5)
    allowlist = _round4_to_round5_allowlist(predecessor, successor)
    changed = copy.deepcopy(successor)
    changed["perturbation"]["epsilon_ladder_m"][0] *= 2
    _resign(changed)
    with pytest.raises(SupersessionError, match="measurement contract"):
        validate_successor(predecessor, changed, allowlist)


def test_wrong_predecessor_is_rejected_even_with_matching_terminal_kernel(tmp_path):
    predecessor = _read(ROUND4)
    allowlist = _round4_to_round5_allowlist(predecessor, _read(ROUND5))
    tmp = tmp_path
    criteria = tmp / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round4.json"
    diagnostic = tmp / "docs/evidence/sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json"
    criteria.parent.mkdir(parents=True)
    criteria.write_bytes(ROUND4.read_bytes())
    criteria.with_suffix(".json.sha256").write_bytes(ROUND4.with_suffix(".json.sha256").read_bytes())
    altered = _read(ROUND4_DIAGNOSTIC)
    altered["criteria_path"] = "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round3.json"
    diagnostic.write_text(json.dumps(altered))
    diagnostic.with_suffix(".json.sha256").write_text(__import__("hashlib").sha256(diagnostic.read_bytes()).hexdigest())

    with pytest.raises(SupersessionError, match="different predecessor"):
        build_successor(
            criteria,
            diagnostic,
            source_commit=ROUND5_COMMIT,
            source_reader=git_source_reader(ROOT),
            allowed_source_changes=allowlist,
            registered_at_utc="2026-10-02T00:00:00Z",
        )


def test_wrong_kernel_slug_and_unallowlisted_source_change_are_rejected():
    predecessor, successor = _read(ROUND4), _read(ROUND5)
    allowlist = _round4_to_round5_allowlist(predecessor, successor)

    wrong_slug = copy.deepcopy(successor)
    wrong_slug["kernel_title"] = "Different Kernel"
    _resign(wrong_slug)
    with pytest.raises(SupersessionError, match="kernel identity|slug"):
        validate_successor(predecessor, wrong_slug, allowlist)

    incomplete = dict(allowlist)
    incomplete.pop("kernel_runner")
    with pytest.raises(SupersessionError, match="allowed source changes"):
        validate_successor(predecessor, successor, incomplete)


def test_successor_writer_is_append_only(tmp_path):
    output = tmp_path / "round6.json"
    digest = write_successor({"criteria_round": 6}, output)
    assert output.with_suffix(".json.sha256").read_text().strip() == digest
    with pytest.raises(SupersessionError, match="append-only"):
        write_successor({"criteria_round": 6}, output)
