# WP05 mesh and OpenFOAM design

Amendment 1 supersedes the first-attempt density and layer-count choices below.
See [the correction design](wp05_amendment1_design.md) and current WP5 report.
Input polylines must satisfy non-cap turn <=5 degrees and every segment <=ds,
including finite-cap segments. WP4 supplies the smooth dense vertices; WP5
does not resample. A generic subdivided cap declares `cap_start_index` (default
penultimate vertex for one edge); all points from that endpoint to closure
must lie in monotone order on the straight cap. WP4's adapter derives the
index from the paired-surface prefix and preserves its supplied cap suffix.
Only the two TE cap endpoints (or sharp cusp) are exempt from the turn test.

`boundary_layer_plan(geometries)` requires all six E1/E2/E3 thick/sharp inputs,
records their exact hashes and minimum ground/inter-element gap, and computes
one `T.layers` result per family. `write_case(..., boundary_layer_plan=plan)`
reads those fixed values for both bodies and ground. Production without a
six-member study plan fails before output creation. Short synthetic cases
can explicitly use a development plan, which cannot authorize a production
render. The plan's compact sorted JSON bytes have the same SHA as
`plan_sha256(plan)`. No present six-member WP4 study plan is invented.

T2-0's LE ball, TE and wake sizing remain inherited. Wall Distance now uses
the supplied dense point set rather than three samples per polyline segment;
the mesh manifest retains the informational proxy. Only checkMesh controls
acceptance. The synthetic tiny-third-nose test checks topology and finite
proxy reporting, and does not assert a qualified three-body mesh.

This is a development design record, not a registration, qualification or a change to the roadmap. The parent WP05 design covers the complete package. The implementation follows the shared W1 README, AGENTS authority split, TOPO-2D-00 §§2–4 and 7–10, immutable T2-0 helpers and LOCAL-OF-01. Ponytail applies: reuse the existing numerical and dictionary helpers; add only the multi-hole gmsh geometry assembly that the single-body helper cannot express.

## Geometry interface and scope

Input is a JSON object with `config` and `elements`. Every element has `name`, `points_m` (a finite, explicitly closed N×2 polygon in physical metres, at least 3 unique points), and `te_kind` (`sharp` or `blunt`). The first point is the trailing edge. For a blunt contour, the first and penultimate points are the two cap endpoints; the final duplicate closes the cap. Optional `main_chord_m` must equal the common T2-0 reference 0.2234 m; optional `ride_height_m` is checked against the contour minimum. NPZ uses a scalar Unicode `metadata_json` with the same object, each element replacing `points_m` by `points_key`; that key addresses a numeric N×2 array. Pickled objects are rejected. A declared `units` must be `m`; declared `reference_chord_m` must also equal 0.2234 m. Raw input bytes receive SHA-256; every element's metadata is retained.

There are 1–3 bodies, ordered main, flap, second flap. Wall patches are `airfoil`, `airfoil_2`, `airfoil_3`; inlet, outlet, top, ground, front and back retain the T2-0 names. Polygons must be closed, simple, disjoint, above ground and strictly inside the unchanged domain. The geometry is supplied by WP4/the user; no published E2 section is invented from a figure. At the initial design this worktree contained neither WP4 geometry nor authoritative flap coordinates. The later direct WP4 adapter below resolves the export interface; actual E2 smoke and source-verification status are recorded by the parent report. Synthetic two-body fixtures are marked as such.

## Mesh and blunt trailing edge

Use the unchanged `t20_case` values for domain, thickness, far size, surface spacing, first height and layer growth. The second family is existing `med30`, avoiding a new family or pin. Import `layers`, `_stats`, `_write_msh`, `mesh_quality`, `quality_failures`, `sha256` and constants from `t20_case`; the new function assembles two/three holes rather than copying the old generator. One gmsh line per supplied segment preserves WP4's exact closed polygon (no spline approximation). A single gmsh BoundaryLayer field covers every element (same ds/y1/g). Dense input vertices may force surface edges finer than nominal ds; input segment minima/maxima are recorded and no identical realized tangential spacing to the original spline mesh is claimed. Layer count is capped using the minimum ground/inter-body gap and the existing `layers` helper, then checked against that gap.

Sharp contours use the inherited fan count at the explicit first point. Blunt contours retain their finite closing cap as a line and have no fan points at either cap corner. Their local surface size is capped near the trailing-edge corners, and the same quality proxy is recorded. Neither proxy success nor local checkMesh success qualifies Kaggle physics; LOCAL-OF-01 makes platform-dependent gmsh variation an explicit property of the pipeline. Each realisation is a fresh mesh, identified by SHA, not a pseudo-random seed or guaranteed distinct topology.

## OpenFOAM dictionaries and continuation

`t2d_foam_case.write_case(out, geometry, model='sa-wf', family='fine30', realisation=0, iters=5000)` generates mesh, dictionaries and a T2-0-style `case_manifest.json`. The immutable `t20_foam.fields` and `system_and_constant` supply the dictionaries. Additional wall entries are duplicated from the generated airfoil entry; total `forceCoeffs` includes all element patches, and `forceCoeffs_<patch>` writes each element with the same reference chord 0.2234 m and area 0.2234×0.002 m². Thus per-element coefficients sum to the total, and all E1/E2/E3 increments have the same normalization. `forces` remains the total dimensional force object; `forces_<patch>` retains the pressure/viscous force split per element, needed to compare pressure-integrated experimental Cp without silently substituting total RANS force. `Cl` is downforce (+groundward = −y), `Cd` is drag (+x). SA and SST wall-function models are supported; these are fully turbulent closures with no trip or transition model, matching the draft's stated modelling scope rather than simulating free transition physically.

5000 is the production initial cap. A smoke may request 1–200; intermediate caps are rejected. SIMPLEC 0.9, residual thresholds and schemes stay inherited. The manifest records the unchanged T2-0c rule: 20%-tail, ≥50 rows; 20-iteration block means; relative block standard deviation and relative drift <0.005; one continuation from latestTime to 15000 if the plateau fails; raw tail relative standard deviation >0.005 is unsteady. Runner/collector handle the decision. Prewritten continuation dictionaries use the same SIMPLEC settings and latestTime.

## Test plan and assumptions

Write tests before implementation. Without gmsh, only mesh-execution tests skip via `importlib.util.find_spec('gmsh') is None`, matching conftest; format validation and dictionary tests still run. Two-body synthetic fixtures verify patches, count, raw geometry/mesh SHAs, finite proxy metrics, fine30 first layer, fans recorded only on sharp bodies, and element function objects. Negative tests cover malformed/overlapping contours, unknown trailing-edge kind, unsupported models and iteration caps. NPZ and JSON must agree. Local Docker mesh-only/checkMesh and ≤200 iterations are parent-owned. No Kaggle operation, frozen-source edit, dependency or global configuration change is authorized here.

## Development verification record

The first import-only TDD invocation failed because the new modules did not exist. After implementation the initial 11 tests passed (32.43 s). Review replaced interpolating splines by exact polygon segments, added strict units/reference-chord and NPZ scalar checks, and retained per-element dimensional pressure/viscous objects. The new dimensional-object test first failed, then passed after cloning the inherited `forces` block. Final mesh-bearing invocation was `.venv/bin/python -m pytest -q tests/topo2d00/test_multibody_case.py --basetemp /private/tmp/wp05-mesh-verification`: **17 passed in 98.27 s**. A subsequent raw-byte NPZ hash/read fix was checked by the pure format/dictionary subset: **14 passed, 3 deselected in 8.01 s**. Compileall of both new modules and this test file and `git diff --check` passed. The parent owns the full-suite baseline/final comparison and local Docker checkMesh/solver evidence.

All three synthetic exact-polygon meshes have zero inherited quality-proxy failures and zero unused nodes. These local Python/gmsh records do not constitute OpenFOAM checkMesh or published E2 evidence:

| synthetic fixture | cells | max nonorth (deg) | max internal skew | minimum weight | minimum volume ratio | minimum determinant | mesh SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2 sharp bodies, fine30 | 37505 | 47.3567 | 0.739595 | 0.125446 | 0.140074 | 0.0300731 | `0c17def80c36f8b452d3addecf1cfd63c9dc9f6e85469429f3306b4bdef39a95` |
| 2 blunt bodies, fine30, no fan | 37489 | 60.8721 | 0.868029 | 0.125446 | 0.140074 | 0.0156487 | `a61059b382e4dd5c544fb1d1e04501e2c4b6b9329d74ba666357f884b7985d96` |
| 3 sharp bodies, med30 | 27128 | 62.1817 | 1.161775 | 0.0659761 | 0.0672054 | 0.0164540 | `94c3eff06c21dc74ae53a416d9c64045e36459e6e57def989a3be5e6347e23a3` |

Fine30 first-cell medians are 0.600279 mm (sharp) and 0.600291 mm (blunt). Exact synthetic manifests/meshes are under `/private/tmp/wp05-mesh-verification/test_multibody_mesh_manifest_s0/case`, `..._b0/case` and `test_threebody_med300/case`. Source formatting/diagnostic-only additions during the development test are not registered evidence; the parent will bind the completed source and final smoke artifacts separately. No repeat was used to select a favorable mesh. The separate three-body med30 control also passed once in 18.48 s before the final full-file invocation.

WP4's later actual `geometry.py` resolved the export contract. Its `topo2d-scene-v1` JSON and `scene_json` NPZ are accepted directly as detailed below; no guessed trailing-edge ordering is used. The original published finite-thickness trailing edges remain blunt even when their arm name ends in `_sharp`.

Final review additionally tests known configuration/element-count identity (E1/E1_sharp=1, E2/E2_sharp=2, E3/E3_sharp=3; generic development identifiers are allowed). `nominal_ride_height_m` with explicit `height_datum` is retained separately from `minimum_clearance_m` and `main_element_clearance_m`. The legacy manifest `h_m`/`h_over_c` fields are labelled as the current-contour minimum, never as an inferred published zero-incidence datum. No coordinate is translated by the reader. `te_kind` is trusted explicit input metadata; accepting it is not an automatic cusp detector or a physical geometry qualification.


## Direct WP4 export interface

After the actual WP4 `src/cfd_sdf/topo2d/geometry.py` appeared, `_closed_from_surfaces`, `_element`, `build_scene` and `save_npz` were read. `load_geometry` now also accepts its JSON directly:

```json
{
  "schema": "topo2d-scene-v1",
  "configuration": "E2_sharp",
  "height_mm": 100.0,
  "ground_z_mm": 0.0,
  "normalizations": {"c1_mm": 223.4},
  "sharp_variant": {"mathematically_sharp": false},
  "gates": {"accepted": true},
  "elements": [
    {"name": "main", "polygon_mm": [["x", "z"]],
     "suction_mm": [["x", "z"]], "pressure_mm": [["x", "z"]]}
  ]
}
```

The coordinates above are placeholders illustrating field names, not a valid numerical geometry; actual input must contain the configuration's required element count and finite matching N×2 surfaces with N≥4. The adapter requires the exact source identity `polygon_mm == vstack(suction_mm[::-1], pressure_mm[1:], suction_mm[-1:])`, shared LE, and a finite TE cap whose endpoints differ. That source ordering proves the first and penultimate polygon points are the two cap endpoints. The source's explicit `mathematically_sharp:false` means every such element has `te_kind:blunt`, including the unthickened `_sharp` arm. It checks source gates are accepted, ground is zero and the common c1 is 223.4 mm (only floating-point unit-conversion roundoff allowed), then multiplies coordinates by 0.001. No reordering, interpolation or placement change occurs.

WP4 NPZ uses a Unicode scalar `scene_json` containing the complete JSON scene plus numeric arrays `polygon_0_mm`, `polygon_1_mm`, etc. Each duplicate array must exactly match its JSON polygon. Pickled metadata, non-scalar or bytes metadata, absent/mismatched polygon arrays, and ambiguous simultaneous `metadata_json`/`scene_json` are rejected. Hashing and loading both use the same raw file bytes.

`height_mm` becomes `nominal_ride_height_m`, carrying the explicit WP4 datum of the main-element minimum in the exported current contour; this is checked against that contour, not inferred as a published zero-incidence datum. All scene metadata except the coordinate-bearing elements is preserved as `source_scene_metadata` in the case manifest: sources and their verification status, gates, placement, normalizations, sharp arm meaning, thickness metadata and source grid remain visible. Each element's non-coordinate metadata is retained as `source_element_metadata`. Source provenance/gates are retained declarations, not a new physical qualification by the RANS reader. Its own contour/domain/disjointness checks still run after adaptation.

The new WP4 adapter tests first failed on unsupported JSON/NPZ. They then exposed metre-to-millimetre binary-roundoff in an exact reference comparison; a 1e-10 mm absolute serialization tolerance fixes that numeric representation issue while rejecting a changed chord. The complete format/dictionary subset after adaptation reports **30 passed, 3 deselected**; the parent runs final combined tests and actual WP4 geometry smoke. Tests use a clearly synthetic source-compatible E2-shaped record, not paper coordinate values.
