# G4 B2.0 Brinkman extension deployment

Date: 2026-08-04

## Decision

Adopt **A: source-snapshot, container-built, case-local deployment** for the
project-owned `cfdSdfLinearBrinkman` extension used only by the B2.0 Cartesian
porous-cylinder cases.

At compilation, copy these four extension inputs byte-for-byte into the
compilation root at `extension_source/`:

1. `cfdSdfLinearBrinkman.C`;
2. `cfdSdfLinearBrinkman.H`;
3. `Make/files`; and
4. `Make/options`.

Write `extension_source_manifest.json` with a SHA-256 for every copied file
and a deterministic SHA-256 for the source tree.  The runtime runner must
copy that immutable snapshot into a newly-created temporary build directory
inside the pinned OpenFOAM v2512 digest Docker execution.  It builds there
with `wmake libso`, then copies the resulting library to each porous case at
`lib/libcfdSdfLinearBrinkman.so`.

The runner must create a fresh build area or reject a pre-existing `.so`.
It must never reuse a host, WSL, prebuilt, or prior-run library.  The published
compilation artifact remains source-only: it must not be modified by build
outputs and its public manifest must not disclose an ephemeral host path.

Each porous case's `system/controlDict` must load only the case-local library:

```text
libs ("./lib/libcfdSdfLinearBrinkman.so");
```

The body-fitted cylinder cases must neither reference, build, copy, nor load
this extension.

## Alternatives considered

- **A — snapshot then build in the digest-pinned v2512 container:** selected.
  It makes the exact source, ABI environment, build command, resulting binary,
  and run-time load evidence independently bindable.
- **B — track/distribute a prebuilt `.so`:** rejected.  It does not adequately
  bind the binary to its source, OpenFOAM ABI, or pinned image and conflicts
  with the generated-binary exclusion policy.
- **C — trust a host or WSL-installed library:** rejected.  It cannot establish
  consistent Windows/WSL/OpenFOAM provenance for B2.0 evidence.

## Required porous-case provenance

Every porous execution manifest must contain all of the following fields.  A
missing value is **inconclusive**, never a pass.

```text
extension:
  source_snapshot:
    source_tree_sha256
    source_files[{path, sha256}]
  build:
    container_image_digest
    openfoam_distribution
    openfoam_version
    foam_environment_identity
    canonical_container_command
    build_log_sha256
    library_relative_path
    library_sha256
  runtime_load:
    controlDict_sha256
    fvOptions_sha256
    beta_field_sha256
    library_sha256
    selected_option_type: cfdSdfLinearBrinkman
    selected_option_name: porousCylinderResistance
    solver_log_sha256
    load_log_assertions
```

The canonical command records the container-internal work directory, mount
contract, and `wmake libso` invocation, not a temporary host pathname.  The
image reference must be the same digest-pinned v2512 image as the channel
gate, never a mutable tag.

`load_log_assertions` must prove from the solver log and generated artifacts
that `simpleFoam` selected the `cfdSdfLinearBrinkman` finite-volume option,
read `porousCylinderResistance`, and wrote `brinkmanResistance` at the final
time.  A library-file hash without these run-time assertions is insufficient.

## `fvOptions` semantic contract

The runner must parse and verify semantics, rather than relying solely on a
dictionary hash.  The selected option is exactly
`porousCylinderResistance` of type `cfdSdfLinearBrinkman`, is active, and
declares:

```text
selectionMode       all;
U                   U;
betaField           beta;
betaMax             [0 0 -1 0 0 0 0] 1.5e5;
resistanceField     brinkmanResistance;
```

Thus `beta` is the explicit dimensionless area-fraction field, `betaMax` is
the fixed positive `1/s` coefficient, and the extension's immutable
kinematic source is `Su(U) = -betaMax * beta * U`.  The written positive
field `brinkmanResistance = betaMax * beta * U` is used only for total porous
resistance reduction; it is never a pressure or skin-friction decomposition.

These conditions supplement the hash binding.  Any differing selection mode,
field names, beta dimensions/value, resistance field, option type/name, or
case-local library path is an execution-contract failure.

## Scope and acceptance

This decision defines runtime provenance and deployment only.  It does not
change the B2.0 physical constants, force convention, grids, cylinder
acceptance thresholds, or the channel-before-cylinder gate in
[`2026-08-04-g4-b2-laminar-scope.md`](2026-08-04-g4-b2-laminar-scope.md) and
[`2026-08-04-g4-b2-cylinder-cross-fidelity-design.md`](2026-08-04-g4-b2-cylinder-cross-fidelity-design.md).

Implementation is required before a porous-cylinder run can be accepted as
B2.0 evidence.  A compiled library or successful `wmake` by itself is only
Capability evidence; Target-physics remains subject to the existing
three-grid body-fitted and porous cross-fidelity gates.
