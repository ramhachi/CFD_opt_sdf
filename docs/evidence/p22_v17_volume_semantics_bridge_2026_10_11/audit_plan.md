# P22–v17 volume semantic bridge: frozen audit plan

Frozen before invoking a volume evaluator in this audit, 2026-10-11.
Integration/source parent: `0973f9efc7c7f469978d67c77a95fcfd365d58d5`.
Branch: `exp/p22-v17-volume-semantics-2026-10-11`.
Evidence class: solver-free contract, arithmetic, and state-lineage audit.

## Fixed inputs and order

1. A: exact original v16 NPZ, registered file SHA
   `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`,
   state SHA `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`.
2. B: canonical pre-LOWDIM v17 NPZ, registered file SHA
   `7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`,
   state SHA `02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb`.
3. C: reconstruct only the already selected LOWDIM-03 +1.25 mm state from
   B and the saved robust direction, using existing `construct_state` without
   recomputing a proposal. Require state SHA
   `81d24fe4a66704ed469f560b7396b4c0cbf6810ef8082e710f002145ca6e3a65`,
   NPZ SHA `0ce3256b0f3e5c919caeb2ac1b36f1a33838f34c767c091cb89bda0234ac750b`,
   phi Fortran SHA `b02dc49c39c3e8895befd5a95ae007ccf04fb2582064e8d79bd0f4c57c55286e`.
4. D is optional: only if A–C and code-path checks leave a material question.
   The existing eight LOWDIM-04A perturbation records remain historical evidence.

Input paths are resolved read-only from retained host artifacts. Missing or
mismatched inputs fail closed. Exact A hard volume must equal Python float
`0.12612500000000004`; otherwise stop as INCONCLUSIVE before B/C measurement.

## Fixed measures and checks

For A/B/C report the existing authoritative
`cfd_sdf.design.volume_semantics.sharp_volume_m3`, its solid-center count,
all-center count, `_corner_mean` Float32/strict-negative/zero-fluid semantics;
the existing `smoothed_volume_and_gradient` value, gV, epsilon and gradient
hash; LOWDIM `build_lowdim01_inputs.geometry` sharp and smooth measures;
and diagnostic node occupancy (not a gate). Record file/state/phi/grid hashes,
shape, origin, spacing, source geometry identity and evaluator source hashes.
Compute C-minus-B hard/smooth differences. Compare same-source v16/v17 lattice
lineage without asserting equal trilinear zero sets or continuum volume.
Trace the actual #51 generator, not only a matching function name. Inspect
retained source records if that generator was an ad-hoc command.

## Predeclared classifications

- SEMANTIC_MISMATCH_CONFIRMED: #51 used a different measure from P22 hard.
- TRUE_PARENT_INFEASIBLE: original A reproduces, contract portability is
  unambiguous, B is within the limit, and C alone exceeds it.
- CONTRACT_NONPORTABLE_ACROSS_LATTICE: A reproduces; B and C exceed the v16
  limit with unchanged (or nearly unchanged) C-minus-B hard count; verified
  same physical reference source, changed lattice/sampling, and no portable
  reference migration in v1 explain the comparison failure.
- INCONCLUSIVE: reference replay, evaluator identity, lineage, source physical
  identity, measure separation, or numerical consistency cannot be established.

Classification stays draft until independent review. If C is supported, write
only a P22-v2 migration proposal based on the pre-optimization source geometry,
never the selected parent. Do not register it or change a limit.

## Validation and stop

Small reproducer with focused tests: original expected value, Float32 center
mean, exact-zero fluid, distinct v16/v17 identities, fixed state/grid hashes.
Run compileall src/scripts/tests, full pytest against the same-runtime unchanged
parent baseline (normalize parametrized IDs if needed), and diff --check.
Compare failure sets; never call a failing suite all-pass. Review hashes and
assertions independently before freezing classification and SHA256SUMS.
No CFD, Kaggle, preregistration, coefficient solve, alternate parent,
reinitialization, volume-contract/threshold change, or qualification. Preserve
#51 blocker bytes; all qualification flags false, selected_delta null, and
shape_update_allowed false. Root handles Git/issue actions after review.
