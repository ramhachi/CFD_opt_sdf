# FORCE-00 CPU implementation evidence

This directory records local CPU software checks for WP2. It is not a GPU
measurement, a frozen registration, an adoption decision, or a re-evaluation
of UNC-01/FID-01/SCREEN-01. No qualification flag changes.

Raw terminal logs are preserved losslessly as `validation/*.log.gz`.
`validation/log_archive.json` records both compressed and original-byte hashes.
Use `gzip -dc <file.log.gz>` to read them. The job patch is the exact
`git diff --no-index --unified=0` representation, avoiding whitespace that is
only an empty patch-context marker.

`uniform_pressure.json` contains U1/U2 geometry-only pressure integrals. There
is no flow solve: `p=1`, `u=u⁰=0`. The field and reductions use Float64; the
canonical v18 phi retains its registered Float32 bytes. U1 uses the same
GridSDF/normal-floor/Candidate-C geometry and moment rule as the parent. Its
32 three-dimensional Halton vectors are read from the four FID V1 criteria,
with their registered mirror pairs, and eight z-only placements are generated
by the existing rule at the next four Halton indices. U2 uses the W2a exact
sphere geometry at radii 8/16/32 cells and those eight additional full 3D
vectors. The empty sphere far field is cropped; no domain or flow claim is made.

The JSON records individual vectors, shifts, maximum/RMS norms, source hashes,
runtime, and the quoted issue #369 table. Its `cur`/`nds` vectors are pressure
reaction integrals; `cv` uses the physical body-force convention. Their exact
uniform-pressure answer is zero. U1's area convention is the registered v18
genesis planform area divided by the flow-cell spacing squared. It is distinct
from the historical coefficient normalization area of 0.64 m². U2 uses πR².
The upstream numbers describe different off-grid placements; they are not
replay targets. Source digests are captured before local code is included and
checked again before writing the output. The output refuses an existing path.

`cpu_job_regression/` contains two real, small CPU solves of the v18 parent,
using the registered flow_16 grid, candidate and moving ground. The harness
executes the actual parsed measurement functions from the registered job and
the new copy. It uses CPU CUDA-telemetry stubs, cadence 1 and the short test
window [0.15,0.30] with split 0.225. It compares all original 13 CSV columns
byte for byte, the five appended `cur` tokens, and final solver arrays. This
does not establish T4 C1 regression or full-window equivalence.

The Julia selftest separately checks off-grid circles and spheres, stored μ₀
band values, closure ≤1e-12 for Float32 and Float64 moments, each CV momentum
term against analytic fields, pressure-gauge invariance, nonzero viscous
traction, box validation, and observational readouts. Fresh Julia processes
spend about one to three minutes compiling these checks on the observed host;
the requested seconds of end-to-end cold-start runtime has not been achieved.

## Reproduction

```sh
julia --project=julia/CFDSDFWaterLily -O0 scripts/force00_selftest.jl
julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl /tmp/force00-uniform-new.json
julia --project=julia/CFDSDFWaterLily scripts/force00_job_regression.jl /tmp/force00-job-new
.venv/bin/python -m pytest -q tests/test_force00_gate.py tests/test_force00_uniform_inputs.py
```

The uniform-pressure script uses the existing `.venv` Python and its NPZ loader.
Its JSON/TOML bridge uses Python 3.11+ `tomllib`; this host runs Python 3.12.
The force/gate implementation adds no dependencies and does not change the
pinned Julia project or manifest.

## User-run GPU inputs and gate

No GPU is launched by any of the commands above. The GPU job is the literal
`waterlily_force00_job.jl` copy with appended measurements and explicit box
handling. `waterlily_force00_job.diff` shows every change. Its original 13 CSV
columns, force signs, cadence 8, [80,120] window and phase meanings are kept.
The summary also records the box's inclusive lower/upper cell indices.

The copy retains the registered flow_32 inventory. F1 can use the additional
`waterlily_force00_dispatch.jl` launcher: `FORCE00_CASE=flow_24` selects the
case inventory and filter at include time; `FORCE00_CASE=flow_32` leaves them
unchanged. No solver, force, window or phase expression is substituted.
The source and CPU regression explicitly test the two allowed AST changes.

For a later, separately reviewed GPU launch, inherit each registered run's
canonical identity, lattice, hashes and phase environment from its campaign.
Specify `FORCE00_CV_BOX='lo:hi,lo:hi,lo:hi'` as inclusive pressure-cell ranges.
For the present parent, example enclosing boxes are `47:106,11:64,11:46` on
flow_24 and `62:141,14:85,14:61` on flow_32. The job preflight checks actual
candidate support, scene-face clearance ≥4 cells and domain inset ≥2 cells;
invalid boxes fail. The current job is static; moving bodies must retain
per-measurement `force_readouts` box validation. These sampled SDF checks are
not a continuum certificate for nonmetric geometry.

The gate accepts `force00_runs.json` with schema `force00_runs_v1` and a flat
`runs` list. Each item has exactly `run`, `phase_id`, `state`, `grid`,
`forces_csv`, `summary_json`. File paths are relative to this directory; all
consumed files must be listed in repository-relative `SHA256SUMS`. The example
manifest is a template, not a record of completed runs.

The explicit reference matrix is:

- F1: v18 parent, flow_24, `k0`, `half`, `k1`…`k6`. k0 is U01 smoke, half is
  U01 formal, k1…k6 are U2. There are not eight U01-only reference phases.
- F2: v18 parent, flow_32, k13…k16. k13/k14 are in f32a; k15/k16 are in f32b.
- F3: parent and `v18__camber_m19.7`, flow_32, k7…k10, using the FID identities.

After the user has collected and hashed the required runs, the one-shot CLI is:

```sh
.venv/bin/python scripts/force00_gate.py --evidence-root docs/evidence/force00_2026_11
```

The implementation compares original CSV bytes with the registered evidence,
validates backend/geometry/window/box identity, and recomputes endpoint-clipped
time-weighted means and C1–C5. It writes `gate.json` exclusively and refuses an
existing destination. This implementation task leaves that destination absent.

Three draft/provenance discrepancies are explicit:

- The current user request and C4 table specify a 15% band, whereas rev 0's
  final PASS sentence says 10%. The implementation uses 15% and reports both
  bands. The specification itself is unchanged.
- The f32a-only description omits k15/k16; the gate reads their actual f32b
  provenance without rewriting either frozen result.
- UNC-01 contains no `camber_m19.7` σ_d. C5 reports that absence and blocks
  adoption as `INCOMPLETE`/`NONE`; it does not borrow FID's σ or a pitch proxy.
  The user must resolve the intended estimator/source before adoption.

Missing runs are `INCOMPLETE`. Malformed, unlisted, unknown or hash-mismatched
inputs raise errors. C5's comparison is descriptive; its numerical outcome
does not replace C1–C4. Among complete passing readouts, CV is preferred,
otherwise nds, otherwise NONE.

Whether issue #293's reported 7–9% built-in/CV gap occurs on this project's
parent is unknown until F1–F3 GPU execution. GPU kernel execution and T4 byte
regression remain unverified here. Frozen studies keep their original readout.
