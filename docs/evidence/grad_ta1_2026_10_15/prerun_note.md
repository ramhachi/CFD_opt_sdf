# GRAD-TA1 prerun note (#23): tie-averaged forward-AD slopes vs the FD-08 oracle (fixed before the run)

Plan: `docs/grad_ta1_plan_2026_10_15.md` including Amendment 1 (C1-C7) and Amendment 2 (after the FAILED pre-run review; both override the text above them). This note restates the contract; the freeze (`prerun_freeze.json`) pins the bytes.

## Question
Do the forward-mode tangents of the implemented primal, with the QUICK limiter's partials replaced by the tie-averaged partials (`QuickTie`, tau = 1e-5),
reproduce the FD-08 Model-A regression slopes (8 rows: D0, D1, D2, P1 x drag, downforce) on flow_24, canonical v17, Re 80, within the GRAD-01 rule?

## Contract
- One Kaggle T4 kernel, `ramhachi888/cfd-opt-sdf-grad-ta1`: preflight, a plain Float32 baseline, then D0, D1, D2, P1 as Dual{Float32, width 1} simulations with
  `WaterLily.Simulation(...; λ = QuickTie(1f-5))` (the constructor; `sim_step!(sim; λ)` ignores λ in WaterLily 1.8.0), full 8,740 steps, `d<F>/d alpha` time-averaged over [80, 120] tU/L (G2 bridge semantics; `dual_time` is the verdict comparator, `frozen_time` is reported).
- `QuickTie` (`scripts/quick_tie.jl`): value bit for bit `quick`; partials = mean of the partials of all candidates within tau of the selected value. A surrogate, **not** the derivative
  of the implemented map at ties. The silent mixed-type fallback of the DIAG5 copy is an error, Dual width 1 is asserted by dispatch.
- Preflight (kernel first action, 20 steps): QuickTie-Dual and quick-Dual primal u, p bit-equal, tangents finite, else INCOMPLETE. CPU: 20 steps pass bit-equal (`tests/test_grad_ta1_quick_tie.py`).
  It reports the max u and p tangent difference between the arms, which is exactly 0 iff no tie within tau occurred in the 20 steps. The CPU dry run gives a non-zero difference (u 1.43, p 1.89; relative u 5.7 %), so ties occur there and QuickTie is demonstrably routed; the GPU value is unknown until the run
  and **may be 0, in which case the 20-step preflight exercises only the λ routing (the arms record `quick` vs `QuickTie{Float32}` from `sim.flow.λ`), the bit-equal primal and finiteness, not ties**. The difference is never gated.
- Primal gates (C1, as G2): plain window mean vs registered `baseline_v17` <= 1e-6 relative (drag 0.3239039699743226 N, downforce 0.3316344583180616 N); each Dual window-mean primal vs plain <= 1e-3.
  Bit identity of the Dual primal with the plain primal is **not** required (never observed: G1 2.2e-6).
- Watchdog (C5): every 100 steps max |tangent| over u and p and its argmax cell, flushed per run (`<label>.watchdog.csv`, `<label>.history.csv`). BLOCKED = non-finite or > 1e30 tangent
  (onset step and cell reported, also when detected from a force sample; the next direction still runs). A Dual run longer than **8x** the plain run's total time raises an error; **any error, wall abort included, aborts the whole kernel**
  (status ERROR, INCOMPLETE; no per-direction continue). A false abort remains possible if QuickTie-Dual costs more than 8x the plain run; disclosed.

## Verdict (GRAD-01 exactly, C2; `scripts/analyze_grad_ta1.py`)
Per row: `relative_error_tolerance = 0.25`, `absolute_noise_floor = 3 SE`. Since every |g_hat| > 3 SE the floor never fires and the rule is option B: the row agrees iff sign(g) = sign(g_hat) and
|g - g_hat| / |g_hat| <= 0.25 (inclusive). The additive form 0.25|g_hat| + 3 SE (effective tolerance about 33-36 %) is secondary, reported only.
- `GRAD_TA1_AGREE`: all runs complete and finite, preflight and primal gates pass, 8 of 8 rows agree.
- `GRAD_TA1_DISAGREE`: same integrity, at least one row fails (each reported).
- `GRAD_TA1_BLOCKED`: intact output, a Dual run's tangent non-finite or > 1e30.
- `GRAD_TA1_INCOMPLETE`: any integrity failure (pins, commit, manifest, T4, preflight, kernel error or wall abort, primal gate).
Priority INCOMPLETE > BLOCKED > DISAGREE > AGREE. The BLOCKED path is judged without the full verifier (no plain-baseline gate, no history checks); disclosed. INCOMPLETE also when the recorded `sim.flow.λ` types are not
`typeof(quick)` (plain) and `QuickTie{Float32}` (every Dual run, preflight arm 2). Report-only: per response the 4-direction cosine and relative L2 of g_TA vs g_hat; tangent max-norm history; wall time and VRAM per run.
delta_rel = 0.25 is a judgement (middle illustrative value of `docs/issues/46_...`), not a standard; 1/sqrt(1 + 0.25^2) = 0.970 is the worst case of a 25 % error in one component of a two-component direction, an illustration, not a derived bound.

## Disclosures (known before the run; this is not blind validation)
- **tau was chosen post hoc.** 1e-5 is about 80-170 Float32 ulp in velocity units (U = 1); it was picked from {1e-5, 1e-4} on D0 corner-box states only (DIAG5).
- **tau sensitivity (C4, non-gating, CPU, one step, D0 corner box, stored DIAG5 states S900 and S1000, `tau_sensitivity.json`):** the one-step JVP against the central finite difference of the same map
  (eps = 1e-3, box relative L2 / JVP box-max gain, finite-difference gain in brackets): S900: quick 1.07 / 1.386 (0.589); tau 3e-6 0.185 / 0.534; tau 1e-5 0.126 / 0.586; tau 3e-5 0.876 / 0.872.
  S1000: quick 1.446 / 1.488 (0.551); tau 3e-6 0.159 / 0.497; tau 1e-5 0.157 / 0.539; tau 3e-5 1.055 / 0.689. So 1e-5 sits in a narrow window: a factor 3 up loses the agreement, a factor 3 down keeps it
  with a slightly low gain. The reproduction gate (quick and tau = 1e-5 rows equal the recorded DIAG5 E3 rows to 1e-6 relative) passed. This is far-field corner-box evidence, not force-level; near-body and wake
  and D1/D2/P1 were never compared, and the 12-16 % one-step mismatch is not cited as support. The verdict uses `QuickTie(1f-5)` regardless of this table.
- The mean over tied candidates is not guaranteed unbiased against the FD slope (at a 3-way tie it differs from the centered FD; at a 2-way tie it equals it, tested); this is part of what the run measures.
- The oracle's SE is nominal (FD-08's T2 noise model is assumed, not measured); the oracle's model spread reaches 12.6 %.
- The FD-08 slopes and SE, G2-BLOCKED, DIAG1-5 and STEP-01 were visible when this contract was written. "Decays" is claimed only over the 20 recorded steps at S900 (S1000's 40-step condition failed).

## Claims
AGREE would support, for flow_24, v17 baseline, these four directions and Re 80 only, that the tie-averaged forward derivative reproduces the FD-08 slopes within the registered gate. It is **not** the derivative of the
implemented map, not reverse or full-field qualification (#24), not flow_32 (GRID-01 acceptance needs both grids), not a production selection (#25 needs its own supersession entry), not a statement about step
usefulness (STEP-01: one-sided steps are curvature-dominated), not an optimizer result. All six flags stay false; `selected_delta` is recorded for this contract only. DISAGREE / BLOCKED record the bounded No-Go
of this surrogate for #23; the next candidate is chosen then.

## Amendment after pre-run review (FAIL)
The pre-run review of the first freeze (source cb066dc, freeze c6366a8) failed: `sim_step!(sim; λ)` ignores λ in WaterLily 1.8.0 (`Flow.jl:190-206`: kwargs reach only `udf!`; the scheme is the Flow field `flow.λ` set at construction), so that bridge ran `quick`
everywhere and its preflight was vacuous. Fixed (`docs/grad_ta1_plan_2026_10_15.md`, Amendment 2): λ is passed to the `Simulation` constructor for every run and preflight arm; a type mismatch of `sim.flow.λ` is a hard error; the type is recorded in every summary,
the preflight and the index and checked by the analyzer; routing is covered by `scripts/test_ta1_lambda_routing.jl` and by the preflight test; the preflight reports u/p tangent differences (never gated; 0 would mean no tie in 20 steps); the wall factor is 8x;
abort semantics are stated as above; BLOCKED from a force sample records the tangent maximum and its cell; the BLOCKED path skips the full verifier (disclosed); `scripts/freeze_grad_ta1.py --verify` re-derives the freeze from the committed bytes.
The first freeze and rendered worker (c6366a8) are superseded: they are removed in the commit that precedes the new freeze (git history keeps them), and the identity-free proof was recaptured. Nothing was submitted to Kaggle under the first freeze.
