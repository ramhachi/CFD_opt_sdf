# UNC-01 (#61, M2) registration: paired placement-phase uncertainty sigma_d on the v18 parent

Status: **PLAN, revision 1 (2026-10-20), under the PROC-01 plan review.** It becomes `REGISTERED_FROZEN` at freeze 1 (§9). It supersedes the draft `docs/unc01_preregistration_draft_2026_10_19.md`, whose §9 TODOs are closed in §10. No flag changes: all qualification flags stay false, `shape_update_allowed=false`. Integration branch `codex/kaggle-batch-migration` (not main).

Inputs (both `EXPLORATORY_COMMITTED`, binding from freeze 1):
- v18 parent `docs/evidence/v18_genesis_2026_10_19/` (state `e7376e35…`, NPZ `36967c90…`, phi Fortran `29d53b23…`, C order `0197e688…`, source spec `63fe4730…`), generator `scripts/v18_plate.py` (`4641c2f4…`).
- MODE-01 v18 basis `V18_BASIS_READY` (`docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json`): heave 31.1 mm, pitch 3.1 deg, camber 19.7 mm, reflex 29.3 mm, twist 1.1 deg, sweep 11.3 mm, control surge 31.1 mm; support probes offset_s400/s125/s050; D0 outward only.
- JOB-02 (#59, closed): per-run (x, y) placement in one kernel, run `name`, z fixed per kernel; `JOB02_GATE_PASS` (integration `58425e70`, `docs/evidence/job02_gate_2026_10_19/`).

## 1. Questions
- **Q1 (sigma_d).** The placement-phase standard deviation of same-phase paired differences `Delta_{g,m,k} = F_g(m, k) - F_g(parent, k)` (F = downforce, drag; grid g; state m; phase k) on flow_24, flow_32 and flow_48 for the v18 parent.
- **Q2 (support hypothesis, R2).** Is the relative difference error `r = sigma_d / |mean_k Delta|` smaller for the wide-support offset D0 than for the small-support Gaussian offset (sigma 0.05 m), with sigma 0.125 m and the wide analytic mode L reported between?
- **Q3 (optimisation grid, R3).** Do flow_32 and flow_48 agree on the phase-mean difference of L; does the GRID-02 flow_24 outlier persist on v18?
- **Q4 (E2 and M3a inputs).** S_b, S_c of the E2 rule, the paired-difference analogue S_d, the OpenFOAM retention of each difference, and the summary coefficients of §6.4 that the M3a (#62) registration takes.

M2 does not optimise, accept a shape or set an M3a threshold; it fixes numbers. Claim ceiling: placement-phase spread of Re = 80 reduced-laminar WaterLily and coarse-mesh OpenFOAM differences on one analytic parent, uncertified geometry; no physical downforce, no grid convergence, no gradient.

## 2. Stages (PROC-01)
| Stage | Content | Registration status | Approx. T4 time |
| --- | --- | --- | --- |
| U0 | harness smoke of the U01 campaign (v18 parent, native phase, flow_24) plus the U0 gate on the native parent rows of U01 (flow_24, flow_32, flow_48), §5.1 | engineering gate inside this registration | in U01 |
| U1 | U01 campaign: flow_32 native phase: parent, D0 +3 mm, the five L candidates at +A* and -A*; bridge: parent and D0 at the GRID-02 placement (x, y + 12.5 mm) on flow_24 and flow_32 and native on flow_24; flow_48 native parent (for U0) | `EXPLORATORY_COMMITTED` (selection input only; never cited as sigma_d) | 2.7 h incl. setup |
| U2 | §4 design | `REGISTERED_FROZEN` | 12.4 h incl. setup (pessimistic per-state times) |
| U3 | OpenFOAM coarse Stage V mesh, the U2 flow_32 states x 32 rigid shifts (Kaggle CPU) | `REGISTERED_FROZEN` | CPU only, ~3.2 h |

U0 and U1 share one harness campaign (`docs/harness/unc01_u01_campaign.json`) to save one Kaggle setup: the harness smoke of that campaign runs the v18 parent on flow_24 (the cheapest kernel's first state) and is checked against §5.1 (finite, drift, sign, size) before any formal U01 kernel is pushed; the U01 numbers are read only after the U0 gate has passed on all three grids. U0 failing stops the study (§8).

## 3. States (only prescreen-tested, gate-clean points)
Every state is built through the harness state model: analytic phi (`v18_plate.mode_phi`) → direction `d / max|d|` (float32, zero off the active set), step `1000 max|d|` mm, sign +1 → `construct_state(parent, d, step, +1)`; this is exactly what the runner regenerates (`step01_states.perturb` on the parent and direction raws). `scripts/unc01_build.py states` refuses unless every state's Fortran phi SHA equals the prescreen's gated bytes and the runner-side regeneration reproduces it (done 2026-10-20: 15/15 identical, `docs/evidence/unc01_2026_10_20/states.json`). Each non-parent state has its own direction raw (1.5 MB, `docs/evidence/unc01_2026_10_20/inputs/`).

| State | Prescreen point | Role | max change / support |
| --- | --- | --- | --- |
| `v18__parent` | parent | baseline of every pair | — |
| `v18__D0_p3` | thickness_D0 +3 mm (outward) | wide-support arm (support 1.0); no -A point (inward fails `near_zero_gradient_band`) | 3.0 mm / 1.00 |
| `v18__s125_m5` | offset_s125 -5 mm (inward; the only clean sign) | medium-support arm | 4.9 mm / 0.12 |
| `v18__s050_m5` | offset_s050 -5 mm (inward, same sign as s125) | small-support arm | 4.4 mm / 0.02 |
| `v18__<L>_p<A*>`, `v18__<L>_m<A*>` | L at +A*, -A* | wide analytic arm and the -A point | see prescreen |
| `v18__surge_p31.1`, `v18__surge_m31.1` | surge +-31.1 mm | control C (the only gate-clean control) | 31.0 mm / 0.96 |

L candidates (U1 only): pitch 3.1 deg, camber 19.7 mm, reflex 29.3 mm, twist 1.1 deg, sweep 11.3 mm (heave is excluded: a weak lever at h/c about 0.53 and coupled to the ground boundary).
**L selection rule (fixed here, before U1):** L = the candidate with the largest `|F32(L+, k0) - F32(L-, k0)| / (2 |F32(parent, k0)|)` for downforce on flow_32 at the native phase; ties (equal to 1e-12 relative) go to the order pitch, camber, reflex, twist, sweep. Computed by `scripts/analyze_unc01.py u1`; nothing else in U1 changes the design.
The draft's U1 bridge used D0 +5 mm, which the prescreen never tested; it is D0 +3 mm here. The draft's `offset_s400` reserve is dropped: its trigger ("s125 and D0 unresolved at one phase") has no defined meaning for a deterministic solver at one phase, so the support axis is fixed now (D0, s125, s050).
Confounds of Q2, stated in advance: D0 is outward and changes the smoothed volume by +7.6 % while s125/s050 are inward and nearly volume-neutral; the amplitudes differ (3 vs 4.9 vs 4.4 mm maximum change). Surge is a control by physics only: a 31 mm downstream shift in a finite box changes the forces slightly and, unlike a placement phase, it moves the body inside the SDF lattice.

## 4. U2 design
- **Phases.** Phase k moves `W4_CANONICAL_ORIGIN_M` by `(f_kx, f_ky, 0) h_g` with `f_k = frac(k (0.7548776662, 0.5698402910))` (R2 low-discrepancy sequence) and `h_g` the flow spacing of grid g (1/30, 1/40, 1/60 m); z (ride height) never moves. **U2 uses k = 1..6 on flow_24 and flow_32 and k = 1..4 on flow_48**, disjoint from the native phase k = 0 of U1, so the L selection does not enter the U2 data (no winner's curse in sigma_d or in the mean). The same phases are used by every state of a grid (common random numbers, R4).
- **States per grid.** flow_32: parent, D0, L+, L-, s125, s050, C+, C- (8 x 6 = 48 runs); flow_24 (demoted, R3; kept for Q2's second grid and the outlier question): parent, D0, L+, s050 (4 x 6 = 24); flow_48: parent, L+ (2 x 4 = 8).
- **Kernels** (`docs/harness/unc01_u2_campaign.json`, built by `scripts/unc01_build.py campaign u2 --L <L>`): one kernel per (grid, phase block) so that every pair is computed inside one kernel; runs are phase-major (all states of phase k, parent first, then phase k+1) and named `<state>__k<k>` (JOB-02 `name`).

| Kernel | Grid | Phases | Runs | per-state timeout / aggregate cap / kernel timeout (s) | Estimate (s, pessimistic) |
| --- | --- | --- | --- | --- | --- |
| f48a | flow_48 | 1, 2 | 4 | 6000 / 11000 / 14400 | 9,360 |
| f48b | flow_48 | 3, 4 | 4 | 6000 / 11000 / 14400 | 9,360 |
| f32a, f32b, f32c | flow_32 | (1, 2), (3, 4), (5, 6) | 16 each | 900 / 9000 / 12000 | 6,640 each |
| f24 | flow_24 | 1..6 | 24 | 900 / 6000 / 9000 | 4,320 |
| f24r (alternative) | flow_24 | 1..6 | 12 (parent, L+) | 900 / 3600 / 6600 | 2,160 |
Per-state times: GRID-02/JOB-02 maxima (flow_24 176 s, flow_32 414 s, flow_48 2,340 s), rounded up; setup about 260 s per kernel. flow_48 is split so that no kernel exceeds about 2.7 h of solver time (Kaggle session limit 12 h, two concurrent GPU sessions).
- **Budget cap: 13 GPU h for U2** (kernel session wall time, from the kernel logs). Push order: f48a, f48b, then f32a, f32b, then f32c and finally the flow_24 kernel. Before pushing it: if the session time of the finished U2 kernels plus the nominal estimate of the running ones plus 24 x 180 + 260 s exceeds 13 h, f24r is pushed instead of f24 (recorded as a deviation; Q2's flow_24 condition then reads `NOT_MEASURED`). Exactly one of f24/f24r is pushed.
- Weekly quota: U01 + smokes + U2 is about 16 GPU h, inside one Kaggle week (~30 h). Backend-switch trigger (STATE.md): if any kernel waits more than 24 h in the queue, or the week's need exceeds the quota, stop and report instead of continuing.

## 5. Rules (computed by the frozen `scripts/analyze_unc01.py`)
### 5.1 U0 gate (engineering)
On the harness smoke output (flow_24) and then on the native parent rows `v18__parent__k0` of U01 on flow_24, flow_32 and flow_48: harness `verify` passes (smoke: `verify --smoke`); the job summary flags `finite_u`, `finite_p`, `finite_forces` are true; the relative half-window drift `|mean[80,100] - mean[100,120]| / |mean[80,120]|` (clipped time-weighted means, host-recomputed from the force CSV) is <= 0.02 for drag and for downforce (the W3/W4 rule `relative_half_window_drift_max`); downforce > 0; and `0.5 <= F_v18 / F_v17 <= 2` against the native v17 parents of the same grid (flow_24 0.33188 N and flow_32 0.36178 N, OPT-01 Stage B / JOB-02; flow_48 0.36435 N, GRID-02). Any failure: `U0_FAIL`, stop (§8).

### 5.2 U2 estimators (each grid g, state m ≠ parent, response r ∈ {downforce, drag}, P_g phases)
- `Delta_bar = mean_k Delta`, `sigma_d` = sample SD over k (P_g - 1 dof), `SE = sigma_d / sqrt(P_g)`.
- 90 % intervals: `sigma_d` by chi-square, `[sigma_d sqrt((P-1)/chi2_{0.95,P-1}), sigma_d sqrt((P-1)/chi2_{0.05,P-1})]`; `Delta_bar +- t_{0.95,P-1} SE`.
- `resolved` iff `|Delta_bar| > 3 SE` (strict).
- `r = sigma_d / |Delta_bar|`, with `r_lo = sigma_lo / (|Delta_bar| + t SE)` and `r_hi = sigma_hi / (|Delta_bar| - t SE)` (`+inf` if the denominator is <= 0). An unresolved difference keeps its interval (its `r_hi` is infinite); it is not removed from the ordering.
- Descriptive: the parent's own phase SD `sigma_F` (absolute placement noise) and `sigma_d / (sqrt(2) sigma_F)` (the common-phase reduction); the drift of every run; for L: the even part `(Delta(L+) + Delta(L-)) / 2` and its SD over k (curvature).
- The phases are a deterministic low-discrepancy set, not random draws; the chi-square and t intervals treat them as exchangeable samples (an approximation, stated with every interval). The ride-height (z) placement is not sampled: sigma_d is the in-plane placement spread only.

### 5.3 Q2 (downforce registered; drag reported under the same rule as `Q2_drag`)
- `SUPPORTED` iff on flow_32 `r_hi(D0) < r_lo(s050)` **and** on flow_24 `r(D0) < r(s050)` (point estimates; `NOT_MEASURED` if f24r replaced f24, and then Q2 is at most `SUPPORTED_FLOW32_ONLY`).
- `NOT_SUPPORTED` iff on flow_32 `r_hi(s050) < r_lo(D0)`.
- Otherwise `INCONCLUSIVE`. s125 and L+ are reported with their intervals; the sign and volume confounds of §3 are printed with the label.
- `Q2_OF`: the same rule on the U3 OpenFOAM differences (no second grid), reported.

### 5.4 Q3 (downforce registered; drag reported as `Q3_drag`)
- L+ on flow_32 vs flow_48: `CONFIRMED` iff `|Delta_bar_32 - Delta_bar_48| <= 2 sqrt(SE_32^2 + SE_48^2)` and `Delta_bar_32 / Delta_bar_48` ∈ [0.8, 1.25]; `UNRESOLVED` if either difference is unresolved; else `NOT_CONFIRMED`. The band is the R3 working tolerance (GRID-02 found r = 1.007 for flow_32/flow_48 on v17); it is a registrant choice.
- flow_24 vs flow_32 for L+ and for D0 with the same rule (flow_32 as reference): `FLOW24_CONSISTENT` if both pass, `FLOW24_OUTLIER` if either fails with both differences resolved, else `FLOW24_UNRESOLVED`; with f24r only L+ enters.

### 5.5 Q4: E2 inputs (`docs/architecture_effectiveness_2026_09.md` §9: `I_f = (J_b,f - J_c,f) / max(|J_b,f|, J_scale)`, `S_b = |J_b,f - J_b,m| / max(|J_b,f|, J_scale)`, `S_c = |J_c,f - J_c,m| / max(|J_b,f|, J_scale)`, Go if `I_f > 2 max(S_b, S_c)`)
- f = flow_48, m = flow_32, b = parent, c = L+, J = the phase mean of the response on each grid's own U2 phases (minimised J = -downforce, and drag; the absolute values make the sign convention irrelevant).
- `J_scale = 3.6e-3 N` for both responses (1 % of the v17 flow_48 parent downforce 0.36435 N, GRID-02: fixed before any M2 number; the E2 text requires only a positive value fixed before the results; it binds only if |J_b,48| < 3.6e-3 N).
- Recorded: `S_b`, `S_c`, the paired analogue `S_d = |Delta_bar_48 - Delta_bar_32| / max(|J_b,48|, J_scale)`, `I_f(L+)` (descriptive: L is a response probe, not a candidate), and the two implied minimum gains `2 max(S_b, S_c)` (literal E2) and `2 S_d` (paired). Whether M3a uses S_b/S_c or S_d is for the M3a registration.

### 5.6 U3 (OpenFOAM)
For each U2 flow_32 state m and the 32 matched shifts j: `Delta_OF = F_OF(m, j) - F_OF(parent, j)`; `Delta_bar_OF`, `sigma_d,OF` (31 dof), SE and resolution as §5.2; retention `rho_m = Delta_bar_OF / Delta_bar_32` (WaterLily flow_32 U2 mean), reported when both are resolved; sign agreement reported. A failed case (any stage) removes that shift from every state's pairs of that response (matched-pairs only); fewer than 24 complete shifts: U3 `INCOMPLETE`.

### 5.7 M3a coefficient summary (§6.4 values, fixed formulas)
`analyze_unc01.py` writes, for downforce and for drag: (a) `sigma_d_wide_32` = the largest sigma_d on flow_32 over {D0, L+, L-, C+, C-} and its 90 % upper bound; (b) `r` per state and grid with intervals; (c) `phases_needed(Delta) = ceil((3 sigma_d_wide_32 / Delta)^2)` evaluated at |Delta| = 1e-3, 3e-3 and 1e-2 N; (d) the grid spread `|Delta_bar_32 - Delta_bar_48| / |Delta_bar_48|` of L+; (e) retention rho per state with the OpenFOAM SE; (f) S_b, S_c, S_d. M3a decides which of these it adopts and how; M2 recommends nothing beyond printing them.

## 6. U3 recipe (closes draft TODO 5)
- Mesh and runner: the XFID X3 formal recipe unchanged: `infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py` copied byte for byte except the bound criteria SHA (new kernel `infra/kaggle/kernel_unc01_u3/`, slug `ramhachi888/cfd-opt-sdf-unc01-u3`), case template = the Round 5 template (hash-identical, minus the candidate STL), OpenFOAM v2512 with the registered jammy/noble locks, blockMesh 25 x 13 x 9 (0.2 m), snappy surface level (2 3) (25-50 mm surface cells), simpleFoam, forces from the last-25 % iteration window (force_n_per_coefficient 0.32). X3 calibration: 224/224 cases completed, about 42 s per case, mesh noise sigma_e downforce 5.9e-4 N, drag 1.05e-4 N per case.
- STL export of the v18 states: the GEOM-02 / XFID r = 8 practical pipeline on the harness bytes (`geom02_canonical.export_from_state`: trilinear refinement r = 8, marching cubes, sub-cell components removed, orientation by phi sidedness) and the X1 practical gate (`build_xfid45_stage_v_input_2026_10_04.gates`: watertight, manifold, positive volume, clearance, orientation without flips) on the double mesh and on the float32 STL. A state that fails is not run (recorded `NOT_RUN_EXPORT_GATE`); if the parent fails, U3 is `INCOMPLETE`.
- Phase ensemble: 32 rigid shifts = 16 mirror pairs of the X3 generator (Halton bases (2, 3, 5) magnitudes 0.5-4 mm per axis, bases (7, 11, 13) signs) at Halton indices **33-48**, disjoint from X2/X3 (1-32); identical shifts for every state; pair-major order (all 8 states of a pair before the next pair) so a partial run stays balanced. 8 x 32 = 256 cases, about 3.2 h; launch deadline 9 h; stop after 3 consecutive failures.
- Size: with the X3 per-case noise and independent states, the paired SD is about 8e-4 N and the SE of a 32-shift mean about 1.5e-4 N; the X3 D0 response on v17 was 7.7e-4 N per mm, so D0 +3 mm is expected near 15 SE. 32 shifts is the X3 size and fits one CPU session.

## 7. What was visible before this registration
The prescreen and genesis records (geometry only), the GRID-02, JOB-02, XFID and OPT-01 force records on v17, and the per-state solver times. No v18 force exists. The L selection rule, phases, states, kernels, estimators, decision rules, J_scale and the U3 recipe are fixed before any v18 solver run.

## 8. Stopping rules (fail-closed)
- U0 fails: `U0_FAIL`, stop, diagnose; no U1 selection or U2 under this registration.
- A U01 kernel fails `verify`: U1 may be re-run once under a new slug suffix (exploratory, recorded); the U0 gate needs all three native parent rows.
- Any U2 `harness.py verify` failure: that kernel's rows are `INCOMPLETE`; no silent re-run; a re-run needs an amendment (`REGISTERED_AMENDED`) and keeps the failed attempt in evidence. A grid with an incomplete phase set gets no estimate; any Q that needs it reads `INCOMPLETE`.
- After the first U2 kernel is pushed no state, phase, amplitude, rule or script changes. The analysis is written once (one `analyze_unc01.py u2` run on the verified tables; the output is committed as is).
- Budget cap §4; the queue/quota trigger §4.

## 9. Freeze content
**Freeze 1** (`docs/evidence/unc01_2026_10_20/freeze1.json`, before the U01 smoke): this registration's SHA-256; `scripts/unc01_build.py`, `scripts/analyze_unc01.py`, `scripts/unc01_u3_prepare.py`, `tests/test_unc01.py`; `states.json` and `regate.json` (the prescreen gate stack re-run on the harness bytes of every registered state, identical to the prescreen rows); the U01 campaign and its harness prerun freeze; the v18 parent and generator hashes; the JOB-02 integration commit `58425e70` and its gate result; the statement that P22-v2 is applied unchanged to a second parent and is not binding by design (v18 N_phi 7544 vs cap 8272), so the 10 % smoothed-volume band carries the volume constraint. At freeze 1 the MODE-01 basis becomes binding (#60 is closed).
**Freeze 2** (`freeze2.json`, the U2 freeze, before the first U2 kernel): the U1 selection record (L), the U2 campaign (built by the frozen builder with that L) and its harness prerun freeze (after its own smoke), the U3 criteria SHA (states, STL hashes, shifts) and the bound U3 runner. Nothing in §1-§8 may change at freeze 2.

## 10. Draft TODOs (draft §9), closed
0. min_feature_width caveat: only prescreen-tested, gate-clean points are used (§3) and the freeze re-gates them (`regate.json`); the smooth-body width rule is for the M3 registrations (separate session, width-rule), not M2.
1. JOB-02 done (`JOB02_GATE_PASS`, merged `58425e70`); the kernel layout uses run names and per-run (x, y) origins; z is one value per kernel (the schema rejects otherwise, `campaign_schema.validate_kernel`).
2. Harness state model: `unc01_build.py states` built all 15 states and the runner regeneration on the written raws; 15/15 Fortran phi SHAs equal the prescreen gated bytes; the U01 campaign passes `validate_campaign`.
3. `W4_SOURCE_SURFACE_SHA256 = 63fe4730ad6216fe4d224ac7f729603f2587bf1b28c507ef3070bbd2aaf30e0e` (v18 `source_sha256`), `W4_CANONICAL_STATE_LABEL = v18` (echo-only in the jobs; the verifier compares them with the campaign).
4. flow_48: 8 runs split into two kernels of 4 runs (9,360 s pessimistic each, 14,400 s kernel timeout).
5. U3: §6.
6. J_scale fixed at 3.6e-3 N against the E2 text (§5.5); the U0 drift rule is the existing 0.02 half-window rule (§5.1).
7. Plan review: §11 (this revision is what the reviewers read). Source review: recorded in freeze 1.

## 11. Plan review record
(to be filled from the three-angle review of revision 1)
