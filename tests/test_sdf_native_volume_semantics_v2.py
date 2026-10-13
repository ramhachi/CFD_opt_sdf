"""P22-v2 contract on the retained v17 states and the registrar's fail-closed behaviour; no CFD."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.design import volume_semantics_v2 as V2
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import (
    SMOOTHED_VOLUME_CONTRACT_SHA256,
    VolumeSemanticsError,
    sharp_volume_m3,
    smoothed_volume_and_gradient,
)

ROOT = Path(__file__).parents[1]
INPUTS = ROOT / "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs"


@pytest.fixture(scope="module")
def baseline():
    return SDFDesignState.load(INPUTS / "v17_baseline.npz")


@pytest.fixture(scope="module")
def parent():
    return SDFDesignState.load(INPUTS / "lowdim03_parent.npz")


def registrar():
    spec = importlib.util.spec_from_file_location("v2reg", ROOT / "scripts/sdf_native_volume_semantics_v2_2026_10.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_constants_are_pinned_and_the_limit_is_derived_from_the_integer():
    assert V2.MAX_SOLID_CENTERS == 8272 and V2.VOLUME_LIMIT_M3 == 8272 * 0.025 ** 3 == 0.12925000000000003
    assert V2.CONTRACT_SHA256 == "caaa38ef40e810fe8a9c8d8195e0eada6d2ce5e78af25ea2a9670618f0d1f0a4"
    assert SMOOTHED_VOLUME_CONTRACT_SHA256 == "56825cd50c0916c5659badd21c84bab517ddb370085a92056d40a9028e8a7969"  # v1 is untouched


def test_baseline_and_parent_sit_exactly_at_the_integer_limit_and_fail_v1(baseline, parent):
    for state in (baseline, parent):
        assert V2.hard_count_residual(state) == 0 and V2.hard_feasible(state)
        assert sharp_volume_m3(state) == V2.VOLUME_LIMIT_M3
        assert not smoothed_volume_and_gradient(state).sharp_volume_feasible  # v1 limit 0.126125 is exceeded: the reason for v2


def test_a_real_state_with_more_solid_centres_is_infeasible_and_the_float_rule_agrees(baseline):
    phi = baseline.phi.copy(); phi[:2, :2, :2] = -1.0  # makes the corner cell solid (and its neighbours' shared nodes)
    state = SDFDesignState.create(phi=phi, origin_m=baseline.origin_m, spacing_m=baseline.spacing_m, narrow_band_width_m=baseline.narrow_band_width_m, design_mask=np.ones(phi.shape, bool))
    assert V2.hard_count_residual(state) > 0 and not V2.hard_feasible(state)
    assert V2.hard_feasible(state) == V2.smoothed_volume_and_gradient_v2(state).sharp_volume_feasible == False  # noqa: E712


def test_one_more_solid_centre_via_the_constant(monkeypatch, baseline):
    monkeypatch.setattr(V2, "MAX_SOLID_CENTERS", 8271)
    assert V2.hard_count_residual(baseline) == 1 and not V2.hard_feasible(baseline)


def test_v2_smooth_primitive_is_v1_with_the_v2_denominator(parent):
    v1, v2 = smoothed_volume_and_gradient(parent), V2.smoothed_volume_and_gradient_v2(parent)
    assert v2.smoothed_volume_m3 == v1.smoothed_volume_m3 and np.array_equal(v2.gradient_m2, v1.gradient_m2)
    assert v2.volume_limit_m3 == V2.VOLUME_LIMIT_M3 and v2.constraint_residual == v1.smoothed_volume_m3 / V2.VOLUME_LIMIT_M3 - 1.0
    assert v2.contract_id == V2.CONTRACT_ID and v2.contract_sha256 == V2.CONTRACT_SHA256 and v2.grid_sha256 != v1.grid_sha256
    assert np.allclose(v2.constraint_gradient_per_m * V2.VOLUME_LIMIT_M3, v2.gradient_m2)
    assert v2.sharp_volume_feasible  # the same float expression as the integer limit


def test_report_carries_the_scope_and_the_inactive_smooth_constraint(parent):
    r = V2.report_v2(parent)
    assert r["schema_version"] == 2 and r["kind"] == V2.CONTRACT_ID and r["hard_count_residual"] == 0 and r["hard_feasible"]
    assert "not a physical" in r["scope"] and "not a physical volume" in r["limit_kind"] and "inactive" in r["constraint_residual_note"]
    assert r["constraint_residual"] < -0.3  # g_V is far from active at the hard boundary


def test_every_other_lattice_and_non_state_is_refused():
    phi = np.ones((5, 5, 5), np.float32); phi[1:4, 1:4, 1:4] = -1.0
    other = SDFDesignState.create(phi=phi, origin_m=(0.0, 0.0, 0.0), spacing_m=0.1, narrow_band_width_m=0.3, design_mask=np.ones(phi.shape, bool))
    for call in (V2.hard_count_residual, V2.hard_feasible, V2.smoothed_volume_and_gradient_v2, V2.report_v2):
        with pytest.raises(VolumeSemanticsError):
            call(other)
        with pytest.raises(VolumeSemanticsError):
            call(object())


def test_registrar_writes_a_consistent_immutable_registration(tmp_path):
    R = registrar(); R.OUT = tmp_path / "reg.json"; R.main()
    reg = json.loads(R.OUT.read_text())
    assert reg["registration_id"] == V2.REGISTRATION_ID and reg["contract"]["sampled_solid_centers_max"] == 8272 and reg["contract"]["smooth_contract"]["sha256"] == V2.CONTRACT_SHA256
    assert R.OUT.with_suffix(".json.sha256").read_text().split()[0] == __import__("hashlib").sha256(R.OUT.read_bytes()).hexdigest()
    m = reg["measured"]
    assert m["baseline"]["hard_count_residual_v2"] == m["lowdim03_parent"]["hard_count_residual_v2"] == 0 and len(m["lowdim04a_perturbations_recorded_not_rederived"]) == 8
    before = R.OUT.read_bytes(); R.main(); assert R.OUT.read_bytes() == before  # idempotent rerun


def test_registrar_fails_closed(tmp_path, monkeypatch):
    R = registrar(); R.OUT = tmp_path / "reg.json"
    monkeypatch.setitem(R.PINNED, "v1_registration.json", "0" * 64)
    with pytest.raises(SystemExit):
        R.main()
    assert not R.OUT.exists()  # tampered pinned hash: nothing written
    monkeypatch.undo()
    R = registrar(); R.OUT = tmp_path / "reg.json"; R.main()
    R.OUT.with_suffix(".json.sha256").write_text("0" * 64 + "\n")
    with pytest.raises(SystemExit):
        R.main()  # sidecar differs from the immutable registration
    R.OUT.with_suffix(".json.sha256").unlink(); R.OUT.write_text("{}")
    with pytest.raises(SystemExit):
        R.main()  # refuses to overwrite a different registration
    R.OUT.unlink(); R.OUT.with_suffix(".json.sha256").write_text("x")
    with pytest.raises(SystemExit):
        R.main()  # sidecar without a registration


def test_registrar_refuses_a_tampered_blocker_hash_and_a_count_other_than_n_max(tmp_path, monkeypatch):
    R = registrar(); R.OUT = tmp_path / "reg.json"
    monkeypatch.setattr(R, "BLOCKER_SHA", "0" * 64)
    with pytest.raises(SystemExit):
        R.main()
    monkeypatch.undo()
    R = registrar(); R.OUT = tmp_path / "reg.json"
    monkeypatch.setattr(V2, "MAX_SOLID_CENTERS", 8271)
    with pytest.raises(SystemExit):
        R.main()
    assert not R.OUT.exists()


def test_report_v2_on_the_baseline(baseline):
    r = V2.report_v2(baseline)
    assert r["sampled_solid_centers"] == 8272 and r["hard_feasible"] and -0.32 < r["constraint_residual"] < -0.31
