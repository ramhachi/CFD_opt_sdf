# Localized reference topology role scope

Date: 2026-07-30

## Decision

Keep the rejected localized-reference topology report as failure evidence and
do not start localized FD, OpenFOAM FD, or optimization from it.  Correct the
topology evaluator's role scope before re-evaluation; do not modify STL
assets, thresholds, design-domain limits, or root declarations to make this
fixture pass.

Connectivity, erosion, and manufacturing-feature checks apply to the design
topology solid only:

```text
(active_design_mask AND rho_projected >= 0.5) OR declared_root_masks
```

Non-root `fixed_solid` geometry remains immutable CFD/excluded geometry, but
is outside the design topology solid for these checks.  The current `mounts`
root group remains one required group.  Multiple required root groups must
remain fail-closed until the evaluator has explicit group-specific masks; a
union must not be treated as proof for every group.

## Failed evidence preserved

The first full-resolution report is
`examples/g2_openfoam_compile/runs/localized_reference_topology_surface_v2_20260730/localized_reference_topology.json`
(SHA-256
`0c69d69da8795e7083f2c04ad0d2e2d002faf38ffacd6e1685ae35d71781c9df`).
It is rejected and remains authoritative for the pre-correction evaluator.

Its unrooted component has 847,000 cells in
`x=0.246..0.324 m`, `y=-0.274..0.274 m`, `z=0.277..0.429 m` and is the
non-design `vehicle_nose`: `active=0`, `fixed=1`, `root=0`.  The previous
formula included every fixed-solid cell, incorrectly demanding that this
external component connect to the front-wing mounts.

The report also found 2,833 minimum-solid-width and 27,512 minimum-gap
violations.  Those findings are not dismissed by this role correction.  A
new report stays rejected unless all unchanged checks pass after re-evaluation.

## Acceptance conditions

- a non-root fixed nose-only fixture causes no root-connectivity failure;
- connected root plus active design material passes nominal and eroded
  connectivity checks;
- an unrooted active design island is still rejected;
- multiple required root groups without group-specific masks are rejected;
- new reports bind the same geometry/state/STL/grid/policy hashes; and
- no FD preparation, OpenFOAM FD, or optimizer iteration begins until a new
  full-resolution report succeeds with zero feature/gap/connectivity failures.
