#46 FD-08 v2 R6 retry 2: source-ready checkpoint

R6 retry 2 is ready for the immutable T4 run. The approved contract is unchanged: T2 parameters, four-direction COV-A (8/8 series), six-point L6 ladder, no jitter, and the 49-state inventory. Criteria SHA-256 is `90e9e40ffebffc96891af12bdc7942a0a038d877fe6e7bffe7a88574679e1837`; it binds solver/analyzer source commit `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9`. The pushed integration HEAD is `563c47158b436e557ae735e3f0337c6d2abe8ff2`; all 35 criteria-bound source/input hashes still match.

The Kaggle CLI 2.2.4 runbook workflow created private dataset version 6. Its status is `ready`, and all 103 remotely downloaded files match the registered inventory and hashes (inventory SHA-256 `f1c5f614ee89a4210746fe34a5a6a2933c36da88534a13a4715e492e7b709972`). The new-source setup-only rehearsal passed on the same source commit and contained no force history. Budget preflight passed for 6,600 s aggregate solver time and 11,200 s kernel allowance.

Attempt 1 remains an analyzer infrastructure failure: its complete solver artifacts passed terminal integrity, but serialization stopped before an analysis result or scientific verdict. Retry 2 has a new immutable criteria and will not reuse that output. R5 remains `FAIL`; the 17 historical Stage 1 strict mismatches remain unchanged. R6 is still the last calibration, and formal remains conditional on 8/8 R6 `PASS`. No retry-2 solver execution has started yet. The next action is the runbook-pinned Kaggle CLI T4 submit.

Evidence: `docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_criteria.json`, `r6_retry2_dataset_verification_r2.json`, and `r6_retry2_kernel_pre_submit_check.json`.
