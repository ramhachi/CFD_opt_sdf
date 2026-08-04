# G4 B2.0 laminar benchmark scope

Date: 2026-08-04

## Decision

Implement B2.0 as a gated laminar 2D/2.5D pack: first an analytic parallel
plate channel, then a fixed-cylinder porous/body-fitted cross-fidelity case.
NACA remains B2.1. This keeps the generic benchmark moving without changing
the front-wing feasible-initializer blocker or conflating it with native
raw-alpha work.

All cases use pinned OpenFOAM v2512, incompressible steady Newtonian laminar
flow, one z cell, and `empty` front/back boundaries. Three grids represent
the same geometry and physics at `h`, `h/2`, and `h/4`; they must not silently
change Reynolds number, boundary conditions, or porous coefficients.

## Channel gate

Use plane Poiseuille flow at `Re = 2 H U_bulk / nu = 20`, no-slip walls,
analytic parabolic inlet, and a fixed outlet pressure reference. Bind the
analytic solution `u(y)=1.5 U_bulk (1-(y/H)^2)` and
`-dp/dx=3 mu U_bulk/H^2` to profile L2, bulk-flow, and developed pressure-
gradient evidence.

The finest grid must satisfy velocity L2 <= 2%, bulk-flow <= 0.5%, and
pressure-gradient <= 2%. Each principal metric must have same-signed three-
grid differences and observable order
`p=ln(abs((phi_3-phi_2)/(phi_2-phi_1)))/ln(2) >= 1.5`.

## Cylinder gate

After the channel gate passes, compare a fixed cylinder at `Re_D=20` between
body-fitted and Cartesian porous representations, each on three grids.
Default physical values are `rho=1.225 kg/m3`, `nu=1.5e-5 m2/s`, `D=0.01 m`,
and `Uinf=0.03 m/s`; the external domain spans at least
`x=[-15D,+25D]`, `y=[-15D,+15D]`.

Record body-fitted pressure, viscous, and total forces separately. Compare
only total porous resistance force against body-fitted total drag, with
`Cd=Fx/(0.5 rho Uinf^2 D Lz)`, plus fixed external `Cp` probes at radius
`0.75D`. Never label porous volume resistance as separate pressure or skin-
friction force.

The body-fitted finest grid requires GCI <= 2% when asymptotic convergence is
available. Porous total drag must be within 10% of the body-fitted Richardson
value; without a computable body-fitted GCI it is Capability evidence only.
Every `Cp` probe must meet
`abs(delta Cp) <= 0.05 + 0.10*max(abs(Cp_reference),0.1)`.

## Evidence and limits

Every run binds benchmark YAML/STL/grid/physics/dictionary hashes, image
digest, command, final time, residual/mass/stationarity/fatal-log evidence,
force and probe histories, and the complete grid-series formula inputs. A
failed or inconclusive run may be recorded but does not count as B2 evidence.

B2.0 qualifies neither arbitrary 3D/turbulent external flow, NACA, porous
force decomposition, native-v2 sensitivity, nor an optimizer iteration.

## Runtime incident: initial v2512 channel attempt

The first executed Docker attempt is preserved at
`examples/g4_b2_laminar/runs/channel_runtime_v1/g4_b2_channel_runtime_attempt.json`.
For its coarse, medium, and fine cases, OpenFOAM v2512 completed `blockMesh`,
then `simpleFoam` stopped at `Time = 1` with a FOAM FATAL IO error because
`div((nuEff*dev2(T(grad(U))))` was absent from `system/fvSchemes/divSchemes`.
The per-case solver logs are retained beneath the same artifact directory at
`cases/<grid>/log.simpleFoam`.

This v1 artifact is an execution-failure record, not channel qualification:
it contains no usable profile, bulk-flow, pressure-gradient, or grid-series
acceptance evidence. The v2 rerun is required after the already-reviewed
minimal v2512 dictionary completion and the published-provenance locator
correction; neither change revises the B2.0 physics, thresholds, scope, or
gate order defined above.
