# Documentation map

Use this page as the documentation entry point. There is one active roadmap
and one active schema version for new implementation work.

## Authoritative documents

1. [`phase_plan.md`](phase_plan.md) — the only roadmap, status, and execution
   order.
2. [`problem_contract_v2.md`](problem_contract_v2.md) — user-facing generic
   problem schema.
3. [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) — Stage T
   primal/sensitivity artifact schema.
4. [`fixed_grid_backend_decision.md`](fixed_grid_backend_decision.md) — why the
   first Stage T adapter uses OpenFOAM.

## Supporting documents

- [`git_branching_strategy.md`](git_branching_strategy.md) — Git and pull
  request workflow.

- [`cross_platform_research.md`](cross_platform_research.md) — setup, bounded
  research commands, measured evidence and remaining platform work.
- [`development_plan_2026_09.md`](development_plan_2026_09.md) — accepted design
  and acceptance criteria; progress is maintained in `phase_plan.md`.
- [`architecture_review_2026_09.md`](architecture_review_2026_09.md) — critical
  review motivating the cross-platform design.
- [`architecture_effectiveness_2026_09.md`](architecture_effectiveness_2026_09.md)
  — measured Stage T update/re-evaluation evidence and the remaining
  Stage T-to-S-to-V breakpoints.
- [`p0_openfoam_closed_loop_2026_09.md`](p0_openfoam_closed_loop_2026_09.md)
  — the first end-to-end canonical state/gradient loop on real OpenFOAM, its
  finite-difference verification, and the measurement showing that Stage T had
  never produced a design.
- [`fsae_readiness_execution_plan.md`](fsae_readiness_execution_plan.md)
  — implementation packages, evidence gates, replacement policy, and the
  entry conditions for the later FSAE full-vehicle problem.

## Compatibility policy

The code retains read-only migration and readers for historical v1 artifacts,
but v1 has no separate active specification or roadmap. New features, solver
writers, examples, and acceptance evidence must use v2 identifiers, hashes,
and scopes. If a supporting document conflicts with `phase_plan.md`, the
roadmap takes precedence and the conflicting text must be corrected.
