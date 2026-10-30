# Upstream code reference map

Date: 2026-09-26

This file identifies upstream implementation fragments worth reading before writing new code.
It is a **reference map**, not an instruction to vendor whole repositories.

## Rule

Prefer:
1. exact upstream commit + exact file path;
2. reimplement the required local adapter behind this repository's contracts;
3. add a regression test based on the upstream behavior.

Do not paste GPL example code into `CFD_opt_sdf` unless the repository's licensing decision explicitly permits it.

---

# A. WaterLily core — highest priority

Repository:
`WaterLily-jl/WaterLily.jl`

Pinned reference commit observed during planning:
`aac3c432374fad1f762ad043d1bee2138b612399`

Core package license:
MIT/Expat.

## A1. `src/AutoBody.jl`

Why read it:
- defines `AutoBody(sdf, map)`;
- shows the exact SDF callback interface;
- shows how WaterLily obtains normals from the SDF gradient;
- shows the geometry-map/body-velocity contract.

How it maps locally:

```text
SDFDesignState.phi
    ↓
GridSDFBody interpolation
    ↓
WaterLily-compatible sdf(x,t)
```

Do not create an ever-growing Boolean body expression tree for optimization.
Implement a grid-backed interpolated SDF body.

Local target:
`julia/CFDSDFWaterLily/src/GridSDFBody.jl`

## A2. `src/Body.jl`

Why read it:
- `AbstractBody` interface;
- `measure!`;
- narrow-band/fast-distance behavior;
- `mu0`, `mu1`, normal and body-velocity coupling;
- lazy set operations.

Use it to ensure the grid-SDF adapter satisfies the same geometry contract.

Particularly important:
WaterLily already uses narrow-band body measurement. Do not duplicate a second incompatible narrow-band interpretation on the Python side.

## A3. `src/Metrics.jl`

Why read it:
- `pressure_force`;
- `viscous_force`;
- `total_force`;
- moment definitions;
- mean-flow machinery.

Local rule:
Use WaterLily's `total_force` as the primitive aerodynamic force unless a preregistered diagnostic explicitly decomposes pressure/viscous terms.

Do not implement a second force integral in Python and call it equivalent without qualification.

Local target:
`julia/CFDSDFWaterLily/src/Forces.jl`

## A4. `test/test_forwarddiff.jl`

Why read it:
- current upstream regression patterns for ForwardDiff;
- CPU/GPU parameter derivatives;
- force-based derivative example;
- end-to-end `sim_step!` differentiation patterns.

This is the best seed for the first local **parameter-gradient qualification fixture**.

Local tests should reproduce the idea, not blindly copy tolerances.

Local target:
`tests/test_waterlily_contract.py`
plus Julia-side tests under
`julia/CFDSDFWaterLily/test/`.

## A5. `ext/WaterLilyCUDAExt.jl`

Why read it:
- shows that CUDA support is intentionally a backend extension;
- useful for runtime fingerprint and backend checks.

Do not build local code that assumes `CuArray` exists or that CUDA is always available.

---

# B. WaterLily reverse AD — experimental, separate environment

Pull request:
`WaterLily-jl/WaterLily.jl#285`
`Reverse AD via Enzyme extension`

Pinned experimental head observed:
`feed49f480b52047b4e9b8bfacdf3e4f8201106b`

Do not merge/vendor this branch into the production primal environment.

## B1. `ext/WaterLilyEnzymeCoreExt.jl`

Highest-value adjoint reference.

Why read it:
- custom reverse rule for the multigrid Poisson solve;
- implicit-function-theorem/discrete-adjoint structure;
- explicitly demonstrates that the iterative linear solve should not simply be taped through.

This is directly relevant if a custom WaterLily discrete adjoint is eventually required.

## B2. PR modifications to `src/MultiLevelPoisson.jl`

Why read:
- introduces a stable no-kwargs `poisson_solve!` extension point;
- illustrates a good architectural pattern for AD/custom adjoint boundaries.

Local lesson:
when wrapping upstream solver functions for AD, create explicit stable differentiation boundaries rather than differentiating generic dispatch/kwargs machinery.

## B3. PR modifications to `src/Flow.jl`

Why read:
- demonstrates which portions of the time step had to be made AD-compatible;
- shows that seemingly harmless logging/dynamic-dispatch paths can break Enzyme.

Local lesson:
keep logging, host I/O, checkpoint serialization, and runtime probing outside the differentiated region.

## B4. PR modifications to `src/util.jl`

Why read:
- KernelAbstractions kernel-generation changes required for Enzyme tracing;
- relevant to why a GPU reverse path cannot be assumed to work merely because the primal uses CUDA.

## Mandatory experiment derived from PR #285

Reproduce the reported solver-tolerance sensitivity with a local manifest:

```text
Poisson tol:
1e-4
1e-6
1e-8
1e-10
```

Compare reverse derivative with:
- ForwardDiff for a low-dimensional parameter;
- centered FD.

No production promotion before this passes the repository's preregistered gradient gate.

---

# C. WaterLily Examples — use as behavioral references, not copy-paste sources

Repository:
`WaterLily-jl/WaterLily-Examples`

Pinned reference commit:
`58792dd17cfe585f7f4eea8be925de1b4ffefa25`

License:
GPL-3.0.

Because this repository is GPL-3.0, **do not paste substantial example code into `CFD_opt_sdf` unless a deliberate license decision has been made.**
Use the examples as implementation references and independently implement the required behavior.

## C1. `examples/TwoD_TandemFoilOptim.jl`

Read for:
- end-to-end differentiable parameterized geometry;
- warm-in period;
- finite measurement period;
- force/drag objective;
- optimization over a flow simulation.

This is the conceptual template for:
`parameterized SDF -> primal -> derivative -> FD check`.

Do not reuse its custom optimizer as the production optimizer.

## C2. `examples/ThreeD_SphereLESBiotSavart.jl`

Read for:
- CUDA `CuArray` execution;
- Float32 3D simulation;
- time-averaged force;
- mean-flow accumulation;
- restart/checkpoint behavior;
- long GPU campaign organization.

This is especially useful for the Colab/RTX worker design.

Local behaviors to reimplement:
- explicit warm-up interval;
- separate statistics window;
- durable checkpoint;
- force-history persistence.

## C3. `examples/TwoD_LidCavity.jl`

Read for:
- injecting custom tangential velocity boundary behavior around WaterLily's step/projection sequence.

This is relevant to the moving-ground implementation pattern.

Important:
a lid-driven cavity is **not** a qualified moving-ground external-aero boundary.
Use the injection pattern only; implement and independently test the actual external moving-ground BC.

## C4. `examples/TwoD_Channel.jl`

Read for:
- custom wall BC injection;
- no-slip ghost treatment;
- periodic streamwise setup.

Again, use only as a pattern for BC customization.

---

# D. What should be copied into this repository?

Prefer **none of the upstream implementation files** at first.

Instead add:

```text
docs/references/upstream_code_map.md
docs/references/waterlily_reverse_ad_285.md
```

containing:
- repository;
- commit;
- file path;
- upstream license;
- local purpose;
- test that proves the local implementation behaves as required.

If a WaterLily core helper is later copied or modified, preserve the MIT copyright/license notice as required.

For GPL example material, avoid code copying unless the project deliberately adopts GPL-compatible licensing.

---

# E. Exact local implementation mapping

| Upstream reference | Local implementation |
|---|---|
| `WaterLily/src/AutoBody.jl` | `julia/CFDSDFWaterLily/src/GridSDFBody.jl` |
| `WaterLily/src/Body.jl` | SDF body contract tests / narrow-band adapter |
| `WaterLily/src/Metrics.jl` | `julia/CFDSDFWaterLily/src/Forces.jl` |
| `WaterLily/test/test_forwarddiff.jl` | parameter-gradient qualification fixture |
| PR #285 Enzyme extension | experimental reverse backend only |
| `TwoD_TandemFoilOptim.jl` | low-dimensional AD/FD PoC design |
| `ThreeD_SphereLESBiotSavart.jl` | Colab/RTX GPU runner + checkpoint design |
| `TwoD_LidCavity.jl` / `TwoD_Channel.jl` | moving-ground/custom BC design reference |

---

# F. References not worth importing yet

Do not collect large TCLB/OpenLB/DAFoam code snapshots before WaterLily Gate 0–2.

For those backends, initially record only:
- exact repo/version;
- the smallest adjoint/topology example;
- build/runtime requirements;
- license.

Only materialize/code-read them after WaterLily's production-gradient Go/No-Go decision.
Otherwise the repository will accumulate multiple half-integrated solver stacks and repeat the architecture-drift problem.

---

# G. Immediate recommendation

Before coding PR-03, the implementer should read, in this order:

1. WaterLily `src/AutoBody.jl`
2. WaterLily `src/Body.jl`
3. WaterLily `src/Metrics.jl`
4. WaterLily `test/test_forwarddiff.jl`
5. WaterLily PR #285, especially `WaterLilyEnzymeCoreExt.jl`
6. WaterLily Examples `TwoD_TandemFoilOptim.jl`
7. WaterLily Examples `ThreeD_SphereLESBiotSavart.jl`
8. Lid/channel examples only when implementing moving-ground BC

This set is small enough to understand fully and covers nearly every architectural seam needed for the first WaterLily integration.

---

# H. Web audit verification — 2026-09-26

Live fetch audit (GitHub REST API, raw.githubusercontent.com, arxiv.org, Enzyme.jl
issue search) executed 2026-09-26. Evidence class: third-party repository facts.

| Item | Result | Evidence |
| --- | --- | --- |
| Core pin `aac3c43…` | Verified; it is the current `master` HEAD (merged 2026-09-21, unchanged since) | `commits/master` fetch |
| Core license | `LICENSE.md` (root) is the MIT "Expat" text, Copyright (c) 2020 Gabriel Weymouth. GitHub REST shows `spdx_id: NOASSERTION` only because `LICENSE.md` is not auto-detected | raw `LICENSE.md` fetch |
| PR #285 | `open`, never merged; head `feed49f480b52047b4e9b8bfacdf3e4f8201106b` matches exactly; 4 commits `91d716e / f3f6411 / f1c64f1 / feed49f`; last updated 2026-09-20; 7 files, +121/−23 | `pulls/285` fetch |
| PR #285 mergeability | `mergeable_state: dirty` — master moved after the PR head (PR #327 merged into `aac3c43`), so an upstream re-merge needs a rebase | `pulls/285` fetch |
| PR #285 numbers | PR body confirms: reverse agree with ForwardDiff 9.99% rel error at default Poisson tol `1e-4`; `1e-10` → `2.4e-5` (~5 significant figures). Reverse works through the full `sim_step!` on KA-CPU and SIMD-CPU via `WaterLilyEnzymeCoreExt` rules on `WaterLily.poisson_solve!` (implicit-function-theorem discrete adjoint of the multigrid solve) | `pulls/285` body |
| PR #285 scope | The PR **mutates core `src/util.jl`, `src/Flow.jl`, `src/MultiLevelPoisson.jl`** (module-scope `@loop @kernel` lift, `grab!` call-head capture, `poisson_solve!` wrapper, permanent removal of `@log` from `mom_step!` because of the Enzyme `restoreCache` LLVM assert) | `pulls/285` body |
| Examples license | GPL-3.0 reconfirmed | `repos/WaterLily-Examples` fetch |
| Examples pin `58792dd…` | Exists (2026-06-26, merge of PR #36 "cds+quick blend" for LES sphere streaks) | `commits/58792dd` fetch |
| Examples C1–C4 files | All four exist at the pin. `TwoD_TandemFoilOptim.jl` content verified: segment SDF + motion `map` in `AutoBody(sdf,map)`, warm-in window, then impulse integration as a time-averaged mean drag, custom Davidon minimizer (ForwardDiff-based) | raw file + `examples/` tree at pin |
| A-map source files | `src/AutoBody.jl`, `src/Body.jl`, `src/Metrics.jl`, `src/MultiLevelPoisson.jl`, `test/test_forwarddiff.jl`, `ext/WaterLilyCUDAExt.jl` all exist at `aac3c43` | tree fetches at `aac3c43` |
| WaterLily paper | arXiv 2407.16032 v3 (2025-07-21); journal-ref: *Computer Physics Communications* **315**, 109748 (2025), DOI 10.1016/j.cpc.2025.109748 | arxiv.org fetch |
| DAFoam | Re-verified: `mdolab/dafoam` v5.0.0 (2026-05-05), GPL; OpenFOAM v2506 + OpenFOAM-AD; MPhys/OpenMDAO interface; forward-mode AD flagged unreliable upstream ("use check_totals") | GitHub releases search |
| TCLB | GPL-3.0, MPI+CUDA LBM, `adjoint` topic, active (pushed 2026-03) | `repos/CFD-GO/TCLB` fetch |
| OpenLB / waLBerla / lbmpy | **Not re-verified in this audit**; license/commit checks remain due only at the PR-09 decision point | — |

# I. Audit-derived plan addenda (post-registration changes to `00_HANDOFF_MASTER.md`)

`00_HANDOFF_MASTER.md` is hash-frozen by `sdf_native_architecture_registration_2026_09.json`;
these items are the authorized additions and are recorded additively here and in
[`../current_state_and_next_plan_2026_09_26.md`](../current_state_and_next_plan_2026_09_26.md).

1. **Pressure-shift-invariance contract (hard rule).** The reverse/adjoint cost must be
   invariant to an added constant on `p`: `sum(p)` has an analytically zero reverse gradient
   (Neumann pressure nullspace; the non-zero value ForwardDiff returns is a numerical artifact).
   PR-04 (force contract) and PR-07 experiments must use force/moment integrals (as
   `TwoD_TandemFoilOptim.jl` does with its impulse/mean-drag integral), never raw pressure sums.
2. **Metal backend status.** Upstream PR #327 (merged into `aac3c43`) added Apple Metal support:
   `mem=MtlArray`, **Float32 only** (no Float64 kernels on Metal), and force/moment sums
   accumulate via `WaterLily.sumtype` (at least Float64, falling back to the field type on
   backends without Float64). Optional, non-blocking: a Metal Float32 smoke spike on the
   MacBook Air can be appended to PR-03's execution matrix. The standing rule "Metal is not a
   blocking production requirement" is unchanged.
3. **PR #285 staleness handling.** The PR head is stale against `master` (`aac3c43`):
   (a) PR-07 replays the pinned head `feed49f…` in a separate pinned Manifest — no rebase needed;
   (b) anything integrating PR #285 into a newer master requires a rebase and must expect
   conflicts in core `src/` because the PR mutates `util.jl`, `Flow.jl`, `MultiLevelPoisson.jl`.
4. **Upstream extension ledger.** Verified at `aac3c43`: `WaterLilyJLD2Ext` (durable
   checkpoints), `WaterLilyMeshingExt` (surface extraction → STL handoff for OpenFOAM Stage V),
   `WaterLilyReadVTKExt`/`WaterLilyWriteVTKExt` (restart/continuation), `WaterLilyPathlinesExt`,
   plus `TwoD_MeanCircleJLD2.jl` and `ThreeD_CylinderVTKRestart.jl` examples. Prefer these
   upstream extensions, behind contracts-with-verification, over reimplementing
   checkpoint/mesh-export machinery locally.
5. **Enzyme watch items.** Enzyme #3195 (gc-transition bundle abort on `cuPointerGetAttribute`,
   affects CuArray-mode AD) and Enzyme PR #3148 (GPU linalg rules via a GPUArrays extension) are
   the concrete upstream gates for the PR-08 bounded CUDA spike. General Enzyme reverse on plain
   CUDA kernels is reported working in the 0.13.x era, so the WaterLily-specific blocker remains
   the missing `cuMemcpyHtoDAsync_v2` rule (registered status unchanged).
6. **DAFoam re-verification.** DAFoam v5.0.0 (GPL, OpenFOAM v2506 + OpenFOAM-AD) is a fresh,
   viable body-fitted gradient-reference alternative for the PR-09 decision if the WaterLily GPU
   reverse is rejected. GPL licensing applies the same caution as TCLB.
7. **Citation update.** The WaterLily paper is now also citable as the peer-reviewed version:
   CPC 315, 109748 (2025), DOI 10.1016/j.cpc.2025.109748.
8. **Local precondition.** Julia is not installed on this development machine (`which julia`
   fails). Julia installation plus a pinned Manifest is an explicit precondition of PR-02.
9. **License clarification.** No claim in this map was falsified. The GitHub "Other/NOASSERTION"
   license badge on WaterLily.jl is an auto-detection artifact of the `LICENSE.md` file name;
   the text is MIT/Expat.
