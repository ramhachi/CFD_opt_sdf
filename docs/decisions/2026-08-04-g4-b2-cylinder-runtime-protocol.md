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
2. **Phase B — measurement restart:** before starting this phase, copy the
   complete Phase-A restart state (`U`, `p`, `phi`, and every other field
   required to restart the representation) to the case-local non-time
   evidence path `evidence/phase_a_restart/<phase-A-final-time>/`, and write
   `evidence/phase_a_restart_manifest.json`.  The manifest shall name the
   source time, SHA-256 each archived field, and bind the archive tree hash.
   Phase B then restarts from the original final Phase-A fields for exactly
   200 iterations, without `residualControl`, with `deltaT = 1`,
   `writeControl = timeStep`, `writeInterval = 1`, and `purgeWrite = 1`.
   Record force and pressure-probe values at every iteration.  Preserve the
   archive and the complete Phase-A and Phase-B solver/residual histories.

Phase B is a measurement tail, not an opportunity to continue until a desired
force or probe value is obtained.  It neither repairs a failed Phase A nor
redefines convergence.  Its extra per-step field writes are a deliberate
evidence-integrity cost: `purgeWrite = 1` retains only the terminal Phase-B
time directory, while the separately hashed non-time archive preserves the
otherwise-deleted Phase-A restart state.

## Runtime order and time limits

Run the six cases serially in this exact order:

1. coarse body-fitted, then coarse porous;
2. medium body-fitted, then medium porous;
3. fine body-fitted, then fine porous.

Stop the sequence when any case fails its phase, timeout, solver health, or
evidence-integrity requirement.  Do not consume later-grid runs to mask or
average away an earlier failure.

The per-case wall-clock limits are deliberately split by representation and
phase.  The body-fitted limits are unchanged.  The porous Phase-B limits are
representation-specific because native per-step porous measurement/output
writes have a materially higher wall-clock cost; this changes no physical or
numerical acceptance criterion.

| Grid | Body Phase A | Body Phase B | Porous Phase A | Porous Phase B |
| --- | ---: | ---: | ---: | ---: |
| coarse | 900 s | 300 s | 900 s | 600 s |
| medium | 1800 s | 600 s | 14400 s (porous Phase-A v2 only) | 3600 s |
| fine | 5400 s | 1800 s | 5400 s | 21600 s |

The runner must apply a **75% hard-timeout guard** independently to every
representation/phase limit.  If a case reaches or exceeds 75% of its assigned
hard timeout, it must not automatically progress to a later grid, even if the
phase otherwise completes.  It records the elapsed time and guard outcome as
runtime evidence and requires a bounded `sol_` re-review before any
next-grid execution or timeout change.  A hard timeout remains a failed or
inconclusive phase and stops the prefix immediately.

A timeout, fatal solver error, absent restart field or archive, incomplete
200-iteration tail, terminal field time different from the declared Phase-B
end time, or missing required raw file is recorded as failed/inconclusive
runtime evidence according to the governing B2 decisions.  It is never a
successful cylinder comparison.

### Medium porous Phase-A v2 exception and watchdog

The retained medium-prefix v1 artifact failed in
`porous_cartesian/medium` Phase A.  Its 1800-second hard timeout terminated
the case after the last complete solver record `Time = 675` at `ClockTime =
1787 s` (a subsequent `Time = 676` banner is incomplete).  No Phase B or fine
case was started.  This is failed raw evidence, not a convergence result and
not a justification for changing the cylinder physics, discretization,
residual controls, linear-solver tolerances, measurement contract, or any
cross-fidelity acceptance threshold.

For one fresh, immutable **medium porous Phase-A v2** execution only, set the
hard timeout to **14400 s**.  The scope of this exception is exactly
`porous_cartesian/medium` Phase A; the body-fitted limits, all Phase-B limits,
and the fine-grid Phase-A limit remain as stated above.  In particular, the
fine porous Phase-A timeout remains **5400 s** pending evidence from this
fresh v2 medium run.  The v2 artifact must use the identical compiled
physical case and controls apart from the timeout/watchdog machinery.

The ordinary 75% guard becomes `10800 s` for this v2 Phase A.  A converged
Phase A at or after `10800 s` is **inconclusive** for progression: preserve
its raw evidence, but do not run its Phase B and do not start fine in that
invocation.  A bounded Sol re-review is required before any later-grid or
Phase-B execution.  This guard does not relabel the Phase-A convergence check
or make a physical acceptance criterion less strict.

While this v2 Phase A is running, the runner must parse the solver log and
apply a **600-second monotonic-Time watchdog**.  If the process remains alive
but no strictly greater completed `Time = <n>` record is observed for 600
seconds, stop the phase and record the explicit terminal reason
`runtime_stalled_no_advance`; do not start Phase B or fine.  Normal progress
that produces strictly increasing Time records resets the watchdog.  The
watchdog is a runtime-health/evidence safeguard, not a convergence substitute
or an additional physical metric.

On Windows, a cleanup `WinError 32` (a transient file-sharing/lock failure)
must be retried and reported in a separate cleanup record.  It is not itself
solver health: the solver/phase status must remain bound to the solver exit,
timeout, log-health, and raw-evidence checks.  Conversely, a successful
cleanup retry cannot convert a failed solver phase into a pass.

## Evidence extraction gate

The force, `Cp`, Richardson, and GCI extractor must not run until all six
case-local raw-evidence bundles are complete and hash-bound.  Required raw
evidence includes both phase dictionaries and manifests, commands/image
digest, the terminal Phase-B fields, the pre-Phase-B Phase-A-restart archive
and its manifest, restart provenance, solver and residual histories, force
histories, probe histories, mesh/geometry/field hashes, and fatal-log status.
The Phase-B log must show every exact integer time from
`phase_a_final_time + 1` through `phase_a_final_time + 200`, followed by
`End`; the terminal directory must match that final time; and both force and
probe histories must contain 200 post-restart samples.  Only then may the
extractor calculate the existing body-fitted force split, porous total
resistance, external `Cp`, and three-grid metrics.

This ordering prevents partial coarse/medium data, a Phase-A terminal field,
or a selectively sampled force series from being interpreted as a
cross-fidelity result.

## Preserved incident evidence

The earlier 120-second smoke-run failure remains retained as an immutable
runtime incident.  It is superseded for execution provenance by this
two-phase protocol, but remains evidence that the prior smoke configuration
did not supply B2.0 cylinder qualification.  It must not be deleted, relabelled
as a pass, or combined with the new six-case evidence series.

The retained v4 coarse body-fitted runtime is also failed evidence:
[`examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v4/g4_b2_cylinder_runtime_attempt.json`](../../examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v4/g4_b2_cylinder_runtime_attempt.json)
records a clean Phase A at `1255` and a Phase-B solver log that reaches
`Time = 1455` and `End`, but `foamListTimes -latestTime` and the saved field
directory stop at `1400`.  The v4 template used `writeInterval = 200`,
`purgeWrite = 0`, and `writeAtEnd yes`; it did not produce a terminal `1455`
field.  This failure is retained without reinterpretation.  It is not a
completed Phase B, a successful coarse prefix, or cylinder qualification.

The retained v8 coarse-prefix artifact is likewise failed raw evidence:
[`examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v8/g4_b2_cylinder_runtime_attempt.json`](../../examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v8/g4_b2_cylinder_runtime_attempt.json).
Its porous/coarse Phase A converged at `813`, and its Phase B reached
`Time = 1010` of the required final time `1013` (197 of 200 measurement
steps).  At approximately 298 seconds it was then stopped by the existing
300-second hard timeout.  It must remain retained as failed evidence; it is
not a successful coarse prefix, must not start medium, and must not be
combined with later output.  The representation-specific Phase-B limits and
75% guard above are the Sol-approved correction for a fresh immutable
replacement artifact.

## Scope and status

This protocol does not change the B2.0 physical conditions, discretization,
force conventions, evidence requirements, convergence thresholds, GCI
requirement, porous-drag tolerance, `Cp` tolerance, or qualification
boundaries.  It is a required runtime-evidence contract for the
implementation of the selected cylinder comparison.

The bounded `sol_g4_b2_phase_b_final_time` review selected this write contract
over retaining the v4 `writeAtEnd` reliance.  The later bounded Sol timeout
review selected the representation-specific limits and guard above after v8.
The implementation and a fresh post-v8 runtime artifact are required.

The retained medium-prefix v1 timeout is also failed raw evidence.  Its
replacement must be a fresh v2 destination that executes the canonical prefix
through medium under the narrowly scoped medium-porous Phase-A exception and
watchdog above.  It must not overwrite, append to, or combine with v1.

Status: implementation and fresh post-v8/coarse execution, followed by a
fresh medium-porous Phase-A v2 execution, required.
