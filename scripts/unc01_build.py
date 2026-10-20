#!/usr/bin/env python3
"""UNC-01 (#61, M2) builder: the registered v18 states through the harness state model, their direction raws, the placement phases and the
campaign JSONs of U01 (U0 smoke + U1 pilot) and U2.  Solver-free and deterministic.  Registration: docs/unc01_registration_2026_10_20.md.

    python scripts/unc01_build.py states                 # direction raws + states.json; every state must reproduce its prescreen phi SHA
    python scripts/unc01_build.py campaign u01           # docs/harness/unc01_u01_campaign.json
    python scripts/unc01_build.py campaign u2 --L MODE   # docs/harness/unc01_u2_campaign.json (MODE = the U1 selection, analyze_unc01.py u1)
    python scripts/unc01_build.py regate [--workers N]   # the freeze re-gate of the states with the prescreen gate stack -> regate.json

Each state: analytic phi (v18_plate.mode_phi) -> direction d / max|d| (float32) and step 1000 max|d| mm -> construct_state(parent, d, step, +1),
i.e. what the harness runner regenerates as float32(float64(parent) + step/1000 * direction) (scripts/step01_states.perturb).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import step01_states as S  # noqa: E402

OUT = ROOT / "docs/evidence/unc01_2026_10_20"
INPUTS = OUT / "inputs"
GENESIS = ROOT / "docs/evidence/v18_genesis_2026_10_19"
PRESCREEN = ROOT / "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json"
PARENT_RAW = "docs/evidence/v18_genesis_2026_10_19/v18_parent.phi_f4_fortran.raw"
HARNESS = ROOT / "docs/harness"
OWNER, REPO_URL = "ramhachi888", "https://github.com/ramhachi/CFD_opt_sdf.git"

# registered states: name -> (prescreen mode, amplitude, harness kind).  Only prescreen-tested, gate-clean points (registration §3).
WIDE = {"pitch": 3.1, "camber": 19.7, "reflex": 29.3, "twist": 1.1, "sweep": 11.3}   # L candidates at A* (prescreen AMPS order = tie order)
STATES = {"v18__parent": ("parent", 0.0, "parent"), "v18__D0_p3": ("thickness_D0", 3.0, "candidate"),
          "v18__s125_m5": ("offset_s125", -5.0, "candidate"), "v18__s050_m5": ("offset_s050", -5.0, "candidate"),
          "v18__surge_p31.1": ("surge", 31.1, "control"), "v18__surge_m31.1": ("surge", -31.1, "control"),
          **{f"v18__{m}_{s}{a:g}": (m, sg * a, "candidate") for m, a in WIDE.items() for s, sg in (("p", 1), ("m", -1))}}

# placement phases (registration §4): phase k shifts the canonical SDF origin by (f_kx, f_ky, 0) h_flow, f_k = frac(k (a1, a2)) (R2 sequence)
R2 = (0.7548776662, 0.5698402910)
NATIVE_ORIGIN = (-1.0, -0.8, -0.6)
HALF_SHIFT_M = 0.0125            # the GRID-02 / JOB-02 bridge placement (x and y + 12.5 mm, z unchanged)
U2_PHASES = {"flow_24": range(1, 7), "flow_32": range(1, 7), "flow_48": range(1, 5)}   # disjoint from the native phase k = 0 used by U1

CASES = {  # identical to docs/harness/replay_grid02_campaign.json / job02_gate_campaign.json
    "flow_24": {"job": "scripts/waterlily_xfid_candidate_c_job.jl", "env": {}, "pins": [],
                "case": {"case_id": "flow_24", "density_kg_m3": 1.0, "dynamic_viscosity_pa_s": 0.01, "flow_dims": [150, 72, 54], "flow_spacing_m": 1 / 30,
                         "freestream_mps": [1.0, 0.0, 0.0], "reference_area_m2": 0.64, "reference_length_m": 0.8, "reynolds": 80.0, "solver_length": 24.0,
                         "solver_time_unit_s": 1 / 30, "solver_viscosity": 0.3}},
    "flow_32": {"job": "scripts/waterlily_lowdim02_flow32_job.jl", "env": {}, "pins": [],
                "case": {"case_id": "flow_32", "density_kg_m3": 1.0, "dynamic_viscosity_pa_s": 0.01, "flow_dims": [200, 96, 72], "flow_spacing_m": 0.025,
                         "freestream_mps": [1.0, 0.0, 0.0], "reference_area_m2": 0.64, "reference_length_m": 0.8, "reynolds": 80.0, "solver_length": 32.0,
                         "solver_time_unit_s": 0.025, "solver_viscosity": 0.4}},
    "flow_48": {"job": "scripts/waterlily_grid02_job.jl", "env": {"GRID02_CASE": "flow_48"}, "pins": ["scripts/grid02_case.jl"],
                "case": {"case_id": "flow_48", "density_kg_m3": 1.0, "dynamic_viscosity_pa_s": 0.01, "flow_dims": [300, 144, 108], "flow_spacing_m": 1 / 60,
                         "freestream_mps": [1.0, 0.0, 0.0], "reference_area_m2": 0.64, "reference_length_m": 0.8, "reynolds": 80.0, "solver_length": 48.0,
                         "solver_time_unit_s": 1 / 60, "solver_viscosity": 0.6}},
}
SETUP = {"instantiate_timeout_s": 2400, "gpu_probe_timeout_s": 300, "reserve_s": 300}


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def phase_fraction(k: int) -> tuple[float, float]:
    return ((k * R2[0]) % 1.0, (k * R2[1]) % 1.0)


def origin(case_id: str | None, k: int | None = None, half: bool = False) -> str:
    """W4_CANONICAL_ORIGIN_M of a run: native (k = 0), phase k of the grid, or the GRID-02 bridge placement; z (ride height) never moves."""
    if half:
        dx = dy = HALF_SHIFT_M
    else:
        h = CASES[case_id]["case"]["flow_spacing_m"]
        fx, fy = phase_fraction(k)
        dx, dy = fx * h, fy * h
    x, y, z = NATIVE_ORIGIN
    return ",".join(repr(round(v, 10)) for v in (x + dx, y + dy, z))


def dir_rel(name: str) -> str:
    return f"docs/evidence/unc01_2026_10_20/inputs/{name}.dir_f4_fortran.raw"


def load_parent():
    sys.path.insert(0, str(ROOT / "scripts"))
    import mode01_v18_prescreen as P
    return P.load_parent()


def npz_sha(state) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.npz", Path(tmp) / "b.npz"
        state.save(a)
        state.save(b)
        if sha(a) != sha(b):
            raise SystemExit("non-deterministic NPZ serialization")
        return sha(a)


def build_states(write: bool = True) -> dict:
    """Every registered state through the harness model; refuses unless its Fortran phi SHA equals the prescreen's gated bytes and the runner
    regeneration (step01_states.perturb on the raw files) reproduces it."""
    import v18_plate as V
    from cfd_sdf.fd08_v2_campaign import construct_state, state_identity
    from cfd_sdf.gradients.directional_fd import zero_level_margin_m
    s, p = load_parent()
    pre = {(r["mode"], r["amplitude"]): r for r in json.loads(PRESCREEN.read_text())["states"]}
    if sha(ROOT / PARENT_RAW) != pre[("parent", 0.0)]["phi_fortran_sha256"]:
        raise SystemExit("v18 parent raw differs from the prescreen parent")
    parent_raw = S.read_f4(ROOT / PARENT_RAW)
    rows = {}
    for name, (mode, a, kind) in STATES.items():
        ref = pre[(mode, a)]
        if not ref["all_pass"]:
            raise SystemExit(f"{name}: not gate-clean in the prescreen")
        if mode == "parent":
            child, audit, d, step = s, {"changed_node_count": 0, "maximum_pointwise_change_m": 0.0, "zero_level_margin_m": zero_level_margin_m(s.phi, s.spacing_m)}, None, 0.0
            npz = sha(GENESIS / "v18_parent.npz")
        else:
            d, step = V.harness_direction(s, V.mode_phi(s, p, mode, a))
            child, audit = construct_state(s, d, step, 1)
            npz = npz_sha(child)
        ident = state_identity(child)
        if ident["phi_fortran_order_sha256"] != ref["phi_fortran_sha256"]:
            raise SystemExit(f"{name}: harness bytes differ from the prescreen gated bytes")
        if d is not None:
            raw = S.to_raw(d)
            if write:
                INPUTS.mkdir(parents=True, exist_ok=True)
                (ROOT / dir_rel(name)).write_bytes(raw)
            regen = S.perturb(parent_raw, np.frombuffer(raw, "<f4").reshape(S.SHAPE, order="F"), step, 1)
            if S.sha256_bytes(S.to_raw(regen)) != ref["phi_fortran_sha256"]:
                raise SystemExit(f"{name}: runner regeneration differs from the prescreen bytes")
        rows[name] = {"mode": mode, "amplitude": a, "kind": kind, "direction": None if d is None else name, "step_mm": float(step), "sign": 0 if d is None else 1,
                      "direction_sha256_fortran_raw": None if d is None else S.sha256_bytes(S.to_raw(d)),
                      "state_sha256": ident["state_sha256"], "npz_sha256": npz, "phi_fortran_order_sha256": ident["phi_fortran_order_sha256"],
                      "phi_c_order_sha256": ident["phi_c_order_sha256"], "zero_level_margin_m": float(audit["zero_level_margin_m"]), "margin_tolerance_m": 1e-6,
                      "changed_node_count": int(audit["changed_node_count"]), "maximum_pointwise_change_m": float(audit["maximum_pointwise_change_m"]),
                      "prescreen_phi_fortran_sha256": ref["phi_fortran_sha256"], "prescreen_all_pass": ref["all_pass"]}
    rec = {"kind": "unc01_states", "parent": {"npz": "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz", "raw": PARENT_RAW, "state_sha256": s.state_sha256,
                                               "source_sha256": s.source_sha256}, "v18_plate_sha256": sha(ROOT / "scripts/v18_plate.py"),
           "prescreen_sha256": sha(PRESCREEN), "states": rows,
           "check": "every state's Fortran phi SHA equals the prescreen gated bytes, and step01_states.perturb on the written raws reproduces it"}
    if write:
        (OUT / "states.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


def run(state: str, case_id: str, k: int | None = None, half: bool = False) -> dict:
    tag = "half" if half else f"k{k}"
    return {"state": state, "name": f"{state}__{tag}", "env": {"W4_CANONICAL_ORIGIN_M": origin(case_id, k, half), **CASES[case_id]["env"]}}


def kernel(cid: str, k: str, case_id: str, runs: list, per_state: int, cap: int, timeout: int) -> dict:
    c = CASES[case_id]
    out = {"kernel_id": f"{OWNER}/cfd-opt-sdf-{cid.replace('_', '-')}-{k}", "job": c["job"], "case": c["case"],
           "config": {"per_state_timeout_s": per_state, "solver_wall_time_cap_s": cap, "kernel_timeout_s": timeout, **SETUP}, "runs": runs}
    if c["pins"]:
        out["pins"] = c["pins"]
    return out


def phase_runs(states: list, case_id: str, phases) -> list:
    """Phase-major: every state of phase k (parent first) before phase k+1, so a stopped kernel keeps whole phases."""
    return [run(s, case_id, k) for k in phases for s in states]


def kernels_u01() -> dict:
    wide = [f"v18__{m}_{s}{a:g}" for m, a in WIDE.items() for s in ("p", "m")]
    f32 = [run(s, "flow_32", 0) for s in ["v18__parent", "v18__D0_p3", *wide]] + [run(s, "flow_32", half=True) for s in ("v18__parent", "v18__D0_p3")]
    f24 = [run(s, "flow_24", 0) for s in ("v18__parent", "v18__D0_p3")] + [run(s, "flow_24", half=True) for s in ("v18__parent", "v18__D0_p3")]
    return {"f24": kernel("unc01_u01", "f24", "flow_24", f24, 900, 1800, 4800),
            "f32": kernel("unc01_u01", "f32", "flow_32", f32, 900, 9000, 12000),
            "f48": kernel("unc01_u01", "f48", "flow_48", [run("v18__parent", "flow_48", 0)], 6000, 6000, 9000)}


def u2_states(L: str) -> dict:
    if L not in WIDE:
        raise SystemExit(f"L must be one of {list(WIDE)}")
    Lp, Lm = f"v18__{L}_p{WIDE[L]:g}", f"v18__{L}_m{WIDE[L]:g}"
    return {"flow_32": ["v18__parent", "v18__D0_p3", Lp, Lm, "v18__s125_m5", "v18__s050_m5", "v18__surge_p31.1", "v18__surge_m31.1"],
            "flow_24": ["v18__parent", "v18__D0_p3", Lp, "v18__s050_m5"], "flow_24_reduced": ["v18__parent", Lp], "flow_48": ["v18__parent", Lp]}


def kernels_u2(L: str) -> dict:
    st, ph = u2_states(L), U2_PHASES
    k32 = {f"f32{b}": kernel("unc01_u2", f"f32{b}", "flow_32", phase_runs(st["flow_32"], "flow_32", ph["flow_32"][2 * i:2 * i + 2]), 900, 9000, 12000)
           for i, b in enumerate("abc")}
    k48 = {f"f48{b}": kernel("unc01_u2", f"f48{b}", "flow_48", phase_runs(st["flow_48"], "flow_48", ph["flow_48"][2 * i:2 * i + 2]), 6000, 11000, 14400)
           for i, b in enumerate("ab")}
    return {**k48, **k32,
            "f24": kernel("unc01_u2", "f24", "flow_24", phase_runs(st["flow_24"], "flow_24", ph["flow_24"]), 900, 6000, 9000),
            "f24r": kernel("unc01_u2", "f24r", "flow_24", phase_runs(st["flow_24_reduced"], "flow_24", ph["flow_24"]), 900, 3600, 6600)}


def campaign(cid: str, kernels: dict, rec: dict) -> dict:
    used = sorted({r["state"] for kk in kernels.values() for r in kk["runs"]})
    states = {n: {k: rec["states"][n][k] for k in ("kind", "direction", "step_mm", "sign", "state_sha256", "npz_sha256", "phi_fortran_order_sha256",
                                                 "phi_c_order_sha256", "zero_level_margin_m", "margin_tolerance_m", "changed_node_count",
                                                 "maximum_pointwise_change_m")} for n in used}
    return {"harness_version": "harness v1.1", "legacy_replay": False, "campaign_id": cid, "owner": OWNER, "repo_url": REPO_URL,
            "index_name": "harness_index.json", "out_prefix": f"{cid}_",
            "job_env_common": {"W4_CANONICAL_DESIGN_SPACING_M": "0.025", "W4_CANONICAL_STATE_LABEL": "v18", "W4_CELL_SHAPE": "120,64,48",
                               "W4_MARGIN_GATE_M": "0.15", "W4_MARGIN_TOLERANCE_M": "1e-6", "W4_POINT_SHAPE": "121,65,49",
                               "W4_SOURCE_SURFACE_SHA256": rec["parent"]["source_sha256"]},
            "job_env_keys": ["GRID02_CASE"], "scrub_env": ["GRID02_CASE"],
            "measurement": {"candidate_operator": "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))", "time_window_t_u_l": [80.0, 120.0]},
            "domain": {"flow_origin_m": [-2.5, -1.2, -0.9], "physical_box_max_m": [2.5, 1.2, 0.9]},
            "baseline": {"path": PARENT_RAW, "sha256_fortran_raw": sha(ROOT / PARENT_RAW)},
            "directions": {n: {"path": dir_rel(n), "sha256_fortran_raw": rec["states"][n]["direction_sha256_fortran_raw"]} for n in used if rec["states"][n]["direction"]},
            "states": states, "kernels": kernels, "sparse": [], "pins": []}


def write_campaign(which: str, L: str | None) -> Path:
    from cfd_harness import campaign_schema as SC
    rec = json.loads((OUT / "states.json").read_text())
    if build_states(write=False)["states"] != rec["states"]:
        raise SystemExit("states.json no longer re-derives")
    c = campaign("unc01_u01", kernels_u01(), rec) if which == "u01" else campaign("unc01_u2", kernels_u2(L), rec)
    SC.validate_campaign(c)
    path = HARNESS / f"unc01_{which}_campaign.json"
    text = json.dumps(c, indent=1, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != text:
        raise SystemExit(f"refusing to overwrite a different {path}")
    path.write_text(text)
    return path


def regate(workers: int) -> dict:
    """The freeze re-gate: the prescreen's own gate stack (mode01_v18_prescreen.work) on every registered state, compared with the prescreen row."""
    import multiprocessing as mp
    import mode01_v18_prescreen as P
    tasks = [(m, a) for m, a, _ in STATES.values()]
    with mp.get_context("spawn").Pool(workers, initializer=P._init) as pool:
        rows = pool.map(P.work, tasks)
    pre = {(r["mode"], r["amplitude"]): r for r in json.loads(PRESCREEN.read_text())["states"]}
    out = {}
    for name, r in zip(STATES, rows):
        ref = pre[(r["mode"], r["amplitude"])]
        out[name] = {"all_pass": r.get("all_pass"), "phi_fortran_sha256": r.get("phi_fortran_sha256"), "error": r.get("error"),
                     "same_as_prescreen": {k: r.get(k) == ref.get(k) for k in ("all_pass", "phi_fortran_sha256", "failed_geom02", "unmeasured_geom02", "gate_status", "p22")}}
    rec = {"kind": "unc01_regate", "gate_stack": "scripts/mode01_v18_prescreen.py work() (13 GEOM-02 v2 gates, P22-v2, smoothed-volume band, clearance)",
           "states": out, "all_pass": all(v["all_pass"] for v in out.values()),
           "identical_to_prescreen": all(all(v["same_as_prescreen"].values()) for v in out.values())}
    (OUT / "regate.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["states", "campaign", "regate"])
    ap.add_argument("which", nargs="?", choices=["u01", "u2"])
    ap.add_argument("--L")
    ap.add_argument("--workers", type=int, default=7)
    a = ap.parse_args()
    if a.cmd == "states":
        rec = build_states()
        print(json.dumps({n: (r["step_mm"], r["phi_fortran_order_sha256"][:12]) for n, r in rec["states"].items()}, indent=1))
    elif a.cmd == "campaign":
        print(write_campaign(a.which, a.L))
    else:
        rec = regate(a.workers)
        print(json.dumps({"all_pass": rec["all_pass"], "identical_to_prescreen": rec["identical_to_prescreen"]}))


if __name__ == "__main__":
    main()
