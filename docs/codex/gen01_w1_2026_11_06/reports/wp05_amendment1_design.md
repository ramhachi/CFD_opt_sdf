# WP5 Amendment 1 implementation design (2026-11-06)

Scope: fix the source-review findings against `cb4df650`; development tooling,
tests and records only. The user's Amendment 1 overrides the first delivery's
instructions. Claude owns commit, push and PR #87; no `publication.git` path,
Kaggle calls, production solve, freeze, roadmap or registration edits.

Authority: `00_README.md`, `AGENTS.md`, the five project authority documents
(read across the team), `STATE.md`, branching strategy, GEN-01 rev 3.1,
TOPO-2D-00 registration and the **external review worktree's Amendment 1**,
and `reviews/wp05_review_1_opus.md` in that same read-only worktree.
The pinned T2-0 source, LOCAL-OF-01 and reference audit remain unchanged.
OpenCode Go preflight: no callable MCP; normal CLI failed opening its log;
isolated temporary data/cache/state directories allowed the catalogue query
but returned `Provider not found: opencode-go`. No configuration or paid API
change. Native inherited workers own disjoint Cp and collector files; the
parent owns geometry, foam, rendering policy, integration and final review.

## Contracts to implement before measurements

- A1: `load_geometry(..., family='fine30')` validates the *input* polyline;
  no WP5 resampling. Reject non-cap turning angles above 5 degrees and
  segments longer than `T.MESHES[family]['ds']`, with element/index/metric
  in the exception. A finite cap's endpoint corners are exempt from the
  turning-angle test only; its segments still obey the spacing limit.
  WP4 must supply dense smooth surfaces and a suitably divided finite cap.
  Preserve input bytes and SHA; coarse historical WP4 inputs fail closed.
- A3: compute a boundary-layer plan **once**, from minimum ground/inter-body
  gap across declared E1/E2/E3 thick and sharp geometry hashes. Each family's
  `T.layers` result, thickness and mesh specification are recorded in that
  plan and passed unchanged into all element walls and the ground block.
  Production requires this six-config plan. Synthetic/short development
  cases may declare their own smaller geometry set, explicitly development.
  Every case stores `mesh_stats.n_layers`, a top-level `n_layers`, and the
  plan identity; the collector rejects unequal layer counts within a family.
- A2: `collect_rans.CONVERGENCE`, re-exported by `t2d_foam_case`, is the one
  policy declaration derived from the unchanged runner/analyzer constants. Collector
  and runner use the unchanged T2-0b `force_summary` inherited by T2-0c:
  last 20% / at least 50 rows, 20-iteration block plateau (relative std and
  drift each <0.005), one continuation 5000 to 15000. Only raw-tail relative
  Cl std >0.005 is UNSTEADY; no T2-0d URANS/steady statistics or limit-cycle
  interpretation. Add the three review counterexamples as regression tests.
- A4: for each (config, model, family), eight mesh hashes must be pairwise
  distinct. Duplicate hashes produce `DEGENERATE_REALISATIONS`, point means
  retained, `ci90=null`, `ratio_test_status=INCOMPLETE`. Preserve raw forces;
  export INCOMPLETE to the old WP4 reader so it cannot accidentally certify
  a zero-width interval before its own schema/consumer update.
- A5: shared force objects require `observable=pressure_cl` for original
  sharp arms and `observable=total_cl` for thick arms. References are
  pressure_cl. Report h/c1 and h/c380, retaining the height datum. Report
  thickening-alone E* minus E*_sharp descriptively using *the same*
  observable on each side, retaining both pressure and total components.
- C1/C2: SHA-distinct corresponding reader CSVs, at least ten points per
  Cp surface, and positive downforce Cl for each element in each reading.
  Keep Table 15 scalar provenance separate. Double-element uncertainty is
  the sum of per-element absolute reader differences; retain 5% and [0.5,2].
- B1/B2: gmsh proxy is informational; checkMesh determines mesh acceptance.
  Nonfinite force rows are diverged/NUMERICAL, generator/mesh failures are
  MESH_FAILED, and actual infrastructure loss remains INCOMPLETE.
- B3: ready requires a clean *whole* tree and a freeze-1 record bound to
  HEAD, source and geometry hashes. Unknown/OCR-unverified geometry or any
  missing binding yields a development render, ready=false and no push
  plan. Source code/tests may exercise rendering with synthetic fixtures;
  existing real kernel bundles are **not regenerated** in this amendment.
  Mark existing infra/work plans explicitly development, and retain their
  old bytes/hashes as historical development artifacts where immutable.
- B4/E1: source comments for inherited numerical constants; wall Distance
  reads supplied dense vertices rather than three samples per short edge.
  Remove unsupported merge-tree claim. Report A1/A3/A2 differences explicitly.

## Files and verification

Change only WP5 scripts, WP5 tests, WP5 reports/schemas, and development-plan
metadata explicitly requested above. Do not edit registered T2-0 sources,
existing immutable evidence/locks/pins or WP4's worktree. New validation
artifacts go under `reports/wp05_amendment1_validation/`; the first delivery's
raw archives stay historical and do not certify the corrected implementation.

TDD: add targeted adversarial tests first, run smallest relevant slice,
then `pytest -q tests/topo2d00`, `compileall src tests`, and the requested
result-only full suite:

```
.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider
git diff --check
```

Compare failure-node set to Claude's host base `e3dcdf61`:
3482 passed / 74 skipped / **empty failures** (user-supplied base evidence).
Record exact command, outputs/hashes and source inventory separately from
scientific conclusions. No repeat of Metal or base is required by Amendment 1.
Fresh E2 local mesh/smoke needs the WP4 dense input; never bypass the A1 guard
or treat the first delivery's faceted smoke as current acceptance evidence.
