#!/usr/bin/env python3
"""Supersede unrun AMEND1 packaging; copy its scientific contract and state bytes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from register_fd08_v2_formal import ROOT, R6_PARENT, verified_json, require
from register_fd08_v2_r6 import digest, load_budget_evidence

PARENT = ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend1"
PARENT_SHA = "857c21231eb48708daba784318445c43d115dca48567dfd3378c3ba177bd57fe"
PARENT_SOURCE = "30aa20a6891ccabefaa2ef6d41a2e2b5e26701b5"
ROUND_ID = "fd08_v2_formal_2026_10_07_amend2"
CRITERIA_ID = "FD08-V2-FORMAL-AMEND2-2026-10-07"
DATASET_ID = "ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend2"
KERNEL_ID = DATASET_ID
EVIDENCE = ROOT / "docs/evidence" / ROUND_ID
DOCUMENT = ROOT / "docs/issues/46_fd08_v2_formal_amend2_runner_schema_2026_10_07.md"
IDENTITY_FIELDS = {"criteria_id", "round_id", "kernel_id", "input_dataset_id", "source_commit",
                   "source_inputs", "formal_preregistration_amendment", "supersession",
                   "budget_feasibility", "dataset_files", "preflight", "artifact_paths"}


def blob(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def scientific_content(criteria):
    return {k: v for k, v in criteria.items() if k not in IDENTITY_FIELDS}


def read_parent():
    parent, parent_sha = verified_json(PARENT / "formal_criteria.json")
    require(parent_sha == PARENT_SHA and parent["source_commit"] == PARENT_SOURCE,
            "AMEND1 immutable identity mismatch")
    stopped, _ = verified_json(PARENT / "campaign_stop.json")
    failure, failure_sha = verified_json(PARENT / "registration_host_verification.json")
    require(stopped["campaign_status"] == "BLOCKED_INFRASTRUCTURE"
            and failure["exception_type"] == "KeyError"
            and failure["exception_message"] == "'geometry_reject_gates'",
            "AMEND1 blocker identity mismatch")
    for evidence in (stopped, failure):
        require(evidence["formal_solver_executed"] is False
                and evidence["formal_analyzer_executed"] is False,
                "AMEND1 has scientific observations/execution")
    require(stopped["formal_observation_count"] == 0 and failure["formal_response_observed"] is False,
            "supersession requires zero prior formal observations")
    require({k: parent["calibration_binding"][k] for k in R6_PARENT} == R6_PARENT
            and parent["calibration_binding"]["verdict"] == "PASS"
            and parent["calibration_binding"]["analysis_runs"] == 1,
            "immutable R6 provenance mismatch")
    for filename, field in (("r6_retry2_criteria.json", "criteria_sha256"),
                            ("r6_retry2_analysis.json", "result_sha256"),
                            ("r6_retry2_terminal_verification.json", "terminal_verification_sha256")):
        _, actual = verified_json(ROOT / "docs/evidence/fd08_v2_r6_2026_10_06" / filename)
        require(actual == R6_PARENT[field], "R6 immutable evidence changed")
    inventory, _ = verified_json(PARENT / "formal_registered_payload_inventory.json")
    archive = PARENT / "formal_registered_payload.tar.gz"
    require(digest(archive) == inventory["archive_sha256"], "AMEND1 payload archive SHA mismatch")
    with tarfile.open(archive, "r:gz") as tar:
        require(set(tar.getnames()) == set(inventory["files"]), "AMEND1 archive inventory mismatch")
        files = {}
        for member in tar.getmembers():
            require(member.isfile() and Path(member.name).name == member.name, "non-flat archive entry")
            data = tar.extractfile(member).read()
            require(hashlib.sha256(data).hexdigest() == inventory["files"][member.name],
                    "AMEND1 archive file SHA mismatch")
            files[member.name] = data
    require(hashlib.sha256(files["criteria.json"]).hexdigest() == PARENT_SHA,
            "AMEND1 archived criteria mismatch")
    require(all(hashlib.sha256(files[name]).hexdigest() == sh for name, sh in parent["dataset_files"].items()),
            "AMEND1 registered payload mismatch")
    return parent, files, failure_sha


def source_inventory(parent, commit):
    require(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)
            and commit not in (PARENT_SOURCE, R6_PARENT["source_commit"]), "new exact execution commit required")
    sources = copy.deepcopy(parent["source_inputs"])
    replacements = {
        "formal_registrar": "scripts/register_fd08_v2_formal_amend2.py",
        "kernel_metadata": "infra/kaggle/kernel_fd08_v2_formal_amend2/kernel-metadata.json",
        "formal_lineage_tests": "tests/test_fd08_v2_formal_amend2.py",
        "formal_amendment_document": DOCUMENT.relative_to(ROOT).as_posix(),
        "formal_lineage_review": f"docs/evidence/{ROUND_ID}/review_schema.json",
        "formal_scientific_review": f"docs/evidence/{ROUND_ID}/review_scientific.json",
    }
    for name, path in replacements.items():
        sources[name] = {"path": path, "sha256": digest(ROOT / path)}
    for name, path in {
        "amend1_registrar": "scripts/register_fd08_v2_formal.py",
        "runner_schema_tests": "tests/test_fd08_v2_runner_schema.py",
        "presolver_kernel_builder": "scripts/prepare_fd08_v2_presolver_kernel.py",
    }.items():
        sources[name] = {"path": path, "sha256": digest(ROOT / path)}
    sources["kernel_runner"]["sha256"] = digest(ROOT / sources["kernel_runner"]["path"])
    for name, entry in sources.items():
        committed = subprocess.check_output(["git", "show", f"{commit}:{entry['path']}"], cwd=ROOT)
        require(hashlib.sha256(committed).hexdigest() == entry["sha256"], f"source tree mismatch: {name}")
    return sources


def build_formal(args):
    parent, archived, failure_sha = read_parent()
    sources = source_inventory(parent, args.source_commit)
    reviews = {}
    for role, key in (("schema", "formal_lineage_review"), ("scientific", "formal_scientific_review")):
        report, report_sha = verified_json(ROOT / sources[key]["path"])
        require(report["verdict"] == "PASS" and report["scientific_contract_changed"] is False
                and report["runner_sha256"] == sources["kernel_runner"]["sha256"]
                and report["registrar_sha256"] == sources["formal_registrar"]["sha256"],
                "independent review does not accept exact AMEND2 source")
        reviews[role] = {"path": sources[key]["path"], "sha256": report_sha}
    budget, budget_sha = load_budget_evidence(args.budget_evidence, "formal", 3300, 5600)
    criteria = copy.deepcopy(parent)
    criteria.update(criteria_id=CRITERIA_ID, round_id=ROUND_ID, input_dataset_id=DATASET_ID,
                    kernel_id=KERNEL_ID, source_commit=args.source_commit, source_inputs=sources)
    criteria["supersession"] = {
        "supersedes_criteria_id": parent["criteria_id"], "supersedes_criteria_sha256": PARENT_SHA,
        "supersedes_source_commit": PARENT_SOURCE,
        "superseded_status": "REGISTERED_NOT_RUN_SUPERSEDED_INFRASTRUCTURE",
        "blocker_evidence_path": (PARENT / "registration_host_verification.json").relative_to(ROOT).as_posix(),
        "blocker_evidence_sha256": failure_sha,
        "reason": "shared runner expected geometry_reject_gates while formal schema preregistered geometry",
        "formal_observations_before_supersession": 0, "solver_started_before_supersession": False,
        "scientific_contract_changed": False,
    }
    criteria["formal_preregistration_amendment"] = {
        **parent["formal_preregistration_amendment"],
        "amendment": "Formal Infrastructure AMEND2 — Runner Schema Repair",
        "AMEND1_lineage": parent["formal_preregistration_amendment"],
        "amended_source_commit": args.source_commit,
        "amended_registrar_sha256": sources["formal_registrar"]["sha256"],
        "amended_runner_sha256": sources["kernel_runner"]["sha256"],
        "amendment_document_path": DOCUMENT.relative_to(ROOT).as_posix(),
        "amendment_document_sha256": digest(DOCUMENT), "independent_reviews": reviews,
        "scientific_contract_changed": False,
        "reason": "AMEND2 formal schema dispatch repair before any formal solver or observation",
    }
    criteria["budget_feasibility"] = {**parent["budget_feasibility"],
        **{key: budget[key] for key in ("captured_utc", "cli_version", "gpu_quota_remaining_hours",
                                       "platform_max_cpu_gpu_session_seconds", "status")},
        "evidence_sha256": budget_sha}
    files = {name: archived[name] for name in parent["dataset_files"]}
    files["kaggle_budget_preflight.json"] = args.budget_evidence.read_bytes()
    criteria["dataset_files"] = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    preflight, _ = verified_json(PARENT / "formal_preflight.json")
    preflight = {**preflight, "AMEND1_criteria_sha256": PARENT_SHA,
                 "scientific_contract_changed": False, "execution_source_commit": args.source_commit}
    preflight_blob = blob(preflight)
    criteria["preflight"] = {"path": args.preflight.relative_to(ROOT).as_posix(),
                             "sha256": hashlib.sha256(preflight_blob).hexdigest()}
    criteria["artifact_paths"] = {key: value.replace("fd08_v2_formal", ROUND_ID)
                                  for key, value in parent["artifact_paths"].items()}
    require(scientific_content(criteria) == scientific_content(parent), "AMEND1 scientific contract drift")
    require(criteria["state_inventory"] == parent["state_inventory"], "state definitions changed")
    criteria_blob = blob(criteria); criteria_sha = hashlib.sha256(criteria_blob).hexdigest()
    files.update({"criteria.json": criteria_blob, "criteria.json.sha256": (criteria_sha + "\n").encode()})
    manifest = {"kind": "fd08_v2_formal_private_dataset_manifest", "criteria_sha256": criteria_sha,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["fd08_v2_dataset_manifest.json"] = blob(manifest)
    metadata = {"title": "CFD Opt SDF FD08 V2 Formal Amend2 Private Inputs", "id": DATASET_ID,
                "licenses": [{"name": "other"}]}
    built = {"criteria": criteria, "preflight": preflight, "files": files, "metadata": metadata}
    if args.dry_run:
        return built
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/kaggle-batch-migration"],
                                     cwd=ROOT, text=True).split()[0]
    require(head == remote == args.source_commit and not subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT), "registration requires clean pushed integration")
    require(args.rehearsal_evidence is not None, "actual pre-solver evidence path required")
    rehearsal, _ = verified_json(args.rehearsal_evidence)
    require(rehearsal["status"] == "PASS_PRE_SOLVER_EXECUTION_PATH"
            and rehearsal["source_commit"] == args.source_commit
            and rehearsal["runner_sha256"] == sources["kernel_runner"]["sha256"]
            and rehearsal["state_verification_count"] == 25 and rehearsal["state_count"] == 25
            and rehearsal["criteria_sha256"] == criteria_sha
            and rehearsal["dataset_manifest_sha256"] == hashlib.sha256(
                files["fd08_v2_dataset_manifest.json"]).hexdigest()
            and rehearsal["source_inputs_sha256"] == hashlib.sha256(json.dumps(
                sources, sort_keys=True, allow_nan=False).encode()).hexdigest()
            and rehearsal["solver_started"] is False,
            "registered-source actual pre-solver rehearsal required")
    for path in (args.criteria, args.preflight):
        require(not path.exists() and not path.with_name(path.name + ".sha256").exists(), "refusing overwrite")
    require(not args.dataset_dir.exists(), "refusing dataset overwrite")
    for path, data in ((args.criteria, criteria_blob), (args.preflight, preflight_blob)):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        path.with_name(path.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    args.dataset_dir.mkdir(parents=True)
    for name, data in {**files, "dataset-metadata.json": blob(metadata)}.items():
        (args.dataset_dir / name).write_bytes(data)
    return built


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--budget-evidence", required=True, type=Path)
    p.add_argument("--rehearsal-evidence", type=Path)
    p.add_argument("--criteria", type=Path, default=EVIDENCE / "formal_criteria.json")
    p.add_argument("--preflight", type=Path, default=EVIDENCE / "formal_preflight.json")
    p.add_argument("--dataset-dir", type=Path, default=ROOT / "work/kaggle_fd08_v2_formal_amend2_dataset")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(); built = build_formal(args)
    print(json.dumps({"criteria_sha256": hashlib.sha256(built["files"]["criteria.json"]).hexdigest(),
                      "source_commit": args.source_commit, "state_count": 25,
                      "formal_registered": not args.dry_run, "scientific_contract_changed": False}, indent=2))


if __name__ == "__main__":
    main()
