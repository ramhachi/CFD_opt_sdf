# G4 B2.0 cylinder O-grid winding incident and minimal fix

Date: 2026-08-04

## Decision

Apply the reviewed minimal **A** correction to the deterministic body-fitted
cylinder O-grid generator: for every generated hex block, rotate its vertex
layer order from `(a b c d e f g h)` to `(e f g h a b c d)`.

This corrects the block orientation only.  It leaves the circular `arc`
geometry, vertices, patch definitions, block topology, cell counts, grading,
physical problem, solver settings, and every B2.0 runtime and acceptance
criterion unchanged.  The correction therefore requires a fresh v2
compilation and runtime artifact; it does not repair or relabel the v1
artifact.

## Preserved v1 incident

The first coarse body-fitted runtime artifact,
`examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v1`, failed in
`blockMesh`.  The representative invalid hex was
`(0 1 9 8 16 17 25 24)`, which OpenFOAM v2512 reported as inside-out.

That artifact remains a retained execution-failure record.  It is not mesh
health evidence, a completed runtime prefix, or a cylinder qualification
result.  It must not be deleted, overwritten, or combined with v2 evidence.

## Alternatives considered

- **A — swap the z-layer ordering of every hex:** selected.  It is the
  smallest deterministic correction that restores the right-handed hex
  ordering while preserving the stated O-grid contract.
- **B — change arcs, sector ordering, grading, or cell counts:** not
  selected.  Those changes would alter the mesh contract and would require a
  new numerical-design decision rather than an orientation correction.

## Review evidence

The bounded `sol_g4_b2_cylinder_o_grid_winding` review tested the exact
OpenFOAM v2512 correction on the pinned temporary case.  `blockMesh` followed
by `checkMesh` reported `Mesh OK` for 2,880 cells, with maximum non-orthogonality
`39.86` and maximum skewness `2.50`.  Phase A then converged at iteration
1,255.  This establishes that the selected correction addresses the observed
mesh-orientation incident; it is not a three-grid cylinder result and it
does not establish any B2.0 force, `Cp`, GCI, or cross-fidelity criterion.

## Required next evidence

Compile a new, immutable v2 cylinder artifact and execute it under the
existing prefix-complete and two-phase runtime contracts.  The evaluator may
consider the body-fitted result only after a complete fresh six-case
`--through-grid fine` artifact passes all pre-existing raw-evidence and
three-grid gates.

## Scope

This incident addendum changes no physical model, numerical threshold, force
sign convention, grid-refinement requirement, provenance rule, or roadmap
gate.  It neither qualifies the cylinder nor changes the channel-before-
cylinder ordering set by the B2.0 scope decision.
