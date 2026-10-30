# First implementation task for Codex/OpenCode

Repository:
`https://github.com/ramhachi/CFD_opt_sdf.git`

Base branch:
`feat/p0-openfoam-closed-loop`

Expected base HEAD:
`ebdd01f293636b2fc736885a1032d466e6632e9a`

Create a new implementation branch from exactly this state.

## Objective

Create the architecture fork to an SDF-native optimizer **without changing current solver behavior or running new CFD campaigns**.

The current K=16 B-spline reduced-basis Stage S path must remain reproducible but be marked as a superseded diagnostic/reference path. Do not delete it. Do not launch S2.

## Required changes

1. Add a canonical immutable SDF design-state contract under:
   `src/cfd_sdf/design/sdf_state.py`

2. Keep existing `DensityDesignState` intact for Stage T history/reproduction.

3. Add solver-neutral interfaces:
   - `src/cfd_sdf/oracles/base.py`
   - `src/cfd_sdf/gradients/base.py`

4. Add runtime identity:
   - `src/cfd_sdf/runtime/fingerprint.py`
   - hash runtime/compiler/solver/precision/grid identifiers deterministically.

5. Extend the canonical optimization semantics so the future SDF path can represent:
   - objective `f = -CDF`;
   - efficiency constraint `g_eff = R_min * CD - CDF <= 0`;
   - volume constraint;
   without changing existing historical manifests.

6. Add explicit architecture status to documentation:
   - K=16 Stage S v2 S0R/S1R is preserved;
   - S2 is intentionally not started;
   - legacy B-spline/continuous-adjoint route is not the production target;
   - OpenFOAM Stage V remains independent verifier;
   - WaterLily is only a candidate primal backend at this commit.

7. Add tests for:
   - SDF state construction/serialization/hash;
   - sign convention `phi < 0 = solid`;
   - mask shape/identity validation;
   - efficiency-constraint sign semantics;
   - runtime fingerprint stability;
   - incompatible resume/backend identity rejection if applicable.

## Invariants

Do not modify or regenerate existing evidence files.

Do not change:
- P21 physical-profile evidence;
- v2/v3 domain-convergence results;
- Stage S S0R/S1R evidence;
- current OpenFOAM solver controls.

Keep:
- `shape_update_allowed = false`;
- `sdf_gradient_qualified = false`;
- `waterlily_reverse_cpu_qualified = false`;
- `waterlily_reverse_cuda_qualified = false`;
- `topology_birth_qualified = false`.

## Stop conditions

Stop and report rather than adapting architecture silently if:
- the expected base HEAD differs;
- implementing the SDF state requires rewriting historical evidence;
- a new contract conflicts with ProblemSpec/compiler semantics;
- existing tests fail for reasons not caused by the intended architecture fork.

## Required validation

Run:
- full existing pytest suite;
- new unit tests;
- compile/static checks already used by the repository;
- `git diff --check`.

Produce an append-only architecture registration/evidence record and summarize exact files changed.

Suggested commit message:

`Architect SDF-native optimization core and freeze legacy Stage S`
