# RE-01 plan review: adoption record

- **Reviewed snapshot:** `docs/re01_plan_2026_11_01.md` rev 0, commit `06488878`, SHA-256 `84e26c78b43f5dc5c3f4b5393dc8b155fe3571111f77533f7eed13e08405565a`.
- **Reviews:** three independent sonnet reviews, recorded verbatim in this directory (`numerical.md` N1-N23, `governance.md` G1-G25, `strategy.md` S1-S11). All three returned `GO_AFTER_FIXES`.
- **Rulings:** the contested points (rung scope, the attached-parent scan, the 2D bridge, the order, the M4 table conditioned on XV-01) were put to Fable. Its rulings are in `../fable_decisions.md`; the OC script is `../re01_decisions.py`, seed 20261101.
- **Decision-maker:** the registrant (Claude), under the user's delegation of 2026-10-13.
- **Codes:** A = adopted, AM = adopted with modification, R = rejected.
- **Where it lands:** every decision below is implemented in plan rev 1 (`docs/re01_plan_2026_11_01.md`). The section given is rev 1's.
- **This was RE-01's only plan review.** PROC-01 (`docs/phase_plan.md`, the 2026-10-16 entry) allows at most one three-angle plan review per study. The RE-01 registration will therefore be written from rev 1, with the Stage-0 numbers filled in mechanically by the charter rules; it does not get a second plan review. The source review is still to come.

## P1

| ID | Finding (short) | Decision | Where in rev 1 |
| --- | --- | --- | --- |
| N1, G3, S2 | The SE target matches the finalist's effect, so R2/R3 are underpowered (finalist power 0.21-0.58) | **A.** The primary estimand becomes the through-origin retention slope over the 8 tier-A designs, with a 90 % t-interval (7 dof). The finalist becomes secondary. The OC (Fable §1) gives P(PERSISTS \| r = 0.5) = 0.80 at SE_T 1.5 % and 0.69 at 1.9 %; the null case gives < 0.005. The viability target is therefore 1.5 % | §3.4, §3.5, §3.8 |
| N2, G2 | The labels are not exhaustive, overlap, have no INVALID, and `RE_BREAKS_AT_1` is defined twice | **A.** An ordered, exhaustive label table per rung: INVALID → NUMERICAL → INCOMPLETE → NO_RE_EFFECT → CONTROL_UNRESOLVED → RESOLUTION_LIMITED → DOMAIN_SENSITIVE → NUM_SENSITIVE → slope partition (PERSISTS / WEAKENED / LOST / REVERSED / INDETERMINATE). An independent checker and synthetic tests are required before freeze 1 | §3.5 |
| N3, G4 | The A/B consistency gate misfires by construction | **AM.** The statistics are regime-conditional. In the steady regime only estimator A is used. In the unsteady regime B is descriptive and one-sided (the larger SE is used), so no rung is ever made unjudgeable by B. The CRN ratio is reported as a descriptive quantity | §3.4 |
| N4, G1 | Stage 0 has no charter, leaks through the parent, and measures the wrong things | **A.** A hashed charter is written before any Stage-0 run. Parent only; own phases (1-3 at the new Re); 3 phases per rung, 800 CU (R1 240 CU). The viability formulas and every threshold are fixed in the charter, so Stage 0 sets engineering parameters only. Modifications may only drop. A phase_plan decision records this reading of PROC-01 | §4, phase_plan entry |
| G5 | Controls are undefined or insufficient at the new Re | **AM.** Adopted: byte-identity regression of the new source at Re 80 (item 3); R-best as a secondary design (item 5); positive controls pitch ±3.1 deg, existing registered bytes at ±15 % (item 6); the manipulation check (NO_RE_EFFECT, item 7); determinism by exact equality → INVALID (item 2). The roll becomes a descriptive placement control, not a null test (item 1). **R:** the reduced same-phase Re-80 anchor (item 4), because N14 shows the baseline noise is at most 8 % of rung noise. Stationarity is handled by the charter's block-mean rule (item 8) | §3.2, §3.6 |
| G6 | The finalist carries the decision; the reading depends on XV-01 | **A.** Tier A is primary (unselected, with Re-80 OpenFOAM fidelity). The finalist, M and R-best are secondary, with sign plus a descriptive slope residual. The M4 table is conditioned on XV-01's cause class | §3.2, §3.5, §9 |
| G7, N6 | Adaptive windows conflict with frozen kernel caps | **A.** A fixed window per rung from the charter formula; no in-run stopping. Kernel caps follow SCREEN's 1.5x rule | §3.4, §3.7 |
| G8 | Kernel-loss, data-loss and budget rules are missing; the cap is below the worst case | **A.** A divergence is a result (NUMERICAL) and is never rerun; any other loss gets one identical rerun. A data-loss table, a per-push budget record and new caps consistent with the costs (formal 65 GPU h; worst-case windows are excluded by viability) | §3.7, §3.8 |
| G9 | RE-01 has no roadmap slot; the M4 dependency is contradictory | **A.** A phase_plan amendment, a STATE row and a #66 comment. M4's start condition stays #66's M3 records only; RE-01/ATT-00 records available at that time are inputs. One pre-declared exception: tier-A LOST/REVERSED at R1 triggers an M4 addendum | §7, §9 |
| G10 | `RE_PERSISTS` can be misread; the reading table overreaches; Re 80 is called "creeping flow" | **A.** PERSISTS needs LB ≥ 0.3 (a magnitude condition). The proposer and paper sentences are struck, "creeping flow" is corrected, and the iLES-validated statement is tempered | §1, §9 |
| S1 | FSAE Re is not reached and the framing is soft | **A.** A plain statement opens the plan: RE-01 covers Re_c ≤ 3.8e3, about 1 % of 5e5, and T2-0's 2D attached data at Re_c 4.6e5 are the only target-Re data. **AM:** "stalled" is tested by a parent-only Re_L 8000 regime probe inside Stage 0 (descriptive, about 0.5 GPU h), instead of an R4 rung | §0, §4 |
| S3 | Decision value is low; M4 must not wait | **A** (see G9). The table is conditioned on XV-01 (Fable §5). The cost is cut to formal ≤ 65 GPU h | §2, §9 |

## P2

| ID | Decision | Note |
| --- | --- | --- |
| N5 | A | 90 % t-intervals; pooled σ_d across designs for secondary signs in the unsteady regime |
| N7, N8, G18 | A | Steps per CU from Stage 0; memory measured at 131-135 B/cell; costs recomputed (Fable §1); no flow_64 at formal rungs; R4 removed |
| N9, G16 | AM | flow_48 carries parent, C4 and reflex −29.3 (the largest unselected effects). Gate: the 90 % interval of b_48/b_32 versus [0.5, 2]. flow_64 never changes a label |
| N10 | A | The R1 leading-edge boundary layer is already below one cell on flow_32. Every reading is "in this solver family on this grid sequence" |
| N11, G14 | AM | Domain control at every unsteady formal rung: parent and C4 at 2 phases with a +1 m outlet, judged on the C4 difference against 3 pooled SE → DOMAIN_SENSITIVE |
| N12, G15 | AM | Poisson sensitivity at the top formal rung: parent and C4 at 1 phase with itmx 64 (or tol 1e-5) → NUM_SENSITIVE. Residual quantiles recorded at every rung |
| N13 | AM | R1-OF is a sign and consistency check (V2 is the less damped level), not a retention measurement on V1 alone. No pimpleFoam at R2. A `linearUpwind` V2 parent status probe in Stage 0 (status only) |
| N14 | A | No same-phase anchor; byte-identity regression instead |
| N15 | AM | Candidates 250, 450, 800, 2500; 450 replaces a non-viable 800; 2500 has the lowest priority (Fable §1.3) |
| G11 | A | Retention is defined as a slope from named fields with an interval. R1-OF uses FID's shifts 49-64 (same-shift pairing against FID's Re-80 OpenFOAM values) |
| G12 | A | R1-WL and R1-OF are split. RE-01's OpenFOAM forces are not read before XV-01's written-once analysis exists. Waiting limit 2026-12-06, then `R1_OF_NOT_RUN`. Shifts are disjoint from XV-01's 81-96 |
| G13 | A | No discretion. After R1 primary LOST or REVERSED, the unsteady rungs are `NOT_RUN` by rule. R4 is removed. A written-once `rung1.json` is a registered step; the post-R1 freeze binds only mechanically generated campaign files |
| G17, N17 | A | Kendall τ is descriptive only; no τ-based BREAK; no permutation p-value |
| G19 | AM | RE-01 formal phases 17-20; Stage 0 on phases 1-3 at the new Re (used only at Re 80 before); OpenFOAM shifts as above |
| G20 | A | The plan, the Fable analysis and the scripts are committed (`06488878`). H1-H4 appear in the plan as hypotheses; the regime table is non-binding |
| G21 | A | #69 step 1 is recast as a design memo; #69 itself is not started |
| S4 | A | BREAK-type labels need a resolved interval; nothing fires on τ |
| S5 | AM | **R:** new high-SNR amplitudes (new shapes, new gating and provenance). **A:** the existing ±15 % pitch states serve as positive controls, and the slope over tier A tests the mode mechanism rather than the selected 4 % effect |
| S6 | AM | One plan review (this one). Stage 0, ATT-00 and BRIDGE-2D-00 are exploratory. Unsteady rungs become formal only through the viability rule; otherwise a descriptive probe |
| S7 | A | XV-01 FAIL branches (Fable §5); caps consistent; the "idle quota" argument is dropped |
| S8 | AM | (a) The attached-parent scan ATT-00 starts now as an exploratory track (cap 10 GPU h, week 2). (b) The 2D bridge BRIDGE-2D-00: charter and code prepared now, run only on trigger (a first unsteady rung dropped, or quota left in week 4), cap 15 GPU h, WaterLily 2D. (ii), a 3D RANS pair at 5e5, is rejected |
| S9 | A | The claim about the unsteady-statistics contract is narrowed: it transfers to WaterLily/LES-class work only |

## P3

- **A:** N16-N23 and G22-G25 (allocation note, Re_w definition, label inventory, units, citations, geometry interpolation disclosure, 13 runs per phase, M's near-duplication of camber −19.7, the UNRESOLVED-then-BREAK row, retention intervals in the descriptive list), and the S10/S11 cost and omission fixes.
- **N16** (a longer parent window): left to the registration's OC. The default is equal windows.

## Fable's three corrections to the adopted fixes

All three are adopted:
1. The finalist's sign is nearly unpowered at unsteady rungs, so the finalist's residual from the tier-A slope is added as a descriptive quantity.
2. flow_48 does not carry the finalist.
3. R1-OF uses FID's shifts 49-64.
