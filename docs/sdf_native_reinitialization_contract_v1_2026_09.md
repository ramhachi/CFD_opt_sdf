# SDF-Native Reinitialization Contract v1

Status: pre-registered implementation contract for SDF-02 (issue #28). The
tolerances below were committed before any numerical evidence was produced and
are not call arguments. Passing them is contract and capability evidence only;
it does not qualify a shape update, an optimizer step, or a gradient.

- Contract ID: `sdf_native_reinitialization_v1`
- Schema version: `1`
- Static contract SHA-256: `590820800283dba25b188c2f25b76b589bf0b94f541fdc4625cbc8a60a538db0`
  (canonical sorted compact JSON of `REINIT_CONTRACT_PAYLOAD` in
  `src/cfd_sdf/design/sdf_reinitialization.py`, which holds the authoritative
  constants)

## Position in the composite operator

Formal finite differences differentiate `phi -> response` **without**
reinitialization. Reinitialization is a separate, explicit operator `R` applied
only to an *accepted* update, so the multi-step map is `phi <- R(phi + step)`.
`R` is not differentiated and is not part of any registered gradient.

## Method (deterministic, numpy/scipy only)

Fast sweeping and PDE reinitialization were passed over: fast sweeping needs
ordered Python loops over every node (slow, order-dependent), and PDE
reinitialization is iterative, moves the interface and has no exact
fixed-point test. A vectorized Jacobi Godunov relaxation is bit-deterministic,
has an exact stopping test (no change), and its fixed point satisfies the
discrete Eikonal equation by construction.

1. Sign rule: solid iff `phi_in < 0` (strict; exact zero is non-solid,
   matching the volume contract). Signs are never changed.
2. Interface: for every grid edge joining a solid node `a` and a non-solid node
   `b`, the crossing is `t = |phi_a| / (|phi_a| + |phi_b|)` measured from `a`
   as a fraction of `h`. If `|phi_a| + |phi_b| < 1e-7 m` the crossing is fixed
   at `t = 0.5` (degenerate edge, counted and reported).
3. Frozen nodes: every node incident to a crossing edge gets
   `d = 1 / sqrt(sum_axes 1/dmin_axis^2)` where `dmin_axis = h * min t` over
   that axis's crossing edges (axes without one contribute 0). This is exact
   for a locally planar interface whose intercepts lie within one cell.
4. All other nodes: Jacobi Godunov update, per sign side (a node only sees
   same-sign neighbors), starting from infinity and taking
   `min(old, new)`, until no value changes. Full domain, not truncated.
5. Output `phi = sign * max(d, 1e-9 * h)` in float32 (strictly signed: the 109
   exact-zero non-solid nodes of canonical v16 become `+5e-11 m`).
6. New state: `generation + 1`, `reinitialization_policy_id =
   sdf_native_reinitialization_v1`, masks, origin, spacing, source hash copied.

Masks (`design`, `fixed_solid`, `forbidden`, `root`) are copied unchanged.
Magnitudes at masked nodes may change; signs never do, so every
material-in-mask retain/forbid rule of the topology policy is preserved
exactly.

## Fail-closed gates (all must hold)

Band = nodes with `|phi_out| <= 3 h`, excluding grid-boundary nodes;
`|grad phi|` by central differences.

| Gate | Fixtures (analytic) | Canonical v16 |
|---|---|---|
| Eikonal `| |grad phi| - 1 |` p50 / p95 / max | 0.05 / 0.25 / 0.50, both sides | p50 0.10, p95 0.50, fluid side only, no max gate |
| Zero-level displacement: max change of edge crossing fraction `t` (edge = 1) | 0.25 | 0.25 |
| Unmatched crossings (edges whose sign change appears or disappears) | 0 | 0 |
| Sharp volume relative drift vs input | 0.05 | 0.05 |
| Smoothed volume (`sdf_native_smoothed_volume_v1`) relative drift vs input | 0.05 | 0.05 |
| Masks byte-identical, node sign changes | equal, 0 | equal, 0 |
| Node-solid and cell-center-solid topology events; component counts | none; equal | none; equal |
| Idempotence: `max abs(R(R(x)) - R(x))` on band | `0.10 h` | `0.10 h` |

Canonical v16 is a voxel staircase with legitimate medial-axis ridges, so its
Eikonal gate is percentile-only and fluid-side only; the solid side and the
input field are reported without a gate. The canonical input is registered at
the recorded SHA-256 in the evidence file.

An input with no solid/non-solid edge (all solid or all fluid) is rejected.
Non-finite or non-float32 input is already rejected by `SDFDesignState`.

## Evidence boundary

Operator behavior on analytic fixtures and on the canonical v16 field is
contract and capability evidence. It does not show that reinitialization
improves any solver response, that an optimizer step descends, that the
WaterLily normal issue of #36 is resolved, or that topology-birth events are
safe. Zero-level displacement is measured on grid-edge crossings of the
trilinear node field; sub-cell surface geometry between edges is not measured.
