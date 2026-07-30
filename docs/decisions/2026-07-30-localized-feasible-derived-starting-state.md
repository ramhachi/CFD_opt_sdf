# Localized feasible derived starting state

Date: 2026-07-30

## Decision

Retain the direct-STL occupancy state and its rejected topology reports as
immutable benchmark evidence. Build a separately named, constraint-aware
*derived starting state* for the front-wing optimization path. The source STL
remains the only source geometry; the derived state is not direct STL geometry
and must never replace the asset or its direct occupancy artifact.

The initializer operates forward from raw density only. It uses the unchanged
policy radii to remove thin solid material and fill narrow external gaps,
preserves declared roots, never creates material outside the active domain or
inside forbidden cells, and runs for a bounded deterministic number of
iterations. Every candidate is then passed through the existing filter and
projection before the full topology evaluator decides success. No inverse
projection or raw-density reconstruction from a projected field is allowed.

## Evidence and rejected alternatives

The role-aware report
`examples/g2_openfoam_compile/runs/localized_reference_topology_role_aware_v1_20260730/localized_reference_topology.json`
(SHA-256
`647f2c1d28a98099fd176cca1f61d993f45a0985508f46343f53d3450d6ee52f`)
now passes nominal and eroded root connectivity but remains rejected with
2,328 minimum-solid-width and 27,512 minimum-gap violations. The policy is
unchanged: 10 mm solid width, 12 mm void width, 8 mm gap, and 4 mm erosion.

Exempting the initial state from those rules is rejected because it hides the
failure. A root-only or empty starting state is rejected for the front-wing
benchmark because it discards the STL-derived starting geometry. Leaving the
project at the rejected state preserves evidence but cannot initialize the
generic constrained optimizer.

## Publication and acceptance conditions

A derived bundle is publishable only after a new full topology report succeeds
under the unchanged policy. It must include

- `initialization_kind: constraint_aware_feasibility_projection`;
- parent direct-STL raw/projected hashes and parent rejected-report hash;
- source/derived raw, filtered, and projected hashes; repair configuration and
  per-iteration state/report hashes and stop reason;
- active-domain added/removed/changed masks and voxel/volume counts;
- raw/projected L1 difference, threshold-solid symmetric difference and
  Jaccard, source/derived volume, and derived-surface distance metrics; and
- fixed/root/forbidden mask hashes plus hard-mask invariants.

The derived state must be deterministic, float64, x-fastest, and zero outside
the active domain. It must have no prohibited material and pass connectivity,
erosion, minimum solid/void width, and gap checks. A failed attempt publishes
only failure diagnostics, never a partial feasible state. A changed projected
state requires a new alpha reference and binding before FD preparation; the
direct-STL alpha reference may not be reused.
