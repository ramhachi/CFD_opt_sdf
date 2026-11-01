# RE-01 plan rev 0: governance and controls review (adversarial)

Reviewer role: governance and controls angle of the one PROC-01 three-angle plan review.
Plan: `docs/re01_plan_2026_11_01.md` (cited as P:line). Support: `docs/evidence/re01_plan_2026_11_01/fable_analysis.md` (F:line).
Precedents: `docs/screen01_registration_2026_10_30.md` (S:line), `docs/fid01_registration_2026_10_21.md` (FID:line), `docs/phase_plan.md`, `docs/STATE.md`, `docs/exploratory_index.md`, issues #65, #66, #69, `docs/xv01_registration_requirements_2026_10_22.md`.
Read-only review. Two small calculations were run to check the plan's own numbers (power of the 3 SE rule at the stop target; cost of Stage 0). They are inline below and reproducible from F:108-118 and F:133.

## Verdict: GO_AFTER_FIXES

The concept (a staged Re ladder on frozen v18 designs, WaterLily first, Stage 0 exploratory, label families, claim ceiling written first) is sound and reviewable in outline. The decision layer (P:97-147) is not yet registrable: the label algebra has holes, the stop target and the PASS threshold are inconsistent in power, one gate misfires by construction at the steady rung, the in-run adaptive window cannot coexist with frozen kernel caps, and Stage 0 has no charter. PROC-01 allows one three-angle plan review per study (phase_plan.md:7489), so every P1 below has to be closed in rev 1 and recorded in an `adoption.md`, and the end-to-end operating characteristics (G3) have to exist before freeze 1. If those OC runs show that R2/R3 cannot be powered inside the cap, the right response is to shrink the claim (R1, or R1+R2), not to loosen a threshold.

P1 findings: G1-G10. P2: G11-G21. P3: G22-G25.

---

## P1 (must fix before registration)

### G1 (P1). Stage 0 has no charter; it contradicts PROC-01 and the FID-01 P0 precedent it claims to follow
Evidence: P:163 ("FID-01 の P0 OpenFOAM probe と同じ扱い"), P:165-169 (force values are stored, statistics are read), P:171 (rungs and grids may be changed "登録の前に"), P:102 (burn-in from Stage 0), P:100 (SE target relative to the parent force), P:175 and P:177 (Stage 0 source is built before any review; source review covers only analyzer and checker). Precedent: FID:21 and FID:217 (P0 probe read as statuses, cells, times only; "force fields removed by the registered sanitiser before anything was read"); `docs/exploratory_index.md:21` ("sanitised: no force field", "engineering timing only"). Rule: `docs/phase_plan.md:7488` (an exploratory result "never feeds a qualification flag, a threshold, a gate").

Problem:
- FID-01's P0 fed the registration only through statuses. RE-01's Stage 0 feeds force-derived statistics (rms, tau_int, drift, Strouhal number, parent grid gap) into the window, the SE target, the caps and the choice of rungs and grids. That is a different and larger channel, and the plan says it is "the same".
- "Parent only" keeps Stage 0 blind to the estimand (the design-minus-parent difference), but not to the study design. Leak channels, all through the parent: (a) rung and grid placement: the registrant sees which rung is steady, which flow_32/flow_48 pair already disagrees, and can drop or move rungs so that clean outcomes are more likely; (b) the OpenFOAM V1 convergence result decides whether OpenFOAM is a formal component of R1 PASS (P:114, P:168), i.e. the PASS definition is chosen after seeing a solver outcome; (c) the SE target in newtons depends on the parent force seen in Stage 0; (d) if the Stage 0 phase is one of the registered phases, the stored parent trajectory is the first block of a registered parent run (runs are deterministic), so registered data are pre-read; (e) the saved C_L and C_D(Re) are also a listed final descriptive output (P:126-131).
- "Change rungs or grids before registration if needed" (P:171) is an open door: substitution and addition of rungs are possible, not only dropping.
- The case contract and job source used in Stage 0 are built before the registration (P:175) and are not covered by the source review (P:177). The registered runs would then use bytes the probe did not.

Fix (rev 1 text; commit and hash a Stage-0 charter before the first Stage-0 run):
1. Preferred option: take the window, burn-in and caps from a fixed registered schedule justified by F:131-134 and power (G3), and use Stage 0 only for feasibility (does 1.8.0 run stably at each Re, wall, GPU memory, Poisson iteration counts, OpenFOAM convergence yes/no), read through a sanitiser exactly as FID-01 did. Raw forces stay sealed (hash only) until the registered analysis. If force statistics are needed, option 2.
2. Alternative: force-derived statistics may set only engineering parameters (burn-in, window, caps) through formulas written in the charter, e.g. `W = smallest multiple of 100 CU such that predicted 3 SE_eff <= 0.7 * g_min * J_parent(Re)`, with decision thresholds (3 SE, tau, sign rules, retention bands) explicitly not derived from Stage 0. Record a decision in phase_plan that this reading of PROC-01 is intended, because the letter of phase_plan.md:7488 says "never feeds a threshold".
3. Modifications after Stage 0 are drop-only under closed triggers (divergence or non-finite force; memory; wall; viability rule of G3). No new rung, grid or Re value may be added or substituted; a dropped rung is declared in the registration with its Stage-0 record.
4. The charter lists the exact run table (Re, grid, phase, window, parent only; no roll, no repeat, no design state of any kind), the closed list of quantities read, the sanitiser, the mapping formulas, the OpenFOAM V1 convergence criterion and the fallback (P:168, P:202) as a rule written before the run, and the Stage-0 phase.
5. Stage 0 uses a phase that is not one of the registered RE-01 phases and is not reserved (see G19), for example one of k = 1-6 (already used at Re 80, so no collision at other Re).
6. Hypotheses H1-H4 (F:232) with numeric bands, and the baseline estimator files by SHA-256, are registered before Stage 0, so that nothing about the predictions is written after the probe has shown the regime.
7. The case contract and job (Re parameter, window schedule) are frozen at Stage 0 and bound at freeze 1 by hash; any later change re-runs the Stage-0 smoke. The source review covers them, not only `analyze_re01.py` and the checker.
8. The `exploratory_index.md` rows are appended before the runs (denominator visible, including failures).

### G2 (P1). The label algebra is incomplete, not mutually exclusive, has no INVALID and contradicts itself on RE_BREAKS_AT_1
Evidence: P:109-124 (rung and overall labels), P:146, P:135, P:140. Precedent: S:17 and S:131-140 (ordered evaluation, INVALID, INCOMPLETE with causes).

Unlabelled cells (inputs satisfy no PASS, BREAK or UNRESOLVED definition):
1. Finalist keeps its sign but |Delta| < 3 SE_eff with the SE target met. This is the most likely physical outcome (attenuation) and it is the plan's own question 2 (P:34). UNRESOLVED_STAT is defined as "SE target missed" (P:117), not this.
2. Condition 2 fails (fewer than 3/4 of the resolvable designs keep sign) while the finalist is fine.
3. tau in [0.3, 0.6).
4. R1: OpenFOAM V1 disagrees (sign or retention outside 0.3-3.0) while WaterLily passes, or OpenFOAM agrees while WaterLily breaks. OpenFOAM enters only RUNG_PASS (P:114), not BREAK or UNRESOLVED.
5. Finalist reversed on both grids but only one is resolved (BREAK needs both, P:115); signs agree so RESOLUTION_LIMITED does not fire either.
6. flow_48 sign "same" is not defined (same as the Re 80 sign, or same as flow_32 at this rung).

Overlaps without precedence: BREAK together with RESOLUTION_LIMITED (finalist reversed on both grids but two other designs differ between grids), BREAK together with STAT_INCONSISTENT, several UNRESOLVED sub-labels at once (is the rung label a set or a single value?).

Other defects:
- No INVALID outcome. A failed negative control or determinism repeat (P:135) has no outcome, whereas SCREEN has `SCREEN01_INVALID` (S:17, S:136) and FID has `FID01_INVALID`.
- `RE_BREAKS_AT_1` is defined in P:146 as a reversal on both WaterLily grids and OpenFOAM V1. In P:115 and P:122 it is a reversal on both WaterLily grids only. Whether R2/R3 become "optional" depends on which definition holds.
- `UNRESOLVED_NUM` (P:140) is in no label list. `INCOMPLETE` (P:124) has no causes. R4 has no label.
- Overall labels ignore ordering: R1 UNRESOLVED then R2 BREAK is `RE_BREAKS_AT_2`, which the reading table (P:211) treats as evidence of a low-Re effect although R1 was never resolved. R1 BREAK with R2 PASS (non-monotone) is still `RE_BREAKS_AT_1`.

Fix: write one ordered evaluation table per rung and one for the overall label, in the style of S:131-140 (minimum data, then INVALID, then NUMERICAL, then BREAK, then UNRESOLVED causes in a stated order, then PASS, else a named residual label such as `RUNG_ATTENUATED`). Every cell of the 2^k combination of the PASS and BREAK inputs must map to one label; commit a synthetic-table test of every branch and an independent checker implementation, as SCREEN did (S:31). Add `RUNG_INVALID` (negative control or determinism failure), `RUNG_NUMERICAL` (divergence, Poisson dependence), and an R1 solver-conflict label (`R1_WL_OF_CONFLICT`). Define the sign reference of every "same sign". Give INCOMPLETE a cause list (`BUDGET`, `DATA`, `NOT_RUN`).

### G3 (P1). No operating characteristics; the stop target and the PASS threshold are inconsistent in power, and the hypothesised effect is mostly undetectable
Evidence: P:100 (stop at SE_T <= 1.9 % of the parent force), P:110 (PASS needs |Delta| >= 3 SE_eff), P:82, F:133 (SE_eff = 0.71 SE_T; "to resolve a 4 % gain at 3 SE_eff one needs SE_T <= 1.9 %"), F:232 (H1: retention 0.3-1.0). Precedent: S:155-177 (SCREEN's end-to-end OC before freeze 1), FID:173 (FID-01 OC).

Check (independent runs, P = 4, SD from 3 degrees of freedom, effect = finalist's Re-80 gain 4.05 % of J_b,48 times retention rho; STATE.md:14):
- At the stop target, sigma_d = sqrt(2) * 1.9 = 2.69 %, SE_eff = 1.34 %, 3 SE_eff = 4.03 %. The finalist's full Re-80 gain (4.05 %) sits exactly on the threshold.
- Simulated P(condition 1 holds): rho = 1.0: 0.58; 0.8: 0.42; 0.65 (the FID-01 V1 slope, STATE.md:15-16): 0.31; 0.5: 0.21; 0.3: 0.11; 0 (false positive): 0.03.
- 80 % power at rho = 1 needs SE_T <= 1.4 %; at rho = 0.65 it needs <= 0.9 %. Window scales as SE_T^-2, so 1.8x and 4.3x the 1.9 % window. At F:132's 10 % rms that is about 400 and 930 CU; at 20 % rms the second case is far past the 800 CU cap.
- Tier-A Re-80 gains (FID `analysis.json` `wl_flow32`): camber_m11.3 +2.70 %, pitch_m0.7 -3.37 %, camber_p19.7 -3.83 %, pitch_p0.7 +3.99 % are all below 4.03 %, so they cannot be resolved even at rho = 1; only C4 (-12.06 %), reflex_m29.3 (+5.89 %), C1 (+4.99 %) and camber_m19.7 (+4.89 %) can. At rho = 0.65 only C4 survives. Condition 2 ("3/4 of the designs with |Delta(80)| >= 3 SE_eff", P:111) therefore has a denominator of at most 4 and about 1 in the hypothesised band, and is undefined for 0.
- Consequence: on chaotic rungs RUNG_PASS is nearly unreachable by construction, and the modal outcome is an unlabelled (G2 cell 1) or UNRESOLVED rung after 30-60 GPU h.

Fix:
1. Before freeze 1 write `re01_oc.py` and `oc.json` (SCREEN-style: truths rho in {1, 0.65, 0.3, 0, -0.3} per design, lift rms in {5, 10, 20} %, tau_int, P = 4 and 6, the registered rules end to end, 2000 replicates). Require, and register as a rule check, that the null truth never gives PASS and that rho = 1 gives PASS with probability >= 0.8 at the registered window.
2. Add a pre-declared viability rule (G1 option 2): a rung is run only if the Stage-0 prediction gives 3 SE_eff (cap window, P as registered) <= 0.7 * the smallest effect the rung is meant to resolve; otherwise it is dropped before registration with the record, not run to an assured RUNG_UNRESOLVED.
3. If power requires more phases, say so now (P = 6 is a 50 % cost increase); do not tune afterwards.
4. Use a pooled sigma_d across designs (common structure on chaotic rungs, about 33 degrees of freedom) instead of a 3-degree-of-freedom SD per design for SE_eff, or state why not.
5. Remove the H1 band 0.3-1.0 from any binding text unless the OC shows it is detectable.

### G4 (P1). The STAT_INCONSISTENT gate misfires by construction
Evidence: P:99 (gate [0.5, 2] on sigma_d / sigma_d,pred), P:98 (estimator B within run), F:59 (drift 1e-8 to 2.5e-5 in steady runs), F:165 and F:177 (CRN ratio 0.11-0.29 at Re 80), F:176.

Problems:
- Steady rung (R1 is predicted steady, P:63): estimator B is a within-run batch-means SE of a steady signal, about 1e-8 relative. Estimator A is placement scatter (2-5e-4 N at Re 80). The ratio is orders of magnitude above 2, so R1 is `STAT_INCONSISTENT` deterministically. Estimator B contains no placement noise in any regime.
- CRN regime: the plan itself expects the ratio to be well below 1 (0.1-0.3, P:99 "CRN の効果"), which is below the 0.5 lower bound.
- Even with perfect consistency, an SD from P = 4 (3 degrees of freedom) falls outside [0.5, 2] with probability 0.138 + 0.0075 = 14.6 %. If the gate is per design, 10 designs give about 79 % false triggering per rung.
- The gate makes a descriptive quantity (CRN ratio, P:99) a verdict gate, and it is not stated which design's sigma_d is meant.

Fix: make the ratio descriptive on all rungs. If a consistency gate is wanted, define it only for unsteady rungs, compare a pooled sigma_d (all designs) with a pooled batch-means prediction, one-sided (upper bound only), with a bound calibrated by the OC (G3) so that its false-trigger rate under consistency is below 5 %. State the gate's unit (rung, design, pooled).

### G5 (P1). The controls are undefined or insufficient at the new Re
Evidence: P:135 ("SCREEN と同じに置きます"), P:83-84, P:93, P:73; S:61, S:119-120; FID:155; F:196; `src/cfd_sdf/grid02_contract.py:12,54` (Re = 80 hard-coded); `scripts/waterlily_w4_v16_sensitivity_job.jl:53-54` (T_END, BURN_IN fixed).

1. The negative control `v18__roll_p25` is not a null. It is a measured non-null shift with an Re-80 reference (M2 -1.648e-3 N, FID OpenFOAM V1 -6.61e-4 N; S:61, S:119). SCREEN's NC test is "consistent with that reference" (z <= 3.5). At Re 250/800/2500 there is no reference, so "same as SCREEN" cannot be executed and the plan gives no acceptance criterion. It is also used as the floor (P:103), so it cannot be both the floor and the control without a rule.
2. The determinism repeat is asserted ("bit 一致するはずです", P:135; F:196) without a criterion. SCREEN's criterion is a difference within the Re-80 downforce floor 2.09e-4 N (S:120), which has no meaning on a chaotic rung. State exactness (difference == 0) or the alternative, and the consequence (G2: INVALID or `RUNG_NONDETERMINISTIC`). Note that estimator A stays valid without determinism; the repeat guards reproducibility and the pairing claim.
3. No Re-80 reproduction gate for the new source. The case validator asserts Re = 80 and the job has fixed windows (cited above). The plan says only viscosity changes (P:73) but nothing proves the re-parametrised contract and the new windowed job reproduce Re 80. This is the cheapest high-value control: run the new source at Re = 80 on parent, finalist and roll at flow_32, phases 13-14 (SCREEN replays) and require byte equality with the registered SCREEN f32a raws; failure is INVALID. About 0.3 GPU h.
4. The same-phase Re-80 anchor (P:93) is left to plan review. Recommendation: include a reduced anchor (parent, finalist, M, R-best, NC, positive control; flow_32; the four RE-01 phases; about 3.5 GPU h) rather than the full 12-state one (about 6 GPU h). It supplies the new-source Re-80 baseline on the same placements, the NC reference for the new source, and the byte regression of item 3.
5. No unselected comparison. The finalist is the argmax of 19 candidates; SCREEN's best random member `v18__camber_m28.656_pitch_m0.68_reflex_p2.727` already has Re-80 confirmation data (analysis.json `r_best`) and is a natural "selected by search, not by model" control. It is absent. Add it at every rung (flow_32 and the flow_48 set).
6. No positive control. A design whose effect is resolvable at every rung (C4 is -12 %, or the registered M2 pitch +-3.1 state) calibrates detectability. Without it, "UNRESOLVED" cannot be separated from "estimator cannot see anything on this rung".
7. No manipulation check that Re changes the flow in this solver. At Re_L 800 and 2500 the leading-edge boundary layer is below one cell on every grid (F:126), and flow_32 has about 4.6 cells across the thickness against WaterLily's validated 88-168 cells per sphere diameter (F:127). If nominal Re is numerically saturated, `RE_PERSISTS` would be vacuous. Register a per-rung check that the parent's response (C_L, C_D, St, rms) differs from the previous rung's by more than the estimator can resolve, and make "no detectable Re effect" a labelled outcome that blocks PASS.
8. Omitted: a within-run transient/stationarity control for designs (burn-in comes from the parent only, P:102); a block-mean stability rule (F:170 has it, the plan dropped it).

Fix: write the NC rule per rung (reference from the Re-80 anchor on the same placements for the new source; per-rung measurement as descriptive plus a bound derived from the OC), the determinism criterion, and items 3-7 as registered controls with consequences in the label table (G2).

### G6 (P1). The decision vehicle is the weakest design: finalist-centric BREAK, selection bias, and an interpretation that depends on an unknown XV-01 outcome
Evidence: P:110, P:115, P:118, P:211, P:192; S:14 and S:37 (camber extension, no FID fidelity evidence); STATE.md:14 (drag neutrality "relies on an untested OpenFOAM camber drag retention"; "not independent verification"); #65 (the finalist's OpenFOAM verdict is XV-01's job).

Problems:
- BREAK needs only the finalist (P:115) while PASS needs finalist plus many (P:110-113). A single selected design, in the camber extension (u = -1.5) with no fidelity evidence, can end the ladder (and with it R2/R3, P:146).
- The finalist is an argmax over 19 candidates on WaterLily flow_32 at Re 80. SCREEN's own disclosure (S:128) puts the WaterLily-to-OpenFOAM selection bias at b_K 1.03e-3 N (upper 2.67e-3 N). A reduced retention across Re can therefore come from a lattice-specific part of the selected response, not from physics. The plan has no way to tell these apart (no R-best, G5 item 5).
- XV-01 may return `XV01_FAIL` or UNRESOLVED on this finalist. The reading table (P:211: "Re 80 の finalist の利得は…低 Re の効果") is registered before that is known and is not conditioned on it.
- Tier-A designs were selected by d_set on a WaterLily |Delta| threshold on phases 7-10 (FID `tiers`), which are also the phases used as their Re-80 baseline. The selection is on large effects, which are exactly the ones most likely to stay resolvable at higher Re. This should be a stated limit of "persistence".

Fix: (a) make the OpenFOAM-confirmed tier-A set the primary decision set, with finalist, M and R-best as pre-declared secondary comparisons; or keep the finalist primary but require BREAK to be resolved on the finalist and on at least k tier-A designs of the same sign-reversal family; (b) condition every row of the P:208-214 reading table on the XV-01 outcome (a finalist that XV-01 fails cannot support "low-Re effect"); (c) report retention separately for selected (finalist, M, R-best) and unselected (tier A) groups; (d) state the tier-A selection limit in the claim ceiling.

### G7 (P1). In-run adaptive windows contradict frozen kernel caps, are data-dependent, and are not feasible in the harness as written
Evidence: P:100-102; `scripts/waterlily_w4_v16_sensitivity_job.jl:53-54,150,176` (T_END, BURN_IN and the window are constants); S:83 (cap rule: 1.5x registered maximum runs x estimate), S:100 (a cap trip or a divergent state voids the whole kernel under harness v1.1), S:87 (campaign hashes frozen into every run identity); F:125, F:134.

Problems:
- "Extend by 100 CU until both SE_T <= 1.9 %, cap 800 CU" makes the window of each run depend on its own data, and different designs at the same phase get different windows. The paired difference then compares different window lengths (transient and drift confound). It also makes the stop a function of the design's own variance estimate (optional-stopping bias, small but unquantified).
- Per-state and aggregate caps and the 12 h session limit must be frozen per kernel (S:83, S:87). With adaptivity the wall of a kernel is unknown at freeze. At the 800 CU cap a flow_64 run is about 7-8 h (F:134 rates), so one run per kernel; flow_48 about 2.1-2.4 h per run. A cap trip voids the entire kernel (S:100) and the identical rerun (S:233) repeats the same deterministic trip.
- "Steady rung (drift rule satisfied) uses the Re 80 120 CU window" (P:101): who decides, before or after the run? If per run, the window is again data-dependent.
- The job is a new source (fixed constants today); the harness measurement contract and the verify tables assume a registered window.

Fix: fix burn-in and window per rung (and grid) in the registration, from the viability formula (G1/G3), identical for every state at that rung; compute block means post hoc from the full registered series; make "SE target missed at the registered window" the `UNRESOLVED_STAT` trigger (no extension). Specify the kernel table (states, phases, per-state cap, aggregate cap by the SCREEN 1.5x rule, timeout) at registration, with flow_64 and R4-like runs one per kernel. Add a block-mean stationarity label per run.

### G8 (P1). Kernel-loss, data-loss and budget-stop rules are missing or unsafe at high Re
Evidence: P:144-147, P:151-157; S:83, S:89-90 (T rule before every push, stop goes to the user), S:100, S:142-153 (data-loss table), S:233; F:250 (WaterLily stability above Re 80 is unverified).

Problems:
- P:147 says kernel loss is "same as SCREEN, one identical rerun". SCREEN calibrated that rule on about 150 Re-80 runs with no divergence (S:233). At Re 800-2500 on under-resolved grids divergence is a live risk, and under harness v1.1 one divergent state voids every state in its kernel (S:100); the identical rerun is deterministic and diverges again. The result is a twice-paid, wholly lost kernel with no label for it.
- No data-loss table (minimum data per state, per rung: parent runs, finalist phases, flow_48 phases, NC), no minimum |Phi|, no consequence for a lost phase on estimator A with P = 4.
- Budget: the cap (90 GPU h, 100 CPU h) is below the plan's own worst case (125 GPU h, P:157; CPU 50-65 + 40 = 90-105). My recomputation from the F:108-118 rates at 880 CU gives R2 about 58 and R3 about 52 GPU h worst case. There is no per-push check, no definition of what counts toward the cap (Stage 0? smokes? reruns?), no stop authority (SCREEN: the decision goes to the user, S:90), no label for a rung that the cap prevents.
- A divergence is a result at high Re (a finding about the design or the grid), not infrastructure loss. FID-01 and SCREEN distinguish them (FID:225).

Fix: write the SCREEN §4.3/§5.9 analogues for RE-01: per-push T rule with a named authority, what counts, and `INCOMPLETE(BUDGET)` with the stop record; a data-loss table; divergence (non-finite, blow-up) classified as `RUNG_NUMERICAL` for that state and rung, never rerun; either one state per kernel for R2/R3 or a continuing runner (SCREEN rejected both at Re 80 with a reason that no longer holds); a statement that the cap is below the worst case and that R3 is the first rung to be dropped, with the label that follows.

### G9 (P1). Authority, order and dependency: RE-01 has no slot in the roadmap, and the plan contradicts itself on M4
Evidence: AGENTS.md ("`docs/phase_plan.md` is the sole roadmap, status, and execution-order authority"); `docs/phase_plan.md:631` (§11: "sole current roadmap and order authority"); `docs/STATE.md:39` (XV-01 is "**Next**"), `:41` (M4 final keeps its M3 dependency); `docs/phase_plan.md:7630` (2026-10-22 parallel amendment: no new CFD campaign allowed by it); issue #66 body ("最終決定の依存": the listed M3 records; "起票・資料作成は新規 CFD・実装・追加課金を開始しない"); P:3, P:48, P:192, P:193, P:218.

Problems:
- P:218 records "次の作業は RE-01" as decided. STATE.md says XV-01 is next. Nothing in phase_plan or STATE contains RE-01, so a new GPU campaign (about 60-90 GPU h plus Stage 0) enters the project without an order amendment. The user asked for a plan and delegated the hard choice to Fable (P:5), and the plan is only a recommendation (P:51 "推奨は (c)"); the recorded decision is missing. The user's words were "Re を高くした時"; the plan delivers Re_L <= 2500 (Re_c about 3.8e3, 130 times below the FSAE Re, P:12), which is a deviation the decision record should state.
- P:48 says RE-01 "does not wait for M4" but P:192 says M4 decides "after XV-01 and RE-01's R1 judgement (or overall judgement)". That adds a de facto prerequisite to M4 that is not in #66's dependency list (M3 records only). P:192 also says "RE-01 は M4 の前提条件ではなく、入力です", which cannot both hold.

Fix: before Stage 0, a phase_plan amendment (and STATE row, and a #66 comment) that records: the user's request verbatim, options (a)/(b)/(c) and the choice with its authority (user delegation or user decision), the order relative to XV-01 (parallel, with the coupling rules of G12), and one dependency statement for M4: either M4 may decide without RE-01 (RE-01 then informs but cannot reopen), or #66 is amended to name RE-01 R1 as a prerequisite. Open a new issue (P:193) with the label registry.

### G10 (P1). Claim ceiling: `RE_PERSISTS` can be misread and the M4 reading table goes beyond the ceiling
Evidence: P:40, P:110-113, P:121, P:210-211, P:15-16 (CRN lost), P:65 (R3 "iLES が検証されている範囲"); F:126-127.

Problems:
- `RE_PERSISTS` has no magnitude condition. On a steady rung (small SE) a finalist keeping 5 % of its Re-80 gain passes condition 1. On a chaotic rung only about 100 % retention passes (G3). The label thus means "sign persists" on one rung and "nearly everything persists" on another, and it ignores g_min (2.70 % of J_b,48), the quantity that made the gain meaningful in SCREEN/FID.
- The reading of `RE_PERSISTS` in P:210 says the fixed-grid proposer and the paired-difference statistics "転写する". RE-01 never runs the proposer at another Re (the claim ceiling excludes "新しい Re で最適化器が選んだ形状", P:39), and the plan itself says the CRN effect that makes the statistics work is lost on chaotic rungs (P:16). "選択肢 A の論文の頑健性を強める" (P:210) is a publication framing no registered quantity supports.
- P:211 calls Re 80 "creeping flow". Re_L = 80 (Re_c 122) is a steady laminar separated flow, not Stokes flow. "Creeping-flow demonstration" would put a wrong physical statement into the option-A paper text.
- "WaterLily の implicit LES" and "iLES が検証されている範囲" (P:38, P:65): the validated range is 88-168 cells per sphere diameter (F:127); flow_32/48 have 4.6-6.9 cells across the plate thickness (F:126). The nominal Re of R2/R3 on these grids is a viscosity parameter of an under-resolved scheme, not a transition or turbulence statement.

Fix: rename to `SIGN_PERSISTS` or add a magnitude condition (finalist and tier-A: Delta(Re) >= max(3 SE_eff, 0.5 g_min J_parent)); report retention with an interval for every design; add the G5 item-7 manipulation check; delete the proposer/paired-statistics/paper sentences from P:210; use "Re 80 reduced laminar" for the baseline; replace "iLES validated" by "under-resolved relative to the sphere validation; no turbulence or transition claim"; put "not a statement about the proposer at higher Re" in the ceiling and in the first line of the registration.

---

## P2 (should fix)

### G11 (P2). The retention estimand and its Re-80 baselines are not defined
Evidence: P:91-93, P:114, P:82; FID `analysis.json` (`wl_flow32` phases 7-10, tier A), S:14 (finalist phases 13-16), xv01 requirements (finalist OpenFOAM at Re 80 does not exist yet).
- Baseline phase sets differ (tier A: 7-10; finalist and M: 13-16; new rung: four other phases). Numerically small at Re 80 (SE_eff 1-3e-4 N vs Delta 7e-3 to 3.2e-2 N, so 1-4 %), but unchecked, and the unphased z-lattice systematic is common to both sides. The retention has no uncertainty (ratio of two noisy numbers).
- R1 PASS requires "OpenFOAM V1: finalist and M same sign, retention 0.3-3.0" (P:114). Retention relative to what? Neither the finalist nor M has an Re-80 OpenFOAM value (XV-01 pending; M was not an FID design), so the only available denominator is the WaterLily Re-80 gain. That ratio mixes the solver gap (0.57-0.77 at Re 80, STATE.md:15-16) with the Re effect. A band of 0.3-3.0 (a factor of 10) cannot reject anything meaningful.
- flow_48 confirmation states include M (P:111-112 item 3), which has no flow_48 baseline (SCREEN flow_48 ran parent, finalist, R-best only).
- OpenFOAM shifts for the 16 pairs are unspecified (FID Halton sets, XV-01's sets).
Fix: define retention as Delta(Re)/Delta(80) from a named file field, with a Fieller or bootstrap interval; use the same-phase anchor (G5 item 4) as the denominator for the primary retention; define the OpenFOAM comparison as OpenFOAM(Re 250) against OpenFOAM(Re 80) for tier A only (FID V1 exists) and make finalist/M OpenFOAM at Re 250 descriptive; fix the sign references; list the shifts; have the analyzer re-read the Re-80 files by SHA-256 as SCREEN did (S:216).

### G12 (P2). Coupling with XV-01: serialisation, information, shifts
Evidence: P:15, P:154, P:191, P:18-22 (R1 judgement precedes R2/R3); xv01 requirements line 55 (no retuning), line 61 ("no exploratory extras"); `docs/screen_xv_preparation_2026_10_23.md:70-71` (80 or 96 OpenFOAM cases, V3 about 8 h each); #65 body.
- R1's RUNG_PASS contains OpenFOAM (P:114) and R2/R3 start after "R1 の判定" (P:18-22). RE-01's WaterLily work therefore waits for the OpenFOAM part of R1, which waits for XV-01's compute (P:191). "独立に進めます" (P:191) does not follow.
- RE-01 R1 runs the same finalist in the same V1 pipeline at another Re. Reading those forces before XV-01's registered analysis is written would hand XV-01's subject an outcome correlate. XV-01 states "no finalist retuning after results".
- OpenFOAM shift sets and WaterLily phases must not overlap or must be declared identical.
- Both sessions edit STATE.md, phase_plan.md and exploratory_index.md.
Fix: split R1 into R1-WL and R1-OF verdicts; R2/R3 are conditioned on R1-WL only. RE-01's OpenFOAM kernels start only after XV-01's compute is finished and its written-once analysis exists; RE-01's OpenFOAM forces are not read before that. A waiting limit (SCREEN §4.3 style, S:90) after which R1-OF is declared `NOT_RUN` with a pre-defined consequence. Allocate shift index ranges. Serialise doc edits (merge order recorded in the amendment).

### G13 (P2). Discretionary branches and partial analyses
Evidence: P:145-146, P:178, P:170, P:128.
- "R2 and R3 optional after RE_BREAKS_AT_1" (P:146): optional by whose decision, after seeing R1. No rule says whether R3 runs after an R2 BREAK. R4 runs "if R1-R3 are all judged and the cap has room" (P:145): "room" is a judgement, and R4 (F:156, flow_96 300 CU, 11-15 h per run) does not fit a 12 h kernel. It has no label and no rule whether it can change the overall label.
- "凍結 → R2 → R3 → 分析（1 回だけ書く）" (P:178): R1's judgement is a written-once analysis that reads R1 forces before R2/R3 are generated. The text has one analysis, so the partial one is unregistered. What may the post-R1 freeze change?
Fix: after `RE_BREAKS_AT_1`, either unconditionally run R2/R3 as descriptive or unconditionally do not; the choice is registered now. Remove R4 from RE-01 (follow-up exploratory study after the analysis) or register fixed R4 conditions and an explicit "never changes a label". Register a written-once `rung1.json` step and state that the post-R1 freeze binds only mechanically generated campaign files and changes no parameter.

### G14 (P2). The domain-extension control tests the wrong estimand, is under-powered and has no consequence
Evidence: P:139, P:100.
- It compares the parent's absolute force with a +1 m outlet; the estimand is the difference. Threshold 2 % is the size of the estimator noise at the stop target (SE_T 1.9 % per run, 2.7 % for a difference of two runs) and the finalist's gain scale is 4 %.
- Only R3 (R1/R2 wakes are also finite and the laminar wake length grows with Re in lattice units).
- "記録します" with no label: `RE_PERSISTS` can be issued while R3 is domain-sensitive.
- The extended lattice is a new domain: new grid dimensions, possibly new contract bytes.
Fix: run parent and finalist at one registered phase at R2 and R3 on flow_32; state the decision rule in terms of Delta (change in the difference vs 3 SE), the power from the OC, and make `DOMAIN_SENSITIVE` convert PASS to a named non-PASS label.

### G15 (P2). The Poisson probe has no test
Evidence: P:140; label lists P:116-124; GRIDRES-01 (STATE.md:20, flow_40 Poisson-confounded).
"Finalist's sign depends on it" cannot be established from an iteration-count log. No tighter-tolerance run is budgeted. `UNRESOLVED_NUM` is outside the label set. The 10 % threshold is arbitrary.
Fix: register a sensitivity run (parent and finalist, one phase, tighter tolerance or higher itmx) at R2 and R3, its cost, a decision rule on Delta, and the label in G2.

### G16 (P2). Grid-consistency gate is sign-only, with an unresolved flow_48 estimator
Evidence: P:136-138, P:111-112, P:118.
- Sign agreement does not catch a 3x magnitude disagreement, the expected symptom of BDIM smearing the leading edge (P:137). S:118 carried ratio and E2 labels for this reason.
- flow_48 has P = 2 (1 degree of freedom for sigma_d) and no roll run, so its floor "from the roll at that rung" (P:103) does not exist; "resolved on both grids" in BREAK (P:115) has no flow_48 SE.
- "flow_64 の記述的な裁定" (P:138) is an interpretive step; descriptive means it cannot change a label, which should be stated.
Fix: add a magnitude-ratio label (descriptive or gate by OC), a flow_48 SE rule (pooled sigma_d from flow_32 designs or a floor from the flow_32 roll), and say flow_64 never changes a label.

### G17 (P2). Rank statistic and the tau-based BREAK
Evidence: P:104, P:113, P:115.
- tau over 10 designs of which perhaps 1-4 are resolvable (G3) is dominated by noise; `tau < 0.3` triggers BREAK without a resolution requirement.
- The 10 designs are not exchangeable (finalist and M share camber and pitch with tier A; M is nearly camber_m19.7), so the permutation p-value (P:104) is not valid.
Fix: tau among designs resolved at Re 80 and at the rung only, minimum n stated, tau used descriptively or in PASS (not BREAK) unless a resolved sign reversal accompanies it; drop the permutation p-value or use a design-family block permutation.

### G18 (P2). Cost accounting inconsistencies
Evidence: P:14 vs P:154; P:153; P:157; F:108-118 (rates).
- P:14: R1 about 7 GPU h and 40-50 CPU h; P:154: 9 / 15 GPU h and 50-65 CPU h. The summary is stale.
- Stage 0 is stated as about 3 GPU h (P:153). With the plan's own run table (flow_32 and flow_48 at three Re, 400 CU windows, one flow_64 run) and the F rate table, Stage 0 is about 7.3 GPU h (400 CU) to 8.7 (480 CU with burn-in): flow_48 about 3.6, flow_64 about 3.1-3.7, flow_32 about 0.7.
- The cap is below the worst case (G8) and it is not said whether Stage 0 counts.
Fix: recompute from the registered kernel table; state what counts toward the cap; make the summary agree.

### G19 (P2). Phase and shift allocation
Evidence: P:90; S:70 (smoke parent at k = 20; "a re-registration uses k >= 21"), S:221 (at most one re-registration of #64 with phases >= 21); FID:24 (shifts outside every registered set).
RE-01 needs four fresh phases: free are 17, 18, 19 and 20 (20 only ever had a parent run at Re 80), and 21+ is reserved for a SCREEN re-registration. Pin 17-20 now; this leaves no spare phase for a RE-01 rerun, so rerun must use the same phases (identical rerun). Stage 0 needs its own phase (G1 item 5). OpenFOAM shift ranges must be disjoint from XV-01's.

### G20 (P2). Sources, commits and hypotheses before registration
Evidence: P:175-179; `git status` (plan and evidence directory untracked); phase_plan.md:7488 ("Uncommitted work is not evidence"); F:243 and F:250 ("from memory", "no project run exists above Re 80"); P:68-71.
- The plan, the Fable analysis and `re_ladder.py` are untracked. Commit them with hashes before Stage 0 (they are the stated basis of the design).
- The regime table (P:68-71) rests on items Fable could not verify (Taira and Colonius map from memory, F:243; stability above Re 80, F:250). P:63 uses "定常か弱い周期" for R1 and P:101 conditions the window on "steady rung". Mark the table non-binding, and make the labels independent of the predicted regime.
- H1-H4 exist only in F:232; none appears in the plan. Register them (G1 item 6).

### G21 (P2). Section 6 pre-empts #69's start condition
Evidence: P:186; #69 body ("着手条件: #66 が…新しい研究を選んだ記録", "最小の順序 1. solver-free 監査").
The LTS audit is step 1 of EVAL-PT-01, whose start condition (M4 selecting new work) is unmet. #66's "materials in parallel" item for #69 is the design of gates, not step 1 of the study. P:185 (B5 ProblemSpec draft) and P:187 (data request text, to be sent by the user) are fine. Recast P:186 as a design memo, or obtain an explicit recorded decision that step 1 may start before M4.

---

## P3 (minor)

- G22. "12 状態" (P:77) is 13 runs per phase (parent, finalist, M, 8 tier A, NC, parent repeat); cost scaling (P:159) uses 12. F:159 and F:211 count "8 non-control designs" for a list that has 7.
- G23. M (`camber_m19.7_pitch_m0.38`) is nearly the tier-A `camber_m19.7`; the duplicate lowers the effective n in conditions 2 and tau. Say so or drop M from the rank set.
- G24. `RE_BREAKS_AT_3 だけ` (P:212) presumes R1 and R2 PASS; with R2 UNRESOLVED the reading is different. Add rows for UNRESOLVED-then-BREAK.
- G25. Retention should be reported with an interval in the descriptive list (P:126), not only as a curve; the descriptive list should name estimator and files by hash.

---

## Direct answers to the specific questions

### Stage 0: outcome-blind? What must be frozen first?
Delta-blind: yes, provided no design state, roll or repeat is run at any Stage-0 point and the Stage-0 phase is not a registered phase. Design-blind: no. The parent's regime, grid gap, rms/tau_int and the OpenFOAM convergence result determine which rungs and grids survive, the window, the SE target and whether OpenFOAM is part of R1 PASS. Those are researcher degrees of freedom even though no design force is seen, and they exceed what FID-01's P0 allowed (statuses only, sanitised). "Parent only" is therefore necessary and not sufficient. The freeze-before-Stage-0 list is G1 items 1-8: a charter with the exact run table, a sanitised readout, formulas from observables to engineering parameters, drop-only modification triggers, the OpenFOAM convergence criterion and fallback as rules, Stage-0 phase outside the registered set, hypotheses and baseline files by hash, frozen source bytes, index rows before the runs.

### Controls: sufficient?
No (G5): the NC has no reference at new Re; the determinism criterion is undefined; there is no Re-80 reproduction (byte regression) of the new source; no same-phase anchor; no positive control; no random/unselected control (the best random SCREEN member is available); no manipulation check that Re changes the flow; no stationarity control; domain and Poisson controls test the wrong estimand or have no test (G14, G15); the grid gate is sign-only (G16). The Re-80 baseline unbiasedness: phase-set differences are small numerically but unchecked; the winner's curse of the finalist and of tier A is not controlled (G6, G11).

### Forking paths
Adaptive windows (G7), "optional R2/R3" and R4 (G13), rung and grid substitution after Stage 0 (G1), the finalist-only BREAK (G6), partial R1 analysis (G13), retention against different phase sets and an undefined OpenFOAM baseline (G11), tau-based BREAK (G17), gate precedence (G2). The 12-state choice is not itself a fork (frozen designs) but the selection-biased finalist carries the decision (G6).

### Fail-closed
Labels are incomplete and overlapping, have no INVALID, and disagree between P:115 and P:146 (G2). Kernel loss is inherited from a regime where it was safe and is unsafe here (G8). Budget-stop rules are undefined and the cap is below the worst case (G8, G18).

### Claim ceiling
`RE_PERSISTS` can be misread: no magnitude condition, possibly vacuous if Re is numerically saturated, and the reading table claims proposer and paired-statistics transfer that RE-01 does not test (G10). "Not an evaluator GO, so does not wait for M4" is consistent with #66/#69 only if RE-01 is added to the order by an amendment and M4's dependency is stated once (G9).

### Resource conflict with XV-01
Serialisation inside R1 (G12), information coupling on the shared finalist (G12), shifts and phase allocation (G12, G19), concurrent edits of shared documents (G12). The plan's WaterLily-on-Kaggle versus OpenFOAM-local split removes the compute conflict only for the WaterLily part.

### Missing for reviewability
Decision tables (G2), data-loss table and minimum data (G8), operating characteristics (G3), kernel table with caps (G7), who decides each discretionary step (G9, G13: budget stop, rung drop, R4, anchor), what is written once (Stage-0 record, `windows`/viability record, `rung1.json`, final analysis, M4 handoff; G13), independent checker with synthetic-table tests (G2), baseline file hashes (G11), phase and shift allocation (G19).

## P1 list (for the caller)
G1 Stage-0 charter and PROC-01 compliance; G2 label algebra (holes, overlaps, no INVALID, P:115 vs P:146); G3 no OC and power inconsistency (3 SE_eff = 4.03 % vs finalist 4.05 %; P(pass) 0.58 at rho 1, 0.31 at 0.65); G4 STAT_INCONSISTENT gate misfires (steady R1 by construction; 14.6 % false reject per design); G5 controls at new Re (NC reference, determinism, byte regression, anchor, positive and random controls, manipulation check); G6 finalist-centric BREAK, selection bias, XV-01-conditional reading; G7 adaptive window vs frozen caps; G8 kernel-loss, data-loss and budget-stop rules (cap 90 < worst case 125; divergence voids kernels); G9 roadmap slot, STATE.md "Next = XV-01", M4 dependency contradiction; G10 `RE_PERSISTS` semantics and overreach in the M4 reading table.

Verdict: GO_AFTER_FIXES.
