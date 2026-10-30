# v18 analytic plate genesis (#60, S0 + S1)

**Registration status: `EXPLORATORY_COMMITTED` (PROC-01).** Claim ceiling: geometry facts of one analytic parent on the v17 lattice. No solver ran; nothing here feeds a flag, threshold, gate or claim. M2 (#61) pins these bytes in its own registration. All qualification flags stay false; `shape_update_allowed=false`.
Plan: [`docs/v18_mode01_plan_2026_10_19.md`](../../v18_mode01_plan_2026_10_19.md) (rev. 2, committed in `58a965fb` before this run). Decision: B1 = v18 analytic plate (user, 2026-10-19, #60).

**Visible before this run:** the rev. 1 scratch probes and the committed S0 probe (`tip_probe.json`), which chose the tip shape and offset on the same gates (disclosed in plan §1); the parent's gate verdict at t = 0.1181 m with round tips (all 13 pass) from a dry run.

## Parent
Stadium section (t = 0.1153 m, round edges r = t/2) extruded over |y| <= 0.4375 m with flat tips on the cell-centre plane; bounding box = the v17 baseline solid-cell box (x -0.6..0.55, z -0.25..0.25 m), alpha 20.395 deg, chord 1.2192 m, span 0.875 m. Exact parameters in `genesis.json` (`parameters`).

| Identity | SHA-256 |
| --- | --- |
| state | `e7376e3576a045daa4c62353052890c43b4ed8b4562033c889cb1a4580d902bd` |
| NPZ (`v18_parent.npz`) | `36967c90cb48b7fe3475436098b138d4e7998212defb6dcb61bf8cefc52d5890` |
| phi Fortran order (`v18_parent.phi_f4_fortran.raw`) | `29d53b2318c54548da321f265aa2102d59e24d96bbd04fb2dd70d62fbc10c82a` |
| phi C order | `0197e688bf41c87407705e9fee3c78392230fb7edf71b3f58e0aa08c65dceebe` |
| source (parameter spec) | `63fe4730ad6216fe4d224ac7f729603f2587bf1b28c507ef3070bbd2aaf30e0e` |

## Result
- All 13 GEOM-02 v2 gates pass (parent as its own parent), P22-v2 N_phi 7544 <= 8272 (slack 728, 8.8 %; not binding by design), smoothed volume -0.009 % vs the v17 baseline, clearance margin 0.351 m, crossing-slope failing nodes 0, no solid outside the design mask, end layers j = 14/50 at +12.5 mm.
- Ride height (lowest zero level, lattice estimate) 0.6505 m above the ground (analytic 0.65 m, as v17). Continuum volume 0.1205 m^3, sharp 0.1179 m^3 (v17 0.12925). Planform 1.067 m^2, frontal (x) 0.4375 m^2.
- 212 end cells have corner mean exactly 0 (the flat tips on the cell-centre plane; counted fluid, unchanged by every x-z mode); the hard-count invariance radius is therefore 0 (reported, not used). 420 nodes with |phi| < 1 mm (generic inclined faces, no exact zeros).
- S0 probe (`tip_probe.json`, seed 20261019, 40 rigid placements dx, dz within 40 mm, dalpha within 5 deg, t within 8 %): flat tips 0/40 states with crossing-slope failures and 16/40 with min_feature_width below 31.25 mm; rev. 1 round tips 1/40 and 33/40. The width failures are one-cell nubs of the cell occupancy at the rounded leading/trailing edges (radius 2.4 h).

## Reproduce
`python scripts/v18_tip_probe.py` (writes `tip_probe.json`), `python scripts/sdf_native_genesis_v18_2026_10.py` (refuses to overwrite different bytes) and `--check` (rebuilds and compares; `environment` excluded). Tests: `tests/test_v18_plate.py`. `SHA256SUMS` is repo-root relative and includes the scripts.
