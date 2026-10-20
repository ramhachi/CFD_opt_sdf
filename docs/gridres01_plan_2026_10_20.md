# GRIDRES-01 plan: which grid's downforce response along the OPT-01 direction do finer grids support?

Date: 2026-10-20. Follows #30 (OPT-01 v1, `OPT01_V1_REJECT`, record `docs/issues/30_opt01_v1_result_2026_10_15.md`) and GRID-01 (#26 closure).
User instruction (2026-10-20): 「Aで進めて」 (option A of the 2026-10-15 report: a grid study of the response directions). Evidence class (target):
bounded multi-grid actual-primal response measurement at one parent along one direction, Re 80, Kaggle T4.

## Question

At the OPT-01 v1 parent (generation 1, `c9e12f62…`) along the frozen Stage B direction, flow_24 and flow_32 disagree: flow_24 downforce change is
+3.5e-6, −2.8e-5, −1.05e-4, −2.33e-4 N at +0.3125/+0.625/+0.9375/+1.25 mm while flow_32 is +1.34e-4, +2.75e-4, +3.85e-4, +4.68e-4 N; the
reverse probes show flow_24 is dominated by a negative even part (curvature) while flow_32 is nearly odd. Do two finer grids (flow_40, flow_48)
follow flow_32, follow flow_24, or neither? The answer decides whether the both-grid acceptance rule is rejecting good steps because flow_24
is under-resolved for this response, or protecting against a flow_32 artifact.

## Fixed inputs

- States (identical bytes to Stage B, hash-checked against `docs/evidence/opt01b_stage_b_2026_10_15/inventory.json`): parent, +0.3125, +0.625,
  +1.25 mm, −1.25 mm (5 states per grid). flow_24 and flow_32 values are the retained Stage B results (the solver is deterministic: same bytes,
  same settings; no rerun).
- New grids: `flow_40` (cells per reference length 40, spacing 0.02 m, 250×120×90) and `flow_48` (48, 0.016667 m, 300×144×108), built in the
  job script with the existing `V16W4Sensitivity.build_case` (no edit of `julia/CFDSDFWaterLily/src`, which earlier freezes pin), same domain,
  Re 80, window [80,120] tU/L, sampling and Candidate C operator settings as flow_24/flow_32 in the Stage B inventory; per-state timeout and kernel
  caps scaled to the measured flow_32 time (about 405 s/state) by cell count × step count (flow_40 about 1,000 s, flow_48 about 2,100 s per state).
- One kernel per new grid. Integrity: per-state phi hashes, Julia/Manifest pins as Stage B, a plain parent run per grid (no cross-grid byte
  identity is possible).

## Quantities

Per grid g ∈ {24, 32, 40, 48}: Δ_g(s) = F(s) − F(parent) for downforce and drag; odd part O_g = (Δ(+1.25) − Δ(−1.25))/2 and even part
E_g = (Δ(+1.25) + Δ(−1.25))/2. Floor 3e-5 N (the nominal LOWDIM floor; not a measured noise level on the new grids).

## Verdict (preregistered, downforce; drag reported)

- `FINE_FOLLOW_FLOW32`: Δ_40 and Δ_48 > +3e-5 N at both +0.625 and +1.25 mm, and the differences contract:
  |Δ_48 − Δ_40| < |Δ_40 − Δ_32| < |Δ_32 − Δ_24| at +1.25 mm.
- `FINE_FOLLOW_FLOW24`: Δ_40 and Δ_48 < −3e-5 N at +1.25 mm.
- `UNRESOLVED`: anything else (including sign agreement without contraction, or the two fine grids disagreeing).
- `INCOMPLETE`: any integrity failure.
Reported for every outcome: all Δ, odd and even parts per grid, ratios between successive grids, drag; wall time and memory per grid.

## Use of the outcome (not decided here)

FOLLOW_FLOW32 would support a GRID-01 amendment (acceptance on flow_32 plus a finer confirmation grid; flow_24 only for proposals) as a separate,
reviewed decision. FOLLOW_FLOW24 would make flow_32 the suspect and keep the both-grid rule. UNRESOLVED keeps the rule and says grid convergence of
this response is not established up to flow_48. Not claimed in any case: grid independence, physical or Stage V downforce, a gradient.

## Work (implementer: sonnet)

Copy-adapt the OPT-01 Stage B kernel/runner/freeze/analyzer pattern into `gridres01_*` modules (never edit frozen files); preregistration
(scripts, tests of the verdict function on synthetic tables, freeze) before submission; one submission per kernel; analysis `--check` + one
`--write`; post-run review; record; merge.

## Amendment 1 after the adversarial plan review (2026-10-20, before any code or run)

Review: SOUND_WITH_REQUIRED_CHANGES (sonnet subagent, read-only). Verified by the planner: `validate_w4_case` hard-codes n ∈ {16, 24, 32}
(`V16W4Sensitivity.jl:81`), and the quadratic fits below. These items override the sections above.

- **G1 Grid construction (was a blocker).** The new job builds the case with `V16W4Sensitivity.build_case("flow_40", 40, BASE_MAX_M, origin,
  0.025)` and validates **locally** (dims 250×120×90 / 300×144×108, solver_length = n, ν = n/80, origin, box) instead of calling the frozen
  `validate_w4_case`; it does not filter `w4_cases()`. No edit of `julia/CFDSDFWaterLily/src`.
- **G2 Sequential design and caps.** Step counts follow 1/dt = A + cν (flow_24 8,740, flow_32 13,549 → about 19,300 for flow_40, 26,000 for
  flow_48; about 0.9 ks and 2.0 ks per state). **Run flow_40 first**: parent, +0.3125, +0.625, +1.25, −1.25 mm (5 states, about 80 min;
  per-state timeout 1,800 s, aggregate cap 9,000 s, kernel timeout 21,600 s). **flow_48 runs only if the flow_40 verdict is AMBIGUOUS** (same 5 states,
  per-state timeout 3,600 s, kernel timeout 43,000 s or two kernels), preregistered now, frozen and reviewed separately before its submission.
- **G3 Primary quantities.** Per grid, fit Δ(s) = a·s + b·s² (no intercept) to the five-point set (four for flow_24/flow_32 retained plus the
  reverse states as retained; the same five step values on every grid) by least squares; also report the forward-only fit (+0.3125, +0.625,
  +1.25) that avoids the reverse states (whose crossing-slope failures are report-only probe failures) and the max fit residual. Retained fits:
  flow_24 a = 9.9e-5 N/mm, b = −2.28e-4 N/mm² (max residual 5e-6 N), flow_32 a = 4.75e-4, b = −7.6e-5 (8e-6 N). The grids agree in the sign
  of the slope and disagree in magnitude and curvature. **Capability** of a grid along this line: G_max = max over s ∈ (0, 1.25] mm of a·s + b·s²
  (the registered trust region): flow_24 1.1e-5 N (it cannot reach the 3e-5 N floor anywhere on the line), flow_32 5.3e-4 N.
- **G4 Verdict (downforce, preregistered).** Guard band 1e-5 N (the scale of the fit residuals, not a noise measurement):
  `FLOW40_SIDES_WITH_FLOW32` iff G_max(flow_40) > 4e-5 N; `FLOW40_SIDES_WITH_FLOW24` iff G_max(flow_40) < 2e-5 N; `AMBIGUOUS` otherwise (→ flow_48 branch,
  same rule applied to flow_48 and reported jointly). `INCOMPLETE` on integrity failure or a fit residual above 2e-5 N on any grid (the quadratic model
  does not hold). Reported, not gating: contraction ratios |a_40 − a_32| / |a_32 − a_24| and likewise for b (label `CONTRACTING` if both ≤ 0.6;
  `THIRD_VALUE` if flow_40 differs from both flow_24 and flow_32 by more than half their difference in a or b); acceptance emulation per tested step on
  flow_40 (Δdownforce > 3e-5 and Δdrag ≤ 0); drag a and b per grid (drag is not in the verdict because the observed binding constraint was
  downforce; the drag secants of the two grids are nearly unrelated and flow_32 small-step drag is inside the floor).
- **G5 Use of the outcome (reworded).** The direction was selected as the max-min of the flow_24/flow_32 predictions: a selected line, not a random
  draw. No GRID-01 amendment can rest on this result alone. SIDES_WITH_FLOW32 justifies the next step of broadening (the four Stage A basis
  directions at ±1.25 mm on flow_40, about 2.4 h) before any amendment; SIDES_WITH_FLOW24 keeps the both-grid rule and points at flow_32;
  AMBIGUOUS/flow_48 as above.
- **G6 Disclosures.** Non-blind (flow_24/flow_32 values and the quadratic structure are known). Lattice commensurability confound: the design
  lattice (0.025 m) equals the flow_32 spacing; flow_24 is coarser than the lattice, flow_40/48 finer; the sequence changes resolution and lattice
  alignment together, and any convergence is that of this interpolated-lattice body only. The 3e-5 N floor is nominal. Not claimed: grid
  independence, physical or Stage V downforce, a gradient, optimizer behaviour.
