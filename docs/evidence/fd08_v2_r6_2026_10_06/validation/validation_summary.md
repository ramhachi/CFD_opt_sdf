# FD-08 v2 R6 implementation validation

Validation was run on feature branch
`exp/issue46-fd08v2-r6-execution-2026-10-06`, before source integration and
before any Kaggle setup rehearsal or scientific solver run.

- Focused suite: **49 passed** across the v2 campaign, evaluator, numeric
  contract, terminal inventory, and Kaggle budget preflight tests.
- Full suite: **37 failed, 1,494 passed, 9 skipped**. The current 37 failure
  IDs exactly match `docs/evidence/four_track_baseline_2026_10_02/failure_ids.json`
  (SHA-256
  `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`): zero
  new and zero resolved IDs. The unchanged failure details are preserved in
  the JUnit output; this is not reported as a clean full-suite run.
- JUnit is stored losslessly compressed as `full_pytest.xml.gz` (SHA-256
  `39a1ac78dbf660502a7ef05b8e4a8531e27d04d3fa683620bde7d08d39783740`;
  decompressed XML SHA-256
  `e6324d013c6e009413ce5f7e1f7a4489384cb54a428c1ad28ea6f9b7da3341f6`). The
  normalized ID set is in `failure_ids.json`; exact comparison is in
  `failure_id_comparison.json`.
- `python -m compileall -q src tests scripts`: passed.
- CLI `--help` import smoke for all new registration, verification, and
  analysis commands: passed.
- Julia `Meta.parseall` for the bounded setup job and the registered Candidate
  C flow job: passed.
- `git diff --check`: passed.

The canonical v17 fixture used by the tests was the byte-identical NPZ with
SHA-256
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`.
The v2 evaluator is not applied to R5 response data; the new v2 runner,
verifier, and analyzer read only their registered v2 inputs and result paths.

The full-suite failures are not reported as passing tests. The acceptance for
this validation step is unchanged baseline failure identity with no additional
failure, not a clean full-suite run.
