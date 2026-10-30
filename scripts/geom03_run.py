#!/usr/bin/env python3
"""GEOM-03 prospective-protocol study run (scripts/geom03_run.py).

Authority: docs/geom03_registration_2026_10_23.md plus
docs/evidence/geom03_2026_10_23/known_inputs.json. This file owns the exact 180-base-row
input enumeration, the candidate evaluation engine and the serial, append-only,
budget-gated run state machine. Its default CLI reports metadata/counts only: no arrays,
no RNG, no registered schedule.

Shared interface with the independently owned checker scripts/geom03_check.py

    evaluate_pair(phi, parent_phi, masks, h, policy, origin_m=(0,0,0)) -> plain dict:
        "r0": {"solid": float|None, "void": float|None, "status": pass|unmeasured|fail}
        "r3": same value shape; None = empty body, infinity written as the JSON string "inf"
        "p1": {"parent_margin_m": float, "candidate_margin_m": float, "status": pass|fail}
        "p2": {"statuses": {gate_id: status}, "events": [str],
               "parent_components": int|None, "candidate_components": int|None,
               "empty_masks": [str]}
        "composite": pass / unmeasured / fail / blocked
    ``masks`` holds the bool arrays design_mask/fixed_solid_mask/forbidden_mask/root_mask;
    ``h`` is the actual lattice spacing (metres) and ``origin_m`` the actual lattice origin
    (never a forged (0,0,0) when a real origin exists). The checker defines
    check_pair(phi, parent_phi, masks, h, policy[, origin_m]) and
    check_run(workdir, regdict) -> {"verdict", "complete", "criteria",
    "incomplete_reasons", "counterexamples"}; it writes NOTHING itself. Both are imported
    lazily only when delivered; a study result is never its oracle.

Input NPZ (inputs/<row_id>.npz): phi, parent_phi, design_mask, fixed_solid_mask,
forbidden_mask, root_mask, origin_m, spacing_m, spec_json (strict-JSON string, no pickle);
v18 combos also carry basis_<i>_<mode> float32 arrays. Raw input NPZs are cached only
while the observed RSS is below 3 GiB; old hash reconstructions are never retained.

Row JSON lines (append-only work/geom03_2026_10_23/rows.jsonl): id, family, kind base|k6,
spec, prospective expectation, origin_m, spacing_m, field_identity (phi/parent Fortran SHA
+ grid/mask identities), parent_kind, input_npz + input_npz_sha256, halo {parent,
candidate} (both required on ordinary scored rows; the K5 finite-array contract is the
only exception; diagnostics carry None), candidate dict, k6 info (scale, base_id, unscaled
p1, sign body hashes), diagnostic or historical fields, family-specific feature
observables. K6 row ids are ``<base_id>@k6_0.5`` / ``<base_id>@k6_2`` in spec, NPZ path
and rows; the resume prefix is the full interleaved base+K6 enumeration (534 ids).
Distances: None (empty), finite float, JSON string "inf"; NaN/Infinity never written.

Registration/release gating (strict; booleans or arbitrary nonempty files never grant a run):
    registration.json  {schema: "geom03_registration_v1", status: "REGISTERED_FROZEN",
        source_commit: <40-hex>, code_tree_identity: <64-hex>,
        source_files: [{path, sha256}...] covering all pinned sources below,
        review_records: [{path, sha256}...] covering the plan-review artefacts,
        runtime_versions: {"python","numpy","scipy"}, expected_count: 180,
        formal_plan_review_completed: true, source_review_completed: true}
        - every REQUIRED_SOURCE_PIN / REQUIRED_REVIEW_PIN must be listed and its recorded
          sha256 must match the file bytes exactly;
        - runtime_versions must equal the running python/numpy/scipy versions exactly.
    execution_release.json {schema: "geom03_execution_release_v1",
        purpose: "FID01_GO_R3_VALIDATION" | "M4_GEOMETRY_NEED",
        registration_sha256, basis_file, basis_sha256, reason: <non-empty>,
        resource_evidence: {...}}
    work state state.json {schema: "geom03_run_state_v1", run_started_epoch (null during
        preparation, then original cumulative start including downtime), fingerprint,
        attempts (0 before input generation, then 1: one scientific
        attempt), resume_count (separate; the parent/child handoff is NOT a resume),
        launch_token, status, observations}
        rows.jsonl append-only; results.json is written ONCE by this runner (x-mode)
        after the single independent check_run call; stop_reason.json is written once
        (x-mode, first reason retained) for engineering/terminal stops.

Gates before ANY registered input generation: valid frozen registration with all pins, recorded
release, no active host mount AND no running Docker container bind-mount whose source
contains work/fid01_of_out (both probed; any unavailable probe fails closed), load1 <= 4,
memory evidence >= 3 GiB, and delivered checker. Missing dependency/resource evidence =>
WAITING_FOR_DEPENDENCY / WAITING_FOR_RESOURCES: no attempt consumed, no fields generated.
One attempt; only a NONTERMINAL interrupted attempt resumes from verified append-only
artefacts with identical identities and the ORIGINAL start time (downtime included; no
fresh 2 h). Any pre-existing terminal stop/result is refused even if a stale state file
still says RUNNING. Terminal records are never resumed or retried. <= 2 h wall cumulative;
<= 3 GiB observed RSS (live `ps -o rss= -p <child pid>` sampling of the own supervised
child, start-up included); one numerical worker with library threads pinned to 1; the
parent watchdog terminates only its own supervised child, and a controller lock
(work/child.lock, fail-closed on a live recorded pid) prevents a parallel child launch.

Disjointness: the 99 known native and all 250 reconstructed old-combination input
identities (exact original W.combo_phi left-to-right semantics and the recorded old noise
stream; input arithmetic only, no old outcome replay) are compared with the actual 28 new
combination schedule/input identities, all generated and recorded BEFORE any new outcome.
Only the new v18 combinations need this check: the synthetic 27^3 arrays differ from every
old input by grid/shape/dtype, and H0 is a known native field by definition.

K6: two extra evaluations per non-diagnostic scored row (c = 0.5 and 2.0): R0/R3/P2 status
and R3 sampled sign bodies compared; P1 is recorded only in the original metre-valued phi
and the composite is recomputed with that unscaled P1. 180 base rows => 354 K6 rows;
D1/E1/E2 carry no K6.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import width_rule_study as W  # noqa: E402  (registered helpers, imported never modified)
from cfd_sdf.design.geometry_gates import LENGTH_TOLERANCE_M  # noqa: E402  (registered, unchanged)
from cfd_sdf.design.geometry_gates_v2 import _topology_gates  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import _corner_mean  # noqa: E402

DOC = ROOT / "docs/geom03_registration_2026_10_23.md"
EVIDENCE = ROOT / "docs/evidence/geom03_2026_10_23"
KNOWN_INPUTS = EVIDENCE / "known_inputs.json"
REGISTRATION = EVIDENCE / "registration.json"
RELEASE = EVIDENCE / "execution_release.json"
POLICY = ROOT / "docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json"
POLICY_SHA256 = "d4cd9aa42f0062923cdc8713d14d10fd334888a3c9dd5db9be15f7ac9d378d41"
PRESCREEN = ROOT / "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json"
V18_GENESIS_NPZ = ROOT / "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz"
OLD_SWEEP = ROOT / "docs/evidence/width_rule_2026_10_20/v18_phase_sweep.json"
SUPERVISE_ENV = "GEOM03_SUPERVISED_CHILD"
LAUNCH_ENV = "GEOM03_LAUNCH_TOKEN"
WORK = ROOT / "work/geom03_2026_10_23"
SCHEMA_REG, SCHEMA_RELEASE, SCHEMA_STATE, SCHEMA_STOP = (
    "geom03_registration_v1", "geom03_execution_release_v1", "geom03_run_state_v1", "geom03_stop_reason_v1")
SCHEMA_RESULTS = "geom03_results_v1"
PURPOSES = ("FID01_GO_R3_VALIDATION", "M4_GEOMETRY_NEED")
EXPECTED_COUNT, K6_SCALES, K6_DIAGNOSTIC_SKIPPED = 180, (0.5, 2.0), ("d1", "e1", "e2")
H = W.H
BUDGET_RSS = 3 * 1024 ** 3
BUDGET_WALL_S = 2 * 3600.0
LOAD_LIMIT = 4.0
FID_MOUNT_NEEDLE = "work/fid01_of_out"
P2_NARROW_BAND_CELLS = 8.0  # valid positive container width for the same-grid P2 states
TOPOLOGY_GATE_IDS = ("mask_preservation", "component_connectivity", "topology_change_classification")
ORDER = {"pass": 0, "unmeasured": 1, "fail": 2, "blocked": 3}
FAMILY_COUNTS = {"k1_analytic": 24, "k1_combos": 28, "k2_k3_controls": 76, "k4_controls": 8,
                 "diagnostics": 3, "k5_slabs": 40, "historical": 1}
DIAGNOSTIC_FAMILY = "diagnostics"
K6_EXPECTED = 2 * (EXPECTED_COUNT - 3)  # 354
H0_R0_RECORD = {"solid": 0.09762812094883319, "void": None, "status": "pass"}
H0_PHI_SHA256 = "29d53b2318c54548da321f265aa2102d59e24d96bbd04fb2dd70d62fbc10c82a"
REQUIRED_SOURCE_PINS = (
    ("docs/geom03_registration_2026_10_23.md", "doc"),
    ("docs/evidence/geom03_2026_10_23/known_inputs.json", "known input/task bindings"),
    ("docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json", "v18 basis source"),
    ("docs/evidence/width_rule_2026_10_20/v18_phase_sweep.json", "old task stream (250 combos)"),
    ("docs/evidence/v18_genesis_2026_10_19/v18_parent.npz", "frozen v18 parent"),
    ("docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json", "policy"),
    ("scripts/width_rule_study.py", "registered helpers"),
    ("scripts/geom03_run.py", "this study script"),
    ("scripts/geom03_check.py", "independent checker"),
    ("tests/test_geom03.py", "development regression"),
    ("scripts/mode01_v18_prescreen.py", "registered state_phi builder"),
    ("scripts/mode01_modes.py", "builder state/mask helpers"),
    ("scripts/v18_plate.py", "analytic and harness builders"),
    ("docs/evidence/v18_genesis_2026_10_19/genesis.json", "parent parameters"),
    ("src/cfd_sdf/design/sdf_state.py", "P2 state container"),
    ("src/cfd_sdf/design/topology_policy.py", "topology overlap implementation"),
    ("src/cfd_sdf/design/topology_policy_research.py", "research topology implementation"),
    ("src/cfd_sdf/design/geometry_gates.py", "registered R0 estimator"),
    ("src/cfd_sdf/design/geometry_gates_v2.py", "registered P2 gates"),
    ("src/cfd_sdf/design/volume_semantics.py", "registered corner arithmetic"),
    ("src/cfd_sdf/fd08_v2_campaign.py", "basis harness state construction"),
    ("src/cfd_sdf/gradients/directional_fd.py", "basis harness margin helper"),
    ("src/cfd_sdf/runtime/fingerprint.py", "state hash validation helper"),
)
REQUIRED_REVIEW_PINS = (
    ("docs/evidence/geom03_2026_10_23/plan_review.json", "formal plan review record"),
    ("docs/evidence/geom03_2026_10_23/plan_review_go_reports.json", "plan review GO reports"),
    ("docs/evidence/geom03_2026_10_23/geometry_review.md", "geometry review record"),
    ("docs/evidence/geom03_2026_10_23/source_review.json", "completed formal source review"),
)
HEX40 = set("0123456789abcdef")
HEX64 = set("0123456789abcdef")

G: dict = {}  # lazy frozen-run context; strictly empty whenever the module is only imported
WAITING_STATUSES = ("WAITING_FOR_DEPENDENCY", "WAITING_FOR_RESOURCES")
WAITING_EXIT = 75


class ProtocolError(Exception):
    """An input/spec/checker error path; makes the experiment INCOMPLETE, never a rejection."""


def phi_sha(phi) -> str:
    return hashlib.sha256(np.asarray(phi, "<f4").tobytes(order="F")).hexdigest()


def mask_sha(mask) -> str:
    return hashlib.sha256(np.asarray(mask, bool).tobytes(order="F")).hexdigest()


def jsonable(x):
    """Strict-JSON-safe conversion: inf -> "inf", None kept, NaN refused, Path -> str."""
    if isinstance(x, (float, np.floating)) and math.isnan(x):
        raise ProtocolError("NaN is not representable; never write it")
    if isinstance(x, (float, np.floating)) and math.isinf(x):
        return "inf"
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    if isinstance(x, Path):
        return str(x)
    return x


def worst(*statuses: str) -> str:
    return max(statuses, key=ORDER.get)


def observed_rss_bytes() -> int | None:
    """Live RSS of the current process from the OS, start-up included."""
    try:
        proc = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            return int(proc.stdout.split()[-1]) * 1024
    except Exception:  # noqa: BLE001 - fall through to getrusage
        pass
    try:
        import resource
        val = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(val if sys.platform == "darwin" else val * 1024)
    except Exception:  # noqa: BLE001
        return None


def assert_rss_budget() -> None:
    """No raw target input is cached while the observed RSS is at/past the 3 GiB budget."""
    observed = observed_rss_bytes()
    if observed is None or observed > BUDGET_RSS:
        raise ProtocolError("RSS is unavailable or exceeds the 3 GiB budget")
    if G.get("controller_pid") is not None and os.getppid() != G["controller_pid"]:
        raise ProtocolError("supervising controller is no longer the numerical child's parent")
    if G.get("started") is not None and time.time() - G["started"] > BUDGET_WALL_S:
        raise ProtocolError("cumulative wall budget exhausted (including downtime)")


# ---------------------------------------------------------------- protocol gates (doc section 2)
def r0_of_phi(phi, h: float = H):
    """Registered R0 driven by the source float32 _corner_mean cell-centre occupancy."""
    return W.r0(_corner_mean(np.asarray(phi, "<f4")) < 0.0, float(h))


def r3_of_phi(phi, h: float = H):
    return W.r3(np.asarray(phi, "<f4"), float(h))


def p1_gate(phi, parent_phi, masks, h) -> dict:
    active = masks["design_mask"] & ~masks["fixed_solid_mask"] & ~masks["forbidden_mask"] & ~masks["root_mask"]
    frozen = ~active
    if not frozen.any():
        raise ProtocolError("empty frozen node mask is an input error, not infinity or a pass")
    parent_m = float(np.abs(np.asarray(parent_phi, "<f4")[frozen]).min())
    cand_m = float(np.abs(np.asarray(phi, "<f4")[frozen]).min())
    return {"parent_margin_m": parent_m, "candidate_margin_m": cand_m,
            "status": "pass" if (parent_m >= h / 2.0 and cand_m >= h / 2.0) else "fail"}


def _p2_state(phi, masks, h, policy, origin_m=(0.0, 0.0, 0.0)) -> SDFDesignState:
    """Same-grid state bound to the resolved research policy: a valid positive 8h narrow
    band and the actual origin alone do not register the state; the policy binding does."""
    return SDFDesignState.create(
        phi=np.asarray(phi, "<f4"), origin_m=tuple(float(v) for v in origin_m), spacing_m=float(h),
        design_mask=masks["design_mask"], fixed_solid_mask=masks["fixed_solid_mask"],
        forbidden_mask=masks["forbidden_mask"], root_mask=masks["root_mask"],
        narrow_band_width_m=P2_NARROW_BAND_CELLS * float(h), generation=0,
        topology_policy_id=policy.state_binding_id)


def p2_gate(phi, parent_phi, masks, h, policy, origin_m=(0.0, 0.0, 0.0)) -> dict:
    st_c = _p2_state(phi, masks, h, policy, origin_m)
    st_p = _p2_state(parent_phi, masks, h, policy, origin_m)
    cand = _topology_gates(st_c, st_p, policy, (), False)
    par = _topology_gates(st_p, st_p, policy, (), False)
    return {
        "statuses": {g: worst(cand[g]["status"], par[g]["status"]) for g in TOPOLOGY_GATE_IDS},
        "events": sorted(cand["topology_change_classification"]["measured"].get("detected_events", ())),
        "parent_components": par["component_connectivity"]["measured"]["node_occupancy_components"],
        "candidate_components": cand["component_connectivity"]["measured"]["node_occupancy_components"],
        "empty_masks": list(cand["mask_preservation"]["measured"].get("empty_masks", ())),
    }


def composite_status(r3_status: str, p2_statuses, p1_status: str) -> str:
    """P1 violation is blocked; otherwise worst R3/P2 with pass < unmeasured < fail."""
    if p1_status == "fail":
        return "blocked"
    return worst(r3_status, worst(*p2_statuses), p1_status)


def evaluate_pair(phi, parent_phi, masks, h, policy, origin_m=(0.0, 0.0, 0.0)) -> dict:
    """Shared registered pair evaluation: descriptive R0, gating R3, P1, P2, composite."""
    for a in (phi, parent_phi):
        if not isinstance(a, np.ndarray) or a.dtype != np.float32 or a.ndim != 3 or min(a.shape) < 2 or not np.isfinite(a).all():
            raise ProtocolError("candidate and parent must be finite 3D float32 arrays")
    if phi.shape != parent_phi.shape or not math.isfinite(h) or h <= 0:
        raise ProtocolError("candidate/parent grids differ or spacing is invalid")
    for name in MASK_NAMES:
        a = masks.get(name)
        if not isinstance(a, np.ndarray) or a.dtype != bool or a.shape != phi.shape:
            raise ProtocolError(f"invalid mask {name}")
    if len(origin_m) != 3 or not all(math.isfinite(v) for v in origin_m):
        raise ProtocolError("origin must contain three finite coordinates")
    p1 = p1_gate(phi, parent_phi, masks, h)
    p2 = p2_gate(phi, parent_phi, masks, h, policy, origin_m)
    r3 = r3_of_phi(phi, h)
    comp = composite_status(r3["status"], tuple(p2["statuses"].values()), p1["status"])
    return {"r0": r0_of_phi(phi, h), "r3": r3, "p1": p1, "p2": p2, "composite": comp}


def sign_body_hashes(phi) -> dict:
    """Identity of the R3 sampled sign body, for the registered K6 comparison."""
    solid = np.asarray(phi, "<f4") < 0
    if not solid.any():
        return {"solid": None, "void": None}
    refined = W.refine(np.asarray(phi, "<f4")[W.box(solid, W.OPEN_PAD)], W.OPEN_K) < 0.0

    def sha(a):
        return hashlib.sha256(np.asarray(a, bool).tobytes()).hexdigest()

    return {"solid": sha(refined), "void": sha(~refined)}


def has_halo(phi, pad=W.OPEN_PAD):
    """True when the coarse solid AABB padded by three nodes lies inside the array."""
    solid = np.asarray(phi, "<f4") < 0
    if not solid.any():
        return None  # empty solid: not an ordinary scored body
    idx = np.argwhere(solid)
    top = np.asarray(solid.shape) - 1
    return bool(((idx.min(axis=0) - pad) >= 0).all() and ((idx.max(axis=0) + pad) <= top).all())


def halo_pair(phi, parent_phi, family, build) -> dict | None:
    """Ordinary rows require the full three-node coarse solid halo on BOTH candidate and
    specified parent; K5 is the declared finite-array exception; diagnostics are None."""
    if build == "k5":
        return {"rule": "inapplicable_k5_finite_array_contract", "candidate": None, "parent": None}
    if family == DIAGNOSTIC_FAMILY:
        return None
    return {"candidate": bool(has_halo(phi)), "parent": bool(has_halo(parent_phi))}


# ---------------------------------------------------------------- frozen declarative inputs
def load_policy():
    data = json.loads(POLICY.read_text())["policy"]
    import cfd_sdf.design.topology_policy_research as tpr
    policy = tpr.SDFTopologyPolicyResearchV2.from_dict(data)
    if policy.policy_sha256 != POLICY_SHA256:
        raise ProtocolError("resolved topology policy hash does not match the registered one")
    return policy


def sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_input_npz(path: Path, spec_json: str, **arrays) -> None:
    assert_rss_budget()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        np.savez_compressed(stream, spec_json=np.array(spec_json),
                            **{k: np.asarray(v) for k, v in arrays.items()})


def load_input_npz(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k] for k in data.files}


# ---------------------------------------------------------------- masks and analytic builders
def ordinary_masks(n=27) -> dict:
    design = np.zeros((n, n, n), bool)
    design[2:-2, 2:-2, 2:-2] = True
    false = np.zeros((n, n, n), bool)
    return {"design_mask": design, "fixed_solid_mask": false, "forbidden_mask": false.copy(),
            "root_mask": false.copy()}


def k5_masks(n=27) -> dict:
    design = np.zeros((n, n, n), bool)
    design[:, :, 1:-1] = True  # frozen nodes are exactly the z = 0 and z = 26 planes
    false = np.zeros((n, n, n), bool)
    return {"design_mask": design, "fixed_solid_mask": false, "forbidden_mask": false.copy(),
            "root_mask": false.copy()}


def p8(j: int):
    return ((2 * j + 1) / 16 - 0.5, (2 * ((3 * j) % 8) + 1) / 16 - 0.5, (2 * ((5 * j) % 8) + 1) / 16 - 0.5)


Q2 = ((1 / 8, 3 / 16, 5 / 16), (-5 / 16, -3 / 16, -1 / 16))
DEFAULT_CENTER = (13.0, 13.0, 13.0)
A_CENTER = (13.5, 13.0, 13.0)  # A0/A1 boxes are centred at x = 13.5 (registration section 4)


def local_coords(theta_deg, phase, n=27, center=DEFAULT_CENTER):
    """q = R_y(theta).T @ (index - center - phase) as three float64 h-unit arrays."""
    idx = np.indices((n, n, n), dtype=np.float64)
    c = np.asarray(center, float) + np.asarray(phase, float)
    p = idx - c.reshape(3, 1, 1, 1)
    th = math.radians(theta_deg)
    ct, st = math.cos(th), math.sin(th)
    x, y, z = p[0], p[1], p[2]
    return (ct * x - st * z, y, st * x + ct * z)


def box_sdf(qx, qy, qz, b):
    """box(q,b) = norm(max(|q|-b,0)) + min(max(|q|-b),0) over components."""
    d0, d1, d2 = np.abs(qx) - b[0], np.abs(qy) - b[1], np.abs(qz) - b[2]
    outside = np.sqrt(np.maximum(d0, 0.0) ** 2 + np.maximum(d1, 0.0) ** 2 + np.maximum(d2, 0.0) ** 2)
    return outside + np.minimum(np.maximum(np.maximum(d0, d1), d2), 0.0)


def product(d, v):
    """2D signed distance d x interval distance v."""
    return np.minimum(np.maximum(d, v), 0.0) + np.hypot(np.maximum(d, 0.0), np.maximum(v, 0.0))


def _wedge_planar(x, z, theta_deg):
    """Signed h-unit planar distance to the closed wedge polygon; negative exactly inside."""
    t = math.tan(math.radians(theta_deg) / 2)
    a = min(8 * t, 2.5)
    v = 4 - a / t
    verts = [(-4.0, -a), (v, -a), (4.0, 0.0), (v, a), (-4.0, a)]
    poly = []
    for pv in verts:
        if not poly or (pv[0] != poly[-1][0] or pv[1] != poly[-1][1]):
            poly.append(pv)
    while len(poly) > 1 and poly[0] == poly[-1]:
        poly.pop()
    d = None
    for i in range(len(poly)):
        (x0, z0), (x1, z1) = poly[i], poly[(i + 1) % len(poly)]
        ex, ez = x1 - x0, z1 - z0
        denom = ex * ex + ez * ez
        s = 0.0 if denom == 0 else np.clip(((x - x0) * ex + (z - z0) * ez) / denom, 0.0, 1.0)
        seg = np.sqrt((x - x0 - s * ex) ** 2 + (z - z0 - s * ez) ** 2)
        d = seg if d is None else np.minimum(d, seg)
    inside = (x >= -4) & (x <= 4) & (np.abs(z) <= np.minimum((4 - x) * t, 2.5))
    return np.where(inside, -d, d)


def _bar(x, y, z):
    return product(np.hypot(x, z) - 2.75, np.abs(y) - 3.5)


def _stadium(x, y, z):
    return product(np.hypot(np.maximum(np.abs(x) - 5.0, 0.0), z) - 2.75, np.abs(y) - 3.5)


def _thickbox(x, y, z):
    return box_sdf(x, y, z, (4.5, 3.5, 2.5))


SHAPE_H = {
    "S": lambda q, w: box_sdf(q[0], q[1], q[2], (4.5, 4.0, w / 2)),
    "V": lambda q, w: np.maximum(box_sdf(q[0], q[1], q[2], (6.5, 6.5, 5.5)),
                                 -box_sdf(q[0], q[1], q[2], (w / 2, 4.25, 3.5))),
    "Vopen": lambda q, w: np.maximum(box_sdf(q[0], q[1], q[2], (6.5, 6.5, 5.5)),
                                     -box_sdf(q[0], q[1], q[2] - 3.5, (w / 2, 4.25, 4.0))),
    "N": lambda q, d: np.minimum(np.minimum(np.sqrt((q[0] - 4.75) ** 2 + q[1] ** 2 + q[2] ** 2) - 2.5,
                                            np.sqrt((q[0] + 4.75) ** 2 + q[1] ** 2 + q[2] ** 2) - 2.5),
                                 product(np.hypot(q[1], q[2]) - d / 2, np.abs(q[0]) - 4.75)),
    "F1": lambda q: np.minimum(box_sdf(q[0], q[1], q[2], (3.5, 3.0, 2.5)),
                               box_sdf(q[0] - 3.625, q[1], q[2], (0.375, 1.5, 0.5))),
    "F2": lambda q: np.minimum(box_sdf(q[0], q[1], q[2], (3.5, 3.0, 2.5)),
                               box_sdf(q[0] - 5.625, q[1], q[2], (2.375, 1.5, 0.5))),
    "A": lambda q, g: np.minimum(box_sdf(q[0] - (2 + g / 2), q[1], q[2], (2.0, 2.5, 2.5)),
                                 box_sdf(q[0] + (2 + g / 2), q[1], q[2], (2.0, 2.5, 2.5))),
    "W": lambda q, deg: product(_wedge_planar(q[0], q[2], deg), np.abs(q[1]) - 3.0),
}
K1_FIELDS = {"bar": _bar, "stadium": _stadium, "thickbox": _thickbox}
ANALYTIC_FIELDS = {
    "S1": lambda q: SHAPE_H["S"](q, 0.875), "S2": lambda q: SHAPE_H["S"](q, 1.125),
    "S3": lambda q: SHAPE_H["S"](q, 4.75), "T1": lambda q: SHAPE_H["S"](q, 1.625),
    "T2": lambda q: SHAPE_H["S"](q, 1.875),
    "V1": lambda q: SHAPE_H["V"](q, 0.875), "V2": lambda q: SHAPE_H["V"](q, 1.125),
    "V3": lambda q: SHAPE_H["V"](q, 3.5),
    "V4": lambda q: SHAPE_H["Vopen"](q, 0.875), "V5": lambda q: SHAPE_H["Vopen"](q, 3.5),
    "N0": lambda q: SHAPE_H["N"](q, 2.5), "N1": lambda q: SHAPE_H["N"](q, 0.875),
    "N2": lambda q: SHAPE_H["N"](q, 0.375),
    "F_base": lambda q: box_sdf(q[0], q[1], q[2], (3.5, 3.0, 2.5)),  # F1/F2 parent: the base box
    "F1": lambda q: SHAPE_H["F1"](q), "F2": lambda q: SHAPE_H["F2"](q),
    "A0": lambda q: SHAPE_H["A"](q, 2.5), "A1": lambda q: SHAPE_H["A"](q, 0.25),
    "W20": lambda q: SHAPE_H["W"](q, 20.0), "W40": lambda q: SHAPE_H["W"](q, 40.0),
    "W60": lambda q: SHAPE_H["W"](q, 60.0), "W90": lambda q: SHAPE_H["W"](q, 90.0),
}
# Explicit ordered 19 control ids (76 = 19 x 2 theta x 2 Q2 rows); never dict enumeration.
CONTROL19 = ("S1", "S2", "S3", "V1", "V2", "V3", "V4", "V5", "N0", "N1", "N2",
             "F1", "F2", "W20", "W40", "W60", "W90", "T1", "T2")
CONTROL_PARENT = {"N1": "N0", "N2": "N0", "F1": "F_base", "F2": "F_base"}


def analytic_field(name, theta_deg, phase, n=27, center=DEFAULT_CENTER) -> np.ndarray:
    """A registered analytic field: float64 h-units evaluated once, cast once to <f4."""
    q = local_coords(theta_deg, phase, n, center)
    if name in K1_FIELDS:
        vals = K1_FIELDS[name](*q)
    elif name in ANALYTIC_FIELDS:
        vals = ANALYTIC_FIELDS[name](q)
    else:
        raise ProtocolError(f"unknown analytic field {name}")
    return (vals * H).astype("<f4")


MASK_NAMES = ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")


def canonical(value) -> str:
    return json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path):
    return read_json_line(Path(path).read_text())


def read_json_line(line):
    def unique(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ProtocolError(f"duplicate JSON key {key}")
            out[key] = value
        return out

    def bad_constant(value):
        raise ProtocolError(f"non-finite JSON token {value}")

    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ProtocolError("non-finite JSON number")
        return value
    return json.loads(line, object_pairs_hook=unique, parse_constant=bad_constant, parse_float=finite_float)


def write_json_once(path, value):
    with Path(path).open("x") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_state(work, value):
    tmp = work / "state.json.tmp"
    tmp.write_text(canonical(value) + "\n")
    os.replace(tmp, work / "state.json")


def field_identity(phi, parent_phi, masks, origin_m, h, spec):
    grid = {"shape": list(phi.shape), "dtype": "<f4", "origin_m": list(origin_m), "spacing_m": float(h)}
    return {**grid, "grid_sha256": digest(grid), "phi_fortran_sha256": phi_sha(phi),
            "parent_fortran_sha256": phi_sha(parent_phi),
            "mask_fortran_sha256": {n: mask_sha(masks[n]) for n in MASK_NAMES},
            "spec_sha256": digest(spec)}


def base_specs():
    """Exact ordered metadata; no target arrays or RNG is touched here."""
    specs = []
    for shape in ("bar", "stadium", "thickbox"):
        for j in range(8):
            specs.append(dict(id=f"{shape}_p8_{j}", family="k1_analytic", build="analytic",
                              field=shape, theta_deg=0.0, phase=p8(j), parent_field="identity"))
    for i in range(28):
        specs.append(dict(id=f"C{i:02d}", family="k1_combos", build="v18_combo", combo_index=i))
    for name in CONTROL19:
        parent = "fin_parent" if name in ("F1", "F2") else CONTROL_PARENT.get(name, "identity")
        for ti, theta in enumerate((0.0, 45.0)):
            for qi, phase in enumerate(Q2):
                specs.append(dict(id=f"{name}_th{ti}_q{qi}", family="k2_k3_controls", build="analytic",
                                  field=name, theta_deg=theta, phase=phase, parent_field=parent))
    for qi, phase in enumerate(Q2):
        for name in ("R0", "R1"):
            specs.append(dict(id=f"{name}_q{qi}", family="k4_controls", build="margin_control", field="bar",
                              theta_deg=0.0, phase=phase, corner_phi_h=H / 2 if name == "R0" else 0.3 * H,
                              parent_field="identity" if name == "R0" else "R0"))
        for name in ("A0", "A1"):
            specs.append(dict(id=f"{name}_q{qi}", family="k4_controls", build="analytic", field=name,
                              theta_deg=0.0, phase=phase, parent_field="identity" if name == "A0" else "A0"))
    for name in ("D1", "E1", "E2"):
        specs.append(dict(id=name, family=DIAGNOSTIC_FAMILY, build=name.lower()))
    for width in (1.0, 1.25, 1.5, 1.75, 2.0):
        for j in range(8):
            specs.append(dict(id=f"K5_w{width:g}_p8_{j}", family="k5_slabs", build="k5", width_h=width, phase_z=p8(j)[2]))
    specs.append(dict(id="H0", family="historical", build="historical"))
    if len(specs) != EXPECTED_COUNT or len({s["id"] for s in specs}) != EXPECTED_COUNT:
        raise ProtocolError("base metadata enumeration is not the registered 180 unique rows")
    return specs


def interleaved_specs():
    for spec in base_specs():
        yield spec
        if spec["family"] != DIAGNOSTIC_FAMILY:
            for scale in K6_SCALES:
                yield {**spec, "id": f"{spec['id']}@k6_{scale:g}", "base_id": spec["id"], "scale": scale, "kind": "k6"}


def expectation(spec):
    sid, field = spec["id"].split("@")[0], spec.get("field")
    if spec["family"] == DIAGNOSTIC_FAMILY:
        return "diagnostic_only"
    if sid.startswith("R0_"):
        return "p1_and_composite_pass"
    if sid.startswith("R1_"):
        return "blocked"
    if field in ("N2", "A1"):
        return "p2_fail"
    if field == "A0":
        return "p2_pass_existing_two"
    if field in ("T1", "T2"):
        return "pass_or_unmeasured"
    if field in ("S1", "S2", "V1", "V2", "V4", "N1", "F2", "W20", "W40"):
        return "non_pass"
    if spec["family"] == "k5_slabs":
        return "discrete_crossover"
    if sid == "H0":
        return "known_r0_replay"
    return "pass"


def combo_schedule(known):
    """Called only inside a frozen, released, supervised attempt."""
    names = [b["mode"] for b in known["ordered_basis"]]
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261023, 1])))
    schedule = []
    for i in range(28):
        n = int(rng.integers(2, 4))
        selected = [str(v) for v in rng.choice(names, size=n, replace=False)]
        schedule.append({"names": selected, "coefficients": [float(v) for v in rng.uniform(-1, 1, n)],
                         "noise_seed": [20261023, 2, i] if i >= 20 else None})
    return schedule


def active_mask(masks):
    return masks["design_mask"] & ~masks["fixed_solid_mask"] & ~masks["forbidden_mask"] & ~masks["root_mask"]


def load_input_context(known):
    import mode01_v18_prescreen as P18
    if sha_file(ROOT / known["parent"]["path"]) != known["parent"]["npz_sha256"]:
        raise ProtocolError("parent NPZ differs from known binding")
    parent, params = P18.load_parent()
    masks = {n: getattr(parent, n) for n in MASK_NAMES}
    if (phi_sha(parent.phi) != known["parent"]["phi_fortran_sha256"] or
            list(parent.phi.shape) != known["parent"]["shape"] or
            {n: mask_sha(masks[n]) for n in MASK_NAMES} != known["parent"]["mask_fortran_sha256"]):
        raise ProtocolError("parent field/masks/grid differ from known binding")
    b = read_json(PRESCREEN)["basis"]
    declared = [(n, b["per_mode"][n]["a_star"]) for n in b["proposed_basis"]]
    if declared != [(v["mode"], v["a_star"]) for v in known["ordered_basis"]]:
        raise ProtocolError("ordered basis/amplitudes differ from the registered input")
    basis = {}
    for entry in known["ordered_basis"]:
        assert_rss_budget()
        phi = P18.state_phi(parent, params, entry["mode"], entry["a_star"])
        if phi_sha(phi) != entry["phi_fortran_sha256"]:
            raise ProtocolError(f"basis input changed: {entry['mode']}")
        basis[entry["mode"]] = phi
    return {"parent": parent, "masks": masks, "basis": basis}


def combined_phi(context, names, coefficients, noise_seed, *, old=False):
    parent = context["parent"].phi.astype(np.float64)
    # Python sum starts at scalar zero: this is exactly the old W.combo_phi arithmetic.
    delta = sum(c * (context["basis"][n].astype(np.float64) - parent) for n, c in zip(names, coefficients))
    phi = parent + delta
    if noise_seed is not None:
        rng = np.random.default_rng([W.SEED, noise_seed]) if old else np.random.Generator(np.random.PCG64(np.random.SeedSequence(noise_seed)))
        noise = rng.uniform(-H / 16, H / 16, size=parent.shape)
        phi += np.where(active_mask(context["masks"]), noise, 0.0)
    if not old:
        phi = np.where(active_mask(context["masks"]), phi, parent)
    return phi.astype("<f4")


def build_row_arrays(spec, context=None, schedule=None):
    build = spec["build"]
    origin, h, extras = (0.0, 0.0, 0.0), H, {}
    if build in ("analytic", "margin_control"):
        name = spec["field"]
        center = A_CENTER if name in ("A0", "A1") else DEFAULT_CENTER
        phi = analytic_field(name, spec["theta_deg"], spec["phase"], center=center)
        parent_name = spec.get("parent_field", "identity")
        parent_name = "F_base" if parent_name == "fin_parent" else parent_name
        if build == "margin_control":
            phi[0, 0, 0] = np.float32(spec["corner_phi_h"])
            parent = phi.copy()
            if parent_name == "R0":
                parent[0, 0, 0] = np.float32(np.float64(H) / 2)
        else:
            parent = phi.copy() if parent_name == "identity" else analytic_field(parent_name, spec["theta_deg"], spec["phase"], center=center)
        masks = ordinary_masks()
    elif build in ("v18_combo", "historical"):
        if context is None:
            raise ProtocolError("missing bound v18 input context")
        state, masks = context["parent"], context["masks"]
        parent, origin, h = state.phi, state.origin_m, state.spacing_m
        if build == "historical":
            phi = parent.copy()
        else:
            s = schedule[spec["combo_index"]]
            phi = combined_phi(context, s["names"], s["coefficients"], s["noise_seed"])
            extras = {f"basis_{name}": arr for name, arr in context["basis"].items()}
    elif build == "k5":
        z = np.arange(27, dtype=np.float64).reshape(1, 1, 27)
        distance = np.abs(z - 13 - spec["phase_z"])
        phi = np.broadcast_to(H * (distance - spec["width_h"] / 2), (27, 27, 27)).astype("<f4")
        parent = np.broadcast_to(H * (distance - 3.5 / 2), (27, 27, 27)).astype("<f4")
        masks = k5_masks()
    elif build in ("d1", "e1"):
        phi = np.full((27, 27, 27), H * (0.75 if build == "d1" else 1), dtype="<f4")
        if build == "d1":
            phi[12, 12, 13] = phi[13, 13, 13] = np.float32(-0.25 * H)
        parent, masks = phi.copy(), ordinary_masks()
    elif build == "e2":
        phi = np.full((5, 5, 5), -H, dtype="<f4")
        masks = {n: np.full(phi.shape, n == "design_mask", bool) for n in MASK_NAMES}
        parent, h = phi.copy(), H / 4
    else:
        raise ProtocolError(f"unknown build {build}")
    return {"phi": phi, "parent_phi": parent, **masks, "origin_m": np.asarray(origin, dtype=np.float64),
            "spacing_m": np.asarray(h, dtype=np.float64), **extras}


def unpack_arrays(arrays):
    return (arrays["phi"], arrays["parent_phi"], {n: arrays[n] for n in MASK_NAMES},
            tuple(float(v) for v in arrays["origin_m"]), float(arrays["spacing_m"]))


def cache_input(work, spec, arrays):
    path = work / "inputs" / f"{spec['id']}.npz"
    serialized = canonical(spec)
    if path.exists():
        previous = load_input_npz(path)
        if set(previous) != set(arrays) | {"spec_json"} or str(previous["spec_json"].item()) != serialized:
            raise ProtocolError(f"cached spec/array keys changed: {spec['id']}")
        if any(previous[k].dtype != np.asarray(v).dtype or not np.array_equal(previous[k], v) for k, v in arrays.items()):
            raise ProtocolError(f"cached input changed: {spec['id']}")
    else:
        save_input_npz(path, serialized, **arrays)
    return {"input_npz": str(path.relative_to(work)), "input_npz_sha256": sha_file(path)}


def recipe_identity(reg, known):
    return digest({"seed_coefficients": [20261023, 1], "seed_noise_prefix": [20261023, 2],
                   "count": 28, "noisy_start": 20, "ordered_basis": known["ordered_basis"], "source_files": reg["source_files"]})


def prepare_inputs(work, reg, fingerprint):
    """Complete all 99+250 separation checks and bind all28 new inputs before any outcome."""
    known = read_json(KNOWN_INPUTS)
    old = known["old_combination_source"]
    old_path = ROOT / old["path"]
    if sha_file(old_path) != old["sha256"]:
        raise ProtocolError("old task source hash mismatch")
    tasks = [r["task"] for r in read_json(old_path)["rows"] if r.get("task", [None])[0] == "combo"]
    if len(tasks) != 250 or old["recorded_task_count"] != 250 or digest(tasks) != old["recorded_tasks_sha256"]:
        raise ProtocolError("incomplete or changed 250-task old input stream")
    native = [r["phi_fortran_sha256"] for r in known["known_native_fields"]]
    if len(native) != 99 or any(not valid_hex(s, 64) for s in native):
        raise ProtocolError("incomplete 99-native input identities")
    context = load_input_context(known)
    old_hashes, old_schedules = [], set()
    for i, task in enumerate(tasks):
        assert_rss_budget()
        if len(task) != 4 or task[1] != i or len({p[0] for p in task[2]}) != len(task[2]):
            raise ProtocolError("malformed registered old combination stream")
        names, coefficients = zip(*task[2])
        old_hashes.append(phi_sha(combined_phi(context, names, coefficients, task[3], old=True)))
        old_schedules.add(canonical({"names": names, "coefficients": coefficients, "noise_seed": None if task[3] is None else [W.SEED, task[3]]}))
    schedule = combo_schedule(known)
    forbidden, seen, inputs = set(native) | set(old_hashes), set(), []
    for i, s in enumerate(schedule):
        assert_rss_budget()
        if canonical(s) in old_schedules:
            raise ProtocolError(f"new schedule duplicates old schedule at C{i:02d}; no replacement draw")
        spec = {"id": f"C{i:02d}", "family": "k1_combos", "build": "v18_combo", "combo_index": i}
        arrays = build_row_arrays(spec, context, schedule)
        phi, parent, masks, origin, h = unpack_arrays(arrays)
        ident = field_identity(phi, parent, masks, origin, h, spec)
        psha = ident["phi_fortran_sha256"]
        if psha in forbidden or psha in seen:
            raise ProtocolError(f"new input collision at {spec['id']}; no replacement draw")
        seen.add(psha)
        inputs.append({"id": spec["id"], "schedule": s, "field_identity": ident, **cache_input(work, spec, arrays)})
    manifest = {"schema": "geom03_premeasurement_inputs_v1", "fingerprint": fingerprint,
                "registration_sha256": G["registration_sha256"], "known_inputs_sha256": sha_file(KNOWN_INPUTS),
                "recipe_sha256": recipe_identity(reg, known), "old_source_sha256": old["sha256"],
                "old_tasks_sha256": digest(tasks), "old_combination_phi_sha256": old_hashes,
                "known_native_phi_sha256": native, "new_combinations": inputs, "schedule_sha256": digest(schedule)}
    path = work / "premeasurement_inputs.json"
    if path.exists():
        if read_json(path) != jsonable(manifest):
            raise ProtocolError("premeasurement input manifest changed on resume")
    else:
        write_json_once(path, manifest)
    return context, schedule


def valid_hex(value, length):
    return isinstance(value, str) and len(value) == length and set(value) <= HEX64


def runtime_versions():
    import scipy
    return {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.platform()}


def repo_path(value):
    if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ProtocolError("pins must use contained repository-relative paths")
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ProtocolError(f"missing/outside-repository pin {value}")
    return path


def validate_manifest(records, required):
    if not isinstance(records, list):
        raise ProtocolError("source/review manifest must be a list")
    pins = {}
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or item["path"] in pins or not valid_hex(item.get("sha256"), 64):
            raise ProtocolError("malformed or duplicate source/review pin")
        pins[item["path"]] = item["sha256"]
        if sha_file(repo_path(item["path"])) != item["sha256"]:
            raise ProtocolError(f"source/review hash differs: {item['path']}")
    if not {p for p, _ in required} <= set(pins):
        raise ProtocolError("missing required source/review pins")
    return pins


def git_identity(ref):
    result = subprocess.run(["git", "rev-parse", ref], cwd=ROOT, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ProtocolError("cannot verify git source identity")
    return result.stdout.strip()


def validate_registration(path=REGISTRATION):
    reg = read_json(path)
    if (reg.get("schema") != SCHEMA_REG or reg.get("status") != "REGISTERED_FROZEN" or
            reg.get("expected_count") != EXPECTED_COUNT or reg.get("formal_plan_review_completed") is not True or
            reg.get("source_review_completed") is not True or not valid_hex(reg.get("source_commit"), 40)):
        raise ProtocolError("registration is not a reviewed frozen source")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", reg["source_commit"], "HEAD"],
                              cwd=ROOT, capture_output=True, timeout=10)
    if ancestor.returncode:
        raise ProtocolError("frozen source commit is not an ancestor of the current checkout")
    pins = validate_manifest(reg.get("source_files"), REQUIRED_SOURCE_PINS)
    validate_manifest(reg.get("review_records"), REQUIRED_REVIEW_PINS)
    if not valid_hex(reg.get("code_tree_identity"), 64) or reg["code_tree_identity"] != digest(pins):
        raise ProtocolError("code tree identity differs from source pin manifest")
    if reg.get("runtime_versions") != runtime_versions():
        raise ProtocolError("runtime/platform differs from frozen registration")
    if reg.get("source_tree") != git_identity(f"{reg['source_commit']}^{{tree}}"):
        raise ProtocolError("git tree identity differs from frozen registration")
    for relative, expected in pins.items():
        blob = subprocess.run(["git", "show", f"{reg['source_commit']}:{relative}"], cwd=ROOT, capture_output=True, timeout=10)
        if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != expected:
            raise ProtocolError(f"source pin was not committed at frozen source: {relative}")
    if (reg.get("base_specs_sha256") != digest(base_specs()) or reg.get("expected_k6_count") != K6_EXPECTED or
            reg.get("seeds") != {"coefficient": [20261023, 1], "noise_prefix": [20261023, 2]}):
        raise ProtocolError("frozen metadata enumeration/seeds differ from the registered recipe")
    return reg


def validate_known_bindings():
    known = read_json(KNOWN_INPUTS)
    if known.get("schema") != "geom03_known_input_bindings_v1":
        raise ProtocolError("invalid known input binding schema")
    for item, key in ((known["source_prescreen"], "sha256"), (known["parent"], "npz_sha256"),
                      (known["old_combination_source"], "sha256")):
        if sha_file(repo_path(item["path"])) != item[key]:
            raise ProtocolError("known source binding differs before input generation")
    if len(known["ordered_basis"]) != 7 or len(known["known_native_fields"]) != 99:
        raise ProtocolError("known basis/native identity set is incomplete")
    load_policy()  # metadata only; bind the exact research-policy content before launch


def validate_release(path, registration_sha256):
    release = read_json(path)
    if (release.get("schema") != SCHEMA_RELEASE or release.get("purpose") not in PURPOSES or
            release.get("registration_sha256") != registration_sha256 or not isinstance(release.get("reason"), str) or not release["reason"].strip() or
            not valid_hex(release.get("basis_sha256"), 64) or not isinstance(release.get("resource_evidence"), dict) or not release["resource_evidence"]):
        raise ProtocolError("execution release lacks a bound parent decision/resource record")
    if not isinstance(release.get("basis_file"), str) or sha_file(repo_path(release["basis_file"])) != release["basis_sha256"]:
        raise ProtocolError("execution release basis is missing or hash mismatched")
    return release


def run_probe(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ProtocolError(f"resource probe failed: {command[0]}")
    return result.stdout


def available_memory_bytes():
    if sys.platform == "darwin":
        text = run_probe(["vm_stat"])
        page = re.search(r"page size of (\d+) bytes", text)
        entries = dict(re.findall(r"^(Pages [^:]+):\s+(\d+)\.", text, re.MULTILINE))
        if not page or not all(k in entries for k in ("Pages free", "Pages inactive", "Pages speculative")):
            raise ProtocolError("vm_stat does not expose available-memory evidence")
        return int(page[1]) * sum(int(entries[k]) for k in ("Pages free", "Pages inactive", "Pages speculative"))
    info = Path("/proc/meminfo").read_text()
    match = re.search(r"^MemAvailable:\s+(\d+) kB$", info, re.MULTILINE)
    if not match:
        raise ProtocolError("no available-memory evidence")
    return int(match[1]) * 1024


def resource_evidence():
    """Host mounts AND live Docker mounts; unavailable evidence cannot grant a launch."""
    mounts = run_probe(["mount"])
    if FID_MOUNT_NEEDLE in mounts:
        raise ProtocolError("active host FID output mount")
    ids = run_probe(["docker", "ps", "--quiet"]).split()
    containers = json.loads(run_probe(["docker", "inspect", *ids])) if ids else []
    if not isinstance(containers, list) or len(containers) != len(ids):
        raise ProtocolError("incomplete live Docker mount evidence")
    for container in containers:
        if not isinstance(container.get("Mounts"), list) or not container.get("State", {}).get("Running"):
            raise ProtocolError("Docker state changed during mount verification")
        for m in container["Mounts"]:
            if m.get("Type") == "bind" and FID_MOUNT_NEEDLE in str(m.get("Source", "")):
                raise ProtocolError("running Docker container bind-mounts FID output")
    load, memory = float(os.getloadavg()[0]), available_memory_bytes()
    if not math.isfinite(load) or load > LOAD_LIMIT or memory < BUDGET_RSS:
        raise ProtocolError("load/memory gate refused launch")
    return {"load1": load, "available_memory_bytes": memory, "running_container_ids": ids, "fid_mounts_clear": True}


def load_checker():
    import importlib
    checker = importlib.import_module("geom03_check")
    if not callable(getattr(checker, "check_run", None)):
        raise ProtocolError("independent check_run is not delivered")
    return checker


def preflight(registration=REGISTRATION, release=RELEASE):
    """Read-only dependency/resource gates, before work state or input generation."""
    try:
        reg = validate_registration(registration)
        release_doc = validate_release(release, sha_file(registration))
        validate_known_bindings()
        load_checker()
    except Exception as exc:  # evidence unavailable, no scientific attempt consumed
        return {"status": "WAITING_FOR_DEPENDENCY", "reason": str(exc)}
    try:
        resources = resource_evidence()
    except Exception as exc:
        return {"status": "WAITING_FOR_RESOURCES", "reason": str(exc)}
    fingerprint = digest({"registration_sha256": sha_file(registration), "release_sha256": sha_file(release)})
    return {"status": "READY", "registration": reg, "release": release_doc,
            "fingerprint": fingerprint, "resources": resources}


def terminal_exists(work):
    return any((work / n).exists() for n in ("results.json", "stop_reason.json"))


@contextlib.contextmanager
def controller_lock(work):
    work.mkdir(parents=True, exist_ok=True)
    path = work / "child.lock"
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProtocolError("another controller holds the child lock") from exc
        stream.seek(0)
        previous = stream.read().strip()
        if previous:
            try:
                previous = json.loads(previous)
                for pid in (previous["pid"], previous.get("child_pid")):
                    if pid is None:
                        continue
                    try:
                        os.kill(int(pid), 0)
                    except ProcessLookupError:
                        continue
                    raise ProtocolError("recorded controller/child pid is still live")
            except Exception as exc:
                raise ProtocolError("cannot verify stale controller lock") from exc
        stream.seek(0)
        stream.truncate()
        stream.write(canonical({"pid": os.getpid()}))
        stream.flush()
        try:
            yield stream
        finally:
            stream.seek(0)
            stream.truncate()
            fcntl.flock(stream, fcntl.LOCK_UN)


def verify_rows(work, specs):
    path = work / "rows.jsonl"
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ProtocolError("truncated append-only row file")
    rows = [read_json_line(line) for line in data.decode().splitlines()]
    if len(rows) > len(specs):
        raise ProtocolError("more cached rows than registered enumeration")
    for row, spec in zip(rows, specs):
        if row.get("id") != spec["id"] or canonical(row.get("spec")) != canonical(spec):
            raise ProtocolError("resume rows are not the registered interleaved prefix")
        rel = row.get("input_npz")
        path = (work / rel).resolve() if isinstance(rel, str) else work.parent
        if not path.is_relative_to((work / "inputs").resolve()) or not path.is_file() or sha_file(path) != row.get("input_npz_sha256"):
            raise ProtocolError("resume input cache path/hash mismatch")
        raw = load_input_npz(path)
        if str(raw["spec_json"].item()) != canonical(spec):
            raise ProtocolError("resume cached spec differs")
        phi, parent, masks, origin, h = unpack_arrays(raw)
        if field_identity(phi, parent, masks, origin, h, spec) != row.get("field_identity"):
            raise ProtocolError("resume field/grid/mask/parent identity differs")
    return rows


def prepare_state(work, fingerprint, resume=False, now=None):
    now = time.time() if now is None else now
    if terminal_exists(work):
        raise ProtocolError("terminal result/stop refuses retry or resume")
    path = work / "state.json"
    if path.exists():
        state = read_json(path)
        if (state.get("schema") != SCHEMA_STATE or state.get("fingerprint") != fingerprint or
                type(state.get("attempts")) is not int or state["attempts"] not in (0, 1) or
                state.get("status") not in ("PREPARING", "RUNNING", "INTERRUPTED", *WAITING_STATUSES) or
                type(state.get("resume_count")) is not int or state["resume_count"] < 0):
            raise ProtocolError("only an identical nonterminal one-attempt state can resume")
        if state["attempts"] == 0:
            if state.get("run_started_epoch") is not None or state.get("generation_started") is not False:
                raise ProtocolError("preparation state cannot contain an earlier generation")
            if any(work.glob("inputs/*.npz")) or any((work / n).exists() for n in ("rows.jsonl", "premeasurement_inputs.json")):
                raise ProtocolError("unstarted preparation has registered input artifacts")
        elif not resume:
            raise ProtocolError("an interrupted scientific attempt requires --resume")
        started = state.get("run_started_epoch")
        if state["attempts"] == 1 and (type(started) not in (int, float) or not math.isfinite(started) or started > now):
            raise ProtocolError("invalid original attempt start time")
        if started is not None and now - started > BUDGET_WALL_S:
            raise ProtocolError("cumulative wall budget exhausted during interruption")
        try:
            verify_rows(work, list(interleaved_specs()))
        except ProtocolError:
            raise
        except Exception as exc:
            raise ProtocolError(f"unverifiable partial artifacts:{exc}") from exc
        if state["attempts"] == 1:
            state["resume_count"] += 1
    else:
        if resume or any(work.glob("inputs/*.npz")) or any((work / n).exists() for n in ("rows.jsonl", "premeasurement_inputs.json")):
            raise ProtocolError("orphaned artifacts cannot start a fresh attempt")
        state = {"schema": SCHEMA_STATE, "run_started_epoch": None, "fingerprint": fingerprint,
                 "attempts": 0, "generation_started": False, "resume_count": 0, "observations": {}}
    state.update(status="PREPARING", launch_token=uuid.uuid4().hex)
    write_state(work, state)
    return state


def check_launch_identity(state, registration, release):
    """A resource wait may not conceal changed frozen bytes or replenish an old budget."""
    started = state.get("run_started_epoch")
    if state.get("attempts") == 1 and (type(started) not in (int, float) or not math.isfinite(started) or
                                       time.time() - started > BUDGET_WALL_S):
        raise ProtocolError("cumulative wall budget exhausted during interruption")
    if Path(registration).is_file() and Path(release).is_file():
        fingerprint = digest({"registration_sha256": sha_file(registration), "release_sha256": sha_file(release)})
        if fingerprint != state["fingerprint"]:
            raise ProtocolError("frozen registration/release identity changed")
        reg = read_json(registration)
        for item in reg.get("source_files", []) + reg.get("review_records", []):
            path = ROOT / item["path"]
            if path.is_file() and sha_file(path) != item["sha256"]:
                raise ProtocolError(f"frozen source/review identity changed:{item['path']}")


def record_waiting(work, state, ready):
    if state.get("attempts") == 1 and time.time() - state["run_started_epoch"] > BUDGET_WALL_S:
        raise ProtocolError("cumulative wall budget exhausted during interruption")
    state.update(status=ready["status"], waiting_reason=ready.get("reason", "dependency/resource unavailable"))
    write_state(work, state)
    return WAITING_EXIT


def start_generation(work, state):
    """The first scientific attempt starts immediately before registered input arithmetic."""
    if state["attempts"] == 0:
        state.update(attempts=1, run_started_epoch=time.time())
    state.update(status="RUNNING", generation_started=True)
    state.pop("waiting_reason", None)
    write_state(work, state)


def write_stop(work, reason, state=None, observed_rss=None):
    result_path = work / "results.json"
    if result_path.exists():
        try:
            result = read_json(result_path)
            if result.get("schema") == SCHEMA_RESULTS and result.get("verdict") in ("GEOM03_PASS", "GEOM03_NO_GO", "GEOM03_INCOMPLETE"):
                return result  # a completed first terminal result is immutable too
        except (ValueError, OSError, ProtocolError):
            pass
    record = {"schema": SCHEMA_STOP, "verdict": "GEOM03_INCOMPLETE", "reason": str(reason),
              "observed_rss_bytes": observed_rss, "run_started_epoch": (state or {}).get("run_started_epoch"), "recorded_epoch": time.time()}
    try:
        write_json_once(work / "stop_reason.json", record)
    except FileExistsError:
        pass  # first terminal reason is immutable
    if state is not None:
        state.update(status="TERMINAL", verdict="GEOM03_INCOMPLETE")
        write_state(work, state)
    return record


def append_row(work, row):
    assert_rss_budget()
    with (work / "rows.jsonl").open("a") as stream:
        stream.write(canonical(row) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def sampled_observations(phi):
    from scipy import ndimage
    solid = phi < 0
    if not solid.any():
        return {"sign_body_hashes": {"solid": None, "void": None}, "refined_components": 0}
    body = W.refine(phi[W.box(solid, W.OPEN_PAD)], W.OPEN_K) < 0
    return {"sign_body_hashes": {"solid": hashlib.sha256(body.tobytes()).hexdigest(),
                                "void": hashlib.sha256((~body).tobytes()).hexdigest()},
            "refined_components": int(ndimage.label(body, structure=np.ones((3, 3, 3), bool))[1])}


def feature_observables(spec, phi, parent, p2):
    """Construction observables only; the independent checker decides label validity."""
    field = spec.get("field", "")
    if spec["build"] != "analytic":
        return None
    q = local_coords(spec["theta_deg"], spec["phase"], center=A_CENTER if field in ("A0", "A1") else DEFAULT_CENTER)
    solid = phi < 0
    if field in ("S1", "S2"):
        return {"negative_node_in_box": int(solid.sum())}
    if field in ("V1", "V2", "V4"):
        width = 0.875 if field in ("V1", "V4") else 1.125
        z = q[2] - 3.5 if field == "V4" else q[2]
        inside = (np.abs(q[0]) < width / 2) & (np.abs(q[1]) < 4.25) & (np.abs(z) < (4 if field == "V4" else 3.5))
        if field == "V4":
            inside &= q[2] < 5.5
        name = "positive_node_in_open_slot" if field == "V4" else "positive_node_in_closed_void"
        return {name: int(((phi > 0) & inside).sum())}
    if field == "N1":
        return {"negative_node_in_neck": int((solid & (np.abs(q[0]) < 2.25)).sum())}
    if field in ("N2", "A0", "A1"):
        from scipy import ndimage
        structure = np.ones((3, 3, 3), bool)
        old, old_count = ndimage.label(parent < 0, structure=structure)
        new, new_count = ndimage.label(solid, structure=structure)
        old_to_new = {str(i): [] for i in range(1, old_count + 1)}
        new_to_old = {str(i): [] for i in range(1, new_count + 1)}
        both = (old > 0) & (new > 0)
        for a, b in np.unique(np.stack((old[both], new[both]), axis=1), axis=0):
            old_to_new[str(a)].append(int(b))
            new_to_old[str(b)].append(int(a))
        name = "neck_split" if field == "N2" else "boxes_merge" if field == "A1" else "boxes_identity"
        return {name: {"parent_components": int(old_count), "candidate_components": int(new_count),
                       "overlap": {"old_to_new": old_to_new, "new_to_old": new_to_old}}}
    if field in ("F1", "F2"):
        offset, half = (3.625, 0.375) if field == "F1" else (5.625, 2.375)
        tail = box_sdf(q[0] - offset, q[1], q[2], (half, 1.5, 0.5)) < 0
        coarse = int((solid & tail & (q[0] > 3.5)).sum())
        if field == "F2":
            return {"negative_node_outside_parent_fin": coarse}
        sl = W.box(solid, W.OPEN_PAD)
        qx, qy, qz = (W.refine(comp[sl], W.OPEN_K) for comp in q)
        tail = box_sdf(qx - offset, qy, qz, (half, 1.5, 0.5)) < 0
        refined = int(((W.refine(phi[sl], W.OPEN_K) < 0) & tail & (qx > 3.5)).sum())
        return {"fin_protrusion_counts": {"coarse": coarse, "refined": refined}}
    if field in ("W20", "W40"):
        angle = float(field[1:])
        start = 4 - 1.5 / (2 * math.tan(math.radians(angle) / 2))
        return {"negative_node_in_thin_tip": int((solid & (q[0] > start) & (q[0] < 4)).sum())}
    return None


def make_row(work, spec, arrays, base_row=None):
    phi, parent, masks, origin, h = unpack_arrays(arrays)
    row = {"id": spec["id"], "kind": spec.get("kind", "base"), "family": spec["family"], "spec": spec,
           "expectation": expectation(spec), "parent_kind": spec.get("parent_field", spec["build"]),
           "origin_m": origin, "spacing_m": h, "field_identity": field_identity(phi, parent, masks, origin, h, spec),
           "halo": halo_pair(phi, parent, spec["family"], spec["build"]), **cache_input(work, spec, arrays)}
    if spec["build"] == "e2":
        body = np.ones((5, 5, 5), bool)
        row.update(candidate=None, diagnostic={"solid": W.opening_defect(body, H / 4, 0.75 * H),
                                              "void": W.opening_defect(~body, H / 4, 0.75 * H), "spacing_m": H / 4})
        return row
    candidate = evaluate_pair(phi, parent, masks, h, G["policy"], origin)
    if spec.get("kind") == "k6":
        if base_row is None:
            raise ProtocolError("missing unscaled base row for K6")
        candidate["p1"] = base_row["candidate"]["p1"]
        candidate["composite"] = composite_status(candidate["r3"]["status"], candidate["p2"]["statuses"].values(), candidate["p1"]["status"])
        row["k6"] = {"base_id": spec["base_id"], "scale": spec["scale"], "unscaled_p1": candidate["p1"]}
    row.update(candidate=candidate, coarse_components=candidate["p2"]["candidate_components"], **sampled_observations(phi))
    row["feature_observables"] = feature_observables(spec, phi, parent, candidate["p2"])
    if spec["build"] == "d1":
        from scipy import ndimage
        refined = W.refine(phi[W.box(phi < 0, W.OPEN_PAD)], W.OPEN_K) < 0
        row["diagnostic"] = {"coarse_components": candidate["p2"]["candidate_components"],
                             "refined_components": int(ndimage.label(refined, structure=np.ones((3, 3, 3), bool))[1])}
    return row


def execute_child(work, reg, fingerprint, state):
    """Exactly one study evaluation per row, followed by exactly one independent run check."""
    G.update(started=state["run_started_epoch"], policy=load_policy(), controller_pid=state["controller_pid"])
    assert_rss_budget()
    context, schedule = prepare_inputs(work, reg, fingerprint)
    specs = list(interleaved_specs())
    rows = verify_rows(work, specs)
    by_id = {row["id"]: row for row in rows}
    for spec in specs[len(rows):]:
        assert_rss_budget()
        base_row = None
        if spec.get("kind") == "k6":
            base_row = by_id[spec["base_id"]]
            arrays = load_input_npz(work / base_row["input_npz"])
            arrays.pop("spec_json")
            arrays["phi"] = (arrays["phi"].astype(np.float64) * spec["scale"]).astype("<f4")
            arrays["parent_phi"] = (arrays["parent_phi"].astype(np.float64) * spec["scale"]).astype("<f4")
        else:
            arrays = build_row_arrays(spec, context, schedule)
        row = make_row(work, spec, arrays, base_row)
        append_row(work, row)
        by_id[spec["id"]] = jsonable(row)
        del arrays
    assert_rss_budget()
    result = load_checker().check_run(work, reg)  # the only independent metric/tally invocation
    required = {"verdict", "complete", "criteria", "incomplete_reasons", "counterexamples"}
    if (not isinstance(result, dict) or not required <= set(result) or result["verdict"] not in
            ("GEOM03_PASS", "GEOM03_NO_GO", "GEOM03_INCOMPLETE") or not isinstance(result["complete"], bool) or
            not isinstance(result["criteria"], dict) or not isinstance(result["incomplete_reasons"], list) or not isinstance(result["counterexamples"], list) or
            (result["verdict"] != "GEOM03_INCOMPLETE" and (not result["complete"] or result["incomplete_reasons"]))):
        raise ProtocolError("independent checker returned an invalid terminal result")
    if result["complete"]:
        criteria = result["criteria"]
        if (set(criteria) != {"K1", "K2", "K3", "K4", "K5", "K6", "H0"} or
                result.get("checked_rows") != EXPECTED_COUNT + K6_EXPECTED or
                any(not isinstance(v, dict) or type(v.get("pass")) is not bool for v in criteria.values()) or
                result["verdict"] != ("GEOM03_PASS" if all(v["pass"] for v in criteria.values()) else "GEOM03_NO_GO")):
            raise ProtocolError("independent completion/tally/verdict is inconsistent")
    assert_rss_budget()
    result.update(schema=SCHEMA_RESULTS, fingerprint=fingerprint, attempts=1,
                  registration_sha256=G["registration_sha256"], run_started_epoch=state["run_started_epoch"],
                  cumulative_wall_s=time.time() - state["run_started_epoch"])
    write_json_once(work / "results.json", result)
    state.update(status="TERMINAL", verdict=result["verdict"])
    write_state(work, state)
    return result


def child_rss_bytes(pid):
    output = run_probe(["ps", "-o", "rss=", "-p", str(pid)])
    return int(output.strip()) * 1024


def terminate_owned(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def supervise(child, work, state):
    peak = 0
    while child.poll() is None:
        state = read_json(work / "state.json")
        reason = None
        if state.get("run_started_epoch") is not None and time.time() - state["run_started_epoch"] > BUDGET_WALL_S:
            reason = "cumulative_wall_budget_exhausted"
        try:
            rss = child_rss_bytes(child.pid)
            peak = max(peak, rss)
            if rss > BUDGET_RSS:
                reason = "observed_child_rss_budget_exhausted"
        except Exception:
            if child.poll() is None:
                reason = "live_child_rss_evidence_unavailable"
        if reason:
            terminate_owned(child)
            write_stop(work, reason, state, peak)
            return 1
        time.sleep(0.25)
    final = read_json(work / "state.json")
    waiting = child.returncode == WAITING_EXIT and final.get("status") in WAITING_STATUSES
    if not terminal_exists(work) and not waiting:
        write_stop(work, f"child_exited_without_terminal_record:{child.returncode}", state, peak)
    final = read_json(work / "state.json")
    final.setdefault("observations", {})["peak_child_rss_bytes"] = peak
    write_state(work, final)
    return child.returncode


def run_controller(work=WORK, registration=REGISTRATION, release=RELEASE, resume=False):
    if terminal_exists(work):
        raise ProtocolError("terminal result/stop refuses retry or resume")
    ready = preflight(registration, release)
    if ready["status"] != "READY":
        if resume and (work / "state.json").is_file():
            with controller_lock(work):
                state = read_json(work / "state.json")
                try:
                    check_launch_identity(state, registration, release)
                except ProtocolError as exc:
                    write_stop(work, str(exc), state)
                    raise
        return ready
    if Path(work).resolve() != WORK.resolve():
        raise ProtocolError("the one registered attempt uses only its declared work directory")
    if Path(registration).resolve() != REGISTRATION.resolve() or Path(release).resolve() != RELEASE.resolve():
        raise ProtocolError("the checker requires the declared registration/release artifact paths")
    with controller_lock(work) as lock:
        try:
            if (work / "state.json").is_file():
                check_launch_identity(read_json(work / "state.json"), registration, release)
            state = prepare_state(work, ready["fingerprint"], resume)
        except ProtocolError as exc:
            # Terminal records remain immutable; a used, expired attempt gets a terminal stop.
            if (work / "state.json").exists() and not terminal_exists(work) and (resume or "identity changed" in str(exc)):
                write_stop(work, str(exc), read_json(work / "state.json"))
            raise
        env = dict(os.environ, **{name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")})
        env.update({SUPERVISE_ENV: "1", LAUNCH_ENV: state["launch_token"]})
        command = [sys.executable, str(Path(__file__).resolve()), "--child", "--work", str(work),
                   "--registration", str(registration), "--release", str(release)]
        state.update(controller_pid=os.getpid(), resource_evidence=ready["resources"])
        state.pop("child_pid", None)
        write_state(work, state)
        try:
            child = subprocess.Popen(command, env=env, cwd=ROOT)
        except Exception as exc:
            write_stop(work, f"numerical_child_launch_failed:{exc}", state)
            raise
        try:
            lock.seek(0)
            lock.truncate()
            lock.write(canonical({"pid": os.getpid(), "child_pid": child.pid}))
            lock.flush()
            state["child_pid"] = child.pid
            write_state(work, state)
            code = supervise(child, work, state)
        except BaseException:
            terminate_owned(child)
            if not terminal_exists(work):
                current = read_json(work / "state.json")
                current["status"] = "INTERRUPTED"
                write_state(work, current)
            raise
        final = read_json(work / "state.json")
        return {"status": final["status"] if code == WAITING_EXIT and final["status"] in WAITING_STATUSES else "TERMINAL",
                "returncode": code, "work": str(work)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="GEOM-03 metadata by default; explicit frozen/released serial execution only.")
    parser.add_argument("--run", action="store_true", help="launch one frozen and released attempt")
    parser.add_argument("--resume", action="store_true", help="resume only a verified nonterminal interrupted attempt")
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--registration", type=Path, default=REGISTRATION)
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not (args.run or args.resume or args.child):
        print(canonical({"status": "METADATA_ONLY", "base_rows": EXPECTED_COUNT, "k6_rows": K6_EXPECTED,
                         "total_rows": EXPECTED_COUNT + K6_EXPECTED, "families": FAMILY_COUNTS,
                         "registration": args.registration, "release": args.release}))
        return 0
    if not args.child:
        print(canonical(run_controller(args.work, args.registration, args.release, args.resume)))
        return 0
    if args.work.resolve() != WORK.resolve():
        raise ProtocolError("alternate numerical-child work directory is not registered")
    state = read_json(args.work / "state.json")
    if (os.environ.get(SUPERVISE_ENV) != "1" or not state.get("launch_token") or
            os.environ.get(LAUNCH_ENV) != state["launch_token"] or terminal_exists(args.work)):
        raise ProtocolError("direct/terminal numerical child launch refused")
    handshake_started = time.monotonic()
    while state.get("child_pid") != os.getpid():
        if os.getppid() != state.get("controller_pid") or time.monotonic() - handshake_started > 5:
            raise ProtocolError("numerical child was not recorded by its owning controller")
        time.sleep(0.05)
        state = read_json(args.work / "state.json")
    try:
        check_launch_identity(state, args.registration, args.release)
        ready = preflight(args.registration, args.release)
        if ready["status"] in WAITING_STATUSES:
            return record_waiting(args.work, state, ready)
        if ready["status"] != "READY" or ready.get("fingerprint") != state.get("fingerprint"):
            raise ProtocolError("child frozen identity differs from its controller")
        check_launch_identity(state, args.registration, args.release)
        G["registration_sha256"] = sha_file(args.registration)
        start_generation(args.work, state)
        execute_child(args.work, ready["registration"], ready["fingerprint"], state)
    except Exception as exc:
        write_stop(args.work, f"{type(exc).__name__}:{exc}", state, observed_rss_bytes())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
