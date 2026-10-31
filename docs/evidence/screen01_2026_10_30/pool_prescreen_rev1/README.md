# SCREEN-01 P0 record, revision 1 (geometry only) — 2026-10-30

**Evidence class: solver-free geometry / lattice-representability of candidate states on the v18 parent.** No solver ran, no force exists. Registration: [`docs/screen01_registration_2026_10_30.md`](../../../screen01_registration_2026_10_30.md) rev. 2 §3.3-3.4 and the P0 row of §2; decisions D2-D4 and D7 of [`../decision_memo.md`](../decision_memo.md); the rev. 0 record stays in [`../pool_prescreen/`](../pool_prescreen/README.md).

Two runs, same states and the same results:
- **Run 1 (2026-10-30, pre-source-review code)**, in the registration worktree at commit `901a491432a618cf8d584f1212b6fb72405f9cda`; its caches carried no code key (source review Q1). Its files are in git history at `db8732e0b87ab6264c057f2e03dd524e0c22a525` (hashes in the last table).
- **Run 2 (2026-10-30T21:40:36Z → 2026-10-31T00:16:40Z, the re-validation the registration requires before freeze 1)**, from empty caches (the run-1 cache was moved aside to `work/screen01_pool_prescreen_pre_rev2`) at commit `9b47ae67c6605cd8024899bef901a54a81840b80` (rev. 2; `screen01_pool.py` and its dependencies are unchanged at `db8732e0`), under `screen01_pool.fingerprint()` = `f5a5a95a74e3208a06280f634c405b3e55e578b1a5948c04c7b2bcf15a02473b` (SHA-256 over the 65 `DEPENDENCIES` files, listed in `summary.json`). The current `rows.jsonl`, `summary.json` and `design_check.json` are run 2; `p0.log` holds both runs. **This is the record freeze 1 binds.**

**Run 2 vs run 1, row by row:** 129 rows, same states in the same order; every field equal (admissibility, every gate status, gated phi SHA-256, STL SHA-256, volumes, chain check, P22-v2, support, eikonal statistics) except the code-key fields (run 1 `code_fingerprint` / `d_fingerprint`, run 2 `fingerprint`) and the wall times. `summary.json` differs only in timing, the new `fingerprint` / `dependencies` / `error_rows` (empty in every pool) and `rand3.n_consumed` 48 → 36 (rev. 2 defines it as the sequence index of the 19th admissible member + 1, §3.3; 48 is now `n_evaluated`). `design_check.json` differs only in that `n_consumed`. Chosen design points, control set and M are identical.

## What was run

Script [`scripts/screen01/screen01_pool.py`](../../../../scripts/screen01/screen01_pool.py) (run 1 SHA-256 `819fa1155f8d4c5887925ef7ebfdafd905ace84723580b0b91a2f94f848e1553`; run 2 `d194b6d55aec6ff12d9b1a0d669f156e7a9f654ad9a5174f48211b40465b1ef7`), which reuses `scripts/fid01/fid01_designs.py` unchanged (`work` = the MODE-01 v18 gate stack, `_x1` = r = 8 STL export + X1 practical gate) and `scripts/fid01/fid01_build.stl_volume`. Admissible = gate stack AND X1 AND the STL chain check `|V_STL/V_STL,parent - 1 - dV_SDF,smoothed/V| <= 0.01` (parent STL volume 0.119664 m^3, SHA-256 `41ceb0c6f75ab465d4d85627c53fe8c5333a36a53baba0515dff535ff80fd626`). Run 1 keyed cached rows by the `fid01_designs` dependency fingerprint `bc3cb4b2bb9e59a989a4035dc0ecb841fc3e6f69da6b88026acb26f9117547dd` (the rev. 0 rows of the axial states and C1 were reused under their rev. 0 key); run 2 evaluated every row afresh and keys rows, STLs and phi caches by `fingerprint()`. 4 worker processes on a 10-core machine under other load (load average 4-6).

Commands (worktree root, `.venv/bin/python`):
```
scripts/screen01/screen01_pool.py selfcheck
scripts/screen01/screen01_pool.py gen
scripts/screen01/screen01_pool.py p0 --pools axial ref manual rs rand3 --workers 4
scripts/screen01/screen01_pool.py design
scripts/screen01/screen01_build.py states          # after run 2: states.json + ../inputs/*.raw
scripts/screen01/screen01_build.py states --check  # byte check passed, 37 files
```

Run 1: 2026-10-30T16:20:50Z → 2026-10-30T18:58:43Z (157.9 min wall). Per-pool wall: axial 3.3 min, manual 16.1 min, rand3 58.8 min, ref 1.0 min, rs 78.6 min. Per-member gate evaluation (median per worker, 4 workers): axial 222 s, manual 243 s, rand3 241 s, ref 249 s, rs 240 s; X1 export about 55 s per member alone.
Run 2: 156.1 min wall (axial 10.8 min and ref 3.2 min, now evaluated afresh; manual 16.7, rs 71.4, rand3 53.9 min); medians axial 198 s, manual 278 s, rand3 219 s, ref 138 s, rs 218 s.

## Space and pools (`pools.json`)

Fixed subset (pitch, camber, reflex), heave 0; box u in [-1.0, 1.0] x [-1.5, 1.0] x [-1.0, 1.0] (camber extended to -29.55 mm); amplitude = u A* with A* = 3.1 deg / 19.7 mm / 29.3 mm, rounded to 1e-3. Scrambled Sobol (`scipy.stats.qmc.Sobol(d=3, scramble=True, seed)`): design pool `rs` seed 20261030 (first 64, +64 while < 12 admissible, max 256), random control `rand3` seed 20261033 (sequence order until 19 admissible or 512). Hand-design ladders for m_D = 1.0e-3 and 1.5e-3 N (both gated; the registration fixes m_D = 1.5e-3 N), the FID C1 downforce reference, the 6 axial states.

## Counts
| pool | evaluated | gate-clean | X1 pass | chain ok | admissible | failing gates |
| --- | --- | --- | --- | --- | --- | --- |
| axial | 6 | 6 | 6 | 6 | 6 | - |
| manual | 10 | 10 | 10 | 10 | 10 | - |
| rand3 | 48 | 25 | 25 | 25 | 25 | export_surface_integrity 2; min_feature_width 23; surface_self_intersection 2 |
| ref | 1 | 1 | 1 | 1 | 1 | - |
| rs | 64 | 35 | 35 | 35 | 35 | export_surface_integrity 2; min_feature_width 29; surface_self_intersection 2 |

- `rs`: 64 points used (no extension needed; rule: at least 12 admissible); 35 of 64 admissible (55 %); in the camber extension (u_camber < -1): 7 of 13 admissible.
- `rand3`: the 19th admissible member is sequence point 36 (`n_consumed` = 36; 48 points evaluated in chunks of 16, 25 admissible = 52 %; complete); the registered control set is the first 19 in sequence order (`summary.json: pools.rand3.control_set`).
- `manual`: first admissible ladder entry M = `v18__camber_m19.7_pitch_m0.38` for m_D = 1.5e-3 N (registered) and `v18__camber_m19.7_pitch_m0.33` for m_D = 1.0e-3 N; all 10 ladder entries: 10 admissible.
- `axial` 6/6 and `ref` 1/1 admissible (rev. 0 gate rows reused; X1 volumes and the chain check added).
- The STL chain check passed for every X1-clean state; R3 (opening defect, descriptive) passes every evaluated state; P22-v2, the smoothed-volume band and the clearance margin pass on all of them. The binding gate is again R0 `min_feature_width` (the one-cell occupancy artefact).

## Response-surface design check (`design_check.json`)

Rule: base = the 6 axial points; 9 admissible `rs` members added by greedy Bayesian D-optimality on the 9-column no-intercept quadratic. Result: 15 non-parent points, rank 9 (required 9), condition number 3.51 (bound 20; the 14 x 9 face-centred central composite reference has 3.61); design admissible: **True**. Rank of all admissible members + axial: 9. Design points in the camber extension: 7 admissible members lie there, design camber u values -1.11, +0.17, -1.00, -1.29, -0.03, +0.82, +0.76, -1.19, +0.78; |u|_inf of the design points 1.11, 1.00, 1.00, 1.29, 0.94, 0.96, 0.76, 1.19, 0.78.
Random control |u|_inf (K = 19): median 0.83 (optimizer design + axial median 1.00; `AMPLITUDE_MISMATCH` threshold 0.25 on the difference of medians → matched); 2 control members in the camber extension.

Chosen design points:
- `v18__camber_m21.959_pitch_m2.307_reflex_m24.023`  u = (-0.744, -1.115, -0.820)
- `v18__camber_p3.261_pitch_m3.085_reflex_p28.738`  u = (-0.995, +0.166, +0.981)
- `v18__camber_m19.789_pitch_m0.621_reflex_p26.168`  u = (-0.200, -1.005, +0.893)
- `v18__camber_m25.466_pitch_p2.31_reflex_p4.633`  u = (+0.745, -1.293, +0.158)
- `v18__camber_m0.502_pitch_m2.372_reflex_m27.474`  u = (-0.765, -0.025, -0.938)
- `v18__camber_p16.113_pitch_p1.042_reflex_p28.057`  u = (+0.336, +0.818, +0.958)
- `v18__camber_p15.009_pitch_p2.043_reflex_m11.687`  u = (+0.659, +0.762, -0.399)
- `v18__camber_m23.394_pitch_p0.776_reflex_m21.432`  u = (+0.250, -1.188, -0.731)
- `v18__camber_p15.396_pitch_m1.812_reflex_m17.01`  u = (-0.585, +0.782, -0.581)

## Admissible members

`rs` (35): `v18__camber_p0.507_pitch_m0.744_reflex_p11.354`, `v18__camber_m18.684_pitch_m2.494_reflex_m13.689`, `v18__camber_p15.396_pitch_m1.812_reflex_m17.01`, `v18__camber_m25.466_pitch_p2.31_reflex_p4.633`, `v18__camber_m14.568_pitch_m1.223_reflex_p14.671`, `v18__camber_p13.368_pitch_m1.043_reflex_m1.458`, `v18__camber_m5.821_pitch_m2.019_reflex_p2.756`, `v18__camber_p3.261_pitch_m3.085_reflex_p28.738`, `v18__camber_p19.01_pitch_m0.295_reflex_p18.527`, `v18__camber_m3.01_pitch_m2.14_reflex_m9.895`, `v18__camber_m6.961_pitch_p1.884_reflex_p26.847`, `v18__camber_m20.758_pitch_m0.777_reflex_p7.652`, `v18__camber_p15.009_pitch_p2.043_reflex_m11.687`, `v18__camber_p9.478_pitch_m2.663_reflex_p6.637`, `v18__camber_m1.456_pitch_p0.004_reflex_p16.677`, `v18__camber_p7.406_pitch_m0.451_reflex_m19.545`, `v18__camber_m17.91_pitch_p0.174_reflex_p2.533`, `v18__camber_m0.162_pitch_p3.088_reflex_m0.293`, `v18__camber_m10.245_pitch_m2.59_reflex_p21.794`, `v18__camber_p5.369_pitch_m1.716_reflex_p10.693`, `v18__camber_p16.113_pitch_p1.042_reflex_p28.057`, `v18__camber_m26.132_pitch_m1.516_reflex_m8.441`, `v18__camber_m4.308_pitch_m0.946_reflex_p22.582`, `v18__camber_m21.959_pitch_m2.307_reflex_m24.023`, `v18__camber_m13.595_pitch_m0.271_reflex_p4.382`, `v18__camber_p1.287_pitch_m0.005_reflex_m11.925`, `v18__camber_m11.693_pitch_p0.524_reflex_p24.355`, `v18__camber_m21.608_pitch_p1.594_reflex_m4.049`, `v18__camber_m2.417_pitch_p1.395_reflex_p6.388`, `v18__camber_p14.199_pitch_m1.298_reflex_p0.876`, `v18__camber_m23.394_pitch_p0.776_reflex_m21.432`, `v18__camber_m15.862_pitch_m1.885_reflex_m2.178`, `v18__camber_m0.502_pitch_m2.372_reflex_m27.474`, `v18__camber_p10.108_pitch_p0.295_reflex_m10.104`, `v18__camber_m19.789_pitch_m0.621_reflex_p26.168`

`rand3` control set (19, sequence order): `v18__camber_m17.304_pitch_m1.056_reflex_m4.377`, `v18__camber_m3.701_pitch_m2.29_reflex_p17.406`, `v18__camber_m7.817_pitch_m2.417_reflex_p7.656`, `v18__camber_p9.129_pitch_m0.554_reflex_m28.934`, `v18__camber_m11.14_pitch_m0.003_reflex_p27.435`, `v18__camber_m26.303_pitch_m1.751_reflex_m15.958`, `v18__camber_m8.416_pitch_p0.028_reflex_m3.18`, `v18__camber_p2.982_pitch_m1.486_reflex_p6.097`, `v18__camber_p13.023_pitch_m1.611_reflex_p11.039`, `v18__camber_p16.454_pitch_p1.64_reflex_m16.946`, `v18__camber_m1.442_pitch_m0.263_reflex_m0.534`, `v18__camber_m28.656_pitch_m0.68_reflex_p2.727`, `v18__camber_p6.88_pitch_m2.543_reflex_m19.455`, `v18__camber_m14.935_pitch_m2.041_reflex_m13.167`, `v18__camber_m19.007_pitch_p0.706_reflex_m26.059`, `v18__camber_p17.017_pitch_m0.807_reflex_p23.478`, `v18__camber_m16.263_pitch_m0.962_reflex_p13.18`, `v18__camber_m4.576_pitch_p0.673_reflex_m10.721`, `v18__camber_p19.106_pitch_m2.002_reflex_m23.47`

`manual` admissible: `v18__camber_m19.7_pitch_m0.33`, `v18__camber_m19.7_reflex_p9`, `v18__camber_m19.7_pitch_m0.25`, `v18__camber_m19.7_pitch_m0.41`, `v18__camber_m19.7_pitch_m0.17_reflex_p4.5`, `v18__camber_m19.7_pitch_m0.38`, `v18__camber_m19.7_reflex_p10.5`, `v18__camber_m19.7_pitch_m0.29`, `v18__camber_m19.7_pitch_m0.47`, `v18__camber_m19.7_pitch_m0.19_reflex_p5.2`

## Caveats
- Admissibility is at the native placement (as FID §3.3) and is not re-evaluated at the exploration or confirmation phases.
- The subset and box were chosen from visible force values (registration §8); this record is geometry only and says nothing about forces.
- Run 1 preceded the source review; run 2 re-validated every row under the reviewed fingerprint with no difference (above).
- STL blobs and gated phi of the X1-clean states are under `work/screen01_pool_prescreen/` (gitignored, regenerable by run 2's commands); their SHA-256 are in `rows.jsonl`. The direction raws the harness reads are committed in [`../inputs/`](../inputs/) and listed with their hashes in [`../states.json`](../states.json).

## Files and hashes (SHA-256)
| file | run 1 (in history at `db8732e0`) | run 2 (current) |
| --- | --- | --- |
| `pools.json` | `1430daef9cc6d9e394294ee5839d5944e16fcc27544defa6cbedba73dc0cf2e2` | same |
| `rows.jsonl` | `f88208b6f71bca16fb4a5cd65a21bceb73a411723ddc5451ef8ca566063bd581` | `db165ebac26538758cd6c4e692b4454edb9a6ff31f8416cbd145680df40fba00` |
| `summary.json` | `11fa24963df767dd96aebf0b71e0dfa759c43911df5ff68bd21610ca80c49544` | `dc259ce53ebfff6217dc1b8c84afbf5fc5987bd971f14a5f235b7eca18417629` |
| `design_check.json` | `3ce5fffd1119ce6cce06e01a41e9fcd812a1003d3dbbffcd75ee1e7fff9040f6` | `2bccd0f430974775385f7e22c970a17ea14448688cd5b59f6c0461e5904f9e39` |
| `p0.log` | `5b479c55744fb0cea2860ff310684e3e702fe5feba45b354c9966daca9434d2e` | `c0494650de874965234c39c9ae97a47c25ead76c24323732c2022b5bc72ad676` (both runs) |
| `scripts/screen01/screen01_pool.py` | `819fa1155f8d4c5887925ef7ebfdafd905ace84723580b0b91a2f94f848e1553` | `d194b6d55aec6ff12d9b1a0d669f156e7a9f654ad9a5174f48211b40465b1ef7` |
| `scripts/screen01/screen01_oc.py` | `ae951e5bcdfb4eaafc5e9c941bad0859b58a2be8fc341784750ac2b2da496366` | `5c9617dcb04502d57753163b92a32daac6f66e0a4641c36aa7c33c760da92ced` |
| `docs/evidence/screen01_2026_10_30/oc.json` | `ad58b5e1a5b0669d2ce2758e605833afa59c0be306691b0fddc62d3eb266220f` | `d9049976a1b754c59d965226acdc7380a38a58a56752b2b397e2ed1465648f8c` |
| `docs/evidence/screen01_2026_10_30/states.json` | - | `17011cf5c8a3952e03ad899db2b2cb8ed2f6c429af50b4dd4e838e1edae50dc9` (built from run 2; 36 raws in `../inputs/`) |
