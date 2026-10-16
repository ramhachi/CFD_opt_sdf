# Exploratory run index (PROC-01, append-only)

Every `EXPLORATORY_COMMITTED` run is listed here, including failures, so the denominator stays visible. Exploratory results never feed a qualification flag, threshold, gate or `shape_update_allowed`, and are cited only after a registered re-run on disjoint data (`docs/phase_plan.md`, 2026-10-16 entry).

| date | id | purpose | commit | outputs (hash) | result in one line | claim ceiling |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-16 | HARNESS-01 smoke v1 | first real-world run of the common harness (1 state, GRID-02 f16 parent) | ace6ad4 | forces CSV 97e7b43c… | COMPLETE; byte-identical to GRID-02 | capability |
| 2026-10-16 | HARNESS-01 smoke v1.1 | acceptance smoke of harness v1.1 (same state) | 1edbdcb | forces CSV 97e7b43c…; smoke_verify_table.json | COMPLETE; verify --smoke pass; byte-identical | capability |
| 2026-10-16 | T2-0a attempt 1 | 2D wing case on Kaggle CPU | 415f36e | attempt1_r1/ERROR.json | stopped before any case: OpenFOAM lock only for jammy, image is noble | descriptive numerical |
| 2026-10-16 | T2-0a attempt 2 | same, lock by codename | 6af9e92 | (scratch) smoke.json | SA/SST smoke ran; LM diverged; checkMesh failed (unused points, skewed cells) | descriptive numerical |
| 2026-10-16 | T2-0a meshcheck | mesh-only checkMesh of 25 (spec, height) | fix commit | meshcheck_r1/meshcheck.md | all 25 Mesh OK; numpy proxy agrees | descriptive numerical |
| 2026-10-16 | T2-0a attempt 3 | 13 cases: SA-WF and SST-WF x 5 heights, SST->LM x 3 | fix commit | attempt3_r3/analysis.md | all complete; SA Cl within ~5 % of experiment at h/c 0.224/0.09; peak at 0.134 | descriptive numerical |
| 2026-10-16 | MODE-01 prescreen | solver-free geometry prescreen of 11 modes x amplitudes on the OPT-01 v1 parent and a quarter-cell re-genesis diagnostic | this commit | prescreen.json 30deab8c…, prescreen_regen6p25.json 5b41474b… | 13/76 states pass all hard gates on the registered parent, none a wide rigid mode (only inward signs); tie plateau, pinned end layers and a 2-3 cell thick slab identified | geometry only |
