#46 FD-08 v2 Formal Preregistration Lineage Amendment: source-ready checkpoint

R6 remains **PASS, 8/8**. Formal is still **NOT REGISTERED / NOT RUN** at this checkpoint. All six qualification flags remain false.

The original pre-R6 registrar SHA is `7882195db39b01a3178c9ef1b8bc8c014ba1a579c81c768cf8fdb7df22b5c92c`. Its dict initialization followed by `.add(raw)` caused the preserved pre-registration `AttributeError`. The subsequent source-lineage issue would have mixed the old R6 checkout commit with the amended registrar SHA; the original dataset identity also reused R6's dataset.

The user-authorized **post-R6 Formal Preregistration Lineage Amendment** repairs the set initialization and separates formal execution source from calibration provenance. Amended registrar SHA is `0570d34a06fa9469b9db7a96f780fc8f95d3535867fe48f8e53b162dd81467b6`. Feature implementation `bf7e6ae`, independent review checkpoint `9c2aa51`, and validation checkpoint `d076774` were merged with `--no-ff` and pushed as clean integration source **`30aa20a6891ccabefaa2ef6d41a2e2b5e26701b5`**. The shared runner and all scientific sources are byte-identical.

Formal top-level `source_commit` will bind that amended execution commit. Exact R6 source `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9` and criteria/result/terminal SHA remain in `calibration_binding`. Formal criteria/round are `FD08-V2-FORMAL-AMEND1-2026-10-07` / `fd08_v2_formal_2026_10_07_amend1`; the dedicated private dataset and kernel are both `ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend1`. R6's dataset is not updated.

**scientific_contract_changed=false**: same four directions, intervals `{0,2,4}`, geometric-mean interior epsilon, Model A/no refit, T2, COV-A, prediction/magnitude/sign/error rules, aggregation, 25-state inventory and 3300/5600 s caps. Two independent reviews passed. Actual host dry construction checked all 49 parent phi arrays, 25 formal states, geometry/masks/Float32 audits and byte disjointness. A fresh amended-source checkout passed the unchanged runner's 40-source-input SHA verification. Focused tests: 107 passed; full pytest: 37 failed / 1506 passed / 9 skipped, exact baseline 37 IDs with zero new/resolved. Compileall, py_compile, CLI imports and diff check passed. Integration-source lineage tests/dry-run passed again before this checkpoint; fresh pinned CLI budget capability passed.

No formal criteria or solver observation exists yet. Immutable registration is the next gate. No R6 reanalysis/re-execution occurred; R5 FAIL, the 17 historical Stage 1 mismatches, and Stage 1.5 evidence remain unchanged.

Evidence: `docs/issues/46_fd08_v2_formal_lineage_amendment_2026_10_07.md` and `docs/evidence/fd08_v2_formal_2026_10_07_amend1/`.
