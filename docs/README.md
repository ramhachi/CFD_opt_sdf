# Documentation map

The current production research direction is SDF-native: the canonical design
state is a bounded Cartesian signed-distance field `phi`. Read
[`phase_plan.md`](phase_plan.md) for the only roadmap, status, and execution
order. Earlier density/Brinkman Stage T and B-spline Stage S plans remain
available as historical capability and evidence context; they do not define
the current production path.

Latest execution checkpoint: FD round 5 exact private T4 kernel `/4` ran all
33 fresh primals but ended in `KernelWorkerStatus.ERROR`; the strict host
verifier failed closed because `DONE` is absent. The diagnostic-only raw CSV
postmortem confirms T6/T7 summary-schema failures and T10/T11 failure of the
registered 5% derivative plateau. See the
[`round-5 kernel diagnostic`](evidence/sdf_directional_fd_v16_round5_kernel4_diagnostic_2026_09.json)
and [`raw CSV postmortem`](evidence/sdf_directional_fd_v16_round5_kernel4_postmortem_2026_09.json).
No FD or gradient qualification is granted. W3 round 4 exact T4 kernel version
5 passed host verification for its registered finite-box primal contract.
W3 v4's all-zero root cause remains unresolved. W4 immutable criteria round 4
([SHA-256 `3efc8133c8d1b7d306041ee3f49ec5a708024f189095bdb0f13646fe329b578f`](evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json))
was executed by exact private T4 kernel version 3 and passed independent host
verification. Append-only result evidence is
[`kaggle_w4_v16_sensitivity_result_round4_2026_09.json`](evidence/kaggle_w4_v16_sensitivity_result_round4_2026_09.json),
SHA-256 `87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae`.
The registered four-case matrix passed T0-T10; the extended-domain fine-grid
follow-up condition was not triggered. This qualifies only the registered
WaterLily finite-box sensitivity matrix. OpenFOAM profile equivalence,
absolute downforce, grid/domain convergence, gradient, reverse mode, topology,
optimizer and shape update remain unqualified. The formal FD entry gate is
open. Immutable FD round 2 is preserved; its exact kernel `/1` stopped in
`host_input_preflight` before GPU or solver startup because the Python runner
referenced canonical identity names outside their scope. A complete local
preflight repair and regression coverage are implemented and pushed in source
commit `86087b888e7ea42033476bfcee9c8c7e888bb3cb`. Immutable round 3 is now
registered against source commit `9978eb4f19c716b9666c50c18261738edd978e4f`
(criteria file SHA-256
`45fb570bc3628ff083d5cd34f496e352f6ec0834ac93f381909bef1c4d13f6c5`,
canonical SHA-256
`fe49a91e5800460dc4560f453b72fd25f12158ecd4a099a1e940cbf434db8d52`).
Private dataset version 3 is `ready`; all 37 registered payload files matched
the remote manifest by path, size, and SHA-256, and the 38-file mounted
inventory passed the runner's exact local host-input preflight before GPU
inventory. Verification evidence is
[`sdf_directional_fd_v16_dataset_round3_verification_2026_09.json`](evidence/sdf_directional_fd_v16_dataset_round3_verification_2026_09.json),
SHA-256 `aad6667f391543d78a338d089daf737203222e7ec54b4ffe871ffd740745d48c`.
The exact round-3 kernel `/2` ended in `ERROR` after starting the Julia job,
but before any solver step. It hit a run-queue self-copy path error at
`waterlily_sdf_directional_fd_v16_job.jl:304`; host verification failed closed
because no `DONE` marker exists. The exact diagnostic is
[`sdf_directional_fd_v16_round3_kernel2_diagnostic_2026_09.json`](evidence/sdf_directional_fd_v16_round3_kernel2_diagnostic_2026_09.json),
SHA-256 `4044e4f01508590f622e89194427af47c599d00959cf721a0f143b136d746fae`,
with detailed failure analysis in
[`sdf_directional_fd_v16_round3_kernel2_failure_analysis_2026_09.json`](evidence/sdf_directional_fd_v16_round3_kernel2_failure_analysis_2026_09.json),
SHA-256 `faf0f9b8100b02f303b029a3644cbf5c3df4e3e0a18d935014401142936c8596`.
The queue input now comes from the runner's temporary base directory, while
Julia retains the `OUT/run_queue.tsv` snapshot; this one-path fix is covered by
an executable regression. Immutable FD round 4 is registered at
[`sdf_directional_fd_v16_criteria_2026_09_round4.json`](evidence/sdf_directional_fd_v16_criteria_2026_09_round4.json)
(file SHA `ace4e53963ee7d37d7806f48ef1ef449380294c0a5216043e50558f1d31192fd`,
canonical SHA `949d998bb9e5b83ddbb2a24efc25b57754f4db29568e0a0f6e8b062647206db9`)
and binds source commit `8bf88756791213ac75b3c36ab6316323653d5c9a`. Machine
comparison confirms the entire measurement contract remains identical to
round 3. Private dataset v4 is `ready`; all 38 downloaded files match the
staged paths, sizes and hashes, and the exact Kaggle listing agrees. Host
source and input preflight passed for the 32 pinned source inputs, W3/W4
prerequisites, canonical state, three directions and 30 perturbations. Evidence
is
[`sdf_directional_fd_v16_dataset_round4_verification_2026_09.json`](evidence/sdf_directional_fd_v16_dataset_round4_verification_2026_09.json),
SHA-256 `e3f4fecde25f4161595deda684a2db7a9bd5d83298d299cf22f4745dda4831aa`.
Exact private T4 kernel `/3` was submitted with the registered 14,400-second
timeout. Its submission checkpoint is
[`sdf_directional_fd_v16_round4_kernel3_submission_2026_09.json`](evidence/sdf_directional_fd_v16_round4_kernel3_submission_2026_09.json),
SHA-256 `7906199306835e1da529b52313e7f27b7e18bf3665c091e6c4d099b340ee52bb`.
The exact version later ended in `KernelWorkerStatus.ERROR`. All 33 registered
primal calls returned, but runner-side recomputation failed after its temporary
source checkout was removed. The strict host verifier failed closed because
`DONE` is absent; no FD result passed verification. Append-only terminal
diagnostic is
[`sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json`](evidence/sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json),
SHA-256 `f53ce0cf2784db810cdec39ba05448795010210e5e39e664810ae9f84527ded8`.
Round 4 and its `/3` outputs remain failed evidence; the formal FD oracle,
gradient, reverse, optimizer, topology and shape update remain unqualified.
Round 5 criteria remain immutable at SHA-256
`2aad32922b2746d9ee7b170b590673779e60f032b238c29d1bc7ca6b2779ee17`. Private
dataset v5 passed exact remote inventory and host-input checks. Kernel `/4`
produced 33 completed fresh runs but no outer `DONE` marker; the recorded
runner gates include genuine directional plateau failures as well as a summary
schema defect. The append-only dataset verification record is
[`sdf_directional_fd_v16_dataset_round5_verification_2026_09.json`](evidence/sdf_directional_fd_v16_dataset_round5_verification_2026_09.json),
SHA-256 `fe6159799cd23a4b44d83b5b89b616159a9f128cb34c0a373b0d0f4e981af55e`.
All FD, gradient, reverse, optimizer, topology, and shape-update qualification
flags remain false; `shape_update_allowed=false`.
See
[`phase_plan.md`](phase_plan.md) for current execution order and
[`kaggle_batch_runbook_2026_09.md`](kaggle_batch_runbook_2026_09.md) for
version-bound commands and artifacts.

## Fresh OpenCode read order

Start with the repository root [`AGENTS.md`](../AGENTS.md), then read:

1. [`opencode_handoff_2026_09.md`](opencode_handoff_2026_09.md) — concise
   current SDF-native architecture, status, evidence boundaries, and next gate.
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
- [`sdf_topology_policy_v1_2026_09.md`](sdf_topology_policy_v1_2026_09.md)
  — registered SDF topology-policy semantics, immutable registration hash,
  and the unresolved v16 Birth-0 inputs.
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
