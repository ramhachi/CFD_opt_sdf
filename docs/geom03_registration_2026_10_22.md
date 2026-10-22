# GEOM-03 (#70) preregistration draft: represented-width + frozen-node margin + fixed topology composite — DRAFT_FOR_REVIEW (rev. 3)

Status: **DRAFT_FOR_REVIEW.** Nothing is frozen, registered, qualified, passed or run; no fixture or seed executed.
Parent owns review and freeze. Governing roadmap: `docs/phase_plan.md` (2026-10-22); ledger GEOM-03 #70
(`docs/problem_register_2026_09.md`). Sources: `docs/width_rule_decision_2026_10_20.md` (D-1..D-3),
`docs/width_rule_plan_2026_10_20.md` (K1–K6), `docs/evidence/width_rule_2026_10_20/` (exploratory); solver-free, no
OpenFOAM/FID force results are used by this preparation. Existing FID execution is preserved separately.

## 1. Scope; unchanged contracts; claim scope

GEOM-02 v2 stack, profile `geom02_v17_research_gates_v2_crossing_slope_2026_10_15`, policy `d4cd9aa4…`, all 13
gates, thresholds, records, qualification flags: unchanged. FID-01 (#62, M3a) keeps R0 as registered; M3a is not
modified; R3 in M3a is descriptive-column-only, never a gate. `shape_update_allowed = false`; the registered 1.5 h
limit is not lowered; manufacturing claims unchanged. Old artifacts are immutable **known data** — diagnostic
controls (§8), never held-out validation evidence. `GEOM03_PASS` alone is not adoption; M3b (#64) adopts only via
its own registration. No claim regardless of verdict: CAD minimum thickness, manufacturing minimum, meshing
quality, physical/FSAE qualification, grid-independent downforce, solver accuracy — the composite measures only
the solver-visible lattice representation.

## 2. Composite definition (frozen at freeze; no parameter changes after)

- **R3** (`h = 0.025 m`; reused from `scripts/width_rule_study.py`, no reimplementation, no new dependency).
  Crop = node-aligned bounding box of solid nodes (`phi < 0`) padded `OPEN_PAD = 3` nodes/side, **padding clipped
  at array bounds — no guarantee the body is interior**. `phi` trilinearly refined at `OPEN_K = 4` (h/4,
  node-aligned, the solver's interpolation); body `B = {refined phi < 0}` — an h/4-sampled **approximation of the
  continuous trilinear zero set, not an exact continuous certification**. Erosion `E = {x in B : EDT_B(x) > r}`,
  `r = 0.75 h`, EDT step h/4; opening `O = {x : dist(x, E) <= r}`;
  defect `D = max over B \ O of dist(x, O)` — the **maximum distance of rejected material to the opening**, not a
  "largest ball radius".
- Status (`defect_status`): solid — empty `B` → `unmeasured`; `D <= tau + LENGTH_TOLERANCE_M` → `pass`;
  `D <= tau + h/4 + LENGTH_TOLERANCE_M` → `unmeasured`; else `fail`; `tau = 1.0 h` and
  `LENGTH_TOLERANCE_M = 1e-9 m`. An empty helper input gives `D = None`; a nonempty body with no eroded
  voxel gives `D = infinity`, hence `fail`. Void uses the complement **within the whole crop array**.
  `defect_status(None, h, void=True)` is `pass`; a nonempty void with no eroded voxel is not exempt.
  Top-level `r3` returns solid/void `None`, status `unmeasured` immediately when there is no solid.
  Ordinary finite interior bodies have exterior void in their crop. E2 tests the all-true finite-array helper
  convention directly; it is diagnostic, not an interior-body validation. Row status = worst(solid, void).
- Boundary: ordinary scored finite-body rows require a full +3-node halo. Clipped → `crop_halo_missing` →
  `INCOMPLETE`, counted, never silently excluded. **The spanning K5 slab family cannot meet this halo rule.**
  Its separate finite-array boundary convention/comparison domain remains REQUIRED_BEFORE_FREEZE (§12);
  no K5 execution or verdict is authorised until that conflict is resolved prospectively.
- **P1 (precondition, metres).** `min |phi| over non-active (frozen) nodes >= h/2` for parent and every gated
  state; violation → composite `blocked` (blocks like a fail), scored in the prespecified negative control
  (K4'a), not globally excluded. Every ordinary fixture needs an explicitly bound nonempty frozen-node mask;
  the empty-mask convention remains REQUIRED_BEFORE_FREEZE, never a silent vacuous pass.
  **P2 (registered gates unchanged).** `allowed_events = ()`; registered `max_components = null` (no fixed
  count cap), solid neighbourhood 26, empty solid inadmissible; a forbidden event still fails P2.
  `component_connectivity` / `topology_change_classification` exactly as `geometry_gates_v2._topology_gates`;
  scope **solid components only; void cavities/tunnels are not judged** (registered, line 344).
- Composite = `blocked` if P1 fails, else worst(R3, P2) with order pass < unmeasured < fail. R0 recorded per row,
  descriptive only.

## 3. Three distinct topology notions (P2 judges only the first)

**Node-graph topology** — what P2 judges: 26-neighbour connectivity over **coarse nodes with phi < 0** (registered
rule, `geometry_gates_v2.py:337`); **not** continuous trilinear topology. **Dense-sampled represented set** — h/4
refined body; basis of R3 and `represented_*` labels. **Analytic topology** — true signed-distance geometry;
metadata only, never a gate input.

Fixture event rule: an event is a node-graph component-count **change from a specified parent fixture** (1→2 split,
2→1 merge); a final count observed without a specified parent is **not an event**; every topology-transition
fixture names its parent (§7). Under `allowed_events = ()` any node-graph split/merge → P2 fail.

## 4. Criteria K1'–K6' (fixed before measurement; no observed-value exclusions)

- **K1' (no artefact):** every K1 row (§7: 24 phase rows + 20 combinations) is `pass`; `unmeasured` is a non-pass
  → K1' fails. **K2' (thin held fails):** preregistered `thin_represented` rows (solid or void) are **not pass**
  (`fail` or `unmeasured` both satisfy K2'); the R3 guard band is part of the status scale, not an exclusion.
- **K3' (thick and declared-tolerance rows pass):** preregistered `thick` (S3, V3, R1) and `tolerated_short`
  (F1, W3, W4) are `pass`; a tolerated row failing means the declared tolerance was wrong (K3' failure), never a
  class reassignment.
- **K4' (negative controls, main):** (a) P1 control R2 → composite `blocked`; (b) above-limit slabs T2, T3 (true
  SDF width 1.6 h, 1.76 h > 1.5 h) → **not `fail`** (pass or unmeasured); (c) split control N2 (parent, d = 2 h)
  → P2 topology fail; merge control A1 → P2 topology fail. D1 is a diagnostic node-graph 1 / dense 2
  comparison, **a discrepancy between representations, not a continuous-topology qualification or a general
  conservatism guarantee**. Its preregistered build labels must be verified independently; it is not a K4
  acceptance target. Historical controls (§8) are also diagnostic only.
- **K5' (proposed discrete comparison; boundary contract still open).** On the 40 slab rows let
  `q(w) = count(status == pass) / 8` for each rule (composite, R0); `unmeasured` and `blocked` are non-pass.
  Require a nondecreasing sampled pass curve and define `w_lo = max{w : q(w) < 1/2}`,
  `w_hi = min{w : q(w) >= 1/2}` on the five-width grid. K5' holds iff both endpoints for the composite are
  at least the corresponding R0 endpoint (zero tolerance). Missing brackets or a nonmonotone curve give
  `k5_degenerate` → `INCOMPLETE`; no adaptive width additions. This compares discrete intervals only, not
  an exact or continuously ordered crossover. §12 must resolve the spanning-slab boundary/P1 contract
  before this proposed rule can be frozen.
- **K6' (positive phi scale, width zero-set only).** The trilinear zero set is determined by the **nodal values**
  via linear interpolation, not by the sign pattern alone; `c·phi` (c > 0) leaves the zero set unchanged, so the
  sampled sign body and every R3/P2 status is identical. Each scored row: statuses at `c ∈ {0.5, 2}` equal the
  base status; **P1 is never evaluated under scaling** (reads phi units, metres).

## 5. No adaptive retuning; one attempt

`r = 0.75 h`, `tau = 1.0 h`, `k = 4`, `pad = 3`, thresholds, seeds, phase lists, fixture table, preregistered
labels/expectations and criteria are fixed here; no label or class is assigned from any R3 output; a changed
candidate is a new registration. After freeze: **one attempt**; resume only from the append-only cache with
identical hashes (same attempt); otherwise `INCOMPLETE`.

## 6. Lattices and phases (explicit)

- **Synthetic lattice** (fixed cases, slabs, controls): 26³ nodes, h = 0.025 m, origin (0,0,0) m; analytic
  signed-distance formulas sampled at nodes.
- **v18 lattice** (K1 rows): existing frozen `genesis.json` and `v18_parent.npz` confirm shape 121×65×49,
  float32 phi, bool design mask, origin (-1,-0.8,-0.6) m, h = 0.025 m. Full source/policy hashes are in
  [preparation source bindings](evidence/parallel_preparation_2026_10_22/geom03_source_bindings.json).
  Reading this existing metadata is not a new held-out study measurement.
- Phases (odd h/16, disjoint from the exploratory h/8 grid): `P8 = {((1,1),(1,5),(5,1),(5,5),(9,9),(3,11),(13,3),
  (7,15))/16·h}`; `Q2 = {(0,0), ((1,1))/16·h}`.

## 7. Proposed held-out fixture table (136 rows; geometry bindings still required)

**K1 — 44 rows.** (a) 24 = 3 analytic bodies × `P8` on the v18 lattice, explicit signed-distance formulas (not
`v18_plate.py`): B1 stadium plate t = 0.12 m, edge radius 2.5 h, span 0.875 m; B2 rounded box bar radius 2.6 h; B3
rounded slab t = 4 h, end radius 1.8 h. (b) 20 combinations on B1, `k = 0..19`: `numpy.random.default_rng(20261022
+ k)`, `c = rng.uniform(-1, 1, 3)`; `t += 0.15 h·c[0]`, `z += 2 h·c[1]`, pitch `+= 0.4°·c[2]`; phase (0,0); no noise
fields; expected all pass (K1').

**Fixed analytic table — 26 cases × `Q2` = 52 rows**, including named parent controls N1p, N2p, A1p, D1p.
These are prospective labels/expectations; the independent checker must verify the build, never reclassify
it from the measured R3 result:

| id | case | preregistered label / expected outcome |
|---|---|---|
| S1 | solid sheet 0.75 h | thin_represented → not pass (K2') |
| S2 | solid sheet 1.25 h | diagnostic: expected unmeasured (guard band); not K-scored |
| S3 | solid slab 3 h | thick → pass (K3') |
| V1 | void sheet 0.75 h | thin_represented (void) → not pass (K2') |
| V2 | void slot 1 h | thin_represented (void) → not pass (K2') |
| V3 | void gap 3 h | thick (void) → pass (K3') |
| N1 | neck d = 1 h, l = 4 h (parent N1p: d = 2 h) | thin_represented → not pass (K2'); parent node-graph 1 comp; no node-graph event expected |
| N2 | neck d = 0.5 h (parent N2p: d = 2 h) | split control: node-graph 1→2 vs parent → P2 fail (K4'c); analytic label connected (metadata) |
| W1 / W2 | wedges 20° / 40° | thin_represented → not pass (K2') |
| W3 / W4 | wedges 60° / 90° | tolerated_short → pass (K3') |
| F1 | fin 1 h × 4 h | tolerated_short → pass (K3') |
| T1 | taper, thin end 0.75 h | thin_represented → not pass (K2') |
| T2 / T3 | slabs, true SDF width 1.6 h / 1.76 h | above-limit controls → not `fail` (K4'b) |
| A1 | two bodies 0.2 h apart (parent A1p: 2 h apart) | merge control: node-graph 2→1 vs parent → P2 fail; analytic label 2 comps (metadata) — node-graph judges representation, not analytic geometry |
| D1 | two bodies touching only diagonally (parent D1p: 2 h apart) | diagnostic comparison: proposed node-graph 1 / dense 2; no claim of continuous-topology qualification |
| R1 / R2 | thick bodies, frozen rims \|phi\| = h/2 exactly / 0.3 h | R1: thick → pass (K3'), p1_min = h/2 (P1 holds at >=); R2: P1 negative control → composite `blocked` (K4'a) |
| E1 / E2 | empty solid / direct all-true finite-array helper input | diagnostic: top-level empty-solid is unmeasured; empty void helper is None and its defect status passes. E2 is not a finite interior-body/halo test; not K-scored |

**Slabs (K5') — 40 proposed rows:** spanning slabs, widths {1.0, 1.25, 1.5, 1.75, 2.0} h × `P8`, synthetic
lattice. Boundary/P1 contract remains open (§12). Proposed total: 44 + 52 + 40 = **136** base rows, including
diagnostics; K6 adds two scale evaluations per scored row. No rows added after freeze; all evaluations and
checker work count against the wall/memory budget, not an invented 200-function-call limit.

## 8. Known-data historical controls (diagnostic only; not K-scored; ≤ 5 rows)

Candidates: v18 parent, OPT-01 v1 parent, OPT-01 `surge +25`, OPT-01 `thickness -5`, one REINIT-04 output. Before
freeze each is bound to **exact source hash(es) and recorded status as written in the artifact record**; a row
whose recorded R0 status cannot be verified is **dropped, not guessed** (REQUIRED_BEFORE_FREEZE #3). The checker
reproduces kept controls' recorded R0 statuses; composite statuses reported descriptively. Historical integrity
does not replace K4'; the new rim/thinned-slab controls of §7 are the main negative controls.

## 9. Implementation (minimal: 2 scripts + 1 test)

- `scripts/geom03_run.py` — study path; imports `width_rule_study` (`measure`, `r3`, constants); implements the §3
  fixture event rule and the explicitly bound fixture formulas/masks; no separate fixture framework.
- `scripts/geom03_check.py` — independent checker; **scipy.ndimage only** (`distance_transform_edt`,
  `binary_dilation`, `label` with a 26-connectivity structure; no custom union-find, no framework, no new
  dependencies); computes R3, node-graph and dense counts, analytic labels from its own signed-distance formulas;
  the measured gate is never its own oracle (reusing scipy is fine).
- `tests/test_geom03.py` — one file: (1) study-vs-checker agreement on 5 tiny fixtures (round bar 2.3 h, 0.75 h
  sheet, 3 h box, spike, empty-input convention); (2) P1 boundary h/2 passes / 0.3 h blocks; (3) K6 scaling
  equality; (4) halo/clip and void/empty conventions.
- Agreement: identical status and prospective-label verification on 100 % of rows; any disagreement or
  ambiguous independent label → `INCOMPLETE`, never a parent-selected alternate verdict or rescoring.
  A validly constructed row contradicting a scored acceptance criterion gives `NO_GO` under §10.

## 10. Verdicts

- **`GEOM03_PASS`** — K1'–K6' hold; agreement 100 %; kept historical R0 controls reproduce; all scored §7
  expectations realised (including tolerated rows under K3' and the P1 block under K4'; no reclassification).
  Diagnostic observations alone add no acceptance conditions; invalid construction/label verification instead
  prevents a complete verdict.
- **`GEOM03_NO_GO`** — run completed, ≥ 1 criterion fails with valid data; M3b does not adopt; roadmap fallback is
  a registered R0-clean fixed set (selection bias recorded) or parent choice; no second attempt.
- **`GEOM03_INCOMPLETE`** — budget stop after launch, implementation disagreement/errors, halo-invalid scored rows,
  `k5_degenerate`, empty-input gap, or label ambiguity; no partial scoring.

## 11. Budgets and resource states

One local process, single-threaded; limits ≤ 200 rows, ≤ 2 h wall, ≤ 3 GiB RSS. Active FID OpenFOAM jobs have
absolute priority; no solver work here. **Before freeze and again before launch:** FID active or load > 4 → do
not launch; status **`WAITING_FOR_RESOURCES`** (preparation state, no attempt consumed, not a result). Only a
frozen attempt stopped by budget mid-run yields `INCOMPLETE`.

## 12. REQUIRED_BEFORE_FREEZE (explicit remaining design work)

Resolved by existing source inspection: v18 shape/dtype/origin/h; policy `max_components = null` and solid
26-neighbourhood; `LENGTH_TOLERANCE_M = 1e-9 m`; empty/no-erosion behavior (§2). Source hashes are in the
preparation binding file. The exploratory study uses seed 20261020; the proposed seed is 20261022. Seed
inequality alone does not demonstrate that all generated geometry/phase bytes will be disjoint.

1. Bind exact signed-distance formulas, dimensions, orientations, positions, parent states, nonempty
   frozen-node masks and each expected node/dense-label triple. Current shape descriptions do not fully
   determine bytes. Define the empty frozen-mask treatment explicitly; do not infer a passing infinity.
2. Resolve K5's spanning-array boundary and P1 contract prospectively. The ordinary finite-body halo rule
   cannot simply be applied to spanning slabs. Any chosen finite-array convention must be shared by the
   study and checker, documented in the claim, and reviewed before freeze; no data-based exception.
3. Resolve K1(b)'s coverage: its current analytic thickness/translation/pitch combinations do not cover the
   non-SDF linear phi-space mode combinations of WIDTH-RULE D3. Bind a disjoint combination protocol or
   explicitly narrow the claim and reconcile that narrowing with D-3 before attempting adoption.
4. Pin historical-control source hashes and recorded R0 statuses; drop unverifiable optional rows (§8).
5. Implement the two scripts and one test file in §9. Freeze exact enumeration and byte hashes; check
   disjointness from visible exploratory inputs without using R3 output to choose new labels or cases.

**This draft is not ready for freeze or held-out execution.** The items above, one formal plan review with
three angles and one subsequent source review remain required. The author revisions and incomplete draft
review attempts during preparation do not satisfy those formal review gates. No fixture, seed or study
step has been run.

## 13. Artifacts and freeze flow

- `docs/evidence/geom03_2026_10_22/registration.json` at freeze: SHA-256 of this document, `geom03_run.py`,
  `geom03_check.py`, `tests/test_geom03.py`, seeds `20261022`, phase lists (`P8`, `Q2`), §12 pinned values,
  python/numpy/scipy versions; committed in the same freeze commit as the code it hashes.
- Run artifacts (append-only): `rows.jsonl` (per row: phi SHA-256 Fortran-order, both paths' statuses, labels, D,
  halo flag, R0 descriptive column), `results.json` (K tallies, agreement counts, verdict), `stop_reason.json`.
- Freeze flow (parent-owned): three-angle plan review → implementation and source review → freeze commit (authorises the single
  attempt) → run → results commit → ledger/STATE update by parent only; until that commit everything is
  reviewable/mutable by review, not by a runner.
