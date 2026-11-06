# Brief C report: full-vehicle RANS validity, validation data, unsteady gradients

(sonnet research agent, 2026-11-01, verbatim; "unverified" = abstract/snippet only; "inference" = agent derivation)

## 1. Full-car steady-RANS fidelity

| Region / quantity | Steady-RANS status | Evidence |
|---|---|---|
| Rear diffuser interior, undertray suction | Converges; trends credible; magnitude biased: CFD suction exceeds on-track static pressure by roughly 10-15 % on average, individual taps up to ~35 % (table extraction garbled; approximate). Tufts vs CFD correlate "very well" in the diffuser interior. | R2 (primary, half-car steady RANS); R1 |
| Rear wing main elements, outer endplates | Trends good; separation on the inner endplate and supports over-predicted. | R1 |
| Front wing, wide span, moderate h/c | Converges; sensitive to transition modelling; a gamma-transition model gave spurious pressure-side separation and was dropped. | R1 |
| Front wing, inverted, h/c below ~0.15 | Steady RANS does not converge ("inherent unsteadiness"). Vogt: steady RSM at Re 458,800, alpha 6 deg, lowest converged h/c 0.15; 0.10, 0.05, 0.03 failed. Agrees with the project's 0.134 and 0.09. | R3 (primary) |
| Wheel wakes, wing-vortex/wheel interaction | Inherently unsteady. IFW-W: wheel CL 0.310 +/- 0.024, CD 0.382 +/- 0.013; isolated wheel not statistically converged after 41 convective units (std >= 5 %); main wing vortex "bursts on interacting with the wheel"; Lombard: RANS and DES "ill-suited". | R11 (arXiv 2503.03035); R11b |
| Wake behind the wheel entering the diffuser flat plates | Not interpretable (tufts show 3D motion from "severe turbulence"). | R1 |
| Integral downforce | Poor to modest in road-car references. Ford DrivAer DES: CD up to +10 %, front lift under-predicted by up to 250 %. First DrivAer workshop (53 data sets, 9 groups): hybrid RANS-LES smaller spread than RANS; front lift systematically under-predicted. | R12, R13 |

Reference-class errors:
- FSAE 1/3-scale car (Pacheco et al., SST, 13.7 M polyhedral cells, y+ <= 5, ~17.5 h per case) [R1]: numerical error 5.8 % CL, 4.3 % CD; uncertainties "did not enable a full quantitative evaluation"; trends captured except pitching-moment vs ride height; tunnel had fixed ground plate and static wheels, Re limited (25 vs 45 m/s); DRS effect tunnel vs CFD downforce ~-44 vs -42 %, drag ~-62 vs -45 % (verify sign artefact).
- Stuttgart full-size, moving ground, rotating front wheels: efficiency within 3 % of transient DES and 7 % of time-averaged DES (as quoted in R1).
- TU Wien half-car steady RANS (Star-CCM+, k-omega) [R2]: mesh study 19-163 M cells, ClA 3.81-5.20 m2, Richardson 5.15; design-phase 33 mm base ~34 M cells ClA 4.72 (~8 % low); URANS check of the front-tyre wake similar; y+ 30-100 bodywork, ~1 wings; thesis concludes CFD magnitude exceeds reality.
- Wheel treatment and moving ground: on DrivAer, moving wall, MRF and sliding mesh change drag little but lift and ventilation drag a lot (SAE 2018-01-0728, unverified) [R15]; AutoCFD4 used static wheels and floor.
- Mesh and y+: Ford found mesh strategy matters less than solver, turbulence model and DES formulation [R12].
- Mahon & Zhang: SST better on surface pressure, realizable k-eps better on wake [R4].
- Older FSAE work (Wordley & Saunders; Doddegowda "CL within 10 %, CD poorly predicted") unverified. No 2020-2026 FSAE paper with a quantified full-car downforce error with uncertainty other than R1 and R2.

## 2. Validation data

| Dataset | Content | Open? | Use |
|---|---|---|---|
| Zerihan & Zhang (J. Aircraft 37(6) 2000; thesis 2001), Tyrrell 026 | forces and flow field; downforce drops below h/c ~0.1 | not retrievable (403); Re and uncertainty unverified | trends only |
| Zhou, Overmars, Westerweel, Exp. Fluids 67(6):75, 2026 — exists [R5] | Tyrrell 026, span 550 mm, chord 110.8 mm, alpha 6.6 deg, Re_c 5.5e4 (water, inferred); H/C 0.054-1.40; accelerating start + steady phase; PIV impulse reconstruction; steady optimum H/C 0.153; ~5 Hz force oscillation | on request only; no force uncertainty; no CFD | unsteady/transient low-Re; peak height Re-dependent (0.153 vs ~0.1) |
| Mahon & Zhang 2005 [R4] | RANS vs experiment, surface pressure and wake | paper | 2D benchmark |
| Cranfield: Correia 2014 [R9]; Roberts et al. 2016 [R6, R8]; Roberts 2019 [R7] | 3D wings 50 % scale, moving ground, 2.7 x 1.7 m tunnel; single element up to 320 % downforce and 35 % drag change for delta Re_c 0.81e5; multi-element vs F1 wing < 6 %; k-kL-omega vs SST "substantial improvement" (unverified) | theses probably open (403) | Re and transition sensitivity |
| Wing-wheel: Heyder-Bruckner 2011 [R10]; Pegrum 2006; Diasinos & Gatto 2008; Zhang & van den Berg 2009 | wing-wheel vortex interaction | Heyder-Bruckner on Southampton ePrints | where RANS fails |
| Imperial Front Wing [R11] | open geometry; PIV at Re 2.2e5, h/c 0.36; CL -5.540, CD 0.575; 2026 volumetric-PTV rolling-road campaign (arXiv 2606.14342, Re 74,896) described as a benchmark, no data DOI | geometry open per nektar.info; data unverified | wing + wheel, 3D |
| DrivAer, AutoCFD [R13] | road-car reference; static wheels and floor in AutoCFD4 | DrivAerML CFD CC-BY-SA [R14] | full-car bias |
| FSAE datasets | R1 three-run SD; R2 61-point rake and 8 taps | R2 thesis public; R1 data not open | local checks |

## 3. Gradients in unsteady regimes

| Method | Cost/behaviour | Limits | Evidence |
|---|---|---|---|
| Windowed unsteady adjoint | >= 10x a steady adjoint plus per-step storage | perturbations grow exponentially | R20 |
| Ensemble adjoint (Lea et al.) | ~10 % accuracy on Lorenz-63 | unlikely reliable for complex systems | R16 |
| LSS | >= 500,000 work units, 4-5 orders over the CFD solve (2D inviscid NACA0012 at 90 deg, 2,218 points, 6,500 cores, 81 GB) | not practical | R18, R17 |
| NILSS/NILSAS | cost independent of parameter count; backward step, Lorenz, Re 525 cylinder | cylinder "not uniformly hyperbolic"; nothing on wall-bounded high-Re vehicles | R19 |
| Viscosity-stabilised adjoint | turbine-vane LES; "10-20 %" error (unverified) | unknown | R21 |
| URANS windowing | more robust for periodic flows (SU2) | periodic only | R26 |
| FD/ensemble with CRN | no ground-effect or vehicle study found | unquantified | R21 |

Steady adjoint of a time-averaged field: Petrocchi & Barakos: adjoint and FD agree except beyond buffet onset [R23]. Fidkowski (Re 1e4 airfoil) [R22]: steady-RANS lift-vs-camber gradient trend disagrees with the time-averaged unsteady result; unsteady lift 40-60 % above steady; fix is FIML (steady RANS corrected on unsteady means with an adjoint including the correction).

PTC/LTS: Dicholkar (DTU 2022) [R24]: on a massively separated bluff body the standard RANS solver stalls in a limit cycle and optimisation from averaged gradients barely moves; a "deep convergence" solver gives accurate adjoint gradients and reaches the reference optimum. Christianson 1994 [R25]: adjoint of a fixed-point iteration converges at least as fast as the primal, assuming an attractive fixed point. Inference: where no physical steady state exists (h/c < 0.15), PTC/LTS yields an unphysical or non-existent fixed point whose derivative is not the sensitivity of the time mean.

## 4. Experimental validation of an optimised car

| Method | Gives | Uncertainty |
|---|---|---|
| Coast-down (SAE J2263) | CdA only | 5.3-7.8 % below tunnel (FIAT, summary); 9.2 % vs constant speed on a truck; rolling resistance dominates |
| Constant speed + ride-height/damper potentiometers | downforce proxy | dive/squat corrupt; noisy for small deltas; no published uncertainty |
| Pushrod strain gauges | axle loads | FSAE teams use them; no error figures |
| Pressure taps / aero rake | local pressure | TU Wien 61-point rake and 8 taps, local agreement only |
| 1/3-scale model + balance | trends | cross-talk 6.9 % and 1.7 %; three-run SD; CFD error 4-6 %; Re mismatch |

Cost proxies (unverified): Embry-Riddle $600/h; Washington KWT $500-860/h; Texas A&M $5,000 per setup day. TU Wien: +10 % downforce ~ -1 % lap time; mass about twice as sensitive. A 1-5 % downforce gain ~ 0.1-0.5 % lap time (inference), smaller than every absolute error above; only paired A/B runs on the same day, mesh and model can resolve it; sign-level agreement is the realistic acceptance criterion (inference).

## 5. Rules (PDFs read)

| Item | FSAE 2025 v1.0 = 2026 v1.0 (T.7) [R27] | FSG 2026 v1.0 (T8, T2) [R28] | FSG 2027 v1.0 |
|---|---|---|---|
| Length | <= 700 mm forward of front tyres, 250 mm aft of rear tyres (T.7.5) | same (T 8.2.3) | same |
| Height | Rear Aerodynamic Zone <= 1200 mm; elsewhere <= 500 mm; forward of the front axle and outboard of the inside-of-front-tyre planes <= 250 mm (T.7.7.1) | forward of the head-restraint plane < 500 mm; ahead of the front axle and outboard of the front tyre's inboard point < 250 mm; rearward of the head-restraint plane < 1.1 m | forward of the front tyre LE < 350 mm; rearward of the head-restraint plane < 1100 mm; otherwise below the plane through the tyre tops |
| Width | forward of the front axle inboard of the outside-of-front-tyre planes; between axles inboard of the line joining the outer tyre surfaces; rearward within the Rear Aerodynamic Zone (T.7.6) | below 500 mm aft of the front axle not wider than the outboard tyre planes; above 500 mm not outboard of the inboard rear tyre point | 150 mm inboard of the rear tyre between tyre top and 700 mm; 700-1100 mm not outboard of the rear tyre |
| Ground clearance | no numeric floor; no ground contact in dynamic events (V.1.4.1); <= 90 mm below the lower side impact structure, should be <= 75 mm (V.1.4.2); skirts prohibited | 30 mm static minimum with driver (T 2.2.1); skirts prohibited | not read |
| Edge radii | forward-facing edges of wings, endplates, undertrays: 5 mm horizontal, 3 mm vertical (T.7.1.4); forward bodywork edges 38 mm (T.7.2.4) | 3 mm forward-facing, 1 mm other; bodywork ahead of the front wheels 38 mm | not read |
| Measurement | wheels straight, no driver (T.7.3.1) | any suspension setup, with or without driver | same |
| Stiffness | ~200 N, <= 25 mm loaded, < 5 mm permanent (IN.6.2.2) | 200 N over 225 cm2 <= 10 mm; 50 N any direction <= 25 mm (T 8.3) | same |
| Other | powered ground effect prohibited (T.7.1.2); wing angle adjustable after inspection, location not (IN.16.2) | | |

FSAE Japan 2026 follows Formula SAE Rules 2026 plus Participation Rules (3rd ed.) and Local Rules (4th ed., 2026-06-16); no aero amendments found [R29]. FSAE-A 2026 Local Addendum v1.4.2: no aero change. No FSAE 2027 / FSAE Japan 2027 rules found. SDF mapping: static boxes and half-spaces referenced to tyre planes and the head-restraint plane; make the envelope a switchable rule set. Under FSG, 30 mm clearance on a 0.15-0.25 m chord is h/c ~0.12-0.2 (inference): the lowest legal FSG wing sits at the non-convergence boundary of R3.

## Recommendation (agent)

Regions a steady-RANS adjoint can credibly optimise: attached rear-wing main elements and outer endplates; front wing at h/c >= ~0.2; undertray and diffuser interior and main suction surface (ranking/trend only, suction over-predicted 10-15 %); bulk bodywork pressure drag.
Freeze, mask or constrain: wheels and wheel wake, wing-vortex/wheel interaction; front wing at h/c < 0.15 (lower h/c bound as an SDF constraint); diffuser flat plates behind the wheel; rear-wing inner endplate and supports.
Gradient policy: deep convergence on every design (Dicholkar); adjoint vs FD on converged cases only; reject designs whose force history oscillates or residual stalls; where unsteadiness is unavoidable, no LSS; FIML-style steady correction trained on time-averaged DES, or window-regularised URANS if periodic.
Validation ladder: rung 0 numerics (grid, iteration, adjoint vs FD); rung 1 2D section (Tyrrell trends, Mahon & Zhang, Vogt, Zhou 2026; pass = force-reduction onset and peak-height shift, not absolutes); rung 2 3D wing (Cranfield 50 % data; Imperial Front Wing geometry and PIV); rung 3 wing + wheel (Heyder-Bruckner, Pegrum, IFW-W; calibrate the exclusion zone); rung 4 full-car bias (DrivAer, front-lift error known); rung 5 FSAE (Pacheco trends, TU Wien taps and rake, own 1/3-scale balance model and paired on-track A/B).
Top 5 risks: (1) gradient validity in unsteady zones, optimiser moves into low h/c where the model is wrong; (2) model-form bias exceeds the gain (4-6 % numerical, 10-15 % local pressure, DrivAer front lift), steady-vs-unsteady gradient sign flip documented; (3) Re and transition (320 % per delta Re_c 0.81e5; transition model choice); (4) wheel and ground BCs (only FSAE tunnel validation used static wheels on a fixed plate; wheel wake not converged); (5) unverifiable gains and rule drift (no open FSAE dataset with an uncertainty budget; FSG 2027 envelope changed).

## References
R1 Pacheco, Marta, Eca, Proc IMechE D 238(14):4347-4363 (2024), DOI 10.1177/09544070231203076; R2 Kirchberger, TU Wien MSc thesis 2023 (repositum.tuwien.at); R3 Vogt, Barber, Leonardi, 16th AFMC 2007; R4 Mahon & Zhang, J. Fluids Eng. 127(2):290-298 (2005); R5 Zhou, Overmars, Westerweel, Exp. Fluids 67(6):75 (2026), DOI 10.1007/s00348-026-04191-5; R6 Roberts, Finnis, Knowles, J. Fluids Eng. 138(9):091106 (2016); R7 Roberts et al., Proc IMechE D (2019) DOI 10.1177/0954407018804007; R8 Roberts, Correia, Finnis, Knowles, Proc IMechE D 230:841-854 (2016); R9 Correia et al., Aeronaut. J. 118 (2014); R10 Heyder-Bruckner PhD Southampton 2011 (eprints 207263); R11 Imperial Front Wing arXiv 2503.03035, arXiv 2606.14342, nektar.info; R11b Lombard PhD Imperial; R12 Lewington et al., SAE 2022-01-0900; R13 Ashton & van Noordt, SAE Int. J. Commer. Veh. 16(1); Ashton et al., Comput. Fluids 128:1-15 (2016); R14 DrivAerML arXiv 2408.11969; R15 SAE 2018-01-0728; R16 Lea, Allen, Haine, Tellus A 52(5) (2000); R17 Wang JCP 235 (2013); Wang, Hu, Blonigan JCP 267 (2014); R18 Blonigan, Wang, Nielsen, Diskin, NASA NTRS 20160007741; R19 Ni & Wang JCP 347 (2017); Ni & Talnikar arXiv 1801.08674; Ni JFM 2019; R20 Kenway, Mader, He, Martins, Prog. Aerosp. Sci. 2019; R21 Talnikar & Wang arXiv 2011.06744; R22 Fidkowski AST 2022; R23 Petrocchi & Barakos AST 126 (2022) 107664; R24 Dicholkar PhD DTU 2022 DOI 10.11581/dtu.00000240; R25 Christianson 1994; R26 arXiv 2412.00604; R27 Formula SAE Rules 2026 v1.0 / 2025 v1.0; R28 FS Rules 2026 v1.0, FS Rules 2027 v1.0; R29 FSAEJ 2026 rules index, FSAE-A Local Addendum v1.4.2.
Not verified at primary source: Wordley & Saunders and Doddegowda numbers, Zerihan Re and uncertainty, Correia's thesis, Pegrum's thesis, TU Delft DES full-car thesis, coast-down percentages, student wind-tunnel pricing.
