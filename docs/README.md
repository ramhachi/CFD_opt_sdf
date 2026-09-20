# Documentation map

Use this page as the documentation entry point. There is one active roadmap
and one active schema version for new implementation work.

## Fresh OpenCode Read Order

Start here in a new terminal, after reading the repository root
[`AGENTS.md`](../AGENTS.md):

1. [`opencode_handoff_2026_09.md`](opencode_handoff_2026_09.md) - detailed
   repository-local working memory, current evidence boundaries, next slice,
   commands, and reporting template.
2. [`phase_plan.md`](phase_plan.md) - the sole roadmap, status, and execution
   order.
3. [`problem_register_2026_09.md`](problem_register_2026_09.md) - the issue
   ledger, including P1-P17 and the measured contradictions.
4. [`problem_resolution_plan_2026_09.md`](problem_resolution_plan_2026_09.md) -
   detailed implementation and test slices, subordinate to the latest roadmap.
5. [`problem_contract_v2.md`](problem_contract_v2.md) and
   [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) - active
   schemas and artifact semantics.
6. [`git_branching_strategy.md`](git_branching_strategy.md) - branch workflow.

## Authoritative documents

1. [`phase_plan.md`](phase_plan.md) — the only roadmap, status, and execution
   order.
2. [`problem_register_2026_09.md`](problem_register_2026_09.md) — the
   authoritative issue ledger, not a second roadmap.
3. [`problem_contract_v2.md`](problem_contract_v2.md) — user-facing generic
   problem schema.
4. [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) — Stage T
   primal/sensitivity artifact schema.
5. [`fixed_grid_backend_decision.md`](fixed_grid_backend_decision.md) — why the
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
- [`opencode_handoff_2026_09.md`](opencode_handoff_2026_09.md)
  — the fresh-session OpenCode handoff. It summarizes current architecture and
  evidence without replacing the roadmap or issue ledger.
- [`stage_t_optimizer_diagnosis_2026_09.md`](stage_t_optimizer_diagnosis_2026_09.md)
  — why the native ISQP path could not move the design, read against the
  OpenFOAM sources, and the decision to own the optimization in Python.
- [`fsae_readiness_execution_plan.md`](fsae_readiness_execution_plan.md)
  — implementation packages, evidence gates, replacement policy, and the
  entry conditions for the later FSAE full-vehicle problem.
- [`glm_downforce_assessment_2026_09.md`](glm_downforce_assessment_2026_09.md)
  — the GLM-session downforce-focused investigation and plan (WP4–WP6 results,
  literature refinement, and the recommended WP7/B-ladder route), subordinate
  to the roadmap and the evidence records.
- [`downforce_architecture_research_2026_09.md`](downforce_architecture_research_2026_09.md)
  — advisory research note (external literature and proposals only) on why the
  Stage T downforce ranking failed on the thickness axis and which architecture
  tracks could address it. Subordinate to `phase_plan.md`; it adds no repository
  evidence and changes no gate.

## Compatibility policy

The handoff is working memory only. `phase_plan.md` remains the sole roadmap,
status, and execution-order authority, and `problem_register_2026_09.md`
remains the issue ledger.
The handoff's commit table and validation snapshot are historical context;
fresh sessions must trust live `git status`/`git log` and current artifacts over
those values.

The code retains read-only migration and readers for historical v1 artifacts,
but v1 has no separate active specification or roadmap. New features, solver
writers, examples, and acceptance evidence must use v2 identifiers, hashes,
and scopes. If a supporting document conflicts with `phase_plan.md`, the
roadmap takes precedence and the conflicting text must be corrected.
