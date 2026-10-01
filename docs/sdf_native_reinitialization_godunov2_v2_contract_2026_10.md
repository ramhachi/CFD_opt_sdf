# SDF-native reinitialization contract: sub-cell Godunov v2

Status: proposed for a new immutable SDF-02 qualification round. The criteria
JSON records the source commit, source hashes, fixture specifications, canonical
input SHA, and the unchanged conservative gate values before any qualification
run. This is a new method-specific identity; it does not edit the historical
SDF reinitialization contract or evidence from `feat/issue-28-sdf-reinit`.

The implementation's static payload SHA-256 is
`01c1337601da841ab97c34c78676e17f826bc710e8faed90243c27794fba0f25`.

## Operator boundary

Reinitialization is an explicit post-acceptance operator. It is not applied in
the registered finite-difference forward map `phi -> response` and is not
differentiated. A pass can qualify only the recorded geometric/operator effects;
it does not qualify a solver response, gradient, accepted optimizer step, or
descent.

## Method and fixed domain

For each grid edge with one strictly negative endpoint and one non-negative
endpoint, seed the zero crossing at the linear interpolation fraction
`t = |phi_solid| / (|phi_solid| + |phi_non_solid|)`. If the denominator is below
`1e-7 m`, use `t=0.5` and record the degenerate edge. Each interface-adjacent
node is seeded from the minimum crossing distance on each grid axis combined as
`d = 1/sqrt(sum_axis(1/dmin_axis^2))`. Nodes with input `phi == 0` remain exact
zero seeds. All other distances use deterministic, per-sign-side second-order
Godunov Eikonal Jacobi relaxation in float64, with the stable second upwind
stencil used only when its second neighbor is no larger than its first.

The stop test is an exact floating-point fixed point. The iteration limit is
`4 * sum(shape)`; reaching the limit is `UNRESOLVED`, never a pass. This
algorithmic convergence rule is separate from the geometric acceptance gates.
Output is float32. The output replaces only nodes with `abs(phi_in) <= 3h`; all
far-band input values are retained bit-for-bit. Solid remains `phi < 0`, zero
remains an interface/non-solid node, and signs never change. The four masks are
copied byte-identically; state generation increments once and the reinitialization
policy id records this method.

Uniform all-solid, all-fluid, or no-interface input is rejected before
relaxation. No fallback to a binary EDT, alternate solver, or changed threshold
is allowed in this round.

## Registered measurements and gates

For analytic fixtures, measure on output nodes satisfying `abs(phi_out) <= 3h`,
excluding one-node grid boundaries, using central differences. Record fluid and
solid `abs(|grad(phi)|-1)` percentiles 50/95 and maximum. For canonical v16,
use the same fixed band and stencil but gate only fluid p50/p95; report solid
statistics without a gate because the voxel staircase has legitimate medial
axis ridges. Do not narrow the band or remove points after seeing results.

Also record and gate:

- maximum change in the linear zero-crossing fraction on edges present in both
  fields (edge length is one), and the count of unmatched crossing edges;
- relative drift in the registered trilinear cell-center sharp volume and the
  `sdf_native_smoothed_volume_v1` value;
- strict node sign changes, exact-zero node preservation, all four masks,
  node-level and trilinear-cell-center topology events, and component counts;
- exact far-band preservation and second-application idempotence measured as
  `max(abs(R(R(phi))-R(phi))) / h` on the fixed output band.

The unchanged numeric gates are:

| Quantity | Analytic fixtures | Canonical v16 |
| --- | ---: | ---: |
| Eikonal error p50 | ≤ 0.05, both sides | ≤ 0.10, fluid |
| Eikonal error p95 | ≤ 0.25, both sides | ≤ 0.50, fluid |
| Eikonal error maximum | ≤ 0.50, both sides | reported, ungated |
| Zero-level edge fraction displacement maximum | ≤ 0.25 | ≤ 0.25 |
| Unmatched crossing edges | 0 | 0 |
| Sharp and smoothed volume relative drift | ≤ 0.05 each | ≤ 0.05 each |
| Sign changes / exact zeros / masks | 0 / preserved / identical | 0 / preserved / identical |
| Node and cell-center topology events | 0; component counts unchanged | 0; component counts unchanged |
| Far-band changes | 0 | 0 |
| Idempotence on fixed band | ≤ 0.10h | ≤ 0.10h |

Every gate is reported for every case. Any failed gate is `FAIL`; iteration
non-convergence or inability to resolve the registered input is `UNRESOLVED`.
No result is called PASS unless every applicable gate passes for every case.

## Evidence boundary

Analytic and canonical-v16 results describe the operator and its bounded effect
on those fields only. They do not resolve the FD-02/FD-06 response issue, do not
justify using reinitialization in an FD forward path, do not qualify a shape
update or topology transition, and do not imply optimizer descent or physical
aerodynamics.
