# DF2 refresh campaign audit — design-update confound (2026-09-21)

Status: campaign execution audit. The refreshed FD campaign ran to completion
and is **invalidated as P6 evidence** because the perturbed cases did not keep
the design frozen. This record documents the mechanism, the measured numbers,
and the required fix. P6 remains open with a sharper question.

## What was rebuilt (all prerequisites now exist)

1. Qualified dual transfer against the current ProblemSpec:
   `work/df2_fd_refresh/source_state/provenance.json` (the old
   pre-semantic-binding provenance and the missing `injected_contract` were
   rebuilt; the identity C3 contract template was re-derived from the recorded
   `beta_max = 2500` identity rule and validates with
   `validate-fixed-grid-contract`).
2. Base run `work/df2_fd_refresh/primal_base`: converged (primal 91 iters,
   drag adjoint 577, downforce adjoint 592; `downforce = 0.300720062967`).
3. Canonical gradient through the new **identity-profile path**:
   `reconstruct_final_decomposed_openfoam_fields(allow_identity_profile=True)`
   substitutes `beta` for the unwritten `alphaTilda` when the case declares
   `regularise false` (new feature, tested). The transfer records
   `identity_profile: true` in its provenance.
4. Campaign runner `scripts/run_df2_fd_campaign_2026_09.py` with the three
   registered directions and four registered epsilons; 24 runs executed, all
   stated converged, FD stable in epsilon (e.g. aligned direction
   `fd = -0.1576 ... -0.1581` across `3e-5 ... 1e-3`).

## Measured invalidation

| check | result |
| --- | --- |
| transfer chain `g_canonical == P.T g_source` | exact (max diff 0.0) |
| `dot(g_canonical, d)` vs `dot(g_source, P d)` | identical (0.00855210839130539) |
| base run final `beta` vs injected state | agrees to 1.1e-8 |
| **perturbed run final `beta` vs injected state** | **differs by 0.187 (plus) and 0.187 (minus) at `eps = 1e-3`** |
| FD / analytic ratio | 18.4 (aligned), 41-43 (seed 11), 21.6 (seed 2026) |

The solver's `topO` design update moved the design by ~0.187 in both the plus
and minus perturbed cases, nearly identically. The FD therefore measures the
difference between two solver-updated designs, not the response to the
registered perturbation; the direction-dependent ratio is an artefact of that
update, not a property of the transferred gradient.

## Required fix before the campaign can be evidence

- freeze the design in the perturbed runs: use a template whose `topO`
  design-variable update cannot move the design (e.g. disable the update method
  or pin the initial change), or run a frozen-alpha primal solver; the identity
  profile already removes the projection confound, but the ISQP update remains;
- re-run the 24 registered rows only after the frozen-design template is
  validated by repeating the base-state check (final `beta` vs injected state
  within solver tolerance);
- do not compare these rows with the historical 0.99/0.90 ratios: the
  configuration (`regularise false`, identity profile, rebuilt contract) is a
  different numerical chain.

## Claims

- Supported: the identity-profile export path, the hardened per-perturbation
  provenance chain, and the campaign runner are implemented, tested, and
  executable end to end on real OpenFOAM.
- Not supported: any FD ratio, P6 closure, or transfer-exoneration conclusion
  from this campaign. P6 stays open; the next registered action is the
  frozen-design template.

## Appendix — regularisation A/B attempt (same day, invalid)

A second registered campaign (`p6_regularised_ab_2026_09`,
`docs/evidence/fd_campaign_p6_regularised_ab_manifest_2026_09.json`) re-ran the
same 24 rows with `regularise true` and `maxInitChange 0`. It reproduced the
original design-movement ratios (18/41/22) instead of the frozen ratios
(1.22/1.38/1.57), and the check on `gradient_aligned/1e-03/plus` shows
`max|beta_final - injected| = 0.187`: with solver-side regularisation the
solver's own filter/projection maps the injected rho to a different `beta`, so
the design cannot be frozen by `maxInitChange` alone.

This is a re-confirmation of the one-owner rule (P14): the solver-side
projection must stay off, and the A/B says nothing about whether regularisation
would improve the FD ratio. The valid configuration remains
`regularise false` + frozen design, whose ratios 1.2178 / 1.3764 / 1.5680 are
recorded in `docs/evidence/fd_campaign_p6_solver_side_result_2026_09.json`.
