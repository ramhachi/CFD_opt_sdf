# GRAD-00 Amendment 3 validation records

These are implementation, input-integrity, synthetic-contract and short CPU
software checks from 2026-11-07. They are not registered-window BOUNDED/AGREE
measurements, GPU results, or physical/gradient qualification. The complete
report and future host runbook are in `../../wp03_report.md`.

`cpu_results.json` and `cpu_summary.json` cover eight sequential, real 20-step
preflights. Stock vanLeer exits 2 with finite selected_plain and nonfinite
selected_dual; the other profiles pass. The direct Julia checks intentionally
do not publish production runner identities/DONE/manifests and cannot be used
as measured campaign outputs. `ta1_bit_comparison.json` compares actual frozen
TA1 plain/Dual captures with the new quick preflight; `determinism_*` in the job
is only a same-build repeat. Argmax coordinates and solid signs are descriptive,
including the Float64 pressure-tangent maximum in the represented body interior.

Each `synthetic/` profile runs the actual main/save_run!/index/hash code with
preflight/run_one stubs, verifies seven runs and thirteen localization assertions,
and records zero solver steps. Failure-label fixtures stay in the tests; no
campaign `analysis.json` has been created here. `source_review.json` is an
independent software review, with the synthetic source-pin boundary stated.

The recorded drivers refuse reused run output. Run fresh copies in a sibling
validation directory to repeat them. The CPU driver reuses the retained
Amendment 2 short-check driver, with a 480 s per-process safety limit. The
result-side full pytest driver has no timeout, excludes only
`tests/test_lbm_metal.py`, disables cacheprovider, and does not run a base suite.
Package checks instantiate only the existing 1.10 project with automatic
precompilation/registry updates disabled; Project/Manifest hashes remain intact.

`protected_before.json` / `protected_after.json` and the final result record
check the 228 preserved files. `SHA256SUMS` covers every retained file here other
than itself, with paths relative to this directory. `COMMIT_FILES.txt` lists all
intended changed/new repository paths, including the report and design memo.
No git mutation, Kaggle operation, GPU solve, or full-window CPU solve occurred.
