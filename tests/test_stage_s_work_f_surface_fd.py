"""Contract tests for the Stage S Work F surface-FD campaign (no OpenFOAM runs)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fd_preregistration import (  # noqa: E402
    FdPreregistrationError,
    read_fd_campaign_manifest,
)
from cfd_sdf.stage_s_surface_fd import (  # noqa: E402
    DEFAULT_EPSILON_RATIOS,
    DEFAULT_RANDOM_SEEDS,
    build_epsilon_ladder,
    build_work_f_fd_manifests,
    default_fixed_regions,
    default_surface_basis,
    evaluate_work_f_fd,
    worst_case_offset_mesh,
)

CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_preflight_2026_09.json"
BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"


def _baseline_mesh() -> trimesh.Trimesh:
    baseline = json.loads(BASELINE.read_text())
    stl = ROOT / baseline["handoff"]["artifacts"]["surface_stl"]["path"]
    return trimesh.load_mesh(stl)


def _manifests() -> dict:
    baseline = json.loads(BASELINE.read_text())
    mesh = _baseline_mesh()
    ladder = build_epsilon_ladder(0.05)
    return build_work_f_fd_manifests(
        baseline=baseline,
        problem_spec_sha256="a" * 64,
        level_name="V1",
        voxel_size_m=0.05,
        response_scales={"drag": 2.5234447, "downforce": 1.6908433},
        basis=default_surface_basis(np.asarray(mesh.bounds, dtype=np.float64)),
        fixed_regions=default_fixed_regions(max(ladder.epsilons_m)),
        ladder=ladder,
    )


def _rows(manifest, analytic: float, fd: float) -> list[dict]:
    return [
        {
            "direction": direction.name,
            "epsilon": float(epsilon),
            "analytic": analytic,
            "fd": fd,
            "converged": True,
        }
        for direction in manifest.directions
        for epsilon in manifest.epsilons
    ]


def test_epsilon_ladder_is_dimensionless_and_requires_four_levels():
    ladder = build_epsilon_ladder(0.05)
    assert ladder.ratios == DEFAULT_EPSILON_RATIOS
    assert ladder.epsilons_m == pytest.approx((1e-4, 2.5e-4, 5e-4, 1e-3))
    with pytest.raises(ValueError, match="at least four"):
        build_epsilon_ladder(0.05, (0.01, 0.02, 0.05))
    with pytest.raises(ValueError, match="positive"):
        build_epsilon_ladder(0.05, (0.0, 0.005, 0.01, 0.02))


def test_response_manifests_share_the_catalog_and_identity_contract():
    manifests = _manifests()
    assert set(manifests) == {"drag", "downforce"}
    drag, downforce = manifests["drag"], manifests["downforce"]
    assert drag.epsilons == downforce.epsilons
    assert [d.name for d in drag.directions] == [d.name for d in downforce.directions]
    assert {d.name for d in drag.directions} == {
        "downforce_gradient_aligned",
        "drag_gradient_aligned",
        "random_seed_11",
        "random_seed_2026",
    }
    assert drag.fixture["response_identity"]["coefficient"] == "Cd"
    assert drag.fixture["response_identity"]["bound_kind"] == "relative"
    assert downforce.fixture["response_identity"]["coefficient"] == "downforce"
    assert downforce.fixture["response_identity"]["bound_kind"] == "absolute"
    assert downforce.fixture["response_identity"]["objective_sign"] == -1.0
    assert "liftDir" in downforce.fixture["response_identity"]["sign_convention"]
    assert drag.fixture["surface_basis"]["kind"] == "volumetricBSplines"
    assert drag.fixture["fixed_regions"]["free_patch"] == "design_candidate"
    assert drag.fixture["epsilon_ladder"]["epsilons_m"] == pytest.approx((1e-4, 2.5e-4, 5e-4, 1e-3))
    assert drag.fixture["near_zero_relative"] > 0.0
    assert drag.fixture["near_zero_absolute_error"] > 0.0


def test_manifest_validation_rejects_missing_roles_and_seeds():
    from cfd_sdf.fd_preregistration import build_fd_campaign_manifest

    template = _manifests()["drag"]
    kwargs = dict(
        campaign_id="bad",
        hypothesis="h",
        decision="d",
        fixture=dict(template.fixture),
        responses=["drag"],
        epsilons=template.epsilons,
        uncertainty_rule="r",
        gates=dict(template.gates),
        stop_conditions=("s",),
    )
    with pytest.raises(FdPreregistrationError, match="gradient-aligned"):
        build_fd_campaign_manifest(
            directions=[d for d in template.directions if d.role != "gradient_aligned"],
            **kwargs,
        )
    with pytest.raises(FdPreregistrationError, match="random seeds"):
        build_fd_campaign_manifest(
            directions=[d for d in template.directions if d.seed != 11],
            **kwargs,
        )


def test_worst_case_offset_mesh_keeps_a_box_valid():
    box = trimesh.creation.box(extents=(0.2, 0.2, 0.2))
    baseline_volume = float(box.volume)
    for sign in (+1.0, -1.0):
        offset = worst_case_offset_mesh(box, sign * 1e-4)
        assert offset.is_watertight
        assert offset.is_winding_consistent
        assert abs(offset.volume - baseline_volume) / baseline_volume < 0.01


def test_evaluation_requires_both_responses_and_resolvable_aligned_directions():
    manifests = _manifests()
    rows = {
        response: _rows(manifest, analytic=0.01, fd=0.01)
        for response, manifest in manifests.items()
    }
    verdict = evaluate_work_f_fd(manifests, rows=rows)
    assert verdict["both_pass"] is True
    assert verdict["shape_update_allowed"] is False

    # a drag failure keeps the combined gate false
    rows["drag"] = _rows(manifests["drag"], analytic=0.01, fd=0.013)
    verdict = evaluate_work_f_fd(manifests, rows=rows)
    assert verdict["both_pass"] is False
    assert verdict["responses"]["drag"]["passed"] is False
    assert verdict["responses"]["downforce"]["passed"] is True

    # a below-noise primary gradient-aligned direction is unresolved, fail-closed
    rows = {
        response: _rows(manifest, analytic=0.01, fd=0.01)
        for response, manifest in manifests.items()
    }
    rows["downforce"] = _rows(manifests["downforce"], analytic=0.01, fd=0.01)
    for row in rows["downforce"]:
        if row["direction"] == "downforce_gradient_aligned":
            row["analytic"] = 1e-9
            row["fd"] = 1e-9
    verdict = evaluate_work_f_fd(manifests, rows=rows)
    assert verdict["both_pass"] is False
    assert verdict["responses"]["downforce"]["primary_gradient_aligned_resolved"] is False
    assert any(
        failure["reason"] == "near_zero_gradient_aligned_unresolved"
        for failure in verdict["responses"]["downforce"]["failures"]
    )


def test_registered_catalog_and_preflight_reverify():
    catalog = json.loads(CATALOG.read_text())
    assert catalog["kind"] == "stage_s_work_f_surface_fd_catalog"
    for response, record in catalog["manifests"].items():
        path = ROOT / record["path"]
        assert ca.sha256_file(path) == record["sha256"]
        manifest, manifest_hash = read_fd_campaign_manifest(path)
        assert manifest_hash == record["manifest_hash"]
        assert list(manifest.responses) == [response]
    assert catalog["baseline"]["sha256"] == ca.sha256_file(ROOT / catalog["baseline"]["path"])
    preflight = json.loads(PREFLIGHT.read_text())
    assert preflight["catalog"]["sha256"] == ca.sha256_file(CATALOG)
    assert preflight["summary"]["preflight_pass"] is True
    assert preflight["summary"]["campaign_allowed"] is True
    assert preflight["summary"]["solver_started"] is False
    assert preflight["worst_case_checks"]["all_pass"] is True
