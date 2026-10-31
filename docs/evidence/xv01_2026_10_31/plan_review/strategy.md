# XV-01 plan review — strategy angle (sonnet, independent, read-only)

Reviewed snapshot: registration revision 0 at commit 02a74312 (SHA-256 1fb669ff42902161f54a3a3335e99334cf414a7716d50d50e3c4353e8476721a; the same file content is at commit 81826220 after the rev. 0 commit was rebased onto the integration head f8e2e358, whose tree equals the reviewed base). Report of the reviewer (2026-10-31/11-01), recorded verbatim. Reviewer scratch: /private/tmp/claude-501/xv01_review_strategy/, not committed.

---

XV-01 (#65) registration revision 0 (commit 02a74312, SHA-256 1fb669ff...) - STRATEGY plan review for PROC-01

Method. I read the listed documents and `gh issue view 65` / `66`. I then re-ran the registrant's planning model: a scratch copy of `pass_probability.py`, same seed, ROOT patched, `main()` not called, so nothing was written into the repo. It reproduces the registered numbers exactly (PASS 0.219 / 0.168 / 0.083). I then varied its structural assumptions and applied alternative rule variants. Scratch scripts are in /private/tmp/claude-501/xv01_review_strategy/. I changed nothing in the repo. An untracked `docs/evidence/xv01_2026_10_31/README.md` (mtime 23:57) already existed and is not mine. Probabilities below come from the registrant's own model run under the variants stated; they are indicators, not forecasts.

Overall reading. The run set, estimators, pairing, chain controls and blinding are sound. The risk lies in what a FAIL or UNRESOLVED will be allowed to mean, and in one rule (the zero-margin drag test on every mesh) that cannot be evaluated at the available resolution. A "typical tier-A-like" design (all parts through the tier-A slopes, same WaterLily gain and drag) passes the registered gate with P = 0.97-1.00 in the registrant's model. The 0.17-0.22 is therefore specific to this finalist: a camber-dominated net with a drag cancellation. That is a legitimate thing for XV to measure. The fixes below are about making the measurement interpretable, not about easing the gain or fidelity tests.

S1 [P1] Zero-margin, resolved drag non-increase on all three meshes (§5.3, §7.3, §9, memo D4)
- The test is not decidable at the available resolution. DRAG_V3 PASS needs D_V3 <= -t*SE. With SE_V3 >= f/sqrt(4) = 6.9e-5 N and t = 2.353, that is D_V3 <= -1.6e-4 N.
- FAIL occurs at D_V3 > +1.6e-4 N. That is 0.046 % of the parent drag (~0.344 N), against a WaterLily finalist drag effect of 0.58 %.
- A design whose true V3 drag is the registrant's own median (-1e-4 N) passes with probability 0.18 at SE 6.9e-5 and 0.09 at SE 1.0e-4. Power is capped by the SE floor (taken from V2), and re-registration cannot repair it.
- A zero-tolerance inequality is untestable under finite resolution: the better the measurement, the more likely a design near the boundary "fails".
- L2 is stricter than L1 by construction. The SCREEN memo D1 rejected a resolved non-increase at P = 4, saying it rejects boundary finalists most of the time. It took a point sign and deferred the resolved drag test to XV (SE about 1e-4 N). XV now makes the strict version binding on every mesh, while the L1 drag resolution was 5.4e-4 N.
- The finalist's cushion (-1.99e-3 N in WaterLily) is eaten by mode-dependent retentions: camber V3 drag retention 0.84-0.92, reflex 0.59.
- The §9/D3/D4 selection principle ("a looser variant would raise P, so it is rejected") is itself probability-driven. The only defensible criteria are the claim and resolution quantities that exist before any XV force.
- Proposed change. Replace zero-margin with non-inferiority at a margin delta_D:
  - PASS iff D_L + t_L SE_L <= delta_D; FAIL iff D_L - t_L SE_L > delta_D; else UNRESOLVED.
  - Recommended delta_D = 5.397769910001766e-4 N, the finalist's SCREEN drag SE_eff. This is the resolution at which the constraint was decided at L1. It is recorded in the SCREEN handoff, so no OpenFOAM or FID value enters it.
  - Sanity bound: it is about 9 % of the projected OpenFOAM gain, below the cheapest known drag price (camber, ΔD/ΔDF ~0.15) and an order of magnitude below the pitch route (OpenFOAM U3: ΔD/ΔDF = 0.86).
  - Report the strict zero-margin result per level as labels (`DRAG_STRICT_{V1,V2,V3}`), keep `XV_DRAG_MESH_DEPENDENT`, and report the price ΔD/ΔDF.
  - If the review prefers a smaller margin, use delta_D = the OpenFOAM drag floor 1.3747e-4 N.
  - Record the justification text and the planning probability under strict and margin variants in the adoption record before freeze. In the registrant's model (b_K central): PASS 0.17 -> 0.21 (delta 1.37e-4) or 0.32 (delta 5.4e-4); `XV_OF_GAIN_CONFIRMED` 0.40 -> 0.49 / 0.72.
  - The minimum acceptable alternative is to keep the strict rule but adopt S2, so that a drag-only FAIL below materiality is not read as a constraint violation.

S2 [P1] Undisclosed link between XV01_FAIL and research termination; per-cause consequences missing (§8, §7.4; roadmap review 2026-10-24 §6.2/§7; #66)
- §8 says a FAIL of any cause is closed and "M4 decides". It forbids retuning, substitution, a second SCREEN round and any rule change; SCREEN §7 says the same. There is no re-registration after FAIL.
- The roadmap review §7 proposes one SCREEN re-registration after a selection-bias FAIL. It also defines research NO-GO as "XV FAIL (after one re-registration also FAIL) and B NO-GO". That document is subordinate, but the two are inconsistent and the registration does not mention the conflict.
- B is likely NO-GO: T2-0b/c/d are all NO-GO and EVAL-VALID-01 is REFERENCE_INADEQUATE.
- The registrant's own model gives P(FAIL) 0.52-0.74, most likely via drag at V3 at the 1e-4 N level. In the worst reading, a sub-materiality drag verdict on one draw could feed the termination rule. Registration §7.4 says "every outcome is informative" but does not say what each licenses.
- #66 lists acceptable M3 records as "#65 L2 or XV01_FAIL" (or #64 NO_GAIN, etc.). Registration §7.5's `XV01_NOT_FUNDED` ("M4 decides with L1") is not on that list.
- Proposed change. Add a §8.1 table, recorded before freeze, mapping cause class to what the result licenses and what M4 must not conclude:
  - FAIL with the core true (gain, drag, chain and EX all pass; see S6): fidelity or consistency only. This is not a NO-GO of the screen-and-verify approach.
  - Drag-only FAIL below materiality.
  - WL_OF (G1/G4 resolved low): selection attenuation, the approach is in doubt.
  - OF_MESH only: reference-side problem.
  - DRAG_VIOLATION above delta_D.
  - Reconcile roadmap §7 with §8 in the adoption record. Either state that no re-registration follows FAIL, or add a pre-declared conditional path.
  - Make `XV01_NOT_FUNDED` consistent with #66 (state that M4 then lacks a listed M3 record).

S3 [P2] The stated pass probability is not decision-grade (§7, `pass_probability.py`)
- The quoted 0.08-0.22 spans only the downforce shift b_K. Structural variants of the registrant's own script (b_K central) give:

| Variant | PASS | DRAG_V3 pass / fail |
| --- | --- | --- |
| Registered | 0.17 | 0.48 / 0.32 |
| Reflex drag retention x0.8 | 0.02 | 0.10 / 0.76 |
| Reflex drag retention x1.2 | 0.35 | 0.85 / 0.06 |
| Reflex drag retention x1.35 | 0.41 | 0.97 / 0.01 |
| Camber source = -19.7 only | 0.11 | 0.54 / 0.25 |
| Camber source = -11.3 only | 0.23 | 0.40 / 0.38 |

- V3 drag is a small residual of large terms: camber +2.6e-3, reflex -3.5e-3, pitch +1.1e-3, rest -3e-4, summing to about -1.3e-4 N.
- The reflex retention comes from one FID design of opposite sign (-29.3, against the finalist's +16.1 at 55 % amplitude), measured at a single V3 shift.
- tau = 0.08 versus an observed V3 drag retention spread across FID designs of about 0.55-0.92 (SD ~0.14, log-SD ~0.19).
- Data not used: U3 reflex +29.3 on V1 (drag retention 0.665, against 0.69 for -29.3), and C4 (reflex +29.3 dominant) at V3 (0.70).
- SE is treated as known (the minimum possible, floor/2), which understates UNRESOLVED.
- There is no selection effect on drag in the model.
- The V3 band is a 50/50 mixture of two camber designs, while V3/V1 rises with camber amplitude: -11.3 gives 0.92, -19.7 gives 1.52, and the finalist is at -29.55. With the -19.7 source only, V3-band pass/fail is 0.35/0.42 (b_K central).
- Proposed change. In §7 and the memo, restate as "P(PASS) roughly 0.02-0.4 under structural variants; point value not used". Add the sensitivity table and a reflex-positive variant (U3, C4). State explicitly that the funding decision does not rest on the number.

S4 [P2] Funding and staging: fund the full run set, but only after S1, S2 and S5 (§7.5, memo D1/D7)
- V3 is 149 of 164 CPU h (91 %), and GAIN_V3 passes with probability >= 0.998 in the registrant's model. V3 therefore buys only drag and consistency information on one design. That is worth 149 CPU h only if those rules are interpretable.
- Not funded: contradicts #66's dependency list and leaves L2 empty.
- V1/V2 only (about 15 CPU h): loses the finest mesh, where the camber behaviour is uncertain (FID camber V3/V1 0.92 -> 1.52). Not recommended.
- Staged (V3 only if V1/V2 show no resolved FAIL): expected saving about 0.2-0.3 x 149 = 30-45 CPU h, with no deadline and no spend. It loses the V3 measurement exactly on the FAIL branch. I agree with rejecting it (D1(d)).
- Proposed change. Record this comparison in D1/D7, and make the freeze-2 funding decision conditional on S1/S2/S5 being adopted.

S5 [P2] Two-sided V3 consistency: decision-useful as a label, a trap as a gate (§5.5, memo D5; the registrant asked)
- Same-shift FID V3/V1 ratios are 1.21, 1.10, 1.45, 1.21, 1.23, 1.07, 1.05, 0.98 (median ~1.15), and 1.45-1.52 for camber -19.7.
- A camber-dominated net with partly cancelling reflex credit projects 1.2-1.9, so the upper side is more likely binding than not.
- A larger finest-mesh gain cannot contradict "improvement". G3 already tests V1-V2 two-sided on this finalist, and the FID set slope passed at 1.086.
- A point ratio in (1.67, ~1.95) is `UNRESOLVED_STAT`: it blocks PASS, and re-registration cannot change that point estimate. With the registered SE(hi) from four common pairs (about 8e-4 N), a resolved FAIL needs a ratio of about 1.95.
- Proposed change.
  - Keep the lower side outcome-bearing: V3 collapsing below 0.6 x V1 stays FAIL or blocks PASS.
  - Demote the upper side to a registered label `V3_UPPER_EXCEEDS`, with the ratio reported and read through the S2 map.
  - Keep G3 two-sided.
  - Record it as a claim-based decision in the adoption record. Effect in the registrant's model: PASS 0.17 -> 0.23 with the registered drag rule; with S1 and S5 together 0.44.
  - The remaining FAIL (0.28) and UNRESOLVED (0.27) come from G3, G4, the V3 lower side and gain V2, so the gate stays demanding.
  - Optionally, if the upper arm is kept, use the 16-pair V1 mean in the margin SE (SE_V1 ~2.5e-4) instead of only the four common pairs.

S6 [P2] What tests the claim, the label ladder, and `XV_OF_GAIN_CONFIRMED` (§5.4, §5.9)
- Tests "improvement confirmed by independent CFD": GAIN on all levels, DRAG, NC and determinism, and EX. EX asks whether the OpenFOAM force is an artefact of the new shape's STL export; I would keep it in the core.
- Tests WaterLily-to-OpenFOAM transfer fidelity instead: G3, G4, V3 consistency.
- Redundant: G1 and G2 are implied by GAIN. GAIN PASS gives Delta >= x > 0 and Delta_V1 > 3 SE_V1, and G1 FAIL implies GAIN FAIL. G5a is a P0 precondition. G5b is declared "not tested".
- G4's upper arm (resolved rho > 2) and the V3 upper arm penalise better-than-WaterLily results.
- `XV_OF_GAIN_CONFIRMED` already includes drag and NC, so the name oversells "gain". As primary it would be looser than PASS (it drops G3, G4, V3 consistency), and it would still be dominated by the V3 drag rule: 0.40 in the model.
- Proposed change.
  - Keep `XV01_PASS` as the full conjunction, after S1 and S5.
  - Rename the secondary label (for example `XV_OF_CORE`), add EX to it, and print it with the outcome.
  - Drop G1 and G2 from the conjunction, keeping them as reported values and for cause attribution.
  - Treat the G4 upper arm as a label, or document why it blocks.

S7 [P2] M4 will want data that the run set does not provide cheaply (§3.3, §5.8, §5.10)
- §5.10 says the component retentions are "not identifiable from one design". Cheap additions, descriptive only and with no outcome effect:
  - (a) Component states at the finalist's amplitudes (camber -29.55 alone, reflex +16.115 alone, pitch +0.155 alone):
    - V1 at 16 pairs: 3 x 32 cases x 106 s = 2.8 CPU h.
    - V2 at 4 pairs: 24 cases x 1,713 s = 11.4 CPU h.
    - Optional V3, one mirror pair of camber-only and reflex-only: 4 x 9.3 = 37 CPU h.
    - V1+V2 is about 14 CPU h (9 % of the formal estimate). With the V3 pair, raise the cap from 250 to about 300.
  - (b) A V1 panel of SCREEN states that already carry WaterLily flow_32 values (axial, D-optimal, proposals, random-control members):
    - Cost about 0.94 CPU h per state at 16 pairs, so about 18 CPU h for 19 states or about 9 CPU h at 8 pairs.
    - It gives an OpenFOAM-versus-WaterLily regression for optimizer-type camber-extension designs (sigma_disc, mode-wise drag retention, and drag-cushion calibration for M4/M5). This is the highest information per CPU h available, because the single finalist is one point.
  - (c) Finalist vs M and vs R-best already exist. Pre-register a power note: WaterLily advantages 3.1e-3 and 4.9e-3 N, so expected OpenFOAM advantages of about 2.0e-3 and 3.2e-3 N against a pair-difference SE of about 2-3e-4 N. These are the only evidence on optimizer value, since the hand design M also clears g_min in WaterLily (+7.7e-3 N).
- Add all of them to the blinding clause (§4.7).

S8 [P2] The single re-registration and the UNRESOLVED dead end (§8, memo D8)
- UNRESOLVED_STAT on V3 drag or V3 consistency (P ~0.18-0.26) cannot be repaired by "same finalist, rules no weaker, no pooling, dof 3". A V3 point ratio above 1.67 stays above it. Halving the V3 SE needs about 4x the pairs (~600 CPU h).
- Proposed change. Choose one of two:
  - (i) A pre-specified conditional V3 stage. Trigger: the only non-PASS rules are `UNRESOLVED_STAT` on V3 and there is no point violation. Action: four more V3 pairs (85-88, about +149 CPU h, cap raised accordingly), same rules at 8 pairs. The expected extra cost is about 30 CPU h. FID had a registered extension; D8's "result-guided" objection applies to ad hoc additions, not to a pre-specified sequential rule.
  - (ii) State plainly that V3 UNRESOLVED is terminal and goes to M4 through the S2 map. Either way, list which UNRESOLVED causes the one re-registration can actually change.

S9 [P3] Minor
- The `endTime` 12000 contingency (§4.6) likely pushes V3 to about 270-390 CPU h, above the 250 CPU h cap. By §4.4 that would stop the pushes and give `XV01_INCOMPLETE` (BUDGET). Say at freeze 2 how the cap follows the probe record.
- G5b: |Delta_drag,32| = 1.9939e-3 N is 0.3 % below the 2e-3 eligibility, while the flow_48 drag of -2.79e-3 N would be eligible. Keep "not tested", and report the flow_48-based eligibility and the drag retention.

Verdict: GO_AFTER_FIXES. The experiment is the right next one. The registration is carefully built and mechanically fail-closed, and the gain test is not at risk (gain passes with probability >= 0.94 on every level except V2 under the upper b_K bias). What must change before freeze is the drag test and the meaning of non-PASS. Specifically:
- Replace the zero-margin resolved drag test, which cannot be decided at about 7e-5 N SE and fails at 0.05 % of drag, with a non-inferiority margin tied to the resolution at which the constraint was decided (S1).
- Record per-cause consequences, and reconcile with the roadmap's termination row, so a sub-materiality drag verdict on one draw cannot silently feed the research NO-GO rule (S2).
- Demote the upper V3 arm (S5). Restate the probability as a structural range (S3), clean up the label ladder (S6), add the cheap identification controls that make a FAIL informative (S7), and clarify what re-registration can change (S8).
None of this lowers the gain, chain, extraction or lower-side fidelity requirements. With S1 and S5 adopted the registrant's model still gives PASS about 0.44, FAIL about 0.28 and UNRESOLVED about 0.27, so the gate remains demanding and a PASS would still be a real L2 statement. Fund the full run set at freeze 2, conditional on these fixes.
