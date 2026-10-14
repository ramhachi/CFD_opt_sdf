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

## Amendment 1 after the adversarial plan review (2026-10-15, before any code or run)

Review: SOUND_WITH_REQUIRED_CHANGES (sonnet subagent; local CPU checks on synthetic inputs only). Verified by the planner:
`scripts/verify_grad_g2_terminal.py:23-24` (G2 primal gate 1e-3 on the window mean; plain-vs-registered baseline gate 1e-6) and the GRAD-01 rule
`src/cfd_sdf/gradients/directional_comparison.py:218-234` (near-zero switch, else sign plus relative error). These items override the text above:

- **C1 Primal gate (was a blocker).** Bit identity of the Dual primal with the plain primal was never observed (G1: 2.2e-6). Gates, as in G2:
  plain window mean vs registered `baseline_v17` ≤ 1e-6 relative (harness), each Dual window-mean primal vs plain ≤ 1e-3 relative. Bit identity is
  required only between QuickTie-Dual and quick-Dual on the same GPU over the 20-step preflight (C6).
- **C2 Verdict rule = GRAD-01 exactly (was a blocker).** `relative_error_tolerance = 0.25`, `absolute_noise_floor = 3·SE` per row; since every
  |ĝ| > 3·SE the floor never fires and the rule is option B (sign match and |g − ĝ|/|ĝ| ≤ 0.25). The additive `0.25|ĝ| + 3·SE` form is reported as
  secondary only, with its effective tolerance per row (about 33–36%). SE is nominal (FD-08's T2 noise model is assumed, not measured); the oracle's
  model spread reaches 12.6%. The "cosine ≥ 0.97" sentence is replaced by: 1/√(1+0.25²) ≈ 0.970 is the worst case of a 25% error in one component of
  a two-component direction, an illustration, not a derived bound. **Report-only:** per response, the cosine and relative L2 of the 4-direction
  vector (g_TA vs ĝ); the optimizer consumes that vector.
- **C3 Comparator pinned.** Verdict on `dual_time` (tangent of the time step propagated); `frozen_time` reported. Window and interpolation as FD-08
  (`fd08_v2_campaign_io.py:62-75`, mirrored by the bridge's `window_mean`); ĝ is the odd part (`:150-156`), so an ε → 0 derivative is the right
  comparand. Reuse `analyze_grad_g2_bridge.py` / `verify_grad_g2_terminal.py` (extend, do not rewrite). AGREE says nothing about step usefulness
  (STEP-01: one-sided steps are curvature-dominated).
- **C4 τ.** τ is absolute in velocity units (U = 1); 1e-5 is about 80–170 Float32 ulp and was chosen post hoc from {1e-5, 1e-4} on D0 corner-box
  states only. Before the freeze, a disclosed, non-gating CPU one-step sensitivity at τ ∈ {3e-6, 1e-5, 3e-5} on the DIAG5 states is recorded. The
  verdict uses `QuickTie(1f-5)` (Float32 literal). The mean over tied candidates is not guaranteed unbiased against the FD slope (at a 3-way tie it
  differs from the centered FD); this is part of what the run measures. The one-step 12–16% corner-box mismatch is not cited as support (far-field,
  not force-level; near-body/wake and D1/D2/P1 never compared).
- **C5 Watchdog and partial evidence.** New code: every 100 steps a GPU reduction of max |tangent| over u and p with the argmax cell, written and
  flushed to a per-run CSV together with the force samples, so a failed run keeps its history. BLOCKED = non-finite tangent or max |tangent| > 1e30
  (Float32 headroom), with onset step and location; a per-run wall-time abort at 3× the plain-run time. Order D0 (the known blower, pilot), D1,
  D2, P1. Expected about 5 min per run (DIAG1: about 32 ms/step); kernel timeout 3 h.
- **C6 Integrity and GPU risk.** Extract `QuickTie` (`waterlily_grad_g2_diag5_stages.jl:37-67` plus `_p1`) into a minimal `scripts/quick_tie.jl`
  shared by the CPU tests and the kernel and frozen by hash. Remove the silent fallback for mixed Float32/Dual arguments (error instead) and assert
  Dual width 1. Kernel's first action: a 20-step GPU Dual preflight with `quick` and with `QuickTie`; primal values must be bit-equal and tangents finite,
  else INCOMPLETE. CPU tests: value identity on ties/±0/NaN/random inputs; at a 2-way tie the partial equals the centered FD; the Dual method is
  actually dispatched.
- **C7 Wording.** "Decays over 40 steps" is replaced by "decays over the 20 recorded steps at S900 (S1000's 40-step condition failed)". AGREE is
  never described as the derivative of the implemented map.
