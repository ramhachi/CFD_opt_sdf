# WP5 design — TR-00 / TOPO-2D-00 RANS tooling

Amendment 1: the first-attempt decisions/verification below are historical.
The active correction design is [wp05_amendment1_design.md](wp05_amendment1_design.md).
In particular, coarse faceted input is now rejected, BL counts are fixed per
family over six geometries, and T2-0c (not T2-0d) classifies convergence.
Claude performs commit/push; no real kernel is re-rendered in this amendment.

Date: 2026-11-06. Development/capability work only; the registration remains a
draft, qualification flags remain false, and no production run is authorised.
Base: `e3dcdf61`, branch `feat/gen01-w1-05-tr00-rans`, clean before work.

## Authority and scope

Read order follows `../00_README.md` and `AGENTS.md`. The five authority
documents, `STATE.md`, branching strategy, GEN-01 rev 3.1, the complete
TOPO-2D-00 registration, W1 facts report, T2-0 generators/runners, fine30
evidence, LOCAL-OF-01 and reference audit are reviewed across the parent and
workers. `phase_plan.md` controls order; existing source, evidence, registries,
pins and kernel directories are immutable. This adds tooling and tests only.
The old T2-0 NO-GOs are not revisited. No Kaggle calls, production solves,
figure digitisation, registration verdict, or threshold changes.

OpenCode Go: no callable MCP tool was available; `opencode models opencode-go`
failed opening `/Users/sota/.local/share/opencode/log/opencode.log`. No global
configuration change or paid fallback. Native workers implement disjoint
files, and the parent reviews integration and runs bounded local verification.

Routing trace: `requested_model=OpenCode Go (logical worker pool)`,
`actual_model=native inherited Codex (no override; exact ID not recorded)`,
`reason=no callable MCP and CLI preflight log-path permission failure`,
`attempt_number=1`. No paid direct API was enabled; the failed CLI preflight
was not retried.

## Interfaces and decisions fixed before implementation

1. Import `t20_case` mesh-writing, layer and quality helpers and `t20_foam`
   dictionary functions; do not copy or edit the registered generators.
   Assemble one plane surface with one hole per closed contour and independent
   wall groups `airfoil`, `airfoil_2`, `airfoil_3`; retain inlet/outlet/top,
   moving ground and front/back from T2-0.
2. Choose `med30` as the second family. It is the existing family and adds no
   unregistered tuning parameters. `fine30` retains its ds/y1/g settings.
   Sharp TE points use the existing fan parameters; finite blunt caps do not
   receive a sharp-tip fan. Inspect both mesh proxy and real `checkMesh`.
3. Geometry JSON declares metres, config, reference chord and elements with
   IDs, closed point arrays, and explicit sharp/blunt TE metadata. NPZ uses
   the same JSON metadata and per-element point arrays, without pickle.
   Input SHA, source-helper SHAs, mesh SHA and per-element decisions go in a
   T2-0-style manifest. Missing, intersecting, unknown or inconsistent input
   must fail closed.
4. `write_case(out, geometry_path, model, family, realisation, iterations)`
   produces SA-WF/SST-WF dictionaries, 5000 iterations by default, total and
   per-element force coefficients, using a single reference area `c1*z`.
   All configurations use `c1=0.2234 m` so differences represent force changes;
   the paper's `c=0.380 m` normalisation is separately documented. No trip is
   imposed. SA/SST wall functions do not resolve or predict free transition;
   absence of a trip is not transition-model validation.
5. Cp inputs are supplied by the user, separately for physical upper/lower
   surfaces and two independent digitisations, with source and normalisation
   metadata. Integrate piecewise-linear data by trapezoids, positive
   downforce. Use the mean of the two independent integrals and their absolute
   difference as a conservative digitising sensitivity, not a confidence
   interval or total experimental uncertainty. Retain Table 15's 1.009 at
   h/c1=0.448 as a distinct scalar-source route. Never mix balance CL with
   centre-section pressure Cl. The 5% rule and ratio band [0.5,2] are unchanged.
6. Publish `topo2d00_rans_result_schema.json` if WP4 has not supplied it.
   Keys: config/model/family/realisation; total and element Cl/Cd, common
   normalisation, convergence evidence, geometry and mesh SHAs. Preserve
   missing runs explicitly and distinguish a non-settled steady iteration
   history from physical unsteadiness. Reuse existing convergence helpers.
7. Render self-contained, hash-bound CPU kernels locally. TR-00 has 64 runs;
   the main series has at most 96, gated on explicit qualified cells. Split
   into chunks fitting the 12-hour session limit with budget stops and five
   concurrent sessions. Source-bound rendering does not submit a kernel.

## Files and validation plan

New modules: `scripts/topo2d00/{t2d_multibody_case,t2d_foam_case,digitize_cp,
collect_rans,build_tr00_kernels}.py`, with a runner/helper only if necessary.
New tests live in `tests/topo2d00/`. No dependency changes or new source pins.
Design detail for each disjoint worker is recorded in `wp05_*_design.md`.

TDD: synthetic contours/Cp/run records first, then implementation. Mesh tests
skip if gmsh is unavailable following the existing `_NO_GMSH` convention.
Baseline full pytest starts before editing, with log in
`/private/tmp/wp05_baseline_pytest.log`. Final checks: focused pytest,
compileall src/tests, full pytest and diff check; compare exact failure sets.

Local execution uses `scripts/local_openfoam.py` and the frozen image only:
one realisation each for E2_sharp and E2, mesh-only then SA-WF at no more than
200 iterations. Record mesh/checkMesh/force finiteness and image/package
identity as smoke evidence only. Do not repair frozen policy or claim local
gmsh equivalence with Kaggle (LOCAL-OF-01 failed that contract).

## Open inputs and risks

At initial inspection WP4 has no geometry files or schema in its worktree.
The user has been asked for an existing geometry path while independent work
continues. Published E2 and thickened E2 must not be fabricated from the
listed gap/chord dimensions. Synthetic closed contours can test capability,
but cannot satisfy a claim of running the registered E2 geometry.

Historical runtime attribution differs: the WP prompt quotes 13–21 minutes
as fine30, whereas `t20_summary_for_m4_2026_10_22.md` assigns it to xfine30 and
6–11 minutes to fine30. Use the requested 13–21-minute envelope conservatively,
disclose the discrepancy, and make no measured multibody runtime claim.

Commit only intended new files after validation, push this feature branch and
open a PR against `codex/kaggle-batch-migration`, with auto-merge disabled.
