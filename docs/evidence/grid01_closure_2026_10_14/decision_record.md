# GRID-01 (#26) closure: which flow grid may decide a first update

Date: 2026-10-14 Asia/Tokyo. Issue: [#26](https://github.com/ramhachi/CFD_opt_sdf/issues/26). Evidence class: solver-free synthesis of retained, hash-pinned results; **no new CFD and no new measurement.**

**Authority and its limits.** The user's words recorded on #51 are blanket (「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」), but the comment that recorded them listed only the LOWDIM-04A restart, the P22-v2 count and Kaggle submissions, and earlier comments on #26 and #49 explicitly withheld "grid selection"
authorization pending the user. This record **reads** the blanket words as covering the #26 decision; it is an interpretation, not a grant specific to #26, and a later explicit user decision supersedes it. Reviewers are Claude subagents, not humans.
The rule was fixed in `scripts/synthesize_grid01_closure.py` (`decide`) and applied to evidence the author has already seen: a **non-blind synthesis**, not a test.

## Decision: DUAL_GRID_REQUIRED_FOR_FIRST_UPDATE (a conservative AND policy)

For the first optimization update:

1. **flow_24 may propose the downforce direction** (cheap). Drag-feasible proposals must come from the cross-grid secants of **both** grids (as every retained dual-grid proposal did), not from flow_24 alone: the one flow_24-only direction tested on flow_32 (LOWDIM-01 in LOWDIM-02A) kept downforce positive but failed flow_32 drag.
2. **flow_32 is a mandatory confirmation**: the candidate SDF must also be run on flow_32.
3. **Acceptance needs both grids** for the same candidate state: strictly more than 3e-5 N downforce gain and a computed drag change <= 0, plus the geometry gates (the retained LOWDIM rule). Neither grid alone may accept a shape update.
4. **The step size comes from the actual dual-grid ladder, never from a flow_24 linear model** (along the Stage A solution the flow_24 linear model predicted +1.7e-4 N at 1.25 mm; the actual was -5.2e-5 N).
5. **No grid is declared the truth.**

What the data robustly show is that **flow_24 alone is insufficient**. Whether flow_32 alone would suffice is undecidable here (no convergence is shown), so "both grids" is a conservative policy chosen for safety and cost, not something the data force. Only the clause "flow_24 may propose the downforce direction" depends on the 0.8 cosine
threshold; points 2 to 5 hold at any threshold because any acceptance disagreement already blocks "sufficient".

## Evidence ([synthesis.json](synthesis.json), derived from six pinned analyses)

- **Resolution sensitivity (W4 v17):** flow_16 to 24: drag 31.6%, downforce 23.4%; **flow_24 to 32: drag 6.77%, downforce 8.37%**. The changes shrink, but **convergence is not established** and flow_32 cannot be declared the true response.
- **Secant vectors** (downforce / drag cosine; flow_32/flow_24 norm ratio): GRID-01 at the baseline 0.984 / 0.279; 1.21 / 0.89. LOWDIM-04A at the parent 0.864 / 0.102; 2.13 / 0.48. The downforce direction is largely shared but its magnitude on flow_32 doubles at the parent; the drag vectors are nearly unrelated (drag D0 flips sign; P1 unresolved at the parent).
- **Acceptance on identical states disagrees.** 9 retained states were measured on both grids: LOWDIM-02A +1.25 and +2.5 mm (LOWDIM-01 direction), LOWDIM-03 0.625/1.25/2.5 mm (GRID-01 robust direction), LOWDIM-04B 0.3125/0.625/0.9375/1.25 mm (Stage A solution, relative to the LOWDIM-03 parent). They come from three direction families and reference states, the rule is
  applied per grid against each source's own reference, and the disagreements are concentrated (02A 2 of 2, 04B 3 of 4, LOWDIM-03 0 of 3): **5 of 9 is a count of correlated trials, not a rate.** The disagreement is two-sided: four are flow_24 failing downforce where flow_32 passes (LOWDIM-02A +2.5 mm, whose flow_24 value LOWDIM-02A itself calls barely
  resolved; LOWDIM-04B 0.625, 0.9375, 1.25 mm) and one is flow_32 drag failing where flow_24 passes (LOWDIM-02A +1.25 mm; flow_32 drag at the floor is unresolved, so that one is not noise-robust). Geometry gates are not part of this count.
  **Floor sensitivity** (disagreements at downforce floors 5e-6 / 1e-5 / 2e-5 / 3e-5 N): 4 / 4 / 4 / 5; the 0.625 mm flow_24 case (2.97e-5 N, 3.4e-7 N under the floor) is the one that flips, so the count is not an artifact of that boundary.
  On the LOWDIM-04B ladder flow_24 alone would select 0.3125 mm and flow_32 alone 1.25 mm (the largest step, because its gain rises with the step), a step on which flow_24 loses downforce.
- **Step-size dependence** (retained LOWDIM-03 ladder, one direction): the flow_24 downforce gain peaks inside the ladder (+2.09e-4 N at 1.25 mm, +1.16e-4 N at 2.5 mm) while the flow_32 gain is still rising at the largest step (+3.87e-4 N, +6.76e-4 N).

## Cost of the rule

The mean flow_32/flow_24 per-state wall-time ratio over the retained campaigns is 2.3 to 2.4 on the process wall time and 3.1 to 3.3 on the Julia solver time (LOWDIM-03, 04A, 04B in synthesis.json). Running both grids therefore costs about 3.3 times a flow_24-only evaluation (process wall; about 4.1 by solver time) per candidate; the two grids run on separate kernels.

## Robustness and limits

The proposal role of flow_24 rests on a downforce cosine whose minimum is 0.864, 0.064 above the frozen 0.8 threshold (with 0.9 the rule would return UNDECIDED), and on cross-grid proposals having been accepted on both grids in LOWDIM-03. The thresholds (0.8, 0.95, 0.8) are judgement values chosen after seeing the data. flow_32 noise is unmeasured: the 3e-5 N floor is a nominal value (the LOWDIM-02A/04A records define it as ten times a nominal 3e-6 N sigma), not a noise measurement, and exploratory
residual estimates put flow_32 response jitter at the 1e-5 to 3e-5 N level.

## Not claimed

That flow_32 (or any grid) is the converged or true response; formal continuum or GCI gradient convergence (that needs a registered convergence study, e.g. a finer grid); flow_32 noise; any physical downforce or drag gain; that the dual-grid rule is optimal. This decision does not authorize a shape update:
`shape_update_allowed=false`, all qualification flags false, #30 still needs #25 and #27 to #29.
