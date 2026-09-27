# WaterLily Enzyme reverse spike (diagnostic only)

This private Kaggle T4 kernel probes three separate failure boundaries: Enzyme
reverse compilation for a CUDA array, the WaterLily #285 Poisson VJP on a tiny
sphere-derived grid, and reverse differentiation through a two-step WaterLily
sphere primal. It is a scratch experiment. `DONE` means the diagnostic script
finished; it does not mean any reverse stage passed or is qualified.

Kaggle runs the submitted `runner.py` as `/kaggle/src/script.py` and does not
mount this folder's neighboring `julia/` directory. The runner therefore
downloads the repository archive at the pinned source commit recorded in the
code, extracts only this scratch project, and verifies exact
`Project.toml`/`Manifest.toml`/`reverse_spike.jl` SHA-256 values. It then copies
the verified project to a temporary writable directory under
`/kaggle/working`, checks the copied Project/Manifest hashes, and runs both
`Pkg.instantiate()` and the diagnostic script from that copy. The
`enzyme_reverse_spike/project_identity.json` output records source archive and
input/copy hashes, post-instantiation hashes, and the failure stage. The
CUDA.jl 6.2.1, Enzyme and PR #285 pins remain unchanged. This avoids both the
v2 missing-source-bundle failure and v1's attempt to write under the
read-only `/kaggle/src` mount.

The package manifest pins Julia 1.12.6 dependencies to Enzyme 0.13.205,
CUDA.jl 6.2.1, and WaterLily PR #285 at
`feed49f480b52047b4e9b8bfacdf3e4f8201106b` (WaterLily 1.6.1). CUDA.jl 6.2.1
is deliberate: on 2026-09-27, Julia Pkg could not resolve Enzyme 0.13.205 with
CUDA.jl 6.3.1 because their GPUCompiler compatibility ranges do not intersect.
This environment is not the project's WaterLily 1.8.0 / CUDA.jl 6.3.1 runtime.

Submit and collect a new private kernel version with Kaggle CLI 2.2.4:

```bash
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels push \
  -p infra/kaggle/kernel_enzyme_reverse_spike --accelerator NvidiaTeslaT4 --timeout 7200
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels status \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/<version>
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels logs \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/<version>
uvx --index https://pypi.org/simple --from kaggle==2.2.4 kaggle kernels output \
  ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/<version> -p work/kaggle_enzyme_reverse_spike_v<version>
```

Keep the Kaggle kernel log, output manifest and version-specific output
folder together, including `project_identity.json`. Verify its input and
pre-instantiation copy hashes match the Project/Manifest shipped with the
submitted source. Interpret each `*_STATUS` line independently. A missing
`DONE`, `ERROR.txt`, failed reverse stage, or runtime/package mismatch is
scratch evidence only and never opens a qualification gate.

## CPU diagnostics reproduced locally

The three scripts in `julia/cpu/` run with the same pinned Project/Manifest
and Julia 1.12.6 on a CPU host. The observed commands and outcomes are:

```bash
julia --project=infra/kaggle/kernel_enzyme_reverse_spike/julia infra/kaggle/kernel_enzyme_reverse_spike/julia/cpu/sphere_parameter_reverse_spike.jl
julia --project=infra/kaggle/kernel_enzyme_reverse_spike/julia infra/kaggle/kernel_enzyme_reverse_spike/julia/cpu/initial_state_reverse_spike.jl
julia --project=infra/kaggle/kernel_enzyme_reverse_spike/julia infra/kaggle/kernel_enzyme_reverse_spike/julia/cpu/poisson_adjoint_spike.jl
```

On Julia 1.12.6 / WaterLily PR #285 / Enzyme 0.13.205, the two-step sphere
primal drag was `8.45013686103991`. Differentiating through construction with
respect to sphere radius stopped in Enzyme's `Core.apply_type` handling with
`length(modifiedBetween) [aka 5] != length(TT.parameters) [aka 4]`. With the
sphere prebuilt and body remeasurement disabled, the initial-velocity
centered FD was `0.09989015934408484`, while whole-step reverse stopped at
`MixedDuplicated(::Flow, ::Flow)` inside `mom_step!`.

The isolated PR #285 Poisson VJP completed: primal objective `1082.13368557`,
centered FD `0.12250039845`, reverse directional derivative `0.13056436355`
(ratio `1.06582807`). This is a failure-to-match diagnostic, not a gradient
pass. WaterLily 1.8.0 also stopped at `MixedDuplicated(::Flow, ::Flow)` for the
whole-step reverse, and that package version exposed no
`WaterLilyEnzymeCoreExt` in the tested environment. Those results, and the
Kaggle T4 attempt, do not qualify reverse mode or authorize a design update.
