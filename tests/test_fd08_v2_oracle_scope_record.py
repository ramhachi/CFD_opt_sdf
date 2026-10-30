"""Scope-limited oracle record: pinned inputs, regenerated directions, bridge fields, literal-false flags."""
import json
import re

import pytest

from cfd_sdf import criteria_supersession as cs
from scripts import build_fd08_v2_oracle_scope_record as rec

pytestmark = pytest.mark.skipif(not rec.DEFAULT_STATE.is_file(), reason="canonical v17 NPZ fixture unavailable")


@pytest.fixture(scope="module")
def record():
    return rec.build(rec.DEFAULT_STATE)


def test_record_is_deterministic(record):
    assert json.dumps(rec.build(rec.DEFAULT_STATE), sort_keys=True) == json.dumps(record, sort_keys=True)


def test_flags_stay_literally_false_and_record_passes_the_registry_flag_check(record):
    assert set(record["qualification_flags"].values()) == {False} and len(record["qualification_flags"]) == 6
    cs._check_flag_state(record)  # no fd_oracle / *_qualified true key anywhere in the payload


def test_eight_series_cover_four_directions_by_two_responses(record):
    assert len(record["rows"]) == 8
    assert {(r["direction_id"], r["response_id"]) for r in record["rows"]} == {
        (d, r) for d in record["scope"]["directions"] for r in ("drag", "downforce")}
    for row in record["rows"]:
        assert row["se_g_n_per_m"] > 0 and row["relative_se"] < 0.1


def test_regenerated_directions_match_registered_hashes_and_bridge_hashes_are_hex(record):
    criteria = json.loads((rec.FORMAL / "formal_criteria.json").read_text())
    for row in record["rows"]:
        assert row["direction_sha256_f32_c_order"] == criteria["direction_inventory"]["hashes"][row["direction_id"]]
        for key in ("direction_sha256_grad01_f64", "response_semantics_sha256"):
            assert re.fullmatch(r"[0-9a-f]{64}", row[key])
    assert re.fullmatch(r"[0-9a-f]{64}", record["grad01_bridge"]["fd_backend_fingerprint_sha256"])


def test_no_error_gate_is_chosen_here(record):
    bridge = record["grad01_bridge"]
    assert bridge["relative_error_tolerance"] is None and bridge["absolute_noise_floor"] is None


def test_wrong_or_missing_state_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        rec.build(tmp_path / "missing.npz")


def test_changed_pinned_evidence_is_rejected(monkeypatch):
    monkeypatch.setitem(rec.PINS, rec.FORMAL / "campaign_final.json", "0" * 64)
    with pytest.raises(ValueError, match="pinned evidence changed"):
        rec.build(rec.DEFAULT_STATE)
