"""G2 terminal verifier and bridge analyzer on synthetic outputs: pass path, fail-closed paths, no-delta rule."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_bridge as analyzer
from scripts import grad_g2_window as W
from scripts import verify_grad_g2_terminal as verifier
from tests import grad_g2_synthetic as syn


@pytest.fixture()
def good(tmp_path):
    freeze = syn.freeze_stub()
    out = tmp_path / "out"
    plain = syn.build_output(out, freeze)
    formal = tmp_path / "formal.json"
    syn.formal_stub(formal, plain)
    return out, freeze, formal


def run(out, freeze, formal):
    return verifier.verify(out, freeze, formal)


def test_consistent_output_passes_and_the_tangent_is_scaled_to_n_per_m(good):
    out, freeze, formal = good
    result = run(out, freeze, formal)
    assert result["status"] == "PASS_G2_TERMINAL_INTEGRITY", result["problems"]
    assert result["integrity"]["plain_vs_formal_baseline_v17"]["rel_drag"] < 1e-12
    assert set(result["runs"]) == {"plain", *syn.DIRECTIONS}


@pytest.mark.parametrize("damage", ["no_done", "error_file", "extra_history", "missing_run", "bad_pin", "bad_sha", "not_t4",
                                    "zero_tangent", "primal_gate", "baseline_gate", "window_short", "summary_mismatch",
                                    "summary_missing", "summary_wrong_label"])
def test_every_damage_is_rejected(good, damage):
    out, freeze, formal = good
    if damage == "no_done":
        (out / "DONE").unlink()
    elif damage == "error_file":
        (out / "ERROR.txt").write_text("boom")
    elif damage == "extra_history":
        shutil.copy(out / "D0_interface_offset.history.csv", out / "D9_extra.history.csv")
    elif damage == "missing_run":
        (out / "P1_upstream_lobe.history.csv").unlink()
    elif damage == "bad_pin":
        freeze = copy.deepcopy(freeze); freeze["pins"]["scripts/x.jl"] = "0" * 64
    elif damage == "bad_sha":
        (out / "plain.summary.json").write_text((out / "plain.summary.json").read_text() + " ")
    elif damage == "not_t4":
        index = json.loads((out / "g2_run_index.json").read_text()); index["gpu_name"] = "Tesla V100"
        (out / "g2_run_index.json").write_text(json.dumps(index))
    elif damage == "zero_tangent":
        rows = syn.make_rows(0.0, k=1.0)
        for r in rows:
            for c in r:
                if c.endswith("_tan"):
                    r[c] = 0.0
        syn.write_history(out / "D0_interface_offset.history.csv", rows)
    elif damage == "primal_gate":
        rows = syn.make_rows(0.0, k=1.0)
        for r in rows:
            r["fx"] *= 1.01
        syn.write_history(out / "D0_interface_offset.history.csv", rows)
    elif damage == "baseline_gate":
        formal.write_text(formal.read_text().replace('"drag_n": ', '"drag_n": 1'))
    elif damage == "window_short":
        syn.write_history(out / "D1_filtered_seed11.history.csv", syn.make_rows(0.0, k=2.0, steps=range(8, 6000, 8)))
    elif damage == "summary_missing":
        (out / "D1_filtered_seed11.summary.json").unlink()
    elif damage == "summary_wrong_label":
        summary = json.loads((out / "D0_interface_offset.summary.json").read_text()); summary["label"] = "other"
        (out / "D0_interface_offset.summary.json").write_text(json.dumps(summary))
    elif damage == "summary_mismatch":
        summary = json.loads((out / "D2_filtered_seed2026.summary.json").read_text())
        summary["window_mean_fx_dual_time"]["tangent"] *= 1.001
        (out / "D2_filtered_seed2026.summary.json").write_text(json.dumps(summary))
    if damage in ("bad_sha", "extra_history", "missing_run", "zero_tangent", "primal_gate", "window_short", "summary_mismatch", "error_file", "no_done"):
        pass  # the manifest is intentionally NOT refreshed, so tampering also trips the output SHA check where relevant
    assert run(out, freeze, formal)["status"] == "FAIL_G2_TERMINAL_INTEGRITY"


def test_analyzer_refuses_a_failed_verification_and_never_sets_delta(good):
    out, freeze, formal = good
    record = json.loads(analyzer.SCOPE_RECORD.read_text())
    verification = run(out, freeze, formal)
    bridge = analyzer.analyze(verification, record)
    assert bridge["row_count"] == 8 and bridge["selected_delta"] is None and bridge["grad03_verdict"] is None
    assert bridge["refit"] is False and bridge["reverse"] == "untouched" and set(bridge["qualification_flags"].values()) == {False}
    assert {r["response_id"] for r in bridge["rows"]} == {"drag", "downforce"}
    first = bridge["rows"][0]
    expected = verification["runs"]["D0_interface_offset"]["fx_dual_time"]["tangent"] * W.FORCE_SCALE_N_PER_SOLVER
    assert first["g_forward_n_per_m"] == expected and first["direction_id"] == "D0_interface_offset"
    assert bridge["aggregate"]["sign_mismatch_count"] == sum(not r["sign_match"] for r in bridge["rows"])
    failed = copy.deepcopy(verification); failed["status"] = "FAIL_G2_TERMINAL_INTEGRITY"
    with pytest.raises(ValueError):
        analyzer.analyze(failed, record)


def test_analyzer_reads_the_immutable_scope_record():
    import hashlib
    assert hashlib.sha256(analyzer.SCOPE_RECORD.read_bytes()).hexdigest() == analyzer.SCOPE_RECORD_SHA256
    record = json.loads(analyzer.SCOPE_RECORD.read_text())
    assert len(record["rows"]) == 8 and all(r["g_hat_n_per_m"] != 0 for r in record["rows"])
    assert record["grad01_bridge"]["relative_error_tolerance"] is None
