"""Re-judge the WP6-2 ranking with candidate-specific uncertainty (P18 condition 5).

The historical reports carried one inherited band (downforce 0.0147, drag 3.4%)
while the measured V1->V2 drift of several candidates exceeds it. This script
implements the DF0 closure condition 5: it pre-registers the re-judgment rules
BEFORE computing, then applies the existing Gate-4 qualification module with
per-candidate bands on the unchanged historical measurements.

Rules registered in the manifest:

- per-candidate downforce band = max(inherited 0.0147, measured |V2 - V1|);
- per-candidate drag band = max(inherited 0.034, measured relative |V2 - V1|);
- extraction sensitivity: ``not_applicable_analytic_anchor`` — this program is
  defined on analytic anchor shapes evaluated on the same grid, with no
  density-to-surface extraction in the loop, so there is no extraction term to
  measure (this is a declaration of applicability, not a zero measurement);
- resolvability: Gate 4, ``|I| > 2 * max(S_b, S_c, S_extraction)``;
- verdict: the cross_fidelity_ranking module rules (no_go / pass / unresolved).

Historical evidence files are read-only inputs; the output is a new report.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.cross_fidelity_ranking import (  # noqa: E402
    FidelityScores,
    Uncertainty,
    qualify_cross_fidelity_ranking,
)

REACHABLE = ROOT / "docs/evidence/reachable_set_cross_fidelity_ranking_2026_09.json"
FIRST_PROGRAM = ROOT / "docs/evidence/fixed_shape_cross_fidelity_ranking_2026_09.json"
MANIFEST_OUT = ROOT / "docs/evidence/wp6_2_rejudgment_manifest_2026_09.json"
REPORT_OUT = ROOT / "docs/evidence/wp6_2_rejudgment_2026_09.json"

INHERITED = Uncertainty(downforce_abs=0.0147, drag_coefficient_rel=0.034)
SUBSET_EXCLUDED_FROM_POOL = ("plate_a20_t05",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_measurements(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    stage_t = document.get("results", document).get("stage_t_results") or document.get(
        "stage_t_results"
    )
    stage_v = document.get("results", document).get("stage_v_results") or document.get(
        "stage_v_results"
    )
    if stage_t is None or stage_v is None:
        raise SystemExit(f"cannot locate stage_t/stage_v results in {path}")
    return {"stage_t": stage_t, "stage_v": stage_v}


def _response_values(measurements: dict, level: str, response: str) -> dict[str, float]:
    if response == "downforce":
        return {
            candidate: float(values["downforce"])
            for candidate, values in measurements["stage_v"][level].items()
        }
    return {
        candidate: float(values["Cd"])
        for candidate, values in measurements["stage_v"][level].items()
    }


def _stage_t_values(measurements: dict, response: str) -> dict[str, float]:
    key = "downforce_coefficient" if response == "downforce" else "drag_coefficient"
    return {
        candidate: float(values[key])
        for candidate, values in measurements["stage_t"].items()
    }


def _drift_bands(measurements: dict, candidates: list[str], response: str) -> dict[str, float]:
    v1 = _response_values(measurements, "V1", response)
    v2 = _response_values(measurements, "V2", response)
    inherited = (
        INHERITED.downforce_abs
        if response == "downforce"
        else INHERITED.drag_coefficient_rel
    )
    bands: dict[str, float] = {}
    for candidate in candidates:
        if response == "downforce":
            measured = abs(v2[candidate] - v1[candidate])
        else:
            measured = abs(v2[candidate] - v1[candidate]) / abs(v1[candidate])
        bands[candidate] = max(inherited, measured)
    return bands


def main() -> None:
    reachable = _load_measurements(REACHABLE)
    first = _load_measurements(FIRST_PROGRAM)

    reachable_candidates = sorted(reachable["stage_t"])
    first_candidates = sorted(first["stage_t"])
    pool_candidates = sorted(
        (set(first_candidates) | set(reachable_candidates))
        - set(SUBSET_EXCLUDED_FROM_POOL)
    )
    if len(reachable_candidates) != 8 or len(pool_candidates) != 17:
        raise SystemExit(
            f"unexpected candidate counts: reachable={len(reachable_candidates)}, "
            f"pool={len(pool_candidates)}"
        )

    manifest = {
        "kind": "wp6_2_rejudgment_manifest",
        "created": "2026-09-21",
        "registered_before_computation": True,
        "inputs": {
            "reachable_evidence": {
                "path": str(REACHABLE.relative_to(ROOT)),
                "sha256": _sha256(REACHABLE),
            },
            "first_program_evidence": {
                "path": str(FIRST_PROGRAM.relative_to(ROOT)),
                "sha256": _sha256(FIRST_PROGRAM),
            },
        },
        "candidate_sets": {
            "reachable_set_8": reachable_candidates,
            "combined_pool_17": pool_candidates,
            "pool_excluded": list(SUBSET_EXCLUDED_FROM_POOL),
        },
        "candidate_uncertainty_rule": (
            "downforce: max(inherited 0.0147, measured |V2 - V1|); "
            "drag: max(inherited 0.034, measured relative |V2 - V1|)"
        ),
        "extraction_sensitivity": {
            "status": "not_applicable_analytic_anchor",
            "reason": (
                "the program is defined on analytic anchor shapes evaluated on the "
                "same grid with no density-to-surface extraction in the loop; there "
                "is no extraction term to measure. This is an applicability "
                "declaration, not a zero measurement."
            ),
        },
        "resolvability_rule": "Gate 4: |I| > 2 * max(S_b, S_c, S_extraction)",
        "required_pairs": [],
        "required_pairs_note": (
            "the program's resolvability rule is applied to every generated pair; "
            "no additional pair subset is required"
        ),
        "verdict_rule": "cross_fidelity_ranking module: no_go / pass / unresolved",
        "j_scale": 1.0,
    }
    MANIFEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"registered {MANIFEST_OUT}")

    reports: dict[str, dict] = {}
    bands_table: dict[str, dict] = {}
    for set_name, candidate_source, candidates in (
        ("reachable_set_8", reachable, reachable_candidates),
        ("combined_pool_17", None, pool_candidates),
    ):
        def measurements_for(candidate: str) -> dict:
            if candidate in reachable["stage_t"] and candidate in first["stage_t"]:
                raise SystemExit(
                    f"candidate {candidate!r} exists in both programs; the pool merge "
                    "must be explicit"
                )
            return reachable if candidate in reachable["stage_t"] else first

        for response in ("downforce", "drag"):
            bands: dict[str, float] = {}
            for candidate in candidates:
                bands[candidate] = _drift_bands(
                    measurements_for(candidate), [candidate], response
                )[candidate]
            bands_table[f"{set_name}/{response}"] = bands
            for level in ("V1", "V2"):
                surrogate_values = {}
                reference_values = {}
                for candidate in candidates:
                    source = measurements_for(candidate)
                    surrogate_values[candidate] = _stage_t_values(source, response)[candidate]
                    reference_values[candidate] = _response_values(source, level, response)[candidate]
                report = qualify_cross_fidelity_ranking(
                    FidelityScores(fidelity_id="stage_t", values=surrogate_values),
                    FidelityScores(fidelity_id=f"stage_v_{level.lower()}", values=reference_values),
                    uncertainty=INHERITED,
                    response_id=response,
                    j_scale=1.0,
                    candidate_uncertainty=bands,
                )
                reports[f"{set_name}/{response}/{level}"] = report.to_dict()
                print(
                    f"{set_name} {response} {level}: {report.verdict} "
                    f"signed={report.n_signed_pairs} inversions={report.n_sign_inversions}"
                )

    aggregate = {}
    for response in ("downforce", "drag"):
        verdicts = [
            value["verdict"]
            for key, value in reports.items()
            if key.endswith(f"/{response}/V1") or key.endswith(f"/{response}/V2")
        ]
        if "no_go" in verdicts:
            aggregate[response] = "no_go"
        elif all(verdict == "pass" for verdict in verdicts):
            aggregate[response] = "pass"
        else:
            aggregate[response] = "unresolved"

    report_document = {
        "artifact_id": "wp6_2_rejudgment_2026_09",
        "evidence_class": "cross_fidelity_rejudgment",
        "issue": "P18 closure condition 5",
        "manifest": {
            "path": str(MANIFEST_OUT.relative_to(ROOT)),
            "registered_before_computation": True,
        },
        "candidate_uncertainty_table": bands_table,
        "reports": reports,
        "aggregate_verdict": aggregate,
        "conclusions": {
            "historical_files_rewritten": False,
            "verdict_change_from_historical": (
                "compare with the historical pass/unresolved values in "
                "docs/evidence/reachable_set_cross_fidelity_ranking_2026_09.json"
            ),
            "extraction_declared_not_applicable": True,
        },
        "claims_supported": [
            "the re-judged verdicts use candidate-specific bands on unchanged measurements"
        ],
        "claims_not_supported": [
            "no optimizer-generated-shape capability claim",
            "no absolute-response calibration claim",
        ],
    }
    REPORT_OUT.write_text(json.dumps(report_document, indent=2), encoding="utf-8")
    print(f"wrote {REPORT_OUT}")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
