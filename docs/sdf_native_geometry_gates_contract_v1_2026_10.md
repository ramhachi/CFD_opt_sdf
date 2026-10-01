# SDF-native geometry gate contract v1 (GEOM-01)

This contract measures a fixed `SDFDesignState` without running a flow solver
or changing the state. The gate bundle is fail-closed: every required gate must
be `pass`; either `fail` or `unmeasured` blocks the aggregate verdict.

## Inputs and scope

The canonical diagnostic input is the exact v16 state archive named by
`docs/evidence/sdf_native_genesis_v16_2026_09.json`. Its archive hash must be
checked before loading. The v16 state has no populated fixed, forbidden, or
root masks and no bound source `ProblemSpec`; those omissions are visible in
the result. The canonical evaluation uses the inherited sharp-volume bound
from `volume_semantics.py`; it does not infer feature sizes from grid spacing.

Analytic fixtures may use explicit test-only `SDFTopologyPolicy` width and gap
limits. Such fixture results validate implementation behavior only and do not
register canonical limits. The canonical call uses
`policy_scope="canonical_unresolved"`. Its mask/root binding, disconnected
component admissibility, and event permissions remain `unmeasured` until the
source masks and unresolved #31 policy choices are bound. This contract does
not modify immutable `SDFTopologyPolicy` v1 or register a successor policy.
The 26-neighbour component count is a measurement convention, not a selected
permission for topology changes.

## Gates

All metrics are in metres or SI volume units. `phi < 0` is solid. Topology and
mask checks use node occupancy; volume, widths, gaps, clearance, and surface
checks use the established cell-centre `V_phi` occupancy. The implementation
reuses the existing #31 transition evaluator, volume semantics, and P20
self-intersection detector.

| Gate | Measurement and decision |
| --- | --- |
| `sdf_finite_structure` | 3-D float32, finite values, negative-inside convention, state digest, and both solid/fluid signs. |
| `sdf_distance_property` | Median absolute `|\|grad phi\|-1|` in the interior state narrow band; threshold must be explicitly supplied. |
| `near_zero_gradient_band` | Gradient norm distribution in interior nodes with `|phi| <= 0.05 m`; the band follows the #36 diagnostic request. The prior `<1e-6` and `>=0.25` bins are descriptive only. A low-gradient acceptance floor is not registered for canonical geometry, so this gate is `unmeasured` there. |
| `sdf_boundary_margin` | Solid cell clearance from the SDF array boundary of at least one structural grid cell. This is not a physical domain-clearance claim. |
| `mask_preservation` | Existing transition evaluator checks bound masks/root groups. Canonical source-mask linkage is absent and remains `unmeasured`. |
| `component_connectivity` | Existing transition evaluator plus reported 26-neighbour component count. Canonical root/disconnected-component permissions are unresolved. |
| `topology_change_classification` | Existing transition evaluator's measured events. Canonical birth/split/merge/deletion permissions remain unresolved. |
| `min_feature_width` | Sampled `2*EDT` ridge-width estimate on 4x supersampled cell occupancy. The operational uncertainty guard is one supersample (`h/4`); a measurement within that distance of a bound is `unmeasured`. This is not guaranteed continuous-geometry minimum width. Limits come only from the bound policy; no `h`-derived physical limit is allowed. |
| `inter_component_gap` | Exact face distance for the sampled cell union between separate 26-neighbour cell components, which estimates rather than proves the continuous-SDF gap. A one-cell (`h`) resolution guard makes near-bound measurements `unmeasured`. Limit must come from the bound policy. |
| `export_surface_integrity` | A separate voxel-cell-union diagnostic surface is checked for watertightness, winding, manifold/duplicate faces, positive volume, relative volume agreement, and node/cell component count agreement. Canonical qualification stays `unmeasured` until the actual GridSDF zero-level export mesh is supplied and checked. |
| `surface_self_intersection` | Existing P20 triangle self-intersection detector is run on the diagnostic voxel-cell-union surface. Canonical actual-export self-intersection stays `unmeasured` until its mesh is supplied. Detector inability is `unmeasured`. |
| `domain_clearance` | Cell-body AABB clearance from the SDF grid extent or an explicitly supplied physical domain. Physical clearance threshold must be supplied. |
| `volume_semantics` | Existing sharp `V_phi` rule against a registered finite positive volume limit; smoothed volume remains diagnostic only. |

Unavailable inputs or thresholds are `unmeasured`, never defaults. Non-finite
SDF data fails the structural gate and blocks dependent measurements.

## Fixture-only validation

The tests include a sampled analytic hollow box with explicit fixture-only
width, gap, clearance, distance-field, and low-gradient limits; a deliberate
forbidden-mask overlap that must fail for that reason; and two disconnected
canonical components whose count is reported without turning the unresolved
root policy into an inferred failure or pass. Fixture limits have no authority
over v16/v17 or future optimization states.

## Evidence boundary

The canonical artifact is solver-free geometry contract/capability evidence.
The voxel-cell-union mesh checks are labelled proxies and cannot qualify the
actual GridSDF zero-level/STL artifact; that actual mesh needs its own input
hash and provenance. The sampled width and gap values are estimates, not
guaranteed continuous-geometry bounds. This contract cannot establish force,
flow, optimization, manufacturing feasibility, canonical topology policy, or
shape-update eligibility. All qualification flags remain false. A complete
gate report is not a passing qualification when required gates are unresolved.
