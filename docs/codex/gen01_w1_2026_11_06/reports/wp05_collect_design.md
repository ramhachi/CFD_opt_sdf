# WP5 collection and local kernel rendering design

Amendment 1 supersedes the first-attempt convergence and readiness decisions
below; [wp05_amendment1_design.md](wp05_amendment1_design.md) is the active
correction design. T2-0d is no longer imported or applied to SIMPLE histories.
The inherited T2-0b `force_summary` and T2-0c raw-tail threshold define the
shared policy, re-exported in the foam manifest. No limit-cycle label exists.
Nonfinite coefficients are diverged/NUMERICAL; generator/mesh failures export
MESH_FAILED. Proxy failure does not gate the solver when checkMesh accepts.

Collector asserts equal `n_layers` within each family across configs/models.
Eight mesh SHA values must be distinct in every (config,model,family); a
duplicate gives `DEGENERATE_REALISATIONS`, retained point means, null interval
and INCOMPLETE ratio input. Export also sets affected per-run statuses to
INCOMPLETE to prevent the previous WP4 reader from certifying those records.
Shared force objects now require `observable` (pressure_cl sharp, total_cl
thick); same-observable pressure and total thickening deltas are descriptive.
Schema updates must be integrated into WP4 before formal analysis.

The renderer requires a clean whole tree, verified geometry and an explicit
`topo2d00-rans-freeze1-v1` binding to HEAD and every bundled input SHA. Supply
all six study geometries with `--study-geometry CONFIG=PATH` and the owner's
freeze with `--freeze PATH`. Missing binding keeps render_kind=development,
ready_for_execution=false, push_plan empty. E3_sharp is a BL-plan member but
not an additional force run. This amendment does not re-render real kernels;
the original bundles are historical and their readiness is revoked by
`wp05_amendment1_validation/render_invalidation.json`.

Written before implementation. Authority: W1 `00_README.md`, TOPO-2D-00
registration §§3–5,7–9, T2-0c evidence README, T2-0 summary, the immutable
T2-0b runner and T2-0d analyzer. The full WP5 design remains `wp05_design.md`.
No registered source, existing kernel, roadmap or evidence will be changed.

## Interfaces

The mesh worker supplies `t2d_foam_case.write_case(out, geometry, model,
family, realisation, iters)` and `fix_boundary(text, patches)`. Geometry JSON
has `config`, `elements` with `name`, closed `points_m`, and `te_kind`;
NPZ is the equivalent metadata plus arrays. Patch names are `airfoil`,
`airfoil_2`, `airfoil_3`. Force objects are `forceCoeffs` (all bodies) and
`forceCoeffs_<patch>` (each body). A single c1=0.2234 m and extrusion span
normalize every configuration; Cl is positive downforce, Cd positive drag.
Dimensional `forces` and `forces_<patch>` retain pressure/viscous vectors.
The actual v2512 `force.dat` header was checked in retained T2-0c output:
`Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x
viscous_y viscous_z`. The collector projects these with the same force axes
and reference area; it does not mistake forceCoeffs' front/rear columns for
pressure/viscous contributions. `coefficients` explicitly means
pressure-plus-viscous; `pressure_coefficients` is the Cp-comparable quantity,
and `viscous_coefficients` remains separate. Each has total and element values.

`run_rans.py` is the local-only-rendered kernel's measurement driver, not an
analysis verdict. It reuses the existing T2-0b runner's installer, process
control, log parsers, Cl block plateau and one continuation to iteration 15000
when the initial 5000 iterations have no plateau. Generation runs in isolated
subprocesses because gmsh has process-global state. Four independent cases
share each Kaggle CPU session. Raw coefficients retain object and restart
directories, hashes and mesh/geometry identities; failed/lost cases remain
explicit records. Local callers are limited to mesh-only or at most 200
iterations unless actually running inside Kaggle's environment.

`collect_rans.py` consumes extracted `case_result.json` directories and an
explicit expected run list/plan. It rejects unknown/duplicate keys, invalid
JSON, coefficient/mesh hash mismatches, missing completed-run force histories,
nonmatching sampling times and inconsistent element totals. Missing runs are
reported separately and make `complete=false`; CLI writes the diagnostic
artifact and exits nonzero unless `--allow-incomplete` is deliberately given.
Smoke records cannot become production results. The shared JSON schema is
`topo2d00_rans_result_schema.json` (`topo2d00-rans-results-v1`), copied
byte-for-byte from the actual WP4 consumer's schema during integration.
The detailed per-run diagnostic contract is
`topo2d00_rans_measurement_schema.json` (`topo2d00-rans-v1`).
An expected builder plan also binds each run's geometry SHA. A completed
run's absent history is an error; a recorded solver crash with zero/one rows
has null coefficients and its explicit failure classification instead of
aborting collection of the other cases. Hash corruption still fails closed.

Convergence calls the existing T2-0d `steady_stats` first. CONVERGED maps to
`settled`; finite stationary periodic iteration histories confirmed by
T2-0d's `urans_stats` (iteration coordinate, dt=1) map to `limit_cycle`.
The frequency is descriptive per iteration, never a physical frequency or a
URANS qualification. Nonfinite/blown-up histories map to `diverged`;
NOT_CONVERGED without periodic evidence stays `not_settled`. Infrastructure
and mechanical losses are `unavailable`. Only settled complete production
records are usable by WP4. T2-0d's raw classifications remain in the output.
Total and pressure-only convergence are evaluated independently; cancellation
between unsettled pressure and viscous forces cannot make a record usable.
For continued cases both statistics and coefficient means use the last
continuation segment, matching T2-0c; the full history is retained and checked
for hashes, continuity and force closure. Iteration-space periodic diagnostics
omit the inherited physical Strouhal number.

## Kernel packaging and budget

The builder emits deterministic, self-contained Python runner files with an
embedded tar archive of the exact source and five supplied geometry files.
Archive paths and each input SHA are checked before extraction/execution.
This permits rendering from a reviewable working tree without pretending it
is committed; the observed Git HEAD and dirty flag are recorded separately.
No Kaggle API, CLI, push, source checkout, cloud execution or production
solver is called during rendering. Existing v2512 hash locks and inherited
gmsh==4.15.2 are reused, without adding a dependency pin.

TR-00: 2 sharp configurations ×2 models ×2 families ×8 realizations =64 runs.
Main: 3 thick configurations ×2×2×8 =96 maximum, restricted to qualified
(model,family) cells after TR-00. Main kernels rendered before that decision
are explicitly blocked; rebuild with explicit qualified cells after judgment.
At 12 runs/kernel and 4 workers, there are 6 TR kernels and at most 8 main
kernels: 2 waves per stage with five concurrent sessions. The registered
13–21 min/5000 assumption yields a planning estimate only (the T2-0 summary
actually associates 13–21 min with xfine30 and 6–11 with fine30). Multibody
cost is unknown. For conservative partitioning use 60 min/5000 and 3× for a
continuation, so 3 waves of cases fit in 9 h plus setup; the hard session cap
is 11 h with 10 min reserved. Missing work at a cap remains incomplete.
Four full 11 h stage waves are 44 h ≈1.83 continuous days, not a measured
completion prediction or an assertion about account-level daily quotas.
The 13–21 minute envelope gives 34.7–56 total run-hours for 160 initial
solves; 20 workers would ideally need 1.73–2.8 h. The staged 12-run partition
uses 10 case waves in total (TR 3+1; main 3+3), giving 130–210 min plus setup,
inspection and the TR-00 decision, before continuations or multibody growth.
The individual case solver cap is 2.5 h. Those independent caps could sum
to 400 h; they do not enforce the study's 160 CPU h global cap. The builder
records `global_budget_enforced=false`: before production, the user must
maintain a shared study ledger across sessions and stop at the registration
cap. This is a disclosed orchestration boundary, not a budget guarantee.

`--stage smoke` generates two case specs (E2_sharp, E2), one realisation
each: mesh generation → gmshToFoam → checkMesh → 200 SA-WF iterations on
the same mesh. `mesh_only_stage.mesh_msh_sha256` must equal the final mesh
SHA. A second remesh is not silently introduced. No continuation or package
installation occurs in local smoke; the existing locked runtime is probed.
`--plan-only` emits run coverage without geometry and creates no runner.

The sibling WP4 design was inspected read-only when it appeared. Its proposed
`cells` schema had not been placed yet when the first measurement schema was
created. When the actual WP4 schema/analyzer appeared, the parent requested
an explicit adapter to its real consumer contract. The original detailed
schema is preserved at the measurement path, and the shared schema is an
exact byte copy of WP4's existing file. No sibling file is modified.

`to_wp4(measurements, reference_json)` groups by model/family and emits eight
paired realization IDs, each with all five configurations. Missing values
are `INCOMPLETE` and null; attempted numerical failures are `NUMERICAL`.
Sharp-arm forces explicitly select `pressure_coefficients` for comparison
with Cp; thickened main-arm forces select pressure-plus-viscous totals.
Every original row stays in per-config `diagnostics`, and full measurements,
the unmodified Cp reference estimate, and `component_by_config` remain in
provenance. Unknown total reference uncertainty is preserved, not replaced
by the two-reading sensitivity.

The adapter accepts only `digitize_cp.py`'s
`topo2d00_pressure_reference_v1`, common c1, downforce sign, global-streamwise
Cp integration, h=100 mm, and the unique nonzero E1_sharp→E2_sharp increment.
It verifies the signed increment and summed sensitivity against the two
reference estimates and checks that the unchanged 5% threshold is present.
No ratio rule, reference band or qualification verdict is implemented here.

The final integration follows the later WP4 schema revision (artifact-bound
reference provenance). `reference.source` includes the explicitly supplied
HTTP(S) `source.url` of both reference estimates; missing URLs stop shared
export instead of producing invented citations. `digitization_records` are
actual `{path, sha256, method}` objects for each user CSV (including Cl(h)
curves when used) plus the configuration manifest that records a tabulated
single-element value. The method records the operator/tool, element and
surface. Paths are canonical absolute paths resolved relative to the original
Cp manifest, not the collector's working directory. Manifest and CSV bytes are
re-read and checked against their recorded SHAs; duplicate paths and fragment
identifiers are rejected. These records can be listed directly in the parent
study freeze's input inventory. Distinct files do not themselves prove
methodological independence; the two-reader metadata and its scope remain.

`to_wp4(..., plans=(), geometry_sha256=None)` accepts explicit run/geometry
plans or a complete five-config geometry SHA map. Every supplied hash must
agree with observed measurement geometry, and shared output requires all
five main/sharp identities. `--geometry-plan PATH` supplies only metadata
from an unrun or blocked main plan without expanding expected run coverage;
therefore TR-only collection does not need main solves to run first. Missing
geometry identity stops shared export; `--measurements-only` remains available
for diagnostics without references or complete geometry metadata.

Actual source commit, dirty flag and archive/input SHAs are preserved from
provided plans and available kernel `environment.json`; available `install.json`
and environment records retain their own paths and SHAs. No missing runtime
identity is filled in, and this adapter does not create or infer a study freeze.

The default collector CLI requires `--reference` and writes the actual WP4
interchange. `--measurements-only` retains the detailed diagnostic output
when the user has not supplied Cp CSVs yet. `--plan` may be repeated for the
TR and qualified-main run plans; both sets bind their geometry SHAs and any
duplicate or unexpected run remains an error. Example after user runs:

```sh
.venv/bin/python scripts/topo2d00/collect_rans.py path/to/extracted/tr path/to/extracted/main \
  --plan path/to/tr/run_plan.json --plan path/to/main/run_plan.json \
  --reference path/to/user_pressure_reference.json --out rans_results.json
```

For TR-only output, pass only the TR coverage plan with `--plan`, and use
`--geometry-plan path/to/main/run_plan.json` to supply the already prepared
main geometry identities. Main force values remain `INCOMPLETE` and null.

## Test plan and assumptions

TDD fixtures cover closed schemas, exact key uniqueness, complete/missing
run behavior, corrupted hashes, per-element sum closure, finite settled and
periodic histories, divergence, smoke rejection and known nonsettled cases.
Kernel tests cover Cartesian counts, 12-run cap, five-session waves,
deterministic archive/render, embedded source hash checks, metadata CPU and
privacy settings, blocked production and overwrite refusal. Driver stubs
exercise inherited continuation and preservation of per-object histories.
No solver is invoked by these unit tests. Mesh/smoke integration belongs to
the parent. Kaggle package installation, runtime and multibody cost remain
unverified until the user runs the kernels; no TR-00 decision is made here.
