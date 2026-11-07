# FORCE-00 Amendment 1 CPU implementation evidence

This directory records the continuation from `21d1e8e7`, using the placement
selected in Amendment 1. Evidence class: CPU software/numerical fixtures and
source-path regression. It is not a registered GPU measurement, an adoption
decision, grid convergence or target-physics qualification. The preceding
attempt's files in the parent directory remain their historical records.

The implementation lives in new `julia/CFDSDFWaterLily/src/Force00.jl`.
Both `Forces.jl` and `CFDSDFWaterLily.jl` are whole-file SHA-pinned by existing
studies, so the new entrypoints opt in explicitly:

```julia
include("julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl")
Base.include(CFDSDFWaterLily, "julia/CFDSDFWaterLily/src/Force00.jl")
readouts = CFDSDFWaterLily.force_readouts(sim, box)
```

Use paths resolved from the caller's repository location in production.
`readouts.cur`, `.nds`, and `.cv` use the registered body-force convention;
drag is +Fx and downforce is -Fz. `box` is a tuple of inclusive pressure-cell
index ranges. Candidate-plus-ground scenes must pass `body=candidate` and
enclose only that candidate. `validate_force_box` checks candidate support,
two-cell domain inset and four-cell sampled scene-face clearance. These are
sampled SDF checks, not a continuum distance certificate for nonmetric SDFs.

## CPU reproduction

From the repository root, use fresh destinations; the output commands refuse
existing outputs. No command here launches a GPU.

```sh
julia --project=julia/CFDSDFWaterLily -O0 scripts/force00_selftest.jl
julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl /tmp/force00-uniform-a.json
julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl /tmp/force00-uniform-b.json
cmp /tmp/force00-uniform-a.json /tmp/force00-uniform-b.json
julia --project=julia/CFDSDFWaterLily scripts/force00_job_regression.jl /tmp/force00-cpu-job-new
.venv/bin/python -m pytest -q tests/test_force00_gate.py tests/test_force00_uniform_inputs.py
```

`uniform_pressure.json` contains 80 parent placements (40 on each grid) and
24 off-grid sphere placements. The 32 FID vectors are read from their
SHA-verified registration; eight extra z-only phases use the next four mirror
pairs from the existing generator. U2 uses those eight generator vectors in
all three coordinates. The JSON reports force vectors, max/RMS, projected
areas, upstream reference residuals and geometry/source hashes, without a
timestamp or destination-dependent content. The second run's byte comparison
and timings are recorded in `validation/uniform_determinism.json`.

`cpu_job_regression/` executes the actual registered and new measurement
definitions on the same parent, flow_16 lattice and short CPU window. The
receipt discloses the test-only backend/telemetry, cadence and endpoint
substitutions. Its checks compare the original CSV prefix, appended cur
tokens and final flow arrays. This is not the F1/F2 T4 regression.

`validation/` retains source-pin checks, source review, CPU logs and the
completed base/feature full-suite comparison. The base is a real detached
worktree at `e3dcdf61`, not the interrupted first-attempt run. Raw pytest logs
and JUnit results are compressed without modifying their content.

## Later GPU runs and one-shot gate

The job interface and reference matrix remain documented in
`../README.md`; use `scripts/waterlily_force00_job.diff` for the exact copy
delta. The required environment variable is
`FORCE00_CV_BOX='lo:hi,lo:hi,lo:hi'`. The optional dispatcher additionally
requires `FORCE00_CASE=flow_24|flow_32`. Preserve each registered campaign's
geometry, phase, runtime and window settings when preparing F1-F3.

Put the later `force00_runs.json` and run artifacts in this evidence root,
using the schema of `../force00_runs.example.json`. Update this directory's
repository-relative `SHA256SUMS` to include those new inputs before invoking
the gate. The gate validates every consumed artifact and its registered
reference hashes, full eight-step sample sequence, endpoint and summary
identity, then recomputes the registered endpoint-clipped window means.

```sh
.venv/bin/python scripts/force00_gate.py --evidence-root docs/evidence/force00_2026_11/amendment1
```

`gate.json` is write-once. This CPU implementation task deliberately leaves it
absent because F1-F3 have not run. Missing runs are INCOMPLETE. C4 uses the
user-confirmed 15% adoption band and reports the 10% diagnostic. UNC-01 has
no exact `camber_m19.7` sigma_d row, so C5 remains INCOMPLETE until an
authoritative matching source is provided; no FID or pitch proxy is used.
Among complete passing readouts, the adoption order is R_cv, R_nds, NONE.

Whether issue #293's reported 7-9% built-in/control-volume difference occurs
on this project's parent is unknown until the user's F1-F3 GPU execution.
GPU kernel compilation, T4 byte regression, parent phase SD and actual paired
differences are unverified here. Frozen campaign verdicts and qualification
flags remain unchanged.
