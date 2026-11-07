# WP4 Amendment 3 independent geometry review

Evidence class: software/static geometry, no CFD or physics qualification.
Native read-only reviewer inspected the geometry, tests, scene bridge, Julia SDF and plot diff.
All required governing/technical documents were read in full across the assigned workers.

The reviewer found an initial duplicate-endpoint gate bypass caused by the generic SDF helper
normalizing explicit closure before the gate compared reconstructed surfaces. The parent fixed it
with a direct unique-vertex check on the input JSON polygon. A regression rejects append(first).
The reviewer independently confirmed the correction.

Independent cyclic NumPy readback of all 10 JSON scenes found min segment 0.133179922501 mm,
max segment 0.992904900205 mm, max adjacent length ratio 2.897564688141, and max noncap turn
3.445371053014 degrees. Every polygon has unique vertices and no duplicated closing endpoint.
Exactly the suction/pressure TE cap corners are angle-exempt; cap interior vertices are tested.

Every paired printed source row occurs in the unshifted sharp contours within 2.45e-13 mm.
After removing declared translations, thick vs sharp camber changes by <=8.53e-14 mm,
TE midpoint by <=2.85e-14 mm and retained LE cap samples by <=1.43e-14 mm.
Python closes internally; Julia traverses cyclically. New Julia square probes exercise the
last-to-first edge directly. No remaining actionable geometry/closure defect was identified.

This is source/geometry verification only. The parent separately ran pytest and CPU Julia tests.
The current WP5 adapter still expects explicit closure; see wp5_geometry_readback.json for the
actual rejected readback and wp04_report.md for the required downstream adapter change.
