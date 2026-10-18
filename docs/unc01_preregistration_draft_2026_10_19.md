# UNC-01 (#61, M2) pre-registration — DRAFT (2026-10-19, not frozen)

Status: **DRAFT**. Nothing here is registered, frozen or reviewed as a source. It becomes `REGISTERED_FROZEN` only after the TODOs in §9 are closed, the freeze in §8 is written, and the PROC-01 reviews (one three-angle plan review, one source review) are recorded. No Kaggle run is authorised by this draft. All qualification flags stay false; `shape_update_allowed=false`.
Inputs: the v18 parent (`docs/evidence/v18_genesis_2026_10_19/`, phi Fortran SHA `29d53b2318c54548da321f265aa2102d59e24d96bbd04fb2dd70d62fbc10c82a`) and the MODE-01 v18 basis proposal `V18_BASIS_READY` (`docs/evidence/mode01_v18_prescreen_2026_10_19/`: heave 31.1 mm, pitch 3.1 deg, camber 19.7 mm, reflex 29.3 mm, twist 1.1 deg, sweep 11.3 mm, control surge 31.1 mm; plan `docs/v18_mode01_plan_2026_10_19.md`), both `EXPLORATORY_COMMITTED`; JOB-02 (#59) per-run placement (branch `feat/job02-per-state-placement`, gate `docs/evidence/job02_gate_2026_10_19/`, result pending at drafting time).

## 1. Questions
- Q1 sigma_d: the placement-phase uncertainty of same-phase paired differences `Delta_{g,m,k} = F_g(m, k) - F_g(parent, k)` (F = downforce, drag; grid g; mode state m; phase k) on flow_24, flow_32 and flow_48 for the v18 parent.
- Q2 support hypothesis (R2): is the relative difference error `r_{g,m} = sigma_d / |mean_k Delta|` smaller for wide-support modes than for small-support ones, on one kind of mode (normal offsets with Gaussian width sigma = infinity (D0), 0.125, 0.05 m; 0.4 m in reserve), with the wide analytic mode L as a second axis?
- Q3 optimisation grid (R3): do flow_32 and flow_48 agree on the phase-mean difference of the large modes; does the GRID-02 flow_24 outlier persist on v18?
- Q4 inputs for M3a: S_b, S_c of the E2 rule and their paired-difference analogue (§6).
M2 does not optimise, accept a shape, or set any threshold itself; it fixes numbers that the M3a (#62) registration uses.

## 2. Stages (PROC-01)
| Stage | Content | Status | Approx. T4 time |
| --- | --- | --- | --- |
| U0 smoke | v18 parent, native phase, flow_24/32/48: finite, stationary in [80, 120] tU/L, downforce sign and size, harness `smoke` + `verify --smoke` | engineering gate | 0.8 h |
| U1 pilot | one phase (native), flow_32: parent, D0 +5 mm, every proposed basis mode at +A* and -A*; plus a GRID-02-style bridge: parent and D0 +5 mm at native and (h/2, h/2, 0) on flow_24 and flow_32 | `EXPLORATORY_COMMITTED` (selection input only, §3) | 2.5 h |
| U2 main | §4 design | `REGISTERED_FROZEN` | 11.4 h |
| U3 OpenFOAM | the same paired differences on the coarse Stage V mesh, phase ensemble (Kaggle CPU) | `REGISTERED_FROZEN` (same registration) | CPU only |
U1 is the strategy review's pilot (v18 plan review, finding 3) and bridge (finding 1); its numbers are never cited as sigma_d.

## 3. Mode and amplitude selection (rule fixed before U1)
- Large-support arm L: the basis mode with the largest `|Delta downforce| / |F_parent|` in U1 among the wide members other than heave (pitch 3.1 deg, camber 19.7 mm, reflex 29.3 mm, twist 1.1 deg, sweep 11.3 mm; heave is a weak lever at h/c ~ 0.53 and is coupled to the ground boundary) at its A*. Ties: AMPS order of the prescreen.
- D0 arm: `thickness_D0` +3 mm (its largest gate-clean point; the inward sign fails `near_zero_gradient_band` on v18, so D0 has no -A point).
- Support axis (same kind of mode as D0): `offset_s125` -5 mm (only the inward sign is gate-clean), `offset_s050` -5 mm (both signs clean; the inward sign is taken so the medium and small arms have the same sign), `offset_s400` +5 mm in reserve (§4). D0 is outward: the sign difference between the D0 arm and the s125/s050 arms is a confound of Q2, stated in the analysis.
- Control C: `surge` +-31.1 mm (the only gate-clean control; `twist_anti`, the mirror-odd control preferred by the plan review, fails `min_feature_width` at every tested point). Surge is a control by physics only (a 31 mm downstream shift in a finite box changes the forces slightly); unlike a placement phase it moves the body inside the SDF lattice, while a phase moves body and lattice together relative to the flow grid.
- -A point: the L arm at -A*.
- Only prescreen-tested (mode, amplitude) points are allowed; the U2 freeze re-gates the exact harness bytes.

## 4. Main design (U2)
- Phases: P = 6 per grid, common to all states of that grid (common random numbers, R4). Phase k shifts `W4_CANONICAL_ORIGIN_M` by `(f_k,x, f_k,y, 0) * h_flow` with `f_k = frac(k * (0.7548776662, 0.5698402910))`, k = 0..5 (k = 0 native); z is fixed per kernel (ride height). flow_48 uses k = 0..3.
- States per grid: flow_32: parent, D0, L+, L-, s125, s050, C+, C- (C = surge; 8 states x 6 phases = 48 runs); flow_24 (demoted, R3; kept for the outlier question): parent, D0, L+, s050 (4 x 6 = 24 runs); flow_48: parent, L+ (2 x 4 = 8 runs, as #61). `offset_s400` is measured only if U1 shows the s125 and D0 responses unresolved at one phase (then it replaces s125 on flow_32; decided at the freeze, before U2).
- Budget (per-state solver time flow_24 175 s, flow_32 400 s, flow_48 2,200 s): flow_32 5.3 h, flow_24 1.2 h, flow_48 4.9 h, total 11.4 h solver time plus setup, inside one Kaggle week (30 h, 2 concurrent sessions). **Cap: 13 GPU h for U2**; above it flow_24 is cut to parent, L+ first, recorded as a deviation.
- Kernel layout: one kernel per (grid, phase block) so that one kernel carries the parent and all states of the same phases; run names `<state>__k<k>` (JOB-02 `name`).

## 5. Estimators and decisions (fixed before U2)
- `Delta_bar_{g,m} = mean_k Delta`, `sigma_d,{g,m}` = sample standard deviation over k (P - 1 dof), 90 % CI by chi-square; `r_{g,m} = sigma_d / |Delta_bar|`; drag and downforce separately.
- Q2: `SUPPORTED` if on flow_32 the upper 90 % bound of sigma_d / |Delta_bar| for D0 is below the lower bound for s050 (s125 reported between them), and D0 < s050 also holds on flow_24; `NOT_SUPPORTED` if the order is reversed with non-overlapping bounds on flow_32; otherwise `INCONCLUSIVE`. Resolution: a difference with `|Delta_bar| < 3 sigma_d / sqrt(P)` is reported as unresolved and excluded from the ordering.
- Q3: flow_32 is confirmed for v18 if for L+ `|Delta_bar_32 - Delta_bar_48| <= 2 sqrt(sigma_32^2 / 6 + sigma_48^2 / 4)` and the ratio is within [0.8, 1.25]; flow_24 (L+, D0) is reported against the same rule with flow_32 as reference (the GRID-02 outlier question).
- Control: surge +-31.1 mm is reported with its own sigma_d; it has no exact-zero expectation and is not used in the Q2 ordering.
- M3a note (strategy review S4): the M3a registration should report retention per mode family, not pooled.

## 6. E2 inputs (Q4)
The E2 rule (`docs/architecture_effectiveness_2026_09.md`) uses fine/medium absolute differences: `I_f = (J_b,f - J_c,f) / max(|J_b,f|, J_scale)`, `S_b = |J_b,f - J_b,m| / ...`, `S_c = |J_c,f - J_c,m| / ...`, Go if `I_f > 2 max(S_b, S_c)`. With f = flow_48, m = flow_32 M2 records S_b and S_c (phase means) **and** the paired-difference analogue `S_d = |Delta_bar_48 - Delta_bar_32| / max(|J_b,48|, J_scale)`. On v17 the absolute grid shift was 8-10 %, so the literal E2 form would require improvements of that order; whether M3a uses S_b/S_c or S_d is a decision for the M3a registration, made before its runs and recorded there. `J_scale` is fixed in the U2 freeze as 1 % of the U0 parent downforce on flow_48 (TODO: confirm against the E2 text before freezing).

## 7. Stopping rules (fail-closed)
- U0 fails (non-finite, non-stationary beyond the registered drift rule, verify failure): stop, diagnose, no U1/U2 under this registration.
- Any `harness.py verify` failure in U2: the kernel's rows are `INCOMPLETE`; no silent re-run; a re-run needs an amendment (`REGISTERED_AMENDED`) and keeps the failed attempt in evidence.
- The analysis is written once; no amplitude, phase or state change after the first U2 kernel starts.
- Budget cap §4.

## 8. Freeze content (to be written)
v18 parent bytes (state, NPZ, Fortran/C phi SHA-256) and `scripts/v18_plate.py` SHA-256; the selected states (mode, amplitude, direction raw SHA-256, state identity) built through the harness state model (`v18_plate.harness_state`: `construct_state(parent, float32(phi - parent), 1000 mm, +1)`), re-gated in the freeze with the same gate stack as the prescreen; the phase list; the campaign JSON; JOB-02 commit and gate result; the analysis script SHA-256; the statement that P22-v2 is applied unchanged to a second parent and is not binding by design (v18 N_phi 7544 vs cap 8272), so the 10 % smoothed-volume band carries the volume constraint.

## 9. TODO before freezing
0. Gate-limit caveat: `min_feature_width` fails at 40-50 % of sub-cell placements of v18 (prescreen README); the M2 freeze may only use the tested points above, and the M3 registrations must decide how a smooth-body width rule is handled before any optimiser runs on v18.
1. JOB-02 (#59): wait for `JOB02_GATE_PASS` and its merge; use its `runs[].name` and per-run x/y origin; confirm z cannot vary within a kernel.
2. Harness state model (checked 2026-10-19, keep re-checking at the freeze): the schema requires `step_mm > 0`, `sign` = +-1 and a declared direction raw per perturbation (`src/cfd_harness/campaign_schema.py:185`); the builder's `step01_states.perturb` is the same float64 formula as `construct_state` and leaves inactive nodes unchanged because the direction is zero there, so the gated prescreen bytes (`v18_plate.harness_state`: direction `d / max|d|`, step `1000 max|d|` mm, sign +1) are what the harness builds. Each analytic state needs its own direction raw (about 1.5 MB each). Remaining: build one campaign and compare the built state identities with the prescreen hashes.
3. `W4_SOURCE_SURFACE_SHA256` is echo-only in the jobs (`scripts/waterlily_grid02_job.jl:223` and the flow_24/flow_32 jobs write it into the summary; the harness compares it with the env, `campaign_schema.py:326`): set it to the v18 `source_sha256` (parameter-spec hash) and `W4_CANONICAL_STATE_LABEL=v18`.
4. flow_48 job (`scripts/waterlily_grid02_job.jl` with `GRID02_CASE=flow_48`): confirm kernel time limits with 2 states x 4 phases (8 x 2,200 s = 4.9 h) split over kernels within the Kaggle session limit.
5. OpenFOAM U3: choose the coarse-mesh recipe (`infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/`) and the STL export of v18 states (XFID practical gate) and its phase ensemble size.
6. Confirm `J_scale` against the E2 source and the drift rule used by U0.
7. Plan review (three angles) and source review per PROC-01.
