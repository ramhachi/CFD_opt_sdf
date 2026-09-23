"""Small contract tests for the append-only PQ3.3b v5 preflight."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pq3_3b_preflight_v5", REPO / "scripts" / "pq3_3b_preflight_v5_2026_09.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_level_lineage_uses_objective_accepted_rho() -> None:
    restoration_rho = np.array([0.1, 0.3])
    objective_rho = np.array([0.2, 0.3])
    previous = {
        "phase1": {"accepted_rho_sha256": MODULE.sha256_array(restoration_rho)},
        "objective_accepted": {"rho_sha256": MODULE.sha256_array(objective_rho)},
    }

    accepted_lineage = MODULE.objective_accepted_lineage(previous, objective_rho)
    assert accepted_lineage["exact_rho_carryover"] is True
    assert accepted_lineage["previous_objective_accepted_rho_sha256"] == MODULE.sha256_array(objective_rho)

    restoration_only_lineage = MODULE.objective_accepted_lineage(previous, restoration_rho)
    assert restoration_only_lineage["exact_rho_carryover"] is False


def test_missing_objective_acceptance_cannot_start_next_level() -> None:
    rho = np.array([0.1, 0.3])
    previous = {"phase1": {"accepted_rho_sha256": MODULE.sha256_array(rho)}}
    assert MODULE.objective_accepted_lineage(previous, rho)["exact_rho_carryover"] is False


def test_noise_repeat_must_have_two_fresh_case_directories() -> None:
    a = {"case_dir": "/tmp/noise-a/case", "summary_sha256": "a", "reused": False}
    b = {"case_dir": "/tmp/noise-b/case", "summary_sha256": "b", "reused": False}
    assert MODULE.independent_noise_runs(a, b) is True
    assert MODULE.independent_noise_runs(a, {**b, "reused": True}) is False
    assert MODULE.independent_noise_runs(a, {**b, "case_dir": a["case_dir"]}) is False
    assert MODULE.independent_noise_runs(a, {**b, "summary_sha256": None}) is False


def test_partial_or_failed_final_level_is_not_a_completed_chain() -> None:
    levels = ({"name": "b4"}, {"name": "b8"}, {"name": "b16"})
    records = [
        {"level": name, "objective_accepted": {"rho_sha256": name}}
        for name in ("b4", "b8", "b16")
    ]
    assert MODULE.completed_objective_chain(records, levels) is True
    assert MODULE.completed_objective_chain(records[:2], levels) is False
    failed_b16 = [*records[:2], {"level": "b16", "objective_accepted": None}]
    assert MODULE.completed_objective_chain(failed_b16, levels) is False
