# Opus source review 1 of WP1 (PR #88, e6c57e7b), 2026-11-06

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions taken on it: `docs/local_gpu_env_gate_2026_11_01.md` §10 Amendment 2 and `01_local_gpu_01.md` Amendment 3.

# Source review: WP1 LOCAL-GPU-01 (branch feat/gen01-w1-01-local-gpu, HEAD e6c57e7b on e3dcdf61)

Read-only review. Ran the four new test files (88 passed); scratch scripts re-verifying registered UNC-01 U01 outputs at e3dcdf61, at HEAD, and at HEAD with only `campaign_schema.py` reverted; a tool-hash comparison against every registered freeze; `patch` of the `.diff`; and SHA checks of the validation artifacts. No Julia.

## A. Kaggle T4 contract preservation

**B1 BLOCKER: the default T4 contract is not byte-identical. Re-verifying registered evidence breaks at HEAD.**
`campaign_schema.py` is both a `BASE_PIN` (`campaign_build.py:20`) and a `TOOL_FILE` (`campaign_schema.py:404`). `campaign_build.py` and `campaign_verify.py` are also `TOOL_FILES`. The WP edits all three (`campaign_schema.py:38,244-246,344,349-360`, `campaign_build.py:76-77,134-136,176`, `campaign_verify.py:15,46-47,86-94,146-149`). Measured:
- At e3dcdf61, `verify` of UNC-01 U01 reproduces the committed `u01/state_force_table.json` and `u01/smoke/smoke_verify_table.json` exactly. Inputs: 3 formal kernels plus the prerun freeze, and the committed smoke.
- At HEAD, the formal table differs in `harness_tool_sha256` (schema, build and verify values). The smoke verification **fails**: `source commit or runner differs from the expected smoke rendering`. The cause is that `B.render` now bakes the new schema SHA into the PIN block. With only `campaign_schema.py` restored, smoke verification passes again and just the build/verify hashes drift.
- All 9 `docs/harness/*.prerun_freeze.json` files and the UNC-01, FID-01 and SCREEN-01 `freeze1.json` files record exactly the e3dcdf61 tool hashes. None match HEAD. `analyze_screen01.py:594` requires each table to carry freeze 1's tool hashes, and `screen01_freeze.py:83` requires the running tools to equal freeze 1's. A SCREEN-01 table re-verified at HEAD would therefore be refused.
- Every committed T4 kernel re-rendered from the current tree now differs, again through the PIN block.

The commit message and report say "keep the Kaggle T4 contract byte-identical", which is false. Amendment 2 §3 foresaw exactly this case ("失敗が出るなら schema の編集をやめ…") and named the fallback.

Fix (preferred):
- Restore the three tool files byte for byte.
- Move the local logic into `backend_profiles.py`:
  - `adapt_runner` also rewrites `SC.validate_campaign(campaign)` to drop `backend_profile`, and loads `backend_profiles.py` by path from the pinned checkout.
  - The module goes into the local campaign's top-level `pins` instead of a hook in `pins()`.
  - `render_local` builds the runner from `B.pin_block` and `B.pins`.
  - A `verify_local` reuses the harness checks with the local selector, probe and `gpu_name`.

Alternative: the user explicitly accepts the tool-hash drift as a recorded harness change, keeps `campaign_schema.py` restored regardless (the BASE_PIN breakage is avoidable), and documents that historical re-verification runs the tools at the freeze's source commit.

Either way, add a test that re-verifies the committed UNC-01 U01 smoke and formal outputs from the current tree and asserts byte equality with the committed tables.

**Checked and OK:** without `backend_profile`, `pins`/`render`/`refuse_legacy`/`validate_campaign` behave as before; default GPU selection delegates to the unchanged `grid01_gpu.select_worker_gpu` (identical logic; `scripts/` still reaches `sys.path` via the schema import fallback); the default `check_probe` expects the same dict; table key order and `harness_tool_sha256` keys are unchanged (values differ, B1); registered freezes still pass `validate_freeze`/`check_kernel`.

**N1 NOTE.** `backend_profiles.py:55`: the UUID fallback `selected["uuid"] or observed[...]` also applies to `kaggle_t4`. It is unreachable there, since grid01 requires a `GPU-` UUID, but should be limited to LOCAL. The T4 probe error text also changed. Profile strings are duplicated as literals in `campaign_build.py`/`campaign_schema.py` instead of using the `BP` constants.

## B. Local profile correctness and fail-closed behaviour

These are refused as they should be: legacy replay (schema, `create_local_campaign`, `render_local`), Kaggle build/smoke/freeze of a local campaign, a wrong GPU name, a probe that is not a singleton or has a mismatched UUID, a missing lock (exit 2), and different runner SHAs across C1 repeats (`RUN_IDENTITY_KEYS`).

**m1 MINOR. Lock identity is weaker than spec §2.**
- Julia identity is only the SHA of the `bin/julia` launcher (`capture_lock.py:164-170`, `backend_profiles.py:66-79`), not the install tree.
- `archive_sha256` is copied from the template constant, not measured. It reads like verification but is not.
- Hardware-accelerated GPU scheduling (HAGS) state is not recorded.
- The persistent local Julia depot is not bound (Kaggle starts with a fresh one).

Hash the Julia root with `SC.sha256_path` and pin a dedicated `JULIA_DEPOT_PATH`.

**m2 MINOR.** `local_gpu.py:252-255` passes the whole user environment to the runner and the job. `JULIA_LOAD_PATH`, `JULIA_CUDA_*`, `JULIA_PKG_*` and similar variables are neither scrubbed nor recorded, so C1/C5 identity cannot see them. Record a filtered snapshot in `local_run.json` and add it to `RUN_IDENTITY_KEYS`, or scrub them.

**m3 MINOR.** If the NVML UUID is unavailable, nothing ties R1–R6 to a single CUDA UUID. `local_gpu_gate.py:227-228` checks only when the lock UUID is a string. Require one CUDA UUID across all runs and record it in `gate.json`.

**m4 MINOR.** `used_gpu_count=1` is a literal written by the adapted runner (`backend_profiles.py:88-89`), so the verify and gate checks of it are tautological. The real evidence is the probe's `logical_device_count`; say so in the record.

## C. Checkpoint module

The saved state is sufficient for the standard WaterLily 1.8.0 path:
- `u⁰` is overwritten at the start of `mom_step!`.
- `p` aliases `pois.x`, and the restore uses `copyto!`, so the alias is kept.
- μ/V/L are rebuilt by remeasure, and `pois.n` is only a log.
- The full Δt history gives `time`.

The write is atomic (tmp + same-directory rename). Load validates header, schema, shapes, element type, the time–Δt consistency and trailing bytes, and fails closed. `restore_checkpoint!` checks the runtime/Manifest configuration and that the simulation is freshly built. The CPU 64×32 restart is BITWISE, and the artifact's source SHA equals HEAD's `Checkpoint.jl`. The job keeps the absolute-step sampling cadence and the endpoint-clipped window.

**m5 MINOR.** `Checkpoint.jl:68,112-123`: `identity=""` is the default and `restore_checkpoint!` never compares the identity, so a WP4 caller can silently resume a foreign checkpoint. Make the identity mandatory and pass the expected value to load/restore. Also document for WP4 that `length(Δt)==step+1` assumes one `mom_step!` per counted step, which does not hold for `sim_step!(sim,t_end)`.

**m6 MINOR.** The job's resume branch (identity hash, history and step continuation, resume-event JSON) is untested until the real R5. GPU restart across processes is unverified, as the report states.

## D. Job variant

**N2 NOTE.** The `.diff` is an exact delta: `patch` on the registered job reproduces `waterlily_local_gpu_job.jl` byte for byte, and the test checks it against difflib output. The changes are the `Base.include` of `Checkpoint.jl`, the checkpoint hooks, and one non-hook change (the usage string). Force semantics, CSV columns and order, window, phase mechanism and hash checks are untouched, and a test guards those ranges. The checkpoint goes outside the kernel output (`CAMPAIGN_WORK_ROOT`), and the resume event goes inside it, where it is hashed.

## E. Gate and bench

The record is written once (`open("xb")`). Missing inputs give INCOMPLETE. C1 and C5 follow the spec, including bitwise floats for the BITWISE class. Thresholds 1e-6, 5.5e7/5.6e7 and 21600 s match the spec.

**M2 MAJOR: the PASS rule differs from spec §5.** `local_gpu_gate.py:544-546` lets a FAIL or INCOMPLETE in C3/C4 block PASS. The spec says PASS = C1 ∈ {BITWISE, TOLERANCE} and C2, C5, C6 pass; C3/C4 are descriptive. So a failed or missing R4, or a reference-identity mismatch in C3, would turn a passing environment into FAIL or INCOMPLETE. Exclude C3/C4 from the status and report them separately, or amend the spec before freezing the comparator.

**M3 MAJOR: C6 cannot be run as specified.**
- (a) Clock drawdown is taken over every sample, including the idle cold start of each repeat (git fetch, `Pkg.instantiate`, JIT) (`:476-480`). A normal R6 will very likely exceed 15 % for a non-thermal reason; the report admits this. The synthetic PASS test hides it: a constant 2000 MHz clock and a solver share of 2/21600.
- (b) The spec's "VRAM stable" condition is never evaluated (`:520-521`), so C6 passes even with a leak.
- (c) One NVML field missing on WSL2 (e.g. `power.draw`) makes every row an error, which gives FAIL (`:462,466`) rather than INCOMPLETE.
- (d) The 90 s gap and 60 s first-sample allowances have no source.

Fix: amend the spec and code before the freeze. Measure the drop only over solver-active samples (query `utilization.gpu`, or join on solver intervals), define a VRAM rule (or return INCOMPLETE until one exists), and make the optional telemetry fields optional.

**m7 MINOR.**
- C3 omits the per-sample maximum relative difference against T4 that spec §4 requires.
- The f48 anchor 5.6e7 disagrees with the gate's own formula applied to its C3 reference f48k13 (26360 × 4,665,600 / 2424.3 s = 5.07e7; f32a gives 5.48e7, consistent). Derive the ratio from the reference summary or cite where the anchor comes from.

**m8 MINOR.** The bench output has no lock SHA and no VRAM (`local_gpu.py:413-419`, `local_gpu_bench.jl:125-133`). R0 uses a custom TGV, not WaterLily's benchmark suite, so comparisons with published ns/DOF anchors need that caveat.

**m9 MINOR.** `write_gate` reserves `gate.json` before evaluating (`:563-566`). An unexpected exception outside `part()` leaves a 0-byte file that uses up the one-shot gate. Write to a temporary file, then link with exclusive create.

**m10 MINOR.** If a run has DONE but lacks e.g. `run_identity.json`, `Missing` makes it INCOMPLETE. Contradictory evidence like this should be FAIL.

**N3 NOTE.** C2 runs `verify --smoke` against the current tree. Any commit that touches a pinned file between render and gate (BASE_PINS, `backend_profiles.py`, the job) makes C2 FAIL. The procedure must freeze those files, or verify at the source commit.

**N4 NOTE.** C1's relative test has no absolute floor (`max(…,1e-300)`), so it is ill-conditioned on near-zero side-force columns (`fy`, `pressure_fy`, `viscous_fy`). Spec-literal; the spec owner may want a floor.

## F. Tests and report honesty

**M1 MAJOR: the tests are structurally blind to B1.**
- The byte-identity proof (`test_local_gpu_backend.py:36-60`) renders from a `git archive` of the historical source commit, so a change to a BASE_PIN in the current tree cannot show up.
- No test re-verifies a committed registered table. `test_unc01` per-kernel verify (the JOB-02 freeze with real outputs) compares only `state_forces_n`, and the replay test uses a synthetic freeze.
- The gate tests monkeypatch C2.

The "486 focused / identical full suite" result is real but does not support the byte-identity claim.

**m11 MINOR.** The focused regression "486 passed / 1 skipped" has no log or junit artifact. The full and new pytest logs exist only under `/private/tmp/wp01-validation-attempt3`; their SHAs match `validation.json` today, but the location is temporary. The counts are consistent: 3482 → 3570 = +88 new tests, and the 3482 base matches the host baseline commit 39cf0284. All 28 intended-file SHAs in `validation.json` equal the committed blobs.

**N5 NOTE.** `/private/tmp/wp01-base-e3dcdf61/.git` links to the WP worktree's gitdir, so its HEAD now reads e6c57e7b though its tree is e3dcdf61. Harmless for the recorded run; misleading if reused.

## Verdict

**INTEGRATE_AFTER_FIXES.** The local tooling is careful and mostly fail-closed: lock capture, renderer hooks, wrapper, checkpoint module, job copy and most of the gate. The checkpoint design is sound. The branch must not merge as is, because it silently changes the registered T4 contract: committed UNC-01 smoke evidence no longer re-verifies, and the tool hashes of every registered freeze go stale. Required fixes:
1. B1: restore `campaign_schema.py`, and preferably `campaign_build.py`/`campaign_verify.py`, byte for byte, with the logic moved to `backend_profiles.py`. Otherwise get a recorded user decision accepting the build/verify hash drift, with a procedure for re-verifying history.
2. M1: add a regression test that re-verifies committed UNC-01 U01 smoke and formal outputs and asserts byte-equal tables. Correct the byte-identity claim in the commit message and report.
3. M2: align the gate's PASS rule with spec §5.
4. M3: fix C6's clock and VRAM rules and telemetry optionality, through a spec amendment, before the gate script is frozen.

Recommended before the first run: m1–m3, m5, m9.
