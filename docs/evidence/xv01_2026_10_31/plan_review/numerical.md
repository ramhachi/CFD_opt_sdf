# XV-01 plan review — numerical / statistical angle (sonnet, independent, read-only)

Reviewed snapshot: registration revision 0 at commit 02a74312 (SHA-256 1fb669ff42902161f54a3a3335e99334cf414a7716d50d50e3c4353e8476721a; the same file content is at commit 81826220 after the rev. 0 commit was rebased onto the integration head f8e2e358, whose tree equals the reviewed base). Report of the reviewer (2026-10-31/11-01), recorded verbatim. Reviewer scratch: /private/tmp/claude-501/xv01_review_numerical/, not committed.

---

XV-01 (#65) registration revision 0 (commit 02a74312, SHA-256 1fb669ff...) - PROC-01 plan review, NUMERICAL / STATISTICAL angle

Method. I recomputed from the FID result.json files (733 cases) and the SCREEN handoff. I regenerated pass_probability.json from a scratch copy; it is bit-identical to the committed file. I wrote my own pair-level implementation of the §5 rule tree as written (13 rules) and ran Monte Carlo on it. Scratch files are in /private/tmp/claude-501/xv01_review_numerical/. No repository file was touched.

Result in one line: no P1. I found nothing mis-specified enough to need a redesign, and every number I could recompute matches. There are 7 P2 findings (disclosure, model and gap issues to fix before freeze 1) and 5 P3 findings. All sections cited are of the registration unless stated.

## P2 findings

**N1 (P2) §5.4, §7.1, §7.3. The binding V1 gain requirement is G4's 5.387e-3 N, not the 3.369e-3 N floor.**
- G4 PASS needs Δ_V1 ≥ 0.5·Δ_32 = 5.387e-3 N (I reproduced 5.0431e-3 and 5.3871e-3 with t = 2.3534). That is 60 % above x_OF.
- §7.1 states 1.00 central / 0.80 pessimistic. That is correct for GAIN_V1 only (I reproduced 1.000 / 0.801 / 0.919).
- Using the same §5.7 inputs for the PASS-relevant condition, P(Δ_V1 ≥ 5.387e-3) = 0.94 central and 0.30 pessimistic. The expected ρ is 0.59 central and 0.43 pessimistic. The pessimistic view therefore predicts a G4 miss. P(Δ_V1 < ~4.45e-3, a resolved G4 FAIL) is about 0.45 there.
- G4 is evaluated against Δ_32, which is selection-biased by b_K = 1.0e-3 to 2.7e-3 N (10-25 % of Δ_32). The expected attenuation is therefore built into the denominator.
- A G4 FAIL with GAIN and DRAG passing gives XV01_FAIL (cause WL_OF) for a design whose OpenFOAM gain clears the floor.
- Fix: state next to 1.00/0.80 the G4-relevant 0.94/0.30. Rewrite §7.3 "the binding risk is drag, not the gain" to name G4 as the second binding rule (model G4 pass 0.82 / 0.63 under b_K central / upper). Say in §8 that WL_OF can co-occur with XV_OF_GAIN_CONFIRMED.

**N2 (P2) §7.2-7.3, pass_probability.py L24, L67, L73. The model cannot represent the camber-extension risk, so "about 0.2" is the upper end.**
- The camber retention is bootstrapped from two designs (-11.3, -19.7): V1 0.77 / 0.61, V3 0.71 / 0.93. The finalist's camber part (+16.6e-3 N) is 1.5x the largest FID amplitude. It exceeds the net gain (10.8e-3 N), so any camber-retention error is amplified: net ΔV1 changes by 1.54·Δ_32 per unit of camber retention.
- EXT = 0.10 is a single draw per replicate (L67) applied identically to V1, V2 and V3 (L73). It cancels in every level ratio and adds no mesh inconsistency.
- Through-origin quadratic extrapolation of the FID OpenFOAM camber responses to -29.55 mm gives V1 ≈ 8.96e-3 N, against the model's 0.61-0.77 × 16.6e-3 = 10.1-12.8e-3 N. At V3 it gives about 2.4e-2 N, against the model's 1.4e-2 N. The V3 value rests on one V3 shift per design, so treat it as indicative only.
- Sensitivities (MC, my reimplementation; no shift / b_K central):

| Variant | P(PASS) | P(FAIL) |
| --- | --- | --- |
| registered | 0.22 / 0.17 | 0.50 / 0.57 |
| per-level camber noise sd 0.15 | 0.15 / 0.12 | 0.67 / 0.73 |
| per-level camber noise sd 0.25 | 0.10 / 0.07 | 0.79 / 0.83 |
| V3 camber retention ×1.25 | 0.15 / 0.12 | 0.69 / 0.73 |

- The "b_K upper" variant is not the §5.7 pessimistic scenario, because it keeps the family retentions (about 0.69 camber, 0.62 reflex) instead of 0.57. With retention scaled by 0.57/0.655 plus b_K,upper, P(PASS) = 0.055 and P(FAIL) = 0.78.
- Fix: add per-level independent extension noise and a camber-amplitude trend scenario. Add the true §5.7-pessimistic variant. Report "about 0.1-0.2 (0.06-0.22 depending on scenario), model uncertainty about a factor 2" instead of "about 0.2".

**N3 (P2) pass_probability.py L98-100. The V3-band SE is mis-scaled.**
- The model uses one s13 = hypot(SE_V3, 1.0e-3/2) for both margins. The registered SE(lo) scales with 0.6·σ_V1 and SE(hi) with 1.67·σ_V1.
- The model also uses the 16-pair V1 draw, not the 4-common-pair V1 mean, whose noise is about 5e-4 N.
- Effect when corrected: P(V3-band FAIL) 0.215 → 0.178 (central), PASS unchanged (0.168 → 0.167). §7.2's "V3 consistency 0.64 / 0.22" becomes 0.64 / 0.18 in my run.
- Fix: model the margins at pair level, or scale the SEs as above.

**N4 (P2) §5.3, §7.3. The drag rule is a resolved-decrease test, and the V3 drag "coin flip" is within model uncertainty.**
- "Resolved non-increase" (D + t·SE ≤ 0) means the upper bound is ≤ 0. A drag-neutral design cannot pass. For a common true drag change D at all three levels (V1 pair SD 5e-4, V2/V3 SD = f):

| True D (N) | P(PASS, all three levels) | P(any resolved FAIL) |
| --- | --- | --- |
| 0 | 0.00 | 0.06 |
| -1e-4 | 0.00 | 0.01 |
| -2e-4 | 0.17 | 0.00 |
| -3e-4 | 0.64 | 0.00 |
| -4e-4 | 0.91 | 0.00 |
| -6e-4 | 1.00 | 0.00 |

- With V1 pair SD 8e-4 (reflex-type designs reach 9.4e-4 in FID), PASS at -4e-4 is only 0.60.
- Effective V2/V3 thresholds when the floor binds (about 61 % of the time if σ = f): PASS iff D ≤ -1.62e-4 N, FAIL iff D > +1.62e-4 N. That is 0.05 % of the 0.33 N parent drag.
- Deterministic recomputation of the V3 drag: -1.5e-4 N. MC gives -1.28e-4 N, model SD 6e-4. Shifting the V3 median by ±3e-4 moves P(DRAG_V3 pass) across 0.29-0.66.
- The camber drag retentions come from WL drag differences with SE_eff 3.9e-4 on 1.2e-3 N (33 %) and 3.6e-4 on 2.0e-3 N (18 %). The model treats them as exact plus a lognormal with TAU = 0.08. With TAU_drag = 0.25: DRAG_V3 fail 0.32 → 0.41, P(PASS) 0.22 → 0.17.
- The WL decomposition at u = -1.5 (RS_FIT_POOR, beyond the ±1 axial points) is itself a ±1e-3 N model input.
- Fix: rename the label to DRAG_RESOLVED_DECREASE (or state the strict-decrease meaning in §5.3). Add the power table and the effective thresholds to §5.3. Whether to add a drag allowance is a policy choice; D4 reasonably rejects it. Do not present "binding risk = V3 drag" as a quantified fact.

**N5 (P2) §5.5. The V3 consistency rule is well-defined and computable, but several points need fixing.**
- The constant is a literal 1.67. The FID analyzer uses 1/0.6 = 1.6667.
- The parenthetical "point ratio of the common-pair means lies in [0.6, 1.67]" is true only for Δ_V1,J > 0. For Δ_V1,J < 0 the margins invert. This is inert for PASS because GAIN requires Δ > 0, but it can mislabel a FAIL. State "Δ_V1,J > 0".
- The floor f_DF = 1.98e-4 never binds. sd(lo) ≥ about 6e-4 and sd(hi) ≥ about 1.7e-3 for σ_V1 ≈ 1e-3. P(sd(hi) < f) is of order 1e-3.
- Operating characteristics (4 common pairs, dof 3, σ_V1 = 1e-3, σ_V3 = 3e-4, ρ = 0 / 0.5; larger noise gives similar results):

| True V3/V1 | P(point pass) | P(resolved FAIL) |
| --- | --- | --- |
| 0.6 | 0.50 | 0.05 |
| 1.0 - 1.4 | ≥ 0.99 | 0 |
| 1.52 (FID camber -19.7) | 0.89 | 0.004 |
| 1.67 | 0.50 | 0.05 |
| 1.8 | 0.12-0.14 | 0.21-0.24 |
| 2.0 | 0.00 | 0.67-0.74 |
| 2.2 | 0 | 0.94-0.97 |
| 0.5 | 0.00-0.02 | 0.49-0.66 |
| 0.4 | 0 | 0.93-0.99 |

- The false-fail rate at a band edge is the nominal 5 %, and it is below 1 % at ratio 1.52. The UNRESOLVED zones are about 1.67-1.95 and 0.5-0.6.
- Answer to D5: the upper side matters for PASS only through the point rule, which already blocks PASS above 1.67. The resolved upper-side FAIL needs a ratio ≳ 1.9-2.0. Mapping it to XV01_FAIL (OF_MESH) therefore changes a label, not P(PASS). Because a larger gain on the finest mesh does not contradict "gain persists", I recommend keeping the two-sided point-pass but reporting an upper-side-only resolved exceedance as XV01_UNRESOLVED with a cause V3_ABOVE_BAND (or a secondary label). This is a policy call; I flag it only.
- Efficiency note. The V1 and V2 pair-to-pair deviations are uncorrelated across the 12 FID designs (r = 0.03 downforce, 0.23 drag; n = 12, so the confidence interval is wide). Common pairs add V1 noise (5e-4, 7 % of Δ, against 2.5e-4 for 16 pairs) without a demonstrated covariance benefit. Keep the design, but also report V3 against the V1 16-pair mean.

**N6 (P2) §4.3-§4.6. Budget gap in the endTime-12000 contingency.**
- Measured simpleFoam cost is 7.27 s per iteration (33,067 s / 4,548) plus about 450 s of mesh stages per case. V1 + V2 take 15.2 CPU h.
- The cap becomes infeasible for a V3 case needing more than about 7,200 iterations (1.58 × the FID median). This is before any rerun, and the rule only checks T before reruns and before the second V3 wave.
- The probe's cost (up to about 25 h for a 12000 repeat) is excluded from the cap.
- Fix: require T_est ≤ 250 CPU h in the freeze-2 budget record. If it is exceeded, the funding decision is re-opened explicitly, not by default.
- Minor: "at least 7x the slowest measured need" is 6.9x for V3 (259,200 / 37,535 s). 164 + 74.4 = 238 fits under the cap, but the upper estimate 182 + 74.4 = 256 does not.

**N7 (P2) §7.2. The pass-probability record needs three label and wording fixes.**
- It does not model G1, G2, G5, EX or NC. All are near-certain passes, so this is harmless but should be stated.
- Planning SEs: V1 drag 1.0e-4 is the optimistic end for a reflex-containing design (FID V1 drag pair SD 3.8e-4 to 9.4e-4, so SE 1.0e-4 to 2.4e-4). The effect on P(PASS) is below 0.01.
- One-line fix: label the "b_K upper" row as not equal to the §5.7 pessimistic scenario (see N2).

## P3 findings

**N8 (P3) §5.2, decision memo D3. The normaliser rationale and the max() are off.**
- g_OF = 2·S_d,OF = 2 × 0.0063375, where S_d,OF = median|ΔV3 - ΔV2| / |F_parent,V3| (1.346e-3 / 0.2124). S_d = 0.0034 is not the active term.
- The M2 S_d precedent max(|J_b,48|, J_scale) is therefore the precedent for the inactive term. The literal FID reading is g_OF × |F_parent| = 2.56-2.69e-3 N. The registered x_OF = 3.369e-3 N is 1.25-1.32x that. That is a legitimate and disclosed stricter choice, and it matches SCREEN §5.7's convention (% of J_b,48 against 1.27 %). Say so, instead of citing the S_d precedent.
- max(J_b,48, |F_bar_parent,L|) is inert: every parent mean is 0.2008-0.2124 < 0.2658, so x_OF is the constant 3.36874e-3 N.
- "F_bar_parent,L = mean parent downforce over the level's valid XV cases" is ambiguous (r = 8 only? matched pairs only? repeat and r = 4 included?). Fix: freeze x_OF = 3.3687409403e-3 N and drop the data-dependent max.

**N9 (P3) §5.4. G5b is decided by 0.3 %.**
- The G1-G5 transcription matches FID §6.3 and the analyzer. The G4 numbers (5.043e-3 and 5.387e-3 N) are correct. t = 2.353 for G4 against 1.753 for the same SE_V1 in GAIN/DRAG is inherited from FID; note it.
- |Δdrag_32| = 1.99387e-3 N is below 2e-3 by 6.1e-6 N, which makes G5b "not tested". The model's V1 drag retention would be ρ ≈ 0.55, with about a 40 % chance of being below 0.5.
- Fix: state the knife edge, and report ρ_drag,V1 with its band label as a descriptive G5B_DESCRIPTIVE.

**N10 (P3) §4.5, §4.6, §5.9. Data-loss slack and pre-freeze gaps.**
- V3 has one pair of slack (minimum 3 of 4, and the V3 spend is 149 of 164 CPU h). The risk looks small: 0 of 733 FID cases were invalid, no kernel was lost, and V3 iteration counts were 4,415-4,599.
- The V1 concave fraction is 6.2-7.0 % across all 672 FID V1 cases against the 8 % validity limit. The finalist is a new shape, so state what happens if the V1 smoke exceeds 8 %. As written the only route is an engineering re-freeze that cannot change a rule.
- A failed r = 4 export gate of the finalist stops the registration. This makes EX unmeasurable rather than an informative outcome.
- "Valid pairs for the parent" in §5.9 step 1 should read "pairs valid for state and parent". Finalist data shortfalls are covered by step 5.

**N11 (P3) §4.6. The environment replay covers V1 only.**
- Add the FID V2 parent at Halton 49+ (about 0.5 h) and a template-hash equality check of the V2/V3 blockMesh and controlDict against the FID p0 probe cases. The V3 replay is too expensive.

**N12 (P3) Sampling meaning and small numeric nits.**
- Deterministic solver plus fixed Halton panel: the SE is a descriptive spread over the panel, as §5.1 says. The 4-pair V2/V3 panel 81-84 is sign-imbalanced (mean sign(xz) = sign(yz) = -0.5), and V1 on those 4 pairs differs from the 16-pair mean by about 4.3e-4 N (SD).
- G3 uses σ_R = hypot(SE_V1, SE_V2), so the V1-V2 covariance is zero, which the preparation note says needs a basis. It is conservative for the FAIL side if the true covariance is positive. State this.
- FID V1 parent mean downforce is 0.20186 N (§0 says "about 0.2017"). EX values in §1 are given as "6e-6 against 8e-4 for both W4 and W6"; the actual W6 values are 3.1e-7 against 9.8e-4. Both the "dof about 15" and the "12 designs" in the V2 pool should read dof 12.

## Independently reproduced, no finding
- V2 pooled pair SD 1.984576864434452e-4 / 1.3747177622390572e-4 N, dof 12, recomputed from the FID case files.
- Floor justification: the 1.45e-3 N V3-on-V1 residual is driven by one design. Without camber -19.7 it is 5.3e-4 N (the outlier residual is 3.5e-3 N). V3 single-shift noise is consistent with V2's single-shift SD of 4.2e-4 N, so the V2 floor is a plausible V3 scale, neither clearly conservative nor anti-conservative. SE_V1 without a floor and SE_V2/V3 with one is coherent. At dof 3 the floor binds about 61 % of the time if σ = f; the t(3) quantile is conservative relative to dof 12.
- t quantiles 1.753 (dof 15) and 2.353 (dof 3); t_{0.95,1} = 6.31 and the D1 alternatives (5 and 6 pairs give 2.13 / 2.02; each pair adds 37 CPU h).
- Halton 1-100: 200 distinct vectors (including mirrors); XV 81-96 and smoke 99 disjoint from 1-80. Sign mixing is limited and the first four pairs 81-84 are z-positive in the "+" member.
- Environment replay values (0.20139452023048948 / 0.3444265555692308 N; 572 iterations; 39,561 cells).
- Costs: V1 median 73.5 s, mean 104.0 s; V2 median 1,712.5 s; V3 median 33,566 s (30,339-37,535 s; 4,415-4,599 iterations); 289 cases; 164 CPU h (150-182); the "10.4 CPU h" for smokes plus probe.
- Iterative-convergence offset (V3 forces drift about 5e-4 N) cancels in paired differences (≤ 3e-5 N), well below the floor.
- quad9 coefficient order [p, c, r, p², c², r², pc, pr, cr] and the component split (downforce +2.081 / +16.605 / -7.739 / -0.839 / +0.666e-3 N; drag +1.521 / +3.009 / -6.024 / -0.041 / -0.458e-3 N).
- pass_probability.json regenerates bit-identically; the §7.2 table and per-rule values match; the s57 numbers match; hand recomputation gives V1 7.9e-3, V2 6.0e-3, V3 9.6e-3 N (ratio 1.21) against MC medians of 7.85e-3 / 5.92e-3 / 9.48e-3 N.
- D1 (d) savings: P(resolved FAIL on V1/V2-only rules) = 0.16-0.25.
- My full rule-tree implementation behaved sensibly:
  - clearly good design (DF 7.5 / 6.5 / 8.5e-3, drag -1.5e-3): PASS 1.00
  - drag -4e-4: PASS 0.91
  - drag 0: PASS 0.00, FAIL 0.065
  - drag +3e-4: FAIL 0.99
  - V1 exactly at the G4 edge: PASS 0.50
  - V1 = 4.5e-3: FAIL 0.45 (G4)
  - V3/V1 = 1.9: FAIL 0.44-0.47
- NC, EX and determinism logic transcribe FID. The EX SE of FID (7e-6 N against a tolerance of 8e-4 N) leaves a 57x margin.

## Verdict: GO_AFTER_FIXES
No decision rule is wrong or uncomputable enough to need a redesign. The SE rules are coherent. The floor is supported by FID data. The G1-G5 and NC/EX transcriptions are faithful, and the cost and Halton claims hold. The seven P2 items are all documentation, model or gap fixes: the G4 binding risk and the §5.7 probability (N1); the pass-probability model and its narrative (N2, N3, N7); the drag rule's semantics and power (N4); the V3 consistency rule's exact definition (N5); and the missing freeze-2 budget guard (N6). None changes a rule threshold. The honest expectation is XV01_PASS of about 0.1-0.2 (0.06-0.22) and XV01_FAIL ≥ 0.5, driven by DRAG_V3, the V3 band, and G4 under selection bias. The fixes should be applied before freeze 1 so that the §7.5 funding decision rests on a corrected record.
