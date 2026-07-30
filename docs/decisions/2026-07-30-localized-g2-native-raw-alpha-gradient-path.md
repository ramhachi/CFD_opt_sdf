# Localized G2 native raw-alpha gradient path

Date: 2026-07-30

## Decision

For the localized G2 finite-difference qualification, implement the native
`dJ/d(staged_raw_alpha)` exporter as a patch to a version-pinned OpenCFD v2512
solver/adjoint source tree.  Do not attempt to derive it from the public
objective extension API, and do not wrap or rename `topOSens` or
`topologySens` as a raw-alpha gradient.

The patch must be built in a pinned container/source revision and write a
response-specific field only after the complete
`alpha -> alphaTilda -> beta -> named response` adjoint chain has been
applied.  It remains coefficient-scaled at its native source; the already
declared single `coefficient -> N` factor is applied identically to the
response and to the gradient by the extractor.

## Evidence and rejected paths

The bounded `sol_local_filter_projection_contract` review inspected the
current extension.  `objectivePorousDirectionalForce::update_dJdb()` exposes
only the direct beta contribution.  The public extension has no audited API
for the filter/projection derivative plus flow-state adjoint contribution.
The new `stagedRawAlphaGradientExporter` therefore correctly fails closed.

- Extension-only derivation would omit the complete chain and is rejected.
- Adding JSON provenance to legacy `topOSens`/`topologySens` would assert, not
  prove, its response, stage, sign, scale, and ordering; it is rejected.
- A solver/adjoint patch is selected, but no API names or private layouts will
  be guessed before the pinned v2512 source is available.

At this decision time the Docker daemon is unavailable in the development
environment, so no live v2512 header audit or patched build has been claimed.

## Acceptance conditions

Before a localized G2 FD result can be called qualified, the patch artifact
must bind the source revision, image digest, patch hash, build log, library
hash, named response/adjoint, final time, alpha hash, grid hash, cell ordering,
and native coefficient units.  The emitted scalar field must be finite,
response-specific, and match the serial canonical cell count.  A small
filter/projection-enabled fixture and a real serial central FD must verify the
raw-alpha directional derivative's sign and scale.  Any missing identity,
chain stage, scale, or ordering remains an extraction refusal.
