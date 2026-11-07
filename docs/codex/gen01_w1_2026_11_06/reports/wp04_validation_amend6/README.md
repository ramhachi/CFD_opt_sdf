# WP4 Amendment 6 validation and handoff

These artifacts record software regression and short CPU capability checks at
task-start commit `0741a474`. They do not freeze the study or qualify a GPU,
TR-00, RANS, physical downforce, grid independence or Reynolds-number transfer.
Claude owns the later host commit, push and PR #89 update. Earlier validation
directories remain historical records of their own source bytes.

The applicable authority is registration Amendment 7 and round-2 Opus review
in the read-only follow-ups worktree. The job, Julia helper, selftest, geometry,
scene JSONs, protected source closures and historical evidence are unchanged.
Only focused Python tests and the CPU Julia selftest are required this round;
the full pytest suite is deliberately not run under user Amendment 6 item 5.

## Result and records

Status: **PARTIAL**. Focused pytest: **314 passed / 1 failed**. Julia CPU
selftest: **86/86 passed**. The sole failure is the AR(1) true-W=50 median
acceptance condition: median W=100 (2x), despite zero refusals. The registered
estimator, constants, seeds and assertion remain unchanged while the requested
clarification is pending. True W=100 and150 give medians150 and200.

- `authority.json`: exact read-only registration/review hashes and worker route.
- `targeted_execution.json`, `targeted_junit.xml`, `test_summary.json`:
  command, duration, before/after source hashes and the complete failure set.
- `ar1-results.json`, `ar1_summary.json`: all600 per-seed windows, exact
  stationary AR(1) parameters and aggregate acceptance checks.
- `prerun-independent-audit.json`: independent clipped-trapezoid arithmetic,
  20 irregular histories and540 comparisons, distinct from static review.
- `cpu_execution.json`, `cpu_source_verification.json`, `cpu_selftest/`:
  branch-local WP1, current source bindings, cur-only provider, raw CPU force
  histories and the expected exit42/NUMERICAL negative test.
- `cpu_checkpoint_exclusion.json`: size/SHA of the generated artificial
  checkpoint buffer excluded from the host commit. Its receipts are retained.
- `compileall_execution.json`, `protected_source_closure.json`: compilation
  and unchanged protected paths/source closure, without claiming a full replay.
- `development_review.json`: independent static review; this is development
  review evidence, not the preregistered source approval or a new Opus ruling.
- `*.log.gz`, `log_archives.json`: deterministic gzip logs with raw-byte SHA.
- `wp04_pending_files.json`: every intended host commit path, including the
  negative-test receipts; flags any ignored path for explicit staging.
  This run has no ignored intended paths and no moves/deletions.
- `SHA256SUMS`: all validation artifacts except this manifest.

## Parent pre-run estimator (supersedes Amendment 5 runbook)

Run the two hash-bound E1/main/phase-0 parent states for 520 c1/U after the
externally owned source review, geometry verification, freeze and backend gate.
No parent pre-run or formal GPU work is performed by this change.

`scripts/topo2d00/prerun_window.py SERIES SUMMARY` writes its target once
(`docs/harness/topo2d00_window_re<Re>.json` by default). Force units are N/m
with rho=1 and U=1; time is c1/U; S0 units are (N/m)^2*c1/U. Candidate starts
are the first sample time plus 50 k. Compare each 100-wide candidate mean with
the remaining mean using twice the remainder's batch-means SE at length 20.
Use the earliest accepted start with B=max(80,start), or B=130 and
`BURN_IN_FALLBACK` if none qualifies. S0 is the maximum point estimate
L*sample_variance(batch means) for L=10,20,40 after B. W is the smallest
50 multiple meeting the 1.5% target, clipped at 400 with `WINDOW_CAPPED`.
All candidates, flags, formula constants and raw SHA bindings are recorded.
Formal admission re-hashes and recomputes this record; manual B/W values
remain forbidden. Clipping is reported even if the requested SE is unattainable.

The existing pre-run/formal selection and solver time caps remain as documented
in the previous runbook. Formal analyses use the same verified force table,
raw reference and freeze requirements. An incomplete, timed-out or single-phase
DOMAIN control reports `DOMAIN_NOT_JUDGED` and does not block the study label.
Actual nonfinite solves and explicit study-wide cap hits retain their registered
precedence. Ranking requires Delta13 on both sides whenever either point order
is non-monotone; a noise-level required ordering is `UNRESOLVED`.

## Future GPU capability smoke (user equipment only; not executed here)

- Invoke `scripts/waterlily_topo2d_job.jl` directly using the T4 Julia project,
  `TOPO2D_BACKEND=cuda`, `TOPO2D_SMOKE=1`, actual selected device UUID and
  job/scene SHA bindings, after the externally owned backend/source checks.
- Start from a clean job/device environment and scratch output. Run E1 then
  E3 (largest tuple), at the declared formal grid for a few hundred steps.
- Record source/scene/runtime/device identities, compilation time, acceptance
  of the approximately 15.7 KB tuple kernel parameter, and `measure!` and
  `mom_step!` wall milliseconds per step. The job keeps `remeasure=false`.
- Also record **wall milliseconds per force sample**, measured around the
  force-readout call with GPU synchronization before and after timing. Record
  sample count and total elapsed sampling time, distinguish compilation and
  warm-up from steady-state samples, and include per-element integrations.
  Dividing total solver time by sample count does not isolate this cost.
- Compare finite forces with the CPU reference and record the differences.
  CUDA checkpoint restore, full-window behavior and GPU performance remain
  unverified. This smoke is capability evidence only and supplies no new
  scientific qualification or automatic threshold.
