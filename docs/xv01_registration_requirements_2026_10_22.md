# XV-01 #65 registration requirements — PREPARATION_ONLY (2026-10-22)

**PREPARATION_ONLY**: registration *input* — not a registration, freeze, or campaign start. No CFD is funded, queued, or started. No finalist exists ([SCREEN-01 #64](https://github.com/ramhachi/CFD_opt_sdf/issues/64)) and the final [FID-01 #62](https://github.com/ramhachi/CFD_opt_sdf/issues/62) result is unknown; `REQUIRED_FROM_FID` / `REQUIRED_FROM_SCREEN` placeholders are filled only from completed records, whose content hashes are themselves handoff items. Evidence class: solver-free contract/capability preparation; no optimized-shape improvement, grid-independent downforce, FSAE qualification, or Stage T/V ranking claims. Parent handles commits/issues/validation.

Reference: FID branch snapshot [`78e1e76f`](https://github.com/ramhachi/CFD_opt_sdf/tree/78e1e76f) holds the **registered FID definitions only** (freeze-3 record [#62 comment](https://github.com/ramhachi/CFD_opt_sdf/issues/62#issuecomment-6324411553)); no completed FID result is known from it and none may be inferred. XV-01 is L2: independent verification of the frozen SCREEN-01 finalist at Re 80 ([STATE](STATE.md)).

## 1. Handoff inputs

| Input | Source | Definition / XV role | Status |
| --- | --- | --- | --- |
| FID outcome + cause/secondary labels | final FID record once completed (its hash REQUIRED) | `FID01_GO`; `FID01_NO_GO` cause `WL_OF`/`OF_MESH`; `INCONCLUSIVE_*`/`INCOMPLETE`/`INVALID` retained exactly | REQUIRED_FROM_FID |
| Registered M3b rule (FID §8) | same record | exact estimator, normalization, and decision rule M3b must use | REQUIRED_FROM_FID |
| `S_d`, `S_d_OF` | FID §8 | `S_d` (M2-registered): dimensionless paired GRID-sensitivity term on flow_32-vs-flow_48, \|Δ̄48 − Δ̄32\| / max(\|J_b,48\|, J_scale), symbols as registered there — NOT a placement SD. `S_d_OF`: dimensionless, median over tier-A designs of \|Delta_V3 − Delta_V2\| / \|F_parent,V3\| | REQUIRED_FROM_FID |
| `sigma_d`, per-run SE | FID/M2 records | placement SD of paired differences and standard errors, units N; kept separate from S_d/S_d_OF | REQUIRED_FROM_FID |
| `g_min` (WL / OF) | FID §8 | WL: max(2·S_d, x*/abs(Jb48)); OF: 2·max(S_d, S_d_OF); symbols as registered, prospective forms | REQUIRED_FROM_FID |
| R3 / EXPORT label | FID §6.5 / §6.6 | exact registered labels, incl. `R3_CHALLENGED`, flow48 `NOT_MEASURED`, `EXPORT_SENSITIVE`, `EXPORT_UNRESOLVED` | REQUIRED_FROM_FID |
| Geometry version | SCREEN freeze | registered version + content hash; all XV runs bind to it | REQUIRED_FROM_SCREEN |
| Parent / finalist hash | SCREEN freeze | state/geometry SHA-256 + campaign input hash; finalist does not exist yet | REQUIRED_FROM_SCREEN |
| Constraint set + margins | FID/SCREEN records | registered hard constraints; re-evaluated in XV, never inherited as passed | REQUIRED_FROM_FID/SCREEN |
| Grids | FID/SCREEN registrations | WL: two grids flow_32/flow_48 only (no flow_24, no new WL coarse grid); OF: three independent grids V1/V2/V3 for the XV arm | REQUIRED_FROM_SCREEN |
| Backend applicability | FID/SCREEN registrations | WaterLily Kaggle T4; OpenFOAM local Docker under LOCAL-OF-01; no new-pipeline equivalence assumed; runtime identity verified before any GPU measurement | REQUIRED_FROM_FID/SCREEN |
| Budget + rerun cap | XV registration | binding finite budget and identical-infrastructure rerun cap, fixed before any run | REQUIRED_AT_REGISTRATION |

In [FID §8](https://github.com/ramhachi/CFD_opt_sdf/blob/78e1e76f/docs/fid01_registration_2026_10_21.md#8-consequences), `x*` is the smallest absolute flow_32 difference of a passing tier-A/B design above every non-passing tier-B difference. Its value is a final-FID handoff, not recomputed from XV selection. The WL-defined, dimensionless `S_d` in the OF floor is deliberately inherited from FID §8; XV does not replace it with an OF placement SD or run a new WL grid to estimate it.

## 2. Statistical contract — one finalist

Registered FID definitions (at `78e1e76f`; final values REQUIRED_FROM_FID): §6.1 derives the V3-shift uncertainty as the leave-one-out residual SD across the multiple tier-A designs of the ΔV3-vs-ΔV1 regression, dof n−2; §6.3 defines the G3-set as that cross-design regression set; `scripts/fid01/analyze_fid01.py:270-291` ([permalink](https://github.com/ramhachi/CFD_opt_sdf/blob/78e1e76f/scripts/fid01/analyze_fid01.py#L270-L291)) returns `UNRESOLVED_DATA` for n<3 — insufficient ensemble is unresolved, never zero SE.

XV is ONE finalist vs ONE parent: no design ensemble exists, so the cross-design regression, leave-one-out SD, and dof n−2 cannot be mechanically reused. The XV registration must fix, before freeze and before any run:

1. **`SINGLE_FINALIST` V3 SE rule.** Predeclared valid phase/shift *ensemble* (multiple valid samples of the paired comparison) or an independently justified calibration uncertainty. WL `sigma_d` is never borrowed into the OF arm. The SE definition covers the zero-variance case: a legitimate, independently justified exact-deterministic identification may set SE=0, but SE=0 is never inferred from one observation.
2. **OF V1–V3 paired consistency plan (the only three-grid plan).** Parent and finalist evaluated on the three independent OF grids, common phases, paired differences; the finest-grid (V3) disagreement rule is predeclared — explicit outcome, never a silent drop of V3 and never post-hoc exclusion.
3. **WL side = SCREEN handoff check.** SCREEN owns WL validation on flow_32/flow_48; XV verifies that handoff (geometry/finalist integrity and flow_48 confirmation) and builds no WL grid itself.
4. **Threshold inheritance with pre-disclosure.** Exact `g_min` values and the §8 rule as registered, or each prospective difference disclosed before runs. Never infer 0.68 % in place of `g_min`, never substitute an arbitrary 2 %, and no old literal-E2 absolute form re-added on top of the registered M3b mapping.

## 3. Composed pass gate (proposed rule for the XV registration)

PASS requires ALL of, on the registered geometry version: (a) the registered FID §8 M3b rule — exact estimator, normalization, threshold — applied to paired parent-vs-finalist differences with the §2 SE and OF V1–V3 consistency outcomes; (b) independent feasibility: the registered hard constraints re-evaluated on the finalist's actual registered geometry, on the XV OF arm, with propagated uncertainty; (c) SCREEN handoff verified (§2.3); (d) every §4 trigger resolved, or recorded not-triggered with its FID label value. Any unresolved or missing input keeps the outcome out of PASS; it never resolves by default.

### 3.1 G5b is fidelity, not feasibility

Preserved G5b facts (unchanged FID registration): the drag response ratio must lie in [0.5, 2] where `abs(Delta_drag_32) >= 0.002 N` and `abs(Delta_drag_32) > 3*SE_eff`. If either eligibility condition fails, its G5 verdict is PASS with a not-tested note (no fidelity information), rather than evidence that a ratio lies inside the band. A near-zero negative WL drag beside a positive OF drag can be G5-PASS this way, so G5 pass must never be mapped to constraint pass: compliance is decided only by (b).

## 4. Obligations, labels, and discipline

Label-triggered obligations (checked against FID labels at registration; a not-triggered state is recorded with the label value, never silently skipped):

- FID §6.5 `R3_CHALLENGED` or flow48 `NOT_MEASURED` → the registered rule "EVERY SCREEN/M3b candidate — the whole pool, not only XV's parent/finalist — is confirmed on flow_48 at P>=2" is a SCREEN obligation. XV must check SCREEN complied; non-compliance is not repaired by belated substitution and blocks the handoff outcome per the registered rule.
- FID §6.6 `EXPORT_SENSITIVE` or `EXPORT_UNRESOLVED` → the XV registration contains a predeclared export-resolution check (exact label `EXPORT_UNRESOLVED`, not bare `UNRESOLVED`).

Discipline:

- SCREEN/M3b meshes are optimization data. XV's OF meshes are judgment-only holdout data: used once for the verification decision, never fed back into geometry or mesh selection.
- No finalist retuning after results; a FAIL is a decision, not a tuning signal. No per-grid or per-phase rule variants are added without a new registration.
- Proposed terminal labels (**PROPOSED_TO_REGISTER** — binding spellings are fixed only in the XV registration): `XV01_PASS` (composed gate fully passed); `XV01_FAIL` (run set completed and a **resolved** constraint violation, or a boundedly negative verified decision); `XV01_INCOMPLETE` (registered run set not completed by pipeline/budget); `XV01_UNRESOLVED` (completed; data insufficient, e.g. V3 conflict, unresolved SE, missing access). Missing or uncertain data is never a physical NO_GO; only resolved violations are FAIL.
- Retry: FID's retry cap governs FID-01 only and is not imported. XV fixes its own budget and an identical-infrastructure rerun cap at registration; no result-guided finalist retry and no automatic loops.

## 5. Finite budget (structure; numbers REQUIRED_AT_REGISTRATION)

Enumerated before freeze, no exploratory extras: parent on OF V1/V2/V3; finalist on OF V1/V2/V3; paired comparison on common phases; export-resolution check only if §4-triggered; WL role limited to the SCREEN handoff check; OpenFOAM independent arm as registered (local Docker, LOCAL-OF-01-gated). Binding walltime/compute cap and rerun rule are fixed at freeze.

## 6. Open items (finite; none started)

1. Complete FID-01 #62 under its existing registration; record outcome, cause, secondary labels, and the completed record's hash (infer nothing from `78e1e76f`).
2. SCREEN-01 #64 registration and execution → finalist, parent hashes, geometry version, constraint margins.
3. GEOM-03 #70 decision only if the R3 composite is adopted; otherwise a registered R0-clean fixed set must already exist.
4. Write the `SINGLE_FINALIST` V3 SE rule (§2.1).
5. Write the OF V1–V3 paired consistency plan incl. the V3 conflict rule (§2.2).
6. Fill every `REQUIRED_FROM_*` cell; determine §4 triggers and verify SCREEN's flow_48 P>=2 compliance over the whole pool.
7. Fix the binding budget, identical-infrastructure rerun cap, and terminal-label set at registration.

Until items 1-2 land, XV-01 remains blocked ([STATE](STATE.md)); this document changes no flag, no registration, and starts no compute. Commits, issue filing, and validation runs are handled by the parent task.
