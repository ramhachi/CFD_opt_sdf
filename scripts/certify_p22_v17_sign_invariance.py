#!/usr/bin/env python3
"""SRCMAP-03a (#54): P22-v17 boundary-sign invariance certificate.  Solver-free; reads retained evidence only.

Question: does the P22 hard-volume observable of the retained v17 baseline depend on the sign given to
boundary-ambiguous lattice nodes?  Everything that decides a cell reuses the production evaluator
(`_corner_mean`, `cell_occupancy`, `zero_level_margin_m`, `_gradient_diagnostics`); no new evaluator is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from build_lowdim01_inputs import CELL_COMPONENTS, EIKONAL_MEDIAN_MAX, VOLUME_BAND  # noqa: E402
from cfd_sdf.design.geometry_gates import _gradient_diagnostics, cell_occupancy  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.design.volume_semantics import _corner_mean, smoothed_volume_and_gradient  # noqa: E402
from cfd_sdf.fd08_v2_campaign import MARGIN_GATE_M  # noqa: E402
from cfd_sdf.gradients.directional_fd import zero_level_margin_m  # noqa: E402

INPUTS = ROOT / "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs"
SRCMAP01 = ROOT / "docs/evidence/srcmap01_v17_reproducibility_2026_10_12"
STL_SHA = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
BASELINE_NPZ_SHA = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
BASELINE_STATE_SHA = "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"
PARENT_NPZ_SHA = "0ce3256b0f3e5c919caeb2ac1b36f1a33838f34c767c091cb89bda0234ac750b"
MESH_VERTEX_BYTES_SHA = "b2e014fce6ffe5e15e6c90e1605fe6c1578eacfc42266dd9eb962096e12ecaed"
MESH_FACE_BYTES_SHA = "7b4be8455c6752ff66e1e59ba151c8aacd789c040d1e24fdfd145dc4b9b73296"
REFERENCE_SOLID_CENTERS = 8272
CONTROL_COUNT = 19                # 18 retained v17 SRCMAP-01 fields (no v16, no unsigned, no difference maps) + the Oct12 replay

# frozen parameters (set before any target measurement; see prerun_plan.md)
TAU_REP = np.float32(1e-6)       # representative of the plateau; certificate binds to the whole plateau, not to this number
PLATEAU_MIN_RATIO = 1e3          # smallest-outside / largest-inside magnitude required
GWN_TOL = 1e-9                   # max distance of an outside-band winding number from {0,1}
GWN_CHUNK = 1500
SMOOTH_BOUND_MAX_REL = 1e-3      # smoothed-volume bound relative to baseline V_eps
OFFSETS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1]])


class IntegrityError(RuntimeError):
    """A frozen identity or precondition failed: the run is INCOMPLETE, never a verdict."""


def require(cond: bool, msg: str) -> None:
    if not cond: raise IntegrityError(msg)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def f64_hash(a: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(a, dtype="<f8").tobytes())


def band_plateau(phi: np.ndarray, tau_rep: float) -> dict:
    """Band B = {|phi| < tau_rep}; membership must be identical across the observed gap between inside and outside."""
    mag = np.abs(phi).astype(np.float64)
    band = mag < float(tau_rep)
    require(bool(band.any() and (~band).any()), "ambiguity band or its complement is empty")
    lo, hi = float(mag[band].max()), float(mag[~band].min())
    at_lo, at_hi = mag <= lo, mag <= np.nextafter(hi, 0.0)
    return {"band": band, "band_nodes": int(band.sum()), "max_inside_magnitude": lo, "min_outside_magnitude": hi, "ratio": hi / lo if lo > 0 else float("inf"),
            "identical_at_lo_rep_hi": bool(np.array_equal(band, at_lo) and np.array_equal(band, at_hi)),
            "negative": int((phi[band] < 0).sum()), "positive": int((phi[band] > 0).sum()), "exact_zero": int((phi[band] == 0).sum())}


def winding_numbers(points: np.ndarray, vertices: np.ndarray, faces: np.ndarray, chunk: int = GWN_CHUNK) -> np.ndarray:
    """Generalized winding number (Van Oosterom-Strackee solid angles), numpy float64; independent of trimesh signing and libigl."""
    a0, b0, c0 = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    w = np.empty(len(points))
    for s in range(0, len(points), chunk):
        p = points[s:s + chunk, None, :]
        a, b, c = a0[None] - p, b0[None] - p, c0[None] - p
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        num = np.einsum("ijk,ijk->ij", a, np.cross(b, c))
        den = la * lb * lc + np.einsum("ijk,ijk->ij", a, b) * lc + np.einsum("ijk,ijk->ij", b, c) * la + np.einsum("ijk,ijk->ij", c, a) * lb
        w[s:s + chunk] = (2.0 * np.arctan2(num, den)).sum(axis=1) / (4.0 * np.pi)
    return w


def outside_sign_certification(phi: np.ndarray, band: np.ndarray, origin, spacing: float, vertices: np.ndarray, faces: np.ndarray) -> dict:
    idx = np.argwhere(~band)
    w = winding_numbers(np.asarray(origin, dtype=np.float64) + idx * float(spacing), vertices, faces)
    dev = np.minimum(np.abs(w), np.abs(w - 1.0))
    mismatch = int(((w > 0.5) != (phi[~band] < 0)).sum())
    return {"outside_nodes": int(len(idx)), "max_distance_from_0_or_1": float(dev.max()), "tolerance": GWN_TOL, "sign_mismatches_vs_registered": mismatch,
            "winding_float64_sha256": f64_hash(w), "pass": bool(dev.max() <= GWN_TOL and mismatch == 0)}


def enumerate_cells(phi: np.ndarray, band: np.ndarray, amp: np.ndarray) -> dict:
    """For every cell touching B, evaluate the production _corner_mean over all 2^8 sign patterns of its ambiguous corners."""
    cells = np.argwhere(_corner_mean(band.astype(np.float32)) > 0)
    idx = cells[:, None, :] + OFFSETS[None]
    ix = (idx[..., 0], idx[..., 1], idx[..., 2])
    base, amb, av = phi[ix], band[ix], amp[ix]
    n = len(cells)
    cmin, cmax = np.full(n, np.inf, np.float32), np.full(n, -np.inf, np.float32)
    for pattern in range(256):
        bits = (pattern >> np.arange(8)) & 1
        val = np.where(amb, np.where(bits[None, :] == 1, av, -av), base).astype(np.float32)
        blocks = np.empty((2 * n, 2, 2), np.float32)  # block k = rows 2k,2k+1; even output rows are the block centres
        for c, (i, j, k) in enumerate(OFFSETS):
            blocks[i::2, j, k] = val[:, c]
        centre = _corner_mean(blocks)[::2, 0, 0]
        cmin, cmax = np.minimum(cmin, centre), np.maximum(cmax, centre)
    return {"cells": cells, "cmin": cmin, "cmax": cmax}


def occupancy_certificate(phi: np.ndarray, band: np.ndarray, amp: np.ndarray, reference_mask: np.ndarray) -> dict:
    e = enumerate_cells(phi, band, amp)
    cells, cmin, cmax = e["cells"], e["cmin"], e["cmax"]
    ref = reference_mask[tuple(cells.T)]
    ambiguous = (cmin < 0) & (cmax >= 0)
    differs = ((cmin < 0) != ref) | ((cmax < 0) != ref)
    lo_field = np.where(band, -amp, phi).astype(np.float32)
    hi_field = np.where(band, amp, phi).astype(np.float32)
    lo_mask, hi_mask = cell_occupancy_of(lo_field), cell_occupancy_of(hi_field)
    c_lo, c_hi = _corner_mean(lo_field)[tuple(cells.T)], _corner_mean(hi_field)[tuple(cells.T)]
    return {"touching_cells": int(len(cells)), "ambiguous_cells": int(ambiguous.sum()), "cells_differing_from_reference": int(differs.sum()),
            "min_abs_centre_over_patterns": float(np.minimum(np.abs(cmin), np.abs(cmax)).min()),
            "endpoint_solid_counts": [int(lo_mask.sum()), int(hi_mask.sum())], "endpoint_masks_equal_reference": bool(np.array_equal(lo_mask, reference_mask) and np.array_equal(hi_mask, reference_mask)),
            "endpoints_equal_enumeration_extrema": bool(np.array_equal(c_lo, cmin) and np.array_equal(c_hi, cmax)),
            "pass": bool(ambiguous.sum() == 0 and differs.sum() == 0 and np.array_equal(lo_mask, reference_mask) and np.array_equal(hi_mask, reference_mask))}


def cell_occupancy_of(phi: np.ndarray) -> np.ndarray:
    return _corner_mean(phi) < 0.0


def amplitude_sweep(phi: np.ndarray, band: np.ndarray, reference_mask: np.ndarray, lo_mag: float) -> dict:
    """Descriptive: largest uniform ambiguity amplitude for which the two endpoint fields still give the reference mask."""
    for amp in np.geomspace(float(TAU_REP), 2.5e-2, 60):
        a = np.full(phi.shape, amp, np.float32)
        if not (np.array_equal(cell_occupancy_of(np.where(band, -a, phi).astype(np.float32)), reference_mask)
                and np.array_equal(cell_occupancy_of(np.where(band, a, phi).astype(np.float32)), reference_mask)):
            return {"first_failing_uniform_amplitude_m": float(amp), "ratio_to_observed_band_max": float(amp / lo_mag)}
    return {"first_failing_uniform_amplitude_m": None, "ratio_to_observed_band_max": None}


def smooth_volume_bound(phi: np.ndarray, band: np.ndarray, h: float) -> float:
    """|dV_eps| <= pi/(2 eps) * h^3 * sum(c_max - c_min), eps = h (cosine Heaviside Lipschitz constant), band nodes free in [-TAU_REP, TAU_REP]."""
    lo = np.where(band, -TAU_REP, phi).astype(np.float32); hi = np.where(band, TAU_REP, phi).astype(np.float32)
    return float(np.pi / (2.0 * h) * (_corner_mean(hi) - _corner_mean(lo)).astype(np.float64).sum() * h ** 3)


def gate_bounds(state: SDFDesignState, band: np.ndarray, parent: SDFDesignState, observed_band_max: float) -> dict:
    """Pass/fail robustness of the registered LOWDIM gates for every sign assignment inside B (bounds, not observable invariance)."""
    phi, h, tau = state.phi, float(state.spacing_m), float(TAU_REP)
    require(float(state.narrow_band_width_m) > tau, "narrow band must exceed tau")  # band nodes are in the Eikonal narrow band for every sign
    worst = phi.copy(); worst[band] = -TAU_REP   # clearance uses the node-level phi<0 set: every band node solid at -tau is the worst case
    clearance_worst = float(zero_level_margin_m(worst, h)); clearance_base = float(zero_level_margin_m(phi, h))
    eik = _gradient_diagnostics(state)
    eik_med = float(eik["median_abs_gradient_deviation"])
    eik_bound = lambda a: float(np.sqrt(3.0) * 2.0 * a / h)  # central difference, both neighbours flipped; median is 1-Lipschitz in sup norm
    lo = np.where(band, -TAU_REP, phi).astype(np.float32); hi = np.where(band, TAU_REP, phi).astype(np.float32)
    v_eps = float(smoothed_volume_and_gradient(state).smoothed_volume_m3)
    smooth_bound = smooth_volume_bound(phi, band, h)
    v_par = float(smoothed_volume_and_gradient(parent).smoothed_volume_m3)
    par_bound = smooth_volume_bound(parent.phi, np.abs(parent.phi) < TAU_REP, h)  # the parent has its own ambiguity band
    parent_rel = float(v_par / v_eps - 1.0)
    parent_rel_worst = [float((v_par + par_bound) / (v_eps - smooth_bound) - 1.0), float((v_par - par_bound) / (v_eps + smooth_bound) - 1.0)]
    comp = [int(ndimage.label(cell_occupancy_of(x))[1]) for x in (lo, hi)]
    out = {"clearance": {"baseline_margin_m": clearance_base, "worst_case_margin_m": clearance_worst, "gate_m": MARGIN_GATE_M, "pass": bool(clearance_worst >= MARGIN_GATE_M)},
           "eikonal_median": {"baseline": eik_med, "bound_actual_band_max": eik_bound(observed_band_max), "bound_tau": eik_bound(tau), "limit": EIKONAL_MEDIAN_MAX,
                              "pass": bool(eik_med + eik_bound(tau) < EIKONAL_MEDIAN_MAX)},
           "smoothed_volume": {"baseline_m3": v_eps, "abs_bound_m3": smooth_bound, "rel_bound": smooth_bound / v_eps, "parent_abs_bound_m3": par_bound, "band": VOLUME_BAND,
                               "parent_relative_change": parent_rel, "parent_relative_change_worst_range": parent_rel_worst,
                               "pass": bool(smooth_bound / v_eps < SMOOTH_BOUND_MAX_REL and max(abs(x) for x in parent_rel_worst) < VOLUME_BAND)},
           "cell_components": {"endpoints": comp, "required": CELL_COMPONENTS, "pass": bool(comp == [CELL_COMPONENTS] * 2)},
           "masks_and_support_preserved": "not applicable: design/fixed/forbidden/root masks are separate arrays; no phi sign enters them"}
    out["pass"] = all(out[k]["pass"] for k in ("clearance", "eikonal_median", "smoothed_volume", "cell_components"))
    return out


def verify_manifest(manifest: Path) -> dict:
    bad, n = [], 0
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        digest, name = line.split(None, 1); n += 1
        if sha256_file(ROOT / name.strip()) != digest: bad.append(name.strip())
    return {"entries": n, "mismatches": bad}


def controls(phi: np.ndarray, band: np.ndarray, reference_mask: np.ndarray) -> dict:
    """Validation/control only (never a proof input): retained sign variants must agree with the certificate."""
    rows, outside_total = {}, 0
    files = sorted(p for p in (SRCMAP01 / "diagnostics").glob("*.npz") if "difference" not in p.name and "D_unsigned" not in p.name) + [INPUTS / "v17_source_replay_2026_10_12.npz"]
    skipped = []
    for p in files:
        z = np.load(p); q = z["phi_float32"] if "phi_float32" in z.files else z["phi"]
        if q.shape != phi.shape: skipped.append(p.name); continue
        q = q.astype(np.float32); diff = np.signbit(q) != np.signbit(phi)
        rows[p.name] = {"sign_differences": int(diff.sum()), "outside_band_differences": int((diff & ~band).sum()), "mask_equals_reference": bool(np.array_equal(cell_occupancy_of(q), reference_mask))}
        outside_total += rows[p.name]["outside_band_differences"]
    require(len(rows) == CONTROL_COUNT and sorted(skipped) == ["A_v16_1.npz", "A_v16_2.npz"], f"control population {len(rows)}, skipped {skipped}")
    return {"variants": rows, "count": len(rows), "skipped_v16_controls": skipped, "outside_band_differences_total": outside_total,
            "all_masks_equal_reference": all(r["mask_equals_reference"] for r in rows.values()), "pass": bool(rows and outside_total == 0 and all(r["mask_equals_reference"] for r in rows.values()))}


def classify(r: dict) -> str:
    preds = r["predicates"]
    if any(v is None for v in preds.values()): return "INCOMPLETE"
    return "P22_V17_SIGN_INVARIANCE_CERTIFIED" if all(preds.values()) else "P22_V17_SIGN_INVARIANCE_NOT_CERTIFIED"


def verify_freeze(path: Path) -> dict:
    fr = json.loads(path.read_text()); body = {k: v for k, v in fr.items() if k != "freeze_sha256"}
    require(sha256_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()) == fr["freeze_sha256"], "freeze manifest self-hash mismatch")
    bad = [r["path"] for r in fr["files"] if sha256_file(ROOT / r["path"]) != r["sha256"]]
    require(not bad, f"frozen files changed: {bad}")
    require({**fr["frozen_parameters"], "TAU_REP": float(np.float32(fr["frozen_parameters"]["TAU_REP"]))} == {"TAU_REP": float(TAU_REP), "PLATEAU_MIN_RATIO": PLATEAU_MIN_RATIO, "GWN_TOL": GWN_TOL, "SMOOTH_BOUND_MAX_REL": SMOOTH_BOUND_MAX_REL, "REFERENCE_SOLID_CENTERS": REFERENCE_SOLID_CENTERS}, "frozen parameters differ from freeze")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"freeze_sha256": fr["freeze_sha256"], "git_head": head, "script_sha256": sha256_file(Path(__file__))}


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    provenance = verify_freeze(out / "prerun_freeze.json")
    ident = {"stl_sha256": sha256_file(INPUTS / "reference_surface.stl"), "baseline_npz_sha256": sha256_file(INPUTS / "v17_baseline.npz"), "parent_npz_sha256": sha256_file(INPUTS / "lowdim03_parent.npz")}
    require(ident == {"stl_sha256": STL_SHA, "baseline_npz_sha256": BASELINE_NPZ_SHA, "parent_npz_sha256": PARENT_NPZ_SHA}, f"input identity {ident}")
    manifest = verify_manifest(SRCMAP01 / "SHA256SUMS"); require(not manifest["mismatches"], f"SRCMAP-01 manifest {manifest}")
    state, parent = SDFDesignState.load(INPUTS / "v17_baseline.npz"), SDFDesignState.load(INPUTS / "lowdim03_parent.npz")
    require(state.state_sha256 == BASELINE_STATE_SHA, "baseline state hash")
    phi = state.phi
    mesh = trimesh.load(INPUTS / "reference_surface.stl", force="mesh")
    mesh_id = {"vertex_bytes_sha256": sha256_bytes(np.ascontiguousarray(mesh.vertices, dtype="<f8").tobytes()), "face_bytes_sha256": sha256_bytes(np.ascontiguousarray(mesh.faces, dtype="<i8").tobytes()),
               "watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent)}
    require(mesh_id["vertex_bytes_sha256"] == MESH_VERTEX_BYTES_SHA and mesh_id["face_bytes_sha256"] == MESH_FACE_BYTES_SHA, f"mesh identity {mesh_id}")
    ref_mask = cell_occupancy(state)
    r = {"provenance": provenance, "identity": ident, "mesh": mesh_id, "srcmap01_manifest": manifest, "reference_solid_centers": int(ref_mask.sum()), "tau_rep": float(TAU_REP)}
    pl = band_plateau(phi, float(TAU_REP)); band = pl.pop("band"); r["plateau"] = pl
    r["outside_sign"] = outside_sign_certification(phi, band, state.origin_m, state.spacing_m, mesh.vertices.astype(np.float64), mesh.faces)
    r["occupancy_uniform_tau"] = occupancy_certificate(phi, band, np.full(phi.shape, TAU_REP, np.float32), ref_mask)
    r["occupancy_actual_magnitude"] = occupancy_certificate(phi, band, np.abs(phi), ref_mask)
    r["amplitude_sweep"] = amplitude_sweep(phi, band, ref_mask, pl["max_inside_magnitude"])
    r["gates"] = gate_bounds(state, band, parent, pl["max_inside_magnitude"])
    r["controls"] = controls(phi, band, ref_mask)
    np.savez_compressed(out / "band_nodes.npz", indices=np.argwhere(band).astype(np.int16))
    r["predicates"] = {
        "P1_plateau": bool(pl["identical_at_lo_rep_hi"] and pl["ratio"] >= PLATEAU_MIN_RATIO and pl["band_nodes"] > 0),
        "P2_outside_sign_numerical_certification": r["outside_sign"]["pass"] and mesh_id["watertight"] and mesh_id["winding_consistent"],
        "P3_occupancy_interval_certificate": r["occupancy_uniform_tau"]["pass"] and r["occupancy_actual_magnitude"]["pass"] and r["reference_solid_centers"] == REFERENCE_SOLID_CENTERS
        and r["occupancy_uniform_tau"]["endpoints_equal_enumeration_extrema"],
        "P4_gate_classification_robustness": r["gates"]["pass"],
        "P5_controls_consistent": r["controls"]["pass"]}
    r["terminal_classification"] = classify(r)
    r["runtime"] = {"python": platform.python_version(), "numpy": np.__version__, "trimesh": trimesh.__version__, "platform": platform.platform()}
    r["claims_not_made"] = ["mapping reproducibility", "signer qualification", "correctness of any sign inside the band", "other STLs or lattices", "CFD response", "physical or continuum volume"]
    (out / "classification.json").write_text(json.dumps({"terminal_classification": r["terminal_classification"], "predicates": r["predicates"], "cfd_runs": 0, "kaggle_submissions": 0, "selected_delta": None, "shape_update_allowed": False}, indent=2, sort_keys=True) + "\n")
    (out / "certificate.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    return r


def main(out: Path) -> int:
    try:
        res = run(out)
    except Exception as e:  # any failure before a verdict is INCOMPLETE and is recorded, never silently dropped
        out.mkdir(parents=True, exist_ok=True)
        (out / "classification.json").write_text(json.dumps({"terminal_classification": "INCOMPLETE", "exception_class": type(e).__name__, "exception_message": str(e), "cfd_runs": 0,
                                                             "kaggle_submissions": 0, "selected_delta": None, "shape_update_allowed": False}, indent=2, sort_keys=True) + "\n")
        print("INCOMPLETE", type(e).__name__, e); return 1
    print(res["terminal_classification"], json.dumps(res["predicates"])); return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("--output-dir", type=Path, required=True)
    sys.exit(main(ap.parse_args().output_dir))
