"""Register the v7 campaign manifest (volume-cap correction, resume at v6 end).

Immutable registration before the v7 entry preflight: pins the v6 final
checkpoint, the v6 outcome, the D2/D1 evidence, the current source tree and
the v7 entry-preflight script. Refuses to overwrite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

V6_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v6_2026_09.json"
V6_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v6_outcome_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v7_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v7_2026_09.json"
V6_CAMPAIGN = ROOT / "work/pq3_3b_campaign_v6"


def _v6_final_rho() -> tuple[Path, dict]:
    pointer = ca.load_json(V6_CAMPAIGN / "latest.json")
    state = ca.load_json(V6_CAMPAIGN / pointer["state_path"])
    rho_path = V6_CAMPAIGN / state["rho_path"]
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != state["rho_sha256"]:
        raise SystemExit("v6 final rho hash mismatch")
    return rho_path, state


def build() -> dict:
    v6 = ca.load_json(V6_MANIFEST)
    rho_path, state = _v6_final_rho()
    return {
        "kind": "pq3_3b_campaign_manifest_v7",
        "schema_version": 6,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": v6["plan"],
        "previous_registrations": {
            "manifest_v6": {"path": str(V6_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V6_MANIFEST)},
            "campaign_v6_outcome": {"path": str(V6_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V6_OUTCOME)},
        },
        "pinned_evidence": {
            "campaign_v6_outcome": {"path": str(V6_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V6_OUTCOME)},
            "manifest_v6": {"path": str(V6_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V6_MANIFEST)},
            "change_manifest_d2": {"path": str(D2_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(D2_MANIFEST)},
            "discriminant_outcome_d1": {"path": str(D1_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(D1_OUTCOME)},
        },
        "change": {
            "id": "objective-oc-inequality-v1+volume-cap-correction",
            "description": (
                "the inequality policy gains the active-set volume-cap correction: when the sign step "
                "would exceed Vmax, the largest uniform downward offset inside the move box that keeps "
                "V <= Vmax is bisected before the norm gate, bracket and trial"
            ),
            "evidence": {
                "v6_outcome": str(V6_OUTCOME.relative_to(ROOT)),
                "v6_final_projected_volume": 0.07562221522434376,
                "v6_stop_reason": "every alpha exceeded the projected-volume upper bound",
            },
            "unchanged": [
                "Phase 1 restoration, the sign-step ladder, freeze policy, Path B epsilon/noise, thresholds",
            ],
        },
        "input_stop_state": {
            "level": v6["input_stop_state"]["level"],
            "source": "v6 final accepted checkpoint",
            "checkpoint_index": state["checkpoint_index"],
            "rho_path": str(rho_path.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(rho_path),
            "rho_sha256": state["rho_sha256"],
        },
        "registered_inputs": v6["registered_inputs"],
        "openfoam_image": v6["openfoam_image"],
        "openfoam_image_id": v6["openfoam_image_id"],
        "objective": v6["objective"],
        "phase1_policy": v6["phase1_policy"],
        "phase2_policy": {
            **v6["phase2_policy"],
            "volume_cap_correction": True,
        },
        "filter_radius_m": v6["filter_radius_m"],
        "projection_eta": v6["projection_eta"],
        "registered_target": v6["registered_target"],
        "v_max_projected": v6["v_max_projected"],
        "volume_tolerance": v6["volume_tolerance"],
        "levels": v6["levels"],
        "path_b": v6["path_b"],
        "noise_thresholds": v6["noise_thresholds"],
        "convergence": v6["convergence"],
        "reject_stop_count": v6["reject_stop_count"],
        "restoration_step_cap": v6["restoration_step_cap"],
        "resume_rule": v6["resume_rule"],
        "terminal_rule": v6["terminal_rule"],
        "output_directory": "work/pq3_3b_campaign_v7",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v7_entry_preflight_2026_09.json",
            "requirement": "must pass before the v7 campaign; the campaign additionally requires the user go for long runs",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "no long campaign result, no terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v7 manifest already exists")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "input_rho": manifest["input_stop_state"]["rho_sha256"]}))


if __name__ == "__main__":
    main()
