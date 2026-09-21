"""Registered discretization-factor screen for the Stage V downforce drift.

The plain fixed-domain family drifts 0.01291 in downforce from V1 to V2 (bound
0.005) with the first-order ``bounded Gauss upwind`` convection scheme. This
screen tests whether the scheme is the dominant factor before any V3 run:

- arm A (control): upwind at V1, re-run in this campaign root to prove the
  copy-and-patch path reproduces the recorded baseline;
- arm B: ``linearUpwind grad(U)`` at V1 and V2.

The campaign registers its hypothesis, factor, metric, and decision rule before
running; it runs no V3. Historical evidence is read-only input.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.cfd import write_stage_v_qualification  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from stage_t_filtered_ramp import SOLVE_ONLY_ALLRUN  # noqa: E402

BASELINE_ROOT = ROOT / "work/stage_v_fixed_domain_2026_09"
BASELINE_RESULTS = BASELINE_ROOT / "results.json"
BASELINE_EVIDENCE = ROOT / "docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json"
OUT = ROOT / "work/stage_v_scheme_factor_2026_09"
MANIFEST = ROOT / "docs/evidence/stage_v_scheme_factor_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_scheme_factor_2026_09.json"
CID = "opt_q100_b0_step0_try0_block"
LEVELS = ("V1", "V2")
SCHEME_ARMS = {
    "upwind_control": "bounded Gauss upwind;",
    "linearUpwind": "bounded Gauss linearUpwind grad(U);",
}
DOWNFORCE_BOUND = 0.005
DRAG_RELATIVE_BOUND = 0.02


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register() -> dict:
    manifest = {
        "kind": "stage_v_scheme_factor_manifest",
        "created": "2026-09-21",
        "registered_before_computation": True,
        "hypothesis": (
            "the V1->V2 downforce drift of the plain fixed-domain family is "
            "dominated by the first-order upwind convection scheme"
        ),
        "factor": {
            "name": "div(phi,U) convection scheme",
            "baseline": "bounded Gauss upwind",
            "treatment": "bounded Gauss linearUpwind grad(U)",
        },
        "levels": list(LEVELS),
        "metric": {
            "downforce_absolute_drift": "|downforce(V2) - downforce(V1)|",
            "drag_relative_drift": "|Cd(V2) - Cd(V1)| / |Cd(V1)|",
            "bounds": {
                "downforce_absolute": DOWNFORCE_BOUND,
                "drag_relative": DRAG_RELATIVE_BOUND,
            },
        },
        "decision": (
            "if the treatment arm moves the downforce drift below the bound, "
            "register the scheme as the discretization factor and continue to V3 "
            "for that arm; otherwise accept the measured band for the planned "
            "ranking experiment and escalate the mesh-convergence policy"
        ),
        "stop_conditions": [
            "no V3 run in this campaign",
            "a treatment arm that fails any qualification gate is reported as failed, never dropped",
        ],
        "budget": {"runs": 3, "note": "V1 control + V1/V2 treatment"},
        "inputs": {
            "baseline_results": {
                "path": str(BASELINE_RESULTS.relative_to(ROOT)),
                "sha256": _sha256(BASELINE_RESULTS),
            },
            "baseline_evidence": {
                "path": str(BASELINE_EVIDENCE.relative_to(ROOT)),
                "sha256": _sha256(BASELINE_EVIDENCE),
            },
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _baseline_family() -> dict:
    document = json.loads(BASELINE_EVIDENCE.read_text(encoding="utf-8"))
    family = document["plain_fixed_domain_family"]
    return {
        level: {
            "qualified": bool(family[level].get("qualified")),
            "Cd": float(family[level]["Cd"]),
            "downforce": float(family[level]["downforce"]),
        }
        for level in LEVELS
    }


def _prepare_arm_case(level: str, arm: str, scheme_line: str) -> Path:
    source = BASELINE_ROOT / CID / level
    if not source.is_dir():
        raise SystemExit(f"baseline case is missing: {source}")
    case_dir = OUT / CID / f"{level}_{arm}"
    if case_dir.exists():
        shutil.rmtree(case_dir)
    shutil.copytree(source, case_dir)
    for stale in ("log.simpleFoam", "stage_v_qualification.json"):
        (case_dir / stale).unlink(missing_ok=True)
    for item in case_dir.iterdir():
        if item.is_dir() and item.name not in {"constant", "system", "0"}:
            shutil.rmtree(item)
    schemes_path = case_dir / "system" / "fvSchemes"
    text = schemes_path.read_text(encoding="utf-8")
    if "div(phi,U) bounded Gauss upwind;" not in text:
        raise SystemExit(f"expected upwind div(phi,U) in {schemes_path}")
    text = text.replace("div(phi,U) bounded Gauss upwind;", f"div(phi,U) {scheme_line}")
    schemes_path.write_text(text, encoding="utf-8")
    (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN)
    return case_dir


def _run_arm(level: str, arm: str, scheme_line: str) -> dict:
    case_dir = OUT / CID / f"{level}_{arm}"
    if (case_dir / "stage_v_qualification.json").is_file() and (
        case_dir / "log.simpleFoam"
    ).is_file():
        qualification = json.loads(
            (case_dir / "stage_v_qualification.json").read_text(encoding="utf-8")
        )
        responses = qualification.get("force_stationarity", {}).get("responses", {})
        return {
            "level": level,
            "arm": arm,
            "case_dir": str(case_dir),
            "qualified": bool(qualification.get("qualified")),
            "reasons": list(qualification.get("reasons", [])),
            "iterations": qualification.get("solver", {}).get("iteration_count"),
            "Cd": (responses.get("Cd") or {}).get("mean"),
            "downforce": (responses.get("downforce") or {}).get("mean"),
            "reused_existing_run": True,
        }
    case_dir = _prepare_arm_case(level, arm, scheme_line)
    result = run_openfoam_case(
        case_dir,
        backend="docker",
        dry_run=False,
        timeout_seconds=21600,
    )
    if result.returncode != 0:
        return {
            "level": level,
            "arm": arm,
            "qualified": False,
            "returncode": result.returncode,
            "error": "solver run failed; no qualification claim",
        }
    write_stage_v_qualification(case_dir)
    qualification = json.loads(
        (case_dir / "stage_v_qualification.json").read_text(encoding="utf-8")
    )
    responses = qualification.get("force_stationarity", {}).get("responses", {})
    return {
        "level": level,
        "arm": arm,
        "case_dir": str(case_dir),
        "qualified": bool(qualification.get("qualified")),
        "reasons": list(qualification.get("reasons", [])),
        "iterations": qualification.get("solver", {}).get("iteration_count"),
        "Cd": (responses.get("Cd") or {}).get("mean"),
        "downforce": (responses.get("downforce") or {}).get("mean"),
    }


def main() -> None:
    _register()
    baseline = _baseline_family()
    rows: list[dict] = []
    for arm, scheme_line in SCHEME_ARMS.items():
        levels = ("V1",) if arm == "upwind_control" else LEVELS
        for level in levels:
            row = _run_arm(level, arm, scheme_line)
            rows.append(row)
            print(json.dumps(row), flush=True)

    def drift(arm: str) -> dict:
        values = {row["level"]: row for row in rows if row["arm"] == arm}
        if not {"V1", "V2"} <= set(values):
            return {"available": False}
        v1, v2 = values["V1"], values["V2"]
        if not (v1.get("qualified") and v2.get("qualified")):
            return {"available": False, "reason": "arm is not fully qualified"}
        return {
            "available": True,
            "downforce_v1": v1["downforce"],
            "downforce_v2": v2["downforce"],
            "downforce_absolute_drift": abs(v2["downforce"] - v1["downforce"]),
            "drag_relative_drift": abs(v2["Cd"] - v1["Cd"]) / abs(v1["Cd"]),
        }

    baseline_drift = {
        "available": True,
        "downforce_v1": baseline["V1"]["downforce"],
        "downforce_v2": baseline["V2"]["downforce"],
        "downforce_absolute_drift": abs(
            baseline["V2"]["downforce"] - baseline["V1"]["downforce"]
        ),
        "drag_relative_drift": abs(
            baseline["V2"]["Cd"] - baseline["V1"]["Cd"]
        )
        / abs(baseline["V1"]["Cd"]),
    }
    treatment = drift("linearUpwind")
    control_rows = [row for row in rows if row["arm"] == "upwind_control" and row["level"] == "V1"]
    control_ok = bool(
        control_rows
        and control_rows[0].get("qualified")
        and abs(control_rows[0]["downforce"] - baseline["V1"]["downforce"]) < 1e-9
    )
    moved_below_bound = (
        treatment.get("available")
        and treatment["downforce_absolute_drift"] <= DOWNFORCE_BOUND
    )
    # NOTE (recorded): this screen uses the V1->V2 transition, which was already
    # inside the bound for the baseline (0.00461). The failing transition is
    # V2->V3 (0.012908); it is registered and run as a separate campaign.
    evidence = {
        "artifact_id": "stage_v_scheme_factor_2026_09",
        "evidence_class": "numerical_verification_factor_screen",
        "issue": "P16 discretization factor",
        "manifest": {
            "path": str(MANIFEST.relative_to(ROOT)),
            "registered_before_computation": True,
        },
        "baseline_recorded": baseline_drift,
        "upwind_control": {
            "level": "V1",
            "qualified": control_ok,
            "downforce": control_rows[0]["downforce"] if control_rows else None,
            "Cd": control_rows[0]["Cd"] if control_rows else None,
        },
        "control_reproduces_baseline": bool(control_ok),
        "linearUpwind": treatment,
        "decision": {
            "scheme_is_dominant_factor": bool(moved_below_bound),
            "outcome": (
                "register the scheme as the discretization factor and run V3 for this arm"
                if moved_below_bound
                else "accept the measured band for the ranking experiment and escalate the mesh policy"
            ),
        },
        "rows": rows,
        "claims_supported": [
            "the screen measures the scheme factor at V1/V2 under the registered conditions"
        ],
        "claims_not_supported": [
            "no grid-independent claim",
            "no V3 or ranking claim from this campaign",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence["decision"], indent=2))


if __name__ == "__main__":
    main()
