"""STEP-01 input states: the registered inventory is reproduced from the committed raws by the numpy function the runner uses, the plan matches, geometry gates hold."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import step01_states as S  # noqa: E402

E = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
INV = json.loads((E / "inventory.json").read_text())
IN = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
BASE = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"


def test_plan_counts_names_and_registered_grid():
    plans = S.all_plans()
    assert {k: len(v) for k, v in plans.items()} == {"a": 21, "b": 21, "c": 5} and all(v[0]["name"] == S.BASELINE_NAME for v in plans.values())
    assert S.STEP_MM == tuple(f * 25 for f in S.FRACTIONS_H) and S.COMBO_STEP_MM == 7.5 and S.FRACTIONS_H == (0.1, 0.2, 0.3, 0.4, 0.5)
    names = [x["name"] for v in plans.values() for x in v if x["kind"] != "baseline"]
    assert len(names) == 44 == len(set(names)) and all(n.startswith("step01__") for n in names)          # disjoint from the FD-08 state names
    assert INV["kernels"] == {k: [x["name"] for x in v] for k, v in plans.items()} and len(INV["states"]) == 47


def test_every_registered_state_is_reproduced_by_the_runner_numpy_function():
    phi = S.read_f4(BASE)
    assert S.sha256_bytes(S.to_raw(phi)) == INV["baseline"]["phi_fortran_sha256"]
    dirs = {n: S.read_f4(IN / e["file"]) for n, e in INV["directions"].items()}
    for n, e in INV["directions"].items():
        assert S.sha256_bytes((IN / e["file"]).read_bytes()) == e["sha256_fortran_raw"] and float(np.max(np.abs(dirs[n]))) == 1.0
    combos = {}
    for key, c in INV["combined_directions"].items():
        a, b = c["pair"]
        d, m = S.combo_direction(dirs[a], dirs[b])
        assert S.sha256_bytes(S.to_raw(d)) == c["sha256_fortran_raw"] == S.sha256_bytes((ROOT / c["file"]).read_bytes()) and m == c["m_max_abs_sum"]
        assert c["component_step_mm"] == pytest.approx(S.COMBO_STEP_MM / m, rel=1e-15) and float(np.max(np.abs(d))) == 1.0
        combos[key] = d
    seen = set()
    for row in INV["states"]:
        if row["kind"] == "baseline":
            assert row["phi_fortran_order_sha256"] == INV["baseline"]["phi_fortran_sha256"] and row["changed_node_count"] == 0
            continue
        d = dirs[row["directions"][0]] if row["kind"] == "single" else combos["+".join(row["directions"])]
        raw = S.to_raw(S.perturb(phi, d, row["step_mm"], row["sign"]))
        assert S.sha256_bytes(raw) == row["phi_fortran_order_sha256"], row["name"]
        assert int(np.count_nonzero(np.frombuffer(raw, "<f4") != np.frombuffer(S.to_raw(phi), "<f4"))) == row["changed_node_count"] > 0
        assert raw not in seen and raw != S.to_raw(phi)
        seen.add(raw)


def test_geometry_gates_and_realised_step_in_the_inventory():
    for row in INV["states"]:
        assert row["zero_level_margin_m"] >= INV["margin_gate_m"] == 0.15 and row["margin_tolerance_m"] == 1e-6
        if row["kind"] != "baseline":
            assert abs(row["realized_over_requested"] - 1.0) < 1e-6 and row["maximum_pointwise_change_m"] == pytest.approx(row["step_mm"] / 1000.0, rel=1e-6)
    combo = [r for r in INV["states"] if r["kind"] == "combo"]
    assert len(combo) == 4 and all(r["step_mm"] == 7.5 and r["combo_m_max_abs_sum"] > 0 for r in combo)
    assert INV["job_env_common"]["W4_MARGIN_GATE_M"] == "0.15" and INV["fd08_baseline_reference"]["forces_csv_sha256"].startswith("39370386")


def test_perturbation_rejects_bad_arguments():
    phi = np.zeros(S.SHAPE, dtype="<f4")
    with pytest.raises(ValueError):
        S.perturb(phi, phi, 2.5, 0)
    with pytest.raises(ValueError):
        S.perturb(phi, phi, -2.5, 1)
    with pytest.raises(ValueError):
        S.combo_direction(phi, phi)
