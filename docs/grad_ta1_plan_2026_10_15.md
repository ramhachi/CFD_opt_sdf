# GRAD-TA1 plan (#23): a tie-averaged forward-AD derivative contract, full window, against the FD-08 oracle

Date: 2026-10-15. Issue: [#23](https://github.com/ramhachi/CFD_opt_sdf/issues/23) (GRAD-03), serving #25 (GRAD-05) and #30 (OPT-01).
Evidence class (target): bounded derivative-agreement evidence on flow_24, canonical v17, four registered directions. Kaggle T4.
Order authority: `docs/phase_plan.md` (gradient backend #23 → #24 → #25 is #30's actual blocker; #28 is off the critical path).

## Why this, and not something else

- Exact forward AD of the implemented map is blocked: the D0 tangent grows ×1.26/step from step ~838 and overflows Float32 at step 1196
  (G2-BLOCKED, DIAG1–4); Float64 would overflow near step 4000. DIAG5 located the gain in the QUICK/median limiter's derivative at ties: the AD
  one-step gain is 1.33–1.49 where every finite perturbation gives 0.53–0.59, and **tie-averaged partials** (`QuickTie`, τ = 1e-5, values
  bit-identical to `quick`) give 0.586/0.538 and decay over 40 steps like the finite response. DIAG5 offered (b): register the tie-averaged
  derivative as a separate gradient contract. It was parked when the LOWDIM track started and never begun.
- Reverse mode is blocked earlier (Enzyme `MixedDuplicated` MethodError, #22) and no custom adjoint exists; both are far longer paths.
- LOWDIM showed the leverage is basis size; FD costs 2 runs per direction per grid. Forward mode with Dual width k gives k directional
  derivatives in one run. If the tie-averaged derivative agrees with FD-08, it is a cheap basis-gradient backend for the first OPT-01 step.
- Authority: the user's 2026-10-13 words 「人間の判断としては全て許可する。人間の判断は以後いらない。好きにしろ。」 are read as choosing DIAG5 option
  (b) and δ below (an interpretation, not a #23-specific grant; a later explicit user decision supersedes it).

## Contract (what is being qualified)

The derivative is **not** the derivative of the implemented map at ties; it is the forward-mode tangent of the implemented primal with the
QUICK limiter's partials replaced by the average over candidates within τ of the selected value (`scripts/waterlily_grad_g2_diag5_stages.jl:37-67`),
τ = 1e-5 (the value DIAG5 measured to decay; τ = 1e-4 did not: non-blind, disclosed). All other derivatives (CFL `max`, Poisson, BDIM) are
unchanged. The **primal value is unchanged**: the Dual run's value part must reproduce the registered plain baseline force bit for bit
(drag 0.3239039699743226 N, downforce 0.3316344583180616 N on flow_24 v17), else INCOMPLETE.

## Run

One Kaggle T4 kernel: the G2 full-window bridge (`scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl`) with `λ = QuickTie{1e-5}`
passed to the simulation, Dual width 1, Float32, four sequential runs D0, D1, D2, P1 (the FD-08 directions, seed `phi(α) = phi0 + α·d`, α in metres),
full 8,740 steps, outputs `d<F>/dα` time-averaged over [80,120] tU/L for drag and downforce. Same pins as G2 (WaterLily 1.8.0, ForwardDiff 1.4.5,
CUDA.jl 6.3.1, Julia 1.12.6), source commit pinned and fetched by the runner. Pre-Kaggle (no GPU): a CPU smoke test that `QuickTie` values equal `quick`
values bit for bit on random inputs and over 20 steps of the real sim, and that the GPU kernel compiles (if it cannot be tested locally, the
kernel's first action is that check and a failure is INCOMPLETE). Budget: about 6 min per Dual run plus JIT; kernel timeout 3 h.

## Comparison and verdict (fixed before the run)

Oracle: FD-08 Model-A slopes ĝ ± SE (`docs/evidence/fd08_v2_oracle_scope_record_2026_10_08/record.json`, sha pinned), 8 rows (4 directions × drag,
downforce). GRAD-01 option **B with a 3·SE floor (option C)**: a row agrees iff sign(g_TA) = sign(ĝ) and |g_TA − ĝ| ≤ 0.25·|ĝ| + 3·SE.
δ_rel = 0.25 is the middle illustrative value of `docs/issues/46_fd08_v2_grad03_delta_options_2026_10_08.md`, between the oracle's
uncertainty bound (11% to 38%) and a direction error that still gives a descent direction (cosine ≥ about 0.97 for a 25% error in one component); the
choice is recorded as a judgement, not a standard.

- `GRAD_TA1_AGREE`: all four runs finite and complete, primal bit-identical, all 8 rows agree.
- `GRAD_TA1_DISAGREE`: complete and finite, primal identical, at least one row disagrees (each row reported).
- `GRAD_TA1_BLOCKED`: a non-finite or overflowing tangent (step and location reported, as DIAG1).
- `GRAD_TA1_INCOMPLETE`: integrity failure (primal mismatch, pin/hash mismatch, kernel failure).

Reported for every outcome: per-row g_TA, ĝ, SE, error/|ĝ|, standardized error; tangent max-norm history (every 100 steps); per-run wall time and VRAM
(Dual width 1 vs the plain primal's 12.4 ms/step).

## Use of the outcome (and what it is not)

AGREE supports, for flow_24, v17 baseline, these four directions and Re 80 only: the tie-averaged forward derivative reproduces the FD-08 slopes within
the registered gate. It is not reverse/full-field qualification (#24), not flow_32 (GRID-01 requires both grids for *acceptance*, not for this
derivative check; a flow_32 confirmation would be a follow-up), not a production selection (#25 needs its own supersession entry, e.g. "forward-mode basis
gradient for the first OPT-01 step"), not an optimizer result. All six flags stay false; `selected_delta` is recorded only for this contract.
DISAGREE/BLOCKED: #23 records the bounded No-Go of this surrogate; the next candidate is chosen then.

## Work (implementer: sonnet)

`scripts/waterlily_grad_ta1_2026_10_15.jl` (reuse the G2 bridge and `QuickTie`; no WaterLily source edits), kernel builder/runner under
`infra/kaggle/kernel_grad_ta1/` following the existing freeze/render/identity pattern (prerun freeze of every imported file by hash, source commit tree id,
identity-free Kaggle check), `scripts/analyze_grad_ta1.py` (`--check`, one `--write`, verdict exactly as above), tests for the analyzer on synthetic
rows (sign, floor, δ edge, BLOCKED and INCOMPLETE paths) and for the CPU value-identity smoke. Then freeze, independent review of the frozen bytes, submit,
analyze, independent post-run review, record, merge.
