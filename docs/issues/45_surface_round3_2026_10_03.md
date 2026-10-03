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

Pending: evaluation starts only after the immutable registration commit is pushed.

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
