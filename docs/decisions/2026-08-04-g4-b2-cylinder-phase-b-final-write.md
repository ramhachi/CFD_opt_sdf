# G4 B2.0 cylinder Phase-B terminal-write evidence

Date: 2026-08-04

## Decision

Adopt the Phase-B terminal-write contract defined in
[`2026-08-04-g4-b2-cylinder-runtime-protocol.md`](2026-08-04-g4-b2-cylinder-runtime-protocol.md)
for the next fresh cylinder runtime artifact, v5.  This is an
evidence-integrity correction only.  It changes neither the physical problem,
discretisation, grids, solver scheme, force convention, `Cp` convention, nor
any B2.0 numerical acceptance threshold.

For each case, retain the fully hash-bound Phase-A restart state before Phase
B under the case-local non-time path
`evidence/phase_a_restart/<phase-A-final-time>/`, with
`evidence/phase_a_restart_manifest.json`.  The manifest records the source
time, each archived-file SHA-256, and an archive-tree SHA-256.  Run Phase B
from that original state to `phase_a_final_time + 200` with `deltaT = 1`,
`writeControl = timeStep`, `writeInterval = 1`, `purgeWrite = 1`, and no
`residualControl`.  The terminal Phase-B time directory must therefore hold
the final `U` and `p`; porous cases must also retain the required resistance
field.  `writeAtEnd` is not an acceptable substitute for the per-step write
contract.

## Retained v4 failure evidence

The source-bound v4 coarse body-fitted attempt is retained at
[`examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v4/g4_b2_cylinder_runtime_attempt.json`](../../examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v4/g4_b2_cylinder_runtime_attempt.json).
Its Phase A completed at `1255`.  Its Phase-B solver log reached `Time = 1455`
and `End`, and the force/probe histories ran, but the retained time directories
are only `0`, `1255`, and `1400`; the final saved fields are consequently at
`1400`, not `1455`.

The failure arose under the former `writeInterval = 200`, `purgeWrite = 0`,
`writeAtEnd yes` control.  The v4 record remains failed/inconclusive runtime
evidence.  It must not be deleted, repaired in place, combined with later
cases, or cited as a successful prefix or a cylinder result.

## v5 runtime-evidence acceptance

A v5 case is runtime-complete only when its hash-bound raw bundle contains all
of the following:

1. a Phase-B log with the exact 200 restart steps from
   `phase_a_final_time + 1` through `phase_a_final_time + 200`, followed by
   `End`, and no fatal solver record;
2. a terminal directory at exactly `phase_a_final_time + 200`, containing
   `U` and `p` (plus the porous resistance field where applicable);
3. exactly 200 post-restart force and pressure-probe samples;
4. the non-time Phase-A restart archive with a manifest that binds the
   archived fields and their SHA-256 hashes to the Phase-A final time; and
5. the existing phase dictionaries, image/command provenance, mesh and field
   bindings, residual/mass/stationarity evidence, and all other governing B2
   runtime requirements.

Missing, unhashable, or inconsistent evidence is inconclusive/failed.  A
runtime-complete case remains only an input to the existing six-case
cross-fidelity gate; it is not a B2.0 cylinder qualification by itself.

## Rationale and scope

The measured v4 discrepancy proves that `writeAtEnd yes` does not guarantee a
terminal field in the OpenFOAM v2512 execution path used here.  One field
write per Phase-B step increases I/O, but `purgeWrite = 1` bounds retained
Phase-B time directories to the terminal state.  The explicit pre-Phase-B
archive preserves the restart provenance that purge would otherwise remove.

This decision is supported by the bounded
`sol_g4_b2_phase_b_final_time` review and the retained v4 runtime record.  It
does not qualify cylinder, NACA, arbitrary external bodies, turbulence,
adjoints, or the optimizer.

Status: implementation and a fresh v5 runtime are required.
