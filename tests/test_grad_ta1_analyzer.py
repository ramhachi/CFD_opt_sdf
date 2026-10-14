"""GRAD-TA1 analyzer on synthetic kernel outputs: the GRAD-01 row rule (sign, delta edge, floor branch, additive secondary), AGREE / DISAGREE, and the BLOCKED /
INCOMPLETE / primal-gate paths.  The synthetic G2-layout output builder is tests/grad_g2_synthetic.py (the kernel keeps the G2 output layout)."""
import copy
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import analyze_grad_g2_bridge as bridge_mod
from scripts import analyze_grad_ta1 as A
from scripts import grad_g2_window as W
from scripts import verify_grad_g2_terminal as verifier
from tests import grad_g2_synthetic as syn

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads(bridge_mod.SCOPE_RECORD.read_text())


# ---------------------------------------------------------------------------------------------------------------- the GRAD-01 row rule
def test_relative_rule_delta_edge_is_inclusive():
    assert A.grad01_row(5.0, 4.0, 0.01)["passed"] is True                            # |g - g_hat| / |g_hat| = 0.25 exactly
    row = A.grad01_row(5.0001, 4.0, 0.01)
    assert row["passed"] is False and row["reason"] == "relative_error" and row["error_rule"] == "relative"
    assert A.grad01_row(3.0, 4.0, 0.01)["passed"] is True and A.grad01_row(2.99, 4.0, 0.01)["passed"] is False


def test_sign_mismatch_is_reported_before_the_magnitude():
    row = A.grad01_row(-1.0, 4.0, 0.01)
    assert row["passed"] is False and row["reason"] == "sign_mismatch" and row["sign_match"] is False
    assert A.grad01_row(0.0, 4.0, 0.01)["reason"] == "sign_mismatch"                # a zero tangent has no sign (the rule's sign 0 != +1)
    assert A.grad01_row(-5.0, -4.0, 0.01)["passed"] is True                         # negative slopes: relative to |g_hat|


def test_near_zero_oracle_row_uses_only_the_3_se_floor():
    row = A.grad01_row(0.1, 0.05, 0.02)                                              # |g_hat| = 0.05 <= 3 SE = 0.06
    assert row["error_rule"] == "absolute_noise_floor" and row["relative_error"] is None and row["sign_match"] is None
    assert row["passed"] is True and row["tolerance_applied"] == pytest.approx(0.06)
    assert A.grad01_row(0.12, 0.05, 0.02)["reason"] == "absolute_error"
    assert A.grad01_row(-0.005, 0.05, 0.02)["passed"] is True                       # sign is unresolved there, as in the rule


def test_additive_form_is_secondary_and_reports_its_effective_tolerance():
    row = A.grad01_row(1.3, 1.0, 0.1)                                                # rel 0.30 > 0.25, but 0.25 + 3 SE = 0.55
    assert row["passed"] is False and row["additive_form_passed_secondary"] is True
    assert row["additive_effective_relative_tolerance"] == pytest.approx(0.55)


def test_fd08_oracle_rows_are_all_above_the_floor_so_the_rule_is_option_b():
    assert len(RECORD["rows"]) == 8
    assert all(abs(r["g_hat_n_per_m"]) > 3 * r["se_g_n_per_m"] for r in RECORD["rows"])
    assert A.RELATIVE_ERROR_TOLERANCE == 0.25 and A.NOISE_FLOOR_SE_MULTIPLE == 3.0


def test_rule_mirrors_the_registered_comparison_function_source():
    source = (ROOT / "src/cfd_sdf/gradients/directional_comparison.py").read_text()
    for fragment in ("near_zero = abs(finite_difference) <= float(fd.absolute_noise_floor)", "relative_error = absolute_error / abs(finite_difference)",
                     "passed = sign_match and relative_error <= tolerance", "passed = absolute_error <= tolerance"):
        assert fragment in source


def test_vector_metrics_cosine_and_relative_l2():
    rows = [{"response_id": r, "direction_id": f"d{i}", "g_forward_n_per_m": g, "g_hat_fd08_modelA_n_per_m": h}
            for r in ("drag", "downforce") for i, (g, h) in enumerate(((3.0, 3.0), (4.0, 4.0), (0.0, 0.0), (5.0, 12.0)))]
    m = A.vector_metrics(rows)["drag"]
    assert m["relative_l2"] == pytest.approx(7.0 / math.sqrt(9 + 16 + 144))
    assert m["cosine"] == pytest.approx((9 + 16 + 60) / (math.sqrt(9 + 16 + 25) * math.sqrt(9 + 16 + 144)))


# ---------------------------------------------------------------------------------------------------------------- synthetic kernel outputs
QUICK_T, TIE_T = "typeof(quick)", "WaterLily.QuickTie{Float32}"


def freeze_stub():
    return {**syn.freeze_stub(), "file_hashes": {A.ANALYZER_FREEZE_KEY: A.sha256(A.__file__)}}


def refresh_manifest(out):
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))


def patch_index(out, **changes):
    index = json.loads((out / "g2_run_index.json").read_text())
    index.update(changes)
    (out / "g2_run_index.json").write_text(json.dumps(index))
    refresh_manifest(out)


def build_ta1(tmp_path):
    freeze = freeze_stub()
    out = tmp_path / "out"
    plain = syn.build_output(out, freeze)
    pre = {"pass": True, "primal_u_bit_equal": True, "primal_p_bit_equal": True, "steps": 20,
           "arms": {"quick": {"lambda_type": QUICK_T}, "quick_tie": {"lambda_type": TIE_T}}}
    status = {n: "COMPLETE" for n in ["plain", *syn.DIRECTIONS]}
    types = {n: (QUICK_T if n == "plain" else TIE_T) for n in status}
    index = json.loads((out / "g2_run_index.json").read_text())
    index.update({"lambda_types": types, "tau": 1e-5, "dual_width": 1, "preflight": pre, "run_status": status})
    (out / "g2_run_index.json").write_text(json.dumps(index))
    for label, t in types.items():
        path = out / f"{label}.summary.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "lambda_type": t}))
    for label in syn.DIRECTIONS:                                                    # a calm watchdog history
        (out / f"{label}.watchdog.csv").write_text("step,t_u_l,tan_max_u,tan_argmax_u,tan_max_p,tan_argmax_p,last_sample_step,fx,fx_tan,fz,fz_tan,elapsed_s,vram_bytes\n"
                                                   "100,1.4,0.5,1;2;3;1,0.7,4;5;6,96,1.0,1.0,1.0,1.0,3.0,1\n200,2.7,0.4,1;2;3;1,0.6,4;5;6,192,1.0,1.0,1.0,1.0,6.0,1\n")
    refresh_manifest(out)
    formal = tmp_path / "formal.json"
    syn.formal_stub(formal, plain)
    return out, freeze, formal


def record_for(out, freeze, formal, errors):
    """An oracle record whose g_hat gives each TA1 row the given signed relative deviation g = (1 + e) g_hat."""
    verification = verifier.verify(out, freeze, formal)
    assert verification["status"].startswith("PASS"), verification["problems"]
    record = copy.deepcopy(RECORD)
    for r in record["rows"]:
        key = "fx" if r["response_id"] == "drag" else "fz"
        g = verification["runs"][r["direction_id"]][f"{key}_dual_time"]["tangent"] * W.FORCE_SCALE_N_PER_SOLVER
        e = errors.get((r["direction_id"], r["response_id"]), errors.get("default", 0.0))
        r["g_hat_n_per_m"] = g / (1.0 + e)
        r["se_g_n_per_m"] = abs(r["g_hat_n_per_m"]) * 0.03
    return record


def analyze(out, freeze, formal, record):
    return A.analyze_output(out, freeze, record, formal)


@pytest.fixture()
def good(tmp_path):
    return build_ta1(tmp_path)


def test_all_rows_within_the_rule_is_agree(good):
    out, freeze, formal = good
    result = analyze(out, freeze, formal, record_for(out, freeze, formal, {"default": 0.2}))
    assert result["verdict"] == "GRAD_TA1_AGREE" and result["failed_rows"] == [] and result["option_b_equivalent"] is True
    assert len(result["rows"]) == 8 and all(r["grad01"]["passed"] for r in result["rows"])
    assert set(result["vector_metrics"]) == {"drag", "downforce"}
    assert set(result["qualification_flags"].values()) == {False} and result["grad03_verdict"] is None
    assert set(result["runs"]) == {"plain", *syn.DIRECTIONS} and result["runs"]["D0_interface_offset"]["tangent_history_every_100_steps"][0]["step"] == 100.0
    json.dumps(result, allow_nan=False)


def test_one_row_beyond_delta_is_disagree_and_names_the_row(good):
    out, freeze, formal = good
    errors = {"default": 0.1, ("D2_filtered_seed2026", "downforce"): 0.26}
    result = analyze(out, freeze, formal, record_for(out, freeze, formal, errors))
    assert result["verdict"] == "GRAD_TA1_DISAGREE"
    assert result["failed_rows"] == [("D2_filtered_seed2026", "downforce", "relative_error")] or result["failed_rows"] == [["D2_filtered_seed2026", "downforce", "relative_error"]]


def test_a_sign_flip_is_disagree(good):
    out, freeze, formal = good
    result = analyze(out, freeze, formal, record_for(out, freeze, formal, {"default": 0.0, ("D0_interface_offset", "drag"): -2.0}))   # g = -g_hat
    assert result["verdict"] == "GRAD_TA1_DISAGREE" and list(result["failed_rows"][0])[2] == "sign_mismatch"


def test_the_floor_branch_cannot_rescue_a_row_in_the_synthetic_pipeline(good):
    out, freeze, formal = good
    record = record_for(out, freeze, formal, {"default": 0.0})
    for r in record["rows"]:
        r["se_g_n_per_m"] = abs(r["g_hat_n_per_m"])                                  # 3 SE > |g_hat|: every row is on the absolute-floor branch
    result = analyze(out, freeze, formal, record)
    assert result["verdict"] == "GRAD_TA1_AGREE" and result["option_b_equivalent"] is False
    assert all(r["grad01"]["error_rule"] == "absolute_noise_floor" for r in result["rows"])


def test_frozen_time_is_reported_but_the_verdict_uses_dual_time(good):
    out, freeze, formal = good
    result = analyze(out, freeze, formal, record_for(out, freeze, formal, {"default": 0.0}))
    row = result["rows"][0]
    assert "g_forward_frozen_time_n_per_m" in row and row["grad01"]["absolute_error"] == pytest.approx(0.0, abs=1e-12)
    assert result["rule"]["comparator"].startswith("dual_time")


# ---------------------------------------------------------------------------------------------------------------- BLOCKED
def make_blocked(out):
    blocked = {"reason": "tangent_non_finite_or_above_limit", "onset_step": 1200, "t_u_l": 16.4, "tan_max_u": None, "tan_argmax_u": "3;4;5;1", "tan_max_p": 1e31,
               "tan_argmax_p": "7;8;9", "limit": 1e30}
    (out / "D0_interface_offset.blocked.json").write_text(json.dumps(blocked))
    (out / "D0_interface_offset.watchdog.csv").write_text("step,t_u_l,tan_max_u,tan_argmax_u,tan_max_p,tan_argmax_p,last_sample_step,fx,fx_tan,fz,fz_tan,elapsed_s,vram_bytes\n"
                                                         "1100,15.0,3.0,1;2;3;1,4.0,4;5;6,1096,1.0,1.0,1.0,1.0,30.0,1\n1200,16.4,NaN,3;4;5;1,Inf,7;8;9,1192,1.0,NaN,1.0,1.0,40.0,1\n")
    summary = json.loads((out / "D0_interface_offset.summary.json").read_text())
    summary.update({"status": "BLOCKED", "blocked": blocked})
    (out / "D0_interface_offset.summary.json").write_text(json.dumps(summary))
    index = json.loads((out / "g2_run_index.json").read_text())
    index["run_status"]["D0_interface_offset"] = "BLOCKED"
    index.update({"status": "BLOCKED", "blocked_runs": ["D0_interface_offset"]})
    (out / "g2_run_index.json").write_text(json.dumps(index))
    identity = json.loads((out / "run_identity.json").read_text()); identity["spike_exit_code"] = 3
    (out / "run_identity.json").write_text(json.dumps(identity))
    refresh_manifest(out)


def test_a_blocked_tangent_is_blocked_with_onset_and_location(good):
    out, freeze, formal = good
    make_blocked(out)
    result = analyze(out, freeze, formal, RECORD)
    assert result["verdict"] == "GRAD_TA1_BLOCKED" and "rows" not in result
    assert result["blocked"]["D0_interface_offset"]["onset_step"] == 1200 and result["blocked"]["D0_interface_offset"]["tan_argmax_p"] == "7;8;9"
    history = result["runs"]["D0_interface_offset"]["tangent_history_every_100_steps"]
    assert history[1]["tan_max_u"] == "NaN" and history[0]["tan_max_u"] == 3.0 and result["runs"]["D0_interface_offset"]["tangent_max_over_run"] == 4.0
    json.dumps(result, allow_nan=False)


def test_blocked_with_a_broken_manifest_is_incomplete_not_blocked(good):
    out, freeze, formal = good
    make_blocked(out)
    (out / "D0_interface_offset.blocked.json").write_text("{}")                    # tamper without refreshing the manifest
    assert analyze(out, freeze, formal, RECORD)["verdict"] == "GRAD_TA1_INCOMPLETE"


def test_blocked_status_without_a_blocked_run_is_incomplete(good):
    out, freeze, formal = good
    patch_index(out, status="BLOCKED", blocked_runs=[])
    result = analyze(out, freeze, formal, RECORD)
    assert result["verdict"] == "GRAD_TA1_INCOMPLETE" and any("BLOCKED" in p for p in result["problems"])


# ---------------------------------------------------------------------------------------------------------------- INCOMPLETE
@pytest.mark.parametrize("damage", ["preflight_failed", "preflight_not_bit_equal", "preflight_missing", "kernel_error", "wall_abort", "not_quicktie", "dual_ran_quick", "plain_ran_quicktie", "summary_type_missing", "preflight_arm_type", "tau", "width",
                                    "bad_pin", "bad_commit", "no_done", "plain_not_complete", "not_t4", "primal_gate", "baseline_gate", "bad_sha"])
def test_every_integrity_failure_is_incomplete(good, damage):
    out, freeze, formal = good
    record = record_for(out, freeze, formal, {"default": 0.0})
    pre = {"pass": True, "primal_u_bit_equal": True, "primal_p_bit_equal": True, "arms": {"quick": {"lambda_type": QUICK_T}, "quick_tie": {"lambda_type": TIE_T}}}
    types = json.loads((out / "g2_run_index.json").read_text())["lambda_types"]
    if damage == "preflight_failed":
        patch_index(out, preflight={**pre, "pass": False})
    elif damage == "preflight_not_bit_equal":
        patch_index(out, preflight={**pre, "primal_p_bit_equal": False})
    elif damage == "preflight_missing":
        index = json.loads((out / "g2_run_index.json").read_text()); del index["preflight"]
        (out / "g2_run_index.json").write_text(json.dumps(index)); refresh_manifest(out)
    elif damage == "kernel_error":
        patch_index(out, status="ERROR", error="boom")
    elif damage == "wall_abort":
        patch_index(out, status="ERROR", error="D1: wall-time abort (500 s > 400 s = 8.0 x the plain run)")
    elif damage == "not_quicktie":
        patch_index(out, lambda_types={**types, "D1_filtered_seed11": QUICK_T})
    elif damage == "dual_ran_quick":                                                 # the recorded summary says quick although the index claims QuickTie
        path = out / "D0_interface_offset.summary.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "lambda_type": QUICK_T})); refresh_manifest(out)
    elif damage == "plain_ran_quicktie":
        patch_index(out, lambda_types={**types, "plain": TIE_T})
    elif damage == "summary_type_missing":
        path = out / "P1_upstream_lobe.summary.json"
        summary = json.loads(path.read_text()); del summary["lambda_type"]
        path.write_text(json.dumps(summary)); refresh_manifest(out)
    elif damage == "preflight_arm_type":                                             # both preflight arms ran quick: the QuickTie arm was never routed
        patch_index(out, preflight={**pre, "arms": {"quick": {"lambda_type": QUICK_T}, "quick_tie": {"lambda_type": QUICK_T}}})
    elif damage == "tau":
        patch_index(out, tau=1e-4)
    elif damage == "width":
        patch_index(out, dual_width=2)
    elif damage == "bad_pin":
        freeze = copy.deepcopy(freeze); freeze["pins"]["scripts/x.jl"] = "0" * 64
    elif damage == "bad_commit":
        freeze = {**freeze, "source_commit": "c" * 40}
    elif damage == "no_done":
        (out / "DONE").unlink()
    elif damage == "plain_not_complete":
        patch_index(out, run_status={"plain": "ERROR"})
    elif damage == "not_t4":
        patch_index(out, gpu_name="Tesla V100")
    elif damage == "primal_gate":                                                    # a Dual window-mean primal 1% off the plain run (C1: gate 1e-3)
        rows = syn.make_rows(0.0, k=1.0)
        for r in rows:
            r["fx"] *= 1.01
        syn.write_history(out / "D0_interface_offset.history.csv", rows); refresh_manifest(out)
    elif damage == "baseline_gate":                                                  # plain vs the registered baseline_v17 (C1: gate 1e-6)
        formal.write_text(formal.read_text().replace('"drag_n": ', '"drag_n": 1'))
    elif damage == "bad_sha":
        (out / "plain.summary.json").write_text((out / "plain.summary.json").read_text() + " ")
    result = analyze(out, freeze, formal, record)
    assert result["verdict"] == "GRAD_TA1_INCOMPLETE" and result["problems"]


def test_primal_gate_is_the_g2_gate_not_bit_identity(good):
    out, freeze, formal = good
    rows = syn.make_rows(0.0, k=1.0)
    for r in rows:
        r["fx"] *= 1.0 + 2e-4                                                        # a Dual primal 2e-4 off the plain run is inside C1's 1e-3 window-mean gate
    syn.write_history(out / "D0_interface_offset.history.csv", rows)
    summary = syn.summary_for(rows, "D0_interface_offset", "Dual")
    summary["lambda_type"] = TIE_T
    (out / "D0_interface_offset.summary.json").write_text(json.dumps(summary)); refresh_manifest(out)
    assert verifier.PRIMAL_GATE == 1e-3 and verifier.BASELINE_GATE == 1e-6
    result = analyze(out, freeze, formal, record_for(out, freeze, formal, {"default": 0.0}))
    assert result["verdict"] == "GRAD_TA1_AGREE"
    assert 0 < result["integrity"]["D0_interface_offset"]["window_mean_primal_rel_diff_max"] <= 1e-3


def test_a_missing_index_is_incomplete(good):
    out, freeze, formal = good
    (out / "g2_run_index.json").unlink()
    assert analyze(out, freeze, formal, RECORD)["verdict"] == "GRAD_TA1_INCOMPLETE"


# ---------------------------------------------------------------------------------------------------------------- CLI
def cli(tmp_path, out, freeze, formal, *args, record=None):
    freeze_path = tmp_path.parent / (tmp_path.name + "_freeze") / "prerun_freeze.json"
    if not freeze_path.exists():
        freeze_path.parent.mkdir()
        freeze_path.write_text(json.dumps(freeze, sort_keys=True))
        freeze_path.with_name(freeze_path.name + ".sha256").write_text(hashlib.sha256(freeze_path.read_bytes()).hexdigest() + "\n")
    code = ("import sys, json; sys.path.insert(0, 'scripts'); import verify_grad_g2_terminal as V; V.FORMAL_VERIFICATION = __import__('pathlib').Path(sys.argv[1]); "
            "import analyze_grad_ta1 as A; sys.argv = ['analyze_grad_ta1.py'] + sys.argv[2:]; A.main()")
    return subprocess.run([sys.executable, "-c", code, str(formal), str(out), "--freeze", str(freeze_path), *args], cwd=ROOT, capture_output=True, text=True)


def test_check_writes_nothing_and_write_is_single_shot(good, tmp_path):
    out, freeze, formal = good
    make_blocked(out)                                                                # a verdict that does not depend on the real FD-08 numbers
    before = sorted(p.name for p in tmp_path.rglob("*"))
    checked = cli(tmp_path, out, freeze, formal, "--check")
    assert checked.returncode == 0 and checked.stdout.splitlines()[0] == "GRAD_TA1_BLOCKED", checked.stderr
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    target = tmp_path / "analysis.json"
    written = cli(tmp_path, out, freeze, formal, "--write", str(target))
    assert written.returncode == 0 and json.loads(target.read_text())["verdict"] == "GRAD_TA1_BLOCKED"
    assert target.with_name("analysis.json.sha256").read_text().strip() == hashlib.sha256(target.read_bytes()).hexdigest()
    again = cli(tmp_path, out, freeze, formal, "--write", str(target))
    assert again.returncode != 0 and "refusing to overwrite" in again.stderr


def test_the_analyzer_refuses_to_run_if_its_bytes_differ_from_the_freeze(good, tmp_path):
    out, freeze, formal = good
    freeze = {**freeze, "file_hashes": {A.ANALYZER_FREEZE_KEY: "0" * 64}}
    result = cli(tmp_path, out, freeze, formal, "--check")
    assert result.returncode != 0 and "frozen bytes" in result.stderr
