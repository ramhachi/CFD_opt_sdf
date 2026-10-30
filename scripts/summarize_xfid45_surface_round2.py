#!/usr/bin/env python3
"""Reconcile immutable screen/verifier outputs without extracting surfaces."""

import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main():
    result = json.loads((OUT / "result.json").read_text())
    verify = json.loads((OUT / "independent_verification.json").read_text())
    reg = json.loads((OUT / "preregistration.json").read_text())
    failure = json.loads((OUT / "validation/failure_id_comparison.json").read_text())
    paired = {(r["candidate"], r["case"]): r for r in verify["cases"]}
    rows = []
    for row in result["cases"]:
        check = paired[row["candidate"], row["case"]]
        differences = {
            k: {"evaluator": value, "verifier": check["gates"][k]}
            for k, value in row["gates"].items()
            if value != check["gates"][k]
        }
        numerical = {}
        for label in ("statistics", "serialized_statistics"):
            for key in (
                "area_m2",
                "signed_volume_m3",
                "clearance_m",
                "watertight",
                "winding_consistent",
                "nonmanifold_edges",
                "nonmanifold_vertex_links",
                "duplicate_faces",
                "zero_area_faces",
            ):
                a = row[label][key]
                b = check[label][key]
                same = (
                    np.isclose(a, b, rtol=1e-10, atol=1e-12)
                    if isinstance(a, float)
                    else a == b
                )
                if not same:
                    numerical[f"{label}.{key}"] = {"evaluator": a, "verifier": b}
        rows.append(
            {
                "candidate": row["candidate"],
                "case": row["case"],
                "evaluator_pass": row["pass"],
                "verifier_pass": all(check["gates"].values()),
                "all_individual_gates_agree": check["agreement"],
                "gate_differences": differences,
                "other_statistic_differences": numerical,
                "accepted": row["pass"]
                and check["agreement"]
                and all(check["gates"].values()),
            }
        )
    frozen = {}
    for group in ("input_files", "source_files", "runtime_files"):
        frozen[group] = {
            key: sha(
                ROOT / spec["path"]
                if not Path(spec["path"]).is_absolute()
                else Path(spec["path"])
            )
            == spec["sha256"]
            for key, spec in reg[group].items()
        }
    for key in ("predecessor_registration", "predecessor_result"):
        frozen[key] = sha(ROOT / reg[key]["path"]) == reg[key]["sha256"]
    candidates = {
        name: all(r["accepted"] for r in rows if r["candidate"] == name)
        for name in ("A", "B", "C")
    }
    report = {
        "evidence_class": "reconciliation_of_frozen_solver_free_screen_and_independent_recomputation",
        "registration_commit": result["registration_commit"],
        "registration_sha256": sha(OUT / "preregistration.json"),
        "result_sha256": sha(OUT / "result.json"),
        "independent_result_sha256": sha(OUT / "independent_verification.json"),
        "individual_gate_agreement_case_count": sum(
            r["all_individual_gates_agree"] for r in rows
        ),
        "overall_verdict_agreement_case_count": sum(
            r["evaluator_pass"] == r["verifier_pass"] for r in rows
        ),
        "candidate_all_cases_accepted": candidates,
        "selected_candidate": None,
        "formal_XFID_may_resume": False,
        "qualification_flags": result["qualification_flags"],
        "frozen_files_unchanged": frozen,
        "validation_new_failure_ids": failure["new_failure_ids"],
        "next_decision": "reconsider direct GridSDF Stage V separately; no solver/production semantics change here",
        "cases": rows,
    }
    dump(OUT / "geometry_gate_results.json", report)
    assert not any(report["qualification_flags"].values())
    assert all(all(v.values()) if isinstance(v, dict) else v for v in frozen.values())
    assert not failure["new_failure_ids"]
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "individual_gate_agreement_case_count",
                    "overall_verdict_agreement_case_count",
                    "candidate_all_cases_accepted",
                    "selected_candidate",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
