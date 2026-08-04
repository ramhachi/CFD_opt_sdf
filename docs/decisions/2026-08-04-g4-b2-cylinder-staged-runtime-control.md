# G4 B2.0 cylinder staged runtime control

Date: 2026-08-04

## Decision

Adopt a **prefix-complete, grid-major runtime control contract** for the
selected B2.0 cylinder cross-fidelity benchmark.  This decision governs only
the execution and partial-artifact protocol.  It preserves the physical
problem, grids, two-phase convergence/measurement protocol, force convention,
`Cp` convention, GCI calculation, and every numerical acceptance threshold in
[`2026-08-04-g4-b2-laminar-scope.md`](2026-08-04-g4-b2-laminar-scope.md),
[`2026-08-04-g4-b2-cylinder-cross-fidelity-design.md`](2026-08-04-g4-b2-cylinder-cross-fidelity-design.md),
and
[`2026-08-04-g4-b2-cylinder-runtime-protocol.md`](2026-08-04-g4-b2-cylinder-runtime-protocol.md).

An executed cylinder command must require `--through-grid` with exactly one of
`coarse`, `medium`, or `fine`.  The request means “execute the complete
canonical prefix through this grid”, not “resume from another runtime
artifact” and not “run this grid alone”.

The canonical sequence is fixed and grid-major:

1. `body_fitted/coarse`;
2. `porous_cartesian/coarse`;
3. `body_fitted/medium`;
4. `porous_cartesian/medium`;
5. `body_fitted/fine`;
6. `porous_cartesian/fine`.

Therefore `--through-grid coarse` runs entries 1–2, `--through-grid medium`
runs entries 1–4, and `--through-grid fine` runs entries 1–6.  A medium or
fine invocation independently reruns every preceding pair as a fresh,
standalone prefix from the immutable compilation input.  It must not import,
append to, or treat a prior coarse/medium artifact as current evidence.

## Partial runtime artifacts

Every successful prefix execution writes one immutable partial runtime
artifact.  It is required to contain, at minimum:

- a schema/kind identifier and the requested `through_grid`;
- the compilation, specification, extension-source, and digest-pinned image
  bindings needed by the underlying case manifests;
- the complete canonical six-case order and the exact executed prefix;
- one case-local, two-phase raw-evidence record and status for every member of
  that prefix, including final fields, restart provenance, logs, hashes, and
  runtime-health data required by the existing protocol;
- `status: partial_runtime_completed_unqualified`, `qualified: false`, and an
  explicit statement that no force, `Cp`, Richardson, GCI, or
  cross-fidelity result has been evaluated; and
- the next required condition: all six canonical case records from one
  `--through-grid fine` execution, followed by the force/`Cp` grid-series
  extractor.

The two-case coarse and four-case medium artifacts are preserved runtime
evidence, but are not inputs to a B2.0 physical conclusion.  They may support
diagnosis only.  They cannot be concatenated with one another or with a
separate fine run to form a six-case series.

## Failure handling

On a case, phase, timeout, solver-health, provenance, or raw-evidence failure,
the runner stops immediately.  Its partial artifact records
`stopped_by: runtime_failure`, identifies the failed canonical case and phase,
and contains no later-grid or later-representation run.  No next grid may be
started in that invocation.

The runtime protocol's per-representation/phase **75% hard-timeout guard** is
also a no-automatic-progression gate.  A completed case at or above that
guard records its elapsed time and guard result, then requires a bounded
`sol_` re-review before a later grid may be started.  This is distinct from a
hard timeout: it preserves potentially complete raw evidence while forbidding
an automatic escalation whose remaining budget has not been reviewed.

The failed artifact remains retained incident evidence.  Re-running the
benchmark requires a new immutable destination and the requested canonical
prefix; it does not repair, overwrite, or silently replace the failed
artifact.

## Evaluation gate

The cylinder evaluator may run only on an artifact produced by
`--through-grid fine` that contains all six canonical cases in the exact order
above, each with complete required raw evidence and canonical source/image
bindings.  It must reject a coarse or medium artifact, a subset, a reordered
series, a series assembled from multiple invocations, or one missing either
the final-grid body-fitted/porous pair.

Only after that gate may the existing force and external-`Cp` grid-series
extraction calculate the unchanged Richardson, GCI, and porous/body-fitted
comparison criteria.  Execution completion, including a complete six-case
prefix, remains unqualified until that evaluator passes all pre-existing
requirements.

## Scope and status

This is an artifact-provenance and staged-execution decision.  The timeout
guard adds no physical, evidence, or numerical acceptance threshold; it does
not alter the declared cylinder problem, and does not qualify cylinder, NACA,
arbitrary bodies, turbulent flow, adjoints, or the optimizer.

Status: implementation required.
