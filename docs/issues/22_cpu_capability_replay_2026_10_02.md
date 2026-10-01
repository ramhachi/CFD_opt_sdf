# GRAD-02 (#22): CPU capability replay, 2026-10-02

Evidence class: local experimental CPU reverse capability diagnostic.

The pinned two-step `sim_step!` reverse attempt fails before returning a
gradient. It reproduces `MethodError: MixedDuplicated(::Flow, ::Flow)` while
Enzyme builds the augmented-forward activity wrapper for `mom_step!`. This
is the same bounded blocker recorded on 2026-09-29, not a statement about
every CPU backend or all upstream PR fixtures. No gradient correctness
verdict is evaluated in this replay.

## Command and identity

```text
julia --startup-file=no --project=infra/kaggle/kernel_enzyme_reverse_spike/julia infra/kaggle/kernel_enzyme_reverse_spike/julia/cpu/initial_state_reverse_spike.jl
```

Exit status: **2**. Runtime: Julia 1.12.6, WaterLily 1.6.1 at the pinned
PR #285 head `feed49f480b52047b4e9b8bfacdf3e4f8201106b`, Enzyme 0.13.205,
macOS arm64, Float64 CPU `Array`, two steps on the existing tiny prebuilt
sphere fixture. The experimental Project/Manifest and script remain unchanged;
production W3/W4/FD dependencies are untouched. The script's primal/FD numbers
are solver-unit diagnostic fingerprints, not physical-force or gradient
qualification results.

Append-only evidence is preserved in
[`grad02_cpu_replay_2026_10_02`](../evidence/grad02_cpu_replay_2026_10_02/).
`result.json` SHA-256:
`1d4a44949d54715a21ce94cbd6fb274f5546b0e3ee41ec299ef1e04aa82d82e2`.
`full_step.log` SHA-256:
`395b0f3f18308756af8ac18f47b147625d05bb86941dc22624d3975c4bf85778`.
The result binds all three unchanged source-input hashes and the replay's
source commit `2fd7f6abc5d21d74cadf7e207f75785c582bc7cb`.

## Verification

`.venv/bin/python -m compileall src tests` passed.
The first `.venv/bin/python -m pytest -q --tb=short` invocation reported
`38 failed, 1224 passed, 5 skipped`: its sole additional failure lacked the
ignored canonical-v17 NPZ/raw fixture. After copying those exact read-only
inputs into this worktree, the focused prerequisite test passed and the full
suite reported `37 failed, 1225 passed, 5 skipped` in 261.07 s. All 37 failure
IDs match the measured integration baseline; no new source failure remains.
The differing skip/pass counts reflect ignored optional fixtures.
Both raw logs are preserved losslessly, with SHA-256 values and the ID-set
comparison in `validation.json`. `git diff --check` passed.

The existing full-step capability blocker remains open. Isolated Poisson VJP
execution from the prior record cannot substitute for full-step reverse.
This result neither starts #48 nor promotes any production gradient backend.
All six qualification and shape-update flags remain false.
