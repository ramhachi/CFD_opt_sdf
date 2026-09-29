# SDF topology policy v1

Status: the solver-independent v1 policy semantics are registered. The v16
genesis binding is unresolved, so topology birth remains disabled and
unqualified.

Machine-readable registration:
[`evidence/sdf_topology_policy_v1_2026_09.json`](evidence/sdf_topology_policy_v1_2026_09.json).
Its sidecar freezes the complete registration artifact; `policy_sha256`
freezes the canonical policy object separately.

## Contract

`SDFTopologyPolicy` wraps the existing `ProblemSpec` v2
`topology_policy` object. A resolved policy records both the full canonical
`problem_spec_sha256` and a canonical hash of that existing topology-policy
subobject. Root-group identifiers and source geometry-role references, solid
and void connectivity modes, component bounds, minimum solid and void widths,
minimum gap, and erosion radius remain sourced from `ProblemSpec` v2; this
contract does not introduce another set of physical lengths.

The SDF component checker uses 26-neighbour connectivity (face, edge, or
corner contact) on the canonical occupancy `phi < 0`, matching the existing
Stage S component convention. Disconnected solid components are permitted
only when every component intersects at least one required ProblemSpec root
group. Each component's owner set is the sorted set of required root-group
IDs it intersects. Any source `max_components` bound remains binding. For an
evaluation, the supplied per-group masks must have exactly the required IDs,
their union must equal `SDFDesignState.root_mask`, and the root cells must
remain solid. The per-group masks are external registered evidence. The
checker validates their IDs, shapes, union, and occupancy, but does not load
or re-verify the geometry-mask manifest that produced them; that provenance
must be checked by the caller.

Hard mask rules reuse the SDFDesignState fields: solid material is allowed
only in `design_mask`, `fixed_solid_mask`, or `root_mask`; every fixed-solid
and root cell must remain solid; and no solid may occupy `forbidden_mask`.
Candidate minimum solid and void widths are compared with the exact positive
limits inherited from `ProblemSpec` v2. If the source also declares
`minimum_gap_m`, the evaluator requires a candidate-bound minimum-gap
measurement and rejects a value below that limit. Both width limits and their
candidate-bound measurements are required for an admissibility pass. A
measurement report must name the candidate `state_sha256` and a report
SHA-256. This module consumes those measurements; it does not define a new
feature-size measurement algorithm. A declared gap limit without a registered
evaluator result fails closed.

The event rules are fixed in v1:

- **Birth:** disabled. A new 26-connected solid component that has no
  cell-overlap with a current solid component is rejected.
- **Merge:** allowed only when all root, mask, feature, and source policy
  checks pass.
- **Split:** allowed only when every resulting component has a required root
  owner and all other checks pass.
- **Deletion:** disabled for deletion of a whole connected component.
  Removal of cells from a component is subject to retained fixed/root masks
  and the same feature checks.

Missing source hashes, required root groups, per-group root masks, minimum
width limits, or feature measurements fail closed. The evaluator reads two
existing immutable `SDFDesignState` values and returns detected events,
component ownership, and violations. It does not create a candidate, modify
an SDF, run a flow solver, or propose a topology.

## v16 binding

The registered genesis record reports zero root, fixed-solid, and forbidden
mask cells, and the associated Stage S entry records root connectivity as
`not_applicable`. That observation means no root rule was evaluated for the
v16 state; it is not evidence that a root requirement passes.

The v16 registration therefore has no source ProblemSpec v2 digest or
topology-policy payload bound to its state. The tracked Stage V v16 physical
profile ProblemSpec has empty root groups, disabled solid connectivity, and
null minimum solid and void widths, so it cannot supply the missing Birth-0
policy inputs. The existing SDFDesignState identifier is retained as
historical metadata and has no v1 policy content hash. The evaluator requires
an exact policy-ID-plus-SHA binding for future states.

The unresolved inputs recorded in the registration are:

1. the native ProblemSpec v2 and topology-policy hashes for the SDF lineage;
2. nonempty required root groups with per-group masks on the SDF grid;
3. registered `minimum_solid_width_m` and `minimum_void_width_m` values;
4. if the source declares `minimum_gap_m`, a candidate-bound minimum-gap
   measurement; and
5. a candidate-bound measurement report for both feature widths.

No physical threshold is inferred from the v16 grid spacing, measured feature
width, Stage V profile, or analytic test fixtures. The current evidence class
is contract and capability only; `topology_birth_qualified` and
`shape_update_allowed` remain false.
