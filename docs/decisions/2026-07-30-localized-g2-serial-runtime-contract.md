# Localized G2 serial runtime contract

Date: 2026-07-30

## Decision

Use the Sol-reviewed choices `1=B`, `3=A`, and `4=A` for the localized G2
runtime boundary:

1. **B — explicit compiler contract.**  The compiler emits one immutable
   response/raw-alpha-gradient contract for each serial G2 flow case.  The
   later extractor reads only that contract; it must not infer objective names,
   time directories, field names, units, or ordering from OpenFOAM output.
2. **3=A — force units at the compiler boundary.**  The native source is a
   dimensionless response coefficient.  The compiler converts it to N with
   `q_ref = 0.5 * rho * ||Uinf||^2` and `factor = q_ref * Aref`; the exact
   same factor is reserved for the raw-alpha gradient.  This changes units,
   not the declared derivative variable or chain rule.
3. **4=A — serial-only qualification slice.**  A parsed single,
   ungraded, axis-aligned `blockMeshDict`, canonical `x-fastest` cell order,
   no processor directories, and no parallel/decomposition commands are
   required.  Parallel reconstruction is deliberately not accepted here.

The opt-in compiler mode emits `AllrunAdjoint` with POSIX LF endings.  The
script checks the strict staged alpha value hash from
`localized_openfoam_alpha_case.json`, copies exactly `0.orig/alpha` to
`0/alpha`, refuses `processorN` directories, then launches
`adjointOptimisationFoam -case .`.  Its hash and command are recorded in the
serial runtime contract; the default runtime checks that hash and the staged
alpha binding again before launch.

## Acceptance evidence

For a compiled serial case, all of the following must hold before an execution
can be treated as eligible input to extraction:

- `localized_g2_serial_runtime.json` binds compilation metadata, parsed
  `blockMeshDict` byte hash, grid hash/count, and `x-fastest` ordering;
- `localized_g2_cell_centre_ordering.json` records the full-cell-centre
  float64 little-endian hash, index formula, and boundary probes;
- `localized_g2_response_gradient_contract.json` binds exact flow/response/
  named-adjoint IDs, final-time selection, N units, and the same conversion
  factor for response and gradient;
- `AllrunAdjoint` is UTF-8, LF-only, executable on POSIX, hash-bound, and has
  the expected serial command; and
- no `processorN` directory or parallel/decomposition command appears in the
  compiled template or fresh runtime case.

The emitted response and gradient source paths are declarations only.  A
missing native exporter is a fail-closed extraction error, not evidence of a
zero gradient or a successful FD check.

## Limits

This decision does not implement the C++ `dC/d(raw_alpha)` exporter, change
the raw-alpha gradient meaning, provide processor reconstruction, qualify an
OpenFOAM run, validate an FD ladder, establish body-fitted agreement, or claim
an optimizer iteration.  Those remain later G2/G4 gates.
