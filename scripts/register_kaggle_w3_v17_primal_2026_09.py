"""Register W3 round 1 for the canonical v17 SDF (#43) before execution.

The measurement contract, backend identity, profile adapter, fixture selection and
gates are the registered W3 v16 round-4 contract, built by the unchanged v16
registrar code.  Only the canonical-state identity is replaced: v17 genesis
(same source surface and design box as v16, design lattice h/2).  v16 values are
not gates; a v16 comparison is diagnostic only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import register_kaggle_w3_v16_primal_2026_09 as base  # noqa: E402

LABEL = "v17"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v17-genesis-state"
OUTPUT = ROOT / "docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json"
V17_GENESIS = ROOT / "docs/evidence/sdf_native_genesis_v17_2026_09.json"
V17_GENESIS_SCRIPT = ROOT / "scripts/sdf_native_genesis_v17_2026_09.py"
V17_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
RAW_NAME = f"canonical_{LABEL}_phi_f4_fortran.raw"


def zero_level_margin_m(phi: np.ndarray, spacing: float) -> float:
    """Same definition as the host verifier and GridSDFBody.zero_level_margin_m."""
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing for n in phi.shape]
    face = np.minimum(np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]), gaps[2][None, None, :])
    solid = phi < 0
    return float(np.min(face[solid] + phi[solid]))


def build_criteria(source_commit: str) -> dict:
    from cfd_sdf.design.sdf_state import SDFDesignState

    criteria = base.build_criteria(source_commit, criteria_round=4)
    genesis = json.loads(V17_GENESIS.read_text())
    if base.sha256(V17_STATE) != genesis["state"]["state_file_sha256"]:
        raise ValueError("v17 state NPZ does not match its genesis evidence")
    state = SDFDesignState.load(V17_STATE)
    if state.state_sha256 != genesis["state"]["state_sha256"] or state.phi_sha256() != genesis["state"]["phi_sha256"]:
        raise ValueError("v17 state identity does not match its genesis evidence")
    phi = np.asarray(state.phi, dtype="<f4")
    phi_f = hashlib.sha256(np.asarray(phi, order="F").tobytes(order="F")).hexdigest()
    if phi_f != genesis["state"]["phi_f4_fortran_sha256"]:
        raise ValueError("v17 Fortran phi bytes do not match its genesis evidence")
    grid = genesis["grid_identity"]
    margin = zero_level_margin_m(phi.astype(np.float64), grid["spacing_m"])
    if margin < criteria["geometry"]["margin_gate_m"]:
        raise ValueError(f"v17 zero-level margin {margin} fails the registered gate")

    criteria["geometry"].update({
        "state_label": LABEL,
        "point_shape": grid["point_shape"],
        "cell_shape": grid["cell_shape"],
        "spacing_m": grid["spacing_m"],
        "canonical_sdf_origin_m": grid["origin_m"],
        "state_sha256": state.state_sha256,
        "state_npz_sha256": genesis["state"]["state_file_sha256"],
        "phi_c_order_sha256": state.phi_sha256(),
        "phi_fortran_sha256": phi_f,
        "source_surface_sha256": state.source_sha256,
        "expected_margin_m": margin,
        "expected_margin_source": "host numpy zero-level margin of the v17 genesis phi, computed at registration before any solver run",
    })
    criteria["profile_adapter"]["point_shape"] = grid["point_shape"]
    criteria["measurement"]["force_integration_body"] = (
        f"canonical {LABEL} candidate GridSDF only; do not integrate the auxiliary moving-ground half-space"
    )
    inputs = criteria["inputs"]
    inputs["canonical_state_npz"] = {"path": "sdf_design_state.npz", "sha256": genesis["state"]["state_file_sha256"],
                                     "location": "kaggle_dataset"}
    inputs["canonical_phi_fortran_raw"] = {"path": RAW_NAME, "sha256": phi_f, "location": "kaggle_dataset",
                                           "dtype": "float32_little_endian", "order": "Fortran",
                                           "shape": grid["point_shape"]}
    inputs["genesis_evidence"] = base.input_entry(V17_GENESIS)
    inputs["genesis_script"] = base.input_entry(V17_GENESIS_SCRIPT)
    inputs["v16_criteria_registrar"] = inputs.pop("criteria_registrar")
    inputs["criteria_registrar"] = base.input_entry(Path(__file__).resolve())

    criteria.update({
        "criteria_id": "kaggle_w3_v17_primal_2026_09",
        "criteria_round": 1,
        "kind": "waterlily_w3_canonical_primal_criteria",
        "input_dataset_id": DATASET_ID,
        "measurement_contract_source": "kaggle_w3_v16_primal_2026_09_round4 (measurement, backend, profile adapter, fixture selection and gates unchanged)",
        "round_reason": "#36/#43: v16 has 66 force-band cells with near-zero trilinear gradient; v17 resamples the same source surface on an h/2 design lattice. This round re-runs the registered W3 primal contract on v17.",
        "registered_source_commit": source_commit,
        "source_commit": source_commit,
    })
    gates = criteria["acceptance"]["gates"]
    gates[1] = "T1 canonical v17 state, source surface, C/Fortran phi hashes, GPU round-trip and solver grid identity match"
    gates[2] = "T2 CPU-side margin gate is 0.15 m and the measured margin matches the registered v17 value within 1e-6 m"
    criteria["acceptance"]["claim_scope"] = (
        "canonical v17 SDF met the registered integrity, force, and stationarity contract on the registered WaterLily finite-box approximation"
    )
    criteria["acceptance"]["v16_comparison"] = "diagnostic only; v16 force values are not a gate"
    criteria["claims_not_supported"] = criteria["claims_not_supported"] + [
        "v16 W3/W4/FD results transfer to v17",
        "v16 or v17 force values are closer to a body-fitted reference",
    ]
    flags = criteria["flags"]
    flags.pop("waterlily_v16_primal_qualified", None)
    flags["waterlily_v17_primal_qualified"] = False
    return criteria


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--preview", action="store_true", help="print criteria for the current HEAD without writing")
    args = parser.parse_args()
    sidecar = OUTPUT.with_suffix(".json.sha256")
    if args.check:
        if base.sha256(OUTPUT) != sidecar.read_text().strip():
            raise SystemExit("W3 v17 criteria SHA sidecar mismatch")
        print(base.sha256(OUTPUT))
        return 0
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if args.preview:
        print(json.dumps(build_criteria(head), indent=2, sort_keys=True))
        return 0
    if OUTPUT.exists() or sidecar.exists():
        raise SystemExit("W3 v17 criteria already exist; immutable registration will not be overwritten")
    if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise SystemExit("commit and push the W3 v17 source before registering immutable criteria")
    criteria = build_criteria(head)
    OUTPUT.write_text(json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n")
    sidecar.write_text(base.sha256(OUTPUT) + "\n")
    print(json.dumps({"criteria_path": OUTPUT.relative_to(ROOT).as_posix(),
                      "criteria_sha256": base.sha256(OUTPUT), "source_commit": head}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
