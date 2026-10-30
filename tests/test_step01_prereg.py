"""STEP-01 pre-registration: the freeze matches the files that will run, the rendered kernels carry its pins, and the registered design is consistent."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import build_step01_freeze as F  # noqa: E402
import build_step01_kernels as B  # noqa: E402
import step01_states as S  # noqa: E402

E = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
FREEZE_PATH = E / "prerun_freeze.json"
pytestmark = pytest.mark.skipif(not FREEZE_PATH.is_file(), reason="freeze not written yet")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def freeze():
    return json.loads(FREEZE_PATH.read_text())


def load(kernel):
    spec = importlib.util.spec_from_file_location(f"r_{kernel}", ROOT / f"infra/kaggle/kernel_step01_{kernel}/runner.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_sidecar_and_every_frozen_file_hash(freeze):
    assert hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest() == (E / "prerun_freeze.json.sha256").read_text().strip()
    for name, path in F.FILES.items():
        assert freeze["file_hashes"][name] == sha(path), name
    assert freeze["file_hashes"]["inventory_canonical_json"] == freeze["file_hashes"]["inventory"]


@pytest.mark.parametrize("kernel", ["a", "b", "c"])
def test_the_rendered_kernels_carry_the_frozen_pins_and_identity(freeze, kernel):
    mod = load(kernel)
    assert mod.KERNEL == kernel and mod.SOURCE_COMMIT == freeze["source_commit"] and len(mod.SOURCE_COMMIT) == 40
    assert mod.PINS == freeze["pins"] and mod.DIRECTION_FILES == freeze["direction_files"] and mod.FD08_BASELINE_CSV_SHA256 == freeze["fd08_baseline"]["forces_csv_sha256"]
    assert mod.KERNEL_TIMEOUT_S == freeze["design"]["kernel_timeout_s"][kernel] == B.TIMEOUT_S[kernel]
    meta = json.loads((ROOT / f"infra/kaggle/kernel_step01_{kernel}/kernel-metadata.json").read_text())
    assert meta["id"] == freeze["design"]["kernel_ids"][kernel] and meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == []
    used = {json.loads(p.read_text())["id"] for p in (ROOT / "infra/kaggle").glob("*/kernel-metadata.json") if p.parent.name != f"kernel_step01_{kernel}"}
    assert meta["id"] not in used
    for rel, digest in freeze["pins"].items():
        assert B.sha(ROOT / rel) == digest, rel


def test_the_design_constants_definitions_and_declarations(freeze):
    d = freeze["design"]
    assert d["states"] == 47 and d["kernels"] == {"a": 21, "b": 21, "c": 5} and d["step_mm"] == [2.5, 5.0, 7.5, 10.0, 12.5] and d["combo_step_mm"] == 7.5 and d["baseline_per_kernel"] is True
    assert d["primary_quantity"].startswith("g_sec(s) = [R(+s) - R(-s)]") and d["combos"] == [list(p) for p in S.COMBOS]
    assert freeze["definitions"]["agreement_tolerances"] == [0.3, 0.5] and freeze["definitions"]["nominal_sigma0_n"] == 3e-6 and freeze["definitions"]["resolved_factor"] == 10.0
    assert freeze["verdicts"] == ["STEP01_RECORDED", "STEP01_INCOMPLETE"] and set(freeze["qualification_flags"].values()) == {False} and all(freeze["prohibitions"].values())
    dec = freeze["declarations"]
    assert dec["selected_delta"] is None and dec["grad03_verdict"] is None and dec["gradient_qualification"] is False and dec["fd08_verdict_unchanged"] is True
    assert dec["agreement_radius_is_descriptive"] is True and dec["g_hat_is_model_a_local_slope_not_the_epsilon_to_zero_derivative"] is True


def test_g_hat_fits_are_those_of_the_frozen_formal_criteria(freeze):
    fits = json.loads((ROOT / F.FILES["formal_criteria"]).read_text())["calibration_binding"]["fits"]
    assert len(freeze["fd08_g_hat_fits"]) == 8
    for k, v in freeze["fd08_g_hat_fits"].items():
        assert fits[k]["g_n_per_m"] == v["g_n_per_m"] and fits[k]["se_g_n_per_m"] == v["se_g_n_per_m"]


def test_earlier_records_are_bound_and_unchanged(freeze):
    for rel, digest in freeze["diag5_evidence_sha256"].items():
        assert hashlib.sha256((ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09" / rel).read_bytes()).hexdigest() == digest
    assert freeze["runtime"]["accelerator"] == "NvidiaTeslaT4" and freeze["runtime"]["julia_version"] == "1.12.6"
    assert json.loads((E / "identity_free_check.json").read_text())["all_free"] is True
