# #45 canonical zero-level surface export qualification (2026-10-03)

## Decision

Status: **UNRESOLVED; the preregistered geometry-preserving candidate fails**.
No solver or formal XFID measurement was started. The production exporter was
not changed to adopt the candidate. Do not resume formal XFID from this round,
and do not start #46 FD-08. Every qualification flag remains false.

The fixed sequence preserved every unique input coordinate inside the
canonicalizer and kept the positive-area triangle surface exactly unchanged
(surface Hausdorff distance `0 m`) in all seven cases. D0 ±ε passed the
manifold/orientation/volume/clearance gates. The baseline retained 12
non-manifold edges and one roundoff-ambiguous face. D1 and D2 facewise local
orientation created winding conflicts, so their signed enclosed volume is not
defined for the candidate meshes. Five of seven cases fail.

## Registration and scope

The immutable criteria were committed and pushed before any target-case
evaluation: commit `b2d170d` on
`exp/issue-45-export-qualification-2026-10-03`, based on authoritative
`codex/kaggle-batch-migration` HEAD
`8959f7dcc9427d2234b8faf6313a5050735bade3`. Criteria:
[`xfid45_surface_export_round_2026_10_03_prereg.json`](../evidence/xfid45_surface_export_round_2026_10_03_prereg.json),
SHA-256 `96cece05ee24a2c63f46c27cbbff8b493b71c9340a8e9d21d0a04ac55393a6cd`.
It binds the canonical v17 state, the six frozen D0/D1/D2 `±0.005 m` snapshots
and direction hashes, prior PLY/STL hashes, candidate/evaluator/verifier
sources, and the Python 3.12.13, NumPy 2.5.2, SciPy 1.18.1, PyVista 0.48.4,
VTK 9.6.2, and trimesh 5.1.0 runtime.

The registered sequence was: exact coordinate merge; exact duplicate triangle
removal; repeated-index and exact zero-area triangle removal; then facewise
orientation by the local trilinear `+grad(phi)` at each triangle centroid, with
the fixed float64 roundoff tolerance. No signed-volume inversion, iso-value
change, vertex movement, smoothing, hole fill, or repair was used. This
sequence was not changed after observing results.

The evidence applies only to actual canonical v17 zero-level / Stage V STL
export integrity under this candidate. It does not qualify #29 minimum feature,
topology policy, manufacturing, or any other #29 close condition. The earlier
UNRESOLVED #45 preflight evidence remains immutable.

## Orientation findings

The canonical convention is `phi < 0` solid, `phi > 0` fluid, so outward solid
normal is `+grad(phi)`. All six raw perturbation meshes were watertight and
winding-consistent, but their signed volume was negative. The local normal audit
shows why a single `volume < 0` inversion is insufficient:

| Case | Raw `n·grad(phi)` signs (− / + / ambiguous) | Faces flipped by registered rule | Candidate same-direction edge conflicts | Candidate signed volume (m³) | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| D0 −ε | 11,056 / 0 / 0 | 11,056 | 0 | +0.1453838150 | PASS |
| D0 +ε | 9,928 / 0 / 0 | 9,928 | 0 | +0.1108300099 | PASS |
| D1 −ε | 13,195 / 81 / 0 | 13,195 | 191 | undefined; winding inconsistent | FAIL |
| D1 +ε | 13,337 / 95 / 0 | 13,337 | 211 | undefined; winding inconsistent | FAIL |
| D2 −ε | 13,347 / 101 / 0 | 13,347 | 229 | undefined; winding inconsistent | FAIL |
| D2 +ε | 13,392 / 108 / 0 | 13,392 | 248 | undefined; winding inconsistent | FAIL |

For D0 both meshes had every raw triangle normal opposed to the local SDF
gradient, and flipping every face produced positive volume without changing
connectivity. For D1/D2, 81–108 raw faces per case already had positive local
dot while the rest were negative. Orienting every face to `+grad(phi)` makes
all dots positive but creates 191–248 same-direction shared edges. A global
volume-based flip would instead leave those locally positive faces pointing
against `+grad(phi)`. The fixed candidate cannot satisfy both local orientation
and coherent winding on those four surfaces.

The component audit uses exact-coordinate edge connectivity. Each D0 surface
has one component and all of its raw face dots are negative, so that component
can be flipped deterministically to satisfy every local normal. D1− and D1+
each have two components; both components in each case contain faces with
positive and negative raw dots (respectively `13,182−/78+` and `13−/3+`, then
`13,330−/94+` and `7−/1+`). D2− has two mixed components and two all-negative
components; D2+ has four mixed and two all-negative components. Thus a single
orientation choice per component cannot align every face with `+grad(phi)` on
any D1/D2 mesh. The post-result source-cell audit also compared the VTK
contouring source cell against the preregistered half-open-cell gradient rule:
all six cases had zero changed face classifications. The conflict is not
caused by that cell-selection choice. Full per-component counts are in
[`orientation_source_cell_semantics.json`](../evidence/xfid45_surface_export_round_2026_10_03/diagnostics/orientation_source_cell_semantics.json).

The baseline raw mesh had 9,600 negative, 263 positive, and 1,127 ambiguous raw
face-dot records. The ambiguous raw faces are dominated by collapsed triangles;
after the registered cleanup one face remains ambiguous (candidate face 4,224,
source triangle 4,712).

## Baseline defect localization

The prior audit's 712 non-manifold-edge count is reproduced only with the same
Trimesh default vertex merge used by that audit (8-decimal coordinate rounding).
The candidate's required exact-coordinate merge yields 666 such edges. The
rounded diagnostic coalesces 39 additional near-coincident vertices
(4,937 exact unique STL coordinates versus 4,898 rounded coordinates), which
changes the count from 666 to 712; no coordinate was moved in the candidate.
The same reconciliation finds 555 two-face winding-conflict edges under the
prior audit's merge and 524 under exact merge. There are 4 duplicate faces.

Across the prior audit's 712 edge defects, 555 winding-conflict edges, and 4
duplicate faces (categories can overlap), 232 entities (18.25%) have an
involved contour cell with an exact `phi == 0` node. The four duplicate faces
all touch exact-zero cells; 183/712 non-manifold edges and 45/555 winding
conflicts do. Among 2,522 distinct source triangles involved in any of these
defects, 643 (25.50%) touch an exact-zero node. Canonical v17 contains 498
exact-zero GridSDF nodes.

After exact coordinate merge and duplicate removal, the fixed candidate finds
1,126 repeated-index triangles and no additional zero-area/non-repeated
triangles. All 1,126 are degenerate (zero area); 39/1,126 touch an exact-zero
cell, while 1,123 have at least one vertex exactly at a GridSDF node. The
minimum absolute corner-`phi` quantiles over their source cells range from 0
at the minimum to `8.43e-9` at the maximum (median `7.45e-10`). This strongly
supports zero-neighborhood contour degeneracy, including non-exact near-zero
values. It does not prove that every original edge defect is only a VTK tie
artifact: exact-zero contact is absent for most defect entities, and 12
non-manifold edges remain after the fixed cleanup. The underlying baseline
zero-set's manifoldness is therefore still unresolved.

The exact-coordinate candidate removes the 4 duplicate faces and 1,126
repeated-index triangles, taking the PLY triangle count from 10,990 to 9,860.
It reduces the exact-merge non-manifold count from 666 to 12, but remains
non-watertight. The remaining 12 edges and the ambiguous face are mapped to
source triangles/cells. The registered geometry sequence therefore does not
repair the baseline.

## Seven-case geometry results

Vertex counts and topology values below use exact coincident-coordinate merge
for inspection. Area is the sum of represented positive-area triangles, with
the baseline raw value including duplicate-face area. Candidate signed volume
is reported only for closed, consistently wound meshes.

| Case | Unique vertices raw → Stage V STL | Faces raw → candidate | Edge components raw → candidate | Euler χ raw → candidate | Area (m²) raw → candidate | Signed volume (m³) raw → candidate | Non-manifold edges raw → candidate | Clearance (m) | Candidate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 4,938 → 4,937 | 10,990 → 9,860 | 4 → 4 | 611 → 6 | 3.044783 → 3.043533 | undefined → undefined | 666 → 12 | 0.650000 | FAIL |
| D0 −ε | 5,530 → 5,530 | 11,056 → 11,056 | 1 → 1 | 2 → 2 | 3.125013 → 3.125013 | −0.145384 → +0.145384 | 0 → 0 | 0.645833 | PASS |
| D0 +ε | 4,966 → 4,966 | 9,928 → 9,928 | 1 → 1 | 2 → 2 | 2.899622 → 2.899622 | −0.110830 → +0.110830 | 0 → 0 | 0.654167 | PASS |
| D1 −ε | 6,640 → 6,640 | 13,276 → 13,276 | 2 → 2 | 2 → 2 | 3.101248 → 3.101248 | −0.127765 → undefined | 0 → 0 | 0.645833 | FAIL |
| D1 +ε | 6,712 → 6,712 | 13,432 → 13,432 | 2 → 2 | −4 → −4 | 3.130460 → 3.130460 | −0.128476 → undefined | 0 → 0 | 0.646397 | FAIL |
| D2 −ε | 6,724 → 6,724 | 13,448 → 13,448 | 4 → 4 | 0 → 0 | 3.117577 → 3.117577 | −0.128247 → undefined | 0 → 0 | 0.646600 | FAIL |
| D2 +ε | 6,756 → 6,756 | 13,500 → 13,500 | 6 → 6 | 6 → 6 | 3.128586 → 3.128586 | −0.128095 → undefined | 0 → 0 | 0.646420 | FAIL |

For every case the canonicalizer's pre-serialization unique coordinate set and
bounds are exactly unchanged, and the positive-area triangle support is
identical, giving exact vertex-set and surface Hausdorff distances of `0 m` at
that stage. The Stage V STL round trip drops one baseline coordinate used only
by removed degenerate faces (4,938 to 4,937 unique coordinates; vertex-set
Hausdorff distance `0.025 m`); the positive-area surface remains identical
(surface Hausdorff distance `0 m`). No retained vertex was moved. Every case
meets the Stage V clearance minimum `0.25 m`.

The explicit topology gates are: the candidate baseline is non-watertight and
has 12 non-manifold edges; D0 ±ε are watertight and winding-consistent with no
non-manifold or duplicate faces; D1/D2 remain watertight with zero incidence
defects and zero duplicate faces, but their candidate winding is inconsistent.
Only D0 ±ε also have defined positive signed/unsigned enclosed volume. All
seven clearances pass. For closed consistently oriented cases, unsigned volume
is the absolute signed volume; raw and candidate values, bounds, unique vertex
coordinate hashes, topology, area, and Hausdorff results are recorded per case
in `result.json` and independently recomputed.

## Independent recomputation and validation

The independent verifier does not import the canonicalizer. It independently
re-contours all seven snapshots at exactly zero, compares triangle-coordinate
multisets with the frozen raw PLYs, checks PLY/STL identity, and recomputes
topology, volume, clearance, Hausdorff metrics, and local orientation. It
agrees: D0 ±ε pass; baseline and D1/D2 fail. Full per-case results, raw and
candidate surface hashes, compressed per-face orientation records, 712-edge
localization, residual-edge localization, and independent output are retained
under [`../evidence/xfid45_surface_export_round_2026_10_03/`](../evidence/xfid45_surface_export_round_2026_10_03/).
The final validation record is
[`validation.json`](../evidence/xfid45_surface_export_round_2026_10_03/validation/validation.json).
Its `SHA256SUMS` manifest covers all 46 files in the round evidence directory
and has SHA-256
`362ca3d17dfe5c99611b10d52b5e6205c474890594b0b93e12059b86ff2553f3`.

The focused canonicalization tests pass (3 tests), and compileall over `src`
and `tests` passes. With the two missing ignored fixtures restored and their
hashes checked, full pytest reports 36 failed, 1,343 passed, and 5 skipped.
Exact node-ID comparison against the pinned 37-ID baseline finds zero new
failures and one baseline failure absent in this run. The earlier run before
the v17 ignored state fixture was restored is retained separately and records
the transient extra missing-fixture failure. Both logs and the final ID
comparison are in the evidence directory's `validation/` subdirectory.

## Follow-on design boundary

This failure is diagnostic only. No new exporter was adopted. If the
geometry-preserving sequence is insufficient, the bounded next design review
can compare (a) deterministic marching tetrahedra with an explicit tetrahedral
decomposition, (b) a VTK contouring variant with specified exact-zero tie
semantics, and (c) deterministic symbolic treatment of exact-zero GridSDF
nodes. This round did not implement or evaluate those methods. Any method that
changes the trilinear zero-level surface must quantify the displacement and
state exactly which GridSDF interpolation defines its geometry; that change
requires a separate decision before qualification. No `0 ± ε` iso-value,
smoothing, moving-vertex repair, hole filling, or manual edits are authorized
by this result.

## Gate and issue relationship

The new export/input round does **not** pass all seven cases, so #45 formal
XFID cannot resume. The #45 force-response verdict remains `UNRESOLVED`; no
direction, epsilon, GridSDF, or previous evidence was changed. #46 remains
blocked. No qualification flag is raised.

This is a direct update to #29 GEOM-01's formerly unmeasured actual zero-level /
Stage V STL export component. The candidate failed and the existing production
exporter remains unqualified. #29 remains open; this result does not satisfy its
minimum-feature, topology-policy, or manufacturing close conditions.
