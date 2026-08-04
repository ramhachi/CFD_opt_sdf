# G4 B2.0 cylinder cross-fidelity design

Date: 2026-08-04

## Decision

Adopt **A: a deterministic, project-owned two-representation benchmark** for
the B2.0 cylinder gate.  After the channel-only gate has passed, the same
laminar `Re_D = 20` circular-cylinder problem will be run on three grids in
each of the following representations:

1. a body-fitted `blockMesh` O-grid solved by unmodified `simpleFoam`; and
2. a Cartesian, area-fraction porous cylinder solved by a project-owned
   `simpleFoam` linear-Brinkman extension.

The extension is a pinned source/build artifact owned by this repository; it
is not `topOSource`, a relabelled topology sensitivity source, or an OpenFOAM
run-time option substituted after the fact.  Its compiled-library hash,
source revision, build command, force-field definition, and case dictionary
hash must be part of every run manifest.

This is the next B2.0 implementation only.  It is governed by the fixed
laminar scope in
[`2026-08-04-g4-b2-laminar-scope.md`](2026-08-04-g4-b2-laminar-scope.md).
The prerequisite channel-only gate has passed through the source-bound v4
attestation in
[`2026-08-04-g4-b2-channel-evidence-extraction.md`](2026-08-04-g4-b2-channel-evidence-extraction.md).
That attestation does not qualify the cylinder comparison itself.

## Alternatives considered

- **A — deterministic `blockMesh` O-grid versus Cartesian linear-Brinkman
  pack:** selected.  It has controlled geometry, grids, force definitions,
  and repeatable source provenance, so it can establish the intended narrow
  cross-fidelity evidence.
- **B — `snappyHexMesh` body-fitted cylinder:** not selected for B2.0.  Its
  castellated/snap/layer settings add mesh-generation variability before the
  benchmark establishes the body-fitted-versus-porous force convention.
  It remains a possible later mesh-technology study, not an equivalent B2.0
  result.
- **C — analytical drag correlation or a surrogate as the body-fitted
  reference:** rejected.  A correlation/surrogate cannot prove agreement
  between the declared OpenFOAM representations, nor provide the required
  pressure/viscous split and grid-series evidence.

## Fixed physical problem and boundary conditions

Both representations use OpenFOAM v2512, steady incompressible Newtonian
laminar flow, `rho = 1.225 kg/m3`, `nu = 1.5e-5 m2/s`, `D = 0.01 m`, and
`Uinf = 0.03 m/s`.  Thus `Re_D = Uinf D / nu = 20`.  The 2D/2.5D span has
one cell, `Lz = D`, with `empty` front/back patches; reported forces are
therefore explicitly normalized by that declared span.

The rectangular external domain is fixed at
`x = [-15D, +25D]`, `y = [-15D, +15D]`.  The inlet is fixed uniform
`U = (Uinf, 0, 0)` with zero-gradient kinematic pressure.  The outlet fixes
kinematic pressure to zero and uses zero-gradient velocity.  Top and bottom
are symmetry boundaries, and the physical cylinder wall in the body-fitted
case is stationary no-slip.  The solver, linear solver settings, convergence
criteria, and final-time/stationarity gate must be identical across grids
unless a dictionary difference is explicitly declared as representation-only
and hash-bound in the manifest.

## Geometry and discretization contract

### Body-fitted representation

The body-fitted mesh is a deterministic `blockMesh` O-grid: circular `arc`
edges define the cylinder at radius `D/2`; a fixed sector/block ordering maps
the annulus to the surrounding rectangular far field; and the cylinder wall
is a named no-slip patch.  The manifest must record vertices, arc controls,
block order, cell order, grading, and all generated mesh hashes.  No
unrecorded snapping, layer addition, or automatic remeshing is allowed.

The nominal grid spacings are `h_c = D/8`, `h_m = D/16`, and `h_f = D/32`.
The O-grid radial and azimuthal cell counts must refine exactly by two between
each adjacent grid and preserve the same circle, domain, patch topology, and
grading ratio.  The actual minimum/maximum spacings and cell counts are
reported rather than inferred from the nominal values.

### Cartesian porous representation

The porous case uses a uniform Cartesian `blockMesh` over the same domain,
with the same three nominal spacings `D/8`, `D/16`, and `D/32`, one z cell,
and the same outer boundary conditions.  Every Cartesian cell receives the
deterministic circular solid area fraction of the disk of radius `D/2`; the
area-fraction algorithm, its subcell/quadrature rule if used, and the exact
field hash must be recorded.  A centre-cell binary mask is not an acceptable
substitute.

The benchmark constants are fixed at `betaMax = 1.5e5` and `Da = 1e-6` in
the extension/case contract.  Their dimensions, the exact area-fraction to
coefficient mapping, and the linear source equation used by the compiled
extension must be emitted in the manifest and checked against the pinned
source.  They may not be tuned per grid, representation, iteration, or
observed drag.  An absent, dimensionally inconsistent, or hash-unbound force
definition is inconclusive.

## Force and pressure conventions

For the body-fitted case, record the signed streamwise pressure force, viscous
force, and their total separately from the cylinder wall.  Use the fixed
sign convention `Fx > 0` for drag and

`Cd = Fx / (0.5 rho Uinf^2 D Lz)`.

For the porous case, integrate and report only the total signed streamwise
linear-Brinkman resistance over the declared cylinder area/volume.  It must
not be called pressure drag, skin-friction drag, or decomposed into either.
The porous total is compared only to body-fitted total drag.

Sample kinematic pressure at eight fixed external locations
`r = 0.75D`, `theta = 0, 45, 90, 135, 180, 225, 270, 315 degrees`, measured
from positive x about the cylinder centre.  Convert to
`Cp = (p - p_infinity) / (0.5 Uinf^2)` using kinematic pressure and the
declared reference pressure.  Each probe position, interpolation rule,
value, and source-field hash is retained.

## Three-grid analysis and acceptance

For any body-fitted scalar used as the reference (total `Cd` and each `Cp`
probe), use the fixed refinement ratio two and report the raw coarse/medium/
fine values.  Where consecutive differences have one sign and an observable
order can be formed, compute

`p = ln(abs((phi_f - phi_m)/(phi_m - phi_c))) / ln(2)`,

the Richardson value

`phi_R = phi_f + (phi_f - phi_m)/(2^p - 1)`,

and the fine-grid GCI

`GCI_f = 1.25 * abs(phi_f - phi_m) / (abs(phi_f) * (2^p - 1))`.

The implementation must also record the standard asymptotic-consistency
check from the coarse/medium and medium/fine GCIs.  A body-fitted reference is
usable for Target-physics evidence only when this analysis is computable,
asymptotic, and the finest-grid GCI is at most 2%.  The calculations retain
unrounded values; neither a hand-selected order nor a clipped denominator is
permitted.

The porous fine-grid total drag passes cross-fidelity only when it is within
10% of the body-fitted Richardson total-drag value.  Every porous fine-grid
probe must pass

`abs(Cp_porous - Cp_reference) <= 0.05 + 0.10 * max(abs(Cp_reference), 0.1)`.

Here `Cp_reference` is the corresponding qualified body-fitted Richardson
value.  A passing force value cannot compensate for a failing probe, nor can
passing probes compensate for a failing force value.

## Fail-closed evidence rules

Each case records the benchmark YAML/STL or analytic-geometry hash, grid and
dictionary hashes, image digest, extension source/build hash where relevant,
command, final time, solver/fatal logs, residual histories, mass balance,
stationarity, force histories, and the complete inputs to every grid-series
formula.  The body-fitted and porous cases must each meet the B2.0 runtime
health gate before their values are compared.

The result is **inconclusive**, rather than a pass, if any required source,
mesh, field, force, probe, command, hash, or convergence datum is missing; if
the geometry/physics/coefficient contract differs across the grid series; if
the body-fitted order/GCI/asymptotic test cannot be computed; or if the
extension cannot prove its exact source term.  A numerical threshold violation
is a recorded **failure**, not grounds to change `betaMax`, `Da`, a mesh, or a
tolerance.  Without a computable qualifying body-fitted GCI, a completed run
may be Capability evidence only and must not be labelled a B2.0 cylinder
Target-physics pass.

## Scope limits

This decision qualifies neither `snappyHexMesh`, NACA/B2.1, arbitrary 3D or
turbulent external flow, adjoints/sensitivities, porous pressure/skin-friction
decomposition, topology optimization, nor the front-wing native-v2 path.  It
does not alter the independent localized front-wing feasible-initializer
blocker.
