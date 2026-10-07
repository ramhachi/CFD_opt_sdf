# #46 formal amend1: post-registration host execution-path blocker

This is an append-only infrastructure stop record. It does not supersede or
modify the registered criteria, R6 evidence, or the Formal Preregistration
Lineage Amendment design. No formal scientific observation or verdict exists.

## Registered identity

- Formal execution source: `30aa20a6891ccabefaa2ef6d41a2e2b5e26701b5`.
- Registration checkpoint commit: `62ca5ac`.
- Criteria: `FD08-V2-FORMAL-AMEND1-2026-10-07`.
- Criteria SHA-256: `857c21231eb48708daba784318445c43d115dca48567dfd3378c3ba177bd57fe`.
- Formal round: `fd08_v2_formal_2026_10_07_amend1`.
- Local dedicated dataset identity: `ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend1`.
- Dataset and kernel remote versions: none; upload and submission were not attempted.
- Immutable R6 parent source: `f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9`.
- R6 verdict remains PASS, 8/8; its analyzer remains at one historical execution.

## Observed failure

After immutable formal registration, host verification used the actual
registered shared runner with an exact 54-file mounted input inventory.
`load_criteria()` and `verify_dataset()` both passed. All 40 source-input SHA
values matched the formal execution commit's Git tree.

The next call, `validate_state_files()`, raised the following exception before
solver execution:

```text
infra/kaggle/kernel_fd08_v2_r6/runner.py:253
criteria["geometry_reject_gates"]["minimum_zero_level_margin_m"]
KeyError: 'geometry_reject_gates'
```

The formal registrar stores the unchanged R6 geometry gates at
`scripts/register_fd08_v2_formal.py:321` as:

```python
"geometry": r6["geometry_reject_gates"],
```

The shared registered runner expects the field name `geometry_reject_gates`.
This is a criteria-schema/consumer incompatibility already present in the
pre-amendment implementation. The lineage amendment preserved that field and
the runner bytes. The scientific thresholds themselves have not changed.

The exact traceback, checks, identities, flags and absence of execution are
preserved in
[`registration_host_verification.json`](../evidence/fd08_v2_formal_2026_10_07_amend1/registration_host_verification.json),
with its reproducer and SHA sidecars. The reproducer catches the exception to
save this record; its process exit code does not mean the host gate passed.

## Why pre-registration validation missed it

The real dry-run constructed all 25 states with registrar geometry/mask,
Float32, uniqueness and disjointness audits. Its fresh checkout exercised the
runner's `verify_source()` function. It did not call the runner's
`validate_state_files()` on the fully mounted candidate payload. The nine new
lineage tests and both independent reviews therefore passed their stated
scope without detecting this consumer schema mismatch. Focused tests were
107/107, and full pytest had exactly the 37 pinned baseline failures with zero
new failures. Those results are preserved; they are not sufficient evidence
of a complete host execution-path pass.

This coverage gap is material and is recorded explicitly. The pre-registration
source-ready comment and review artifacts retain their historical contents;
this record provides the later correction to their practical execution scope.

## Fail-closed disposition

- `formal_registered=true`, criteria and 55-file local packaging payload immutable.
- `formal_dataset_uploaded=false`, `formal_kernel_submitted=false`.
- `formal_solver_executed=false`, `formal_response_observed=false`.
- `formal_analyzer_executed=false`, formal comparisons executed: zero of 24.
- Formal scientific verdict: none, not FAIL or UNRESOLVED.
- Campaign status: **BLOCKED_INFRASTRUCTURE**.
- R6 remains PASS; no R6 rerun or reanalysis occurred.
- All six qualification flags remain literal false.

The user's post-registration source-correction rule requires a new amendment,
new source and a new preregistration identity. Consequently the current criteria
and payload will not be patched, re-registered, uploaded, or submitted. No
scientific source, threshold, epsilon, direction, model, covariance, coverage,
fit, or budget adjustment is made at this stop. A later authorized repair must
preserve this blocked registration and test the actual runner's mounted-input
validation before creating a different immutable registration.

The exact local registered payload is archived losslessly, including metadata,
with per-file hashes in `formal_registered_payload_inventory.json`. The archive
was independently read back and every one of its 55 files matched. Remote
runtime, solver time, terminal evidence, force responses and a 24-comparison
numerical table do not exist for this attempt.
