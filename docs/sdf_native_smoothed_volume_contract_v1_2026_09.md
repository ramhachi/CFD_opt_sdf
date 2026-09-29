# SDF-Native Smoothed Volume Contract v1

Status: implementation contract for P22-01; numerical software checks do not
qualify a shape update.

## Identity and reference

- Contract ID: `sdf_native_smoothed_volume_v1`
- Schema version: `1`
- Static contract SHA-256: `56825cd50c0916c5659badd21c84bab517ddb370085a92056d40a9028e8a7969`
- Sharp reference limit: `V_phi_0 = 0.12612500000000004 m^3`
- Reference lineage: v16 genesis, 1009 sampled solid centers
- Source registration: `sdf_native_volume_semantics_v1_2026_09`
- Source SHA-256: `0142ace4de9419dd73cc27e90135ed1fe1f847b074ca2faa37fdb0962505bbce`
- Stage T `Vmax = 0.0763256681 m^3` is not carried into this contract.

The registered sharp volume remains

```text
V_phi = count(center_phi < 0) * h^3
```

where `center_phi` is the existing float32 arithmetic mean of the eight
canonical SDF nodes at each h-cube center. Exact-zero center samples are fluid.
The differentiable value and sharp value are reported separately.

## Frozen smooth rule

For each h-cube, let `s = -center_phi`, in metres. The transition width is
exactly one state spacing, `epsilon = h`, and is not a tunable v1 argument.

```text
H_epsilon(s) = 0                               when s <= 0
               (1 - cos(pi*s/epsilon)) / 2     when 0 < s < epsilon
               1                               when s >= epsilon

V_epsilon = h^3 * sum_over_all_h_cubes H_epsilon(-center_phi)
g_V = V_epsilon / V_phi_0 - 1
```

This one-sided C1 cosine transition makes exact-zero centers fluid and has the
pointwise sharp limit `1[center_phi < 0]` as `epsilon -> 0` at fixed grid.
It intentionally differs from a centered Heaviside regularization. Volume is
sampled at every cell center, including cells adjacent to fixed, forbidden,
root, and non-design nodes; masks do not remove or alter samples.

The derivative at a node is the sum over its adjacent h-cubes:

```text
dV_epsilon/dphi_node = -h^3/8 * sum H'_epsilon(-center_phi)
H'_epsilon(s) = pi/(2*epsilon) * sin(pi*s/epsilon),  0 < s < epsilon
```

The returned `gradient_m2` is zero unless the node is in `design_mask` and
outside `fixed_solid_mask`, `forbidden_mask`, and `root_mask`. Root ownership
is applied independently: a root node has no design derivative even if a
caller supplies a root mask not nested in the fixed-solid mask. The state phi
at all masked nodes remains part of the volume value. Units are
`dV/dphi`: `m^2`; `dg_V/dphi`: `m^-1`.

At finite width this one-sided transition underestimates the sharp count for
centers inside the transition band. Therefore `g_V <= 0` is not a conservative
sharp-volume feasibility certificate and cannot admit an optimizer step or
shape update by itself. Every acceptance decision must independently require
the registered sharp gate `V_phi - V_phi_0 <= 0`. The result reports that
signed sharp residual, its positive violation, and sharp feasibility separately
from `g_V`.

## API and identity

`cfd_sdf.design.smoothed_volume_and_gradient(state)` returns a
`SmoothedVolumeResult` with the smoothed volume, sharp diagnostic, registered
limit, signed residual, masked analytic gradient, transition width, state hash,
grid hash, and contract hash. An explicit `transition_width_m` is accepted
only if it equals the state spacing exactly. The serialized result contains
deterministic little-endian float64 gradient hashes, while keeping the arrays
separate from metadata.

`contract_sha256` hashes the static definition above, including the source
registration identity and independent sharp acceptance rule. `grid_sha256` binds the contract identity, state shape,
origin, spacing, and realized transition width. `state_sha256` binds the SDF
field and its masks/policies. The smooth residual uses only the registered
v16 reference limit; the sharp diagnostic is not substituted into it.

## Evidence boundary

Unit tests may establish this software contract's algebra, mask ownership,
determinism, and finite-difference agreement on fixtures. They do not establish
the missing ignored v16 state artifact, WaterLily reverse-mode qualification,
optimizer integration, hard-gate enforcement, target-physics validity, or
permission to perform a shape update. P22 closes only after a constrained SDF
step and its required gates are independently authorized and observed.
