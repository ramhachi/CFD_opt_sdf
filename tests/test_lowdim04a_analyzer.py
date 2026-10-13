"""LOWDIM-04A Stage A analyzer: check_kernel replayed over the REAL retained LOWDIM-03 kernel output (expected hashes swapped), negatives, end-to-end."""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_lowdim04a as A  # noqa: E402
import lowdim04a_contract as C  # noqa: E402
import lowdim04a_states as L  # noqa: E402

EV = ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13"
L3 = ROOT / "docs/evidence/lowdim03_dual_grid_primal_2026_10_10"
INV = json.loads((EV / "inventory.json").read_text())
REAL_FREEZE = json.loads((L3 / "prerun_freeze.json").read_text())
GRIDS = {"a": "flow_24", "b": "flow_32"}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def replay(tmp, kernel, mutate=None, after_manifest=None, forces=None):
    """A nine-state output built from the real retained LOWDIM-03 s1.25 mm run (its real CSV/summary/GPU/identity files), with only the expected identity swapped."""
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
        shutil.copy(src / f"{grid}.forces.csv", d / f"{grid}.forces.csv")
        shutil.copy(src / "W4_JOB_DONE", d / "W4_JOB_DONE")
        s = json.loads((src / f"{grid}.summary.json").read_text())
        s.update({"phi_fortran_sha256": row["phi_fortran_order_sha256"], "phi_c_order_sha256": row["phi_c_order_sha256"], "state_sha256": row["state_sha256"],
                  "state_npz_sha256": row["npz_sha256"], "device_roundtrip_sha256": row["phi_fortran_order_sha256"], "phi_margin_m": row["zero_level_margin_m"]})
        (d / f"{grid}.summary.json").write_text(json.dumps(s))
        entries.append({**template, "name": row["name"], "kind": row["kind"], "direction": row["direction"], "step_mm": row["step_mm"], "sign": row["sign"],
                        "forces_csv_sha256": sha(d / f"{grid}.forces.csv")})
    index = {"kernel": kernel, "kernel_id": ident["kernel_id"], "case_id": grid, "states": entries, "status": "COMPLETE", "solver_process_wall_seconds_total": sum(e["seconds"] for e in entries)}
    (out / "lowdim04a_index.json").write_text(json.dumps(index))
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
    def append_newline(out, grid):  # same force values, different bytes: only the byte-identity gate can catch it
        p = out / "states" / L.PARENT_NAME / f"{grid}.forces.csv"; p.write_bytes(p.read_bytes() + b"\n")
        idx = json.loads((out / "lowdim04a_index.json").read_text()); idx["states"][0]["forces_csv_sha256"] = sha(p); (out / "lowdim04a_index.json").write_text(json.dumps(idx))
    with pytest.raises(ValueError, match="byte-identical"):
        A.check_kernel(replay(tmp_path, "a", mutate=append_newline), "a", freeze_for_replay(), INV)


def test_a_fortran_c_hash_swap_a_missing_done_and_a_post_manifest_edit_all_fail(tmp_path):
    f = freeze_for_replay()

    def swap(out, grid):
        p = out / "states" / L.state_name("D0_interface_offset", 1) / f"{grid}.summary.json"; s = json.loads(p.read_text())
        s["phi_fortran_sha256"], s["phi_c_order_sha256"] = s["phi_c_order_sha256"], s["phi_fortran_sha256"]; p.write_text(json.dumps(s))
    with pytest.raises(ValueError, match="phi_fortran_sha256"):
        A.check_kernel(replay(tmp_path / "1", "a", mutate=swap), "a", f, INV)
    with pytest.raises(ValueError, match="DONE"):
        A.check_kernel(replay(tmp_path / "2", "a", mutate=lambda o, g: (o / "DONE").unlink()), "a", f, INV)
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        A.check_kernel(replay(tmp_path / "3", "a", after_manifest=lambda o, g: (o / "nvidia_smi.csv").write_text("x")), "a", f, INV)


def linear_states(g_lift, g_drag, scale=1.0):
    """Synthetic forces R(+-s) = R0 +- g s, matching the inventory's names; g in N/m per (grid, basis)."""
    states = {}
    for gi, grid in enumerate(C.GRIDS):
        states[grid] = {L.PARENT_NAME: {"downforce_n": 0.33, "drag_n": 0.32}}
        for di, d in enumerate(L.BASIS):
            for sign in (-1, 1):
                states[grid][L.state_name(d, sign)] = {"downforce_n": 0.33 + sign * scale * g_lift[gi][di] * C.STEP_M, "drag_n": 0.32 + sign * scale * g_drag[gi][di] * C.STEP_M}
    return states


FREEZE_FLAGS = {"qualification_flags": {"optimizer": False}}
LIFT = [[0.78, -0.11, -0.10, -0.38], [0.94, 0.06, -0.15, -0.48]]
DRAG = [[-0.11, -0.07, -0.17, -0.21], [0.19, -0.11, -0.15, -0.06]]


def test_analysis_reproduces_the_secants_and_finds_the_cone():
    r = A.analysis_report(linear_states(LIFT, DRAG), INV, FREEZE_FLAGS)
    assert r["verdict"] == "LOCAL_FEASIBLE_CONE_FOUND" and r["unresolved_count"] == 0 and r["integrity"]["pass"]
    assert r["secants"]["flow_24"]["downforce"]["D0_interface_offset"]["g_sec_n_per_m"] == pytest.approx(0.78)  # the registered 1.25 mm step, not 2.5 mm
    assert r["solutions"]["all_solutions_verified"] and r["shape_update_allowed"] is False and r["selected_delta"] is None
    vp = r["volume_projection"]
    assert "constrains no physical" in vp["meaning"] and set(vp["main_cross_grid"]) >= {"d0_coefficient_m", "predicted_v_cont_m3_change_m3", "predicted_v_eps_m3_change_vs_parent"}


def test_unresolved_components_are_reported_and_never_make_the_analysis_incomplete():
    tiny = [[0.78, -0.11, -0.10, -0.38], [0.94, 0.06, -0.15, 0.005]]  # flow_32 P1 downforce contrast 2*0.005*1.25e-3 = 1.25e-5 N < 3e-5
    r = A.analysis_report(linear_states(tiny, DRAG), INV, FREEZE_FLAGS)
    assert r["integrity"]["pass"] and "flow_32|downforce|P1_upstream_lobe" in r["unresolved_components"] and r["verdict"] in C.TERMINALS


def test_end_to_end_replay_has_integrity_and_a_not_found_verdict_and_a_broken_input_is_incomplete(tmp_path):
    f = freeze_for_replay()
    r = A.analyze(replay(tmp_path / "x", "a"), replay(tmp_path / "x", "b"), f, INV)
    assert r["integrity"]["pass"] is True and r["verdict"] == "LOCAL_FEASIBLE_CONE_NOT_FOUND"  # identical states: every secant is zero, so there is no cone
    bad = A.analyze(tmp_path / "missing_a", tmp_path / "missing_b", f, INV)
    assert bad["integrity"]["pass"] is False and bad["verdict"] == "LOWDIM04A_INCOMPLETE"
