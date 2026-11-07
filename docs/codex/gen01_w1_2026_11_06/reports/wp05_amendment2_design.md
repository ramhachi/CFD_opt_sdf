# WP5 Amendment 2 design (2026-11-07)

Base: `45917d8c`, clean `feat/gen01-w1-05-tr00-rans` worktree. This is the
third implementation pass, responding to `wp05_review_2_opus.md` and the
registration's Amendment 3 in Claude's read-only review worktree. Those
amendments take precedence over the earlier WP5 instructions. Frozen T2-0
helpers, registration text, roadmap and existing evidence stay untouched.
Commit, push and PR updates belong to Claude on the host.

## Intended changes and interfaces

- `t2d_multibody_case.py`: validate >=0.1 mm segments and adjacent length ratio
  <=3, including cap segments (only cap angles are exempt). Preserve every
  supplied vertex. Registration Amendment 3's maximum is min(1 mm, family ds).
  Realisation k rotates each polygon by k*floor(n/8), remaps
  its TE/LE feature indices, and offsets the far-field inlet/outlet/top by
  Halton(2,3)*ds, with the ground fixed. Expose the exact perturbation in the
  manifest. No upstream spline reconstruction.
- `t2d_foam_case.py`: pass the realisation to the mesher, record the deterministic
  mechanism, read the physical scene height and validate it against a declared
  study height passed through the run plan. Preserve separate minimum-clearance
  diagnostics and both chord normalisations.
- `run_rans.py`: integrity failures and session-deadline interruptions are
  `RUNNER_EXCEPTION`/INCOMPLETE; actual generator/gmsh/checkMesh results alone
  are MESH_FAILED. Preserve solver divergence as a numerical result.
- `collect_rans.py`: bind heights from case/plan metadata, compare them with the
  reference, export INCOMPLETE > MESH_FAILED > NUMERICAL > SETTLED severity,
  and form thickening descriptors only from two settled histories of the same
  observable. Keep duplicate-mesh detection and the shared schema contract.
- `digitize_cp.py`: canonicalize parsed, ascending numeric pairs before comparing
  independent readings. Byte hashes remain provenance; BOM, line endings,
  numeric spelling and input direction cannot manufacture independence.
- Tests: hermetic fixtures and the branch-local JSON schemas replace execution
  of another worktree's analyzer. Tests cover the 5.6 micrometre sliver, dense
  accepted polygons, all eight deterministic realisations, failure boundaries,
  severity combinations, observable-specific usability and numeric reader copies.

## Validation and evidence

Use TDD on each relevant test module, then `pytest -q tests/topo2d00`. Measure
eight distinct med30 E2_sharp synthetic mesh hashes locally and repeat an index
in a fresh process; this is a mesh-realisation mechanism check, not an E2
physical smoke or a checkMesh acceptance claim. Gmsh tests retain the existing
find_spec skip convention, without a new source pin or dependency.

Final checks: `.venv/bin/python -m compileall src tests`,
`.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider`,
and `git diff --check`. Compare the final failed-node set with the supplied
host base record (`e3dcdf61`: 3482 passed / 74 skipped / zero failed), without
re-running a base checkout. Store new command logs, JUnit, hash receipts and
mesh-mechanism measurements under `reports/wp05_amendment2_validation/`.

No OpenFOAM smoke, production solve, kernel regeneration, Kaggle operation,
freeze, commit or push is authorized in this pass. Old renders remain revoked
development artifacts. Ready still requires a clean freeze-1-bound commit and
verified complete geometry. Actual WP4 sliver repair and Kaggle single-index
determinism remain external validation steps.

## Reproducibility investigation: N2 remains blocked

The indexed-input implementation is deterministic, but raw same-index mesh
output is not established. Preserve the following counterevidence:

- `Mesh.Reproducible=1` did not stabilize 2D output. A 13-significant-digit
  serialization trial passed once, then failed the final focused run (274 pass,
  1 fail). It crossed both rounding boundaries and T2-0's x-sort node-ID ties.
- A repositioning-off probe passed four times, then a sixth control changed
  raw SHA and cells (31796/31794). The paired repositioning/topology-off probe
  produced four raw hashes in eight same-index processes. Smoothing-off also
  failed. No candidate option is adopted; these public-option/precision trials
  did not qualify N2.
- Independent official gmsh-4.15.2 source inspection found a pointer-ordered
  BL wall-vertex container assigning creation-dependent internal node numbers
  before the later 2D insertion/tie-break operations. This is a concrete
  possible mechanism, not instrumented proof of the failed pair's internal
  ordering. Public options to stabilize it were not identified.

Final cleanup removes all coordinate post-processing and the ineffective
reproducible flag. `T._write_msh` alone writes the actual solver-input artifact.
Keep the registered polygon rotation/Halton input mechanism and strict
same-index mesh-SHA assertion. Write all measurement receipts before asserting,
so a failure is retained rather than weakened into a passing test. Complete
one final focused/full execution after cleanup. Report N2 as BLOCKED regardless
of a later single passing pair; do not promote chance passes to qualification.

A separately qualified Gmsh implementation fix or a formally materialized-mesh
input contract would require owner decisions outside this WP's registered
scope. No registration, dependency, runtime, freeze or external publication
is changed. All other scoped amendment implementations remain reviewable.

OpenCode Go MCP was absent. CLI 1.19.3 model listing failed before provider
contact with FileSystem.open on its sandbox-external log path; no Go worker
ran and no global configuration or paid API was changed. Native scoped workers
are used for the expressly requested independent work; the parent integrates
and verifies the concrete diffs and artifacts.
