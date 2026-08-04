# G4 B2.0 cylinder coarse porous restart-field binding

Date: 2026-08-04

## Decision

Adopt **Option C: correct the representation-specific restart-field contract,
then obtain a fresh coarse prefix before any medium execution.**  The fresh
coarse prefix must use a new immutable destination and execute the canonical
body-fitted/porous pair in that order.  It must not overwrite, repair in
place, or combine records with the failed v6 artifact.

This is an evidence-integrity correction to the two-phase runtime protocol.
It changes neither the B2.0 cylinder physical problem, discretisation,
grids, force or `Cp` conventions, nor any numerical acceptance threshold.
Raw mass and stationarity are explicitly `evaluated: false` until the
governing six-case, three-grid evidence-extraction gate is reached.

## Retained v6 failure evidence

The ignored raw artifact
[`cylinder_runtime_coarse_v6`](../../examples/g4_b2_laminar/runs/cylinder_runtime_coarse_v6/)
is failed evidence and remains intact.  Its body-fitted/coarse case passed
Phase A and its exact 200-step Phase B.  Its porous/coarse Phase A reached
the required convergence marker, `SIMPLE solution converged in 813
iterations`, but Phase B terminated fatally while constructing the Brinkman
option:

```text
cannot find file "/case/813/beta"
```

The phase-B log selected `cfdSdfLinearBrinkman` and
`porousCylinderResistance` before this error.  This does not prove a valid
porous restart, a coarse prefix, or any physical comparison.  v6 must remain
failed raw evidence; it must not be relabelled as a pass, used to start
medium, or merged with a replacement run.

## Corrected restart contract

Before Phase B, the runner must materialize at the Phase-A final time exactly
the fields required by the representation, then archive and hash that
restart state.  The required fields are:

| Representation | Phase-A restart fields | Phase-B terminal fields |
| --- | --- | --- |
| Body-fitted | `U`, `p`, `phi` | `U`, `p` |
| Porous Cartesian | `U`, `p`, `phi`, `beta` | `U`, `p`, `brinkmanResistance` |

For a porous case, the materialized `<phase-A-final-time>/beta` must be a
byte-identical copy of immutable compiled `0/beta`.  Its original SHA-256,
materialized-file SHA-256, and archive-file SHA-256 must all match.  The
phase-A restart archive and manifest must include `beta`; its tree hash must
bind all required restart files.  A mismatch, a missing field, or a tree/hash
binding failure is failed/inconclusive runtime evidence.

`brinkmanResistance` is a derived output, not a restart input.  It is not
archived or copied as a Phase-A field; the required evidence is its presence
only at the exact terminal Phase-B time together with the established
extension build/load provenance.  The Phase-A residual-control convergence
marker remains required before any restart archive or Phase B.  Phase B still
has no `residualControl`, runs exactly 200 steps, and retains the existing
per-step write/measurement contract.

## Required evidence and execution gate

Each fresh coarse case must retain the governing mesh and `checkMesh` logs,
Phase-A and Phase-B solver logs, phase dictionaries, exact phase-time
contracts, force/probe histories, final-field bindings, and a manifest/tree
binding for the restart archive.  The porous case must additionally retain
the immutable extension-source snapshot, digest-pinned container build log,
case-local library hash, `fvOptions`/`beta` hashes, solver option-selection
evidence, and terminal `brinkmanResistance` binding.

This is a **pre-fresh-coarse evidence-contract correction**, not a physics,
grid, solver, or roadmap change.  It adds no numerical threshold.  Each
per-case runtime-evidence record must explicitly state all of the following:

| Evidence item | Required coarse-record state |
| --- | --- |
| Residual | The Phase-A convergence result and its extracted residual evidence. |
| Continuity / mass balance | The raw continuity or normalized-mass value and its evaluation status; no threshold is introduced at this prefix stage. |
| Stationarity | `evaluated: false` and a deferred reason that identifies the missing six-case three-grid force/`Cp` extraction gate. |

For every porous case, the raw runtime artifact itself must self-contain an
immutable extension-source snapshot and a manifest that verifies that
snapshot.  The per-case evidence must bind the source snapshot SHA-256 and
its tree hash, the digest-pinned container build assertion, and the
case-local library load assertion.  A source snapshot or manifest that is
missing, outside the artifact, fails verification, or is not bound to these
build/load assertions makes the porous case failed or inconclusive; it cannot
be used as the fresh coarse prefix.

### Extension snapshot exactness gate

The accepted extension-source snapshot is an **exact, manifest-bound set of
regular files**.  Before its container build begins, the runner must enumerate
the snapshot actually present in the runtime artifact and fail closed unless
it is exactly the manifest's relative-path set: every listed entry must exist
as a regular file with the declared SHA-256, and no unlisted entry may be
present.  Symbolic links, Windows reparse points, directories where a file is
declared, device/special files, and every other non-regular entry are rejected
before Phase A.  The source tree hash must be computed from that verified
actual regular-file set, rather than from a requested copy list or an
unverified directory walk.

Consequently, a manifest mismatch, an unexpected file, or any disallowed file
type is a **pre-Phase-A fail-closed** outcome for the porous case: the build
must not start and no solver result may be recorded as usable evidence.  This
only tightens artifact provenance.  It changes no physics, threshold,
acceptance criterion, or roadmap phase, and the retained v6 artifact remains
failed evidence exactly as described above.

The coarse runtime artifact remains
`partial_runtime_completed_unqualified` even when both cases satisfy this
contract.  Medium and fine execution are forbidden until a fresh coarse
artifact passes all of the above raw-evidence checks.  The force, `Cp`,
Richardson, GCI, mass, and stationarity evaluator remains forbidden until one
fresh `--through-grid fine` artifact contains all six canonical cases.

## Rationale and scope

v6 shows that copying only `U`, `p`, and `phi` creates an invalid porous
restart because the finite-volume option reads the time-local `beta` field.
Making `beta` explicit and hash-bound preserves both OpenFOAM restart
semantics and the immutable compiled-input provenance.  This decision is
supported by the bounded `sol_g4_b2_coarse_evidence_correction` review and
the retained v6 logs/manifests named above.

Status: implementation and a fresh coarse runtime artifact are required.
