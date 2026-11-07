# WP3 Amendment 2 validation

Evidence class: software/input-integrity and short CPU preflight checks only. No registered-window measurement or scientific labels were generated.

- `cpu_summary.json` / `cpu_results.json`: eight 20-step profiles, commands, exit/status/wall/source hashes. Stock vanLeer fails; the other seven pass.
- `ta1_bit_comparison.json`: actual frozen TA1 versus the current quick job, matched plain and Dual-value u/p hashes.
- `reference_audit.json`: both storage-order direction hashes and all eight selected-epsilon field hashes versus registered FD-08.
- `frozen_semantics_audit.json`: unchanged measurement helper/constant/window bytes and reproducible TA1-to-GRAD00 diff.
- `focused_checks.json`, `focused.txt`, `pytest_focused.xml`: 175 focused tests, compileall, 1.8 scalar selftest.
- `selftest110.txt`, `instantiate110.json`: 120 scalar tests under 1.10 and successful immutable-environment instantiate.
- `pytest_full_result.json`: completed, uncapped result-side full suite; 3657 passed, 74 skipped, failed nodes `[]`. No baseline was rerun.
- `protected_before.json` / `protected_after.json`: source/environment/reference/generated-worker preservation.
- `waterlily_source_audit.json`: pinned installed primary-source identities and version differences.
- `SHA256SUMS`: hashes of this directory's files except itself, for transfer integrity only; this is not a study freeze.

`run_cpu_validation.py` reproduces short CPU checks in a fresh output directory. It deliberately refuses reused profile directories. Each Julia subprocess has a 480 s safety limit; the separately recorded full pytest run has no cap. The TA1 wrapper files are copies of prior capture helpers with only their output destinations changed, never edits to the frozen TA1 source.

`COMMIT_FILES.txt` enumerates all files from this invocation for Claude's host commit, including the report and this validation directory. Existing UNCONFIGURED kernels are excluded; the user requested a second, post-commit configured render by Claude.
