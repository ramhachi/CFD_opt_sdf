"""Reproduce Amendment-1 band diagnostics; no solver, tuning or qualification.

Run from any directory using the repository venv. Prints deterministic JSON;
the independent dense-boundary oracle is reused from the committed test, not
from the production projection code. Random coordinates and amplitudes are
fixed below before the run. The finite point cloud bounds its own coverage
error; values are not proofs for every possible geometry or query.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import runpy
import sys

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/"src"))
from cfd_sdf.scene.primitives import PlateElement  # noqa: E402


def main():
    oracle = runpy.run_path(str(ROOT/"tests/scene/test_primitives.py"))
    gradient, dense, raw_section = (oracle[k] for k in ("gradient","dense_zero_set","raw_section"))
    rows = []
    for camber,reflex in itertools.product((-.06,-.03,0.,.03,.06),(-.04,-.02,0.,.02,.04)):
        body = PlateElement("probe",0.,0.,1.,.1,camber=camber,reflex=reflex)
        tree = cKDTree(dense(1.,.1,camber,reflex))
        for dimension in (2,3):
            rng = np.random.default_rng(610)
            points = rng.uniform([-.57,-.17],[.57,.17],(1700,2)) if dimension==2 else rng.uniform(
                [-.57,-.7,-.17],[.57,.7,.17],(1700,3))
            values = body.phi(points)
            mask = np.abs(values)<=.05
            points,values = points[mask],values[mask]
            section = points if dimension==2 else points[:,[0,2]]
            distances = tree.query(section)[0]
            reference = np.where(raw_section(section,1.,.1,camber,reflex)<0,-distances,distances)
            if dimension==3:
                dy = np.abs(points[:,1])-.5
                reference = np.minimum(np.maximum(reference,dy),0)+np.hypot(np.maximum(reference,0),np.maximum(dy,0))
            max_error = float(np.max(np.abs(values-reference))/.1)
            median_gradient = float(np.median(np.abs(np.linalg.norm(gradient(body,points),axis=-1)-1)))
            if max_error>.02 or median_gradient>.10:
                raise RuntimeError("band contract failed")
            rows.append({"camber_over_c":camber,"reflex_over_c":reflex,"dimension":dimension,
                "band_points":len(points),"max_error_over_t":max_error,"median_gradient_error":median_gradient})
    source_paths = ["src/cfd_sdf/scene/primitives.py","tests/scene/test_primitives.py",
        "docs/codex/gen01_w1_2026_11_06/reports/wp06_band_check.py"]
    print(json.dumps({"evidence_class":"solver_free_development_diagnostic","seed":610,
        "c_m":1.,"t_m":.1,"h_m":.025,"queries_per_case":1700,
        "surface_side_points":50001,"gradient_step_m":1e-6,"max_error_over_t_limit":.02,
        "median_gradient_error_limit":.10,"scope":"finite sampled band; not a global convergence or physical qualification",
        "sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_paths},"cases":rows},
        sort_keys=True,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
