#!/usr/bin/env python3
"""Write the scope-limited FD-08 v2 oracle record (no flag changes; no gradient delta is chosen here).

The record binds R6 (calibration), formal AMEND3 (interior interpolation) and the identities GRAD-01 needs
(f64 direction hash, response semantics hash, FD backend fingerprint). It carries no ``fd_oracle`` /
``*_qualified`` true key: the six qualification flags stay literally false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.fd08_v2_campaign import FLAG_NAMES, generate_p1, sha256_json  # noqa: E402
from cfd_sdf.gradients.directional_comparison import field_direction_sha256  # noqa: E402
from cfd_sdf.gradients.directional_fd import direction_sha256, generate_directions  # noqa: E402

EVIDENCE = ROOT / "docs/evidence"
R6 = EVIDENCE / "fd08_v2_r6_2026_10_06"
FORMAL = EVIDENCE / "fd08_v2_formal_2026_10_07_amend3"
PINS = {  # path -> sha256 (verified before use)
    FORMAL / "formal_criteria.json": "31b29cccc9d3fd6912a910b09694a8230f9ee0aa84e6a418161881ffbcf907be",
    FORMAL / "formal_analysis.json": "3da59ac9b1086ed286cb0109cd669dac804f4fb99785986515ce35db1acf0466",
    FORMAL / "formal_terminal_verification.json": "13841237ca95142c45761963c5e61f68310de63ca5f70e3386e6ca465333e6ef",
    FORMAL / "campaign_final.json": "6cd5a22e291eb4d22accb22c1ed8aaf68da3687fcd75eaabf8c985e73bb8f13f",
    R6 / "r6_retry2_analysis.json": "b5d55b77f750f447fd486a600f9e52a66a3f6c2610c5dba5ce6792018cc647be",
    R6 / "r6_retry2_criteria.json": "90e9e40ffebffc96891af12bdc7942a0a038d877fe6e7bffe7a88574679e1837",
}
NPZ_SHA256 = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
OUTPUT = EVIDENCE / "fd08_v2_oracle_scope_record_2026_10_08/record.json"
RESPONSE_DEFINITIONS = {
    "drag": "force on body along +x, N; centered odd response S=(R(+eps)-R(-eps))/2 of the window-mean force",
    "downforce": "force on body along -z, N; centered odd response S=(R(+eps)-R(-eps))/2 of the window-mean force",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(state_path: Path) -> dict:
    for path, expected in PINS.items():
        if sha256_file(path) != expected:
            raise ValueError(f"pinned evidence changed: {path}")
    criteria = json.loads((FORMAL / "formal_criteria.json").read_text())
    r6 = json.loads((R6 / "r6_retry2_analysis.json").read_text())
    if not state_path.is_file() or sha256_file(state_path) != NPZ_SHA256:
        raise FileNotFoundError(f"canonical v17 NPZ unavailable or SHA mismatch: {state_path}")
    state = SDFDesignState.load(state_path)
    if state.state_sha256 != criteria["canonical_state"]["state_sha256"]:
        raise ValueError("canonical state identity mismatch")
    directions = dict(generate_directions(state))
    directions["P1_upstream_lobe"], _ = generate_p1(state)
    f32_expected = criteria["direction_inventory"]["hashes"]
    semantics = {r: sha256_json({"response_id": r, "definition": d, "measurement": criteria["measurement"]})
                 for r, d in RESPONSE_DEFINITIONS.items()}
    fingerprint_source = {"runtime": criteria["runtime"], "operator_identity": criteria["candidate_c_identity"]["operator_identity"],
                          "candidate_c_contract_sha256": criteria["candidate_c_identity"]["contract_sha256"],
                          "body_source_sha256": criteria["candidate_c_identity"]["body_source_sha256"],
                          "formal_source_commit": criteria["source_commit"]}
    rows = []
    for series in r6["series"]:
        direction_id, response = series["direction_id"], series["response"]
        direction = directions[direction_id]
        if direction_sha256(direction) != f32_expected[direction_id]:
            raise ValueError(f"regenerated direction differs from registered hash: {direction_id}")
        rows.append({
            "direction_id": direction_id, "response_id": response,
            "g_hat_n_per_m": series["model_a"]["g_n_per_m"], "se_g_n_per_m": series["model_a"]["se_g_n_per_m"],
            "relative_se": series["relative_se"],
            "direction_sha256_f32_c_order": f32_expected[direction_id],
            "direction_sha256_grad01_f64": field_direction_sha256(np.asarray(direction, dtype=np.float64)),
            "response_semantics_sha256": semantics[response],
            "calibration_epsilon_range_mm": [min(series["epsilon_mm"]), max(series["epsilon_mm"])],
            "estimate_kind": "weighted least-squares slope g of Model A (S = g eps + c eps^3) over the six-point ladder; "
                             "not a single-epsilon difference and not an epsilon-to-zero derivative claim",
        })
    final = json.loads((FORMAL / "campaign_final.json").read_text())
    return {
        "kind": "fd08_v2_oracle_scope_record",
        "evidence_class": "scope_limited_fd_oracle_status_record_unregistered_not_a_flag_change",
        "fd08_v2_scope_limited_oracle_status": "R6_PASS_AND_FORMAL_INTERIOR_INTERPOLATION_PASS_WITHIN_SCOPE",
        "scope": {
            "operator": criteria["candidate_c_identity"]["operator_identity"], "canonical_state_sha256": state.state_sha256,
            "canonical_npz_sha256": NPZ_SHA256, "case": criteria["measurement"]["case"]["case_id"],
            "directions": sorted(f32_expected), "responses": sorted(RESPONSE_DEFINITIONS),
            "calibration_epsilon_range_mm": [0.5, 5.0],
            "formal_interior_epsilon_mm": criteria["formal_epsilon"]["epsilon_mm"],
            "formal_claim": final["evidence_class"], "series_count": len(rows),
        },
        "evidence": {path.name: sha for path, sha in PINS.items()},
        "t2_parameters_sha256": criteria["calibration_binding"]["T2_parameter_sha256"],
        "t2_classification": "arbitrary-provisional diagnostic operating contract; not a gradient error gate",
        "rows": rows,
        "grad01_bridge": {
            "response_semantics_sha256": semantics,
            "response_semantics_rule": "fd08_v2_campaign.sha256_json({response_id, definition, formal measurement block})",
            "fd_backend_fingerprint_sha256": sha256_json(fingerprint_source),
            "fd_backend_fingerprint_rule": "sha256_json of formal runtime block, Candidate C operator/contract/body source hashes and formal source commit",
            "direction_hash_rule": "GRAD-01 field_direction_sha256 over the registered float32 direction cast to float64 (C order)",
            "relative_error_tolerance": None, "absolute_noise_floor": None,
            "gate_note": "no numeric delta is recorded: the GRAD-03 error gate is a separate user decision (see delta options note)",
        },
        "consumption_rules": [
            "only the listed direction/response rows; anything else must fail closed",
            "the six qualification flags below are literal false; a later change needs a separate user decision and new record",
            "a GRAD-01 loader may build CenteredDirectionalFD(qualified=True) from a row only after verifying every cited SHA and supplying its own registered gate",
        ],
        "not_claimed": final["not_claimed"],
        "qualification_flags": {name: False for name in FLAG_NAMES},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, default=DEFAULT_STATE)
    p.add_argument("--output", type=Path, default=OUTPUT)
    args = p.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    data = (json.dumps(build(args.state), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    args.output.with_name(args.output.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
