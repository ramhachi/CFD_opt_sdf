"""Read-only checks of the generated P22-v2 registration artifact (added after the registrar run; it cannot change it)."""
import hashlib
import json
from pathlib import Path

from cfd_sdf.design import volume_semantics_v2 as V2

EV = Path(__file__).parents[1] / "docs/evidence"
PATH = EV / "sdf_native_volume_semantics_v2_2026_10.json"
REG = json.loads(PATH.read_text())


def test_sidecar_and_contract_bind_to_the_module():
    assert PATH.with_suffix(".json.sha256").read_text().split()[0] == hashlib.sha256(PATH.read_bytes()).hexdigest()
    c = REG["contract"]
    assert REG["registration_id"] == V2.REGISTRATION_ID and REG["immutable"] is True and REG["schema_version"] == 2
    assert c["sampled_solid_centers_max"] == V2.MAX_SOLID_CENTERS == 8272 and c["volume_limit_m3_derived"] == V2.VOLUME_LIMIT_M3
    assert c["smooth_contract"]["sha256"] == V2.CONTRACT_SHA256 and c["smooth_contract"]["id"] == V2.CONTRACT_ID
    assert c["lattice"]["spacing_m"] == V2.SPACING_M and c["lattice"]["node_shape"] == list(V2.NODE_SHAPE) and c["lattice"]["origin_m"] == list(V2.ORIGIN_M)


def test_scope_reference_and_supersession_are_stated():
    assert "not a physical or continuum volume constraint" in REG["contract"]["scope"]
    ref = REG["reference"]
    assert ref["canonical_reference_artifact"]["state_sha256"] == V2.REFERENCE_STATE_SHA256 and ref["canonical_reference_artifact"]["npz_sha256"] == V2.REFERENCE_NPZ_SHA256
    assert ref["not_the_reference"]["lowdim03_parent_state_sha256"] == "81d24fe4a66704ed469f560b7396b4c0cbf6810ef8082e710f002145ca6e3a65"
    m = REG["mapping_reproducibility"]
    assert m["status"] == "UNRESOLVED" and m["classification_for_this_contract"] == "non_blocking" and "hard count" in m["validity"]
    assert REG["supersession"]["v1"]["registration_sha256"] == hashlib.sha256((EV / "sdf_native_volume_semantics_v1_2026_09.json").read_bytes()).hexdigest()


def test_ten_states_sit_at_the_integer_limit_and_nothing_is_qualified():
    m = REG["measured"]
    states = [m["baseline"], m["lowdim03_parent"], *m["lowdim04a_perturbations_recorded_not_rederived"]]
    assert len(states) == 10 and all(s["sampled_solid_centers"] == 8272 and s["hard_count_residual_v2"] == 0 and s["hard_feasible_v2"] for s in states)
    assert not m["baseline"]["v1_sharp_feasible"] and not m["lowdim03_parent"]["v1_sharp_feasible"]  # the historical v1 verdict is preserved
    assert REG["selected_delta"] is None and REG["cfd_runs"] == 0 and REG["kaggle_submissions"] == 0 and not any(REG["flags"].values())
