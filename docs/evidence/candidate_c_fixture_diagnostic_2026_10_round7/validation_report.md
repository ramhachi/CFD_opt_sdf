# Round 7 source and pre-execution validation

Evidence class: bounded CPU implementation diagnostic preparation and pure geometry/runtime preflight. No Simulation was constructed and no solver timestep was taken.

## Immutable source and criteria identity

Criteria: C-OP-01-CPU-GRID-SDF-LONG-DIAGNOSTIC-7; SHA-256 c2f3161b45797012331db271eab136d1c1ba6b5c7bbe7bfb8b085789723f17d5.
Host runner SHA-256: fbd20f28735b1bfa16d1c923db32357c7b1ed6cb16210674050dda71aba8cccd.
Julia job SHA-256: f615aa42ac34158d66e733fefbcadbe79011e1d4de1e451cda9fbdc108f4e448.
Source inventory SHA-256: 1726fde054f8fd559c562d957db7d95a927015e2698c51b87f13ee19c2b2d1f7.
Rejected prior draft is preserved in docs/evidence/candidate_c_fixture_diagnostic_2026_10_round6_rejected_preexecution/ and was rejected before solver initialization.
Round 7 fixes deterministic path-shadowing, distinct preflight identities, explicit no-interface NA margin, existing GridSDF constructor arithmetic slack, raw API forces versus once-negated SI force, and description of differently staggered nearby velocity.

## Pure geometry/runtime preflight

Command: PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python scripts/verify_candidate_c_grid_sdf_long_cpu_diagnostic_round7.py --plan docs/evidence/candidate_c_fixture_diagnostic_2026_10_round7/plan.json --geometry-only
Result: passed. Julia 1.12.6, WaterLily 1.8.0, 4 threads, Array, Float32; job and source-inventory hashes matched. No Simulation was initialized.

Geometry records:
- sphere: margin 0.14999999403953557 m; SHA-256 432c45e63734b399f9ba8b9abce7b71ac63dfe45ba4549757b1152c11d75f575
- plate_1cell: margin 0.14999999999999997 m; SHA-256 067b7728c83d1676b2919efacc3a2b7fed8e90a8e9c05c99472df781a375e72e
- plate_2cell: margin 0.14999999925494195 m; SHA-256 bed5e090e5518eab0aa8c903668a849cd600212adc6a938655bc86375b2da256
- moving_ground_only: no zero level; margin NA; SHA-256 1cf218b1e2a00f35e8a879e6195b745a93bf1df1363b6023498cf48e4fc1495b
The registered arithmetic tolerance reflects the existing GridSDF constructor check and does not set or relax a physical acceptance threshold.

## Software validation

Focused tests: 5 passed.
Compileall: passed.
Julia Meta.parseall syntax check: passed; no simulation initialized.
Source/criteria/runtime parser identity: passed; solver_steps_authorized=false.
Full suite: 37 failed, 1264 passed, 5 skipped. All 37 failing IDs exactly match the controlled baseline (new=0, resolved=0); these are existing ignored work/ fixture/evidence absences. Exact IDs are in pytest_failure_ids.json.
git diff --check: passed.

Raw geometry transcript SHA-256: 4fa4624eded8cb4fa03ab45934fbbdc831f0378c20dc64a99dbcaa752ae56179.
Runtime JSON SHA-256: 1227107487bb21470ce5f3ca6e2060ca379703cfcdebed1e9fcff9542b086af3.
Failure-ID JSON SHA-256: 2cf203e3083cca2dfba8ccde6dc9b190a83f725c4c6cd4496d8ad309c1318934.
Supporting evidence file hashes are listed in validation_artifacts.sha256.

## Scope

This source and geometry preparation does not qualify immersed-body mass conservation, no-penetration, stationarity, native/GridSDF accuracy, Candidate C production status, W3-C/W4-C, gradients, reverse mode, optimization, topology, or shape updates. All six qualification flags remain false. Initialization and the bounded CPU diagnostic await orchestrator dispatch.
