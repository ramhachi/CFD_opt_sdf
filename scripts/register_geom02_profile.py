#!/usr/bin/env python3
"""Register the GEOM-02 (#29) gate profile and the resolved research topology policy instance.  Solver-free.

Writes docs/evidence/geom02_v17_gates_2026_10_14/{geom02_gate_profile,geom02_resolved_research_policy}.json (+ .sha256) once and
refuses to overwrite; ``--check`` re-derives both and compares them to the files.  Run before the canonical run (geom02_canonical.py).
Thresholds are non-blind (v16/v17 values are known) and fixed here; a change is a new profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402

EV = ROOT / "docs/evidence"
OUT = EV / "geom02_v17_gates_2026_10_14"
PROFILE, POLICY = OUT / "geom02_gate_profile.json", OUT / "geom02_resolved_research_policy.json"
JULIA = ROOT / "julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl"
CLEARANCE_SOURCE = EV / "xfid45_surface_round3_2026_10_03/preregistration.json"
POLICY_PREDECESSOR = EV / "sdf_topology_policy_v2_research_2026_10_14.json"
H = V2.SPACING_M
FLAGS = {"sdf_gradient_qualified": False, "shape_update_allowed": False, "topology_birth_qualified": False,
         "waterlily_reverse_cpu_qualified": False, "waterlily_reverse_cuda_qualified": False}
NOT_SUPPORTED = ["manufacturing or physical feature qualification", "export certification at 0.5 mm", "cavity or tunnel topology control", "any shape-update permission", "grid-independent downforce or FSAE qualification"]


def sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + "\n"


def write_once(path: Path, obj) -> str:
    """Write ``obj`` and its .sha256 sidecar; refuse to overwrite either."""
    sidecar = path.with_name(path.name + ".sha256")
    if path.exists() or sidecar.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(obj))
    digest = sha_file(path)
    sidecar.write_text(f"{digest}  {path.name}\n")
    return digest


def flow_box() -> list[list[float]]:
    """Registered WaterLily flow domain (FLOW_ORIGIN_M, BASE_MAX_M), parsed from the pinned Julia source."""
    text = JULIA.read_text()
    box = [[float(x) for x in re.search(rf"const {name} = \(([^)]*)\)", text).group(1).split(",")] for name in ("FLOW_ORIGIN_M", "BASE_MAX_M")]
    if box != [[-2.5, -1.2, -0.9], [2.5, 1.2, 0.9]]:
        raise SystemExit(f"unexpected flow box {box}")
    return box


def build() -> tuple[dict, dict]:
    policy = SDFTopologyPolicyResearchV2(minimum_solid_width_m=1.5 * H, minimum_void_width_m=1.5 * H, minimum_gap_m=2.5 * H)
    label = "lattice representability limit (research), not a physical or manufacturing minimum"
    policy_reg = {
        "kind": "sdf_topology_policy_registration",
        "registration_id": "sdf_topology_policy_v2_research_resolved_geom02_2026_10_14",
        "evidence_class": "contract",
        "immutable": True,
        "policy": policy.to_dict(),
        "state_binding_id": policy.state_binding_id,
        "limits": {"minimum_solid_width_m": "1.5h", "minimum_void_width_m": "1.5h", "minimum_gap_m": "2.5h", "h_m": H, "label": label,
                   "reading": "a resolved instance is a new content-addressed policy (#31 record); physical limits remain unregistered and would be a further new policy"},
        "source_problem_spec": "absent: the v17 genesis (sdf_native_genesis_v17_2026_09.json) binds no ProblemSpec; not inferred",
        "predecessor_unresolved_registration": {"path": str(POLICY_PREDECESSOR.relative_to(ROOT)), "sha256": sha_file(POLICY_PREDECESSOR)},
        "authority": "user blanket delegation of 2026-10-13, read as an interpretation (as #31 did); an explicit later user decision supersedes it",
        "non_blind": "v16/v17 measured widths are known; 2h was the observed minimum and was not used (circular)",
        "flags": FLAGS,
        "claims_not_supported": NOT_SUPPORTED,
        "solver_started": False,
    }
    prereg = json.loads(CLEARANCE_SOURCE.read_text())["clearance"]
    profile = {
        "kind": "sdf_native_geometry_gate_profile",
        "schema_version": 1,
        "profile_id": "geom02_v17_research_gates_2026_10_14",
        "contract_id": "sdf_native_geometry_gates_v2",
        "plan": "docs/geom02_plan_2026_10_14.md (with Amendment 1)",
        "evidence_class": "contract_and_capability",
        "non_blind": "v16 values and v17 values in SRCMAP-03a/LOWDIM records and read-only plan-review measurements are known; thresholds are not tuned after the canonical run",
        "eikonal_median_tolerance": 0.10,
        "zero_level_gradient_floor": 0.5,
        "boundary_margin_cells": 1,
        "domain_bounds_m": flow_box(),
        "domain_source": {"path": str(JULIA.relative_to(ROOT)), "sha256": sha_file(JULIA), "constants": ["FLOW_ORIGIN_M", "BASE_MAX_M"]},
        "min_clearance_m": prereg["minimum_m"],
        "clearance_source": {"path": str(CLEARANCE_SOURCE.relative_to(ROOT)), "sha256": sha_file(CLEARANCE_SOURCE), "key": "clearance.minimum_m",
                             "flow_box_m": prereg["flow_box_m"]},
        "max_solid_centers": V2.MAX_SOLID_CENTERS,
        "lattice": {"origin_m": list(V2.ORIGIN_M), "spacing_m": V2.SPACING_M, "node_shape": list(V2.NODE_SHAPE)},
        "volume_source": {"registration_id": V2.REGISTRATION_ID, "contract_sha256": V2.CONTRACT_SHA256},
        "allowed_events": [],
        "birth_qualified": False,
        "export": {"refinement": 8, "small_component_min_bbox_diagonal_m": H, "extractor": "scikit-image 0.25.2 Lewiner via scripts/xfid45_round3_export.py extract",
                   "decisions": "XFID user decisions D2 (small components) and D3 (r=8), 2026-10-04",
                   "self_intersection_tolerance_rel": 1e-12,
                   "self_intersection_tolerance_note": "contact tolerance as a fraction of the mesh extent; P20 uses 1e-10, whose absolute value reports a phantom contact on needle triangles (tests/test_geometry_gates_v2.py); 1e-12 and 1e-14 gave the same verdict on the saved v17 baseline r=8 surface"},
        "policy": {"registration_id": policy_reg["registration_id"], "state_binding_id": policy.state_binding_id, "policy_sha256": policy.policy_sha256},
        "labels": {"widths_and_gap": label},
        "flags": FLAGS,
        "claims_not_supported": NOT_SUPPORTED,
        "solver_started": False,
    }
    return profile, policy_reg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    profile, policy = build()
    if args.check:
        for path, obj in ((PROFILE, profile), (POLICY, policy)):
            side = path.with_name(path.name + ".sha256").read_text().split()[0]
            if path.read_text() != dump(obj) or side != sha_file(path):
                raise SystemExit(f"check failed: {path}")
        print("check ok", sha_file(PROFILE), sha_file(POLICY))
        return
    print("profile", write_once(PROFILE, profile))
    print("policy", write_once(POLICY, policy))


if __name__ == "__main__":
    main()
