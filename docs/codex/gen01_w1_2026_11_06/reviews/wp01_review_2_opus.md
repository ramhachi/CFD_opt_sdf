# Opus source review 2 of WP1 (PR #88, ab801695), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions: `docs/local_gpu_env_gate_2026_11_01.md` §11 Amendment 3 and `01_local_gpu_01.md` Amendment 4.

# Source review round 2: WP1 LOCAL-GPU-01 (PR #88, HEAD ab801695 on e6c57e7b/e3dcdf61)

Read-only review; no Julia, no GPU. What I ran:
- the 5 focused test files: **169 passed**;
- a scratch script re-verifying UNC-01 U01 from the current tree and comparing tool hashes with every freeze;
- `git diff e3dcdf61` of each `TOOL_FILE` and `BASE_PIN`;
- `patch` of the job `.diff`;
- a scratch copy of the tree with tool files edited one at a time, then the guard test rerun;
- SHA checks of the artifacts and of source-stability "after" against HEAD;
- the C3 anchors recomputed.

## Round-1 findings

**B1 CLOSED.**
- `git diff e3dcdf61 HEAD -- src/cfd_harness/` shows only the new `backend_profiles.py`.
- All 5 `SC.TOOL_FILES`, the non-file `BASE_PINS` and the registered flow_32 job are identical to e3dcdf61.
- Re-verification from the current tree is byte-equal: `smoke byte-equal: True`, `formal byte-equal: True`.
- `SC.tool_hashes()` at HEAD equals the tool hashes in all 9 `docs/harness/*.prerun_freeze.json` and in the UNC-01, FID-01 and SCREEN-01 `freeze1.json` files.
- No freeze pins anything under `src/` except `campaign_schema.py`.

**M1 CLOSED.**
- `tests/test_harness_registered_reverify.py` imports from the worktree `src` (`pythonpath=["src"]`, no installed package), with no git archive. It covers smoke and formal and compares raw bytes.
- I simulated edits in a scratch copy: an edit to `campaign_verify.py`, `campaign_build.py` or `harness.py` fails both cases; an edit to the BASE_PIN `grid01_gpu.py` fails smoke.
- A second test re-verifies registered evidence after `verify_local` runs in the same process.

**Local backend confinement: done.**
- `adapt_runner` (`backend_profiles.py:152-178`) loads `backend_profiles.py` by path from `source`, after pin verification. It then calls `validate_local_campaign` and the unchanged `SC.validate_campaign` with `backend_profile` stripped. Each hook must match exactly once.
- `MODULE_REL` is in the top-level `pins`, and that is enforced.
- `render_runner`/`render_local` use `B.pin_block` and `B.pins` without editing `B`.
- `verify_local` reuses `V.verify`/`V.check_kernel` through `_bind`: function copies with private globals, and `SimpleNamespace` copies of `SC`/`B`.
- I found no `setattr`, module-attribute assignment or `sys.modules` edit in `local_gpu.py`, `local_gpu_gate.py`, `backend_profiles.py` or `capture_lock.py`.
- No tool file, `grid01_gpu.py` or `harness.py` imports `backend_profiles`, so the default path is the e3dcdf61 code.

**M2 CLOSED.** The required set is C1, C2, C5, C6 and C_identity (`local_gpu_gate.py:733`). C_identity is the one-UUID rule of §11.5. C3 and C4 are reported under `descriptive_issues`, and a test checks they never block.

**M3 CLOSED** (new minor n2 below).
- (a) Clock drawdown uses solver-active samples only: utilization ≥ 50 % or inside `solver_intervals`.
- (b) VRAM: range ≤ 5 % of the device total after 60 s in each active interval; repeat peaks vary ≤ 2 % as (max−min)/max.
- (c) Missing telemetry gives INCOMPLETE. Non-finite values, resets and errors give FAIL.
- (d) The defaults are recorded.
- Tests cover idle→PASS and active→FAIL.

**m1 CLOSED.**
- The lock records the Julia root `root_sha256` and the `expected_archive_sha256`.
- It requires a dedicated depot and records its Manifest-resolved tree SHA.
- HAGS is recorded but not required.
- The worker re-checks all of it in `local_julia()`.

**m2 CLOSED.** The filtered environment is recorded in `local_run.json` and in the run identity, the two must be equal (`:232`), and it is in `RUN_IDENTITY_KEYS`. See n1.

**m3 CLOSED.** One CUDA UUID is required across R1–R6, including a recorded R4. It is written to `gate.json` as `common_cuda_uuid`.

**m4 CLOSED.** `used_gpu_count` comes from the probe's `logical_device_count` (`bp:171`), and `verify_local` and the gate check it.

**m5 CLOSED.**
- `identity` is required; empty or foreign values are refused before any mutation.
- The docstring carries the `sim_step!` caveat.
- The CPU self-test passes 25 assertions, BITWISE, and its recorded source SHAs equal HEAD.

**m6 OPEN (accepted deferral).** The job's resume branch is exercised only by a real GPU R5. The report says so.

**m7 CLOSED.**
- C3 records the per-sample maximum relative difference at aligned steps. If steps are not aligned the sub-record is INCOMPLETE, with no interpolation.
- The anchors are derived: R3 54,771,184.79 and R4 50,729,748.45. I recomputed both, and they match §11.4. The SHAs are in the provenance.

**m8 CLOSED.** The bench records the lock SHA (required for GPU runs, including the native wrapper), the sampled VRAM peak and the TGV caveat.

**m9 CLOSED.** The gate is published by temporary file, fsync, then `os.link` (`:768`). An exception and a racing writer are tested.

**m10 CLOSED.** DONE without identity artifacts is FAIL (`:195`), and so is a missing resume event in R5.

**m11 CLOSED.** The artifacts are in `wp01_amendment3_validation/`. All 20 artifact SHAs and 42 intended-file SHAs match, and the committed file list equals the report's list.

**N1 CLOSED.** DEFAULT returns before the UUID fallback, and the original T4 error text is kept (tested).

**N2 holds.** The `.diff` reproduces `waterlily_local_gpu_job.jl` byte for byte. The only job change since e6c57e7b moves the identity check into `restore_checkpoint!`. Force columns, window and phase are untouched.

**N3 OPEN (procedural).** C2 still verifies against the current tree, so pinned files must be frozen from render to gate. The report keeps this rule.

**N4 unchanged** (spec-literal). **N5 moot.**

## New findings

**n1 MINOR (fix before the first run).**
- `RUNTIME_ENV_PREFIXES` includes `WSL` (`bp:24`), so `WSL_INTEROP` is captured. It is a per-terminal-session socket path (`/run/WSL/<pid>_interop`).
- That variable is compared through `RUN_IDENTITY_KEYS` in C1 (`gate:291`) and in C5 (`:457`, `:469`).
- If R1a/R1b, or R3, R5 and the interrupted run, start from different terminal sessions (likely over several days), the gate records a hard FAIL that has nothing to do with the environment.
- §11.5 does say `WSL*`. Keep recording the variable, but exclude a named volatile set from the comparison, or add a single-shell procedure rule.

**n2 MINOR.**
- Any active group with fewer than 2 samples after its first 60 s makes C6 INCOMPLETE (`:637`).
- One stray sample at ≥ 50 % utilization (probe or JIT), or a single dip that splits an interval, is therefore enough to block PASS permanently.
- §11.3(b) does not require this. Apply the VRAM rule only to intervals with ≥ 2 mature samples, require ≥ 1 such interval per repeat, and record the skipped groups.

**n3 NOTE (spec owner).** §11.3(c) makes a missing UUID or `power.draw` block PASS. On WSL2 with partial NVML, the case the LOCAL UUID fallback exists for, PASS becomes unreachable. Decide before the run whether the CUDA-probe UUID is enough identity for R6 telemetry.

**n4 NIT.** The watchdog CSV schema check was loosened from exact to subset (`:505`). A CSV without the `error` or `driver_reset` columns then degrades to INCOMPLETE. Require set equality.

**n5 NIT (report).** `finished_utc` in `full-pytest-result.json` and `source-stability.json` is 2026-11-07T09:07Z, but JUnit shows a start at 2026-11-06T09:00Z and 1923 s of runtime. The field holds the write time. Source stability shows before == after == HEAD (I checked 927 files, 0 mismatches), so 3651/74/0 holds for HEAD. Rename the field.

**Report honesty: OK.** 3651/74/0 = 3482 + 169 new; all 5 test files are new. The base result is honestly labelled as reused. The attempt-3 byte-identity claim is explicitly withdrawn (report, design note, `prior_t4_byte_claim_corrected`). Every claim I checked has an artifact.

## Verdict

**INTEGRATE_AFTER_FIXES.** All round-1 blocker and major findings are closed, with evidence I reproduced:
- the tool files are byte-identical to e3dcdf61;
- registered UNC-01 smoke and formal outputs re-verify byte-equal from the current tree;
- every freeze's tool hashes match;
- the guard test demonstrably catches edits to tool files and BASE_PINs;
- the local backend is confined to `backend_profiles.py` and `scripts/local_gpu.py`, with no monkeypatching.

The tooling can merge, but two small fixes belong before the first real R1–R6, because a spurious FAIL or permanent INCOMPLETE on the one-shot gate is costly:
1. n1: exclude `WSL_INTEROP` and other volatile session variables from the identity comparison, or add the single-shell procedure rule.
2. n2: stop marking C6 INCOMPLETE for short active groups.

Recommended: n4. The spec owner should decide n3.
