#!/usr/bin/env python3
"""Write GRID-01's immutable pre-measurement freeze after source review."""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import analyze_grid01 as analyzer  # noqa: E402
import build_grid01_kernel as kernel  # noqa: E402
from cfd_sdf import grid01_contract as C  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/grid01_cross_grid_secant_2026_10_09"
EXPECTED_PARENT = "32e64715dc20a9ac2dd78e3c011bcb48f311b98e"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-grid01-a"
MAX_IDENTITY_AGE_S = 24 * 60 * 60


def sha(path: Path) -> str:
    return analyzer.sha256(path)


def _require_listing_confirmation(record: dict[str, Any], witness: Any, reference: datetime.datetime) -> None:
    """Require complete authenticated owner lists, not an inference from HTTP 403."""
    if not isinstance(witness, dict) or witness.get("kind") != "grid01_authenticated_owned_listing_confirmation" or witness.get("owner") != record["owner"]:
        raise ValueError("missing authenticated owned-listing confirmation")
    captured = datetime.datetime.fromisoformat(str(witness.get("captured_utc", "")).replace("Z", "+00:00"))
    original = datetime.datetime.fromisoformat(record["captured_utc"].replace("Z", "+00:00"))
    if captured.tzinfo is None or captured < original or not 0 <= (reference - captured).total_seconds() <= MAX_IDENTITY_AGE_S:
        raise ValueError("authenticated listing confirmation is stale or not registration-time evidence")
    slug = KERNEL_ID.split("/", 1)[1]
    for kind, count_key in (("kernels", "owned_kernel_count"), ("datasets", "owned_dataset_count")):
        listing = witness.get("listings", {}).get(kind, {})
        rows = listing.get("rows")
        if listing.get("command") != [kind, "list", "-m", "--page-size", "200", "--format", "csv"] or type(listing.get("exit_code")) is not int or listing["exit_code"] != 0:
            raise ValueError(f"{kind} owned-listing command did not succeed")
        parsed = list(csv.DictReader(io.StringIO(listing.get("stdout", ""))))
        if not isinstance(rows, list) or parsed != rows or not 0 < len(rows) < 100 or len(rows) != record[count_key]:
            raise ValueError(f"{kind} owned listing is incomplete, truncated, or inconsistent")
        refs = [row.get("ref", "") for row in rows]
        if len(set(refs)) != len(refs) or any(not ref.startswith(record["owner"] + "/") for ref in refs):
            raise ValueError(f"{kind} listing has duplicate refs or a different authenticated owner")
        taken = {ref.split("/", 1)[1] for ref in refs}
        taken |= {re.sub(r"[^a-z0-9]+", "-", row.get("title", "").lower()).strip("-") for row in rows}
        if slug in taken:
            raise ValueError(f"{kind} complete owned listing contains a slug/title collision")
        control = witness.get("positive_controls", {}).get(kind, {})
        ref = control.get("ref")
        expected_command = [kind, "status", ref] if kind == "kernels" else [kind, "files", ref, "--format", "csv"]
        if ref not in refs or control.get("command") != expected_command or type(control.get("exit_code")) is not int or control["exit_code"] != 0 or not str(control.get("stdout", "")).strip():
            raise ValueError(f"{kind} existing-owned-item positive access control failed")
        if re.search(r"permission.*denied|403\s+client error|unauthorized|forbidden", str(control.get("stdout", "")) + str(control.get("stderr", "")), re.I):
            raise ValueError(f"{kind} positive access control reports an authorization error")


def _require_identity_free(record: Any, *, as_of: datetime.datetime | None = None, listing_confirmation: Any = None) -> None:
    if not isinstance(record, dict) or record.get("all_free") is not True:
        raise ValueError("Kaggle identity-free check is missing or does not report all_free")
    slug = KERNEL_ID.split("/", 1)[1]
    if record.get("kind") != "fd08_v2_kaggle_identity_free_check" or record.get("owner") != KERNEL_ID.split("/", 1)[0]:
        raise ValueError("identity-free check kind or owner mismatch")
    try:
        captured = datetime.datetime.fromisoformat(str(record.get("captured_utc", "")).replace("Z", "+00:00"))
        reference = as_of if as_of is not None else datetime.datetime.now(datetime.timezone.utc)
        age = (reference - captured).total_seconds()
    except (TypeError, ValueError) as exc:
        raise ValueError("identity-free check timestamp is missing or invalid") from exc
    if captured.tzinfo is None or age < 0.0 or age > MAX_IDENTITY_AGE_S:
        raise ValueError("identity-free check is stale or has a future timestamp")
    if record.get("intended_slugs") != [slug]:
        raise ValueError("identity-free check must contain exactly the GRID-01 kernel slug")
    for key in ("owned_kernel_count", "owned_dataset_count"):
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= 100:
            raise ValueError("identity-free check may have a missing or truncated Kaggle listing")
    if not isinstance(record.get("listed_slug_clashes"), dict):
        raise ValueError("identity-free check clash inventory is missing or malformed")
    if slug in record["listed_slug_clashes"]:
        raise ValueError("Kaggle kernel/dataset listing contains a slug collision")
    probes = record.get("status_probes", {}).get(slug, {})
    for kind in ("kernels", "datasets"):
        probe = probes.get(kind)
        if not isinstance(probe, dict) or type(probe.get("exit_code")) is not int or probe["exit_code"] == 0:
            raise ValueError(f"Kaggle {kind} status probe does not show the slug is absent")
        text = f"{probe.get('stdout', '')} {probe.get('stderr', '')}".lower()
        if not re.search(r"404|not found|does not exist|could not find", text):
            if not re.search(r"403|permission.*denied", text):
                raise ValueError(f"Kaggle {kind} status probe is an unknown failure, not confirmed absence")
            try:
                _require_listing_confirmation(record, listing_confirmation, reference)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Kaggle {kind} status probe is an unknown failure without authenticated absence evidence: {exc}") from exc


def require_identity_artifact(record: Any, root: Path = ROOT) -> None:
    path = root / analyzer.FILE_PATHS["identity_free_check"]
    sidecar = root / analyzer.FILE_PATHS["identity_free_check_sha256"]
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("identity-free check or its SHA-256 sidecar is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != sidecar.read_text().strip():
        raise ValueError("identity-free check SHA-256 sidecar mismatch")
    if json.loads(path.read_text()) != record:
        raise ValueError("freeze identity-free record differs from the authenticated artifact")


def load_listing_confirmation(root: Path = ROOT) -> dict[str, Any]:
    path = root / analyzer.FILE_PATHS["identity_listing_confirmation"]
    sidecar = root / analyzer.FILE_PATHS["identity_listing_confirmation_sha256"]
    if not path.is_file() or not sidecar.is_file() or sha(path) != sidecar.read_text().strip():
        raise ValueError("authenticated listing confirmation is missing or its SHA sidecar differs")
    return json.loads(path.read_text())


def contract_sections(inventory: dict[str, Any]) -> dict[str, Any]:
    """Return every deterministic freeze declaration from the inventory and code contract."""
    metadata = kernel.metadata()
    return {
        "runtime": {
            "kernel_id": KERNEL_ID,
            "slug": KERNEL_ID.split("/", 1)[1],
            "title": metadata["title"],
            "kernel": "a",
            "machine_shape": "NvidiaTeslaT4",
            "enable_gpu": True,
            "dataset_sources": [],
            "timeout_s": kernel.TIMEOUT_S,
            "per_state_timeout_s": C.PER_STATE_TIMEOUT_S,
            "solver_wall_time_cap_s": C.SOLVER_WALL_TIME_CAP_S,
            "gpu_probe_timeout_s": C.GPU_PROBE_TIMEOUT_S,
            "identity_absence_authority": "explicit not-found status, or complete authenticated owned listings with positive existing-resource access controls; missing-slug permission errors alone are not absence proof",
            "instantiate_timeout_s": 2400,
            "julia_threads": 1,
            "gpu_inventory_policy": "nonempty_all_visible_devices_must_be_tesla_t4",
            "selected_gpu_physical_index": 0,
            "cuda_device_order": "PCI_BUS_ID",
            "cuda_visible_devices": "0",
            "used_gpu_count": 1,
            "summary_uuid_field": "gpu_uuid",
            "summary_uuid_semantics": "configured UUID echo; independently observed CUDA singleton/default UUID in preflight under the identical environment used for all jobs",
        },
        "design": {
            "states": [row["name"] for row in inventory["states"]],
            "state_count": 9,
            "baseline_count": 1,
            "case": C.FLOW32_CASE["case_id"],
            "basis_order": list(C.BASIS),
            "signed_step_mm": [-2.5, 2.5],
            "reinitialization": "none",
            "job": "scripts/waterlily_lowdim02_flow32_job.jl (unchanged)",
            "baseline_byte_reference": inventory["flow32_baseline_reference"]["forces_csv_sha256"],
        },
        "measurement": inventory["measurement_contract"],
        "solver": {
            "solver_id": C.SOLVER_ID,
            "description": "Exact finite branch partition (active minimum-lift grid; plus all coefficient sign orthants for L1 sensitivity), exhaustive independent active-set enumeration up to dimension four, float64 KKT primal-dual certificate for every branch, and global maximum over every branch.",
            "epsilon_n_per_m": C.UNCERTAINTY_N_PER_M,
            "feasibility_atol": C.FEASIBILITY_ATOL,
            "dual_atol": C.DUAL_ATOL,
            "kkt_atol": C.KKT_ATOL,
            "optimum_atol_n_per_m": C.OPTIMUM_ATOL,
            "rank_atol": C.RANK_ATOL,
            "approximate_cone": False,
            "nonlinear_optimizer": None,
            "optimality_certificate": "All branch primal feasibility, dual feasibility, stationarity, complementarity, and primal/dual gaps are independently checked; the maximum branch dual bound proves the global optimum over the exhaustive partition.",
        },
        "rules": {
            "resolved_difference_strictly_greater_than_n": C.MIN_RESOLVED_N,
            "resolution_source": "10 times nominal flow_24 sigma0; flow_32 noise is not measured",
            "eta_even": "abs(R_plus+R_minus-2*R0)/abs(R_plus-R_minus); null only if denominator is exactly zero",
            "unresolved_policy": "retain finite numeric secant, set resolved false, do not infer or emit a component sign, never substitute zero for missing data",
            "sign_statuses": ["sign_preserved_resolved", "sign_flipped_resolved", "unresolved"],
            "proposal_positive_t_threshold_n_per_m": C.OPTIMUM_ATOL,
            "minimum_downforce_prediction_at_1p25mm_n": C.MIN_PREDICTED_DOWNFORCE_N,
            "feasible_cone_rule": "Main and sensitivity cross-grid t* both exceed the frozen numeric positivity threshold; main raw gain and sensitivity L1-robust lower-bound gain at 1.25 mm each meet the same minimum downforce increase on both grids.",
            "spatial_normalization": "For each coefficient vector independently, use lowdim01_states.coefficient_direction on the four pinned raw arrays and its actual m=max(abs(sum(c_i*d_i))); step coefficients are (s/m)c_i and force predictions are (g.c)s/m.",
            "flow24_authority": "STEP-01 step01_analysis.json rows[0] at step_mm=2.5; immutable source numbers copied, GRID-01 resolved flag and even_part_n rederived from copied R values",
        },
        "flow24_reference": inventory["flow24_reference_step01"],
        "flow32_baseline_reference": inventory["flow32_baseline_reference"],
        "known_before_run": {
            "prior_exploratory_flow24_secants_were_visible": True,
            "flow32_new_measurement_available_at_registration": False,
            "direction_and_thresholds_changed_after_exploration": False,
            "flow32_noise_measured": False,
        },
        "prohibitions": {
            "gradient_qualification": True,
            "grid_convergence_or_gci_claim": True,
            "physical_downforce_claim": True,
            "opt01_supersession": True,
            "qualification_flag_change": True,
            "fd08_verdict_change": True,
            "grad03_verdict": True,
            "selected_delta": True,
            "reinitialization": True,
            "basis_expansion": True,
            "ad_or_tangent": True,
            "actual_primal_line_search": True,
            "flow_grid_selection_for_first_optimization_step": True,
            "posthoc_threshold_or_state_change": True,
            "prohibit_new_experiment_issue_creation_without_user_decision": True,
            "prohibit_issue29_edits_in_grid01_branch": True,
        },
        "qualification_flags": {name: False for name in analyzer.FLAGS},
    }


def build(source_commit: str, parent: str) -> dict[str, Any]:
    inventory_path = EVIDENCE / "inventory.json"
    identity_path = EVIDENCE / "identity_free_check.json"
    inventory = json.loads(inventory_path.read_text())
    from build_grid01_inputs import build as rebuild_inventory
    if inventory != rebuild_inventory():
        raise ValueError("inventory differs from full immutable-input rederivation")
    identity_free = json.loads(identity_path.read_text())
    require_identity_artifact(identity_free)
    _require_identity_free(identity_free, listing_confirmation=load_listing_confirmation(ROOT))
    if parent != EXPECTED_PARENT:
        raise ValueError(f"parent must be the exact integration checkpoint {EXPECTED_PARENT}")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a full lowercase Git SHA-1")
    metadata_path = ROOT / analyzer.FILE_PATHS["kernel_metadata"]
    metadata = json.loads(metadata_path.read_text())
    if metadata != kernel.metadata():
        raise ValueError("kernel metadata does not exactly match kernel.metadata()")
    runner_path = ROOT / analyzer.FILE_PATHS["rendered_runner"]
    if runner_path.read_text() != kernel.render(source_commit):
        raise ValueError("rendered runner does not exactly match kernel.render(source_commit)")
    file_hashes = {name: analyzer.frozen_path_sha(name, ROOT / relpath, source_commit, root=ROOT) for name, relpath in analyzer.FILE_PATHS.items()}
    file_hashes["inventory_canonical_json"] = hashlib.sha256((json.dumps(inventory, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()).hexdigest()
    source_failures = analyzer._source_commit_failures(source_commit, file_hashes, root=ROOT)
    if source_failures:
        raise ValueError("source commit does not contain the reviewed frozen inputs: " + "; ".join(source_failures))
    if file_hashes["inventory_canonical_json"] != file_hashes["inventory"]:
        raise ValueError("inventory bytes are not canonical JSON")
    pins = kernel.pins()
    if pins.get("docs/evidence/grid01_cross_grid_secant_2026_10_09/inventory.json") != file_hashes["inventory"]:
        raise ValueError("kernel inventory pin differs from the source inventory")
    return {
        "kind": "grid01_cross_grid_secant_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": file_hashes,
        "pins": pins,
        "identity_free_check": identity_free,
        **contract_sections(inventory),
        "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def check_git(source_commit: str) -> None:
    tracked = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
    if tracked:
        raise SystemExit("tracked files have uncommitted changes; freeze only committed reviewed source")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", source_commit, "HEAD"]).returncode:
        raise SystemExit("the source commit is not an ancestor of HEAD")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--parent", required=True)
    args = parser.parse_args()
    check_git(args.source_commit)
    out = EVIDENCE / "prerun_freeze.json"
    if out.exists():
        raise SystemExit("refusing to overwrite the GRID-01 freeze")
    data = (json.dumps(build(args.source_commit, args.parent), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    out.write_bytes(data)
    out.with_name(out.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
