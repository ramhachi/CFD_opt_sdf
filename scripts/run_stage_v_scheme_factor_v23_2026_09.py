"""Registered V2->V3 finest-transition screen for the Stage V scheme factor.

The V1->V2 screen (`stage_v_scheme_factor_2026_09`) showed the first-order
upwind scheme changes the level values materially but that transition was
already inside the bound (baseline 0.00461). The failing transition is V2->V3
(baseline 0.012908). This campaign registers the finest-transition metric
before running and reuses the recorded V1/V2 linearUpwind runs; only the V3
linearUpwind arm is new.
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
BASELINE_EVIDENCE = ROOT / "docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json"
SCREEN_EVIDENCE = ROOT / "docs/evidence/stage_v_scheme_factor_2026_09.json"
PREVIOUS_ROOT = ROOT / "work/stage_v_scheme_factor_2026_09"
OUT = ROOT / "work/stage_v_scheme_factor_v23_2026_09"
MANIFEST = ROOT / "docs/evidence/stage_v_scheme_factor_v23_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_scheme_factor_v23_2026_09.json"
CID = "opt_q100_b0_step0_try0_block"
TREATMENT_SCHEME = "bounded Gauss linearUpwind grad(U);"
DOWNFORCE_BOUND = 0.005
DRAG_RELATIVE_BOUND = 0.02


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register() -> None:
    manifest = {
        "kind": "stage_v_scheme_factor_v23_manifest",
        "created": "2026-09-21",
        "registered_before_computation": True,
        "supersedes": (
            "stage_v_scheme_factor_manifest_2026_09.json used the V1->V2 "
            "transition, which was already inside the bound; that screen is "
            "closed and retained as recorded"
        ),
        "hypothesis": (
            "the failing V2->V3 downforce drift (baseline 0.012908) is "
            "dominated by the first-order upwind convection scheme"
        ),
        "factor": {
            "name": "div(phi,U) convection scheme",
            "baseline": "bounded Gauss upwind",
            "treatment": "bounded Gauss linearUpwind grad(U)",
        },
        "transition": "V2 -> V3 (finest registered transition)",
        "reused_runs": {
            "V1_linearUpwind": str(
                (PREVIOUS_ROOT / CID / "V1_linearUpwind").relative_to(ROOT)
            ),
            "V2_linearUpwind": str(
                (PREVIOUS_ROOT / CID / "V2_linearUpwind").relative_to(ROOT)
            ),
        },
        "new_runs": ["V3_linearUpwind"],
        "metric": {
            "downforce_absolute_drift": "|downforce(V3) - downforce(V2)|",
            "drag_relative_drift": "|Cd(V3) - Cd(V2)| / |Cd(V2)|",
            "bounds": {
                "downforce_absolute": DOWNFORCE_BOUND,
                "drag_relative": DRAG_RELATIVE_BOUND,
            },
        },
        "decision": (
            "if the treatment's finest drift is inside both bounds, register the "
            "second-order scheme as the discretization factor for the qualified "
            "reference family; otherwise escalate the mesh-convergence policy"
        ),
        "stop_conditions": [
            "a failed V3 qualification is reported as failed, never dropped",
            "no further grid level is added in this campaign",
        ],
        "budget": {"new_runs": 1, "finest_cells_estimate": 1348281},
        "inputs": {
            "baseline_evidence": {
                "path": str(BASELINE_EVIDENCE.relative_to(ROOT)),
                "sha256": _sha256(BASELINE_EVIDENCE),
            },
            "v1v2_screen": {
                "path": str(SCREEN_EVIDENCE.relative_to(ROOT)),
                "sha256": _sha256(SCREEN_EVIDENCE),
            },
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _prepare_v3_case() -> Path:
    source = BASELINE_ROOT / CID / "V3"
    if not source.is_dir():
        raise SystemExit(f"baseline V3 case is missing: {source}")
    case_dir = OUT / CID / "V3_linearUpwind"
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
    text = text.replace("div(phi,U) bounded Gauss upwind;", f"div(phi,U) {TREATMENT_SCHEME}")
    schemes_path.write_text(text, encoding="utf-8")
    (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN)
    return case_dir


def _read_arm(case_dir: Path, level: str, arm: str) -> dict:
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
    baseline_document = json.loads(BASELINE_EVIDENCE.read_text(encoding="utf-8"))
    baseline_family = baseline_document["plain_fixed_domain_family"]
    v2_case = PREVIOUS_ROOT / CID / "V2_linearUpwind"
    v3_case = OUT / CID / "V3_linearUpwind"

    if not (v3_case / "stage_v_qualification.json").is_file():
        v3_case = _prepare_v3_case()
        result = run_openfoam_case(
            v3_case, backend="docker", dry_run=False, timeout_seconds=21600
        )
        if result.returncode != 0:
            EVIDENCE.write_text(
                json.dumps(
                    {
                        "artifact_id": "stage_v_scheme_factor_v23_2026_09",
                        "qualified": False,
                        "error": "V3 treatment run failed; no conclusion",
                        "returncode": result.returncode,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise SystemExit("V3 treatment run failed")
        write_stage_v_qualification(v3_case)

    v2 = _read_arm(v2_case, "V2", "linearUpwind")
    v3 = _read_arm(v3_case, "V3", "linearUpwind")
    treatment_drift = {
        "available": bool(v2["qualified"] and v3["qualified"]),
        "downforce_v2": v2["downforce"],
        "downforce_v3": v3["downforce"],
        "downforce_absolute_drift": abs(v3["downforce"] - v2["downforce"]),
        "drag_relative_drift": abs(v3["Cd"] - v2["Cd"]) / abs(v2["Cd"]),
    }
    baseline_drift = {
        "downforce_v2": float(baseline_family["V2"]["downforce"]),
        "downforce_v3": float(baseline_family["V3"]["downforce"]),
        "downforce_absolute_drift": abs(
            float(baseline_family["V3"]["downforce"])
            - float(baseline_family["V2"]["downforce"])
        ),
        "drag_relative_drift": abs(
            float(baseline_family["V3"]["Cd"]) - float(baseline_family["V2"]["Cd"])
        )
        / abs(float(baseline_family["V2"]["Cd"])),
    }
    inside = (
        treatment_drift["available"]
        and treatment_drift["downforce_absolute_drift"] <= DOWNFORCE_BOUND
        and treatment_drift["drag_relative_drift"] <= DRAG_RELATIVE_BOUND
    )
    evidence = {
        "artifact_id": "stage_v_scheme_factor_v23_2026_09",
        "evidence_class": "numerical_verification_factor_screen",
        "issue": "P16 discretization factor (finest transition)",
        "manifest": {
            "path": str(MANIFEST.relative_to(ROOT)),
            "registered_before_computation": True,
        },
        "baseline_finest_transition": baseline_drift,
        "treatment_finest_transition": treatment_drift,
        "decision": {
            "second_order_scheme_is_the_factor": bool(inside),
            "outcome": (
                "register the second-order scheme for the qualified reference family"
                if inside
                else "escalate the mesh-convergence policy"
            ),
        },
        "rows": [v2, v3],
        "claims_supported": [
            "the finest-transition screen measures the scheme factor under the registered conditions"
        ],
        "claims_not_supported": [
            "no grid-independent claim beyond V3",
            "no ranking or target-physics claim",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence["decision"], indent=2))


if __name__ == "__main__":
    main()
