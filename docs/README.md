# Documentation map

The current production research direction is SDF-native: the canonical design
state is a bounded Cartesian signed-distance field `phi`. Read
[`phase_plan.md`](phase_plan.md) for the only roadmap, status, and execution
order. Earlier density/Brinkman Stage T and B-spline Stage S plans remain
available as historical capability and evidence context; they do not define
the current production path.

Current checkpoint: W3 round 4 exact T4 kernel version 5 passed host
verification for its registered finite-box primal contract. W3 v4's all-zero
root cause remains unresolved; physical-profile, grid-response and downstream
qualification remain false. W4 immutable criteria round 1
(`5bdfb819ff9512dcc3ca85f8919e5cff236de4706240cbdf09a577d56183a9ea`) are
preserved but superseded before computation after a local pre-upload preflight
found a dataset filename mapping defect. The minimal runner/host correction
and regression test pass locally and are pushed in `f69c56e`. Immutable W4
round 2 is registered (SHA-256
`5e41ffd790b64638659136bfba5b0abfda7325c3578f15fe4d16fa610a7123da`) against
source commit `97a5bca`; dataset upload and W4 measurement have not started. See
[`phase_plan.md`](phase_plan.md) for evidence and the current gate.

## Fresh OpenCode read order

Start with the repository root [`AGENTS.md`](../AGENTS.md), then read:

1. [`opencode_handoff_2026_09.md`](opencode_handoff_2026_09.md) — concise
   current SDF-native architecture, status, evidence boundaries, and immediate
   blocker.
2. [`phase_plan.md`](phase_plan.md) — the sole current roadmap, status, and
   execution-order authority.
3. [`problem_register_2026_09.md`](problem_register_2026_09.md) — the issue
   ledger. It records issue state; it does not define execution order.
4. [`CFD_opt_sdf_SDF_native_handoff/00_HANDOFF_MASTER.md`](CFD_opt_sdf_SDF_native_handoff/00_HANDOFF_MASTER.md)
   — frozen SDF-native architecture rationale and design detail. It is
   supporting context, not a roadmap.
5. [`problem_contract_v2.md`](problem_contract_v2.md) and
   [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) — active
   ProblemSpec semantics and the retained Stage T fixed-grid artifact schema.
   The fixed-grid contract does not make density the current canonical design
   state.
6. [`problem_resolution_plan_2026_09.md`](problem_resolution_plan_2026_09.md)
   — historical Stage T/S/V diagnosis and repair plan; consult it for the
   recorded rationale and evidence, not as current execution instructions.
7. [`colab_t4_batch_worker_plan_2026_09_26.md`](colab_t4_batch_worker_plan_2026_09_26.md)
   and [`kaggle_batch_runbook_2026_09.md`](kaggle_batch_runbook_2026_09.md) —
   execution infrastructure and operational procedures. Colab and Kaggle are
   execution substrates, not solver or optimizer architecture components.
8. [`git_branching_strategy.md`](git_branching_strategy.md) — branch workflow.

## Authority

1. [`phase_plan.md`](phase_plan.md) — the only roadmap, current status, and
   execution order.
2. [`problem_register_2026_09.md`](problem_register_2026_09.md) — the issue
   ledger.
3. [`problem_contract_v2.md`](problem_contract_v2.md) — generic user problem
   schema.
4. [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) —
   semantics for retained Stage T fixed-grid artifacts.
5. `docs/evidence/*.json` and registered sidecars — immutable evidence. Prose
   may summarize it but must not change its measured values, verdicts, or
   scope.

If a supporting or historical document conflicts with `phase_plan.md`, the
roadmap controls the current architecture and order. Preserve the older
document's recorded evidence and correct only the misleading current-status
framing.

## Supporting and historical documents

- [`CFD_opt_sdf_SDF_native_handoff/README.md`](CFD_opt_sdf_SDF_native_handoff/README.md)
  — index for the frozen SDF-native research handoff bundle.
- [`colab_t4_batch_worker_plan_2026_09_26.md`](colab_t4_batch_worker_plan_2026_09_26.md)
  — Colab T4 batch-worker execution design, subordinate to the roadmap.
- [`kaggle_batch_runbook_2026_09.md`](kaggle_batch_runbook_2026_09.md) —
  version-bound Kaggle execution and artifact-retrieval procedures; it does not
  set architecture or qualification order.
- [`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
  — historical density/Brinkman Stage T → B-spline Stage S → Stage V plan and
  qualification evidence. Retained; not the current production architecture.
- [`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md)
  — historical Stage T-to-Stage S bridge findings and evidence. Retained; not
  the current execution plan.
- [`stage_s_v16_contract_and_execution_plan_2026_09_25.md`](stage_s_v16_contract_and_execution_plan_2026_09_25.md)
  — frozen K=16 reference contract and its historical gates; it does not
  authorize S2 or replace the SDF-native roadmap.
- [`fixed_grid_backend_decision.md`](fixed_grid_backend_decision.md) —
  historical backend decision for the former fixed-grid Stage T route; it does
  not select the current SDF primal backend.
- [`pq3_3b_post_v5_plan_2026_09.md`](pq3_3b_post_v5_plan_2026_09.md) —
  historical Stage T campaign diagnosis and decision rules.
- [`current_state_and_next_plan_2026_09_26.md`](current_state_and_next_plan_2026_09_26.md)
  — dated September 26 snapshot, superseded for current status and next steps by
  `phase_plan.md` and the current handoff.
- [`cross_platform_research.md`](cross_platform_research.md) — platform setup,
  bounded research commands, and recorded capability evidence.
- [`development_plan_2026_09.md`](development_plan_2026_09.md) — earlier
  cross-platform design and acceptance criteria; progress authority remains
  `phase_plan.md`.
- [`architecture_review_2026_09.md`](architecture_review_2026_09.md) — earlier
  cross-platform architecture review.
- [`architecture_effectiveness_2026_09.md`](architecture_effectiveness_2026_09.md)
  — historical Stage T-to-S-to-V evidence and failure boundaries.
- [`p0_openfoam_closed_loop_2026_09.md`](p0_openfoam_closed_loop_2026_09.md)
  — historical OpenFOAM canonical-loop implementation and its evidence scope.
- [`stage_t_optimizer_diagnosis_2026_09.md`](stage_t_optimizer_diagnosis_2026_09.md)
  — historical diagnosis of the native ISQP path and Python-side optimizer.
- [`glm_downforce_assessment_2026_09.md`](glm_downforce_assessment_2026_09.md)
  — historical downforce-focused Stage T assessment and proposals.
- [`pq4_extraction_gate_record_2026_09.md`](pq4_extraction_gate_record_2026_09.md)
  — retained extraction and Stage S entry-gate evidence for the registered PQ4
  candidate.
- [`fsae_readiness_execution_plan.md`](fsae_readiness_execution_plan.md) —
  future qualification packages and entry conditions; it is subordinate to the
  current roadmap.
- [`downforce_architecture_research_2026_09.md`](downforce_architecture_research_2026_09.md)
  — advisory research on the historical Stage T downforce ranking problem; it
  adds no repository evidence and changes no gate.
- [`colab_mcp_runbook_2026_09.md`](colab_mcp_runbook_2026_09.md) —
  operational Colab MCP guidance. It describes execution infrastructure and
  does not set architecture or gate order.

## Compatibility policy

The handoff is working memory, and the frozen architecture bundle is supporting
rationale. Neither replaces `phase_plan.md` or `problem_register_2026_09.md`.
Fresh sessions must trust live Git state and current artifacts over historical
commit tables and validation snapshots. Readers for legacy v1 artifacts remain
read-only; new ProblemSpec declarations use v2 semantics. Historical Stage T
artifacts continue to use their registered fixed-grid v2 schema.
