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

## Reproduction

Use the recorded Python 3.12 runtime and its recorded NumPy/SciPy/PyVista/VTK/
trimesh versions. Install the experiment dependency in an ignored task folder:

```sh
uv pip install --python <recorded-python> \
  --target work/xfid45_surface_round2_deps --no-deps \
  scikit-image==0.25.2 lazy-loader==0.4
```

Set `PYTHONPATH=work/xfid45_surface_round2_deps:src:scripts`. Synthetic tests
work without this optional dependency by skipping the two B cases if the
pinned version is unavailable. The recorded qualification screen includes B.
`audit_xfid45_surface_round2.py` deliberately refuses changed registered
sources/inputs/runtime binaries or an unpushed registration HEAD. Its first
execution must be at the registration commit. Existing saved surfaces can be
recomputed separately with `verify_xfid45_surface_round2.py`; that script
performs no extraction. The post-screen representation diagnostic likewise
reads only saved arrays and does not modify the criteria or candidates.

## Step 2: frozen screen result

The registration/source commit `4dbcfb8d5f71d73324f30c9be16d39f68390a552`
was pushed and remote-HEAD matched **before** target evaluation. Registration
SHA-256 is `981eddecd957817fc40fc0a1b6460a4de6cd4527ba05cee5677f3ebbfdf316a3`.
The evaluator verified every registered input, source and runtime file hash
before extracting any target. All three candidates were executed twice on
all 10 inputs; all raw vertex/face array hashes repeat exactly. Original phi
is unchanged in every extraction. **No candidate is selected.**

| Input | A | B | C |
|---|---|---|---|
| canonical v17 baseline | FAIL | FAIL | FAIL |
| D0 minus | FAIL | FAIL | FAIL |
| D0 plus | FAIL | FAIL | FAIL |
| D1 minus | FAIL | FAIL | FAIL |
| D1 plus | FAIL | FAIL | FAIL |
| D2 minus | FAIL | FAIL | FAIL |
| D2 plus | FAIL | FAIL | FAIL |
| held-out combined minus | FAIL | FAIL | FAIL |
| held-out combined plus | FAIL | FAIL | FAIL |
| held-out analytic shell | FAIL | FAIL | FAIL |

### Identity and topology findings

Every canonical/frozen-direction case has sampled **Lipschitz lower bounds**
above 0.5 mm, so rejection is supported by a bound, not just failure of the
witness search. Maximum lower bounds across the seven inputs are:

| Candidate | Smallest case maximum lower bound | Largest case maximum lower bound |
|---|---:|---:|
| A | 3.0318 mm | 5.3458 mm |
| B | 3.0318 mm | 5.3458 mm |
| C | 4.7755 mm | 5.5083 mm |

These bounds measure distance from **triangle samples** to the original
trilinear zero set. They are neither a vertex-motion measure nor an exact
nearest-distance/Hausdorff value. The corresponding finite witness upper
bounds are also retained, with unresolved samples explicitly counted. In the
analytic shell held-out, A/B have upper bounds about 0.515 mm and lower bounds
about 0.300 mm: their identity is **not certified by the registered method**,
not proved to exceed 0.5 mm. C's shell lower bound is 0.6557 mm and does prove
exceedance.

A keeps the original contour coordinates. Whole-component flips preserve
winding in the six perturbations, but do not cure baseline's 12 bad edges and
11 bad vertex links. D2's small ambiguous components remain an orientation
failure. Even D0/D1's topology and orientation successes do not establish
original-trilinear surface identity.

B baseline has closed edges, no duplicate/zero-area triangles, but **one
non-manifold vertex link**. At approximately `(0.5, -0.4, 0.15) m`, its link
has two disjoint cycles. Localization records nine incident faces and the
containing cell `[60,16,30]`, whose phi values include exact zeros and
`-6.28e-16 m`. Edge incidence alone would miss this defect. This numerical
and contouring evidence does not prove that the original mathematical zero
set is manifold, nor that every old defect is solely a VTK bug.

C's six perturbations pass double-coordinate edge/link gates and have no
native duplicate or zero-area faces. Their minimum positive triangle area is
only `7.1054e-17 m2`. float32 STL merges 257 coordinate sets per perturbation,
creating 321 non-manifold edges, 318 invalid vertex links, 16 duplicate faces
and 580 zero-area triangles in each. These are measured serialization
failures, despite combinatorial edge identities. C baseline already fails
before serialization: native-ID edge incidence is bad at 1,380 edges;
exact double-coordinate merging yields 896 bad edges, 874 bad links,
114 duplicate faces and 1,512 zero-area triangles. Degenerate-coordinate
rounding and the registered implementation's polygon ordering limit what
can be inferred from a construction argument. No guarantee is claimed and
no corrective cleanup is added after observing these results.

C uses a piecewise-affine tetrahedral field, whereas the identity reference
is the original trilinear field. Its measured discrepancy, STL failures and
baseline implementation/numerical defects reject C. They do not authorize a
change of canonical geometry semantics. The finite zero tie does not by
itself explain the failures on nonzero perturbation inputs.

All 30 outputs have positive total signed volume and satisfy clearance;
the smallest measured clearance is `0.6061457 m`. These gates alone do not
make any surface acceptable. Detailed raw/serialized statistics, samples,
orientation votes, source-edge/tetra provenance and hashes are in the result
and per-case files. Extraction audits are losslessly gzip archived; the
archive record includes uncompressed-content hashes and checked decompression
identity. Prior-round evidence remains immutable.

### Independent recomputation and its discrepancies

The registered independent verifier completed all 30 cases, imports no
extractor or measurement helper, and agrees with the **overall FAIL verdict
on all 30**. It agrees on every individual geometry gate in **24/30**, so the
registered all-case independent-agreement requirement also fails.

Six differences are retained without changing either registered program:

- A baseline: the evaluator joins all faces sharing an edge, including
  edges with more than two faces; the verifier's face-adjacency graph separates
  such faces. Their component-sidedness gate differs on this already
  non-manifold surface.
- C D0 minus/plus, both combined held-outs, and baseline: the evaluator
  removes zero-area faces before its sidedness component census; the verifier
  retains their components and reports zero-total-area components ambiguous.
  The verifier rejects orientation where the evaluator reports a pass.

Every difference is limited to orientation gates; independently measured
closed-edge/vertex-link, duplicates, zero-area faces, area/volume/clearance and
identity gate verdicts agree. Raw maximum witness upper distances need not be
identical because the two projection methods find different valid witnesses.
The discrepancy report is an **evaluation-harness limitation**, not a new
successful exporter or a reason to relax the criteria. Any future round must
align this component-definition contract with synthetic regressions before
registration. Registered evidence here is unchanged and all six cases fail
other geometry gates regardless.

### Validation and status

Focused tests: **15 passed** (12 successor tests plus 3 prior canonicalization
tests). `python -m compileall src tests`, script compilation, ruff and
`git diff --check` pass. Full `pytest -q`: **36 failed, 1,355 passed, 5 skipped**.
The exact 36 failure IDs equal the predecessor's fixture-restored run. Against
the pinned 37-ID baseline: **zero new IDs**, one baseline ID absent (the
canonical objective sign test). Existing failures are retained in the full
log and failure-ID record; this is not a claim that the full suite is green.

**#45 remains UNRESOLVED. Formal XFID cannot resume from this screen.** No
solver/Kaggle/formal XFID/#46 ran, and all qualification flags remain false.
A/B/C all fail, so the requested escalation is to **reconsider a GridSDF-direct
Stage V representation as a separate design decision**, including the
independence of the Stage V geometry/solver semantics. No direct-input solver
path is implemented or run here. A new surface method, additional refinement,
changed geometry semantics or production exporter would need a separately
reviewed task/PR and preregistration.

This evidence is cross-referenced to #29's actual zero-level / Stage V STL
export gap only; #29's other close conditions remain unmeasured here.
