#!/usr/bin/env python3
"""Read-only post-registration diagnosis of one frozen correspondence failure.

This is not a replacement evaluator, does not change gates, and cannot qualify
any geometry. The original failed records and immutable scripts remain intact.
"""

import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def main():
    case = "D0_interface_offset_minus"
    r = 4
    result = json.loads((OUT / "result.json").read_text())
    parent = next(
        p for p in result["fidelity_pairs"] if p["r"] == r and p["case"] == case
    )
    with np.load(OUT / "surfaces" / f"r{r}" / case / "normal_correspondence.npz") as z:
        samples = z["double_samples"]
    index = int(np.nanargmax(samples[:, -1]))
    row = samples[index]
    point, normal = row[:3], row[3:6]
    reg = json.loads((OUT / "preregistration.json").read_text())
    path = ROOT / reg["inputs"][case]["path"]
    with np.load(path) as z:
        phi = z["phi"].astype(float)
        m = json.loads(str(z["metadata"]))
    h = float(m["spacing_m"])
    origin = np.array(m["origin_m"])
    axes = [origin[a] + h * np.arange(phi.shape[a]) for a in range(3)]
    interp = RegularGridInterpolator(axes, phi, bounds_error=True)

    def f(t):
        return float(interp((point + t * normal)[None, :])[0])

    # One source-cell interval along the largest normal coordinate contains a
    # direct sign crossing; this bracket diagnoses an omitted root, not all roots.
    dominant = int(np.argmax(np.abs(normal)))
    upper = h / abs(normal[dominant])
    a, b = 0.0, upper
    assert f(a) * f(b) < 0
    root = brentq(f, a, b, xtol=np.nextafter(0.0, 1.0), rtol=4 * np.finfo(float).eps)
    independent = json.loads(
        (
            OUT / "independent_partitions" / f"r{r}" / "independent_result.json"
        ).read_text()
    )
    verifier = next(p for p in independent["fidelity_pairs"] if p["case"] == case)
    pdiag = parent["double"]["root_diagnostics"][index]
    vdiag = verifier["double"]["samples"][index]
    baseline_root = pdiag["baseline_root_m"]
    guard = h * 1e-8
    record = dict(
        evidence_class="post_registration_root_omission_diagnostic_not_qualification",
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        case=case,
        r=r,
        sample_index=index,
        point_m=point.tolist(),
        normal=normal.tolist(),
        source_field_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_cell_bracket_t_m=[a, b],
        bracket_phi_m=[f(a), f(b)],
        direct_sign_root_t_m=float(root),
        direct_root_residual_m=abs(f(root)),
        guard_t_m=guard,
        direct_root_guard_phi_m=[f(root - guard), f(root + guard)],
        parent_target_root_t_m=pdiag["target_root_m"],
        parent_target_root_audit=pdiag["target"],
        independent_sample=vdiag,
        mesh_root_t_m=float(row[7]),
        diagnostic_mesh_minus_source_delta_m=float(row[7] - (root - baseline_root)),
        parent_residual_candidate_cutoff_m=h * 1e-10,
        parent_failure_max_m=parent["double"][
            "maximum_normal_displacement_difference_m"
        ],
        independent_failure_max_m=verifier["double"][
            "maximum_normal_displacement_difference_m"
        ],
        parent_unresolved=parent["double"]["unresolved_samples"],
        independent_unresolved=verifier["double"]["unresolved_samples"],
        both_registered_numeric_gates_fail=not parent["double"]["within_limit"]
        and not verifier["double"]["within_limit"],
        qualification_flags=reg["qualification_flags"],
        claims=[
            "A nearer original-trilinear sign crossing exists in the source cell; the parent chooses a farther root after residual-based candidate omission.",
            "A local sign certificate verifies an accepted root; it does not prove exhaustive root enumeration or nearest-root uniqueness.",
            "Boolean gate agreement does not mean displacement metrics or per-sample correspondence agree.",
            "Large frozen error values cannot all be interpreted as actual surface displacement error; no frozen criteria or sources are changed.",
        ],
    )
    (OUT / "ray_root_omission_diagnostic.json").write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        record["sample_index"],
        record["direct_sign_root_t_m"],
        record["diagnostic_mesh_minus_source_delta_m"],
    )


if __name__ == "__main__":
    main()
