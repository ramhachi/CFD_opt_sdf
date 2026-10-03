#!/usr/bin/env python3
"""Assemble complete frozen-verifier partitions; no scientific recomputation."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def main():
    reference = json.loads((OUT / "result.json").read_text())
    registration = json.loads((OUT / "preregistration.json").read_text())
    reports = {}
    bindings = {}
    for r in (1, 2, 4, 8):
        path = OUT / "independent_partitions" / f"r{r}" / "independent_result.json"
        report = json.loads(path.read_text())
        assert len(report["cases"]) == 10 and len(report["fidelity_pairs"]) == 6
        assert all(c["r"] == r for c in report["cases"] + report["fidelity_pairs"])
        reports[r] = report
        bindings[str(r)] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    cases = [c for r in reports for c in reports[r]["cases"]]
    pairs = [c for r in reports for c in reports[r]["fidelity_pairs"]]
    expected_cases = {(c["r"], c["case"]) for c in reference["cases"]}
    expected_pairs = {(c["r"], c["case"]) for c in reference["fidelity_pairs"]}
    assert len(cases) == len(expected_cases) == 40
    assert len(pairs) == len(expected_pairs) == 24
    assert {(c["r"], c["case"]) for c in cases} == expected_cases
    assert {(c["r"], c["case"]) for c in pairs} == expected_pairs
    assert all(
        hashlib.sha256((ROOT / s["path"]).read_bytes()).hexdigest() == s["sha256"]
        for s in registration["sources"].values()
    )
    individual = all(c["individual_gate_agreement"] for c in cases + pairs)
    aggregate = all(c["aggregate_agreement"] for c in cases) and all(
        c["status"] == ref["status"]
        for c, ref in zip(pairs, reference["fidelity_pairs"], strict=True)
    )
    volumes = all(p["all_volumes_agree"] for p in reports.values())
    candidate = {
        str(r): all(c["surface_gates_pass"] for c in cases if c["r"] == r)
        and all(c["status"] == "PASS" for c in pairs if c["r"] == r)
        and individual
        and aggregate
        and volumes
        for r in reports
    }
    numeric = []
    for c, ref in zip(pairs, reference["fidelity_pairs"], strict=True):
        assert (c["r"], c["case"]) == (ref["r"], ref["case"])
        for key in ("double", "float32"):
            metrics = (
                "maximum_normal_displacement_difference_m",
                "unresolved_samples",
                "within_limit",
            )
            numeric.append(
                {
                    "r": c["r"],
                    "case": c["case"],
                    "storage": key,
                    "parent": {k: ref[key][k] for k in metrics},
                    "independent": {k: c[key][k] for k in metrics},
                    "note": "Diagnostic numeric records; Boolean agreement is not root completeness or per-sample numeric agreement.",
                }
            )
    result = {
        "evidence_class": "complete_assembly_of_frozen_independent_NPZ_STL_recomputation",
        "qualification_flags": registration["qualification_flags"],
        "partition_bindings": bindings,
        "coverage": {"surface_cases": 40, "fidelity_pairs": 24},
        "cases": cases,
        "fidelity_pairs": pairs,
        "source_volumes_by_partition": {
            str(r): p["source_volumes"] for r, p in reports.items()
        },
        "all_individual_gates_agree": individual,
        "all_aggregate_gates_agree": aggregate,
        "all_volumes_agree": volumes,
        "candidate_pass": candidate,
        "selected_r": next(
            (
                r
                for r in reports
                if candidate[str(r)]
                and reference["candidate_pass_before_independent_verification"][str(r)]
            ),
            None,
        ),
        "numeric_fidelity_comparison": numeric,
        "limitation": "Frozen source-root enumeration drops valid nearby roots in the parent; retained maxima must not all be interpreted as physical displacement error. No threshold, evaluator or verifier changed after observation.",
    }
    (OUT / "independent_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "coverage",
                    "all_individual_gates_agree",
                    "all_aggregate_gates_agree",
                    "all_volumes_agree",
                    "selected_r",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
