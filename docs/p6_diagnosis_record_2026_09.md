# P6 diagnosis record — updated with the frozen-design FD campaign (2026-09-21)

Status: supersedes the "next experiment" section of the earlier P6 record. The
registered solver-side campaign ran to completion on a frozen design; the
result is a reproducible, direction-dependent mismatch of **+22% to +57%**
between the finite-difference primal derivative and the continuous adjoint.
P6 therefore stays open with the cause localized to the solver-side chain, not
the transfer algebra and not the campaign machinery.

## Artifacts

- `docs/evidence/fd_campaign_p6_solver_side_result_2026_09.json` — the
  qualified negative result (verdict `passed: false`, 4 failing rows).
- `docs/evidence/p0_transfer_diagnostic_2026_09.json` — transfer algebra exact.
- `docs/df2_refresh_campaign_audit_2026_09.md` — the earlier design-update
  confound and its fix (`maxInitChange 0` frozen template).
- `docs/evidence/fd_campaign_p6_solver_side_manifest_2026_09.json` — the
  immutable registration that was executed unchanged.
- Runner: `scripts/run_df2_fd_campaign_2026_09.py`.

## Measured facts

| direction | FD/analytic ratio | spread over epsilons | relative error |
| --- | --- | --- | --- |
| gradient-aligned | 1.2178 | < 0.1% | 21.8% (fails 5% gate) |
| random seed 11 | 1.3764 | < 0.4% | 37.6% |
| random seed 2026 | 1.5680 | < 0.1% | 56.8% |

Controls that isolate the cause:

- transfer identity: `g_canonical == P.T g_source` exactly (max diff 0.0);
  `dot(g_canonical, d) == dot(g_source, P d)` to machine precision;
- design frozen: maximum `|beta_final - injected|` across all 24 runs is
  `2.98e-8`;
- primal converged in 91 iterations in every run; FD stable across
  `3e-5 ... 1e-3` for every direction.

Because the analytic prediction never passes through the transfer in this
comparison (`dot(g_canonical, d) = dot(g_source, P d)`), the mismatch is
exclusively between the OpenFOAM continuous-adjoint sensitivity and the
discrete primal response at this state and resolution.

## Consequences

- The registered gradient gate as applied to this configuration rejects every
  direction, including the gradient-aligned one (ratio 1.22 ≈ 22% error). A
  step accepted on the canonical gradient can therefore be trusted in sign and
  approximate direction but not in magnitude.
- The historical alarm-fxture result (0.99 aligned / 0.90 random, regularise
  true) and this result (1.22 / 1.38–1.57, regularise false, identity profile)
  are different numerical chains; they must not be merged into one conclusion.
- Next registered questions, in order: (i) does refining the Stage T grid or
  the source grid move the ratio toward 1 (discretisation-consistency study)?
  (ii) does the continuous adjoint's boundary-condition/objective
  implementation explain the aligned-direction 22% at this resolution?
  (iii) should accepted-step magnitudes be corrected by a measured
  direction-dependent factor, or should acceptance require FD confirmation on
  candidate-bound directions?

## Control — primal residual tightening (2026-09-21, later same day)

The registered campaign `p6_tight_residual_probe_2026_09`
(`docs/evidence/fd_campaign_p6_tight_residual_manifest_2026_09.json`) re-ran
the same 24 rows with `residualControl` tightened from `5e-7` to `5e-9` and the
primal `nIters` cap raised from 1000 to 5000:

| direction | baseline ratio | tight ratio | delta |
| --- | --- | --- | --- |
| gradient-aligned | 1.2178 | 1.2179 | < 0.01% |
| random seed 11 | 1.3764 | 1.3759 | < 0.04% |
| random seed 2026 | 1.5680 | 1.5684 | < 0.03% |

Primal iterations rose from 91 to 114 with no change in the ratios. Primal
convergence is therefore exonerated as the cause, and the mismatch is a stable
property of the continuous adjoint against this discrete primal.

Consequences for DF3: the acceptance controller must keep re-evaluating the
primal for every trial (it does), and no accepted-step magnitude may rely on the
5% gradient gate in this configuration. The gate failure is recorded as a
configuration-specific bound; the production identity chain needs either a
theoretical magnitude correction or FD-confirmed step sizes.
