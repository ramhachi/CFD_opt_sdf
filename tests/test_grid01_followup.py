"""Pre-measurement generator, archival lineage and conservative-gain regressions."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))

import analyze_grid01 as A
import build_grid01_freeze as BF
import build_grid01_inputs as BI
import build_grid01_kernel as BK
from cfd_sdf import grid01_contract as C
import grid01_synthetic as S


def test_rendered_runner_and_freeze_pin_maps_are_identical():
    namespace = {"__name__": "grid01_readonly_render_test"}
    exec(compile(BK.render("a" * 40), "rendered_grid01.py", "exec"), namespace)
    assert namespace["PINS"] == BK.pins()
    assert "scripts/grid01_gpu.py" in namespace["PINS"]


@pytest.mark.parametrize("field,value", [
    ("step_mm", 99), ("time_window_t_u_l", [0, 1]),
    ("resolution_difference_n_strictly_greater_than", 9),
])
def test_inventory_measurement_declarations_are_rederived(field, value):
    inventory = copy.deepcopy(S.INV)
    inventory["measurement_contract"][field] = value
    failures = A._check_inventory(inventory, S.STEP01_INVENTORY, S.STEP01_ANALYSIS)
    assert any("complete measurement contract" in item for item in failures)


def test_inventory_job_environment_is_bound_to_step01():
    inventory = copy.deepcopy(S.INV)
    inventory["job_env_common"]["W4_CANONICAL_ORIGIN_M"] = "99,99,99"
    assert any("job_env_common" in item for item in A._check_inventory(inventory, S.STEP01_INVENTORY, S.STEP01_ANALYSIS))


def test_freeze_function_requires_full_inventory_rederivation(tmp_path, monkeypatch):
    inventory = copy.deepcopy(S.INV)
    inventory["measurement_contract"]["step_mm"] = 99
    (tmp_path / "inventory.json").write_text(json.dumps(inventory))
    monkeypatch.setattr(BF, "EVIDENCE", tmp_path)
    with pytest.raises(ValueError, match="rederivation"):
        BF.build("a" * 40, BF.EXPECTED_PARENT)


def test_identity_freshness_is_evaluated_at_registration_not_reproduction():
    record = {
        "kind": "fd08_v2_kaggle_identity_free_check", "owner": "ramhachi888",
        "all_free": True, "captured_utc": "2020-01-01T00:00:00+00:00",
        "intended_slugs": ["cfd-opt-sdf-grid01-a"], "owned_kernel_count": 1,
        "owned_dataset_count": 1, "listed_slug_clashes": {},
        "status_probes": {"cfd-opt-sdf-grid01-a": {
            kind: {"exit_code": 1, "stderr": "404 Not Found", "stdout": ""}
            for kind in ("kernels", "datasets")}},
    }
    BF._require_identity_free(record, as_of=datetime(2020, 1, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="stale"):
        BF._require_identity_free(record)


def test_old_authenticated_registration_remains_reproducible(tmp_path, monkeypatch):
    out, freeze, inventory = S.install_synthetic_root(tmp_path, monkeypatch)
    record = freeze["identity_free_check"]
    record["captured_utc"] = "2020-01-01T00:00:00+00:00"
    freeze["frozen_utc"] = "2020-01-01T01:00:00+00:00"
    path = A.ROOT / A.FILE_PATHS["identity_free_check"]
    path.write_text(json.dumps(record, sort_keys=True) + "\n")
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(A.sha256(path) + "\n")
    for key in ("identity_free_check", "identity_free_check_sha256"):
        freeze["file_hashes"][key] = A.sha256(A.ROOT / A.FILE_PATHS[key])
    report = A.analyze(out, freeze, inventory, S.FORMAL, S.STEP01_ANALYSIS)
    assert report["verdict"] == "GRID01_SECANT_RECORDED", report["integrity"]


def gain_case(robust_lower):
    proposals = {family: {"t_star_n_per_m": 1.0} for family in ("main_cross_grid", "robust_cross_grid")}
    predictions = {family: {"per_grid": {grid: {
        "raw_downforce_prediction_at_1p25mm_n": 2 * C.MIN_PREDICTED_DOWNFORCE_N,
        "l1_robust_downforce_lower_prediction_at_1p25mm_n": robust_lower,
    } for grid in C.GRIDS}} for family in proposals}
    return proposals, predictions


def test_sensitivity_gain_gate_uses_conservative_bound_at_exact_threshold():
    proposals, predictions = gain_case(C.MIN_PREDICTED_DOWNFORCE_N)
    assert A._proposal_verdict(proposals, predictions)["verdict"] == "FEASIBLE_CONE_FOUND"
    below = np.nextafter(C.MIN_PREDICTED_DOWNFORCE_N, 0.0)
    proposals, predictions = gain_case(float(below))
    report = A._proposal_verdict(proposals, predictions)
    assert report["verdict"] == "NO_FEASIBLE_CONE_IN_4D"
    assert report["predictions_tested_n"]["robust_cross_grid|flow_24"] == below


def test_registered_package_closure_ignores_unrelated_later_added_modules(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    git("init", "-q")
    git("config", "user.email", "grid01-test@example.invalid")
    git("config", "user.name", "GRID01 test")
    tree = repo / "src/cfd_sdf"
    tree.mkdir(parents=True)
    module = tree / "original.py"
    module.write_text("value = 1\n")
    git("add", ".")
    git("commit", "-qm", "registered source")
    registered = git("rev-parse", "HEAD")
    digest = A.frozen_path_sha("cfd_sdf_source_tree", tree, registered, root=repo)
    (tree / "separate_geom01.py").write_text("unrelated = True\n")
    git("add", ".")
    git("commit", "-qm", "independent new geometry module")
    assert A.frozen_path_sha("cfd_sdf_source_tree", tree, registered, root=repo) == digest
    kwargs = dict(root=repo, file_paths={"cfd_sdf_source_tree": "src/cfd_sdf"}, exceptions=set(), parent_commit=registered)
    assert A._source_commit_failures(registered, {"cfd_sdf_source_tree": digest}, **kwargs) == []
    orphan = git("commit-tree", "HEAD^{tree}", "-m", "unrelated parent")
    assert any("integration parent" in item for item in A._source_commit_failures(orphan, {"cfd_sdf_source_tree": digest}, **kwargs))
    module.write_text("value = 2\n")
    assert A.frozen_path_sha("cfd_sdf_source_tree", tree, registered, root=repo) != digest


def test_flow32_scope_declaration_never_claims_flow24_qualification():
    contract = BI.measurement_contract(S.FORMAL)
    assert "flow_24 local diagnostic" not in contract["flow32_measurement"]["qualification_claim"]
    assert "no qualification claim" in contract["flow32_measurement"]["qualification_claim"]


def authenticated_identity_case():
    record = json.loads((ROOT / A.FILE_PATHS["identity_free_check"]).read_text())
    witness = BF.load_listing_confirmation(ROOT)
    reference = datetime.fromisoformat(witness["captured_utc"])  # archived registration time, never today's clock
    return record, witness, reference


def test_real_permission_masked_status_is_not_absence_without_authenticated_lists():
    record, witness, reference = authenticated_identity_case()
    with pytest.raises(ValueError, match="without authenticated absence"):
        BF._require_identity_free(record, as_of=reference)
    BF._require_identity_free(record, as_of=reference, listing_confirmation=witness)


@pytest.mark.parametrize("mutation", ["missing_control", "failed_control", "wrong_owner", "truncated", "slug_collision", "raw_csv_mismatch"])
def test_permission_masked_status_requires_complete_consistent_positive_owner_evidence(mutation):
    record, witness, reference = authenticated_identity_case()
    if mutation == "missing_control":
        witness["positive_controls"].pop("kernels")
    elif mutation == "failed_control":
        witness["positive_controls"]["datasets"]["exit_code"] = 1
    elif mutation == "wrong_owner":
        witness["owner"] = "not-the-authenticated-owner"
    elif mutation == "truncated":
        record["owned_kernel_count"] = 100
    elif mutation == "slug_collision":
        # Keep raw CSV and parsed rows coherent so collision detection is exercised.
        import csv, io
        rows = witness["listings"]["kernels"]["rows"]
        rows[-1]["ref"] = A.KERNEL_ID
        buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        witness["listings"]["kernels"]["stdout"] = buffer.getvalue()
    else:
        witness["listings"]["kernels"]["rows"].pop()
    with pytest.raises(ValueError):
        BF._require_identity_free(record, as_of=reference, listing_confirmation=witness)


@pytest.mark.parametrize("mutation", ["missing_seconds", "over_per_state", "wrong_total", "nonfinite_summary", "wrong_cuda_uuid", "missing_cuda_probe"])
def test_runtime_timing_and_observed_cuda_identity_fail_closed(tmp_path, monkeypatch, mutation):
    out, freeze, inventory = S.install_synthetic_root(tmp_path, monkeypatch)
    index_path = out / "grid01_index.json"
    index = json.loads(index_path.read_text())
    if mutation == "missing_seconds":
        index["states"][0].pop("seconds")
    elif mutation == "over_per_state":
        index["states"][0]["seconds"] = C.PER_STATE_TIMEOUT_S + 1
    elif mutation == "wrong_total":
        index["solver_process_wall_seconds_total"] = C.SOLVER_WALL_TIME_CAP_S + 1
    elif mutation == "nonfinite_summary":
        p = out / "states/step01__baseline/flow_32.summary.json"
        summary = json.loads(p.read_text()); summary["wall_seconds"] = float("nan")
        p.write_text(json.dumps(summary))
    elif mutation == "wrong_cuda_uuid":
        p = out / "gpu_device_probe.json"
        probe = json.loads(p.read_text()); probe["default_device_uuid"] = "GPU-not-selected"
        p.write_text(json.dumps(probe))
    else:
        p = out / "gpu_device_probe.json"
        assert p.resolve().parent == out.resolve() and p.name == "gpu_device_probe.json"
        p.unlink()
    index_path.write_text(json.dumps(index))
    S.rebuild_manifest(out)
    report = A.analyze(out, freeze, inventory, S.FORMAL, S.STEP01_ANALYSIS)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"


def test_grid01_runtime_budget_is_distinct_from_unchanged_formal_force_contract():
    contract = BI.measurement_contract(S.FORMAL)["flow32_measurement"]
    assert contract["solver_wall_time_cap_s"] == 8100
    assert contract["kernel_execution_allowance_s"] == 10800
    assert contract["per_state_timeout_s"] == 900
    assert S.FORMAL["measurement"]["solver_wall_time_cap_s"] == 3300


def test_the_cuda_probe_needs_no_julia_package_beyond_cuda_and_writes_the_json_the_runner_expects(tmp_path):
    """The first T4 attempt died on `using JSON3` (not in the T4 project): the probe may use only CUDA + Julia Base; check it against a CUDA stub."""
    import os
    import shutil
    import subprocess

    template = (ROOT / "scripts/grid01_runner_template.py").read_text()
    ns: dict = {}
    exec(template[template.index("GPU_PROBE_CODE"):template.index("EXPECTED_NAMES")], ns)
    code = ns["GPU_PROBE_CODE"]
    assert "JSON3" not in code and code.count("using ") == 1 and "\\" not in code
    project = (ROOT / "julia/CFDSDFWaterLilyT4/Project.toml").read_text()
    assert "JSON3" not in project and "CUDA" in project
    julia = shutil.which("julia")
    if julia is None:
        pytest.skip("julia is not installed here")
    stub = ('module CUDA\nstruct Dev; i::Int; end\nfunctional() = true\ndevices() = [Dev(0)]\ndevice() = Dev(0)\n'
            'uuid(d::Dev) = Base.UUID("2725eec8-7d49-5e29-3d12-e9d9a4b0a9d4")\nname(d::Dev) = "Tesla T4"\nend\nusing .CUDA\n')
    out = tmp_path / "probe.json"
    env = dict(os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES="0", GRID01_GPU_PROBE_OUT=str(out))
    done = subprocess.run([julia, "--startup-file=no", "-e", code.replace("using CUDA\n", stub, 1)], env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-500:]
    uuid = "GPU-2725eec8-7d49-5e29-3d12-e9d9a4b0a9d4"
    assert json.loads(out.read_text()) == {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"], "visible_gpu_uuids": [uuid], "default_device_uuid": uuid,
                                           "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}
