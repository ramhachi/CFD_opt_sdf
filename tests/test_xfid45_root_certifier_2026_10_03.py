"""Synthetic and fixed-regression tests for XFID45-CERT-01."""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import run_xfid45_root_certifier_replay_2026_10_03 as replay
from scripts.verify_xfid45_root_certifier_2026_10_03 import (
    enumerate_ray_roots as sturm_ray_roots,
    nearest_root as sturm_nearest,
    polynomial_roots as sturm_roots,
)
from scripts.xfid45_root_certifier_2026_10_03 import (
    enumerate_ray_roots,
    nearest_root,
    polynomial_roots,
    position_tolerance,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def test_replay_runner_reads_the_registered_target_inventory_schema():
    registration_path = (
        ROOT / "docs/evidence/xfid45_root_certifier_2026_10_03/preregistration.json"
    )
    prereg = json.loads(registration_path.read_text())
    inventory = replay._registered_inventory(prereg)
    files = inventory["files"]
    loaded, parent_hash, amendment_hash = replay._load_registration()

    assert files["file_count"] == len(files["files"]) == 201
    assert set(files["original_fields"]) == set(replay.CASES)
    assert len(files["saved_surface_artifacts"]) == 40
    assert parent_hash == replay.sha256(registration_path)
    assert amendment_hash == replay.sha256(replay.PREREGISTRATION_AMENDMENT)
    for source in (replay.AMENDABLE_SOURCE, replay.AMENDABLE_TEST):
        assert loaded["effective_source_sha256"][source] == replay.sha256(ROOT / source)


def test_replay_agreement_checks_all_root_positions_not_only_the_nearest():
    def root(t):
        return SimpleNamespace(t_m=t, bracket_m=(t, t), kind="crossing")

    primary = SimpleNamespace(
        status="COMPLETE", zero_intervals=(), roots=(root(-0.02), root(0.001))
    )
    independent = SimpleNamespace(
        status="COMPLETE", zero_intervals=(), roots=(root(-0.019), root(0.001))
    )

    comparison = replay._root_agreement(primary, independent, 0.025, 0.05)

    assert comparison["root_position_mismatch"] == 1
    assert comparison["nearest_position_mismatch"] == 0
    assert comparison["nearest_identity_mismatch"] == 0


def _coeff(roots: tuple[float, ...], scale: float = 1.0) -> tuple[float, ...]:
    return tuple(
        float(v) for v in np.polynomial.polynomial.polyfromroots(roots) * scale
    ) + (0.0,) * (4 - len(roots) - 1)


def _assert_agree(
    coeff: tuple[float, ...], expected: tuple[float, ...], kind: str = "crossing"
) -> None:
    primary = polynomial_roots(coeff, ta=-0.025, tb=0.025, h=0.025)
    independent = sturm_roots(coeff, ta=-0.025, tb=0.025, h=0.025)
    assert primary.status == independent.status == "COMPLETE"
    expected_t = tuple(-0.025 + 0.05 * root for root in expected)
    for result in (primary, independent):
        assert len(result.roots) == len(expected)
        assert np.allclose(
            [r.t_m for r in result.roots],
            expected_t,
            atol=position_tolerance(0.025, 0.05),
            rtol=0,
        )
    assert tuple(r.kind for r in primary.roots) == tuple(
        r.kind for r in independent.roots
    )
    assert all(root.kind == kind for root in primary.roots if kind != "mixed")


@pytest.mark.parametrize(
    ("coeff", "expected", "status"),
    [
        ((2.0, 0.0, 0.0, 0.0), (), "COMPLETE"),
        ((0.0, 0.0, 0.0, 0.0), (), "ZERO_INTERVAL"),
        ((-0.0, 1.0, 0.0, 0.0), (0.0,), "COMPLETE"),
        ((-0.4, 1.0, 0.0, 0.0), (0.4,), "COMPLETE"),
        ((0.16, -1.0, 1.0, 0.0), (0.2, 0.8), "COMPLETE"),
        ((0.09375, -0.6875, 1.5, -1.0), (0.25, 0.5, 0.75), "COMPLETE"),
        ((-0.4, 1.0, 1e-18, 1e-20), (0.4,), "COMPLETE"),
    ],
)
def test_degree_and_generic_cubic_cases(coeff, expected, status):
    primary = polynomial_roots(coeff, ta=0.0, tb=1.0, h=0.025)
    independent = sturm_roots(coeff, ta=0.0, tb=1.0, h=0.025)
    assert primary.status == independent.status == status
    if status == "ZERO_INTERVAL":
        assert primary.zero_intervals == independent.zero_intervals == ((0.0, 1.0),)
        return
    assert len(primary.roots) == len(independent.roots) == len(expected)
    tolerance = position_tolerance(0.025, 1.0)
    assert np.allclose([r.t_m for r in primary.roots], expected, atol=tolerance, rtol=0)
    assert np.allclose(
        [r.t_m for r in independent.roots], expected, atol=tolerance, rtol=0
    )


def test_simple_root_multiplicity_endpoints_and_tangent_roots():
    _assert_agree(_coeff((0.4, -2.0, 3.0)), (0.4,))
    _assert_agree(_coeff((0.2, 0.8, 2.0)), (0.2, 0.8))
    _assert_agree(_coeff((0.2, 0.5, 0.8)), (0.2, 0.5, 0.8))
    _assert_agree(_coeff((0.25, 0.25, 0.75)), (0.25, 0.75), kind="mixed")
    _assert_agree(_coeff((0.5, 0.5, 0.5)), (0.5,), kind="mixed")

    for endpoint in (0.0, 1.0):
        coeff = _coeff((endpoint, 0.25, 0.75))
        primary = polynomial_roots(coeff, ta=0.0, tb=1.0, h=0.025)
        independent = sturm_roots(coeff, ta=0.0, tb=1.0, h=0.025)
        assert primary.status == independent.status == "COMPLETE"
        assert np.allclose(
            [r.t_m for r in primary.roots], [r.t_m for r in independent.roots]
        )


def test_repeated_rational_root_not_representable_as_binary_float():
    # (3x - 1)^2 (4x - 3) has an exact repeated root at 1/3. The
    # coefficients are exactly representable integers, while the root is not
    # exactly representable in binary floating point.
    coefficients = (-3.0, 22.0, -51.0, 36.0)
    primary = polynomial_roots(coefficients, ta=0.0, tb=1.0, h=0.025)
    independent = sturm_roots(coefficients, ta=0.0, tb=1.0, h=0.025)
    assert primary.status == independent.status == "COMPLETE"
    assert len(primary.roots) == len(independent.roots) == 2
    assert primary.roots[0].kind == independent.roots[0].kind == "tangent"
    assert primary.roots[0].t_m == pytest.approx(1.0 / 3.0, abs=1e-12)
    assert independent.roots[0].t_m == pytest.approx(1.0 / 3.0, abs=1e-12)
    assert primary.roots[1].t_m == pytest.approx(0.75, abs=1e-12)
    assert independent.roots[1].t_m == pytest.approx(0.75, abs=1e-12)


def test_near_endpoint_close_roots_and_coefficient_dynamic_range():
    near = 2.0**-32
    _assert_agree(_coeff((near, 0.6, 1.2)), (near, 0.6))
    close = (0.375, 0.375 + 2.0**-20, 0.75)
    _assert_agree(_coeff(close), close)
    _assert_agree(_coeff((0.125, 0.5, 0.875), 1e-200), (0.125, 0.5, 0.875))
    _assert_agree(_coeff((0.125, 0.5, 0.875), 1e100), (0.125, 0.5, 0.875))
    for scale in (float(np.finfo(np.float32).eps), float(np.finfo(np.float64).eps)):
        _assert_agree((-0.25 * scale, scale, 0.0, 0.0), (0.25,))


def test_distinct_roots_inside_position_tolerance_remain_unresolved():
    separation = 2.0**-44
    # x * (x - separation) * (x - 0.75): both close roots are exact zeros
    # of a polynomial with binary64 coefficients, but cannot be distinguished
    # at the registered root-position tolerance.
    coefficients = (0.0, 0.75 * separation, -(0.75 + separation), 1.0)
    primary = polynomial_roots(coefficients, ta=0.0, tb=1.0, h=0.025)
    independent = sturm_roots(coefficients, ta=0.0, tb=1.0, h=0.025)
    assert primary.status == independent.status == "UNRESOLVED"
    assert "distinct_roots_not_separable_at_registered_precision" in primary.reasons
    assert "distinct_roots_not_separable_at_registered_precision" in independent.reasons
    assert len(primary.roots) == len(independent.roots) == 3
    chosen, primary_status = nearest_root(primary, 0.025, 1.0)
    independent_chosen, independent_status = sturm_nearest(independent, 0.025, 1.0)
    assert chosen is independent_chosen is None
    assert primary_status == independent_status == "UNRESOLVED_ROOT_SET"


def test_piecewise_trilinear_boundary_roots_and_near_zero_nodes():
    x = np.arange(4, dtype=np.float64)[:, None, None]
    phi = np.broadcast_to(x - 1.0, (4, 2, 2)).copy()
    point = np.array((0.3, 0.5, 0.5))
    direction = np.array((1.0, 0.0, 0.0))
    primary = enumerate_ray_roots(phi, (0.0, 0.0, 0.0), 1.0, point, direction, 2.0)
    independent = sturm_ray_roots(phi, (0.0, 0.0, 0.0), 1.0, point, direction, 2.0)
    assert primary.status == independent.status == "COMPLETE"
    assert len(primary.roots) == len(independent.roots) == 1
    assert primary.roots[0].t_m == pytest.approx(0.7, abs=1e-12)
    assert independent.roots[0].t_m == pytest.approx(0.7, abs=1e-12)

    values = np.array((0.0, 1e-16, -1e-6, 1e-3), dtype=np.float64)[:, None, None]
    near_zero_phi = np.broadcast_to(values, (4, 2, 2)).copy()
    q = enumerate_ray_roots(
        near_zero_phi, (0.0, 0.0, 0.0), 1.0, (0.25, 0.5, 0.5), direction, 2.0
    )
    q_sturm = sturm_ray_roots(
        near_zero_phi, (0.0, 0.0, 0.0), 1.0, (0.25, 0.5, 0.5), direction, 2.0
    )
    # The exact structural zero is retained. The first source-grid boundary
    # has no two-sided field neighborhood, so correspondence identity is
    # conservatively unresolved in both independent implementations.
    assert q.status == q_sturm.status == "UNRESOLVED"
    assert len(q.roots) == len(q_sturm.roots)
    assert np.allclose(
        [r.t_m for r in q.roots], [r.t_m for r in q_sturm.roots], atol=1e-12
    )
    assert any(abs(r.t_m + 0.25) <= 1e-14 for r in q.roots)


def test_all_roots_on_a_ray_through_a_trilinear_cell():
    axes = np.indices((2, 2, 2), dtype=np.float64)
    phi = (axes[0] - 0.25) * (axes[1] - 0.5) * (axes[2] - 0.75)
    point = np.zeros(3)
    direction = np.ones(3) / math.sqrt(3.0)
    primary = enumerate_ray_roots(
        phi, (0.0, 0.0, 0.0), 1.0, point, direction, math.sqrt(3.0)
    )
    independent = sturm_ray_roots(
        phi, (0.0, 0.0, 0.0), 1.0, point, direction, math.sqrt(3.0)
    )
    expected = np.array((0.25, 0.5, 0.75)) * math.sqrt(3.0)
    tolerance = position_tolerance(1.0, 2 * math.sqrt(3.0), *expected)
    assert primary.status == independent.status == "COMPLETE"
    assert np.allclose([r.t_m for r in primary.roots], expected, atol=tolerance, rtol=0)
    assert np.allclose(
        [r.t_m for r in independent.roots], expected, atol=tolerance, rtol=0
    )


def test_seeded_random_cubic_property_suite():
    rng = np.random.default_rng(451003)
    count = 512
    for _ in range(count):
        roots = np.sort(rng.uniform(-0.5, 1.5, size=3))
        scale = float(10.0 ** rng.uniform(-12.0, 12.0))
        coeff = _coeff(tuple(float(x) for x in roots), scale)
        primary = polynomial_roots(coeff, ta=0.0, tb=1.0, h=0.025)
        independent = sturm_roots(coeff, ta=0.0, tb=1.0, h=0.025)
        expected = roots[(roots >= 0.0) & (roots <= 1.0)]
        assert primary.status == independent.status == "COMPLETE"
        assert len(primary.roots) == len(independent.roots) == len(expected)
        assert np.allclose([r.t_m for r in primary.roots], expected, atol=1e-11, rtol=0)
        assert np.allclose(
            [r.t_m for r in independent.roots], expected, atol=1e-11, rtol=0
        )


def test_round3_sample_691_near_root_regression():
    case = "D0_interface_offset_minus"
    with np.load(EVIDENCE / "surfaces/r4" / case / "normal_correspondence.npz") as z:
        sample = z["double_samples"][691]
    registration = json.loads((EVIDENCE / "preregistration.json").read_text())
    source = ROOT / registration["inputs"][case]["path"]
    with np.load(source) as z:
        phi = z["phi"]
        meta = json.loads(str(z["metadata"]))
    h = float(meta["spacing_m"])
    origin = np.asarray(meta["origin_m"], dtype=np.float64)
    point, direction = sample[:3], sample[3:6]
    parent = enumerate_ray_roots(phi, origin, h, point, direction, 2.0 * h)
    independent = sturm_ray_roots(phi, origin, h, point, direction, 2.0 * h)
    primary_near, primary_status = nearest_root(parent, h, 2.0 * h)
    independent_near, independent_status = sturm_nearest(independent, h, 2.0 * h)
    tol = position_tolerance(h, 4.0 * h, *[r.t_m for r in parent.roots])
    assert parent.status == independent.status == "COMPLETE"
    assert len(parent.roots) == len(independent.roots) == 2
    assert primary_status == independent_status == "UNIQUE_NEAREST_ROOT"
    assert primary_near is not None and independent_near is not None
    assert primary_near.t_m == pytest.approx(0.004166670751981498, abs=tol)
    assert independent_near.t_m == pytest.approx(0.004166670751981498, abs=tol)
    assert np.allclose(
        [r.t_m for r in parent.roots],
        [r.t_m for r in independent.roots],
        atol=tol,
        rtol=0,
    )
    mesh_t = float(sample[7])
    baseline_source = ROOT / registration["inputs"]["baseline"]["path"]
    with np.load(baseline_source) as z:
        baseline_phi = z["phi"]
        baseline_meta = json.loads(str(z["metadata"]))
    baseline_roots = enumerate_ray_roots(
        baseline_phi, origin, h, point, direction, 2.0 * h
    )
    baseline_near, baseline_status = nearest_root(baseline_roots, h, 2.0 * h)
    assert baseline_status == "UNIQUE_NEAREST_ROOT" and baseline_near is not None
    assert h == pytest.approx(float(baseline_meta["spacing_m"]))
    delta = mesh_t - (primary_near.t_m - baseline_near.t_m)
    assert delta == pytest.approx(3.3780709279e-8, abs=2e-12)
    assert delta * 1e9 == pytest.approx(33.780709279, abs=0.01)


def test_nearest_root_refuses_equivalent_and_tangent_choices():
    tied = polynomial_roots(_coeff((0.25, 0.75, 1.5)), ta=-1.0, tb=1.0, h=0.025)
    chosen, status = nearest_root(tied, 0.025, 1.0)
    assert chosen is None and status == "AMBIGUOUS_EQUIDISTANT_ROOTS"
    tangent = polynomial_roots(_coeff((0.5, 0.5, 1.5)), ta=0.0, tb=1.0, h=0.025)
    chosen, status = nearest_root(tangent, 0.025, 1.0)
    assert chosen is None and status == "AMBIGUOUS_TANGENCY"
