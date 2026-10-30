"""PQ3.3b preflight v2: reachability and mask-contract evidence through the registered backend.

Differences from v1 (docs/evidence/pq3_3b_preflight_2026_09.json, kept as
diagnostic evidence):

- every kappa evaluation goes through the real ``ProjectedVolumeTargetBackend``
  (Work C.1 contract path), not an ad-hoc phi replica;
- non-active / forbidden / fixed-solid drift is always measured and
  ``masks_invariant`` is always a verdict (no ``None``);
- the volume basis is ``mean(rho_projection[active])`` compared against the
  projected V_max; the raw design mean is never used as infeasibility evidence;
- an intermediate growth level (b=4, q=15, move_limit=0.05) is registered ahead
  of the b=8 and b=16 levels with a projected-basis target of 0.018.

This script does NOT start the OpenFOAM campaign: it runs one parent
primal+adjoint per level to freeze the gradient hash, then records the
reachability and mask-contract measurements.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.preflight_v2 import measure_level  # noqa: E402

WORK = ROOT / "work" / "df2_fd_refresh"
CHECKPOINT = ROOT / "work" / "pq3_3_volume_target" / "checkpoint_chunk02.json"
OUT = ROOT / "work" / "pq3_3b_preflight_v2"
TEMPLATE_SOURCE = ROOT / "work" / "pq0_2_smoke" / "template_trial"
EVIDENCE = ROOT / "docs" / "evidence" / "pq3_3b_preflight_v2_2026_09.json"
V1_EVIDENCE = ROOT / "docs" / "evidence" / "pq3_3b_preflight_2026_09.json"
SHAPE = (60, 32, 24)
SPACING = 0.05
FILTER_RADIUS_M = 0.15
V_MAX_PROJECTED = 0.07632566813424899
REGISTERED_TARGET = 0.018
V_TOLERANCE = 1e-4
LEVELS = (
    {"name": "level_0_growth_b4_q15", "b": 4.0, "q": 15.0, "move_limit": 0.05},
    {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03},
    {"name": "level_2_b16_q100", "b": 16.0, "q": 100.0, "move_limit": 0.01},
)


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values, dtype=np.float64).tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if EVIDENCE.exists() or OUT.exists():
        raise SystemExit(f"preflight v2 artifacts already exist: {OUT} / {EVIDENCE}")
    OUT.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE_SOURCE.exists():
        raise SystemExit(f"template source missing: {TEMPLATE_SOURCE}")
    shutil.copytree(TEMPLATE_SOURCE, OUT / "template_trial")

    cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    rho0 = np.asarray(cp["rho"], dtype=np.float64)
    source = load_fixed_grid_density_state(WORK / "topology_state.json")
    joint = (
        (np.asarray(source.arrays["active_design_mask"]) > 0)
        & (np.asarray(source.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(source.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(source.arrays["fixed_solid_mask"]) > 0)
    )
    forbidden = np.asarray(source.arrays["forbidden_mask"]) > 0
    fixed = np.asarray(source.arrays["fixed_solid_mask"]) > 0

    records: list[dict] = []
    for level in LEVELS:
        transform = DesignTransform(
            shape=SHAPE,
            spacing_m=SPACING,
            active_mask=joint,
            filter=ConeFilter(SHAPE, SPACING, joint, radius_m=FILTER_RADIUS_M),
            projection=TanhProjection(level["b"], 0.5),
            ramp=RampInterpolation(level["q"]),
        )
        adapter = OpenFoamOracle(
            OpenFoamOracleConfig(
                work_root=WORK,
                canonical_topology_state_json=WORK / "topology_state.json",
                template_parent=WORK / "template_frozen",
                template_trial=OUT / "template_trial",
                flow_case_id="straight",
                responses=("downforce",),
                run_root=OUT / "runs",
                timeout_seconds=1800,
            ),
            transform,
        )
        state = transform.forward(rho0)
        payload = adapter.parent_evaluator(state)
        gradients = payload.get("gradients") or {}
        if not gradients:
            raise SystemExit("parent evaluation returned no gradient")
        # the oracle returns the sensitivity in the beta/solver space; the
        # registered OC contract (stage_t_loop line 517) pulls it back into
        # design space before the backend consumes it
        g_beta = np.asarray(next(iter(gradients.values())), dtype=np.float64)
        g_design = transform.pullback_from_beta(rho0, g_beta)
        if not np.isfinite(g_design).all():
            raise SystemExit("pulled-back design gradient contains non-finite values")

        record = measure_level(
            transform=transform,
            rho=rho0,
            gradient=g_design,
            forbidden_mask=forbidden,
            fixed_solid_mask=fixed,
            move_limit=level["move_limit"],
            registered_target=REGISTERED_TARGET,
            v_max_projected=V_MAX_PROJECTED,
            tolerance=V_TOLERANCE,
        )
        record.update(
            {
                "level": level["name"],
                "b": level["b"],
                "q": level["q"],
                "filter_radius_m": FILTER_RADIUS_M,
                "candidate_rho_sha256": cp["rho_sha256"],
                "beta_sensitivity_sha256": _sha256(g_beta),
                "design_gradient_sha256": _sha256(g_design),
                "gradient_space": "design (transform.pullback_from_beta)",
                "transform_sha256": transform.transform_hash(),
            }
        )
        records.append(record)
        print(
            json.dumps(
                {
                    "level": record["level"],
                    "bracketed": record["bracketed"],
                    "phi_design": record["phi_design"],
                    "phi_frontier": record["phi_frontier"],
                    "frontier_growth": record["frontier_growth"],
                    "masks_invariant": record["masks_invariant"],
                    "mask_drift_max": record["mask_drift_max"],
                    "probe_within_tolerance": (record["probe"] or {}).get("within_tolerance"),
                }
            ),
            flush=True,
        )

    all_masks_invariant = all(record["masks_invariant"] for record in records)
    all_monotone = all(record["monotone_nondecreasing"] for record in records)
    any_bracketed = any(record["bracketed"] for record in records)
    all_growth_positive = all(record["frontier_growth"] > 0.0 for record in records)
    level_0 = records[0]
    artifact = {
        "kind": "pq3_3b_preflight_v2",
        "schema_version": 2,
        "input_checkpoint": {
            "path": str(CHECKPOINT.relative_to(ROOT)),
            "sha256": _sha256_file(CHECKPOINT),
            "objective": cp["objective"],
            "iteration": cp["iteration"],
            "accepted": cp["accepted"],
        },
        "diagnostic_evidence": {
            "path": str(V1_EVIDENCE.relative_to(ROOT)),
            "sha256": _sha256_file(V1_EVIDENCE),
            "reason_kept": "v1 measured with an ad-hoc phi replica and left the "
            "mask drift as None when unbracketed; v1 is kept unmodified",
        },
        "corrections_vs_v1": [
            "measurements go through ProjectedVolumeTargetBackend.propose/_projected_volume",
            "the oracle beta-space sensitivity is pulled back to design space with transform.pullback_from_beta before the backend consumes it (v1/v2-draft fed it raw, which collapsed the OC family); v1/v2-draft kept unmodified as diagnostic evidence",
            "mask drift (non_active, forbidden, fixed_solid) is always measured; masks_invariant is always a verdict",
            "volume basis is mean(rho_projection[active]) judged against V_max in the projected basis; the raw design mean is not used as infeasibility evidence",
            "intermediate growth level (b=4, q=15, move_limit=0.05) registered ahead of b=8/b=16",
        ],
        "registered_target_projected": REGISTERED_TARGET,
        "v_max_projected": V_MAX_PROJECTED,
        "target_feasible_in_projected_basis": bool(REGISTERED_TARGET <= V_MAX_PROJECTED),
        "levels": records,
        "summary": {
            "all_masks_invariant": all_masks_invariant,
            "all_monotone": all_monotone,
            "any_level_brackets_registered_target": any_bracketed,
            "all_levels_growth_possible": all_growth_positive,
            "preflight_pass": bool(all_masks_invariant and all_monotone and all_growth_positive),
        },
        "claims_supported": [
            "the projection host contract (non-active, forbidden, fixed-solid cells)"
            " is invariant across the backend kappa path, measured per level",
            "phi(kappa) measured monotone non-decreasing with growth margin per level",
        ],
        "claims_not_supported": [
            "the registered projected target 0.018 is not claimed reachable in one OC step;"
            " per-step reachability gates the multi-iteration campaign manifest",
            "no OpenFOAM optimization iteration has been run: this is a preflight only",
        ],
    }
    EVIDENCE.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))


if __name__ == "__main__":
    main()
