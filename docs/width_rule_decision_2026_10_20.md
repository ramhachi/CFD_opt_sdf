# Width rule for smooth bodies in M3a (#62) and M3b (#64): decision proposal (2026-10-20)

Status: **PROPOSAL, not adopted.** A rule is adopted only by the M3a / M3b registrations under PROC-01 (one three-angle plan review and one source review per study). Evidence: [WIDTH-RULE](evidence/width_rule_2026_10_20/README.md) (`EXPLORATORY_COMMITTED`, solver-free); plan [`width_rule_plan_2026_10_20.md`](width_rule_plan_2026_10_20.md). This answers the UNC-01 draft §9 TODO 0 ("M3 must decide how a smooth-body width rule is handled before any optimiser runs on v18") with a proposal. The registered GEOM-02 v2 gate stack, its profile and policy, the flags and `shape_update_allowed=false` are unchanged.

## 1. Problem
GEOM-02 `min_feature_width` (R0) is a **lattice representability limit**: 1.5h = 37.5 mm, guard h/4. It is explicitly not a manufacturing or physical minimum (GEOM-02 plan item 1 and A5; policy `d4cd9aa4…`). R0 binarises cells (trilinear cell-centre value < 0), repeats each cell 4x, and takes 2 × the smallest local maximum of the Euclidean distance transform.

On a smooth body this binarisation grows one-cell protrusions wherever the surface curves or tilts against the lattice. R0 returns exactly 25.0 mm on all 1,089 of its v18 failures. The failures sit at the leading/trailing-edge rounds, at the flat-tip edges, and at faces of rough modes.

The v18 plate is at least 103.8 mm thick in every state. Its SDF ridge is >= 90 mm. R0 still fails:
- 60 % of v18 (state, sub-cell phase) pairs;
- 34/64 parent placements with the tips on the cell-centre plane;
- **190 of 200 optimiser-like linear combinations** of 2–3 proposed basis members.

The verdict is placement noise. It also follows mode orientation: shear modes that tilt the tip edges fail at every phase. An optimiser gated by R0 would select lattice-lucky shapes.

## 2. Evidence in one table
Pre-registered criteria K1–K6 (plan §6):
- K1: no artefact failures on v18 states and combinations;
- K2: fails thin features held by the lattice;
- K3: passes thick shapes;
- K4: historical failures;
- K5: not looser than R0 on aligned slabs;
- K6: invariant to phi scale.

| rule | K1 | K2 | K3 | K4 | K5 | K6 |
| --- | --- | --- | --- | --- | --- | --- |
| R0 registered (cell occupancy, 2 x EDT ridge) | 1255/1954 fail | ok | 141/144 fail | ok | ref. | ok |
| R1 SDF ridge on phi nodes | ok | 37 miss | 6 fail | rim mismatch passes | ok | **fails** (phi units) |
| R2 R0 majority over 8 sub-cell resamplings | 366/384 fail | ok | 144/144 fail | ok | ok | ok |
| **R3 opening defect of the trilinear body** | **ok (0/1954)** | 6 miss | **ok** | rim mismatch, thinned slab pass | ok (1.594h vs 1.469h) | ok |
| R4 opening defect of the cell occupancy | 917/1954 fail | 2 miss | 130/144 fail | ok | ok | ok |

**No candidate met all six** (`NO_CANDIDATE_MEETS_K1_K6`). R3 is the only one that removes the artefact (K1) and still passes thick and fails thin shapes on the synthetic suite. Its misses, described after the run (not re-scored):
- **6 K2 draws.** All are 0.5h necks that the lattice does not hold as a connection: the represented body is 2 components.
- **K4 rim mismatch** (OPT-01 v1 `surge +-25`). It needs the zero level on frozen nodes: 652 nodes with |phi| < 1 mm on that parent. The v18 parent has |phi| >= h/2 on all frozen nodes.
- **K4 thinned slab** (`thickness -3/-5`). SDF ridge width 44 and 40 mm, above the registered 37.5 mm.

## 3. Proposal
**D-1 M3a (FID-01, #62; fixed designs, no optimiser): keep R0 unchanged.**
- Choose the >= 12 designs only among states that pass all 13 registered gates at the registered lattice (as M2 does with the MODE-01 points).
- Record R3 as a descriptive column.
- Why:
  - with fixed designs the artefact only narrows the admissible set, it does not steer a search;
  - keeping R0 keeps M2 → M3a comparable;
  - on every v18 state measured here (1,824 single-mode pairs and 250 combinations) R3 passes, so an R0-clean M3a design is also admissible under the M3b rule proposed below.

**D-2 M3b (SCREEN-01, #64; continuous amplitudes, combinations, response surface): R0 cannot be the admissibility rule on v18.** Proposed rule, registered as a new gate-contract version and a new content-addressed policy instance (GEOM-02 v2 and every past record unchanged):
- **`min_feature_width` := R3, the opening defect of the trilinear body.**
  - Body: B = {trilinear phi < 0} on the node-aligned h/4 refinement of the solid node box + 3 cells.
  - Erosion: E = {x in B : EDT_B(x) > r}, with r = minimum_solid_width_m / 2 = 0.75h.
  - Opening: O = {x : dist(x, E) <= r}.
  - Defect: D = max over B \ O of dist(x, O).
  - Thresholds: pass D <= h; unmeasured D <= 1.25h; fail beyond. The same applies to the void inside the crop. An empty solid is unmeasured; no void feature is pass.
  - R3 measures what the solver (`GridSDFBody` trilinear interpolant) and the export see, and depends only on the sign of phi.
- **P1 frozen-node margin (precondition):** min |phi| over non-active nodes >= h/2 for the parent and every state. v18 parent: exactly h/2. Excludes the rim-mismatch mechanism.
- **P2 fixed topology:** `allowed_events = ()` as now. A thin neck that breaks is a split and fails `component_connectivity` / `topology_change_classification`; this covers the 6 K2 misses.
- **Dual reporting:** R0 is computed and stored for every M3b state as a descriptive column, never as a gate.
- **Accepted risk, stated in the registration:** R3 tolerates material that no 1.5h ball reaches when it protrudes at most about one cell: short fins and bumps <= 1h, wedges wider than ~51 deg. R0 rejected such features only at placements where they showed as an occupancy cell. Where R3 and R0 differ in the other direction:
  - R3 is stricter on aligned slabs (50 % at 1.59h vs 1.47h) and on rough fields such as grad03 D1/P1.
  - R3 fails 20/40-deg wedges and passes 60/90-deg ones. R0 fails every wedge, including 90 deg, through the occupancy artefact.

**D-3 Validation before any optimiser run.** R3 + P1 + P2 did not pass a pre-registered bar here. The M3b registration therefore contains a registered (`REGISTERED_FROZEN`) validation of exactly this composite on disjoint data, with K1–K6 as written in the plan and these changes, fixed in the registration before the run:
- K2 counts a thin feature as held only if the lattice holds it connected;
- the K4 rim-mismatch item is replaced by P1;
- the thinned-slab labels come from the SDF width;
- new synthetic seeds, new combination seeds.

If it fails, M3b screens only R0-clean points on the registered lattice. It records the resulting selection bias, or it reopens the parent choice. No further exploratory tuning of r, tau or the refinement.

## 4. Not proposed, with the reason
- **Keep R0 for M3b:** rejects 95 % of optimiser-like candidates for a one-cell artefact; the admissible set would be a placement lottery.
- **Lower the threshold (scale with h):** R0 returns exactly one cell for a one-cell nub and for a genuine one-cell sheet, so any threshold that passes the nub passes the sheet (a pure relaxation).
- **R1 SDF ridge:** reads phi units (46 thin draws pass with phi doubled; the eikonal gate checks only the median), misses tapers, necks and slots (37 thin draws), fails 6 thick draws.
- **R2 phase majority:** fails the registered parent itself; the 8 sub-samples are correlated. Worst-of-8 is stricter than R0 and best-of-8 is a relaxation, both by construction.
- **R4 occupancy opening:** inherits the staircase (one-cell nubs measure 0.75–1.15h), fails K1 and K3.
- **Choosing a passing placement per state:** gaming the gate; not considered.

## 5. What this does not change
- M2 (UNC-01, #61) uses only MODE-01 points that pass R0 at the registered lattice and is unaffected.
- The v18 genesis, MODE-01 v18 records and `scripts/v18_plate.py` are untouched.
- No qualification flag and no `shape_update_allowed` change.
