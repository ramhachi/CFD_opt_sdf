# #23 GRAD-TA1 result: the tie-averaged forward-AD tangent also blows up (2026-10-15)

Evidence class: bounded derivative-capability result on Kaggle T4, flow_24, canonical v17, four FD-08 directions. Plan:
[grad_ta1_plan_2026_10_15.md](../grad_ta1_plan_2026_10_15.md) (Amendments 1–2). Implementation, run and analysis by sonnet subagents; plan, reviews
coordination and this record by the parent; all reviewers are Claude subagents, not humans.

## Result

- **Official registered verdict: `GRAD_TA1_INCOMPLETE`** (frozen analyzer, one `--write`): its τ identity check compared the recorded Float32
  τ (`Float64(1f-5)` = 9.999999747378752e-06) with the Float64 literal 1e-5. No other integrity problem.
- **Amendment 1 (post hoc, disclosed): `GRAD_TA1_BLOCKED`.** A new analyzer that changes only that check to a Float32 comparison
  (`docs/evidence/grad_ta1_2026_10_15/amendment1/`); a wrong τ still gives INCOMPLETE. The kernel itself reported `TA1_RESULT BLOCKED`
  independently of either analyzer.

All four Dual runs (D0, D1, D2, P1) crossed the 1e30 tangent watchdog at step 700 (t ≈ 9.5 tU/L, of 8,740 steps). Onset (first logged step with
u and p above 10× their step-200 value) lies in steps (300, 400] for all four; growth 5.2, 9.2 and 11.7 decades per 100 steps over steps
400–700, identical across directions to two decimals; force tangents grow with them (D0 `fz_tan` 2.5e9 at step 504, 1.2e29 at 696). The argmax
cell is (105,54,9) in all four runs = (0.950, 0.550, −0.650) m in flow_24: 0.25 m above the ground plane, in the near-ground wake about 0.58 m
from the body's bounding box, far from the domain boundaries. No derivative row was produced, so nothing was compared with FD-08.

`QuickTie` was active: λ was routed through the `Simulation` constructor (a pre-run review FAILED the first freeze because
`sim_step!(sim; λ)` is ignored in WaterLily 1.8.0; fixed and re-frozen), every Dual run recorded `QuickTie{Float32}`, and the 20-step GPU
preflight had bit-equal primal and different tangents between the `quick` and `QuickTie` arms (1.27%).

## Comparison with the exact-AD attempt (descriptive; thresholds are not like-for-like)

G2/DIAG1 (exact AD, `quick`): onset about step 838 (DIAG4 control, box max > 1), first non-finite at step 1196 (Float32 overflow, about 3e38) at
cell (24,61,40) = (−1.75, 0.78, 0.38) m, upstream far field; pre-failure fit 0.0975 decades/step over steps 1096–1196. GRAD-TA1: watchdog 1e30
at step 700 (3.4e38 would be reached near step 750 at its rate), mean 0.117 decades/step over steps 600–700, at a different place. Tie-averaging
the QUICK limiter removed the far-field mode DIAG5 diagnosed but did not make the tangent bounded: a different, direction-independent growing
mode appears earlier. No mechanism is identified here.

## Integrity and review

Freeze `9ea48ca9…` (source `28d2c01`), `scripts/freeze_grad_ta1.py --verify` holds at HEAD (the amendment test was renamed out of the frozen
test glob). Pre-run review: FAIL (λ routing), fixed; post-run review: PASS_WITH_REQUIRED_CHANGES (the verify fix above; disclosure notes folded into
this record). The reviewer recomputed onset, blocked step, argmax cells, growth rates and the coordinate mapping from the raw CSVs. The amendment
analyzer monkeypatches the frozen module's globals when imported; it must not be imported together with the frozen analyzer in one process. The
BLOCKED path skips the plain-baseline and window-mean primal gates (frozen behaviour, disclosed before the run). Kaggle: one submission, version 1,
about 9 minutes; plain 138.9 s; Dual peak VRAM 309 MB.

## Consequence

The forward tangent of this discrete solver is unbounded over the registered window with both the exact and the tie-averaged limiter derivative,
while finite perturbations decay (DIAG5). A reverse or adjoint method linearizes the same map, so this is a warning for #24/#39 as well, not a
result about them. #23 stays open; no gradient backend is qualified; all six flags remain false; `selected_delta` is not set. The next step is
a roadmap decision on #25/#30 (see phase_plan), not a further local diagnostic of this tangent.
