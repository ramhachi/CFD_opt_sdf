# SCREEN-01 (#64, M3b-1) registration: fixed-topology screening and a small response surface on the v18 plate, finalist judged on sealed phases (L1, Re 80)

Status: **`DRAFT_FOR_PLAN_REVIEW`** (revision 0, 2026-10-30). Not frozen, not reviewed; no force of any SCREEN state exists. The study becomes `REGISTERED_FROZEN` at freeze 2 (§10), after one three-angle plan review (§12) and one source review (§13). No flag changes: all qualification flags stay false, `shape_update_allowed=false`. Integration branch `codex/kaggle-batch-migration` (not main). Where this text and `scripts/screen01/analyze_screen01.py` (to be implemented) disagree, this text governs and the disagreement is an analyzer defect. Decisions and the alternatives considered are in `docs/evidence/screen01_2026_10_30/decision_memo.md`.

Inputs (registered or `EXPLORATORY_COMMITTED`, binding from freeze 1):
- FID-01 `FID01_GO` (`docs/evidence/fid01_2026_10_21/analysis.json`, SHA-256 `b89203d0…`; handoff `docs/fid01_to_screen_xv_handoff_2026_10_23.md`): the M3b minimum gain `g_min = 0.027030580470324268` applied to paired flow_32 downforce differences normalised by the flow_48 parent downforce `J_b,48 = 0.26577921974115387 N` (FID §8; `g_min J_b,48 = x* = 7.184166586553256e-3 N`); `S_d = 0.003399676556346094`, `S_d,OF = 0.006337479927119433`, XV OpenFOAM floor `2 max(S_d, S_d,OF) = 0.012674959854238867`; R3 not challenged (no mandatory flow_48 P >= 2 over the pool), EX insensitive; `TIER_B_FAIL` (pure heave), `SUPPORT_UNTESTABLE`; the G3-set residual SD `1.4474126675928642e-3 N` and the tier-A V1 retention range 0.57-0.77 (used only in the §5.8 disclosure).
- M2 UNC-01 `M2_COMPLETE` (`docs/evidence/unc01_2026_10_20/analysis.json`, SHA-256 `ee71c6d6…`): the sigma_d floors 2.09e-4 N (downforce) and 1.36e-4 N (drag), the x-translation reference -1.648e-3 N (SE 8.53e-5), `sigma_d ~ 9.7e-5 (|Delta|/1e-3)^0.48 N` (planning only), flow_32 = flow_48 for large modes (R3).
- v18 parent `docs/evidence/v18_genesis_2026_10_19/` (state `e7376e35…`, phi Fortran `29d53b23…`), `scripts/v18_plate.py` (`4641c2f4…`, not edited); MODE-01 v18 basis, A* and gate stack (`scripts/mode01_v18_prescreen.py`); the FID-01 joint analytic builder and gate/X1 prescreen `scripts/fid01/fid01_designs.py` (reused unchanged).
- GEOM-03 `GEOM03_NO_GO` (`docs/evidence/geom03_2026_10_23/result.md`): R3 is **not** the width rule; the registered R0 `min_feature_width` stays the admissibility gate and its selection bias is disclosed (§3.6).
- Harness v1.1 with JOB-02 per-run placement (`scripts/harness.py`, the FID wrapper `scripts/fid01/fid01_harness.py` for the "[Private Notebook]" listing row).

## 1. Question, hypothesis and claim ceiling
**Question (L1, roadmap M3b-1; #64).** Does a gradient-free, fixed-topology procedure — a single-mode screen, a small quadratic response surface on the three strongest modes, and a finalist chosen by a fixed rule from a finite pre-gated pool — find, on the v18 analytic plate under the registered geometry and drag constraints, a WaterLily flow_32 downforce gain of at least `g_min` that holds on fresh placement phases and on flow_48?

Claim ceiling: Re = 80 reduced-laminar WaterLily (Kaggle T4), one analytic parent (v18), five analytic wide modes at MODE-01-tested amplitudes with heave fixed at 0, in-plane placement phases only (z, the ride height, is never phased, §4.1), uncertified geometry, the registered R0 width gate with its placement artefact. An `SCREEN01_GAIN` is a statement about **one finalist's paired same-phase differences against the parent inside the WaterLily solver family**; it is not independent verification (XV-01 #65 is), not an optimized-shape claim beyond L1, not physical downforce, not grid independence, not FSAE, not high Re. The finalist's expected OpenFOAM gain is disclosed with a selection-bias allowance (§5.8) and is not a result.

Outcomes (§5.9): `SCREEN01_GAIN`, `SCREEN01_NO_GAIN` (with a cause), `SCREEN01_INCONCLUSIVE` (completed but a rule unresolved by noise), `SCREEN01_INCOMPLETE` (data or budget), `SCREEN01_INVALID` (chain check fails). Registered secondary labels (no effect on the outcome): drag resolution, R3 ratio and `R3_E2_EXCEEDED`, flow_48 drag sign, `OPT_VS_RANDOM`, `OPT_VS_MANUAL`, `RANDOM_FEASIBLE_GAIN`, `XV_MARGIN_{ADEQUATE,THIN}`, `RS_FIT` quality, `GENERATION_DRIFT`.

## 2. Stages (PROC-01)
| Stage | Content | Status |
| --- | --- | --- |
| P0 | pool generation, solver-free gate prescreen and X1 export gate of every pool member, the per-subset response-surface design check (`scripts/screen01/screen01_pool.py`, §3.3-3.4), operating characteristics (`scripts/screen01/screen01_oc.py`, §5.10) | before freeze 1, no force; the exploratory run of 2026-10-30 covers one subset and a prefix of the random pool (§3.4, §8) |
| P1 | this revision 0 → one three-angle plan review (numerical, controls, strategy) → revision 1 | |
| P2 | sources (`scripts/screen01/*.py`, tests) → one source review → **freeze 1** (commit, push, #64 comment) | |
| S1 | WaterLily harness smoke of the exploration campaign (parent, flow_32, phase 11) and `verify --smoke`; prerun freeze → **freeze 2** | engineering under freeze 1 |
| G1 | generation 1, two kernels (phases 11 and 12): parent, the 10 axial states, the manual control, the x-translation control, the 22 random-control states; `analyze_screen01.py topmodes` written once → the response-surface subset and its frozen design points | `REGISTERED_FROZEN` |
| G2 | generation 2, one kernel (phases 11, 12): parent and the 9 design points of the selected subset; `analyze_screen01.py rs` written once → fit and at most 3 proposals | registered step |
| G3 | generation 3, one kernel (phases 11, 12): parent and the proposals; `analyze_screen01.py finalist` written once → finalist, random-best, K, the selection record; the sealed campaigns and the flow_48 campaign built from it, their smokes and prerun freezes, the budget rule (§4.3), the STL chain check → **freeze 3** | registered step / engineering |
| F | sealed confirmation: flow_32 phases 13-16 (parent, finalist, random-best, manual control) and flow_48 phases 13, 14 (parent, finalist, random-best), pushed unconditionally | `REGISTERED_FROZEN` |
| A | one analysis (`analyze_screen01.py main`), written once | `REGISTERED_FROZEN` |

Every selection step (topmodes, rs, finalist) reads only harness-verified WaterLily tables, applies the rules of §5 mechanically, is written once with `--out` opened exclusively, and its output SHA-256 is recorded in the following freeze before the kernels it determines are pushed. The analyst sees the exploration forces before the sealed runs; the decision estimator is the sealed one (§5.6), which the analyst cannot influence after freeze 3.

## 3. Search space, pool and controls
### 3.1 Modes, box and normalisation
Five analytic wide modes of `v18_plate` (units and signs of `v18_plate.UNITS`): pitch (deg, + nose down), camber (mm, + mid-chord up), reflex (mm, + trailing edge down), twist (deg, + tips nose down), sweep (mm, + tips downstream). **Heave is fixed at 0** (new SCREEN decision, not an FID rule): the ride height is a vehicle setting rather than a wing shape, pure heave failed FID tier B, and heave moves the body against the never-phased z lattice, so a heave component would carry an unsampled placement systematic (§4.1). Surge (translation) is the negative control, not a mode. Local/narrow modes stay excluded (FID `SUPPORT_UNTESTABLE`).

Amplitude box: `a_m = u_m A*_m`, `u_m in [-1, 1]`, with the MODE-01 v18 A* (both signs gate-clean): pitch 3.1 deg, camber 19.7 mm, reflex 29.3 mm, twist 1.1 deg, sweep 11.3 mm. Nothing outside the box is ever built. The box edges are MODE-01-tested geometry; interior points and combinations are **not** MODE-01-tested and are gated individually (§3.3).

### 3.2 Construction
A candidate is a dict `{mode: amplitude}` built by `scripts/fid01/fid01_designs.py` on the v18 parent: the modes are applied **jointly** to the plate parameters and `v18_plate.plate_phi` is evaluated once (an exact plate SDF; no superposition of phi differences; a single mode reproduces `v18_plate.mode_phi` bit for bit). Only active nodes change; the evaluated bytes are the harness state model `construct_state(parent, d / max|d|, 1000 max|d| mm, +1)`, i.e. what the WaterLily runner regenerates and what the STL is exported from. State names are `fid01_designs.name(spec)` with the spec keys in sorted order.

### 3.3 Admissibility and the finite pools (solver-free, fixed at freeze 1)
**Gate stack (unchanged, applied by `fid01_designs.work`):** the 13 GEOM-02 v2 gates (`component_connectivity, domain_clearance, export_surface_integrity, inter_component_gap, mask_preservation, min_feature_width (R0), near_zero_gradient_band, sdf_boundary_margin, sdf_distance_property, sdf_finite_structure, surface_self_intersection, topology_change_classification, volume_semantics`, profile `docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json`, v18 parent as `parent_state`), P22-v2 `N_phi <= 8272`, the 10 % smoothed-volume band against the v17 baseline, clearance margin >= 0.15 m; an unmeasured gate counts as a fail; R3 (opening defect) is a descriptive column. **X1 export gate:** the r = 8 STL passes the practical gate in double and float32 (`unc01_u3_prepare.export`). A pool member is **admissible** iff it passes both. Admissibility is decided before freeze 1 for every pool member and never re-decided.

**Pools** (`screen01_pool.py gen`; scrambled Sobol, `scipy.stats.qmc.Sobol(scramble=True, seed)`, `u = 2x - 1`, amplitudes rounded to 1e-3 mm or deg):
- `axial`: the 10 stage-1 states `{m: ±A*_m}`.
- `rs_<m1>_<m2>_<m3>`, one per 3-mode subset of the five modes (10 subsets, index i in `itertools.combinations` order): the first `N_RS = 64` points of the sequence with seed `20261030 + i` in `[-1, 1]^3`. A subset with fewer than 12 admissible members extends to the next 64 points of the same sequence (deterministic prefix) until it has 12 or reaches 256; the count used is recorded per subset.
- `rand5`: the random-direction control pool, seed `20261031` in `[-1, 1]^5`; evaluated in sequence order until **22 admissible members** are found (the registered control set) or 512 points are exhausted (the sequence extends deterministically past the generated 256; then the control has fewer members, recorded).
- `manual`: camber -11.3 mm, reflex -11.3 mm (FID-01 C1).

**Response-surface design per subset (frozen at freeze 1 for all 10 subsets):** base points = the parent (u = 0) and the 6 axial points `±e_i` of the subset (stage-1 states); 9 further points chosen from the subset's admissible members by greedy Bayesian D-optimality on the full-quadratic columns `[1, u, u_i^2, u_i u_j]` (`logdet(X'X + 1e-6 I)`, ties → smallest pool index; `screen01_pool.py design`). A subset design is admissible iff the no-intercept matrix of the 15 non-parent points on the 9 columns `[u, u_i^2, u_i u_j]` has rank 9 and condition number <= 20 (the face-centred central composite design has about 5.8 on the 10-column form). **If any subset is inadmissible at P0 the pool is extended by the rule above before freeze 1; after freeze 1 nothing about pools, designs or rules changes** (a subset cannot become inadmissible later except through data loss, §9). Trust region of a subset = the convex hull of its 16 design points (`scipy.spatial.Delaunay.find_simplex >= 0`).

### 3.4 P0 exploratory prescreen (geometry only, 2026-10-30)
Run in the registration worktree at integration commit `46bcd619` with `screen01_pool.py` (4 workers, machine under other load; commands, timing, names and hashes in `docs/evidence/screen01_2026_10_30/pool_prescreen/README.md`), covering the axial and manual states, the subset {pitch, camber, reflex} (the one the visible data predict, §8) and the first 16 points of the random pool. Results: axial 10/10 and manual 1/1 gate-clean; `rs_pitch_camber_reflex` 27 of 64 gate-clean (42 %; every failure includes `min_feature_width`, 7 also the export-integrity/self-intersection gates; R3 descriptive passes all 64); all 41 gate-clean states pass X1, so the subset has 27 admissible members; the frozen-design rule gives 16 points of rank 10 (9 on the no-intercept form), condition number 7.5 (4.2 no-intercept; FCCD reference 4.4; bound 20), a trust region of 45 % of the box volume holding 23 of the 27 admissible members (14 unevaluated ones available as proposals), 7 of the 27 three-level grid points and no box corner. `rand5`: 3 of 16 gate-clean (19 %), all X1-clean, projecting about 117 sequence points for 22 admissible members (a wide interval at n = 16, hence the cap of 512). Cost: 110-140 s per member alone, 170-250 s per member per worker with 4 workers, X1 about 55 s; the remaining nine subsets and the rest of the random pool (about 9 x 64 + 120 members) run before freeze 1. **The P0 record is geometry only; it says nothing about forces.**

### 3.5 Controls
- **Manual control M** (visible, §8): camber -11.3 + reflex -11.3 (FID-01 C1, `v18__camber_m11.3_reflex_m11.3`), the FID-visible gate-clean two-mode combination with the largest flow_32 downforce difference whose drag increase was the smallest among the FID combinations (+1.326e-2 N downforce, +5.8e-3 N drag at phases 7-10). It is run at every exploration and sealed flow_32 phase and compared with the finalist (§5.7). It is not eligible as finalist.
- **Random-direction control R**: the 22 admissible `rand5` members (§3.3), the same space, gates, phases and budget as the 22 optimizer candidates (10 axial + 9 design + 3 proposals = 44 flow_32 runs each side). Its best member (§5.5) receives the same sealed flow_32 and flow_48 confirmation as the finalist. Not eligible as finalist.
- **Negative control NC** (x-translation `v18__roll_p25`, the M2/FID state, same bytes): run at phases 11 and 12 and judged against M2's measured -1.648e-3 N (§5.6); it checks the measurement chain, not a design.
- **Parent repeats**: the parent is the first run of every kernel at every phase of that kernel; every paired difference uses the parent run of the same kernel and phase.

### 3.6 Width rule and the disclosed selection bias of the pool
Admissibility uses the registered R0 at the native placement, unchanged (GEOM-03 did not qualify R3). R0 fails about 40-60 % of sub-cell placements of this smooth plate for a one-cell occupancy artefact and more often for joint combinations (FID prescreen: 6 of 30 joint combinations; WIDTH-RULE: 190/200 linear combinations). Consequences, stated: (i) the admissible pool is a lattice-dependent subset of the box, so the finalist is the best admissible member, not the best point of the box; (ii) the response surface is fitted on admissible points only and may propose only admissible points; (iii) the restriction is placement-dependent (a candidate's R0 status at other phases is not evaluated, as in FID); (iv) no R0 failure is repaired, re-sampled or re-phased. The per-subset admissible fraction and the failing gates are recorded in freeze 1 (P0 record). The same filter applies to the random control, so the optimizer-vs-random comparison is within the same restricted space.

## 4. WaterLily design
### 4.1 Grids, phases and generations
- Placement as M2/FID: phase k moves `W4_CANONICAL_ORIGIN_M` by `(f_kx, f_ky, 0) h_g`, `f_k = frac(k (0.7548776662, 0.5698402910))` (R2 sequence). **z never moves**: a candidate whose surface occupies the z lattice differently from the parent carries a systematic that no in-plane phase averages; XV-01's 3-axis shifts sample it partly on the OpenFOAM side; it is one reason heave is fixed (§3.1).
- Used phases: k = 0 (U1), 1-6 (M2), 7-10 (FID). **Exploration generation (G1-G3): k = 11, 12 (P = 2), common to every exploration state** (R4). **Sealed confirmation (F): flow_32 k = 13, 14, 15, 16 (P = 4) and flow_48 k = 13, 14 (P = 2)**, disjoint from every phase any SCREEN state has seen. P = 2 for exploration follows UNC-01's `phases_needed(r) = ceil(9 r^2) = 1` for the wide arms (sigma_d/|Delta| about 0.03) with one phase of redundancy; a selection-phase SE of about 1-3e-4 N against differences of 1e-2 N ranks candidates; it is not the decision estimate. P = 4 sealed gives `t_{0.95,3} SE_eff` about 3-4e-4 N (0.1-0.15 % of J_b,48) under the FID sigma_d values, the resolution the §5.6 rule spends.
- flow_32 proposes, flow_48 confirms (R3): flow_48 is run only in the sealed stage (§5.6 R3 rule). flow_24 is not used.

### 4.2 Kernels (flow_32 about 415 s per run + 260 s per kernel; flow_48 about 2,340 s per run; FID-01 measured 395-431 s and 2,178-2,283 s)
| Campaign / kernel | Grid | Phases | Runs (parent first at each phase) | per-state / aggregate cap / kernel timeout (s) | Estimate (s) |
| --- | --- | --- | --- | --- | --- |
| screen01 / g1k11, g1k12 | flow_32 | one each | 35: parent, 10 axial, M, NC, 22 R | 900 / 18,000 / 21,300 | 35 x 415 + 260 = 14,785 each |
| screen01 / g2 | flow_32 | 11, 12 | 20: parent x2, 9 design points x2 | 900 / 10,500 / 13,500 | 8,560 |
| screen01 / g3 | flow_32 | 11, 12 | 8: parent x2, <= 3 proposals x2 | 900 / 6,000 / 9,000 | <= 3,580 |
| screen01_f / f32a (13, 14), f32b (15, 16) | flow_32 | two each | 8: parent, finalist, R-best, M at each phase | 900 / 6,000 / 9,000 | 3,580 each |
| screen01_f48 / f48k13, f48k14 | flow_48 | one each | 3: parent, finalist, R-best | 6,000 / 9,200 / 12,500 | 3 x 2,340 + 260 = 7,280 each |

One phase per G1 kernel (a kernel lost twice costs one exploration phase, P = 1 survives); G2 and G3 are small enough for one kernel each. Every pair (candidate and parent at the same phase) is inside one kernel; parent first. The two G1 kernels and the two f48 kernels run concurrently (Kaggle allows 2 sessions). Total estimate about 17.6 GPU h of session wall + two smokes (about 0.9 h) = about 18.5 GPU h; every kernel is far inside the 12 h session limit. Budget equality of the controls: optimizer 22 candidates x 2 phases = 44 runs; random 22 x 2 = 44 runs; parent repeats and controls are overhead of both.

### 4.3 Budget, quota, queue
Cap **24 GPU h** (86,400 s) of formal session wall (Kaggle session wall from each kernel log; smokes excluded, INFRA_LOSS reruns included). It governs only the flow_48 kernels: before pushing them, `T = sum(session wall of every finished formal kernel) + 14,560 s`; if `T > 86,400 s` flow_48 is `NOT_MEASURED` (recorded with its inputs) and the outcome is `SCREEN01_INCOMPLETE` (cause `BUDGET`, §5.9). If the weekly quota (30 GPU h) stops a push: pause, resume in order, no rule change; the generations are sequential by construction so the campaign spans at least two quota weeks. **Backend trigger** (STATE.md): a kernel waiting more than 24 h in the queue, or the quota blocking the remaining kernels for more than 7 days, stops the pushes and is reported; finished kernels stay valid; the backend decision is the user's.

### 4.4 Blinding
While kernels run only statuses, session times and `verify` pass/fail are read (per-kernel verify tables to files, stdout discarded). Forces are read only by the frozen selection steps and the analysis, each written once after all kernels of its generation are verified or declared lost. The sealed-stage states are fixed in freeze 3 before any sealed run.

## 5. Rules (computed by the frozen `scripts/screen01/analyze_screen01.py`)
Responses: downforce (objective) and drag (constraint), N, as the harness state-force tables report them. Differences are candidate minus parent at the same phase in the same kernel.

### 5.1 Estimators
- For a state s and a phase set Φ (the phases common to s and the parent in the stage's kernels): `Delta_bar = mean_k(F_s,k - F_parent,k)`, `sigma_d` (|Φ| - 1 dof) as M2 (`analyze_unc01.stats`); `SE_eff = max(sigma_d, floor) / sqrt(|Φ|)` with the M2 floors `0.00020904201605451784 N` (downforce) and `0.000136408347135453 N` (drag); with |Φ| = 1, `sigma_d` is undefined and `SE_eff = floor`. `t = t_{0.95, |Φ|-1}` (one-sided 95 %), undefined for |Φ| = 1.
- Gains are reported as `I = Delta_bar / J_b,48` with `J_b,48 = 0.26577921974115387 N` (the FID normalisation; the flow_32 parent force is not the denominator).
- Exploration estimates use Φ ⊆ {11, 12}; sealed estimates use Φ ⊆ {13, 14, 15, 16} (flow_32) and {13, 14} (flow_48). The two are never pooled.

### 5.2 Stage 1 → the response-surface subset (`topmodes`, written once after G1)
For each mode m: `s_m = max(|Delta_bar_DF(+A*_m)|, |Delta_bar_DF(-A*_m)|)` over the exploration phases. The subset is the three largest `s_m`; ties (|s_m - s_n| <= 1e-6 N) in the registered order pitch, camber, reflex, twist, sweep. A mode with both axial states lost at both phases ranks last (`DATA_LOSS`); fewer than 3 modes with data → `SCREEN01_INCOMPLETE`. Output: the subset, the per-mode table (downforce and drag, both signs), the frozen design points of that subset (from freeze 1), and the G2 run list. **Disclosure (§8):** from visible M2/FID/U1 values the expected ranking is pitch > reflex > camber > twist > sweep; the rule is applied mechanically and all 10 subsets carry frozen designs.

### 5.3 Stage 2 → the response surface and the proposals (`rs`, written once after G2)
On the 15 non-parent design points (6 axial from G1, 9 from G2; all at phases 11, 12) fit by ordinary least squares, separately for downforce `y` and drag `z`, the no-intercept full quadratic `f(u) = b'u + u'Qu` (9 coefficients; `f(0) = 0` holds exactly because a difference against the parent vanishes at the parent). Report the coefficients, the residual SD, the lack-of-fit ratio against the pooled per-point `SE_eff`, and `RS_FIT_{OK,POOR}` (`POOR` if the residual SD exceeds 3 times the pooled SE_eff; descriptive). A design point lost at both phases is dropped; if the remaining matrix has rank < 9, `RS_NOT_FIT` is recorded, no proposals are made and stage 3 is skipped (the finalist then comes from the evaluated states; nothing is repaired or re-run).
**Proposals:** over the subset's admissible pool members (freeze 1) that are inside the trust region (§3.3) and not yet evaluated, rank by predicted downforce `ŷ(u)` among those with predicted drag `ẑ(u) <= -m_D`, `m_D = 1.0e-3 N` (the response-surface drag target: about 2 SE of a two-phase drag difference at the FID tier-A drag sigma_d of about 7e-4 N; it is an optimizer target, not a decision threshold); take the top 3. Fewer than 3 (or none) → fewer proposals (or stage 3 skipped), recorded. No continuous argmax, no extrapolation outside the hull, no unregistered geometry.

### 5.4 Stage 3 (G3)
The proposals are run at phases 11 and 12 with the parent. No further proposals, no second round.

### 5.5 Finalist, random-best (`finalist`, written once after G3)
Candidate set `C_opt` = the 10 axial states, the 9 design points and the proposals (K_opt = |C_opt| <= 22). **Feasible** = `Delta_bar_drag <= 0` (exploration point estimate; the registered precedent `DRAG_ALLOWANCE_N = 0.0` of the LOWDIM/OPT-01 contracts, computed sign only). **Finalist** = the feasible candidate with the largest exploration `Delta_bar_DF`; ties (within 1e-6 N) → the registered order axial (registered order of modes, + before -), then design points (freeze order), then proposals (rank order). If `C_opt` has no feasible member, or the finalist's `Delta_bar_DF < g_min J_b,48 - 3 SE_eff` (it cannot reach the sealed rule), there is no finalist and the sealed stage is not run (`SCREEN01_NO_GAIN`, cause `NO_FEASIBLE_CANDIDATE` or `GAIN_BELOW_MIN_AT_SELECTION`, §5.9). **Random-best** = the same rule over the 22 random states (`C_rand`); if none is feasible, R-best is empty and the sealed stage runs without it (`RANDOM_NO_FEASIBLE`). Output: both selections, K_opt, K_rand, every candidate's exploration estimates, the sealed run lists.

### 5.6 Sealed decision (`main`, written once after F)
For the finalist f (and, descriptively, for R-best and M) with the sealed flow_32 phases Φ_s (|Φ_s| >= 3 required for f, else `SCREEN01_INCOMPLETE`):
- **G (gain):** `PASS` if `Delta_bar_DF,s - t SE_eff,DF >= g_min J_b,48`; `UNRESOLVED` if `Delta_bar_DF,s >= g_min J_b,48` but the lower bound is below it; `FAIL` if `Delta_bar_DF,s < g_min J_b,48`. The one-sided lower bound is the registered resolution: a gain is claimed only when it is resolved above the minimum.
- **D (drag non-increase, allowance 0):** `PASS_RESOLVED` if `Delta_bar_drag,s + t SE_eff,drag <= 0`; `PASS_UNRESOLVED` if `Delta_bar_drag,s <= 0 < Delta_bar_drag,s + t SE_eff,drag`; `VIOLATION_UNRESOLVED` if `0 < Delta_bar_drag,s <= t SE_eff,drag`; `VIOLATION_RESOLVED` if `Delta_bar_drag,s - t SE_eff,drag > 0`. The decision uses the point sign (both `PASS_*` satisfy D); the resolution label is a registered secondary result and XV-01 re-evaluates the constraint on OpenFOAM with its own uncertainty (requirements §3b). Rationale and the operating characteristics of this choice: §5.10 and the decision memo D1.
- **R3 (flow_48 confirmation):** with Φ_48 ⊆ {13, 14}: `R3_CONFIRMED` if `Delta_bar_DF,48 > 3 SE_eff,48` (floor 2.09e-4 N; with |Φ_48| = 1, `SE_eff,48 = floor`); `R3_CONTRADICTED` if `Delta_bar_DF,48 < -3 SE_eff,48`; else `R3_UNRESOLVED`. Reported: the same-phase ratio `Delta_bar_DF,48 / Delta_bar_DF,32(k13, k14)`, `R3_E2_EXCEEDED` if `|Delta_bar_DF,48 - Delta_bar_DF,32(k13, k14)| > Delta_min = 2 S_d J_b,48 = 1.807e-3 N`, and `R3_DRAG_SAME_SIGN` (sign of the flow_48 drag difference equals the sealed flow_32 one). flow_48 `NOT_MEASURED` (§4.3) or both kernels lost → `SCREEN01_INCOMPLETE`.
- **NC (G1):** `z = |Delta_bar_roll - (-1.6476407624087992e-3)| / sqrt(SE^2 + (8.534104568937632e-5)^2)`, `SE = max(sigma_d, 3e-4) / sqrt(P)` (with P = 1, `SE = 3e-4`); CONSISTENT if `z <= 3.5`, else `SCREEN01_INVALID`.
- **Geometry (freeze 3, before F):** the finalist and R-best pass the gate stack and X1 (already true by admissibility, re-derived on the harness bytes), and the STL chain check `|dV_STL / V - dV_SDF,smoothed / V| <= 0.01` against the parent STL. A chain-check failure of the finalist is `FINALIST_INADMISSIBLE` → `SCREEN01_NO_GAIN`; of R-best → R-best dropped (`RANDOM_INADMISSIBLE`).
- **Generation drift (descriptive):** the maximum absolute difference between the parent's repeated runs at the same phase across kernels (flow_32); `GENERATION_DRIFT` if it exceeds the downforce floor 2.09e-4 N (JOB-02 found byte identity; a drift would indicate an environment change, not a design effect). Reported, no consequence (pairs are within kernel).

### 5.7 Control comparisons (sealed phases; descriptive labels)
Per sealed phase k, `e_k = Delta_DF,f,k - Delta_DF,R-best,k` (the finalist minus R-best, same phase); `OPT_BEATS_RANDOM` if `mean(e) - t SE(e) > 0`, `RANDOM_BEATS_OPT` if `mean(e) + t SE(e) < 0`, else `OPT_RANDOM_UNRESOLVED`; `RANDOM_NO_FEASIBLE` if R-best is empty. The same with M (`OPT_VS_MANUAL`). `RANDOM_FEASIBLE_GAIN` if R-best itself passes G (PASS) and D and R3 (i.e. random sampling alone met the L1 rule). The exploration-phase versions are reported beside them (K_opt and K_rand are equal, so their selection bias is matched).

### 5.8 Selection-bias statement (registered disclosure, computed by the analyzer)
- **Placement-noise bias (removed by the sealed phases):** `Delta_bar_DF,sel - Delta_bar_DF,s` of the finalist is reported with its SE; the decision never uses the selection-phase estimate.
- **WaterLily-to-OpenFOAM bias (not removable here):** upper bound `b_K = E[max of K_opt standard normals] x sigma_disc`, `sigma_disc = 1.4474126675928642e-3 N` (the FID G3-set residual SD, an upper bound because it contains V3 placement noise), `E[max_22] = 1.9097` (`oc.json`), so `b_22 = 2.764e-3 N = 1.04 % of J_b,48` (0.50 % with the retention-spread estimate 7e-4 N, reported beside it). **Expected OpenFOAM gain** `g_XV,exp = 0.57 (I_s - b_K / J_b,48)` with 0.57 the FID tier-A minimum V1 retention; `XV_MARGIN_ADEQUATE` if `g_XV,exp >= 0.012674959854238867`, else `XV_MARGIN_THIN` (at K = 22 the boundary is `I_s = 3.26 %`). The label does not change the outcome and does not gate XV-01 (§7); it is handed over so the XV registration states its expected pass probability before funding.
- `g_min` is applied exactly as registered; no additional floor and no raised target is added to the outcome rule (#64; decision memo D6).

### 5.9 Outcome (evaluation order)
1. Minimum data: a verified G1 parent run at >= 1 phase, every axial state and NC with >= 1 common phase; else `SCREEN01_INCOMPLETE` (cause `DATA_G1`).
2. NC not CONSISTENT: `SCREEN01_INVALID`.
3. No finalist (§5.5): `SCREEN01_NO_GAIN`, cause `NO_FEASIBLE_CANDIDATE` or `GAIN_BELOW_MIN_AT_SELECTION`.
4. `FINALIST_INADMISSIBLE` (§5.6 geometry): `SCREEN01_NO_GAIN`.
5. Sealed flow_32 |Φ_s| < 3, or flow_48 `NOT_MEASURED` / both kernels lost: `SCREEN01_INCOMPLETE` (cause `DATA_SEALED` or `BUDGET`).
6. G `FAIL`, D `VIOLATION_RESOLVED` or `VIOLATION_UNRESOLVED`, or `R3_CONTRADICTED`: `SCREEN01_NO_GAIN`, cause `GAIN_BELOW_MIN`, `DRAG_VIOLATION`, `GRID_CONTRADICTED` (the first that applies, all listed).
7. G `UNRESOLVED` or `R3_UNRESOLVED`: `SCREEN01_INCONCLUSIVE`.
8. G `PASS`, D `PASS_*`, `R3_CONFIRMED`: **`SCREEN01_GAIN`**.
Nothing in steps 3-8 is repaired from a force: no added phase, candidate, proposal or re-fit.

### 5.10 Operating characteristics (`scripts/screen01/screen01_oc.py`, `docs/evidence/screen01_2026_10_30/oc.json`, 20,000 replicates per scenario, seed 20261030)
Synthetic model: K = 22 candidates; WaterLily placement noise `sigma_d = 9.7e-5 (|Delta|/1e-3)^0.48 N` per phase (M2 fit, floor 2.09e-4 N in SE_eff), drag noise 7e-4 N per phase; P = 2 exploration, P = 4 sealed, flow_48 P = 2 with ratio 0.98 and noise 5e-4 N; "best x" = one candidate at true gain x with 21 others uniform in [0, x] and drags uniform in [-2e-3, 2e-3] N; the best candidate's true drag at the response-surface target -m_D, at the boundary 0, or at -2 m_D. Selection filter `Delta_bar_drag <= 0` (registered); the alternative filter `<= -m_D` is in the file.

| Scenario (best candidate) | P(`SCREEN01_GAIN`) | main non-GAIN cause |
| --- | --- | --- |
| all true gains 0 (null), any drag | 0.000 | `GAIN_BELOW_MIN` (false GAIN through selection alone: none in 60,000 replicates) |
| best 0.5 g_min | 0.000 | `GAIN_BELOW_MIN` |
| best = g_min, drag -m_D / 0 / -2 m_D | 0.013 / 0.003 / 0.014 | `GAIN_BELOW_MIN` (the lower-bound rule; the point rule would give 0.49 / 0.16 / 0.50) |
| best 1.2 g_min, drag -m_D / 0 / -2 m_D | 0.934 / 0.332 / 0.984 | `DRAG_VIOLATION` when the optimum sits on the boundary |
| best 1.5 g_min, drag -m_D / 0 / -2 m_D | 0.997 / 0.716 / 0.993 | same |
| best 2 g_min, drag -m_D / 0 / -2 m_D | 0.955 / 0.735 / 0.994 | same |
| all 22 at g_min, drag -m_D (worst case for the curse) | 0.015 | `GAIN_BELOW_MIN` |

Reading: a true gain at exactly g_min is reported `GAIN` about 1 % of the time and `INCONCLUSIVE`/`NO_GAIN` otherwise (the registered meaning of "at least g_min, resolved"); 1.2 g_min with the drag target met passes 93 %; a finalist whose true drag sits on the constraint boundary is lost through D about half the time, which is why the response surface targets `-m_D` and why the measured selection filter uses the point sign (the `-m_D` filter variant halves the probability of selecting the true best, `oc.json`). The sealed re-estimate has no measurable bias (`sealed_bias_n` about 0) while the selection-phase estimate is biased upward by 1-3e-4 N in these scenarios. The model does not simulate the response-surface fit or the pool restriction; it is a statement about the decision rules.

## 6. Coefficients fixed from M2 and FID-01
| Coefficient | Value | Source | Use |
| --- | --- | --- | --- |
| g_min | 0.027030580470324268 | FID `m3b_min_gain.min_gain_relative` | G |
| J_b,48 | 0.26577921974115387 N | FID coefficients / M2 | normalisation |
| g_min J_b,48 (= x*) | 7.184166586553256e-3 N | FID `x_star_n` | G threshold |
| S_d, Delta_min | 0.003399676556346094, 1.8071267650359157e-3 N | FID coefficients | `R3_E2_EXCEEDED` |
| sigma_d floors (downforce / drag) | 2.0904201605451784e-4 / 1.36408347135453e-4 N | M2 roll flow_32 | SE_eff |
| NC reference | -1.6476407624087992e-3 N, SE 8.534104568937632e-5 | M2 roll flow_32 | §5.6 NC |
| m_D | 1.0e-3 N | planning (2 SE of a 2-phase drag difference at sigma_d,drag about 7e-4 N, FID tier A) | response-surface target only |
| sigma_disc, E[max_22], retention 0.57 | 1.4474126675928642e-3 N, 1.9097, 0.57 | FID G3-set residual SD, `oc.json`, FID tier-A minimum V1 retention | §5.8 disclosure only |
| XV OpenFOAM floor | 0.012674959854238867 | FID §8 | §5.8 label only |
The analyzer re-reads the FID and M2 analysis files by SHA-256 and refuses if any value differs.

## 7. Consequences
- `SCREEN01_GAIN`: XV-01 (#65) is registered with the frozen finalist (§11 handoff), regardless of the `XV_MARGIN` label; the XV registration must state the expected pass probability implied by §5.8 before any OpenFOAM case is funded. No second SCREEN round and no finalist retuning after XV.
- `SCREEN01_NO_GAIN` (any cause): recorded; no extra exploration round, no pool refill, no phase added; M4 (#66) decides with this result. The control labels are reported with it.
- `SCREEN01_INCONCLUSIVE`: no extra round within this registration. At most one re-registration of M3b-1 addressing the recorded cause (as FID §8); otherwise M4.
- `SCREEN01_INCOMPLETE`, `SCREEN01_INVALID`: no M3b-2; at most one re-registration addressing the recorded cause; an explicit recorded decision is required before anything else.
- Flags: unchanged in every case (`shape_update_allowed=false`).

## 8. What was visible before this registration
- All of M2 (registered) and U1 single-phase flow_32 values (camber ±19.7, reflex ±29.3, twist ±1.1 (+1.6e-3 / -1.2e-3 N), sweep ±11.3 (about 1e-4 N), pitch ±3.1 with drag +2.97e-2 / -2.80e-2 N); pitch ±3.1 and reflex +29.3 also have OpenFOAM values (U3).
- All of FID-01, including the flow_32 paired downforce and **drag** differences read from `analysis.json` for this design (N, phases 7-10): camber -19.7 +1.300e-2 / +2.0e-3; camber -11.3 +7.18e-3 / +1.2e-3; camber +19.7 -1.02e-2 / -1.6e-5; reflex -29.3 +1.565e-2 / +1.25e-2; pitch +0.7 +1.06e-2 / +6.9e-3; pitch -0.7 -8.95e-3 / -6.4e-3; twist +2.3 +3.62e-3 / +1.24e-3; C1 +1.326e-2 / +5.8e-3; C4 -3.20e-2 / -2.22e-2; the V1 retentions 0.57-0.77 and drag retentions 0.58-0.87; the G3-set residual SD. **Every one of the 10 axial states therefore has a visible flow_32 downforce value, and so has the manual control.** Used here to: fix heave at 0 (tier B), choose the drag constraint form (every downforce-gaining single mode costs drag at a ratio 1.25-6.5, so the constrained problem is not solved by pitch alone), predict the stage-1 ranking (pitch > reflex > camber > twist > sweep, so the response-surface subset is expected to be {pitch, camber, reflex} and that subset was the one evaluated in the exploratory design check), set m_D and the OC noise model, and choose the manual control.
- The MODE-01 v18 prescreen (gate-clean ladder points), the FID prescreen (6 of 30 joint combinations gate-clean), WIDTH-RULE and GEOM-03 (geometry only).
- The P0 exploratory pool prescreen of 2026-10-30 (§3.4; geometry only, no force).
- The operating-characteristics simulation (synthetic only).
Nothing in §1-§7 was chosen after a force of a SCREEN pool member, random-control member or proposal was seen; none exists.

## 9. Freeze, re-run, amendment and stopping rules (fail-closed)
- Order: §2. Freezes 1, 2 and 3 and the written-once selection outputs are committed, pushed and commented on #64 before the runs they determine.
- `INFRA_LOSS` (objective, as FID §10): a kernel ending with `ERROR` before its last run, or with no output, for an infrastructure cause (install, GPU identity, Kaggle error, session kill). One identical rerun per kernel; the first valid output is authoritative; both are archived. A kernel lost again is declared to the analyzer (`--lost`); its runs are data loss. Consequences of loss: a G1 kernel → that phase is missing for every G1 state (P = 1 estimates); G2 → `RS_NOT_FIT`, no proposals; G3 → no proposals enter `C_opt`; a sealed flow_32 kernel → |Φ_s| = 2 → `SCREEN01_INCOMPLETE`; one f48 kernel → |Φ_48| = 1 (floor SE); both → `INCOMPLETE`. A divergent run, an unexpected value or a candidate the solver cannot handle is a result, never a reason to rerun.
- Engineering defect found by a smoke before freeze 2/3: fixed and re-frozen (amendment with diff and reason); rules never change.
- Amendment after freeze 2 (`REGISTERED_AMENDED`): only for a defect that prevents a pre-specified quantity, filed on #64 before any verdict-relevant output is read, never touching a rule or a pool; the original outcome (or `INCOMPLETE`) is kept beside it.
- Written-once outputs: `topmodes.json`, `rs.json`, `finalist.json`, `analysis.json`, `analysis.md` (`--out` opened exclusively); the analyzer re-derives each from the verified tables and the freezes and refuses on any mismatch.
- Stopping: the generations are finite (G1, G2, G3, F); no stage is repeated; §4.3 caps and triggers; a second `INFRA_LOSS` of the same kernel is final.
- Session budget: WaterLily 2 smokes + 9 formal kernels (+ one INFRA_LOSS rerun each). No OpenFOAM in SCREEN-01.

## 10. Freeze content
**Freeze 1** (`freeze1.json`, written by `scripts/screen01/screen01_freeze.py`): source commit; SHA-256 of this registration; `scripts/screen01/*.py`, `tests/screen01/*.py`; reused code (`fid01_designs.py`, `v18_plate.py`, `mode01_v18_prescreen.py`, `mode01_prescreen.py`, `mode01_modes.py`, `step01_states.py`, `geom02_canonical.py`, `build_xfid45_stage_v_input_2026_10_04.py`, `unc01_u3_prepare.py`, `unc01_build.py`, `unc01_verify.py`, `analyze_unc01.py`, `width_rule_study.py`, the harness tool hashes); the P0 record (`pools.json`, `rows.jsonl` for every pool member of the 10 subsets, the random pool prefix and the axial/manual states, `x1.json`, `design_check.json` with the 10 admissible designs, STL SHA-256 of every admissible member); the 22 random-control names; `states.json` for every state that can run (parent and roll = UNC-01 bytes; direction raws for the axial, manual, design, random and every admissible pool member); `oc.json`; the FID and M2 analysis SHA; python, numpy, scipy, scikit-image versions.
**Freeze 2** (`freeze2.json`): the exploration campaign (`screen01`, kernels g1k11, g1k12; g2 and g3 are added to the same campaign file as engineering amendments 2.1 and 2.2 after `topmodes.json` and `rs.json`, each amendment recording the written-once output's SHA-256) and its harness prerun freeze (smoke table SHA).
**Freeze 3** (`freeze3.json`): `finalist.json` SHA-256; the sealed campaigns `screen01_f` (flow_32) and `screen01_f48` with their prerun freezes and the flow_48 smoke; the budget decision (§4.3); the chain-check record; the XV handoff skeleton (§11) with every hash known at this point.
The analyzer refuses to run without these records and checks every campaign, table and written-once output against them. Nothing in §1-§8 changes at freeze 2 or 3.

## 11. Outputs, documentation and the XV-01 handoff record
`docs/evidence/screen01_2026_10_30/`: `decision_memo.md`, `pool_prescreen/` (P0), `oc.json`, `freeze1.json`, `freeze2.json` (+ amendments), `freeze3.json`, `states.json`, `topmodes.json`, `rs.json`, `finalist.json`, `wl/` (smokes, kernel outputs, per-kernel verify tables, budget decision), `analysis.json`, `analysis.md`, `README.md`, `SHA256SUMS`. Also `docs/STATE.md`, a `docs/phase_plan.md` entry, `docs/exploratory_index.md` (P0), comments on #64 at freeze 1, 2, 3 and the result.

**XV-01 handoff (`xv_handoff.json`, written by `main` on `SCREEN01_GAIN`, every item by content hash):** the parent and finalist NPZ (`state_sha256`, `npz_sha256`, phi Fortran- and C-order SHA), the finalist's spec `{mode: amplitude}`, direction raw SHA and step, the lattice (origin, h, shape) and masks (from the parent NPZ), the geometry gate rows (all 13 gates with values, `N_phi` and slack, smoothed-volume change, clearance margin, `min_feature_width` value, R3 descriptive), the X1 export record (STL SHA-256 at r = 8, triangles, STL volume vs the parent, the SDF chain check), the gate profile and policy hashes, the flow grids (flow_32/flow_48 case dicts), the campaign JSONs, prerun freezes, kernel outputs and verify tables, the phase sets (11-12 exploration, 13-16 / 13-14 sealed) and the rule that z is unphased, the selection rule text (§5.2-5.5) with the selection record (K_opt, K_rand, every candidate's exploration estimates, the response-surface coefficients and proposals), the sealed estimates (downforce and drag `Delta_bar`, `sigma_d`, `SE_eff`, P, the G/D/R3 labels, the flow_48 ratio), the constraint margins (sealed drag difference and its interval, volume, clearance, `N_phi` slack), the control results and labels, the §5.8 selection-bias statement (K, `sigma_disc`, `b_K`, `g_XV,exp`, the margin label), the analysis and registration SHA-256. XV-01 re-evaluates every constraint on its own arm; nothing is inherited as passed.

## 12. Plan review record
(empty — to be filled by the one three-angle plan review: numerical, controls, strategy; every finding with A/P/R and the decision)

## 13. Source review record
(empty — to be filled by the one source review of `scripts/screen01/*.py` and `tests/screen01/*.py` against revision 1)

## 14. Deviations from #64 and from the 2026-10-16 roadmap numbers (inventory)
| Source text | Here | Stricter / looser | Decided by |
| --- | --- | --- | --- |
| #64: "flow_48 で符号が一致すること" | R3 resolved sign (`> 3 SE_eff,48`), contradiction resolved, else unresolved | equal / resolution-aware | registrant |
| #64: "最終候補を flow_32 の全位相と flow_48 で確認" | the finalist is measured on 6 flow_32 phases; the decision uses the 4 sealed ones only (11, 12 reported) | stricter (unbiased) | registrant, §5.8 |
| roadmap 10-16: flow_32 P = 8, flow_48 P = 2 for the finalist | P = 4 + 2 (sealed + exploration), P = 2 | looser on count, justified by sigma_d (§4.1) | registrant |
| roadmap 10-16: 17 single-mode states x P = 4 | 10 states (5 modes, heave fixed) x P = 2 | smaller | registrant (heave, UNC-01 phases_needed) |
| #64: "手作業の基準形状" | FID C1 (visible) | defined | registrant |
| #64: "同じ予算のランダム方向" | 22 admissible Sobol points, same gates and phases, same sealed confirmation for its best | defined | registrant |
| #64 / handoff: g_min with its registered normalisation, no extra floor | G uses `g_min J_b,48` exactly, one-sided lower bound; the §5.8 margin is a label | equal (resolution added) | registrant |
| preparation note: "drag 非増加を片側の不確かさ込み" | point-sign decision with resolution labels; the optimizer targets -m_D | defined (looser than resolved non-increase, see OC) | registrant, §5.10 |
| WIDTH-RULE D-2 (R3 for M3b) | R0 kept (GEOM-03 NO_GO); bias disclosed | as registered | GEOM-03 result |
