# MODE-01 on the v18 analytic plate (#60, S2): solver-free prescreen and basis proposal

**Registration status: `EXPLORATORY_COMMITTED` (PROC-01).** Claim ceiling: geometry and lattice-representability facts of 99 states on one analytic parent. No solver ran; nothing here feeds a flag, threshold, gate, `shape_update_allowed` or a downforce claim. The basis below is a **proposal**: it becomes binding only in the M2 (#61) registration, which re-derives gate cleanliness on its own bytes. All qualification flags stay false.
Plan: [`docs/v18_mode01_plan_2026_10_19.md`](../../v18_mode01_plan_2026_10_19.md) rev. 2 (committed in `58a965fb` before this run; the basis rule §5 was applied once by `basis()` in `scripts/mode01_v18_prescreen.py`). Parent: [`../v18_genesis_2026_10_19/`](../v18_genesis_2026_10_19/README.md) (phi Fortran SHA `29d53b23…`).
**Visible before this run:** plan §1 disclosure (the tip shape was tuned on the same gates under rigid placements; top-of-ladder crossing-slope counts of the rev. 1 round-tip modes; 9 round-tip full-gate runs by the numerical reviewer). Not visible: any gate result of the rev. 2 ladders.

## Verdict: `V18_BASIS_READY`
| Basis member | Class | A* (both signs gate-clean) | max interface change | support | gate-clean ladder points |
| --- | --- | --- | --- | --- | --- |
| heave | wide | 31.1 mm | 31.0 mm | 0.955 | 13.7, 31.1 |
| pitch | wide | 3.1 deg | 29.8 mm | 0.863 | 0.7, 1.3, 3.1 |
| camber | wide | 19.7 mm | 13.1 mm | 0.863 | 11.3, 19.7 |
| reflex | wide | 29.3 mm | 11.7 mm | 0.842 | 11.3, 19.7, 29.3 (41.1 only +) |
| twist | wide | 1.1 deg | 6.5 mm | 0.617 | 1.1 (2.3 only +) |
| sweep | wide | 11.3 mm | 6.9 mm | 0.636 | 11.3 |
| surge | control | 31.1 mm | 31.0 mm | 0.957 | 13.7, 21.3, 31.1 |
Six distinct wide members (the minimum the rule requires; |cos| of the symmetric phi-differences at A* all <= 0.3, singular values 0.88-1.11), one control, and the support probes `offset_s400` (2 mm both signs, 5 mm +), `offset_s125` (-2, -5 mm only) and `offset_s050` (2 and 5 mm, both signs). Reference D0 is gate-clean outward only (+1, +2, +3 mm). Proposed basis (7): heave, pitch, camber, reflex, twist, sweep, surge.

## Not in the basis, with the reason
| Mode | Outcome | Reason |
| --- | --- | --- |
| dihedral | no gate-clean point (4 congruent pairs) | `min_feature_width` at every point (+ export/self-intersection at 29.3 mm) |
| twist_anti (control) | no gate-clean point (3 congruent pairs) | `min_feature_width` at every point |
| thick_chord | gates clean at e = +-0.025 and +-0.1 (0.05 only -) | support at -e is 0.07-0.11 < 0.5: the leading/trailing edges move 15-65 mm, so the MODE-01 support threshold (10 % of the band maximum) excludes the 1.3-6 mm face motion. A definition artefact, kept as declared (plan §8 N4) |
| corrugation | +2 mm only | `min_feature_width` otherwise |
| D0 inward, offset_s400 -5 | fail | `near_zero_gradient_band` (8-20 nodes): an inward offset moves the flat tips off the cell-centre plane (plan §3.3), the predicted failure mode |

## Gate statistics (99 states)
48 states fail at least one gate: `min_feature_width` 44, `export_surface_integrity` + `surface_self_intersection` 6 (always with a width failure), `near_zero_gradient_band` 4 (the inward-offset tips above). P22-v2, the smoothed-volume band and the clearance margin pass on all 99 (N_phi 7068-8180, slack >= 92; smoothed volume within +-7.6 %). The rigid and shear modes change N_phi by up to -3.6 % and the smoothed volume by at most +0.5 % (thick_chord +-2.8 %); continuum volume is exact for every analytic mode. Gated bytes = the harness reconstruction (`construct_state` with `d/max|d|`), at most 1.9e-9 m from the analytic values.
**Main finding:** on a smooth analytic body the binding gate is the GEOM-02 `min_feature_width` estimate (2·EDT ridge on 4x-repeated cell occupancy), which flags one-cell nubs at the rounded edges (radius 2.4 h) and fails at about 40-50 % of sub-cell placements (S0: 16/40; here 44 of 98 non-parent states, 39 of the 76 wide and control states). It is not continuous in the placement, so which ladder points pass is close to a coin toss per sub-cell phase; the six members are gate-clean at the listed points only, and mode combinations (M3b) or other amplitudes are untested. Lattice-congruent +-A pairs (heave, surge, camber, dihedral, sweep, twist_anti: identical N_phi and verdicts by symmetry) count as one gate sample.

## Files
`prescreen.json` (meta, 99 states with gate status, N_phi, support, volume, eikonal, lowest zero-level z, harness step, phi SHA-256 of the gated bytes, and `basis`), `prescreen_table.md`. Reproduce: `python scripts/mode01_v18_prescreen.py --workers 7` (about 75 min on 10 cores). `SHA256SUMS` is repo-root relative.
