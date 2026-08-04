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

## First implementation evidence: rejected

The first full-resolution attempt used the bounded raw-only opening/gap-fill
initializer with at most three iterations. It produced no derived bundle. Its
diagnostic is
`examples/g2_openfoam_compile/runs/.localized_feasible_derived_state_v1_20260730.feasibility-failure.json`.
The direct source bundle and rejected report remain unchanged. Iteration zero
and the first repaired state both retained `minimum_solid_width` and
`minimum_gap`; the raw repair then reached a fixed point. This is a failed
initializer attempt, not evidence that the constraints passed or that the
front-wing benchmark is ready for FD.

## Next operator: support-buffer repair

The bounded Sol review selected a filter/projection-aware conservative repair,
not a new constrained initialization solver or a relaxation of the policy.
The repair reads the final projected topology check and modifies raw density
only. For every thin-solid violation target it writes zero to every active raw
cell with positive cone-filter support; for every external-gap violation target
it writes one to the corresponding active support. With the existing
active-source normalized cone filter, a support forced entirely to zero or one
forces the target filtered value, and the unchanged Heaviside maps those
endpoints to zero or one. This is a forward guarantee, not inverse projection.

Removal runs before gap filling. Each phase reruns raw -> filter -> projection
and the full checker. Add/remove conflicts, repeated state hashes, cycles,
resource failures, and iteration limits are rejected. The operator does not
declare feasibility; only the final unchanged checker may do so.

Failure diagnostics must retain the complete checker payload and violation
counts/first indices, source and transition deltas, target and zero/one-buffer
hashes/counts, conflict data, and the support radius/offsets/weights/hash.
The derived state must retain nonzero overlap with the source threshold solid;
metrics describe STL divergence but introduce no unapproved maximum threshold.

## First support-buffer evidence: rejected conflict

The first full-resolution support-buffer attempt produced no derived bundle.
Its fail-closed diagnostic is
`examples/g2_openfoam_compile/runs/.localized_feasible_support_buffer_v2_20260730.feasibility-failure.json`.
The thin-solid removal phase left 3,536 minimum-solid-width and 26,182
minimum-gap violations. The subsequent fill buffer overlapped the already
required zero buffer at 7,130 active raw cells, so the operation stopped with
`add_remove_support_conflict_rejected`. No priority was silently chosen:
forcing the same raw cell to both endpoints would invalidate the forward
support guarantee. This is evidence that the local support-buffer operator is
insufficient for this benchmark state, not evidence of a feasible start.

## Front-wing benchmark blocker

The Sol review selects a stop for the front-wing localized FD/optimizer line
under the current immutable policy. The support conflict makes a deterministic
local repair insufficient, and choosing removal or fill priority would silently
break one of the required topology conditions. A new global feasible-init
optimization or a new geometry-repair policy would introduce objectives and
acceptance criteria beyond this roadmap decision and must be separately
approved before implementation.

This blocks front-wing G2 native-v2, FD, and optimizer qualification only. It
does not block generic topology infrastructure or a separately qualified
simple-geometry benchmark. Restarting the front-wing line requires an approved
initializer that produces a full-checker-success derived state with its
divergence/provenance evidence and a fresh alpha binding.
