"""OPT-01 v1 Stage B analyzer: check_kernel replayed over the REAL retained OPT-01 Stage A kernel output (identity regenerated), negatives, ladder verdicts, gate-rejected steps, end-to-end."""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_opt01b as A  # noqa: E402
import opt01b_contract as C  # noqa: E402
import opt01b_states as L  # noqa: E402

EV = ROOT / "docs/evidence/opt01b_stage_b_2026_10_15"
A1 = ROOT / "docs/evidence/opt01a_stage_a_2026_10_15"
INV = json.loads((EV / "inventory.json").read_text())
REAL_FREEZE = json.loads((A1 / "prerun_freeze.json").read_text())
GRIDS = {"a": "flow_24", "b": "flow_32"}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def replay(tmp, kernel, mutate=None, after_manifest=None):
    """A seven-state output built from the real retained OPT-01 Stage A parent run (real CSV, summary, GPU and identity files) with the expected identity regenerated."""
    grid, real = GRIDS[kernel], A1 / f"kernel_output/opt01a_{kernel}"
    out = Path(tmp) / f"k{kernel}"
    shutil.copytree(real, out, ignore=shutil.ignore_patterns("states", "output_manifest.json", "opt01a_index.json", "*.log"))
    ident = json.loads((out / "run_identity.json").read_text())
    ident["baseline_csv_sha256"] = INV["grids"][kernel]["baseline_reference"]["forces_csv_sha256"]
    (out / "run_identity.json").write_text(json.dumps(ident))
    template = next(e for e in json.loads((real / "opt01a_index.json").read_text())["states"] if e["name"] == "opt01a__parent")
    src = real / "states/opt01a__parent"
    entries = []
    for row in INV["states"]:
        d = out / "states" / row["name"]
        d.mkdir(parents=True)
        shutil.copy(src / f"{grid}.forces.csv", d / f"{grid}.forces.csv"); shutil.copy(src / "W4_JOB_DONE", d / "W4_JOB_DONE")
        s = json.loads((src / f"{grid}.summary.json").read_text())
        s.update({"phi_fortran_sha256": row["phi_fortran_order_sha256"], "phi_c_order_sha256": row["phi_c_order_sha256"], "state_sha256": row["state_sha256"],
                  "state_npz_sha256": row["npz_sha256"], "device_roundtrip_sha256": row["phi_fortran_order_sha256"], "phi_margin_m": row["zero_level_margin_m"]})
        (d / f"{grid}.summary.json").write_text(json.dumps(s))
        entries.append({**template, "name": row["name"], "kind": row["kind"], "direction": row["direction"], "step_mm": row["step_mm"], "sign": row["sign"], "forces_csv_sha256": sha(d / f"{grid}.forces.csv")})
    (out / "opt01b_index.json").write_text(json.dumps({"kernel": kernel, "kernel_id": ident["kernel_id"], "case_id": grid, "states": entries, "status": "COMPLETE",
                                                       "solver_process_wall_seconds_total": sum(e["seconds"] for e in entries)}))
    if mutate:
        mutate(out, grid)
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))
    if after_manifest:
        after_manifest(out, grid)
    return out


def freeze_for_replay():
    f = {"kind": A.FREEZE_KIND, "frozen_parameters": A.FROZEN_PARAMETERS, "inventory_sha256": sha(EV / "inventory.json"), "file_hashes": {}, "source_commit": REAL_FREEZE["source_commit"],
         "qualification_flags": {"optimizer": False, "shape_update_allowed": False}, "selected_delta": None, "runtime": REAL_FREEZE["runtime"], "pins": REAL_FREEZE["pins"]}
    try:
        f["source_tree_id"] = A.git_tree_sha(f["source_commit"])
    except Exception:  # noqa: BLE001
        pytest.skip("the retained OPT-01 Stage A source commit is not available locally")
    return f


def test_check_kernel_replay_over_the_real_retained_output_passes(tmp_path):
    f = freeze_for_replay()
    for k in ("a", "b"):
        states = A.check_kernel(replay(tmp_path, k), k, f, INV)
        assert list(states) == [r["name"] for r in INV["states"]] and states[L.PARENT_NAME]["downforce_n"] == pytest.approx(INV["grids"][k]["baseline_reference"]["host_recomputed_n"]["downforce"], rel=1e-12)


def test_the_parent_must_be_byte_identical_to_the_retained_reference(tmp_path):
    def append_newline(out, grid):
        p = out / "states" / L.PARENT_NAME / f"{grid}.forces.csv"; p.write_bytes(p.read_bytes() + b"\n")
        idx = json.loads((out / "opt01b_index.json").read_text()); idx["states"][0]["forces_csv_sha256"] = sha(p); (out / "opt01b_index.json").write_text(json.dumps(idx))
    with pytest.raises(ValueError, match="byte-identical"):
        A.check_kernel(replay(tmp_path, "a", mutate=append_newline), "a", freeze_for_replay(), INV)


def test_a_fortran_c_hash_swap_a_missing_done_and_a_post_manifest_edit_all_fail(tmp_path):
    f = freeze_for_replay()

    def swap(out, grid):
        p = out / "states" / L.candidate_name(0.625) / f"{grid}.summary.json"; s = json.loads(p.read_text())
        s["phi_fortran_sha256"], s["phi_c_order_sha256"] = s["phi_c_order_sha256"], s["phi_fortran_sha256"]; p.write_text(json.dumps(s))
    with pytest.raises(ValueError, match="phi_fortran_sha256"):
        A.check_kernel(replay(tmp_path / "1", "a", mutate=swap), "a", f, INV)
    with pytest.raises(ValueError, match="DONE"):
        A.check_kernel(replay(tmp_path / "2", "a", mutate=lambda o, g: (o / "DONE").unlink()), "a", f, INV)
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        A.check_kernel(replay(tmp_path / "3", "a", after_manifest=lambda o, g: (o / "nvidia_smi.csv").write_text("x")), "a", f, INV)


def all_eligible():
    """The registered inventory with every positive step gate-eligible, so that the rule tests below do not depend on which steps the real gates rejected."""
    inv = copy.deepcopy(INV)
    for r in inv["states"]:
        if r["kind"] == "candidate":
            r["pre_cfd_gates"].update(eligible_for_acceptance=True, gate_rejected=False, failed=[], all_pass=True)
    return inv


def ladder_states(per_step):
    """per_step[step] = ((d_down24, d_drag24), (d_down32, d_drag32)); the parent forces are fixed; reverse states move the opposite way."""
    base = {"flow_24": {"downforce_n": 0.33, "drag_n": 0.32}, "flow_32": {"downforce_n": 0.36, "drag_n": 0.35}}
    states = {g: {L.PARENT_NAME: dict(base[g])} for g in C.GRIDS}
    for s in L.STEPS_MM:
        for gi, g in enumerate(C.GRIDS):
            dd, dr = per_step[s][gi]
            states[g][L.candidate_name(s)] = {"downforce_n": base[g]["downforce_n"] + dd, "drag_n": base[g]["drag_n"] + dr}
    for s in L.CONTROL_STEPS_MM:
        for gi, g in enumerate(C.GRIDS):
            dd, dr = per_step[s][gi]
            states[g][L.control_name(s)] = {"downforce_n": base[g]["downforce_n"] - dd, "drag_n": base[g]["drag_n"] - dr}
    return states


FLAGS = {"qualification_flags": {"optimizer": False}}
GOOD = {0.3125: ((3.5e-5, -1e-5), (9e-5, -1e-5)), 0.625: ((6e-5, -1e-5), (2e-4, -2e-5)), 0.9375: ((5e-5, -1e-5), (3e-4, -2e-5)), 1.25: ((1.9e-5, -1e-5), (4e-4, -2e-5))}


def test_ladder_selects_the_largest_minimum_gain_ignores_reverse_diagnostics_and_records_the_lineage():
    inv = all_eligible()
    r = A.analysis_report(ladder_states(GOOD), inv, FLAGS)
    assert r["verdict"] == "OPT01_V1_ACCEPT" and r["selected"] == "opt01b__prop__s0.625mm" and r["selected_step_mm"] == 0.625 and r["closes_issue_30"] is True
    assert r["candidates"]["opt01b__prop__s1.25mm"]["accepted"] is False and r["integrity"]["pass"] and r["shape_update_allowed"] is False and r["selected_delta"] is None
    assert r["lineage"]["child_generation_if_selected"] == INV["parent"]["generation"] + 1 and r["lineage"]["selected_child"] == next(x for x in INV["states"] if x["name"] == r["selected"])["if_selected_lineage"]
    assert r["lineage"]["selected_child"]["generation"] == INV["parent"]["generation"] + 1 and r["lineage"]["parent_state_sha256"] == INV["parent"]["state_sha256"]
    assert set(r["reverse_controls_diagnostic_never_eligible"]) == {L.control_name(s) for s in L.CONTROL_STEPS_MM} and set(r["hindcast_vs_stage_a_descriptive"]) == {f"{s:g}" for s in L.STEPS_MM}


def test_a_gate_rejected_step_is_ineligible_whatever_its_responses_and_all_rejected_is_reject():
    inv = all_eligible()
    row = next(x for x in inv["states"] if x["name"] == "opt01b__prop__s0.625mm")  # the step that would win
    row["pre_cfd_gates"]["table"]["near_zero_gradient_band"] = "fail"
    row["pre_cfd_gates"].update(failed=["near_zero_gradient_band"], all_pass=False, gate_rejected=True, eligible_for_acceptance=False)
    r = A.analysis_report(ladder_states(GOOD), inv, FLAGS)
    assert r["candidates"]["opt01b__prop__s0.625mm"]["accepted"] is False and r["candidates"]["opt01b__prop__s0.625mm"]["gate_rejected"] is True
    assert r["verdict"] == "OPT01_V1_ACCEPT" and r["selected"] == "opt01b__prop__s0.9375mm" and r["gate_rejected_steps"] == {"opt01b__prop__s0.625mm": ["near_zero_gradient_band"]}
    for x in inv["states"]:
        if x["kind"] == "candidate":
            x["pre_cfd_gates"].update(failed=["near_zero_gradient_band"], all_pass=False, gate_rejected=True, eligible_for_acceptance=False)
    none = A.analysis_report(ladder_states(GOOD), inv, FLAGS)
    assert none["verdict"] == "OPT01_V1_REJECT" and none["selected"] is None and none["lineage"]["selected_child"] is None and none["lineage"]["outcome"] == "rollback: keep the parent" and none["closes_issue_30"] is True


def test_a_positive_drag_change_on_either_grid_blocks_acceptance_and_nothing_accepted_is_reject():
    per = {s: ((6e-5, -1e-5), (6e-5, 1e-6)) for s in L.STEPS_MM}
    r = A.analysis_report(ladder_states(per), all_eligible(), FLAGS)
    assert r["verdict"] == "OPT01_V1_REJECT" and r["selected"] is None and not any(c["accepted"] for c in r["candidates"].values())


def test_end_to_end_replay_has_integrity_and_reject_and_a_broken_input_is_incomplete(tmp_path, monkeypatch):
    f = freeze_for_replay()
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)  # registration validation is covered by test_opt01b_inputs
    r = A.analyze(replay(tmp_path / "x", "a"), replay(tmp_path / "x", "b"), f, INV)
    assert r["integrity"]["pass"] is True and r["verdict"] == "OPT01_V1_REJECT" and r["closes_issue_30"] is True  # identical states: no gain anywhere
    bad = A.analyze(tmp_path / "missing_a", tmp_path / "missing_b", f, INV)
    assert bad["integrity"]["pass"] is False and bad["verdict"] == "OPT01_V1_INCOMPLETE" and bad["closes_issue_30"] is False
