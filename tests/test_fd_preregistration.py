"""Tests for the fixed-grid transfer diagnostic (DF2/P6) and FD preregistration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfd_sdf.fd_preregistration import (
    FD_QUALIFICATION_PROFILE_V1,
    FD_V2_REQUIRED_BASE_GATES,
    FD_V2_REQUIRED_PERTURBATION_GATES,
    FdDirection,
    FdDirectionV2,
    FdPreregistrationError,
    build_fd_campaign_manifest,
    build_fd_campaign_manifest_v2,
    evaluate_fd_campaign_rows,
    evaluate_fd_campaign_v2,
    read_fd_campaign_manifest,
    write_fd_campaign_manifest,
)
from cfd_sdf.openfoam_grid_transfer import (
    ExactCartesianOverlapTransfer,
    UniformCartesianCellGrid,
)
from cfd_sdf.transfer_diagnostic import diagnose_transfer, grid_from_json


def _grid(origin, spacing, shape) -> UniformCartesianCellGrid:
    return UniformCartesianCellGrid(origin=origin, spacing=spacing, cell_shape=shape)


def test_identity_transfer_is_exact():
    grid = _grid((0.0, 0.0, 0.0), (0.1, 0.1, 0.1), (4, 4, 4))
    diagnostic = diagnose_transfer(
        ExactCartesianOverlapTransfer.build(source_grid=grid, target_grid=grid)
    )
    assert diagnostic.verdict == "exact"
    assert diagnostic.consistency_error <= 1e-12
    assert diagnostic.random_state_conservation_error <= 1e-12
    assert diagnostic.euclidean_adjoint_identity_error <= 1e-12


def test_integer_ratio_transfer_is_algebraically_exact():
    source = _grid((0.0, 0.0, 0.0), (0.2, 0.2, 0.2), (2, 2, 2))
    target = _grid((0.0, 0.0, 0.0), (0.1, 0.1, 0.1), (4, 4, 4))
    diagnostic = diagnose_transfer(
        ExactCartesianOverlapTransfer.build(source_grid=source, target_grid=target)
    )
    assert diagnostic.verdict == "exact"
    assert diagnostic.integer_ratio is True
    assert diagnostic.random_state_conservation_error <= 1e-12
    # informational only: a volume-weighted pullback would not equal P.T here
    assert diagnostic.volume_weighted_pullback_difference_relative > 0.0


def test_p0_non_integer_pair_is_algebraically_exact():
    source = _grid((-1.0, -0.8, -0.6), (0.09375, 0.1, 0.075), (32, 16, 16))
    target = _grid((-1.0, -0.8, -0.6), (0.05, 0.05, 0.05), (60, 32, 24))
    diagnostic = diagnose_transfer(
        ExactCartesianOverlapTransfer.build(source_grid=source, target_grid=target)
    )
    assert diagnostic.integer_ratio is False
    assert diagnostic.verdict == "exact"
    assert diagnostic.consistency_error <= 1e-12
    assert diagnostic.random_state_conservation_error <= 1e-12
    assert diagnostic.euclidean_adjoint_identity_error <= 1e-12
    assert any("not integers" in note for note in diagnostic.notes)


def test_grid_from_json_accepts_topology_state_and_snapshot_shapes():
    topology_state = {
        "grid": {
            "origin": [0.0, 0.0, 0.0],
            "spacing": [0.1, 0.1, 0.1],
            "cell_shape": [4, 4, 4],
        }
    }
    snapshot = {
        "grid": {
            "lower_origin_m": [0.0, 0.0, 0.0],
            "spacing_m": [0.1, 0.1, 0.1],
            "cell_shape": [4, 4, 4],
        }
    }
    assert grid_from_json(topology_state).cell_count == 64
    assert grid_from_json(snapshot).cell_count == 64
    with pytest.raises(ValueError, match="cell_shape"):
        grid_from_json({"grid": {"origin": [0.0, 0.0, 0.0], "spacing": [0.1, 0.1, 0.1]}})


def _manifest_kwargs(**overrides) -> dict:
    kwargs = dict(
        campaign_id="fd_campaign_test",
        hypothesis="the mapped chain is exact on the reduced fixture",
        decision="close P6 if every registered row resolves within the profile",
        fixture={
            "candidate_binding": "work/p0_closed_loop/stage_t_candidate_binding.json",
            "problem_spec_sha256": "a" * 64,
            "grid_family": "canonical_60x32x24_to_source_32x16x16",
            "refinement_ratio": 2.0,
        },
        responses=["downforce"],
        epsilons=[3e-5, 1e-4, 3e-4, 1e-3],
        directions=[
            FdDirection("gradient_aligned", "gradient_aligned", None, "dJ/drho = -g"),
            FdDirection("random_seed_11", "random", 11, "dJ/drho = -g"),
            FdDirection("random_seed_2026", "random", 2026, "dJ/drho = -g"),
        ],
        uncertainty_rule="pre-registered relative/absolute error rule",
        gates={
            "convergence": "registered residual gates",
            "stationarity": "registered window",
            "mesh": "registered mesh profile",
            "geometry": "candidate binding hash",
            "required_pairs": "aligned plus random seeds at every epsilon",
            "resolvability": "5% relative error and sign agreement",
        },
        stop_conditions=("re-register on any gate failure",),
    )
    kwargs.update(overrides)
    return kwargs


def test_fd_manifest_round_trip_and_hash_binding(tmp_path: Path):
    manifest = build_fd_campaign_manifest(**_manifest_kwargs())
    assert manifest.profile_id == FD_QUALIFICATION_PROFILE_V1["profile_id"]
    assert manifest.random_seeds == (11, 2026)
    path = write_fd_campaign_manifest(manifest, tmp_path / "fd_manifest.json")
    read_manifest, digest = read_fd_campaign_manifest(path)
    assert json.dumps(read_manifest.to_dict(), sort_keys=True) == json.dumps(
        manifest.to_dict(), sort_keys=True
    )
    assert digest == manifest.manifest_hash()

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["manifest"]["hypothesis"] = "a hypothesis changed after the run"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(FdPreregistrationError, match="hash mismatch"):
        read_fd_campaign_manifest(path)


def test_fd_manifest_fails_closed_on_weakened_registration():
    with pytest.raises(FdPreregistrationError, match="epsilons"):
        build_fd_campaign_manifest(**_manifest_kwargs(epsilons=[1e-4, 1e-3]))

    with pytest.raises(FdPreregistrationError, match="random seeds"):
        build_fd_campaign_manifest(
            **_manifest_kwargs(
                directions=[
                    FdDirection("gradient_aligned", "gradient_aligned", None, "dJ/drho = -g"),
                ]
            )
        )

    with pytest.raises(FdPreregistrationError, match="gradient-aligned"):
        build_fd_campaign_manifest(
            **_manifest_kwargs(
                directions=[
                    FdDirection("random_seed_1", "random", 1, "dJ/drho = -g"),
                    FdDirection("random_seed_2", "random", 2, "dJ/drho = -g"),
                ]
            )
        )

    with pytest.raises(FdPreregistrationError, match="sign convention"):
        build_fd_campaign_manifest(
            **_manifest_kwargs(
                directions=[
                    FdDirection("gradient_aligned", "gradient_aligned", None, "  "),
                    FdDirection("random_seed_1", "random", 1, "dJ/drho = -g"),
                    FdDirection("random_seed_2", "random", 2, "dJ/drho = -g"),
                ]
            )
        )

    with pytest.raises(FdPreregistrationError, match=r"gates\.resolvability"):
        gates = dict(_manifest_kwargs()["gates"])
        gates.pop("resolvability")
        build_fd_campaign_manifest(**_manifest_kwargs(gates=gates))

    with pytest.raises(FdPreregistrationError, match="candidate_binding"):
        build_fd_campaign_manifest(
            **_manifest_kwargs(fixture={"problem_spec_sha256": "a" * 64, "grid_family": "x", "refinement_ratio": 2.0})
        )


def _fd_rows(fd_by_direction: dict[str, float], analytic: float = 1.0) -> list[dict]:
    rows = []
    for direction in ("gradient_aligned", "random_seed_11", "random_seed_2026"):
        for epsilon in (3e-5, 1e-4, 3e-4, 1e-3):
            rows.append(
                {
                    "direction": direction,
                    "epsilon": epsilon,
                    "fd": fd_by_direction.get(direction, analytic),
                    "analytic": analytic,
                    "converged": True,
                }
            )
    return rows


def _manifest_with_scale(scale: float) -> "object":
    kwargs = _manifest_kwargs()
    kwargs["fixture"] = dict(kwargs["fixture"], response_scale=scale)
    return build_fd_campaign_manifest(**kwargs)


def test_fd_row_evaluation_passes_inside_profile_and_fails_outside():
    manifest = _manifest_with_scale(1.0)
    ok = evaluate_fd_campaign_rows(manifest, _fd_rows({"gradient_aligned": 1.02, "random_seed_11": 0.98, "random_seed_2026": 1.0}))
    assert ok["passed"] is True

    biased = evaluate_fd_campaign_rows(
        manifest,
        _fd_rows({"gradient_aligned": 1.0, "random_seed_11": 0.9, "random_seed_2026": 1.0}),
    )
    assert biased["passed"] is False
    assert any(item["reason"] == "relative_error" for item in biased["failures"])

    flipped = evaluate_fd_campaign_rows(
        manifest,
        _fd_rows({"gradient_aligned": -1.0, "random_seed_11": 1.0, "random_seed_2026": 1.0}),
    )
    assert flipped["passed"] is False
    assert any(item["reason"] == "relative_error" for item in flipped["failures"])


def test_fd_row_evaluation_fails_closed_on_missing_or_unconverged_rows():
    manifest = _manifest_with_scale(1.0)
    rows = _fd_rows({})
    with pytest.raises(FdPreregistrationError, match="missing FD rows"):
        evaluate_fd_campaign_rows(manifest, rows[:-1])

    rows = _fd_rows({})
    rows[0] = dict(rows[0], converged=False)
    verdict = evaluate_fd_campaign_rows(manifest, rows)
    assert verdict["passed"] is False
    assert verdict["failures"][0]["reason"] == "unconverged"


def test_fd_row_evaluation_near_zero_uses_absolute_rule():
    manifest = _manifest_with_scale(1.0)
    rows = _fd_rows({}, analytic=1e-6)
    rows[0] = dict(rows[0], fd=5e-3, analytic=1e-6)
    verdict = evaluate_fd_campaign_rows(manifest, rows)
    assert any(check["status"] == "absolute_rule" for check in verdict["checks"])
    assert verdict["passed"] is False


def _v2_kwargs(**overrides) -> dict:
    kwargs = dict(
        campaign_id="fd_v2_test",
        hypothesis="primal-only perturbations bound the ratio",
        decision="Path A if every registered direction passes",
        fixture={
            "candidate_binding": "work/p0_closed_loop/stage_t_candidate_binding.json",
            "problem_spec_sha256": "a" * 64,
            "grid_family": "canonical_to_source",
            "refinement_ratio": 2.0,
            "response_scale": 0.78,
        },
        responses=["downforce"],
        epsilons=[3e-5, 1e-4, 3e-4, 1e-3],
        directions=[
            FdDirectionV2("gradient_aligned", "gradient_aligned", None, 0.008552, "dJ/drho = -g"),
            FdDirectionV2("random_seed_11", "random", 11, 0.00028, "dJ/drho = -g"),
            FdDirectionV2("random_seed_2026", "random", 2026, 0.000298, "dJ/drho = -g"),
        ],
        base_gates={gate: True for gate in FD_V2_REQUIRED_BASE_GATES},
        perturbation_gate_template={gate: True for gate in FD_V2_REQUIRED_PERTURBATION_GATES},
        noise_floor=1e-4,
        uncertainty_rule="registered",
        stop_conditions=("re-register on gate failure",),
    )
    kwargs.update(overrides)
    return kwargs


_V2_ANALYTIC = {
    "gradient_aligned": 0.008552,
    "random_seed_11": 0.00028,
    "random_seed_2026": 0.000298,
}


def _v2_rows(ratios: dict[str, float], *, converged: bool = True) -> list[dict]:
    rows = []
    for direction in ("gradient_aligned", "random_seed_11", "random_seed_2026"):
        for epsilon in (3e-5, 1e-4, 3e-4, 1e-3):
            rows.append(
                {
                    "direction": direction,
                    "epsilon": epsilon,
                    "fd": ratios[direction] * _V2_ANALYTIC[direction],
                    "converged": converged,
                    "gates": {gate: True for gate in FD_V2_REQUIRED_PERTURBATION_GATES},
                }
            )
    return rows


def test_v2_manifest_separates_base_and_perturbation_gates():
    manifest = build_fd_campaign_manifest_v2(**_v2_kwargs())
    assert manifest.base_gates["adjoint_residual"] is True
    assert "adjoint_residual" not in manifest.perturbation_gate_template
    with pytest.raises(FdPreregistrationError, match="adjoint gate"):
        build_fd_campaign_manifest_v2(
            **_v2_kwargs(
                perturbation_gate_template={
                    **{gate: True for gate in FD_V2_REQUIRED_PERTURBATION_GATES},
                    "adjoint_residual": True,
                }
            )
        )
    with pytest.raises(FdPreregistrationError, match="non-zero analytic reference"):
        build_fd_campaign_manifest_v2(
            **_v2_kwargs(
                directions=[
                    FdDirectionV2("gradient_aligned", "gradient_aligned", None, 0.0, "dJ/drho = -g"),
                    FdDirectionV2("random_seed_11", "random", 11, 0.00028, "dJ/drho = -g"),
                    FdDirectionV2("random_seed_2026", "random", 2026, 0.000298, "dJ/drho = -g"),
                ]
            )
        )


def test_v2_evaluation_enforces_noise_floor_and_plateau():
    manifest = build_fd_campaign_manifest_v2(**_v2_kwargs())
    base_analytic = dict(_V2_ANALYTIC)
    # all ratios inside 5% -> pass
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=base_analytic,
        rows=_v2_rows({"gradient_aligned": 1.0, "random_seed_11": 1.02, "random_seed_2026": 0.99}),
    )
    assert verdict["passed"] is True
    assert verdict["below_noise_floor_directions"] == []

    # the aligned ratio is 1.2178 (measured) -> relative failure
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=base_analytic,
        rows=_v2_rows({"gradient_aligned": 1.2178, "random_seed_11": 1.0, "random_seed_2026": 1.0}),
    )
    assert verdict["passed"] is False
    assert any(item["reason"] == "relative_error" for item in verdict["failures"])

    # a non-aligned direction inside the noise floor is judged by the registered
    # absolute rule, never silently skipped
    near_zero = dict(base_analytic, random_seed_11=1e-6)
    near_zero_rows = _v2_rows(
        {"gradient_aligned": 1.0, "random_seed_11": 1.0, "random_seed_2026": 1.0}
    )
    for row in near_zero_rows:
        if row["direction"] == "random_seed_11":
            row["fd"] = 2e-5
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=near_zero,
        rows=near_zero_rows,
    )
    assert "random_seed_11" in verdict["below_noise_floor_directions"]
    assert verdict["passed"] is True
    assert any(check.get("status") == "absolute_rule" for check in verdict["checks"])

    # the same direction with an absolute error above the registered floor fails
    rows = _v2_rows({"gradient_aligned": 1.0, "random_seed_11": 1.0, "random_seed_2026": 1.0})
    for row in rows:
        if row["direction"] == "random_seed_11":
            row["fd"] = 1e-2
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=near_zero,
        rows=rows,
    )
    assert verdict["passed"] is False
    assert any(item["reason"] == "absolute_error" for item in verdict["failures"])

    # a gradient-aligned direction below the noise floor is unresolved, fail-closed
    near_zero_aligned = dict(base_analytic, gradient_aligned=1e-6)
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=near_zero_aligned,
        rows=_v2_rows({"gradient_aligned": 1.0, "random_seed_11": 1.0, "random_seed_2026": 1.0}),
    )
    assert verdict["passed"] is False
    assert any(
        item["reason"] == "near_zero_gradient_aligned_unresolved"
        for item in verdict["failures"]
    )

    # a non-plateau direction fails even if each row is close
    rows = _v2_rows({"gradient_aligned": 1.0, "random_seed_11": 1.0, "random_seed_2026": 1.0})
    for row in rows:
        if row["direction"] == "random_seed_2026":
            row["fd"] = (0.9 if row["epsilon"] < 1e-3 else 1.0) * _V2_ANALYTIC["random_seed_2026"]
    verdict = evaluate_fd_campaign_v2(
        manifest,
        base_gates=manifest.base_gates,
        base_analytic=base_analytic,
        rows=rows,
    )
    assert any(item["reason"] == "epsilon_not_plateau" for item in verdict["failures"])
