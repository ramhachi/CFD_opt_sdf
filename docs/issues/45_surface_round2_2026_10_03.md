# #45 successor zero-level surface export round 2 (2026-10-03)

## Scope and authority

This is a **solver-free geometry candidate screen** from authoritative
`codex/kaggle-batch-migration` at
`c89bfa209fe3c3c4d9a28d481352e9fa5ed93c4f`. The immutable predecessor evidence
remains unchanged. No solver, Kaggle, formal XFID, or #46 campaign is run.
All qualification flags remain false. Implementation uses a Codex parent and
one explicitly requested luna worker. Production exporter changes require a
separate PR.

## Step 0: diagnostic only

Evidence: `docs/evidence/xfid45_surface_round2_2026_10_03/step0.json` and
`baseline_residual12_localization.json`. The sidedness rule and delta ladder
were defined before Step 0; no threshold was fitted to these observations.
A component is orientable only if strictly more than half its positive face
area votes for the same polarity at every `delta/h = 0.02, 0.05, 0.1`.
Sidedness uses original trilinear phi at both sides of triangle centroids.
Gradient dots are auxiliary. Signed volume never chooses the flip.

All six main components vote inward at all three deltas. D1-minus also has a
resolved void boundary; D1-plus has a separate resolved solid component.
D2-minus has two small unresolved components (one delta-dependent), and
D2-plus has two unresolved 8-face components. These observations do not
justify a component-volume inversion rule or an adjusted voting threshold.
Solid/void labels are signed-volume diagnostics after sidedness orientation,
not independently proved containment/nesting classifications.

All 12 remaining baseline non-manifold edges touch exact-zero source cells.
The mapping retains each original source triangle, cell, node index, phi
value, area and coincident-coordinate set. Near-zero is analytically defined
as `h * eps(float32)`, not a threshold inferred from the defects. This shows
where contour ambiguity is concentrated, without proving that the original
trilinear zero set itself is a manifold.

For D0, `2 epsilon A = 0.0304353340 m3` and
`2 epsilon integral(1/|grad phi|) dA = 0.0377634585 m3` on unique positive-area
baseline triangles with centroid quadrature. The raw mesh unsigned-volume
difference is `0.0345538051 m3`. Original global `phi +/- epsilon` sublevel
volume and frozen D0 snapshot volume are different comparators: D0's frozen
mask/direction contract is not a global field shift. At the fixed 64x64 xy
midpoint rule with exact per-cell linear-z fraction, their differences are
`0.0378460502` and `0.0288304035 m3`, respectively. The 4/8/16/32/64 ladder
has material residual variation; these are numerical diagnostics, not exact
volumes or a qualification of the coarea approximation. Finite epsilon,
non-unit SDF gradients, mask-limited directions and planar contour
representation all matter; the comparisons do not isolate one cause alone.

## Step 1: immutable preregistration

`docs/evidence/xfid45_surface_round2_2026_10_03/preregistration.json` binds
canonical v17, all six unchanged snapshots/directions, three held-out inputs,
source hashes, pinned runtime and the entire processing sequence. The held-outs
are a normalized frozen D1+D2 combination at both epsilon signs and an
analytic off-center spherical shell, all unused in Step 0 surface diagnostics.
They are stress inputs and do not replace the formal D0/D1/D2 contract.

A: current VTK contour, fixed exact cleanup, whole-component sidedness.
B: scikit-image 0.25.2 Lewiner contour, fixed positive symbolic-zero tie,
whole-component sidedness.
C: fixed Kuhn-6 tetrahedra, combinatorial node-edge IDs, affine tetra native
winding, whole-component sidedness.

The predecessor symbolic tie ban is explicitly lifted for this successor.
B/C realize it with finite `float32(h * 2^-20)` at exact zeros only. This is
not a mathematical infinitesimal; immutable original phi is the identity
reference. No post-extraction vertex motion, smoothing, filling or repair is
allowed. Manifoldness is expected by construction, not asserted as guaranteed.

The displacement limit is fixed analytically at
`min(0.1 epsilon, 0.02 h) = 0.0005 m`. Every triangle's 10 degree-3 barycentric
samples is checked against original trilinear zero witnesses, for both double
arrays and float32 STL. Feasible witness distance is an upper bound; a global
Lipschitz bound supplies a lower bound. A lower bound above the limit proves
representation disagreement. An upper bound above the limit without such a
lower bound only means identity cannot be certified by this fixed method.
This is a sampled certificate, **not a continuous Hausdorff guarantee**.

Every candidate is evaluated on all 10 inputs, with all results retained;
selection priority A then B then C. C additionally needs explicit assessment
of piecewise-affine versus trilinear semantics. The independent verifier
imports neither extractor nor evaluator/measurement helpers and consumes
stored arrays and STL. Every input must meet closed edge and vertex-link
manifoldness, winding, duplicate/degenerate, positive total volume, 0.25 m
clearance, stable sidedness, identity, determinism and agreement gates.

At registration this round is **PREREGISTERED_NOT_EVALUATED**. Evaluation
begins only after this criteria/source commit is pushed.

## #29 GEOM-01 relationship

This round directly measures the actual zero-level / Stage V STL export gap
in [#29](https://github.com/ramhachi/CFD_opt_sdf/issues/29), cross-referenced
from [#45](https://github.com/ramhachi/CFD_opt_sdf/issues/45). It establishes
no minimum-feature, topology-policy or manufacturing close condition for
#29. A geometry pass would only permit considering return to #45; this task
does not execute formal XFID and never advances automatically to #46.
