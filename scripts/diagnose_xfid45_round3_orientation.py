#!/usr/bin/env python3
"""Post-registration auxiliary diagnostics; never changes a qualification gate."""

import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from xfid45_round3_export import _edge_components
from xfid45_round3_measure import Field

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def main():
    reg = json.loads((OUT / "preregistration.json").read_text())
    result = json.loads((OUT / "result.json").read_text())
    rows = []
    for case in result["cases"]:
        folder = OUT / "surfaces" / f"r{case['r']}" / case["case"]
        with np.load(folder / "surface.npz") as z:
            v, f = z["vertices"], z["faces"]
        with np.load(ROOT / reg["inputs"][case["case"]]["path"]) as z:
            phi = z["phi"]
            m = json.loads(str(z["metadata"]))
            o = np.array(m["origin_m"])
            h = float(m["spacing_m"])
        tri = v[f]
        centers = tri.mean(1)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        length = np.linalg.norm(normals, axis=1)
        normals = np.divide(
            normals,
            length[:, None],
            out=np.zeros_like(normals),
            where=length[:, None] > 0,
        )
        _, _, gradient = Field(phi, o, h).value_error_grad(centers, True)
        dots = np.einsum("ij,ij->i", normals, gradient)
        _, inverse = np.unique(v, axis=0, return_inverse=True)
        labels, _ = _edge_components(inverse[f])
        components = []
        for cid in np.unique(labels):
            ids = np.flatnonzero(labels == cid)
            vv = (
                np.einsum(
                    "ij,ij->i", tri[ids, 0], np.cross(tri[ids, 1], tri[ids, 2])
                ).sum()
                / 6
            )
            components.append(
                dict(
                    component_id=int(cid),
                    face_count=len(ids),
                    normal_dot_gradient_min=float(dots[ids].min()),
                    normal_dot_gradient_median=float(np.median(dots[ids])),
                    normal_dot_gradient_max=float(dots[ids].max()),
                    positive_dot_face_fraction=float((dots[ids] > 0).mean()),
                    negative_dot_face_fraction=float((dots[ids] < 0).mean()),
                    signed_volume_m3=float(vv),
                    bounds_m=[
                        tri[ids].min((0, 1)).tolist(),
                        tri[ids].max((0, 1)).tolist(),
                    ],
                )
            )
        rows.append(
            dict(
                r=case["r"],
                case=case["case"],
                topology_prerequisite=case["statistics"]["topology_pass"],
                registered_orientation_status=case["orientation"]["status"],
                components=components,
            )
        )
    # Read-only original-field star and backend-precision diagnosis.
    with np.load(ROOT / reg["inputs"]["baseline"]["path"]) as z:
        source = z["phi"]
    indices = np.argwhere(source == 0)
    mixed = nonpositive = nonnegative = 0
    for index in indices:
        star = source[tuple(slice(int(k) - 1, int(k) + 2) for k in index)]
        nonpositive += int(star.max() <= 0)
        nonnegative += int(star.min() >= 0)
        mixed += int(star.min() < 0 and star.max() > 0)
    pole = np.array([60, 16, 30])
    value = float(source[tuple(pole)])
    tau = float(np.float32(0.025 * 2**-20))
    offsets = []
    for axis in (1, 2):
        for sign in (-1, 1):
            neighbor = pole.copy()
            neighbor[axis] += sign
            endpoint = float(source[tuple(neighbor)])
            offsets.append(
                dict(
                    node=neighbor.tolist(),
                    original_phi_m=endpoint,
                    tied_endpoint_phi_m=tau if endpoint == 0 else endpoint,
                    edge_root_from_pole_m=0.025 * value / (value - tau)
                    if endpoint == 0
                    else None,
                )
            )
    backend = dict(
        defect_node=pole.tolist(),
        original_phi_m=value,
        reported_mesh_point_is_exact_original_zero=False,
        tau_m=tau,
        tau_to_pole_abs_phi_ratio=tau / abs(value),
        cardinal_edges=offsets,
        float32_half_ULP_world_m=(
            np.spacing(pole.astype(np.float32)).astype(float) * 0.025 / 2
        ).tolist(),
        zero_node_star_counts=dict(
            exact_zero_count=len(indices),
            mixed_sign=mixed,
            nonpositive=nonpositive,
            nonnegative=nonnegative,
        ),
        claim="near-node tie roots below float32 geometry resolution explain r1 coincident crossings; this does not prove original trilinear zero-set manifoldness or impossibility; zero-star same-sign hypothesis not observed",
    )
    report = dict(
        evidence_class="post_registration_auxiliary_gradient_diagnostic_not_qualification",
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope="n dot grad phi is auxiliary only; component grouping is the frozen edge-connected definition; no flips, vertex changes, thresholds or gates modified. Signed-volume tags on ambiguous components do not establish physical solid/void class.",
        qualification_flags=reg["qualification_flags"],
        cases=rows,
        original_field_and_backend_diagnostic=backend,
    )
    (OUT / "auxiliary_orientation.json.gz").write_bytes(
        gzip.compress(
            json.dumps(report, sort_keys=True, allow_nan=False).encode(), mtime=0
        )
    )


if __name__ == "__main__":
    main()
