# SRCMAP-01: current source mapping is algorithmically nondeterministic

Terminal classification: **SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC**.
The frozen solver-free diagnosis is complete. Mapping reproducibility is not
established, and no production remedy or downstream continuation is authorized.
Issue: [#52](https://github.com/ramhachi/CFD_opt_sdf/issues/52).

## Authority and execution binding

- Integration parent: `b94eebacf7d1e4425e1b6303a5e34b4fe08b1863`.
- Freeze SHA-256: `45ce00295d4d3ca663c34b78f2c331ec3ac6e39f2819e41e5f22d8cf1dd81482`.
- Diagnostic source SHA-256: `dddb27521283b8fb1ef3a161c4e15919539d8b318c8a32411183992728a5610e`.
- Runner source SHA-256: `9d72e88d70705df9d0d43f0c077b1b984eb9499f50749a29a0e3dfe2add927ff`.
- Source STL SHA-256: `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`.
- Retained v17 state SHA-256: `02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`.
- Retained v17 NPZ SHA-256: `7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`.
- Retained v17 phi, little-endian Float32 C bytes:
  `f6419547c7b58991462a19f8116b819e7bbe60074fa524c01a51ef41cc0e3b1f`.

The source was frozen by these hashes before any mapping measurements; the
containing final Git commit is reported in the completion issue comment. The
independent pre-run PASS and root approval preceded the execution marker. The
campaign executed its 21 full-field jobs and one local-analysis process exactly
once, with exit code 0. No run was discarded or rerun to obtain agreement.
Every run passed structural runtime, imported-code, mesh-byte, coordinate and
job-condition checks. All 21 frozen file hashes were verified after measurement.
See [plan](prerun_plan.md), [freeze](prerun_freeze.json),
[approval](prerun_approval.json), [classification](classification.json), and
[exact campaign log](logs/campaign.log.gz).

## Environments and loaded source identity

Both environments use Python 3.12.13, macOS 26.3.1 arm64 and Apple M4. The second
environment represents project minimum dependencies; it does not reconstruct
the unknown Oct11 runtime. No production dependency declaration changed.

| Component | Current frozen environment | Minimum representative |
| --- | --- | --- |
| NumPy | 2.5.2 | 1.26.4 |
| SciPy | 1.18.1 | 1.11.4 |
| trimesh | 5.1.0 | 4.4.0 |
| rtree | 1.4.1 | 1.2.0 |
| libspatialindex | 2.1.0 | 1.9.3 |
| ray backend | trimesh.ray.ray_triangle.RayMeshIntersector | same |

`trimesh.load(source, force="mesh")` implicitly uses mesh processing. Both loaded
meshes have identical Float64 vertices `(1344,3)` and Int64 faces `(2684,3)`,
consistent winding, watertightness, one connected component and identical bounds.
Vertex C-byte SHA is `b2e014fce6ffe5e15e6c90e1605fe6c1578eacfc42266dd9eb962096e12ecaed`;
face C-byte SHA is `7b4be8455c6752ff66e1e59ba151c8aacd789c040d1e24fdfd145dc4b9b73296`.
Mesh preprocessing byte divergence was not observed. Imported module paths,
package locks/RECORD hashes, source and shared-library hashes, BLAS/build config,
compiler, locale, thread settings and entropy states are retained in
[current inventory](runtime_inventory.json) and
[minimum inventory](alternative_runtime_inventory.json). Only the two explicitly
frozen entropy-state fields are excluded from structural identity comparison.

Static interpretation correction: the frozen inventory's generic
`force_mesh_semantics` description names current `Scene.to_mesh()` behavior for
both versions. In 4.4.0, the corresponding Scene-only coercion is actually
`util.concatenate(loaded.dump())`. The frozen metadata is preserved unchanged;
[load-source clarification](load_semantics_analysis.json) records both exact
source excerpts and hashes. This prose-label error does not change the measured
loaded arrays or their per-environment identity checks.

## Strict field results

All counts below compare Float32 uint32 bytes with the unchanged registered
field. Every field also retains pre-cast Float64, endian-explicit C/F hashes,
sign/zero masks, exact comparisons and full difference maps. No allclose or
tolerance changes any classification.
Agreement of the two v16 controls and the finite zero-difference observations
in other stages applies only to those observed runs; it is not a proof of
universal determinism.

| Fixed diagnostic | Registered bit-difference counts |
| --- | --- |
| A: v17, five independent canonical runs | 4, 0, 4, 0, 0 |
| A: v16, two independent controls | 0, 0 |
| B: chunk sizes 385385, 50000, 100000, 200000, 368640, 131071 | 10, 4, 3, 0, 4, 2 |
| C: canonical, reverse, seed-20261012 permutation, restored to canonical | 0, 1, 1 |
| D1: direct project signed distance | 0 |
| D2: explicit closest-point + contains composition | 3930; 3495 nonzero and 435 signed-zero-only |
| D3: unsigned distance, compared with absolute registered phi | 0 |
| G: two independent minimum-environment canonical runs | 11, 11 |

The current canonical production identity group has seven observations
(A five, B200000, Ccanonical). Ten of its 21 pairs differ at four nonzero signs
in both Float32 and pre-cast Float64. The A1/A2 unsigned Float32 and Float64 bytes
are identical. The A1 changed indices are the historical three plus `(55,20,26)`.
Across the fixed current production chunk/order runs, up to ten registered
nonzero sign differences occur, with maximum `4.7706993910878737e-8 m`.
Additional nodes were retained by the predeclared whole-field analysis; the
local experiment remained restricted to the three frozen historical nodes.

Every current v17 diagnostic's unsigned Float64 field equals A1's unsigned
Float64 field bit for bit. All D1/D2/D3 unsigned Float32 fields equal the absolute
registered field; these comparisons are in raw `diagnostics/D_*.json` under
`unsigned_float32_vs_registered_magnitude`. D3's deliberately unsigned field
differs at 10262 bits if compared with a signed reference; that expected semantic
difference is not evidence of mapping nondeterminism.
D2 assigns every point's sign with contains, unlike D1's triangle-projection
and distance-threshold branches. It is a distinct diagnostic algorithm, not a
same-condition repeat. Its `fallback_invoked=false` metadata means the production
outer fallback was not invoked; D2 explicitly requested the composition itself.

Both minimum runs agree with each other, but current repeats are not stable.
Therefore these data do not satisfy the frozen ENVIRONMENT_DEPENDENT predicate
or localize the problem to an individual dependency. Their unsigned Float32
magnitudes also match the reference. Their unsigned Float64 magnitudes differ
from current at eight nodes, maximum `2.220446049250313e-16 m`; these numerical
bundle differences are distinct from the current run-to-run sign instability.
No claim that exact dependency pinning remedies the instability is made.

Chunk/order conditions each have one observation and leave production entropy
untouched. Their differing signs do not independently establish deterministic
chunk/order causality. See [repeatability](repeatability.json),
[chunk results](chunk_dependence.json), [ordering](ordering_dependence.json),
[paths](backend_path_comparison.json), [dependency comparison](dependency_sensitivity.json),
and [field differences](field_difference_summary.json).

## Measured mechanism and its limits

All production measurements, in both bundles, succeeded through the outer
`-trimesh.proximity.signed_distance` try path. No outer fallback or exception was
observed. The installed trimesh signed-distance implementation sends points to
ray containment when their nearest-triangle plane projection falls outside the
triangle; this route is not limited to near-edge points. In A1's first chunk,
168435 points enter ray containment and 19 require randomized retry. The ray
routine retries inconsistent forward/backward
parity with an entropy-derived direction. Actual draws, states, parent events,
recursive point subsets and directions are saved. Instrumentation does not seed
or consume extra production draws; the neutrality test verifies draw/state equality.
Logged utility-query counts cover recursive retries, not initial alias calls.
The saved A1 retry subset contains the A-group's four differing nodes and the
ten B385385 differing nodes. This is compatible with a shared retry mechanism,
while the controlled intervention below directly tests only the frozen three.

Exhaustive triangle-distance calculations for the three historical nodes found
equal minimum-distance triangle pairs on shared edges:

| Index | Unsigned distance (m) | Equal minimum triangles |
| --- | --- | --- |
| (28,24,19) | 1.2287812384712986e-8 | 908, 910 |
| (48,44,23) | 1.2287812223151806e-8 | 1657, 1671 |
| (56,44,27) | 1.3328003649948747e-8 | 2163, 2177 |

The nearest barycentric coordinate on the shared edge is exactly zero; vertices
are about 0.025 m away. The plane projections have small negative barycentric
coordinates beyond the installed `tol.merge=1e-8` test, consistent with the
observed ray route. Equal nearest primitives are present, but no change of
primitive identity was demonstrated as the run-to-run cause.

The three predeclared raw retry draws provide a direct intervention: draw
`(0.137,0.271,0.619)` makes all three project phi values positive and contains
False; draws `(0.731,0.419,0.173)` and `(0.317,0.823,0.457)` make all three negative
and contains True. Each draw was actually used once by direct signed distance
and once by contains. Magnitudes remain unchanged. The ray direction is the
unit vector of `draw - 0.5`; the raw vector is not itself the final direction.
This demonstrates current sign sensitivity to randomized ray retry at the
registered geometry. It does not independently qualify a physically correct
inside/outside label. Separate nominal local calls consume different entropy
draws; their labels must not be treated as paired same-direction path controls.
See [local geometry and intervention](problem_nodes.json).

## Historical reconstruction

The Oct11 successful completion is confirmed by the retained command/session
record. The Oct12 first strict failure and separate saved three-node diagnostic
are separate executions; the first failure's field and exact script hash were
not retained. Registered genesis and Oct12 recorded Python/NumPy/trimesh versions
match. Oct11 exact versions, imported module/backend identity, historical outer
fallback and inner ray/Rtree paths remain UNKNOWN. A shared venv symlink or old
package timestamps cannot establish historical equality.

The current mechanism can produce strict replay instability without a version
change or outer fallback. It has not been proven to be the actual path taken by
the historical Oct11/Oct12 runs. Historical implementation-path divergence is
not established. See [historical audit](historical_runtime_audit.json).

## Verification and stop

The independent pre-run review initially found blockers; they were corrected
before measurements, then reviewed PASS at the final freeze. The initial review
is retained in `reviews/`. The post-run verdict is recorded separately in
`independent_review_postrun.md`.

An independent saved-array checker imports no primary diagnostic helper and
performs no fresh geometry query. It verified 21 jobs, 315 frozen/field hash
checks, saved comparisons, Float64-to-Float32 casts and all 23 same-condition
pairs. See [checker result](independent_numeric_check.json).

Focused tests: 8 passed. Full baseline: 48 failed / 2176 passed / 23 skipped.
Full final: 48 failed / 2184 passed / 23 skipped. Failure-ID sets are identical:
new 0, resolved 0. This is not an all-pass suite. Compileall of src/scripts/tests
passed. Exact logs/JUnit gzip hashes are in [baseline validation](baseline_validation.json)
and [final validation](final_validation.json); final staged checks and evidence
integrity are recorded in `validation.json` and `SHA256SUMS`.

The old bridge manifest contains 35 unchanged current files and historical
hashes of two living documents, `phase_plan.md` and `problem_register_2026_09.md`.
Those two old hashes are verified against the integration parent, and their
current versions preserve the parent bytes as an exact prefix plus the SRCMAP
appendix. The old manifest itself and every file inside the old bridge directory
are unchanged. Current document hashes belong to this diagnosis's new manifest.
See [protected authority checks](protected_authority_check.json).

Original bridge audit remains **INCONCLUSIVE**. P22-v1, volume limits/rules,
retained references, accepted parent and all qualification flags are unchanged.
P22-v2 and its contract hash were not registered/generated. LOWDIM-04A was not
restarted or preregistered. CFD runs 0; Kaggle submissions 0. This diagnosis has
`selected_delta=null`, `shape_update_allowed=false`. No coefficient solve,
reinitialization, basis expansion, optimizer continuation, #27 reopen or #30
supersession occurred. #51 remains OPEN and blocked. Work stops at this result.
