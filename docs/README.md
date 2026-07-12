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

## Compatibility policy

The code retains read-only migration and readers for historical v1 artifacts,
but v1 has no separate active specification or roadmap. New features, solver
writers, examples, and acceptance evidence must use v2 identifiers, hashes,
and scopes. If a supporting document conflicts with `phase_plan.md`, the
roadmap takes precedence and the conflicting text must be corrected.
