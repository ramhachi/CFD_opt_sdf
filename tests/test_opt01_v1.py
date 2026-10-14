"""OPT-01 v1 phase 1 (#30): crossing-slope near-zero gate rule (synthetic) and the registered profile v2 / contract / evaluation records."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.design.geometry_gates_v2 import CROSSING_SLOPE_RULE, _crossing_slope_gate, evaluate_geometry_gates_v2
from test_geometry_gates_v2 import POLICY, _box, _clean_phi, _evaluate, _faces, _patch, _profile, _state

BAND = {"rule": CROSSING_SLOPE_RULE, "threshold": 0.5}


def gate(phi):
    return _crossing_slope_gate(_state(phi), BAND, 0.5)


def test_clean_box_passes():
    g = gate(_clean_phi())
    assert g["status"] == "pass" and g["measured"]["crossing_slope_min"] >= 0.5 and g["measured"]["nodes_below_threshold"] == 0


def test_kink_passes_although_the_central_gradient_is_below_the_floor():
    g = gate(_faces((6.8, 6.8, 9.8), (28.2, 20.2, 11.4)))  # one-cell sheet: ridge, central |grad| ~ 0 at its nodes
    assert g["status"] == "pass" and g["measured"]["central_nodes_below_floor"] > 0


def test_near_tie_crossing_fails():
    phi = _clean_phi()
    phi[8, 12, 12], phi[7, 12, 12] = -1e-4, 1e-4  # solid / fluid pair 2e-4 m apart: slope 0.004 on its only crossing edge
    g = gate(phi)
    assert g["status"] == "fail" and g["measured"]["nodes_below_threshold"] == 2 and g["measured"]["failing_nodes"]["other_near_tie"] == 2
    assert g["fail_reasons"] == ["crossing_slope_below_threshold_at_zero_level"]


def test_exact_zero_plateau_fails():
    phi = _clean_phi()
    phi[_patch((6, 10, 10), (7, 16, 16))] = 0.0  # exact zero is fluid
    g = gate(phi)
    assert g["status"] == "fail" and g["measured"]["failing_nodes"]["exact_zero_phi"] > 0


def test_array_boundary_sign_change_node_is_unmeasured():
    g = gate(_box((0, 8, 8), (16, 18, 18)))
    assert g["unmeasured_reasons"] == ["sign_change_nodes_on_array_boundary"] and g["status"] == "unmeasured"


def test_profile_selects_the_rule_and_the_old_profile_keeps_the_central_rule():
    state = _state(_clean_phi())
    profile = {**_profile(state), "near_zero_gradient_band": BAND}
    v2 = evaluate_geometry_gates_v2(state, parent_state=state, profile=profile, policy=POLICY, export_mesh=None)["gates"]["near_zero_gradient_band"]
    assert v2["thresholds"]["rule"] == CROSSING_SLOPE_RULE and v2["status"] == "pass"
    v1 = evaluate_geometry_gates_v2(state, parent_state=state, profile=_profile(state), policy=POLICY, export_mesh=None)["gates"]["near_zero_gradient_band"]
    assert "rule" not in v1["thresholds"] and "nodes_below_floor" in v1["measured"]
    bad = evaluate_geometry_gates_v2(state, parent_state=state, profile={**profile, "near_zero_gradient_band": {"rule": "x"}}, policy=POLICY, export_mesh=None)
    assert bad["gates"]["near_zero_gradient_band"]["unmeasured_reasons"] == ["near_zero_gradient_band_rule_unregistered"]


# ---- registered records -------------------------------------------------------------------------------------------------------------------

def test_registered_profile_v2_differs_from_v1_only_in_the_band():
    import register_geom02_profile as reg
    import register_opt01_v1 as r1

    v1, v2 = json.loads(reg.PROFILE.read_text()), json.loads(r1.PROFILE.read_text())
    assert {k for k in v2 if k not in v1 or v1[k] != v2[k]} == {"profile_id", "near_zero_gradient_band", "predecessor_profile", "non_blind_v2"}
    assert v2["near_zero_gradient_band"]["rule"] == CROSSING_SLOPE_RULE and v2["near_zero_gradient_band"]["threshold"] == 0.5
    assert v2["zero_level_gradient_floor"] == 0.5 and v2["allowed_events"] == [] and v2["policy"] == v1["policy"]


def test_registered_files_rederive_and_match_their_sidecars():
    import register_geom02_profile as reg
    import register_opt01_v1 as r1

    profile, contract = r1.build()
    for path, obj in ((r1.PROFILE, profile), (r1.CONTRACT, contract)):
        assert path.read_text() == reg.dump(obj)
        assert path.with_name(path.name + ".sha256").read_text().split()[0] == reg.sha_file(path)


def test_contract_pins_resolve_to_the_files_they_name():
    import register_geom02_profile as reg
    import register_opt01_v1 as r1

    c = json.loads(r1.CONTRACT.read_text())
    pins = c["pins"]
    assert pins["gate_profile_v2"]["sha256"] == reg.sha_file(r1.PROFILE) and pins["resolved_research_policy"]["sha256"] == r1.POLICY_SHA256 == "b5bcc8c742cb9c09988a80b7e42374c7d7f9bdfccce5c5acb8713cc9204375c8"
    for p in (*pins["cone_solver_code"].values(), pins["gate_code"], pins["p22_v2"], pins["p22_v2"]["code"], pins["lowdim04a_inventory"], pins["lowdim04b_inventory"]):
        assert reg.sha_file(ROOT / p["path"]) == p["sha256"], p["path"]
    assert len(pins["basis_raw_files"]) == 4 and all(reg.sha_file(ROOT / d["path"]) == d["sha256_fortran_raw"] for d in pins["basis_raw_files"].values())
    assert set(pins["dual_grid_kernels"]) == {"flow_24", "flow_32"} and c["D3_update"]["ladder"]["steps_mm"] == [0.3125, 0.625, 0.9375, 1.25]
    assert not any(c["flags"].values()) and c["solver_started"] is False and c["floors"]["min_downforce_gain_n"] == 3e-5


def test_evaluation_record_is_labelled_retroactive_and_does_not_close_30():
    import register_opt01_v1 as r1

    path = r1.OUT / "opt01_v1_phase1_evaluation.json"
    if not path.exists():
        pytest.skip("evaluation not yet registered")
    a = json.loads(path.read_text())
    r = a["retroactive_d3_conformance"]
    assert set(a["states"]) == {"baseline", "lowdim03_parent", "lowdim04b_trial"} and "RETROACTIVE" in r["statement"] and "cannot close #30" in r["statement"]
    assert a["trial_reconstruction"]["identity_matches_04b_inventory"] is True and a["solver_started"] is False and not any(a["flags"].values())
