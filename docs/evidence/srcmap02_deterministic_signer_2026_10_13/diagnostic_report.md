# SRCMAP-02: fail-closed zero-semantics stop before signer qualification

Terminal classification: **SRCMAP02_INCONCLUSIVE**.
The once-only campaign stopped in its first canonical v17 Candidate A job.
No deterministic signer or production remedy is qualified. The campaign's
`complete=false` is preserved; this report records the terminal stop, not a
completed 32-job comparison. Issue: [#53](https://github.com/ramhachi/CFD_opt_sdf/issues/53).

## Authority, freeze and environment

- Integration parent: `e621b585531f7fe3f44d0a8683cec1923008de56`.
- Freeze SHA256: `58fe2853fe2b913b82555bd4a5cbcefd2b6fcf93740e88c3c644e9c893d0d707`.
- The exact diagnostic/runner/test sources, inputs, inventories and plan are
  bound by 161 frozen file hashes. Containing source and integration commit
  identities are published in the completion issue comment.
- Source STL SHA256: `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`.
- SRCMAP-01 diagnostic commit `0cd941badb45770c518809a95a535c2d06c1f4c5` and its
  old evidence remain unchanged. Its 130-entry manifest passed before this
  campaign. #52 was closed as a completed nondeterminism diagnosis, explicitly
  without a qualified remedy; signer qualification moved to #53.

Libigl was exact-pinned to **2.6.3**, installed only in a diagnostic PYTHONPATH
target at `/private/tmp/srcmap02-libigl`. The same wheel imports in both bundles:
`libigl-2.6.3-cp312-abi3-macosx_11_0_arm64.whl`, SHA256
`da3c62c50103be9b192bc76bbcb9e5031d80a2cf209b3ef0a0cf0060750088d9`.
Its imported module is `/private/tmp/srcmap02-libigl/igl/__init__.py`;
13 module/binary/distribution artifacts per inventory are hashed. The exact
release sdist declares core revision `f68f01c23ac82351e2543ce8c529b6d4c89fdf16`.
This source provenance is not a reproducible binary-build attestation.
See [wheel identity](wheel_identity.json), [candidate runtime](candidate_runtime.json),
[current inventory](current_runtime_inventory.json), [minimum inventory](minimum_runtime_inventory.json)
and [release source](libigl_source_provenance.json).

| Runtime | Current | Minimum representative |
| --- | --- | --- |
| Python | 3.12.13 | 3.12.13 |
| NumPy | 2.5.2 | 1.26.4 |
| SciPy | 1.18.1 | 1.11.4 |
| trimesh | 5.1.0 | 4.4.0 |
| rtree | 1.4.1 | 1.2.0 |
| libspatialindex | 2.1.0 | 1.9.3 |
| libigl | 2.6.3 | 2.6.3, same wheel |
| OS / CPU | macOS 26.3.1 arm64 / Apple M4 | same |

Both metadata-only preflights and the formal fixture runtime check passed the
frozen structural identity checks. No minimum-environment target field was
attempted. The failed worker did not persist its before/after runtime metadata,
so a complete per-worker after-identity check is not claimed.

## Methods, analytic gate and mesh premises

Candidate A was preferred before results: official angle-weighted pseudonormal.
B is the generalized winding-number control. They are independent sign criteria
within libigl, not independent libraries or independent geometric certification.
Explicit `trimesh.proximity.closest_point` unsigned distance is separate from
libigl signing. No randomized trimesh signed distance or abs thereof is used.
Only the sign of libigl's returned scalar is used, not its magnitude.

The formal analytic gate passed for both candidates at all **42 points each**:
axis-aligned box 11, rotated box 9, tetrahedron 11, triangulated sphere 11.
Shared smooth-sphere/polyhedron points are safely interior/exterior to both;
near-feature sphere-family tests refer to the inscribed convex polyhedron and
its analytic half-space labels. Surface zero cases refer to the actual mesh.
See [analytic fixtures](analytic_fixtures.json).

Static source-mesh evidence records 1344 vertices, 2684 faces, 4026 edges each
with incidence two, edge/vertex manifold checks passed, consistent winding,
watertightness and one component. Positive signed polyhedral volume is
`0.1292499984670429 m3`, descriptive only. Self-intersections were not tested;
outward orientation is supported conditional on a non-self-intersecting
embedded boundary. These checks do not establish universal geometric truth.
See [mesh prerequisites](mesh_prerequisites.json) and [authority audit](authority_audit.json).

## Observed first-job failure and what remains unknown

The predeclared zero rules require unsigned bitwise +0 to produce phi +0.
A libigl returned scalar exactly zero with strictly positive independent
unsigned distance is a fail-closed semantic blocker. No epsilon/tie rescue
was allowed. Float64 and Float32 output zeros were to normalize to +0.

After the formal fixture PASS, job **B_A_repeat_1** ran in the current bundle,
v17, canonical order, chunk size 200000. It reached the composition guard:

`ValueError: signer zero at strictly positive unsigned distance`

The child and runner returned exit code 1. The traceback identifies the exact
`(raw == 0) & (unsigned > 0)` predicate. At least one query therefore had an
exactly zero libigl signed scalar and a positive closest-point magnitude.
This does not prove that the pseudonormal dot-product sign itself was zero:
libigl returns a signed distance scalar, and different distance arithmetic can
also yield that scalar state. Which nodes, their count, magnitudes, closest
features and geometric/numerical cause are **unavailable**.

The implementation raises inside `query` before returning arrays to the worker's
persistence step. The failed process therefore retained a traceback but **no raw
NPZ, job JSON, candidate state or complete combined field**. This is an evidence
retention limitation. No fresh query, rerun, frozen-source edit, threshold change
or added tie rule was used to recover those missing observations.

See [execution stop](execution_stop.json), [first-job traceback](logs/B_A_repeat_1.log),
[exact runner log](logs/campaign.log.gz), [execution marker](execution_started.json)
and the unchanged raw [classification](classification.json).

## Fixed matrix disposition

The planned matrix was 32 independent full-field jobs: 10 repeats, 18 chunk/order,
2 minimum-environment fields and 2 v16 fields. Actual disposition is **1 attempted,
0 completed, 31 not attempted, 0 measurement reruns**. This is not zero target work:
the first worker reached the combine guard after its query loop.

| Requested result | Observed disposition |
| --- | --- |
| A pseudonormal, N=5 repeat identity | First attempt blocked; zero complete retained fields; identity unavailable |
| B winding, N=5 repeat identity | Not attempted |
| Three chunks x three orders, both candidates | Not attempted |
| Two-environment exact candidate agreement | Not attempted; both metadata inventories/preflights are available |
| Whole-field A/B sign differences | Unavailable, not zero |
| Known historical three and all 19 saved SRCMAP-01 problem nodes | Population/old outcomes frozen; new candidate signs unavailable |
| Candidate versus old v16/v17 fields | Unavailable |
| Deterministic v16/v17 hard volumes and their difference | Unavailable; no candidate states generated |

The corresponding summary files explicitly use NOT_EXECUTED/UNAVAILABLE/null
rather than invented counts. Existing registered hard volumes remain
`0.12612500000000004 m3` (v16) and `0.12925000000000003 m3` (v17); these are old
reference observations, not new deterministic-mapping measurements. This stop
adds no new lattice-nonportability or volume-bridge qualification evidence.

## Independent review and software validation

The final pre-run independent review is PASS for the exact freeze. Its design
findings were resolved before measurement. The post-run independent review is **PASS**, limited to recording/integrating
this fail-closed result and its limitations; it does not approve signer adoption.
The prepared full-array checker is preserved as frozen source but cannot run
without completed fields; a separate independent stop checker verifies the
retained failure/fixture/freeze evidence without geometry queries.
See [pre-review](independent_review_prerun.md), [post-review](independent_review_postrun.md),
[independent stop check](independent_stop_check.json) and [validation](validation.json).

Focused tests: **8 passed**. Full baseline: **48 failed / 2184 passed / 23 skipped**.
Full final: **48 failed / 2192 passed / 23 skipped**. The same 48 failure IDs remain:
**new 0, resolved 0**. All eight new tests also pass in final JUnit. This is not
an all-pass suite. Compileall src/scripts/tests and diff checks passed. Exact
logs/JUnit are retained as gzip with compressed and uncompressed hashes in
[baseline validation](baseline_validation.json) and [final validation](final_validation.json).

The old SRCMAP-01 manifest now has 128 matching current hashes plus two living
document hashes verified at the integration parent with exact-prefix preservation.
The old bridge manifest similarly has 35 current matches plus two earlier-parent
document hashes. Both manifests and all 159 files in the three protected historical
evidence directories are unchanged. The freeze had 161/161 matches after the stop
before authority appendices; final preservation is 159 current matches plus those
two parent/prefix checks. See [protected authority checks](protected_authority_check.json).

## Preservation and stop

Production mapping, pyproject dependencies, P22-v1 hard/smooth contracts/limits,
source geometry, retained fields, accepted LOWDIM parent and qualification flags
are unchanged. P22-v2 and its contract hash were not registered/generated.
LOWDIM-04A is blocked and was neither preregistered nor restarted. CFD runs 0;
Kaggle submissions 0; selected_delta=null; shape_update_allowed=false.
No coefficient solve, production signer migration, canonical authority replacement,
reinitialization, basis expansion, optimizer continuation, #27 reopen or #30
supersession occurred. #51 remains OPEN. #53 retains this inconclusive stop;
any additional measurement or revised contract requires a separate user decision.
