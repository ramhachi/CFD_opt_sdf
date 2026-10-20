# WIDTH-RULE: why `min_feature_width` fails on the smooth v18 plate, and four placement-robust candidates

**Registration status: `EXPLORATORY_COMMITTED` (PROC-01).** Solver-free, local CPU only (no Kaggle). Claim ceiling: geometry and lattice-representability facts and a proposal. Nothing here changes a gate, gate profile, policy, flag or `shape_update_allowed`; the registered `min_feature_width` (R0) stays in force. Adoption of any rule happens only in the M3a (#62) / M3b (#64) registrations under PROC-01. All qualification flags stay false.
Plan: [`docs/width_rule_plan_2026_10_20.md`](../../width_rule_plan_2026_10_20.md) rev. 2. It was committed with the script and tests in `233a1a4f` before the run, and records an adversarial review (numerical and governance angles) and the decision on each of its 13 findings. The compute deviation (§9) was committed in `3c4295ce` before the rerun; the first run was stopped under machine-wide thrashing, and none of its rows were written or read. Decision proposal: [`docs/width_rule_decision_2026_10_20.md`](../../width_rule_decision_2026_10_20.md).
**Visible before the run:** see plan §2 (a scratch prototype of the parent sweep, the reviewer's scratch numbers, the unit-test fixtures).

## Verdict: `NO_CANDIDATE_MEETS_K1_K6` (closest: R3)
| rule | K1 v18 + combinations + round tips not passing | K2 thin draws passed | K3 thick draws not passed | K4 rim mismatch passed | K4 historical width failures passed with no other failing gate | aligned-slab 50 % width | K5 | K6 | short (l <= 1.5h) not passing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 registered | 1255/1954 | 0/171 | 141/144 | 0 | 0 | 1.469h | (ref.) | yes | 114/114 |
| R1 SDF ridge | 0/1954 | 37/171 | 6/144 | 2 | 3 | 2.219h | yes | **no** (46 thin draws pass with phi x 2) | 2/114 |
| R2 phase majority | 366/384 | 0/171 | 144/144 | 0 | 0 | 1.719h | yes | yes | 114/114 |
| **R3 opening defect, trilinear body** | **0/1954** | 6/171 | **0/144** | 2 | 4 | 1.594h | yes | yes | 29/114 |
| R4 opening defect, cell occupancy | 917/1954 | 2/171 | 130/144 | 0 | 0 | 1.469h | yes | yes | 110/114 |

Checks: `valid`. All 99 phase-0 v18 states reproduce their recorded phi SHA-256 and R0 status. The 40 round-tip placements reproduce their recorded R0 width. All 118 MODE-01 OPT-01 v1 / regen6p25 states reproduce their phi SHA-256 and R0 status. Both REINIT-04 outputs reproduce their state SHA-256 and R0 status. There were no errors. R2 was evaluated on 384 of the 1,954 K1 states (plan §9).

**Where R3, the closest candidate, misses the frozen bar (the explanations are post hoc and descriptive, not a re-scoring):**
- **K2 (6 draws).** All six are 0.5h necks (`neck_d0.5_l4`). In each of the six, the represented body is **two components**: the trilinear zero level does not connect the balls, and the cell occupancy is also 2 components. The neck is broken into stubs of at most 0.9h. The "held" criterion (one lattice node inside the thin part) did not guarantee a connected feature. In a fixed-topology step (`allowed_events = ()`), such a split fails `topology_change_classification` and `component_connectivity`. Every 0.5h neck that stays connected or splits into 3–4 pieces fails R3.
- **K4 rim mismatch (OPT-01 v1 `surge +-25`).** R3's defect is 15–19 mm. The mechanism needs the zero level on frozen nodes: on the OPT-01 v1 parent, 652 non-active nodes at y = +-0.45 m have |phi| < 1 mm (down to 1.2e-8 m). On the v18 parent, the smallest |phi| over non-active nodes is 12.5 mm = h/2 (flat tips on the cell-centre plane). The mechanism cannot occur on v18 while that margin holds.
- **K4 thinned slab (OPT-01 v1 `thickness -3, -5`).** The labels were assigned before the run as "near the limit, no expectation". Their SDF-ridge width (R1) is 44 and 40 mm, above the registered 37.5 mm. Their only recorded gate failure is R0's one-cell value. Under the frozen K4 they still count as misses.

R1 also passes every v18 state, but it reads phi units (K6: 46 thin draws pass when phi is doubled; the eikonal gate checks only the median), misses 37 thin draws (tapers, necks, slots) and fails 6 thick ones. R2 fails the registered parent itself at phase 0 (4/8), as predicted. R4 inherits the occupancy staircase: one-cell occupancy nubs have an opening defect of 0.75–1.15h, so R4 sits at its tolerance.

## Decomposition: what fails on v18 and why
- **Not physically thin.** Every v18 state is at least 103.8 mm thick. The nominal t is 115.3 mm = 4.6h. The thinnest states are thick_chord −0.1 at 103.8 mm, the 5 mm inward offsets and corrugation at 105.3 mm, and D0 −3 mm at 109.3 mm. Its convex radii are >= 2.3h, apart from the right-angle tip edges that the registered parent passes. The SDF ridge (R1) measures >= 90.1 mm on every v18 state and phase. R3's largest defect over all 1,824 v18 (state, phase) pairs is 12.5 mm (solid) and 6.25 mm (void).
- **It is the cell occupancy.** R0 fails 1,089 of 1,824 v18 (state, phase) pairs (60 %), always with the value 25.0 mm, exactly one cell. Parent: 34/64 phases with the tips on the cell-centre plane, 148/192 with the tips moved off it. Locations (pairs containing the location): flat tip 890, leading-edge round 645, trailing-edge round 645, face 370. Only 30 pairs fail at faces alone (corrugation 19, offset 9, sweep 2). The occupancy opening defect (R4) of every R0 failure is 18.8–28.6 mm (0.75–1.15h). These are one-cell protrusions of the cell-wise binarisation. The pre-stated strict form "<= 1.0 cell" is rejected for 825 of 1,089, whose far corner sits up to 15 % beyond one cell.
- **Placement and orientation.** At fixed amplitude the verdict changes with the sub-cell phase (e.g. heave, pitch, camber, surge: some phases pass, others fail). No mode × amplitude passes at all 16 phases. The shear modes (twist >= 2.3 deg, dihedral and sweep >= 19.7 mm, twist_anti) fail at every phase: they tilt the flat tip edges against the lattice, so the occupancy staircase runs along the whole tip.
- **Optimiser-like states.** On 200 linear phi-space combinations of 2–3 proposed basis members (c ~ U(−1, 1) × A*), R0 fails 190 (95 %). It fails all 50 of the same with ±h/16 phi noise. R1 and R3 pass all 250 (R3 max defect 18.8 mm; R1 min 44.5 mm, close to its 43.75 mm guard). Under R0, a screening or response-surface step on v18 would reject almost every candidate for a lattice artefact.
- **Historical states.** Of the 57 recorded width failures (OPT-01 v1, regen6p25, REINIT-04), R3 still fails 2: the reinitialised LOWDIM-03 parent (defect 32.5 mm) and one tie-plateau state. The tie-plateau states R3 passes still fail their bundle through `near_zero_gradient_band` (and `sdf_distance_property`/`volume_semantics`), the gates designated for that mechanism. R3 is stricter than R0 on the rough grad03 fields (D1_filtered, P1: defect 25.8 mm = unmeasured, while R0 passes).

## Synthetic suite (true widths known; `synthetic_table.md`)
Random rotation and sub-cell translation, near-exact SDF.
- **R0** fails every draw of every shape, thin or thick: rotated boxes, balls R = 3h, the v18-like stadium. The only exceptions are a few balls. R0 returns exactly 25.0 mm for a one-cell nub and for a one-cell sheet alike, so no threshold-only variant can separate them.
- **R3** fails:
  - every slab up to 1.25h, 14/16 at 1.5h, none from 1.75h;
  - every fin and neck of 1h width at length >= 2h (0.5h necks: see K2);
  - every slot up to 1h;
  - wedges of 20/40 deg (16/15 of 16).
- **R3** passes:
  - 60/90-deg wedges, all thick shapes, the 2h stadium and balls R >= 1.5h;
  - short features of length <= 1h (its tolerance by design, 29/114 short draws not passing).
- **Aligned slabs (32 phases):** R0 50 % at 1.469h; R3 at 1.594h (0 % failing from 1.75h); R1 at 2.219h (stricter, its crest is sampled at nodes).

## Files
- `summary.json`: checks, criteria, per-rule historical rows, aligned-slab fractions.
- `v18_phase_sweep.json`: D1 parent 256 phases, D2 98 states × 16 phases, D3 250 combinations, 40 round tips.
- `synthetic.json`: 41 shapes × 16 draws, 11 aligned slabs × 32 phases.
- `historical.json`: 77 + 41 MODE-01 states, 2 REINIT-04.
- Tables: `criteria_table.md`, `v18_phase_sweep_table.md`, `v18_combos_table.md`, `synthetic_table.md`, `historical_table.md`.
- `SHA256SUMS`: repo-root relative.

Code: `scripts/width_rule_study.py`; tests: `tests/test_width_rule.py` (4 pass).

Reproduce: `python scripts/width_rule_study.py --workers 5`. Rows are cached in the ignored `work/width_rule_2026_10_20/rows.jsonl`, so a restart resumes. About 3.5 h on 5 workers under load.
