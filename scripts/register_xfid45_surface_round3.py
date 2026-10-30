#!/usr/bin/env python3
"""Create fixed Round3 input manifest without extracting target surfaces."""

import hashlib
import importlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def spec(path):
    path = Path(path)
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    prior = json.loads(
        (
            ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03/preregistration.json"
        ).read_text()
    )
    origin = np.array([-1.0, -0.8, -0.6])
    h = 0.025
    shape = (121, 65, 49)
    p = np.stack(
        np.meshgrid(
            *(origin[a] + h * np.arange(shape[a]) for a in range(3)), indexing="ij"
        ),
        axis=-1,
    )

    def ellipsoid(center, axes):
        return min(axes) * (np.sqrt(np.sum(((p - center) / axes) ** 2, axis=-1)) - 1)

    q = p - np.array([0.043, -0.061, 0.037])
    fields = {
        "heldout_R3_torus": (
            np.sqrt((np.hypot(q[..., 0], q[..., 1]) - 0.20) ** 2 + q[..., 2] ** 2)
            - 0.07,
            "center=(.043,-.061,.037), major radius=.20m, tube radius=.07m; sqrt((hypot(x-cx,y-cy)-R)^2+(z-cz)^2)-a",
        ),
        "heldout_R3_two_ellipsoids": (
            np.minimum(
                ellipsoid(
                    np.array([-0.113, 0.087, 0.049]), np.array([0.31, 0.19, 0.14])
                ),
                ellipsoid(np.array([0.45, -0.21, 0.02]), np.array([0.12, 0.09, 0.08])),
            ),
            "min of ellipsoid level min(axes)*(norm((p-center)/axes)-1); centers=(-.113,.087,.049),(.45,-.21,.02); axes=(.31,.19,.14),(.12,.09,.08)",
        ),
        "heldout_R3_eccentric_void": (
            np.maximum(
                ellipsoid(
                    np.array([-0.023, 0.041, 0.057]), np.array([0.30, 0.23, 0.20])
                ),
                0.09 - np.linalg.norm(p - np.array([0.031, -0.017, 0.024]), axis=-1),
            ),
            "max of outer ellipsoid center=(-.023,.041,.057), axes=(.30,.23,.20), and .09-norm(p-(.031,-.017,.024)); fluid cavity radius=.09m",
        ),
    }
    held = OUT / "inputs"
    held.mkdir(parents=True, exist_ok=True)
    inputs = {
        "baseline": spec(
            ROOT
            / "docs/evidence/xfid01_geometry_preflight_2026_10_03/canonical_state.npz"
        )
    }
    targets = list(prior["frozen_direction_contract"]["cases"])
    for case in targets:
        inputs[case] = spec(
            ROOT
            / prior["frozen_direction_contract"]["cases"][case]["state_snapshot_path"]
        )
    formulas = {}
    for name, (phi, formula) in fields.items():
        file = held / f"{name}.npz"
        metadata = {
            "origin_m": origin.tolist(),
            "spacing_m": h,
            "shape": list(shape),
            "formula": formula,
            "purpose": "fresh synthetic heldout, not canonical design state or formal FD direction",
        }
        np.savez_compressed(
            file,
            phi=phi.astype(np.float64),
            metadata=np.array(json.dumps(metadata, sort_keys=True)),
        )
        inputs[name] = spec(file)
        formulas[name] = metadata
    source_names = [
        "audit_xfid45_surface_round3.py",
        "xfid45_round3_export.py",
        "xfid45_round3_measure.py",
        "verify_xfid45_round3.py",
        "verify_xfid45_surface_round3.py",
        "register_xfid45_surface_round3.py",
        "xfid45_surface_round2_candidates.py",
    ]
    sources = {n: spec(ROOT / "scripts" / n) for n in source_names}
    sources.update(
        {
            n: spec(ROOT / "tests" / n)
            for n in ["test_xfid45_round3_export.py", "test_xfid45_round3_measure.py"]
        }
    )
    runtime_files = {"python": spec(Path(sys.executable).resolve())}
    for name in [
        "skimage.measure._marching_cubes_lewiner_cy",
        "skimage.measure._marching_cubes_lewiner",
        "skimage.measure._marching_cubes_lewiner_luts",
        "scipy.ndimage._nd_image",
        "scipy.ndimage._interpolation",
    ]:
        runtime_files[name] = spec(
            Path(importlib.import_module(name).__file__).resolve()
        )
    runtime = {
        name: importlib.metadata.version(name)
        for name in [
            "numpy",
            "scipy",
            "scikit-image",
            "trimesh",
            "rtree",
            "pyvista",
            "vtk",
            "pytest",
        ]
    }
    runtime.update(
        python=platform.python_version(),
        platform=platform.platform(),
        machine=platform.machine(),
        executable=sys.executable,
        thread_environment={"OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"},
    )
    reg = {
        "schema_version": 1,
        "round_id": "XFID45_surface_round3_2026_10_03",
        "evidence_class": "immutable_solver_free_export_candidate_registration",
        "branch": "exp/issue45-surface-round3-2026-10-03",
        "authoritative_branch": "codex/kaggle-batch-migration",
        "authoritative_start_head": "7351d41e31ab8f4ba939e426831646af409ee9a7",
        "integration": "--no-ff, never force-push/reset/main",
        "predecessor_registration": spec(
            ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03/preregistration.json"
        ),
        "predecessor_result": spec(
            ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03/result.json"
        ),
        "epsilon_m": 0.005,
        "grid_h_m": h,
        "canonical_v17": prior["canonical_v17"],
        "frozen_direction_contract": prior["frozen_direction_contract"],
        "inputs": inputs,
        "fidelity_target_cases": targets,
        "fresh_heldout_formulas": formulas,
        "sources": sources,
        "runtime_files": runtime_files,
        "runtime_identity": runtime,
        "upstream_source": dict(
            spec(OUT / "lewiner_0_25_2_source.pyx"),
            url="https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/measure/_marching_cubes_lewiner_cy.pyx",
            interpretation="backend weights use 1/(eps64+abs(phi)); finite numerical floor remains fixed",
        ),
        "candidates": {
            "uniform_virtual_refinement": {
                "r": [1, 2, 4, 8],
                "design_state_changes": False,
                "resampling": "float64 scipy.ndimage.zoom endpoint aligned, order=1, grid_mode=False, prefilter=False; values from original trilinear field",
                "extractor": "scikit-image 0.25.2 Lewiner, level=0, step_size=1, ascent, allow_degenerate=False",
                "processing_sequence": [
                    "virtual trilinear sampling",
                    "scratch exact-zero tie",
                    "native Lewiner extraction",
                    "voxel-to-world mapping",
                    "topology prerequisite",
                    "whole-component sidedness orientation if valid",
                    "save untouched vertex coordinates NPZ and float32 STL",
                    "independent saved-artifact assessment",
                ],
                "adaptive_candidate": None,
            }
        },
        "zero_tie": {
            "previous_prohibition_explicitly_lifted_for_round3": True,
            "tau_m": float(np.float32(h * 2**-20)),
            "rule": "only exact float64 zero virtual nodes -> +tau in extraction scratch; original fields immutable",
            "nearzero_nonzero": "retained unchanged; no clamp or relative rescale",
            "float32_cast": "native backend conversion; any nonzero-to-zero underflow fails lineage; rounding max recorded",
            "finite_tau_semantics": "finite positive realization of fixed symbolic sign, not a claim of infinitesimal exactness",
        },
        "component_definition": "exact coordinate identity for audit adjacency only; edge-connected face graph retaining EVERY face incl degenerate; all incidences of nonmanifold edges connected; order by minimum original face id",
        "gate_order": [
            "lineage",
            "edge manifold then vertex link manifold then watertight/winding/duplicate/degenerate",
            "component sidedness orientation",
            "absolute trilinear zero-set sample geometry",
            "baseline-to-six normal displacement fidelity",
            "clearance",
        ],
        "topology": "closed edge counts exactly 2; each vertex link one connected degree-2 cycle; no duplicate faces, repeated-index or exact zero-area triangles; coherent winding; NPZ float64 and roundtripped STL float32 both required; manifold expected by construction but not guaranteed",
        "orientation": {
            "prerequisite": "global topology pass; otherwise N/A and NO flips",
            "deltas_over_original_h": [0.02, 0.05, 0.1],
            "criterion": "strict area >50% two-sided phi signs at each delta, same polarity all deltas; only whole-component flip",
            "sign_guard_m": 64 * np.finfo(float).eps * h,
            "stored_gate": "all components already outward towards fluid and global signed volume >0",
            "solid_void": "positive contribution solid boundary, negative contribution void boundary; classification conditional on stable orientation",
            "gradient_dot": "auxiliary only, never orientation decision",
        },
        "absolute_geometry": {
            "limit_m": 0.0005,
            "analytic_formula": "min(.1 epsilon,.02 original_h)",
            "samples": "10 degree-3 barycentric samples per triangle, including all vertices, edge and interior points, on BOTH double and STL surfaces",
            "lower": "max(abs(phi)-E,0)/L where global per-axis max edge slopes bound gradient and L inflated 64eps64",
            "evaluation_error": "E=64eps64*sum(abs(eight weighted corner terms))",
            "upper": "axis-line original-cell root intervals from reliable signs and endpoint E bounds; exact zero witness only phi==0 and E==0; coordinate guard h*1e-9",
            "search": "initial axis witnesses plus <=20 Newton proposals, step cap h; proposal points never move surface vertices",
            "independent_search": "finite-difference proposal gradient h*1e-5 vs parent analytic gradient",
            "failure": "unresolved upper OR certified upper >limit; certified lower>limit separately reported",
            "scope": "guarded floating-point sampled lower/upper distances, NOT a continuous Hausdorff certificate nor full directed-rounding interval arithmetic",
        },
        "normal_fidelity": {
            "limit_m": 0.0005,
            "analytic_formula": "min(.1 epsilon,.02 original_h)",
            "samples": 1024,
            "anchors": "unique area-stratified baseline triangle centroids at CDF quantiles (k+.5)/1024",
            "normal": "original baseline analytic trilinear grad phi normalized, not current triangle normal",
            "source_correspondence": "nearest unique absolute ray zero of source baseline and target trilinear fields in +/-2h; original-cell segments are cubic; ambiguous tie or zero interval unresolved",
            "source_root_guard": "sign crossing certified at t +/- h*1e-8 using E intervals",
            "mesh_correspondence": "target stored triangle ray hits, nearest unique absolute t; baseline anchor mesh t=0",
            "dedup_and_tie_m": h * 1e-9,
            "error_upper": "abs(mesh_target_t-(SDF_target_t-SDF_baseline_t))+2h*1e-8+h*1e-9",
            "applicability": "six canonical baseline-to-perturbation pairs; heldouts have no paired direction so this gate is N/A by design, not a fail",
            "prerequisite": "all baseline and target surface gates pass; otherwise correspondence diagnostic only, qualification N/A",
            "volume": "original SDF Gauss xy n=16,32,64 with exact linear-z sublevel fraction; approximate ladder not a certified integral; mesh and STL signed-volume changes recorded",
        },
        "clearance": {
            "minimum_m": 0.25,
            "flow_box_m": [[-2.5, -1.2, -0.9], [2.5, 1.2, 0.9]],
        },
        "determinism": "two independent extraction+orientation calls per case/r, exact little-endian vertex/face array SHA256 equality required in lineage; gzip mtime=0",
        "independent_verifier": {
            "source_imports": "neither extractor nor parent evaluation helpers imported",
            "input": "saved NPZ and gzip lossless raw binary STL; original snapshot fields",
            "recomputes": [
                "topology",
                "orientation",
                "sample distance bounds",
                "normal correspondence",
                "mesh signed volumes",
                "original SDF volume ladder",
            ],
            "agreement": "ALL individual Boolean/status gates and aggregate decisions equal; SDF/mesh volumes rtol=1e-8 atol=h^3*1e-9",
            "lineage_scope": "source/artifact hashes and frozen extraction provenance checked; independent verifier does not re-run extraction",
        },
        "selection": "evaluate every r on every input; choose smallest r for which all10 double+STL surface gates, all6 fidelity pairs, independent per-gate/aggregate/volume agreement pass",
        "all_fail_action": "distinguish finite sampling/refinement insufficiency, intrinsic original zero-set singularity, backend precision/tie floor and serialization defects; no proof of intrinsic impossibility from candidate failure alone; raise direct GridSDF Stage V reconsideration to user, do not implement",
        "step0": {
            "evidence_class": "synthetic_definition_check_not_qualification",
            "focused_log": spec(ROOT / "work/xfid45_round3_step0.log"),
            "tests": "degenerate/nonmanifold-edge/pinched-vertex/void/float32-collapse plus identity, normal fidelity, volume and import independence; 16 passed before registration",
            "thresholds_fitted": False,
        },
        "forbidden": prior["forbidden"]
        + [
            "OpenCode",
            "direct GridSDF Stage V selection this round",
            "post-result evaluator/verifier/threshold changes",
        ],
        "qualification_flags": prior["qualification_flags"],
        "production_exporter_change": False,
    }
    # Copy synthetic log into tracked evidence and bind that immutable copy.
    (OUT / "step0.log").write_bytes(
        (ROOT / "work/xfid45_round3_step0.log").read_bytes()
    )
    reg["step0"]["focused_log"] = spec(OUT / "step0.log")
    (OUT / "preregistration.json").write_text(
        json.dumps(reg, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print("registered fixed inputs without target extraction")


if __name__ == "__main__":
    main()
