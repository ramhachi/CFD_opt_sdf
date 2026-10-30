# #46 Formal Infrastructure AMEND3 — Kaggle Kernel Identity Repair

The user authorized AMEND3 on 2026-10-07. R6 remains immutable PASS, 8/8; no R6
solver or analyzer is rerun. AMEND1 and AMEND2 registered criteria, payloads,
datasets and blocker records remain historical evidence; their files are never
edited, regenerated or overwritten. AMEND3 supersedes the unsubmitted AMEND2
registration, not its scientific contract. Main and unrelated worktrees are
untouched. All six qualification flags remain false.

## Parent and exact blocker

AMEND2 criteria `FD08-V2-FORMAL-AMEND2-2026-10-07` has SHA-256
`ccbe6abd4f41c0900a3dd69612e31af7013d01040b7554b9e394d2f9eef0cf6e` and execution
source `f072bc7c5a9e98cc84f7a6a225c0780ad10e31be`. Its private dataset
`ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend2` version 1 was uploaded and all 54
files verified. The formal `SaveKernel` was refused twice (HTTP 409,
`ALREADY_EXISTS`): the requested kernel title "CFD Opt SDF FD08 V2 Formal Amend2"
is already in use by a dataset. No kernel version exists, no solver started, and
zero formal observations/comparisons exist (failure record SHA-256
`d8740544264547491ad0afd0ed1c53000f1fe233d24313b4d428e215cb346bf5`).

Cause: the AMEND2 registrar set `KERNEL_ID = DATASET_ID`; a kernel title and a
dataset slug share one Kaggle slug namespace. The same collision had already been
repaired for R6 (`c8f2ebe`) but was not carried into the formal registrars. The
AMEND2 rehearsal used a differently named `-pre-solver` kernel, so the registered
kernel identity was never exercised before submission.

## Allowed changes and unchanged science

Only identities change: criteria id/round, dataset id, **kernel id and title**,
source commit/inventory, supersession and lineage fields, budget evidence and
artifact paths. Every scientific field of AMEND2 is copied and compared for exact
equality (scientific projection SHA-256
`8d76b3b4b5837dda38259d560f163223be92531d83b62236a21f5788a01cdb0f`, equal to AMEND1/2);
the 25 state inventory, every `.phi.f32f`/`.npz` byte, the three formal epsilons
(0.6294627058970836, 1.5811388300841898, 3.971641173621408 mm), Model A/no refit,
T2 parameters, COV-A, prediction/magnitude/sign/error rules, aggregation and the
3300 s solver / 5600 s kernel caps are unchanged. `scientific_contract_changed=false`.
The shared runner, gate, analyzer and verifier are not modified (the runner never
reads Kaggle identity metadata).

New identities:

| Item | Value |
|---|---|
| Criteria / round | `FD08-V2-FORMAL-AMEND3-2026-10-07` / `fd08_v2_formal_2026_10_07_amend3` |
| Formal dataset (private) | `ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend3` |
| Formal kernel | `ramhachi888/cfd-opt-sdf-fd08-v2-formal-run-a3`, title "CFD Opt SDF FD08 V2 Formal Run A3" |
| Rehearsal dataset / kernel | `…-formal-amend3-rehearsal` / `…-formal-amend3-pre-solver` |
| Superseded status | `REGISTERED_UPLOADED_NOT_SUBMITTED_NOT_RUN_SUPERSEDED_INFRASTRUCTURE` |

The AMEND2 dataset version 1 is left untouched. The title-derived slug of the formal
kernel must differ from every dataset slug.

## Pre-registration identity gates (new)

1. The registrar refuses to run unless `KERNEL_ID != DATASET_ID`, the kernel slug is
   the slug of the kernel title, it equals no dataset slug this campaign has used (hard-coded list plus recorded dataset metadata), and
   the kernel metadata `dataset_sources == [DATASET_ID]`.
2. A test asserts the same, so a future registrar copy cannot regress it.
3. `scripts/check_fd08_v2_kaggle_identity_free.py` lists the owner's Kaggle kernels
   and datasets (pinned CLI 2.2.4) and fails if any intended slug, or any title-derived
   slug, is already used. The per-slug `status` probes are recorded but are not the
   decisive signal (they return 403 for a missing item).
4. The registered kernel id cannot itself be rehearsed: the pre-solver stop hook needs
   the environment variable `FD08_V2_STOP_BEFORE_SOLVER`, which requires a wrapper notebook
   (`kernel_type: notebook`), whereas the registered formal kernel is a `script` whose bytes
   are hash-bound. Gates 1–3 stand in for it; this limitation is recorded rather than hidden.

## Actual pre-solver execution gate

Unchanged from AMEND2: the exact merged source passes a T4 rehearsal
(`PASS_PRE_SOLVER_EXECUTION_PATH`, 43→44 source inputs, 54 mounted files, 25/25 states,
`solver_started=false`, no force history) before registration, and the registered bytes
pass it again before dataset publication and kernel submit.

## Execution and final interpretation

Submit the formal kernel once. Any Kaggle error, source or identity bug is recorded
without retry, rename or patch; it requires a new amendment and a user decision.
After a complete 25/25 terminal and host integrity PASS, the registered analyzer runs once
and gives PASS/FAIL/UNRESOLVED over the 24 preregistered comparisons. Criteria are
not changed after seeing results. A formal PASS does not change any qualification flag,
and claims neither physical truth, grid independence, arbitrary directions, full-field
gradient, ε→0 exact derivative, reverse AD, optimizer nor topology qualification.
