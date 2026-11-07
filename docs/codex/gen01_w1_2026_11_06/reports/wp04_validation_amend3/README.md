# WP4 Amendment 3 validation

This directory contains development software and CPU-capability evidence only. It is not a
registered TOPO-2D-00 result, a transfer verdict, GPU qualification, mesh acceptance or physical CFD evidence.
The final status and exact command results are in ../wp04_report.md and validation.json.

- `targeted_execution.json`: compileall, all219 TOPO tests, diff-check commands and timings.
- `full_execution.json`: the exact user-specified full pytest invocation, supplied host baseline,
  source hashes before/after, actual failure-node set and complete-run result.
- `cpu_execution.json`, `cpu_selftest/`: short Re200 CPU run, 59 assertions, raw forceCSV/TOML/JSON,
  evolved moving ground, common phase, polygon closing-edge probes, checkpoint and WP1/WP2 integration.
- `provider_origins.json`: read-only sibling source paths, separate temporary source snapshots and SHA256.
  The snapshots contain only the two provider files, not a repository clone. Their original source
  hashes are checked before/after the CPU run.
- `geometry_summary.json`, `independent_geometry_review.md`: all10scene hashes, periodic sampling metrics,
  true gap/clearance/thickness gates, thickness ratios and independent source/camber/cap checks.
- `protected_source_closure.json`: no protected source/evidence/registration mutation relative to e3dcdf61.
- `amendment_authority.json`, `worker_routing.json`: read-only registration identity, ownership boundaries
  and actual unavailable OpenCode catalog attempts/native fallback. No paid API or global config change.
- `synthetic_analysis/`, `checker_cli.json`: made-up coefficient data only; independent arithmetic agrees
  and written-once outputs refuse a second write. Its CONCORDANT label is NOT a measured study result.
- `partial_precedence_counterexample.json`: raw synthetic input demonstrating the remaining rule conflict.
  PARTIAL is not claimed reachable while the needed clarification is unanswered.
- `wp5_geometry_readback.json` / `wp5_geometry_readback_v2.json`: actual current downstream loader rejects implicit closure at its old
  adapter; no mesh or RANS execution was performed. It is a software integration preflight only.
- `schema_comparison.json`: schema byte hashes/different JSON paths for Claude's later integration.
- `wp04_pending_files.json`: exact modified/new files to commit on the host; no moves in this attempt.
- `log_archives.json`: raw logs and deterministic gzip archive hashes. Raw .log files are not commit targets.
- `SHA256SUMS`: hashes of the delivered validation artifacts, excluding this manifest itself.

No historical validation directory was modified. No freeze, Kaggle/GPU/RANS run, commit or push was made.
