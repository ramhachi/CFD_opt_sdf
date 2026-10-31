# High-Re next-step analysis for the CFD shape-optimization project (v18 / SCREEN-01 state)

Date 2026-11-01. Prepared as a research and decision analysis; nothing here is registered, nothing changes a flag, and every number is marked with its source class: **[repo]** = read from the repository files, **[calc]** = back-of-envelope computed from repo anchors (script `scratchpad/calc/re_ladder.py`), **[lit]** = literature with a citation, **[unverified]** = could not be confirmed.

## 0. Executive summary (10 lines)

1. Recommend option (c), ordered: **first a short Reynolds ladder on the frozen v18 designs ("RE-01"), then M4 option B.** The ladder is the only high-Re question that uses the registered designs, the registered statistics and the idle GPU quota; option B needs M4, a new data contract and the local CPU that XV-01 will occupy.
2. RE-01 should be WaterLily-first with three rungs, Re_L = 250, 800, 2500 (chord Re 381, 1219, 3810), on flow_32 with flow_48/flow_64 resolution checks; body-fitted OpenFOAM only at rung 1 (steady laminar) formally and descriptively at rung 2. Cost: Stage 1 (rung 1) about 7 GPU h + 40-50 local CPU h; Stage 2 (rungs 2-3) 40 GPU h typical, 90 GPU h worst case, 1.5-3 weeks of the 30 h/week quota.
3. Physics expectation: the plate (t/c 9.4 %, alpha 20.4 deg, h/c 0.53) is attached and viscous-dominated at Re 80 (45 % of drag is viscous, C_L 0.50 [calc from repo]), probably still steady at Re_L 250 (low aspect ratio 0.72 and moving ground both stabilise), periodic to three-dimensional shedding by Re_L 800, chaotic wake by Re_L 2500, and a massively separated stalled plate at Re >= 1e4 to 1e6. The Re-80 gain mechanism (more negative camber plus reflex) is expected to **weaken** with Re (optimal camber for lift falls from about 22 % at Re 50-60 to 4 % at Re 3000 [lit]) and may **reverse or become unresolvable** once the suction side separates; this is exactly the information the ladder buys.
4. WaterLily cost per convective time **drops** about 2x above Re_L 800 on the same grid because the time step is viscosity-limited at Re 80 (dt = 1/(max flux + 5 nu)) [repo+calc]; what grows is the averaging window needed once the flow is chaotic, so unsteady rungs cost 3-7x a Re-80 run per phase, not 20x.
5. flow_64 (11.1 M cells, 1.4 GB) and flow_96 (37.3 M, 4.8 GB) fit a T4 (15.4 GB) [calc from 128 B/cell in the WaterLily paper]; flow_64 is 1-3 h per run, flow_96 is 4-5 h per run at Re >= 800 and is the practical ceiling for one 12 h session.
6. WaterLily iLES is validated in its own literature at Re 1e3-8e3 with 20-170 cells per body scale; wall-resolved BDIM at Re 1e4-1e6 needed 700-8555 cells per chord [lit], far beyond a T4. Re_L > 8000 in WaterLily is descriptive only.
7. The paired same-phase (common random numbers) trick that gives sigma_d = 2-5e-4 N at Re 80 **stops working in chaotic flow**: trajectories decorrelate, so the difference variance returns to twice the single-run time-averaging variance. sigma_d must be re-measured as the between-phase SD of time means, cross-checked against a within-run batch-means standard error, with the averaging window set adaptively (200-800 convective units) to a pre-registered SE target.
8. The high-Re (1e5-1e6) rung on v18 is **not** recommended inside RE-01: at 20.4 deg the plate is stalled, steady RANS will not settle (T2-0 lesson, Vogt et al. 2007), URANS/LES costs 1-3 days per 3D case locally, and no reference data exist for this body. FSAE relevance requires an attached-regime parent, which is the M4/B5 decision, not a ladder on v18.
9. Pre-register labels RE_PERSISTS / RE_BREAKS_AT_k / RE_RESOLUTION_LIMITED / RE_UNRESOLVED_STAT / INCOMPLETE, a per-rung flow_32-vs-flow_48 sign gate, a domain-extension control at the top rung, a Poisson-residual probe, and a hard GPU cap (90 h) with no extension.
10. RE-01 feeds M4 (#66) with: whether the Re-80 L1/L2 result is a low-Re artefact for this geometry (bears on option A's paper framing), whether an intermediate-Re iLES stage ("L2.5") is worth declaring in B5, and the unsteady-statistics contract that any URANS/LES evaluator under option B/C would need.

## 1. Which high-Re question first (Q1)

### 1.1 Where the project stands [repo]

- L1 is done at Re 80 (SCREEN-01 `SCREEN01_GAIN`: finalist `v18__camber_m29.55_pitch_p0.155_reflex_p16.115`, +1.077e-2 N = 4.05 % of 0.266 N on flow_32, drag -1.99e-3 N, flow_48 confirmed). XV-01 (#65, L2) is being registered. All qualification flags are false.
- T2-0 (#57) is closed with three registered NO-GO studies; EVAL-VALID-01 (#68) found the only quantitative reference inadequate; EVAL-PT-01 (#69) is conditional on an M4 choice; M4 (#66) is open and keeps its dependency on the applicable M3 outcome (XV-01 PASS or FAIL). The roadmap review of 2026-10-24 recommends option A (close Re 80 as methodology) as mandatory and option B (attached-regime evaluator with slope contracts) as conditional.
- The target physics was declared as U = 30 m/s, L about 3 m, Re about 6e6 in the ProblemSpec (P4e "uncorrected") [repo: roadmap_review_2026_10_16 line 37]; FSAE front-wing chords are 0.3-0.42 m at Re 5e5-6e5 [lit: NTNU thesis; Monash 420 mm at 0.5e6].
- No prior Re-ladder or flow_64/flow_96 discussion exists in `docs/` (grep returned nothing).

### 1.2 Comparison of the options

| | (a) Re ladder on 3D v18 (WaterLily + laminar OpenFOAM) | (b) M4 option B evaluator (attached-regime ground-effect wing, slope contracts, LTS) | (c) hybrid: short ladder, then (b) |
| --- | --- | --- | --- |
| Question answered | Do the registered Re-80 differences (finalist, M, tier-A) keep sign and size as Re rises; where do they break; does the paired-difference method survive unsteadiness | Can a high-Re body-fitted evaluator pass a validation contract on slopes dCl/dalpha, dCl/d(h/c) at affordable cost | Both, in sequence |
| Uses existing registered assets | Yes: frozen phi files, phases, harness, analyzers, FID/SCREEN design set, local OpenFOAM U3 pipeline | No: new geometry (2D section), new mesh path (gmsh non-reproducible locally, LOCAL-OF-01 FAIL), new reference data contract, new solver mode (LTS) | Yes for the ladder |
| Procedural readiness | Can be registered now (PROC-01); no M4 dependency because it is Re-80-problem work, not an evaluator GO | Needs M4 to "select new work" (issue #69 start condition) and an EVAL-VALID-01 contract; M4 waits for XV-01 | Ladder now; option B documents in parallel; M4 decides after XV-01 |
| Compute conflict with XV-01 | None for WaterLily (XV-01 is OpenFOAM-only); OpenFOAM rungs queue after XV-01 | Local CPU conflict with XV-01 V3 (16 cases x 8 h) | Same as (a) |
| Cost | Stage 1 about 7 GPU h + 40-50 CPU h; Stage 2 40-90 GPU h | Unknown until EVAL-PT-01; T2-0d gave 92 min per URANS evaluation on Kaggle CPU; LTS target 20-30 min | Sum |
| Can claim | Re-dependence of paired same-phase differences of registered designs in WaterLily iLES and laminar OpenFOAM up to Re_c about 4e3 (sign, retention, ranking, noise structure) | A registered evaluator GO on a 2D attached-regime section (slopes only), or a bounded NO-GO | Both ceilings |
| Cannot claim | Anything about Re >= 1e4, transition, turbulence models, FSAE, physical downforce, grid independence | Anything 3D, separated-regime, full vehicle; still no optimizer-selected shape | Same |
| Value for the FSAE goal | Indirect: tells M4 whether the fixed-grid proposer and the paired statistics generalise beyond the creeping-flow regime, and provides the unsteady-statistics contract | Direct but distant: an evaluator is a prerequisite for L3, not L3 | Indirect then direct |
| Main risk | The stalled plate at 20 deg is physically unlike an FSAE wing at any Re; the ladder could be read as "Re 80 was a toy" without a path forward | Repeats T2-0 (four studies, NO-GO); reference data remain the blocker | Ladder result may be ambiguous (UNRESOLVED_STAT) if fluctuations are large |

### 1.3 Recommendation and reasoning

Order: **(c)**, with the ladder deliberately short and WaterLily-first.

1. It answers the user's question directly and cheaply, with assets that already exist and have been reviewed (the FID-01/SCREEN-01 harness, the frozen states, the UNC-01 estimators). Registration effort is one plan plus the usual three-angle review; most rules are inherited.
2. It is the only high-Re work that can be registered and run before M4, because it is not an evaluator GO and does not depend on the XV-01 verdict. It consumes GPU quota that would otherwise sit idle while XV-01 occupies the Mac.
3. It produces the one ingredient every later high-Re path needs and that T2-0 never settled: a registered way to measure sigma_d and resolve small differences when the flow is unsteady (T2-0d's "time-averaged URANS resolves +-0.25 deg" was never certifiable against fine30; the ladder gives a cheap sandbox to fix the contract).
4. It tells M4 whether to frame L1/L2 as "a creeping-flow demonstration" or "a method whose transfer survives to Re_c about 4e3". Either answer is useful for option A's paper and for the B5 ProblemSpec (should an intermediate-Re iLES stage exist before RANS?).
5. Option B's preparation is documents (EVAL-VALID-01 condition table, slope contract, LTS audit of #69 step 1) and can proceed in parallel without compute or registration; its execution should wait for the M4 decision as issue #66 requires.

What (c) does **not** do: it does not move the project closer to FSAE physics by itself. The v18 plate at alpha 20.4 deg is a bluff body at any Re above about 1e3; an FSAE front wing operates attached. The ladder should be registered with that ceiling written in the first line, so that no one reads a "RE_PERSISTS" as a step toward high-Re qualification.

## 2. Physics expectations for the v18 plate from Re 80 to 1e6 (Q2)

### 2.1 Dimensionless state of the registered problem [repo + calc]

- Geometry: stadium section t = 0.1153 m (round edges r = t/2 = 57.7 mm), chord c = 1.2192 m (t/c = 9.46 %), span 0.875 m (AR = 0.72), alpha = 20.395 deg, ride height 0.65 m (h/c = 0.53), moving ground at U, U = 1 m/s, nu = 0.01 m^2/s, L_ref = 0.8 m, Re_L = 80. Domain 5 x 2.4 x 1.8 m; the plate occupies x = -0.6..0.55, so the outlet is about 1.6 chords behind the trailing edge; cross-section blockage = 0.4375/4.32 = 10 %.
- Derived Reynolds numbers: Re_c = 122, Re_t = 12, Re on the projected width w = c sin(alpha) + t cos(alpha) = 0.533 m: Re_w = 42, leading-edge radius Re_r = 5.8.
- Parent forces at flow_48: downforce 0.266 N, drag 0.284 N [repo UNC-01]; C_L = 0.50 and C_D = 0.53 on the 1.067 m^2 planform; the viscous share of drag is 463/1027 = 45 % [repo SCREEN f48k13 summary]. The flow is steady: half-window relative drift of downforce 1e-8 to 2.5e-5 in every SCREEN flow_32 run [repo].
- The finalist adds camber -29.55 mm (2.4 % of chord), reflex +16.1 mm, pitch +0.155 deg [repo].

### 2.2 Expected regime changes with Re (chord Re in parentheses)

| Re_L (Re_c) | Expected regime | Basis |
| --- | --- | --- |
| 80 (122) | Steady, attached in the viscous sense, thick boundary layers (laminar delta at TE about 5c/sqrt(Re_c) = 0.55 m, 22 cells at flow_32) | Measured drift [repo]; 2D flat plate at Re 100 has its Hopf bifurcation at alpha about 28 deg, above 20.4 deg [lit: Brunton et al., APS DFD 2011 abstract] |
| 250 (381), Re_w 133 | Probably still steady or weakly periodic. Low AR (0.72) and tip vortices stabilise; the moving ground is stabilising at Re 300-1000 (shown for NACA 4415 at 20 deg) | Taira & Colonius 2009: at Re 300 low-AR plates reach steady, periodic or aperiodic states depending on AR and alpha, with tip vortices changing stability relative to the 2D von Karman street [lit]; He et al. (Liverpool) stability analysis [lit]; 3D wake instability of an inclined plate at 20-30 deg sets in at Re_w 160-234 [lit: Floquet study] |
| 800 (1219), Re_w 425 | Periodic to three-dimensional shedding; parallel shedding mode below Re about 525 at 20 deg, oblique above [lit: Yang et al. 2012] | Yang, Pettersen, Andersson, Narasimhamurthy, Phys. Fluids 24, 084103 and 094107 (2012) [lit, abstracts only] |
| 2500 (3810), Re_w 1328 | Aperiodic, transitional wake, laminar boundary layers; the "Re 3700 sphere" class where WaterLily iLES is validated | WaterLily paper sphere Re 3700 [lit] |
| 8000-25000 (1.2e4-3.8e4) | Massively separated stalled plate with a large constant-pressure recirculation on the leeward (suction) side and asymmetric shedding at St about 0.2; shear-layer transition | Breuer & Jovicic 2001 (flat plate, Re_c 2e4, alpha 18 deg) [lit] |
| 1e5-1e6 (1.5e5-1.5e6) | Still stalled at 20 deg (thin and 4.3 % plates stall near 10 deg at Re 6e4-1.6e5 [lit: Ananda et al. 2015]); transition in the separated shear layer; a rounded 57 mm leading edge may form a leading-edge separation bubble whose length is Re-dependent in the laminar/transitional regimes and Re-independent in the turbulent regime [lit: Ota et al. 1981, Li & Djilali 1995 via secondary sources] | T2-0 found steady RANS does not settle for separated ground-effect flows (h/c 0.09-0.134) [repo]; Vogt, Barber & Leonardi 2007 report the same [repo roadmap 4.7] |

Ground effect: at h/c 0.53 the inverted-wing force enhancement is weak (Zerihan & Zhang's enhancement is below h/c about 0.3) [repo roadmap 4.7, lit]; the moving ground mainly acts as a stabiliser and a wake constraint here.

### 2.3 Will the Re-80 gain mechanism persist?

- At Re 80 the plate works as a viscous lifting body; the optimizer found more negative camber (2.4 % of chord) and reflex. Steady-laminar optimal-airfoil studies agree that camber is the dominant lever at low Re and that its optimum **decreases** with Re: optimal camber for C_L/C_D is about 7 % at Re 1, peaks at 22-26 % near Re 50-60, and falls to about 4 % at Re 3000, with the optimal angle of attack falling from 38 deg to 6.4 deg; the sensitivity of the objective to shape grows from 2 % (Re 10) to 12 % (Re 1000) across the same neighbourhood [lit: arXiv 2605.19468, 2026]. Srinath & Mittal 2009 found low-Re optimal airfoils thin and camber-dominated and "very sensitive to Re" [lit].
- Reading for v18: the direction "camber up to a few percent helps lift" should persist while the flow is attached in the mean, i.e. through rung 1 and perhaps rung 2; the magnitude relative to the parent force should shrink; once the suction side is separated (rung 3 and above) the camber lever acts mainly through the separation point and the reflex lever through the trailing-edge Kutta condition, and the sign is not predictable from the literature. Thin cambered plates (4 %) outperform flat plates at Re 6e4-2e5 in lift and stall angle [lit: Pelletier & Mueller 2000], but that is below stall, not at 20 deg.
- Expectation to pre-register as a hypothesis, not a result: H_mech = "the finalist's downforce gain keeps its sign at Re_L 250 and 800 with retention 0.3-1.0 of the Re-80 value, and is unresolved or reversed at Re_L 2500". A reversal at rung 1 would be surprising and would mark the Re-80 result as a creeping-flow artefact.
- The heave non-transfer of FID-01 (pure heave fails on OpenFOAM) is a z-lattice artefact unrelated to Re and is not expected to change; it should stay out of the design set.

### 2.4 Literature on Re sensitivity relevant to the end goal

- Inverted wings in ground effect: Re and transition are first-order. Forcing transition eliminated the laminar separation bubble and produced trailing-edge separation; the force depended on trip location [lit: Roberts, Finnis & Knowles 2017, J. Fluids Eng. 139]; scale effects on the single-element wing were found in both Re and ride height [lit: Roberts et al., Aeronautical Journal]; a 320 % downforce change for a 0.8e5 Re difference is quoted secondhand from Correia et al. 2014 [unverified]. New open-access data: Zhou, Overmars & Westerweel 2026, Exp. Fluids 67(6):75, Tyrrell 026 accelerating and steady, DOI 10.1007/s00348-026-04191-5 [lit].
- Flat plates at Re 6e4-1.6e5: C_Lmax 0.55-0.70 slightly increasing with Re, lift-curve slope increasing with Re, stall near 10 deg, no hysteresis [lit: Ananda, Sukumar & Selig 2015, AST, DOI 10.1016/j.ast.2014.11.016].
- Shape-optimization gains under Re change: single-point optima have poor off-design performance; multi-point designs differ substantially from single-point ones [lit: Srinath, Mittal & Manek 2009]; no paper was found that quantifies the loss of an Re 1e4 optimum at Re 1e5 [unverified gap].

## 3. Feasibility and cost per Re band and solver (Q3)

### 3.1 WaterLily anchors [repo]

- flow_32 (200x96x72 = 1.38 M cells): 13,460-13,650 steps for T = 120 convective units (burn-in 80, window 80-120), solve wall 345-350 s, kernel per-run wall 410-470 s including overhead (SCREEN f32a/f32b: 12 runs in 5,240 s, 10 in 4,683 s).
- flow_48 (300x144x108 = 4.67 M cells): 26,360-27,310 steps, solve wall 2,398-2,424 s, per-run 2,576-2,740 s (f48k13: 3 runs in 7,727 s).
- Throughput 5.1-5.4e7 cell-steps per second on a Tesla T4 (both grids). For comparison the WaterLily paper reports 1.57 ns per cell-step on an H100 (6.4e8 cell-steps/s), about 12x faster, consistent with the memory-bandwidth ratio [lit].
- Time step rule in WaterLily 1.8.0 `Flow.jl`: dt = min(10, 1/(max flux_out + 5 nu)), with nu = n/80 lattice units [repo: ~/.julia/packages/WaterLily/4Wr0g/src/Flow.jl:166-169]. Measured mean dt: 0.284 (n = 32) and 0.219 (n = 48), which implies a max flux of about 1.5-1.6 lattice units [calc]. At Re 80 the 5 nu term (2.0 and 3.0) dominates: **the Re-80 runs are viscosity-limited in dt**.
- Poisson: multigrid, tol 1e-4, itmx 32 [repo]. GPU memory: 128 B per cell from the paper's 29 GB for 226 M cells in FP32 [lit]; the Kaggle T4 has 15,360 MiB [repo nvidia_smi.csv]. Actual memory used by the project's runs was not recorded [unverified].

### 3.2 Scaling with Re and grid [calc]

Steps for T = 120 convective units, solve hours at 5.1e7 cell-steps/s, +20 % overhead for wall, memory at 128 B/cell, and cells per laminar boundary-layer thickness at the trailing edge (delta = 5c/sqrt(Re_c)):

| Re_L | grid | cells (M) | dt | steps/120 CU | wall h/run | mem GB | cells per delta_TE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 80 | 32 | 1.38 | 0.28 | 13,600 | 0.12 | 0.18 | 22 |
| 80 | 48 | 4.67 | 0.22 | 26,200 | 0.80 | 0.60 | 33 |
| 80 | 64 | 11.06 | 0.18 | 42,600 | 3.1 | 1.42 | 44 |
| 80 | 96 | 37.32 | 0.13 | 87,000 | 21 | 4.78 | 66 |
| 250 | 32 | 1.38 | 0.46 | 8,400 | 0.08 | 0.18 | 12.5 |
| 250 | 48 | 4.67 | 0.40 | 14,500 | 0.44 | 0.60 | 19 |
| 250 | 64 | 11.06 | 0.35 | 21,700 | 1.6 | 1.42 | 25 |
| 800 | 32 | 1.38 | 0.57 | 6,700 | 0.06 | 0.18 | 7 |
| 800 | 48 | 4.67 | 0.54 | 10,700 | 0.32 | 0.60 | 10.5 |
| 800 | 64 | 11.06 | 0.51 | 15,000 | 1.1 | 1.42 | 14 |
| 800 | 96 | 37.32 | 0.47 | 24,800 | 6.0 | 4.78 | 21 |
| 2500 | 32 | 1.38 | 0.62 | 6,200 | 0.06 | 0.18 | 4 |
| 2500 | 48 | 4.67 | 0.61 | 9,500 | 0.29 | 0.60 | 6 |
| 2500 | 64 | 11.06 | 0.60 | 12,900 | 0.93 | 1.42 | 8 |
| 2500 | 96 | 37.32 | 0.57 | 20,100 | 4.9 | 4.78 | 12 |
| 8000 | 48 | 4.67 | 0.63 | 9,100 | 0.28 | 0.60 | 3.3 |
| 8000 | 96 | 37.32 | 0.62 | 18,500 | 4.5 | 4.78 | 6.6 |
| 8000 | 128 | 88.5 | 0.61 | 25,000 | 14.5 | 11.3 | 8.8 |

Readings:
- Above Re_L about 800 the step count per convective unit halves (n = 32) to 2.5x fewer (n = 48) relative to Re 80, because dt becomes convection-limited. A 120-CU run at Re 2500 on flow_48 costs 0.29 h instead of 0.80 h.
- flow_64 and flow_96 fit the T4 comfortably (1.4 and 4.8 GB; multigrid and body fields add a fraction). flow_128 (11.3 GB) is marginal. A flow_96 run of 120 CU is 4.5-6 h; a 400-CU averaging run on flow_96 would be 15-20 h and does not fit one 12 h session; flow_64 at 400 CU (3-4 h) does.
- Resolution: the chord has 49/73/98/146 cells and the thickness 4.6/6.9/9.2/13.8 cells at n = 32/48/64/96. The leading-edge radius (57.7 mm) is 2.3/3.5/4.6/6.9 cells, and its local boundary layer (about r/sqrt(Re_r)) is 7.6 mm at Re_L 800, i.e. **below one cell on every grid**; the BDIM kernel (about 1-2 cells) will smear the leading-edge separation at Re >= 800. This makes a per-rung flow_32-vs-flow_48(-vs-flow_64) consistency gate essential, and it is the physical reason the ladder should stop at Re_L 2500 for registered claims.
- WaterLily's own validation range: sphere Re 3700 with 88-168 cells per diameter (C_D within 4-7 % of DNS/LES), oscillating cylinder Re 7620 with about 21 cells per diameter (mean power within 3 %), TGV Re 1600 [lit: Weymouth & Font 2025, CPC 315:109748, arXiv 2407.16032]; "model-free, making it an implicit LES solver"; flux-limited QUICK convection. BDIM is reported accurate for integrated forces up to Re 1e5 [lit: Maertens & Weymouth 2015, CMAME 283:106-129], but the wall-resolved flapping-foil study that used it needed 700, 5000 and 8555 cells per chord at Re 1e4, 1e5 and 1e6 [lit: arXiv 2508.09590, Table 2]. Our flow_96 gives 146 cells per chord. Conclusion: WaterLily rungs are defensible as iLES to Re_c about 4e3 (Re_L 2500) with the sphere-class resolution, descriptive at Re_L 8000, and not meaningful at Re >= 1e5.

### 3.3 Averaging windows for unsteady rungs [calc]

- Shedding scale: St about 0.17-0.2 on the projected width w = 0.533 m gives a period of about 3.1 s = 3.9 convective units (L/U = 0.8 s). The current 40-CU window holds about 10 cycles.
- Standard error of a time mean with integral time tau_int about one period: SE_T = sigma_F sqrt(2 tau_int / T). With a lift rms of 10 % of the mean (plausible for a stalled plate [lit: Breuer & Jovicic report strong asymmetric shedding; the value 10 % is an assumption]), SE_T = 4.4 % of the mean at T = 40 CU, 1.9 % at T = 216 CU, 1.0 % at 780 CU, 0.5 % at 3,100 CU.
- Paired differences in a chaotic regime are differences of two independent means: sigma_d = sqrt(2) SE_T; with P = 4 fresh phases, SE_eff = sqrt(2) SE_T / 2 = 0.71 SE_T. To resolve a 4 % gain at 3 SE_eff one needs SE_T <= 1.9 %, i.e. T about 220 CU per phase for 10 % rms, 880 CU for 20 % rms. Hence the window must be adaptive with a cap (200-800 CU after an 80-CU burn-in), and the realistic resolution at chaotic rungs is a 2-4 % difference, not the 0.3 % the Re-80 CRN method gives.
- Cost consequence per phase run at Re_L 800 on flow_32: 56 steps per CU, so 380 CU = 21k steps = 0.17 h wall (0.44 h at 880 CU); flow_48: 89 steps per CU, 380 CU = 0.95 h (2.0 h at 880 CU); flow_64: 125 steps per CU, 380 CU = 2.9 h (6.7 h at 880 CU, still inside a 12 h session).

### 3.4 OpenFOAM local anchors and scaling [repo + calc]

- Host: Apple M4 through Rosetta inside Docker (`VirtualApple`, AVX2, no AVX-512), containers limited to 4 CPUs and 8 GB in total; OpenFOAM is serial and deterministic [repo local gate]. Laminar simpleFoam cost 5.5-6.8 us per cell-iteration (V2: 212,822 cells, 1,562 iterations, 31 min; V3: 1,461,141 cells, 8-10 s per iteration, about 8 h per case) [repo FID-01 5.3]. V1 (about 40k cells) 3-5 min per case.
- Laminar steady 3D at Re_L 250 (rung 1): V1 288 cases (9 states x 16 mirror pairs x 2) x 5-8 min = 24-38 CPU h; V2 16 cases (4 states x 2 pairs x 2) x 45 min = 12 CPU h; total 40-50 CPU h = 1-2 days on 4 cores, after XV-01 frees the machine. Convergence may slow or fail if the flow is unsteady at Re_c 381 (pre-register a parent probe; if `SIMPLE solution converged` is not reached, rung 1 OpenFOAM degrades to the descriptive pimpleFoam subset).
- Laminar unsteady 3D (pimpleFoam) at Re_L 800: about 40k steps x 2 PISO correctors on V2 = 21 CPU h per case (6.7 h at 4 cores); only a descriptive subset (parent, finalist, M at 2 shifts = 6 cases, about 40 h wall) is affordable; no 16-pair statistics.
- 3D RANS/URANS SST with wall functions at Re_c 1e5-1e6 on v18: first-cell height for y+ 30 is 6.0, 1.4 and 0.76 mm at Re_c 1e5, 5e5, 1e6 [calc]; a snappy mesh with prism layers on plate plus ground is 3-8 M cells; at 6 us x 1.8 (two turbulence equations) and 3,000 iterations: 27-72 CPU h per steady case (8-22 h at 4 cores); URANS 10x more. Steady convergence is unlikely for a 20-deg plate (T2-0 experience, Vogt et al. 2007). Not affordable as a statistics study; 2-6 descriptive cases at most. Not recommended inside RE-01.
- Kaggle: 30 GPU h per week is the commonly reported quota, not an official figure [lit, unverified]; 12 h session cap [lit]; 5 concurrent CPU sessions [repo T2-0 summary]. The T4 x2 session exposes two GPUs; the harness pins one.

### 3.5 Reference data per rung

- Re_L 250-2500 on this exact body: none exist. Independence comes from (i) the flow_32/48/64 consistency gate inside WaterLily and (ii) the laminar OpenFOAM at rung 1 (and descriptively at rung 2). Canonical checks that could be added as a one-off solver control: sphere drag at Re 3700 (C_D 0.38-0.39, the WaterLily paper's own case) or the inclined flat plate Strouhal data of Yang et al. 2012 — the latter would need a thin-plate geometry and is optional.
- Re >= 1e5: only ground-effect wing data (Zerihan & Zhang; Zhou et al. 2026) on a different body; nothing for a stalled thick plate. This is a further reason to keep the FSAE-Re question inside option B.

### 3.6 A concrete ladder

| rung | Re_L (Re_c) | WaterLily grids | window | OpenFOAM | designs x phases | est. GPU h (typical / worst) | est. CPU h |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 250 (381) | flow_32 formal; flow_48 confirm (4 states x 2 phases) | 120 CU; extend to 240 if the drift rule fires | simpleFoam V1 16 pairs all states; V2 2 pairs for 4 states | 9 x 4 | 7 / 12 | 40-50 |
| R2 | 800 (1219) | flow_32 formal; flow_48 confirm (4 x 2); flow_64 parent + finalist x 1 | adaptive 200-800 CU + 80 burn-in | pimpleFoam V2 descriptive, 3 states x 2 shifts | 9 x 4 | 20 / 45 | 40 (descriptive) |
| R3 | 2500 (3810) | same as R2 plus a domain-extension control (parent, +1 m outlet) | adaptive | none | 9 x 4 | 20 / 45 | 0 |
| R4 (optional, descriptive only) | 8000 (1.2e4) | flow_96 parent + finalist x 2 phases | 300 CU | none | 2 x 2 | 20 | 0 |
| total R1-R3 | | | | | | 47 / 102 | 80-90 |

Designs (9): parent; finalist; hand design M `camber_m19.7_pitch_m0.38`; C1 (camber -11.3 + reflex -11.3); W4 camber -19.7; W6 reflex -29.3; W8 pitch +0.7; W3 pitch -0.7 (a negative-sign design); roll +25 mm (NC). Phases: four fresh in-plane phases per rung (k = 17-20 of the R2 sequence, never used). All phi files already exist with hashes [repo].

## 4. Statistics when the flow becomes unsteady or turbulent (Q4)

### 4.1 What the registered method relies on [repo]

UNC-01 measured sigma_d = 2.1-5.5e-4 N on flow_32 with P = 6 common phases, and noted that common phases remove most of the placement noise: sigma_d / (sqrt(2) sigma_F) = 0.11-0.29 for downforce. The floor 2.09e-4 N is the roll control's sigma_d; SE_eff = max(sigma_d, floor)/sqrt(P). FID-01 and SCREEN-01 inherit this. The roadmap review identifies the mechanism as common random numbers (CRN), which reduces variance when the response is monotone in the shared randomness [repo 4.3].

### 4.2 How it changes

1. **Steady rung (R1 if steady).** Nothing changes; the half-window drift rule (0.002 relative, UNC-01) still certifies steadiness; the same estimators apply; the OpenFOAM mirror-pair estimator applies unchanged.
2. **Periodic rung.** Forces are phase-locked limit cycles. Time means over an integer number of periods converge fast; the CRN benefit survives partially because the parent and design share the initial transient and forcing. Pre-register: window length a multiple of the measured period (from the lift spectrum), a stationarity check on three consecutive windows, and report the amplitude and Strouhal number as descriptive outputs.
3. **Chaotic rung.** Trajectories decorrelate after a few Lyapunov times, so the same-phase pair is no longer a matched pair: Var(Delta) -> 2 Var(mean_T). sigma_d then equals sqrt(2) times the time-averaging SE and no longer scales as |Delta|^0.5 as at Re 80. Any residual placement bias (the x-translation non-null of -1.65e-3 N at Re 80) is still removed by taking differences at the same phase, so same-phase pairing remains correct; it simply stops reducing variance.

### 4.3 Re-measuring sigma_d: a two-estimator contract

- **Estimator A (between phases, inherited):** Delta_k for k = 1..P fresh phases; sigma_d = SD(Delta_k) with P-1 dof; SE_eff = sigma_d/sqrt(P). This is the decision estimator, as in M2.
- **Estimator B (within run):** non-overlapping batch means of the force over the averaging window with at least 20 batches of at least 5 tau_int each, or the batch-means-and-batch-correlation estimator of Russo & Luchini (2017) [lit: JCP 347:328-340, DOI 10.1016/j.jcp.2017.07.005]; tau_int from the autocorrelation of the lift signal. SE_T per run; predicted sigma_d,pred = sqrt(SE_T,design^2 + SE_T,parent^2).
- **Consistency gate:** sigma_d / sigma_d,pred inside [0.5, 2]; outside it, label STAT_INCONSISTENT and do not judge the rung. The ratio itself measures how much CRN benefit remains (expected to go from 0.1-0.3 at Re 80 toward 1 at the chaotic rung).
- **Adaptive window:** after the 80-CU burn-in, extend T in 100-CU blocks until SE_T <= 1.9 % of the parent force on both parent and design, cap 800 CU; if the cap is reached, label UNRESOLVED_STAT for that design. Initial-transient detection should use a registered rule (e.g. the drift of successive 100-CU block means, or the transient-detection framework of arXiv 2511.22618 [lit]) rather than the fixed 80 CU alone, since the wake takes longer to develop at higher Re.
- **Floors:** the Re-80 floor (2.09e-4 N) is replaced per rung by the roll control's sigma_d measured at that rung, as UNC-01 did.
- **Decision scale:** at chaotic rungs the resolvable difference is 3 SE_eff about 2-4 % of the parent force, so the ladder judges the sign and the gross retention of the 4 % finalist gain and of the >= 2.7 % tier-A differences; it cannot judge 0.7 % effects. State this in the claim ceiling.
- **OpenFOAM side:** at rung 1 the mirror-pair estimator is unchanged. At an unsteady rung, pimpleFoam means need the same estimator B; with 6 descriptive cases no SE_V can be claimed (report only).
- **Ranking:** Kendall tau between Re-80 Delta_32 and rung-k Delta_32 over the 8 non-control designs, with a pre-registered threshold (tau >= 0.6 for RE_PERSISTS, which FID-01 exceeded at 0.85 against OpenFOAM) and a permutation p-value.

Literature check: an LES study at Re 3900 averaged over 25-100 shedding cycles and found drag and Strouhal number far less sensitive to the window than the recirculation length [lit]; MARIN notes that time-averaging is ill-defined for shedding flows unless the frequency content is checked [lit]. Both support reporting spectra and multiple windows rather than one mean.

## 5. Risks, stopping rules, decision rules, and the M4 feed (Q5)

### 5.1 Risks and pre-committed responses

| Risk | Signal | Pre-registered response |
| --- | --- | --- |
| Leading-edge separation under-resolved (r = 2.3-4.6 cells) | flow_32 and flow_48 disagree in sign for the finalist or for >= 2 of 8 designs | Label RE_RESOLUTION_LIMITED for the rung; the flow_64 pair decides descriptively; no finer formal grid is added inside this registration |
| Outlet too close (1.6 c) and 10 % blockage at high Re | Parent downforce changes by > 2 % with the +1 m outlet control at R3 | Report; mark R3 (and above) domain-sensitive; a domain change is a new registration, not an amendment |
| Poisson at tol 1e-4 / itmx 32 under-converged at sharper pressure fields | `poisson.csv` probe shows the iteration cap hit in > 10 % of steps | Report; if the finalist sign depends on it, label UNRESOLVED_NUM (the GRIDRES-01 probe exists) |
| Fluctuations larger than 20 % rms make SE target unreachable | Cap 800 CU reached | UNRESOLVED_STAT; no window extension beyond cap |
| Float32 accumulation over long runs | Parent repeat at the same phase differs by > SE_T/10 | Determinism control as in SCREEN (expected exact 0 at Re 80; at chaotic rungs exactness still holds for identical inputs) |
| simpleFoam does not converge at R1 | Parent probe fails `SIMPLE solution converged` | R1 OpenFOAM degrades to descriptive pimpleFoam subset; the formal body-fitted test is dropped and the ladder becomes WaterLily-only with grid consistency as independence |
| Kaggle quota or session loss | > 30 % of planned kernels lost | INCOMPLETE; preserve partial records; no rerun beyond the registered one-retry rule |
| Reading drift ("Re 80 result is a toy") | — | Write the claim ceiling and the M4 interpretation table into the registration before any run |
| Resource conflict with XV-01 | XV-01 V3 jobs active | OpenFOAM rungs start only after XV-01's last case; WaterLily rungs are independent |

### 5.2 Hard stopping rules

- GPU cap 90 h total (about 3 weeks of quota), CPU cap 100 h; written once, no extension.
- Rung order fixed R1 -> R2 -> R3; R4 only if R1-R3 complete under cap and all three are judged (any label).
- Stop early after R1 if RE_BREAKS_AT_1 (sign reversal of the finalist on both WaterLily grids and on OpenFOAM V1): the result is already decisive for M4; R2/R3 are optional descriptive follow-ups, not required.
- No design, amplitude, grid, window-cap or threshold changes after the first force is read; no second ladder.

### 5.3 Decision labels (per rung, then overall)

- RUNG_PASS: finalist and >= 6 of 8 designs keep the Re-80 sign on flow_32 with |Delta| >= 3 SE_eff, flow_48 same sign for all four confirmation states, Kendall tau >= 0.6; at R1 also OpenFOAM V1 same sign for the finalist and M with retention 0.3-3.0.
- RUNG_BREAK: finalist sign reversed and resolved (|Delta| >= 3 SE_eff) on both grids, or tau < 0.3.
- RUNG_UNRESOLVED: SE target not met (UNRESOLVED_STAT), grids disagree (RESOLUTION_LIMITED), or statistics inconsistent (STAT_INCONSISTENT).
- Overall: RE_PERSISTS (R1-R3 all PASS), RE_BREAKS_AT_k (first BREAK), RE_UNRESOLVED (no BREAK, some UNRESOLVED), INCOMPLETE.
- Descriptive outputs in every case: retention curves Delta(Re)/Delta(80) per design, C_L and C_D of the parent vs Re, drag-constraint behaviour of the finalist, Strouhal number and rms, the CRN ratio per rung, and the measured cost per run.

### 5.4 What feeds M4 (#66)

| RE-01 outcome | Reading for M4 |
| --- | --- |
| RE_PERSISTS | The fixed-grid proposer and paired statistics transfer beyond creeping flow on this geometry; supports declaring an intermediate-Re iLES stage ("L2.5") in B5 as a cheap step before RANS, and strengthens option A's paper (methodology robustness). Does not touch option B's need for an attached-regime evaluator and validation data. |
| RE_BREAKS_AT_1 or _2 | The Re-80 finalist gain is a low-Re effect for this geometry. Option A should frame L1/L2 as a creeping-flow demonstration of the procedure. M4 should consider redefining the L1/L2 demo problem (B5: an attached-regime parent at Re_c about 1e3 in WaterLily, where laminar OpenFOAM still confirms) before investing in option B, so that the optimizer is exercised on physics closer to the target. |
| RE_BREAKS_AT_3 only | Transfer holds while the flow is attached in the mean and breaks when it separates; supports B5 constraining the operating point to the attached regime (as the 2026-10-24 review proposed for option B) and treats separation margin as a constraint. |
| RE_UNRESOLVED / RE_RESOLUTION_LIMITED | The cost of unsteady statistics or the leading-edge resolution is the limiting factor; feeds B6 (backend) and the EVAL-PT-01 numeric gate with measured numbers instead of estimates. |
| INCOMPLETE | Preserve; no inference. |

In all cases the ladder also delivers the unsteady-statistics contract (4.3) for reuse in any URANS/LES evaluator work under option B or C.

## 6. Proposed study outline

- **Name:** RE-01 (Reynolds ladder on registered v18 designs). Parent issue: #63; informs #66; no change to #64/#65.
- **Hypothesis (pre-registered):** H1, the finalist's same-phase downforce gain keeps its Re-80 sign at Re_L 250 and 800 on flow_32 and flow_48 (and on OpenFOAM V1 at 250) with retention 0.3-1.0; H2, the Re-80 ranking of the 8 non-control designs is preserved (tau >= 0.6) at Re_L 250 and 800; H3, at Re_L 2500 the gain is weakened or unresolved (exploratory label, not a pass condition); H4, the CRN variance-reduction ratio sigma_d/(sqrt(2) sigma_F) rises from 0.1-0.3 toward 1 as the flow becomes chaotic.
- **Re ladder:** Re_L 250, 800, 2500 (Re_c 381, 1219, 3810); optional descriptive Re_L 8000 on flow_96. Implemented by changing only `solver_viscosity = n/Re_L` (the case validator currently asserts n/80 and REYNOLDS = 80, so the contract needs a registered Re parameter; nothing else in the case changes).
- **Designs:** the 9 states of 3.6; all phi hashes already registered.
- **Grids and solvers:** WaterLily flow_32 (formal), flow_48 (4-state confirmation), flow_64 (parent + finalist at R2/R3), flow_96 (R4 only); OpenFOAM v2512 laminar simpleFoam V1/V2 at R1 (U3 pipeline, nu changed only), pimpleFoam V2 descriptive at R2.
- **Measurements:** time-weighted means over the registered window; batch-means SE and tau_int; spectra; drift; Poisson probe; cost per run; domain control at R3.
- **Decision rules:** 5.3. **Stopping:** 5.2. **Cost:** R1 7 GPU h + 40-50 CPU h; R1-R3 47 GPU h typical, 102 GPU h worst (capped at 90); schedule R1 WaterLily immediately, OpenFOAM after XV-01.
- **Claim ceiling:** Re-dependence of paired same-phase downforce and drag differences of pre-registered v18 designs in WaterLily implicit LES on non-converged grids, with laminar OpenFOAM confirmation at one rung; not physical downforce, not grid-independent, not an evaluator GO, not FSAE, not Re >= 1e4, not optimizer-selected at the new Re.
- **Process:** PROC-01 registration, one three-angle plan review, one source review, freeze before each rung; analysis written once; labels fail-closed.

## 7. What could not be verified

- Taira & Colonius 2009 regime map details (which AR/alpha are steady at Re 300) and any Re 100 results: paywalled; only the abstract was read. The "AR about 1 is steady at Re 300 for high alpha" reading is from memory and should be checked against the paper before it is written into a registration.
- The exact 2D Hopf onset Re for a flat plate at alpha 20 deg; the Floquet-study numbers (Re_w 160-234) are for 3D instability.
- The Correia et al. 2014 "320 %" Re sensitivity figure (secondhand in a review).
- Kaggle's 30 GPU h per week quota (community-reported, not in Kaggle's documentation).
- Actual GPU memory used by flow_48 (nvidia-smi dumps hold only the 15,360 MiB total); the 128 B/cell figure is from the WaterLily paper's H100 case.
- OpenFOAM RANS cost on the Apple M4/Rosetta host (no measurement exists; scaled from the laminar us-per-cell-iteration).
- The lift rms level of the stalled plate at Re_c 1e3-4e3 (the 10-20 % assumption drives the window estimates).
- Whether WaterLily 1.8.0 remains stable at Re_L 2500-8000 with the flux-limited QUICK scheme and tol 1e-4 Poisson on these grids (no project run exists above Re 80; a smoke run at R2 settings should precede freeze).
- Maertens & Weymouth 2015 test cases and error figures (landing pages returned 403); only the "up to Re 1e5, second-order" statement is confirmed through secondary sources.
- The sign convention of "reflex +16.1 mm" (trailing edge up or down) was not checked in the mode definitions; it does not affect any number here.

## 8. References

Repository (all under `/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1/`):
- `docs/STATE.md`; `docs/phase_plan.md` (entries 2026-10-23 FID-01 and 2026-10-31 SCREEN-01); `docs/roadmap_review_2026_10_24.md` 4.3, 4.5, 4.7, 6.1-6.5, 7; `docs/t20_summary_for_m4_2026_10_22.md`; `docs/eval_valid01_reference_audit_2026_10_22.md`; `docs/local_openfoam_env_gate_2026_10_20.md`; `docs/fid01_registration_2026_10_21.md` 5-6; `docs/evidence/v18_genesis_2026_10_19/README.md`; `docs/evidence/unc01_2026_10_20/analysis.md`; `docs/evidence/fid01_2026_10_21/analysis.md`; `docs/evidence/screen01_2026_10_30/{README.md,analysis.md,xv_handoff.json}`; `docs/evidence/screen01_2026_10_30/wl/kernel_output/screen01_f_f32a/states/*/flow_32.summary.json` and `screen01_f48_f48k13/states/*/flow_48.summary.json` (steps, walls, drift); `julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl`; `scripts/waterlily_w4_v16_sensitivity_job.jl` (T_END 120, BURN_IN 80); `src/cfd_sdf/grid02_contract.py` (dims, nu = n/80); `~/.julia/packages/WaterLily/4Wr0g/src/Flow.jl` (CFL rule) and `MultiLevelPoisson.jl` (tol 1e-4, itmx 32); GitHub issues #66, #67, #69 (`gh issue view`).

Literature:
- Weymouth, G. D. & Font, B. (2025). WaterLily.jl: A differentiable and backend-agnostic Julia solver for incompressible viscous flow around dynamic bodies. Computer Physics Communications 315, 109748. arXiv:2407.16032. https://arxiv.org/html/2407.16032v3
- Maertens, A. P. & Weymouth, G. D. (2015). Accurate Cartesian-grid simulations of near-body flows at intermediate Reynolds numbers. CMAME 283, 106-129. https://doi.org/10.1016/j.cma.2014.09.007 (confirmed via https://research.tudelft.nl/en/publications/accurate-cartesian-grid-simulations-of-near-body-flows-at-interme)
- Boundary layer flow dynamics of propulsive flapping foils with increasing Reynolds numbers (2025), arXiv:2508.09590 (BDIM, Table 2 resolutions at Re 1e4-1e6). https://arxiv.org/html/2508.09590
- Taira, K. & Colonius, T. (2009). Three-dimensional flows around low-aspect-ratio flat-plate wings at low Reynolds numbers. J. Fluid Mech. 623, 187-207. https://doi.org/10.1017/S0022112008005314
- Yang, D., Pettersen, B., Andersson, H. I. & Narasimhamurthy, V. D. (2012). Vortex shedding in flow past an inclined flat plate at high incidence. Phys. Fluids 24, 084103. https://doi.org/10.1063/1.4744982 ; Yang, D., Narasimhamurthy, V. D., Pettersen, B. & Andersson, H. I. (2012). Three-dimensional wake transition behind an inclined flat plate. Phys. Fluids 24, 094107. https://doi.org/10.1063/1.4753942
- Floquet stability analysis of the wake of an inclined flat plate (3D onset Re_w 159.7-234.2 for alpha 20-30 deg). https://ouci.dntb.gov.ua/works/4E8xyRV7
- Brunton, S. L. et al. (2011). Unsteady aerodynamic models for separated flow past a flat plate at Re = 100 (Hopf at alpha about 28 deg). APS DFD abstract. https://archive.aps.org/dfd/2011/g23/1
- Breuer, M. & Jovicic, N. (2001). Separated flow around a flat plate at high incidence: an LES investigation. J. Turbulence 2, N18. https://openhsu.ub.hsu-hh.de/handle/10.24405/9135
- Ananda, G. K., Sukumar, P. P. & Selig, M. S. (2015). Measured aerodynamic characteristics of wings at low Reynolds numbers. Aerospace Science and Technology 42, 392-406. https://doi.org/10.1016/j.ast.2014.11.016 (PDF: https://m-selig.web.engr.illinois.edu/pubs/AnandaSukumarSelig-2015-AeroSciTech-LowReWings.pdf)
- Pelletier, A. & Mueller, T. J. (2000). Low Reynolds number aerodynamics of low-aspect-ratio, thin/flat/cambered-plate wings. J. Aircraft 37(5), 825-832. https://doi.org/10.2514/2.2676
- Optimal airfoils in the intermediate Reynolds number range (2026). arXiv:2605.19468 (optimal camber vs Re 1-3000). https://arxiv.org/html/2605.19468v1
- Srinath, D. N. & Mittal, S. (2009). Optimal airfoil shapes for low Reynolds number flows. Int. J. Numer. Meth. Fluids 61, 355-381. https://doi.org/10.1002/fld.1960 ; Srinath, D. N., Mittal, S. & Manek, V. (2009). Multi-point shape optimization of airfoils at low Reynolds numbers. CMES 51(2), 169-188.
- Roberts, L. S., Finnis, M. V. & Knowles, K. (2017). Forcing boundary-layer transition on a single-element wing in ground effect. J. Fluids Eng. 139. https://dspace.lib.cranfield.ac.uk/handle/1826/12155 ; Scale effects on a single-element inverted wing in ground effect. Aeronautical Journal. https://www.cambridge.org/core/journals/aeronautical-journal/article/scale-effects-on-a-singleelement-inverted-wing-in-ground-effect/A508D9BD915495561136858B553EC856
- Zhou, Overmars & Westerweel (2026). An accelerating inverted wing with ground effect: downforce measurement and reconstruction. Exp. Fluids 67(6), 75. https://doi.org/10.1007/s00348-026-04191-5 ; TU Delft record https://repository.tudelft.nl/record/uuid:ffc71074-be68-4b75-8610-60c6b523dded
- He, W. et al. (Liverpool). Stability of flow over an airfoil near a stationary or moving ground at Re 300-1000, alpha 20 deg. https://livrepository.liverpool.ac.uk/id/eprint/3032233
- Russo, S. & Luchini, P. (2017). A fast algorithm for the estimation of statistical error in DNS (or experimental) time averages. J. Comput. Phys. 347, 328-340. https://doi.org/10.1016/j.jcp.2017.07.005 ; Boxho et al. (2024), Flow Turbulence Combust., https://orbi.uliege.be/handle/2268/320960 ; A framework for initial transient detection and statistical assessment of convergence in CFD simulations (2025), arXiv:2511.22618
- LES at Re 3900: averaging over 25-100 shedding cycles. https://aminer.org/pub/5d9ed5ee47c8f76646fe0e19/numerical-simulation-of-flow-with-large-eddy-simulation-at-re-a-study
- Leading-edge separation bubble Re dependence (Ota et al. 1981; Li & Djilali 1995; Kazeminejad et al.; Samson et al.) via https://link.springer.com/article/10.1007/s00348-020-03039-w and https://www.jafmonline.net/article_1613_aaebcd9d472a96d27279056c1feca110.pdf
- FSAE Reynolds numbers: NTNU master's thesis (Re_c 5.45e5-6e5) https://ntnuopen.ntnu.no/ntnu-xmlui/handle/11250/235763 ; Imperial Front Wing LES at Re 2.2e5 https://www.nektar.info/?p=3520 ; Grabis & Agarwal FSAE wing (0.33 m chord) https://core.ac.uk/download/233235638.pdf
- Kaggle quota reports: https://gpuperhour.com/blog/free-cloud-gpus-and-credits ; https://huggingface-proxy.pages.dev/datasets/John6666/knowledge_base_md_for_rag_1/blob/93babea0b1c303124af8c062c459fbceea4c3208/kaggle_20251121.md
- OpenFOAM localEuler (LTS) documentation: https://doc.openfoam.com/2306/tools/processing/numerics/schemes/time/rtm/localEuler/

Computation script: `/private/tmp/claude-501/-Users-sota-projects-FomulaTMU-CFD2026-09--claude-worktrees-github-local-status-review-66bea1/f57b46f8-138c-4885-926c-e3f062eb44c3/scratchpad/calc/re_ladder.py` (inputs: SCREEN-01 kernel summaries, FID-01 5.3 costs, WaterLily CFL rule).
