"""LOWDIM-04 Stage B inventory: re-derivation, identity table, parent gate, hard count, proposal binding; strict freeze validation negatives."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_lowdim04b as A  # noqa: E402
import build_lowdim04b_inputs as B  # noqa: E402
import lowdim04b_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402

EV = ROOT / "docs/evidence/lowdim04b_stage_b_2026_10_13"
INV = json.loads((EV / "inventory.json").read_text())


@pytest.fixture(scope="module")
def rederived():
    return B.build()


def test_inventory_and_raw_inputs_are_reproduced_from_the_stage_a_analysis(rederived):
    inv, raw_parent, raw_prop = rederived
    assert canonical_json(inv) == (EV / "inventory.json").read_bytes() and raw_parent == B.PARENT_RAW.read_bytes() and raw_prop == B.PROPOSAL_RAW.read_bytes()
    assert (EV / "inventory.json.sha256").read_text().strip() == B.sha(EV / "inventory.json")


def test_the_proposal_is_the_stage_a_robust_solution_and_stage_a_is_pinned():
    a = json.loads((ROOT / INV["stage_a"]["analysis_path"]).read_text())
    assert B.sha(ROOT / INV["stage_a"]["analysis_path"]) == INV["stage_a"]["analysis_sha256"] == B.STAGE_A_ANALYSIS_SHA and a["verdict"] == "LOCAL_FEASIBLE_CONE_FOUND"
    assert INV["proposal"]["coefficient_vector"] == a["solutions"]["robust_cross_grid"]["coefficient_vector"]
    assert INV["proposal"]["m_max_abs_sum"] == pytest.approx(a["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["m_max_abs_sum"], rel=1e-12)
    assert S.sha256_bytes(B.PROPOSAL_RAW.read_bytes()) == INV["proposal"]["sha256_fortran_raw"]


def test_identity_table_has_four_named_hashes_and_the_runner_order_regenerates_each_state(rederived):
    inv, _, _ = rederived
    parent, prop = S.read_f4(B.PARENT_RAW), S.read_f4(B.PROPOSAL_RAW)
    for row in inv["states"]:
        assert len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) == 2 and all(len(row[k]) == 64 for k in ("state_sha256", "npz_sha256"))
        phi = parent if row["kind"] == "parent" else S.perturb(parent, prop, row["step_mm"], row["sign"])
        assert S.sha256_bytes(S.to_raw(phi)) == row["phi_fortran_order_sha256"]
    assert inv["states"][0]["phi_fortran_order_sha256"] == B.PARENT_FORTRAN_SHA


def test_seven_states_parent_first_same_plan_on_both_grids_all_at_n_max_with_the_parent_reference():
    assert [r["name"] for r in INV["states"]] == [r["name"] for r in L.plan()] and len(INV["states"]) == 7
    assert INV["kernels"]["a"] == INV["kernels"]["b"] == [r["name"] for r in INV["states"]]
    for r in INV["states"]:
        assert r["hard_count"]["sampled_solid_centers"] == 8272 and r["geometry_gates"]["all_hard_gates_pass"] is True
        assert r["hard_count"]["count_equal_margin_m"] > 0 or r["kind"] == "parent"
    for g in INV["grids"].values():
        ref = g["baseline_reference"]
        assert "lowdim03__prop__s1.25mm" in ref["forces_csv_path"] and B.sha(ROOT / ref["forces_csv_path"]) == ref["forces_csv_sha256"] and g["measurement"]["solver_wall_time_cap_s"] == 6300


def complete_freeze(tmp_path):
    import build_lowdim04b_kernel as K
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    infra, runtime = tmp_path / "infra", {}
    for k, grid in (("a", "flow_24"), ("b", "flow_32")):
        d = infra / f"kernel_lowdim04b_{k}"; d.mkdir(parents=True)
        (d / "runner.py").write_text(K.render(head, k)); (d / "kernel-metadata.json").write_text(json.dumps(K.metadata(k), sort_keys=True, indent=2) + "\n")
        runtime[k] = {**A.RUNTIME_FIXED, "kernel_id": K.KERNEL_IDS[k], "case_id": grid, "runner_sha256": B.sha(d / "runner.py"), "metadata_sha256": B.sha(d / "kernel-metadata.json")}
    required = A.REQUIRED_FILES | {INV["parent"]["raw_path"]} | {g["baseline_reference"]["forces_csv_path"] for g in INV["grids"].values()} | {INV["proposal"]["file"], INV["stage_a"]["analysis_path"], A.STAGE_A_INVENTORY} | {d["path"] for d in INV["directions"].values()}
    proof = {"all_free": True, "owner": "ramhachi888"}
    (tmp_path / "identity_free_check.json").write_text(json.dumps(proof))
    freeze = {"kind": A.FREEZE_KIND, "frozen_parameters": A.FROZEN_PARAMETERS, "inventory_sha256": B.sha(EV / "inventory.json"), "file_hashes": {p: B.sha(ROOT / p) for p in sorted(required)},
              "source_commit": head, "source_tree_id": A.git_tree_sha(head), "qualification_flags": {k: False for k in A.FLAGS}, "selected_delta": None, "reinitialization": "none",
              "identity_free_check": proof, "parent_integration_commit": A.PARENT_INTEGRATION_COMMIT, "runtime": runtime, "pins": {k: K.pins(k) for k in ("a", "b")}}
    return freeze, infra


def test_registration_validation_accepts_a_complete_freeze_and_rejects_each_weakening(tmp_path):
    freeze, infra = complete_freeze(tmp_path)
    ident = tmp_path / "identity_free_check.json"
    A.validate_registration(freeze, INV, infra=infra, identity=ident)
    mutations = {
        "inflated per-state budget": lambda f: f["runtime"]["a"].update(per_state_timeout_s=5000), "inflated aggregate cap": lambda f: f["runtime"]["b"].update(solver_wall_time_cap_s=99999),
        "omitted analyzer hash": lambda f: f["file_hashes"].pop("scripts/analyze_lowdim04b.py"), "omitted stage a analysis": lambda f: f["file_hashes"].pop(INV["stage_a"]["analysis_path"]),
        "wrong file hash": lambda f: f["file_hashes"].update({"scripts/lowdim04b_states.py": "0" * 64}), "flag true": lambda f: f["qualification_flags"].update(optimizer=True),
        "selected delta": lambda f: f.update(selected_delta=1.0), "frozen parameter": lambda f: f["frozen_parameters"].update(min_downforce_gain_n=1e-6), "wrong tree id": lambda f: f.update(source_tree_id="0" * 40),
        "pin tampered": lambda f: f["pins"]["a"].update({next(iter(f["pins"]["a"])): "0" * 64}), "identity differs from the record": lambda f: f.update(identity_free_check={"all_free": True, "owner": "ramhachi888", "x": 1}),
        "wrong parent commit": lambda f: f.update(parent_integration_commit="0" * 40), "kernel id": lambda f: f["runtime"]["a"].update(kernel_id="ramhachi888/other")}
    for label, mutate in mutations.items():
        bad = copy.deepcopy(freeze); mutate(bad)
        with pytest.raises(ValueError):
            A.validate_registration(bad, INV, infra=infra, identity=ident)
    bad_inv = copy.deepcopy(INV); bad_inv["states"][1]["hard_count"]["residual_vs_n_max"] = 1
    with pytest.raises(ValueError):
        A.validate_registration(freeze, bad_inv, infra=infra, identity=ident)
    bad_inv = copy.deepcopy(INV); bad_inv["stage_a"]["analysis_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        A.validate_registration(freeze, bad_inv, infra=infra, identity=ident)
    (infra / "kernel_lowdim04b_a/runner.py").write_text((infra / "kernel_lowdim04b_a/runner.py").read_text() + "\n# edited\n")
    with pytest.raises(ValueError, match="rendered worker"):
        A.validate_registration(freeze, INV, infra=infra, identity=ident)


def test_freeze_closure_contains_every_project_file_the_host_scripts_import():
    import freeze_lowdim04b as F
    closure = F.project_closure()
    must = {"scripts/analyze_lowdim04b.py", "scripts/build_lowdim04b_inputs.py", "scripts/build_lowdim04b_kernel.py", "scripts/freeze_lowdim04b.py", "scripts/lowdim04b_contract.py", "scripts/lowdim04b_states.py",
            "scripts/step01_states.py", "scripts/grid01_gpu.py", "scripts/build_lowdim04a_inputs.py", "scripts/build_lowdim01_inputs.py", "scripts/lowdim01_states.py", "src/cfd_sdf/lowdim03_contract.py",
            "src/cfd_sdf/design/volume_semantics_v2.py", "src/cfd_sdf/fd08_v2_campaign.py"}
    assert must <= closure and all(not p.startswith("/") for p in closure)
