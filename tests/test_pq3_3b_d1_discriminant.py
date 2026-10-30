"""Tests for the D1 bounded discriminant construction and verdicts (no OpenFOAM)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from scripts.pq3_3b_d1_discriminant_2026_09 import (  # noqa: E402
    build_directions,
    candidate_for,
    direction_verdict,
)

SHAPE = (6, 5, 4)
MANIFEST = ROOT / "docs/evidence/pq3_3b_d1_manifest_2026_09.json"
D0 = ROOT / "docs/evidence/pq3_3b_stopped_state_diagnosis_2026_09.json"
MANIFEST_V5 = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v5_2026_09.json"


def _arena():
    act = np.zeros(SHAPE, dtype=bool)
    act[2:4, 1:4, 1:3] = True
    active = np.asarray(act).ravel(order="F")
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(SHAPE, 0.05, active, radius_m=0.05),
        projection=TanhProjection(8.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    rho = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    ids = np.nonzero(active)[0]
    values = np.linspace(0.02, 0.4, ids.size)
    rho[ids] = values
    rho[ids[0]] = 0.0
    rho[ids[1]] = 1.0
    grad_j = np.zeros_like(rho)
    grad_j[ids] = np.where(np.arange(ids.size) % 2 == 0, -1.0, 1.0)
    indicator = np.zeros_like(rho)
    indicator[active] = 1.0 / float(np.count_nonzero(active))
    grad_v = transform.pullback_from_projected(rho, indicator)
    return transform, rho, grad_j, grad_v, active


def test_registered_manifest_pins_current_artifacts():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    observed = hashlib.sha256(D0.read_bytes()).hexdigest()
    assert manifest["diagnosis"]["sha256"] == observed
    observed_v5 = hashlib.sha256(MANIFEST_V5.read_bytes()).hexdigest()
    assert manifest["source_registration"]["manifest_v5"]["sha256"] == observed_v5
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    assert sidecar == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def test_build_directions_order_matches_the_registration():
    transform, rho, grad_j, grad_v, active = _arena()
    directions, frozen = build_directions(
        transform=transform,
        rho=rho,
        grad_j=grad_j,
        grad_v=grad_v,
        active=active,
        move_limit=0.03,
        target=float(np.asarray(transform.forward(rho).rho_projected)[active].mean()),
        volume_tolerance=1e-4,
    )
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in directions] == [
        spec["id"] for spec in manifest["directions"]
    ]
    assert frozen.sum() >= 2
    for entry in directions:
        assert entry["delta"].shape == rho.shape
        assert np.all(np.isfinite(entry["delta"]))


def test_d3_is_volume_orthogonal_on_the_movable_subspace():
    transform, rho, grad_j, grad_v, active = _arena()
    directions, frozen = build_directions(
        transform=transform,
        rho=rho,
        grad_j=grad_j,
        grad_v=grad_v,
        active=active,
        move_limit=0.03,
        target=float(np.asarray(transform.forward(rho).rho_projected)[active].mean()),
        volume_tolerance=1e-4,
    )
    d3 = next(entry for entry in directions if entry["id"] == "d3_volume_exchange_orthogonal")
    assert abs(float(np.dot(grad_v, d3["delta"]))) <= 1e-12
    movable = active & ~frozen
    assert float(np.max(np.abs(d3["delta"][~movable]))) == 0.0
    assert float(np.max(np.abs(d3["delta"][movable]))) == pytest.approx(1.0)


def test_d4_is_one_sided_and_only_moves_inward_box_faces():
    transform, rho, grad_j, grad_v, active = _arena()
    directions, frozen = build_directions(
        transform=transform,
        rho=rho,
        grad_j=grad_j,
        grad_v=grad_v,
        active=active,
        move_limit=0.03,
        target=float(np.asarray(transform.forward(rho).rho_projected)[active].mean()),
        volume_tolerance=1e-4,
    )
    d4 = next(entry for entry in directions if entry["id"] == "d4_inward_from_box_faces")
    delta = d4["delta"]
    assert d4["one_sided"] is True
    assert float(np.max(np.abs(delta[~frozen]))) == 0.0
    assert d4["apply_freeze"] is False


def test_candidate_for_respects_box_and_freeze_policy():
    _, rho, _, _, active = _arena()
    frozen = active & ((rho == 0.0) | (rho == 1.0))
    frozen_direction = {
        "delta": np.ones_like(rho),
        "scale": 1.0,
        "apply_freeze": True,
        "one_sided": False,
    }
    candidate, box_low, box_high = candidate_for(
        rho=rho,
        direction=frozen_direction,
        amplitude=1.0,
        move_limit=0.03,
        active=active,
        frozen=frozen,
    )
    assert float(np.max(np.abs(candidate[frozen] - rho[frozen]))) == 0.0
    assert float(np.max(np.maximum(candidate - box_high, box_low - candidate))) <= 1e-15

    one_sided_direction = {
        "delta": np.ones_like(rho),
        "scale": 0.03,
        "apply_freeze": False,
        "one_sided": True,
    }
    candidate, _, _ = candidate_for(
        rho=rho,
        direction=one_sided_direction,
        amplitude=1.0,
        move_limit=0.03,
        active=active,
        frozen=frozen,
    )
    at_zero = frozen & (rho == 0.0)
    if bool(at_zero.any()):
        assert float(np.min(candidate[at_zero])) > 0.0


def test_direction_verdict_rules():
    good = {"constraints_ok": True, "detectable_improvement": True}
    bad = {"constraints_ok": True, "detectable_improvement": False}
    infeasible = {"constraints_ok": False, "detectable_improvement": True}
    assert direction_verdict([good, good]) == "detectable_improvement"
    assert direction_verdict([bad, bad]) == "below_threshold"
    assert direction_verdict([good, bad]) == "amplitude_inconsistent"
    assert direction_verdict([good, infeasible]) == "infeasible"
