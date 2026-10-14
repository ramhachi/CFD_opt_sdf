"""OPT-01 v1 Stage A inventory: re-derivation of the identities, pre-CFD gates, parent gate, hard count, lineage; freeze validation negatives."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_opt01a as A  # noqa: E402
import build_opt01a_inputs as B  # noqa: E402
import opt01a_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf.fd08_v2_campaign import state_identity  # noqa: E402

EV = ROOT / "docs/evidence/opt01a_stage_a_2026_10_15"
INV = json.loads((EV / "inventory.json").read_text())


@pytest.fixture(scope="module")
def ctx():
    return B.context()  # reconstructs the 04B selected state and the nine states from retained inputs (cheap; the gates are not recomputed here)


def test_identities_parent_raw_and_npz_are_reproduced_from_retained_inputs(ctx):
    for row in INV["states"]:
        child, audit = ctx.states[row["name"]]
        ident = state_identity(child)
        assert all(ident[k] == row[k] for k in B.IDENTITY_KEYS) and audit["changed_node_count"] == row["changed_node_count"]
        assert len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) == 2 and all(len(row[k]) == 64 for k in ("state_sha256", "npz_sha256"))
    assert S.to_raw(ctx.parent.phi) == B.PARENT_RAW.read_bytes() and B.sha(B.PARENT_RAW) == INV["parent"]["phi_fortran_order_sha256"]
    assert (EV / "inventory.json.sha256").read_text().strip() == B.sha(EV / "inventory.json")
    assert B.sha(B.PARENT_NPZ) == INV["states"][0]["npz_sha256"]  # the committed NPZ is the parent's deterministic serialization


def test_new_parent_is_the_04b_selected_state_with_generation_plus_one_and_only_state_sha256_changes(ctx):
    lin = INV["parent"]["lineage"]["lowdim04b_selected_state"]
    old, new = state_identity(ctx.trial), state_identity(ctx.parent)
    assert lin["state_sha256"] == old["state_sha256"] != new["state_sha256"] == INV["parent"]["state_sha256"]
    assert lin["phi_fortran_order_sha256"] == new["phi_fortran_order_sha256"] and lin["phi_c_order_sha256"] == new["phi_c_order_sha256"]
    assert ctx.parent.generation == ctx.trial.generation + 1 == lin["generation"] + 1 == INV["parent"]["generation"]
    assert all(child.generation == ctx.parent.generation for child, _ in ctx.states.values())  # construct_state keeps the parent generation
    assert lin["inventory_row"] == B.TRIAL_ROW and lin["state_sha256"].startswith("64e4efb1")


BLOCKED_STATES = {"opt01a__D0_interface_offset__minus1.25mm": 284, "opt01a__D1_filtered_seed11__minus1.25mm": 40, "opt01a__D1_filtered_seed11__plus1.25mm": 153,
                  "opt01a__D2_filtered_seed2026__minus1.25mm": 3, "opt01a__D2_filtered_seed2026__plus1.25mm": 206, "opt01a__P1_upstream_lobe__plus1.25mm": 212}


def ready_copy(inv=None):
    """A synthetic READY inventory (the real one is BLOCKED_PRE_CFD): lets the runner/registration machinery be tested for a future re-registered stage."""
    inv = copy.deepcopy(INV if inv is None else inv)
    inv["stage_status"], inv["blockers"] = "READY", []
    for r in inv["states"]:
        r["pre_cfd_gates"].update(all_pass=True, failed=[], table={k: "pass" for k in r["pre_cfd_gates"]["table"]})
    return inv


def test_nine_states_parent_first_same_plan_on_both_grids_and_the_recorded_pre_cfd_result_is_a_blocker():
    assert [r["name"] for r in INV["states"]] == [r["name"] for r in L.plan()]
    assert INV["kernels"]["a"] == INV["kernels"]["b"] == [r["name"] for r in INV["states"]] and INV["states"][0]["kind"] == "parent" and len(INV["states"]) == 9
    assert INV["stage_status"] == "BLOCKED_PRE_CFD" and {b["state"]: b["failed"] for b in INV["blockers"]} == {n: ["near_zero_gradient_band"] for n in BLOCKED_STATES}
    for r in INV["states"]:
        g = r["pre_cfd_gates"]
        nz = g["record"]["geom02_v2"]["gates"]["near_zero_gradient_band"]["measured"]["nodes_below_threshold"]
        assert nz == BLOCKED_STATES.get(r["name"], 0) and g["geom02_v2_gate_count"] == 13
        assert g["failed"] == (["near_zero_gradient_band"] if nz else []) and g["geom02_v2_pass_count"] == (12 if nz else 13)
        assert g["table"]["p22_v2"] == g["table"]["retained_smoothed_volume_band"] == g["table"]["retained_clearance"] == g["table"]["count_equal_margin_positive"] == "pass"
        assert r["hard_count"]["residual_vs_n_max"] == 0 and r["hard_count"]["sampled_solid_centers"] <= 8272 and r["hard_count"]["count_equal_margin_m"] > 0
    parent = INV["states"][0]  # the E4 stop rule holds: the new parent passes everything, also from its own parent (the LOWDIM-03 parent)
    assert parent["pre_cfd_gates"]["all_pass"] is True and parent["pre_cfd_gates"]["e4_vs_lowdim03_parent"]["all_pass"] is True
    assert parent["hard_count"]["count_equal_margin_m"] == pytest.approx(2.199e-3, abs=2e-6)  # as recorded at the trial in the phase 1 evaluation


def test_gates_use_the_registered_profile_v2_crossing_slope_rule_for_every_state():
    profile = json.loads((ROOT / L.CONTRACT["pins"]["gate_profile_v2"]["path"]).read_text())
    for r in INV["states"]:
        bundle = r["pre_cfd_gates"]["record"]["geom02_v2"]
        assert bundle["profile_id"] == profile["profile_id"] and bundle["gates"]["near_zero_gradient_band"]["thresholds"]["rule"] == "crossing_slope_v1"


def test_parent_reference_is_the_retained_lowdim04b_run_of_the_identical_bytes():
    for k, g in INV["grids"].items():
        ref = g["baseline_reference"]
        assert "lowdim04b__prop__s0.3125mm" in ref["forces_csv_path"] and B.sha(ROOT / ref["forces_csv_path"]) == ref["forces_csv_sha256"]
        assert g["measurement"]["solver_wall_time_cap_s"] == 8100 and g["measurement"]["per_state_timeout_s"] == 900  # as LOWDIM-04A
    a04 = json.loads((ROOT / "docs/evidence/lowdim04a_stage_a_2026_10_13/inventory.json").read_text())
    for k in ("a", "b"):  # identical measurement to LOWDIM-04A except the claim string
        assert {x: y for x, y in INV["grids"][k]["measurement"].items() if x != "qualification_claim"} == {x: y for x, y in a04["grids"][k]["measurement"].items() if x != "qualification_claim"}
    assert INV["job_env_common"] == a04["job_env_common"] and INV["directions"] == {n: {"path": d["path"], "sha256_fortran_raw": d["sha256_fortran_raw"]} for n, d in a04["directions"].items()}


def test_inventory_binds_the_pinned_contract_and_every_contract_pin_verifies():
    assert INV["contract"]["sha256"] == L.CONTRACT_SHA256 == B.sha(ROOT / L.CONTRACT_REL) and INV["contract"]["pins_verified"] == B.verify_pins(L.CONTRACT) > 10
    bad = copy.deepcopy(L.CONTRACT); bad["pins"]["gate_code"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contract pin differs"):
        B.verify_pins(bad)
    assert L.STEP_MM == 1.25 and L.BASIS == tuple(S.SINGLE_DIRECTIONS) and A.FROZEN_PARAMETERS["epsilon_n_per_m"] == pytest.approx(0.012)


def complete_freeze(tmp_path):
    """A complete, valid freeze fixture: rendered workers in a temp infra dir, real file hashes, real pins (the source commit is HEAD; rendering does not contact anything)."""
    import build_opt01a_kernel as K
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    infra, runtime = tmp_path / "infra", {}
    for k, grid in (("a", "flow_24"), ("b", "flow_32")):
        d = infra / f"kernel_opt01a_{k}"; d.mkdir(parents=True)
        (d / "runner.py").write_text(K.render(head, k)); (d / "kernel-metadata.json").write_text(json.dumps(K.metadata(k), sort_keys=True, indent=2) + "\n")
        runtime[k] = {**A.RUNTIME_FIXED, "kernel_id": K.KERNEL_IDS[k], "case_id": grid, "runner_sha256": B.sha(d / "runner.py"), "metadata_sha256": B.sha(d / "kernel-metadata.json")}
    required = A.REQUIRED_FILES | {INV["parent"]["raw_path"]} | {g["baseline_reference"]["forces_csv_path"] for g in INV["grids"].values()} | {d["path"] for d in INV["directions"].values()}
    proof = {"all_free": True, "owner": "ramhachi888"}
    (tmp_path / "identity_free_check.json").write_text(json.dumps(proof))
    freeze = {"kind": A.FREEZE_KIND, "frozen_parameters": A.FROZEN_PARAMETERS, "inventory_sha256": B.sha(EV / "inventory.json"), "file_hashes": {p: B.sha(ROOT / p) for p in sorted(required)},
              "source_commit": head, "source_tree_id": A.git_tree_sha(head), "qualification_flags": {k: False for k in A.FLAGS}, "selected_delta": None, "reinitialization": "none",
              "identity_free_check": proof, "parent_integration_commit": A.PARENT_INTEGRATION_COMMIT, "runtime": runtime, "pins": {k: K.pins(k) for k in ("a", "b")}}
    return freeze, infra


@pytest.fixture
def ready(monkeypatch):
    """The synthetic READY inventory, served by the analyzer's own loader so that its equality check against the frozen file passes (see ready_copy)."""
    inv, real = ready_copy(), A.jload
    monkeypatch.setattr(A, "jload", lambda p: inv if Path(p) == EV / "inventory.json" else real(p))
    return inv


def test_registration_validation_accepts_a_complete_freeze_of_a_ready_inventory(tmp_path, ready):
    freeze, infra = complete_freeze(tmp_path)
    A.validate_registration(freeze, ready, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_registration_validation_refuses_the_real_blocked_inventory(tmp_path):
    freeze, infra = complete_freeze(tmp_path)
    with pytest.raises(ValueError, match="blocked before CFD"):
        A.validate_registration(freeze, INV, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_registration_validation_rejects_each_weakening(tmp_path, ready):
    freeze, infra = complete_freeze(tmp_path)
    mutations = {
        "inflated per-state budget": lambda f: f["runtime"]["a"].update(per_state_timeout_s=5000),
        "inflated aggregate cap": lambda f: f["runtime"]["b"].update(solver_wall_time_cap_s=99999),
        "omitted analyzer hash": lambda f: f["file_hashes"].pop("scripts/analyze_opt01a.py"),
        "wrong file hash": lambda f: f["file_hashes"].update({"scripts/opt01a_states.py": "0" * 64}),
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
            A.validate_registration(bad, ready, infra=infra, identity=tmp_path / "identity_free_check.json")
    (infra / "kernel_opt01a_a/runner.py").write_text((infra / "kernel_opt01a_a/runner.py").read_text() + "\n# edited\n")
    with pytest.raises(ValueError, match="rendered worker"):
        A.validate_registration(freeze, ready, infra=infra, identity=tmp_path / "identity_free_check.json")
    bad_inv = copy.deepcopy(ready); bad_inv["states"][1]["hard_count"]["residual_vs_n_max"] = 1
    with pytest.raises(ValueError):
        A.validate_registration(freeze, bad_inv, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_freeze_closure_contains_every_project_file_the_host_scripts_import():
    import freeze_opt01a as F
    closure = F.project_closure()
    must = {"scripts/analyze_opt01a.py", "scripts/analyze_lowdim04a.py", "scripts/build_opt01a_inputs.py", "scripts/build_opt01a_kernel.py", "scripts/freeze_opt01a.py", "scripts/lowdim04a_contract.py",
            "scripts/opt01a_states.py", "scripts/step01_states.py", "scripts/grid01_gpu.py", "scripts/build_lowdim01_inputs.py", "scripts/build_lowdim04a_inputs.py", "scripts/evaluate_opt01_v1_states.py",
            "scripts/fd08_v2_campaign_io.py", "src/cfd_sdf/grid01_contract.py", "src/cfd_sdf/design/volume_semantics_v2.py", "src/cfd_sdf/design/geometry_gates_v2.py", "src/cfd_sdf/fd08_v2_campaign.py"}
    assert must <= closure and all(not p.startswith("/") for p in closure)
