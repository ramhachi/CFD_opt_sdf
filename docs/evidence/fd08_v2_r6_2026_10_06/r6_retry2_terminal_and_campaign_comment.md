#46 FD-08 v2 R6 terminal result and formal preregistration blocker

Retry 2 Kaggle kernel `ramhachi888/cfd-opt-sdf-fd08-v2-r6-and-formal/5` completed under criteria SHA-256 `90e9e40ffebffc96891af12bdc7942a0a038d877fe6e7bffe7a88574679e1837`, source `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9`, and private dataset v6. Host terminal verification passed 49/49 states, 0 unexpected states, and all 254 manifest files. Aggregate solver time was 5,354.967 s (cap 6,600 s); kernel elapsed was 8,976.250 s (allowance 11,200 s). The registered analyzer ran once and returned **R6 calibration PASS (8/8)**.

| Direction | Response | g_A [N/m] | SE/|g| | Nested max shift | Model A/B diff | Holdout max error/limit | Magnitude | Sign | Verdict |
|---|---|---:|---:|---:|---:|---:|---:|:---:|---|
| D0_interface_offset | drag | -0.10398729 | 0.0321 | 0.0166 | 0.0560 | 0.2485 | 6/6 | − | PASS |
| D0_interface_offset | downforce | 0.80149155 | 0.0257 | 0.0116 | 0.0129 | 0.1446 | 6/6 | + | PASS |
| D1_filtered_seed11 | drag | -0.063723941 | 0.0367 | 0.0575 | 0.0321 | 0.2746 | 6/6 | − | PASS |
| D1_filtered_seed11 | downforce | -0.10643782 | 0.0312 | 0.0663 | 0.0018 | 0.3884 | 6/6 | − | PASS |
| D2_filtered_seed2026 | drag | -0.16976294 | 0.0282 | 0.0010 | 0.0004 | 0.0236 | 6/6 | − | PASS |
| D2_filtered_seed2026 | downforce | -0.091722981 | 0.0326 | 0.0305 | 0.0216 | 0.3304 | 6/6 | − | PASS |
| P1_upstream_lobe | drag | -0.21429781 | 0.0275 | 0.0016 | 0.0043 | 0.0196 | 6/6 | − | PASS |
| P1_upstream_lobe | downforce | -0.38519519 | 0.0264 | 0.0026 | 0.0078 | 0.0850 | 6/6 | − | PASS |

Formal budget preflight passed (3,300 s solver / 5,600 s kernel allowance). Formal registration then hit a pre-registration implementation error in the formal registrar whose source hash was fixed in the R6 criteria: `raw_states` is initialized as a dict, then `.add()` is called at line 106. It raised `AttributeError: 'dict' object has no attribute 'add'` before any formal criteria, preflight, or dataset staging was written. No formal dataset upload or solver submit occurred.

Because this formal source hash was frozen before R6, I did not repair or bypass it after seeing the R6 result. Formal has no scientific verdict. Campaign status is **BLOCKED_PREREGISTRATION**; this is not a formal scientific FAIL/UNRESOLVED and is not FD-08 qualification PASS. R6 remains the last calibration. R5 remains `FAIL`, the 17 historical Stage 1 mismatches remain unchanged, and all six qualification flags remain false.

Evidence: `docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_terminal_verification.json`, `r6_retry2_analysis_summary.json`, and `docs/evidence/fd08_v2_formal_2026_10_06/formal_retry2_registration_failure.json`.
