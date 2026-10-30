# SCREEN-01 P0 exploratory pool prescreen (geometry only) — 2026-10-30

**Evidence class: solver-free geometry / lattice-representability of candidate states on the v18 parent; `EXPLORATORY` (pre-registration).** No solver ran, no force exists, nothing here feeds a flag, threshold or gate. Registration draft: [`docs/screen01_registration_2026_10_30.md`](../../../screen01_registration_2026_10_30.md) §3.3-3.4; decisions: [`../decision_memo.md`](../decision_memo.md) D3-D4. Produced in the registration worktree (branch `exp/screen01-registration-2026-10-30`) at integration commit `46bcd619990e3ab7f5f75f847d39f574c50cab0d`; nothing committed by this run.

## What was run
Script: [`scripts/screen01/screen01_pool.py`](../../../../scripts/screen01/screen01_pool.py) (SHA-256 `00c04625f7269a43148f2126b341174e43c99253560fd7daea5ee153ae501402`), which reuses `scripts/fid01/fid01_designs.py` unchanged (`work` = the MODE-01 v18 gate stack: 13 GEOM-02 v2 gates incl. R0 `min_feature_width`, P22-v2, 10 % smoothed-volume band, clearance 0.15 m, unmeasured = fail, R3 descriptive; `_x1` = r = 8 STL export + X1 practical gate in double and float32). Code fingerprint of the cached rows (fid01_designs dependencies + this script): `9a7e02fc93529576c26b2c67d9f4c4c3bfcd82984c1000a6b452ffef389f6727`. Python 3.12.13, numpy 2.5.2, scipy 1.18.1; 4 worker processes on a 10-core machine that was also running other work (load average about 3 before the run).

Commands (from the worktree root, `.venv/bin/python`):
```
scripts/screen01/screen01_pool.py gen
scripts/screen01/screen01_pool.py all --pools axial manual rs_pitch_camber_reflex rand5 --limit 48 --workers 4     # run 1, stopped after the subset
scripts/screen01/screen01_pool.py prescreen --pools axial manual rs_pitch_camber_reflex --workers 4                # cached rows -> rows.jsonl, summary
scripts/screen01/screen01_pool.py x1 --pools axial manual rs_pitch_camber_reflex --workers 4
scripts/screen01/screen01_pool.py prescreen --pools axial manual rs_pitch_camber_reflex rand5 --limit 16 --workers 4
scripts/screen01/screen01_pool.py x1 --pools axial manual rs_pitch_camber_reflex rand5 --workers 4
scripts/screen01/screen01_pool.py design
```
Run 1 started 2026-10-30T14:08:13Z and was stopped at 15:19:24Z after the 75th row (axial 10, manual 1, subset 64; 71.2 min), because the full `--limit 48` random prefix would have taken about 2 h under the machine load; the 4 random-pool evaluations then in flight were discarded (never written). Phase 2 (15:20:19Z-15:49:09Z, 28.8 min): cached summary, X1 of the 38 gate-clean states (about 16 min), the first 16 random-pool points (669 s), X1 of their 3 gate-clean members (86 s), design check. Per-member gate evaluation: 110-140 s alone (timing probe before the run), median per worker with 4 workers 238 s (subset), 169 s (random); X1 export about 55 s alone. Pool generation itself is instantaneous.

## Pools generated (`pools.json`)
Scrambled Sobol (`scipy.stats.qmc.Sobol(scramble=True, seed)`, `u = 2 x - 1`, amplitude = `u A*`, rounded to 1e-3): `axial` (10), `manual` (1), ten 3-mode subsets of (pitch, camber, reflex, twist, sweep) with 64 points each (seed 20261030 + subset index), `rand5` with 256 points in 5-D (seed 20261031). A* = pitch 3.1 deg, camber 19.7 mm, reflex 29.3 mm, twist 1.1 deg, sweep 11.3 mm; heave fixed at 0. **Evaluated here:** `axial`, `manual`, `rs_pitch_camber_reflex` (the subset the visible M2/FID values predict for stage 1, registration §8) and the first 16 points of `rand5`. The other nine subsets and the rest of `rand5` are not evaluated (they run before freeze 1).

## Counts
| pool | evaluated | gate-clean | failing gates (a state may fail several) | X1 pass of gate-clean | admissible |
| --- | --- | --- | --- | --- | --- |
| axial | 10 | 10 | - | 10 | 10 |
| manual | 1 | 1 | - | 1 | 1 |
| rs_pitch_camber_reflex | 64 | 27 (42 %) | min_feature_width 37; export_surface_integrity 7; surface_self_intersection 7 (always together with the width failure) | 27 | 27 |
| rand5 (first 16) | 16 | 3 (19 %) | min_feature_width 13; export_surface_integrity 1; surface_self_intersection 1 | 3 | 3 |
R3 (opening defect, descriptive) passes every one of the 91 evaluated states; P22-v2, the smoothed-volume band and the clearance margin pass on all of them (as in MODE-01). The binding gate is again R0 `min_feature_width` (the one-cell occupancy artefact of WIDTH-RULE / GEOM-03), which rejects 58 % of the joint 3-mode points and 81 % of the 5-mode points in these samples. Random-pool projection: about 117 sequence points for 22 admissible members (3 of 16 is a wide binomial interval, roughly 4-46 %, i.e. 50-550 points; the registered cap is 512).

## Response-surface design check (`design_check.json`, subset pitch/camber/reflex)
Rule: base = parent + 6 axial points; 9 admissible pool members added by greedy Bayesian D-optimality (`logdet(X'X + 1e-6 I)`) on the full-quadratic columns. Result: 16 design points, rank 10 on the 10-column form (condition number 7.55; the 15-point face-centred central composite reference has 4.40); on the registration's 9-column no-intercept form (15 non-parent points) rank 9, condition number 4.22 (bound 20): **the planned design is full rank before any force**. Rank of all 27 survivors + base: 10. Trust region (convex hull of the 16 design points): 45 % of the box volume; 23 of the 27 survivors inside (so up to 14 unevaluated admissible members are available as proposals), 7 of the 27 three-level grid points inside, 0 of the 8 box corners inside. Chosen design points (names in the sorted-key form `fid01_designs.name`):
- `v18__camber_m19.077_pitch_m2.918_reflex_p14.25`  u = (-0.941, -0.968, +0.486)
- `v18__camber_p16.831_pitch_p1.042_reflex_p28.057`  u = (+0.336, +0.854, +0.958)
- `v18__camber_p13.207_pitch_m2.041_reflex_p18.258`  u = (-0.658, +0.670, +0.623)
- `v18__camber_m18.127_pitch_p2.493_reflex_p16.254`  u = (+0.804, -0.920, +0.555)
- `v18__camber_p16.257_pitch_m1.812_reflex_m17.01`  u = (-0.585, +0.825, -0.581)
- `v18__camber_m11.007_pitch_m2.494_reflex_m13.689`  u = (-0.805, -0.559, -0.467)
- `v18__camber_p15.947_pitch_p2.043_reflex_m11.687`  u = (+0.659, +0.809, -0.399)
- `v18__camber_m15.541_pitch_m1.594_reflex_p25.062`  u = (-0.514, -0.789, +0.855)
- `v18__camber_m1.628_pitch_p1.884_reflex_p26.847`  u = (+0.608, -0.083, +0.916)

## Survivors (gate-clean and X1-clean)
`rs_pitch_camber_reflex` (27): `v18__camber_m11.007_pitch_m2.494_reflex_m13.689`, `v18__camber_p16.257_pitch_m1.812_reflex_m17.01`, `v18__camber_m16.433_pitch_p2.31_reflex_p4.633`, `v18__camber_m7.715_pitch_m1.223_reflex_p14.671`, `v18__camber_p14.634_pitch_m1.043_reflex_m1.458`, `v18__camber_p19.148_pitch_m0.295_reflex_p18.527`, `v18__camber_m1.628_pitch_p1.884_reflex_p26.847`, `v18__camber_m12.667_pitch_m0.777_reflex_p7.652`, `v18__camber_m9.256_pitch_p1.067_reflex_p13.128`, `v18__camber_p15.947_pitch_p2.043_reflex_m11.687`, `v18__camber_m15.541_pitch_m1.594_reflex_p25.062`, `v18__camber_p11.523_pitch_m2.663_reflex_p6.637`, `v18__camber_m2.675_pitch_m0.526_reflex_m5.187`, `v18__camber_p9.865_pitch_m0.451_reflex_m19.545`, `v18__camber_m10.388_pitch_p0.174_reflex_p2.533`, `v18__camber_p8.236_pitch_m1.716_reflex_p10.693`, `v18__camber_p16.831_pitch_p1.042_reflex_p28.057`, `v18__camber_m16.966_pitch_m1.516_reflex_m8.441`, `v18__camber_p0.494_pitch_m0.946_reflex_p22.582`, `v18__camber_m18.127_pitch_p2.493_reflex_p16.254`, `v18__camber_p4.97_pitch_m0.005_reflex_m11.925`, `v18__camber_m5.414_pitch_p0.524_reflex_p24.355`, `v18__camber_m19.077_pitch_m2.918_reflex_p14.25`, `v18__camber_p13.207_pitch_m2.041_reflex_p18.258`, `v18__camber_p2.007_pitch_p1.395_reflex_p6.388`, `v18__camber_m2.221_pitch_m1.067_reflex_m15.928`, `v18__camber_p15.299_pitch_m1.298_reflex_p0.876`

`rand5` first 16, in sequence order (3): `v18__camber_m13.331_pitch_p0.992_reflex_p17.636_sweep_m7.887_twist_m0.639`, `v18__camber_m8.683_pitch_p3.076_reflex_m25.033_sweep_m3.022_twist_p0.081`, `v18__camber_m0.434_pitch_p0.189_reflex_m9.599_sweep_p2.615_twist_m0.255`

## Caveats
- One subset and a 16-point random prefix only; the admissible fractions are sample estimates, not the fractions of the other subsets (shear-dominated subsets with twist/sweep may fail R0 more often, MODE-01 README).
- Admissibility is at the native placement (as FID §3.3); it is not re-evaluated at the exploration or sealed phases.
- The subset evaluated is the one predicted from visible force values (registration §8); the rule itself is applied blind after G1 and every subset gets a frozen design before freeze 1.
- STL blobs of the 41 X1-clean states are under `work/screen01_pool_prescreen/stl/` (41 files, 1320 MB, gitignored); their SHA-256 are in `x1.json`. Per-row caches: `work/screen01_pool_prescreen/rows/`.

## Files and hashes (SHA-256)
| file | sha256 |
| --- | --- |
| `pools.json` | `fc44c5fbd27aca21c1318b077d6e0bcf9fcc207629cb94600a615c837e985d37` |
| `rows.jsonl` | `2f5e7ae41f019f8b193de1706bd8073ef74deee1c19d8171e6b5c668310e1512` |
| `prescreen_summary.json` | `7cffd9bfe1dbb530c83140068b93068e0ade02b49ea745d16fda18e8f757b044` |
| `x1.json` | `0482fd18d1dc53968babc0eb41c5a36d9bb7f2859fe2b911e86f58ad6ee2043a` |
| `design_check.json` | `006866a7ba0f91fb071a9ccfceef3c997396c8e6076d67f58f92ae4782c09679` |
| `scripts/screen01/screen01_pool.py` | `00c04625f7269a43148f2126b341174e43c99253560fd7daea5ee153ae501402` |
| `scripts/screen01/screen01_oc.py` | `261defa411850d937f82f35992b389419ec99546209d47b3af7280b75c299fa1` |
| `docs/evidence/screen01_2026_10_30/oc.json` | `8ba4eaaca86410ca3873312c5f684c695cc574a28006d8cd8bc30d164d750c32` |
| `scripts/fid01/fid01_designs.py` | `4eef7ff8c0ae19d04b2cdaf73fc6e25597704ff75f50721980b3c2a280da2116` |
