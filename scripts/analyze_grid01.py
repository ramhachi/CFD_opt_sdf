#!/usr/bin/env python3
"""Fail-closed GRID-01 analyzer for hash-bound flow_24/flow_32 secants."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from cfd_sdf import grid01_contract as C  # noqa: E402
from cfd_sdf import lowdim02a_contract as FLOW32  # noqa: E402
from fd08_v2_campaign_io import recompute_force_n  # noqa: E402
from analyze_lowdim02a import flow32_criteria  # noqa: E402
import build_grid01_kernel as kernel_builder  # noqa: E402
from grid01_gpu import select_worker_gpu  # noqa: E402
import lowdim01_states  # noqa: E402
import step01_states  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"
FORMAL = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json"
STEP01_INVENTORY = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json"
STEP01_ANALYSIS = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json"
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
SUMMARY_REL = 1.0e-9
BASELINE_REL = 1.0e-12
MIN_T_END = 120.0
KERNEL = "a"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-grid01-a"
MINIMUM_STATE_NAMES = ["step01__baseline"] + [
    f"step01__{direction}__s2.5mm__{side}"
    for direction in C.BASIS
    for side in ("plus", "minus")
]

# Every runtime, registration, and source file that the freeze must bind.
FILE_PATHS = {
    "analyzer": "scripts/analyze_grid01.py",
    "contract": "src/cfd_sdf/grid01_contract.py",
    "input_builder": "scripts/build_grid01_inputs.py",
    "runner_template": "scripts/grid01_runner_template.py",
    "kernel_builder": "scripts/build_grid01_kernel.py",
    "freeze_builder": "scripts/build_grid01_freeze.py",
    "job": "scripts/waterlily_lowdim02_flow32_job.jl",
    "step01_states_module": "scripts/step01_states.py",
    "lowdim01_states_module": "scripts/lowdim01_states.py",
    "lowdim01_geometry_helpers": "scripts/build_lowdim01_inputs.py",
    "flow32_criteria_source": "scripts/analyze_lowdim02a.py",
    "flow32_contract": "src/cfd_sdf/lowdim02a_contract.py",
    "grid01_gpu_policy": "scripts/grid01_gpu.py",
    "cfd_sdf_source_tree": "src/cfd_sdf",
    "force_io": "scripts/fd08_v2_campaign_io.py",
    "formal_criteria": "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json",
    "step01_inventory": "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json",
    "step01_analysis": "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json",
    "lowdim01_inventory": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json",
    "lowdim01_proposal_direction": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inputs/proposal_downforce.dir_f4_fortran.raw",
    "geometry_exploration": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/geometry_exploration_step01_states.json",
    "inventory": "docs/evidence/grid01_cross_grid_secant_2026_10_09/inventory.json",
    "inventory_sha256": "docs/evidence/grid01_cross_grid_secant_2026_10_09/inventory.json.sha256",
    "prerun_note": "docs/evidence/grid01_cross_grid_secant_2026_10_09/prerun_note.md",
    "identity_free_check": "docs/evidence/grid01_cross_grid_secant_2026_10_09/identity_free_check.json",
    "rendered_runner": "infra/kaggle/kernel_grid01_a/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_grid01_a/kernel-metadata.json",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "julia_source_tree": "julia/CFDSDFWaterLily/src",
    "baseline_phi": "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw",
    "w4_flow32_baseline_csv": "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv",
    "canonical_npz": "docs/evidence/xfid01_geometry_preflight_2026_10_03/canonical_state.npz",
    "handoff_instruction": "docs/codex_instruction_grid01_cross_grid_secant_2026_10_09.md",
    **{f"test_{name}": f"tests/{name}.py" for name in (
        "grid01_synthetic", "test_grid01_contract", "test_grid01_analyzer", "test_grid01_prereg", "test_grid01_followup",
    )},
    "identity_free_check_sha256": "docs/evidence/grid01_cross_grid_secant_2026_10_09/identity_free_check.json.sha256",
    "identity_listing_confirmation": "docs/evidence/grid01_cross_grid_secant_2026_10_09/identity_listing_confirmation.json",
    "identity_listing_confirmation_sha256": "docs/evidence/grid01_cross_grid_secant_2026_10_09/identity_listing_confirmation.json.sha256",
    **{f"direction_{name}": f"docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/{name}.dir_f4_fortran.raw" for name in C.BASIS},
}

SOURCE_COMMIT_EXCEPTIONS = {
    "rendered_runner",
    "kernel_metadata",
    "identity_free_check",
    "identity_free_check_sha256",
    "identity_listing_confirmation",
    "identity_listing_confirmation_sha256",
}


def sha256(path: Path) -> str:
    path = Path(path)
    if path.is_dir():
        files = [
            item for item in path.rglob("*")
            if item.is_file() and "__pycache__" not in item.relative_to(path).parts and item.suffix not in {".pyc", ".pyo"}
        ]
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(files)]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jload(path: Path) -> Any:
    return json.loads(Path(path).read_text())


def frozen_path_sha(name: str, path: Path, source_commit: str, *, root: Path = ROOT) -> str:
    """Hash the registered package members, not later unrelated added modules."""
    if name != "cfd_sdf_source_tree":
        return sha256(path)
    relative = str(path.relative_to(root))
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", source_commit, "--", relative],
        check=True, capture_output=True, text=True,
    )
    names = sorted(line for line in listed.stdout.splitlines() if line)
    if not names:
        raise ValueError("registered Python source closure is empty")
    lines = [f"{Path(name).relative_to(Path(relative))}  {sha256(root / name)}" for name in names]
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def _valid_sha(value: Any, *, length: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1.0e-300)


def _json_sha(value: Any) -> str:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    return hashlib.sha256(data).hexdigest()


def _safe_json_sha(value: Any) -> str | None:
    try:
        return _json_sha(value)
    except (TypeError, ValueError):
        return None


def _source_commit_failures(
    source_commit: str,
    file_hashes: dict[str, Any],
    *,
    root: Path = ROOT,
    file_paths: dict[str, str] = FILE_PATHS,
    exceptions: set[str] = SOURCE_COMMIT_EXCEPTIONS,
    parent_commit: str = "32e64715dc20a9ac2dd78e3c011bcb48f311b98e",
) -> list[str]:
    """Bind every non-generated frozen input/source blob to the named commit."""
    failures: list[str] = []
    if not _valid_sha(source_commit, length=40):
        return ["source commit is not a full lowercase Git SHA-1"]
    required = set(file_paths) - exceptions
    missing = sorted(required - set(file_hashes))
    if missing:
        failures.append(f"source commit file-hash closure is incomplete: {missing}")
    git = ["git", "-C", str(root)]
    resolved = subprocess.run(git + ["rev-parse", "--verify", f"{source_commit}^{{commit}}"], capture_output=True, text=True)
    if resolved.returncode != 0 or resolved.stdout.strip() != source_commit:
        return failures + ["source commit does not resolve to the named commit"]
    parent_ancestor = subprocess.run(git + ["merge-base", "--is-ancestor", parent_commit, source_commit], capture_output=True)
    if parent_ancestor.returncode != 0:
        failures.append("declared integration parent is not an ancestor of source commit")
    ancestor = subprocess.run(git + ["merge-base", "--is-ancestor", source_commit, "HEAD"], capture_output=True)
    if ancestor.returncode != 0:
        failures.append("source commit is not an ancestor of HEAD")
    for name in sorted(required & set(file_paths)):
        relpath = file_paths[name]
        expected = file_hashes.get(name)
        if not _valid_sha(expected):
            failures.append(f"source commit SHA is missing or malformed: {name}")
            continue
        path = root / relpath
        if path.is_dir():
            listed = subprocess.run(git + ["ls-tree", "-r", "--name-only", source_commit, "--", relpath], capture_output=True, text=True)
            if listed.returncode != 0:
                failures.append(f"source commit tree cannot be listed: {name}")
                continue
            committed = sorted(line for line in listed.stdout.splitlines() if line)
            current = sorted(
                str(item.relative_to(root)) for item in path.rglob("*")
                if item.is_file() and "__pycache__" not in item.relative_to(path).parts and item.suffix not in {".pyc", ".pyo"}
            ) if path.is_dir() else []
            membership_ok = set(committed) <= set(current) if name == "cfd_sdf_source_tree" else committed == current
            if not membership_ok:
                failures.append(f"source commit tree membership differs from the frozen worktree: {name}")
                continue
            tree_lines = []
            for entry in committed:
                blob = subprocess.run(git + ["show", f"{source_commit}:{entry}"], capture_output=True)
                if blob.returncode != 0:
                    failures.append(f"source commit blob is missing: {entry}")
                    continue
                digest = hashlib.sha256(blob.stdout).hexdigest()
                tree_lines.append(f"{Path(entry).relative_to(Path(relpath))}  {digest}")
            actual_tree_hash = hashlib.sha256(("\n".join(tree_lines) + "\n").encode()).hexdigest()
            if actual_tree_hash != expected:
                failures.append(f"source commit tree hash differs from the freeze: {name}")
        else:
            blob = subprocess.run(git + ["show", f"{source_commit}:{relpath}"], capture_output=True)
            if blob.returncode != 0:
                failures.append(f"source commit blob is missing: {relpath}")
            elif hashlib.sha256(blob.stdout).hexdigest() != expected:
                failures.append(f"{relpath} in source commit differs from its frozen hash")
    return failures


def _incomplete(failures: list[str]) -> dict[str, Any]:
    return {
        "verdict": "GRID01_SECANT_INCOMPLETE",
        "integrity": {"pass": False, "failures": failures},
        "evidence_class": "incomplete_contract_or_runtime_integrity",
        "qualification_flags": {name: False for name in FLAGS},
        "selected_delta": None,
        "grad03_verdict": None,
        "fd08_verdict_unchanged": True,
        "no_gradient_claim": True,
        "not_grid_converged": True,
        "not_opt01": True,
        "reinitialization": "none",
        "shape_update_allowed": False,
    }


def _validate_freeze(freeze: Any, inventory: dict[str, Any], formal: dict[str, Any], step01_analysis: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not isinstance(freeze, dict):
        return ["freeze is not an object"]
    from build_grid01_freeze import contract_sections, require_identity_artifact, _require_identity_free, load_listing_confirmation

    sections = contract_sections(inventory)
    expected_keys = {
        "kind", "parent_integration_commit", "source_commit", "file_hashes", "pins",
        "identity_free_check", "frozen_utc", *sections.keys(),
    }
    if set(freeze) != expected_keys:
        failures.append(
            "freeze top-level schema is incomplete or unexpected: "
            f"missing={sorted(expected_keys - set(freeze))}, extra={sorted(set(freeze) - expected_keys)}"
        )
    if freeze.get("kind") != "grid01_cross_grid_secant_prerun_freeze":
        failures.append("freeze kind mismatch")
    if freeze.get("parent_integration_commit") != "32e64715dc20a9ac2dd78e3c011bcb48f311b98e":
        failures.append("freeze parent integration commit mismatch")
    if not _valid_sha(freeze.get("source_commit"), length=40):
        failures.append("freeze source commit is missing or malformed")
    for section, expected in sections.items():
        try:
            matches = json.dumps(freeze.get(section), sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
                expected, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError):
            matches = False
        if not matches:
            failures.append(f"freeze {section} is incomplete or differs from the exact frozen declaration")
    frozen_utc = freeze.get("frozen_utc")
    frozen_at = None
    try:
        from datetime import datetime, timezone

        frozen_at = datetime.fromisoformat(frozen_utc.replace("Z", "+00:00"))
        if frozen_at.tzinfo is None or frozen_at > datetime.now(timezone.utc):
            raise ValueError("freeze timestamp must be timezone-aware and not in the future")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"freeze timestamp is missing or invalid: {exc}")
    file_hashes = freeze.get("file_hashes")
    expected_hash_keys = set(FILE_PATHS) | {"inventory_canonical_json"}
    if not isinstance(file_hashes, dict):
        failures.append("freeze file_hashes is missing or malformed")
        file_hashes = {}
    if set(file_hashes) != expected_hash_keys:
        failures.append("freeze file_hashes key set is incomplete or unexpected")
    for name, relpath in FILE_PATHS.items():
        expected = file_hashes.get(name)
        path = ROOT / relpath
        if not _valid_sha(expected):
            failures.append(f"freeze SHA-256 is missing or malformed: {name}")
            continue
        try:
            if not path.is_file() and not path.is_dir():
                failures.append(f"frozen file is missing: {relpath}")
            elif frozen_path_sha(name, path, freeze.get("source_commit", ""), root=ROOT) != expected:
                failures.append(f"frozen file hash mismatch: {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"could not hash {name}: {type(exc).__name__}: {exc}")
    failures.extend(_source_commit_failures(freeze.get("source_commit", ""), file_hashes))
    canonical_hash = file_hashes.get("inventory_canonical_json")
    if not _valid_sha(canonical_hash) or _json_sha(inventory) != canonical_hash:
        failures.append("canonical inventory hash differs from the freeze")
    if not isinstance(inventory, dict) or not _valid_sha(file_hashes.get("inventory")):
        failures.append("inventory or its frozen SHA is missing")
    else:
        try:
            if sha256(ROOT / FILE_PATHS["inventory"]) != file_hashes["inventory"]:
                failures.append("inventory file hash differs from the freeze")
            if (ROOT / FILE_PATHS["inventory_sha256"]).read_text().strip() != file_hashes["inventory"]:
                failures.append("inventory SHA sidecar differs from the frozen inventory")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"could not verify inventory file hash/sidecar: {exc}")
    try:
        actual_pins = kernel_builder.pins()
    except Exception as exc:  # noqa: BLE001
        actual_pins = {}
        failures.append(f"runtime pins cannot be re-derived: {type(exc).__name__}: {exc}")
    pins = freeze.get("pins")
    if not isinstance(pins, dict) or not pins or pins != actual_pins:
        failures.append("freeze pins are missing, empty, or differ from the source inputs")
    elif any(not _valid_sha(value) for value in pins.values()):
        failures.append("freeze contains an empty or malformed runtime pin")
    identity_record = freeze.get("identity_free_check")
    try:
        require_identity_artifact(identity_record, ROOT)
        _require_identity_free(identity_record, as_of=frozen_at, listing_confirmation=load_listing_confirmation(ROOT))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"identity-free check is not valid and fresh: {type(exc).__name__}: {exc}")
    try:
        rendered_runner = (ROOT / FILE_PATHS["rendered_runner"]).read_text()
        if rendered_runner != kernel_builder.render(freeze.get("source_commit", "")):
            failures.append("rendered runner does not exactly reproduce kernel.render(source_commit)")
        metadata = jload(ROOT / FILE_PATHS["kernel_metadata"])
        if metadata != kernel_builder.metadata():
            failures.append("kernel metadata differs from kernel.metadata()")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"generated kernel artifacts cannot be verified: {type(exc).__name__}: {exc}")
    if not isinstance(formal, dict) or not isinstance(step01_analysis, dict):
        failures.append("formal criteria or STEP-01 analysis is unavailable")
    return failures


def _check_inventory(inventory: Any, step01_inventory: Any, step01_analysis: Any) -> list[str]:
    failures: list[str] = []
    if not isinstance(inventory, dict):
        return ["GRID-01 inventory is not an object"]
    if not isinstance(step01_inventory, dict) or not isinstance(step01_inventory.get("states"), list):
        return ["frozen STEP-01 inventory is missing or malformed"]
    if inventory.get("kind") != "grid01_flow24_flow32_cross_grid_secant_inventory":
        failures.append("GRID-01 inventory kind mismatch")
    try:
        from build_grid01_inputs import measurement_contract
        expected_measurement = measurement_contract(jload(FORMAL))
        if _json_sha(inventory.get("measurement_contract")) != _json_sha(expected_measurement):
            failures.append("complete measurement contract differs from fixed flow_32 rederivation")
        for key in ("job_env_common", "margin_gate_m", "perturbation"):
            if _json_sha(inventory.get(key)) != _json_sha(step01_inventory.get(key)):
                failures.append(f"inventory {key} differs from immutable STEP-01 contract")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"inventory semantics cannot be rederived: {type(exc).__name__}: {exc}")
    rows = inventory.get("states")
    if not isinstance(rows, list) or [row.get("name") for row in rows if isinstance(row, dict)] != MINIMUM_STATE_NAMES:
        failures.append("inventory must contain the exact ordered baseline plus eight +/-2.5 mm STEP-01 states")
        return failures
    by_step = {row.get("name"): row for row in step01_inventory["states"] if isinstance(row, dict)}
    if inventory.get("kernels") != {"a": MINIMUM_STATE_NAMES}:
        failures.append("inventory kernel plan differs from the nine registered states")
    if inventory.get("basis_order") != list(C.BASIS):
        failures.append("inventory basis order differs from the registered four directions")
    baseline_reference = inventory.get("flow32_baseline_reference")
    if not isinstance(baseline_reference, dict) or not _valid_sha(baseline_reference.get("forces_csv_sha256")):
        failures.append("flow_32 baseline reference SHA is missing or malformed")
    try:
        w4_csv = ROOT / FILE_PATHS["w4_flow32_baseline_csv"]
        if not isinstance(baseline_reference, dict) or sha256(w4_csv) != baseline_reference.get("forces_csv_sha256"):
            failures.append("flow_32 baseline reference differs from retained W4 bytes")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"could not verify retained W4 baseline: {type(exc).__name__}: {exc}")
    source_hashes = inventory.get("source_hashes", {})
    if not isinstance(source_hashes, dict):
        failures.append("inventory source hash map is missing")
    else:
        source_pairs = {
            "step01_inventory_sha256": "step01_inventory",
            "step01_analysis_sha256": "step01_analysis",
            "lowdim01_inventory_sha256": "lowdim01_inventory",
            "geometry_exploration_sha256": "geometry_exploration",
            "formal_criteria_sha256": "formal_criteria",
            "baseline_phi_raw_sha256": "baseline_phi",
            "canonical_npz_sha256": "canonical_npz",
        }
        for field, file_key in source_pairs.items():
            wanted = source_hashes.get(field)
            try:
                if not _valid_sha(wanted) or sha256(ROOT / FILE_PATHS[file_key]) != wanted:
                    failures.append(f"inventory source hash mismatch: {field}")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"inventory source hash could not be checked: {field}: {exc}")
    canonical = inventory.get("canonical_npz")
    if (not isinstance(canonical, dict)
            or canonical.get("path") != FILE_PATHS["canonical_npz"]
            or canonical.get("sha256") != source_hashes.get("canonical_npz_sha256")):
        failures.append("canonical archive path/hash differs from the registered source file")
    else:
        try:
            if sha256(ROOT / canonical["path"]) != canonical["sha256"]:
                failures.append("canonical archive bytes differ from the inventory source hash")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"canonical archive could not be checked: {type(exc).__name__}: {exc}")
    measurement_contract = inventory.get("measurement_contract", {})
    flow32_measurement = measurement_contract.get("flow32_measurement", {}) if isinstance(measurement_contract, dict) else {}
    flow32_case = flow32_measurement.get("case", {}) if isinstance(flow32_measurement, dict) else {}
    if measurement_contract.get("flow32_case") != FLOW32.FLOW32_CASE or flow32_measurement.get("case_id") != FLOW32.FLOW32_CASE["case_id"]:
        failures.append("flow_32 inventory case declaration is stale or differs from FLOW32_CASE")
    if any(flow32_case.get(key) != value for key, value in FLOW32.FLOW32_CASE.items()):
        failures.append("flow_32 measurement case differs from cfd_sdf.lowdim02a_contract.FLOW32_CASE")
    if len(rows) != 9 or rows[0].get("kind") != "baseline" or sum(row.get("kind") == "baseline" for row in rows) != 1:
        failures.append("inventory must contain one first baseline and eight perturbations")
    for index, row in enumerate(rows):
        name = row["name"]
        source = by_step.get(name)
        if source is None:
            failures.append(f"STEP-01 state missing from source inventory: {name}")
            continue
        for key in ("phi_fortran_order_sha256", "phi_c_order_sha256", "state_sha256", "npz_sha256"):
            if row.get(key) != source.get(key) or not _valid_sha(row.get(key)):
                failures.append(f"{name}: {key} differs from the exact STEP-01 state identity")
        for key in ("changed_node_count", "zero_level_margin_m", "margin_tolerance_m"):
            if row.get(key) != source.get(key):
                failures.append(f"{name}: {key} differs from the STEP-01 inventory")
        if index == 0:
            if row.get("direction") is not None or row.get("sign") != 0 or row.get("step_mm") != 0.0:
                failures.append("baseline direction / step metadata is malformed")
            if row.get("geometry_gates") is not None:
                failures.append("baseline must not have perturbation geometry gates")
        else:
            if row.get("kind") != "single" or row.get("direction") not in C.BASIS or row.get("step_mm") != 2.5 or row.get("sign") not in (-1, 1):
                failures.append(f"{name}: invalid direction/step/sign")
            if source.get("kind") != "single" or source.get("directions") != [row.get("direction")] or source.get("step_mm") != 2.5 or source.get("sign") != row.get("sign"):
                failures.append(f"{name}: STEP-01 measurement identity differs")
            geometry = row.get("geometry_gates")
            if not isinstance(geometry, dict) or set(geometry.get("gates", {})) != C.GEOMETRY_GATE_KEYS:
                failures.append(f"{name}: geometry gate set mismatch")
            elif (any(not isinstance(value, bool) for value in geometry["gates"].values())
                  or geometry.get("all_hard_gates_pass") is not all(geometry["gates"].values())):
                failures.append(f"{name}: geometry gate values are inconsistent")
    geometry_contract = inventory.get("geometry_gate_contract", {})
    if set(geometry_contract.get("gate_keys", [])) != C.GEOMETRY_GATE_KEYS:
        failures.append("registered geometry gate contract key set mismatch")
    secants = inventory.get("flow24_reference_step01", {}).get("secants")
    if inventory.get("flow24_reference_step01", {}).get("recomputed") is not False:
        failures.append("flow_24 secants must be direct reads from frozen STEP-01")
    if not isinstance(secants, dict) or not isinstance(step01_analysis, dict):
        failures.append("flow_24 reference secants or STEP-01 analysis are missing")
    else:
        if inventory.get("flow24_reference_step01", {}).get("step01_analysis_sha256") != source_hashes.get("step01_analysis_sha256"):
            failures.append("flow_24 reference SHA differs from the frozen STEP-01 analysis")
        for direction in C.BASIS:
            for quantity in C.RESPONSES:
                expected_rows = step01_analysis.get("series", {}).get(f"{direction}|{quantity}", {}).get("rows", [])
                current = secants.get(direction, {}).get(quantity)
                if not expected_rows or not isinstance(current, dict):
                    failures.append(f"STEP-01 frozen row missing: {direction}|{quantity}")
                    continue
                source = expected_rows[0]
                numeric_keys = ("step_mm", "r0_n", "r_plus_n", "r_minus_n", "g_sec_n_per_m", "eta_even")
                expected_numbers = {key: source[key] for key in numeric_keys if key in source}
                actual_numbers = {key: current.get(key) for key in numeric_keys}
                if actual_numbers != expected_numbers or source.get("step_mm") != 2.5:
                    failures.append(f"flow_24 source numbers differ from the frozen 2.5 mm STEP-01 row: {direction}|{quantity}")
                if current.get("source_step01_resolved") is not source.get("resolved"):
                    failures.append(f"flow_24 historical source_step01_resolved differs from STEP-01: {direction}|{quantity}")
                try:
                    contrast = current["r_plus_n"] - current["r_minus_n"]
                    even_part = (current["r_plus_n"] + current["r_minus_n"] - 2.0 * current["r0_n"]) / 2.0
                    if current.get("resolved") is not (abs(contrast) > C.MIN_RESOLVED_N):
                        failures.append(f"flow_24 GRID-01 resolved flag is not rederived from the strict contrast rule: {direction}|{quantity}")
                    if current.get("even_part_n") != even_part:
                        failures.append(f"flow_24 even_part_n is not rederived from the copied R values: {direction}|{quantity}")
                except (KeyError, TypeError, ValueError):
                    failures.append(f"flow_24 derived resolution/even part is malformed: {direction}|{quantity}")
                if (any(not _finite(current.get(key)) for key in (*numeric_keys, "even_part_n"))
                        or not isinstance(current.get("resolved"), bool)
                        or not isinstance(current.get("source_step01_resolved"), bool)):
                    failures.append(f"flow_24 row has a missing/non-finite value: {direction}|{quantity}")
    return failures


def _manifest_failures(out: Path) -> list[str]:
    failures = []
    manifest_path = out / "output_manifest.json"
    if not manifest_path.is_file():
        return ["output_manifest.json missing"]
    try:
        manifest_obj = jload(manifest_path)
        files = manifest_obj.get("files")
    except Exception as exc:  # noqa: BLE001
        return [f"output_manifest.json malformed: {type(exc).__name__}: {exc}"]
    if not isinstance(files, dict) or not files:
        return ["output_manifest.json has a missing or empty files map"]
    actual = {str(path.relative_to(out)) for path in out.rglob("*") if path.is_file() and path.name != "output_manifest.json"}
    if set(files) != actual:
        failures.append("output_manifest.json path set differs from the actual kernel output")
    for relpath, digest in files.items():
        rel = Path(relpath)
        if rel.is_absolute() or ".." in rel.parts:
            failures.append(f"manifest path escapes the kernel output: {relpath}")
            continue
        if not _valid_sha(digest):
            failures.append(f"manifest SHA is missing or malformed: {relpath}")
            continue
        path = out / relpath
        try:
            if not path.is_file() or sha256(path) != digest:
                failures.append(f"manifest hash mismatch: {relpath}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"manifest could not verify {relpath}: {type(exc).__name__}: {exc}")
    return failures


def _check_kernel(out: Path, freeze: dict[str, Any], inventory: dict[str, Any], criteria: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    states: dict[str, Any] = {}
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done is not True or error is not False:
        failures.append(f"DONE must exist and ERROR.txt must not (done={done}, error={error})")
    try:
        index = jload(out / "grid01_index.json")
    except Exception as exc:  # noqa: BLE001
        index = {}
        failures.append(f"grid01_index.json missing or malformed: {type(exc).__name__}: {exc}")
    try:
        identity = jload(out / "run_identity.json")
    except Exception as exc:  # noqa: BLE001
        identity = {}
        failures.append(f"run_identity.json missing or malformed: {type(exc).__name__}: {exc}")
    if index.get("status") != "COMPLETE" or index.get("kernel") != KERNEL or index.get("kernel_id") != KERNEL_ID:
        failures.append("kernel index status or identity mismatch")
    if identity.get("kernel") != KERNEL or identity.get("kernel_id") != KERNEL_ID or identity.get("source_commit") != freeze.get("source_commit") or identity.get("failure_stage") is not None:
        failures.append("run identity kernel/source commit/failure-stage mismatch")
    frozen_pins = freeze.get("pins")
    if not isinstance(frozen_pins, dict) or not frozen_pins:
        failures.append("freeze pins are empty or malformed")
        frozen_pins = {}
    if identity.get("pins") != frozen_pins or identity.get("verified") != frozen_pins:
        failures.append("kernel did not record exact verification of every frozen pin")
    rendered_sha = freeze.get("file_hashes", {}).get("rendered_runner")
    if not _valid_sha(rendered_sha) or identity.get("runner_sha256") != rendered_sha:
        failures.append("runner hash differs from the reviewed rendered runner")
    baseline_ref = inventory.get("flow32_baseline_reference", {})
    if identity.get("flow32_baseline_csv_sha256") != baseline_ref.get("forces_csv_sha256"):
        failures.append("kernel baseline CSV pin differs from the inventory")
    failures.extend(_manifest_failures(out))
    try:
        manifest = jload(out / "output_manifest.json").get("files", {})
    except Exception:  # noqa: BLE001
        manifest = {}
    required = {"grid01_index.json", "run_identity.json", "nvidia_smi.csv", "gpu_device_probe.json", "gpu_device_probe.log", "DONE"}
    for name in MINIMUM_STATE_NAMES:
        required |= {f"states/{name}/flow_32.forces.csv", f"states/{name}/flow_32.summary.json", f"states/{name}/W4_JOB_DONE"}
    if not required <= set(manifest):
        failures.append("manifest omits one or more required state/runtime files")
    selected_gpu = None
    try:
        selected_gpu = select_worker_gpu((out / "nvidia_smi.csv").read_text())
    except Exception as exc:  # noqa: BLE001
        failures.append(f"GPU inventory must be nonempty and every visible device must be a Tesla T4: {exc}")
    if selected_gpu is not None:
        if identity.get("selected_gpu") != selected_gpu:
            failures.append("runner did not select physical GPU index 0 from the visible inventory")
        if identity.get("cuda_device_order") != "PCI_BUS_ID" or identity.get("cuda_visible_devices") != "0":
            failures.append("runner CUDA device selection differs from the frozen physical-index-zero policy")
        try:
            expected_probe = {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"],
                              "visible_gpu_uuids": [selected_gpu["uuid"]], "default_device_uuid": selected_gpu["uuid"],
                              "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}
            if _json_sha(jload(out / "gpu_device_probe.json")) != _json_sha(expected_probe):
                raise ValueError("CUDA observed singleton/default UUID mismatch")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"independent CUDA GPU identity probe failed: {exc}")
    entries = index.get("states")
    if not isinstance(entries, list) or [entry.get("name") for entry in entries if isinstance(entry, dict)] != MINIMUM_STATE_NAMES:
        failures.append("completed kernel states are not the exact ordered nine-state plan")
        entries = []
    if any(entry.get("complete") is not True or type(entry.get("exit_code")) is not int or entry.get("exit_code") != 0 for entry in entries):
        failures.append("at least one registered state is incomplete")
    try:
        actual_dirs = sorted(path.name for path in (out / "states").iterdir() if path.is_dir())
    except Exception:  # noqa: BLE001
        actual_dirs = []
    if actual_dirs != sorted(MINIMUM_STATE_NAMES):
        failures.append("state directories differ from the registered plan")
    process_total = 0.0
    timing_complete = True
    for entry in entries:
        seconds = entry.get("seconds")
        if not _finite(seconds) or not 0 < float(seconds) <= C.PER_STATE_TIMEOUT_S:
            failures.append("missing, nonfinite, or over-budget per-state process wall time")
            timing_complete = False
        else:
            process_total += float(seconds)
    if not timing_complete or not _finite(index.get("solver_process_wall_seconds_total")) or index.get("solver_process_wall_seconds_total") != process_total or process_total > C.SOLVER_WALL_TIME_CAP_S:
        failures.append("registered aggregate solver process wall-time budget or index sum failed")
    summary_wall_total = 0.0
    rows = {row["name"]: row for row in inventory["states"]}
    entry_by_name = {entry.get("name"): entry for entry in entries if isinstance(entry, dict)}
    for name in MINIMUM_STATE_NAMES:
        row, directory = rows[name], out / "states" / name
        try:
            csv = directory / "flow_32.forces.csv"
            summary_path = directory / "flow_32.summary.json"
            marker = directory / "W4_JOB_DONE"
            if not (csv.is_file() and summary_path.is_file() and marker.is_file()):
                raise ValueError("force CSV, summary, or W4_JOB_DONE is missing")
            entry = entry_by_name.get(name)
            if not isinstance(entry, dict) or entry.get("forces_csv_sha256") != sha256(csv):
                raise ValueError("force CSV differs from the kernel index")
            summary = jload(summary_path)
            for key, want in (
                ("phi_fortran_sha256", row["phi_fortran_order_sha256"]),
                ("phi_c_order_sha256", row["phi_c_order_sha256"]),
                ("state_sha256", row["state_sha256"]),
                ("state_npz_sha256", row["npz_sha256"]),
                ("gpu_name", "Tesla T4"),
                ("gpu_uuid", selected_gpu["uuid"] if selected_gpu is not None else None),
                ("case_id", "flow_32"),
            ):
                if summary.get(key) != want:
                    raise ValueError(f"summary {key} differs from the frozen state/runtime")
            if summary.get("flow_dims") != [200, 96, 72] or not _finite(summary.get("flow_spacing_m")) or summary["flow_spacing_m"] != 0.025:
                raise ValueError("summary flow_32 dimensions or spacing mismatch")
            margin, margin_gate = summary.get("phi_margin_m"), summary.get("phi_margin_gate_m")
            if not _finite(margin) or abs(float(margin) - float(row["zero_level_margin_m"])) > float(row["margin_tolerance_m"]) or margin_gate != 0.15:
                raise ValueError("summary SDF margin differs from the registered value")
            t_end = summary.get("t_end_reached")
            if (summary.get("finite_u") is not True or summary.get("finite_p") is not True or summary.get("finite_forces") is not True
                    or not _finite(t_end) or float(t_end) < MIN_T_END or type(summary.get("julia_threads")) is not int or summary.get("julia_threads") != 1):
                raise ValueError("summary fields, horizon, or thread count failed")
            wall_seconds = summary.get("wall_seconds")
            if not _finite(wall_seconds) or not 0 < float(wall_seconds) <= C.PER_STATE_TIMEOUT_S:
                raise ValueError("Julia summary wall time is missing, nonfinite, or over budget")
            summary_wall_total += float(wall_seconds)
            host = recompute_force_n(csv, criteria)
            measured = {}
            for response, summary_key in (("drag", "drag_time_weighted_n"), ("downforce", "downforce_time_weighted_n")):
                saved = summary.get(summary_key)
                if not _finite(saved) or not _finite(host[f"{response}_n"]) or _rel(float(host[f"{response}_n"]), float(saved)) > SUMMARY_REL:
                    raise ValueError(f"host and Julia {response} measurements differ or are non-finite")
                measured[f"{response}_n"] = float(host[f"{response}_n"])
            states[name] = {
                **measured,
                "forces_csv_sha256": entry["forces_csv_sha256"],
                "summary_sha256": sha256(summary_path),
                "solver_process_wall_seconds": float(entry["seconds"]),
                "julia_summary_wall_seconds": float(wall_seconds),
                "geometry_gates": row["geometry_gates"],
            }
        except Exception as exc:  # noqa: BLE001
            failures.append(f"state {name}: {type(exc).__name__}: {exc}")
    if summary_wall_total > C.SOLVER_WALL_TIME_CAP_S:
        failures.append("Julia summary aggregate solver wall-time budget exceeded")
    baseline = states.get("step01__baseline")
    if baseline is not None:
        if baseline["forces_csv_sha256"] != baseline_ref.get("forces_csv_sha256"):
            failures.append("baseline force CSV is not byte-identical to retained W4 flow_32")
        for q in ("drag_n", "downforce_n"):
            want = baseline_ref.get("host_recomputed_n", {}).get(q)
            if not _finite(want) or _rel(baseline[q], float(want)) > BASELINE_REL:
                failures.append(f"baseline {q} differs from retained W4 host force")
    return failures, states


def _flow32_measurements(states: dict[str, Any]) -> dict[str, dict[str, Any]]:
    baseline = states["step01__baseline"]
    results = {}
    for direction in C.BASIS:
        plus_name = f"step01__{direction}__s2.5mm__plus"
        minus_name = f"step01__{direction}__s2.5mm__minus"
        results[direction] = {}
        for quantity in C.RESPONSES:
            response_key = f"{quantity}_n"
            results[direction][quantity] = C.secant_sample(
                baseline[response_key], states[plus_name][response_key], states[minus_name][response_key]
            )
    return results


def _coefficient_mapping(coefficients: list[float], direction_arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    vec = np.asarray(coefficients, dtype=np.float64)
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return {"m_max_abs_sum": None, "per_unit_step_basis_coefficients": None, "coefficient_unit_vector": [0.0] * 4}
    mapping = {name: float(value) for name, value in zip(C.BASIS, vec)}
    _, info = lowdim01_states.coefficient_direction(mapping, direction_arrays)
    c = np.asarray([info["coefficient_unit_vector"][name] for name in C.BASIS], dtype=np.float64)
    return {
        "m_max_abs_sum": float(info["m_max_abs_sum"]),
        "coefficient_unit_vector": c.tolist(),
        "per_unit_step_basis_coefficients": [float(info["per_unit_step_basis_coefficients"][name]) for name in C.BASIS],
    }


def _proposal_predictions(proposals: dict[str, Any], lift: np.ndarray, drag: np.ndarray, direction_arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    results: dict[str, Any] = {}

    def describe(label: str, solution: dict[str, Any], robust: bool, grid_only: str | None = None) -> dict[str, Any]:
        coefficients = np.asarray(solution["coefficient_vector"], dtype=np.float64)
        scale = _coefficient_mapping(coefficients.tolist(), direction_arrays)
        c = np.asarray(scale["coefficient_unit_vector"], dtype=np.float64)
        m = scale["m_max_abs_sum"]
        per_grid = {}
        for i, grid in enumerate(C.GRIDS):
            if grid_only is not None and grid != grid_only:
                continue
            lift_slope = float(np.dot(lift[i], c))
            drag_slope = float(np.dot(drag[i], c))
            l1 = float(np.linalg.norm(c, ord=1))
            factor = C.PROPOSAL_STEP_M / m if m else None
            per_grid[grid] = {
                "raw_downforce_slope_n_per_m": lift_slope,
                "raw_drag_slope_n_per_m": drag_slope,
                "raw_downforce_prediction_at_1p25mm_n": lift_slope * factor if factor is not None else None,
                "raw_drag_prediction_at_1p25mm_n": drag_slope * factor if factor is not None else None,
                "l1_robust_downforce_lower_slope_n_per_m": lift_slope - C.UNCERTAINTY_N_PER_M * l1,
                "l1_robust_drag_upper_slope_n_per_m": drag_slope + C.UNCERTAINTY_N_PER_M * l1,
                "l1_robust_downforce_lower_prediction_at_1p25mm_n": (lift_slope - C.UNCERTAINTY_N_PER_M * l1) * factor if factor is not None else None,
                "l1_robust_drag_upper_prediction_at_1p25mm_n": (drag_slope + C.UNCERTAINTY_N_PER_M * l1) * factor if factor is not None else None,
            }
        return {
            "source_problem": label,
            "t_star_n_per_m": solution["t_star_n_per_m"],
            "coefficient_vector": c.tolist(),
            "m_max_abs_sum_from_actual_four_direction_arrays": m,
            "per_unit_step_basis_coefficients_c_over_m": scale["per_unit_step_basis_coefficients"],
            "basis_coefficients_at_1p25mm": [float(x * C.PROPOSAL_STEP_M) for x in scale["per_unit_step_basis_coefficients"]] if m else None,
            "per_grid": per_grid,
        }

    results["main_cross_grid"] = describe("main_cross_grid", proposals["main_cross_grid"], False)
    results["robust_cross_grid"] = describe("robust_cross_grid", proposals["robust_cross_grid"], True)
    results["single_grid_references"] = {
        grid: {
            key: describe(f"{grid}_{key}", proposals["single_grid_references"][grid][key], key == "robust", grid)
            for key in ("main", "robust")
        }
        for grid in C.GRIDS
    }
    return results


def _lowdim01_proposal_predictions(
    lowdim01_inventory: dict[str, Any],
    flow24: dict[str, Any],
    flow32: dict[str, Any],
    direction_arrays: dict[str, np.ndarray],
) -> dict[str, Any]:
    proposal = lowdim01_inventory.get("proposal", {})
    if proposal.get("file") != FILE_PATHS["lowdim01_proposal_direction"]:
        raise ValueError("LOWDIM-01 proposal path differs from the frozen proposal direction")
    proposal_path = ROOT / FILE_PATHS["lowdim01_proposal_direction"]
    proposal_sha = proposal.get("sha256_fortran_raw")
    if not _valid_sha(proposal_sha) or sha256(proposal_path) != proposal_sha:
        raise ValueError("LOWDIM-01 proposal direction hash differs from its inventory")
    values = lowdim01_inventory.get("coefficient_gradient", {}).get("values", {})
    gradient: dict[str, float] = {}
    for name in C.BASIS:
        value = values.get(name, {}).get("g_sec_n_per_m")
        if not _finite(value):
            raise ValueError(f"LOWDIM-01 {name} gradient is missing or non-finite")
        gradient[name] = float(value)
    direction, info = lowdim01_states.coefficient_direction(gradient, direction_arrays)
    if step01_states.to_raw(direction) != proposal_path.read_bytes():
        raise ValueError("LOWDIM-01 direction does not reproduce from its frozen coefficient gradient")
    coefficients = np.asarray([info["coefficient_unit_vector"][name] for name in C.BASIS], dtype=np.float64)
    recorded_coefficients_raw = [proposal.get("coefficient_unit_vector", {}).get(name) for name in C.BASIS]
    if not all(_finite(value) for value in recorded_coefficients_raw):
        raise ValueError("LOWDIM-01 coefficient vector is missing or non-finite")
    recorded_coefficients = np.asarray(recorded_coefficients_raw, dtype=np.float64)
    if recorded_coefficients.shape != (4,) or not np.allclose(coefficients, recorded_coefficients, rtol=0.0, atol=1.0e-12):
        raise ValueError("LOWDIM-01 coefficient vector differs from its frozen inventory")
    m = float(info["m_max_abs_sum"])
    recorded_m = proposal.get("m_max_abs_sum")
    if not _finite(recorded_m) or abs(m - float(recorded_m)) > 1.0e-12 * max(1.0, abs(m)):
        raise ValueError("LOWDIM-01 spatial normalization differs from its frozen inventory")
    result: dict[str, Any] = {
        "source": "frozen LOWDIM-01 proposal, reproduced from its STEP-01 coefficient secants and the four raw directions",
        "proposal_sha256": proposal_sha,
        "coefficient_unit_vector": coefficients.tolist(),
        "m_max_abs_sum_from_actual_four_direction_arrays": m,
        "basis_coefficients_per_m_of_max_abs_phi_step": [float(x / m) for x in coefficients],
        "step_at_1p25mm_m": C.PROPOSAL_STEP_M,
        "per_grid": {},
    }
    for grid, secants in ((C.GRIDS[0], flow24), (C.GRIDS[1], flow32)):
        lift = np.asarray([secants[name]["downforce"]["g_sec_n_per_m"] for name in C.BASIS], dtype=np.float64)
        drag = np.asarray([secants[name]["drag"]["g_sec_n_per_m"] for name in C.BASIS], dtype=np.float64)
        result["per_grid"][grid] = {
            "raw_downforce_slope_n_per_m": float(np.dot(lift, coefficients)),
            "raw_drag_slope_n_per_m": float(np.dot(drag, coefficients)),
            "raw_downforce_prediction_at_1p25mm_n": float(np.dot(lift, coefficients) * C.PROPOSAL_STEP_M / m),
            "raw_drag_prediction_at_1p25mm_n": float(np.dot(drag, coefficients) * C.PROPOSAL_STEP_M / m),
            "basis_downforce_components_resolved": [bool(secants[name]["downforce"]["resolved"]) for name in C.BASIS],
            "basis_drag_components_resolved": [bool(secants[name]["drag"]["resolved"]) for name in C.BASIS],
            "interpretation": "raw finite-step linear prediction; unresolved basis component signs remain unqualified",
        }
    return result


def _proposal_verdict(proposals: dict[str, Any], predictions: dict[str, Any]) -> dict[str, Any]:
    main_t = float(proposals["main_cross_grid"]["t_star_n_per_m"])
    robust_t = float(proposals["robust_cross_grid"]["t_star_n_per_m"])
    reasons = []
    if main_t <= C.OPTIMUM_ATOL:
        reasons.append("main_t_star_not_positive_beyond_numeric_tolerance")
    if robust_t <= C.OPTIMUM_ATOL:
        reasons.append("robust_t_star_not_positive_beyond_numeric_tolerance")
    tested = {}
    for family in ("main_cross_grid", "robust_cross_grid"):
        for grid in C.GRIDS:
            field = "raw_downforce_prediction_at_1p25mm_n" if family == "main_cross_grid" else "l1_robust_downforce_lower_prediction_at_1p25mm_n"
            value = predictions[family]["per_grid"][grid][field]
            tested[f"{family}|{grid}"] = value
            if value is None or value < C.MIN_PREDICTED_DOWNFORCE_N:
                reasons.append(f"{family}_{grid}_prediction_below_3e-5_N")
    feasible = not reasons
    return {
        "verdict": "FEASIBLE_CONE_FOUND" if feasible else "NO_FEASIBLE_CONE_IN_4D",
        "main_t_star_n_per_m": main_t,
        "robust_t_star_n_per_m": robust_t,
        "numeric_positive_threshold_n_per_m": C.OPTIMUM_ATOL,
        "minimum_1p25mm_downforce_prediction_n": C.MIN_PREDICTED_DOWNFORCE_N,
        "gain_gate_semantics": "main raw prediction; sensitivity L1-robust lower-bound prediction",
        "predictions_tested_n": tested,
        "reasons": reasons,
        "descriptive_only": True,
        "no_cfd_authorized": True,
    }


def analyze(
    out: Path,
    freeze: Any,
    inventory: Any | None = None,
    formal: Any | None = None,
    step01_analysis: Any | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "kind": "grid01_cross_grid_secant_analysis",
        "selected_delta": None,
        "grad03_verdict": None,
        "fd08_verdict_unchanged": True,
        "no_gradient_claim": True,
        "not_grid_converged": True,
        "not_opt01": True,
        "reinitialization": "none",
        "qualification_flags": {name: False for name in FLAGS},
        "shape_update_allowed": False,
        "evidence_class": "bounded_cross_grid_finite_step_observation",
    }
    try:
        inventory = inventory if inventory is not None else jload(EVIDENCE / "inventory.json")
        formal = formal if formal is not None else jload(FORMAL)
        step01_analysis = step01_analysis if step01_analysis is not None else jload(STEP01_ANALYSIS)
        lowdim01_inventory = jload(ROOT / FILE_PATHS["lowdim01_inventory"])
        step01_inventory = jload(STEP01_INVENTORY)
    except Exception as exc:  # noqa: BLE001
        incomplete = _incomplete([f"registration input missing or malformed: {type(exc).__name__}: {exc}"])
        report.update(incomplete)
        return report
    try:
        failures = _validate_freeze(freeze, inventory, formal, step01_analysis)
    except Exception as exc:  # noqa: BLE001
        failures = [f"freeze validation failed closed: {type(exc).__name__}: {exc}"]
    try:
        failures.extend(_check_inventory(inventory, step01_inventory, step01_analysis))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"inventory validation failed closed: {type(exc).__name__}: {exc}")
    try:
        if freeze.get("file_hashes", {}).get("formal_criteria") != sha256(FORMAL):
            failures.append("formal criteria hash differs from freeze")
        if freeze.get("file_hashes", {}).get("step01_analysis") != sha256(STEP01_ANALYSIS):
            failures.append("STEP-01 analysis hash differs from freeze")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"freeze reference validation failed closed: {type(exc).__name__}: {exc}")
    if failures:
        incomplete = _incomplete(failures)
        incomplete["provenance"] = {"freeze_sha256": _safe_json_sha(freeze) if isinstance(freeze, dict) else None}
        report.update(incomplete)
        return report
    try:
        criteria = flow32_criteria(formal)
        kernel_failures, states = _check_kernel(Path(out), freeze, inventory, criteria)
        failures.extend(kernel_failures)
    except Exception as exc:  # noqa: BLE001
        failures = [f"kernel verification failed closed: {type(exc).__name__}: {exc}"]
    if failures:
        incomplete = _incomplete(failures)
        incomplete["provenance"] = {
            "freeze_sha256": _safe_json_sha(freeze) if isinstance(freeze, dict) else None,
            "inventory_sha256": _safe_json_sha(inventory) if isinstance(inventory, dict) else None,
        }
        report.update(incomplete)
        return report
    try:
        flow32 = _flow32_measurements(states)
        flow24 = inventory["flow24_reference_step01"]["secants"]
        comparisons: dict[str, Any] = {}
        for direction in C.BASIS:
            comparisons[direction] = {
                quantity: C.component_comparison(flow24[direction][quantity], flow32[direction][quantity])
                for quantity in C.RESPONSES
            }
        vectors = {
            "downforce": {
                C.GRIDS[0]: [flow24[name]["downforce"]["g_sec_n_per_m"] for name in C.BASIS],
                C.GRIDS[1]: [flow32[name]["downforce"]["g_sec_n_per_m"] for name in C.BASIS],
            },
            "drag": {
                C.GRIDS[0]: [flow24[name]["drag"]["g_sec_n_per_m"] for name in C.BASIS],
                C.GRIDS[1]: [flow32[name]["drag"]["g_sec_n_per_m"] for name in C.BASIS],
            },
        }
        coefficient_comparison = {
            quantity: C.cosine_and_norm_ratio(vectors[quantity][C.GRIDS[0]], vectors[quantity][C.GRIDS[1]])
            for quantity in C.RESPONSES
        }
        lift = np.asarray([vectors["downforce"][grid] for grid in C.GRIDS], dtype=np.float64)
        drag = np.asarray([vectors["drag"][grid] for grid in C.GRIDS], dtype=np.float64)
        proposals = C.solve_cross_grid_proposals(lift, drag)
        direction_arrays = {
            name: step01_states.read_f4(ROOT / inventory["directions"][name]["path"])
            for name in C.BASIS
        }
        predictions = _proposal_predictions(proposals, lift, drag, direction_arrays)
        lowdim01_predictions = _lowdim01_proposal_predictions(lowdim01_inventory, flow24, flow32, direction_arrays)
        proposal_decision = _proposal_verdict(proposals, predictions)
        report.update({
            "verdict": "GRID01_SECANT_RECORDED",
            "integrity": {"pass": True, "failures": []},
            "measurements": {
                "flow24_from_frozen_step01": flow24,
                "flow32_host_recomputed": flow32,
                "state_forces_n": states,
                "geometry_gates_by_state": {name: row["geometry_gates"] for name, row in ((r["name"], r) for r in inventory["states"])},
            },
            "component_comparisons": comparisons,
            "coefficient_space_comparison_raw_finite_step_vectors": coefficient_comparison,
            "coefficient_vectors_n_per_m": vectors,
            "solver_free_proposals": proposals,
            "proposal_predictions_with_actual_m": predictions,
            "lowdim01_proposal_predictions_with_actual_m": lowdim01_predictions,
            "proposal_verdict": proposal_decision,
            "flow32_noise_evidence": "not measured; the 3e-5 N threshold is the frozen nominal flow24-derived floor",
            "interpretation": "Finite-step secant observation only. Unresolved numeric secants remain in the coefficient vectors but their component signs are not interpreted. The convex proposals are descriptive first-order hypotheses; actual primal evaluation remains authoritative.",
            "provenance": {
                "freeze_sha256": _json_sha(freeze),
                "analyzer_sha256": sha256(Path(__file__)),
                "source_commit": freeze["source_commit"],
                "kernel_manifest_sha256": sha256(Path(out) / "output_manifest.json"),
                "step01_analysis_sha256": sha256(STEP01_ANALYSIS),
            },
        })
    except Exception as exc:  # noqa: BLE001
        incomplete = _incomplete([f"analysis computation failed closed: {type(exc).__name__}: {exc}"])
        report.update(incomplete)
    return report


def clean(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-dir", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--write", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        freeze_bytes = args.freeze.read_bytes()
        sidecar = args.freeze.with_name(args.freeze.name + ".sha256")
        if not sidecar.is_file():
            raise ValueError("freeze SHA-256 sidecar is missing")
        actual_sha = hashlib.sha256(freeze_bytes).hexdigest()
        if sidecar.read_text().strip() != actual_sha:
            raise ValueError("freeze SHA-256 sidecar mismatch")
        freeze = json.loads(freeze_bytes)
    except Exception as exc:  # noqa: BLE001
        freeze = None
        print(f"invalid freeze: {type(exc).__name__}: {exc}", file=sys.stderr)
    report = analyze(args.kernel_dir, freeze)
    if args.check:
        print(json.dumps(clean({"integrity": report["integrity"], "verdict": report["verdict"]}), indent=2, sort_keys=True, allow_nan=False))
        if report["verdict"] == "GRID01_SECANT_INCOMPLETE":
            raise SystemExit(3)
        return
    if args.write is None:
        raise SystemExit("--write is required unless --check")
    if args.write.exists():
        raise SystemExit("refusing to overwrite an existing GRID-01 analysis")
    data = json.dumps(clean(report), indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(report["verdict"], hashlib.sha256(data.encode()).hexdigest())
    if report["verdict"] == "GRID01_SECANT_INCOMPLETE":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
