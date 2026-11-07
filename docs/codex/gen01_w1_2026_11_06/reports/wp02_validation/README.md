# FORCE-00 CPU validation records

`amendment3/` contains the current source-review-fix acceptance captures for
`gen01/Force00.jl`. `final/` preserves the preceding Amendment 2 captures and
must not be used as provenance for the amended source. `wp02_report.md` in the parent directory
records commands, outcomes, failure sets and the complete host commit list.
These are CPU software/numerical fixtures, not registered GPU evidence or
readout adoption. The production `docs/evidence/force00_2026_11/` directory
is deliberately absent; the gate does not search this reports directory.

## Historical records

The root-level CPU JSON/CSV files, `validation/`, `README.attempt1.md` and
`SHA256SUMS.attempt1` preserve attempt 1. `amendment1/` preserves attempt 2.
Their bytes have been moved verbatim; embedded old source/evidence paths,
failed pin checks, old publication boundaries and baseline environments are
historical context only. In particular, attempt 2's temporary Python setup
is not used by this continuation. `relocation.json` lists every old/new
path. The root `SHA256SUMS` covers files at their current repository paths;
the historical manifests describe their original paths and captures.

## Current interfaces and reproduction

Load the unchanged package module, then opt in once:

```julia
Base.include(CFDSDFWaterLily,
    joinpath(repo_root, "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
readouts = CFDSDFWaterLily.force_readouts(sim, box; body=candidate)
```

`cur`, `nds`, `cv` are body-force vectors: drag = +Fx, downforce = -Fz.
`box` is a tuple of inclusive pressure-cell ranges. It must enclose only
the candidate support, stay two cells inside domain boundaries, and keep
four sampled SDF cells from scene bodies including the ground. Every normal
boundary face must have stored `mu0 == 1` exactly. These are
sampled geometry checks, not a continuum clearance certificate.

Run from the repository root using fresh output destinations:

```sh
julia --project=julia/CFDSDFWaterLily -O0 scripts/force00_selftest.jl
julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl /tmp/force00-uniform-new-a.json
julia --project=julia/CFDSDFWaterLily -O1 scripts/force00_uniform_pressure.jl /tmp/force00-uniform-new-b.json
cmp /tmp/force00-uniform-new-a.json /tmp/force00-uniform-new-b.json
julia --project=julia/CFDSDFWaterLily scripts/force00_job_regression.jl /tmp/force00-cpu-job-new
.venv/bin/python -m pytest -q tests/test_force00_gate.py tests/test_force00_uniform_inputs.py -p no:cacheprovider
.venv/bin/python -m pytest -q tests/test_force00_boxes.py -p no:cacheprovider
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest --ignore=tests/test_lbm_metal.py -q -rf -p no:cacheprovider
```

The existing Python environment and pinned Julia project/manifest are used
unchanged. Julia timing receipts include process startup and JIT. No GPU
solver is invoked. Current raw logs/JUnit are retained losslessly as gzip,
with both raw and compressed hashes in the corresponding `log_archive.json`.

U1 has 40 placements on each of flow24/flow32: 32 SHA-verified FID shifts
and eight additional z-only shifts from the existing Halton generator.
U2 has eight off-grid placements at each sphere radius 8/16/32 cells,
using the W2a analytic sphere. Uniform cur/nds vectors are pressure reaction
integrals; CV uses the body-force convention; the exact answer is zero.
The upstream issue #369 numbers are a descriptive table from different
placements, not an exact replay target. The job regression checks actual
production measurement definitions on the same flow16 input and short CPU
window, original 13 CSV columns and appended cur tokens, plus final arrays.

## Later user GPU runs and one-shot gate

The copied job takes the original raw-input/output arguments and reads
`docs/harness/force00_boxes.json`. Its 13 existing columns, cadence8,
[80,120] time-weighted window and phase semantics are preserved. The exact
delta is `scripts/waterlily_force00_job.diff`. An optional dispatcher uses
`FORCE00_CASE=flow_24|flow_32` to select the inventory only. The registered
largest enclosing boxes are `4:149,4:71,6:53` on flow24 and
`4:199,4:95,6:71` on flow32. `scripts/force00_boxes.py` computed them once from
phase-zero Float32 parent moments and refuses an existing registry. Actual
geometry preflight must pass for each state/phase. An environment box override
requires both `FORCE00_CPU_TEST=1` and an actual CPU Array; it is test-only.
The summary records the Force00/job/dispatcher SHAs, which must match U1.
Variant wall time and peak VRAM include readout overhead and are explicitly
incomparable with the registered jobs.

After separate source review/registration and the user's F1-F3 GPU runs,
create the production evidence directory. Copy the manifest template
`force00_runs.example.json` as `force00_runs.json`, retain the required
identities/phases and hash every consumed artifact in repository-relative
SHA256SUMS. Produce a fresh source-bound uniform-pressure JSON there or copy
`amendment3/uniform_pressure.json` without changing bytes and list its hash.
Then run the write-once gate:

```sh
.venv/bin/python scripts/force00_gate.py --evidence-root docs/evidence/force00_2026_11
```

F1 references UNC U01 smoke k0/formal half plus U2 k1..k6. F2 uses SCREEN
f32a k13/14 and f32b k15/16. F3 uses the FID camber_m19.7 pair at k7..k10.
C4 uses 15% for adoption and reports 10% diagnostically. The exact UNC camber
sigma_d is absent, so C5 remains descriptive INCOMPLETE without blocking
adoption. C1 also byte-regresses all eight F3 parent/candidate CSVs. Missing
C1-C4 inputs cause a nonzero exit without writing `gate.json`; the one-shot
write is reserved for a complete decision. GPU kernel
execution, T4 C1 bytes, phase dependence, parent differences and readout
adoption remain unverified. Whether #293's 7-9% built-in/CV gap occurs on
this project's parent is unknown until GPU F1-F3. Frozen study conclusions
and all qualification flags are unchanged.
