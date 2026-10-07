Formal Preregistration Lineage Amendment: immutable registration succeeded, then host execution-path verification blocked. **Campaign = BLOCKED_INFRASTRUCTURE; formal REGISTERED / NOT RUN.** R6 remains PASS (8/8), unchanged; no R6 rerun or reanalysis occurred.

| Identity | Value |
|---|---|
| Amended formal execution source / no-ff integration merge | `30aa20a6891ccabefaa2ef6d41a2e2b5e26701b5` |
| R6 parent source | `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9` |
| Original pre-R6 registrar SHA-256 | `7882195db39b01a3178c9ef1b8bc8c014ba1a579c81c768cf8fdb7df22b5c92c` |
| Amended registrar SHA-256 | `0570d34a06fa9469b9db7a96f780fc8f95d3535867fe48f8e53b162dd81467b6` |
| Formal criteria ID | `FD08-V2-FORMAL-AMEND1-2026-10-07` |
| Formal criteria SHA-256 | `857c21231eb48708daba784318445c43d115dca48567dfd3378c3ba177bd57fe` |
| Formal preflight SHA-256 | `417ca756e49de1a6f6355c47cb10f5da41edcebc533c05626c0be844a05dee2f` |
| Formal dataset/kernel identity | `ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend1` |
| Immutable registration checkpoint | `62ca5ac` |
| Host blocker/evidence checkpoint | `53710bc9c041d4b58c4a2ad476db10f6aa23414a` |

The allowed fixes repair `raw_states = set()`, separate formal execution source from the immutable calibration parent, bind amendment/review provenance and use distinct formal criteria/dataset/round/kernel identities. Both independent reviews passed in their stated lineage/scientific scope. Scientific contract changed = **false**: all directions, exact epsilons, Model A/no-refit, T2, COV-A, formulas, thresholds, aggregation and 3300/5600 s caps remain frozen. Focused tests: 107 passed. Full pytest: 1506 passed / 37 failed / 9 skipped, exactly the pinned 37 failure IDs, zero new and zero resolved. Compileall, py_compile, imports and diff check passed. Integration-source lineage tests: 9 passed; fresh checkout verified all 40 source inputs.

Actual registration constructed 25 unique states (baseline 1 + 24 signed), registrar geometry/mask/Float32 audits and disjointness from all 49 R6 arrays. Exact formal epsilons are `0.6294627058970836`, `1.5811388300841898`, `3.971641173621408` mm. Current CLI 2.2.4 budget capability passed before registration; caps were not changed.

**Observed host blocker:** `load_criteria()` and the exact 54-file mounted dataset verification passed. The registered runner then raised:

```text
infra/kaggle/kernel_fd08_v2_r6/runner.py:253
criteria["geometry_reject_gates"]["minimum_zero_level_margin_m"]
KeyError: 'geometry_reject_gates'
```

The formal registrar saves these unchanged gates under `geometry` (`scripts/register_fd08_v2_formal.py:321`), while the shared runner expects `geometry_reject_gates`. This pre-existing criteria-consumer mismatch was preserved by the amendment. The pre-registration dry-run exercised runner **source verification**, but did not exercise its **mounted state validation**; that coverage gap is explicitly recorded. Passing tests/reviews do not imply that this final host execution gate passed.

Per the post-registration source-correction policy, the immutable criteria and payload are preserved without patching. A new source repair requires a new amendment/source/preregistration identity. **No dataset upload, kernel submit, solver execution, formal observation, analyzer execution or formal scientific verdict occurred.** No remote dataset/kernel version or runtime/solver time exists; zero of 24 scientific comparisons were executed. This is neither FORMAL FAIL nor FORMAL UNRESOLVED.

All 55 packaging files are saved losslessly in the registered payload archive (54 mounted files + metadata), with every file independently read back and SHA-verified. Archive SHA-256: `b8102a7ed16c6e5925bc2876d8289b8e75a076015c644bf48aca2094d3fcde1b`. Dataset inventory SHA-256: `b3af8d1f28e542c5f83e13131e16e342248256af90b4e3b40a8081f096496a41`.

Evidence: [registration host verification](https://github.com/ramhachi/CFD_opt_sdf/blob/53710bc9c041d4b58c4a2ad476db10f6aa23414a/docs/evidence/fd08_v2_formal_2026_10_07_amend1/registration_host_verification.json), [stop record](https://github.com/ramhachi/CFD_opt_sdf/blob/53710bc9c041d4b58c4a2ad476db10f6aa23414a/docs/issues/46_fd08_v2_formal_amend1_host_blocker_2026_10_07.md), [campaign state](https://github.com/ramhachi/CFD_opt_sdf/blob/53710bc9c041d4b58c4a2ad476db10f6aa23414a/docs/evidence/fd08_v2_formal_2026_10_07_amend1/campaign_stop.json). `docs/phase_plan.md` received append-only registration and blocker checkpoints.

R5 FAIL, Stage 1's historical 17 strict mismatches, Stage 1.5 and all immutable R6 artifacts are unchanged. All six qualification flags remain literal false (`fd_oracle`, `field_gradient`, `reverse`, `optimizer`, `topology`, `shape_update_allowed`). No physical/grid/full-gradient/reverse/optimizer/topology qualification is claimed. Main and unrelated worktrees were untouched. Work stops here.
