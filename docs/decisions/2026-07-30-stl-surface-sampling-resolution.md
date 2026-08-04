# STL surface sampling resolution for localized raw density

Date: 2026-07-30

## Decision

Keep the 2 mm local grid, its fixed subcell offsets `(0.25, 0.75)^3`, and the
front-wing STL unchanged.  For ordinary subcell points, use binary union
containment exactly as before.  For a point within `1e-9 m` of a source
surface, use only the following fail-closed resolution:

1. identify one unique globally nearest, nondegenerate triangle;
2. require its closest projection to be strictly inside that triangle, not on
   an edge or vertex;
3. offset the point by `+/- 1e-6 m` along its normalized face normal;
4. require both displaced points to be farther than `1e-9 m` from every
   component surface; and
5. use the arithmetic mean of the two binary union-containment values.

Any failed uniqueness, degeneracy, projection, clearance, or containment
check rejects the raw build.  The generated raw manifest is schema v2 and
records the immutable `symmetric_normal_offset_union` contract, sampler
implementation/version, and the counts of zero, half, and one contributions.
Schema v1 remains readable by bundle verification for already-published
artifacts; new raw artifacts are schema v2.

## Rationale

The q=`.25` local sample plane at `z=.3125 m` coincides with an unchanged
front-wing STL face.  Treating the result as arbitrary inside/outside changes
the physical initial state according to ray direction or library details.
Moving the grid or source geometry would change the declared G3 geometry
contract.  Symmetric displaced union occupancy gives a deterministic half
contribution for a locally separating, face-interior surface while refusing
topological and meshing ambiguities.

Globally flipped but consistently wound faces are accepted: plus/minus union
occupancy is symmetric, so face-normal orientation only swaps the two terms.

## Considered options

1. Change q offsets, local-grid origin, or the STL to avoid the face.
   Rejected: each changes the Sol-approved discretization or sole geometry
   source.
2. Assign an exact surface point to a fixed side, or add an arbitrary floating
   perturbation. Rejected: the result can depend on winding, ray direction, or
   platform details and has no provenance-bearing physical interpretation.
3. Resolve only a unique, face-interior tie by symmetric normal-offset union
   sampling and reject all other ties. Selected.

## Evidence and limits

The prior retry produced
`examples/g2_openfoam_compile/runs/.localized_reference_state_retry_20260730_e896e9c35812.build-failure.json`:
`failed_stage=build_raw_initial_design_rho` and
`initial_design STL occupancy is ambiguous: a sample lies on the STL surface`.
Its sibling private staging tree contains the fully copied geometry snapshot
and a partial raw NPY, establishing that this was not the earlier interrupted
geometry-copy attempt.

`tests/test_local_initial_design_rho.py` now checks face-interior half
contribution, winding invariance, offset-scale stability, rejection of edges,
vertices, multiple nearest faces, and uncleared offsets.  It also performs a
one-cell diagnostic at the real front-wing `z=.3125 m` plane and records
resolved tie statistics without launching a new 87.5M-cell build.  The
focused probe observed `tie_point_count=4`, contribution counts
`{zero: 0, half: 4, one: 0}`, and `rho_raw=0.25` for that cell.  This is a
sampler-contract verification, not a completed G3 runtime qualification; a
future full bundle must still be built and independently verified.
