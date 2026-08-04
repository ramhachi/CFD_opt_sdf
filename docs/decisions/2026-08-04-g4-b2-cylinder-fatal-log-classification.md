# G4 B2.0 cylinder fatal-log classification

Date: 2026-08-04

## Decision

Adopt reviewed option **A**: classify OpenFOAM solver logs line by line, and
exclude only the complete OpenFOAM startup-banner line

```text
trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).
```

from fatal-log detection. The banner records that OpenFOAM has enabled its
floating-point-exception trap; it is not itself evidence that an exception
occurred during the solve.

Actual `floating point exception`, `FOAM_SIGFPE`, or `SIGFPE` indications on
any other line remain fatal, as do `FOAM FATAL`, `Segmentation fault`, and
`MPI_ABORT`. The exclusion must match the complete banner line
case-insensitively; it must not suppress a substring occurrence in another
line or relax any other solver-health check.

This changes only the fatal-log classification used by the cylinder two-phase
runner. Command return code, timeout, required phase-log and final-field
artifacts, Phase-B restart and measurement-tail requirements, mesh checks,
residual/mass/stationarity evidence, provenance bindings, and all B2.0
physical and grid-series acceptance criteria remain unchanged.

## Retained v3 incident

The immutable coarse-prefix artifact at
`examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v3/` is retained. Its
body-fitted Phase A command returned zero, wrote complete `U` and `p` fields at
final time `1255`, and its solver log
`cases/body_fitted/coarse/log.simpleFoam.phaseA` has SHA-256
`3413ab33913027a1730140d68814c259b66380756ff23e562fa7c1058cb77155`.

The log contains the exact `trapFpe` startup banner above, not an actual
floating-point exception or another fatal indication. The prior
substring-based classifier therefore reported `fatal_log_clear=false` and
stopped the prefix. This is an artifact-classification false failure. It is
not a solver-health pass, a completed two-phase run, a complete six-case
prefix, or cylinder qualification.

Do not edit, overwrite, relabel, or cite the v3 artifact as a pass. It
remains diagnostic evidence of the rejected classifier behavior.

## Alternatives considered

- **A — line-aware exclusion of the exact `trapFpe` banner:** selected. It
  removes only the demonstrated false positive while retaining detection of
  actual fatal events.
- **B — allow every `FOAM_SIGFPE` or `SIGFPE` occurrence:** rejected. It
  would hide genuine floating-point solver failures.
- **C — ignore fatal-log evidence after a zero return code:** rejected. A
  process return code cannot replace fail-closed solver-health evidence.

## Required replacement evidence

Run a fresh **v4** compilation and runtime destination after implementing the
line-aware classification. It must independently satisfy the existing
prefix-complete staged runtime and two-phase raw-evidence contracts. It must
not reuse, append to, or repair v3. Only a complete `--through-grid fine` v4
artifact may enter the force/`Cp` grid-series evaluator.

The bounded `sol_g4_b2_cylinder_fatal_log_classification` review supports this
decision using the retained v3 log and runtime summary. The governing
contracts remain
[`2026-08-04-g4-b2-cylinder-runtime-protocol.md`](2026-08-04-g4-b2-cylinder-runtime-protocol.md),
[`2026-08-04-g4-b2-cylinder-staged-runtime-control.md`](2026-08-04-g4-b2-cylinder-staged-runtime-control.md),
and
[`2026-08-04-g4-b2-cylinder-phase-log-contract.md`](2026-08-04-g4-b2-cylinder-phase-log-contract.md).

## Scope and status

This decision does not change the B2.0 physical model, discretization,
convergence thresholds, force or `Cp` conventions, GCI requirement, porous
cross-fidelity tolerance, channel-before-cylinder order, or qualification
boundaries. It does not qualify cylinder, NACA, arbitrary external bodies,
turbulent flow, adjoints, or the optimizer.

Status: implementation and a fresh v4 runtime are required; v3 remains a
retained false-failure incident.
