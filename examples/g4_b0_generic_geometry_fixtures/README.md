# G4 B0 generic geometry fixtures

This pack supplies deterministic STL replacements for the generic native-v2
geometry path.  `sphere`, `box`, `plate`, and `multi_component` are closed,
positive-volume inputs.  `invalid_stl` deliberately contains one open triangle
and must be rejected before any fixture result directory is published.

Run it from Python with `run_generic_geometry_fixture_pack`; the resulting
`fixture_result_index.json` binds each fixture family to its YAML/STL input
SHA-256 and, for accepted fixtures, to the preflight report, canonical snapshot,
and geometry manifest.  This is only G4 B0 geometry-path evidence; it does not
qualify CFD, derivatives, or topology optimization.
