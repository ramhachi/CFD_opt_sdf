"""OPT-01 v1 Stage B inventory: re-derivation of the direction, identities, pre-CFD gates, parent gate, hard count, lineage; freeze validation negatives."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_opt01b as A  # noqa: E402
import build_opt01b_inputs as B  # noqa: E402
import opt01b_states as L  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf.fd08_v2_campaign import state_identity  # noqa: E402

EV = ROOT / "docs/evidence/opt01b_stage_b_2026_10_15"
INV = json.loads((EV / "inventory.json").read_text())


@pytest.fixture(scope="module")
def ctx():
    return B.context()  # reconstructs the parent, the direction and the seven states from retained inputs (cheap; the gates are not recomputed here)


def test_direction_is_the_stage_a_robust_solution_through_the_production_function_and_stage_a_is_pinned(ctx):
    a = json.loads((ROOT / INV["stage_a"]["analysis_path"]).read_text())
    assert B.sha(ROOT / INV["stage_a"]["analysis_path"]) == INV["stage_a"]["analysis_sha256"] == B.STAGE_A_ANALYSIS_SHA and a["verdict"] == "LOCAL_FEASIBLE_CONE_FOUND" and a["integrity"]["pass"] is True
    assert B.sha(ROOT / INV["stage_a"]["inventory_path"]) == INV["stage_a"]["inventory_sha256"] == B.STAGE_A_INVENTORY_SHA
    assert INV["proposal"]["coefficient_vector"] == a["solutions"]["robust_cross_grid"]["coefficient_vector"]
    assert INV["proposal"]["m_max_abs_sum"] == pytest.approx(a["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["m_max_abs_sum"], abs=1e-12)  # equals the Stage A normalization
    raw = B.PROPOSAL_RAW.read_bytes()
    assert S.sha256_bytes(raw) == INV["proposal"]["sha256_fortran_raw"] == INV["lineage"]["direction_sha256_fortran_raw"] and raw == S.to_raw(ctx.prop) and float(np.max(np.abs(S.read_f4(B.PROPOSAL_RAW)))) == 1.0
    bad = copy.deepcopy(a); bad["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["m_max_abs_sum"] += 1e-6
    with pytest.raises(ValueError, match="normalization"):
        B.derive_direction(bad, {n: S.read_f4(ROOT / d["path"]) for n, d in L.CONTRACT["pins"]["basis_raw_files"].items()})


def test_identities_parent_raw_and_directions_are_reproduced_from_retained_inputs(ctx):
    for row in INV["states"]:
        child, audit = ctx.states[row["name"]]
        ident = state_identity(child)
        assert all(ident[k] == row[k] for k in B.IDENTITY_KEYS) and audit["changed_node_count"] == row["changed_node_count"]
        assert len({row["phi_fortran_order_sha256"], row["phi_c_order_sha256"]}) == 2 and all(len(row[k]) == 64 for k in ("state_sha256", "npz_sha256"))
    parent = S.read_f4(B.PARENT_RAW)
    assert S.to_raw(ctx.parent.phi) == B.PARENT_RAW.read_bytes() and B.sha(B.PARENT_RAW) == INV["parent"]["phi_fortran_order_sha256"]
    assert (EV / "inventory.json.sha256").read_text().strip() == B.sha(EV / "inventory.json")
    for row in INV["states"]:  # the runner order regenerates each state
        phi = parent if row["kind"] == "parent" else S.perturb(parent, S.read_f4(B.PROPOSAL_RAW), row["step_mm"], row["sign"])
        assert S.sha256_bytes(S.to_raw(phi)) == row["phi_fortran_order_sha256"]


def test_parent_is_the_stage_a_parent_generation_one_and_lineage_is_recorded(ctx):
    ident = state_identity(ctx.parent)
    assert ident["state_sha256"].startswith("c9e12f62") and ident["state_sha256"] == INV["parent"]["state_sha256"] == INV["lineage"]["parent_state_sha256"] == INV["states"][0]["state_sha256"]
    assert ctx.parent.generation == 1 == INV["parent"]["generation"] and INV["lineage"]["child_generation_if_selected"] == 2 and INV["lineage"]["rollback"] == "keep the parent"
    assert INV["lineage"]["contract_sha256"] == L.CONTRACT_SHA256 == INV["contract"]["sha256"] and INV["lineage"]["stage_a_analysis_sha256"] == B.STAGE_A_ANALYSIS_SHA
    for r in INV["states"]:
        if r["kind"] == "candidate":  # selected child = the step as the next parent: same phi hashes, generation + 1, different state_sha256
            lin = r["if_selected_lineage"]
            assert lin["generation"] == 2 and lin["parent_state_sha256"] == INV["parent"]["state_sha256"] and lin["state_sha256"] != r["state_sha256"] and lin["rollback"] == "keep the parent"
        else:
            assert "if_selected_lineage" not in r


def test_seven_states_parent_first_same_plan_on_both_grids_n_phi_within_n_max_and_the_parent_reference():
    assert [r["name"] for r in INV["states"]] == [r["name"] for r in L.plan()] and len(INV["states"]) == 7 and INV["states"][0]["kind"] == "parent"
    assert INV["kernels"]["a"] == INV["kernels"]["b"] == [r["name"] for r in INV["states"]] and INV["gate_scope"] == L.CONTRACT["D3_update"]["gate_scope"]
    for r in INV["states"]:
        assert r["hard_count"]["residual_vs_n_max"] == 0 and r["hard_count"]["sampled_solid_centers"] <= 8272 and (r["hard_count"]["count_equal_margin_m"] > 0 or r["kind"] == "parent")
        assert r["pre_cfd_gates"]["table"]["count_equal_margin_positive"] == "pass" or r["kind"] == "parent"
    for k, g in INV["grids"].items():
        ref = g["baseline_reference"]
        assert "opt01a__parent" in ref["forces_csv_path"] and B.sha(ROOT / ref["forces_csv_path"]) == ref["forces_csv_sha256"]
        assert g["measurement"]["solver_wall_time_cap_s"] == 6300 and g["measurement"]["per_state_timeout_s"] == 900
    b4 = json.loads((ROOT / "docs/evidence/lowdim04b_stage_b_2026_10_13/inventory.json").read_text())
    for k in ("a", "b"):  # identical measurement to LOWDIM-04B except the claim string
        assert {x: y for x, y in INV["grids"][k]["measurement"].items() if x != "qualification_claim"} == {x: y for x, y in b4["grids"][k]["measurement"].items() if x != "qualification_claim"}
    assert INV["job_env_common"] == b4["job_env_common"]


def test_gate_records_follow_the_contract_scope_candidates_all_hard_controls_crossing_slope_report_only():
    profile = json.loads((ROOT / L.CONTRACT["pins"]["gate_profile_v2"]["path"]).read_text())
    rejected = []
    for r in INV["states"]:
        g = r["pre_cfd_gates"]
        bundle = g["record"]["geom02_v2"]
        assert bundle["profile_id"] == profile["profile_id"] and bundle["gates"]["near_zero_gradient_band"]["thresholds"]["rule"] == "crossing_slope_v1" and g["geom02_v2_gate_count"] == 13
        assert g["failed"] == L.hard_failures(r["kind"], g["table"]) and g["all_pass"] is (not g["failed"])
        zone, nz = g["near_zero_gradient_band"], bundle["gates"]["near_zero_gradient_band"]["measured"].get("nodes_below_threshold", 0)
        assert zone["failing_nodes"] == nz == zone["on_baseline_tie_plateau"] + zone["off_plateau"] and g["table"]["near_zero_gradient_band"] == ("fail" if nz else "pass")
        if r["kind"] == "candidate":
            assert g["gate_rejected"] is bool(g["failed"]) and g["eligible_for_acceptance"] is (not g["failed"])
            if g["failed"]:
                rejected.append(r["name"])
        else:
            assert g["failed"] == [] and ("near_zero_gradient_band" in g["report_only_failed"]) == (r["kind"] == "control" and nz > 0)
    assert [b["state"] for b in INV["gate_rejected_candidates"]] == rejected and INV["stage_status"] == "READY" and INV["blockers"] == []


def test_inventory_binds_the_pinned_contract_and_every_contract_pin_verifies():
    assert INV["contract"]["sha256"] == L.CONTRACT_SHA256 == B.sha(ROOT / L.CONTRACT_REL) and INV["contract"]["pins_verified"] == B.A1.verify_pins(L.CONTRACT) > 10
    assert L.STEPS_MM == tuple(INV["steps_mm"]) and L.CONTROL_STEPS_MM == tuple(INV["control_steps_mm"]) and L.BASIS == tuple(S.SINGLE_DIRECTIONS)
    # the plan file is frozen: contract v1.1 pins its hash (R1 note); the contract's own pin check above covers it
    assert L.CONTRACT["plan"]["sha256"] == B.sha(ROOT / L.CONTRACT["plan"]["path"])


def complete_freeze(tmp_path):
    """A complete, valid freeze fixture: rendered workers in a temp infra dir, real file hashes, real pins (the source commit is HEAD; rendering does not contact anything)."""
    import build_opt01b_kernel as K
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    infra, runtime = tmp_path / "infra", {}
    for k, grid in (("a", "flow_24"), ("b", "flow_32")):
        d = infra / f"kernel_opt01b_{k}"; d.mkdir(parents=True)
        (d / "runner.py").write_text(K.render(head, k)); (d / "kernel-metadata.json").write_text(json.dumps(K.metadata(k), sort_keys=True, indent=2) + "\n")
        runtime[k] = {**A.RUNTIME_FIXED, "kernel_id": K.KERNEL_IDS[k], "case_id": grid, "runner_sha256": B.sha(d / "runner.py"), "metadata_sha256": B.sha(d / "kernel-metadata.json")}
    required = A.REQUIRED_FILES | {INV["parent"]["raw_path"]} | {g["baseline_reference"]["forces_csv_path"] for g in INV["grids"].values()} | {INV["proposal"]["file"], INV["stage_a"]["analysis_path"], A.STAGE_A_INVENTORY} | {d["path"] for d in INV["directions"].values()}
    proof = {"all_free": True, "owner": "ramhachi888"}
    (tmp_path / "identity_free_check.json").write_text(json.dumps(proof))
    freeze = {"kind": A.FREEZE_KIND, "frozen_parameters": A.FROZEN_PARAMETERS, "inventory_sha256": B.sha(EV / "inventory.json"), "file_hashes": {p: B.sha(ROOT / p) for p in sorted(required)},
              "source_commit": head, "source_tree_id": A.git_tree_sha(head), "qualification_flags": {k: False for k in A.FLAGS}, "selected_delta": None, "reinitialization": "none",
              "identity_free_check": proof, "parent_integration_commit": A.PARENT_INTEGRATION_COMMIT, "runtime": runtime, "pins": {k: K.pins(k) for k in ("a", "b")}}
    return freeze, infra


@pytest.fixture
def served(monkeypatch):
    """An editable copy of the inventory served by the analyzer's own loader, so that its equality check against the frozen file passes and only the rule under test can fail."""
    inv, real = copy.deepcopy(INV), A.jload
    monkeypatch.setattr(A, "jload", lambda p: inv if Path(p) == EV / "inventory.json" else real(p))
    return inv


def test_registration_validation_accepts_a_complete_freeze_and_rejects_each_weakening(tmp_path, served):
    freeze, infra = complete_freeze(tmp_path)
    ident = tmp_path / "identity_free_check.json"
    A.validate_registration(freeze, served, infra=infra, identity=ident)
    mutations = {
        "inflated per-state budget": lambda f: f["runtime"]["a"].update(per_state_timeout_s=5000), "inflated aggregate cap": lambda f: f["runtime"]["b"].update(solver_wall_time_cap_s=99999),
        "omitted analyzer hash": lambda f: f["file_hashes"].pop("scripts/analyze_opt01b.py"), "omitted stage a analysis": lambda f: f["file_hashes"].pop(INV["stage_a"]["analysis_path"]),
        "omitted contract": lambda f: f["file_hashes"].pop(L.CONTRACT_REL),
        "wrong file hash": lambda f: f["file_hashes"].update({"scripts/opt01b_states.py": "0" * 64}), "flag true": lambda f: f["qualification_flags"].update(optimizer=True),
        "flag missing": lambda f: f["qualification_flags"].pop("topology"),
        "selected delta": lambda f: f.update(selected_delta=1.0), "frozen parameter": lambda f: f["frozen_parameters"].update(min_downforce_gain_n=1e-6), "wrong tree id": lambda f: f.update(source_tree_id="0" * 40),
        "pin tampered": lambda f: f["pins"]["a"].update({next(iter(f["pins"]["a"])): "0" * 64}), "identity differs from the record": lambda f: f.update(identity_free_check={"all_free": True, "owner": "ramhachi888", "x": 1}),
        "identity check absent": lambda f: f.update(identity_free_check={}),
        "wrong parent commit": lambda f: f.update(parent_integration_commit="0" * 40), "kernel id": lambda f: f["runtime"]["a"].update(kernel_id="ramhachi888/other")}
    for label, mutate in mutations.items():
        bad = copy.deepcopy(freeze); mutate(bad)
        with pytest.raises(ValueError):
            A.validate_registration(bad, served, infra=infra, identity=ident)
    (infra / "kernel_opt01b_a/runner.py").write_text((infra / "kernel_opt01b_a/runner.py").read_text() + "\n# edited\n")
    with pytest.raises(ValueError, match="rendered worker"):
        A.validate_registration(freeze, served, infra=infra, identity=ident)


@pytest.mark.parametrize("mutate, msg", [
    (lambda i: i.update(stage_status="BLOCKED_PRE_CFD"), "blocked before CFD"),
    (lambda i: i["states"][0]["pre_cfd_gates"]["table"].update(near_zero_gradient_band="fail"), "inconsistent|fails the pre-CFD"),  # the parent is a proposal: crossing-slope hard
    (lambda i: i["states"][5]["pre_cfd_gates"]["table"].update(p22_v2="fail"), "inconsistent|fails the pre-CFD"),  # a reverse diagnostic (probe) failing another gate blocks
    (lambda i: i["states"][1]["pre_cfd_gates"].update(eligible_for_acceptance=not i["states"][1]["pre_cfd_gates"]["eligible_for_acceptance"]), "eligibility"),
    (lambda i: i["states"][2]["hard_count"].update(residual_vs_n_max=1), "inconsistent"),
    (lambda i: i["lineage"].update(contract_sha256="0" * 64), "lineage"),
    (lambda i: i["lineage"].update(direction_sha256_fortran_raw="0" * 64), "direction"),
])
def test_registration_validation_refuses_a_blocked_inconsistent_or_scope_violating_inventory(tmp_path, served, mutate, msg):
    freeze, infra = complete_freeze(tmp_path)
    mutate(served)
    with pytest.raises(ValueError, match=msg):
        A.validate_registration(freeze, served, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_a_gate_rejected_candidate_is_registered_not_a_blocker(tmp_path, served):
    freeze, infra = complete_freeze(tmp_path)
    row = served["states"][3]
    row["pre_cfd_gates"]["table"]["near_zero_gradient_band"] = "fail"
    row["pre_cfd_gates"].update(failed=["near_zero_gradient_band"], all_pass=False, gate_rejected=True, eligible_for_acceptance=False)
    A.validate_registration(freeze, served, infra=infra, identity=tmp_path / "identity_free_check.json")


def test_freeze_closure_contains_every_project_file_the_host_scripts_import():
    import freeze_opt01b as F
    closure = F.project_closure()
    must = {"scripts/analyze_opt01b.py", "scripts/analyze_lowdim04b.py", "scripts/build_opt01b_inputs.py", "scripts/build_opt01a_inputs.py", "scripts/build_opt01b_kernel.py", "scripts/freeze_opt01b.py",
            "scripts/opt01b_contract.py", "scripts/opt01b_states.py", "scripts/step01_states.py", "scripts/grid01_gpu.py", "scripts/build_lowdim01_inputs.py", "scripts/lowdim01_states.py",
            "scripts/build_lowdim04a_inputs.py", "scripts/evaluate_opt01_v1_states.py", "scripts/fd08_v2_campaign_io.py", "src/cfd_sdf/lowdim03_contract.py", "src/cfd_sdf/design/volume_semantics_v2.py",
            "src/cfd_sdf/design/geometry_gates_v2.py", "src/cfd_sdf/fd08_v2_campaign.py"}
    assert must <= closure and all(not p.startswith("/") for p in closure)
