"""Fail-closed audit of the WP6-2 ranking evidence (DF0, P18).

The audit consumes the historical artifacts without rewriting them and emits a
new, machine-checkable record:

- the manifest's two declared minimum-width values are compared and a conflict
  is a blocking finding;
- every ranking report's empty ``extraction_sensitivity`` is recorded as
  ``not_measured`` (never zero), and a ``pass`` verdict that depends on an
  unmeasured extraction sensitivity is downgraded to provisional;
- response-level verdict claims must have the same scope as the underlying
  report verdicts (unscoped claims may not exceed the reports);
- per-candidate V1-to-V2 drift is recomputed for downforce (absolute) and drag
  (relative) against the declared band, and candidates that exceed the band are
  recorded so the common band is not silently reused;
- measured feature sizes are compared with the declared minimum-width policy,
  with per-shape exclusions for each candidate policy value.

Historical evidence JSON files are read-only inputs. The output is a new
artifact; the scope-repair manifest narrows the claim to what the evidence
supports.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .analytic_candidate_shapes import (
    CANONICAL_SPACING,
    reachable_set_definitions,
    shape_definitions,
)
from .shape_feature_metrics import (
    measure_shape_definitions,
    measure_shape_registry,
    policy_exclusion_report,
)

FAIL = "fail"
ACTION = "action"
INFO = "info"

_DECLARED_WIDTH_RE = re.compile(r"(?:>=|≥)\s*([0-9]*\.?[0-9]+)\s*m\b")
_VERDICT_TOKENS = ("pass", "unresolved", "no_go", "fail")
_SCOPE_GROUPS = (
    ("reachable", "reachable_set_8"),
    ("17", "combined_pool_17_after_policy_exclusion"),
    ("combined", "combined_pool_17_after_policy_exclusion"),
)


@dataclass(frozen=True)
class AuditFinding:
    finding_id: str
    severity: str
    subject: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_declared_widths_m(*texts: str | None) -> list[float]:
    """Declared ``>= x m`` values found in manifest prose (sorted, unique)."""

    widths: set[float] = set()
    for text in texts:
        if not text:
            continue
        for match in _DECLARED_WIDTH_RE.finditer(text):
            widths.add(round(float(match.group(1)), 12))
    return sorted(widths)


def audit_manifest_thresholds(manifest: dict[str, Any]) -> list[AuditFinding]:
    purpose = manifest.get("purpose")
    definition = (manifest.get("definition") or {}).get("reachable_set")
    purpose_widths = extract_declared_widths_m(purpose)
    definition_widths = extract_declared_widths_m(definition)
    combined = sorted(set(purpose_widths) | set(definition_widths))
    findings: list[AuditFinding] = []
    if len(set(combined)) > 1:
        findings.append(
            AuditFinding(
                "declared_min_width_conflict",
                FAIL,
                "manifest",
                "the manifest purpose and definition declare different minimum "
                f"solid widths ({combined}); the audit cannot treat the ranking "
                "claim as scoped until one value is registered",
                {
                    "purpose_widths_m": purpose_widths,
                    "definition_widths_m": definition_widths,
                },
            )
        )
    elif not combined:
        findings.append(
            AuditFinding(
                "declared_min_width_absent",
                ACTION,
                "manifest",
                "manifest prose declares no machine-extractable minimum width",
            )
        )
    return findings


def iter_report_entries(
    ranking_reports: dict[str, Any]
) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield ``(group, report_key, report)`` for both evidence schemas."""

    entries: list[tuple[str, str, dict[str, Any]]] = []
    for group, value in ranking_reports.items():
        if isinstance(value, dict) and "reports" in value:
            for key, report in value["reports"].items():
                entries.append((group, key, report))
        elif isinstance(value, dict) and "verdict" in value:
            entries.append((group, group, value))
    return entries


def audit_ranking_reports(
    ranking_reports: dict[str, Any],
    declared_uncertainty: dict[str, Any] | None,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for group, key, report in iter_report_entries(ranking_reports):
        subject = f"{group}/{key}"
        extraction = report.get("extraction_sensitivity") or {}
        if not extraction:
            findings.append(
                AuditFinding(
                    "extraction_sensitivity_not_measured",
                    FAIL,
                    subject,
                    "extraction_sensitivity is empty; it is recorded as "
                    "not_measured and must not be treated as zero in the "
                    "verdict",
                )
            )
        if report.get("verdict") == "pass" and not extraction:
            findings.append(
                AuditFinding(
                    "pass_requires_measured_extraction",
                    FAIL,
                    subject,
                    "a pass verdict with an unmeasured extraction sensitivity "
                    "is provisional only; the claim scope must be narrowed",
                )
            )
        if report.get("failed_required_pairs"):
            findings.append(
                AuditFinding(
                    "failed_required_pairs",
                    FAIL,
                    subject,
                    "the report itself records failed required pairs; no "
                    "ranking conclusion is admissible",
                    {"failed_required_pairs": report["failed_required_pairs"]},
                )
            )
        if declared_uncertainty and report.get("uncertainty") != declared_uncertainty:
            findings.append(
                AuditFinding(
                    "report_uncertainty_mismatch",
                    FAIL,
                    subject,
                    "the report's uncertainty differs from the evidence-level "
                    "declared uncertainty",
                    {
                        "report_uncertainty": report.get("uncertainty"),
                        "declared_uncertainty": declared_uncertainty,
                    },
                )
            )
    return findings


def compute_v1v2_drift(
    candidate_v1: dict[str, dict[str, float]],
    candidate_v2: dict[str, dict[str, float]],
    bands: dict[str, float],
) -> dict[str, Any]:
    """Per-candidate V1->V2 downforce (absolute) and drag (relative) drift."""

    rows: dict[str, Any] = {}
    for candidate in sorted(set(candidate_v1) & set(candidate_v2)):
        v1, v2 = candidate_v1[candidate], candidate_v2[candidate]
        d_df = float(v2["downforce"]) - float(v1["downforce"])
        d_cd_rel = (float(v2["Cd"]) - float(v1["Cd"])) / float(v1["Cd"])
        rows[candidate] = {
            "downforce_v1": float(v1["downforce"]),
            "downforce_v2": float(v2["downforce"]),
            "downforce_abs_drift": abs(d_df),
            "drag_coefficient_v1": float(v1["Cd"]),
            "drag_coefficient_v2": float(v2["Cd"]),
            "drag_relative_drift": abs(d_cd_rel),
            "downforce_within_declared_band": bool(
                abs(d_df) <= bands["downforce_abs"] + 1e-12
            ),
            "drag_within_declared_band": bool(
                abs(d_cd_rel) <= bands["drag_coefficient_rel"] + 1e-12
            ),
        }
    downforce_exceed = sorted(
        c for c, r in rows.items() if not r["downforce_within_declared_band"]
    )
    drag_exceed = sorted(
        c for c, r in rows.items() if not r["drag_within_declared_band"]
    )
    return {
        "bands": dict(bands),
        "per_candidate": rows,
        "candidates_exceeding_downforce_band": downforce_exceed,
        "candidates_exceeding_drag_band": drag_exceed,
        "max_downforce_abs_drift": max(
            (r["downforce_abs_drift"] for r in rows.values()), default=None
        ),
        "max_drag_relative_drift": max(
            (r["drag_relative_drift"] for r in rows.values()), default=None
        ),
        "common_band_valid_for_all_candidates": not downforce_exceed and not drag_exceed,
    }


def audit_drift(drift: dict[str, Any], subject: str) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    exceed = drift["candidates_exceeding_downforce_band"]
    if exceed:
        findings.append(
            AuditFinding(
                "candidate_drift_exceeds_downforce_band",
                ACTION,
                subject,
                "the inherited downforce band is exceeded by "
                f"{len(exceed)} candidate(s); register the candidate-specific "
                "drift and do not reuse the common band for those rows",
                {
                    "candidates": exceed,
                    "max_downforce_abs_drift": drift["max_downforce_abs_drift"],
                    "declared_band": drift["bands"]["downforce_abs"],
                },
            )
        )
    drag_exceed = drift["candidates_exceeding_drag_band"]
    if drag_exceed:
        findings.append(
            AuditFinding(
                "candidate_drift_exceeds_drag_band",
                ACTION,
                subject,
                f"the inherited drag band is exceeded by {len(drag_exceed)} candidate(s)",
                {
                    "candidates": drag_exceed,
                    "max_drag_relative_drift": drift["max_drag_relative_drift"],
                    "declared_band": drift["bands"]["drag_coefficient_rel"],
                },
            )
        )
    return findings


def extract_claim_verdict(text: str) -> str | None:
    low = text.lower()
    for token in _VERDICT_TOKENS:
        if token in low:
            return token
    return None


def audit_verdict_claims(
    verdict_by_response: dict[str, str],
    ranking_reports: dict[str, Any],
) -> list[AuditFinding]:
    """Claimed verdicts must be scoped exactly like the underlying reports."""

    by_response: dict[str, dict[str, list[str]]] = {}
    for group, _key, report in iter_report_entries(ranking_reports):
        response = str(report.get("response_id", "")).split("/")[0]
        by_response.setdefault(response, {}).setdefault(group, []).append(
            str(report.get("verdict"))
        )
    findings: list[AuditFinding] = []
    for response, claim in verdict_by_response.items():
        claimed = extract_claim_verdict(claim)
        groups = by_response.get(response, {})
        if claimed is None:
            findings.append(
                AuditFinding(
                    "claim_verdict_unparseable",
                    FAIL,
                    response,
                    f"verdict claim {claim!r} contains no known verdict token",
                )
            )
            continue
        low = claim.lower()
        scope = next((group for token, group in _SCOPE_GROUPS if token in low), None)
        if scope is not None:
            verdicts = set(groups.get(scope, []))
            if not verdicts:
                findings.append(
                    AuditFinding(
                        "claim_scope_group_missing",
                        FAIL,
                        response,
                        f"claim scopes to {scope!r} but no such report group exists",
                    )
                )
            elif verdicts != {claimed}:
                findings.append(
                    AuditFinding(
                        "claim_verdict_exceeds_scope",
                        FAIL,
                        response,
                        f"claim verdict {claimed!r} does not match group "
                        f"{scope!r} report verdicts {sorted(verdicts)}",
                    )
                )
        else:
            verdicts = {v for values in groups.values() for v in values}
            if verdicts and verdicts != {claimed}:
                findings.append(
                    AuditFinding(
                        "unscoped_claim_exceeds_reports",
                        FAIL,
                        response,
                        f"unscoped claim verdict {claimed!r} is not the single "
                        f"verdict of all reports ({sorted(verdicts)})",
                    )
                )
    return findings


def audit_feature_policy(
    feature_table: dict[str, Any],
    declared_widths_m: list[float],
    *,
    subject: str = "feature_sizes",
) -> tuple[list[AuditFinding], dict[str, Any]]:
    exclusion = policy_exclusion_report(feature_table, declared_widths_m)
    findings: list[AuditFinding] = []
    spacing = float(feature_table["spacing_m"])
    tolerance = spacing / 2.0
    mismatches = []
    under_resolved = []
    over_read = []
    for shape_id, entry in feature_table["shapes"].items():
        declared = float(entry["min_declared_part_dimension_m"])
        measured = float(entry["min_measured_feature_size_m"])
        delta = measured - declared
        if abs(delta) <= 1e-9:
            classification = "exact"
        elif abs(delta) <= tolerance + 1e-9:
            classification = "grid_quantized"
        elif delta < 0:
            classification = "under_resolved"
        else:
            classification = "grid_over_read"
        row = {
            "shape_id": shape_id,
            "declared_min_part_dimension_m": declared,
            "measured_min_feature_size_m": measured,
            "delta_m": delta,
            "delta_cells": delta / spacing,
            "classification": classification,
        }
        if classification != "exact":
            mismatches.append(row)
        if classification == "under_resolved":
            under_resolved.append(shape_id)
        if classification == "grid_over_read":
            over_read.append(shape_id)
    if mismatches:
        findings.append(
            AuditFinding(
                "declared_vs_measured_feature_mismatch",
                FAIL if under_resolved else INFO,
                subject,
                f"{len(mismatches)} shape(s) have measured minimum feature size "
                "different from the declared minimum part dimension; each "
                "difference is classified (grid quantization is not an error, "
                "under-resolution is)",
                {
                    "mismatches": mismatches,
                    "under_resolved_shape_ids": under_resolved,
                    "grid_over_read_shape_ids": over_read,
                },
            )
        )
    for width, shape_ids in exclusion["excluded_shape_ids"].items():
        if shape_ids:
            findings.append(
                AuditFinding(
                    "policy_excludes_shapes",
                    ACTION,
                    subject,
                    f"a declared minimum width of {width} m excludes "
                    f"{len(shape_ids)} registered shape(s); the reachable-set "
                    "claim must name the surviving subset",
                    {"width_m": float(width), "excluded_shape_ids": shape_ids},
                )
            )
    return findings, exclusion


def audit_mixed_registry_claims(
    manifest: dict[str, Any], exclusion: dict[str, Any]
) -> list[AuditFinding]:
    """The manifest's own reachable-set statement vs the measured exclusions."""

    policy = exclusion["policy_widths_m"]
    if not policy:
        return []
    widest = max(policy)
    excluded = exclusion["excluded_shape_ids"].get(f"{widest:g}", [])
    findings: list[AuditFinding] = []
    if excluded:
        findings.append(
            AuditFinding(
                "reachable_set_includes_below_policy_shapes",
                FAIL,
                "manifest",
                f"the manifest's widest declared policy {widest:g} m excludes "
                f"{len(excluded)} registered shape(s) that are nevertheless in "
                "the registered reachable set",
                {"excluded_shape_ids": excluded},
            )
        )
    if len(policy) > 1:
        strict = exclusion["excluded_shape_ids"].get(f"{max(policy):g}", [])
        loose = exclusion["excluded_shape_ids"].get(f"{min(policy):g}", [])
        overlapping = sorted(set(loose) - set(strict))
        findings.append(
            AuditFinding(
                "policy_dependent_scope",
                ACTION,
                "manifest",
                "the shape membership of the reachable set depends on which "
                "declared width is used",
                {
                    "excluded_at_strict_width": strict,
                    "excluded_at_loose_width": loose,
                    "shapes_only_excluded_at_strict_width": overlapping,
                },
            )
        )
    return findings


def build_scope_repair_manifest(
    *,
    manifest: dict[str, Any],
    declared_widths_m: list[float],
    exclusion: dict[str, Any],
    drift: dict[str, Any],
    extraction_status: dict[str, str],
    source_paths: dict[str, str],
) -> dict[str, Any]:
    """DF0 output: narrow the WP6-2 claim to what the measured evidence supports."""

    widest = max(declared_widths_m) if declared_widths_m else None
    excluded = (
        exclusion["excluded_shape_ids"].get(f"{widest:g}", []) if widest else []
    )
    candidate_uncertainty = {
        candidate: {
            "downforce_abs": max(
                drift["bands"]["downforce_abs"], row["downforce_abs_drift"]
            ),
            "drag_coefficient_rel": max(
                drift["bands"]["drag_coefficient_rel"], row["drag_relative_drift"]
            ),
        }
        for candidate, row in drift["per_candidate"].items()
    }
    return {
        "kind": "wp6_2_scope_repair_manifest",
        "created": date.today().isoformat(),
        "supersedes": "reachable_set_ranking_manifest.json (claim scope only; "
        "the historical file is not rewritten)",
        "declared_min_width_m": widest,
        "excluded_shape_ids": excluded,
        "reachable_claim_candidates": "registered shapes minus excluded_shape_ids",
        "extraction_sensitivity_status": extraction_status,
        "claim_status": "provisional" if any(
            status == "not_measured" for status in extraction_status.values()
        ) else "measured",
        "required_pair_policy": "pre-registered pairs only; unresolvable pairs "
        "remain explicit rows and never disappear silently",
        "candidate_specific_uncertainty": candidate_uncertainty,
        "source_artifacts": source_paths,
    }


def build_evidence_audit(
    *,
    manifest_path: str | Path,
    reachable_evidence_path: str | Path,
    first_program_evidence_path: str | Path | None = None,
    registry_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    feature_table: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the DF0 audit and (optionally) write the evidence artifact.

    ``feature_table`` may inject a precomputed measurement table (used by unit
    tests); by default the registered shapes are measured from their analytic
    definitions.
    """

    manifest_path = Path(manifest_path)
    reachable_path = Path(reachable_evidence_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = json.loads(reachable_path.read_text(encoding="utf-8"))

    declared_widths = extract_declared_widths_m(
        manifest.get("purpose"),
        (manifest.get("definition") or {}).get("reachable_set"),
    )
    findings: list[AuditFinding] = []
    findings += audit_manifest_thresholds(manifest)

    ranking_reports = evidence.get("ranking_reports", {})
    declared_uncertainty = evidence.get("declared_uncertainty_verbatim")
    findings += audit_ranking_reports(ranking_reports, declared_uncertainty)
    findings += audit_verdict_claims(
        evidence.get("verdict_by_response_at_wp6", {}), ranking_reports
    )

    stage_v = evidence.get("results", {}).get("stage_v_results", {})
    bands = {
        "downforce_abs": float(
            declared_uncertainty.get("downforce_abs", 0.0147)
            if declared_uncertainty
            else 0.0147
        ),
        "drag_coefficient_rel": float(
            declared_uncertainty.get("drag_coefficient_rel", 0.034)
            if declared_uncertainty
            else 0.034
        ),
    }
    drift = compute_v1v2_drift(stage_v.get("V1", {}), stage_v.get("V2", {}), bands)
    findings += audit_drift(drift, "reachable_set_v1_v2")

    feature_table = feature_table or measure_shape_definitions(
        {**shape_definitions(), **reachable_set_definitions()},
        spacing_m=CANONICAL_SPACING,
        threshold_m=min(declared_widths) if declared_widths else None,
    )
    findings += audit_feature_policy(feature_table, declared_widths)[0]
    exclusion = policy_exclusion_report(feature_table, declared_widths)
    findings += audit_mixed_registry_claims(manifest, exclusion)

    extraction_status = {
        f"{group}/{key}": (
            "measured" if (report.get("extraction_sensitivity") or {}) else "not_measured"
        )
        for group, key, report in iter_report_entries(ranking_reports)
    }
    source_paths = {
        "manifest": str(manifest_path),
        "reachable_evidence": str(reachable_path),
    }
    if first_program_evidence_path is not None:
        source_paths["first_program_evidence"] = str(first_program_evidence_path)
    if registry_dir is not None:
        source_paths["registry_dir"] = str(registry_dir)

    repair = build_scope_repair_manifest(
        manifest=manifest,
        declared_widths_m=declared_widths,
        exclusion=exclusion,
        drift=drift,
        extraction_status=extraction_status,
        source_paths=source_paths,
    )
    ok = not any(finding.severity == FAIL for finding in findings)
    artifact = {
        "artifact_id": "wp6_2_evidence_audit_2026_09",
        "created": date.today().isoformat(),
        "evidence_class": "contract_and_evidence_audit",
        "issue": "P18 (DF0)",
        "inputs": {
            **source_paths,
            "manifest_sha256": sha256_file(manifest_path),
            "reachable_evidence_sha256": sha256_file(reachable_path),
        },
        "declared_min_width_policy": {
            "values_m": declared_widths,
            "consistent": len(set(declared_widths)) <= 1,
        },
        "extraction_sensitivity_status": extraction_status,
        "drift_table": drift,
        "feature_sizes": feature_table,
        "policy_exclusions": exclusion,
        "scope_repair_manifest": repair,
        "findings": [asdict(finding) for finding in findings],
        "ok": ok,
        "conclusions": {
            "historical_files_rewritten": False,
            "blocking_findings": [
                finding.finding_id for finding in findings if finding.severity == FAIL
            ],
            "action_findings": [
                finding.finding_id for finding in findings if finding.severity == ACTION
            ],
            "claims_requiring_narrowing": [
                "reachable-set downforce pass is provisional while extraction "
                "sensitivity is not_measured",
                "manifest minimum-width policy must be re-registered with one value",
            ],
        },
        "claims_supported": [
            "all registered shapes have measured per-part local thickness, "
            "connected components, part gaps and overlaps on the canonical grid",
            "the declared/measured width mismatch and every candidate whose "
            "V1->V2 drift exceeds the inherited band are machine-readable",
        ],
        "claims_not_supported": [
            "no new ranking claim is made by this audit",
            "no extraction sensitivity value is inferred from an empty block",
            "no optimizer-generated geometry is covered",
        ],
    }
    if registry_dir is not None:
        artifact["as_run_registry"] = measure_shape_registry(
            registry_dir,
            spacing_m=CANONICAL_SPACING,
            threshold_m=min(declared_widths) if declared_widths else None,
        )
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


__all__ = [
    "ACTION",
    "FAIL",
    "INFO",
    "AuditFinding",
    "audit_drift",
    "audit_feature_policy",
    "audit_manifest_thresholds",
    "audit_mixed_registry_claims",
    "audit_ranking_reports",
    "audit_verdict_claims",
    "build_evidence_audit",
    "build_scope_repair_manifest",
    "compute_v1v2_drift",
    "extract_claim_verdict",
    "extract_declared_widths_m",
    "iter_report_entries",
    "sha256_file",
]
