"""Formal amendment provenance, frozen science, and actual host dry construction.

Set FD08_V2_LINEAGE_SOURCE_COMMIT to a committed candidate to enable the real
canonical/R6 payload and fresh-checkout checks. No solver or R6 analyzer runs.
"""

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

import pytest

from scripts import register_fd08_v2_formal as registrar
from cfd_sdf.fd08_v2_campaign import DIRECTION_IDS, FORMAL_EPSILON_MM, FORMAL_INTERVAL_INDICES, R6_EPSILON_MM

ROOT = registrar.ROOT
FROZEN = json.loads((registrar.EVIDENCE / "scientific_contract_frozen.json").read_text())
SCIENCE = FROZEN["scientific_contract"]


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _contract_literals(source):
    tree = ast.parse(source)
    contract = next(node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "contract" for target in node.targets))
    fields = {key.value: value for key, value in zip(contract.keys, contract.values) if key is not None}
    caps = fields["measurement"]
    return {
        "numeric_prediction_rule": ast.literal_eval(fields["numeric_prediction_rule"]),
        "decision_tree": ast.literal_eval(fields["decision_tree"]),
        "measurement_caps": {key.value: ast.literal_eval(value)
                             for key, value in zip(caps.keys, caps.values) if key is not None},
    }


def test_scientific_literals_are_equal_to_exact_pre_r6_registrar():
    original = subprocess.check_output(
        ["git", "show", f"{registrar.R6_PARENT['source_commit']}:scripts/register_fd08_v2_formal.py"], cwd=ROOT
    )
    assert _sha(original) == registrar.ORIGINAL_REGISTRAR_SHA256 == FROZEN["original_registrar_sha256"]
    amended = (ROOT / "scripts/register_fd08_v2_formal.py").read_bytes()
    before, after = _contract_literals(original), _contract_literals(amended)
    assert before == after == {key: SCIENCE[key] for key in before}


def test_frozen_epsilon_direction_params_and_scientific_sources():
    assert FORMAL_INTERVAL_INDICES == (0, 2, 4)
    assert FORMAL_EPSILON_MM == tuple(math.sqrt(R6_EPSILON_MM[i] * R6_EPSILON_MM[i + 1]) for i in (0, 2, 4))
    assert list(FORMAL_EPSILON_MM) == SCIENCE["epsilon_mm"]
    assert list(DIRECTION_IDS) == SCIENCE["direction_ids"]
    params = (ROOT / "src/cfd_sdf/fd08_v2_gate_params.json").read_bytes()
    assert json.loads(params) == SCIENCE["parameters"]
    assert _sha(params) == SCIENCE["T2_parameter_sha256"]
    parent = json.loads(registrar.DEFAULT_R6_CRITERIA.read_text())
    for name, expected in FROZEN["unchanged_source_sha256"].items():
        assert _sha((ROOT / parent["source_inputs"][name]["path"]).read_bytes()) == expected


def test_formal_artifact_defaults_and_kernel_are_separate_from_r6_and_failure():
    parent = json.loads(registrar.DEFAULT_R6_CRITERIA.read_text())
    assert registrar.CRITERIA_ID != parent["criteria_id"]
    assert registrar.DATASET_ID != parent["input_dataset_id"]
    assert registrar.DEFAULT_CRITERIA.parent == registrar.EVIDENCE
    assert registrar.EVIDENCE.name == registrar.ROUND_ID
    assert registrar.DEFAULT_CRITERIA.parent != registrar.DEFAULT_R6_CRITERIA.parent
    assert registrar.DEFAULT_CRITERIA.parent != registrar.FAILURE_EVIDENCE.parent
    assert _sha(registrar.FAILURE_EVIDENCE.read_bytes()) == registrar.FAILURE_EVIDENCE_SHA256
    metadata = json.loads((ROOT / "infra/kaggle/kernel_fd08_v2_formal_amend1/kernel-metadata.json").read_text())
    slug = re.sub(r"[^a-z0-9]+", "-", metadata["title"].lower()).strip("-")
    assert metadata["id"] == registrar.KERNEL_ID
    assert metadata["id"].split("/", 1)[1] == slug
    assert metadata["dataset_sources"] == [registrar.DATASET_ID]
    assert metadata["is_private"] is True


def test_execution_identity_rejects_r6_source_and_nonexact_git_identity():
    with pytest.raises(ValueError, match="cannot reuse R6"):
        registrar.formal_source_inventory(registrar.R6_PARENT["source_commit"])
    with pytest.raises(ValueError, match="exact Git commit"):
        registrar.formal_source_inventory("HEAD")


@pytest.fixture(scope="module")
def candidate():
    commit = os.environ.get("FD08_V2_LINEAGE_SOURCE_COMMIT")
    if not commit:
        pytest.skip("real source-bound dry construction requires FD08_V2_LINEAGE_SOURCE_COMMIT")
    dataset = Path(os.environ.get("FD08_V2_R6_DATASET_DIR", registrar.DEFAULT_R6_DATASET))
    state = Path(os.environ.get("FD08_V2_CANONICAL_STATE", registrar.DEFAULT_STATE))
    budget = Path(os.environ.get("FD08_V2_BUDGET_EVIDENCE", ROOT / "work/formal_lineage_validation/budget_preflight.json"))
    assert dataset.is_dir() and state.is_file() and budget.is_file()
    (ROOT / "work").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="formal-dry-") as temp:
        output = Path(temp)
        args = argparse.Namespace(
            state=state, r6_criteria=registrar.DEFAULT_R6_CRITERIA,
            r6_result=registrar.DEFAULT_R6_RESULT, r6_terminal=registrar.DEFAULT_R6_TERMINAL,
            r6_dataset_dir=dataset, budget_evidence=budget, source_commit=commit, dry_run=True,
            dataset_dir=output / "dataset", criteria=output / "criteria.json", preflight=output / "preflight.json",
        )
        built = registrar.build_formal(args)
        assert not args.criteria.exists() and not args.preflight.exists() and not args.dataset_dir.exists()
        yield args, built


def test_real_r6_raw_inventory_is_a_49_unique_byte_set_including_baseline(candidate):
    args, _ = candidate
    parent = registrar.read_r6_parent(args.r6_criteria, args.r6_result, args.r6_terminal, args.r6_dataset_dir)
    criteria, *_, raw_states = parent
    assert isinstance(raw_states, set) and len(raw_states) == len(criteria["state_inventory"]) == 49
    baseline = next(row for row in criteria["state_inventory"] if row["kind"] == "baseline")
    assert (args.r6_dataset_dir / baseline["phi_raw_file"]).read_bytes() in raw_states


def test_formal_execution_and_exact_parent_are_two_identities(candidate):
    args, built = candidate
    criteria = built["criteria"]
    assert criteria["source_commit"] == args.source_commit != registrar.R6_PARENT["source_commit"]
    binding = criteria["calibration_binding"]
    assert {key: binding[key] for key in registrar.R6_PARENT} == registrar.R6_PARENT
    assert binding["verdict"] == "PASS" and binding["analysis_runs"] == 1
    lineage = criteria["formal_preregistration_amendment"]
    assert lineage["original_pre_r6_registrar_sha256"] == registrar.ORIGINAL_REGISTRAR_SHA256
    assert lineage["preregistration_failure_evidence_sha256"] == registrar.FAILURE_EVIDENCE_SHA256
    assert lineage["amended_source_commit"] == args.source_commit
    assert lineage["scientific_contract_changed"] is False
    blob = subprocess.check_output(["git", "show", f"{args.source_commit}:scripts/register_fd08_v2_formal.py"], cwd=ROOT)
    assert _sha(blob) == lineage["amended_registrar_sha256"] == criteria["source_inputs"]["formal_registrar"]["sha256"]
    assert built["metadata"]["id"] == criteria["input_dataset_id"] == registrar.DATASET_ID


def test_actual_25_state_science_and_frozen_fit_copy_are_unchanged(candidate):
    _, built = candidate
    criteria = built["criteria"]
    parent = json.loads(registrar.DEFAULT_R6_CRITERIA.read_text())
    result = json.loads(registrar.DEFAULT_R6_RESULT.read_text())
    rows = criteria["state_inventory"]
    assert len(rows) == criteria["expected_state_count"] == SCIENCE["state_count"] == 25
    assert sum(row["kind"] == "baseline" for row in rows) == SCIENCE["baseline_count"] == 1
    signed = [row for row in rows if row["kind"] == "formal"]
    assert len(signed) == SCIENCE["signed_state_count"] == 24
    for direction in DIRECTION_IDS:
        for epsilon in FORMAL_EPSILON_MM:
            assert {row["sign"] for row in signed if row["direction_id"] == direction and row["epsilon_mm"] == epsilon} == {-1, 1}
    assert criteria["formal_epsilon"]["interval_indices"] == SCIENCE["interval_indices"]
    assert criteria["formal_epsilon"]["formula"] == SCIENCE["epsilon_formula"]
    assert criteria["formal_epsilon"]["epsilon_mm"] == SCIENCE["epsilon_mm"]
    assert criteria["numeric_prediction_rule"] == SCIENCE["numeric_prediction_rule"]
    assert criteria["decision_tree"] == SCIENCE["decision_tree"]
    assert {key: criteria["measurement"][key] for key in SCIENCE["measurement_caps"]} == SCIENCE["measurement_caps"]
    assert criteria["direction_inventory"]["hashes"] == parent["direction_inventory"]["hashes"]
    assert criteria["geometry"] == parent["geometry_reject_gates"]
    assert criteria["runtime"] == parent["runtime"]
    assert criteria["calibration_binding"]["T2_parameters"] == SCIENCE["parameters"]
    assert criteria["calibration_binding"]["T2_parameter_sha256"] == SCIENCE["T2_parameter_sha256"]
    assert criteria["calibration_binding"]["model"] == "A"
    for series in result["series"]:
        fit = criteria["calibration_binding"]["fits"][f"{series['direction_id']}|{series['response']}"]
        assert fit["beta_mm"] == series["model_a"]["beta"]
        assert fit["covariance_mm"] == series["model_a"]["covariance"]
    assert len({built["files"][row["phi_raw_file"]] for row in rows}) == 25
    assert criteria["byte_disjointness"]["formal_signed_disjoint_from_all_calibration_and_baseline"] is True
    assert all(value is False for value in criteria["qualification_flags"].values())


def test_fresh_checkout_passes_the_unchanged_runner_source_verification(candidate):
    args, built = candidate
    criteria = built["criteria"]
    runner_path = ROOT / "infra/kaggle/kernel_fd08_v2_r6/runner.py"
    spec = importlib.util.spec_from_file_location("formal_lineage_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with tempfile.TemporaryDirectory(prefix="formal-source-") as temp:
        checkout = Path(temp) / "source"
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(checkout)], check=True)
        paths = sorted({entry["path"] for entry in criteria["source_inputs"].values()})
        subprocess.run(["git", "-C", str(checkout), "sparse-checkout", "set", "--no-cone", *paths], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", args.source_commit], check=True)
        assert runner.verify_source(checkout, criteria, _sha(runner_path.read_bytes())) == checkout / "julia/CFDSDFWaterLilyT4"
        assert _sha((checkout / "scripts/register_fd08_v2_formal.py").read_bytes()) == criteria["formal_preregistration_amendment"]["amended_registrar_sha256"]


def test_dry_run_refuses_to_overwrite_the_historical_failure(candidate):
    args, _ = candidate
    protected = argparse.Namespace(**vars(args))
    protected.criteria = registrar.FAILURE_EVIDENCE
    before = protected.criteria.read_bytes()
    with pytest.raises(FileExistsError):
        registrar.build_formal(protected)
    assert protected.criteria.read_bytes() == before
