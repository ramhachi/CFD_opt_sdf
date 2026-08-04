# G4 B2.0 channel evidence extraction

Date: 2026-08-04

## Decision

Adopt **C** for the B2.0 plane-Poiseuille channel qualification evidence:
the project Python parser is the authoritative, deterministic extractor of
the saved OpenFOAM v2512 fields, and OpenFOAM v2512 `postProcess` is an
independent semantic check run in an immutable runtime copy.  Neither process
may alter the published runtime artifact.

The qualified result remains a fail-closed combination of the existing B2.0
analytic and three-grid gates with the run-quality gate below.  This decision
only fixes how the already completed v2 fields are extracted and checked; it
does not change B2.0 physics, its channel-before-cylinder order, or any of
the accuracy/order thresholds in
[`2026-08-04-g4-b2-laminar-scope.md`](2026-08-04-g4-b2-laminar-scope.md).

## Alternatives considered

- **A — `postProcess` only:** rejected.  It is a useful OpenFOAM semantic
  check but is not the authoritative evidence extractor, because its derived
  output and command semantics must themselves be recorded and independently
  checked.
- **C — direct parser plus `postProcess` cross-check:** selected.  The saved
  final `U`, `p`, `phi`, mesh, and logs can be parsed deterministically without
  changing a solved case.  A v2512 `postProcess` replay in a separate copy then
  checks that field locations, surface/area reductions, and units carry the
  intended OpenFOAM meaning.
- **D — manually entered metrics:** rejected.  Hand-entered profile, bulk, or
  pressure values do not bind to the final fields and cannot qualify B2.0.

## Immutable source and provenance

The evidence source is the published three-grid full run:

`examples/g4_b2_laminar/runs/channel_runtime_v2/g4_b2_channel_runtime_attempt.json`

It records the three compiled case hashes, the benchmark compilation hash
`08d66d758390944bd00e4e932df9815c4823d7a4b8be2804ab3472c75b230efa`, and
the v2512 Docker image digest
`opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319`.
The extractor must bind its input-file hashes and its output to that published
run artifact, including its published replay command.  It must not read a
temporary staging path as public provenance.

The direct parser reads only the published final fields and mesh/log files.
For the independent check, it first creates a fresh, disposable copy of the
published case.  `postProcess` output, commands, and logs live only in that
copy or in a separately published validation artifact; a successful check
must leave the source tree byte-identical.  A missing field, malformed field,
hash mismatch, parser failure, `postProcess` failure, or mismatch between the
two methods is **inconclusive**, never a substituted manual value.

## Initial v2 artifact supersession

The first generated artifacts,
`examples/g4_b2_laminar/runs/channel_evidence_v2_20260804.json` and
`examples/g4_b2_laminar/runs/channel_qualification_v2_20260804.json`, record
numerical metrics and runtime-health checks that meet their declared gates.
They are nevertheless **provenance-invalid and superseded**: they must not be
used to claim a B2.0 channel pass.

The invalidity is limited to provenance/evidence extraction, not to a changed
physical scope, numerical threshold, or solver result.  The qualification
artifact stored `solver_log_sha256` as a command hash rather than the hash of
the saved solver log.  Its `runtime.command` names a staging path that no
longer exists.  The independent `postProcess` command similarly records a
random temporary-directory path, and the mesh-agreement evidence is not yet
complete.  Those defects prevent an independent reader from binding the
reported metrics to the immutable published run, even though the values and
health checks themselves were recorded as passing.

Correct the extractor and regenerate, without re-running `blockMesh` or
`simpleFoam`, from the immutable published final fields and logs.  Publish the
replacement under new names
`channel_evidence_v3_20260804.json` and
`channel_qualification_v3_20260804.json`; retain the v2 files as failed
provenance evidence rather than overwriting them.  The v3 artifacts must bind
the actual saved solver-log hashes, a replayable published-case command (or a
path-independent command contract), deterministic independent-check
provenance, and complete generated-versus-final mesh agreement before the
unchanged B2.0 gates may be evaluated again.

## v3 audit and v4 replacement

The generated v3 values meet the unchanged numerical thresholds, but v3 is
also **superseded and must not be cited as a B2.0 pass**.  Its evidence did
not yet bind the two decision records and retained v2 source artifacts in the
published result, did not parse the OpenFOAM `class` and `dimensions` headers
of final `U`, `p`, and `phi`, and did not use OpenFOAM v2512 to emit and check
actual cell-centre coordinates.  In particular, an assumed x-fastest field
order, profile sampling at `x = 0.030 m`, pressure sampling at `x = 0.015 m`
and `0.045 m`, and all y cell centres were not independently demonstrated.

Publish the replacement as
`channel_evidence_v4_20260804.json` and
`channel_qualification_v4_20260804.json`, again without a solver rerun.  The
v4 extractor must name this record and the B2.0 scope record, bind the retained
v2 evidence/qualification artifacts as superseded sources, and save a
path-independent direct-parser command contract.  It must parse and enforce
the final-field classes/dimensions (including kinematic pressure
`[0 2 -2 0 0 0 0]`).  In a disposable v2512 copy, it must run both
`components(U)` and `writeCellCentres`, save canonical relative commands and
output hashes, and fail closed if `C` is absent or disagrees with every direct
coordinate/order/sampling assumption.  Temporary paths must not appear in the
published JSON.  The v2 and v3 files remain retained, superseded evidence.

## v3 artifact supersession and v4 re-qualification

The subsequently generated v3 artifacts,
`examples/g4_b2_laminar/runs/channel_evidence_v3_20260804.json` and
`examples/g4_b2_laminar/runs/channel_qualification_v3_20260804.json`, are
also **inconclusive and superseded**. They do not establish a B2.0 channel
pass. The v3 extraction corrected the earlier path/log binding defects, but
the Sol v3 provenance audit retained three independent deficiencies:

1. The v3 published artifacts do not name or bind the applicable decision
   records and immutable source artifacts.
2. The extractor did not verify the OpenFOAM headers and dimensions of final
   `U`, `p`, and `phi` before using their values.
3. The independent `postProcess` evidence did not independently verify its
   coordinates and sampling planes against the declared channel contract.

These are evidence-contract failures only. They neither invalidate nor
reinterpret the saved solver result, and they do not change the B2.0 physical
scope, numerical method, acceptance thresholds, or the required
channel-before-cylinder sequence. Retain the v3 artifacts as failed
provenance evidence; do not overwrite or relabel them as a pass.

The next artifact generation is **v4 re-qualification**. It must correct all
three deficiencies while preserving the immutable v2 runtime source and the
existing metric/health gates. A solver, `blockMesh`, or `simpleFoam` re-run is
not required: v4 may re-extract and independently validate the already saved
final fields, mesh, logs, and runtime artifact. The result remains
inconclusive unless every required v4 provenance, field-contract, and
independent-plane check passes in addition to the unchanged gates below.

## Fixed metric extraction contract

The direct parser and independent check use the following locations and unit
conventions for every coarse, medium, and fine case.

- Verify a single `blockMesh` block with the declared `x-fastest` ordering and
  one z cell before reducing any values.  The generated grid dimensions and
  final mesh must agree; otherwise the case is inconclusive.
- At `x = 0.030 m`, linearly interpolate the final cell-centre `U_x` values in
  x and retain every declared y cell centre.  This is the profile used for the
  relative L2 error against the analytic Poiseuille profile and for the
  developed, area-weighted bulk velocity.
- At `x = 0.015 m` and `x = 0.045 m`, sample final pressure on the corresponding
  x-normal cell faces and take the y-area-weighted mean on each section.  The
  OpenFOAM kinematic pressure is converted to Pa by multiplying by the declared
  density before evaluating `-(p_1-p_2)/(0.045-0.015)`.
- Preserve raw samples, interpolants/reductions, exact locations, source-file
  hashes, and both parser and `postProcess` results.  The previously fixed
  finest-grid L2/bulk/pressure limits and same-signed observed-order test are
  then evaluated unchanged.

## Required runtime-health gate

Before numerical accuracy is evaluated, each of the three cases must prove all
of the following from the saved v2 artifact and final files:

1. The exact image digest above, saved replay command, and run artifact agree;
   the runner has `returncode = 0`, did not time out, reports `Time = 2000`,
   and final `U`, `p`, and `phi` exist.
2. `blockMesh`, `simpleFoam`, runner stdout, and runner stderr contain no
   `FOAM FATAL`, segmentation-fault, floating-point-exception, or equivalent
   fatal signature.
3. `primal_final_residual` is the maximum final residual of `Ux`, `Uy`, and
   `p` at the final outer iteration.
4. `normalized_mass_imbalance` is
   `abs(final global continuity error) / (U_bulk * 2H * span)`.
5. `nonlinear_residual_stationarity` passes only when, over the final 100 outer
   iterations, every equation has initial residual at most `1e-6`, every final
   residual is at most its dictionary tolerance (`1e-10`), and the normalized
   mass imbalance is at most `1e-4`.

These are additional run-quality checks, not revisions to the existing
accuracy or three-grid acceptance criteria.  If a required iteration history
or final value cannot be extracted exactly, the status is inconclusive.

## Acceptance and limits

The qualification artifact must name this decision, the v2 source artifact,
the B2.0 scope decision, and both extraction commands.  It may report an
execution-completed/metrics-not-extracted state, but it may call the channel
gate passed only when all three parser evidence sets and all three independent
`postProcess` checks pass the binding, runtime-health, metric, and existing
three-grid gates.

This is channel evidence only.  It is not a cylinder, NACA, external-body,
turbulent-flow, adjoint, or optimizer qualification.

## v4 source-bound re-qualification result

The immutable v2 OpenFOAM v2512 runtime was re-qualified by the following v4
source-bound artifacts:

- `examples/g4_b2_laminar/runs/channel_evidence_v4_20260804.json`
- `examples/g4_b2_laminar/runs/channel_qualification_v4_20260804.json`

The v4 evidence passes the unchanged three-grid analytic profile, bulk, and
pressure-gradient gates; the runtime-health gate; final field/mesh bindings;
and the independent OpenFOAM v2512 `postProcess` `U` component and
cell-centre checks.  It therefore passes the B2.0 **channel-only** gate.

The v2 and v3 artifacts remain provenance-invalid or superseded evidence and
must not be deleted, relabelled, or cited as a B2.0 pass.  This result changes
neither the scope nor the thresholds in this record or in
[`2026-08-04-g4-b2-laminar-scope.md`](2026-08-04-g4-b2-laminar-scope.md): it
does not qualify cylinder, NACA, arbitrary external bodies, turbulent flow,
adjoints, or the optimizer.

## Evidence retention

Selected retention policy: track only the two compact, source-bound v4 JSON
artifacts in Git:

- `examples/g4_b2_laminar/runs/channel_evidence_v4_20260804.json`
  (`22cee8360c3ffae3d07aca9a340d252dd81fd0aa0db6a423f871d2f6164a92b7`)
- `examples/g4_b2_laminar/runs/channel_qualification_v4_20260804.json`
  (`e8a8f113b75d4b2aa1cb3894b964815b9193cc11f5ea8cfb60a9cc13a7d6d079`)

The v2/v3 artifacts and the OpenFOAM runtime bundle remain generated, ignored
local evidence. They are non-portable and are not tracked. When a separately
retained raw bundle is available, its file hashes can be checked against the
hashes recorded in the v4 JSON. A clone of this repository alone therefore
cannot independently rerun the solver or recreate the complete runtime
evidence.

An external archive is not yet a qualification artifact. It may be adopted
only after it contains the complete raw bundle, a manifest, and checksums as
an immutable release asset. This retention decision changes neither the v4
channel-only pass nor any physical or numerical acceptance criterion.
