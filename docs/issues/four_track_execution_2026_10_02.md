# Four-track execution checkpoint — 2026-10-02

Evidence class: orchestration and Python regression baseline. This checkpoint
does not report a solver qualification or a cross-fidelity verdict.

The additional user prerequisites are recorded in `docs/phase_plan.md` under
the four-track execution adjustment. Commit `82ffe29` was reviewed with
`git diff --check`, merged with `--no-ff`, and pushed as integration head
`2fd7f6abc5d21d74cadf7e207f75785c582bc7cb`. The existing checkout remains on
`fix/w3-w4-verifier-bugs`; its unrelated `.claude/` state was preserved.

The initial worker allocation is GPT-6 luna A (#44), B (#45), and C (#46/#47),
each on an issue-specific branch/worktree. The available pool has three worker
slots; subsequent infrastructure and geometry issues use slots as they become
available. The orchestrator reviews source, evidence scope and prerequisites
before integration, registration and execution. OpenCode and Colab are unused.

## Regression baseline

At clean integration source `2fd7f6abc5d21d74cadf7e207f75785c582bc7cb`:

```text
.venv/bin/python -m pytest -q --tb=short
37 failed, 1226 passed, 4 skipped in 204.85s; exit 1
```

Raw log SHA-256:
`46afeaaf2b1cbc6c1f50acb2c053b289f9d194c750cbf5db5f99690d9a8a3589`.
Sorted failure-ID JSON SHA-256:
`71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`.
The lossless log, failure IDs and machine-readable baseline are preserved in
[`four_track_baseline_2026_10_02`](../evidence/four_track_baseline_2026_10_02/).

Fresh worktrees also lack the ignored canonical v17 NPZ/raw inputs used by one
FD preregistration test. Compare exact failure IDs after copying those
read-only inputs with their identities preserved; report initial missing-input
failures separately. Do not infer source regressions or remove tests to make
the failure count match. Optional ignored fixtures can also change skip counts.

## Execution substrate

`kaggle --version` returned `Kaggle CLI 2.2.4`; authenticated
`kaggle kernels list --mine --page-size 5` exited 0. This confirms API access,
not GPU availability, runtime identity, or solver execution. Formal batches
must still bind exact kernel/dataset versions and host-verify terminal outputs.

Historical v16 Stage V case inputs were found in the original checkout under
`work/stage_v_v16_domain_boundary_2026_09/`. Track B reads them without changing
the originals and stages only fresh initial fields, configuration and geometry.
Solved meshes and histories cannot substitute for a fresh environment replay.

All six qualification and shape-update flags remain false. Track B's resolved
AGREE/DISAGREE/UNRESOLVED verdict and the user decisions for #31 remain pending.
