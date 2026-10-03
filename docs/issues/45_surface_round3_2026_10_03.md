# #45 Stage V surface export — Round 3

## Evidence scope and authority

This is a solver-free export candidate screen, not XFID, solver qualification,
Stage V production adoption, or #29 closure. All qualification flags remain false.
Round 2 (`4dbcfb8` preregistration, `7351d41` results) remains a valid immutable
failure experiment. Authoritative integration branch is
`codex/kaggle-batch-migration`, starting at `7351d41e31ab8f4ba939e426831646af409ee9a7`.
Round 3 is integrated with `--no-ff`; literal main is unchanged.

## Step 0: synthetic definitions, not qualification

One component definition is fixed: exact-coordinate identity for audit adjacency,
edge-connected faces, retaining every face and joining every incidence of a
non-manifold edge. IDs follow minimum original face ID. Vertex-link singularities
are checked separately. Invalid topology gives orientation **N/A**, without flips.
The independent verifier imports neither extractor nor parent evaluation helpers.
Synthetic cases cover degenerate faces, multi-face edges, pinched vertices, void
boundaries and float32 serialization collapse; distance, normal correspondence,
volume and import independence are also checked before registration.

Floating-point grid-plane evaluation uses the same explicit node coordinates as
trilinear interpolation. Structural-zero witnesses require both value and weighted
roundoff envelope to be zero. This definition was fixed using synthetic cases only.

## Immutable preregistration

Machine-readable contract:
`docs/evidence/xfid45_surface_round3_2026_10_03/preregistration.json`.
It binds sources, runtime binaries/versions, original seven snapshot hashes and
unchanged D0/D1/D2 contracts, plus three freshly generated analytical heldouts.
The registration commit must be pushed and equal remote HEAD before target evaluation.

Uniform export-only virtual refinement uses `r = 1, 2, 4, 8`, float64 original
trilinear resampling and pinned scikit-image 0.25.2 Lewiner. The fixed positive
zero tie uses `tau = float32(h * 2^-20)` only on exact-zero virtual nodes in
extraction scratch; nonzero near-zero values and original GridSDF remain unchanged.
No adaptive candidate, new design state, repairs, or post-extraction vertex movement.
The backend's native float32 conversion and `1/(eps64 + abs(phi))` weighting are
bound by the runtime/source hashes; precision effects are classified separately.

Gate sequence: lineage; edge/vertex-link/closed/winding/duplicate/degenerate topology
in both double NPZ and float32 STL; component sidedness at `delta/h = .02,.05,.1`;
absolute sample geometry; baseline-to-six normal displacement fidelity; clearance.
Stable strict area majority is required for orientation. Only whole components may
flip; stored components must already point toward fluid. Solid/void contributions
are recorded and total signed volume must be positive.

Absolute and perturbation fidelity tolerances are analytically fixed at
`min(.1 epsilon, .02 h) = 0.5 mm` (`epsilon=5 mm`, `h=25 mm`). Absolute geometry
uses 10 degree-3 barycentric samples per triangle against the original trilinear
zero set with guarded floating-point lower/upper certificates. This is not a
continuous Hausdorff claim or fully directed-rounding interval arithmetic.
Fidelity uses fixed area-stratified baseline centroids, original SDF gradient rays,
certified source zero crossings and saved-mesh ray intersections; ambiguous
correspondence is unresolved. Heldouts have no FD direction and therefore no
paired fidelity gate by design. The six canonical pairs are mandatory.
The SDF volume quadrature ladder (16/32/64) is approximate, with no certified
quadrature error bound; source and mesh/STL changes are reported together.

Every input is evaluated at every r, including failures. Two extraction calls must
produce identical array hashes. Selection is the smallest r passing all ten
surface cases, six fidelity pairs and independent individual/aggregate/volume
agreement. All-fail does not alone prove intrinsic zero-set impossibility: refinement,
source singularity, backend precision and STL defects are separated.

## Relationship to #29 and next authority

This covers #29 GEOM-01's actual zero-level / Stage V STL-export measurement only.
Minimum feature, topology policy, manufacturing and overall #29 close conditions
are not claimed. Direct GridSDF Stage V is not selected in this round.
A passing candidate could be proposed for a separate production-export PR and a
user decision on formal #45 XFID resumption. No solver, Kaggle, formal XFID or
#46 campaign is launched by this round.

## Results

The registered evaluation is complete: **9/40 surface cases PASS and 31/40
FAIL**. Pass counts for `r=1,2,4,8` are respectively **0, 2, 3, 4 of 10**;
`selected_r` is null. All qualification flags remain false. The four independent
partitions are complete: **40/40 surface individual and aggregate gate maps,
24/24 pair Boolean gate/status maps, and all recorded volumes agree**. The
complete assembly checks exact coverage without using the empty-r candidate
fields in partition ledgers. See `independent_result.json` and partition bindings.
This is Boolean and volume agreement, not per-sample correspondence agreement.

The following table combines double NPZ and serialized float32 STL gates.
G means the sampled absolute-geometry certificate does not pass; O means
component sidedness does not pass; T means topology prerequisite failure.
Every canonical pair additionally has fidelity qualification N/A at every r.

| Input | r=1 | r=2 | r=4 | r=8 |
|---|---|---|---|---|
| canonical baseline | G/T | G | G | G |
| D0 −epsilon | G | G | G | PASS |
| D0 +epsilon | G | G | G | G |
| D1 −epsilon | G/O | G/O | G/O | G/O |
| D1 +epsilon | G | G | G | G |
| D2 −epsilon | G | G | G | G/O |
| D2 +epsilon | G/O | G/O | G/O | G/O |
| fresh eccentric void | G | PASS | PASS | PASS |
| fresh torus | G | G | PASS | PASS |
| fresh two ellipsoids | G | PASS | PASS | PASS |

Each storage type passes clearance in 40/40 cases and topology in 39/40.
Minimum clearance across both is `0.643158 m`, above the fixed `0.25 m` gate:
the sole failure is the `r=1` baseline, whose closed, edge-manifold mesh has one
bad vertex link. Its orientation result is therefore N/A and its signed mesh
volume (`-0.130389 m^3`) is not an admissible solid-volume result. Topology passes
for every case at `r>=2`; this shows that the registered extraction no longer has
that sampled topology defect at those refinements, but does not prove the original
trilinear zero set is nonsingular or that its full mathematical zero set is a
manifold. The `r=1` pinch is localized at original node `[60,16,30]`,
`phi=-6.280369727e-16 m`, a strictly negative near-zero value. Four y/z neighbors
are exact zero and receive the fixed positive scratch tie. Their edge crossings
are approximately `6.585e-10 m` from that pole, below backend voxel-coordinate
float32 half-ULP distances of `2.384e-8` to `4.768e-8 m`. The stored vertex link
has separate 4-edge and 5-edge cycles. This supports a mechanism involving tie
semantics, coordinate quantization and native coincident-vertex handling, rather
than proving an intrinsic singularity of the original zero set. Original baseline
has 498 exact-zero nodes, 2,588 nonzero near-zero nodes under the registered
diagnostic threshold, and no all-zero original cells. Mixed-sign node stars do
not establish mathematical regularity. See `auxiliary_orientation.json.gz` and
the per-case `defect_to_original_grid.json.gz` for values and source cells.

The absolute-geometry gate uses certified lower and upper bounds against 0.5 mm.
At `r=1`, 8/10 cases have a certified lower bound above the tolerance; at `r=2`,
7/10 do. Those cases are certified exceedances under the registered sampled
certificate. The remaining G failures at `r=1,2`, and all G failures at `r=4,8`,
are **not certified within tolerance** because the upper bound fails to establish
the limit; their lower bounds do not certify an exceedance. In particular, at
`r=4` the maximum lower bound is 0.378 mm, while the baseline upper bound is
12.132 mm; at `r=8` the maximum double lower bound is 0.097 mm and baseline's
double upper bound is 3.125 mm. Baseline float32 STL has upper bound 10.355 mm
and four unresolved sample certificates. These upper bounds are conservative root-witness bounds, not
measured or asserted actual distances. Thus higher-r G failures indicate
insufficient certification under the frozen method, not demonstrated geometric
error above 0.5 mm.

All 24 canonical normal-fidelity pairs are N/A for qualification because the
surface prerequisites fail; their correspondence calculations are diagnostics
only and report `within_limit=false`. The frozen root residual-filter omission
described below means matching Boolean FAIL outcomes do not establish numerical
agreement between implementations. Fidelity therefore supplies no qualified
perturbation comparison in this round.

For r=8 double surfaces, parent diagnostic maxima range from 35.55 to 64.45 mm
with 425–579 unresolved correspondences, while independent maxima range from
3.23 to 3.44 mm with 3–48 unresolved correspondences. Both report Boolean
`within_limit=false` at the fixed 0.5 mm threshold. These retained diagnostic
values are not upgraded to complete/unique-root physical displacement errors;
the source-root enumeration limitation remains unresolved.

For the original six perturbation shapes, component-wise SDF sidedness attributes
the negative signed-volume findings to inward winding of the main component. The
diagnostic correction reverses each affected component as a whole and changes face
winding only, with vertices fixed. Several cases still have small 8-face components
with unstable/ambiguous sidedness, so their stored orientation gate remains FAIL.
Their raw signed-volume `volume_class` labels are diagnostic tags and do not
establish physical solid/void classification when sidedness fails. Stable heldout
void boundaries have negative component volume toward fluid and positive total
solid volume, as required by the registered convention. `n dot grad(phi)` is
retained in the auxiliary audit and never substitutes for sidedness.
These whole-component flips are the registered processing step before storage;
no post-evaluation repair or extra orientation edit was applied. The `r=1`
baseline topology prerequisite failure likewise prevents any orientation flip there.

At `r=8`, the baseline-relative source SDF quadrature reports `+0.01404047216`
and `-0.01464441389 m^3` for D0− and D0+, while the corresponding mesh signed
volume differences are `+0.01403049906` and `-0.01471453081 m^3`. The source
quadrature ladder has no certified error bound, and the mesh differences use the
registered signed-volume convention; these are descriptive comparisons, not a
volume qualification gate or a claim of physical solid-volume agreement. More
generally, signed-volume differences against the `r=1` baseline must not be read
as solid-volume differences because that baseline failed its topology gate and
has negative signed volume.

The output JSON adapter was registered separately from the original scientific
preregistration: original registration `4a7b8da` fixes the extractor, evaluator,
verifier, criteria and runtime; adapter commit `3a32eee` only enables serialization
of NumPy integer diagnostics. The interrupted first attempt remains retained, and
the completed run checked its overlapping surface hashes and gates. No frozen
scientific source or threshold was changed.

**Disposition:** no refinement is selected. Production exporter and production
state remain unchanged; formal XFID and #46 remain prohibited. The evidence is
limited to the #29 actual zero-level / STL export gap and does not close #29
GEOM-01 overall. A new round would require an independently frozen and validated
root-enumeration method before any new target evaluation. All-r failure does not
distinguish insufficient refinement/certification from all possible representation
limits. A decision on reconsidering direct GridSDF Stage V is raised to the user;
it is not selected or implemented because cross-fidelity independence remains a
material consideration.

### Execution serialization addendum (criteria unchanged)

The first registered execution stopped after six r=1 perturbation cases because
NumPy integer node indices in baseline's diagnostic defect map were not accepted
by Python's default JSON encoder. The partial FAIL ledger and raw interruption
log are retained in `interrupted_attempt/`. The original registration and every
frozen scientific source remain byte-for-byte unchanged. A separately committed
and pushed output-only adapter adds exact `np.integer -> Python int` encoding;
it changes no extractor, measurement, verifier, threshold, gate or numeric value.
The complete run is restarted under the same registration, with prefix surface
hashes and individual gates checked against the interrupted attempt.

### Frozen correspondence numerical limitation (diagnostic, not a repair)

A post-registration read-only check found a source-root enumeration limitation.
For r=4 D0−, double correspondence sample 691, the original target trilinear
field has a sign crossing at `t=+0.00416667075198 m`. The mesh intersection is
`+0.00416669845581 m`. Including the baseline source-root offset, their diagnostic
displacement difference is approximately **33.8 nm**. The parent cubic root
candidate's residual is `3.62e-12 m`, just above its frozen `h*1e-10=2.5e-12 m`
filter; it drops the nearby root and selects another certified crossing at
`−0.0499999531 m`. The resulting frozen error near 54 mm is therefore not evidence
of an actual 54 mm displacement discrepancy at this sample.

The independent verifier accepts the nearby root using its sign certificate.
Its r=4 D0− maximum error/unresolved counts differ from the parent, while both
registered Boolean fidelity gates remain FAIL. **Individual/aggregate gate
agreement must not be described as quantitative per-sample correspondence
agreement.** A local crossing certificate does not establish complete root
enumeration or nearest-root uniqueness. Sources, thresholds and original results
remain unchanged; `ray_root_omission_diagnostic.json` and its separate reproduction
script are auxiliary evidence, not replacement criteria or a qualified result.
A future round must establish robust root enumeration/completeness with synthetic
near-linear cubics before registering and evaluating target shapes.

## Stored evidence and software validation

The bundle under `docs/evidence/xfid45_surface_round3_2026_10_03/` retains the
scientific preregistration, pinned exporter/evaluator/verifier and runtime hashes,
all original and fresh-heldout snapshot hashes, all 40 double NPZ and compressed
raw float32 STL surfaces, repeat-extraction hashes, defect-to-original-grid maps,
component sidedness votes, sampled distance certificates and normal correspondence
records. Parent results are in `result.json`; independent per-r reports and their
complete assembly are retained separately. Auxiliary diagnostics are explicitly
post-registration and cannot replace frozen gate results.
`bundle_manifest.json` binds the complete artifact set, final source/runtime/input
identity checks and report documents. Production `src/`, previous Round 2 evidence
and previous UNRESOLVED geometry preflight evidence remain unchanged.

Focused tests: **16 passed**. `python -m compileall src tests`, Ruff checks and
format checks on all Round 3 scripts/tests, and `git diff --check` pass. The full
frozen suite reports **36 failed, 1,371 passed, 5 skipped**. Against the pinned
37-ID baseline, there are **zero new failure IDs** and one absent baseline ID;
this does not claim a green full suite. See `validation/failure_ID_comparison.json`
for exact IDs and the retained logs for fixture failures. The earlier pre-freeze
development-suite log is also retained: concurrent synthetic-only source edits
caused an old in-memory helper-signature mismatch. The subsequent frozen run
has no new failures; no scientific source was changed after target evaluation.
