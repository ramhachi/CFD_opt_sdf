"""Verify retained GRID-01 evidence without re-running the analyzer or any solver."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import analyze_grid01 as A  # noqa: E402
from cfd_sdf import grid01_contract as C  # noqa: E402
from fd08_v2_campaign_io import clipped_window, read_force_history  # noqa: E402

E = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"
K = E / "kernel_output/grid01_a"


def load(path):
    assert path.is_file(), f"retained evidence missing: {path}"
    return json.loads(path.read_text())


def sha(path):
    assert path.is_file(), f"retained evidence missing: {path}"
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def evidence():
    return (load(E / "prerun_freeze_amend1.json"), load(E / "inventory.json"),
            load(E / "grid01_analysis.json"))


@pytest.fixture(scope="module")
def forces(evidence):
    freeze, inventory, _ = evidence
    measurement = freeze["measurement"]["flow32_measurement"]
    case = measurement["case"]
    start, end = measurement["time_window_t_u_l"]
    assert [start, end] == [80.0, 120.0]
    scale = case["density_kg_m3"] * case["freestream_mps"][0] ** 2 * case["flow_spacing_m"] ** 2
    assert scale == pytest.approx(6.25e-4, rel=1e-15)
    values = {}
    for state in inventory["states"]:
        rows = read_force_history(K / "states" / state["name"] / "flow_32.forces.csv")
        window = clipped_window(rows, start, end)
        assert window[0]["t_u_l"] == start and window[-1]["t_u_l"] == end
        # Independent trapezoidal arithmetic; do not call the production analyzer.
        values[state["name"]] = {
            q: scale * math.fsum((b["t_u_l"] - a["t_u_l"]) *
                                (a[f"{q}_solver"] + b[f"{q}_solver"]) / 2
                                for a, b in zip(window, window[1:])) / (end - start)
            for q in C.RESPONSES
        }
    return values


def test_amended_freeze_sidecar_pins_and_source_binding(evidence):
    freeze, inventory, analysis = evidence
    freeze_sha = sha(E / "prerun_freeze_amend1.json")
    assert freeze_sha == "522b409b75e9ab8579603770850683bde336fc010977a3916147fab7cdadf431"
    assert (E / "prerun_freeze_amend1.json.sha256").read_text().strip() == freeze_sha
    assert freeze["source_commit"] == "ea320dc5a95e9b98dc501b62574ea6ee26eaa211"
    assert A._validate_freeze(freeze, inventory, load(A.FORMAL), load(A.STEP01_ANALYSIS)) == []
    identity = load(K / "run_identity.json")
    assert identity["source_commit"] == freeze["source_commit"]
    assert identity["pins"] == identity["verified"] == freeze["pins"]
    assert identity["runner_sha256"] == freeze["file_hashes"]["rendered_runner"]
    assert identity["failure_stage"] is None
    assert identity["selected_gpu"]["name"] == "Tesla T4"
    assert identity["cuda_visible_devices"] == "0" and identity["cuda_device_order"] == "PCI_BUS_ID"
    assert analysis["provenance"] == {
        "freeze_sha256": freeze_sha, "source_commit": freeze["source_commit"],
        "analyzer_sha256": sha(ROOT / "scripts/analyze_grid01.py"),
        "kernel_manifest_sha256": sha(K / "output_manifest.json"),
        "step01_analysis_sha256": sha(A.STEP01_ANALYSIS),
    }


def test_exact_nine_completed_states_and_manifest_pathset(evidence):
    _, inventory, analysis = evidence
    names = ["step01__baseline"] + [f"step01__{d}__s2.5mm__{side}"
                                      for d in C.BASIS for side in ("plus", "minus")]
    index = load(K / "grid01_index.json")
    assert (K / "DONE").is_file() and not list(K.rglob("ERROR.txt"))
    assert index["status"] == "COMPLETE"
    assert index["kernel"] == "a" and index["kernel_id"] == "ramhachi888/cfd-opt-sdf-grid01-a"
    assert [s["name"] for s in index["states"]] == inventory["kernels"]["a"] == names
    assert {p.name for p in (K / "states").iterdir() if p.is_dir()} == set(names)
    assert all(s["complete"] is True and s["exit_code"] == 0 for s in index["states"])
    manifest = load(K / "output_manifest.json")["files"]
    actual = {str(p.relative_to(K)) for p in K.rglob("*") if p.is_file() and p.name != "output_manifest.json"}
    assert set(manifest) == actual
    assert all(sha(K / path) == digest for path, digest in manifest.items())
    for row, entry in zip(inventory["states"], index["states"]):
        directory = K / "states" / row["name"]
        assert (directory / "W4_JOB_DONE").is_file()
        summary = load(directory / "flow_32.summary.json")
        for key, source in (("state_sha256", "state_sha256"), ("state_npz_sha256", "npz_sha256"),
                            ("phi_fortran_sha256", "phi_fortran_order_sha256"), ("phi_c_order_sha256", "phi_c_order_sha256")):
            assert summary[key] == row[source]
        assert all(summary[key] is True for key in ("finite_u", "finite_p", "finite_forces"))
        assert summary["t_end_reached"] >= 120 and summary["julia_threads"] == 1
        assert summary["phi_margin_m"] == pytest.approx(row["zero_level_margin_m"], abs=row["margin_tolerance_m"])
        assert summary["flow_spacing_m"] == 0.025 and summary["flow_dims"] == [200, 96, 72]
        saved = analysis["measurements"]["state_forces_n"][row["name"]]
        assert entry["forces_csv_sha256"] == saved["forces_csv_sha256"] == sha(directory / "flow_32.forces.csv")
        assert saved["summary_sha256"] == sha(directory / "flow_32.summary.json")
        assert saved["geometry_gates"] == row["geometry_gates"]


def test_baseline_byte_identity_and_independent_time_weighted_forces(evidence, forces):
    freeze, _, analysis = evidence
    reference = ROOT / freeze["flow32_baseline_reference"]["forces_csv_path"]
    baseline = K / "states/step01__baseline/flow_32.forces.csv"
    assert baseline.read_bytes() == reference.read_bytes()
    assert sha(baseline) == "032ef1cfae320ada28d05a3ad5785fc1fd770b202d4f0d2e9ed8490c6ab61753"
    assert forces["step01__baseline"]["downforce"] == pytest.approx(0.3612783598966907, rel=1e-12)
    for name, values in forces.items():
        summary = load(K / "states" / name / "flow_32.summary.json")
        for q, value in values.items():
            assert value == pytest.approx(summary[f"{q}_time_weighted_n"], rel=1e-9)
            assert value == pytest.approx(analysis["measurements"]["state_forces_n"][name][f"{q}_n"], rel=1e-12)


def test_secants_sign_changes_and_vector_comparisons_reconstruct(evidence, forces):
    _, inventory, analysis = evidence
    m = analysis["measurements"]
    assert m["flow24_from_frozen_step01"] == inventory["flow24_reference_step01"]["secants"]
    step01 = load(A.STEP01_ANALYSIS)
    for d in C.BASIS:
        for q in C.RESPONSES:
            old = m["flow24_from_frozen_step01"][d][q]
            source = step01["series"][f"{d}|{q}"]["rows"][0]
            assert all(old[key] == source[key] for key in ("r0_n", "r_plus_n", "r_minus_n", "g_sec_n_per_m", "eta_even"))
            r0 = forces["step01__baseline"][q]
            plus, minus = (forces[f"step01__{d}__s2.5mm__{side}"][q] for side in ("plus", "minus"))
            contrast, even = plus - minus, (plus + minus - 2 * r0) / 2
            current = m["flow32_host_recomputed"][d][q]
            for key, value in {"r0_n": r0, "r_plus_n": plus, "r_minus_n": minus,
                               "contrast_plus_minus_n": contrast, "g_sec_n_per_m": contrast / 0.005,
                               "even_part_n": even, "eta_even": abs(2 * even / contrast)}.items():
                assert current[key] == pytest.approx(value, rel=1e-10, abs=1e-12)
            assert current["resolved"] is (abs(contrast) > 3e-5)
            comparison = analysis["component_comparisons"][d][q]
            assert old["resolved"] is True and current["resolved"] is True
            flipped = (old["g_sec_n_per_m"] > 0) != (contrast > 0)
            assert comparison["sign_status"] == ("sign_flipped_resolved" if flipped else "sign_preserved_resolved")
            assert comparison["raw_ratio_flow32_over_flow24"] == pytest.approx(contrast / 0.005 / old["g_sec_n_per_m"], abs=1e-11)
    flips = {(d, q) for d in C.BASIS for q in C.RESPONSES
             if analysis["component_comparisons"][d][q]["sign_status"] == "sign_flipped_resolved"}
    assert flips == {("D1_filtered_seed11", "downforce"), ("D0_interface_offset", "drag")}
    for q, quoted in (("downforce", (0.9839039751230935, 1.205829048460528)),
                      ("drag", (0.2787729380793491, 0.8927667710923167))):
        vectors = analysis["coefficient_vectors_n_per_m"][q]
        for grid, key in (("flow_24", "flow24_from_frozen_step01"), ("flow_32", "flow32_host_recomputed")):
            assert vectors[grid] == [m[key][d][q]["g_sec_n_per_m"] for d in C.BASIS]
        left, right = vectors["flow_24"], vectors["flow_32"]
        nl, nr = (math.sqrt(math.fsum(x * x for x in v)) for v in (left, right))
        comparison = analysis["coefficient_space_comparison_raw_finite_step_vectors"][q]
        assert comparison["cosine"] == pytest.approx(math.fsum(a * b for a, b in zip(left, right)) / (nl * nr), abs=1e-14)
        assert comparison["flow32_over_flow24_l2_norm"] == pytest.approx(nr / nl, abs=1e-14)
        assert (comparison["cosine"], comparison["flow32_over_flow24_l2_norm"]) == pytest.approx(quoted, abs=1e-12)


def test_saved_proposal_certificates_and_normalized_predictions(evidence):
    _, _, analysis = evidence
    vectors = analysis["coefficient_vectors_n_per_m"]
    lift, drag = (np.asarray([vectors[q][g] for g in C.GRIDS]) for q in C.RESPONSES)
    dirs = [np.fromfile(ROOT / A.FILE_PATHS[f"direction_{d}"], dtype="<f4").astype(np.float64) for d in C.BASIS]
    proposals, predictions = analysis["solver_free_proposals"], analysis["proposal_predictions_with_actual_m"]
    families = [(proposals[key], predictions[key], None, key == "robust_cross_grid")
                for key in ("main_cross_grid", "robust_cross_grid")]
    families += [(proposals["single_grid_references"][g][key], predictions["single_grid_references"][g][key], g, key == "robust")
                 for g in C.GRIDS for key in ("main", "robust")]
    for solution, prediction, grid, robust in families:
        verification = C.verify_cone_family(lift, drag, solution, robust=robust, one_grid=grid)
        assert verification["passed"] is True
        expected_branches = (16 if grid else 32) if robust else (1 if grid else 2)
        assert verification["branch_count"] == expected_branches
        c = np.asarray(solution["coefficient_vector"])
        assert np.linalg.norm(c) == pytest.approx(1.0, abs=1e-12)
        c = c / np.linalg.norm(c)
        m = float(np.max(np.abs(sum(ci * d for ci, d in zip(c, dirs)))))
        assert prediction["coefficient_vector"] == pytest.approx(c, abs=1e-14)
        assert prediction["m_max_abs_sum_from_actual_four_direction_arrays"] == pytest.approx(m, abs=1e-14)
        assert prediction["per_unit_step_basis_coefficients_c_over_m"] == pytest.approx(c / m, abs=1e-14)
        assert prediction["basis_coefficients_at_1p25mm"] == pytest.approx(0.00125 * c / m, abs=1e-15)
        slopes = []
        for g, saved in prediction["per_grid"].items():
            i = C.GRIDS.index(g)
            lift_slope, drag_slope = float(lift[i] @ c), float(drag[i] @ c)
            uncertainty = 0.006 * float(np.linalg.norm(c, ord=1))
            for prefix, slope in (("raw_downforce", lift_slope), ("raw_drag", drag_slope),
                                  ("l1_robust_downforce_lower", lift_slope - uncertainty),
                                  ("l1_robust_drag_upper", drag_slope + uncertainty)):
                assert saved[f"{prefix}_slope_n_per_m"] == pytest.approx(slope, abs=1e-13)
                assert saved[f"{prefix}_prediction_at_1p25mm_n"] == pytest.approx(slope * 0.00125 / m, abs=1e-15)
            assert drag_slope + (uncertainty if robust else 0) <= 1e-9
            slopes.append(lift_slope - (uncertainty if robust else 0))
        assert solution["t_star_n_per_m"] == pytest.approx(min(slopes), abs=1e-12)
        if grid:
            norm = float(np.linalg.norm(lift[C.GRIDS.index(grid)]))
            assert solution["retention_of_unconstrained_downforce"] == pytest.approx(solution["t_star_n_per_m"] / norm, abs=1e-14)
    assert proposals["main_cross_grid"]["t_star_n_per_m"] == pytest.approx(0.5002609628446586, abs=1e-12)
    assert proposals["robust_cross_grid"]["t_star_n_per_m"] == pytest.approx(0.4561908301534262, abs=1e-12)
    assert proposals["main_cross_grid"]["coefficient_vector"] == pytest.approx(
        [0.5385287018526949, 0.36957632057542344, 0.5983823515811342, -0.4640460557606484], abs=1e-12)
    assert proposals["robust_cross_grid"]["coefficient_vector"] == pytest.approx(
        [0.5088319704391167, 0.3741305629564562, 0.6314648863457621, -0.4498538040666822], abs=1e-12)
    decision = analysis["proposal_verdict"]
    assert decision["verdict"] == "FEASIBLE_CONE_FOUND" and decision["reasons"] == []
    assert all(v >= 3e-5 for v in decision["predictions_tested_n"].values())
    for key in ("main_cross_grid", "robust_cross_grid"):
        prefix = "raw_downforce" if key == "main_cross_grid" else "l1_robust_downforce_lower"
        for grid in C.GRIDS:
            assert decision["predictions_tested_n"][f"{key}|{grid}"] == predictions[key]["per_grid"][grid][f"{prefix}_prediction_at_1p25mm_n"]
    old = analysis["lowdim01_proposal_predictions_with_actual_m"]
    c = lift[0] / np.linalg.norm(lift[0])
    v = sum(ci * d for ci, d in zip(c, dirs))
    m = float(np.max(np.abs(v)))
    assert old["coefficient_unit_vector"] == pytest.approx(c, abs=1e-14)
    assert old["m_max_abs_sum_from_actual_four_direction_arrays"] == pytest.approx(m, abs=1e-14)
    assert old["basis_coefficients_per_m_of_max_abs_phi_step"] == pytest.approx(c / m, abs=1e-14)
    assert hashlib.sha256(np.asarray(v / m, dtype="<f4").tobytes()).hexdigest() == old["proposal_sha256"]
    for i, grid in enumerate(C.GRIDS):
        for q, vector in (("downforce", lift[i]), ("drag", drag[i])):
            slope = float(vector @ c)
            assert old["per_grid"][grid][f"raw_{q}_slope_n_per_m"] == pytest.approx(slope, abs=1e-13)
            assert old["per_grid"][grid][f"raw_{q}_prediction_at_1p25mm_n"] == pytest.approx(slope * 0.00125 / m, abs=1e-15)


def test_recorded_scope_and_historical_hashes_remain_unchanged(evidence):
    _, _, analysis = evidence
    assert sha(E / "grid01_analysis.json") == "ec00ed9afe4f44926dd40ff1e87f303dd9baf89195b19cb550103606beedb69c"
    assert sha(E / "prerun_freeze.json") == "f18201ee87aac3ea6a302e5d8e08ec48311ca33be6136a4a7a3cb4abd539fe9b"
    assert sha(E / "failed_attempt1/output_manifest.json") == "2e961522a159647cb207d32949a69de0fe0ec0030d356aeb20f8e1e28b69c302"
    assert sha(E / "failed_attempt1/ERROR.txt") == "c0a9bc857b0d2f78f428b472e9163a97211f0bc9000a430e7322aa48fad82ed5"
    assert analysis["verdict"] == "GRID01_SECANT_RECORDED" and analysis["integrity"] == {"pass": True, "failures": []}
    assert analysis["evidence_class"] == "bounded_cross_grid_finite_step_observation"
    assert analysis["selected_delta"] is None and analysis["grad03_verdict"] is None
    assert all(analysis[key] is True for key in ("fd08_verdict_unchanged", "no_gradient_claim", "not_grid_converged", "not_opt01"))
    assert analysis["reinitialization"] == "none" and analysis["shape_update_allowed"] is False
    assert set(analysis["qualification_flags"].values()) == {False}
    assert analysis["proposal_verdict"]["descriptive_only"] is True and analysis["proposal_verdict"]["no_cfd_authorized"] is True
