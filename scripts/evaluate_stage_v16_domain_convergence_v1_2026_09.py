#!/usr/bin/env python3
"""Evaluate the pre-registered v2-v3 same-profile domain pair."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PARENT_OUTCOME = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json"
CHILD_OUTCOME = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_v1_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_v1_run_manifest_2026_09.json"
PAIR_OUTCOME = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path) -> dict[str, str]:
    return {"path": _rel(path), "sha256": _sha256(path)}


def _gate(name: str, qualified: bool, observed: Any, threshold: Any, rule: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if qualified else "fail",
        "qualified": bool(qualified),
        "observed": observed,
        "threshold": threshold,
        "rule": rule,
    }


def evaluate() -> dict[str, Any]:
    if PAIR_OUTCOME.exists():
        raise SystemExit(f"pair result already exists; refuse overwrite: {_rel(PAIR_OUTCOME)}")
    parent = _load(PARENT_OUTCOME)
    child = _load(CHILD_OUTCOME)
    run_manifest = _load(RUN_MANIFEST)
    profile = run_manifest.get("domain_convergence_profile", {})
    downforce_limit = float(profile["downforce_absolute_delta_threshold"])
    cd_limit = float(profile["cd_relative_delta_threshold"])

    parent_run_manifest_path = ROOT / run_manifest["parent_v2"]["run_manifest"]["path"]
    parent_run_manifest = _load(parent_run_manifest_path)
    parent_run_manifest_sha = _sha256(parent_run_manifest_path)
    parent_physical = parent_run_manifest["canonical_inputs"]["physical_profile_sha256"]
    child_physical = run_manifest["canonical_inputs"]["physical_profile_sha256"]
    parent_candidate = parent_run_manifest["canonical_inputs"]["candidate"]["sha256"]
    child_candidate = run_manifest["canonical_inputs"]["candidate"]["sha256"]

    parent_force = parent["qualification"]["record"]["force_stationarity"]["responses"]
    child_force = child["qualification"]["record"]["force_stationarity"]["responses"]
    parent_cd = float(parent_force["Cd"]["mean"])
    child_cd = float(child_force["Cd"]["mean"])
    parent_downforce = float(parent_force["downforce"]["mean"])
    child_downforce = float(child_force["downforce"]["mean"])
    delta_downforce = child_downforce - parent_downforce
    delta_cd = child_cd - parent_cd
    relative_cd_delta = abs(delta_cd) / abs(parent_cd)

    gates = {
        "parent_physical_profile_qualified": _gate(
            "parent_physical_profile_qualified",
            parent.get("status") == "pass" and parent.get("qualified") is True,
            {"status": parent.get("status"), "qualified": parent.get("qualified")},
            "pass",
            "parent outcome must be a qualified physical-profile run",
        ),
        "child_physical_profile_qualified": _gate(
            "child_physical_profile_qualified",
            child.get("status") == "pass" and child.get("qualified") is True,
            {"status": child.get("status"), "qualified": child.get("qualified")},
            "pass",
            "child outcome must be a qualified physical-profile run",
        ),
        "parent_run_manifest_identity": _gate(
            "parent_run_manifest_identity",
            run_manifest["parent_v2"]["run_manifest"]["sha256"] == parent_run_manifest_sha
            and parent["run_manifest"]["sha256"] == parent_run_manifest_sha,
            parent_run_manifest_sha,
            run_manifest["parent_v2"]["run_manifest"]["sha256"],
            "parent outcome and registered parent manifest SHA must agree",
        ),
        "same_physical_profile": _gate(
            "same_physical_profile",
            parent_physical == child_physical,
            {"parent": parent_physical, "child": child_physical},
            parent_physical,
            "physical-profile SHA must be identical",
        ),
        "same_candidate": _gate(
            "same_candidate",
            parent_candidate == child_candidate,
            {"parent": parent_candidate, "child": child_candidate},
            parent_candidate,
            "candidate STL SHA must be identical",
        ),
        "only_domain_bounds_changed": _gate(
            "only_domain_bounds_changed",
            bool(run_manifest["domain_factor"].get("only_domain_bounds_changed")),
            run_manifest["domain_factor"],
            True,
            "registered ProblemSpecs may differ only in grid domain bounds",
        ),
        "downforce_absolute_delta": _gate(
            "downforce_absolute_delta",
            abs(delta_downforce) <= downforce_limit,
            {"parent": parent_downforce, "child": child_downforce, "delta": delta_downforce},
            downforce_limit,
            "abs(child downforce - parent downforce) <= threshold",
        ),
        "cd_relative_delta": _gate(
            "cd_relative_delta",
            relative_cd_delta <= cd_limit,
            {"parent": parent_cd, "child": child_cd, "delta": delta_cd, "relative": relative_cd_delta},
            cd_limit,
            "abs(child Cd - parent Cd) / abs(parent Cd) <= threshold",
        ),
    }
    qualified = all(gate["qualified"] for gate in gates.values())
    outcome = {
        "kind": "stage_v_v16_physical_profile_domain_convergence_result",
        "schema_version": 1,
        "evidence_class": "qualification_result",
        "status": "pass" if qualified else "fail",
        "qualified": qualified,
        "question": run_manifest["question"],
        "registered_thresholds": profile,
        "pair": {
            "parent_outcome": _artifact(PARENT_OUTCOME),
            "child_outcome": _artifact(CHILD_OUTCOME),
            "run_manifest": _artifact(RUN_MANIFEST),
            "parent_domain": parent["domain_factor"],
            "child_domain": child["domain_factor"],
            "physical_profile_sha256": child_physical,
            "candidate_sha256": child_candidate,
        },
        "metrics": {
            "parent_cd_mean": parent_cd,
            "child_cd_mean": child_cd,
            "cd_delta": delta_cd,
            "cd_relative_delta": relative_cd_delta,
            "parent_downforce_mean": parent_downforce,
            "child_downforce_mean": child_downforce,
            "downforce_delta": delta_downforce,
        },
        "gates": gates,
        "analysis_script": _artifact(Path(__file__)),
        "claims_not_supported": [
            "absolute or grid-independent downforce",
            "high-Reynolds-number or full-vehicle FSAE qualification",
            "Stage S reduced-basis FD qualification",
            "a shape update or optimization campaign",
        ],
        "next_gate": (
            "freeze the qualified Stage V reference profile and register the K=16 reduced-basis FD preflight"
            if qualified
            else "remain blocked; resolve the failed same-profile convergence gate before Stage S"
        ),
    }
    payload = json.dumps(outcome, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    PAIR_OUTCOME.parent.mkdir(parents=True, exist_ok=True)
    PAIR_OUTCOME.write_text(payload, encoding="utf-8", newline="\n")
    digest = _sha256(PAIR_OUTCOME)
    PAIR_OUTCOME.with_suffix(PAIR_OUTCOME.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": outcome["status"], "qualified": qualified, "outcome": _rel(PAIR_OUTCOME), "outcome_sha256": digest}, ensure_ascii=False, sort_keys=True))
    return outcome


if __name__ == "__main__":
    evaluate()
