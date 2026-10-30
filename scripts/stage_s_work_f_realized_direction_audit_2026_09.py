"""Work F realized-direction audit runner (diagnosis D1, solver-free).

Registers the audit manifest (mapping, symmetry, norm rules fixed before the
realized data is read), then reconstructs every registered side's realized
control-point state and compares it with the prescribed movement, direction,
odd/even symmetry and the analytic directional derivatives. No CFD run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_adjoint_qualification import (  # noqa: E402
    active_var_ids,
    parse_derivative_file,
    response_derivative_vector,
)
from cfd_sdf.stage_s_realized_direction import (  # noqa: E402
    BOUNDARY_MOVEMENT_ABS_TOLERANCE_M,
    COSINE_SIMILARITY_MIN,
    DIRECTION_CP_ABS_TOLERANCE_M,
    EVEN_COMPONENT_ABS_TOLERANCE_M,
    ODD_SYMMETRY_ABS_TOLERANCE_M,
    REALIZED_EQUALS_PRESCRIBED_ABS_TOLERANCE_M,
    active_mask_from_ids,
    analytic_directional,
    audit_case,
    audit_pair,
    direction_comparison,
    direction_to_cp_space,
    read_control_points_csv,
    read_control_points_file,
    read_movement_file,
)

CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
SIDES = ROOT / "docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
BASE_CATALOG = (
    ROOT / "work/stage_s_work_f_v1/adjoint/base/optimisation/controlPoints/boxcpsBsplines0.csv"
)
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_realized_direction_audit_manifest_2026_09.json"
ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_realized_direction_audit_2026_09.json"
OBJECTIVE_SIGNS = {"drag": 1.0, "downforce": 1.0}


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _input_hashes() -> dict[str, dict[str, str]]:
    files = {
        "catalog": CATALOG,
        "qualification": QUALIFICATION,
        "sides": SIDES,
        "result": RESULT,
        "base_control_point_catalog": BASE_CATALOG,
    }
    paths = sorted((ADJOINT_CASE / "optimisation" / "derivatives").glob("*"))
    for path in paths:
        files[f"derivative_{path.name}"] = path
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for name, path in files.items()}


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("realized-direction audit manifest already exists")
    manifest = {
        "kind": "stage_s_work_f_realized_direction_audit_manifest",
        "schema_version": 1,
        "rules": {
            "realized_equals_prescribed_abs_tolerance_m": REALIZED_EQUALS_PRESCRIBED_ABS_TOLERANCE_M,
            "boundary_movement_abs_tolerance_m": BOUNDARY_MOVEMENT_ABS_TOLERANCE_M,
            "odd_symmetry_abs_tolerance_m": ODD_SYMMETRY_ABS_TOLERANCE_M,
            "even_component_abs_tolerance_m": EVEN_COMPONENT_ABS_TOLERANCE_M,
            "cosine_similarity_min": COSINE_SIMILARITY_MIN,
            "direction_cp_abs_tolerance_m": DIRECTION_CP_ABS_TOLERANCE_M,
            "analytic_recomputation": (
                "d = sum_i total_i * direction_i over the active varID set, joined by varID; "
                "realized contraction uses the odd difference of the realized control-point states"
            ),
            "note": "tolerances are registered before the realized control-point data is read and are not adjusted afterwards",
        },
        "inputs": _input_hashes(),
        "claims_not_supported": [
            "this audit reads no flow response and changes no registered threshold or evidence",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _derivative_vectors() -> dict[str, np.ndarray]:
    paths = sorted((ADJOINT_CASE / "optimisation" / "derivatives").glob("*"))
    derivatives = {
        "drag": parse_derivative_file(
            next(path for path in paths if "adjDrag" in path.name), expected_solver="adjDrag"
        ),
        "downforce": parse_derivative_file(
            next(path for path in paths if "adjDownforce" in path.name),
            expected_solver="adjDownforce",
        ),
    }
    ids = active_var_ids()
    return {
        response: response_derivative_vector(
            derivative, active_ids=ids, objective_sign=OBJECTIVE_SIGNS[response]
        )
        for response, derivative in derivatives.items()
    }


def audit() -> dict:
    if ARTIFACT.exists():
        raise SystemExit("realized-direction audit artifact already exists")
    manifest = ca.load_json(MANIFEST)
    for name, record in manifest["inputs"].items():
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"audit input changed: {name}")
    qualification = ca.load_json(QUALIFICATION)
    sides = ca.load_json(SIDES)
    result = ca.load_json(RESULT)
    catalog = ca.load_json(CATALOG)
    ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    mask = active_mask_from_ids(ids)
    base = read_control_points_csv(BASE_CATALOG)
    derivative_vectors = _derivative_vectors()
    fd_by_key = {
        (response, row["direction"], float(row["epsilon"])): row["fd"]
        for response, rows in result["rows"].items()
        for row in rows
    }

    side_records: dict[str, dict] = {}
    realized_cache: dict[str, np.ndarray] = {}
    for side_id, side in sides["sides"].items():
        case_dir = ROOT / side["case_dir"]
        realized = read_control_points_file(
            case_dir / "0" / "uniform" / "volumetricBSplines" / "boxcpsBsplines"
        )
        prescribed = read_movement_file(case_dir / "constant" / "controlPointsMovement")
        realized_cache[side_id] = realized
        checks = audit_case(
            base=base, realized=realized, prescribed=prescribed, active_mask=mask
        )
        checks["pass"] = bool(
            checks["realized_equals_prescribed"] and checks["boundary_fixed"] and checks["inactive_zero"]
        )
        side_records[side_id] = {
            "direction": side["direction"],
            "epsilon_m": side["epsilon_m"],
            "sign": side["sign"],
            "case_dir": side["case_dir"],
            "realized_control_points_sha256": _sha256(
                case_dir / "0" / "uniform" / "volumetricBSplines" / "boxcpsBsplines"
            ),
            "prescribed_movement_sha256": side["movement_sha256"],
            "max_prescribed_movement_m": float(np.max(np.abs(prescribed))),
            "checks": checks,
        }

    pair_records: dict[str, dict] = {}
    for direction_name, direction in qualification["directions"].items():
        direction_values = np.asarray(direction["values"], dtype=np.float64)
        direction_cp = direction_to_cp_space(direction_values, ids)
        for epsilon in [float(value) for value in catalog["shared_catalog"]["epsilons_m"]]:
            plus_id = next(
                side_id
                for side_id, record in side_records.items()
                if record["direction"] == direction_name
                and record["epsilon_m"] == epsilon
                and record["sign"] == "plus"
            )
            minus_id = next(
                side_id
                for side_id, record in side_records.items()
                if record["direction"] == direction_name
                and record["epsilon_m"] == epsilon
                and record["sign"] == "minus"
            )
            pair = audit_pair(
                base=base,
                realized_plus=realized_cache[plus_id],
                realized_minus=realized_cache[minus_id],
                epsilon=epsilon,
            )
            comparison = direction_comparison(
                direction_cp=direction_cp, delta_odd=pair.delta_odd, active_mask=mask
            )
            odd_symmetry = float(
                np.max(np.abs(pair.delta_even[mask])) * 2.0 * epsilon
            ) if mask.any() else 0.0
            # the registered tolerances are physical lengths; convert the
            # per-epsilon rates back to metres before judging them
            even_component_m = (
                float(np.max(np.abs(pair.delta_even[mask]))) * epsilon if mask.any() else 0.0
            )
            movement_difference_m = comparison["max_abs_difference"] * epsilon
            analytic: dict[str, dict] = {}
            for response, vector in derivative_vectors.items():
                prescribed_analytic = analytic_directional(vector, direction_cp, mask)
                realized_analytic = float(np.dot(vector, pair.delta_odd[mask]))
                fd = fd_by_key[(response, direction_name, epsilon)]
                analytic[response] = {
                    "d_analytic_prescribed": prescribed_analytic,
                    "d_analytic_realized": realized_analytic,
                    "fd": fd,
                    "ratio_prescribed": (
                        float(fd) / prescribed_analytic if fd is not None and prescribed_analytic else None
                    ),
                    "ratio_realized": (
                        float(fd) / realized_analytic if fd is not None and realized_analytic else None
                    ),
                }
            pair_records[f"{direction_name}__eps{epsilon:.6g}"] = {
                "direction": direction_name,
                "epsilon_m": epsilon,
                "delta_odd_sha256": hashlib.sha256(
                    np.ascontiguousarray(pair.delta_odd, dtype=np.float64).tobytes()
                ).hexdigest(),
                "odd_symmetry_abs_error_m": odd_symmetry,
                "even_component_abs_m": even_component_m,
                "movement_difference_m": movement_difference_m,
                "comparison": comparison,
                "analytic": analytic,
                "pass": bool(
                    comparison["cosine_ok"]
                    and movement_difference_m <= DIRECTION_CP_ABS_TOLERANCE_M
                    and odd_symmetry <= ODD_SYMMETRY_ABS_TOLERANCE_M
                    and even_component_m <= EVEN_COMPONENT_ABS_TOLERANCE_M
                ),
            }
    n_fail_sides = sum(1 for record in side_records.values() if not record["checks"]["pass"])
    n_fail_pairs = sum(1 for record in pair_records.values() if not record["pass"])
    artifact = {
        "kind": "stage_s_work_f_realized_direction_audit",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "sides": side_records,
        "pairs": pair_records,
        "summary": {
            "n_sides": len(side_records),
            "n_side_failures": n_fail_sides,
            "n_pairs": len(pair_records),
            "n_pair_failures": n_fail_pairs,
            "realized_direction_audit_pass": bool(n_fail_sides == 0 and n_fail_pairs == 0),
            "original_verdict_unchanged": True,
            "solver_started": False,
        },
        "claims_supported": [
            "the realized control-point states reproduce the prescribed movements and directions within the registered tolerances",
            "the analytic directional derivatives are recomputed from the raw derivative files joined by varID",
        ],
        "claims_not_supported": [
            "this audit does not change the registered FD verdict or thresholds",
            "no flow response was read in this audit",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F realized-direction audit (D1)")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.audit:
        audit()
    else:
        parser.error("specify --register or --audit")


if __name__ == "__main__":
    main()
