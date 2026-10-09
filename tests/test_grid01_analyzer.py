from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import analyze_grid01 as A  # noqa: E402
import grid01_synthetic as SYN  # noqa: E402
from cfd_sdf import grid01_contract as C  # noqa: E402


@pytest.fixture
def valid_case(tmp_path, monkeypatch):
    out, freeze, inventory = SYN.install_synthetic_root(tmp_path, monkeypatch)
    return out, freeze, inventory


def run(out, freeze, inventory):
    return A.analyze(out, freeze, inventory=inventory, formal=SYN.FORMAL, step01_analysis=SYN.STEP01_ANALYSIS)


def refresh_freeze_inventory(freeze, inventory):
    freeze["file_hashes"]["inventory_canonical_json"] = A._json_sha(inventory)


def test_complete_synthetic_kernel_records_finite_step_results_and_verified_proposals(valid_case):
    out, freeze, inventory = valid_case
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_RECORDED", report["integrity"]
    assert report["integrity"] == {"pass": True, "failures": []}
    assert A.select_worker_gpu((out / "nvidia_smi.csv").read_text()) == {
        "index": 0, "name": "Tesla T4", "uuid": "GPU-grid01-physical-index-zero",
    }
    assert report["qualification_flags"] == {name: False for name in A.FLAGS}
    assert report["selected_delta"] is None and report["shape_update_allowed"] is False
    d1 = report["measurements"]["flow32_host_recomputed"]["D1_filtered_seed11"]["downforce"]
    assert d1["resolved"] is False and d1["g_sec_n_per_m"] != 0.0
    assert report["component_comparisons"]["D1_filtered_seed11"]["downforce"]["sign_status"] == "unresolved"
    pure_even = report["measurements"]["flow32_host_recomputed"]["D2_filtered_seed2026"]["downforce"]
    assert pure_even["g_sec_n_per_m"] == 0.0 and pure_even["resolved"] is False and pure_even["eta_even"] is None
    assert report["proposal_verdict"]["verdict"] in {"FEASIBLE_CONE_FOUND", "NO_FEASIBLE_CONE_IN_4D"}
    assert report["solver_free_proposals"]["all_solutions_verified"] is True
    lowdim = report["lowdim01_proposal_predictions_with_actual_m"]
    assert lowdim["proposal_sha256"] == SYN.LOWDIM01_INVENTORY["proposal"]["sha256_fortran_raw"]
    assert lowdim["m_max_abs_sum_from_actual_four_direction_arrays"] == pytest.approx(SYN.LOWDIM01_INVENTORY["proposal"]["m_max_abs_sum"])
    assert set(lowdim["per_grid"]) == set(C.GRIDS)
    assert all("raw_drag_prediction_at_1p25mm_n" in lowdim["per_grid"][grid] for grid in C.GRIDS)
    flow24_drag = lowdim["per_grid"][C.GRIDS[0]]
    assert flow24_drag["raw_drag_prediction_at_1p25mm_n"] == pytest.approx(
        flow24_drag["raw_drag_slope_n_per_m"] * 0.00125 / lowdim["m_max_abs_sum_from_actual_four_direction_arrays"]
    )
    assert flow24_drag["basis_downforce_components_resolved"][2] is True
    for family in ("main_cross_grid", "robust_cross_grid"):
        assert report["proposal_predictions_with_actual_m"][family]["m_max_abs_sum_from_actual_four_direction_arrays"] > 0
        assert set(report["proposal_predictions_with_actual_m"][family]["per_grid"]) == set(C.GRIDS)


def test_empty_runtime_pins_fail_closed(valid_case):
    out, freeze, inventory = valid_case
    freeze["pins"] = {}
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("pins are missing, empty" in item for item in report["integrity"]["failures"])


def test_nan_pin_fails_closed(valid_case):
    out, freeze, inventory = valid_case
    key = next(iter(freeze["pins"]))
    freeze["pins"][key] = float("nan")
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("pins are missing, empty" in item for item in report["integrity"]["failures"])


def test_missing_registered_state_and_empty_manifest_fail_closed(valid_case, tmp_path, monkeypatch):
    out, freeze, inventory = valid_case
    state = out / "states" / A.MINIMUM_STATE_NAMES[-1] / "flow_32.forces.csv"
    state.unlink()
    SYN.rebuild_manifest(out)
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("missing" in item or "manifest" in item for item in report["integrity"]["failures"])

    # A separate empty manifest mutation cannot pass by listing no files.
    out, freeze, inventory = SYN.install_synthetic_root(tmp_path / "second", monkeypatch)
    (out / "output_manifest.json").write_text('{"files": {}}\n')
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("manifest" in item for item in report["integrity"]["failures"])


def test_missing_summary_and_wrong_gpu_fail_closed(valid_case, tmp_path, monkeypatch):
    out, freeze, inventory = valid_case
    summary = out / "states" / A.MINIMUM_STATE_NAMES[2] / "flow_32.summary.json"
    summary.unlink()
    SYN.rebuild_manifest(out)
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("summary" in item or "manifest" in item for item in report["integrity"]["failures"])

    out, freeze, inventory = SYN.install_synthetic_root(tmp_path / "gpu", monkeypatch)
    (out / "nvidia_smi.csv").write_text(
        "0, Tesla T4, GPU-grid01-physical-index-zero, 15360 MiB, 535.1\n"
        "1, A100, GPU-other, 40960 MiB, 535.1\n"
    )
    SYN.rebuild_manifest(out)
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("GPU inventory" in item for item in report["integrity"]["failures"])


def test_summary_gpu_uuid_must_match_physical_index_zero(valid_case):
    out, freeze, inventory = valid_case
    path = out / "states" / A.MINIMUM_STATE_NAMES[1] / "flow_32.summary.json"
    summary = json.loads(path.read_text())
    summary["gpu_uuid"] = "GPU-grid01-index-one"
    path.write_text(json.dumps(summary) + "\n")
    SYN.rebuild_manifest(out)
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("gpu_uuid" in item for item in report["integrity"]["failures"])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("t_end_reached", 119.9, "horizon"),
        ("julia_threads", 2, "thread"),
        ("finite_forces", False, "fields"),
        ("downforce_time_weighted_n", float("nan"), "non-finite"),
    ],
)
def test_nonfinite_or_unqualified_state_summary_fails_closed(valid_case, field, value, message):
    out, freeze, inventory = valid_case
    path = out / "states" / A.MINIMUM_STATE_NAMES[1] / "flow_32.summary.json"
    summary = json.loads(path.read_text())
    summary[field] = value
    path.write_text(json.dumps(summary, allow_nan=True) + "\n")
    SYN.rebuild_manifest(out)
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any(message in item for item in report["integrity"]["failures"])


def test_missing_or_wrong_geometry_gate_key_fails_closed(valid_case):
    out, freeze, inventory = valid_case
    mutated = copy.deepcopy(inventory)
    gates = mutated["states"][1]["geometry_gates"]["gates"]
    del gates["clearance"]
    refresh_freeze_inventory(freeze, mutated)
    report = run(out, freeze, mutated)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("geometry gate set mismatch" in item for item in report["integrity"]["failures"])


def test_flow24_resolution_and_even_part_are_rederived_from_immutable_response_numbers():
    inventory = copy.deepcopy(SYN.INV)
    d1 = inventory["flow24_reference_step01"]["secants"]["D1_filtered_seed11"]["downforce"]
    assert d1["source_step01_resolved"] is False and d1["resolved"] is True
    d1["resolved"] = False
    failures = A._check_inventory(inventory, SYN.STEP01_INVENTORY, SYN.STEP01_ANALYSIS)
    assert any("strict contrast rule" in item for item in failures)

    inventory = copy.deepcopy(SYN.INV)
    d2 = inventory["flow24_reference_step01"]["secants"]["D2_filtered_seed2026"]["drag"]
    d2["even_part_n"] += 1.0e-6
    failures = A._check_inventory(inventory, SYN.STEP01_INVENTORY, SYN.STEP01_ANALYSIS)
    assert any("even_part_n is not rederived" in item for item in failures)

    inventory = copy.deepcopy(SYN.INV)
    d0 = inventory["flow24_reference_step01"]["secants"]["D0_interface_offset"]["downforce"]
    d0["g_sec_n_per_m"] += 1.0e-8
    failures = A._check_inventory(inventory, SYN.STEP01_INVENTORY, SYN.STEP01_ANALYSIS)
    assert any("source numbers differ" in item for item in failures)


def test_inventory_case_label_must_match_the_reused_flow32_contract():
    inventory = copy.deepcopy(SYN.INV)
    inventory["measurement_contract"]["flow32_measurement"]["case_id"] = "flow_24"
    failures = A._check_inventory(inventory, SYN.STEP01_INVENTORY, SYN.STEP01_ANALYSIS)
    assert any("FLOW32_CASE" in item for item in failures)


def test_manifest_path_escape_fails_closed(valid_case):
    out, freeze, inventory = valid_case
    manifest = json.loads((out / "output_manifest.json").read_text())
    manifest["files"]["../../escape"] = "0" * 64
    (out / "output_manifest.json").write_text(json.dumps(manifest) + "\n")
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("escapes the kernel output" in item for item in report["integrity"]["failures"])


def test_mutated_freeze_source_hash_and_missing_freeze_key_fail_closed(valid_case):
    out, freeze, inventory = valid_case
    freeze["file_hashes"]["analyzer"] = ""
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("analyzer" in item for item in report["integrity"]["failures"])

    out, freeze, inventory = valid_case
    del freeze["source_commit"]
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("missing required keys" in item or "source commit" in item for item in report["integrity"]["failures"])


@pytest.mark.parametrize(
    "section",
    [
        "runtime", "design", "measurement", "solver", "rules", "flow24_reference",
        "flow32_baseline_reference", "known_before_run", "prohibitions", "qualification_flags",
    ],
)
def test_each_freeze_section_requires_its_complete_schema(valid_case, section):
    out, freeze, inventory = valid_case
    freeze[section].pop(next(iter(freeze[section])))
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE", section


@pytest.mark.parametrize(
    ("section", "path", "value"),
    [
        ("runtime", ("timeout_s",), 1.0e99),
        ("design", ("state_count",), 8),
        ("measurement", ("resolution_difference_n_strictly_greater_than",), float("nan")),
        ("solver", ("kkt_atol",), float("nan")),
        ("rules", ("resolved_difference_strictly_greater_than_n",), float("nan")),
        ("flow24_reference", ("secants", "D0_interface_offset", "downforce", "r0_n"), 0.0),
        ("flow32_baseline_reference", ("forces_csv_sha256",), "0" * 64),
        ("known_before_run", ("flow32_noise_measured",), True),
        ("prohibitions", ("actual_primal_line_search",), False),
        ("qualification_flags", ("shape_update_allowed",), True),
    ],
)
def test_every_freeze_section_rejects_mutated_constants_nonfinite_values_and_flags(valid_case, section, path, value):
    out, freeze, inventory = valid_case
    node = freeze[section]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE", section


def test_analyzer_check_authenticates_freeze_sidecar_and_exits_three_before_write(valid_case, tmp_path, monkeypatch, capsys):
    out, freeze, _inventory = valid_case
    freeze["solver"]["kkt_atol"] = 1.0e99
    freeze_path = tmp_path / "prerun_freeze.json"
    raw = json.dumps(freeze, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    freeze_path.write_bytes(raw)
    sidecar = freeze_path.with_name(freeze_path.name + ".sha256")
    sidecar.write_text(hashlib.sha256(raw).hexdigest() + "\n")
    output_path = tmp_path / "analysis.json"
    monkeypatch.setattr(sys, "argv", ["analyze_grid01.py", "--kernel-dir", str(out), "--freeze", str(freeze_path), "--check", "--write", str(output_path)])
    with pytest.raises(SystemExit) as error:
        A.main()
    assert error.value.code == 3
    assert '"verdict": "GRID01_SECANT_INCOMPLETE"' in capsys.readouterr().out
    assert not output_path.exists()


@pytest.mark.parametrize("sidecar_mode", ["missing", "mismatch"])
def test_analyzer_check_fails_closed_without_authenticated_freeze_bytes(valid_case, tmp_path, monkeypatch, capsys, sidecar_mode):
    out, freeze, _inventory = valid_case
    freeze_path = tmp_path / "prerun_freeze.json"
    raw = json.dumps(freeze, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    freeze_path.write_bytes(raw)
    sidecar = freeze_path.with_name(freeze_path.name + ".sha256")
    if sidecar_mode == "mismatch":
        sidecar.write_text("0" * 64 + "\n")
    monkeypatch.setattr(sys, "argv", ["analyze_grid01.py", "--kernel-dir", str(out), "--freeze", str(freeze_path), "--check"])
    with pytest.raises(SystemExit) as error:
        A.main()
    assert error.value.code == 3
    output = capsys.readouterr()
    assert '"verdict": "GRID01_SECANT_INCOMPLETE"' in output.out
    assert "invalid freeze:" in output.err


def test_source_commit_verification_rejects_newer_clean_host_source(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "grid01-test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "GRID01 test"], check=True)
    source = repo / "host_source.py"
    source.write_text("value = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "host_source.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "source v1"], check=True)
    old_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    source.write_text("value = 2\n")
    subprocess.run(["git", "-C", str(repo), "add", "host_source.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "source v2"], check=True)
    new_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    hashes = {"host_source": hashlib.sha256(source.read_bytes()).hexdigest()}
    assert A._source_commit_failures(new_commit, hashes, root=repo, file_paths={"host_source": "host_source.py"}, exceptions=set(), parent_commit=old_commit) == []
    failures = A._source_commit_failures(old_commit, hashes, root=repo, file_paths={"host_source": "host_source.py"}, exceptions=set(), parent_commit=old_commit)
    assert any("source commit differs" in item for item in failures)


def test_source_tree_hash_ignores_python_bytecode_cache(tmp_path):
    tree = tmp_path / "src"
    (tree / "pkg" / "__pycache__").mkdir(parents=True)
    source = tree / "pkg" / "module.py"
    source.write_text("value = 1\n")
    digest = A.sha256(tree)
    (tree / "pkg" / "__pycache__" / "module.cpython-312.pyc").write_bytes(b"generated cache")
    assert A.sha256(tree) == digest


def test_mutated_lowdim01_proposal_direction_fails_closed(valid_case):
    out, freeze, inventory = valid_case
    path = A.ROOT / A.FILE_PATHS["lowdim01_proposal_direction"]
    original = path.read_bytes()
    path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    report = run(out, freeze, inventory)
    assert report["verdict"] == "GRID01_SECANT_INCOMPLETE"
    assert any("lowdim01_proposal_direction" in item for item in report["integrity"]["failures"])
