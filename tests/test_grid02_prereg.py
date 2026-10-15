"""Freeze/closure checks (like test_lowdim03_prereg): every file the freeze binds is committed at HEAD once it exists; the real freeze, once it exists, validates with the analyzer; the freeze script is write-once."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import analyze_grid02 as A  # noqa: E402
import build_grid02_kernel as K  # noqa: E402
import freeze_grid02 as F  # noqa: E402

EV = ROOT / A.EVIDENCE_REL
INV = json.loads((EV / "inventory.json").read_text())
FREEZE = EV / "prerun_freeze.json"
PRE_FREEZE_ABSENT = {A.EVIDENCE_REL + "/identity_free_check.json", A.EVIDENCE_REL + "/identity_free_check.json.sha256"}  # captured only at freeze time (needs the authenticated Kaggle listing)


def committed(name):
    return subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"HEAD:{name}"], capture_output=True).returncode == 0


def test_every_file_the_freeze_binds_is_committed_at_head_once_it_exists():
    for rel in sorted(A.required_file_paths(INV)):
        path = ROOT / rel
        if not path.exists():
            assert rel in PRE_FREEZE_ABSENT and not FREEZE.exists(), f"missing: {rel}"
            continue
        names = [rel] if path.is_file() else [str(p.relative_to(ROOT)) for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        for name in names:
            assert committed(name), f"not committed: {name}"


def test_the_pin_closure_covers_the_runtime_inputs_and_every_pin_is_in_the_freeze_closure():
    closure = A.required_file_paths(INV)
    for k in K.KERNEL_IDS:
        pins = K.pins(k)
        assert {INV["kernel_config"][k]["job"], INV["parent"]["raw_path"], INV["proposal"]["file"], f"{A.EVIDENCE_REL}/inventory.json", "scripts/step01_states.py", "scripts/grid01_gpu.py"} <= set(pins)
        for rel in pins:
            path = ROOT / rel
            assert (rel in closure) if path.is_file() else all(str(p.relative_to(ROOT)) in closure for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts), rel


def test_parent_commit_is_the_approved_integration_commit_and_an_ancestor():
    assert subprocess.run(["git", "-C", str(ROOT), "rev-parse", "ced45f1"], capture_output=True, text=True).stdout.strip() == A.PARENT_COMMIT
    assert subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", A.PARENT_COMMIT, "HEAD"]).returncode == 0


def test_declared_runtime_numbers_and_rules_match_the_contract():
    from cfd_sdf import grid02_contract as C
    for k, spec in C.KERNELS.items():
        r = A.expected_runtime(k, INV["kernel_config"][k], "0" * 64, "1" * 64)
        assert (r["per_state_timeout_s"], r["solver_wall_time_cap_s"], r["kernel_timeout_s"], r["timeout_s"]) == (spec["per_state_timeout_s"], C.aggregate_cap_s(k), spec["kernel_timeout_s"], spec["kernel_timeout_s"])
        assert r["W4_CANONICAL_ORIGIN_M"] == C.origin_env(spec["placement"]) and r["GRID02_CASE"] == spec["grid02_case"] and r["julia_threads"] == 1 and r["machine_shape"] == "NvidiaTeslaT4"
    assert A.RULES["resolution_floor_n"] == C.RESOLUTION_FLOOR_N == 3e-5 and A.RULES["hindcast_band_flow_48_parent_downforce_n"] == [0.38, 0.40] and A.RULES["decision_map"] == C.DECISIONS
    assert {"flow_16", "flow_24", "flow_32", "flow_48"} == set(C.CELLS) and len(A.QUALIFICATION_FLAGS) == 6


def test_identity_free_slugs_and_freeze_script_surface():
    assert [r.split("/")[1] for r in K.KERNEL_IDS.values()] == [f"cfd-opt-sdf-grid02-{k}" for k in ("s24", "s32", "f48a", "f48b", "f16")]
    assert F.IDENTITY == EV / "identity_free_check.json" and F.OWNER == "ramhachi888"
    with pytest.raises(ValueError, match="mismatch"):
        F.require_identity({"all_free": False})


@pytest.mark.skipif(not FREEZE.exists(), reason="no GRID-02 prerun freeze yet")
def test_the_real_freeze_validates_with_the_analyzer_and_is_sidecar_bound():
    freeze = json.loads(FREEZE.read_text())
    assert FREEZE.with_name("prerun_freeze.json.sha256").read_text().strip() == A.sha256(FREEZE)
    A.validate_registration(freeze, INV)
    assert freeze["selected_delta"] is None and freeze["shape_update_allowed"] is False and set(freeze["qualification_flags"].values()) == {False}
    for rel in list(freeze["file_hashes"]) + [f"infra/kaggle/kernel_grid02_{k}/{n}" for k in K.KERNEL_IDS for n in ("runner.py", "kernel-metadata.json")] + [A.EVIDENCE_REL + "/prerun_freeze.json"]:
        assert committed(rel), f"not committed: {rel}"


@pytest.mark.skipif(not FREEZE.exists(), reason="no GRID-02 prerun freeze yet")
def test_freeze_is_write_once():
    with pytest.raises(ValueError, match="refusing to overwrite"):
        F.freeze("0" * 40)
