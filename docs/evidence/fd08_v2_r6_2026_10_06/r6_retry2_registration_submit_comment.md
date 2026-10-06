#46 FD-08 v2 R6 retry 2: immutable registration and Kaggle submit

Retry 2 is immutably registered under criteria SHA-256 `90e9e40ffebffc96891af12bdc7942a0a038d877fe6e7bffe7a88574679e1837`, bound to source `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9`. The exact 49-state inventory, four approved directions (including frozen P1), six-point L6 ladder, no-jitter rule, T2 parameters, and COV-A 8/8 requirement are unchanged. All source hashes and the source-bound setup rehearsal passed before registration.

The runbook-pinned Kaggle CLI 2.2.4 submitted T4 kernel `ramhachi888/cfd-opt-sdf-fd08-v2-r6-and-formal/5`; its initial status was `KernelWorkerStatus.RUNNING`. It uses verified private dataset version 6 (103/103 files match; inventory SHA-256 `f1c5f614ee89a4210746fe34a5a6a2933c36da88534a13a4715e492e7b709972`). Registered caps are 6,600 s aggregate solver and 11,200 s kernel execution; they do not guarantee runtime.

This new attempt follows the prior analyzer serialization infrastructure failure. The prior output is not reused, and no science verdict was produced from it. Retry 2 uses a new immutable criteria identity and has not yet reached terminal verification or analysis. No thresholds, model, direction, ladder, or budget were adjusted. R6 remains the last calibration; R5 remains `FAIL`; the 17 historical Stage 1 mismatches remain unchanged; formal remains conditional on 8/8 R6 `PASS`.

Evidence: `docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_criteria.json`, `r6_retry2_dataset_verification_r2.json`, and `r6_retry2_submission.json`.
