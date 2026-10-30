#!/usr/bin/env python3
"""Audit force-history lineage for the corrected v16 factor screen.

This is a read-only evidence step.  It does not run OpenFOAM.  It verifies
that every qualified response was read from the treatment's newly generated
canonical ``coefficient.dat`` and that the copied top-boundary case did not
fall back to a stale baseline history.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca

MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_boundary_contract_manifest_v2_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_v16_domain_boundary_contract_v2_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_v_v16_domain_boundary_lineage_audit_2026_09.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _require(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"missing lineage input: {path}")
    return path


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _boundary_type(path: Path, patch: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^\s*{re.escape(patch)}\s*\{{(?P<body>.*?)^\s*\}}", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"patch {patch!r} is missing from {_relative(path)}")
    type_match = re.search(r"(?m)^\s*type\s+(\w+)\s*;", match.group("body"))
    if type_match is None:
        raise SystemExit(f"patch {patch!r} has no type in {_relative(path)}")
    return type_match.group(1)


def _field_type(path: Path, patch: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^\s*{re.escape(patch)}\s*\{{(?P<body>.*?)^\s*\}}", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"field patch {patch!r} is missing from {_relative(path)}")
    type_match = re.search(r"(?m)^\s*type\s+(\w+)\s*;", match.group("body"))
    if type_match is None:
        raise SystemExit(f"field patch {patch!r} has no type in {_relative(path)}")
    return type_match.group(1)


def _history_record(case_dir: Path) -> dict[str, Any]:
    qualification_path = _require(case_dir / "stage_v_qualification.json")
    qualification = _load(qualification_path)
    if qualification.get("qualified") is not True:
        raise SystemExit(f"case is not qualified: {_relative(case_dir)}")
    history = qualification.get("force_stationarity", {}).get("history", {})
    source = Path(str(history.get("source", "")))
    canonical = case_dir / "postProcessing/forceCoeffs/0/coefficient.dat"
    if source != canonical:
        raise SystemExit(
            f"qualification source is not the canonical treatment file: "
            f"{source} != {canonical}"
        )
    _require(canonical)
    stale_numbered = sorted(canonical.parent.glob("coefficient_*.dat"))
    return {
        "case_dir": _relative(case_dir),
        "qualification": {
            "path": _relative(qualification_path),
            "sha256": _sha256(qualification_path),
        },
        "history": {
            "source": _relative(canonical),
            "sha256": _sha256(canonical),
            "row_count": int(history["row_count"]),
            "source_is_canonical": True,
            "numbered_sibling_files": [_relative(path) for path in stale_numbered],
        },
        "responses": {
            "Cd_mean": float(qualification["force_stationarity"]["responses"]["Cd"]["mean"]),
            "downforce_mean": float(
                qualification["force_stationarity"]["responses"]["downforce"]["mean"]
            ),
        },
    }


def audit() -> dict[str, Any]:
    manifest = _load(_require(MANIFEST))
    evidence = _load(_require(EVIDENCE))
    manifest_digest = _sha256(MANIFEST)
    if manifest_digest != MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("v2 manifest sidecar mismatch")
    if evidence["manifest"]["sha256"] != manifest_digest:
        raise SystemExit("v2 evidence does not bind the v2 manifest")

    baseline_dir = ROOT / manifest["baseline"]["case_dir"]
    baseline = _history_record(baseline_dir)
    rows: dict[str, Any] = {}
    for treatment in manifest["treatments"]:
        rows[treatment["name"]] = _history_record(ROOT / treatment["case_dir"])

    baseline_hash = baseline["history"]["sha256"]
    distinct_sources = all(row["history"]["sha256"] != baseline_hash for row in rows.values())
    top_case = ROOT / next(
        item["case_dir"] for item in manifest["treatments"] if item["name"] == "top_pressure_outlet"
    )
    base_case = baseline_dir
    boundary = {
        "baseline_top": {
            "mesh": _boundary_type(base_case / "constant/polyMesh/boundary", "top"),
            "U": _field_type(base_case / "0/U", "top"),
            "p": _field_type(base_case / "0/p", "top"),
        },
        "top_pressure_outlet": {
            "mesh": _boundary_type(top_case / "constant/polyMesh/boundary", "top"),
            "U": _field_type(top_case / "0/U", "top"),
            "p": _field_type(top_case / "0/p", "top"),
        },
    }
    expected_boundary = {
        "baseline_top": {"mesh": "symmetryPlane", "U": "symmetryPlane", "p": "symmetryPlane"},
        "top_pressure_outlet": {"mesh": "patch", "U": "zeroGradient", "p": "fixedValue"},
    }
    boundary_matches = boundary == expected_boundary
    if not distinct_sources or not boundary_matches:
        raise SystemExit("v2 lineage audit failed: treatment source or boundary identity is not isolated")

    result = {
        "kind": "stage_v_v16_domain_boundary_lineage_audit",
        "schema_version": 1,
        "status": "pass",
        "contract_manifest": {"path": _relative(MANIFEST), "sha256": manifest_digest},
        "factor_evidence": {"path": _relative(EVIDENCE), "sha256": _sha256(EVIDENCE)},
        "candidate_sha256": manifest["candidate"]["stl"]["sha256"],
        "baseline": baseline,
        "treatments": rows,
        "boundary_identity": boundary,
        "checks": {
            "qualification_reads_canonical_coefficient_dat": True,
            "treatment_histories_distinct_from_baseline": distinct_sources,
            "boundary_change_matches_registered_top_outlet_factor": boundary_matches,
            "preliminary_reused_postprocessing_case_not_used": True,
        },
        "claims_not_supported": [
            "grid-independent or absolute Stage V downforce",
            "Stage S S2 qualification",
            "shape update or optimization authorization",
        ],
    }
    payload = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if AUDIT.exists() and AUDIT.read_text(encoding="utf-8") != payload:
        raise SystemExit("refusing to overwrite immutable lineage audit")
    if not AUDIT.exists():
        AUDIT.write_text(payload, encoding="utf-8")
    digest = _sha256(AUDIT)
    sidecar = AUDIT.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit("lineage audit sidecar mismatch")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    print(json.dumps({"audit": _relative(AUDIT), "sha256": digest, "status": "pass"}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    audit()
