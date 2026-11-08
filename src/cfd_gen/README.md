`src/cfd_sdf` and `julia/CFDSDFWaterLily/src` are enumerated by historical source freezes.
Place new GEN-01 code in `src/cfd_gen/` and `julia/CFDSDFWaterLily/gen01/`.
Reuse existing `cfd_sdf` modules by import without changing their frozen source.

Phase A is solver-free software. Thickness/gap defaults of 4h are development
defaults pending the registered RES-00 ladder. Movable components alone own
thickness, wing/endplate joint requirements, rules envelopes, ground/domain
clearance, forbidden masks and roots. Fixed STL/endplate widths and sampled
solid-node counts are reported separately in `context_resolution`, with an
unknown STL width left unknown. Finite union topology and movable/fixed pair
gaps still include fixed context; a fixed endplate cannot receive a design
joint's gap exemption. Explicit
`MergedElement` IDs appear in gate `distance_contract_exemptions`: their min
union is not a band signed distance inside overlap, and its BDIM effect needs
measurement before MW-01.

`merge_candidates` only generates proposals. Its default overlap is half the
smaller plate thickness, hence at least t_min/2 for thickness-admissible plates.
Admit a merge only through `evaluate_scene_gates_phases` with the checkpoint's
16 distinct common phases: every phase must pass, and all phase reports and
rejection reasons are retained. A single-phase diagnostic is insufficient.

`element_count_designs` retains explicit `gap` callers. With no gap supplied,
provide h (and the gate policy/dimension) to use g_min plus the gate's one-sided
sampling guard plus each child's camber/reflex allowance (0.02t per deformed
plate). The guard is h/4 in 2D and (1+sqrt(2))h/4 in 3D. Splits keep the parent
axial footprint; this is a warm start, not a general gate/volume guarantee.
Thickness-history knock-out requires per-ID floors or per-checkpoint snapshots
from `thickness_parameter_floors`; the ambiguous scalar fallback is rejected.

Known CPU limits before MW-01 (acceleration is a separate work package):

- Design sampling caps allocation at 2,000,000 nodes. The gate reports
  `sampling: unmeasured`, including requested shape/count and cap, rather than
  propagating the sampler's resource-limit signal. Direct `Scene.sample`
  callers receive `SceneSamplingLimit`; malformed inputs remain errors.
- R3 caps the h/4 refined crop at 8,000,000 nodes (about 50 cubed original
  crop nodes). A 1.4 m span at h=5 mm can require refined shape
  `[281, 1137, 57]`, or 18,211,329 nodes, and is therefore `unmeasured`.
  Passing small 3D fixtures does not make this a usable MW-01 admission gate.
- `MeshBody.phi` winding signs cost O(P*T) for P points and T triangles:
  1,000,000 points with 100,000 triangles imply 100,000,000,000 point/triangle
  pairs. Every phi call also re-reads and SHA256-hashes the complete STL
  (O(file bytes)); boundary sampling loops over triangles in Python. No
  vehicle-mesh runtime or memory qualification is claimed.
- The nearest-boundary refinement used for merge proposals is numerical,
  with eight local starts; it is not a certified global distance solver.
  Review 2 observed about 1--2 seconds per pair and 24--26 seconds for strongly
  cambered plates (|camber|/c=6%). These are review measurements, not a new
  benchmark. A typed non-convergence skips only that pair and records its IDs
  and reason in the caller's diagnostics list (or logs a warning when omitted);
  other pairs continue, while invalid inputs and unrelated errors still raise.

2D and 3D plates share the same x,z section; 3D composes a flat-tip extrusion.
Deformed sections preserve v18's zero surface using 2 sides x 6 starts x 13
Newton iterations. Julia/WP4 must evaluate that projection directly in
`AutoBody` and compose bodies with `SetBody(min, ...)`; Float32/AD accuracy and
GPU cost are unmeasured. The v18 field-value parity control covers undeformed
plates only. A WP4 polygon distance uses a different approximated surface and
needs a separate parity test. There is no r_c on this WaterLily line; h controls
sampling and the development feature floors, not a displacement filter.
