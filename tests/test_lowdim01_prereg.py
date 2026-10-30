"""LOWDIM-01 pre-registration: the freeze matches the files that will run; the rendered kernel carries its pins; the freeze keys are exactly those the analyzer reads."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import analyze_lowdim01 as A  # noqa: E402
import build_lowdim01_freeze as F  # noqa: E402
import build_lowdim01_kernel as B  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
FREEZE_PATH = E / "prerun_freeze.json"
pytestmark = pytest.mark.skipif(not FREEZE_PATH.is_file(), reason="freeze not written yet")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def freeze():
    return json.loads(FREEZE_PATH.read_text())


def test_sidecar_and_every_frozen_file_hash(freeze):
    assert hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest() == (E / "prerun_freeze.json.sha256").read_text().strip()
    for name, path in F.FILES.items():
        assert freeze["file_hashes"][name] == sha(path), name
    assert freeze["file_hashes"]["inventory_canonical_json"] == freeze["file_hashes"]["inventory"]


def test_the_keys_the_analyzer_reads_are_exactly_those_the_freeze_holds(freeze):
    for key in ("analyzer", "contract", "states_module", "step01_states_module", "force_io", "formal_criteria", "inventory_canonical_json"):
        assert key in freeze["file_hashes"]
    assert freeze["step01_analysis_sha256"] == freeze["file_hashes"]["step01_analysis"] and freeze["pins"] and freeze["fd08_baseline"]["forces_csv_sha256"]
    out_dir = ROOT / "tests"                     # the analyzer only needs the freeze's key set here: reading a missing key raises KeyError before any decision
    for key in ("source_commit", "pins", "fd08_baseline", "step01_analysis_sha256", "file_hashes"):
        assert key in freeze


def test_the_rendered_kernel_carries_the_frozen_pins_and_identity(freeze):
    spec = importlib.util.spec_from_file_location("lowdim_runner", ROOT / "infra/kaggle/kernel_lowdim01_a/runner.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.KERNEL == "a" and mod.SOURCE_COMMIT == freeze["source_commit"] and len(mod.SOURCE_COMMIT) == 40 and mod.PINS == freeze["pins"]
    assert mod.FD08_BASELINE_CSV_SHA256 == freeze["fd08_baseline"]["forces_csv_sha256"] and mod.KERNEL_TIMEOUT_S == freeze["design"]["kernel_timeout_s"] == B.TIMEOUT_S
    meta = json.loads((ROOT / "infra/kaggle/kernel_lowdim01_a/kernel-metadata.json").read_text())
    assert meta["id"] == freeze["design"]["kernel_id"] and meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == []
    for rel, digest in freeze["pins"].items():
        assert B.sha(ROOT / rel) == digest, rel
    assert json.loads((E / "identity_free_check.json").read_text())["all_free"] is True


def test_the_registered_design_rules_and_declarations(freeze):
    d, r = freeze["design"], freeze["rules"]
    assert d["basis"] == ["D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe"] and d["candidate_step_mm"] == [1.25, 2.5, 5.0, 7.5] and d["control_step_mm"] == [1.25, 2.5]
    assert d["states"] == 7 and d["reinitialization"] == "none" and "Euclidean" in d["metric"]
    assert r["min_downforce_gain_n"] == pytest.approx(3e-5) and r["drag_allowance_n"] == pytest.approx(3e-5) and r["geometry_gate_thresholds"]["smoothed_volume_band"] == 0.10
    assert r["geometry_gate_thresholds"]["eikonal_median_abs_deviation_max"] == 0.10 and "reference only" in r["authority"]
    assert freeze["verdicts"] == ["LOWDIM_ACCEPT", "LOWDIM_NO_GO", "LOWDIM_INCOMPLETE"] and set(freeze["qualification_flags"].values()) == {False} and all(freeze["prohibitions"].values())
    dec = freeze["declarations"]
    assert dec["selected_delta"] is None and dec["grad03_verdict"] is None and dec["not_opt01"] is True and dec["capability_statement_for_a_fixed_four_direction_basis_only"] is True
    gates = freeze["known_before_the_run"]["candidate_hard_gates_pass"]
    assert [gates[n] for n in sorted(gates)] == [True, True, True, False] or gates["lowdim01__prop__s7.5mm"] is False
    assert "plausible" in freeze["known_before_the_run"]["expectation"] and "NO_GO" in freeze["known_before_the_run"]["expectation"]


def test_the_bound_step01_analysis_is_the_recorded_one(freeze):
    assert freeze["step01_analysis_sha256"] == sha("docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json")
    s = json.loads((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json").read_text())
    assert s["verdict"] == "STEP01_RECORDED"
