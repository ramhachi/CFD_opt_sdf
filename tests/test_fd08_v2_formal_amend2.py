"""Immutable supersession, scientific equality and real source/payload checks."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import pytest

from scripts import register_fd08_v2_formal_amend2 as registrar

ROOT = registrar.ROOT


def test_amend1_archive_is_exact_immutable_parent_and_has_25_unique_states():
    parent, files, _ = registrar.read_parent()
    assert hashlib.sha256(files["criteria.json"]).hexdigest() == registrar.PARENT_SHA
    assert parent["expected_state_count"] == len(parent["state_inventory"]) == 25
    assert len({files[row["phi_raw_file"]] for row in parent["state_inventory"]}) == 25
    assert sum(row["kind"] == "baseline" for row in parent["state_inventory"]) == 1
    assert parent["formal_epsilon"]["epsilon_mm"] == [0.6294627058970836, 1.5811388300841898, 3.971641173621408]


def test_actual_formal_bytes_are_disjoint_from_exact_49_calibration_inputs():
    dataset = ROOT / "work/r6_parent_v6"
    if not dataset.is_dir():
        pytest.skip("exact R6 dataset input unavailable in this checkout")
    parent, files, _ = registrar.read_parent()
    r6 = json.loads((ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_criteria.json").read_text())
    calibration = set()
    for row in r6["state_inventory"]:
        data = (dataset / row["phi_raw_file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["phi_fortran_order_sha256"]
        calibration.add(data)
    signed = {files[row["phi_raw_file"]] for row in parent["state_inventory"] if row["kind"] == "formal"}
    baseline = next(row for row in parent["state_inventory"] if row["kind"] == "baseline")
    assert len(calibration) == 49 and len(signed) == 24 and not signed.intersection(calibration)
    assert files[baseline["phi_raw_file"]] in calibration


@pytest.mark.parametrize("field", ["calibration_binding", "candidate_c_identity", "canonical_state",
    "direction_inventory", "formal_epsilon", "geometry", "state_inventory", "expected_state_count",
    "float32_centered_direction_audits", "byte_disjointness", "numeric_prediction_rule", "measurement",
    "runtime", "decision_tree", "not_claimed", "qualification_flags"])
def test_every_scientific_field_is_inside_exact_equality_check(field):
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    changed = copy.deepcopy(parent)
    changed[field] = {"intentional_contract_drift": True}
    assert registrar.scientific_content(changed) != registrar.scientific_content(parent)


def test_historical_amend1_registrar_and_payload_remain_unmodified():
    for path in ["scripts/register_fd08_v2_formal.py", *[
        p.relative_to(ROOT).as_posix() for p in registrar.PARENT.iterdir() if p.is_file()]]:
        old = subprocess.check_output(["git", "show", f"95fda3cf531e6e971b777f62eb71ce8447943465:{path}"], cwd=ROOT)
        assert (ROOT / path).read_bytes() == old


def test_identities_cannot_collide_with_either_parent():
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    r6 = json.loads((ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_criteria.json").read_text())
    assert registrar.CRITERIA_ID not in {parent["criteria_id"], r6["criteria_id"]}
    assert registrar.DATASET_ID not in {parent["input_dataset_id"], r6["input_dataset_id"]}
    assert registrar.ROUND_ID != parent["round_id"]
    metadata = json.loads((ROOT / "infra/kaggle/kernel_fd08_v2_formal_amend2/kernel-metadata.json").read_text())
    assert metadata["id"] == registrar.KERNEL_ID
    assert metadata["dataset_sources"] == [registrar.DATASET_ID]
    assert metadata["is_private"] is True


@pytest.mark.parametrize("commit", ["HEAD", registrar.PARENT_SOURCE, registrar.R6_PARENT["source_commit"]])
def test_execution_source_must_be_new_exact_commit(commit):
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    with pytest.raises(ValueError, match="new exact execution commit"):
        registrar.source_inventory(parent, commit)


@pytest.fixture(scope="module")
def candidate():
    commit = os.environ.get("FD08_V2_AMEND2_SOURCE_COMMIT")
    if not commit:
        pytest.skip("actual source-bound construction requires FD08_V2_AMEND2_SOURCE_COMMIT")
    args = argparse.Namespace(source_commit=commit, budget_evidence=ROOT / "work/amend2_validation/budget_preflight.json",
        criteria=registrar.EVIDENCE / "formal_criteria.json", preflight=registrar.EVIDENCE / "formal_preflight.json",
        dataset_dir=ROOT / "work/kaggle_fd08_v2_formal_amend2_dataset", rehearsal_evidence=None, dry_run=True)
    return registrar.build_formal(args)


def test_actual_candidate_matches_every_amend1_scientific_field_and_state_byte(candidate):
    parent, files, _ = registrar.read_parent()
    criteria = candidate["criteria"]
    assert registrar.scientific_content(criteria) == registrar.scientific_content(parent)
    assert criteria["state_inventory"] == parent["state_inventory"]
    for row in parent["state_inventory"]:
        for key in ("npz_file", "phi_raw_file"):
            assert candidate["files"][row[key]] == files[row[key]]
    assert criteria["calibration_binding"] == parent["calibration_binding"]
    assert criteria["input_dataset_id"] == candidate["metadata"]["id"] == registrar.DATASET_ID
    assert criteria["source_commit"] not in (registrar.PARENT_SOURCE, registrar.R6_PARENT["source_commit"])
    assert criteria["supersession"]["supersedes_criteria_sha256"] == registrar.PARENT_SHA
    assert criteria["supersession"]["formal_observations_before_supersession"] == 0
    assert criteria["supersession"]["solver_started_before_supersession"] is False


def test_actual_complete_mounted_payload_passes_registered_runner_state_consumer(candidate):
    path = ROOT / "infra/kaggle/kernel_fd08_v2_r6/runner.py"
    spec = importlib.util.spec_from_file_location("amend2_payload_runner", path)
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    with tempfile.TemporaryDirectory() as td:
        mount = Path(td)
        for name, data in candidate["files"].items():
            (mount / name).write_bytes(data)
        _, criteria, criteria_sha = runner.load_criteria(mount)
        runner.verify_dataset(mount, criteria, criteria_sha)
        runner.validate_state_files(mount, criteria)
        assert len(criteria["state_inventory"]) == 25


def test_fresh_actual_execution_checkout_matches_all_bound_source_inputs(candidate):
    criteria = candidate["criteria"]
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "source"
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "sparse-checkout", "set", "--no-cone",
            *sorted({entry["path"] for entry in criteria["source_inputs"].values()})], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", criteria["source_commit"]], check=True)
        for entry in criteria["source_inputs"].values():
            assert hashlib.sha256((checkout / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
