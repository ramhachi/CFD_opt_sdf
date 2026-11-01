# GEN-01 plan rev 0: strategy, physics and validation review (angle S)

(Opus reviewer, 2026-11-01, verbatim. Plan reviewed at commit 7bb2049e, SHA-256 7a1432c0...df63c.)

**Verdict: GO_AFTER_FIXES.** The architecture is the right one: body-fitted RANS, discrete adjoint as the primary gradient, filtered normal-displacement variables, constraints that keep the design where steady RANS holds, and fail-closed stages. But five things break the stages that rest on them:
- the regime map is imported from 2D evidence and contradicts the project's own T2-0d;
- the Imperial Front Wing cannot test the contract the plan registers against it;
- the experimental endpoint has no power analysis and is measured last;
- ADJ-00 selects a toolchain without checking the vehicle features it must support;
- the checkpoint loop through phi would destroy thin trailing edges.

## Findings

**S1 (P1). §0, §1.2 (T2-0c/d row), §3.6, §6.4, §7 UNS-G: the h/c lower bound rests on 2D steady-solver failures, not on established 3D physics.**
- Vogt 2007 (verified, full text) is 2D, RSM, SIMPLEC, Re 458,800, alpha 6 deg. The inverted wing converged down to h/c 0.15 and failed at 0.10, 0.05 and 0.03. Nothing was run between 0.10 and 0.15.
- The project's registered T2-0d found that "the URANS settles to a steady state wherever the steady solver did not" (58 runs). Only h/c 0.09 at +1 deg still drifted.
- So at 0.134 a steady fixed point exists in the SA model. The failure was the SIMPLE solver's, not missing physics. The plan says the cause is "both" and that "no physical steady solution exists below 0.15". That is not what the record shows.
- Finite span and endplates in 3D are untested.
- FSAE 2026 (the rule set the plan picks) has no numeric ground clearance (V.1.4.1, verified). FSAE front wings plausibly run at h/c ~ 0.1-0.2 (recalled practice; check against the team CAD).
- Consequence: the a-priori h/c >= 0.2 in WING-3D-01 may optimise a wing at a ride height the car never runs at.

Fix: before registering WING-3D-01, compute the parent's operating h/c envelope (static, braking, cornering) from the team CAD; run a 3D parent scan across that envelope: steady, pseudo-transient/LTS (EVAL-PT-01) and short URANS; separate two gates: (a) a model fixed point exists, so the gradient is defined; (b) the model is valid against data, which sets the claim scope; correct the §0, §1.2 and §7 wording. Confidence: high on the facts, medium on the typical FSAE h/c.

**S2 (P1). §3.8, §6.4, §6.8 rung 2: the Imperial Front Wing has no data for the registered contract.** Verified from Buscariolo et al. (arXiv 1909.06701; JWEIA 2022): 1:2 scale on a rolling road; one configuration only: h/c 0.36, pitch 1.094 deg, Re 2.2e5 (c = 250 mm, 25 m/s), natural transition, no trip; time-resolved PIV on 5 iso-X planes, y<0 endplate side only; oil flow at 15 m/s (Re 1.32e5); no measured forces and no surface pressures. The CL -5.54 / CD 0.575 quoted in research C §2 are NM54 simulation values. The plan's contract ("vortex position and surface-pressure trends", "signs and bands of the slopes against h/c and incidence") therefore has nothing to test against.

Fix: re-scope IFW to a transition/separation-line and vortex-trajectory discriminator for choosing the turbulence/transition model (descriptive or narrowly gated). Get slope data from (i) your own early tunnel test of the parent wing at 2-3 ride heights x 2-3 flap angles; (ii) the UIUC S1223 polars at Re 2e5 (Selig & Guglielmo, J. Aircraft 34(1) 1997, verified to exist) for 2D transition discrimination at FSAE Re; (iii) Pegrum 2006 ride-height data, if obtainable (unverified). Make EVAL-3D-00 its own registered stage; it needs primal runs only, so it can run in parallel with ADJ-00, before any WING-3D-01 optimisation spend. Otherwise the plan repeats T2-0's REFERENCE_INADEQUATE outcome.

**S3 (P1). §6.7 VAL-X: sign-level acceptance is unpowered and comes 12 months too late.**
- A sign match happens 50 % of the time by chance. Pacheco et al. 2024 (verified) report a small delta where tunnel and CFD trends disagreed in sign (bullhorns, downforce).
- On track: an FSAE car at 15 m/s with ClA ~ 4 m2 makes ~540 N of downforce, so a 2 % gain is ~11 N on ~2.9 kN of static weight. q scales with v^2, so a 2 m/s head or tail wind moves q by +28 / -25 %. Pushrod gauges also mix in load transfer.

Fix: add a VAL-0 in months 1-3: measure the repeatability sigma_rep of the chosen methods on the current car. Pre-register a power calculation, n ~ 15.7 (sigma/delta)^2 paired runs (at sigma/delta = 2 about 63 runs). Put load cells on the mounts of the modified part. Run out-and-back pairs to cancel wind. Test at least 3 variants (optimised, baseline, and a predicted-neutral or negative decoy); register the predicted ranking and magnitude intervals before manufacture. 3D-scan the as-built parts and re-run CFD on the scans. Budget the experiment now. A publishable claim needs a V&V-20-style comparison on the delta (E = S_delta - D_delta against u_val) plus a comparator (S8).

**S4 (P1). §4.2 ADJ-00: accuracy cases only, no capability matrix, and circular thresholds.**
- The vehicle needs, inside the adjoint: porous radiator zones (sidepods); rotating-wall or MRF wheels; moving ground; symmetry; per-patch responses (balance); a wall-function adjoint at y+ 30-100; possibly a transition-model adjoint (S2, S11); node-based surface variables with a filter. Research A says DAFoam's documented path is FFD and the node-based route is undocumented.
- The gradient-contract numbers are "provisional, decided by measurement in ADJ-00", yet they are the selection rule. Selection is then made on its own data.
- Requiring both NACA0012 and Ahmed 25 deg to pass lets an Ahmed slant failure send the whole programme to the fallback, even though the wing stages come first.

Fix: make each capability a pass/fail item; freeze the thresholds before any run; gate the wing stages on cases (1) and (3) plus a coarse 3D wing; let Ahmed gate bodywork (CAR-01) only.

**S5 (P1). §2 checkpoint loop, §1.3 role 4, §3.2 "h ~ r_c/4", §6.2: thin features cannot survive a trip through phi.**
- With r_c = 10-50 mm, h is 2.5-12.5 mm. FSAE trailing edges (~1 mm), Gurney flaps and slot gaps cannot be represented at that spacing.
- "Rebuild phi from the surface -> geometry gate -> remesh" would therefore blunt the trailing edges.
- The plan then books the resulting force change as a "mesh difference" and subtracts it from the claimed gain, so geometry loss would be misread as mesh noise.

Fix (before GEOM-K1 is designed): make the explicit surface, with lineage, the canonical design; derive phi for constraints only. Alternatively, use a narrow-band sparse SDF with sharp-feature extraction at h <= TE thickness/2. Add GEOM-K1 tests on the team CAD: round-trip Hausdorff distance, trailing-edge thickness preservation, and one CFD run of round-tripped versus original surface with |delta J| < sigma_J.

**S6 (P2). §0 "without per-component parameterisation": per-component hand configuration is still there.** Configured by hand per component: radii r_c, design/fixed/forbidden masks, the frozen list, interference-mask widths calibrated on another car (IFW-W), separation-margin definitions, the h/c bound, operating points, CAD clean-up. Defensible (BMW did it too), but not "generic" until tested on a second geometry. Fix: declare all of these in ProblemSpec; derive the frozen regions automatically from local pressure/velocity RMS in a short URANS/DDES of the parent; add a genericity criterion: a second geometry goes through the same pipeline with no component-specific code.

**S7 (P2). §1.3: the SDF does less in the main line than the plan says.** Role 1 (composition) is unnecessary for snappyHexMesh, which takes several STLs. Role 3 (topology) is deferred to TOPO-G, which has no turbulent 3D precedent. Role 4 (canonical representation) is false at the stated h (S5). Messmer 2024's implicit Vertex Morphing is cited, but the working representation is explicit Vertex Morphing. The Hadamard argument holds only to first order, at fixed topology, for features larger than r_c. In effect the main line is industrial explicit Vertex Morphing, plus SDF constraints from fixed objects and the rules. That is the right engineering choice, but the user chose SDF for generality and should be told plainly. Fix: state this framing in §1.3 and §11; give TOPO-G a registered entry criterion; note that under adjoint the cost does not depend on the number of variables, so §1.1 does not decide node-based versus auto-generated FFD/RBF or Laplace-Beltrami bases; compare them on their merits.

**S8 (P2). §1.1, §4.2: the low-dimensional FD route is affordable as a comparator, not only as a fallback.** With K = 30 at WING-3D-01: 30 iterations x 61.5 primals x 42-100 core-h ~ 77k-185k core-h ~ USD 2.9k-7.0k on-demand, or 1.2k-2.8k at spot. Within the stage budget, so "nothing except adjoint is affordable" is too strong at component scale. Fix: run an automatic Laplace-Beltrami K = 30 FD optimisation and a hand design by the team's aero lead as control arms in WING-3D-01, like SCREEN-01's OPT_BEATS_MANUAL/RANDOM. This is what makes the generic-system claim publishable.

**S9 (P2). §3.6: masking design variables does not mask sensitivity paths.** With whole-car J in CAR-01, the gradients for the front wing and floor run through the tyre-wake and diffuser regions the plan flags as unreliable. Fix: component-local objectives in the early stages; report the adjoint-weighted share of sensitivity passing through flagged cells; before CAR-01, pre-register a check on the parent's first adjoint: the share of downforce and of the H1 sensitivity norm on designable surfaces; if too small, re-scope. Confirm the final CAR-01 delta with DDES, not descriptive URANS only.

**S10 (P2). §3.7, §6.6: operating points and objective.** Yaw is listed, but §6.4/§6.6 use half models; yaw and steering need the full car: ~5e7 cells, ~5.3 TiB with DAFoam's explicit Jacobian, 7-8 nodes; CAR-01's budget does not cover this. Speed (Re) is missing: Pacheco's car averages about 15 m/s in competition (verified), giving main-element Re ~ 2-3e5 and flaps ~ 1e5; §3.8's "3e5-6e5" is too high. "Maximise downforce with drag <= parent" is not derived from lap time or EV endurance energy. Fix: price full-model yaw points, add a low-speed point, take objective weights from the team's lap-time simulation.

**S11 (P2). §3.8: fully turbulent SA/SST at Re 1e5-4e5 is the largest physics risk for the wings.** The "other model" check in WING-3D-01 must include a transition model. Option: specify tripped manufactured parts so the CFD's transition assumption holds physically; record the trade.

**S12 (P2). §6.0, §6.3: stage order.** LOOP-2D-01's 2D gmsh chain is throwaway (not the 3D snappyHexMesh/layers/IDWarp chain), and ADJ-00 case (3) already covers the section. Replace it with an exploratory LOOP-3D-00 on a coarse 3D wing with endplates using the real pipeline. Optimising the front wing without tyres optimises the wrong problem. Consider making the rear wing the WING-3D-01 target (out of ground effect, no tyre interaction, already a "design" region in §3.6); move the front wing into WW-01 with the tyre.

**S13 (P2). §3.9, §11(c): the relationship to the Re-80 line is incoherent.** GEN-01 uses neither WaterLily nor any Re-80 result. RE-01 (Re_c <= 3.8e3) and BRIDGE-2D-00 have no consumer in GEN-01. GEN-01 is M4 option C (new 3D evaluator, new solver, new backend), not option B, and it reverses principle R5. Recommendation: keep XV-01 (closes L2 for the methodology paper, local CPU); ask the user explicitly whether to stop or park RE-01; record GEN-01 as M4-C now rather than "after XV-01" while ADJ-00 money is already being spent; count review bandwidth (six more registered studies, each with a three-angle plan review and a source review) as the binding resource.

**S14 (P2). §3.9: v2512 is not an independent verification code.** DAFoam's OpenFOAM-AD fork comes from v2506, the same ESI lineage. Fix: verify with a different code (SU2, or a commercial solver if the team has a licence) and a different mesher for the "other mesh family".

**S15 (P2). §9 is missing these risks:** team design cycle (CAR-01 lands around Jul-Oct 2027, likely after the 2027 car's design freeze); CAD quality, IP and shareability (publication needs an open replication case; IFW is CC-BY 4.0); manufacturing tolerance and aeroelastic deflection; spot pre-emption of multi-day adjoint jobs; porous radiator and cooling-flow constraints for the sidepods; the suspension arms are never placed in §3.6 (likely inside the frozen wheel region; say so).

**S16 (P3). Factual corrections:** §1.2 Work F row: "refining the source grid brought all directions close to 1 (P6)" is the fixed-grid Brinkman line (P6), not Work F. Work F's FD plateaus were stable; in D3, switching upwind to linearUpwind reshuffled which directions passed (seed2026 downforce 0.88->1.03; drag seed11 1.04->0.85): the signature of a continuous/discrete inconsistency, not FD noise. Pacheco's 5.8 % / 4.3 % are mesh-convergence uncertainties for a 1/3-scale tunnel model at 25 m/s, not absolute errors for "an FSAE-class car". The Vogt threshold is somewhere in (0.10, 0.15], not "below 0.15". §3.6 argues with FSG's 30 mm while choosing FSAE 2026. T.7.3.1 measures the envelope with wheels straight and no driver, so GEOM-K1 must check the envelope in that attitude, not in the CFD attitude.

## What must not be lost in revision
- Body-fitted RANS and discrete adjoint as primary; Brinkman and fixed-grid AD kept out of the loop.
- Regime-aware constraints, convergence certificates, and non-convergence recorded as a result rather than retried.
- Claims made on paired differences, retention and sign across mesh families and models, never on absolutes.
- sigma_J measured before every campaign, with the 3 sigma_J and rho acceptance rule.
- r_c fixed at registration, with results always reported with their r_c.
- Morphing inside a campaign and logged remeshing at checkpoints.
- A single cloud node type with a bitwise rerun check.
- Mesh-movement terms required in the gradient.
- An explicit statement that no full-car experimental precedent exists.

## Claims checked externally
- Imperial Front Wing: CAD at DOI 10.14469/hpc/6049 (CC-BY 4.0); 1:2 model, rolling road, h/c 0.36 only, Re 2.2e5, no trip, PIV on 5 planes (one side), oil flow at Re 1.32e5, no measured forces or pressures; CL/CD figures are simulation values. Verified (full text).
- Vogt, Barber, Leonardi 2007 (16th AFMC): 2D steady RANS, RSM, Re 458,800, alpha 6 deg; converged to 0.15; 0.10, 0.05, 0.03 failed. Verified.
- Pacheco, Marta, Eca, Proc IMechE D 238(14):4347-4363 (2024): SST, 13.7M cells, 17.5 h per run, 5.8 % CL and 4.3 % CD from mesh convergence; 1/3 scale at 25 m/s vs 45 m/s needed; balance crosstalk 6.9 % / 1.7 %; one sign-disagreeing small delta. Verified.
- FSAE Rules 2026 v1.0 (10 Sept 2025), T.7: 700/250 mm (T.7.5); 1200/500/250 mm heights (T.7.7.1); 5/3 mm edge radii (T.7.1.4); 38 mm bodywork radii (T.7.2.4); measured with wheels straight and no driver; no numeric ground clearance (V.1.4.1). Verified.
- FSG 2026 T 2.2.1: 30 mm static minimum including the driver. Verified.
- Carter 1991 (SIAM J. Numer. Anal. 28(1):251-265): convergence holds if the relative gradient error stays below a constant; the ">= 0.5 still converged" figure is from the companion numerical study. Partially verified (abstracts).
- Selig & Guglielmo 1997 S1223 data at Re 2e5: verified to exist.
