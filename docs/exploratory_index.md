# Exploratory run index (PROC-01, append-only)

Every `EXPLORATORY_COMMITTED` run is listed here, including failures, so the denominator stays visible. Exploratory results never feed a qualification flag, threshold, gate or `shape_update_allowed`, and are cited only after a registered re-run on disjoint data (`docs/phase_plan.md`, 2026-10-16 entry).

| date | id | purpose | commit | outputs (hash) | result in one line | claim ceiling |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-16 | HARNESS-01 smoke v1 | first real-world run of the common harness (1 state, GRID-02 f16 parent) | ace6ad4 | forces CSV 97e7b43c… | COMPLETE; byte-identical to GRID-02 | capability |
| 2026-10-16 | HARNESS-01 smoke v1.1 | acceptance smoke of harness v1.1 (same state) | 1edbdcb | forces CSV 97e7b43c…; smoke_verify_table.json | COMPLETE; verify --smoke pass; byte-identical | capability |
