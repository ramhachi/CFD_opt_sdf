# Decision Record: Localized Canonical Design Grid for Physical Topology Policy

Date: 2026-07-14 (evidence updated 2026-07-30)
Status: selected architecture; geometry snapshot and alpha-reference contract implemented; runtime qualification required
Scope: front-wing G2 fixture and the generic arbitrary-topology product path

This record supports the authoritative roadmap in
[`phase_plan.md`](phase_plan.md).  It chooses the next design-state
architecture; it does not claim localized OpenFOAM transfer or native-v2
runtime qualification.

## Decision

Keep the declared physical topology policy unchanged and make a localized,
uniform 2 mm canonical **design grid** over the `allowed_front_box` design
domain the future authority for topology state.  The design box is
`1.15 m x 1.45 m x 0.42 m`; at 2 mm this is
`575 x 725 x 210 = 87,543,750` cells.

The existing 20 mm OpenFOAM `blockMesh` remains the outer CFD transfer grid.
It is not the authoritative topology state and must not be used to evaluate
manufacturing or connectivity-policy values.  The new path must define and
validate explicit, provenance-bound transfer of CFD sensitivities to the
localized canonical design grid.  It must not reconstruct a fine topology
state by inverse interpolation of coarse OpenFOAM `alpha`.

The canonical topology state will contain the design-grid, mask, and problem
hashes; `rho`, filtered `rho`, and projected `rho`; filter/projection
configuration hashes; and the transfer/operator and solver-alpha hashes.  The
writer may report topology-policy values only from the canonical projected
state after applying its declared masks.

## Evidence and rationale

The G2 role/domain fixture has a 20 mm canonical transfer grid.  Its declared
physical policy is:

| Quantity | Declared value | 20 mm representation | 2 mm representation |
| --- | ---: | ---: | ---: |
| Minimum solid width | 10 mm | 0.5 cells | 5 cells |
| Minimum void width | 12 mm | 0.6 cells | 6 cells |
| Minimum gap | 8 mm | 0.4 cells | 4 cells |
| Erosion radius | 4 mm | 0.2 cells | 2 cells |

The required G3 preflight criterion is at least three cells for a minimum
feature and at least two cells for erosion/dilation.  The 20 mm grid therefore
cannot truthfully evaluate any of these physical requirements.  A 2 mm grid
meets those declared representation bounds without changing the engineering
intent of the policy.

The alternative of lowering the policy until it fits 20 mm was rejected.  For
example, a 60 mm feature and 40 mm erosion threshold would be representable,
but would replace the stated 10 mm solid-width, 12 mm void-width, 8 mm gap,
and 4 mm erosion requirements.
That would make G2 easier to run while weakening the arbitrary-topology
product requirement, so it is not an acceptable qualification shortcut.

Refining the entire current `3.0 m x 2.4 m x 1.3 m` transfer domain to 2 mm
would require 1,170,000,000 cells and is also not the selected near-term path.
Localizing the canonical state to the allowed design box preserves the
physical policy while keeping the design-state scope bounded.

### Verified G2 localized geometry evidence

The first full-resolution G2 geometry-mask snapshot was generated in the
ignored run directory
`examples/g2_openfoam_compile/runs/local_design_geometry_snapshot_v3_20260730/`
and independently revalidated. Its snapshot identifier is
`381423ea5d095017756beff729bdc1dea2da38afe730b1d9c11e539cfaf37f64`; it binds
ProblemSpec SHA-256
`0fb37503b272080a3b773649023370b8283087a410cc297b64bdbc233500fb43` and local
grid SHA-256 `3c612b5e77804f2a36bb07e4cbb73ed453f84ee5c5d655d83e5a0cd3afceba01`.
For the `575 x 725 x 210 = 87,543,750` cell grid, the verified counts are:

| Mask | True cells |
| --- | ---: |
| active design | 85,967,750 |
| fixed solid | 1,576,000 |
| root | 729,000 |
| forbidden | 0 |

The zero forbidden count is not a clearance omission. The two
`tire_clearance` volumes start at `y = +/-0.740 m`; the `allowed_front_box`
ends at `y = +/-0.725 m`, so they are separated by about 15 mm. The global
20 mm G2 forbidden region therefore lies outside this local design domain.
This is verified geometry/contract evidence, not a claim that tire clearance
has been weakened or that a topology result exists.

The hash-bound localized-state and alpha-reference contracts are implemented
and focused-tested. The allowed alpha source is exactly
`alpha = alpha_reference + E @ (rho_projected - rho_projected_reference)`,
with no clipping or inverse reconstruction. The strict field codec and
fresh-case stager have unit-tested OpenFOAM write/read and `Allrun` placement:
they reject any disagreement in alpha value, current-state, reference-binding,
canonical `x-fastest` order, or parsed `blockMeshDict` grid hashes. No full
localized reference state has been written to an actual compiled case, no
localized finite-difference direction check has run, and there is no native-v2
readiness qualification.

The Sol-reviewed initializer uses `front_wing_initial.stl` as the sole source
of the localized raw density: the union of its ten watertight components is
sampled at the fixed `2 x 2 x 2` subcell offsets `{0.25, 0.75}^3`, only for
active cells. A source/grid/mask-hash-bound memmap writer and its small-grid
tests are implemented; it deliberately does not yet apply filter/projection
or publish the full 87,543,750-cell projected reference state.

The declared transform for that raw density is an active-mask-normalized
Euclidean cone filter with 4 mm radius, then a tanh Heaviside projection with
`beta=2` and `eta=0.5`. Non-active cells are neither filter sources nor
normalizers and stay exactly zero; fixed/root material is added only while
evaluating topology. Canonical filter/projection JSON is bound by the
schema-v2 state manifest. This implemented small-grid contract is not evidence
that the full projected state or its physical topology checks have passed.

## Required implementation and validation

Before native-v2 topology values can become ready, implementation and
qualification must:

1. create and validate a localized projected state against the hash-bound
   geometry snapshot and state contract for the allowed design domain;
2. implement the fail-closed G3 representability gate using the stated
   three-cell feature and two-cell erosion criteria;
3. implement and qualify the explicit CFD-density/sensitivity transfer,
   including
   operator direction, source/target grid and mask hashes, coverage, and the
   `rho`/solver-`alpha` binding;
4. verify the transfer with deterministic identity/conservation and
   finite-difference direction checks appropriate to the bound grids; and
5. evaluate topology-policy values from the 2 mm projected state, then bind
   those values and their provenance into the native-v2 writer/readiness gate.

The existing 20 mm G2 finite-difference evidence proves its current
transferred force-sensitivity chain only.  It neither creates the localized
state nor qualifies a fine-grid topology-policy result.  Later G4 and Stage V
work must still perform porous-to-body-fitted and body-fitted grid-convergence
verification; this decision does not replace those target-physics gates.

## Invariants

This is an architecture decision only.  It does **not** change:

- any declared topology-policy length;
- accepted finite-difference tolerances or observed finite-difference results;
- primal, adjoint, mass-balance, or stationarity convergence evidence; or
- the status of the native-v2 writer, which remains fail-closed and not ready
  until the design state and transfer above are complete.

Historical G2 artifacts, including the 20 mm mask and its successful
two-flow numerical evidence, remain preserved as evidence for the solver
transfer grid.  They must be labelled as such rather than relabelled as
physical-resolution evidence.
