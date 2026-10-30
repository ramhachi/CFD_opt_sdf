# FD-07 (#37): design-lattice phase and sign-consistency diagnostics

Date: 2026-10-01. Evidence class: **diagnostic only**. The FD-05 and FD-06
registered FAIL verdicts, thresholds and outputs remain unchanged.

## Result

Changing only the design-lattice phase does **not** remove the irregular
solved-flow response in the fixed short CPU experiment. The original STL is
unchanged, but its trilinear representation changes; this is not an isolated
causal proof or a qualified replacement canonical state. No v18 is registered.

The upstream WaterLily sign-consistency branch exposes a concrete
initialization discontinuity at this fixture: approximately 10 nm nodal phi
noise changes the zeroth BDIM coefficient by about **0.8183** at some faces.
The original and shifted design lattices both retain this finite jump. It
must not be reclassified as random baseline-repeat noise or used to relax
existing FD acceptance thresholds.

## Fixed experiment and identity

Evidence directory: `docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/`.
Persistent premeasurement `plan.json` SHA-256:
`f0036608eb1705376f985a7f6617cf9181d4792b6f21cb90a8ae41afb6805d91`.
Source base: `bd1961565b6d1ce7b2feda3d525d48a4e1f35134`; new scripts are
bound by their explicit file hashes, since they were not committed at execution.
All 17 plan source hashes and both raw phi hashes passed prelaunch checks.

- Same registered source STL SHA-256
  `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`;
  copied unchanged as `source_surface.stl` for reproduction.
- Original control regenerated from that source and reproduced registered
  v17 raw **byte-for-byte**, including signed zeros. Shape 121×65×49,
  spacing 0.025 m, original origin (-1, -0.8, -0.6) m.
- Shifted design origin: original + h×(0.27, 0.37, 0.43). Source geometry and
  physical flow grid stay fixed. The fluid-only SDF support translates;
  minimum source-bound clearance is 0.33925 m (control 0.35 m).
- CPU Array, Julia 1.12.6, WaterLily 1.8.0, four threads, Float32 solver and
  phi storage, normal floor 0.25, original pressure tolerance/iteration limit.
  flow_24: 150×72×54, origin (-2.5, -1.2, -0.9) m, spacing 1/30 m,
  registered moving ground and Re=80. This is not vehicle/high-Re evidence.
- Each lattice: baseline, seed-1 white phi noise ±1e-8 m and ±1e-7 m;
  identical lattice-local noise array across signs, scales and lattices.
  It is not the same world-space random field on different lattices.
- Exactly ten solves to tU/L≥3, force sampling every eight steps plus final
  sample. Endpoint interpolation and trapezoidal integration cover the same
  exact [2,3] window; force conversion is 1/900 N per solver-force unit.
- No mask/topology/update contract is exercised. One seed, no fresh repeated
  baseline, short transient window. All qualification/update flags are false.

The first preparation attempt with the helper's 200,000-point chunks failed
raw byte reproduction before creating a plan or starting a solver and used
about 11 GB workspace. Its discarded raw candidate was not retained, so the
mismatch mechanism (including signed-zero versus distance differences) is
unknown. The bounded 8,000-point preparation uses the same signed-distance
helper and passed full control identity before the recorded measurement.
Historical genesis/evidence/source files were not changed. The diagnostic
preparer changes the imported helper's chunk size within its own process;
it is intended as a standalone diagnostic, not a production genesis API.

## Measured forces in the short [2,3] window

All values below are N. These are transient diagnostic window means, not
qualified steady drag/downforce.

| Lattice | Baseline drag | Baseline downforce | Δdrag, +10 nm / −10 nm | Δdownforce, +10 nm / −10 nm |
| --- | ---: | ---: | ---: | ---: |
| Control | 0.334373767 | 0.345760171 | +0.000293366 / +0.000329232 | +0.000825700 / +0.000964710 |
| Shifted | 0.374098193 | 0.370764427 | −0.000563341 / −0.000180626 | −0.001175696 / −0.000674968 |

The shifted baseline changes by +11.88% drag / +7.23% downforce. Geometry
representation and normal fields therefore cannot be assumed unchanged.
Design-cell census below |gradient|=0.25 grows from 3 to 828, while nodal
|phi|<1e-7 m samples drop from 5,370 to zero; neither count grants a geometry
qualification or permission to adopt the shifted state.

Odd response is (R+−R−)/2 and even response is (R++R−)/2−R0. On the shifted
lattice, increasing intended noise amplitude tenfold gives odd ratios
0.289 (drag) / 1.446 (downforce), and even ratios 1.342 / 1.421.
These descriptive ratios do not establish proportionality and have no
postmeasurement PASS threshold. Actual Float32 realized noise is recorded:
roughly 8.05e-9 m RMS at the 1e-8 intended scale, with about 70,000 changed
nodes. The same noise-array SHA is logged for all ten runs.

`summary.json` SHA-256:
`c6e2990155c715044809749d2ac5e83c543c2a13beac84a7ba1aa7455268dbd8`.
An independent stdlib integration reproduced all ten exact-window means;
raw pressure+viscous force closure differs by at most 5.68e-14 solver units.

## Actual sign-consistency branch exposure

Pinned WaterLily 1.8.0 `src/Body.jl` SHA-256:
`aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee`.
Its initialization uses:

```julia
d_i = abs(d_i) <= 0.5 ? d_i : copysign(d_i, d[I])
```

An independent actual-body-plus-ground census and the full initialized
simulation arrays agree:

| Lattice | Near-zero centers (1e-6 m census) | Exposed faces with abs(d_face)>0.5 | Sign flips, ±10 nm | Maximum actual Δmu0 |
| --- | ---: | ---: | ---: | ---: |
| Control | 1,773 | 261 | 54 / 64 | ~0.8183113 |
| Shifted | 798 | 117 | 57 / 53 | ~0.8183115 |

The exposed faces exceed the half-cell threshold only slightly: control
2e-7–4.77e-6 solver units, shifted 1.25e-6. For flip-relevant faces the
half-cell Lipschitz-bound excess reaches about 1.25e-6 solver units
(4.17e-8 m). Coordinate/constant/storage precision remains a plausible
contributor. This is evidence of a discontinuous initialization map at the
fixture, not yet a proof that this branch alone explains the long-window
FD-06 force deviations or that the upstream handling is universally wrong.

The earlier FD06_FLOAT=64 switch retained Float32 phi and changed world-query
coordinate arithmetic and constants as well as solver arithmetic. It does
not isolate or exclude coordinate precision or SDF-storage roundoff.

## Additional solver-free arithmetic and branch controls

A separately preregistered matrix keeps solver precision, returned-distance
dtype and phi storage at Float32; the sampled distance values vary with the
world map. It constructs nine initial states (three
maps × baseline/seed-1 ±10 nm), with **zero** flow steps or pressure solves.

| Map | World-query arithmetic | Constants | Maximum Δmu0 under ±10 nm |
| --- | --- | --- | ---: |
| A | Float32 | Float32 (original path) | ~0.8183113 |
| B | Float64 | Same Float32-rounded constants promoted to Float64 | 8.94e-7 / 9.54e-7 |
| C | Float64 | Original declared Float64 physical constants | ~0.8183103 |

B and C baseline mu0 arrays each differ from A by about 0.81831. B's local
noise response improves in this tested fixture, while C retains the finite
jump. Arithmetic and constant representation interact with the branch;
"use Float64" is not a validated general fix. No B/C solved forces were run,
and no map was adopted into production.

On the same 261 fixed exposed faces, an algebraic ablation holds **all sampled
center and face distances fixed** and evaluates the kernel with the sign
correction enabled versus disabled. For A, the corrected maximum delta is
0.81831123 (54/64 faces above 1e-3), while the uncorrected maximum is only
2.6e-7 / 2.7e-7 (zero faces above 1e-3). For C, correction retains jumps at
10/23 faces; uncorrected deltas remain around 2.5e-7. This directly localizes
the large coefficient change on the recorded faces to the sign-consistency
correction. It does not establish the effect of removing that correction on
solved forces, conservation, thin-body handling, other shapes, or long-window
FD; the production solver remains unchanged.

Files in `world_map_precision/` contain the preregistration, source/runtime
hashes, all nine initial-array hashes and statistics, fixed-face scalar
values and independent descriptive summary. Summary SHA-256:
`d30771f9884fd2cd13966dd2d39ce45ee03ef9950d2e463bc597fc66e3314e74`.

## Next bounded investigation

The design-only shift is not a remedy and does not justify v18 adoption.
Before any future formal FD round, test a separately registered
sign-consistency intervention against the unchanged baseline, retaining
physical mapping, thin-body/moving-ground semantics and small-perturbation
controls. Its primal and geometry behaviour must be checked before any
FD/gradient or optimization qualification. Do not loosen FD-06's 5% plateau
threshold or treat deterministic mask jumps as baseline-repeat noise.

## Software validation

- Focused diagnostic and existing normal-floor checks: **11 passed**.
- `.venv/bin/python -m compileall -q src tests`: passed.
- Baseline `.venv/bin/python -m pytest -q`: **1216 passed, 37 failed,
  4 skipped**, 214.28 s.
- Final `.venv/bin/python -m pytest -q`: **1221 passed, 37 failed,
  4 skipped**, 311.26 s. Exact failing test identities are unchanged: zero
  new failures. The full suite is not green; prior failures remain out of
  this diagnostic scope and are listed in `software_validation.json`.
- `git diff --check`: passed; it is checked again before commit.

## Reproduction

From the repository root, use a **fresh** output directory:

```sh
.venv/bin/python scripts/sdf_native_fd07_lattice_shift_prepare.py \
  docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/source_surface.stl \
  docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/control/phi.raw \
  work/fd07_reproduction
```

Before solving, verify every `source_file_hashes` and each lattice
`raw_sha256` in the new plan. The original check is retained as
`preflight_identity.txt`; its commands are in `execution_commands.txt`.
Then run:

```sh
julia -t 4 --project=julia/CFDSDFWaterLily \
  scripts/sdf_native_fd07_lattice_shift_cpu_probe.jl work/fd07_reproduction
.venv/bin/python scripts/sdf_native_fd07_lattice_shift_analysis.py work/fd07_reproduction
```

Independent branch census (replace `control` and origin for shifted):

```sh
julia --threads=1 --project=julia/CFDSDFWaterLily \
  scripts/sdf_native_fd07_sign_branch_census.jl \
  docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/control/phi.raw \
  -1,-0.8,-0.6 work/fd07_control_faces.csv
```

Runtime capture hashes the actual WaterLily source package and registered
local sources. `MANIFEST.sha256` preserves the original 26-file measurement
snapshot. Additional review/validation evidence is separately covered by
`FINAL_MANIFEST.sha256`; the original manifest is not rewritten.

Additional map/branch controls (solver-free):

```sh
julia --threads=1 --project=julia/CFDSDFWaterLily \
  scripts/sdf_native_fd07_world_map_precision_probe.jl \
  docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/control/phi.raw \
  docs/evidence/sdf_native_fd07_lattice_shift_diagnosis_2026_10/review/control_final_sign_branch_faces.csv \
  work/fd07_world_map_precision
```
