#!/usr/bin/env python3
"""Freeze XFID45-CERT-01 criteria after synthetic and known-regression checks."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

import numpy as np
import scipy
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_xfid45_root_certifier_2026_10_03 import (  # noqa: E402
    enumerate_ray_roots as sturm_roots,
    nearest_root as sturm_nearest,
)
from scripts.xfid45_root_certifier_2026_10_03 import (  # noqa: E402
    enumerate_ray_roots,
    nearest_root,
    position_tolerance,
)

ROUND3 = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"
OUT = ROOT / "docs/evidence/xfid45_root_certifier_2026_10_03"
BRANCH = "exp/issue45-root-certifier-2026-10-03"
CASES = (
    "D0_interface_offset_minus",
    "D0_interface_offset_plus",
    "D1_filtered_seed11_minus",
    "D1_filtered_seed11_plus",
    "D2_filtered_seed2026_minus",
    "D2_filtered_seed2026_plus",
    "baseline",
    "heldout_R3_eccentric_void",
    "heldout_R3_torus",
    "heldout_R3_two_ellipsoids",
)
R_VALUES = (1, 2, 4, 8)
SOURCES = (
    "scripts/xfid45_root_certifier_2026_10_03.py",
    "scripts/verify_xfid45_root_certifier_2026_10_03.py",
    "scripts/run_xfid45_root_certifier_replay_2026_10_03.py",
    "tests/test_xfid45_root_certifier_2026_10_03.py",
    "scripts/xfid45_round3_measure.py",
    "scripts/verify_xfid45_round3.py",
    "scripts/xfid45_round3_export.py",
    "scripts/diagnose_xfid45_round3_ray_roots.py",
    "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
)
LOCAL_TEST_INPUTS = (
    "work/pq0_2_smoke/project_downforce_volume.yaml",
    "work/sdf_native_genesis_v17/sdf_design_state.npz",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_entry(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def _runtime() -> dict:
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "trimesh": trimesh.__version__,
    }


def _target_inventory(r3_registration: dict) -> dict:
    entries: dict[str, dict] = {}
    fields = {}
    for case in CASES:
        path = ROOT / r3_registration["inputs"][case]["path"]
        entry = inventory_entry(path)
        if entry["sha256"] != r3_registration["inputs"][case]["sha256"]:
            raise RuntimeError(f"Round 3 field hash mismatch: {case}")
        fields[case] = entry
        entries[entry["path"]] = entry
    surfaces = {}
    for r in R_VALUES:
        for case in CASES:
            directory = ROUND3 / "surfaces" / f"r{r}" / case
            stl = directory / "surface.stl.gz"
            if not stl.exists():
                stl = directory / "surface.stl"
            names = {
                "surface_npz": directory / "surface.npz",
                "surface_stl": stl,
                "sample_certificates": directory / "sample_certificates.npz",
                "lineage_orientation": directory / "lineage_orientation.json.gz",
            }
            if case.startswith(("D0_", "D1_", "D2_")):
                names["fixed_baseline_samples"] = (
                    directory / "normal_correspondence.npz"
                )
            saved = {}
            for key, path in names.items():
                entry = inventory_entry(path)
                saved[key] = entry
                entries[entry["path"]] = entry
            surfaces[f"r{r}/{case}"] = saved
    for name in (
        "preregistration.json",
        "result.json",
        "independent_result.json",
        "ray_root_omission_diagnostic.json",
        "bundle_manifest.json",
        "validation/failure_ID_comparison.json",
    ):
        path = ROUND3 / name
        entry = inventory_entry(path)
        entries[entry["path"]] = entry
    pinned_failures = (
        ROOT / "docs/evidence/four_track_baseline_2026_10_02/failure_ids.json"
    )
    entry = inventory_entry(pinned_failures)
    entries[entry["path"]] = entry
    return {
        "case_ids": list(CASES),
        "refinements": list(R_VALUES),
        "original_fields": fields,
        "saved_surface_artifacts": surfaces,
        "files": [entries[key] for key in sorted(entries)],
        "file_count": len(entries),
    }


def _regression_fixture() -> dict:
    case = "D0_interface_offset_minus"
    path = ROUND3 / "surfaces/r4" / case / "normal_correspondence.npz"
    with np.load(path) as data:
        sample = data["double_samples"][691].copy()
    registration = json.loads((ROUND3 / "preregistration.json").read_text())
    target_path = ROOT / registration["inputs"][case]["path"]
    baseline_path = ROOT / registration["inputs"]["baseline"]["path"]
    with np.load(target_path) as data:
        target_phi = data["phi"].copy()
        meta = json.loads(str(data["metadata"]))
    with np.load(baseline_path) as data:
        baseline_phi = data["phi"].copy()
    h = float(meta["spacing_m"])
    origin = np.asarray(meta["origin_m"], dtype=np.float64)
    point, direction = sample[:3], sample[3:6]
    primary = enumerate_ray_roots(target_phi, origin, h, point, direction, 2 * h)
    independent = sturm_roots(target_phi, origin, h, point, direction, 2 * h)
    p_near, p_status = nearest_root(primary, h, 2 * h)
    i_near, i_status = sturm_nearest(independent, h, 2 * h)
    baseline = enumerate_ray_roots(baseline_phi, origin, h, point, direction, 2 * h)
    baseline_near, baseline_status = nearest_root(baseline, h, 2 * h)
    mesh_t = float(sample[7])
    if p_near is None or i_near is None or baseline_near is None:
        raise RuntimeError(
            "known Round 3 sample is not resolved by both successor methods"
        )
    tol = position_tolerance(h, 4 * h, p_near.t_m, i_near.t_m)
    source_mesh_delta = mesh_t - (p_near.t_m - baseline_near.t_m)
    if (
        primary.status != "COMPLETE"
        or independent.status != "COMPLETE"
        or p_status != "UNIQUE_NEAREST_ROOT"
        or i_status != "UNIQUE_NEAREST_ROOT"
        or len(primary.roots) != 2
        or len(independent.roots) != 2
        or abs(p_near.t_m - 0.004166670751981498) > tol
        or abs(i_near.t_m - 0.004166670751981498) > tol
        or abs(p_near.t_m - i_near.t_m) > tol
        or abs(source_mesh_delta - 3.378070927931992e-8) > 2e-12
    ):
        raise RuntimeError("known regression fixture failed successor criteria")
    old = json.loads((ROUND3 / "ray_root_omission_diagnostic.json").read_text())
    return {
        "evidence_class": "known_regression_fixture_pre_target_qualification",
        "case": case,
        "r": 4,
        "sample_index": 691,
        "fixed_sample_file": inventory_entry(path),
        "source_field_file": inventory_entry(target_path),
        "point_m": point.tolist(),
        "normal": direction.tolist(),
        "primary_status": primary.status,
        "independent_status": independent.status,
        "primary_roots": [
            {"t_m": root.t_m, "bracket_m": list(root.bracket_m), "kind": root.kind}
            for root in primary.roots
        ],
        "independent_roots": [
            {"t_m": root.t_m, "bracket_m": list(root.bracket_m), "kind": root.kind}
            for root in independent.roots
        ],
        "primary_nearest_status": p_status,
        "independent_nearest_status": i_status,
        "primary_nearest_root_m": p_near.t_m,
        "independent_nearest_root_m": i_near.t_m,
        "baseline_nearest_root_m": baseline_near.t_m,
        "mesh_intersection_root_m": mesh_t,
        "mesh_minus_corresponding_source_delta_m": source_mesh_delta,
        "root_position_agreement_tolerance_m": tol,
        "previous_parent_selected_root_m": old["parent_target_root_t_m"],
        "previous_residual_cutoff_m": old["parent_residual_candidate_cutoff_m"],
        "previous_diagnostic_discrepancy_m": old["parent_failure_max_m"],
        "result": "PASS",
    }


def _pretarget_validation(test_path: str) -> dict:
    local_test_inputs = {}
    for name in LOCAL_TEST_INPUTS:
        path = ROOT / name
        if not path.is_file():
            raise RuntimeError(f"required local full-suite fixture is missing: {name}")
        local_test_inputs[name] = inventory_entry(path)
    source_paths = (
        "scripts/xfid45_root_certifier_2026_10_03.py",
        "scripts/verify_xfid45_root_certifier_2026_10_03.py",
        "scripts/run_xfid45_root_certifier_replay_2026_10_03.py",
        "scripts/register_xfid45_root_certifier_2026_10_03.py",
        test_path,
    )
    ruff = shutil.which("ruff")
    if ruff is None:
        raise RuntimeError("Ruff executable is required for preregistration")
    commands = [
        ("compileall", [sys.executable, "-m", "compileall", "src", "tests"]),
        ("focused_pytest", [sys.executable, "-m", "pytest", "-q", test_path]),
        ("full_pytest", [sys.executable, "-m", "pytest", "-q"]),
        ("ruff_format_check", [ruff, "format", "--check", *source_paths]),
        ("ruff_check", [ruff, "check", *source_paths]),
        ("git_diff_check", ["git", "diff", "--check"]),
        ("git_cached_diff_check", ["git", "diff", "--cached", "--check"]),
    ]
    records = {}
    logs = {}
    for name, command in commands:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        raw_log = result.stdout + result.stderr
        logs[f"{name}.log"] = "\n".join(
            line.rstrip(" \t\r") for line in raw_log.splitlines()
        ) + ("\n" if raw_log.endswith("\n") else "")
        records[name] = {
            "command": command,
            "exit_code": result.returncode,
            "log": f"pre_target_validation/{name}.log",
        }
        if name != "full_pytest" and result.returncode != 0:
            raise RuntimeError(f"pre-target validation failed: {name}")

    focused_match = re.search(r"(\d+) passed", logs["focused_pytest.log"])
    if not focused_match:
        raise RuntimeError("focused pytest did not report a pass count")
    full_log = logs["full_pytest.log"]
    summary_match = re.search(
        r"(?:(\d+) failed, )?(\d+) passed(?:, (\d+) skipped)?", full_log
    )
    if not summary_match:
        raise RuntimeError("full pytest did not report a recognized summary")
    current_ids = sorted(set(re.findall(r"^FAILED\s+([^\s]+)", full_log, re.M)))
    round3_comparison_path = ROUND3 / "validation" / "failure_ID_comparison.json"
    round3_comparison = json.loads(round3_comparison_path.read_text())
    round3_ids = sorted(round3_comparison["current_failure_ids"])
    pinned_path = ROOT / "docs/evidence/four_track_baseline_2026_10_02/failure_ids.json"
    pinned_ids = sorted(json.loads(pinned_path.read_text()))
    new_ids = sorted(set(current_ids) - set(pinned_ids))
    if current_ids != round3_ids or new_ids:
        raise RuntimeError(
            "full pytest failure IDs differ from the frozen Round 3/current pinned comparison"
        )
    return {
        "evidence_class": "pre_target_software_validation",
        "result": "PASS",
        "commands": records,
        "local_test_input_inventory": local_test_inputs,
        "stored_log_normalization": "trailing spaces, tabs, and carriage returns removed per line; line content and order retained",
        "focused_test_count_passed": int(focused_match.group(1)),
        "full_test_summary": {
            "failed": int(summary_match.group(1) or 0),
            "passed": int(summary_match.group(2)),
            "skipped": int(summary_match.group(3) or 0),
        },
        "failure_ID_comparison": {
            "current_failure_ids": current_ids,
            "frozen_round3_current_failure_ids": round3_ids,
            "pinned_baseline_failure_ids": pinned_ids,
            "new_failure_ids": new_ids,
            "new_failure_ids_zero": not new_ids,
            "exact_round3_current_set_match": current_ids == round3_ids,
            "round3_comparison_file": str(round3_comparison_path.relative_to(ROOT)),
            "pinned_failure_ID_file": str(pinned_path.relative_to(ROOT)),
            "pinned_failure_ID_file_sha256": sha256(pinned_path),
        },
        "logs": {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in logs.items()
        },
        "log_contents": logs,
        "ruff_version": subprocess.check_output(
            [ruff, "--version"], cwd=ROOT, text=True
        ).strip(),
    }


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"evidence directory already exists: {OUT}")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    if branch != BRANCH:
        raise RuntimeError(f"expected {BRANCH}, got {branch}")
    start_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    expected_head = "3f9322dc0fa0f2847a3204427b81a665932b83b8"
    if start_head != expected_head:
        raise RuntimeError(
            f"feature branch must begin at {expected_head}, got {start_head}"
        )

    r3_registration = json.loads((ROUND3 / "preregistration.json").read_text())
    inventory = _target_inventory(r3_registration)
    source_hashes = {name: sha256(ROOT / name) for name in SOURCES}
    regression = _regression_fixture()
    test_path = "tests/test_xfid45_root_certifier_2026_10_03.py"
    validation = _pretarget_validation(test_path)
    OUT.mkdir(parents=True)
    validation_dir = OUT / "pre_target_validation"
    validation_dir.mkdir()
    superseded_pytest_log = Path("/tmp/xfid45-cert01-full-pytest.log")
    superseded_attempt = None
    if superseded_pytest_log.is_file():
        preserved = validation_dir / "initial_full_pytest_without_local_fixtures.log"
        raw_log = superseded_pytest_log.read_text()
        preserved.write_text(
            "\n".join(line.rstrip(" \t\r") for line in raw_log.splitlines())
            + ("\n" if raw_log.endswith("\n") else "")
        )
        superseded_attempt = {
            "evidence_class": "superseded_pre_target_validation_environment_attempt",
            "reason": "managed worktree initially lacked two ignored local test fixtures; it produced 38 failures including two environment-only IDs, then the exact local fixture files were copied from the original checkout and hash-verified",
            "log": str(preserved.relative_to(OUT)),
            "sha256": sha256(preserved),
            "log_normalization": "trailing spaces, tabs, and carriage returns removed per line; line content and order retained",
            "local_fixture_hashes_after_copy": {
                name: inventory_entry(ROOT / name) for name in LOCAL_TEST_INPUTS
            },
        }
    validation["superseded_attempt"] = superseded_attempt
    for name, content in validation.pop("log_contents").items():
        (validation_dir / name).write_text(content)
    (validation_dir / "failure_ID_comparison.json").write_text(
        json.dumps(
            validation["failure_ID_comparison"],
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    validation["artifacts"] = {
        name: inventory_entry(validation_dir / name)
        for name in sorted(path.name for path in validation_dir.iterdir())
    }
    (OUT / "pre_target_validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (OUT / "observed_regression.json").write_text(
        json.dumps(regression, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    synthetic = {
        "result": "PASS",
        "focused_test_command": validation["commands"]["focused_pytest"]["command"],
        "focused_test_count_passed": validation["focused_test_count_passed"],
        "focused_test_log": "pre_target_validation/focused_pytest.log",
        "seed": 451003,
        "random_cubic_cases": 512,
        "case_groups": [
            "constant_nonzero_and_zero",
            "negative_zero_endpoint",
            "linear_quadratic_cubic_and_near_linear_cubic",
            "simple_roots_one_two_three",
            "double_triple_and_tangent_roots",
            "left_right_and_near_endpoint_roots",
            "shared_cell_boundary_root_deduplication",
            "coefficient_dynamic_range_and_small_cubic_term",
            "close_roots_and_float32_float64_epsilon_scales",
            "sub_tolerance_distinct_roots_fail_closed",
            "exact_zero_and_near_zero_neighboring_nodes",
            "trilinear_cell_ray_with_three_roots",
            "fixed_round3_sample_691_regression",
            "nearest_tie_and_tangency_fail_closed",
            "primary_derivative_partition_vs_independent_exact_sturm",
        ],
        "property_generator": "three known real roots sampled uniformly on [-0.5,1.5], scale sampled as 10**U with U uniform [-12,12]",
        "source_hashes": {
            name: source_hashes[name]
            for name in (
                "scripts/xfid45_root_certifier_2026_10_03.py",
                "scripts/verify_xfid45_root_certifier_2026_10_03.py",
                test_path,
            )
        },
    }
    (OUT / "synthetic_results.json").write_text(
        json.dumps(synthetic, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )

    prereg = {
        "certifier_identity": "XFID45-CERT-01",
        "evidence_class": "solver_free_root_certifier_preregistration",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": BRANCH,
        "authoritative_branch": "codex/kaggle-batch-migration",
        "authoritative_start_head": start_head,
        "integration_policy": "merge --no-ff into the authoritative branch after evidence review",
        "issue_scope": "#45 actual zero-level / Stage V export evidence only; #29 cross-reference limited to the same export gap",
        "round3_immutable": True,
        "production_exporter_unchanged": True,
        "solver_free": True,
        "target_evaluation_authorized_after_registration_push": True,
        "target_evaluation_started": False,
        "target_case_replay_not_done": True,
        "certifier_contract": {
            "field": "the registered nodal GridSDF with cellwise trilinear interpolation; restriction to a cellwise straight ray is a polynomial of degree at most three",
            "partition": "split the closed registered ray interval at every original GridSDF cell plane crossed by the ray",
            "primary": "scale-aware coefficient degree reduction; derivative critical points partition the full cubic into monotonic intervals; endpoint zeros, sign crossings, and exact repeated/tangent roots are retained; crossings are isolated by bisection using a position bracket",
            "independent": "separately sampled cubic coefficients and exact-rational Sturm sequence with interval root counting and isolation; imports no primary or Round 3 helper",
            "root_existence_vs_precision": "existence is established by a sign bracket, exact structural endpoint, or exact repeated-root condition; root-position accuracy is the final t-interval width and coefficient-error enclosure; no absolute residual cutoff discards a root",
            "degree_reduction": "trailing coefficient threshold = 32*eps(Float64)*sum(abs(coefficients)); discarded coefficient magnitudes are retained in the sign uncertainty envelope and full-polynomial critical points are also checked",
            "coefficient_error": "64*eps(Float64)*sum(abs(expanded coefficient contributions))",
            "root_position_agreement_tolerance": "16384*eps(Float64)*max(original_h_m, local_interval_length_m, abs(t_left_m), abs(t_right_m), abs(t_root_m))",
            "endpoint_zero": "exact structural zero endpoints are retained before interval sign decisions; -0.0 is zero; non-structural values inside the operation error envelope remain unresolved",
            "cell_boundary_deduplication": "retain distinct cell-plane cuts even when closer than position tolerance; merge only the same exact point endpoint; distinct roots closer than tolerance remain listed and make the root set unresolved",
            "nearest_root": "enumerate all roots first, then minimize abs(t); ties inside the registered position tolerance, zero intervals, incomplete root sets, and tangent roots are ambiguous and unresolved",
            "independent_agreement_required": [
                "root count equality",
                "root positions within the registered position agreement tolerance",
                "nearest-root identity equality",
                "ambiguity/status equality",
            ],
        },
        "absolute_geometry": {
            "limit_m": 0.0005,
            "limit_origin": "unchanged Round 3 min(0.1*epsilon,0.02*h)",
            "pass": "all required samples have certified upper distance <= 0.5 mm and no unresolved sample",
            "fail": "at least one required sample has certified lower distance > 0.5 mm",
            "unresolved": "no certified exceedance, and at least one required sample has no upper certificate <= 0.5 mm",
            "replay": "freshly call the byte-frozen Round 3 parent and independent linear-cell axis-witness evaluators on every saved double and float32 surface; these candidate witness rays are axis-aligned and degree <=1; no topology/orientation/clearance or exporter processing changes",
        },
        "normal_correspondence": {
            "surface_prerequisite": "only pairs whose baseline and target double/float32 surfaces all pass the unchanged topology, orientation, clearance, lineage, and new absolute-geometry gates are qualification-eligible",
            "samples": "re-use the two saved 1,024-row Round 3 baseline sample/normal arrays per target pair; do not resample or extract surfaces",
            "sdf_roots": "re-enumerate every root on the original trilinear baseline and target fields over the unchanged +/-2h normal ray, then select nearest absolute t",
            "mesh_roots": "freshly intersect each saved double mesh and float32 STL on the same registered ray; deduplicate intersections using the registered position tolerance",
            "error_limit_m": 0.0005,
            "mesh_error_guard_m": "unchanged Round 3 2*h*1e-8 + h*1e-9",
            "ambiguous": "multiple equally-near roots, zero intervals, undefined source gradient, tangency, incomplete root set, or nearest mesh-ray tie are unresolved; never fall back to a farther root",
        },
        "synthetic_suite": synthetic,
        "known_regression_fixture": regression,
        "target_replay_inventory": {
            "surfaces": "all 10 registered input fields x r={1,2,4,8}, reusing saved surface.npz and float32 STL bytes (40 surface pairs); no extraction",
            "correspondences": "all six D0/D1/D2 +/- epsilon cases x r={1,2,4,8} x {double,float32}, using saved baseline sample arrays",
            "files": inventory,
        },
        "source_sha256": source_hashes,
        "runtime_identity": _runtime(),
        "pre_target_evidence": {
            "synthetic_results_sha256": sha256(OUT / "synthetic_results.json"),
            "pre_target_validation_sha256": sha256(OUT / "pre_target_validation.json"),
            "observed_regression_sha256": sha256(OUT / "observed_regression.json"),
        },
        "qualification_flags": {
            "solver_qualification": False,
            "fd_oracle": False,
            "field_gradient": False,
            "reverse": False,
            "optimizer": False,
            "topology": False,
            "shape_update_allowed": False,
        },
        "forbidden": [
            "Round 3 evaluator/verifier modification or re-judgment",
            "surface extraction rerun or stored surface byte changes",
            "production exporter changes",
            "orientation or other geometry-processing changes",
            "WaterLily, OpenFOAM, Kaggle, formal XFID, #46 FD-08, optimizer, or gradient backend",
        ],
        "registration_tool_sha256": sha256(Path(__file__)),
    }
    (OUT / "preregistration.json").write_text(
        json.dumps(prereg, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "evidence_dir": str(OUT),
                "case_file_count": inventory["file_count"],
                "synthetic_tests": synthetic["focused_test_count_passed"],
                "regression": regression["result"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
