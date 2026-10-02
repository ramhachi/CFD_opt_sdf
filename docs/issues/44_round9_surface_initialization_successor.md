# #44 Round9 surface diagnostic preregistration

Round8 is preserved as initialization ERROR before Simulation. Its direct
StaticArrays import was unavailable in the pinned WaterLily-only Project.
Round9 uses WaterLily.SVector from that exact existing dependency; Project,
Manifest, operator and geometry inputs remain unchanged. It additionally
casts raw pressure and viscous components to Float64 before adding and
converting to N, matching the independent host arithmetic. This was identified
before any solver step or force sample. Force sign and .0025 N scale are unchanged.

The fresh immutable Round9 retains .10-.25 time window, 4 x 3 fixture matrix,
all surface levels, raw fields and integrity tolerances. Round8 source/criteria
and ERROR are not edited. No physical acceptance threshold is introduced.
A parent external registration and integration push are required before fresh
initialization or steps. All six flags remain false.

Validation: 5 focused Python controls PASS, exact dependency control PASS
without Simulation, Julia source parse PASS, compileall PASS, full pytest
37 failed / 1311 passed / 5 skipped with zero extra baseline failure IDs.
See `docs/evidence/candidate_c_surface_flux_round9/validation.json`.
