`src/cfd_sdf` and `julia/CFDSDFWaterLily/src` are enumerated by historical source freezes.
Place new GEN-01 code in `src/cfd_gen/` and `julia/CFDSDFWaterLily/gen01/`.
Reuse existing `cfd_sdf` modules by import without changing their frozen source.

Phase A is solver-free software. Thickness/gap defaults of 4h are development
defaults pending the registered RES-00 ladder. Movable components alone own
rules envelopes, ground/domain clearance, forbidden masks and roots; finite
union topology and movable/fixed pair gaps include fixed context. Explicit
`MergedElement` IDs appear in gate `distance_contract_exemptions`: their min
union is not a band signed distance inside overlap, and its BDIM effect needs
measurement before MW-01.

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

2D and 3D plates share the same x,z section; 3D composes a flat-tip extrusion.
Deformed sections preserve v18's zero surface using 2 sides x 6 starts x 13
Newton iterations. Julia/WP4 must evaluate that projection directly in
`AutoBody` and compose bodies with `SetBody(min, ...)`; Float32/AD accuracy and
GPU cost are unmeasured. The v18 field-value parity control covers undeformed
plates only. A WP4 polygon distance uses a different approximated surface and
needs a separate parity test. There is no r_c on this WaterLily line; h controls
sampling and the development feature floors, not a displacement filter.
