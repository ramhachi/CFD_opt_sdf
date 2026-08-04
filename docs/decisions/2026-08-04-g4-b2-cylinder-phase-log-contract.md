# G4 B2.0 cylinder phase-log artifact contract

Date: 2026-08-04

## Decision

The B2.0 cylinder two-phase runner shall expose the already-generated
camel-case OpenFOAM solver logs, `log.simpleFoam.phaseA` and
`log.simpleFoam.phaseB`, as the sole public phase-log artifacts.  The runner
must not publish or require alternative underscore-named aliases such as
`log.simpleFoam.phase_a` or `log.simpleFoam.phase_b`.

A phase is runtime-successful only when all of the following are true:

- the phase command returns zero without a timeout;
- the selected camel-case solver log exists;
- that log contains no fatal solver indication; and
- the required final fields for the phase exist at the reported final time.

The existing two-phase protocol still additionally requires the Phase-B
restart and its exact 200-iteration measurement tail.  This decision only
repairs the identity and health check of the solver-log artifact; it adds no
physical, convergence, force, `Cp`, Richardson, GCI, or cross-fidelity
threshold.

## Retained v2 incident

`examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v2/` is retained as
immutable failed evidence.  Its body-fitted coarse Phase A command returned
zero, produced complete `U` and `p` fields at final time `1255`, and had no
fatal indication, but the runner searched for the non-existent
underscore-named `log.simpleFoam.phase_a` rather than the actual
`log.simpleFoam.phaseA`.  It therefore reported Phase A and the prefix as
failed.  That failure is an artifact-contract false failure, not a
qualification result and not evidence that Phase A met every runtime or
physical gate.

Do not edit, overwrite, relabel, or cite the v2 artifact as a pass.  It did
not execute Phase B or a complete six-case prefix, and it cannot support a
cylinder conclusion.

## Required replacement evidence

After the runner correction, create a fresh **v3** compilation and runtime
destination.  The v3 execution must independently satisfy the normal
prefix-complete staged runtime contract and the two-phase raw-evidence gate;
it must not reuse, append to, or repair the v2 artifact.  Only a complete
`--through-grid fine` v3 artifact may enter the force/`Cp` grid-series
evaluator.

This record is supported by the retained v2 runtime attempt and its
case-local `openfoam_run_summary.json`, plus the selected protocols in
[`2026-08-04-g4-b2-cylinder-runtime-protocol.md`](2026-08-04-g4-b2-cylinder-runtime-protocol.md)
and
[`2026-08-04-g4-b2-cylinder-staged-runtime-control.md`](2026-08-04-g4-b2-cylinder-staged-runtime-control.md).

## Scope and status

This is a public artifact-name and runner-health decision.  It changes no
B2.0 physical acceptance criterion and does not qualify the cylinder,
NACA, arbitrary external bodies, turbulent flow, adjoints, or the optimizer.

Status: implementation required; v2 remains failed incident evidence and a
new v3 compilation/runtime is required.
