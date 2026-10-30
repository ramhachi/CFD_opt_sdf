# SRCMAP-02 preregistered deterministic signer qualification

Date: 2026-10-13 Asia/Tokyo. Issue: #53.
Integration parent: `e621b585531f7fe3f44d0a8683cec1923008de56`.
Evidence class: solver-free finite-campaign geometry/mapping qualification only.

## Immutable authority and question

SRCMAP-01 (#52), diagnostic commit `0cd941badb45770c518809a95a535c2d06c1f4c5`,
freeze `45ce00295d4d3ca663c34b78f2c331ec3ac6e39f2819e41e5f22d8cf1dd81482`,
established current algorithmic nondeterminism without qualifying a remedy.
Its 130-entry manifest was reverified at this parent. All historical evidence,
registered v16/v17 fields, production source and dependencies remain immutable.
Source STL SHA256 is `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`.
No objective or acceptance condition matches a candidate to an old field hash.

## Frozen methods

Preferred Candidate A: official libigl `SIGNED_DISTANCE_TYPE_PSEUDONORMAL`.
Independent control B: official libigl `SIGNED_DISTANCE_TYPE_WINDING_NUMBER`.
Libigl exact version 2.6.3; wheel, binary, imported module and RECORD identities
are recorded in wheel_identity.json and candidate runtime inventories.
The same wheel is isolated at `/private/tmp/srcmap02-libigl`; it is not added
to production dependencies or the shared production environment.

Explicit unsigned distance uses `trimesh.proximity.closest_point(mesh, points)`.
This is the SRCMAP-01 D_unsigned path, whose complete current-environment
unsigned Float64 field matched every current v17 job. No random signed-distance
call or abs(signed_distance) is permitted in the new candidate computation.
Libigl returns a signed scalar; only its sign is used. In particular the winding
scalar may equal `(1 - 2*w)*distance`, and its magnitude is not the chosen distance.
Combine sign with the independent unsigned magnitude: negative inside, positive
outside. There is no epsilon, clipping, allclose, old-hash adjustment, random retry,
or geometry repair. Analytic fixtures verify the convention before target queries.

## Zero and invalid-data semantics

Finite unsigned distances must be nonnegative; negative zero is rejected.
Bitwise +0 unsigned yields bitwise +0 combined phi, independent of signer zero sign.
Signer scalar zero with strictly positive unsigned distance is a semantic blocker,
not a tie to be assigned after seeing results. Nonfinite values are blockers.
Both Float64 and final Float32 zero values are normalized to +0, including any
Float32 cast underflow; counts are recorded. Project hard center zero is fluid.
Actual mesh bytes, winding consistency, closure and loaded topology are recorded;
watertight edge incidence alone does not establish absence of self-intersections.
Static topology checks in mesh_prerequisites.json record edge and vertex manifoldness,
consistent winding and positive signed volume. Self-intersections are not tested;
global outward orientation is supported conditional on a non-self-intersecting embedding.
A/B are independent sign criteria within one library, not independent mesh certifications.

## Fixed campaign and execution order

The frozen source contains the complete fixture coordinates and analytic expected
labels. Four fixture families: triangulated sphere, axis-aligned box, rotated box,
and tetrahedron, with inside/outside and face/edge/vertex-near observations.
Shared smooth-sphere/polyhedron observations use radii guaranteed interior to both
or exterior to both, avoiding the approximation shell. The separate sphere-family
face/edge/vertex-near observations are tests of the inscribed convex polyhedron,
whose expected signs follow its face half-spaces, not the continuous sphere.
Exact facet/edge/vertex surface cases likewise refer to the actual triangle mesh.
Formal fixtures run first in an independent process before ANY target distance
or sign query. If fixtures fail, stop fail-closed; do not repair after measuring
canonical geometry. Pre-freeze development tests are limited to fixtures/mocks.

After the analytic gate, 32 independent full-field processes execute once:

- B repeat: current v17, five per candidate, canonical order, chunk 200000 (10 jobs).
- C invariance: current v17, complete product of chunks 385385/50000/200000 and
  canonical/reverse/permuted order for each candidate (18 jobs).
- D environment: minimum representative v17, canonical, chunk 200000, one per
  candidate (2 jobs), compared with current B first runs.
- G representation: current v16, canonical, chunk 200000, one per candidate (2 jobs).

Permutation seed is 20261013. Restore the full permutation to canonical order
before hashes and comparisons. Python hash seed is 0. Candidate selection,
chunk/order matrix, counts, environments and predicates cannot change after freeze.
A durable exclusive execution marker and exclusive output writes prohibit reruns.
Failed/partial results remain evidence; no retry-until-pass or discarded observations.

## Recorded results and comparisons

Every job retains unsigned Float64, raw libigl signed scalar, canonical sign int8,
combined Float64/Float32, closest face/point and A pseudonormal arrays. Record
endian-explicit hashes, sign and exact-zero masks and canonical state hash using
unchanged registered grid/masks/metadata. These are diagnostic states, not registrations.
Compare combined arrays by uint64/uint32 bits and np.array_equal, without tolerance.
Repeat/invariance/cross-environment gates include unsigned Float64, canonical sign,
combined Float64/Float32 and state hash. Raw scalar/closest-feature metadata are
diagnostic; changes that do not affect sign/combined field are reported separately.

Whole-field A/B agreement is measured on both v17 and v16, reporting all nonzero
sign differences and exact-zero disagreements with coordinates and distances.
Known nodes are the pre-frozen union of all saved SRCMAP-01 production v17 A/B/C/G
registered differences (19 nodes, current-only union 12), including the historical
three. D unsigned/composition semantic differences do not enlarge this local set.
Use saved closest-feature outputs; no extra adaptive target queries are authorized.
Compare candidate fields with registered v16/v17 and all saved production repeats;
old hash agreement is descriptive only. Retain exact difference maps and near-surface
magnitude distributions. The existing P22 hard center evaluator and existing smooth
volume/gV evaluator are used without changes; smooth diagnostics cannot grant hard
feasibility. The v16/v17 hard-volume difference is a two-grid discrete observation,
not continuum convergence or portability proof.

## Terminal predicates and precedence

1. Missing/incomplete output, input/runtime/source/mesh/integrity drift, analytic
   failure, unresolved zero/tie semantics or unexpected error => SRCMAP02_INCONCLUSIVE.
2. A repeat/chunk/order instability => PSEUDONORMAL_NOT_DETERMINISTIC.
3. B repeat/chunk/order instability => WINDING_CONTROL_NOT_STABLE.
4. Any nonzero A/B canonical sign disagreement => DETERMINISTIC_SIGNER_DISAGREEMENT.
5. Otherwise require two frozen environments' exact unsigned Float64, sign,
   combined Float64/Float32 and state hash agreement plus every earlier gate;
   if not satisfied => SRCMAP02_INCONCLUSIVE.
6. All gates satisfied => DETERMINISTIC_SIGNER_QUALIFIED, with A preferred only
   for a separately authorized next mapping contract.

Every exact mismatch fails the corresponding gate. No materiality tolerance is
introduced. Environment agreement is limited to these two bundles and observations.
A/B agreement is independent-method corroboration, not mathematical ground truth.

## Independent review, validation and stop

Independent pre-run review must PASS the exact frozen plan/source/runtime/input
hashes before the root records approval and launches the once-only campaign.
Post-run independent review evaluates raw outputs, predicates and claim scope.
Focused tests cover analytic sphere, box edge/vertex, A/B convention, exact zero,
chunk assembly, permutation restoration, repeat identity and classifier branches.
Full pytest baseline excludes only the new SRCMAP02 test file; final includes it.
Compare normalized failure IDs and require zero new failures, retaining exact
logs/JUnit as gzip with compressed and uncompressed hashes. Compileall src/scripts/tests
and diff/cached-diff checks are required before intended-file commit/push and no-ff
integration, with remote HEAD rechecked before merge.

No production signer/dependency migration, reference replacement, P22-v1/limits
change, P22-v2 registration/hash, canonical v17 authority regeneration, parent change,
LOWDIM-04A preregistration/restart, coefficient solve, CFD, Kaggle, #27 reopen,
#30 supersession, reinitialization, basis expansion or optimizer continuation.
Qualification flags unchanged; selected_delta=null; shape_update_allowed=false.
#51 stays OPEN and blocked. Stop at the recorded result for a separate user decision.

## Primary method documentation

- https://libigl.github.io/tutorial/#signed-distance
- https://libigl.github.io/libigl-python-bindings/igl_docs/
- https://pypi.org/project/libigl/2.6.3/

The installed API docstring and binary identity supplement these general references.
