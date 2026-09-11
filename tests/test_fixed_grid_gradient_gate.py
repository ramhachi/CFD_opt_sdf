from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cfd_sdf.fixed_grid_gradient_gate import (
    aggregate_fixed_grid_gradient_gate,
    write_fixed_grid_gradient_gate,
)


def _artifact_set(tmp_path: Path, name: str) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for role in (
        "direction_summary_json",
        "validation_report_json",
        "sensitivity_vti",
        "direction_vti",
        "baseline_primal_summary_json",
        "baseline_case_metadata_json",
        "baseline_topology_state_json",
        "baseline_density_vti",
        "plus_primal_summary_json",
        "plus_case_metadata_json",
        "plus_input_density_vti",
        "minus_primal_summary_json",
        "minus_case_metadata_json",
        "minus_input_density_vti",
        "plus_topology_state_json",
        "minus_topology_state_json",
    ):
        path = tmp_path / f"{name}_{role}.artifact"
        path.write_text(f"{name}:{role}\n", encoding="utf-8")
        paths[role] = path
    return paths


def _suite(tmp_path: Path, *, mode: str, epsilon: float, name: str, seed: int | None = None, **overrides):
    artifacts = _artifact_set(tmp_path, name)
    direction_summary = {
        "kind": "fixed_grid_sensitivity_direction_summary",
        "direction_mode": mode,
        "epsilon": epsilon,
        "direction_info": ({"perturbation_seed": seed} if seed is not None else {}),
        "statistics": {
            "requested_direction_active": {"l2": 2.0},
            "actual_direction_active": {"l2": 1.0},
        },
        "problem_binding": _binding(),
    }
    direction_path = artifacts["direction_summary_json"]
    direction_path.write_text(json.dumps(direction_summary), encoding="utf-8")
    validation = {
        "status": "pass",
        "objective": "downforce",
        "finite_difference_derivative": 2.0,
        "adjoint_directional_derivative": 2.0,
        "finite_difference_to_adjoint_ratio": 1.0,
        "relative_error": 0.0,
        "sign_match": True,
        "report_json": str(artifacts["validation_report_json"]),
        "problem_binding": _binding(),
    }
    artifacts["validation_report_json"].write_text(json.dumps(validation), encoding="utf-8")
    artifacts["baseline_topology_state_json"].write_text("{}", encoding="utf-8")
    artifacts["baseline_density_vti"].write_bytes(b"baseline-density\n")
    artifacts["baseline_case_metadata_json"].write_text(
        json.dumps(
            {
                "topology_state_json": str(artifacts["baseline_topology_state_json"]),
                "density_vti": str(artifacts["baseline_density_vti"]),
            }
        ),
        encoding="utf-8",
    )
    perturbed_contracts = {}
    for label in ("plus", "minus"):
        metadata_path = artifacts[f"{label}_case_metadata_json"]
        metadata_path.write_text(
            json.dumps({"problem_binding": _binding()}),
            encoding="utf-8",
        )
        density_path = artifacts[f"{label}_input_density_vti"]
        topology_path = artifacts[f"{label}_topology_state_json"]
        topology_path.write_text(
            json.dumps(
                {
                    "problem_id": _binding()["problem_id"],
                    "problem_spec_sha256": _binding()["problem_spec_sha256"],
                    "candidate_id": _binding()["candidate_id"],
                    "parent_candidate_id": _binding()["parent_candidate_id"],
                    "iteration": _binding()["iteration"],
                    "density_vti": str(density_path),
                    "density_sha256": hashlib.sha256(density_path.read_bytes()).hexdigest(),
                    "baseline_candidate_binding": _binding(),
                }
            ),
            encoding="utf-8",
        )
        perturbed_contracts[label] = {
            "topology_state_json": str(topology_path),
            "topology_state_sha256": hashlib.sha256(topology_path.read_bytes()).hexdigest(),
            "density_vti": str(density_path),
            "density_sha256": hashlib.sha256(density_path.read_bytes()).hexdigest(),
        }
    summary = {
        "kind": "fixed_grid_sensitivity_direction_suite_summary",
        "status": "pass",
        "direction_mode": mode,
        "epsilon": epsilon,
        "direction_summary_json": str(direction_path),
        "sensitivity_vti": str(artifacts["sensitivity_vti"]),
        "direction_vti": str(artifacts["direction_vti"]),
        "plus_topology_state_json": str(artifacts["plus_topology_state_json"]),
        "minus_topology_state_json": str(artifacts["minus_topology_state_json"]),
        "validation": validation,
        "baseline_case_dir": str(tmp_path / "no_case_dir"),
        "baseline_case": {
            "summary": {
                "status": "converged",
                "convergence": {"primal_converged": True},
            },
            "primal_summary_json": str(artifacts["baseline_primal_summary_json"]),
            "case_metadata_json": str(artifacts["baseline_case_metadata_json"]),
        },
        "plus_case": {
            "summary": {"status": "converged", "convergence": {"primal_converged": True}},
            "primal_summary_json": str(artifacts["plus_primal_summary_json"]),
            "case_metadata_json": str(artifacts["plus_case_metadata_json"]),
            "input_density_vti": str(artifacts["plus_input_density_vti"]),
        },
        "minus_case": {
            "summary": {"status": "converged", "convergence": {"primal_converged": True}},
            "primal_summary_json": str(artifacts["minus_primal_summary_json"]),
            "case_metadata_json": str(artifacts["minus_case_metadata_json"]),
            "input_density_vti": str(artifacts["minus_input_density_vti"]),
        },
        "clipping": {"clipped_count": 2, "clipped_fraction": 0.25},
        "noise_floor": 0.1,
        "grid": {"cell_order": "vtk-x-fastest", "cell_shape": [2, 2, 1]},
        "problem_binding": _binding(),
        "perturbed_contracts": perturbed_contracts,
    }
    summary.update(overrides)
    if seed is not None:
        summary["perturbation_seed"] = seed
    return summary


def _binding() -> dict[str, object]:
    return {
        "problem_id": "synthetic-fixed-grid",
        "problem_spec_sha256": "a" * 64,
        "execution_ready": True,
        "candidate_id": "candidate_0000",
        "parent_candidate_id": None,
        "iteration": 0,
        "candidate_binding_sha256": "b" * 64,
        "canonical_grid_sha256": "c" * 64,
        "geometry_manifest_sha256": "d" * 64,
        "baseline_topology_state_sha256": hashlib.sha256(b"{}").hexdigest(),
        "baseline_density_sha256": hashlib.sha256(b"baseline-density\n").hexdigest(),
        "rho_variant": "rho",
        "binding_validation": "verified_stage_t_candidate_binding",
    }


def test_gradient_gate_accepts_complete_unique_matrix_and_writes_hashes(tmp_path: Path) -> None:
    suites = [
        _suite(tmp_path, mode="sensitivity", epsilon=epsilon, name=f"s{epsilon}")
        for epsilon in (1.0e-4, 3.0e-4)
    ]
    suites.extend(
        _suite(
            tmp_path,
            mode="filtered-random",
            seed=7,
            epsilon=epsilon,
            name=f"r{epsilon}",
        )
        for epsilon in (1.0e-4, 3.0e-4)
    )

    report = aggregate_fixed_grid_gradient_gate(
        suites,
        required_directions=("sensitivity", "filtered-random:seed=7"),
        required_epsilons=(1.0e-4, 3.0e-4),
        problem_binding=_binding(),
    )

    assert report["status"] == "pass"
    assert report["ok"] is True
    assert report["coverage"]["complete"] is True
    assert report["coverage"]["required_pair_count"] == 4
    present = [item for item in report["artifact_hashes"] if item["status"] == "present"]
    assert present
    assert all(len(item["sha256"]) == 64 for item in present)
    assert report["rows"][0]["clipping"]["bound"] is True
    assert report["rows"][0]["noise_floor"]["passed"] is True

    output = write_fixed_grid_gradient_gate(report, tmp_path / "gradient_validation.json")
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "pass"
    assert saved["artifact_hashes"] == report["artifact_hashes"]


def test_gradient_gate_fails_closed_for_duplicate_and_missing_pairs(tmp_path: Path) -> None:
    first = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="first")
    duplicate = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="duplicate")
    report = aggregate_fixed_grid_gradient_gate(
        [first, duplicate],
        required_directions=("sensitivity", "filtered-random"),
        required_epsilons=(1.0e-4, 3.0e-4),
        problem_binding=_binding(),
    )

    assert report["status"] == "fail"
    assert "duplicate_direction_epsilon_rows" in report["coverage"]["failures"]
    assert "missing_required_direction_epsilon_pairs" in report["coverage"]["failures"]
    assert report["ok"] is False


def test_gradient_gate_is_diagnostic_only_without_problem_binding(tmp_path: Path) -> None:
    suites = [
        _suite(tmp_path, mode="sensitivity", epsilon=epsilon, name=f"s{epsilon}")
        for epsilon in (1.0e-4, 3.0e-4)
    ]
    suites.extend(
        _suite(
            tmp_path,
            mode="filtered-random",
            seed=7,
            epsilon=epsilon,
            name=f"r{epsilon}",
        )
        for epsilon in (1.0e-4, 3.0e-4)
    )
    report = aggregate_fixed_grid_gradient_gate(
        suites,
        required_directions=("sensitivity", "filtered-random:seed=7"),
        required_epsilons=(1.0e-4, 3.0e-4),
    )

    assert report["status"] == "diagnostic_only"
    assert report["problem_binding_status"] == "missing"
    assert "problem_binding_missing" in report["evidence_gaps"]
    assert report["ok"] is False


def test_gradient_gate_requires_binding_on_every_row(tmp_path: Path) -> None:
    suite = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="missing-row-binding")
    del suite["problem_binding"]
    report = aggregate_fixed_grid_gradient_gate(
        [suite],
        required_directions=("sensitivity",),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )

    assert report["status"] == "diagnostic_only"
    assert report["problem_binding_status"] == "incomplete"
    assert "row_problem_binding_missing" in report["evidence_gaps"]


def test_gradient_gate_rejects_perturbed_topology_binding_mismatch(
    tmp_path: Path,
) -> None:
    suite = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="mismatch")
    plus_state = Path(suite["plus_topology_state_json"])
    mismatched = _binding()
    mismatched["candidate_id"] = "different_candidate"
    plus_state.write_text(
        json.dumps({"baseline_candidate_binding": mismatched}),
        encoding="utf-8",
    )

    report = aggregate_fixed_grid_gradient_gate(
        [suite],
        required_directions=("sensitivity",),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )

    assert report["status"] == "fail"
    assert report["rows"][0]["perturbed_topology_binding_status"] == "invalid"
    assert "plus_topology_candidate_binding_mismatch" in report["rows"][0]["failures"]


def test_gradient_gate_rejects_direction_and_primal_metadata_binding_tamper(
    tmp_path: Path,
) -> None:
    suite = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="row-tamper")
    direction_path = Path(suite["direction_summary_json"])
    direction = json.loads(direction_path.read_text(encoding="utf-8"))
    direction["problem_binding"]["candidate_id"] = "different_candidate"
    direction_path.write_text(json.dumps(direction), encoding="utf-8")
    plus_metadata = Path(suite["plus_case"]["case_metadata_json"])
    metadata = json.loads(plus_metadata.read_text(encoding="utf-8"))
    metadata["problem_binding"]["iteration"] = 1
    plus_metadata.write_text(json.dumps(metadata), encoding="utf-8")

    report = aggregate_fixed_grid_gradient_gate(
        [suite],
        required_directions=("sensitivity",),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )

    failures = report["rows"][0]["failures"]
    assert report["status"] == "fail"
    assert "direction_summary_problem_binding_mismatch" in failures
    assert "plus_case_metadata_problem_binding_mismatch" in failures


def test_gradient_gate_rejects_reused_plus_minus_topology_state(
    tmp_path: Path,
) -> None:
    suite = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="reused-state")
    suite["minus_topology_state_json"] = suite["plus_topology_state_json"]

    report = aggregate_fixed_grid_gradient_gate(
        [suite],
        required_directions=("sensitivity",),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )

    assert report["status"] == "fail"
    assert "plus_minus_topology_state_not_distinct" in report["rows"][0]["failures"]


def test_gradient_gate_records_noise_floor_and_rejects_numeric_failure(tmp_path: Path) -> None:
    suite = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="bad")
    suite["validation"]["sign_match"] = False
    suite["validation"]["finite_difference_to_adjoint_ratio"] = 1.5
    suite["validation"]["relative_error"] = 0.5
    report = aggregate_fixed_grid_gradient_gate(
        [suite],
        required_directions=("sensitivity",),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )

    assert report["status"] == "fail"
    assert "ratio_out_of_bounds" in report["rows"][0]["failures"]
    assert "relative_error_out_of_bounds" in report["rows"][0]["failures"]
    assert "sign_match_missing_or_false" in report["rows"][0]["failures"]
    assert report["rows"][0]["noise_floor"]["threshold"] == 0.1


def test_gradient_gate_hash_is_sha256_of_artifact_bytes(tmp_path: Path) -> None:
    suite = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="hash")
    report = aggregate_fixed_grid_gradient_gate(
        [suite],
        required_directions=("sensitivity",),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )
    target = Path(suite["sensitivity_vti"])
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    found = next(item for item in report["rows"][0]["artifacts"] if item["role"] == "sensitivity_vti")
    assert found["sha256"] == expected


def test_gradient_gate_rejects_mixed_objectives(tmp_path: Path) -> None:
    downforce = _suite(tmp_path, mode="sensitivity", epsilon=1.0e-4, name="downforce")
    efficiency = _suite(
        tmp_path,
        mode="filtered-random",
        epsilon=1.0e-4,
        name="efficiency",
        seed=7,
        objective="efficiency_constraint",
    )
    report = aggregate_fixed_grid_gradient_gate(
        [downforce, efficiency],
        required_directions=("sensitivity", "filtered-random:seed=7"),
        required_epsilons=(1.0e-4,),
        problem_binding=_binding(),
    )

    assert report["status"] == "fail"
    assert report["objective"] is None
    assert report["observed_objectives"] == ["downforce", "efficiency_constraint"]
    assert "mixed_objectives" in report["failures"]
