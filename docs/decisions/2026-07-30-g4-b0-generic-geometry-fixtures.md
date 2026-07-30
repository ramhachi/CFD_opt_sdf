# G4 B0 generic geometry fixture pack

Date: 2026-07-30

## Decision

Advance the unblocked generic roadmap through G4 B0 before B1 numerical
topology. Add a YAML/STL-replacement fixture pack for sphere, box, finite
thickness plate, multi-component geometry, and an invalid STL. The fixtures
must exercise existing generic preflight and geometry snapshot paths without
benchmark-specific core branches.

## Acceptance

- Each valid fixture reaches preflight, snapshot, role report, and hash-bound
  result publication.
- The plate is watertight and has positive thickness/volume.
- The invalid STL fails closed and publishes no result bundle.
- A versioned index records family, input SHA-256, pass/reject reason, and
  result identity.
- Tests cover all cases and deterministic replay/order.

This is B0 evidence only. It does not claim a three-family/three-grid
acceptance set, B1 derivative qualification, OpenFOAM qualification, or any
resolution of the front-wing blocker.
