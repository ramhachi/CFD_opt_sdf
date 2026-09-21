# P6 diagnosis record — DF2 transfer-algebra result (2026-09-21)

Status: DF2 deliverable, subordinate to
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
DF2 and to the P6 entry in [`problem_register_2026_09.md`](problem_register_2026_09.md).

The P6 ledger entry (`一般方向で約10%の勾配バイアス / 機構未解明`) suspects the
non-integer overlap transfer (`P`/`P.T`, spacing ratios 1.875/1.5). This record
replaces that suspicion with a measurement, in the same style as the P18
closure record: the ledger status line should point here when its pending edits
are committed.

## Artifacts

- `docs/evidence/p0_transfer_diagnostic_2026_09.json` — transfer diagnostic on
  the real P0 grid pair (canonical 60x32x24, 0.05 m vs source 32x16x16,
  0.09375/0.1/0.075 m; ratios 1.875 / 2.0 / 1.5).
- `docs/evidence/fd_campaign_p6_solver_side_manifest_2026_09.json` — immutable
  pre-registration (profile `fd_gradient_v1`) of the next FD campaign.
- `docs/evidence/df2_grid_campaign_registration_2026_09.json` — registered
  Stage T / Stage V grid campaigns (not run).
- Command: `.venv/bin/cfd-sdf diagnose-fixed-grid-transfer <source> <target> --output ...`.

## Measured facts

The exact-overlap transfer used by the canonical closed loop is, on this real
grid pair:

| property | measured | note |
| --- | --- | --- |
| consistency (each source row sums to 1) | 6.4e-15 | constant fields are preserved |
| conservation (`sum_s (P x)_s V_s = sum_t x_t V_t`) | 1.5e-16 | full coverage holds by construction |
| adjoint identity `<P x, y> = <x, P.T y>` | 5.1e-15 | `P.T` is the exact discrete adjoint of the value transfer |
| volume-weighted pullback difference (informational) | 0.82 | would only matter for a different (integral) transfer definition; not a defect |
| verdict | `exact` | also exact for clean integer-ratio pairs |

## Consequence for P6

The transfer algebra is exonerated: non-integer ratios do not introduce a
mapping defect in this implementation. The residual ~0.90 FD ratio on generic
directions therefore lives in the solver-side chain (primal re-solve, injection
consumption, adjoint convergence at the perturbed state, or the nonlinearity of
the response between the perturbation scale and the solver tolerance).

The next experiment is pre-registered with fixed epsilons, directions, seeds,
sign convention, gates, and stop conditions
(`fd_campaign_p6_solver_side_manifest_2026_09.json`). P6 remains open with a
narrowed scope: **not** a transfer operator defect; a solver-side chain effect
to be bounded or resolved by the registered campaign. Until it completes,
acceptance stays limited to gradient-aligned directions, and any new direction
family must be FD-qualified before it can drive an accepted step (DF3).
