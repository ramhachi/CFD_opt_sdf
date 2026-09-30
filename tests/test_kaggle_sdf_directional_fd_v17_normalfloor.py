"""FD-06 (#37): criteria are FD-05 verbatim except normal_floor, and the floor is plumbed end to end."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registrar = load("fd06_registrar", "scripts/register_kaggle_sdf_directional_fd_v17_flow24_normalfloor_2026_09.py")
runner = load("fd06_runner", "infra/kaggle/kernel_sdf_directional_fd_v17_flow24_normalfloor/runner.py")
verifier = load("fd06_verifier", "scripts/verify_kaggle_sdf_directional_fd_v16.py")
FD05 = json.loads((ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_criteria_2026_09_schemafix5.json").read_text())


@pytest.fixture(scope="module")
def criteria():
    return registrar.build_criteria("0" * 40, require_pushed_head=False)


def test_only_normal_floor_differs_in_measured_and_judged_blocks(criteria):
    for field in registrar.FIXED + ("epsilon_relative_to_design_spacing_rationale",):
        assert criteria[field] == FD05[field], field
    assert criteria["geometry"]["normal_floor"] == 0.25
    assert {k: v for k, v in criteria["geometry"].items() if not k.startswith("normal_floor")} == FD05["geometry"]
    assert criteria["criteria_id"] != FD05["criteria_id"] and criteria["input_dataset_id"] != FD05["input_dataset_id"]
    assert criteria["geometry"]["normal_floor"] == registrar.NORMAL_FLOOR


def test_criteria_hash_is_canonical_for_runner_and_host(criteria):
    assert runner.criteria_digest(criteria) == criteria["criteria_sha256"]
    assert verifier.canonical_json_sha(
        {k: v for k, v in criteria.items() if k != "criteria_sha256"}) == criteria["criteria_sha256"]


def test_runner_outcome_reports_the_canonical_hash_the_host_compares():
    source = (ROOT / "infra/kaggle/kernel_sdf_directional_fd_v17_flow24_normalfloor/runner.py").read_text()
    assert '"criteria_sha256": criteria["criteria_sha256"], "criteria_file_sha256": criteria_sha' in source


def test_job_environment_carries_the_floor_and_defaults_to_zero(criteria):
    assert runner.julia_job_environment(criteria)["FD_NORMAL_FLOOR"] == "0.25"
    old = copy.deepcopy(criteria)
    del old["geometry"]["normal_floor"]
    assert runner.julia_job_environment(old)["FD_NORMAL_FLOOR"] == "0.0"


def test_kernel_and_dataset_identity_are_bound(criteria):
    meta = json.loads((ROOT / registrar.KERNEL_DIR / "kernel-metadata.json").read_text())
    assert meta["id"] == criteria["kernel_id"] and meta["dataset_sources"] == [criteria["input_dataset_id"]]
    assert len(meta["id"].split("/")[1]) <= 40  # Kaggle rejected longer FD-05 slugs
    assert criteria["inputs"]["kernel_runner"]["path"] == f"{registrar.KERNEL_DIR}/runner.py"
    for name in ("waterlily_body", "normal_floor_body", "normal_floor_selftest", "fd05_criteria"):
        assert criteria["inputs"][name]["location"] == "source_repo"


def test_host_summary_check_requires_the_registered_floor():
    out = ROOT / "work/kaggle_sdf_directional_fd_v17_flow24_kernel_v1_2026_09/sdf_directional_fd_v17_flow24"
    path = out / "baseline_A.summary.json"
    if not path.is_file():
        pytest.skip("FD-05 kernel output is not available locally")
    summary = json.loads(path.read_text())
    assert verifier.host_physics_identity(summary, FD05)  # FD-05 criteria carry no floor: unchanged behaviour
    floor = copy.deepcopy(FD05)
    floor["geometry"]["normal_floor"] = 0.25
    assert not verifier.host_physics_identity(summary, floor)
    assert not verifier.host_physics_identity({**summary, "normal_floor": 0.0}, floor)
    assert verifier.host_physics_identity({**summary, "normal_floor": 0.25}, floor)
