# XV-01 plan review — governance / controls angle (sonnet, independent, read-only)

Reviewed snapshot: registration revision 0 at commit 02a74312 (SHA-256 1fb669ff42902161f54a3a3335e99334cf414a7716d50d50e3c4353e8476721a; the same file content is at commit 81826220 after the rev. 0 commit was rebased onto the integration head f8e2e358, whose tree equals the reviewed base; that rebase is the "HEAD moved" event the reviewer noted). Report of the reviewer (2026-10-31/11-01), recorded verbatim. Reviewer scratch: /private/tmp/claude-501/xv01_review_governance/, not committed.

---

XV-01 (#65) registration revision 0: PROC-01 plan review, governance / controls angle (independent, read-only)

Reviewed: docs/xv01_registration_2026_10_31.md, SHA-256 1fb669ff42902161f54a3a3335e99334cf414a7716d50d50e3c4353e8476721a. The worktree file still hashes the same. Line numbers below refer to that file unless a path is given. REG means the registration; req means docs/xv01_registration_requirements_2026_10_22.md.

Note on the worktree: while I was reviewing, HEAD moved to 81826220 (a merge of #76) and an untracked docs/evidence/xv01_2026_10_31/README.md appeared. I did not create either. I wrote only under /private/tmp/claude-501/xv01_review_governance/.

Severity scale: P1 = must fix before freeze; P2 = should fix; P3 = minor.

## P1 findings

**G1 (P1). Outcome order, §5.9 (L130-136), with §1 (L19), §5.6 (L119-120), §8 (L191-192) and req §4 (L56). A FAIL can be issued with unjudged chain controls and on an incomplete run set.**
- req §4 defines the label as "`XV01_FAIL` (run set completed and a **resolved** constraint violation ...)". REG step 3 (resolved failures) comes before step 5 (INCOMPLETE and UNRESOLVED). SCREEN did the opposite: its step 4, INCOMPLETE, is evaluated "whatever the other confirmation data show", before step 6 NO_GAIN.
- NC `MISSING` (fewer than 12 roll pairs, L119) is routed only through step 5. A NOT_CONSISTENT NC voids a FAIL (step 2), but an unjudged NC does not.
- Example: two V1 kernels lost, so V1 and NC are missing, and a resolved DRAG_V2 FAIL still gives `XV01_FAIL`.
- Step 1 is inconsistent with this. If V3 is wholly lost, the outcome is INCOMPLETE even when V1 shows a resolved GAIN FAIL. If V3 is half lost (parent has at least 3 pairs, finalist partly invalid), a FAIL is possible.
- §8 gives FAIL no re-registration (L191 vs L192). A FAIL issued on incomplete evidence therefore closes #65 permanently.
- "traces to a declared lost or not-run kernel" (step 5) is not mechanical when a lost kernel and non-convergent cases both reduce the same level.
- None of this is in the §14 inventory.
- Proposed change:
  - Insert a gate before step 3. If NC is MISSING, or any registered kernel is declared lost or not run, no FAIL and no PASS is issued. The outcome is INCOMPLETE if any kernel is lost or not run, otherwise UNRESOLVED (NC_MISSING). Resolved failures are listed as descriptive "would-be causes".
  - Define INCOMPLETE mechanically: at least one lost or not-run kernel exists, and counting its cases as valid would lift some rule above its §4.5 minimum. Otherwise the outcome is UNRESOLVED.
  - If the registrant prefers FAIL-on-partial-data, add it to §14 as a deviation from req §4 and grant FAIL-on-incomplete-set the one re-registration.

**G2 (P1). §7.5 (L187), the stage table (L27), §8 (L190-193), memo D7. The funding decision, XV01_NOT_FUNDED and every pre-freeze exit are unconstrained.**
- Funding is decided at freeze 2, after the finalist smoke and probe statuses are known, by the registrant (the memo header, L3, says "Decision-maker: the registrant"). The text itself states P(PASS) ≈ 0.2 and that FAIL is more likely (§7.3).
- XV01_NOT_FUNDED means "no outcome; M4 decides with SCREEN's L1 result". That is the only exit that avoids the likeliest result while leaving the L1 gain usable.
- Nothing bounds it:
  - There are no funding criteria.
  - §8 has no NOT_FUNDED row.
  - The "at most one re-registration" cap (L192) covers only UNRESOLVED, INCOMPLETE and INVALID, so a later XV registration with different rules is not barred.
  - SCREEN §7 states that SCREEN does not bind XV's compute decision.
- Other pre-freeze stops have no terminal record and allow unlimited "new plans":
  - handoff mismatch (L35, "not frozen; a defect record")
  - §3.2 mismatch (L38)
  - r = 4 X1 failure (L44, "stops the registration")
  - replay mismatch (L83)
  - probe failing twice (L85, "a new plan")
- A finalist smoke that cannot mesh or converge is not an "engineering defect", because bytes and template cannot change (L203). No rule covers it.
- The fallback for an r = 4 X1 failure (drop EX?) would be a rule change made after seeing geometry.
- Proposed change: register an exit table before freeze 1.
  - Each pre-freeze exit gets a terminal record (for example `XV01_NOT_REGISTERED(cause)`).
  - Every exit counts against one shared allowance for #65 (same finalist, rules no weaker).
  - NOT_FUNDED is allowed only for a host or resource reason recorded before the smoke statuses are read, or for an explicit user decision. State that the pass probability is not a funding criterion.
  - Funding is mechanical: fund iff the freeze-2 budget record T ≤ cap and the smokes and probe meet registered status criteria.
  - A finalist that cannot be run becomes a registered outcome (for example INCOMPLETE, cause `FINALIST_NOT_RUNNABLE`), not a funding choice.
  - Add the §8 row: any non-PASS, NOT_FUNDED included, leaves L2 unattained, and L1 may not be cited as verification.

**G3 (P1). §4.5 (L80), §10 (L202), §4.3 (L74). Kernel loss is not mechanical, and runner statuses are unclassified.**
- infra/kaggle/kernel_openfoam_xfid_gridphase_x3_formal/runner.py L321-340 writes `RUNNER_EXCEPTION` (fail-soft), `NOT_RUN_CONSECUTIVE_FAILURES` and `NOT_RUN_TIME_BUDGET`. L222-227 can write `PARSE_FAILED`. The kernel then finishes normally with rc 0.
- Neither §4.5 nor §10 classifies these statuses. By the registered text the kernel output is "valid", "the first valid output is authoritative", and a per-case failure is "a result, never a rerun".
- A disk-full or Docker-OOM event can therefore erase hundreds of V1 cases with no rerun, and the outcome becomes UNRESOLVED_DATA instead of INCOMPLETE.
- "stopped by a host or Docker failure" is operator judgement. SCREEN froze a signature table and a classification record (SCREEN §9); XV has neither.
- `--lost KERNEL=ID` and `--not-run` are declared by the registrant. As written, the analyzer does not check them against the archived attempt records, so a declaration could discard a valid unfavourable kernel.
- `launch_deadline_hours` and `stop_after_consecutive_failures` semantics are not registered. FID's criteria have `launch_deadline_hours: 200.0` (docs/evidence/fid01_2026_10_21/of/criteria/v1_1.json).
- Proposed change: add a status mapping to §4.5 and §10.
  - Physical results: snappyHexMesh_FAILED, checkMesh_FAILED other than the allowed concave case, and non-convergence.
  - Infrastructure statuses: RUNNER_EXCEPTION, PARSE_FAILED, NOT_RUN_*, a stage timeout, rc ≠ 0, a dpkg mismatch, and an install-guard failure. Each is a kernel loss with one identical full-kernel rerun.
  - A frozen signature table (default = not infrastructure) and a classification record per attempt.
  - The analyzer refuses `--lost` unless both attempts classify as infrastructure, and refuses to drop any kernel that has a valid output.
  - Register `launch_deadline_hours` (at least twice the V3 kernel estimate) and the consecutive-failure rule.

**G4 (P1). §4.4 (L77), §4.6 (L85), §4.3 (L72-74), §7.5. The budget cap is not binding where it matters.**
- T > 250 CPU h is tested only "before every rerun and before the second V3 wave". Nothing happens if the freeze-2 budget record already exceeds the cap.
- The registered endTime-12000 contingency collides with the cap. I used 33,566 s per V3 case at about 4,500 iterations, that is about 7.46 s per iteration:
  - Whenever endTime 12000 is triggered, the finalist needs more than 6,000 iterations, so at least 12.4 h per case.
  - T ≥ 15.2 + 8 × (9.3 + 12.4) ≈ 189 CPU h with no reruns.
  - One wave rerun adds at least 4 × 21.7 h, giving about 276 CPU h, which is over 250. The "one identical rerun per kernel" of §10 is then unfundable.
  - Even without the contingency, the claim "cap admits one rerun of every V3 kernel of one wave" holds only if the finalist converges in 4,950 iterations or fewer. FID's V3 designs took 4,415-4,599, and the finalist is in the unvalidated camber extension.
  - T alone exceeds the cap at about 9,650 finalist iterations.
- Wave composition and push order are not registered.
  - A budget stop before wave 2 leaves at most 2 complete V3 pairs, below the minimum of 3 (§4.5). The outcome is then certainly INCOMPLETE, after about 75 CPU h or more have been spent.
- "the decision goes to the user (not an automatic rule change)" is undefined. A raised cap would be an unregistered amendment.
- Smokes and probe are excluded from the cap and are not bounded in number (L203 allows repeated "engineering defect" re-freezes). Each V3 probe costs 8-20 h.
- Proposed change:
  - Compute T for the whole V3 stage at freeze 2 and make "T > cap" a mechanical no-fund or `--not-run BUDGET` for the affected kernels. No user override; a different cap needs re-registration.
  - Order the waves pair-complete and register that order.
  - Cap attempts: each smoke once plus at most one repeat after a registered defect; the probe at most at endTime 6000 and 12000.
  - Add a margin rule so a marginal probe cannot hide a likely loss. For example, raise endTime if probe iterations exceed 0.9 × endTime.
  - Reconcile the "one wave rerun" statement with the actual estimate.

## P2 findings

**G5 (P2). §3.1 (L35), §3.2 (L38), §6 (L149), L159. The "independent" re-evaluation re-runs the same code, and the handoff is verified by hash only.**
- §3.2 re-runs `screen01_pool.admissible_rows` (fingerprint f5a5a95a…) on bytes reconstructed from the same handoff, and requires equality with the handoff row. Equality is guaranteed unless the environment drifted. It detects drift, not infeasibility, whereas req §3(b) asks for "independent feasibility ... on the XV OF arm".
- Nothing is evaluated on the OpenFOAM arm. The runner records `stl_sha256` per case (runner.py L204), but the analyzer is not required to compare it with the frozen STL plus shift.
- R0 `min_feature_width` is placement-dependent with a known one-cell artefact (GEOM03_NO_GO). Re-running it at the native placement says nothing about the continuous finalist.
- The WaterLily confirmation values (Delta_32, SE_eff, P, `R3_CONFIRMED`) enter §6 (L149) as constants. "The analyzer re-reads the SCREEN handoff ... by SHA-256" is a hash check of a JSON, not a re-derivation from the verify tables. req §2.3 asks XV to verify the flow_48 confirmation, and the SCREEN freeze chain (each freeze binding the previous) is not re-verified.
- Proposed change:
  - P0 re-runs `analyze_screen01.py main` and the SCREEN freeze verification into scratch paths and requires byte equality with analysis.json and xv_handoff.json.
  - P0 compares Delta_32, SE_eff and the labels with the §6 constants.
  - Add a differently coded STL-only check: closed surface, signed-volume ratio against `stl_volume_vs_parent`, bounding box inside the template domain at the maximum 4 mm shift, and min-z margin. It must not import `screen01_pool`.
  - The analyzer compares every case record's `stl_sha256` and `triangles` with the frozen values.
  - Add to §1 that XV01_PASS says nothing about the finalist's minimum feature width, and that constraints were re-run, not independently re-measured.

**G6 (P2). §4.5 (L80). Finalist-only invalid cases can be dropped and still allow PASS.**
- A non-converged or invalid case is "data loss ... never a rerun and never a FAIL"; pairs are dropped. Minimum data is V1 ≥ 12 of 16 pairs, V2 ≥ 3 of 4 and V3 ≥ 3 of 4.
- PASS is therefore possible with 25 % of the finalist's pairs missing where the parent converged at the same shifts. That conditions Delta on the stability of the finalist's steady solution, in the camber extension where FID has no evidence. FID had 733 of 733 valid cases, so this is new behaviour.
- Proposed change:
  - Define `FINALIST_ASYMMETRIC_LOSS` (finalist, NC or EX state invalid while the parent is valid at that shift).
  - PASS requires none at V2 and V3 (and a stated cap at V1). Otherwise the rule is UNRESOLVED_DATA with a cause.
  - Report Delta under worst-case treatment as a sensitivity label.

**G7 (P2). §5.4 G3 (L111), §4.2 (L63), req §2.2. The V1-V2 spread uses unmatched ensembles with zero covariance.**
- G3 compares Delta_V1 (all 16 pairs) with Delta_V2 (pairs 81-84) and uses `sigma_R = sqrt(SE_V1^2 + SE_V2^2)`. The pairs 81-84 are in both, so the independence assumption is wrong. pass_probability.py L93 does the same with `math.hypot(s1, s2)`.
- §4.2 says grid contrasts use common pairs, and §5.5 does that for V3, but G3 does not. req §2.2 requires "common phases". The preparation note (screen_xv_preparation, L64) says not to set the grid covariance to zero without grounds.
- Proposed change: judge G3 on the common pairs 81-84 with margin units like §5.5, or compute sigma_R from the SE of the per-pair unit differences. Keep the 16-pair form as descriptive.

**G8 (P2). §2 (L31), §10 (L205), §11 (L209). The analyzer-defect and ambiguity protocol is weaker than the SCREEN precedent.**
- A discrepancy is "an analyzer defect to fix before writing", so the fix is made with real forces visible.
- Text-silent cases (the "traces to" test, non-finite forces in COMPLETED cases, G3 with m = 0, and others) would be resolved after the data are seen. SCREEN fixed these in a pre-freeze reconciliation record (SCREEN §5.11) bound in freeze 1. XV's freeze-1 list (L209) has no such record.
- The "independent second implementation" is written by the registrant. Source-review-later amendments (L203) may touch the analyzer or checker.
- Proposed change:
  - A pre-freeze synthetic cross-check plus a reconciliation record, hashed in freeze 1.
  - At analysis time, any uncovered discrepancy is resolved by the reading less favourable to PASS. The repair only makes code match text, and its diff and both outputs are committed before the write.
  - The checker is written by a separate session from the text alone.
  - Post-review amendments rerun all branch tests and record the diff.

**G9 (P2). §4.6 (L83-85) and §4.7 (L88). Blinding relies on discipline, and the smokes and probe are unbounded.**
- The runner writes the finalist's window means into `case_result.json` (`record["forces"]`, runner.py L222-224) and rewrites `result.json` after every case (L342). "force files are removed by the sanitiser" does not by itself cover those JSON keys.
- It is unspecified whether the replay (which keeps parent forces) runs in a separate kernel and output directory from the finalist smoke. The sanitiser is not in the freeze-1 code list.
- Proposed change:
  - A hashed status-extractor with a key whitelist (status, stage return codes, counts, solver converged and iterations, wall) as the only reader before `main`.
  - Sanitiser code hash in freeze 1, and an assertion that no `forces` key or `coefficient.dat` remains for any non-replay case.
  - The replay runs in its own kernel.
  - See G4 for the caps on attempts.

**G10 (P2). §4.1 (L54), §11 (L209-211). The freeze content is incomplete.**
- L209 lists "python and numpy versions". The analyzer needs scipy (t quantiles). The P0 STL export needs scikit-image (scripts/geom02_canonical.py L74 requires 0.25.2; commit 66ab7c37 shows CI without it). SCREEN pinned both.
- Also missing from the freeze:
  - Docker, Rosetta and macOS versions
  - `launch_deadline_hours`
  - the wave and push plan
  - the sanitiser
  - the G8 reconciliation record
  - the integration commit that contains the merged #76 (L6 still cites the branch and PR)
- Every kernel start downloads the installer and apt indexes (runner.py L266-279) and fails closed on a SHA mismatch. Drift between V3 waves, 18 h or more apart, is a deterministic whole-wave loss that the one identical rerun cannot repair.
- LOCAL-OF-01 qualified only the V1 template. XV has no V2 or V3 replay, and the freeze-2 replay is not repeated later.
- Proposed change:
  - Add all of the above to freeze 1 or 2.
  - Add a V2 parent replay (FID 49+ values exist) and a closing V1 replay (about 100 s, descriptive).
  - Define one `ENV_DRIFT` event (install guard fails for all remaining kernels) as INCOMPLETE with that cause.

**G11 (P2). §7 (L160-181), §9 (L197), memo D1/D2/D5. The claim that no choice raises the pass probability is not supported as phrased.**
- §9 says "§7 shows every choice that could be made looser ... would raise it". pass_probability.py and .json compute none of these except `p_clear_x_F_parent_V1` (the V1 gain only). There is no ablation block.
- The claim that no choice was made to raise the probability also does not hold in direction:
  - The memo rejects stricter alternatives, and each rejection raises P(PASS): option A (D1, dof 1), copying the 1.45e-3 N residual (D2a), and the whole-interval V3 rule (D5d).
  - The G5b "not tested" status (see G15) does the same.
- The model's `rules()` (L81-101) omits G1 on V1-V3 sign, G2, EX, NC and determinism, so P(PASS) is an upper bound.
- `SE_PLAN` for V3 (L25-26) equals the floor divided by 2, which assumes V3 placement scatter equals the V2 pooled SD. FID's V3-V1 residual is 1.45e-3 N. No sensitivity is shown, and DRAG_V3 PASS would collapse if V3 scatter were 3-5 times the floor. The funding decision rests on 0.17-0.22.
- Proposed change: add to pass_probability.py and its JSON one ablation per registered choice against its rejected alternative (P(PASS), P(FAIL), P(UNRESOLVED)), all rules, and a V3-SE sensitivity grid (×1, ×2, ×4). Reword §9 to a checkable statement. Fix the cross-reference at L187.

**G12 (P2). §14 (L222-231). The deviations inventory is incomplete.**
- Missing rows:
  1. FAIL on a completed run set (req §4) versus step 3 (G1).
  2. The FID §5.3 V3 contingency (remove V3, record `V3_NOT_CONVERGED`) replaced by endTime 12000 and a stop (L85). The V3 template then differs from FID's.
  3. req §5 "no exploratory extras; export check only if §4-triggered" versus W4, M, R-best, the determinism repeat and an outcome-relevant EX. L231 lists the cases but not the deviation from req §5.
  4. G5(a) moved from FID's OpenFOAM-arm check to a P0 re-run of SCREEN code (L38).
  5. GAIN required on each of V1, V2, V3. FID §8 gives a level-less minimum, and the memo (D3) records only the normaliser.
  6. NC MISSING gives no INVALID, but FID §6.6 says "otherwise FID01_INVALID".
  7. Minimum data V2 ≥ 3 and V3 ≥ 3 versus FID's V2 ≥ 1 and V3 "its shift".
  8. The `XV01_NOT_FUNDED` label (new).
- Proposed change: add these rows with a stricter / looser / neutral label and the decider.

**G13 (P2). §5.6 (L119-121), §5.8 (L127), memo D6 (decision_memo.md L31). Chain-control coverage is thin, and PASS survives unjudged controls.**
- The memo calls W4 `REF_CONSISTENT` "a chain check of the shape path (the NC is a translation and does not exercise the shape export)". REG L127 says an inconsistency "is reported, not a chain failure". No outcome-relevant control exercises shape → STL → mesh → force on new shifts: NC is a translation, the replay is parent-only, determinism is parent-only, and EX tests only export resolution.
- Determinism `NOT_JUDGED` (L120) can coexist with PASS. req §3 says "Any unresolved or missing input keeps the outcome out of PASS".
- The replay is only a precondition of freeze 2 (L121).
- Proposed change:
  - Make `REF_INCONSISTENT` block PASS (rule registered), or correct D6.
  - Determinism NOT_JUDGED gives no PASS.
  - Add the V2 replay and closing V1 replay from G10.

**G18 (P2). §4.3 (L70), §5.5 (L116). Kernel `v1_1` is a single point of failure.**
- v1_1 holds the only V1 pairs shared with V2 and V3 (81-84) and the determinism repeat.
- If it is lost after its rerun:
  - V1 ∩ V3 is empty, so V3 consistency is UNRESOLVED_DATA (|J| = 0 < 3).
  - The determinism check is gone.
  - V1 has exactly 12 pairs, with zero slack for the finalist, NC and EX minimums.
- Proposed change: spread the common pairs one per V1 kernel. For example, v1_k = pairs {80+k, 84+k, 88+k, 92+k}. The case count and cost are unchanged, and one V1 kernel loss then leaves 3 common pairs.

## P3 findings

**G14 (P3). §1 (L13, L17, L19), §5.9 (L133, L138). Labels and claim wording can over-claim.**
- `XV_OF_GAIN_CONFIRMED` can accompany `XV01_FAIL` (causes `WL_OF` or `OF_MESH`), and its name reads as "improvement confirmed".
- The cause `WL_OF` shares its spelling with FID's cause that auto-triggers the one-shot smooth-advection study (STATE.md "Branch rules"). §8 gives M4 the decision, so say explicitly that nothing is automatic.
- The question text "insensitive to the STL extraction" overstates EX, which tests only export resolution (r = 4 versus 8) of the same routine.
- The PASS statement "its WaterLily improvement is confirmed by independent CFD" is independent in the solver but not in the geometry (same SDF-derived STL), on non-converged meshes.
- The camber-extension disclosure and the untested camber drag retention are in §1 and §7.3, but they are not mandatory fields of the §8 outcome record.
- Proposed change:
  - Rename the label (for example `OF_GAIN_DRAG_ABOVE_FLOOR`).
  - Rename or annotate `WL_OF` in XV.
  - Reword the question and the PASS statement.
  - Add `in_camber_extension` and the measured V1/V2/V3 camber drag retention to the PASS record.

**G15 (P3). §5.4 G5 (L113). The G5b "not tested" status depends on a 0.3 % margin.**
- The status depends on |-1.9939e-3| < 2e-3, a margin of 6.1e-6 N. The flow_48 drag, -2.79e-3 N, would be eligible.
- A counterfactual G5b (ρ_drag in [0.5, 2]) would require V1 drag ≤ -1.0e-3 N, against a projected median of -1.10e-3 N, so it carries real fail and unresolved mass.
- The status is mechanically correct per req §3.1 and FID.
- Proposed change: state the margin, and register a descriptive `G5B_COUNTERFACTUAL` label. It must carry no outcome effect.

**G16 (P3). §8 (L192), §4.2 (L63). Re-registration wording and Halton indices.**
- "rules no weaker" is undefined. Make it mechanical: every threshold, floor, band and minimum at least as strict, and the PASS set a subset.
- Halton indices 73-79, 97, 98 and 100 are not accounted for. Declare them reserved or unused.
- Who records "an explicit recorded decision" is not stated.

**G17 (P3). Cross-references and recording slips.**
- L38 "G5a = PASS (§5.6)" should read §5.4.
- L187 "(§14)" cites a row that does not exist.
- L6 cites the SCREEN branch and PR #76, which is now merged.
- §3.1 (L35) records `R3_CHALLENGED = false` but not FID's `R3_E2_EXCEEDED = true`.
- memo D1's "a resolved FAIL on V1/V2 has a probability of roughly 0.15-0.4" is not computed in pass_probability.json.

## Answers to the registrant's two open questions

- **D5, whether the upper V3 side (V3/V1 > 1.67) should be outcome-relevant.**
  - Keep it. Loosening a registered band after FID values were visible is exactly what §9 says it avoids.
  - Because FAIL has no re-registration and an upper-side violation strengthens the gain claim, give it its own cause (for example `OF_MESH_UPPER`). Say in §8 that it is reported beside `XV_OF_GAIN_CONFIRMED` (renamed per G14).
- **D7, funding on a low stated pass probability.**
  - Funding the full run set is reasonable, since the non-PASS outcomes are informative.
  - The decision must be made mechanical and bounded per G2 and G4. A discretionary NOT_FUNDED exit after the smokes should not exist.

## Checked, no finding

- All hash prefixes in the Inputs block match the files on disk: the handoff (ac0909e2…), SCREEN analysis (cbf0292b…), rs.json (66f7005d…), finalist.json (f7fd2456…), SCREEN registration (fa3e5f7e…), FID analysis (b89203d0…), FID registration (4d692af6…), M2 analysis (ee71c6d6…), req (ffd8328a…) and the lock (c105b7df…).
- Re-derived numbers:
  - x_OF = 3.36874e-3 N, and 1.25-1.32× stricter than the OpenFOAM-parent reading.
  - G4 bounds 5.043e-3 / 5.387e-3 N; t quantiles 1.753 and 2.353.
  - Case counts 257 / 16 / 16 = 289, and the 164 CPU h estimate.
  - The §7.3 camber, pitch and reflex drag and downforce retentions, checked against docs/evidence/fid01_2026_10_21/analysis.json.
  - pass_probability.py, copied to scratch and run with the repo venv, reproduces pass_probability.json byte for byte (seed 20261031). The §7.2 table equals the JSON.
- req §2.1 (SE = 0 never inferred; WaterLily sigma_d never borrowed), §2.4 (no 0.68 %, 2 % or literal-E2 floor added), §3.1 (G5b is not feasibility), §4 (triggers recorded as not triggered with label values), and §6 items 1-7 are all handled.
- #65 acceptance items are met:
  - S_d / S_d,OF are kept separate from sigma_d and SE.
  - The V2 pooled variance and the V3 regression residual are not copied as the SE; the floor is a disclosed partial borrow of the pooled quantity.
  - OpenFOAM meshes are holdout, with no feedback to geometry or selection.
  - All flags are false and `shape_update_allowed=false`.
- Written-once structure: exclusive `--out`, accepted criteria set from freeze 2, no interim analysis. The FAIL cause list is mechanically defined and ordered. The rerun rule (one identical rerun, same bytes, first valid output authoritative, both archived, no third attempt, timeouts never raised) is stated.
- §8 consequences: no substitution of other candidates, no finalist retuning, no second SCREEN round, flags unchanged.
- The drag rule (resolved non-increase on every level) and the normaliser are stricter than SCREEN D and FID, and are labelled so in §14.
- NC reference values equal the FID/M2 coefficients (-6.6148e-4 N, SE 5.792e-5).

## Verdict: GO_AFTER_FIXES

The structure is sound: a single finalist, a fixed run set, written-once analysis against an independent checker, inherited FID rules, stricter drag and normaliser choices, a stated pass probability, and an honest claim ceiling. Nothing needs redesign, and none of the fixes needs additional CFD.

The four P1 items are rule and text gaps that let a terminal outcome or a funding exit depend on unregistered judgement:
- a FAIL on incomplete or unjudged data (G1)
- a discretionary NOT_FUNDED exit and undefined pre-freeze stops (G2)
- runner statuses that silently become results (G3)
- a budget cap that the registered endTime contingency can exceed (G4)

The P2 items tighten the independence of the geometry re-evaluation, blinding, freeze completeness, the analyzer protocol and the honesty of the pass-probability claims. Because PROC-01 allows only one plan review, the source review must cover the revision-1 delta, including the §5.9 restructure, the status mapping and the exit table.
