from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import build_grid01_inputs as BI  # noqa: E402
import build_grid01_freeze as BF  # noqa: E402
import build_grid01_kernel as BK  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf import grid01_contract as C  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"


def test_inventory_rederives_from_the_immutable_step01_states_and_geometry_helpers():
    rebuilt = BI.build()
    expected = json.loads((EVIDENCE / "inventory.json").read_text())
    assert rebuilt == expected
    assert len(expected["states"]) == 9
    assert expected["kernels"]["a"] == [row["name"] for row in expected["states"]]
    assert expected["states"][0]["name"] == "step01__baseline"
    assert sum(row["kind"] == "baseline" for row in expected["states"]) == 1
    assert expected["geometry_gate_contract"]["gate_keys"] == sorted(C.GEOMETRY_GATE_KEYS)
    assert expected["canonical_npz"]["path"] == "docs/evidence/xfid01_geometry_preflight_2026_10_03/canonical_state.npz"
    assert expected["canonical_npz"]["sha256"] == "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
    assert expected["source_hashes"]["canonical_npz_sha256"] == expected["canonical_npz"]["sha256"]
    assert BI.CANONICAL_NPZ == ROOT / expected["canonical_npz"]["path"]
    measurement = expected["measurement_contract"]["flow32_measurement"]
    assert measurement["case_id"] == "flow_32"
    assert measurement["case"]["case_id"] == "flow_32"
    assert measurement["case"] == C.FLOW32_CASE | {
        "density_kg_m3": 1.0,
        "dynamic_viscosity_pa_s": 0.01,
        "freestream_mps": [1.0, 0.0, 0.0],
        "precedent_criteria_path": "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json",
        "precedent_criteria_sha256": "09e25e88767110312a134de8c10f3c2668a4d7f9a2f29829d163c72a1f5f3ef1",
        "reference_area_m2": 0.64,
        "reference_length_m": 0.8,
        "reynolds": 80.0,
    }
    assert all(set(row["geometry_gates"]["gates"]) == C.GEOMETRY_GATE_KEYS for row in expected["states"][1:])
    step01 = json.loads(BI.STEP01_EVIDENCE.joinpath("inventory.json").read_text())
    source = {row["name"]: row for row in step01["states"]}
    for row in expected["states"]:
        assert row["phi_fortran_order_sha256"] == source[row["name"]]["phi_fortran_order_sha256"]
        assert row["phi_c_order_sha256"] == source[row["name"]]["phi_c_order_sha256"]
        assert row["state_sha256"] == source[row["name"]]["state_sha256"]
        assert row["npz_sha256"] == source[row["name"]]["npz_sha256"]


def test_flow24_is_a_direct_copy_of_the_frozen_step01_rows():
    inventory = json.loads((EVIDENCE / "inventory.json").read_text())
    analysis = json.loads((BI.STEP01_EVIDENCE / "step01_analysis.json").read_text())
    for direction in C.BASIS:
        for response in C.RESPONSES:
            source = analysis["series"][f"{direction}|{response}"]["rows"][0]
            copied = inventory["flow24_reference_step01"]["secants"][direction][response]
            numeric_keys = ("step_mm", "r0_n", "r_plus_n", "r_minus_n", "g_sec_n_per_m", "eta_even")
            assert {key: copied[key] for key in numeric_keys} == {key: source[key] for key in numeric_keys}
            assert copied["source_step01_resolved"] is source["resolved"]
            contrast = source["r_plus_n"] - source["r_minus_n"]
            assert copied["resolved"] is (abs(contrast) > C.MIN_RESOLVED_N)
            assert copied["even_part_n"] == (source["r_plus_n"] + source["r_minus_n"] - 2.0 * source["r0_n"]) / 2.0
            assert copied["step_mm"] == 2.5
    for direction in ("D1_filtered_seed11", "D2_filtered_seed2026"):
        downforce = inventory["flow24_reference_step01"]["secants"][direction]["downforce"]
        assert downforce["source_step01_resolved"] is False
        assert downforce["resolved"] is True
    assert inventory["flow24_reference_step01"]["recomputed"] is False


def test_kernel_metadata_uses_the_distinct_unregistered_grid01_slug():
    metadata = BK.metadata()
    assert metadata["id"] == "ramhachi888/cfd-opt-sdf-grid01-a"
    assert metadata["title"] == "cfd-opt-sdf-grid01-a"
    assert BK.TIMEOUT_S == 10800
    pins = BK.pins()
    assert len([path for path in pins if path.endswith(".dir_f4_fortran.raw")]) == 4
    assert pins["scripts/waterlily_lowdim02_flow32_job.jl"] == hashlib.sha256((ROOT / "scripts/waterlily_lowdim02_flow32_job.jl").read_bytes()).hexdigest()
    assert S.SINGLE_DIRECTIONS == C.BASIS


def test_handoff_instruction_copy_is_preserved_byte_for_byte():
    path = ROOT / "docs/codex_instruction_grid01_cross_grid_secant_2026_10_09.md"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "8f8e75773243b9b5763c70fb6aced5997b7d427cc63f9a4a749243c4c2c2dc30"


def test_preregistration_fixes_measurement_solver_and_claim_boundaries():
    note = (EVIDENCE / "prerun_note.md").read_text()
    for phrase in (
        "GRID01_SECANT_RECORDED",
        "GRID01_SECANT_INCOMPLETE",
        "3e-5 N",
        "6e-3 N/m",
        C.SOLVER_ID,
        "independently checks every branch",
        "flow_32 noise",
        "shape_update_allowed=false",
        "Only an actual primal evaluation",
        "CUDA_DEVICE_ORDER=PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES=0",
        "separate issue branch",
    ):
        assert phrase in note


def identity_free_record():
    slug = "cfd-opt-sdf-grid01-a"
    return {
        "kind": "fd08_v2_kaggle_identity_free_check",
        "all_free": True,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "cli_version": "Kaggle CLI test fixture",
        "intended_slugs": [slug],
        "listed_slug_clashes": {},
        "owned_kernel_count": 1,
        "owned_dataset_count": 2,
        "owner": "ramhachi888",
        "status_probes": {
            slug: {
                kind: {"exit_code": 1, "stdout": "", "stderr": "404 Not Found"}
                for kind in ("kernels", "datasets")
            }
        },
    }


def test_freeze_identity_probe_requires_positive_absence_evidence():
    BF._require_identity_free(identity_free_record())


def test_freeze_contract_sections_include_full_math_and_hardware_declarations():
    inventory = json.loads((EVIDENCE / "inventory.json").read_text())
    sections = BF.contract_sections(inventory)
    assert set(sections) == {
        "runtime", "design", "measurement", "solver", "rules", "flow24_reference",
        "flow32_baseline_reference", "known_before_run", "prohibitions", "qualification_flags",
    }
    assert sections["runtime"]["gpu_inventory_policy"] == "nonempty_all_visible_devices_must_be_tesla_t4"
    assert sections["runtime"]["selected_gpu_physical_index"] == 0
    assert sections["runtime"]["cuda_visible_devices"] == "0"
    assert sections["prohibitions"]["prohibit_new_experiment_issue_creation_without_user_decision"] is True
    assert sections["prohibitions"]["prohibit_issue29_edits_in_grid01_branch"] is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda x: x.update(owned_kernel_count=100), "truncated"),
        (lambda x: x["listed_slug_clashes"].update({"cfd-opt-sdf-grid01-a": ["collision"]}), "collision"),
        (lambda x: x["status_probes"]["cfd-opt-sdf-grid01-a"]["kernels"].update(exit_code=0), "does not show"),
        (lambda x: x["status_probes"]["cfd-opt-sdf-grid01-a"]["datasets"].update(stderr="timeout"), "unknown failure"),
        (lambda x: x["status_probes"]["cfd-opt-sdf-grid01-a"].pop("datasets"), "does not show"),
    ],
)
def test_freeze_identity_probe_rejects_ambiguous_or_conflicting_evidence(mutate, message):
    record = identity_free_record()
    mutate(record)
    with pytest.raises(ValueError, match=message):
        BF._require_identity_free(record)


def test_freeze_identity_probe_rejects_stale_evidence():
    record = identity_free_record()
    record["captured_utc"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="stale"):
        BF._require_identity_free(record)
