"""LOWDIM-04A Stage A inventory: re-derivation, identity table, parent gate, hard count; freeze validation negatives."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_lowdim04a as A  # noqa: E402
import build_lowdim04a_inputs as B  # noqa: E402
import lowdim04a_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from build_grid01_inputs import canonical_json  # noqa: E402

EV = ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13"
INV = json.loads((EV / "inventory.json").read_text())


@pytest.fixture(scope="module")
def rederived():
    return B.build()


def test_inventory_and_parent_raw_are_reproduced_from_retained_inputs(rederived):
    inv, raw = rederived
    assert canonical_json(inv) == (EV / "inventory.json").read_bytes() and raw == B.PARENT_RAW.read_bytes()
    assert (EV / "inventory.json.sha256").read_text().strip() == B.sha(EV / "inventory.json")


def test_identity_table_has_four_named_hashes_and_consumers_use_the_right_order(rederived):
    inv, _ = rederived
    parent = S.read_f4(B.PARENT_RAW)
    dirs = {n: S.read_f4(ROOT / inv["directions"][n]["path"]) for n in L.BASIS}
    for row in inv["states"]:
        assert len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) == 2 and all(len(row[k]) == 64 for k in ("state_sha256", "npz_sha256"))
        phi = parent if row["kind"] == "parent" else S.perturb(parent, dirs[row["direction"]], row["step_mm"], row["sign"])
        assert S.sha256_bytes(S.to_raw(phi)) == row["phi_fortran_order_sha256"]  # the runner and device round trip pin the Fortran order
    assert inv["states"][0]["phi_fortran_order_sha256"] == B.PARENT_FORTRAN_SHA == INV["parent"]["phi_fortran_order_sha256"]


def test_nine_states_parent_first_same_plan_on_both_grids_all_at_n_max():
    assert [r["name"] for r in INV["states"]] == [r["name"] for r in L.plan()]
    assert INV["kernels"]["a"] == INV["kernels"]["b"] == [r["name"] for r in INV["states"]] and INV["states"][0]["kind"] == "parent"
    for r in INV["states"]:
        assert r["hard_count"]["residual_vs_n_max"] == 0 and r["hard_count"]["sampled_solid_centers"] == 8272
        assert r["hard_count"]["count_equal_margin_m"] > 0 or r["kind"] == "parent"
        assert r["geometry_gates"]["all_hard_gates_pass"] is True


def test_parent_reference_is_the_retained_lowdim03_run_of_the_identical_bytes():
    for k, g in INV["grids"].items():
        ref = g["baseline_reference"]
        assert "lowdim03__prop__s1.25mm" in ref["forces_csv_path"] and B.sha(ROOT / ref["forces_csv_path"]) == ref["forces_csv_sha256"]


def complete_freeze(tmp_path):
    """A complete, valid freeze fixture: rendered workers in a temp infra dir, real file hashes, real pins (the source commit is HEAD; rendering does not contact anything)."""
    import build_lowdim04a_kernel as K
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    infra, runtime = tmp_path / "infra", {}
    for k, grid in (("a", "flow_24"), ("b", "flow_32")):
        d = infra / f"kernel_lowdim04a_{k}"; d.mkdir(parents=True)
        (d / "runner.py").write_text(K.render(head, k)); (d / "kernel-metadata.json").write_text(json.dumps(K.metadata(k), sort_keys=True, indent=2) + "\n")
        runtime[k] = {**A.RUNTIME_FIXED, "kernel_id": K.KERNEL_IDS[k], "case_id": grid, "runner_sha256": B.sha(d / "runner.py"), "metadata_sha256": B.sha(d / "kernel-metadata.json")}
    required = A.REQUIRED_FILES | {INV["parent"]["raw_path"]} | {g["baseline_reference"]["forces_csv_path"] for g in INV["grids"].values()} | {d["path"] for d in INV["directions"].values()}
    proof = {"all_free": True, "owner": "ramhachi888"}
    (tmp_path / "identity_free_check.json").write_text(json.dumps(proof))
    freeze = {"kind": A.FREEZE_KIND, "frozen_parameters": A.FROZEN_PARAMETERS, "inventory_sha256": B.sha(EV / "inventory.json"), "file_hashes": {p: B.sha(ROOT / p) for p in sorted(required)},
              "source_commit": head, "source_tree_id": A.git_tree_sha(head), "qualification_flags": {k: False for k in A.FLAGS}, "selected_delta": None, "reinitialization": "none",
              "identity_free_check": proof, "parent_integration_commit": A.PARENT_INTEGRATION_COMMIT, "runtime": runtime, "pins": {k: K.pins(k) for k in ("a", "b")}}
    return freeze, infra


def test_registration_validation_accepts_a_complete_freeze(tmp_path):
    freeze, infra = complete_freeze(tmp_path)
    A.validate_registration(freeze, INV, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_registration_validation_rejects_each_weakening(tmp_path):
    freeze, infra = complete_freeze(tmp_path)
    mutations = {
        "inflated per-state budget": lambda f: f["runtime"]["a"].update(per_state_timeout_s=5000),
        "inflated aggregate cap": lambda f: f["runtime"]["b"].update(solver_wall_time_cap_s=99999),
        "omitted analyzer hash": lambda f: f["file_hashes"].pop("scripts/analyze_lowdim04a.py"),
        "wrong file hash": lambda f: f["file_hashes"].update({"scripts/lowdim04a_states.py": "0" * 64}),
        "flag true": lambda f: f["qualification_flags"].update(optimizer=True),
        "flag missing": lambda f: f["qualification_flags"].pop("topology"),
        "selected delta": lambda f: f.update(selected_delta=1.0),
        "frozen parameter": lambda f: f["frozen_parameters"].update(epsilon_n_per_m=0.006),
        "wrong tree id": lambda f: f.update(source_tree_id="0" * 40),
        "pin tampered": lambda f: f["pins"]["a"].update({next(iter(f["pins"]["a"])): "0" * 64}),
        "identity check absent": lambda f: f.update(identity_free_check={}),
        "identity check differs from the record": lambda f: f.update(identity_free_check={"all_free": True, "owner": "ramhachi888", "x": 1}),
        "wrong parent commit": lambda f: f.update(parent_integration_commit="0" * 40),
        "kernel id": lambda f: f["runtime"]["a"].update(kernel_id="ramhachi888/other"),
    }
    for label, mutate in mutations.items():
        bad = copy.deepcopy(freeze); mutate(bad)
        with pytest.raises(ValueError):
            A.validate_registration(bad, INV, infra=infra, identity=tmp_path / "identity_free_check.json")
    (infra / "kernel_lowdim04a_a/runner.py").write_text((infra / "kernel_lowdim04a_a/runner.py").read_text() + "\n# edited\n")
    with pytest.raises(ValueError, match="rendered worker"):
        A.validate_registration(freeze, INV, infra=infra, identity=tmp_path / "identity_free_check.json")
    bad_inv = copy.deepcopy(INV); bad_inv["states"][1]["hard_count"]["residual_vs_n_max"] = 1
    with pytest.raises(ValueError):
        A.validate_registration(freeze, bad_inv, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_the_eight_perturbation_hashes_equal_the_recorded_blocker_hashes():
    blocker = json.loads((ROOT / "docs/evidence/lowdim04_dual_grid_local_model_2026_10_11/pre_registration_blocker.json").read_text())["existing_lowdim_geometry_preflight"]["states"]
    rows = {r["name"]: r for r in INV["states"]}
    assert len(blocker) == 8
    for s in blocker:
        assert rows[s["state_name"]]["phi_fortran_order_sha256"] == s["phi_fortran_sha256"] and rows[s["state_name"]]["state_sha256"] == s["state_sha256"]


def test_freeze_closure_contains_every_project_file_the_host_scripts_import():
    import freeze_lowdim04a as F
    closure = F.project_closure()
    must = {"scripts/analyze_lowdim04a.py", "scripts/build_lowdim04a_inputs.py", "scripts/build_lowdim04a_kernel.py", "scripts/freeze_lowdim04a.py", "scripts/lowdim04a_contract.py",
            "scripts/lowdim04a_states.py", "scripts/step01_states.py", "scripts/grid01_gpu.py", "scripts/build_lowdim01_inputs.py", "scripts/fd08_v2_campaign_io.py",
            "src/cfd_sdf/grid01_contract.py", "src/cfd_sdf/design/volume_semantics_v2.py", "src/cfd_sdf/fd08_v2_campaign.py"}
    assert must <= closure and all(not p.startswith("/") for p in closure)
