# P22-v2 registration: result

Issue: [#55](https://github.com/ramhachi/CFD_opt_sdf/issues/55). Terminal: the registration was written once, with no integrity
failure. Evidence class: contract registration plus solver-free arithmetic; CFD runs 0, Kaggle submissions 0,
`selected_delta=null`, `shape_update_allowed=false`; no flag, v1 file, production mapping or dependency was modified.

Artifact: [`sdf_native_volume_semantics_v2_2026_10.json`](../sdf_native_volume_semantics_v2_2026_10.json), sha256
`735a0cc45ffd8920ac0f4716ddd9154d21b1f86fb05317cc713f44dad95843f3` (sidecar `.json.sha256`), written by the frozen registrar at
freeze `459c2864f0f31a219ae561e85d97dad924d8c7b5f317e7781cbefcdb10fd20af` after the independent pre-run PASS (a Claude subagent reviewer, not a human); the hash equals
that of a scratch rehearsal made on the same frozen sources. The smooth contract `sdf_native_smoothed_volume_v2` has sha256
`caaa38ef40e810fe8a9c8d8195e0eada6d2ce5e78af25ea2a9670618f0d1f0a4` and binds the unchanged v1 contract
`56825cd5…7a969`.

## Registered constraint

`N_phi <= N_max = 8272` (integer comparison) on the registered v17 lattice (origin `(-1,-0.8,-0.6)` m, h = 0.025 m, nodes
121×65×49). `V_max = 0.12925000000000003` m³ is derived only. Reference: the hash-pinned pre-LOWDIM v17 baseline artifact
(state `02f48f64…`); not the LOWDIM-03 parent. It is a representation-specific discrete constraint and not a physical or
continuum volume constraint.

## Measured at registration (ten states, all exactly at the limit: two re-measured, eight from recorded volumes)

| State | Solid centers | v2 hard residual | v1 verdict (historical) |
| --- | ---: | ---: | --- |
| v17 baseline (re-measured) | 8272 | 0 | infeasible: +0.003125 m³ over the v1 limit |
| LOWDIM-03 parent (re-measured) | 8272 | 0 | infeasible: +0.003125 m³ |
| eight LOWDIM-04A ±1.25 mm perturbations (recorded volumes divided by h³, not re-derived) | 8272 each | 0 | not evaluated here |

Smooth values on the baseline and the parent: `V_eps` 0.08897032 and 0.08791792 m³; the v2 constraint residual `g_V` is −0.3116 and
−0.3198 (v1 residuals −0.2946 and −0.3029 reproduce the recorded values). `g_V` is far from active at the hard boundary and cannot
signal the active hard constraint; equal `N_phi` does not mean equal volume (the recorded ±1.25 mm D0 states keep `N_phi` while the
smoothed volume changes by about ±2.8%).

## What this does and does not establish

Establishes: a registered, hash-bound, lattice-specific integer volume constraint under which the retained baseline and parent are
feasible with zero slack, with v1 untouched. Does not establish: mapping reproducibility or signer qualification (#52 and #53 stay
unresolved; non-blocking only for the hard count of this artifact); anything for another lattice, STL or regenerated SDF; physical or
continuum volume; feasibility or optimality of any candidate; that LOWDIM-04A may restart. **#51 stays blocked**: its restart needs a
separate decision and preregistration that handles the active, integer-quantized hard constraint (smooth gradient may propose, the
integer count decides, and a rule is needed for proposals that the hard count rejects).

On coverage: the SRCMAP-03a certificate bounds the baseline smoothed volume (relative 1.2e-4) and the parent's relative change only through its gate-classification bound, not as a contract property; the registration states the conservative form ("not covered").

The "about −0.31 to −0.32" figure applies to the baseline and the parent only; the recorded D0 perturbations span roughly −0.30 to
−0.34.
