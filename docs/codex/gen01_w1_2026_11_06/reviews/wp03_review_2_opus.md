# Opus source review 2 of WP3 (PR #86, b1737bf3 / impl da28dba4), 2026-11-07

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Verdict INTEGRATE_AS_IS; kernels safe to push (A–D now, D′ after `--check`). Decisions: `docs/grad00_lambda_swap_spec_2026_11_01.md` Amendment 3 (runbook rules).

# WP3 (GRAD-00) source review, round 2: feat/gen01-w1-03-grad00 @ b1737bf3 (impl da28dba4), PR #86

This review was read-only. I modified no repository file and ran no git command that writes. What I ran:
- The four GRAD-00 test files: **203 passed** (132 analyzer + 5 reference + 37 builder + 29 CPU).
- A scratchpad re-render of the five kernels at da28dba4, compared to the committed renders with `diff -r`.
- `patch` of the `.diff` onto the frozen TA1 job, then `cmp` against the GRAD-00 job.
- `SHA256SUMS` (154 entries) and the 228 protected-file SHAs.
- `git ls-remote` on the feature branch.
- Two probe scripts (`scratchpad/wp03r2_probe/`). They reuse the test fixtures, with the real attempt-3 D preflight record substituted in.

## Round-1 findings

| ID | Status | Evidence |
|---|---|---|
| **B1** | **CLOSED** | See "How B1 is closed" and the probe table below. |
| **M1** | **CLOSED** | `NEXT_STEP_ARMS` includes `vanLeer_safe` (`:33`). Terminal-state and NOT_RUN arms are not eligible. The test at `tests/test_grad00.py:573-584` asserts that D′ BOUNDED_ALL with 4/4 AGREE gives `GRAD01_DRAFT_ALLOWED`. Probe S14 gives the same result with D PREFLIGHT_BLOCKED and B/C blocked: eligible = `['vanLeer_safe']`. |
| **m1** | **CLOSED** | Direction precedence is DISAGREE > NOT_EVALUABLE > AGREE (`:637`). The test at `:703` checks that fx DISAGREE + fz NOT_EVALUABLE gives DISAGREE. |
| **m2/m3** | **CLOSED** | The job, the analyzer and the CPU launcher all restrict CPU runs to D0/D1, which gives 7 runs for E, F and the Float32 controls: job `:55`, analyzer `:452`, `run_grad00_cpu.py:48`. E is accepted only as a CPU arm (`:449`; launcher `:71-72`). The builder still renders only the five T4 arms, so there is no E kernel. |
| **m4** | **CLOSED** | The preflight records the u and p argmax, or the first non-finite cell (job `:290-311`, `:340-341`). Each record holds the index, signed value, staggered and world position, candidate SDF, ground distance, halo flag and boundary clearance. All 8 report rows match the records. F-A and F-B both show p ≈ −3.30e6 at [75,49,27], with SDF −0.050 m (inside the body), not halo, and 0.82 m from the nearest boundary. The report gives no cause. |
| **m5** | **CLOSED** | `--check` prints `vanLeer_safe_run_condition` (`met`, `human_run_decision_required`, `basis`) and writes nothing (`:656-660`, test `:731`). `--write` is exclusive-create, and a second write is refused (probe S1). The runbook is at `wp03_report.md:114-170`. |
| **n1** | **CLOSED** | The fields are renamed `determinism_primal_{u,p}_bit_equal`, and the analyzer requires them (`:332`, test `:786`). The new records contain no old keys. |
| n2–n6 | No action needed | The λ helpers, `LAMBDA_TYPES` and the builder are unchanged. da28dba4 is an ancestor of the GitHub tip b1737bf3. D′ gating is computed by `--check` and decided by a human. |

### How B1 is closed

- `verify_output` requires exactly one of `DONE` and `ERROR.txt` (`analyze_grad00.py:415`).
- An authenticated ERROR output goes to `_failed_output` (`:350`).
- `PREFLIGHT_BLOCKED` (`:395`, using `_check_preflight` at `:304`) requires all of the following:
  - preflight `pass` is false;
  - `selected_plain` is finite;
  - λ routing is correct;
  - the `selected_dual` tangent is non-finite;
  - the index status is `INCOMPLETE` with exit 2;
  - no runs were saved.
- Every other authenticated failure is `ARM_ERROR` (`:359`).
- Final analysis requires only that A–D each have an authenticated terminal output (`:600`).

### Probe results

| Probe | Constructed output | Label | `analysis.json` writable |
|---|---|---|---|
| S1 | Real-D-shaped: the real attempt-3 D preflight and progress records, ERROR.txt, exit 2, `failure_stage=measurement`, runner logs, and an identity containing only the T4 runner's fields | **PREFLIGHT_BLOCKED**; D′ and E are NOT_RUN; `met=true` | yes (a second write raises FileExistsError) |
| S2, S2c | Forged: a byte appended after the manifest was written, or a bad manifest digest | refused ("output SHA mismatch") | no |
| S2b | Forged source commit, with the manifest rewritten to match | refused (`_source_identity`) | no |
| S11 | `pass=false` but the Dual tangent is finite | **ARM_ERROR** | yes |
| S3 | Partial D′ (3 runs saved, then ERROR) | **ARM_ERROR** | yes |
| S4 | Wall abort in C after the plain run | **ARM_ERROR** | yes |
| S7 | Failure in `julia_installation`: pins verified, no index | **ARM_ERROR**, runtime null | yes |
| S6 | Failure in `gpu_inventory`: no verified pins | refused (unauthenticated, as intended) | no |
| S8 | Hard kill: neither DONE nor ERROR.txt | refused | no |
| S9 | Failed D plus a re-run D directory | refused (duplicate identity) | no |
| S5, S10 | see N1 and N3 | refused | no |

## New findings

**N1 (minor): an authenticated failure before CUDA identity capture is refused instead of being labelled ARM_ERROR.**
- `verify_output` checks `cuda_jl == 6.3.1` and `"Tesla T4" in gpu_name` (`:442`) before it branches to `_failed_output` (`:465`).
- The job records both values inside its try block, via `CUDA.name(CUDA.device())` (job `:451-452`).
- If CUDA initialisation throws, the output is an authenticated ERROR transport (verified pins, manifest, exit 2) whose index lacks both fields. Probe S5 confirms that the whole campaign is then refused.
- This deviates narrowly from Amendment 2 §1 ("any other authenticated failure"). It fails closed, and re-running that arm recovers it without changing the analyzer.
- Not push-blocking. If the analyzer is edited before the push for another reason, include a fix: skip that check in the failed branch when the fields are absent.

**N2 (minor, runbook): there is no re-run rule and no pinned-analyzer rule.**
- Re-run rule:
  - Because duplicates are refused (S9), a re-run requires moving the earlier output out of `OUTPUT_ROOT`.
  - Without a pre-declared rule, re-running an authenticated ARM_ERROR cannot be told apart from re-running until a good result appears.
  - Suggested rule: authenticated PREFLIGHT_BLOCKED and ARM_ERROR outputs are final. Unauthenticated outputs (the S5, S6, S8 and S10 shapes) are archived outside the root and re-run once, and the re-run is recorded.
- Pinned-analyzer rule:
  - `_source_identity` requires the host's `analyze_grad00.py`, `grad_g2_window.py` and `verify_grad_g2_terminal.py` to equal the da28dba4 pins (`:197-198`).
  - If any of them changes after integration, `--check` and `--write` must run from a da28dba4 checkout.
- Both rules are documentation only; no pinned bytes change.

**N3 (note):** the job writes its JSON indices non-atomically (truncate, then write; job `:370`). If the runner's `SCRIPT_TIMEOUT_S` kill lands mid-write, the index is unreadable and the campaign is refused (S10). The write window is milliseconds, and N2's re-run rule covers recovery.

**N4 (note):** the code reads Amendment 2 §1's "finite primal" as `selected_plain`. In the real D record, `selected_dual.primal_finite` is false too. The report says so. A one-line spec clarification would stop readers taking PREFLIGHT_BLOCKED to mean that the Dual primal stayed finite.

**N5 (note):** an absent F gets no `NOT_RUN` entry (`precision_differences` is simply `{}`). Only D′ and E get one (`:649-655`). This matches the spec, but an explicit entry would make the final analysis self-describing.

## Kernels and regressions

**Kernels:**
- All five runners pin `SOURCE_COMMIT da28dba4…` and tree `092a2a1f…`.
- The pinned `analyze_grad00.py` SHA, `da285236…`, equals the file at HEAD.
- b1737bf3 touches only the five runners.
- The scratchpad re-render is byte-identical for all five.
- Against the e2dddf06 renders, only the analyzer and job pins changed.
- Metadata matches TA1 except id and title. The timeout is 10800.
- The runners set `G2_BACKEND=cuda` and pop all four dry-run switches. No CPU-only environment settings leak through.

**Regressions:**
- The job changed in only three ways: the CPU `ACTIVE_DIRECTIONS`, the report-only preflight localisation, and the `determinism_*` rename.
- These are unchanged: the window, sampling, `>1e30`, the watchdog, the 8× wall abort, force semantics, the thresholds, and `compare_row`.
- These have no diff: the TA1 job, `grad_g2_window.py`, `verify_grad_g2_terminal.py`, both λ helpers, the template and builders, the Julia projects, and the reference.
- The complete-output preflight checks are equivalent to the old inline code.
- **The `.diff` applied to frozen TA1 reproduces the job byte for byte.**

## Report honesty

Every claim I checked holds:
- 203 focused tests, with the per-file counts above.
- The full suite gives 3685 passed / 74 skipped / 0 failed, `failed_nodes: []`, which equals the baseline 3482 plus the 203 focused tests.
- The 228 protected files are unchanged at da28dba4. Since then, only the five host-re-rendered runners differ.
- `SHA256SUMS` verifies.
- `COMMIT_FILES.txt` equals da28dba4's 164 files.
- The preflight table matches all 8 records.
- CPU 20-step results are never presented as T4 or registered-window evidence.

## Verdict

**INTEGRATE_AS_IS.** Every round-1 finding is closed in code and tests:
- authenticated failures get terminal labels, and forged outputs are refused;
- a campaign containing a real-D-shaped output completes;
- D′ is a next-step candidate;
- `--check` computes D′'s run condition;
- the kernels, the `.diff` and the frozen semantics do not regress.

What remains is documentation in the authority docs (N2, optionally N4 and N5), which touches no pinned bytes. N1 is worth fixing only if the analyzer is edited again before the push.

**Can the re-rendered kernels be pushed to Kaggle as they are? YES.**
- Push A–D now.
- Push D′ only after `--check` reports `met=true` and a human decides to run it.
- Keep da28dba4 reachable on origin.
- Run the analyzer from a tree whose three consumer files equal the pins.
