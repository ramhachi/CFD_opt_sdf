"""Synthetic GRAD-00 contracts; these fixtures are not CFD measurements."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import analyze_grad00 as A
from scripts import grad_g2_window as W
from scripts.build_lowdim04a_kernel import sha as working_sha
from tests import grad_g2_synthetic as G

ROOT = Path(__file__).resolve().parents[1]
REAL_COMMITTED_SHA = A.committed_sha
SYNTHETIC_REFERENCES = {}
SYNTHETIC_SOURCE_HASHES = {}


def synthetic_pin(name):
    if name in SYNTHETIC_REFERENCES:
        return hashlib.sha256(json.dumps(SYNTHETIC_REFERENCES[name], sort_keys=True).encode()).hexdigest()
    if name not in SYNTHETIC_SOURCE_HASHES:
        SYNTHETIC_SOURCE_HASHES[name] = working_sha(ROOT / name)
    return SYNTHETIC_SOURCE_HASHES[name]


def dump(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False))


def reference():
    return {
        "schema_version": 1, "kind": "grad00_fd08_reference",
        "definition": "SYNTHETIC fixture: fixed epsilon and a declared plateau spread, not registered FD-08 data",
        "sources": {"scripts/grad_g2_window.py": A.sha256(ROOT / "scripts/grad_g2_window.py")},
        "directions": {d: {"epsilon_m": 0.001, "spread_n_per_m": {"fx": 0.00001, "fz": 0.00001}} for d in A.DIRECTIONS},
    }


def manifest(out):
    dump(out / "output_manifest.json", {"files": {p.name: A.sha256(p) for p in out.iterdir() if p.is_file() and p.name != "output_manifest.json"}})


def fixture(out, arm="quick", real_type="Float32", waterlily="1.8.0", *, blocked=(), errors=None, plain_offset=0.0):
    """Four constant-force samples bracket the real window; no solver is run."""
    out.mkdir(parents=True)
    dirs = A.DIRECTIONS[:2] if real_type == "Float64" else A.DIRECTIONS
    lam = A.LAMBDA_TYPES[arm]
    runs, by_direction = {}, {}
    order = ["plain", *(label for d in dirs for label in (d, d + "__plus", d + "__minus"))]
    for label in order:
        direction = next((d for d in dirs if label.startswith(d)), None)
        dual = label in dirs
        alpha = 0.001 if label.endswith("__plus") else -0.001 if label.endswith("__minus") else 0.0
        k = 1.0 + (dirs.index(direction) if direction else 0)
        slope = {"fx": 2.0 * k, "fz": -3.0 * k}
        rows = []
        for step, time in ((8, 79.0), (16, 90.0), (24, 110.0), (32, 121.0)):
            row = {key: 0.0 for key in W.HEADER}
            row.update(step=float(step), t_u_l=time)
            for c, base in (("fx", 100.0), ("fz", -200.0)):
                row[c] = base + plain_offset + alpha * slope[c]
                row[c + "_tan"] = slope[c] * (errors or {}).get(direction, 1.0) if dual else 0.0
                row["p" + c] = row[c]
                row["p" + c + "_tan"] = row[c + "_tan"]
            rows.append(row)
        G.write_history(out / f"{label}.history.csv", rows)
        summary = G.summary_for(rows, label, f"ForwardDiff.Dual{{Nothing, {real_type}, 1}}" if dual else real_type)
        summary.update(lambda_type=lam, status="BLOCKED" if label in blocked else "COMPLETE", loop_seconds=10.0)
        if dual:
            terminal = {"tan_max_u": 1e31 if label in blocked else 1.0, "tan_max_p": 0.5,
                        "tan_argmax_u": "1;2;3;1", "tan_argmax_p": "1;2;3"}
            summary.update(terminal_tangent=terminal, watchdog_max_abs_tangent_u_finite=terminal["tan_max_u"],
                           watchdog_max_abs_tangent_p_finite=terminal["tan_max_p"], watchdog_onset=None)
        if label in blocked:
            summary["blocked"] = {"reason": "tangent_non_finite_or_above_limit", "onset_step": 100, "limit": 1e30,
                                  "tan_max_u": 1e31, "tan_max_p": 4.0, "tan_argmax_u": "1;2;3;1", "tan_argmax_p": "1;2;3"}
            dump(out / f"{label}.blocked.json", summary["blocked"])
            summary["watchdog_onset"] = summary["blocked"]
            summary["terminal_tangent"].update(tan_max_p=4.0)
            summary["watchdog_max_abs_tangent_p_finite"] = 4.0
            short = [{**rows[0], "step": float(step), "t_u_l": step * 0.014} for step in range(8, 100, 8)]
            G.write_history(out / f"{label}.history.csv", short)
            summary.update(steps=100, sample_count=len(short))
            for key in list(summary):
                if key.startswith("window_mean_"):
                    del summary[key]
        summary.update(input_phi_storage_type=real_type, input_phi_sha256=A.expected_field_hash(real_type, direction if alpha else None, alpha))
        if dual:
            summary["input_tangent_sha256"] = A.expected_field_hash(real_type, direction, tangent=True)
        dump(out / f"{label}.summary.json", summary)
        artifacts = (("summary", ".summary.json"), ("history", ".history.csv"))
        if dual:
            watch = "step,t_u_l,tan_max_u,tan_argmax_u,tan_max_p,tan_argmax_p,last_sample_step,fx,fx_tan,fz,fz_tan,elapsed_s,vram_bytes\n"
            if label in blocked:
                watch += "100,1.4,1e31,1;2;3;1,4,1;2;3,96,100,2,-200,-3,2,1\n"
            (out / f"{label}.watchdog.csv").write_text(watch)
            artifacts += (("watchdog", ".watchdog.csv"),)
        runs[label] = {**summary, **{key + "_path": label + suffix for key, suffix in artifacts}}
        runs[label].update({key + "_sha256": A.sha256(out / runs[label][key + "_path"]) for key, _ in artifacts})
    for d in dirs:
        by_direction[d] = {"plain": "plain", "dual": d, "plus": d + "__plus", "minus": d + "__minus", "epsilon_m": 0.001}
    status = "BLOCKED" if blocked else "COMPLETE"
    index = {"schema_version": 1, "tier": "GRAD-00", "arm": arm, "real_type": real_type, "backend": "cpu" if real_type == "Float64" else "cuda",
             "julia": "1.12.6", "waterlily": waterlily, "forwarddiff": "1.4.5", "cuda_jl": "6.3.1", "gpu_name": "Tesla T4", "lambda_type": lam, "window_t_u_l": [80.0, 120.0],
             "sample_every": 8, "dual_width": 1, "block_limit": 1e30, "wall_factor": 8.0, "directions": list(dirs),
             "input_sha256": A.INPUT_SHA256,
             "epsilon_m": {d: 0.001 for d in A.DIRECTIONS}, "preflight": {"pass": True, "steps": 20, "primal_u_bit_equal": True, "primal_p_bit_equal": True,
                 "arms": {name: {"lambda_type": A.LAMBDA_TYPES["quick"] if name == "quick" else lam,
                                  "primal_finite": True, "tangent_u_finite": True, "tangent_p_finite": True, "max_abs_tangent_u": 1.0, "max_abs_tangent_p": 1.0,
                                  "primal_u_sha256": "1" * 64, "primal_p_sha256": "2" * 64} for name in (("quick", "selected_dual", "selected_plain") if arm == "quick" else ("selected_dual", "selected_plain"))}},
             "runs": runs, "by_direction": by_direction, "status": status, "qualification_flags": {k: False for k in A.FLAGS},
             "evidence_class": "SYNTHETIC_TEST_FIXTURE"}
    dump(out / "grad00_index.json", index)
    dump(out / "preflight.json", index["preflight"])
    dump(out / "g2_run_index.json", {**index, "run_order": order, "run_status": {k: v["status"] for k, v in runs.items()}})
    commit = A._git_output("rev-parse", "HEAD").decode().strip()
    project = "julia/CFDSDFWaterLily110" if waterlily == "1.10.0" else "julia/CFDSDFWaterLily" if real_type == "Float64" else "julia/CFDSDFWaterLilyT4"
    pins = {name: synthetic_pin(name) for name in A.REQUIRED_SOURCE_PINS | {f"{project}/Project.toml", f"{project}/Manifest.toml"}}
    reference_name = f"synthetic/{out.name}_reference.json"
    SYNTHETIC_REFERENCES[reference_name] = reference()
    pins[reference_name] = synthetic_pin(reference_name)
    dump(out / "run_identity.json", {"source_commit": commit, "source_tree_id": A._git_output("rev-parse", f"{commit}^{{tree}}").decode().strip(),
                                    "failure_stage": None, "spike_exit_code": 3 if blocked else 0, "pins": pins, "verified": pins,
                                    "arm": arm, "reference": {**reference(), "path": reference_name, "sha256": pins[reference_name]},
                                    "phi_sha256": A.INPUT_SHA256["phi"], "direction_sha256": A.INPUT_SHA256["directions"]})
    (out / "DONE").write_text("synthetic\n")
    manifest(out)
    return index


@pytest.fixture(autouse=True)
def synthetic_committed_bytes(monkeypatch):
    """New uncommitted job files have no git blobs in this pre-commit TDD run.

    Source-payload integrity tests still compare pins with this independent
    synthetic committed-byte provider. The real git hashing is checked below.
    """
    SYNTHETIC_REFERENCES.clear()
    SYNTHETIC_SOURCE_HASHES.clear()
    monkeypatch.setattr(A, "committed_sha", lambda commit, name: synthetic_pin(name))
    monkeypatch.setattr(A, "committed_reference", lambda commit, name: SYNTHETIC_REFERENCES[name])


def patch(out, change):
    index = json.loads((out / "grad00_index.json").read_text())
    change(index)
    dump(out / "grad00_index.json", index)
    manifest(out)


def change_run(out, label, change):
    index = json.loads((out / "grad00_index.json").read_text())
    path = out / f"{label}.summary.json"
    summary = json.loads(path.read_text())
    change(summary)
    dump(path, summary)
    index["runs"][label].update(summary)
    for kind in ("summary", "history", "watchdog"):
        if kind + "_path" in index["runs"][label]:
            index["runs"][label][kind + "_sha256"] = A.sha256(out / index["runs"][label][kind + "_path"])
    dump(out / "grad00_index.json", index)
    manifest(out)


@pytest.mark.parametrize(("tangent", "fd", "spread", "label"), [
    (1.0, 1.0, 0.01, "AGREE"), (-1.0, -1.0, 0.01, "AGREE"),
    (1.1, 1.0, 0.01, "AGREE"), (1.10001, 1.0, 0.01, "DISAGREE"),
    (-1.0, 1.0, 0.01, "DISAGREE"), (0.0, 1.0, 0.01, "DISAGREE"),
    (0.01, 0.01, 0.01, "NOT_EVALUABLE"), (0.0, 0.0, 0.0, "NOT_EVALUABLE"),
    (0.03, 0.03, 0.01, "AGREE"),
])
def test_row_rules(tangent, fd, spread, label):
    assert A.compare_row(tangent, fd, spread)["label"] == label


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, "1"])
def test_nonfinite_or_wrong_type_rejected(invalid):
    with pytest.raises(ValueError):
        A.compare_row(invalid, 1.0, 0.1)


def test_ratio_nextafter_endpoints_do_not_widen_tolerance():
    import math

    assert A.compare_row(math.nextafter(1.1, math.inf), 1.0, 0.0)["label"] == "DISAGREE"
    assert A.compare_row(math.nextafter(0.9, -math.inf), 1.0, 0.0)["label"] == "DISAGREE"
    assert A.compare_row(0.9, 1.0, 0.0)["label"] == "AGREE"


def test_finite_ratio_overflow_is_disagree_and_json_safe():
    row = A.compare_row(1e27, 1e-300, 0.0)
    assert row["label"] == "DISAGREE" and row["ratio"] is None
    json.dumps(row, allow_nan=False)


def test_finite_spread_threshold_overflow_fails_closed():
    with pytest.raises(ValueError, match="threshold overflow"):
        A.compare_row(1.0, 1.0, 1e308)


def test_load_reference_checks_provenance_and_requires_all_spreads(tmp_path):
    path = tmp_path / "reference.json"
    ref = reference()
    dump(path, ref)
    assert A.load_reference(path) == ref
    ref["sources"]["scripts/grad_g2_window.py"] = "0" * 64
    dump(path, ref)
    with pytest.raises(ValueError, match="SHA"):
        A.load_reference(path)
    ref = reference()
    del ref["directions"][A.DIRECTIONS[0]]["spread_n_per_m"]["fz"]
    dump(path, ref)
    with pytest.raises(ValueError):
        A.load_reference(path)


def test_reference_does_not_accept_a_model_a_se_as_an_implicit_spread(tmp_path):
    ref = reference()
    ref["directions"][A.DIRECTIONS[0]]["se_g_n_per_m"] = 0.1
    del ref["directions"][A.DIRECTIONS[0]]["spread_n_per_m"]
    path = tmp_path / "reference.json"
    dump(path, ref)
    with pytest.raises(ValueError, match="spread"):
        A.load_reference(path)


def test_all_direction_labels_and_arm_labels(tmp_path):
    fixture(tmp_path / "quick")
    fixture(tmp_path / "quick_nobound", "quick_nobound", errors={A.DIRECTIONS[2]: 1.2})
    fixture(tmp_path / "cds", "cds", blocked=(A.DIRECTIONS[0],))
    fixture(tmp_path / "vanLeer", "vanLeer", blocked=A.DIRECTIONS)
    result = A.analyze_campaign(tmp_path, reference())
    assert result["arms"]["quick"]["label"] == "BOUNDED_ALL"
    assert result["arms"]["quick_nobound"]["agree_count"] == 3
    assert result["arms"]["quick_nobound"]["directions"][A.DIRECTIONS[2]]["agreement"] == "DISAGREE"
    assert result["arms"]["cds"]["label"] == "PARTIAL"
    assert result["arms"]["cds"]["directions"][A.DIRECTIONS[0]]["boundedness"] == "BLOCKED"
    assert result["arms"]["vanLeer"]["label"] == "BLOCKED_ALL"
    assert result["next_step"] == "GRAD01_DRAFT_ALLOWED"
    assert not any(result["qualification_flags"].values())
    json.dumps(result, allow_nan=False)


def test_both_force_components_required_and_near_zero_precedence(tmp_path):
    fixture(tmp_path / "quick")
    for arm in A.ARMS[1:]:
        fixture(tmp_path / arm, arm, blocked=A.DIRECTIONS)
    ref = reference()
    ref["directions"][A.DIRECTIONS[0]]["spread_n_per_m"]["fz"] = 10.0
    for identity_path in tmp_path.glob("*/run_identity.json"):
        identity = json.loads(identity_path.read_text())
        name = identity["reference"]["path"]
        SYNTHETIC_REFERENCES[name] = ref
        digest = synthetic_pin(name)
        identity["reference"] = {**ref, "path": name, "sha256": digest}
        identity["pins"][name] = identity["verified"][name] = digest
        dump(identity_path, identity)
        manifest(identity_path.parent)
    result = A.analyze_campaign(tmp_path, ref)
    assert result["arms"]["quick"]["directions"][A.DIRECTIONS[0]]["agreement"] == "NOT_EVALUABLE"
    assert result["next_step"] == "GRAD01_DRAFT_NOT_ALLOWED"


def test_precision_differences_and_control_side_arms_excluded_from_next_rule(tmp_path):
    fixture(tmp_path / "quick")
    fixture(tmp_path / "quick_nobound", "quick_nobound", blocked=A.DIRECTIONS)
    for arm in A.ARMS[2:]:
        fixture(tmp_path / arm, arm, blocked=A.DIRECTIONS)
    fixture(tmp_path / "quick_110", waterlily="1.10.0", plain_offset=1.0)
    fixture(tmp_path / "quick_f64", real_type="Float64", plain_offset=0.5)
    fixture(tmp_path / "quick_nobound_f64", "quick_nobound", real_type="Float64")
    result = A.analyze_campaign(tmp_path, reference())
    assert result["next_step"] == "GRAD01_DRAFT_NOT_ALLOWED"
    assert result["arms"]["quick_110"]["plain_minus_arm_a_n"]["fx"] == pytest.approx(1 / 900)
    assert result["precision_differences"]["quick"]["plain_f64_minus_f32_n"]["fx"] == pytest.approx(0.5 / 900)
    assert len(result["precision_differences"]["quick"]["directions"]) == 2


@pytest.mark.parametrize("key", sorted(A.REQUIRED_INDEX_KEYS))
def test_index_required_keys(tmp_path, key):
    out = tmp_path / "quick"
    fixture(out)
    patch(out, lambda index: index.pop(key))
    with pytest.raises(ValueError, match=key):
        A.verify_output(out, reference())


@pytest.mark.parametrize("damage", ["history_sha", "missing_history", "summary_sha", "lambda", "epsilon", "input_sha", "extra_run", "run_order", "flags", "preflight", "short_window", "onset", "primal"])
def test_corrupt_or_incomplete_output_fails_closed(tmp_path, damage):
    out = tmp_path / "quick"
    fixture(out, blocked=(A.DIRECTIONS[0],) if damage == "onset" else ())
    if damage == "history_sha":
        (out / "plain.history.csv").write_text("tamper")
    elif damage == "missing_history":
        (out / "plain.history.csv").unlink()
    elif damage == "summary_sha":
        (out / "plain.summary.json").write_text("{}")
    elif damage == "lambda":
        patch(out, lambda i: i.update(lambda_type="typeof(cds)"))
    elif damage == "epsilon":
        patch(out, lambda i: i["epsilon_m"].update({A.DIRECTIONS[0]: 0.002}))
    elif damage == "input_sha":
        patch(out, lambda i: i["input_sha256"].update(phi="0" * 64))
    elif damage == "extra_run":
        patch(out, lambda i: i["runs"].update(unexpected=i["runs"]["plain"]))
    elif damage == "run_order":
        g2 = json.loads((out / "g2_run_index.json").read_text())
        g2["run_order"] = ["plain"]
        dump(out / "g2_run_index.json", g2)
        manifest(out)
    elif damage == "flags":
        patch(out, lambda i: i["qualification_flags"].update(shape_update_allowed=True))
    elif damage == "preflight":
        patch(out, lambda i: i["preflight"].update({"pass": False}))
    elif damage == "short_window":
        patch(out, lambda i: i.update(window_t_u_l=[0.1, 0.2]))
    elif damage == "onset":
        patch(out, lambda i: i["runs"][A.DIRECTIONS[0]]["blocked"].pop("onset_step"))
    elif damage == "primal":
        patch(out, lambda i: i["runs"][A.DIRECTIONS[0]]["window_mean_fx_dual_time"].update(value=110.0))
    with pytest.raises(ValueError):
        A.verify_output(out, reference())


def test_watchdog_threshold_preserves_frozen_strict_greater_than_rule():
    assert A.boundedness({"status": "COMPLETE", "watchdog_max_tangent": 1e30, "blocked": None}) == "BOUNDED"
    with pytest.raises(ValueError):
        A.boundedness({"status": "COMPLETE", "watchdog_max_tangent": 1.0001e30, "blocked": None})


@pytest.mark.parametrize("value", [0.0, -0.001, 0.00500000001, True])
def test_reference_epsilon_respects_registered_amplitude(tmp_path, value):
    ref = reference()
    ref["directions"][A.DIRECTIONS[0]]["epsilon_m"] = value
    path = tmp_path / "ref.json"
    dump(path, ref)
    with pytest.raises(ValueError):
        A.load_reference(path)


@pytest.mark.parametrize("damage", ["verified", "tree", "source_pin", "missing_pin", "reference_pin", "reference_sha", "reference_definition", "exit", "arm", "raw_phi", "runtime"])
def test_runtime_identity_is_bound_to_committed_sources(tmp_path, damage):
    out = tmp_path / "quick"
    fixture(out)
    path = out / "run_identity.json"
    identity = json.loads(path.read_text())
    if damage == "verified":
        identity["verified"] = {}
    elif damage == "tree":
        identity["source_tree_id"] = "0" * 40
    elif damage == "source_pin":
        name = "scripts/grad_g2_window.py"
        identity["pins"][name] = identity["verified"][name] = "0" * 64
    elif damage == "missing_pin":
        identity["pins"].pop("scripts/quick_nobound.jl")
        identity["verified"].pop("scripts/quick_nobound.jl")
    elif damage == "reference_pin":
        identity["pins"].pop(identity["reference"]["path"])
        identity["verified"].pop(identity["reference"]["path"])
    elif damage == "reference_sha":
        identity["reference"]["sha256"] = "0" * 64
    elif damage == "reference_definition":
        identity["reference"]["definition"] = "different reference"
    elif damage == "exit":
        identity["spike_exit_code"] = 3
    elif damage == "arm":
        identity["arm"] = "cds"
    elif damage == "raw_phi":
        identity["phi_sha256"] = "0" * 64
    elif damage == "runtime":
        patch(out, lambda i: i.update(forwarddiff="1.4.6"))
    dump(path, identity)
    manifest(out)
    with pytest.raises(ValueError):
        A.verify_output(out, reference())


def test_actual_committed_directory_hash_matches_renderer(monkeypatch):
    monkeypatch.setattr(A, "committed_sha", REAL_COMMITTED_SHA)
    commit = A._git_output("rev-parse", "HEAD").decode().strip()
    assert REAL_COMMITTED_SHA(commit, "scripts/grad_g2_window.py") == working_sha(ROOT / "scripts/grad_g2_window.py")
    assert REAL_COMMITTED_SHA(commit, "julia/CFDSDFWaterLily/src") == working_sha(ROOT / "julia/CFDSDFWaterLily/src")


@pytest.mark.parametrize("field", ["input_phi_sha256", "input_tangent_sha256", "terminal_tangent"])
def test_actual_stored_inputs_and_terminal_tangents_verified(tmp_path, field):
    out = tmp_path / "quick"
    fixture(out)
    change_run(out, A.DIRECTIONS[0], lambda summary: summary.update({field: {"tan_max_u": None, "tan_max_p": None} if field == "terminal_tangent" else "0" * 64}))
    with pytest.raises(ValueError):
        A.verify_output(out, reference())


def test_sampling_cadence_and_summary_count_are_not_metadata_only(tmp_path):
    out = tmp_path / "quick"
    fixture(out)
    rows = W.read_history(out / "plain.history.csv")
    rows[1]["step"] = 17.0
    G.write_history(out / "plain.history.csv", rows)
    change_run(out, "plain", lambda summary: None)
    with pytest.raises(ValueError, match="cadence"):
        A.verify_output(out, reference())


def test_complete_terminal_overflow_does_not_get_a_bounded_label(tmp_path):
    out = tmp_path / "quick"
    fixture(out)
    change_run(out, A.DIRECTIONS[0], lambda summary: summary["terminal_tangent"].update(tan_max_u=1e31))
    with pytest.raises(ValueError, match="terminal"):
        A.verify_output(out, reference())


def test_blocked_requires_a_raw_watchdog_onset_witness(tmp_path):
    out = tmp_path / "quick"
    fixture(out, blocked=(A.DIRECTIONS[0],))
    path = out / f"{A.DIRECTIONS[0]}.watchdog.csv"
    path.write_text(path.read_text().replace("1e31", "0.5"))
    change_run(out, A.DIRECTIONS[0], lambda summary: summary.update(terminal_tangent={"tan_max_u": 0.5, "tan_max_p": 4.0}, watchdog_max_abs_tangent_u_finite=0.5))
    with pytest.raises(ValueError, match="onset"):
        A.verify_output(out, reference())


def test_force_sample_blocked_before_same_step_scheduled_watchdog_is_valid(tmp_path):
    out = tmp_path / "quick"
    fixture(out, blocked=(A.DIRECTIONS[0],))
    direction = A.DIRECTIONS[0]
    path = out / f"{direction}.watchdog.csv"
    header = path.read_text().splitlines()[0]
    path.write_text(header + "\n100,1.4,1,1;2;3;1,0.5,1;2;3,96,100,2,-200,-3,2,1\n")
    rows = []
    for step in range(8, 201, 8):
        row = {key: 0.0 for key in W.HEADER}
        row.update(step=float(step), t_u_l=step * 0.014, fx=100.0, fz=-200.0)
        if step == 200:
            row["fx_tan"] = float("nan")
        rows.append(row)
    G.write_history(out / f"{direction}.history.csv", rows)
    blocked = {"reason": "non_finite_tangent_in_force_sample", "onset_step": 200, "tan_max_u": None, "tan_max_p": 0.5, "tan_argmax_u": "1;2;3;1", "tan_argmax_p": "1;2;3"}
    dump(out / f"{direction}.blocked.json", blocked)
    change_run(out, direction, lambda s: s.update(steps=200, sample_count=len(rows), blocked=blocked, watchdog_onset=blocked,
                                                 terminal_tangent={"tan_max_u": None, "tan_max_p": 0.5}, watchdog_max_abs_tangent_u_finite=1.0, watchdog_max_abs_tangent_p_finite=0.5))
    checked = A.verify_output(out, reference())
    assert checked["runs"][direction]["status"] == "BLOCKED"


def test_final_analysis_requires_all_four_primary_arms(tmp_path):
    fixture(tmp_path / "quick")
    with pytest.raises(ValueError, match="all four primary"):
        A.analyze_campaign(tmp_path, reference())


def test_synthetic_and_measured_classes_cannot_be_mixed(tmp_path):
    for arm in A.ARMS:
        fixture(tmp_path / arm, arm)
    patch(tmp_path / "cds", lambda i: i.update(evidence_class="exploratory_lambda_swap_forward_ad_measurement"))
    with pytest.raises(ValueError, match="cannot be mixed"):
        A.analyze_campaign(tmp_path, reference())


def test_precision_rows_keep_blocked_status_and_fd_difference(tmp_path):
    for arm in A.ARMS:
        fixture(tmp_path / arm, arm, blocked=A.DIRECTIONS if arm == "quick_nobound" else ())
    fixture(tmp_path / "quick_nobound_f64", "quick_nobound", real_type="Float64")
    result = A.analyze_campaign(tmp_path, reference())
    rows = result["precision_differences"]["quick_nobound"]["directions"]
    assert set(rows) == set(A.DIRECTIONS[:2])
    assert rows[A.DIRECTIONS[0]]["float32_status"] == "BLOCKED"
    assert rows[A.DIRECTIONS[0]]["tangent_f64_minus_f32_n_per_m"] == {"fx": None, "fz": None}
    assert rows[A.DIRECTIONS[0]]["fd_f64_minus_f32_n_per_m"]["fx"] == pytest.approx(0.0)
    assert result["arms"]["quick_nobound"]["directions"][A.DIRECTIONS[0]]["agreement"] is None
    assert result["arms"]["quick_nobound"]["directions"][A.DIRECTIONS[0]]["rows"]["fx"]["fd_n_per_m"] != 0.0


def test_write_is_exclusive_and_sidecar_is_verified(tmp_path):
    path = tmp_path / "analysis.json"
    result = {"kind": "synthetic_grad00_test"}
    A.write_analysis(path, result)
    assert path.with_suffix(".json.sha256").read_text().strip() == A.sha256(path)
    with pytest.raises(FileExistsError):
        A.write_analysis(path, {"changed": True})
    assert json.loads(path.read_text()) == result


def test_cli_without_reference_never_writes_or_labels(tmp_path):
    fixture(tmp_path / "quick")
    checked = subprocess.run([sys.executable, str(ROOT / "scripts/analyze_grad00.py"), str(tmp_path), "--check"], capture_output=True, text=True)
    assert checked.returncode != 0 and "reference" in checked.stderr.lower()
    assert not (tmp_path / "analysis.json").exists()
    assert "BOUNDED_ALL" not in checked.stdout


def test_cli_refuses_existing_output_before_loading_missing_inputs(tmp_path):
    path = tmp_path / "analysis.json"
    path.write_text("preserve")
    done = subprocess.run([sys.executable, str(ROOT / "scripts/analyze_grad00.py"), str(tmp_path), "--write", str(path), "--reference", "missing.json"], capture_output=True, text=True)
    assert done.returncode != 0 and "overwrite" in done.stderr
    assert path.read_text() == "preserve"
