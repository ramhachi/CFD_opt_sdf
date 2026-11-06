# WP5 development validation artifacts

These artifacts document code contracts and a bounded local OpenFOAM smoke.
They are not TR-00 qualification, production RANS, measured experimental Cp,
grid convergence, or proof that local gmsh reproduces Kaggle's realization.
The registration and LOCAL-OF-01 remain unchanged.

`archives.json` binds all three archives by SHA-256 and byte count. Each archive
contains `ARCHIVE_MANIFEST.json`, which maps every other member to its byte
count and SHA-256. The archives were read back and all members checked after
writing. Members are ordinary files with relative paths, sorted names and
zero archive timestamps. Extract into a new directory; do not overwrite a
previous run or the repository's immutable evidence.

- `local_smoke_artifacts.tar.gz`: the local wrapper's metadata and log,
  package-lock comparison, exact rendered smoke kernel/source bundle, and
  both case directories under `smoke_01/`. Each case retains the original
  mesh, manifest, dictionaries, generator/checkMesh/solver logs, raw total
  and per-element coefficient/pressure/viscous force histories, their hashes,
  and `case_result.json`. Each one mesh-only gate precedes exactly 200 SA-WF
  iterations on that same mesh. There is no continuation or production solve.
- `rendered_kernels_and_inputs.tar.gz`: final TR-00/main kernel directories,
  their plans and embedded-source bundles, all five WP4 JSON/NPZ inputs, and
  the read-only geometry producer/table snapshot. Main kernels are blocked
  until explicit TR-00 qualified cells are supplied during a new render.
  Rendering made no Kaggle API/CLI call. `source_commit` is the observed base
  HEAD and `source_dirty=true`; the exact source inventory, not that HEAD
  alone, identifies the rendered implementation.
- `test_logs.tar.gz`: raw pytest/compileall/collection logs, both complete
  non-Metal JUnit XML files, the original native-abort/interrupted attempts,
  and the six Metal tests' individual logs on each version. Its identity is
  also in `test_validation.json`. Every legacy non-Metal node ID and outcome
  matches base; adding the separately observed six Metal device failures
  accounts for all 3562 base / 3681 final nodes, with 119 new passes.
- `smoke_mesh_summary.json`: gmsh/OpenFOAM-style geometry quality proxies.
  Real checkMesh results remain in the archived `case_result.json` and logs;
  gmsh's internal and boundary skew proxies are not checkMesh's maximum skew.
- `smoke_source_comparison.json`: SHA equality of all executed mesh/foam/driver
  source between the smoke bundle and final implementation, plus AST equality
  of the collector helpers called by that driver. The later WP4 interchange
  adapter was validated independently using synthetic records.
- `smoke_force_closure.json`: the two actual 200-row smoke histories checked
  for common sampling, total/element closure and dimensional-force/coefficient
  consistency. The largest absolute coefficient difference is below 3e-8;
  these are output bookkeeping checks, not converged physical coefficients.
- `schema_validation.json`: both JSON Schema 2020-12 metaschema/instance
  checks and the actual WP4 analyzer's input check on synthetic histories and
  a synthetic reference. Its synthetic label is only an interface/arithmetic
  exercise. `actual_physics_or_reference_validated=false`.
- `frozen_inputs_unchanged.json`: original source/roadmap/registration/pins
  compared byte-for-byte against the base commit.
- `render_validation.json`: all 14 final rendered wrappers compiled without
  invoking main; embedded source inventories and hashes matched current inputs.
- `test_environment.json`: Python/dependency versions and final source/test
  hashes. No project dependency manifests were changed.
- `metal_environment_diagnostic.json`: all six existing Metal tests invoked
  separately in fresh processes on base and final source, avoiding the native
  abort after a failed MLX import. All six fail on both versions because no
  Metal device is accessible in this sandbox. This is an environment failure,
  not a passing or skipped GPU validation.

The local Docker command was:

```sh
.venv/bin/python scripts/topo2d00/build_tr00_kernels.py --stage smoke \
  --geometry E2_sharp=work/wp05/geometry/E2_sharp.json \
  --geometry E2=work/wp05/geometry/E2.json --out work/wp05/local_smoke_kernel
.venv/bin/python scripts/local_openfoam.py run \
  work/wp05/local_smoke_kernel/smoke_01 --out work/wp05/local_smoke_run \
  --cpus 4 --memory 8g
```

WP4 geometry inputs came from its development `topo2d-scene-v1` producer,
captured with source/table hashes in `geometry/input_snapshot.json` in the
render archive. These source tables identify unverified OCR, and no physical
geometry or BDIM-core qualification is inferred from this local check. The
legacy `_sharp` arm retains the original finite trailing-edge cap; its name
does not mean a mathematically sharp cusp. Both actual E2 inputs therefore
use the explicit blunt-cap/no-fan path. Separate synthetic-cusp unit meshes
exercise the inherited sharp-tip fan.

The retained formal run proposal uses the WP4 JSON geometry files. NPZ is
also a supported mesh-generator input, and its raw input bytes have their own
SHA. That raw NPZ hash must not substitute for the JSON-file geometry identity
required by the current WP4 study-freeze contract. A formal NPZ-to-JSON identity
mapping would need separate agreement and verification; it is not inferred.

`test_validation.json` and compressed raw logs record the original unfiltered
suite's native abort, the interrupted pre-interoperability final attempt,
focused final tests, and the complete suite comparison with only the known
Metal file explicitly ignored. The separately run Metal node failures belong
to the aggregate failure-set comparison. No partially completed or aborted
suite is a passing result; the unfiltered one-process command did not complete.
