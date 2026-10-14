#!/usr/bin/env python3
"""REINIT-04 (#28): the unchanged registered Godunov2 operator on the v17 baseline and the LOWDIM-03 parent.  Solver-free.

Plan: docs/reinit04_plan_2026_10_15.md with Amendment 1 (B1-B7 override the plan text).  Committed before the run (preregistration); the
verdict rule below does not change afterwards.  Run once; writes docs/evidence/reinit04_v17_2026_10_15/result.json (+ .sha256) once and
refuses to overwrite; output NPZs go under ignored work/reinit04_v17/ with their sha256 bound.  ``--check`` re-derives (runtime excluded).

Verdict (per state, ``state_verdict``): pass iff every operator gate passes (unchanged ``canonical`` tolerances), every GEOM-02 gate that
passed on the input (artifact 899aeb7c) still passes on the output as a transition from its input (allowed_events=()), and N_phi <= 8272.
``near_zero_gradient_band`` is never in the verdict.  The LOWDIM-03 parent alone decides (``decide``); the baseline is reported separately.
INCOMPLETE on a pin/hash mismatch, exception or non-finite output.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import geom02_canonical as canon  # noqa: E402
import geom02_gradient_floor_diagnostic as diag  # noqa: E402
import register_geom02_profile as reg  # noqa: E402
from cfd_sdf.design import volume_semantics_v2 as V2  # noqa: E402
from cfd_sdf.design.geometry_gates_v2 import evaluate_geometry_gates_v2  # noqa: E402
from cfd_sdf.design.sdf_reinitialization import (  # noqa: E402
    DEGENERATE_EDGE_SUM_M,
    REINIT_CONTRACT_SHA256,
    TOLERANCES,
    _axis_slices,
    edge_crossings,
    reinitialize_sdf,
)
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.topology_policy_research import SDFTopologyPolicyResearchV2  # noqa: E402
from cfd_sdf.design.volume_semantics import _corner_mean, sampled_solid_centers_count  # noqa: E402

OUT = reg.EV / "reinit04_v17_2026_10_15"
RESULT = OUT / "result.json"
WORK = ROOT / "work/reinit04_v17"
OPERATOR_SOURCE = ROOT / "src/cfd_sdf/design/sdf_reinitialization.py"
CONTRACT_SHA256 = "9895ab008e880ea65b30bbf01ab2489c62ad655ee911f9f237e300a118cc4f98"
GEOM02_ARTIFACT = canon.ARTIFACT
GEOM02_ARTIFACT_SHA256 = "899aeb7c58d35b835887b83f77cc88f4bfe84c8c03d7dc0cc40391bebe24fb6b"
STATES = (("baseline", "v17_baseline", canon.BASELINE_NPZ_SHA), ("lowdim03_parent", "lowdim03_parent", canon.PARENT_NPZ_SHA))
NOT_IN_VERDICT = ("near_zero_gradient_band",)
N_PHI_LIMIT = V2.MAX_SOLID_CENTERS
COUNT_BUDGET_ONLY = {"n_phi", "geom02:volume_semantics"}
COUNT_BUDGET_NOTE = "count budget, not operator quality"
INCOMPLETE, BOUNDED, NOT_BOUNDED = "REINIT04_INCOMPLETE", "REINIT04_BOUNDED_ON_PARENT", "REINIT04_NOT_BOUNDED_ON_PARENT"


def state_verdict(op_gates: dict, input_status: dict, output_status: dict, n_phi_output: int) -> dict:
    """Preregistered per-state rule.  A GEOM-02 gate that did not pass on the input is not required on the output."""
    failed = [f"operator:{g}" for g, v in op_gates.items() if not v["passed"]]
    failed += [f"geom02:{g}" for g, s in input_status.items() if s == "pass" and g not in NOT_IN_VERDICT and output_status.get(g) != "pass"]
    failed += ["n_phi"] * (n_phi_output > N_PHI_LIMIT)
    return {"pass": not failed, "failed": failed, "note": COUNT_BUDGET_NOTE if failed and set(failed) <= COUNT_BUDGET_ONLY else None}


def decide(states: dict) -> dict:
    """The LOWDIM-03 parent alone decides; the baseline (tie-bearing genesis case) is reported separately and never feeds the verdict."""
    parent, baseline = states["lowdim03_parent"], states["baseline"]
    name = INCOMPLETE if "incomplete" in parent else BOUNDED if parent["verdict"]["pass"] else NOT_BOUNDED
    return {"verdict": name, "decided_by": "lowdim03_parent",
            "parent": parent.get("incomplete") or parent["verdict"],
            "baseline_separate": {"incomplete": baseline["incomplete"]} if "incomplete" in baseline else baseline["verdict"]}


def edge_displacement(before: SDFDesignState, after: SDFDesignState) -> dict:
    """Zero-level crossing displacement (in edges) on common crossing edges, split by degenerate (|phi| sum < 1e-7 m) vs other input edges."""
    cb, ca = edge_crossings(before.phi, before.solid_mask), edge_crossings(after.phi, after.solid_mask)
    absolute, parts = np.abs(before.phi.astype(np.float64)), {"degenerate": [], "non_degenerate": []}
    for axis, ((m0, t0, _), (m1, t1, _)) in enumerate(zip(cb, ca)):
        lo, hi = _axis_slices(axis)
        degenerate, common, d = m0 & (absolute[lo] + absolute[hi] < DEGENERATE_EDGE_SUM_M), m0 & m1, np.abs(t0 - t1)
        parts["degenerate"].append(d[common & degenerate])
        parts["non_degenerate"].append(d[common & ~degenerate])
    limit = TOLERANCES["zero_level_displacement_max_edges"]
    out = {"limit_edges": limit, "input_degenerate_crossing_edges": sum(c for _, _, c in cb)}
    for k, v in parts.items():
        d = np.concatenate(v)
        out[k] = {"common_edges": int(d.size), "max": float(d.max()) if d.size else None, "mean": float(d.mean()) if d.size else None, "over_limit": int((d > limit).sum())}
    return out


def n_phi_change(before: SDFDesignState, after: SDFDesignState) -> dict:
    b, a = _corner_mean(before.phi) < 0.0, _corner_mean(after.phi) < 0.0
    nb, na = sampled_solid_centers_count(before), sampled_solid_centers_count(after)
    return {"input": nb, "output": na, "signed_change": na - nb, "limit": N_PHI_LIMIT, "margin_input": N_PHI_LIMIT - nb,
            "centres_lost": int((b & ~a).sum()), "centres_gained": int((~b & a).sum()), "flipped_total": int((b != a).sum())}


def transitions(input_gates: dict, output_gates: dict) -> dict:
    """Every GEOM-02 gate whose status differs from the input's, with the output's reasons (B4/B6)."""
    return {g: {"input": input_gates[g]["status"], "output": o["status"], "fail_reasons": o["fail_reasons"], "unmeasured_reasons": o["unmeasured_reasons"],
                "input_measured": input_gates[g]["measured"], "output_measured": o["measured"]}
            for g, o in output_gates.items() if o["status"] != input_gates[g]["status"]}


def evaluate_state(state: SDFDesignState, input_bundle: dict, profile: dict, policy: SDFTopologyPolicyResearchV2) -> tuple[dict, SDFDesignState]:
    t0 = time.time()
    result = reinitialize_sdf(state, profile="canonical", fail_closed=False)
    out, report = result.state, result.report
    if not np.isfinite(out.phi).all():
        raise ValueError("non-finite output phi")
    floor = profile["zero_level_gradient_floor"]
    bundle = evaluate_geometry_gates_v2(out, parent_state=state, profile=profile, policy=policy, export_mesh=canon.export_from_state(out, profile))
    input_status = {g: v["status"] for g, v in input_bundle["gates"].items()}
    output_status = {g: v["status"] for g, v in bundle["gates"].items()}
    n_phi = n_phi_change(state, out)
    in_vol = input_bundle["gates"]["export_surface_integrity"]["measured"]["mesh_signed_volume_m3"]
    out_vol = bundle["gates"]["export_surface_integrity"]["measured"]["mesh_signed_volume_m3"]
    doc = {
        "input": {"state_sha256": state.state_sha256, "phi_sha256": state.phi_sha256()},
        "output": {"state_sha256": out.state_sha256, "phi_sha256": out.phi_sha256()},
        "operator_report": report,
        "zero_level_displacement": edge_displacement(state, out),
        "n_phi": n_phi,
        "geom02": {"input_status": input_status, "output_status": output_status, "transitions": transitions(input_bundle["gates"], bundle["gates"]), "output_bundle": bundle},
        "solid_side_eikonal": {"input": report["measured"]["eikonal_input"]["solid"], "output": report["measured"]["eikonal_output"]["solid"],
                               "note": "recorded, not gated: the canonical profile gates the fluid side only"},
        "export_mesh_signed_volume_m3": {"input": in_vol, "output": out_vol, "relative_change": (out_vol - in_vol) / in_vol},
        "gradient_floor_failing_nodes": {"floor": floor, "input": diag.classify(state, floor), "output": diag.classify(out, floor)},
        "verdict": state_verdict(report["gates"], input_status, output_status, n_phi["output"]),
        "runtime_s": time.time() - t0,
    }
    return json.loads(reg.dump(doc)), out  # round trip: fails on non-finite values, normalises types


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(f"pin mismatch: {msg}")


def context() -> tuple[dict, SDFTopologyPolicyResearchV2, dict]:
    profile, policy_reg = reg.build()
    need(reg.sha_file(reg.PROFILE) == canon.PROFILE_SHA256 and reg.sha_file(reg.POLICY) == canon.POLICY_SHA256, "registered profile/policy hash")
    need(reg.PROFILE.read_text() == reg.dump(profile) and reg.POLICY.read_text() == reg.dump(policy_reg), "profile/policy no longer re-derive")
    need(reg.sha_file(GEOM02_ARTIFACT) == GEOM02_ARTIFACT_SHA256, "GEOM-02 artifact hash")
    need(REINIT_CONTRACT_SHA256 == CONTRACT_SHA256, "operator contract payload hash")
    need(importlib.metadata.version("scikit-image") == "0.25.2", "scikit-image version")
    return profile, SDFTopologyPolicyResearchV2.from_dict(policy_reg["policy"]), json.loads(GEOM02_ARTIFACT.read_text())["states"]


def derive() -> tuple[dict, dict]:
    states, outputs = {}, {}
    try:
        profile, policy, artifact = context()
        error = None
    except Exception as e:  # noqa: BLE001 - any failure is INCOMPLETE by rule
        error = f"{type(e).__name__}: {e}"
    for name, npz, sha in STATES:
        try:
            if error:
                raise RuntimeError(error)
            need(reg.sha_file(canon.INPUTS / f"{npz}.npz") == sha, f"{npz}.npz hash")
            states[name], outputs[name] = evaluate_state(SDFDesignState.load(canon.INPUTS / f"{npz}.npz"), artifact[name], profile, policy)
        except Exception as e:  # noqa: BLE001
            states[name] = {"incomplete": f"{type(e).__name__}: {e}"}
    m = {n: s.get("zero_level_displacement") for n, s in states.items()}
    b, p = states["baseline"], states["lowdim03_parent"]
    prediction = None if not all(m.values()) else {
        "statement": "baseline fails zero_level_displacement_edges_max through its degenerate edges; the parent is not exposed to that mechanism",
        "baseline_gate_fails": not b["operator_report"]["gates"]["zero_level_displacement_edges_max"]["passed"],
        "baseline_degenerate_max_over_limit": m["baseline"]["degenerate"]["over_limit"] > 0,
        "baseline_non_degenerate_max_within_limit": m["baseline"]["non_degenerate"]["over_limit"] == 0,
        "parent_degenerate_edges": m["lowdim03_parent"]["input_degenerate_crossing_edges"],
        "parent_gate_passes": p["operator_report"]["gates"]["zero_level_displacement_edges_max"]["passed"],
    }
    if prediction:
        prediction["held"] = (prediction["baseline_gate_fails"] and prediction["baseline_degenerate_max_over_limit"]
                              and prediction["baseline_non_degenerate_max_within_limit"] and prediction["parent_degenerate_edges"] == 0)
    doc = {
        "kind": "reinit04_v17_result",
        "evidence_class": "contract_and_capability",
        "plan": "docs/reinit04_plan_2026_10_15.md (with Amendment 1)",
        "operator": {"contract_id": "sdf_native_reinitialization_godunov2_v2", "contract_payload_sha256": CONTRACT_SHA256, "source_sha256": reg.sha_file(OPERATOR_SOURCE),
                     "call": "reinitialize_sdf(state, profile='canonical', fail_closed=False)", "tolerances": TOLERANCES},
        "inputs": {"v17_baseline_npz_sha256": canon.BASELINE_NPZ_SHA, "lowdim03_parent_npz_sha256": canon.PARENT_NPZ_SHA, "geom02_profile_sha256": canon.PROFILE_SHA256,
                   "geom02_policy_registration_sha256": canon.POLICY_SHA256, "geom02_artifact_sha256": GEOM02_ARTIFACT_SHA256},
        "environment": {name: importlib.metadata.version(name) for name in ("scikit-image", "numpy", "scipy")},
        "states": states,
        "decision": decide(states),
        "b3_prediction": prediction,
        "flags": reg.FLAGS,
        "claims_not_supported": reg.NOT_SUPPORTED + ["a qualified reinitialization operator in general", "any optimizer descent", "gradient-floor gate resolved"],
        "solver_started": False,
    }
    return doc, outputs


def npz_record(name: str) -> dict:
    path = WORK / f"{name}_reinit.npz"
    return {"path": str(path.relative_to(ROOT)), "sha256": reg.sha_file(path)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    check = ap.parse_args().check
    if not check:
        canon.require(not RESULT.exists() and not any(WORK.glob("*_reinit.npz")), "refusing to overwrite a previous run")
    doc, outputs = derive()
    if check:
        stored = json.loads(RESULT.read_text())
        sidecar = RESULT.with_name(RESULT.name + ".sha256").read_text().split()[0]
        canon.require(sidecar == reg.sha_file(RESULT), "result sidecar")
        records = stored.pop("output_npz")
        canon.require(canon.strip_runtime(json.loads(reg.dump(doc))) == canon.strip_runtime(stored), "result does not re-derive")
        for name, out in outputs.items():  # NPZ zip bytes are not deterministic; bind the file hash and the state it holds
            canon.require(npz_record(name) == records[name], f"{name} output npz hash")
            canon.require(SDFDesignState.load(ROOT / records[name]["path"]).state_sha256 == out.state_sha256, f"{name} output npz state")
        print("check ok", sidecar)
        return
    for name, out in outputs.items():
        out.save(WORK / f"{name}_reinit.npz")
    doc["output_npz"] = {name: npz_record(name) for name in outputs}
    print(reg.write_once(RESULT, doc))
    print(doc["decision"]["verdict"], "baseline:", doc["decision"]["baseline_separate"])


if __name__ == "__main__":
    main()
