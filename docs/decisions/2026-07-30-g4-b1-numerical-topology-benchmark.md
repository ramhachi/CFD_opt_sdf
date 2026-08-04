# G4 B1 numerical topology benchmark

Date: 2026-07-30

## Decision

Implement B1 as an STL-independent canonical voxel fixture pack. It binds
topology-checker outcomes and the localized filter/projection derivative chain
to one deterministic result index. It is not an OpenFOAM, adjoint, or physical
gradient benchmark.

## Fixtures and topology acceptance

Use the unchanged 2 mm spacing and 10 mm minimum-solid-width policy:

- an unrooted island is rejected;
- root-attached bridges of width 1--4 cells are rejected; and
- root-attached bridges of width 5--6 cells pass when all other fixture rules
  are satisfied.

Every result records grid/mask/policy/filter/projection JSON hashes, canonical
`x-fastest` ordering, checker report, status, and reasons.

## Transform derivative acceptance

For the deterministic scalar probe
`J(rho_raw) = w^T P(F(rho_raw))`, check the analytic gradient
`F^T(P'(F(rho_raw)) * w)`.

- Test every active cell and at least three active-only deterministic random
  directions; persist seeds, direction indices, normalisation, and SHA-256.
- Use central differences at `h = 1e-4, 1e-5, 1e-6`, retaining all values.
- At `h = 1e-5`, require
  `abs(FD - analytic) <= 2e-9 + 1e-7 * max(abs(FD), abs(analytic))`.
- The error must improve from `1e-4` to `1e-5`; a round-off deterioration at
  `1e-6` is recorded but not automatically rejected.
- Non-active raw entries and direction entries remain exactly zero.
- Replaying the pack yields byte-identical index and numerical-array hashes.

The criteria follow the existing exact forward/transpose/projection-derivative
tests and make the 2 mm / 10 mm five-cell representability rule explicit.
