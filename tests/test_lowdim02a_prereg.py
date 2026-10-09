"""LOWDIM-02A pre-registration: the freeze matches the files that will run; the rendered kernel carries its pins; the freeze keys are those the analyzer reads."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import analyze_lowdim02a as A  # noqa: E402
import build_lowdim02a_freeze as F  # noqa: E402
import build_lowdim02a_kernel as B  # noqa: E402

E = ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
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


def test_the_keys_the_analyzer_reads_are_held_by_the_freeze(freeze):
    for key in ("analyzer", "contract", "step01_states_module", "force_io", "formal_criteria", "job", "lowdim01_analysis", "inventory_canonical_json"):
        assert key in freeze["file_hashes"]
    assert freeze["pins"] and freeze["flow32_baseline"]["forces_csv_sha256"] == freeze["file_hashes"]["w4_flow32_baseline_csv"]


def test_the_rendered_kernel_carries_the_frozen_pins_and_identity(freeze):
    spec = importlib.util.spec_from_file_location("lowdim02a_runner", ROOT / "infra/kaggle/kernel_lowdim02a_a/runner.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.KERNEL == "a" and mod.SOURCE_COMMIT == freeze["source_commit"] and len(mod.SOURCE_COMMIT) == 40 and mod.PINS == freeze["pins"]
    assert mod.FLOW32_BASELINE_CSV_SHA256 == freeze["flow32_baseline"]["forces_csv_sha256"] and mod.KERNEL_TIMEOUT_S == freeze["design"]["kernel_timeout_s"] == B.TIMEOUT_S
    meta = json.loads((ROOT / "infra/kaggle/kernel_lowdim02a_a/kernel-metadata.json").read_text())
    assert meta["id"] == freeze["design"]["kernel_id"] and meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == []
    for rel, digest in freeze["pins"].items():
        assert B.sha(ROOT / rel) == digest, rel
    assert json.loads((E / "identity_free_check.json").read_text())["all_free"] is True


def test_the_registered_design_rules_and_declarations(freeze):
    d, r = freeze["design"], freeze["rules"]
    assert d["case"] == "flow_32" and len(d["states"]) == 5 and d["reinitialization"] == "none" and d["descriptive_only_state"] == "lowdim02a__prop__s2.5mm"
    assert r["min_resolved_n"] == pytest.approx(3e-5) and r["noise_factor"] == 10.0 and r["flow32_case"]["flow_spacing_m"] == 0.025
    assert freeze["verdicts"] == ["STAGE_A_PASS", "STAGE_A_SIGN_FLIP", "STAGE_A_UNRESOLVED", "STAGE_A_CONSTRAINT_FAIL", "STAGE_A_INCOMPLETE"]
    assert set(freeze["qualification_flags"].values()) == {False} and all(freeze["prohibitions"].values())
    dec = freeze["declarations"]
    assert dec["selected_delta"] is None and dec["grad03_verdict"] is None and dec["not_grid01"] is True and dec["not_opt01"] is True and dec["stage_b_requires_separate_preregistration"] is True
    assert "SIGN_FLIP" in freeze["known_before_the_run"]["expectation"] and "UNRESOLVED" in freeze["known_before_the_run"]["expectation"]


def test_the_analyzer_accepts_the_freeze_key_set_on_a_synthetic_kernel(freeze, tmp_path):
    import lowdim02a_synthetic as SYN
    out, fr, inv = SYN.make_all(tmp_path)
    assert set(fr["file_hashes"]) <= set(freeze["file_hashes"]) and set(fr) - {"pins", "source_commit", "file_hashes", "flow32_baseline"} == set()
    assert A.analyze(out, fr, inventory=inv, formal=SYN.FORMAL)["verdict"] == "STAGE_A_PASS"
