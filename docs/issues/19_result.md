# INFRA-02 immutable criteria supersession

## Scope

This change adds a small, reusable builder and validator for source-only retry
rounds. It does not register a new FD measurement round, run a solver, or change
any existing criteria/evidence. Calibration for FD-08 changes the measurement
contract and therefore requires a new criteria contract; it cannot use this
source-only supersession path.

The builder requires immutable predecessor criteria and sidecar files plus an
immutable terminal diagnostic and sidecar. It binds the exact predecessor file
hash, canonical criteria hash, diagnostic hash, terminal kernel ID/version and
ERROR/COMPLETE status. A successor advances the round exactly once, gets a new
registration source commit and timestamp, remains unrun, and preserves all
measurement-contract fields and all non-source inputs. Source changes must be
listed by exact registered input name and path with a non-empty diagnostic
reason; the source hashes are read from the selected Git commit. The validator
rejects changed thresholds, matrices/directions, backend, geometry, epsilon,
dataset identity, source inventory, kernel/title slug mismatch, and enabled
qualification flags. The writer refuses to overwrite either successor file
and its SHA-256 sidecar. Registration records the successor kernel version as
pending with the required relation to the predecessor version, and pins the
dataset ID, exact version, and file-inventory hash. A post-submission verifier
checks those identities; a frozen dataset version can be reused only with the
same exact inventory.

## Validation

Evidence is limited to contract tests and historical criteria compatibility.
The round-4-to-round-5 regression checks that the historical successor retains
the measurement contract and changes only four registered source inputs:
`criteria_draft`, `criteria_registrar`, `harness_tests`, and `kernel_runner`.
Negative tests check altered measurement terms (including epsilon), a wrong
predecessor diagnostic, a mismatched kernel/title identity, and an incomplete
source-change allowlist. They also check exact successor submission identity
and append-only writing. These tests do not establish FD-oracle or CFD
qualification.

No Kaggle/GPU run is part of this issue.

## Commands and artifacts

| Command | Result | Evidence class |
| --- | --- | --- |
| `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_criteria_supersession.py` | 12 passed | Focused contract regression |
| `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m compileall src tests` | Passed | Syntax/bytecode validation |
| `PYTHONPATH=src /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q` | 37 failed, 1256 passed, 5 skipped; failure IDs exactly match the established 37-ID baseline, with no new failures | Full repository suite; pre-existing failures only |
| `git diff --check` | Passed | Patch whitespace validation |

The full-suite output is preserved at
`work/issue19_validation/full_pytest.log` (SHA-256
`a50e5dce415aa99b45242964bce8469c4a6f7b1e279a24bca42a77b72f8c7115`). The
baseline failure-ID artifact is
`/Users/sota/.codex/worktrees/kaggle-batch-migration/CFD2026_09/work/four_track_2026_10_02/baseline_failure_ids.json`
(SHA-256 `71c9d7cec4639d4443ff1f7e239e68d735dd0e9d26559eca047a380b21a2bf3a`);
the current and baseline ID sets compared equal. `compileall` output is
preserved at `work/issue19_validation/compileall.log` (SHA-256
`6cc1d0a4a09296b0a6246d4f63c0c39840f51c459278ec71887fac107def67f8`).

This worktree initially lacked the gitignored v17 state fixture. The exact
fixture was copied read-only from the original checkout to
`work/sdf_native_genesis_v17/sdf_design_state.npz` and has SHA-256
`7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31`; this
made the relevant pre-existing fixture-dependent test runnable. No generated
solver evidence was created or changed.

Source artifact hashes before commit:

| Path | SHA-256 |
| --- | --- |
| `src/cfd_sdf/criteria_supersession.py` | `df3bc798cfbb666f5a9f5679298e02313c8f3cffe6ce7e330ccba01dea0466b4` |
| `tests/test_criteria_supersession.py` | `9fd8f443aebcdec04d0e62b490e08593dcbd54a991d99ac38c3eb2ffcca55a24` |
| `docs/issues/19_result.md` | recorded by the pushed commit |
