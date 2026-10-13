# GRID-01 (#26) closure: which flow grid may decide a first update

Date: 2026-10-14 Asia/Tokyo. Issue: [#26](https://github.com/ramhachi/CFD_opt_sdf/issues/26). Evidence class: solver-free synthesis of retained, hash-pinned results; **no new CFD and no new measurement.**
Authority: the user's words recorded on #51 (「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」), read as authorizing this decision; reviewers are Claude subagents, not humans.
The decision rule was fixed in `scripts/synthesize_grid01_closure.py` (function `decide`) and is applied to evidence the author has already seen: this is a **non-blind synthesis**, not a test.

## Decision: DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE

For the first optimization update:

1. **flow_24 proposes.** Its centered secants give the local direction and model (cheap, and the downforce secant vectors of the two grids agree: cosine 0.984 at the baseline, 0.864 at the LOWDIM-03 parent).
2. **flow_32 is a mandatory confirmation.** The candidate SDF must be run on flow_32 as well.
3. **Acceptance needs both grids.** The registered rule (strictly more than 3e-5 N downforce gain and a computed drag change <= 0, plus the geometry gates) must hold on flow_24 **and** flow_32 for the same candidate state. Neither grid alone may accept a shape update.
4. **The step size comes from the actual dual-grid ladder, never from the flow_24 linear model.** (Along the Stage A solution the flow_24 linear model predicted +1.7e-4 N at 1.25 mm; the actual was -5.2e-5 N.)
5. **No grid is declared the truth.** flow_32 is not claimed converged or more accurate; the rule is a bounded engineering decision that single-grid acceptance is contradicted by retained states.

## Evidence ([synthesis.json](synthesis.json), derived from six pinned analyses)

- W4 v17 resolution sensitivity (flow_16 to 24: drag 31.6%, downforce 23.4%; **flow_24 to 32: drag 6.77%, downforce 8.37%**): no convergence; flow_32 cannot be declared the true response.
- Secant vector agreement between the grids, downforce / drag: GRID-01 at the baseline 0.984 / 0.279; LOWDIM-04A at the parent 0.864 / 0.102. The downforce direction is shared (one resolved sign flip, D1); the drag vector is not (drag D0 flips sign; P1 unresolved at the parent). A single grid does not determine the drag constraint.
- **Acceptance on identical states disagrees**: of 9 retained states measured on both grids (LOWDIM-02A +1.25 and +2.5 mm, LOWDIM-03 0.625/1.25/2.5 mm, LOWDIM-04B 0.3125/0.625/0.9375/1.25 mm), **5 get opposite accept/reject verdicts**. The disagreement is two-sided: four are flow_24 failing downforce where flow_32 passes
  (LOWDIM-02A +2.5 mm; LOWDIM-04B 0.625, 0.9375 and 1.25 mm) and one is flow_32 drag failing where flow_24 passes (LOWDIM-02A +1.25 mm; flow_32 drag changes are at jitter level). On the LOWDIM-04B ladder flow_24 alone would select 0.3125 mm and flow_32 alone 1.25 mm, a step on which flow_24 loses downforce.
- Step-size dependence on the grid (retained LOWDIM-03 ladder, same direction): the flow_24 downforce gain peaks inside the ladder (+2.09e-4 N at 1.25 mm, +1.16e-4 N at 2.5 mm) while the flow_32 gain is still rising at the largest step (+3.87e-4 N at 1.25 mm, +6.76e-4 N at 2.5 mm).

## Robustness and limits

The proposal role of flow_24 rests on the downforce cosine, whose minimum is 0.864, 0.064 above the frozen 0.8 threshold; with a threshold of 0.9 the rule would return UNDECIDED. LOWDIM-03 accepted its 1.25 mm step on both grids, which supports the role, and LOWDIM-04B shows the proposal is
adequate for a direction but not for a step size. The thresholds (0.8, 0.95, 0.8) are judgement values for this synthesis, not standards. flow_32 noise is unmeasured (the 3e-5 N floor is nominal and about 1 sigma). The cost of the rule is roughly the flow_32 cost per candidate (about 2.3 times flow_24 per state).

## Not claimed

That flow_32 (or any grid) is the converged or true response; formal continuum or GCI gradient convergence (that needs a registered convergence study, e.g. a finer grid); flow_32 noise; any physical downforce or drag gain; that the dual-grid rule is optimal. This decision does not authorize a shape update:
`shape_update_allowed=false`, all qualification flags false, #30 still needs #25 and #27 to #29.
