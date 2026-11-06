# Opus source review 1 of WP3 (PR #86, e2dddf06 / impl 05138c72), 2026-11-06

Reviewer: Claude Opus subagent, read-only, briefed by Claude (Fable 5.1). Verbatim. Decisions taken on it: `docs/grad00_lambda_swap_spec_2026_11_01.md` Amendment 2 and `03_grad00.md` Amendment 3.

# WP3 (GRAD-00 λ swap) source review — feat/gen01-w1-03-grad00 @ e2dddf06 (impl 05138c72), Draft PR #86

Read-only review. Commands I ran: the four GRAD-00 test files (175 passed); `grad00_reference_from_fd08.py --check` (exit 0); I applied the `.diff` to frozen TA1 with `patch` and compared the result to the job; I re-rendered the five kernels at 05138c72 into the scratchpad and compared them to the committed renders; I probed the analyzer with adversarial inputs; I ran a scalar Julia check of `vanLeer_safe` against stock `vanLeer`. No repository file was modified.

## Findings (most severe first)

### BLOCKER

**B1 [C/D]: The analyzer cannot produce `analysis.json` for the expected outcome of arm D, or for any arm that ends in an error. The analyzer's bytes are pinned in the kernels, so this has to be fixed before any push.**
- Arm D is expected to fail its preflight on the T4 (Amendment 1 §2). The chain from there:
  - The job then sets `INCOMPLETE` and exits 2 (`waterlily_grad00_lambda_2026_11.jl:448-450,481`).
  - The runner turns exit 2 into `ERROR.txt` and writes no `DONE` (`infra/kaggle/kernel_grad00_vanLeer/runner.py:184-185`).
  - `verify_output` rejects that output because it needs `DONE` (`analyze_grad00.py:284`), `spike_exit_code ∈ {0,3}` (`:294`), status `COMPLETE`/`BLOCKED` (`:322`) and a passing preflight (`:325`).
  - `analyze_campaign` verifies every directory present (`:469`) and requires all four primary CUDA arms A–D (`:473`). Analysis is therefore impossible both with D present and with D absent.
- The same applies to:
  - a cds primal blow-up (`error("non-finite primal force")`, job `:229`). Spec §3 says this should be "recorded".
  - a Dual wall abort.
  - a failed or partial D′ run. The spec separates `NOT_RUN` from `INCOMPLETE`, which implies `INCOMPLETE` is a label; here it is a refusal of the whole campaign.
- Amendment 1 §2 says D is "labelled by the rule". The code has no representation for that.
- The tests never model the real outcome. The D fixture is a synthetic BLOCKED_ALL with `DONE` (`tests/test_grad00.py:252-268`, `fixture(..., blocked=A.DIRECTIONS)`), and `:471` only asserts the refusal. The report admits the gap (`wp03_report.md:203`) but leaves it open.
- **Why it blocks the push:** `_source_identity` refuses any output whose pinned `scripts/analyze_grad00.py` differs from the running analyzer (`analyze_grad00.py:198-199`). All five runners pin `992c7073…`. Fixing the analyzer after the runs would leave every arm unverifiable.
- **Fix.** Claude decides the semantics, then the analyzer implements them. Minimal option: accept a terminal non-success arm as an arm-level label, e.g. `PREFLIGHT_BLOCKED`, when the run is authenticated through `output_manifest.json` and `run_identity.json` and the failure is exactly one of these:
  - the preflight's `selected_dual` tangent is non-finite while the primal is finite and the lambda routing is OK (D); or
  - an index `ERROR`, labelled `INCOMPLETE`.
  The fix should also:
  - make such arms not eligible for the next step;
  - stop refusing the whole campaign because of one failed arm;
  - add a fixture that reproduces the real D output (`ERROR.txt`, exit 2, `preflight.pass=false`).
  - Then re-render and re-pin the kernels.

### MAJOR

**M1 [C]: D′ is excluded from `GRAD01_DRAFT_ALLOWED`, contrary to Amendment 1 §2 ("joins B–D as a candidate").**
- The code: `NEXT_STEP_ARMS = PRIMARY_ARMS[1:]` (`analyze_grad00.py:32-34`) and `eligible = index["arm"] in NEXT_STEP_ARMS …` (`:503`).
- The test `tests/test_grad00.py:512-524` asserts the wrong result: D′ with BOUNDED_ALL and 4/4 AGREE still gives `GRAD01_DRAFT_NOT_ALLOWED`.
- The report says it deliberately kept B–D (`wp03_report.md:142`).
- Root cause: the WP3 worktree's spec is rev 0 only (`grep -c "Amendment 1"` returns 0), so Codex never saw §2's candidate clause.
- Fix:
  - set `NEXT_STEP_ARMS = ("quick_nobound","cds","vanLeer","vanLeer_safe")`;
  - flip the test;
  - keep `NOT_RUN` as not eligible.
- This also changes the pinned analyzer bytes, which is another reason to re-render.

### MINOR

**m1 [C]: Per-direction precedence lets `NOT_EVALUABLE` hide an evaluable disagreement.**
- `analyze_grad00.py:498` labels "fx DISAGREE + fz NOT_EVALUABLE" as `NOT_EVALUABLE`.
- Spec §5 is ambiguous about precedence. Suggested rule: DISAGREE if any evaluable component disagrees; otherwise NOT_EVALUABLE if any component is not evaluable.
- No effect on the next-step rule, which counts only AGREE.

**m2 [B/E]: Side arm E has no T4 kernel.**
- Amendment 1 §4 budgets "E +1 h" of T4, and the report's budget table lists E at "約1 T4 h" (`wp03_report.md:241`).
- But the builder renders only the five 1.8.0 arms (`build_grad00_kernels.py:25`), and E can only run through the CPU launcher (`run_grad00_cpu.py:27,67`).
- As wired, E is a full-window CPU Float32 run on the Mac with 13 runs and no budget. Either add an E kernel on `julia/CFDSDFWaterLily110` (whose CUDA 6.3.1 / ForwardDiff 1.4.5 / WaterLily =1.10.0 pins are already correct), or re-budget E as CPU.

**m3 [F]: The CPU Float32 control for arm F runs all four directions (13 runs), although F compares only D0/D1.**
- Code: `ACTIVE_DIRECTIONS` is restricted only for Float64 (job `:54`, `run_grad00_cpu.py:40`, analyzer `:316`, `:518-519`).
- This roughly doubles the control's cost against the 60 CPU h cap.
- Fix: a D0/D1-only Float32 CPU control mode, or state that the T4 Float32 arm is the control (which keeps the cross-backend confound).

**m4 [E]: An unreported Float64 anomaly.**
- After 20 steps, the Float64 Dual `max_abs_tangent_p` is about 3.30e6 for both A and B (`amendment2/CFDSDFWaterLily_{quick,quick_nobound}_Float64/preflight.json`).
- In Float32 it is 33.7 / 31.4; the u tangents are comparable across precisions (23.9 vs 25.1).
- The report's table (`wp03_report.md:162-171`) shows only PASS.
- This bears directly on how arm F should be read: the p watchdog could block F for reasons unrelated to the limiter, for example pressure null-space or solid-cell drift.
- It should be reported, and ideally localised (argmax cell), before spending up to 60 CPU h.

**m5 [C, process]: `analysis.json` is written once and must include every arm present.**
- The rules: write-once (`:544-554`), every present arm verified (`:469`).
- Consequence: the single `--write` has to wait for the D′ decision, E, and F (60 CPU h). A later arm can never be added.
- The runbook should say to use `--check` for the B/C → D′ decision and to `--write` only at the end.

### NOTE

- **n1 [A]: The job's quick "bit-equal" check is a self-comparison.**
  - It compares control `("quick", WaterLily.quick, DT)` with `selected_dual` (same λ, same DT, same build; job `:291`, `:320-321`), and the analyzer requires it (`:326-327`, `:346-347`).
  - So it tests determinism only.
  - The real comparison with TA1 is `amendment2/ta1_bit_comparison.json`, and it is genuine:
    - the frozen TA1 bytes are loaded with `include_string` into a separate module;
    - both the Dual path (quick λ, TA1's `build`) and the Float32 plain path are compared;
    - u and p SHAs are equal in both.
  - It is CPU-only. On the T4 it cannot be repeated, because TA1's preflight recorded no field hashes.
  - Suggest renaming the fields to `determinism_*` so nobody reads them as a TA1 replication.
- **n2 [A]: The `.diff` is exact.**
  - `patch` applied to TA1 reproduces the job byte-for-byte. The `diff -U0` output from macOS's diff differs from the committed file only in hunk alignment.
  - Every change is in the permitted set:
    - arm/λ routing through the constructor, with the unchanged `typeof(sim.flow.λ)` hard check;
    - the 13-run plan, with ±ε runs after each Dual so a BLOCKED Dual still yields FD;
    - plain runs re-done under the selected λ (spec §4, whereas TA1 used `quick`);
    - the Float64 CPU gate;
    - the preflight extension.
  - Window, sampling, `>1e30` limit, 100-step watchdog, 8× wall abort, error propagation and index names are unchanged. Force semantics (`-(p+v)`, Fx, −Fz) are unchanged.
  - Harmless extras outside the list: the `main()` guard (`:484`, fails closed), the DeviceGridSDF label (`:96`), and report-only terminal-tangent fields (`:267-276`).
- **n3 [B]: λ definitions.**
  - `quick_nobound` is the #358 expression. It lacks stock `quick`'s `@fastmath`, so small primal contraction differences are not attributable to the bound.
  - `vanLeer_safe` plain:
    - The guard fires only when `u == d`, where stock already returns `c`.
    - My scalar probe gave `===` with stock for (1,1,1), (0,1,−0), (1,−2,1) and NaN.
    - Bit-identity in a fused `@fastmath` GPU kernel cannot be proven a priori. It is checked at runtime by the T4 `vanLeer_plain` preflight, which the analyzer enforces (`:328-329`, `:348-350`).
  - `vanLeer_safe` Dual:
    - The guard compares values only, so the tie gives c's tangent: (1,2) where stock gives NaN.
    - At c==u≠d or c==d≠u, ForwardDiff 1.x's lexicographic `≤` takes the interpolation branch: 2c′−u′ or d′. That is finite and the same as stock.
    - At monotone near-ties ab/(a+b) has partials in [0,1], so no blow-up.
- **n4 [B]: `LAMBDA_TYPES` strings.** They rely on how Julia prints types in Main. They are confirmed on Julia 1.12.6 for 1.8.0 and 1.10.0, and fail closed. The test at `tests/test_grad00.py:200` is tautological.
- **n5 [D]: `verify_source`.**
  - It refuses dirty pinned files but does not check that the commit is on GitHub.
  - 05138c72 is on `origin/feat/gen01-w1-03-grad00` and must stay reachable (no squash or delete) until the runs finish.
- **n6 [D]: D′ gating.**
  - The D′ kernel can be pushed now; its run condition is human-enforced only.
  - The worst case per arm, set by the 8× wall abort, is about 2 h, so A–D′ is at most about 8–10 h, at the cap.

## Checked with no finding

- **Reference** matches Amendment 1 §1. I recomputed it independently:
  - ε = max{0.629, 1.581, 3.9716} mm for all four directions;
  - spread = Model A `se_g_n_per_m`, fx from drag, fz from downforce;
  - source SHAs `3da59ac9…` and `31b29ccc…`.
- **Analyzer.** The FD is (plus − minus)/(2ε) on `dual_time` window means, with consistent units.
  - Adversarial inputs:
    - finite tangent 1e29 gives BOUNDED, then DISAGREE;
    - a watchdog maximum of exactly 1e30 is BOUNDED; above 1e30 is refused;
    - |FD| exactly 3×spread is evaluable; one ulp below is NOT_EVALUABLE;
    - a ratio of exactly 0.9 or 1.1 is AGREE; 1.1000001 is DISAGREE;
    - a sign flip, or a zero tangent, is DISAGREE.
  - Exclusive-create write with a SHA sidecar; refusal on reference or pin mismatch; an absent D′ directory gives NOT_RUN.
- **Kernels.**
  - The five renders are byte-reproducible at 05138c72 (tree `b0f4915b…`), and e2dddf06 touches only `infra/`.
  - Pins include the reference and its sources.
  - Metadata is identical to TA1's (T4, internet on, no sources, private) except id and title. Timeout is 10800.
  - CPU-only env switches are removed. There is no push, and each runner runs only its named arm.
- **1.10 project.**
  - WaterLily =1.10.0 (`pinned`), ForwardDiff 1.4.5, CUDA 6.3.1.
  - λ is still a Flow field, and `measure!` still dispatches to the Candidate-C override.
- **Report claims** all match artifacts:
  - 104+37+29+5 = 175 tests;
  - full suite 3657/74/0, which equals the host baseline 3482 plus 175;
  - walls and exits; the job SHA at run time equals the pin `b7b305…`;
  - D′ tangents 24.48 / 32.07;
  - 1.10 instantiate with SHAs unchanged;
  - `COMMIT_FILES.txt` = the 92 files of 05138c72.
  - CPU 20-step results are never phrased as window or GPU results.

## Verdict

**INTEGRATE_AFTER_FIXES.** The job, the reference, the builder and the runner are sound. The `.diff` is the exact delta, and the bit comparison against TA1 is a real cross-script check. Fixes required before integration:

1. B1: give the analyzer, and its tests, a labelled terminal state for a preflight-failed or errored arm, D and a failed D′ included, so that the campaign is not refused.
2. M1: add `vanLeer_safe` to the next-step candidates and flip `test_grad00.py:512-524`.
3. Recommended: m1 (precedence), m2 (E kernel or re-budget), m3 (F control scope), and report m4.

Then commit, re-render the five kernels pinned to the new commit, and re-run the focused tests.

**Kaggle push of the current kernels: no.** All five runners pin `scripts/analyze_grad00.py` at `992c7073…`, and the analyzer refuses any output whose pinned analyzer differs from the running one (`analyze_grad00.py:198-199`). Arm outputs produced now would therefore be bound to an analyzer that cannot label arm D's expected preflight failure (B1) and excludes D′ from the next-step rule (M1). Fixing either afterwards would leave every arm's output unverifiable. Arms A/B/C would execute correctly, but their outputs would be unusable.
