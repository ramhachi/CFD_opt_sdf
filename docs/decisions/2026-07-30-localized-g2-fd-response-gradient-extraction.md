# Localized G2 response and raw-alpha-gradient extraction

Date: 2026-07-30

## Decision

Adopt Sol option B: a completed localized G2 FD run is followed by a separate
immutable response-and-gradient extraction artifact.  The extractor reads only
a verified prepared experiment, a completed immutable run report, a
compiler-generated response/gradient contract, and explicit
`flow_case_id`/`response_id`/named-adjoint identifiers.

The artifact contains all fresh baseline and FD-ladder primal response values,
plus a canonical native-`float64` `dJ_dalpha.npy` field.  Its only declared
gradient variable is `raw_alpha`, with the exact meaning:

```text
dJ = sum_i g_alpha[i] * d(alpha_i)
```

The extractor does not apply `E.T`, the projection derivative, or the filter
adjoint.  Those operations remain exclusively in the later FD validator:

```text
g_rho_raw = F.T(P_prime * (E.T * g_alpha))
```

## Compiler contract

The required compiler-generated JSON contract explicitly declares the response
and flow identifiers, the one response source and JSON selector, response
units, identity scale/conversion, recorded-final-time selection, adjoint NPY
source, `raw_alpha` derivative meaning, gradient units, and either the
single-case canonical `x-fastest` ordering rule or explicit per-processor
global labels and scatter reconstruction rule.  The contract also binds the
compiled metadata hash and the parsed CFD-grid hash/count/order.

There is no filename inference.  A field named `topologySens`, an objective
file whose name appears related, a filtered/penalized field, an undeclared
conversion, or a decomposed field without complete unique global labels is
rejected.

## Evidence and rejection boundary

The extractor verifies the prepared/run hashes, every run-case output-tree
hash, staged alpha manifest, alpha binding, actual `blockMeshDict`, grid,
contract compiler hash, selected final-time source, response scalar, and
gradient layout.  It rejects missing/multiple/nonfinite values, hash or grid
mismatches, final-time mismatch, non-identity or unknown scale, unknown
gradient variable, and invalid decomposition labels/order before publishing an
output directory.

Synthetic field-tree tests cover successful scalar/gradient extraction, a
non-scalar response rejection, tampering rejection, and bad ordering
rejection.  No actual OpenFOAM run is claimed by this decision.

## Rationale

`sol_local_filter_projection_contract` selected option B after comparing:

1. interpreting existing OpenFOAM filenames such as `topologySens` directly;
2. an explicit post-run extraction artifact; and
3. leaving all runs permanently inconclusive.

Option 1 cannot prove response identity, raw-alpha differentiation, scale,
final-time selection, or global ordering.  Option 3 cannot produce localized
G2 evidence.  Option B preserves the execution/interpretation boundary and
keeps the mathematical chain exact.

## Limitation

The extractor is implemented but is not yet wired into the numerical validator
or a production compiler-generated runtime contract.  Until an actual G2
OpenFOAM run produces an accepted extraction artifact, this is implementation
evidence only: it does not qualify localized FD, native v2, continuous
manufacturability, or an optimizer iteration.
