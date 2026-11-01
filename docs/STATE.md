# STATE — current position in one page

Updated: 2026-10-31 (SCREEN-01 registered result `SCREEN01_GAIN`). Integration: `codex/kaggle-batch-migration` at `4c40407a`; the SCREEN-01 result is on `exp/screen01-registration-2026-10-30` until integrated.
Roadmap authority: [phase_plan.md, latest amendment](phase_plan.md#2026-10-31-screen-01-64-m3b-1-registered-response-surface-screen-on-three-analytic-modes-screen01_gain).
Rationale and primary sources: [2026-10-22 review](roadmap_review_2026_10_22.md). Earlier decisions remain in phase_plan and the [2026-10-16 review](roadmap_review_2026_10_16.md).

## Goal and claim boundary

A canonical-SDF rigid-object shape/topology optimizer with improvement confirmed by independent body-fitted CFD on grids not used for optimization; final use is FSAE aero (declared high-Re, turbulent, moving ground). No deadline (user, 2026-10-16).
No optimized shape has yet had its improvement independently confirmed. L1 is a Re80 numerical demo, L2 adds independent CFD at Re80, and L3 requires a separately validated target-physics evaluator. All qualification flags remain false; `shape_update_allowed=false`.

## Latest evidence

- **SCREEN-01 #64: `SCREEN01_GAIN`** (2026-10-31, `REGISTERED_FROZEN`, 7 Kaggle T4 kernels, 17.2 GPU h, no loss). Finalist `v18__camber_m29.55_pitch_p0.155_reflex_p16.115` (pitch +0.155 deg, camber -29.55 mm, reflex +16.1 mm), chosen before any confirmation force: fresh-phase flow_32 downforce +1.077e-2 N = 4.05 % of J_b,48 (1.50 g_min, SE_eff 2.9e-4 N), drag -1.99e-3 N; flow_48 +1.036e-2 N, `R3_CONFIRMED`. `OPT_BEATS_MANUAL` (hand design +7.71e-3 N) and `OPT_BEATS_RANDOM` (best random +5.86e-3 N); NC consistent, determinism exact. XV projection (planning only): OpenFOAM V1 gain 2.40 % central / 1.74 % pessimistic vs the 1.27 % floor. Scope: one finalist, WaterLily Re80; the finalist is in the camber extension without FID fidelity evidence and its drag neutrality relies on an untested OpenFOAM camber drag retention; not independent verification. [Record](evidence/screen01_2026_10_30/analysis.md).
- **UNC-01 #61: `M2_COMPLETE`** (2026-10-21). On the v18 plate, wide pitch/reflex downforce differences have placement SD sigma_d = 2.1–5.5e-4 N on flow_32. For pitch +3.1 deg, flow_32/48 = 0.980 [0.962, 0.999]; coarse OpenFOAM retains 0.63–0.71 of wide-arm downforce differences. Scope: one parent, selected modes and placements, Re80. This is not grid convergence or optimized-shape verification. [Record](evidence/unc01_2026_10_20/analysis.md).
- **FID-01 #62: completed `FID01_GO`**, result `b2314d9d` merged at `458e2df5` (2026-10-23). Tier A8/8 and G3-set PASS on the registered Re80 v18 designs;733/733 OF cases valid. V1 retention0.57–0.77; V3/V1 slope1.086 [0.992,1.181]. Pure heave ±31.1 FAIL (`TIER_B_FAIL`); local support `SUPPORT_UNTESTABLE`. Flow-grid R3 is confirmed, with `R3_E2_EXCEEDED`; this does not validate the geometry-width R3 proposal. Registered M3b minimum gain2.70% and XV OF minimum1.27% now apply. No optimizer-selected design, high-Re/FSAE or converged-mesh claim. [Written-once owner record](evidence/fid01_2026_10_21/analysis.md).
- **T2-0 #57: completed with no evaluator GO** (closed 2026-10-22). T2-0b/c/d are `T20B_NO_GO`, `T20C_MORPH_NO_GO`, `T20D_NO_GO`. The final study gives DATA `FAIL_INPUT`, DIFF `FAIL_VALUE`, cost `NOT_AFFORDABLE` (median 92.4 min/evaluation on Kaggle CPU). Fixed-topology morphs help at h/c=0.224; the peak remains uncertified across mesh realisations/levels. URANS settling is a statement about the 2D SA model, not experimental steadiness. [M4 summary](t20_summary_for_m4_2026_10_22.md).
- **EVAL-VALID-01 #68: bounded audit complete, `REFERENCE_INADEQUATE` for quantitative absolute-Cl adoption.** Primary Zerihan thesis Table 15 matches all seven legacy points (max difference 0.00091824). The observable is pressure-integrated sectional Cl, explicitly limited by the author to qualitative trends. Per-record trip and total integrated-Cl uncertainty remain unknown. Old T2-0 results stay unchanged. [Source/condition matrix and M4 packet](eval_valid01_reference_audit_2026_10_22.md).
- **Geometry width:** registered **GEOM03_NO_GO** (2026-10-23). All534 records completed their registered independent checks; E2 numerical equality remains descriptive rather than an acceptance gate. K1/K3/K5/K6/H0 pass, K2 W40_th1_q0 is accepted and K4 T1_th0_q0 is rejected against their registered labels. R3 is not adopted. New28 combinations pass the composite but R0 accepts1/rejects27 descriptively; no counterexample is excluded to promote that success. Next is the R0-clean fixed-pool/parent path with selection bias disclosed. [Result](evidence/geom03_2026_10_23/result.md). The preceding exploratory WIDTH-RULE and its190/200 R0 rejection remain their dated evidence.
- **GRIDRES-01 correction:** flow_40 was Poisson-confounded; the earlier “all grids discretization-dominated” hypothesis was withdrawn. GRID-02 and UNC-01 support flow_32 with flow_48 confirmation for measured large modes; flow_24 remains demoted. [Correction](issues/gridres01_result_2026_10_21.md).

## Principles and process

R1 same-phase paired differences with measured sigma_d; R2 wide smooth modes; R3 flow_32 proposes and flow_48 confirms; R4 common phases within a generation, full set for finalists; R5 screening and a small response surface; R6 reuse the campaign harness.
FID-01 tier A retains literal E2 (about 2.0%, 5.363e-3 N); the paired 0.68% is a tier-B floor. M3b takes its minimum-gain rule from the completed FID-01 record, not a new threshold in this review.
`EXPLORATORY_COMMITTED` is descriptive; `REGISTERED_FROZEN/AMENDED` requires pre-registration, freeze, one three-angle plan review and one source review, fail-closed, and written-once analysis. Existing verdicts remain immutable.

## Order and dependencies

| Stage | Issue | Current state / next condition |
| --- | --- | --- |
| M0 / M1 / M1' | #58, #59, #60 | Done: harness and JOB-02 byte gate; user selected B1=v18; mode prescreen exploratory, binding at M2 |
| M2 | #61 | Done: `M2_COMPLETE` |
| M3a | #62 | Done: FID01_GO, owner analysis b89203d0; preserve secondary labels |
| M4 preparation | #66 | Prepare now in parallel: the T2-0 fallback is unavailable. Final evaluator/product decision retains the required M3-result dependency |
| High-Re validation contract | [EVAL-VALID-01 #68](https://github.com/ramhachi/CFD_opt_sdf/issues/68) | Audit done: original quantitative reference inadequate; source matrix and bounded alternatives return to M4, no evaluator GO |
| Geometry before M3b | [GEOM-03 #70](https://github.com/ramhachi/CFD_opt_sdf/issues/70) | Completed bounded validation: [GEOM03_NO_GO](evidence/geom03_2026_10_23/result.md),534/534 verified, two counterexamples. No retry/retuning; R3 not adopted. R0-clean fixed-pool/parent route selected |
| M3b / L1 | #64 | Done: [`SCREEN01_GAIN`](evidence/screen01_2026_10_30/analysis.md), frozen finalist and [`xv_handoff.json`](evidence/screen01_2026_10_30/xv_handoff.json); no second SCREEN round, no finalist retuning |
| Independent verification / L2 | #65 | **Next.** Eligible for registration (SCREEN §7) with the frozen finalist; [preparation requirements](xv01_registration_requirements_2026_10_22.md): single-finalist uncertainty, constraints re-checked on its own arm, camber-extension fidelity and camber drag retention, expected pass probability from SCREEN §5.7 stated before any case is funded |
| Re dependence of the Re-80 result (parallel, off path) | [RE-01 #78](https://github.com/ramhachi/CFD_opt_sdf/issues/78) | [Plan rev 1](re01_plan_2026_11_01.md): Stage 0 parent probe and charter → registered R1 (Re_L 250) and viability-selected unsteady rungs on tier A; ATT-00 attached-parent scan and BRIDGE-2D-00 prepared in parallel. Covers Re_c ≤ 3.8e3 only (about 1 % of FSAE Re); M4 does not wait for it |
| High-Re numeric/cost recovery | [EVAL-PT-01 #69](https://github.com/ramhachi/CFD_opt_sdf/issues/69) | Conditional on M4 selecting new work, validation inputs and a registered bounded comparison; not a continuation of #57 |
| M4 final | #66 | Choose scope/evaluator, new evidence work, or research NO-GO after the applicable M3 outcome |
| M5 / L3 | #32, #33, #40, #67 | Existing dependencies; L3 blocked on new registered high-Re evaluator GO and M4 scope decision |

**Branch rules:** `FID01_NO_GO/WL_OF` triggers the pre-committed one-shot smooth-advection WaterLily study when registered; `OF_MESH` returns to reference/evaluator choice, not that automatic test. Inconclusive/incomplete/invalid outcomes follow FID-01's own retry rules. No branch automatically adopts the failed T2-0 evaluator. #23 remains the sole off-path gradient research issue; #28, #20, #53 retain their parked/reopen conditions.

## Compute and reproducibility

WaterLily stays on Kaggle T4. User decision 2026-10-20 moved OpenFOAM to local Docker where LOCAL-OF-01 permits it: U3/X3 family `LOCAL_ENV_PASS_BITWISE`, T2-0c mesh-generation family `LOCAL_ENV_FAIL`. T2-0 stayed on Kaggle CPU. The pinned image/lock and `scripts/local_openfoam.py` remain the reusable path; source: [local gate](local_openfoam_env_gate_2026_10_20.md).
Do not assume a local high-Re pipeline is equivalent: consume hash-pinned base meshes or requalify that pipeline. Backend changes are raised on the existing quota/latency/run-size triggers; no rented API or new spending was selected.
The 22:25 JST [status snapshot](evidence/parallel_preparation_2026_10_22/process_snapshot.json) found four advancing FID V3 jobs (5/9 case records complete). Preserve their resources and registered outputs; no extra CFD/GPU job was started. Parallel work is source research and preparation only.
Validation and exact hashes for this continuation: [audit record](evidence/parallel_preparation_2026_10_22/validation.json); the [earlier review validation](evidence/roadmap_review_2026_10_22/validation.json) remains its dated record. Other historical manifests with missing logs are not covered by its scoped integrity checks.

GEOM-03 continuation: [next execution plan](next_execution_plan_2026_10_23.md), [review record](evidence/geom03_2026_10_23/plan_review.json). The4 FID V3 jobs were still active at02:05JST; no registered geometry data were generated or measured. Development fixtures/tests are a separate evidence class.

At02:47JST the integration branch advanced to458e2df5 (FID result b2314d9d), owner branch was removed and Docker had no active containers. Select the proposed R3-composite validation route because the R0 occupancy alias blocks most optimizer-like combinations; adoption still requires GEOM03_PASS and SCREEN registration. Freeze/release follows the source review and full regression. Pure-heave treatment must be explicit in SCREEN; do not change GEOM fixture definitions after reading FID results.

[SCREEN/XV preparation](screen_xv_preparation_2026_10_23.md) identifies the five-wide-mode/heave-fixed proposal and the single-finalist V2 as well as V3 uncertainty gap. The80/96-case XV options are unregistered proposals, not a compute launch or transferred SE qualification.

At03:51JST the one frozen GEOM attempt completed GEOM03_NO_GO,301.39s and906.39MiB observed peak child RSS,attempt1/resume0. Preserve all534 raw inputs and the terminal result; no automatic R3 repair study follows. R0-clean pool generation/filtering must be registered before new SCREEN force observations; an unidentifiable response surface or insufficient pool cannot trigger outcome-based pool replacement.
