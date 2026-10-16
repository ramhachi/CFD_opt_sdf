# HARNESS-01 smoke records (PROC-01: EXPLORATORY_COMMITTED; infrastructure capability only, no physics claim)

## v1 (source ace6ad4, kernel ramhachi888/cfd-opt-sdf-harness01-replay-a-smoke version 1, 2026-10-16 05:00 UTC)
One state (the OPT-01 v1 parent, flow_16, native placement) rendered by `scripts/harness.py smoke` from `docs/harness/harness01_replay_campaign.json`.
Result: COMPLETE, DONE, no ERROR, stage-0 self-test passed, solver ~103 s; the force CSV SHA-256 is `97e7b43c346a57a1e24be28e385d9cb9ac03d17b427677b9052683cc3e9c6477`, byte-identical to the GRID-02 f16 parent (`docs/evidence/grid02_trend_2026_10_16/kernel_output/grid02_f16/states/opt01b__parent/flow_16.forces.csv`), i.e. the harness runner reproduces the proven runner's computation on Kaggle.
Superseded for acceptance by v1.1 (review fixes S1-S6 changed the campaign format); kept as the first real-world run of the harness.

## v1.1 (source 1edbdcb, kernel ramhachi888/cfd-opt-sdf-harness01-replay-a-smoke version 2, 2026-10-16 05:23 UTC) — acceptance smoke
Same single state. Result: COMPLETE, DONE, no ERROR; `scripts/harness.py verify --smoke --source-commit 1edbdcb…` passed (`v1_1_1edbdcb/smoke_verify_table.json`, integrity pass, runner/pins/commit bound to the smoke rendering). Host-recomputed forces 0.25494295704560826 N downforce / 0.22350538264820372 N drag and the force CSV SHA `97e7b43c…` equal the GRID-02 f16 parent exactly.
Together with the local replay acceptance (verify on all five saved GRID-02 kernel outputs reproduces `grid02_analysis.json` state_forces_n bit for bit) this completes HARNESS-01's acceptance. Evidence class: infrastructure capability; no physics claim.
