# G4 B2.0 cylinder two-phase runtime protocol

Date: 2026-08-04

## Decision

Run each B2.0 cylinder grid in two serial phases, preserving the fixed
physical problem, mesh contract, solver scheme, linear-solver tolerances, and
cross-fidelity thresholds in
[`2026-08-04-g4-b2-laminar-scope.md`](2026-08-04-g4-b2-laminar-scope.md) and
[`2026-08-04-g4-b2-cylinder-cross-fidelity-design.md`](2026-08-04-g4-b2-cylinder-cross-fidelity-design.md).
This protocol changes runtime evidence collection only; it does not relax or
replace a B2.0 acceptance criterion.

For every representation/grid pair, execute the following phases in one
case-local evidence bundle:

1. **Phase A — convergence:** keep `residualControl` at `p` and `U` equal to
   `1e-8`; retain the established linear-solver tolerance and all other
   dictionary settings; set `endTime = 4000` as a hard ceiling.
2. **Phase B — measurement restart:** restart from the final Phase-A fields
   for exactly 200 iterations, without `residualControl`; set
   `writeInterval = 200`; record force and pressure-probe values at every
   iteration.  Preserve the Phase-A final fields and the complete Phase-A and
   Phase-B solver/residual histories.

Phase B is a measurement tail, not an opportunity to continue until a desired
force or probe value is obtained.  It neither repairs a failed Phase A nor
redefines convergence.

## Runtime order and time limits

Run the six cases serially in this exact order:

1. coarse body-fitted, then coarse porous;
2. medium body-fitted, then medium porous;
3. fine body-fitted, then fine porous.

Stop the sequence when any case fails its phase, timeout, solver health, or
evidence-integrity requirement.  Do not consume later-grid runs to mask or
average away an earlier failure.

The per-case wall-clock limits are deliberately split by phase:

| Grid | Phase A timeout | Phase B timeout |
| --- | ---: | ---: |
| coarse | 900 s | 300 s |
| medium | 1800 s | 600 s |
| fine | 5400 s | 1800 s |

A timeout, fatal solver error, absent restart field, incomplete 200-iteration
tail, or missing required raw file is recorded as failed/inconclusive runtime
evidence according to the governing B2 decisions.  It is never a successful
cylinder comparison.

## Evidence extraction gate

The force, `Cp`, Richardson, and GCI extractor must not run until all six
case-local raw-evidence bundles are complete and hash-bound.  Required raw
evidence includes both phase dictionaries and manifests, commands/image
digest, final fields, restart provenance, solver and residual histories,
force histories, probe histories, mesh/geometry/field hashes, and fatal-log
status.  Only then may the extractor calculate the existing body-fitted
force split, porous total resistance, external `Cp`, and three-grid metrics.

This ordering prevents partial coarse/medium data, a Phase-A terminal field,
or a selectively sampled force series from being interpreted as a
cross-fidelity result.

## Preserved incident evidence

The earlier 120-second smoke-run failure remains retained as an immutable
runtime incident.  It is superseded for execution provenance by this
two-phase protocol, but remains evidence that the prior smoke configuration
did not supply B2.0 cylinder qualification.  It must not be deleted, relabelled
as a pass, or combined with the new six-case evidence series.

## Scope and status

This protocol does not change the B2.0 physical conditions, discretization,
force conventions, convergence thresholds, GCI requirement, porous-drag
tolerance, `Cp` tolerance, or qualification boundaries.  It is a required
runtime-evidence contract for the implementation of the selected cylinder
comparison.

Status: implementation required.
