# SDF-01 trilinear-normal host diagnostic (2026-09-29)

Status: host-side regression added; GitHub issue #20 remains open. This result
does not explain or close the reported CPU/CUDA normal discrepancy.

## Measurement

`julia/CFDSDFWaterLily/test/test_sdf01_trilinear_normal.jl` evaluates one
interior point in a synthetic one-cell trilinear polynomial. Its node values,
query coordinates, and spacing are exactly representable in Float32. It records
the raw value, raw world gradient, gradient magnitude, returned unit normal,
and independent analytic references for both Float64 and Float32 host paths.
The body uses an identity solver-to-world map and `fastd²=Inf`, isolating the
trilinear interpolation and normalization path.

Command:

```text
julia --project=julia/CFDSDFWaterLily julia/CFDSDFWaterLily/test/test_sdf01_trilinear_normal.jl
```

Result: Float64 raw gradient `(3.060546875, -1.7734375, 4.921875)` and normal
`(0.5049494381, -0.2925935480, 0.8120437677)` match the analytic reference
exactly. Float32 gives raw gradient `(3.0605469, -1.7734375, 4.921875)` and
normal `(0.50494945, -0.29259354, 0.8120438)`; maximum component error is
`1.837e-8`. Both assertions pass. Evidence class: deterministic host-side
implementation regression, not a registered CUDA measurement.

Repository validation from the diagnostic worktree:

- Julia focused diagnostic: pass for Float64 and Float32.
- `python -m compileall src tests`: pass (exit 0), using the existing primary
  worktree's `.venv` interpreter because the fresh managed worktree has no
  copied `.venv`.
- `python -m pytest -q`: 1039 passed, 4 skipped, 37 failed. The failures are
  `FileNotFoundError` for ignored `work/` snapshots absent from this fresh
  worktree (for example `work/pq0_2_smoke/project_downforce_volume.yaml` and
  registered historical Stage S/V run artifacts); no project code was
  changed to mask those missing inputs.

## Limits and blocked scope

- The test covers one well-conditioned interior query. It does not test the
  CPU/GPU affine map, CUDA kernel execution, cell-face behavior, outside
  extension, near-zero gradients, or `fastd²` cutoff behavior.
- The W1g criteria and existing evidence are unchanged. The current W1g GPU
  result is still absent; the prior `~1.338` report has no retained probe
  identity or raw vectors in this checkout. The local `work/.../local_cpu*.summary.json`
  files are CPU-only precision-path comparisons and cannot diagnose CUDA.
- The matching W0b round-2 registration is pending only as uncommitted state in
  the primary worktree and was not copied here. Therefore no T4 run or CUDA
  conclusion is recorded on this branch. W1g G6/G9 and SDF gradient
  qualification remain unverified; issue #20 is not closed.

The next diagnostic must preserve per-probe world/solver coordinates, cell
indices, raw CPU and CUDA gradients, magnitudes, normalized vectors, values,
and any early-exit reason for the same deterministic query set.
