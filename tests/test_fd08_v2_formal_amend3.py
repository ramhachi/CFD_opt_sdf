"""AMEND3: kernel identity separation, immutable supersession of AMEND2, scientific equality and real source/payload checks."""
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

from scripts import register_fd08_v2_formal_amend3 as registrar

ROOT = registrar.ROOT


def test_amend2_archive_is_exact_immutable_parent_and_has_25_unique_states():
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
    "runtime", "decision_tree", "not_claimed", "qualification_flags", "dataset_manifest_file", "evidence_class",
    "immutable", "kind", "registered_before_computation", "schema_version", "status"])
def test_every_scientific_field_is_inside_exact_equality_check(field):
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    changed = copy.deepcopy(parent)
    changed[field] = {"intentional_contract_drift": True}
    assert registrar.scientific_content(changed) != registrar.scientific_content(parent)


AMEND2_FROZEN_COMMIT = "e3b2ce0853a7e94454c8073902fe88ae046ff00a"


def test_historical_amend1_and_amend2_artifacts_remain_unmodified():
    paths = ["scripts/register_fd08_v2_formal.py", "scripts/register_fd08_v2_formal_amend2.py",
             "tests/test_fd08_v2_formal_amend2.py", "infra/kaggle/kernel_fd08_v2_formal_amend2/kernel-metadata.json",
             *[p.relative_to(ROOT).as_posix() for p in registrar.PARENT.iterdir() if p.is_file()]]
    for path in paths:
        old = subprocess.check_output(["git", "show", f"{AMEND2_FROZEN_COMMIT}:{path}"], cwd=ROOT)
        assert (ROOT / path).read_bytes() == old, path


def test_identities_cannot_collide_with_either_parent():
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    r6 = json.loads((ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_criteria.json").read_text())
    assert registrar.CRITERIA_ID not in {parent["criteria_id"], r6["criteria_id"]}
    assert registrar.DATASET_ID not in {parent["input_dataset_id"], r6["input_dataset_id"]}
    assert registrar.KERNEL_ID not in {parent["kernel_id"], r6["kernel_id"]}
    assert registrar.ROUND_ID != parent["round_id"]
    metadata = json.loads((ROOT / registrar.KERNEL_METADATA).read_text())
    assert metadata["id"] == registrar.KERNEL_ID
    assert metadata["dataset_sources"] == [registrar.DATASET_ID]
    assert metadata["is_private"] is True


def test_kernel_slug_never_equals_any_dataset_slug_and_matches_title():
    """AMEND2 regression: Kaggle rejects a kernel whose title-slug is already used by a dataset (HTTP 409)."""
    registrar.check_kernel_identity()
    metadata = json.loads((ROOT / registrar.KERNEL_METADATA).read_text())
    kernel_slug = registrar.KERNEL_ID.split("/", 1)[1]
    assert kernel_slug == registrar.slug(metadata["title"])
    dataset_slugs = {registrar.DATASET_ID.split("/", 1)[1]}
    for path in (ROOT / "infra/kaggle").glob("*/dataset-metadata.json"):
        dataset_slugs.add(json.loads(path.read_text())["id"].split("/", 1)[1])
    for path in (ROOT / "docs/evidence").glob("fd08_v2_*/formal_criteria.json"):
        dataset_slugs.add(json.loads(path.read_text())["input_dataset_id"].split("/", 1)[1])
    dataset_slugs.add(json.loads((registrar.PARENT / "formal_criteria.json").read_text())["input_dataset_id"].split("/", 1)[1])
    assert kernel_slug not in dataset_slugs
    assert registrar.KERNEL_ID != registrar.DATASET_ID


def test_amend2_collision_is_the_recorded_cause_and_amend2_kernel_never_existed():
    _, _, failure_sha = registrar.read_parent()
    assert failure_sha == registrar.PARENT_FAILURE_SHA
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    assert parent["kernel_id"] == parent["input_dataset_id"]


@pytest.mark.parametrize("commit", ["HEAD", registrar.PARENT_SOURCE, *registrar.OLDER_SOURCES,
                                    registrar.R6_PARENT["source_commit"]])
def test_execution_source_must_be_new_exact_commit(commit):
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    with pytest.raises(ValueError, match="new exact execution commit"):
        registrar.source_inventory(parent, commit)


@pytest.fixture(scope="module")
def candidate():
    commit = os.environ.get("FD08_V2_AMEND3_SOURCE_COMMIT")
    if not commit:
        pytest.skip("actual source-bound construction requires FD08_V2_AMEND3_SOURCE_COMMIT")
    args = argparse.Namespace(source_commit=commit, budget_evidence=ROOT / "work/amend3_validation/budget_preflight.json",
        criteria=registrar.EVIDENCE / "formal_criteria.json", preflight=registrar.EVIDENCE / "formal_preflight.json",
        dataset_dir=ROOT / "work/kaggle_fd08_v2_formal_amend3_dataset", rehearsal_evidence=None, dry_run=True)
    return registrar.build_formal(args)


def test_actual_candidate_matches_every_amend2_scientific_field_and_state_byte(candidate):
    parent, files, _ = registrar.read_parent()
    criteria = candidate["criteria"]
    assert registrar.scientific_content(criteria) == registrar.scientific_content(parent)
    assert criteria["state_inventory"] == parent["state_inventory"]
    for row in parent["state_inventory"]:
        for key in ("npz_file", "phi_raw_file"):
            assert candidate["files"][row[key]] == files[row[key]]
    assert criteria["calibration_binding"] == parent["calibration_binding"]
    assert criteria["input_dataset_id"] == candidate["metadata"]["id"] == registrar.DATASET_ID
    assert criteria["source_commit"] not in (registrar.PARENT_SOURCE, *registrar.OLDER_SOURCES,
                                             registrar.R6_PARENT["source_commit"])
    assert criteria["kernel_id"] == registrar.KERNEL_ID != registrar.DATASET_ID
    assert criteria["supersession"]["supersedes_criteria_sha256"] == registrar.PARENT_SHA
    assert criteria["supersession"]["formal_observations_before_supersession"] == 0
    assert criteria["supersession"]["solver_started_before_supersession"] is False


def test_actual_complete_mounted_payload_passes_registered_runner_state_consumer(candidate):
    path = ROOT / "infra/kaggle/kernel_fd08_v2_r6/runner.py"
    spec = importlib.util.spec_from_file_location("amend3_payload_runner", path)
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


def test_parent_scientific_projection_is_the_pinned_hash():
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    assert hashlib.sha256(registrar.blob(registrar.scientific_content(parent))).hexdigest() == registrar.SCIENTIFIC_PROJECTION_SHA


def test_registrar_rejects_kernel_equal_to_dataset_identity(monkeypatch):
    monkeypatch.setattr(registrar, "KERNEL_ID", registrar.DATASET_ID)
    with pytest.raises(ValueError, match="kernel identity"):
        registrar.check_kernel_identity()


def test_registrar_rejects_title_slug_colliding_with_a_known_dataset(monkeypatch):
    monkeypatch.setattr(registrar, "KNOWN_DATASET_SLUGS", registrar.KNOWN_DATASET_SLUGS | {registrar.KERNEL_ID.split("/", 1)[1]})
    with pytest.raises(ValueError, match="kernel identity"):
        registrar.check_kernel_identity()


def test_source_inventory_rejects_a_change_outside_the_identity_set(monkeypatch):
    """Needs a real commit for git-show verification; the guard fires before it, on the parent comparison."""
    parent = json.loads((registrar.PARENT / "formal_criteria.json").read_text())
    parent["source_inputs"]["gate"]["sha256"] = "0" * 64
    monkeypatch.setattr(registrar, "digest", lambda path: "1" * 64)
    with pytest.raises(ValueError, match="unexpected source change"):
        registrar.source_inventory(parent, "a" * 40)
