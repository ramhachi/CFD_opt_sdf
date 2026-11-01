# Strategy review: RE-01 plan, rev 0 (docs/re01_plan_2026_11_01.md)

Reviewer role: adversarial STRATEGY reviewer. Read-only. Date 2026-11-01.

Read: the plan; `fable_analysis.md` and `re_ladder.py`; `docs/STATE.md`; `docs/roadmap_review_2026_10_24.md` (§0, §3, §4.7, §5.8, §6, §7); `docs/roadmap_review_2026_10_16.md` (§4-§9); `docs/t20_summary_for_m4_2026_10_22.md`; issue #66 (body and comment); `docs/xv01_registration_requirements_2026_10_22.md`; `docs/evidence/screen01_2026_10_30/analysis.md`; `docs/evidence/fid01_2026_10_21/analysis.md` (tier-A table); T2-0c/d registrations (morph definitions).

Web checks done in this review (what is and is not verified is listed in Appendix B).

---

## 0. Bottom line

The plan is honest about its ceiling and has good parts (Stage 0 as exploratory, R1 with a body-fitted cross-check, hypotheses labelled as hypotheses, a written claim ceiling, XV-01 resource conflict handled). But as a strategy it is mis-sized and mis-framed:

1. It does not answer the question the user asked (what happens at the FSAE Re). It answers a smaller one (how far a Re-80 plate result carries up to Re_c 3.8e3 in WaterLily iLES) and the user only learns this in point 2 of the summary.
2. About 80 % of the GPU budget (R2 + R3 = 50 of about 62 GPU h) buys rungs that, by the plan's own numbers, cannot produce PASS or BREAK for the finalist unless retention is about 1.0. The most likely overall label is `RE_UNRESOLVED`.
3. Four of the five rows in the §9 reading table lead to the same next step the project already chose on 2026-10-24 (option A mandatory, option B attached-regime). The one row that changes a decision has a low prior and is justified on physics alone, without the ladder.
4. It is the largest GPU study in the project (about 3.5x SCREEN-01's 17.2 GPU h, cap 5.2x) and it is off the critical path (XV-01 -> M4 -> B -> L3), while B's long-lead items stay at "paper only".

Verdict: **GO_AFTER_FIXES**. Stage 0 and R1 survive almost unchanged. R2/R3 as designed should not be registered. The framing, the estimand, the M4 coupling and the governance weight need to change (S1-S8).

---

## 1. Findings

### S1 (P1): RE-01 does not reach the FSAE Re, and the plan frames the gap too softly

Evidence:
- Re coverage (Re_c, chord basis): Re 80 case is Re_c 122; the ladder tops out at Re_c 3,810; FSAE is about 5e5. That is 1.5 decades covered of 3.6, and the uncovered 2.1 decades (3.8e3 to 5e5) contain every regime change that matters: laminar separation bubble, transition, turbulent attached flow. Roberts, Finnis & Knowles (J. Fluids Eng. 139, 2017; abstract checked) report that a single-element inverted wing changes downforce by up to 320 % and drag by 35 % over a chord-Re difference of only 0.81e5, with the effect driven by the laminar separation bubble and trip position. No rung of RE-01 can see that mechanism.
- The plan states this in §0.2 and §1, but the title and §0.1 sell it as "check what happens when Re is raised". The user's request ("it would be good to check what happens when Re is raised") will be read as covering high Re.
- The plan never says what the project already knows at high Re: T2-0 gives 2D, Re_c 4.6e5, attached-regime (h/c 0.224) morph responses for incidence, camber and flap that passed every gate (T2-0c; descriptive only; `docs/t20_summary_for_m4_2026_10_22.md` §2). That is the only data in the repository that touches the user's question, and the plan omits it.

On "v18 is a stalled bluff body above Re 1e3, so do not go there": the physics is plausible (9.4 % thick, alpha 20.4 deg, blunt rounded TE; thick symmetric sections stall at roughly 14-18 deg at Re_c 5e5; Ananda et al. 2015 flat plates stall near 10 deg at Re 6e4-1.6e5). It is a reasonable reason not to run steady RANS on v18. But three things make it more of an excuse than a finding:
- It is an untested hypothesis. Fable's regime table (§2.2) is literature inference, and the plan itself says so (§3.1). No run in the project looks at separation on v18 above Re 80. Stage 0 should record wall-shear sign and pressure distributions, not only forces.
- It is used asymmetrically: stalled, therefore skip Re >= 1e4 (S1), yet the ladder is still said to inform M4 (§0.6, §9). If v18 is a bluff body at Re >= 1e4, the ladder up to 2500 is a statement about a laminar-to-transitional wake that will not exist at 5e5.
- It cuts the other way too. For bluff, separation-dominated flows, force coefficients tend to saturate with Re (flat-plate and sharp-edged bluff-body data, Hoerner-type; from memory, not verified here), which is the case where lower-Re LES extrapolates best. v18 has a 57 mm leading-edge radius (r/c 4.7 %), so leading-edge separation may stay Re-dependent; nobody knows. The item that probes this (R4, flow_96, Re_L 8000, parent and finalist) is the one closest to the user's question, and the plan puts it last and optional.

Alternative:
- Retitle and reframe: "How far does a Re-80 result carry in our own tools (Re_c <= 3.8e3), and what is the cost of unsteady statistics". Open §0 with a coverage statement (below, §6).
- Add a short "what we already know at Re_c 4.6e5" paragraph pointing to T2-0.
- Add separation diagnostics (wall-shear sign change, Cp on both surfaces, mean wake) to Stage 0 so that "stalled" becomes a measurement.
- Promote one R4-like probe (parent plus finalist, flow_96 or flow_64, descriptive, 2 phases) ahead of R3, or state why it is not.

### S2 (P1): R2/R3 cannot deliver PASS or BREAK by the plan's own numbers; the instrument resolution is below the signal

Quantities (re-derived; script in my scratch calc, formulas as in Fable §3.3):
- Finalist gain at Re 80: 4.05 % of the parent force. Stop rule (§3.4): SE_T <= 1.9 % of the parent force for parent and design. With P = 4 phases and decorrelated trajectories, SE_eff = sqrt(2) SE_T / sqrt(P) = 1.34 %, so 3 SE_eff = 4.0 %.
- RUNG_PASS condition 1 needs finalist |Delta| >= 3 SE_eff, i.e. about 4.0 %, i.e. retention about 1.00. The plan's own hypothesis H_mech (Fable §2.3) is retention 0.3-1.0 at Re_L 250/800 and weaker at 2500. At retention 0.5 you need SE_T <= 0.95 %; at 0.3, SE_T <= 0.57 %.
- What window does that take? With the plan's assumed lift rms of 10 % of the mean and tau_int of about one period (3.9 CU): SE_T 1.9 % needs 216 CU; 0.95 % needs 860 CU (at the cap); 0.57 % needs 2,200 CU (2.7x the cap). With rms 20 % (also plausible for a stalled plate), 1.9 % already needs 864 CU. The rms assumption is unmeasured (Fable §7).
- Tier-A differences are only >= 5.363e-3 N, i.e. >= 2.0 % of the 0.266 N parent (FID-01 definition), so most of them are below 3 SE_eff at a chaotic rung too. Condition 2 and tau both become noise-dominated.
- The stop rule is set for retention = 1, not for the hypothesised 0.3-1.0. That is an internal inconsistency in the plan.

Independent-check gap:
- arXiv 2508.09590 (Zurman-Nasution, Weymouth, Ganapathisubramani; abstract and HTML checked): a BDIM wall-resolved iLES of a flapping foil used 700, 5000 and 8555 cells per chord at Re_c 1e4, 1e5, 1e6 (3D, narrow spans). Fitting a power law through the first two (exponent 0.85) gives roughly 43, 116 and 307 cells per chord at R1, R2, R3 (extrapolation, rough). Available: 49 / 73 / 98 / 146 for flow_32/48/64/96. So R1 is at the wall-resolved standard on every grid, R2 is under by about 1.6x (flow_48) to 2.4x (flow_32), and R3 is under by 2x to 6x on every grid.
- The plan's gate for resolution is flow_32 versus flow_48 sign agreement. Two grids that are both under-resolved in the same way can agree and both be wrong. At R2 there is only a descriptive pimpleFoam; at R3 there is nothing independent. So BREAK and PASS at R2/R3 would be WaterLily-versus-WaterLily statements about an under-resolved iLES.

Consequence (my judgement, not a registered probability): R1 is likely resolved. R2 and R3 most likely return `UNRESOLVED_STAT` or `RESOLUTION_LIMITED`, giving overall `RE_UNRESOLVED`. §9 maps that to "give numbers to B6 and #69", which is no decision. The study spends about 80 % of its GPU on the rungs least likely to resolve.

Alternative:
- Make R2/R3 conditional on a Stage 0 power gate, written before any design force is read: proceed with a rung only if, from the measured rms and tau_int of the parent (4 phases, not 1), SE_T <= 0.6 % of the parent force is reachable within 400 CU (otherwise the rung is not registered or is run as a descriptive 2-state probe).
- Replace R2/R3 by a statistics probe (parent, finalist, hand design M; 4 phases; flow_32 with adaptive window; flow_48 for 2 states by 2 phases) at Re_L 800 and 2500: about 8-12 GPU h. It delivers what the plan says is the real prize (sigma_d, the CRN ratio, rms, tau_int, the window needed), plus the sign of the finalist as a descriptive outcome.
- If the design-persistence question at R2/R3 is kept, change the estimand (S5).

### S3 (P1): The ladder's decision value is low, and the §9 table shows it

Row-by-row, what changes?
| RE-01 outcome | §9 reading | Does the next step change? |
| --- | --- | --- |
| `RE_PERSISTS` | supports L2.5 in B5, strengthens option A; "option B still needs an attached evaluator and data" | No. Option A (mandatory) and B (conditional) proceed as on 2026-10-24. A footnote in the paper. Prior: very low (PASS essentially needs retention 1 at R2/R3, S2). |
| `RE_BREAKS_AT_1/2` | Re-80 gain is a low-Re effect; consider replacing the demo problem with an attached parent before investing in B | Yes, it is the only row that moves a decision. Prior for R1: the plan itself calls it "surprising". At R2: needs a resolved reversal of at least about 4 % on under-resolved WL-only evidence (S2, S4). |
| `RE_BREAKS_AT_3` only | supports constraining B to the attached regime | No. That is the 2026-10-24 recommendation already (roadmap review §6.2 B(i)). |
| `RE_UNRESOLVED` | numbers to B6 and #69 | No. |
| `INCOMPLETE` | nothing | No. |

My prior over outcomes (judgement): `RE_UNRESOLVED` most likely, then `RE_BREAKS_AT_2/3` (mostly via the tau label, S4), `RE_BREAKS_AT_1` and `RE_PERSISTS` rare. The table is honest in its text (it does not oversell), but it exposes that the ladder cannot change B, which is the path to the target. The only live decision ("replace the demo with an attached parent") follows from physics alone: v18's alpha 20.4 deg and thickness were inherited from the legacy v17 body (genesis bisects thickness to match the v17 smoothed volume, and the incidence is v17's principal axis, 21.07 deg to 20.395 deg; `docs/v18_mode01_plan_2026_10_19.md` lines 35 and 50), not chosen as an FSAE operating point, and the optimum shape is known to depend on Re. Literature: Srinath & Mittal (2009) find low-Re optimal airfoils "very sensitive to Re"; Srinath, Mittal & Manek (2009) find multi-point shapes significantly different from single-point ones; Zhdanko & Kolomenskiy (arXiv 2605.19468, abstract checked) find optimal alpha decreases monotonically with Re and optimal camber peaks near Re 40-50 and then declines (steady laminar solver, Re 1-3000).

Coupling inconsistency: §7 says RE-01 is "not a prerequisite for M4, but an input", yet the same paragraph says M4 decides "after XV-01 and R1 (or the whole) judgement". An input that M4 waits for is a prerequisite. With R2/R3 in the loop this delays M4 and B by 3-5 weeks.

Alternative:
- Cut RE-01 to Stage 0, R1 and the statistics probe (about 20-30 GPU h, 50-65 CPU h).
- Pre-commit in the plan that M4 does not wait for R2/R3 and uses R1 and the probe if available at the time of the XV-01 result.
- The "replace demo problem" decision should be made on a priori grounds plus the cheap parent-selection scan (S8), not conditional on a 60-90 GPU h ladder.

### S4 (P2; P1 if R2/R3 survive as written): the decision-bearing BREAK label can fire from noise or from under-resolved WL-only evidence

- RUNG_BREAK includes "or tau < 0.3". Kendall tau between Re-80 Delta and rung Delta over 10 designs has no resolution condition. At a rung where most designs are below 3 SE_eff (S2), tau shrinks toward 0 from noise alone, so `RE_BREAKS_AT_k` can be produced by an under-powered rung. That is the label that triggers "replace the demo problem". The permutation p-value does not fix this (it tests tau against zero, not against the tau expected under the measured noise).
- BREAK at R2/R3 also needs only WL agreement on two under-resolved grids (S2). PASS and BREAK are treated symmetrically, but only the BREAK drives a decision.
- Floors: the plan replaces the Re-80 floor by the roll control's sigma_d per rung. That is 4 phase differences of a single design (df = 3), so the floor can be off by a factor of several in either direction; if it is low by chance the rung looks better resolved than it is. Pooled sigma_d over all designs (df about 36) is the natural estimator when it is dominated by time-averaging noise, and is what estimator B predicts.

Alternative:
- Compute tau only on designs that are resolved at the rung, and compare it with the tau expected from a Monte Carlo draw `Delta_new ~ N(r Delta_80, SE_eff^2)` using the measured SE_eff (report "tau_obs versus tau_expected(r = 1)").
- A BREAK label at R2/R3 additionally requires concurrence from flow_64 (or an independent solver) for the finalist; otherwise it is `RESOLUTION_LIMITED`.
- Use pooled sigma_d for the floor; report the roll control as a check on it.

### S5 (P2): The estimand tests a 4 % selected effect that sits at the instrument's noise; test the mechanism at high SNR instead

- The finalist is the maximum of K = 19 candidates chosen at Re 80 (selection bias b_K 0.10-0.27 % of J, `analysis.md`) and its gain is 4.05 %. Persistence of a small, selected effect is the weakest possible test of "does the mode response carry over".
- What the user, M4 and the spectral argument (roadmap review §5.8) care about is whether the wide-mode slopes (pitch, camber, reflex) keep sign and rough size as Re rises. A 3-5x larger amplitude on the same wide modes raises the signal above 12-20 %, well above chaotic-rung noise of 3-4 %, and slope sign is what matters for a proposer.
- The plan forbids new shapes ("phi bytes are all registered, no new shapes") for provenance. That trades power for provenance in exactly the rungs where power is missing. Re-80 anchor values for the 12 states come from two different studies on different phase sets (SCREEN 13-16, FID 7-10), which also makes retention a ratio of two independently noisy estimates.
- The plan's R1 retention band [0.3, 3.0] for OpenFOAM is very wide (a tripling passes).

Alternative:
- Make the RE-01 estimand "sign and size of the five wide-mode slopes at high-SNR amplitudes (+/- A*, possibly 3-4x the SCREEN amplitude) at each Re", with the finalist and M as secondary. The new phi files are mode amplitudes already defined by the analytic modes; registration of new amplitudes is a small step.
- Add the Re-80 anchor at the same phases for the 12 states (about 6 GPU h, flow_32) if retention is kept; otherwise report the Re-80 value from the registered estimate with its own SE.

### S6 (P2): Procedure overhead is not proportionate to a descriptive question

Numbers that show the overhead scale:
- `docs/phase_plan.md` is 7,729 lines; `docs/` has 96 entries; `docs/evidence/` has 763 directories; 1,138 commits since 2026-09-01 (202 since 10-16, the re-baseline).
- Since 10-16 the project ran about 12 studies in 15 days (HARNESS, JOB-02, MODE-01, UNC-01, T2-0b/c/d, FID-01, GEOM-03, WIDTH-RULE, LOCAL-OF-01, SCREEN-01). Registered outcomes in that period that were NO-GO: T2-0b, T2-0c, T2-0d, GEOM-03. The procedure was worth it where the result decided something; each of those NO-GOs did redirect M4.
- RE-01 is five procedural stages (Stage 0, registration with a three-angle review, analyzer plus independent checker plus source review, freeze 1 -> smoke -> freeze 2 -> R1 -> judge -> freeze -> R2/R3 -> analysis written once) for a study whose output is "input to M4 framing". Estimated calendar 3-5 weeks (1-2 weeks of registration and review, 2-3 weeks of quota-limited execution), i.e. about 2-3 times the longest study so far.
- The 2026-10-16 two-layer rule exists so that only studies that claim a verdict are registered. RE-01's claim ceiling says it makes no qualification claim (not an evaluator GO, not FSAE, not Re >= 1e4). Its verdict labels are decision aids for M4.

Alternative:
- Run Stage 0 and the statistics probe as `EXPLORATORY_COMMITTED` with a pre-committed interpretation memo (the claim ceiling and the reading table written before the first run, which is all that the plan's "reading drift" risk needs).
- Register only R1 (steady, well-powered, with an OpenFOAM cross-check), and only if Stage 0 shows the flow is steady.
- Register anything above R1 only if the Stage 0 probe shows it is resolvable and its outcome would change a decision.

### S7 (P2): Sequencing and opportunity cost

- The baseline is not yet independent. XV-01 (registration in progress on `exp/xv01-registration-2026-10-31`) verifies the finalist at Re 80. If it fails (XV margin: central 2.40 % vs 1.27 % floor, pessimistic 1.74 %, so a pass is likely but not certain), the RE-01 retention numbers are relative to an unverified Re-80 gain. The plan has no branch for XV-01 FAIL.
- Compute: R1 WaterLily and Stage 0 do not conflict with XV-01 (no GPU use). R1's OpenFOAM (50-65 CPU h) waits for XV-01's 128+ CPU h on the same 4-core Docker; fine. The risk is the Kaggle quota: STATE has 30 GPU h per week (not an official figure, Fable §7) and the GPU slots are shared with other sessions. 60 GPU h typical is two full weeks of exclusive quota; the stated cap (90) is below the plan's own worst case (125), so `INCOMPLETE` is not a remote outcome.
- "Idle GPU quota" is not a value argument. Unused quota is not a cost to be recouped; the same hours buy (i)/(iii) (S8).
- Off-path: STATE.md says "#23 remains the sole off-path research issue; #28, #20, #53 retain parked conditions". RE-01 is a second off-path item, and by the plan's own admission (§1, §7) it is not on the critical path XV-01 -> M4 -> B -> L3-01.

Alternative:
- Run Stage 0 now (3 GPU h, no dependency). Register R1 in parallel with XV-01 but start R1 forces only after the XV-01 outcome is known or within the same week (R1 WL is cheap).
- Gate R2/R3 on both XV-01 (PASS) and the Stage 0 power gate.
- Spend the first free GPU hours on the parent-selection scan for the attached demo (S8) rather than R2/R3.

### S8 (P2): Alternatives (i) and (iii) were dismissed or deferred too fast; their cheapest first steps are available now

The plan puts the attached-regime parent ("L2.5") in a B5 draft (§6.1) and executes nothing. Two cheap steps exist now:

(a) Parent-selection scan for an attached demo problem (alternative (i), first step). Scan alpha 2-10 deg, camber 2-6 %, h/c 0.2-0.4 at Re_c about 3e3 on flow_32/48 (Zhdanko and Kolomenskiy's optimum at Re 3000 is about 4 % camber at alpha 6.4 deg, i.e. an attached-regime wing, so the target regime exists at WaterLily-reachable Re). Needs a section thick enough for the grid: at flow_48 (73 cells per chord) t/c of 8-12 % gives 6-9 cells across the thickness (FSAE main elements are 10-12 % thick, so this is not a toy restriction); t/c of 3-4 % would give 2-3 cells, which is below what the BDIM kernel and the project's own R0 occupancy lesson (GEOM-03) tolerate. Cost: about 5-10 GPU h, 1 week. Output: a parent where the flow is steady or periodic and the five mode responses are resolvable, or a clean "no".

(b) Same-mode cross-Re comparison on a 2D section (alternative (iii)). T2-0c already ran pitch, camber (parabolic, "inverted camber") and trailing-edge flap morphs on the Tyrrell 026 section at Re_c 4.6e5, h/c 0.224, with every gate passing and fine30 costing about 0.6 minutes per case. Those are the same three mode types as v18's pitch, camber and reflex. A descriptive run of the same morphs at Re_c 1e3-1e4 (laminar body-fitted; WaterLily 2D) gives the sign and size of the three slopes across 1.5 decades on an attached section, which is exactly the contract option B proposes (slopes, not absolute Cl). It needs a 2D case contract, comparable in size to the Re-parameter contract RE-01 already requires, and wall-resolved meshes at low Re (new but small). Cost estimate (mine, not measured): 10-30 GPU plus CPU hours, mostly engineering. It reads on option B's central risk (do low-Re iLES slopes predict high-Re RANS slopes?) which RE-01 cannot.

Alternatives compared (all estimates are mine unless marked; calendar assumes the 30 GPU h/week quota and the current review procedure):

| Option | Cost (GPU h / CPU h / calendar) | What it measures | Decision it can change | Verdict |
| --- | --- | --- | --- | --- |
| RE-01 as planned | about 62 (cap 90, worst 125) / about 100 / 3-5 wk | design persistence Re 80 to 3,810, WL-only above R1, on a presumably stalled plate | at most one of five rows, low prior | resize (S2, S3) |
| RE-01-lite (recommended) | about 20-30 / 50-65 / about 2 wk | steady-regime robustness of the WL-OF chain at 3x Re; unsteady-statistics contract; parent regime map | framing of L1/L2; whether R2/R3 are affordable | do |
| (i) attached demo problem | scan 5-10 GPU h / 1 wk; full chain (UNC, FID, SCREEN, XV equivalents, scaled from 17 GPU h SCREEN, 13 GPU h FID WL, 128+ CPU h XV) about 40-50 GPU + 150-300 CPU / 4-6 wk | first L1/L2 on physics near the target | the relevance of L1/L2 | start the scan now; commit to the chain after XV-01 and M4 |
| (ii) one 3D RANS/URANS pair at Re 5e5, v18 | the plan's own steady estimate 27-72 CPU h per case, so about 55-145 for a pair; URANS about 10x; competes with XV-01's CPU | the sign of one difference, one realisation, one model | none | no; at most one parent-only run if "stalled" must be tested (S1) |
| (iii) 2D section study across Re | about 10-30 / minutes per case / 1-2 wk | Re-robustness of pitch, camber and TE-flap slopes on an attached section; WL as proposer for B | B5 slope contract; L2.5 | best value per hour among high-Re-relevant options; do after Stage 0 |
| (iv) skip the ladder, go to M4 B | 0 GPU for prep; B's evaluator work is CPU (Kaggle, 5 sessions) | B feasibility | the path to L3 | do the prep now and make it the lead line; the ladder shrinks to lite |
| (v) wait for XV-01 | 0 GPU; 1-2 wk calendar that registration needs anyway | removes the unverified-baseline problem | none | adopt for R2/R3 only; no need for Stage 0, R1 WL or registration |

Why (ii) is the weakest: the finalist's expected difference at 5e5 is 1.2-4 % (retention 0.3-1 of 4.05 %) against realisation noise of 0.2-0.9 % of Cl in the 2D T2-0 meshes (3D snappy meshes are untested and likely worse), a model spread of at least 33 % between SA and SST on incidence derivatives (T2-0b G4), no reference data for this body, and a local pipeline that is only qualified for U3/X3 (LOCAL-OF-01; gmsh meshes differ across platforms). Its only defensible use is a parent-only regime check.

### S9 (P2): The "unsteady-statistics contract" is the main stated prize and it is narrower than claimed

- §2 reason 3 and §0.6 say the contract is needed "for every later high-Re path" and that T2-0d never settled it. But T2-0's noise is mesh-realisation noise (0.2-0.9 % of Cl) and URANS settled to a steady state in all 58 valid runs (T2-0d, "no oscillation"). A contract for chaotic time-averaging noise in iLES does not transfer to the RANS/URANS line (option B) at all.
- It transfers only to a WaterLily/LES line at Re_c >= 800, which the plan itself says is not meaningful for FSAE Re. So the prize is real only if option C (LES-class evaluators) is ever chosen, which the 2026-10-24 review ranks last.
- The cheap, real part of the prize is the CRN decay measurement (sigma_d/(sqrt(2) sigma_F), expected to rise from 0.1-0.3 at Re 80 toward 1) and the rms/tau_int numbers. A 2-state probe (S2) gets this.

Alternative: state the narrower claim and size the study to it.

### S10 (P3): Numbers and design details to fix

- R4 cost: Fable's table gives flow_96, Re_L 8000, 4.5 h per 120 CU; at 300 CU that is 11.3 h per run, so 2 designs by 2 phases = 45 GPU h (and one run is about at the 12 h session cap). The "20 GPU h" in the table is inconsistent with its own rows. §3.8 omits R4 altogether.
- Cap versus worst case (90 versus 125), see S7.
- Stage 0 uses one phase and one run per grid to set burn-in, window, rms and tau_int, which then fix the registration. One realisation of a chaotic signal gives a poor rms and tau_int; use 3-4 phases for the parent at Re 800 and 2500.
- Domain control: the +1 m outlet (outlet at 1.6c becomes 2.4c) is parent-only, absolute force, 2 % threshold. It is a small change and it cannot detect effects on the differences. Also 10 % blockage with moving ground at Re 2500 in a wake-constrained domain is worth one explicit comment.
- The H_mech retention hypothesis (0.3-1.0) lacks a quantitative anchor in the cited literature (the Zhdanko and Kolomenskiy optimum is for steady laminar solutions up to Re 3000, so not an anchor at R3 where the wake is not steady).
- Taira and Colonius (2009) regime claims were read from the abstract and memory (Fable §7): check against the paper before writing steady/unsteady expectations at R1/R2 into a registration.
- Fable §2.3 says optimal camber peaks at "22-26 % near Re 50-60"; the abstract I checked says the peak is "near Re 40-50". Minor, but numbers from the full text should be re-checked before they enter a document.

### S11 (P3): Missing from the plan

- What happens if XV-01 fails (S7).
- The user-facing statement (S1; draft in §6).
- A line saying RE-01 does not advance L3 and which STATE.md rows it touches (none).
- Cost of procedure itself (hours of Claude and Sonnet time per stage) is nowhere counted next to the GPU hours.

---

## 2. M4 reading table: honest, but it reveals that the outcomes collapse

The table in §9 is honest in its prose (it does not claim any outcome supports high-Re qualification). Its structure shows what the ladder is: a framing input to option A. See S3. If the plan keeps a reading table, add a column "next step if this outcome" and "difference from the next step without RE-01" so that rows with no difference are visible, and trim the study until the remaining rows carry the cost.

## 3. Sequencing and opportunity cost, short version

- Right now the cheapest things with the highest information per hour are: Stage 0 (3 GPU h), the parent-selection scan for an attached demo (5-10 GPU h), the 2D same-mode comparison (10-30 h), the TU Delft data request (Zhou, Overmars & Westerweel 2026, Exp. Fluids 67:75, DOI 10.1007/s00348-026-04191-5; exists; its focus is accelerating inverted wings with a steady comparison; the user must send the request, lead time is weeks), and the #69 step-1 solver-free LTS audit. None of them competes with XV-01 for CPU, and only the first two use GPU.
- XV-01 -> M4 is the critical path. Anything that lengthens M4's wait (S3) costs more than its GPU hours.

## 4. Research-direction risk

Is the project drifting into ever more validation of a toy? Partly yes, and RE-01 as written is a symptom.
- The 2026-10-16 review already says the physics is 3-5 decades from the target ("物理が目標から3-5桁離れている", §4 item 3), that "Re 80 optimising does not guarantee FSAE", and 2026-09-20 had decided not to dig further into the reduced case. RE-01 digs further into the reduced case with the project's largest GPU study.
- The 2026-10-24 review concluded that what is publishable now is a methodology evaluation (L1/L2 as a method result, option A), with B as the route to target physics. The method's valuable claims (paired same-phase differences as CRN, wide-mode spectral rationale, fixed-grid proposer with body-fitted verification) are only worth anything for FSAE if they hold on a problem whose physics resembles FSAE. RE-01 does not test that; it measures how fast a Re-80 answer decays on a plate that is not an FSAE wing.
- A senior CFD and optimization researcher would say: low-fidelity models are useful only if their ranking correlates with the high-fidelity ranking on the design family and regime of interest (multifidelity framing: Peherstorfer, Willcox & Gunzburger, SIAM Review 60(3), 2018; cited from memory, not fetched). Measure that on an attached section, early. A Re ladder on a body that is acknowledged not to be the target is an indirect and expensive substitute.
- On Re-scaling of optimised shapes: single-point optima are sensitive to Re (Srinath & Mittal 2009; Srinath, Mittal & Manek 2009; Zhdanko and Kolomenskiy 2026). For ground-effect wings the Re sensitivity is regime-dependent: single-element forces swing by up to 320 % over ΔRe 0.81e5 through the laminar separation bubble, while multi-element and F1-like wings varied by under 6 % over the same range (Roberts et al. 2017, abstract). Forced transition can reproduce a higher-Re force coefficient without reproducing the flow features. So high-Re transfer is decided by transition and trip handling, which is what option B's contract (trip fixed, slopes only) targets, and which no rung of RE-01 touches.
- On WaterLily/BDIM usable Re: the WaterLily paper validates iLES at sphere Re 3700 with 88-168 cells per diameter, cylinder Re 7620 at about 21 cells per diameter, and TGV Re 1600 (Fable's reading of Weymouth & Font 2025; I did not re-verify the numbers). Maertens & Weymouth (2015) extend BDIM to Re up to about 1e5 for forces (search summary; the paper itself returned 403 for Fable). Wall-resolved BDIM iLES of a foil needed 700/5000/8555 cells per chord at Re_c 1e4/1e5/1e6 (arXiv 2508.09590, verified). A T4 reaches 146 cells per chord at flow_96. So WaterLily is a proposer at Re_c up to a few thousand, not an evaluator at 5e5.

What the senior researcher would recommend instead: finish L2 (XV-01), define the target-relevant demo problem now (attached section, Re_c about 3e3, same mode types, WaterLily-validated range), run the same-mode comparison against the existing 4.6e5 RANS data, and use the ladder only to the extent it is cheap (R1 plus a statistics probe).

## 5. What survives of the plan

- The claim ceiling, written first.
- Hypotheses labelled as hypotheses (§3.1).
- Stage 0 as `EXPLORATORY_COMMITTED` with no design information; its measurement list (stability, drift, rms, tau_int, Strouhal, burn-in, memory, Poisson iterations) is right.
- R1: steady regime, WL flow_32/48 plus OpenFOAM V1 cross-check, floors from the roll control; resolved and independently checked.
- The two-estimator statistics (A between phases, B within run) and the `STAT_INCONSISTENT` gate. This is the good part.
- No second ladder, no thresholds changed after the first force, fail-closed labels.
- OpenFOAM after XV-01.
- The §6 paper-only M4-B preparation (should be upgraded, S8).

## 6. What the plan should tell the user (draft; translate into Japanese for the document)

"RE-01 does not tell you what happens at the FSAE Reynolds number. It tells you how far the Re-80 plate result carries as Re rises to a chord Re of about 3,800 in our fixed-grid solver (about 1 percent of the way to 5e5 in Re; 1.5 of the 3.6 decades in log terms), and whether our statistics still work when the wake becomes unsteady. Above that, the plate is expected to be a stalled bluff body, so nothing at Re 5e5 follows from this study. The only data we have at the target Re are the 2D attached-section runs from T2-0 (descriptive only). The cheapest way to learn about the FSAE regime is a different parent (an attached cambered section) and a comparison of pitch, camber and flap slopes between low Re and 4.6e5. I propose a short ladder (Re 250 plus a statistics probe at 800 and 2500) next to that, not instead of it."

(The "1 percent" is Re_c 3.8e3 / 5e5 = 0.76 %.)

## 7. Verdict and recommended next step

Verdict: **GO_AFTER_FIXES**.

P1 list (must change the plan):
- S1: reframe so the plan says plainly that RE-01 covers Re_c <= 3.8e3, name T2-0 as the existing high-Re evidence, test the "stalled" premise in Stage 0, and treat one R4-like probe as the item closest to the user's question.
- S2: R2/R3 cannot resolve the finalist's 4.05 % x retention at the stated stop rule (3 SE_eff = 4.0 %, so PASS needs retention about 1.0); R2/R3 are under-resolved with no independent check. Gate them on a Stage 0 power test and replace them by a statistics probe.
- S3: the ladder's decision value is low and M4 must not wait for it. Cut to Stage 0, R1 and the probe (20-30 GPU h).

P2 (should change): S4 (BREAK by tau from noise; floor from df = 3; BREAK needs flow_64 or independent concurrence), S5 (estimand: wide-mode slopes at high-SNR amplitude), S6 (exploratory for Stage 0 and the probe; register only R1), S7 (no branch for XV-01 FAIL; cap below worst case; R2/R3 gated on XV-01), S8 (start the attached-parent scan and the same-mode 2D comparison now), S9 (narrow the "unsteady contract" claim).

Recommended next step (5 lines):
1. Run Stage 0 now (parent only, 3-4 phases at Re_L 800 and 2500, plus Re_L 250), adding wall-shear sign and Cp diagnostics so "stalled" and the window power gate become measurements.
2. In parallel, run the attached-parent selection scan (5-10 GPU h, Re_c about 3e3, t/c 8-12 %) and draft the 2D same-mode (pitch, camber, TE-flap) comparison against the existing T2-0c data at Re_c 4.6e5; send the TU Delft data request (user) and do the #69 step-1 audit.
3. Register only R1 (Re_L 250, WL flow_32/48 plus OpenFOAM V1 after XV-01) and run the 2-state statistics probe at 800/2500 as exploratory; write the claim ceiling and reading table before the first force.
4. Register nothing above R1 unless Stage 0 shows SE_T <= 0.6 % reachable within 400 CU and XV-01 has passed; M4 does not wait for any of it.
5. Tell the user the §6 statement above in the first lines of the plan.

---

## Appendix A: numbers behind S2 (my calculation)

Formulas as in Fable §3.3 and §4.3: SE_T = rms * sqrt(2 tau_int / T), sigma_d = sqrt(2) SE_T, SE_eff = sigma_d / sqrt(P), P = 4, tau_int = 3.9 CU.
- SE_T 1.9 %: SE_eff 1.34 %, 3 SE_eff 4.03 %, finalist retention needed 1.00.
- SE_T 1.0 %: SE_eff 0.71 %, 3 SE_eff 2.12 %, retention 0.52.
- SE_T 0.5 %: SE_eff 0.35 %, 3 SE_eff 1.06 %, retention 0.26.
- Window for SE_T 1.9 % / 0.6 %: rms 5 %: 54 / 542 CU; rms 10 %: 216 / 2,167 CU; rms 20 %: 864 / 8,667 CU.
- Wall-resolved BDIM chord cells (power law through 700 at 1e4 and 5000 at 1e5, exponent 0.85, extrapolated down): Re_c 381: 43; 1,219: 116; 3,810: 307; 1.2e4: 818. Available: 49 / 73 / 98 / 146.
- R4: flow_96, Re_L 8000, 18,500 steps per 120 CU, 37.3 M cells at 5.1e7 cell-steps/s plus 20 %: 4.5 h per 120 CU; 11.3 h per 300 CU run; 45 h for 4 runs.
- Log gap (Re_c): 122 to 3,810 = 1.49 decades; 3,810 to 5e5 = 2.12; total 3.61.
- GPU: plan typical 62 (Stage 0 3 + R1 9 + R2 25 + R3 25); R2+R3 = 81 %. SCREEN-01 = 17.2 GPU h, so 3.5x typical, 5.2x at the cap.

## Appendix B: verification status of literature used

Checked in this review:
- arXiv 2605.19468 (Zhdanko and Kolomenskiy, 2026): exists; steady laminar solver, Re 1-3000; optimal alpha decreases monotonically with Re; optimal camber non-monotonic, peak near Re 40-50.
- arXiv 2508.09590 (Zurman-Nasution, Weymouth, Ganapathisubramani): BDIM wall-resolved iLES, 3D, 700/5000/8555 chord cells at Re_c 1e4/1e5/1e6 (note: does not name WaterLily).
- Roberts, Finnis & Knowles 2017 (via Cranfield records): 320 % downforce / 35 % drag over ΔRe 0.81e5 for the single-element wing; multi-element and F1 wing under 6 %; bubble and trip effects. (Fable listed the 320 % figure as unverified second-hand; the Cranfield abstract confirms it.)
- Zhou, Overmars & Westerweel 2026 (Exp. Fluids 67:75): exists; accelerating inverted wing in ground effect with a steady comparison.
- Srinath & Mittal 2009 and Srinath, Mittal & Manek 2009: repository abstracts (flow "very sensitive to Re"; multi-point shapes significantly different).
- WaterLily is an implicit-LES BDIM solver (search results). Maertens & Weymouth 2015 BDIM to Re up to 1e5 with second-order treatment (search summary).

From memory or Fable only, not verified here: Weymouth & Font 2025 validation cases and cell counts; Peherstorfer, Willcox & Gunzburger 2018; Hoerner-type Re-independence of separated bluff-body forces; Ananda et al. 2015; Breuer & Jovicic 2001; Taira & Colonius 2009 regime map; Vogt, Barber & Leonardi 2007 (from the repository's roadmap review).

Repository facts relied on: STATE.md, T2-0 summary, SCREEN-01 analysis (finalist 4.05 %, b_K), FID-01 analysis (tier-A threshold 5.363e-3 N), `fable_analysis.md` tables (dt, cost, steps), issue #66 text. Counts (phase_plan lines, docs, evidence directories, commits) from `wc`, `ls` and `git log` on this worktree.
