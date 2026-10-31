# XV-01 (#65) registration — decision memo, revision 0 (2026-10-31)

Companion to `docs/xv01_registration_2026_10_31.md` (revision 0, `DRAFT_FOR_PLAN_REVIEW`). Each decision gives the alternatives, the choice, the reason and the residual risk. Nothing here is a new measurement; no OpenFOAM force of the finalist exists. Decision-maker: the registrant under the 2026-10-13 delegation; every choice goes through the one PROC-01 plan review and the source review before freeze.

## D1. What XV verifies, and with which run set
**Alternatives.** (a) the preparation note's option A (V1 16 pairs, V2/V3 2 pairs each; 80 cases); (b) option A′ (V1 16, V2/V3 4 pairs each; 96 cases); (c) A′ plus V3 at more pairs; (d) a staged design (V1/V2 first, V3 only if V1/V2 do not already decide FAIL).
**Choice: (b), plus cheap V1 controls.** A gives dof 1 on V2 and V3 (t_0.95 = 6.31), which makes the per-level SE and the V3 consistency rule almost uninformative. A′ gives dof 3 at about 149 CPU h of V3 (16 cases x 9.3 h); a fifth or sixth V3 pair adds 37-75 CPU h for t 2.13-2.02 instead of 2.35. (d) saves about 0.25 x 149 CPU h in expectation (§7 of the registration: a resolved FAIL on V1/V2 has a probability of roughly 0.15-0.4) but adds an interim written-once analysis, delays V3 and, on a V1/V2 FAIL, leaves the V3 camber drag and consistency behaviour unmeasured, which is the information M4 most needs (D7). The V1 controls (NC, W4 reference, M, R-best, r = 4 EX; 192 cases, about 6 CPU h) are cheap and answer chain, extraction and comparison questions.
**Residual risk.** dof 3 on V2/V3: a true value near a threshold stays `UNRESOLVED` more often than with more pairs; disclosed.

## D2. Single-finalist uncertainty (requirements §2.1)
**Alternatives.** (a) copy FID's V2 pooled SD and the V3 leave-one-out regression residual (1.45e-3 N); (b) own pair ensembles per level with no floor; (c) own ensembles with a floor from an OpenFOAM-internal placement SD; (d) a calibration/prediction term (WaterLily-to-OpenFOAM discrepancy) inside the SE.
**Choice: (c)**, floor = the FID V2 pooled pair SD (downforce 1.98e-4 N, drag 1.37e-4 N, dof 12) on V2 and V3; V1 unchanged from FID (own 16 pairs, no floor). (a) is excluded by the requirements note and the FID handoff (the regression residual mixes placement noise with design-to-design grid departure). (b) can produce a spuriously small SE from 4 units of a deterministic solver. (d) mixes a prediction uncertainty into a measurement rule; the discrepancy belongs to the planning projection (§7), not to the decision SE.
**Residual risk.** The floor is a within-design V2 quantity applied to V3; if V3 placement noise is larger, the own SD governs; if smaller, the floor is conservative. The Halton panel is not an iid sample (registration §5.1).

## D3. Normalisation of the OpenFOAM floor
**Alternatives.** (a) `Delta_L / J_b,48` (the SCREEN normaliser, the §5.7 basis); (b) `Delta_L / |F_parent,L|` (OpenFOAM's own parent, the `S_d,OF` denominator); (c) `max` of the two.
**Choice: (c)**, expressed as an absolute floor `x_OF,L = g_OF max(J_b,48, |F_parent,L|)`; with the visible FID parent forces (0.20-0.21 N) it equals (a), 3.369e-3 N. FID §8 does not state the normaliser of the XV floor; `g_OF` mixes a WaterLily-normalised term (`S_d`) and an OpenFOAM-normalised term (`S_d,OF`). (c) follows M2's `S_d` precedent `max(|J_b,48|, J_scale)`, is the basis of SCREEN's §5.7 projection, and is the stricter reading by 1.25-1.32x. (b) would lower the floor in N to 2.56e-3 N (V1) after the parent forces were visible: rejected as the looser choice.
**Residual risk.** None for the outcome at the projected values (the gain floor passes with probability >= 0.94 on every level except V2 under the upper bias); the relative gain on OpenFOAM's own scale is reported.

## D4. Drag constraint on the OpenFOAM arm
**Alternatives.** (a) SCREEN's point sign `D <= 0`; (b) resolved non-increase on V1 only (FID's G5 level); (c) resolved non-increase on every level, any resolved violation a FAIL, otherwise UNRESOLVED; (d) a drag allowance.
**Choice: (c).** The requirements note asks for re-evaluation "with propagated uncertainty" and maps only resolved violations to FAIL and anything unresolved out of PASS; the claim is that the constraint holds on independent CFD, and a sign that depends on the mesh is not a confirmed constraint. (a) and (b) would raise the pass probability (§7: the V3 drag is the binding rule) and are rejected for that reason after the FID drag values were visible. (d) has no registered value (SCREEN D1).
**Residual risk.** The V3 drag projects at about -1e-4 N (a coin flip): the most likely `XV01_FAIL` cause. It is the measurement M4 needs (D7).

## D5. V3 consistency for one finalist
**Alternatives.** (a) drop the set rule (no set); (b) a one-sided rule (only V3 below 0.6 V1 fails, V3 above 1.67 V1 is a label); (c) two-sided per-design margins on common pairs, point-pass and resolved-fail (the FID G3-set form for one design); (d) require the whole interval inside the band.
**Choice: (c).** (a) is a silent drop of V3 (requirements §2.2 forbids). (b) is attractive for the gain claim (a larger V3 gain does not threaten the improvement) but loosens the FID two-sided band, which tests that the OpenFOAM difference is mesh-robust in magnitude; the gain floor alone does not test that. (d) is stricter than the FID point-pass and would leave most outcomes UNRESOLVED at dof 3. The margins on common pairs avoid ratio instability and use the pairing across levels (preparation note).
**Residual risk.** The camber-dominated finalist projects V3/V1 of about 1.2-1.8 (FID camber -19.7: 1.52); P(FAIL) about 0.2, mostly on the upper side. The plan review is asked whether the upper side should be outcome-relevant.

## D6. EX, REF, M and R-best
EX is included for the finalist because #65 lists the STL extraction control in scope and FID's insensitivity was shown for two other shapes; FID's values (6e-6 N against 8e-4 N tolerances) make it a cheap, likely-passing check. REF (W4) reproduces a known design difference at new shifts as a chain check of the shape path (the NC is a translation and does not exercise the shape export). M and R-best are descriptive: whether the optimizer's WaterLily advantage over the hand design (+3.1e-3 N) and the best random member (+4.9e-3 N) survives on V1; both also add OpenFOAM retentions of camber-heavy designs with WaterLily confirmation values. None changes the outcome.

## D7. Funding on a low stated pass probability
**Alternatives.** (a) fund the full run set; (b) do not fund (XV01_NOT_FUNDED, M4 decides with L1 only); (c) fund a reduced set (V1/V2 only); (d) loosen rules to raise the probability.
**Proposed: (a), decided at freeze 2.** The composed-gate pass probability projects at about 0.2 (0.08-0.22); §5.7 alone suggested 0.80-1.00 because it projects only the V1 gain. The cost is local CPU (about 164 CPU h, about two days of wall), no spending. The non-PASS outcomes are not wasted: the drag and V3 measurements of a camber-extension design whose WaterLily drag neutrality is a cancellation answer M4's constraint-transfer and extension-fidelity questions, which no other registered study answers. (c) would not measure V3, where the risk and the information are. (d) is rejected (D3-D5).
**Residual risk.** Two days of the shared host; a FAIL is the more likely outcome and must be reported as a decision, not tuned.

## D8. No extension round, one re-registration at most
FID had a registered extension for `UNRESOLVED_STAT`; SCREEN had none. XV has one fixed run set: an unresolved rule is `XV01_UNRESOLVED`, and at most one re-registration (fresh Halton >= 101, no pooling, rules no weaker, same finalist) follows only an explicit recorded decision. Reason: an automatic extension guided by which rule is unresolved is a result-guided addition; dof 3 was chosen up front (D1).

## D9. What is not done
No WaterLily case (SCREEN owns that arm). No other SCREEN candidate verified in place of the finalist. No OpenFOAM mesh beyond V1/V2/V3, no GCI or grid-convergence claim. No high-Re, no FSAE, no flag change.
