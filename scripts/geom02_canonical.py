#!/usr/bin/env python3
"""GEOM-02 (#29) canonical run: the v2 geometry gate bundle on the v17 baseline and on the LOWDIM-03 parent.  Solver-free.

Run once, after register_geom02_profile.py and its commit.  Verifies input hashes and the registered profile/policy, requires the
A1 surface-hash reproduction of the saved XFID baseline surface, writes docs/evidence/geom02_v17_gates_2026_10_14/geom02_gate_artifact.json
(+ .sha256) once and refuses to overwrite.  ``--check`` re-derives everything (runtime fields excluded) and compares.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import build_xfid45_stage_v_input_2026_10_04 as bx  # noqa: E402
import register_geom02_profile as reg  # noqa: E402
import xfid45_round3_export as ex  # noqa: E402
from cfd_sdf.design.geometry_gates_v2 import evaluate_geometry_gates_v2  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402

INPUTS = reg.EV / "p22_v17_volume_semantics_bridge_2026_10_11/inputs"
ARTIFACT = reg.OUT / "geom02_gate_artifact.json"
BASELINE_NPZ_SHA = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
PARENT_NPZ_SHA = "0ce3256b0f3e5c919caeb2ac1b36f1a33838f34c767c091cb89bda0234ac750b"
XFID_STATE = reg.EV / "xfid01_geometry_preflight_2026_10_03/canonical_state.npz"
XFID_SURFACE = reg.EV / "xfid45_surface_round3_2026_10_03/surfaces/r8/baseline/surface.npz"
XFID_SURFACE_ARRAY_SHA = "e337541d7497e51a465ef3bb9e650760d85af7161bdddcc36fa5bd161d5084be"  # raw_array_sha256, Round 3 result.json, baseline r=8
PROFILE_SHA256 = "af3d74c883e4071904483a8d365d1a9bb9206717c49c0bf429da5867cd0f9f9d"  # registered by register_geom02_profile.py before the canonical run
POLICY_SHA256 = "b5bcc8c742cb9c09988a80b7e42374c7d7f9bdfccce5c5acb8713cc9204375c8"


def array_sha(vertices, faces) -> str:
    return hashlib.sha256(vertices.astype("<f8").tobytes() + faces.astype("<i8").tobytes()).hexdigest()


def export_from_arrays(vertices, faces, phi, origin, h, *, min_diagonal_m, extracted_triangles=None, refinement=None) -> dict:
    """XFID practical pipeline on a mesh: remove sub-cell components (D2), orient by phi sidedness, audit topology."""
    v, f, removed = bx.remove_small_components(vertices, faces, min_diagonal_m)
    oriented, audit = ex.orient(v, f, phi, np.asarray(origin, dtype=np.float64), h)
    return {
        "vertices": v, "faces": oriented, "topology": ex.topology(v, oriented), "orientation_status": audit["status"],
        "orientation_flips": sum(c["whole_component_flipped"] for c in audit["components"]), "removed_components": removed,
        "extracted_triangles": len(faces) if extracted_triangles is None else extracted_triangles, "refinement": refinement,
    }


def export_from_state(state: SDFDesignState, profile: dict) -> dict:
    r = profile["export"]["refinement"]
    v, f, _ = ex.extract(state.phi, state.origin_m, state.spacing_m, r)
    return export_from_arrays(v, f, state.phi, state.origin_m, state.spacing_m, refinement=r,
                              min_diagonal_m=profile["export"]["small_component_min_bbox_diagonal_m"])


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"integrity failure: {msg}")


def derive() -> dict:
    require(reg.sha_file(INPUTS / "v17_baseline.npz") == BASELINE_NPZ_SHA, "v17 baseline npz hash")
    require(reg.sha_file(INPUTS / "lowdim03_parent.npz") == PARENT_NPZ_SHA, "LOWDIM-03 parent npz hash")
    require(reg.sha_file(XFID_STATE) == BASELINE_NPZ_SHA, "XFID canonical_state.npz is not byte-identical to the v17 baseline")
    profile, policy_reg = reg.build()
    require(reg.sha_file(reg.PROFILE) == PROFILE_SHA256 and reg.sha_file(reg.POLICY) == POLICY_SHA256, "registered profile/policy hash")
    require(reg.PROFILE.read_text() == reg.dump(profile) and reg.POLICY.read_text() == reg.dump(policy_reg), "profile/policy no longer re-derive")
    require(importlib.metadata.version("scikit-image") == "0.25.2", "scikit-image version")
    policy = SDFTopologyPolicyResearchV2.from_dict(policy_reg["policy"])
    require(policy.state_binding_id == profile["policy"]["state_binding_id"], "policy binding")
    baseline, parent = (SDFDesignState.load(INPUTS / n) for n in ("v17_baseline.npz", "lowdim03_parent.npz"))

    v, f, _ = ex.extract(baseline.phi, baseline.origin_m, baseline.spacing_m, profile["export"]["refinement"])
    oriented, _ = ex.orient(v, f, baseline.phi, np.asarray(baseline.origin_m), baseline.spacing_m)
    saved = np.load(XFID_SURFACE)
    a1 = {"extract_orient_array_sha256": array_sha(v, oriented), "expected_xfid_raw_array_sha256": XFID_SURFACE_ARRAY_SHA,
          "identical_to_saved_surface_arrays": bool(np.array_equal(saved["vertices"], v) and np.array_equal(saved["faces"], oriented))}
    require(a1["extract_orient_array_sha256"] == XFID_SURFACE_ARRAY_SHA and a1["identical_to_saved_surface_arrays"], f"A1 surface reproduction {a1}")
    exports = {"baseline": export_from_arrays(v, oriented, baseline.phi, baseline.origin_m, baseline.spacing_m, min_diagonal_m=profile["export"]["small_component_min_bbox_diagonal_m"],
                                              extracted_triangles=len(f), refinement=profile["export"]["refinement"])}
    exports["lowdim03_parent"] = export_from_state(parent, profile)
    states = {"baseline": (baseline, baseline), "lowdim03_parent": (parent, baseline)}  # (state, transition parent)
    return {
        "kind": "geom02_v17_gate_artifact",
        "evidence_class": "contract_and_capability",
        "contract_id": "sdf_native_geometry_gates_v2",
        "inputs": {"v17_baseline_npz_sha256": BASELINE_NPZ_SHA, "lowdim03_parent_npz_sha256": PARENT_NPZ_SHA, "profile_sha256": PROFILE_SHA256,
                   "policy_registration_sha256": POLICY_SHA256, "flow_box_source_sha256": profile["domain_source"]["sha256"]},
        "environment": {name: importlib.metadata.version(name) for name in ("scikit-image", "numpy", "scipy")},
        "a1_surface_reproduction": a1,
        "states": {name: evaluate_geometry_gates_v2(s, parent_state=p, profile=profile, policy=policy, export_mesh=exports[name]) for name, (s, p) in states.items()},
        "flags": reg.FLAGS,
        "claims_not_supported": reg.NOT_SUPPORTED,
        "solver_started": False,
    }


def strip_runtime(value):
    if isinstance(value, dict):
        return {k: strip_runtime(v) for k, v in value.items() if k != "runtime_s"}
    if isinstance(value, list):
        return [strip_runtime(v) for v in value]
    return value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    require(PROFILE_SHA256 and POLICY_SHA256, "profile/policy hash constants are not set")
    if args.check:
        sidecar = ARTIFACT.with_name(ARTIFACT.name + ".sha256").read_text().split()[0]
        require(sidecar == reg.sha_file(ARTIFACT), "artifact sidecar")
        require(strip_runtime(json.loads(reg.dump(derive()))) == strip_runtime(json.loads(ARTIFACT.read_text())), "artifact does not re-derive")
        print("check ok", sidecar)
        return
    artifact = derive()
    print(reg.write_once(ARTIFACT, artifact))
    for name, bundle in artifact["states"].items():
        print(name, "pass" if bundle["verdict"]["pass"] else "NOT PASS", {k: bundle["verdict"][k] for k in ("failed", "unmeasured")})


if __name__ == "__main__":
    main()
