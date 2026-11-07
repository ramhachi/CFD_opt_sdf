# WP4 Amendment 2 independent geometry review

Evidence class: SOFTWARE_REVIEW_ONLY. Read-only review of the current generator against
TOPO-2D-00 registration Amendments 1 and 2. This is not registration, a source-image
qualification, CFD evidence, or approval to run a formal campaign.

Reviewed generator SHA-256: `3f33be577438fbe3e78eaa1d589bbe1172e0b93330088f5b8f080f54f20ee512`.

No blocking geometry defect was identified in the reviewed source or adapter checks.
The generator uses the T2-0 natural cubic contour-spline rule, retains every source pair,
then bounds each source-spline interval by numerical integration of the spline speed.
Its PCHIP maps pair the two surfaces without replacing the contour spline. The recorded
maximum source-spline arc interval is below 0.698 mm. Generated polygons additionally
check every segment, including subdivisions of the finite trailing-edge cap, against
1 mm and every surface turn, including the leading edge, against 5 degrees; only the
two trailing-edge cap corners are exempt.

The preserved leading-edge region is selected by surface arc length at 2 percent of
the nominal element chord. The smoothstep ramp uses camber arc length. The controlled
region starts at the original maximum-thickness station. Camber-normal reconstruction
preserves the camber and trailing-edge midpoint, removes paired tangential separation
outside the cap/ramp, and never reduces source normal thickness. The smooth L8 width
envelope is at least the source width and the 4dx floor; a separate continuous polygon
normal-ray gate checks actual width. The code explicitly excludes the preserved cap
and ramp from the positive global-width claim. It does not call the polygon or the
software gate an independently qualified BDIM result.

The source-table paths and SHA-256, original camber, preserved cap, thickness scope,
normal reconstruction, thickness ratios, finite trailing edges, nominal gap/overlap,
actual polygon gap, ground clearance, self-intersections, and element overlap are
rechecked before a scene is accepted. E3 splits the flap chord equally and bisects the
main-to-flap chord-angle change. The datum is the source-table leading-edge point and
the finite trailing-edge midpoint, as adopted in Amendment 2; it is not redefined by a
new extremum of the resampled contour.

For the main grid, the regenerated main/flap/half-flap maximum thickness ratios are
4.5947536662 / 8.8667345026 / 17.7334690053. The E2 actual minimum polygon gap is
8.5741101958 mm; the E3 adjacent gaps are 8.3950855008 and 8.9362600688 mm, above
4dx = 7.4466666667 mm. These are geometry facts, not aerodynamic evidence. All OCR
coordinates remain UNVERIFIED pending comparison with PDF page images.

The actual sibling WP5 loader accepted every one of the ten scene JSON files for both
fine30 and med30: 20 validations, no geometric repair, gmsh import, mesh, or solver.
The independent adapter report is `wp5_geometry_readback.json`. It binds the actual WP5
source and each input scene SHA. Its largest observed segment is 0.992904899966 mm and
largest surface turn is 3.02243306101 degrees.

One nonblocking future-runtime risk remains: `validate_scene` uses exact dictionary
equality for recomputed source/sampling metadata that includes quadrature-derived and
geometric float values. Last-bit differences across SciPy versions or platforms could
reject an otherwise byte-identical frozen geometry JSON. The current-host tests and
actual WP5 adapter validation pass. Keep source SHA/discrete identity exact; any future
portability change should use an explicitly justified numerical comparison for derived
metric floats without weakening geometric thresholds or silently repairing polygons.

No source or existing evidence was changed by this independent review. CPU solver and
whole-suite verification are owned by the parent agent and are not duplicated here.
