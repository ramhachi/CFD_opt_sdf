"""LOWDIM-04 Stage B analyzer: check_kernel replayed over the REAL retained LOWDIM-03 kernel files (identity regenerated), negatives, ladder verdicts, end-to-end."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_lowdim04b as A  # noqa: E402
import lowdim04b_contract as C  # noqa: E402
import lowdim04b_states as L  # noqa: E402

EV = ROOT / "docs/evidence/lowdim04b_stage_b_2026_10_13"
L3 = ROOT / "docs/evidence/lowdim03_dual_grid_primal_2026_10_10"
INV = json.loads((EV / "inventory.json").read_text())
REAL_FREEZE = json.loads((L3 / "prerun_freeze.json").read_text())
GRIDS = {"a": "flow_24", "b": "flow_32"}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def replay(tmp, kernel, mutate=None, after_manifest=None):
    """A seven-state output built from the real retained LOWDIM-03 s1.25 mm run (real CSV, summary, GPU and identity files) with the expected identity regenerated."""
    grid, real = GRIDS[kernel], L3 / f"failed_attempt1/kernel_output/lowdim03_{kernel}"
    out = Path(tmp) / f"k{kernel}"
    shutil.copytree(real, out, ignore=shutil.ignore_patterns("states", "output_manifest.json", "lowdim03_index.json", "*.log"))
    ident = json.loads((out / "run_identity.json").read_text())
    ident["baseline_csv_sha256"] = INV["grids"][kernel]["baseline_reference"]["forces_csv_sha256"]
    (out / "run_identity.json").write_text(json.dumps(ident))
    template = next(e for e in json.loads((real / "lowdim03_index.json").read_text())["states"] if e["name"] == "lowdim03__prop__s1.25mm")
    src = real / "states/lowdim03__prop__s1.25mm"
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
    (out / "lowdim04b_index.json").write_text(json.dumps({"kernel": kernel, "kernel_id": ident["kernel_id"], "case_id": grid, "states": entries, "status": "COMPLETE",
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
        pytest.skip("the retained LOWDIM-03 source commit is not available locally")
    return f


def test_check_kernel_replay_over_the_real_retained_output_passes(tmp_path):
    f = freeze_for_replay()
    for k in ("a", "b"):
        states = A.check_kernel(replay(tmp_path, k), k, f, INV)
        assert list(states) == [r["name"] for r in INV["states"]] and states[L.PARENT_NAME]["downforce_n"] == pytest.approx(INV["grids"][k]["baseline_reference"]["host_recomputed_n"]["downforce"], rel=1e-12)


def test_the_parent_must_be_byte_identical_to_the_retained_reference(tmp_path):
    def append_newline(out, grid):
        p = out / "states" / L.PARENT_NAME / f"{grid}.forces.csv"; p.write_bytes(p.read_bytes() + b"\n")
        idx = json.loads((out / "lowdim04b_index.json").read_text()); idx["states"][0]["forces_csv_sha256"] = sha(p); (out / "lowdim04b_index.json").write_text(json.dumps(idx))
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


def ladder_states(per_step, reverse=None):
    """per_step[step] = ((d_down24, d_drag24), (d_down32, d_drag32)); the parent forces are fixed; reverse states move the opposite way by default."""
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


def test_ladder_selects_the_largest_minimum_gain_and_ignores_reverse_diagnostics():
    per = {0.3125: ((3.5e-5, -1e-5), (9e-5, -1e-5)), 0.625: ((6e-5, -1e-5), (2e-4, -2e-5)), 0.9375: ((5e-5, -1e-5), (3e-4, -2e-5)), 1.25: ((1.9e-5, -1e-5), (4e-4, -2e-5))}
    r = A.analysis_report(ladder_states(per), INV, FLAGS)
    assert r["verdict"] == "LOWDIM04B_ACCEPT" and r["selected"] == "lowdim04b__prop__s0.625mm" and r["selected_step_mm"] == 0.625
    assert r["candidates"]["lowdim04b__prop__s1.25mm"]["accepted"] is False and r["integrity"]["pass"] and r["shape_update_allowed"] is False and r["selected_delta"] is None
    assert set(r["reverse_controls_diagnostic_never_eligible"]) == {L.control_name(s) for s in L.CONTROL_STEPS_MM} and "constrains no" not in r["interpretation"]
    assert set(r["hindcast_vs_stage_a_descriptive"]) == {f"{s:g}" for s in L.STEPS_MM}


def test_a_positive_drag_change_on_either_grid_blocks_acceptance_and_nothing_accepted_is_no_accept():
    per = {s: ((6e-5, -1e-5), (6e-5, 1e-6)) for s in L.STEPS_MM}
    r = A.analysis_report(ladder_states(per), INV, FLAGS)
    assert r["verdict"] == "LOWDIM04B_NO_ACCEPT" and r["selected"] is None and not any(c["accepted"] for c in r["candidates"].values())


def test_end_to_end_replay_has_integrity_and_no_accept_and_a_broken_input_is_incomplete(tmp_path, monkeypatch):
    f = freeze_for_replay()
    monkeypatch.setattr(A, "validate_registration", lambda *a, **k: None)  # registration validation is covered by test_lowdim04b_inputs
    r = A.analyze(replay(tmp_path / "x", "a"), replay(tmp_path / "x", "b"), f, INV)
    assert r["integrity"]["pass"] is True and r["verdict"] == "LOWDIM04B_NO_ACCEPT"  # identical states: no gain anywhere
    bad = A.analyze(tmp_path / "missing_a", tmp_path / "missing_b", f, INV)
    assert bad["integrity"]["pass"] is False and bad["verdict"] == "LOWDIM04B_INCOMPLETE"
