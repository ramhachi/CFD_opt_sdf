# GRIDRES-01 result: the downforce response along the OPT-01 direction is not grid-resolved between flow_24 and flow_40 (2026-10-21)

Evidence class: bounded multi-grid actual-primal response measurement, one parent (OPT-01 v1 generation 1, `c9e12f62…`), one selected direction,
Re 80, Kaggle T4. Plan: [gridres01_plan_2026_10_20.md](../gridres01_plan_2026_10_20.md) (Amendments 1–2). User instruction 2026-10-20:
「Aで進めて」. Implementation, run and analysis by sonnet subagents; plan, reviews and record by Claude, not humans.

## Result

**Registered verdict: `FLOW40_SIDES_WITH_FLOW24`** (G_max(flow_40) = 0 N < 2e-5 N; `analyze_gridres01.py --check` reproduces it). Integrity
passed: the instrumented flow_24 and flow_32 parent reruns are byte-identical to the retained Stage B CSVs (the Poisson probe is passive), all
fits hold (max downforce residual 9.9e-6 N < 2e-5 N), SHA256SUMS 55/55.

| Grid | Δ +0.3125 | Δ +0.625 | Δ +1.25 | Δ −1.25 (N) | a (N/mm) | b (N/mm²) | G_max over (0, 1.25] mm |
| --- | --- | --- | --- | --- | --- | --- | --- |
| flow_24 | +3.5e-6 | −2.78e-5 | −2.33e-4 | −4.79e-4 | +9.8e-5 | −2.28e-4 | 1.05e-5 |
| flow_32 | +1.34e-4 | +2.75e-4 | +4.68e-4 | −7.10e-4 | +4.73e-4 | −7.7e-5 | 4.71e-4 |
| flow_40 | −1.45e-4 | −4.07e-4 | −1.305e-3 | −7.34e-4 | **−2.31e-4** | −6.53e-4 | 0 |

**What the verdict name does not say:** flow_40 does not reproduce flow_24 either. It is a third value (`THIRD_VALUE` true): its slope has the
opposite sign to both coarser grids and its curvature is three times flow_24's. The sequence does not contract (|a_40 − a_32| / |a_32 − a_24| = 1.88,
for b 3.81): the differences grow with refinement. Drag falls on every grid at every step (drag slope −2.3e-4, −1.8e-5, −5.4e-4 N/mm), so the
disagreement is in downforce.

Poisson (descriptive): solves at the 32-iteration cap are rare on every grid (flow_24 0.17%, flow_32 0.015%, flow_40 ≤ 0.24%); `POISSON_CONFOUNDED`
not set. flow_40's final residuals are about 20 times larger than flow_32's (per-sample p50 about 1e-5 vs 5.6e-7), so a pressure-solver contribution
is not excluded, only not indicated by cap saturation. The lattice-commensurability confound stands: flow_32 is the only grid whose spacing equals
the design lattice (0.025 m).

## Interpretation (hypothesis, not established)

The perturbations are 0.3–1.25 mm, i.e. 1–5% of the design lattice cell and 1–8% of the flow cells. Across flow_24/32/40 the downforce response
to them differs by up to about 1.8e-3 N at 1.25 mm, far more than the gains the LOWDIM/OPT-01 rules accept (3e-5 N floor; the LOWDIM-04B
accepted gain 3.6e-5 N). This is consistent with the XFID finding that forces move non-smoothly under sub-cell geometry changes (grid-phase
effects), here on WaterLily: at this step scale the response direction is set by the discretization, not resolved geometry. If so, the both-grid
rule did its job (it rejected), and further mm-scale secant steps on these grids would mostly chase discretization effects.

## Consequences (not decided here)

- The flow_48 branch was preregistered only for AMBIGUOUS and is not triggered; it would also not change the non-contraction already seen.
- No GRID-01 amendment: neither "accept on flow_32" nor "flow_24 suffices" is supported.
- Directions worth deciding next: (1) larger, resolvable shape changes (perturbation amplitudes of the order of a flow cell, 20–35 mm), which
  meets the P22-v2 count (now exactly at its limit) and needs volume-neutral directions; (2) grid-phase ensembles of each response (as XFID did on
  OpenFOAM) to average the discretization effect; (3) a re-genesis that removes the lattice tie plateau and the commensurability special case.

Not claimed: grid independence, physical or Stage V downforce, a gradient, optimizer behaviour. All flags false; `shape_update_allowed=false`.

## Correction and reconciliation with GRID-02 (#56), added 2026-10-21 after the merge

This study was planned on a stale base and did not know that GRID-02 (#56, 2026-10-16, `docs/evidence/grid02_trend_2026_10_16/`) had already run
the same seven Stage B geometries on flow_16 and flow_48 and placement-shifted flow_24/flow_32, and that the 2026-10-16 roadmap re-baseline
(`docs/STATE.md`, R3: optimise on flow_32, confirm on flow_48, flow_24 demoted) followed from it. Forward-step downforce slopes (GRID-02 fit, N/mm):
flow_16 +4.1e-4, flow_24 +0.94e-4, flow_32 +4.9e-4, flow_48 +4.9e-4, shifted flow_24 +3.2e-4, shifted flow_32 +9.3e-4 — all positive. flow_40 here
is negative at every forward step (−1.45e-4, −4.07e-4, −1.305e-3 N): the only negative slope among seven grid/placement cells.

**flow_40 is most likely Poisson-confounded, and the interpretation above is withdrawn.** The registered confound label used the fraction of solves
at the 32-iteration cap, which is negligible everywhere. The residuals tell a different story: the per-sample maximum final residual is 0.076–0.081
on every flow_40 state against 3.9e-5 on flow_32 and 3.8e-3 on flow_24 (p50 about 20 times flow_32's). flow_40's 250×120×90 grid coarsens poorly
(250 = 2·5³; the pre-run review counted 4 multigrid levels against 6 on flow_32 and 5 on flow_48). The flow_40 sign flip is therefore **not** taken as
evidence against flow_32 ≈ flow_48, and the hypothesis "mm-scale responses are discretization-dominated on all grids" is withdrawn in favour of
GRID-02's diagnosis (slope varies 50–100 % with grid and placement, flow_24 the outlier). The registered verdict string is unchanged (it was computed
correctly by the frozen rule) but carries no decision weight.

Lesson for grid choices: a flow grid must be checked for its pressure-solver hierarchy and residual level before its responses are compared; the cap-hit
fraction is not a sufficient confound test. The flow_48 branch is moot (GRID-02 already has flow_48). No further GRIDRES-01 work is planned; the roadmap
authority is the 2026-10-16 re-baseline.
