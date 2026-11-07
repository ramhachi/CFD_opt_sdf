# GRAD-00 local validation artifacts

This directory contains software checks and short CPU preflights, not registered [80,120] measurements. Synthetic orchestration uses zero solver steps and is explicitly marked SYNTHETIC_TEST_FIXTURE. CPU CLI epsilon values 0.001 m are synthetic fixtures and are not selected FD-08 plateau values.

`capped_attempts/` preserves externally timed-out earlier preflight attempts and gives no PASS claim. `pytest/original_full_abort.*` preserves the original full-suite Metal initialization abort, which cannot establish a baseline failure set. The attempted later CPU-only comparison excludes the same existing Metal test file, but the base run reached its 1800 s cap near 46%; the final full CPU run was not started. Global failure-set equality is NOT_ESTABLISHED. Focused new modules passed all 137 tests.

`SHA256SUMS` covers the final retained files. Commands retain the actual checkout/output paths used during execution. All qualification flags remain false. No Kaggle push or GRAD-00 GPU measurement was performed.
