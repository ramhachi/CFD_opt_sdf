# STATE — current position in one page

Updated: 2026-10-22 (parallel preparation and primary-reference audit). Integration: `codex/kaggle-batch-migration` at `1467af14` when reviewed; this continuation is on PR #71's feature branch until integrated.
Roadmap authority: [phase_plan.md, latest amendment](phase_plan.md#2026-10-22-parallel-preparation-and-primary-reference-audit).
Rationale and primary sources: [2026-10-22 review](roadmap_review_2026_10_22.md). Earlier decisions remain in phase_plan and the [2026-10-16 review](roadmap_review_2026_10_16.md).

## Goal and claim boundary

A canonical-SDF rigid-object shape/topology optimizer with improvement confirmed by independent body-fitted CFD on grids not used for optimization; final use is FSAE aero (declared high-Re, turbulent, moving ground). No deadline (user, 2026-10-16).
No optimized shape has yet had its improvement independently confirmed. L1 is a Re80 numerical demo, L2 adds independent CFD at Re80, and L3 requires a separately validated target-physics evaluator. All qualification flags remain false; `shape_update_allowed=false`.

## Latest evidence

- **UNC-01 #61: `M2_COMPLETE`** (2026-10-21). On the v18 plate, wide pitch/reflex downforce differences have placement SD sigma_d = 2.1–5.5e-4 N on flow_32. For pitch +3.1 deg, flow_32/48 = 0.980 [0.962, 0.999]; coarse OpenFOAM retains 0.63–0.71 of wide-arm downforce differences. Scope: one parent, selected modes and placements, Re80. This is not grid convergence or optimized-shape verification. [Record](evidence/unc01_2026_10_20/analysis.md).
- **FID-01 #62: in progress on `claude/m3a-fid01`** (public snapshot `78e1e76f`). Freeze 3, four flow_32 kernels and the flow_48 kernel output are committed as verified. Tier A has eight designs and tier B four. No final OpenFOAM-inclusive registered verdict was confirmed. Do not change its registration or infer GO from this checkpoint.
- **T2-0 #57: completed with no evaluator GO** (closed 2026-10-22). T2-0b/c/d are `T20B_NO_GO`, `T20C_MORPH_NO_GO`, `T20D_NO_GO`. The final study gives DATA `FAIL_INPUT`, DIFF `FAIL_VALUE`, cost `NOT_AFFORDABLE` (median 92.4 min/evaluation on Kaggle CPU). Fixed-topology morphs help at h/c=0.224; the peak remains uncertified across mesh realisations/levels. URANS settling is a statement about the 2D SA model, not experimental steadiness. [M4 summary](t20_summary_for_m4_2026_10_22.md).
- **EVAL-VALID-01 #68: bounded audit complete, `REFERENCE_INADEQUATE` for quantitative absolute-Cl adoption.** Primary Zerihan thesis Table 15 matches all seven legacy points (max difference 0.00091824). The observable is pressure-integrated sectional Cl, explicitly limited by the author to qualitative trends. Per-record trip and total integrated-Cl uncertainty remain unknown. Old T2-0 results stay unchanged. [Source/condition matrix and M4 packet](eval_valid01_reference_audit_2026_10_22.md).
- **Geometry width:** exploratory WIDTH-RULE is `NO_CANDIDATE_MEETS_K1_K6`; R0 rejects 190/200 optimizer-like v18 combinations through one-cell occupancy artefacts. R3 + frozen-node margin + topology is a proposal requiring registered disjoint validation. M3a retains R0. [Proposal](width_rule_decision_2026_10_20.md).
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
| M3a | #62 | Complete the existing registered campaign and retain its cause/secondary labels |
| M4 preparation | #66 | Prepare now in parallel: the T2-0 fallback is unavailable. Final evaluator/product decision retains the required M3-result dependency |
| High-Re validation contract | [EVAL-VALID-01 #68](https://github.com/ramhachi/CFD_opt_sdf/issues/68) | Audit done: original quantitative reference inadequate; source matrix and bounded alternatives return to M4, no evaluator GO |
| Geometry before M3b | [GEOM-03 #70](https://github.com/ramhachi/CFD_opt_sdf/issues/70) | [Draft registration](geom03_registration_2026_10_22.md) prepared, not frozen or run. Required if adopting R3; failure keeps the registered R0-clean/parent branch |
| M3b / L1 | #64 | Only after `FID01_GO`, the geometry-admissibility path, and new registration |
| Independent verification / L2 | #65 | [Preparation requirements](xv01_registration_requirements_2026_10_22.md) available; requires frozen SCREEN finalist, single-finalist uncertainty and actual constraint checks; meshes judgment-only |
| High-Re numeric/cost recovery | [EVAL-PT-01 #69](https://github.com/ramhachi/CFD_opt_sdf/issues/69) | Conditional on M4 selecting new work, validation inputs and a registered bounded comparison; not a continuation of #57 |
| M4 final | #66 | Choose scope/evaluator, new evidence work, or research NO-GO after the applicable M3 outcome |
| M5 / L3 | #32, #33, #40, #67 | Existing dependencies; L3 blocked on new registered high-Re evaluator GO and M4 scope decision |

**Branch rules:** `FID01_NO_GO/WL_OF` triggers the pre-committed one-shot smooth-advection WaterLily study when registered; `OF_MESH` returns to reference/evaluator choice, not that automatic test. Inconclusive/incomplete/invalid outcomes follow FID-01's own retry rules. No branch automatically adopts the failed T2-0 evaluator. #23 remains the sole off-path gradient research issue; #28, #20, #53 retain their parked/reopen conditions.

## Compute and reproducibility

WaterLily stays on Kaggle T4. User decision 2026-10-20 moved OpenFOAM to local Docker where LOCAL-OF-01 permits it: U3/X3 family `LOCAL_ENV_PASS_BITWISE`, T2-0c mesh-generation family `LOCAL_ENV_FAIL`. T2-0 stayed on Kaggle CPU. The pinned image/lock and `scripts/local_openfoam.py` remain the reusable path; source: [local gate](local_openfoam_env_gate_2026_10_20.md).
Do not assume a local high-Re pipeline is equivalent: consume hash-pinned base meshes or requalify that pipeline. Backend changes are raised on the existing quota/latency/run-size triggers; no rented API or new spending was selected.
The 22:25 JST [status snapshot](evidence/parallel_preparation_2026_10_22/process_snapshot.json) found four advancing FID V3 jobs (5/9 case records complete). Preserve their resources and registered outputs; no extra CFD/GPU job was started. Parallel work is source research and preparation only.
Validation and exact hashes for this continuation: [audit record](evidence/parallel_preparation_2026_10_22/validation.json); the [earlier review validation](evidence/roadmap_review_2026_10_22/validation.json) remains its dated record. Other historical manifests with missing logs are not covered by its scoped integrity checks.
